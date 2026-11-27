# Avoiding Load Amplification When Multiple Layers Retry Simultaneously

## 1. When One User Request Turns Into Dozens of Internal Requests

**Spring Cloud Gateway** typically sits at the boundary between clients and microservices. After selecting a route via predicates, the Gateway executes its filter chain, transforms paths/headers, discovers services with `lb://`, applies authentication, rate limiting, circuit breakers, TLS, and request observability. Along this chain, several components may each think: **"Upstream had a transient error, one more try should work."**

Retries can improve resilience against brief glitches like a freshly reset connection or an instance swap. However, if the **client, Gateway, service A, service B, and SDK** all retry independently, a single user action can generate dozens or hundreds of calls against the same dependency. When a backend is already slow, those extra requests slow it down further, causing more timeouts and triggering yet more retries: this is **retry amplification**.

~~~mermaid
flowchart LR
    C["Client: retry"] --> G["Spring Cloud Gateway: Retry filter"]
    G --> O["Orders service: client retry"]
    O --> P["Payment/Inventory SDK: retry"]
    P --> D["Degraded dependency"]
    D -. "Timeout / 503" .-> P
~~~

For example, a user clicks "View Order" just once, yet:

- The client tries up to **3 attempts** (initial + 2 retries).
- The Gateway tries up to **3 attempts** per client send.
- Orders service tries up to **3 attempts** for a dependency call.

In the scenario where every try propagates down to the next layer, calls hitting the deepest dependency can reach:

\[
A_{\text{dependency,max}} = 3 \times 3 \times 3 = 27
\]

That means **1 user action can spawn 27 calls** at the deepest tier. Each call can also hold connections, allocate buffers, emit logs, run DB queries, or consume quotas. If 100 such actions occur concurrently, attempts at the dependency can climb to 2,700—before counting fan-out, DB client retries, or background jobs.

**The goal of this lesson** in the **Request Retries** chapter is helping you recognize and control generated load across every layer, not merely getting one `Retry` filter to run.

After this lesson, you will be able to:

1. Distinguish a **user operation**, an **HTTP request**, an **attempt**, and a **retry**.
2. Compute upper bounds on load when retry layers nest and when fan-out exists.
3. Designate **one primary retry owner**, or partition explicit policies/budgets if multiple layers genuinely need retries.
4. Establish **retry budgets, deadlines, backoff, jitter**, and retryable error classifications.
5. Configure Spring Cloud Gateway Server WebFlux's **Retry GatewayFilter Factory** without defaulting to retrying every method or status.
6. Explain risks of body replay, double charges/duplicate orders, request cancellation, and post-commit response errors.
7. Combine retries with rate limiting, circuit breakers, load balancing, connection pools, and service discovery.
8. Measure **client requests vs. upstream attempts** and verify that the Gateway does not amplify load past limits.

> **Version Scope:** Examples target **Spring Cloud Gateway Server WebFlux** on Reactor Netty, not Gateway Server MVC. Starter names, YAML prefixes, configuration semantics, and filter ordering may vary across Spring Boot/Spring Cloud releases; always check your active release. Configuration numbers here are **illustrative for learning**, not defaults or universal production recommendations.

## 2. Attempt Counting Model: Measure With the Right Units

A very common mistake is using the word "retry" to include the initial call. Separate these terms:

| Concept | Definition in This Lesson | Example |
| --- | --- | --- |
| **User operation** | One logical action the client intends to complete | View order `O-42` or place a new order |
| **HTTP request** | One request actually sent by the client to Gateway | `GET /api/orders/O-42` |
| **Attempt** | One try by a layer to invoke downstream | One Gateway proxy call to Orders |
| **Retry** | An **additional** attempt after the first attempt | Attempt 2 or attempt 3 |
| **Fan-out** | One operation calling multiple downstream branches | Orders calling both Inventory and Pricing |
| **Deadline** | Final cutoff time an operation is allowed to wait | 800 ms left in a 2-second budget |
| **Retry budget** | Cap on retry attempts/resources allowed | Max 5% extra requests over a window, if policy defines so |

For example, `retries: 2` in **Retry GatewayFilter** generally means **up to 2 retries beyond the initial call**, or **3 attempts** when every try qualifies. Do not mistake it for "only 2 attempts."

### Upper-Bound Formula for Nested Layers

Suppose there are \(n\) layers. Layer \(i\) permits at most \(r_i\) retries and **every attempt at that layer traverses all subsequent layers**. The upper bound on attempts at the final dependency is:

\[
A_{\max} = \prod_{i=1}^{n}(1+r_i)
\]

If client has 2 retries, Gateway has 1 retry, and Orders SDK has 3 retries:

\[
A_{\max}=(1+2)(1+1)(1+3)=3\times2\times4=24
\]

**24 is an upper bound, not a guarantee that the live system emits exactly 24 requests.** Some attempts may fail before reaching downstream, a circuit breaker may be OPEN, the deadline may expire, the client may cancel, or a policy may treat a status as non-retryable.

### Amplification Comparison Table

| Client | Gateway | Service/SDK | Max Attempts at Deepest Dependency | Theoretical Amplification |
| --- | --- | --- | ---: | ---: |
| 1 | 1 | 1 | 1 | 1× |
| 2 | 1 | 1 | 2 | 2× |
| 2 | 2 | 1 | 4 | 4× |
| 3 | 3 | 1 | 9 | 9× |
| 3 | 3 | 3 | 27 | 27× |
| 3 | 4 | 3 | 36 | 36× |

Numbers in the first three columns represent **max attempts per layer**, not YAML `retries` values. Setting `retries: 2` at each layer yields 3 attempts per layer, matching the **27×** row across three layers.

### Fan-Out and Sequential Calls Differ

If Orders calls Inventory and Pricing in parallel, total calls also depend on the **branch count**. With each branch bounded by \(a_j\), calls across immediate branches grow as a sum:

\[
A_{\text{all branches,max}}=\sum_{j=1}^{m} a_j
\]

Meanwhile, a dependency sitting **deep inside a nested branch** multiplies by attempts of upstream layers ahead of it. When one operation combines fan-out and multi-layer retries, draw the **actual call graph** before computing rather than blindly multiplying across every service without considering conditional branches.

## 3. Positive Feedback Loop: Slower Backends Get Called More

Load amplification is deadliest when a backend is already near its CPU, thread pool, connection pool, or database limits:

~~~mermaid
flowchart TD
    A["Backend slow / overloaded"] --> B["Latency rises"]
    B --> C["More timeouts or 502/503s"]
    C --> D["Client / Gateway / SDK all retry"]
    D --> E["Upstream attempts surge"]
    E --> F["CPU, DB, queues, connections saturate further"]
    F --> A
~~~

This is a **positive feedback loop**: the fallback recovery mechanism worsens the failure. Symptoms include:

- Actual dependency QPS rises faster than user-facing QPS.
- Outbound HTTP connections and Reactor Netty `pending acquire` counts climb.
- TCP connect, TLS, response, and queueing waits lengthen.
- Most requests exceed deadlines before the backend can finish.
- Error logs flood because each attempt generates multiple log/trace lines.
- Autoscaling reacts slowly or fails to help when the bottleneck is the DB rather than service CPU.
- Load balancers keep picking overloaded instances, or retries spread pressure across every instance.
- Circuit breakers flap OPEN, CLOSED, and OPEN again when probes/retries are uncoordinated.

Suppose a backend sustains around **1,000 calls/s**, while users send 800 operations/s. If policy causes an average of **1.5 backend attempts per operation**, the backend sees:

\[
\lambda_{\text{upstream}}=800\times1.5=1,200\ \text{calls/s}
\]

This load **exceeds the 1,000 calls/s sustainable capacity** in the example, even though initial traffic is only 800 operations/s. Queues build, latency climbs, and retries can drive the attempt ratio higher still. **That 200 calls/s deficit will not clear on its own** without load shedding, capacity recovery, or traffic reduction.

### Checking the Amplification Ratio in Operations

For a consistently defined route and time window:

\[
\text{Amplification ratio}
= \frac{\text{Outbound upstream attempts}}{\text{Accepted inbound requests}}
\]

If 1,000 inbound requests produce 1,400 upstream attempts, the ratio is **1.4×**. Be careful though:

- An API with legitimate **fan-out** to two backends naturally has total calls/inbound > 1 even with zero retries.
- Requests rejected by authentication/rate limiting should not be mixed into another route's sample when evaluating retries.
- A request may generate zero upstream calls when a circuit breaker is OPEN; a low ratio **does not prove system health**.
- Across multiple Gateway replicas, aggregate matching windows and tags cleanly; client retries happen **outside the Gateway**, which also inflates inbound request counts.

Hence a more informative metric is **attempts per logical operation, route, and dependency**, paired with dedicated counters for retry attempts, rejected calls, and fan-out.

## 4. Where Retries Originate in a Microservices Chain

Retries can be enabled in many places outside Gateway config files:

| Layer | Common Retry Mechanism | Easily Overlooked Aspect |
| --- | --- | --- |
| Browser/mobile SDK | Automatic network retries, UI "Retry" button | User taps again while old request is still running |
| CDN / Edge proxy | Retries upstream when an instance stops responding | Same request can enter Gateway multiple times |
| Ingress / Load balancer | Retries on upstream reset, 502/503 | Creates extra attempts ahead of Gateway |
| Spring Cloud Gateway | `Retry GatewayFilter`, custom filters | Multiplies calls to backends |
| Orders / Account service | `WebClient.retryWhen(...)`, SDK clients | Retries Inventory/Payments calls deeper down |
| Service mesh / sidecar | Envoy/Istio HTTP retry policies | Generates retries outside app code |
| DB/queue client | Driver reconnects or retries | Triggers internal work multiple times, even side effects |

**Every layer must be inventoried.** Saying "Gateway only retries twice" does not cap amplification at 3× if ingress and downstream SDKs also retry.

### Layered Attempt Diagram

~~~mermaid
flowchart TB
    U["1 logical user operation"] --> C["Client: 2 HTTP attempts"]
    C --> G1["Gateway invocation #1"]
    C --> G2["Gateway invocation #2"]
    G1 --> A1["Gateway upstream attempt #1"]
    G1 --> A2["Gateway upstream attempt #2"]
    G2 --> A3["Gateway upstream attempt #1"]
    G2 --> A4["Gateway upstream attempt #2"]
    A1 --> S["Orders SDK: 3 attempts per received call"]
    A2 --> S
    A3 --> S
    A4 --> S
    S --> D["Up to 12 calls to final dependency"]
~~~

In the diagram above, edges entering "Orders SDK" represent **multiplicative call counts**, not four requests sharing one publisher or transaction.

If a retry happens **after the backend already persisted data** while the response was lost, neither Gateway nor client can infer "the backend did not process it." That leads to double bookings, double charges, or duplicate writes beyond sheer load issues.

## 5. Which Failures Are Worth Retrying and Which Are Not?

A safe retry policy distinguishes **transience**, **HTTP method**, **remaining deadline**, **whether side effects occurred**, and **backend capacity for extra load**.

| Scenario | Retry From Gateway? | Notes |
| --- | --- | --- |
| GET hits connection reset before response | Possibly, few tries within budget | Uncertain if server processed it; GET must truly be safe |
| Upstream HTTP 502/503 | Conditionally | Avoid massive retries during backend overload |
| HTTP 504 / response timeout | With caution | Server may still be processing; client deadline may be expiring |
| HTTP 429 Too Many Requests | Usually **no** immediate retry | Honor `Retry-After`, quotas, and backpressure |
| HTTP 400 Bad Request | No | Caller must fix request |
| HTTP 401 Unauthorized | No | Missing/invalid credentials; retrying same token fixes nothing |
| HTTP 403 Forbidden | No | Insufficient permissions |
| HTTP 404 Not Found | Usually no | May be normal business outcome |
| HTTP 409 Conflict | Only under special contracts | Blind retries can worsen conflicts |
| HTTP 422 Unprocessable Entity | No | Request violates data rules |
| Payment POST times out | **Never automatically** | May already have charged; needs idempotency + status lookup |
| SSE/WebSocket partially streamed | Do not retry as a short HTTP request | Needs dedicated reconnect/resume |

**No status table replaces a business contract.** For example, order-creation POST can be designed idempotently with `Idempotency-Key`, yet it is only safe if the backend persists results by key and replays them on duplicates—not merely by attaching a header.

### HTTP 503 and `Retry-After`

A backend may respond:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Cache-Control: no-store
Content-Type: application/json

{"code":"UPSTREAM_BUSY","message":"Try again later"}
~~~

`Retry-After` can be **seconds** or an **HTTP-date**, advising when to retry if the caller chooses. For a retry policy with a max wait shorter than 10 seconds, never ignore the header and call back immediately; return an error so the client tries in a new operation if allowed. **Do not assume `Retry GatewayFilter` automatically parses and honors `Retry-After` across all versions.**

## 6. Choosing the Retry Owner: Do Not Enable Everywhere

A useful design principle is **one layer owns the primary retry decision per dependency/operation**. Other layers can enforce deadlines, circuit breakers, or rate limits without spawning extra attempts themselves.

Example browser → CDN → Gateway → Orders → Inventory flow:

~~~mermaid
flowchart LR
    B["Browser: deadline, UX"] --> E["CDN: no write API retries"]
    E --> G["Gateway: budgeted GET retries"]
    G --> O["Orders: do not re-retry same call already retried by Gateway"]
    O --> I["Inventory: health/readiness + timeout"]
~~~

Still, **you do not always restrict the entire system to a single retry layer**. If Orders calls Inventory in an internal step distinct from Gateway → Orders, Orders may retry Inventory **if** justified and bounded by shared budgets and deadlines. What you must prevent is multiple layers **independently retrying the same failure** without clear ownership or an overall cap.

### Sample Ownership Matrix

| Dependency / Operation | Primary Retry Layer | What Other Layers Should Do | Reason |
| --- | --- | --- | --- |
| Public Catalog GET | Gateway (1 conditional retry) | Client offers manual retry UX; SDK does not loop endlessly | Brief connection glitches can recover |
| User Orders GET | Gateway **or** client per contract | Other layer skips default retries | Keeps deadlines clear and avoids multiplying attempts |
| Orders calling Inventory GET | Orders service (if needed) | Gateway does not multiply retries for whole request | Orders knows Inventory call cost/timing |
| Create Order POST | Backend idempotency, no blind retries | Gateway fails fast on ambiguous outcome | Prevents duplicate orders |
| Payment authorization | Dedicated client/backend payment workflow | Gateway never auto-retries | Protects funds and decision authority |
| SSE/WebSocket | Client protocol reconnect/resume | Gateway never replays entire stream | Partially sent streams cannot "restart" safely |

A **retry policy inventory** should list: API name, owner, retryable statuses, exception types, max attempts, deadlines, jitter, retry budget, idempotency, metrics, and verification tests.

### Why Is "Client Retrying After Gateway Already Retried" Easy to Miss?

