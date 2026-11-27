# Load Testing, Soak Testing, and Scalability Limit Testing

## 1. Purpose of Performance Testing in Cloud Architecture Assessment

A cloud application architecture may work functionally yet still fail when traffic surges, when running continuously for days, or when scaling out across multiple instances. Therefore, architecture assessment requires **measurable evidence** of the ability to satisfy business requirements rather than relying solely on diagrams or configuration specs.

Three complementary test groups serve distinct roles:

- **Load test:** how does the system handle normal and projected peak load in terms of latency, error rate, and processing capacity?
- **Soak/endurance test:** when maintaining load for a sufficiently long duration, do resources, latency, queues, and operational state degrade gradually over time?
- **Scalability/capacity test:** does adding resources genuinely increase useful throughput; which component saturates first; how much load can the system serve while still meeting SLOs?

These tests tie directly to cloud architecture trade-offs: **reliability, performance, security, scalability, cost, and operations**. Handling high request volume does not mean a system is reliable if error rates climb. Adding replicas may fail to add capacity if the database, queue, or provider limits are already saturated.

**Running example:** an e-commerce platform uses an API gateway, containerized ordering services, a managed database, a cache, and a payment-processing queue. The business expects a peak of 600 requests/sec during a sales campaign, 10% of which are order creation calls. The architect must prove the ordering flow meets committed response times, neither drops nor duplicates orders, and stays stable throughout an extended campaign.

> **Principle:** Evaluate capacity by **load successfully served within SLO**, not by the highest requests/sec the system ever accepted before failing.

## 2. Understanding Measurement Concepts Correctly

| Concept | Meaning | Common Misconception |
|---|---|---|
| **Throughput** | Volume of work completed per unit of time, e.g., successful orders/minute | Counting every request, including failed ones, as real business capacity |
| **Arrival rate** | Rate at which work arrives at the system, e.g., 600 requests/sec | Assuming arrival rate always equals successful completion rate |
| **Response time / latency** | Time from client start to receiving a response within the measured scope | Looking only at app CPU time while ignoring network, DB, and queue waits |
| **Concurrency** | Number of requests or jobs actively in progress simultaneously | Confusing with total logged-in users |
| **Error rate** | Ratio of failed requests per SLI definition | Counting only HTTP 500s while ignoring timeouts, rejections, business errors, or errors masked by retries |
| **Saturation** | Utilization level of the capacity-limiting resource | Assuming low CPU means the system is not saturated |
| **Queue depth/lag** | Count or delay of unprocessed work in asynchronous systems | Thinking a fast HTTP 202 from the API means the entire workflow finished |
| **Capacity** | Maximum load *proven* to still satisfy service conditions | Using configured quota numbers or results from one short test |
| **Scalability** | Ability to increase capacity by adding resources, factoring in time and cost | Assuming 2x instances automatically yields 2x throughput |
| **SLO/SLI** | Target and indicator expressing service quality levels | Using a single generic latency goal across all endpoints and workflows |

### 2.1. Average Latency Does Not Describe the Worst Experience

Latency should be tracked as distributions—especially **p50, p95, p99**, and the count of slow-tail requests. For instance, p95 = 500 ms means roughly 95% of observed samples completed within 500 ms, depending on tool calculation and valid sample rules.

In multi-tier systems, one service's p99 latency can heavily affect overall transaction completion time when requests await multiple components. Never sum individual p95 values to claim an end-to-end p95: percentiles are not simply additive. Directly measure the **user journey** or business transaction.

### 2.2. Virtual Users Do Not Equal Requests/Second

A virtual user (VU) typically simulates a sequence of actions, read/pause intervals (*think time*), and business steps. Keeping VU counts constant does not guarantee a constant arrival rate: when the system slows down, each VU completes fewer iterations. This can cause the tool to inadvertently reduce load right when the system weakens.

Two key load generation models:

- **Closed workload model:** concurrent VU count is controlled; each VU typically waits for the previous request to finish before issuing the next. Well-suited for simulating user sessions, though send rate drops when responses slow down.
- **Open workload model:** work is injected at a target arrival rate, largely independent of prior response times. Well-suited for testing tolerance to external incoming request rates; requires enough load-generator workers.

Choose the model matching real behavior. For example, webhooks arriving from another system resemble an arrival-rate model; a shopper browsing and reading products exhibits think time and bounded concurrent actions.

### 2.3. Relationship Between Load, Latency, and Concurrency

In steady state, **Little's Law** applies to any consistently measured system boundary:

\[
L = \lambda W
\]

Where \(L\) is the average number of jobs inside the system, \(\lambda\) is the average completion rate, and \(W\) is the average time a job spends in the system. For example, at 300 requests/sec with 0.2 seconds average end-to-end duration, roughly \(300 \times 0.2 = 60\) concurrent requests reside within the measured boundary.

If latency rises to 1 second while 300 requests/sec are still completing steadily, in-flight concurrency climbs to around 300. This can exhaust connection pools, thread pools, or in-flight limits. The formula describes equilibrium; when queues grow continuously, the system is **not** in steady state, so arrival rate, completion rate, and backlog must all be inspected.

## 3. Distinguishing Test Types and Architectural Questions

| Test Type | Typical Load Shape | Question to Answer |
|---|---|---|
| **Baseline** | Low, steady load, enough to warm up | What are normal latency and resource usage? |
| **Load test** | Typical and projected peak load | Does the system meet SLOs at expected service levels? |
| **Stress test** | Stepped increases beyond target load with controls | Where does overload start, and how do failures manifest? |
| **Spike test** | Very rapid surges or drops | Can it absorb sudden bursts and recover after the peak? |
| **Soak/endurance test** | Moderate or high load sustained over long periods | Are there memory leaks, backlogs, connection exhaustion, or cumulative degradation? |
| **Scalability test** | Varying load alongside resource counts/sizes | Does horizontal/vertical scaling add real capacity cost-effectively? |
| **Recovery test** | Returning to low load or removing a component as planned | After overload or partial failure, how quickly does stability return? |

