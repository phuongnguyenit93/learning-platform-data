# Estimating Users, Traffic, Data Volume, and Growth Rate

A cloud design must answer two questions before choosing services or machine sizes: **how much load must the system handle**, and **how does that load change over time**? The answers directly affect choices across compute, databases, caches, queues, networking, scaling mechanisms, fault tolerance, and budget.

In the **architecture requirements** phase, estimation is the process of turning business objectives into quantities that can be measured, verified, and used for decision-making. Initial figures may not be exact; what matters is stating assumptions, units, variation ranges, and how they will be verified. A forecast of "one million users" is not enough to determine how many resources a system needs.

## 1. What Needs to Be Estimated?

| Metric | Meaning | Architectural Question to Answer |
| --- | --- | --- |
| Registered users | Total accounts created, including inactive ones | Profile data scale and account lifecycle? |
| MAU (Monthly Active Users) | Users active within a month | Product scale and long-term growth? |
| DAU (Daily Active Users) | Users active within a day | Workload volume on a typical day? |
| Sessions/day and actions/session | Intensity of usage per user | How many API calls, transactions, and events occur? |
| RPS/QPS/TPS | Requests, queries, or transactions per second; must specify which layer is measured | How much load do APIs, databases, and supporting systems handle? |
| Concurrency | Active sessions, in-flight requests, or open connections | How many concurrent resources are needed? |
| Bandwidth and transfer volume | Bytes/second at peak and bytes/month | Networking, CDN, load balancers, and data transfer cost? |
| Data volume | Existing data, new growth, indexes, replicas, backups | Storage capacity, backup strategy, data tiering? |
| Growth rate | Rate of change in users, requests, data, and payload sizes | When will scaling or architectural changes be needed? |

These numbers **are not interchangeable**. For instance, 100,000 DAU can generate dozens or thousands of RPS depending on actions per user, API calls per action, and time-of-day concentration. Similarly, 10,000 users having the app open does not mean 10,000 HTTP requests are hitting the server simultaneously.

Every measurement should be tied to a **component and system boundary**: requests at the CDN, requests reaching the API gateway, requests entering the application, and queries hitting the database are usually four distinct figures. Distinguish ingress from egress traffic, especially when estimating cloud costs.

## 2. Turn Business Requirements into Calculable Assumptions

Before applying formulas, describe the main journeys: login, browsing listings, searching, booking, paying, uploading files, background sync, and receiving notifications. Each journey has a different usage profile and processing cost.

An input assumptions table should include:

| Category | Information to Gather | Preferred Sources |
| --- | --- | --- |
| Scale | Current DAU/MAU, 3–12–24 month targets, segments and regions | Analytics, business metrics, product forecasts |
| Behavior | Sessions/user/day, session duration, actions/session, feature frequency | Product analytics, surveys, prototypes |
| Application | API calls per action, request/response sizes, retries and polling | API logs, tracing, real client measurements |
| Time distribution | Peak hours, days of week, seasonality, campaigns, simultaneous events | Historical minute/hour charts, marketing plans |
| Data | New records generated, actual row size, attachments, indexes, retention | Schemas, sample data, retention policies |
| Service quality | Latency SLOs, error rates, availability, RPO/RTO | Business requirements and operational commitments |

For a greenfield system without historical data, derive assumptions from user journeys and build **three scenarios: low / baseline / high**. Label the confidence of each assumption; for example, DAU from analytics has higher confidence than requests/session inferred from interviews.

### Group by Workload Type

Do not lump every request into a single bucket. A minimal design usually separates:

- **Interactive reads:** viewing content, lookups, search; typically latency-sensitive and cacheable.
- **Transactional writes:** booking, payment, state updates; require consistency, deduplication, and recoverability controls.
- **Background jobs:** syncing, sending emails, image processing, report generation; typically handled asynchronously via queues.
- **File and media transfer:** uploading/downloading images/video/documents; byte volume can be large even when request counts are low.
- **Real-time streams:** WebSockets, streaming, live notifications; connection count and connection duration may matter more than RPS.

For example, one user click on "Book Now" may generate a single HTTP request while triggering multiple database, queue, and external service operations. Therefore, calculate **load per layer**, never equating API RPS with database QPS.

## 3. Calculating Requests, Peaks, and Concurrency

Assume:

- \(D\): daily active users (DAU).
- \(S\): average sessions per user per day.
- \(A\): average API calls per session, including relevant background requests.
- \(B\): peak-to-average concentration factor for the peak hour/minute compared to the daily average.
- \(C\): campaign-day multiplier relative to a normal day.

