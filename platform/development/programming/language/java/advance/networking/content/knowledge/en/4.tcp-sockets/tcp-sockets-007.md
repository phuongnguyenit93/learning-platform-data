# Flushing the Application Buffer Differs from Remote Application Confirmation

In **TCP communication using Java `Socket`**, calling `OutputStream.flush()` is usually a necessary step to push data sitting in the **application buffer** down to the lower layer. However, **`flush()` returning does not prove that the receiving application has read, processed, or successfully persisted the request**. To know that, you must design an **application-level acknowledgment/response (application-level ACK/response)** and specify exactly what the ACK signifies.

This lesson focuses on three events that are easily confused: **pushing data out of the Java buffer**, **the peer's TCP acknowledging bytes at the transport layer**, and **the peer application replying after performing its work**.

## 1. Four Completely Different Milestones in a Single Send

Suppose the client sends the request `REQ:42` over a TCP connection. The path can be visualized as follows:

```text
Client Java                              Server Java
+-------------------------+             +----------------------------+
| write(...)              |             |                            |
| BufferedOutputStream    |             |                            |
| [bytes still in buffer] |             |                            |
+------------+------------+             |                            |
             | flush()                   |                            |
             v                           |                            |
+-------------------------+             |                            |
| Socket OutputStream     |             |                            |
| passes bytes to OS      |             |                            |
+------------+------------+             |                            |
             v                           |                            |
+-------------------------+   TCP       +----------------------------+
| Local TCP send buffer   | ----------> | Remote TCP receive buffer  |
|                         | <---- ACK --| Remote TCP stack           |
+-------------------------+             +-------------+--------------+
                                                     |
                                                     v
                                        +----------------------------+
                                        | readFrame()/read(...)       |
                                        | validate / process business |
                                        +-------------+--------------+
                                                      |
                                          server sends "ACK:42"
                                                      |
Client readFrame() <----------------------------------+
(Client receives application ACK)
```

| Milestone | What has happened? | What is **not yet** guaranteed |
| --- | --- | --- |
| 1. `write(...)` into `BufferedOutputStream` | Bytes may be sitting in the Java buffer | Not certain they have been passed down to the socket |
| 2. `flush()` completes | Pending bytes in the Java buffer have been passed to the underlying stream per the `flush` contract, unless an error occurred | Does not prove bytes reached the peer OS, that the receiving application called `read`, or that business logic succeeded |
| 3. TCP ACK from the receiver | The TCP stack on the other end acknowledges receipt of the corresponding bytes per TCP's mechanism | Does not prove the server process has read or processed them; standard Java `Socket` does not provide an API to "wait for peer TCP ACK for this request" |
| 4. Application ACK/response | The server actively sends a reply message according to the **application protocol** | The level of confirmation depends on where the server sends the ACK: after reading, after validating, after committing, or only after queuing |

**The word "ACK" must include context.** A TCP ACK and an application-defined `ACK:42` are two different events. One side can receive all TCP segments and emit an ACK in the kernel even if the server program has never called `read()`. Conversely, an HTTP 200 or an "OK" message is an **application protocol** response, meaningful only according to the server's specific contract.

## 2. What Does `flush()` Actually Do in Java?

### 2.1. A Stream Chain Has Multiple Buffering Layers

```java
OutputStream raw = socket.getOutputStream();
BufferedOutputStream buffered = new BufferedOutputStream(raw);
DataOutputStream output = new DataOutputStream(buffered);

output.writeInt(6);
output.write("REQ:42".getBytes(StandardCharsets.UTF_8));
output.flush();
```

*This is an illustrative snippet inside a method that already has a `socket` variable and handles `IOException`; it is not a standalone program.*

- `DataOutputStream` writes binary structures; in this example `writeInt(6)` creates a four-byte length prefix.
- `BufferedOutputStream` accumulates bytes in JVM RAM. A `write(...)` call may only modify the Java buffer, **without** calling down to the socket immediately.
- `output.flush()` traverses the stream layer to flush `BufferedOutputStream`, forcing any remaining bytes to be written through `raw`. A successful write to the socket usually means the data has been accepted by the local socket layer for sending; **it produces no proof that the server has processed it**.
- If enough data is written to fill the buffer, `BufferedOutputStream` may automatically push data down to the underlying stream during `write()`. Therefore, one should not claim "no bytes go onto the network before flush."
- `OutputStream.flush()` on the base class is a **no-op**; its actual meaning depends on the implementation and the wrappers in use. Calling `flush()` directly on a socket stream is not an operation that "forces the remote side to acknowledge."

