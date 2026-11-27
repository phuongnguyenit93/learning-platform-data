# Comparing Performance Against Cost and Quality Objectives

> **Chapter:** Performance  
> **Scope:** Designing cloud application architectures from business requirements through network, compute, data, and deployment model choices. This lesson focuses on comparing performance, cost, and quality objectives to choose a suitable architecture configuration, while weighing trade-offs across latency, throughput, availability, scalability, reliability, security, operations, and total cost under Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Translate business needs into measurable quality attributes, SLIs/SLOs, and workload models.
2. Distinguish between latency, throughput, concurrency, utilization, saturation, and capacity, and choose appropriate metrics.
3. Design fair, repeatable benchmarks and load tests to compare architectural options.
4. Convert cloud spend into cost per request, transaction, tenant, or useful unit of work.
5. Compare performance-cost curves, identify the Pareto frontier, and recognize diminishing returns.
6. Evaluate trade-offs across compute, storage, databases, caches, networking, managed services, and scaling strategies.
7. Make decisions grounded in SLOs, risk, total cost of ownership (TCO), headroom, and evidence rather than picking only the fastest or cheapest setup.

## 1. Performance Is Meaningful Only When Tied to Quality Objectives

An architecture can deliver ultra-fast responses at prohibitive cost; another can be cheap yet violate p99 latency thresholds; or a system can achieve high throughput while failed or corrupt transactions rise under heavy load. Performance must never be evaluated in isolation from business goals and other quality attributes.

Example booking platform requirements:
- Users need fast service search, even during peak hours.
- Checkout must complete with accurate transaction state.
- Operations dashboards can lag by a few minutes.
- Financial reports must be complete and reconcilable.
- Cost per booking must stay within profit margins.
- The system needs enough headroom when an availability zone fails.

These requirements are non-uniform. Search can prioritize read caches and bounded stale data; checkout prioritizes correctness and consistency; reporting prioritizes completeness and cost-efficient batch processing.

**The architectural question to answer is not "which configuration is fastest?" but "which configuration achieves the required quality at an acceptable cost and risk?"**

### 1.1. Common Quality Attributes

| Attribute | Measurement question | Common metrics/targets |
| --- | --- | --- |
| Performance | How fast do actions complete? | p50/p95/p99 latency, throughput |
| Scalability | How does capacity scale as load grows? | Throughput per replica, scale time |
| Availability | Can users complete business flows? | Journey success rate, error budget |
| Reliability | Does behavior stay correct under faults? | Failure rate, recovery, data correctness |
| Security | Are permissions and data protected? | Unauthorized access, policy coverage |
| Maintainability | How easy is it to change and operate? | Deployment lead time, toil, change failures |
| Cost efficiency | At what cost are outcomes delivered? | Cost/request, cost/transaction, TCO |
| Data quality | Are results accurate and complete? | Reconciliation, freshness, duplicate rate |

Not every quality attribute can be maximized simultaneously. Increasing replication improves availability at the cost of higher storage and network spend; caching lowers latency while adding invalidation complexity and stale-data risk.

## 2. From Business Requirements to SLIs/SLOs

### 2.1. Turning Qualitative Statements into Measurable Requirements

A statement like "the application must be fast" is insufficient for choosing an architecture. Ask:
- What actions do users perform?
- Where are start and end timestamps measured?
- What are normal, peak, and burst loads?
- What success rates and correctness guarantees are required?
- Are SLOs measured per request, per transaction, or over time?
- Which environments, geographies, devices, and tenant segments are in scope?

Conversion examples:

| Initial requirement | Verifiable definition |
| --- | --- |
| Fast search | p95 search latency under 300 ms at 2,000 requests/second under the agreed workload |
| Reliable checkout | 99.9% of valid transactions reach a defined business state within the measurement window |
| On-time reports | 99% of batches finish before 06:00 with reconciliation discrepancies below threshold |
| Peak resilience | Handle 3x normal-hour traffic while keeping error rates below threshold |
| Reasonable cost | Cost per completed booking stays within target budget at both normal and peak load |

These numbers are illustrative examples, not universal standards. Product, SRE, Finance, and Data owners must agree on denominators, measurement windows, exclusions, and metric sources.

### 2.2. SLIs and SLOs

- **SLI:** an actual measurement such as the fraction of valid requests succeeding, p95 latency, queue age, or freshness.
- **SLO:** the internal target set for an SLI over a measurement period.
- **SLA:** an external commitment carrying contractual definitions and terms.

