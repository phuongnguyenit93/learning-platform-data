# Bulkheads, Circuit Breakers, and Cascading Failure Isolation

## Learning Objectives

In distributed systems, a service often depends on databases, internal APIs, payment services, message brokers, or external providers. When a dependency slows down or fails, requests may hold threads, connections, and memory longer than normal. Queues grow, pools exhaust, timeouts propagate back to callers, and otherwise healthy components begin failing as well. This phenomenon is a **cascading failure**.

Three techniques commonly used to contain incident scope are:

- **Bulkhead:** partitions resources into isolated compartments so one workload group cannot consume all resources belonging to others.
- **Circuit breaker:** monitors dependency errors and temporarily halts calls when a dependency shows signs of unhealthiness, giving the system space to recover.
- **Fault isolation:** designs boundaries so failures stay confined within a component, tenant, request class, region, or dependency.

These techniques complement timeouts, retry budgets, backpressure, load shedding, queues, and graceful degradation. They do not stop dependencies from failing; the goal is to protect the rest of the system, preserve critical capabilities, and recover under control.

This lesson belongs to the **Reliability** chapter, focusing on bulkheads, circuit breakers, and cascading failure isolation. In Cloud Architecture, choosing isolation boundaries should start from business requirements, network topology, compute, databases, deployment models, and resource-sharing levels; balancing reliability, security, scalability, cost, and operations per Well-Architected principles.

After this lesson, you will be able to:

- Explain how a single dependency failure cascades into a system-wide outage.
- Recognize resource exhaustion, queue buildup, retry storms, and thread/connection starvation.
- Design bulkheads by dependency, workload class, tenant, region, and criticality.
- Describe a circuit breaker with Closed, Open, and Half-Open states.
- Select failure thresholds, slow-call thresholds, open durations, and probe policies with clear rationale.
- Coordinate circuit breakers with timeouts, retries, backoff, jitter, and idempotency.
- Design fallbacks/degraded modes that do not violate business invariants.
- Distinguish transient errors, permanent errors, overload, and business errors.
- Observe incidents via latency, concurrency, queues, breaker states, and business SLOs.
- Test fault injection, recovery, tenant isolation, and failover scenarios.
- Evaluate costs and risks when applying these patterns in cloud systems.

## 1. How Do Cascading Failures Form?

Suppose a room booking system has a synchronous flow:

1. API receives a booking confirmation request.
2. Booking service checks inventory.
3. Booking service calls payment service.
4. Booking service writes to the database and returns the result.
5. Notification service sends a notification.

If the payment service latency rises from 100 ms to 8 seconds, booking requests wait longer. Each request holds a thread and potentially connections or other resources. In-flight concurrency rises, pools exhaust, and new requests start queuing. The API gateway hits its deadline and returns timeouts, yet downstream work may continue consuming resources. Clients retry, increasing calls to payment. Other services get pulled into the outage even though they are not broken themselves.

~~~mermaid
flowchart TD
    C["Incoming traffic increases"] --> API["Booking API"]
    API --> PAY["Payment service slow"]
    PAY --> WAIT["Requests/threads wait long"]
    WAIT --> POOL["Thread / connection pools exhausted"]
    POOL --> TIMEOUT["API timeout"]
    TIMEOUT --> RETRY["Clients and services retry"]
    RETRY --> PAY
    RETRY --> LOAD["Added load"]
    LOAD --> WAIT
~~~

### 1.1. Propagation Mechanisms

| Mechanism | What happens | Consequence |
| --- | --- | --- |
| Resource exhaustion | Threads, connections, memory, or file descriptors stay held | New requests cannot be processed |
| Queue buildup | Requests/jobs arrive faster than completion rate | Latency and backlog grow continuously |
| Retry amplification | Multiple layers retry the same operation | Failing dependency receives extra load |
| Timeout mismatch | Caller times out while callee keeps running | Wasted work keeps consuming resources |
| Synchronous dependency chain | One request waits sequentially on multiple services | Latencies add up; one failure affects many services |
| Shared resource contention | Multiple workloads share a DB, pool, or executor | Other tenants/features are impacted |
| Recovery storm | Many clients reconnect or replay simultaneously | Recovering dependency gets overloaded again |

### 1.2. Availability of a Dependency Chain

If a request requires all sequential dependencies to succeed, total path availability is usually lower than each individual component. Under a simple independence assumption:

~~~text
Availability(path)
  = A(service 1) × A(service 2) × ... × A(service n)
~~~

For example, three dependencies with 99.9% availability each, assuming independence:

~~~text
0.999 × 0.999 × 0.999 ≈ 99.7003%
~~~

This is an illustrative model only. In practice, failures can correlate due to shared regions, networks, identity providers, or databases. Fallbacks, caches, queues, and degraded modes can reduce mandatory dependencies for certain use cases.