An assessment may combine test types, yet **each run needs one clear testable hypothesis**. Never mix stress, config edits, failovers, and dataset changes in one run and guess root causes from a single chart.

## 4. From Business Requirements to Load Models

### 4.1. Model Transactions Rather Than Just Endpoints

Users perform journeys such as browsing products, searching, adding to cart, placing orders, paying, and tracking orders. Each journey has distinct traffic share, data patterns, latency tolerances, and failure consequences.

An **illustrative workload profile** for a retail platform:

| Journey | Request Share | Peak Level at 600 req/s | Characteristics |
|---|---:|---:|---|
| Browse catalog / details | 50% | 300 req/s | Mostly reads, heavily cache-sensitive |
| Search | 25% | 150 req/s | Complex queries and keyword skew |
| Shopping cart | 15% | 90 req/s | Read/write, tied to user sessions |
| Create order / checkout | 10% | 60 req/s | Writes, business transactions, often involving DB and queues |
| **Total** | **100%** | **600 req/s** | Model must be validated against real metrics |

This is purely a teaching assumption. In real systems, derive numbers from access logs, APM, business analytics, order volume, campaign events, peak days, and growth forecasts. Never take a normal day's traffic ratios and blindly apply them to flash-sale days.

Load parameters to specify:

1. **Peak and average RPS/TPS:** including ramp rate, peak duration, and growth forecasts.
2. **Read/write ratios and journeys:** a single order request may fan out into multiple writes, events, and downstream calls.
3. **Data characteristics:** payload sizes, table row counts, ID distributions, tenant counts, hot keys, and search result sizes.
4. **User distribution:** by region, device, login state, tokens, network origin, seasonality, and peak hours.
5. **Cache behavior:** cold/warm state, hit ratios, cacheable data, and TTLs.
6. **External dependencies:** payment gateways, email, SMS, ERP systems; rate limits and timeout/retry behaviors.
7. **Asynchrony:** events emitted per action, queue delays, background processing duration, and business completion criteria.

### 4.2. Sanity-Checking Load Calculations from Business Data

Suppose the business expects 36,000 orders/hour at peak. The hourly average rate is \(36{,}000 / 3{,}600 = 10\) orders/sec. That figure **does not mean** 10 requests/sec on the system:

- Each order may require multiple checkout journey requests.
- Traffic may cluster into a few minutes within the peak hour.
- Browsers who do not buy generate far higher read traffic.
- Client retries or webhooks inflate request counts without increasing valid orders.

Model both **successful order counts** and per-operation request rates rather than using total RPS as the sole proxy for serving capacity.

## 5. Establishing SLIs, SLOs, and Acceptance Criteria

Tests must conclude *pass or fail* against a requirement. Set SLOs from user experience and business risk tolerance, not directly from current infrastructure capability.

Example set of **illustrative criteria** to tailor per application:

| Item | SLI | SLO/Condition in Peak Scenario |
|---|---|---|
| Browse products | End-to-end p95 latency | Under 300 ms |
| Checkout | Order creation response p95 latency | Under 800 ms |
| Order creation success | Ratio of requests processed business-accurately | 99.5% or higher, excluding approved input errors |
| Payment event processing | Latency from receipt to completion p95 | Under 10 seconds |
| Processing throughput | Valid orders completed/minute | Meets forecast without unbounded backlog growth |
| Post-spike recovery | Time to return within SLO | Under agreed threshold, e.g., 5 minutes |
| Cost | Cost per 1,000 successful transactions | Within approved capacity budget |

**Measurement definitions must be explicit:** is latency measured from the load generator or the gateway; does it include queue wait time; does "success" mean HTTP 202 or actually persisted orders; are client timeouts counted as errors; how long is the measurement window? For async flows, HTTP 202 only means the request may have been accepted, not that business processing finished.

Alongside business targets, set operational **guardrails** such as CPU, memory, connection pools, quotas, queue depth, and retry rates. These are diagnostic and headroom indicators, not substitutes for end-to-end SLOs. For instance, 80% CPU may be healthy on a tuned workload, while 30% CPU can still coincide with database locks or exhausted connections.

## 6. Designing a Trustworthy Test Environment

### 6.1. Production Parity

Test environments should mirror factors that affect results: compute tiers, replica counts, autoscaling, database configuration, indexes, caches, networking, service mesh/gateway, security, quotas, observability, and dataset scale. If testing on a scaled-down environment, document **differences** and inference limits; never linearly extrapolate results by core count.

Common factors that skew measurements:

- Database holds a few thousand rows in test versus tens of millions in production.
- All requests hit one cache key, creating unrealistic cache hit rates.
- Running the load generator on the same host as the app, causing CPU/bandwidth contention.
- Using a near-zero-latency payment mock and concluding real checkout will be equally fast.
- Disabling auth, TLS, WAF, or expensive middleware during tests while production enforces them.
- Measuring only after every cache is warm even though production experiences restarts, rollouts, and failovers.
- Not holding load long enough for autoscaling, queues, or storage to reach steady state.

Differences can be acceptable if documented and assessed for impact. **Test conclusions hold strictly within the measured environment, load, data, and timeframe.**

### 6.2. Scope, Authorization, and Test Safety

