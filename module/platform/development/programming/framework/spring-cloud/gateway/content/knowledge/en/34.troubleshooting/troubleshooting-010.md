# Retries Causing Duplicate Operations or Circuit Breakers Opening Unexpectedly

## 1. Symptom: Request Fails Once, Yet the System Executes Multiple Times

An API Gateway can automatically **retry** when an upstream times out or returns a transient error. This helps GET requests recover from a single network blip. Yet if the same mechanism applies to write operations, a single client request can trigger multiple business executions:

- A customer clicks "Pay" once and sees two transactions.
- BFF calls `POST /orders` once, Gateway retries, and the backend creates two orders.
- A service already deducted inventory, yet the response was lost; the retry deducts inventory a second time.
- Gateway, LoadBalancer, and WebClient all retry at once, multiplying backend calls exponentially.
- The circuit breaker repeatedly trips to **OPEN** even after the backend recovered, because failure/slow-call thresholds or health probes are poorly tuned.

Conversely, a circuit breaker can **trip too early** under low traffic, or a fallback can return HTTP 200 making dashboards look green while the real operation never ran.

The lesson **"Retries Causing Duplicate Operations or Circuit Breakers Opening Unexpectedly"** belongs to the **Troubleshooting** chapter of the **SPRING_CLOUD_GATEWAY** module. We will analyze retries, idempotency, circuit breakers, filter ordering, and retry budgets across layers. The goal is to locate the **actual reason behind a duplicate operation or an OPEN breaker**, rather than guessing higher retry counts or looser thresholds.

After this lesson, you will be able to:

1. Distinguish retries triggered by clients, Gateway, Spring Cloud LoadBalancer, and downstream WebClient.
2. Explain why a timeout does not prove the backend has not committed.
3. Design idempotency keys and result storage to prevent duplicate execution.
4. Retry only transient errors and operations with appropriate semantics.
5. Read CLOSED/OPEN/HALF_OPEN states and tune Resilience4j to match traffic.
6. Analyze how filter ordering between Retry and CircuitBreaker changes behavior.
7. Use metrics/events/traces to find why a breaker opened unexpectedly.
8. Write tests proving business execution counts, not merely HTTP request counts.

> **Core rule:** Retry can resend a request; it cannot know whether the prior attempt committed. Circuit breakers block calls to an unhealthy upstream; they do not undo side effects and do not replace idempotency.

## 2. Distinguish Retry from Circuit Breaker

| Mechanism | Question It Answers | Behavior | What It Does NOT Guarantee |
| --- | --- | --- | --- |
| Retry | "Is this error transient enough to try again?" | Resends request within policy/attempt budget | Does not guarantee the previous attempt did not run |
| Circuit breaker | "Does upstream look unhealthy enough to pause calls?" | Tracks outcomes/slow calls, opens circuit, and fails fast | Does not fix backend bugs or retry automatically |
| Timeout | "How long at most to wait for one call?" | Cancels/stops waiting past deadline | Does not prove the server stopped processing |
| Bulkhead / concurrency limit | "How many concurrent calls are permitted?" | Caps resource/concurrency usage | Does not guarantee valid business outcomes |
| Idempotency | "What happens when the same intent arrives multiple times?" | Recognizes and replays the processed result | Does not replace authorization or transaction design |

### 2.1. Example: Request Times Out After Order Was Created

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orders service
    participant DB as Database
    C->>G: POST /orders
    G->>O: POST /orders
    O->>DB: INSERT order
    DB-->>O: COMMIT OK
    O--xG: Response lost on network
    G->>G: Timeout → Retry
    G->>O: POST /orders (attempt 2)
    O->>DB: INSERT order again
    DB-->>O: COMMIT OK
    O-->>G: 201 Created
    G-->>C: 201 Created
~~~

The client sees only a single successful response, yet the DB holds **two orders**. If the client also retries because the first response never reached it, execution counts climb further.

### 2.2. Timeout Is an Uncertain State

When Gateway hits a timeout, at least three possibilities exist:

1. The backend never received the request.
2. The backend received it, has not committed yet, and may have aborted.
3. The backend committed the side effect, yet the response failed to return in time.

Gateway cannot distinguish these three cases from a timeout exception alone. **Never infer "timeout = not executed"** and retry a non-idempotent write.

## 3. At Which Layers Can Retries Happen?

A microservices system can retry at several places:

~~~text
Browser / Mobile
    │  client retry (lost response)
    ▼
Ingress / Load Balancer
    │  proxy retry (if configured)
    ▼
Spring Cloud Gateway
    │  Retry GatewayFilter
    ▼
Spring Cloud LoadBalancer
    │  retry instance selection (if enabled)
    ▼
BFF / Orders service
    │  WebClient / Resilience4j Retry
    ▼
Database / Message broker / Payment provider
~~~

### 3.1. Execution Counts Can Multiply

Suppose each layer permits at most:

| Layer | Max Attempts (Example) |
| --- | ---: |
| Client | 2 |
| Gateway Retry | 3 |
| LoadBalancer | 2 |
| BFF WebClient | 3 |

Theoretical worst-case total reaches:

\[
2 \times 3 \times 2 \times 3 = 36
\]

**36 is an illustrative multiplication when independent layers all exhaust their retries**, not a Spring Cloud Gateway default. Actual counts depend on exceptions, timeouts, filter order, cancellation, LoadBalancer policy, and fallback branches. Still, it shows you cannot evaluate retry at each layer in isolation.

### 3.2. Cross-Layer Retry Budget

A request should share **one overall retry budget**: deadline, maximum attempts, and allowed error set. If Gateway already spent two attempts, BFF should not blindly open three more attempts without accounting for total deadline and load.

Recommendations:

- Assign **one primary retry-owning layer** per hop or operation.
- Outer layers propagate deadline/correlation/idempotency keys instead of minting new keys per attempt.
- Inner layers honor the remaining deadline.
- Never retry validation, authentication, authorization, or business-rejection errors.
- Cap attempts and apply backoff/jitter where appropriate.
- Track **attempts per logical operation**, not just requests per second.

## 4. Classify the Request Type Before Configuring Retry

| HTTP Method / Operation | Default Mindset | Conditions for Retrying |
| --- | --- | --- |
| GET reading data | Typically idempotent per contract | Transient error, remaining timeout budget, no hidden side effects |
| HEAD/OPTIONS | Typically safe | Proper backend semantics |
| PUT replacing full state by resource/key | Can be idempotent per contract | Same resource, same payload, semantics produce no extra side effects |
| DELETE identified resource | Can be idempotent per contract | Repeated DELETE produces no new side effects |
| POST creating order/payment | Never retry blindly | Durable idempotency key/deduplication |
| PATCH incrementing count/balance | Usually non-idempotent | Requires command ID/operation ID and transaction semantics |
| POST sending email/notification | Can cause duplicate sends | Deduplication/outbox/provider idempotency |

HTTP method alone **does not guarantee idempotency**. A poorly designed GET can still mutate state; a POST can be made idempotent with an operation key and stored results. Rely on the **business contract**.