Suppose Gateway spends 2 retries and finally returns 503. The client SDK sees 503 and retries the **entire request**, causing the Gateway to run up to 3 attempts again. The same failure restarts from scratch with a fresh budget; without an **operation-level budget**, each layer obeys its local cap while the combined total explodes.

To reduce risk, deliberately pick one approach:

1. Gateway handles short GET retries; client surfaces errors with user-driven retry UX and proper rate limits.
2. Client owns retries and deadlines; Gateway disables Retry on that route and proxies with timeouts, rate limits, and circuit breakers.
3. Multiple layers retry for specific needs, while an explicit **total attempt** cap via retry budgets/deadlines is enforced at trusted boundaries.

**Never trust Internet client-supplied headers** like `X-Retry-Count: 0` or `X-Max-Attempts: 100` to decide how many calls Gateway may make. Rely solely on trusted sources; if passing budgets between services, define validation, normalization, and clamping.

## 7. Retry Budgets: Keeping Retries Within a Finite Pool

`retries: 2` limits attempts **for one HTTP request at one layer**. Yet when 100,000 requests fail at once, even 2 retries per request can overwhelm backends. You need a shared budget at the route, service, or caller level.

### Two Different Budget Types

**Per-operation budget** — caps each logical action:

~~~text
GET order #42:
  Max total attempts across chosen owner = 2
  Deadline = 1.5 s
  Retry only on eligible failure
  No retry after response commit
~~~

**Fleet-level retry budget** — caps total retries over a window, e.g., allowing extra retries up to **5% of successful/valid requests** or a well-designed token quota:

\[
R_{\text{allowed}}(T) \le B(T)
\]

Where \(R_{\text{allowed}}(T)\) is allowed retry attempts in window \(T\), and \(B(T)\) is the budget computed from live throughput or fixed quota. Define the **denominator** explicitly: successful original calls, admitted requests, or a configured token bucket? Each behaves differently during an outage.

Hypothetical quota policy example:

~~~text
Admitted inbound operations in 60 s = 10,000
Additional retry cap                = 5%
Fleet-wide budget                   = 500 retry attempts
Once budget is exhausted            = no more retries; return controlled error
~~~

**This is an illustrative policy construct, not an automatic feature** gained merely by adding `Retry GatewayFilter`. Enforcing 500 attempts cluster-wide requires shared or partitioned quota accounting across Gateway replicas.

### Budgets Must Not Starve First-Attempt Requests

During overload, **prioritize fresh first-attempt requests** over spending full capacity on retries. Sound strategies:

- Reserve a small dedicated quota for retries.
- Halt retries when error rate, queue depth, or circuit-open rate crosses a threshold.
- Skip retries when remaining deadline is insufficient for useful completion.
- Use backoff + jitter to desynchronize callers.
- Isolate priority traffic and tenants where appropriate so one tenant cannot burn everyone else's budget.

A token bucket for retry attempts can live at the application or edge policy layer, yet **do not confuse it with default `RequestRateLimiter`**: rate limiters normally meter inbound requests entering Gateway rather than internal attempts spawned downstream of Retry. Verify filter order and quota accounting.

### When Multiple Gateway Replicas Retry Together

With 5 Gateway replicas each holding a local budget of 500 retries/60s, the cluster can permit up to 2,500 retries in that window unless coordinated. To enforce a **fleet budget of 500**, you can:

1. Assign fixed per-replica quotas (e.g., max 100 per replica), updating when autoscaling.
2. Use a reliable distributed quota store (with clear latency, HA, and failure semantics).
3. Use adaptive control driven by real upstream load and centralized telemetry; verify stability.

No option is free: distributed quotas introduce a new dependency and failure point. Define behavior when the budget store is unreachable: for optional retries, **failing closed on extra retries** is usually safer than unleashing unbounded attempts.

## 8. Deadlines: Do Not Retry When Results Will Arrive Too Late

Even a low retry count is wasteful if each attempt burns its full timeout before retrying. Distinguish **per-attempt timeout** from the **end-to-end deadline** of a user operation.

Suppose a client expects a response within **2 seconds**:

~~~text
Operation deadline: T0 + 2,000 ms

T0 + 000 ms : attempt #1 starts
T0 + 600 ms : attempt #1 times out
T0 + 700 ms : after backoff, attempt #2 starts
T0 + 1,300ms: attempt #2 times out
T0 + 1,450ms: 550 ms left; should attempt #3 start?
T0 + 2,000ms: client deadline
~~~

If the backend's normal p95 is around 700 ms, starting attempt #3 with only 550 ms remaining has very low odds of finishing. It likely adds load only for the result to be discarded.

### Pre-Retry Check Rule

Let \(D\) be the operation deadline, \(t\) the current time, \(b\) the required backoff wait, and \(a\) the budget reserved for the next attempt:

\[
\text{Only retry if } D-t > b+a
\]

In practice \(a\) can be a minimum per-attempt timeout or estimated duration with margin. If insufficient time remains, **fail/cancel cleanly** rather than firing a doomed call.

### Multi-Hop Timeouts Must Align

| Layer | Example Policy | Risk if Uncoordinated |
| --- | --- | --- |
| Browser/mobile | 2s total deadline | Gateway keeps working after client gave up |
| Ingress | 2.5s timeout | May sever connections mid-Gateway-retry |
| Gateway | 700 ms response timeout per attempt | Two retries + backoff can exceed client deadline |
| Orders | 500 ms timeout to Inventory | Orders retries can exceed how long Gateway waits |
| DB/SDK | Independent timeout | Can hold resources after parent request ended |

**No universal rule like "subtract 100 ms per lower hop" works for every system.** Network jitter, processing time, pool acquisition, TLS handshakes, and response streaming mean deadlines must be validated empirically. More importantly, **each layer should know remaining total time** and cancel work once results are no longer useful.

### Retry Timeout Does Not Equal Whole-Operation Timeout

In Spring Cloud Gateway Server WebFlux, `httpclient.connect-timeout` caps TCP connection setup; `httpclient.response-timeout` governs response waits per Reactor Netty/Gateway version semantics. With the `Retry` filter, multiple attempts can make total request duration **exceed one response timeout** due to backoff, pool acquisition, and other stages. If you need an overall deadline, design and test it separately.

## 9. Exponential Backoff and Jitter: Avoid Synchronized Surges

If 1,000 clients receive 503 and all retry **instantly**, the backend gets slammed with a second wave while already degraded. If all wait **exactly 1 second**, they create a synchronized "retry wave" every second.

**Exponential backoff** widens wait intervals after each failure, usually capped:

\[
b_k = \min(b_{\max}, b_0 \times q^{k-1})
\]

Where:

- \(b_0\): base wait duration, e.g., 100 ms.
- \(q\): growth factor, e.g., 2.
- \(b_{\max}\): maximum wait duration, e.g., 800 ms.
- \(k\): **retry** index; the initial call needs no backoff.

With \(b_0=100\text{ ms}\), \(q=2\), \(b_{\max}=800\text{ ms}\):

| Retry # | Backoff Before Next Attempt |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 800 ms, capped |

**Jitter** randomizes retry timing so clients do not return together:

~~~text
Without jitter: 100 ms, 200 ms, 400 ms, 800 ms...
With jitter:     74 ms, 167 ms, 309 ms, 612 ms...  (an illustrative sample)
~~~

A common strategy called **full jitter** picks a wait between 0 and the current backoff cap:

\[
b_k^{\text{jitter}} \sim U(0,\min(b_{\max},b_0q^{k-1}))
\]

