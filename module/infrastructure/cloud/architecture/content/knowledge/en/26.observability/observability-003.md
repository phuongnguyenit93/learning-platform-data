# Measuring Business Metrics Alongside Infrastructure and Application Metrics

## 1. Why Look at All Three Metric Layers?

A system can have low CPU, stable memory, and all instances healthy while customers are still unable to book a room. Conversely, CPU can spike during a batch run while users still receive results on time. If you only monitor infrastructure, operations teams can miss business failures; if you only look at revenue or conversion dashboards, they may know results dropped without finding the technical root cause.

**Observability** is the ability to infer the internal state of a system from the signals it emits. Metrics, logs, and distributed traces are three common forms of telemetry; they must be linked with business context to explain what happened and who is affected.

Three layers of observation need to be connected:

- **Business metrics:** is the system delivering the outcomes the business and users need? Examples include successful bookings, payment success rate, captured revenue, and time to confirmation.
- **Application metrics:** are requests and services processing correctly, fast, and reliably? Examples include request rate, error rate, latency, retries, queue age, and dependency timeouts.
- **Infrastructure metrics:** do compute, network, storage, and data platforms have sufficient capacity and operate properly? Examples include CPU, memory, disk I/O, connections, packet loss, and node readiness.

The goal is to connect a business fluctuation to the relevant technical path. When booking rate drops, operations teams can inspect request errors, payment dependencies, database saturation, and queue lag across the same time window, tenant, or processing flow.

In the **CLOUD_ARCHITECTURE** module, observability supports designing for reliability, performance, scalability, security, cost, and operations. Telemetry must reflect both user SLOs and platform limits while avoiding unnecessary collection of sensitive data.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between business metrics, application metrics, and infrastructure metrics.
2. Define KPIs, SLIs, SLOs, and error budgets for a business flow.
3. Use RED and USE to observe services and resources.
4. Design telemetry with appropriate labels/correlation to trace incidents back to root causes.
5. Build dashboards linking business funnels, request paths, and infrastructure.
6. Set alerts based on user impact and error budget burn rate.
7. Avoid high cardinality, misleading metrics, and collecting PII/secrets.
8. Design case studies and runbooks from signals to actions.

## 2. Three Metric Layers and Their Relationships

| Layer | Primary Question | Example Metrics | Audience |
|---|---|---|---|
| **Business** | Are users achieving their goal? Are business outcomes met? | Booking conversion, payment success, net revenue, cancellation rate | Product, business owners, operations |
| **Application** | Are services processing requests/jobs accurately and quickly? | Request rate, error rate, p95 latency, retry count, queue age | Engineering, SRE, service owners |
| **Infrastructure** | Do resources and platforms have sufficient capacity and health? | CPU, memory, disk latency, DB connections, node pressure | Platform, cloud operations, SRE |

The three layers have causal relationships, though they do not always correlate directly:

- Rising CPU may be due to increased traffic, inefficient queries, or leaks; it does not necessarily mean better business outcomes.
- Dropping payment success may be due to card declines at the provider, misconfigured auth, or request timeouts; API CPU stays normal.
- Dropping conversion may be due to UX, pricing, marketing audience, or availability; not every business fluctuation is a technical incident.
- Rising request counts may be a retry storm or bot traffic rather than genuine customer growth.

Therefore, dashboards must display metrics across all three layers, clear measurement definitions, and investigative links between them.

### 2.1. Signal Correlation Model

~~~mermaid
flowchart TD
    Business["Business outcomes<br/>Booking, payment, revenue"] --> App["Application signals<br/>RED, queue, dependency"]
    App --> Infra["Infrastructure signals<br/>CPU, memory, DB, network"]
    Infra --> Capacity["Capacity / bottleneck"]
    Capacity --> App
    App --> Business
    Trace["Trace / logs / correlation IDs"] -. "connect events across layers" .-> Business
    Trace -.-> App
    Trace -.-> Infra