The `java.io.OutputStream` documentation emphasizes that flushing through abstractions provided by the operating system only guarantees transfer to the operating system layer per the stream contract, not that the destination task has completed. This is why `flush` cannot replace an application ACK.

### 2.2. `flush()` Can Throw `IOException`

If the stream is broken, closed, or an I/O error is detected, `write`/`flush` may fail. However:

- **An error is detected** ⇒ the request must not be recorded as successful; part of the bytes **may** still have gone out before the error occurred.
- **No error at `flush`** ⇒ only confirms that writing within the local API scope has completed. The server can still crash, the network can drop afterward, or the application ACK can be lost.

Therefore, neither state **conclusively determines** server-side business execution.

## 3. Practical Java 17+ Example: Flush Finished, but Application ACK Not Yet Sent

The example opens a TCP listener on **loopback** (no external network needed), creates a client connecting to the same JVM, and has the server read and validate the request. A `CountDownLatch` intentionally **holds back the ACK** until the client logs that `flush()` has completed. Thus the result does not depend on `Thread.sleep()` or machine speed.

The sample protocol uses **length-prefix framing**:

- Request: 4-byte `int` length + UTF-8 bytes containing `REQ:42`.
- Response: 4-byte `int` length + UTF-8 bytes containing `ACK:42`.
- The server checks the request before being allowed to reply; the client waits for the exact ACK and verifies its content.
- In the example, `ACK:42` **only proves that the server handler read/checked the request and sent a response**; there is no database or commit operation.

**File `FlushVsAckDemo.java`:**

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FlushVsAckDemo {
    static void writeFrame(DataOutputStream out, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(payload.length);
        out.write(payload);
    }

    static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > 4096) {
            throw new IOException("Invalid frame length");
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch handled = new CountDownLatch(1);
        CountDownLatch permitAck = new CountDownLatch(1);

        try (ServerSocket listener = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5000);
            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> server = workers.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(5000);
                        DataInputStream in = new DataInputStream(
                                new BufferedInputStream(peer.getInputStream()));
                        DataOutputStream out = new DataOutputStream(
                                new BufferedOutputStream(peer.getOutputStream()));

                        String request = readFrame(in);
                        if (!"REQ:42".equals(request)) {
                            throw new IOException("Unexpected request");
                        }
                        handled.countDown();

                        // Intentionally do not send ACK yet even though server has read/validated.
                        if (!permitAck.await(5, TimeUnit.SECONDS)) {
                            throw new IOException("ACK gate timeout");
                        }
                        writeFrame(out, "ACK:42");
                        out.flush();
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                });

                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(5000);
                    DataOutputStream out = new DataOutputStream(
                            new BufferedOutputStream(client.getOutputStream()));
                    DataInputStream in = new DataInputStream(
                            new BufferedInputStream(client.getInputStream()));

                    writeFrame(out, "REQ:42");
                    out.flush();
                    System.out.println("1. client: flush returned");

                    if (!handled.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Server did not read");
                    }
                    System.out.println("2. server: request validated");
                    System.out.println("3. client: application ACK not sent yet");

                    // Server is now permitted to send the response.
                    permitAck.countDown();
                    String ack = readFrame(in);
                    if (!"ACK:42".equals(ack)) {
                        throw new IOException("Wrong application ACK");
                    }
                    System.out.println("4. client: received ACK:42");
                } finally {
                    // Do not leave the server thread stuck if the client encounters an error.
                    permitAck.countDown();
                }
                server.get(5, TimeUnit.SECONDS);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