### 4.1. Reasonable Retry

Suppose a public catalog GET returns 503 during a deployment:

~~~http
GET /api/catalog/items/42
~~~

If upstream has no side effects, a bounded retry once or twice with backoff can recover without duplicating transactions.

### 4.2. Dangerous Retry

Example:

~~~http
POST /api/orders
Content-Type: application/json

{"productId":"P-42","quantity":1,"paymentMethod":"wallet"}
~~~

If the server charged the wallet/recorded the order while the response was lost, retrying can charge again. Merely adding a `Retry` filter will not solve that problem.

### 4.3. Errors That Should Not Be Retried

- 400/422: bad payload/validation; resending the identical request yields the same result.
- 401/403: bad credentials/permissions; retrying does not grant the token more permissions.
- 404: missing resource or wrong route; retry only when the contract specifies eventual consistency within a deadline.
- 409: conflict requires reading current state/resolving, not blind retries.
- 429: retry only per `Retry-After` and budget if policy allows; immediate retries worsen overload.
- 5xx: not all 5xx are transient; a business exception mapped to 500 needs a logic fix, not infinite retries.

## 5. Configuring a Bounded Retry Gateway Filter

The example below applies strictly to **GET catalog** and selected transient upstream errors. Syntax illustrates Gateway Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - name: Retry
                  args:
                    retries: 2
                    methods:
                      - GET
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                      - GATEWAY_TIMEOUT
                    backoff:
                      firstBackoff: 50ms
                      maxBackoff: 250ms
                      factor: 2
                      basedOnPreviousValue: false
                    jitter:
                      randomFactor: 0.5
                    timeout: 800ms
~~~

Explanation:

- `retries: 2` is the **number of additional retry attempts** per the filter contract, not a guarantee of total system-wide attempts; verify per version and test.
- Only `GET` is retried.
- Only specific transient statuses are selected; never retry all 4xx/5xx.
- Backoff grows with an upper cap.
- Jitter desynchronizes retries across requests; timeout caps retry duration per filter configuration.
- The example does not enable retry for `POST /orders`.

**Note:** WebFlux Gateway 4.x uses prefix `spring.cloud.gateway.routes`; WebFlux Gateway 5.x uses `spring.cloud.gateway.server.webflux.routes`. Never put both prefixes in the same configuration. Verify docs and runtime route/filter config against your real BOM.

### 5.1. Retrying by Exception

The Retry factory supports configuring exception classes in compatible releases, such as I/O or timeout errors. Add exceptions only when you understand the call path:

~~~yaml
filters:
  - name: Retry
    args:
      retries: 1
      methods:
        - GET
      exceptions:
        - java.io.IOException
        - java.util.concurrent.TimeoutException
~~~

Exact exception classes depend on Reactor Netty implementation/exception wrapping and version. **Do not copy a list assuming every timeout is matched**; test against real stack failures.

### 5.2. Never Configure Retry for All Routes via Default Filters

Putting Retry in `default-filters` exposes admin refund, checkout, order creation, or upload routes to retries unless strictly scoped. Prefer **per-route policies** with explicit methods/statuses/exceptions; test that new routes do not accidentally inherit retries.

### 5.3. Retry Re-Executes Filters Placed After It

Gateway documentation explicitly states that the Retry filter **retries all filters ordered after Retry in the chain**. Thus filter placement can cause another filter to execute multiple times:

~~~text
Retry
  → AddRequestHeader
  → Custom audit filter
  → CircuitBreaker
  → Netty routing
~~~

If a custom filter writes audit events, generates an operation ID, or calls an external service, it can run again on every attempt. In particular, `AddRequestHeader` can append duplicate values if the request already carries that header. Make sure to:

- Avoid placing side-effecting custom filters after Retry unless they are idempotent.
- If a technical header is needed, overwrite/normalize rather than appending repeatedly.
- Check effective route filter order; filters sort by order, not just visual YAML line order.
- Use backend/filter counters to verify how many times each step executes.

This is a common reason **a request looks like it was retried only upstream while audit logs/custom logic also ran multiple times**.

## 6. Request Bodies, Uploads, and Memory Under Retry

To resend a request carrying a body, Gateway may have to **cache the body** for replay. This adds memory overhead and can pressure Gateway under concurrent large uploads/bodies.

Risks:

- Large bodies may stay in memory across multiple attempts.
- Concurrent requests drive up direct/heap memory and GC pressure.
- Streaming bodies cannot always replay safely like a cached byte array.
- Multipart/file upload requests can cause duplicate writes or duplicate object-storage uploads.
- Retrying a side-effecting POST only replays bytes; caching **does not guarantee idempotency**.

Recommendations:

- Do not enable broad retries on uploads/streaming or large bodies without memory testing.
- Enforce request size limits at edge/Gateway/backend.
- When retries are required, pair operation IDs/idempotency keys with backend deduplication.
- Measure memory/GC under representative concurrency, not just a single small request.
- Use object-storage upload sessions/chunk IDs and idempotent finalize operations if uploads must be resumable.

## 7. Idempotency Keys: Protecting Write Operations

An order-creation API can require clients to send:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: 01J8Q2C7D8W9M3P4
Content-Type: application/json

{"productId":"P-42","quantity":1}
~~~

### 7.1. Key Must Represent One Business Intent

- Client generates **one key per logical operation**.
- Every retry of that operation resends the **exact same key**.
- When a user intentionally places a new order, a new key must be generated.
- Gateway must never generate a fresh key per retry attempt.
- Server scopes the key to **authenticated principal/tenant + operation**, never a global key alone.
- Server stores a request fingerprint to catch the same key reused with a different payload.

Never use IP/User-Agent as a key; multiple users can share NAT, one user can change IP, and neither identifies a transaction.

### 7.2. Minimal Idempotency Table

PostgreSQL example:

~~~sql
CREATE TABLE idempotency_record (
    principal_id       VARCHAR(160) NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       VARCHAR(128) NOT NULL,
    state              VARCHAR(20) NOT NULL,
    response_status    INTEGER,
    response_body      JSONB,
    resource_id        VARCHAR(160),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (principal_id, operation_name, idempotency_key)
);
~~~

`principal_id` must come from a verified identity; `operation_name` scopes the key; `request_hash` is a canonical hash of payload/semantic inputs. TTL must outlast client retry/reconciliation windows, include cleanup, and never delete records while the operation is still processing.

### 7.3. Safe Processing Flow

~~~mermaid
flowchart TD
    A["POST + authenticated principal + idempotency key"] --> B["Validate key, hash request"]
    B --> C{"Record already exists?"}
    C -->|"No"| D["Atomic insert PROCESSING"]
    D --> E["Execute business transaction"]
    E --> F["Commit result + response snapshot"]
    F --> G["Return response"]
    C -->|"Yes, same hash + COMPLETED"| H["Replay stored result"]
    C -->|"Yes, different hash"| I["409 Conflict"]
    C -->|"Yes, PROCESSING"| J["Wait/poll or 409/202 per contract"]