In production, pick a jitter strategy matching desired behavior; if 0 ms waits are possible, budgets and concurrency limits are still needed to prevent immediate bursts during mass failures. Equal jitter or decorrelated jitter can also fit, but **never label something "exponential backoff" and assume jitter is included**.

### Do Not Outsmart `Retry-After`

When an upstream returns `429` or `503` with `Retry-After`, a supporting caller can wait accordingly while respecting its own deadline and budget. Never assume Gateway's Retry filter honors this header automatically; if policy requires it, implement and verify it at the chosen retry owner.

If `Retry-After` exceeds the operation deadline, **do not hold an HTTP request open waiting**; return an appropriate response so the client can try in a fresh operation. Never treat `Retry-After` as an order forcing retries regardless of limits.

## 10. Narrowly Scoped `Retry` GatewayFilter Factory Configuration

Gateway Server WebFlux example for **Catalog GET/HEAD**, never for payment APIs or write operations:

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
                - Method=GET,HEAD
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 1
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                      - GATEWAY_TIMEOUT
                    methods:
                      - GET
                      - HEAD
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 800ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

**Reading the configuration accurately:**

1. `Path=/api/catalog/**` and `Method=GET,HEAD` narrow retryable APIs right at the route predicate layer.
2. `uri: lb://catalog-service` requires Spring Cloud LoadBalancer and a valid `ServiceInstance` source; the real backend must serve the path after `StripPrefix=1`.
3. `retries: 1` permits **one retry beyond the initial call** when criteria match—an upper bound of **2 attempts** at the Gateway per inbound request.
4. `statuses` limits HTTP codes recognized by `Retry` GatewayFilter as retryable; **never blindly capture 4xx client errors**.
5. `methods` restricts retryable methods. On some versions, `exceptions` and `series` also apply; check defaults to avoid retrying unwanted exceptions.
6. `backoff` inserts bounded delays between attempts using supported properties.
7. This configuration **does not provide a fleet-wide retry budget, overall deadline, or jitter**. Those require separate controls and testing.

**Important compatibility note:** Older Spring Cloud Gateway WebFlux releases typically use `spring.cloud.gateway.routes`, whereas newer lines may use `spring.cloud.gateway.server.webflux.routes`. Starter names, `Duration` formats, filter ordering, and `backoff` properties can differ by release. Verify property binding and loaded routes on your target version; the YAML above is an **illustrative sample**, not a deployed configuration.

### Why Avoid "Retry All 5xx"?

A 500 can stem from a non-transient code bug; retrying only repeats the failure and adds load. A 503 may carry a long `Retry-After`. A 504 can indicate the backend **already executed a write while the response timed out**. Retry policies should come from **failure classification and API contracts**, not a blanket `SERVER_ERROR` label.

### Always Verify Filter Default Behavior

If `methods`, `statuses`, `series`, or `exceptions` are omitted, the Gateway may apply version-defined defaults. In documentation and production configs, **explicitly declare what should retry** and test what must not retry. Never rely on memory of an older release's defaults during upgrades.

## 11. Idempotency: Mandatory Prerequisite Before Replaying Writes

**Load amplification** is a performance problem; **retrying unsafe writes** is a data correctness problem. An HTTP call may have been processed by the backend even though the response vanished due to TCP reset, timeout, or client disconnect. The Gateway missing a response **never proves the backend did not commit the transaction**.

### Duplicate Order Creation Scenario

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orders service
    participant DB as Database
    C->>G: POST /api/orders
    G->>O: POST /orders (attempt 1)
    O->>DB: INSERT order O-100
    DB-->>O: COMMIT
    Note over O,G: Response lost / timeout
    G->>O: POST /orders (retry attempt 2)
    O->>DB: INSERT order O-101
    DB-->>O: COMMIT
    O-->>G: 201 Created (O-101)
    G-->>C: 201 Created (O-101)
~~~

In this failure mode, **one user action created two orders**. If multiple layers retry together, unintended transactions multiply rapidly.

### Safe Methods vs. Idempotent Operations

| Method | Typical HTTP Semantics | Safe to Blind-Retry? |
| --- | --- | --- |
| GET | Read; designed as safe and idempotent | Only when backend truly has no significant side effects and budget allows |
| HEAD | Read metadata, no response body | Similar conditions to GET |
| PUT | Semantically idempotent when expressing same desired state | Not by default; concurrency and version/ETag checks can matter |
| DELETE | Semantically idempotent in final effect, though responses may differ | Not by default; permissions and side effects like events/emails matter |
| POST | Not guaranteed idempotent | **No**, unless application enforces a deduplication contract |
| PATCH | Not guaranteed idempotent in general | **No**, unless the specific operation guarantees it |

**HTTP idempotency does not mean zero cost on repeat calls.** A GET can trigger expensive DB queries, cache fills, per-request billing, or misdesigned business logic. A DELETE can emit events per call if unguarded. Retries still require budgets, deadlines, and cost assessment.

### `Idempotency-Key` Must Actually Be Enforced in the Backend

A safer pattern for `POST /orders`:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <redacted-token>
Idempotency-Key: 9c8c0e2e-7e3f-4c10-a0fd-55b16f8d21f0
Content-Type: application/json

{"sku":"SKU-42","quantity":1}
~~~

The backend must:

1. Bind the key to **user/tenant, operation type, and payload fingerprint** so one key cannot apply to a different request.
2. Record operation state and outcome **atomically**, preventing two concurrent requests from both executing side effects.
3. For same key + valid matching payload, return the **stored outcome** without creating a new order.
4. For same key + different payload, return a contractual error instead of executing a new action.
5. Define TTLs, in-progress states, ambiguous failures, and recovery workflows.

Simply attaching `Idempotency-Key` at the Gateway **does not automatically make POST safe to retry**. Worse, if the Gateway mints a fresh key on each retry, deduplication breaks completely; the key must stay stable **for the same logical operation** and be validated where the transaction lives.

**Guidance when no idempotency contract exists:** Never enable Retry filters for payments, fund transfers, order creation, or harmful writes. When uncertain whether the backend committed, return an "unknown/pending" status per contract and offer status lookup via a reliable business identifier.

## 12. Request Bodies, Buffers, and Replay Costs in WebFlux

In **Spring Cloud Gateway Server WebFlux**, a request body can be a `Flux<DataBuffer>` stream. You cannot assume an already-read stream replays unless the publisher/body supports replay. To retry a body-bearing request, the Gateway may need to **cache the request body** or use Retry's version-specific body mechanism.

For a 2 MiB JSON POST retried twice, each retry:

- Must retain/replay exact bytes so upstream receives identical data.
- Can create heap/off-heap buffer pressure and extra GC.
- Can extend connection lifetimes and concurrency.
- Can strain client uploads if connections drop.

At 500 concurrent requests, simply holding **2 MiB per request** corresponds to roughly:

\[
500\times2\text{ MiB}=1,000\text{ MiB}\approx0.98\text{ GiB}
\]

This figure **illustrates a single cached body per request**, excluding object overhead, network buffers, TLS, responses, copies, or streaming. Actual memory depends on how bodies are cached, `DataBuffer` pooling, and request lifetimes.

### Cases Unsuitable for Blind Replay

| Body Type | Risk |
| --- | --- |
| Small JSON, bodyless GET/HEAD | Simplest; no body caching needed |
| JSON POST with side effects | Replay can duplicate operations even if byte caching succeeds |
| Multipart upload | Large body; replay consumes memory/disk and time |
| Streaming upload | Not necessarily replayable; full input isn't buffered upfront |
| gRPC or long-lived stream | Different semantics from short HTTP request/response |
| Body with tokens or PII | Caching/retrying/logging extends exposure lifetime of sensitive data |

