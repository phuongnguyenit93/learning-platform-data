# Retries, Circuit Breakers, Timeouts, and Bulkheads in Applications

An application can be healthy while a service it calls fails: flaky networking, slow APIs, overloaded databases, or an infrastructure zone disruption. If every request waits forever or endlessly retries a failing service, a small dependency issue can cascade into a system-wide outage.

In the **Reliability and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_AZURE** track, we focus on four application-protection design patterns: **timeouts**, **retries**, **circuit breakers**, and **bulkheads**. They apply to Java, .NET, Node.js, or other workloads deployed on Azure App Service, Azure Kubernetes Service (AKS), Azure Container Apps, and Azure Functions. This complements the broader Azure architecture across networking, compute, storage, data, monitoring, security, and cost control.

The goal is not to force every request to succeed at all costs. The goal is to **bound waiting time and resource usage, recover cleanly from transient faults, and prevent failures from cascading**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish transient errors, persistent failures, overload, and business errors before choosing a handling mechanism.
2. Design overall deadlines, per-attempt timeouts, and bounded retries with backoff and jitter.
3. Explain the **closed → open → half-open** states of a circuit breaker and how recovery probing is timed.
4. Calculate and apply concurrency limits using **bulkheads** so one dependency cannot exhaust app threads, connections, or memory.
5. Combine all four mechanisms together and alongside built-in retries in Azure SDKs, HTTP gateways, or queues.
6. Configure a Java HTTP client example, monitor it with Azure Monitor / Application Insights, and design fault tests.

## 2. Real-World Context: One Small Fault Triggers a Cascade

Suppose an API **orders-api** runs on Azure Container Apps or AKS. When a user places an order, the API calls **inventory-api** to check stock, **pricing-api** to fetch prices, and **payment-api** to confirm payment. Inventory API slows temporarily from 100 ms to 8 seconds due to database connection-pool contention.

If orders-api handles each request on a thread with no timeout:

1. New requests keep calling inventory-api.
2. Threads stay blocked waiting; HTTP and connection pools fill up.
3. Requests unrelated to inventory run out of resources to execute.
4. The load balancer may keep sending traffic because some health checks still pass.
5. Autoscaling adds instances, yet new instances immediately pile more load onto inventory-api.

Adding unbounded retries makes matters worse: 100 initial requests, each retrying multiple times, can generate hundreds of extra requests against an already overloaded dependency.

~~~mermaid
flowchart LR
    U["Client"] --> O["orders-api on Azure"]
    O --> I["slow inventory-api"]
    O --> P["pricing-api"]
    O --> M["payment-api"]
    I --> D["Overloaded database connection pool"]
    D -. "Increases response latency" .-> I
    I -. "Holds threads / connections" .-> O
    O -. "Starves resources" .-> P
    O -. "Starves resources" .-> M
~~~

The four patterns answer distinct questions:

| Pattern | Question to answer | Primary action | Risk if misused |
| --- | --- | --- | --- |
| **Timeout** | How long am I willing to wait for a dependency? | Cap wait time; fail or fall back on expiry | Too short causes false errors; timeout may not cancel server work |
| **Retry** | Is this error likely to clear if attempted again? | Bounded re-attempts with wait intervals | Amplifies traffic; duplicates side-effecting operations |
| **Circuit breaker** | Is the dependency failing badly enough to stop calling it briefly? | Trip open past error threshold; allow controlled recovery probes | Poor thresholds reject too early or recover too slowly |
| **Bulkhead** | How many resources may one dependency consume at most? | Cap concurrency or queue depth per group | Cap too low bottlenecks traffic even when dependency is healthy |

None of these replaces Availability Zone/region redundancy, backups, data recovery, or disaster recovery strategies. They provide **call-level and resource-level application resilience**, helping stabilize systems against partial failures.

## 3. Classify Errors Before Deciding to Retry

Retrying only helps when the next attempt has a solid chance of succeeding and retry cost is bounded.

| Signal | Examples | Handling approach |
| --- | --- | --- |
| **Timeout / network reset** | Dropped connection, response misses deadline | Can retry within deadline, but check whether side effects already completed server-side |
| **HTTP 429** | Service rate limiting | Honor **Retry-After** if present, throttle send rate, and retry within budget; tune concurrency/rate limits |
| **HTTP 503 / 502 / 504** | Service temporarily unavailable, bad proxy, gateway timeout | Can run bounded retries if the request is safe |
| **HTTP 500** | Server error, cause unclear | Retry only when error nature and operation safety are known; avoid retrying every 500 by default |
| **HTTP 400 / 401 / 403 / 404 / 422** | Bad input, unauthenticated, forbidden, not found, validation error | Usually **do not retry** when request and state remain unchanged |
| **HTTP 409 / 412** | State conflict, precondition/version mismatch | Inspect business logic and concurrency; do not retry blindly |
| **Circuit breaker OPEN** | Dependency already determined unhealthy | Fail fast or fall back; do not keep retrying the same dependency |
| **Bulkhead full** | Allowed concurrency ceiling reached | Reject fast, apply backpressure, bounded queue, or degrade |
| **Permanent business error** | Out of stock, card declined, invalid product code | Return business outcome; do not auto-retry |

This classification is a **starting point**, not an absolute rule for every HTTP API. The dependency's contract must define which error codes are genuinely recoverable, which are retryable, and whether a call may have produced side effects.

### 3.1. Idempotency Determines Whether Retries Are Safe