For example, a latency SLI can be the ratio of valid requests completing under 300 ms:

\[
SLI_{\text{latency}} =
\frac{\text{Requests completed within 300 ms}}
{\text{Total valid requests}}
\]

For checkout, measure accurate business outcomes rather than HTTP 2xx alone. If a payment provider times out after the charge already succeeded, a request timeout does not automatically mean the transaction failed.

### 2.3. Multi-Dimensional SLOs

A single SLO rarely captures overall quality. You may need:
- Latency SLOs.
- Availability/success SLOs.
- Data correctness SLOs.
- Freshness SLOs.
- Capacity/queue-age objectives.
- Cost budgets or unit-cost targets.

Avoid creating too many SLOs without owners or clear actions tied to breaches. Each SLO should map directly to a concrete user experience or business risk.

## 3. Measuring Performance Properly: Latency, Throughput, and Saturation

### 3.1. Latency

Latency is the duration from a defined start point to a defined end point. Inspect distributions rather than averages alone:
- p50: half of requests complete faster than or equal to this value.
- p95: 95% of requests complete no slower than this value.
- p99: captures tail latency affecting the slowest tier of requests.
- Max: useful for debugging, though highly sensitive to outliers.

Average latency can conceal tail latency. An API with a 100 ms average and a 3-second p99 still delivers a poor experience to a subset of users.

### 3.2. Throughput

Throughput is completed work per unit of time:
- requests/second,
- transactions/second,
- messages/second,
- jobs/hour,
- GB processed/hour.

Distinguish offered load (incoming demand) from achieved throughput (work actually completed). A system might receive 5,000 requests/second yet complete only 3,000 requests/second while the rest time out, get rejected, or sit in queues.

### 3.3. Concurrency and Little's Law

Concurrency is the number of requests/jobs inside the system at once. In steady state, Little's Law states:

\[
L = \lambda W
\]

Where:
- \(L\): average number of items in the system.
- \(\lambda\): average throughput.
- \(W\): average time spent in the system.

For example, 400 requests/second throughput with a 0.2-second average duration:

\[
L = 400 \times 0.2 = 80
\]

On average, roughly 80 requests are present within the measurement boundary. This is not a complete sizing formula; distributions, bursts, queueing, and per-request resource usage must still be evaluated.

### 3.4. Utilization and Saturation

Utilization measures how busy a resource is; saturation reflects contention or work waiting due to resource scarcity.

Examples:
- Sustained 90% CPU shrinks burst headroom.
- A DB connection pool at 95% busy with growing wait queues.
- Disk latency rising as IOPS hits limits.
- Network interfaces reaching throughput caps.
- Climbing consumer lag and oldest message age.
- Full thread pools forcing requests to wait even while CPU is low.

Never target 100% utilization. Maintain headroom to absorb bursts, failures, and scaling lag. Target utilization varies with workload and SLO strictness.

## 4. Workload Models: Comparisons Must Be Fair

Benchmarks that fail to represent production workloads lead to poor decisions.

### 4.1. Describing the Workload

A workload model needs:
- Read/write ratios and operation types.
- Endpoint/transaction mix.
- Payload sizes and response sizes.
- Key/tenant distributions, hot keys, and data cardinality.
- Concurrency, arrival rates, think time, and session patterns.
- Cache hit/miss ratios.
- Query complexity and data volumes.
- Background jobs, batches, and event rates.
- Peaks, bursts, seasonality, and growth.
- Geographic distribution, network RTT, and client profiles.

For instance, a search-only benchmark misrepresents checkout if checkout involves transactions, row locks, payment calls, and event publishing. A tiny dataset sitting in a warm cache likewise misrepresents a production database.

### 4.2. Load Test Types

| Test | Objective | What to observe |
| --- | --- | --- |
| Baseline/load | Behavior at expected load | p95/p99, throughput, cost |
| Stress | Limits and degradation points | Saturation, rejections, failure modes |
| Spike | Sudden load surges | Autoscale lag, cold caches, queues |
| Soak | Extended sustained load | Leaks, GC, backlogs, storage growth |
| Capacity | Maximum throughput meeting SLOs | Cost/capacity and bottlenecks |
| Skew | Skewed tenant/key distributions | Hot partitions, noisy neighbors |
| Failover | Loss of node/AZ/dependency | SLOs during failure modes |
| Regression | Comparing builds or configs | Shifts in latency, errors, and cost |

