# Building a Latency Budget for End-to-End Flows

Users perceive performance through the time from performing an action until they receive a useful result. An API may respond quickly at each individual service, yet the overall flow remains slow because the gateway, authentication, network, database, cache, queue, or external services accumulate latency. Optimizing an isolated endpoint is not enough without understanding the total time of the user journey and which parts are consuming the budget.

A **latency budget** is the time limit allocated to an entire request or business flow, which is then divided into targets for each component and a safety reserve. It turns requirements like "the checkout page must be fast" into measurable targets: maximum end-to-end duration, deadlines for each dependency, queue wait, database work, serialization, and response transfer. The budget also helps decide whether to call a secondary service synchronously, offload work to the background, use caching, or reject early when time has run out.

A good budget must be grounded in user experience, SLOs, and actual latency distributions. You should not add averages together and conclude a request will meet p95; tail latency at each hop, concurrency, retries, and load correlation can make the end-to-end flow much slower. You need to define deadlines, measure with traces, analyze percentiles, and adjust based on evidence.

This lesson belongs to the **Performance** section of the cloud architecture design module. The focus is on building a latency budget for end-to-end flows, connecting user goals with network, compute, data, and operations architecture, while balancing performance, reliability, security, scalability, and cost under Well-Architected thinking.

After this lesson, you will be able to:

- Identify user journeys, SLIs, and appropriate latency SLOs.
- Decompose end-to-end duration into hops, queues, and processing stages.
- Allocate deadlines for gateways, services, databases, and external dependencies.
- Distinguish between average latency, percentiles, tail latency, and wait time.
- Propagate deadlines across services and control retries/concurrency.
- Measure latency using tracing, metrics, logs, and load tests.
- Locate bottlenecks, adjust budgets, and design degraded paths.

## 1. Start from the User Experience

A latency budget should not start with the question "how many milliseconds does the database get?". Start with the action the user needs to complete and the moment the result becomes useful.

For example:

- Opening an appointment list and seeing the data.
- Searching for products and receiving an interactive results page.
- Confirming a booking and knowing whether the booking has been saved.
- Paying and receiving a clear status.
- Downloading a report and receiving a file or an operation ID.

Different actions have different time sensitivities. Interactive search pages generally need faster responses than large reports. Asynchronous tasks may not need to finish within the request, but they must have a processing deadline and a status for the user to track.

### Defining Latency SLIs and SLOs

- **SLI (Service Level Indicator):** a metric measuring user experience, such as the percentage of requests finishing within 400 ms.
- **SLO (Service Level Objective):** an internal target for an SLI, such as 99% of search requests completing within 400 ms over a measurement window.
- **Deadline:** the latest point in time at which a request or processing step still has value.
- **Latency budget:** the total limit and per-step allocation used to achieve that objective.

Illustrative SLO examples:

| User journey | Latency objective | Where to measure |
| --- | --- | --- |
| Open booking page | p95 under 500 ms | API gateway to complete response body |
| Search catalog | p95 under 300 ms | Search API, excluding client-side rendering time if the SLO is backend-only |
| Confirm booking | p99 under 1.2 seconds | From when the API receives the request until the commit result or valid pending status is recorded |
| Send confirmation email | 95% within 2 minutes | From event acceptance to provider acknowledgement |
| Daily report | Complete before 08:00 | From scheduled trigger to dataset/report publish |

These numbers are examples for exercise design, not universal standards. Organizations need to determine SLOs from user research, business criticality, baselines, and the cost of meeting the target.

### Choosing Start and End Points

A measurement must have clear boundaries:

- Client-side latency starts when the user interacts, and may include DNS, TLS, download, and rendering.
- Server-side latency typically starts when the gateway receives the request and ends when the response is sent.
- Business completion may occur later than the response if the operation is accepted for asynchronous processing.

Do not mix these types on the same dashboard. An API with a 200 ms p95 does not mean the user sees content after 200 ms if the frontend still has to fetch additional assets, call other APIs, and render.

## 2. Modeling the End-to-End Flow

Draw the dependency graph before dividing the budget. A request can make sequential calls, parallel calls, or hand off work via a queue. The orchestration pattern determines how latencies add up.

