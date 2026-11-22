# Request IDs, Responses, and Duplicate Message Detection on TCP Retries

## Lesson Objectives

When communicating over TCP, an application typically sends a **request**, waits for a **response**, and may **retry** if a timeout occurs or the connection drops. The problem is: **not receiving a response does not mean the server has not processed the request**. If the same command such as “add 10 points”, “create order”, or “process payment” is executed twice, the consequences can be very different from resending a data-read request.

After this lesson, you can:

1. Attach a **`requestId`** to each logical operation; use **`responseTo`** in the response to know which request a reply belongs to, even when multiple requests are in flight.
2. Distinguish **TCP retransmission** of bytes within a single connection from an **application retry** that resends a logical message, possibly over a new connection.
3. Identify duplicate messages using **request ID + caller scope + operation content**, while safely handling in-flight requests, completed requests, and cases where an ID is reused for a different payload.
4. Understand the limits of in-memory caches, timeouts, retries, caching, transactions, and “exactly-once” promises; choose how to protect **business effects** according to requirements.
5. Run a Java 17+ example illustrating a command resent over TCP that is applied only once, and an example correlating responses with their corresponding requests.

The scope of this lesson focuses on **application messages sent over TCP sockets**. HTTP mechanisms such as `Idempotency-Key` can be built on similar principles, but every concrete contract must be agreed upon by both server and client.

## 1. First: TCP Does Not Provide a Business “Request ID”

TCP delivers an **ordered byte stream** to the application, rather than built-in request/response objects. One call to `OutputStream.write(...)` does **not** reliably correspond to one `InputStream.read(...)` on the other side. Therefore, the application needs two layers of convention:

- **Framing:** knowing from which byte to which byte constitutes **one message**, such as a length prefix, delimiter, or standard protocol parser.
- **Message envelope:** after extracting a message, reading fields such as `type`, `requestId`, `responseTo`, `operation`, `payload`, and `status`.

Example of a custom protocol:

```json
{
  "type": "REQUEST",
  "requestId": "req-7f2a",
  "operation": "ADD_CREDIT",
  "payload": {"amount": 10}
}
```

The response corresponding to that request:

```json
{
  "type": "RESPONSE",
  "responseTo": "req-7f2a",
  "status": "OK",
  "result": {"balance": 110}
}
```

These JSON snippets illustrate **message shape**, not a standard that Java `Socket` understands on its own. To exchange multiple JSON messages over TCP, framing is required, such as **a 4-byte length prefix + the exact number of UTF-8 bytes** for each JSON message. Simply concatenating JSON strings and calling `read()` once is not enough to separate messages reliably.

`requestId` is usually **generated once by the client for a single logical operation**. Every retry of **that same operation** must **reuse the same `requestId` and the same semantic content**. When the user actually performs a new operation, generate a **new `requestId`**.

A response may also include `responseId` if each reply message needs independent identification, but `responseTo` remains the key field to answer “which request is this the result of?”. In a protocol with only one in-flight request per connection, ordering can also help with pairing; however, explicit IDs support retries, logging, and multiple concurrent in-flight requests much better.

### Easily Confused Identifiers

| Field | Meaning | Used to prevent duplicate processing? |
|---|---|---|
| `requestId` | Identifies **a single logical intent/operation** of the client | **Yes, potentially**, when the server has a mechanism to store state by ID |
| `responseTo` / correlation ID | Indicates which request the response answers | Used for **correlation**; by itself it does not prevent duplicate side effects |
| `responseId` (if present) | Independent identifier of the response/message | Can detect **duplicate responses**, does not replace request deduplication |
| TCP sequence number | Numbers bytes at the TCP layer for that specific connection | **Not** a business request ID; does not persist across a new connection |
| Trace ID / span ID | Tracks an execution flow in logs/tracing | **Not** an idempotency key by default |
| `Idempotency-Key` in HTTP | A client-supplied key per the API contract | Only works if the server **implements** idempotency/deduplication logic |

