# Isolating Two Dependencies with Bulkheads and Separate Circuit Breaker IDs

## Practice Objectives

A product aggregation service often calls multiple dependencies within a single request. For instance, a product details page needs stock quantity from `inventory-service` and selling price from `pricing-service`. These two systems have different capacity, latency, and failure domains. If one dependency slows down, it should not exhaust resources and prevent calls to the other dependency from being served.

In this hands-on practice, we configure two independent layers of protection for each dependency:

- **Separate Circuit Breaker IDs:** `inventory` tracks inventory errors and state; `pricing` tracks pricing. One dependency opening its circuit does not cause the other dependency to be rejected.
- **Separate Bulkheads:** each dependency has its own worker limit and queue. A spike in load on inventory does not exhaust the pool reserved for pricing.
- **Separate Fallbacks:** when one dependency is unavailable, the service returns a semantically accurate degraded state for that slice of data. The rest can still succeed.

We use Spring Cloud Circuit Breaker with Resilience4j in a synchronous service. The example uses `ThreadPoolBulkhead` to isolate blocking calls. For reactive applications, bulkhead selection and publisher execution differ; never run blocking calls directly on the event loop.

## Model to Protect

The business flow can be visualized as follows:

```text
                  Product Summary API
                          |
                 ProductSummaryService
                    /           \
                   /             \
          ID: inventory        ID: pricing
          Separate Bulkhead    Separate Bulkhead
          Circuit Breaker      Circuit Breaker
                |                    |
                v                    v
        inventory-service      pricing-service
```

The two branches are invoked independently. If inventory slows down, inventory calls can queue in their own queue and be rejected when the pool is full. Pricing still uses its own pool and breaker. When the inventory Circuit Breaker transitions to `OPEN`, new inventory calls route to the inventory fallback; the pricing breaker continues operating on its own outcomes.

The key point is that IDs must represent failure domains. If both calls share the ID `remote-service`, state and statistics get mixed. Six timeouts in inventory could open the shared breaker and block pricing even though pricing is healthy.

## 1. Declare Dependencies

With Maven, add the Spring Cloud Circuit Breaker Resilience4j starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

This starter integrates Spring Cloud's `CircuitBreakerFactory` abstraction with Resilience4j. Manage versions using a Spring Cloud BOM compatible with your project's Spring Boot version. Resilience4j bulkhead support requires the Bulkhead module on the runtime classpath; inspect the dependency graph to confirm the starter/provider in use brings in the required module.

This example uses blocking calls via `RestTemplate`. If the project uses Spring Framework 6.1+ `RestClient`, you can swap the HTTP client while keeping the exact same Circuit Breaker boundary. Configure connect timeout and response/read timeout on the HTTP client; a Bulkhead does not enforce a deadline on a network request by itself.

## 2. Configure Breaker and Bulkhead per Dependency

Define two separate instances in `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 40
        waitDurationInOpenState: 25s
        permittedNumberOfCallsInHalfOpenState: 1

  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms

      pricing:
        coreThreadPoolSize: 2
        maxThreadPoolSize: 4
        queueCapacity: 8
        keepAliveDuration: 20ms
```

Both configuration groups share the same IDs `inventory` and `pricing`, yet each group has a distinct responsibility:

| Dependency | Circuit Breaker | ThreadPoolBulkhead |
| --- | --- | --- |
| Inventory | Window of 20 results, minimum 10 samples, 50% failure threshold, open 15s, 2 probes in `HALF_OPEN`. | 4 core workers, max 8 workers, queue of 16 tasks. |
| Pricing | Window of 10 results, minimum 5 samples, 40% failure threshold, open 25s, 1 probe in `HALF_OPEN`. | 2 core workers, max 4 workers, queue of 8 tasks. |

These numbers are practice settings only. In real deployments, choose them based on target latency, traffic volume, connection limits, processing capacity, and each dependency's SLA.

### What Does ThreadPoolBulkhead Limit?

`coreThreadPoolSize` is the baseline worker count; `maxThreadPoolSize` is the maximum worker limit; `queueCapacity` is the number of tasks allowed to wait. When both workers and queue are full, new tasks are rejected. With the inventory configuration above, the pool can run at most 8 concurrent tasks and hold at most 16 waiting tasks. Pricing has its own pool and queue, so inventory cannot occupy its capacity.

