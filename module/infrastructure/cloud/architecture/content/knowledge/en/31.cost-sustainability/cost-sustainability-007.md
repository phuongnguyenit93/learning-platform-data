# Cost Estimation Across Architecture Options and Sensitivity Analysis

## 1. Why Estimate Multiple Options?

A business requirement usually has multiple ways to be implemented in the cloud. An API can run on VMs, managed containers, or serverless; data can reside in a multi-region relational database, a single-region database with recovery replicas, or a separated write store and read projection model. Each option creates a different cost profile across compute, storage, networking, licenses, operations, availability, and recovery.

Choosing an option based solely on hourly compute price easily leads to wrong decisions. A service with cheap compute that requires numerous standby nodes, NAT gateways, cross-region replication, heavy log ingestion, and on-call staffing can end up far more expensive. Conversely, an option with a higher unit price may reduce instance count, administration time, downtime, or incident recovery effort.

**Estimating multiple architectural options** is the process of building cost models under identical workload, timeframe, and service-level assumptions, then comparing Total Cost of Ownership (TCO), cost per business unit, risk, and sensitivity to key variables.

**Sensitivity analysis** shows how results change when one or more assumptions shift: traffic grows, data is retained longer, egress prices rise, cache hit rates drop, an extra standby region is required, or operational costs run higher than expected.

In the **CLOUD_ARCHITECTURE** module, cost estimation is part of trading off networking, compute, data, resilience, security, and operations. The goal is balancing **cost, reliability, security, performance, scalability, and sustainability** with Well-Architected thinking.

Running example throughout: a booking platform must serve search, booking creation, payments, notifications, and reporting. The architecture team evaluates three options: self-managed VMs/containers, a managed container platform, and serverless/event-driven. No single option is inherently cheapest; the outcome depends on traffic profile, processing duration, redundancy levels, and operational team capabilities.

## 2. Starting with a Common Baseline

Comparisons are meaningful only when options meet the same demand. Before plugging in unit prices, align on a baseline:

| Assumption Group | Items to Lock Down |
| --- | --- |
| Workload | Average and peak requests/second, concurrency, request/response size, CPU and memory per operation |
| Data | Record count, initial volume, growth rate, retention, backups, replication, and read/write rates |
| Network | Ingress/egress, cross-zone/region traffic, CDN/cache hit rate, NAT, and private endpoints |
| Availability | SLOs, zone/region counts, failover capacity, RTO/RPO |
| Security | Encryption, key management, auditing, private networking, security tooling, and retention |
| Operations | Environment counts, release frequency, on-call, patching, backup tests, incidents, and support |
| Commercial | Region, currency, billing period, discounts/commitments, licenses, and support plans |
| Time horizon | 12/24/36 months, start date, ramp-up, and time to steady-state load |

Never compare Option A's average workload against Option B's peak. The baseline must specify average, peak, burst duration, and intraday/weekly usage patterns.

### 2.1. Workload Profile

A profile can be expressed as:

~~~text
monthly_requests = 120,000,000
average_rps = monthly_requests / seconds_in_month
peak_rps = 8 * average_rps
average_request_compute_ms = 35
response_size_kb = 12
monthly_egress_gb = estimated_from_response_volume
data_growth_gb_per_month = 120
retention_months = 24
~~~

These example values are illustrative study assumptions. In a real project, pull figures from telemetry, load tests, billing, and business forecasts; record sources, observation windows, confidence levels, and extrapolation methods.

### 2.2. Never Use a Single Average to Describe All Loads

Two systems with the same 100 million requests/month can have vastly different costs:

- System A runs steady load 24/7.
- System B concentrates most requests into two narrow windows, requiring burst capacity.
- System C handles fewer requests, but each runs heavy queries and holds connections open long.

Serverless may suit bursty loads with long idle stretches; containers/VMs can be efficient for steady, predictable loads. Conclusions must rest on the full profile, not request count alone.

## 3. Defining TCO Scope

TCO (Total Cost of Ownership) covers the cost of bringing a solution into operation and sustaining it over the analysis period. Its scope can extend well beyond the cloud invoice.

