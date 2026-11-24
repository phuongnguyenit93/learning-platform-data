# Simulating Connection Loss Before or After Target Receipt

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot organizes integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Systems must manage configuration, data contracts, transactions, errors, deduplication, testing, and observability across real integration flows.

Suppose **Order Service** calls `POST /reservations` on **Inventory Service** to reserve stock. The client sends the request, waits a few seconds, and hits `Connection reset` or `Read timed out`. Two very different realities exist:

- Inventory never received or never processed the request: retrying may be necessary.
- Inventory **wrote the reservation and COMMITTED**, yet the response was lost in transit: a naive retry may reserve stock **a second time**.

From the client's perspective, both scenarios produce **the exact same `IOException` or timeout**. Therefore, the core of this lesson is not picking a retry count, but **precisely simulating the disconnect point, gathering evidence of target-side state, and ensuring safe retries and reconciliation**.

This lesson belongs to the **Contracts and Edge Cases** chapter, topic **Simulating connection loss before or after the target receives the request**. This problem spans HTTP, SOAP, databases, Redis, Kafka, RabbitMQ, RSocket, and Spring Integration adapters, differing only in each protocol's confirmation mechanics.

### Learning outcomes

After this lesson, you will be able to:

1. Distinguish **request sent, broker/endpoint received, validated, committed, and acknowledged**.
2. Explain why a timeout never proves a request went unprocessed.
3. Design a **failure window matrix** spanning pre- and post-receipt/commit/ACK checkpoints.
4. Simulate connection refused, TCP resets, dropped responses, delays, partial request bodies, and network partitions.
5. Build HTTP tests proving the target persisted side effects before dropping the response.
6. Define contracts using **`operationId`/`Idempotency-Key`**, response replay, and status lookup APIs.
7. Test producer confirms, consumer ACKs, offset commits, and inbox/outbox on RabbitMQ/Kafka.
8. Separate transient network errors from **UNKNOWN** business outcomes.
9. Measure and curb retry storms, and handle incidents when target state is uncertain.
10. Write acceptance tests covering network faults, concurrency, crashes, restarts, and recovery.

> **Core rule:** “Client received no acknowledgment” **is not** “target never received the request” and **is not** “target never committed.” Without proof, business state must be recorded as **UNKNOWN**—never mark it **FAILED** and resend a non-idempotent command.

## 1. Draw the timeline before simulating

~~~mermaid
sequenceDiagram
    participant C as Order Service (Client)
    participant N as Network / Proxy
    participant T as Inventory API (Target)
    participant D as Target Database
    C->>N: 1. Write request bytes
    N->>T: 2. Target receives request
    T->>T: 3. Validate + authorize
    T->>D: 4. Write reservation
    D-->>T: 5. COMMIT OK
    T-->>N: 6. Produce HTTP response
    N-->>C: 7. Client receives response
    Note over C,D: Connection can break at any interval
~~~

There is no single instant called “target received.” Define which milestone you mean:

| Milestone | What is proven to have happened | What is **NOT** yet proven |
| --- | --- | --- |
| Client calls `RestClient.post()` | Code began the call | Request left the process |
| Client finishes writing socket bytes | Local OS/client stack accepted bytes | Target application read them |
| Proxy receives request | Request reached proxy | Backend service received it |
| Target handler starts executing | Handler saw the request | Validation passed or SQL committed |
| Target queue durably accepts command | Work persisted per contract | Business side effect completed |
| DB COMMIT succeeds | Business write committed in that DB | Caller received response or broker ACKed |
| Target writes response to socket | App/transport began sending response | Client read, parsed, and saved result |
| Client receives HTTP 2xx | Target returned success per HTTP contract | Async downstreams also finished |
| Client persists receipt/result | Caller holds durable proof | External systems outside receipt scope completed |

**Note:** An HTTP 202 may mean only that the server **accepted work for processing**, not that the final business transaction finished. Even HTTP 200 only means what the **specific API contract** defines: some APIs return 200 when starting a background workflow.

### 1.1. Three states to distinguish

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CONFIRMED: Proof target completed
    PENDING --> REJECTED: Explicit rejection per contract
    PENDING --> UNKNOWN: Timeout / lost connection
    UNKNOWN --> CONFIRMED: Status query / idempotent replay
    UNKNOWN --> REJECTED: Status query confirms rejected
    UNKNOWN --> PENDING: Retry with same operationId (per policy)
    CONFIRMED --> [*]
    REJECTED --> [*]
~~~

- **CONFIRMED:** sufficient business-defined evidence exists, such as a receipt/transaction ID the target guarantees was committed.
- **REJECTED/FAILED:** target explicitly rejected and verified no business side effect occurred, or the failure cannot produce a side effect per contract.
- **UNKNOWN:** insufficient evidence to tell whether side effects occurred.
- **PENDING:** intent is in progress or queued for retry/reconciliation, not “never sent.”

In production, state machines may include richer states like `WAITING_AUTH`, `RETRY_SCHEDULED`, `CANCEL_REQUESTED`, `CONFLICT`, and `MANUAL_REVIEW`. Above all, never collapse **UNKNOWN** into **REJECTED**.

## 2. Failure window matrix

Consider a state-mutating command (reserve/charge/ship), not a read-only GET.

| Scenario | Disconnect point | Could target have received? | Could target have committed? | What should client do? |
| --- | --- | --- | --- | --- |
| A | Before TCP connect | No for **this attempt** if socket never opened | No for this attempt; consider prior attempts | Safer to retry, still keeping `operationId` |
| B | After connect, before full body sent | Partial receipt possible | Depends on protocol/streaming handler | Do not guess; inspect trace/state |
| C | After target receipt, before validation | Yes | Usually no, though middleware may write audits/effects | Distinguish accepted vs. committed |
| D | After validation, before DB COMMIT | Yes | Could roll back or still be in-flight | Wait/query by key |
| E | **After COMMIT, before sending response** | Yes | **Yes** in this fault-injected window | Query status or replay same key |
| F | Target sent response, network dropped it | Yes | Per contract, likely committed | Caller treats as UNKNOWN |
| G | Client got 2xx then crashed before saving receipt | Yes | Likely committed | Durable intent + idempotent recovery |
| H | Timeout, client retries with **new key** | Yes | First attempt may have committed | **Dangerous: duplicate** |
| I | Timeout, client retries with **same key** | Yes | First attempt may have committed | Safe **if target enforces idempotency properly** |

Simulations must prove which row of the table is being tested. Injecting `connection reset` on a stub **that never executes side effects** only tests “disconnect before processing”—it does not prove safety in window E.

### 2.1. Identical timeouts, opposite outcomes

~~~mermaid
flowchart TD
    R["Client POST reserve"] --> D{"Where did disconnect happen?"}
    D -->|"Before request reached target"| N["Target: no reservation"]
    D -->|"After COMMIT, before response"| C["Target: reservation exists"]
    N --> T["Client sees timeout/reset"]
    C --> T
    T --> U["Outcome UNKNOWN from client view"]
    U --> Q["Query operationId or idempotent retry"]
~~~

A client must never use `SocketTimeoutException`, `ResourceAccessException`, or HTTP 502/504 alone to assume the server never received the request. Gateways and proxies can sever responses after the backend finished processing.

## 3. Distinguishing acknowledgment layers

**Identify who is actually acknowledging:**