## 2. Fault Isolation: Defining Boundaries to Protect

Fault isolation begins with the question: **if one component breaks, which workloads are allowed to be affected?**

Isolation boundaries can be drawn by:

- Dependency: payment, search, notification, reporting.
- Resource: thread pool, connection pool, queue, CPU, memory.
- Workload class: interactive, background, batch, admin.
- Tenant/customer: one tenant cannot exhaust shared resources.
- Region/zone: regional failures do not spread to other regions.
- Criticality: booking confirmation separated from email notifications.
- Data plane/control plane: user-facing operations do not depend entirely on control-plane APIs.

### 2.1. Dependency Graphs and Failure Domains

Draw a dependency graph to identify components capable of failure propagation:

~~~mermaid
flowchart LR
    U["Client"] --> G["API Gateway"]
    G --> B["Booking service"]
    B --> I["Inventory DB"]
    B --> P["Payment API"]
    B --> N["Notification"]
    B --> S["Search"]
    N --> Q["Message queue"]
    Q --> W["Notification worker"]
    S --> IDX[("Search index")]
~~~

In this example, notification usually does not belong on the synchronous booking confirmation path. Notification intent can be written to an outbox/queue after the booking commits so a payment/search outage does not fail bookings. Inventory DB and payment may be more critical dependencies, yet payment can also be coordinated via pending states and sagas instead of holding requests open indefinitely.

### 2.2. Criticality Classification

| Feature category | When dependency fails | Desired behavior |
| --- | --- | --- |
| Booking/inventory invariants | Must never create invalid bookings | Reject/hold safely in pending state |
| Payment capture | Must never assume funds were captured | UNKNOWN state and reconciliation |
| Search recommendations | Experience may degrade | Cache/stale results or omit secondary section |
| Notification emails | Can be sent late | Queue and bounded retries |
| Analytics dashboards | Data can be delayed | Display last-updated timestamp and backlog |
| Admin exports | Can be deferred | Dedicated queue, quotas, status tracking |

Not every feature needs the same availability level. Degradation design must rest on the business impact if that step is skipped or delayed.

## 3. What Is the Bulkhead Pattern?

Bulkhead comes from watertight compartments in a ship: if one compartment floods, others keep floating. In software, bulkheads partition resources or processing capacity into bounded compartments so a failure in one workload does not consume all shared capacity.

~~~mermaid
flowchart TB
    API["Application"] --> B1["Interactive pool"]
    API --> B2["Payment dependency pool"]
    API --> B3["Reporting pool"]
    B1 --> D1["Interactive DB/API"]
    B2 --> D2["Payment API"]
    B3 --> D3["Reporting DB"]
~~~

If reporting slows down, reporting's dedicated pool can fill up while interactive requests retain capacity. That is the core benefit: **limiting blast radius**.

### 3.1. Thread/Concurrency Pool Bulkheads

Each dependency or workload class has its own concurrency limit. When a dependency slows down, only the pool assigned to that dependency saturates. Other dependencies do not compete for the same entire thread pool.

Example:

| Pool | Maximum concurrent calls | Purpose |
| --- | ---: | --- |
| Inventory calls | 24 | Check/reserve inventory |
| Payment calls | 12 | Call payment provider |
| Search calls | 20 | Search queries |
| Reporting jobs | 4 | Heavy reports |
| Notification | Async queue | Avoid blocking main API |

Numbers must derive from downstream capacity, traffic profiles, and SLOs. Do not split thread counts evenly by guesswork.

### 3.2. Connection Pool Bulkheads

An application can use separate JDBC pools for reporting and transactional paths, or cap concurrency per workload. If reporting runs heavy queries, it must not consume all connections needed by booking transactions.

However, both pools still connect to the same database. Total connections must stay within the connection budget; application-level bulkheads do not automatically isolate database CPU, I/O, or locks. Read replicas, workload groups, or separate databases may be needed for stronger isolation.

### 3.3. Queue/Worker Bulkheads

Separate queues or consumer concurrency for heavy jobs and critical jobs:

- Interactive event queues get latency priority.
- Export/report queues get low concurrency.
- Payment reconciliation queues have dedicated retention and alerts.
- Notifications can tolerate delay and process using remaining throughput.

If all jobs share one FIFO queue, a tenant or workload with many messages can cause head-of-line blocking. Separating queues improves isolation but increases the number of components to observe and manage.

### 3.4. Tenant Bulkheads

In multi-tenant platforms, you can apply:

- Per-tenant rate limits and concurrency caps.
- Weighted fair queueing by service tier.
- Per-tenant job quotas and storage quotas.
- Dedicated worker/database pools for special tenants.
- Shards/partitions by tenant group.
- Per-tenant circuit breakers when calling tenant-specific dependencies.

