# Distinguishing Load Balancing, Retry, and Circuit Breaker

In a microservices system, a request from **Order Service** to **Inventory Service** can fail because an instance just stopped, a transient network error occurred, response time is too long, or the entire service is overloaded. Three mechanisms that commonly appear together in Spring Cloud are **client-side load balancing**, **retry**, and **circuit breaker**. All three relate to fault tolerance, yet they **answer three different questions**:

- **Load balancing:** *Which ServiceInstance should this call be sent to?*
- **Retry:** *After a recoverable error, should the call be attempted again?*
- **Circuit breaker:** *Based on recent errors, should calls to this dependency continue to be allowed?*

One mechanism cannot replace another. LoadBalancer may pick the right instance while the backend still returns 503; retry may switch instances yet cannot save a completely failed service; a circuit breaker can protect the caller by failing fast, but on its own it **does not find a new instance and does not retry automatically**.

This lesson presents the roles, composition order, recovery scenarios, and how to apply them to **RestClient, RestTemplate, WebClient, and OpenFeign** with Spring Cloud LoadBalancer. It also clarifies the differences between a circuit breaker, **timeout**, **bulkhead**, **fallback**, and **health check** to design reliable inter-service communication.

> **Scope:** APIs and properties are illustrated according to current Spring Cloud Commons/LoadBalancer, Spring Cloud CircuitBreaker, and Resilience4j. Configuration values are examples that must be tuned to your project's SLOs and Spring Boot–Spring Cloud BOM. In Spring Cloud, **enabling a retry property does not mean every client and every HTTP method will automatically be retried**; it still depends on dependencies, filters, and the integration path.

## 1. Where Do the Three Mechanisms Sit in the Call Flow?

Suppose Order Service calls a logical URI:

~~~http
GET http://inventory-service/api/stock/BOOK-01
~~~

Discovery provides the instances:

| Service ID | Instance ID | Host/port | Illustrative status |
| --- | --- | --- | --- |
| inventory-service | inventory-a | 10.20.0.11:8080 | UP |
| inventory-service | inventory-b | 10.20.0.12:8080 | UP but slow |
| inventory-service | inventory-c | 10.20.0.13:8080 | Transient connection errors |

The flow below describes an **intentional design**, not the automatic ordering of every Spring Cloud application:

~~~mermaid
flowchart TD
    A["Order Service wants to read inventory"] --> B{"Does the circuit breaker allow it?"}
    B -->|OPEN, rejected| C["Fail fast / controlled fallback"]
    B -->|CLOSED or HALF_OPEN probe| D["LoadBalancer selects ServiceInstance"]
    D --> E["Send HTTP request to an instance"]
    E --> F{"Result"}
    F -->|Success| G["Return response and record success"]
    F -->|Non-retryable error| H["Report error, record outcome"]
    F -->|Retryable error| I{"Attempts and deadline remaining?"}
    I -->|Yes| D
    I -->|No| H
    G --> J["Circuit breaker updates statistics"]
    H --> J
~~~

In this diagram, the circuit breaker wraps **one logical call** that may consist of multiple attempts, so it sees the final outcome. If the circuit breaker is placed **inside retry**, it can record each attempt and transition to OPEN earlier. Both approaches can be valid, but you must choose based on your error-measurement and downstream-protection goals.

### 1.1. Three Different Design Axes

| Mechanism | Core decision | Input data | Action |
| --- | --- | --- | --- |
| LoadBalancer | Choose *target* | ServiceInstance list, zone/hint/health/metadata | Select instance and reconstruct URI |
| Retry | Should it *repeat*? | Exception/status, HTTP method, attempts, deadline | Resend the same operation, possibly re-selecting an instance |
| Circuit breaker | Should it *allow*? | Error/slow-call statistics, breaker state, thresholds | Pass through, allow limited probes, or reject immediately |

**LoadBalancer chooses where to send; retry decides whether to send again; circuit breaker decides whether sending is still permitted.**

## 2. Load Balancing: Distributing Traffic, Not Automatically Recovering Every Error

In Spring Cloud LoadBalancer, **ServiceInstanceListSupplier** provides the list of instances by service ID. The supplier chain can use discovery, caching, health checks, zone preference, hints, or retry-aware filters. **RoundRobinLoadBalancer** or **RandomLoadBalancer** selects from the final list.

~~~text
Order Service
   |
   | logical URI: inventory-service
   v
ServiceInstanceListSupplier -> [A, B, C]
   |
   | Round Robin / Random
   v
ServiceInstance B
   |
   v
HTTP http://10.20.0.12:8080/api/stock/BOOK-01
~~~

LoadBalancer handles:

1. Resolving the **service ID** from the logical URI.
2. Retrieving the instance list from the supplier.
3. Applying configured ordering/filtering policies.
4. Selecting one ServiceInstance.
5. Reconstructing the physical URI while preserving the appropriate path, query, and scheme.

However, it **does not automatically guarantee**:

- That the chosen instance will respond successfully.
- That an HTTP 503 will be resent to another instance.
- That any instance will be removed immediately when a single request fails.
- That an overloaded backend will recover merely by changing the selection algorithm.
- That a write request can be safely resent.

### 2.1. Instance Health Differs from Request Outcome

Discovery/HealthCheck may evaluate an instance as UP and keep it in the list. However, a specific endpoint can return 500 while the health endpoint still returns 200. Conversely, a request that times out does not necessarily mean the instance is dead; it may simply be a slow query.

**Health-check supplier** provides recent candidate status; **circuit breaker** evaluates the sequence of outcomes for calls within the scope you wrap with it. These two perspectives complement each other, but they are not equivalent.

### 2.2. Having No Instances Does Not Mean the Circuit Breaker Is OPEN

If the supplier returns **[]**, LoadBalancer cannot select a target. That is an input discovery/availability failure, not evidence that the circuit breaker is OPEN. Diagnose the registry, cache, health filter, service ID, and metadata before changing circuit breaker thresholds.

## 3. Retry: Repeating After a Classified Error

Retry is a policy for **trying again** after an error that the system classifies as recoverable. A logical call can consist of an initial attempt and one or more retries (**attempts**).

~~~text
Attempt 1:  choose A -> connection reset
Backoff:    100 ms
Attempt 2:  choose B -> HTTP 200
Result:     success after 2 attempts
~~~

Retry can execute on:

- **The same ServiceInstance**, when the error is expected to be transient.
- **A different ServiceInstance**, when you want to avoid the instance that just failed.
- **Another HTTP client or application wrapper**, depending on where retry is configured.

**Important:** retry only changes the number of sends; re-selecting an instance depends on the LoadBalancer mechanism and retry context. A Reactor/Resilience4j retry can re-subscribe to the HTTP call, yet **does not inherently guarantee the second attempt goes to B**. To verify, inspect the URI/instance ID of each attempt.

### 3.1. When Should You Retry?

