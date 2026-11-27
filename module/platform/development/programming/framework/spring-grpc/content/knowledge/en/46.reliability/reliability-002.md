# Failover when a server is unavailable

In a Spring gRPC system with multiple backends, **failover** is the ability to keep serving traffic when one server becomes unavailable. The client needs to know the list of endpoints, select a backend that can serve traffic, and handle failed RPCs according to a deadline and retry policy. When a server returns `UNAVAILABLE` or loses its connection, new RPCs can be routed to another backend if the resolver and load balancing policy provide alternative endpoints.

Failover involves two related but distinct layers:

- **Load balancing** selects an eligible backend for a new RPC.
- **Retry** re-attempts a failed RPC according to policy, potentially on a different backend if the load balancer picks another endpoint.

An in-flight streaming RPC cannot automatically migrate the remainder of the stream to another server. If the connection drops, the application must open a new stream and resume from a confirmed checkpoint/sequence if the business protocol supports it.

## 1. Prerequisites for failover to work

Client-side failover requires the following components:

1. **A resolver** providing multiple backend addresses, such as a DNS resolver or a custom resolver.
2. **A load balancing policy** that selects a backend, such as `pick_first` or `round_robin`.
3. **A long-lived channel** to track connection state and reuse transport.
4. **Health signals** if you want to exclude unhealthy backends before sending RPCs.
5. **A deadline and retry policy** bounding wait time and attempt count.

If the resolver returns only a single address, the client has no second backend to fail over to. If all backends are unavailable, calls may return `UNAVAILABLE`; enabling wait-for-ready only makes the call wait for a backend to recover until the deadline expires.

## 2. Resolvers and load balancing policies

A resolver turns a target into a list of addresses. Example DNS target:

~~~text
dns:///orders.internal:9090
~~~

A DNS resolver can return multiple A/AAAA records. The load balancing policy uses that list to create and manage subchannels.

| Policy | How a backend is chosen | Behavior when a backend fails |
| --- | --- | --- |
| pick_first | Tries addresses in order and picks one connectable subchannel | Can switch to the next address when the current endpoint cannot connect |
| round_robin | Distributes new calls across READY subchannels | Non-READY backends are skipped; new calls use remaining READY backends |

`pick_first` fits when you want one primary active connection with fallback addresses. `round_robin` fits when you want to distribute load across multiple backends. Both require the resolver to return an accurate endpoint list; a policy cannot discover new servers on its own if the resolver does not update addresses.

## 3. Configuring service config for a gRPC Java client

Service config can specify the load balancing policy, health checking, and retry policy per service/method. Example configuring client-side `round_robin` and retrying a unary RPC on `UNAVAILABLE`:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

Map<String, ?> serviceConfig = Map.of(
    "loadBalancingConfig",
    List.of(Map.of("round_robin", Map.of())),
    "methodConfig",
    List.of(Map.of(
        "name", List.of(Map.of(
            "service", "acme.orders.v1.OrderService",
            "method", "GetOrder")),
        "retryPolicy", Map.of(
            "maxAttempts", 3,
            "initialBackoff", "0.1s",
            "maxBackoff", "1s",
            "backoffMultiplier", 2,
            "retryableStatusCodes", List.of("UNAVAILABLE")))));

ManagedChannel channel = ManagedChannelBuilder
    .forTarget("dns:///orders.internal:9090")
    .defaultServiceConfig(serviceConfig)
    .build();

OrderServiceGrpc.OrderServiceBlockingStub stub =
    OrderServiceGrpc.newBlockingStub(channel);

GetOrderResponse response = stub
    .withDeadlineAfter(2, TimeUnit.SECONDS)
    .getOrder(request);
~~~

`maxAttempts` includes the initial attempt. In this example, the client has at most three attempts, with increasing backoff capped at one second. The two-second deadline remains the total budget for the logical RPC; retries must not extend the call past the deadline.

`defaultServiceConfig` is the channel's fallback configuration. If the resolver provides its own service config and the runtime accepts it, the resolver-provided service config may take precedence. Verify that your resolver/DNS and gRPC Java version apply the intended policy. Do not assume that writing one map in Spring automatically applies that configuration to every channel in the system.

## 4. Managing channels in Spring