~~~mermaid
flowchart LR
    CLIENT["Client"] --> EDGE["DNS / TLS / Edge"]
    EDGE --> GW["API Gateway"]
    GW --> AUTH["Authentication"]
    AUTH --> APP["Application service"]
    APP --> CACHE["Cache"]
    CACHE -->|Miss| DB["Database"]
    CACHE -->|Hit| RESP["Response assembly"]
    DB --> RESP
    APP --> OPT["Optional service"]
    OPT --> RESP
    RESP --> CLIENT
    APP --> Q[("Async queue")]
    Q --> WORKER["Background worker"]
~~~

### Components That Commonly Consume Latency

| Component | Time to measure | Example causes of slowness |
| --- | --- | --- |
| Client/network | DNS, connect, TLS, RTT, transfer | New connections, cross-region distance, large payloads |
| Edge/gateway | Queue wait, auth, routing, rate limit | Overload, policy lookup, cold connections |
| Application | Queue/thread wait, CPU, lock, serialization | Exhausted thread pool, GC, synchronous call chain |
| Cache | Network RTT, command latency, miss | Hot keys, connection limits, eviction |
| Database | Pool wait, query, lock, commit | Scans, contention, slow storage, connection exhaustion |
| External API | Connect, server processing, response | Provider latency, quotas, retries, cross-region calls |
| Queue/worker | Publish, queue wait, consume, processing | Consumer lag, backlog, retries/DLQ |
| Response | Aggregation, compression, serialization, transfer | Large JSON, compression CPU, client bandwidth |

Not every component lies on the critical path. A queue that sends emails after the response has been returned has its own latency and must not be added to the booking API's latency, though it needs its own SLO.

### Identifying the Critical Path

The critical path is the dependency chain that determines when the request can complete. If two dependencies run in parallel, the total time for that segment is roughly the slowest branch plus aggregation overhead, not the sum of both branches.

For example:

~~~mermaid
flowchart TD
    A["API starts"] --> B["Read booking: 90 ms"]
    B --> C["Parallel calls"]
    C --> D["Customer profile: 70 ms"]
    C --> E["Recommendation: 180 ms"]
    D --> F["Assemble: 35 ms"]
    E --> F
    F --> G["Return response"]
~~~

After reading the booking, two branches run in parallel. The critical path is the 180 ms recommendation branch, plus coordination and assembly time. If recommendations are not essential for the use case, you can set a short deadline or skip that branch when it is slow.

## 3. Decomposing the End-to-End Budget

Suppose an API has a p95 latency objective of 500 ms. An initial allocation might look like this:

| Stage | Budget | Notes |
| --- | ---: | --- |
| Gateway, auth, and routing | 45 ms | Includes queue wait at the gateway |
| Application queue and processing | 60 ms | Excludes dependency call time |
| Cache/database access | 130 ms | Includes pool wait and query |
| Business dependency | 90 ms | One or more calls on the critical path |
| Response assembly/serialization | 45 ms | Mapping, JSON, and compression |
| Network/response margin | 50 ms | Remaining transfer and variability |
| Safety reserve | 80 ms | Tail variation, scheduler, unexpected retries |
| **Total** | **500 ms** | Illustrative target |

You do not have to allocate budgets proportionally or equally across steps. Any dependency with high latency variance, low controllability, or external ownership needs tighter timeouts. The reserve protects the request from components that cannot be fully predicted.

### Allocation Process

1. Set the overall deadline based on user experience and the SLO.
2. List the critical path and parallel calls.
3. Estimate the current p50/p95/p99 of each hop.
4. Allocate budgets to controllable parts and set timeouts for dependencies.
5. Reserve margin for variance, scheduling, and response transfer.
6. Verify the total budget against the sequential/parallel structure.
7. Run load tests and tracing to validate; adjust from measured data.

### Avoid Mis-adding Parallel Branches

For sequential steps:

\[
T_{\mathrm{total}} \approx T_1 + T_2 + \cdots + T_n
\]

For parallel branches starting at nearly the same time:

\[
T_{\mathrm{parallel}} \approx \max(T_1,T_2,\ldots,T_n)+T_{\mathrm{join}}
\]

This is a simplified model. In reality, there are also coordination overhead, queueing, concurrency limits, and correlation between branches.

### A Budget Is Not a Quota for Each Service to Exhaust

