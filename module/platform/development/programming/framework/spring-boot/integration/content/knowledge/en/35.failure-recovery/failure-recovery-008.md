# Rate Limiting and Traffic Shaping Based on Target System Capacity

## 1. Why Is Traffic Throttling Part of Failure Recovery?

In a **Spring Boot Integration** system, a service may simultaneously call partner HTTP APIs, query databases, publish messages to RabbitMQ/Kafka, access Redis, and run Spring Integration adapters. Every target system has finite capacity: requests per second, concurrent connections, message processing speed, per-minute quotas, or quotas shared across multiple clients.

Suppose an Order application runs four replicas, each sending 35 payment requests per second. Combined, the system emits **140 requests/second**, while the partner permits only 100 requests/second for that account. Without throttling, the partner responds with HTTP `429 Too Many Requests` or `503 Service Unavailable`, raising timeouts and triggering retries. Those retries overload the target even further—creating a **failure amplification loop (retry storm)**.

Rate limiting caps the **dispatch rate** of requests; concurrency limiting caps how many requests **occupy resources simultaneously**; bounded queues and backpressure let the application react cleanly when incoming demand exceeds processing capacity. They complement each other in a recovery strategy rather than any single setting replacing the rest.

### Three Questions to Answer Before Writing Code

1. **How much can the target handle?** Distinguish per-account quotas, sustained rate, allowed burst, connection limits, and latency under heavy load.
2. **Which sources generate traffic?** Single instances, multiple replicas, broker consumers, scheduled jobs, retries, and sibling apps sharing credentials all count toward the total.
3. **When capacity is full, what should the app do?** Fail fast, persist work in a durable queue, slow producers, prioritize critical requests, or return `PENDING`?

The running example here is **Order Service calling Payment Provider over HTTP**. The same principles apply to JDBC, Redis, SMTP, and message broker consumers, adapted to each protocol's capabilities.

## 2. Distinguishing Rate Limiting, Concurrency Limiting, and Backpressure

| Mechanism | Constraint | What It Solves | What It Does Not Guarantee |
| --- | --- | --- | --- |
| **Rate limit** | Attempts per time window, e.g., 20 requests/sec. | Prevents quota breaches and smooths dispatch rate. | Does not bound in-flight waiting requests if latency spikes. |
| **Concurrency limit / bulkhead** | Active executing operations, e.g., max 8 concurrent HTTP calls. | Protects connection pools, threads, and target capacity. | Does not cap requests/sec when calls complete ultra-fast. |
| **Bounded queue** | Pending item count and max wait time. | Absorbs brief bursts; defers execution. | Does not increase target capacity; unbounded queues turn overload into latency and OOM. |
| **Backpressure** | Signals/controls slowing or pausing upstream producers. | Keeps the system from accepting work faster than it can process. | Cannot slow external producers whose contracts lack flow control. |
| **Load shedding** | Proactively rejects or drops low-priority work over threshold. | Protects critical operations and system stability. | Unsuitable for mandatory requests unless work is durably persisted first. |
| **Circuit breaker** | Temporarily stops calls once error/slow rates exceed threshold. | Prevents hammering an already-broken target. | Does not replace quotas or rate limiters while the target is healthy. |
| **Retry with backoff** | Retries eligible errors with bounded spacing. | Rides out transient glitches. | Amplifies load unless paired with traffic budgets and idempotency. |

Key insight: **100 requests/second** and **100 concurrent requests** are different units. If each request averages 2 seconds, even 50 requests/second yields ~100 concurrent active requests in steady state.

## 3. Sizing Budgets from Target System Capacity

### 3.1. Distinguish Partner SLAs from Measured Capacity

Real limits come from API contracts, gateways, target ops teams, or load tests. Never assume an HTTP endpoint that answers fast in staging will sustain production load. Clarify:

- Does the quota apply per **API key, account, tenant, endpoint, HTTP method, or globally**?
- Is the window **per second, per minute, daily quota, or concurrent request cap**?
- Are bursts allowed? Will a 50-request burst in 100 ms be rejected even though the 1-second average stays under 100?
- Do other apps share the same quota? Are there cross-region or account-wide caps?
- Does the quota count **every attempt reaching the target** (including retries), or only completed requests?

When multiple caps exist, satisfy all simultaneously. If a partner caps at 120 requests/sec and 4,000 requests/min, sustaining 120 requests/sec for a minute breaches the per-minute cap—so budget for both.