| Cost Group | Typical Line Items |
| --- | --- |
| Compute | VMs, container nodes, serverless invocations/duration, accelerators, autoscaling headroom |
| Data | Database instances, storage, IOPS, backups, snapshots, replication, caches, search/indexes |
| Network | Load balancers, NATs, private endpoints, CDN, DNS, egress, cross-zone/region transfers |
| Platform | Kubernetes control/worker nodes, service mesh, registries, secrets, observability services |
| Security | KMS operations, WAF, vulnerability scanning, SIEM, audit retention, security support |
| Software | OS/database licenses, commercial middleware, monitoring agents, support subscriptions |
| Operations | Engineering/on-call time, patching, upgrades, capacity management, incident response |
| Delivery | CI/CD minutes, artifact storage, test environments, preview environments |
| Resilience | Warm standbys, replicas, multi-region capacity, DR exercises, backup restore testing |
| Migration | Refactoring, data transfer, parallel runs, dual-writes, training, and cutover |

### 3.1. Direct Costs and Indirect Costs

Direct costs typically appear explicitly on invoices or contracts. Indirect costs include engineering time, coordination overhead, downtime, audit effort, or migration costs.

Do not lump items together arbitrarily. Specify clearly:

- Which items are included in TCO?
- What loaded rate applies to labor?
- By what ratio are shared costs allocated?
- Is downtime valued by lost contribution margin, penalties, or qualitative description?
- How are one-time and recurring costs separated?

Separate known costs, estimated costs, and hard-to-quantify risks. This helps decision-makers see which figures are firm and which depend on assumptions.

## 4. Driver-Based Cost Modeling

Do not produce an estimate as a single lump sum up front. Break costs down by measurable, forecastable drivers.

A general model:

~~~text
TCO(horizon) =
    one_time_cost
  + recurring_fixed_cost
  + variable_cost(workload)
  + operations_cost
  + resilience_cost
  + risk_allowance
  - applicable_credits_or_discounts
~~~

Where:

- One-time cost: migration, setup, training, initial data transfer.
- Fixed cost: reserved capacity, licenses, minimum clusters/nodes, support.
- Variable cost: requests, compute duration, storage growth, I/O, egress.
- Operations cost: staffing, maintenance, upgrades, recovery testing.
- Resilience cost: replicas, standbys, backups, failover capacity.
- Risk allowance: contingency calculated via an organization-approved method; never used to mask missing data.

### 4.1. Cost Driver Tree

~~~mermaid
flowchart TD
    TCO["Total Cost of Ownership"]
    TCO --> FIX["Fixed / committed"]
    TCO --> VAR["Usage-based"]
    TCO --> OPS["Operations"]
    TCO --> RES["Resilience"]
    TCO --> ONE["One-time"]
    FIX --> NODE["Baseline compute / license"]
    VAR --> REQ["Requests / compute time"]
    VAR --> DATA["Storage / IOPS / egress"]
    OPS --> ENG["Engineering / on-call / support"]
    RES --> DR["Replica / backup / standby"]
    ONE --> MIG["Migration / parallel run"]
~~~

This diagram illustrates driver categories, not a specific provider's invoice layout. Each driver needs an owner and a data source.

## 5. Calculating Compute Cost by Architecture Model

Compute models use different billing units:

| Model | Common Cost Drivers | Must Include in Estimate |
| --- | --- | --- |
| VMs | Instance hours, size, OS/licenses, disks | Minimum instances, autoscaling, standbys, patching |
| Containers on node pools | Node hours, CPU/memory, cluster fees per platform | Daemon/system overhead, bin packing, idle nodes, upgrades |
| Managed/serverless containers | vCPU/memory duration, requests, or capacity | Minimum instances, cold start strategy, concurrency |
| Functions/serverless | Invocations, execution duration, allocated memory/CPU, provisioned concurrency | Retries, timeouts, cold starts, event volume, logging |
| Managed application platforms | Instances/time, requests, feature tiers | Platform fees, autoscaling bounds, integration charges |

### 5.1. Calculate Utilization Instead of Just Adding Nodes

Suppose a node has 8 vCPUs while the workload uses an average of 2 vCPUs. You cannot always cut nodes by 75%, because headroom is needed for peaks, memory, replica placement, failures, and system daemons.

A simple estimate:

~~~text
required_nodes =
  ceil(peak_resource_demand / usable_resource_per_node)
~~~

Usable resources must subtract reservations for OS, kube/system services, safety headroom, and bin-packing fragmentation. With multi-zone HA, also determine remaining capacity when a zone fails; never assume all nodes can be utilized identically during normal operation and failover.

### 5.2. Autoscaling Does Not Make Compute Free

Autoscaling lowers costs during low demand, yet:

- Scale-out has lag, so baseline capacity is still needed.
- Scale-in may be constrained by disruption budgets or stateful workloads.
- Peak bursts can hold nodes active longer due to cooldowns.
- More replicas can increase connections to databases/caches.
- Scaling on CPU may miss queue latency or request costs.

Estimates should simulate capacity over time or use utilization distributions—neither multiplying peak nodes across every hour when autoscaling works well, nor using average utilization when SLOs demand higher peak capacity.

## 6. Calculating Storage, Database, and Backup Costs

Data costs involve many components beyond primary capacity:

~~~text
data_cost =
    primary_storage
  + replicas
  + backup_storage
  + snapshot_retention
  + IOPS_or_throughput
  + read/write_requests
  + data_transfer
~~~

### 6.1. Growth Forecasting

~~~text
stored_data(month_n) =
  initial_data + monthly_growth * n

retained_data =
  sum(data_created_in_each_period_still_within_retention)
~~~

When data expires under retention policies, capacity does not grow linearly forever. However, backups/snapshots can retain multiple versions or changed blocks; exact calculation depends on service mechanics.

### 6.2. Database Tiering

Database comparisons must include:

- Compute tiers and HA topology.
- Storage, IOPS, transaction logs/WAL, and backups.
- Read replicas or cross-region replication.
- Connection pooling, proxies, and monitoring.
- Licenses and support.
- Maintenance windows and upgrades.
- Migration/compatibility costs if changing engines.

A small database has a lower unit price, yet failing to meet peak or failover SLOs can raise disruption costs. A large database tier can also be wasteful when queries remain unoptimized.

### 6.3. Backups and Retention

Longer retention raises storage spend, while overly short retention can violate recovery, audit, or business needs. Backup estimates must include frequency, retention, full/incremental behavior, cross-region copies, immutable storage, restore testing, and recovery egress.

## 7. Frequently Overlooked Network and Data Transfer Costs

Network costs can climb rapidly when services split up or deploy across regions:

- Internet egress.
- Cross-zone transfers between compute and databases.
- Cross-region replication.
- NAT gateway processing/hourly charges.
- Private endpoint hourly/request fees.
- Load balancer and CDN requests/transfers.
- Service mesh sidecar overhead and east-west traffic.
- Backup/restore and migration transfers.

### 7.1. Data Flows Requiring Diagramming

~~~mermaid
flowchart LR
    U["Users"] --> CDN["CDN / Edge"]
    CDN --> API["API compute"]
    API --> DB["Database"]
    API --> CACHE["Cache"]
    API --> OBJ["Object storage"]
    DB --> REPL["Cross-region replica"]
    API --> EXT["External providers"]
    API --> NAT["NAT / Internet egress"]
~~~

Every arrow should carry volume, average payload size, compression ratio, call counts, cache hit ratio, and zone/region placement. If API and database sit in different zones, every query can incur repeated transfer; if images route through a CDN, origin egress can drop.

### 7.2. Cache Hits and Egress

Cache hits cut origin requests and origin data transfer, yet caches also carry storage, request, invalidation, and operational costs. Estimates should use measured hit ratios or bounded assumptions—never assume 99% merely because caching is enabled.

## 8. Observability, Security, and Platform Service Costs

Supporting services can make up a significant share of spend:

| Service | Drivers | Estimation Questions |
| --- | --- | --- |
| Logs | GB ingested, retention, queries | Is debug logging excessive? Are sampling/redaction applied? |
| Metrics | Samples/time series, cardinality, retention | Which labels create high cardinality? |
| Traces | Span volume, sampling, retention | Does sampling preserve critical error traces? |
| SIEM/security analytics | Event ingestion, retention, queries | Which logs are mandatory, and which can be filtered? |
| KMS | Key count, API operations, HSM tiers | How many encrypt/decrypt requests occur? |
| WAF | Request counts, rule tiers | Can bot/attack traffic inflate request fees? |
| Container registry | Artifact storage, transfers, vulnerability scans | How many images/versions are retained? |
| CI/CD | Build minutes, runners, artifacts | Are preview environments/parallel builds excessive? |

Never slash retention or sampling mechanically to trim bills. Preserve data needed for security, investigations, compliance, and SLOs.

## 9. Operations Costs and Team Capabilities

Self-managed architectures often trade a lower cloud invoice for higher engineering effort. Managed platforms typically carry higher service prices while offloading portions of patching, control plane, upgrades, or on-call work. Measure that reduction rather than assuming it.

