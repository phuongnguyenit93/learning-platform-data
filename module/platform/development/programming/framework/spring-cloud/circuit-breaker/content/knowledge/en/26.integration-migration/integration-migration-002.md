# Distinguishing Legacy Hystrix Configuration from Spring Cloud CircuitBreaker

## Lesson Objectives

Many legacy Spring Cloud applications use Netflix Hystrix to isolate remote calls, bound wait times, open the circuit when a dependency fails repeatedly, and return fallbacks. When migrating to Spring Cloud CircuitBreaker, development teams often encounter old configuration files still sitting in the repository that are no longer read by the new runtime. Renaming a few properties is not enough to complete the migration because the two systems differ in API models, thread isolation mechanisms, sliding window calculations, and metric exposure.

Spring Cloud CircuitBreaker provides a unified abstraction for circuit breakers. Resilience4j is a popular implementation with separate modules for CircuitBreaker, TimeLimiter, Bulkhead, and Retry. When migrating, you must clearly identify the behaviors currently used by the application, map each responsibility to the new mechanism, and test thoroughly before removing old Hystrix configurations.

After this lesson, you will be able to:

- Recognize legacy Hystrix configuration and understand why it does not automatically apply to Spring Cloud CircuitBreaker.
- Distinguish Hystrix's command key, group key, and thread-pool key from the new factory's id and groupName.
- Map circuit-opening thresholds, statistical windows, timeouts, and isolation to Resilience4j.
- Choose SemaphoreBulkhead or ThreadPoolBulkhead in place of the legacy isolation strategy.
- Migrate fallbacks from HystrixCommand to the CircuitBreakerFactory API or Feign fallback.
- Identify Hystrix features that have no direct one-to-one replacement.
- Build a verifiable migration plan with a safe rollback path.

## 1. Why Does Legacy Hystrix Configuration Not Apply Automatically?

Netflix Hystrix has been placed in maintenance mode, and modern Spring Cloud Netflix generations no longer provide Hystrix integration as older release trains did. Spring Cloud CircuitBreaker was built as an abstraction over modern implementations, including Resilience4j.

An application might still contain configuration such as:

    hystrix:
      command:
        default:
          execution:
            isolation:
              thread:
                timeoutInMilliseconds: 1000
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000

Keeping this YAML block in application.yml does not make Spring Cloud CircuitBreaker automatically read and translate it into Resilience4j configuration. The two namespaces and configuration models are different. If the new runtime no longer includes Hystrix integration, old Hystrix properties may simply sit there as unused configuration.

Before making edits, determine:

- Which Spring Cloud release train the application is running.
- Whether Hystrix dependencies are still present on the runtime classpath or only in configuration files.
- Whether calls are protected by HystrixCommand, annotations, Feign integration, or custom wrappers.
- Which commands use timeouts, thread isolation, semaphore isolation, fallbacks, request caches, collapsers, or dashboards.
- Whether Hystrix configuration exists in separate profiles, environment variables, or deployment manifests.

Do not delete old dependencies and properties based solely on file names. Verify actual call paths and which features are actively used.

## 2. Comparing Hystrix and Spring Cloud CircuitBreaker Models

Hystrix organizes protection around commands. Each command typically has a command key, a group key, and optionally a thread-pool key. Spring Cloud CircuitBreaker provides a factory to create a breaker by id; with Resilience4j, you can also pass a groupName to select group configuration.

| Hystrix | Spring Cloud CircuitBreaker / Resilience4j | Migration Meaning |
| --- | --- | --- |
| commandKey | id passed to the factory | Identifies the breaker instance and statistical scope. |
| groupKey | No direct equivalent; factory groupName mainly selects group configuration | Do not assume the new groupName has the same service-grouping, metrics, or thread-pool role as Hystrix. |
| threadPoolKey | ThreadPoolBulkhead configuration or a dedicated executor | Requires redesigning the pool and queue limits. |
| HystrixCommand | CircuitBreakerFactory and a protected Supplier | Usually requires rewriting command-invocation code to use the new API. |
| fallbackMethod / getFallback | Fallback function in run or Feign fallback/FallbackFactory | Must preserve semantics and error classification. |
| execution.isolation.thread.timeoutInMilliseconds | TimeLimiter, HTTP client timeout, or Reactor timeout | Choose the mechanism matching the execution model; not just a renamed property. |
| execution.isolation.strategy | SemaphoreBulkhead or ThreadPoolBulkhead | Requires re-selecting the concurrency and thread-ownership model. |
| circuitBreaker.* | resilience4j.circuitbreaker.instances.* | Thresholds and sliding windows are expressed differently. |
| Hystrix Dashboard / Turbine | Micrometer, Actuator, Prometheus, and centralized dashboards | Rebuild metrics, tags, events, and multi-instance aggregation. |