If every service uses the full maximum timeout it is allocated, the request can hit the overall deadline. Each step must maintain headroom and stop when the remaining deadline is no longer sufficient for useful work. Do not keep initiating new calls merely because a local timeout has not yet expired.

## 4. Understanding p50, p95, p99, and Tail Latency

Latency is not a single average number. If most requests are fast while a small subset is very slow, users are impacted and percentile SLOs can fail.

| Metric | Interpretation |
| --- | --- |
| p50 | Half of the requests complete faster than or equal to this value |
| p90 | 90% of requests complete faster than or equal to this value |
| p95 | 95% of requests complete faster than or equal to this value |
| p99 | 99% of requests complete faster than or equal to this value |
| p99.9 | Very slow tail, useful for high-volume or critical flows |
| Mean/average | Average; can hide the tail |
| Max | Largest value observed in the sample set; sensitive to sample size/outliers |

### Why Does Tail Latency Compound?

Suppose a request traverses 10 services sequentially. Each service has a 99% probability of finishing within 50 ms. The probability that all 10 services stay within 50 ms, assuming independence, is:

\[
0.99^{10} \approx 90.4\%
\]

Thus, even if each service achieves a p99 of 50 ms, only about 90.4% of requests have all 10 hops within that threshold under the independence assumption. End-to-end requests can exhibit worse percentiles than any individual component.

This is a probabilistic illustration, not a direct formula for computing end-to-end p95 from per-service p95s. Latencies across services can be correlated due to load, networking, or shared dependencies.

### Tail Amplification

The tail can grow sharply due to:

- A slow node or partition in a pool.
- Increasing queue wait when concurrency exceeds capacity.
- Lock contention or noisy neighbors.
- Retries adding extra load right when a dependency is slow.
- One slow parallel branch delaying the entire response.
- Cold starts, autoscaling, or connection establishment.
- Garbage collection, CPU throttling, and storage throttling.

Track percentiles by route, tenant tier, region, and dependency. Do not look only at system-wide percentiles, because they can mask a specific user group or partition experiencing issues.

## 5. Deadline Propagation and Remaining-Time Timeouts

Independent timeouts at each service easily cause total duration to exceed the target. A request with an overall 800 ms deadline but three dependencies each configured with an 800 ms timeout can drag on for several seconds when waited on sequentially.

### Propagating Deadlines

As a request passes through services, propagate an absolute deadline or remaining timeout in a consistent format. Each service computes the remaining budget, subtracting elapsed time and internal overhead.

~~~text
incoming deadline: 12:00:00.800
current time:      12:00:00.310
remaining:         490 ms

local response reserve: 60 ms
dependency call budget: 300 ms
unallocated safety:     130 ms
~~~

For example, the service allocates only 300 ms to the dependency because it needs to keep 60 ms to finalize the response and 130 ms as reserve. If only 50 ms remains, it should not initiate a call that requires a 300 ms timeout.

### Per-Hop Timeouts

- Connect timeout: limits the time to establish a connection.
- Request/read timeout: limits waiting for a response or data.
- Pool-acquisition timeout: limits waiting for a connection/thread.
- Database statement timeout: limits query execution.
- Overall deadline: limits the entire request.

These timeouts must be configured together; one timeout does not replace another. For example, a 2-second HTTP read timeout will not help a request meet a 500 ms SLO.

### Cancellation Propagation

When the caller's deadline expires or the client cancels the request, downstream work should be canceled if safe to do so. Continuing to run queries or call providers after the caller has given up wastes resources and reduces capacity for other requests.

Do not cancel side effects that have already committed or operations that must finish to preserve consistency. Tasks such as payment reconciliation or durable workflows need lifecycles independent of the HTTP client.

### Clocks and Deadline Formats

Absolute deadlines across multiple hosts require attention to clock skew. Within each process, use a monotonic clock to measure durations; propagate deadlines using the platform's standard protocol/runtime mechanism and convert carefully. Never use arbitrary client timestamps as a source of truth for authorization or business expiry.

## 6. Retries, Hedging, and Time Budgets

Retries can recover from transient errors, but they make requests slower and increase load. Only retry when deadline budget remains and safety mechanisms are in place.

### Retry Budget

