# 16.9. Handling `BUFFER_UNDERFLOW`, `BUFFER_OVERFLOW`, Connection Closure, and Buffer Resources

## Objectives and context

In **JSSE (Java Secure Socket Extension)**, `SSLEngine` provides TLS/DTLS at the `ByteBuffer` level rather than owning a socket. The application is responsible for moving data over the network, handling handshake state, allocating buffers, coordinating non-blocking I/O, and **closing TLS per protocol**. In particular, the two `SSLEngineResult.Status` values `BUFFER_UNDERFLOW` and `BUFFER_OVERFLOW` **are not simply errors requiring connection closure**: they are data- and memory-coordination signals.

After this lesson, you will be able to:

1. Distinguish **network packet buffers** from **application plaintext buffers** for both directions of `SSLEngine`.
2. Interpret all four `Status` values (`OK`, `BUFFER_UNDERFLOW`, `BUFFER_OVERFLOW`, `CLOSED`) together with `HandshakeStatus`, `bytesConsumed`, and `bytesProduced`.
3. Resolve `BUFFER_UNDERFLOW` by **retaining unprocessed bytes and reading more data**, increasing capacity only when needed to hold a TLS record; never losing packet fragments.
4. Resolve `BUFFER_OVERFLOW` by **draining/flushing or growing the destination buffer** properly for `wrap` and `unwrap`; never looping endlessly with unchanged buffers.
5. Send and receive `close_notify` via `closeOutbound`, `wrap`, and `unwrap`, tracking `isInboundDone/isOutboundDone`; distinguish abrupt EOF from valid TLS closure.
6. Design capacity caps, pooling, backpressure, cleanup, timeouts, and failure tests for a non-blocking Java 17+ application.

This lesson includes **two standalone runnable Java programs**: one probe triggering `BUFFER_OVERFLOW`/`BUFFER_UNDERFLOW`, and a TLS 1.3 loop between two `SSLEngine`s in RAM with a test KeyStore/truststore, data exchange, `close_notify` exchange, and close-state verification. The loop example is purely an **in-memory simulation**: when deploying real `SocketChannel + Selector`, add I/O scheduling, concurrency, timeouts, policies, and resource management as covered in later sections.

## 1. Why does `SSLEngine` need four buffer directions?

Visualize a TLS connection:

```text
SENDING APPLICATION                                    RECEIVING APPLICATION
plaintext ByteBuffer                                        plaintext
         |                                                       ^
         v                                                       |
     engine.wrap(src, networkOut)                    engine.unwrap(networkIn, dst)
         |                                                       ^
         v                                                       |
TLS record bytes (ciphertext/handshake)       TLS record bytes received from network
         |                                                       ^
         +-------- SocketChannel / network ---------------------+
```

Each side typically organizes separate buffers:

| Logical buffer | Contents | Writer | Consumer |
| --- | --- | --- | --- |
| `applicationOut` | Plaintext **waiting to be sent** | Application | `engine.wrap(...)` |
| `networkOut` | TLS records **waiting to be written to socket** | `engine.wrap(...)` | `SocketChannel.write(...)` |
| `networkIn` | TLS records **read from socket** | `SocketChannel.read(...)` | `engine.unwrap(...)` |
| `applicationIn` | **Decrypted** plaintext | `engine.unwrap(...)` | Application |

These are **four roles**, not strictly four literal `ByteBuffer` instances. An application may maintain queues of plaintext messages, multiple network buffers, or a memory pool. What is mandatory is **never mixing up directions, `position/limit` states, and data ownership**.

A TLS record can contain handshake content, application content, or alerts. Thus **`wrap` does not always consume plaintext to encrypt**, and **`unwrap` does not always return plaintext**. During handshakes or closure, `wrap(EMPTY, networkOut)` can still emit control records, and `unwrap` can consume network bytes while producing **0 application bytes**.

`SSLEngine` never reads/writes sockets itself; if you receive `BUFFER_UNDERFLOW` without arranging a network read, state will not advance. If you hit `BUFFER_OVERFLOW` without freeing the destination buffer, calling again with identical arguments creates a busy spin.

## 2. `ByteBuffer` is the second state machine

To coordinate accurately, always remember:

- `capacity()`: physical allocated capacity.
- `position()`: current read/write index.
- `limit()`: read/write boundary.
- `remaining()`: number of bytes readable/writable in the current mode, equal to `limit - position`.
- `flip()`: transitions from **write mode → read mode**, setting `limit=position` and `position=0`.
- `compact()`: after reading, shifts **unread bytes** to the start of the buffer and switches to **write mode** so more data can be read into the free space.
- `clear()`: switches to write mode, **does not wipe physical bytes**, and **does not logically preserve unread data**.
- `slice()/duplicate()`: may share backing memory; keep ownership separate and avoid mutating the same region while `wrap/unwrap` uses it.

Example receiving two fragments of the **same TLS record**:

```text
networkIn in WRITE MODE:
  [initial record bytes...][not yet received]  position=k

flip():
  [initial record bytes...]  position=0, limit=k  READ MODE

engine.unwrap(networkIn, applicationIn) -> BUFFER_UNDERFLOW

compact():
  [retained unread bytes][space for next read]  WRITE MODE

socket.read(networkIn) -> appends new data

flip() -> unwrap(...) again
```

**Never call `networkIn.clear()` after `BUFFER_UNDERFLOW`**, because it drops the unconsumed record fragment. `compact()` retains the incomplete piece and is the right operation before reading more. If `unwrap` consumed part of the data, `compact` keeps only **the remainder**, without re-copying already-processed bytes.

Small mental-model snippet (`buffer` starts in write mode with `position=3`):

```java
buffer.flip();           // position=0, limit=3
// read 1 byte from buffer ...
buffer.compact();        // keeps 2 unread bytes, position=2, limit=capacity
// socket.read(buffer);  // fills more after those 2 bytes
```

This is an illustrative snippet, not a standalone program; buffers/sockets must be created and managed properly.

## 3. Reading `SSLEngineResult`: two independent status layers

`SSLEngine.wrap` and `SSLEngine.unwrap` return `SSLEngineResult` with:

```java
result.getStatus();
result.getHandshakeStatus();
result.bytesConsumed();
result.bytesProduced();
```

**`getStatus()`** reports the buffer/I/O outcome of the engine call. **`getHandshakeStatus()`** indicates what to do next for the TLS/DTLS handshake. These two fields **do not replace** each other: for instance, `Status.OK` can accompany `HandshakeStatus.NEED_TASK` or `NEED_WRAP`.

| `SSLEngineResult.Status` | Interpretation | Typical action |
| --- | --- | --- |
| `OK` | Operation was not blocked by a buffer/close condition | Process bytes consumed/produced, network I/O, and `HandshakeStatus`; do not assume the full message is done |
| `BUFFER_UNDERFLOW` | `unwrap` lacks enough TLS record bytes in the input network buffer | Retain unconsumed bytes, check capacity, then **read more from peer** |
| `BUFFER_OVERFLOW` | Destination buffer too small / out of space for output | **`wrap`: `networkOut`**; **`unwrap`: `applicationIn`**. Flush/drain or grow the right destination |
| `CLOSED` | Engine closed the relevant side or operation ended due to closed state | Handle `close_notify` and half-close; distinguish clean close from abnormal EOF |