An operation is **idempotent** if executing it multiple times with the same inputs produces no business effect beyond the first execution. HTTP GET is normally designed to be safe to re-read. HTTP PUT can be idempotent when updating to the same target state; DELETE is generally idempotent in final effect even if individual responses vary.

With a **POST creating an order or charging payment**, a timeout does not prove the operation failed. The server may have committed the order and dropped the connection before returning the response.

Example protecting payment creation:

~~~http
POST /payments
Idempotency-Key: payment-order-78125-v1
Content-Type: application/json

{"orderId":"78125","amount":250000,"currency":"VND"}
~~~

The payment server must define how idempotency keys are stored and validated, key retention lifetimes, handling of reused keys with differing payloads, atomic state writes, and replay policies. **An `Idempotency-Key` header does not magically make every API idempotent.** Retry POSTs only when the target API explicitly supports it or your application enforces verified deduplication.

## 4. Timeouts: Bounding Wait Time, Not Just Hung Requests

### 4.1. Types of Timeouts to Distinguish

| Layer | Meaning | Example |
| --- | --- | --- |
| **Connection timeout** | Wait to establish connection to host/port | TCP handshake fails to complete within 200 ms |
| **TLS/handshake timeout** | Wait for TLS handshake where client/proxy supports it | Secure session fails to complete on time |
| **Read/response timeout** | Wait for data from server or gap between reads, per HTTP client | No response bytes for 450 ms |
| **Per-attempt timeout** | Maximum duration for one concrete attempt | One HTTP attempt capped at 500 ms |
| **Overall deadline** | Final timestamp by which the entire business request must finish, including retries and fallback | Total order creation budget 2 seconds |
| **Gateway/ingress timeout** | Limit at Azure Front Door, Application Gateway, API Management, or proxy | Gateway may close connection before backend finishes |

**Read timeout is not always total request duration.** Some HTTP clients apply read timeouts per socket read or idle gap, so a trickle-feeding server can stretch one request well past expectations. When an app needs a hard cap, enforce an **overall deadline** or a true whole-operation request timeout.

Outer layers govern the maximum budget inner layers must respect. If the client waits at most 2 seconds while orders-api spends 3 seconds just calling inventory, the result arrives too late for the client. Evaluate application, proxy, load balancer, and dependency timeouts together; never assume an Azure service's default timeout stays fixed across all configurations.

### 4.2. Calculating an End-to-End Time Budget

Suppose a request must respond within **2,000 ms**. Allocate:

- 250 ms for validation, authentication, and serialization.
- 200 ms reserve for scheduling, networking, and fallback.
- Up to 1,550 ms for inventory calls and retry backoff delays.

If inventory is called up to **3 attempts**, each capped at **400 ms**, with two backoffs of 100 ms and 200 ms, the theoretical sum is:

\[
3 \times 400 + 100 + 200 = 1{,}500 \text{ ms}
\]

Only about 50 ms remains in the inventory budget, so real execution must account for connect overhead, internal processing, network jitter, and scheduling. These numbers are **illustrative budgeting examples**, not standard settings for all workloads.

Better still, compute each attempt's cap from the **actual remaining deadline** instead of granting a fresh 400 ms blindly:

~~~text
deadline = monotonic_now() + 2_000_ms
...
remaining = deadline - monotonic_now()
attempt_timeout = min(400_ms, remaining - safety_margin)
if attempt_timeout <= 0:
    stop_with_timeout
~~~

Use a monotonic clock to measure intervals because wall-clock time can jump. Across multi-service chains, propagate deadline/budget metadata appropriately, while having receiving servers enforce trust bounds so external callers cannot demand infinite timeouts.

### 4.3. Timeouts Do Not Mean Work Was Canceled

When a client times out, the downstream database query or HTTP handler **may still be running**. Cancellation signals also do not guarantee the server rolled back a transaction or stopped work. Therefore:

1. Configure matching timeouts/cancellations across the HTTP client, database driver, and upstream.
2. Keep write operations idempotent.
3. Use correlation IDs to trace final outcomes.
4. For long-running tasks, accept work asynchronously via a queue and return **202 Accepted** with a status lookup token instead of holding HTTP connections open.

## 5. Retries: Recovering from Transient Faults Without Request Storms

### 5.1. Bounded Retries

A retry policy must declare at minimum:

- **Max attempts:** total tries including the initial call (e.g., 3 attempts = 1 initial + up to 2 retries).
- **Retryable conditions:** which exceptions or status codes qualify.
- **Backoff:** delay formula between attempts.
- **Jitter:** randomness preventing synchronized client retries.
- **Deadline:** stop retrying if insufficient time remains for useful completion.
- **Idempotency:** write calls must be safe to execute multiple times.
- **Retry budget:** service-wide cap on total retry volume to prevent amplification.

Example bounded exponential backoff:

\[
d_k = \min(d_{max}, d_0 \times 2^{k-1})
\]

where \(d_0\) is the initial delay, \(d_{max}\) is the ceiling, and \(k\) is the retry index. With **full jitter**, sleep time is drawn randomly between 0 and \(d_k\), preventing instances from hammering the dependency in lockstep after fixed waits.

Suppose \(d_0 = 100\) ms and \(d_{max} = 2{,}000\) ms:

| Retry # | Backoff ceiling before jitter |
| --- | --- |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1,600 ms |

