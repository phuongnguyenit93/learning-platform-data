# 16.8 SSLEngine with wrap, unwrap, delegated tasks, and handshake state management

`javax.net.ssl.SSLEngine` is the **socket-independent** TLS/DTLS processing layer of the Java Secure Socket Extension (JSSE). It accepts/delivers data through application-managed `ByteBuffer`s; the application itself transports ciphertext over TCP/transport, schedules reads/writes, runs delegated handshake tasks, and guarantees ordering. This API fits NIO servers, event loops, Netty-style transports, certain asynchronous I/O models, and programs that want to decouple the **TLS engine** from the **network transport**.

The focus of this lesson is **practical state management**: `wrap()`, `unwrap()`, `getDelegatedTask()`, `SSLEngineResult.Status`, and `SSLEngineResult.HandshakeStatus`. A proper loop must handle partial incoming records, full buffers, potentially blocking tasks, results consuming/producing zero bytes, and TLS closure via `close_notify`. Calling `wrap` and `unwrap` just once is **not enough** to establish a reliable TLS connection.

This lesson uses **Java 17+** and presents a real TLS 1.3 client/server demo using two `SSLEngine` instances connected via in-memory byte queues, requiring no open network ports. This demo lets you observe real handshakes, certificates, and encryption, while **intentionally not being a production NIO implementation**: buffers are oversized, the transport does not fragment, and delegated tasks run synchronously for easy inspection. Later sections explain precisely what must be added when moving to `SocketChannel`/`Selector`.

## 1. Where does `SSLEngine` sit in JSSE?

Diagram from **one** endpoint's perspective:

~~~text
                 APPLICATION                       NETWORK / TRANSPORT
                  (plaintext)                         (TLS records)
                      |                                     ^
                      v                                     |
              outboundApp ByteBuffer                       |
                      |                                     |
                      v                                     |
             SSLEngine.wrap(appSrc, netDst) ----------------+
                      ^
                      |
   local TLS state: handshake, certificate, session,
   key schedule, traffic keys, record encryption/decryption
                      |
                      v
             SSLEngine.unwrap(netSrc, appDst) <------------+
                      |                                     ^
                      v                                     |
              inboundApp ByteBuffer                 inboundNet ByteBuffer
                  (plaintext)                         (TLS records)
~~~

**`wrap(srcApp, dstNet)`** takes plaintext application bytes (when in an allowed phase), transforms them into protected TLS data or generates handshake/alert records, and places them into `dstNet`. The application must **send those bytes itself** over the transport.

**`unwrap(srcNet, dstApp)`** takes TLS bytes from the transport, decrypts/processes handshake messages, and (when appropriate) places application plaintext into `dstApp`. The application must **supply enough bytes in the exact order**.

These calls **do not read/write TCP themselves** and do not make a `SocketChannel` "ready" in the application's NIO logic. `SSLEngine` is a stateful TLS processor, while I/O multiplexing and framing/buffer ownership are the caller's responsibility.

### `SSLSocket` vs. `SSLEngine`

| Criterion | `SSLSocket` | `SSLEngine` |
| --- | --- | --- |
| Transport | Integrates socket and TLS streams. | **Transport-independent**; caller moves bytes in/out. |
| Programming model | `InputStream`/`OutputStream`, relatively simple. | `ByteBuffer` + state machine + scheduler. |
| Handshake | `startHandshake()` orchestrates the exchange. | `beginHandshake()` only initiates; caller must drive `wrap/unwrap/task` until done. |
| Backpressure/partial I/O | Library manages many stream details. | Caller manages `SocketChannel` partial reads/writes and queues. |
| Use case | Synchronous apps, simple examples, direct socket APIs. | Event loops/NIO, custom engine transports, async protocols. |
| Difficulty | Lower. | **Significantly higher**, easy to get state/buffers/close wrong. |

**Rule of thumb:** If you only want to make HTTPS calls, prefer `java.net.http.HttpClient` or an HTTP framework with proper TLS support. Do not write your own `SSLEngine` driver when a reliable networking library already solves these problems.

## 2. Four byte regions of an endpoint

An application using `SSLEngine` typically has four logical regions; libraries may represent them with various buffers/queues:

| Region | What bytes does it hold? | Who writes / who reads? |
| --- | --- | --- |
| **Outbound application** (`appOut`) | Plaintext app data to send. | App writes; `wrap` consumes. |
| **Outbound network** (`netOut`) | TLS handshake/alert/encrypted records to send. | `wrap` writes; transport reads/`SocketChannel.write` sends. |
| **Inbound network** (`netIn`) | TLS bytes received from peer; may be only **part of a record**. | Transport writes; `unwrap` consumes. |
| **Inbound application** (`appIn`) | Plaintext decrypted and authenticated by `unwrap`. | `unwrap` writes; app reads. |

**Important:** `wrap`/`unwrap` may consume/produce bytes, though **not necessarily at the same time**:

- `wrap(emptyApp, netOut)` can produce handshake records even with zero application bytes.
- `unwrap(netIn, appIn)` can consume many handshake bytes while producing **0 application bytes**.
- An `unwrap` encountering insufficient bytes may consume nothing: the caller must wait for more bytes from the network rather than spinning on the same data.
- A `wrap` after the handshake can produce TLS post-handshake messages or `close_notify`; do not assume it always produces only application ciphertext.

### A buffer is not a TCP "message boundary"

TCP is a **byte stream** and does not guarantee a single `SocketChannel.read` delivers one complete TLS record or only one record. Data can arrive split across multiple reads, or multiple TLS records can arrive in a single read. `SSLEngine` decodes TLS framing, yet the application must still **retain unconsumed bytes** in `netIn`.

Never treat `read()` returning 0 bytes as an "end of record" signal. In NIO, 0 usually means **no new data available right now**. `SocketChannel.read` EOF is represented by `-1`; TLS EOF handling must be distinct from both 0 and `BUFFER_UNDERFLOW`.

## 3. Creating the engine, configuring client/server, and ensuring identity

### 3.1. `SSLContext` must have policy-compliant key/trust managers

- **Server** uses `KeyManagerFactory`/key provider to select the appropriate certificate and private key; may require a client cert for mTLS.
- **Client** uses `TrustManagerFactory`/an approved PKIX truststore to verify the server certificate.
- On a raw `SSLEngine` client, supply **peer host/port** when creating the engine, and enable `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` if verifying HTTPS hostnames.
- `SSLContext.getInstance("TLS")` provides a TLS engine and does not imply legacy SSL protocols. You can restrict to `TLSv1.3` in a lab, while production follows security policy/peer compatibility.

Basic API:

~~~java
// Illustrative API snippet: sslContext must already be initialized with proper key/trust policy.
SSLEngine client = sslContext.createSSLEngine("api.example.test", 443);
client.setUseClientMode(true);

SSLParameters p = client.getSSLParameters();
p.setProtocols(new String[] {"TLSv1.3"});
p.setEndpointIdentificationAlgorithm("HTTPS");
client.setSSLParameters(p);

// Only call beginHandshake/wrap/unwrap once configuration is done.
client.beginHandshake();
~~~

The code above is **not a standalone file**, because `sslContext` comes from the application's trust configuration. `SSLContext` does not build a truststore automatically from an unknown network certificate, and `setEndpointIdentificationAlgorithm("HTTPS")` **does not replace** choosing the right CA/truststore source.

**Never use "trust-all"** or drop endpoint identification as a quick fix for certificate errors. That enables MITM attacks even when `wrap/unwrap` and AES-GCM work flawlessly.

### 3.2. Client/server mode must be set before the handshake

~~~java
SSLEngine server = serverSslContext.createSSLEngine();
server.setUseClientMode(false);
~~~

An engine without client/server mode set may throw `IllegalStateException` when calling `wrap/unwrap`. Once the handshake starts, never flip modes arbitrarily. Create **one engine per connection**, never sharing a single `SSLEngine` across multiple clients.