~~~

The insert/lock must be **atomic**. If two requests with the same key arrive concurrently, the unique constraint/transaction must guarantee only one executes the business logic; the other reads the result or returns an in-progress status.

### 7.4. Never Rely Solely on ConcurrentHashMap in Production

An in-memory map:

~~~java
Map<String, OrderResponse> results = new ConcurrentHashMap<>();
~~~

only illustrates the concept. It fails across multiple replicas, loses state on process restarts, lacks transactional atomicity with the DB, and breaks if a crash happens between side effect and response storage. Use **database unique constraints/transactions** or an idempotency store with strong consistency semantics.

### 7.5. Side Effects Outside the Database Need Outbox or Provider Idempotency

If the order service:

1. writes the order in the DB;
2. calls a payment provider;
3. publishes an event;

a DB idempotency record alone does not guarantee payment/event execution happens once. You need:

- Provider idempotency keys for payments if supported.
- A transactional outbox committing domain state + event record in the same transaction.
- Consumer deduplication/inbox by event ID.
- Sagas/compensation for multi-service workflows instead of assuming distributed transactions roll back automatically.

**End-to-end exactly-once** is not achieved by a single header alone. Design uses at-least-once delivery + idempotent processing/deduplication at each side effect.

## 8. Circuit Breaker: Understand States Before Tuning Thresholds

A circuit breaker tracks call outcomes to a dependency and transitions states:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Failure rate / slow-call rate exceeds threshold\nand minimum calls reached
    OPEN --> HALF_OPEN: Wait duration elapsed
    HALF_OPEN --> CLOSED: Probe calls meet policy
    HALF_OPEN --> OPEN: Probe calls fail / too slow
~~~

| State | Meaning | Behavior |
| --- | --- | --- |
| **CLOSED** | Normal circuit | Calls allowed; outcomes recorded in sliding window |
| **OPEN** | Dependency considered unhealthy | Calls rejected fast, typically raising `CallNotPermittedException` |
| **HALF_OPEN** | Probing recovery | Only a limited number of probe calls permitted; results decide whether to close or reopen |

### 8.1. Failure Rate and Slow-Call Rate Differ

- **Failure rate:** percentage of calls counted as failures in the window.
- **Slow-call rate:** percentage of calls exceeding `slowCallDurationThreshold`.
- **Minimum number of calls:** minimum sample count before computing thresholds; avoids tripping on tiny samples.
- **Sliding window:** most recent call count (`COUNT_BASED`) or time span (`TIME_BASED`) used for evaluation.

Example:

~~~text
slidingWindowSize = 20
minimumNumberOfCalls = 10
failureRateThreshold = 50%

Within a window reaching 10 calls:
  5 calls recorded as failures → failure rate = 50%
  breaker may transition to OPEN per policy
~~~

This is a **numerical illustration**, not Resilience4j or Gateway defaults. A handful of timeouts under low traffic may not reach `minimumNumberOfCalls`; conversely, a low threshold under burst traffic can trip the breaker rapidly.

### 8.2. Why Is HALF_OPEN Not a Perfect Health Check?

Probe calls in HALF_OPEN are **real requests** allowed through to the dependency. If a probe is a non-idempotent POST, it can still trigger side effects. Therefore:

- Do not let breaker probes execute dangerous writes without idempotency.
- Prefer read-only health/diagnostic operations where the breaker model allows, keeping in mind Gateway CircuitBreaker protects route calls rather than calling health endpoints itself.
- Cap `permittedNumberOfCallsInHalfOpenState`.
- Monitor state and actual probe counts to prevent a large probe wave from overwhelming a recovering backend.

## 9. Configuring CircuitBreaker Gateway Filter and Resilience4j

To use the CircuitBreaker GatewayFilter with Reactor/WebFlux, the project needs the BOM-compatible Spring Cloud CircuitBreaker Reactor Resilience4j starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Catalog/orders route example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - name: CircuitBreaker
                  args:
                    name: orders-read
                    fallbackUri: forward:/fallback/orders
                    statusCodes:
                      - 500
                      - 502
                      - 503
                      - 504
~~~

`fallbackUri` with `forward:` dispatches internally within the Gateway application to a fallback handler. A fallback **is not another automatically protected backend**; fallback code must have timeouts, must never call the same OPEN upstream, and must never fabricate fake success data from errors.

### 9.1. Tune Resilience4j to Your Workload

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      orders-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 2s
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

The values above are **illustrative lab values**, not production recommendations. For example, calls over 2 seconds are classified as slow; if orders' real SLO is 300 ms, that threshold is too loose. If upstream regularly takes 3 seconds for batch exports, the same threshold is too tight.

Key properties:

| Property | Meaning | Common Misconfiguration |
| --- | --- | --- |
| `slidingWindowType` | COUNT_BASED or TIME_BASED | Choosing a window mismatched to traffic pattern |
| `slidingWindowSize` | Call count or window duration per type | Too small, causing noisy oscillations |
| `minimumNumberOfCalls` | Minimum samples before computing rates | Too low, letting a few errors trip the breaker |
| `failureRateThreshold` | Failure percentage to trip open | Too low for dependencies with transient blips |
| `slowCallRateThreshold` | Slow-call percentage to trip open | Confusing slow threshold with request timeout |
| `slowCallDurationThreshold` | Duration classifying a call as slow | Mismatched against real SLO/timeouts |
| `waitDurationInOpenState` | Time spent OPEN before trying HALF_OPEN | Too short, causing constant probing |
| `permittedNumberOfCallsInHalfOpenState` | Number of probe calls allowed | Too high, slamming a recovering backend |
| `automaticTransitionFromOpenToHalfOpenEnabled` | Automatically transitions after wait duration | Misunderstanding that probe traffic is still needed |

### 9.2. Record and Ignore Exceptions Intentionally

Resilience4j CircuitBreaker can configure which exceptions count as failures and which are ignored. Distinguish:

- Upstream errors like connection failures, timeouts, or 5xx can count as failures.
- `CallNotPermittedException` means the breaker **was already OPEN prior to calling upstream**, not a new upstream error.
- Caller-layer validation/authorization errors should not trip a dependency breaker.
- A fallback exception may occur after the breaker already opened; do not count it as a backend failure if metrics/recording policy targets the wrong layer.

Never copy `recordExceptions`/`ignoreExceptions` without knowing which real exceptions Reactor/Netty wraps. Use traces/logs to inspect the cause chain and configure per version. When setting explicit `recordExceptions`, check the semantics of unlisted exceptions and test success, ignored, and recorded failure cases.

## 10. Fallback: Never Turn Errors into Fake Success

WebFlux fallback controller example:

~~~java
package demo.gateway.fallback;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersFallbackController {

    @GetMapping("/fallback/orders")
    public Mono<ResponseEntity<Map<String, Object>>> ordersFallback() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .header("Retry-After", "5")
                        .body(Map.of(
                                "code", "ORDERS_TEMPORARILY_UNAVAILABLE",
                                "message", "Please try again later",
                                "retryable", true)));
    }
}
~~~

