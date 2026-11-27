# Retries with Backoff, Jitter, and Retry Budgets

## 1. Retries Recover Transient Failures, Yet Can Worsen Outages

In cloud systems, a request can fail due to flaky networks, connection resets, overloaded services, rate limits, node failovers, or temporary dependency unavailability. Retries help overcome brief glitches without forcing users to resubmit actions manually. However, if many clients retry immediately at the same time, the system can unleash a fresh wave of requests right when the dependency is weakest.

This is **retry amplification**: one initial request spawns multiple extra calls, inflating load, queues, latency, and errors. When services retry one another across tiers, call counts multiply across layers.

In the **CLOUD_ARCHITECTURE** module, reliability is engineered from business requirements down through compute, networking, storage, and operations. Retries are an application-layer recovery mechanism; they must coordinate with timeouts, deadlines, idempotency, circuit breakers, rate limits, and capacity budgets to protect SLOs.

After this lesson, you will be able to distinguish transient, permanent, and ambiguous failures; choose safe operations to retry; compute exponential backoff, attempt caps, and wait bounds; apply jitter to prevent synchronized requests; design retry budgets; coordinate timeouts/deadlines; prevent retry storms across services and queues; and verify behavior with metrics, fault injection, and Well-Architected reviews.

## 2. The Nature of Retries and Result Semantics

Retrying means re-sending an operation after a prior attempt failed to achieve the expected outcome. Crucially, **not all errors carry the same meaning**.

### 2.1. Three Result Categories

| Result category | Examples | Handling approach |
|---|---|---|
| Definitive success | Server returned a valid response; operation completed | Do not retry |
| Definitive failure | Validation error, permission denied, business conflict | Do not auto-retry; fix input/permissions or handle in business logic |
| Ambiguous outcome | Timeout after server may have committed; connection reset before response | Query status or retry with the same idempotency key |

A timeout only says the caller did not receive a response in time. It **does not prove** the server never executed the operation. For a POST creating a booking or charging payment, the first call may have committed while the response was lost. Retrying as a new request can create duplicate side effects.

### 2.2. Retryable Does Not Mean Every 5xx

Classify based on dependency semantics and contracts, not just HTTP status codes:

| Situation | Usually retry? | Reason / handling |
|---|---|---|
| DNS/network transient failure | Possibly | Cap attempts/deadline; confirm error is recoverable |
| Connection reset before sending request | Possibly | Likely never reached server; still distinguish phases |
| Timeout after sending request | Conditionally | Outcome may have committed; requires idempotency/status lookup |
| HTTP 408 | Possibly | Per contract and deadline |
| HTTP 429 | Conditionally | Honor `Retry-After` and quotas; avoid exceeding budget |
| HTTP 502/503/504 | Possibly | If dependency documents transient semantics and operation is safe |
| HTTP 400 validation | No | Same request will keep failing |
| HTTP 401 | Not via blind retry | Refresh credentials via auth flow if valid |
| HTTP 403 | No | Fix authorization/policies |
| HTTP 404 | Usually no | May retry if contract defines eventual resource propagation |
| HTTP 409 business conflict | Not via immediate retry | Refresh state/propose another action |
| Insufficient funds / invalid state | No | Definitive business failure |
| Circuit breaker open | Do not call dependency | Fall back or return controlled error |

Even for retryable status codes, consider the operation, error code, `Retry-After`, deadline, and retry budget.

### 2.3. Retry Policies Must Tie to Operations

- GET product can usually be retried on transient network errors because reads create no side effects.
- PUT setting a resource to a specific state may be API-idempotent, though version/concurrency checks still apply.
- POST creating a booking is safe to retry only when the API supports an idempotency key or the client can look up outcomes via an operation ID.
- POST charging payment requires provider idempotency and reconciliation; never retry with a new key solely due to a timeout.
- DELETE may be idempotent in final state, yet downstream logs, notifications, or external side effects must still be designed not to repeat unintentionally.

## 3. Exponential Backoff

If a dependency is overloaded or experiencing transient errors, immediate retries push more requests onto its queue. **Backoff** increases the wait interval between attempts.

With basic exponential backoff:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where \(d_0\) is the initial delay, \(n\) is the retry attempt index starting at 1, \(d_{\max}\) is the maximum delay, and \(d_n\) is the wait duration before retry \(n\).

For example, choosing an initial delay of 200 ms and a 5-second cap:

| Retry attempt | Delay before jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 3,200 ms |
| 6 | 5,000 ms (capped) |
| 7 onward | 5,000 ms |

These are illustrative examples; actual delays depend on latency, SLAs, deadlines, and dependency load.

### 3.1. Why Cap the Delay?

Without a cap, delays grow rapidly and requests may wait longer than business value permits. A cap limits each individual wait, though it does not automatically cap total elapsed time. Simultaneously cap maximum attempts, total retry time, request/workflow deadlines, and total retries allowed against the dependency.

### 3.2. Fixed Delay, Linear Backoff, and Exponential Backoff

| Approach | General formula | When to consider | Limitations |
|---|---|---|---|
| Fixed delay | Wait the same interval every time | Simple retries under low load | Clients synchronize easily |
| Linear backoff | Delay grows steadily per attempt | Systems with steady load | Scales up slowly during prolonged outages |
| Exponential backoff | Delay grows exponentially, capped | Overloaded dependencies or transient outages | Can create retry clusters without jitter |

## 4. Jitter: Desynchronizing Retries

If 10,000 clients fail at the same instant and all use delays of 1, 2, 4, 8 seconds, they can retry in near lockstep. This phenomenon is a **thundering herd**. Jitter adds randomness to delays to spread requests over time.

### 4.1. Full Jitter

Given exponential cap \(b_n\), full jitter picks:

\[
d_n \sim U(0, b_n)
\]

If the backoff cap is 800 ms, the actual delay is sampled randomly between 0 and 800 ms. This spreads requests aggressively; some requests may retry quite early, so deadlines and retry budgets must still enforce limits.

### 4.2. Equal Jitter

A variant selects:

\[
d_n = \frac{b_n}{2} + U(0, \frac{b_n}{2})
\]

The delay is never below half of the exponential cap. This avoids retrying too early, at the cost of less dispersion than full jitter.

### 4.3. Decorrelated Jitter

A form of decorrelated jitter computes the next delay from the previous delay:

\[
d_n = \min(d_{\max}, U(d_{\min}, 3d_{n-1}))
\]

It avoids fixed periodic retry schedules. Check your library's exact implementation because naming and formulas can vary.

### 4.4. Retry Schedule Illustration

~~~mermaid
flowchart TD
    A["Attempt 1"] -->|"Failure"| B["Compute exponential cap"]
    B --> C["Apply jitter"]
    C --> D{"Deadline and retry budget remain?"}
    D -->|"No"| E["Stop / fallback / fail"]
    D -->|"Yes"| F["Wait selected delay"]
    F --> G["Attempt next"]
    G --> H{"Success?"}
    H -->|"Yes"| I["Return result"]
    H -->|"No"| B
~~~

Jitter spreads retries across time; it does not automatically reduce total attempts. A retry budget is what caps total added load.

## 5. Retry Budgets: Limiting Load Created by Retries

A policy stating only "retry up to 5 times" is insufficient for a service handling millions of requests. During an outage, every request may burn all 5 attempts and overload the dependency further.

A **retry budget** is a resource or ratio cap allocated to retry requests over a time window. Its goal is to ensure retries consume only a bounded fraction of traffic/capacity.

### 5.1. Ratio-Based Budgets

A common approach caps retries relative to original requests or successful requests within a window.

Example policy:

- Allow at most 10 retries per 100 original requests in a measurement window.
- If the budget is exhausted, new requests fail temporarily or use a fallback instead of continuing to call the dependency.
- The budget replenishes as healthy traffic flows or over a defined rolling window.

These numbers are examples only. Budgets should be derived from capacity headroom, SLOs, error rates, and dependency characteristics.

### 5.2. Token Bucket Budgets

Budgets can be implemented as a token bucket: each retry consumes one token; tokens replenish at a defined rate; the bucket has a maximum capacity to allow brief retry bursts; when empty, stop retrying or fall back.

Buckets can live per process, service instance, sidecar, or centralized coordinator. Local budgets are simple to deploy, though cluster-wide retries scale with replica count; distributed budgets are more accurate but add dependencies and coordination.

### 5.3. Budgets by Dependency and Tenant

A service often calls multiple dependencies. Separate budgets per dependency so Payment errors do not exhaust the retry budget for the Database or Identity provider.

You can further partition by dependency/endpoint; tenant or client tier; foreground requests vs. background jobs; critical operations vs. secondary tasks; and region/zone or failure domain when blast radii differ.