`createSSLEngine(host, port)` provides peer host/port for session/certificate/endpoint identification; it **does not open a TCP socket**. Transport remains managed by `SocketChannel` or the application.

## 4. Two kinds of status that must be read together

The result of `wrap`/`unwrap` is `SSLEngineResult`, which provides **two independent status values**:

~~~java
SSLEngineResult result = engine.wrap(appBytes, netBytes);
SSLEngineResult.Status status = result.getStatus();
SSLEngineResult.HandshakeStatus hs = result.getHandshakeStatus();

int inputBytes = result.bytesConsumed();
int outputBytes = result.bytesProduced();
~~~

The snippet above illustrates the API; `engine` and the two `ByteBuffer`s must be set up in a working system.

- **Operation status (`getStatus()`):** did the call process the buffer cleanly, close the engine, or need more capacity/data?
- **Handshake status (`getHandshakeStatus()`):** which **TLS state machine** step does the engine want the application to perform next?
- **`bytesConsumed()` and `bytesProduced()`:** byte counts consumed from source / written to destination; the basis for updating queues/backpressure and detecting progress.

For example, `Status.OK` **does not mean the handshake is finished**. `OK + NEED_UNWRAP` may mean the current record was processed, yet more records must be received from the peer. `OK + NEED_TASK` means crypto/trust work was delegated for the application to execute.

### 4.1. `SSLEngineResult.Status`

| `Status` | Meaning | What to do |
| --- | --- | --- |
| `OK` | Operation completed with no buffer/close condition for this call. | Check handshake status, consumed/produced, and continue accordingly. |
| `BUFFER_UNDERFLOW` | Insufficient source data for the operation (common in `unwrap` with an incomplete TLS record). | Keep unprocessed net bytes, read more from network; check/grow `netIn` if record exceeds buffer capacity. **Do not spin** on the same bytes. |
| `BUFFER_OVERFLOW` | Destination lacks space to hold output. | For `wrap`: flush/grow `netOut`; for `unwrap`: drain/grow `appIn`. Retry once space exists. |
| `CLOSED` | The corresponding side is closed or cannot proceed because the engine closed. | **Still transmit any bytes produced**, handle `close_notify`, close state, and transport properly. |

**Never lump `BUFFER_UNDERFLOW` and `BUFFER_OVERFLOW` into a TLS error**: they are normally **buffer-coordination signals**, not invalid certificates/signatures. Conversely, `SSLException` may indicate a genuine security/protocol failure and must fail closed.

### 4.2. `SSLEngineResult.HandshakeStatus`

| `HandshakeStatus` | Meaning | Next action |
| --- | --- | --- |
| `NEED_WRAP` | Engine needs to emit TLS bytes (handshake/alert/post-handshake). | Call `wrap`, keep/send all produced ciphertext. |
| `NEED_UNWRAP` | Engine needs TLS bytes from the peer. | Run `unwrap` on received bytes; if insufficient, wait for read. |
| `NEED_UNWRAP_AGAIN` | Engine still has internally buffered received data to process. | Call `unwrap` **immediately**, possibly without new network bytes. |
| `NEED_TASK` | Engine is waiting on delegated `Runnable` tasks. | Drain all tasks via `getDelegatedTask()`, run/await completion per threading policy, then resume engine. |
| `FINISHED` | **The `wrap/unwrap` call just completed the handshake.** | Usually observed on the returned **result**; record completion and transition properly to application/transport handling. |
| `NOT_HANDSHAKING` | No handshake is currently in progress. | Can process application data; still handle queue flushing, post-handshake messages, and close protocol when they occur. |

**Special trap:** `FINISHED` is an **event on `SSLEngineResult`**, not a persistent state. `engine.getHandshakeStatus()` normally transitions to `NOT_HANDSHAKING` right after completion. Never write a loop that exits only when `engine.getHandshakeStatus() == FINISHED`: that may never be true.

**`NEED_UNWRAP_AGAIN` is not the same as `BUFFER_UNDERFLOW`**. The former means the engine still holds internally queued handshake data and **may need `unwrap` even when `netIn` has no new bytes**. The latter means input data is insufficient and requires more network bytes or a larger buffer.

### 4.3. Never infer lack of progress from `bytesProduced() == 0`

For example:
- `unwrap` may consume handshake bytes while producing 0 plaintext bytes.
- `getDelegatedTask()` may advance state even with zero bytes flowing through.
- `wrap` may return `Status.OK` and `HandshakeStatus.NEED_UNWRAP`, which does not mean "nothing happened."
- TLS output is meaningful only when combining status, handshake status, buffer positions, and queue state.

When diagnosing deadlocks, log **both statuses + consumed/produced + buffer positions/capacities**, never raw handshake secrets or sensitive payloads.

## 5. State machine model driving the handshake

`beginHandshake()` **does not mean the handshake has finished**. It only starts the process; the application must alternate sending/receiving until both the peer and TLS state meet completion criteria.

Driver-level logical diagram:

~~~text
engine.beginHandshake()
          |
          v
  engine.getHandshakeStatus()
          |
          +-- NEED_TASK ----------> getDelegatedTask().run()
          |                         (or offload & await completion)
          |                                  |
          |                                  v
          |                              Re-check state
          |
          +-- NEED_WRAP ----------> wrap(app buffer or EMPTY, netOut)
          |                         check status, flush/allocate buffer
          |                         deliver TLS bytes in exact order
          |                                  |
          |                                  v
          |                              Re-check state
          |
          +-- NEED_UNWRAP --------> receive more net bytes if needed
          |                         unwrap(netIn, appIn)
          |                         check status, preserve unused bytes
          |                                  |
          |                                  v
          |                              Re-check state
          |
          +-- NEED_UNWRAP_AGAIN --> unwrap(...) even with no new bytes
          |                                  |
          |                                  v
          |                              Re-check state
          |
          +-- FINISHED (result) ---> record handshake completion
          |
          +-- NOT_HANDSHAKING ----> data phase / post-handshake / close
~~~

**This is an orchestration diagram, not standalone production code.** A real event loop must also handle `Status.CLOSED`, `BUFFER_OVERFLOW`, `BUFFER_UNDERFLOW`, EOF, cancel/timeout, `close_notify`, slow tasks, pending ciphertext, and network channel state.

### 5.1. Driver pseudocode distinguishing result statuses

~~~text
onTick(connection):
  if taskFuture is running:
    return, wait for completion; do not call wrap/unwrap as if task finished

  while valid progress remains within CPU budget:
    hs = engine.getHandshakeStatus()

    if hs == NEED_TASK:
      tasks = drain all engine.getDelegatedTask()
      run tasks per policy and await completion
      if offloaded: return, schedule resume when future completes
      continue

    if hs == NEED_WRAP:
      result = engine.wrap(pendingApplicationOrEmpty, netOutWriteMode)
      inspect result.Status and result.HandshakeStatus
      if BUFFER_OVERFLOW: flush/grow netOut; retry when space exists
      if CLOSED: flush bytes/close_notify, update outbound state
      if OK: enqueue ciphertext; register OP_WRITE if not fully flushed
      continue or yield per backpressure

    if hs == NEED_UNWRAP or hs == NEED_UNWRAP_AGAIN:
      netIn.flip()       # WRITE -> READ
      result = engine.unwrap(netIn, appInWriteMode)
      netIn.compact()    # preserve unconsumed ciphertext; back to WRITE
      if BUFFER_UNDERFLOW:
        if buffer too small: grow to reasonable packet size
        wait for OP_READ / new bytes; DO NOT busy-spin
      if BUFFER_OVERFLOW:
        deliver/grow appIn; retry once space exists
      if CLOSED: record close_notify/inbound state
      if OK: process app bytes and handshake status; continue

    if hs == NOT_HANDSHAKING:
      flush any pending ciphertext
      receive/send application data only after policy handshake is verified
      handle post-handshake/close/queued application I/O
      return

    FINISHED is only an event from SSLEngineResult, not the sole condition