| Message/acknowledgment | Who confirms? | What it does NOT prove |
| --- | --- | --- |
| TCP ACK | Peer TCP stack | Application processed or committed |
| HTTP request body write completed | Local HTTP client/OS | Remote read the entire body |
| HTTP 200/201 | HTTP endpoint/gateway | Async background workers finished unless contracted |
| HTTP 202 | Endpoint accepted work | Business operation completed |
| HTTP 409 | Server reported contract conflict | Automatically retryable or permanent |
| Kafka producer future success | Broker accepted per `acks` config | Consumer committed SQL |
| Rabbit publisher confirm ACK | Broker confirmed per AMQP policy | Routed to consumer or business completed |
| Rabbit consumer `basicAck` | Consumer acknowledged delivery on channel | Producer client knows the result |
| Kafka offset commit | Consumer group progress | Side effect committed if committed early |
| PostgreSQL JDBC COMMIT success | Database confirmed commit | HTTP caller received the receipt |
| Redis command `OK` | Redis executed command per protocol | Concurrent SQL transaction succeeded |

**Subtlety:** “Target received” sometimes means “broker persisted to queue,” sometimes “handler ran,” and sometimes “database committed.” Tests must pick one meaning and record matching evidence instead of calling everything “delivered.”

## 4. Define the business contract before cutting the network

Suppose the stock reservation API is:

~~~http
POST /v1/reservations HTTP/1.1
Host: inventory.example.org
Content-Type: application/json
Idempotency-Key: 5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2

{"orderId":"ORD-100","sku":"SKU-A","quantity":2}
~~~

The contract must state:

1. An `Idempotency-Key` identifies **one business intent**, not one HTTP attempt.
2. Retries of the same intent reuse **the same key and semantic payload**.
3. The server retains keys and results long enough, surviving restarts if required by SLA.
4. Reusing an old key with a different payload returns a clear conflict/mismatch without creating new work.
5. On success, the server returns **`reservationId`**, `operationId`, and state.
6. Provide a status-lookup endpoint if operations can be async or have unknown outcomes.
7. Specify key retention and behavior after expiration.
8. Define 400/401/403/409/422/429/5xx semantics explicitly rather than guessing defaults.
9. Distinguish **accepted** from **completed**.
10. Specify ordering/versioning when two distinct commands target the same order.

### 4.1. Success response

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/reservations/RES-500

{"operationId":"5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2",
 "reservationId":"RES-500",
 "state":"CONFIRMED"}
~~~

On replay with the same key, an API may replay the original status/body or return `200 OK` with the same `reservationId`. **This is a contract policy**, not a universal rule for every `Idempotency-Key` API.

### 4.2. Status lookup

~~~http
GET /v1/operations/5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2 HTTP/1.1
Host: inventory.example.org
Authorization: Bearer <redacted>
~~~

Example response:

~~~json
{
  "operationId": "5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2",
  "state": "CONFIRMED",
  "reservationId": "RES-500"
}
~~~

Status APIs must enforce service/tenant authorization—never expose transaction data solely by knowing an `operationId`. If status lookup returns 404, read-replica lag or retention expiry might be involved; **404 does not prove the operation never committed** unless the contract guarantees strong read consistency.

### 4.3. Never generate a new key per retry

~~~java
// Wrong: each attempt gets a brand-new logical identity.
retry(() -> inventory.reserve(
        java.util.UUID.randomUUID().toString(),
        command));
~~~

~~~java
// Right: key is created once for one business intent.
String operationId = command.operationId();
retry(() -> inventory.reserve(operationId, command));
~~~

`retry` illustrates orchestration; real code needs bounded retry policies and overall deadlines. Especially for Payments and Inventory, retrying with a fresh token **does not erase the earlier side effect**.

## 5. Server-side idempotency must be atomic

A client sending the same key is not enough. If the target stores the key only **after** executing the side effect, two concurrent attempts can both execute the business logic.

### 5.1. Illustrative SQL schema

~~~sql
CREATE TABLE api_idempotency (
    consumer_name VARCHAR(80) NOT NULL,
    operation_id UUID NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(24) NOT NULL,
    response_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (consumer_name, operation_id)
);

CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    state VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

**Two distinct protective constraints:**

- `PRIMARY KEY (consumer_name, operation_id)` identifies seen intents.
- `UNIQUE (operation_id)` on the business table blocks duplicate reservations from retries or callers bypassing the idempotency store.

`request_hash` fingerprints the **canonicalized business payload**, not an arbitrary serialized JSON string whose key order might vary. Never log sensitive raw payloads; ensure hashing policies handle low-entropy or guessable inputs safely.

### 5.2. Transaction must cover both idempotency result and business state

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as Inventory Service
    participant D as PostgreSQL
    C->>T: Reserve(operationId, requestHash)
    T->>D: BEGIN
    T->>D: INSERT idempotency row ON CONFLICT DO NOTHING
    alt New key
        T->>D: INSERT reservation
        T->>D: UPDATE idempotency state=COMPLETED + receipt
        T->>D: COMMIT
        D-->>T: Commit OK
    else Existing key
        T->>D: Read stored hash/state/receipt
        D-->>T: Existing result
    end
    T-->>C: Return stored receipt
~~~

If the idempotency insert and reservation insert **do not share a transaction**, you risk recording “key processed” without a reservation—or vice versa.

### 5.3. Claiming operations in PostgreSQL with a unique key

~~~sql
INSERT INTO api_idempotency (
    consumer_name, operation_id, request_hash, state)
VALUES (
    'inventory-reserve', :operationId, :requestHash, 'PROCESSING')
ON CONFLICT (consumer_name, operation_id) DO NOTHING;
~~~

Inside the **same SQL transaction** when the claim succeeds:

~~~sql
INSERT INTO inventory_reservations (
    reservation_id, operation_id,
    order_id, sku, quantity, state)
VALUES (
    :reservationId, :operationId,
    :orderId, :sku, :quantity, 'CONFIRMED');
~~~

~~~sql
UPDATE api_idempotency
   SET state = 'COMPLETED',
       response_json = CAST(:receiptJson AS jsonb),
       completed_at = CURRENT_TIMESTAMP
 WHERE consumer_name = 'inventory-reserve'
   AND operation_id = :operationId;
~~~

Then COMMIT. If the transaction rolls back, all writes roll back together. When two duplicate-key requests arrive concurrently, PostgreSQL's unique index and transaction isolation serialize the insert conflict; the losing request must **re-read state after the winner commits** or return `IN_PROGRESS` per policy rather than assuming data is already visible.

### 5.4. Application service pseudocode

~~~java
@Transactional
public ReservationReceipt reserve(
        UUID operationId,
        String fingerprint,
        ReserveCommand command) {

    boolean claimed = idempotencyStore.tryClaim(
            "inventory-reserve", operationId, fingerprint);

    if (!claimed) {
        StoredOperation previous =
                idempotencyStore.find("inventory-reserve", operationId);

        if (!previous.requestHash().equals(fingerprint)) {
            throw new IdempotencyPayloadMismatchException();
        }

        if (previous.completed()) {
            return previous.receipt();
        }
        throw new OperationInProgressException();
    }

    ReservationReceipt receipt =
            reservationRepository.insertReservation(
                    operationId, command);

    idempotencyStore.complete(
            "inventory-reserve", operationId, receipt);

    return receipt;
}
~~~

`idempotencyStore`, `ReserveCommand`, `ReservationReceipt`, and the exceptions are **application-defined interfaces/classes**, not built-in Spring APIs. This pseudocode assumes `tryClaim` uses atomic SQL, all operations share the **same `DataSource`/transaction manager**, and `@Transactional` runs through a Spring proxy.

**Never place external HTTP calls inside this transaction** expecting rollback to undo remote side effects. If reservation must notify an ERP, the target can write to an internal outbox for durable handoff.

### 5.5. Crashes between claim and completion

If `PROCESSING` exists only inside an **uncommitted transaction**, crashing before COMMIT rolls back both claim and reservation so retries can reclaim cleanly. If you commit the claim early and run business writes in a later transaction, design **leases, `IN_PROGRESS` state, and recovery** so keys never get stuck forever.