Avoid splitting into so many tiny buckets that operations become opaque or each bucket holds too few tokens to absorb legitimate bursts.

### 5.4. Retry Budgets vs. Rate Limits

| Mechanism | What it limits |
|---|---|
| Rate limit | Total request rate to a resource/client/route |
| Concurrency limit | Number of operations running concurrently |
| Retry budget | Additional request share allowed from retries |
| Circuit breaker | Stops calling a dependency when failures breach a threshold |
| Deadline | Maximum time an operation remains useful to the caller |

They complement rather than replace one another. A rate limit may allow original requests through without knowing which are retries; a retry budget explicitly governs extra load from retries.

## 6. Timeouts, Deadlines, and Total Retry Time

Retries help only if the next attempt still has enough time to produce a useful outcome.

### 6.1. Per-Attempt Timeouts

A timeout bounds a single attempt, such as connect timeout, TLS handshake timeout, response timeout, or total client request timeout. Too short cuts off operations still progressing on the server; too long causes concurrent requests to pile up and exhaust resources.

Timeouts must reflect latency distributions, network paths, dependency SLOs, and operation types. Never use an arbitrary identical value for every dependency.

### 6.2. Overall Deadlines

A deadline is the final timestamp by which an operation is still permitted to complete. Suppose an external HTTP request has 2 seconds remaining on its deadline. If the previous attempt consumed 1.5 seconds, you cannot wait 1 second of backoff and start another attempt within the deadline.

~~~text
remaining = deadline - monotonic_now()

if remaining <= minimum_attempt_time:
    stop retry
else:
    wait = min(jittered_backoff, remaining - minimum_attempt_time)
    wait
    call dependency with timeout <= remaining
~~~

This is pseudocode. In real systems, use a monotonic clock to measure durations/deadlines inside a process; never substitute a wall clock that can jump on time adjustments.

### 6.3. Coordinating Timeouts Across Layers

Suppose a request flows through API gateway → Booking service → Inventory service → Database:

- Gateway holds the overall deadline.
- Booking sets an internal timeout shorter than remaining deadline.
- Inventory sets connection and response timeouts.
- Database queries set an appropriate statement timeout.

No layer should configure timeouts longer than the caller's remaining deadline and keep retrying after the caller has given up. Propagate bounded deadlines/remaining timeouts across services to avoid "orphan" work.

### 6.4. Backoff Must Not Exceed the Deadline

Total workflow time must include:

\[
T_{\text{total}} = \sum T_{\text{attempt}} + \sum T_{\text{backoff}} + T_{\text{overhead}}
\]

If total time would exceed the deadline, stop retrying and pick an appropriate outcome: return a temporary error, return `PROCESSING` with an operation ID, enqueue the job, or hand off to reconciliation.

## 7. Idempotency and Ambiguous Outcomes

Backoff and jitter govern **when** to retry; idempotency governs **whether retrying repeats side effects**.

### 7.1. Idempotent Operations

An idempotent operation produces the same final state whether executed once or multiple times under identical conditions. HTTP GET is generally designed to be safe/idempotent; PUT and DELETE can be resource-state idempotent. That does not mean downstream logs, notifications, or external side effects automatically fire only once.

### 7.2. Idempotency Keys for POST

~~~http
POST /v1/bookings
Authorization: Bearer <token>
Idempotency-Key: booking-create-user-120-req-781
Content-Type: application/json

{
  "deviceId": "dev-017",
  "slotId": "slot-0900"
}
~~~

The server should define key scope; store the key alongside payload hash, processing status, and result; for matching key/payload return the prior result or in-progress status; reject matching keys with differing payloads; retain keys longer than the retry window and workflow timeout; and persist the idempotency record atomically with business state changes in the same transaction when possible.

Never generate a fresh key after a timeout simply because the client does not know if the first call succeeded. Query or retry using the same key or operation ID.

### 7.3. Ambiguous Outcomes

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as Booking API
    participant DB as Database
    C->>A: POST booking + idempotency key K
    A->>DB: Commit booking + result for K
    DB-->>A: Commit success
    Note over A,C: Response lost / connection timeout
    C->>A: Retry same request + key K
    A->>DB: Lookup idempotency record K
    DB-->>A: Existing committed result
    A-->>C: Return original booking result
~~~