~~~

**Additional production nuance:** `NEED_WRAP` can still appear after the application handshake due to KeyUpdate, NewSessionTicket, or closing the connection. Conversely, `NOT_HANDSHAKING` alone does not guarantee all ciphertext has actually reached the peer. Deciding "complete" must consider both engine state and transport queues.

### 5.2. Avoiding CPU-burning loops

Never write:

~~~java
while (engine.getHandshakeStatus()
        == SSLEngineResult.HandshakeStatus.NEED_UNWRAP) {
    engine.unwrap(netIn, appIn); // WRONG if netIn has no new bytes.
}
~~~

When `unwrap` returns `BUFFER_UNDERFLOW`, data is insufficient; calling it again on the exact same unchanged buffer creates a 100% CPU **busy loop**. With a non-blocking `SocketChannel`, you must **wait until the channel is read-ready**, receive more bytes, and then retry.

A sound scheduler distinguishes:
- **Internal progress**: tasks completed, engine state transitioned, bytesConsumed/Produced.
- **Transport progress**: new bytes received or buffer flushed/drained, freeing capacity.
- **No progress**: yield and wait for a new event; never busy-spin on `BUFFER_UNDERFLOW`.

## 6. ByteBuffer: `flip`, `compact`, and unread data

`ByteBuffer` has `capacity`, `position`, and `limit`. `put` writes when the buffer is in **WRITE mode**; `get`/`unwrap` require the source buffer in **READ mode** after calling `flip()`.

### 6.1. Correct pattern for `netIn`

~~~text
ByteBuffer netIn = allocate(...);  // WRITE mode
SocketChannel.read(netIn);         // writes new ciphertext
netIn.flip();                      // READ mode
engine.unwrap(netIn, appIn);       // consumes <= remaining()
netIn.compact();                   // preserves unconsumed ciphertext
// netIn is back in WRITE mode, with room to append on next read
~~~

`compact()` **differs** from `clear()`:
- `clear()` resets writing from the start and **discards old bytes**, which is dangerous if unconsumed TLS bytes remain.
- `compact()` shifts **remaining()** bytes to the front and switches to WRITE mode; partial records are never lost.

### 6.2. Java 17+: small example verifying `flip`/`compact`