| Call outcome | Is retry usually appropriate? | Reason |
| --- | --- | --- |
| TCP connection reset before response | Possibly | Transient network error, though write requests still require idempotency |
| Connect timeout | Possibly | Temporary instance or network issue |
| HTTP 502/503/504 | Possibly | Downstream/gateway unavailable; requires backoff and limits |
| HTTP 429 | Possibly | Respect Retry-After and rate limits |
| HTTP 400/422 | Usually no | Invalid payload; resending identically rarely fixes it |
| HTTP 401/403 | Usually no | Missing permissions; do not retry blindly |
| HTTP 404 | Usually no | The resource may genuinely not exist |
| HTTP 409 | Domain-dependent | May need to read fresh state rather than resending identically |
| JSON schema decode error | No | Contract mismatch; retrying just adds load |
| Circuit breaker OPEN | No | Intentionally rejected; repeated retries cause a storm |

Do not hardcode "retry every 5xx" if the request has side effects. You must consider **HTTP method, idempotency, server contract, deadline, and downstream load**.

### 3.2. Backoff, Jitter, and Attempt Limits

A complete retry policy needs:

- **max attempts**: maximum number of transmissions.
- **retryable status/exceptions**: explicit conditions.
- **backoff**: pause interval between attempts.
- **jitter**: randomizing the wait interval so callers do not retry simultaneously.
- **overall deadline**: time limit for the *logical call*, including attempts and backoff.
- **retry budget**: limit on retry traffic relative to baseline traffic.

Example with **one** retry:

~~~text
Attempt 1: 350 ms -> 503
Backoff:   100 ms
Attempt 2: 420 ms -> 200
------------------------
Total:     870 ms
~~~

If the Request SLA is only 700 ms, that policy exceeds the budget even though the second attempt succeeds. Timeout **per attempt** is not the **total deadline**.

### 3.3. Retry Can Amplify Overload

Suppose Inventory receives 1,000 requests/second; every request returns 503, and callers are configured with up to 3 attempts (1 initial + 2 retries). If all callers retry up to the limit, Inventory can receive **3,000 attempts/second**. If the Gateway layer also retries 3 times, actual load can reach **9,000 attempts/second** due to cascading multiplication, depending on how wrappers are applied.

Prevent retry storms using backoff/jitter, deadlines, small attempt counts, concurrency limits, and circuit breakers. **Retry is not a free way to increase availability**.

## 4. Circuit Breaker: Breaking the Call Path on Repeated Failures

A circuit breaker tracks call outcomes under **a breaker identifier key** such as inventory-read. When the failure rate or slow-call rate exceeds the configured threshold, it transitions to **OPEN** to **reject new calls** without continuing to load the downstream service.

In Resilience4j, there are three common states:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN : Failure/slow-call rate exceeds threshold
    OPEN --> HALF_OPEN : Wait duration elapsed and probe triggered
    HALF_OPEN --> CLOSED : Probes meet criteria
    HALF_OPEN --> OPEN : Probes continue failing/slow
~~~

| State | Behavior | Impact on backend |
| --- | --- | --- |
| **CLOSED** | Lets requests pass through; records success/failure/slow calls | Backend continues receiving traffic |
| **OPEN** | Rejects most new calls fast, typically throwing CallNotPermittedException | Backend load from that caller is relieved |
| **HALF_OPEN** | Permits a limited number of probes to measure recovery | Backend receives a controlled amount of test traffic |

Resilience4j also has special states such as **DISABLED, FORCED_OPEN, METRICS_ONLY**; these are not part of the normal recovery lifecycle and must be used intentionally.

### 4.1. A Breaker Is Not a Backend

Suppose a circuit breaker named **inventory-read** wraps all calls to service ID inventory-service. If A fails while B/C remain healthy, a single breaker can open and block the chance to pick B/C as well. This is a consequence of **breaker statistical scope**.

There are two ways to scope a breaker:

- **Per dependency / operation**: for example inventory-read, aggregating outcomes across all instances for an operation; simple, protects the caller during a full downstream outage.
- **Per instance**: creating a breaker per instance ID/host to isolate individual faulty instances; harder to manage lifecycle as instances churn and must avoid unbounded cardinality growth.

In most systems, start by scoping breakers **per service or operation**; use health-aware selection/retry to handle individual faulty instances. Only build per-instance breakers when truly required, with stable identity data and proper breaker cleanup.

**The circuit breaker does not read ServiceInstanceListSupplier to remove an instance from the registry.** It wraps a defined call, which may sit above or below instance selection depending on your architecture.

### 4.2. The Breaker Records Failures by Policy, Not Every 4xx by Default

Resilience4j evaluates errors based on **exceptions**, results (if converted into errors by an adapter), thresholds, and predicates such as **recordExceptions**, **ignoreExceptions**, or recordFailurePredicate. If the HTTP client does not throw an exception for HTTP 503, the breaker may record a success even though the business logic treats it as a failure.

For example:

- HTTP 404 because a SKU does not exist may be a **valid domain result** and should not open the breaker.
- HTTP 503 due to server overload is usually worth recording as a failure.
- Timeouts and connection resets are usually worth recording, provided the underlying error has not been swallowed by a fallback.
- A caller validation error should not cause all of Inventory to be marked unhealthy.

The error-classification policy must be placed explicitly at the HTTP adapter and breaker layer. **A fallback returning a success value inside the breaker can hide the original error from it**, leading to inaccurate metrics.

## 5. A Circuit Breaker Is Not a Bulkhead, Timeout, or Rate Limiter

These concepts can appear in the same Resilience4j library:

| Mechanism | Primary question | Example |
| --- | --- | --- |
| **LoadBalancer** | Which instance to send to? | Pick Inventory B |
| **Retry** | Should it send again? | Try B after A fails |
| **Circuit breaker** | Should the next call be allowed? | OPEN: reject new requests |
| **Bulkhead** | How many concurrent executions are allowed at most? | Max 20 in-flight Inventory calls |
| **Timeout / TimeLimiter** | How long to wait at most? | 800 ms per attempt or 1.5 s for the whole call |
| **RateLimiter** | How many requests are allowed per unit time? | 100 requests/second |
| **Fallback** | What result to return when execution fails? | Read inventory from cache with a stale label |
| **Health check** | Is the instance currently considered available? | Exclude C from candidate list |

**A CLOSED circuit breaker can allow thousands of concurrent requests through.** The breaker's sliding window size is the statistical sample count, **not a limit on concurrent requests**. If you need concurrency limits to protect thread/connection pools, use a **bulkhead**, pool limits, or backpressure.

### 5.1. Circuit Breaker Differs from Timeout

A circuit breaker collects *outcome history* to decide whether to permit new requests. A timeout is a *time limit* on a request or phase.

If the backend hangs for 60 seconds and the client has no timeout, the circuit breaker will not necessarily open early: it needs the call to finish or be reported as slow/failed according to its recording rules. Therefore, you need timeouts (and potentially TimeLimiter) so slow calls are terminated/classified.

Conversely, timeout=500 ms does not create an **OPEN/HALF_OPEN** mechanism on its own. It only limits waiting for a single call, without remembering failure rates for subsequent calls.

### 5.2. Spring Cloud CircuitBreaker TimeLimiter Has Separate Configuration

When integrating Spring Cloud CircuitBreaker with Resilience4j, alongside CircuitBreakerConfig there is **TimeLimiterConfig**. Current documentation allows declaring:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory-read:
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

TimeLimiter may be **enabled by default in the Spring Cloud CircuitBreaker integration**. Do not confuse it with HTTP transport connect/read timeouts. With synchronous HTTP clients, canceling a Future or timing out at the wrapper layer **does not guarantee immediately closing** a waiting socket and does not roll back server-side transactions.