### 4.3. Controlling Variables

When comparing two options, keep constant:
- Workload, input data, and warm-up duration.
- Test location/region, or explicitly account for network differences.
- Identical SLOs and pass criteria.
- Recorded artifact versions, configs, instance types, and autoscaling policies.
- Enough repeated runs to expose variance.
- Cold runs separated from warm runs.
- Changing one factor at a time when isolating root causes.

A faster run tested on a warm cache compared against a cold-start run of another option is not a fair comparison.

## 5. Measuring Cost by Business Outcome

A raw cloud bill does not tell you how much one useful transaction costs. Translate spend into business unit metrics.

### 5.1. Unit Economics

Useful unit metrics:
- Cost per request.
- Cost per successful transaction.
- Cost per booking.
- Cost per active tenant.
- Cost per GB ingested/queried.
- Cost per million events.
- Cost per completed report.
- Cost per inference or model prediction.

Basic formula:

\[
CostPerSuccess =
\frac{\text{Total cost in period}}
{\text{Successful outcomes in period}}
\]

Hypothetical monthly example:
- Checkout-related platform spend: $12,000 USD.
- Valid completed bookings: 600,000.
- Cost per successful booking:

\[
12{,}000 / 600{,}000 = 0.02\text{ USD}
\]

If a new architecture costs $14,000 USD yet supports 800,000 valid bookings:

\[
14{,}000 / 800{,}000 = 0.0175\text{ USD}
\]

Total spend rose while unit cost dropped. Define clearly which costs are allocated to checkout and compare over identical scopes.

### 5.2. Cost per Request Can Mislead

If a system looks cheap because it rejects many requests or returns wrong results, cost/request appears artificially low. Measure cost per **successful, valid outcome** alongside latency, correctness, and availability SLOs.

Also include:
- Retries and duplicate work.
- Failed jobs and waste.
- Idle capacity held to protect SLOs.
- Backups, replication, and DR.
- Logs, metrics, and traces.
- Egress and cross-region traffic.
- Licensing and managed service fees.
- Operational effort and incident response.

### 5.3. TCO

\[
TCO = C_{\text{compute}} + C_{\text{storage}} +
C_{\text{database}} + C_{\text{network}} +
C_{\text{managed services}} + C_{\text{observability}} +
C_{\text{security}} + C_{\text{operations}}
\]

Evaluate TCO over a consistent horizon, such as 12 or 36 months, including migration, dual-running, training, support, vendor lock-in risk, and decommissioning.

## 6. Performance-Cost Curves

As you add compute, caching, or replicas, performance generally improves up to a point before marginal gains shrink. Costs can grow roughly linearly or in steps; some services carry tier/quota jumps and separate network fees.

### 6.1. Marginal Gain

Hypothetical example:

| Configuration | Throughput meeting SLO | Monthly cost | Cost per 1,000 completed requests |
| --- | ---: | ---: | ---: |
| A: 2 replicas | 1,000 req/s | $1,000 USD | $0.0039 USD |
| B: 4 replicas | 1,850 req/s | $1,650 USD | $0.0029 USD |
| C: 6 replicas | 2,100 req/s | $2,400 USD | $0.0033 USD |
| D: 8 replicas | 2,200 req/s | $3,100 USD | $0.0041 USD |

Values are illustrative and require a consistent workload and window. Configurations C and D add less throughput per dollar than B, worsening unit cost. However, if the business requires 2,000 req/s plus failure headroom, B may be insufficient; weigh both peak and failure capacity.

### 6.2. Pareto Frontier

An option is Pareto-dominated if another option is:
- No more expensive and faster, or
- No slower and cheaper,
with at least one dimension strictly better.

The Pareto frontier is the set of options where no single metric can be improved without worsening another within the evaluated set.

~~~mermaid
quadrantChart
    title Cost vs. latency comparison (illustrative)
    x-axis Low cost --> High cost
    y-axis Low latency --> High latency
    quadrant-1 Needs performance review
    quadrant-2 Potentially inefficient
    quadrant-3 Relatively efficient
    quadrant-4 High cost, strong performance
    A: [0.25, 0.75]
    B: [0.48, 0.35]
    C: [0.72, 0.22]
    D: [0.90, 0.18]
~~~