File **`ByteBufferModesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

public class ByteBufferModesDemo {
    public static void main(String[] args) {
        ByteBuffer inbound = ByteBuffer.allocate(8);

        inbound.put(new byte[] {1, 2, 3, 4});
        inbound.flip();                  // WRITE -> READ

        byte[] first = new byte[2];
        inbound.get(first);             // consumed 1, 2

        inbound.compact();              // retains 3, 4; to WRITE
        inbound.put(new byte[] {5, 6}); // appends when more bytes arrive
        inbound.flip();                 // to READ

        byte[] rest = new byte[inbound.remaining()];
        inbound.get(rest);

        System.out.println("Consumed: " + Arrays.toString(first));
        System.out.println("Retained and appended: "
                + Arrays.toString(rest));
    }
}
~~~

~~~bash
javac ByteBufferModesDemo.java
java ByteBufferModesDemo
~~~

Verified stdout:

~~~text
Consumed: [1, 2]
Retained and appended: [3, 4, 5, 6]
~~~

**Do not confuse this simple buffer example with a TLS parser.** TLS records require complete headers/payloads and engine state; `ByteBuffer` merely ensures you **do not lose leftover bytes** between I/O operations.

### 6.3. How to write `netOut` and handle partial writes

When `wrap` writes ciphertext into `netOut`, `netOut` is typically in WRITE mode. Before sending:

~~~text
netOut.flip()                  // switch to READ
SocketChannel.write(netOut)    // may send only part of it
if netOut.hasRemaining():
    keep unsent bytes intact; schedule OP_WRITE
else:
    netOut.clear()             // or compact and append next record
~~~

If output was only partially sent, **never clear/overwrite** the buffer and never emit another record on top of unsent data out of order. The TLS record layer requires exact byte ordering; an engine may have multiple outbound records awaiting transport.

In the in-memory demo in section 10, both queues always have ample room, so `peerInbound.put(encrypted)` simulates transferring the **entire** record. This intentionally removes partial writes so the exercise focuses on the state machine. Real NIO must build enqueue + `OP_WRITE` + backpressure policies.

## 7. Responding accurately to `BUFFER_UNDERFLOW` and `BUFFER_OVERFLOW`

### 7.1. `BUFFER_UNDERFLOW` during `unwrap`

Suppose a TLS record is 1200 bytes long, yet TCP has delivered only 80 bytes. The full record cannot be decrypted:

~~~text
netIn holds 80 bytes -> flip -> unwrap
Result.Status = BUFFER_UNDERFLOW
    |
    +-- Do not discard the 80 bytes
    +-- compact preserves the 80 bytes
    +-- wait for more read bytes
    +-- next time append bytes to netIn
    +-- flip -> unwrap again
~~~

If `netIn.capacity()` is smaller than `SSLSession.getPacketBufferSize()` or smaller than the record size the engine needs, the buffer can **never hold enough**: grow it per policy, while capping max size/resources to prevent DoS. `getPacketBufferSize()` is a recommended buffer size that **can change during the session/handshake**.

**Do not immediately treat `BUFFER_UNDERFLOW` as TLS tampering.** It normally means data is arriving in chunks. However, if the transport reports EOF while a record is incomplete, handle the truncated connection properly instead of waiting forever.

### 7.2. `BUFFER_OVERFLOW` during `wrap`

The engine wants to produce a TLS record, yet `netOut` lacks space. How to handle:
1. If pending ciphertext awaits sending, try **draining `netOut`** over the transport.
2. If capacity is still smaller than a record, **grow** the buffer to match `getPacketBufferSize()`.
3. Call `wrap` again once space is available.
4. Never drop plaintext from `appOut` if it **was not yet `bytesConsumed`**.

### 7.3. `BUFFER_OVERFLOW` during `unwrap`

The engine wants to write application plaintext into `appIn`, yet `appIn` is full. How to handle:
1. If authenticated plaintext sits in `appIn`, deliver it to the application consumer when the consumer has capacity.
2. If unable to drain, apply **backpressure** to network reads; do not keep reading unboundedly.
3. If the buffer is too small for an application packet per `getApplicationBufferSize()`, grow reasonably.
4. Retry `unwrap` when space is available, keeping unconsumed input intact.

### 7.4. Summary table to prevent confusion

| Case | What is lacking? | Right action |
| --- | --- | --- |
| `unwrap` -> `BUFFER_UNDERFLOW` | Input **network** TLS bytes insufficient. | Keep `netIn` + read more, grow `netIn` if needed. |
| `unwrap` -> `BUFFER_OVERFLOW` | Destination **application** buffer too small. | Drain/grow `appIn`. |
| `wrap` -> `BUFFER_OVERFLOW` | Destination **network** buffer too small. | Flush/grow `netOut`. |
| `wrap` -> `Status.OK` + `bytesConsumed=0` | May have produced only a handshake record. | Check handshake status + `bytesProduced`. |
| `unwrap` -> `Status.OK` + `bytesProduced=0` | May have processed only handshake/alert. | Do not assume an app message arrived. |
| `NEED_UNWRAP_AGAIN` | Internal handshake data still needs processing. | Call `unwrap` again; no new read needed if engine says so. |

## 8. Delegated tasks: why can `SSLEngine` still stall an event loop?

JDK documentation states that `SSLEngine` methods are designed **not to perform blocking transport I/O**, yet some handshake work can take significant time, such as:

- Checking certificate chains/PKIX or contacting certificate validation services.
- Fetching private keys from tokens/HSMs, signing, or high-latency provider operations.
- Cryptographic computations, trust/key manager lookups, or potentially blocking provider behavior.

The engine may return `HandshakeStatus.NEED_TASK`; the caller must retrieve the `Runnable` instances via `getDelegatedTask()` and run them.

### 8.1. Synchronous approach for learning

~~~java
// Illustrative handler snippet, suitable for a DEMO with no event-loop latency requirements.
Runnable delegated;
while ((delegated = engine.getDelegatedTask()) != null) {
    delegated.run();
}
// After all delegated tasks finish:
// read engine.getHandshakeStatus() and resume wrap/unwrap.
~~~

**This is not best practice for an event loop serving thousands of connections.** `Runnable.run()` can block: if executed on the thread serving all channels, one slow certificate validation stalls every connection.

### 8.2. Production: controlled offloading and resuming the right state

Pseudo-architecture:

~~~text
Event loop:
  engine reports NEED_TASK
      |
      v
  collect delegated tasks
      |
      v
  offload to bounded crypto/handshake executor
      |                     |
      |                     +-> enforce concurrency, timeout, backpressure
      |
  mark connection WAITING_FOR_TASK
  do not spin or overlap wrap/unwrap as if tasks done
      |
  future completion / scheduled event
      |
      v
  check task error, verify engine/session state
  re-register needed interestOps
  resume handshake from engine.getHandshakeStatus()
~~~

In real implementations:
- Tasks must run **completely to finish** before the engine can advance past the stage needing them. Never submit to an executor and immediately call `wrap/unwrap`.
- Use a **bounded executor**; avoid unbounded `new Thread(task).start()` per client on a loaded server.
- Never block the event loop with `future.get()`; use callbacks/queues to post completion back to the **owner event-loop thread**.
- Account for timeouts, connection cancellation, task failures, and races with close. When a connection is already closed or replaced by a new generation, stale completions must not resurrect the engine.
- With some providers, task exceptions may be propagated or cause errors on the next `wrap/unwrap`; log the sanitized cause without printing private keys/handshake secrets.
- **Serialize state orchestration per connection** (one event-loop owner) to prevent concurrent callbacks/tasks from mutating queues/engines out of order.

### 8.3. Do not confuse `NEED_TASK` with `NEED_UNWRAP`

`NEED_TASK` means the engine needs **results of local work**; reading more from the socket will not run delegated tasks. `NEED_UNWRAP` means the engine needs **TLS data from the peer** or has queued data waiting; running a task does not replace network reads.

Only by handling both properly do you avoid deadlocks like "client waits for ServerHello while server has not run its key/cert task yet."

## 9. Boundary between handshake phase and application phase

For the initial handshake:

1. Create `SSLEngine`, configure mode/trust/parameters.
2. Call `beginHandshake()` or let the first `wrap/unwrap` initiate it.
3. Loop `NEED_WRAP/NEED_UNWRAP/NEED_TASK/NEED_UNWRAP_AGAIN` until the handshake finishes per engine/result state.
4. Record the `FINISHED` event if needed, while checking `SSLSession` protocol/cipher and trust/identity decisions per JSSE policy.
5. Once a valid TLS session exists, process application bytes with `wrap`/`unwrap`.

**TLS 1.3 note:** After the initial handshake completes, **NewSessionTicket**, **KeyUpdate**, or post-handshake events can still trigger `wrap/unwrap` and corresponding tasks. Never write logic assuming "once `FINISHED` occurs, from then on only wrap plaintext and ignore handshake status."

`NOT_HANDSHAKING` is the engine state at a point in time; to consider **application data sent to the network**, verify `netOut` has fully flushed; to consider a **request fully received**, rely on application-protocol framing (HTTP, custom length prefix, etc.), not a single `unwrap`.

## 10. Runnable Java 17+ demo: TLS 1.3 between two in-memory `SSLEngine`s

### 10.1. Purpose, limits, and environment

The example uses two `SSLEngine`s: **client** and **server**, each with its own `SSLContext` configuration. Between them are two `ByteBuffer`s simulating **inbound network ciphertext queues**. For each status:
- `NEED_TASK`: runs all delegated tasks **synchronously** in the demo.
- `NEED_WRAP`: calls `wrap(EMPTY, output)` and copies output to the peer's inbound queue.
- `NEED_UNWRAP` / `NEED_UNWRAP_AGAIN`: `flip`, `unwrap`, `compact`, and updates state.
- `NOT_HANDSHAKING` on both ends: demo treats the initial handshake as complete.
- Then the client `wrap`s the `"hello"` message, and the server `unwrap`s to recover plaintext.
- Finally, the client calls `closeOutbound()` and delivers TLS `close_notify` to the server, proving inbound close is received.

**No network sockets are opened** in the example. This is still a **real TLS 1.3 handshake/encryption performed by JSSE** using test certificates and the crypto provider, not a fake simulation of the math. However, it does not test TCP partial-read/write, application backpressure, buffer growth, task cancellation, full-duplex shutdown, or multi-client load — those are analyzed separately.

The program requires:
- JDK 17+ with TLS 1.3 and `TLS_AES_128_GCM_SHA256`.
- A PKCS#12 keystore containing the server private key + certificate for hostname `localhost`.
- A client PKCS#12 truststore trusting the demo certificate.
- `TLS_DEMO_PASS` holding the **test-only** password.

### 10.2. Creating the two test keystores

Run in a **new test directory**; never commit these files. Password `changeit` is for learning only, **never for production**.

~~~bash
# Generate private key + self-signed certificate for localhost (lab).
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1" -validity 2 \
  -storetype PKCS12 -keystore server.p12 \
  -storepass changeit -keypass changeit -noprompt

# Export public certificate for the client to use as a test trust anchor.
keytool -exportcert -rfc -alias localhost -keystore server.p12 \
  -storepass changeit -file server.crt

# Import the test cert into the lab's DEDICATED truststore.
keytool -importcert -alias localhost -file server.crt \
  -keystore trust.p12 -storetype PKCS12 \
  -storepass changeit -noprompt
~~~

Trailing `\` in the example is **Bash** line continuation. On Windows PowerShell/CMD, run each command on **a single complete line** without `\`. Use the same filenames in the Java command below.

**Note:** importing the self-signed certificate you just created into a test truststore is an **intentional trust decision** for the lab. Never trust a certificate from unverified input and import it into a production truststore to "get past PKIX errors." Protect the certificate and `server.p12` private key; delete test artifacts after practicing.

### 10.3. Complete code: `InMemoryEngineDemo.java`

~~~java
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.net.ssl.*;

public class InMemoryEngineDemo {
    private static final ByteBuffer EMPTY = ByteBuffer.allocate(0);

    static SSLContext serverContext(
            String file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = new FileInputStream(file)) {
            store.load(in, password);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, password);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(kmf.getKeyManagers(), null, new SecureRandom());
        return ctx;
    }

    static SSLContext clientContext(
            String file, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = new FileInputStream(file)) {
            store.load(in, password);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
        return ctx;
    }

    static boolean drive(
            SSLEngine engine, ByteBuffer inbound,
            ByteBuffer peerInbound) throws Exception {
        SSLEngineResult.HandshakeStatus hs =
                engine.getHandshakeStatus();
        switch (hs) {
            case NEED_TASK -> {
                Runnable task;
                int count = 0;
                while ((task = engine.getDelegatedTask()) != null) {
                    task.run();
                    count++;
                }
                if (count == 0) {
                    throw new IllegalStateException(
                            "NEED_TASK without task");
                }
                return true;
            }
            case NEED_WRAP -> {
                ByteBuffer output = ByteBuffer.allocate(
                        engine.getSession().getPacketBufferSize() * 2);
                SSLEngineResult result = engine.wrap(EMPTY, output);
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new IllegalStateException("wrap: " + result);
                }
                output.flip();
                if (peerInbound.remaining() < output.remaining()) {
                    throw new IllegalStateException(
                            "Demo transport queue full");
                }
                peerInbound.put(output);
                return result.bytesProduced() > 0
                        || result.getHandshakeStatus() != hs;
            }
            case NEED_UNWRAP, NEED_UNWRAP_AGAIN -> {
                inbound.flip();
                SSLEngineResult result;
                try {
                    ByteBuffer app = ByteBuffer.allocate(
                            engine.getSession()
                                    .getApplicationBufferSize() * 2);
                    result = engine.unwrap(inbound, app);
                } finally {
                    inbound.compact();
                }

                if (result.getStatus()
                        == SSLEngineResult.Status.BUFFER_UNDERFLOW) {
                    return false;
                }
                if (result.getStatus() != SSLEngineResult.Status.OK) {
                    throw new IllegalStateException(
                            "unwrap: " + result);
                }
                return result.bytesConsumed() > 0
                        || result.bytesProduced() > 0
                        || result.getHandshakeStatus() != hs;
            }
            case NOT_HANDSHAKING, FINISHED -> {
                return false;
            }
            default -> throw new IllegalStateException(
                    "Unexpected handshake status");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java InMemoryEngineDemo server.p12 trust.p12");
            return;
        }

        String passText = System.getenv("TLS_DEMO_PASS");
        if (passText == null) {
            throw new IllegalStateException("TLS_DEMO_PASS missing");
        }
        char[] pass = passText.toCharArray();
        try {
            SSLEngine client = clientContext(args[1], pass)
                    .createSSLEngine("localhost", 443);
            client.setUseClientMode(true);

            SSLEngine server = serverContext(args[0], pass)
                    .createSSLEngine();
            server.setUseClientMode(false);

            SSLParameters cp = client.getSSLParameters();
            cp.setProtocols(new String[]{"TLSv1.3"});
            cp.setCipherSuites(
                    new String[]{"TLS_AES_128_GCM_SHA256"});
            cp.setEndpointIdentificationAlgorithm("HTTPS");
            client.setSSLParameters(cp);

            SSLParameters sp = server.getSSLParameters();
            sp.setProtocols(new String[]{"TLSv1.3"});
            sp.setCipherSuites(
                    new String[]{"TLS_AES_128_GCM_SHA256"});
            server.setSSLParameters(sp);

            // Two inbound network buffers in WRITE mode.
            ByteBuffer toServer = ByteBuffer.allocate(1024 * 1024);
            ByteBuffer toClient = ByteBuffer.allocate(1024 * 1024);

            client.beginHandshake();
            server.beginHandshake();

            boolean complete = false;
            for (int n = 0; n < 1000; n++) {
                boolean progress =
                        drive(client, toClient, toServer);
                progress |= drive(server, toServer, toClient);

                if (client.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING
                        && server.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.NOT_HANDSHAKING) {
                    complete = true;
                    break;
                }
                if (!progress) {
                    throw new IllegalStateException(
                            "Handshake stalled");
                }
            }
            if (!complete) {
                throw new IllegalStateException(
                        "Handshake loop limit");
            }

            System.out.println(
                    "Handshake complete: " + complete);
            System.out.println("Protocol: "
                    + client.getSession().getProtocol());
            System.out.println("Cipher suite: "
                    + client.getSession().getCipherSuite());
            System.out.println("Peer certificate present: "
                    + (client.getSession()
                            .getPeerCertificates().length > 0));

            // Client application plaintext -> TLS ciphertext.
            ByteBuffer clear = ByteBuffer.wrap(
                    "hello".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer encrypted = ByteBuffer.allocate(
                    client.getSession().getPacketBufferSize() * 2);
            SSLEngineResult wr = client.wrap(clear, encrypted);
            if (wr.getStatus() != SSLEngineResult.Status.OK
                    || clear.hasRemaining()) {
                throw new IllegalStateException(
                        "Application wrap: " + wr);
            }
            encrypted.flip();

            // Server TLS ciphertext -> authenticated plaintext.
            ByteBuffer received = ByteBuffer.allocate(
                    server.getSession().getApplicationBufferSize() * 2);
            SSLEngineResult ur = server.unwrap(encrypted, received);
            if (ur.getStatus() != SSLEngineResult.Status.OK) {
                throw new IllegalStateException(
                        "Application unwrap: " + ur);
            }
            received.flip();
            System.out.println("Application message: "
                    + StandardCharsets.US_ASCII.decode(received));

            // Illustrates client close_notify -> server only.
            client.closeOutbound();
            ByteBuffer closeRecord = ByteBuffer.allocate(
                    client.getSession().getPacketBufferSize() * 2);
            SSLEngineResult cr = client.wrap(EMPTY, closeRecord);
            if (cr.getStatus() != SSLEngineResult.Status.CLOSED) {
                throw new IllegalStateException(
                        "Close wrap: " + cr);
            }
            closeRecord.flip();
            SSLEngineResult peerClose = server.unwrap(
                    closeRecord,
                    ByteBuffer.allocate(
                            server.getSession()
                                    .getApplicationBufferSize() * 2));

            System.out.println("Peer received close_notify: "
                    + (peerClose.getStatus()
                            == SSLEngineResult.Status.CLOSED
                            && server.isInboundDone()));
        } finally {
            Arrays.fill(pass, '\0');
        }
    }
}
~~~

### 10.4. Compiling and running

Bash (from the directory containing the Java file and both keystores):

~~~bash
export TLS_DEMO_PASS=changeit
javac InMemoryEngineDemo.java
java InMemoryEngineDemo server.p12 trust.p12
unset TLS_DEMO_PASS
~~~

Windows PowerShell:

~~~powershell
$env:TLS_DEMO_PASS = "changeit"
javac InMemoryEngineDemo.java
java InMemoryEngineDemo server.p12 trust.p12
Remove-Item Env:TLS_DEMO_PASS
~~~

Verified output on a JDK supporting TLS 1.3 with test keystores matching the instructions:

~~~text
Handshake complete: true
Protocol: TLSv1.3
Cipher suite: TLS_AES_128_GCM_SHA256
Peer certificate present: true
Application message: hello
Peer received close_notify: true
~~~

**This is verified stdout on the demo environment setup.** If the JVM lacks TLS 1.3/AEAD suite support, the truststore lacks the right certificate, the SAN mismatches `localhost`, or `keytool` failed, the handshake may throw an exception — never lower security just to print `true`.

### 10.5. Explaining tricky points in the code

1. **Client/server identity:** Server builds `SSLContext` with `KeyManagerFactory` from `server.p12`; client builds `SSLContext` with `TrustManagerFactory` from `trust.p12`. Client enables `HTTPS` endpoint identification with peer host `localhost`.
2. **Buffers simulate network queues:** `toServer` is the server's inbound ciphertext; `toClient` is the client's inbound ciphertext. Each queue stays in **WRITE mode** between turns.
3. **`NEED_WRAP`:** `engine.wrap(EMPTY, output)` produces a handshake record even with no application plaintext, then `peerInbound.put(output)` transfers bytes to the other side.
4. **`NEED_UNWRAP`:** `inbound.flip()`, `engine.unwrap(inbound, app)`, `inbound.compact()`; unconsumed bytes stay in the queue after returning to WRITE mode.
5. **`NEED_UNWRAP_AGAIN`:** uses the same `unwrap` branch, even when the engine processes internally buffered handshake bytes.
6. **`NEED_TASK`:** drains and runs tasks until `getDelegatedTask()` returns `null`. **The demo runs synchronously**; production must offload and avoid blocking the event loop.
7. **Handshake complete:** once **both** engines are no longer handshaking after valid `drive` calls, the demo enters the application phase. On real networks, you must also consider ciphertext queues and peer/network state.
8. **Client `wrap` / server `unwrap`:** Client wraps `"hello"`; server recovers plaintext via unwrap. This is a real encrypted record. Plaintext is never sent raw across the `toServer` simulation.
9. **`close_notify`:** `client.closeOutbound()` makes `wrap(EMPTY, ...)` generate the close alert; server `unwrap` sees `Status.CLOSED` and `isInboundDone()`. The demo **only checks one-way `close_notify`**; real apps must also handle the reverse close per protocol and flush all ciphertext before closing transport.
10. **Protecting secrets:** `Arrays.fill(pass, '\0')` wipes only the **temporary char array** created by the demo; `passText` from the environment is an immutable `String` and cannot guarantee erasing all copies in the JVM. Never use `changeit` for real secrets.

### 10.6. What does the demo intentionally NOT support?

The demo runs on large in-memory buffers, so:
- It **throws `IllegalStateException`** if a simulated queue fills or overflows, instead of retrying/resizing like a production transport.
- It does not fragment TLS ciphertext across multiple `SocketChannel.read` calls; hence it does not thoroughly test `BUFFER_UNDERFLOW` on real networks.
- It does not implement `Selector`/`OP_READ`/`OP_WRITE`, overall timeouts, scheduling fairness, or handling thousands of connections.
- It handles only **one simple application record**. Real applications have framing/streaming, multiple records, partial writes, EOF, and backpressure.
- It shows only **client `close_notify` to server**, not completing the full bidirectional close procedure of the engine pair.
- It does not implement mTLS, resumption policies, early-data/0-RTT, or post-handshake monitoring.
- It uses a self-signed test truststore. Never use this model to replace production PKIX/truststores.

Therefore **do not copy this demo straight into a nonblocking production server**. Use the status/buffer/transport sections below to understand what frameworks like Netty handle for you.

## 11. Mapping to `SocketChannel` and `Selector`

In non-blocking NIO, each connection typically has:
- A `SocketChannel` in nonblocking mode, a `SelectionKey`, and an event-loop owner.
- An `SSLEngine` configured for client or server.
- `netIn` holding received ciphertext bytes **not yet unwrapped**.
- `netOut`/queue holding ciphertext bytes **not yet fully flushed**.
- `appIn`/`appOut` or application streams/framing.
- State: handshake in progress, tasks pending, closing/closed, timers, and buffer limits.

### 11.1. Rules for registering interest ops

| Condition | Which event to register? | Why |
| --- | --- | --- |
| `NEED_UNWRAP` and `netIn` lacks bytes | `OP_READ` | Wait for fresh TLS bytes without spinning. |
| `NEED_WRAP`, room in `netOut` | Can run `wrap` right on the event loop | Generates ciphertext/handshake records locally. |
| `netOut` has unsent bytes | `OP_WRITE` | Channel is writable when notified by the event loop; flush incrementally. |
| `NEED_TASK` with offloaded tasks | Await completion, manage interest ops per policy | Do not block the loop or call engine concurrently before tasks finish. |
| `appIn` full, app consumes slowly | Throttle `OP_READ`, apply backpressure | Prevent unbounded RAM growth. |
| Outbound queue too large | Stop/throttle accepting more `appOut` | Avoid producing ciphertext faster than the network can send. |
| TLS closing/`close_notify` pending | Keep `OP_WRITE` until close record is flushed | Closing TCP too early truncates the TLS alert. |

**CPU trap:** Leaving `OP_WRITE` enabled when there is no data to send causes `Selector` to wake up continuously since sockets are usually writable, burning CPU. Enable `OP_WRITE` only when **pending bytes actually exist**.

### 11.2. When the channel is readable

Pattern:

~~~text
n = channel.read(netIn)    # netIn in WRITE mode
if n > 0:
    netIn.flip()
    loop:
       result = engine.unwrap(netIn, appIn)
       handle result Status + HandshakeStatus
       if UNDERFLOW -> break, need more network bytes
       if OVERFLOW -> drain/grow appIn, maybe retry
       if NEED_TASK -> offload tasks, pause
       if no progress -> break to avoid busy-loop
    netIn.compact()        # preserve unconsumed bytes

if n == 0:
    no new bytes: yield, do not treat as EOF

if n == -1:
    network EOF: check if TLS close_notify was received
    handle closeInbound()/truncation per protocol & policy
~~~

This is **algorithmic pseudocode**, omitting full production concurrency/exception details. With `NEED_UNWRAP_AGAIN`, the driver may still need to call `unwrap` even with no new network bytes.

### 11.3. When the channel is writable

Pattern:

~~~text
while netOut/queue has ciphertext:
    count = channel.write(readModeBuffer)
    if count == 0:
        keep pending bytes, schedule OP_WRITE
        break
    if readModeBuffer has remaining:
        keep remainder, schedule OP_WRITE
        break
    else:
        release/recycle sent buffer

when queue is empty:
    clear OP_WRITE interest
    if engine NEED_WRAP: call wrap to emit next record
    if application appOut pending and handshaken: wrap more when capacity allows
~~~

**Never reorder records.** If `wrap` produces ciphertext A then ciphertext B, they must be sent in that exact order, even if A hits a partial write. Never use a buffer currently being read by the network thread for concurrent `wrap` writes.

### 11.4. Bidirectional backpressure

- **Inbound:** App consumes plaintext too slowly -> `appIn` fills -> `unwrap BUFFER_OVERFLOW` -> temporarily throttle TCP reads, while accounting for TLS control/close to prevent deadlocks. Design bounded queues and policy-driven schedulers.
- **Outbound:** Peer or network is slow -> `netOut` fills -> `wrap BUFFER_OVERFLOW` -> stop generating new records and drain via `OP_WRITE`. Never keep calling `wrap` and allocating unbounded buffers.
- **Handshake:** Even with no application data, TLS still needs to send/receive messages. Never block all `NEED_WRAP/NEED_UNWRAP` merely because the app queue is empty.

## 12. Calculating buffer sizes and managing allocation

`SSLSession` provides two key metrics:

~~~java
int packetSize = engine.getSession().getPacketBufferSize();
int appSize = engine.getSession().getApplicationBufferSize();
~~~

- `getPacketBufferSize()`: recommended capacity for a TLS/DTLS packet produced/consumed by the engine.
- `getApplicationBufferSize()`: recommended capacity for one record's application plaintext.
- Sizes can **change across handshakes/sessions**; never hardcode `16_384` bytes assuming it always fits TLS framing and tags.
- Never allocate single-record buffers and keep writing ciphertext unboundedly. Each connection needs memory caps, queue caps, and buffer grow/shrink rules.

### 12.1. Illustrative buffer growth pattern

~~~java
// Illustrative snippet: source is in WRITE mode and retains all written bytes.
static ByteBuffer growWriteBuffer(ByteBuffer old, int requiredCapacity) {
    if (requiredCapacity <= old.capacity()) {
        return old;
    }
    ByteBuffer replacement = ByteBuffer.allocate(requiredCapacity);
    old.flip();
    replacement.put(old);
    return replacement; // WRITE mode, prior bytes preserved.
}
~~~

This is not a complete production-ready method:
- You must **cap capacity** to prevent untrusted peers from causing unbounded memory growth.
- If using direct buffers, manage resource pooling and copy overhead.
- For an output buffer in READ mode with pending bytes, copy `remaining()` rather than mechanically calling `flip()` a second time.
- Appropriate sizing depends on engine and queue state, not just a fixed constant.

### 12.2. `ByteBuffer` can be heap or direct

`ByteBuffer.allocate(...)` creates a heap buffer; `ByteBuffer.allocateDirect(...)` creates a direct buffer suited to certain I/O channels. The choice depends on performance, GC, allocation, providers, and resource limits—**not cryptographic properties**. `SSLEngine` does not require raw heap arrays for all buffers, so avoid assuming `buffer.array()` always works on direct/read-only buffers.

**Never share the same backing memory region for source and destination** in `wrap/unwrap`. The API contract requires non-aliasing input/output in hazardous ways; overlapping buffers can corrupt data or be rejected by the provider.

## 13. Delegated tasks and event-loop threading: designing for high load

Practical rules:

1. **Each connection has one state orchestrator owner.** Let a single event loop decide when to call `wrap`, `unwrap`, pass buffers, and close. Never let two arbitrary callbacks call `wrap` concurrently on the same engine.
2. **`wrap` and `unwrap` can run concurrently at the API level** if the caller guarantees ordering/synchronization and state; however, two concurrent `wrap`s or two concurrent `unwrap`s on the same engine risk reordering. The simplest design serializes all engine operations per connection.
3. **Deferred tasks are not network I/O.** Use a dedicated pool or compute mechanism; never spawn unbounded worker threads.
4. **Task completion must wake the right connection.** Post an event back to the event loop, check the connection is still alive, handle exceptions, and resume engine state.
5. **Never hold locks across potentially blocking tasks.** Design around races with close, timeouts, cancellation, and provider state; avoid deadlocks between the event loop and task workers.
6. **Check active timers.** A peer may send a few bytes and never finish the handshake. Set handshake timeouts, max queued bytes, and max cert chain sizes per framework/policy.
7. **Use fail-closed error handling.** Any unhandled `SSLHandshakeException`, `SSLProtocolException`, certificate trust failure, or buffer logic violation must reject the connection, never fall back to plaintext.
8. **Never leak TLS secrets in diagnostics.** You may log negotiated protocol, cipher suite, connection ID, and generic failure stage; never log raw keys, pre-master/traffic secrets, session ticket secrets, or sensitive application plaintext.

Java SE 17 docs note that delegated tasks can take a long time or even block due to trust managers, key managers, or crypto providers. Therefore **schedule, await completion, and resume engine state** — never blindly run every `Runnable` "just to get it over with" on the Selector thread.

## 14. Closing TLS properly: `closeOutbound`, `closeInbound`, and `close_notify`

TLS has its own **protocol-level closure**, distinct from closing TCP immediately. When the application wants to stop sending:

~~~text
Application decides to close
    |
engine.closeOutbound()
    |
wrap(EMPTY, netOut) -> TLS close_notify record
    |
flush all netOut over transport
    |
peer unwrap(record) -> Status.CLOSED / isInboundDone()
    |
peer may send close_notify in the opposite direction
    |
only after closing/data-protection steps close the underlying channel
~~~

Details:
- `closeOutbound()` tells the engine to produce no further outbound application data. It **does not send** any bytes itself; call `wrap` until outbound TLS closure records are generated and sent.
- `isOutboundDone()` indicates the engine's outbound side is finished; it **does not prove** the final record's ciphertext was fully delivered over TCP.
- `isInboundDone()` after `unwrap` receives `close_notify` indicates the peer closed its TLS send side per protocol. If `SocketChannel` hits EOF before `close_notify`, handle possible **truncation** per security policy; `closeInbound()` may throw `SSLException` to signal an incomplete close.
- A closed `SSLEngine` **cannot be reused** for a new connection; create a fresh engine.
- TLS 1.3 has specific half-close/alert semantics; do not force a "one side closes so both TCP sides instantly cut" model if protocol data/modes still need exchanging.

**The `InMemoryEngineDemo` shows only one-way `close_notify`**, not a full bidirectional shutdown. Real applications must manage outbound/inbound status independently, flush buffers, and enforce close deadlines to avoid hanging indefinitely when a peer is unresponsive.

### 14.1. `Status.CLOSED` can still produce bytes to send

When `wrap` returns `Status.CLOSED`, it may have written a TLS alert/close record into `netOut`. **Do not discard the buffer and drop TCP immediately**: flush the record if the transport is still writable and policy permits. When `unwrap` returns `CLOSED`, check inbound done and protocol control state before releasing the connection.

### 14.2. EOF with `BUFFER_UNDERFLOW` is not a clean close

A peer may lose connectivity mid-TLS-record, leaving `unwrap` returning `BUFFER_UNDERFLOW` followed by transport `read` returning `-1`. Ignoring this and invoking app callbacks as a "normal end" risks accepting truncated or incomplete data. Distinguish **truncation** from a **clean TLS close with `close_notify`** and handle per application protocol rules.

## 15. Common implementation mistakes

| Mistake | Impact | Right approach |
| --- | --- | --- |
| Calling `beginHandshake()` and immediately sending app data | Handshake was never driven. | Run the `wrap/unwrap/NEED_TASK` state machine until complete. |
| Calling `wrap`/`unwrap` and ignoring `SSLEngineResult` | Misses buffer overflow/underflow, handshake status, bytes consumed. | Always handle both statuses and byte counts. |
| Checking only `getStatus() == OK` | `OK` does not mean handshake completed. | Read `getHandshakeStatus`/engine state. |
| Waiting for `engine.getHandshakeStatus()==FINISHED` | `FINISHED` usually appears only on the returned result. | Handle `result.getHandshakeStatus()==FINISHED` and `NOT_HANDSHAKING` in context. |
| Not handling `NEED_UNWRAP_AGAIN` | Handshake can stall on matching providers/TLS states. | Allow another `unwrap` without waiting for new read bytes. |
| Calling `unwrap` repeatedly on partial input | Busy loop on `BUFFER_UNDERFLOW`. | Retain bytes and wait for `OP_READ`. |
| Using `netIn.clear()` after `unwrap` | Discards unprocessed TLS record bytes. | `flip` before `unwrap`, `compact` after `unwrap`. |
| Calling `netOut.clear()` after `wrap` when TCP wrote partially | Drops ciphertext or scrambles record order. | Keep remaining bytes, flush via `OP_WRITE`. |
| Handling `BUFFER_OVERFLOW` by dropping plaintext | Can lose app data and corrupt record stream. | Drain/grow destination, retry; track `bytesConsumed`. |
| Running delegated tasks on the Selector thread | Slow crypto/trust tasks block all connections. | Offload with bounds, post completion back to event loop. |
| Submitting task and immediately calling `wrap/unwrap` | Engine lacks task result; risks stalls/races. | Wait for tasks to finish and resume the right state. |
| Sharing one `SSLEngine` across connections | Session/state/ciphers/queues mix unsafely. | One engine per TLS connection. |
| Omitting `setUseClientMode` | Engine may throw `IllegalStateException`. | Set mode before handshake. |
| Disabling hostname verification to "fix PKIX" | Can accept wrong-identity servers. | Fix truststore and endpoint identity. |
| Confusing `SSLEngine` with `SSLSocket` auto-I/O | Zero bytes ever hit the socket. | Move ciphertext in/out of `SocketChannel` yourself. |
| Assuming one TCP read delivers a whole record | TCP is a stream; partial/multiple records happen. | Retain `netIn` and process `unwrap` results. |
| Leaving `OP_WRITE` always enabled | Busy loop when writable with nothing to send. | Register `OP_WRITE` only when ciphertext is pending. |
| Closing TCP immediately after `closeOutbound()` | `close_notify` never generated/sent; causes truncation. | `wrap` TLS close records, flush, then close cleanly. |
| Debugging raw application/traffic secrets | Can leak data/keys and sensitive metadata. | Log minimal status/metadata; protect debug logs. |

## 16. Diagnosing errors and testing the state machine

### 16.1. Exceptions do not replace statuses

| Signal | Category | Explanation |
| --- | --- | --- |
| `BUFFER_UNDERFLOW` / `BUFFER_OVERFLOW` | `SSLEngineResult.Status` | Buffer condition, **usually not a security exception**. |
| `NEED_TASK` / `NEED_WRAP` / `NEED_UNWRAP` | `HandshakeStatus` | Engine requests the next orchestration step. |
| `SSLHandshakeException` | Exception | Handshake failed (e.g., chain/trust, hostname, protocol/ciphers, key material). |
| `SSLProtocolException` | Exception | TLS/DTLS protocol error; fail closed and diagnose context. |
| `SSLException` | Base exception | Engine cannot process TLS data/connection; may include close/truncation. |
| `IllegalStateException` | Java or app-defined exception | E.g., client/server mode unset; demo also uses it for tiny/stalled queues. |
| `SocketChannel.read() == -1` | Transport EOF | Network closed; **not `close_notify`**. |

Never catch `Exception` broadly and try calling `wrap` endlessly or falling back to plaintext. If certificate validation fails, inspect truststore/PKIX/SAN and algorithms—never build a trust-all manager.

### 16.2. Minimum test suite for an NIO driver

| Test | Setup | Expectation |
| --- | --- | --- |
| Normal TLS 1.3 handshake | Valid client/server trust | Completes, matching session protocol/cipher, bidirectional data works. |
| Untrusted certificate | Different truststore / missing issuer | Handshake fails; no plaintext app data delivered. |
| Wrong hostname | Cert has SAN `localhost` only, engine created with another host | Client endpoint identification fails. |
| Split record across 2–3 TCP reads | Send header/partial record then remainder | `BUFFER_UNDERFLOW`, retains bytes, then `unwrap` succeeds. |
| One read holds multiple TLS records | Concatenate ciphertext records | Driver loops `unwrap` and preserves position without losing records. |
| Small `netOut` | Destination smaller than packet | `BUFFER_OVERFLOW`, flushes/grows then retries. |
| Small `appIn` | Destination smaller than plaintext | `BUFFER_OVERFLOW`, drains/grows `appIn`. |
| Slow delegated task | Trust manager/provider simulates controlled delay | Other event-loop work runs; task completion resumes right connection. |
| `NEED_UNWRAP_AGAIN` | Provider/state returns that status | Driver keeps calling `unwrap` instead of wrongly waiting for a read. |
| TCP partial write | `Channel.write` sends only a few bytes | Remaining ciphertext stays ordered; `OP_WRITE` flushes incrementally. |
| Event loop with empty `netOut` | Socket writable | `OP_WRITE` does not spin. |
| Clean TLS close | Both sides exchange `close_notify` | Both inbound/outbound done per policy; transport closes only after flush. |
| Abrupt TCP EOF | Close without sending `close_notify` | Distinguishes truncation/`closeInbound` error from clean close. |
| Concurrent close + delegated task | Close while task runs | Completion neither revives connection nor leaks buffers. |
| Stalled handshake | Peer sends half a record then goes silent | Timeouts and memory caps trigger; no infinite busy-spin. |
| TLS 1.3 post-handshake | NewSessionTicket/KeyUpdate | Driver keeps processing control messages even after handshake completed. |

Do not assert tests against fixed exception message strings of one provider; assert **status types, failure stage, received data, and fail-closed behavior**. Different providers can differ in delegated task counts, wrap/unwrap iterations, output sizes, or status sequences — never hardcode that a handshake takes exactly N rounds.

### 16.3. Controlled status logging

Example logging fields:
- Connection/correlation ID, client/server role, JSSE provider or JDK build within policy.
- `SSLEngineResult.Status`, `HandshakeStatus`, `bytesConsumed`, `bytesProduced`.
- `netIn.position/limit/capacity`, `netOut.remaining`, count of pending tasks/bytes.
- Protocol and cipher suite **after** handshake.
- `SSLException` class, stage (handshake, read, write, close), normalized exception category.

Never log private keys, TLS traffic secrets, session tickets, client credentials, raw record bytes, or sensitive decrypted plaintext; use JSSE debug flags in controlled labs, never enabled indiscriminately in production.

## 17. Knowledge self-check

**Q1.** `SSLEngine.wrap(app, net)` returns `OK` with `bytesConsumed=0` yet `bytesProduced>0`. Is the API buggy?

**Answer:** No. During handshakes or TLS closure, the engine can emit TLS records without consuming any application plaintext.

**Q2.** `unwrap` returns `BUFFER_UNDERFLOW` after receiving just 12 bytes. Should we call `unwrap` 10,000 more times to be sure?

**Answer:** No. Preserve unprocessed bytes via `compact`, wait for more network data or grow `netIn` if too small, then retry; avoid busy loops.

**Q3.** `unwrap` returns `BUFFER_OVERFLOW`; should you grow `netIn` or `appIn`?

**Answer:** **`appIn`** (or drain authenticated output plaintext), because the **destination** of `unwrap` lacks space. `BUFFER_UNDERFLOW` is what relates to insufficient `netIn` input.

**Q4.** If `wrap` returns `BUFFER_OVERFLOW`, what is the right action?

**Answer:** Flush/grow the outbound network buffer `netOut`, then retry when space exists. Never discard plaintext not yet counted in `bytesConsumed`.

**Q5.** Why isn't `FINISHED` the sole exit condition when looping over `engine.getHandshakeStatus()`?

**Answer:** `FINISHED` is primarily an event on `SSLEngineResult` when `wrap/unwrap` just ended the handshake; the engine itself has usually already transitioned to `NOT_HANDSHAKING`.

**Q6.** Do `NEED_UNWRAP_AGAIN` and `BUFFER_UNDERFLOW` require the same action?

**Answer:** No. `NEED_UNWRAP_AGAIN` asks to call `unwrap` again on internally buffered TLS data, possibly needing no new network bytes; `BUFFER_UNDERFLOW` means insufficient input data requiring waiting for more bytes.

**Q7.** `NEED_TASK` appears; can you submit tasks to an executor and immediately keep calling `wrap` before the future completes?

**Answer:** No. The engine needs the **completed results** of the tasks; wait, wake up, and resume state via the connection owner.

**Q8.** `SocketChannel.write(netOut)` returns fewer bytes than `netOut.remaining()` before the call. Can you clear `netOut`?

**Answer:** No. Keep the unsent bytes and continue `OP_WRITE`; clearing early loses ciphertext and breaks TLS record ordering.

**Q9.** A TLS client uses `createSSLEngine("bank.example", 443)` without enabling `setEndpointIdentificationAlgorithm("HTTPS")`. Can we assume the hostname is always checked?

**Answer:** No. With a raw engine you must configure the appropriate endpoint identification; peer host/port hints alone do not automatically equal full hostname verification.

**Q10.** When a client calls `closeOutbound()`, can it close the TCP socket immediately?

**Answer:** No. Continue calling `wrap` to produce `close_notify`, flush all ciphertext, handle inbound close policy, and only then close the transport.

**Q11.** After a TLS 1.3 handshake, can `SSLEngine` still return `NEED_WRAP`?

**Answer:** Yes. Post-handshake messages such as NewSessionTicket/KeyUpdate and `close_notify` can require further `wrap/unwrap` calls. The driver must keep following state rather than treating TLS as "immutable."

**Q12.** Why can't the in-memory demo be dropped straight into a production NIO server?

**Answer:** The demo assumes large queues and intact byte delivery, runs tasks synchronously, and omits full-duplex close, buffer growth, partial I/O, backpressure, `Selector` scheduling, and races/timeouts. All of those are responsibilities of a real transport driver.

## 18. References

- [Java SE 17 — SSLEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngine.html): `wrap/unwrap` contract, transport-independent processing, buffer semantics, delegated tasks, close, and concurrency.
- [Java SE 17 — SSLEngineResult](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.html): `Status`, `HandshakeStatus`, `bytesConsumed()`, and `bytesProduced()`.
- [Java SE 17 — SSLEngineResult.HandshakeStatus](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): `NEED_WRAP`, `NEED_UNWRAP`, `NEED_UNWRAP_AGAIN`, `NEED_TASK`, `FINISHED`, and `NOT_HANDSHAKING`.
- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `SSLEngine` guide, buffer overflow/underflow, delegated tasks, nonblocking I/O, and TLS handshake.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): creating `SSLEngine` from key/trust managers.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): protocol/cipher suites and endpoint identification.
- [Java SE 17 — SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getPacketBufferSize()`, `getApplicationBufferSize()`, session metadata.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `compact`, `position`, `limit`, and `remaining`.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) and [SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): event loop `OP_READ`/`OP_WRITE`.
- [Oracle JDK 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): PKCS#12 keystores and test certificates.