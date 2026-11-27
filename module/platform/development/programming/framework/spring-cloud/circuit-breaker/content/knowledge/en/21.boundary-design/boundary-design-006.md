# Relationship with Service Discovery, Load Balancing, and Failing Instances

## Lesson objectives

In a multi-instance system, a call to inventory-service typically does not go to a fixed host. Service Discovery provides the list of instances, Spring Cloud LoadBalancer selects one instance per call, and the circuit breaker decides whether to permit the logical call based on recent outcomes.

When an instance fails, these three mechanisms may react at different times. The registry may not have evicted the instance yet; the LoadBalancer may still select it; the circuit breaker may record the error after the request fails. Without distinguishing the scope of each mechanism, development teams easily open the breaker for the entire service just because of one failing instance, or expect the LoadBalancer to automatically evict an instance immediately after a single 5xx response.

After this lesson, you will be able to:

- Describe a request's path from the client through Service Discovery, LoadBalancer, and the circuit breaker to the selected instance.
- Distinguish an instance's registration/health status from the outcome of a remote call.
- Understand per-service or per-operation breaker scope and the limitations of per-instance breakers.
- Choose how to handle a single failing instance, multiple failing instances, or when the registry has no available instances.
- Combine health checks, retries, timeouts, circuit breakers, and fallbacks without creating load loops.
- Design logs, metrics, and tests to accurately identify the failing instance.

## 1. Three mechanisms participate in one call

Suppose order-service needs to read inventory from inventory-service. In the deployment environment, inventory-service has three instances. The application calls it by service ID instead of a specific IP address.

The logical flow can be visualized as:

    order-service
        |
        v
    InventoryGateway / Feign client
        |
        v
    CircuitBreaker: inventory-read
        |
        v
    Spring Cloud LoadBalancer
        |
        v
    ServiceInstanceListSupplier
        |
        +---- select instance A ----> inventory-service A
        |
        +---- select instance B ----> inventory-service B
        |
        +---- select instance C ----> inventory-service C

Each component has its own responsibility:

| Component | Question it answers | Example |
| --- | --- | --- |
| Service Discovery | Which instances are registered for this service ID? | Registry returns A, B, and C. |
| Health check / readiness | Which instances are considered eligible to receive traffic? | Instance B is not ready yet, so it is excluded from the eligible list. |
| LoadBalancer | Among the selectable instances, where does this request go? | Selects A based on the algorithm and current state. |
| CircuitBreaker | Should a new logical call to the dependency be permitted? | Rejects calls fast while the inventory-read breaker is OPEN. |
| Retry | When an attempt fails, should it be retried and target another instance? | Retries at most one other instance within the request budget. |

Discovery and health checks manage whether an instance can be selected. LoadBalancer picks the target for a request. The circuit breaker protects the logical call before or around the call execution depending on the integration. Retry decides whether to make an additional attempt. No single mechanism automatically replaces all the others.

## 2. Service Discovery knows instances via registration and status

An instance normally registers its address, port, service ID, and metadata with the registry at startup. The registry or orchestration platform updates status via heartbeats, health checks, registration/deregistration, or equivalent mechanisms.

Typical lifecycle:

1. The instance starts up and registers with the service registry.
2. The instance finishes initialization and becomes ready to receive traffic.
3. The registry or discovery client supplies the instance to LoadBalancer.
4. When the instance stops or becomes unhealthy, registration status is updated or the instance is removed from the selectable list.
5. The instance recovers and re-registers or is marked ready again.

Updates are not always instantaneous. The registry may hold stale data for a period; heartbeats run on an interval; instance list caches may not have refreshed yet. Therefore, a dead instance can still appear in the list seen by LoadBalancer.

Distinguish three states:

- **Registered:** the registry knows the instance's address.
- **Ready/healthy:** the instance has passed readiness criteria to receive traffic.
- **Request succeeded:** a specific call to the instance completed successfully.

An instance can be registered without being ready. An instance can be marked healthy while an individual request still fails due to bad data, timeout, or transient errors. Conversely, one successful request does not prove an instance is permanently healthy.

In Kubernetes, readiness probes typically determine whether a Pod is added to traffic-serving endpoints; liveness probes detect processes that need restarting. Do not use liveness instead of readiness: an application that is alive but not ready can still fail requests if included in the traffic-receiving list.

## 3. LoadBalancer selects an instance from the usable list

Spring Cloud LoadBalancer obtains a list of ServiceInstances from a discovery client or ServiceInstanceListSupplier, then applies an instance selection strategy. Depending on configuration, the strategy may distribute sequentially, randomly, or use another policy.

Key points to remember:

- LoadBalancer can only choose from the list provided by the supplier.
- If the list contains a dead instance, the algorithm can still pick that instance.
- If the registry returns an empty list, the call has no destination and may fail before an HTTP request can even be built.
- A single instance selection does not itself build failure-rate history to trip a circuit.
- Health checks or instance filters must be configured separately if you want unhealthy instances excluded from the list.

Example configuring a Feign client by service ID:

    @FeignClient(name = "inventory-service")
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

When no fixed URL is configured, OpenFeign can use Spring Cloud LoadBalancer to select an inventory-service instance. The service ID must match the name registered in the registry.

If a specific URL is set on the Feign client or a fixed URL is configured for the client, the call path can bypass service-ID instance selection. A circuit breaker can still protect the Feign call, but tests will no longer verify Service Discovery and LoadBalancer.

## 4. Circuit breakers usually protect logical calls, not individual IPs automatically

In typical integrations, a circuit breaker is created per client name or operation, such as inventory-read. LoadBalancer performs instance selection inside the protected call. Consequently, multiple instances can contribute outcomes to the same breaker sliding window.

Example:

    inventory-read
        |
        +-- request 1 --> instance A --> success
        +-- request 2 --> instance B --> connection error
        +-- request 3 --> instance C --> success
        +-- request 4 --> instance B --> timeout
        +-- request 5 --> instance A --> success

The inventory-read breaker sees outcomes of the logical call across the scope wrapped by the integration. It does not by default maintain separate state for A, B, and C. If B fails continuously while A and C are healthy, B's errors still raise the overall failure rate; however, two healthy instances may keep the aggregate rate below the opening threshold.

This leads to two consequences:

- An OPEN breaker for inventory-read does not prove all inventory-service instances are failing.
- A single failing instance does not guarantee the breaker will open immediately, because the decision still depends on sample count, sliding window, failure rate, slow-call rate, and outcomes from other instances.

Do not use breaker state as the sole source for deciding which instance should be removed from the registry. A breaker answers a question about the logical call; health checks and LoadBalancer manage instance eligibility.

## 5. What happens when only one instance fails?

Suppose inventory-service has three instances A, B, and C. A and C are healthy, while B refuses connections.

| Scenario | Discovery / LoadBalancer | Per-service circuit breaker |
| --- | --- | --- |
| B is still in the registry | B can continue to be selected. | Requests to B fail and contribute to shared statistics. |
| B has been removed from the list | LoadBalancer only selects A and C. | New requests succeed; the breaker gradually reflects new outcomes across the sliding window. |
| B fails intermittently | B can continue to be selected depending on the algorithm. | Failure rate may not yet reach the opening threshold. |
| B fails continuously, A and C remain healthy | LoadBalancer can still distribute to all three if there is no health filter. | The shared breaker may open if the combined error rate exceeds the threshold. |
| A, B, and C are all unavailable | No healthy target to select or all attempts fail. | The breaker may open once enough samples accumulate; prior to that, requests still suffer timeouts/errors. |

If only one instance fails, the solution usually belongs at the health/discovery layer or bounded retries to avoid continuing to send requests to that instance. A service-level circuit breaker remains useful when most or all calls are degrading, but it is not an automatic per-instance outlier filter.

If the system needs to detect and isolate a single failing instance, an instance-aware health check or outlier detection mechanism is required. Do not assume an HTTP 500 error will automatically cause the registry to deregister an instance.

## 6. Health checks and the usable instance list

Spring Cloud LoadBalancer supports extending the instance list source via ServiceInstanceListSupplier. Discovery can be combined with a filter or health-check supplier to provide only instances meeting check criteria.

Design points to consider:

- Choose an appropriate health endpoint, usually a readiness endpoint or one that verifies request-serving capability.
- Set reasonable check intervals and timeouts; overly frequent checks can create extra load.
- Define detection time for failing instances and cooldown time before returning an instance to the list.
- Avoid health checks that depend on the inspected service in a way that creates a loop.
- Do not reinstate an instance immediately after a single successful health check if the service is still unstable.
- Monitor the number of instances returned by discovery and the number remaining after filtering.

Periodic health checks have detection lag. If an instance starts failing right after a successful check, some requests can still be routed to it before the next check. Thus, health checks do not replace timeouts and bounded retries.

With Kubernetes, readiness probes and Service endpoints are usually the primary mechanism controlling whether a Pod receives traffic. With Eureka, Consul, or other registries, the discovery client has its own status updates and caches. Use the mechanism suited to your deployment platform and measure actual update propagation lag.

## 7. Combining retries with LoadBalancer and circuit breakers

Retries can help when one specific instance fails while other healthy instances exist. A failed attempt can be retried on a different instance within the same request budget.