Actual retry count must be capped independently; **this table does not imply apps should retry 5 times**. Many interactive APIs with tight deadlines tolerate only 0–2 retries.

### 5.2. HTTP 429, Retry-After, and Backpressure

When returning **429 Too Many Requests**, servers may send a **Retry-After** header as seconds or an HTTP date. Clients must parse it accurately, respect request budgets, and apply a maximum wait cap. If the requested delay exceeds the user's deadline, surface an overload signal or shift to async processing rather than hanging uselessly until timeout.

Retries **do not replace rate limiting**. If baseline load persistently exceeds capacity, reduce send rates, cap concurrency, scale appropriately, optimize queries, or expand downstream capacity.

~~~mermaid
flowchart TD
    A["Call dependency"] --> B{"Outcome?"}
    B -->|"Success"| C["Return result"]
    B -->|"Non-retryable error"| D["Return error / fallback"]
    B -->|"Retryable 429, 503, timeout"| E{"Idempotent and within deadline/budget?"}
    E -->|"No"| D
    E -->|"Yes"| F["Backoff + jitter; check Retry-After"]
    F --> G{"Budget remaining to try again?"}
    G -->|"No"| D
    G -->|"Yes"| A
~~~

### 5.3. Avoiding Nested Multi-Layer Retries

A system might configure retries in:

- Mobile/web clients.
- Azure API Management or gateways.
- The orders-api application.
- Azure SDK / HTTP clients.
- Database drivers or message consumers.

If three independent layers each try up to three times, one user request can trigger up to **3 × 3 × 3 = 27** attempts at the furthest dependency in the worst case. Designate **which layer owns retries**, enforce an overall deadline, and track actual attempt counts. Never add a retry policy merely because a library offers one.

## 6. Circuit Breakers: Failing Fast When Calls Are Likely to Fail

### 6.1. Three Core States

**CLOSED:** lets requests pass and records outcomes. If the failure rate or slow-call rate exceeds configured thresholds after enough samples, the breaker transitions to OPEN.

**OPEN:** rejects calls immediately to protect both caller and dependency. The application returns a fallback or controlled error. Once the open wait timer expires, the breaker transitions to HALF_OPEN.

**HALF_OPEN:** permits a small number of probe calls. If results show recovery, it returns to CLOSED; if failures still breach the threshold, it flips back to OPEN.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure/slow-call rate exceeds threshold after min samples
    OPEN --> HALF_OPEN: Open wait duration elapses
    HALF_OPEN --> CLOSED: Probes meet recovery criteria
    HALF_OPEN --> OPEN: Probes fail
~~~

Some libraries add states such as **DISABLED**, **FORCED_OPEN**, or **METRICS_ONLY** for operations and testing. Do not equate an OPEN breaker with a completely dead service; sometimes it reflects latency spiking past policy or overly sensitive thresholds.

### 6.2. Choosing Meaningful Thresholds

Example starting settings for inventory-api:

| Parameter | Illustrative value | Purpose |
| --- | --- | --- |
| Sliding window | Last 20 calls | Tracks recent health |
| Minimum number of calls | 10 | Avoids tripping on tiny sample sizes |
| Failure rate threshold | 50% | Opens circuit when half or more calls fail |
| Slow-call duration | 400 ms | Defines what counts as a slow call |
| Slow-call rate threshold | 70% | Trips even before HTTP errors spike |
| Wait duration in open state | 30 seconds | Gives dependency breathing room before probing |
| Permitted half-open calls | 3 | Bounds probe traffic |

Tune these values to **SLOs, traffic volume, dependency behavior, observation windows, and recovery speed**. A service seeing 2 requests/minute cannot wait for 10 samples to react. A 10,000 requests/second service may need time-based windows and finer grouping.

**Exception classification is crucial.** Client-induced HTTP 400 errors should not make the breaker treat the dependency as unhealthy. Conversely, timeouts, network errors, and 503s are strong health signals. Treat 429 carefully as overload/rate-limiting with its own policy rather than blindly counting all 429s as system crashes.

### 6.3. Fallbacks When a Circuit Breaker Opens

Sensible fallbacks depend on business semantics:

| Call | Acceptable fallback | Dangerous fallback |
| --- | --- | --- |
| Fetch product recommendations | Return cached list labeled as potentially stale | Claim latest pricing/stock is guaranteed |
| Fetch secondary info | Omit optional section or show placeholder | Assume full business operation succeeded |
| Check stock before ordering | Pause order acceptance or mark order pending verification | Claim stock is available without evidence |
| Charge payment | Return processing/pending status and reconcile by idempotency key | Assume payment succeeded or fire unchecked extra charges |

A fallback **must never violate business correctness**. A storefront API can degrade recommendations, whereas confirming a charge or reserving stock requires real verification.

## 7. Bulkheads: Isolating Dependency Capacity

The term **bulkhead** comes from watertight ship compartments: flooding one compartment does not sink the vessel. In applications, each critical dependency group receives a **bounded share of resources**.

Two common approaches:

1. **Semaphore bulkhead:** allows at most N concurrent calls. Once N is reached, calls fail fast or wait briefly. Fits async I/O or HTTP calls without creating separate thread pools.
2. **Thread-pool bulkhead:** dedicates a bounded thread pool and bounded queue to a synchronous task group. Increases isolation but adds thread, queue, scheduling overhead, and queue-buildup risk.

Suppose orders-api has 80 worker threads. If all 80 block on inventory, pricing and health endpoints lose all threads. Capping **inventory to 20 concurrent calls per instance** preserves capacity for other endpoints—provided HTTP/thread pools align accordingly.