In the chart above, the latency axis runs low-to-high for illustration; when building real dashboards, make axis directions explicit and plot measured numbers. Never treat a Pareto frontier as a substitute for hard constraints: a cheap option that violates security or data correctness is invalid.

## 7. Finding Optimal Capacity, Not Just the Cheapest Setup

Capacity must cover:
- Peak workload.
- Growth forecasts.
- Failure headroom for node or AZ loss.
- Autoscaling reaction time.
- Warm-up and cold starts.
- Batch windows and maintenance.
- Provider quota limits.
- Latency/availability SLOs in both normal and degraded modes.

A rough sizing model:

\[
N_{\text{replicas}} \geq
\left\lceil \frac{\lambda_{\text{peak}}}
{\mu_{\text{replica}} \times U_{\text{target}}} \right\rceil
\]

Where:
- \(\lambda_{\text{peak}}\): peak offered workload.
- \(\mu_{\text{replica}}\): benchmarked throughput per replica.
- \(U_{\text{target}}\): target utilization below 1.

For example, peak 1,600 req/s, one replica delivers 250 req/s within SLO, target utilization 0.7:

\[
N \geq \left\lceil \frac{1600}{250 \times 0.7} \right\rceil
= 10
\]

If the system must survive losing an AZ holding 3 replicas, total replicas or capacity distribution must leave enough capacity for survivors to meet SLOs. This formula is only an initial estimate; request cost heterogeneity, skew, coordination overhead, dependency limits, and autoscaling lag all shift the real requirement.

Never size based on average CPU. Benchmark throughput while meeting SLOs and test under failure modes.

## 8. Compute Trade-Offs: Scale Up, Scale Out, and Managed Services

| Option | Performance benefit | Cost / trade-off |
| --- | --- | --- |
| Larger instances (scale up) | More CPU/RAM/network per node, simplifies some workloads | Higher per-node cost, hardware ceiling, resize downtime depending on service |
| More replicas (scale out) | Higher parallelism for stateless workloads | Greater coordination, load balancing, connections, and total memory |
| Serverless | Scales per event/request, less server management | Cold starts, concurrency/quotas, per-invocation/duration cost, execution limits |
| Managed containers | More runtime freedom and standardization | Clusters, nodes, patching, and capacity still require management |
| Dedicated capacity | Predictable performance, noisy-neighbor isolation | Idle costs and capacity planning |
| Spot/preemptible | Lower compute cost for interruptible workloads | Can be reclaimed; requires checkpoints and retries |

Choose based on the bottleneck. Scaling APIs does not fix database write contention. Scaling workers does not help if the downstream sink is throttled. Managed services trim operational toil without automatically guaranteeing optimal performance or cost.

## 9. Storage and Database Trade-Offs

### 9.1. Storage Tiers

| Storage type | Characteristics | Suitable workloads | Trade-offs |
| --- | --- | --- | --- |
| High-performance block | Low latency / high IOPS | Transactional DBs, latency-sensitive state | High cost per GB and per IOPS |
| General-purpose block | Balanced cost and performance | Application volumes, moderate DBs | Must benchmark IOPS and throughput |
| Hot object storage | Durable, massive scale, frequent access | Active files, data lakes, recent backups | Request/egress fees and different latency vs. block |
| Cool/archive object storage | Lower storage cost | Infrequently accessed backups/history | Retrieval latency and retrieval fees |
| In-memory cache | Very low latency | Hot reads, sessions, computed results | Expensive RAM, invalidation and stale-data risk |

Never compare $/GB in isolation. Account for IOPS, throughput, request counts, retrieval, egress, replication, and recovery.

### 9.2. Database Choices

- Relational databases: ACID transactions, constraints, and rich queries; require sizing, indexing, connection management, and write scaling.
- Distributed SQL: designed for horizontal scale and availability, with added coordination, latency, and operational complexity.
- Key-value/document stores: clear access patterns and horizontal scaling; require understanding query limits and consistency models.
- Columnar warehouses: efficient for analytical scans and aggregations; not transactional serving databases.
- Search engines: full-text and filtering; carry index freshness lag and storage duplication.
- Caches: reduce read latency; do not replace sources of truth unless semantics allow.

### 9.3. Read Replicas and Caches