You do not need physical pools for every single tenant. With tens of thousands of tenants, separate pools/brokers/resources per tenant become unmanageable. Shared limiters and schedulers with fairness, quotas, and tiered isolation can be used instead.

### 3.5. Region or Availability Zone Bulkheads

Regions or zones can have dedicated compute, networking, and database endpoints. Regional bulkheads prevent a regional DNS, egress, or dependency failure from impacting the entire deployment. Avoid letting shared control planes, secret services, or global databases become a common failure point.

## 4. Sizing Bulkheads

A bulkhead that is too small rejects/throttles requests even when downstream still has capacity. A bulkhead that is too large fails to limit blast radius. Sizing must come from downstream capacity and total budgets.

### 4.1. Estimating Concurrency via Little's Law

Under steady-state conditions:

~~~text
Concurrent calls ≈ Arrival rate × Average service time
~~~

For example, the payment API receives 80 calls/second with an average service time of 150 ms:

~~~text
80 calls/s × 0.15 s = 12 concurrent calls
~~~

If p99 rises to 2 seconds, instantaneous concurrency can spike much higher. Use the average for an initial estimate, then benchmark against duration distributions, bursts, and tail latency.

### 4.2. Determining Capacity Budgets

Suppose the payment provider allows 100 concurrent requests for the organization's account, and another service uses 30 of them. The booking service should only be allocated its agreed share—say 50 concurrent—leaving headroom for retries/reconciliation. Local bulkheads must be multiplied by application replicas and deployment regions.

~~~text
Fleet concurrency ceiling
  = Instance count × Per-instance bulkhead limit
~~~

If 8 pods each have a semaphore limit of 20, total calls can reach 160. If the provider only allows 100, local bulkheads are insufficient; you need a distributed limiter, proxy/gateway quota, or per-replica/region budget allocation.

### 4.3. Queue Length and Queue Timeout

Bulkheads are not just about concurrency. Unbounded wait queues turn overload into huge latency and memory growth.

Specify:

- Maximum pending tasks.
- Maximum wait time.
- Rejection policy when full.
- Priority and fairness.
- Deadline propagation.
- Cancellation when the caller no longer needs the result.

For interactive requests, failing fast with retry-after guidance is often better than holding requests past their deadline.

## 5. What Is a Circuit Breaker?

A circuit breaker stops an application from repeatedly calling a failing or overly slow dependency. Instead of every request waiting for a long timeout, the breaker opens and fails fast or returns a fallback for a duration. Afterward, it allows a few probes to test if the dependency has recovered.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Failure/slow-call threshold reached
    Open --> HalfOpen: Wait duration elapsed
    HalfOpen --> Closed: Probe successes meet policy
    HalfOpen --> Open: Probe failure / threshold breached
~~~

Three primary states:

- **Closed:** calls pass through; the breaker records successes/failures/slow calls over a measurement window.
- **Open:** calls are blocked immediately without calling the dependency; returns a fallback or controlled error.
- **Half-Open:** allows a limited number of probes through to test the dependency; outcomes decide whether to close or re-open.

Circuit breakers typically operate per dependency and sometimes per operation class. Do not use a single application-wide breaker if endpoints have different error profiles and SLOs.

## 6. Circuit Breaker Parameters

| Parameter | Meaning | Design question |
| --- | --- | --- |
| Failure rate threshold | Error rate that trips the breaker | How many errors across how many calls? |
| Slow call duration threshold | Duration considered a slow call | Which deadline does this threshold match? |
| Slow call rate threshold | Slow-call percentage that trips the breaker | What tail latency signals overload? |
| Sliding window size | Number of calls or time window tracked | How should low traffic handle windows? |
| Minimum number of calls | Minimum sample size before evaluating | Avoid tripping on a single isolated error |
| Open state duration | Blocking duration before probing | How long does the dependency need to recover? |
| Permitted half-open calls | Number of probes allowed | Low enough to prevent a recovery storm? |
| Exception/result classifier | Which errors count as failures | Should business 4xx errors trip the breaker? |

Thresholds must be grounded in baselines and dependency contracts. For instance, 50% errors over at least 20 calls in 30 seconds can be a starting point for a high-traffic service; it is not a universal constant.

### 6.1. Do Not Count All Error Responses Equally

For example:

- HTTP 503 or connection reset from a dependency: usually a technical failure.
- Timeout: failure or slow call.
- HTTP 429: overload/rate limiting; may need backoff and a separate breaker.
- HTTP 400 from invalid input: usually does not indicate a broken dependency.
- HTTP 401 from wrong credentials: likely a configuration/identity incident, not necessarily a transient failure.
- Business rejection like "no rooms available": not a dependency availability failure.

If every HTTP 4xx/5xx counts identically, the breaker can trip on business errors or invalid client input. Define an explicit exception/result classifier.

### 6.2. Sliding Windows