~~~mermaid
flowchart LR
    R["Incoming requests to orders-api"] --> B{"Inventory bulkhead slot free?"}
    B -->|"Yes"| I["At most N inventory calls"]
    B -->|"Full"| F["Fail fast / backpressure"]
    R --> P["Pricing uses separate bulkhead"]
    R --> H["Critical endpoints keep dedicated capacity"]
~~~

### 7.1. Estimating Concurrency with Little's Law

Under steady traffic, the approximate relationship is:

\[
L = \lambda \times W
\]

where \(L\) is average concurrent tasks, \(\lambda\) is requests/second, and \(W\) is average processing time in seconds.

If one instance sends **50 requests/second** to inventory averaging **0.2 seconds** each, average concurrency is roughly:

\[
50 \times 0.2 = 10
\]

You might start testing with a limit around 15–20 concurrent calls, then measure p95/p99, queueing, and rejection rates. This is an illustration only: traffic bursts, tail latency, CPU, connection limits, and cross-replica skew can require adjusting the cap. Across 5 replicas, 20 concurrent calls each implies up to **100 potential concurrent calls**, so check the dependency's actual capacity.

### 7.2. Queues Are Resources Too

Long queues turn overload errors into long waits followed by timeouts. Specify:

- Maximum concurrent calls.
- Maximum queue capacity if using thread-pool queues.
- Very short or zero wait time for slot acquisition on low-latency APIs.
- Rejection response (e.g., HTTP 503/429 per API contract) with backpressure signals.
- Alerts when slot rejection rates rise.

Per-dependency bulkheads work better than one global limit when inventory and pricing behave differently. Still, bulkheads cannot rescue an app if all calls share one tiny thread pool or unisolated blocking operations run outside the bulkhead.

## 8. Combining Timeouts, Retries, Circuit Breakers, and Bulkheads

Evaluation order affects attempt counts, wait duration, and failure tracking. One clean conceptual pipeline:

1. On request arrival, establish the **overall deadline**.
2. Acquire a **bulkhead** permit for the logical dependency operation.
3. Before each attempt, check whether the **circuit breaker** permits calling.
4. If permitted, execute the call with a **per-attempt timeout** smaller than remaining deadline.
5. Record the attempt outcome in the circuit breaker per error classification rules.
6. On a retryable error, if budget remains and the breaker allows, apply **backoff + jitter** and retry.
7. Return result or fallback; **always release the bulkhead permit**.

~~~mermaid
flowchart TD
    A["Request + overall deadline"] --> B{"Bulkhead slot available?"}
    B -->|"No"| X["Return overload / safe fallback"]
    B -->|"Yes"| C{"Deadline and retry budget remain?"}
    C -->|"No"| Z["Return error / fallback"]
    C -->|"Yes"| D{"Circuit breaker permits?"}
    D -->|"No, OPEN"| Z
    D -->|"Yes"| E["Call dependency with attempt timeout"]
    E -->|"Success"| S["Return result"]
    E -->|"Failure"| F{"Retryable error and idempotent?"}
    F -->|"No"| Z
    F -->|"Yes"| G["Backoff + jitter, bounded by deadline"]
    G --> C
    S --> H["Release bulkhead"]
    Z --> H
~~~

In this model, the bulkhead **may hold a slot during backoff waits** because it wraps the logical operation. That cleanly caps pending operations though slots sit idle while sleeping. Another variant holds a slot per attempt only, releasing before backoff and reacquiring before the next attempt. Choose based on concurrency protection needs and metrics, ensuring logical pending requests remain bounded.

**Framework gotcha:** actual execution order of decorators or annotations like `@Retry`, `@CircuitBreaker`, `@Bulkhead`, and `@TimeLimiter` depends on AOP/decorator ordering. If the circuit breaker wraps retry, it may record **one final operation outcome**; if inside retry, it may record **every attempt**. That shifts failure rates, timing, and trip thresholds. Verify configured order and test under controlled fault injection.

### 8.1. Ratios Worth Tracking

- **Retry amplification:** downstream attempts / upstream logical requests.
- **Failure rate:** policy-counted failures / measured calls.
- **Slow-call rate:** calls exceeding slow threshold / measured calls.
- **Bulkhead utilization:** active slots / total slots.
- **Time budget exhaustion:** share of requests aborted due to expired deadlines.

A high post-retry success rate can still mask instability if p99 skyrockets, the dependency stays overloaded, and retry amplification climbs.

## 9. Java Example: HTTP Timeouts + Resilience4j

This section illustrates patterns on **Spring Boot with Spring Framework 6.1+** (e.g., Spring Boot 3.2+) using a compatible **Resilience4j** library. Verify exact APIs/versions against your project dependencies. The goal is understanding policy placement and boundaries rather than requiring a pre-existing project or live Azure resources.

### 9.1. Dependencies

A Spring MVC app might declare corresponding dependencies:

~~~text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-aop
org.springframework.boot:spring-boot-starter-actuator
io.github.resilience4j:resilience4j-spring-boot3:<compatible-version>
io.github.resilience4j:resilience4j-micrometer:<compatible-version>
~~~

These are **illustrative library coordinates**, not a complete Gradle/POM file. Select a Resilience4j version compatible with your Spring Boot and JDK versions. For WebFlux and `CompletionStage` apps, configure reactive/async integration properly; `@TimeLimiter` does not automatically enforce hard deadlines on arbitrary synchronous return types.

