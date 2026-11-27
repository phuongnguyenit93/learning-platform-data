# Testing failed server instances

A gRPC client typically holds a long-lived channel that can connect to multiple server instances. When an instance stops, loses network connectivity, or is no longer healthy enough to serve, the client must stop sending new RPCs to that instance and continue using the remaining healthy instances. Testing this scenario verifies that the load balancer, resolver, health checking, and retries work together properly.

**Testing failed server instances** focuses on injecting controlled failures, observing how the client detects an unavailable endpoint, verifying that new RPCs shift to a healthy instance, and understanding what happens to in-flight RPCs. This lesson belongs to the **Load balancing** chapter of the **SPRING_GRPC** module: developing gRPC services in the Spring ecosystem with Protocol Buffers contracts, generating Java code, and implementing clients/servers for unary or streaming RPCs; learners handle metadata, deadlines, statuses, interceptors, TLS, integration testing, and performance and reliability monitoring.

## 1. Distinguishing instance failures from request errors

Not every failed RPC means the server instance has failed. An instance may be operating normally while rejecting a request due to invalid data, insufficient permissions, or business state.

| Scenario | Example | Meaning for load balancing |
| --- | --- | --- |
| Instance/process stops | Process killed, container restarted. | Connection to instance drops; subchannel may enter TRANSIENT_FAILURE. |
| Network path failure | Connection reset, lost route, firewall block. | Client cannot communicate with endpoint even if the process is still running. |
| Unhealthy instance | Health service returns NOT_SERVING or readiness probe fails. | Endpoint can be excluded from new RPC selection if health checking is enabled and supported. |
| Overloaded instance | Growing queues, high latency, exhausted connection/database pool. | Requires health/outlier/capacity policies; TCP connection may still stay open. |
| Business error | INVALID_ARGUMENT, PERMISSION_DENIED, NOT_FOUND. | Should not exclude the instance just because of such a request error. |

When testing, define which failure mode is being simulated. Stopping a server, dropping a connection, and setting health to NOT_SERVING exercise different layers. A test that only calls shutdown on a server does not prove health checking or outlier detection works.

## 2. How does the load balancer detect a failed instance?

With client-side load balancing, the resolver supplies an address list. gRPC creates subchannels for endpoints and monitors connection state. The policy chooses an eligible subchannel for RPCs:

~~~text
Name Resolver
     |
     v
Endpoint list: A, B, C
     |
     v
Load Balancing Policy
     |
     +---- Subchannel A: READY
     +---- Subchannel B: READY
     +---- Subchannel C: TRANSIENT_FAILURE
     |
     v
Pick endpoint for each new RPC
~~~

Common connectivity states:

- IDLE: subchannel does not currently have an active connection.
- CONNECTING: establishing a connection.
- READY: connection can accept RPCs.
- TRANSIENT_FAILURE: connection temporarily failed; gRPC may continue reconnecting with backoff.
- SHUTDOWN: subchannel is closed and will not be reused.

With `round_robin`, `READY` subchannels are included in the selection pool. When an endpoint loses connectivity and leaves `READY`, new RPCs are selected from the remaining eligible endpoints. With `pick_first`, the client typically uses one chosen endpoint; switching to another endpoint depends on connectivity states and the resolver/policy.

Failure detection is not necessarily instantaneous. A client may only learn an instance died when an RPC read/write fails or the transport detects a lost connection. Health checking, keepalive, outlier detection, and resolver updates can shorten or alter detection timing, though each mechanism has its own purpose and configuration requirements.

## 3. In-flight RPCs and new RPCs behave differently

The load balancer primarily selects an endpoint for new RPCs. Once a unary RPC has been sent to instance A, it does not automatically transfer the in-flight request to instance B if A dies. In-flight RPCs typically finish with a transport error, such as UNAVAILABLE, or another status depending on where it failed and the last response.

Once the client detects A is no longer available:

1. Subchannel A leaves the READY state.
2. The policy stops picking A for new RPCs while A is not READY.
3. New RPCs can be sent to B or C.
4. If A recovers, the subchannel reconnects and can return to the READY pool.

For streaming RPCs, the entire stream stays attached to the instance that accepted it. If the instance dies, the stream terminates with an error; the load balancer does not move remaining messages to another server. The application must open a new stream and use a sequence number, cursor, or resume token if it needs to continue from where processing left off.

## 4. Setting up multiple server instances for integration tests

To test client-side load balancing over TCP, start at least two independent server instances and have the resolver return addresses for both. Each instance should return an identifier so the test knows which server handled each request:

