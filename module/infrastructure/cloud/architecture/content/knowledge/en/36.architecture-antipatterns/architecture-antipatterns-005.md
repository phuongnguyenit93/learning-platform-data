# Unbounded retries, inconsistent timeouts, and cascading failures

## 1. Context: how a minor fault becomes a system-wide outage

A cloud application typically consists of multiple components calling one another: an API Gateway routes requests to a business service; that service calls a database, cache, payment system, and one or more external APIs. Networks are not 100% reliable: connections drop, dependencies overload, queries run unusually slow, or an instance restarts.

**Retries** and **timeouts** are essential tools for surviving transient faults. However, when implemented without a shared policy, those very tools amplify incidents:

- **Unbounded retries:** a failed request is retried continuously without considering deadlines, attempt caps, or downstream service health.
- **Inconsistent timeouts:** each layer configures timeouts independently, some layers omit timeouts altogether, or the cumulative time spent on sub-calls exceeds the user's request deadline.
- **Cascading failures (*cascading failure*):** one slow or failing component exhausts resources in healthy callers, overloading them and taking them down one after another.

Within the **Architecture Antipatterns** chapter of **CLOUD_ARCHITECTURE**, this lesson shows how to identify these three issues, explain how they interact, and design alternatives starting from **business requirements** through **networking, compute, data, and deployment models**. Choices must balance reliability, security, scalability, cost, and operations using **Well-Architected** thinking.

**Lesson objectives:** explain why retries cause traffic storms; set timeouts from an end-to-end time budget; distinguish retryable from non-retryable errors; combine backoff, jitter, circuit breakers, concurrency limits, and controlled degradation; and read metrics to detect and contain cascading failures.

> **Core idea:** Retrying helps only when the fault cause is likely transient, another attempt has a real chance of succeeding, and the system has enough **time and resources** for that attempt. When those conditions do not hold, continuing to retry usually worsens the incident.

## 2. Running example: an order-placement service

Suppose an e-commerce platform has the following synchronous processing chain:

~~~mermaid
flowchart LR
    C["Client App"] --> G["API Gateway"]
    G --> O["Order API"]
    O --> I["Inventory Service"]
    O --> P["Payment Service"]
    P --> B[("Payment Provider")]
    O --> D[("Order Database")]
    I --> R[("Inventory Database")]
~~~

Hypothetical business requirements:

| Requirement | Illustrative target | Design implication |
|---|---|---|
| User experience | Submit an order and receive a response within at most 2 seconds in most cases | Enforce an **end-to-end deadline**; limit what work sits on the synchronous path |
| Correctness | Never create two orders or charge twice | Idempotency keys, business state machines, handling ambiguous outcomes |
| Reliability | Brief network blips do not break every transaction | Conditional retries with attempt and total-time caps |
| When external services fail | Users can still view their cart and order history | Resource isolation, controlled error responses, graceful degradation |
| Operations | Detect issues before thread/connection pools exhaust | Per-hop metrics, tracing, alerts, and load limits |

These are **exercise assumptions**, not universal SLOs for every service. Payments carry side effects and far stricter business accuracy needs than reading a product catalog; retry policies must differ accordingly.

## 3. What do unbounded retries break?

### 3.1. The load-amplification mechanism

When the payment service overloads, latency rises and timeouts appear. If the Order API immediately retries every failed request, the Payment Service receives new traffic **plus** retry traffic. Concurrent waiting requests hold connections, memory, and worker threads; the payment service must handle more work at the exact moment it has less capacity.

At a baseline rate of **100 requests/second**, if each request produces **up to three total attempts** and every attempt fails, downstream can receive **300 attempts/second** before counting retries at other layers. If the Gateway also retries three times for every Order API call, one edge request can turn into **9 attempts** at the Payment Service. If another layer also retries three times, the extreme case reaches **27 attempts**. This is the theoretical multiplier when every failure branch triggers retries, not a fixed load factor in every system.

~~~mermaid
flowchart TB
    A["1 user request"] --> G1["Gateway: attempt 1"]
    A --> G2["Gateway: attempt 2"]
    A --> G3["Gateway: attempt 3"]
    G1 --> O1["Order API: 3 calls"]
    G2 --> O2["Order API: 3 calls"]
    G3 --> O3["Order API: 3 calls"]
    O1 --> P["Payment: up to 9 calls"]
    O2 --> P
    O3 --> P
~~~

This diagram assumes each Gateway attempt triggers three Order API attempts; retry sequences run one after another, not necessarily in parallel. When a service is slow rather than failing fast, the original request may have expired while downstream retries keep running.

