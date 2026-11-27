# How Rate Limiter (Rate Control) Differs from Bulkhead (Concurrency Control)

Rate Limiter and Bulkhead both control load in a Spring Cloud application, yet they protect two different limits. **Rate Limiter** caps the number of calls accepted over a time period. **Bulkhead** caps the number of calls executing at the same time. A service may need both: Rate Limiter controls incoming request rate, while Bulkhead keeps the number of tasks occupying resources from exceeding processing capacity.

If you only use Rate Limiter, calls granted permission in consecutive cycles can still pile up when the service responds slowly. If you only use Bulkhead, the application caps concurrent calls, yet can still send a huge volume of requests in one second when each call finishes quickly. Understanding the distinction helps you choose thresholds and compose them with circuit breaker, timeout, and fallback.

## Two Different Questions: How Many Calls per Second and How Many Calls at Once?

Rate Limiter answers the question: **Within a time period, how many calls are allowed to start?**

Bulkhead answers the question: **At a single moment, how many calls are allowed to occupy processing resources?**

| Criterion | Rate Limiter | Bulkhead |
|---|---|---|
| Limit | Number of call permits within a time period. | Number of calls running concurrently. |
| Goal | Throttle rate, enforce quota, and protect dependency limits. | Isolate resources and prevent one dependency from exhausting processing capacity. |
| When limit is exhausted | Reject or wait until new call permits become available. | Reject or wait until an execution slot becomes free. |
| Typical parameters | `limitForPeriod`, `limitRefreshPeriod`, `timeoutDuration`. | `maxConcurrentCalls`, `maxWaitDuration`. |
| Does not guarantee | Does not limit how many calls are currently running. | Does not limit total calls over a time period. |

For example, the inventory service allows at most 50 calls per second and the application wants at most 20 inventory calls waiting or executing at any instant. Rate Limiter can set 50 call permits per second; Bulkhead sets 20 concurrent slots.

If each call takes only 10 ms, a concurrency limit of 20 can allow many back-to-back batches within one second. Bulkhead does not replace a 50 calls/second quota. Conversely, if each call takes 2 seconds, a Rate Limiter granting 50 permits in one second can leave many calls still running at the same time. Bulkhead prevents task accumulation.

## Rate Limiter in Resilience4j

Resilience4j RateLimiter grants a number of call permits in each refresh cycle. Key parameters:

- `limitForPeriod`: number of call permits granted in one cycle.
- `limitRefreshPeriod`: duration of the permit refresh cycle.
- `timeoutDuration`: maximum time a call waits for a permit before being rejected.

Configuration example for at most 50 call permits per second:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      inventory-read:
        limitForPeriod: 50
        limitRefreshPeriod: 1s
        timeoutDuration: 0s
~~~

With `timeoutDuration: 0s`, calls do not wait when permits are exhausted and are rejected immediately. If a wait duration greater than 0 is set, the caller may wait for a permit in the next cycle. The wait time must fit within the request deadline; do not hold a thread for long just waiting for quota.

Resilience4j's RateLimiter refreshes permits on a configured period. It is not a global counter shared across all servers, nor should it be treated as a millisecond-accurate sliding-window limiter. Traffic can cluster near the boundary between two periods. If you need system-wide limits or burst smoothing via token bucket/leaky bucket at the gateway, choose the appropriate mechanism at that layer.

When permits are exhausted, Resilience4j throws `RequestNotPermitted`. This is a load-throttling decision in the calling application, not evidence that the inventory service is failing. You can map it to HTTP 429 or an overload response matching the API contract.

## Bulkhead in Resilience4j

Bulkhead limits the number of calls allowed to execute concurrently. Resilience4j offers two main types:

| Type | How it works | When appropriate |
|---|---|---|
| Semaphore Bulkhead | Uses a semaphore to limit concurrent calls on the current calling thread. | Synchronous calls or when you only need to cap active in-flight tasks. |
| Thread Pool Bulkhead | Runs tasks in a dedicated thread pool with a bounded queue. | When execution thread groups must be separated, especially to isolate blocking tasks. |

Semaphore bulkhead example for the inventory service:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory-read:
        maxConcurrentCalls: 20
        maxWaitDuration: 0s
~~~