With Netty-managed `DataBuffer`s, manually retaining/reusing buffers risks reference-count bugs or memory leaks. **Never build custom retries by calling `chain.filter(exchange)` multiple times without mastering request body replay and exchange state.**

### `Content-Length`, Headers, and Body Must Stay Consistent

If a filter alters the body between attempts while keeping a stale `Content-Length`, protocol errors occur. Attempts under retry must follow a consistent contract for method, URI, headers, and transmitted bytes. For compressed/encoded bodies, preserve `Content-Encoding` and actual bytes. Never log raw bodies just to verify retries; use a test stub returning safe checksums/byte counts when needed.

## 13. How Do Circuit Breakers, Rate Limiting, and Load Balancing Coordinate?

These three mechanisms complement each other rather than replacing one another:

~~~mermaid
flowchart TD
    C["Client"] --> A["Authentication / route selection"]
    A --> RL["Rate limiting / admission control"]
    RL --> RB["Retry policy + budget"]
    RB --> CB["Circuit breaker"]
    CB --> LB["Reactive load balancing: choose instance"]
    LB --> HTTP["HTTP client / connection pool"]
    HTTP --> U["Upstream"]
    CB -. "OPEN" .-> F["Fallback / fail fast"]
    RL -. "429" .-> C
    F --> C
~~~

This is a **responsibility diagram**, not a guarantee of exact filter order in every configuration. At runtime, `Retry`, `CircuitBreaker`, and `GlobalFilter`s are sorted by order; publisher wrapping determines how attempts, errors, and short-circuiting are counted.

### Retry Before or After Circuit Breaker?

Suppose one client HTTP request gets retried up to 3 attempts:

- **Breaker inside retry loop:** It can observe **each attempt** and increment failure counts multiple times for one user operation. Once OPEN, subsequent retries are rejected immediately.
- **Breaker outside retry loop:** It can observe the **combined outcome of the retried operation**; if all 3 attempts fail, the breaker may record one failure while the backend received 3 calls.

Both have trade-offs; neither order is "universally right" for every workload. Explicitly pick **what unit the breaker measures** (attempt vs. operation), and test upstream call counts and Resilience4j metrics. Never guess solely from two YAML filters sitting adjacent.

### Does the Load Balancer Always Pick a Different Instance on Retry?

**There is no default guarantee.** It depends on whether the retry re-enters load balancing, whether the supplier updates candidates, and whether a policy avoids recently failed instances. A retry might pick the **same instance** and fail again, or pick a healthy replica and add load there.

When an instance is genuinely unhealthy, fix **readiness probes, registry TTL/health, service discovery, and connection draining**. Never use retries as an infinite workaround for broken instances lingering in discovery.

### Does the Rate Limiter See Retry Attempts?

A `RequestRateLimiter` at Gateway ingress normally counts **inbound user HTTP requests** by key. When Retry GatewayFilter spawns extra upstream attempts **after** the rate limiter, those attempts may bypass inbound quota. Conversely, when a client retries by sending fresh HTTP requests, each hits the rate limiter.

Therefore, maintain **separate outbound attempt metrics/budgets** instead of assuming a 1,000 inbound requests/s limit caps backend calls at 1,000 calls/s.

### Bulkheads and Connection Pools

Even with bounded retries per request, a traffic spike can launch thousands of concurrent operations. **Bulkheads**, concurrency caps, connection pools, and pending queues protect resources. Circuit breakers do not replace bulkheads; retries do not automatically respect upstream socket limits unless capacity-aware.

A safer policy flow:

~~~text
Admit request by quota
  -> Check deadline and retry budget
  -> Retry only permitted failures
  -> Backoff with jitter
  -> Stay within concurrency / pool capacity
  -> Stop when circuit is OPEN or budget is exhausted
~~~

### Fallbacks Must Not Trigger Unbounded New Retry Chains

If Gateway's `CircuitBreaker` forwards to a fallback handler that calls service B (which also retries multiple times), attempts are merely shifted onto another dependency. **Fallbacks need their own budgets, timeouts, auth, and load-shedding policies.** Never return 200 with stale/wrong data just to mask an outage.

## 14. After Response Commit, You Cannot "Retry From Scratch"

For short JSON GETs, errors before the Gateway writes status/body can sometimes be retried cleanly. For **SSE**, NDJSON, large file downloads, or WebSockets, part of the response may already have been flushed:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

event: progress
data: 20

<upstream connection interrupted>
~~~

Once status and headers commit:

- Gateway cannot rewind and change 200 to 503 on **the same HTTP response**.
- Replaying the whole stream can send **duplicate events** or records to the client.
- An automatic filter retry attempting to write to an already-committed response causes framing/protocol errors.
- Clients generally need **reconnect** and resume mechanisms via event IDs/checkpoints if supported by contract.

**Never assume `Retry GatewayFilter` delivers exactly-once streaming.** Test pre-stream and mid-stream failures separately and avoid unconditional replay policies. WebSockets use an upgraded bidirectional connection rather than short request/response cycles, so short-HTTP retry policies do not apply.

### Client Cancellation Does Not Automatically Undo Side Effects

When a client disconnects or its deadline expires, Reactor propagates cancellation to publishers. However, the backend may already have received the request and committed data; cancellation never proves "the operation did not happen." Propagate deadlines/cancellation deliberately to supporting layers, stop scheduling new retries once the client disconnects, and rely on **idempotency/status lookup** for writes.

## 15. Security, Tokens, and Outbound Attempts

Each retry dispatches a fresh outbound HTTP request to upstream (when actually executed). That implies:

- `Authorization` headers may be sent again.
- `Cookie`, API keys, and trace headers may be copied across attempts.
- Updated discovery or routing might direct a later attempt to a different target.
- Per-attempt logging can expose the same token repeatedly if wiretap/header dumps are enabled.

**Never weaken authentication/authorization for retries.** A `401/403` response must not be retried as a dependency error, and fallbacks must never turn authorization failures into 200s. If backends require audience-specific tokens, retrying onto another service must never blindly carry the previous service's token.

When combining `Retry` and `TokenRelay`, verify **every attempt only targets trusted destinations** with a token still valid for that scope/audience. Never substitute a shared admin token to "make retries succeed" in place of user credentials.

For logging:

~~~text
DO:
  route=catalog-read
  attempt=2
  outcome=connect_timeout
  upstreamService=catalog-service

DON'T:
  Authorization=Bearer eyJ...
  Cookie=SESSION=...
  url.full=/api/orders?access_token=...
~~~

Log only non-sensitive metadata: route ID, attempt index, normalized status/error category, latency, controlled request/trace IDs, and circuit state. Never dump whole exchanges/bodies on retry failures.

## 16. Proper Observability: Measure Operations, Inbound Requests, and Outbound Attempts

Looking only at `HTTP 503/s` at the Gateway hides:

- How many times did clients retry on their own?
- How many retries did the Gateway add?
- How many more times did Orders/SDKs retry?
- Was a 200 response actually the third attempt?
- Was Gateway's `CircuitBreaker` OPEN (skipping backend calls), or was the backend called and returning 503?
- Is a 200 fallback masking degraded dependencies?

To tell these apart, maintain **at least three observation layers**:

| Measurement Layer | Meaning | Safe Label Examples |
| --- | --- | --- |
| **User operation / logical request** | One initiated business action | Operation type, tenant tier if appropriate—never tokens |
| **Inbound Gateway request** | Each HTTP request entering Gateway | Route ID, method, final status |
| **Outbound upstream attempt** | Each actual Gateway/SDK call to a dependency | Service ID, attempt index, outcome |

