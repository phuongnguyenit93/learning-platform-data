# Exponential Backoff and Overall Processing Time Limits in Spring Cloud Gateway

When a microservice temporarily returns `503 Service Unavailable` or the Gateway cannot connect to an instance, **retrying the request** can salvage a call without forcing the client to retry manually. However, retrying too quickly makes it harder for an overloaded backend to recover, while retrying for too long causes the client to time out. That is why you need **exponential backoff** paired with an **end-to-end time budget/deadline**.

In **Spring Cloud Gateway**, the `Retry` GatewayFilter Factory controls retry count, status/exception groups, methods, and backoff. However, **`maxBackoff` only caps a single wait interval between attempts—it does not automatically limit the total completion time of the entire request**. This is the most important distinction in this lesson of the **Request Retries** chapter.

This lesson connects retries with route predicates, filter chains, paths/headers, service discovery/load balancing, authentication, rate limiting, circuit breakers, TLS, and request observability: a single client request can turn into **multiple outbound attempts**, so these layers must coordinate closely.

> **Version Scope:** Examples target **Spring Cloud Gateway Server WebFlux** and the `spring.cloud.gateway.routes` syntax common in several Gateway 4.x releases. Gateway Server MVC and newer releases may differ in starter names, namespaces, DSLs, or supported details. Verify your actual Spring Boot/Spring Cloud/Gateway versions before deploying. The timeouts and limits here are for learning purposes only, not universal recommendations for every API.

## 1. How Many Backend Calls Does One Retry Mean?

In `Retry` configuration, the `retries` parameter represents the **number of retry attempts after the initial call**, not the total number of calls.

| `retries` | Initial Call | Max Retries | Max Total Attempts |
|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 |
| 1 | 1 | 1 | 2 |
| 2 | 1 | 2 | 3 |
| 3 | 1 | 3 | 4 |
| 5 | 1 | 5 | 6 |

These numbers are **configured upper bounds**, not a guarantee that every retry will occur: if the first attempt succeeds, the Gateway does not need to retry. If the response is not in a retryable status group, the method is ineligible, the exception does not match, or the request can no longer be re-sent, the filter may also skip retrying.

Example:

~~~text
Client sends 1 request GET /api/catalog/42
   attempt #1 -> backend returns 503
   attempt #2 -> backend returns 503
   attempt #3 -> backend returns 200

retries=2 is enough to allow up to 3 attempts.
Client normally receives only the final response (200) if no response has committed yet.
~~~

This affects capacity: **1 request at the Gateway edge can generate 3 downstream requests**. A dashboard that counts only client HTTP requests without counting downstream attempts will underestimate actual load.

### Retry and CircuitBreaker Are Not the Same

| Mechanism | Goal | Question It Answers |
|---|---|---|
| **Retry** | Try again on transient failures when recovery is plausible | *Is it worth trying one more time?* |
| **Backoff** | Space out retry attempts | *If retrying, how long should we wait?* |
| **Timeout** | Cap the duration of one operation/attempt | *How long can a single attempt wait?* |
| **Overall deadline** | Stop the entire chain from exceeding its budget | *How much time remains for the whole request?* |
| **CircuitBreaker** | Temporarily stop calling downstream during systemic errors | *Should we even call downstream right now?* |
| **Rate limiter** | Control allowed traffic from clients | *Whose traffic is this and has it exceeded thresholds?* |

No single mechanism can replace all the others.

## 2. Why Do Retries Need Exponential Backoff?

If 1,000 Gateway requests all fail at the same moment, having every request retry **immediately** can hit the backend with thousands more calls right when it is most overloaded: the **retry storm** or **thundering herd** problem.

Exponential backoff gives downstream time to recover and reduces attempt density.

Example backoff growing by a factor of 2:

~~~text
Attempt 1 fails
    wait 100 ms
Attempt 2 fails
    wait 200 ms
Attempt 3 fails
    wait 400 ms
Attempt 4 fails
    wait 500 ms (capped by maxBackoff)
Attempt 5 ...
~~~

Given:

- `firstBackoff = 100ms`: base wait duration.
- `factor = 2`: growth multiplier.
- `maxBackoff = 500ms`: **maximum wait between two attempts**.
- `basedOnPreviousValue = false`: selects calculation from the base duration and iteration count per factory contract.

In this illustrative model, the `i`-th wait can be expressed as:

\[
d_i = \min\left(d_{\max},\;d_0\times f^{i-1}\right),\quad i=1,2,\ldots,r
\]

Where `r` is the number of retries **that can actually occur**, `d_0` is `firstBackoff`, and `f` is `factor`. Exact implementation details of loop indexing and `basedOnPreviousValue` may vary slightly across versions; verify with timestamped logs.

