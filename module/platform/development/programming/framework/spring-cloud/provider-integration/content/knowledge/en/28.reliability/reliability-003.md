# Exponential Backoff, Jitter, and Rate-Limit Handling

When multiple Spring Boot instances call Azure Blob Storage, Service Bus, or a partner API together, a brief burst of errors can cause every instance to retry almost simultaneously. Request volume spikes right when the service is already overloaded, creating a **retry storm** and prolonging the incident. Conversely, if clients retry too rarely or ignore rate limits, the application may miss recovery opportunities or continuously receive HTTP 429s.

**Exponential backoff** progressively increases wait times between attempts; **jitter** spreads retry timing across clients; **rate limiting** controls the rate of requests allowed through. Together, these three mechanisms work with retry policies, deadlines, circuit breakers, and concurrency limits to protect both the application and dependent services.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secrets, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain why immediate retries and synchronized retries amplify load during service failures.
2. Compute exponential backoff and distinguish full jitter, equal jitter, and decorrelated jitter.
3. Read and handle **Retry-After** in both delay-seconds and HTTP-date formats.
4. Distinguish rate limits, quotas, concurrency limits, and connection pools.
5. Choose fixed window, sliding window, token bucket, or leaky bucket algorithms based on business needs.
6. Configure retry/rate limits in the Azure SDK, Resilience4j, and the API/application layer without unintentionally multiplying policies.
7. Handle distributed rate limiting across multiple Spring Boot replicas.
8. Test backoff, jitter, 429s, retry budgets, bursts, and fairness using a fake clock or test server.
9. Monitor throttling, retry amplification, quota consumption, and latency in a multi-cloud environment.

## 2. Why Backoff and Jitter Are Needed

Suppose a dependent service starts returning 503 for 10 seconds. A system has 100 Spring Boot instances, each handling 50 requests. If all requests retry immediately after 100 ms, the service will be hit by a new wave of load nearly at the exact same instant, before it has time to recover.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Client C
    participant S as Managed service
    par Concurrent retries
        A->>S: Retry at 1.0 s
        B->>S: Retry at 1.0 s
        C->>S: Retry at 1.0 s
    end
    S-->>A: 429 / 503
    S-->>B: 429 / 503
    S-->>C: 429 / 503
    Note over A,C: Clients again wait together and retry
~~~

**Backoff** increases the spacing between attempts, reducing request velocity when an incident persists. Yet if every client uses the exact same fixed schedule, they can still retry in lockstep. **Jitter** adds randomness to the wait duration to spread out requests.

~~~mermaid
flowchart TD
    A[Transient error / throttling] --> B[Classify error]
    B --> C[Read Retry-After if present]
    C --> D[Compute backoff and jitter]
    D --> E[Check deadline / retry budget]
    E -->|Budget remains| F[Wait without holding a thread if possible]
    E -->|Budget exhausted| G[Return error / schedule for later]
    F --> H[Bounded retry]
~~~

Backoff/jitter do not heal a broken service and do not fix configuration, permission, or invalid request errors. They only regulate **when and how often to retry** when retrying makes sense.

## 3. Exponential Backoff

Exponential backoff increases the wait duration exponentially. A basic form:

\[
d_k = \min(d_{max}, d_0 \times m^{k-1})
\]

Where:

- (d_k): wait duration before attempt (k).
- (d_0): initial wait duration.
- (m): growth multiplier, typically greater than 1.
- (d_{max}): maximum wait cap.

Example with (d_0 = 100) ms, (m = 2), (d_{max} = 2,000) ms:

| Wait | Base Wait Duration |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1,600 ms |
| 6 onward | 2,000 ms |

Without jitter, clients sharing the same configuration can still produce synchronized request bursts at 100, 200, 400 ms... Backoff alone lowers frequency, but does not spread out timing.

### Capped Exponential Backoff

Wait durations should not grow unbounded. Capping at (d_{max}) keeps timing predictable and aligned with the retry budget. Even so, total retry time can still become large:

\[
T = \sum_{i=1}^{n} t_i + \sum_{i=1}^{n-1} d_i
\]

Where (t_i) is the duration of attempt (i) and (d_i) is the wait before the next attempt. Ensure total time does not exceed the **deadline** and still leaves time for response/cleanup.

## 4. Common Jitter Strategies

Jitter introduces variance into the wait interval. Several algorithms exist; pick one based on load requirements and latency control needs.

| Algorithm | General Formula | Characteristics |
| --- | --- | --- |
| **No jitter** | (d_k) | Predictable, but clients easily synchronize |
| **Full jitter** | (U(0, d_k)) | Random value from 0 to backoff cap; strong dispersion |
| **Equal jitter** | (d_k/2 + U(0, d_k/2)) | Guarantees a minimum wait of half the backoff |
| **Decorrelated jitter** | (U(d_0, \min(d_{max}, previous \times 3))) | Next wait depends on previous wait; wide variance |