```

Compile and run with Java 17 or later:

```bash
javac --release 17 FlushVsAckDemo.java
java FlushVsAckDemo
```

Stdout on a successful run:

```text
1. client: flush returned
2. server: request validated
3. client: application ACK not sent yet
4. client: received ACK:42
```

**Reading the result correctly:** line 1 only states that the local flush completed; line 2 is an additional observation via a latch specific to this demo; line 3 proves the server still had not sent the ACK even though both flush and read/validate had finished; line 4 only appears after the client receives the **actual response frame** via `readFrame()`. In a production program, the client does not have a `handled` latch shared with the server process; it must rely on the **protocol response received over the network**.

Intentional limitations: the program uses a single request, a single server thread, loopback, and ASCII strings to clarify the essence; the latch only creates a deterministic experiment, not a distributed acknowledgment mechanism. `ServerSocket.setSoTimeout(5000)` limits how long `accept()` waits for a connection; `Socket.setSoTimeout(5000)` limits blocking read operations, **does not** set a deadline for the entire transaction, and does not create an application ACK. `Future.get(...)` is used to detect server thread errors rather than silently ignoring them.

## 4. TCP Is a Byte Stream, Not a Message Queue

One `output.write(bytes)` call on the client does not correspond 1-to-1 with one `input.read(bytes)` call on the server. TCP preserves byte order on a connection, while segmenting/coalescing bytes is decided by the operating system and network. For example:

- The client writes `"HEL"` then `"LO"`; the server may receive `"HELLO"` in a single read or across multiple reads.
- The client calling `flush()` on a request does not automatically add a message terminator. The server needs to know **where to stop reading**.
- `DataInputStream.readFully(payload)` reads until the requested length is met or reports EOF/error. The length must be checked before allocating the array to avoid dangerous input.
- Both sides only calling `read()` without flushing the remaining request/response in the buffer can lead to a **protocol deadlock**.
- One side calling `close()` or `shutdownOutput()` can help represent stream termination in an EOF-delimited protocol, but must not be confused with "the server has processed it"; you must actively flush Java buffers **before** `shutdownOutput()` if data remains in wrappers. For keep-alive/multiplexed requests, explicit framing is usually more appropriate than EOF.

The example in this lesson uses a 4-byte length via `DataOutputStream.writeInt`, followed by UTF-8 bytes; the server uses `readInt`/`readFully` following the convention. `DataInputStream.readUTF()`/`DataOutputStream.writeUTF()` also have their own framing, but use **modified UTF-8** and a different length prefix: **do not mix** `writeUTF` with a raw UTF-8 length-prefix protocol without defining a conversion.

## 5. Application-Layer ACKs Need a Clear Contract

There is no single universal ACK suitable for every request. A response message is only as trustworthy as **what the server defines and enforces**.

| ACK sent at the moment | What can the client conclude (if trusting server/protocol)? | What remains uncertain |
| --- | --- | --- |
| Server just `read` enough bytes | The process has extracted the full frame from the TCP stream | Not yet parsed/validated/committed |
| Server has parsed and validated | The data satisfies syntax/input policies | Business logic not yet executed |
| Server has enqueued the request | Accepted into the queue per contract | Worker has not processed it yet; queue may not be durable |
| Server has performed durable write/commit | Business logic reached the agreed commit point | Subsequent asynchronous side effects may not be finished |
| Server has completed the entire business operation | Work within the acknowledgment scope has been executed | Does not encompass all external systems unless included in the contract |

To state "**processed successfully**", the server needs to send the ACK **after** the desired success milestone. For instance, for a payment or data-write command, an ACK right after reading from the socket is too early; if the specification requires a commit, perform the commit before sending the ACK. If offloading work to a durable queue, return `ACCEPTED` rather than pretending it is `COMPLETED`.

A practical request/response protocol should specify:

1. **Frame/encoding:** length + UTF-8, newline-delimited, or a chosen standard. Specify size limits, protocol version, and error reporting.
2. **Correlation ID:** for example `requestId=42`; the ACK returns the same ID so responses from different requests are not confused on long-lived or concurrent connections.
3. **ACK semantics:** `RECEIVED`, `VALIDATED`, `COMMITTED`, `REJECTED`, transient error, etc., rather than just a vague "OK".
4. **Send order:** the client flushes the request after the complete frame; the server reads/validates/processes, then writes and **flushes the response**.
5. **Timeout/deadline:** set a wait limit for the response; handle socket closure, EOF, `SocketTimeoutException`, and protocol errors.
6. **Idempotency:** if the client resends due to a timeout, the server must have a way to recognize duplicate requests, typically by ID and business key.

**Do not use a `boolean sent = true` after `flush()` to mark status `COMPLETED`.** Local send status and server-side completion status are two different axes of observation.

## 6. A Timeout Does Not Prove the Server Has Not Processed the Request

Situations to distinguish:

| Phenomenon on client | What is actually known | Correct action |
| --- | --- | --- |
| `flush()` returns successfully, no reply yet | The client has passed the local write operation | Continue waiting for the application ACK within the deadline |
| `flush()` throws `IOException` | Local write encountered a detected error; partial data may have been sent | Do not treat as succeeded; handle **unknown** state if the operation has side effects |
| TCP ACK (if observed with network tools) | Kernel received TCP's byte acknowledgment | Does not replace an application response |
| Server reads frame then crashes before returning ACK | Client usually only sees EOF, reset, or timeout | Record uncertain state; decide on retry per protocol |
| Server commits then ACK is lost | Client times out **even though business logic succeeded** | Query status by ID or perform an idempotent retry |
| Client receives `ACK:42` per protocol | Server sent a reply at the milestone defined by the protocol | Transition state accordingly, verify ID/status/result |

In particular, a lost ACK creates a situation where **you cannot infer "did not run" solely from the client not seeing an ACK**. If the client retries a request with side effects, the server may execute it twice. To achieve an "at-most-once/exactly-once" effect in business logic, you need an idempotency key and to store duplicate-handling results aligned with the transaction/commit; TCP, `flush`, or automatic retries alone do not provide exactly-once processing.

**Example:** the client sends `charge(requestId=42, amount=100)`; the server deducts the funds and commits, but the response is lost. If the client resends with a new request ID, there is a risk of double-charging. An idempotent contract with the same ID and same data will return the stored result instead of running the business logic again.

With `Socket.setSoTimeout(...)`, a `read()` call can throw `SocketTimeoutException` when the read wait time is exceeded. That is only the timeout of the read operation; to enforce an **end-to-end** deadline, you must manage time across the entire request, including connect, queue, send, read, retry, and application processing.

## 7. APIs That Easily Cause Misunderstandings About Flush

### 7.1. `PrintWriter` and `autoFlush`

```java
PrintWriter writer = new PrintWriter(
        socket.getOutputStream(), true, StandardCharsets.UTF_8);

