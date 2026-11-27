# Per-Client Rate Limiting

## Learning Objectives

After this lesson, you can:

- Explain per-client rate limiting and distinguish it from concurrency limits, message size limits, and total quotas.
- Identify clients by authenticated identity rather than trusting caller-supplied metadata.
- Choose quota scopes by client, method, tenant, or service group.
- Compare fixed window, sliding window, token bucket, and leaky bucket.
- Implement a testable token bucket using a monotonic clock.
- Apply rate limiting in a server interceptor before invoking the business handler.
- Limit message rate separately for client-streaming and bidirectional streaming.
- Choose between local and distributed limiters when running multiple replicas.
- Return appropriate statuses, guide client backoff, and observe policy effectiveness.

## 1. What problem does per-client rate limiting solve?

In **SPRING_GRPC**, multiple clients can call the same service or method. A client sending requests too rapidly can consume workers, connection pools, database capacity, and bandwidth, degrading service quality for other clients.

**Per-client rate limiting** bounds the rate at which a client is allowed to issue requests or send messages over a time interval. The goal is to protect processing capacity and share resources fairly. When a client exceeds the threshold, the server rejects early before the request reaches business logic.

Rate limits differ from other resource limits:

| Mechanism | What does it limit? | Example |
| --- | --- | --- |
| Rate limit | Rate of requests/messages over time | 20 RPCs/second/client |
| Concurrency limit | Number of active RPCs at the same time | Max 5 streams/client |
| Message-size limit | Size of each gRPC message | Max 2 MiB/message |
| Message-count limit | Total messages in one stream | Max 1,000 messages/stream |
| Byte quota | Total data over a period or session | 100 MiB/minute/client |
| Deadline | Maximum duration of one RPC | 2 seconds/call |

Rate limits control arrival rate; concurrency limits control active work holding resources; message-size and byte quotas control volume. A system usually needs to combine these mechanisms.

For example, one client may send 100 RPCs per second where each RPC completes in 5 ms; concurrency is low yet rate is high. Another client opens 2 streams and keeps them open for 10 minutes; stream-open rate is low yet concurrency and lifetime are high. Do not use a single limiter to replace every limit.

~~~mermaid
flowchart TD
    A["gRPC call arrives at server"] --> B["Authenticate client"]
    B --> C["Read client identity from Context"]
    C --> D["Evaluate quota by client and method"]
    D --> E{"Tokens available?"}
    E -- "Yes" --> F["Allow handler invocation"]
    E -- "No" --> G["RESOURCE_EXHAUSTED"]
    F --> H["Business logic and downstream"]
~~~

## 2. Identifying clients reliably

Rate limiting is only fair if the server knows which client a request belongs to. Never use an arbitrary header like x-client-id directly as the quota key, because callers can change the value to get a fresh bucket or impersonate another client.

Identification should come from completed authentication, for example:

- Client ID inside an access token whose signature and issuer have been verified.
- Authenticated service account or workload identity.
- API key looked up and mapped to an internal client record.
- Certificate identity from mTLS, after verifying trust chain and mapping.

The authentication interceptor verifies credentials and places the principal into gRPC Context. The rate-limit interceptor reads that principal. If no authenticated identity is present, the request must be rejected by the authentication layer; do not create a bucket for a default value like anonymous or unknown and accidentally let all callers share one quota.

Example shared context key:

~~~java
import io.grpc.Context;

public final class ClientIdentityContext {

    public static final Context.Key<String> CLIENT_ID =
            Context.key("authenticated-client-id");

    private ClientIdentityContext() {
    }
}
~~~

The authentication interceptor sets the value after verifying credentials:

~~~java
Context context = Context.current().withValue(
        ClientIdentityContext.CLIENT_ID,
        authenticatedClient.internalId());

return Contexts.interceptCall(
        context, call, headers, next);
~~~

Record only a stable, authenticated internal client ID. Do not put raw bearer tokens, API keys, certificate bytes, or personal information into limiter keys, logs, or metric labels.

