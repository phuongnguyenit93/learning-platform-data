# Retries combined with load balancing

## 1. One RPC can have multiple attempts

In **SPRING_GRPC**, the client uses `ManagedChannel` and stubs generated from Protocol Buffers contracts to call a service that may run across multiple server instances. Load balancing picks a backend for an RPC; retries create a new attempt when a previous attempt fails under allowed conditions. The two mechanisms work together to improve resilience, while each solves a distinct problem.

For example, a client calls `GetOrder`:

~~~text
Logical RPC: GetOrder(ORD-42)

Attempt 1 -> backend A
              A returns UNAVAILABLE before RPC commits
                 |
                 v
              backoff
                 |
Attempt 2 -> backend B
              B returns successful response
~~~

A **logical RPC** is the call observed by the application. Each **attempt** is a single execution over transport/server. The retry policy decides whether to create a new attempt; the load balancing policy chooses a subchannel for that attempt.

Key points to remember:

- Load balancing does not automatically retry a failed RPC.
- Retrying does not guarantee the next attempt lands on a different backend.
- A committed RPC cannot be automatically replayed by gRPC under standard retry policies.
- If a retry can repeat side effects, the application must ensure idempotency.

## 2. Load balancing is applied per attempt

A `ManagedChannel` manages the resolver, subchannels, and picker. When a new attempt needs to start, the picker selects a subchannel according to the policy and readiness state:

~~~mermaid
flowchart TD
    A["Logical RPC"] --> B["Attempt 1"]
    B --> C["Load balancer picker"]
    C --> D["Backend A"]
    D --> E{"Attempt failed?"}
    E -- "No" --> F["Return result to application"]
    E -- "Yes, retryable and uncommitted" --> G["Backoff"]
    G --> H["Attempt 2"]
    H --> I["Picker is invoked again"]
    I --> J["Selected backend"]
    J --> K{"Succeeded?"}
    K -- "Yes" --> F
    K -- "No, retries left" --> G
    K -- "No retries left / committed" --> L["Return error to application"]
~~~

With `round_robin`, new attempts can be distributed across `READY` subchannels. With `pick_first`, attempts typically keep using the currently selected subchannel if it remains ready. Thus, the same retry policy can produce different outcomes depending on the load balancing policy and backend states.

Do not rely on retries to guarantee backend switching. If backend A remains `READY` while returning `UNAVAILABLE` due to an internal dependency, the picker may keep choosing A. To remove A from selection, you need health checking, outlier detection, or appropriate discovery updates.

## 3. When is gRPC allowed to retry?

gRPC Java supports retries via service config. A retry policy specifies:

- `maxAttempts`: maximum number of attempts, including the initial attempt.
- `initialBackoff`: initial wait duration before retrying.
- `maxBackoff`: upper bound on wait duration.
- `backoffMultiplier`: factor by which backoff grows after each failure.
- `retryableStatusCodes`: status codes permitted for retry.

Retries can only proceed when the RPC is not yet **committed** and the attempt ends with a status allowed by the policy. An RPC is generally considered committed once the client receives response headers from the server or when request data exceeds the retry buffer limit. Beyond that point, the client cannot assume a new attempt is safe because the server may already have begun processing.

This is especially important for server streaming. Servers usually send response headers when starting a stream; once the client receives headers, the RPC is committed. If the stream later breaks after a few events, the retry policy will not open a new stream to replay missing events. The application must reconnect/resume using a cursor or sequence.

In addition to retry policies, gRPC may perform transparent retries when transport fails very early, before the server application handles the call. Do not rely on transparent retries to recover an RPC that the server already processed or responded to.

## 4. Choosing retryable status codes

Retries should only apply to likely transient errors and operations that can be safely re-executed. General guidance:

| Status | Considerations |
|---|---|
| `UNAVAILABLE` | Usually suitable for transient backend/transport errors; requires the RPC to be uncommitted |
| `RESOURCE_EXHAUSTED` | Retry only with clear recovery/quota rules and adequate backoff |
| `ABORTED` | Application layer may retry the entire transaction if the contract calls for it |
| `DEADLINE_EXCEEDED` | Retry only if time budget remains and operation is idempotent; server may already have completed |
| `CANCELLED` | Do not retry when the caller explicitly cancelled |
| `INVALID_ARGUMENT` | Fix the request; retrying verbatim will not help |
| `PERMISSION_DENIED` | Fix permissions or policy; do not retry repeatedly |
| `UNAUTHENTICATED` | Refresh credentials through the auth flow before deciding to call again |
| `NOT_FOUND` | Typically a business outcome, not a transient backend error |

Do not put every status into `retryableStatusCodes`. For example, a server may return `UNAVAILABLE` due to a temporary downstream failure, yet if the server already sent response headers, the RPC is committed and automatic retries no longer apply. Conversely, a transport error before the server receives the request may be handled by a transparent retry.

## 5. Configuring a retry policy in service config

Example retry configuration for the `GetOrder` method:

