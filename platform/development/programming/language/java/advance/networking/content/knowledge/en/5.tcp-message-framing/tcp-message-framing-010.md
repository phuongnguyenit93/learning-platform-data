# Identifying Mutual Read-Wait Situations and Defining Exchange Order

In a TCP connection, both client and server **have the right to read and write**; TCP does not dictate which side must speak first. Therefore, the application protocol must define **who sends first, how much data is sent, when a message is complete, and which side waits for a response**.

Typical mistake: the client calls `readLine()` to wait for the server, while the server also calls `readLine()` to wait for the client. Neither side sends data first. Both can wait indefinitely even though TCP has connected successfully, the port is right, and the network path is working normally.

This is a **deadlock caused by protocol exchange order** (protocol-level circular wait). It must be distinguished from TCP packet loss, a slow server, or a connection error: increasing the timeout or enabling `TCP_NODELAY` does not solve a protocol where both sides are programmed to wait for input first.

## 1. Model: TCP Is Two Independent Byte Streams, Without Automatic Speaking Turns

For a `java.net.Socket`, the application receives an `InputStream` and an `OutputStream`. TCP preserves **byte** order on each direction of the connection, but **does not preserve `write()` call boundaries as messages**. The library does not automatically add "request" or "response".

- `socket.getInputStream().read()` can wait until there is a byte, EOF, a configured timeout, or an I/O error. It **does not make the peer send data automatically**.
- `BufferedReader.readLine()` waits for a line terminator (`\n`, `\r`, or `\r\n`) or EOF; if bytes are present without a line terminator, it may still keep waiting.
- `DataInputStream.readInt()` requires **four full bytes**. `readFully(byte[])` requires the full requested number of bytes; if not enough have arrived, the method can wait for more.
- `OutputStream.write(...)` writes bytes to the send path; with `BufferedOutputStream`/`BufferedWriter`, bytes may remain in the Java buffer until `flush()` or until the buffer is full.
- `socket.setSoTimeout(milliseconds)` sets a wait limit for blocking read operations on the socket. A value of `0` means no time limit; a timeout throws an exception, **it does not complete the message or fix a broken protocol design**.

The following diagram illustrates when both sides read before writing:

```text
Client                                         Server
  |                                             |
  | TCP connect ------------------------------> | accept()
  |                                             |
  | readLine()  (waits for server to send first)|
  |                                             | readLine()
  |                                             | (waits for client to send first)
  |                  NEITHER SIDE WRITES        |
  |                                             |
  | <------------ both wait together ---------->|
  |                                             |
  | if SO_TIMEOUT is set:                       |
  | SocketTimeoutException                      | SocketTimeoutException
  v                                             v
```

**Key takeaway:** A successful `connect()`/`accept()` only establishes the connection; they do not implicitly send a greeting, command code, or business payload. Do not confuse "connected" with "received the full request".

## 2. How to Identify Forms of Circular Wait

Not every read-wait case is caused by "both sides calling `read()` first"; the cause can be that **the condition for one side to send is never met by the other side**.

| Situation | Client is waiting | Server is waiting | Cause to check |
| --- | --- | --- | --- |
| **Both sides read first** | `readLine()` waiting for greeting | `readLine()` waiting for request | No opening message |
| **Client writes without flushing** | Waiting for response | Waiting for request from socket | Bytes still in `BufferedWriter`/`BufferedOutputStream` |
| **Missing delimiter** | Waiting for ACK | `readLine()` waiting for newline or EOF | Client wrote `"PING"` without sending `\n` |
| **Wrong frame length** | Waiting for ACK | `readFully()` waiting for more bytes | Prefix declares 100 bytes but client sent 20 |
| **Server waits for EOF** | Waiting for response, keeping output open | Reading until EOF before starting processing | Both sides disagree on how request ends |
| **Both write large blocks before reading** | `write()` may block due to full send buffer | `write()` may also block | Neither side drains the receive stream; two-way backpressure |
| **Out-of-turn handshake** | Waiting for `READY` before sending AUTH | Waiting for AUTH before sending `READY` | Different protocol specs/versions on the two sides |
| **Response not read/flushed** | Waiting for reply line | Already called `write("OK")` but kept in buffer | Missing `flush()` or terminator |