### 9.2. HTTP Client with Connection and Read Timeouts

~~~java
package example.orders;

import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.HttpClientErrorException;
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;

@Component
public class InventoryGateway {
    private final RestClient http;

    public InventoryGateway(RestClient.Builder builder) {
        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(200); // milliseconds
        requestFactory.setReadTimeout(450);    // milliseconds
        this.http = builder
            .baseUrl("https://inventory.internal.example")
            .requestFactory(requestFactory)
            .build();
    }

    @Bulkhead(name = "inventory", type = Bulkhead.Type.SEMAPHORE)
    @CircuitBreaker(name = "inventory")
    @Retry(name = "inventory")
    public InventoryResult checkStock(String sku) {
        return http.get()
            .uri("/v1/stock/{sku}", sku)
            .retrieve()
            .body(InventoryResult.class);
    }
}
~~~

In this example, `InventoryResult` is an application DTO, such as:

~~~java
package example.orders;

public record InventoryResult(String sku, boolean available, int quantity) {}
~~~

The host `inventory.internal.example` is a placeholder and must be replaced with a real endpoint using proper TLS and authentication. Even with a 200 ms connect timeout and 450 ms read timeout, those two settings **do not guarantee a hard 650 ms end-to-end timeout**. Enforce overall deadlines at the service orchestration / API gateway tier and verify how your HTTP client behaves on chunked responses.

Resilience4j annotations typically apply via Spring AOP proxies. **Calling `checkStock` from another method inside the same object (self-invocation) can bypass the proxy and skip policies.** Invoke through a Spring-managed bean and verify behavior with tests.

### 9.3. Retry, Circuit Breaker, and Bulkhead Configuration

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 150ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 400ms
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 3
        recordExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - org.springframework.web.client.HttpClientErrorException

  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
~~~

**Limitations of this illustrative configuration:**

- `maxAttempts: 3` covers the initial call plus up to two retries. `waitDuration` + exponential backoff here omits jitter; in production, add randomization via the library's supported API or a supported retry policy.
- **4xx** exceptions are excluded from retries and circuit breaking. **HTTP 429** is often mapped by `RestClient` as a 4xx exception; retrying 429s with `Retry-After` requires a dedicated handler/predicate. Never enable blind retries for all 4xx responses.
- Other exceptions, including bulkhead/circuit-breaker rejections, must be classified explicitly so **retries do not fire when the circuit is open or the bulkhead is full**.
- `ResourceAccessException` can cover connect or read timeouts; never assume every I/O error is safe to retry for write operations.
- `@TimeLimiter` targets async/`CompletionStage` or reactive methods with matching integration. This synchronous snippet configures HTTP client timeouts only and still needs an **overall deadline** at orchestration.
- Circuit breaker metrics depend on actual AOP aspect ordering; verify in a running environment before finalizing thresholds.

### 9.4. Keeping Fallbacks Separate from Downstream Transport

The business service decides how to degrade when `InventoryGateway` fails. Rather than assuming stock exists, return a status requiring verification:

~~~java
package example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderAvailabilityService {
    private final InventoryGateway inventoryGateway;

    public OrderAvailabilityService(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    public AvailabilityStatus lookup(String sku) {
        try {
            var result = inventoryGateway.checkStock(sku);
            return result.available()
                ? AvailabilityStatus.AVAILABLE
                : AvailabilityStatus.OUT_OF_STOCK;
        } catch (RuntimeException failure) {
            // Log centrally without sensitive details.
            // Classify specific exceptions to choose an appropriate HTTP response.
            return AvailabilityStatus.UNKNOWN_TEMPORARILY;
        }
    }

    public enum AvailabilityStatus {
        AVAILABLE, OUT_OF_STOCK, UNKNOWN_TEMPORARILY
    }
}
~~~

This snippet demonstrates a **business-safe fallback**, not a complete production endpoint. In real code, catch classified exception groups rather than broad `RuntimeException` so programming bugs are not masked. When stock cannot be verified, place the order flow in a pending check state or return a controlled error—never turn `UNKNOWN_TEMPORARILY` into `AVAILABLE`.

### 9.5. Tighter Timeouts for Async Flows

For asynchronous APIs, combine `CompletionStage + TimeLimiter` or Reactor `timeout(Duration)` per your framework's return types. Active async timeouts stop caller waiting promptly, though you must confirm whether cancellation stops underlying I/O. Conceptual Spring WebFlux example:

~~~java
Mono<InventoryResult> result = inventoryWebClient.get()
    .uri("/v1/stock/{sku}", sku)
    .retrieve()
    .bodyToMono(InventoryResult.class)
    .timeout(Duration.ofMillis(450));
~~~

This requires a configured `inventoryWebClient` and Reactor/WebClient imports. It illustrates a single reactive publisher timeout; if adding `retryWhen`, check operator placement relative to `timeout` to know whether the cap applies per attempt or to the entire sequence. An overall deadline remains an independent boundary.

## 10. On Azure: What Policies Exist Built-In vs. What You Must Add

Infrastructure layers may already handle some transient faults. Before adding application retries, inspect built-in behaviors:

| Azure component | Built-in mechanism | What the app still must do |
| --- | --- | --- |
| **Azure Storage SDK** | Typically includes transient retry policies per SDK config | Set deadlines, idempotency, retry budgets; avoid nested retries |
| **Azure Cosmos DB SDK** | Handles throttling, 429 codes, and wait hints per SDK | Track RU/s, latency, request charge; optimize partitions and capacity |
| **Azure Service Bus SDK** | Retries service operations; message processing supports redelivery | Build idempotent consumers, manage lock duration, max delivery count, dead-lettering |
| **Azure Functions** | Certain triggers support host/trigger retries and error handling | Verify exact trigger behavior, retry counts, message/poison handling |
| **Azure API Management** | Offers policies such as retry and timeout/forward-request | Assign one retry owner, enforce system-wide caps, avoid replaying writes |
| **Azure Front Door / Application Gateway** | Configurable timeouts, routing, health probes | Ensure matching app deadlines and degradation plans |
| **AKS / Container Apps / App Service** | Scaling and health checks per deployment model | Never treat scaling or health probes as replacements for retries/breakers/bulkheads |

This is a **conceptual overview** and does not claim every SDK version or service tier shares identical default retry counts, timeouts, or policies. Check your exact SDK version, resource/namespace config, and current service documentation.

### 10.1. Azure Cosmos DB: Retries Must Pair with Capacity

If Cosmos DB returns 429 due to insufficient Request Units (RU/s), the SDK may wait and retry. If the caller wraps that in an outer retry policy, total duration can blow past the user's SLA. Fixes go beyond raising retries—inspect:

- Partition keys and RU distribution across partitions.
- Expensive queries or hot-partition access patterns.
- Autoscale throughput, provisioned RU/s, and cost.
- `Retry-After` values, total latency, and failing fast when deadlines expire.

Retrying a read differs from retrying a conditional write (ETag) or stored procedure; evaluate business semantics and SDK behavior.

### 10.2. Azure Service Bus: At-Least-Once Delivery and Dead-Lettering

A consumer receiving messages in **Peek-Lock** mode might complete processing yet fail before calling **Complete**. When the lock expires or the message is abandoned, Service Bus redelivers it. That yields **at-least-once** semantics, so consumers must be idempotent and persist processing records where required.

Reference flow:

~~~mermaid
flowchart TD
    A["Service Bus receives message"] --> B["Consumer checks deduplication"]
    B --> C{"Already processed successfully?"}
    C -->|"Yes"| D["Complete message; skip duplicate work"]
    C -->|"No"| E["Process with deadline and concurrency limit"]
    E -->|"Success"| F["Persist outcome durably + Complete"]
    E -->|"Transient error"| G["Controlled retry / await redelivery"]
    E -->|"Poison message"| H["Dead-letter + alert"]
~~~

Business state persistence and message completion usually do not share a single cross-system transaction, so design explicit deduplication and recovery. `MaxDeliveryCount`, dead-letter queues (DLQs), lock duration, and auto-lock renewal are key operational controls; an in-process retry loop must never run unbounded until the lock expires. Move persistently failing messages to the DLQ with clear reasons for investigation and controlled replay after fixing the root cause.

### 10.3. Per-Replica Circuit Breakers

In multi-replica AKS or Container Apps deployments, Resilience4j circuit breakers and semaphore bulkheads **typically maintain local in-process state**. When one replica opens its breaker, other replicas may keep sending requests. Account for this when:

- Sizing aggregate concurrency sent to a dependency.
- Estimating allowed half-open probe volume across all replicas.
- Scaling replica counts alongside real concurrency.
- Explaining why some requests succeed while others fail fast.

Do not treat a local breaker as a cluster-wide kill switch. If global throttling is needed, evaluate distributed rate limiting or admission control without introducing a new single point of failure.

## 11. Designing SLOs and Observing via Azure Monitor

Resilience patterns are measurable operational mechanisms, not just code annotations. Monitor at minimum:

| Metric group | Examples | Significance |
| --- | --- | --- |
| **Latency** | End-to-end and per-dependency p50, p95, p99 | Distinguishes average improvements from worsening tail latency |
| **Success/error** | 2xx, 4xx, 5xx rates; timeouts; network errors | Identifies failure types and trends |
| **Retries** | Total attempts, retry counts, retry amplification | Detects retry storms |
| **Circuit breaker** | State transitions, open duration, calls not permitted | Confirms whether a dependency is genuinely unhealthy |
| **Bulkhead** | Available permits, rejected calls, queued/active tasks | Surfaces contention and resource exhaustion risk |
| **Dependency health** | Connection pools, DB latency, RU/throttling | Targets root causes |
| **Business** | Order creation success rate, pending orders, duplicate payments | Prevents fallbacks from silently corrupting business metrics |

With **Azure Monitor / Application Insights**, correlate traces, dependency telemetry, and custom app metrics. OpenTelemetry propagates trace context across services, revealing how many HTTP attempts a single user request generated. Ensure telemetry never logs tokens, passwords, sensitive payloads, or full URLs carrying private data.

Example **Kusto Query Language (KQL)** query on classic Application Insights tables:

~~~kusto
dependencies
| where timestamp >= ago(30m)
| summarize
    calls = count(),
    failures = countif(success == false),
    p95Ms = percentile(duration / 1ms, 95)
  by target, type
| order by failures desc
~~~

Workspace-based Application Insights setups use different table/column names, such as `AppDependencies`, `TimeGenerated`, and `DurationMs`. Adjust table and column names to match your Log Analytics workspace; this query illustrates analyzing **failures and p95 dependency latency** and is not guaranteed to run unmodified in every workspace.

### 11.1. Sound SLIs, SLOs, and Alerts

Suppose **orders-api** has an SLO of **99.9% of valid requests returning within 2 seconds** over the defined window. Even when retries boost success rates, requests taking longer than 2 seconds still violate the latency SLO.

Do not page production merely because a breaker opened briefly for a few seconds—that may be working protection. Instead, track **final error rates, sustained OPEN duration, rejected call spikes, retry amplification, dependency latency, and error-budget burn**.

Dashboards should separate **pre-retry failures** from **post-retry outcomes**. Reporting only final success can blind teams to severe underlying dependency degradation.

## 12. Tuning Policies with Measurements, Not Guesswork

A structured calibration workflow:

1. **Measure baseline:** RPS, concurrency, p50/p95/p99, timeouts, 429/503 rates, connection pools, and CPU/memory.
2. **Set business deadline:** aligned with user response targets and gateway limits.
3. **Partition time budget:** latencies for serial/parallel steps, retry waits, and fallbacks.
4. **Select retry conditions:** transient errors and safe operations only; audit built-in SDK retries.
5. **Size bulkheads:** base on downstream throughput, latency, and capacity across all replicas.
6. **Tune breakers:** adequate sample sizes, error/slow thresholds, and probe durations.
7. **Test faults:** inject delays, 503s, 429s, network resets, overload; observe cross-service blast radius.
8. **Monitor post-rollout:** check latency targets, rejection rates, and cost, adjusting one parameter at a time.

For example, a workload handles **200 requests/second** across 4 replicas—50 requests/second per replica on average. If inventory calls average 200 ms and only 70% of requests call inventory, average per-replica inventory concurrency is roughly:

\[
50 \times 0.7 \times 0.2 = 7
\]

The number 7 ignores bursts and tail latency. Starting with 12–16 bulkhead slots per replica is a load-test hypothesis, not a universal formula. Across 4 replicas, peak concurrency reaches 48–64 calls. If inventory only handles 30 concurrent calls, tighten limits, add admission control, or scale inventory before scaling callers.

**Never raise retry counts to mask chronic under-capacity.** Real fixes include rate limiting, async queues, TTL caching, reducing fan-out, optimizing queries, or scaling downstream capacity.

## 13. Hands-On Exercise: Designing and Testing Fault Tolerance

**Context:** `orders-api` on Azure App Service/AKS/Container Apps calls `inventory-api` via HTTP GET. Normally inventory responds in 120 ms. During an incident, 30% of calls fail with HTTP 503 and 20% take over 2 seconds. Requirements: respond to users within 2 seconds, avoid flooding inventory, and keep non-inventory features working.

### Step 1 — Define the Business Contract

Document clearly:

- Whether inventory GET is safe to retry and how stale cached data may be.
- When inventory cannot confirm stock, whether orders are blocked, marked pending, or queued asynchronously.
- Which requests return HTTP 503/429 vs. 202 Accepted.
- Acceptable user error rates and maximum wait times.

**Expected artifact:** an error-classification and fallback table, not merely a list of HTTP status codes.

### Step 2 — Choose Trial Configuration

Initial values to test and refine against real measurements:

| Mechanism | Initial value |
| --- | --- |
| Overall deadline | 2,000 ms |
| Connection timeout | 200 ms |
| Per-attempt response timeout | 450 ms |
| Retry | Max 3 attempts, 150/300 ms exponential backoff with jitter |
| Circuit breaker | Window 20, min 10 calls, 50% failure threshold, 30s open wait |
| Bulkhead | 20 concurrent calls/replica, zero queue |
| Fallback | `UNKNOWN_TEMPORARILY`, never assume in stock |

**Note:** the Java HTTP client timeouts shown earlier do not create a hard 450 ms deadline on their own; add request-level deadlines and an overall service deadline.

### Step 3 — Controlled Fault Simulation

Run in an authorized test environment with non-sensitive data:

1. **Baseline:** healthy inventory; measure p95/p99, RPS, CPU, active concurrency, and success rate.
2. **Delay:** inject latency above the per-attempt timeout; verify requests do not hang indefinitely.
3. **503:** inject transient errors; verify bounded retries and backoff/jitter.
4. **429:** return `Retry-After`; confirm client honors it without breaching the overall deadline.
5. **Burst:** spike concurrency suddenly; verify bulkhead rejects cleanly while independent endpoints keep responding.
6. **Sustained failure:** keep errors high; verify breaker trips OPEN and downstream traffic drops.
7. **Recovery:** restore inventory; observe HALF_OPEN, probes, and return to CLOSED.
8. **Duplicate operation:** test write APIs with idempotency keys to ensure retries never duplicate orders or payments.

Use HTTP fault simulators, test network proxies, or environment-appropriate fault-injection tools. **Never run chaos experiments on production** without approved scope, guardrails, timing, and operational controls.

### Step 4 — Acceptance Criteria

A passing exercise must show evidence that:

- Attempts per request have a clear ceiling and cannot grow unbounded.
- Timed-out requests exit within the budgeted window, including overhead.
- Downstream does not receive retry traffic spikes; retry amplification is measured.
- Independent endpoints retain capacity while inventory fails.
- Circuit breaker transitions accurately with bounded recovery probes.
- Write paths create zero duplicate side effects; fallbacks never report false business outcomes.
- Dashboards separate pre-retry and post-retry errors; alerts measure real user impact.

**Practice report** should include the call diagram, actual config table, fault-test outcomes, latency/error graphs, retry counts, breaker states, bulkhead rejections, and tuning proposals. Omit secrets, access tokens, and real customer data.

## 14. Common Implementation Pitfalls and Fixes

| Symptom | Common cause | How to inspect and fix |
| --- | --- | --- |
| Requests hang for seconds despite short read timeout | Timeout applies per read operation; no overall deadline | Separate connect/read/request/deadline; measure total elapsed time |
| Errors rise after enabling retries | Retry storm, non-transient errors, multi-layer retries | Lower max attempts, add jitter/budget, audit SDK retries |
| Duplicate payments or orders occur | Retrying POST without idempotency | Add idempotency keys and server-side deduplication |
| Breaker stays CLOSED even when dependency is slow | Counting exceptions only, ignoring slow calls, or too few samples | Check error filters, slow-call threshold, window, and metrics |
| Breaker stays OPEN constantly | Overly sensitive threshold, probes fail, or downstream still broken | Check sample counts, probe behavior, latency, and root cause |
| Annotations added but policies do not run | Spring AOP self-invocation, missing AOP starter, wrong bean | Verify dependencies, proxy boundaries, call paths, and actuator metrics |
| Bulkhead capped at 20 yet app still stalls | Shared thread/connection pools or unisolated blocking elsewhere | Inspect thread dumps, connection pools, queues, and event loops |
| 429s keep climbing | Retries ignore `Retry-After` or exceed RU/s/API quotas | Throttle rate and adjust capacity or rate limits |
| Service Bus processes duplicates | Lock expires or `Complete` fails, triggering redelivery | Use idempotent consumers, lock renewal, and DLQ |
| Autoscale kills downstream faster | Each replica holds a local bulkhead, multiplying aggregate concurrency | Sum slots across replicas and cap to downstream capacity |
| Fallbacks hide system outages | Catching all exceptions and returning fake business success | Return meaningful degraded states, classify errors, and alert |
| Timeout fires yet downstream still consumes resources | Cancellation does not propagate or queries stay running | Verify cancellation propagation, DB timeouts, and server cleanup |

## 15. Self-Check Questions

**Question 1.** A GET API returns HTTP 503 after 200 ms with 1 second left on the deadline. Should you retry?  
**Suggested answer:** Yes, provided the API is safe to call again, retry budget remains, backoff/jitter is applied, and no lower layer already exhausted the retry budget.

**Question 2.** Why can raising `maxAttempts` from 3 to 10 make a system less reliable?  
**Suggested answer:** It piles load onto an already struggling dependency, consumes more time and threads/connections, worsens tail latency, and risks a retry storm.

**Question 3.** Should an OPEN circuit breaker continuously send requests to check if the dependency recovered?  
**Suggested answer:** No. An OPEN breaker must fail fast and allow only a bounded number of probe calls after transitioning to HALF_OPEN per policy wait duration.

**Question 4.** Does a 20-slot/replica bulkhead across 6 replicas enforce a cluster-wide limit of 20 requests?  
**Suggested answer:** No. It allows up to roughly 120 concurrent calls across all replicas; size against total capacity and add higher-level limits if needed.

**Question 5.** Does a client-side timeout prove a payment request was never processed?  
**Suggested answer:** No. The server may have finished before the response dropped; use idempotency keys and status reconciliation.

**Question 6.** Why can post-retry success rate be misleading?  
**Suggested answer:** Users may still suffer high latency, initial attempts may fail heavily, and downstream faces extra attempts, resource usage, and cost. Track both attempt counts and latency.

**Question 7.** Should Resilience4j retry every exception thrown by `RestClient`?  
**Suggested answer:** No. Classify failures, distinguish 4xx vs. 5xx appropriately, and account for idempotency, deadlines, and built-in SDK/gateway retries.

**Question 8.** What is the difference between a timeout and a circuit breaker?  
**Suggested answer:** A timeout bounds a single wait; a circuit breaker tracks errors/slow calls across multiple calls and proactively blocks new calls for a period to stop error amplification.

## 16. Azure Project Implementation Checklist

- [ ] Every dependency documents error classifications and retry conditions.
- [ ] Write operations are protected with appropriate idempotency/deduplication.
- [ ] Overall deadlines and per-attempt timeouts align across gateway, SDK, and app.
- [ ] Retries enforce max attempts, backoff/jitter, retry budgets, and `Retry-After`.
- [ ] Built-in retries in Azure SDKs, gateways, Functions, and message consumers are audited.
- [ ] Circuit breakers track errors/slow calls properly with sensible sample windows and HALF_OPEN probes.
- [ ] Bulkheads cap concurrency/queues considering total replica count and connection pools.
- [ ] Fallbacks never compromise business decisions or transactional integrity.
- [ ] Application Insights / Azure Monitor records latency, retries, breakers, bulkheads, dependency health, and business metrics.
- [ ] Delay, 429, 503, network failure, overload, and recovery scenarios are tested in a controlled environment.
- [ ] Alerts exist for SLO/error budget burn and runbooks guide dependency degradation response.

**Key takeaway:** Timeouts cap waiting; retries handle transient errors; circuit breakers stop calling degraded dependencies; bulkheads prevent one failing dependency from starving the app. Together they work best when anchored in **deadlines, load bounds, idempotency, observability, and business correctness**—the foundation for Azure applications that absorb partial failures while protecting user experience and recovering cleanly.