`maxConcurrentCalls` sets the maximum number of execution slots. `maxWaitDuration` defines how long to wait for a free slot; set to 0 to reject immediately when full. When no slots remain, Resilience4j throws `BulkheadFullException`.

For Thread Pool Bulkhead, configure separate parameters:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory-refresh:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Thread Pool Bulkhead has its own thread pool and queue. The queue should have a small limit aligned with the deadline; an oversized queue only delays rejection and increases latency. When the queue is full, new tasks are rejected. Do not use Thread Pool Bulkhead solely to enforce a concurrency limit; a semaphore bulkhead is simpler if you do not need to offload tasks onto a separate thread pool.

## Examining a Real-World Scenario

Suppose the order service calls the inventory service. The dependency can handle about 50 calls/second, and the application only wants at most 20 inventory calls executing concurrently.

- Rate Limiter grants at most 50 permits in a one-second cycle.
- Bulkhead keeps at most 20 concurrent calls.
- Timeout bounds the wait time for each call.
- Circuit breaker stops sending calls when the dependency repeatedly fails or responds too slowly.
- Fallback determines the appropriate response when a call fails or is rejected.

~~~mermaid
flowchart TD
    A[Request arrives at order service] --> B[Rate Limiter]
    B -->|Permit granted| C[Bulkhead]
    B -->|Quota exhausted| R[Reject / overload response]
    C -->|Slot available| D[Circuit Breaker]
    C -->|At capacity| R
    D -->|Permitted| E[Timeout + inventory call]
    D -->|OPEN| F[Fallback]
    E -->|Success| G[Normal result]
    E -->|Error or timeout| F
    F --> H[Fallback result]
~~~

The diagram illustrates a commonly useful composition order: Rate Limiter and Bulkhead control intake capacity before a call goes through circuit breaker. Rejections from exhausted quota or full capacity are not mistaken for failures of the inventory service.

## Combining Rate Limiter, Bulkhead, and Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker provides the abstraction for circuit breakers; RateLimiter and Bulkhead can be used directly from Resilience4j to add load-limiting policies. The example below uses Spring Cloud's factory to create a circuit breaker while wrapping the call with RateLimiter and a semaphore Bulkhead.

~~~java
import java.util.function.Supplier;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryQueryService {

    private final InventoryClient inventoryClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RateLimiter rateLimiter;
    private final Bulkhead bulkhead;

    public InventoryQueryService(
            InventoryClient inventoryClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryClient = inventoryClient;
        this.circuitBreakerFactory = circuitBreakerFactory;

        this.rateLimiter = RateLimiter.of(
                "inventory-read",
                RateLimiterConfig.custom()
                        .limitForPeriod(50)
                        .limitRefreshPeriod(java.time.Duration.ofSeconds(1))
                        .timeoutDuration(java.time.Duration.ZERO)
                        .build()
        );

        this.bulkhead = Bulkhead.of(
                "inventory-read",
                BulkheadConfig.custom()
                        .maxConcurrentCalls(20)
                        .maxWaitDuration(java.time.Duration.ZERO)
                        .build()
        );
    }

    public Inventory find(String sku) {
        Supplier<Inventory> circuitProtected = () ->
                circuitBreakerFactory.create("inventory-read").run(
                        () -> inventoryClient.fetch(sku),
                        error -> Inventory.unavailable(sku)
                );

        Supplier<Inventory> bulkheadProtected =
                Bulkhead.decorateSupplier(bulkhead, circuitProtected);

        Supplier<Inventory> rateLimited =
                RateLimiter.decorateSupplier(rateLimiter, bulkheadProtected);

        try {
            return rateLimited.get();
        } catch (RequestNotPermitted ex) {
            throw new InventoryRateLimitedException(
                    "Inventory request rate exceeded", ex
            );
        } catch (BulkheadFullException ex) {
            throw new InventoryBusyException(
                    "Inventory concurrency limit reached", ex
            );
        }
    }
}
~~~

`InventoryClient`, `Inventory`, `InventoryRateLimitedException`, and `InventoryBusyException` are illustrative types. In a real application, create RateLimiter and Bulkhead as beans or retrieve them from a registry to share the same instance across the application, and use `application.yml` configuration rather than instantiating new ones per service instance.

The execution order of the example is:

1. RateLimiter checks call permission.
2. Bulkhead acquires a concurrency slot.
3. Spring Cloud CircuitBreaker checks state and executes the call.
4. If the call is permitted, InventoryClient calls the remote service.

With this order, `RequestNotPermitted` and `BulkheadFullException` occur outside the circuit breaker. Therefore, they do not inflate the failure rate of the circuit breaker protecting the inventory service. The circuit breaker focuses on recording dependency errors and latency.

If you place the circuit breaker on the outermost layer, RateLimiter or Bulkhead rejection errors can enter the circuit breaker's error classifier. In that case, configure an ignore predicate for these policy exceptions or change the decorator order. Otherwise, the application could open the circuit because of its own load-limiting actions.

## Choosing the Policy Composition Order

The decorator order affects which resource is acquired first and which errors are recorded by the circuit breaker.

| Order | Impact |
|---|---|
| RateLimiter → Bulkhead → CircuitBreaker → call | Checks quota first, acquires concurrency slot second; circuit breaker mainly observes dependency errors. |
| Bulkhead → RateLimiter → CircuitBreaker → call | May hold a bulkhead slot while waiting for quota, wasting concurrency capacity. |
| CircuitBreaker → RateLimiter → Bulkhead → call | Circuit breaker may record RateLimiter/Bulkhead rejection errors unless ignore rules are configured properly. |

For synchronous calls, RateLimiter → Bulkhead → CircuitBreaker is usually an intuitive choice when you want to reject local overload first and count only dependency errors in the circuit breaker. However, if RateLimiter has to wait long for a permit, the request still holds a thread during the wait. Set `timeoutDuration` short or to 0 when fast rejection is needed.

For reactive operations, use Resilience4j's corresponding Reactor operators and verify the order when applying `transformDeferred`. Do not call `block()` to force synchronous policies into a reactive chain.

## Rough Concurrency Limit Calculation

You can estimate the average number of in-flight calls using the relationship between throughput and processing time:

`Average concurrent calls ≈ calls per second × average processing time in seconds`

If a service handles 40 calls/second and average response time is 250 ms (0.25 seconds), the average number of in-flight calls is approximately 10. If response time rises to 800 ms, the same throughput requires roughly 32 concurrent calls.

This is an average-load estimate, not a safety limit. Also factor in p95/p99, bursts, connection hold time, and thread/connection pool capacity. A Bulkhead set too low will reject normal traffic; set too high, it will fail to protect the system when the dependency slows down.

Rate Limiter must also be sized according to actual dependency capacity and provider quotas. If each replica has its own RateLimiter set to 50 permits/second and there are 4 replicas, total throughput can reach roughly 200 permits/second across the cluster. If the quota is system-wide, divide quota across replicas or use a gateway/distributed rate limiter with coordination.

Similarly, a Bulkhead inside each JVM is a local limit. Four replicas, each allowing 20 concurrent calls, can generate up to around 80 concurrent calls to the dependency. Calculate total limits at cluster scale and leave headroom for other callers.

## Distinguishing Policy Rejections from Dependency Failures

RateLimiter and Bulkhead can reject calls before a request ever reaches the upstream service. These errors should be distinguished from timeouts, connection errors, and server errors.

| Exception or outcome | Cause | Recommended response |
|---|---|---|
| `RequestNotPermitted` | Call permits exhausted in the RateLimiter period. | HTTP 429 or retry-later overload response. |
| `BulkheadFullException` | Concurrent call limit reached. | HTTP 503 or temporary overload response. |
| `CallNotPermittedException` | Circuit breaker is OPEN. | Fallback or dependency temporarily unavailable response. |
| Timeout or connection error | Dependency is slow or unreachable. | Appropriate fallback and record in circuit breaker. |
| Business error | Invalid request or rule violation. | Return business error; do not miscount as infrastructure failure. |

Exact HTTP codes depend on the API contract and how the system separates quota limits from resource overload. If returning `Retry-After`, provide a grounded wait time based on the quota policy or system state. Do not encourage clients to retry continuously, as that can add further load.

## Combining Timeout, Retry, and Fallback

Bulkhead and RateLimiter do not replace timeouts. Bulkhead caps concurrent running calls; if one call holds a slot for too long, new requests can still be rejected. Timeout frees caller wait time and helps return bulkhead slots when tasks actually complete or can be canceled.

