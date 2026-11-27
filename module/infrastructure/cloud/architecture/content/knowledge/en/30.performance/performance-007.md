# Designing Normal, Peak, and Sustained Load Tests

> **Chapter:** Performance  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements through network, compute, data, and deployment model choices; balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between load tests, peak load tests, soak/endurance tests, stress tests, and spike tests.
2. Translate usage data and business requirements into a workload model specifying arrival rates, concurrency, request mix, data, and run duration.
3. Establish baselines, SLI/SLO targets, pass/fail criteria, and stop thresholds before running tests.
4. Choose workload profiles and test types matching questions about capacity, autoscaling, stability, or failure modes.
5. Prepare environments, datasets, traffic generators, and dependencies so results are representative without risking production.
6. Measure latency percentiles, throughput, error rates, saturation, queue age, resource utilization, and cost.
7. Analyze results to locate bottlenecks, verify scaling behavior, and estimate headroom/capacity.
8. Detect common pitfalls such as coordinated omission, generator bottlenecks, cache warm-up skew, undersized datasets, and unrealistic traffic.
9. Structure reports, version test scenarios, and rerun tests to compare architecture revisions over time.

## 1. Why Run Performance Tests?

An architecture may work fine with a handful of test users yet degrade when traffic climbs, datasets grow, or many concurrent requests contend for shared dependencies. Autoscaling, caches, database tiers, and queues are often selected based on assumptions. Without verification, those assumptions can drive excessive costs or leave the system unable to handle peak hours.

Performance testing generates controlled load to answer concrete questions:

- How many requests or transactions per second can the system serve at committed quality levels?
- How do p95/p99 latencies change as concurrency rises?
- Do short traffic spikes destabilize queues, databases, or autoscalers?
- Can the system sustain load for hours without memory leaks, growing backlogs, or gradual degradation?
- When a dependency slows down or capacity is constrained, how does the system degrade?
- How much headroom remains if peak load coincides with a zone or instance failure?
- What is the cost per transaction or per unit of throughput?

No single test answers all of these. Normal load tests establish baselines, peak tests validate capacity at the busiest window, and soak tests uncover cumulative issues. Stress and spike tests answer separate questions about limits and recovery.

### 1.1. Start from the Business, Not from the Tool

Suppose a booking platform has the following flows:

- Searching available slots.
- Viewing service and location details.
- Creating and confirming a booking.
- Canceling or rescheduling.
- Sending email/SMS notifications.
- Operations staff viewing dashboards.

These flows carry very different costs. Search may read from cache or query multiple tables; booking creation requires transactions, slot checks, and event emission; notifications can run asynchronously. Generating 1,000 requests/second of cached GETs is not equivalent to 1,000 booking writes/second.

Therefore, a workload model must describe **what users do, how often, against what data, and over what duration**.

## 2. Test Types to Distinguish

### 2.1. Load Test — Expected Target Load

A load test runs a representative workload at a defined level to measure how the system behaves under normal or near-target operating conditions.

Goals:

- Validate latency, throughput, and error-rate SLOs.
- Establish a baseline before architectural changes.
- Identify bottlenecks at forecasted load.
- Quantify capacity and headroom.

For example: simulating 2,000 active users generating roughly 350 requests/second for 30 minutes, following the search, detail, booking, and cancellation mix observed in production.

### 2.2. Peak Load Test — Peak Traffic

A peak load test simulates the highest expected traffic over a window, typically modeled after rush hours, campaigns, holidays, or ticket drops.

It must capture total peak arrival rate or concurrency; read/write ratios during peak windows; tenant/region skew and hot data; bursts at the start of the window; scale-up capability; and autoscaler reaction time.

Peak testing is not just raising user counts. If real peak traffic concentrates 60% of volume in the first 10 minutes, running a flat average rate over an hour can miss queueing and autoscaling issues during the surge.

### 2.3. Soak/Endurance Test — Sustained Load

A soak test sustains a representative workload over an extended duration to uncover issues hidden in short runs:

- Memory leaks, file descriptor leaks, or connection leaks.
- Gradually growing thread pools, connection pools, or caches.
- Accumulating queue backlogs because consumers lag behind producers.
- Uncontrolled growth of logs, metrics, or temporary storage.
- Expiring tokens/certificates, stale connections, or overlapping batch jobs.
- Database bloat, checkpoints, compaction, and maintenance impacting latency.
- Autoscaler oscillation or failure to scale back down.

For example: sustaining 70% of peak load for 8 hours or a full day, including background jobs, periodic batches, and cache cycles. Exact duration depends on the system; the goal is covering a meaningful operational cycle rather than picking an arbitrary fixed number of hours.

### 2.4. Stress Test — Beyond Expected Limits

A stress test pushes load past normal/peak levels to discover limits and failure modes:

- At what point do latency or errors breach SLOs?
- Where is the first bottleneck—API, database, broker, or external dependency?
- Does the system fail gracefully, queue up, or suffer cascading failure?
- Do rate limits, backpressure, circuit breakers, and load shedding engage?
- After load drops, does the system recover automatically or require restarts/intervention?

Stress testing is not meant to prove infinite capacity. Its real value is identifying boundaries, failure modes, and how the rest of the system stays protected.