## 2. Why Must Clients Retry While Still Risking Duplicates?

Consider the command `ADD_CREDIT(amount=10)` with `requestId=req-001`.

```text
Client                              Server
  │  REQUEST(req-001, ADD 10)          │
  ├───────────────────────────────────►│  Process, balance +10
  │                                    │  Save result req-001 = OK
  │           RESPONSE(req-001, OK)    │
  │   ◄────────────── X ───────────────┤  Client does not receive/see response
  │                                    │
  │   Timeout / connection lost        │
  │  RETRY(req-001, ADD 10)            │
  ├───────────────────────────────────►│  Sees req-001 already processed
  │                                    │  Does not add 10 again
  │      RESPONSE(req-001, OK)         │
  │ ◄──────────────────────────────────┤  Returns the saved result
```

The `X` mark means the result may fail to arrive or fail to be recorded by the client application. There are at least three possibilities after a client experiences a timeout:

- **The request never reached the server:** the retry may be the first time the server sees the request.
- **The request arrived and is still being processed:** the retry may arrive while the previous request is **not yet finished**.
- **The request succeeded, but the response did not reach the client:** the retry may ask for **the same business effect a second time**.

The client only observes “outcome unknown” and cannot deduce which case occurred from a timeout alone. Therefore, for non-idempotent operations such as adding money/points, **safe automatic retries require server-side support**.

**Distinguishing from TCP retransmission:** TCP can retransmit lost segments within *the same connection* and reconstruct the ordered byte stream for the application. Segment retransmission at the TCP layer normally does not cause the application program to receive two copies of the bytes as two requests. But when the application **resends the entire request itself**, especially over a new TCP connection, the server can receive **two valid, separate requests**. TCP does not tie those two requests together as “the same execution”.

Nor can `write()`, `flush()`, or a TCP ACK be treated as confirmation of **business logic**. They do not prove that the server wrote the transaction to the database, committed it, or returned a proper response.

## 3. Request ID, Response Correlation, and Retry Rules

### 3.1. Generate the ID Once Before the Retry Loop

In Java 17, a common way to obtain an ID unlikely to collide by chance is `UUID.randomUUID()`:

```java
// Illustrative snippet, placed inside a method that performs a logical operation.
String requestId = java.util.UUID.randomUUID().toString();
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    // encodeAndSend(requestId, sameOperationAndPayload);
    // Retry only according to the protocol's policy.
}
```

`maxAttempts` and `encodeAndSend` in this snippet are hypothetical application components; it is **not a standalone program**. The key point is that **`requestId` is generated OUTSIDE the retry loop**. Generating a new ID on every iteration prevents the server from recognizing that the attempts belong to the same operation.

UUID is one option, not a requirement. For another protocol, you can use random IDs following an internal standard or a properly controlled counter. Enforce length/format limits and handle collisions; **an ID is not a secret or an authorization credential**.

### 3.2. Responses Must Carry an ID to Match the Right Request

The client can maintain a table of pending requests:

```text
pending["req-A"] = future/getInventory
pending["req-B"] = future/createOrder

RESPONSE(responseTo="req-B", result=OK)
    -> completes pending["req-B"]
RESPONSE(responseTo="req-A", result=3 items)
    -> completes pending["req-A"]
```

If the protocol allows concurrent processing, responses may arrive **out of the order in which requests were sent**, even though bytes in each direction of *one* TCP connection are still delivered in order. This is due to server processing, queuing, or how the protocol multiplexes streams, not TCP reordering bytes on its own.

The client must clearly define what happens if a response arrives whose `responseTo` does not exist in `pending`: it may have already timed out/been removed, it may be a duplicate reply, or it may be an unknown ID. You should not blindly apply that response to the most recent request. Every pending request needs a deadline and cleanup to avoid memory leaks.

### 3.3. One Intent, Multiple Attempts; New Intent, New ID