(U(a,b)) is a uniform random variable between (a) and (b). These formulas describe common variants; a given library may implement slightly different details.

### Full Jitter

With an 800 ms backoff cap, full jitter chooses a random wait in [0, 800] ms. Some clients retry early, others later; load is dispersed better than everyone waiting 800 ms.

### Equal Jitter

With an 800 ms cap, equal jitter always waits at least 400 ms and at most 800 ms. Appropriate when you want to reduce synchronization without letting clients accidentally retry too soon.

### Decorrelated Jitter

The next wait depends on the previous wait, for example from (d_0) up to three times the previous interval, capped at (d_{max}). This produces a different distribution from full jitter and requires keeping state between retries.

### Which Algorithm to Choose?

- **Full jitter** is easy to reason about and usually effective for spreading retries across many clients.
- **Equal jitter** preserves a minimum wait floor.
- **Decorrelated jitter** is useful when you want to reduce correlation across consecutive waits.
- If the service returns **Retry-After**, respect that guidance per the service contract; do not apply jitter that makes the client retry earlier than requested.

## 5. Implementing Backoff and Jitter in Java

The example below computes full jitter for a retry. It does not send requests on its own and does not replace an SDK's retry policy.

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class BackoffPolicy {

    private final long initialMillis;
    private final long maxMillis;
    private final double multiplier;

    public BackoffPolicy(
            Duration initial,
            Duration max,
            double multiplier) {

        if (initial == null || max == null ||
                initial.isNegative() || initial.isZero() ||
                max.compareTo(initial) < 0 ||
                multiplier < 1.0) {
            throw new IllegalArgumentException("Invalid backoff settings");
        }

        this.initialMillis = initial.toMillis();
        this.maxMillis = max.toMillis();
        this.multiplier = multiplier;
    }

    public Duration fullJitter(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                    "retryNumber must start at 1");
        }

        double cap = initialMillis;
        for (int i = 1; i < retryNumber && cap < maxMillis; i++) {
            cap = Math.min(maxMillis, cap * multiplier);
        }

        long upperBound = Math.max(1L, (long) Math.ceil(cap));
        long delay = ThreadLocalRandom.current()
                .nextLong(upperBound + 1L);

        return Duration.ofMillis(delay);
    }
}
~~~

Example:

~~~java
BackoffPolicy policy = new BackoffPolicy(
        Duration.ofMillis(100),
        Duration.ofSeconds(2),
        2.0);

Duration waitBeforeRetry3 = policy.fullJitter(3);
~~~

This is illustrative code. For production, check for overflow/very large Duration limits, use an injectable random source for tests, and integrate with deadlines/retry budgets. Never call Thread.sleep() directly on a WebFlux event loop or reactive request thread.

### Waiting for Retries in Applications

- In synchronous/blocking code, Thread.sleep() can be used on a bounded worker thread, but the wait time must count toward the deadline and avoid holding threads unnecessarily.
- In Reactor, use Mono.delay or a retry operator with proper backoff; do not block the event loop.
- In background workflows, persist nextRetryAt and enqueue work to a scheduler/queue instead of holding a request open for long durations.
- With SDKs, prefer built-in retry policies when the SDK understands service semantics.

## 6. Retry-After: How Long Does the Service Ask You to Wait?

Some services use HTTP 429 or 503 with a **Retry-After** header. Per HTTP semantics, the header can contain:

1. **Delay seconds**: number of seconds the client should wait.
2. **HTTP-date**: an HTTP-date timestamp after which the client may retry.

Examples:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
~~~

Or:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: Wed, 25 Nov 2026 10:00:00 GMT
~~~

Clients should parse the header per the service/SDK contract. If the SDK already honors Retry-After internally, do not wrap it in another retry layer with a shorter delay that undermines the guidance.

### Combining Retry-After and Jitter

Suppose the service asks clients to wait at least 2 seconds. A safe approach is:

\[
d_{effective} = d_{server} + U(0, j_{max})
\]

This keeps the retry time **no earlier than** the server's instruction while adding jitter to reduce synchronization. However, some services/clients treat Retry-After as an exact delay or impose their own bounds; follow the service documentation. Never shorten the server's delay if doing so causes the request to arrive early.

If Retry-After exceeds the remaining deadline, do not keep a synchronous request waiting. Return a controlled error or enqueue the work with an appropriate retry timestamp.

### Handling HTTP-Date and Clock Skew