| Retry # | Uncapped Exponential Wait | Wait Capped by `maxBackoff=500ms` | Cumulative Wait Time |
|---:|---:|---:|---:|
| 1 | 100 ms | 100 ms | 100 ms |
| 2 | 200 ms | 200 ms | 300 ms |
| 3 | 400 ms | 400 ms | 700 ms |
| 4 | 800 ms | 500 ms | 1,200 ms |
| 5 | 1,600 ms | 500 ms | 1,700 ms |

This table shows **estimated wait durations**, excluding attempt execution, networking, serialization, authentication, instance selection, or sending the response back to the client.

### `maxBackoff` Is Not `totalTimeout`

With `maxBackoff=500ms`, you **only cap each individual wait around 500ms**. If there are many retries or each attempt takes seconds, total processing time can still be very long. This is a common design mistake when looking only at `firstBackoff`, `factor`, and `maxBackoff`.

## 3. Configuring Retry with Exponential Backoff

Suppose the Gateway listens on `localhost:8080` and a read-only catalog backend listens on `localhost:9090`. Configure retries only for `GET` on specific transient infrastructure errors:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 3
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

For a request `GET /api/catalog/items/42`:

1. `Path` and `Method` predicates must match before route filters run.
2. `StripPrefix=1` shapes the downstream path to `/catalog/items/42`.
3. `Retry` is configured to retry up to three times **after the initial call**.
4. Only the listed **statuses** and matching conditions trigger retries under this policy.
5. Between retries, the filter applies backoff.
6. If all attempts fail, the final request returns an error via Gateway/downstream/error-handling mechanisms rather than generating an automatic fallback JSON.

The **status names** in `statuses` are HTTP status enum values supported by the factory in that version. Codes `502`, `503`, and `504` are chosen because they often indicate transient failures, whereas **not all 5xx codes are safe to retry**. For example, a 500 from a business error or recurring bug is unlikely to be resolved by trying again.

### Parameters of the Retry Factory

| Parameter | Role | Points to Watch |
|---|---|---|
| `retries` | Max number of retry attempts | Total attempts = 1 + retries |
| `statuses` | Specific HTTP statuses allowed to retry | Does not automatically expand to all statuses |
| `series` | Status groups (e.g., 5xx) per version | Can be too broad if business logic doesn't distinguish errors |
| `methods` | HTTP methods eligible for retry | Include only methods matching idempotency requirements |
| `exceptions` | Exception types allowed to retry | Must verify actual runtime exceptions and class hierarchy |
| `backoff.firstBackoff` | Initial wait duration | A Duration, e.g., `100ms` |
| `backoff.maxBackoff` | Cap per wait interval | **Not an overall deadline** |
| `backoff.factor` | Growth multiplier | Avoid setting too high and causing long waits |
| `backoff.basedOnPreviousValue` | Controls next step calculation from previous wait/base | Test in practice when enabling `true` |

Typically, the Retry factory supports retrying on both **HTTP statuses** and **exceptions** occurring during routing. Because concrete exceptions can come from Reactor Netty, LoadBalancer, or custom filters, never assume every `java.util.concurrent.TimeoutException` or `IOException` behaves identically across every configuration.

### Shortcut vs. Expanded Form

For filters requiring multiple arguments and a `backoff` block, the **expanded form** under `name: Retry` / `args:` is clearer and less error-prone. Do not cram Retry arguments into an arbitrary shortcut string hoping the framework parses every field.

## 4. `basedOnPreviousValue` and Jitter: Two Different Concepts

In the factory, `basedOnPreviousValue` controls whether backoff computes from the **previous wait value** or from the base value by iteration. With the same factor and max cap, initial sequences may look identical; do not assume setting `true` turns on randomness.

**Jitter** is controlled random variation so that clients or Gateway instances do not all retry at the exact same instant.

Conceptual example:

~~~text
Without jitter:
  Node A: wait 100, 200, 400 ms
  Node B: wait 100, 200, 400 ms
  Node C: wait 100, 200, 400 ms

With jitter (illustrative):
  Node A: wait  87, 180, 350 ms
  Node B: wait 121, 215, 430 ms
  Node C: wait  94, 239, 386 ms
~~~

