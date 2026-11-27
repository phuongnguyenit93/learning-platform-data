# Creating Circuit Breakers with Stable IDs

In Spring Cloud CircuitBreaker, an application creates a circuit breaker through a factory and passes in an identifier, typically the name of the dependent service or service call operation. For example, when the order service calls the inventory service to read product quantities, the application can use the ID `inventory-read`.

A stable ID ensures the application always accesses the same circuit breaker for the same call flow. This ID also serves as the link between source code, Resilience4j configuration, and monitoring metrics. When names vary per request, the application can create many circuit breakers with fragmented state and metrics, making configuration hard to apply and observability unreliable.

## What Is a Circuit Breaker ID Used For?

Spring Cloud CircuitBreaker provides `CircuitBreakerFactory` to create a circuit breaker by name:

~~~java
CircuitBreaker circuitBreaker = circuitBreakerFactory.create("inventory-read");
~~~

With the Resilience4j backend, the ID is used to identify the circuit breaker instance. This ID is matched against the instance name in configuration and also appears in monitoring metrics as an identifying tag. Therefore, the same call flow must use the same ID across executions.

A stable ID serves three roles:

- **Call flow identification:** indicates which dependency or business operation the circuit breaker is protecting.
- **Configuration binding:** ensures the instance receives the exact thresholds and durations declared in `application.yml`.
- **Operational tracking:** enables development and operations teams to filter metrics by a consistent name across runs and application replicas.

An ID does not represent a specific HTTP request, a user, or an order. It represents a category of calls that the application wants to protect with the same circuit breaker policy.

## Choosing the Scope of an ID

Choose an ID based on the failure characteristics and recovery policy of the call. If two operations share the same dependency, latency profile, and fallback behavior, they can share a circuit breaker. If a read operation and a write operation have different criticality, thresholds, or recovery strategies, separate them into two IDs.

For example, in an ordering system:

| Stable ID | Protected flow | Reason |
|---|---|---|
| inventory-read | Reading inventory information | Can serve the latest cached data if business rules allow. |
| inventory-reserve | Reserving inventory quantity | Must accurately reflect write outcomes and must not assume the operation succeeded. |
| payment-authorize | Requesting payment gateway authorization | Has its own timeout, failure, and indeterminate-outcome handling policy. |

If a single ID is shared across flows with different behaviors, the outcome of one flow can trip the circuit breaker and affect the other. For instance, errors from inventory reservation could disrupt inventory reads even when reads are operating normally.

Conversely, do not split IDs simply because each URL has a different parameter value. If endpoints share the same operational characteristics and protection policy, creating a separate ID per URL can fragment metrics and leave each circuit breaker with too few samples to evaluate.

## Stable Naming Conventions

A useful convention is to combine the dependent service name with the business operation, in lowercase and separated by hyphens:

- Readable and clearly describes the protection target.
- Contains no per-request dynamic data.
- Remains unchanged across restarts and replicas of the same application.
- Matches the instance name in configuration exactly when using Resilience4j.

You can centralize these names in a constants class:

~~~java
public final class CircuitBreakerIds {

    public static final String INVENTORY_READ = "inventory-read";
    public static final String INVENTORY_RESERVE = "inventory-reserve";
    public static final String PAYMENT_AUTHORIZE = "payment-authorize";

    private CircuitBreakerIds() {
    }
}
~~~

A constants class helps avoid typos and makes it clear which call flows are protected. When renaming an ID, update all usage sites and the corresponding instance configuration in sync.

Do not include the following values in an ID:

| Avoid using | Example | Problem |
|---|---|---|
| Order ID | order-93821 | Each order creates a new name and fragments state. |
| User ID | customer-1042 | Causes instance count and metric labels to grow with users. |
| Random UUID | 9c1... | Cannot be stably mapped to configuration or metrics across runs. |
| URL parameter | inventory-sku-ABC | Number of IDs grows with input data. |
| Timestamped name | inventory-2026-11-24T10:00 | Each time window produces a different identifier. |

If an ID changes per request, the registry can accumulate many instances and the metrics system can suffer high cardinality. Each instance also receives only a fraction of the traffic, starving the sliding window of samples and preventing failure or slow-call thresholds from accurately reflecting dependency health.

## Creating and Using a Circuit Breaker in Synchronous Calls