Evaluation can count the latest N calls or the latest time duration. Count-based windows fit steady traffic; time-based windows reflect error rates over time but need minimum call counts to prevent tiny sample sizes.

Low traffic needs different rules: a breaker should not trip on a single failed call and immediately close on timeout without reliable probes.

## 7. Circuit Breakers Do Not Replace Timeouts

Without timeouts, requests can hang for a long time before the breaker even sees a failure or slow call. Timeouts bound a single call; circuit breakers control whether to keep sending calls.

~~~mermaid
flowchart LR
    R["Incoming request"] --> CB["Circuit breaker"]
    CB --> T["Dependency timeout"]
    T --> D["Dependency"]
    CB --> F["Fallback / controlled error"]
~~~

Timeouts must be shorter than the caller's overall deadline and match the SLO. For example, with a 2-second request deadline and a 500 ms dependency budget, never let a payment call hold the request for 10 seconds.

### 7.1. Timeout Budgets Across Chains

If a request calls three dependencies sequentially, total duration can equal the sum of timeouts plus internal processing. Allocate the budget:

~~~text
Total request deadline
  = Internal processing budget
  + Dependency A budget
  + Dependency B budget
  + Persistence/response budget
~~~

For parallel calls, latency is the slowest branch plus overhead, yet each branch still consumes resources. Once the deadline expires, cancel work where possible to stop useless operations from continuing.

## 8. Retries, Backoff, and Circuit Breakers

Retries help with transient failures, yet unbounded retries can pile load onto a struggling dependency. Combining retries and breakers requires clear ordering and budgets.

### 8.1. Exponential Backoff with Jitter

~~~text
delay(attempt)
  = min(maxDelay, baseDelay × 2^attempt) + randomJitter
~~~

Backoff spaces out attempts; jitter prevents many clients from retrying in lockstep. Cap both attempts and total elapsed time against the deadline. Never retry permanent errors like validation failures or permission denied.

### 8.2. Retry Budgets

Cap retries as a ratio of original requests or via a service-wide budget. When the retry budget is spent, return a controlled error or queue the work if the business permits.

Do not retry simultaneously at every layer. If the client retries 3 times, the API retries 3 times, and the downstream service retries 3 times, one operation can generate up to 27 calls. Designate one retry owner per dependency or propagate retry budgets/deadlines across the chain.

### 8.3. Idempotency

Retrying a write operation can create duplicate side effects if the first response was lost after commit. Use idempotency keys, unique business keys, conditional updates, or reconciliation. Circuit breakers do not resolve ambiguity around already-committed transactions.

## 9. Combining Bulkheads and Circuit Breakers

The two patterns serve distinct roles:

| Pattern | Question addressed | Primary effect |
| --- | --- | --- |
| Timeout | How long can one call wait? | Caps resource hold duration |
| Bulkhead | How many calls can run concurrently? | Limits blast radius |
| Circuit breaker | Should we keep calling the dependency? | Stops sending traffic to a failing dependency |
| Rate limiter | Maximum request rate? | Protects capacity and entitlements |
| Retry budget | How much retrying is allowed? | Limits retry amplification |
| Backpressure | How should producers slow down? | Smooths traffic flow |
| Load shedding | Under overload, which traffic gets dropped? | Preserves capacity for critical workloads |
| Queue | Can work be deferred? | Absorbs bursts and decouples processing time |

A typical flow might be: request enters rate limiter → acquires bulkhead slot → checks circuit breaker → executes call with timeout → bounded retry if policy permits → returns result/fallback. Exact ordering depends on the library and how concurrency is counted; check whether slots remain held across retries.

### 9.1. Resilience4j Configuration Example

Illustrative configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      paymentProvider:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
  timelimiter:
    instances:
      paymentProvider:
        timeoutDuration: 600ms
  bulkhead:
    instances:
      paymentProvider:
        maxConcurrentCalls: 12
        maxWaitDuration: 50ms
~~~

Values must be tuned to traffic, provider quotas, latency baselines, and timeout budgets. Depending on library version/module, configuring TimeLimiter, thread-pool bulkheads, and circuit-breaker decorators may differ. Verify the exact library version and run integration tests.

### 9.2. Semaphore vs. Thread-Pool Bulkhead?

- **Semaphore bulkhead:** limits concurrent calls on the calling thread. Minimal thread switching; suits blocking calls if caller thread budgets are managed.
- **Thread-pool bulkhead:** uses a dedicated executor/thread pool with a bounded queue. Isolates workload threads but adds threads, context switching, and queuing; requires timeout/rejection policies.

Do not create large thread pools for every dependency. Total threads per instance and across the fleet must still fit compute capacity.

## 10. Fallbacks and Graceful Degradation

When a breaker is Open, the application must decide what to return. Valid fallbacks depend on the business:

- Search can return cached results with a last-updated timestamp.
- Recommendations can be skipped in favor of default content.
- Notifications can be queued for later delivery.
- Analytics can display stale data with a freshness marker.
- Bookings can return a pending state or temporarily withhold confirmation.
- Payments must never report "success" merely because the provider timed out.

### 10.1. Fallbacks Must Preserve Business Invariants

Fallbacks must never turn technical errors into false success. For example, an unresponsive inventory service does not mean rooms are available. A payment timeout means neither success nor failure; the state may be UNKNOWN and requires querying/reconciliation.

### 10.2. Cache Fallbacks

Caches can retain recent data while a dependency is unavailable. Specify:
- Which data is allowed to be stale?
- Maximum staleness duration?
- Are timestamps and source markers shown?
- Which data must never drive write decisions?
- What happens on cache miss while the breaker is Open?

Cache fallbacks fit reference data; never use a stale inventory snapshot to confirm a booking if it risks overselling.

### 10.3. Queue Fallbacks

If an operation can run asynchronously, durably record intent in an outbox/queue and return Accepted/Pending. Provide a job ID, lookup status, retry policy, business deadline, and DLQ. Return Accepted only after intent is durably persisted.

## 11. Bulkheads and Multi-Tenant Isolation

In multi-tenant SaaS, a large tenant can generate API bursts, exports, or queries. Bulkheads can partition concurrency by tenant group, service tier, or workload class.

~~~mermaid
flowchart TB
    T1["Tenant A requests"] --> L["Tenant-aware limiter"]
    T2["Tenant B requests"] --> L
    T3["Tenant C requests"] --> L
    L --> QA["Queue / pool A"]
    L --> QB["Queue / pool B"]
    L --> QC["Queue / pool C"]
    QA --> W["Shared worker capacity"]
    QB --> W
    QC --> W
~~~

A fair scheduler must stop a tenant with many messages from starving workers. Use weighted fair queues, per-tenant concurrency caps, or tier-based reservations. At high tenant counts, map tenants into shards/queue groups rather than creating a dedicated queue and pool per tenant.

### 11.1. Per-Tenant Circuit Breakers

If each tenant calls its own integration endpoint, per-tenant breakers prevent tenant X's broken endpoint from impacting other tenants. However, if all tenants share a single provider endpoint, overly granular breakers create excessive state and miss provider-wide outages.

Key breakers by actual failure domain: provider-wide, tenant-specific endpoint, region, or operation class. Do not key by tenant ID just because it exists.

## 12. Fault Isolation in Databases and Networks

### 12.1. Databases

- Separate transactional and reporting pools.
- Enforce statement timeouts/lock timeouts.
- Cap query concurrency and connection budgets.
- Offload analytical workloads to read replicas/warehouses.
- Partition workloads by database role/resource group where engine-supported.
- Avoid long transactions and holding locks across external I/O.

Application bulkheads do not stop a CPU-heavy or lock-heavy query from degrading the whole database. Isolate at the DB engine or physically separate workloads when risk is high enough.

### 12.2. Networks and Dependencies

- Separate subnets/security groups by workload and dependency.
- Size connection/egress quotas and DNS capacity appropriately.
- Set explicit connect/read/write timeouts.
- Avoid making all services depend on a single NAT/proxy.
- Use multi-AZ endpoints or redundant paths where needed.
- Scope circuit breakers by endpoint/region when failure domains differ.
- Monitor connection resets, retransmissions, DNS errors, and TLS handshake latency.

Network segmentation aids security and isolation, but does not automatically provide resilience. A single centralized proxy can become a new failure domain without HA.

## 13. When Circuit Breakers Are Misconfigured

Circuit breakers themselves can cause outages when thresholds or scopes are wrong.

| Mistake | Consequence | Adjustment |
| --- | --- | --- |
| Minimum calls too low | Trips on a couple of random errors | Raise sample threshold, check traffic |
| Window too long | Reacts slowly to new outages | Tune to rate of change |
| Threshold too sensitive | Breaker flapping | Use hysteresis and probe policies |
| No exception classification | Business errors trip the breaker | Count only relevant dependency errors |
| Open duration too long | Dependency recovers while traffic stays blocked | Half-open probes and recovery monitoring |
| Too many concurrent probes | Recovery storm | Cap half-open calls |
| App-wide breaker | One broken endpoint blocks healthy endpoints | Split by failure domain |
| No clear fallback | Confusing errors or fake success | Define degraded behavior |
| Unbounded retries before breaker | Breaker struggles to protect dependency | Retry budgets and sensible timeouts |
| Local-only breaker per pod | Every pod probes the dependency together | Probe jitter or shared coordination if needed |

### 13.1. Breaker Flapping