~~~json
{
  "methodConfig": [
    {
      "name": [
        {
          "service": "orders.v1.OrdersService",
          "method": "GetOrder"
        }
      ],
      "retryPolicy": {
        "maxAttempts": 4,
        "initialBackoff": "0.2s",
        "maxBackoff": "2s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [
          "UNAVAILABLE"
        ]
      }
    }
  ]
}
~~~

In this example, up to four attempts are made: one initial attempt and up to three retries. Backoff increases by a factor of 2 and does not exceed 2 seconds. The runtime may apply jitter to backoff durations so many clients do not retry simultaneously.

The service config can be provided by the resolver or set as the channel's default configuration. Example illustrating default configuration in gRPC Java:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;

java.util.Map<String, Object> retryPolicy = java.util.Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.2s",
        "maxBackoff", "2s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", java.util.List.of("UNAVAILABLE")
);

java.util.Map<String, Object> methodConfig = java.util.Map.of(
        "name", java.util.List.of(java.util.Map.of(
                "service", "orders.v1.OrdersService",
                "method", "GetOrder")),
        "retryPolicy", retryPolicy
);

java.util.Map<String, Object> serviceConfig = java.util.Map.of(
        "loadBalancingConfig", java.util.List.of(
                java.util.Map.of("round_robin", java.util.Map.of())),
        "methodConfig", java.util.List.of(methodConfig)
);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget("dns:///orders.internal:9090")
        .defaultServiceConfig(serviceConfig)
        .useTransportSecurity()
        .build();
~~~

This example combines `round_robin` with a retry policy for one method. Actual behavior also depends on the `round_robin` provider, gRPC Java version, and any service config delivered by the resolver. A service config returned by the resolver can take precedence over the channel's default config. Verify which policies/providers are loaded in the deployed runtime.

## 6. Backoff, deadlines, and total time limits

Retries must not run indefinitely. A logical RPC should have an overall deadline; backoff delays and all attempts consume from that budget.

~~~java
GetOrderReply reply = ordersStub
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .getOrder(request);
~~~

With a 3-second deadline, the client does not get an extra 3 seconds per attempt. For instance, if the first attempt takes 1 second, backoff takes 200 ms, and the second attempt needs 2 seconds, the logical RPC may expire before the second attempt finishes.

Exponential backoff eases pressure while backends recover:

~~~text
Attempt 1 fails
  -> wait around 0.2 seconds
Attempt 2 fails
  -> wait around 0.4 seconds
Attempt 3 fails
  -> wait around 0.8 seconds
...
  -> never exceed maxBackoff and overall deadline
~~~

Jitter staggers retry timing across clients. If thousands of clients receive `UNAVAILABLE` at once and retry at the exact same instant, the backend cluster can suffer a retry storm right as it begins recovering.

## 7. Retries and business operation idempotency

A transport error does not prove the server has not performed side effects. Example:

~~~text
Client -> CreatePayment
Server -> records payment successfully
Network -> response is lost
Client -> receives UNAVAILABLE/DEADLINE_EXCEEDED
Client -> retries CreatePayment
~~~

If the retry creates a second payment, the customer could be charged twice. For operations that create/update data, issue commands, or trigger transactions, design for idempotency:

1. Client generates a stable idempotency key for the logical operation.
2. Every attempt of the same operation reuses that key.
3. Server stores the key alongside the outcome inside a transaction or idempotency store.
4. If an already processed key arrives again, the server returns the stored result instead of executing side effects again.

Example request:

~~~proto
message CreatePaymentRequest {
  string idempotency_key = 1;
  string order_id = 2;
  int64 amount_minor = 3;
}
~~~

`idempotency_key` must remain identical across attempts. If the client generates a fresh key on each retry, the server cannot recognize it as the same operation.

For read operations like `GetOrder`, retries are usually safer. Still, if read outcomes depend on snapshots or different backends hold unsynchronized data, define consistency requirements before permitting retries across different instances.

## 8. Retries can hit the same backend again

Suppose the resolver returns A, B, and C:

| Condition | Policy | Possible outcome |
|---|---|---|
| A, B, C all `READY` | `round_robin` | New attempts can be distributed across multiple subchannels |
| A, B, C all `READY` | `pick_first` | Attempts may continue hitting A |
| Only B `READY` | `round_robin` | New attempts can only choose B |
| A stays `READY` yet returns `UNAVAILABLE` at application layer | `pick_first` | A may still be selected again |
| A disconnects | B or C is ready | Picker can choose a working backend for new attempts |

Thus, retry and failover are distinct behaviors. The retry policy decides **whether to try again**; the load balancer decides **where the new attempt goes** based on current state. To stop selecting a repeatedly failing backend, you need health checking, outlier ejection, or resolver updates—not merely increasing `maxAttempts`.

## 9. Retries for server streaming and commitment limits

Server streaming can emit multiple responses within a single RPC. Once the server sends response headers, the client receives them and the RPC is committed, so a retry policy cannot automatically restart the stream to continue from the last response.

~~~text
Attempt 1:
  Client -> WatchEvents
  Server -> headers
  Server -> Event #1
  Server -> Event #2
  Server -> UNAVAILABLE