Where fan-out exists, tag by dependency/operation so two parallel calls are not mistaken for a retry. Across multiple Gateway replicas, aggregate metrics cleanly by instance and window.

### Key Metrics

| Conceptual Metric | Usage |
| --- | --- |
| Original request rate | Baseline traffic at the relevant boundary |
| Retry attempt rate | Additional call volume from retries |
| Retry ratio | Retries / original requests or admitted operations (always state denominator) |
| Outbound attempts by route/service | Pinpoints dependencies suffering amplified load |
| Attempt outcome by status/exception | Reveals which errors trigger policies |
| Backoff wait histogram | Detects synchronized retry waves |
| Retry budget remaining / exhausted | Shows when policy actively sheds retry load |
| Deadline exceeded / client cancelled | Catches retries happening too late or uselessly |
| Circuit breaker state / call-not-permitted | Separates fail-fast from backend errors |
| Rate limiter rejections | Measures admission-layer blocks |
| Reactor Netty active/idle/pending connections | Exposes connection pressure from attempts |
| Upstream p95/p99 latency | Checks whether retries help or hurt performance |
| Idempotency replay/deduplication counts | Tracks resent writes intercepted cleanly |

Names in this table are **conceptual metrics**, not guaranteed built-in Micrometer meter names in every release. Spring Cloud Gateway, Reactor Netty, Resilience4j, Micrometer/Actuator, and OpenTelemetry expose parts of this telemetry when enabled; verify exact meter/tag names and cardinality costs in your live environment.

### Correlating Attempts Without Using Tokens as IDs

A trusted `operationId` helps correlate attempts for the **same logical operation**, and `attemptIndex` identifies which try occurred. Still:

1. Never use `Authorization` or session cookies as correlation IDs.
2. Never put user IDs, raw URL queries, or unbounded operation IDs into **metric labels**.
3. If accepting a correlation ID from clients, validate length, format, and trust before forwarding or logging.
4. Never trust a client-supplied `X-Attempt` header to grant extra budget or bypass rate limits.
5. In tracing, use child spans per attempt while keeping full JWTs, cookies, queries, and bodies out of span attributes/baggage.

### Sample Metrics Reading

~~~text
Window: 60 seconds, route=catalog-read
Inbound HTTP requests            : 10,000
Outbound calls to catalog        : 13,000
Additional upstream attempts     :  3,000
Gateway-level amplification      :  1.30x
Retry budget exhausted operations:    800
Circuit denied attempts          :    600
~~~

These are **illustrative numbers**, assuming each valid inbound request has one intended Catalog call with no fan-out, cache short-circuits, or secondary routes. When circuit-rejected calls are significant, "additional attempts = outbound − inbound" is **no longer an accurate retry count**; instrument the retry filter directly and separate `attempt_started` from `attempt_rejected`.

## 17. Java Example When the Service Owns Retries: Always Pick One Owner

If your organization decides **Orders service** will retry its own `WebClient` GET calls to Inventory, the matching Gateway route **should not also enable Retry** for the same failure by default. Illustrative Java example of a narrow policy:

~~~java
import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class InventoryClient {
    private final WebClient client;

    public InventoryClient(WebClient client) {
        this.client = client;
    }

    public Mono<String> getStock(String sku) {
        return client.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class)
                .retryWhen(
                        Retry.backoff(1, Duration.ofMillis(100))
                                .maxBackoff(Duration.ofMillis(800))
                                .jitter(0.5)
                                .filter(this::isRetryable)
                );
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException responseError) {
            HttpStatus status =
                    HttpStatus.resolve(responseError.getStatusCode().value());
            return status == HttpStatus.BAD_GATEWAY
                    || status == HttpStatus.SERVICE_UNAVAILABLE
                    || status == HttpStatus.GATEWAY_TIMEOUT;
        }
        // Do not assume every exception is retryable.
        return false;
    }
}
~~~

Explanation:

- `Retry.backoff(1, ...)` permits **one retry beyond the initial attempt** when the error passes the filter.
- `.jitter(0.5)` adds random variance to wait intervals in Reactor Retry; this **differs** from `Retry` GatewayFilter's `backoff` YAML properties.
- `.filter(this::isRetryable)` intentionally retries only selected statuses; this sample **does not retry connection resets or timeouts**. Supporting those requires explicit classification and testing—never write `Throwable -> true`.
- `bodyToMono(String.class)` only fits small text payloads. Binary, streaming, or large responses need different body contracts.
- This snippet **lacks an overall deadline, shared retry budget, circuit breaker, and telemetry**, so it is **not a complete production solution**. It illustrates attaching a selective policy at **one layer**, not enabling retries at both Gateway and service.

### Note the Difference Between Statuses and Exceptions

In `WebClient.retrieve()`, HTTP 4xx/5xx responses are typically mapped to `WebClientResponseException` when reading bodies as shown. In the Gateway, an HTTP 503 can be inspected directly as a status by `Retry` GatewayFilter depending on factory/version. Thus Reactor `retryWhen` code cannot simply be copy-pasted as a GatewayFilter equivalent: understand **what each layer's publisher sees**.

### Adding an Overall Deadline

A production version must track remaining time before each attempt, combining HTTP client timeouts and stop conditions. Never slap `.timeout(Duration.ofSeconds(2))` in a random spot assuming timers, queues, and cancellation all align. Operator placement limits either **the whole publisher** or **each attempt**, and ordering relative to `retryWhen` dictates total elapsed time; always test it.

## 18. Backend Stub to Count Attempts Instead of Guessing

To test Gateway policies, use a **mock backend in a test environment** scripted to return 503 for a set number of calls and then 200. This verifies the Gateway truly stops at the configured attempt count.

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogStubController {

    private final AtomicInteger calls = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> getItem(
            @PathVariable String id) {

        int attempt = calls.incrementAndGet();

        if (attempt <= 1) {
            return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of(
                            "code", "SIMULATED_TEMPORARY_FAILURE",
                            "attempt", attempt)));
        }

        return Mono.just(ResponseEntity.ok(Map.of(
                "itemId", id,
                "attempt", attempt,
                "name", "Test item")));
    }

    int callCount() {
        return calls.get();
    }

    void resetCounter() {
        calls.set(0);
    }
}
~~~

This is a **single-process stub** purely for illustration/testing. Under concurrent requests, counters interleave and per-request outcomes become unpredictable. For reliable integration tests, run **sequentially or isolate each test**, reset counters, and never expose `resetCounter()` publicly. Here the backend expects `GET /catalog/items/{id}`, matching Section 10's `StripPrefix=1` route.

### Expected Behavior With `retries: 1`

Starting with counter at 0 and one single request:

1. Attempt #1: `GET /catalog/items/42` → stub returns 503.
2. `Retry` recognizes 503 and, if budget/conditions permit, waits backoff.
3. Attempt #2: stub returns 200 with `attempt: 2`.
4. Gateway returns 200 and stub counter equals **2**.

With `retries: 0`, Gateway skips this filter's retry; the first request gets 503 and counter equals **1**. If the stub always returns 503 while `retries: 1`, max counter is **2**, not 3, provided requests reach upstream and no other layer retries.

**Key test check:** If the client sends a new HTTP request itself, the counter keeps rising. Distinguish "one inbound HTTP request retried by Gateway" from "two independent inbound requests sent by the client."

## 19. From `WebTestClient` to a Fault-Tolerance Test Matrix