Generate load only against environments/endpoints authorized by the system owner. Agree in advance on timing, maximum load, tenant/partner impact, abort thresholds, on-call contacts, and recovery steps. For order creation, billing, or notification flows:

- Use synthetic data or policy-compliant sanitized data.
- Use payment sandboxes, mock modes, or stubs with realistic latency/error behaviors; never trigger real charges.
- Tag test runs with an ID to identify, clean up, or reconcile test records.
- Suppress real email/SMS delivery; respect rate limits and third-party billing caps.
- Protect secrets and tokens via secrets management; never hardcode them in scripts.
- Define stop conditions if impact threatens out-of-scope systems or budget limits.

Never probe limits on third-party systems without permission. For rate-limited external dependencies, use controlled simulators followed by a small integration check within permitted quotas.

### 6.3. Measurement System Architecture

~~~mermaid
flowchart LR
    T[Load generator / Workers] --> E[API Gateway / LB]
    E --> A[Application replicas]
    A --> C[(Cache)]
    A --> D[(Database)]
    A --> Q[Queue / Event bus]
    Q --> W[Background workers]
    W --> D
    A --> S[External service or Sandbox]
    T -. Client metrics .-> M[Metrics / Logs / Traces]
    E -. Telemetry .-> M
    A -. Telemetry .-> M
    D -. Telemetry .-> M
    Q -. Telemetry .-> M
    W -. Telemetry .-> M
    H[Autoscaler / Quotas] --> A
    H -. Events .-> M
~~~

The load-generation cluster needs its own telemetry for CPU, network, VU/worker counts, and **achieved arrival rate**. If the load generator saturates, results only measure the tool's limits.

## 7. Observing the Full Path End-to-End

At minimum, collect and time-align these metric groups:

| Layer | Core Metrics | Diagnostic Questions |
|---|---|---|
| **Load generator** | Requested/achieved rate, VUs, dropped iterations, client timeouts, latency | Did the tool actually emit target load? |
| **Gateway / LB** | Request counts, status codes, 4xx/5xx, p95/p99, throttling, connections, TLS | Is traffic rejected or slowed at the edge? |
| **Application** | Per-endpoint p50/p95/p99, thread/worker pools, CPU, memory, GC, heap, in-flight requests | Is the bottleneck in app processing or downstream waits? |
| **Database** | Query latency, wait/locks, connection pools, CPU/IOPS, replication lag, slow queries | Is the DB hitting connection, lock, or I/O limits? |
| **Cache** | Hit ratio, evictions, memory, hot keys, request latency | Is the cache actually offloading the backend? |
| **Queue / Worker** | Enqueue/dequeue rates, backlog, oldest age, retries, DLQ, consumer lag | Does the API respond fast while background work falls behind? |
| **Cloud platform** | Desired/ready replicas, autoscaling events, startup/readiness, quotas, rate limits | Do resources scale on time and become ready? |
| **Business** | Successful orders, duplicate orders, payment failures, inventory, completion latency | Do technical metrics match business outcomes? |
| **Cost** | Compute, database, egress, cache, logs, traces, external services | At what cost were SLOs met? |

**Distinguish latency layers:** client-side measurements reflect network + app experience; server spans measure single-service processing; database spans or query metrics isolate DB calls. Distributed tracing clarifies dependency chains, though sampling must match traffic volume; avoid full tracing on every request at very high load if cost and overhead exceed limits.

For percentiles, use histograms or distribution-merging methods supported by your tooling. **Never average p95 values across multiple instances** to infer system-wide p95. Aggregate at the distribution level or compute from appropriate raw observations.

## 8. Building a Test Matrix and Execution Sequence

A practical sequence progresses from small sanity checks to high-pressure tests, catching misconfigurations before incurring heavy cost.

| Phase | Illustrative Load | Illustrative Duration | Objective |
|---|---|---|---|
| **0. Smoke & data** | 1–5 req/s | A few minutes | Verify scripts, valid data read/write, complete metrics |
| **1. Baseline** | 50 req/s | 10–15 minutes | Record steady-state latency, errors, and resource usage |
| **2. Step load** | 100 → 200 → 400 → 600 req/s | Long enough to stabilize per step | Find where latency/errors climb and observe autoscaling |
| **3. Peak** | 600 req/s | Matching business peak duration | Prove SLO compliance at projected peak |
| **4. Stress/capacity** | 650 → 800 → ... | Stepped with stop criteria | Identify saturation limits and failure modes |
| **5. Spike** | Rapid 100 → 600 → 100 req/s | Isolated bursts | Test autoscaling reaction, cache, backlog, and recovery |
| **6. Soak** | 200–400 req/s or representative load | Several hours or cycles | Catch time-based degradation and cumulative faults |
| **7. Scale-in/out** | Repeat load across replica/quota tiers | Comparative runs | Measure scaling efficiency and cost; expose new bottlenecks |

These numbers are not rigid standards. For other systems, derive load levels and durations from SLOs, data volumes, impact limits, and operational cycles. Each stage must last long enough for measured components to approach steady state, including autoscaler startup and warmup times.

### 8.1. Controlling Variables

Across comparison runs, hold constant the **application version, dataset, configuration, network zone, load model, and metric collection method**, changing only the variable under test. Adding replicas, adding indexes, and swapping caches simultaneously prevents attributing gains to any single change.

Record test timestamps, commits/releases, infrastructure configs, datasets, load levels, cache states, quotas, and dependent services. A single run may suffer noise from noisy neighbors, caches, networks, or storage; confirm key conclusions with repeated runs under equivalent conditions.

### 8.2. Controlled Load Generation and Stop Limits