If a breaker repeatedly flips Open/Closed because a dependency recovers briefly and fails again, probe traffic can destabilize the provider. Tune open duration, half-open permitted calls, slow-call thresholds, and sampling windows. Inspect state transitions alongside dependency metrics.

### 13.2. Local vs. Distributed Breakers

A local breaker inside each instance is simple and needs no coordination. With 50 pods, however, each pod opens/closes on its own samples, which can generate more total probes than expected.

Distributed breakers share state to coordinate across the fleet, yet introduce extra dependencies, consistency issues, and failure modes. Usually start with local breakers using low half-open concurrency, jitter, and global rate limits; add distributed coordination only with measured justification.

## 14. Observing Bulkheads, Breakers, and Cascading Failures

Track not only error counts, but also resource states and business impact.

| Group | Metrics | Meaning |
| --- | --- | --- |
| Bulkhead | Active calls, available permits, rejected calls, queue depth/wait | Is the pool saturating? |
| Circuit breaker | State, failure rate, slow-call rate, not-permitted calls, transitions | Is the dependency blocked? |
| Dependency | Latency p50/p95/p99, timeouts, 5xx/429, connection errors | How healthy is the dependency? |
| Application | Thread pools, connection pools, CPU, memory, event loop lag | Are app resources exhausting? |
| Queue | Oldest message age, backlog, retries, DLQ | Is work being delayed? |
| Business | Booking success, payment outcomes, pending/unknown counts | Are users completing workflows? |
| Recovery | Half-open successes, reconnect rate, replay rate | Has the dependency recovered stably? |

### 14.1. Logs and Traces

Record service, dependency, operation class, breaker state, retry attempt, timeout reason, bulkhead rejection, tenant tier, and correlation ID. Avoid logging sensitive payloads or tokens.

Traces should distinguish:
- Time waiting for a bulkhead slot.
- Time waiting for a connection/pool.
- Network/connect time.
- Dependency execution time.
- Retry delay.
- Fallback duration.

Seeing only total latency makes it hard to tell whether slowness came from queues, app pools, or dependencies.

### 14.2. Impact-Based Alerts

- Breaker remains Open longer than threshold.
- Bulkhead rejections exceed baseline.
- Oldest queue age exceeds business deadline.
- Dependency p99 rises and slow-call rate breaches threshold.
- Payment UNKNOWN or reconciliation backlog increases.
- Multiple services time out against the same endpoint.
- Half-open probes fail repeatedly.
- Thread/connection pool wait queues grow despite low CPU.

Every alert needs an owner and runbook. Avoid paging on-call for isolated single breaker transitions without user impact; aggregate by dependency and business SLOs.

## 15. SLOs and Quality Scenarios

The values below are illustrative examples only. Replace them with product SLOs and verified capacity.

| ID | Scenario | Expected response | Illustrative measure |
| --- | --- | --- | --- |
| QA-REL-01 | Payment API times out continuously | Breaker Opens; requests do not hold threads long | Opens within 30s after threshold met; booking API meets deadline |
| QA-REL-02 | Reporting worker overloaded | Reporting pool fills while interactive pool retains capacity | Interactive p95 stays within budget |
| QA-REL-03 | Dependency begins recovering | Half-open probes bounded; breaker closes only after sufficient success | No probe burst; probes satisfy policy |
| QA-REL-04 | Notification provider fails | Bookings still commit; notifications queued | Booking success independent of email provider |
| QA-REL-05 | Tenant creates export burst | Fair scheduler/tenant cap protects other tenants | Other tenants' interactive SLOs remain met |
| QA-REL-06 | Simultaneous retries and timeouts | Retry budget caps amplification | Max attempts per policy; stays within provider quota |
| QA-REL-07 | Payment response lost after commit | No blind retry causing duplicate payment | UNKNOWN reconciled; zero duplicate charges in fault test |
| QA-REL-08 | One AZ/proxy fails | Traffic shifts to healthy capacity per policy | RTO and error budget met; no recovery storm |

### 15.1. Technical SLOs vs. Business SLOs

An Open circuit breaker may raise rejected requests while saving the overall system from collapse. Therefore monitor both:
- Endpoint availability/latency.
- Rate of bookings/payments completing accurately.
- Fallback and stale-data rates.
- Queue job completion times.
- Count of UNKNOWN operations needing reconciliation.

Do not declare a breaker "working properly" a success if users cannot complete core business workflows for extended periods.

## 16. Fault Injection and Chaos Testing

A resilience design is trustworthy only after failure modes are tested. Tests need hypotheses, blast radius limits, stop conditions, and recovery criteria.

### 16.1. Tests to Include