The following example protects an inventory read operation. The circuit breaker is created from the factory with a fixed ID and stored in the client so all calls share the same identifier.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient restClient;
    private final CircuitBreaker inventoryReadBreaker;

    public InventoryClient(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryReadBreaker =
                circuitBreakerFactory.create(CircuitBreakerIds.INVENTORY_READ);
    }

    public Inventory findInventory(String sku) {
        return inventoryReadBreaker.run(
                () -> restClient.get()
                        .uri("/inventory/{sku}", sku)
                        .retrieve()
                        .body(Inventory.class),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

`Inventory`, `Inventory.unavailable`, and `CircuitBreakerIds` are illustrative application types. In a real project, replace them with your project's data models and constants class.

Every time `findInventory` is called, the same `inventory-read` circuit breaker records the outcome of the call. When the circuit is `CLOSED`, the call is forwarded to the inventory service. If the failure rate or slow-call rate exceeds the threshold, the circuit can transition to `OPEN`. Subsequent calls are rejected fast and the fallback function can return degraded data.

The fallback must reflect the proper business semantics. If cached data is acceptable for a reference view, the application can return the most recent data and mark it as stale. If the operation requires exact inventory quantities to confirm an order, it must not assume inventory is still available when the service does not respond.

## Matching IDs with Resilience4j Configuration

When using Spring Cloud CircuitBreaker with Resilience4j, the instance name in `application.yml` must match the ID passed to the factory. For example, if code calls `create("inventory-read")`, the corresponding configuration goes under `instances.inventory-read`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
      inventory-reserve:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

In this example, `inventory-read` and `inventory-reserve` have separate policies. The reservation operation may need more conservative thresholds because it directly affects business data. The numbers only illustrate how configuration is bound by ID; tune them according to the latency, traffic, and requirements of each system.

If the ID in source code does not match the configured instance name, the circuit breaker may use the default configuration instead of the thresholds the development team expects. When renaming an ID, find and update the constant, factory call sites, configuration, and any dashboard queries or alerts filtering by the old name.

## Using Stable IDs in Reactive Calls

With WebClient and Reactor, use `ReactiveCircuitBreakerFactory` to create a reactive circuit breaker. The ID remains a stable name for the call flow; do not put SKU or order IDs into the circuit breaker name.

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class ReactiveInventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryReadBreaker;

    public ReactiveInventoryClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryReadBreaker =
                circuitBreakerFactory.create(CircuitBreakerIds.INVENTORY_READ);
    }

    public Mono<Inventory> findInventory(String sku) {
        Mono<Inventory> request = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return inventoryReadBreaker.run(
                request,
                error -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

The reactive chain continues returning a `Mono` without calling `block` to wait for the result. Creating the circuit breaker with a fixed ID routes all requests through the same protection policy. If a reactive operation has different operational characteristics from a synchronous one, consider using a separate ID to isolate policies and metrics; if they truly represent the same logical flow, sharing an ID can be done intentionally.

## Stable IDs and Monitoring Metrics

The ID is typically used as the identifying label for the circuit breaker in Resilience4j and Micrometer metrics. Thanks to a stable name, operations teams can compare the state and failure rate of the same call flow across time ranges.

When monitoring, observe:

- `CLOSED`, `OPEN`, and `HALF_OPEN` states per ID.
- Counts of successful, failed, slow, and rejected calls.
- Failure rate, slow-call rate, and latency.
- Number of fallback invocations.
- Number of circuit breaker state transitions.

Consistent ID names allow dashboards and alerts to group metrics by business operation. Avoid adding user IDs, order IDs, or input values to ID names, because doing so increases label series count and makes metrics hard to aggregate.

It is also important to understand state scope. A stable ID ensures calls within the same application process use the right instance by name. It does not automatically create a distributed circuit breaker sharing state across all servers. When an application runs multiple replicas, each replica normally tracks circuit breaker state within its own process; sharing the same ID across replicas keeps configuration and metric interpretation consistent, but does not mean an `OPEN` state on one replica automatically opens the circuit on another.

## Common Mistakes When Choosing IDs

| Mistake | Consequence | Fix |
|---|---|---|
| Generating IDs from request data | Many instances, under-sampled windows, and high metric cardinality. | Use constants scoped to a service or business operation. |
| Source code and YAML using different names | Instance-specific configuration is not applied as expected. | Use a single constants source in code and verify configuration names. |
| Using one ID for operations with different policies | Failures in one operation can open the circuit and impact the other. | Split IDs when failure, timeout, or fallback characteristics differ. |
| Splitting IDs for every endpoint despite identical policies | Traffic and outcomes are fragmented, making it hard to gather enough samples. | Group calls that share the same protection characteristics. |
| Renaming an ID but forgetting dashboards or alerts | Charts and alerts keep querying the old name. | Update monitoring configurations alongside the rename. |
| Assuming identical IDs share state across replicas | Incorrect expectations when deploying multiple instances. | Monitor state per replica and design alerts accordingly. |

## Pre-Production Design Checklist

Before deploying, review each ID against these questions:

1. Does the ID clearly describe the dependent service and the protected operation?
2. Does the ID remain unchanged across requests, restarts, and replicas?
3. Does the ID match the instance name in the Resilience4j configuration exactly?
4. Do calls sharing the same ID truly share the same failure, timeout, and fallback characteristics?
5. Could any user ID, order ID, UUID, or URL parameter leak into the ID?
6. Can dashboards and alerts identify the circuit breaker by this name?

You can verify behavior by generating load on a call flow, simulating failures or latency from the dependent service, and observing the expected ID transition states. Then send requests with various SKUs or order IDs and confirm they are still recorded under the same stable ID. If the number of IDs grows with request data, fix the naming strategy before wide deployment.

A stable ID is the foundation for circuit breaker configuration, state, and metrics to describe a single call flow consistently. Name IDs after the dependency and business operation, use them consistently in the factory and `application.yml`, and only split IDs when there is a clear operational reason. Doing so ensures Spring Cloud CircuitBreaker protects the right scope and helps operations teams read clear signals when a dependent service runs into trouble.