### 2.5. Spike Test — Sudden Load Shifts

A spike test applies a sharp jump in traffic, such as 100 to 1,500 requests/second within 20 seconds followed by a drop.

It helps verify:

- Can the autoscaler react fast enough to the rate of change?
- Do connection pools, thread pools, and caches survive the burst?
- Do queues absorb the spike and do consumers catch up?
- Do cold starts, image pulls, and initialization inflate latency?
- Does overload protection hold while capacity is still scaling?

A spike test differs from a peak test: peak describes the sustained high level to serve, whereas spike stresses the speed and abruptness of the transition.

### 2.6. Quick Comparison

| Test type | Primary question | Load shape | Expected output |
|---|---|---|---|
| Load | At target load, is quality met? | Ramp to target then hold steady | Baseline SLIs/capacity |
| Peak | Can the system handle the busiest hour? | Time-varying peak pattern | Headroom and peak SLOs |
| Soak | Does running long-term cause degradation? | Steady or cyclically varying load | Long-term stability |
| Stress | What are the limits and failure modes? | Step above expected capacity | Saturation point, graceful degradation |
| Spike | Do sudden bursts cause instability? | Very rapid rise/drop | Autoscaling, queueing, and recovery behavior |

Tests can be combined, provided each keeps distinct questions and pass criteria. Never call a 5-minute high-load run a soak test.

## 3. Defining Targets and Success Criteria

### 3.1. SLIs, SLOs, and Workload Targets

Before testing, define:

- **Latency:** p50, p95, p99 per operation or endpoint.
- **Throughput:** requests/s, transactions/s, or business operations/s.
- **Error rate:** technical errors, timeouts, and business rejections clearly separated.
- **Saturation:** CPU, memory, connection pools, IOPS, queue capacity, and network.
- **Freshness/queue age:** data staleness, oldest message age, or replication lag where applicable.
- **Cost:** cost per unit of throughput/transaction and autoscaling cost.

Hypothetical criteria example for Booking API:

| Metric | Illustrative target |
|---|---|
| Arrival rate | 500 requests/s sustained |
| Booking write throughput | 80 bookings/s |
| Search p95 latency | ≤ 250 ms |
| Booking p99 latency | ≤ 800 ms |
| Technical error rate | < 0.5% |
| Queue oldest age | < 60 seconds |
| Database CPU | < 70% at target load |
| Data correctness | Zero double-booked slots; all outcomes reconciled |

These numbers are illustrative only. Real SLOs must match business requirements, baselines, and measurement points. Never treat 70% CPU as a universal goal; a database can bottleneck on IOPS, locks, or connections while CPU remains low.

### 3.2. Defining Pass/Fail Conditions

A test passes only when all hold simultaneously:

1. Target load is sustained long enough after warm-up.
2. Latency percentiles stay within thresholds.
3. Error rates and business correctness remain within bounds.
4. Dependencies and resources retain defined headroom.
5. Backlogs do not grow continuously or drain within the target window.
6. Autoscaling and failure handling avoid oscillation or cascading failures.
7. No signs of long-term degradation appear.

Never declare a pass solely because average latency is low. Averages can hide a very slow p99 cohort; likewise, a low HTTP error rate is not success if transactions were duplicated.

### 3.3. Measurement Points

Specify where latency is measured:

- Client-side end-to-end, including DNS, TLS, network, and gateway.
- Load balancer or API gateway.
- Application handler.
- Database query/transaction.
- Queue publish/consume.

Client-side measurement sits closer to user experience. Server-side traces uncover root causes. Propagate correlation or trace IDs to link both views; never substitute server processing time for end-to-end latency when network or cold starts are material.

## 4. Building a Workload Model

### 4.1. Arrival Rate vs. Concurrency

Two common ways to express load:

- **Arrival-rate model:** requests/operations started per unit time, e.g., 500 requests/second.
- **Concurrency model:** simultaneously active requests/sessions, e.g., 1,000 virtual users.

Approximate relationship via Little's Law:

~~~text
Concurrency (L) ≈ Arrival rate (λ) × Average time in system (W)
~~~

For example, 200 requests/second with an average 0.4-second time in system creates roughly 80 requests in the system at once, assuming steady state and valid assumptions.

This is a steady-state average relationship. When load exceeds capacity, wait times grow and concurrency can surge even if arrival rate stays constant. Tests must therefore track both offered load and achieved throughput.

### 4.2. Closed Workloads vs. Open Workloads

A **closed workload** holds a fixed number of virtual users; each user sends the next request only after the previous one finishes or after think time. When the system slows down, new requests automatically drop because virtual users are waiting.

An **open workload** schedules arrivals independently of response times; if the server slows down, requests keep arriving at the configured rate. This is usually the better model for testing resilience against a fixed offered load.

This distinction matters. Closed tests can inadvertently ease off right when the server slows down, making latency look better than reality. Coordinated omission happens when a load generator records only the latency of requests actually sent, omitting the delay during which requests should have arrived while the generator waited.

Match the model to real behavior:

- Users clicking and waiting for results: session/closed models may fit.
- Events, webhooks, scheduled jobs, or independent API clients: open/arrival-rate models usually fit better.
- Mixed systems: simulate each source separately and combine them.