Concepts may share similar goals without being line-for-line equivalents. Migrate based on observable behavior rather than mechanically translating property names.

## 3. Mapping Command Key, Group Key, and Thread-Pool Key

In Hystrix, the command key identifies a command and is typically used to attach configuration and metrics. The group key groups commands by service area. The thread-pool key identifies the pool used by the command when running under THREAD isolation.

In Spring Cloud CircuitBreaker:

- id is the breaker instance name. Calls sharing the same id normally share that breaker's state and sliding window.
- groupName is supplementary metadata allowing the factory to resolve group configuration when supported by the implementation.
- ThreadPoolBulkhead has its own configuration and lifecycle; do not treat groupName as a thread-pool key.

For example, two operations that share an inventory policy but need separate statistics:

    CircuitBreaker readBreaker =
        circuitBreakerFactory.create("inventory-read", "inventory");

    CircuitBreaker reserveBreaker =
        circuitBreakerFactory.create("inventory-reserve", "inventory");

Two different ids create two independent breakers. Sharing a groupName can let them share a configuration policy, but it does not merge their CLOSED, OPEN, HALF_OPEN states or sliding windows.

When migrating from Hystrix, build a mapping table for each command:

| Legacy Command | Dependency | Legacy Isolation/Pool | New Breaker id | Configuration Group |
| --- | --- | --- | --- | --- |
| InventoryReadCommand | inventory-service | inventory-read-pool | inventory-read | inventory |
| InventoryReserveCommand | inventory-service | inventory-write-pool | inventory-reserve | inventory |
| PricingCommand | pricing-service | pricing-pool | pricing-quote | pricing |

The table above is only an example. Do not merge read and reserve into a single id just because they call the same service ID. Consider each operation's SLO, timeout, business errors, traffic volume, and fallback.

## 4. Mapping Circuit Breaker Thresholds

A typical Hystrix block contains properties such as:

    hystrix:
      command:
        inventory:
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000
          metrics:
            rollingStats:
              timeInMilliseconds: 10000
              numBuckets: 10

Resilience4j can express a corresponding policy as follows:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

Meaning of these fields:

- slidingWindowType selects a count-based or time-based window.
- slidingWindowSize is the number of samples for COUNT_BASED or the window size in seconds for TIME_BASED.
- minimumNumberOfCalls sets the minimum number of samples before calculating the failure rate.
- failureRateThreshold is the failure percentage that transitions the breaker to OPEN.
- waitDurationInOpenState is the wait time before allowing recovery probes.
- permittedNumberOfCallsInHalfOpenState limits the number of trial calls in HALF_OPEN.

Mapping points to watch carefully:

| Hystrix property | Resilience4j suggestion | Notes |
| --- | --- | --- |
| requestVolumeThreshold | minimumNumberOfCalls | Both relate to minimum sample count, but verify version and window semantics. |
| errorThresholdPercentage | failureRateThreshold | Roughly equivalent in percentage, though sample sets and exception recording must be verified. |
| sleepWindowInMilliseconds | waitDurationInOpenState | Convert units to duration; verify HALF_OPEN and automatic transition behavior. |
| metrics.rollingStats.timeInMilliseconds | slidingWindowType: TIME_BASED and slidingWindowSize | TIME_BASED takes the window size in seconds; do not simply convert units and assume buckets match Hystrix. |
| metrics.rollingStats.numBuckets | No direct equivalent in standard Resilience4j configuration | Resilience4j manages time-window buckets internally. |
| forceOpen / forceClosed | Special Resilience4j control states or configurations | Do not translate into fake thresholds; define proper operational procedures and management APIs. |

For instance, setting Hystrix requestVolumeThreshold to 20 does not always mean minimumNumberOfCalls must be 20. Check traffic volume, window type, and how Hystrix vs. Resilience4j count samples. A COUNT_BASED window of 20 with minimumNumberOfCalls of 10 starts evaluating after 10 calls, whereas legacy Hystrix parameters may behave differently in the running version.

## 5. Migrating Timeouts: More Than Renaming a Property

Hystrix can bound command execution time with:

    hystrix:
      command:
        default:
          execution:
            isolation:
              thread:
                timeoutInMilliseconds: 1000

In the new architecture, timeouts belong at the proper layer:

- HTTP client connect timeout bounds connection establishment time.
- HTTP response/read timeout bounds waiting for response data according to client capabilities.
- Resilience4j TimeLimiter bounds supported CompletionStage/Future executions.
- Reactor timeout bounds how long a publisher waits without emitting signals.
- CircuitBreaker slowCallDurationThreshold classifies slow calls; it does not cancel calls itself.

