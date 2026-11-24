# Distinguishing timeouts, reconnects, and library-level resume in RSocket

RSocket combines multiple asynchronous interaction models over a long-lived connection: request-response, fire-and-forget, request-stream, and request-channel. When integrating RSocket into Spring Boot, three concepts are frequently conflated into one: **timeout**, **reconnect**, and **resume**. They solve three distinct problems:

- **Timeout**: decides *how long to wait for an operation or signal* before treating it as overdue.
- **Reconnect**: attempts to *establish a new connection/communication session* after the old one drops or fails to connect.
- **Resume**: attempts to *recover the existing RSocket session along with stream state and unacknowledged frames* after a physical disconnect, provided both client and server still hold sufficient state.

This lesson belongs to the **RSocket** chapter of **SPRING_BOOT_INTEGRATION**, a module dedicated to organizing system integrations in Spring Boot via HTTP clients, databases, caches, message brokers, and Spring Integration adapters. Beyond Reactor/RSocket APIs, the lesson clarifies boundaries between transport and business logic, replay safety, transactions, duplicate handling, resource limits, testing, and operational observability.

**Version scope:** Spring configuration examples follow Spring Boot 3.x, Spring Framework 6.x, and rsocket-java 1.x, illustrating APIs of `RSocketRequester.Builder`, `RSocketConnector`, and `RSocketServerCustomizer`. When upgrading Boot/Framework/rsocket-java, verify API signatures against your project's version before applying. Non-Java libraries, or intermediate gateways/brokers, may lack resume support or use different reconnect policies.

## 1. A real-world scenario needing all three concepts

`order-service` opens an RSocket connection to `inventory-service` to query stock levels and receive a stream of inventory updates. Several types of disruptions can occur on the link:

1. `inventory-service` remains connected, yet an SQL query is too slow; one request waits past 800 ms.
2. The TCP or WebSocket connection drops due to a proxy reset, flaky network, or pod eviction.
3. During a brief network outage, the client wants to keep its active inventory watch request-stream alive and receive any missed frames once connectivity returns.

From the client's perspective, all three look like “waiting without receiving data,” yet the remedies differ:

| Incident | Primary mechanism | Desired outcome | What the mechanism does not guarantee |
| --- | --- | --- | --- |
| Single request overdue | Operation-level timeout | Stop waiting and emit error/fallback | Automatically re-establishing connections or rolling back side effects |
| Transport lost and must serve new requests | Reconnect | New RSocket, fresh SETUP, ready for subsequent requests | Preserving old streams or guaranteeing replay |
| Brief transport loss, session state intact | Resume | Reattach to the identified session and continue missed streams/frames | Succeeding after server restart/state loss or storing data indefinitely |
| Caller wants to retry a business command | Request retry | Replay the operation per retry policy | Executing business logic only once without idempotency |

Decision flow:

~~~mermaid
flowchart TD
    A["An RPC/stream encounters an issue"] --> B{"Only the operation timed out?"}
    B -->|Yes| C["Timeout: emit error/cancel; handle unknown outcome"]
    B -->|No: transport lost| D{"Do both sides enable resume and retain session/frames?"}
    D -->|Yes| E["Send RESUME, await RESUME_OK; continue old session"]
    D -->|No/Resume rejected| F["New connection via SETUP if policy allows"]
    F --> G["Business recovery via re-read/re-subscribe/idempotent retry"]
    C --> H["Choose fallback/retry per contract"]
    E --> I["Monitor resumed stream and check SLA limits"]
~~~

The “business recovery” branch here is an **application policy**, not a default protocol effect.

## 2. Layering timeouts: business request, TCP, keepalive, and resume session

In practice, multiple timers exist. Seeing the single word “timeout” in a log does not tell you which timer expired.

### 2.1. Timeout of a request-response

In Spring, `RSocketRequester` returns `Mono<T>` for `request-response`. Callers can apply the Reactor `timeout(Duration)` operator:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public class InventoryClient {
    private final RSocketRequester requester;

    public InventoryClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<StockReply> readStock(String sku) {
        return requester.route("inventory.stock")
                .data(new StockQuery(sku))
                .retrieveMono(StockReply.class)
                .timeout(Duration.ofMillis(800));
    }
}
~~~

