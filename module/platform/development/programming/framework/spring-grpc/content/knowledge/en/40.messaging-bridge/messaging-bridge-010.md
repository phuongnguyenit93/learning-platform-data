# Do Not Hold Streams Open Indefinitely Waiting for the Broker

A messaging bridge may receive commands over gRPC, forward them to a broker, and then wait for results or push events back to the client. If every request opens a gRPC stream and holds that stream open indefinitely just waiting for the broker to produce a message, the number of waiting sessions grows with the number of callers. Idle streams still hold state, queues, deadlines, transport, and tracking resources; proxies or deployments can also close them unexpectedly.

**Do not hold streams open indefinitely waiting for the broker** is the principle of decoupling the lifecycle of a broker consumer from the lifecycle of a gRPC RPC, while bounding wait time, session count, and queued outbound data. This lesson belongs to the **Messaging bridge** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem using Protocol Buffers contracts, generating Java code, and implementing client/server logic for unary or streaming RPCs; learners handle metadata, deadlines, status, interceptors, TLS, integration testing, and monitoring performance and reliability. The focus is choosing a request/response, bounded long polling, or leased subscription model; applying deadlines, flow control, bounded queues, cursors/acknowledgements, and cleanup when clients depart.

## 1. Why Are Infinite-Wait Streams Risky?

A gRPC stream is not a perpetually blocked thread, yet it still owns lifecycle and resources that must be managed:

- The server holds call state, listeners, contexts, callbacks, and session references.
- The client holds stream observers, retry/reconnect state, and response-handling logic.
- The application may hold per-caller queues, correlation state, subscriptions, or broker delivery state.
- An HTTP/2 connection can multiplex many streams, but each stream still consumes resources and quota.
- Proxies, ingresses, load balancers, or service meshes may enforce their own idle timeouts or maximum stream durations.
- Rolling deployments, network interruptions, and broker rebalances can terminate a stream at any moment.

If a client opens a stream to wait for events for hours, the service must handle disconnects, reconnects, queue overflow, duplicate delivery, graceful shutdown, and recovery cursors. Without those mechanisms, an open stream does not mean a reliable bridge.

Keepalive does not solve this problem either. HTTP/2 keepalive PINGs check the connection at the transport layer; they do not prove the broker has messages, the consumer is making progress, or the client application is still processing events. A healthy connection can still carry an idle stream waiting indefinitely with zero business progress.

## 2. Decoupling Broker Consumer Lifecycle from gRPC RPCs

Broker consumers should be managed as background components of the service, following consumer group/subscription and application lifecycles. A gRPC RPC should only register interest in receiving data or await results for a bounded duration.

~~~mermaid
flowchart LR
    B[Message broker] --> C[Background consumer]
    C --> H[Bridge event hub]
    H --> Q[Bounded session queues]
    Q --> G[gRPC streaming sessions]
    G --> A[Clients]
    A -->|ack/cursor| H
~~~

This model separates the components:

- **Broker consumer:** reads messages independently of how many gRPC clients are connected.
- **Event hub:** routes events by permitted subscription, correlation ID, or topic.
- **Session queue:** holds a bounded number of events for each gRPC subscriber.
- **gRPC session:** has an expiry, queue limits, cancellation state, and reconnect rules.
- **Client:** processes events, stores cursors/acknowledgements, and opens a new session when needed.

Do not spin up a new broker consumer for every gRPC stream if the goal is sharing a consumer group or fanning out events. Doing so scales consumer count with client count and causes rebalances, partition contention, or duplicate processing. Only create dedicated consumers when broker isolation and semantics truly demand it.

Distinguish consumer-group load balancing from pub/sub fan-out. Multiple consumers in the same group normally divide messages/partitions among themselves; they do not automatically receive copies of every message. If every gRPC subscriber must see the same events, the bridge needs an explicit fan-out mechanism: separate offset groups per subscription, a background consumer publishing into an internal pub/sub, or a shared event store that each session reads by cursor. When running multiple replicas, an event hub residing solely in one instance's RAM does not automatically forward events to subscribers connected to other instances.

