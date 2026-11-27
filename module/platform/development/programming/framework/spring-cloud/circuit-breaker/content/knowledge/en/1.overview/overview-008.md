# Foundational Concepts and Learning Path: From a Single Call to a Multi-Service System

## Lesson Objectives

When an application calls only one other service, failures often look localized: a request fails or takes a long time to finish. In a multi-service system, that same failure can tie up processing threads, occupy connections, grow queues, and cause otherwise healthy services to stop responding. A circuit breaker helps limit this impact by tracking call outcomes and temporarily stopping calls to a troubled dependency.

After this lesson, you will be able to:

- Describe the path of a request from a simple application to a multi-service chain and explain how failures propagate.
- Distinguish the three states **CLOSED**, **OPEN**, and **HALF_OPEN**, along with the role of the sliding window.
- Wrap a synchronous or reactive call using Spring Cloud CircuitBreaker with Resilience4j.
- Combine circuit breaker with timeout, fallback, and bulkhead according to each mechanism's responsibility.
- Read basic metrics to see how a circuit breaker is protecting a service.

## 1. Starting from a Single Call to a Dependent Service

Suppose **order-service** needs to call **inventory-service** to check stock before confirming an order. In the first version, the processing flow is simple:

    Client -> order-service -> inventory-service

If inventory-service responds quickly and reliably, the call proceeds normally. However, a remote dependency can fail in many ways:

- Unable to connect because the process stopped, DNS failed, or the network dropped.
- HTTP error responses because the service could not process the request.
- Overly slow responses due to database queries, lock contention, or rising load.
- Only a subset of requests failing while others continue succeeding.

A key difference between an in-process call and a network call is that the calling application has no control over when the receiving application finishes. A slow call can hold processing threads and connections for the entire wait duration. When many requests wait concurrently, available threads shrink, queues grow, and order-service itself starts responding slowly.

A timeout limits how long a single call waits. A circuit breaker answers a different question: when recent calls indicate the dependency is failing or overly slow, should we keep sending more requests there or temporarily reject them immediately? The two mechanisms usually need to work together.

## 2. When a Single Call Becomes a Multi-Service Chain

A real-world system may also include a pricing service and a central warehouse service:

    Client
      |
      v
    order-service
      |-- Circuit breaker: inventory --> inventory-service
      |                                   |
      |                                   +-- Circuit breaker: warehouse --> warehouse-service
      |
      +-- Circuit breaker: pricing -----> pricing-service

An order creation request may require both stock and price. Inventory-service itself calls warehouse-service. If the central warehouse slows down, calls from inventory are held up. Inventory gradually runs out of processing threads, then order has to wait on inventory, and new order creation requests are impacted too.

Circuit breakers are placed at the boundary calling remote dependencies. In the example above, order has one breaker for inventory and one breaker for pricing; inventory has its own breaker for warehouse. Each breaker monitors a specific dependency, so an incident in warehouse does not directly trip pricing's breaker.

Do not lump all outbound calls into one shared breaker. One service may be healthy while another is failing. Nor should you create breakers per user or per order ID: instance counts would grow uncontrollably and each statistical window would have too little data. Name breakers by dependency or call group with comparable operational characteristics, such as inventory and pricing.

## 3. The Three States of a Circuit Breaker

A circuit breaker is commonly understood through three states:

| State | Call Handling | State Transition Condition |
| --- | --- | --- |
| **CLOSED** | Allows calls to reach the dependent service and records outcomes. | When the failure rate or slow call rate exceeds the threshold after enough samples are collected, transitions to OPEN. |
| **OPEN** | Fails fast on new calls, sending no requests to the dependency. The application can run a fallback. | After the configured wait duration, the breaker transitions to HALF_OPEN. |
| **HALF_OPEN** | Allows only a small number of probe calls to test whether the dependency has recovered. | If probe calls meet requirements, returns to CLOSED; if failures or excessive slowness persist, returns to OPEN. |

State transition flow:

    CLOSED -- failure or slowness exceeds threshold --> OPEN
       ^                                                |
       |                                                | wait duration expires
       |                                                v
       +--------------- probe succeeds ------------ HALF_OPEN
                                                        |
                                                        +-- probe fails --> OPEN

In CLOSED, the breaker does not guarantee every call succeeds; it simply lets calls through and keeps collecting statistics. In OPEN, calls are blocked fast, typically throwing CallNotPermittedException from Resilience4j. In HALF_OPEN, probe call counts are capped to avoid flooding a freshly recovered service with heavy load.

Breaker state is typically held in memory within each application process. If order-service runs multiple instances, each instance can have its own state and statistics; do not assume all instances will open their breakers at the exact same moment.

## 4. Sliding Windows for Deciding When to Open the Breaker

A breaker needs to inspect recent call outcomes. Resilience4j provides two common sliding window types:

- **COUNT_BASED**: the window holds outcomes of a fixed number of most recent calls. For instance, a slidingWindowSize of 20 means statistics are computed over up to the 20 most recent calls.
- **TIME_BASED**: the window is divided into time slices across an observation interval. This type fits when you want to evaluate failures on a time cadence rather than by request count.