`StockQuery` and `StockReply` are application DTOs; the server may use `@MessageMapping("inventory.stock")`. When no response arrives within 800 ms, `timeout` emits an error (typically `TimeoutException`) and cancels the upstream subscription. **Timing out does not prove the server did not execute or commit the transaction.** Cancellation travels over the protocol when possible, yet in-progress DB/HTTP side effects may already have completed.

If the service mutates data, every retry after a timeout requires a stable `requestId` and deduplication constraints. For read-only queries, retries are simpler, though total elapsed time and capacity should still be bounded.

### 2.2. Timeout of a request-stream

For `Flux<T>`, the standard `timeout(Duration)` checks the gap **between consecutive signals** (including waiting for the first signal), not necessarily “the entire stream takes at most X seconds.” For example:

~~~java
public Flux<StockEvent> watchStock(String sku) {
    return requester.route("inventory.watch")
            .data(new StockQuery(sku))
            .retrieveFlux(StockEvent.class)
            .timeout(Duration.ofSeconds(15));
}
~~~

If a stream normally emits one event every few minutes, a 15-second timeout will tear down a healthy stream. Design application-level heartbeat signals, pick timeouts matching legitimate quiet gaps, or use a separate **overall session** deadline if that is the real requirement. An unbounded stream does not inherently have a “final completion response” to time out like a `Mono`.

Remember that Reactor's `timeout` observes silence from the **publisher at the operator's position**. If a pipeline includes `delayElements`, `publishOn`, buffering, or slow operators, the timeout measures time *after* those transformations rather than pure network time.

### 2.3. TCP connect timeout, handshake, and network idle timeout

Before any RSocket stream can run, a transport (such as TCP or WebSocket) must connect and exchange SETUP. Expiring during **connection establishment** is different from timing out an already-sent request.

Places where limits can be configured:

- Reactor Netty client/transport: TCP connect timeout, TLS handshake, proxy handshake, idle handlers (if configured).
- RSocket client setup: an overall bound for obtaining a usable client RSocket.
- Infrastructure: ingress, load balancers, NAT, and service meshes may drop idle connections under their own policies.

Illustrative example with low-level rsocket-java APIs (not `RSocketRequester.Builder`):

~~~java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<RSocket> connected = RSocketConnector.create()
        .connect(TcpClientTransport.create("inventory.internal", 9898))
        .timeout(Duration.ofSeconds(4));
~~~

This snippet applies a **wait limit to the connection/SETUP `Mono`**. To set the TCP connect timeout itself, configure Reactor Netty's `TcpClient` and pass it to `TcpClientTransport` per your version's API. Avoid hardcoding a single “4 seconds” across every environment since internal networks, TLS, proxies, and DNS have different budgets. Libraries emit varying connection exceptions; inspect actual exceptions/statuses rather than catching everything and labeling it a timeout.

### 2.4. RSocket KEEPALIVE is not a request timeout

RSocket includes `KEEPALIVE` frames to verify the peer is alive. rsocket-java provides connector-level configuration:

~~~java
connector.keepAlive(
    Duration.ofSeconds(20),  // KEEPALIVE send interval
    Duration.ofSeconds(90)   // max lifetime without a valid response
);
~~~

At the protocol level, these primary parameters are negotiated in SETUP. If `maxLifeTime` elapses without a valid keepalive acknowledgment, the transport/session can be considered lost. **There is no rule that a business request may take 90 seconds**; bounding a request requires its own timeout. Conversely, a `Mono` timing out after 800 ms does not necessarily break the underlying RSocket connection.

Setting keepalive too aggressively generates unnecessary traffic, especially across thousands of connections. Setting `maxLifeTime` too short causes false positives during GC pauses, congestion, or network jitter. Also align these values with proxy/NAT idle limits.

### 2.5. Resume session duration is not a request timeout either

When resume is enabled, the library retains session state for a window after the transport drops. `sessionDuration` answers: **how long to keep the opportunity to resume the session**. It does not measure business command execution time and does not mean messages are stored durably long-term.

A request waiting 800 ms can time out even while the session remains resumable for 2 minutes. Likewise, a 2-minute resume window can expire while a business request is still pending and must be terminated per policy.

## 3. Reconnect: establishing a new connection without resuming old stream progress

When using **reconnect without resume**, the client creates a fresh RSocket after the previous transport drops. A new SETUP means a new RSocket connection/session. In-flight streams from the old session are not automatically migrated to the new session by the protocol; if data updates are still needed, the application must re-subscribe or query from a cursor.