### 3.2. Why immediate retries are dangerous

After a brief glitch, thousands of clients retrying at the exact same instant cause a **thundering herd**: traffic spikes in waves. Retrying **with zero delay** or identical fixed delays synchronizes retry waves, creating load oscillations and preventing the service from recovering.

Continuous retries can also cause:

- **Retry storms:** retry volume vastly outnumbers fresh business requests.
- **Long-held resources:** threads, goroutines, connection pools, memory, and queues grow with the count of in-flight requests.
- **Duplicate or corrupted data:** re-executing non-idempotent operations like order creation or payment capture can create a second side effect.
- **Rising costs:** extra calls to paid APIs, queries, logs, compute, and cross-zone/cross-region transfer.
- **Masking root causes:** top-level metrics report only “succeeded after retry” even while downstream systems are unstable.

**Clear antipattern signs:** infinite retry loops, no time cap, no attempt cap, no backoff, or retrying authentication, invalid-input, and business-logic errors as if they were transient infrastructure faults.

## 4. Inconsistent timeouts: expired outside, still running inside

### 4.1. Distinguishing timeout types

| Mechanism | What it bounds | Example risk if missing |
|---|---|---|
| **Connect timeout** | Time to establish a network connection | Connecting to a broken destination holds sockets too long |
| **TLS handshake timeout** | Time for TLS handshake, if supported separately by the client | Requests stall during secure connection setup |
| **Read/response timeout** | Time waiting for data/response, depending on SDK semantics | Connected, yet the server sends no data |
| **Per-attempt timeout** | Maximum duration for **one** attempt | One slow attempt burns all time the user is willing to wait |
| **Overall timeout / deadline** | Time limit for **total** work, including retries/backoff | Sequential attempts far exceed the end-to-end SLO |
| **Queue/worker timeout** | Wait and execution time for background processing | Jobs linger indefinitely, clogging workers or queues |

Some HTTP clients define *socket timeout* as **the idle gap between reads**, not the total time to receive the full response. Never assume any setting named “timeout” protects the entire path. Verify the exact semantics of your HTTP client, SDK, proxy, gateway, and service mesh.

### 4.2. Example deadline conflict

Suppose:

~~~text
Gateway timeout                     = 2.0 seconds
Order API timeout calling Payment   = 3.0 seconds / attempt
Payment SDK retries                 = 3 attempts
Backoff intervals                   = 0.2 seconds then 0.4 seconds
Maximum time on Payment side        = 3 + 0.2 + 3 + 0.4 + 3 = 9.6 seconds
~~~

The Gateway stopped waiting at second 2, yet Order API may stay busy processing Payment for nearly 10 seconds if it does not receive and honor cancellation signals. The user sees an error and clicks submit again; the system may end up processing both the old and new requests concurrently.

**Core fix:** assign an **absolute deadline to each request at the system edge**, then propagate the remaining time budget down through layers. Each layer subtracts elapsed time; downstream call timeouts must be **less than or equal to the remaining budget**, leaving room for business logic and response serialization. Once the deadline expires, never start a new attempt.

An illustrative calculation:

~~~text
request deadline = arrival time + 2,000 ms
time spent on auth/DB = 350 ms
remaining budget = 1,650 ms
reserve 150 ms to aggregate results and return response
maximum budget for Payment = 1,500 ms, including retries and backoff
~~~

There is no universal “magic number”: budgets must be grounded in SLOs, high-percentile dependency latencies, variance, and business needs. Host clocks can drift; when propagating an **absolute deadline** over the network, account for clock skew, while internal code should use a **monotonic clock** (*monotonic clock*) for durations where supported by the runtime.

### 4.3. A timeout does not automatically cancel downstream work

The client stopping its wait does not mean the server stopped computing or rolled back its transaction. To curb wasted resources:

1. Propagate **cancellation/deadline context** across APIs and libraries that support it.
2. On the backend, stop work that is no longer needed and release connections, threads, memory, and locks.
3. Distinguish **cancellable work** from side effects that must not halt mid-flight, such as an already submitted payment instruction.
4. For uncertain outcomes, **query status via request/idempotency key** or run reconciliation before issuing a new operation.

A timeout after sending a payment instruction is an **unknown outcome**, never proof that “the payment did not happen.” Retrying operations with side effects requires idempotency enforced by **the receiver**, not merely generating a key on the caller.

## 5. How cascading failures unfold