### 3.2. Example Calculation of Rate and Concurrency

Suppose a partner advertises **100 requests/second** for your account with no sibling clients sharing it. Keeping **20% headroom** for variance and high-priority calls, the system targets **80 attempts/second** across all replicas.

Little's Law in steady state:

\[
L = \lambda W
\]

Where `L` is average in-flight items, `\lambda` is average completion rate, and `W` is average processing time. With 200 ms average target latency at 80 requests/second:

\[
L \approx 80 \times 0.2 = 16 \text{ in-flight requests}
\]

The figure 16 is a **directional average**, not an automatic safe concurrency cap. Measure latency distributions, p95/p99, burstiness, actual connections, and behavior under slowdowns. If latency climbs to 1 second while you keep pushing 80 requests/second, concurrency approaches **80 in-flight requests**, imposing much heavier load.

For planning, track separately:

| Threshold | Example | Role |
| --- | --- | --- |
| Partner quota | 100 attempts/sec | Contractual ceiling never to breach. |
| System-wide target budget | 80 attempts/sec | Leaves headroom for traffic variance. |
| Replicas calling target | 4 fixed replicas in example | Determines per-replica split if using local limiters. |
| Per-replica budget | 20 attempts/sec | Valid only when all replicas and shared clients are accounted for. |
| Per-replica concurrency limit | e.g., 8 | Starting point verified via load testing, not inferred from rate alone. |
| Max wait time | Within endpoint latency budget | Prevents requests queuing infinitely before/during target calls. |

If autoscaling expands 4 replicas to 8 while keeping **20 requests/sec per replica**, total load doubles to **160 requests/sec**, blowing past quota. That is why you must distinguish **per-instance local** limits from **cluster-wide shared-identity** limits.

## 4. Traffic Shaping Algorithms

### 4.1. Fixed Window and Sliding Window

**Fixed window** counts requests in consecutive buckets (e.g., each second). Simple to implement, yet permits double bursts across boundaries: 20 requests at the end of one second plus 20 right at the start of the next.

**Sliding window** evaluates a rolling lookback from the current timestamp, reducing boundary spikes at the cost of more complex state or approximation. Verify how your library computes windows and what precision you need.

### 4.2. Token Bucket

A **token bucket** has capacity `B` tokens and refill rate `r` tokens/second. Each request consumes one or more tokens:

- If tokens are available, the request proceeds immediately.
- If empty, the system rejects, waits up to a limit, or enqueues work.
- After idle periods, tokens accumulate up to `B`, allowing bounded bursts.

For example, `r = 20` tokens/sec, `B = 10` tokens: up to 10 requests can burst together when full, after which sustained rate follows `r`. If the target forbids bursts, shrink bucket capacity or pace dispatch evenly.

### 4.3. Leaky Bucket and Paced Shaping

**Leaky bucket/shaping** dispatches work at a smooth cadence (e.g., one request every 50 ms), helpful when targets are burst-sensitive. If arrivals exceed dispatch rate for long periods, queues grow; bound queue size, max wait, and overflow behavior.

| Algorithm | Characteristics | Typical Choice |
| --- | --- | --- |
| Fixed window | Simple; allows boundary bursts. | Lightweight administrative limits, approximate quotas. |
| Sliding window | Fairer rolling lookback enforcement. | Strict rolling-window quota compliance. |
| Token bucket | Permits defined bursts while holding average rate. | Target APIs with documented burst allowances. |
| Leaky bucket / paced queue | Smooths dispatch cadence. | Targets sensitive to simultaneous arrival spikes. |

Never call every `RateLimiter` a token bucket. For instance, granting `N` permissions per refresh cycle implements a **fixed-window** style limit, not smooth leaky-bucket pacing.

## 5. Where to Place Limits in an Integration Flow?

~~~mermaid
flowchart LR
    A["HTTP / scheduler / broker"] --> B["Validate contract & priority"]
    B --> C{"Capacity to accept work?"}
    C -->|No| D["429/503 or durable queue"]
    C -->|Yes| E["Outbound rate limiter"]
    E --> F["Concurrency bulkhead"]
    F --> G["HTTP client / adapter"]
    G --> H[("Target system")]
    H --> I["Outcome / Retry-After"]
    I --> J["Retry policy & state update"]