Because TCP is a byte stream, a single `write()` on the client **can be seen by the server across multiple `read()` calls**, or multiple writes can be coalesced into a single read. Therefore, explicit framing and exchange order are required, rather than relying on the assumption that "each write corresponds to one read".

**Distinguishing from network failure:** if packet capture/trace shows that the request has arrived yet the server is still waiting, check whether the parser is waiting for a delimiter/sufficient length or waiting for another business event. If no bytes appear on the sender's socket, check the write/flush steps and code path before blaming TCP. A thread dump showing both threads blocked on reading is a strong sign of a choreography bug, but it should be cross-checked with protocol state logs.

## 3. Mapping Wait Relationships to Find Bottlenecks

A deadlock can be described with a dependency graph:

```text
Client READ(response)
       |
       | response is only generated by server after receiving request
       v
Server READ(request)
       |
       | request is only generated by client after receiving response
       v
Client READ(response)       (cycle with no starting event)
```

The fix is to **break the cycle** with a designated first send step. For example, if the client actively requests work, set "client sends request" as the first event. If the server needs to announce a challenge/greeting immediately upon accepting a connection, set "server sends greeting" as the first step, and only then wait for a request from the client.

Do not handle deadlocks by having both sides call `Thread.sleep(100)`. Sleeping only shifts timing; each side still waits for the same condition. Similarly, offloading all work to a new thread does not by itself fix the send/receive contract. Separate threads help both directions operate concurrently when the protocol truly requires it, but framing, state, and completion conditions are still required.

## 4. Defining Exchange Order with a Protocol Contract

### 4.1. Request/response: client starts

Example of a **one UTF-8 line per message** protocol, with two commands `PING` and `PONG`. Condition: payload does not contain newlines, client sends one request at a time.

```text
Client Side                                Server Side
CONNECT ---------------------------------> ACCEPT
WRITE "PING\n"
FLUSH (push Java buffer) ----------------> READ LINE = "PING"
WAIT / READ LINE                          VALIDATE "PING"
                                          WRITE "PONG\n"
READ LINE = "PONG" <--------------------- FLUSH
VALIDATE RESPONSE                         READY FOR NEXT REQUEST / CLOSE
```

Minimal specification:

1. **Connection:** client connects; server calls `accept()`. Both sides agree on UTF-8 charset.
2. **Message unit:** one request/response ends with a newline; no newlines inside payload unless an escaping rule is defined.
3. **Send turn:** after connecting, **client writes the full request and flushes before reading**; server reads the full request before writing the response.
4. **Reply turn:** server writes response, newline, and flushes; client reads one line, validates content, and ends the turn.
5. **Errors and termination:** specify timeout, EOF, malformed frames, and closing behavior; the socket can continue serving subsequent turns if the protocol allows.
6. **Extension:** if there are multiple in-flight requests, add request IDs, correlation, ordering/state rules, or use a single reader loop to route responses.

A state table that can be used during implementation:

| Role | State | Valid action | Next state |
| --- | --- | --- | --- |
| Client | `CONNECTED` | Write full request + delimiter + flush | `WAIT_RESPONSE` |
| Client | `WAIT_RESPONSE` | Read full response or handle timeout/EOF | `READY` or `FAILED/UNKNOWN` |
| Server | `WAIT_REQUEST` | Read full framed request | `PROCESSING` |
| Server | `PROCESSING` | Validate/execute and write full response + flush | `WAIT_REQUEST` or `CLOSED` |

Defining states helps code review: if in `CONNECTED` the client reads before sending a request, that behavior violates the contract. If the server waits for a message that the client never sends in the current state, the protocol has a flaw.

### 4.2. Handshake: server starts

There is also the reverse protocol, where the server actively sends a greeting or challenge:

```text
Server                                Client
accept()
WRITE "READY\n", FLUSH ------------> READ "READY"
READ "AUTH ...\n" <---------------- WRITE "AUTH ...\n", FLUSH
VALIDATE, WRITE "OK\n", FLUSH -----> READ "OK"
```

This is also valid. Bugs happen when the server is programmed as "client speaks first" while the client is programmed as "server speaks first". Both sides and all client/server versions must use **the same contract**. If the protocol is versioned, it must clearly specify which side sends the version negotiation message and when; do not rely on guesswork by each endpoint.

### 4.3. Active two-way (full-duplex)