Configure maximum allowed load and stop conditions such as sustained high error rates, database overload, budget overruns, or collateral impact on adjacent systems. Beyond saturation, pushing higher load yields no "more accurate" measurements once the system and data sources lose stability.

In an assessment program, verify recovery plans and test-data cleanup before launching long stress or soak runs.

## 9. Example Load Test Script with k6

The example below generates **read** load against an illustrative `/api/products` endpoint. It uses an open arrival-rate model targeting 50 iterations/sec over 10 minutes. Operators must adapt endpoints, journey ratios, SLO thresholds, and load-generator sizing to match their system.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    browse_products: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 100,
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    'http_req_duration{endpoint:products}': ['p(95)<500'],
    'http_req_failed{endpoint:products}': ['rate<0.01'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('Missing BASE_URL');
  }

  const response = http.get(
    baseUrl + '/api/products?limit=20',
    {
      headers: { 'X-Load-Test-Run': __ENV.RUN_ID || 'demo-run' },
      tags: { endpoint: 'products' },
      timeout: '5s',
    }
  );

  check(response, {
    'HTTP 200': (r) => r.status === 200,
    'JSON response': (r) => {
      const contentType = r.headers['Content-Type'] || '';
      return contentType.includes('application/json');
    },
  });
}
~~~

Example invocation from an authorized environment:

~~~bash
BASE_URL=https://performance.example.test RUN_ID=assessment-001 k6 run browse-products.js
~~~

The inline environment variable syntax above is for POSIX shells; in PowerShell/Windows, set environment variables using that shell's syntax. The domain in the example is solely a placeholder.

**How to read the results:**

- If **dropped_iterations > 0**, the tool failed to launch scheduled iterations; inspect VU allocations, generator CPU/network, and response times.
- If achieving 50 iterations/sec while each iteration fires multiple HTTP calls, **RPS will differ from 50**. Here each iteration makes one GET, so both values stay close when load generation succeeds.
- Script p95 and error thresholds are examples only; align them to real SLOs. HTTP 200 alone does not validate business correctness of returned payloads.
- For write load tests, manage test IDs, prevent accidental replay duplicates, verify final persisted state, and clean up test records.

A complete business load test typically combines weighted scenarios (browse, search, order...), valid token handling, realistically distributed random inputs, and result verification steps. Never copy a single GET script and extrapolate full-system capacity.

## 10. Finding the Saturation Point and Scalability Limits

### 10.1. Recognizing the "Knee" on the Load Curve

As arrival rate rises, successful throughput initially scales almost linearly while latency stays flat. Approaching saturation, throughput growth slows while **p95/p99, backlogs, and timeouts can spike sharply**. Past this point, adding requests merely increases queued work or failures.

Illustrative measurements once each step stabilizes:

| Target Arrival Rate | Completed Throughput (req/s) | p95 (ms) | Error Rate | App CPU | Queue Backlog |
|---:|---:|---:|---:|---:|---:|
| 200 | 199 | 190 | 0.0% | 35% | 0 |
| 400 | 397 | 280 | 0.1% | 52% | 0 |
| 600 | 593 | 470 | 0.5% | 76% | 40 |
| 800 | 642 | 1,450 | 6.0% | 96% | 3,500 |

If this journey's SLO is **p95 under 500 ms and error rate under 1%**, then 600 req/s is the **verified compliant load in this illustrative run**; 800 req/s fails. You still cannot declare "absolute capacity is 600 req/s": probe the region between 600 and 800, verify whether the 40-item backlog is growing, and validate under a soak test. If backlog grows continuously at 600, that rate is unsustainable even if HTTP p95 temporarily passes.

### 10.2. Separating System Limits from Measurement Tool Limits

Sometimes throughput stalls at 600 req/s because the **load generator ran out of CPU or VUs**, not because the target system saturated. Cross-check:

1. Target rate, achieved send rate, and dropped iterations.
2. Load-generator CPU, memory, network, DNS, TLS, and file descriptors.
3. Gateway-received throughput vs. backend-completed throughput.
4. SUT error rates, timeouts, and saturation graphs.
5. Whether distributing load generators raises throughput without touching SUT config.

Only once measurement tooling has ample headroom can you determine limits of the System Under Test (SUT).

### 10.3. Architectural Bottlenecks Often Lie Outside Service CPU

Typical bottlenecks:

- **Database:** exhausted connection pools, lock contention, poor query plans, write IOPS, replica limits, or hot partitions.
- **Cache:** cache stampedes on key expiry, sudden hit-rate drops, excessive evictions.
- **Queue:** workers slower than enqueue rate, rising backlog/oldest message age.
- **Network and gateway:** connection limits, NAT ports, LB quotas, TLS handshakes, API gateway throttling.
- **Compute:** CPU saturation, GC pauses, thread/async worker pools, memory or file descriptor limits.
- **Cloud infrastructure:** account/region quotas, autoscaling limits, IP exhaustion, DB connection caps, managed service limits.
- **External dependencies:** rate limits or latency from payment gateways, email, or identity providers.

To draw accurate conclusions, always link **client symptoms** to **evidence at the limiting component**. For example, spiking p99 with 45% app CPU may stem from threads waiting on a 100%-utilized DB connection pool; adding app replicas can worsen matters by opening even more DB connections.

## 11. Testing Horizontal, Vertical, and On-Demand Scaling

### 11.1. Scale-Up, Scale-Out, and Downstream Limits