### 4.3. Request Mix

A realistic workload might look like:

| Operation | Hypothetical share | Characteristics |
|---|---:|---|
| Search available slots | 45% | Read-heavy, multi-filter |
| View service details | 25% | Cache-friendly |
| Create booking | 15% | Transactional/write, conflict checks |
| Cancel/reschedule | 5% | Update and event emission |
| Read booking history | 7% | Tenant/time-scoped reads |
| Admin dashboard | 3% | Aggregated queries, privileged access |

Shares must come from telemetry, product analytics, or validated forecasts. A 100%-GET mix misjudges database write capacity and queue throughput. Moreover, request share does not equal resource share: one dashboard query can burn more CPU than many search calls.

### 4.4. User Journeys and Think Time

A user might:

1. Open the page and load the service list.
2. Search slots.
3. View details.
4. Select a slot and confirm the booking.
5. View the confirmation page.

Simulating user journeys preserves correlations across sessions, cookies, tokens, caches, and data. Think time between steps avoids unrealistic traffic if real users pause to read and choose before clicking.

Do not set think time so high that the test under-delivers target load. Nor should you strip think time out entirely when testing journey and session behavior.

### 4.5. Per-Tenant Workloads and Data Distribution

Cloud SaaS platforms often have widely varying tenant sizes. Model small/medium/large tenants; tenants with hot data or long histories; distinct regions, locales, and time zones; campaign bursts per tenant; and tenants with special configs, quotas, or keys.

Never distribute data uniformly if production has hot tenants or hot keys. A test across 10 identically sized tenants will miss contention caused when one tenant drives most of the traffic.

## 5. Modeling Normal, Peak, and Sustained Load

### 5.1. Normal Load

Normal load should represent typical usage during standard operating hours:

- Hourly/daily arrival rates.
- Request mix and user journeys.
- Background jobs, batches, refreshes, and telemetry.
- Dataset sizes, hot/cold caches, and tenant distributions.
- External dependencies simulated at realistic levels.

Use normal load to confirm baselines and day-to-day operating costs. Never rely on a daily average if it hides per-minute or per-tenant peaks.

### 5.2. Peak Load

Peak models should rely on measured data or reasoned forecasts:

~~~text
Peak offered load =
  forecast active users
  × actions per user per time window
  × request fan-out per action
~~~

Hypothetical example:

- 12,000 active users during a 10-minute window.
- Average of 2 actions/minute/user in that window.
- Each action triggers an average of 1.4 API requests.

~~~text
12.000 × 2 × 1,4 / 60 = 560 request/second
~~~

Roughly 560 requests/second is the estimated offered load under these assumptions. Calibrate it for concurrency, think time, request fan-out, retries, cache hit rates, and background job traffic. Never treat this number as final required capacity if inputs are unverified.

Peak tests need extra headroom for forecast uncertainty and failure scenarios. For example, if one region must absorb traffic after another region fails, test the surviving region at failover traffic—not merely normal peak.

### 5.3. Sustained/Soak Load

A soak workload should cover a meaningful operational cycle:

- Sustained base load for multiple hours.
- Periodic short peak bursts.
- Scheduled batches, backups, cleanups, compaction, or reports matching production.
- Cache turnover and session lifecycles.
- Token/certificate refreshes if test duration spans them.
- Tracking storage growth, memory, connections, and queue backlogs.

Example 8-hour profile:

| Phase | Duration | Load |
|---|---:|---|
| Warm-up | 20 minutes | 20% normal |
| Normal | 2 hours | 55% target |
| Peak windows | 4 × 10 minutes | 100% peak |
| Inter-peak | 2 hours | 60% target |
| Drain/observe | 30 minutes | Ramp down, watch queues/cleanup |

This profile is illustrative. Build profiles from historical traffic and actual batch schedules; if backups run nightly, an 8-hour daytime run may miss backup contention.

### 5.4. Test Matrix

| Scenario | Offered load | Duration | Objective |
|---|---:|---:|---|
| Baseline normal | 50–60% target | 30 minutes | Baseline latency/resources |
| Expected load | 100% target | 30–60 minutes | Meet SLOs |
| Peak | 100% forecast peak | 20–30 minutes | Capacity at peak |
| Headroom | 120–130% peak | 10–15 minutes | Safety margin and failure modes |
| Spike | Rapid 20% → 100% peak | Multiple times | Autoscaling/burst behavior |
| Soak | 60–70% normal/peak profile | 8–24 hours or matching cycle | Memory/queue/storage drift |
| Stress | Step up to controlled overload | Stepped intervals | Saturation and graceful degradation |

Percentages and durations are examples only. Choose them based on production profiles, SLOs, safety boundaries, and the specific measurement questions.

## 6. Designing Test Scripts and Data

### 6.1. Workload Scripts Must Model Valid Behavior

Scripts must handle authentication and token refreshes; cookies/sessions; headers, tenant IDs, and permissions; correlation IDs; data setup/cleanup; client-like retries/timeouts or test-policy bounds; and response payload validation rather than checking only HTTP status codes.

If a script fires requests without checking responses, a test can report high throughput while the server returns business errors or corrupt data.

### 6.2. Test Data

Datasets must be representative in size and distribution:

- Tenant count and records per tenant.
- Booking history, index cardinality, and relationships.
- Hot/cold keys, partition skew, and varying selectivity.
- Object and request payload sizes.
- Cache key hit ratios.
- Competing transactions targeting the same slot to test locks and unique constraints.

Use synthetic or anonymized data. Never copy production PII into a load-test environment without legal basis, access controls, and masking workflows. Test data also needs retention and cleanup policies.

### 6.3. Data Isolation and Side Effects

Prevent tests from accidentally sending real emails/SMS to customers, charging cards or hitting production payment providers, creating real business bookings, firing partner webhooks, deleting live tenant data, or blowing cloud/egress budgets.

Isolate accounts, projects, networks, and credentials; use sandboxes or mocks for external providers where appropriate. If production-like dependencies must be tested, enforce approved test tenants, allowlists, quotas, and kill switches.

### 6.4. State Cleanup and Repeatability

A test can rapidly inflate data volume, trigger unique constraint conflicts, or alter cache states between runs. Define seed dataset versions, unique namespaces/run IDs, idempotent setup/teardown scripts, TTL/cleanup schedules, snapshot/restore procedures to keep baseline environments clean, and safe queue/cache/database resets.

Repeatable tests let you compare commits, instance families, or configurations without dataset drift skewing the numbers.

## 7. Test Environments and Traffic Generators

### 7.1. Production Likeness

The test environment should match production on factors that affect results:

- Service topology and network paths.
- Instance/container sizes, autoscaling policies, and quotas.
- Database engine/version/tier, storage/IOPS, indexes, and parameters.
- Caches, queue partitions, and broker configurations.
- TLS, IAM, secret retrieval, and encryption overhead.
- Regions, availability zones, and inter-service latencies.
- Observability agents, log/trace sampling, and sidecar overhead.

You do not always need a 1:1 replica if costs are prohibitive. However, document every difference and its inference limits. For example, testing on a smaller database tier cannot directly prove write capacity when storage throughput differs.

### 7.2. Never Let Load Generators Become the Bottleneck

Monitor generator CPU, memory, and network; offered arrival rate vs. achieved request rate; open connections, sockets, ephemeral ports, and TLS handshakes; client-side queues, timeouts, and errors; and geographic placement of generators.

Distribute load generators when needed, keeping metric aggregation and clocks synchronized. Never look solely at server CPU; a bottlenecked generator makes the server appear idle.

### 7.3. Cache State and Warm-Up

A test with a warm cache can deliver far higher throughput than a cold start. Run separate scenarios for cold caches/cold starts when measuring startup behavior, warm caches for steady state, cache eviction/refresh patterns, and cache-miss bursts or slow dependencies.

Record when the test transitions into its warm steady-state window. Never compare one build tested warm against another tested cold and claim an optimization.

### 7.4. NTP and Timing

Generators and services need clocks synchronized closely enough to align timelines, traces, and latencies. Clock drift produces negative spans or skewed metrics. Use monotonic clocks on clients/load tools for measuring durations when supported; use wall-clock timestamps for correlation.

## 8. Metrics to Collect

### 8.1. Latency Percentiles

Latency distributions are skewed: many fast requests, a few very slow ones. Track:

- **p50:** half of requests have latency at or below this value.
- **p95:** 95% of requests have latency at or below this value.
- **p99:** 99% of requests have latency at or below this value.

For example, p50 = 80 ms, p95 = 220 ms, p99 = 1,200 ms reveals a heavy tail; a subset of requests may be hitting locks, cache misses, GC, retries, or slow dependencies. Never rely on averages alone.

When aggregating across instances, never average per-instance p95s to estimate fleet p95. Use aligned histogram buckets or raw samples to compute valid system-wide percentiles.

### 8.2. Throughput and Offered Load

Distinguish among:

- **Offered load:** requests the generator intends to send.
- **Started requests:** requests actually initiated.
- **Completed throughput:** requests finished per unit time.
- **Successful business throughput:** valid, successful business operations.

If offered load is 1,000 requests/s while completed throughput is only 650 requests/s, the remainder are waiting, timing out, or failing to dispatch. Cross-check client-side queues and error counters.

### 8.3. Error Rates

Separate HTTP 4xx from bad inputs/auth/business rules; HTTP 5xx from server failures; timeouts, connection resets, and TLS handshake failures; retry exhaustion and open circuit breakers; and incorrect business outcomes, duplicates, or dropped events.

Do not lump an expected 409 "slot already booked" into 500 database-unavailable errors if it is intentional business behavior. Still, during contention tests, check whether valid conflicts spike abnormally and verify zero double-bookings occur.

### 8.4. Saturation and Dependency Metrics

| Component | Metrics |
|---|---|
| API/compute | CPU, memory, GC pauses, thread pools, worker counts, request queues |
| Network | Throughput, retransmits, connection counts, packet drops, TLS handshakes |
| Database | CPU, IOPS, storage latency, connections, lock waits, slow queries, replica lag |
| Cache | Hit/miss, evictions, memory, command latency, hot keys |
| Broker/queue | Publish/consume rates, backlogs, oldest age, partition lag, DLQ |
| Autoscaler | Desired/current replicas, scale events, pending pods, cold starts |
| Platform | Quotas, API throttling, NAT/connection tracking, storage request limits |
| Business | Booking success, duplicate prevention, payment success, notification lag |

