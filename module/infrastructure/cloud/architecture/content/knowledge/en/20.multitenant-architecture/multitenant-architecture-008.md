# Measuring Usage, Cost, and Quality of Service per Tenant

## Learning Objectives

In a *multi-tenant architecture*, multiple tenants share an application platform, compute, databases, networking, and data services. Sharing resources improves efficiency and lowers platform costs, yet also raises a critical question: **how many resources is each tenant consuming, what costs are they generating, and what quality of service are they receiving?**

If you only measure CPU, memory, or total requests at the cluster level, operations teams struggle to tell which tenant is driving load, which tenant is impacted, whom costs should be attributed to, and whether one tenant is starving others. Simply counting requests can also mislead, because a lightweight search request and a massive report generation request consume vastly different resources.

This lesson explains how to design **tenant metering, cost allocation, and quality of service (QoS)** systems—from defining measurement units through collection, aggregation, enforcement, and serving data for operations or billing. Topics include usage dimensions, attribution, quotas, fairness, noisy neighbors, per-tenant SLIs/SLOs, showback/chargeback, and metric accuracy controls.

After this lesson, you will be able to:

- Determine trustworthy tenant identity and propagate tenant context across requests, workers, events, and data pipelines.
- Choose measurement units reflecting real resource consumption instead of raw request counts.
- Design usage events, meter aggregation, idempotency, and corrections.
- Distinguish metering, billing, cost allocation, showback, and chargeback.
- Allocate shared costs using explainable, auditable drivers.
- Design quotas, rate limits, concurrency limits, fairness, and admission control.
- Detect and mitigate noisy-neighbor impacts across compute, databases, storage, and networking.
- Define per-tenant or per-tier SLIs/SLOs and error budgets.
- Build dashboards, alerts, audit trails, and reconciliation workflows.
- Evaluate security, privacy, accuracy, and TCO under Well-Architected principles.

## 1. Why Measure per Tenant?

Suppose a SaaS platform serves 2,000 businesses. They share APIs, database clusters, object storage, queues, and worker fleets. Within one hour, total requests double. System-level dashboards show rising CPU and degrading p95 latency, yet cannot answer:

- Which tenant generated most of the load spike?
- Which APIs, jobs, or features drove the load?
- Is a throttled tenant consuming fewer resources due to quotas or suffering from another tenant?
- Did costs rise due to compute, database, storage, egress, or logging?
- Are Enterprise-tier tenants receiving their committed SLOs?
- Can usage be metered fairly without double-counting when requests retry or events are redelivered?

Tenant-level metering grounds technical telemetry in contractual and business context. It supports capacity planning, abuse detection, cost optimization, plan design, and billing dispute resolution.

### 1.1. Tenant Usage Does Not Equal Tenant Cost

Usage is the quantity of resources or activities measured. Cost is the monetary value allocated according to a cost model. QoS is the service quality a tenant experiences.

A tenant with high request volume may not generate the highest cost if most requests hit cache. Conversely, a tenant with few requests can drive high costs if each request runs huge queries, processes multi-gigabyte files, or transfers data over the Internet.

Similarly, low cost does not imply good QoS. A tenant might be heavily throttled, resulting in low usage and low cost alongside a terrible user experience.

| Concept | Question | Example |
| --- | --- | --- |
| Usage / metering | How much did the tenant consume? | 1.2M API units, 80 GB storage |
| Cost allocation | How are platform costs attributed? | 4.5M VND compute/storage |
| Billing | How much must the tenant pay per contract? | Base plan + overages |
| QoS | What quality did the tenant receive? | API p95 180 ms, availability 99.95% |
| Fairness | Are resources distributed reasonably? | One tenant cannot monopolize all workers |
| Entitlement | What is the tenant permitted to use? | 500 requests/s, 100 GB storage |

## 2. Identify Tenant Identity Before Measuring

Metering under the wrong tenant is often more dangerous than missing metrics, as inaccurate numbers can lead to wrong invoices, wrong quotas, or exposure of another tenant's data.

### 2.1. Never Trust Client-Declared Tenant IDs

Tenant identity must come from a trusted source, such as:

- Authenticated claims in a token or session.
- API keys mapped to tenants in a registry.
- Server-verified mappings from customer/account to tenant.
- Service identities for background jobs or system integrations.
- Tenant context embedded in system-emitted jobs/events.

Never accept an arbitrary tenant header from the Internet and use it directly as a billing dimension. The gateway or application must authenticate the caller and verify permission to access the requested tenant.

### 2.2. Tenant Context End-to-End Across Processing Flows

A single request may spawn events, background jobs, or batch tasks. Context must follow the work so downstream usage still attributes to the originating tenant, while workers verify context integrity and processing permissions.

~~~mermaid
flowchart LR
    C["Client"] --> G["Gateway / Authentication"]
    G --> A["Tenant context resolver"]
    A --> API["Tenant-aware API"]
    API --> DB[("Tenant data")]
    API --> E["Usage / business event"]
    E --> Q[("Queue")]
    Q --> W["Background worker"]
    W --> M["Usage meter"]
    API --> M
    M --> U[("Usage ledger")]