With reactive WebClient, cancellation is typically propagated down to the Publisher, though actual connection closure/network I/O cancellation still depends on the connector and request timing. Verify this with slow-network tests.

### 5.3. Bulkhead Isolates Resources; Breaker Isolates Traffic by State

Example:

~~~text
inventory-service is responding slowly without failing yet:

Without bulkhead:
  hundreds of requests can hold connections, threads/buffers and overload Order

With bulkhead:
  at most 30 concurrent Inventory requests
  excess requests are rejected/queued in a controlled way

With circuit breaker:
  once errors/slow calls exceed threshold, new requests fail fast
~~~

The two mechanisms complement each other. With Spring Cloud CircuitBreaker Resilience4j, if the bulkhead module is on the classpath, **bulkhead integration may be applied automatically**; choosing between semaphore and thread-pool bulkhead depends on version/configuration. Verify this when measuring latency and thread usage.

## 6. Same Failure, Three Different Reactions

### 6.1. Instance A Dies, B Is Healthy

~~~text
Discovery: [A, B]
First attempt: LoadBalancer picks A
Result: connection refused
Retry policy: retry once, re-select instance
Second attempt: LoadBalancer picks B -> 200
Per-service breaker: sees final outcome as success if wrapping retry
~~~

Here **LoadBalancer + retry** can recover. The breaker does not necessarily need to OPEN just because A failed once. However, if retry lacks context to avoid A, the second attempt **might pick A again**.

### 6.2. Both A and B Return 503 for an Extended Period

~~~text
Attempt 1: A -> 503
Attempt 2: B -> 503
Attempt 3: A/B -> 503
Breaker records failure
Enough samples + threshold exceeded => OPEN
Subsequent request => fails fast, not sent to Inventory
~~~

When the entire downstream fails, **retrying multiple times only increases load**. The circuit breaker prevents the caller from continuously worsening the outage and can protect threads/pools.

### 6.3. Inventory Is Healthy, but Order Runs Out of Threads

~~~text
Inventory: HTTP 200, latency 1,500 ms
Order: 500 concurrent requests, connection pool only has 30
Acquire queue grows, threads are held
~~~

LoadBalancer can still pick the right instance. Retry can increase load further. The breaker only opens when outcome/slow-call policies meet their thresholds. **Bulkhead, pool-acquire timeout, and overall deadline** are the direct tools to isolate resources in this scenario.

### 6.4. Business Errors 404/409

If Inventory returns 404 because a SKU does not exist or 409 due to optimistic locking, switching instances will not fix the error. Retrying 404/409 verbatim and recording them as outages can distort breaker statistics. Classify by the API contract first.

## 7. Ordering Composition: Breaker Outside or Inside Retry?

**Decorator order determines what the circuit breaker measures.**

### 7.1. Circuit Breaker Outside Retry: Measuring the Logical Call Outcome

~~~text
CircuitBreaker(
    Retry(
        LoadBalancerChooseAndHttpCall()
    )
)
~~~

If A fails first and B succeeds next, the outer breaker can record **one success** for the entire logical call (though total latency may be high). This makes sense when the breaker protects an *operation* and you want to evaluate the final outcome of that operation.

Advantage: transient errors recovered by retry do not immediately push the breaker toward OPEN. Risk: multiple failed attempts may still collapse into one failure; actual requests hitting the backend exceed breaker call counts. Track **attempt metrics separately**.

### 7.2. Retry Outside Circuit Breaker: Measuring Each Attempt

~~~text
Retry(
    CircuitBreaker(
        LoadBalancerChooseAndHttpCall()
    )
)
~~~

If A fails twice and B succeeds, the breaker can record **two failures and one success**. It opens faster when many attempts fail, but if the breaker is OPEN and the outer retry still retries **CallNotPermittedException**, the system generates useless rejections.

You must configure retry **not to retry CallNotPermittedException**, and decide whether the retry policy should stop completely when the breaker is OPEN. Do not confuse wrapper notation order with execution order during failure evaluation.

### 7.3. AOP Annotations Do Not Default to the Same Order as Reactor Operators

Resilience4j has both annotation/AOP and functional decorators. Resilience4j documentation describes a typical default annotation aspect order like **Retry(CircuitBreaker(RateLimiter(TimeLimiter(Bulkhead(function)))))**. If you compose Reactor operators or Spring Cloud factories manually, the order is determined by **your code** and may differ substantially.

Do not conclude that all projects share the same order simply because they declare **@Retry and @CircuitBreaker**. Inspect the actual configuration, aspect order, method proxying, and auto-configured wrappers.

**An often-overlooked note:** Spring Cloud LoadBalancer has its own retry mechanism; if you also place Resilience4j @Retry or Reactor retryWhen outside it, **nested retries** can occur. That affects both attempt counts and circuit breaker statistics.

## 8. Budget Calculation Example: A Breaker Does Not Replace a Deadline

Suppose Order API must complete within **1,800 ms**. You design:

| Item | Illustrative limit |
| --- | ---: |
| Instance selection/lookup | 50 ms |
| Connect + response per attempt | 600 ms |
| Backoff between attempts | 100 ms |
| Max retries | 1 |
| Domain processing + response | 150 ms |
| Overall call deadline | 1,800 ms |

Two attempts may take:

~~~text
T ~= 50 + 600 + 100 + 600 + 150 = 1,500 ms
~~~

If network jitter, pool acquisition, or decoding adds 400 ms, the total can exceed **1,800 ms** even though each attempt timeout is set to 600 ms. Therefore, you need an **overall deadline** wrapping retry/backoff, not just transport connect/read timeouts.

A breaker can open and fail fast in a few milliseconds, yet **it does not replace deadlines** for requests that are permitted through. SLOs must be protected with timeouts, retry budgets, and resource limits, then combined with a breaker.

## 9. Where Is the Boundary of Fallback?

**Fallback is how the application handles being unable to obtain a result from downstream**, not a default LoadBalancer feature. Spring Cloud CircuitBreaker provides an API accepting a fallback function, but that callback must respect the domain contract.

Inventory read example:

~~~text
Inventory online:  STOCK=7 (fresh)
Inventory error:   STOCK=7 (cached, stale=true, cacheAge=10s)
~~~

If the application has a read-only cache built to tolerate stale data, such a fallback **may** be useful. You must return freshness metadata rather than disguising it as live data.

Conversely:

~~~text
POST /reservations times out
Fallback: return success even though whether the backend committed is unknown
~~~

This is a **serious business bug**. Never treat "unknown outcome" as "successfully reserved"; you need an idempotency key, operation-status API, or a pending/unknown state for reconciliation.

### 9.1. Do Not Fall Back on Every Exception

A fallback that "returns cache for all errors" can hide:

- 401/403: misconfigured authentication.
- 400/422: invalid request.
- 404: SKU genuinely does not exist.
- 409: state conflict.
- NullPointerException: caller programming bug.

Only fall back on appropriate error classes such as downstream unavailable, breaker OPEN, or a confirmed subset of timeouts. Record the degraded state and monitor **fallback usage**, not only aggregate HTTP 200 responses.

## 10. Which Layer Should Own Which Responsibility?