Example flow:

    Logical call: inventory-read
        |
        v
    Attempt 1 -> instance B -> connection failure
        |
        v
    Retry policy (attempts left and within deadline?)
        |
        v
    Attempt 2 -> instance C -> success
        |
        v
    Logical result: success

If retry sits inside the breaker boundary, the breaker can observe the final outcome of the logical call rather than each individual attempt. In that case, a request with one failed attempt followed by a successful retry can be recorded as a success at the breaker level. Exact composition behavior depends on integration ordering and version; verify through logs, events, and testing.

When configuring retries:

- Limit retries on the same instance and hops to other instances.
- Keep total retry duration within the request deadline.
- Only retry recoverable errors, such as transient connection errors.
- Do not retry all 4xx errors; many are business or authorization outcomes.
- Be cautious with data-mutating requests such as reserve, create, or payment.
- Use an idempotency key or operation ID when retries could repeat side effects.
- Avoid retrying at multiple layers simultaneously because attempts can multiply.

If no instances exist in the registry, retries cannot conjure a valid target. Repeating the same request while the list is empty only adds latency. In that case, return an error or fallback per the business contract and let the breaker record the failure if the exception is classified as a dependency failure.

## 8. Distinguishing failure causes

Not all errors carry the same meaning. When handling fallbacks or tuning breakers, classify by layer:

| Cause | Originating layer | Handling approach |
| --- | --- | --- |
| No suitable instance found | Discovery / LoadBalancer | Check registry, service ID, readiness, and instance list. |
| Connection refused | Connection to instance | Check process, port, network policy, and registration status. |
| HTTP 5xx | Instance application | Check server-side logs and per-instance error rate. |
| HTTP 4xx | API contract or business logic | Handle by status and request; do not assume a health failure by default. |
| Read timeout | HTTP client / slow instance | Check latency, timeout, load, and slow-call rate. |
| CallNotPermittedException | Circuit breaker | Breaker is OPEN or denying calls; no new HTTP attempt made. |
| BulkheadFullException | Bulkhead | Permits or concurrency resources exhausted; does not mean registry has no instances. |

With Feign, exceptions from LoadBalancer or the HTTP client may be wrapped inside another exception. Inspect the cause chain and client-layer logs to identify the root cause. Do not match solely on exception messages because messages can change across versions.

Fallbacks should distinguish at least the main scenarios:

- Breaker OPEN: new calls blocked; can return cache or unavailable status.
- No instances: dependency cannot be routed; check discovery and respond per contract.
- One attempt timed out but retry succeeded: return the primary result if the logical call succeeded.
- All attempts failed: fallback or propagate error per business rules.
- Validation/authorization error: propagate the appropriate error rather than masking it with fallback data.

Never return quantity = 0 or a successful reservation confirmation when the system only knows the dependency is unresponsive. Fallback data must clearly represent UNKNOWN, UNAVAILABLE, or PENDING states.

## 9. When do you need a separate breaker per instance?

A per-service or per-method breaker is usually simpler and easier to operate. It limits the number of breakers, is easy to configure, and reflects the health of the logical dependency. However, it does not isolate statistics per instance address.

If a per-instance breaker is needed, the design must obtain the instance identity after LoadBalancer selects the destination. Each breaker must then be tied to a stable instance key, such as service ID combined with instance ID, rather than generating keys per request.

A per-instance design brings extra overhead:

- The number of breakers fluctuates with the instance count and can scale dynamically.
- Breakers must be evicted or cleaned up when instances deregister to avoid retaining stale state.
- Total instance counts must be bounded and registry lifecycles managed.
- Per-instance metrics can increase cardinality.
- A new instance may not have enough samples for the breaker to evaluate.
- Coordination between per-instance breakers, retries, and health checks must be defined.

Do not assume Spring Cloud CircuitBreaker automatically creates separate breakers per ServiceInstance simply because the application uses LoadBalancer. If that behavior is required, build an intentional integration around instance selection or per-instance clients and thoroughly test the lifecycle.

In many systems, health checks or instance filters are the better place to remove a clearly broken instance. A service-level breaker continues protecting when overall calls to the service degrade. Only implement per-instance breakers when operational data proves that per-instance isolation delivers substantial benefit.

## 10. Example protecting a LoadBalanced call with Spring Cloud CircuitBreaker

In an application using RestClient with LoadBalancer, you can define a builder annotated with @LoadBalanced:

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
            .baseUrl("http://inventory-service")
            .build();
    }

The name inventory-service is the service ID. LoadBalancer will select an instance when the request executes.