If the idempotency record and business row are written in two independent transactions, a crash between writes still leaves a window for duplicates or lost results. Use a shared transaction, unique constraints, or an appropriate protocol.

## 8. Retry Storms and Multi-Layer Amplification

Suppose a mobile client retries up to 3 times; the API gateway retries 2 times; the Booking service retries 3 times against Inventory. If every tier nests retries without coordination, call counts multiply across tiers.

Simple example: the gateway can forward up to 2 times; the service can try Inventory 3 times per received call. Inventory can receive up to 6 calls, not counting internal retries inside the database client.

~~~mermaid
flowchart TD
    CLIENT["Client: attempts"] --> GW["Gateway: retries"]
    GW --> SVC["Booking service: retries"]
    SVC --> DEP["Inventory dependency"]
    DEP --> DB["Database"]
    DEP -. "Failure responses" .-> SVC
    SVC -. "Failure responses" .-> GW
    GW -. "Failure responses" .-> CLIENT
~~~

### 8.1. Choose One Layer to Own Retries

- Identify which layer understands operation semantics and holds authority to retry.
- Avoid retrying the same failure at every tier.
- Lower layers may retry narrow transport errors only if the operation is guaranteed unsent; the business layer manages retries by operation ID.
- Propagate deadlines and retry metadata/budgets across layers.
- Never let a gateway blindly retry non-idempotent POST requests.

Strictly limiting retries to a single layer is not always absolute. A database driver may retry transaction serialization errors while the application retries workflows. Still, total attempts must be modeled so they do not multiply unintentionally.

### 8.2. Circuit Breakers and Load Shedding

When a dependency fails continuously, the circuit breaker transitions from Closed to Open, blocking new calls for a period; then Half-open allows a few probes to check recovery. Retry budgets cap retry load; circuit breakers stop sending requests to broken dependencies; load shedding drops lower-priority work when capacity runs out.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: failure threshold reached
    Open --> HalfOpen: cooldown elapsed
    HalfOpen --> Closed: probe succeeds
    HalfOpen --> Open: probe fails
~~~

## 9. Retries in Queues and Background Jobs

Queue consumers often retry messages when handlers fail. Unmanaged, a poison message can redeliver endlessly, block partitions, or swell backlogs.

### 9.1. Retry Topics/Queues or Delayed Delivery

Use delayed retry queues with increasing delays; visibility timeouts/leases for message processing; maximum delivery/attempt counts; dead-letter queues (DLQs) once limits are exceeded; and consumer idempotency so duplicate deliveries do not repeat side effects.

### 9.2. Message-Level Backoff

| Attempt | Illustrative delay | Behavior |
|---:|---:|---|
| 1 | 1 second | Fast retry for brief glitches |
| 2 | 5 seconds | Wait for dependency recovery |
| 3 | 30 seconds | Reduce delivery rate |
| 4 | 2 minutes | Retry within bounded window |
| Beyond max attempts | DLQ | Controlled investigation/replay |

Actual delays need jitter and must align with retention, visibility timeouts, message ordering, and business deadlines. Never let retries cause a message to expire before it has a chance to process.

### 9.3. Poison Messages and DLQs

Messages failing due to bad schemas or invalid business data will not heal through retries. After reasonable attempts, route them to a DLQ, store the cause and safe metadata, and alert owners. Replay only after fixing the root cause and ensuring idempotency; never replay an entire DLQ straight into production without checking blast radius.

### 9.4. Long-Running Workflow Retries

For sagas or long jobs, never hold a request thread to retry for minutes. Persist state durably, schedule the next attempt, give callers an operation ID to poll status or subscribe to events, and provide cancellation/deadlines/reconciliation.

## 10. Designing a Retry Policy

A policy can be documented in a table:

| Attribute | Example for Inventory API | Purpose |
|---|---|---|
| Retryable failures | Transient network errors, 503, 429 honoring `Retry-After` | Retry only recoverable failures |
| Max attempts | 3 total | Prevent infinite retries |
| Initial delay | 100 ms | Wait before first retry |
| Backoff | Exponential | Increase wait interval |
| Jitter | Full jitter | Desynchronize clients |
| Max delay | 1 second | Cap per-attempt wait |
| Per-attempt timeout | Per dependency latency/SLO | Avoid holding requests indefinitely |
| Overall deadline | Within request deadline | Stop when outcome is no longer useful |
| Retry budget | Ratio over defined window | Cap extra load |
| Idempotency | Required for hold/release by operation ID | Avoid duplicate holds/releases |
| Circuit breaker | Per failure/slow-call thresholds | Stop calling failing dependency |
| Exhaustion behavior | Return 503 or workflow `PENDING` | Report consistent outcomes |