**Do not assume the `Retry` GatewayFilter Factory has a YAML `jitter` property in every version.** If you need jitter or deadline-aware retries that the built-in factory does not provide, design a custom reactive retry policy (such as Reactor's retry API) or place resilience in a supporting downstream client, then test to avoid double-retrying at two layers.

Even when adding jitter, ensure **waits never exceed the overall budget**. Jitter is not a reason to drop deadlines.

## 5. Total Time Formula: Attempts + Backoff + Overhead

Let:

- `A = retries + 1` be the maximum number of attempts.
- `t_i` be the duration of attempt `i`, including its wait/processing time.
- `d_j` be the backoff before retry `j`.
- `h` be shared overhead: auth, route/filter chain, serialization, metrics, network/client-facing response, and remaining steps.
- `T_total` be the total elapsed time from when the Gateway receives the request until completion (or cancellation).

An estimation model:

\[
T_{total} \approx \sum_{i=1}^{A}t_i
  + \sum_{j=1}^{A-1}d_j + h
\]

This is an **estimation model**; in reality a request may finish early, overlap stages, or be cancelled by a deadline. When every attempt has an upper bound `t_attempt` and backoffs are bounded, the theoretical ceiling before overhead is:

\[
T_{max,estimate} \approx A\cdot t_{attempt}
   + \sum_{j=1}^{A-1}d_j
\]

### Example: 800ms Per-Attempt, 3 Retries

With:

~~~yaml
retries: 3
backoff:
  firstBackoff: 100ms
  maxBackoff: 500ms
  factor: 2
  basedOnPreviousValue: false
~~~

Suppose **each attempt has an actually enforced 800ms limit** (not just configured without verifying effect):

| Attempt | Max Attempt Duration | Backoff Before Attempt | Cumulative Time, Excl. Overhead |
|---|---:|---:|---:|
| Attempt 1 | 800 ms | — | 800 ms |
| Attempt 2 | 800 ms | 100 ms | 1,700 ms |
| Attempt 3 | 800 ms | 200 ms | 2,700 ms |
| Attempt 4 | 800 ms | 400 ms | **3,900 ms** |

Thus, an API with a **3-second** target can still exceed it even with `maxBackoff=500ms`. Adding Gateway and network overhead pushes the total even higher.

**If only 2 retries are allowed**, the estimate with the same numbers is:

\[
3\times800\text{ ms} + (100+200)\text{ ms}
= 2,700\text{ ms}
\]

That leaves roughly **300ms before the 3-second mark** for overhead if all assumptions hold. That is a razor-thin margin under network variance; measure P95/P99 and leave a safety margin rather than budgeting up to 100% of the SLA.

### Planning with a Budget

A practical budgeting approach:

~~~text
Client/Gateway total deadline:           3000 ms
Reserve for Gateway, network, encoding:   400 ms
Remaining budget for attempts + waits:   2600 ms

Example with only 2 retries:
  3 attempts x 700 ms             = 2100 ms
  2 backoffs (100 + 200)          =  300 ms
  Estimated total                 = 2400 ms
  Remaining headroom in budget    =  200 ms
~~~

These numbers are an **illustrative exercise**, not a guarantee if timeouts are not actually enforced, bodies are streamed, backends have slow handshakes, or proxies buffer data.

## 6. Distinguishing Per-Attempt Timeout from Overall Deadline

In Spring Cloud Gateway Server WebFlux using Reactor Netty, you can configure global HTTP client timeouts (properties vary by version):

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 1000
        response-timeout: 800ms
~~~

Typically:

- `connect-timeout` bounds the time to **establish a connection** for the corresponding HTTP client; in these lines, the global value is usually in **milliseconds**.
- `response-timeout` is the HTTP client's response wait duration per Netty/Gateway contract and is expressed as a **Duration** in global config.
- **Do not treat `response-timeout` as an end-to-end limit from client request start to full body delivery.** It applies at the outbound HTTP client layer with version-specific semantics and may not cover route matching, queueing, retry waits, DNS, streaming, and downstream full-response handling.

Some Gateway lines support per-route timeouts via metadata:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          metadata:
            connect-timeout: 1000
            response-timeout: 800
          filters:
            - name: Retry
              args:
                retries: 2
                statuses:
                  - SERVICE_UNAVAILABLE
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 200ms
                  factor: 2
~~~

**Watch the units:** in this WebFlux configuration style, **route metadata** `response-timeout` usually takes **milliseconds**, unlike **global HTTP client** `response-timeout: 800ms` which is a Duration. Never assume both places accept the same format. Test startup, inspect effective configuration, and run real requests before deploying.

### Three Time Limits Often Conflated Into One

| Limit | What Does It Protect? | Guarantees Total Time Across Multiple Attempts? |
|---|---|---|
| Connect timeout | Prevents waiting forever to connect to upstream | **No** |
| Outbound HTTP client response/read timeout | Prevents waiting too long for upstream response per client semantics | **No**, may apply per call |
| End-to-end deadline | All work from Gateway receiving request until completion/cancellation | **Yes**, if designed and enforced across the whole retry chain |

Add timeouts at the **backend**, **reverse proxy/ingress**, **API client**, and potentially **load balancer**. Make sure layers do not conflict: if the client times out after 2 seconds while the Gateway keeps retrying up to 8 seconds, many outbound calls become wasted work and can cause overload.

## 7. Designing an Overall Deadline for a Retry Chain

**The Retry factory should not be assumed to act as an overall-deadline-aware scheduler.** Even with `maxBackoff`, a separate mechanism is needed to cap the **entire chain**.

### Deadline-Aware Principle

When receiving a request, compute:

~~~text
deadline = startTime + totalBudget

Before each attempt or next sleep:
  remaining = deadline - now

  If remaining <= safetyMargin:
      stop retrying, terminate per policy

  If nextBackoff + expectedAttemptBudget > remaining - safetyMargin:
      do not schedule another attempt

  Otherwise:
      wait backoff within budget,
      execute attempt with timeout <= remaining
~~~

This is **policy pseudocode**, not a built-in setting of the `Retry` GatewayFilter Factory. If your system needs exact `remaining`-based logic, implement it with an appropriate reactive component and test cancellation, response commit, and exception mapping.

### Implementation Options

1. **Keep thresholds small enough plus an outer overall timeout:** choose retry counts, per-attempt timeouts, and backoffs so the worst-case sum stays well within a safety margin, while ingress/client/proxy also enforce clear deadlines.
2. **Custom reactive deadline wrapper/policy:** a `GlobalFilter`/`GatewayFilter` placed **outside the Retry chain** can apply an overall timeout via Reactor, provided execution order is verified and the response has not committed. Cancellation, HTTP status mapping, and cleanup must be handled properly.
3. **Propagate remaining deadline downstream via a verified internal contract:** only trust deadline headers after ingress/Gateway normalizes them; the backend stops work when expired and never trusts raw client-supplied timestamps.
4. **Move retries into the client library/backend when appropriate:** when the service itself understands idempotency, budgets, and domain errors better than the Gateway.

**Caution when using `Mono.timeout(Duration)`:** it binds the lifecycle of a reactive publisher; it does not guarantee the backend halted side effects, that the response hasn't committed, or that non-Reactor sockets/tasks cancel immediately. If a timeout fires after the HTTP response is committed, you cannot always alter status/body. That is why a custom timeout filter requires integration tests and version verification.

### Where Should Total Budget Be Placed?

- **Client budget** dictates when the consumer stops waiting.
- **Ingress/Gateway budget** should be shorter than or aligned with the client's, leaving headroom to transmit the response back.
- **Downstream budget** should receive only the remaining time and avoid starting new transactions if results will certainly arrive too late.
- **Operational timeouts** can proactively reject rather than holding requests indefinitely.

If a business API is a long-running task, consider **202 Accepted + job ID/polling or webhooks** instead of stretching timeouts and retrying a synchronous HTTP request for tens of seconds.

## 8. Timeline Illustration: When Do Retries Become Wasteful?

Suppose the client has a 2.5-second timeout, the Gateway configures 3 retries, and each downstream attempt waits nearly 800ms:

~~~mermaid
flowchart LR
    A["0–800 ms: Attempt 1"] --> B["800–900 ms: Backoff 100 ms"]
    B --> C["900–1700 ms: Attempt 2"]
    C --> D["1700–1900 ms: Backoff 200 ms"]
    D --> E["1900–2700 ms: Attempt 3"]
    E -.-> F["2500 ms: Client deadline hits before attempt 3 finishes"]
    E --> G["2700–3100 ms: Backoff 400 ms"]
    G --> H["3100–3900 ms: Attempt 4 if not cancelled"]
~~~

*The diagram depicts relative millisecond milestones for each phase (not measured telemetry). The 2,500ms deadline lands mid-way through attempt 3, while an uncapped retry schedule can stretch out to 3,900ms.*

At **2,500ms**, the client may already have given up, yet the Retry chain still plans attempt 3 and beyond. If the Gateway layer does not honor cancellation/deadlines, the backend keeps receiving load with no user left waiting for the response.

**Conclusion:** never pick a large `retries` value as a default "reliability booster." Decide based on **latency SLOs, transient failure probability, idempotency, and backend capacity**.

## 9. Which Methods Are Safe to Retry?

The HTTP method is only a **preliminary signal**, insufficient to prove safe replay. It is especially dangerous when the client never receives a response after the backend already succeeded and the connection dropped; retrying can repeat side effects.

| Method | Normally Expected Semantics | Gateway Recommendation |
|---|---|---|
| `GET` | Read, idempotent per HTTP semantics | Suitable for retrying infrastructure errors **if backend truly has no significant side effects** |
| `HEAD` | Read metadata | Retryable per contract |
| `PUT` | Idempotent semantics when identical request sets desired state | Enable only after verifying business logic, concurrency, and body replay |
| `DELETE` | Idempotent semantics though response may differ after first call | Consider target state and response when already deleted |
| `POST` | Usually creates resources/payments; not idempotent by default | **Do not enable blindly** |
| `PATCH` | May not be idempotent | Retry only when operation design and deduplication are explicit |

### Why Payment POSTs Easily Cause Double Charges

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway Retry
    participant P as Payment backend
    C->>G: POST /payments
    G->>P: Attempt 1
    P->>P: Transaction persisted successfully
    P--xG: Response lost / connection dropped
    Note over G: Gateway does not know if backend persisted
    G->>P: Attempt 2
    P->>P: Risk of recording a duplicate transaction
    P-->>G: Response
    G-->>C: Final status
~~~

To permit POST retries in a genuinely necessary scenario, the backend needs an **idempotency key** or reliable request ID, deduplication/transactional guarantees, and a result policy for duplicate attempts. Simply attaching an `Idempotency-Key` header at the Gateway is not enough: **the backend must enforce idempotent semantics** and protect its result store against concurrency.

### Body Replay and Memory

Retrying a request with a body may require **caching/buffering the body** to resend it. In Gateway Server WebFlux, retrying methods with bodies can retain the request body in memory (in some implementations via an exchange attribute like `CACHED_REQUEST_BODY_ATTR` and `DataBuffer`). Enabling retries for large uploads or large JSON payloads under high traffic can put heavy heap/direct memory pressure on the Gateway.

**Never enable POST/upload retries just because a GET test worked.** Verify memory usage, max request size, backpressure, replayability, cancellation, and streaming behavior in your exact version.

## 10. Choosing Which Errors to Retry and Which to Skip

Prioritize **transient, recoverable failures**. Common statuses to evaluate:

| Error Type | Retry? | Reason |
|---|---|---|
| `502 Bad Gateway` | Possibly | Transient reverse proxy/downstream failure |
| `503 Service Unavailable` | Possibly | Backend overloaded/under maintenance; requires backoff |
| `504 Gateway Timeout` | Conditionally | Timeout might succeed on another attempt, but risks duplicating work |
| `500 Internal Server Error` | Conditionally | If it's a deterministic logic bug, retrying only adds load |
| `429 Too Many Requests` | Not by default at Gateway | May carry `Retry-After` and quota constraints; immediate retry worsens load |
| `401 Unauthorized` | No | Invalid/missing authentication token |
| `403 Forbidden` | No | Authorization denied |
| `404 Not Found` | Usually no | Resource or route does not exist |
| `400/422` | No | Invalid request; client must fix payload |
| Connection reset/timeout | Possibly | Must inspect exception class, phase of failure, and idempotency |

### `Retry-After` on 429 or 503

Per HTTP semantics, a server may return:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
~~~

The value `5` signals a hint to wait **5 seconds** per header semantics. However, **never assume the Retry GatewayFilter automatically reads `Retry-After` and uses it instead of backoff** in every version.

If told to wait 5 seconds while **only 2 seconds remain in the overall deadline**, the sensible choice is usually **not to retry within that synchronous request**, and instead return an appropriate response so the client schedules the next call. Forwarding `Retry-After` to the client must also conform to the API contract.

### Inspecting `exceptions` at Runtime

Exceptions commonly come from I/O, timeouts, connection pools, or DNS. They **do not necessarily share the same class** across Reactor Netty/HTTP client versions. For example, Java's `TimeoutException` and a Netty-specific exception may have different hierarchies.

When customizing the `exceptions` list, do not copy class names from an old log; verify the **actual runtime exception and Retry factory configuration of the version you are running**.

## 11. Compounding Effects Across Retry, CircuitBreaker, RateLimiter, and LoadBalancer

In a microservices Gateway, filter order and scope produce noticeably different behavior.

~~~mermaid
flowchart LR
    C["1 client request"] --> AUTH["Spring Security"]
    AUTH --> LIMIT["RequestRateLimiter"]
    LIMIT --> RETRY["Retry: potentially multiple attempts"]
    RETRY --> CB["CircuitBreaker: order-dependent"]
    CB --> LB["LoadBalancer lb://catalog"]
    LB --> I1["Instance A"]
    LB --> I2["Instance B"]
    CB -.-> FB["Fallback when policy triggers"]
~~~

*This diagram **only illustrates functional groups** and does not imply a fixed ordering between `Retry`, `CircuitBreaker`, and `LoadBalancer` across all Gateway versions. `GlobalFilter` and `GatewayFilter` are ordered by `Ordered`; actual runtime order must be verified against config/runtime.*

### When Retry Wraps CircuitBreaker

If Retry sits outside CircuitBreaker in the reactive chain, **each attempt** can pass through the circuit breaker and affect its counters. Once the circuit is OPEN, subsequent attempts can be rejected immediately. Still, exact error recording and breaker state depend on filter ordering and implementation.

### When CircuitBreaker Wraps Retry

CircuitBreaker may view the **entire retry chain** as a single logical call rather than individual attempts. One request might consume multiple outbound calls before the breaker triggers fallback. Test "recorded calls," "failure rate," and "open state" rather than inferring from filter names alone.

### When RateLimiter Precedes Retry

One client request admitted by the limiter **can spawn multiple downstream attempts**. If quota is measured per client request, that request consumes one quota unit while generating three backend calls. A separate **retry budget** may be needed to avoid load amplification. Do not rely on rate limiting alone to shield the backend from retry storms.

### With Service Discovery

A `lb://catalog-service` URI may pick different instances across attempts, yet **there is no guarantee every retry goes to a fresh instance**. That depends on the LoadBalancer, discovery state, connection reuse, and filter ordering. If only one instance is unhealthy, retrying the same instance achieves nothing; per-instance observability and health policies are essential.

## 12. Total Time Limits Across Authentication, TLS, and Proxies

Total latency is more than just backend I/O.

| Component | How Can It Consume Budget? |
|---|---|
| Spring Security / JWT | Verifying claims, fetching/checking keys/JWKS per cache and config |
| Route predicate / filter chain | Evaluating conditions, mutating paths/headers, reading metadata |
| Redis RateLimiter | Calling Redis, timeouts, and queueing |
| DNS / service discovery | Selecting endpoint/instance and resolving addresses |
| TCP/TLS | Connect, TLS handshake, certificate validation |
| Backend | Business processing, DB/cache, waiting on dependencies |
| Retry backoff | Time **intentionally spent waiting** between attempts |
| CircuitBreaker | Timeout, fallback, breaker state transitions |
| Reverse proxy/CDN/client | Buffering, connections, timeouts, and response transmission time |

Therefore, when an API has a 3-second SLO, do not assign the entire 3 seconds to **each attempt's** `response-timeout` and then add multiple retries. The total deadline must be budgeted **end-to-end**, including proxy overhead and returning data to the client.

### Propagating Deadlines via Headers

Internally, you might define a header like `X-Request-Deadline` so downstream services know the cutoff for useful work. However:

- Headers from the Internet **must never be trusted by default**; ingress/Gateway must validate or regenerate them.
- Agree clearly on absolute timestamps vs. remaining durations, clock sync, and timezones.
- Never allow a client to set an "infinite" deadline to exhaust resources.
- A header carrying a deadline **does not automatically cancel work**; backends must honor it and applications still need timeouts.
- If a late cancellation happens after side effects committed, idempotency/transaction recovery is required.

This is an advanced pattern; for simpler APIs, tight budget/timing alignment and timeouts across client, edge, and backends may be more suitable.

## 13. Hands-On Lab: Measuring Retries and Inter-Attempt Delays

### Setup

Assume:

- Gateway Server WebFlux at `http://localhost:8080`.
- Demo WebFlux backend at `http://localhost:9090`, endpoint `GET /lab/flaky`.
- No secondary retry/circuit breaker at ingress, client, or test backend.
- Gateway has route `retry-flaky-lab` with 100/200/400ms backoff and `retries=3`.

Demo backend: returns 503 for the **first two calls**, then 200 on the third.

~~~java
package example.backend.lab;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FlakyController {

    private final AtomicInteger attempts = new AtomicInteger();

    @GetMapping("/lab/flaky")
    public Mono<ResponseEntity<Map<String, Object>>> flaky() {
        int current = attempts.incrementAndGet();

        System.out.println("LAB backend attempt #" + current
            + " at " + System.currentTimeMillis());

        if (current <= 2) {
            return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("attempt", current, "state", "temporarily-failed")));
        }

        return Mono.just(ResponseEntity.ok(
            Map.of("attempt", current, "state", "ok")));
    }
}
~~~

