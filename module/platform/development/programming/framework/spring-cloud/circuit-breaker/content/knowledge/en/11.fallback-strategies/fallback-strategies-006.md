# Avoiding Fallbacks That Call Back Into the Failing System

A fallback is only helpful when it allows the application to produce a safe response while the primary call fails or the Circuit Breaker is `OPEN`. If a fallback calls back into the very service that just failed, the application can continue generating load on the dependency, bypass circuit breaking, or fall into a fallback loop. Therefore, a fallback must obtain its result from an independent source, use existing backup data, or return an explicitly described degraded state.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, Spring Cloud Circuit Breaker and Resilience4j help limit impact when a dependent service is slow or unavailable. Fallback is one part of that protection strategy; it must coordinate with `CLOSED`, `OPEN`, `HALF_OPEN` states, timeouts, bulkheads, and observability to avoid turning one service's outage into a cascading failure.

## 1. Why Must a Fallback Never Call the Failing Dependency Again?

Suppose the Order service calls the Inventory service to get stock levels. When Inventory becomes overloaded, the Circuit Breaker opens and rejects new calls. The fallback executes to return cached data or a notice that stock cannot currently be verified.

If the fallback calls the Inventory service again, two dangerous situations arise:

- The fallback calls the HTTP client directly, bypassing the Circuit Breaker. Even though the circuit is `OPEN`, new requests still hit the Inventory service and continue adding load.
- The fallback calls back into the method protected by the same Circuit Breaker. The nested call can be immediately rejected while the circuit is `OPEN`, triggering the fallback again and causing recursion or an infinite loop.

Diagram of a flawed design:

~~~mermaid
flowchart TD
    A[Request from Order service] --> B[Circuit Breaker]
    B --> C[Inventory service call]
    C -->|Error or rejected| D[Fallback]
    D --> E[Call Inventory service again]
    E -->|Continues failing| D
    D --> F[Loop or repeated load]
~~~

A Circuit Breaker is meant to stop new calls to a struggling dependency. A fallback calling that dependency again defeats the protection goal. Nor should a fallback method indirectly call another service if that service routes through the same failing call path.

## 2. Recognizing Dangerous Fallbacks

The following example illustrates a design flaw: the fallback method calls back into the protected `getInventory` method itself.

~~~java
public InventoryResult getInventory(String sku) {
    CircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            () -> inventoryClient.get(sku),
            failure -> fallbackInventory(sku, failure)
    );
}

private InventoryResult fallbackInventory(String sku, Throwable failure) {
    // Unsafe: calls back into the protected flow itself.
    return getInventory(sku);
}
~~~

When the circuit is `OPEN`, the call inside the fallback can be rejected immediately and invoke the fallback again. If the fallback keeps calling `getInventory`, execution can recurse until the stack overflows. If instead the fallback calls `inventoryClient.get(sku)` directly, it still sends extra requests to the Inventory service even though the Circuit Breaker blocked the primary call.

Another variant occurs when the fallback calls an intermediary service, yet that service uses the same endpoint or the same Inventory service cluster. A different class name or URL does not guarantee an independent data source. You must examine the entire request path, including gateways, service discovery, proxies, and indirectly invoked clients.

Ask yourself: when the primary service is unavailable, does the fallback genuinely avoid the failing resources, endpoints, and infrastructure? If the answer is no, that fallback does not yet provide a trustworthy recovery path.

## 3. Choosing an Independent Backup Data Source

A good fallback typically uses one of the following sources:

| Backup Source | When Appropriate | What Must Be Conveyed |
| --- | --- | --- |
| Local cache | Data was preloaded and can be used for a short duration | Mark data as stale, update timestamp, and age limit |
| Independent cache or read store | Can be queried without depending on the same failing system | Ensure backup infrastructure does not share the same failure |
| Replica or alternative provider | A secondary source exists with independent serving capacity | Check consistency, access permissions, and rate limits |
| Precomputed data | Results can be generated ahead of time without calling the primary service during fallback | Specify timestamp and scope of applicability |
| Degraded state | No trustworthy data is available to return | Clearly indicate unable to verify; do not pretend success |

A fallback does not always have to return data. For payment or order-state update operations, returning "cannot confirm yet" can be safer than synthesizing a fake success result. The calling layer can keep the request in a pending state, prompt for a retry later, or show an appropriate message.

Caches must also be evaluated for independence. If the cache is a Redis cluster sharing the same network, credentials, or infrastructure as the failing service, the cache may suffer the exact same outage. For data requiring high consistency, stale data may not be permitted for decision-making. Fallbacks must follow business rules regarding data age and acceptable staleness.

## 4. Synchronous Example: Cache Fallback Instead of Calling Inventory Again