Retry can consume extra quota and concurrency slots. If retry sits inside RateLimiter, each attempt may require a new permit depending on how decorators are layered. If retry sits outside RateLimiter, the entire sequence might acquire only one permit despite generating multiple calls to the dependency. Choose the policy according to the dependency's quota: quotas typically count every actual request sent.

Do not retry `RequestNotPermitted` or `BulkheadFullException` immediately. These signal that the application has hit its limit; immediate retries will increase pressure. You can return a response advising the caller to retry after a controlled delay. For dependency errors, retries should only be used for transient errors and must stay within the overall deadline.

Fallback must also distinguish the root cause. Cached data may be appropriate when a circuit breaker opens due to a failing dependency, but if RateLimiter rejects because a caller exceeded quota, serving cache might inadvertently let callers bypass the limit. Explicitly decide whether the quota applies to all responses or only calls to the dependency.

## Monitoring Each Policy's Effectiveness

Do not lump every rejection into a single “circuit breaker failure” metric. Each mechanism has its own objective and needs separate metrics:

- RateLimiter: granted permits, rejected calls, permit wait time, and quota utilization.
- Bulkhead: active concurrent calls, available slots, rejection count, and queue depth if using a thread pool.
- Circuit breaker: CLOSED/OPEN/HALF_OPEN state, error count, failure rate, slow-call rate, and rejected call count.
- Timeout: expiration count, latency before timeout, and tasks not stopping after cancellation.
- Fallback: fallback count by cause and returned data type.

Use bounded-cardinality labels such as dependency name, policy ID, and outcome type. Do not attach user IDs, order IDs, or parameterized URLs to metric labels. For local RateLimiters and Bulkheads, monitor per replica and aggregate at cluster level to detect total load exceeding the upstream service's quota.

## Testing Rate Limiter and Bulkhead Composition

You can test each mechanism independently and then test the combined order:

| Scenario | Expected verification outcome |
|---|---|
| Send fewer calls than quota in one period | RateLimiter grants permission to the calls. |
| Exceed quota with timeoutDuration set to 0 | Calls are rejected fast with RequestNotPermitted. |
| Slow calls reaching maxConcurrentCalls | Bulkhead rejects new calls with BulkheadFullException. |
| A call finishes | Semaphore bulkhead slot is released. |
| Circuit breaker OPEN | Calls are rejected by circuit breaker and fallback executes. |
| RateLimiter rejects before circuit breaker | Circuit breaker does not record a dependency failure for this rate-limited rejection. |
| Bulkhead rejects before circuit breaker | Dependency failure rate does not rise due to concurrency limit errors. |
| Retry hits RateLimiter or Bulkhead rejection | Does not retry immediately; obeys deadline and retry policy. |
| Running multiple replicas | Total quota and total concurrency are accounted for at cluster scale. |

Use a controlled clock or short refresh period in tests to observe RateLimiter replenishing permits. For Bulkhead, use mock calls with a latch to hold several concurrency slots, then verify the next call is rejected and a slot is released once a task completes.

## Policy Selection Workflow

1. Identify the dependent service's time-based quota and select an appropriate RateLimiter.
2. Measure processing time, throughput, and thread/connection limits to choose `maxConcurrentCalls`.
3. Decide whether to reject immediately or wait for a permit/slot; keep wait times inside the request deadline.
4. Place RateLimiter and Bulkhead before circuit breaker if you want load-limiting rejections not to count as dependency errors.
5. Configure timeouts so slow calls do not hold Bulkhead slots indefinitely.
6. Distinguish `RequestNotPermitted`, `BulkheadFullException`, and `CallNotPermittedException` when returning errors.
7. Bound retries, avoid immediate retries on rejection, and account for quota per real outgoing call.
8. Sum total quota and concurrency across all replicas.
9. Track separate metrics and test both normal load and slow-dependency scenarios.

Rate Limiter controls call rate over a period; Bulkhead controls how many calls occupy resources simultaneously. Composing them ahead of the circuit breaker lets the application throttle traffic, isolate resources, and allow the circuit breaker to focus on reflecting dependent service health. Choose limits based on actual quotas, latency, and capacity, while accounting for aggregate load when deploying multiple replicas.