Two important counters:

- `bytesConsumed()` is the byte count consumed from the **input buffers** in that call.
- `bytesProduced()` is the byte count written into the **output buffers** in that call.

**Never equate** plaintext byte counts with TLS network byte counts; TLS adds record headers, authentication tags, and metadata. One `unwrap` may **consume a TLS record** yet produce 0 plaintext because it was a handshake/alert message. One `wrap` may produce a record while consuming 0 application bytes.

A better progress metric is **bytes consumed/produced, handshake state changed, task completed, or socket transferred data**. When there is no progress and input is lacking, wait for I/O instead of spinning. Even so, certain TLS/DTLS transitions may advance internal state without obvious counter changes; implement per provider contract.

## 4. `BUFFER_UNDERFLOW`: insufficient incoming data, not a "bad packet"

Over TCP, `SocketChannel.read` **does not guarantee returning one complete TLS record**. TLS data may arrive across multiple fragments, or multiple records may arrive in a single read. `SSLEngine.unwrap` needs enough bytes to decrypt the record at hand; if short, it reports `BUFFER_UNDERFLOW`.

### Standard handling procedure

1. `networkIn` starts in **write mode** holding bytes read from the socket.
2. Call `networkIn.flip()` so the engine can read.
3. Call `SSLEngineResult r = engine.unwrap(networkIn, applicationIn)`.
4. If `r.getStatus()==BUFFER_UNDERFLOW`, **do not discard remaining bytes**. Call `networkIn.compact()` to return to write mode preserving unconsumed bytes.
5. Check whether `networkIn.capacity()` is smaller than `engine.getSession().getPacketBufferSize()`. If smaller, grow capacity **after preserving bytes**. If capacity is already sufficient, **do not grow unconditionally** just on underflow.
6. Register interest in `OP_READ`/wait for the socket to receive more bytes; retry `unwrap` only when new data or TLS state permits.
7. If the socket returns **-1 (EOF)**, handle as **transport closure**, never waiting forever for a record that will never arrive and never turning unknown into success.

Snippet handling one result (`networkIn` is managed in write mode outside the call; `appIn` is in write mode):

```java
networkIn.flip();
SSLEngineResult r = engine.unwrap(networkIn, appIn);
networkIn.compact(); // preserve remaining network bytes

if (r.getStatus() == SSLEngineResult.Status.BUFFER_UNDERFLOW) {
    int expected = engine.getSession().getPacketBufferSize();
    if (networkIn.capacity() < expected) {
        networkIn = growWriteModeBuffer(networkIn, expected);
    }
    // Wait for socket.read(networkIn) to deliver more bytes, DO NOT spin.
}
```

`growWriteModeBuffer(...)` is a helper that must **copy bytes currently held in write mode**, not a built-in JDK method; the full example below provides a `grow(...)` helper. Since `getPacketBufferSize()` can change across session/handshake, do not check the size only once when the connection is first created.

**Two cases that are easily confused:**

- `BUFFER_UNDERFLOW` when `networkIn.remaining()==0` in read mode or holding only a record header/fragment: **needs more bytes**.
- `BUFFER_OVERFLOW` on `unwrap` because `applicationIn` is too small: **cannot be solved by reading more network bytes**. Handle the output buffer.

**Never parse TLS record lengths to allocate arbitrary amounts** based on untrusted input. Use `getPacketBufferSize` and per-connection memory caps, test the provider, and close policy-violating connections.

## 5. `BUFFER_OVERFLOW`: insufficient space for output

### Case A — `wrap` overflow: `networkOut` is too small

`wrap(applicationOut, networkOut)` produces TLS network bytes (record headers, ciphertext, tags, handshake/alerts). Insufficient output space causes `BUFFER_OVERFLOW`. Do not try writing more application data into `applicationOut` to fix it; the source is not the problem.

Choose one of two paths:

1. If `networkOut` already holds bytes from earlier wraps, **flip and flush to `SocketChannel`**. If the socket writes partially, keep the remainder in read mode, register `OP_WRITE`, wait for socket writability, and finish writing. After flushing, `compact` back to write mode.
2. If capacity is genuinely smaller than the packet to emit, grow `networkOut` based on `engine.getSession().getPacketBufferSize()` and the application's upper bound. **Preserve already-written, unsent bytes.**

Conceptual snippet:

```java
SSLEngineResult r = engine.wrap(applicationOut, networkOut);
if (r.getStatus() == SSLEngineResult.Status.BUFFER_OVERFLOW) {
    // Prioritize sending TLS bytes already in networkOut;
    // if still insufficient: grow destination properly, never clear.
    int required = engine.getSession().getPacketBufferSize();
    networkOut = growWriteModeBuffer(networkOut, required);
    // Retry once space actually exists.
}
```

If growing while output is pending, the helper must preserve exact unsent bytes without duplicating or dropping records. In an event-loop model, **wait for `OP_WRITE` when the socket makes no progress**, rather than burning CPU calling `wrap` endlessly.

### Case B — `unwrap` overflow: `applicationIn` is too small

`unwrap(networkIn, applicationIn)` decrypts TLS records into plaintext. When plaintext does not fit the destination, it returns `BUFFER_OVERFLOW`. In that case:

1. Let the application **read/process bytes already in `applicationIn`**, then `compact()/clear()` when genuinely permitted.
2. Or grow `applicationIn` to at least `engine.getSession().getApplicationBufferSize()` plus any bytes already held.
3. Retry `unwrap` with the exact **unconsumed network bytes**; never discard queued TLS bytes.

Snippet:

```java
if (r.getStatus() == SSLEngineResult.Status.BUFFER_OVERFLOW) {
    int required = engine.getSession().getApplicationBufferSize();
    appIn = growWriteModeBuffer(appIn, required);
    // Then call unwrap again using the unprocessed network bytes.
}
```

**You do not have to grow memory on every overflow:** draining to the consumer can be better, especially when holding many connections. If the consumer is slow, apply **backpressure** and enforce queue limits; never grow buffers unboundedly to "absorb everything."

### Writing a mode-safe buffer growth helper

Assuming the current buffer is in **write mode** and `position` is the byte count to preserve:

```java
static ByteBuffer grow(ByteBuffer old, int minimum) {
    int capacity = Math.max(old.capacity() * 2, minimum);
    if (capacity > MAX_BUFFER_BYTES) {
        throw new IllegalStateException("Buffer cap exceeded");
    }
    ByteBuffer newer = ByteBuffer.allocate(capacity);
    old.flip();          // switch written bytes to read mode
    newer.put(old);      // copy exact bytes
    return newer;        // write mode, position after preserved data
}
```

`MAX_BUFFER_BYTES` is your own policy constant; this helper **is not a built-in API**. If a buffer is in **read mode** with unsent bytes, preserve `remaining()` and switch modes appropriately rather than blindly applying a write-mode helper. The second loop example provides a complete helper matching its assumptions.

## 6. `SSLSession` sizes: packet vs. application