Read replicas offload read traffic at the cost of replication lag. Caches cut latency and DB load while introducing freshness and invalidation challenges. Measure:
- Cache hit ratio by workload, key, and tenant.
- Origin request reduction.
- Data staleness.
- Cache memory and replication cost.
- Invalidation traffic and stampedes.
- Read replica lag and failover behavior.

A high overall cache hit ratio can still perform poorly if hits cover cheap requests while expensive queries keep missing. Track cost and latency per endpoint and business outcome.

## 10. Networking and Data Placement

Networking is often overlooked when optimizing application latency. Key factors:
- Client-to-edge RTT and geographic distribution.
- Cross-AZ and cross-region traffic.
- Service-to-service hop counts.
- TLS handshakes and connection reuse.
- Payload sizes and compression.
- NAT gateways, load balancers, and egress costs.
- Private connectivity and partner links.

A dependency in another region adds both latency and transfer cost. Co-locating services near the database cuts RTT, though it can complicate multi-region availability and data consistency.

Measures:
- Co-locate services and data according to access patterns where appropriate.
- Use CDNs/edge caching for public or cacheable content.
- Use connection pooling and keep-alive.
- Trim payloads and serialization overhead.
- Batch requests when semantics permit.
- Curb cross-region chatter.
- Measure network egress and latency hop by hop.

Never move sensitive data into another region purely to shave latency if data residency or policy forbids it.

## 11. Autoscaling and Cost-Performance Trade-Offs

Autoscaling reacts to demand with inherent lag. If load surges faster than scale-out completes, users still suffer latency spikes or errors during provisioning and warm-up.

### 11.1. Choosing Scaling Signals

| Signal | When useful | Limitations |
| --- | --- | --- |
| CPU | Compute-bound workloads | Misses I/O wait or queue age |
| Memory | Memory pressure or caches | Often hard to scale down due to state/caches |
| Request rate | Stateless APIs | Individual request costs can vary widely |
| In-flight concurrency | Workers/APIs with concurrency caps | Requires threshold tuning |
| Queue age/backlog | Async workers | Downstream sink may be the true bottleneck |
| Custom business metric | Heterogeneous workload costs | Requires metric computation and maintenance |

### 11.2. Scaling Policies

Configure min/max replicas, stabilization windows, scale-up/scale-down steps, warm capacity, cooldowns, quotas, and dependency protections. Scaling down too fast can re-trigger latency spikes or interrupt active jobs. Scaling up too aggressively can unleash connection storms on databases.

### 11.3. Scheduled and Predictive Scaling

For workloads with clear seasonality (campaigns, payroll, batch windows), scheduled or predictive capacity can be cheaper and steadier than reactive autoscaling. However, bad forecasts waste idle spend; compare pre-warming costs against error budgets and the business impact of under-provisioning.

## 12. Managed Services vs. Self-Managed

Managed services reduce operational toil, patching, and control-plane maintenance, while altering cost models, quotas, observability, portability, and tuning control.

| Criterion | Managed service | Self-managed |
| --- | --- | --- |
| Operations | Provider manages part of the stack | Team carries broader operational responsibility |
| Scaling | Built-in APIs/settings, subject to quotas | Greater flexibility if team has expertise |
| Performance tuning | Bounded by provider abstractions | Deeper low-level control |
| Cost | Usage/tier/feature pricing | Compute/storage plus engineering operations labor |
| Reliability | HA/backups often built in but must be configured | Self-architected and self-verified |
| Portability | Possible lock-in to provider APIs/features | Code/configs may be more portable, with higher ops complexity |
| Security | Shared responsibility | Greater runtime and platform ownership |

Compare **total operational cost**, not just the cloud invoice. A managed service costing 20% more on paper that slashes on-call burden, patching, and downtime can yield lower TCO.

Conversely, a managed service with high minimum tiers or steep per-request/egress fees can be uneconomical. Benchmark and model growth carefully.

## 13. Reliability and Redundancy Costs

Redundancy, backups, replication, and DR raise direct spend while lowering expected business losses and recovery risks.

You can frame the comparison as:

\[
ExpectedAnnualLoss = P(\text{incident}) \times Impact(\text{incident})
\]

\[
EconomicValueOfControl =
ExpectedLoss_{\text{before}} -
ExpectedLoss_{\text{after}} -
ControlCost
\]

This is a directional model, as probabilities and impacts carry uncertainty. For legal, safety, or mandatory compliance obligations, decisions cannot rest on financial math alone.