TimeLimiter example:

    resilience4j:
      timelimiter:
        instances:
          inventory-read:
            timeoutDuration: 1s
            cancelRunningFuture: true

TimeLimiter fits asynchronous tasks backed by Future or CompletionStage. It does not automatically turn a blocking method into a non-blocking one. If a synchronous client still runs on the request thread, offload it to a suitable executor and configure real timeouts on the HTTP client.

With WebClient, you can use Reactor timeout:

    Mono<InventoryResponse> request = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(1));

If using Resilience4j Reactor CircuitBreakerOperator, place timeout before the operator so the breaker observes TimeoutException, and place fallback after the operator:

    Mono<InventoryResponse> protectedRequest = request
        .timeout(Duration.ofSeconds(1))
        .transformDeferred(CircuitBreakerOperator.of(inventoryBreaker))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

A timeout on the caller does not guarantee the remote server stopped processing. For write operations such as reserving inventory or charging payments, verify idempotency and status lookup after a timeout.

## 6. Migrating THREAD and SEMAPHORE Isolation

Hystrix supports two common isolation strategies:

- THREAD: executes the command on a separate thread pool, isolating blocking tasks and limiting concurrency.
- SEMAPHORE: limits concurrent calls via a semaphore on the calling thread.

Resilience4j provides two Bulkhead types with comparable goals:

| Hystrix | Resilience4j | Behavior |
| --- | --- | --- |
| THREAD isolation | ThreadPoolBulkhead | Executes work in a dedicated pool with thread and queue limits. |
| SEMAPHORE isolation | SemaphoreBulkhead | Limits concurrent calls without switching to a separate pool. |

SemaphoreBulkhead configuration:

    resilience4j:
      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 20
            maxWaitDuration: 0

ThreadPoolBulkhead configuration:

    resilience4j:
      thread-pool-bulkhead:
        instances:
          inventory-read:
            coreThreadPoolSize: 4
            maxThreadPoolSize: 8
            queueCapacity: 20
            keepAliveDuration: 20ms

These numbers are illustrative. ThreadPoolBulkhead owns a dedicated pool and queue; SemaphoreBulkhead only issues permits. In the Spring Cloud CircuitBreaker Resilience4j integration, when resilience4j-bulkhead is on the classpath, Bulkhead may be applied automatically; the default type for synchronous calls is typically FixedThreadPoolBulkhead. The enableSemaphoreDefaultBulkhead property can select SemaphoreBulkhead as the default for synchronous calls. Reactive integration uses SemaphoreBulkhead.

Do not assume the new thread pool has the same naming, sizing, queue policy, or rejection behavior as Hystrix. Calculate total concurrency across all pods and the downstream service's limits. An 8-thread pool per pod across 10 pods can generate far higher concurrent load than an old Hystrix pool running on a single process.

If the application uses WebFlux, do not move non-blocking WebClient calls onto a thread pool simply because Hystrix previously used THREAD isolation. For legacy blocking APIs that cannot yet be replaced, offload them onto an appropriate scheduler/executor and apply a bulkhead to bound concurrency.

## 7. Migrating Fallbacks and Exception Handling

Hystrix typically declares fallbacks via getFallback(), fallbackMethod, or equivalent command mechanisms. With Spring Cloud CircuitBreaker, you can pass the fallback directly to run:

    InventoryResponse result = circuitBreakerFactory
        .create("inventory-read")
        .run(
            () -> inventoryClient.find(sku),
            error -> InventoryResponse.unknown(sku)
        );