A maintainable design can be divided as follows:

| Layer | Responsibility |
| --- | --- |
| Domain Service | Select business-appropriate recovery policy; decide whether stale/cached results are acceptable |
| HTTP Adapter | Map HTTP statuses, exceptions/timeouts, and DTOs into stable domain results |
| Spring Cloud LoadBalancer | Obtain ServiceInstance list, select physical URI |
| Retry policy | Define retry conditions, attempts, backoff/jitter, deadline |
| Circuit breaker | Measure selected outcomes and control CLOSED/OPEN/HALF_OPEN |
| Bulkhead/RateLimiter | Isolate concurrency and request rate |
| Observability | Track instance, attempt, outcome, breaker state, fallback, latency |

Avoid a single service method that manually invokes DiscoveryClient, loops with while(true) for retries, toggles a boolean circuitOpen flag, and returns fallbacks inline. Mixing responsibilities makes it hard to verify **when requests were actually sent**, **how many times**, and **why they were rejected**.

## 11. Configuring Retry in Spring Cloud LoadBalancer

Spring Cloud LoadBalancer supports retry depending on integration path, HTTP client, classpath, and release train. An illustrative configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false
        retry-on-all-exceptions: false
        retryable-status-codes:
          - 503
        backoff:
          enabled: true
          min-backoff: 100ms
          max-backoff: 500ms
          jitter: 0.3
~~~

Meaning:

| Property | Intent |
| --- | --- |
| retry.enabled | Enables retry support when required components are present |
| max-retries-on-same-service-instance=0 | Do not configure retries on the same selected instance |
| max-retries-on-next-service-instance=1 | Allow at most one retry along the next-instance selection path |
| retry-on-all-operations=false | Do not broadly enable retries for all HTTP methods |
| retryable-status-codes=[503] | Specify status codes eligible for retry |
| backoff.enabled | Enable retry wait interval on supported reactive paths |
| min/max-backoff, jitter | Control wait intervals and avoid synchronized retries |

**Warning:** Blocking **RestTemplate** retry requires a compatible **Spring Retry** version on the classpath; reactive WebClient integration uses Reactor retry mechanisms and corresponding supporting configuration. OpenFeign has its own default retryer; do not assume the same YAML block above automatically governs all Feign clients.

Additionally, **retry.enabled** does not automatically allow retrying every error or every write operation. Inspect **retryable-exceptions, status codes, HTTP method, and retry policy**, and write integration tests verifying actual attempt counts.

### 11.1. Avoiding the Previously Failed Instance on Retry

**RetryAwareServiceInstanceListSupplier** can prioritize excluding the previous instance from the list when alternatives exist. The property **spring.cloud.loadbalancer.retry.avoid-previous-instance** relates to applying this decorator; defaults and activation conditions depend on dependencies/configuration.

Suppose the list before retry is:

~~~text
Attempt 1: [A, B, C]  -> pick A -> fail
Attempt 2: [B, C]     -> chance to pick B or C
~~~

However, if the list after health/zone/hint filtering only contains **[A]**, retry-aware cannot invent instances B or C. Moreover, **retrying on the next instance does not guarantee a different instance** when no alternative candidates exist or when retry context is not propagated properly.

Do not call avoiding the previous instance a **per-instance circuit breaker**. It is a preference filter during candidate selection, not a state machine that tracks failure rates or has OPEN/HALF_OPEN states like a circuit breaker.

### 11.2. Retry Behavior Differs Across HTTP Clients

| Client | Execution path | Points to verify |
| --- | --- | --- |
| RestTemplate | BlockingLoadBalancerClient, Spring Retry when integrated | Spring Retry dependency, status/exception policy |
| RestClient | Blocking LoadBalancer integration | Retry support per release train/interceptor in use; do not infer from RestTemplate config |
| WebClient | ReactorLoadBalancerExchangeFilterFunction / retry-aware filter when present | Auto-configured filters, Reactor retry, backoff, cancellation |
| OpenFeign | FeignBlockingLoadBalancerClient and Feign retryer | Feign Retryer, separate policy, circuit-breaker wrapper |

According to Spring Cloud OpenFeign documentation, the default bean is **Retryer.NEVER_RETRY**, unlike Feign core's default behavior. Therefore, to enable Feign retry, you must explicitly configure a Retryer/custom configuration and not assume from the service ID that Feign retries automatically.

**Count actual requests at the backend**, not only Java method invocations. Retries inside filters or transport layers can send multiple HTTP attempts even though the business method is invoked once.

## 12. Adding Spring Cloud CircuitBreaker with Resilience4j

Spring Cloud CircuitBreaker provides a circuit breaker abstraction. A widely used implementation is **Resilience4j**.

Illustrative Gradle dependencies with compatible Spring Boot BOM and Spring Cloud BOM:

~~~gradle
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    // Synchronous applications (RestClient / RestTemplate):
    implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")

    // For reactive applications (WebClient), use the reactive starter instead of
    // the synchronous starter when appropriate:
    // implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j")
}
~~~

These examples do not require adding both CircuitBreaker starters to the same application. Choose the starter matching your stack and avoid redundant dependencies. A circuit breaker is not added automatically just because the application includes **spring-cloud-starter-loadbalancer**.

### 12.1. Configuring a Breaker with Clear Thresholds

Resilience4j configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

This is an **illustrative** policy, not a universal recommendation. It means:

- Up to the **last 20 calls** are evaluated in a count-based sliding window.
- At least **10 calls** must be recorded before evaluating failure/slow-call rate thresholds.
- A failure rate of **50% or higher** can open the breaker.
- A slow-call rate of **60% or higher**, with slow calls taking longer than **800 ms**, can also open it.
- Once OPEN for 5 seconds, the circuit can transition to HALF_OPEN when checked/triggered according to automatic transition policy; a background thread is not required by default.
- In HALF_OPEN, **3 probe calls** are allowed to decide whether to return to CLOSED or OPEN.

**Important:** The circuit breaker computes statistics on what the **decorated operation** returns. If an inner operation retried and succeeded, the outer breaker sees one success. If a 404 has not been mapped to an appropriate domain result/exception, it may be counted under recordExceptions policy.

### 12.2. Name Breakers by Operation, Not by Host/Port by Default

Example names:

~~~text
inventoryRead
inventoryReserve
paymentCapture
catalogSearch
~~~

Endpoints with completely different characteristics (cached GET read, POST inventory reservation, payment call) should not share one breaker and fallback by default. Conversely, if you create a new breaker per **request ID**, you will never accumulate enough samples to evaluate state.

Choose a breaker key that is **stable across requests for the same operation**, avoiding high-cardinality keys based on user ID, SKU, session ID, trace ID, or ephemeral instance IDs.

## 13. Blocking Example: RestClient + LoadBalancer + CircuitBreaker

A minimal HTTP client configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

An adapter using a circuit breaker for a **read operation**:

~~~java
@Service
class InventoryReader {

    private final RestClient client;
    private final CircuitBreakerFactory<?, ?> breakers;

    InventoryReader(
            @LoadBalanced RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> breakers) {
        this.client = builder.baseUrl("http://inventory-service").build();
        this.breakers = breakers;
    }