## 3. Choosing the Right Pattern Instead of Waiting Forever

| Pattern | How it works | When appropriate |
| --- | --- | --- |
| Asynchronous request/response | RPC accepts command, returns operation ID; client queries status or receives notification later. | Broker tasks can take seconds/minutes and callers do not need to keep the RPC open. |
| Bounded long polling | RPC waits up to a short interval; returns event if available, or empty/cursor on timeout. Client re-polls with backoff. | Client needs events without maintaining a continuous connection. |
| Leased subscription stream | Client opens server stream for a fixed duration; service pushes events, then closes cleanly for client reconnect. | Low latency needed with continuously online clients, while still supporting reconnect. |
| Webhook/callback | Service calls a registered endpoint when events are ready. | Client exposes a callback endpoint and accepts managing callback security/retries. |

There is no single pattern right for every bridge. Base your choice on latency requirements, client counts, broker processing times, reconnect capability, and delivery guarantees. What must be avoided is an RPC with no deadline, no lease, and no session limits.

## 4. Asynchronous Request/Response for Long Tasks

When a client submits a command and waits for broker processing, it is usually best to separate accepting the command from waiting for the outcome:

1. The client calls `SubmitCommand`.
2. The service validates the request, creates `operation_id`, and writes the command to the broker/outbox.
3. The service returns `ACCEPTED` with `operation_id` as soon as the command is accepted per the durability contract.
4. Workers process the broker message and update operation state.
5. The client calls `GetOperation(operation_id)` or subscribes to notifications to receive the result.

Example response:

~~~protobuf
message SubmitCommandReply {
  string operation_id = 1;
  enum State {
    STATE_UNSPECIFIED = 0;
    ACCEPTED = 1;
    RUNNING = 2;
    SUCCEEDED = 3;
    FAILED = 4;
  }
  State state = 2;
}
~~~

`ACCEPTED` must have clear semantics: the command has been durably written to the broker or transactional outbox, not merely appended to an in-memory queue. If the service returns accepted before data is durable, a process crash can lose the command while the client believes the system accepted it.

`operation_id` is a business identifier for querying results; it does not replace authentication. The `GetOperation` API must verify that the caller is authorized to view the corresponding operation.

## 5. Bounded Long Polling

Long polling holds an RPC briefly to wait for the next event, but always with an upper bound. The client sends a cursor or offset; the server waits at most `max_wait`, returning events if available or `no_event` when the wait expires.

~~~text
Client                         Bridge                         Broker
  |                              |                               |
  |-- Poll(cursor, max_wait) --->|                               |
  |                              |-- wait/read after cursor ---->|
  |                              |<--------- event / timeout ----|
  |<----- event or no_event -----|                               |
  |                              |                               |
  |-- Poll(next_cursor, ...) --->|   (new bounded RPC)           |
~~~

The server bound must be less than or equal to service policy, regardless of how long the client requests. For example, if a client asks for 60 seconds but the service allows at most 20 seconds, the server waits at most 20 seconds.

The RPC deadline must cover the wait duration plus response serialization/handling time. If the deadline expires before long polling finishes, the client receives `DEADLINE_EXCEEDED`; if the application-defined wait ends normally with no events, return `no_event` rather than turning an expected empty wait into an RPC failure.

Example wait budget calculation:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

Duration boundedWait(
        Duration requested,
        Duration maxWait,
        Duration responseMargin) {

    long waitMillis = Math.min(
            requested.toMillis(),
            maxWait.toMillis());

    Deadline deadline = Context.current().getDeadline();
    if (deadline != null) {
        long remainingMillis =
                deadline.timeRemaining(TimeUnit.MILLISECONDS);
        waitMillis = Math.min(
                waitMillis,
                Math.max(0, remainingMillis - responseMargin.toMillis()));
    }

    return Duration.ofMillis(waitMillis);
}
~~~