~~~

Context typically carries `tenantId`, `requestId`, `correlationId`, `service`, `operation`, `plan`/`tier`, and resource scope. Avoid putting PII or secrets in metric labels. For events/jobs, record the tenant identifier in a stable schema with trusted signatures/origins if traversing untrusted zones.

### 2.3. Tenant Context in Multi-Tenant Databases

If a database uses a shared schema with `tenant_id`, every tenant-scoped query must enforce the proper filter or row-level security. Usage aggregations must also separate by tenant. Test raw SQL queries, reports, exports, cache keys, and background jobs; a metering pipeline missing a tenant filter can merge multiple customers' usage into one account.

### 2.4. Changes in Tenant Ownership

Tenants can change plans, transfer ownership, merge, or split. Persist effective timestamps and mapping history. Never retroactively rewrite historical usage to a new owner without an explicit policy. Billing periods must know which tenant, account, subscription, and plan were active when usage occurred.

## 3. Designing Taxonomies and Measurement Units

### 3.1. Classifying Usage Dimensions

Metering can be grouped into dimensions:

| Group | Example Dimensions | Unit |
| --- | --- | --- |
| API | Request count, request class, API units | request, unit |
| Compute | Function duration, CPU time, vCPU-seconds, GB-seconds | second, GB-second |
| Database | Query count, rows read/written, DB compute, connection time | query, row, unit-second |
| Storage | Logical bytes, physical bytes, object count, request count | byte, GB-month, operation |
| Network | Ingress, egress, cross-region transfer | byte, GB |
| Messaging | Message count, message size, queue storage, delivery attempts | message, byte, operation |
| Analytics | Data scanned, query runtime, slot/warehouse time | GB scanned, second |
| AI/processing | Tokens, image pages, processing units | token, page, unit |
| Support | Backup retention, exports, audit retention | GB-month, job |

Not every dimension should be billed. Some dimensions guide internal optimization or system protection; others belong in contracts. Clearly define what is internal metering, what is a billing meter, and what is strictly an operational metric.

### 3.2. Choosing Units Correlated with Resources

Request counts are easy to collect but fail to capture heaviness. A better approach classifies requests into operation classes:

- `Read-small`: querying a single record or metadata.
- `Read-large`: searches, exports, or multi-row queries.
- `Write`: creating/updating data.
- `Compute-heavy`: report generation, file processing, calculations.
- `External-transfer`: large data transfers or cross-region traffic.

Weighted units can be assigned based on benchmarks, but weights must be validated and documented clearly if used for billing. Never arbitrarily assign a heavy request 10 units on gut feel; measure CPU time, data scanned, duration, or downstream dependency cost.

### 3.3. Distinguishing Logical Usage from Provider Cost

Suppose a tenant stores 50 GB of logical data. After replication, versioning, compression, or backups, the cloud provider may bill for more or less than 50 GB of physical storage. Logical usage governs product limits; physical consumption drives cost allocation. Give these two metrics distinct names.

Similarly:
- API request count is a product unit.
- Egress bytes are a cloud resource.
- Function GB-seconds are a provider meter.
- Database connection-seconds may be an internal usage metric without necessarily matching managed DB billing units.

### 3.4. Defining Usage Record Grain

A usage record needs a clear grain—for example, one completed operation, one usage interval for a resource, or an hourly storage snapshot. Without defined grain, aggregation might count a request once at the API and again in the worker even though both belong to the same business operation.

## 4. Usage Events and Metering Pipelines

### 4.1. Usage Event Structure

Example usage event:

~~~json
{
  "usage_event_id": "usage-7f4a",
  "tenant_id": "tenant-42",
  "account_id": "account-18",
  "subscription_id": "sub-2026-08",
  "meter_name": "report_compute",
  "quantity": 12.5,
  "unit": "GB_SECOND",
  "operation_id": "report-run-991",
  "resource_id": "job-991",
  "occurred_at": "2026-11-18T09:15:00Z",
  "recorded_at": "2026-11-18T09:15:03Z",
  "service": "report-worker",
  "region": "ap-southeast-1",
  "meter_version": 2,
  "source": "worker-completion"
}
~~~

This is an illustrative schema. Quantities, units, and meter versions must have exact definitions. Never use floating-point arbitrarily for money; store usage decimals with appropriate precision or convert to integer micro-units if the meter requires.

Key fields:

- Unique `usage_event_id` for deduplication.
- Effective tenant/account/subscription at the time of occurrence.
- Meter name and version.
- Quantity and unit.
- Operation/resource ID for reconciliation.
- Occurred time and recorded time.
- Source service, region, environment.
- Correlation/request ID for investigations.
- Correction/reversal reference when adjusting usage.

### 4.2. Where to Meter?

Usage can be collected across multiple layers:

- Gateway: accepted requests, endpoint classes, bytes, response statuses.
- Application: completed business operations, features used.
- Worker: duration, compute units, job outcomes.
- Storage: per-tenant byte/object-count snapshots.
- Database: query/row/compute attribution if the engine supports it.
- Cloud billing exports: provider cost by resource/account/tag.