A labor conversion model:

~~~text
annual_operations_cost =
  engineers_involved
  * average_hours_per_month
  * loaded_hourly_rate
  * 12
~~~

Break down operational activities:

| Activity | Questions |
| --- | --- |
| Patching/upgrades | How many hours/month and how many maintenance/outage events? |
| Capacity management | Who tracks peaks, quotas, and scaling? |
| Incident response | Incident count, on-call coverage, and recovery time? |
| Backup/DR | How often are restores/failovers tested, and by how many people? |
| Security/compliance | Hours spent on access reviews, evidence, and remediation? |
| Release/platform | Cost of maintaining pipelines, modules, and clusters? |

Do not assign 100% of an engineer's time to one option if they also support other organizational work. Distinguish incremental cost, opportunity cost, and sunk/fixed costs.

## 10. Building Comparable Architecture Options

Each option must specify topology, assumptions, SLOs, failure modes, operating model, and cost drivers—not merely product names.

Example three options for the booking platform:

| Dimension | A: Self-Managed VMs/Containers | B: Managed Container Platform | C: Serverless/Event-Driven |
| --- | --- | --- | --- |
| Compute | VMs/clusters operated by the team | Managed cluster/runtime | Functions/managed services |
| Scaling | Team-configured autoscaling | Platform-assisted scheduling/autoscaling | Automatic scaling per invocation/event within quotas |
| Database | Shared managed DB | Comparable managed DB | Managed DB/serverless tier or compatible data service |
| Events | Self-managed/managed broker | Managed broker | Integrated event service/queues |
| Operations | Heavy infrastructure responsibility | Moderate | Minimal compute management, heavier integration and quota management |
| Cost sensitivity | Node utilization, standbys, licenses | Node/pod density, platform fees | Invocations, duration, concurrency, provisioned capacity |
| Key risks | Patching, capacity, and cluster ops | Platform complexity, upgrades, node waste | Cold starts, vendor limits, duration/egress, and observability |

All options must satisfy the same functional scope, security baseline, data residency, SLOs, and RTO/RPO. If Option A is multi-zone while Option C runs single-zone, cost is not an apples-to-apples comparison.

## 11. Modeling by Load Scenario

Include at least three scenarios:

| Scenario | Description | Purpose |
| --- | --- | --- |
| Low/slower adoption | Slow user growth, low load | Test baseline cost floor and avoidance of overprovisioning |
| Base/expected | Grounded in supported forecast | Planning budget |
| High/growth | Rapid growth, large peaks, or campaigns | Test scalability, quotas, and marginal cost |

You can add stress or disruption scenarios: zone loss, regional failover, cache cold starts, retry storms, or bot traffic. These events increase not just traffic, but also cost curves and required headroom.

### 11.1. Example Assumption Table

| Driver | Low | Base | High |
| --- | ---: | ---: | ---: |
| Monthly requests | 60 million | 120 million | 240 million |
| Peak/base ratio | 4x | 8x | 12x |
| Data growth/month | 60 GB | 120 GB | 240 GB |
| Cache hit ratio | 92% | 85% | 75% |
| Cross-region transfer | Low | Medium | High |
| Support/operation effort | 20 h/month | 35 h/month | 55 h/month |

These figures are purely hypothetical. The High case can more than double costs because peak ratios climb, hit ratios fall, and extra reserve capacity is needed.

## 12. Comparing TCO and Unit Economics

TCO shows total financial resources committed over the horizon. Unit economics shows cost per unit of business value/activity.

Selectable unit examples:

- Cost per completed booking.
- Cost per 1,000 valid search requests.
- Cost per active tenant/month.
- Cost per GB stored and served.
- Cost per successfully processed event.

~~~text
cost_per_completed_booking =
  total_platform_cost / completed_bookings

cost_per_1k_searches =
  total_search_related_cost / eligible_searches * 1000
~~~

Denominators must reflect valid outcomes. When bookings fail due to system errors, dividing total cost by successful bookings raises unit cost—and that is a valuable signal; never strip failures out of metrics just to flatter the numbers.

### 12.1. Do Not Compare Unit Costs Across Different Scopes

Align on:

- Are shared platform costs included?
- Are backups, observability, and security included?
- Do bookings share the same definition of "completed"?
- How is bot/test traffic filtered?
- Are labor and migration costs allocated?

