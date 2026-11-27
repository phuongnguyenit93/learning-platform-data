# Do Not Share One ID Across Independent Systems

In Spring Cloud CircuitBreaker, the ID identifies which Circuit Breaker a call will use. The ID is typically bound to the breaker's state, configuration, events, and metrics. If multiple independent systems share one ID, they can end up sharing the same protection boundary. When one dependency experiences an incident, its failures can open the breaker and block calls to another dependency that is still healthy.

For example, a service calls both Inventory and Payment. If both calls create a Circuit Breaker with the ID **remote-service**, payment failures can cause the breaker to open. Subsequent inventory calls are then rejected even though the inventory service is operating normally. This is a boundary design flaw: dependencies with different failure domains are sharing a single unit of state.

Choose a stable ID per dependency or per group of operations that truly share the same operational characteristics. Inventory and Payment need separate IDs. Endpoints of the same dependency should only share an ID when they share reliability requirements, failure thresholds, timeouts, and recovery behavior.

## 1. The ID defines the Circuit Breaker boundary

When creating a breaker through Spring Cloud CircuitBreaker, the application passes an ID to the factory:

~~~java
CircuitBreaker inventoryBreaker =
        circuitBreakerFactory.create("inventory");
~~~

The **inventory** ID tells the factory which breaker to create or retrieve according to the implementation in use. With a registry-based implementation such as Resilience4j, the ID is used to look up the instance in the registry. Calls using the same ID pass through the breaker state managed for that ID.

A Circuit Breaker maintains its own state:

- CLOSED: allows calls and records outcomes.
- OPEN: rejects new calls for the duration of the open state.
- HALF_OPEN: permits a limited number of probe calls to test recovery.

A breaker also has its own configuration such as sliding window, failure threshold, slow-call threshold, and OPEN duration. Metrics and events are typically tagged with the instance name so operations teams know which breaker is having issues.

Therefore, the ID is part of the operational boundary. Assigning the same ID to two independent dependencies mixes their state and statistics. Assigning separate IDs ensures each dependency is evaluated based on its own outcomes.

The exact instance management and caching mechanism depends on the Spring Cloud CircuitBreaker implementation. However, when using Resilience4j, do not treat the ID as just a display label: the registry uses the ID to manage the Circuit Breaker instance.

## 2. Failure in one dependency can block another dependency

Suppose Order Service calls two systems:

- Inventory Service to check stock quantities.
- Payment Service to process payments.

The two systems have different latencies, failure rates, load limits, and recovery schedules. If both use the **external** ID, outcomes from both calls affect the same breaker.

~~~mermaid
flowchart TD
    A[Order Service] --> B[Circuit Breaker ID: external]
    B --> C[Inventory Service]
    B --> D[Payment Service]
    D --> E[Payment fails continuously]
    E --> F[Breaker external transitions to OPEN]
    F --> G[Inventory is also rejected]
~~~

In this situation, Inventory can be blocked even though there have been no errors from Inventory. Order Service loses the ability to check stock simply because Payment is having an incident.

This is a cascading effect caused by misconfigured boundaries. A Circuit Breaker is meant to limit the impact of dependency failures, but an inappropriate shared ID can turn a localized failure into a multi-dependency outage.

A better structure:

~~~mermaid
flowchart TD
    A[Order Service] --> B[Circuit Breaker: inventory]
    A --> C[Circuit Breaker: payment]
    B --> D[Inventory Service]
    C --> E[Payment Service]
    E --> F[Payment breaker OPEN]
    B --> G[Inventory continues to be evaluated independently]
~~~

When Payment fails, only the **payment** breaker transitions to OPEN. The **inventory** breaker continues evaluating stock calls and can remain CLOSED.

## 3. Using separate IDs in code