~~~mermaid
flowchart TD
    A["Payment Provider slows down"] --> B["Payment Service holds many requests"]
    B --> C["Connection / thread pools fill up"]
    C --> D["New requests queue up"]
    D --> E["Latency and timeouts rise"]
    E --> F["Client, Gateway, Order API retry"]
    F --> G["Attempt rate to Payment climbs"]
    G --> B
    C --> H["Order API lacks workers for other requests"]
    H --> I["Unrelated features also slow down / fail"]
~~~

A **positive feedback loop** spreads failure from one dependency to its callers. Unbounded queues can delay overload signals, yet add zero processing capacity. Autoscaling cannot rescue the system immediately if load rises faster than instances boot, or if a shared dependency like the database remains the bottleneck.

### Minimalist quantitative model

By Little's Law, under steady-state conditions:

\[
L = \lambda W
\]

Where **L** is the average number of requests in the system, **λ** is the average throughput, and **W** is the average time a request spends in the system. Suppose at 200 requests/second, wait time climbs from 0.1 seconds to 3 seconds:

- Initially: roughly \(L = 200 \times 0.1 = 20\) concurrent requests.
- When the dependency slows: roughly \(L = 200 \times 3 = 600\) concurrent requests, assuming traffic is admitted and processed in steady state.

If the pool only holds 100 concurrent calls, the excess queues up or gets rejected. When retries keep inflating the arrival rate, the system may **leave steady state**; at that point, the formula above cannot accurately predict an unbounded queue. It simply illustrates why **rising latency drives concurrency pressure** even before retries begin.

### Distinguishing local vs. propagating failures

| Severity | Manifestation | Meaning |
|---|---|---|
| **Local fault** | Payment Provider returns 503 for some commands | One dependency is unhealthy; other services may remain healthy |
| **Caller degradation** | Order API latency rises, hitting connection limits | Order API resources are being dragged down by the dependency |
| **Cascading failure** | Order API throws widespread 503s; Cart API slows because of shared pools | Failure blast radius has escaped the payment task |
| **Zone/system-wide outage** | Multiple instances/zones overload together from retries, shared backends, or sudden failover | Needs load isolation, controlled failover, and dependency protection |

Especially dangerous are **multi-layer retries of the same error** and **unbounded failovers**, such as shifting all traffic into a standby region without sufficient capacity and then retrying there too.

## 6. Classify errors before deciding to retry

Not every error should be retried. **Retryability also depends on operation type, idempotency, prior attempts, remaining deadline, and current health signals**, not status codes alone.

| Case | Retry? | Rationale and conditions |
|---|---|---|
| Transient connection error before the request was sent | Possibly | Suitable for safe operations with remaining deadline and retry budget |
| HTTP 429 with **Retry-After** | Conditional | Honor suggested wait time; retry only if deadline and policy allow |
| HTTP 503 or 502 from transient overload/fault | Conditional | Cap attempts, use backoff+jitter; if service is overloaded, reduce attempts |
| HTTP 500 | Depends | May be a persistent bug; do not blindly retry every 500 |
| HTTP 400/401/403 from invalid payload, permissions, or token | Usually no | Fix request/permissions—retrying will not help; 401 from an expired token may use a controlled credential-refresh flow |
| HTTP 404 | Context-dependent | Do not retry if the resource genuinely does not exist; brief retries may work when eventual-consistency propagation delay is known |
| Validation error, business quota, out of stock | No | Repeating the same request will not change the outcome; handle at business layer |
| Timeout after sending a payment instruction | Never blindly retry | Outcome is **unknown**; query the transaction or use a provider-supported idempotency key |
| Read-only GET with no side effects | Usually safer | Still must avoid retry storms and respect time/resource limits |
| DELETE/PUT with idempotent semantics per API contract | Possibly | Must verify the backend truly handles repeats safely |

Note: **POST is not safe to retry by default.** A POST API can still be safe when combined with durable idempotency keys; conversely, supposedly read-only endpoints can trigger side effects if poorly designed.

## 7. Bounded retry policies

A practical policy can include six rules:

1. **Cap total attempts** (e.g., 2 or 3, including the initial call).
2. **Cap total duration** via the request deadline or an allocated sub-budget.
3. **Retry only when the error is classified as transient and the operation can safely repeat.**
4. **Exponential backoff with jitter** to spread out retry timestamps.
5. **Retry budget / token bucket** to throttle total retry traffic when error rates spike.
6. **Assign a single retry-owning layer**, preventing multiple layers from multiplying attempts unintentionally.

### Exponential backoff and jitter