- **Scale-up (vertical scaling):** increasing CPU, RAM, or tier of a single instance/DB. Fast for local bottlenecks, yet bounded by instance ceilings, cost, and potential resize downtime.
- **Scale-out (horizontal scaling):** adding replicas, workers, partitions, or shards when software can distribute load. Helps fault isolation and elasticity, while increasing connections, coordination, distributed caching, and cost.
- **Autoscaling:** adjusting capacity via metrics/triggers and configured bounds. Inspect reaction lag, startup speed, readiness probes, cooldowns, cost, and scale-in behavior.

Doubling replicas does not guarantee double throughput. Any shared resource can become the new ceiling.

### 11.2. Measuring Scaling Efficiency

Holding workload and data conditions equal, measure multiple configurations:

| Illustrative Configuration | SLO-Compliant Throughput (req/s) | Scaling Gain | What to Check Next |
|---|---:|---|---|
| 2 replicas | 300 | Baseline | CPU, DB, queue, p95/p99 |
| 4 replicas | 540 | 1.8x vs. 2 replicas | Why not 2x? |
| 8 replicas | 620 | Only 1.15x vs. 4 replicas | Are DB or shared resources saturated? |

This example is purely illustrative. **Scaling efficiency** between two configurations can be estimated as:

\[
E = \frac{\text{New Throughput} / \text{Old Throughput}}
{\text{New Resources} / \text{Old Resources}}
\]

If going from 2 to 4 replicas raises throughput from 300 to 540 req/s, \(E = (540/300)/(4/2) = 0.9\), or roughly 90% relative scaling efficiency in that test. Compare using identical SLOs, data configs, and load profiles while accounting for DB/cache/network costs so optimizing one tier does not inflate costs elsewhere.

### 11.3. Measuring Autoscaling Over Time

During a 100 → 600 req/s ramp, record:

1. **When the trigger metric crosses threshold:** CPU, request concurrency, queue lag, or custom design metric.
2. **When the autoscaler requests new replicas:** relative to the load increase.
3. **When new replicas become ready to serve:** including image pull, startup, cache warmup, and readiness probes.
4. **Latency and errors during the gap:** traffic has surged while new capacity is not ready yet.
5. **Post-peak behavior:** scale-in, connection draining, in-flight handling, and stability.

Never inspect only final replica count. For a 2-minute spike when instances take 4 minutes to become ready, autoscaling misses the critical window entirely. Mitigations may include **scheduled/pre-warmed capacity**, minimum replicas, queue buffering, or optimizing startup time.

If scaling on CPU when the true bottleneck is the DB or queue, the control metric responds late or wrongly. Tie scaling metrics to the constraining resource and serving demand. Set upper/lower bounds, rate limits, and budgets to prevent runaway scaling.

### 11.4. Checking Quotas Before Trusting a Scaling Design

Suppose a plan scales from 4 to 20 replicas for a flash sale, yet node quotas, subnet IP space, or database connection caps only support 12 replicas. An architecture with "correct" autoscaling YAML still fails target capacity. Verify **account, region, and resource-type quotas**—both soft quotas and hard service limits.

## 12. Soak Testing: Catching Faults That Only Appear Over Time

A **soak test** sustains meaningful load long enough to exercise resource lifecycles and operational routines. The goal is not merely "no crash after 24 hours," but proving service quality never degrades, resources do not grow unbounded, and work does not pile up.

### 12.1. How Long Is Long Enough?

Match duration to risk and operational cycles:

- **Several hours:** exposes fast leaks, retry accumulation, connection leaks, cache churn, or steadily rising memory/GC.
- **Across one or more operational cycles:** tests token refreshes, certificate rotations, log rotation, scheduled jobs, backups, cache TTLs, or end-of-day batches.
- **Multiple days:** catches slow accumulation or daily/weekly schedule interactions, if budget and environments permit.

No single duration fits every app. A 24-hour run cannot prove 90-day safety, especially for slow growth or uncovered periodic jobs.

### 12.2. Long-Term Degradation Indicators

| Signal | How to Observe | Risk |
|---|---|---|
| Memory climbs steadily by the hour | Heap, RSS, GC, cache entries, post-cycle memory | Memory leak or unbounded cache |
| Active connections drift upward | DB connections, HTTP pools, sockets, file descriptors | Connection/resource leak |
| Queue backlog/lag grows | Enqueue vs. dequeue, oldest age, retries, DLQ | Consumers cannot keep pace over sustained load |
| p95/p99 rises despite flat RPS | Latency time series, slow traces, DB waits | Growing contention, heap pressure, locks, or I/O |
| Periodic error bursts | Log rotation, batches, backups, token refresh | Operational jobs disrupting live traffic |
| Log/storage footprint expands | Disk, object storage, telemetry volume, retention | Disk exhaustion or surprise observability bills |
| Autoscaler oscillates | Desired/ready replicas, CPU, queue, cooldowns | Scaling thrash, instability, or high cost |
| Business state drifts | Order counts, events, state reconciliation | Retries or async handling creating duplicates/losses |

### 12.3. Distinguishing Memory Leaks from Valid Memory Usage

Do not label every rising RSS curve a leak. During startup, JITs, buffers, caches, and connection pools grow until stabilizing. Some runtimes retain freed memory pages from the OS. Inspect:

- Memory levels **post-warmup** and after relevant GC cycles.
- Long-term trend under identical load and equivalent datasets.
- Heap breakdown, object counts, cache size, file descriptors, and connection counts.
- Temporary growth vs. plateauing vs. unbounded climb.

For instance, if post-GC heap rises from 1.0 GB to 1.6 GB over 8 hours under steady work, investigate; it is not conclusive proof of a leak if a bounded cache is legitimately warming against a broader dataset.

### 12.4. Running and Evaluating a Soak Test