Metrics must tie to timestamps and deployment revisions so changes align cleanly with load steps.

### 8.5. Queueing Behavior

When arrival rate exceeds service rate long enough, backlogs build. When load subsides, the system needs time to drain the queue. Looking only at API latency misses accumulating async events.

Measure queue depth/backlog, oldest message age, producer and consumer rates, retries/DLQ, per-message processing times, and post-peak drain time.

A peak test that passes at the API while queue age climbs from 10 seconds to 40 minutes signals the system cannot sustain the load end to end.

## 9. Identifying Bottlenecks and Interpreting Results

### 9.1. The First Bottleneck Governs Throughput

A request may traverse gateway → API → cache → database → broker. If the database connection pool saturates, adding API replicas merely increases connection contention. If broker consumers lag, scaling producers only inflates the backlog.

Analysis workflow:

1. Compare offered load against completed and successful throughput.
2. Pinpoint when latency and errors start rising.
3. Check saturation across every dependency at that exact timestamp.
4. Follow traces, slow queries, and profiles to locate the dominant time consumer.
5. Change one variable under control (query, pool, cache, replicas, partitions).
6. Rerun the exact same workload/dataset and compare.

Never optimize for a single metric in isolation. Cutting latency via caching can introduce stale data; expanding connection pools can overload the database; scaling workers can trigger external API throttling.

### 9.2. Common Bottleneck Patterns

| Symptom | Likely cause | Investigation path |
|---|---|---|
| High API CPU, low DB load | Serialization, business logic, crypto, compression | CPU profiles, allocations, GC, hot paths |
| Low API CPU, high DB latency | Slow queries, locks, IOPS, connection saturation | Query plans, locks, connection pools, storage |
| Rising queue age | Low consumer throughput, poison messages, partition skew | Consumer lag, retries/DLQ, partition keys |
| Rising p99 with steady p50 | Tail dependency, hot keys, GC pauses, retries | Percentile traces, outlier instances, GC/locks |
| Frequent scale events, flat throughput | Downstream bottleneck or autoscaler lag | Dependency saturation, scaling signals |
| Error spikes on bursts | Connection exhaustion, quotas, cold starts | Generator/clients, quotas, startup timelines |
| Steadily rising latency over hours | Leaks, cache churn, bloat, background work | Memory/FD/connection trends, storage, overlapping jobs |

### 9.3. Capacity Curves

~~~mermaid
flowchart LR
    L[Increase offered load] --> A[Throughput rises]
    A --> B{First saturation reached?}
    B -->|No| A
    B -->|Yes| C[Queueing and tail latency grow]
    C --> D[Errors / timeouts increase]
    D --> E[Graceful degradation or cascading failure]
~~~

Over an initial range, throughput rises nearly linearly. Once a dependency saturates, throughput flattens while latency climbs steeply; errors soon follow. Useful capacity is the highest load that still satisfies SLOs with policy-mandated headroom—not the load right before processes crash.

### 9.4. Headroom and Capacity Planning

Suppose tests show a cell handles 700 requests/s within SLO, at 65% database CPU, stable queue age, and spare load capacity. If forecasted peak is 500 requests/s, nominal headroom over forecast is 40% per:

~~~text
Headroom ratio = (tested safe capacity - forecast peak) / forecast peak
               = (700 - 500) / 500
               = 40%
~~~

This figure is meaningful only if the test used a realistic request mix, dataset, region layout, and failure assumptions. If 700 requests/s holds only with warm caches and no background batches, real headroom is lower.

Capacity planning must account for traffic/data growth, tenant/region skew, zone or replica loss, autoscaling/provisioning lag, provider quotas, batch/backup/compaction jobs, and normal vs. campaign traffic swings.

## 10. Autoscaling and Load Testing

### 10.1. Scale-Out Is Not Instantaneous

Autoscalers need time to collect metrics, evaluate thresholds/windows, request new replicas, schedule nodes/capacity, pull images, start processes, pass readiness checks, and register with load balancers.

If a spike hits in 10 seconds while scale-out takes 90 seconds, the system needs enough headroom or burst absorption to bridge that gap. A peak test may pass once scaled out while a spike test still fails.

### 10.2. Validating Scaling Policies

Measure trigger metrics and detection delay; desired vs. ready replicas; pending/failed pods or VMs; scale-up/scale-down durations; throughput/latency before and after scaling; downstream connection/queue/network impacts; and oscillation/cooldowns.

Scaling API replicas while connection pools grow proportionally can overwhelm databases. Cap fleet-wide connections across max replicas to stay within database budgets.

### 10.3. Testing Scale-Down and Idle Costs

After peaks, verify replicas scale back to baseline without dropping in-flight requests; queue consumers do not shrink prematurely while backlogs remain; cold caches do not trigger thundering herds; connection pools and DBs do not hit reconnect storms; and costs return to expected baselines.

Performance tests must verify both safe scale-out and safe scale-in.

## 11. Running Tests Safely

### 11.1. Environment Boundaries

Prefer isolated accounts, projects, and clusters. If testing against production:

- Obtain approvals, change windows, and dedicated monitoring owners.
- Restrict to approved test tenants and permitted data.
- Cap RPS/concurrency, budgets, regions, and duration.
- Enforce kill switches and automated stop conditions.
- Never call live partners or real payment systems outside approved scope.
- Watch user impact continuously with an empowered decision-maker ready to halt.

Never run ad-hoc stress or spike tests against production. A single test can trigger outages, inflate bills, exhaust quotas, or corrupt live data.

### 11.2. Stop Thresholds

Define stop conditions before launching: critical error rates across consecutive windows; p99 breaching user-impact thresholds; database CPU/IOPS/connections entering danger zones; rapid queue age or DLQ growth; external dependency rate limits; cost/budget ceilings; or production/customer-support alerts.

Thresholds must be concrete. Test operators must know how to halt generators, drain queues, roll back configs, and notify incident owners.

### 11.3. Post-Test Recovery

- Stop generators and confirm offered load returns to 0.
- Monitor queue draining or clean up test data within scope.
- Restore any temporary feature flags, quotas, scaling policies, or configs.
- Verify external providers have no lingering jobs or test sessions.
- Confirm production baselines and SLIs return to normal.
- Archive reports, logs, and traces before retention expires.
- Record an incident or near-miss if the test crossed boundaries or caused impact.

## 12. Tools and Scenario Implementation

### 12.1. Picking Tools by Load Model

| Tool | Characteristics | When to consider |
|---|---|---|
| k6 | JavaScript scripts, virtual users and arrival-rate executors | API load tests, CI scenarios |
| Apache JMeter | GUI/CLI, broad protocol/plugin support and distributed mode | Diverse workloads, existing test plans |
| Gatling | Code DSL, scenarios, and reporting | Complex scenarios, automation |
| Locust | Python user behavior and distributed workers | Custom user journeys |
| wrk/wrk2 | Lightweight HTTP benchmarks; wrk2 targets constant throughput | Endpoint microbenchmarks and rate-controlled latency |
| Cloud provider load testing | Managed generator orchestration | Distributed tests, cloud-native integration |

No tool guarantees a representative workload on its own. Scripts, test data, generator capacity, and metrics determine result validity.

### 12.2. k6 Example with Arrival Rate

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    booking_peak: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 600,
      stages: [
        { target: 200, duration: '2m' },
        { target: 500, duration: '5m' },
        { target: 500, duration: '10m' },
        { target: 100, duration: '2m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
  },
};

export default function () {
  const response = http.get(__ENV.BASE_URL + '/api/slots', {
    headers: {
      Authorization: 'Bearer ' + __ENV.TEST_TOKEN,
      'X-Test-Run': __ENV.RUN_ID,
    },
    tags: { operation: 'search_slots' },
  });

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response has slots': (r) => {
      try {
        return Array.isArray(r.json('slots'));
      } catch (_) {
        return false;
      }
    },
  });

  sleep(0.2);
}
~~~

This example illustrates configuring arrival-rate stages and thresholds; adapt it to your k6 version, generator capacity, endpoints, auth, and test data. With arrival-rate executors, allocate enough VUs to sustain the rate; if VUs run short, k6 cannot maintain the offered load and reports dropped iterations—monitor that metric.

Never hard-code real tokens in scripts. Inject test credentials through pipeline secret mechanisms and avoid printing environment variables or tokens into logs.

### 12.3. Soak Scenario Example