Spring Cloud Circuit Breaker Resilience4j supports Bulkhead when the corresponding module is present. The provider typically uses `FixedThreadPoolBulkhead` as the default. If you want to switch to `SemaphoreBulkhead`, configure `spring.cloud.circuitbreaker.resilience4j.enableSemaphoreDefaultBulkhead=true` according to the version in use and declare `resilience4j.bulkhead.instances`. A semaphore limits concurrent calls without offloading blocking work to a separate thread pool. For blocking calls, understand this distinction clearly before choosing.

Do not configure both an automatic `ThreadPoolBulkhead` and a second manual Bulkhead for the same call without a clear purpose. Two overlapping limits can reduce accepted tasks below expectations and make diagnosing rejections harder. Pick a single owner for the Bulkhead policy per dependency.

## 3. Create Clients for Both Dependencies

Declaring separate clients makes network boundaries easy to read and test:

```java
public interface InventoryClient {
    InventoryResponse find(String sku);
}

public interface PricingClient {
    PricingResponse quote(String sku);
}
```

An implementation can use `RestTemplate`:

```java
@Component
public class HttpInventoryClient implements InventoryClient {
    private final RestTemplate restTemplate;

    public HttpInventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Override
    public InventoryResponse find(String sku) {
        return restTemplate.getForObject(
            "http://inventory-service/items/{sku}",
            InventoryResponse.class,
            sku
        );
    }
}
```

Pricing has a similar implementation calling `pricing-service`. In production, base URLs should come from configuration or service discovery; the example uses an illustrative URL to make the target dependency clear.

## 4. Use Separate IDs When Creating Circuit Breakers

