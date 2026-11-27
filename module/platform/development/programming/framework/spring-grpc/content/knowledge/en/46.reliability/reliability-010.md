# Recovery after restart

## Learning objectives

After this lesson, you will be able to:

- Distinguish graceful shutdown, process crash, and restart of a gRPC server.
- Explain how `ManagedChannel` reconnects to an endpoint after a server restarts.
- Recognize why an in-flight RPC can fail even when the new server is already ready.
- Choose appropriate retry, wait-for-ready, and deadline settings for new RPCs.
- Protect operations with side effects using idempotency keys.
- Recover streaming sessions using application-layer sequences/cursors.
- Structure readiness, service discovery, and integration tests for restart scenarios.

## 1. Restart is a failure mode you must design for ahead of time

A gRPC server can restart due to a new deployment, container scaling/recreation, process crash, host reboot, or operational maintenance. While the server is down, clients may fail to establish new transports; in-flight RPCs can be cut off, and new RPCs may have to wait or fail.

In **SPRING_GRPC**, reliability is not merely the server starting back up successfully. Clients need to know when they can call again, whether the prior operation completed, where a stream should resume from, and services must only be marked ready once required dependencies are operational.

Post-restart recovery spans multiple layers:

- Transport reconnect to re-establish connections to endpoints.
- RPC retry or wait-for-ready to handle eligible calls appropriately.
- Idempotency to avoid duplicating side effects when prior outcomes are unknown.
- Persistence and checkpoints to restore business state.
- Readiness/service discovery to route traffic only to ready instances.

No single mechanism guarantees all of these layers alone.

## 2. Graceful shutdown and process crashes

Different stop modes behave differently:

| Situation | Behavior | Impact on clients |
| --- | --- | --- |
| Graceful shutdown | Server stops accepting new calls and gives in-flight calls a drain window to finish | In-flight calls can complete; new calls must route to another instance or wait. |
| Forced shutdown | Server requests cancelling active calls and closes transport | In-flight calls may receive errors or cancellations. |
| Process crash / lost node | Server cannot run shutdown lifecycle hooks | Transport breaks; client detects errors and tries to reconnect. |
| Restart on same endpoint | New process binds the exact same address/port | Channel can reconnect and send new RPCs. |
| Restart on new endpoint | Instance address changes | Resolver/load balancer must update endpoints; channel must see the new address. |

Graceful shutdown reduces interrupted RPCs, yet does not guarantee all calls finish. Calls may exceed the drain timeout or fail because a dependency breaks. A process crash gets no chance to run cleanup; any state needed for recovery must have been persisted beforehand.

## 3. ManagedChannel reconnects after the server returns

`ManagedChannel` represents a logical target and manages transports, resolvers, load balancing, and backoff. When a connection drops, the channel can transition through states such as `IDLE`, `TRANSIENT_FAILURE`, `CONNECTING`, and back to `READY` once connectivity is re-established.

If the new server listens on the same target, the client can usually continue using the existing channel. There is no need to create a brand-new channel for every server restart. Reconnect only restores the ability to establish transport; it does not automatically resume an interrupted business operation.

A channel will not automatically discover a new endpoint if the client points directly to an IP/port that changed. In container/orchestrator environments, use DNS/service discovery or a stable resolver so the channel receives the updated endpoint list.

## 4. Channel reconnect does not mean RPCs are replayed

This is the single most important distinction when designing recovery:

- **Reconnect** re-establishes transport for new RPCs.
- **Retry** re-attempts an eligible RPC after a failure.
- **Wait-for-ready** lets a new RPC wait for the channel to return to a sendable state instead of failing immediately while the channel is temporarily unavailable.
- **Resume** restores a stream or workflow from an application-defined checkpoint.

An RPC in flight when the server crashes can fail even if the channel reconnects seconds later. gRPC cannot know whether the server already executed side effects if no response reached the client.

