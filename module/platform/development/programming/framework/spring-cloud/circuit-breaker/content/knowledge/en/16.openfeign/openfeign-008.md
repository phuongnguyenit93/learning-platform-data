# Verifying Circuit Breaking with Service Discovery and LoadBalancer

## Lesson Objectives

In microservices systems, OpenFeign typically calls services by service ID rather than a fixed IP address. Service Discovery provides the list of registered instances; Spring Cloud LoadBalancer selects an instance for each call. Circuit breaker protects that call when the service fails or responds too slowly.

These three mechanisms are related but do not replace one another. Discovery finds instances, LoadBalancer picks the destination, and the circuit breaker decides whether to let a new logical call pass through based on recent outcomes. To verify behavior properly, you must know which Feign call the breaker wraps, which instance LoadBalancer selected, and at which layer errors occur.

After this lesson, you will be able to:

- Configure OpenFeign to call services by service ID and Spring Cloud LoadBalancer.
- Enable Spring Cloud CircuitBreaker integration for Feign clients.
- Explain the path of a request from Feign through LoadBalancer to the selected instance.
- Distinguish a per-client/method breaker from the health state of individual instances.
- Test behavior when the registry has no instances, one instance fails, or the entire service is slow.
- Use fallback or FallbackFactory for controlled responses.
- Read metrics and logs to determine whether errors originate from discovery, load balancing, HTTP, or the circuit breaker.
- Verify the effects of retries, timeouts, and fixed URL configuration.

## 1. Three Responsibilities in an OpenFeign Call

Suppose order-service needs to fetch inventory from inventory-service. The application declares a Feign client using the service name:

    @FeignClient(name = "inventory-service")
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

When no fixed URL is declared, the name inventory-service is used as the service ID. Typical flow:

    order-service
        |
        v
    InventoryClient (OpenFeign)
        |
        v
    CircuitBreaker (if enabled)
        |
        v
    Feign request handler
        |
        v
    Spring Cloud LoadBalancer
        |
        +---- select instance A ----> inventory-service
        |
        +---- or instance B ------> inventory-service

Each component has its own responsibility:

| Component | Responsibility | What It Does Not Solve on Its Own |
| --- | --- | --- |
| Service Discovery | Registers and provides the list of instances per service ID. | Does not decide whether a business call should continue after repeated failures. |
| Spring Cloud LoadBalancer | Selects an instance from the available list for a call. | Does not create a circuit breaker from repeated Feign call outcomes. |
| CircuitBreaker | Tracks protected call outcomes and blocks new calls when the breaker is OPEN. | Does not update the registry or remove a failing instance from discovery lists. |
| OpenFeign | Builds HTTP calls from the declared interface. | Does not replace discovery, load balancing, or recovery policies. |

Feign's circuit breaker protects a logical call boundary. LoadBalancer selects the instance beneath that boundary. Therefore, a single per-client/method breaker can observe outcomes from multiple different instances.

## 2. Declaring Required Dependencies

An application using OpenFeign, Service Discovery, LoadBalancer, and Resilience4j CircuitBreaker needs the corresponding components. Maven example:

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-openfeign</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        </dependency>

        <!-- Add an appropriate discovery client, such as Eureka, Consul, or Kubernetes. -->
    </dependencies>

Versions should be managed by a Spring Cloud BOM compatible with the project's Spring Boot version. The specific discovery client depends on the registry platform the system uses. If LoadBalancer or CircuitBreaker starters are already brought onto the classpath via another dependency, inspect the dependency tree before adding duplicates.

Enable Feign client scanning in the application:

    @SpringBootApplication
    @EnableFeignClients
    public class OrderApplication {

        public static void main(String[] args) {
            SpringApplication.run(OrderApplication.class, args);
        }
    }

The application also needs discovery client configuration to register or look up inventory-service. The service ID in the registry must match the name of @FeignClient.

## 3. Enabling CircuitBreaker for OpenFeign

Spring Cloud OpenFeign supports Spring Cloud CircuitBreaker integration. With Resilience4j, the implementation starter must be on the classpath and OpenFeign's circuit breaker feature must be enabled:

    spring:
      cloud:
        openfeign:
          circuitbreaker:
            enabled: true