Numbers above are samples only. Each API needs a policy tailored to latency distributions, SLOs, semantics, capacity, and dependency contracts.

### 10.1. Illustrative Pseudocode

~~~text
call_with_retry(operation, deadline, policy):
    for attempt in 1..policy.max_attempts:
        remaining = deadline - monotonic_now()
        if remaining <= policy.minimum_attempt_time:
            return DEADLINE_EXCEEDED

        if attempt > 1:
            if not retry_budget.try_consume(operation.dependency):
                return RETRY_BUDGET_EXHAUSTED

            cap = min(
                policy.max_delay,
                policy.initial_delay * 2 ** (attempt - 2)
            )
            delay = random(0, cap)  # full jitter

            if delay + policy.minimum_attempt_time >= remaining:
                return DEADLINE_EXCEEDED

            sleep(delay)

        timeout = min(policy.per_attempt_timeout, remaining)
        result = operation.execute(timeout)

        if result.success:
            return result

        if not policy.is_retryable(result):
            return result

        if not operation.is_safe_to_retry:
            return UNKNOWN_OUTCOME_OR_RECONCILE

    return ATTEMPTS_EXHAUSTED
~~~

This pseudocode illustrates the decision flow, not a production library. Add cancellation, interruption handling, exception classification, clock injection, observability, server-directed `Retry-After`, concurrency control, and explicit semantics for ambiguous outcomes. The `is_safe_to_retry` check must enforce idempotency or appropriate status lookup.

## 11. Retry-After and Server Signals

When a server returns 429 or 503, the `Retry-After` header may specify when or how long to wait before retrying. Clients should parse supported contract formats properly; never retry earlier than requested; still enforce deadlines and retry budgets; apply controlled extra jitter to prevent synchronized client retries; and avoid holding threads/requests indefinitely if `Retry-After` is too long.

Servers should emit `Retry-After` values aligned with quotas/recovery policies and avoid suggesting an exact timestamp to millions of clients if that would trigger a new herd.

## 12. Retry Libraries and Safe Configuration

When selecting an HTTP client, database driver, messaging client, or resilience library, check:

- Whether retries are enabled by default and at which layer.
- Which exceptions/statuses are retried.
- Whether exponential backoff/jitter is supported.
- Max attempts and max elapsed time.
- Whether `Retry-After` is honored.
- Whether deadline/cancellation propagation is supported.
- Which methods/operations are retried; whether POST is retried.
- Whether metrics/logs capture attempt numbers, reasons, and exhaustion.
- Whether a retry budget or hook to integrate a budget service exists.
- Whether interactions with circuit breakers/rate limiters prevent double-counting retries.

Avoid letting multiple middleware layers auto-retry unaware of one another. Write integration tests verifying actual wire-level request counts when dependencies return errors.

## 13. Observing and Operating Retries

Aggregate request success metrics can hide heavy retrying underneath. Separate original traffic from retry traffic.

### 13.1. Metrics

| Metric | Meaning | Interpretation |
|---|---|---|
| Original request count | Initial business request volume | Denominator for calculating amplification |
| Retry attempt count | Additional calls | Spikes indicate unstable dependencies or policies |
| Retry ratio | Retry/original requests | Measures load amplification |
| Retry success rate | Share of retries turning failures into success | Shows if retries help or just add load |
| Retry budget exhaustion | Number of times budget ran out | Signals system hitting safety limits |
| Attempts per operation | Distribution of attempt counts | Detects tails taking many attempts |
| Backoff delay histogram | Actual wait times | Confirms jitter and caps |
| Deadline exceeded | Operations timing out | Separates dependency slowness from excessive retry waits |
| Circuit breaker state | Closed/Open/Half-open | Tracks dependency health |
| DLQ depth/age | Messages awaiting manual handling | Detects poison messages/backlogs |

### 13.2. Logs and Traces

Log attempt number, dependency, error classification, delay, timeout, appropriately masked idempotency/operation IDs, retry budget decisions, and final outcomes. In distributed traces, represent each attempt as a separate span under the same parent operation.