~~~

Telemetry helps connect layers but does not prove causation on its own. To conclude that high CPU caused conversion to drop, inspect the exact request path, timestamps, cohort, and other variables.

## 3. Separating KPIs, Metrics, SLIs, and SLOs

| Concept | Meaning | Example |
|---|---|---|
| **KPI** | Indicator reflecting a business outcome or management target | Monthly booking revenue |
| **Metric** | A measurement with values over time or aggregations | Failed requests per minute |
| **SLI (Service Level Indicator)** | Measurement reflecting the service quality users experience | Proportion of booking requests completing successfully within target latency |
| **SLO (Service Level Objective)** | Quantitative target for an SLI over a time window | 99.9% of booking requests meet success criteria over 30 days |
| **SLA (Service Level Agreement)** | Service commitment to customers/partners, potentially carrying penalties or service credits | Contractual availability commitment |
| **Error budget** | Allowable proportion of SLO misses within the window | 0.1% of requests failing criteria |

KPIs may focus on revenue or growth; SLIs/SLOs focus on service quality that engineering teams can influence. A drop in a KPI does not automatically mean an SLO violation.

### 3.1. SLOs Must Measure What Users Experience

Example SLIs for a booking API:

- **Availability:** proportion of valid requests receiving a successful response or an accepted business state.
- **Latency:** proportion of requests completing under a chosen latency threshold.
- **Correctness:** proportion of create-booking operations that do not violate invariants or return incorrect state.
- **Freshness:** recency of displayed data, such as availability snapshots.
- **Durability/completion:** proportion of accepted operations that eventually reach a valid terminal state within deadline.

Do not count an HTTP 200 as a success if the response body contains a failed business status. Conversely, an HTTP 202 Accepted may count as success at the API boundary if the contract states the work was accepted; a separate SLI is needed to track end-to-end completion.

### 3.2. Example SLI Formula

If there are 100,000 valid booking requests in a window and 99,920 requests meet the success criteria:

\[
SLI = \frac{99,920}{100,000} \times 100\% = 99.92\%
\]

If the SLO is 99.9%, the SLI in this example exceeds the target. However, verify whether excluded requests are justified; excluding too many client errors, timeouts, or dependency failures can artificially inflate the SLI.

## 4. Choosing Business Metrics Around User Journeys

Good business metrics start from user goals and business funnels. Do not pick metrics simply because they are easy to count.

### 4.1. Example Booking Funnel

~~~mermaid
flowchart LR
    Visit["Visit / search"] --> View["View property"]
    View --> Select["Select dates / room"]
    Select --> Checkout["Start checkout"]
    Checkout --> Pay["Payment authorized/captured"]
    Pay --> Confirm["Booking confirmed"]
    Confirm --> Complete["Stay completed"]
    Checkout --> Drop["Abandoned"]
    Pay --> Fail["Payment failed"]
    Confirm --> Cancel["Cancelled / refunded"]
~~~

Each step should have clear event and state definitions:

| Metric | Definition to Standardize |
|---|---|
| Search-to-view rate | Search sessions with at least one property view / valid search sessions |
| Checkout-start rate | Sessions or users starting checkout / eligible funnel group |
| Payment authorization rate | Successful authorizations / valid payment attempts |
| Booking confirmation rate | Confirmed bookings / valid booking requests |
| Cancellation rate | Cancelled bookings / bookings in a defined cohort and period |
| Net booking value | Booking value after adjustments/cancellations/refunds per business accounting rules |
| Time to confirmation | Duration from user request submission to confirmed state |

Denominators and cohorts must be consistent. Do not divide today's confirmed bookings by today's sessions if bookings can originate from prior-day sessions or flows with delays.

### 4.2. Event Semantics and Business State

