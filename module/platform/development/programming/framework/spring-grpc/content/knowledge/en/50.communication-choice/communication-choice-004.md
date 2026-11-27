# Choosing Server Streaming for Continuous Data

## Learning Objectives

After this lesson, you can:

- Identify workloads suited for server-streaming RPC.
- Distinguish server streaming from polling, SSE, WebSocket, bidirectional streaming, and messaging.
- Design Protobuf contracts for subscriptions and continuous data updates.
- Manage flow control, bounded buffers, cancellation, and deadlines.
- Design reconnect/resume using sequence numbers or cursors at the application layer.
- Evaluate the impact of long-lived streams on load balancing, scaling, and shutdown.
- Test streaming through a Spring gRPC server using a generated client stub.

## 1. The Continuous Data Problem

Some clients need to receive data as soon as the server has changes: market prices, order status, processing progress, device telemetry, or inventory updates. If a client continuously calls an API to ask for new data, the system creates many requests even though most polls have no changes. This increases load, adds latency between polling intervals, and forces the client to choose a polling cadence.

**Server streaming** lets a client send one subscription request, after which the server sends multiple response messages over the same RPC. The server proactively emits data when updates occur; the client does not need to send a new request per message.

In **SPRING_GRPC**, server streaming fits service-to-service or backend clients needing an update stream with Protobuf data types, gRPC statuses, metadata, and an explicit lifecycle. It is an option for continuous data when the flow moves primarily from server to client.

Server streaming does not automatically turn into a durable event store. If an offline client needs to read back all missed events, you must add a log/cursor or use a message broker/event platform as the data source.

## 2. How Does a Server-Streaming RPC Work?

In Protobuf, a server-streaming method takes one request and declares the response as a stream:

~~~proto
rpc WatchPrices(WatchPricesRequest) returns (stream PriceUpdate);
~~~

Basic lifecycle:

1. The client opens the RPC and sends a WatchPricesRequest.
2. The server authenticates, checks the subscription, and subscribes to the data source.
3. The server emits multiple PriceUpdates over the same call.
4. The server finishes with onCompleted() when a finite stream completes, or onError() when an error occurs.
5. The client can cancel the call when it no longer needs data.

A server-streaming RPC can be finite or long-lived. For instance, downloading a report in chunks is typically finite; a market price subscription can last until the client cancels, the deadline expires, or the server closes the connection.

Server streaming is unidirectional for data after the initial request. If the client needs to send control commands frequently within the same call, consider bidirectional streaming or separating commands into dedicated unary RPCs.

## 3. When Should You Choose Server Streaming?

Server streaming is appropriate when:

- The client needs to receive multiple updates from an initial subscription or query.
- Data flows primarily from server to client.
- The client can process each message upon arrival without waiting for the entire result.
- You want to reduce polling and keep a single RPC with a clear lifecycle.
- Rate, buffers, and stream lifetime can be bounded.
- Both client and server support gRPC and HTTP/2.

Examples: a monitoring service subscribes by device_id and the server pushes new statuses; a backend tracks batch progress and the server emits completion percentages; a trading client subscribes by symbol and receives each price change.

Do not choose server streaming just because the dataset has many records. If the client needs to fetch a static collection, pagination over unary RPC is usually simpler. If transferring large files, chunked upload/download may fit, but resume, checksums, and size limits must be designed separately.

## 4. Comparing with Polling, SSE, WebSocket, and Messaging

| Mechanism | Data Direction | Best Fit When | Limitations to Consider |
| --- | --- | --- | --- |
| REST Polling | Client asks periodically | Data changes infrequently, update latency is not critical | Wasted requests; polling interval introduces delay. |
| gRPC Server Streaming | Server sends multiple messages after one request | Backend/gRPC clients needing typed feeds and RPC statuses | Stream is tied to connection/call; reconnect and replay must be designed. |
| SSE | Server pushes one-way events to browser | Web browsers needing updates over simple HTTP | One-way; browsers/API gateways must support long-lived streams. |
| WebSocket | Bidirectional | Browsers/apps needing two-way real-time communication | Must define message contract, auth, heartbeat, and flow control at the application layer. |
| Bidirectional gRPC | Bidirectional over one RPC | Both client and server need to send messages continuously | More complex than server streaming; requires managing both directions and backpressure. |
| Message broker/event log | Producer emits, consumer reads | Buffering, independent consumers, replay, or durable fan-out needed | Adds a broker, eventual consistency, and consumer operations. |