    StockResponse read(String sku) {
        return breakers.create("inventoryRead").run(
                () -> client.get()
                        .uri("/api/stock/{sku}", sku)
                        .retrieve()
                        .body(StockResponse.class),
                error -> {
                    // Demo: translate error into a domain exception rather than
                    // returning fake stock counts when Inventory is unavailable.
                    throw new InventoryUnavailableException(
                            "Inventory read unavailable", error);
                });
    }
}
~~~

This snippet assumes **StockResponse** and **InventoryUnavailableException** are defined by the application, a **CircuitBreakerFactory** bean has been created by the starter, and the client has a discovery source for inventory-service. In production code, check for null bodies and classify 404/409/5xx before translating to domain exceptions.

**Notable limitation:** the fallback function in this example only **throws a domain exception** and does not perform retries. If retry is desired, configure LoadBalancer retry or another retry wrapper and decide whether it sits inside or outside the breaker.

### 13.1. Do Not Apply Fallback Uniformly to 404

The example above is intentionally simplified, so 404 is also mapped to InventoryUnavailableException. In a real system, a 404 meaning SKU not found may need:

~~~java
try {
    return reader.read(sku);
} catch (StockNotFoundException ex) {
    return Optional.empty();
}
~~~

A cleaner approach is for the **HTTP adapter** to map 404 to a domain result or an exception that the breaker is configured to **ignore**, so the breaker only records infrastructure failures as intended.

**Do not copy this demo as a final production error mapping.** The example's purpose is to illustrate where to wrap a circuit breaker around a load-balanced RestClient.

## 14. Reactive Example: WebClient + ReactiveCircuitBreakerFactory

WebClient is a non-blocking HTTP client; you should not call **block()** to wrap it with a synchronous circuit breaker on a WebFlux request thread. Spring Cloud provides **ReactiveCircuitBreakerFactory** for Mono/Flux.

~~~java
@Service
class ReactiveInventoryReader {

    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakers;

    ReactiveInventoryReader(
            @LoadBalanced WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> breakers) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
        this.breakers = breakers;
    }

    Mono<StockResponse> read(String sku) {
        Mono<StockResponse> source = webClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);

        return breakers.create("inventoryRead").run(
                source,
                error -> Mono.error(new InventoryUnavailableException(
                        "Reactive inventory read unavailable", error)));
    }
}
~~~

This pattern aligns with the **Spring Cloud Circuit Breaker** documentation: a ReactiveCircuitBreaker wraps a Mono/Flux and accepts a fallback function to optionally handle errors. Each subscription can trigger an actual request, so when adding retry you must decide **where to place the retry operator**.

### 14.1. Retry Inside or Outside the Reactive Breaker?

Suppose you have a **cold Mono** performing an HTTP request:

~~~java
Mono<StockResponse> source = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

Order A: retry happens before the breaker observes the final outcome:

~~~java
Mono<StockResponse> withRetry = source.retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));

Mono<StockResponse> protectedCall =
        breakers.create("inventoryRead").run(withRetry);
~~~

Order B: the breaker observes each subscription of source, while retry sits outside:

~~~java
Mono<StockResponse> protectedAttempt =
        breakers.create("inventoryRead").run(source);

Mono<StockResponse> retryOutside = protectedAttempt.retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));
~~~

**Why filter on 503?** It prevents the retry operator from re-invoking every error type, especially **CallNotPermittedException**, auth failures, or schema decode errors. The two snippets only illustrate ordering; when Spring Cloud LoadBalancer also retries automatically, **disable one layer or account for both**.

The corresponding Reactor imports are **reactor.core.publisher.Mono**, **reactor.util.retry.Retry**, and **java.time.Duration**. ReactiveCircuitBreakerFactory belongs to the Spring Cloud CircuitBreaker API and WebClientResponseException belongs to Spring WebFlux.

### 14.2. TimeLimiter Can Change the Outcome

If ReactiveCircuitBreakerFactory also applies a TimeLimiter per configuration, the Mono may time out before some retries finish. Therefore, inspect **HTTP connector timeouts**, **TimeLimiter**, **Reactor timeout operators**, and the **overall deadline** together. When multiple timeout layers exist, the error received reflects whichever timer fires first.

Do not set TimeLimiter to 200 ms and configure two retries with a 2-second response timeout each; most retries will never have a chance to complete, making the configuration confusing.

## 15. OpenFeign: Load Balancing and Circuit Breaker Are Two Separate Integrations

Spring Cloud OpenFeign can use:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

With **spring-cloud-starter-loadbalancer** present, Feign can resolve the service ID via LoadBalancer instead of a fixed URL. To wrap Feign methods with Spring Cloud CircuitBreaker, add the corresponding CircuitBreaker implementation and enable:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Current OpenFeign documentation states that **spring.cloud.openfeign.circuitbreaker.enabled** defaults to **false**, so you cannot assume "using Feign + LoadBalancer automatically enables a circuit breaker." Breaker names can derive from interface/method names and can be customized via CircuitBreakerNameResolver.

### 15.1. Feign Retry Is Not Enabled by Default Like Feign Core

Spring Cloud OpenFeign creates **Retryer.NEVER_RETRY** by default. Feign core has its own retry behavior, but Spring Cloud overrides it during integration. If you need Feign retry, declare a Retryer and safe conditions deliberately.

When you have:

- Feign retry,
- Spring Cloud LoadBalancer retry,
- CircuitBreaker wrapper,
- Service mesh/proxy retry,

you must inspect the actual HTTP attempt count and application order. A single Java call can generate many requests if multiple retry layers are stacked.

### 15.2. Feign Fallback Must Understand Error Types

Spring Cloud OpenFeign supports fallback/fallbackFactory when circuit breaker integration is used. However, a fallback returning **StockResponse(sku, 0)** for all errors is dangerous: 0 may be interpreted as definitely out of stock rather than **unknown because the system is failing**.

A better contract is:

~~~text
StockQueryResult:
  status = FRESH / STALE / UNAVAILABLE
  available = 7 (present only when source is valid)
  observedAt = ...
~~~

For operations like **capture payment, place order, reserve stock**, a fallback must never fabricate success or an unverified result. It can return **PENDING_RECONCILIATION** per the business contract and use an operation ID to check later.

## 16. Which Exceptions Should the Circuit Breaker Distinguish?

| Error group | Source | Should record as breaker failure? | Should retry? |
| --- | --- | --- | --- |
| HTTP 503 backend | Server/gateway | Usually yes | Possibly, bounded |
| HTTP 502/504 gateway | Proxy | Usually yes | Possibly, bounded |
| Connection refused/reset | HTTP transport | Usually yes | Possibly |
| Connect/read timeout | HTTP transport/TimeLimiter | Usually yes | Careful with side effects |
| ResourceAccessException/WebClientRequestException | Spring client | Classify by root cause | Depends on cause/method |
| HTTP 429 | Rate limiting | Policy-dependent; may indicate downstream overload | Respect Retry-After |
| HTTP 400/422 | Contract/input | Usually no | Usually no |
| HTTP 401/403 | Authentication/authorization | Goal-dependent, usually not availability | Usually no |
| HTTP 404 | Resource not found | Usually no if valid domain outcome | Usually no |
| HTTP 409 | Domain conflict | Business-dependent | Do not repeat verbatim |
| JSON mapping/schema error | Client/contract | May need separate alert, not necessarily instance outage | Usually no |
| CallNotPermittedException | Breaker OPEN | **Should not re-count as backend failure** | Do not retry repeatedly |