## 13. One-Way Sensitivity Analysis

Sensitivity analysis varies one assumption while holding others constant to reveal which variables swing results the most.

Example variables:

- Request volume ±30%.
- Peak/base ratio from 4x to 12x.
- Cache hit ratio from 70% to 95%.
- Storage growth ±50%.
- Egress unit price ±20%.
- Loaded engineering hours ±25%.
- Standby capacity from 20% to 100%.

### 13.1. Illustrative Sensitivity Table

Suppose the 36-month base TCO is 1,000,000 currency units. The ranges below are illustrative examples:

| Variable | Low Value | Base | High Value | Illustrative Resulting TCO |
| --- | ---: | ---: | ---: | ---: |
| Request volume | -30% | 0% | +30% | 900k / 1,000k / 1,120k |
| Egress price | -20% | 0% | +20% | 970k / 1,000k / 1,030k |
| Cache hit ratio | 95% | 85% | 70% | 970k / 1,000k / 1,100k |
| Data growth | -50% | 0% | +50% | 960k / 1,000k / 1,070k |
| Operations hours | -25% | 0% | +25% | 940k / 1,000k / 1,080k |

Actual resulting TCO must be computed from the real cost model. This table merely illustrates presentation format and shows why request volume is not always the sole dominant driver.

### 13.2. Tornado Chart

A tornado chart orders variables from largest to smallest impact:

~~~text
TCO impact (illustrative)
Request volume       |<-------------------->
Cache hit ratio          |<---------------->
Operations effort            |<------------>
Data growth                     |<-------->
Egress price                       |<---->
~~~

Variables at the top of the chart deserve sharper measurement, explicit forecasting, and close monitoring. You do not need identical precision for every single input.

## 14. Multi-Variable Sensitivity and Monte Carlo

In reality, request volume, cache hits, storage growth, and egress often correlate. Higher traffic can raise cache hit rates when hot items dominate, or lower them if query diversity/cardinality increases. One-way analysis cannot capture those interactions.

### 14.1. Scenario Matrix

Build three or more coordinated scenarios:

| Scenario | Request Growth | Cache Hit | Data Growth | Operations Effort |
| --- | ---: | ---: | ---: | ---: |
| Efficient growth | +30% | 92% | +20% | +10% |
| Expected | +50% | 85% | +40% | +20% |
| Stress growth | +100% | 70% | +80% | +50% |

This provides consistent assumption bundles rather than probabilistic forecasts. Document why the variables move together.

### 14.2. Conceptual Monte Carlo

Monte Carlo runs thousands of trials by sampling from input distributions to produce a distribution of TCO outcomes. For instance, request volume might follow a triangular distribution around low/base/high; egress price has bounds; incident hours follow their own distribution.

Process:

1. Select key drivers and defensible distributions.
2. Specify correlations among variables where present.
3. Sample inputs for each trial.
4. Compute TCO via the same formula.
5. Repeat enough times and inspect median, percentiles, and tail risk.
6. Compare options on median and the cost percentile the organization cares about.

Never invent probability distributions purely to feed numbers into a tool. When data is sparse, use ranges/scenarios and communicate uncertainty openly rather than fabricating false precision.

## 15. Break-Even and Decision-Flip Thresholds

One option may be cheaper at low traffic yet more expensive above a threshold. Break-even analysis finds where cost curves intersect.

Simple example:

~~~text
Option A cost = fixed_A + variable_A * workload
Option B cost = fixed_B + variable_B * workload

Break-even workload =
  (fixed_B - fixed_A) / (variable_A - variable_B)
~~~

Use this formula only when units and linearity assumptions hold, the denominator is non-zero, and workload stays within model bounds. Real-world tiered pricing, autoscaling steps, quotas, minimum fees, and discounts create non-linear cost curves.

### 15.1. Interpretation Example

Option A has a cheap baseline yet high cost/request; Option B needs a pricier minimum cluster yet has lower cost/request. At low load A wins; past break-even, B gains the advantage. When growth forecasts are uncertain, also factor in switching feasibility, migration cost, and capacity risk.

## 16. Bringing Reliability and Risk Into the Same Model

Do not choose the cheapest option if it misses business targets. Comparisons must check:

| Dimension | Questions |
| --- | --- |
| Availability | Does it meet SLOs across defined failure domains? |
| RTO/RPO | How long do restores/failovers take, and how much data can be lost? |
| Performance | Do p95/p99 hold during peaks and failovers? |
| Security | Do IAM, networking, encryption, auditing, and patching meet baseline? |
| Scalability | Can it scale within quotas and required timeframes? |
| Operability | Does the team have the skills, tools, and on-call capacity to run it? |
| Vendor/portability | How deep is proprietary lock-in and what is the exit cost? |
| Sustainability | How do idle resources, utilization, data transfer, and workload efficiency look? |

### 16.1. Cost of Downtime

You can add downtime impact to the analysis:

~~~text
expected_downtime_cost =
  incident_frequency
  * average_duration
  * business_impact_per_time_unit
~~~

This is a simple expected-value estimate—be cautious with small sample sizes and tail incidents. Separate quantified downtime costs from hard-to-monetize legal, reputational, or safety risks. A higher-TCO architecture can still be the rational choice if it eliminates unacceptable risk.

## 17. Cost and Environmental Sustainability

Low financial cost and low environmental footprint often align via higher utilization, fewer idle resources, and reduced unnecessary data movement, though they are not always identical. A cheaper region or service may carry a different emissions factor; low-latency workloads may force placement near users.

Factors to evaluate:

- CPU/memory utilization and idle hours.
- Right-sizing and autoscaling.
- Ephemeral environment creation frequency and cleanup delays.
- Duplicate data, retention, and lifecycle tiering.
- Network egress and cross-region transfers.
- Sensible caching to cut compute/data retrieval, accounting for cache overhead.
- Region choice balancing latency, residency, availability, price, and available emissions data.
- Processing efficiency per transaction/booking rather than total resources alone.

### 17.1. Resource Efficiency Indicators

Track:

- vCPU-seconds or GB-memory-hours per completed booking.
- GB egress per 1,000 valid requests.
- kWh or carbon estimate per unit of work when provider/methodology offers reliable data.
- Resource utilization rate and idle capacity ratio.
- Share of data transitioned to appropriate storage tiers.

When reporting carbon estimates, document factor sources, scope (location-based/market-based where methodology distinguishes them), timeframe, and margin of error. Never present proxy-derived estimates as direct measurements.

## 18. Pricing Data Reliability and Uncertainty Management

Cloud prices vary by region, time, currency, tier, discount, enterprise agreement, and traffic type. Record:

- Assumed provider/service/region and SKU or tier.
- Currency, billing unit, and price lookup date.
- On-demand vs. commitment/reserved/savings plan.
- Discount eligibility, usage commitments, and termination terms.
- Time-limited free tiers/credits—never treat them as zero long-term cost.
- Taxes/support fees if within scope.
- Price volatility and who is responsible for refreshes.

### 18.1. Confidence Classes

| Confidence Level | Source | Usage |
| --- | --- | --- |
| High | Actual invoices/usage, contract quotes, or verified SKU prices | Base estimate |
| Medium | Calculators/exports with near-production configurations | Planning estimate |
| Low | Benchmarks, utilization assumptions, or unmeasured traffic | Ranges/scenarios requiring verification |

Estimates should express ranges and confidence. For example, 36-month TCO might be 0.9–1.2 million currency units with a base of 1.03 million; presenting this is more honest than a long decimal implying false precision.

## 19. Modeling and Decision Process

~~~mermaid
flowchart TD
    R["Business requirements and SLO"]
    W["Workload / data / traffic baseline"]
    A["Define comparable architecture options"]
    C["Build cost-driver model"]
    S["Scenario and sensitivity analysis"]
    Q["Check reliability, security, sustainability"]
    D["Decision and ADR"]
    M["Measure actual cost and recalibrate"]
    R --> W --> A --> C --> S --> Q --> D --> M
    M --> W
~~~

Execution steps:

1. Lock business outcomes, SLOs, RTO/RPO, and scope.
2. Gather workload profiles and data growth.
3. Define architectural options meeting identical requirements.
4. List cost drivers and pricing sources.
5. Produce monthly and full-horizon base estimates.
6. Run low/base/high scenarios and sensitivity on key drivers.
7. Evaluate break-even, reliability, security, operations, and sustainability.
8. Document assumptions, exclusions, uncertainty, and risks.
9. Choose an option or propose a prototype/load test to shrink uncertainty.
10. Post-deployment, compare forecasts against actual invoices/usage and recalibrate the model.

## 20. Practice Exercise: Comparing Three Options for the Booking Platform