### 5.6. Idempotency retention and payload mismatch

A complete contract answers:

- How long is a key recognized?
- If retried after key expiry, is duplication possible?
- If same key arrives with a different body, reject or return the old result?
- If responses include time-varying fields, replay the original receipt or build fresh state?
- If the first attempt returned 5xx after transaction rollback, is that “failure” cached permanently?
- If an operation was accepted and work is running, which status is returned?
- If order rows grow large, are archival/tombstone records needed so old keys cannot resurrect retired commands?

For high-risk side effects, retention must match **real retry/replay windows**, including broker DLQs, worker outages, and manual replays.

## 6. Simulating HTTP disconnects before target receipt

To genuinely test **target never received**, inject faults at the proxy/network **before requests reach the target**.

### 6.1. Scenario A: connection refused

A client calls a `host:port` where nothing is listening:

~~~text
Order Service
    |
    +-- TCP connect → ECONNREFUSED
    |
    x  Target HTTP handler never runs on this connection
~~~

Proving an endpoint **refused the connection** proves no request ran on that connection. However, never assume **the overall business intent never arrived** if the client/SDK already tried an earlier attempt or a proxy retried transparently.

Unit/integration tests should verify:

- Client classifies the connection exception under the proper error taxonomy.
- Local business state is not marked `CONFIRMED` merely because `post()` was called.
- Outbox intent stays durable and scheduled for retry.
- Retries do not generate a new `operationId`.
- HTTP client pools/timeouts do not hang forever.

### 6.2. Scenario B: TCP reset right after connect, before request body

Place a fault proxy before the target and inject RST/drop from client to target **before forwarding bytes to the backend**. Verify:

1. Proxy logged an accepted connection.
2. Target recorded zero request-received entries for that attempt.
3. Target DB has no row for `operationId`.
4. Client observed a network failure.
5. Retrying with the same `operationId` once connectivity recovers creates exactly one reservation.

A WireMock/MockWebServer “disconnect at start” illustrates a transport fault, yet **does not prove real target behavior**. Concluding “target never received” requires **target-side evidence** or a proxy known not to have forwarded bytes.

### 6.3. Scenario C: disconnect after sending half the body

An HTTP request carries a large body (e.g., JSON/XML import). Connection breaks after a few KB:

~~~text
POST /import Content-Length: 100000
  -> target receives first 4096 bytes
  -> client/proxy disconnects
  -> target cannot parse complete payload
~~~

Many frameworks buffer and validate the full body before calling controllers. However, streaming APIs can trigger side effects **before receiving the full body**, so never assume partial requests are always safe.

Tests should verify actual parser/handler contracts:

- Does commit happen atomically only after full payload receipt?
- Are uncommitted temporary artifacts cleaned up?
- Does the target maintain a `multipart upload session` or import checkpoint?
- If the client retries the full file, do duplicate rows occur?
- Are request size, timeout, and streaming semantics consistent?

## 7. Simulating HTTP target received but not yet committed

This is a critical window because “request received” **does not mean business completed**.

### 7.1. Use synchronization gates instead of sleep

A test-only target can expose three synchronization points:

~~~text
onRequestReceived:
    record RECEIVED(operationId)
    signal requestReceivedLatch
    await allowBusinessWriteLatch

businessWrite:
    BEGIN; insert business row; COMMIT
    signal committedLatch
    await allowResponseLatch

writeResponse:
    return receipt
~~~

Test orchestration sequence:

1. Client sends POST in an async task.
2. Wait on `requestReceivedLatch` to prove the target handler started.
3. Cut the proxy connection **before** releasing the write transaction.
4. Open `allowBusinessWriteLatch` or cancel the operation per contract.
5. Query the target DB to confirm whether the side effect happened.
6. Never infer server outcome from the client's exception alone.

**Never use `Thread.sleep(200)` as proof a request arrived or DB committed.** Varying scheduler/network delays make tests flaky. Use `CountDownLatch`, barriers, database rows/states, or event hooks with finite timeouts.

### 7.2. Distinguish “received” from “durably accepted”

A server might return 202 after inserting a command into `pending_jobs` for a worker to process later:

~~~text
HTTP handler received
   -> INSERT pending_jobs; COMMIT
   -> 202 Accepted
   -> background worker later modifies inventory
~~~

If the 202 response is lost, the client does not know whether **the job record was saved**; querying by `operationId` must return `ACCEPTED/PENDING`. Retrying POST with the same key must not create a second job. Never report “COMPLETED” right after merely inserting a pending job.

## 8. Simulating target COMMITTED but response lost

This is the centerpiece scenario: **server-side success and client-side error coexist**.

~~~mermaid
sequenceDiagram
    participant C as Order Service
    participant P as Fault Proxy
    participant T as Inventory Service
    participant D as PostgreSQL
    C->>P: POST Idempotency-Key=K-100
    P->>T: Forward request
    T->>D: INSERT reservation + idempotency receipt
    D-->>T: COMMIT OK
    T-->>P: HTTP 201 receipt
    P--xC: DROP response / TCP RESET
    C->>C: Timeout → mark UNKNOWN
    C->>P: GET /operations/K-100 or retry same key
    P->>T: Reconciliation
    T->>D: Find stored receipt K-100
    D-->>T: CONFIRMED, reservation R-500
    T-->>C: Same receipt (no new reservation)
~~~

### 8.1. Key distinctions

- **Lost request:** target may never know the command.
- **Lost response:** target may have committed while only the caller doesn't know.
- **Lost broker acknowledgment:** broker may have stored the event while the producer doesn't know.
- **Lost consumer ACK:** consumer may have committed SQL while the broker may redeliver.

**Every case leads to potential replay**, though the timing and location requiring idempotency differ.

### 8.2. A flawed design that duplicates side effects

~~~java
try {
    inventoryClient.reserve(orderId);
} catch (ResourceAccessException e) {
    // Wrong: timeout does not prove server did not reserve.
    inventoryClient.reserve(orderId);
}
~~~

If `reserve(orderId)` generates a random `operationId` inside each call, the second request looks like a **brand-new business command** to the target.

### 8.3. A better design

~~~java
String operationId = outboxIntent.operationId();
try {
    ReservationReceipt receipt =
            inventoryClient.reserve(operationId, command);

    outboxIntent.markConfirmed(receipt);
} catch (ResourceAccessException e) {
    // Do not generate a new operationId.
    outboxIntent.markUnknown(e.getClass().getSimpleName());
    reconciliationScheduler.schedule(operationId);
}
~~~

`outboxIntent`, `reconciliationScheduler`, and `inventoryClient` are illustrative application components. State must be durably persisted in the DB, not held only in Java fields. Never log raw `Authorization` headers or tokens in error logs.

## 9. HTTP hands-on: stub test dropping response after “commit”

One controlled simulation uses **OkHttp MockWebServer**: the stub tracks side effects by `Idempotency-Key`, executes an in-memory “commit” **before** injecting a network fault, and the client then retries with the same key and receives the original receipt.

This is a **controlled contract/transport test**—it does not replace PostgreSQL transaction tests.

### 9.1. Illustrative test dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Match artifact/group to your project's OkHttp version.
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

With OkHttp 5 or other Spring Boot versions, MockWebServer packages/artifacts may differ; pin compatible versions via dependency management. Never alter production BOM versions just to copy a test snippet.

### 9.2. Test: “target processed then socket closed”

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.*;

class LostResponseContractTest {