In Spring Framework, **RestClient** typically throws HttpClientErrorException/HttpServerErrorException from retrieve(); **WebClient** typically throws WebClientResponseException; **Feign** has FeignException/RetryableException; **RestTemplate** has HTTP/ResourceAccessException. Whether the breaker records an error depends on the exception type **after** adapters/wrappers process it.

A sound option is translating HTTP errors into a domain taxonomy (NotFound, Conflict, Unavailable, TransportFailure...), then configuring predicates to **only record types that reflect dependency health**.

**Do not attach a retry policy to all RestClientException or RuntimeException types.** A decode error on a 200 response signals schema incompatibility; retrying only re-fetches the same payload.

## 17. Test Each Mechanism Individually Before Testing Them Combined

An integration test calling two backends and receiving HTTP 200 is **not enough** to prove circuit breaker, retry, and LoadBalancer work together properly. Test each component independently first, then test the combined wrappers.

### 17.1. Unit Testing Circuit Breaker State Directly

Resilience4j provides a CircuitBreaker that can be tested without a Spring Context or HTTP:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CircuitBreakerStateTest {

    @Test
    void opensAfterSufficientFailuresAndRejectsNewCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("inventoryReadTest", config);

        AtomicInteger executed = new AtomicInteger();

        for (int i = 0; i < 4; i++) {
            assertThrows(IllegalStateException.class, () ->
                    breaker.executeSupplier(() -> {
                        executed.incrementAndGet();
                        throw new IllegalStateException("backend down");
                    }));
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
        assertEquals(4, executed.get());

        assertThrows(CallNotPermittedException.class, () ->
                breaker.executeSupplier(() -> {
                    executed.incrementAndGet();
                    return "should-not-execute";
                }));

        // OPEN rejected the call before the supplier executed.
        assertEquals(4, executed.get());
    }
}
~~~

This test proves **the breaker rejects calls when OPEN**: actual execution count does not increase. It **does not test** service discovery, HTTP retry, or LoadBalancer instance selection; it is a pure Resilience4j state unit test.

### 17.2. Testing HALF_OPEN Without Depending on Sleep

Another test can manually transition the breaker to HALF_OPEN:

~~~java
CircuitBreaker breaker = CircuitBreaker.of(
        "recoveryTest",
        CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .permittedNumberOfCallsInHalfOpenState(2)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build());

// In a unit test, transition manually to avoid waiting on real wall-clock time.
breaker.transitionToHalfOpenState();

assertEquals("ok1", breaker.executeSupplier(() -> "ok1"));
assertEquals("ok2", breaker.executeSupplier(() -> "ok2"));
assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
~~~

This is a **state machine test**, not an exact simulation of the full OPEN wait duration in production. If you need to test timers/automaticTransition, write a dedicated test with an appropriate clock/scheduler and avoid arbitrary Thread.sleep calls.

**Important:** HALF_OPEN does not mean all traffic is restored. Only a configured number of probes are permitted; remaining requests may be rejected until the breaker has enough data to decide CLOSED or OPEN.

### 17.3. Unit Testing Retry by Execution Count

With Reactor Retry:

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n == 1
            ? Mono.error(new IllegalStateException("transient"))
            : Mono.just("success");
});

Mono<String> result = source.retryWhen(
        Retry.max(1)
                .filter(error ->
                        error instanceof IllegalStateException));

StepVerifier.create(result)
        .expectNext("success")
        .verifyComplete();

assertEquals(2, attempts.get());
~~~

The test above proves **one retry** after failure. It does not run through LoadBalancer at all. To test selecting A then B, attach retry to a supplier/LoadBalancer or a WebClient with a real filter and observe the target instances.

### 17.4. Unit Testing LoadBalancer with a Fixed List

Provide [A, B] via a fake ServiceInstanceListSupplier. Test RoundRobinLoadBalancer with a deterministic seed, then call **choose(Request)** and inspect the returned ServiceInstance.

Things to verify:

- When only A exists, always select A.
- When A and B exist, selection always lies within [A, B].
- When the list is empty, return the corresponding **no server available** status rather than fabricating an address.
- When retry-aware excludes A and B remains, it has the chance to select B.

Do not extrapolate that a unit test verifying retryWhen proves the instance selection behaviors above. Target selection and repetition are **two different test contracts**.

## 18. Integration Test: A Fails, B Healthy — Counting Actual HTTP Attempts

### 18.1. Setup

Run two MockWebServer/WireMock instances on dynamic ports:

~~~text
inventory-a -> localhost:<portA> -> HTTP 503
inventory-b -> localhost:<portB> -> HTTP 200 JSON
~~~

Create a fixed supplier or SimpleDiscoveryClient providing:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

In a real integration test, **replace 8081/8082 with dynamic ports** from MockWebServer and register them via **@DynamicPropertySource**. The YAML above only illustrates the SimpleDiscoveryClient format.

With WebClient:

1. Register **@LoadBalanced WebClient.Builder**.
2. Create a LoadBalancer supplier [A, B] and control the instance-selection policy.
3. Configure at most one retry on HTTP 503.
4. Disable other retries at application/proxy layers so results are not multiplied.
5. Use **RecordedRequest** on both servers to verify where requests were sent.

### 18.2. Key Assertions

| Check | Expectation |
| --- | --- |
| Requests to A | Exactly 1, returning HTTP 503 |
| Requests to B | Exactly 1, returning HTTP 200 |
| Total network requests | 2, not 3 or 4 |
| Caller response | 200/valid DTO |
| Retry attempts | Recorded as 2 |
| Circuit breaker outside retry | One logical success, if operation completes successfully |
| Circuit breaker inside retry | May record one failure and one success |
| After breaker OPEN | New calls rejected before backend receives requests |

**Condition:** only assert that A receives the first attempt and B receives the second when the test has **fixed the selection policy**. If using Round Robin with a non-deterministic seed/state, you can only assert two requests reached valid instances, not the A→B order.

### 18.3. Distinguish Three Kinds of 503

- **Backend A returns a real 503:** server A received the request and responded 503.
- **Gateway returns 503:** gateway received the request but could not find/call upstream.
- **LoadBalancer has no instances:** filter/client may emit an error signal or 503/404 response before any request reaches a backend.

All three may be translated into "service unavailable" at the business layer, yet debugging, retrying, and breaker evaluation should not treat them identically. Track **backend request counts, instance IDs, traces, and status origin**.

## 19. Integration Test When the Entire Service Fails and Breaker Opens

A valuable CI scenario:

1. Mock servers A and B both return 503 or time out after a small configured interval.
2. Send enough logical calls to reach **minimumNumberOfCalls** and **failureRateThreshold**.
3. Verify the circuit breaker transitions from CLOSED to OPEN.
4. Record total HTTP requests before and after OPEN.
5. Send one more logical call and confirm no new HTTP request reaches A/B.
6. Confirm the caller receives **CallNotPermittedException** or the appropriate domain fallback.
7. Transition/wait for HALF_OPEN via a controlled test mechanism.
8. Make one backend return 200 and verify permitted probe counts and breaker state.