This snippet uses a **single-instance global counter** for lab convenience, not as a production backend pattern. If multiple clients call concurrently or multiple backend instances exist, the sequence number will no longer correspond to a single request. Restart the backend to reset tests, or track state per request ID via a dedicated test mechanism.

Corresponding route:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: retry-flaky-lab
          uri: http://localhost:9090
          predicates:
            - Path=/lab/flaky
            - Method=GET
          filters:
            - name: Retry
              args:
                retries: 3
                statuses:
                  - SERVICE_UNAVAILABLE
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

### Step 1 — Call the Backend Directly to Understand Baseline Behavior

~~~bash
curl -i "http://localhost:9090/lab/flaky"
~~~

The backend returns 503 on the first call. Calling twice more yields 503 then 200, assuming no other client alters the counter. Restart the backend before testing through the Gateway to reset initial state.

### Step 2 — Call Once Through the Gateway

~~~bash
curl -i "http://localhost:8080/lab/flaky"
~~~

Expected:

- Client sends **one** HTTP request.
- Backend logs roughly **three attempts** (503, 503, 200) if response/status matching and retries work as configured.
- The gap between attempt #1 and #2 includes roughly `100ms` of backoff; between #2 and #3 roughly `200ms`, plus processing and overhead.
- Client receives HTTP 200 from the third attempt, assuming no response had committed yet.