A common form:

\[
d_n \sim \operatorname{Uniform}(0,\ \min(d_{\max}, d_0 2^{n-1}))
\]

Where \(n\) is the **retry index** (starting at 1), \(d_0\) is the base delay, and \(d_{\max}\) is the cap. This is the **full jitter** variant; the formula illustrates spreading wait intervals rather than guaranteeing complete elimination of load spikes.

Example with \(d_0 = 100\) ms, \(d_{\max} = 800\) ms:

| Retry # | Backoff cap | Random wait range |
|---|---:|---|
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5+ | 800 ms | 0–800 ms |

**Never sleep through a backoff past the deadline.** If the server returns Retry-After, weigh that duration against your remaining budget and policy caps; a 429 response does not grant permission to violate your request deadline.

### Retry budgets

A retry budget limits how much retry work the system accepts within a time window—for instance, a maximum ratio relative to original requests or a dedicated token bucket. It is a **protective guardrail**, not a quota to be spent completely.

Illustrative example: an app receives 1,000 new requests/minute and caps retries at **100 retry attempts/minute** on a flaky route. Once the budget is exhausted, new failures return errors or move to durable background processing per business rules instead of amplifying load further. Tune thresholds from real telemetry rather than copying 10% across every dependency.

### Which layer should own retries?

In a multi-hop synchronous system, it is usually best to place policy **where business semantics, deadline, and idempotency are understood**, and configure lower-level SDKs/proxies not to retry independently past the budget. Keeping low-level retries for a specific connection error can make sense, provided **total attempts are counted together**.

If retries involve major side effects or long durations, consider moving to a **durable async job** with an ID and status rather than holding HTTP connections open for minutes. Queues with retries and DLQs also need caps to prevent infinite loops.

## 8. Implementation pattern: deadlines, retries, and business outcomes

The following pseudocode illustrates a safely repeatable dependency read. This is **language-agnostic pseudocode**, not ready-to-run code for a specific SDK:

~~~text
function call_dependency(request, parent_deadline):
    MAX_ATTEMPTS = 3                   # includes the initial call
    PER_ATTEMPT_CAP = 500ms
    RESERVED_FOR_RESPONSE = 100ms
    MINIMUM_ATTEMPT_TIME = 50ms        # example useful-execution threshold

    for attempt in 1..MAX_ATTEMPTS:
        remaining = parent_deadline - monotonic_now()
        if remaining <= RESERVED_FOR_RESPONSE:
            return DEADLINE_EXCEEDED

        if circuit_breaker.is_open():
            return DEPENDENCY_UNAVAILABLE

        if not concurrency_limiter.try_acquire():
            return OVERLOADED

        try:
            attempt_timeout = min(
                PER_ATTEMPT_CAP,
                remaining - RESERVED_FOR_RESPONSE
            )
            result = dependency.call(
                request,
                timeout=attempt_timeout,
                cancellation=parent_deadline
            )
            record_attempt_success()
            return result
        catch error:
            record_attempt_failure(error)
            if not is_transient(error):
                raise error
            if attempt == MAX_ATTEMPTS:
                raise error
            if not retry_budget.try_consume_token():
                raise RETRY_BUDGET_EXHAUSTED
        finally:
            concurrency_limiter.release()

        backoff = full_jitter(base=100ms, cap=500ms, retry_no=attempt)
        if monotonic_now() + backoff + MINIMUM_ATTEMPT_TIME >=
           parent_deadline - RESERVED_FOR_RESPONSE:
            return DEADLINE_EXCEEDED
        sleep_cancellable(backoff, parent_deadline)

    return UNEXPECTED_STATE
~~~

Key design choices:

- **Per-attempt timeout** never exceeds remaining time.
- **Concurrency limiting** fails fast / sheds load before pools saturate.
- **Retry budget** is checked before retrying; both initial and retry attempts obey the deadline.
- **Cancellable sleep** aborts when the client disconnects or the deadline arrives.
- **Metrics distinguish** initial attempts, retries, and stop reasons.
- **Underlying SDK settings** align so hidden retries never exceed MAX_ATTEMPTS.

For payments, the flow must add idempotency keys, persist payment intent upfront, and include a **query/reconcile** step for **UNKNOWN** states. Without provider guarantees, simple retry logic like the pseudocode above is unsafe.

## 9. Designing timeouts from an end-to-end budget

### Start from the SLO instead of copying a number

Suppose the illustrative target is a **2-second response** for synchronous order creation. A preliminary allocation:

| Step on the synchronous path | Illustrative max budget |
|---|---:|
| Gateway, authentication, and routing | 150 ms |
| Input validation and inventory check | 300 ms |
| Payment processing, including retries/backoff | 1,000 ms |
| Writing Order DB state | 250 ms |
| Margin for jitter, serialization, and network | 300 ms |
| **Total** | **2,000 ms** |

This table shows a **sequential budget to illustrate the math**, not a fixed sum for every flow. When steps run in **parallel**, branch duration is governed by the slowest branch plus coordination overhead; when flows branch conditionally, allocate along actual paths. A request that already spent 500 ms before calling Payment only has 1,500 ms left overall, even if Payment's nominal budget is 1,000 ms.

### Configuring across layers

~~~mermaid
flowchart LR
    U["Client deadline: 2.0s"] --> G["Gateway: 1.9s remaining"]
    G --> O["Order API: 1.7s remaining"]
    O --> P["Payment call: <= 1.0s"]
    P --> X["Provider attempt: <= 0.5s"]
~~~

The numbers in this diagram show **remaining budget**, not independent timeouts you can add together. Downstream layers must read the upstream deadline or receive a smaller timeout. Account for queue wait times inside ingress, service mesh, proxies, and connection pools; a timeout that starts only after bytes hit the wire misses prior queuing delay.

**Design principles:**

1. Define the user-facing SLO, then set the **overall deadline** at the edge.
2. Allocate budgets based on the processing journey and real dependency latencies.
3. Set separate **reasonably short connect timeouts**, **per-attempt timeouts**, and **overall deadlines**.
4. Propagate deadlines/cancellation over RPC, HTTP, and async jobs where protocols support it.
5. Do not start a retry when remaining time is too short for a useful attempt.
6. Handle ambiguous business outcomes carefully when timeouts happen after side effects.

If a transaction inherently takes longer than users can wait synchronously, switch the API contract to **202 Accepted + operationId** (where protocol semantics fit) with status polling or notifications, rather than inflating every timeout.

## 10. Isolation mechanisms to stop cascading failures

### 10.1. Circuit breakers

A circuit breaker tracks dependency errors/slowness. When thresholds breach, it transitions from **CLOSED** (passing requests) to **OPEN** (failing fast), then after a cooldown moves to **HALF_OPEN** to allow a few probe requests to test recovery.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Errors/timeouts exceed threshold
    OPEN --> HALF_OPEN: Open-state cooldown expires
    HALF_OPEN --> CLOSED: Probe attempts succeed
    HALF_OPEN --> OPEN: Probe attempt fails
~~~

A circuit breaker stops sending extra load to an unresponsive dependency. **It does not fix the underlying fault**, and overly sensitive thresholds can reject too much valid traffic. Separate circuits for dependencies with distinct behavior, emit metrics, and avoid having every instance enter half-open simultaneously and trigger a probe surge.

### 10.2. Bulkheads and concurrency limits

The **bulkhead** pattern partitions resources (thread pools, connection pools, worker slots, or semaphores) by feature or dependency. For example, Payment can use at most 40 out of 100 processing slots, leaving capacity for cart and history APIs.

**Concurrency limits** protect finite resources; **rate limits** bound request volume over time. They complement rather than replace each other. When slots run out, fail fast or place requests into a **bounded** queue; an unbounded queue merely shifts exhaustion from pools to memory and latency.

### 10.3. Load shedding and backpressure

When demand exceeds capacity, the system must **shed excess load** cleanly, prioritizing critical transactions or asking clients to retry later. Bottlenecks need a way to signal backpressure upstream: meaningful 429/503 responses, Retry-After headers where appropriate, Gateway throttling, or slowing queue consumers.

Do not return 200/202 for work that has not been durably persisted if the system cannot execute and track it. That turns visible errors into silent losses.

### 10.4. Fallbacks and graceful degradation

When Payment fails, the system can still let users **browse products and view carts**. Some businesses allow saving orders in **PENDING_PAYMENT** for later processing, but only when business contracts, stock holds, deduplication, and transaction expiry allow it. **Never fake payment success** just to boost HTTP 200 rates.

Falling back to stale cached data suits reference catalogs/prices better, showing data age if risk exists; never serve account balances, credit limits, or payment outcomes from stale cache without explicit business policy.

### 10.5. Offloading slow work to async processing

For tasks that can complete later (sending emails, generating reports, updating search indexes), use **durable queues + workers + DLQs** to decouple ingestion rate from processing rate. Require idempotency, retry caps, per-job timeouts, max job age, and reconciliation. **Queues do not eliminate failures**; they provide buffering and controlled recovery.