An HTTP test checks final output, yet must be paired with a **backend counter** to verify actual call volume:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class CatalogGatewayRetryHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void getCanRecoverAfterOneTransientFailure() {
        // Before test: reset stub counter and ensure no concurrent traffic.
        client.get()
                .uri("/api/catalog/items/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.attempt").isEqualTo(2);
    }
}
~~~

This is an **illustrative integration test snippet**, not executed in this environment. Complete tests need JUnit/Spring Test, Gateway on port 8080, properly routed stub, counter resets before tests, and an independent assertion on the stub verifying `callCount() == 2`. Never rely solely on the response's `attempt` field if backends run concurrently or across multiple instances.

### Essential Test Matrix

| Scenario | Setup / Fault | Expected |
| --- | --- | --- |
| A. GET succeeds immediately | Stub returns 200 | 1 outbound attempt, no retry |
| B. GET transient error | Stub returns 503 then 200 | 2 attempts with `retries: 1` |
| C. GET always fails | Stub always returns 503 | Max 2 attempts; final error per contract |
| D. GET returns 400/401/403/404 | Outside retry `statuses` | No extra attempts from those statuses |
| E. GET returns 429 and `Retry-After` | 429 not configured for retry | No immediate retry; policy preserved |
| F. POST/payment | Route lacks Retry or method excluded | Never replays body or side effects |
| G. Response timeout | Stub delays past deadline | Retries only if exception is allowed and budget remains |
| H. Circuit breaker OPEN | Breaker rejects upstream | Zero backend HTTP attempts while rejected |
| I. Client cancellation | Client closes before result | No new retries spawned after cancel; verify cancellation |
| J. Retry budget exhausted | Test quota/budget depleted | Stops retrying; preserves controlled error behavior |
| K. Two retry layers enabled | Client and Gateway both retry | Measure multiplication, then fix to single owner |
| L. Multiple Gateway replicas | Controlled load/tests | Cluster-wide budget stays within committed limit |
| M. Partial SSE stream | Stub sends partial events then resets | Never replays into committed response |
| N. Large body | Lab POST upload test | No off-policy/out-of-budget caching or replay |
| O. Unexpected redirect target | Upstream redirects to untrusted host | Never forwards credentials or retries off-allowlist hosts |

Never use a degraded production backend as a "load experiment"; run bounded stubs/fault injection in safe environments. When testing multi-layer retries, cap traffic so you do not cause an outage yourself.

### Verifying `Retry` GatewayFilter Actually Executed

If a route's `Path` predicate never matches, its filters never run. When seeing GET 503, verify step by step:

1. Did the route match?
2. Was the Retry filter initialized properly?
3. Did the status/exception match policy?
4. Did deadlines and budgets allow retrying?
5. Did another filter commit the response, alter the status, or short-circuit earlier?
6. Is the request body safely replayable?
7. Did the upstream counter increment the expected number of times?

Checking every step avoids knee-jerk mistakes like raising `retries` from 1 to 5 when the request never matched the route or the error originated elsewhere.

## 20. Runbook: When Retry Amplification Is Worsening an Outage

Suppose alerts show p99 latency spiking, frequent 503s, and backend CPU/DB queues near saturation, while HTTP client logs show heavy retries. **Do not increase retry counts to "improve resilience" before quantifying generated load.**

### Step 1 — Identify the Source and Impacted Dependency

Collect over the same time window:

- Client/user operation rate if measurable.
- Inbound Gateway requests per route.
- Outbound attempts per service and failure type.
- Retry attempts in SDKs, service mesh, ingress, and clients where visible.
- Rate limiter rejections, circuit breaker states, connection pool pending queues, backend p95/p99.
- Active Gateway replica count and which instances discovery is returning.

Distinguish causes: missing backend instances, TLS failures, connect timeouts, response timeouts, 429 quota rejections, 503 overload, or slow DBs. **Not every 503 is the same incident.**

### Step 2 — Estimate Amplification

Given aligned telemetry where one route call maps to one backend call:

~~~text
Inbound Gateway requests / second     = 900
Outbound attempts / second           = 2,250
Attempts per inbound ratio           = 2.5x
Extra attempt rate                   = 1,350 attempts/s
~~~

This is a hypothetical example. If the frontend also auto-retries 3 times, original logical operations may be far below 900 inbound requests/s; frontend metrics or operation-level tracing are needed to gauge total induced load.

### Step 3 — Reduce Amplification Controlledly

Situational actions:

1. **Temporarily dial down or disable retries at a layer** multiplying attempts without improving success rates, following change control.
2. **Tighten retry budgets** or quotas, prioritizing fresh initial requests.
3. **Add or tune backoff and jitter** at the retry-owning layer to break herd synchronization.
4. **Cap concurrency and pending queues** to stop piling connections onto backends.
5. **Use circuit breakers** to cut calls to degraded dependencies, with fallbacks honoring status contracts.
6. **Apply deliberate load shedding/rate limiting** when capacity falls below incoming demand.
7. For single unhealthy instances, **fix readiness/health/discovery** so they drop out of rotation instead of letting retries hunt indefinitely.

Across multi-replica fleets, changing budgets on one replica is insufficient; update the entire fleet. Disabling retries may dip short-term success slightly while **relieving backend pressure**, allowing recovery—watch both signals rather than 200 counts alone.

### Step 4 — Fix the Underlying Cause

Retry amplification is usually both a **symptom and an accelerant**, not the original root cause. Investigate backend CPU, GC, DB connection pools, slow queries, DNS, TLS, file descriptor limits, thread/event-loop blocking, network policies, and rolling deployments.

Never weaken TLS validation or bypass authentication just to make retries succeed. When a dependency faces a prolonged outage, return clear contractual errors, supply `Retry-After` where justified, or use queues/outbox/deferred processing **if business semantics truly support it**.

### Step 5 — Confirm Recovery and Prevent Recurrence

1. Backend latency and error rates return to acceptable thresholds.
2. Attempts-to-inbound ratio returns to expected levels.
3. Retry budgets stop depleting continuously, and circuit breakers stop flapping OPEN/CLOSED.
4. Inbound rates are no longer inflated by client auto-retries.
5. Zero attempts occur past deadlines or cancellations.
6. Duplicate operations remain blocked by backend idempotency.
7. Run safe fault injection against the updated policy and document findings in the runbook.

Never declare the system healthy just because one Gateway replica sees HTTP 200 again; inspect the whole cluster and deepest dependencies.

## 21. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Fix |
| --- | --- | --- |
| Client, CDN, Gateway, service, and SDK all enable default retries | Attempts multiply across layers | Designate retry owners and shared total budgets |
| Mistaking `retries: 3` for 3 total attempts | Higher call volume than planned | Count initial attempt + retries per filter semantics |
| Retrying all 5xx blindly | Repeats code bugs or prolonged backend outages | Select verified transient statuses/exceptions |
| Retrying immediately on 429 with long `Retry-After` | Worsens quota/throttling pressure | Honor wait signals, deadlines, and backpressure |
| Fixed backoff without jitter across thousands of clients | Synchronized retry waves | Add jitter at the supporting retry owner |
| Retrying past client deadlines | Generates load with zero user benefit | Check remaining deadline before each retry |
| Raising pool max connections to absorb endless attempts | Exhausts sockets/CPU/DB and pushes load downstream | Bound concurrency, budgets, and fix root errors |
| Retrying POST/Payment without idempotency | Double charges/duplicate orders | Atomic backend deduplication; no blind retries |
| Unconditionally replaying multipart/streaming bodies | Buffer bloat, unreplayable bodies | Do not retry, or use resumable uploads |
| Trusting client `X-Attempt` header as reliable quota | Clients can inflate their own budget | Use authenticated sources; validate/clamp values |
| Calling `chain.filter(exchange)` twice manually in a custom filter | Duplicates side effects, breaks Reactive lifecycle | Use supported factories/operators and return Publisher |
| Retrying after HTTP response commit | Cannot reset status/body; corrupts/duplicates data | Application-level reconnect/resume |
| Seeing 503 and assuming retries always switch instances | May hit same instance or whole service may be down | Check discovery, routing, and policy |
| Enabling breaker and Retry without verifying filter order | Wrong breaker sampling, retry storms | Test attempt counts, state transitions, and precedence |
| Measuring only client-facing 200/503 | Hides how hard backends are being hit | Measure inbound requests, outbound attempts, and retries separately |
| Putting tokens/raw URLs in trace/metric labels | Secret leaks, cardinality explosion | Metadata allowlists and safe trace IDs |
| Fallbacks calling another service with unbounded retries | Shifts outage onto another dependency | Enforce budgets and timeouts on fallbacks too |
| Setting tiny breaker failure thresholds to shed load | False OPENS blocking healthy traffic | Tune against SLOs, sample counts, and real errors |