This returns 503 with an explicit error code instead of faking an empty order as success. If a BFF returns a **stale cached catalog** in fallback, clearly indicate data freshness and never use stale fallbacks for permissions, inventory, balances, or payment statuses requiring accuracy.

### 10.1. Fallbacks Must Not Retry the Same Dependency

If a fallback calls `lb://orders-service` again via WebClient without an isolated budget, it calls the exact dependency that is already OPEN, creating a loop:

~~~text
Route → CircuitBreaker OPEN → fallback
  → WebClient orders-service
  → same failing dependency
  → fallback/error handler
~~~

Fallbacks should return a defined degraded response, read a safe cache, or enqueue a job per contract. Never put order/payment creation logic inside a fallback.

### 10.2. Avoid Returning 200 for Unfinished Operations

For a POST creating an order, a fallback like:

~~~json
{"status":"accepted","orderId":"unknown"}
~~~

returning 200/202 can mislead clients into believing the transaction succeeded. When execution hasn't committed or outcome is unknown, return an explicit **pending/unknown** status per contract, provide an operation ID for lookup, and prevent clients from resubmitting with a new key. Never declare failure prematurely if the backend may have committed; reconcile with the idempotency key.

## 11. Circuit Breaker Opens Unexpectedly: Read the Numbers Before Adjusting Thresholds

When a breaker trips OPEN, ask in order:

1. Which breaker instance is OPEN? Is the name shared across multiple routes?
2. Was `minimumNumberOfCalls` reached?
3. Did failure rate or slow-call rate exceed its threshold?
4. Which exceptions/statuses are being recorded?
5. Is the Gateway/HTTP client timeout shorter than normal latency?
6. Did retries turn one logical request into multiple samples/failures?
7. Is the fallback failing itself and being mistaken for an upstream error?
8. After OPEN, do HALF_OPEN probes succeed or immediately fail?

### 11.1. Common Causes

| Symptom | Possible Cause |
| --- | --- |
| Breaker OPENS after the first few requests | Low `minimumNumberOfCalls` or tiny window |
| Backend returns 200 yet breaker failures rise | Exception in pre/post filter, status mapping, or exception recording policy |
| Backend recovered yet breaker stays open | Long `waitDurationInOpenState`, failing probes, or no traffic reaching HALF_OPEN |
| Breaker flaps CLOSED→OPEN→HALF_OPEN | Flaky backend, excessive probes, threshold sitting right on the edge |
| Breaker OPENS on only one route | Route uses a different breaker name/config, upstream target, or timeout |
| Multiple routes OPEN together when one service fails | Shared breaker name/instance or shared dependency |
| OPENS right after a retry burst | Each attempt was observed and recorded by the breaker; filter order affects sample count |
| Breaker trips on 404/401/403 | Status/exception policy treats business/client responses as failures |
| Breaker stays closed even when backend hangs | Slow-call threshold too high or duration not measured |
| Circuit breaker opens under light traffic | Small window, background/health probes, or misaggregated metrics |

### 11.2. Never Raise Thresholds Just to Keep Dashboards Green

If a breaker opens due to `minimumNumberOfCalls=2`, raising it to 20 cuts false positives yet **delays outage detection**. If a breaker opens due to a 200 ms timeout against a 1-second SLO, raising timeouts holds requests longer and ties up connections/threads. Adjust one parameter at a time, test with traffic replay/stubs, and weigh both false-opens and detection speed.

## 12. What Does Filter Order Between Retry and CircuitBreaker Change?

When a route attaches both filters, what matters is **whether each retry attempt is observed by the breaker as a separate call**.

Two conceptual compositions:

~~~text
Model A — Retry wraps CircuitBreaker:
Logical request
  → Retry
      → CircuitBreaker → upstream (attempt 1)
      → CircuitBreaker → upstream (attempt 2)
      → CircuitBreaker → upstream (attempt 3)

Model B — CircuitBreaker wraps Retry:
Logical request
  → CircuitBreaker
      → Retry
          → upstream (attempt 1)
          → upstream (attempt 2)
          → upstream (attempt 3)
~~~

Consequences differ:

| Aspect | Retry Outside Breaker | Breaker Outside Retry |
| --- | --- | --- |
| Samples in breaker | May record each attempt | May record the final outcome of the logical call |
| Breaker opens mid-retry | Next attempt can be rejected fast | Breaker evaluates only after retries finish |
| Failure rate | Can climb faster due to multiple attempts | Fewer samples per logical request |
| Latency | Retries continue until budget exhausts or breaker blocks | Retries run inside one breaker call, yielding longer call duration |
| Operational meaning | Breaker reflects upstream attempts | Breaker reflects logical operation experience |

These are **conceptual models**. Gateway docs note the Retry filter retries filters ordered after it; hence if Retry precedes CircuitBreaker, each attempt can pass through the breaker separately. If the breaker precedes Retry, the breaker may observe the final outcome of the retry sequence. Never infer actual order from YAML line order alone: Spring Cloud Gateway merges GlobalFilters and route GatewayFilters and sorts them by `Ordered`; each filter factory can assign its own order. **Inspect the runtime chain of your running version**, or write an integration test with counters to see how many calls the breaker records.

### 12.1. How to Investigate Filter Order

1. Inspect route definitions and effective filters via secured Actuator.
2. Check the implementation/docs of your exact Gateway release; do not copy order numbers from blog posts for other versions.
3. Enable debug/trace logging in test environments while keeping tokens/bodies out of production logs.
4. Use a stub backend with a counter returning a controlled sequence of statuses (503, 503, 200).
5. Compare backend attempts, breaker event counts, and client responses.
6. Check whether fallback runs once or multiple times.

### 12.2. Prevent Unintended Sharing of a Breaker Name

If multiple routes share `name: orders`, depending on how circuit breakers are created/cached in the integration, they may share one breaker instance/config. When a high-latency admin/batch route trips the breaker OPEN, the separate GET orders route gets rejected by the same state.

Design:

- Use breaker names reflecting **dependency + latency class/use case** (e.g., `orders-read`, `orders-command`).
- Never create a separate breaker per user/request.
- Share only when routes truly share upstream, SLO, and failure semantics.
- Inspect `CircuitBreakerRegistry`/metrics to verify actual instance counts.

Different names do not create network isolation; they only separate in-process breaker policies and state.

## 13. LoadBalancer Retries and Service Discovery

A route with `uri: lb://orders-service` uses Spring Cloud LoadBalancer to choose a service instance. If retries exist in both Gateway Retry filter and LoadBalancer:

- One Gateway attempt can route to instance A.
- A connection error can make LoadBalancer try instance B.
- Gateway Retry can resend the logical request and trigger another instance selection.
- If instance A already committed while the response was lost, instance B can execute the side effect a second time.

**Retrying another instance does not make an operation idempotent.** Two replicas sharing a database still create duplicate rows unless the backend enforces unique keys/idempotent transactions.