`ManagedChannel` is a long-lived resource that should be created once and reused across RPCs. Example bean configuration:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersGrpcClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    ManagedChannel ordersChannel() {
        return ManagedChannelBuilder
            .forTarget("dns:///orders.internal:9090")
            .build();
    }

    @Bean
    OrderServiceGrpc.OrderServiceBlockingStub orderStub(
            ManagedChannel ordersChannel) {
        return OrderServiceGrpc.newBlockingStub(ordersChannel);
    }
}
~~~

The bean snippet above illustrates the minimal lifecycle. In production configuration, apply the service config chosen earlier and configure TLS/trust material for the environment. If the starter already provides a channel or channel factory, use that mechanism instead of creating a second channel to the same target.

Do not create and close a new channel per request. A shared channel lets the resolver refresh endpoints, tracks subchannel states, reuses HTTP/2 connections, and performs load balancing.

## 5. Health checking to exclude non-serving backends

A load balancer can rely purely on connection state or follow the gRPC Health Checking Protocol. When the server implements `grpc.health.v1.Health`, client-side load balancing can enable `healthCheckConfig`:

~~~json
{
  "healthCheckConfig": {
    "serviceName": "acme.orders.v1.OrderService"
  },
  "loadBalancingConfig": [
    {
      "round_robin": {}
    }
  ]
}
~~~

The server must register the health service and update its status:

- `SERVING`: the backend can receive RPCs for the queried service.
- `NOT_SERVING`: the backend should not be selected for that service.

When a backend transitions to `NOT_SERVING`, a health-aware load balancer can remove it from selection for the corresponding service. When the backend recovers and reports `SERVING`, it can be returned to the pool.

Health checking must be supported by the client runtime/policy and the server must advertise the exact full service name. Without health checking enabled, the client can still detect transport errors when a call is sent, but will not necessarily exclude the backend before the next request.

## 6. What happens when a backend returns UNAVAILABLE?

Suppose the resolver provides three backends A, B, and C:

1. The channel creates subchannels to the addresses published by the resolver.
2. The load balancer picks a `READY` backend according to its policy.
3. Backend A stops or the connection closes.
4. Subchannel A leaves the `READY` state; the policy stops selecting A for new calls.
5. `round_robin` continues selecting B or C as long as they are `READY`.
6. If an in-flight call on A fails with `UNAVAILABLE`, the retry policy can issue a new attempt within the remaining deadline.

Not every failure triggers a retry. Retries occur only when the status is in `retryableStatusCodes`, the policy has remaining attempts, and enough deadline remains. An `UNAVAILABLE` explicitly returned by a service handler can also be treated as retryable if configuration permits; only enable retries when business semantics are safe.

## 7. Distinguishing failover, retry, and wait-for-ready

| Mechanism | Purpose | Limitation |
| --- | --- | --- |
| Failover via load balancer | Picks another backend for new calls | Requires alternative endpoints and a supporting policy |
| Retry policy | Re-attempts a failed call | Can duplicate side effects if the operation is not idempotent |
| Wait-for-ready | Waits for the channel to have a ready backend | Can wait until deadline expiration; does not create new backends |

`withWaitForReady()` is useful during brief disruptions when the caller is willing to wait. For calls without wait-for-ready enabled, if no transport is ready the client typically receives `UNAVAILABLE` faster. Both modes still require a finite deadline so requests do not hang indefinitely.

Do not use wait-for-ready as a replacement for load balancing or health checking. It does not make an unhealthy backend healthy and does not guarantee fallback endpoints exist.

## 8. Limits of failover for in-flight RPCs

Load balancing typically selects a backend when the call starts. If a unary RPC fails before completing, a retry can send a new attempt to another backend. However, if a server-streaming, client-streaming, or bidirectional stream has started and the connection drops:

- The old stream ends; already-exchanged messages cannot be migrated automatically to another backend.
- The client must open a new stream if business rules allow.
- The application protocol should include a sequence number, cursor, offset, or checkpoint to resume from the confirmed position.
- The server must support resume/idempotency if the client can resend messages.

For streaming uploads, do not simply reconnect and resend all bytes unless the operation prevents duplicate writes. Design chunk IDs and acknowledgements so the client knows the last chunk committed by the server.

## 9. Idempotency when retrying unary RPCs

Retrying a write RPC can produce duplicate side effects if the first backend committed but the response was lost. Example `CreateOrder`:

1. The client sends the request to A.
2. A persists the order successfully.
3. A stops before the response reaches the client.
4. The client sees `UNAVAILABLE` and retries on B.
5. If B does not recognize the duplicate request, the system may create a second order.

For commands with side effects, use a stable idempotency key across all attempts. The server stores the key alongside the result and returns the previous result when receiving the same operation again. Never generate a new key per retry.

Pure read RPCs are generally easier to retry. For write RPCs, document idempotency semantics, transaction boundaries, and how callers look up results when a response is lost.

## 10. Deadlines and backoff must stay within the total budget

A retry policy uses increasing backoff to avoid every client hammering a backend the instant it recovers. For example, `initialBackoff = 0.1s`, `maxBackoff = 1s`, `backoffMultiplier = 2` creates progressively longer waits, yet an attempt only runs if sufficient total deadline remains.

Principles:

- Set a deadline for the logical RPC; do not grant a full fresh timeout on each attempt.
- Cap `maxAttempts` and total elapsed time.
- Retry only statuses identified as transient.
- Use jitter if retries are implemented at the application layer to prevent synchronized load spikes.
- Do not retry `INVALID_ARGUMENT`, `UNAUTHENTICATED`, or `PERMISSION_DENIED` as availability failures.
- Watch for retry amplification: higher attempt counts can overload surviving backends further.

If all backends are unavailable, continuous retrying does not create extra capacity. Circuit breakers, retry throttling, and backoff help the system recover in a controlled manner.

## 11. Testing failover across multiple backends

A test calling a single server directly does not prove failover. Integration tests need two or more backends implementing the service, a resolver returning all addresses, and a client channel using the actual load balancing policy.

Test matrix:

| Scenario | What to verify |
| --- | --- |
| Both A and B are READY | Calls are distributed per the policy |
| A stops, B remains READY | New calls continue succeeding via B |
| Call on A receives UNAVAILABLE | Retries occur only per retry policy and deadline |
| A reports NOT_SERVING | Health-aware LB stops selecting A |
| A recovers and reports SERVING | A is returned to the pool |
| Both A and B are unavailable | Calls return UNAVAILABLE or wait until deadline if wait-for-ready |
| Write RPC loses response after commit | Idempotency key prevents duplicate records |
| Streaming RPC loses connection | Client resumes via checkpoint or fails clearly |

For stable tests, bind dynamic ports per server and use a test resolver returning the exact addresses. After stopping A, wait for channel/subchannel or health state updates rather than relying on fixed `Thread.sleep()` calls. Verify requests actually reach B via a backend identity field in the response or test counters.

## 12. Observing failover in production

Track these metrics:

- Subchannel counts in `READY`, `CONNECTING`, and `TRANSIENT_FAILURE`.
- Number of backends published by the resolver and number eligible to serve.
- Rates of `UNAVAILABLE`, `DEADLINE_EXCEEDED`, and successful RPCs.
- Retry attempts per logical RPC.
- Retry success rate and recovery time after a backend outage.
- Request distribution by backend before and after failover.
- Interrupted streams and successful resume counts.

Logs should include the method, backend/peer if available, status code, attempt number, remaining deadline, and request/operation ID. Never log tokens or sensitive payloads. When retries rise without a matching rise in successes, inspect the resolver, health status, policy, and whether surviving backends are overloaded.

## 13. Key takeaways and self-check

**Failover when a server is unavailable** relies on a resolver providing multiple endpoints and a load balancing policy selecting `READY` backends. `round_robin` distributes new calls across healthy backends; a retry policy can re-attempt unary RPCs that fail with `UNAVAILABLE` within the overall deadline. Health checking removes `NOT_SERVING` backends before new calls are sent. In-flight streaming RPCs do not migrate automatically; application-layer checkpoint/resume is required.

Self-check:

1. Why can a client not fail over to another backend if the resolver returns only one address?
2. How do `pick_first` and `round_robin` differ in selecting a backend?
3. How does failover via a load balancer differ from a retry policy?
4. Why does retrying `CreateOrder` require an idempotency key?
5. How does wait-for-ready behave when no backend is `READY`?
6. Why do streaming RPCs need checkpoint/resume instead of expecting the channel to switch servers automatically?

Proper failover design lets Spring gRPC keep serving via healthy backends, bounds retries within latency budgets, and prevents duplicate side effects when a server stops mid-request.