Arithmetic rule example:

~~~text
slidingWindowSize=10
minimumNumberOfCalls=10
failureRateThreshold=50%

10 logical calls:
    6 5xx/timeout errors
    4 successes
failureRate = 60% -> OPEN upon evaluation
~~~

In the test, check **whether the breaker measures logical calls or attempts**. If retry is **inside the breaker**, one logical request with three attempts yields only one final outcome; breaker counts will not equal backend HTTP request counts.

### 19.1. Do Not Count Breaker OPEN Rejections as New Backend Failures

A request rejected because the breaker is OPEN **never reaches the backend**. Therefore, do not increment a metric named "inventory backend 5xx" for that request. Separate them:

~~~text
inventory_http_5xx
inventory_connect_timeout
inventory_retry_attempts
inventory_circuit_not_permitted
inventory_fallback_used
~~~

These names are **metric classification suggestions**, not default meter names in Spring Cloud/Resilience4j. Use library-provided meters where appropriate and add labels with controlled cardinality.

## 20. Observability: Inspect Instance, Attempts, and Breaker State Together

When an incident occurs, you need to answer:

1. Which logical call failed?
2. Which ServiceInstance did LoadBalancer pick on the first attempt?
3. Did retry try another instance?
4. Did the HTTP client fail at DNS/connect/TLS/read or receive an HTTP response?
5. Is the circuit breaker CLOSED, OPEN, or HALF_OPEN?
6. How many calls actually reached the backend versus failed fast?
7. Was a fallback used? Is the returned data stale?
8. Were thread/connection pools or bulkheads saturated?

Event timeline example:

~~~text
trace=abc, operation=inventoryRead, breaker=CLOSED
attempt=1, instance=A, outcome=connection_reset, elapsed=90ms
attempt=2, instance=B, outcome=HTTP_200, elapsed=130ms
logicalOutcome=SUCCESS, totalElapsed=270ms
breaker=CLOSED, fallbackUsed=false
~~~

During sustained downstream failure:

~~~text
trace=xyz, operation=inventoryRead, breaker=OPEN
attemptsSent=0, outcome=CALL_NOT_PERMITTED, elapsed=2ms
fallbackUsed=true, fallbackType=CACHED_STOCK, staleAge=8s
~~~

These logs are **observability examples**, not default output. Never place tokens, cookies, personal addresses, full bodies, or URLs containing sensitive data into logs.

### 20.1. Useful Metrics

| Metric group | Meaning |
| --- | --- |
| Logical call success/failure | Call quality from a business perspective |
| HTTP attempts by service/instance | Retry amplification and faulty instances |
| Circuit breaker state/gauge | Proportion of dependencies currently tripped |
| Failure/slow call rate | Conditions triggering breaker OPEN |
| Not-permitted calls | Requests rejected early |
| Retry attempts/exhausted | Retry effectiveness/quality |
| Timeout per phase | Transport, overall deadline, TimeLimiter |
| Pool active/pending/idle | Risk of connection exhaustion or acquire wait |
| Bulkhead permitted/rejected | Concurrency limit exceeded |
| Fallback rate/staleness | Degree of data quality degradation |

Resilience4j supports metrics via Micrometer; Spring Boot Actuator/metrics integration requires compatible dependencies and configuration. Avoid metric tags containing **SKU, user ID, session, or overly granular ephemeral instance details** that cause high cardinality.

### 20.2. Do Not Alert Only on Caller HTTP 200

If a fallback always returns HTTP 200 with cached data, the availability dashboard can stay green even while Inventory is completely dead. Alert on:

- Fallback rate.
- Staleness of returned data.
- Circuit breaker OPEN duration.
- Rejected call count.
- Retry amplification and P95/P99 latency.
- Instance-level connection errors.

**Fallback success does not mean downstream has recovered.**

## 21. A Runbook for a Real Incident

### Scenario: Order 503 Responses Spike, Inventory Has 3 Instances

Follow this sequence:

1. **Determine scope:** are errors happening across all Order instances or only one zone?
2. **Check service discovery:** how many inventory-service instances exist, and what metadata/health is visible?
3. **Check selection:** which instances is LoadBalancer picking, and is traffic hitting a faulty instance?
4. **Check transport:** is the backend returning genuine 503s, or are these connect/timeout/no-instance errors?
5. **Check retry:** attempts per logical call, nested retries, whether instances are switched?
6. **Check breaker:** is it OPEN, is it scoped per-operation or per-instance, which rate/threshold was breached?
7. **Check load:** pool pending count, CPU, threads, queues, rate limits, and bulkhead rejections.
8. **Check fallback:** is degraded data acceptable; is anyone seeing stale stock numbers as fresh?
9. **Remediate:** fix backend/health/registry, adjust capacity, or isolate instances based on root cause.
10. **Controlled recovery:** observe HALF_OPEN probes, success rate, and returning load.

**Do not reflexively increase retry counts or disable the circuit breaker during an incident.** If all of Inventory is overloaded, doing so can cause HTTP attempt counts to surge. Only change them with evidence and observed consequences.

### 21.1. When the Breaker Is OPEN While One Instance Is Still Healthy

Ask:

- Is the breaker measuring the **whole service** or each instance?
- Is the failure rate amplified because retry sits inside/outside the breaker?
- Did a health/zone/hint filter exclude the healthy instance?
- Was the retry policy rejected before re-selecting an instance?

The fix is not necessarily "increase waitDurationInOpenState." You may need to fix the fallback, reposition the breaker, adjust instance sources, or detect faulty backends before requests run.

### 21.2. When the Breaker Never Opens Even Though the Backend Is Slow

Check:

- Has **minimumNumberOfCalls** accumulated enough samples?
- Are slow-call threshold and duration configured?
- Does the HTTP client have a timeout to terminate hanging calls?
- Is a fallback inside the breaker swallowing errors and returning success?
- Is 503 being converted into a "successful" domain response before the breaker sees it?
- Is a new breaker ID being created per request, preventing statistics from accumulating?

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating LoadBalancer as a circuit breaker | Selected instance can still fail repeatedly | Add a properly scoped breaker |
| Treating retry as guaranteed failover | Next attempt may pick the same instance again | Test retry context and RetryAware supplier |
| Retrying every exception | Retries 400/404/schema errors, wasting load | Classify by contract |
| Retrying immediately without backoff | Retry storm during wide downstream outage | Backoff, jitter, retry budget |
| Using a breaker to limit concurrency | CLOSED breaker still lets many requests through | Use bulkhead/pool/concurrency limit |
| Placing breaker outside retry then reading per-attempt stats from breaker metrics | Breaker metrics only see final outcomes | Collect HTTP attempt metrics separately |
| Placing retry outside breaker and retrying CallNotPermittedException | Loops calls even while breaker is OPEN | Exclude that exception from retry |
| Circuit breaker per request ID | Insufficient samples, unbounded breaker count | Name by service/operation |
| Per-instance breaker without cleanup | High cardinality/stale registry | Define lifecycle and retention policy |
| Fallback returning success for ambiguous POST | Duplicate transactions or corrupted data | Idempotency + pending/reconcile |
| 404 inflating breaker failure rate | Breaker opens on valid business outcomes | Map 404 to domain result / ignore properly |
| Setting only connect timeout | Slow responses still hold resources | Read/response timeout + deadline |
| Enabling multiple retry layers | Attempts multiply uncontrollably | Designate one primary retry layer |
| Assuming OpenFeign CB is on just from LB starter | Feign CB has its own flag | Enable and test spring.cloud.openfeign.circuitbreaker.enabled |
| Using fallback without measuring degradation | HTTP 200 masks downstream outage | Fallback/stale-age metrics |
| Increasing retries during system-wide 503 | Adds load to an already overloaded backend | Cut retries, protect with breaker/bulkhead, fix backend |