Record **backend timestamps** and **total Gateway elapsed time**. Never judge exact backoff precision from a single run: timer scheduling, network, CPU, and event loops introduce jitter.

### Step 3 — Measure Total Client Time

~~~bash
curl -sS -o /dev/null \
  -w "http_code=%{http_code} total=%{time_total}s\n" \
  "http://localhost:8080/lab/flaky"
~~~

The command above uses POSIX cURL syntax. On Windows, choose an appropriate sink/output such as `-o NUL`, and invoke `curl.exe` when PowerShell aliases `curl`.

Before each controlled measurement, reset backend state and eliminate caching or interfering requests. `time_total` is **client-observed time**, including loopback transit—not merely the sum of `firstBackoff`.

### Step 4 — Test Insufficient Retry Count

Change `retries: 1`, restart/refresh configuration per your version, and reset the backend. Because the backend fails on the first two attempts, the client can receive 503 after two attempts, never reaching the successful third call.

### Step 5 — Test Overall SLA and Per-Attempt Timeout

Create a lab backend endpoint that intentionally responds slowly, then configure the HTTP client response timeout per your version. Test sequentially:

1. **No retry**: measure duration before the request fails.
2. **Two retries**: measure outbound attempts, total elapsed time, and status.
3. **Three retries**: compare against an assumed 3-second SLA target.
4. **With a dedicated overall deadline layer**: verify how many attempts are cancelled/cut off when the budget expires.