    @Test
    void commitsOnceEvenIfFirstResponseIsLost() throws Exception {
        var reservations =
                new ConcurrentHashMap<String, String>();
        var businessInserts = new AtomicInteger();
        var dropFirstResponse = new AtomicBoolean(true);

        try (var server = new MockWebServer()) {
            server.setDispatcher(new Dispatcher() {
                @Override
                public MockResponse dispatch(RecordedRequest request) {
                    if (!"/v1/reservations".equals(request.getPath())) {
                        return new MockResponse().setResponseCode(404);
                    }

                    String key = request.getHeader("Idempotency-Key");
                    if (key == null || key.isBlank()) {
                        return new MockResponse().setResponseCode(400);
                    }

                    // Simulate business commit / persisted receipt:
                    String receipt = reservations.computeIfAbsent(
                            key, ignored -> {
                                businessInserts.incrementAndGet();
                                return "RES-500";
                            });

                    if (dropFirstResponse.getAndSet(false)) {
                        // Target stub already saved result before
                        // closing connection without sending HTTP response.
                        return new MockResponse()
                                .setSocketPolicy(
                                        SocketPolicy.DISCONNECT_AFTER_REQUEST);
                    }

                    return new MockResponse()
                            .setResponseCode(201)
                            .addHeader("Content-Type", "text/plain")
                            .setBody(receipt);
                }
            });

            server.start();

            RestClient client = RestClient.builder()
                    .baseUrl(server.url("/").toString())
                    .build();

            String operationId =
                    "d9c7590a-2544-4af1-a76e-438a1f1b6154";

            // Test setup must disable transparent retries
            // in the underlying HTTP transport if it auto-retries.
            assertThrows(RestClientException.class,
                    () -> reserve(client, operationId));

            assertEquals(1, businessInserts.get());

            String replayReceipt = reserve(client, operationId);

            assertEquals("RES-500", replayReceipt);
            assertEquals(1, businessInserts.get());
            assertEquals(1, reservations.size());
        }
    }