Never log raw tokens, secrets, payment data, or PII. Avoid using unique operation IDs as metric labels to prevent high cardinality; keep IDs inside access-controlled traces/logs.

### 13.3. SLOs and Error Budgets

Retries can let a request ultimately succeed even if intermediate attempts failed. Decide where SLOs measure:

- User-visible success/latency: reflects end-user experience.
- Dependency attempt success/error: reflects health of individual calls.
- Retry amplification: reflects extra load.
- Queue completion age: reflects asynchronous processing time.

Never mask dependency incidents by reporting only final success. If latency spikes due to retries, success rate may still hold while user experience and capacity degrade.

## 14. Testing Retries and Fault Injection

Before production, simulate these scenarios:

1. Dependency returns 503 twice, then succeeds.
2. Dependency returns 429 with `Retry-After`.
3. Connection resets before request finishes sending.
4. Request executes and commits, but response is dropped.
5. Dependency runs slower than per-attempt timeout.
6. Many clients fail simultaneously.
7. Retry budget exhausts during a prolonged outage.
8. Circuit breaker opens when failure threshold is breached.
9. Queue consumer receives a poison message.
10. Client cancels request while server is still processing.

### 14.1. Verification Criteria

- Total attempts never exceed max attempts.
- No attempt starts after the deadline.
- Delays disperse via jitter when many clients fail together.
- Retry budget bounds additional load per policy.
- Booking/payment POSTs never create duplicate side effects when responses are lost.
- Non-retryable errors are never retried.
- `Retry-After` is honored.
- Circuit breakers and load shedding reduce origin QPS when dependencies fail.
- DLQs capture messages exceeding max deliveries and replay safely under control.
- Metrics distinguish original requests, retry attempts, and final outcomes.

## 15. Example: Retry Policy for BookingCloud

Booking API calls Inventory to hold slots and Payment provider to authorize. The two operations have distinct semantics:

| Component | Hold inventory | Authorize payment |
|---|---|---|
| Operation identity | Stable `hold_id`/`booking_id` | Stable payment operation ID |
| Idempotency | Required | Required per provider contract |
| Retryable | Transient network errors, 429/503 per policy | Transient network errors, 429/503 per provider policy |
| Ambiguous timeout | Query hold status or retry with same key | Query payment status with reference/key |
| Backoff | Exponential + jitter | Honor `Retry-After` + exponential/jitter |
| Budget | Dedicated to Inventory dependency | Dedicated to Payment dependency |
| Exhaustion | Booking `PENDING` or fail per hold deadline | Payment outcome unknown; hand off to reconciliation |
| Compensation | Idempotent hold release | Void authorization; never blindly charge/refund |

~~~mermaid
flowchart TD
    START["Create booking request"] --> BUDGET{"Request deadline and budget available?"}
    BUDGET -->|"No"| PENDING["Return PROCESSING / controlled failure"]
    BUDGET -->|"Yes"| HOLD["Hold inventory with stable key"]
    HOLD -->|"Success"| PAY["Authorize payment with stable key"]
    HOLD -->|"Transient failure"| RETRYH["Backoff + jitter + inventory budget"]
    RETRYH --> HOLD
    HOLD -->|"Permanent / exhausted"| FAIL["Fail or compensate"]
    PAY -->|"Success"| CONFIRM["Confirm booking"]
    PAY -->|"Ambiguous timeout"| QUERY["Query payment status"]
    QUERY -->|"Authorized"| CONFIRM
    QUERY -->|"Not authorized, retry allowed"| RETRYP["Retry same key within deadline"]
    RETRYP --> PAY
    QUERY -->|"Still unknown"| RECON["Reconciliation / manual review"]
    PAY -->|"Definitive decline"| FAIL
    CONFIRM --> DONE["Completed"]
~~~

This flow illustrates a stateful process. For synchronous APIs with tight deadlines, the system can return `PROCESSING` with an operation ID and continue the workflow in the background. Never hold HTTP requests open for tens of seconds just to finish retries if callers can poll or receive events.

## 16. Well-Architected Review