HTTP-date uses UTC wall-clock time. If the client clock is skewed relative to the server, computing the wait from Instant.now() can be inaccurate. When the response includes a **Date** header, you can use the difference between Date and Retry-After per contract, while capping the maximum wait according to internal policy.

Do not use monotonic System.nanoTime() values to parse an HTTP-date. Convert Retry-After into a duration and then use a monotonic deadline to control the wait.

## 7. What Is Rate Limiting?

**Rate limiting** restricts the number of requests or operations allowed within a period of time. It protects:

- Managed service quotas.
- Requests-per-second or transactions-per-second limits.
- Partner APIs with per-tenant/key limits.
- Connection pools, databases, and worker capacity.
- Costs and fair service across customers.

For instance, a partner API allows only 100 requests/second per API key. If 10 Spring Boot replicas each emit 20 requests/second, the total is 200 requests/second and calls can be throttled with 429 even though no individual replica exceeds 100 requests/second.

### Rate Limit vs. Quota and Concurrency Limit

| Mechanism | Controls | Example |
| --- | --- | --- |
| **Rate limit** | Request rate over time | 100 requests/second |
| **Quota** | Total usage within a billing/time period | 1 million requests/day |
| **Concurrency limit** | Number of simultaneous operations | Maximum 20 in-flight uploads |
| **Connection pool** | Number of connections held/leased | 30 JDBC connections |
| **Queue capacity** | Number of queued tasks | Maximum 5,000 pending jobs |

A system can satisfy its rate limit yet still overload if each request takes several seconds and concurrency climbs too high. Conversely, a low concurrency limit does not guarantee a rate limit if requests complete ultra-fast.

## 8. Rate-Limiting Algorithms

### 8.1. Fixed Window Counter

Counts requests within a fixed time window, such as 100 requests per second.

Pros:
- Simple and easy to implement.
- Low storage overhead.
- Easy to explain to operators.

Cons:
- **Boundary burst**: a client can send 100 requests at the end of one window and 100 requests right at the start of the next window, producing 200 requests in a very short span.

~~~text
Window A: |--------------------|
Requests:                 100
Window B:                  |--------------------|
Requests:                  100
                           ↑ boundary burst
~~~

### 8.2. Sliding Window Log

Stores the timestamp of each request and counts requests within a sliding time range.

Pros: more accurate enforcement over the time window.

Cons: stores many timestamps; high memory and processing cost at high throughput.

### 8.3. Sliding Window Counter

Combines the counters of the current and previous windows, estimating request count in the sliding interval based on elapsed time ratio.

Pros: uses less memory than a log and reduces boundary bursts compared to fixed window.

Cons: it is an approximation; not strictly exact for every request distribution.

### 8.4. Token Bucket

A bucket holds at most (B) tokens. Tokens are replenished at rate (r) tokens/second. Each request consumes one or more tokens.

- When the bucket has tokens, the request is allowed through.
- When the bucket is empty, the request is rejected or waits.
- The bucket allows bursts up to roughly capacity (B), while long-term average rate is bounded by (r).

Example: refill rate 20 tokens/second, capacity 40 tokens. A burst of 40 requests can be accepted when the bucket is full; afterward, the long-term average rate cannot exceed the refill rate without extra tokens.

~~~mermaid
flowchart LR
    A[Incoming request] --> B{Bucket has tokens?}
    B -->|Yes| C[Deduct tokens]
    C --> D[Allow request]
    B -->|No| E[Reject / wait / queue]
    F[Refill over time] --> G[Bucket, max B tokens]
    G --> B
~~~

### 8.5. Leaky Bucket

Requests enter a queue and are drained/processed at a fixed or bounded rate. If the queue is full, new requests are rejected.

Pros:
- Smooths out bursts.
- Steady outbound processing rate.

Cons:
- Can increase latency due to queue wait.
- Capacity must be bounded to avoid unbounded backlogs.

### Algorithm Comparison

| Algorithm | Allows Bursts | Accuracy | Complexity | Best Fit |
| --- | --- | --- | --- | --- |
| Fixed window | Yes, at boundaries | Medium | Low | Simple quotas |
| Sliding log | Yes, up to window limit | High | High | Limits requiring strict precision |
| Sliding counter | Yes, with reduced boundary effect | Approximate | Medium | High-throughput APIs |
| Token bucket | Yes, up to bucket capacity | Good for average rate and bursts | Medium | APIs / service clients |
| Leaky bucket | Smooths bursts at output | Steady output rate | Medium | Workers and pipelines needing uniform load |

## 9. Where Does Rate Limiting Sit in the Architecture?

Rate limiting can be applied at multiple layers:

| Layer | Goal | Example |
| --- | --- | --- |
| **API gateway/ingress** | Protect endpoints from external clients | Limit requests per API key/tenant/IP |
| **Spring application** | Protect business logic or a dependency | Limit calls to Blob / partner API |
| **SDK/service client** | Respect service throttling/quotas | SDK handles 429/Retry-After |
| **Message consumer** | Bound message processing rate | Max 50 messages/s or 10 concurrent handlers |
| **Database access** | Protect DB from overload | Bulkhead, pool, and concurrency cap |
| **Distributed platform** | Share quota across replicas | Redis-backed token bucket |

Do not place identical rate limiters at every layer without reason. For example, an API gateway limits users to 100 requests/s, yet each request spawns 3 downstream calls; the dependency can still receive 300 operations/s. Account for the **fan-out factor** and per-service quotas.

### Which Key Should Rate Limits Partition By?

A limiter can be keyed by:

- Entire application or entire dependency.
- Tenant/customer ID.
- API key or authenticated principal.
- Resource/service namespace.
- Operation type, e.g., Blob upload vs. Blob list.
- Users or customer groups with different tiers.

Do not rely solely on IP address as the key behind NAT/proxies where many users share an IP. Do not trust client-supplied user/tenant headers; obtain identity/tenant from the authenticated context.

## 10. Rate Limiting in Spring Boot

You can use libraries such as **Resilience4j RateLimiter**, **Bucket4j**, Spring Cloud Gateway, or a centralized limiter. Choose based on placement and the scope you need to control.

### 10.1. Resilience4j RateLimiter

Example configuration of a local limiter for a dependency:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      blobWrites:
        limit-for-period: 20
        limit-refresh-period: 1s
        timeout-duration: 0
~~~

A service can apply the annotation:

~~~java
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import org.springframework.stereotype.Service;

@Service
public class BlobWriteService {

    private final BlobGateway gateway;

    public BlobWriteService(BlobGateway gateway) {
        this.gateway = gateway;
    }

    @RateLimiter(name = "blobWrites")
    public BlobReference upload(Document document) {
        return gateway.upload(document);
    }
}
~~~

This configuration illustrates a limiter within **one JVM instance**. With 10 replicas, each replica can allow 20 operations/second, totaling around 200 operations/second. It does not automatically create a cluster-wide quota.

**timeout-duration: 0** indicates not waiting for a permit in this illustrative config; verify the API/properties for your Resilience4j version. When no permit is available, the application must handle the rate-limit failure explicitly instead of retrying immediately.

### 10.2. Local Rate Limiter vs. Distributed Rate Limiter

An in-memory process limiter is scoped to a single JVM. When an application runs multiple replicas:

~~~text
Replica A: 20 req/s
Replica B: 20 req/s
Replica C: 20 req/s
Replica D: 20 req/s
---------------------
Possible total: 80 req/s
~~~

If the partner's quota is 50 req/s system-wide, a local 20 req/s limiter per replica is insufficient. You may need:

- A distributed rate limiter backed by Redis or a shared state service.
- An API gateway managing quotas centrally.
- A single dispatcher/worker throttling outbound traffic.
- Fixed quota allocations per replica adjusted as you scale.

A distributed limiter must perform token/counter updates **atomically**. Non-atomic read-modify-write operations can allow multiple replicas to consume the same token or exceed the quota. Account for Redis scripts/transactions, clock consistency, network failures, and behavior when the limiter store is unavailable.

### 10.3. Token Bucket via Library

Libraries such as **Bucket4j** provide token buckets and integrate with distributed backends depending on edition/version. Conceptual example:

~~~java
// Pseudocode: exact API depends on Bucket4j version/backend.
Bucket bucket = createTokenBucket(
        capacity = 40,
        refillTokens = 20,
        refillPeriod = Duration.ofSeconds(1));

if (bucket.tryConsume(1)) {
    callDependency();
} else {
    throw new RateLimitExceededException();
}
~~~

Do not treat the pseudocode above as directly compilable Java. When selecting a library, check its version, refill behavior, clock source, distributed backend, atomicity, and licensing/edition for cluster features.

## 11. Handling 429 and Throttling from Managed Services

HTTP 429 **Too Many Requests** typically indicates the client exceeded a rate limit or quota. Some services return a Retry-After header or proprietary metadata. However, not all Azure services signal throttling identically.

### Azure

- **Azure Blob Storage:** may return 429 or 503 for throttling/capacity depending on the situation; the Storage SDK has retry options and can act on server responses per policy.
- **Azure Cosmos DB:** throttling commonly surfaces as **429 RequestRateTooLarge**; responses may provide a wait interval such as retry-after for clients to adjust. The Cosmos SDK has its own retry mechanism.
- **Azure Service Bus:** quota/throttling and transient service errors can appear by operation/namespace; the client has its own retry behavior and messaging semantics.
- **Azure Event Hubs:** throughput unit/processing limits can trigger throttling; consumers/producers must tune partitions, batching, concurrency, and retries.