Important: never assume a slow request **is always recognized by the Retry filter as a retryable exception**. Outcomes depend on the actual timeout/error type, `exceptions`, and implementation version. Record the allowed exception classes in your test environment and match them against policy.

### Step 6 — Test With Multiple Concurrent Clients

In a lab environment, use a concurrency-bounded load testing tool to verify:

- Do many clients retry in lockstep at 100/200/400ms marks?
- Does Redis rate limiting cap **client requests** while downstream attempts multiply?
- Do backend P95/P99 and connection pools degrade once retries are enabled?
- If one instance is shut down, does LoadBalancer pick a healthy instance next?
- Once the overall budget is exceeded, does the request genuinely stop spawning new outbound attempts?

Never stress-test a production service without explicit authorization and test safeguards.

## 14. Troubleshooting: When Backoff or Total Time Differs from Expectations

| Symptom | Common Cause | How to Verify |
|---|---|---|
| `retries: 3` produces 4 backend calls | That is 1 initial call + 3 retries | Count attempts; do not confuse retries with attempts |
| No retries seen despite backend returning 503 | Route mismatch, status/method outside policy | Check route ID, runtime filters, request path/method |
| Retries occur with no apparent delay | `backoff` failed to bind/wrong syntax or delay too tiny | Inspect effective config and backend timestamps |
| Backoff appears longer than `maxBackoff` in logs | Logs measure attempt/network/queueing, not sleep alone | Measure gap between **failure end and next attempt start** |
| Total latency exceeds `maxBackoff` | `maxBackoff` caps only one wait interval | Sum attempts + waits + overhead |
| `response-timeout: 800ms` set, yet client waits seconds | Outbound timeout applies per attempt; multiple retries run | Distinguish per-attempt timeout from end-to-end deadline |
| Client timed out, yet backend stays busy | Deadline/cancellation does not cross layers or side effect started | Track active attempts and aborted client connections |
| POST executed twice | Unsafe retry on side-effecting call | Disable POST retry by default; build idempotency key/dedupe |
| Raising retries increases 503/429s | Retry storm, overloaded backend, insufficient capacity | Lower retries, increase backoff, add jitter/budget, use circuit breaker |
| `429` gets retried repeatedly | 429 added to `statuses` without quota/`Retry-After` handling | Adjust policy; respect rate limits |
| Adding CircuitBreaker changes results | Filter ordering and breaker failure accounting shifted | Compare attempts vs. recorded calls and fallback counts |
| Does not switch to another instance | LoadBalancer/connection reuse/discovery policy | Log instance ID per outbound attempt |
| Body retry causes memory pressure | Buffering request body for replay | Monitor `DataBuffer`/direct memory; avoid upload retries |
| Failure mid-response streaming | Response already committed; cannot retry/change status pre-commit | Design a dedicated streaming error contract |
| Route metadata timeout has no effect | Wrong unit, namespace, metadata key, or version | Verify runtime config and actual measured requests |
| Errors only on a few Gateway nodes | Rollout skew, route cache, client timeout, config drift | Compare versions, routes, metrics, and logs per node |