This is only the budget calculation; `brokerFacade.awaitNext(cursor, wait)` must be an asynchronous API or run on a dedicated executor. Never block gRPC transport/event-loop threads while waiting on the broker. If the wait budget is zero, return an empty result immediately or a status per the published contract.

Clients should use backoff with jitter when repeatedly receiving `no_event`, preventing thousands of clients from polling at the exact same instant. Wait duration can be tuned with load, while preserving the upper bound and total deadline.

## 6. Leased Subscription Streams

Server-streaming remains suitable when events must be pushed with low latency. The difference is that the stream has an explicit lease or maximum lifetime:

- Each session has a `max_session_age` or lease expiry.
- The session caps pending event count and pending byte volume.
- The client sends a cursor/last acknowledged sequence on reconnect.
- The server closes the session gracefully when the lease expires or before a rolling shutdown.
- The client reconnects with jitter and resumes from the confirmed cursor.
- The server enforces quotas per authenticated caller/tenant.

Example: a session lives at most 5 minutes. Before closing, the server provides the final cursor/checkpoint under agreed semantics. The client opens a new session and continues from the appropriate position. Do not tie the broker consumer's lifecycle to individual sessions; background consumers continue managing offsets independently.

If a stream expires while unacknowledged events exist, the client must be able to receive those events again. This is why cursors/acknowledgements and idempotent processing matter more than trying to keep sockets open forever.

## 7. Bounded Queues and Backpressure

The broker can emit messages faster than a client reads. If the bridge pushes every event into an unbounded queue, a single slow client can grow the heap until the service hits OOM.

Each session needs bounds on:

- Maximum events in the queue.
- Maximum total payload bytes.
- Maximum age of queued events.
- Maximum concurrent sessions per principal/tenant.
- Maximum send rate if business quotas apply.

With gRPC Java, `ServerCallStreamObserver.isReady()` indicates whether the transport can accept more messages without exceeding current buffering thresholds; `setOnReadyHandler()` notifies when readiness changes. When not ready, hold events in the bounded queue and wait for the callback; do not keep calling `onNext()` without bound.

~~~java
void drain(
        ServerCallStreamObserver<Event> stream,
        Queue<Event> pending) {

    while (stream.isReady()) {
        Event next = pending.poll();
        if (next == null) {
            return;
        }
        stream.onNext(next);
    }
}
~~~

This snippet only illustrates the drain loop; in a real application, the queue must be thread-safe or accessed exclusively from one serial executor. The `setOnReadyHandler` callback must be short and never block waiting on the broker. Use one sender/serial executor per session so multiple threads never call `onNext` concurrently.

When the queue fills, enforce an explicit policy:

| Policy | When appropriate | Consequence |
| --- | --- | --- |
| Pause broker consumption | Consumer can pause a partition/subscription without affecting other subscribers. | Backpressure propagates back to broker; avoid stalling an entire consumer group. |
| Persist and deliver later | Events must be durably retained and subscribers can resume. | Requires storage/cursors and cleanup of acked data. |
| Disconnect slow subscriber | Subscriber must reconnect and resume from cursor. | Frees RAM; must handle duplicates on reconnect. |
| Policy-based drop | Only for best-effort events where loss is acceptable. | Must clearly publish semantics and track dropped-event metrics. |

Never silently drop important events when a queue is full. Return an error or close the stream with a recoverable status such as `RESOURCE_EXHAUSTED` along with reconnect/resume guidance per contract.

## 8. Broker Acknowledgement Is Not gRPC Delivery Acknowledgement

Calling `responseObserver.onNext(event)` does not prove the client received or processed the event. Likewise, the server writing an HTTP/2 frame does not mean the client application committed the data.

Define precisely when broker messages are acked/committed:

- Ack immediately on reading from broker: risks losing events if the service crashes before sending/persisting durably.
- Ack after placing in an in-memory queue: still risks losing events if the process crashes before the queue drains.
- Ack after persisting to a durable store/outbox: recoverable after crashes, but requires cursor management and cleanup.
- Ack after application acknowledgement: increases end-to-end reliability, but requires an ack protocol, timeouts, retries, and deduplication.

Under at-least-once requirements, occasional redelivery is accepted; the client handles idempotently via event ID/sequence. If the server must know business processing finished, the client must send an application-level acknowledgement. Calling `onNext()` is not exactly-once delivery.

## 9. Cursors, Resumption, and Duplicate Handling

A subscription can be interrupted by networks, deploys, deadlines, or lease expiries. Clients should persist the last successfully processed cursor/offset and send it on reconnect:

~~~protobuf
message SubscribeRequest {
  string topic = 1;
  string resume_cursor = 2;
}

message EventEnvelope {
  string event_id = 1;
  string cursor = 2;
  bytes payload = 3;
}

message AckRequest {
  string subscription_id = 1;
  string event_id = 2;
  string cursor = 3;
}
~~~

Cursors must have clear semantics: broker offset, per-partition sequence, or an opaque token managed by the bridge. With multiple partitions, a single scalar cursor may not suffice; use an offset vector/map or a server-encoded opaque checkpoint.

Clients update the last acknowledged cursor only after processing the event to the required durability level. Updating the cursor before committing business state risks losing events on crash. Committing business state first and crashing before ack causes redelivery; deduplication by event ID handles that case.

Do not use an RPC request ID as a cursor. Request IDs correlate logs for one call; cursors mark progress within an event stream.

## 10. Bounded Session Pattern in Spring gRPC

A gRPC service should not spin up a broker consumer inside each `subscribe()` call. A Spring-managed singleton `EventHub` receives events from a background consumer, then registers sessions with dedicated queues and leases:

~~~java
@GrpcService
public final class EventSubscriptionService
        extends EventSubscriptionGrpc.EventSubscriptionImplBase {

    private static final Duration MAX_SESSION_AGE =
            Duration.ofMinutes(5);

    private final EventHub eventHub;
    private final ScheduledExecutorService scheduler;
    private final Executor serialExecutor;

    public EventSubscriptionService(
            EventHub eventHub,
            ScheduledExecutorService scheduler,
            Executor serialExecutor) {
        this.eventHub = eventHub;
        this.scheduler = scheduler;
        this.serialExecutor = serialExecutor;
    }

    @Override
    public void subscribe(
            SubscribeRequest request,
            StreamObserver<EventEnvelope> responseObserver) {

        ServerCallStreamObserver<EventEnvelope> stream =
                (ServerCallStreamObserver<EventEnvelope>) responseObserver;

        SubscriptionSession session = eventHub.openSession(
                request.getTopic(),
                request.getResumeCursor(),
                256,                 // max pending events
                2 * 1024 * 1024);    // max pending bytes

        session.attach(stream, serialExecutor);
        stream.setOnReadyHandler(session::scheduleDrain);
        stream.setOnCancelHandler(session::cancel);
        session.scheduleDrain(); // process events already present before onReady transitions state

        scheduler.schedule(
                session::expireGracefully,
                MAX_SESSION_AGE.toMillis(),
                TimeUnit.MILLISECONDS);
    }
}
~~~

`EventHub`, `SubscriptionSession`, and the sender here are application abstractions; they must enforce bounded queues, serialize all stream-write callbacks, avoid blocking broker threads, and ensure idempotent cleanup. `expireGracefully()` should stop accepting new events for the session, flush what fits within a bounded budget, record a checkpoint per contract, and call `onCompleted()` on the sender executor. If a session is cancelled, send no further events and release queues/listeners.