For instance, multi-AZ databases raise compute/storage/network spend while cutting outage duration. Active-active multi-region boosts resilience while increasing replication traffic, conflict handling, testing, operational complexity, and incident surface.

Define:
- RTO/RPO per user journey and data class.
- Failure modes to withstand.
- Capacity during AZ or region loss.
- Standby and replication costs.
- Test cadence and restore evidence.
- Failover and failback criteria.

## 14. Security and Performance Must Not Be Optimized Separately

A setup may run faster if TLS, logging, or authorization is stripped out, yet that is never a valid optimization if it violates policy or introduces unacceptable risk.

Keep security baselines equivalent when comparing options:
- TLS/mTLS and encryption.
- Authentication and authorization.
- Network segmentation.
- Auditing and telemetry.
- Vulnerability scanning and artifact verification.
- Data retention and residency.

Some controls introduce overhead; measure that overhead and optimize its implementation (connection reuse, durable async logging, well-scoped policy caching) instead of removing controls.

Never use security exceptions as a performance shortcut when a safer architectural path exists.

## 15. FinOps: Connecting Cost to Architecture and Product

FinOps aligns engineering, finance, and business teams so cost data informs design decisions.

### 15.1. Cost Allocation

Attribute spend to:
- Service, team, and owner.
- Environment.
- Tenant or product line where possible.
- Workload type: API, batch, analytics, ML.
- Cost center or project.
- Shared-platform allocation rules.

Incomplete tagging distorts unit costs. Shared costs such as networking, security monitoring, CI runners, and control planes require transparent allocation rules.

### 15.2. Key Cost Drivers

- Compute hours, CPU/RAM, and accelerators.
- Storage GB-months, IOPS, requests, and retrievals.
- Database capacity, replicas, backups, and snapshots.
- Broker partitions, throughput, and retention.
- NAT gateways, load balancers, egress, and cross-region/AZ traffic.
- Logs, metrics, traces, retention, and ingestion volume.
- Managed service tiers, support, and licenses.
- Idle and orphaned resources.
- Build, test, DR, and temporary environments.

### 15.3. Unit Cost and Growth Forecasting

Do not track only this month's spend. Forecast across:
- Active users/tenants.
- Requests and transactions.
- Data volume and retention.
- Peak-to-average ratios.
- Replica/partition growth.
- Cross-region traffic.
- Security/observability coverage.
- DR footprint.

Cost models should cover base, expected, and peak scenarios, noting assumptions and sensitivities. Cloud pricing varies by region, commitments, volume tiers, and enterprise agreements; use your organization's current price book and invoices when deciding.

## 16. Decision Process for Comparing Options

A practical workflow:

1. Define business outcomes and quality constraints.
2. Specify SLIs/SLOs, workload profiles, and failure scenarios.
3. List viable architectural alternatives.
4. Eliminate options that violate security, data residency, availability, or functional constraints.
5. Build representative benchmarks and cost models.
6. Measure latency/throughput/quality/capacity/cost on identical workloads.
7. Calculate unit economics, headroom, TCO, and sensitivities.
8. Analyze the Pareto frontier and marginal gains.
9. Document assumptions, uncertainties, residual risks, and operational burden.
10. Select the option, set review triggers, and monitor post-production metrics.

### 16.1. Reference Scorecard

| Criterion | Example weight | Option A | Option B | Option C |
| --- | ---: | ---: | ---: | ---: |
| Latency/SLO | 25% |  |  |  |
| Throughput/capacity | 15% |  |  |  |
| Cost per success | 20% |  |  |  |
| Availability/recovery | 15% |  |  |  |
| Security/compliance | Mandatory gate | Pass/Fail | Pass/Fail | Pass/Fail |
| Operational toil | 10% |  |  |  |
| Scalability/growth | 10% |  |  |  |
| Portability/lock-in | 5% |  |  |  |

Weights are illustrative. Never let a weighted score compensate for failing a mandatory gate. Security/compliance, data correctness, and minimum SLOs are hard constraints; score only options that pass all hard gates.

### 16.2. Sensitivity Analysis

Vary key assumptions:
- Traffic grows 2x/3x/5x.
- Cache hit rates drop.
- An AZ becomes unavailable.
- Egress climbs due to data transfers.
- Managed service hits a higher pricing tier.
- Log retention extends for compliance.
- Discounts or commitments expire.
- A dependency experiences higher latency or errors.