For a call with a 240 ms budget, two attempts can be made:

| Attempt | Timeout | Backoff | Notes |
| --- | ---: | ---: | --- |
| Attempt 1 | 100 ms | 20 ms | Only retry transient errors |
| Attempt 2 | 100 ms | 0 ms | Stop if remaining deadline is insufficient |
| Reserve | 20 ms | — | Reserved for processing the result |

These numbers are illustrative only. Total timeout, backoff, and serialization must be counted within the budget. Retries must not consume all remaining time of the request.

### Retry Rules

- Only retry transient errors such as connection resets or specific 5xx/429 responses per the contract.
- Use exponential backoff and jitter to avoid synchronized retries.
- Limit attempt counts and enforce a per-service retry budget.
- Use idempotency keys for write operations.
- Do not retry validation, authorization, or explicit business errors.
- Avoid stacked retries across layers: gateway retrying service, service retrying database, and SDK retrying as well.

### Hedged Requests

Hedging sends a second copy of a request to another replica when the first request exceeds a latency threshold, then uses the first valid result. It can reduce tail latency for idempotent read operations, but it increases load and can easily trigger a stampede. Only use it when:

- Genuine replica capacity is available.
- The read operation produces no side effects.
- The slower request is canceled once a result arrives.
- There is a cap on hedge rate and extra load is monitored.
- Consistency semantics across replicas are acceptable.

Do not hedge payment writes or booking creation without an appropriate idempotency/coordination protocol.

## 7. Queueing, Concurrency, and Little's Law

A request does not only spend time being processed; it can also wait before being processed. Queueing delay typically rises rapidly as a system approaches its capacity limit.

### Little's Law

In steady state:

\[
L = \lambda W
\]

Where:

- \(L\) is the average number of requests currently in the system.
- \(\lambda\) is the average throughput (requests/second).
- \(W\) is the average time spent in the system (seconds).

For example, 200 requests/second and an average of 0.25 seconds in the system correspond to roughly 50 requests being processed or waiting. If duration rises to 1 second at the same throughput, the average number of concurrent requests rises to about 200, increasing memory, connection, and queue pressure.

Little's Law does not determine maximum capacity on its own; it relates concurrency, throughput, and latency under steady-state conditions.

### Queue Wait Budget

If a request waits 150 ms in a worker queue, that time has already consumed budget even though the CPU has done nothing. Measure:

- Queue depth and oldest item age.
- Queue wait p50/p95/p99.
- Active workers and saturation.
- Reject/drop/backpressure counts.
- Downstream concurrency and connection pool wait.

### Admission Control and Load Shedding

When queues or connection pools exceed thresholds, reject early, throttle, or deprioritize non-essential tasks. Unbounded queueing merely turns overload errors into massive latency and resource exhaustion.

A request should only be admitted if sufficient time and capacity exist to complete it usefully. For long-running tasks, move to a durable async workflow and return an operation ID instead of holding an HTTP connection open.

## 8. Allocating Budgets by Dependency Type

Each dependency has different characteristics and levels of controllability.

| Dependency | What to account for in the budget | Strategy |
| --- | --- | --- |
| Same-region internal service | Gateway/mesh, queue, serialization, and downstream processing | Deadline propagation, connection reuse |
| Cross-region service | RTT, TLS, egress, replication, and retries | Reduce synchronous hops, cache/read models |
| Database | Pool wait, query, lock, commit, network | Query timeouts, indexes, pool sizing |
| Cache | Pool wait, network RTT, hit/miss | Short timeouts, bounded fallbacks |
| External API | Connect, provider processing, quotas, and retries | Tight timeouts, circuit breakers, async when appropriate |
| Message broker | Publish acknowledgement and queue wait | Durable publish, async processing SLOs |
| Object storage | DNS/TLS, upload/download, multipart, and transfer | Streaming, multipart, signed URLs |
| Authentication | Token verification, introspection, or remote policy lookup | Local verification when safe, bounded policy caching |

### Internal Calls Are Not Free

A service in the same VPC still incurs network stack, service mesh, mTLS, load balancing, queueing, and serialization overhead. Calling many small services can increase latency and failure surface. Consider combining queries, bulk endpoints, or read models when they belong to the same transaction/use case and domain boundaries allow.

