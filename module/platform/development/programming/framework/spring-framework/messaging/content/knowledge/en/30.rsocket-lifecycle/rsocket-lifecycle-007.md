# Lease and Distinguishing Request Quotas from REQUEST_N

## 1. Place in the RSocket Lifecycle

RSocket is a bidirectional communication protocol. After establishing TCP or WebSocket and exchanging the `SETUP` frame, either side can act as `Requester` (the side initiating requests) or `Responder` (the side handling requests). Therefore, do not permanently tie these two roles to client and server.

RSocket has two flow-control mechanisms at two different levels:

- **Lease** controls whether a party is allowed to open additional new requests on the connection.
- **Reactive Streams demand**, carried by `REQUEST_N`, controls how many payloads the receiver is ready to accept on a specific stream.

Both mechanisms can operate at the same time. Lease protects request admission capacity at the connection level; `REQUEST_N` lets each stream regulate data transmission speed according to the subscriber's consumption capacity.

Overview flow when Lease is enabled:

1. Requester sends `SETUP` with the `L` flag to announce that it will honor Leases from the peer.
2. After accepting the connection, Responder sends a `LEASE` frame granting a request quota and validity duration.
3. Requester opens new requests only within the granted count and time limit.
4. For stream or channel requests, initial demand is sent with the stream-opening frame; when more payloads are needed, the receiver sends `REQUEST_N`.
5. Responder can emit a subsequent Lease to grant a new quota. A new Lease replaces the previous Lease's values.

If the `L` flag is not set, Requester can send requests without waiting for a Lease. Once this flag is enabled, Requester must wait for a valid Lease before sending requests.

## 2. Lease: Time-Bounded Quota for Opening New Requests

### 2.1. What Problem Does Lease Solve?

A single connection can carry many concurrent requests. If Responder is overloaded, controlling individual streams alone is not enough to curb continuous initiation of new requests. Lease lets Responder advertise its current intake capacity so Requester adjusts how many requests it sends.

A `LEASE` frame contains two main values:

| Field | Meaning |
|---|---|
| `Time-To-Live (TTL)` | Duration the Lease remains valid, in milliseconds from when Requester receives the frame |
| `Number of Requests` | Maximum number of new requests Requester is allowed to send under that Lease |

The `LEASE` frame is connection-level and uses Stream ID `0`. It can be sent by Responder on either side of the connection to limit requests initiated by the other side.

### 2.2. What Does Lease Count?

Each time Requester opens a new request interaction, it consumes one unit from the Lease quota. Counted request types include:

- `REQUEST_RESPONSE`
- `REQUEST_STREAM`
- `REQUEST_CHANNEL`
- `REQUEST_FNF` (Fire-and-Forget)

For example, a Lease grants `10` requests for `2 seconds`. Within that window, Requester can open at most 10 new requests of the types above. A `REQUEST_STREAM` still consumes only one unit when initiated, even if the stream later emits many payloads.

When the granted request count is exhausted or the TTL expires, Requester must not open additional requests under the old Lease. When a new Lease arrives, the previous Lease's quota and duration are replaced; the two quotas do not stack. If Responder receives a request it cannot accept due to Lease limits, the protocol specifies responding with `ERROR[REJECTED]`.

### 2.3. Lease Is Not a Stream Message Limit

Lease regulates starting requests. Once a `REQUEST_STREAM` has been accepted, how many payloads the stream continues emitting is controlled by that stream's demand.

Thus, when a Lease expires:

- Requester cannot open new requests until the next valid Lease arrives.
- Already-open streams are not automatically cancelled merely because the Lease expired.
- Payloads on running streams must still follow `REQUEST_N` and the stream lifecycle.

Lease is also not equivalent to a concurrent-in-flight request limit. It limits how many requests are initiated within a time period. If you need limits on concurrency, queues, or actual processing load, the application still needs appropriate policies at the processing layer.

## 3. REQUEST_N: Per-Stream Payload Demand

### 3.1. What Is REQUEST_N?

`REQUEST_N` is RSocket's Reactive Streams flow-control signal. It indicates how many more payloads the receiver wants from the sender on a specific stream.

For `REQUEST_STREAM` and `REQUEST_CHANNEL`, the stream-opening frame carries initial demand. Afterward, when more data is needed, the receiver sends a `REQUEST_N` frame with an incremental count.

Example:

1. Requester opens a stream with `REQUEST_STREAM` and initial demand of `3`.
2. Responder sends at most 3 `PAYLOAD` frames on that stream.
3. When Requester wants more, it sends `REQUEST_N(N=2)` on the same Stream ID.
4. Responder is allowed to send up to 2 more payloads per the newly received demand.