An option that looks economical only under a razor-thin assumption is rarely sustainable.

## 17. Practical Scenario: Selecting a Configuration for Booking API

### 17.1. Context and Objectives

A booking platform runs its Booking API on the cloud. Normal load is 600 requests/second, peak is 1,800 requests/second; 70% reads and 30% writes. Hypothetical targets:
- p95 under 250 ms under normal load.
- p95 under 400 ms at peak.
- Error rate under 0.5% for valid requests.
- Zero lost committed bookings.
- Survive loss of one AZ per recovery objectives.
- Cost per completed booking stays flat or falls as scale grows.

These figures are exercise assumptions, not recommended SLOs for every product.

### 17.2. Three Options

- **A: Small instances, heavy scale-out:** many small API replicas, primary database, and basic cache.
- **B: Balanced instances + read replica/cache:** fewer replicas, mid-sized compute, read workload offload, hot-read caching.
- **C: Large dedicated instances + high redundancy:** large compute/database tiers, generous reserve capacity, minimal reliance on peak autoscaling.

### 17.3. Hypothetical Benchmark Results

| Metric at peak | A | B | C |
| --- | ---: | ---: | ---: |
| Throughput meeting SLO | 1,500 req/s | 2,000 req/s | 2,200 req/s |
| p95 latency | 390 ms | 310 ms | 260 ms |
| Error rate | 0.8% | 0.3% | 0.2% |
| Monthly cost | $8,000 USD | $9,200 USD | $13,500 USD |
| Ops complexity | High due to many replicas | Moderate | Moderate |
| AZ failure headroom | Low | Meets target after sizing | High |

Illustrative outcomes: Option A is cheapest yet fails peak throughput and error targets; Option C delivers the best performance at steep cost; Option B appears balanced if peak SLOs and failure headroom are validated.

You cannot pick Option B from the table alone. You still must verify data correctness, write contention, replica lag, cache staleness, network egress, and cost per successful booking.

### 17.4. Cost per Successful Booking

Suppose monthly costs and completed bookings are:
- A: $8,000 USD / 350,000 bookings = $0.0229 USD/booking.
- B: $9,200 USD / 500,000 bookings = $0.0184 USD/booking.
- C: $13,500 USD / 650,000 bookings = $0.0208 USD/booking.

Under these assumptions, B achieves a lower unit cost than A despite a higher monthly bill. A rejects many peak requests and lacks throughput; C handles high volume with expensive capacity. If the business requires over 650,000 bookings/month or harsher failure tolerance, the winner could shift.

## 18. Second Scenario: Batch vs. Streaming Processing

A data platform ingests 100 million events/day. Consumers want dashboards refreshed within 5 minutes, while a fraud detection team needs alerts within 5 seconds. Options:
- Hourly batch: low per-job compute cost, misses the alert SLA.
- 1–5 minute micro-batch: can serve dashboards at moderate cost.
- Continuous streaming: meets fast alert targets, yet carries broker, always-on compute, state/checkpoint, retention, and on-call costs.

A hybrid architecture might use:
- Streaming for fraud events and operational alerts.
- Micro-batch for dashboards.
- End-of-day batch reconciliation for finance.

Matching processing models to each consumer's freshness objective avoids paying continuous streaming costs for all data. Measure throughput, event skew, late data, replay, broker costs, and operational burden.

## 19. Common Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Picking the option with lowest p50 | Tail latency may still be poor | Measure p95/p99 and journey SLOs |
| Comparing only monthly bills | Misses cost per outcome | Compute cost per successful transaction |
| Using unrepresentative benchmarks | Decisions mismatch production | Model endpoints, keys, payloads, caches, and peaks |
| Measuring only averages | Misses outliers and queueing | Use histograms, percentiles, and traces |
| Comparing configs under unequal conditions | Unfair conclusions | Fix data, warm-up, regions, versions, and load |
| Scaling to 100% utilization | Zero headroom left | Set target utilization and failure capacity |
| Adding API replicas to fix DB bottlenecks | Increases connection and DB pressure | Locate bottlenecks tier by tier |
| Caching everything | Stale data, invalidation bugs, and RAM cost | Cache per freshness and consistency needs |
| Choosing serverless solely to avoid servers | May hit cold starts, quotas, or high costs | Benchmark latency, concurrency, and unit cost |
| Using managed services without checking quotas | Throttling or caps during peaks | Review quotas and load test |
| Ignoring egress/cross-region fees | Costs exceed budgets | Analyze network flows and transfer costs |
| Trading away security for latency | Unacceptable risk exposure | Optimize implementation while preserving security baselines |
| Omitting DR and backups | Cheap on paper, poor recovery | Include full TCO and failure scenarios |
| Letting weighted scores offset hard-gate failures | Selects non-compliant options | Apply hard gates before scoring |
| Skipping post-production verification | Benchmarks drift from live traffic | Maintain continuous SLI and cost monitoring |
| Failing to revisit assumptions | Growth/pricing/workload shifts outdate design | Set review triggers and run sensitivity analysis |