Inject `CircuitBreakerFactory` into the aggregation service. Each supplier contains only the call to its respective dependency:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductSummaryService {
    private final InventoryClient inventoryClient;
    private final PricingClient pricingClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductSummaryService(
            InventoryClient inventoryClient,
            PricingClient pricingClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryClient = inventoryClient;
        this.pricingClient = pricingClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductSummary load(String sku) {
        InventoryView inventory = circuitBreakerFactory
            .create("inventory")
            .run(
                () -> InventoryView.current(inventoryClient.find(sku)),
                error -> InventoryView.unavailable()
            );

        PricingView pricing = circuitBreakerFactory
            .create("pricing")
            .run(
                () -> PricingView.current(pricingClient.quote(sku)),
                error -> PricingView.unavailable()
            );

        return new ProductSummary(sku, inventory, pricing);
    }
}
```

`create("inventory")` selects the inventory breaker and Bulkhead instance; `create("pricing")` selects the pricing instance. The same business request can receive current inventory data alongside a temporarily unavailable pricing state, or vice versa. `ProductSummary` must explicitly expose each part's status so clients do not mistake fallback data for current data.

`InventoryResponse`, `PricingResponse`, `InventoryView`, `PricingView`, and `ProductSummary` are application domain types. You can use a status enum like `CURRENT`, `UNAVAILABLE`, or `UNKNOWN` instead of substituting quantity 0 or price 0 when data cannot be fetched. Semantically misleading defaults can cause incorrect purchasing or checkout decisions.

## 5. Why Must the Two IDs Be Independent?

Consider two scenarios:

**Scenario A — inventory fails, pricing is healthy:** inventory times out repeatedly and the `inventory` breaker transitions to `OPEN`. New calls to inventory are rejected and the inventory fallback returns an unavailable status. The `pricing` breaker remains `CLOSED`, so prices can still be fetched normally.

**Scenario B — pricing is overloaded:** the pricing pool exhausts its workers and queue. New pricing calls are rejected because its Bulkhead is full. Inventory still has its own pool and continues serving. When pricing recovers, queued tasks drain or new calls are accepted according to pricing's capacity.

If they shared an ID and a pool, errors or load spikes in one dependency could impact the other. Separating Circuit Breaker and Bulkhead IDs isolates both failure state and execution resources.

## 6. Distinguishing Bulkhead Errors from Circuit Breaker Errors

Two common rejection types have different meanings:

| Error | Meaning | What to investigate |
| --- | --- | --- |
| `BulkheadFullException` | The dependency's pool or queue is out of capacity for new tasks. | Workers, queue capacity, worker hold time, latency, and traffic volume. |
| `CallNotPermittedException` | The Circuit Breaker is `OPEN` and rejecting new calls. | Failure rate, slow-call rate, sliding window, and open duration. |

Do not automatically treat `BulkheadFullException` as proof that the remote dependency failed. The task may have been rejected before being sent to the server because the calling application ran out of local capacity. If a Circuit Breaker predicate records Bulkhead rejections as dependency failures, the breaker may open due to local overload. Verify decorator ordering and the behavior of the provider in use; track Bulkhead rejections and Circuit Breaker rejections with separate metrics.

If the provider auto-configures Bulkhead, verify the exact ID and Bulkhead type used by the factory. Do not assume `resilience4j.bulkhead` controls `ThreadPoolBulkhead`; `SemaphoreBulkhead` and `ThreadPoolBulkhead` use separate configuration namespaces.

## 7. Independent Fallbacks Without Cascading Failures

Each dependency needs a semantically appropriate fallback. Inventory can return `InventoryView.unavailable()`; pricing can return `PricingView.unavailable()`. Never use a shared fallback that fabricates valid-looking objects for both.

Fallbacks should be fast and have minimal dependencies. If the inventory fallback calls pricing or another overloaded service, it can trigger a cascading failure chain. If using a cache, check freshness and mark stale data clearly. For critical data such as transaction prices, never use an expired cache entry as the final confirmed price.

In the `run` example, the fallback is invoked when the supplier fails or the Circuit Breaker rejects the call per the provider contract. Also verify how Bulkhead rejections are routed to the fallback in the version in use. If you want a distinct response for local overload, you can handle `BulkheadFullException` at the API layer or use an appropriate fallback; avoid masking the cause with a fake success result.

## 8. Timeouts per Dependency

A Bulkhead limits concurrency and queuing, but it does not terminate a hung HTTP request. Each client needs timeouts aligned with its dependency's SLA:

- Inventory might use a 300 ms connect timeout and a 1.5-second response timeout.
- Pricing might use a 300 ms connect timeout and a 1-second response timeout if business requirements demand faster responses.

The values above are examples only. Configure them on the HTTP client in use and set an overall deadline for the business request. For blocking calls, do not assume `TimeLimiter` can always interrupt a blocking synchronous supplier. Interrupting a thread does not guarantee the network library or remote server stopped processing the request.

When a worker is held too long, that dependency's pool can fill up even if the server is only temporarily slow. Reasonable timeouts free workers sooner. For write operations, a timeout does not prove the server did not execute the operation; require an idempotency key or duplicate-prevention mechanism before retrying.

## 9. Calculating Capacity Across Replicas

`ThreadPoolBulkhead` is created per process. If one instance has at most 8 inventory workers and the application runs 5 replicas, total inventory workers can reach 40. Pricing has at most 4 workers per replica, totaling 20 workers across 5 replicas.

| Dependency | Max workers per replica | Queue per replica | Across 5 replicas: max workers | Across 5 replicas: max queue |
| --- | ---: | ---: | ---: | ---: |
| Inventory | 8 | 16 | 40 | 80 |
| Pricing | 4 | 8 | 20 | 40 |

These are theoretical limits from this service alone; other applications and callers also consume backend capacity. Coordinate per-instance limits with system-wide quotas, connection pools, and dependency capacity. A large queue does not make a backend healthier; it only holds more waiting tasks and can push latency past deadlines.

## 10. Testing Isolation Between Two Dependencies

Create two mock servers or controllable mock clients that can be controlled independently. One test should verify that inventory failures do not block pricing:

1. Configure the mock inventory server to return timeouts or 503 enough times to open the inventory breaker.
2. Call `ProductSummaryService.load(sku)`.
3. Verify inventory returns its fallback state.
4. Verify pricing is still invoked and returns the current price.
5. Check that the `inventory` breaker is `OPEN` while the `pricing` breaker still permits calls.

Another test verifies Bulkhead isolation:

1. Hold inventory calls inside the supplier with a latch to occupy workers and fill the inventory queue.
2. Send another inventory call and verify it is rejected once both pool and queue are full.
3. While inventory is full, call pricing and verify pricing still executes on its own pool.
4. Release the latch and verify inventory workers and queue drain.
5. Send a new inventory call and verify the pool accepts work again.

When testing concurrency, use `CountDownLatch` or `CyclicBarrier` to know precisely when suppliers have started. Avoid using `Thread.sleep()` as a synchronization condition because thread ordering depends on the OS scheduler. Always release latches and shut down resources in `finally` blocks so a failed test does not leave hanging threads.

### Observations to Verify

| Check | Expected outcome |
| --- | --- |
| Inventory fails continuously | Only the `inventory` breaker transitions to `OPEN`. |
| Pricing remains healthy | The `pricing` breaker continues allowing calls. |
| Inventory pool full | New inventory calls are rejected; pricing is unaffected. |
| Pricing pool full | New pricing calls are rejected; inventory is unaffected. |
| Suppliers complete | Workers are returned and the queue continues draining. |
| Circuit Breaker `HALF_OPEN` | Probe count does not exceed `permittedNumberOfCallsInHalfOpenState` for that ID. |
| Fallback invoked | Result accurately reflects which dependency is unavailable or overloaded. |

## 11. Separating Metrics and Logs by Dependency

Track metrics by breaker ID and Bulkhead ID to pinpoint where issues occur:

- Circuit Breaker state: `CLOSED`, `OPEN`, `HALF_OPEN`.
- Failure rate, slow-call rate, successful/failed call counts, and rejected call count.
- ThreadPoolBulkhead: active worker count, queued task count, rejected task count.
- Latency and timeouts per HTTP client.
- Fallback invocation count and fallback result status.

Use bounded tags such as `dependency=inventory` or `dependency=pricing`. Do not include SKUs, user IDs, request IDs, or exception messages in metric tags because cardinality will explode. Logs can include correlation IDs to trace specific requests without logging tokens or sensitive data.

When dashboards alert, distinguish these cases:

- `inventory` has high failure rate and is `OPEN`: the inventory dependency may be degrading.
- `inventory` has a full queue but low failure rate: the application is receiving load beyond capacity or workers are held too long; the backend may not be failing.
- `pricing` stays `CLOSED` with a shallow queue: pricing is operating independently despite the inventory incident.
- Both are full: examine overall load, connection pools, CPU, and shared downstream dependencies.

## 12. Common Configuration Mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Sharing one Circuit Breaker ID for inventory and pricing | Failures in one dependency can open the other dependency's breaker. | Separate IDs by failure domain. |
| Sharing one Bulkhead for both dependencies | Inventory load can exhaust pricing's workers and queue. | Configure separate Bulkheads per ID. |
| Configuring SemaphoreBulkhead while expecting thread isolation | Blocking calls still run on the caller thread. | Use ThreadPoolBulkhead when a separate pool is needed, or understand semaphore limits. |
| Queue too large | Requests wait too long, heap grows, and deadlines are missed. | Set finite queues aligned with target latency. |
| Missing HTTP timeouts | Workers are held too long and pools fill rapidly. | Configure connect/read timeouts on the client. |
| Recording Bulkhead rejections as dependency errors | Circuit Breaker may open due to local overload. | Classify `BulkheadFullException` separately and verify decorator order. |
| Fallback returns misleading default values | Callers may treat unknown data as real values. | Use explicit unavailable/unknown states. |
| Sizing capacity for a single replica only | Cluster-wide concurrency exceeds backend capacity. | Multiply limits by replica count and other callers. |

## Completion Exercise

Implement both dependencies `inventory` and `pricing` within the same service, with separate Circuit Breaker and Bulkhead IDs. Then prove through tests that:

- Inventory opening its circuit does not open pricing's circuit.
- A full inventory queue does not cause pricing calls to be rejected.
- A full pricing queue does not cause inventory calls to be rejected.
- Each dependency's fallback returns a semantically accurate state.
- Timeouts release workers within the expected window.
- Metrics distinguish dependency errors, open breakers, and full bulkheads.

If the project chooses `SemaphoreBulkhead` instead of `ThreadPoolBulkhead`, document the reason and confirm that blocking calls still consume caller threads. If the project uses reactive `WebClient`, keep the pipeline reactive and select a Bulkhead suited to publishers; never block the event loop waiting for permits or blocking results.

When two dependencies are bound to separate Circuit Breaker and Bulkhead IDs, the system isolates both failure state and execution resources. This prevents one degraded service from dragging the other into the same outage, while making metrics, fallbacks, and capacity limits clear in Spring Cloud Circuit Breaker operations.