Assuming relatively uniform usage across user cohorts:

\[
N_{\text{day}} = D \times S \times A
\]

\[
RPS_{\text{avg}} = \frac{N_{\text{day}}}{86\,400}
\]

\[
RPS_{\text{normal peak}} \approx RPS_{\text{avg}} \times B
\]

\[
RPS_{\text{campaign peak}} \approx RPS_{\text{avg}} \times B \times C
\]

The factor \(B\) should come from actual traffic charts—for example, the ratio between peak RPS in a **1- or 5-minute window** and the daily average RPS. The factor \(C\) is only used to represent an uplift **not already included in the baseline data**; if DAU already reflects campaign-day DAU, do not multiply by \(C\) again. An hourly peak factor also cannot capture multi-second spikes during flash ticket drops or broadcast notifications: those cases require checking peaks at shorter time resolutions.

If splitting reads and writes by ratios \(p_{\text{read}}\) and \(p_{\text{write}}\):

\[
RPS_{\text{read}} = RPS_{\text{total}} \times p_{\text{read}}, \qquad
RPS_{\text{write}} = RPS_{\text{total}} \times p_{\text{write}}
\]

To forecast database load, multiply further by the number of queries actually reaching the database per request. Subtract queries served by cache and add secondary queries, retries, or background jobs; cache hit ratios can fluctuate sharply right after deployment or cache expiration.

### Two Easily Confused Concurrency Concepts

**Concurrent active sessions** can be roughly estimated from daily sessions and session duration:

\[
\text{Average concurrent sessions}
\approx \frac{\text{sessions/day} \times \text{session duration (seconds)}}{86\,400}
\]

**Concurrent in-flight requests** use Little's Law when the system is in steady state:

\[
L \approx \lambda \times W
\]

Where \(L\) is the number of in-flight requests, \(\lambda\) is requests/second, and \(W\) is average processing time in seconds. For example, 400 RPS with an average response time of 0.25 seconds corresponds to roughly **100 in-flight requests**, not 400 users. This is a steady-state approximation; if queues back up or requests hang, waiting counts can surge rapidly. For WebSockets, measure concurrent connections and memory per connection separately.

## 4. Calculating Network Traffic and Bandwidth

Request count and byte volume reflect two different pressures. An API returning small JSON payloads may sustain high RPS with low bandwidth; video delivery may have low request counts yet consume heavy egress.

\[
\text{Egress/day (bytes)} =
\sum_i N_{i,\text{day}} \times \text{average response bytes}_i
\]

\[
\text{Peak egress bandwidth (bit/s)}
\approx RPS_{\text{peak}} \times \text{response bytes/request} \times 8
\]

When using decimal KB, MB, and GB: 1 KB = 1,000 bytes, 1 GB = \(10^9\) bytes. If using KiB, MiB, and GiB, the factors are 1,024; state units explicitly to avoid discrepancies.

When budgeting and sizing networks, also include:

- Actual payload after compression, headers, TLS, and protocol overhead; measure at the exact boundary corresponding to the cost item being forecasted.
- Cache/CDN hit ratios and origin fetch rates: bytes delivered to users can differ from bytes leaving the origin.
- Uploads, downloads, cross-region/cross-Availability-Zone traffic, data replication, backups, and inter-service traffic.
- Unusually large payloads, retries, duplicate downloads, WebSockets, and separate media streams.

Never use monthly average throughput to check for bottlenecks during minute- or second-level peaks. Conversely, never multiply peak bandwidth by the seconds in a month to forecast your bill: use traffic distribution curves or time-bucketed assumptions.

## 5. Estimating Data Volume and Storage Lifecycle

For a data type generated at a relatively steady rate:

\[
\text{Raw volume/day}
= \text{new records/day} \times \text{bytes/record}
\]

\[
\text{Volume with indexes/overhead}
\approx \text{raw volume} \times k
\]

\[
\text{Volume retained for } T \text{ days}
\approx \text{volume/day} \times T
\]

The factor \(k\) must be measured on sample data, because indexes, MVCC, fragmentation, and encoding vary by engine. The \(T\)-day retention formula assumes steady growth and that deleting old data actually frees or allows reuse of space; if traffic is growing, sum across individual time intervals.

Do not lump storage components together before explaining their nature:

| Component | What to Estimate |
| --- | --- |
| Business records | Row counts, record size, update/delete patterns, regulatory retention |
| Indexes and metadata | Indexes, page overhead, version history, tombstones, fragmentation |
| Logs, metrics, traces, audits | Events/second, bytes/event, sampling rate, retention |
| Objects and media | File sizes, copy/version counts, lifecycle policies |
| Replicas | Number of replicas for HA/reads; include full physical storage |
| Backups and PITR | Snapshots, incremental backups, recovery logs, retention window |
| Caches | Working set and memory overhead; distinct from durable storage |

If you run one primary and two read replicas each holding the full dataset, do not count only the primary's capacity when forecasting storage. Likewise, incremental snapshots do not necessarily occupy a full copy every day; costs depend on changed blocks, snapshot frequency, and retention duration. Forecast backups using real samples or provider calculators.

Beyond **total GB**, estimate **reads/writes per second, IOPS, query sizes, throughput, working set, transaction locks, and latency**. Two 500 GB databases may demand completely different architectures if one runs sequential batch reads while the other executes thousands of random transactions per second.

## 6. End-to-End Example: Booking Application

A booking application operating across multiple regions is preparing for a growth campaign. The project team builds an *illustrative* assumptions table—these are not real measurements or commitments from any cloud provider.

| Assumption | Value |
| --- | ---: |
| Normal-day MAU / DAU | 300,000 / 60,000 users |
| Sessions per DAU per day | 1.5 |
| HTTP API requests per session | 24 |
| Session duration | 8 minutes |
| Normal-day peak factor \(B\) | 8x daily average |
| Campaign day \(C\) | 2x normal-day load |
| API read / write split | 85% / 15% |
| Average egress data / API response | 25 KB, decimal |
| New booking records | 0.12 records/DAU/day |
| Size per booking record | 2 KB raw; index/overhead factor 1.5 |
| Analytics events | 10 events/DAU/day, avg 1 KB/event |
| Retention | Booking records: 3 years; events: 90 days |
| Media storage | 400 GB existing; projected +40 GB/month |

### Step 1 — Derive Requests and Peaks

On a normal day:

1. Sessions/day = \(60,000 \times 1.5 = 90,000\) sessions.
2. API requests/day = \(90,000 \times 24 = 2,160,000\) requests.
3. Average RPS = \(2,160,000 / 86,400 = 25\) RPS.
4. Normal-day peak = \(25 \times 8 = 200\) RPS.
5. Campaign-day peak = \(25 \times 8 \times 2 = 400\) RPS.

At campaign peak, assuming the operation ratio holds, the application receives roughly **340 read RPS** and **60 write RPS**. This is API-layer traffic; SQL query counts must be measured separately.

| Scenario | Requests/day | Average RPS | Assumed Peak RPS |
| --- | ---: | ---: | ---: |
| Normal day | 2,160,000 | 25 | 200 |
| Campaign day, 2x load | 4,320,000 | 50 | 400 |

Average concurrent active sessions on a normal day is \(90,000 \times 480 / 86,400 = 500\) sessions. If session distribution follows the peak factor of 8, there are about **4,000 active sessions at normal-day peak**, or **8,000 sessions at campaign peak**. Meanwhile, at campaign peak with a 0.25-second average response time, estimated in-flight HTTP requests are \(400 \times 0.25 = 100\). The three numbers—8,000, 400, and 100—measure three distinct things.

### Step 2 — Derive Bandwidth and Bytes/Month

With an average response of 25 KB:

- Normal-day API egress: \(2,160,000 \times 25,000 = 54,000,000,000\) bytes, equal to **54 GB/day**.
- If all 30 days resemble a normal day: **1.62 TB/month**, excluding media, CDN, and other egress types.
- Egress bandwidth at campaign peak: \(400 \times 25,000 \times 8 = 80,000,000\) bit/s, or roughly **80 Mb/s** at the assumed measurement boundary.

This is the result of using an **average payload**. When sizing networks or estimating bills, substitute measured payload distributions, separate CDN-served traffic, and add other relevant transfer paths. For example, image files should not be assumed to fit inside the 25 KB API response.

### Step 3 — Derive Storage Capacity

**Bookings:** \(60,000 \times 0.12 = 7,200\) new records/day. At 2 KB/record and a 1.5x overhead factor, estimated daily growth is \(7,200 \times 2 \times 1.5 = 21,600\) KB, or **21.6 MB/day**. Retaining three 365-day years at constant load equals roughly **23.65 GB** of data and indexes before replicas/backups.