Two operations with identical payloads are **not automatically a duplicate operation**. A user might want to buy two identical items twice. Do not use **payload content alone** as the deduplication key.

Conversely, if a client retries the same `requestId` but changes the amount, target account, method, or business content, the server must treat that as a **conflict error**, not as a new request. A reused ID must represent an immutable intent.

## 4. How Does the Server Detect Duplicates?

A straightforward design is to store:

```text
(scope, requestId) -> {
    payloadFingerprint,
    state,
    originalResponse,
    createdAt,
    expiresAt
}
```

`scope` is the identification scope, for example `tenantId + authenticatedPrincipal + operationType`; its exact definition is set by the API contract. Avoid using `requestId` as a system-wide global key without tenant/user: identical IDs from two independent principals must not interfere with each other.

`payloadFingerprint` is a fingerprint of the **semantic content that must remain immutable**: method/operation, target resource, amount, currency, receiver, or fields that produce side effects. With JSON, hashing the raw JSON string may treat two equivalent documents with different whitespace or key order as different; if semantic recognition is desired, explicit **canonicalization** and a consistent server-side policy are required. Hashing does not replace authentication or authorization checks.

Decision table:

| State in the appropriate scope | New payload | Correct handling |
|---|---|---|
| No `requestId` yet | Valid | Register the ID and execute the request for the first time |
| `IN_PROGRESS` | Same fingerprint | **Do not run the side effect a second time in parallel**; wait for the result, return an in-progress status, or let the client query later |
| `COMPLETED` | Same fingerprint | **Return the saved result** without executing the business logic again |
| Same `requestId` exists | Different fingerprint | Report `CONFLICT`; do not silently overwrite or apply as a new command |
| No ID yet, but payload matches an old request | Same content | Treat as a **new request**, unless business rules have their own uniqueness constraint |
| Expired ID removed from dedup store | Even with same payload | May be processed again; the retention window must be documented |

Distinguish three kinds of “duplicates”:

1. **Duplicate request:** the same intent sent multiple times. Must be deduplicated **before the side effect** or handled with idempotent logic inside a transaction.
2. **Duplicate response:** the same response observed multiple times; the client matches `responseTo` and pending/completed state to avoid triggering callbacks or updating the UI twice.
3. **Two messages with the same content but different `requestId`s:** may be two valid intents. Only a business rule such as a unique order number determines whether they are truly business duplicates.

### Should a `DUPLICATE` Label Be Returned?

If the API contract requires that **a retry receives the same original result**, the server should store and replay the original response (for example `OK, balance=110`). You can record “replayed=true” in logs/metrics or metadata depending on the protocol, but you should not turn a successful response into a `DUPLICATE` error that misleads the client into thinking the operation failed. If a `requestId` is reused with different content, that is a **conflict**, and a clear error should be returned (in HTTP, `409 Conflict` can be used per the service contract).

## 5. State and Race Conditions When Two Copies Arrive Simultaneously

An in-memory check like `if (!map.containsKey(id)) { apply(); map.put(id, result); }` is **not safe across multiple threads**. Two threads can both observe “ID not present” and both apply the effect.

State model:

```text
UNKNOWN ── authorize + unique registration ──► IN_PROGRESS
                                                   │
                                           business processing
                                                   │
                                     succeed + save response
                                                   ▼
                                               COMPLETED
                                               (replay result)

Same ID + different payload in any state -> CONFLICT
Same ID + same payload while IN_PROGRESS -> WAIT / IN_PROGRESS response
Same ID + same payload when COMPLETED    -> REPLAY original response
```

A real server workflow should have a **unique lock** or an atomic entry-creation mechanism keyed by `(scope, requestId)` before running business logic. Do not rely solely on check-then-act.

A database transaction can record “`requestId` processed” **in the same transaction as the side effect** if they reside in **the same DBMS and transaction boundary**. Conceptual example:

```text
BEGIN TRANSACTION
  check/register (scope, requestId) with UNIQUE constraint
  if ID already exists:
      lock/read record, compare fingerprint, return committed result
  if ID is new:
      update balance in the same transaction
      save response result and COMPLETED status
COMMIT
```

This is **pseudocode illustrating ordering and atomic boundaries**, not SQL you can copy and run verbatim. Under real concurrency, you need locking rules, isolation levels, wait/retry on unique constraint collisions, and a way to avoid returning uncommitted results. Never perform the side effect first and **only then** write the ID to a cache in another transaction: a crash between the two steps means a retry will apply the effect a second time.

If the side effect lives **outside** that database (calling another payment service, sending email, publishing a message, etc.), a local transaction alone does not make the remote side effect exactly-once. You need a downstream idempotency contract, a transactional outbox/inbox, business locks, reconciliation, or an appropriate compensation design.

### Crash Windows and Guarantees

| Failure point | What might the server have done? | Consequence if stored only in RAM |
|---|---|---|
| Before receiving the full message | Not processed yet | Client can retry |
| Processing, not yet committed | May roll back or depend on external state | Cannot be inferred from client timeout |
| Business effect committed, response not sent | Side effect has occurred | Restart loses cache → retry may execute again |
| Response sent, client did not record it | Side effect has occurred | Client still retries; server needs to replay response |
| Both effect and dedup record saved in same transaction | Durable result or both rolled back together | Retrying the same ID can be safe **within the guaranteed scope and retention window** |

Do not promise “exactly-once delivery” for a distributed system solely because of `requestId`. What can be designed is **non-repetition of the business effect** for a registered key, within a time window, and with side effects backed by appropriate atomic/idempotent mechanisms. **Message arrival** and **business effect execution** are two concepts that must be distinguished.

## 6. Java 17+: Runnable TCP Retry and Deduplication Example

This example uses **two TCP socket endpoints on loopback**. One server handles four requests across **four separate connections**, keeping the deduplication table in a `HashMap` to focus on the core concept. The assumed operation is `ADD amount` starting from an initial balance of 0:

- First request `req-001, ADD 10`: the server executes it, but the client **intentionally discards the received result** to simulate an application failing to record the reply.
- Retry with **the same `requestId` and same payload**: the server replays the stored response and **does not add 10 again**.
- Same ID but changing amount to 20: receives `CONFLICT`.
- New request `req-002, ADD 5`: applied as a new operation.

**Simulation note:** the example intentionally **hides** the first response at the application layer; it does not create real packet loss on the network. The output accurately illustrates the “client does not know the previous reply” scenario, while the server-side caching mechanism is what to observe.

To establish clear message boundaries, both sides use `DataOutputStream.writeUTF(...)`/`DataInputStream.readUTF(...)` for the two text fields, followed by `writeInt(...)`/`readInt(...)` for the amount. `writeUTF` uses Java's **modified UTF-8 with a 2-byte length prefix**, not standard headerless UTF-8; use it only when both sides agree on this exact protocol.