In rsocket-java, `RSocketConnector.reconnect(Retry)` is the library's option, applying a retry policy to acquire a new connection. Note its behavior: the RSocket is shared/cached while the connection is alive; after a disconnect, subsequent access triggers reconnection.

Example using the rsocket-java API:

~~~java
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import java.time.Duration;
import reactor.util.retry.Retry;

var connector = RSocketConnector.create()
        .reconnect(Retry.backoff(5, Duration.ofMillis(300))
                .maxBackoff(Duration.ofSeconds(5)))
        .keepAlive(Duration.ofSeconds(20), Duration.ofSeconds(90));

var sharedSocket = connector.connect(
        TcpClientTransport.create("inventory.internal", 9898));
~~~

`sharedSocket` here is a `Mono<RSocket>`. Keeping the `Mono` alive, caching the connection, and triggering reconnect on subsequent use belong to **rsocket-java's `reconnect` mechanism**; do not equate it with arbitrary external `retryWhen` calls. Limits like 5 attempts, 300 ms, and 5 seconds are discussion examples, not universal defaults.

The rsocket-java API documentation emphasizes: **`reconnect(Retry)` does not automatically retry failed individual requests**. To retry a request after obtaining a new connection, the request layer still needs an appropriate retry policy.

### Reconnect with Spring RSocketRequester.Builder

Spring Framework exposes the `rsocketConnector(...)` callback for low-level connector configuration:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
public class InventoryRSocketClientConfig {

    @Bean
    RSocketRequester inventoryRequester(RSocketRequester.Builder builder) {
        return builder
                .rsocketConnector(connector -> connector
                        .keepAlive(Duration.ofSeconds(20),
                                Duration.ofSeconds(90))
                        .reconnect(Retry.backoff(
                                5, Duration.ofMillis(300))
                                .maxBackoff(Duration.ofSeconds(5))))
                .tcp("inventory.internal", 9898);
    }
}
~~~

This configuration enables **reconnect**, not resume. The Spring Boot auto-configured `RSocketRequester.Builder` comes with codecs and Spring Messaging integration; target the desired service with it. Depending on how the builder initializes and establishes connections, bean creation might require the server to be reachable; design readiness/lazy initialization if startup must not depend on an online backend.

An application might retry only *read-only* RPCs on transient transport failures:

~~~java
import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<StockReply> readWithRetry(RSocketRequester requester, StockQuery query) {
    return requester.route("inventory.stock")
            .data(query)
            .retrieveMono(StockReply.class)
            .retryWhen(Retry.backoff(2, Duration.ofMillis(250))
                    .filter(error -> isTransientConnectionFailure(error)))
            .timeout(Duration.ofSeconds(2));
}
~~~

`isTransientConnectionFailure(Throwable)` is an **application-written error classifier** tailored to the exceptions/statuses of your stack; never assume every exception is retryable. `ConnectionErrorException` is an example rsocket-java connection error; check whether Spring/Reactor wraps it in practice. Retry counts must fit within an overall time budget to avoid “5 reconnects × 2 request retries × 3 service hops” multiplying attempts exponentially.

**Design principle:** the connector retries the connection, while the request layer decides *whether the business operation may be resent*. If the request is `reserveInventory`, retrying after a timeout can double-reserve stock unless idempotency is enforced.

### What happens to an active stream without resume?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SETUP (connection A)
    C->>S: REQUEST_STREAM watchStock
    S-->>C: Event #101
    S-->>C: Event #102
    Note over C,S: Connection A transport drops
    C->>S: SETUP (connection B - reconnect)
    Note over C,S: Stream on A does not automatically survive onto B
    C->>S: REQUEST_STREAM watchStock(afterVersion=102)
    S-->>C: Event #103 from cursor-backed source
~~~

`afterVersion` here is an application contract requiring the server to have an event store capable of resuming reads. Reconnect only restores the transport pipe; all checkpointing, deduplication, and gap recovery belong to the application.

## 4. Resume: recovering an RSocket session when both sides retain state

**Resumption** is an *optional* feature of the RSocket protocol. It targets temporary transport drops while both client and server **still retain session state**. When resume is negotiated during SETUP, both sides track unacknowledged frames and received frame positions.

Once a new physical transport connects for recovery, the client sends **`RESUME`** with the resume identification token and last received frame position; the server checks the token, position, session, and retained buffers:

- If valid, the server replies with **`RESUME_OK`** and the required position. Both sides replay unacknowledged frames from that position and continue existing streams.
- If recovery is impossible, the server returns **`REJECTED_RESUME`** (or an appropriate connection error). The client must handle session loss per policy rather than pretending old streams survived.
- If the outage lasts too long or frame buffers lack history to align positions, resume fails.
- If a server restart wipes in-memory sessions/tokens/frame stores, resume normally **has no foundation** to recover. Survival across process crashes is not guaranteed.

~~~mermaid
sequenceDiagram
    participant C as Client + resume state
    participant S as Server + resume state
    C->>S: SETUP (resume requested, token)
    C->>S: REQUEST_STREAM
    S-->>C: PAYLOAD E1
    Note over C,S: TCP/WebSocket lost, but session remains in memory
    S--xC: PAYLOAD E2 not yet acknowledged by client
    C->>S: New transport + RESUME(token, lastReceivedPosition)
    S-->>C: RESUME_OK(lastReceivedPosition)
    S-->>C: Replay missing frame E2
    S-->>C: PAYLOAD E3 (stream continues)
~~~

*Frame positions* and *resume tokens* are protocol artifacts. Never design business logic around “every frame is received exactly once” while ignoring crashes/timeouts of business side effects: resume does not turn the system into an exactly-once transaction.

### Conditions required for resume to succeed

| Condition | Consequence when missing |
| --- | --- |
| Both client and server enable/support resume | Cannot negotiate a resumable session |
| Valid resume token and server session not evicted | `REJECTED_RESUME` or connection error |
| Client/server retain sufficient frame buffers for unacked positions | Cannot reconstruct a consistent frame stream |
| Still within session duration/policy | Session may have expired |
| New transport reaches the server holding that session | Requires session affinity or supported shared session state |
| Business publisher/handler remained active while transport was down | Resume cannot recreate canceled application state |

In multi-replica deployments, a client may reconnect to a different pod lacking the resume session. Without appropriate session routing/state handling, resume fails even when the old pod is still alive. “Having a load balancer” does not imply “cross-pod resume.”

### Resume is not a message broker

RSocket resume is meant for an **active session** keeping frame state for a bounded window. It does not provide durable subscriptions, dead-letter queues, persistent event logs, or historical replay. If an app must reliably receive events after an hour of downtime or a server restart, use application storage, a broker, or an event log with offsets/cursors. Reconnect paired with querying from a durable source can then satisfy the SLA.

## 5. Enabling resume with rsocket-java and Spring Boot

Several low-level rsocket-java APIs provide direct support:

- `RSocketConnector.resume(Resume)` on the client.
- `RSocketServer.resume(Resume)` on the server.
- `Resume.sessionDuration(Duration)` and `Resume.retry(Retry)` to control session lifetime and resume retries (version-dependent).
- Spring Boot's `RSocketServerCustomizer` to configure the `io.rsocket.core.RSocketServer` instance before startup.

**Never enable resume on one side only.** Brokers/gateways/drivers may also lack resume support even if the app-side client and server expose the API. Verify at runtime.

### 5.1. Configuring the Spring Boot RSocket server

Basic Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-rsocket</artifactId>
</dependency>
~~~

Declare a standalone RSocket TCP port using Spring Boot configuration:

~~~yaml
spring:
  rsocket:
    server:
      port: 9898
      transport: tcp
~~~

`spring.rsocket.server.port` tells Boot to launch a standalone server; WebFlux WebSocket deployments require separate properties like `mapping-path`. Broker/proxy setups must align TCP vs. WebSocket transport, TLS, and routes.

To enable server-side resume using a customizer bean (applicable to Spring Boot 3.x and rsocket-java 1.x):

~~~java
import io.rsocket.core.Resume;
import java.time.Duration;
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RSocketServerResumeConfig {

    @Bean
    RSocketServerCustomizer enableResumeOnServer() {
        return server -> server.resume(
                new Resume()
                        .sessionDuration(Duration.ofMinutes(2))
        );
    }
}
~~~

`RSocketServerCustomizer` beans apply to the Boot-managed server. If the server is constructed manually or managed by another starter, this customizer may not take effect; verify your actual infrastructure setup.