Related settings include:

- **slidingWindowSize**: window size in number of calls or number of time buckets, depending on window type.
- **minimumNumberOfCalls**: minimum number of calls required before calculating rates to make a decision. When samples are insufficient, the breaker does not open solely due to the first few failures.
- **failureRateThreshold**: percentage threshold of failed calls.
- **slowCallDurationThreshold**: duration from which a call is considered slow.
- **slowCallRateThreshold**: percentage threshold of slow calls.

For example, with failureRateThreshold set to 50, once enough samples exist, a failure rate reaching or exceeding 50% can open the breaker. A breaker can also open when the slow call rate exceeds slowCallRateThreshold, even if calls still eventually return successfully. This is useful because an overly slow service can still exhaust the caller's resources.

A sliding window is not a request rate limiter. It uses recent data to evaluate call health. Window size, minimum sample count, and thresholds must be grounded in normal traffic, SLOs, and dependency characteristics; numbers in examples are only starting points for experimentation.

## 5. Integrating Spring Cloud CircuitBreaker with Resilience4j

Spring Cloud CircuitBreaker provides an abstraction layer for applications to create and use circuit breakers. Resilience4j is a popular implementation. For a Spring Boot application using synchronous calls, add the following starter and manage versions using a Spring Cloud release train compatible with the project's Spring Boot version:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