## 11. Networking, compute, data, and deployment: concrete trade-offs

| Architectural decision | Benefit | Risks / trade-offs to measure |
|---|---|---|
| Separate priority traffic at gateway / rate limiting | Protects critical APIs from low-priority spikes | Misconfigured policies can block legitimate users |
| Enable timeouts and retries in service mesh/proxy | Consistent edge configuration and visibility | Hidden retries multiply with SDK retries; proxies lack business idempotency awareness |
| Isolate pools for Payment, Inventory, and reads | Shrinks blast radius across dependencies | Higher config complexity, overhead, and capacity planning |
| Autoscale compute by request/concurrency or queue age | Absorbs load growth | Cold-start lag, quotas, and shared bottlenecks can still stall |
| Cache eligible reads | Cuts DB or dependency call volume | Stale reads; simultaneous cache misses cause stampedes |
| Separate databases/connection pools per workload | Reduces resource contention | More complex data consistency; added cost |
| Async jobs for work not needed synchronously | Frees HTTP connections quickly, absorbs spikes | Eventual consistency states and complex error recovery |
| Multi-zone or multi-region failover | Survives single-zone outages | Risk of overloading remaining zones; cost, data, and access implications |

**Networking view:** align timeouts across application and network components so proxies/load balancers do not conflict with request deadlines. Connection timeouts over private links, NAT, DNS, TLS, or load balancers behave differently. Network zones improve access control, yet do not stop retry storms if all services still hit one shared dependency.

**Compute view:** monitor concurrent requests, worker counts, connection pools, and autoscaling warmup times. Scaling Order API instances while Payment is the bottleneck may simply overload Payment faster.

**Data view:** DB transactions, locks, connection pools, and idempotency storage must handle repeated requests. If a transaction committed before the client timed out, the system must return the **saved outcome** when the same idempotency key arrives again.

**Deployment view:** retry/timeout configs need clear owners and testing across SDKs, ingress, mesh, load balancers, and workers. A minor library default change can sharply raise real attempt counts.

## 12. Implementing correctness for operations with side effects

A major risk of timeouts is an **ambiguous outcome** (*ambiguous outcome*): the client saw no response while the server already completed the work.

Example:

~~~text
Client sends POST /payments with idempotencyKey = order-824
Payment Service receives and initiates charge
Provider confirms success; Payment Service saves the result
Response connection drops before Client receives HTTP 200
Client sees timeout and resends request with the same idempotencyKey
Server finds the saved result and returns the matching response
~~~

An execution pattern:

1. Backend validates caller permissions, request body, and **idempotency key**.
2. Create a durable record with a unique constraint on the key within tenant/business scope; store a payload fingerprint. If the same key arrives with a different payload, **return a conflict error**.
3. On retry with the same key, if the prior request **completed**, return the stored outcome; if **in progress**, return a pending status or lookup pointer instead of triggering a second side effect.
4. For **ambiguous** provider outcomes, query by correlation/reference ID and reconcile before issuing another charge.
5. Set idempotency-record retention long enough to cover the retry and transaction window; do not purge too early.

**A unique constraint in your own DB does not guarantee once-only charging at the provider.** If the provider supports idempotency keys, follow their contract strictly; if not, build reconciliation and manual resolution workflows when outcomes cannot be confirmed. Cross-system “exactly once” behavior never emerges automatically from retries, timeouts, or local transactions.

## 13. Timeline analysis of a hypothetical incident

This is a simulated example for diagnostic practice, not logs from a real system.

| Time | Event | Impact |
|---|---|---|
| 10:00 | Payment Provider p95 latency climbs from 200 ms to 2,500 ms | Some Payment calls time out |
| 10:01 | Payment SDK retries 3 times; Order API also retries 3 times | Payment attempt volume surges; requests hold connections longer |
| 10:02 | Payment pool fills; Order API request queue grows | Order API p99 breaches SLO |
| 10:03 | Gateway retries further; users click “Pay” again | Heavy duplicate traffic; double-charge risk without idempotency |
| 10:04 | Order API shares a thread pool with Cart API | Cart API starts throwing 5xx even though the cart DB is healthy |
| 10:05 | Autoscaling adds Order API instances while Provider has not recovered | Even more traffic piles onto the bottleneck |
| 10:07 | Gateway retries disabled, Payment concurrency capped, circuit breaker opened | Load to Provider drops; Cart API begins recovering |
| 10:12 | Provider recovers; circuit breaker probes within thresholds | Traffic ramps back under control while watching errors and latency |