`REQUEST_N` is bound to the Stream ID of an active stream, unlike `LEASE` which uses Stream ID `0` at the connection level.

### 3.2. Relationship to Reactive Streams

In Reactive Streams, a subscriber calls `Subscription.request(n)` to signal how many elements it is capable of receiving. RSocket transmits this demand signal over the network so Responder paces payload emission.

With Spring Framework, applications typically work with `Mono` and `Flux`. When using `RSocketRequester` to receive a `Flux` result, subscriber demand is translated by Reactor and RSocket Java into the protocol's flow-control mechanism. Usually, the application does not need to construct `REQUEST_N` frames manually.

This mechanism keeps producers from emitting data faster than subscribers can consume it. It also reduces the amount of data held in buffers and helps independent streams share the connection more efficiently.

`REQUEST_N` has no TTL. Demand remains on the stream until consumed or the stream terminates; when more payloads are needed, the receiver sends additional demand.

### 3.3. REQUEST_N in Request-Channel

`REQUEST_CHANNEL` supports data in both directions. Demand always belongs to the side receiving payloads: each side must grant demand for the data it receives from the peer. When reading a Channel frame log, inspect the Stream ID and direction to determine which direction's payload sending `REQUEST_N` authorizes.

`REQUEST_RESPONSE` has only one response, so it does not need a `REQUEST_N` demand sequence like a stream. `REQUEST_FNF` has no response stream.

## 4. Comparing Lease and REQUEST_N

| Criterion | Lease | REQUEST_N |
|---|---|---|
| Scope | Whole connection, in the direction Responder grants permission to Requester | One specific stream |
| Controls | Number of new requests opened | Number of additional payloads allowed to be sent |
| Counting unit | Request interaction | Payload/message |
| Key info | TTL and Number of Requests | N |
| Frame | `LEASE` | `REQUEST_N` |
| Stream ID | `0` | Active Stream ID |
| Timing | Has TTL; expires and leaves no quota | Has no separate TTL |
| Applies to | Request-Response, Request-Stream, Channel, Fire-and-Forget | Payload flow of Request-Stream and Channel |
| Goal | Admission control, pacing new requests and protecting processing capacity | Backpressure, pacing data rate to match consumer |

You can remember the difference with two questions:

- **Lease asks: “How many more new requests am I allowed to open during this window?”**
- **REQUEST_N asks: “On this stream, how many more payloads am I allowed to send?”**

Never use Lease counts in place of stream demand, or use `REQUEST_N` as a connection-wide request quota.

## 5. Example Combining Both Mechanisms

Suppose Responder sends a Lease with a 2-second TTL and Number of Requests equal to 10.

Within that window, Requester opens a `REQUEST_STREAM`. This request consumes one Lease unit. When opening the stream, Requester grants an initial demand of 3:

~~~text
Requester -> Responder: SETUP (L = 1)
Responder -> Requester: LEASE (TTL = 2000 ms, Requests = 10)

Requester -> Responder: REQUEST_STREAM (Stream ID = 1, initial REQUEST_N = 3)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)

Requester -> Responder: REQUEST_N (Stream ID = 1, N = 2)
Responder -> Requester: PAYLOAD (Stream ID = 1)
Responder -> Requester: PAYLOAD (Stream ID = 1)
~~~

After this sequence:

- Remaining Lease quota is 9 new requests, assuming still within TTL and not replaced by a new Lease.
- Stream ID 1 has received 5 payloads across two demand grants.
- The two extra payloads did not consume two additional Lease units.
- Requester can send more `REQUEST_N` on Stream ID 1 to receive more payloads.
- Requester can open new requests if the Lease is still valid and has remaining quota.

This example shows Lease and `REQUEST_N` operate independently: one governs how often requests start, while the other governs data transferred within each stream.

## 6. Configuration in Spring Framework and RSocket Java

### 6.1. Enabling Lease for RSocketRequester

Spring provides `RSocketRequester` to build requests with a fluent API. Its builder allows configuring `io.rsocket.core.RSocketConnector` via `rsocketConnector`:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.lease(spec -> spec.maxPendingRequests(128)))
    .tcp("localhost", 7000);
~~~

Calling `lease` enables Lease support on the connector so Requester honors quotas issued by the peer. The peer must still emit valid Leases; enabling it on Requester does not automatically create quotas on Responder.

`maxPendingRequests(128)` limits how many requests wait in the local queue when no Lease is available. This is not Number of Requests in the `LEASE` frame, nor the number of payloads a stream may receive.

### 6.2. Issuing Leases on the Responder Side