At initialization:

```java
SSLSession session = engine.getSession();

ByteBuffer networkIn =
        ByteBuffer.allocate(session.getPacketBufferSize());
ByteBuffer networkOut =
        ByteBuffer.allocate(session.getPacketBufferSize());
ByteBuffer applicationIn =
        ByteBuffer.allocate(session.getApplicationBufferSize());
```

The returned numbers are recommendations/bounds from the session/provider for holding TLS and plaintext data. Do not treat them as business message sizes (HTTP payloads) or as immutable RAM amounts for the life of the connection.

| Type | Getter | Usage |
| --- | --- | --- |
| TLS network packet buffer | `getPacketBufferSize()` | Ensures network input can hold a complete record and network output can hold a `wrap`-generated record |
| Decrypted application buffer | `getApplicationBufferSize()` | Ensures `unwrap` destination can hold a record's plaintext data |
| Application output/source | No hard minimum for business input size | `wrap` may consume partially; rely on `bytesConsumed`/`hasRemaining` to send the rest |

**TLS data does not always expand by a fixed ratio.** Overhead varies by TLS version, cipher suite, and handshake vs. application record. Never guess `plaintext + 32` or hardcode `16 * 1024` as the sole capacity. Query the session and handle actual `SSLEngineResult` values.

**Resource protection limits:** even when helpers suggest growing, the application still needs per-connection RAM and connection limits; if quotas are exceeded, fail/close per policy instead of allocating unboundedly. This lesson's example uses an illustrative **1 MiB cap per buffer** — that is not an optimal number for all apps. Measure real handshakes/certificate chains/record sizes and bound concurrency.

## 7. Handshake status must still be handled when buffers are OK

`SSLEngineResult.HandshakeStatus` includes:

| Status | Application action |
| --- | --- |
| `NEED_WRAP` | Call `wrap` to produce handshake/TLS control records; send all network output |
| `NEED_UNWRAP` | Wait for TLS bytes from peer and call `unwrap` |
| `NEED_TASK` | Drain `engine.getDelegatedTask()` until no tasks remain; complete properly before advancing |
| `FINISHED` | Handshake **just** completed; appears only on `wrap/unwrap` results, **not** from `engine.getHandshakeStatus()` |
| `NOT_HANDSHAKING` | No handshake currently active at check time; application data/closure may still need handling |
| `NEED_UNWRAP_AGAIN` | Requests another `unwrap` call without necessarily reading more network data; Java 17 docs describe this for **DTLS** to process internally buffered handshake data |

During `NEED_TASK`, some tasks (certificate validation, keys, trust manager) may **block** even though the `SSLEngine` I/O API is non-blocking oriented. In a real selector server, run tasks in a **bounded executor**/worker instead of stalling the event loop. Be careful with per-engine synchronization: never let multiple threads concurrently call `wrap/unwrap`/mutate a single connection's `ByteBuffer`s.

General flow:

```text
engine.getHandshakeStatus()
      |
      +-- NEED_TASK ------> drain / execute delegated tasks ---+
      |                                                       |
      +-- NEED_WRAP ------> wrap(empty or app bytes) ---------+--> write networkOut
      |                                                       |
      +-- NEED_UNWRAP ----> network input ready? -- no: OP_READ |
      |                             | yes                      |
      |                             v                          |
      |                           unwrap                       |
      |                             |                          |
      +-- NEED_UNWRAP_AGAIN -------> unwrap (DTLS) ------------+
      |
      +-- FINISHED/NOT_HANDSHAKING --> application IO / close
```

After **every `wrap/unwrap`**, check both `getStatus()` and `getHandshakeStatus()`. Even with `OK`, the engine may still need `NEED_TASK` or `NEED_WRAP`. And `FINISHED` does not mean the connection closed; it only means the TLS handshake just finished.

## 8. Stopping data writes does not mean complete TLS closure

TLS has the **`close_notify` closure alert**. On `SSLEngine`, manage **both directions independently**:

- `closeOutbound()` signals the application will **send no more new plaintext**. The engine must emit a close message via `wrap(EMPTY, networkOut)`; the application must **send all those TLS bytes** to the peer.
- `isOutboundDone()` reports the engine has finished outbound processing; **it does not guarantee the socket transmitted all bytes in `networkOut` or the kernel send queue**.
- When receiving the peer's `close_notify`, call `unwrap(networkIn, applicationIn)` so the engine processes it; the result may be `Status.CLOSED` and `isInboundDone()==true`.
- Each side must emit `close_notify` per TLS/protocol rules and app policy. In common client/server protocols, the side initiating closure sends first, and the peer receives it and sends its own `close_notify`.
- Once **both engine directions are done** and all network output is flushed, the transport can close; in practice handle half-close, outstanding app data, timeouts, and I/O errors.

```text
Client                                Server
------                                ------
stop application writes
closeOutbound()
wrap(EMPTY, networkOut)
          -- TLS close_notify -->   unwrap(...)
                                       isInboundDone == true
                                   closeOutbound()
                    <-- close_notify -- wrap(EMPTY, networkOut)
unwrap(...)
isInboundDone == true
Both outboundDone/inboundDone when fully processed
Close channels after pending network bytes are flushed
```

**Never** call `SocketChannel.close()` right after `engine.closeOutbound()` while `networkOut` remains unsent: the peer may see EOF without `close_notify`, losing the valid TLS termination signal.

### Abrupt EOF, `closeInbound()`, and truncation

If `SocketChannel.read() == -1` before receiving `close_notify`:

- This is a **truncated TLS stream / unexpected peer transport closure** (or a policy/protocol failure to close cleanly).
- `engine.closeInbound()` notifies the engine no more incoming TLS bytes will arrive. Per Java Javadoc, it **can throw `SSLException` when the peer has not sent a proper closure message** — **never swallow the error and treat the connection as cleanly closed**.
- You may still need `closeOutbound()` to release engine state per policy, yet never report that the peer completed TLS closure.
- For sensitive data, design application-level framing and completeness checks (e.g., content length/expected message count) so truncated data is never treated as complete. `close_notify` does not replace "business transaction committed successfully."

Illustrative snippet:

```java
if (endOfStream) {
    try {
        engine.closeInbound();
    } catch (SSLException truncated) {
        // Peer did not close TLS cleanly; record and refuse incomplete data.
        throw truncated;
    } finally {
        engine.closeOutbound(); // allow send-side cleanup per state machine
    }
}
```

`endOfStream` and `engine` are application-defined variables; this snippet **does not** replace network flushing or retry/backpressure/cleanup. Never call `closeInbound()` prematurely just to "force" handshake/unwrap completion.

**TLS 1.3 note:** `close_notify` and half-close policies must align with the application protocol. A side receiving `close_notify` may still have outbound data depending on state and policy, yet the application must define clearly when to stop sending and avoid hanging. A closed `SSLEngine` **cannot be reused** for a new connection.

## 9. First Java example: deliberately triggering OVERFLOW and UNDERFLOW