If one credential represents multiple tenants, the contract must specify whether quotas apply per client, per tenant, or per client-tenant pair. Do not let callers pick a tenant key before checking membership.

## 3. Choosing quota scopes

A rate limit policy must define the bucket key clearly. Common options:

- **Per client:** all methods of one client share a budget.
- **Per client + method:** a client has separate quotas for each RPC method.
- **Per tenant:** clients within a tenant share a quota.
- **Per client + method + tenant:** granular quota for a client within a tenant and method.
- **Per service class/tier:** different quotas for free, standard, or premium clients.

For example, a system might allow 100 RPCs/second/client overall, while GenerateReport allows only 2 calls/second/client because that method consumes more CPU and database resources. A lightweight GetStatus method can have a higher quota.

Avoid creating bucket keys with unbounded cardinality from untrusted input. Use only verified client/tenant identities and method names taken from the gRPC descriptor. Bound the number of buckets held in memory and configure an eviction policy.

If one client holds multiple API keys, decide whether quotas attach per key or to the client owning those keys. Per-client quotas usually prevent an organization from bypassing limits by creating multiple credentials.

## 4. Choosing a rate-limiting algorithm

Common algorithms have different semantics:

| Algorithm | How it works | Pros | Limitations |
| --- | --- | --- | --- |
| Fixed window | Counts requests in each fixed time window | Simple, minimal state | Bursts across window boundaries can nearly double the limit |
| Sliding window log | Stores timestamps of each request in a sliding window | Accurate | Memory grows with request count |
| Sliding window counter | Estimates sliding window from two buckets | Lighter than log | Approximation |
| Token bucket | Tokens refill steadily; each request consumes tokens | Allows bounded bursts and controls long-term rate | Needs per-bucket state |
| Leaky bucket | Places requests in a queue and processes at a fixed rate | Smooths processing rate | Can increase queue latency; requires a finite queue |

Token bucket is often a good fit for gRPC APIs because it allows short bursts within a defined capacity while bounding the average rate. For example, a bucket with capacity 40 tokens and refill 20 tokens/second: a client can send a burst of up to 40 requests when the bucket is full, then sustain at most roughly 20 requests/second.

Do not confuse capacity with refill rate. Capacity determines maximum burst; refill rate determines long-term sustained rate.

## 5. How does a token bucket work?

A token bucket has three components:

- **Capacity:** maximum tokens in the bucket.
- **Refill rate:** tokens added per second.
- **Cost:** tokens consumed by one operation.

When a request arrives, the limiter computes tokens refilled since the last update. If enough tokens exist, it deducts cost and allows the request. If not enough, it rejects and can optionally estimate the time until sufficient tokens are available.

Conceptual formula:

\[
T_{\text{new}} =
\min(C,\ T_{\text{old}} + \Delta t \times R)
\]

Where C is capacity, R is tokens/second, and Δt is elapsed time on a monotonic clock.

Use a monotonic clock like System.nanoTime(), not a wall clock like Instant.now(), to measure elapsed time. System clocks can jump due to NTP or administrative adjustments; monotonic clocks are much better suited for elapsed intervals.

## 6. Simple token bucket implementation in Java

The example below uses synchronized to make refill and consume atomic for one bucket. A ticker is injected so unit tests can control time without real-time waiting:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

public final class TokenBucket {

    private final double capacity;
    private final double tokensPerNano;
    private final LongSupplier ticker;

    private double tokens;
    private long lastRefillNanos;

    public TokenBucket(
            long capacity,
            double tokensPerSecond,
            LongSupplier ticker) {

        if (capacity <= 0 || tokensPerSecond <= 0) {
            throw new IllegalArgumentException(
                    "capacity and refill rate must be positive");
        }

        this.capacity = capacity;
        this.tokensPerNano =
                tokensPerSecond / TimeUnit.SECONDS.toNanos(1);
        this.ticker = ticker;
        this.tokens = capacity;
        this.lastRefillNanos = ticker.getAsLong();
    }