~~~

There are at least three control points:

1. **Inbound API**: limit by user/tenant, API key, or endpoint to protect your own service. When callers exceed published quotas, return HTTP `429` with retry guidance.
2. **Outbound connector**: limit against **target capacity**, covering traffic from scheduled jobs, broker consumers, and HTTP requests alike. This directly shields the partner.
3. **Broker consumer / worker**: limit concurrent messages and outbound dispatch pace. Pause consumers, reduce concurrency, or route to bounded delay queues depending on the broker.

Throttling only at the ingress API gateway is insufficient if scheduled jobs, retries, and message consumers also generate outbound traffic. Conversely, throttling only outbound while accepting unbounded inbound work saturates queues, memory, and response times inside your own app.

## 6. Spring Boot Example: `RateLimiter` Combined with Concurrent HTTP Call Limits

The example uses **Spring Boot 3.2+, Java 17+, `RestClient`, and Resilience4j RateLimiter 2.x**. Crucially, **every attempt hitting the Payment API—including retries—must pass through this same connector**. Align the Resilience4j dependency version with your platform BOM; the code illustrates core `resilience4j-ratelimiter` APIs.

Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-ratelimiter</artifactId>
        <version>2.2.0</version>
    </dependency>
</dependencies>
~~~

Example `application.yml`:

~~~yaml
app:
  payment:
    base-url: https://payment.example.net
    max-attempts-per-second: 20
    max-in-flight: 8
~~~

This represents a **single-instance budget** in a 4-replica illustration. `payment.example.net` is a placeholder hostname. Never hardcode 20/replica if replica counts or shared clients fluctuate without central quota coordination.

### 6.1. Declaring Protection Beans

~~~java
package com.example.integration.payment;