### Finding root causes

Do not stop at “the Provider was slow.” Provider slowness was the **trigger**; the architectural causes turning it into a broad outage were **stacked retries**, **timeouts exceeding deadlines**, **unisolated pools**, and **unbounded load**. Post-incident remediation must fix those amplifiers.

A useful postmortem distinguishes:

- **Trigger:** which dependency slowed/failed first, and when?
- **Amplifier:** which SDKs, proxies, and services retried, and how many attempts each?
- **Propagation:** which shared resources dragged unrelated features down?
- **Detection:** which metrics/alerts fired earliest, and which fired too late?
- **Containment:** which load-limit, timeout, circuit-breaker, or failover actions halted the bleed?
- **Prevention:** which tests, config defaults, deploy checks, and runbooks prevent recurrence?

## 14. Observability and resilience testing

### Required metrics and traces

| Signal | What to measure | Interpretation clue |
|---|---|---|
| **End-to-end latency p50/p95/p99** | From user edge to final response/status | Is the SLO being breached? |
| **Per-dependency downstream latency** | DNS/connect/TLS, queuing, request/response where measurable | Where is the bottleneck? |
| **Retry attempt rate** | Retry attempts / original requests, broken down by reason | Are retries amplifying load? |
| **Timeout and cancellation counts** | By layer, request, and dependency | Are deadlines propagated and honored? |
| **In-flight requests, pool utilization** | Active threads/connections/semaphores | Are we nearing concurrency limits? |
| **Queue depth / oldest item age** | In request queues or async jobs | Is congestion sustained or a brief spike? |
| **Circuit breaker state, rejected probes** | Open/half-open, rejected request count | Is the failing dependency properly isolated? |
| **429/503/load-shedding rate** | By upstream and tenant if applicable | Are protective policies impacting users? |
| **Idempotency hits/conflicts** | Duplicate key hits, payload mismatches | Are retries or impatient users repeating calls? |
| **Request/compute/egress cost** | By dependency and error class | Are retries causing abnormal cost spikes? |

Request traces should capture **deadlines, individual attempts, backoff intervals, dependency names, statuses, and idempotency/correlation IDs** safely. Avoid logging tokens, payment details, or sensitive payloads; avoid high-cardinality metric labels like request IDs.

### Controlled testing

Run *fault injection* in a test environment or approved traffic slice:

1. **Inject 2 seconds of latency** into a mock Payment Provider while holding baseline load steady.
2. **Compare** stacked multi-layer retries against single-layer bounded retries with jitter and a retry budget.
3. **Observe** attempts/request, pool utilization, p95/p99 latency, queue depth, and Cart API error rate.
4. **Drop the connection after the provider records a transaction** to verify idempotency and UNKNOWN-state handling.
5. **Restore the dependency** and verify half-open probing, traffic ramp-up, and SLO recovery.

**Pass criteria:** one slow dependency does not take down unrelated features; attempt counts remain bounded; expired requests stop generating useless work; transactions are never duplicated; and operators receive clear signals to act.

Never run fault injection against live payment transactions without dedicated test isolation, synthetic data, and proper safeguards.

## 15. Well-Architected evaluation

| Pillar | Questions to answer | Choices that improve it |
|---|---|---|
| **Operational Excellence** | Who owns retry policies? When a breaker opens, do on-call engineers know what to do? | Standardized configs, tracing, dashboards, alerts, and runbooks |
| **Security** | Can retries resend sensitive tokens/payloads or bypass access quotas? | Scoped tokens, scrubbed logs, rate limits, and per-request auth checks |
| **Reliability** | Can one failing dependency take down other features? Can timeouts cause duplicate side effects? | Deadlines, idempotency, bulkheads, circuit breakers, durable queues where needed |
| **Performance Efficiency** | Are workers/connections held by requests that can no longer succeed? | Cancellation, concurrency caps, timeouts grounded in real latency |
| **Cost Optimization** | Are retries multiplying API, DB, egress, and log bills? | Retry budgets, error classification, backoff+jitter, balanced autoscaling |
| **Sustainability** | How much compute is wasted retrying operations guaranteed to fail? | Stop at deadline, trim futile work, rightsize capacity |

**Trade-offs to record in architecture decisions:** short timeouts free resources sooner yet can raise false errors when dependencies jitter; retries improve transient success rates yet consume time and capacity; circuit breakers isolate failures yet can reject requests briefly after recovery starts; bulkheads protect critical paths yet add limits and management overhead.