The following example uses RestClient from Spring Framework 6.1 or later. Assume the client is configured with a base URL pointing to inventory-service:

    import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestClient;

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse find(String sku) {
            return circuitBreakerFactory.create("inventory").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

create("inventory") retrieves the breaker named inventory. The first function executes the actual call. The second function is the fallback invoked when the call fails or the breaker is OPEN. InventoryResponse.unknown(sku) is an application-defined method representing an undetermined state; it is not a built-in Spring API.

Fallbacks must accurately reflect data certainty. If inventory cannot be queried, do not claim the product is definitely in stock or definitely out of stock. You can return an UNKNOWN status, use still-valid cached data if business rules allow, or ask the user to retry. Fallbacks must also be fast and must not call back into the very failing dependency. If the fallback throws an error, that error can still propagate up to the calling layer.

Resilience4j configuration can be placed in application.yml:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            registerHealthIndicator: true
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3
            automaticTransitionFromOpenToHalfOpenEnabled: true

This is an illustrative configuration for a breaker named inventory. Once at least 10 samples exist in the window, Resilience4j evaluates the failure rate and slow call rate. If the breaker opens, it waits 10 seconds before allowing up to 3 probe calls in HALF_OPEN. After probing, the breaker decides to close again or reopen based on outcomes and configured thresholds.

The instance name in configuration must match the name passed to create("inventory"). For another dependency, create a separate configuration instance such as pricing. Clearly determine which exceptions count as failures and which exceptions should be ignored. For instance, authentication errors or invalid input usually do not indicate dependent service health; counting them toward the failure rate can open the breaker for the wrong reason. Resilience4j supports recordExceptions and ignoreExceptions settings for this case.

## 6. Coordinating Circuit Breaker, Timeout, Fallback, and Bulkhead

Protection mechanisms address different risks:

| Mechanism | Responsibility | Key Takeaway |
| --- | --- | --- |
| Timeout | Limits how long a single call waits. | Set timeouts on the HTTP client or actual transport layer; a circuit breaker does not stop an already-running call on its own. |
| Circuit breaker | Stops sending calls when a dependency shows sustained errors or slowness. | Uses statistics and state to avoid piling requests onto a troubled dependency. |
| Fallback | Provides a degraded response when the call cannot complete. | Only return defaults or cached data when business rules permit, and clearly indicate reliability. |
| Bulkhead | Caps resources or concurrent calls allocated to a dependency. | Keeps a slow dependency from exhausting threads, connections, or application processing capacity. |
| Retry | Re-attempts a call likely to succeed on the next try. | Cap attempts, use backoff, and avoid amplifying load while a service is overloaded. |

### Timeout

A circuit breaker can mark calls as slow based on slowCallDurationThreshold, yet measuring slowness does not equate to cancelling the call. For synchronous HTTP calls, configure connect timeouts and response/read timeouts on the HTTP client. Client timeouts must fit within the time budget the upstream calling layer can wait.

Resilience4j TimeLimiter can cap duration for supported async tasks, such as CompletableFuture-based calls. An instance can be configured as follows:

    resilience4j:
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 900ms
            cancelRunningFuture: true

TimeLimiter does not replace network connection timeouts. Cancelling a Future also does not guarantee the remote server has stopped processing the request; set timeouts on the proper HTTP client and verify cancellation behavior of the library in use.

### Bulkhead

A bulkhead limits concurrent calls to a dependency. For example, if inventory may receive at most 24 concurrent calls from one order instance, excess calls can be rejected or forced to wait according to configuration. When using a semaphore-style Resilience4j Bulkhead, configuration looks like:

    resilience4j:
      bulkhead:
        instances:
          inventory:
            maxConcurrentCalls: 24
            maxWaitDuration: 0ms

This limit applies per application instance and per bulkhead configuration in use. If the system runs multiple pods, total concurrent calls hitting inventory can exceed a single pod's limit. Account for instance count when choosing limits. A thread-pool bulkhead is another option when isolating tasks in a dedicated thread pool; manage both pool size and queue capacity to avoid shifting bottlenecks elsewhere.

### Retry and Application Order

Retry helps with transient errors, yet every retry attempt creates additional load. If multiple layers retry simultaneously, one initial request can generate a large number of actual calls. Retry only recoverable errors, cap attempt counts, add backoff and jitter, and keep total duration within the request budget.

Do not use retry to mask a dependency experiencing prolonged failures. A circuit breaker stops new calls once evidence shows continuing to try causes harm. When composing multiple decorators, understand execution order so you know whether the breaker records each individual attempt or the entire retry chain; configure a consistent order and test with deliberate fault scenarios.

## 7. Protecting Reactive Calls

For applications using WebClient and Reactor, Spring Cloud CircuitBreaker provides a dedicated reactive starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>

You can wrap a Mono using ReactiveCircuitBreakerFactory:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Component;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Component
    public class ReactiveInventoryGateway {

        private final WebClient inventoryClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient inventoryClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            return circuitBreakerFactory.create("inventory").run(
                inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .bodyToMono(InventoryResponse.class),
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

In a reactive flow, the fallback returns a publisher such as Mono. Keep the processing chain asynchronous and avoid calling block() on reactive threads, as doing so negates non-blocking benefits and stalls the event loop. Also set appropriate timeouts on WebClient; the circuit breaker still tracks failure statistics and blocks subsequent calls, while the timeout governs how long each individual request waits.

## 8. Monitoring Protection Effectiveness

A circuit breaker is only helpful when operations teams can observe when it opened, why it opened, and whether the dependency has recovered. With Spring Boot Actuator and Micrometer, Resilience4j can export metrics on call counts, success/failure outcomes, slow calls, failure rates, and breaker states. You can start with these data groups:

- Call counts by breaker name and outcome: succeeded, failed, or rejected while the breaker is open.
- Current state: CLOSED, OPEN, or HALF_OPEN.
- Failure rate and slow call rate against configured thresholds.
- Dependency response time and active in-flight call count.
- Fallback invocation count and degraded response rate.

You can use Actuator endpoints such as health and metrics; if exporting to Prometheus, add the corresponding Prometheus registry and expose only endpoints aligned with the application's operational policy. Exact metric names may vary by version and integration configuration, so inspect the application's actual metric list instead of assuming all names are available.

When reading metrics, combine breaker state with the dependent service's latency and error rates. A continuously opening breaker can indicate an unstable dependency, overly tight timeouts, misconfigured thresholds, or misclassified exceptions. A sudden spike in fallbacks signals that the user experience is in degraded mode; it should not be treated as normal operation simply because the API still returns HTTP success.

## 9. Learning and Practice Sequence

Proceeding step by step helps you see the effect of each protection layer before combining them:

| Step | Practice Activity | Expected Observation |
| --- | --- | --- |
| 1. Single call | Create order-service calling inventory-service and record response times. | Understand the request path and normal latency. |
| 2. Failures and timeouts | Make inventory return errors, drop connections, or respond slowly; configure client timeouts. | Requests do not wait indefinitely and errors are handled cleanly. |
| 3. Circuit breaker | Create the inventory breaker, configure sliding window and thresholds. | Observe transitions from CLOSED to OPEN, then HALF_OPEN. |
| 4. Fallback | Return an undetermined status or valid cached data when the breaker opens. | API produces an intentional degraded response without fabricating wrong data. |
| 5. Multiple dependencies | Add pricing-service, then have inventory call warehouse; use a separate breaker per dependency. | One failing dependency does not trip breakers for all other calls. |
| 6. Bulkhead and retry | Cap concurrent calls; test bounded retries on transient errors. | Load stays controlled and is not amplified by repeated attempts. |
| 7. Reactive | Convert one call to WebClient and wrap the publisher with a reactive circuit breaker. | Flow remains non-blocking and fallback returns a publisher. |
| 8. Observability | Enable Actuator/Micrometer; monitor state, latency, errors, and fallbacks. | Data is available to tune thresholds based on real behavior. |

Capstone practice exercise: build an order creation flow consisting of order-service, inventory-service, and pricing-service. First measure latency while all services are healthy. Next, deliberately make inventory respond slowly, return errors, and recover. Observe when the breaker opens, confirm new calls fail fast, inspect fallback content, and watch probe calls in HALF_OPEN. Finally, add warehouse behind inventory and generate concurrent load to see how bulkhead limits blast radius.

Upon completion, you should be able to explain why timeout, circuit breaker, fallback, and bulkhead must work together; choose breaker boundaries per dependency; and use metrics to tune windows and thresholds to real traffic. Validate these choices in a test environment under simulated load and faults before applying them to a user-facing production system.