### 13.1. Check LoadBalancer Retries Separately

Verify:

- Spring Cloud LoadBalancer version and active retry configuration.
- Does retry trigger only on `onNext`/`onError` or specific response statuses?
- Does it retry on the same instance or next instance?
- Are `POST`/non-idempotent methods excluded per policy?
- Is Gateway Retry wrapping extra outer attempts?
- Does a health-check/load-balancer policy drop an instance on one replica while another replica still sends traffic to it?

Do not assume `spring.cloud.loadbalancer.retry.*` properties behave identically across release trains. Verify effective config via Actuator/config metadata and test against your exact BOM.

### 13.2. Never Let Many Replicas Retry a Dead Dependency Simultaneously

If 50 Gateway replicas all retry 3 times immediately, a recovering backend gets hit with a massive burst. Use:

- Exponential backoff and jitter at the retry-owning layer.
- Circuit breakers to fail fast when a dependency shows signs of outage.
- Bulkheads/concurrency limits to cap in-flight requests.
- Rate limiting/admission control for excess traffic.
- Staggered rollouts/probe budgets when services come back.

Retries add load precisely when a dependency is weak; you need **retry budgets** and **load shedding**, not higher attempt counts.

## 14. Timeouts and Deadlines: Avoid Conflicting Layers

One request traverses multiple timeouts:

~~~text
Client deadline:              3.0 s
Gateway route/client timeout: 2.5 s
Retry attempt + backoff:      2.0 s total
Backend processing timeout:   1.5 s
DB statement timeout:         1.0 s
~~~

This is an **illustrative timeline**; real deadlines need headroom for networking/serialization and cancellation. Principles:

- A caller's deadline must exceed the internal budget it waits on if a response is expected.
- Each downstream call receives the **remaining deadline**, never a fresh full timeout per retry.
- DB statement timeouts must align with transaction deadlines.
- Backoff must fit inside the overall deadline rather than adding unbounded time.
- When the client cancels, propagate cancellation downstream where safe; remember cancellation still does not roll back committed transactions.

### 14.1. Retry Budget Example

Suppose a 2-second overall deadline:

| Component | Budget |
| --- | ---: |
| Attempt 1 | max 500 ms |
| Backoff | 100 ms |
| Attempt 2 | max 500 ms |
| Response/serialization margin | 300 ms |
| Reserve | 600 ms |

If attempt 1 already took 1.2 seconds, insufficient budget remains for attempt 2. Starting a retry after the caller's deadline has expired only adds wasted load.

### 14.2. Never Confuse HTTP Client Timeout with CircuitBreaker Slow Threshold

Suppose HTTP client timeout is 1 second while `slowCallDurationThreshold=2s`: the request times out at 1 second and gets recorded as an exception failure, so the 2-second slow-call threshold may **never trigger** for that call. If slow-call rate should reflect SLOs, align thresholds with client timeouts and latency objectives.

## 15. Observing Retry and CircuitBreaker

### 15.1. Resilience4j Metrics

With appropriate Micrometer/Actuator integration, Resilience4j metrics typically include:

| Metric | What to Watch |
| --- | --- |
| `resilience4j.circuitbreaker.state` | CLOSED/OPEN/HALF_OPEN state per instance |
| `resilience4j.circuitbreaker.calls` | Call counts by kind: success/failed/not_permitted |
| `resilience4j.circuitbreaker.failure.rate` | Current failure rate |
| `resilience4j.circuitbreaker.slow.call.rate` | Current slow-call rate |
| `resilience4j.circuitbreaker.not.permitted.calls` | Calls rejected by the breaker |

Metric names/tags can differ across registries/versions. Confirm at `/actuator/metrics` or your app's Prometheus scrape target rather than assuming metrics are enabled automatically just because the dependency exists.

### 15.2. Gateway Route Metrics and Downstream Metrics

Combine:

- Gateway request metrics by route ID, method, status, and outcome.
- Resilience4j state/call metrics by breaker name.
- HTTP client connection/response timeout metrics.
- Backend business metrics: orders created, payment captures, inventory decrements.
- Idempotency store metrics: duplicate key hits, hash conflicts, in-progress waits.
- Distributed tracing: logical trace ID, attempt spans, downstream service/instance.

**Gateway request count alone is insufficient**: one Gateway request can produce multiple downstream attempts. To diagnose duplicate orders, compare **client logical operations, Gateway attempts, backend handler executions, and committed business records**.

### 15.3. Safe and Correlatable Logging

A useful structured log:

~~~json
{
  "traceId": "trace-test-42",
  "routeId": "orders-read",
  "operation": "GET /api/orders/{id}",
  "attempt": 2,
  "upstream": "orders-service",
  "upstreamInstance": "orders-2",
  "status": 503,
  "durationMs": 420,
  "breakerState": "CLOSED"
}
~~~

`attempt` is instrumentation added by your application; Gateway does not emit a standard attempt header across all retry filters. Never log raw Authorization, cookies, payment bodies, full idempotency keys, or PII. If idempotency key correlation is needed, log a policy-approved hash/partial fingerprint.

### 15.4. Keep Actuator on a Secured Management Plane

Example exposing metrics/health:

~~~yaml
management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

`/actuator/circuitbreakers` or Spring Cloud Gateway endpoints are **not exposed by default in every release**. Expose only needed endpoints, protect them with authentication/network policy, and avoid public write/refresh operations. Internal JMX/metrics registries can also be used instead of public Actuator endpoints.

### 15.5. Separate Gateway Failures from Business Failures

Dashboards should classify:

- **Upstream transport failures:** connection refused/reset, DNS, TLS, timeouts.
- **Upstream HTTP failures:** statuses recorded by CircuitBreaker config.
- **Business rejections:** validation/conflict/quota/authz — normally should not trip dependency breakers.
- **Breaker rejections:** `CallNotPermittedException`, upstream not called.
- **Fallback failures:** errors in fallback handlers/caches/serialization.

Lumping everything into "5xx" tempts you to raise breaker thresholds to hide fallback bugs or trip breakers because clients sent bad input.

## 16. Runbook: Investigating Duplicate Operations

When customers report duplicate orders/double charges, do not immediately disable Retry as your first move. First preserve evidence to establish **how many times the same logical operation was sent and which side effects committed**.

### 16.1. Query by Operation / Idempotency Key

An internal investigation report should capture:

| Data | Question |
| --- | --- |
| Verified principal/tenant | Do both records belong to the same user/tenant? |
| Operation name | Both create-order, or two distinct operations? |
| Idempotency key/fingerprint | Same key/intent? |
| Gateway trace IDs | One client request or multiple? |
| Gateway retry attempts | How many times was each logical request forwarded? |
| Backend handler executions | How many times did the backend actually run? |
| DB committed rows | How many orders/payments/inventory rows exist? |
| Provider transaction IDs | Did the payment provider capture multiple times? |

Never paste raw tokens/card data/customer PII into tickets. Use controlled identifiers, masked values, and trace IDs.

### 16.2. Read the Timeline in Order