`EngineStatusProbe.java` runs **without a real server, certificate, or socket**: it creates two fresh `SSLEngine`s from the default `SSLContext` to observe status codes. The client needs to emit a TLS ClientHello, yet the network output buffer is only **1 byte**, making `wrap` return `BUFFER_OVERFLOW`. The server just started handshaking and received zero bytes, so `unwrap` returns `BUFFER_UNDERFLOW`.

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLSession;

public final class EngineStatusProbe {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();

        SSLEngine client = context.createSSLEngine("localhost", 443);
        client.setUseClientMode(true);
        client.beginHandshake();
        SSLSession session = client.getSession();

        SSLEngineResult overflow =
                client.wrap(ByteBuffer.allocate(0), ByteBuffer.allocate(1));

        SSLEngine server = context.createSSLEngine();
        server.setUseClientMode(false);
        server.beginHandshake();
        SSLEngineResult underflow =
                server.unwrap(ByteBuffer.allocate(0),
                        ByteBuffer.allocate(session.getApplicationBufferSize()));

        System.out.println("wrapStatus=" + overflow.getStatus());
        System.out.println("unwrapStatus=" + underflow.getStatus());
        System.out.println("wrapConsumed=" + overflow.bytesConsumed());
        System.out.println("unwrapProduced=" + underflow.bytesProduced());

        client.closeOutbound();
        server.closeOutbound();
    }
}
```

```bash
javac -encoding UTF-8 EngineStatusProbe.java
java EngineStatusProbe
```

**Verified stdout on the test JDK:**

```text
wrapStatus=BUFFER_OVERFLOW
unwrapStatus=BUFFER_UNDERFLOW
wrapConsumed=0
unwrapProduced=0
```

Explanation:

- `wrapStatus=BUFFER_OVERFLOW` occurs because **network output destination is too small**, not because of a bad certificate. With empty input during a handshake, the engine is merely trying to emit a control record.
- `unwrapStatus=BUFFER_UNDERFLOW` occurs because network input has **0 bytes**, with no record to parse.
- `wrapConsumed=0` and `unwrapProduced=0` are both expected in these two calls.
- The example **does not complete a handshake** and opens no sockets. The two `closeOutbound()` calls merely mark no further sends; they **must not** be considered a successful `close_notify` exchange.

Exact output details may vary if a provider/JSSE version has special behavior; the core lesson is how `Status` guides handling. When working with real providers, always handle `Status` rather than assuming a single call succeeds.

## 10. Second Java example: two TLS 1.3 `SSLEngine`s running in RAM

This example demonstrates full coordination:

- A **server `SSLEngine`** with a `PrivateKeyEntry` and **lab** self-signed certificate in `server.p12`.
- A **client `SSLEngine`** with `trust.p12` trusting only the generated lab certificate. The example **does not use an accept-all `TrustManager`**.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` so the client checks `localhost` against the SAN. Creating `SSLEngine("localhost",443)` **does not automatically guarantee** hostname verification unless endpoint identification is enabled.
- **TLSv1.3** handshake, exchanging TLS records between two `ByteBuffer`s in RAM, and decrypting the string `tls-data`.
- Client sends `close_notify`, server receives it and sends `close_notify`, client receives it; verifies all four inbound/outbound completion flags.
- Handles `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`; resolves overflow via `grow` and underflow by waiting for more bytes without losing data.

**Example boundary:** the `send` helper simulates copying all network output to the peer immediately in RAM, **not** replacing `SocketChannel.write` which can write partially. Tasks run inline for single-threaded testing; production needs a task executor, event-loop scheduling, fairness, cancellation, and timeouts. The **1 MiB** cap merely illustrates a memory limit.

### 10.1. Creating the certificate set inside the lab directory only

Use a fresh directory. In Bash, create a **lab-only** password variable:

```bash
mkdir jsse-engine-lab
cd jsse-engine-lab
read -r -s -p "Lab password: " LAB_PASS
echo
export LAB_PASS
```

In PowerShell, if using an environment variable, **enter a dedicated lab password**, never production credentials; e.g., prompt interactively via an appropriate environment security mechanism. Both `keytool -storepass:env` and the Java demo read `LAB_PASS`. Environment variables can be read by processes/diagnostics in some cases; **do not treat `:env` as a secret manager**.

Once `LAB_PASS` is set and you are in the lab directory, generate the server key pair/cert, export the cert, and import it into the lab truststore:

```bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 1 -dname "CN=localhost" -ext "SAN=dns:localhost" -ext "EKU=serverAuth" -storetype PKCS12 -keystore server.p12 -storepass:env LAB_PASS -keypass:env LAB_PASS

keytool -exportcert -alias server -rfc -file server.pem -keystore server.p12 -storetype PKCS12 -storepass:env LAB_PASS

# ONLY for self-created lab: trust the cert just created and self-verified!
keytool -importcert -alias server -file server.pem -keystore trust.p12 -storetype PKCS12 -storepass:env LAB_PASS -noprompt
```

`-noprompt` here is **only for the certificate the lab itself just generated**; never use it to silently trust a stranger's certificate. `server.p12` **contains the private key** and must be protected/deleted after the lab; `server.pem` holds the public certificate. The certificate has SAN `localhost` so the client's endpoint identification succeeds; no public DNS/TLS calls occur in the RAM demo.

### 10.2. Complete runnable program: `EngineLoopbackDemo.java`