### External Dependencies

Do not bet your entire budget on a provider's SLA. The organization needs timeouts shorter than the overall deadline, circuit breakers, sensible fallbacks, retry policies, and business states for ambiguous outcomes. For payments, a timeout does not prove the transaction failed; status queries or reconciliation are required.

## 9. Measuring Latency Properly

You cannot manage what you do not measure. Combine metrics, distributed tracing, logs, and synthetic/load tests.

### Metrics

Core metrics:

- Request count and throughput by route.
- Latency histograms for p50/p90/p95/p99.
- Error rate and timeout rate.
- Queue wait and processing duration.
- Connection pool wait/active/idle.
- Cache hit/miss and command latency.
- Database query duration, lock wait, and pool wait.
- CPU, memory, GC, throttling, and network saturation.

Use histograms with buckets aligned to your SLOs. Averages are insufficient for calculating percentiles; avoid computing overall percentiles by averaging per-instance percentiles, as that becomes inaccurate when traffic is unevenly distributed.

### Distributed Tracing

Traces reveal which services a request traverses, which calls are sequential vs. parallel, duration per span, and where the tail originates. Spans should record:

- Service, operation, route template.
- Start/end/duration and status.
- Dependency name and peer region.
- Queue wait, pool wait, or query class when possible.
- Retry attempt and remaining deadline if safe.
- Correlation/request ID.

Do not place secrets or sensitive payloads in span attributes. Use appropriate trace sampling; retain representative samples of errors and slow requests to investigate the tail.

### Client-Side Measurement

If the SLO reflects user experience, also measure DNS, connection, TLS, TTFB, content download, and render/interaction time. Backend tracing cannot see device execution time, mobile networks, or JavaScript bundles.

### Synthetic Monitoring

Run test journeys from selected regions/network vantage points using safe test data. Synthetic tests help detect issues before many users are affected, though they do not replace real-user monitoring.

## 10. Analyzing Bottlenecks and Optimizing Based on Evidence

Once you have traces and percentiles, locate what consumes the most time or drives up the tail.

### Distinguishing Latency Sources

- **Network-bound:** high RTT, frequent handshakes, large payloads, cross-region calls.
- **CPU-bound:** CPU-intensive processing, serialization, compression, or cryptography.
- **I/O-bound:** slow database/storage or limited throughput.
- **Lock/contention-bound:** multiple requests contending on locks, rows, or partitions.
- **Queue-bound:** insufficient workers, threads, or connections.
- **Dependency-bound:** slow downstream provider or service.

### Optimizing by Layer

**Network:** use connection pooling/keep-alive, reduce round trips, co-locate compute near dependencies, transfer only needed payloads, and weigh compression CPU/network tradeoffs.

**Compute:** eliminate unnecessary blocking calls, optimize serialization, reduce allocations, avoid long-held locks, size thread/worker pools to downstream capacity, and measure GC/throttling.

**Database:** inspect query plans, indexes, N+1 queries, lock waits, connection pools, pagination, and data access patterns. Do not raise pool sizes indefinitely, as that can push the database into saturation.

**Cache:** cache repeated reads with appropriate freshness, control stampedes/hot keys, set timeouts and fallbacks; do not cache transactional decisions that require the latest authoritative data.

**Architecture:** reduce sequential hops, parallelize independent work, offload non-synchronous side effects to queues, and use materialized views or read models for aggregated queries.

**Payload:** trim unnecessary fields, use pagination, streaming responses, or compression; measure CPU and network before and after.

### Change One Variable at a Time

Record a baseline, change a single factor, run the same workload, and compare p50/p95/p99, throughput, errors, and cost. If a change improves p50 but degrades p99, understand which subset of requests is affected. Avoid claiming an optimization based on a single small run.

## 11. Capacity, Autoscaling, and Latency Budgets

Autoscaling can add capacity, but it does not react instantaneously. Provisioning instances, containers, JVMs, warming caches, or opening connections can raise latency during scale-out.

### What to Include in the Budget

- Queueing while new capacity is not yet ready.
- Cold starts or image pulls.
- Health/readiness gates before receiving traffic.
- Connection pool warm-up and DNS resolution.
- Cache warm-up or JIT compilation.
- Scale-in draining so in-flight requests are not dropped.