Browsers do not call native gRPC directly the way Fetch calls REST. If the client is a browser, consider SSE, WebSocket, or gRPC-Web depending on contracts and proxies. For consumers that need to receive events while offline and replay from older offsets, a broker/event log fits better than a pure RPC stream.

## 5. Server-Streaming Subscription Architecture

~~~mermaid
flowchart LR
  C["gRPC client"] -->|"Watch request"| S["Spring gRPC service"]
  S -->|"Subscribe"| F["Domain feed / event source"]
  F -->|"Updates"| S
  S -->|"Response stream"| C
  C -->|"Cancel / deadline"| S
~~~

The service receives the request, verifies access permissions, subscribes to the feed, and forwards each update to the response observer. When the call is canceled or the deadline expires, the service must unsubscribe and stop related work.

If the data source already has an event log, the service can read from a cursor and then transition to live updates. If the source only emits events in memory, offline clients may miss data; in that case, the contract must state clearly that the stream only delivers data from the time of subscription.

## 6. Designing a Protobuf Contract for a Continuous Feed

Example of a service emitting prices by symbol:

~~~proto
syntax = "proto3";

package acme.market.v1;

option java_package = "com.acme.market.grpc";
option java_multiple_files = true;

message WatchPricesRequest {
  string symbol = 1;
  int64 resume_after_sequence = 2;
  bool include_snapshot = 3;
}

message PriceUpdate {
  string symbol = 1;
  int64 sequence = 2;
  int64 price_minor_units = 3;
  string currency_code = 4;
  int64 published_at_epoch_millis = 5;
}

service MarketData {
  rpc WatchPrices(WatchPricesRequest) returns (stream PriceUpdate);
}
~~~

symbol identifies the data source. sequence helps detect gaps, duplicates, and order. resume_after_sequence is a contract-defined cursor for the client to request continuation after an already-received update. include_snapshot lets the client request the current state before receiving new updates.

Use integers in the smallest currency unit instead of floating-point numbers to avoid floating-point rounding errors. Clearly define currency, units, timezone, and timestamp meaning. Do not use timestamps as sequence numbers because multiple updates can share the same timestamp or clocks across nodes may drift.

If the server does not support resume, omit the cursor field or return a clear error; do not mislead the client into thinking sending a sequence enables server replay.

## 7. Snapshots and Live Updates Must Not Leave Gaps

A common bug is when the server reads the current snapshot first and registers the listener afterward. If data changes between the two operations, the client misses that update.

There are two safe approaches:

- The data source provides an atomic operation: fetch the snapshot together with its log/sequence position, then continue reading from that position.
- Use a cursor-backed event log: determine the snapshot offset, emit events after that offset, and then switch to tail/live.

For example, the client receives a snapshot at sequence 100, and then the server emits sequence 101 onward. If the server cannot guarantee a seamless transition, the client needs to detect gaps and call a snapshot/resync API.

Do not claim server streaming inherently guarantees snapshot consistency. That is a semantic property of the domain feed or event store and must be designed and tested separately.

## 8. Implementing the Server Service in Spring gRPC

The generated base class provides the method receiving the request and the response StreamObserver. The service is registered with the gRPC server according to the mechanism of the Spring starter in use:

~~~java
final class MarketDataGrpcService
        extends MarketDataGrpc.MarketDataImplBase {
    private final PriceFeed priceFeed;

    MarketDataGrpcService(PriceFeed priceFeed) {
        this.priceFeed = priceFeed;
    }

    @Override
    public void watchPrices(
            WatchPricesRequest request,
            StreamObserver<PriceUpdate> responseObserver) {
        // Validate symbol, access permissions, and cursor.
        // Subscribe to the feed and emit updates through responseObserver.
        // Cancel the subscription when the call is canceled or ends.
    }
}
~~~

This is a skeleton showing the service boundary; feed subscription and flow control depend on the application's domain API. Do not store StreamObserver in a singleton field shared across clients. Each RPC needs its own state including subscription, queue, cancellation, and cursor.

The service should not block a Netty event loop waiting for data. Register asynchronous callbacks or publishers; any blocking work must run on an appropriate, bounded executor.

## 9. Cancellation Must Unregister the Subscription

A client can stop receiving data at any time. On the server side, you can use ServerCallStreamObserver to monitor cancellation:

~~~java
ServerCallStreamObserver<PriceUpdate> call =
    (ServerCallStreamObserver<PriceUpdate>) responseObserver;

AtomicBoolean closed = new AtomicBoolean();
PriceFeed.Subscription subscription =
    priceFeed.subscribe(request.getSymbol(), update -> {
        if (!closed.get() && !call.isCancelled()) {
            // Enqueue update into a bounded outbound queue.
        }
    });

call.setOnCancelHandler(() -> {
    closed.set(true);
    subscription.close();
});
~~~

This snippet illustrates lifecycle handling and the ServerCallStreamObserver.setOnCancelHandler() API. In a complete implementation, cancellation registration must be coordinated with subscription creation so you do not miss cases where the call is canceled during setup. When the data source completes or errors, the service must also close the subscription and send exactly one terminal signal.

Do not merely check call.isCancelled() whenever an event arrives while forgetting to unregister the listener. Without closing the subscription, the feed continues holding callbacks and client objects after the RPC has ended.

## 10. Flow Control and Bounded Buffers

The data source may emit faster than the client consumes. If the server keeps calling onNext() and accumulates unbounded unsent messages, heap usage can grow until the process is overloaded.

In gRPC Java, ServerCallStreamObserver.isReady() indicates whether the transport can currently accept more messages without excessive buffering. setOnReadyHandler() allows the server to resume draining when the call becomes ready.

A stream producer should:

- Place updates into a queue bounded by message count or bytes.
- Drain only while isReady() is true.
- Stop draining when the queue is empty or the transport is no longer ready.
- Register an on-ready handler to resume sending when the transport is ready.
- Define an overflow policy when the queue is full: drop/coalesce replaceable data, write to a log for replay, or terminate the stream with an appropriate status.

The client can also control how many response messages it permits before requesting more. With an async stub, configure manual inbound flow control in beforeStart:

~~~java
AtomicReference<ClientCallStreamObserver<WatchPricesRequest>> callRef =
    new AtomicReference<>();

stub.watchPrices(request, new ClientResponseObserver<>() {
    @Override
    public void beforeStart(
            ClientCallStreamObserver<WatchPricesRequest> call) {
        call.disableAutoRequestWithInitial(1);
        callRef.set(call);
    }

    @Override
    public void onNext(PriceUpdate update) {
        processAndPersist(update);
        callRef.get().request(1);
    }

    @Override
    public void onError(Throwable error) {
        handleStreamFailure(error);
    }

    @Override
    public void onCompleted() {
        markStreamComplete();
    }
});
~~~

The example requests one more message after finishing the current message. If processing asynchronously, call request(1) only after the worker completes or accepts the message into a bounded queue. Do not request more messages before capacity is available, otherwise manual flow control loses its purpose.

Never use an unbounded queue. For price feeds, you may keep only the latest price per symbol if the contract allows skipping intermediate updates. For audit/event streams, never drop arbitrarily; use a durable log and cursor so consumers can re-read.

All calls to onNext, onError, and onCompleted for the same observer must be serialized. If the feed invokes callbacks concurrently from multiple threads, use a serial executor or per-stream synchronization.