When this feature is enabled, Feign client methods created through the integration mechanism will execute inside a circuit breaker. Without enabling the property, merely having OpenFeign and Resilience4j on the classpath does not mean Feign methods are protected.

Example client with a fallback factory:

    @FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient",
        fallbackFactory = InventoryFallbackFactory.class
    )
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

contextId distinguishes client configuration when an application has multiple Feign clients calling the same service ID. name remains the service ID used to locate the service via LoadBalancer.

Do not declare the url attribute if the goal is to let LoadBalancer select instances by service ID. When a fixed URL is configured directly on @FeignClient or its corresponding client configuration, calls use that address and bypass service-ID instance selection. The circuit breaker can still protect the Feign call, but the test no longer verifies discovery and LoadBalancer.

## 4. Understanding What Scope the Breaker Protects

When Feign CircuitBreaker is enabled, the Feign method call is wrapped by a circuit breaker. Within a request, the inner execution can include fetching an instance from LoadBalancer, making the HTTP request, and receiving the response.

For example, order-service calls:

    inventoryClient.find("SKU-42");

LoadBalancer might choose instance A on the first call and instance B on the next. If the same breaker name is used for the find method, outcomes from the selected instances contribute to that breaker's statistics.

This leads to two important points:

- A per-client/method breaker typically evaluates the aggregate outcome of logical calls, rather than creating a separate breaker per IP or per instance by default.
- If one instance fails while other instances are healthy, failed calls from the failing instance still affect the breaker's overall statistics.

The circuit breaker does not mark instance A as unhealthy in the Service Registry. Registration, deregistration, health checks, and instance filtering belong to the discovery client or LoadBalancer configuration. To exclude a failing instance from selection, inspect the health check mechanism and instance status on the discovery platform.

Do not interpret an OPEN state of the inventory-read breaker as proof that every inventory-service instance is broken. It only indicates that the protected call met the breaker's opening condition based on metrics and configured thresholds.

## 5. Configuring Resilience4j for Feign Calls

The breaker name is generated according to Spring Cloud OpenFeign's naming rules and the version in use. Do not guess a name from the service ID and assume the configuration was definitely applied. Check the actual name in logs, metrics, or the application's CircuitBreakerNameResolver configuration.

Once the exact breaker name is confirmed, configure the Resilience4j instance:

    resilience4j:
      circuitbreaker:
        instances:
          <feign-breaker-name>:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

Values in the example are illustrative. Choose window size, minimum sample count, failure rate, and slow call threshold based on traffic volume and the latency budget of inventory-service.

Feign client timeouts can be configured separately:

    spring:
      cloud:
        openfeign:
          client:
            config:
              inventoryReadClient:
                connectTimeout: 500
                readTimeout: 1200

Client-specific configuration must match the Feign configuration name used by the project's version. In real projects, check the version documentation and bound configuration to verify timeouts apply to the right client.

Feign timeouts limit wait time at the HTTP client layer. CircuitBreaker's slowCallDurationThreshold only classifies slow calls for statistics. These two settings play different roles: one limits request duration, while the other helps the breaker assess dependency health.

## 6. Using FallbackFactory to Identify Causes

FallbackFactory allows creating fallbacks based on the Throwable that caused the failure. This is useful when distinguishing an OPEN breaker, missing instances, timeouts, or HTTP errors.

Example:

    @Component
    public class InventoryFallbackFactory
            implements FallbackFactory<InventoryClient> {

        @Override
        public InventoryClient create(Throwable cause) {
            return sku -> {
                if (hasCause(cause, CallNotPermittedException.class)) {
                    return InventoryResponse.unavailable(sku);
                }

                if (isNoInstanceFailure(cause)) {
                    return InventoryResponse.unavailable(sku);
                }

                if (isTimeoutFailure(cause)) {
                    return InventoryResponse.unknown(sku);
                }

                return InventoryResponse.unknown(sku);
            };
        }

        private boolean hasCause(Throwable error, Class<?> type) {
            Throwable current = error;
            while (current != null) {
                if (type.isInstance(current)) {
                    return true;
                }
                current = current.getCause();
            }
            return false;
        }

        private boolean isNoInstanceFailure(Throwable error) {
            // Check specific exceptions thrown by the project's discovery/LoadBalancer.
            return false;
        }

        private boolean isTimeoutFailure(Throwable error) {
            // Classify timeout exceptions according to the HTTP client in use.
            return false;
        }
    }