RPC committed after headers:
  gRPC does not auto-retry to continue from #3

Application resume:
  Client -> WatchEvents(after_sequence = 2)
  New server/backend -> Event #3, #4, ...
~~~

If a stream needs recoverability, the application contract needs a stable cursor/sequence. The client checkpoints only after durably processing events; when the stream breaks, it opens a new RPC and sends the cursor. The new backend must read data from shared storage. This is application-level resume, not automatic gRPC retry.

## 10. Avoiding retry storms and load amplification

Retries multiply actual requests relative to logical RPCs initiated by the application. When backends are overloaded, uncontrolled retries make things worse:

~~~text
Backend overloaded
   -> returns errors for many RPCs
   -> clients retry simultaneously
   -> attempt count spikes
   -> backend gets even more overloaded
~~~

Control measures:

- Keep `maxAttempts` low and retry only genuinely transient status codes.
- Use exponential backoff and jitter.
- Cap total logical RPC duration with a deadline.
- Use retry throttling if supported by the runtime/service config.
- Enforce server-side quotas/admission control and concurrency limits.
- Do not stack gRPC retry policies on top of unbounded retry loops in application code.
- Do not retry validation errors, authorization errors, or non-recoverable business errors.

Some gRPC runtimes support `retryThrottling` in service config to curtail retries when failure rates climb. Availability and exact mechanics depend on the version; verify in your runtime rather than assuming the setting always applies.

## 11. Observing logical RPCs and individual attempts

Counting only method calls at the application layer can hide internal attempts generated by gRPC retries. Observe both logical calls and attempts:

- Logical RPC count per method.
- Average attempts and attempt-count distribution per logical RPC.
- Status per attempt and final status returned to the caller.
- Backend/instance receiving each attempt.
- Total logical RPC duration, per-attempt duration, and backoff time.
- Percentage of RPCs succeeding after retry.
- Number of retries blocked because the RPC was already committed or hit its deadline.
- Server-side duplicate/idempotency hit rate.

Never log sensitive payloads, access tokens, or sensitive idempotency keys. Use traces/spans to correlate attempts under one logical operation ID and attach a non-sensitive instance ID to analyze distribution.

If retries run multiple times yet all attempts hit the same backend, check the policy (`pick_first` vs `round_robin`), `READY` subchannel counts, and health status. If retries do not trigger at all, check status codes, commitment, whether the service config reached the channel, and whether the provider/runtime supports retries.

## 12. Testing retries combined with load balancing

A test that only checks whether an RPC eventually succeeds is insufficient. You need control over per-attempt statuses and visibility into which backend received each request:

| Scenario | What to verify |
|---|---|
| A returns `UNAVAILABLE` before commit, B succeeds | A new attempt occurs within policy limits; final outcome succeeds |
| A returns `INVALID_ARGUMENT` | No retry when policy permits only `UNAVAILABLE` |
| A returns `UNAVAILABLE` after response headers were sent | RPC is committed; do not expect automatic retry |
| A and B both `READY`, `round_robin` policy | New attempts can be routed via the picker to another backend |
| `pick_first` keeps A `READY` while A returns application errors | Do not assume retries switch to B |
| First attempt consumes nearly the entire deadline | Logical RPC terminates per overall deadline |
| Multiple clients fail simultaneously | Backoff/jitter and throttling limit retry storms |
| Operation with side effects is retried | Idempotency key prevents duplicate processing |
| Server stream fails after first event | No automatic resume; client starts a new RPC with cursor |
| Resolver removes failing backend | New attempts stop picking the removed endpoint after update applies |

Use multiple test servers with instance IDs, a custom resolver, or equivalent test fixtures to observe backends. In-process tests work well for retry/status logic; TCP/TLS and DNS need dedicated integration tests when behavior depends on real transports or resolvers.

## 13. Common configuration mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Assuming retries always switch to another backend | Multiple attempts may still hit the same instance | Pick an appropriate policy and check subchannel readiness |
| Retrying every status code | Repeats request, permission, or business errors | List only recoverable status codes |
| Setting `maxAttempts` too high | Amplifies load and inflates latency | Cap attempts, backoff, and deadlines |
| Omitting a deadline | Logical RPC can wait too long | Set deadlines per business budget |
| Retrying non-idempotent side-effect operations | Creates duplicate transactions or records | Use idempotency keys and deduplication |
| Assuming server streams auto-resume after failure | Loses data after the break point | Design cursor/checkpoint and application resume |
| Only exposing a health service | Unhealthy backend can still be picked | Configure client health checking/discovery |
| Stacking gRPC retries with an application retry loop | Attempt count grows beyond expectations | Choose one primary retry layer and set clear limits |

**Key takeaway:** The retry policy decides whether to make a new attempt; the load balancing policy chooses the backend for that attempt. Retries only run when the status is eligible and the logical RPC is not yet committed; the deadline covers all attempts plus backoff delays. `round_robin` can spread attempts across multiple backends, whereas `pick_first` may keep selecting the same backend. Operations with side effects require idempotency keys; committed server streams require application-level reconnect/resume with a cursor.