A booking may transition through REQUESTED, INVENTORY_HELD, PAYMENT_PENDING, CONFIRMED, CANCELLED, or REFUNDED. Business metrics must distinguish between a newly received request, a temporarily held slot, an authorized vs. captured payment, a confirmed booking, a cancelled booking, and whether funds have been refunded.

Counting payment_requested as revenue skews numbers when payments decline or time out. Counting booking_created as booking confirmed can also artificially inflate conversion.

### 4.3. Business Dimensions

Breakdowns can use tenant, property region, channel, platform version, payment method, customer segment, or campaign. Only use dimensions with clear definitions and access controls; avoid putting emails, phone numbers, user names, or unnecessary personal IDs into metric labels.

## 5. Application Metrics: RED and Golden Signals

The RED model fits request-handling services:

- **Rate:** requests per second/minute.
- **Errors:** rate or count of failed requests, broken down by error type.
- **Duration:** distribution of processing time, typically viewing p50/p95/p99.

Some systems add saturation and queue metrics to understand whether a service has hit its limits.

| Metric | Definition | Usage |
|---|---|---|
| http_requests_total | Counter of requests by route/method/status class | Rate and error ratio |
| http_request_duration_seconds | Histogram of request duration | p50/p95/p99 |
| inflight_requests | Number of requests currently in flight | Concurrency and saturation |
| request_retries_total | Number of retries | Detecting retry amplification |
| dependency_duration_seconds | Time spent calling DB/provider/queue | Pinpointing bottlenecks |
| queue_oldest_message_age_seconds | Age of the oldest message | Freshness and worker capacity |

### 5.1. Golden Signals

| Signal | Question |
|---|---|
| Latency | How long must users wait? |
| Traffic | How much demand is the system receiving? |
| Errors | How many requests/jobs are failing? |
| Saturation | Which resource is a component close to exhausting? |

RED and golden signals do not replace business metrics. They describe service health, while business metrics reveal whether services are producing the right outcomes.

### 5.2. Error Classification

Do not lump all errors into a single number:

- 4xx from invalid input or policy rejection.
- 429 from rate limiting/throttling.
- 5xx from service or upstream failures.
- Timeouts and connection resets.
- Business rejections such as sold-out inventory or payment declines.
- Retry exhaustion and dead-lettering.

SLI definitions must explicitly specify which categories count as service failures versus valid business outcomes. For instance, a payment decline is a failure for the conversion funnel, but not necessarily an availability failure of the payment API.

## 6. Infrastructure Metrics: USE and Capacity

USE is a per-resource view:

- **Utilization:** how busy is the resource?
- **Saturation:** is work queuing or waiting because the resource is congested?
- **Errors:** is the resource generating errors?

| Resource | Utilization | Saturation | Errors |
|---|---|---|---|
| CPU | CPU usage/time | Run queue, throttling | CPU steal/throttling events depending on platform |
| Memory | Working set/used memory | Swap, reclaim, OOM risk | OOM kills/abnormal page faults |
| Disk/storage | IOPS/throughput/capacity | Queue depth, latency | Read/write errors |
| Network | Throughput | Queuing/drops/congestion | Packet loss, retransmits, connection resets |
| Database | CPU, connections, storage | Lock wait, connection wait, replication lag | Query errors, failovers, deadlocks |
| Queue/broker | Throughput, storage | Consumer lag, oldest message age | Publish/consume failures, redeliveries |
| Node/cluster | Allocatable CPU/memory | Pending pods, scheduling wait | Node not ready, evictions |

### 6.1. Infrastructure Can Look Healthy While the App Is Saturated

CPU may be at only 40%, yet the thread pool is exhausted, the DB connection pool is depleted, a hot partition is bottlenecked, or an external API quota is hit. Therefore, saturation should be measured where work actually queues up, not only on CPU and memory.

### 6.2. Adding Infrastructure Capacity Can Worsen Business Outcomes

Scaling out more API replicas can increase connections to databases and payment providers. If a dependency is already near its limit, request timeouts and payment failures can rise. Dashboards should display app replica counts, DB connections, dependency latency, and business success side by side.