### Scale on the Right Signals

CPU alone may not reflect the bottleneck. A service can be slow due to database pool wait even when CPU is low. Consider request concurrency, queue depth, oldest item age, latency, downstream saturation, and throughput.

### Headroom and Overload

Capacity needs headroom for peaks and failure scenarios. If an availability zone is lost, remaining zones must have enough capacity or enforce admission control. Do not set autoscaling max so high that it opens excessive connections to databases or providers.

### Load Testing

Test under:

- Expected steady-state traffic.
- Peak/burst traffic.
- Ramp-up and ramp-down.
- Dependency slowdowns.
- Loss of a node or zone.
- Cold caches or queue backlogs.
- Tenant hot keys/noisy neighbors.

Measure latency percentiles and error rates alongside throughput; a system can keep latency low by silently dropping requests, so all metrics must be inspected together.

## 12. Designing Deadline-Based Graceful Degradation

When remaining time is low, the application should choose valuable behavior instead of continuing to call every dependency.

Example booking page with a 500 ms overall deadline:

- Booking data is mandatory and prioritized.
- Customer display profile can use a valid snapshot within policy limits.
- Recommendations are optional, with an 80 ms timeout.
- Analytics events are emitted asynchronously.

~~~mermaid
flowchart TD
    A["Request: 500 ms deadline"] --> B["Auth and booking read"]
    B --> C["Remaining budget check"]
    C --> D["Profile call"]
    C --> E["Optional recommendation"]
    E --> F{"Completed within 80 ms?"}
    F -- "Yes" --> G["Include suggestions"]
    F -- "No" --> H["Omit suggestions / degraded flag"]
    D --> I["Assemble response"]
    G --> I
    H --> I
    I --> J["Return before overall deadline"]
    B --> Q["Async analytics event"]
~~~

### Degraded Mode Rules

- Never sacrifice authorization or business invariants to reduce latency.
- Only serve stale data within limits approved by the domain owner.
- Do not confirm a write until the source of truth has committed or durable acceptance is guaranteed per the contract.
- Optional dependencies must have smaller deadlines than the overall request.
- Queue/async paths must have their own SLOs and report pending status.
- Monitor degraded response rates and business outcomes.

### When to Fail Fast?

If the remaining budget is insufficient for useful work or a mandatory dependency cannot respond within the deadline, fail fast with a clear status. Returning an error quickly can be better than waiting for long timeouts, provided retry guidance and idempotency prevent duplicate side effects.

## 13. Practical Example: Latency Budget for Checkout

**Hypothetical context:** An e-commerce platform wants its checkout backend to achieve p95 under 800 ms and p99 under 1.2 seconds under target load. The flow includes an API gateway, authentication, cart, pricing, inventory, order database, and payment provider. Email and analytics run after the order is recorded. These are simulated targets.

### Synchronous and Asynchronous Flows

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Auth"]
    G --> CART["Cart and checkout"]
    CART --> PRICE["Pricing"]
    CART --> INV["Inventory validation/reservation"]
    PRICE --> ORDER["Order transaction"]
    INV --> ORDER
    ORDER --> RESP["Response"]
    ORDER --> OUT["Transactional outbox"]
    OUT --> Q[("Queue")]
    Q --> PAY["Payment workflow"]
    Q --> EMAIL["Notification"]
    Q --> ANA["Analytics"]
~~~

This diagram illustrates one design option. If payment must be confirmed synchronously before the order transitions to a success state, the payment call must sit on the critical path with its own budget; if the workflow accepts a pending state, payment can proceed asynchronously according to the contract.

### Initial Budget Allocation

| Step | Budget | Type |
| --- | ---: | --- |
| Gateway, TLS/auth/routing | 70 ms | Sequential |
| Cart load and application processing | 90 ms | Sequential |
| Pricing lookup | 110 ms | Parallel with inventory |
| Inventory validation/reservation | 160 ms | Parallel with pricing, slower branch |
| Order database transaction | 180 ms | Sequential after validation |
| Response assembly/serialization | 50 ms | Sequential |
| Network/safety reserve | 140 ms | Reserve |
| **Estimated critical path total** | **690 ms** | 70 + 90 + max(110,160) + 180 + 50 + 140 |