**File `RetryDedupTcpDemo.java`:**

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RetryDedupTcpDemo {
    private static final int REQUEST_COUNT = 4;

    private record Cached(String fingerprint, String response) {}
    private record Stats(int applied, int balance) {}

    private static String send(InetAddress host, int port,
                               String id, String operation, int amount)
            throws IOException {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 3000);
            socket.setSoTimeout(3000);
            DataOutputStream output = new DataOutputStream(socket.getOutputStream());
            DataInputStream input = new DataInputStream(socket.getInputStream());
            output.writeUTF(id);
            output.writeUTF(operation);
            output.writeInt(amount);
            output.flush();
            return input.readUTF();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(3000);
            int port = listener.getLocalPort();

            Future<Stats> serverResult = executor.submit(() -> {
                Map<String, Cached> completed = new HashMap<>();
                int applied = 0;
                int balance = 0;

                for (int i = 0; i < REQUEST_COUNT; i++) {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        DataInputStream input =
                                new DataInputStream(peer.getInputStream());
                        DataOutputStream output =
                                new DataOutputStream(peer.getOutputStream());

                        String id = input.readUTF();
                        String operation = input.readUTF();
                        int amount = input.readInt();
                        String fingerprint = operation + ":" + amount;
                        Cached prior = completed.get(id);
                        String response;

                        if (id.isBlank() || id.length() > 80) {
                            response = id + "|INVALID_ID";
                        } else if (prior != null) {
                            response = prior.fingerprint().equals(fingerprint)
                                    ? prior.response() : id + "|CONFLICT";
                        } else if (!operation.equals("ADD")
                                || amount < 1 || amount > 1000) {
                            response = id + "|INVALID";
                        } else {
                            balance += amount;
                            applied++;
                            response = id + "|OK|" + balance;
                            completed.put(id, new Cached(fingerprint, response));
                        }
                        output.writeUTF(response);
                        output.flush();
                    }
                }
                return new Stats(applied, balance);
            });

            send(loopback, port, "req-001", "ADD", 10); // Ignore reply on purpose.
            System.out.println("Initial reply: hidden by simulation");
            System.out.println("Retry reply: "
                    + send(loopback, port, "req-001", "ADD", 10));
            System.out.println("Mismatched payload: "
                    + send(loopback, port, "req-001", "ADD", 20));
            System.out.println("New request: "
                    + send(loopback, port, "req-002", "ADD", 5));

            Stats stats = serverResult.get(5, TimeUnit.SECONDS);
            System.out.println("Applied requests: " + stats.applied());
            System.out.println("Final balance: " + stats.balance());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 RetryDedupTcpDemo.java
java RetryDedupTcpDemo
```

**Verified stdout when running the program:**

```text
Initial reply: hidden by simulation
Retry reply: req-001|OK|10
Mismatched payload: req-001|CONFLICT
New request: req-002|OK|15
Applied requests: 2
Final balance: 15
```

Explanation:

1. `listener.bind(..., 0)` asks the OS to assign an **ephemeral port**; since server and client run in the same program, no manual port entry is needed. `InetAddress.getLoopbackAddress()` restricts traffic to the local machine.
2. Each `send(...)` call creates **a new TCP connection**, encodes a request according to the fixed format, and reads one response with `readUTF()`.
3. The server accepts connections **sequentially on a single thread**. This keeps the demo easy to follow, but **does not handle multi-threaded race conditions**; in production, atomic key registration and durable state storage are required.
4. `fingerprint = operation + ":" + amount` is only a simplified representation for a protocol with two simple fields. Do not use this string concatenation as a canonical fingerprint for complex JSON/business payloads or multi-tenant systems.
5. The first time `req-001` is processed: `balance=10`, `applied=1`, and the cache stores `req-001|OK|10`.
6. The retry keeps the same ID/payload, so the server retrieves **the exact old response** from the cache. The balance does not change.
7. Reusing `req-001` with `ADD 20` is rejected with `CONFLICT`. This is a **violation of the request ID contract**, not a new operation.
8. `req-002` is a new intent, bringing the balance to 15. Two business effects occurred, even though the server received four messages.

**Intentional limitations of the example:** the `HashMap` lives only in the JVM, uses a single thread, has no authentication, no durable storage, no real deadlines/retention, no transactions, and no automatic retry policy. A restart loses the cache; another client could spoof an ID if the protocol lacks authentication. This code **must not be used as-is for real money transactions**. It demonstrates the principle: the server must understand **application request IDs** rather than looking only at TCP addresses or byte sequences.

## 7. Java 17+: Correlating Responses by `responseTo` and Detecting Duplicate Responses

The server may return responses out of request-submission order if the protocol/application allows multiple in-flight requests. A `pending` table maps each request ID to its corresponding work; when a response arrives, look it up by `responseTo`.

The following example simulates three responses arriving at the application in the order B, A, B; the second B response is a duplicate message. **This is an in-memory client state-management example and does not open sockets**; TCP framing and I/O were demonstrated in the previous example.

**File `ResponseCorrelationDemo.java`:**

```java
import java.util.HashMap;
import java.util.Map;