**Analytics events:** \(60,000 \times 10 = 600,000\) events/day, generating roughly **600 MB raw data/day**. Retaining only 90 days at steady generation yields about **54 GB raw**; this excludes indexes, compression, metadata, replicas, and backups.

**Media:** 400 GB existing plus 40 GB/month yields roughly **880 GB after 12 months** before replication, versioning, and lifecycle policies. Media size and retention can dominate the storage bill even when transactional data is relatively small.

From these numbers, the architect can separate the transactional database, event/analytics store, and object storage, then choose appropriate retention, backup, hot/cold access, and partitioning policies.

### Step 4 — Translate Load into Compute and Fault-Tolerance Assumptions

Suppose a **load test on the actual application** shows one instance sustainably serves 150 RPS within the target SLO latency. To keep target utilization at 65% of measured capacity:

\[
\text{Design capacity/instance} = 150 \times 0.65 = 97.5\ \text{RPS}
\]

\[
\text{Instances for throughput}
= \left\lceil \frac{400}{97.5} \right\rceil = 5
\]

**Five instances satisfy only the throughput math**; they do not prove availability. If required to survive the complete loss of one of three Availability Zones, one candidate layout to test is **8 instances distributed 3–3–2**: losing the 3-instance zone still leaves 5 instances with estimated capacity \(5 \times 97.5 = 487.5\) RPS. Actual design also depends on load balancing, database capacity, quotas, network connections, autoscale ramp-up time, cross-zone latency, and post-failover testing.

You cannot infer vCPU/RAM specs from RPS alone. Benchmarks must reflect read/write ratios, payload sizes, backend queries, caching, p95/p99 latency, CPU, RAM, I/O, and real workload bottlenecks.

## 7. Forecasting Growth and Building Scenarios

With a per-period growth rate \(g\), a simple projection is:

\[
V_t = V_0 \times (1+g)^t
\]

Where \(V_0\) is the initial value and \(t\) is the number of periods. For example, if DAU grows **20% per quarter** for four quarters, the annual multiplier is \(1.2^4 \approx 2.074\). If usage behavior stays constant, a 400 RPS campaign peak could become roughly **829 RPS** after 12 months. However, data retention, records per user, payloads, and cache hit rates can grow along different curves; do not automatically multiply every metric by the same factor.

Evaluate at least three scenarios:

| Scenario | Dominant Assumptions | Decisions to Test |
| --- | --- | --- |
| Low | Slow growth, stable requests/session | Minimum resource footprint, fixed costs |
| Baseline | Most credible product forecast; includes seasonality | Operating budget and upgrade schedule |
| High / Spike | Successful campaigns, simultaneous events, increased retries | Autoscaling, queues, rate limiting, redundancy, and load ceilings |

Beyond percentage growth, describe **feature changes**. For example, adding auto-refresh every 10 seconds raises request volume even if DAU stays flat. Adding video can alter egress and storage by orders of magnitude. Increasing transactional writes can turn the primary database into a bottleneck before API servers hit CPU limits.

For data with finite retention, forecast by time slices:

\[
\text{Retained data at } t
\approx \sum_{d=t-T+1}^{t} \text{data generated on day } d
\]

This formula shows that a log dataset with a 90-day retention policy still grows while traffic is rising, yet does not grow linearly forever like undeleted business records. Add mandatory historical archives, cold storage, and backup restore footprint separately.

## 8. From Estimation Tables to Architecture Choices

Calculations serve as inputs for **Well-Architected** evaluations, always weighing reliability, security, performance, operations, and cost together.

| Insight from Workload | Design Implication to Evaluate | Trade-offs to Verify |
| --- | --- | --- |
| High read RPS, rarely changing data | CDN/cache, query indexes, read replicas | Data freshness, cache invalidation, replica cost |
| Spiky write RPS | Queues, concurrency control, idempotency, backpressure | Completion latency, ordering, consistency |
| Multi-second bursts far exceed hourly peaks | Rate limiting, preloading, early autoscaling, queues | Warm-up time, downstream limits |
| Large media, regional access | Object storage and CDN | Egress cost, geographic distribution, access control |
| Fast-growing events, rare immediate access | Retention, compression, hot/cold tiering | Re-query speed and retention cost |
| Critical business data | Replication, backups, restore testing, RPO/RTO | Cost, latency, and blast radius |
| Quarterly throughput growth | Autoscaling and quota forecasting | Scale-out lag, idle capacity cost |

In particular, **security and compliance** requirements affect replica counts, storage regions, and retention periods. Never "solve growth" by keeping all logs indefinitely or replicating personal data endlessly. Designs must specify access permissions, encryption, data deletion lifecycles, and recovery plans.