    public synchronized boolean tryConsume(long cost) {
        if (cost <= 0 || cost > capacity) {
            return false;
        }

        refill();

        if (tokens < cost) {
            return false;
        }

        tokens -= cost;
        return true;
    }

    private void refill() {
        long now = ticker.getAsLong();
        long elapsed = now - lastRefillNanos;

        if (elapsed > 0) {
            tokens = Math.min(
                    capacity,
                    tokens + elapsed * tokensPerNano);
            lastRefillNanos = now;
        }
    }

    public synchronized double availableTokens() {
        refill();
        return tokens;
    }
}
~~~

Initialize a bucket for 20 requests/second with max burst 40:

~~~java
TokenBucket bucket = new TokenBucket(
        40,
        20.0,
        System::nanoTime);
~~~

This is an illustrative implementation for a single bucket inside one process. synchronized keeps bucket state consistent when multiple threads consume concurrently. When there are many clients, you need a registry managing buckets by identity with eviction; do not allocate a new bucket object per RPC.

For quotas needing high accuracy or multiple replicas, use a proven limiter library or a distributed limiter with atomic operations. Do not build a custom distributed algorithm using separate read-then-write network calls.

## 7. Bucket registry by client and method

A registry can use a key combining the internal client ID and full method name:

~~~java
public record RateLimitKey(
        String clientId,
        String fullMethodName) {
}

public interface ClientRateLimiter {

    boolean tryAcquire(
            String clientId,
            String fullMethodName,
            long cost);
}
~~~

Implementation creating buckets from policy:

~~~java
public final class LocalClientRateLimiter
        implements ClientRateLimiter {

    private final ConcurrentMap<RateLimitKey, TokenBucket> buckets =
            new ConcurrentHashMap<>();

    private final RateLimitPolicy policy;

    public LocalClientRateLimiter(RateLimitPolicy policy) {
        this.policy = policy;
    }

    @Override
    public boolean tryAcquire(
            String clientId,
            String fullMethodName,
            long cost) {

        RateLimitKey key =
                new RateLimitKey(clientId, fullMethodName);

        RateLimitRule rule = policy.ruleFor(fullMethodName);
        TokenBucket bucket = buckets.computeIfAbsent(
                key,
                ignored -> new TokenBucket(
                        rule.capacity(),
                        rule.refillPerSecond(),
                        System::nanoTime));

        return bucket.tryConsume(cost);
    }
}
~~~

This is a skeleton: a production registry must include eviction, a maximum bucket count, and policy update handling. If client IDs can change or there are millions of clients, an unbounded map becomes a memory leak. You can use a cache with maximumSize and expireAfterAccess; when a bucket is evicted, the next call recreates it with a full bucket, so eviction policies must be evaluated for fairness and quota-bypass potential.

If policy changes, decide whether existing buckets keep the old rule until expiry or update immediately. Do not let deploying a new rule accidentally reset every bucket and trigger a synchronized burst if that exceeds downstream capacity.

## 8. Enforcing rate limits in a ServerInterceptor