1. Warm up and record a steady-state baseline.
2. Hold workload mix, input data, and arrival rate controlled; track achieved rate.
3. Continuously capture multi-layer telemetry and verify business completion, not just HTTP codes.
4. Log intentional events: deployments, autoscaling, backups, rotations, cron jobs.
5. Compare early, middle, and late windows for p95/p99, errors, queue lag, and post-warmup resources.
6. Ramp load down and observe recovery: do queues drain, do memory/connections return to sane levels, do alerts clear?

**Example failure condition:** the system holds HTTP p95 under 500 ms for 12 hours, yet accumulates 100,000 unprocessed events per hour. Even with fast API responses, the architecture lacks sustainable capacity for the async workflow.

## 13. Queues, Capacity, and Processing Debt

For async flows, separately measure work arrival rate \(\lambda_{\text{in}}\) and completion rate \(\mu_{\text{out}}\). Over an interval, backlog changes approximately by:

\[
\Delta Q \approx (\lambda_{\text{in}}-\mu_{\text{out}})\Delta t
\]

If a queue receives 600 events/sec while consumers complete only 550 events/sec, backlog grows by roughly 50 events/sec—around 180,000 events after one hour if the gap persists without shedding.

This explains why **fast API response times do not guarantee good scalability**. An API can return HTTP 202 instantly while queues pile up debt and users wait hours for order confirmation. Assessments need SLOs on end-to-end business completion and oldest-message age limits, not just queue depth.

Queue buffering absorbs brief spikes, but cannot cure sustained overload where processing capacity trails arrival rate. Fixes include scaling/tuning workers, optimizing processing, proper partitioning, backpressure, clear rate limiting, or reshaping the business flow.

## 14. Root-Cause Analysis When Results Miss SLOs

An investigation flow should trace from symptoms back to the limiting resource:

~~~mermaid
flowchart TD
    A[Load rises, latency or errors spike] --> B{Generator hitting target rate?}
    B -- No --> C[Check VUs / CPU / network / dropped iterations]
    B -- Yes --> D{Clients being rejected?}
    D -- Yes --> E[Gateway, rate limits, auth, quotas, timeouts]
    D -- No --> F{App CPU / memory saturated?}
    F -- Yes --> G[Profiling, GC, thread/worker pools, scale]
    F -- No --> H{DB / cache / network / queue saturated?}
    H -- Yes --> I[Query waits, pools, locks, IOPS, hit rate, backlog]
    H -- No --> J[Trace journeys and inspect external dependencies]
    C --> K[Change one variable, re-run, and compare]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

Evidence-driven remediation paths:

| Evidence | Hypothesis to Test | Potential Changes |
|---|---|---|
| High app CPU, DB has headroom | CPU-bound work, serialization, or inefficient algorithms | Profile CPU, trim work, scale app in controlled steps |
| Low app CPU, DB connection pool full | DB waits or connections held too long | Optimize transactions/queries, tune pool size and connection caps |
| High p99 on cache misses | Slow queries or cache stampedes | Optimize queries, add TTL jitter, request coalescing, check hot keys |
| Throughput plateaus as replicas scale | Shared DB, lock, gateway, or quota saturated | Measure shared resources, optimize/partition, or raise valid quotas |
| HTTP stable but backlog climbs | Consumers slower than producers | Optimize consumers, add matched workers, monitor lag |
| Spike causes 429/503 surges | Rate limits, slow capacity warmup, or slow autoscaler | Pre-scale, buffer, add backpressure, controlled rejection policy |
| Soak causes continuous memory/connection growth | Leaks, unbounded caches, or skipped cleanup | Heap/resource profiling, enforce lifetimes, close connections and bound retries |

After fixing, re-verify under **the same workload and criteria**, measuring cost and cross-pillar impact. Raising a DB pool from 50 to 500 may relieve app waiting while pushing the DB into overload; a local "optimization" can degrade system-wide outcomes.

## 15. Cost, Security, and Reliability in Scaling Decisions

### 15.1. Cost per Successful Unit of Work

To compare configurations meaningfully, use a metric such as:

\[
C_{\text{success}} =
\frac{\text{Relevant cost during observation window}}
{\text{Successful business transactions}}
\]

Relevant costs may include compute, database, cache, network/egress, logging/tracing, queues, licenses, and external services. To compare per 1,000 transactions, multiply by 1,000. Explicitly define conversion scope and allocation rules for shared infrastructure.

For instance, if two setups both sustain 600 req/s but one requires double the replicas and higher tracing bills, the architect must judge whether the extra redundancy, fault isolation, or recovery speed justifies the cost. Never optimize cost by accepting SLO violations.

### 15.2. Scaling Does Not Eliminate Redundancy and Fault-Isolation Needs

Capacity tests when one replica, zone, or dependency is unavailable can differ sharply from healthy-state load tests. Architectures required to survive zone loss must include sufficient headroom and verify post-failure traffic distribution. Never assume "N replicas when everything is healthy" suffices when an availability zone goes down.

### 15.3. Test Traffic Must Traverse Required Security Controls

Auth, TLS, network policies, rate limiting, WAF, and data controls affect latency and throughput. If tests bypass these layers, explicitly note that results **do not directly represent** production paths. Meanwhile, ensure tests neither generate real sensitive data nor breach third-party limits.

## 16. Connecting to the Six Well-Architected Pillars