The remaining margin up to the 800 ms p95 target is 110 ms of headroom for unmodeled variance. This is an initial allocation; it must be verified with histograms and distributed traces. Do not add pricing and inventory as two sequential steps if they actually run in parallel.

### Payment Workflow

If payment runs after the response, the API must return an appropriate status such as order accepted/payment pending along with an operation ID. The payment worker has its own deadline/SLO, idempotency keys, and reconciliation. Never trigger the provider asynchronously and return "paid" without confirmation.

### Measurement

- Gateway duration and auth duration.
- Cart query/pool wait.
- Pricing p95/p99.
- Inventory lock/queue wait.
- Database commit duration.
- Outbox publish lag, payment queue age, and provider processing time.
- Checkout end-to-end p50/p95/p99 and success rate.

### Acceptance Criteria

- Checkout API meets its latency SLO alongside its success/error objective.
- No overselling or duplicate orders caused by timeouts/retries.
- Optional analytics/email do not lengthen the critical path.
- When pricing/inventory are slow, timeouts and degraded policies operate properly.
- Queue/payment backlogs are observed and processed under their own SLOs.
- Peak load does not push connection pools or databases past their limits.

## 14. Lab Exercise: Building a Latency Budget for a Booking Flow

**Scenario:** A booking platform provides APIs to view schedules, search providers, and confirm bookings. The system runs in two regions; users may be located far from the region hosting their tenant. The confirmation flow requires auth, reading availability, checking pricing, reserving a slot in the database, and emitting a notification event. Search can use a cache/read model; notification does not need to complete before the response. Hypothetical targets: search p95 under 350 ms, booking confirmation p95 under 900 ms and p99 under 1.5 seconds.

### Tasks

1. **Map the user journey:** define start/end points, client/network/server segments, and business completion.
2. **Draw the dependency graph:** distinguish sequential calls, parallel calls, the critical path, and async side effects.
3. **Create the budget:** allocate gateway, auth, network, service queue, cache/database, locks, serialization, response, and reserve.
4. **Define deadlines:** propagate remaining budget across services; assign connect/read/statement/pool timeouts.
5. **Design retries:** define retryable errors, idempotency, backoff/jitter, attempt limits, and retry budgets.
6. **Design for overload:** queue depth, worker concurrency, admission control, load shedding, and autoscaling headroom.
7. **Instrumentation:** define histograms, traces, span fields, dashboards, synthetic tests, and sampling policies.
8. **Graceful degradation:** decide whether to use cache/stale data, drop recommendations, queue notifications, or fail fast per dependency.
9. **Validation:** run load tests, dependency slowdowns, cold cache scenarios, and zone failures; compare the latency budget against actual results.

### Test Matrix

| Test | Scenario | Required evidence |
| --- | --- | --- |
| Normal load | Expected steady load | p50/p95/p99 and throughput meet SLO |
| Peak load | Burst traffic | Queue wait and tail stay within limits or admission control triggers |
| Slow dependency | Pricing latency increases | Caller stops at deadline, does not hold requests indefinitely |
| Parallel branch | Availability and pricing run in parallel | Critical path uses the slower branch, does not mistakenly sum both times |
| Retry storm | Dependency returns 503/429 | Retry budget/backoff/jitter limit extra load |
| Connection saturation | Pool nears exhaustion | Pool wait is measured, timeouts and backpressure are clear |
| Cold cache | Widespread cache misses | Database does not suffer a stampede beyond capacity |
| Queue backlog | Notification worker is slow | API still meets SLO; queue age triggers alerts |
| Region latency | User far from home region | RTT is measured; placement/edge/read path has a plan |
| Zone failure | One zone is lost | Headroom/failover maintains the defined SLO level |
| Cancellation | Client cancels request | Downstream reads are canceled; durable side effects are still handled properly |
| Payload growth | Response larger than normal | Serialization/transfer stay within budget |

### Deliverables

- User journey and dependency graph.
- Latency SLI/SLO and measurement boundaries.
- Budget table for the critical path and async workflows.
- Deadline/timeout/retry/concurrency policies.
- Observability dashboards and trace specification.
- Load/fault test plan and results.
- Bottleneck analysis with optimization recommendations.
- ADR documenting assumptions, trade-offs, owners, and review triggers.