writer.print("PING");      // autoFlush=true does not auto-flush on print()
writer.println();          // println() triggers flush when autoFlush=true

if (writer.checkError()) {
    throw new IOException("Local output error");
}
```

The snippet above is inside a method that has `socket` and handles `IOException` (Java 17+). With `PrintWriter`:

- `autoFlush=true` flushes when calling **`println`, `printf`, or `format`**; it does not mean every `write`/`print` or every `\n` character auto-flushes.
- `PrintWriter`'s write methods **do not throw `IOException` directly like `DataOutputStream`**; use `checkError()` to observe the error state. `checkError()` flushes first before checking if the writer is still open.
- Even if `println()` auto-flushed and `checkError()` returns false, it still **does not prove the remote app has read or replied**.
- If using a text line protocol, specify the charset (e.g., UTF-8), line terminator, and line length limit; `BufferedReader.readLine()` can wait forever if the sender does not emit a delimiter or EOF.

### 7.2. `BufferedWriter` / `OutputStreamWriter`

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(socket.getOutputStream(),
                StandardCharsets.UTF_8));
writer.write("PING");
writer.newLine();
writer.flush();            // push char/byte buffer to underlying stream
```

*This illustrative snippet requires a `socket` variable and `IOException` handling in the enclosing method.* Unlike `PrintWriter` which has an auto-flush option, `BufferedWriter.newLine()` only writes the line separator to the stream and **does not flush immediately by default**. Calling flush resolves the **sender-side buffer**, while remote app confirmation still requires reading the reply. If wrapping an `OutputStreamWriter` with a character encoder, flush also helps push the character buffer down to the byte stream layer; it does not guarantee that bytes have been consumed by the remote handler.

### 7.3. `Socket.getOutputStream()` and `TCP_NODELAY`

For `Socket.getOutputStream()` without an added `BufferedOutputStream`, calling `flush()` usually does not produce an extra "send immediately" effect as learners often imagine: the socket already has an OS send buffer layer, and the base `OutputStream.flush()` has a no-op implementation. `setTcpNoDelay(true)` tunes **Nagle's algorithm** to reduce one form of delay when sending small packets; it **does not change** the definition of `flush()`, does not force the remote process to `read()`, and does not create an application ACK.

### 7.4. `close()`, `shutdownOutput()`, and EOF

- `close()` on a wrapper normally flushes per stream behavior and then closes the resource; `Socket.close()` closes the socket. Closing successfully is **not** an application response.
- For sockets supporting half-close, `shutdownOutput()` signals the end of sending (a TCP FIN after data already written to the socket); the receiver may see EOF after reading all data. **FIN/EOF does not mean the server has completed business processing.**
- If the sender still holds data in `BufferedOutputStream`, you must `flush()` that wrapper before calling `shutdownOutput()` on the socket; do not assume `shutdownOutput()` knows how to flush Java wrappers it does not own.
- For protocols that still need to receive an application ACK after finishing sending, half-close may be suitable in some protocols, but you must check both sides' contracts. Do not automatically close the input side as well before reading the response.

## 8. Practical Protocol Design and How to Measure/Test

For operations requiring correctness, milestones can be organized as:

```text
client: create requestId=42
client: encode frame + write + flush   → local SEND_ATTEMPTED
server: read full frame + validate     → server VALIDATED
server: execute and durable commit     → server COMMITTED
server: write ACK(COMMITTED, 42) + flush
client: read full ACK; verify id/status → client COMMITTED_CONFIRMED
```