```java
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.*;

public final class EngineLoopbackDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);
    private static final int LIMIT = 1024 * 1024;

    private static final class Side {
        final SSLEngine engine;
        ByteBuffer networkIn;
        ByteBuffer networkOut;
        ByteBuffer applicationIn;
        Side peer;

        Side(SSLEngine engine) {
            this.engine = engine;
            SSLSession session = engine.getSession();
            networkIn = ByteBuffer.allocate(session.getPacketBufferSize());
            networkOut = ByteBuffer.allocate(session.getPacketBufferSize());
            applicationIn = ByteBuffer.allocate(
                    session.getApplicationBufferSize());
        }
    }

    // Input must be in WRITE MODE; preserves existing bytes.
    private static ByteBuffer grow(ByteBuffer writeMode, int wanted) {
        int capacity = Math.max(writeMode.capacity() * 2, wanted);
        if (capacity > LIMIT) {
            throw new IllegalStateException("Buffer cap exceeded");
        }
        ByteBuffer larger = ByteBuffer.allocate(capacity);
        writeMode.flip();
        larger.put(writeMode);
        return larger;
    }

    // In the lab, copies full TLS bytes into the peer's receive buffer.
    private static boolean send(Side side) {
        if (side.networkOut.position() == 0) return false;
        side.networkOut.flip();
        int needed = side.peer.networkIn.position() +
                side.networkOut.remaining();
        if (side.peer.networkIn.remaining() <
                side.networkOut.remaining()) {
            side.peer.networkIn = grow(side.peer.networkIn, needed);
        }
        side.peer.networkIn.put(side.networkOut);
        side.networkOut.clear();
        return true;
    }

    private static boolean handshakeStep(Side s) throws Exception {
        SSLEngineResult.HandshakeStatus before =
                s.engine.getHandshakeStatus();
        switch (before) {
            case NEED_TASK -> {
                Runnable task;
                while ((task = s.engine.getDelegatedTask()) != null) {
                    task.run();
                }
                return true;
            }
            case NEED_WRAP -> {
                SSLEngineResult result =
                        s.engine.wrap(EMPTY.duplicate(), s.networkOut);
                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_OVERFLOW) {
                    s.networkOut = grow(s.networkOut,
                            s.engine.getSession().getPacketBufferSize());
                    return true;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new SSLException(
                            "Unexpected handshake wrap: " + result);
                }
                boolean sent = send(s);
                return sent || result.getHandshakeStatus() != before;
            }
            case NEED_UNWRAP, NEED_UNWRAP_AGAIN -> {
                if (before ==
                        SSLEngineResult.HandshakeStatus.NEED_UNWRAP &&
                        s.networkIn.position() == 0) {
                    return false;
                }
                s.networkIn.flip();
                SSLEngineResult result =
                        s.engine.unwrap(s.networkIn, s.applicationIn);
                s.networkIn.compact();

                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                    if (s.networkIn.capacity() <
                            s.engine.getSession().getPacketBufferSize()) {
                        s.networkIn = grow(s.networkIn,
                                s.engine.getSession().getPacketBufferSize());
                        return true;
                    }
                    return false; // Wait for more TLS bytes from peer.
                }
                if (result.getStatus() ==
                        SSLEngineResult.Status.BUFFER_OVERFLOW) {
                    s.applicationIn = grow(s.applicationIn,
                            s.engine.getSession().getApplicationBufferSize());
                    return true;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new SSLException(
                            "Unexpected handshake unwrap: " + result);
                }
                return result.bytesConsumed() > 0 ||
                        result.bytesProduced() > 0 ||
                        result.getHandshakeStatus() != before;
            }
            case NOT_HANDSHAKING, FINISHED -> {
                return false;
            }
        }
        return false;
    }

    private static void handshake(Side client, Side server)
            throws Exception {
        client.engine.beginHandshake();
        server.engine.beginHandshake();
        for (int i = 0; i < 500; i++) {
            boolean a = handshakeStep(client);
            boolean b = handshakeStep(server);
            boolean done =
                    client.engine.getHandshakeStatus() ==
                            SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING &&
                    server.engine.getHandshakeStatus() ==
                            SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING;
            if (done) return;
            if (!a && !b) {
                throw new SSLException("Handshake stalled");
            }
        }
        throw new SSLException("Handshake loop limit");
    }

    private static void deliverAndUnwrap(Side receiver)
            throws Exception {
        int attempts = 0;
        while (receiver.networkIn.position() > 0 && attempts++ < 100) {
            receiver.networkIn.flip();
            SSLEngineResult r = receiver.engine.unwrap(
                    receiver.networkIn, receiver.applicationIn);
            receiver.networkIn.compact();
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                receiver.applicationIn = grow(receiver.applicationIn,
                        receiver.engine.getSession().getApplicationBufferSize());
            } else if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                if (receiver.networkIn.capacity() <
                        receiver.engine.getSession().getPacketBufferSize()) {
                    receiver.networkIn = grow(receiver.networkIn,
                            receiver.engine.getSession().getPacketBufferSize());
                }
                return;
            } else if (r.getStatus() ==
                    SSLEngineResult.Status.CLOSED) {
                return;
            } else if (r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Unexpected data unwrap: " + r);
            }
        }
    }

    private static void write(Side sender, Side receiver,
            byte[] plaintext) throws Exception {
        ByteBuffer input = ByteBuffer.wrap(plaintext);
        int attempts = 0;
        while (input.hasRemaining() && attempts++ < 100) {
            SSLEngineResult r =
                    sender.engine.wrap(input, sender.networkOut);
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                sender.networkOut = grow(sender.networkOut,
                        sender.engine.getSession().getPacketBufferSize());
                continue;
            }
            if (r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Unexpected data wrap: " + r);
            }
            send(sender);
            deliverAndUnwrap(receiver);
        }
        if (input.hasRemaining()) {
            throw new SSLException("Data loop limit");
        }
    }

    private static void close(Side sender, Side receiver)
            throws Exception {
        sender.engine.closeOutbound();
        for (int i = 0; !sender.engine.isOutboundDone() && i < 100; i++) {
            SSLEngineResult r = sender.engine.wrap(
                    EMPTY.duplicate(), sender.networkOut);
            if (r.getStatus() ==
                    SSLEngineResult.Status.BUFFER_OVERFLOW) {
                sender.networkOut = grow(sender.networkOut,
                        sender.engine.getSession().getPacketBufferSize());
                continue;
            }
            if (r.getStatus() != SSLEngineResult.Status.CLOSED &&
                    r.getStatus() != SSLEngineResult.Status.OK) {
                throw new SSLException("Close wrap failed: " + r);
            }
            send(sender);
        }
        if (!sender.engine.isOutboundDone()) {
            throw new SSLException("Close stalled");
        }
        deliverAndUnwrap(receiver);
    }

    private static SSLContext context(Path store, char[] pass,
            boolean useIdentity) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(store)) {
            ks.load(in, pass);
        }
        if (useIdentity) {
            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, pass);
            SSLContext ssl = SSLContext.getInstance("TLS");
            ssl.init(kmf.getKeyManagers(), null, null);
            return ssl;
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(ks);
        SSLContext ssl = SSLContext.getInstance("TLS");
        ssl.init(null, tmf.getTrustManagers(), null);
        return ssl;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java EngineLoopbackDemo server.p12 trust.p12");
        }
        String fromEnv = System.getenv("LAB_PASS");
        if (fromEnv == null || fromEnv.length() < 6) {
            throw new IllegalArgumentException("LAB_PASS is required");
        }
        char[] pass = fromEnv.toCharArray();
        try {
            SSLEngine a = context(Path.of(args[1]), pass, false)
                    .createSSLEngine("localhost", 443);
            a.setUseClientMode(true);
            a.setEnabledProtocols(new String[]{"TLSv1.3"});
            SSLParameters cp = a.getSSLParameters();
            cp.setEndpointIdentificationAlgorithm("HTTPS");
            a.setSSLParameters(cp);

            SSLEngine b = context(Path.of(args[0]), pass, true)
                    .createSSLEngine();
            b.setUseClientMode(false);
            b.setEnabledProtocols(new String[]{"TLSv1.3"});

            Side client = new Side(a), server = new Side(b);
            client.peer = server;
            server.peer = client;

            handshake(client, server);
            byte[] msg = "tls-data".getBytes(StandardCharsets.UTF_8);
            write(client, server, msg);
            server.applicationIn.flip();
            byte[] received =
                    new byte[server.applicationIn.remaining()];
            server.applicationIn.get(received);

            close(client, server);
            close(server, client);

            System.out.println("handshakeProtocol=" +
                    a.getSession().getProtocol());
            System.out.println("messageRecovered=" +
                    Arrays.equals(msg, received));
            System.out.println("clientInboundDone=" + a.isInboundDone());
            System.out.println("serverInboundDone=" + b.isInboundDone());
            System.out.println("clientOutboundDone=" +
                    a.isOutboundDone());
            System.out.println("serverOutboundDone=" +
                    b.isOutboundDone());
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
```