An **Architecture Decision Record (ADR)** for retry policy can specify: SLOs and operation types; retry owner; total attempts; deadline; retryable error classes; backoff+jitter; retry budget; idempotency; concurrency limits; test plan; and evaluation metrics. Never pick numbers out of habit without evidence.

## 16. Practice exercises and reference solutions

### Exercise A — Find configuration flaws

A system has:

~~~text
Client deadline                  = 1,500 ms
Gateway retries                  = 2 attempts
Order API retries to Inventory   = 3 attempts
Inventory SDK retries to DB      = 3 attempts
Timeout per Inventory call       = 1,200 ms
Timeout per DB query             = 800 ms
No cancellation, jitter, or concurrency limits
~~~

Questions:

1. If all branches fail and retry, what is the **maximum theoretical DB attempt count under stacked multiplication**?
2. Why does an 800 ms DB query timeout not guarantee the request finishes within 1,500 ms?
3. Propose an attempt-limit, deadline, and resource-protection policy.

**Reference solution:** maximum theoretical DB attempts is \(2 \times 3 \times 3 = 18\) per edge request, assuming every attempt triggers the downstream retries. Real counts depend on failure location, cancellation, and dependency state. The DB timeout bounds only **a single query**; it excludes retries, queuing, networking, backoff, and cumulative layer delays. Fixes include propagating a single deadline; assigning retries to one appropriate layer instead of stacking; bounding total attempts to the latency budget; adding backoff+jitter; enforcing a retry budget; capping concurrency; and alerting on request age.

### Exercise B — Designing around an unstable Payment Provider

A retail gateway processes **300 payment requests/second** at peak. The provider's p99 latency climbs to 4 seconds while the user's synchronous wait budget is 2 seconds. Users may click pay again if the UI reports a timeout.

Propose an API contract, idempotency keys, ambiguous-outcome handling, retry caps, and fallbacks for features not depending on Payment.

**Reference solution:**

- Payment path uses a business-scoped **paymentIntentId/idempotency key** persisted durably before calling out. On timeout after dispatch, return **PENDING/UNKNOWN** and enable status checks and provider reconciliation; avoid declaring final failure before verification.
- Enforce a **2-second total deadline** on the synchronous path. When outcomes cannot reliably finish inside that window, provide a payment-intent creation API plus an **asynchronous** flow for status updates. Retry only when the provider supports safe repeats and budget remains; apply concurrency caps, backoff+jitter, and a circuit breaker.
- Isolate Payment's pools/resource limits from catalog, cart, and history. Those features continue serving normally or degrade per their own policies; never serve payment success from stale cache.
- Monitor **attempt rate, p95/p99 latency, UNKNOWN count, duplicate key count, in-flight Payment calls, circuit breaker state, and SLO breach rate**. Test lost responses after provider completion to verify zero double charges.

## 17. Pre-deployment review checklist

- [ ] **SLOs and end-to-end deadlines** are defined per request class.
- [ ] You know exactly which **SDKs, services, proxies, gateways, and meshes** have retries enabled; total attempts are bounded.
- [ ] Errors are classified into retryable, non-retryable, and **ambiguous outcome** by business semantics.
- [ ] All retries have **attempt caps, total time caps, backoff, jitter, and retry budgets**.
- [ ] Connect, per-attempt, and overall timeouts align; deadlines and cancellation propagate downstream.
- [ ] Operations with side effects enforce **idempotency** and post-timeout lookup/reconciliation.
- [ ] **Concurrency limits, bulkheads, rate limiting/load shedding** isolate dependencies.
- [ ] Circuit breakers have clear thresholds, probes, metrics, and runbooks.
- [ ] Queues, if used, enforce retry caps, max job age, DLQs, and recovery.
- [ ] Telemetry tracks **attempts/request, timeouts, p95/p99, in-flight count, queue age, fallbacks, and cost**.
- [ ] Tested against slow dependencies, transient faults, prolonged outages, dropped connections after side effects, and recovery.
- [ ] Trade-offs across reliability, security, performance, cost, operations, and sustainability are documented under Well-Architected.

**Conclusion:** Unbounded retries and inconsistent timeouts are **antipatterns** because they lose control over how much work gets generated and how long it holds resources. Resilient architectures bound total work by deadlines, prioritize business correctness, isolate unhealthy dependencies, and enable **controlled rejection or degradation** under overload. The goal is keeping critical parts of the system serving while waiting for failing components to recover.