TCP supports both directions simultaneously: for example, chat or server push. In that case, there can be **one long-lived reading loop** at each end and an independent writing mechanism. It is not necessary to wait for an ACK before every message if the protocol allows concurrency, but:

- The reader must know how to frame messages; the writer must not send two half-frames interleaved from different threads.
- Writing to the same socket must be synchronized/serialized or use a single writer queue.
- ACKs/responses need a request ID to match the sent request; do not let two threads arbitrarily `read()` together and "compete" for each other's responses.
- Backpressure and queue limits must be clear, because the peer may read slowly.
- Closing, cancellation, EOF, and error handling must wake/unblock waiting parties.

Having both sides **write first and then read** is not always safe if each side tries to write a large amount of data exceeding buffer capacity without reading: both `write()` calls can still block. Concurrent interactive protocols must be designed so the receiving side keeps draining input.

## 5. Java 17+ Program Reproducing the Bug and the Fix

The experimental example uses loopback `127.0.0.1`/localhost via the address returned by `InetAddress.getLoopbackAddress()`. It creates **two independent connections**:

- Run 1: client and server both read first, **neither sends**. Both receive `SocketTimeoutException` after waiting, illustrating circular wait. Both client and server keep the socket open until both results are collected to avoid turning one side into an early EOF.
- Run 2: client sends `PING` + newline + flush and then reads; server reads `PING`, sends `PONG` + newline + flush. The exchange completes.
- `ExecutorService` is only used to run the server concurrently with the client in **one demonstration JVM**, not as a replacement for a protocol. The Future helps surface worker errors. No internet access is needed.

**File `ReadReadProtocolDemo.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ReadReadProtocolDemo {
    private static String readWithTimeout(Socket socket)
            throws IOException {
        socket.setSoTimeout(800);
        BufferedReader input = new BufferedReader(
                new InputStreamReader(socket.getInputStream(),
                        StandardCharsets.UTF_8));
        try {
            String line = input.readLine();
            return line == null ? "EOF" : line;
        } catch (SocketTimeoutException e) {
            return "TIMEOUT";
        }
    }

    private static void demonstrateWrongOrder() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(4000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> server = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        return readWithTimeout(peer);
                    }
                });
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    String clientResult = readWithTimeout(client);
                    String serverResult = server.get(4, TimeUnit.SECONDS);
                    System.out.println("BAD client read-first: " + clientResult);
                    System.out.println("BAD server read-first: " + serverResult);
                }
            } finally {
                worker.shutdownNow();
            }
        }
    }

    private static void demonstrateCorrectOrder() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(4000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> server = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        BufferedReader input = new BufferedReader(
                                new InputStreamReader(peer.getInputStream(),
                                        StandardCharsets.UTF_8));
                        BufferedWriter output = new BufferedWriter(
                                new OutputStreamWriter(peer.getOutputStream(),
                                        StandardCharsets.UTF_8));
                        String request = input.readLine();
                        if (!"PING".equals(request)) {
                            throw new IOException("Invalid request");
                        }
                        output.write("PONG");
                        output.newLine();
                        output.flush();
                        return request;
                    }
                });
                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(3000);
                    BufferedWriter output = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader input = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    output.write("PING");
                    output.newLine();
                    output.flush();
                    String reply = input.readLine();
                    if (!"PONG".equals(reply)) {
                        throw new IOException("Invalid response");
                    }
                    System.out.println("GOOD server read: "
                            + server.get(4, TimeUnit.SECONDS));
                    System.out.println("GOOD client read: " + reply);
                }
            } finally {
                worker.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        demonstrateWrongOrder();
        demonstrateCorrectOrder();
    }
}
```

Compile and run:

```bash
javac --release 17 ReadReadProtocolDemo.java
java ReadReadProtocolDemo
```

Stdout of a successful run:

```text
BAD client read-first: TIMEOUT
BAD server read-first: TIMEOUT
GOOD server read: PING
GOOD client read: PONG
```

Analysis:

- The two `BAD` lines are not packet loss: **no bytes were actively sent** on the first connection. The timeout only helps detect waiting instead of hanging forever; the program cannot "self-heal" send/receive errors if the order is not changed.
- The server has `setSoTimeout(4000)` on `accept()` and each peer socket has its own read timeout. With `readLine()`, a timeout occurs when a complete line has not been read within the corresponding read wait limit.
- In the correct version, the client does **write → newline → flush → read**; the server does **read → validate → write → newline → flush**. Roles are reversed without circular wait.
- `server.get(...)` is used to collect the result and propagate errors from the server thread back to main. Calling `get()` **is not** an application ACK; the client already received `PONG` over the input socket before printing the result.
- The 800 ms, 3000 ms, and 4000 ms timeouts are only for the demo. In busy environments, more appropriate configurations may be needed; timeout values are an operational policy, not protocol ordering.
- Server and client use the same UTF-8. `BufferedWriter.newLine()` writes the platform's line separator, and `BufferedReader.readLine()` accepts common line ending forms. Production formats should standardize on a fixed delimiter, such as CRLF or LF, so different languages/OSes behave consistently.

## 6. Defining Message Boundaries Before Defining Read Turns

An agreement that "client writes first, server reads later" is still not enough if **the server does not know whether the request is complete**. There are three common framing styles:

| Framing style | How a message ends | What must be agreed upon |
| --- | --- | --- |
| Delimiter (e.g. newline) | `\n`/`\r\n` terminates frame | Encoding, escaping delimiter in payload, line length limit |
| Length prefix | Send byte count N first, then exactly N bytes | Number type/endianness, limit on N, reading exact N bytes |
| Fixed size | Every frame is exactly K bytes long | Fixed K, padding, version, how to separate real data from padding |

**Line-based protocol:** `write("PING")` does not by itself create a line. You must send a delimiter via `write("\n")` or `newLine()`, then `flush()` if the stream is buffered. If the server calls `readLine()` while the client only wrote `PING` and waits for an ACK, the server will keep waiting for the line terminator.

**Length-prefix protocol:** the following pseudocode is a *code snippet inside a method with corresponding streams*; the reader must handle `IOException`:

```java
// Sender
byte[] payload = "PING".getBytes(StandardCharsets.UTF_8);
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(socket.getOutputStream()));
out.writeInt(payload.length);  // 4 bytes, big-endian
out.write(payload);
out.flush();

// Receiver (on the peer socket)
DataInputStream in = new DataInputStream(
        new BufferedInputStream(peerSocket.getInputStream()));
int length = in.readInt();
if (length < 0 || length > 64 * 1024) {
    throw new IOException("Invalid frame length");
}
byte[] message = new byte[length];
in.readFully(message);
String text = new String(message, StandardCharsets.UTF_8);
```

**Note:** `DataOutputStream.writeInt` and `DataInputStream.readInt` use 32-bit big-endian format; length bounds must be checked before allocating buffers. If the sender declares N bytes but only sends N−1 bytes and then waits for an ACK, the receiver's `readFully` will wait for the last byte. Do not equate "N characters" with "N UTF-8 bytes": Unicode characters can take multiple bytes.

Do not mix different framing methods on the two ends of the same connection, such as the sender using `DataOutputStream.writeUTF` (modified UTF-8 with a two-byte prefix) while the receiver reads a four-byte `readInt` followed by a standard UTF-8 payload.

**EOF-delimited protocol:** If the contract says "the request ends when the client closes its send direction", the client can flush buffers and then call `socket.shutdownOutput()`. The server reads until EOF, processes, and returns the response over the still-open direction. However, the client side **must not wait for a response before calling `shutdownOutput()`** in this protocol, because the server has not yet seen EOF to end the request. `shutdownOutput` is a half-close of the send side, unlike `socket.close()` which closes the entire socket. EOF is a data-transmission boundary, not proof that the business operation succeeded.

## 7. Read Waiting, Timeouts, and Connection Closing: Three Different Signals

When reading from a socket, handle these distinctly:

- **Complete message received:** the decoder/framer has extracted enough data per the protocol; only then transition state to PROCESSING or RECEIVED_RESPONSE.
- **Read returns `-1` or `BufferedReader.readLine()` returns `null`:** the peer closed its send direction cleanly and there is no more data; this is EOF. EOF may be valid if the protocol uses it as a delimiter, or it is a "peer closed prematurely" error when still expecting a frame.
- **`SocketTimeoutException`:** not enough data arrived for the read operation to finish within the set limit; **does not prove the peer never processed the request**.
- **Other `IOException`:** connection issue or I/O failure; partial data may have been sent/received. Transaction state must be evaluated at the application level.
- **No timeout set:** blocking calls can wait forever; production usually needs a read timeout and a deadline covering the entire request.