1. When did the client send the request? Did the client retry after a timeout?
2. How many logical requests did Gateway receive? Same correlation ID or different?
3. How many attempts did Gateway Retry generate? Which status/exception triggered them?
4. Which instance did LoadBalancer pick on each attempt?
5. Did the backend commit prior to timing out?
6. Do the DB/provider enforce idempotency/deduplication?
7. Did the client generate a new key on retry instead of reusing the original key?

If Gateway received **two logical requests** with two different idempotency keys, Gateway Retry is not the sole culprit; the client may have resubmitted as two separate operations. If one logical request produced three backend attempts yet only one business record, idempotency worked; investigate why retries exceeded budget.

### 16.3. Immediate and Long-Term Remediation

**Immediate:**

- Pause retries on write routes lacking idempotency, following change control.
- Preserve trace/DB/provider evidence; never delete idempotency records "to try again".
- Reconcile transactions with the payment provider before issuing refunds or removing records.
- Halt retry storms and cap concurrency if the dependency is overloaded.
- Clearly report operations as `pending/unknown` when backend commit status is uncertain.

**Long-term:**

- Add idempotency keys and unique constraints/transactions where side effects occur.
- Designate one retry-owning layer with deadlines/backoff/jitter and attempt budgets.
- Separate transient error statuses from business rejections.
- Instrument attempts, dedupe hits, backend commits, and breaker states.
- Add regression tests simulating response loss **after commit**.

### 16.4. Avoid "Fixing Duplicates" by Blindly Deleting Rows

Two orders for the same product might be two genuine purchases; two payment captures may need refunds/reconciliation. Never delete rows by timestamp or customer ID without checking operation keys, ledgers, outboxes, payment providers, and downstream events. Transactional data requires **audited reconciliation**.

## 17. Runbook: Breaker OPEN Unexpectedly

### 17.1. First-Minutes Diagnostic Checklist

1. Identify the breaker **instance name** and all routes sharing it.
2. Read current state, failure rate, slow-call rate, and not-permitted count.
3. Check minimum calls/window size and when OPEN began.
4. Inspect recorded exception cause chains/status codes.
5. Compare backend latency against Gateway/client timeouts.
6. Check retry attempt counts leading up to OPEN.
7. Check fallback errors and downstream fallback calls.
8. Check backend health/connection pools/DB saturation.
9. Observe HALF_OPEN probe results and `waitDurationInOpenState`.
10. Change one setting at a time; canary and record config revisions.

### 17.2. Questions to Isolate Root Cause

| Observation | Possible Interpretation |
| --- | --- |
| Failure rate rises, backend 5xx rises | Dependency or its own downstream dependency is genuinely failing |
| Failure rate rises, backend status stays 200 | Exception in proxy/decoder/filter, or status/metrics belong to another route |
| Slow-call rate rises, failure rate low | Backend too slow; check SLO, timeouts, connection pool, DB |
| Not-permitted rises after OPEN | Callers still send traffic while breaker is open; not new backend failures |
| HALF_OPEN probes fail immediately | Backend not ready, too many probes, or network/config error |
| Only one Gateway replica reports OPEN | State is per-process/instance or traffic skew; check breaker registry/replica metrics |
| All replicas OPEN together | Shared config, traffic burst, dependency outage, or alert aggregation |
| Breaker OPENS after deploying new route | Shared breaker name, new timeouts, overly broad statusCodes, altered filter order |

**Note on distributed state:** Resilience4j CircuitBreaker typically manages state in-process; never assume breaker state is synchronized across all Gateway replicas. Dashboards must tag instance/Pod/route so one replica is not mistaken for the entire cluster.

### 17.3. Do Not Force the Breaker CLOSED to Restore Traffic

If the backend is still failing, forcing CLOSED or repeatedly resetting pushes load back onto an exhausted dependency. Only reset state once:

- Root cause is fixed or dependency recovery is verified.
- Concurrency/traffic can be controlled.
- Safe probes pass.
- Rollback exists if failure rate/latency spikes again.

A breaker is a resource-protection safeguard, not an alert to "clear green".

## 18. Lab: Observing Retry and Circuit Breaker with a Backend Stub

Lab goals:

1. Create a GET route that retries only when upstream returns 503.
2. Have a backend stub return 503 once and then 200.
3. Verify Gateway makes the exact expected number of downstream attempts.
4. Add a circuit breaker with a small threshold in a test profile and observe OPEN/fallback.
5. Verify a POST route without a Retry filter is never resent.

### 18.1. Controllable Backend Stub

Use MockWebServer or WireMock in tests; no public backend needed. Conceptual dispatcher example:

~~~java
AtomicInteger calls = new AtomicInteger();

server.setDispatcher(new Dispatcher() {
    @Override
    public MockResponse dispatch(RecordedRequest request) {
        int attempt = calls.incrementAndGet();
        if (attempt == 1) {
            return new MockResponse().setResponseCode(503);
        }
        return new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"status\":\"ok\"}");
    }
});
~~~

This snippet is a **test fixture**, valid only inside a test class initializing `MockWebServer` with the required imports. Reset counters/queues between test cases; never share unsynchronized state across parallel tests.

### 18.2. Retry Test Route

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: retry-read-test
              uri: http://127.0.0.1:${test.backend.port}
              predicates:
                - Path=/test/read
                - Method=GET
              filters:
                - name: Retry
                  args:
                    retries: 1
                    methods:
                      - GET
                    statuses:
                      - SERVICE_UNAVAILABLE
~~~

Expectations when stub returns 503 then 200:

| Assertion | Expected |
| --- | --- |
| Client response | 200 |
| Backend request count | 2 |
| Request method | GET on both attempts |
| Body | No body requiring replay |
| Trace | Same logical request/correlation; distinct attempt index if instrumented |

Do not assert that every deployment automatically adds an attempt header. Gateway Retry filter does not guarantee a standard attempt header.

### 18.3. Verify POST Is Not Retried

Add a separate route:

~~~yaml
- id: create-order-test
  uri: http://127.0.0.1:${test.backend.port}
  predicates:
    - Path=/test/orders
    - Method=POST
~~~

Send POST while the stub returns 503. Without Retry attached to the route, **backend count must be 1** (one downstream attempt from Gateway). If the test client itself has retries, disable client retries or count separately; do not infer Gateway retried from seeing two total requests.

### 18.4. Testing Idempotency When Response Is Lost After Commit

A key business test:

~~~text
Given:
  principal = user-123
  idempotency key = op-001
  payload hash = H1

When:
  first request commits order O-42
  response is dropped before reaching client
  client resends same key op-001 and same payload H1

Then:
  backend returns the stored response/result for O-42
  orders table contains only one order O-42
  payment provider has only one capture for the provider key

And:
  same key op-001 with different payload hash H2
  → 409 Conflict, no second order created
~~~

This is a **backend/domain service test** and cannot be proven by Gateway route tests alone. Use fault injection/proxy tests to drop responses after commit; never use a live payment environment.

### 18.5. Testing CircuitBreaker State Transitions

