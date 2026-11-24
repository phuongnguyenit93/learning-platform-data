# Reconnect and Limits of Recovering In-Flight Requests

## Objectives

After this lesson, you can distinguish reopening an RSocket connection from resuming an interrupted RSocket session; configure retries at the right layer; explain what happens to in-flight requests; and design safe recovery mechanisms when the server has processed a request but the client has not received the response.

## 1. Distinguishing Transport Connection, Session, and Stream

RSocket runs over a transport such as TCP or WebSocket. When the transport is established, both sides exchange a `SETUP` frame to create a communication context. Afterward, each interaction creates a separate stream, which can be:

- **Request-Response:** one request and at most one response.
- **Request-Stream:** one request opening a stream of responses.
- **Channel:** both sides exchange bidirectional data streams.
- **Fire-and-Forget:** send one message without waiting for a response.

Three concepts to separate:

- **Transport connection** is the current physical or logical link, such as a TCP connection.
- **RSocket session** is the protocol context tied to a connection session. When resumption is enabled, a session can span multiple transport connections.
- **Stream** is a specific interaction within the session. A stream has its own state, sequence, and lifecycle.

Losing TCP/WebSocket does not automatically mean business processing on the server has stopped. The server may have already received the request, be processing it, have written data, or have sent the response before it reached the client. Therefore, seeing a connection error on the client does not tell you for certain how far the request has been executed.

## 2. Three Commonly Confused Mechanisms

| Mechanism | Recovery Scope | What It Does | What It Does Not Guarantee |
|---|---|---|---|
| Reconnect | Transport connection | Creates a new RSocket connection after the old connection is lost | Does not automatically restore old streams or resend in-flight requests |
| Protocol resumption | RSocket session and stateful streams | Reattaches the session and replays stored frames so streams continue | Does not guarantee the session is always accepted, nor provide business exactly-once |
| Request-layer retry | An application operation | Resubscribes to the publisher and resends the operation per retry policy | Can execute business logic a second time if the first ran and the response was lost |

**Reconnect and request retry are two different things.** Reconnect provides a new connection. The application must still decide which requests need to be resent, how many times to resend, and when to stop.

**Resumption differs from regular reconnect.** Resumption tries to preserve the existing session and active streams by exchanging state and replaying frames. This is an optional protocol feature, not a default supported by every RSocket server.

In RSocket Java, `RSocketConnector.reconnect(Retry)` and `RSocketConnector.resume(Resume)` are mutually exclusive modes. If both are configured, `resume` takes precedence. Choose one explicit strategy based on server capabilities and business requirements.

## 3. Reconnect: Opening a New Connection

Spring provides `RSocketRequester.Builder.rsocketConnector(...)` to customize `io.rsocket.core.RSocketConnector`. The example below uses the current Spring Framework `tcp(...)` API. The connection is created lazily on the first request.

~~~java
import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.reconnect(
        Retry.backoff(3, Duration.ofMillis(500))
            .maxBackoff(Duration.ofSeconds(5))))
    .tcp("localhost", 7000);
~~~

Meaning of the configuration:

1. `reconnect(...)` instructs the connector to manage a shared RSocket for subscribers.
2. When the current connection is lost, the next subscription can trigger creating a new connection.
3. `Retry.backoff(3, ...)` limits attempts and progressively increases wait times; `maxBackoff` caps the delay.
4. This is a policy for recreating the connection, not a policy for replaying every failed request.

RSocket Java documentation states explicitly that each request's subscriber still needs its own retry if you want to resend the request. Example:

~~~java
import java.time.Duration;

import io.rsocket.exceptions.ConnectionErrorException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<OrderStatus> status = requester.route("orders.status")
    .data(orderId)
    .retrieveMono(OrderStatus.class)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(250))
        .filter(ConnectionErrorException.class::isInstance));
~~~

This is an illustrative snippet inside a service that already has `requester`, `orderId`, and type `OrderStatus`. The filter is only an example for connection errors; in a real application, classify errors according to your RSocket version, transport, and business rules. Do not retry validation errors, authorization errors, or business errors that cannot be fixed by resending.

When the publisher is resubscribed, the request operation is created and sent again. That may be fine for a read query, but dangerous for write operations. If the server already created the order and the response was lost, a retry can create a duplicate second order.

## 4. Protocol Resumption: Continuing Sessions and Streams

Resumption is an optional extension of the RSocket protocol. Both requester and responder must support and enable this feature. When the transport is interrupted, the client opens a new transport and sends a `RESUME` frame along with the session identification token and the received frame position. The server continues only if it still recognizes the session and still holds the needed state/frames; when accepted, the server returns `RESUME_OK`. Both sides then continue exchanging from the agreed positions and can replay missing frames from the store.