With RSocket Java, the server can configure a Lease emitter using `RSocketServer.lease`. This is a server configuration fragment; `RSocketController` is the application's `@Controller` class containing `@MessageMapping` methods. Example granting 10 requests with a 2-second TTL and sending a new Lease every second:

~~~java
import java.time.Duration;

import io.rsocket.SocketAcceptor;
import io.rsocket.core.RSocketServer;
import io.rsocket.lease.Lease;
import io.rsocket.transport.netty.server.TcpServerTransport;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import reactor.core.publisher.Flux;

// RSocketController is a @Controller with @MessageMapping methods.
RSocketStrategies strategies = RSocketStrategies.builder().build();
SocketAcceptor acceptor = RSocketMessageHandler.responder(
    strategies, new RSocketController());

RSocketServer.create(acceptor)
    .lease(spec -> spec.sender(() ->
        Flux.interval(Duration.ZERO, Duration.ofSeconds(1))
            .map(tick -> Lease.create(Duration.ofSeconds(2), 10))))
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

This is a fixed Lease-issuing policy example to illustrate the API. In a real system, the Lease emitter should reflect current capacity such as pending requests, CPU load, worker limits, or service health. Do not copy fixed quotas into production without load evaluation.

If the application needs both sides to initiate requests, each direction must be configured for its role: Requester enables Lease compliance in `SETUP`, while Responder on the opposite side provides a Lease emitter. Configuring Lease for one direction does not mean the reverse direction has a quota policy.

### 6.3. REQUEST_N via Flux

When receiving a stream in Spring, use `retrieveFlux` to obtain a `Flux`:

~~~java
Flux<Event> events = requester
    .route("events")
    .data(command)
    .retrieveFlux(Event.class);
~~~

Subscriber demand on `events` is propagated through Reactor and RSocket Java. If the subscriber requests more data in batches, RSocket sends corresponding demand signals for the stream. Reactor backpressure operators can help regulate how the application consumes data; they do not replace connection-level Lease policies.

## 7. Common Misconceptions

1. **Treating Lease as the maximum message count of a stream.** Lease only counts new request interactions; stream payloads are controlled by demand.
2. **Treating REQUEST_N as a connection-wide request quota.** REQUEST_N belongs to one Stream ID and does not grant permission to open new requests.
3. **Thinking a stream request consumes Lease per payload.** A stream request consumes one unit at initiation; subsequent payloads follow REQUEST_N.
4. **Confusing maxPendingRequests with Number of Requests.** maxPendingRequests bounds the local queue of requests waiting for a Lease; Number of Requests is the quota granted by the peer in a LEASE frame.
5. **Enabling Lease on the requester without emitting Leases on the responder.** Once the requester agrees to honor Leases, it must wait for a valid quota before sending requests.
6. **Assuming an expired Lease cancels running streams.** Expiration blocks new requests under the old Lease; the lifecycle of running streams continues to be governed by flow control and stream termination signals.
7. **Thinking Lease is a full authentication or rate-limiting mechanism.** Lease is a protocol-level admission control mechanism. Applications still need authentication, authorization, per-user rate limits, and proper overload handling.

## 8. How to Check When Debugging

When analyzing frame logs, check in order:

- In `SETUP`, whether Requester enabled the `L` flag.
- Whether Responder emits `LEASE`; check TTL and Number of Requests.
- Whether new requests are opened only while a Lease is valid and has remaining quota.
- For `REQUEST_STREAM` or `REQUEST_CHANNEL`, check initial demand.
- For `REQUEST_N` frames, check Stream ID, direction, and incremental payload count.
- If `ERROR[REJECTED]` occurs, check whether requests exceeded the Lease quota or the Lease expired.

You can enable RSocket Java frame logging at DEBUG level for the `io.rsocket.FrameLogger` logger when you need to observe the protocol on the wire.

## 9. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): request models, backpressure, `RSocketRequester`, and connector configuration.
- [RSocket Protocol — Lease Semantics](https://github.com/rsocket/rsocket/blob/master/Protocol.md#lease-semantics): TTL rules, request counts, Lease flag in SETUP, and behavior when limits are exceeded.
- [RSocket Protocol — Flow Control](https://github.com/rsocket/rsocket/blob/master/Protocol.md#flow-control): Reactive Streams semantics and `REQUEST_N`.
- [RSocket Java — RSocketServer API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html): configuring Lease emission on the server side.
- [RSocket Java — RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html): enabling Lease on the connector side.
- [RSocket Java — LeaseSpec API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/LeaseSpec.html): configuring the queue of requests awaiting Lease and LeaseSender.