## 7. Linking Business Events with Requests and Traces

To determine why a booking failed, link business events to requests and participating services.

### 7.1. Correlation Context

A flow may carry these identifiers:

- trace_id: identifies the distributed trace.
- span_id: an operation within the trace.
- request_id: identifies the request at a boundary if used separately.
- booking_id/operation_id: business identifier, logged only when policy permits.
- tenant_id: controlled tenant scope.
- deployment_version: code version handling the request.
- data_interval or partition: for data workloads.

Do not put every identifier into metric labels. Traces/logs can contain selected high-cardinality context if storage and access controls permit; metrics should keep dimensions with controlled cardinality.

### 7.2. Tracing a Booking

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Booking API
    participant DB as Database
    participant P as Payment service
    participant Q as Notification queue
    C->>API: POST /bookings (trace_id)
    API->>DB: Check and hold inventory
    DB-->>API: Hold result
    API->>P: Authorize payment
    P-->>API: Payment result
    API->>DB: Confirm booking + outbox
    DB-->>API: Commit
    API->>Q: Publish confirmation event
    API-->>C: Response
~~~

Traces identify slow or failing spans. Business events confirm whether the booking ultimately succeeded or failed. An HTTP request may succeed while the queue consumer sending the email fails later; traces and operation state must be linked via event/correlation IDs to observe the complete asynchronous flow.

### 7.3. Instrumentation at Boundaries

Start traces at the edge/API gateway; propagate context through HTTP/gRPC/message headers per supported standards; emit spans for DB/HTTP/queue operations; emit business events at commit state; record deployment/version and error classifications. For asynchronous workflows, link trace context through messages or use span links when an event continues from multiple traces.

## 8. Metric Design: Names, Units, Labels, and Cardinality

Metrics need clear definitions so two dashboards do not measure the same name with different denominators.

### 8.1. Metric Contract

| Field | Example |
|---|---|
| Name | booking_confirmations_total |
| Type | Counter |
| Unit | Booking |
| Description | Number of bookings transitioning to CONFIRMED |
| Start/end semantics | Recorded after transaction commit |
| Labels | channel, region, payment_method (bounded value sets) |
| Owner | Booking service team |
| Cardinality budget | Limit on label combinations |
| SLI/KPI mapping | Booking confirmation rate |
| Retention | Per telemetry policy |

### 8.2. Counter, Gauge, and Histogram

- **Counter:** monotonically increases, e.g., total requests or booking confirmations.
- **Gauge:** value that can increase/decrease, e.g., queue depth, active connections.
- **Histogram:** distribution of values across buckets, e.g., request latency or job duration.
- **Summary:** client/implementation-specific quantile aggregation; consider ability to aggregate across replicas.

For system-wide latency, histograms are usually easier to aggregate across instances if buckets are designed consistently.

### 8.3. High Cardinality

If labels contain user_id, booking_id, raw URLs, emails, or exception messages, each new value can create a new time series. The result is rising storage/query costs, slow dashboards, and overloaded telemetry backends.

Best practices:

- Use route templates like /bookings/{id}, not raw URLs containing IDs.
- Use status classes or error categories, not free-form exception messages.
- Do not attach user/booking IDs to metric labels.
- Use traces/logs to drill down into a specific request.
- Restrict labels to dimensions like region, channel, outcome, and service version.
- Monitor time series counts and set cardinality budgets/alerts.

## 9. Multi-Layer Dashboards

An operational dashboard should offer an overview and drill-down paths. Do not pack hundreds of charts that answer no concrete question.