Suppose `inventoryClient` calls the Inventory service, while `inventoryCache` provides the latest previously stored data. The fallback only reads from the cache and returns an unavailable status if no entry exists:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    public InventoryResult getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> fallbackInventory(sku, failure)
        );
    }

    private InventoryResult fallbackInventory(
            String sku,
            Throwable failure) {
        return inventoryCache.findRecent(sku)
                .map(cached -> cached.withStale(true))
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }
}
~~~

In this example:

1. The primary call accesses the Inventory service solely through `inventoryClient`.
2. When the primary call fails or the circuit is `OPEN`, the Circuit Breaker passes the cause to the fallback.
3. The fallback reads previously stored data from the cache; it does not call `inventoryClient` or `getInventory` again.
4. If the cache has no data, the application returns an unverified-inventory status.
5. The `stale` flag lets the calling layer know the cached data may be outdated.

`InventoryCache` here is an illustrative abstraction. If implemented with a remote cache, set timeouts and resource limits on cache reads, and assess whether the cache infrastructure is independent of the Inventory service.

## 5. Reactive Example: Keeping the Fallback Inside the Mono Chain

With `WebClient`, the fallback should return a publisher and continue asynchronous processing. Never call `block()` or send a new request to the same Inventory service inside the fallback:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReactiveInventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;
    private final ReactiveInventoryCache inventoryCache;

    public ReactiveInventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient,
            ReactiveInventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
        this.inventoryCache = inventoryCache;
    }

    public Mono<InventoryResult> getInventory(String sku) {
        ReactiveCircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        Mono<InventoryResult> primary = inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResult.class);

        return circuitBreaker.run(
                primary,
                failure -> inventoryCache.findRecent(sku)
                        .map(cached -> cached.withStale(true))
                        .defaultIfEmpty(InventoryResult.unavailable(sku))
        );
    }
}
~~~

The cache publisher is returned directly as the fallback. When the cache has no data, `defaultIfEmpty` produces an unavailable result. Both the primary publisher and fallback publisher have type `Mono<InventoryResult>`.

Do not do the following:

~~~java
return circuitBreaker.run(
        primary,
        failure -> inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResult.class)
);
~~~

This snippet sends another request to the same Inventory service after the primary call failed or was rejected. If Inventory is overloaded, the fallback keeps generating load; if the circuit is `OPEN` and the fallback request bypasses that circuit, it also circumvents the blocking mechanism. Being reactive does not make repeated calls safer; the publisher still fires a request when subscribed.

## 6. If a Remote Alternative Source Is Required

Sometimes a cache is insufficient and the application has a second provider or replica. You may use an alternative source if it is independent in network path, serving capacity, and fault domain. However, the alternative source is still a dependency and must be protected.

Some guidelines:

- Use a separate client and Circuit Breaker for the alternative source, with a short timeout and a bulkhead limiting concurrent calls.
- Never configure the alternative source's fallback to route back to the primary source. The fallback chain must terminate at a terminal response such as a cache or an unavailable status.
- Bound the number of attempts. Never use infinite retries inside a fallback.
- Only invoke the alternative source for recoverable errors; input errors or business errors must be propagated.
- Separately monitor the alternative source call rate, response latency, and failure rate.

Diagram of a bounded fallback chain:

~~~mermaid
flowchart TD
    A[Request] --> B[Primary service Circuit Breaker]
    B -->|Success| C[Primary result]
    B -->|Error or OPEN| D[Fallback]
    D --> E[Independent cache]
    E -->|Valid data present| F[Cached result, marked stale]
    E -->|No data| G[Unavailable status]
    D -. Alternative source if permitted .-> H[Separate Circuit Breaker]
    H -->|Success| I[Result from alternative source]
    H -->|Error or OPEN| G
~~~

In this model, the alternative source never calls back to the primary service. If the alternative source also fails, the flow ends with cache or an unavailable status. Avoid designing mutually dependent fallbacks that form a cycle where A calls B, B calls C, and C calls back to A.

## 7. Timeouts, Bulkheads, and Retries Inside Fallbacks

A fallback typically runs precisely when the system is degraded, so it needs minimal resources and fast completion. A fallback calling a remote service can hang or consume all worker threads, leaving the application congested even though the Circuit Breaker blocked the primary call.

| Mechanism | Role in the Fallback Path |
| --- | --- |
| Timeout | Bounds wait time on a cache or alternative source |
| Bulkhead | Caps concurrent fallback executions to prevent resource exhaustion |
| Separate Circuit Breaker | Stops calling an alternative source that is also failing |
| Bounded retry | Retries only transient errors when the operation is safe and time budget remains |

Do not automatically retry the same primary service inside the fallback. When the Circuit Breaker is `OPEN`, the goal is to stop sending requests to that service. If retries are needed for an alternative source, keep the retry count small, use backoff and jitter, apply them only to idempotent operations, and stay within the allowed total response time.

