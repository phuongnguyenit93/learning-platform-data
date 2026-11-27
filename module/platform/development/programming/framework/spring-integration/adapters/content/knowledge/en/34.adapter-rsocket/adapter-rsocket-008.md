# Reconnect and resume in RSocket Adapter

## 1. Context: connections can drop mid-message processing

In module **SPRING_INTEGRATION_ADAPTERS**, applications connect external systems with Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`. With **RSocket Adapter**, connections are often long-lived to exchange request-response, fire-and-forget, or continuous data streams. What happens if a client's Wi-Fi drops for three seconds, a server node restarts, or a load balancer closes a connection with an in-flight request?

Suppose an inventory app uses route `inventory.events` to receive inventory changes:

~~~text
Client                              RSocket Server
  |---- SETUP -------------------------->|
  |---- REQUEST_STREAM inventory.events>|
  |<---- Event #101 ---------------------|
  |<---- Event #102 ---------------------|
  |             DISCONNECTED             |
  X-------------------------------------X
  |        Connection restored?          |
  |        What about Event #103, #104?  |
~~~

Three questions must be separated:

1. **Is the connection still alive?** Involves transport, RSocket KEEPALIVE, and failure detection.
2. **Can the interrupted session/stream continue?** Involves **resume** capability at the RSocket layer.
3. **Is business data or an operation lost, duplicated, or executed twice?** Involves **application-level idempotency, progress tracking, and durable storage**.

The **Reconnect and resume** lesson explains these three questions in the context of Spring Integration adapters/gateways. After this lesson, you can:

- Distinguish transport reconnect, request retry, and RSocket session resume.
- Configure reconnection policies with `RSocketRequester` and resume mechanisms when both sides support them.
- Know the conditions under which resume succeeds or gets rejected.
- Design consumers/producers and message flows that tolerate network drops without unintended business side effects.
- Build test scenarios for network cuts, server restarts, expired session lifetimes, and duplicate requests.

## 2. From TCP to business logic: recovery layers

| Layer | Failure | Handling | Not guaranteed |
| --- | --- | --- | --- |
| Transport | TCP/WebSocket closed, timeout | Open a new transport | In-flight requests automatically complete |
| RSocket connection | Old `SETUP` no longer usable | **Reconnect** to create a new connection/session | Old streams continue automatically |
| RSocket session | Transport lost yet both sides still hold state | **Resume** if negotiation and frame storage succeed | DB transactions ran only once |
| Reactor Publisher | `Mono`/`Flux` terminates with error | Conditional `retryWhen` or re-subscription | Retrying every operation is safe |
| Spring Integration | Incomplete message/missing reply | Error flows, idempotent receivers, progress tracking, message stores | In-memory channels become durable queues |
| Business | Command processed yet reply lost | Idempotency keys, uniqueness, transactions, status queries | RSocket deduplicates business actions |

**Reconnect** and **resume** are two distinct strategies. Reconnect opens a new connection/session for subsequent operations. Resume tries to attach a new transport to **the same RSocket session whose state is still retained**, then exchanges frame positions to retransmit missing frames.

In rsocket-java, `RSocketConnector.reconnect(Retry)` and `RSocketConnector.resume(Resume)` are **mutually exclusive modes**; if both are configured, resume takes precedence. Do not assume declaring both gives automatic fallback from resume to reconnect.

## 3. Detecting lost connections: KEEPALIVE and timeouts

RSocket provides `KEEPALIVE` frames to probe connection health. The sender can configure:

- **`keepAliveInterval`:** interval between KEEPALIVE frames.
- **`maxLifeTime`:** maximum allowed time before considering the peer unresponsive.

In rsocket-java, this can be configured on `RSocketConnector` from Spring:

~~~java
import java.time.Duration;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.keepAlive(
            Duration.ofSeconds(20),
            Duration.ofSeconds(90)
        )
    )
    .tcp("localhost", 7000);
~~~

These are illustrative parameter choices, not mandatory values for every environment. Base them on network latency, proxy/load balancer settings, server resources, and desired failure detection speed.

**KEEPALIVE is neither reconnect nor resume.** It detects an unhealthy connection. Too short a timeout triggers false disconnects on jittery networks; too long a timeout delays failure detection. OS-level TCP keepalive and RSocket KEEPALIVE are also separate mechanisms.

### Situations that can sever a connection

| Situation | Symptoms to observe | Recoverability |
| --- | --- | --- |
| Mobile switches networks, brief Wi-Fi drop | Transport drops; client process alive | Can resume if server still holds session |
| Proxy/LB closes idle connection | Transport terminates or times out | Check idle timeouts, KEEPALIVE, resume |
| RSocket server restarts | In-RAM sessions wiped | Normally must open new session; resume typically rejected |
| Client killed | Client subscriptions and state lost | Must open new session, recover progress from durable storage |
| Server running, yet handler throws business error | Stream/request gets `onError` signal | Do not reconnect solely for validation/business errors |
| Disconnected longer than session retention | Session/frame store expired | Resume may fail; application recovery policy required |

## 4. Reconnect: creating a new connection to keep handling requests

In Spring Framework 6, `RSocketRequester.Builder.tcp(...)` builds a requester using a **shared connection**, establishing it when requests occur and able to re-establish it for subsequent requests after the old connection drops. This does **not** mean in-flight request-responses or old request-streams replay automatically when resume is off.

In rsocket-java, the lower-level `RSocketConnector.reconnect(Retry)` API configures the reconnection policy. Once a connection dies, the next subscription acquires a new `RSocket`; downstream requests still need separate retry logic if failed operations should re-run.

### 4.1. Configuring reconnect on Spring RSocketRequester

The following example uses Spring Boot 3 / Spring Framework 6 / rsocket-java 1.1.x:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

@Configuration
class InventoryRSocketClientConfig {

    @Bean
    RSocketRequester inventoryRequester(RSocketRequester.Builder builder) {
        return builder
            .rsocketConnector(connector -> connector
                .keepAlive(
                    Duration.ofSeconds(20),
                    Duration.ofSeconds(90)
                )
                .reconnect(
                    Retry.backoff(5, Duration.ofMillis(500))
                        .maxBackoff(Duration.ofSeconds(8))
                        .jitter(0.3)
                )
            )
            .tcp("localhost", 7000);
    }
}
~~~

Meaning:

- `RSocketRequester.Builder` configures Spring codecs, MIME types, and request routing.
- `rsocketConnector(...)` exposes customization of the rsocket-java connector.
- `reconnect(Retry.backoff(...))` sets the retry policy when acquiring a new connection via the connector.
- `keepAlive(...)` detects unresponsive peers.
- `tcp(...)` creates a requester for the RSocket server; the app can send many requests over one connection.

The retry count here is **bounded**, preventing an unmanageable infinite connection loop. Long-running systems may pick another policy with load caps, error observability, and cancellation support. Backoff with jitter mitigates thundering-herd reconnects when a server recovers.

### 4.2. Reconnect does not mean retrying requests safely

Suppose the client sends an order-creation command, the server writes the order to the DB, and the link drops before the reply reaches the client:

~~~text
Client                     Server                Database
   |--- createOrder #A ----->|                       |
   |                         |---- INSERT order ---->|
   |                         |<--- COMMIT -----------|
   X--- connection lost -----X                       |
   |                                                 |
   |-- reconnect (new session) ---------------------> |
   |-- resend createOrder #A? ----------------------->|
~~~

If the client resends the command when the server lacks idempotency, an order can be created **twice**. A new connection only lets you exchange more messages; it does not tell you whether the prior transaction committed.

For **read-only operations without side effects**, retrying after transport errors can be appropriate. For example, `orders.status`:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.Exceptions;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderQuery(String orderId) {}
record OrderStatus(String orderId, String status) {}

class OrderStatusClient {
    private final RSocketRequester requester;

    OrderStatusClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<OrderStatus> lookup(String orderId) {
        return Mono.defer(() -> requester
                .route("orders.status")
                .data(new OrderQuery(orderId))
                .retrieveMono(OrderStatus.class))
            .timeout(Duration.ofSeconds(3))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(300))
                    .filter(this::isRetryable)
            );
    }

    private boolean isRetryable(Throwable failure) {
        Throwable unwrapped = Exceptions.unwrap(failure);
        return unwrapped instanceof IOException
            || unwrapped instanceof TimeoutException;
    }
}
~~~

`Mono.defer` ensures each subscription/retry creates a fresh request publisher. `retryWhen` here applies to **`lookup`**, not every route; overall timeouts and exception classification must be tuned to your system. RSocket errors may be wrapped in other exceptions; `isRetryable` only illustrates **error filtering**, not an exhaustive detector for all network errors. In production, classify real exceptions and never retry validation, authentication, or permanent business errors.

**Never copy this retry logic verbatim to `orders.create`, fund transfers, or payment recording** without idempotency keys and server-side deduplication.

## 5. Resume: continuing an existing RSocket session

**RSocket Resume** is an optional protocol feature. When transport drops, applications can retain logical connection state and protocol-unacknowledged frames. The client opens a new transport and sends a resume request; if the server still holds the matching session, both sides reconcile byte/frame positions and retransmit missing frames.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SETUP (resume enabled, token=T)
    C->>S: REQUEST_STREAM inventory.events
    S-->>C: PAYLOAD event #101
    S-->>C: PAYLOAD event #102
    Note over C,S: Transport interrupted, both sides still hold session state
    C->>S: New transport + RESUME(token=T, positions)
    S-->>C: RESUME_OK(last received position)
    Note over C,S: Retransmit missing frames if stored data suffices
    S-->>C: Continue PAYLOAD
~~~

This diagram shows a **successful resume**. It does not mean events were written to a database, forwarded to Kafka, or confirmed at the business layer.

### 5.1. Mandatory preconditions

1. The client requested resume support at initial session setup (`SETUP` with resume flag and token).
2. The server **enables and accepts resume**, not merely supporting standard RSocket request-response.
3. Client and server still hold the **old session state** and sent/received frame positions.
4. Frames needing retransmission still exist in the **frame store** and the session has not expired.
5. The client reconnects to an instance able to locate that session by token. With multiple server instances, arbitrary node routing fails if state lives only in local RAM.
6. Session attributes such as data MIME type, metadata MIME type, and encoding format **have not changed** between the original session and resume.

Resume is a conditional recovery effort; the client must always handle resume failure.

### 5.2. RESUME, RESUME_OK, and REJECTED_RESUME

| Frame/signal | Meaning |
| --- | --- |
| `SETUP` with resume flag/token | Client requests a resumable session from the start |
| `RESUME` | Client proposes continuing the session over a new transport with token and received position |
| `RESUME_OK` | Server accepts and returns the position received from the client |
| `ERROR[REJECTED_RESUME]` | Server rejects resumption: unknown token, expired state, or frames unavailable |
| `KEEPALIVE` | Monitors connection health and helps track protocol-level receive progress |

When receiving `REJECTED_RESUME`, do not keep retrying resume indefinitely with the rejected session. Switch to **creating a new session**, and decide whether to query state or recover data using business checkpoints.

### 5.3. Frame positions differ from business checkpoints

RSocket uses send/receive positions of resumable frames to determine what must be retransmitted. This is a **protocol-layer** mechanism. If the application received an event without committing processing, frame positions do not indicate the data was persisted.

Example:

~~~text
Frame event #102 arrived at client
  -> Consumer decoded
  -> Spring Integration received message
  -> Database transaction not yet COMMITTED
  -> Disconnected
~~~

A successful resume does not automatically redo a DB transaction broken at the final step. To guarantee business effects, you need an application-level checkpoint/idempotency key or a durable-offset event source with replay.

## 6. Configuring resume on server and client

In rsocket-java, `io.rsocket.core.Resume` configures resume. By default this feature is **disabled** on `RSocketConnector` and `RSocketServer`. Below illustrates configuring it with Spring Boot 3; bean setup may need adjustment if creating servers manually or using different library versions.

### 6.1. Server: enabling resume via customizer

~~~java
import io.rsocket.core.Resume;
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RSocketServerResumeConfiguration {

    @Bean
    RSocketServerCustomizer enableResume() {
        return server -> server.resume(new Resume());
    }
}
~~~

With a Spring Boot-managed RSocket TCP server, transport properties must still be present:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

`RSocketServerCustomizer` receives `io.rsocket.core.RSocketServer`, and `server.resume(new Resume())` enables resumable sessions on the server. **Enabling this bean does not guarantee every request will resume**: the server must retain sessions/frames long enough, the client must also enable resume, and the load balancer must route to the node holding that session.

### 6.2. Client: enabling resume from SETUP

~~~java
import io.rsocket.core.Resume;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketRequester;

@Configuration
class RSocketResumeClientConfiguration {

    @Bean
    RSocketRequester resumableRequester(RSocketRequester.Builder builder) {
        return builder
            .rsocketConnector(connector ->
                connector.resume(new Resume())
            )
            .tcp("localhost", 7000);
    }
}
~~~

The client can continue using Spring routes:

~~~java
Flux<InventoryEvent> events = resumableRequester
    .route("inventory.events")
    .data(new InventorySubscription("warehouse-a"))
    .retrieveFlux(InventoryEvent.class);
~~~

Here `InventoryEvent` and `InventorySubscription` are **illustrative DTOs**. In real programs, define them per your payload contract and chosen codecs. The example omits arbitrary `retryWhen` because retrying a `Flux` after an error can start a **new subscription**, distinct from resuming the old subscription.

### 6.3. Settings to review in operations

`Resume` and your specific rsocket-java version's connector expose settings for:

- **Session duration:** timeout before a session is no longer resumable.
- **Resume retry/backoff:** how often and when to attempt reopening the transport.
- **Resume token:** identifier unique enough for the server to locate the old session.
- **Frame store:** stores frames that may need retransmission; memory and retention must be bounded.
- **Keepalive:** detects disconnects before exceeding the application's wait budget.

Never apply one hardcoded numeric configuration across all servers. When sizing timeouts and frame stores, account for stream volume, outage bandwidth, event emission rate, concurrent clients, and memory usage. Resume frame buffers can grow rapidly when many clients drop while the server keeps producing data.

## 7. How do reconnect and resume affect Spring Integration?

A simple inbound flow:

~~~mermaid
flowchart LR
    A["RSocket client"] --> B["RSocket responder / inbound gateway"]
    B --> C["MessageChannel"]
    C --> D["IntegrationFlow"]
    D --> E["Service / DB / queue"]
    E --> F["Reply"]
    F --> A
~~~

If **reconnect** starts a new session, old requests may fail and the client must decide whether to resend. If **resume** succeeds, RSocket attempts to preserve the existing session/stream over a new transport. However, **`MessageChannel` does not persist messages durably by default**: for instance, `DirectChannel` runs synchronously, while queue/channel message stores must be explicitly configured to survive restarts.

In Spring Integration, consider these aspects:

| Component | On disconnect | What to design |
| --- | --- | --- |
| Inbound RSocket gateway / `@MessageMapping` | Incoming request may fail, cancel, or continue if resume succeeds | Timeouts, exception mapping, correlation IDs |
| `MessageChannel` | Messages already in the channel may be mid-processing | Distinction between in-memory and durable storage |
| `IntegrationFlow` | Handler may finish before the reply can be sent | Idempotent receivers and queryable outcomes |
| Outbound RSocket gateway | Replies from external systems may never arrive | Per-route retry policies by mutability |
| Error flow / `errorChannel` | Captures errors at configured boundaries | Separate transport errors from business errors |
| Database / event store | Commits may happen independently of RSocket replies | Transactions, unique keys, checkpoints, and replay |

Do not treat `errorChannel` as a durable persistence service or automatic request recovery tool. It only participates in error paths when flows are configured to route errors to it.

### 7.1. Distinguishing request errors from connection errors

Suppose the client calls `orders.submit` and the Spring Integration handler rejects it because `quantity = -1`. Even though this appears as an error signal on RSocket, **reopening the connection will not make the quantity valid**. Retry policies must filter by error category:

- **Potentially transient:** transport drops, peer timeouts, certain overload signals with clear retry-after semantics.
- **Should not auto-retry:** malformed schema, invalid data, unauthorized access, missing route, contract violations.
- **Unknown outcome:** timeouts on side-effecting operations. Query status by request ID or rely on idempotency before re-executing.

## 8. Business guarantees: idempotency and checkpoints

Protocol-layer RSocket resume restores streams under the right conditions. It is **not business-layer exactly-once delivery/processing**. The practical guarantee is usually *effective-once*, achieved via deduplication and transactions.

### 8.1. Idempotency key pattern for write commands

The client sends an unchanged request ID on retries:

~~~json
{
  "requestId": "8cfa2e7b-0a94-4d0b-a9fe-88e6a640b2a5",
  "orderId": "ORD-102",
  "quantity": 3
}
~~~

The server must execute the equivalent of:

~~~text
BEGIN TRANSACTION
  1. Check/insert requestId with UNIQUE constraint.
  2. If already processed: read first result and return it.
  3. If new: execute business operation.
  4. Store result against requestId.
COMMIT
~~~

Steps 1–4 must execute **atomically inside a proper transaction boundary**. A naive `if (!seen) { createOrder(); seen.add(id); }` using a `ConcurrentHashMap` is unsafe across multiple instances or restarts. When publishing events onward to Kafka/JMS, you may need a transactional outbox or broker-aligned deduplication.

When a reply is lost, the client can resend the **same request ID** or query `orders.status` to check whether the server created the order. Never mint a new request ID on retries of the same business intent.

### 8.2. Checkpoints for event streams

For route `inventory.events`, each event should carry an `eventId` or a suitably scoped monotonic position such as `sequence`:

~~~json
{
  "eventId": "stock-000103",
  "sequence": 103,
  "sku": "SKU-18",
  "available": 42
}
~~~

A consumer can:

1. Receive the event over RSocket.
2. Start a transaction and check whether `eventId` was already processed.
3. Persist business changes and checkpoint `sequence=103` in the same transaction.
4. Commit before advancing the application's progress state.
5. If reconnect creates a new session, ask the server to **replay from checkpoint** if the server has a durable event log and the route supports `fromSequence`.

**Note:** `fromSequence` is an **application-defined business contract parameter**, not a built-in RSocket Resume feature. To replay across server restarts, the source needs durable event/offset storage; an in-RAM stream alone cannot re-emit old events.

### 8.3. Backpressure does not replace durability

RSocket sends `REQUEST_N` to regulate receive demand in request-stream/channel. When a peer temporarily slows down, backpressure reduces emission pressure. Yet if the peer crashes and the session cannot recover, **backpressure cannot rebuild lost state**. Design bounded frame stores, sensible buffers, and source-backed replay if history must be preserved.

## 9. Choosing a strategy by scenario

| Scenario | Primary choice | Why |
| --- | --- | --- |
| Order status query, request-response | Reconnect + filtered retries and timeouts | Status reads are normally safe to retry |
| Order/payment creation command | Reconnect + idempotency key; query outcome before unsafe retries | Replies can be lost after commit |
| Telemetry stream tolerating minor sample loss | Reconnect + re-subscribe, track loss metrics | Simple, low overhead |
| Data-change stream needing continuity across brief drops | Resume if both sides and LB support it; combine with checkpoints | Bridges brief interruptions, with fallback when resume fails |
| Consumer must recover across client/server restarts | Reconnect + replay from durable event log/offset | Resume relies on surviving session state |
| Multiple server instances behind LB | Sticky routing/session-aware resume or shared state design | Resume token must reach the right session state |
| Route exposed to heterogeneous tech clients | Document resume support and fallback explicitly | Not all RSocket implementations support resume |

Do not enable resume just because it sounds "safer". It consumes memory storing frames, complicates session lifecycles, and requires coordination across clients, servers, and load balancers. Choose based on real recovery needs and operational capabilities.

## 10. Test scenarios for reconnect and resume

### 10.1. Distinguishing the two test paths

**Path A — Reconnect:** disable resume, configure a reconnect policy, and use a request-response route. Make the server briefly unavailable, restore it, and send a **new request**. Verify the new request uses a fresh connection; previously failed requests do not silently complete on their own.

**Path B — Resume:** enable resume **on both client and server**, open a request-stream, and observe events. Sever the transport for shorter than the session lifetime **while keeping both server and client processes running**. Then let the client reconnect to the same server. Verify the stream continues without losing resumable payloads under test conditions.

### 10.2. Test matrix

| Test | Expectation |
| --- | --- |
| Brief TCP loss, both sides hold session | Resume can succeed if frames remain buffered |
| Resume disabled on server | Client cannot resume session; must handle error |
| Server restart wipes in-memory sessions | Resume typically rejected; fallback creates new session |
| Outage exceeds session timeout | Resume fails; never retry stale token infinitely |
| LB routes resume to stateless instance | Resume fails unless shared state/routing supports it |
| Order creation commits, reply lost | Request ID ensures retry does not create a second order |
| Receiving event #102, drops before checkpoint #102 | After fallback replay, duplicate event handled safely |
| Network loss during backpressured request-stream | Monitor memory/frame store, buffer caps, cancel/error signals |
| Intentional application stop | Do not treat `dispose`/shutdown as resumable outage |

Do not test solely by invoking Java methods on `@MessageMapping` or `IntegrationFlow` directly: that bypasses transport, SETUP, KEEPALIVE, RESUME, and frame stores. Write tests traversing real RSocket clients/servers or equivalent test setups, and verify database/event-store state for side-effecting flows.

### 10.3. What to observe

Logs/metrics should capture:

- New connection attempts, retry/reconnect counts, and time to recover.
- Resume attempts, `RESUME_OK` acceptances, and `REJECTED_RESUME` rejections.
- Session age, active un-expired sessions, frame store size, and eviction rates.
- Active streams, errors/cancellations, timeouts, backpressure, and response latency.
- Correlation ID, request ID, event ID, and business-layer deduplication counts.

Never log auth tokens, resume tokens, or full sensitive payloads. Distinguish **server restarts** from **transport-only cuts** when analyzing test results.

## 11. Common issues and isolation steps

| Symptom | What to check | Resolution |
| --- | --- | --- |
| Client reconnects yet old stream does not continue | Running reconnect instead of resume? | Confirm both sides enable resume from SETUP |
| `REJECTED_RESUME` after server restart | Session state/token lost | Open new session and recover from durable checkpoint |
| Resume succeeds yet business events are missing | Checkpoint ordered wrong vs. transaction, or source lacks history | Use event log with replay + deduplication |
| Every network drop creates an extra order | Retrying write commands without idempotency | Preserve request ID, transactional dedup, unique constraints |
| Continuous reconnects overload server | Retries lack backoff/jitter or caps | Add backoff, jitter, retry limits, monitoring |
| Long-lived sessions grow RAM | Frame store accumulates while client stalls | Bound session lifetime/buffers, control streams |
| LB sends client to different server, resume fails | Local session state absent on new node | Sticky routing or supported session state sharing |
| Disconnects detected slowly | KEEPALIVE/`maxLifeTime`, LB idle timeouts | Tune intervals, lifetimes, and environment timeouts |
| Message entered channel yet no reply arrives | Hung handler, business error, missing reply path | Check `MessageChannel`, `IntegrationFlow`, timeouts, error handling |
| `retryWhen` partially recovers then starts a fresh stream | Retries create a new subscription | Separate business replay from protocol resume and pick appropriately |

When investigating, follow the chain: **transport → KEEPALIVE/SETUP → reconnect or RESUME/RESUME_OK → RSocket route → codec → Spring Integration channel → business transaction → reply/checkpoint**. Never lump every symptom under "RSocket auto-reconnect is broken".

## 12. Practice exercises and self-check questions

### Exercise A — Controlled reconnect

Create a client calling `orders.status` every few seconds, configure backoff, and toggle the server off/on. Record when connections fail, when new requests succeed, and retry counts. Explain whether an in-flight request at shutdown re-runs automatically or needs Publisher-layer retries.

### Exercise B — Resuming a request-stream

Create route `inventory.events` emitting ascending sequences. Enable resume on both sides and simulate a brief transport cut **without restarting the server process**. Verify all sequences arrive while the session is valid; then repeat by restarting the server and observing the fallback path.

### Exercise C — Preventing duplicate orders

Create route `orders.submit` with `requestId`. Simulate a successful server commit whose reply is lost, then retry with the same `requestId`. Implement idempotent persistence so the total created orders remains one. Explain why `MessageChannel` and RSocket Resume do not guarantee this automatically.

### Exercise D — Strategy selection

Given three systems: a temperature dashboard tolerant of dropped points; a CDC stream requiring all events; and an invoice creation API subject to retries. Propose a strategy for each, specifying when resume is needed, when logs/checkpoints are needed, and when idempotency keys are mandatory.

## 13. Summary

- **KEEPALIVE** helps detect lost connections; **reconnect** opens a new connection for future requests; **resume** tries to preserve an existing session and stream while state remains valid.
- In rsocket-java, `reconnect(Retry)` and `resume(Resume)` are alternative modes. Resume requires both client and server support, matching tokens/sessions, retained frames, and un-expired lifetimes.
- Resume can be rejected, especially on server restarts, expired sessions, or routing to stateless nodes.
- **Retrying a Publisher** is an application-layer choice. Retrying after errors is not protocol resume and can re-execute side effects.
- Spring Integration requires proper timeouts, error handling, idempotency, checkpoints, and durable storage to satisfy business guarantees across network outages.
- Test both brief transport cuts and server restarts/resume failures, and always verify database/event-store state for write operations.

## References

- [RSocket Protocol — Resuming Operation](https://rsocket.io/about/protocol/): resume conditions, `RESUME`, `RESUME_OK`, `REJECTED_RESUME`, and implied positions.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, connection setup, and customizing `RSocketConnector`.
- [RSocket Java — RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html): `reconnect`, `resume`, `keepAlive`, and mode constraints.
- [RSocket Java — RSocketServer API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html): server-side resume configuration.