### 10.3. Compiling, running, and verifying output

After creating `server.p12`/`trust.p12` and setting `LAB_PASS` as shown above:

```bash
javac -encoding UTF-8 EngineLoopbackDemo.java
java EngineLoopbackDemo server.p12 trust.p12
```

**Expected stdout on JDK 17+ with a compatible TLS 1.3/KeyStore provider:**

```text
handshakeProtocol=TLSv1.3
messageRecovered=true
clientInboundDone=true
serverInboundDone=true
clientOutboundDone=true
serverOutboundDone=true
```

Because private/public keys and TLS sessions are randomly generated, **do not** rely on TLS record bytes matching across runs. The output above reports logical state without displaying secrets.

**Reading the code in sequence:**

1. `context(...,true)` loads the KeyStore containing the server's private key via `KeyManagerFactory`; `context(...,false)` loads the truststore containing the lab certificate via `TrustManagerFactory`. The client verifies the server certificate using the truststore without trust-all; `HTTPS endpoint identification` verifies `localhost`.
2. `Side` allocates `networkIn`/`networkOut` per `getPacketBufferSize()` and `applicationIn` per `getApplicationBufferSize()`. They start in **write mode**, keeping `send` and `unwrap` handling consistent.
3. `handshakeStep` handles `NEED_TASK`, `NEED_WRAP`, and `NEED_UNWRAP`. On `BUFFER_OVERFLOW`, it grows the right **destination**; on `BUFFER_UNDERFLOW`, `compact` preserves bytes and waits for the peer to provide more network data. The `NEED_UNWRAP_AGAIN` branch reflects the API state, primarily used with DTLS.
4. `send` simulates `write/network transport` by copying TLS bytes from `networkOut` into the peer's `networkIn`. In the lab, the peer can accept all bytes immediately. **Real sockets have partial writes/reads**, so never replace network I/O primitives directly with `send`.
5. `write` passes `tls-data` through `client.wrap`; the server calls `unwrap` to recover plaintext. Every step must check `Status` and never return plaintext not protected/verified by TLS.
6. `close(client,server)` calls `closeOutbound`, generates `close_notify` via `wrap(EMPTY)`, and feeds it to the server's `unwrap`. Then the server does the same back to the client.
7. `isInboundDone/isOutboundDone` inspect engine state after **simulated `close_notify` exchange**. On real sockets, also ensure the kernel has sent all bytes before closing the transport.
8. `grow` caps a single buffer to prevent unbounded memory growth; production needs buffer pools, per-connection budgets, and cap-exceeded strategies.
9. `LAB_PASS` is read from the environment solely for lab operations, without exporting raw private keys. `Arrays.fill(pass, '\0')` shortens the `char[]` lifetime; environment variables/other `String`s still require secret-manager/ACL governance per policy.

**Important:** this program is a fixture demonstrating the basic flow **for one small message** over TLS 1.3 in RAM, not a production-ready NIO server implementation. It does not implement socket fairness, partial writes, multiple concurrent requests, memory pressure, cancellation, application framing, shutdown timeouts, TLS renegotiation/DTLS retransmission, or all provider-specific handshake cases. Subsequent sections specify what must be added.

When finished, delete the files containing the **lab private key** and unset the shell environment variable, e.g., `unset LAB_PASS` in Bash. Never copy self-signed lab certificates into system/production truststores. To test TLS 1.2, update the protocol on both engines and re-test thoroughly rather than assuming identical close/handshake behavior.

## 11. From RAM simulation to `SocketChannel + Selector`

In a real Java NIO server, network buffers must manage **asynchronous operations and partial I/O**.

### Read flow

```text
OP_READ fired
    |
    v
readBytes = channel.read(networkIn in WRITE mode)
    |
    +-- >0 --> networkIn.flip()
    |          engine.unwrap(networkIn, applicationIn)
    |          networkIn.compact()
    |                |
    |                +-- OK: process result, handshake, and plaintext
    |                +-- UNDERFLOW: keep remainder, wait OP_READ or grow capacity as needed
    |                +-- OVERFLOW: drain/grow applicationIn, retry
    |                +-- CLOSED: process inbound close_notify, schedule outbound close
    |
    +-- =0 --> wait for next event, DO NOT spin
    |
    +-- -1 --> peer transport EOF; check close_notify / closeInbound
```

**Reading enough before unwrap** does not mean waiting until `networkIn` is full; a buffer may hold a complete record with just a few hundred bytes used. Attempt `unwrap` with available bytes and decide from the status. When multiple TLS records sit in `networkIn`, keep processing until below threshold, input runs short, output fills, or fairness budget expires.

### Write flow

```text
App bytes present or engine NEED_WRAP/CLOSING
    |
    v
engine.wrap(applicationOut, networkOut in WRITE mode)
    |
    +-- BUFFER_OVERFLOW --> flush networkOut or grow networkOut
    +-- OK/CLOSED -------> networkOut.flip()
                           channel.write(networkOut)
                                |
                                +-- partial write --> keep remainder,
                                |                    wait OP_WRITE
                                |
                                +-- all sent -------> networkOut.compact()
                                |                    (or clear when empty)
                                |
                                +-- exception ------> close/error policy
```

If `channel.write(...)` writes 0 bytes, **do not** retry in a busy loop. Register `OP_WRITE` and resume when the socket becomes writable; in many selector implementations, leaving `OP_WRITE` always enabled causes continuous wakeups, so disable it when no output is pending.

**Protecting data during partial writes:**

```java
networkOut.flip();
channel.write(networkOut);
networkOut.compact(); // retain bytes not yet consumed by the channel
```

This is a short snippet assuming `networkOut` starts in **write mode**. If the channel wrote everything, `compact()` returns to write mode at position=0; if partially written, `compact()` keeps remaining TLS bytes for the next `OP_WRITE`. Never call `clear()` after a partial write.

### When both pending output and handshake `NEED_UNWRAP` exist

You may need to **finish sending already-generated bytes** before the peer responds in the handshake, while still reading incoming bytes and running tasks. Design a state machine where each connection has bounded work per event, separate queues/app-I/O, and state-driven `OP_READ/OP_WRITE` allocation. Never hold system-wide locks while running trust managers or network I/O.

## 12. State-based connection closure and guaranteed cleanup

A production design should use explicit phases rather than a single `boolean closed` for everything:

| Phase | Work to complete |
| --- | --- |
| `OPEN` | Allow app writes, normal wrap/unwrap |
| `DRAIN_APP` | Stop accepting new app messages, flush accepted messages into TLS records per policy |
| `SEND_CLOSE_NOTIFY` | `closeOutbound`, continue `wrap(EMPTY)` as needed, flush all outbound TLS bytes |
| `WAIT_PEER_CLOSE` | Wait for `unwrap` to process peer's `close_notify`, with a deadline; never wait infinitely |
| `TRANSPORT_CLOSE` | Once policy met or error confirmed, cancel selector interest, cancel tasks/queues, close socket |
| `RELEASE` | Return pooled buffers, release connection state, emit metrics, never reuse closed engine |