Therefore, never conclude "the client saw `UNAVAILABLE`, so the server did nothing." The server may have committed to the database right before the connection dropped. For operations with side effects, you need an idempotency key or an operation status query API.

## 5. Connectivity state and readiness

gRPC Java exposes connectivity state to inspect a channel:

- `IDLE`: the channel has not needed a transport yet or is idle.
- `CONNECTING`: establishing a connection.
- `READY`: transport is ready to accept RPCs.
- `TRANSIENT_FAILURE`: connection failed temporarily and the runtime will retry with backoff.
- `SHUTDOWN`: the channel has been shut down and cannot accept new calls.

You can observe state while diagnosing issues:

~~~java
ConnectivityState state = channel.getState(true);
log.info("gRPC channel state: {}", state);
~~~

Passing `true` asks the channel to start connecting if currently `IDLE`. In real applications, avoid tight polling loops. You can use `notifyWhenStateChanged` to observe state transitions, though `READY` only describes transport connectivity; it does not prove every business dependency is ready.

If the system enables the gRPC Health Checking Protocol, clients/load balancers can inspect individual service health. The health service should report `SERVING` only when the service can actually accept traffic, and `NOT_SERVING` during startup, draining, or when a mandatory dependency is unready.

## 6. Wait-for-ready for new RPCs

When a server is temporarily unavailable, a new RPC can fail immediately with a transport error. `withWaitForReady()` lets the call wait until the channel can send the request:

~~~java
InventoryServiceGrpc.InventoryServiceBlockingStub recoveryStub =
    InventoryServiceGrpc.newBlockingStub(channel)
        .withWaitForReady()
        .withDeadlineAfter(4, TimeUnit.SECONDS);

GetAvailabilityResponse response =
    recoveryStub.getAvailability(request);
~~~

Wait-for-ready does not grant unlimited time. The deadline still caps total waiting and processing time. If the server does not return before the deadline, the call fails.

Enable wait-for-ready only when waiting makes business sense. If a request is already stale by the time the server recovers, processing it can cause thundering herds or perform unneeded work. Interactive user requests should keep short deadlines; background tasks can use durable queues instead of holding RPCs open.

## 7. Retry after restart

Retry fits failures likely to be transient where the operation is safe to re-run. gRPC Java performs transparent retries in specific cases where the runtime knows the request never reached the application; configured retries can be declared in service config per method.

A retry policy typically defines:

- `maxAttempts`: maximum total executions, including the initial attempt.
- `initialBackoff` and `maxBackoff`: initial wait and maximum cap.
- `backoffMultiplier`: factor by which backoff increases.
- `retryableStatusCodes`: statuses permitted to retry.

Illustrative service config example for an inventory read method:

~~~java
Map<String, Object> retryPolicy = Map.of(
    "maxAttempts", 3.0,
    "initialBackoff", "0.1s",
    "maxBackoff", "1s",
    "backoffMultiplier", 2.0,
    "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
    "name", List.of(Map.of(
        "service", "acme.inventory.v1.InventoryService",
        "method", "GetAvailability")),
    "retryPolicy", retryPolicy);

Map<String, Object> serviceConfig = Map.of(
    "methodConfig", List.of(methodConfig));

ManagedChannel channel = ManagedChannelBuilder
    .forAddress(host, port)
    .defaultServiceConfig(serviceConfig)
    .build();
~~~

Service/method names must match the Protobuf RPC path. Actual configuration must be compatible with your gRPC Java version and resolver. Do not enable retries broadly across every method without analyzing side effects and post-recovery load.

### When can the runtime still retry?

gRPC retries a call only while the runtime remains eligible to replay the call history. Once the client receives response headers, the call is considered committed and the runtime stops retrying it automatically. A call can also become non-retryable if the retry buffer cannot hold the necessary data.

Therefore, the server may have started or even finished a side effect while the client never received a response. A retry policy is not an exactly-once guarantee. For write commands, idempotency keys remain essential even when retries are configured solely for `UNAVAILABLE`.