    private String reserve(RestClient client, String operationId) {
        return client.post()
                .uri("/v1/reservations")
                .header("Idempotency-Key", operationId)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"orderId":"ORD-100",
                         "sku":"SKU-A",
                         "quantity":2}
                        """)
                .retrieve()
                .body(String.class);
    }
}
~~~

**How to read this test:**

- `computeIfAbsent` models **creating at most one reservation per `operationId`**.
- `DISCONNECT_AFTER_REQUEST` injects a network failure after the stub receives the request; the dispatcher has already persisted the simulated receipt.
- The first client call sees no response; retrying with the same key receives `RES-500`.
- `businessInserts==1` provides **target-stub evidence** that the logical side effect ran only once.

**Important limitations:**

1. `ConcurrentHashMap` does not survive restarts and does not replace SQL transactions; this is only a **simulation**.
2. Exact behavior of socket policies and transport retries must be verified against your MockWebServer/HTTP client version.
3. If the underlying HTTP transport retries transparently, asserting “first call throws” may fail even though the target saw the fault. To test each attempt precisely, disable transport auto-retries and assert server request counts.
4. An in-memory idempotency map like this is **insufficient** for multi-pod production deployments.
5. This test does not verify payload fingerprint comparison; add a separate test reusing the key with a different body.
6. This test does not verify DB commits or process restarts; use Testcontainers and the real target app next.

### 9.3. Testing key reuse with a different payload

A contract-compliant target must catch:

~~~text
Key K-100, body {"sku":"A","quantity":2} -> reserve R-500
Key K-100, body {"sku":"B","quantity":7} -> conflict/mismatch
~~~

It must neither return receipt `R-500` for request B as if B succeeded, nor create a second reservation under the same key. Assert the response per your **published contract**, such as 409 Conflict or 422 Unprocessable Content if the API adopts those semantics.

### 9.4. Testing two concurrent calls with the same key

Run 2+ concurrent clients sharing one `operationId`. Goals:

- Exactly one transaction creates the reservation.
- The other caller waits, gets the stored receipt, or gets `IN_PROGRESS` per policy.
- No `existsByKey → insert` race occurs.
- If the first transaction rolls back, a subsequent valid attempt can still create the reservation.
- Total business rows = 1 once both finish.
- No deadlocks or indefinite blocking.

Run this test against **PostgreSQL Testcontainers** with real `UNIQUE` constraints and transactions rather than trusting `ConcurrentHashMap`.

## 10. Simulating response loss with a proxy instead of modifying the service

A stronger option places **Toxiproxy** between Order Service and Inventory Service:

~~~text
Order Service
   |
   v
Toxiproxy listen port
   |
   v
Inventory Service → PostgreSQL
~~~

A proxy lets you inject latency, timeouts, bandwidth caps, or connection cuts **without altering business code**. However, **when** you cut determines whether the test is meaningful.

### 10.1. Test fixtures and synchronization gates

The test-only target exposes signals:

~~~text
requestReceivedLatch
businessCommittedLatch
responseReleaseLatch
~~~

Conceptual test script:

~~~text
1. Start Inventory + PostgreSQL + Toxiproxy.
2. Client sends POST operationId K-100 through proxy.
3. Wait for Inventory to signal businessCommittedLatch.
4. Sever proxy path target -> client before response traverses.
5. Allow Inventory to emit its response.
6. Client sees IOException/timeout; does not mark FAILED.
7. Query PostgreSQL directly: reservation K-100 exists.
8. Restore proxy.
9. Client calls GET /operations/K-100 or retries POST with same key.
10. Assert same receipt returned, DB still has one reservation.
~~~

**Test windows must be deterministic.** Adding 500 ms proxy latency and cutting after `Thread.sleep(100)` leaves you guessing whether the server committed. Wait for `businessCommittedLatch` or a committed transaction marker while holding response release.

### 10.2. Cut direction for each experiment

| Fault location | Desired effect | Required evidence |
| --- | --- | --- |
| Client → proxy before connect | Client cannot send attempt | Zero accepted connections for attempt |
| Proxy → target before forward | Target never receives attempt | Target handler counter = 0 |
| Proxy → target after partial forward | Target receives truncated body | Request byte count, validation/result |
| Target → proxy before response | Target may commit without replying | DB committed row + response suppressed |
| Proxy → client after target COMMIT | Target finished, client unaware | Commit marker + client network error |
| After client receipt, before local persist | Target + client exchanged, caller crashed | Target receipt + local intent still pending |
| Broker → consumer before delivery | Message sits in queue, unprocessed | Queue ready/durable state |
| Consumer → broker after DB COMMIT | Consumer ACK lost | DB inbox committed + broker redelivery |

### 10.3. Do not hardcode the wrong version of fault APIs

Toxiproxy Java APIs, Docker images, and toxics have version-specific parameters. When automating tests, check the exact library pinned in your project (e.g., Testcontainers Toxiproxy module and client toxic builders). Never grab a proxy `timeout` snippet assuming it cuts right after COMMIT; **fault injection timing must be controlled by test gates**.

### 10.4. Proxy logs do not replace target evidence

Proxies know what crossed the wire; they do not know whether a SQL transaction committed. To verify post-COMMIT state, inspect:

- Database rows or transaction receipts.
- Application-level commit markers or durable events.
- Deterministic test barriers placed right after commit.
- `operationId` correlation across requests, DB, and logs.

Concluding “the target processed it” from proxy TCP logs alone is unverified guesswork.

## 11. HTTP scenarios to automate

| ID | Fault | Target side effect? | Caller expectation | Post-recovery expectation |
| --- | --- | --- | --- | --- |
| HTTP-01 | DNS/connect fail before request | No for this attempt | Transient / pending retry | One operation |
| HTTP-02 | Reset before target handler | No | UNKNOWN or transport failure | One operation |
| HTTP-03 | Partial body sent | Depends on handler/contract | UNKNOWN | No duplicate |
| HTTP-04 | Handler received, validation rejected | No business commit | Explicit rejection if receipt received | No inappropriate retry |
| HTTP-05 | DB rollback, response lost | No committed reservation | UNKNOWN, query/retry same key | Can succeed once |
| HTTP-06 | DB COMMIT, response lost | **Yes** | UNKNOWN | One reservation, replays old receipt |
| HTTP-07 | Target sends 201, proxy drops | **Yes** | UNKNOWN | One reservation |
| HTTP-08 | Client got 201, local DB write fails | **Yes** | Pending/UNKNOWN after crash | Reconciles, no duplicate |
| HTTP-09 | Two concurrent same-key requests | At most one business write | One success + replay/in-progress | One row |
| HTTP-10 | Same key, different payload | No second side effect | Conflict/mismatch | No mutation |
| HTTP-11 | Retry after server restart | Prior commit exists | UNKNOWN -> confirmed | Idempotency state survives restart |
| HTTP-12 | Target async 202 then worker fails | Accepted, incomplete | PENDING | Status FAILED/RETRY or completed per policy |
| HTTP-13 | Target 429/503 before processing | Usually no, check contract | Bounded retry/backoff | No retry storm |
| HTTP-14 | Timeout after remote side effect | **Possibly** | UNKNOWN | Status lookup/idempotent retry |
| HTTP-15 | Retry after key retention expired | May have committed long ago | No blind retry | Manual reconciliation/retention policy |

Different rows require different retry policies. A `400` from an invalid payload cannot be fixed by retrying; `429` demands quota/backoff; a timeout after a write is `UNKNOWN` even if the exception looks “network transient.”

## 12. Spring Boot RestClient: policy for uncertain outcomes

`RestClient` in Spring Framework 6.1+ is the modern synchronous HTTP client usable from Spring Boot 3.2+.

### 12.1. Isolate HTTP adapters per downstream

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.org")
                .build();
    }
}
~~~

In production, `baseUrl` should come from externalized configuration with HTTPS/TLS trust, authentication, connection pooling, connect/read timeouts, and dedicated observability. **An HTTP request factory does not automatically guarantee a suitable total timeout**; configure timeouts on the underlying transport explicitly.

### 12.2. API adapter attaching operationId

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class InventoryHttpGateway {

    private final RestClient client;

    InventoryHttpGateway(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    ReservationReceipt reserve(
            String operationId, ReserveCommand command) {

        return client.post()
                .uri("/v1/reservations")
                .header("Idempotency-Key", operationId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(command)
                .retrieve()
                .body(ReservationReceipt.class);
    }
}
~~~

`ReserveCommand` and `ReservationReceipt` are illustrative domain DTOs. Never store raw `Authorization` headers or access tokens in DB outboxes or request logs; let workers obtain credentials at execution time.

### 12.3. Classify timeouts accurately

| Error | What you can conclude | What you must NOT conclude |
| --- | --- | --- |
| Connect refused | Could not open connection for this attempt | No prior attempt was processed |
| TLS handshake failed | TLS connection failed per client | Remote had no side effect from another request |
| Pool acquisition timeout | Failed to borrow connection from pool | Business intent was never sent |
| Write failure | Write did not complete per client | Remote received zero partial/full bytes |
| Read timeout | Did not receive response in time | Remote did not commit |
| Connection reset | Connection severed | Whether server received or committed |
| HTTP 502/504 from proxy | Proxy/gateway error or timeout | Backend definitely did not process |
| HTTP 409 | Conflict per contract | Automatically retryable or non-retryable |
| HTTP 202 | Request accepted per contract | Business completed |
| HTTP 201 with durable receipt | Proof per API contract | Out-of-contract workers also succeeded |

Avoid a generic `catch (Exception)` that calls `markFailed`. Map network errors to **unknown outcome** or retry-scheduled state per operation contract, and log the error category for investigation.

### 12.4. Retry policies should follow business semantics

- Pure read-only GETs can retry per HTTP semantics if free of hidden side effects.
- Resource-ID PUTs can be idempotent **if the API honors that contract**.
- State-mutating POSTs require server-side idempotency keys and status lookups.
- Retrying 429/503 needs exponential backoff with jitter and `Retry-After` respect where applicable.
- Never retry 401/403/invalid credentials endlessly.
- Every operation needs a **total deadline** and maximum attempt count.
- When remote outcome is `UNKNOWN`, never emit a new logical command with a new ID.
- Client SDKs may enable **transparent retries**; inspect combined layer settings so attempts do not multiply unexpectedly.

## 13. SOAP, XML, and endpoints without Idempotency-Key

A legacy SOAP system might expose only:

~~~xml
<ReserveOrder>
    <ExternalOrderId>ORD-100</ExternalOrderId>
    <Sku>SKU-A</Sku>
    <Quantity>2</Quantity>
</ReserveOrder>
~~~

If the SOAP response is lost after commit, retries can still duplicate. HTTP Basic/TLS, WS-Security signatures, and XML schema validation **do not provide idempotency**.

### 13.1. If the partner supports a business key

Use a stable `ExternalOrderId`/`OperationId` and require the partner to deduplicate via a unique constraint or return the original receipt. For payments, this usually requires a provider-supported `merchantTransactionId` or request ID.

### 13.2. If the partner does not support idempotency

Choose among safer strategies:

1. **Query status** by business reference before retrying.
2. **Reconcile** via partner reports, batches, or APIs.
3. **Human approval** for high-cost side effects.
4. Workflows with explicit `UNKNOWN` states and timeout SLAs.
5. Compensation if supported by the business contract (cancellation/refund), noting compensation is not ACID rollback.
6. Restrict retries; never auto-replay indefinitely.

**True end-to-end exactly-once is impossible** from the client alone if the target lacks a way to identify logical operations, inspect status, or participate in a suitable transaction protocol.

## 14. Producer: “broker received, but ACK lost”

The pattern mirrors HTTP response loss, except the acknowledging peer is the **broker**.

~~~mermaid
sequenceDiagram
    participant P as Order Producer
    participant B as RabbitMQ / Kafka
    participant R as Consumer
    P->>B: Publish eventId E-100
    B->>B: Accept/persist per broker policy
    B--xP: Producer ACK / confirm lost
    P->>P: Publish outcome UNKNOWN
    P->>B: Retry eventId E-100
    B->>R: Deliver possibly duplicated E-100
    R->>R: Deduplicate by eventId
~~~

If a producer times out waiting for confirms, the broker **may already have persisted the message** without the producer knowing. Therefore:

- Keep outbox `eventId` stable across retries.
- Consumers must be idempotent.
- Track producer attempted, broker confirmed, and consumer applied separately.
- Never mint a “new event” with a fresh `eventId` for the same outbox intent.

### 14.1. RabbitMQ publisher confirms

Rabbit publisher confirms report that the broker processed a publish per confirm semantics. Pairing `mandatory=true` with publisher returns catches unroutable messages; **a publisher ACK alone does not prove a message routed to the intended queue unless returns/routing contracts are checked**.

Illustrative Boot config:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Configure appropriate exchanges, queues, bindings, and durable/quorum persistence. If the broker connection drops **after broker acceptance and before the confirm returns**, the confirm future may fail/time out while the message still exists on the broker.

### 14.2. Kafka producer ACKs

Kafka `acks=all` requires broker acknowledgment across the replicated log/ISR policy, yet does not prove consumers processed the record. Idempotent producers reduce duplicates from **retries within the same producer session** under Kafka protocol semantics; they do not stop **a business command from being republished by another process with a new producer identity**.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

Kafka transactions / exactly-once semantics apply within scoped Kafka read-process-write pipelines; **they do not span PostgreSQL or remote HTTP transactions automatically**. When an outbox relay republishes a logical event after a crash, consumer inboxes and unique business keys remain mandatory.

## 15. Consumer: “DB COMMITTED, but ACK/offset commit lost”

This is the mirror image of losing a publisher confirm.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as PostgreSQL
    B->>C: Deliver E-100
    C->>D: BEGIN + inbox unique insert + business update
    D-->>C: COMMIT OK
    C--xB: Consumer ACK lost / connection closed
    B->>C: Redelivery E-100
    C->>D: Inbox indicates already applied
    C-->>B: ACK duplicate safely
~~~

No connection timeout tuning fixes this. **ACK after COMMIT + inbox idempotency** is a practical pattern for at-least-once delivery.

### 15.1. RabbitMQ manual ACK

~~~java
@RabbitListener(
        queues = "inventory.order-events",
        containerFactory = "manualAckListenerFactory")
public void onMessage(
        OrderEvent event,
        com.rabbitmq.client.Channel channel,
        @Header(AmqpHeaders.DELIVERY_TAG) long tag)
        throws java.io.IOException {

    inventoryService.applyIdempotently(event); // SQL COMMIT

    channel.basicAck(tag, false);              // ACK after COMMIT
}
~~~

This assumes `manualAckListenerFactory` sets `AcknowledgeMode.MANUAL`, `inventoryService` enforces transactions and an atomic SQL inbox, and `OrderEvent` is an app DTO. Add imports for `@RabbitListener`, `@Header`, `AmqpHeaders`, and error paths. Manual ACKs must go out **on the exact channel that received the delivery**; never save tags to ACK from another channel.

**Mandatory test:** force broker/channel disconnect after SQL COMMIT and before `basicAck`, then assert redelivery of `E-100` does not increment business counts.

### 15.2. RabbitMQ AUTO ACK vs. NONE

Spring AMQP `AcknowledgeMode.AUTO` means **the container sends a consumer ACK after the listener method returns normally**—not RabbitMQ's auto-ack-on-delivery. `AcknowledgeMode.NONE` corresponds to broker auto-ack-on-delivery. With synchronous transactional services, `AUTO` works when the method returns only after SQL COMMIT.

If the method merely calls `executor.submit(...)` and returns immediately, `AUTO` ACKs prematurely before the background task runs; virtual threads do not change this.

### 15.3. Kafka offset commit

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    inventoryService.applyIdempotently(record.value());
    acknowledgment.acknowledge(); // Per configured ack-mode.
}
~~~

This assumes `Acknowledgment` is injected by Spring Kafka under an appropriate manual acknowledgement mode. If SQL COMMIT succeeds and the offset commit fails, Kafka redelivers. Committing offsets **before** SQL COMMIT risks losing replayability if the DB rolls back.

Kafka partition ordering and concurrency still matter: `eventId` deduplication does not ensure `E-2`/`E-1` for the same order apply in version order. Enforce version guards and state transition checks.

## 16. SQL inbox for idempotent consumers

An inbox committed alongside business updates:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

With PostgreSQL:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryEventService {

    private final JdbcTemplate jdbc;

    public InventoryEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id)
                VALUES ('inventory', ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Same logical event already processed.
        }

        jdbc.update(
                """
                INSERT INTO inventory_projection(
                    order_id, version, state)
                VALUES (?, ?, 'RESERVED')
                ON CONFLICT (order_id)
                DO UPDATE SET
                    version = EXCLUDED.version,
                    state = EXCLUDED.state
                WHERE inventory_projection.version < EXCLUDED.version
                """,
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

This requires a migration creating `inventory_projection` with a `UNIQUE`/`PRIMARY KEY` on `order_id` and a `version` column. If updating the projection fails, the transaction rolls back the inbox insert too. If an event arrives with an older version, the conditional update prevents overwriting newer state.

**Distinction:** the inbox stops **the same `eventId`** from running twice; the version guard stops **a different-ID event arriving out of order** from regressing state.

## 17. Outbox: protecting “local commit then disconnect before publish”

A producer often writes business state and publishes an event to RabbitMQ/Kafka.

If code writes:

~~~java
@Transactional
public void confirmOrder(Order order) {
    repository.save(order);
    rabbitTemplate.convertAndSend(
            "orders.events", "order.confirmed", order);
}
~~~

`@Transactional` with a JDBC transaction manager **does not pull RabbitMQ publishing into an ACID transaction**. Broker acceptance followed by DB rollback, or DB COMMIT followed by publish failure, are two distinct failure windows.

### 17.1. Outbox pattern

~~~mermaid
flowchart LR
    A["Business command"] --> T["SQL transaction"]
    T --> O["Update order"]
    T --> E["Insert outbox eventId"]
    O --> C["COMMIT"]
    E --> C
    C --> W["Outbox relay"]
    W --> B["Broker or HTTP partner"]
    W --> R["Receipt/confirm or UNKNOWN"]
    R --> U["Retry/reconciliation"]
~~~

Simplified SQL schema:

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

An outbox relay needs **claim/lease** coordination across multiple pods. With PostgreSQL, use `SELECT ... FOR UPDATE SKIP LOCKED` inside short transactions to record leases/statuses. Never hold a SQL transaction open for seconds waiting on HTTP responses or broker confirms.

### 17.2. Crash after broker accepted before outbox status update

~~~text
Outbox row PENDING(E-100)
    |
    +-- relay publish E-100
    +-- broker accepted E-100
    +-- producer confirm LOST / relay crashes
    |
    +-- outbox still PENDING
    +-- relay restarts, publishes E-100 again
    |
    +-- consumer inbox deduplicates E-100
~~~

This is *at-least-once delivery with idempotent processing*, not "exactly-once publish." Changing the outbox `eventId` per attempt breaks deduplication.

### 17.3. Retry budgets and DLQ

If an outbox relay retries 5 times, a RabbitMQ consumer retries 3 times, and an HTTP adapter retries 3 times, total side-effect attempts can multiply beyond expectations. Manage **cross-layer retry budgets**, DLQs/parking, reconciliation, and alerts. Permanent contract failures must not hot-retry.

## 18. Disconnects on JDBC: COMMIT outcome unknown

A JDBC client sends `COMMIT` to the database, then loses the connection before receiving the acknowledgment:

~~~text
Client: COMMIT request sent
DB:    COMMIT may have succeeded
Link:  connection reset before response
Client: transaction outcome UNKNOWN
~~~

Do not assume an exception thrown by `connection.commit()` proves the transaction rolled back. Drivers, JTA, and runtimes have specific behaviors, yet under distributed communication principles, **a `COMMIT` ACK can always be lost after the DB committed**.

### 18.1. Retrying can create two business rows

If code does:

~~~java
try {
    insertOrderWithGeneratedId(command);
} catch (CannotGetJdbcConnectionException ex) {
    insertOrderWithGeneratedId(command); // Risky!
}
~~~

and the connection dropped after a successful COMMIT, the second call inserts a brand-new order with a different ID.

Countermeasures:

- Enforce a `UNIQUE` constraint on business identity/`commandId`.
- Insert/upsert using a stable key.
- On unknown-outcome exceptions, query the DB by the stable key.
- Never mint a new ID/key for the same command.
- If DB failover or read replicas lag, perform consistent reads per contract.
- Separate known deadlock/serialization rollbacks from `COMMIT` acknowledgment loss.

### 18.2. Do not misuse @Transactional

Spring `@Transactional` does not eliminate commit ambiguity across network partitions. It manages local transactions, yet applications still require business idempotency, reconciliation, unique constraints, and retry policies.

## 19. Redis: write acknowledged vs. durable state

Redis `SET` can return `OK`, or the connection can drop after Redis executes the command and before the client reads the reply. Retrying `INCR` doubles the mutation:

~~~text
INCR stock_counter
  → Redis incremented 10 to 11
  → reply lost
  → client retries INCR
  → incremented to 12
~~~

Commands like `SET key value` are idempotent with the same value, whereas `INCR`, `LPUSH`, `XADD`, and side-effecting scripts require careful analysis. Redis persistence and replication durability also depend on AOF/RDB, replication, failover, and configuration.

### 19.1. Testing Redis

1. Start Redis Testcontainers.
2. Use a proxy to drop the response after the server receives/executes `INCR`.
3. Read the counter directly from an independent client.
4. Retry using the same business `operationId` under a deduplicating Lua/SQL contract.
5. Assert the counter incremented exactly once.
6. Test restarts/failovers if durability is required.

Increasing timeouts cannot turn `INCR` into exactly-once. If Redis is just a cache, transient drift or retries may be acceptable; if it acts as an inventory or payment ledger, keep authoritative state in a database with uniqueness and transactions.

## 20. Simulating faults with Testcontainers

Run fault injection in isolated test environments—never against real production systems. Typical topology:

~~~mermaid
flowchart TD
    T["JUnit / SpringBootTest"] --> O["Order Service test"]
    O --> PX["ToxiproxyContainer"]
    PX --> I["Inventory target test service"]
    I --> DB["PostgreSQLContainer"]
    O --> R["RabbitMQContainer / KafkaContainer"]
    R --> C["Consumer test app"]
    C --> DB
~~~

### 20.1. Components to include

- **PostgreSQL Testcontainers**: verifies real commits, rollbacks, and `UNIQUE` constraints.
- **MockWebServer/WireMock**: simulates HTTP errors, verifies headers/bodies, and drops responses.
- **Toxiproxy**: targets directional transport links to inject partitions, latency, or resets.
- **RabbitMQ/Kafka Testcontainers**: verifies publisher confirms, consumer ACKs/offset commits, and redeliveries.
- **`CountDownLatch`/barriers**: synchronizes deterministically before/after commit milestones.
- **Outbox/inbox schema migrations**: runs real production DDL.
- **Logs/counters**: ties `operationId` to target evidence, not just client exceptions.
- **Cleanup**: closes proxies/containers and releases latches in `finally` so tests never hang.

### 20.2. Never use fixed sleep durations as fault triggers

~~~java
// Flaky: no idea which stage the target reached.
Thread.sleep(100);
proxy.disconnect();
~~~

~~~java
// Better approach with a test barrier:
assertTrue(targetCommitted.await(5, TimeUnit.SECONDS));
proxy.disconnectResponsePath();
allowTargetResponse.countDown();
~~~

`proxy.disconnectResponsePath()` is pseudocode for your test proxy's control API, not a literal method on a specific Toxiproxy Java client. In real implementations, use the toxic/cut action supported by your exact library version.

### 20.3. Mandatory timeouts on every latch

Fault-injection tests can prevent targets from ever reaching a milestone. Every `await` must specify a timeout and assertion, and `finally` blocks must release gates so threads/sockets never hang indefinitely—especially during parallel CI runs.

## 21. Periodic regression tests for “received but ACK lost”

Every solid integration system needs a compact, reliable regression suite:

### 21.1. Acceptance criterion for HTTP

~~~text
Given operationId K-100 and payload P
And Inventory target enforces transactional idempotency
When Inventory COMMITs reservation K-100
And the response is cut before Order Service receives it
Then Order Service records state UNKNOWN/PENDING_RECONCILIATION
And Inventory holds exactly 1 reservation for K-100
When Order Service queries or retries with the same K-100
Then it receives the original receipt
And Inventory still holds exactly 1 reservation
~~~

### 21.2. Acceptance criterion for publishers

~~~text
Given outbox event E-100 PENDING
When the broker accepted message E-100
And the producer confirm was lost
Then outbox does not mark it permanently failed
When the relay retries E-100
Then consumer side effect applies once
And outbox eventually transitions to confirmed/reconciled
~~~

### 21.3. Acceptance criterion for consumers

~~~text
Given consumer received E-100
When DB COMMITs inbox + projection
And consumer ACK/offset commit was lost
Then broker may redeliver E-100
When consumer receives E-100 again
Then inbox blocks duplicate business write
And consumer ACK/progress commit succeeds
~~~

### 21.4. Acceptance criterion for local caller crash

~~~text
Given target returned HTTP 201 for K-100
And Order Service crashed before updating its outbox row
When Order Service restarts
Then outbox still holds durable intent K-100
And retry/reconciliation reuses the same key
And target still has only one reservation
~~~

### 21.5. Critical negative cases

- Replay same key with different payload → conflict, zero side effects.
- Retry after retention expiry → explicit policy, never silently duplicate.
- Two concurrent requests with same key → single durable business write.
- Target COMMIT fails → never store `COMPLETED` receipt.
- Target returns 202 then worker fails → caller must not mark `CONFIRMED`.
- Read replica lag → temporary 404 on status GET does not trigger a new-key command retry.
- Missing/invalid `operationId` → reject early.
- Timeout after write → `UNKNOWN`, never assume rollback.
- Consumer receives older low-version event → version guard blocks overwrite.
- Unroutable broker message → publisher return/retry/DLQ policy triggers properly.

## 22. Observing “received”, “committed”, and “outcome known” accurately

Separate these signals:

| Metric or event | Meaning |
| --- | --- |
| `integration.outbound.attempted` | Client started an attempt |
| `integration.outbound.bytes_written` | HTTP transport finished writing bytes (if instrumented) |
| `integration.target.request_received` | Target handler received the request |
| `integration.target.business_committed` | Target business transaction COMMITTED |
| `integration.outbound.response_received` | Client received response |
| `integration.outbound.outcome_unknown` | Caller lacks sufficient proof |
| `integration.outbox.pending_age` | Age of unresolved durable intents |
| `integration.reconciliation.success` | `UNKNOWN` resolved to final state |
| `integration.idempotency.replayed` | Target returned cached receipt |
| `integration.idempotency.conflict` | Same key, different payload |
| `integration.consumer.duplicate` | Consumer caught duplicate event |
| `integration.publisher.confirmed` | Broker confirmed per policy |
| `integration.consumer.business_applied` | SQL/domain side effect committed |
| `integration.consumer.ack_failed` | ACK/offset commit failed |

These metric names are **suggested application instrumentation**, not metrics guaranteed out-of-the-box by Micrometer/Actuator. Measure explicitly and avoid confusing `business_committed` with `request_received`.

### 22.1. Correlation and cardinality

Structured logs may record `operationId`/`eventId` under proper access control, retention, and redaction for investigating incidents. Prometheus metric labels must remain low-cardinality (e.g., `downstream=inventory`, `stage=response_lost`, `outcome=unknown`); **never put `operationId`/`orderId`/tokens into metric labels**.

### 22.2. Never log secrets

Never log `Authorization` headers, Basic credentials, API keys, OAuth2 access tokens, client secrets, database passwords, or raw PII payloads in traces. When fingerprinting payloads, follow contract canonicalization/hashing rules so secrets cannot be inferred.

### 22.3. A trace with a missing response

~~~text
trace / operationId K-100
  10:00:00.000 client POST started
  10:00:00.010 target request received
  10:00:00.030 target transaction committed R-500
  10:00:00.031 proxy reset response
  10:00:02.000 client read timeout (UNKNOWN)
  10:00:05.000 reconciliation GET K-100
  10:00:05.010 target returns CONFIRMED R-500
  10:00:05.020 client state updated CONFIRMED
~~~

This is an illustrative timeline. In reality clocks skew and logs arrive out of order; correlate using `operationId` and causal markers rather than sorting timestamps alone to “prove” ordering.

## 23. Runbook when timeouts leave target receipt uncertain

| Symptom | Risk | Action |
| --- | --- | --- |
| Client read timeout after POST | Target may have committed | Mark `UNKNOWN`, query status/key |
| Connection reset after request bytes | Target may have processed | Check target receipt/DB |
| Gateway 504 while target logs show COMMIT | Duplicate if retried with new key | Retry same key or reconcile |
| HTTP 202 lost response | Job may be persisted | Query `operationId` |
| Publisher confirm timeout | Broker may hold event | Retry same `eventId`, rely on consumer inbox |
| Rabbit consumer ACK failed | DB may have committed | Deduplicate on redelivery |
| Kafka offset commit failed | Record may be processed | Inbox + replay safety |
| JDBC COMMIT ack lost | DB outcome unknown | Query by stable business key |
| Redis INCR timeout | Counter may have incremented | Do not blindly retry `INCR` |
| Idempotency table miss on read replica | Replica lag | Read primary / consistent read |
| DLQ growing | Poison messages or exhausted retries | Inspect contracts, replay carefully |
| Retries spiking | Retry storm overloading target | Rate-limit, backoff/jitter, circuit breaker |
| 409 on key reuse | Payload mismatch or operation in progress | Compare fingerprint/status contract |
| 2 reservations for same `operationId` | Broken server idempotency | Incident, reconciliation, add unique constraint |

### 23.1. Procedure for investigating an UNKNOWN outcome

1. Retrieve the stable `operationId` from the source intent/outbox.
2. Check request/publish attempts and response/confirm evidence.
3. Determine via target evidence whether the network failed **before request, after receipt, or after commit**.
4. Query operation status / target database per contract using consistent reads.
5. If `CONFIRMED`, update local state with the receipt—**never issue a new command**.
6. If explicitly `REJECTED`, record the reason/compensate per policy.
7. If `PENDING`, schedule another check with a deadline.
8. If `UNKNOWN` persists, run idempotent replay or manual reconciliation based on risk.
9. Retain an audit trail of the decision; never alter or delete evidence.
10. Review incidents/backoff settings and add an automated test.

### 23.2. When NOT to auto-retry

- Financial or order side effects lacking idempotency or status lookup.
- Target cannot confirm state and a duplicate carries severe impact.
- Retry window or credentials expired, or request body is no longer certain.
- Payload mismatch under the same `operationId`.
- Permanent validation or authorization failure.
- Broker backlog or partner overload requiring load shedding rather than repeated replays.

In these cases, leaving the operation `UNKNOWN` and escalating/reconciling is **safer than creating a duplicate**.

## 24. Common anti-patterns

| Anti-pattern | Why it is wrong | Right approach |
| --- | --- | --- |
| `catch IOException => NOT_PROCESSED` | You do not know if target committed | `UNKNOWN` + reconciliation |
| Generating a fresh UUID per retry | Turns one intent into multiple commands | Keep `operationId` stable |
| Testing only `connection refused` | Misses lost responses after COMMIT | Inject faults at commit barrier |
| Using `Thread.sleep(100)` to cut proxy | Racy, flaky | `CountDownLatch`/commit marker |
| Counting client HTTP attempts as business success | Attempts do not prove commit | Target DB receipt + business metric |
| In-memory set for production idempotency | Lost on crash, not shared across pods | SQL unique + transaction |
| `SELECT exists` then INSERT without constraint | Concurrent retry race | Atomic INSERT/UNIQUE |
| Committing business and receipt in two transactions | Key/result drift apart | Same DB transaction |
| Saving key only after side effect | Racing retries duplicate | Atomic claim + business write |
| Deduplicating only at producer | Consumer redeliveries still happen | Inbox/unique business key |
| Treating Kafka `acks=all` as consumer applied | Misunderstands broker ACK scope | Consumer commit + idempotency |
| Rabbit consumer ACK before SQL COMMIT | Risks losing messages | ACK after COMMIT |
| Kafka offset commit before DB | Loses replayability | Commit progress after durable handoff |
| Treating HTTP 202 as COMPLETED | Only means workflow accepted | Status polling/completion event |
| Uncoordinated retries across 3 layers | Attempts multiply, overloading system | Cross-layer retry budget |
| Retrying Redis `INCR` on timeout | Double-increments counter | Business idempotency/script/DB |
| Testing HTTP stub and claiming ACID | In-memory state is not durable | PostgreSQL Testcontainers |
| Treating proxy logs as DB commit proof | Proxy cannot see DB transactions | Database receipt/commit marker |
| Deleting outbox row after publish attempt | Confirm may still be lost | Durable state + reconciliation |
| Failing to define key retention | Late replays recreate mutations | SLA-aligned retention |
| Logging `Authorization`/raw payloads to debug | Leaks secrets/PII | Redaction and correlation IDs |

## 25. Pre-production testing checklist

- [ ] Defined “target received”, “accepted”, “committed”, and “confirmed” for each API/protocol.
- [ ] Clients supply a stable `operationId`/idempotency key per business intent.
- [ ] Targets persist idempotency/receipts durably with unique constraints and atomic transactions.
- [ ] Same key + same payload replay returns consistent receipts/statuses.
- [ ] Same key + different payload is clearly rejected.
- [ ] Status lookup or reconciliation policy exists for `UNKNOWN`.
- [ ] Tested cutting **before backend receipt** and verified real target never received it.
- [ ] Tested cutting **after backend receipt, before COMMIT** with deterministic barriers.
- [ ] Tested cutting **after COMMIT, before response** and verified target side effect.
- [ ] Tested proxy dropping responses even after target sent/committed.
- [ ] Tested client crash after receiving receipt and before persisting local result.
- [ ] Tested concurrent same-key requests and target restarts.
- [ ] Verified transparent HTTP retries, response timeouts, and `Retry-After`.
- [ ] Tested transactions and schemas/migrations against real DBs (Testcontainers).
- [ ] Tested producer confirm loss with real brokers and stable `eventId`s.
- [ ] Tested consumer SQL COMMIT + ACK loss with inbox blocking duplicates.
- [ ] Out-of-order events protected by aggregate version guards.
- [ ] Outbox relay implements leases, retry budgets, unknown states, and DLQ/reconciliation.
- [ ] Non-idempotent Redis commands have duplicate-prevention policies.
- [ ] All test gates/latches have timeouts and cleanup.
- [ ] Metrics separate attempted, received, committed, response received, and unknown.
- [ ] No secrets/tokens/PII in logs; no high-cardinality IDs in metric tags.
- [ ] Runbooks exist for `UNKNOWN`, manual review, replays, and compensation.
- [ ] Never equate HTTP 202, publisher ACK, consumer ACK, and SQL COMMIT as one kind of “success.”

**Key takeaway:** **Disconnecting before the target receives a request** may mean the operation never happened; **disconnecting after the target has COMMITTED** can trigger the exact same `IOException` on the client even though business state already changed. The only reliable way to handle this is designing **business-identity contracts, `UNKNOWN` states, server-side idempotency, status lookup/reconciliation, and outbox/inbox**, then deterministically testing those exact failure windows. Timeouts and retries are operational tools—they **never replace proof of business state**.

## References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): idempotent methods, status codes, and HTTP semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP message framing, incomplete messages, and connections.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, response handling, and HTTP interfaces.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): local transaction boundaries.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC, `DataSource`, transactions, and pooling.
- [Spring Retry — Reference](https://docs.spring.io/spring-retry/docs/current/reference/html/): retry policies, backoff, and recoverers.
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): bounded retries and exception classification.
- [OkHttp — MockWebServer](https://square.github.io/okhttp/features/mocking/): deterministic HTTP stubs, faults, and recorded requests.
- [Testcontainers — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network fault injection in integration tests.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): real transaction/unique constraint tests.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/publisher-confirms-returns.html): broker confirms and unroutable messages.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): consumer vs. publisher acknowledgement semantics.
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` producer futures.
- [Spring for Apache Kafka — Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): consumer ACK/offset lifecycles.
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): `acks`, idempotence, and retry/timeout behavior.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): deduplication and at-least-once delivery.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): business transactions and durable publish intents.