| Section | Content | Questions |
|---|---|---|
| Business outcome | Booking conversion, confirmation, payment success, net value | Are customers achieving their goals? |
| Experience/SLO | Availability, p95/p99 latency, error budget burn | Is service quality meeting commitments? |
| Application path | Request rate, error classes, dependency latency, retries, queue age | Which component is slowing/failing the flow? |
| Infrastructure | CPU, memory, DB connections/locks, I/O, network, node readiness | Which resource is the bottleneck? |
| Change context | Deployments, config, schema, provider incidents | What just changed? |
| Data quality | Freshness, reconciliation, duplicates, missing events | Are business figures trustworthy? |

### 9.1. Dashboards Do Not Replace Investigation

When spotting an anomaly, drill down: pinpoint start time and blast radius; compare the business funnel by channel/region/platform; open application RED metrics and error breakdowns; follow traces to slow/failing dependency spans; check infrastructure saturation, recent deployments, and provider status; determine final business events and the number of affected customers/transactions.

## 10. Alerting on Impact, Not Every Metric

Good alerts are actionable, have an assigned owner, and fire early enough. CPU at 80% may be informational; if the system still meets latency targets without saturation, paging an on-call engineer may not be necessary.

### 10.1. Alerting on SLO / Error Budget

Suppose the availability SLO is 99.9% over 30 days. The proportional error budget is 0.1% of requests in the window. If the error rate rises rapidly, alert on burn rate: the rate at which the error budget is consumed relative to the sustainable pace.

Alerts can combine short and long windows:

- Fast burn over minutes: likely an outage requiring an immediate page.
- Slow sustained burn: create a ticket or notify the team.
- Business conversion drops while technical SLOs remain green: send a product/business alert to investigate the funnel.
- DB saturation rises without impacting SLOs yet: send an early capacity-threshold warning for proactive action.

### 10.2. Example Alert Matrix

| Signal | Illustrative Condition | Action |
|---|---|---|
| Booking SLI | Confirmation rate drops rapidly below SLO | Page booking on-call, inspect funnel/traces |
| Payment success | Drops for a provider/method | Check provider, auth config, and retries |
| API latency | p95 continuously exceeds SLO | Check RED metrics, deployments, and dependencies |
| Queue age | Oldest message exceeds processing SLA | Check worker capacity and provider throttling |
| DB connections | Near limit while pool wait increases | Check for leaks, autoscaling, and queries |
| Disk capacity | Growth trajectory projected to fill before remediation | Expand/clean up per controlled policy |
| Data freshness | Dashboard partition older than SLA | Check orchestration, source watermark, and quality gates |
| Cardinality | Abnormal spike in time series count | Find new/high-cardinality labels and restrict them |

Thresholds in the table are illustrative only. Choose them based on baselines, SLOs, error budgets, capacity tests, and on-call response capacity.

## 11. Defining Business Success and Avoiding Misleading Metrics

A business metric often has several variants; rules must be defined before using it as a KPI or alert.

### 11.1. Gross vs. Net

Revenue example:

- Gross booking value: total value of bookings created under a given definition.
- Captured payment: funds actually captured from the payment provider.
- Refund: funds returned to customers.
- Net revenue/value: result after adjustments per accounting rules and recognition periods.

Do not treat total booking amount as cash collected. Payment authorization does not guarantee capture; refunds may happen days after booking. Standardize timestamps, currencies, timezones, and cohorts.

### 11.2. Conversion Rate

Conversion should use the same cohort and window:

\[
Conversion = \frac{Eligible\ users\ completing\ goal}{Eligible\ users\ entering\ funnel}
\]

If the denominator shifts due to bots, campaigns, or broken event tracking, conversion can fluctuate even when actual user experience has not changed. Monitor event completeness and data quality alongside business metrics.

### 11.3. Guardrail Metrics

Improving one KPI can mask risks elsewhere. When optimizing conversion, monitor cancellation/refund rates, fraud/chargeback signals, duplicate bookings or inventory conflicts, support contact rates, latency/error rates, and data freshness.

Increasing booking counts at the expense of double bookings, refunds, and support tickets is not sustainable success.

## 12. Telemetry for Asynchronous Systems and Data Platforms