**Caution:** longer `sessionDuration` values retain more sessions/frames in memory and raise resource-exhaustion risk when many clients disconnect. Verify frame buffer bounds, session caps, and eviction/cleanup policies against your running rsocket-java API; do not bump 2 minutes to 30 minutes assuming it is free.

### 5.2. Configuring the Spring RSocketRequester client with resume

The client must also enable resume on its **connector**, using the same transport to the server:

~~~java
import io.rsocket.core.Resume;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
public class RSocketResumeClientConfig {

    @Bean
    RSocketRequester resumableInventoryRequester(
            RSocketRequester.Builder builder) {

        return builder
                .rsocketConnector(connector -> connector
                        .keepAlive(Duration.ofSeconds(20),
                                Duration.ofSeconds(90))
                        .resume(new Resume()
                                .sessionDuration(Duration.ofMinutes(2))
                                .retry(Retry.backoff(
                                        8, Duration.ofMillis(300))
                                        .maxBackoff(Duration.ofSeconds(4)))))
                .tcp("inventory.internal", 9898);
    }
}
~~~

This configuration is an **alternative** to the `reconnect(Retry)` bean in section 3. Do not deploy both expecting automatic “resume then fallback to reconnect.”

Per the rsocket-java 1.x `RSocketConnector` API, **`reconnect(Retry)` and `resume(Resume)` are mutually exclusive**; if both are set, resume takes precedence. Therefore chaining:

~~~java
connector.reconnect(reconnectPolicy)
         .resume(new Resume().retry(resumePolicy));
~~~

**does not mean** the library tries resume first and automatically falls back to reconnect on session expiration. If resume is rejected or expires, the application must decide to establish a fresh requester/connection via SETUP and recover business state from a checkpoint. Never assume automatic fallback unless verified in your exact library version.

### 5.3. Do not reuse the wrong identity/continuation token

A resume token is a protocol-level session identifier, **not** an `orderId`, `userId`, or business operation idempotency key. Never treat the token as arbitrary reusable business data. When a new session is required, run a fresh protocol SETUP and recover business progress via stored cursors rather than fabricating tokens to mimic old sessions.

In multi-replica deployments, ensure `RESUME` frames route to the endpoint holding the session. Options like sticky sessions or distributed state must be evaluated against **real library/broker capabilities**, not merely ingress routing rules.

## 6. Protocol, library API, and application policy are three distinct layers

It is easy to read an API named `retry` or `timeout` and assume identical behavior everywhere:

| Layer | API/concept | Direct effect | Does not guarantee |
| --- | --- | --- | --- |
| Reactor | `Mono.timeout(Duration)` | Expires waiting for a publisher signal/result | Reconnect or SQL rollback |
| Reactor | `Flux.timeout(Duration)` | Errors when inter-signal silence exceeds limit | Fixed total stream lifetime |
| Reactor | `retryWhen(Retry)` | Re-subscribes to publisher after matching errors | Idempotency or preserving old stream |
| RSocket protocol | SETUP/KEEPALIVE | Connection initialization/liveness | Every request finishing before deadline |
| rsocket-java | `RSocketConnector.reconnect(Retry)` | Acquires a new RSocket connection per retry | Automatic per-request retries or old streams |
| RSocket protocol | RESUME/RESUME_OK | Attempts to resume a negotiated session | Success if frames/session are lost |
| rsocket-java | `RSocketConnector.resume(Resume)` | Enables/retries transport resume for old session | Automatic fallback to new SETUP on resume failure |
| Spring Boot | `spring.rsocket.server.*`, customizers | Starts/configures RSocket server | Per-route SLAs or exactly-once |
| Application | Deadlines, cursors, inbox, outbox | Enforces business guarantees | Working automatically without persistent state/stores |

Another common pitfall is that publisher-level `retryWhen` **re-subscribes to a request-producing source**. For request-response, this usually **re-sends the request**. For streams, retrying after an error can open a brand-new stream from the beginning; without a cursor, the client may receive duplicates or miss events.

### Three distinct semantics when handling request-stream

~~~mermaid
flowchart LR
    A["Stream A running"] --> B{"Transport lost"}
    B --> C["Plain reconnect"]
    C --> D["Stream A errors; app opens new stream B"]
    B --> E["Resume succeeds"]
    E --> F["Keeps logical session and continues stream A frames"]
    B --> G["Resume fails"]
    G --> H["Read checkpoint then open new stream if needed"]
~~~