| Pillar | Questions When Reviewing Test Results | Evidence or Action |
|---|---|---|
| **Operational Excellence** | Can tests be repeated, compared, and acted on when SLOs break? | Runbooks, dashboards, versions, test reports, stop thresholds, owners |
| **Security** | Does rising load expose weaknesses in auth/rate limits, secrets, WAF, or permissions? | Controlled tests through security layers, audits, quotas |
| **Reliability** | Does the system degrade gracefully and recover from overload or component loss? | Error budgets, timeouts, retries, circuit breakers, backpressure, recovery times |
| **Performance Efficiency** | Are load distribution, caching, DB, compute, and queues used efficiently? | p95/p99, successful throughput, saturation, profiling, scaling efficiency |
| **Cost Optimization** | Does added capacity justify total cost and successful transaction volume? | Cost per successful transaction, idle headroom, test and ops cost |
| **Sustainability** | Are over-provisioning, redundant retries, and unnecessary data transfers avoided? | Right-sizing, avoiding retry storms, pruning idle capacity, work efficiency |

An architecture is deemed fit when it **meets chosen goals and demonstrates well-reasoned trade-offs**. No single configuration is universally optimal for every business. For instance, pre-scaling before a flash sale raises cost yet removes autoscaler lag risk and protects SLOs during peak revenue hours.

## 17. Case Study: Assessing an Ordering Service Architecture

### 17.1. Context and Hypotheses

An ordering platform uses:

- API gateway and 4 ordering service replicas.
- Managed relational database and read cache.
- Queue forwarding events to payment and status-update workers.
- CPU-based autoscaling bounded from 4 to 12 replicas.

Business forecasts 600 requests/sec for 2 hours, with roughly 60 requests/sec creating orders. Product requires checkout p95 under 800 ms, order failure rate under 0.5%, and payment confirmation p95 under 10 seconds.

Initial hypothesis: **4 replicas suffice for normal load; autoscaling up to 12 replicas will handle 600 req/s**. This is only a hypothesis, not an architectural conclusion.

### 17.2. Test Design

1. Record a 100 req/s baseline using representative workload mix and dataset.
2. Step up through 200, 400, and 600 req/s, measuring achieved rate, p95/p99, errors, DB pools, cache hit rate, queue lag, and autoscaler events.
3. Hold peak load long enough to verify stability; then test a sudden spike.
4. Benchmark 4, 8, and 12 replicas at identical load with appropriate DB limits.
5. Run a soak test at projected sustained load spanning key batches/rotations.
6. Reconcile order commands issued, persisted orders, payment events, and final states.

### 17.3. Illustrative Results

| Hypothetical Observation | Initial Interpretation | Next Check |
|---|---|---|
| 400 req/s: checkout p95 520 ms, errors 0.1% | Meets SLO at this level | Inspect queues and stability |
| 600 req/s: checkout p95 1,100 ms, errors 1.8% | Fails SLO | Inspect traces, DB pool, cache, throttling |
| Replicas scale 4 → 10, throughput barely rises | Bottleneck likely not app CPU | Measure DB waits, connection pools, and queries |
| Active DB connections hit configured cap, pool waits climb | Database is likely bottleneck | Optimize queries/transactions before raising pool |
| After 6h soak, queue oldest age climbs steadily | Consumers lack sustainable capacity | Measure enqueue/dequeue rates, retries, worker lag |

**Do not conclude "just add more replicas."** Tune queries, shorten connection hold times, separate read/write paths, and boost consumer capacity. After each change, re-run the 600 req/s load and soak tests. Only if post-fix checkout hits p95 650 ms, 0.2% errors, flat queues, and on-budget cost do you have evidence supporting the revised architecture.

### 17.4. Acceptance Decision

Based on initial illustrative findings, status is **FAIL** at peak load, even if app CPU never hits 100%. Decision makers need an issue tracker listing owners, actions, due dates, and re-verification tests. Switch to **PASS** only once sufficient evidence confirms all applicable SLOs and guardrails over expected durations.

## 18. Sample Assessment Plan and Report Template

A test record can use this structure for reproducibility:

~~~yaml
assessment_id: architecture-load-001
system: order-platform
environment: performance
purpose: "Verify peak capacity and long-term stability"
owners:
  business: order-operations
  technical: platform-and-order-teams

workload:
  model: open-arrival-rate
  target_rps: 600
  test_mix:
    browse_percent: 50
    search_percent: 25
    cart_percent: 15
    checkout_percent: 10
  data_profile: "Reference dataset description"
  scenario_duration: "Per approved test plan"

slos:
  checkout_p95_ms_max: 800
  checkout_error_rate_max: 0.005
  payment_completion_p95_seconds_max: 10

environment_snapshot:
  app_version: "commit-or-release-id"
  app_replicas: 4
  database_size: "Reference config and data volume"
  autoscaling: "min=4, max=12"
  known_differences_from_production: []

run_controls:
  authorized_scope: "List of authorized endpoints and services"
  stop_conditions: "Approved error, cost, or impact thresholds"
  test_data_cleanup: "Procedure and owner"

result:
  requested_rps: null
  achieved_rps: null
  successful_business_transactions: null
  error_rate: null
  latency_p95_ms: null
  backlog_trend: null
  limiting_resource: null
  cost_estimate: null
  verdict: PENDING

evidence:
  dashboards: []
  logs_and_traces: []
  test_tool_output: []
  deployment_snapshot: []
~~~

**PENDING/null** fields are intentionally blank; never populate them with estimates as evidence. Link dashboards, traces, tool artifacts, and config snapshots to the exact test window.

An executive summary for the architecture board should answer:

1. **What was tested?** Config, load model, scenarios, data, and inclusions/exclusions.
2. **What were the requirements?** SLIs, SLOs, evaluation windows, cost caps, and operational needs.
3. **What were the results?** Requested/achieved load, successful throughput, latency, errors, backlog, resources, trends over time.
4. **Where are the limits?** Metric/trace/quota evidence and confidence level.
5. **What residual risks remain?** Production parity gaps, untested long cycles, small datasets, mocked dependencies.
6. **What is the next decision?** Pass/fail, improvements required, owners, deadlines, and re-verification plan.

## 19. Common Mistakes and How to Prevent Them

| Mistake | Consequence | Prevention |
|---|---|---|
| Looking only at peak RPS | Overestimates capacity when many requests fail or time out | Count successful business transactions **within SLO** |
| Testing only one cache-friendly endpoint | Misses bottlenecks in checkout, DB, and queues | Use full workload mixes and business journeys |
| Tiny datasets or repeating one ID | Unrealistic cache hit rates and query plans | Use large enough datasets, realistic input distributions, and hot keys |
| Using closed VUs while assuming steady arrival rate | Load throttles itself whenever SUT slows down | Pick the right workload model; measure achieved rate |
| Ignoring load-generator metrics | Mistakes tool saturation for SUT saturation | Track dropped iterations, CPU/network, and distribute generators when needed |
| Averaging p95 across instances | Statistically meaningless system latency | Aggregate distributions/histograms properly |
| Adding replicas while DB is bottlenecked | Increases connections and cost while hurting stability | Trace and measure bottlenecks before scaling |
| Checking only HTTP 202, ignoring queues | Processing debt builds silently | Define end-to-end completion SLOs and oldest-message age caps |
| Soak test too short or missing cycles | Misses leaks, rotations, end-of-day batches | Size duration to risk and resource lifecycles |
| Skipping auth/TLS/WAF during tests | Artificially good latency and blind spots on security controls | Keep security layers active or state limits explicitly |
| Changing multiple variables at once | Cannot isolate what helped or hurt | Hold baseline steady; test one hypothesis at a time |
| Ignoring cost and recovery | Setup hits RPS yet proves unaffordable or fragile | Measure cost per success, scale-in, and failure/recovery |

## 20. Self-Assessment Practice Exercises

### Exercise 1 — Calculating Load and Concurrency

An API handles a steady 250 requests/sec with 400 ms average response time. Estimate concurrent requests inside the measured system boundary. Then suppose latency climbs to 1,200 ms while throughput stays at 250 requests/sec. What happens to concurrency demand?

**Suggested Answer:** By Little's Law, \(L \approx 250 \times 0.4 = 100\), rising to \(250 \times 1.2 = 300\). In-flight concurrency demand triples under steady-state conditions and identical boundaries. Connections, memory, and thread/worker pools may become the next bottleneck.

### Exercise 2 — Fast API, Waiting Users

An invoicing service returns HTTP 202 in 120 ms at 800 requests/sec. Workers only process 720 invoices/sec. After 30 minutes at constant rates, how much theoretical backlog accumulates? Is a "30-second invoice completion" goal met?

**Suggested Answer:** The gap is 80 jobs/sec, yielding roughly \(80 \times 1{,}800 = 144{,}000\) extra queued jobs. The 30-second SLO cannot be claimed met; continuously growing backlog strongly signals an unsustainable rate. Inspect per-invoice processing time and queue age history to quantify the violation.

### Exercise 3 — Proposing a Scaling Fix

A workload ramps from 200 to 700 req/s in 20 seconds. HPA takes 3 minutes to spin up enough replicas. The database connection pool hits 90% utilization, and checkout p95 breaches SLO during the first 2 minutes. Propose changes and verification steps.

**Suggested Answer:** Evaluate campaign-based pre-scaling, minimum replicas, startup time optimization, and earlier scaling signals; simultaneously address connection hold times and DB capacity. Run before/after spike tests measuring p95/p99, errors, readiness times, DB waits, and backlog. Do not merely raise max replicas when the DB is already near saturation.

## 21. Pre-Approval Architecture Assessment Checklist

- [ ] Business requirements translated into a workload profile (transactions, journey shares, RPS, peak, and duration)?
- [ ] SLIs/SLOs defined for end-to-end latency, success rate, and async flows?
- [ ] Appropriate open/closed workload model selected, verifying both target and achieved arrival rates?
- [ ] Environment, dataset, cache, auth, network, quotas, and dependencies sufficiently representative; differences documented?
- [ ] Dashboards and evidence collected across clients, gateways, apps, DB, cache, queues, autoscalers, and business transactions?
- [ ] Baseline, peak load, stress, spike, scale-out/in, soak, and recovery tested proportionally to risk?
- [ ] **Highest SLO-compliant verified load** identified, without confusing it with raw peak throughput?
- [ ] Real bottlenecks verified before adding compute; downstream quotas and limits understood?
- [ ] Soak tests cover resource trends, token/connection/backup lifecycles, and queue draining?
- [ ] Business reconciliation executed to catch lost, duplicate, or delayed transactions?
- [ ] Cost/capacity and headroom evaluated for peak load and component failures?
- [ ] Stop conditions, safe test data, owners, run records, and cleanup/recovery plans in place?
- [ ] Pass/fail verdict, inference limits, and follow-up verification tasks recorded?

## 22. Conclusion

Load testing answers whether the system handles demand **right now**; soak testing reveals whether that capability **holds up over time**; scalability limit testing shows **how far, why, and at what cost** capacity can grow. Combining all three with representative load models, business SLOs, and end-to-end telemetry yields actionable proof.

In Well-Architected cloud architecture assessment, the goal is not chasing an impressive raw RPS number. The goal is **proving an architecture has the capacity, stability, security, recoverability, operability, and cost efficiency** required for the scenarios the business truly depends on.