For queues and pipelines, request latency cannot represent the entire experience.

### 12.1. Queues / Workers

Measure messages published/consumed/acked; queue depth and oldest message age; consumer lag and processing duration; retries, redeliveries, and dead-letter counts; and final business operation success.

An acked message does not necessarily mean the business operation succeeded if the consumer acks too early. Events should carry the operation ID and committed business state.

### 12.2. Data Pipelines

Measure pipeline/run success rate; data freshness lag vs. source watermark; rows/files read and written; quality failures, missing/duplicate records, and reconciliation deltas; task retries, duration, and queue/scheduler delays; and cost per successful partition/dataset.

A pipeline exiting with code 0 while producing empty data or missing partitions is still a quality failure. Quality gates must be surfaced on dashboards alongside job health.

## 13. Telemetry Security and Privacy

Logs, metrics, and traces can contain sensitive data. Observability platforms centralize data from many services, making them high-value targets.

Practices:

- Never log passwords, access tokens, refresh tokens, private keys, card security codes, or secrets.
- Mask/redact PII before shipping telemetry.
- Do not use emails, phone numbers, booking IDs, or customer IDs as metric labels.
- Restrict trace/log access by team and data classification.
- Set retention by purpose; debug logs do not need the same retention as audit logs.
- Encrypt in transit/at rest and audit data searches/exports.
- Be careful with sampling: do not sample out all rare errors/critical transactions; use tail sampling or error-aware sampling if supported.
- Protect telemetry ingestion endpoints with identity, TLS, and quotas.

Traces/logs should not be treated as the official system of record for transactions. If auditing or ledgers are required, use storage designed for integrity and corresponding retention.

## 14. Sampling, Retention, and Observability Cost

Collecting all logs, traces, and metrics at maximum granularity can push the observability bill above application infrastructure costs.

Strategies:

1. Retain aggregated metrics long enough for trend and capacity analysis.
2. Sample normal traffic traces, prioritizing retention of error/slow traces per policy.
3. Use structured logs and appropriate log levels; avoid logging every item inside large loops.
4. Separate short-lived debug logs from security/audit logs.
5. Reduce label cardinality and remove unused metrics.
6. Measure ingestion volume, query cost, retention bytes, and cost per service.
7. Use exemplars/trace links to jump from a metric spike to representative traces.

Sampling must be clearly documented on dashboards. Rare errors can disappear under random sampling; do not use sampled traces as the primary denominator for availability SLIs without accurate counter measurements.

## 15. Case Study: End-to-End Observability for a Booking Platform

**Context:** an accommodation rental platform has a Search API, Booking API, Inventory service, Payment service, Notification worker, and a revenue aggregation data pipeline. Users report occasional checkout failures. Cluster CPU is not high, yet business owners see confirmed bookings dropping.

### 15.1. Proposed Metric Set

| Layer | Metric | Definition |
|---|---|---|
| Business | booking_confirmation_rate | Confirmed bookings / valid booking requests by cohort |
| Business | payment_authorization_rate | Authorized payments / valid attempts by provider/method |
| Business | checkout_abandonment_rate | Checkouts not reaching a successful terminal state within window |
| Business | net_booking_value | Value after cancellations/refunds per approved rules |
| Application | booking_request_duration | Booking API latency p50/p95/p99 |
| Application | inventory_conflict_total | Requests failing to hold inventory due to conflicts |
| Application | payment_dependency_errors | Errors/timeouts by provider and error category |
| Application | notification_queue_age | Age of the oldest message |
| Infrastructure | db_connection_pool_wait | Connection wait time in app |
| Infrastructure | db_lock_wait | Lock wait time in database |
| Infrastructure | node_cpu_throttling | CPU throttling on compute nodes |
| Data | revenue_model_freshness | Reporting data lag relative to source watermark |

### 15.2. Investigation Flow