If the request has no durable side effect, `PROCESSED` can be returned after processing instead of `COMMITTED`. If the server decouples asynchronous processing, return `ACCEPTED` with a tracking ID and let the client query status later. Defining clear milestones makes latency measurements meaningful:

- `write→flush`: time spent draining buffers/writing to the underlying stream on the client.
- `flush→first response byte`: a mix of network transmission, queuing, server processing, and waiting for the response.
- `request→ACK`: end-to-end latency according to the defined ACK milestone.
- TCP RTT or TCP ACK: transport-layer characteristics, **not** transaction latency.

When debugging the symptom "client flushed, yet server hasn't processed", check both sides: has the server called `accept`, is the frame complete, is the reader waiting for more bytes/delimiter, is a server thread/queue blocked, did the server flush the ACK, did reading the response time out. Packet capture can prove packets reached the TCP stack, but cannot directly prove business logic committed; to prove a business milestone, you need traces/logs with a correlation ID or state persisted at the server.

Note when using TLS: data also passes through the TLS encryption/buffering layer before reaching TCP; `flush()` at the application layer still **does not** become proof that the peer application has decrypted/processed it. The ACK must be defined by the protocol on top of TLS.

## 9. Common False Conclusions

| Claim | Assessment and reason |
| --- | --- |
| "`flush()` did not throw an error, so the other side received the message." | **False**: it may have only completed writing at the client layer; TCP ACK / remote app read is not proven. |
| "Seeing a TCP ACK means the server has processed the request." | **False**: the ACK is emitted by the TCP stack and does not substitute for `read`/business logic. |
| "The server calling `read()` once is enough for the whole message." | **False**: TCP is a byte stream; you must frame and read all data. |
| "`PrintWriter(autoFlush=true)` flushes on every `print` call." | **False**: auto-flush applies to `println`/`printf`/`format`. |
| "`Socket.close()` confirms the server has committed." | **False**: close/FIN/EOF belong to the connection, not business semantics. |
| "Timing out while waiting for an ACK means the server definitely did nothing." | **False**: the server may have committed, with the response lost. |
| "You can retry any request with side effects without an ID." | **False**: risks duplicate processing; idempotency and result management are required. |
| "The server sending `OK` right after enqueuing means all subsequent tasks are complete." | **False**: the ACK must clearly state `ACCEPTED` or `COMPLETED` based on the actual milestone. |

## 10. Self-Check Exercises

1. A client creates `BufferedOutputStream(socket.getOutputStream())`, writes 30 bytes, and then waits for the server to reply without calling `flush()`. Why can both sides get stuck?
2. The server uses `read()` and has read an initial part of the request. The client's `flush()` succeeded. Do we already know the length and content of the entire request?
3. When seeing a TCP ACK in Wireshark, can we conclude that the server has successfully written the data to the database?
4. The server commits a transaction and then loses the connection before sending the ACK. The client receives a timeout. Should the request state be treated as definitely `FAILED` or `UNKNOWN`? How can it be retried?
5. In the `FlushVsAckDemo` example, if you want the ACK to mean "durable write", where should the creation of `ACK:42` be moved?
6. A `PrintWriter` with `autoFlush=true` is called with `print("HELLO\n")` without calling `println()`. Can you assume it has flushed?

**Suggested Answers:**

1. The data may still be sitting in the Java buffer; the server waits for the frame, while the client waits for the ACK. Flush after completing the request frame.
2. No; TCP does not preserve `write` call boundaries. Read according to a length-prefix/delimiter and verify the full payload.
3. No; a TCP ACK only reflects TCP-layer progress.
4. State is **UNKNOWN**; if retrying, keep the same request ID/idempotency key or query the status first.
5. The server must execute and confirm the commit **before** sending the ACK; update the response semantics accordingly and keep flushing the response.
6. No. `PrintWriter`'s auto-flush is not triggered merely because `\n` was written via `print`.

## Official References

- [Java SE 17 — `OutputStream.flush()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): flush contract and operating system layer boundaries.
- [Java SE 17 — `BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html): byte buffer and how it flushes to the underlying stream.
- [Java SE 17 — `PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html): scope of `autoFlush` and `checkError()`.
- [Java SE 17 — `Socket`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): `getInputStream`, `getOutputStream`, `setSoTimeout`, `setTcpNoDelay`, `shutdownOutput`.
- [Java SE 17 — `DataInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readInt`, `readFully`, and byte framing.