~~~java
final class InventoryService extends InventoryGrpc.InventoryImplBase {
    private final String instanceId;

    InventoryService(String instanceId) {
        this.instanceId = instanceId;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        responseObserver.onNext(StockReply.newBuilder()
                .setInstanceId(instanceId)
                .setAvailableUnits(10)
                .build());
        responseObserver.onCompleted();
    }
}
~~~

Start the servers on ephemeral ports:

~~~java
Server serverA = NettyServerBuilder.forPort(0)
        .addService(new InventoryService("instance-a"))
        .build()
        .start();

Server serverB = NettyServerBuilder.forPort(0)
        .addService(new InventoryService("instance-b"))
        .build()
        .start();
~~~

The test resolver must return both addresses `127.0.0.1:serverA.getPort()` and `127.0.0.1:serverB.getPort()` under the same target. The channel uses the `round_robin` policy. You can implement the test resolver with `NameResolver.Factory` and `NameResolver.Listener2`, emitting a `ResolutionResult` containing `EquivalentAddressGroup` entries; or use a discovery/test resolver already present in the project. Do not create a separate channel per backend, as doing so bypasses the load balancer's subchannel selection.

Example policy configuration for the channel:

~~~java
Map<String, ?> serviceConfig = Map.of(
        "loadBalancingConfig",
        List.of(Map.of("round_robin", Map.of()))
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("test:///inventory")
        .nameResolverFactory(testResolverFactory)
        .defaultServiceConfig(serviceConfig)
        .usePlaintext()
        .build();
~~~

`testResolverFactory` is a resolver fixture provided by the test. The target scheme must match the scheme supported by the factory. If the runtime has not registered the `round_robin` policy or the resolver does not emit endpoints properly, the channel may never become READY; check for resolver/policy errors rather than letting RPCs wait indefinitely.

## 5. Verifying distribution before injecting a failure

Before stopping an instance, verify the test fixture actually routes traffic to both servers. Send several unary RPCs and collect `instanceId`:

~~~java
Set<String> observedInstances = new HashSet<>();

for (int i = 0; i < 20; i++) {
    StockReply reply = blockingStub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(request);
    observedInstances.add(reply.getInstanceId());
}

assertTrue(observedInstances.contains("instance-a"));
assertTrue(observedInstances.contains("instance-b"));
~~~

This checks the fixture and policy, not an assertion that `round_robin` produces a strict alternating sequence. RPCs can distribute based on READY state and connection timing; small sample sizes may skew. If an instance never appears, inspect resolver results, subchannel connectivity, service config, and server listeners before starting the fault test.

## 6. Simulating an instance stop and verifying failover

After confirming both instances received RPCs, stop A and keep sending new RPCs:

~~~java
serverA.shutdownNow();
assertTrue(serverA.awaitTermination(2, TimeUnit.SECONDS));

// While the client detects that A failed, some attempts may receive UNAVAILABLE.
long failoverEnd = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
boolean reachedB = false;
while (System.nanoTime() < failoverEnd && !reachedB) {
    try {
        StockReply reply = blockingStub
                .withDeadlineAfter(1, TimeUnit.SECONDS)
                .getStock(request);
        reachedB = "instance-b".equals(reply.getInstanceId());
    } catch (StatusRuntimeException failure) {
        if (Status.fromThrowable(failure).getCode()
                != Status.Code.UNAVAILABLE) {
            throw failure;
        }
    }
}
assertTrue(reachedB, "Client did not fail over to instance-b within test timeout");

// Once B is able to serve, new RPCs must continue reaching B.
for (int i = 0; i < 10; i++) {
    StockReply reply = blockingStub
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .getStock(request);
    assertEquals("instance-b", reply.getInstanceId());
}
~~~

Realistic tests need to give the client a bounded window to detect that A is no longer reachable. The example above retries a bounded check, continuing only when an attempt temporarily receives UNAVAILABLE, then verifies subsequent RPCs all reach B. You can replace the loop with a connectivity/health signal observed by the fixture. Never use a fixed sleep and assume the subchannel has already transitioned state. Every wait must have a timeout so tests do not hang.

`Server.shutdownNow()` closes the server and active calls; it simulates an instance stopping from the server side, yet is not fully equivalent to a killed process or network partition. To test connection resets, process crashes, or proxies losing routes, run dedicated tests over TCP with separate processes/containers or a network fault fixture.

## 7. Distinguishing graceful shutdown from abrupt failure

These two ways of stopping an instance produce different behavior:

| Stop type | Behavior | What to test |
| --- | --- | --- |
| Graceful shutdown | Server stops accepting new calls and can let active calls finish within drain time. | Client stops choosing the instance for new RPCs; active RPCs have a chance to complete. |
| Immediate shutdown | Server closes active calls and connections. | Active RPCs receive errors; new RPCs shift to a healthy endpoint once failure is detected. |
| Process crash | No drain phase; sockets may close abruptly. | Client detects transport error and reconnects/fails over. |
| Network partition | Process may keep running while client cannot reach it. | Deadlines/keepalive/health policies bound wait time and detect the unserviceable endpoint. |

In production, graceful drain is normally used for rollouts; abrupt failure is used to test fault tolerance. Do not use graceful shutdown to conclude the system handles process crashes properly.

## 8. Testing health checking

The gRPC Health Checking Protocol defines the standard service `grpc.health.v1.Health`. A server can report `SERVING` or `NOT_SERVING` for a service. When the client enables health checking and the load-balancing policy supports it, the client can avoid sending RPCs to endpoints not reporting `SERVING`.

Health checking should be tested separately:

1. Start two instances and verify both report `SERVING`.
2. Change A's health to `NOT_SERVING` while process A keeps running.
3. Wait for the client health watcher to receive the status and exclude A from new RPC selection.
4. Verify new requests reach B; restore A to `SERVING` and observe A returning to the eligible pool.

Health checking does not replace connectivity checks. An endpoint can report `SERVING` yet lose its network path; conversely, a process can accept connections while the application cannot serve requests. Choose health checks at a granularity that reflects true request-handling capability and configure the exact service name.

Do not assume every gRPC Java load-balancing policy enables health checking by default. Support and configuration depend on the `grpc-java` version, resolver, policy, and service config in use. Tests must confirm the feature is actually active at runtime.

## 9. Testing retries when an instance fails

Load balancer failover and RPC retries are two distinct mechanisms:

- The load balancer selects an eligible endpoint for a new RPC.
- The retry policy decides whether to create a new attempt when an attempt fails.

If the first attempt goes to A and A dies mid-flight, the client may receive `UNAVAILABLE`. Only when the method has an appropriate retry policy and the status is in `retryableStatusCodes` can gRPC retry per policy. Example service config for a read unary method:

~~~java
Map<String, ?> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "inventory.Inventory",
                "method", "GetStock")),
        "retryPolicy", Map.of(
                "maxAttempts", 3.0,
                "initialBackoff", "0.1s",
                "maxBackoff", "1s",
                "backoffMultiplier", 2.0,
                "retryableStatusCodes", List.of("UNAVAILABLE"))
);