1. The business dashboard shows confirmation rate dropped 8% on mobile checkout; search-to-view remains normal.
2. The application dashboard shows rising payment dependency timeouts for one provider; inventory conflicts did not increase.
3. Sample traces of slow checkouts show time spent in the provider-call span, not in the DB.
4. The infrastructure dashboard shows normal CPU and DB connections; dependency timeouts are the primary signal.
5. The payment team checks provider quotas/latency and retry config; retry storms are capped via backoff/circuit breakers.
6. The Booking API keeps operations in pending/unknown state rather than marking them failed immediately on timeout.
7. The business dashboard tracks confirmation/reconciliation once the provider returns a result; the data pipeline publishes revenue only after passing quality gates.

The 8% drop is an illustrative scenario. Investigation conclusions must be grounded in actual data rather than inferring causation from correlation alone.

### 15.3. Dashboard Layout

~~~mermaid
flowchart TD
    Overview["Executive / business overview"] --> Funnel["Funnel and payment outcomes"]
    Overview --> SLO["SLO and error budget"]
    SLO --> RED["Service RED metrics"]
    RED --> Trace["Trace by operation / provider"]
    Trace --> Infra["DB, compute, network and queue"]
    Overview --> Data["Data freshness and quality"]
    Data --> Pipeline["Pipeline run / reconciliation"]
~~~

### 15.4. Acceptance Criteria

- Booking confirmations and payment outcomes have clear event/state definitions.
- Business metrics connect to requests/traces without using PII as metric labels.
- Traces pinpoint slow dependency spans during checkout.
- Infrastructure metrics capture DB connections/locks, node saturation, and queue age.
- Availability/latency SLOs have approved windows and error budgets.
- Revenue dashboards display freshness and quality status.
- Alerts have owners, severities, runbooks, and distinguish business degradation from technical outages.

## 16. Process for Building Observability from Scratch

1. **Select user journeys:** identify value-creating flows and critical business states.
2. **Define events:** names, emission points, business keys, sources of truth, and terminal states.
3. **Choose SLIs/SLOs:** availability, latency, completion, freshness, or correctness.
4. **Instrument applications:** RED metrics, dependency spans, structured logs, and correlation context.
5. **Instrument infrastructure:** USE metrics and resource saturation.
6. **Design metric contracts:** types, units, labels, owners, cardinality, and retention.
7. **Build dashboards:** business → SLO → service → dependency → infrastructure.
8. **Set up alerts:** burn rate, business anomalies, saturation, and data freshness.
9. **Write runbooks:** each alert specifies queries, owners, decisions, and recovery actions.
10. **Test:** inject faults, generate representative traffic, and verify dashboards and alerts fire accurately.
11. **Review:** remove unused metrics, fix label cardinality, and tune SLOs and costs.

## 17. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Monitoring only CPU/memory | Blind to whether users complete business tasks | Add business outcomes and application SLIs |
| Monitoring only revenue/conversion | Cannot locate technical root causes | Link business events with requests, traces, and dependencies |
| Counting HTTP 200 as booking success | Artificially inflated numbers when business logic fails | Measure committed business state |
| Counting payment requested as revenue | Includes declined/timed-out transactions | Distinguish authorized, captured, and refunded |
| Conversion denominator from mismatched cohorts | Meaningless ratios | Define cohorts, time windows, and eligibility |
| Alerting only on CPU thresholds | Many false positives or missed bottlenecks | Alert on SLOs, saturation, and user impact |
| Labels containing user/booking IDs | Cardinality and costs surge | Use bounded metric dimensions; use traces/logs to drill down |
| Traces/logs lacking correlation context | Cannot connect async flows | Propagate trace context and operation IDs |
| Dashboards lacking data freshness | Stale reports mistaken for current results | Display source watermarks and quality status |
| Using sampled traces as SLI denominator | Skewed error/availability rates | Use complete counters/histograms for SLIs |
| Collecting unbounded telemetry | High costs and potential PII exposure | Sampling, retention, redaction, and access control |
| Alerts without owners/runbooks | On-call receives pages with no clear action | Attach severity, owner, queries, and recovery steps |