`Socket.setSoTimeout(3000)` limits the duration of **a single blocking read operation**, not the deadline for an entire multi-frame request, and it does not create a write timeout. When a request involves multiple reads, a separate **end-to-end deadline** is needed, otherwise the other side could trickle small amounts of data and stretch the total duration.

For `Socket.connect(SocketAddress, timeout)`, the timeout is for establishing the connection; it does not replace `SO_TIMEOUT` when reading. If `write()` also risks blocking due to backpressure, you need asynchronous/concurrent I/O design, size limits, queue management, and timeouts at the appropriate protocol or I/O layer; do not assume `setSoTimeout` protects all operations.

Application buffers and TCP buffers are different. A successful `flush()` only pushes data out of the buffer layers in use according to the stream contract; it **is not confirmation that the server has read/processed it**. You must wait for an application-level ACK/response per the protocol-defined semantics.

## 8. Naming Wait States to Detect Errors Early

If adding logs or metrics, log by request ID and phase:

```text
client(42) CONNECTED
client(42) WRITE_START
client(42) REQUEST_FLUSHED
client(42) WAIT_RESPONSE
server(42) REQUEST_FRAME_COMPLETE
server(42) PROCESSING
server(42) RESPONSE_FLUSHED
client(42) RESPONSE_RECEIVED
```

Some symptom pairs:

| Observation | Likely issue to check immediately |
| --- | --- |
| Both sides log `WAIT_READ`, no `WRITE_START` | Both sides are waiting for the other to speak first |
| Client logs `WRITE_START` but no `REQUEST_FLUSHED` | Buffering, `write` blocked, I/O error, or code never reaches flush |
| Client logs `REQUEST_FLUSHED`; server only logs `WAIT_FRAME` | Missing delimiter/length, charset/codec mismatch, server reading wrong connection |
| Server logs `RESPONSE_FLUSHED`; client has no `RESPONSE_RECEIVED` | Waiting for wrong frame, mismatched request ID, timeout/connection issue, incomplete response |
| Client waits for response; server logs `WAIT_EOF` | Both sides disagree on whether request ends with a delimiter or EOF |
| Both threads are blocked on `write` | Receiving side not draining stream; may need concurrent reader/backpressure |

A thread dump (e.g., `jstack` or `jcmd <pid> Thread.print`) can point out threads waiting on socket read/write. Internal method names vary across JDK versions, so focus on **stack traces, request IDs, and the state machine** rather than expecting a fixed system method name.

Packet capture can show TCP segments/ACKs, but **a TCP ACK is not an application ACK** and does not prove the server has read the frame or committed business logic. Application-layer logs/traces are needed to know what state the server reached. When logging payloads, avoid exposing passwords, tokens, or sensitive data; state, size, and ID are usually enough to analyze ordering.

## 9. Handling Concurrent Requests and Delayed Responses

The simple "send one request then read one response" protocol is easy to understand and avoids mixing up responses. When scaling up:

1. **Multiple requests on the same socket:** attach `requestId` to both request and response to avoid mistaking request A's response for B's. If the server can reply out of order, the client must route by ID instead of relying on send order.
2. **Only one message-dispatching reader per direction:** do not let multiple threads arbitrarily read the same `InputStream` and each "hope" to catch its own ACK. A central reader dispatches to pending requests by ID or queue.
3. **Serialize the writer:** if multiple threads write, ensure each frame's bytes remain intact in order; avoid interleaving headers/bodies of different requests' `write` calls.
4. **Server push:** unsolicited messages may arrive while waiting for a response, so the decoder needs to distinguish types like `EVENT`, `RESPONSE`, `ERROR`.
5. **Resource limits:** cap in-flight message count, frame size, queues, timeouts, and send rate; have proper cancel/close mechanisms.
6. **Retries:** a timeout waiting for a response can happen after the server has finished processing but the reply was lost; use idempotency keys/status queries when business operations have side effects. Do not automatically conclude "not processed" just because `read()` timed out.

A way to simplify before adding concurrency: verify a single request/response turn on one connection, one reader, and one writer under a clear contract. When expanding to full-duplex, preserve the verified framing, states, and ACK semantics.