public class ResponseCorrelationDemo {
    private record Response(String responseTo, String result) {}

    public static void main(String[] args) {
        Map<String, String> pending = new HashMap<>();
        pending.put("req-A", "Inventory lookup");
        pending.put("req-B", "Create order");

        Response[] incoming = {
                new Response("req-B", "OK"),
                new Response("req-A", "3 items"),
                new Response("req-B", "OK")
        };

        for (Response response : incoming) {
            String operation = pending.remove(response.responseTo());
            if (operation == null) {
                System.out.println("Unmatched/duplicate: "
                        + response.responseTo());
            } else {
                System.out.println(operation + " <- " + response.result());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 ResponseCorrelationDemo.java
java ResponseCorrelationDemo
```

**Verified stdout:**

```text
Create order <- OK
Inventory lookup <- 3 items
Unmatched/duplicate: req-B
```

What the program demonstrates:

- A response carrying `responseTo=req-B` can complete task B before A finishes.
- Once `req-B` has been removed from `pending`, another reply carrying the same ID **must not be applied to request A or trigger UI effects a second time**.
- The code cannot tell for sure whether the second response is a duplicate or an invalid message, so the log says `Unmatched/duplicate`. In a real system, you distinguish these cases by keeping a TTL-bounded set of completed IDs, checking the sender, request state, and protocol contract.
- This is **client-side response deduplication**, which does not replace **server-side request deduplication**. Ignoring a duplicate reply does not stop the server from adding money twice if the request was executed twice.

## 8. Designing Safe Retries and ID Retention Windows

### 8.1. Client-Side Retry Policy

A practical policy typically includes:

1. **Fix** the `requestId` and payload of *the same intent* before the first send.
2. Only retry **potentially transient** failures according to the service contract (timeouts, lost connections, transient rate-limit errors, or retryable status codes).
3. Set a **connect timeout**, **read/request deadline**, **overall deadline**, and maximum attempt count; after the deadline, surface an “outcome unknown” state if the request may have been processed.
4. Use **exponential backoff with jitter** to avoid synchronized client retry storms. Respect `Retry-After` when provided by the service.
5. Once a **successful response for the same `requestId`** is received, stop retrying and return that result. If the response reports `IN_PROGRESS`, wait or query status instead of generating another `requestId`.
6. For non-idempotent operations, only retry automatically when the server has a sufficiently strong **deduplication contract**. Otherwise, verify the business state before deciding to retry.

An **illustrative** backoff schedule, not a mandatory configuration: 200 ms, around 400 ms, around 800 ms, plus small jitter and a total time cap. Never configure infinite retries, as they can amplify load on an already struggling server.

Not every `IOException` or HTTP status should be retried. Validation errors, invalid credentials, `requestId`/payload conflicts, and permanently rejected operations usually require fixing the input. Sometimes a request has completed but the client lost the result; a lost response is an **indeterminate state**, not proof of failure.

### 8.2. TTL and Duplicate Detection Capability

Dedup records must be kept long enough relative to the **maximum retry duration**, queue delays, client offline periods, and business rules. If the server deletes the `req-001` record after 10 minutes, but the client retries after 1 hour, the server may treat it as a **new** request and cause a second side effect.

There is no single TTL that is “right for every business domain”:

- Small, low-risk actions can use short retention and accept a finite deduplication window.
- Payments, money transfers, or order placement usually need a **unique business transaction ID**/ledger, status lookup, and retention rules longer than a temporary cache.
- The system needs a bounded-memory/storage cleanup strategy, protection against clients generating unbounded IDs, and metrics for abnormally long `pending` states.

**Do not use the client's IP address + port to identify a duplicate request:** each retry can open a new connection with a different ephemeral port, or pass through a different NAT/proxy. A single connection can also carry many different requests. The logical key must live at the **application layer**.

### 8.3. Security and Key Scoping

A client-supplied `requestId` is **untrusted input**. The server must:

- Authenticate and authorize every request as usual; a duplicate ID **must not bypass auth**.
- Scope keys by tenant/principal/operation appropriately so one user cannot access another user's responses or keys.
- Enforce length/format limits, maximum pending requests, and retention limits to prevent resource exhaustion attacks.
- Compare fingerprints for commands with side effects; conflicts must return a clear error. Never “serve someone else's cached response” when two clients accidentally or intentionally use the same ID.
- Never embed secrets in IDs or return cached responses containing sensitive data to an unauthorized caller.

Over plain TCP, `requestId` does **not** protect integrity, confidentiality, or peer identity. For communication over untrusted networks, use appropriate security mechanisms (TLS and application-layer authentication).

## 9. When Do You Need Natural Idempotency, Deduplication, and Business Keys?

**Idempotency** means repeating the same operation produces the same **intended effect** as executing it once, under a defined contract. Not every operation is naturally idempotent:

| Operation | Safe to retry directly? | Handling to consider |
|---|---|---|
| Read order status | Usually causes no business side effects | Still needs appropriate deadlines and consistency |
| “Set config value X = 5” | Can be idempotent in final effect | Concurrent updates/versioning still need handling |
| “Increase balance by 10” | **No**; doing it twice gives +20 | Stable `requestId` + atomically recorded effect |
| “Create new order” | Usually no; easily creates two orders | Client business key or durably stored `requestId` |
| “Send email” | Resending can produce two emails | Outbox/idempotent provider, contract-based dedup |
| “Process payment” | Must not be retried arbitrarily | Provider idempotency key, transaction ID, and reconciliation |

A `requestId` helps *identify the operation*, but true idempotency also depends on **how keys and side effects are stored**. A `PUT` or state-assignment operation that looks idempotent in its final state can still emit multiple audit records or webhooks if not designed carefully.

## 10. Debugging and Logging by Request ID

When investigating a report of “clicked once but got two orders”, minimal useful logs include:

```text
time | scope/tenant | requestId | operation | payloadFingerprint
     | state | duplicateDecision | responseStatus | businessRecordId
```

Useful metrics to track: new requests, retries with the same ID, cache replays, ID conflicts, requests stuck in `IN_PROGRESS` too long, timeout rate, completion latency, and dedup record expiration rate. Avoid logging secret payloads, credentials, or unnecessary sensitive data; use correlation/trace IDs to link events across services.

Commonly misinterpreted symptoms:

| Symptom | Correct interpretation |
|---|---|
| Server logs two TCP connections from two ephemeral ports | Does not tell you whether they are duplicate requests; check `requestId` |
| Client logs a timeout, but server already has the business record | Request may have completed and response was lost; query by business/request ID |
| Two requests with same ID, same fingerprint, one is running | Do not allow two workers to apply the side effect simultaneously |
| Retry receives original `OK` response | Server likely processed the first attempt; this is the desired replay behavior |
| Same ID but different payload | Protocol conflict; do not silently treat it as a request update |
| Two requests with different IDs, identical payload | Insufficient evidence of a duplicate; check intent and unique business key |
| Server restarts and the same ID creates another record | Dedup was only in RAM or the retention window was too short |
| Client sees the response twice | Client must correlate by `responseTo` and avoid triggering the effect twice |

### Checklist for a Request-Response Protocol Over TCP

1. **Framing:** standard header/delimiter/length, size limits, handling partial reads and EOF.
2. **Identity:** unique `requestId` within the defined scope, preserved across retries, `responseTo` matching the request.
3. **Validation:** auth, schema, fingerprint, and same-ID-different-content conflicts.
4. **Server lifecycle:** atomic registration, `IN_PROGRESS` concurrency handling, durable storage of results/side effects when needed.
5. **Client lifecycle:** pending table, timeouts/deadlines, bounded retries with backoff/jitter, late-response cleanup.
6. **Retention/observability:** dedup TTL, `requestId` logging, metrics, and a way to query status after a timeout.

## 11. Reasoning Exercises

**Scenario A:** The client sends `req-21, ADD 10`, times out reading the response, and then sends **`req-22, ADD 10`**. The server already executed the first command. Can it add 20?

**Answer:** Yes, because two different IDs are treated as two separate intents. If this was a retry of the same intent, `req-21` must be kept; the server must check/store the ID and side effect per the contract.

**Scenario B:** The server receives two copies of `req-21, ADD 10` nearly simultaneously on two connections. Is `HashMap.containsKey` followed by `put` enough?

**Answer:** No, not in a multi-threaded server. You need atomic unique registration or locking/transactions; otherwise, both workers can see the ID as absent and both apply the addition.

**Scenario C:** The client receives `responseTo=req-B` before `responseTo=req-A`, even though it sent A before B. Does this violate TCP ordering?

**Answer:** Not necessarily. The server/protocol may send response B before A; TCP still preserves **the order of bytes actually sent**. The client must correlate responses by ID.

**Scenario D:** The client retries the same `requestId` but changes the amount from 10 to 20. Should the server replay the old response, update to 20, or report a conflict?

**Answer:** Report a **conflict**, because the same ID was attached to two different contents; a new request must have a new ID and be confirmed as a separate intent.

**Scenario E:** The dedup cache is only in RAM. The server committed the balance increase but crashed before sending the response. After restart, the client retries. Can the balance be increased twice?

**Answer:** Yes. RAM loses the dedup record. To survive restarts, both the ID and the effect must be persisted durably, ideally atomically in an appropriate transaction or using downstream idempotency.

**Scenario F:** The server deduplicates and returns the correct original response, but the client receives that response twice. Does server-side deduplication automatically prevent the UI from invoking a callback twice?

**Answer:** No. The client must match `responseTo`, check pending/completed state, and enforce a policy for handling late/duplicate responses.

**Scenario G:** Two independent customers happen to send `req-1`. Is sharing one global cache key safe?

**Answer:** No. Keys must be scoped by tenant/principal/operation appropriately, and every request must be authenticated. An ID is not an authorization key.

**Scenario H:** A duplicate `requestId` is evicted from the cache after 5 minutes, but the client retries after 2 hours. Can the server still be considered to guarantee “no duplicates”?

**Answer:** No. The deduplication guarantee is only valid within the published **retention window** and constraints, unless a durable business ID continues to protect the effect.

## 12. Key Takeaways

- TCP delivers ordered bytes by itself; **requests, responses, and message IDs belong to the application protocol**. TCP retransmission is not equivalent to an application retry.
- One logical operation has a **stable `requestId`** across all retries; responses must carry **`responseTo`** to match the right task. New intents must use new IDs.
- The server handles new, in-progress, completed, and same-ID-different-payload requests **along distinct branches**. Same ID + same payload after `COMPLETED` should replay the original result without applying the side effect again.
- To prevent duplicate effects across concurrency and crashes, deduplication and business effects must be protected by **atomic registration, durable state, and appropriate transactions/idempotency**. An in-memory cache is for illustration, not a complete guarantee.
- A timeout means **outcome unknown**, not that the server failed. Retries must have deadlines/backoff and respect the idempotency contract.
- Both the server (request deduplication) and the client (response correlation) have distinct responsibilities.

### Java 17 Documentation

- [`Socket` — TCP sockets and I/O streams](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`ServerSocket` — listening for connections](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [`DataInputStream` — `readUTF`, `readInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [`DataOutputStream` — `writeUTF`, `writeInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html)
- [`UUID` — generating random request IDs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html)