Do not rely on a single measurement point for every resource type. The gateway does not know a background job's exact compute duration; a worker can measure duration yet cannot know the provider egress bill without ingesting billing exports.

### 4.3. Events Occurring Once Are Not Guaranteed Recorded Once

Usage events can be re-sent due to retries or queue redeliveries. Metering pipelines need idempotency:

1. Every operation generates a deterministic `usage_event_id`.
2. Consumers write events to the ledger under a unique constraint.
3. Aggregate solely from committed ledger events.
4. When duplicates arrive, ignore them by event identity.
5. When adjustments are needed, emit correction events linking back to the original record.
6. Reconcile usage totals against source counts or provider invoices.

Never deduplicate using nearby timestamps, since two legitimate operations can occur in the same millisecond.

### 4.4. Metering Ledger and Aggregation

The usage ledger stores granular records for auditing/reconciliation. Aggregate tables or warehouses power dashboards and invoicing. Never retain only end-of-period totals while discarding details; when a tenant disputes a bill, you must be able to trace back to operations/resources and meter versions.

~~~mermaid
flowchart TB
    S1["API meters"] --> E["Usage events"]
    S2["Worker meters"] --> E
    S3["Storage snapshots"] --> E
    S4["Provider billing export"] --> E
    E --> Q[("Durable ingestion")]
    Q --> V["Validate / deduplicate"]
    V --> L[("Usage ledger")]
    L --> A["Aggregate by tenant / meter / period"]
    A --> D[("Usage warehouse")]
    D --> BILL["Billing / invoice"]
    D --> DASH["Tenant and operator dashboards"]
    L --> REC["Reconciliation"]
~~~

## 5. Exactness, Late Data, and Corrections

Metering often ties directly to money or entitlements. Therefore, define exactness and how late data is handled.

### 5.1. Occurred Time vs. Recorded Time

A job starts at 10:00 and finishes at 10:20; exact usage may only be known upon completion. Events record `occurred_at` for the activity window and `recorded_at` for when the ledger received the record. Billing periods may rely on start time, completion time, or contractual rules; document this consistently.

### 5.2. Late-Arriving Usage

Provider billing exports can lag by hours or days. Workers can go offline and submit usage once connectivity recovers. Support:
- Late arrival windows.
- Period close and reopen policies.
- Provisional usage vs. finalized usage.
- Correction/reversal records.
- Invoice adjustments or credits.
- Audits tracking who approved corrections.

Never silently overwrite finalized figures. Once an invoice is issued, adjustments must follow billing policies and formal documentation.

### 5.3. Meter Versioning

If how CPU units or operation weights are measured changes, the same meter name may no longer be comparable across periods. Version meters, store effective dates, and keep old definitions long enough to regenerate historical invoices. Never replay historical data through a new meter without an approved migration/correction.

## 6. Cost Allocation: From Cloud Bill to Tenant

Cloud providers typically bill by account, project, subscription, resource, region, tag, or meter. A shared database or cluster may serve many tenants without a separate provider bill line per tenant.

Cost allocation distributes those costs using chosen **cost drivers**. Categories include:

- **Direct cost:** costs attributed directly to one tenant, e.g., dedicated compute or a dedicated storage bucket.
- **Shared variable cost:** costs scaling with usage, e.g., data transfer or compute units.
- **Shared fixed cost:** baseline platform, control plane, minimum capacity, support.
- **Platform overhead:** security, logging, backups, monitoring, network hubs.
- **Unallocated/residual:** portions lacking a reliable driver; surface separately rather than fabricating false precision.

### 6.1. Choosing Cost Drivers

| Cost Pool | Potential Drivers | Risks |
| --- | --- | --- |
| API compute | CPU time, weighted request units | Request weights do not reflect every code path accurately |
| Worker compute | vCPU-seconds/GB-seconds per job | Shared worker idle capacity is hard to attribute |
| Database | Query/compute units, rows, workload attribution | Shared caches/locks/idle capacity add complexity |
| Storage | GB-months per tenant, object counts/operations | Replication/backups skew physical totals |
| Network | Egress bytes per tenant/endpoint | Shared NAT/gateways carry fixed fees |
| Logs | Bytes ingested per service/tenant | Logs lacking tenant context or high cardinality |
| Support/platform | Seats, plan, tenant count, or revenue allocation | Does not reflect direct consumption causes |
| Shared baseline | Equal share, plan tier, capacity reservation | May feel unfair across tenants of different sizes |

Drivers must match the cost pool's structure. Do not allocate an entire cluster's cost purely by request count when query costs vary wildly.

### 6.2. Allocating Shared Costs

A general model:

~~~text
Tenant allocated cost
  = Direct tenant cost
  + Σ(shared cost pool × tenant driver share)
  + Contractual fixed fee or reserved capacity (if applicable)
~~~

For example, monthly shared worker cost is 100M VND. Metered compute is 40,000 units for Tenant A, 35,000 for B, and 25,000 for C; total 100,000 units.

~~~text
A share = 40,000 / 100,000 = 40%  -> 40M VND
B share = 35,000 / 100,000 = 35%  -> 35M VND
C share = 25,000 / 100,000 = 25%  -> 25M VND
~~~