### Layer-by-Layer Investigation Procedure

1. Confirm **route matched** and `Retry` loaded.
2. Record **method**, status, or **actual exception** to verify retry triggers.
3. Count **attempts** and timestamps for each attempt.
4. Check bound values of `retries`, `firstBackoff`, `maxBackoff`, `factor`, and `basedOnPreviousValue`.
5. Check **per-attempt timeout** and which layer triggers/cancels the request.
6. Compare total client/Gateway elapsed time against the **overall deadline**.
7. Audit CircuitBreaker, RateLimiter, LoadBalancer, and retries in client/SDK/backend layers to prevent **nested retries**.

In particular, if a client library already performs 3 retries and the Gateway performs 3 retries, a single business request can generate far more calls than expected due to **nested retries**. Clearly designate the policy owner per layer and enforce a unified total budget.

## 15. Production Checklist for Backoff and Overall Deadlines

- [ ] I know `retries` is the **number of retries**, with max total attempts equal to `retries+1`.
- [ ] I only retry **recoverable** transient statuses/exceptions.
- [ ] I explicitly scope `methods` and do not blindly enable POST/PATCH.
- [ ] I understand `firstBackoff`, `factor`, `maxBackoff`, and `basedOnPreviousValue` in my exact version.
- [ ] I know `maxBackoff` **does not cap total request duration**.
- [ ] I have roughly budgeted total attempts + total backoff + overhead against the SLO.
- [ ] I configured connect/response timeouts with the right **units for global and route metadata**.
- [ ] I have a real **overall deadline** at client/Gateway/ingress or an explicitly designed layer.
- [ ] I do not schedule a new attempt when too little budget remains to finish usefully.
- [ ] I tested cancellation, committed responses, and side-effecting backend operations.
- [ ] I do not assume the built-in Retry factory has an arbitrary jitter property without verifying.
- [ ] I defined a retry budget and avoided synchronized retry storms during backend overload.
- [ ] I honor `Retry-After`/quota policies on 429/503 per contract.
- [ ] I do not retry 401/403 or input errors like 400/422.
- [ ] I understand RateLimiter counts client requests, which can differ from total outbound attempts.
- [ ] I tested Retry/CircuitBreaker ordering and fallbacks to prevent loops.
- [ ] I verified whether `lb://` switches instances and confirmed TLS/network stability.
- [ ] I understand body retries can consume `DataBuffer` memory and avoid large upload retries until verified.
- [ ] I monitor attempt counts, retry successes, elapsed latency, 429/5xx rates, downstream saturation, and cancellations.
- [ ] I checked multi-instance Gateway behavior, rollouts, nested client retries, and trust boundaries for timeout headers.
- [ ] I have a strategy to dial down retries/roll back if retry storm symptoms rise.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — check **Retry GatewayFilter Factory**, **HTTP timeouts**, and **Server WebFlux** for your exact version.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — release train info and documentation selector.
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/) — structuring circuit breakers/fallbacks and cooperating with Retry.
- [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — reactive operators `retryWhen`, `timeout`, cancellation, and error handling.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP methods, idempotency, status codes, and `Retry-After`.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — reactive HTTP processing, streaming, and response commit semantics.

**Key Takeaway:** Successful retries are not just "trying many times." **Exponential backoff spaces out attempts; `maxBackoff` caps only one wait interval; an overall deadline caps the whole chain.** Account for `retries+1` attempts, budget per-attempt + waits + overhead, avoid repeating non-idempotent side effects, and coordinate RateLimiter/CircuitBreaker/LoadBalancer so a transient error does not escalate into system-wide overload.