Not every app must wait forever for "the peer's `close_notify` first": set a **shutdown timeout**. If it times out and the transport must close, record that the connection **did not perform a complete TLS close**, never turning a forced close into a security success.

For abruptly reset connections, I/O exceptions, or EOF without `close_notify`, mark **truncation/unclean close**. If the app processes only complete messages with its own framing/authentication, it may have a policy for retaining committed messages; that is **different** from claiming the TLS connection closed cleanly.

**Never let a pool reuse a closed `SSLEngine`**, especially when key/session states change. `SSLSession` may be cached/resumed in JSSE via separate TLS mechanisms, which is **not** reusing the `SSLEngine` object itself across peers.

### Must `closeInbound()` always be called?

No. When the peer sends `close_notify` and `unwrap` processes it, `isInboundDone()` becomes true inside the engine; calling `closeInbound` **to pretend `close_notify` was received** is wrong. Only when the transport ends without the engine receiving closure should you call `closeInbound` to signal no more inbound data, and **handle any `SSLException`**. Never "suppress errors" from closure alerts with `try/catch(Exception ignored)`.

### Buffer resources after closing

- Java heap `ByteBuffer.allocate` needs no `free()`; drop references so GC reclaims them once unowned.
- Direct buffers `ByteBuffer.allocateDirect` live outside managed heap memory, with release managed by JVM/Cleaners and providers; avoid internal APIs/`sun.misc.Unsafe` to force uncontrolled unmap/free.
- If using a **buffer pool**, **return a buffer exactly once** after no `wrap/unwrap`/socket write/task still uses it. Never return a buffer to the pool while `networkOut` still holds unsent bytes or `networkIn` still holds a TLS record fragment.
- Plaintext `applicationIn/applicationOut` can hold sensitive contents. `clear()` and `compact()` alter only metadata and **do not erase old data**; when zeroization is required, actively overwrite contents cleanly before reuse, mindful of JVM copies/GC limits.
- Avoid keeping `ByteBuffer.slice()`/`duplicate()` after the owner has returned the backing buffer to the pool; doing so can cause data races or leak plaintext across connections.

## 13. Capacity planning, pooling, and backpressure

A single connection may hold multiple buffers of tens of KiB or more. With thousands of connections, oversized pre-allocation strains heap/direct memory/GC. Conversely, undersized buffers cause repeated overflow/underflow, copying, and allocations.

### Design rules

1. **Size from `SSLSession`**, without treating session getters as mandatory simultaneous allocations for all buffers. Allocate lazily or pool by size classes depending on load.
2. Set **per-connection byte caps**, global direct/heap caps, concurrent handshake limits, and delegated task caps. Never grow buffers infinitely because a peer sends malformed data.
3. Do not pile up unconsumed app messages: if the application consumer lags, **pause reading/throttle `OP_READ`** within reason, propagate backpressure upstream, and bound queues.
4. **Pool** network buffers as direct buffers if real benchmarks show socket I/O gains; heap buffers may be cheaper for business logic/plaintext. Never assume direct is always fastest.
5. Enforce clear buffer ownership; never share a writable buffer between two `SSLEngine`s concurrently, even to save memory.
6. Grow buffers only with proven need: `BUFFER_UNDERFLOW` with undersized packet capacity, or `BUFFER_OVERFLOW` with insufficient output capacity or undrained consumer.
7. When memory quotas are hit, fail/close cleanly with metrics and shed load rather than OOMing the entire JVM.
8. Cap retries per operation within one event tick so a peer cannot cause CPU starvation; when no progress occurs, wait for the corresponding I/O or task.

Rough sizing formula:

```text
memoryPerConnection ~= networkInCapacity
                     + networkOutCapacity
                     + applicationInCapacity
                     + queuedAppOutBytes
                     + bufferPoolOverhead
                     + TLS/session/key material overhead

total ~= sum(active connection memory)
         + global caches + executor queues + JVM overhead
```

This is a **budgeting estimate**, not an exact JVM native memory measurement. TLS providers also allocate objects/session caches/temporary buffers; measure peak/RSS/direct buffer pools, GC allocation, write queues, and handshake concurrency.

### Useful metrics

| Metric | Meaning |
| --- | --- |
| `sslengine_wrap_status_total{status="BUFFER_OVERFLOW"}` | Output network buffer insufficient |
| `sslengine_unwrap_status_total{status="BUFFER_UNDERFLOW"}` | Input TLS record fragmented or capacity insufficient |
| `sslengine_unwrap_status_total{status="BUFFER_OVERFLOW"}` | Plaintext buffer full or consumer slow |
| `sslengine_handshake_duration`, `task_queue_delay` | Track latency/bottlenecks in TLS handshakes and delegated tasks |
| `tls_pending_network_out_bytes` | Pending socket write pressure |
| `tls_pending_app_in_bytes` | Application consumer/backpressure load |
| `tls_unclean_eof_total` | Connections truncated without `close_notify` |
| `tls_clean_close_total` | Clean `close_notify` completions |
| `tls_buffer_grows_total`, `tls_buffer_cap_exceeded_total` | Churn/capacity pressure and malicious/oversized records |
| `tls_active_connections`, `pool_bytes_in_use` | Resource budget and pool leak detection |

Tag metrics by provider/TLS version and high-level service, avoiding high cardinality from per-sample connection IDs/remote IPs. Never log TLS plaintext or private keys to debug; enable `-Djavax.net.debug=ssl,handshake` only on scoped test systems while understanding its output.

## 14. Essential test matrix

| Scenario | How to reproduce | Right outcome |
| --- | --- | --- |
| `wrap` output too small | `EngineStatusProbe` `ByteBuffer.allocate(1)` | `BUFFER_OVERFLOW`; no app data lost |
| `unwrap` empty input | Fresh server engine, empty network buffer | `BUFFER_UNDERFLOW`; waits for network |
| TLS record split across 2–3 fragments | Socket/test transport delivers piece by piece | Retains unprocessed bytes via `compact` and reassembles cleanly |
| Two TLS records in one read | Peer sends multiple records before one `read` | Processes sequentially until underflow/no progress, dropping nothing |
| Plaintext buffer full | `unwrap` with insufficient destination | `BUFFER_OVERFLOW`; drains/grows app buffer, retries |
| Socket partial write | Channel consumes only part of `networkOut` | Retains remainder, waits for `OP_WRITE`; no duplicate sends |
| `SocketChannel.read()==0` | Non-blocking I/O with no data yet | Does not spin |
| `SocketChannel.read()==-1` before `close_notify` | Abrupt transport disconnect | Truncation/unclean EOF; `closeInbound` per policy and handles exception |
| Client `close_notify` then server replies | `EngineLoopbackDemo` | Both `isInboundDone`/`isOutboundDone` true |
| `close_notify` lost in one direction | Drop `close_notify` message in test transport | Does not report clean close |
| Slow handshake `NEED_TASK` | Trust manager task simulates delay | Does not block system-wide selector; bounded executor |
| Peer floods continuously, slow consumer | Throttle application processing | Backpressure prevents RAM explosion |
| Memory cap exceeded | Intentionally configure small buffer cap | Fails cleanly under control, no endless growth |
| Expired/untrusted cert | Use wrong keystore/hostname mismatch in lab | Handshake fails; never disable trust checks as a workaround |
| Different TLS 1.2/1.3 and providers | Test on target JDK/provider | Verifies compatible state machine without relying on one exact trace |