## 8. Choosing retryable statuses

`UNAVAILABLE` generally matches transient issues like a restarting server or unreachable transport. However, that status does not prove the operation has not run.

Other statuses must be evaluated by semantics:

| Status | Common handling |
| --- | --- |
| UNAVAILABLE | Can retry with limits if the operation is safe. |
| RESOURCE_EXHAUSTED | Retry only with a clear recovery/quota policy; immediate retry can worsen overload. |
| DEADLINE_EXCEEDED | Use caution since the deadline expired and the prior attempt may have finished. |
| ABORTED | May require re-running the transaction at the application layer. |
| INVALID_ARGUMENT | Never retry the same malformed request. |
| UNAUTHENTICATED / PERMISSION_DENIED | Fix credentials/permissions before calling again. |
| FAILED_PRECONDITION | Change business preconditions before retrying. |

Retries need backoff and jitter so multiple clients do not reconnect and retry in lockstep, creating a retry storm. Total retry duration must still fit within the defined RPC or business deadline.

## 9. Idempotency protects side effects

Suppose a client calls `CreateOrder`. The server writes the order successfully, then crashes before the response reaches the client. The client receives `UNAVAILABLE` and cannot tell whether the order was created. If it resends the request and the server fails to recognize the duplicate, two orders may be created.

Idempotency design:

1. The client generates an idempotency key for the logical operation.
2. Every retry attempt of that operation carries the exact same key.
3. The server persists the key alongside the result or processing state in durable storage.
4. When receiving an already-processed key, the server returns the stored result instead of repeating side effects.
5. Storing the key and mutating business state must happen in the same transaction or use a consistent recovery mechanism.

~~~proto
message CreateOrderRequest {
  string idempotency_key = 1;
  string customer_id = 2;
  repeated OrderLine lines = 3;
}
~~~

Never generate a new key per attempt. A fresh key turns a retry into a brand-new operation and eliminates duplicate protection.

## 10. Servers need readiness before accepting traffic

A process that just opened a port is not necessarily ready to handle RPCs. The server may still be connecting to the database, warming caches, registering services, or restoring state.

A safe startup sequence:

1. Initialize the Spring `ApplicationContext` and dependencies.
2. Start the gRPC listener.
3. Verify mandatory dependencies and application state.
4. Register/mark the service `SERVING` once it can accept traffic.
5. Let the resolver/load balancer add the instance to the pool.

When using health checking, update health status across lifecycle stages. Never mark `SERVING` merely because the socket bound. During restarts, clients may reconnect very quickly; readiness prevents requests from hitting an unready instance.

## 11. Graceful shutdown during deployment

Before stopping a server:

- Mark the instance `NOT_SERVING` or remove it from service discovery.
- Stop accepting new RPCs and begin draining.
- Give in-flight RPCs a configured window to complete.
- Cancel long-lived streams or signal clients to reconnect per contract.
- Close dependencies/executors in lifecycle order.

In Spring, starter-managed servers should shut down through the starter/application context lifecycle. Never shut down a shared server from inside a request handler or test method.

Graceful shutdown only reduces disruption; clients still must handle transport errors because processes can crash or exceed drain timeouts. RPC deadlines should be shorter than or compatible with drain windows so calls do not pin resources indefinitely.

## 12. Service discovery and endpoints after restart

If a server restarts on the same address/port, a channel pointing to that endpoint can reconnect once the new listener is ready.

In multi-instance environments:

- Use DNS, a service mesh, or a resolver rather than hardcoding pod IPs in clients.
- The resolver must refresh endpoint lists as old instances leave and new instances appear.
- Load balancers select backends only for new RPCs; open streams typically stay pinned to the old backend.
- When an instance drains, clients need to reconnect and open new RPCs.
- Check proxy and load balancer timeouts/connection-draining settings to avoid unexpected stream cuts.

