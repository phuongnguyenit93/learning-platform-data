# Circuit Breakers, Concurrency Limits, and Graceful Degradation

When a managed service responds slowly or goes down, waiting requests can tie up every thread, connection pool slot, and memory buffer in a Spring Boot application. New requests continue flowing toward the failing dependency, piling on load and dragging down other services. An initial fault in storage, a database, or messaging can turn into a widespread outage.

Three mechanisms must work together to contain the blast radius:

- **Circuit breaker:** temporarily stops calling a dependency when error rates or response times cross thresholds, then probes in a controlled manner once the dependency may have recovered.
- **Concurrency limits and bulkheads:** bound active requests and isolate resources so one dependency or request group cannot exhaust the application's entire capacity.
- **Graceful degradation:** preserves safe functionality when a dependency is unavailable, such as serving explicitly marked cached data, disabling non-core features, or returning a pending status.

A circuit breaker does not replace timeouts, retries, rate limits, or bulkheads. Each mechanism addresses a distinct category of risk. In the Spring Cloud Provider Integration module, these mechanisms apply when Spring Boot calls Azure, AWS, and Google Cloud managed services, while accounting for built-in retries and throttling in each provider's SDK.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain failure cascades and why a slow dependency can exhaust application threads and connections.
2. Describe the CLOSED, OPEN, and HALF_OPEN states of a circuit breaker.
3. Choose sliding windows, failure thresholds, slow-call thresholds, and half-open probe counts.
4. Distinguish timeouts, retries, circuit breakers, bulkheads, concurrency limits, and rate limiters.
5. Design timeout budgets, retry budgets, and admission control.
6. Isolate resources by dependency, operation, or tenant.
7. Design fallbacks and graceful degradation that do not mask business errors.
8. Configure Spring Boot with Spring Cloud CircuitBreaker and Resilience4j.
9. Coordinate application resilience policies with cloud provider SDK retries, quotas, and throttling.
10. Measure, test, and operate recovery mechanisms when dependencies are slow or unavailable.

## 2. Failure Cascades: One Slow Dependency Can Bring Down Many Parts

Suppose the Order API calls the Inventory service, a database, and a Payment provider. Inventory slows down from 100 ms to 8 seconds. If each request holds a servlet thread while waiting, active request counts climb rapidly.

~~~mermaid
flowchart TD
    A[Client requests rise] --> B[Order API calls Inventory]
    B --> C[Inventory responds slowly]
    C --> D[Requests hold threads and connections]
    D --> E[Thread pool / connection pool exhausted]
    E --> F[Other requests time out]
    F --> G[Retries add further load]
    G --> C
    E --> H[Payment / database / health endpoints impacted]
~~~

The problem is not just that Inventory is unhealthy. Order API keeps accepting new requests, holds resources longer, adds retries, and starves unrelated dependencies. This is a **cascading failure** or failure cascade.

A fault-tolerant system must:

- Detect slow or failing dependencies.
- Stop generating futile extra load.
- Bound how many requests are allowed to wait.
- Reserve dedicated resources for critical functions.
- Provide alternative execution paths where business rules allow.
- Recover gradually to avoid triggering a fresh load spike.

## 3. Four Distinct Mechanisms: Timeout, Retry, Circuit Breaker, and Bulkhead

| Mechanism | Question It Answers | Effect |
| --- | --- | --- |
| **Timeout** | How long at most to wait for one call? | Prevents requests from hanging indefinitely |
| **Retry** | Should transient errors be re-attempted? | Recovers from brief glitches |
| **Circuit breaker** | Should we keep calling a failing dependency? | Pauses calls with high failure probability |
| **Bulkhead/concurrency limit** | How many calls may run simultaneously? | Caps resources and isolates load |

You can add a **rate limiter** to bound call rate over time and **load shedding** to reject work early when overloaded.

Examples:

- A 2-second timeout bounds wait time for one request.
- At most one retry with backoff on recoverable throttling errors.
- A circuit breaker transitions to OPEN after observing high failure rates, rejecting new calls for a cooldown period.
- A bulkhead allows at most 20 concurrent Inventory calls.
- A rate limiter permits up to 100 requests/second per allocated quota.

No single mechanism replaces the others.

## 4. How Does a Circuit Breaker Work?

A circuit breaker tracks outcomes of dependency calls and transitions state when configured conditions are met.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure / slow-call threshold reached
    OPEN --> HALF_OPEN: Wait duration elapsed
    HALF_OPEN --> CLOSED: Probe calls succeed
    HALF_OPEN --> OPEN: Probe calls fail