Do not lump all 429/503 responses into one generic handler if the SDK already implements service-specific behavior. Read the detailed error codes and service documentation.

### AWS and Google Cloud

- AWS SDK for Java v2 has retry strategies and retry modes suited to specific throttling/service errors. Service quotas and retry behavior still need individual verification.
- Google Cloud Java clients have per-RPC/API retry settings and error codes; quotas may surface as RESOURCE_EXHAUSTED or service-specific errors.
- For Pub/Sub, SQS, Event Hubs, and Service Bus, delivery/ack/lock are not outbound request rate limits. Tune consumer concurrency and flow control separately.

### Never Retry 429 Immediately

When 429 appears, immediate retries usually worsen the problem. Instead:

1. Read Retry-After or service-specific retry delays.
2. Reduce concurrency/rate if quotas are persistently exceeded.
3. Apply backoff and jitter per contract.
4. Check the deadline and retry budget.
5. Monitor quotas, request rate, and success rate.
6. Increase quotas or capacity only through service governance processes, not by increasing retries.

## 12. Combining Rate Limits, Concurrency, and Backpressure

Rate limits control **rate**; concurrency limits control **the number of active tasks**. For dependencies with variable latency, both are needed.

Conceptual Little's Law example:

\[
L = \lambda \times W
\]

Where:

- (L): average number of active operations (concurrency).
- (\lambda): average throughput (operations/second).
- (W): average processing time (seconds).

If throughput is 50 operations/s and average latency is 0.4 seconds, average concurrency is about 20. If latency rises to 2 seconds while maintaining 50 operations/s, average concurrency can climb to roughly 100. An appropriate pool/concurrency cap bounds pressure on the system.

### Backpressure

Backpressure is the mechanism by which a consumer/downstream signals upstream to slow down data emission. In Reactor, backpressure is expressed via demand; in messaging, you can tune message prefetch counts/concurrent handlers; in worker queues, you can limit how many tasks are pulled simultaneously.

**Do not replace backpressure with retries.** If the system keeps accepting work faster than it can process it, retries only enlarge the backlog and load.

### Coordinated Measures

- A rate limiter caps how many requests may start.
- A bulkhead caps how many operations execute concurrently.
- A connection pool caps physical connections.
- Queue capacity caps the backlog.
- Backpressure throttles upstream producers.
- A circuit breaker stops calling a failing dependency.
- Retries with backoff/jitter recover transient errors within budget.

## 13. Retries, Rate Limits, and Deadlines Must Share One Policy

A request with a 2-second deadline that receives a 3-second Retry-After cannot wait within that same request and retry. Similarly, a rate limiter may wait for a permit, and that wait time also consumes the deadline.

Rules:

1. Compute the deadline before waiting for a permit or starting a downstream call.
2. If the rate limiter cannot grant a permit immediately, wait only if budget remains and policy permits.
3. If Retry-After exceeds the deadline, return an error or schedule a business retry.
4. Backoff/jitter must stay within the retry budget.
5. Start a new attempt only if enough time remains for the attempt and the response reserve.
6. Under prolonged overload, a circuit breaker or queue may be better than synchronous retries.

~~~mermaid
flowchart TD
    A[Operation deadline starts] --> B[Rate limiter / acquire permit]
    B -->|Permit granted| C[Call dependency]
    B -->|No permit| D{Time left to wait?}
    D -->|No| X[Reject / enqueue]
    D -->|Yes| E[Bounded wait]
    E --> B
    C --> F{Succeeded?}
    F -->|Yes| G[Return result]
    F -->|No| H{Transient and retryable?}
    H -->|No| X
    H -->|Yes| I[Retry-After / backoff + jitter]
    I --> J{Retry budget left?}
    J -->|No| X
    J -->|Yes| B
~~~

The rate limiter should be placed so permits are consumed **per outbound attempt** if the service's quota counts individual requests. If the limiter only wraps a method that uses internal SDK retries, it may count only one application call while the SDK sends multiple requests. When quotas apply per actual HTTP request, understand internal SDK retries and how quotas are metered.

## 14. Spring Boot Example: Limiting Outbound Calls

Suppose the Documents API uploads Blobs and calls an external metadata API. The application team wants to limit Blob operations to 20/second **per JVM** and allow at most 10 concurrent uploads.

You can combine:

- Resilience4j RateLimiter for rate.
- Bulkhead or executor limits for concurrency.
- Azure Storage SDK retries for transient service/transport errors.
- A business deadline to bound total duration.

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      blobWrites:
        limit-for-period: 20
        limit-refresh-period: 1s
        timeout-duration: 0
  bulkhead:
    instances:
      blobWrites:
        max-concurrent-calls: 10
        max-wait-duration: 0
~~~

Example service:

~~~java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import org.springframework.stereotype.Service;

@Service
public class DocumentsUploadService {

    private final BlobGateway blobGateway;

    public DocumentsUploadService(BlobGateway blobGateway) {
        this.blobGateway = blobGateway;
    }

    @RateLimiter(name = "blobWrites")
    @Bulkhead(name = "blobWrites")
    public BlobReference upload(Document document) {
        return blobGateway.upload(document);
    }
}
~~~

This example uses Resilience4j's annotation integration. Add the required dependencies and verify AOP/proxies and your Spring Boot version. Decorator ordering can affect whether a rate-limit permit is held while waiting on the bulkhead or vice versa; verify configuration and runtime metrics.

**Scope limitation:** with 5 replicas, this configuration can allow roughly 100 operations/s total and up to around 50 concurrent calls if each instance runs independently. If the whole storage account's quota is only 40 operations/s, you need a distributed limiter or per-replica quota allocation.

### Do Not Use Retry to Handle Local Rate Limits

If Resilience4j RateLimiter rejects an operation because no permits remain, wrapping it with Retry can create a tight loop requesting permits and burning CPU. Choose one of these policies instead:

- Reject immediately with an internal rate-limit error.
- Wait for a permit up to a bounded wait within the deadline.
- Enqueue the operation for a worker to pace.
- Return an appropriate HTTP 429/503 to the caller if the API cannot accept more load.

## 15. Distributed Rate Limiting Across Multiple Replicas

When quotas are **system-wide**, a local limiter is not enough. Suppose 8 replicas call a partner API with a 100 request/s quota. If each replica allows 20 requests/s, the total can hit 160 requests/s.

### Common Approaches

| Approach | Pros | Cons |
| --- | --- | --- |
| **Central API gateway** | Single point of quota enforcement across services | Must route all requests through the gateway and understand how it meters quotas |
| **Redis-backed limiter** | Shares state across replicas, supports atomic scripts | Redis is a new dependency; must handle latency/failures/clocks |
| **Dedicated dispatcher/worker** | Centralized outbound pacing and queuing | Adds latency and another operational component |
| **Quota allocation per replica** | Simple, no shared state needed | Must adjust when scaling and can waste unused quota |
| **Service-provided quota** | Relies on actual service limits | Does not replace outbound burst control on the application side |

### Scale-Out Changes the Total Quota

If each replica is statically allocated (r) requests/s and there are (N) replicas, total allowed rate can reach:

\[
R_{total} = N \times r
\]

When autoscaling increases (N), total outbound rate rises too. If the service quota is fixed, you need to:

- Allocate quota based on current total replicas.
- Use a distributed limiter.
- Cap autoscaling according to downstream capacity.
- Or use a worker/dispatcher with a global concurrency/rate cap.

### Failure Modes of a Distributed Limiter

If Redis becomes unavailable, the application must decide between **fail-open** or **fail-closed**:

- **Fail-open:** allow requests through to avoid service disruption; risks exceeding the service quota.
- **Fail-closed:** reject requests when permits cannot be verified; protects the quota but lowers availability.
- **Degraded local mode:** fall back to a local limiter with a conservative quota; not exact globally, but limits risk.

The choice depends on the consequences of exceeding quotas and availability requirements. Monitor limiter health and never silently fail-open if strict cost or quota enforcement is required.

## 16. Rate Limiting for External APIs and Multi-Tenancy

A multi-tenant API may need fair limits:

- Separate quota per tenant.
- System-wide quota for a dependency.
- Quota by operation type, such as read vs. write.
- Tier-based burst allowances.
- Reserved capacity for critical operations.
- Fair scheduling so large tenants cannot starve others of permits.

Do not use a single global bucket alone if fairness across customers is required. Conversely, per-tenant buckets alone may fail to protect a dependency's shared quota. A **two-tier** design may be needed: global limit plus per-tenant limit.

### Example

An API has a partner quota of 100 requests/s. The organization has 10 tenants, each capped at 15 requests/s:

- Global token bucket: 100 requests/s.
- Per-tenant bucket: 15 requests/s per tenant.
- Burst capacity: configured per service contract.
- Concurrency cap: maximum 30 in-flight requests.
- Retry budget: allocate only a fraction of quota to retries so retries do not starve new traffic.