**Hypothetical scenario:** The platform handles 120 million requests/month, peak at 8x average, 120 GB of new data/month, 24-month retention, multi-zone database, cross-region backups, and a 99.9% availability target for bookings. The team is evaluating self-managed VMs/containers, a managed container platform, and serverless/event-driven.

### Tasks

1. Verify the workload baseline and document the source/confidence of each input.
2. Describe the topology for all three options: compute, database, cache, queues, networking, observability, and DR.
3. Build a cost-driver tree for each option.
4. Compute 12-, 24-, and 36-month TCO; separate one-time, fixed, variable, operations, and resilience costs.
5. Compute cost per 1,000 search requests and per completed booking.
6. Run low/base/high scenarios and sensitivity for traffic, cache hits, egress, data growth, node utilization, and operations hours.
7. Identify break-even workloads across the options.
8. Evaluate RTO/RPO, failure modes, and remaining capacity when losing a zone/region.
9. Evaluate sustainability using utilization and resources per unit of work; state emissions data limitations.
10. Compare uncertainty, lock-in, migration costs, and operational skills.
11. Write an ADR covering the chosen option, rejected options, assumptions, risks, and revisit conditions.

### TCO Table Template

| Cost category | Option A | Option B | Option C | Source/confidence |
| --- | ---: | ---: | ---: | --- |
| Compute baseline/peak | Input | Input | Input | SKU/usage |
| Database/storage/backup | Input | Input | Input | Tier/GB/IOPS |
| Network/CDN/egress | Input | Input | Input | GB/request/region |
| Platform/security/observability | Input | Input | Input | Service pricing |
| Operations labor | Input | Input | Input | Hours/rate |
| DR/standby/replication | Input | Input | Input | RTO/RPO topology |
| Migration/parallel run | Input | Input | Input | One-time estimate |
| Total 36-month TCO | Formula | Formula | Formula | Model version |

### Completion Criteria

- All options use the same workload, SLO, security, and DR baseline.
- TCO separates recurring, variable, one-time, and operations costs.
- Unit economics use consistent business outcomes and denominators.
- Includes low/base/high scenarios, one-way sensitivity, and key variable interactions.
- Break-even is computed within valid assumption bounds.
- Clearly states price sources, dates, currencies, discounts, and confidence.
- Cost is never optimized by stripping mandatory security or reliability controls.
- Sustainability metrics have explicit scope and confidence boundaries.
- ADR documents assumptions, exclusions, risks, and revisit triggers.

## 21. Well-Architected Checklist Before Approving an Architecture Cost Estimate

- [ ] Options share the same workload baseline and functional scope.
- [ ] Peak, average, burst, concurrency, and growth are modeled separately.
- [ ] SLOs, RTO/RPO, security, and data residency are shared comparison constraints.
- [ ] TCO includes compute, data, networking, platform, security, operations, resilience, and migration.
- [ ] Fixed, variable, one-time, and indirect costs are separated.
- [ ] Databases, backups, replicas, IOPS, log retention, and data lifecycles are included.
- [ ] Egress, cross-zone/region transfers, NAT, CDN, and private endpoints follow data flows.
- [ ] Autoscaling, utilization, and headroom are modeled against the workload profile.
- [ ] Observability, SIEM, KMS, WAF, registry, and CI/CD costs are evaluated.
- [ ] Operations labor and team skills are factored in with explicit assumptions.
- [ ] TCO spans multiple horizons alongside business-outcome unit costs.
- [ ] Low/base/high scenarios, sensitivity, and break-even analyses are included.
- [ ] High-impact variables are measured or have plans to reduce uncertainty.
- [ ] Prices list source, region, currency, date, billing unit, and discount assumptions.
- [ ] Downtime/risk is weighed alongside investment cost, never ignored when hard to quantify.
- [ ] Sustainability is evaluated via utilization, data movement, and efficiency per unit of work.
- [ ] An ADR records assumptions, exclusions, confidence, risks, and revisit triggers.
- [ ] A post-launch process compares forecasts against actual usage/invoices and recalibrates the model.

**Core takeaway:** Architecture cost estimation is trustworthy only when options are compared on an identical baseline and service level. TCO must capture compute, data, networking, security, resilience, operations, and migration; unit economics links cost to business outcomes; sensitivity and break-even show where conclusions flip. Documenting price sources, assumptions, uncertainty, and post-deployment actuals keeps cost decisions verifiable and continuously updated across the architecture lifecycle.