This is transparent when compute units accurately represent shared worker costs. If a pool has a large idle baseline, separate fixed costs from variable costs and allocate fixed costs by capacity reservation/plan rather than charging everything by active usage.

### 6.3. Showback and Chargeback

- **Showback:** displays how much a tenant/team consumed and was allocated without directly billing.
- **Chargeback:** uses the numbers to actually charge fees or allocate real budgets.
- **Billing:** calculates what a tenant owes under contracts, discounts, tiers, minimum commitments, taxes, currencies, and adjustments.

You can roll out showback first to validate meters and drivers. Moving to chargeback requires stronger governance: audits, period closes, corrections, dispute workflows, and invoice access controls.

## 7. Pricing Models and Billing Meters

Usage meters are not necessarily billing meters. Contracts may charge flat subscriptions, seat counts, transaction counts, storage overages, API units, or hybrids.

| Pricing Model | Basis of Charge | Details to Define |
| --- | --- | --- |
| Flat subscription | Fixed fee per period | Entitlements, fair-use limits, overage policies |
| Per-seat | Active/licensed user count | Active seat definition, deactivation, prorating |
| Per-operation | Operation/billing unit count | Successful vs. attempted, retries, excluded operations |
| Tiered | Unit rate by usage bracket | Cumulative tiers, reset periods, boundaries |
| Volume discount | Lower unit rate once threshold passed | Thresholds, retroactive vs. marginal |
| Reserved capacity | Paying for committed capacity | Reservations, utilization, burst policies |
| Hybrid | Subscription + usage/overages | Included quotas and overage calculation |

### 7.1. Defining Billable Events

Contracts must answer:

- Are only successful operations billed, or attempted requests too?
- Are retries caused by platform errors billed?
- Are operations canceled mid-flight by clients billed for compute already consumed?
- Do cache hits count as API requests or resource usage?
- Is storage billed on logical, physical, or average daily GB-months?
- Are there free tiers, included quotas, and grace periods?
- Is usage rounded by second, minute, GB-day, or GB-month?
- What are the sources and timestamps for currencies, taxes, and exchange rates?

Without clarity, tenants may see two systems meter the exact same feature differently.

### 7.2. Tiered Pricing Example

Suppose a contract includes 100,000 API units; the next 100,000 units cost 0.8 VND/unit; usage above 200,000 costs 0.5 VND/unit. The tenant uses 260,000 units:

~~~text
Included:                100,000 × 0      = 0
Tier 1:                  100,000 × 0.8    = 80,000 VND
Tier 2:                   60,000 × 0.5    = 30,000 VND
Usage charge:                             110,000 VND
~~~

This is a marginal tier example. Some contracts apply the lowest rate across the entire volume once a bracket is reached (volume tier); the two methods yield different totals and must be stated explicitly.

## 8. QoS per Tenant: Fairness and Noisy Neighbors

### 8.1. What Is a Noisy Neighbor?

A noisy neighbor occurs when one tenant consumes shared resources to a degree that slows down, breaks, or starves other tenants. Causes include request bursts, expensive database queries, large exports, queue backlogs, storage operations, or log volume.

A platform must ensure large tenants can consume more resources per their entitlements while preventing any single tenant from causing uncontrolled harm to others.

### 8.2. Control Mechanisms

- **Rate limiting:** limits requests per tenant, endpoint, or operation class.
- **Concurrency limits:** caps simultaneous requests/jobs.
- **Quotas:** caps total resource consumption per period or existing resource counts.
- **Weighted fair queueing:** allocates processing turns by plan/priority weight.
- **Admission control:** rejects or defers work when capacity is insufficient.
- **Bulkheads:** separates pools/queues/resource pools by workload or tenant tier.
- **Priority classes:** separates interactive, background, and batch work.
- **Per-tenant circuit breakers:** isolates dependencies or error-looping tenants.
- **Backpressure:** slows down producers or signals `retry-after` when saturated.

Not every tenant needs dedicated infrastructure. You can run shared pools with fair schedulers while providing isolated pools for tenants with specific entitlements or compliance mandates.

### 8.3. Rate Limits vs. Quotas

Rate limits constrain speed over a short time window, e.g., 100 requests/second. Quotas constrain total consumption over a period, e.g., 2M API units/month or 500 GB storage.

A tenant may still have monthly quota remaining yet hit a temporary rate limit. Conversely, a low-rate tenant may exhaust its monthly quota. API responses should distinguish the reason and return helpful metadata such as `retry-after`, `limit`, `remaining`, and `reset` time.

### 8.4. Token Bucket Illustration

Token buckets allow bounded bursts:

~~~text
tokens(t)
  = min(bucket_capacity,
        previous_tokens + refill_rate × elapsed_time)

Request cost <= available tokens -> accept and deduct
Otherwise -> throttle or reject
~~~

Each request can consume tokens proportional to its operation class. Buckets must distribute state consistently across multiple API instances; local in-memory buckets per pod can multiply a tenant's effective limit by the replica count. Use gateways, centralized limiters, or per-instance quota partitioning algorithms.

## 9. Capacity Isolation by Layer

### 9.1. Compute