## 20. Practice Exercise

A booking platform is selecting an architecture for its APIs and data processing. Load averages 800 requests/second and peaks at 2,400 requests/second; 65% reads, 35% writes; the event pipeline receives 3,000 events/second. Product requires p95 checkout under 350 ms, search under 250 ms, dashboard freshness within 5 minutes, and fraud alerts within 5 seconds. Finance requires cost per successful booking not to exceed $0.025 USD.

Complete the following:

1. Convert requirements into SLIs/SLOs, defining denominators and success conditions per user journey.
2. Build a workload model covering endpoint mix, payloads, tenant skew, cache hits, concurrency, and peaks.
3. Propose at least three compute/database/cache/streaming options.
4. Design fair benchmark, load, stress, spike, soak, and failover tests.
5. Produce a comparison table for p50/p95/p99 latency, throughput, error rates, saturation, and capacity headroom.
6. Build a cost model spanning compute, database, storage, brokers, networking, observability, security, and operations.
7. Calculate cost per successful booking and cost per million events; state assumptions.
8. Plot the cost-performance curve, eliminate Pareto-dominated options, and identify diminishing returns.
9. Analyze failure cases: AZ loss, cold cache, database lag, and provider quotas.
10. Enforce hard constraints on security, data correctness, availability, and compliance before scoring.
11. Write an ADR selecting the option, documenting trade-offs, residual risks, owners, and review triggers.

**Self-Evaluation Criteria:** a strong design meets SLOs on representative workloads, converts cost to successful outcomes, includes failure headroom, preserves security/data correctness, and clearly justifies why incremental spend delivers necessary business value.

## 21. Checklist Before Locking Performance and Architecture Budgets

- [ ] Business outcomes and quality attributes are clearly defined.
- [ ] SLIs/SLOs specify denominators, measurement windows, scope, and owners.
- [ ] Workload models include mix, payloads, concurrency, skew, peaks, and growth.
- [ ] Benchmarks use identical conditions, datasets, warm-up, and versioned artifacts/configs.
- [ ] p50/p95/p99, throughput, offered load, errors, and saturation are measured.
- [ ] Bottlenecks are mapped across compute, database, network, queues, and dependencies.
- [ ] Appropriate load/stress/spike/soak/skew/failover tests are executed.
- [ ] Cost models include compute, storage, databases, networking, managed services, and operations.
- [ ] Cost per successful outcome is calculated—not just cost/request or raw bills.
- [ ] Utilization, headroom, autoscaling lag, and failure capacity are analyzed.
- [ ] Scale-up/out, serverless, and managed vs. self-managed options are compared by TCO.
- [ ] Caches, storage, and databases have explicit freshness, consistency, and retrieval costs.
- [ ] Egress/cross-region, observability, security, and DR costs are included.
- [ ] Hard constraints on security, correctness, compliance, and minimum SLOs are satisfied.
- [ ] Pareto/marginal-gain and sensitivity analyses are completed.
- [ ] Assumptions, uncertainties, residual risks, and operational burdens are documented.
- [ ] Post-production performance and cost monitoring plans exist.
- [ ] The ADR captures the decision, rationale, owner, and review triggers.

## Key Takeaway

Comparing performance against cost must start from **business quality objectives**. Measure percentile latencies, SLO-compliant throughput, saturation, correctness, and availability under representative workloads; convert spend to cost per successful outcome; and evaluate options by TCO, headroom, risk, and marginal gains.

Never pick a configuration solely for being fastest or cheapest. Choose the option that satisfies hard constraints, sits on the appropriate Pareto frontier, and justifies incremental spend with business value. After launch, keep tracking SLIs/SLOs and unit costs to verify architectural assumptions remain valid as traffic, pricing, and products evolve.