Retries also consume quota. If you rate-limit only initial requests without counting retries, retry traffic can push total volume past the limit.

## 17. Observing Backoff, Jitter, and Rate Limits

Key metrics:

| Metric | Meaning |
| --- | --- |
| retry_attempts_total | Attempts by dependency/operation |
| retry_delay_seconds | Distribution of actual backoff durations |
| retry_after_seconds | Server-requested wait durations |
| rate_limit_allowed_total | Operations granted a permit |
| rate_limit_rejected_total | Operations rejected |
| rate_limit_wait_seconds | Time spent waiting for permits |
| rate_limit_tokens | Remaining tokens if exposed by the algorithm |
| dependency_429_total | Throttling responses |
| dependency_503_total | Service unavailable errors |
| in_flight_requests | Currently executing operations |
| queue_depth | Queued operations waiting |
| deadline_exceeded_total | Operations that ran out of budget while waiting/retrying |

Group metrics by dependency, operation, tenant tier, or instance pool. Avoid placing user IDs, request IDs, blob names, or message IDs in high-cardinality metric labels. Detailed identifiers can be recorded in logs/traces with appropriate masking.

### Signals That the System Needs Tuning

- 429 rate rises alongside rising retry attempts.
- Rate limiter rejects many requests while queue depth keeps growing.
- One tenant consumes most permits.
- Autoscaling adds replicas and pushes total outbound requests over quota.
- Backoff durations grow while deadline exhaustion also climbs.
- Retry traffic makes up a larger share than fresh requests.
- Concurrency is high while throughput fails to scale proportionally.

Do not simply raise quotas or retry counts. Identify whether the bottleneck is quota, concurrency, latency, connection pools, downstream capacity, or traffic distribution.

## 18. Testing Backoff, Jitter, and Rate Limiting

### 18.1. Unit Tests for Algorithms

Use an injectable random source and fake clock to verify:

- Backoff grows by the right multiplier and stops at the max cap.
- Full jitter stays within [0, cap].
- Equal jitter is never less than half the cap.
- Decorrelated jitter respects bounds and depends on the previous delay.
- Retry-After is not shortened in violation of the contract.
- No new attempts start after the deadline expires.
- Counters/tokens never grant more than the defined window limit.

Do not use real Thread.sleep() in unit tests to verify formulas. Test math deterministically; test wait behavior with a fake scheduler/clock.

### 18.2. Testing the Rate Limiter

With a token bucket of capacity 10 and refill rate 5 tokens/second:

1. Bucket starts full; 10 requests can acquire permits.
2. The next request is rejected or waits per policy.
3. After roughly 1 second, tokens refill according to refill semantics.
4. Concurrent threads requesting permits cannot consume beyond capacity.
5. Test restarts/replicas if the limiter is distributed.
6. Test behavior when the limiter backend is unavailable per fail-open/fail-closed policy.

### 18.3. Integration Tests with Managed Services

- Run test workloads against test Azure Storage/Service Bus/Cosmos resources or APIs with controlled quotas.
- Generate bounded bursts to observe 429/throttling.
- Inspect Retry-After or service-specific retry signals.
- Count outbound attempts at both the SDK and application layers.
- Verify the rate limiter applies to every actual request, including SDK retries if quotas count per request.
- Never intentionally trigger throttling on production accounts or shared services.

### 18.4. Testing a Distributed Limiter

Run multiple replicas/test workers sharing a limiter backend:

- Total requests granted permits do not exceed the global quota per the algorithm.
- Concurrent updates do not double-spend tokens.
- Scaling replicas up/down does not unexpectedly raise total quota usage.
- Redis/network failures follow the fail-open/fail-closed policy.
- Clock differences across instances do not severely skew refills.
- Per-tenant fairness holds under mixed load.

## 19. Comparing Azure, AWS, and Google Cloud

| Topic | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| SDK retry | Azure SDK service retry options | AWS SDK retry strategies/modes | API/RPC client retry settings |
| Throttling | 429/503 and service-specific error metadata | Per-API throttling/service errors | RESOURCE_EXHAUSTED or quota/service errors |
| Server retry signal | Retry-After or service-specific metadata | Retry headers/service guidance per API | RPC retry settings/status/service guidance |
| Application-side rate limit | Resilience4j, Bucket4j, gateway, or Redis | Same Spring/Redis/gateway libraries | Same Spring/Redis/gateway libraries |
| Storage | Blob throughput/partition behavior | S3 request patterns and service limits | Cloud Storage request/quota behavior |
| Messaging | Service Bus lock/receiver flow control, Event Hubs throughput | SQS visibility/polling, Kinesis shard limits | Pub/Sub flow control/ack deadline |
| Quotas | By subscription/resource/service/region depending on service | By account/region/service/API | By project/region/API/service |