## 11. Receiving a Stream on the Client with an Async Stub

The client uses the generated async stub and StreamObserver to receive each message:

~~~java
List<PriceUpdate> updates = new CopyOnWriteArrayList<>();
AtomicReference<Throwable> failure = new AtomicReference<>();
CountDownLatch terminal = new CountDownLatch(1);

MarketDataGrpc.MarketDataStub stub =
    MarketDataGrpc.newStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS);

stub.watchPrices(
    WatchPricesRequest.newBuilder()
        .setSymbol("ACME")
        .setIncludeSnapshot(true)
        .build(),
    new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate update) {
            updates.add(update);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });
~~~

This is a finite stream example for testing. Continuous feeds may never call onCompleted() until the client cancels or the server terminates. Do not wait indefinitely on a terminal latch for long-lived subscriptions; use cancellation, deadlines, and application shutdown conditions.

The onNext() callback should return quickly. If you must write to a database or call another service, offload the work to a bounded executor/queue; do not block the callback thread for long and do not create an unbounded queue.

## 12. Canceling the Stream from the Client

To proactively cancel a server-streaming call, the client can use ClientResponseObserver and hold a reference to ClientCallStreamObserver:

~~~java
AtomicReference<ClientCallStreamObserver<WatchPricesRequest>> callRef =
    new AtomicReference<>();
CountDownLatch firstUpdate = new CountDownLatch(1);

stub.watchPrices(
    WatchPricesRequest.newBuilder().setSymbol("ACME").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchPricesRequest> call) {
            callRef.set(call);
        }

        @Override
        public void onNext(PriceUpdate update) {
            firstUpdate.countDown();
        }

        @Override
        public void onError(Throwable error) {}

        @Override
        public void onCompleted() {}
    });

if (firstUpdate.await(5, TimeUnit.SECONDS)) {
    callRef.get().cancel("client no longer needs feed", null);
}
~~~

In production code, validate the reference before canceling and handle the case where the first message is never received. Cancellation is the call termination signal; the server must propagate that signal to the feed subscription and related workers.

Do not treat closing the channel as the only way to stop a subscription. If the channel is shared by multiple RPCs, cancel the specific call so other RPCs are unaffected.

## 13. Deadlines and Stream Lifetime

A gRPC deadline bounds the lifetime of an RPC. For finite server streaming, set the deadline according to expected processing time. For long-lived subscriptions, finite deadlines are still worth considering: when the deadline expires, the call ends and the client opens a new call if it still wants data.

You can design streams as bounded sessions, such as 5 minutes, after which the client reconnects with a cursor. This helps rotate connections, refresh credentials, and avoid holding infinite streams through proxies/load balancers.

Do not omit deadlines just because a stream is expected to run long. If a long-lived subscription is needed, define lease/session duration, reconnect policy, cursors, and how authentication is refreshed.

## 14. Heartbeats and Keepalive

Two mechanisms are frequently confused:

- **HTTP/2 keepalive ping** checks whether the transport/connection is alive per client/server settings.
- **Application heartbeat message** is a message in the Protobuf stream indicating the feed or application session is still progressing.

Keepalive does not prove business data is fresh. A connection can be alive while the source feed has stopped emitting events. Conversely, not every feed needs heartbeats if idle detection is not required.

If you add heartbeats to the schema, clearly define whether heartbeat messages carry a sequence number, whether the client counts them toward business progress, and the server emission interval. Avoid overly frequent heartbeats that add load when many subscriptions exist.

## 15. Reconnect and Resume After Disconnection

Server streaming does not automatically replay missed messages. When a connection resets or the server restarts, the client receives a terminal error and must open a new RPC.

To resume safely:

1. Every update has a stable sequence/event ID.
2. The client persists the last successfully processed cursor.
3. On reconnect, the client sends resume_after_sequence or a cursor token.
4. The server replays events after the cursor from a source with retention.
5. The client deduplicates if an update is re-sent after a crash between processing and saving the cursor.
6. If the cursor is outside retention, the server returns a status requiring a snapshot/resync.