import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;
import java.time.Duration;
import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PaymentTrafficConfiguration {

    @Bean("paymentOutboundLimiter")
    RateLimiter paymentOutboundLimiter(
            @Value("${app.payment.max-attempts-per-second}") int attempts) {
        return RateLimiter.of(
                "payment-outbound",
                RateLimiterConfig.custom()
                        .limitForPeriod(attempts)
                        .limitRefreshPeriod(Duration.ofSeconds(1))
                        .timeoutDuration(Duration.ZERO)
                        .build());
    }

    @Bean("paymentInFlight")
    Semaphore paymentInFlight(
            @Value("${app.payment.max-in-flight}") int maxInFlight) {
        return new Semaphore(maxInFlight, true);
    }

    @Bean("paymentRestClient")
    RestClient paymentRestClient(
            RestClient.Builder builder,
            @Value("${app.payment.base-url}") String baseUrl) {
        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_000);
        factory.setReadTimeout(2_000);
        return builder.baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

Explanation:

- `limitForPeriod` and `limitRefreshPeriod` grant up to 20 permissions per 1-second refresh cycle. Refresh-cycle limiters **can still allow bursts across cycle boundaries**; do not substitute them for smooth pacers if the partner forbids bursts.
- `timeoutDuration(Duration.ZERO)` makes the limiter **reject immediately** when out of permissions rather than blocking HTTP threads. If waiting is permitted, include wait time in latency budgets and cap queues/concurrency.
- `Semaphore` enforces an **in-process** concurrency cap; pair `tryAcquire()` with `release()` inside `finally`.
- Connect and read timeouts do not replace end-to-end deadlines across multi-hop calls. Verify actual timeout semantics with your HTTP client.

### 6.2. Connector Enforcing Both Limits

~~~java
package com.example.integration.payment;

import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;
import java.math.BigDecimal;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record PaymentCommand(String operationId, BigDecimal amount) {}
record PaymentReply(String transactionId, String status) {}

class DownstreamBusyException extends RuntimeException {
    DownstreamBusyException(String message) {
        super(message);
    }

    DownstreamBusyException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Service
public class PaymentConnector {
    private final RestClient client;
    private final RateLimiter limiter;
    private final Semaphore inFlight;

    public PaymentConnector(
            @Qualifier("paymentRestClient") RestClient client,
            @Qualifier("paymentOutboundLimiter") RateLimiter limiter,
            @Qualifier("paymentInFlight") Semaphore inFlight) {
        this.client = client;
        this.limiter = limiter;
        this.inFlight = inFlight;
    }

    public PaymentReply authorize(PaymentCommand command) {
        Supplier<PaymentReply> remoteCall = () -> {
            if (!inFlight.tryAcquire()) {
                throw new DownstreamBusyException(
                        "Payment concurrent-call capacity exhausted");
            }
            try {
                return client.post()
                        .uri("/authorizations")
                        .header("Idempotency-Key", command.operationId())
                        .body(command)
                        .retrieve()
                        .body(PaymentReply.class);
            } finally {
                inFlight.release();
            }
        };

        try {
            PaymentReply reply =
                    RateLimiter.decorateSupplier(limiter, remoteCall).get();
            if (reply == null) {
                throw new IllegalStateException("Empty payment response");
            }
            return reply;
        } catch (RequestNotPermitted ex) {
            throw new DownstreamBusyException(
                    "Payment outbound rate budget exhausted", ex);
        }
    }
}
~~~

In this order, **each `authorize` call consumes one rate-limiter permission** before checking the semaphore; if concurrency is full, a rate-limit permit is spent even though no HTTP call went out. This is a **conservative choice that protects target quotas**, at the expense of slightly lower throughput under saturation. You may reverse or adjust ordering once wait/refund semantics are explicitly tested.

`RestClient.retrieve()` throws exceptions on 4xx/5xx responses; upper layers must classify `429`, `503`, timeouts, and non-retryable errors. `Idempotency-Key` prevents duplicates only when the **Payment Provider actually stores and enforces results by that key**—never assume sending the header alone ensures once-only execution. For payments, reuse the **identical key** across every retry and reconciliation attempt.

> **Example Limitations:** `RateLimiter` and `Semaphore` here exist only inside **one JVM**. Across multiple pods/replicas, global quotas must be partitioned or centrally coordinated. This example also omits durable queues, retries, and circuit breakers, which must be added per business requirements.

## 7. Responding Properly to HTTP 429 and `Retry-After`

When a target returns `429 Too Many Requests`, never retry immediately in a loop. Check **`Retry-After`** if present alongside internal quotas, request deadlines, and attempt limits.

`Retry-After` takes two standard HTTP formats:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 12
~~~

`12` means retry after **12 seconds**. Or:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: Sat, 21 Nov 2026 10:00:00 GMT
~~~

The second form is an **HTTP-date**. Never parse both forms by blindly converting to an integer; parse both formats properly, handle clock skew, past timestamps, invalid values, and cap maximum wait durations.

### Outcome Classification and Handling

| Signal | Interpretation | Appropriate Action |
| --- | --- | --- |
| `429` with `Retry-After` | Target quota or throttling policy triggered. | Defer attempt until after suggested delay if deadline permits; share slowdown signal across workers calling that target. |
| `429` without `Retry-After` | Rate limited without recovery hint. | Jittered backoff, trim dispatch budget; never retry immediately. |
| `503` or timeout | Target temporarily unavailable or outcome unclear. | Bounded retries, circuit breaker, status lookup if side effects could have occurred. |
| `400` bad data | Contract/validation failure. | Fix payload, return clear error; retrying identically rarely helps. |
| `401`/`403` | Broken auth/authorization or missing permissions. | Fix credentials/permissions; do not add load with continuous retries. |
| `409` | State conflict or API-defined business outcome. | Interpret per partner contract; do not assume transient. |

In synchronous **HTTP request/response** flows, if waiting exceeds the caller's deadline, prefer returning `PENDING` once work is durably persisted, or return an appropriate error so the caller retries later. If work has **not** been persisted durably, never return `202 Accepted` and silently drop the request if the process crashes.

## 8. Retry Budgets: Never Let Retries Blow Quotas

A classic mistake is capping **initial requests** at 80/sec while allowing up to three retries **inside the HTTP client** bypassing the limiter. When all three attempts fire, target load surges to **240 attempts/sec**. Therefore:

1. **Every retry attempt sent to the target must acquire permission from the outbound limiter.**
2. Cap max attempts, jittered backoff, and end-to-end deadlines.
3. Reserve a dedicated **retry budget** if needed—e.g., permitting only a small percentage of outbound rate for retries during failures.
4. Never retry infinitely across broker redeliveries or scheduled job runs.
5. Apply idempotency/reconciliation to side-effecting operations.

Illustrative orchestration flow:

~~~text
Read stable operationId
  -> Check deadline and retry budget
  -> Acquire rate limiter permission for current attempt
  -> Acquire concurrency slot
  -> Execute HTTP call with timeout
  -> On success: persist confirmed state
  -> On 429/503: compute backoff + Retry-After + jitter and reschedule
  -> On unknown outcome: query status by operationId
  -> On expired deadline/attempts: transition to reconciliation state
~~~

In layered architectures, prevent **stacked retries**: HTTP client retrying 3 times × service retrying 3 times × queue consumer redelivering 3 times produces **27 attempts** for one message. Pick one primary retry owner and coordinate shared budgets.

**Exponential backoff** does not excuse ignoring `Retry-After`. If the target asks to wait 12 seconds, do not retry after 2 seconds simply because local backoff is shorter. Across multiple workers, add bounded random jitter to prevent synchronized wake-up bursts.

## 9. Multi-Replica, Multi-Tenant, and Cluster-Wide Quotas

Local rate limiters only observe **one process's** traffic. When a quota applies to a shared API key, three patterns are common:

| Option | How It Works | Control Considerations |
| --- | --- | --- |
| **Static per-replica allocation** | Divide global quota across replicas. | Fragile under autoscaling, rolling deploys, and uneven traffic; requires safety headroom. |
| **Distributed limiter** | All replicas request tokens/permissions via Redis or a central quota service. | Requires atomic operations, TTL/clock policies, latency budget, Redis-down fallback, and key isolation. |
| **Central gateway/dispatcher** | All outbound calls route through a queuing/throttling tier. | Dispatcher becomes a critical dependency needing HA, backpressure, and monitoring. |

Suppose an **80 req/sec cluster quota** splits into 20 req/sec across 4 replicas. When one replica sits idle while another is hot, static splits waste unused quota. A distributed limiter shares capacity flexibly at the cost of network latency and another operational dependency.

With Redis, running separate `GET` then `SET` commands **is not atomic** under concurrency. Use atomic primitives (Lua scripts, proper transactions, or distributed limiter libraries) and define failure behavior when the quota store is unreachable:

- **Fail closed**: temporarily reject or queue to avoid breaching target quotas when violations carry severe penalties.
- **Bounded fail open**: allow limited fallback traffic within conservative local caps when availability outweighs strict quota compliance and the partner tolerates minor bursts.

Document the policy explicitly; never let a Redis outage silently become "allow unlimited outbound traffic."

### 9.1. Fair Allocation Across Tenants and Priorities

A single noisy tenant must not consume the entire budget for all other tenants. Use a two-tier limiter:

~~~mermaid
flowchart TD
    A["Outbound operation"] --> B["Per-tenant limiter"]
    B --> C["Global API-key limiter"]
    C --> D["Per-target concurrency limit"]
    D --> E["Payment API"]
    B --> F["Controlled rejection / wait"]
    C --> F
    D --> F
~~~

Workloads with different priorities (active checkouts, marketing emails, report syncs) should use isolated queues/worker pools or reserved quota slices so low-priority traffic cannot starve critical paths. Explicitly define how high-priority bursts behave so they do not inadvertently breach the partner's aggregate cap.

## 10. Queues, Brokers, and Spring Integration: Throttling from the Source

When work **can be deferred**, a durable queue absorbs bursts far better than blocking thousands of HTTP threads:

~~~mermaid
flowchart LR
    A["Order API"] --> B[("Database + Outbox")]
    B --> C["Relay"]
    C --> D[("Broker")]
    D --> E["Concurrency-bounded consumer"]
    E --> F["Outbound rate + bulkhead"]
    F --> G["Payment / Notification API"]
    E --> H["Delayed retry / DLQ"]
~~~

In this architecture:

1. The app **persists work durably** and returns `202 Accepted` with a tracking ID if the contract allows.
2. Consumers cap concurrent processing, and every outbound attempt goes through the rate limiter.
3. When over quota, defer retries or let the broker delay redelivery. **Avoid tight immediate nack/requeue loops**, which burn CPU, logs, and network.
4. Enforce max message age, max attempts, and DLQ/quarantine workflows so queues never grow unbounded.

Spring Integration provides `IntegrationFlow`, inbound/outbound adapters, `MessageChannel`, `Gateway`, and error flows. These building blocks make it clean to attach limiters **right at the outbound target adapter**, though they do not automatically provide distributed quotas. For example:

~~~mermaid
flowchart LR
    I["Inbound AMQP/Kafka adapter"] --> C["MessageChannel"]
    C --> V["Filter/validate contract"]
    V --> L["Rate-limited Service Activator"]
    L --> O["Outbound HTTP gateway"]
    L --> X["Retry/Error policy"]
~~~

With `DirectChannel`, steps run synchronously on the sender's thread; with `ExecutorChannel`, execution crosses a thread boundary; with a default `QueueChannel`, messages sit only in memory. **Never treat in-memory `ExecutorChannel` or `QueueChannel` as durable across restarts**. For brokers, align prefetch, concurrency, acknowledgments, retry/DLQ, and transaction/offset commits.

### 10.1. Measuring Backlog Stability

With arrival rate `\lambda` and sustainable processing rate `\mu`:

- If `\lambda < \mu` over the long run, backlogs can drain.
- If `\lambda > \mu` persists, backlogs grow indefinitely regardless of queue size.

If jobs arrive at **150/sec** while the target sustains **80 attempts/sec**, the backlog grows by at least **70 jobs/sec** (before retries or multi-attempt work). Over 10 minutes, queued work swells by ~**42,000 jobs**. No queue setting turns capacity 80 into 150; you must shed/throttle intake, negotiate higher quotas, reduce outbound calls per business operation, or scale target capacity.

## 11. Combining Rate Limiters with Bulkheads, Circuit Breakers, and Timeouts

Use each protection for its dedicated role:

| Mechanism | Primary Decision | Example |
| --- | --- | --- |
| Rate limiter | **May a new attempt start right now?** | Max 20 attempts/sec from one instance. |
| Semaphore bulkhead | **How many attempts currently occupy resources?** | Max 8 concurrent calls to Payment. |
| Timeout/deadline | **How long may each attempt and the whole operation wait?** | HTTP read timeout 2s; total deadline per contract. |
| Circuit breaker | **Is the target failing enough to pause calls temporarily?** | Open circuit when windowed error rate crosses tested threshold. |
| Retry budget | **Is another attempt permitted?** | Retry transient errors only, bounded count and rate. |
| Queue/buffer | **If we cannot call right now, where does work live?** | Persistent broker or bounded job table with expiry. |

Order execution intentionally: validate bad inputs first, fail fast on expired deadlines or open circuits, acquire rate-limit permission, then hold a concurrency slot during I/O. Wrap decorators so **every attempt, including retries, consumes quota**; placing the limiter outside the whole retry block lets inner attempts breach quotas.

Never hold a JDBC/JPA transaction open while waiting on a rate limiter or `Retry-After`: that holds locks and connections and fuels cascading failures. For long waits, persist state in a short transaction and schedule deferred processing using outbox/idempotency as needed.

## 12. Error Contracts and Recovery Design

### 12.1. Responding to Your Own Application's Clients

When your API enforces caller quotas, return `429` with `Retry-After` if a sensible retry time is known. When your system itself is overloaded and cannot accept work, `503` or an appropriate business error fits better. Pick statuses by **contract semantics** rather than mechanically forwarding every Payment Provider status code as-is.

For async intake, return `202 Accepted` **only after durably persisting the job** with a lookup ID and clear expiration rules. A `PENDING` status must never be interpreted as "paid."

### 12.2. Never Equate Timeout with Business Failure

For side-effecting operations like capturing payment or creating transactions:

~~~mermaid
sequenceDiagram
    participant Order as Order Service
    participant Provider as Payment Provider
    Order->>Provider: POST /authorizations, operationId=X
    Provider->>Provider: Record payment X
    Provider--xOrder: Response lost / timeout
    Note over Order: Real outcome unknown
    Order->>Provider: Query status for X
    Provider-->>Order: X already recorded
    Note over Order: Do not execute a second payment
~~~

On timeout, **unknown outcome** is a meaningful state. APIs need `operationId`/idempotency keys, status lookups, and reconciliation. If a partner lacks them, introduce a manual review or verification step before retrying potentially duplicating operations.

### 12.3. Classify Errors Before Retrying

Separate `validation failure`, `quota exceeded`, `temporary unavailable`, `business rejection`, and `unknown outcome`. Each group gets distinct states, retry policies, and user messaging. Route unrecoverable failures to a DLQ with diagnostic context—without logging secrets, tokens, card data, or unnecessary PII.

## 13. Observing Whether the Limiter Actually Protects the Target

Tag metrics with `destination`, `operation`, environment, and tenant/quota tier at controlled cardinality:

| Metric Group | What to Observe |
| --- | --- |
| Rate limit | Permissions granted/denied, wait rate, effective rate per instance and cluster-wide. |
| HTTP client | Total attempts/sec, p50/p95/p99 latency, 429/503 errors, timeouts, unknown outcomes. |
| Concurrency | Active in-flight calls, remaining permits, bulkhead rejections, connection pool saturation. |
| Retry | Retry rate, attempts per operation, backoff duration, retry budget exhaustions. |
| Queue/broker | Queue depth, consumer lag, oldest message age, retry backlog, DLQ count, throughput. |
| Business | Overdue `PENDING` payments, transactions needing reconciliation, time-to-final-outcome. |

**Seeing 429s drop is not enough**: 429s might drop merely because internal layers are rejecting too much legitimate work. Track completion rates, wait durations, and shed/failed job counts too. When changing quotas or scaling replicas, dashboards should show **actual aggregate outbound attempts** per API key.

Set actionable alerts such as "queued message age exceeding SLO" or "sustained 429 spike despite outbound attempts staying below expected budget." Propagate trace/correlation IDs across initial requests, retries, outbox events, and target calls while keeping `operationId` constant across attempts.

## 14. Load and Fault Testing Before Deployment

| Test Case | Expected Result |
| --- | --- |
| Single replica receives instant burst of 100 requests | Outbound attempts follow the chosen algorithm; excess fails or queues per policy. |
| Four replicas concurrently call Payment | Aggregate attempts/sec stay inside shared quota, including retries and sibling clients. |
| Scale from 4 to 8 replicas | Global quota does not accidentally double; distributed limiter or allocator adapts properly. |
| Target slows from 200 ms to 2 s | In-flight calls remain bounded; thread/connection pools and queues do not grow unbounded. |
| Target returns 429 with `Retry-After: 12` | Workers do not retry early, while still checking deadlines and retry budgets. |
| Target returns sustained 429s | No retry storm forms; actual dispatch rate backs off per policy. |
| Target returns 400 validation error | Never retries identical invalid data; error classified accurately. |
| Timeout after target already committed | Retries with same idempotency key or queries status; zero duplicate transactions. |
| Redis / quota service outage | Enforces the agreed fail-closed or bounded fail-open policy accurately. |
| Full queue and stalled consumers | Backpressure/load shedding and DLQ/expiry work without JVM OOM. |
| Process restart with pending work | Durably persisted jobs recover and continue processing. |

Coordinate load tests with **real target capacity** and authorized environments; never blast a production partner API just to probe limits. Use mock HTTP servers simulating 429/503/timeouts, then run controlled tests against a provider sandbox. For brokers, use real integration environments to verify acks, redeliveries, retries, and DLQs.

An essential test is **counting requests actually received by the mock server**, rather than only counting service method calls. If a retry decorator sits inside the rate limiter, this test immediately catches outbound attempts exceeding quotas even when business calls look within bounds.

## 15. Throttling Selection Checklist

Before rolling out configuration into Spring Boot, confirm:

- [ ] Documented **target limits** per API key, endpoint, window, burst, and concurrency, with safety headroom and quota owners.
- [ ] All traffic sources and every retry attempt pass through outbound limits—not just ingress gateways.
- [ ] Distinguished per-JVM limiters from cluster-wide limiters, accounting for autoscaling and shared clients.
- [ ] Bounded in-flight concurrency, timeouts, and queues, with clear rules on rejecting vs. persisting work.
- [ ] Explicit handling for HTTP 429, `Retry-After`, 503, timeouts, circuit breakers, and retry budgets.
- [ ] Side-effecting operations have idempotency keys, status lookups, and reconciliation.
- [ ] No database transactions held open across long waits; async steps track accurate business states.
- [ ] Metrics, alerts, multi-replica tests, fault injection, and post-restart recovery tests in place.

**Target-capacity rate limiting** succeeds only as part of a cohesive traffic-management design. It helps Spring Boot apps respect quotas, prevent overload, and give retries, circuit breakers, queues, and recovery room to work. Ultimately, data contracts, transactions, idempotency, observability, and testing decide whether integration flows preserve business correctness when targets slow down, throttle, or fail.