## 9. Verifying Assumptions and Updating Forecasts

A useful workflow is:

~~~mermaid
flowchart LR
    A["Business objectives"] --> B["User journeys and behavior"]
    B --> C["DAU, requests, bytes, data"]
    C --> D["Peaks, growth, scenarios"]
    D --> E["Sizing and architectural options"]
    E --> F["Load tests, live metrics, chaos/failover tests"]
    F --> G["Adjust assumptions and budget"]
    G --> C
~~~

Measure at least **minute- and second-resolution RPS**, p50/p95/p99 latency, error rates, CPU/RAM utilization, DB QPS and connections, cache hit rates, queue depth/lag, ingress/egress bytes, and storage footprint. Load tests should include ramp-ups, short spikes, sustained steady load, and post-spike recovery. Results must tie back to SLOs, because "the system handled 1,000 RPS" is meaningless if most requests timed out.

During load tests:

1. Simulate realistic journey proportions, datasets, and payloads; avoid hitting only one lightweight endpoint.
2. Measure **steady state** at each load tier, inspecting latency and errors before claiming sustainable throughput.
3. Record the first bottleneck hit: application, database, cache, connection pool, queue, network, or external service.
4. Test autoscaling and failover; verify remaining capacity after losing an instance/zone and measure recovery time.
5. Update the assumptions table with measured numbers along with test date, scope, and confidence level.

A simple decision tracking table template:

| Metric | Current Baseline | 12-Month Forecast | Peak to Sustain | Source / Confidence |
| --- | --- | --- | --- | --- |
| DAU | … | … | … | Analytics / high |
| API RPS | … | … | … | Logs + model / medium |
| DB read/write QPS | … | … | … | Tracing + benchmark / medium |
| Egress GB/month | … | … | … | CDN/network metrics / high |
| Database GB | … | … | … | Schema + sample / medium |
| Event/log GB | … | … | … | Telemetry + retention / medium |
| Object storage GB | … | … | … | Storage inventory / high |

Set alerts and review triggers when actuals diverge from forecasts—for example, requests/session rises by 30%, cache hit ratio drops sharply, database nears IOPS limits, or data growth exceeds plan. Specific thresholds should come from benchmarks, SLOs, and the lead time required to add capacity.

## 10. Common Mistakes

- **Using total accounts instead of DAU to calculate RPS:** ignores real activity levels and easily skews sizing.
- **Using average RPS to design for peaks:** ignores hourly distributions, seasonality, and synchronized traffic spikes.
- **Double-counting peak multipliers:** taking campaign-day DAU and multiplying by the campaign factor again.
- **Equating API RPS with database QPS:** ignores caching, fan-out, queries per request, and background jobs.
- **Deriving concurrent users from RPS:** ignores session duration and request processing time.
- **Counting only raw data:** omits indexes, logs, replicas, backups, object versions, and retention windows.
- **Forgetting units:** confusing KB with KiB, Mb/s with MB/s, or one-time transfer with stored data.
- **Applying a single growth rate to all metrics:** user behavior, media volume, and retention can evolve independently.
- **Sizing from ideal benchmarks:** ignores p95/p99 latency, errors, cold starts, quotas, zone outages, and downstream bottlenecks.
- **Treating estimates as commitments:** failing to record sources, confidence, scenarios, and verification mechanisms.

## 11. Self-Check Exercise

An application has 100,000 DAU; each user runs 2 sessions/day, with 15 API calls per session. Peak hour load is 6x the daily average; each response averages 40 KB in decimal units; 20% of requests are writes. Assume no other traffic.

**Questions:** Estimate (1) requests/day, (2) average and peak RPS, (3) API egress/day, (4) write RPS at peak.

**Reference answers:**

1. \(100,000 \times 2 \times 15 = 3,000,000\) requests/day.
2. \(3,000,000 / 86,400 \approx 34.7\) average RPS; peak \(\approx 208.3\) RPS.
3. \(3,000,000 \times 40,000 = 120,000,000,000\) bytes, or **120 GB/day**.
4. \(208.3 \times 20\% \approx 41.7\) write RPS at the API layer. You cannot infer DB write QPS without knowing how many writes each API call triggers.

If asked for an answer ready for an architecture review, do not provide only these four numbers: add **load-distribution assumptions, response-size sources, SLOs, growth scenarios, and a load-testing plan**. Those details determine whether the numbers are trustworthy enough to select a cloud solution.