| Perspective | Review questions | Required evidence |
|---|---|---|
| **Operational Excellence** | Do retry policies have owners, dashboards, runbooks, and controlled changes? | Policy inventory, attempt metrics, exhaustion alerts, replay/incident runbooks |
| **Security** | Do retries repeat sensitive actions, bypass tenant quotas, or leak data in logs? | Idempotency, auth revalidation, least privilege, log redaction |
| **Reliability** | Can outages trigger retry storms? Are deadlines, jitter, budgets, and recovery paths in place? | Fault injection, amplification ratios, budget exhaustion, circuit breaker tests |
| **Performance Efficiency** | Do backoff/attempts inflate latency or hold resources too long? | p95/p99, attempt histograms, connection/queue utilization |
| **Cost Optimization** | How much do retries add to compute, network, provider charges, and queue costs? | Cost per successful operation, duplicate request counts |
| **Sustainability** | Are retry loops or wasteful polling burning unnecessary compute? | Retry success rates, bounded attempts, queue polling/retention metrics |

Retries pay off only when recovery probability and business value outweigh load, latency, and side-effect costs. If continued retrying stops improving success odds, stop, shed load, or transition to a recovery workflow.

## 17. Hands-On Exercise: Preventing a Retry Storm During an Inventory Outage

BookingCloud receives 4,000 requests/second. Each request calls Inventory once. Inventory begins returning 503 for 30 seconds. Currently:

- API gateway retries 2 times.
- Booking service retries 3 times.
- HTTP client adds 2 default retries.
- Slot holds have no idempotency key.
- Per-attempt timeout is 2 seconds; request deadline is 5 seconds.
- No retry budget exists.

Complete the following:

**Task 1 — Amplification:** calculate maximum generated calls under this nested retry setup. Explain why you cannot simply add attempts across layers when retries nest.

**Task 2 — Retry ownership:** choose the retry-owning layer based on Inventory semantics; disable or bound redundant retries at remaining layers.

**Task 3 — Backoff/jitter:** propose initial delay, exponential cap, full/equal/decorrelated jitter, and max attempts grounded in the deadline.

**Task 4 — Idempotency:** design a hold operation ID and handle cases where Inventory held the slot but the response was lost.

**Task 5 — Retry budget:** design a per-dependency token budget and define behavior when exhausted.

**Task 6 — Circuit breaker:** select open/half-open signals and protect capacity as Inventory recovers.

**Task 7 — Verification:** write fault-injection tests for a 30-second outage, 429s, timeout-after-commit, and synchronized client retries.

### Self-Check Analysis Framework

| Current state | Risk | Fix direction |
|---|---|---|
| Retries at gateway + service + client | Attempts multiply | Designate owning layer; limit nested retries |
| No idempotency | Duplicate holds or multiple reservations | Stable operation key, unique constraints/status lookup |
| No jitter | Thundering herd | Exponential backoff + jitter |
| No retry budget | Retries exhaust capacity | Per-dependency token/rate budget |
| 2s timeout with 5s deadline | Insufficient time for multiple retries/backoffs | Compute remaining deadline before each attempt |
| No circuit breaker | Keeps hammering failing dependency | Open/half-open states and load shedding |

Do not check only total latency; also measure actual wire calls reaching Inventory and persisted side effects.

## 18. Pre-Production Retry Checklist

- [ ] Failures are classified as retryable, permanent, or ambiguous per contract.
- [ ] Every operation has semantics/idempotency matching its side effects.
- [ ] Max attempts, exponential backoff, and max delay are configured.
- [ ] Jitter disperses client retries.
- [ ] Backoff never exceeds the overall deadline; each attempt has proper timeout/cancellation.
- [ ] `Retry-After` is honored while still enforcing budgets/deadlines.
- [ ] Retry budgets exist per dependency and critical load groups.
- [ ] Uncontrolled multi-layer retries are prevented; actual wire-level attempts are known.
- [ ] Circuit breakers, concurrency limits, rate limits, and load shedding coordinate with retries.
- [ ] Queue retries enforce max deliveries, delayed retries, and DLQs.
- [ ] Ambiguous results use status lookups/idempotency/reconciliation.
- [ ] Metrics separate original requests, retry attempts, retry successes, exhaustion, and final outcomes.
- [ ] Logs/traces carry correlation without recording sensitive secrets/PII.
- [ ] Fault-injection tests cover outages, timeout-after-commit, duplicates, 429s, and herds.

Retries are part of reliability engineering, not an endless loop. Exponential backoff slows down during sustained faults; jitter breaks synchronization; retry budgets cap amplification; timeouts/deadlines bound time and resources; idempotency protects side effects. Combining these controls with circuit breakers, backpressure, and thorough observability lets systems recover from transient errors without turning a slow dependency into a widespread outage.