Business data cannot be protected merely by picking one of these three branches: consumers still need version/sequence checks and deduplication during replays or re-publishes.

## 7. End-to-end design for operations with side effects

Suppose `inventory-service` handles an RSocket `reserveStock` request and decrements SQL stock. The client may time out after the server commits yet before receiving the response, or reconnect and resend the command. Guaranteeing a single logical effect requires an **idempotency key**.

Example application DTOs:

~~~java
public record ReserveCommand(
        String requestId,
        String orderId,
        String sku,
        int quantity
) {}

public record ReserveResult(
        String reservationId,
        String status
) {}
~~~

The server uses a database transaction recording the result under `(callerId, requestId)` alongside the stock update. Illustrative table:

~~~sql
CREATE TABLE inventory_command_receipts (
    caller_id         VARCHAR(120) NOT NULL,
    request_id        VARCHAR(120) NOT NULL,
    reservation_id    VARCHAR(120) NOT NULL,
    result_status     VARCHAR(40) NOT NULL,
    created_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (caller_id, request_id)
);
~~~

Processing sequence:

1. Authenticate caller and validate command.
2. Start SQL transaction.
3. Insert receipt keyed by `callerId + requestId` with a unique constraint; if already present, return the recorded outcome without decrementing stock again.
4. Update inventory and reservation in the same transaction, then commit.
5. Return response; if the response is lost due to timeout/disconnect, the client can retry with the same `requestId` to retrieve the same receipt.

Handle concurrent races with the same ID at the database level rather than an unlocked `SELECT`-then-`INSERT`. If the command also publishes broker events, consider a **transactional outbox** to keep SQL commits consistent with event publishing. RSocket resume does not replace transactions or an outbox.

### Do reconnect and resume share the same business idempotency requirements?

Yes. Resume reduces the need to open new streams/requests when **session recovery succeeds**, yet cannot cover every failure: sessions may be rejected, callers may time out, or servers may finish side effects before confirmations reach the client. Side-effecting business commands therefore still require idempotency and status reconciliation.

For instance, generate `requestId` once at the start of the business workflow and keep it constant across retries; never generate a fresh UUID inside `Mono.defer` on every `retryWhen` subscription if targeting the exact same command.

## 8. Configuring strategies by SLA rather than one magic number

Suppose a `checkout` API has a 2-second budget and `inventory-service` normally has a 120 ms p99:

| Mechanism | Example setting | Practical meaning | What to observe |
| --- | --- | --- | --- |
| Request timeout | 600–800 ms | Max wait for one inventory call within checkout budget | Timeout rate, p95/p99 latency |
| Connection setup timeout | 2–4 seconds | Time allowed to establish session on startup/access | Connect latency, DNS/TLS errors |
| Keepalive interval | 20 seconds | Periodic peer liveness probe | Keepalive send/ack, false positives |
| Keepalive max lifetime | 90 seconds | Tolerance before declaring peer unresponsive | Connection close reasons |
| Reconnect delay | Backoff 300 ms to a few seconds | Back off when server is unhealthy | Attempt count, reconnect success |
| Resume window | e.g., 2 minutes | Window during which session recovery is attempted | Resume success/reject, session count, buffered bytes |
| Business retry | 0–2 attempts, filtered | Improves success on safe operations | Retry amplification, duplicate suppression |

These numbers **illustrate how to reason about budgets**; do not copy them blindly as universal production defaults. They may also conflict if uncoordinated: for example, keepalive detects a dead link only after 90 seconds while request timeout is 800 ms; the client must handle request timeouts immediately instead of waiting for keepalive to declare the transport dead.

### Layering the time budget

If an endpoint has a 2-second total budget, do not grant 2 seconds to each consecutive downstream call. Allocate budgets separately to the inventory call and subsequent steps per SLA. Scope `timeout` appropriately:

~~~java
Mono<CheckoutResult> checkout(CheckoutCommand command) {
    return checkInventory(command)
            .timeout(Duration.ofMillis(700))
            .flatMap(stock -> reserveAndPay(command, stock))
            .timeout(Duration.ofMillis(1800)); // pipeline budget
}
~~~

This example illustrates per-step and overall flow limits; `checkInventory` and `reserveAndPay` are application methods. In production, propagating an absolute deadline in metadata avoids resetting budgets across service hops. Also account for thread scheduling, serialization, DB, TLS/transport, and response transmission.