Cursors should be scoped to the appropriate partition/stream/tenant and must not allow clients to read unauthorized data. Do not use a single global sequence if symbols or tenants have independent ordering.

If the source does not retain events, it can only resume from the latest state or a snapshot. The contract must state clearly that intermediate data may be lost.

## 16. Ordering and Consistency

Server streaming delivers messages in the order the server calls onNext() on the call. However, business order also depends on the data source and concurrency:

- Multiple producers may emit events concurrently.
- Events from different partitions have no natural total order.
- Timestamps do not guarantee order when clocks skew.
- Parallel client processing can complete side effects out of receipt order.

If ordering per symbol/order/device is required, assign sequences per aggregate and serialize publishing within that scope. Clients check for increasing sequences, detect gaps, and request resyncs. Clearly define whether updates are latest snapshots or delta events; with deltas, missing a single message can corrupt state.

## 17. Authentication and Authorization for Subscriptions

A subscription can live much longer than a unary request. When opening a stream, the server must authenticate metadata/credentials and authorize access to the requested symbol, tenant, or device.

Essential practices:

- Never trust filters or tenant IDs solely sent by the client.
- Verify permissions for the resource in the request.
- Limit concurrent streams per principal/tenant.
- Account for credential expiry during long-lived streams; reconnects may need fresh tokens.
- Terminate streams when permissions are revoked if immediate enforcement is required.
- Never log bearer tokens.

Metadata validated at call start is not automatically refreshed mid-stream. If policy requires immediate permission updates, implement a revocation signal or bounded session duration.

## 18. Scaling, Load Balancing, and Connection Draining

A long-lived stream is usually pinned to the backend selected when the RPC began. A load balancer does not automatically migrate an open stream to another instance when a backend is overloaded or draining.

This impacts operations:

- One backend may hold many long-lived subscriptions.
- Evenly distributing RPC counts does not guarantee even subscriber counts or message rates.
- During deployments, the server needs graceful shutdown and a stream-termination policy.
- Clients must reconnect/resume when a backend drains or restarts.
- Proxies/load balancers need timeouts and HTTP/2 support aligned with stream lifetimes.

Monitor active stream counts, subscribers per backend, outbound queue bytes, message rates, and stream lifetimes. During rolling deploys, signal clients to reconnect with an appropriate status and cursor to avoid data loss.

## 19. Testing Server Streaming Through Spring

Integration tests should invoke the server via the generated stub and running gRPC transport. Tests should verify:

1. The client sends a subscription with a valid filter.
2. The server emits the snapshot or updates per contract.
3. Messages have sequences/payloads in the expected order.
4. The client receives an error with the appropriate status when the filter or authorization is invalid.
5. Client cancellation causes the server to cancel the subscription.
6. Deadlines terminate the stream within a bounded time.
7. Reconnecting with a cursor neither drops nor duplicates side effects.
8. Channels close and the server follows the Spring lifecycle properly.

Use CountDownLatch, queues, and finite timeouts to synchronize callbacks. Do not use Thread.sleep() to wait for events. Tests for continuous feeds should control a fake data source, emit events on demand, and assert the observer receives the expected number of messages.

## 20. Observability for Continuous Streams

A streaming RPC can run for minutes, so per-call metrics alone are insufficient. Monitor:

- Active stream count by service/method/backend.
- Stream duration and disconnect/cancel counts.
- Message rate, bytes sent, and queue depth.
- Reconnect count, resume success, and expired cursor count.
- Sequence gaps, duplicates, and resync count.
- Deadline exceeded, RESOURCE_EXHAUSTED, and UNAVAILABLE.
- Subscriber lag relative to the event source.

Use trace/correlation IDs to link subscribe and reconnect attempts. Do not use high-cardinality symbols, user IDs, or stream IDs as metric labels if unbounded; record them in controlled logs/traces.