Production code must handle synchronous errors when opening a session, cancel the expiry schedule when a session already closed, handle sender exceptions, and handle races among `onReady`, `cancel`, and `expire`. Use a terminal guard so `onCompleted`/`onError` is never called multiple times. Never retain `SubscriptionSession` in maps after terminal cleanup.

## 11. Deadlines, Idle Timeouts, and Keepalive

These three mechanisms do not replace one another:

- **RPC deadline:** total time limit for a single call. When expired, the client ends the call and the server receives cancellation if transport/context propagates it.
- **Application idle timeout:** limit on how long a session goes without events or progress per policy.
- **HTTP/2 keepalive:** checks connection responsiveness at the transport layer; does not prove the broker has events or the client is processing them.

For bounded long polling, the deadline should exceed `max_wait` plus a margin for serialization and response delivery. For subscription streams, use leases/max session age and reconnection rather than relying on an unbounded deadline-free RPC. Apply idle timeouts only when semantics permit; a valid subscription may legitimately see no events for a long stretch.

Proxies may configure different idle timeouts/maximum stream durations than the server. Align client/server/proxy settings, and clients must handle `DEADLINE_EXCEEDED`, `CANCELLED`, and `UNAVAILABLE` via a jittered reconnect policy using their cursor.

## 12. Cancellation and Graceful Shutdown

When a client cancels or disconnects:

1. Stop draining the queue and call `onNext` no further.
2. Remove the session from the event hub.
3. Cancel registered timers/heartbeats and callbacks.
4. Release queues, buffers, and correlation state.
5. Do not tear down shared broker consumers just because one subscriber left.

During application shutdown or rolling deploys:

- Stop accepting new subscriptions.
- Mark active sessions as expiring soon.
- Allow flushing/acking within a bounded drain window.
- Close streams cleanly or with a documented status.
- Clients reconnect after jittered backoff and resume from their cursor.
- The broker consumer commits offsets per durability/ack policy, never merely because a gRPC socket closed.

If a session closes due to server shutdown, clients must distinguish reconnectable errors from terminal business failures. Do not turn every disconnect into `OK` if clients might mistakenly conclude the stream finished delivering all data.

## 13. Session Capacity and Quotas

Even leased streams can overwhelm a service if session count is unbounded. Enforce:

- Max active sessions service-wide.
- Max sessions per authenticated principal/tenant.
- Max pending events/bytes per session.
- Max session age and reconnect rate.
- Session creation rate limits to prevent reconnect storms.
- Max event size and total bytes sent per session.

When quotas are exceeded, return `RESOURCE_EXHAUSTED` or reject registration per contract. You can attach retry-after or retry hints in metadata/trailers if clients understand the semantics; never send arbitrary unbounded wait times.

Derive tenant identity from the authenticated principal, never trusting self-declared tenant IDs in requests. Request IDs, cursors, and event IDs are not proof of authorization.

## 14. Metrics and Alerting

Track signals showing whether streams are actually making progress:

| Metric | Meaning |
| --- | --- |
| `active_subscription_sessions` | Number of currently open gRPC subscription sessions. |
| `subscription_session_duration` | Session duration prior to termination. |
| `subscription_session_expired_total` | Sessions closed due to lease expiration. |
| `subscription_cancelled_total` | Sessions cancelled/disconnected by clients. |
| `pending_events` / `pending_bytes` | Queue depth and bytes awaiting transmission. |
| `oldest_pending_event_age` | Age of the oldest event sitting in a queue. |
| `broker_consumer_lag` | Gap between broker head and committed offset. |
| `event_delivery_attempts` / `redeliveries` | Event send and redelivery counts. |
| `slow_consumer_disconnects_total` | Subscribers disconnected for failing to keep up. |
| `session_reconnects_total` | Reconnect rate after lease expiry/disconnects. |

Read queue depth alongside broker lag and delivery rate. Growing queues with flat broker lag may point to slow clients; rising broker lag across all sessions may mean the consumer cannot keep pace. Rising active sessions paired with high reconnect rates can signal overly short leases or mismatched proxy timeouts.