In integration tests, **never manufacture expected results by catching every exception and returning success**. In particular, certificate errors, TLS record integrity errors, `close_notify`/truncation, and buffer caps must produce distinct, observable failures.

## 15. Common mistakes and fixes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating `BUFFER_UNDERFLOW` as corrupted TLS | Missing bytes does not mean a bad record | Keep remainder, wait for more bytes, check capacity |
| Calling `clear()` on network input after underflow | Logically discards incomplete record bytes | Call `compact()` then read more |
| Calling `unwrap` endlessly with no new bytes | Busy loop, CPU spikes | Wait for `OP_READ` or event/task progress |
| Doubling buffers on every underflow | Unbounded RAM growth, masks stall bugs | Compare `getPacketBufferSize()` and cap capacity |
| Seeing `unwrap` overflow and reading more from socket | Wrong buffer: app output is full | Drain/grow `applicationIn` |
| Seeing `wrap` overflow and growing application buffer | Wrong buffer: network output is full | Flush/grow `networkOut` |
| Calling `clear()` on `networkOut` after partial socket write | Loses TLS bytes, breaks record stream | `flip → write → compact` |
| Ignoring `bytesConsumed()` | Can lose plaintext or miscount | Rely on ByteBuffer positions and result counters |
| Treating `OK` as handshake finished | `NEED_TASK/NEED_WRAP` may remain | Always process `HandshakeStatus` |
| Running heavy delegated tasks on the selector | Blocks hundreds of connections | Bounded executor and per-engine ownership |
| Closing socket right after `closeOutbound()` | `close_notify` was never sent | `wrap(EMPTY)`, flush TLS bytes first |
| Assuming `isOutboundDone()==true` means socket queue is empty | Engine does not track kernel/socket pending bytes | Track `networkOut` and socket write completion |
| Swallowing `SSLException` from `closeInbound` | Hides truncated connections | Mark unclean EOF and check app framing |
| Reusing a closed `SSLEngine` | Engine state is not reset for a new connection | Create a new engine |
| Thinking `ByteBuffer.clear()` wipes plaintext from RAM | Only resets position/limit metadata | Perform explicit zeroization per policy and lifecycle |
| Returning buffer to pool while `slice/duplicate` is active | Causes data leaks / races | Enforce clear buffer ownership, refcounts/lifecycle |
| Unbounded allocations per handshake | Flood of handshakes causes OOM/GC | Connection quotas, memory caps, bounded tasks |
| Testing only the happy path | Bugs surface under fragmentation/partial writes | Test underflow/overflow/truncation/slow consumers |
| Enabling trust-all so the demo runs | Loses TLS identity verification | Use proper lab truststore and endpoint identification |
| Copying the RAM demo straight into production | Lacks selector/backpressure/timeouts/protocol integration | Build an event loop and tests for the real environment |

## 16. Practice exercises

1. **Buffer identification:** for `wrap` and `unwrap`, identify source/destination buffers and prove why `BUFFER_OVERFLOW` requires growing different buffers.
2. **Reading statuses:** `Status.OK`, `HandshakeStatus.NEED_WRAP`, `bytesConsumed=0`, `bytesProduced=125`. Why is this likely a handshake record rather than app ciphertext?
3. **Underflow with fragmentation:** peer sends a TLS record in three fragments. Trace `position/limit` before `unwrap`, after `compact`, and when receiving the third fragment. What is lost if `clear` is called instead of `compact`?
4. **Overflow on a slow socket:** `networkOut` holds a pending record and `channel.write` sends only 20%. Design `OP_WRITE` and `compact` to finish sending without duplicating records.
5. **Full plaintext buffer:** `unwrap` returns `BUFFER_OVERFLOW` while `networkIn` has plenty of bytes. Propose two fixes (drain consumer vs. grow buffer) and state pros/cons under high load.
6. **Java experiment:** run `EngineStatusProbe` and explain why `wrapConsumed=0` does not stop the client from emitting handshake data when the buffer is big enough.
7. **TLS loopback:** run `EngineLoopbackDemo` on TLSv1.3 and explain why output shows `messageRecovered=true` and all four Done flags true.
8. **Disabling hostname checks:** in a lab copy, remove `setEndpointIdentificationAlgorithm("HTTPS")` and analyze the impact: why can the client accept a trusted cert with the wrong hostname? Avoid putting this change into production.
9. **Abnormal closure:** simulate sending only TCP FIN without `close_notify`. Why can calling `closeInbound` throw an exception? How should already-received data be handled?
10. **Memory budget:** assume 30,000 connections, each with two packet buffers and one app buffer. Build a table of measured capacities and total RAM limits, calculating the impact of automatically doubling every buffer.
11. **TLS states:** distinguish `NEED_UNWRAP` and `NEED_UNWRAP_AGAIN`. When must you read the socket, and when not? Which status relates primarily to DTLS?
12. **Delegated tasks:** simulate a 200ms slow trust manager and explain why it must not run directly on a selector serving many connections.
13. **Result counters:** explain when `unwrap` consumes 200 TLS bytes yet produces 0 plaintext. Does that mean data was lost?
14. **Production checklist:** write pseudocode for `Selector` ensuring flush before close, no spinning when I/O returns 0, enforced memory caps, per-operation underflow/overflow metrics, and never using plaintext before TLS record integrity checks.
15. **Peer reset:** in a test, cut transport right after the app sends half a message. Distinguish TLS stream truncation from a "complete business message" and propose framing/transaction boundaries.
16. **Buffer pooling:** why doesn't `ByteBuffer.allocateDirect()` mean you can allocate endlessly? Describe returning buffers to a pool when the app holds a `slice()` and the socket still has pending writes.

**Completion criteria:** accurately explain `BUFFER_UNDERFLOW` (wait for data) and `BUFFER_OVERFLOW` (insufficient output space); preserve `ByteBuffer` contents via `flip/compact`; handle handshakes and `close_notify` via `SSLEngineResult`, distinguishing clean shutdown from truncation; and operate buffers with proper resource caps, selector handling, and backpressure.

## References

- [Java SE 17 `SSLEngine` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap`, `unwrap`, buffer overflow/underflow, closure, `closeInbound/closeOutbound`.
- [Java SE 17 `SSLEngineResult` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): `getStatus`, `getHandshakeStatus`, `bytesConsumed/bytesProduced`.
- [Java SE 17 `SSLEngineResult.Status`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html): `OK`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, `CLOSED`.
- [Java SE 17 `SSLEngineResult.HandshakeStatus`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): `NEED_TASK`, `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `FINISHED`.
- [Java SE 17 `SSLSession`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPacketBufferSize` and `getApplicationBufferSize`.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `compact`, `clear`.
- [Java SE 17 `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking reads/writes and end-of-stream.
- [Oracle Java Security Developer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): JSSE, SSLEngine examples, TLS initialization, and session configuration.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): alerts, record layer, and `close_notify`.