Track CPU time, memory, duration, concurrency, and queue age by tenant/job class. Cap report/export concurrency, separate worker pools, or assign priorities so batch jobs never starve interactive workers.

### 9.2. Database

One tenant can run reports scanning millions of rows while another runs short transactions. Mitigations include query timeouts, statement/resource limits where supported, per-workload connection pools, workload groups, read replicas, partitioning, and indexing. Never create unbounded per-tenant connection pools; total pools must stay within the database's connection budget.

### 9.3. Storage

Measure logical/physical bytes, object counts, API operations, and growth rates. Enforce per-tenant quotas, lifecycle policies, upload size limits, and export guardrails. One tenant must never overload platform-wide storage listings or compaction.

### 9.4. Network and Egress

Track bytes per tenant, destination class, and region. Heavy egress can incur substantial bills or saturate gateways. Limit export concurrency, offload large files via object storage presigned URLs, use CDNs, and enforce plan-based quotas.

### 9.5. Queues and Workers

Queues need priority/fairness by tenant or job class. If one tenant publishes millions of messages, a single global FIFO queue causes head-of-line blocking. Shard by key, use fair schedulers, or separate queues by tier—trading off higher queue count and operational overhead.

## 10. SLOs per Tenant and Service Tier

Platform-wide SLOs can hide tenants suffering poor experiences. For example, 99.9% of global requests succeed while one tenant sees 20% errors due to a bad data partition or misconfigured quota.

### 10.1. Tenant-Specific SLIs

SLIs can include:

- Availability: ratio of valid requests succeeding.
- Latency: p50/p95/p99 by API/operation class.
- Freshness: data or projection lag.
- Job completion: ratio of jobs finishing within deadline.
- Throttling: ratio of requests rate-limited/quota-rejected.
- Data correctness: reconciliation mismatches or failed validations.
- Support: response/incident times by tier if contractual.

Separate platform faults, client errors, valid quota rejections, and external dependencies using clear rules. Do not exclude all throttled requests from SLOs if unexpected platform throttling occurs; however, cases where a tenant deliberately exceeds entitlements can be classified separately.

### 10.2. Service Tier Example

| Tier | Availability Objective | Interactive Latency Target | Job Priority | Support |
| --- | --- | --- | --- | --- |
| Standard | 99.5% | API p95 under 700 ms | Best effort | Business hours |
| Business | 99.9% | API p95 under 400 ms | Normal priority | Faster response |
| Enterprise | 99.95% | API p95 under 250 ms | Contractual reserved/priority capacity | SLA-backed support |

These are illustrative levels, not service promises. Real targets must be achievable given infrastructure, regions, dependencies, and contracts. Never promise dedicated per-tenant p95 targets if a shared-pool architecture cannot sustain them at peak.

### 10.3. Error Budgets

If the availability SLO is 99.9% over a 30-day month, the time-based error budget is:

~~~text
30 days × (1 - 0.999)
= 0.03 days
= 43.2 minutes
~~~

Request-count error budgets differ from time-based ones. Pick an appropriate SLI, publish the window, and define exclusion rules. Tenant-specific SLOs also need enough traffic for percentiles to be meaningful; low-traffic tenants should use longer windows or combine per-operation latency/error metrics.

## 11. Separating Platform Health, Tenant QoS, and Contract Entitlements

Never conflate these three layers of information:

1. **Platform health:** how clusters, databases, queues, networks, deployments, and regions are performing.
2. **Tenant QoS:** the actual latency, availability, freshness, and job completion a specific tenant receives.
3. **Entitlement/contract:** how much the tenant is allowed to consume and its support/service tier.

A tenant can suffer poor QoS due to a platform incident, or be legitimately throttled after exceeding rate limits. Dashboards must display both actual usage and entitlements to prevent misinterpretation.

### 11.1. Tenant Experience Scorecard

Example scorecard:

| Metric | Actual Period | Entitlement/SLO | Status |
| --- | ---: | ---: | --- |
| API units | 820,000 | 1,000,000 | Within quota |
| Logical storage | 72 GB | 100 GB | Within quota |
| API p95 | 310 ms | 400 ms | Met |
| Availability | 99.92% | 99.9% | Met |
| Export completion p95 | 8 minutes | 10 minutes | Met |
| Throttled requests | 0.4% | Baseline 0.2% | Needs investigation |

Values are illustrative only. Avoid collapsing metrics into a single composite score without explaining the formula and relative importance of each component.

## 12. Tenant-Aware Observability and Dashboards

### 12.1. Metric Labels Must Be Controlled

Attaching tenant IDs directly to every time-series metric creates massive cardinality across tens of thousands of tenants and multiple operations/regions/statuses. That drives up monitoring storage, memory, and query costs.

Options:
- Use aggregated metrics by tier, region, and operation class.
- Keep tenant-level details in the usage ledger or analytics store.
- Use exemplars or trace links for targeted request debugging.
- Emit detailed metrics only for tenants/tiers with dedicated SLOs.
- Cap high-cardinality dimensions.
- Use hashed/pseudonymous tenant references where appropriate.

Never place emails, domains, customer names, or sensitive data into labels. Even internal tenant IDs require evaluating re-identification risks and access controls.