Map<String, ?> serviceConfig = Map.of(
        "methodConfig", List.of(methodConfig),
        "loadBalancingConfig", List.of(
                Map.of("round_robin", Map.of()))
);
~~~

This is an illustrative configuration for one method; verify that the service/method names match the package and service in the proto. `maxAttempts` includes the initial attempt. Retries use backoff and are bounded by the RPC deadline. Do not turn on retries mechanically for every method.

Important limitations:

- Retries do not guarantee an in-flight attempt is transferred intact to another server.
- gRPC retries can buffer and replay requests via retry machinery, yet once an RPC commits or passes the retry commitment point, it can no longer be retried normally.
- For write RPCs, the server may have already executed side effects before the connection failed; use idempotency keys or deduplication.
- The overall deadline applies across all attempts and backoffs; never grant a fresh full timeout to each retry.

Tests should cover two parts: one case without retry configured to observe the active attempt failing, and one case with a retry policy to verify an idempotent read request can succeed via the healthy instance. Do not use a non-idempotent write RPC to prove retries succeed.

## 10. Deadlines and failure detection time

When an instance dies, the client may need time to detect the connection error, update subchannel state, and pick another endpoint. The deadline must be long enough for:

- Initial connect/resolve time if the channel is not yet `READY`.
- Time to detect the failed endpoint.
- Backoff/reconnect or retries per policy.
- Processing time on the replacement instance.

If the deadline is too short, requests may expire before failover completes. If the deadline is too long, callers wait excessively when all endpoints fail. Set deadlines according to SLOs and measure actual failover latency in a production-like environment.

Keepalive helps detect some unresponsive connections, though configuring it too aggressively creates load and can trigger proxy/server limits. Health checking evaluates service status; connection failures detect reachability; outlier detection evaluates abnormal traffic behavior. Do not treat them as one single mechanism.