Example creating two independent breakers in a service:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderDependencyService {

    private final CircuitBreaker inventoryBreaker;
    private final CircuitBreaker paymentBreaker;

    private final InventoryClient inventoryClient;
    private final PaymentClient paymentClient;

    public OrderDependencyService(
            CircuitBreakerFactory<?, ?> factory,
            InventoryClient inventoryClient,
            PaymentClient paymentClient) {

        this.inventoryBreaker = factory.create("inventory");
        this.paymentBreaker = factory.create("payment");

        this.inventoryClient = inventoryClient;
        this.paymentClient = paymentClient;
    }

    public Inventory checkInventory(String sku) {
        return inventoryBreaker.run(
                () -> inventoryClient.check(sku),
                error -> Inventory.unavailable(sku)
        );
    }

    public PaymentResult charge(PaymentRequest request) {
        return paymentBreaker.run(
                () -> paymentClient.charge(request),
                error -> PaymentResult.temporarilyUnavailable()
        );
    }
}
~~~

The two calls use different IDs. Failures in **payment** do not alter the state of **inventory**. Each breaker can have its own configuration and fallback appropriate for its business logic.

The classes InventoryClient, PaymentClient, Inventory, PaymentRequest, and PaymentResult are illustrative application types. In a real project, replace them with your existing interfaces and models.

Do not create a new breaker on every call using a random ID. IDs should be stable so requests to the same dependency share the same protection policy and metrics.

## 4. Aligning IDs with Resilience4j configuration

When using Resilience4j, the ID name in code must match the instance name in **application.yml**.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 15
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

The configuration shows that the two dependencies have different policies:

| Property | inventory | payment |
|---|---:|---:|
| Window type | COUNT_BASED | TIME_BASED |
| Window size | 30 calls | 15 seconds |
| Minimum samples | 10 | 20 |
| Failure threshold | 50% | 30% |
| Slow-call threshold | 1 second | 2 seconds |
| OPEN duration | 10 seconds | 30 seconds |
| HALF_OPEN probe calls | 3 | 2 |

These numbers are only meant to illustrate separating policies. Choose values based on the actual SLA, traffic, latency, and recovery characteristics of each dependency.

If the code calls factory.create("payment") while YAML only declares instances.billing, the billing configuration will not automatically apply to the payment ID. Keep ID names consistent across breaker creation sites, configuration, and dashboards.

## 5. Using separate IDs for reactive Circuit Breakers

With WebFlux and Reactor, IDs must also be separated by dependency. ReactiveCircuitBreakerFactory creates reactive breakers by ID:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderDependencyService {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;
    private final ReactiveCircuitBreaker paymentBreaker;

    public ReactiveOrderDependencyService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.inventoryBreaker = factory.create("inventory");
        this.paymentBreaker = factory.create("payment");
    }

    public Mono<Inventory> checkInventory(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("http://inventory-service/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return inventoryBreaker.run(
                remoteCall,
                error -> Mono.just(Inventory.unavailable(sku))
        );
    }

    public Mono<PaymentResult> charge(PaymentRequest request) {
        Mono<PaymentResult> remoteCall = webClient.post()
                .uri("http://payment-service/charges")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResult.class);

        return paymentBreaker.run(
                remoteCall,
                error -> Mono.just(
                        PaymentResult.temporarilyUnavailable())
        );
    }
}
~~~

Each publisher passes through the breaker for its corresponding dependency. The fallbacks for Inventory and Payment are also defined separately to accurately reflect business semantics.

Do not use a single ReactiveCircuitBreaker named **remote** for every publisher just because they are all called via WebClient. WebClient is an HTTP client tool; it does not determine whether two remote services share the same failure domain.

For Flux, the same ID selection principle applies. Create a separate breaker for each dependency or group of operations with the same policy, and pass the corresponding Flux to run.

## 6. When can multiple endpoints share an ID?

Having two URLs does not automatically require two Circuit Breakers. Boundaries should reflect failure domains and operational policies, not merely the number of endpoints.

An ID can be shared when endpoints:

- Belong to the same dependency and typically degrade together.
- Have similar SLAs, timeouts, and failure thresholds.
- Share the same error classification policy.
- Need to be protected as a single shared load unit.
- Opening the circuit for the entire endpoint group is the desired behavior.

For example, **/inventory/{sku}** and **/inventory/{sku}/availability** can share the **inventory** breaker if they both depend on the same Inventory Service and belong to the same failure domain.

Separate IDs should be used when:

- Endpoints call independent backends.
- One operation is slow while the other continues operating properly.
- SLAs or deadlines differ noticeably.
- One operation has high traffic that could overwhelm the statistics of another operation.
- Exception classification or fallback policies differ.
- You need to open the circuit for one flow while still allowing another flow to continue.