The isNoInstanceFailure and isTimeoutFailure methods are extension points to implement for your system's actual exceptions. Avoid relying on an error message string because messages can change across versions or implementations.

InventoryResponse.unavailable and unknown are application-defined methods. Fallbacks should not return inventory quantity 0 or claim out-of-stock when the service could not be queried. Clearly indicate unknown data or that the service source is currently unavailable.

FallbackFactory must also be placed within component scan scope. If using a direct fallback class instead of a factory, ensure it implements the right Feign client interface and can be instantiated by Spring as a bean.

## 7. Verifying Service Discovery and LoadBalancer

To verify the actual path, start with at least two inventory-service instances distinguishable via logs or responses. Each instance can return an instanceId field in the test environment.

Example SimpleDiscoveryClient configuration in a test environment:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082

This creates a static instance list for testing. In production environments, registries such as Eureka, Consul, or Kubernetes provide the instance list through their respective mechanisms.

Proceed step by step:

1. Start two inventory-service instances on ports 8081 and 8082.
2. Start order-service with OpenFeign, LoadBalancer, and CircuitBreaker enabled.
3. Call inventoryClient.find multiple times and observe instanceId or access logs on both instances.
4. Confirm both instances can be selected according to the active LoadBalancer strategy.
5. Stop one instance or make that instance return controlled errors.
6. Continue calling from order-service and record the selected instance, exceptions, and breaker state.
7. Stop all instances or make the registry return an empty list.
8. Observe no-instance-found errors, fallback behavior, and breaker metrics.
9. Restart the instances and observe re-registration and recovery state.

Do not assume LoadBalancer immediately excludes an instance just because one request failed. Instance exclusion depends on health checks, the registry, and specific configuration. If a failing instance remains advertised, LoadBalancer may continue selecting it.

## 8. Distinguishing Single-Instance Failures from Service-Wide Failures

Test three distinct scenarios:

| Scenario | Discovery / LoadBalancer | CircuitBreaker |
| --- | --- | --- |
| One instance fails, another is healthy | May still pick the failing instance if the registry has not removed it. | Records Feign call outcomes; breaker may stay CLOSED if error rate stays below threshold. |
| All instances unavailable or unregistered | No suitable target; calls may fail before sending an HTTP request. | Call-path errors can be recorded per breaker config and lead to OPEN. |
| Service responds slowly across multiple instances | LoadBalancer can still pick instances; discovery does not necessarily know request latency. | Slow call rate can rise and open the breaker once enough samples accumulate. |

If only one instance fails yet the breaker opens, calls to healthy instances may also be blocked during the OPEN period because they share the same breaker name. In that case, address the root cause at the instance health layer and evaluate appropriate breaker boundaries.

If you want a separate circuit breaker per instance, you need a design that identifies the instance at target selection time and intentionally integrates with LoadBalancer. Default Feign CircuitBreaker configuration should not be assumed to automatically provide per-instance breakers. This is an advanced design requiring evaluation of instance counts, breaker lifecycles, and metric cardinality before implementation.

## 9. Retries and CircuitBreaker Can Affect Call Counts

Spring Cloud LoadBalancer can be configured to retry certain error types or requests. Feign can also have a retry mechanism depending on the client and configuration. When combining retries with a circuit breaker, determine whether retries sit inside or outside the breaker boundary.

If LoadBalancer performs multiple attempts inside one Feign call, the circuit breaker may observe the final outcome of the logical call rather than each instance selection as an independent sample. This detail depends on the integration and version in use; verify with logs and tests rather than assuming HTTP request counts equal breaker-recorded counts.

Key guidelines:

- Bound total retry attempts and retry time within the request deadline.
- Do not retry indefinitely when the registry has no instances.
- Retry only recoverable errors compatible with request semantics.
- Be cautious with write operations such as reserve or submit; a timeout does not prove the server never executed the command.
- Use an idempotency key or operation ID to avoid duplicate side effects.
- Avoid simultaneous retries across multiple layers, as actual requests can multiply exponentially.

Circuit breaker halts new calls when a dependency suffers prolonged failures. Retry handles brief transient glitches. Both mechanisms need a shared time budget so requests are not stretched excessively.

## 10. Inspecting Metrics and Logs Layer by Layer

When a Feign call fails, identify which layer caused the error before adjusting breaker thresholds:

- **Discovery:** Is the service ID registered, what status do instances have, and does the registry have fresh data?
- **LoadBalancer:** Which instance was selected, did retries happen, and was there a no-instance error?
- **Feign/HTTP client:** Actual request URL, connect timeout, read timeout, HTTP status, and decoding errors.
- **CircuitBreaker:** Breaker name, CLOSED/OPEN/HALF_OPEN state, failure rate, slow call rate, and rejected call count.
- **Fallback:** Cause passed into FallbackFactory and the type of fallback result returned.

Spring Boot Actuator and Micrometer can export Resilience4j metrics when appropriate dependencies and metrics configuration are present. Metric names and tags depend on versions. Check actual metrics endpoints, confirm the breaker name in use, and secure administrative endpoints.

Do not attach IP addresses, request IDs, or SKUs as metric tags if they create high cardinality. Detailed instance addresses belong in controlled logs or traces. A Correlation ID can help link order-service logs with inventory-service logs to determine which instance handled a request.

## 11. Verifying HALF_OPEN Recovery State

After the breaker transitions to OPEN and waitDurationInOpenState elapses, the breaker transitions to HALF_OPEN to allow a limited number of test calls. With Feign, these probe calls still route through LoadBalancer and may be distributed across different instances.

This means probe outcomes can depend on which instance is selected:

- If the selected instance is healthy, the breaker can record a success.
- If LoadBalancer picks an instance that is still failing, the breaker can transition back to OPEN.
- If the registry has already removed failing instances and only healthy ones remain, probes are more likely to succeed.

Do not treat HALF_OPEN as a direct per-instance health check. The breaker is testing the outcome of the logical call it protects. Registry/LoadBalancer health checks and breaker state should be observed separately.

When testing recovery, record the instanceId of each probe request, HTTP outcome, breaker state transition, and transition timestamp. This distinguishes full service recovery from a single healthy instance happening to be selected by chance.

## 12. Hands-On Integration Exercise

Build order-service calling inventory-service using OpenFeign, Service Discovery, LoadBalancer, and Resilience4j:

1. Declare OpenFeign, LoadBalancer, discovery client, and Resilience4j CircuitBreaker under a compatible BOM.
2. Enable @EnableFeignClients and declare InventoryClient with name set to inventory-service.
3. Do not set a fixed URL so Feign resolves the service ID through LoadBalancer.
4. Enable spring.cloud.openfeign.circuitbreaker.enabled.
5. Configure FallbackFactory to distinguish OPEN breaker, timeouts, and no-instance failures.
6. Register two inventory-service instances and confirm LoadBalancer distributes calls.
7. Make one instance return errors or respond slowly; observe the failures and selected instances.
8. Generate enough samples for the breaker to reach its open threshold; confirm new calls are rejected and fallback runs.
9. Stop all instances to verify the discovery no-target case.
10. Restart the services and observe HALF_OPEN probe calls through LoadBalancer.
11. Test bounded retries and compare HTTP attempt counts against logical call counts.
12. Inspect metrics and logs to distinguish discovery, LoadBalancer, Feign, CircuitBreaker, and fallback.

The expected outcome is that you can accurately trace a Feign call from service ID to selected instance, identify which boundary the breaker protects, and explain why breaker state does not represent individual instance health. With a clear understanding of each layer, you can tune health checks, LoadBalancer, timeouts, retries, and circuit breakers without confusing responsibilities across layers.

## References

- Spring Cloud OpenFeign — CircuitBreaker Support: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
- Spring Cloud LoadBalancer Reference: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-loadbalancer.html
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