### 12.2. Audience-Specific Dashboards

**Tenant dashboards** should show:
- Current usage and trends per meter.
- Quotas, entitlements, remaining balances, and reset times.
- Service health and relevant SLOs.
- Job/export statuses.
- Cost estimates or invoice details per permissions.
- Warnings when nearing thresholds or being throttled.

**Operator dashboards** should show:
- Top tenants by resource consumption, growth, and cost drivers.
- Noisy-neighbor signals.
- Pool/queue/database saturation.
- Platform SLIs/SLOs and tenant-specific SLOs.
- Meter ingestion lag, duplicates, and rejected/corrected events.
- Allocation residuals and reconciliation mismatches.

### 12.3. Traces and Usage Attribution

Traces should carry verified tenant context and operation classes. Worker child spans must inherit context from job metadata. Traces can link to usage event IDs so operators can investigate specific figures without storing full payloads or PII.

## 13. Billing Correctness, Audits, and Dispute Handling

When usage drives billing, the system must trace every number from source to invoice.

A billing record should include:
- Tenant/account/subscription and billing period.
- Meter name/version and quantity/unit.
- Pricing plan/version, tier, and rate.
- Discounts/credits/taxes if applicable.
- Source usage event range or ledger reference.
- Calculation timestamp and invoice version.
- Adjustments/reversals and approval references.

### 13.1. Separating Metering from Pricing

Metering determines quantity. Pricing applies contractual rates. Billing totals amounts owed. Separating these lets you update rates or discounts without re-metering historical usage, and recalculate invoices whenever corrections arrive.

### 13.2. Dispute Workflow

When a tenant disputes an invoice:

1. Identify the invoice line and meter version.
2. Trace back to ledger records and operation/resource references.
3. Check for duplicates, missing data, late arrivals, and corrections.
4. Compare against source logs, provider usage exports, or business transactions.
5. Verify entitlements, plan effective dates, and pricing rules.
6. Approve credits/adjustments if warranted.
7. Record audits and publish an updated invoice revision.

Never directly edit a finalized ledger to make numbers look clean. Emit correction/reversal events with reasons and approvers.

### 13.3. Reconciliation

Reconciliation checks can cover:

- API gateway request counts vs. application usage meters.
- Job completion records vs. worker compute meters.
- Tenant logical storage snapshots vs. storage inventory.
- Cloud billing exports vs. resource/account cost pools.
- Usage ledger vs. invoice quantities.
- Invoice totals vs. pricing rules and rounding.

Discrepancies need thresholds, owners, and tracking statuses. Not every resource charge can be attributed precisely to a single tenant; explicitly report shared residuals.

## 14. Security and Privacy for Tenant Metering

Metering data reveals a tenant's business scale, usage patterns, user counts, operating hours, and transaction types. Therefore, usage analytics are sensitive data requiring protection.

- Tenants may read only their own usage/billing data.
- Billing operators have explicit roles with audited access and exports.
- Meter writers may emit events only for verified tenant contexts.
- Never accept arbitrary tenant identities from clients.
- Usage ledgers need integrity protection, retention, and backups.
- Guard against event tampering/forging and unauthorized replay.
- Separate production data from test/demo data.
- Mask or pseudonymize identifiers in analytics.
- Limit retention per contracts and legal requirements.
- Apply encryption at rest/in transit and proper key separation.
- Never put private tenant-level details in public metric labels.

If tenants use BYOK or dedicated encryption keys, verify whether reading usage/billing metadata depends on the tenant's data key. Metering should not require decrypting payload content merely to count bytes or operations.

## 15. Capacity Planning and Per-Tenant Forecasting

Usage history supports growth forecasting, anomaly detection, and capacity planning. However, forecasts must not rely solely on total request counts.

Track:
- Per-tenant growth rates by meter.
- Peak-to-average ratios.
- Seasonality by day, hour, or campaign.
- Storage growth and retention.
- Job duration distributions.
- API operation mix.
- Quota utilization and throttling frequency.
- Cost per unit and unit economics.

### 15.1. Forecasts and Alerts

For example, a tenant's storage grows from 50 GB to 70 GB in 10 days. The average growth rate is roughly 2 GB/day. With a 100 GB quota, an estimated 15 days remain before hitting the threshold at current pace.

~~~text
Average daily growth
  = (Current storage - Previous storage) / Elapsed days

Estimated days to quota
  = (Quota - Current usage) / Average daily growth
~~~

This is a simple linear forecast; reality involves seasonality, compression, deletions, and snapshots. Label forecasts clearly as estimates, not guaranteed exhaustion dates.

### 15.2. Anomaly Detection

Detect:
- Abnormal request rate spikes against a tenant's baseline.
- Sudden egress spikes after enabling exports.
- Abrupt storage growth.
- Error/throttle spikes.
- Abnormal jumps in job duration or data scanned.
- Usage meters dropping to zero despite ongoing business traffic.

Anomalies do not automatically mean abuse. Tenants may be running legitimate campaigns; operators should contextualize with deployments, contracts, and activity schedules.

## 16. TCO and Shared vs. Isolated Capacity Decisions