## 11. Streaming RPCs when a server instance fails

A streaming RPC is pinned to the server instance that accepted the stream. When that instance dies:

- The client receives a terminal error or deadline expiration.
- The stream is not migrated mid-flight by the load balancer to another instance.
- The client must open a new stream to continue.
- The application needs a sequence number, cursor, or resume token to request unprocessed data.

With server streaming, you can track the last message processed by the client before reconnecting. With bidirectional streaming, define how to recover both send and receive state. Without a resume protocol, opening a new stream can drop or duplicate messages.

## 12. Testing network failures and process crashes

In-process transport is useful for testing observer and service logic, yet does not fully simulate TCP resets, process kills, proxies, or network partitions. A fault-tolerance integration test suite should include:

1. Two real server instances listening on ephemeral TCP ports.
2. One resolver returning both instance addresses to the same channel.
3. A single client channel using `round_robin`.
4. Confirmation that endpoint A received requests before fault injection.
5. Stopping process A or severing the route to A while B keeps serving.
6. Verifying new RPCs reach B once the client detects A failed.
7. Verifying in-flight RPCs on A produce the expected error/deadline semantics.
8. Restoring A and verifying the resolver/health policy brings A back properly.

You can use test containers or a separate server process to kill process A. If you only call `shutdownNow()` inside the same process, document clearly that the test simulates server connection closure rather than a host crash or network partition.

## 13. Observability in tests and production

Record metrics by method and instance:

- RPC count, success/error rates, and status codes per backend.
- Subchannel counts in READY, CONNECTING, and TRANSIENT_FAILURE.
- Time from instance failure until the client stops selecting that instance.
- Retry attempts, retry successes, deadline exceeded counts, and total latency.
- Interrupted streams, reconnects, and successful resumes.
- Health states and time from NOT_SERVING until endpoint exclusion.

In logs/traces, include instance ID, target, method, attempt number, and trace ID. Do not use request IDs or ephemeral instance IDs as unbounded-cardinality metric labels. On dashboards, separate business errors from transport errors so an instance is not mistakenly flagged unhealthy simply for rejecting invalid requests.

## 14. Common issues

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Client keeps sending new RPCs to a dead instance | Connection failure not yet detected or resolver still advertises endpoint. | Check subchannel state, resolver refresh, health checking, and failure detection timeouts. |
| Test has only one backend | Cannot prove failover to a healthy instance. | Use at least two endpoints on the same channel. |
| Each backend has its own channel | Test does not exercise load-balancing policy. | Use one channel with a resolver returning multiple addresses. |
| Active RPC switches automatically to another backend | Misunderstanding load balancing as call migration. | Verify in-flight failure; retry or resume creates a new attempt/stream. |
| Assertions run immediately after stopping server | Client has not detected connection failure yet. | Wait boundedly on actual state/calls rather than fixed sleeps. |
| Retries create duplicate data | Write RPC already committed before attempt failed. | Use idempotency keys, deduplication, and status lookups. |
| Health checks do not exclude instance | Health service/config/policy not enabled or unsupported. | Verify health protocol and actual runtime configuration. |
| Failover causes requests to hit deadline | Budget too small for failure detection and new attempt. | Measure failover latency, set SLO-based deadlines, and bound retries. |

## 15. Hands-on exercises

1. Start two Inventory server instances on ephemeral TCP ports; have each return its instance ID.
2. Configure a test resolver and a `round_robin` channel; verify both instances receive RPCs before fault injection.
3. Stop instance A; verify new RPCs continue reaching B once the client detects A is no longer READY.
4. Keep an RPC in flight on A and stop A; verify the active call fails rather than assuming it migrates to B.
5. Enable health checking, switch A to NOT_SERVING, and verify A stops receiving new RPCs; then restore SERVING.
6. Configure retries for an idempotent unary read; verify a new attempt can complete on B within the overall deadline.
7. Run a process crash or network partition test over TCP/TLS and measure detection/failover time.
8. Open a streaming RPC, stop the backend serving the stream, and verify reconnect/resume via sequence number or cursor.

After this lesson, you should be able to distinguish endpoint failures from business errors, understand subchannel states and failover limits for in-flight RPCs, and build tests with at least two instances sharing one channel. Testing server shutdowns, NOT_SERVING health, retries, and network failures independently confirms that a Spring gRPC client keeps serving through healthy instances while preserving deadlines and operation semantics.