A server interceptor is the right boundary to limit new RPCs before invoking the service handler. Authentication must run first and place the verified client identity into Context.

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class ClientRateLimitInterceptor
        implements ServerInterceptor {

    private final ClientRateLimiter rateLimiter;

    public ClientRateLimitInterceptor(
            ClientRateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String clientId = ClientIdentityContext.CLIENT_ID.get();

        if (clientId == null || clientId.isBlank()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authenticated client identity is required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String method =
                call.getMethodDescriptor().getFullMethodName();

        if (!rateLimiter.tryAcquire(clientId, method, 1)) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Client rate limit exceeded"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

When the quota is exhausted, the interceptor closes the call with RESOURCE_EXHAUSTED before the handler runs. This is a quota/capacity error, not an authentication or authorization error.

Ensure the authentication interceptor executes before the rate-limit interceptor. Exact registration order and interceptor composition can vary by grpc-java builder or Spring gRPC starter; verify with an integration test that Context already holds the principal when the limiter runs and that the handler is not invoked when rejected.

Do not use x-client-id metadata directly as clientId. Metadata is caller-supplied input; identity must be verified first. If identity is missing, fail closed instead of letting all callers share one bucket.

## 9. Per-RPC rate limiting vs. message rate limiting in streaming

ServerInterceptor interceptCall runs once per RPC. For client-streaming or bidirectional streaming, it limits the rate of opening new RPCs, not the rate of messages sent within an already open stream.

If you need to limit inbound message rates, wrap ServerCall.Listener and consume tokens inside onMessage:

~~~java
ServerCall.Listener<ReqT> delegate =
        next.startCall(call, headers);

return new ForwardingServerCallListener
        .SimpleForwardingServerCallListener<ReqT>(delegate) {

    @Override
    public void onMessage(ReqT message) {
        if (!messageRateLimiter.tryAcquire(
                clientId, method, 1)) {
            call.close(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Message rate limit exceeded"),
                    new Metadata());
            return;
        }

        super.onMessage(message);
    }
};
~~~

This is a skeleton; real implementations need a terminal guard and subscription/worker cleanup when the stream closes. Never forward messages to the delegate after closing the call. For outbound streaming, apply the limiter before emitting each response or throttle the producer using flow control.

Three independent policies can be defined:

- RPC start rate: new calls per second/client.
- Inbound message rate: request messages per second/client/method.
- Outbound message rate: response messages per second/client/method.

Do not share one token bucket across all three dimensions if the contract needs separate budgets. One client might open few streams yet send messages very fast; another client might open many empty streams. Each traffic shape needs an appropriate limiter.

## 10. Registering policies in Spring gRPC

In a Spring application, configure the policy and limiter as shared beans:

~~~java
@Configuration
public class GrpcRateLimitConfiguration {

    @Bean
    RateLimitPolicy rateLimitPolicy() {
        return RateLimitPolicy.defaults();
    }

    @Bean
    ClientRateLimiter clientRateLimiter(
            RateLimitPolicy policy) {
        return new LocalClientRateLimiter(policy);
    }

    @Bean
    ClientRateLimitInterceptor clientRateLimitInterceptor(
            ClientRateLimiter limiter) {
        return new ClientRateLimitInterceptor(limiter);
    }
}
~~~

Register the interceptor via the server builder customizer/configurer or extension point of the Spring gRPC starter in use. Do not assume every starter uses the same bean declaration or property style. Check the documentation/API of the exact project version and write an application integration test to verify the interceptor is truly in the server chain.

If there are multiple services, use policies keyed by full method name to set distinct quotas. For sensitive methods, combine per-client rate limits with concurrency limits. Never create a separate limiter bean per request; the limiter registry must live with the application context and have a clear lifecycle.

## 11. Local limiters vs. distributed limiters

A local token bucket lives in the memory of a single instance. When running multiple replicas, each instance has its own bucket. If the quota is 20 requests/second/client and there are 4 replicas, a client can reach nearly 80 requests/second if traffic distributes evenly and each replica grants full tokens.

Three models exist:

| Model | Characteristics | When appropriate |
| --- | --- | --- |
| Per-instance local limit | Each replica limits independently | Protecting individual instances; total quota scales by replica count |
| Sticky routing | Client generally returns to one replica | Reduces bucket split, yet not guaranteed across rebalance/failover |
| Distributed shared limiter | Multiple replicas atomically consume one quota | Need cluster-wide client/tenant quota |

Distributed limiters can use Redis scripts, database atomic counters, or a dedicated rate-limit service. Consume/refill operations must be atomic so two replicas do not both read the last token and allow both requests.

Decide behavior when the limiter store fails:

- **Fail closed:** reject requests when quota cannot be verified; protects downstreams but reduces availability.
- **Fail open:** allow requests when limiter is unavailable; preserves availability but risks exceeding quotas.
- **Local fallback:** apply a conservative per-instance quota when the shared store fails; lowers risk though semantics are no longer exact cluster quotas.

Choose based on downstream criticality and document it operationally. Never let a Redis outage hang all RPCs indefinitely; limiter lookups also require finite timeouts.

## 12. Client handling when rate-limited

When exceeding quota, the server returns **RESOURCE_EXHAUSTED**. Clients should slow down and retry per policy rather than resending immediately.

Principles:

- Exponential backoff with jitter.
- Respect retry delays if the server provides contract-defined metadata/status details.
- Never retry validation, authentication, or authorization errors.
- Retry only safe operations or those with idempotency keys.
- Avoid creating retry storms when many clients hit limits together.
- Preserve the operation's overall deadline; retries must not reset the budget indefinitely.

gRPC can carry rich status details like google.rpc.RetryInfo if the system uses corresponding protobuf error details. Without such a contract, clients can use bounded default backoff. Never parse free-form descriptions like "try again in 3 seconds" to drive retry logic.

If client-streaming already sent part of its data before hitting a rate limit, reconnecting from the start can create duplicate side effects. Use sequences, acknowledgements, idempotency keys, and resume cursors to continue safely.

## 13. Bucket keys, eviction, and memory protection

Each client/method pair can allocate bucket state. If client counts are large or client identities are uncontrolled, the registry can grow unboundedly.

You must:

- Create buckets only after authentication.
- Bound the maximum bucket count.
- Expire inactive buckets after a period of time.
- Use bounded-size internal IDs.
- Keep raw tokens or arbitrary metadata out of keys.
- Monitor eviction and bucket creation rates.
- Set separate quotas for large tenants if required by policy.

Eviction has quota consequences: an evicted and recreated bucket can start at full capacity. For regularly active clients, expire-after-access can work well; however, eviction under memory pressure may allow callers to bypass quotas. If quotas carry strict billing/security significance, use shared persistent/distributed state instead of an easily evicted cache.

Do not retain principal objects, credentials, or request payloads inside buckets. Store only minimal state: token count, timestamp, rule reference, and necessary metrics.

## 14. Observing and operating rate limits

Monitor by method and client tier while avoiding unbounded metric cardinality:

- Allowed and rejected requests.
- Rate-limit rejections by method/status.
- Token bucket available tokens or bucket saturation by bucket group.
- Client identity count and active bucket count.
- Bucket creation/eviction rates.
- Client retry and backoff rates.
- Distributed limiter store latency.
- Limiter store timeouts/errors and fail-open/fail-closed decisions.
- Downstream CPU, DB pool, queue depth, and latency before/after enabling policy.

Do not use raw client IDs, API keys, or arbitrary tenant IDs as metric labels when cardinality is large. Use client tier, method, and rejection reason; use pseudonymized or redacted identifiers in logs/traces when investigating.

Good rate limiting reduces downstream overload without causing excessive rejection rates for valid clients. Track request distribution by client tier and method; if a client repeatedly hits the limit, review the contract, burst capacity, and retry behavior before raising quotas.

## 15. Testing rate limits

Use a fake ticker or controllable clock to test token buckets without waiting in real time.

| Scenario | Expected result |
| --- | --- |
| Fresh bucket, request within capacity | Allowed |
| Send exact capacity consecutive requests | Allowed until tokens run out |
| Next request with zero tokens | Rejected |
| Time advances and tokens refill | Requests allowed again per refill rate |
| Two different client identities | Independent buckets |
| Same client, two different methods | Separate quotas if policy is per-method |
| Unauthenticated client | Rejected by auth layer; no bucket created |
| Request rejected by limiter | Handler does not execute |
| Streaming opens one RPC and sends many messages | RPC-start limit counts one call; message limiter counts each message |
| Multiple replicas using shared limiter | Total quota shared atomically |
| Limiter store unavailable | Fail-open/closed/fallback per policy |
| Bucket eviction | Does not create unexpected quota bypasses |

Test the interceptor using in-process gRPC or transport integration tests. Use raw generated stubs to prove callers bypassing the official client SDK are still limited by the server. Test the ordering of authentication and rate-limit interceptors so the principal is already in Context before the limiter reads it.

For distributed limiters, test concurrency with multiple clients/replicas consuming the final token simultaneously to ensure races do not exceed capacity. For streaming, test message N+1 at high rates and verify no messages are processed after terminal state.

## 16. Common implementation pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using x-client-id directly as bucket key | Callers change ID to obtain fresh quotas | Use authenticated principal |
| Limiting only system-wide totals | One client can consume other clients' quota | Add per-client buckets |
| Using fixed window without considering boundary bursts | Requests bunch up at window boundaries | Token bucket or sliding window |
| Limiting only RPC start | One streaming RPC sends unbounded messages | Add inbound/outbound message rates |
| Local limiter while expecting cluster quota | Total quota multiplies by replica count | Use distributed limiter or define per-instance quotas |
| Bucket map without eviction | Memory grows with client count | Maximum size and controlled expiry |
| Limiter running before authentication | No trustworthy identity | Put auth before rate-limit and test chain |
| Using UNAVAILABLE for every rejection | Clients retry with wrong semantics | Use RESOURCE_EXHAUSTED for quotas |
| Retrying immediately on rejection | Retry storms and heavier overload | Backoff, jitter, and deadlines |
| Ignoring shared store timeouts | RPCs hang when Redis slows down | Timeout limiter lookups and define failure policy |

## 17. Hands-on exercises and self-check questions

### Hands-on exercises

1. Create an authentication interceptor that places the verified internal client ID into gRPC Context.
2. Implement TokenBucket using System.nanoTime and an injectable ticker for unit tests.
3. Create a bucket registry keyed by client ID and full method name with a maximum size and eviction policy.
4. Write a ServerInterceptor rejecting over-quota RPCs with RESOURCE_EXHAUSTED before the handler runs.
5. For client-streaming, add an inbound message limiter inside onMessage; for server-streaming, limit responses before emitting.
6. Register the limiter via Spring gRPC configuration and verify interceptor ordering.
7. Run a local limiter across multiple replicas to observe quota multiplication; then evaluate a distributed limiter.
8. Write tests for capacity, refill, client isolation, method isolation, unauthenticated requests, streaming message rates, eviction, and store failure.

### Self-check questions

**1. What does per-client rate limiting limit?**  
The rate at which a client is allowed to create RPCs or send messages over a time interval.

**2. Why shouldn't the x-client-id header be used directly?**  
Callers can spoof or alter the value; limiters must use an authenticated principal.

**3. How do token bucket capacity and refill rate differ?**  
Capacity limits maximum burst; refill rate determines the long-term token replenishment rate.

**4. Does a ServerInterceptor rate-limit messages inside a streaming RPC?**  
Not automatically. The interceptor limits RPC starts; to limit messages, inspect each onMessage or each outbound response.

**5. Why can't a local limiter guarantee cluster-wide quotas?**  
Each replica maintains its own buckets, so total available tokens scale with replica count.

**6. Which status is appropriate when a client exceeds its rate limit?**  
RESOURCE_EXHAUSTED.

**7. Why does a bucket registry need eviction?**  
So memory does not grow unboundedly with client/method count; eviction must be evaluated because recreated buckets can grant a fresh burst.

**8. How should a client retry after RESOURCE_EXHAUSTED?**  
Use exponential backoff, jitter, respect retry delays, and preserve idempotency/resume semantics.

## Summary

Per-client rate limiting protects gRPC services from callers sending requests or messages faster than processing capacity. Identify clients from authenticated principals, choose bucket scopes by client/method/tenant, and use an algorithm with clear semantics such as token bucket. Server interceptors limit RPC starts; streaming needs separate limiters for inbound/outbound messages. Local buckets protect individual replicas, while cluster-wide quotas require a shared atomic limiter. When thresholds are exceeded, return RESOURCE_EXHAUSTED, have clients back off with jitter, and preserve deadlines/idempotency. Bound the bucket registry, observe rejections, and test races, eviction, streaming, and Spring interceptor wiring so policies hold in production.