Labels should include service, method, normalized topic, and bounded outcomes. Never put request ID, event ID, cursor, user ID, or session ID into metric labels. Use logs/traces to investigate individual sessions.

## 15. Testing Time-Bounded Bridges

Tests should cover both broker semantics and gRPC lifecycle:

1. Long poll with event: event returns before `max_wait` and cursor updates per contract.
2. Long poll without event: RPC returns `no_event` in finite time without holding the call indefinitely.
3. RPC deadline shorter than wait budget: client receives `DEADLINE_EXCEEDED`; server cleans up session/waiter.
4. Subscription lease expires: server closes stream, client reconnects with acked cursor.
5. Client cancels: session is removed from event hub, queues and listeners are freed.
6. Slow consumer: `isReady` false, queue stays within max events/bytes, and overflow policy executes.
7. Broker burst: consumer thread does not block waiting on gRPC clients; queues/lag reflect load.
8. Broker ack: crash before/after durable handoff behaves per the chosen delivery guarantee.
9. Duplicate delivery: client handles repeated events via event ID/idempotency.
10. Rolling shutdown: sessions drain within bounds, reconnects do not trigger storms.
11. Multiple subscribers: global and per-principal quotas are enforced.
12. Multiple partitions: resume cursor restores exact positions across all partitions.

Use latches/barriers and controllable fake brokers instead of `Thread.sleep()` for deterministic event/timeout assertions. Supplement with integration tests using real or containerized brokers to verify commits, rebalances, redeliveries, and partition semantics; in-process gRPC tests do not verify these properties.

## 16. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Stream stays open forever without events | No deadline, lease, or idle policy. | Use bounded long polling or leased subscription sessions. |
| Creating a broker consumer per stream | Couples broker lifecycle to each caller. | Use background consumers and a shared event hub when semantics allow. |
| Heap grows with slow clients | Unbounded queues or ignoring `isReady`. | Bounded queues, byte caps, and slow-consumer policy. |
| Broker acked, yet client never processed event | Treating `onNext` as delivery/business acknowledgement. | Durable handoff or explicit application ack. |
| Events lost after restart | Acking broker while data only lives in RAM. | Persist before acking or use proper offsets/transactions. |
| Events processed twice | Reconnect/resume without deduplication. | Event IDs, cursors, and idempotent handlers. |
| Keepalive active while stream makes no progress | Confusing transport health with application progress. | Monitor event age, queues, broker lag, and leases. |
| Reconnect storm after deploy | All sessions reconnect simultaneously. | Jittered lease/drain and jittered client backoff. |
| One subscriber exhausts resources | No session quota or byte cap. | Quotas per principal/tenant and global capacity limits. |

## 17. Practice Exercises

1. Design a `SubmitCommand` API returning `operation_id` and `GetOperation` to track asynchronous broker outcomes.
2. Write a bounded long-poll method with max wait, deadline margin, and `no_event` outcome.
3. Design a server-streaming subscription with max session age, resume cursor, and bounded queue.
4. Use `ServerCallStreamObserver.isReady()`/`setOnReadyHandler()` to drain the queue under flow control.
5. Simulate a broker burst and a slow client; verify the queue never exceeds event/byte caps.
6. Decide whether to ack the broker at durable handoff or application acknowledgement; document the delivery guarantee.
7. Test cancellation, deadlines, lease expiry, reconnects, duplicate events, and graceful shutdown.
8. Build a dashboard for active sessions, queue bytes, oldest event age, broker lag, redeliveries, and slow-consumer disconnects.

After this lesson, you should know how to decouple broker consumers from gRPC sessions, choose bounded long polling or leased subscriptions, and manage queues/cursors/acknowledgements according to delivery guarantees. Streams can stay alive long enough to meet latency goals, but they must have clear limits, resumption capability, and cleanup so messaging bridges in Spring gRPC systems never hold resources indefinitely.