## 9. Testing failure modes by observable behavior

Unit-testing `timeout` differs from integration-testing reconnect/resume: resume requires **two endpoints, frame state, and a real transport** to observe `RESUME`/`RESUME_OK`. Use Reactor `StepVerifier` with `VirtualTimeScheduler` for publisher timeout logic; for reconnect/resume, run integration tests over TCP/WebSocket and simulate network cuts without killing the process (and separately test process-kill scenarios).

| Test case | How to trigger | Expectation |
| --- | --- | --- |
| Slow request, healthy connection | Handler responds after 800 ms timeout | `Mono` times out/cancels; connection need not be rebuilt |
| Stream silent for 15 seconds | Stop emitting payloads | `Flux.timeout` errors after inter-signal gap |
| TCP unreachable | Stop listener or block port | Connect timeout/failure per transport policy |
| Transport lost, reconnect enabled | Cut TCP and issue new call after server returns | Fresh SETUP, new request succeeds; old stream does not auto-recover |
| Transport lost, resume on both ends | Brief network cut keeping both processes/states alive | `RESUME_OK` possible; unacked streams/frames continue |
| Resume disabled on server | Client requests resume | Setup/resume rejected per library/protocol behavior |
| Outage longer than session policy | Cut network past window | Resume rejected/expired; application recovery triggers |
| Server restarts during outage | Restart wipes session store | Do not expect resume to succeed on the new process |
| Resume hits wrong pod | Load balancer routes to another pod | Likely rejected due to missing token/session |
| Retry command after timeout | Client resends with same `requestId` | Only one stock change; consistent receipt returned |
| Multi-layer retries | Retries enabled on requester and downstream services | Total attempts stay bounded with no retry storm |
| Frame buffer full | Brief transport drop while producer emits fast | Resource policy rejects resume or applies backpressure as configured |

### Which test truly proves resume?

A proper test verifies that **the same logical stream** continues after a transport break, not merely that the client can connect again. Evidence should show:

- A token/session negotiated at SETUP (never log raw secret tokens in production).
- A **RESUME** attempt with the server returning **RESUME_OK**.
- Interrupted frames exchanged per protocol without a fresh SETUP replacing the old session.
- Received data preserves contract ordering/versions without uncontrolled application duplicates.

Conversely, a test checking only “after restoring the network, the API call succeeds” is likely measuring **reconnect** rather than **resume**.

## 10. Operational observability and troubleshooting

Log and meter three distinct layers:

| Layer | Recommended metrics and logs | Question to answer |
| --- | --- | --- |
| Application timeout | `route`, `duration`, `timeoutType`, `requestId` | Is the route slow due to DB or downstream? |
| Transport/keepalive | Connection opens/closes, keepalive misses, close reason | Flaky network, proxy idle reap, TLS? |
| Reconnect | Attempt count, backoff duration, new SETUP successes | How long does establishing a new connection take? |
| Resume | `RESUME` attempts, `RESUME_OK`, `REJECTED_RESUME`, session expirations | Are sessions and frames still intact? |
| Frame/session store | Buffered bytes, active/disconnected sessions, evictions | Risk of memory exhaustion? |
| Stream | Active streams, reconnect/re-subscribe counts, cursor gaps | Did streams resume or open anew? |
| Business idempotency | Duplicate command counts, receipt hits, conflicts | Are side effects being duplicated? |

On dashboards, separate **RPC timeouts** from **reconnect attempts** and **resume success rate**. Spiking timeouts may point to overloaded SQL while connections remain completely healthy. Conversely, climbing reconnects with low timeouts can indicate a proxy reaping idle connections. If resume rejections jump after scaling pods, check session affinity/state loss before extending the resume window.

Never log sensitive full payloads, authentication tokens, resume tokens, or customer PII. Use correlation IDs, trace IDs, and message/request IDs per contract. Business trace spans may span multiple RSocket connections; never equate one TCP connection with one business transaction.

### Short diagnostic procedure

1. Identify whether the error came from a Reactor timeout operator, TCP/handshake, keepalive, or protocol resume.
2. Inspect `route`, interaction type (response/stream/channel), elapsed time, and subscription state.
3. On reconnect, check which SETUP was used on the new connection and whether prior requests were replayed.
4. On resume, verify both client and server enabled it, session is still alive, frame buffers sufficed, and `RESUME_OK` occurred.
5. Check SQL/business outcome by request ID before re-running any side-effecting command.
6. Tune SLAs, retries, timeouts, or frame retention based on tests/metrics; re-verify load and memory after changes.