1. Increase dependency latency 5x briefly.
2. Force dependency to return 5xx/429 at a defined rate.
3. Sever network between application and dependency.
4. Slow down the database to test pool exhaustion.
5. Saturate the reporting bulkhead and verify the interactive path keeps serving.
6. Stop workers while queue backlog grows.
7. Trip the breaker Open and recover via Half-Open.
8. Inject a traffic burst right as a dependency recovers.
9. Send duplicate requests/retries after a side effect commits.
10. Fault one tenant or shard and inspect other tenants.
11. Fail an AZ or proxy in an appropriate staging/game-day environment.
12. Slow down the logging/metrics backend to verify observability does not cause secondary outages.

### 16.2. Evidence to Record

- Arrival rate, concurrency, and latency.
- Active permits, rejections, and pending queues.
- Breaker state transitions and timestamps.
- Dependency status and recovery duration.
- Thread/connection pool utilization.
- Business successes, pending counts, and duplicate counts.
- Blast radius: which tenants/workloads/regions were impacted.
- Test cost and generated retry/egress volume.

Never run unbounded chaos experiments in production. Start in staging or canary; production experiments require clear scope, guardrails, and accountable owners.

## 17. Case Study: Booking Service Protecting the Payment Dependency

### 17.1. Context

The Booking service runs 12 pods on Kubernetes. Each pod accepts up to 100 concurrent requests. The payment provider normally has p95 latency of 250 ms, occasionally slowing to several seconds. The Booking API has a 2-second deadline. Notifications and reports run in the background.

Problem: when payment slows down, Booking service threads are held, HTTP client pools exhaust, and request retries amplify payment calls. Notifications/reports share the same executor and get impacted too.

### 17.2. Redesign

- Create a dedicated payment semaphore bulkhead capping fleet concurrency within provider quota.
- Set a 600 ms payment call timeout on the request path.
- Configure a circuit breaker evaluating failures/slow calls with a minimum sample and small half-open probes.
- Cap retries per policy for transient errors only; use idempotency keys on payment operations.
- Write notification intent to an outbox after booking commit, processed by workers on a separate queue.
- Run reporting on a dedicated executor/queue with low concurrency.
- On ambiguous payment timeouts, leave bookings in `PAYMENT_PENDING/UNKNOWN` and reconcile by querying the provider.
- Dashboards track breaker state, rejected calls, payment p99, unknown counts, and queue age.

~~~mermaid
flowchart TB
    U["Client"] --> API["Booking API"]
    API --> B["Payment bulkhead"]
    B --> CB["Payment circuit breaker"]
    CB --> T["600 ms timeout"]
    T --> PAY["Payment provider"]
    API --> TX["Booking transaction"]
    TX --> DB[("Booking DB")]
    TX --> O[("Outbox")]
    O --> NQ[("Notification queue")]
    NQ --> NW["Notification worker"]
    RQ[("Reporting queue")] --> RW["Reporting worker"]
~~~

### 17.3. Behavior When Payment Fails

If the provider slows down or fails, the breaker opens once thresholds are met. The Booking API stops sending unbounded calls. Clients receive a pending/temporarily unavailable status per contract; requests never report payment success. When the provider shows signs of recovery, limited probes pass through. If probes meet policy, the breaker gradually closes; ambiguous payment operations are resolved separately via reconciliation.

### 17.4. Evaluating Outcomes

Measure before and after:
- Booking request p95/p99.
- Payment concurrent calls and timeouts.
- Bulkhead rejections.
- Breaker Open duration.
- Payment UNKNOWN/duplicate counts.
- Notification completion lag.
- Reporting completion.
- CPU/thread/connection pool utilization.

A design passes only when payment failures do not exhaust capacity for notifications/reports or the booking API, and when recovery causes no secondary burst.

## 18. TCO and Trade-Offs

Bulkheads and circuit breakers add configuration, telemetry, testing, and sometimes dedicated compute. In return, they reduce cascading outages, preserve capacity for critical features, and cut wasted retries.

Costs to account for:
- Dedicated pools/threads/executors/queues and headroom.
- Proxies/gateways/limiters/distributed coordination if used.
- Observability for breaker states and per-dependency metrics.
- Fallback caches or storage.
- Queue retention, replay, and reconciliation.
- Failure/chaos testing and runbook operations.
- Idle capacity from isolation or reserved concurrency.

~~~text
Resilience investment value
  = Expected avoided outage impact
    + Reduced retry/overload cost
    + Preserved critical business throughput
    - Added infrastructure and operational cost
~~~

Not every benefit converts neatly into exact dollars. Tie investments to business impact: protected bookings, reduced downtime, fewer impacted tenants, and preserved error budgets.