## 15. Well-Architected Review

| Pillar | Question for the latency budget |
| --- | --- |
| **Operational Excellence** | Are there SLO owners, dashboards, traces, runbooks, a load-testing cadence, and reviews when workloads change? |
| **Security** | Are TLS, auth, policy lookups, encryption, and redaction accounted for in the budget rather than bypassed for speed? |
| **Reliability** | Are deadline propagation, timeouts, cancellation, retry budgets, circuit breakers, and degraded modes tested? |
| **Performance Efficiency** | Are critical paths, queueing, caching, queries, networking, payloads, and capacity optimized based on measurements? |
| **Cost Optimization** | Is latency balanced against replicas, overprovisioning, caching, region placement, and autoscaling costs? |
| **Sustainability** | Are retry storms, unnecessary polling, oversized payloads, and idle capacity avoided when pursuing unnecessary latency? |

## 16. Common Mistakes

**Measuring only a single service's duration.** Users experience the entire flow, including network, gateway, dependencies, and client.

**Adding averages to infer p95.** Percentiles do not add linearly; you must measure end-to-end and understand each hop's distribution.

**Giving every dependency the same timeout.** A secondary service should not be allowed to hold a request for the entire deadline.

**Not propagating deadlines.** Independent per-layer timeouts can cause the total request to exceed the SLO.

**Retrying at multiple layers.** Nested retries multiply call counts exponentially during outages.

**Ignoring queue wait.** Workers can wait a long time even when processing time is low.

**Using CPU as the sole autoscaling signal.** Database pool wait or external dependencies can be the bottleneck while CPU stays low.

**Running every call sequentially.** Independent dependencies can run in parallel, though fan-out and concurrency must be controlled.

**Running all calls in parallel without bounds.** Large fan-outs can overload downstream services.

**Hedging every request.** Duplicated requests can worsen the tail when the system is saturated.

**Not reserving time for response handling.** Services exhaust the deadline on dependencies and have no time left to serialize and return the result.

**Treating async acceptance as immediate completion.** Queue acceptance differs from business completion; the API must reflect the accurate status.

**Not measuring client-side latency.** The backend can be fast while DNS, TLS, transfer, or rendering remains slow.

**Optimizing p50 while ignoring p99.** A subset of users or partitions still suffers a very poor experience.

## 17. Checklist Before Publishing a Latency SLO

- [ ] User journeys and measurement boundaries are clearly defined.
- [ ] SLIs/SLOs use appropriate percentiles and have assigned owners.
- [ ] Dependency graph identifies the critical path, parallel branches, and async side effects.
- [ ] Budget accounts for gateway, auth, queueing, pool wait, compute, data, network, and response.
- [ ] Each hop has timeouts aligned with the remaining deadline.
- [ ] Cancellation propagation is implemented for work that is no longer useful.
- [ ] Retries have backoff/jitter, attempt limits, idempotency, and a retry budget.
- [ ] Hedging is used only for suitable operations and has concurrency caps.
- [ ] Queue depth, wait time, oldest age, and backpressure are observed.
- [ ] Percentiles are measured via representative histograms/tracing; not inferred from averages.
- [ ] Dashboards break down by route, region, tenant tier, and dependency as needed.
- [ ] Client-side measurement is included when the SLO reflects user experience.
- [ ] Load tests cover steady state, peak, bursts, cold starts, and dependency degradation.
- [ ] Capacity/autoscaling has headroom and does not overload downstream systems.
- [ ] Graceful degradation does not break authorization or business invariants.
- [ ] Async acceptance and business completion have distinct semantics.
- [ ] Optimization results are compared under identical workloads with cost/error trade-offs.
- [ ] Budgets are reviewed whenever code paths, dependencies, regions, or traffic profiles change.

A latency budget turns end-to-end performance into an engineerable and verifiable goal. Start from the user journey and SLOs, identify the critical path, allocate time across hops along with reserve margin, and propagate deadlines end to end so services stop in time. Percentiles, queueing, retries, and tail latency must be measured with traces and representative workloads; choices around caching, parallelization, async workflows, autoscaling, and degraded modes must preserve business semantics. A sound budget not only makes requests faster, but also helps the system use capacity responsibly and sustain performance as load or dependencies change.