Providers differ in quotas, error codes, retry behaviors, and flow control. Do not copy a 100 requests/s threshold verbatim from Azure to S3 or Pub/Sub without checking quotas and service contracts. Likewise, **Spring Cloud Azure/AWS/GCP** do not provide a single unified rate limit across all managed services.

## 20. Lab Exercise: Protecting the Documents API from a Retry Storm

**Context:** The Documents API runs 6 Spring Boot replicas, calling Azure Blob and a partner metadata API. The partner allows 120 requests/s system-wide and returns 429 with Retry-After when exceeded. Each business request has a 2-second deadline.

### Part A — Design Retries

1. Choose an exponential backoff cap and full jitter for transient errors.
2. Parse Retry-After and never retry before the server-permitted timestamp.
3. Compute the retry budget within the 2-second deadline.
4. Retry only classified errors; never retry 401/403, validation, or configuration errors.
5. Determine how many times the SDK retries internally before the application layer sees an error.

### Part B — Design Rate Limiting

1. Choose a global token bucket with a long-term rate not exceeding 120 requests/s.
2. Set burst capacity according to the partner contract.
3. Add per-tenant limits if fairness is needed.
4. Set a concurrency cap based on latency and capacity.
5. Use Redis/gateway/dispatcher for cluster-wide quota; do not use a local 20 requests/s limit and assume total traffic stays constant when scaling.

### Part C — Testing

1. Run a burst test with multiple replicas/workers.
2. Have a test server return 429 and Retry-After.
3. Verify no retries occur before the server-requested delay.
4. Count total requests including SDK retries and Spring retries.
5. Make the Redis limiter unavailable and verify fail-open/fail-closed behavior.
6. Scale up replica count to verify total outbound rate.
7. Test deadline expiration while waiting on permits/backoff.
8. Test fairness between two tenants with vastly different traffic volumes.

### Deliverables

- Table of backoff cap, jitter type, Retry-After handling, and retry budget.
- Rate limiter/concurrency limiter configuration specifying local vs. global scope.
- Burst test and distributed test results.
- Metrics for 429s, retry attempts, wait times, rejected requests, and deadline exhaustion.
- Explanation of test limitations relative to production quotas.

### Self-Check Questions

1. Why can exponential backoff without jitter still cause synchronized retries?
2. How do full jitter and equal jitter differ?
3. If Retry-After is 5 seconds while only 1 second remains on the deadline, what should the application do?
4. How does a rate limit differ from a quota and a concurrency limit?
5. Why does a local RateLimiter fail to protect a cluster-wide quota?
6. How does a token bucket permit bursts?
7. In what scenarios is a leaky bucket a better fit than a token bucket?
8. Why can internal SDK retries cause an application rate limiter to undercount actual requests?
9. What bug does atomicity prevent in a Redis-backed limiter?
10. Why must retry traffic also consume quota and retry budget?
11. When the limiter backend fails, what trade-off do fail-open and fail-closed create?
12. Why should you avoid immediately retrying when Resilience4j RateLimiter rejects a permit?

## 21. Takeaways

- **Exponential backoff** increases wait durations; **jitter** spreads retry timing; **Retry-After** is a service signal that must be honored per contract.
- Never retry earlier than the server instructs. If Retry-After exceeds the deadline, return a controlled error or offload to an asynchronous business retry.
- **Rate limits** control rate, **quotas** control total usage over a period, and **concurrency limits** control active operations; connection pools and queue capacities address other bounds.
- Fixed window is simple but suffers boundary bursts; sliding windows are more accurate at higher cost; token bucket permits bounded bursts; leaky bucket smooths output rate.
- A local rate limiter is not a cluster-wide quota. Across multiple replicas, use a gateway, distributed limiter, dispatcher, or scale-aware quota allocation.
- Combine rate limits, concurrency, backpressure, circuit breakers, deadlines, and retry budgets; do not let retries add load while a service is throttling.
- Test 429s, Retry-After, retry amplification, bursts, multi-replica runs, limiter backend failures, and fairness; measure actual requests at every layer.

## References

- [Resilience4j RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Azure SDK for Java — Retry policy](https://learn.microsoft.com/azure/developer/java/sdk/retries)
- [Azure Storage retry policy for Java](https://learn.microsoft.com/azure/storage/blobs/storage-retry-policy-java)
- [Azure Cosmos DB request units and throttling](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [HTTP Retry-After header semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)
- [Token Bucket algorithm overview](https://en.wikipedia.org/wiki/Token_bucket)
- [AWS SDK for Java 2.x retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