The fallback timeout should be shorter than or accounted for within the overall request time budget. If an API has a 1-second SLA while the fallback waits 5 seconds on an alternative source, the fallback fails to improve user experience. A bulkhead bounds resource consumption but does not replace a timeout.

## 8. Avoiding Loops Through Services or Proxies

Mistakenly calling back into the failing dependency does not always appear directly within the same method. Indirect forms include:

- The fallback calls an internal service, which calls back into a gateway that also triggers the fallback.
- The fallback uses a Feign or `WebClient` whose URL points through an API gateway that routes back to the original service.
- The backup source shares a backend cluster or database that is the root cause of the primary source's outage.
- The fallback calls a method annotated or wrapped with the same Circuit Breaker, which triggers the fallback again.
- Retries placed inside the fallback keep firing requests even though the main Circuit Breaker is open.

During design, trace the actual path of the request rather than looking only at bean or client names. Clearly separate the primary data source, backup source, corresponding Circuit Breakers, and the final termination point when all sources are unavailable.

A helpful rule is that a fallback must never call back into its own protected entry point. If a remote alternative source is needed, call a distinct abstraction with its own timeout and Circuit Breaker; that abstraction's terminal fallback must return an error or terminal status, never loop back to the primary source.

## 9. Choosing Semantically Accurate Fallback Responses

Fallbacks must preserve business semantics. A technically successful response carrying fabricated data can cause subtler bugs than an explicit error.

| Situation | Response to Consider |
| --- | --- |
| Cache has data within allowed age | Return cached data and mark update timestamp |
| Cache has data but past business expiration | Return unavailable status or require re-verification |
| No data and no alternative source | Return temporarily unavailable status |
| Write operation like payment has unknown outcome | Return pending/unknown status and use reconciliation; do not fake success |
| Business error such as resource not found | Propagate the business error instead of substituting backup data |

Be especially careful with write operations. If a payment request times out, you cannot conclude the transaction failed; the payment system may have processed it while the response was lost. The fallback should return an undetermined status and rely on an idempotency key or reconciliation workflow to resolve the outcome. Never blindly resend a write command from a fallback.

## 10. Monitoring Fallbacks to Detect Outages

An API continuing to return HTTP 200 does not mean the dependent service is healthy. If the fallback frequently serves cached data, the system can mask an underlying outage.

Monitor:

- Primary call failures and Circuit Breaker rejection counts.
- Fallback invocation counts by instance and cause category.
- Cache hit rate, cache miss rate, and average age of backup data.
- Alternative source invocation counts and failure rate.
- Fallback latency, timeout count, and fallback self-failure count.
- Ratio of degraded/unavailable responses to total requests.

Logs should include dependency name, Circuit Breaker name, exception type, and trace ID. Do not log tokens, personal data, or full error bodies unnecessarily. Metrics must separate primary source failures from fallback source failures so operations teams can pinpoint bottlenecks accurately.

## 11. Verifying Fallbacks Do Not Call the Primary System Again

You can verify this via unit tests or integration tests using mock clients. Beyond checking the returned result, verify the invocation count against the primary dependency.

| Scenario | Expected Outcome | What to Verify |
| --- | --- | --- |
| Primary call succeeds | Returns primary result | Fallback is not invoked |
| Primary call fails, cache has data | Returns cached data marked stale | Primary client called only once; cache is read |
| Primary call fails, cache empty | Returns unavailable | No second request sent to primary service |
| Circuit Breaker `OPEN` | Fallback runs when call is rejected | Primary client is not called on that request |
| Alternative source fails | Returns terminal status or appropriate error | No path loops back to primary source |
| Fallback itself fails | Fallback error propagates up and is logged | No infinite fallback recursion |

A key test is configuring the primary client to throw an error, then asserting the client invocation count remains one after the fallback finishes. In the `OPEN` state, assert the primary client invocation count is zero for rejected requests.

## 12. Safe Fallback Design Checklist

When adding a fallback for a dependency, follow this sequence:

1. Identify which causes trigger the fallback: HTTP exceptions, timeouts, connection errors, or an `OPEN` Circuit Breaker.
2. List backup data sources and verify they are independent of the primary service's fault domain.
3. Pick a business-meaningful response: stale-marked cached data, pending status, or unavailable status.
4. Implement the fallback so it never calls back into the primary client, protected entry point, or any service routing back to that dependency.
5. If a remote alternative source is needed, protect it with its own timeout, bulkhead, and Circuit Breaker; configure a terminal final fallback.
6. Test empty caches, failing alternative sources, an `OPEN` Circuit Breaker, and exceptions thrown inside the fallback itself.
7. Monitor fallback counts, latency, cache hit/miss rates, and degraded response ratios.

A safe fallback creates a bounded recovery path with a clear termination point. Only when it uses an independent source or returns an honest degraded state does the Circuit Breaker truly offload a failing service and stop failures from spreading across the rest of the Spring Cloud system.