For example, a Customer system has a profile-reading API and a report-generation API. If the report API runs long queries, its errors or latency may not represent the profile-reading API. You can use **customer-profile** and **customer-report** to separate the two boundaries.

| Scenario | How to choose IDs |
|---|---|
| Multiple endpoints on the same backend, same SLA and failure domain | Can share one ID |
| Two independent backends such as Inventory and Payment | Use two separate IDs |
| One backend with a fast read flow and a long report flow, different policies | Consider splitting by operation |
| Same backend, but one API has dominant traffic and needs separate protection | Consider a separate ID |
| Creating a dynamic ID per tenant or per request | Avoid; typically causes excessive cardinality and state |

## 7. Avoiding dynamic IDs and high cardinality

IDs should be stable and finite in number. Do not use user ID, request ID, order ID, or tenant ID as a Circuit Breaker ID if each value creates a separate instance.

Example of what not to do:

~~~java
String breakerId = "inventory-" + tenantId;
CircuitBreaker breaker = factory.create(breakerId);
~~~

If the system has tens of thousands of tenants, this approach can create tens of thousands of breaker instances. Each instance has its own state, configuration, statistics window, and metrics. Consequences can include:

- Increased memory usage and object count in the registry.
- Increased number of time series in the metrics system.
- Each breaker receiving too few requests to reach minimumNumberOfCalls.
- Difficulty observing and managing the state of individual instances.
- Difficulty modifying or cleaning up dynamic instances.

If per-tenant limits are needed, use a Rate Limiter or a quota mechanism suited for tenants, while keeping the Circuit Breaker at finite dependency boundaries. If there is a group of backends per region or cluster, you can use an ID per backend group when they genuinely share a failure domain.

ID names should be readable and stable, for example:

- inventory
- payment
- customer-profile
- customer-report
- shipping-provider-a

Do not include dynamic hostnames, full URLs, or user data in the ID.

## 8. Shared configuration does not mean shared state

Resilience4j lets you define shared configuration profiles under **configs** and have multiple instances reference them via **baseConfig**. Reusing configuration does not mean instances must share an ID.

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      standard:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

    instances:
      inventory:
        baseConfig: standard

      customer:
        baseConfig: standard

      payment:
        baseConfig: standard
        failureRateThreshold: 30
~~~

**inventory** and **customer** inherit the same **standard** configuration, yet remain two separate instances with separate IDs and states. Payment also inherits the shared configuration and then overrides its own failure threshold.

This is an appropriate way to organize configuration when you want to standardize policies while preserving independent boundaries. There is no need to duplicate all properties for every instance, nor is there a need to use a shared ID just to reuse configuration.

If a group of dependencies genuinely needs a shared Circuit Breaker state, explicitly identify it as an intentional shared failure domain. Never share an ID solely to reduce lines of YAML.

## 9. Circuit Breaker state is typically local to each application instance

Another important point: having the same ID in two processes or two pods does not by default create a distributed Circuit Breaker with shared state.

In a typical Resilience4j deployment, the registry and breaker state are managed in the memory of each application instance. For example, two Order Service pods both creating the **inventory** ID will each have their own **inventory** breaker inside each pod. One pod may be OPEN while the other remains CLOSED, depending on the call outcomes observed by each pod.

~~~mermaid
flowchart TD
    A[Order Service] --> B[Pod 1]
    A --> C[Pod 2]
    B --> D[Breaker inventory: OPEN]
    C --> E[Breaker inventory: CLOSED]
    D --> F[Pod 1 rejects calls]
    E --> G[Pod 2 still calls Inventory]
~~~

This is not a reason to assign different IDs per pod. Pods of the same service should use the same ID convention for consistent configuration and metrics. However, identical IDs should not be mistaken for a state synchronization mechanism across pods.

If business requirements demand a distributed protection decision or cluster-wide shared quota, a separate coordination mechanism is required. Local Circuit Breakers primarily protect resources and call flows within each process.

## 10. Monitoring metrics by ID

Circuit Breaker metrics are usually tagged with the instance name. When each dependency has a separate ID, dashboards can distinguish:

- The current state of each breaker.
- The number of successful, failed, and rejected calls.
- Failure rate and slow-call rate.
- Transition counts for CLOSED, OPEN, and HALF_OPEN.
- Fallback rate per dependency.

If multiple dependencies share an ID, metrics can no longer pinpoint which dependency is generating errors. For example, a dashboard only shows **remote-service** with a 60% failure rate; operations teams cannot tell whether errors come from Payment or Inventory if both wrote to the same breaker.

ID names should be used consistently across logs, metrics, and configuration. Do not use dynamic high-cardinality IDs as labels. You can combine IDs with routes or operations in logs/tracing, but keep the metric label set bounded.

## 11. Testing independence between IDs

A useful test is to make one dependency fail long enough for its breaker to open, then verify that the other dependency still works.

Illustrative scenario:

1. Create two breakers **inventory** and **payment**.
2. Configure thresholds small enough in the test environment to easily observe state transitions.
3. Make Payment Service return errors continuously.
4. Call Payment through the **payment** breaker until the circuit is OPEN.
5. Verify subsequent Payment calls are rejected without making HTTP calls to Payment.
6. Call Inventory through the **inventory** breaker.
7. Verify Inventory is still allowed to be called and its breaker remains CLOSED if calls succeed.
8. Check metrics and events under their separate instance names.
9. Wait for the OPEN duration and verify Payment's HALF_OPEN transition independently of Inventory.

Expected results table:

| Check | Breaker payment | Breaker inventory |
|---|---|---|
| Dependency forced to fail | Yes | No |
| Failure rate increases | Yes | No |
| Transitions to OPEN | Possible | No |
| New calls rejected | Yes | No, if Inventory is healthy |
| Separate metrics | Yes | Yes |

If both breakers transition to OPEN when only Payment fails, check whether the code accidentally used the same ID, shared the same breaker object, or wrapped both calls inside a single outer breaker.

## 12. Common design mistakes

- **Using a single remote ID for all dependencies**: state and metrics get mixed, causing failures in one system to block another.
- **Using the same ID with different configurations per call**: the same registry instance cannot simultaneously represent two independent policies.
- **Using an ID per request**: creates too many instances and high metric cardinality.
- **Splitting IDs just because there are multiple URLs**: can create too many breakers even when endpoints share a failure domain and policy.
- **Merging IDs for operations with different SLAs**: errors or latency in one operation can affect another operation.
- **Sharing an inappropriate fallback**: one dependency may need a cache, while another needs to return a temporary error.
- **Mismatching IDs between code and YAML**: the intended configuration is not applied to the created instance.
- **Confusing configs with instances**: sharing baseConfig only reuses configuration values, not instance state.
- **Assuming identical IDs across pods share state**: local registries do not automatically synchronize state across processes.
- **Failing to test fault isolation**: only testing successful calls does not catch boundary bugs.

## 13. Process for choosing IDs by failure domain

When designing Circuit Breaker IDs for Spring Cloud CircuitBreaker, you can follow this sequence:

1. List all dependencies that the service calls.
2. Identify failure domains: which systems can degrade independently of which systems.
3. Compare SLA, latency, traffic, timeout, and error classification for each dependency.
4. Use separate IDs when dependencies have independent failure probabilities or protection policies.
5. Only share an ID among endpoints that genuinely need the same protection state.
6. Keep IDs stable, finite in number, and clearly associated with dependency names.
7. Align IDs across factory.create, Resilience4j configuration, and dashboards.
8. Use baseConfig to reuse common properties while keeping instances separate.
9. Test when one dependency fails to verify that other dependencies' breakers are unaffected.
10. Monitor state, failure rate, fallback, and metrics separately for each ID.

A Circuit Breaker ID represents a protection boundary. When two independent dependencies share an ID, their errors and states get mixed together, destroying fault isolation. Assigning separate IDs by failure domain gives each dependency appropriate state, configuration, and metrics. For dependencies with similar characteristics, configuration can be reused via **baseConfig** while keeping instances independent. Choosing stable IDs, limiting cardinality, and testing single-dependency failure scenarios ensures Circuit Breaker boundaries accurately reflect the system architecture.