## 19. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sharing one pool for all dependencies | One slow dependency consumes all threads | Bulkhead by failure domain |
| Sizing bulkhead limits per pod only | Fleet exceeds downstream quota | Compute total concurrency and allocate global budget |
| Unbounded queues | Memory/backlog grow indefinitely | Bounded queues, deadlines, and load shedding |
| Circuit breaker without timeouts | Calls hang before breaker reacts | Explicit deadline-aligned timeouts |
| Retrying at every layer | Retry amplification | Designate retry owner and budget |
| All errors trip the breaker | Business rejections block the dependency | Classify exceptions/results |
| Too many probes in half-open | Recovery storm | Cap probes, add jitter |
| Fallback returns fake success | Violates business invariants | Pending/UNKNOWN or reference-only fallback |
| Bulkheads only in app tier | DB/queue/network remain shared bottlenecks | Isolate at the proper resource layer |
| Breaker state unobservable | Hard to diagnose errors and operate | Dashboards, logs, transition alerts |
| Not testing retry side effects | Duplicate payments/orders | Idempotency and reconciliation |
| Using circuit breaker as rate limiter | False blocking or missing burst protection | Separate breakers from rate limiters |

## 20. Hands-On Exercise

An e-commerce platform's checkout calls inventory, payment, tax, and notification. The API deadline is 2 seconds. Payment occasionally slows to 4 seconds; notifications can lag 5 minutes; the tax provider enforces 50 requests/second. Reporting jobs run in the same cluster and once exhausted the thread pool.

Complete the following:

1. Draw the dependency graph and identify failure domains.
2. Classify which dependencies belong on the critical path and which can move asynchronous.
3. Design bulkhead concurrency for inventory, payment, tax, reporting, and notification.
4. Calculate total fleet concurrency across 10 pods with your proposed limits; compare against the 50 req/s tax quota.
5. Allocate timeout budgets per dependency so the total fits within the 2-second deadline.
6. Propose circuit breaker thresholds, minimum calls, open duration, and half-open probes; explain how to benchmark them.
7. Design retry/backoff/jitter and retry ownership; calculate amplification risk if two layers both retry.
8. Define safe fallbacks for inventory, payment, tax, and notification.
9. Design UNKNOWN states and reconciliation for payment timeouts after commit.
10. Build dashboards/alerts by dependency, bulkhead, breaker, and business outcome.
11. Write a fault injection plan for payment latency, tax 429s, reporting overload, and worker outages.
12. Evaluate shared vs. isolated pools by cost and blast radius; write an ADR.

**Self-Assessment Hint:** A strong solution identifies held resources, isolation boundaries, total fleet capacity, timeout/retry budgets, invariant-safe fallbacks, and verification via fault injection.

## 21. Pre-Production Checklist

- [ ] Dependency graphs and failure domains exist for critical flows.
- [ ] Criticality and degraded behavior are defined for each feature.
- [ ] Bulkheads cap concurrency, queue length, and wait time.
- [ ] Capacity is sized fleet-wide, including autoscaling and deployment overlap.
- [ ] Isolation exists by dependency/workload/tenant where needed.
- [ ] Circuit breakers classify errors accurately and set sliding windows/minimum calls.
- [ ] Closed/Open/Half-Open policies, probe caps, and recovery jitter are defined.
- [ ] Timeout budgets propagate across the request path with proper cancellation.
- [ ] Retries have an owner, maximum attempts, backoff, jitter, and budget.
- [ ] Write operations have idempotency and reconciliation for ambiguous outcomes.
- [ ] Fallbacks do not violate business or security invariants.
- [ ] Queues/backlogs define capacity, retention, DLQ, and backpressure.
- [ ] Dashboards monitor pools, breakers, dependencies, and business SLOs.
- [ ] Alerts have owners, severity, and runbooks.
- [ ] Outages, latency, overload, duplicates, and recovery storms have been fault-injected.
- [ ] TCO, operational overhead, and shared bottleneck risks have been evaluated.

## 22. Well-Architected Review

| Pillar | Questions when reviewing bulkheads and circuit breakers |
| --- | --- |
| **Operational Excellence** | Are breaker states, resource saturation, runbooks, game days, and recovery measurable/rehearsed? |
| **Security** | Does tenant/dependency isolation prevent context, credential, or data leakage across failure domains? |
| **Reliability** | Do bulkheads, timeouts, breakers, retry budgets, and fallbacks contain blast radius and recover safely? |
| **Performance Efficiency** | Do pool sizes, concurrency, queues, and probes meet SLOs without overprovisioning? |
| **Cost Optimization** | Do isolation capacity, proxies, queues, and observability deliver commensurate value? |
| **Sustainability** | Are wasted retries, long-waiting compute, and excessive idle resources avoided? |

**Conclusion:** Bulkheads limit how much resource a workload can claim; circuit breakers halt calls to failing dependencies to protect the rest; fault isolation bounds blast radius by dependency, tenant, workload, or region. They work effectively only when paired with timeouts, retry budgets, backpressure, idempotency, and business-safe fallbacks. Measure fleet-wide capacity, test failure and recovery states, and tune against SLOs and Well-Architected trade-offs.