~~~javascript
export const options = {
  scenarios: {
    sustained_workload: {
      executor: 'constant-arrival-rate',
      rate: 180,
      timeUnit: '1s',
      duration: '8h',
      preAllocatedVUs: 120,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.005'],
    http_req_duration: ['p(95)<300', 'p(99)<800'],
  },
};
~~~

This is merely a single sustained-load snippet; real soak tests typically combine multiple scenarios, batch jobs, peak windows, cache cycles, and test-data lifecycle management. Hammering one endpoint for 8 hours is not enough to validate an entire system.

## 13. Analyzing and Reporting Results

### 13.1. What Belongs in a Report?

A useful performance report contains:

1. **Questions and scope:** test objective, environment, services/regions, and build version.
2. **Workload model:** arrival/concurrency, request mix, dataset, tenant skew, think time, and duration.
3. **Environment conditions:** instance sizes, autoscaling, database tier, cache, network, provider quotas, and configs.
4. **Results:** latency percentiles, throughput, errors, business success, saturation, queues, and cost.
5. **Timeline:** warm-up, ramps, plateaus, spikes, scaling events, and failures.
6. **Bottlenecks:** components/metrics, trace/query/profile evidence, and ruled-out hypotheses.
7. **Conclusions:** pass/fail against criteria, safe capacity, and inference limits.
8. **Actions:** changes, owners, priorities, and retest plan.

### 13.2. Illustrative Results Table

| Offered load | Completed throughput | p95 | p99 | Error rate | DB CPU | Queue age |
|---:|---:|---:|---:|---:|---:|---:|
| 200 req/s | 199 req/s | 140 ms | 280 ms | 0.05% | 35% | 2 s |
| 400 req/s | 398 req/s | 210 ms | 510 ms | 0.10% | 55% | 8 s |
| 600 req/s | 590 req/s | 390 ms | 1,100 ms | 0.80% | 82% | 45 s |
| 800 req/s | 620 req/s | 1,400 ms | 4,800 ms | 6.5% | 95% | 8 min |

Numbers are hypothetical. They suggest the system starts missing targets near 600 req/s: completed throughput lags offered load, latency/errors/queues rise, and DB saturation is high. Safe capacity must be reconfirmed with the full workload mix, data correctness checks, headroom, and repeated runs.

### 13.3. Before-and-After Optimization Comparisons

Hold constant the workload/request mix, dataset version and cache state, environment sizing/config, test duration and warm-up, generator capacity, region, and dependency behavior.

Changing multiple variables at once makes it impossible to tell which change drove the gain. Test one hypothesis per cycle—for example, adding an index for query X, tuning connection pools, or adjusting worker concurrency—and rerun the identical test.

### 13.4. Reproducibility and Versioning

Store test scripts and commit hashes; tool versions and dependencies; dataset seeds/versions, shapes, and cleanup steps; infrastructure revisions/provider versions; metrics/reports and timestamps; and approvals, stop events, or deviations.

When a test is non-repeatable, variance may stem from shared environments, noisy neighbors, cache states, or data drift. Recording run conditions prevents drawing wrong conclusions about code.

## 14. Optimizing Architecture from Test Findings

### 14.1. From Symptom to Change

| Symptom | Potential optimizations to test | What to re-verify |
|---|---|---|
| Slow DB queries | Indexes, query rewrites, partitioning, read replicas | Write amplification, locks, storage |
| High API CPU | Profiling, algorithms, serialization, compression | Memory/GC and correctness |
| Connection saturation | Pool sizing, proxies, backpressure | Total connections during scale-out |
| High cache misses | Key design, TTLs, prewarming, cache size | Staleness, thundering herds |
| Queue backlogs | Consumer concurrency, partitions, batch sizes | Ordering, duplicates, downstream limits |
| Slow scale-up | Pre-provisioning, min replicas, startup optimization | Idle cost, quotas |
| Excessive peak cost | Autoscaling, caching, workload isolation | Tail latency and scale-down behavior |
| Abnormal p99 spikes | Tail dependencies, retries, hot keys, GC | p50/p95, errors, and fairness |

Do not throw more hardware at a high CPU chart if the root cause is lock contention, I/O, or bad query plans. Scaling up may hide symptoms briefly without fixing architectural limits.

### 14.2. Retesting After Optimizations

After every change:

1. Run smoke/functional tests.
2. Run baseline load with the identical test profile.
3. Run peak load to verify target capacity.
4. Run controlled stress tests if the change affects saturation/failure behavior.
5. Run soak tests when changing caches, pools, workers, or lifecycles.
6. Reconcile cost, business correctness, and security.

A performance improvement is valid only if it preserves transaction integrity, security, and acceptable costs.

## 15. Common Mistakes in Performance Testing

| Mistake | Consequence | How to improve |
|---|---|---|
| Using virtual user counts alone | True offered request rate is unknown | Measure arrival rate, concurrency, and achieved throughput |
| Measuring only average latency | Hides tail latency | Track p50/p95/p99 and histograms |
| Using closed workloads for open traffic | Slow servers make generators self-throttle | Use arrival-rate/open models where appropriate |
| Under-provisioned load generators | Test misses target and blames the server | Monitor generator CPU/network and dropped iterations |
| Undersized test datasets | Cache/index behavior mismatches production | Use representative datasets and cardinality |
| Testing only the happy path | Misses writes, retries, locks, and error paths | Model full request mix and business outcomes |
| Skipping warm-up or not logging cache state | Unfair comparisons | Standardize warm-up and cold-cache scenarios |
| Tests too short | Misses leaks, queue buildup, and batch contention | Soak across meaningful operational cycles |
| Watching only API latency | Async queues/backlogs silently build up | Measure end-to-end completion and oldest message age |
| Ignoring autoscaling delay | Peak spikes time out before replicas are ready | Run spike tests and track scale timelines |
| Allowing unbounded retries in tests | Amplifies load and masks root errors | Enforce retry budgets, backoff, and idempotency |
| Testing directly in production without guardrails | Causes outages or real side effects | Use isolated environments or approved windows/kill switches |
| Changing multiple parameters at once | Cannot tell which change helped | One primary hypothesis/variable per cycle |
| Skipping business data reconciliation | High throughput with corrupt/duplicate transactions | Validate invariants and reconcile records |
| Failing to save configs/commit hashes | Results cannot be reproduced | Version scripts, data, and infrastructure |

## 16. Lab Exercise: Building a Test Plan for a Booking Platform

**Scenario:** A cloud SaaS booking platform consists of an API Gateway, Booking Service, relational database, cache, event broker, and Notification Worker. Normal weekdays average roughly 150 requests/second, and the recent peak hit 450 requests/second for 15 minutes. The team expects an upcoming campaign to reach 700 requests/second. It is currently unknown what the database's safe capacity is and whether consumers can drain the notification backlog after peak.

Build a test plan covering:

1. **Business workload:** define the operation mix across search, details, create, cancel, history, and notifications.
2. **Traffic model:** convert historical normal/peak numbers into arrival-rate profiles; state assumptions for concurrency, think time, retries, and tenant skew.
3. **SLOs:** choose latency percentiles, error rates, booking correctness, queue age, freshness, and capacity headroom.
4. **Test matrix:** design load, peak, spike, stress, and soak tests; define duration/warm-up/ramp/plateau.
5. **Test data:** create representative tenants/data volumes, hot keys, and booking conflicts; ensure zero real PII.
6. **Environment:** describe instances/databases/IOPS/caches/brokers/regions/autoscalers and differences from production.
7. **Generators:** choose tools, distribute generators, size max VUs/arrival rates, and monitor dropped iterations.
8. **Instrumentation:** build dashboards for p50/p95/p99 latency, throughput, errors, DB, cache, queues, autoscaler, and business metrics.
9. **Safety:** budgets, scope, test credentials, sandboxes, kill switches, stop conditions, and cleanup.
10. **Analysis:** use results to determine safe capacity, bottlenecks, headroom, and optimization proposals.
11. **Repeatability:** version test scripts, datasets, configs, commit hashes, and before/after reports.

### Sample Test Matrix

| Scenario | Illustrative profile | Duration | Question |
|---|---|---:|---|
| Normal | 150 req/s, production-like mix | 30 minutes | Does baseline meet SLOs? |
| Current peak | 450 req/s | 20 minutes | Can rush-hour traffic be reproduced cleanly? |
| Forecast campaign | 700 req/s | 20 minutes | Does it hit target with headroom left? |
| Spike | 150 → 700 req/s in 15 seconds | 5 times | Do autoscalers/queues survive the burst? |
| Stress | Step 700 → 900 → 1,100 req/s | 5 minutes per step | Where are bottlenecks and graceful degradation? |
| Soak | 300 req/s, plus peak windows and batch jobs | 8 hours | Do memory/queues/storage remain stable? |

These profiles are initial assumptions to be calibrated against real analytics and environment safety limits.

### Sample Pass/Fail Criteria Table

| Metric | Illustrative pass condition |
|---|---|
| Booking API p95 | ≤ 300 ms at 700 req/s |
| Booking API p99 | ≤ 800 ms at 700 req/s |
| Technical error rate | < 0.5% |
| Successful bookings | Meets business target with zero double-booked slots |
| Queue oldest age | < 60 seconds at peak; drains to baseline within 10 minutes |
| DB saturation | Stays within safety limits established by load testing |
| Autoscaling | Scaling completes before error budget burn breaches policy |
| Soak stability | Memory/connections/backlogs do not grow without bound |

**Completion Criteria:** A reviewer can understand what load is simulated, why it represents the business, pass/fail thresholds, evidence collection, stop conditions, and how safe capacity is derived. All hypothetical figures must be clearly distinguished from measured data.

## 17. Well-Architected Review

| Pillar | Performance testing questions | Evidence |
|---|---|---|
| **Operational Excellence** | Are scenarios, datasets, environments, reports, and rerun processes versioned? | Test plans, script revisions, repeatable reports |
| **Security** | Are test data/credentials protected; are scope and stop switches safe? | Data masking, IAM, approvals, cleanup evidence |
| **Reliability** | Do peak/spike/soak tests prove graceful degradation and recovery? | Queue draining, error budgets, soak trends, failure tests |
| **Performance Efficiency** | Are capacity, bottlenecks, tail latencies, and autoscaling measured? | p95/p99, throughput, saturation, capacity curves |
| **Cost Optimization** | Are cost per transaction, idle headroom, and peak costs measured? | Cost dashboards, cost/load curves, scale-down results |
| **Sustainability** | Are compute/storage/network utilized efficiently relative to load? | Utilization, data lifecycles, resource efficiency |

Performance testing produces more than a single requests/second number. It supplies the evidence needed to choose architectures, capacities, and scaling policies; when run repeatedly against representative workloads, it lets organizations understand limits, risks, and costs before live traffic hits them.

## 18. Key Takeaways

- **Load tests** validate normal target load; **peak tests** validate busy windows; **soak tests** catch cumulative degradation.
- **Stress tests** find limits and failure modes; **spike tests** evaluate sudden surges and autoscaling responsiveness.
- **Workload models** must specify arrivals/concurrency, request mix, journeys, think time, tenant skew, and data.
- **Offered load differs from completed throughput.** Watch dropped iterations and load generator headroom.
- **Latency requires percentiles:** averages miss tail behavior; combine p50/p95/p99 with errors and business correctness.
- **Bottlenecks span the full flow:** APIs, databases, caches, queues, networks, quotas, and external dependencies.
- **Soak tests track trends:** memory, connections, storage, queue age, caches, and background jobs.
- **Tests must be safe and repeatable:** controlled data, stop conditions, cleanup, versioned scripts/configs, and reports.
- **Capacity is the load that meets SLOs with headroom**, not the maximum load right before the system crashes.

Effective load test design starts from how users and systems generate traffic, converts that into a repeatable workload, and measures quality across both technical and business layers. Normal, peak, and sustained load tests answer different questions; combining them with stress and spike tests gives architects clear visibility into capacity, limits, and recovery before committing to investments or scaling changes.