## 18. Observability Review Checklist

### Business Metrics

- [ ] User journeys and business states are defined.
- [ ] KPIs have explicit formulas, cohorts, timezones, currencies, and denominators.
- [ ] Accepted, completed, authorized, captured, confirmed, cancelled, and refunded states are distinguished.
- [ ] Guardrail metrics exist, such as cancellations, duplicates, fraud, and support contacts.
- [ ] Business metrics have owners and authoritative data sources.

### Application and Infrastructure

- [ ] Services have RED metrics and dependency latency/errors.
- [ ] Queues/workers track backlog, oldest age, retries, and DLQs.
- [ ] Infrastructure has USE metrics for CPU, memory, disk, network, databases, and nodes.
- [ ] Desired/running/ready capacity and saturation are displayed.
- [ ] Deployment/config/provider change context is captured.

### Correlation and Telemetry Quality

- [ ] Trace context propagates across HTTP/RPC/messages.
- [ ] Business operations carry correlation IDs as allowed by policy.
- [ ] Metrics have types, units, descriptions, owners, and cardinality budgets.
- [ ] Metric labels contain no PII or high-cardinality identifiers.
- [ ] Sampling does not skew SLIs; logs/traces have appropriate retention.
- [ ] Data freshness and quality status appear alongside business dashboards.

### SLOs, Alerts, and Operations

- [ ] SLIs/SLOs measure user experience, with defined windows and error budgets.
- [ ] Alerts are based on burn rate/impact and have owners/severities.
- [ ] Business anomalies and technical incidents are distinguished.
- [ ] Each alert has a runbook, queries, and recovery actions.
- [ ] Dashboards have been tested with fault injection and representative data.
- [ ] Telemetry, retention, and query costs are monitored.

## 19. Hands-On Exercise

**Context:** a booking platform has Search, Booking, Inventory, Payment, and Notification services. The product team reports conversion dropped over the past two days; operations reports CPU and memory are normal. Current dashboards only show total HTTP requests and cluster CPU.

Design observability:

1. Draw the funnel from search to booking confirmed and define events/terminal states.
2. Write formulas for booking conversion, payment authorization rate, and cancellation rate with clear cohorts/denominators.
3. Choose at least two SLIs and SLOs for the booking API; explain which requests count as success.
4. Design RED metrics for Booking/Payment services and USE metrics for DB/compute/queues.
5. Propose traces/spans and correlation context to connect a checkout to the payment provider.
6. Select labels with controlled cardinality; specify data excluded from metrics.
7. Design a dashboard flowing business → SLO → application → infrastructure → data freshness.
8. Propose alerts for error budget burn, payment degradation, DB saturation, and queue age.
9. Write a runbook for investigating falling conversion while CPU remains normal.
10. Design a fault-injection test and verify dashboards/alerts work.

**Self-check hint:** Falling conversion does not prove a service is broken; normal CPU does not prove the request path is healthy. Payment declines must be distinguished from provider timeouts. A booking should only be counted as confirmed according to the authoritative post-commit state, not by counting successful HTTP responses.

## 20. Takeaways

Observability delivers value when business outcomes are connected to request experience and resource health. Business metrics tell you whether users and the business are achieving their goals; application metrics reveal how requests, dependencies, and queues behave; infrastructure metrics explain capacity and saturation. No single layer suffices on its own.

Define KPIs/SLIs/SLOs with clear denominators and states, instrument RED/USE, propagate trace context, manage cardinality and sensitive data, and build dashboards along the path business → SLO → service → dependency → infrastructure. Alerts should be based on impact/error budget, with clear owners and runbooks. A well-observed system does not merely show "what is red," it helps teams identify which business flow is affected, where the root cause lies, and what action to take.