## 23. Practice Exercises with Answers

### 23.1. Scenario A: One Instance Fails

~~~text
Supplier = [A, B, C]
A = connection refused
B = 200
C = 200
Retry = max 1 time, avoid previous instance
Breaker = CLOSED
~~~

**Question:** After picking A and failing, which mechanism is needed to try B/C? Does the circuit breaker switch targets on its own?

**Answer:** retry decides to try again; LoadBalancer picks an instance from the updated candidate list, and retry-aware can avoid A. The circuit breaker only permits/records outcomes; it **does not select B on its own**.

### 23.2. Scenario B: Entire Backend Fails

~~~text
10 logical calls
Each call max 2 attempts
Both A and B return HTTP 503
Breaker outside retry
minimumNumberOfCalls = 10
failureRateThreshold = 50%
~~~

**Question:** How many attempts can the backend receive before the breaker opens? How many outcomes does the breaker record?

**Answer:** if all 10 calls run 2 attempts each with no other limit, the backend can receive **20 attempts**; the breaker outside retry records **10 logical failures**, enough to open at a 100% failure rate. In a real environment, breaker state can transition at the moment a call completes, so you must measure concurrency and completion order accurately.

### 23.3. Scenario C: POST Times Out

~~~text
Attempt 1: POST /reservations -> timeout after 900ms
Server may have committed
Retry policy: 1 more attempt
~~~

**Question:** Should you immediately retry on another instance?

**Answer:** Only if the backend supports an **idempotency key** and appropriate deduplication. Otherwise, reconcile via an operation ID or return a pending/unknown status rather than fabricating failure or success.

### 23.4. Scenario D: Breaker OPEN, Retries Still Incrementing

~~~text
Breaker OPEN
Retry outside breaker
Retry predicate = all RuntimeExceptions
~~~

**Question:** What can happen?

**Answer:** Retry can loop over **CallNotPermittedException** multiple times, even with zero real HTTP attempts. This wastes CPU, inflates latency, and pollutes metrics. Fix the predicate to exclude CallNotPermittedException and apply fallback/fail-fast per contract.

### 23.5. Scenario E: Many Requests Stuck, Breaker CLOSED

~~~text
500 concurrent calls
Inventory has not returned errors yet, responding very slowly
Breaker remains CLOSED
~~~

**Question:** Which mechanism should be applied first?

**Answer:** **timeout/deadline** so calls do not hang indefinitely; **bulkhead/pool limit** to cap concurrency; then configure **slowCallRateThreshold** so the circuit breaker can trip once sufficient data is collected. LoadBalancer/Retry alone cannot solve pool starvation.

## 24. Pre-Production Design Checklist

- [ ] Clearly distinguish **LoadBalancer** selects instances, **Retry** repeats attempts, **CircuitBreaker** permits/rejects.
- [ ] Configure ServiceInstanceListSupplier/discovery/health explicitly; do not guess registry state.
- [ ] Apply retry only to safe statuses/exceptions/methods, with max attempts.
- [ ] Configure backoff/jitter, retry budget, and **overall deadline**.
- [ ] Avoid nested retries across HTTP client, LoadBalancer, Feign, Reactor, and service mesh.
- [ ] Provide sufficient retry-aware context if avoiding the previous instance; do not promise guaranteed instance switching.
- [ ] Give circuit breakers stable names per service/operation and explicit record/ignore exception policies.
- [ ] Understand the effect of placing the breaker **outside retry** versus **inside retry**.
- [ ] Never retry CallNotPermittedException when the breaker is OPEN.
- [ ] Cap concurrency with bulkhead/pool limits where needed instead of relying on a breaker.
- [ ] Align TimeLimiter/connect/read timeouts and deadlines into a consistent budget.
- [ ] Ensure fallbacks only return valid data; cached data must include stale/freshness metadata.
- [ ] Design idempotency and unknown-outcome handling for POST/PUT operations with side effects.
- [ ] Write separate unit tests for LB, retry, and breaker state machine.
- [ ] Write real integration tests for A fails/B healthy, full service failure, and OPEN/HALF_OPEN.
- [ ] Count **HTTP attempts** at the backend, not only logical calls at the client.
- [ ] Separate tracing/metrics for no-instance, transport, 4xx/5xx, retry, breaker OPEN, and fallback.
- [ ] Never log authorization tokens, cookies, or sensitive data.
- [ ] Verify behavior against your BOM/release train, as starters and auto-configuration differ.

## 25. Conclusion

**Load balancing, retry, and circuit breaker are three complementary protection layers, not three names for the same feature.** LoadBalancer finds a suitable instance and reconstructs the physical URI; retry repeats a call on recoverable errors; circuit breaker observes statistics and temporarily stops permitting harmful calls. Timeouts bound wait durations, bulkheads isolate resources, and fallbacks define business behavior when a dependency is unavailable.

To operate safely, **classify errors by the HTTP contract, bound retries with attempts/backoff/deadlines, decide whether the breaker observes logical calls or individual attempts, and test both instance selection and actual HTTP request counts**. For requests with side effects, never treat a timeout as proof the backend did not process the request; use idempotency and reconciliation.

A resilient system is not one that "retries the most," but one that **routes to the right target, retries conditionally, trips at the right moment, sheds load in a controlled manner, and returns honest results**.

## 26. References

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, load-balancing policies, retry, and retry-aware supplier.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced HTTP clients and retry.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): retry.enabled, max-retries-on-*, retryable-status-codes, and related properties.
- [Spring Cloud Circuit Breaker – Abstraction](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): CircuitBreakerFactory/ReactiveCircuitBreakerFactory and fallback.
- [Spring Cloud CircuitBreaker – Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): starters, Java config, TimeLimiter, metrics, and bulkhead integration.
- [Spring Cloud CircuitBreaker – Properties](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html): circuitbreaker/timelimiter configs and precedence.
- [Spring Cloud CircuitBreaker – Bulkhead](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-pattern-supporting.html): SemaphoreBulkhead and ThreadPoolBulkhead.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): FeignBlockingLoadBalancerClient, Retryer.NEVER_RETRY, and circuit breaker opt-in.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): CLOSED/OPEN/HALF_OPEN, sliding window, failure/slow rate, and CallNotPermittedException.
- [Resilience4j – Retry](https://resilience4j.readme.io/docs/retry): maxAttempts, retryOnException, result predicate, backoff, and interval functions.
- [Resilience4j – Getting Started](https://resilience4j.readme.io/docs/getting-started-3): decorator ordering, AOP annotations, and composing policies.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient error semantics and HTTP transport.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): WebClient HTTP error handling.
- [Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retryWhen, error mapping, and operator semantics.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier/virtual time for testing reactive retry and errors.