## 21. Common Mistakes

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Polling too aggressively for continuously changing feeds | Wasted requests and stale intervals between polls | Consider server streaming or SSE. |
| Using server streaming when the client needs continuous control messages | No client-to-server channel after the initial request | Use bidi or separate control RPCs. |
| Treating a stream as a durable event log | Offline clients miss updates | Use cursors with an event store or broker retention. |
| Unbounded outbound queue | Heap grows when clients are slow | Bounded buffers and an overflow policy. |
| Calling onNext from multiple unsynchronized threads | Races and out-of-order observer calls | Serialize callbacks per stream. |
| Not unregistering subscriptions on client cancel | Leaked listeners/workers | Register on-cancel cleanup. |
| Infinite streams with no deadline/session policy | Connections and credentials stay open too long | Session durations, reconnect, and resume. |
| Relying solely on keepalive to check feed health | Transport is alive while data is stale | Monitor application heartbeats/source progress. |
| Lacking sequences/cursors | Cannot detect gaps or duplicates after reconnect | Event IDs/sequences and a resume contract. |
| Assuming load balancers migrate streams | Backend drain interrupts active calls | Clients reconnect to a new backend. |

## 22. Decision Matrix

| Question | If the answer is "yes" | Direction to consider |
| --- | --- | --- |
| Does data flow primarily from server to client? | Yes | Server streaming is a strong candidate. |
| Does the client need to send messages continuously within the same session? | Yes | Bidirectional streaming. |
| Is the client a browser needing only one-way events? | Yes | SSE or gRPC-Web depending on contract. |
| Do offline clients need durable event replay? | Yes | Broker/event log with cursors. |
| Only need to read latest state at low frequency? | Yes | Unary RPC or polling may be simpler. |
| Can the feed emit faster than consumers process? | Yes | Flow control and bounded buffers are required. |
| Are ordering and gap detection needed after reconnect? | Yes | Sequences/cursors and resync semantics. |

Choose server streaming when the benefits of continuous push outweigh the costs of holding streams, operating long-lived connections, and building reconnect/resume.

## 23. Hands-on Exercise

Design MarketData.WatchPrices in Spring gRPC:

1. Define the request with symbol and cursor, and the response with sequence, price, and timestamp.
2. Implement the server service subscribing to the feed and emitting updates via the response observer.
3. Use ServerCallStreamObserver to detect cancellation and handle readiness.
4. Configure a bounded outbound queue and define the policy for slow clients.
5. Write an async client receiving updates, checking sequences, and canceling the stream.
6. Set a deadline/session duration and reconnect using the cursor after a server restart.
7. Test gapless snapshot-to-live transitions.
8. Verify authorization, subscriber limits, and subscription cleanup.
9. Measure active streams, message rate, queue depth, disconnects, and resume success.

**Completion criteria:** the client receives multiple updates per contract; the server enforces buffers/flow control; cancellation releases subscriptions; reconnect detects gaps/duplicates and never assumes the stream replays automatically.

## 24. Takeaways

- Server streaming uses one request to open a multi-response stream in the server-to-client direction.
- It fits continuous feeds, progress updates, telemetry, and subscriptions where clients need immediate updates.
- Polling, SSE, WebSocket, bidi gRPC, and brokers solve different interaction models; choose by client and durability.
- Protobuf contracts should define clear sequence/event IDs, cursors, and snapshot/resume semantics.
- Snapshot and live subscription transitions must avoid gaps.
- ServerCallStreamObserver.isReady() and on-ready handlers support flow control; outbound buffers must be bounded.
- Cancellation must unregister feed subscriptions and related workers.
- Finite deadlines/session durations help rotate connections and credentials; reconnect/resume requires cursors.
- Long-lived streams are pinned to the selected backend; load balancers do not migrate open streams.
- Test through generated stubs, synchronize callbacks with latches/queues, and verify cleanup.

Choose server streaming for continuous data when clients primarily receive multiple updates from a server over one subscription; combine flow control, cancellation, cursors, and reconnect so streams operate reliably in Spring gRPC.