Metering also informs which tenants belong in shared pools, reserved capacity, or dedicated environments.

| Model | Advantages | Trade-Offs |
| --- | --- | --- |
| Fully shared | Cost efficiency, centralized operations | Complex noisy-neighbor control and attribution |
| Shared with quotas/fairness | Balanced consumption, reduces cross-tenant impact | Complex schedulers/limiters |
| Pooled by tier/region | Better isolation per workload group | Higher headroom cost, complex placement |
| Dedicated tenant stack | Isolation, customization, compliance | High cost and ops overhead, potential idle capacity |
| Hybrid | Shared baseline, dedicated for special tenants | Multiple models require consistent metering |

### 16.1. Cost per Tenant and Cost to Serve

~~~text
Cost to serve tenant
  = Direct resource cost
    + Allocated shared variable cost
    + Allocated platform fixed cost
    + Support/operations allocation

Tenant contribution
  = Contract revenue
    - Cost to serve
    - Applicable discounts/credits
~~~

Never use contribution margin to automatically degrade QoS or discriminate against a tenant in violation of contracts. This metric supports product, pricing, and capacity planning; service delivery must still honor entitlements and SLAs.

## 17. Case Study: Multi-Tenant SaaS Platform

### 17.1. Context

An operations management SaaS serves 500 businesses. The platform shares Kubernetes, PostgreSQL, object storage, queues, and workers across Standard, Business, and Enterprise plans. A few tenants run heavy exports at end-of-day, driving up queue and database load.

Hypothetical requirements:

- Tenants have dashboards viewing usage and quotas.
- Operators know which tenants drive load and which costs are rising.
- Heavy exports never push other tenants' interactive requests out of SLO.
- Usage billing is reconcilable down to operations.
- Enterprise receives contractual reserved concurrency and dedicated SLOs.
- Tenant usage data must be protected.

### 17.2. Metering Design

The gateway records API units by operation class; workers record compute duration and job size; storage inventory takes daily GB snapshots; cloud billing exports provide per-resource provider costs. Usage events flow into a durable queue, get validated/deduplicated, and land in the usage ledger. Aggregations by tenant, meter, period, and version power dashboards and billing.

~~~mermaid
flowchart TB
    G["API gateway meters"] --> UE["Usage event bus"]
    W["Worker meters"] --> UE
    ST["Storage inventory"] --> UE
    CB["Cloud billing export"] --> UE
    UE --> LEDGER[("Usage ledger")]
    LEDGER --> AGG["Tenant aggregation"]
    AGG --> DW[("Usage warehouse")]
    DW --> TD["Tenant usage dashboard"]
    DW --> OP["Operator cost/QoS dashboard"]
    DW --> INV["Billing calculation"]
~~~

### 17.3. Fairness for Exports

Export jobs are classified as background-heavy. Standard/Business share a worker queue with per-tenant concurrency limits and fair scheduling. Enterprise gets reserved worker capacity per entitlement. Interactive APIs carry higher priority than batch exports. When backlogs grow, the system returns `retry-after` or pending job status rather than holding thousands of request threads open.

### 17.4. Cost Allocation

Storage GB-months are allocated directly from tenant snapshots. Worker compute is allocated by measured duration/resource units. Shared database baseline is split into fixed pools by tier/entitlement, while variable costs allocate via published workload drivers. Network egress uses per-tenant bytes; platform security/control-plane costs appear as shared overhead.

### 17.5. QoS and Investigation

Operators spot Tenant X running high export concurrency, rising queue age, and degraded database read latency. The limiter throttles Tenant X's export concurrency within its quota; interactive APIs retain full capacity. The tenant dashboard shows usage, quotas, and job statuses. Per-tenant SLOs confirm Business tenants still meet API latency while export completion lags; operators follow a runbook checking worker saturation and backlogs.

### 17.6. Billing Dispute

Tenant Y disputes API units exceeding their internal dashboard. The billing team traces the invoice line to the meter version and usage ledger. They discover retry events were recorded twice in an older consumer missing a unique constraint. A correction event reverses the duplicate usage; the pipeline is fixed, and an audited invoice revision is issued. This demonstrates why metering requires a ledger, idempotency, and reconciliation.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Trusting tenant ID from request headers | Misattributed usage or data leaks | Resolve from verified identity |
| Counting raw requests only | Fails to reflect heavy request costs | Weighted meters and resource usage |
| Metering at multiple layers without operation IDs | Double-counting API and worker | Define grain and meter ownership |
| Non-idempotent usage events | Retries inflate invoices | Unique event IDs and ledger constraints |
| Keeping only period-end aggregates | Cannot investigate disputes | Retain an auditable usage ledger |
| Mixing fixed and variable costs | Unfair cost allocation | Separate cost pools and cost drivers |
| Using tenant ID as a label on all metrics | High cardinality and monitoring cost spikes | Aggregate metrics; keep details in warehouse |
| Local rate limits per pod | Total limit scales with replica counts | Shared limiters or quota partitioning |
| Large tenants monopolizing queues | Noisy neighbors and head-of-line blocking | Fair schedulers, priorities, bulkheads |
| Measuring SLOs solely platform-wide | Failing individual tenants go unseen | Tenant-level SLIs/SLOs |
| Corrections overwriting history | Lost audit trail, billing disputes | Reversal/correction events |
| Changing pricing without versioning | Cannot reproduce old invoices | Meter/pricing versions and effective dates |
| Using unverified showback straight as chargeback | Unvalidated trust | Shadow billing and dispute testing first |
| Fabricating false precision in cost allocation | Bad decisions and eroded trust | Disclose residuals and shared overhead |