~~~

### CLOSED

- Requests are allowed through to the dependency.
- The circuit breaker records successes, errors, and/or response durations.
- When failure rate or slow-call rate exceeds thresholds within the observation window, the breaker trips to OPEN.

### OPEN

- New requests fail fast without calling the dependency.
- The application can run a fallback or return an appropriate error.
- After the wait duration, the breaker transitions to HALF_OPEN (automatically or on the next call, depending on configuration).

### HALF_OPEN

- Only a small number of probe calls are permitted.
- If probes succeed per policy, the breaker transitions back to CLOSED.
- If probes fail or run too slowly, the breaker returns to OPEN.
- Requests exceeding the permitted probe count are still rejected.

### Why Is HALF_OPEN Needed?

If every instance suddenly sends thousands of requests the moment a dependency recovers from an outage, the service can overload again immediately. HALF_OPEN caps probe traffic and ramps back up only with evidence of recovery.

Tripping to OPEN does not necessarily cancel in-flight requests already sent. In-flight calls still require their own timeouts/cancellation.

## 5. Failure Rate and Slow-Call Rate

A circuit breaker can evaluate two signals:

- **Failure rate:** fraction of calls treated as failures in the sliding window.
- **Slow-call rate:** fraction of calls exceeding a duration considered slow.

Example with a 20-call window:

- 10 calls fail → failure rate is 50%.
- 12 calls take longer than 2 seconds → slow-call rate is 60%.

If the respective thresholds are 50% and 60%, the breaker can trip OPEN once minimum call count and configured conditions are satisfied.

### Parameters to Choose

| Parameter | Meaning | Design Question |
| --- | --- | --- |
| Sliding window type | Count-based or time-based window | Is traffic steady or bursty? |
| Sliding window size | Number of calls or seconds observed | How quickly must the breaker react? |
| Minimum number of calls | Minimum calls before calculating rates | Avoid tripping from a single isolated error |
| Failure rate threshold | Error percentage triggering OPEN | What error rate is unacceptable? |
| Slow-call duration threshold | Duration above which a call counts as slow | Fits the operation's latency budget? |
| Slow-call rate threshold | Slow-call percentage triggering OPEN | How slow before stopping calls? |
| Wait duration in OPEN | How long the circuit stays OPEN | How long does the dependency typically take to recover? |
| Permitted calls in HALF_OPEN | Number of probes allowed | How many probes give enough confidence? |

Never copy one set of thresholds across every dependency. A cache query, payment write, and file upload have completely different latency profiles, risks, and SLAs.

## 6. Which Errors Should Count Toward the Circuit Breaker?

Not every exception proves the dependency is unhealthy.

Distinguish:

- Network timeouts, connection resets, service unavailable: typically dependency failures.
- HTTP 429 or throttling errors: dependency/quota is throttled; may count as failures, but coordinate with Retry-After and rate control.
- HTTP 5xx: typically server-side errors, depending on the operation.
- HTTP 400 from bad payloads: caller/application error; should not trip the breaker.
- HTTP 401/403 from missing permissions: configuration/identity error; usually needs alerting and separate handling—continuous retries will not fix it.
- Business rejections like insufficient inventory or payment declined: valid business outcomes, not a dependency outage.
- Application validation exceptions: do not count as external service errors.

Use deliberate exception allowlists/denylists. If the breaker counts every RuntimeException, a code bug or business rejection can trip the circuit OPEN even when the dependency is healthy.

### Ignoring vs. Recording Exceptions

In Resilience4j, you can configure which exceptions to record and which to ignore. Avoid conflicting settings and verify precedence rules for your library version.

When an exception is ignored, it does not inflate the failure rate. Yet the application must still return an appropriate business response and emit logs/metrics for that error.

## 7. A Circuit Breaker Does Not Limit Concurrency

An OPEN circuit breaker blocks new calls after thresholds are crossed. While still CLOSED, however, it permits huge numbers of concurrent requests. If a dependency slows down before enough calls finish to trip the circuit, threads and connections can still exhaust.

Therefore combine:

- Timeouts to bound wait duration.
- Bulkheads/concurrency limits to bound in-flight calls.
- Circuit breakers to stop calling dependencies with high failure/slow-call rates.
- Rate limiters to cap request rate.
- Queue bounds to cap waiting work.

These are distinct layers of protection.

## 8. Bulkheads and Concurrency Limits

Bulkheads borrow from ship compartments: flooding one compartment does not sink the whole ship. In an application, each dependency or workload gets its own resource budget.

Example:

~~~text
Order API thread pool: 200 threads
  ├── Inventory calls: max 20 concurrent
  ├── Payment calls: max 10 concurrent
  ├── Blob uploads: max 8 concurrent
  └── Optional recommendations: max 5 concurrent
~~~

If Inventory slows down, it can occupy at most its 20 allocated slots. Payment and other features retain capacity to operate.

### Semaphore Bulkhead

A semaphore bulkhead caps active calls:

- Creates no separate thread pool.
- Calls execute on the caller's thread.
- Can configure how long to wait for a permit.
- When permits run out, requests are rejected or wait briefly per policy.

Suited for synchronous calls when you want to limit in-flight calls without adding extra executors.

### Thread-Pool Bulkhead

A thread-pool bulkhead uses a dedicated executor and queue:

- Separates dependency workers from the main thread pool.
- Uses a bounded queue.
- Can isolate blocking calls.
- When both threads and queue are full, requests are rejected.
- Costs extra threads, context switching, and lifecycle management.

Suited when you need to isolate a group of blocking tasks. The queue must be bounded; an unbounded queue just converts overload into latency and memory growth.

### Choosing Semaphore vs. Thread Pool

| Criterion | Semaphore Bulkhead | Thread-Pool Bulkhead |
| --- | --- | --- |
| Thread isolation | No separate pool | Dedicated executor |
| Caps in-flight calls | Yes | Yes |
| Queue | Usually no separate work queue | Bounded queue |
| Overhead | Lower | Higher |
| Blocking calls | Runs on calling thread | Can isolate from request threads |
| Best fit | Simple concurrency caps | Isolating blocking work and bounded queuing |

Never use a thread-pool bulkhead to mask a slow dependency by growing the queue. The goal is to contain blast radius and fail fast under overload.

## 9. Concurrency Limits, Rate Limits, and Admission Control

Three related but distinct concepts:

- **Concurrency limit:** maximum requests executing simultaneously.
- **Rate limit:** maximum requests accepted per unit of time.
- **Admission control:** deciding whether to accept new work or reject immediately based on current capacity.

For example, a dependency handles 50 requests/second, each taking 2 seconds. Maintaining that throughput requires around 100 concurrent in-flight requests. Yet if latency climbs to 10 seconds, keeping the same concurrency can slash throughput and balloon backlogs.

Concurrency limits protect active resource slots. Rate limiters protect time-window quotas. Admission control combines thread pool state, queue depth, deadlines, and priority to decide whether to admit incoming work.

### Never Queue Indefinitely

A long queue can keep requests waiting past the client's deadline. By the time a request finally runs, the client has already timed out and sent another retry.

Use bounded queues and define:

- Queue capacity.
- Maximum queue wait.
- Job deadline/TTL.
- Priority or per-tenant fairness.
- Action when full: reject, shed, or durably enqueue to a managed queue.
- Metrics for queue depth and oldest wait time.

### Per-Tenant Fairness

One tenant sending a huge burst should not starve shared dependency capacity for everyone else. Enforce per-tenant or per-tier concurrency/rate budgets, while avoiding creating unbounded numbers of uncleaned limiter instances.

## 10. Timeout Budgets and Deadline Propagation

Timeouts must be designed across the whole request path, not configured in isolation per layer.

Example API with a 3-second deadline:

~~~text
Client deadline: 3.0 s
  ├── Authentication / validation: 0.2 s
  ├── Inventory call: 1.0 s
  ├── Database: 0.8 s
  └── Response / safety margin: 1.0 s
~~~

If every dependency uses a 3-second timeout, the overall request can stretch to multiples of the client's deadline.

### Timeouts Needed Across Layers

- Connection timeout: time to establish a connection.
- Read/response timeout: time waiting for a response.
- Request/operation timeout: deadline for a single call.
- Queue wait timeout: time waiting for a permit or executor.
- Overall request deadline: bound on the entire request.
- Broker processing/visibility/lock deadline: aligned with message processing time.

### Deadline Propagation

When service A calls service B, propagate the deadline or remaining timeout so B does not keep working after the caller already gave up. Not every SDK supports uniform deadline propagation; configure client timeouts and cancellation appropriately.

For blocking SDK calls, canceling a Future or TimeLimiter does not guarantee the underlying network operation stops if the client ignores interrupts. Always configure timeouts directly in the HTTP client/cloud SDK.

## 11. Retries Need Budgets and Backoff

Retries help on brief glitches, yet unbounded retries amplify incidents.

If each request retries 3 times across 3 layers (API, service, and SDK), call counts multiply. When a dependency is already overloaded, a retry storm makes recovery harder.