For Resilience4j unit tests, build a breaker config in the test:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class CircuitBreakerStateTest {

    @Test
    void opensAfterHalfOfTheMinimumWindowFails() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(1))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("orders-test", config);

        breaker.onSuccess(10, TimeUnit.MILLISECONDS);
        breaker.onSuccess(10, TimeUnit.MILLISECONDS);
        breaker.onError(20, TimeUnit.MILLISECONDS,
                new IOException("simulated upstream failure"));
        breaker.onError(20, TimeUnit.MILLISECONDS,
                new IOException("simulated upstream failure"));

        if (breaker.getState() != CircuitBreaker.State.OPEN) {
            throw new AssertionError(
                    "Expected OPEN after 2/4 failures");
        }
    }
}
~~~

Then:

1. The snippet records 2 successes + 2 failures in CLOSED.
2. Verify OPEN state once the 50% threshold triggers.
3. Verify subsequent calls are rejected and increment not-permitted counts.
4. Advance using a controllable clock supported by your Resilience4j test API/harness (or wait briefly) to enter HALF_OPEN.
5. Send the permitted number of probes and verify closing/reopening based on outcomes.

This is a **unit test for Resilience4j**; it does not test Gateway filter ordering or HTTP fallbacks. Integration tests must attach the CircuitBreaker GatewayFilter to a route and call through a real HTTP server.

### 18.6. Avoid Long Sleeps When Testing State Machines

When testing `waitDurationInOpenState`, prefer a clock/time abstraction supported by your Resilience4j test API version or use a small bounded duration with test timeouts. Never put multi-second sleeps of tens of seconds in CI, and never let tests share the same registry/state.

## 19. Quick Troubleshooting Table

| Symptom | Possible Cause | Evidence to Collect | Remediation |
| --- | --- | --- | --- |
| One click creates two orders | Gateway/client/LoadBalancer retried after commit | Idempotency key, Gateway attempts, DB records | Deduplicate in backend; fix retry budget |
| Payment captured twice | Payment call retried without provider key | Provider transaction IDs, request timeline | Provider idempotency/reconciliation |
| POST sent three times | Retry filter applied to write route or multi-layer retries | Effective route filters, recorded requests | Disable blind retries; per-route policy |
| GET retried yet never recovers | Retry does not match actual exception/status | Cause chain, status, Retry filter config | Configure matching exception/status and test |
| Retries cause continuous 503s | Backoff too short, dependency still down | Attempts/sec, latency, breaker state | Lower retry budget, add jitter, breaker/load shed |
| Retries continue after client cancels | Cancellation not propagated or side effect committed | Reactor traces, downstream logs | Respect cancellation/deadline; idempotency |
| Gateway reports 504 yet order exists | Backend committed, response lost | DB commit timestamp and gateway timeout | Query operation by idempotency key |
| Breaker OPENS after a few failures | Minimum calls/window too low | Breaker config/events | Tune for sample size and SLO |
| Breaker OPENS on 401/403 | Security/business errors recorded as dependency failures | Status/exception mapping | Ignore/skip recording caller errors |
| Breaker OPENS on 404 | Overly broad route/status policy or normal backend 404 | Route config, downstream responses | Record only statuses representing dependency failures |
| Breaker OPENS despite backend 200 | Filter/decoder error, exception wrapping, wrong metrics | Cause chain, trace spans | Pinpoint failure source; fix recording policy |
| Breaker stays closed when backend hangs | Slow threshold too high or calls unmeasured | Latency distribution, slow rate | Align threshold with SLO/timeouts |
| Breaker fails to close again | HALF_OPEN probes fail or no traffic | State events, wait duration, probe results | Check upstream, probe budget |
| Breaker flaps open/closed | Threshold right on boundary, flaky backend | State transition timestamps, rates | Tune window/hysteresis, fix backend |
| Only one route affected | Route uses different breaker name/config | Route ID, breaker registry | Fix name/config or route timeout |
| Multiple routes OPEN together | Shared breaker name/instance or shared dependency | Instance name, registry | Share intentionally or split policies |
| Recovering backend overloads again | Too many HALF_OPEN probes, many Gateway replicas | Probe counts, in-flight requests | Reduce probes, add jitter/stagger, bulkhead |
| Fallback returns 200 for unclear order | Fallback masks pending/unknown state | Fallback response/body, business records | Return clear status, operation ID/reconciliation |
| Retrying request body spikes memory | Caching large bodies/replaying across attempts | Heap/direct memory, GC, body sizes | Disable upload retries; cap body/concurrency |
| CircuitBreaker never activates | Missing starter or route filter not bound | Dependency tree, runtime filters | Add compatible starter; inspect route |
| Metrics lack breaker state | Registry/Actuator unexposed or different tags | Secured metrics endpoint, scrape target | Enable right registry/secured endpoint |
| Not-permitted metric spikes | Traffic continues hitting OPEN breaker | `CallNotPermittedException` logs | Do not treat as new backend failures |
| Tests pass green yet backend count wrong | Tests assert only HTTP status | MockWebServer recorded requests | Assert attempt counts and business commits |

### 19.1. Distinguish One Logical Operation from Multiple HTTP Attempts

A trace ID may propagate across retries, yet never assume every client/proxy preserves trace context automatically. Distinguish:

- **Logical operation ID:** identifies one business intent (e.g., hashed idempotency key).
- **Trace ID:** links spans across a distributed trace.
- **HTTP attempt:** one outbound call to upstream.
- **Business execution/commit ID:** actual recorded business execution.

One logical operation can span multiple HTTP attempts with only one business commit. A client can also submit two distinct logical operations with identical payloads. Each identifier serves a distinct role and must not be conflated.

## 20. Pre-Enablement Checklist for Retry / CircuitBreaker

### 20.1. Retry

- [ ] Retry-owning layer designated; no uncontrolled stacked retries across client/Gateway/LoadBalancer/WebClient.
- [ ] Operations classified by business idempotency, not HTTP method alone.
- [ ] Write/payment/refund/upload routes have no blind retries.
- [ ] Stable idempotency key preserved across all attempts of one logical operation.
- [ ] Backend stores durable deduplication records, unique constraints, and request hashes.
- [ ] Same key with different payload returns conflict rather than silent replay.
- [ ] Off-DB side effects use appropriate provider keys/outbox/inbox/sagas.
- [ ] Retries target only selected transient errors, never auth/validation/business rejections.
- [ ] Attempt caps, backoff/jitter, and overall deadlines are enforced.
- [ ] Large/streaming request bodies are not replayed uncontrollably.
- [ ] Metrics/logs track attempts per logical operation and backend commits.

### 20.2. Circuit Breaker