## 19. Hands-On Exercise

A SaaS platform has 1,000 tenants sharing APIs, PostgreSQL, object storage, and queues. Three service plans define distinct quotas. One tenant runs a 2 TB export, spiking queue backlogs and pushing another tenant's API latency out of SLO. Finance wants monthly usage billing, while operations needs noisy-neighbor detection.

Complete the following:

1. Define trustworthy tenant identity across APIs, scheduled jobs, and worker events.
2. Propose meters for APIs, compute, database, storage, egress, and queues; specify unit, grain, and source.
3. Design a usage event schema with event ID, operation ID, tenant/account, meter version, and timestamps.
4. Ensure idempotent metering under queue redeliveries and worker retries.
5. Classify direct, shared variable, shared fixed, and platform overhead costs; pick drivers for each.
6. Allocate 120M VND in worker costs if Tenants A/B/C consume 50,000/30,000/20,000 compute units.
7. Design pricing tiers specifying included quotas, overages, retries, and late-usage policies.
8. Design rate limits, concurrency limits, fair queues, and reserved capacity to mitigate noisy neighbors.
9. Define at least two per-tenant SLIs/SLOs and one platform-wide SLO.
10. Build dashboards for tenants and operators while avoiding excessive metric cardinality.
11. Design the usage ledger, correction events, invoice reconciliation, and dispute workflow.
12. Test tenant context spoofing, duplicate usage, late events, limiter scale-out, and queue starvation.
13. Write an ADR covering shared, pooled, or dedicated capacity per tier, detailing cost and QoS trade-offs.

**Self-assessment hints:** A solid solution traces usage back to tenants and operations, uses explainable cost drivers, prevents quotas from multiplying across replicas, prevents aggregate metrics from masking per-tenant QoS, and keeps invoices reproducible/reconcilable.

## 20. Pre-Production Checklist

- [ ] Tenant identity is authenticated and propagated across APIs, events, workers, and batches.
- [ ] Usage meters define name, version, unit, grain, source, and owner.
- [ ] Logical usage, provider resource usage, and billable usage are clearly separated.
- [ ] Every operation/usage event has a deterministic ID and deduplication mechanism.
- [ ] Usage ledger supports retention, auditing, and corrections/reversals.
- [ ] Policies exist for late data, period closes, and invoice adjustments.
- [ ] Meter versions and pricing versions carry effective timestamps.
- [ ] Direct, shared fixed, and shared variable costs are cleanly separated.
- [ ] Cost drivers are published and residuals are never falsely attributed with fake precision.
- [ ] Showback is validated before enabling chargeback.
- [ ] Quotas, rate limits, and concurrency limits stay consistent when scaling replicas.
- [ ] Fairness, priorities, bulkheads, and backpressure protect heavy workloads.
- [ ] Tenant-level SLIs/SLOs distinguish platform failures from quota enforcement.
- [ ] Dashboards avoid PII and unbounded metric cardinality.
- [ ] Tenants read only their own usage/billing; operator access is audited.
- [ ] End-to-end reconciliation spans sources, ledger, aggregates, and invoices.
- [ ] Dispute workflows and correction approvers are established.
- [ ] Tested for noisy neighbors, duplicates, late usage, scale-out, and dependency failures.
- [ ] TCO and capacity planning rely on verified, high-quality usage data.

## 21. Well-Architected Evaluation

| Pillar | Design Questions for Tenant Metering and QoS |
| --- | --- |
| **Operational Excellence** | Do the usage ledger, dashboards, alerts, cost allocation, invoice reconciliation, and runbooks have owners? |
| **Security** | Is tenant identity trustworthy; do usage/billing enforce tenant isolation, least privilege, audits, and retention? |
| **Reliability** | Is metering durable, idempotent, able to handle late data/corrections, and non-blocking on the request path? |
| **Performance Efficiency** | Do quotas, fairness, concurrency, and isolation protect other tenants during peaks/noisy-neighbor events? |
| **Cost Optimization** | Do cost drivers reflect consumption; are shared overhead, per-tenant cost, and pricing actively tracked? |
| **Sustainability** | Are overprovisioning, idle reservations, redundant logs, and duplicate processing minimized? |

**Conclusion:** Per-tenant measurement must tie identity, operations, resources, costs, and service quality together into a single auditable model. Accurate metering underpins showback and billing; cost allocation needs transparent drivers; QoS needs quotas, fairness, and per-tenant SLOs so one customer cannot silently degrade another. Separate usage from pricing, maintain a reconcilable ledger, protect tenant context end-to-end, and choose isolation levels grounded in contracts and real workload data following Well-Architected principles.