### Retry Policy

- Retry only recoverable errors.
- Cap maximum attempts.
- Use exponential backoff and jitter.
- Honor Retry-After when returned by the service.
- Never retry when insufficient overall deadline remains.
- Use idempotency keys on write operations.
- Never retry business rejections or validation errors.
- Designate one primary layer as retry owner.

### Circuit Breaker and Retry Ordering

Decorator order changes what the breaker observes:

- If **circuit breaker wraps retry**, one logical operation counts as one call; measured duration may span all retries.
- If **retry wraps circuit breaker**, each attempt is observed individually by the breaker; one logical operation can increment failure counters multiple times.

No single order fits all cases. Choose based on what you want to measure and verify the aspect/decorator order of your Resilience4j version. Either way, retries must stay inside a global budget.

## 12. Graceful Degradation: Keeping Safe Functionality Alive

Graceful degradation means designing the system to continue delivering whatever safe value remains possible when a dependency is unavailable.

Examples:

| Failing Dependency | Possible Degradation |
| --- | --- |
| Recommendation API | Hide recommendation widgets; still allow search and checkout |
| Product image storage | Show placeholder or metadata; keep product page usable |
| Read replica/search index | Serve cache or fall back to primary within strict limits |
| Notification provider | Save notification intent to outbox; send later |
| Analytics | Buffer/queue or pause analytics; never block checkout |
| Inventory service | Show unconfirmed status; do not falsely claim items are in stock |
| Payment provider | Keep order in PAYMENT_PENDING; do not mark paid |

### Fallbacks Must Be Honest

Fallbacks must never turn an error into a fake business success:

- Never return "payment successful" when the payment provider timed out.
- Never display exact stock levels from stale caches without marking staleness.
- Never claim a notification was sent when it was only written to an outbox.
- Never serve stale data without freshness metadata/staleness bounds when callers need current data.
- Never return success on a write if the intent was not durably persisted.

Fallbacks should surface explicit states such as PENDING, STALE, UNAVAILABLE, or DEGRADED per the API contract.

## 13. Common Fallback Patterns

### Cache Fallback

Read recent cached data when the primary source is unavailable:

- Store cachedAt or version.
- Enforce maximum staleness.
- Use only for data where staleness is acceptable.
- Never use stale caches for authoritative payments, balances, or absolute inventory without explicit policy.

### Feature Fallback

Disable non-essential features:

- Drop recommendations.
- Hide real-time statistics.
- Serve a simplified layout.
- Pause large exports or reports.

### Async Acceptance

When synchronous execution cannot finish, durably persist a command/outbox record and return HTTP 202 Accepted with an operation ID. Return 202 only after the intent is durably persisted. Clients poll status later.

### Read-Only Mode

When write dependencies fail, allow safe reads while temporarily rejecting writes. Clearly indicate that read data may be stale.

### Static/Default Response

Return default values only when they cannot mislead. For example, a placeholder image is fine; defaulting an account balance to 0 is not.

## 14. Load Shedding and Prioritizing Work

When processing capacity falls below incoming traffic, you cannot keep every request queued forever. **Load shedding** rejects lower-priority work to protect critical paths.

Prioritize:

- Payment/order state transitions over analytics.
- Interactive user requests over batch backfills.
- Tenants within quota/priority tiers.
- Work with enough remaining deadline.
- Work that can safely be retried later.

Rejecting early is usually better than letting requests wait until their deadline expires and fail anyway. APIs can return 429 Too Many Requests when clients exceed rate quotas, or 503 Service Unavailable when servers/dependencies temporarily cannot accept more load. Include Retry-After when you can offer a reasonable retry window.

Never return 429/503 to mask business validation errors; status codes must accurately reflect the problem category.

## 15. Spring Boot and Resilience4j

Resilience4j provides circuit breaker, retry, bulkhead, rate limiter, and time limiter modules. Spring Cloud CircuitBreaker offers an abstraction for applications to call through a unified API backed by the chosen implementation.

The examples below illustrate structure; align dependencies and configuration with your project's Spring Boot, Spring Cloud release train, and Resilience4j versions.

### 15.1. Circuit Breaker Annotation

~~~java
@Service
public class InventoryClient {

    private final InventoryHttpClient httpClient;

    public InventoryClient(InventoryHttpClient httpClient) {
        this.httpClient = httpClient;
    }

    @CircuitBreaker(
            name = "inventory",
            fallbackMethod = "inventoryFallback")
    public InventoryResult getInventory(String sku) {
        return httpClient.getInventory(sku);
    }