### Retry vs. Hedging

**Hedged requests** dispatch multiple **parallel** or slightly staggered calls across replicas to cut tail latency. Unlike sequential post-failure retries, hedging proactively **multiplies load** and can trigger side effects if unguarded. If SDKs/meshes use hedging, count those calls in the **same outbound budget** and restrict them to safe operations. Never assume "zero retries" means a system sends only one call per operation.

### Retry vs. Manual Resubmission

When a UI displays a timeout, a user clicks "Pay" again. That is a **new UI-layer user action**, not a Gateway Retry filter, yet **it may represent the same business intent**. Backend idempotency and transaction state checks must cover both, especially when the first attempt committed while the response was lost.

## 22. Hands-On Exercise: Reducing Attempts While Preserving Resilience

**Scenario:** Spring Cloud Gateway proxies `GET /api/catalog/items/{id}` to Catalog service via `lb://catalog-service`. Client, Gateway, and Catalog SDK all support retries. When Catalog returns 503, call volume spikes and p99 latency degrades.

### Part A — Draw the Call Graph and Compute Upper Bounds

1. List layers: client → ingress → Gateway → Catalog → Inventory.
2. Write **max attempts** per layer, not just `retries` names.
3. Suppose client has 3 attempts, Gateway 3 attempts, Catalog SDK 2 attempts. Compute:

\[
A_{\max}=3\times3\times2=18
\]

4. If one user operation also fans out to Pricing, compute calls to Pricing and Inventory **separately** to avoid mis-multiplying.
5. Note when circuit breakers, deadlines, or cancellations keep actual attempts below the upper bound.

### Part B — Choose the Primary Retry Owner and Configure

1. Designate **Gateway** as retry owner **for Catalog GET/HEAD only**, or designate the client and disable Retry GatewayFilter. Document your rationale.
2. If choosing Gateway, set `Retry` with `retries: 1`, statuses 502/503/504, and bounded backoff.
3. Disable retries for the same errors at remaining layers or reduce budgets, proving attempts no longer multiply unexpectedly.
4. Define an operation deadline and per-attempt timeout; verify total time including backoff.
5. Define per-route and cluster-wide retry budgets/caps in the production design.
6. Never add POST retries for Payments; rely on idempotency contracts and status lookups if needed.

### Part C — Test With a Request-Counting Stub

1. Run a backend stub like Section 18 returning 503 first, then 200.
2. Send one GET through Gateway; assert backend receives **at most 2 attempts** and final response matches expected JSON.
3. Configure stub to always return 503; verify attempts stop at the limit without growing endlessly.
4. Configure stub to return 400/401/403/404; verify **no retries** since statuses are excluded.
5. Send a controlled short burst; measure retries/request and pending connections without touching production.
6. Temporarily enable client retries in the lab to observe amplification, then turn them back off and compare.
7. Test circuit OPEN: outbound HTTP attempts must drop while fallback matches contract.

### Part D — Load Testing and Business Safety

1. Compare **success rate, p95/p99 latency, backend QPS, retry attempts, and error rate** before and after.
2. Verify retry budgets hold across multiple Gateway replicas.
3. For a mock write operation, simulate backend commit followed by lost response; use idempotency keys to ensure zero duplicate records.
4. For large bodies, watch memory/pooled buffers; never retry uploads lacking replay support.
5. For SSE, drop mid-stream after a few events and verify no stream replay occurs into a committed response.
6. Record behavior on `Retry-After` and expired client deadlines.
7. Audit logs/traces to confirm zero tokens, cookies, or sensitive query URLs across every attempt.

### Lab Results Table to Submit

| Case | Inbound HTTP Requests | Outbound Attempts | Final Status | Notes |
| --- | ---: | ---: | --- | --- |
| Immediate 200 | 1 | 1 | 200 | No retry |
| 503 then 200, Gateway `retries: 1` | 1 | 2 | 200 | One retry allowed |
| Continuous 503, Gateway `retries: 1` | 1 | 2 | 503/fallback per policy | Stopped at limit |
| 400 from backend | 1 | 1 | 400 | No retry |
| 401/403 from auth layer | 1 | 0 (if blocked pre-proxy) | 401/403 | Auth preserved |
| Client 2 attempts, Gateway 2 attempts | 2 | Up to 4 | Per backend | 4× amplification vs. 1 operation |
| Circuit OPEN | 1 | 0 on blocked branch | Fallback | Fail fast |

**Results in this table are logical expectations in a controlled setup**, not actual executed test output. If routes include extra filters, load balancing, caching, or auth, adjust preconditions and count attempts via backend counters.

**Passing criteria:** You can explain amplification sources, establish a single-owner retry policy, bound attempts and overall deadlines, separate GET from side-effecting POSTs, prove via metrics/stubs that attempts stay within budget, keep credentials out of logs, and maintain a runbook for backend degradation.

## 23. Key Takeaways

- **Retries help with transient errors yet turn dangerous when stacked across layers.** The upper bound on nested attempts grows as a product \(\prod_i(1+r_i)\), not a sum.
- **Distinguish retries from attempts.** In `Retry` GatewayFilter, `retries` normally counts **additional tries after the initial call**; verify semantics on your running version.
- **Assign retry ownership per dependency/operation.** Avoid letting client, ingress, Gateway, and SDK each independently retry the same failure without a shared budget.
- **Budgets, deadlines, backoff, and jitter belong together.** Backoff does not imply jitter by default; retrying past deadlines adds load with little value.
- **Retry only permitted errors and suitable methods.** Never retry 400/401/403/404 by default; 429/503 may carry `Retry-After`; POST/payments require genuine backend idempotency.
- **Request body replay in WebFlux carries memory cost**, especially for multipart/uploads/streams. Never manually call `chain.filter(exchange)` multiple times or mishandle `DataBuffer` lifecycles.
- **Retry, CircuitBreaker, RequestRateLimiter, LoadBalancer, and connection pools serve distinct roles.** Filter ordering affects attempts and failure accounting; verify with stubs and metrics.
- **Once a response commits, you cannot retry the same response from scratch.** For SSE/WebSockets, use contractual reconnect/resume mechanisms.
- **Measure outbound attempts and retry ratios alongside inbound requests**, combining safe tracing, circuit state, and backend metrics to spot real amplification.

A resilient **Spring Cloud Gateway** system is not the one that retries the most—it is the one that **retries the right failures, at the right layer, within a finite budget, and stops in time before pushing dependencies into overload**.