## 11. Frequently confused design questions

**“With `Mono.timeout` configured, do we still need `RSocketConnector.reconnect`?”**

Likely yes, if the app must serve new requests after a transport drop. `Mono.timeout` only bounds publisher waiting; it does not establish a new connection. Still, enabling reconnect without idempotency risks duplicating write operations.

**“With RSocket keepalive enabled, can requests still time out?”**

Yes. Keepalive checks peer liveness; business requests can still stall on slow queries or downstream calls. Configure per-route/SLA timeouts independently of keepalive.

**“After a successful reconnect, do old request-streams resume automatically?”**

No under plain reconnect semantics. A new connection starts a new session; the application must open a new stream and use cursors/versions to fetch missed events.

**“Is enabling resume on the client sufficient?”**

No. The server and every hop in the path must support resume, and sessions/tokens/frame stores must remain intact. Server restarts or routing to another pod without session state typically break resume.

**“Should we enable both `resume` and `reconnect` on the same `RSocketConnector` to get both?”**

In rsocket-java 1.x, the two settings are mutually exclusive and **resume takes precedence**. If fallback after resume failure is required, implement an explicit recovery strategy, verify your exact version's behavior, and restore business state cleanly.

**“Does resume guarantee zero event loss if the app is offline all day?”**

No. Resume relies on finite session state and in-memory frame buffers; if durable retention is needed, use an event log/broker or replayable storage.

**“Once `REQUEST_FNF` is sent, can we treat the operation as succeeded?”**

You cannot infer side-effect completion from sending a frame or client-side completion. Fire-and-forget returns no confirming business reply. If confirmation is required, use an interaction with acknowledgments/receipts or durable persistence patterns.

### Mechanism selection table

| Practical goal | Recommended approach |
| --- | --- |
| Prevent request-response from waiting forever | `Mono.timeout` + application timeout budget |
| Detect dead connections when idle | `KEEPALIVE`/lifetime and/or transport idle policy |
| Keep serving **new** requests after network loss | `RSocketConnector.reconnect(Retry)` + request-layer recovery |
| Preserve streams/frames of an **existing** session across brief drops | `RSocketConnector.resume(Resume)` + server resume with sufficient session/frame state |
| Receive every event across restarts/long outages | Broker/event store + cursors/offsets + retries + idempotency |
| Prevent duplicate execution of writes after timeout/retry | Stable `requestId`, unique receipts, transactions/outbox |

## 12. Production readiness checklist

- Clearly define which timeout is being configured: request deadline, event gap, connect/handshake, keepalive lifetime, or resume session window.
- Choose **reconnect or resume** based on real rsocket-java/server capabilities and requirements, not API names.
- Configure retry backoff, max attempts, overall deadlines, and concurrency caps to prevent retry storms.
- If using resume, confirm both sides support it, validate session duration, frame buffer sizing, load-balancer routing, and server-restart behavior.
- For streaming, maintain cursors/checkpoints and storage-backed recovery when resume cannot continue.
- For side-effecting requests, apply idempotency keys and transactions; when brokers are involved, consider an outbox.
- Test over real transports across short/long outages, session affinity, rejected resume, and post-timeout idempotency.
- Include timeouts/reconnects/resumes in metrics, traces, sanitized logs, and capacity planning.

### Technical references for version verification

- [Spring Boot Reference – RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): server configuration, `RSocketRequester.Builder`, and auto-configuration.
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, routing, and `rsocketConnector` callbacks.
- [rsocket-java – RSocketConnector source](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): exact semantics of `reconnect(Retry)`, `resume(Resume)`, and keepalive; inspect the release tag matching your runtime version.
- [RSocket Protocol – Resuming Operation](https://rsocket.io/about/protocol/): SETUP, KEEPALIVE, RESUME, RESUME_OK, REJECTED_RESUME, and protocol limits.

**Key takeaway:** **timeout** stops waiting for a signal/operation; **reconnect** builds a new connection/session; **resume** attempts to salvage an existing session using retained frame/stream state. None of these mechanisms automatically provides exactly-once business semantics or durable event storage across all outages. Design timeouts, retries, and state recovery around the data contracts, transactions, and SLAs of your actual Spring Boot system.