With Feign, you can enable circuit breaker integration and use a fallback or FallbackFactory:

    @FeignClient(
        name = "inventory-service",
        fallbackFactory = InventoryFallbackFactory.class
    )
    public interface InventoryClient {
        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

FallbackFactory lets you inspect the Throwable that caused the failure and choose a response by root cause. At minimum, distinguish:

- Breaker OPEN: call rejected, typically CallNotPermittedException.
- Timeout: caller wait deadline expired; business outcome may be indeterminate.
- Bulkhead rejection: failed to acquire a permit or pool/queue is full.
- HTTP 5xx or connection failure: dependency may be unavailable.
- Business 4xx error: may represent a valid business outcome that does not necessarily require a fallback.

Hystrix and Resilience4j have different exception hierarchies. Do not keep catch blocks for HystrixRuntimeException and assume they will catch CallNotPermittedException or BulkheadFullException. Inspect the cause chain and classify exceptions according to your HTTP client and actual implementation.

Fallbacks must preserve business semantics. Do not return quantity = 0 to indicate inventory could not be queried, and do not return a fake success for a timed-out reservation request. Instead, return UNKNOWN, UNAVAILABLE, or PENDING along with an operation ID so the caller can query status.

Place the fallback outside the protected operation. If you catch exceptions inside the Supplier and return a normal value, the circuit breaker may record a success instead of a failure.

## 8. Translating Hystrix Configuration to Resilience4j

A legacy Hystrix configuration might look like:

    hystrix:
      command:
        default:
          execution:
            isolation:
              strategy: THREAD
              thread:
                timeoutInMilliseconds: 1000
          circuitBreaker:
            requestVolumeThreshold: 20
            errorThresholdPercentage: 50
            sleepWindowInMilliseconds: 10000
        inventory:
          execution:
            isolation:
              strategy: SEMAPHORE
              semaphore:
                maxConcurrentRequests: 15

The Resilience4j configuration can be organized into independent sections:

    resilience4j:
      circuitbreaker:
        configs:
          inventory-policy:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3
        instances:
          inventory-read:
            baseConfig: inventory-policy
          inventory-reserve:
            baseConfig: inventory-policy

      timelimiter:
        instances:
          inventory-read:
            timeoutDuration: 1s
            cancelRunningFuture: true

      bulkhead:
        instances:
          inventory-read:
            maxConcurrentCalls: 15
            maxWaitDuration: 0

The new configuration separates CircuitBreaker, TimeLimiter, and Bulkhead into independent policies. Do not put timeouts or concurrency settings under the circuitbreaker branch. If using ThreadPoolBulkhead, its configuration lives under resilience4j.thread-pool-bulkhead.instances.

A shared policy can be reused via baseConfig while each id keeps its own state and sliding window. This usually preserves shared operational targets without mixing statistics across different operations.

## 9. Hystrix Features Without a One-to-One Replacement

Migration is incomplete if you only port commands and thresholds. Inventory every Hystrix feature actually in use:

| Legacy Feature | Approach in the New Architecture |
| --- | --- |
| Hystrix Dashboard / Turbine | Export metrics via Micrometer/Actuator, scrape centrally with Prometheus, and build new dashboards. |
| Hystrix request cache | Design application caching with Spring Cache, Caffeine, or Redis; define keys and request scope explicitly. |
| Hystrix request collapser | Use batching, DataLoader, or API-level request aggregation; there is no automatic replacement in CircuitBreaker. |
| Hystrix concurrency strategy | Review context propagation via executors, TaskDecorator, Reactor Context, or Micrometer Context Propagation. |
| Hystrix command hooks/plugins | Use event publishers, customizers, observations, and interceptors suited to each integration. |
| Thread pool metrics | Monitor dedicated executors/ThreadPoolBulkhead along with queue depth, active threads, and rejections. |
| Hystrix properties | Translate each behavior into CircuitBreaker, TimeLimiter, Bulkhead, Retry, or HTTP client configuration. |

Do not preserve a legacy feature simply because a configuration file mentions it. Verify whether the code actually invokes request caches, collapsers, or plugins. If unused, they can be removed after verification. If used, they must be redesigned before removing the dependency.

## 10. Migrating Metrics and Alerts

Hystrix Dashboard typically focused on command metrics and thread-pool metrics. With Resilience4j, metrics can be exported through Micrometer when the appropriate dependencies and auto-configuration are enabled.

Metric groups to rebuild:

- CLOSED, OPEN, and HALF_OPEN states by breaker name.
- Counts of successful, failed, ignored, and rejected calls.
- Failure rate and slow call rate.
- Call duration and latency distribution.
- State transition counts and time spent in OPEN.
- Bulkhead active calls, rejected calls, queue depth, and thread-pool utilization.
- TimeLimiter timeouts and fallback rates.

Metric names and tags can vary across Resilience4j/Micrometer versions. Query the application's metrics endpoint or Prometheus after migration to confirm the exact names. Do not copy a Hystrix dashboard and merely rename series.

Keep breaker name, service, and pod as bounded dimensions. Avoid tagging by request ID, SKU, or exception message because cardinality grows rapidly. Use logs and traces with correlation IDs to investigate individual requests.

## 11. Step-by-Step Migration Plan

A safe migration should proceed per command or call group:

1. **Inventory:** list all HystrixCommand classes, command keys, group keys, thread-pool keys, properties, fallbacks, and metrics in use.
2. **Define boundaries:** choose breaker ids by dependency and operation; do not mix distinct business error profiles into the same window.
3. **Select implementation:** verify compatible Spring Cloud CircuitBreaker and Resilience4j starters for your Spring Boot/release train.
4. **Map policies:** move sliding window, failure threshold, wait duration, timeout, and bulkhead settings into their proper namespaces.
5. **Migrate code:** replace HystrixCommand with the factory or Feign integration; port fallbacks and exception mapping.
6. **Migrate observability:** build new metrics, events, dashboards, and alerts before retiring old dashboards.
7. **Test:** simulate success, HTTP 5xx, timeout, slow call, breaker OPEN, HALF_OPEN, bulkhead rejection, and fallback.
8. **Controlled rollout:** roll out to one service group or operation, monitoring latency, rejections, errors, and resource usage.
9. **Remove legacy config:** delete Hystrix dependencies/properties only after confirming no remaining code or profile uses them.
10. **Verify rollback:** retain previous deployment artifacts and configs for the agreed rollback window.

Do not enable two breaker layers simultaneously for the same call without an explicit design. Nested breakers can introduce two sliding windows, two timeouts, and two fallbacks, blocking requests at an unintended layer.

## 12. Post-Migration Test Matrix

| Scenario | Behavior to Verify |
| --- | --- |
| Dependency returns fast success | Primary result is returned; breaker records success. |
| Dependency returns HTTP 5xx | Exception is classified properly; fallback runs per policy; breaker records failure. |
| Dependency times out | Caller aborts at deadline; breaker observes timeout if configured to record it. |
| Slow call that still succeeds | Slow call rate increases; slow threshold is not confused with timeout. |
| Breaker OPEN | Supplier does not execute; call is rejected fast and appropriate fallback runs. |
| HALF_OPEN | Only the permitted number of trial calls execute; outcomes decide close or reopen. |
| Bulkhead full | Call is rejected per policy; distinguished from breaker OPEN. |
| Business error such as out-of-stock | Does not open the breaker if the exception is classified as an ignored business outcome. |
| Blocking work | Does not block the event loop; timeout and cancellation are verified at the client/executor layer. |
| Multiple pods | Local breaker states and metrics are aggregated properly without assuming shared state across JVMs. |

Beyond the final response, verify HTTP attempt counts, breaker states, fallback counts, tasks still running after timeout, and thread/queue utilization. A migration is only correct when operational behavior matches the intended design, not merely when the application compiles.

## 13. Hands-On Exercise: Migrating a Hystrix Command to Resilience4j

Suppose a legacy application has an InventoryCommand using THREAD isolation, a 1-second timeout, opening the circuit when failure rate reaches 50% after sufficient samples, and returning an UNKNOWN fallback.

**Part A — Record Legacy Behavior**

1. Document the command key, group key, thread-pool key, and all active properties.
2. Identify which endpoint the command calls and which errors count toward failure rate.
3. Measure concurrency, queueing, timeouts, fallbacks, and metrics in a test environment.
4. Check whether request cache, collapser, or a custom concurrency strategy is used.

**Part B — Create the New Configuration**

1. Add the compatible Spring Cloud CircuitBreaker Resilience4j starter.
2. Create the breaker id inventory-read.
3. Declare sliding window, minimumNumberOfCalls, failureRateThreshold, and waitDurationInOpenState.
4. Choose ThreadPoolBulkhead if blocking work needs isolation; choose SemaphoreBulkhead if only concurrency limiting is needed.
5. Configure an HTTP client timeout or TimeLimiter suited to the call type.
6. Register metrics and events for the new breaker.

**Part C — Migrate Code and Compare**

1. Replace HystrixCommand with CircuitBreakerFactory or Feign integration.
2. Move the UNKNOWN fallback outside the protected Supplier.
3. Verify timeout exceptions, HTTP errors, and business errors.
4. Simulate enough failures to OPEN the breaker; confirm subsequent calls do not hit the server.
5. Simulate recovery to confirm HALF_OPEN and CLOSED transitions.
6. Compare latency, throughput, concurrency, rejections, and fallbacks against the legacy system.
7. Confirm no leftover Hystrix request cache, collapser, or plugins were overlooked.

Upon completion, you should be able to explain why Hystrix properties do not automatically apply to Resilience4j, how id differs from groupName, how timeout differs from slow-call threshold, and why THREAD isolation must be redesigned using executors or ThreadPoolBulkhead. Complete your inventory and behavioral tests before deleting legacy configuration.

## References

- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html
- Spring Cloud CircuitBreaker — Reference: https://docs.spring.io/spring-cloud-circuitbreaker/reference/index.html
- Resilience4j — CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Bulkhead: https://resilience4j.readme.io/docs/bulkhead
- Resilience4j — TimeLimiter: https://resilience4j.readme.io/docs/timeout