With Spring, you can configure the low-level connector via `rsocketConnector`. The example below illustrates client configuration:

~~~java
import java.time.Duration;

import io.rsocket.core.Resume;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

Resume clientResume = new Resume()
    .sessionDuration(Duration.ofMinutes(5))
    .retry(Retry.backoff(10, Duration.ofSeconds(1)));

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.resume(clientResume))
    .tcp("localhost", 7000);
~~~

The server side must also enable resumption for the same connection type. For a server built with RSocket Java and a handler from Spring:

~~~java
import java.time.Duration;

import io.rsocket.core.Resume;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import reactor.util.retry.Retry;

// handler is an RSocketMessageHandler configured in Spring.
Resume serverResume = new Resume()
    .sessionDuration(Duration.ofMinutes(5))
    .retry(Retry.backoff(10, Duration.ofSeconds(1)));

RSocketServer.create(handler.responder())
    .resume(serverResume)
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

These are configuration fragments, not a standalone application. You need the appropriate RSocket transport dependency, a configured `RSocketMessageHandler`, a listening server, and compatible Spring/RSocket Java versions. Connection APIs may differ in older Spring versions; check the exact Javadoc for your project version before copying configuration.

### Conditions for Resumption to Succeed

- Both sides support and enable Resume; a server without support may reject `SETUP` or `RESUME`.
- The client must keep the old session token and send the resume request while the session is still valid.
- The server must retain the session, stream states, and unacknowledged frames long enough to replay them.
- The frame store must remain contiguous from the recovery position. If required frames were evicted or the store lacks sufficient data, the server may reject resumption.
- The client must connect to the right session state. In a multi-node system, a load balancer may route the client to another node; that node must access shared state or the system must route back to the node holding the session.
- Session parameters such as data/metadata formats must match the original session.

`sessionDuration` bounds how long session state is retained after disconnection; `retry` controls reconnect attempts to resume. Configuring retries longer than the server retains the session will not recover an expired session.

Resumption is only an optimistic recovery attempt. It can fail on server restart, lost session/token, interruption exceeding the timeout, missing frames in the buffer, or active server rejection. If using an in-memory store, that state is lost when the process stops; supporting failover or restarts requires storage and routing designed for your actual deployment.

## 5. Important Limits for In-Flight Requests

### No Business-Level Exactly-Once Guarantee

RSocket resumption tracks and replays frames at the protocol layer. It does not know whether a database transaction committed, nor whether an email was sent or a payment was recorded. The protocol specification makes no atomicity or transactionality guarantees for processed frames.

Example with Request-Response:

1. The client sends `createOrder`.
2. The server receives the request and writes the order successfully.
3. The server sends the response.
4. The network disconnects before the client receives the response.
5. The client sees only a connection error; the client cannot deduce whether the order was created.

If the client resends the request as a new operation, the server may create a duplicate order. Resumption can help continue streams and replay frames, but it does not replace business idempotency.

### How to Protect Operations with Side Effects

For create, update, payment, or notification operations:

1. The client generates a stable `requestId` or idempotency key for one business intent.
2. The client sends that key with the payload; every retry of the same intent must reuse the key, never generate a new key.
3. The server stores the key and processing result atomically with the side effect (e.g., in the same database transaction).
4. Upon receiving an already-processed key again, the server returns the stored result instead of executing the side effect a second time.
5. Keep the key for a retention window aligned with retry duration and late client retries.

Do not store the key only on the client. Deduplication must be enforced on the side that owns the data or side effect.

### Recovery by Interaction Model

- **Request-Response:** retrying can resend the entire operation. Safe for read queries or commands with an idempotency key. Do not treat a timeout as proof the server has not processed it.
- **Request-Stream:** if resumption succeeds, the stream can continue. If a new request must be created, send a cursor/offset or the last processed sequence number so the server emits from the checkpoint; the client should deduplicate by sequence.
- **Channel:** this is a bidirectional stream. When a session is lost and a new session must be created, the application needs to restore both sending and receiving state, such as sequence numbers, acknowledgements, and checkpoints.
- **Fire-and-Forget:** there is no response confirming the server received or processed it. If delivery results are needed, use Request-Response with an acknowledgement or an application-layer outbox/durable messaging mechanism.

## 6. Designing Controlled Retries

A safe retry policy should have these traits:

- **Bounded:** set a maximum attempt count or overall deadline. Never retry infinitely without a stopping mechanism and alerting.
- **Backoff and jitter:** increase wait time between attempts and add random jitter so many clients do not slam a newly recovered server at once.
- **Error classification:** retry transient transport errors; do not retry data errors, authentication, authorization, or business errors that cannot resolve on their own.
- **Timeouts:** limit wait time for a single request and total recovery time. Do not let a request hang beyond the business deadline.
- **Load limits:** consider circuit breakers, bulkheads, and limits on pending requests to prevent retry storms.
- **Preserve business identity:** every attempt of the same operation must carry the same idempotency key.
- **Fallback:** when resume is rejected or retries are exhausted, create a new session and recover at the application layer using requestId, cursor, or checkpoint.

Keepalive helps detect a lost peer or connection based on heartbeats and timeouts. It does not resend requests and does not automatically restore streams. Shrinking the keepalive interval can detect failures faster, but increases traffic and false positives on flaky networks.

## 7. Choosing a Strategy by Scenario

| Scenario | Strategy to Consider |
|---|---|
| Server does not support Resume; short read requests | Reconnect combined with bounded request-layer retries |
| Write requests that may be resent | Retry with idempotency key and server-side deduplication |
| Long stream, brief network drop, both sides hold session | Protocol resumption |
| Long stream, but session may be lost or expire | Resumption combined with application-layer cursor/checkpoint |
| Multi-node deployment or rolling restarts | Check where session/frame state lives and how routing works; always have requestId/cursor recovery |
| Fire-and-Forget needing delivery guarantees | Add acknowledgements or durable messaging; do not rely on plain reconnect |

No option replaces defining business requirements: how much data loss is acceptable, how much latency is tolerable, whether duplicate processing is allowed, and which checkpoint the client can resume from.

## 8. Testing and Observability

Do not test only shutting down and starting up the server. Simulate different failure points:

1. Cut the network with no active streams; verify reconnect creates a new connection.
2. Cut the network while a Request-Response is pending; verify the request fails or resumes per configuration.
3. Let the server commit a side effect and then drop the response; verify retries do not create duplicate records.
4. Cut the network mid-Request-Stream; verify the stream continues without losing or duplicating elements.
5. Keep the connection down longer than `sessionDuration`; verify resume fails gracefully and the application falls back to a checkpoint.
6. Restart the server or route the client to another node; verify behavior when the session store is unavailable.
7. Send an intentional business error; verify the retry filter does not resend that request.

Record reconnect counts, resume success/rejection counts, retry counts per route, recovery duration, deadline-exceeded requests, interrupted streams, and duplicate request rates blocked by the idempotency layer. Do not log sensitive payloads or resume tokens.

## 9. Common Mistakes

- **Enabling only reconnect and expecting streams to keep running:** reconnect creates a new connection; retrying requests requires a policy on the request's publisher.
- **Enabling resume on the client but forgetting the server:** both sides must support and enable resumption.
- **Configuring reconnect and resume together:** the two modes are mutually exclusive; resume takes precedence.
- **Retrying every exception:** can repeat business errors and cause unnecessary load. Filter for transient errors.
- **Generating a new idempotency key for every retry:** the server treats them as distinct operations and cannot deduplicate.
- **Assuming resume guarantees exactly-once:** the protocol recovers frames/streams, not business transactions.
- **Failing to test session expiration or node restarts:** short network drops often succeed easily, but do not represent all failures.
- **Retrying without a deadline or backoff:** can trigger retry storms and prolong requests indefinitely.

## 10. Implementation Checklist

- [ ] Clearly identified whether reconnect, resume, or request retry is needed.
- [ ] Verified server and client use compatible RSocket versions.
- [ ] If using resume, both sides enable it and retain state long enough.
- [ ] Calculated frame store capacity and routing behavior for multi-node deployments.
- [ ] Requests with side effects use stable idempotency keys and server deduplication.
- [ ] Streams have cursors/sequences/checkpoints to continue when a new request is needed.
- [ ] Retries have error filters, backoff, attempt limits, and deadlines.
- [ ] Tested lost responses after server commit, session expiration, and server restarts.
- [ ] Logs/metrics distinguish reconnect, resume, retry, and business-layer recovery.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, `RSocketConnector` configuration, and interaction models.
- [RSocket Protocol — Resuming Operation](https://github.com/rsocket/rsocket/blob/master/Protocol.md#resuming-operation): tokens, frame positions, resume accept/reject conditions, and protocol assumptions.
- [RSocket Java — RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java): behavior of `reconnect(Retry)`, `resume(Resume)`, and separate request-layer retry requirements.