You can wrap the call operation using CircuitBreakerFactory:

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryRestClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryRestClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse find(String sku) {
            return circuitBreakerFactory.create("inventory-read").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

This example illustrates a breaker at the logical call boundary. RestClient has an instance selected by LoadBalancer inside the Supplier. InventoryResponse.unknown is an application-defined result that the business layer must treat as undetermined inventory.

If using OpenFeign with automatic CircuitBreaker integration enabled, do not wrap the same Feign method a second time with CircuitBreakerFactory unless intentionally designed to do so. Avoid creating two nested breaker layers because they can record different outcomes and run different fallbacks, making diagnosis difficult.

## 11. Observing both service ID and instance

To understand whether a breaker opened because of a single instance or the entire service, observe both the logical call and the selected instance.

Data worth collecting:

- Service ID and breaker name.
- Selected instance ID or target address, in logs or traces.
- HTTP outcome and exception type.
- Connect duration, response duration, and total logical call duration.
- Attempt count, instance chosen on each attempt, and retry outcome.
- Number of registered, healthy, and selectable instances.
- Breaker state, transitions, failure rate, slow-call rate, and rejected call count.
- Fallback counts by cause.

A dashboard can separate two views:

| View | Metrics |
| --- | --- |
| Logical service | Breaker state, total requests, failure rate, slow-call rate, not-permitted, fallback. |
| Instance | Requests per instance, error rate, latency, health/readiness, and selections after errors. |

Looking only at the inventory-read breaker may show rising failure rates without revealing which instance caused them. Looking only at instance health may miss a situation where all instances are slow below the threshold that triggers health-check eviction.

Do not put request ID, SKU, or exception message into metric tags. Instance IDs bounded by deployment scale can generally be used in logs/traces; for metrics, consider cardinality and instance lifecycle. Use correlation IDs to link caller, LoadBalancer, and server logs during investigations.

## 12. Testing failing instance scenarios

Spin up inventory-service with three instances A, B, and C. Each instance logs its instance ID or returns metadata for test environments only. Run these cases:

| Test case | How to reproduce | What to verify |
| --- | --- | --- |
| One instance stops abruptly | Stop B while keeping B in the registry long enough to simulate stale data. | LoadBalancer may pick B before registry updates; failed requests are recorded. |
| Instance not ready | Start B without passing readiness. | B should not be placed in the traffic-receiving list if discovery/health integration is configured properly. |
| One instance returns 5xx | Configure B to return errors while A and C succeed. | Observe distribution, retries, per-instance errors, and shared breaker failure rate. |
| One instance responds slowly | Make B delay responses past slow-call threshold or timeout. | Measure latency, timeouts, and slow-call rate. |
| All instances down | Stop A, B, and C or make the discovery list empty. | No destination available; inspect exceptions, breaker, and fallback. |
| Instance recovers | Restart B and let it pass readiness. | B is only selected again once the instance list updates per configured mechanism. |
| Breaker OPEN | Induce enough errors to open the breaker. | Requests are rejected before creating new attempts to instances; LoadBalancer cannot pick a target for blocked calls. |

In every test case, record the service ID, selected instance, attempt count, exception, breaker transition, and when the registry updated. Never rely solely on the final response because retries or fallbacks can hide first-attempt failures.

## 13. Comprehensive practice exercise

Build order-service calling inventory-service with Service Discovery, Spring Cloud LoadBalancer, and Spring Cloud CircuitBreaker:

1. Register at least three inventory-service instances in the registry or test discovery configuration.
2. Create a client using the service ID without hardcoding a fixed URL.
3. Enable a circuit breaker at the inventory-read boundary and configure sliding window and timeouts.
4. Verify LoadBalancer selects multiple instances when all are healthy.
5. Make one instance fail and keep it in the list briefly to observe behavior with a stale registry.
6. Enable health/readiness integration or an appropriate instance-eviction mechanism; verify the failing instance is removed from selection once status updates.
7. Add bounded retry of one attempt to another instance and measure actual attempt counts.
8. Induce errors across all instances so the breaker reaches OPEN.
9. While OPEN, verify requests fail fast and the fallback accurately reflects an unknown state.
10. Recover the instances and observe HALF_OPEN, followed by CLOSED.
11. Compare logical-service metrics with per-instance logs to determine whether the breaker reflects localized errors or service-wide degradation.

Upon completion, you should be able to explain how the registry manages instance lists, how health checks determine traffic eligibility, how LoadBalancer picks a target, and how the circuit breaker protects the logical call. You should also be able to state why a default breaker does not automatically isolate individual IPs, when retries help, and why both registry state and request outcomes must be inspected.

## References

- Spring Cloud LoadBalancer Reference: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-loadbalancer.html
- Spring Cloud CircuitBreaker Reference: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker.html
- Spring Cloud OpenFeign Reference: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