    private InventoryResult inventoryFallback(
            String sku,
            Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
~~~

Fallbacks take the original parameters plus the exception at the end per Resilience4j fallback method rules. Verify exact method signatures when using overloads or reactive return types.

In this example, unavailable must represent an unknown/unavailable state. Never return stock count 0 unless that is real data.

### 15.2. Circuit Breaker Configuration

YAML example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

These values are illustrative starting points only. In production, measure baseline latency and error rates, then tune thresholds around SLOs and actual traffic.

### 15.3. Exception Classification

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.io.IOException
          - java.util.concurrent.TimeoutException
        ignoreExceptions:
          - com.example.BusinessRuleException
~~~

This example shows the classification idea. Real exceptions may be wrapped in SDK exceptions or CompletionException; inspect the exception chain observed by the breaker. Never ignore an exception merely to stop the circuit from opening if it is genuinely a dependency failure.

## 16. Configuring Bulkheads and TimeLimiters

### Semaphore Bulkhead

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
~~~

Limits active calls to 20 with zero wait for permits. Once slots fill up, new calls fail fast per policy.

### Thread-Pool Bulkhead

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      blobUpload:
        maxThreadPoolSize: 8
        coreThreadPoolSize: 4
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

Size thread pools and queues according to processing time, CPU, memory, and connection limits. A queue capacity of 16 does not guarantee every request succeeds; once full, callers must receive rejections and appropriate fallbacks/HTTP responses.

### TimeLimiter

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

TimeLimiter works with asynchronous/Future calls per supported integrations. cancelRunningFuture does not guarantee every blocking network call stops immediately. Connect/read/operation timeouts on HTTP clients and cloud SDKs remain mandatory.

## 17. Using the Spring Cloud CircuitBreaker API

Spring Cloud CircuitBreaker lets applications work through CircuitBreakerFactory. Illustrative example:

~~~java
@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public CatalogItem find(String id) {
        return circuitBreakerFactory
                .create("catalog")
                .run(
                    () -> catalogClient.find(id),
                    error -> CatalogItem.unavailable(id));
    }
}
~~~

Exact APIs and fallback configuration depend on the selected implementation/factory. If you need bulkheads, retries, or time limiters, check the corresponding integration; do not assume every factory automatically applies all resilience modules.

### Annotation vs. Programmatic API?

| Style | When Suitable |
| --- | --- |
| Annotations | Clear per-method policy, concise code |
| Programmatic API | Dynamic policy selection, composing operations, or per-call-site fallbacks |
| Spring Cloud CircuitBreaker | Need an abstraction across implementations |
| Resilience4j directly | Need full access to library-specific modules/APIs |

Avoid placing circuit breakers at too many layers for the same dependency without purpose. A request may traverse controller, service, client wrapper, and SDK; independent breakers at every layer make failure rates and fallbacks confusing.

## 18. Reactive vs. Blocking Calls

Spring MVC and WebFlux have different resource models.

- Blocking SDK calls hold threads while waiting.
- Reactive clients release event-loop threads during I/O waits, yet can still exhaust connection pools, pending queues, or memory.
- Never run blocking SDKs directly on a reactive event loop.
- When calling a blocking API is unavoidable, offload to a bounded elastic/dedicated executor.
- A circuit breaker does not make blocking code non-blocking.
- Test timeouts/cancellation against the actual HTTP client and SDK.

In WebFlux, use operators and adapters compatible with reactive publishers. Never wrap a Mono in a Future and block on the event loop.

## 19. Retries and Circuit Breakers in Resilience4j

Multiple modules can be combined:

~~~java
@Retry(name = "inventory")
@CircuitBreaker(name = "inventory")
@Bulkhead(name = "inventory")
public InventoryResult getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

This illustrates composition. Aspect/decorator order depends on configuration and version. Verify:

- Does the breaker count one logical request as one call or multiple retry attempts?
- Is the bulkhead permit held across the whole retry loop or per attempt?
- Does TimeLimiter apply per attempt or to the whole operation?
- Is fallback invoked when retries exhaust or when the breaker is OPEN?
- Are business exceptions retried?
- Does cancellation halt the SDK request?

Do not blindly slap every annotation onto every method. Choose a clear policy owner and test all states.

## 20. Combining with Cloud Provider SDK Retries

Azure, AWS, and Google Cloud SDKs have their own retry, timeout, and throttling behaviors. When adding Resilience4j, calculate total attempts and wait times.

For example, one service call has:
- Application retries: up to 2 attempts.
- SDK retries: up to 3 attempts per call.
- HTTP client retries: another layer.

Actual request volume can exceed expectations. Pick one primary retry owner and cap the total retry budget.

### AWS

AWS SDK retry modes can retry transient/throttling errors depending on service and configuration. When calling DynamoDB, S3, or SQS:

- Distinguish throttling from validation/authorization errors.
- Use bounded SDK timeouts and retry policies.
- Cap concurrency around quotas/service capacity.
- For DynamoDB, monitor throttled requests and consumed capacity.
- For SQS, control receive/delete throughput and consumer concurrency.
- For S3, align timeouts and retries with multipart uploads and cleanup.

### Azure

Azure SDKs/services may return 429, 503, or service-specific throttling/server-busy errors:

- For Cosmos DB, watch RU throttling and Retry-After.
- For Service Bus, handle ServerBusy, lock expiry, and settlement timeouts.
- For Blob Storage, use retry policies while bounding concurrent requests.
- Avoid retrying RBAC/403 errors as if they were temporary outages.
- Monitor quotas/capacity and latency per account, container, or namespace.

### Google Cloud

Google Cloud client libraries apply per-API retry/timeout policies:

- For Pub/Sub, use flow control to limit in-flight messages/bytes.
- For Firestore/Spanner, distinguish transient aborts/resource exhaustion from data or permission errors.
- For Cloud Storage, limit upload/download concurrency and align retries with operation semantics.
- Monitor quotas, 429/503s, and request latency.
- Use idempotency/conditional writes when retrying writes.

Never copy retry settings verbatim across cloud providers. Every SDK has distinct exception types, retryable codes, deadlines, and semantics.

## 21. Designing Fallbacks by Operation Type

### Read Operations

Caches or stale-while-revalidate can be used if staleness is acceptable. Responses should carry timestamps/versions so callers know when the data was last refreshed.

### Write Operations

Never return success unless the write is known to have committed. If an outbox/local durable queue exists, return 202 with an operation ID once the intent is durably persisted. If persistence fails, return a retryable error per the API contract.

### Payments

Never fall back to payment success. On timeout with unknown outcome, hold status as PENDING/UNKNOWN and reconcile via provider reference/idempotency key.

### Messaging

If the broker is unavailable, persist an outbox record inside the database when the local transaction succeeds. Never ACK an inbound message just because downstream publishing failed unless the emit intent is durably stored.

### Optional Features

Disable recommendations, analytics, or thumbnail generation if core functions can continue safely. Track degraded mode so operators know which features are disabled.

## 22. Circuit Breaker Scope Across Multiple Instances

Circuit breakers typically keep state in-process. Each replica maintains its own sliding window and state:

~~~text
Replica A: CLOSED
Replica B: OPEN
Replica C: CLOSED
Replica D: HALF_OPEN
~~~

This happens naturally when traffic and call histories differ across instances. Do not assume a local breaker acts as a cluster-wide circuit.

### Implications

- While one instance is OPEN, others may still call the dependency.
- When the dependency recovers, multiple instances may enter HALF_OPEN and probe simultaneously.
- Autoscaling launches fresh instances with initial breaker state.
- Local rate limiters/concurrency limits do not automatically enforce fleet-wide caps.

### Mitigations

- Keep probe counts small and cap per-instance concurrency.
- Use provider quotas/global rate limits when fleet-wide caps are required.
- Add shared coordination only when genuinely necessary and account for the new dependency it introduces.
- Monitor breaker states per instance and dependency.
- Add jitter to retry/recovery timing to prevent synchronization.
- Size dependency capacity for traffic across all replicas.

You do not always need synchronized circuit breaker state across every replica. Local breakers protect individual instances fast; global quotas are a separate concern.

## 23. Fallbacks and Circuit Breakers Should Not Hide Errors

Fallbacks are helpful when a safe alternative exists. However, fallbacks must never:

- Return default values that distort business meaning.
- Catch every Throwable and return success.
- Swallow authorization errors or code bugs.
- Route fresh requests to the same failing dependency through an unbounded side path.
- Retry infinitely inside the fallback.
- Trigger non-idempotent side effects.
- Prevent callers from distinguishing real data from stale data.

Track fallbacks with dedicated metrics: fallback invoked, fallback succeeded, fallback unavailable, stale responses, and business outcomes. If a fallback always returns HTTP 200 with unusable data, SLIs must reflect business quality, not just status codes.

## 24. Health Checks and Readiness

Never let health checks add excessive load or misreport application state.

- **Liveness:** is the process alive; usually should not depend on every external service.
- **Readiness:** is the instance ready to receive the traffic routed to it.
- **Dependency health:** observe each dependency separately; optional dependencies should not fail readiness.
- **Circuit breaker health:** an OPEN state may indicate degraded mode, not necessarily an instance needing a restart.

If readiness depends on a failing dependency, the load balancer may pull every replica out of rotation simultaneously—knocking out even features that still work. Select critical dependencies per request path and use degraded mode where appropriate.

## 25. Observability for Resilience

Track latency, failures, rejections, and fallbacks separately.

| Metric | Meaning |
| --- | --- |
| dependency_call_total | Calls by dependency/operation and outcome |
| dependency_latency_seconds | Call latency distribution |
| circuitbreaker_state | CLOSED/OPEN/HALF_OPEN state |
| circuitbreaker_not_permitted_total | Calls rejected by the breaker |
| circuitbreaker_failure_rate | Failure rate in the window |
| circuitbreaker_slow_call_rate | Slow-call rate |
| bulkhead_available_concurrent_calls | Remaining open slots |
| bulkhead_rejected_total | Calls rejected because slots were full |
| executor_queue_depth | Thread pool queue depth |
| rate_limiter_rejected_total | Requests rejected by rate limiter |
| retry_attempt_total | Retry attempts |
| fallback_invoked_total | Fallback invocations |
| degraded_response_total | Responses served in degraded mode |
| timeout_total | Timeouts by dependency/operation |

### Logs and Traces

Record fields:

- Dependency and operation.
- Circuit breaker name/state.
- Retry attempt and retry reason.
- Remaining timeout budget.
- Bulkhead rejections or queue waits.
- Fallback type and cache freshness/version.
- Correlation/trace ID.
- Provider request ID when available.

Never log sensitive payloads, access tokens, or connection strings. Avoid using user ID, order ID, or request ID as high-cardinality metric labels.

### Questions Dashboards Should Answer

1. Which dependency is slow or failing?
2. Which circuit breakers are OPEN and for how long?
3. How many requests are being rejected by breakers/bulkheads/rate limiters?
4. Are thread pools, connection pools, and queues nearing saturation?
5. Are retries amplifying traffic?
6. Are fallbacks serving stale data?
7. Are critical operations like checkout/payment still succeeding?

## 26. Testing Circuit Breakers and Bulkheads

Unit testing fallback logic alone is not enough. Test breaker state transitions and resource behavior under dependency failure.

### Circuit Breaker Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Dependency succeeds steadily | Breaker stays CLOSED |
| Errors below threshold | Remains CLOSED |
| Enough samples and failure rate exceeds threshold | Transitions to OPEN |
| Calls while OPEN | Dependency not called; fallback/rejection runs |
| Wait duration elapses | Transitions to HALF_OPEN per policy |
| Probes succeed | Transitions to CLOSED |
| Probes fail | Returns to OPEN |
| Slow-call rate exceeds threshold | Can trip OPEN per configuration |
| Business rejection ignored | Does not raise failure rate |
| Timeouts | Classified accurately per exception policy |

### Bulkhead Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Calls below limit | Executed |
| Exceeds semaphore limit | Rejected or waits up to maxWaitDuration |
| Thread pool and queue full | Rejected per policy |
| Slow dependency | Cannot consume beyond its allocated slots |
| Dependency A saturated | Dependency B retains its own capacity |
| Request deadline expires in queue | Does not execute futile work |

### Fault Injection

1. Make a dependency return 503 for a window.
2. Inject rising latency without errors to test slow-call thresholds.
3. Hold requests open to saturate the bulkhead.
4. Exhaust the HTTP connection pool.
5. Make the dependency return 429/Retry-After.
6. Suddenly recover the dependency and observe HALF_OPEN probes.
7. Scale across multiple replicas and verify recovery bursts.
8. Age fallback cache past staleness limit to confirm stale rejection/tagging.
9. Run application retries alongside SDK retries to verify total attempt budgets.
10. Check liveness/readiness probes during degraded mode.

## 27. Lab Exercise: Protecting the Order API When Inventory Is Slow

**Context:** The Spring Boot Order API calls a cloud Inventory service. Inventory may return 429/503 or stall for 5–10 seconds. Recommendations and analytics are optional. Payment is critical and must never be assumed successful on timeout.

### Part A — Timeouts and Retry Budgets

1. Set an overall request deadline.
2. Choose connect/read timeouts for Inventory.
3. Retry only transient/throttling errors per policy.
4. Use backoff/jitter and respect Retry-After.
5. Bound total attempts across the application and SDK.

### Part B — Circuit Breaker

1. Create a dedicated breaker for Inventory read operations.
2. Choose sliding window and minimum calls based on traffic.
3. Configure failure and slow-call thresholds.
4. Separate business rejections from dependency failures.
5. Verify OPEN/HALF_OPEN transitions and probe counts.

### Part C — Bulkhead and Admission Control

1. Cap Inventory concurrency.
2. Use a bounded queue or semaphore without long waits.
3. Reserve separate capacity for Payment and the database.
4. Apply rate limits aligned with provider quotas.
5. Return 503/429 when additional work cannot be admitted safely.

### Part D — Graceful Degradation

1. Hide recommendation sections if recommendations fail.
2. Buffer analytics for later if analytics fail.
3. If Inventory times out, do not falsely claim stock is available; return an unconfirmed status or ask to retry.
4. If Payment times out, keep PENDING/UNKNOWN and reconcile.
5. If a command is persisted in the outbox, return 202 with an operation ID per contract.

### Part E — Testing and Observability

1. Slow down Inventory and verify the bulkhead stays within limits.
2. Push errors past the threshold and verify the breaker trips OPEN.
3. Restore Inventory and verify HALF_OPEN recovery.
4. Take down recommendations while verifying checkout still works.
5. Time out Payment and verify no fake success is returned.
6. Measure rejections, retries, fallbacks, queue depth, and business success rate.

### Deliverables

- Architecture diagram showing timeouts/retries/circuit breakers/bulkheads.
- Table of thresholds per dependency and operation.
- Resilience4j configuration and fallback code.
- Evidence of concurrency limits and circuit state transitions.
- Degraded-response policies for reads, writes, and payments.
- Dashboard for dependency latency, breaker states, retries, and rejections.
- Failure-injection test results.

### Self-Check Questions

1. Why do timeouts not replace circuit breakers?
2. Does an OPEN circuit breaker automatically free in-flight requests?
3. How do CLOSED, OPEN, and HALF_OPEN differ?
4. What do failure rate and slow-call rate measure?
5. Why should business rejections not count as dependency failures?
6. How does a bulkhead differ from a rate limiter?
7. What are the trade-offs between semaphore bulkheads and thread-pool bulkheads?
8. Why do unbounded queues worsen overload?
9. How can multi-layer retries create a retry storm?
10. Why does canceling a Future not guarantee stopping a blocking SDK call?
11. Which fallback strategies fit reads, writes, payments, and notifications?
12. Why can circuit breaker states differ across replicas?
13. How should Azure Cosmos DB 429s and AWS/GCP throttling be handled alongside retry budgets?
14. When should an API return 202, 429, or 503?
15. Should readiness probes fail when an optional dependency goes down?

## 28. Takeaways

- Timeouts bound wait time; retries recover transient errors; circuit breakers pause calls to failing dependencies; bulkheads isolate concurrent resources.
- Circuit breakers have three states—CLOSED, OPEN, and HALF_OPEN; HALF_OPEN probes must be bounded.
- Failure rate and slow-call rate require enough samples before tripping per policy.
- Never mechanically count business rejections, validation errors, or code bugs as dependency failures.
- Circuit breakers do not limit concurrency and do not necessarily cancel in-flight requests.
- Bulkheads must bound both in-flight calls and queues; unbounded queues merely delay overload.
- Rate limits control rate, concurrency limits control active work, and admission control decides whether to accept new work.
- Retries need overall budgets, backoff/jitter, deadlines, and idempotency coordinated with SDK retries.
- Graceful degradation uses only safe fallbacks that explicitly reflect stale/pending/unavailable status; never fake payment or write success.
- Circuit breakers usually maintain per-instance state; fleet-wide quotas need dedicated global enforcement.
- Monitor dependency latency, breaker states, rejections, retries, queues, fallbacks, and business success rates.
- Test outages, slow calls, throttling, half-open recovery, saturation, and degraded modes.

## References

- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Azure Cosmos DB request units and throttling](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [Azure Service Bus throttling](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-throttling)
- [AWS SDK retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [Amazon DynamoDB throttling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html)
- [Google Cloud retry strategy](https://cloud.google.com/storage/docs/retry-strategy)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Google Cloud API design: errors](https://cloud.google.com/apis/design/errors)
- [Microsoft Azure Architecture Center — Bulkhead pattern](https://learn.microsoft.com/azure/architecture/patterns/bulkhead)
- [Microsoft Azure Architecture Center — Circuit Breaker pattern](https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker)