Do not confuse reconnecting to the same endpoint with discovering a new endpoint. If a channel uses `forAddress` to an old IP, restarting the server at a different IP will not make the channel discover the new address.

## 13. Recovering server-streaming and bidirectional streams

An open stream does not automatically migrate to a new server. When the server restarts, the client receives a terminal error/cancellation and must open a new RPC.

To avoid losing data:

1. Every message carries a stable sequence or event ID.
2. The client persists the last successfully processed cursor.
3. On reconnect, the client sends the cursor so the server resumes from the corresponding position.
4. The server replays events from a retained source and then switches to the live feed.
5. The client deduplicates if the last message is re-sent.
6. If the cursor expired, the server triggers a snapshot/resync.

If the source keeps data solely in process memory, a restart wipes that state. Persist events/checkpoints in a database or event log when recovery must cover data produced while the server was offline.

For bidirectional streams, the client must also recover outbound state: last server-acknowledged sequence, unacknowledged messages, and idempotency keys per operation.

## 14. Session state must not live solely in memory

A server process may hold subscriptions, session maps, or workflow state in memory. When the process restarts, those structures vanish.

Classify state carefully:

- Ephemeral state: rebuildable caches, connections, and observers; safe to lose on restart.
- Durable business state: orders, payments, workflow progress; must live in durable storage.
- Recoverable stream state: cursors, sequences, checkpoints; must be persisted if clients need to resume.
- Derived state: caches/indexes rebuildable from the database or event log.

Never attempt to serialize Netty channels or `StreamObserver`s across restarts. Recover the logical operation/session from durable storage, then establish a fresh RPC/transport.

## 15. Testing restart on the same endpoint

An integration test can start a server on a dynamic port, keep the channel open, stop the server, and bind a new server on that exact port:

~~~java
Server first = NettyServerBuilder.forPort(0)
    .addService(service)
    .build()
    .start();

int port = first.getPort();
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("127.0.0.1", port)
    .usePlaintext()
    .build();

InventoryServiceGrpc.InventoryServiceBlockingStub stub =
    InventoryServiceGrpc.newBlockingStub(channel)
        .withWaitForReady()
        .withDeadlineAfter(5, TimeUnit.SECONDS);

first.shutdown();
if (!first.awaitTermination(5, TimeUnit.SECONDS)) {
    first.shutdownNow();
    throw new IllegalStateException("First server did not stop");
}

Server second = NettyServerBuilder.forPort(port)
    .addService(service)
    .build()
    .start();

GetAvailabilityResponse response = stub.getAvailability(request);
~~~

This is a skeleton for a test fixture owning the servers. Real tests need `try`/`finally` blocks to shut down the channel and second server, and must handle cases where rebinding the port fails. Reuse the same channel to prove reconnect; creating a new channel after restart only proves the new server accepts calls, not that the old channel recovered.

Picking the initial port via `forPort(0)` avoids hardcoding a shared port across the suite. On restart, the fixture deliberately rebinds the actual port to keep the client's endpoint unchanged.

## 16. Testing in-flight RPCs during restart

Create a test handler that blocks on a latch:

1. The client starts an RPC and the server signals the handler was entered.
2. The test stops the server before the handler completes.
3. The client observes the terminal status/error of the in-flight call.
4. The test restarts the server on the same endpoint.
5. The client reuses the old channel to issue a new RPC and verifies success.
6. If the prior operation had side effects, query state by idempotency key to determine whether it committed.

Do not assert that every transport/version always returns the exact same status for an interrupted in-flight call. Depending on when the server stops, the client may see `UNAVAILABLE`, `CANCELLED`, or another deadline/transport error. Assert contract behavior and call termination, then verify recovery on a new call.

## 17. Essential recovery scenarios

An integration test suite should cover:

1. Server graceful restart: new calls succeed once the new server is ready.
2. Server abrupt stop: channel detects transport error and reconnects after restart.
3. Interrupted in-flight unary RPC: client does not assume the operation did not commit.
4. Retryable `UNAVAILABLE`: retries stay bounded by attempts and deadline.
5. Non-retryable status: client does not loop uselessly on bad requests.
6. Wait-for-ready: new calls wait for the server to return or until the deadline expires.
7. Endpoint change: resolver/service discovery supplies the new address.
8. Server-streaming restart: client reconnects with cursor and handles gaps/duplicates.
9. Readiness: instance accepts traffic only after required dependencies are ready.
10. Idempotency: retrying with the same key produces no duplicate side effects.

Use latches and timeouts in tests instead of `Thread.sleep()`. Record server lifecycle events, channel states, invocation counts, and cursors for diagnostics.

## 18. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming channel reconnect replays in-flight RPCs | Lost operations or misunderstood outcomes | Distinguish reconnect from retry. |
| Retrying every UNAVAILABLE without idempotency | Duplicate side effects | Use idempotency keys and operation status. |
| Creating a new channel on every retry | Connection churn and hard-to-observe recovery | Reuse ManagedChannel per target. |
| Omitting deadlines | Calls hang indefinitely if server never returns | Set finite deadlines within latency budgets. |
| Enabling wait-for-ready on every RPC | Stale requests pile up after restart | Enable only when waiting makes sense and with deadlines. |
| Marking readiness immediately on port bind | Traffic arrives before dependencies are ready | Tie health/readiness to application state. |
| Keeping session/sequence only in memory | Restarts destroy resume ability | Persist durable checkpoints/events where required. |
| Expecting streams to auto-resume after restart | Messages lost during downtime | Implement cursors, replay, and deduplication in the app layer. |
| Hardcoding instance IPs | Cannot follow new endpoints | Use DNS/resolvers/service discovery. |
| Testing only new calls after restart | Misses in-flight RPC behavior | Test in-flight calls and new calls separately. |

## 19. Practice exercise

Design recovery for `InventoryService` in Spring gRPC:

1. Build a server fixture that can start/stop on a dynamic port.
2. Create one `ManagedChannel` and reuse it across the restart.
3. Verify a unary RPC works before stopping the server.
4. Stop the server, restart on the same endpoint, and verify a new RPC succeeds over the old channel.
5. Keep an RPC in flight while stopping the server and inspect its terminal status.
6. Add a retry policy solely for safe read methods, with bounded attempts/backoff/deadline.
7. Add an idempotency key to order-creation or reservation commands.
8. If server-streaming exists, add sequences/cursors and test resuming after restart.
9. Mark the service `SERVING` only after dependencies and recovery state are ready.
10. Verify graceful shutdown, channel/server cleanup, and service discovery.

**Completion criteria:** the channel reconnects, new RPCs succeed after restart, in-flight calls follow clear semantics, retries create no duplicate side effects, and stream resumption is verified.

## 20. Key takeaways

- Restarts can be graceful, forced, or caused by process crashes; disruption severity varies.
- `ManagedChannel` can reconnect to the same target, yet does not automatically recover in-flight RPCs.
- Retry, wait-for-ready, and reconnect are three distinct mechanisms; streaming resume requires application logic.
- Deadlines bound total wait and retry duration; backoff avoids retry storms.
- `UNAVAILABLE` can be retried if the operation is safe, yet never proves the server did not execute side effects.
- Idempotency keys protect commands when clients cannot tell whether a prior attempt committed.
- Readiness must reflect real processing capability, not merely that a port is bound.
- Service discovery must refresh endpoints when instances change.
- Long-lived streams need cursors, sequences, replay, and deduplication when zero data loss is required.
- Durable business state must live outside process memory to survive restarts.
- Test graceful/abrupt restarts, in-flight RPCs, new calls, readiness, and resume behavior separately.

Post-restart recovery is reliable when transports reconnect, applications safely re-handle calls, business state is durably persisted, and clients resume workflows from checkpoints instead of assuming a new process retains old in-memory state.