## 10. Common Mistakes and How to Fix Them

| Bug in code/protocol | Why it is wrong | How to fix |
| --- | --- | --- |
| Client and server both call `readLine()` first | Circular wait: nobody sends | Designate an active side to send/greet |
| Writing `"PING"` then calling `readLine()` on client | Server may be waiting for a newline | Add the protocol's delimiter, then flush |
| Writing the full request but forgetting `BufferedWriter.flush()` | Bytes remain in Java buffer | Flush after building a complete frame |
| Server waits for `read() == -1`, client waits for ACK with output open | No EOF for server to start processing | Agree on framing; if truly EOF-delimited, flush + half-close |
| Client calls `read()` once and assumes it is the full response | TCP has no message boundaries | Use length prefix/delimiter and read completely |
| Server keeps response in buffer, then goes back to `read()` | Client has not seen response to continue | Flush response before waiting for next turn |
| Calling `Thread.sleep(...)` to "wait for enough bytes" | Timing does not prove a complete frame | Explicit framing and timeouts |
| Calling `InputStream.available() == 0` to conclude peer hasn't sent or is done | `available` only estimates immediately readable bytes without blocking, not message completion/EOF | Read according to framing; distinguish EOF, timeout, and error |
| Setting a huge timeout when both sides wait for each other | Only makes the deadlock last longer | Fix send/receive state ordering |
| Calling `socket.close()` after `write()` and assuming peer finished processing | Close/EOF is not a business ACK | Define and read an application-level response |
| Using two readers independently reading ACKs on the same socket | Can swallow the wrong response | One reader routing by correlation ID |
| Having both sides write a huge buffer before reading | Can block due to backpressure | Design full-duplex, drain input concurrently, and bound buffers |

## 11. Practice Exercises

**Exercise 1 — Find the deadlock:** Client calls `reader.readLine()` waiting for `READY` before sending `AUTH`; server calls `reader.readLine()` waiting for `AUTH` before sending `READY`. Draw the dependency and fix it so one side speaks first.

**Exercise 2 — Spot the missing frame:** Client calls `writer.write("HELLO")`, `writer.flush()`, then `readLine()` waiting for ACK. Server also uses `readLine()`. Why does the server still wait even though the client flushed? Fix one line of code.

**Exercise 3 — Distinguish bytes and messages:** Client sends a 12-byte length prefix and then sends only 5 bytes of payload. Server calls `readFully(new byte[12])`. If the client waits for a response, what state can the two sides fall into? When can the server raise an error?

**Exercise 4 — EOF protocol:** Server reads until EOF before sending a response; client sends a request and then waits for a response. What must the client do to end its send direction while still being able to read the response on the same TCP socket?

**Exercise 5 — Full-duplex:** Two concurrent requests A and B on one socket, and the server returns B before A. Explain why two threads both calling `readLine()` to wait for their own ACK can receive the wrong data. State the appropriate protocol structure and reader model.

**Suggested answers:**

1. If the server requires AUTH first while the client requires READY first, neither side sends. Either have the server send `READY\n` and flush, with the client sending `AUTH\n` after receiving it; or change the spec so the client sends AUTH first and update both.
2. `flush` does not automatically add a newline. After `write("HELLO")`, add `writer.newLine()` **before** `flush()` so the server gets a complete frame.
3. Server waits for 7 more bytes; client waits for ACK, creating a circular wait. The server only stops when enough bytes arrive, EOF causes `readFully` to fail, or a socket read timeout/other error occurs.
4. Flush Java wrappers and then call `socket.shutdownOutput()` so the server sees EOF; the client continues reading input until it gets the response, per a protocol allowing half-close.
5. Two readers compete for one byte stream, so one thread can receive the other request's frame. Add `requestId` and a single reader loop that routes replies by ID.

## References

- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `getInputStream`, `getOutputStream`, `setSoTimeout`, `shutdownOutput`, `setTcpNoDelay`.
- [Java SE 17 — `ServerSocket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `accept`, `setSoTimeout`, and listener.
- [Java SE 17 — `BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): `readLine()` and line-ending rules.
- [Java SE 17 — `BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html): `newLine()` and `flush()`.
- [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt()`, `readFully()`.
- [Java SE 17 — `OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `write`/`flush` semantics.