- [ ] Explicit dependency name/route mapping; breaker instances are not shared unintentionally.
- [ ] `minimumNumberOfCalls`, sliding window, and thresholds fit traffic/SLO.
- [ ] Slow-call threshold compared against HTTP client timeouts and latency objectives.
- [ ] Exceptions/statuses recorded/ignored appropriately.
- [ ] `CallNotPermittedException` separated from backend failures.
- [ ] HALF_OPEN probe count is safe for recovering backends.
- [ ] Fallbacks never call back into the same OPEN upstream.
- [ ] Fallbacks never return fake 200/202 for unresolved transactions.
- [ ] Breaker state/metrics tagged by Pod/instance/route.
- [ ] Canary/rollback config workflow exists instead of repeatedly resetting breakers.

### 20.3. Testing and Operations

- [ ] Tested timeout occurring **after commit**, with client resending the same idempotency key.
- [ ] Tested two concurrent requests with the same key proving atomic deduplication.
- [ ] Tested same key with a different payload.
- [ ] Tested Retry with 503 then 200 asserting exact backend attempt count.
- [ ] Tested POST route does not retry.
- [ ] Tested Retry/CircuitBreaker filter order with runtime counters.
- [ ] Tested CLOSED→OPEN→HALF_OPEN→CLOSED transitions and failing probes.
- [ ] Tested fallback status/body ensuring no fake success.
- [ ] Tested across multiple Gateway replicas/LoadBalancer instances if horizontally scaled.
- [ ] Dashboards track failure rate, slow-call rate, not-permitted calls, retries, and backend commits.
- [ ] No raw tokens/cookies/payment data/idempotency keys logged.
- [ ] Actuator/metrics restricted to a secured management plane.

## 21. Hands-On Practice Exercises

### Exercise 1 — Find the Layer Causing Duplicates

An order-creation POST shows this timeline:

~~~text
Client sends 1 request
Gateway logs 2 attempts
Orders service logs 2 handler executions
Database contains 1 order
~~~

Explain why the database holds only one order even though the backend ran twice. Prove that idempotency worked, then locate why Gateway retried the POST. Propose a configuration ensuring only GET is retried.

### Exercise 2 — Timeout After Commit

Using a stub/test backend: commit the order and intentionally drop the response. Client retries with the same key. Verify:

- Only one order is created.
- The second response replays the same resource ID.
- Same key with a different payload returns 409.
- No second payment capture occurs.

### Exercise 3 — Find Why CircuitBreaker Tripped OPEN

Set `minimumNumberOfCalls=4`, window 4, failure threshold 50%. Send 2 successes + 2 failures. Observe state, not-permitted calls, and HALF_OPEN. Adjust thresholds and explain the trade-off between detection speed and false-opens.

### Exercise 4 — Verify Filter Order

Build a route using both Retry and CircuitBreaker. Have the stub return 503 twice then 200. Compare:

- Backend attempts.
- Breaker call/failure events.
- Client response.
- Fallback counts.

Never deduce filter order solely from YAML line order; record the runtime chain on your actual version.

### Exercise 5 — Mitigate a Retry Storm

Simulate 20 Gateway instances simultaneously calling a stub returning 503. Compare immediate retries against backoff/jitter + circuit breaker + concurrency limits. Record requests/sec, p99, and dependency recovery time.

Never generate load against production or unauthorized services.

### Exercise 6 — Fallback for Optional Data

A mobile home screen needs catalog, recommendations, and profile. Determine:

- Under what conditions can recommendations fall back to stale/empty?
- Can profile/authorization fall back to guest/admin?
- Can price/inventory be stale?
- Which circuit breakers should be split per dependency?
- Which response status communicates degradation without misleading clients?

## 22. Self-Check Questions

**1. Why does a timeout not mean the backend failed to execute side effects?**

Because the backend may have committed the transaction while the response was lost before reaching Gateway/client. Gateway only knows it did not receive a response in time.

**2. Does retrying twice mean how many total attempts?**

Usually `retries` counts additional retry attempts beyond the initial attempt, yet you must verify your filter/version contract and account for retries at other layers.

**3. Can POST ever be retried safely?**

Yes, if the business operation is designed to be idempotent, uses a stable key, durable deduplication, and off-DB side effects also enforce deduplication. You cannot infer safety from the HTTP method alone.

**4. Why must the same `Idempotency-Key` with a different payload be rejected?**

Because one key represents one intent. Allowing a different payload to reuse the key makes replay results ambiguous and risks data/authorization bugs.

**5. Does an OPEN circuit breaker retry requests itself?**

No. It rejects calls fast; retry is a separate mechanism and can be blocked by an OPEN breaker.

**6. How do failure rate and slow-call rate differ?**

Failure rate counts calls classified as failed; slow-call rate counts calls exceeding the duration threshold even if they returned 200.

**7. Why might a breaker trip after only a few failures?**

Due to low `minimumNumberOfCalls`, a small window, a low failure threshold, or multiple retries being counted as separate samples.

**8. Does `CallNotPermittedException` mean the backend just returned an error?**

No. It indicates the breaker is OPEN so the call was never sent to the backend.

**9. Why does filter order between Retry and CircuitBreaker matter?**

Because it determines whether the breaker observes each individual attempt or only the final outcome of a logical request after retries; this affects failure rates and when the breaker trips OPEN.

**10. Why can a fallback returning 200 be dangerous?**

Clients may assume an order/payment succeeded even though backend commit status is unknown. Fallbacks must accurately convey degraded/pending/unknown states per contract.

**11. Should one breaker name be used for every route to the orders service?**

Only when those routes share the same dependency, SLO, and failure semantics. Read endpoints and command/batch endpoints often need distinct policies; avoid unintended state sharing.

**12. How do you prove idempotency truly works?**

Resend the same key after a response is dropped post-commit, then verify only one business record/provider side effect exists and the retry returns the identical result.

## 23. Official and Reference Documentation

1. [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html): retries, statuses, methods, exceptions, and backoff.
2. [Spring Cloud Gateway Server WebFlux — CircuitBreaker GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter-factory.html): breaker name, fallback URI, and status codes.
3. [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): Reactor/Resilience4j integration and configuration.
4. [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): state machine, sliding windows, failure/slow-call rates, and events.
5. [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): retry attempts, interval functions, and exception/result predicates.
6. [Spring Cloud LoadBalancer — Retry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): load-balancer behavior/configuration per release.
7. [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive downstream calls, timeouts/cancellation, and composition.
8. [HTTP Semantics — RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html): method semantics, safe/idempotent methods, and response behavior.
9. [Stripe — Idempotent Requests](https://docs.stripe.com/api/idempotent_requests): example provider idempotency contract, storing/replaying results, and conflict behavior.
10. [AWS Builders’ Library — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/): designing idempotency for APIs and retries.
11. [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint, Micrometer registry, and exposure.

**Key takeaway:** Retries aid recovery from transient errors yet can **resend an already-committed operation**. Writes require stable idempotency keys, durable deduplication, and protection for off-DB side effects. An OPEN circuit breaker signals a dependency is considered unhealthy; inspect failure/slow-call rates, minimum calls, exception policies, filter order, and HALF_OPEN probes before adjusting thresholds. Only when you measure **logical requests, downstream attempts, and business commits** together can you distinguish retry storms, duplicate operations, and unexpected breaker trips.
