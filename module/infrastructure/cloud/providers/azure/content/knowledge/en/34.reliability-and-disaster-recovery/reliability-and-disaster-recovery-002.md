# Defining SLI, SLO, RTO, and RPO for Azure Applications

## 1. From Business Requirements to Reliability Targets

An application can run on Azure services rated highly for availability and still deliver a poor experience: users cannot sign in, APIs return errors, payments hang, or order data cannot be recovered after an incident. Therefore, **reliability** design must start from what users and the business actually need, then turn those needs into measurable metrics and a verifiable recovery plan.

In the Microsoft Azure ecosystem, applications commonly combine subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute services (App Service, Azure Container Apps, AKS), storage, databases, and monitoring systems. Each component has different failure modes, recovery times, and data-loss characteristics. No single default number fits every application.

Consider an online ordering application **Orders**:

- Users send requests to an API running on Azure App Service.
- The API authenticates identities, creates orders in Azure SQL Database, and publishes events to Azure Service Bus.
- Azure Monitor and Application Insights collect telemetry; the on-call operations team receives alerts.
- The business requires fast, low-error order creation and wants to keep processing orders after an Azure region outage.

Four concepts address distinct questions:

| Concept | Core question | Nature |
| --- | --- | --- |
| **SLI – Service Level Indicator** | What service quality are users receiving right now? | **Measurement** from real data |
| **SLO – Service Level Objective** | What quality level counts as passing over a time window? | **Target** for one or more SLIs |
| **RTO – Recovery Time Objective** | When a disruption occurs, how quickly must the service recover? | **Recovery time limit** accepted by the business |
| **RPO – Recovery Point Objective** | After a disaster, how much recent data loss can the business tolerate? | **Time-bounded data-loss limit** |

**SLO is not RTO; RPO is not downtime duration.** SLIs/SLOs guide day-to-day service quality management; RTO/RPO guide the design and verification of incident recovery capabilities. These metrics are related, yet must be defined separately.

### Lesson Outcomes

You will be able to define user-centric SLIs, set SLOs with clear measurement windows and error budgets, derive RTO/RPO from business impact, choose Azure approaches that meet targets, write basic monitoring queries, and run recovery drills with pass/fail criteria.

## 2. Choosing SLIs That Reflect User Experience

An SLI is a measurable value derived from events, requests, transactions, or probes. Do not confuse an SLI with the name of a tool. Application Insights, Azure Monitor, or Azure Load Testing only help collect or test data; the operations team must still **define what a good experience looks like**.

### 2.1 Common SLIs

| Category | Example SLI | Meaning to users |
| --- | --- | --- |
| Availability / success | Share of valid requests served successfully | Can the action be completed? |
| Latency | Share of successful requests completing within 300 ms, or p95 latency | Is the action fast enough? |
| Correctness | Share of orders with accurate totals and status | Is the result accurate? |
| Freshness | Share of orders appearing in reports within 2 minutes | Is data up to date in time? |
| Durability | Share of acknowledged data retrievable after an outage | Does written data still exist? |
| Completion / background jobs | Share of events processed completely within 5 minutes | Do queues and async jobs keep up? |

Do not use CPU, disk usage, or replica count as the primary SLI for customer goals. They are useful **diagnostic signals**, but CPU below 50% does not prove users are successfully placing orders.

### 2.2 Defining Eligible Requests and Measurement

For an order creation API, you might define:

- **Eligible requests**: all valid `POST /orders` requests crossing the chosen measurement boundary; exclude internal health probes and identifiable synthetic test traffic per documented rules.
- **Good requests**: eligible requests that complete with a correct business outcome and without service-side errors.
- **Bad requests**: the remaining eligible requests, including timeouts, 5xx errors, and business errors as specified by the SLI.

Success-rate SLI over window $W$:

\[
\mathrm{SLI_{success}}(W)=\frac{\text{number of good requests in }W}{\text{number of eligible requests in }W}\times100\%.
\]

For example, with 1,000,000 eligible requests over 28 days, of which 998,900 are good requests:

\[
\mathrm{SLI_{success}}=\frac{998\,900}{1\,000\,000}\times100\%=99.89\%.
\]

When establishing the denominator, agree on at least these conditions:

1. **Measurement boundary**: API gateway, ingress, Front Door, or in-app instrumentation? Requests failing before reaching the app may not appear in application logs.
2. **User group / path**: all customers, just the ordering flow, a specific geography, or key tenants?
3. **Success status**: 4xx errors caused by invalid client input may represent correct behavior; do not blindly count every 4xx as a service failure. Conversely, an HTTP 200 that creates a corrupted order is not a good request either.
4. **Timeouts and retries**: how are client-side timeouts, load-balancer rejections, or retry duplicates counted? Do you count individual requests or the final business transaction?
5. **Missing data**: telemetry gaps must never automatically be interpreted as 100% success.

A key principle is **never beautify metrics by arbitrarily excluding failures or maintenance that genuinely impact users**. Every exception must be defined upfront, documented, and applied consistently.

### 2.3 Latency SLIs: Percentiles and Good Thresholds

Two common ways to measure latency:

- **p95 latency**: 95% of observed requests have latency no greater than the p95 value. For instance, p95 = 280 ms indicates 95% of samples responded within roughly 280 ms.
- **Proportion of fast requests**: eligible requests completing within a 300 ms threshold divided by all eligible requests. This pairs easily with error budgets because each request is classified good/bad.

The two are not strictly equivalent once you factor in success criteria, timeouts, sampling, and measurement windows. Example combined SLI:

\[
\mathrm{SLI_{fast\_success}}=
\frac{\text{successful requests with latency}\leq300\,\mathrm{ms}}
{\text{eligible requests}}\times100\%.
\]

Set thresholds based on the actual operation. A product catalog read API has different targets than a multi-step payment flow or a data sync job; do not impose a single 300 ms threshold on every workload.

## 3. Setting Operable SLOs

An **SLO** specifies one or more target thresholds for an SLI along with an **evaluation window**. Illustrative example for Orders:

| Journey | SLI | Illustrative SLO | Window |
| --- | --- | --- | --- |
| Order creation | Share of valid requests completing accurately | At least **99.9%** | Rolling 28 days |
| Order list read | Share of requests succeeding in ≤ 300 ms | At least **95%** | Rolling 28 days |
| Order event sync | Share of events processed within ≤ 5 minutes | At least **99.5%** | Rolling 7 days |
| Sign-in | Share of user sign-ins completing successfully across the full journey | Target agreed by business and responsibility boundary | Rolling 28 days |

Percentages in this table are **learning assumptions only**, not official Azure SLAs or commitments of a real Orders service.

A good SLO should be written as a complete statement:

> Over every rolling 28-day window, at least 99.9% of valid production user order-creation requests must complete with accurate results. Measurement is based on telemetry at the chosen API boundary, accounting for ingress timeouts and errors; synthetic traffic is separated out.

Besides the percentage, an SLO document should specify the owner, calculation formula, data source, environment/region scope, minimum volume threshold, missing-data rule, dashboard, alerts, and breach actions.

### 3.1 Distinguishing SLO and SLA

- **SLO** is an operational target set by the service-owning team; it may be stricter, looser, or scoped differently from an SLA.
- **SLA (Service Level Agreement)** is a commitment in a service agreement, potentially carrying applicability conditions or service credit terms. Each Azure product's SLA depends on SKU, configuration, region, terms, and time.
- **SLI** is the actual measured number at your application's boundary. You cannot cite a single component service's SLA as proof that the entire application meets its SLO.

If a system consists of multiple serial components, all required to work, overall availability can be lower than any individual component's. In a simplified independent model:

\[
A_{\mathrm{end\ to\ end}}\approx A_1\times A_2\times\cdots\times A_n.
\]

For example, assuming two independent components each at 99.9% availability, the theoretical availability of a path requiring both is around 99.8001%. **This is an illustrative model only**: failures can be correlated, and systems can use caching, retries, fallbacks, and various degraded states.

### 3.2 Error Budget: Allowable Errors Within the Window

With a 99.9% success-rate SLO:

\[
\mathrm{ErrorBudgetFraction}=1-0.999=0.001=0.1\%.
\]

If there are 2,000,000 eligible requests in the window, the corresponding error budget is:

\[
2\,000\,000\times0.001=2\,000\ \text{bad requests}.
\]

If 2,600 bad requests actually occur, the team exceeded the budget by 600 requests and the SLI drops to 99.87%, below the 99.9% SLO.

**Be careful to distinguish request budgets from downtime.** With a request-rate SLO, you cannot automatically convert 2,000 failed requests into minutes of downtime because traffic fluctuates hourly. If you define a separate time-based availability SLO and assume complete outage:

\[
28\times24\times60\times(1-0.999)=40.32\ \text{minutes}.
\]

The 40.32-minute figure is **an illustration of a time-based budget** over a 28-day window and does not replace the request-based calculation above.

### 3.3 Burn Rate and Response Policies

**Burn rate** indicates how many times faster than the allowable pace the error budget is being consumed:

\[
\mathrm{BurnRate}=
\frac{\mathrm{ObservedErrorFraction}}
{1-\mathrm{SLOTarget}}.
\]

With a 99.9% SLO, the allowable error rate is 0.1%. If a recent observation window shows a 1% error rate, the burn rate is **10×**. If that condition persists, the budget will exhaust much sooner than planned.

You can set multi-window alerts—such as a short window to catch severe incidents quickly and a longer window to filter transient spikes. Do not apply identical burn-rate thresholds to every SLO; tune them for traffic volume, user impact, and on-call workflows.

When the error budget is exhausted, the team can temporarily throttle high-risk changes, prioritize reliability fixes, expand canary coverage, roll back, or add tests. This policy must be agreed upon by the service owner and stakeholders; no Azure feature makes this decision for the engineering team automatically.

## 4. RTO and RPO: Two Axes of a Recovery Plan

### 4.1 RTO – How Long to Restore Service?

**Recovery Time Objective (RTO)** is the acceptable time limit to restore defined service functionality after an in-scope disruption. To measure consistently, specify:

- **Start point**: when the service first drops below minimum acceptable criteria due to the incident—not just when an alert fires or staff start investigating.
- **End point**: when critical journeys are working again at the agreed minimum level and have been verified.
- **Scope**: which system, what degradation level, how much traffic, which user regions, and which disaster scenario.

For example, an incident starts at 10:00, monitoring detects it at 10:06, and region failover plus verification finish at 10:42. **Measured recovery time is 42 minutes**, not 36 minutes from the alert. If target RTO is 45 minutes, this drill passes on timing, provided functional recovery criteria are met.

RTO typically spans several stages:

\[
T_{\mathrm{recover}}=
T_{\mathrm{detect}}+
T_{\mathrm{declare}}+
T_{\mathrm{failover}}+
T_{\mathrm{restore/verify}}.
\]

This formula is a planning model; in reality, steps overlap, interact, and wait on DNS, identity, databases, networking, or applications.

### 4.2 RPO – How Much Data Can Be Lost?

**Recovery Point Objective (RPO)** is the acceptable data-loss limit, expressed as the time interval between the incident and the **most recent consistently recoverable data point**.

For example, an incident occurs at 10:00; the latest consistent recovery point is 09:55. Data committed between 09:55 and 10:00 is at risk of loss, so **time-based data loss is 5 minutes**. If target RPO is 10 minutes, this meets the recovery-point target; you must still verify that recovered data is consistent and the business can reprocess transactions.

RPO is not simply a backup schedule. Taking a backup every 15 minutes does not prove a 15-minute RPO if backups lag, fail, lack consistency, or fail to restore. **Replication does not automatically equal RPO = 0 either**: asynchronous replication has lag and may not have received every commit before the source region went down.

### 4.3 Relationship Between RTO and RPO

~~~mermaid
flowchart LR
    A["09:55\nConsistent recovery point"] --> B["10:00\nIncident begins"]
    B --> C["10:06\nDetection / declaration"]
    C --> D["10:42\nService recovered"]
~~~

- **Actual time-based data loss:** 10:00 − 09:55 = **5 minutes**; compared against RPO.
- **Actual disruption duration:** 10:42 − 10:00 = **42 minutes**; compared against RTO.
- The two values are **relatively independent**: a system can recover very fast yet lose substantial data, or lose almost no data yet take hours to restart.

RTO and RPO must be paired with the **incident scenario**. Targets set for a single instance or availability zone failure do not automatically apply to a full region outage, intentional data deletion, or ransomware encryption.

## 5. Deriving Targets from Business Impact

Before choosing technology, conduct a right-sized **Business Impact Analysis (BIA)**. Ask product owners, operations, and security:

1. Which journeys must operate for the business to keep serving customers?
2. If stopped for 5 minutes, 30 minutes, 4 hours, or 1 day, what are the transaction, reputational, and compliance losses?
3. Which records must never be lost, which data can be reconstructed, and who owns reconciliation?
4. Which users or geographies are critical; are there peak hours, transaction cutoffs, or settlement close times?
5. What budget limits govern the trade-off between faster recovery and retaining near-real-time data?

**Illustrative** target table for the Orders application:

| Component / journey | Reference SLO | Regional-loss RTO | Regional-loss RPO | Rationale |
| --- | --- | --- | --- | --- |
| Order creation API | 99.9% good transactions / 28 days | ≤ 45 minutes | ≤ 5 minutes for recorded orders | Lost transactions disrupt sales |
| Catalog lookup | 99.5% good requests / 28 days | ≤ 4 hours | ≤ 24 hours for resyncable data | Can serve cached copy and refresh |
| Reporting dashboard | 99% jobs on time / 7 days | ≤ 8 hours | ≤ 1 hour | Can reload data from transactional source |
| Critical audit logs | Measure share of records stored accurately and completely | Per investigation/compliance policy | May require very low data loss | Hard to reconstruct historical events |

These are hypothetical design targets, **not proof that Azure guarantees achieving these RTO/RPO values**. For example, RPO ≤ 5 minutes for orders may be unsuitable if financial transactions allow zero lost commits. When a system needs near-zero RPO, architecture, commit protocols, and reconciliation must be designed and evaluated specifically.

### 5.1 Often-Overlooked Dependencies

For the ordering API, map the entire path:

~~~mermaid
flowchart TD
    U["Users"] --> F["Azure Front Door / DNS"]
    F --> W["App Service / API"]
    W --> I["Microsoft Entra ID or identity provider"]
    W --> D["Azure SQL Database"]
    W --> Q["Azure Service Bus"]
    Q --> J["Background worker"]
    W --> O["Azure Monitor / Application Insights"]
~~~

In this diagram, components play different roles; not every operation touches all of them. Draw a **dedicated critical path per journey**. A DR plan that starts App Service in a backup region without DNS routes, secrets, role assignments, database connectivity, or queues has not met end-to-end RTO.

## 6. Designing Azure to Meet SLIs/SLOs

A good SLI must be backed by architecture, not just dashboards:

- **Survive instance failures:** use scale-out, health checks, bounded retries, timeouts, and appropriate circuit breakers; track real user impact.
- **Survive zone failures:** evaluate Azure SKUs/services supporting availability zones and configure zone redundancy per region. Support and behavior vary across products.
- **Survive region failures:** prepare redirectable entry points (such as Front Door and proper routing), compute in another region, data with replication/restore strategies, plus matching network, identity, and secrets configuration.
- **Preserve data correctness:** use transactions, idempotency keys, outbox/inbox patterns, or reconciliation across retries, failovers, and duplicate events; never treat HTTP 2xx rate as sufficient.
- **Limit blast radius:** isolate workloads, scope RBAC appropriately by resource group/subscription, restrict automation privileges, and roll out changes via canary/rolling updates where supported.

**Zone redundancy is not cross-region DR**: multiple zones within one region mitigate certain local faults but do not protect against a region-wide outage. Conversely, multi-region placement does not automatically guarantee consistent data or instant failover.

### 6.1 Connecting Targets to Observable Configuration

For API SLOs, collect telemetry at the boundary users experience. Application Insights SDK/auto-instrumentation provides request, dependency, exception, and distributed tracing telemetry; Azure Monitor collects metrics/logs and drives alerts; availability tests simulate user traffic from external locations.

Combine at least two perspectives:

- **Inside-out:** backend request duration and outcome, SQL dependencies, application exceptions, compute saturation.
- **Outside-in:** HTTP/HTTPS probes, sign-in checks, or synthetic journeys traversing edge, DNS, routing, and network. Simple probes alone do not prove the real ordering workflow works properly.

Without ingress telemetry, requests failing before reaching the application can go unnoticed. Probes and user telemetry each have their own biases; document them in your SLI definition.

## 7. Designing Azure to Meet RTO/RPO

DR engineering choices should start from each data source and each outage scenario:

| Need | Azure services / capabilities typically evaluated | Points to verify by testing |
| --- | --- | --- |
| Compute in backup region | Deploy App Service, Azure Container Apps, AKS, or VMs in a second region; Azure Site Recovery for applicable VM scenarios | Provision/start time, images/config, autoscale, health checks, DNS/routing, dependencies |
| Transactional database | Azure SQL failover groups or active geo-replication depending on service type and config; backups/point-in-time restore | Replication lag, consistency, endpoint switching, data loss, permissions, post-failover app behavior |
| Distributed data | Azure Cosmos DB multi-region and appropriate consistency/failover options | Actual RPO, conflict behavior, session/consistency, backup options for bad deletes |
| Blobs / files | Azure Storage redundancy and geo-redundancy options (e.g., GRS/GZRS/RA-GRS per service and region) | Failover conditions, replication lag, supported service scope, recently written data |
| Backup and recovery | Azure Backup and service-native backup/PITR features | Frequency, retention, actual restore testing, immutability/delete protection as needed |
| Routing and health | Azure Front Door, Traffic Manager, DNS, load balancing, and proper health probes | How healthy endpoints are determined, propagation, caching, TLS/certs, safe routing |

Support, pricing, SLAs, and failover behavior vary by SKU, region, configuration, and time. **Never infer guaranteed RTO/RPO from feature names like "geo-redundant" or "auto-failover."** Verify service limits in your actual architecture and rehearse them.

### 7.1 Replication and Backups Address Different Risks

Replication gets data to a standby location faster, but it can also replicate bad changes, accidental deletes, or encrypted data. Independent backups with retention and tested restores address logical corruption and attacks; however, restoring from backup can take longer than failing over to a replica.

A complete strategy must cover both **regional loss** and **logical data corruption**. Depending on targets, combine replicas for lower RTO with backups/point-in-time restore to return to a clean data point.

### 7.2 Cross-Component Data Consistency

Suppose the API writes an order to Azure SQL and publishes an event to Service Bus. During a regional failover, you may encounter:

- The order committed to SQL, but the event was never sent.
- The event was sent, but the consumer never acknowledged it.
- The event is redelivered after the consumer had already processed it successfully.

Therefore, RPO is not just "up to which minute does the database still have data." You must define consistency points across orders, payments, queue state, and integrated systems. Patterns like **transactional outbox**, idempotent processing, retries with backoff, and reconciliation jobs help applications recover accurately when components have differing RPOs.

### 7.3 Failure Scenarios Drive Design

| Scenario | Response to prove |
| --- | --- |
| One App Service instance fails | Health probes, scale-out/restart/route to healthy instances |
| Availability zone experiences outage | Zone-resilient setup and backing data free of single points of failure |
| Entire region goes down | Ability to serve in another region, data failover, and access routing |
| Accidental deletion / data corruption | Backups, point-in-time restore, RBAC, reconciliation, and clean-data recovery process |
| Token or identity outage | Scenario-tested service access/recovery permissions without storing secrets in runbooks |
| Infrastructure outage from config update | Verified rollback/configuration; controlled blast radius |

Each scenario may have distinct RTO/RPO targets. Record plan versions, owners, and criteria for escalating from normal recovery to full DR.

## 8. Collecting SLIs with Azure Monitor and Application Insights

### 8.1 Choosing Telemetry Sources

For workspace-based Application Insights, request logs typically reside in the **AppRequests** table in a Log Analytics workspace, with columns such as `TimeGenerated`, `AppRoleName`, `Success`, `DurationMs`, and `ItemCount`. Table and field names may differ if you query another Application Insights surface or use custom instrumentation; verify the actual schema in your application.

Illustrative example for the Orders application's request success rate over a **rolling 28 days**:

~~~kusto
let lookback = 28d;
AppRequests
| where TimeGenerated >= ago(lookback)
| where AppRoleName == "orders-api"
| where Name !in ("GET /healthz", "GET /readyz")
| summarize
    Eligible = sum(ItemCount),
    Good = sumif(ItemCount, Success == true)
| extend
    SuccessSLI_pct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(Good) / todouble(Eligible)
    )
| project Eligible, Good, SuccessSLI_pct
~~~

Notes:

- **ItemCount** estimates original request counts when Application Insights sampling is active; counting each log row as one request can skew ratios.
- **Success** reflects what instrumentation recorded; if business rules need to exclude expected client errors or evaluate actual order outcomes, normalize SLI fields/logic instead of relying solely on `Success`.
- **Name** and **AppRoleName** are example values; replace them with your real application name, operations, and filters.
- If **Eligible = 0**, never mark the SLO as 100% met; that represents a **missing-data / zero-traffic** state to handle per policy.
- Sampling can affect measurements of low-volume segments. For critical SLIs, consider edge telemetry, unsampled metrics, or trusted transaction sources, and reconcile calculations.

Example share of requests succeeding and completing in **≤ 300 ms**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(28d)
| where AppRoleName == "orders-api"
| where Name !in ("GET /healthz", "GET /readyz")
| summarize
    Eligible = sum(ItemCount),
    FastGood = sumif(ItemCount, Success == true and DurationMs <= 300)
| extend
    FastSuccessSLI_pct = iff(
        Eligible == 0,
        real(null),
        100.0 * todouble(FastGood) / todouble(Eligible)
    )
| project Eligible, FastGood, FastSuccessSLI_pct
~~~

To evaluate latency at p95, you can compute percentiles over `DurationMs` after filtering the same request set. However, percentiles over sampled log rows may not reflect `ItemCount` weights accurately. For high-precision SLIs, verify telemetry collection and percentile calculation design.

### 8.2 Dashboards and Alerting

For Orders, a minimum dashboard should display:

1. Daily/hourly SLI and rolling 28-day SLI alongside the SLO target.
2. Eligible requests, bad requests, remaining error budget, and burn rate.
3. Latency p50/p95/p99 or fast-request share, traffic, and errors by route/region/tenant.
4. SQL and Service Bus dependency health, exceptions, retries, and queue depth.
5. Multi-location synthetic availability test results, Azure Service Health, and related resource health.

In Azure Monitor, you can use Log Analytics/KQL, metrics, workbooks/dashboards, metric or log search alerts, and Action Groups to notify responsible teams. For critical alerts, specify **evaluation window and minimum sample rate**, no-data rules, recipients, runbooks, and alert-storm suppression.

**SLO is not an alert threshold:** a single burst of errors may not breach a 28-day SLO yet, but a rapid sustained error stream must be detected immediately. Multi-window burn-rate alerts balance sensitivity against noise.

## 9. Measuring RTO/RPO Through Drills Instead of Guessing

RTO/RPO are targets. To know whether your actual architecture meets them, conduct **DR exercises** and record the results of each drill.

### 9.1 Region-Loss Drill Scenario

Suppose:

- Target RTO: **≤ 45 minutes** for the order-creation journey to return at minimum capacity.
- Target RPO: **≤ 5 minutes** for acknowledged orders.
- Simulated outage starts at **10:00**; on-call receives alert at **10:06**.
- Secondary-region API and target database come online, health checks pass, and a test order succeeds at **10:42**.
- After reconciliation, the last consistently committed data point before the outage at source is **09:57**.

Calculations:

\[
\mathrm{ActualRTO}=10{:}42-10{:}00=42\ \mathrm{minutes};
\quad
\mathrm{ActualRPO}=10{:}00-09{:}57=3\ \mathrm{minutes}.
\]

On timing alone, **both targets pass** in this scenario. However, final sign-off requires checking order data, new write capability, queue processing, payment states, network paths, and user experience. Never treat a successful failover command return as the moment the service recovered.

### 9.2 Milestones to Record

| Milestone | Evidence | Why it matters |
| --- | --- | --- |
| T0 – disruption | First log/probe showing service fell below minimum service level | Measures RTO from customer impact |
| T1 – detection | Azure Monitor alert, on-call acknowledgment | Separates detection time from remediation |
| T2 – DR declaration | Authorized decision, incident commander | Prevents unauthorized failovers |
| T3 – technical recovery | Secondary region, database, routing, secrets, permissions operational | Verifies technical dependencies |
| T4 – business verification | Test transactions and customer journeys meet criteria | Agreed RTO end point |
| Recovery point | Last consistent, recoverable, reconcilable timestamp/transaction ID | Computes RPO and identifies data needing handling |

Conduct drills in approved environments to avoid unintended outages. For services where failover can lose data, run live region switches only after preparing scope, owners, rollback/failback, and risk reviews.

### 9.3 Short Runbook for Orders

A DR runbook may follow this sequence:

1. **Detect and scope**: confirm a real incident and separate application bugs from Azure regional outages; check Azure Service Health, telemetry, and dependency signals.
2. **Declare incident status**: authorized leader declares DR; record T0, impact scope, and stakeholders.
3. **Protect data**: determine the consistent replica/backup timestamp, pause conflicting writes if required by architecture, and note RPO exposure.
4. **Activate secondary region**: bring compute, routing, database, secrets, network links, and queues into the defined state; run pre-tested scripts/IaC.
5. **End-to-end verification**: place a test order, query data, test auth, check event processing, error rates, and latency under appropriate load.
6. **Communicate and monitor**: update operations/business stakeholders, watch SLIs, check queue backlog, and reconcile pending data.
7. **Controlled failback**: return to the source region only when data, write direction, routing, and business criteria are ready. Failback is a separate plan, not an automatic step right after failover.

Runbooks must be version-controlled, stored where they remain accessible if the primary system goes down, rehearsed regularly, and assigned specific owners. If only one person knows how to recover, projected RTO will rarely hold in practice.

## 10. Connecting SLOs with RTO/RPO and Cost Trade-Offs

A design can **meet RTO/RPO** during a disaster yet still **breach its SLO** over the evaluation window. For example, a 99.9% time-based availability SLO over 28 days budgets roughly 40.32 minutes of total outage; a 42-minute region outage exhausts that budget even though a 45-minute RTO passes.

Conversely, an application with a 99.95% SLI last month might still lack backups, untested failover, and miss its RPO when data corrupts. Examine both **day-to-day operational quality** and **resilience to rare, high-impact events**.

Choices carry real trade-offs:

- Higher SLOs can require greater redundancy, tighter monitoring, canaries, fault-injection testing, and stronger on-call operations.
- Shorter RTO typically demands warmer standby compute/routing; active-active or warm standby costs more than cold restores in many cases.
- Smaller RPO typically requires faster replication, stricter sync/consistency mechanisms, or transactional recovery—while still accounting for logical errors.
- Multi-region setups increase data transfer, operational, testing, and identity/network complexity costs. Weigh these against outage losses.

A practical approach is **tiering by criticality**: core transactions and data get stricter targets, while reporting can accept slower recovery. Avoid setting every system to "99.999% and zero RPO" without a confirmed BIA, technical design, and budget.

## 11. Reliability Target Design Checklist

For **each critical journey** of an Azure application, operational docs should record:

| Item | Question that must be answered |
| --- | --- |
| Owner and business value | Who is accountable? What do users lose when the journey stops? |
| SLI | What are good events, eligible events, measurement boundaries, and telemetry sources? |
| SLO | What is the threshold, over what window; what are error budget and no-data rules? |
| Related SLAs | Which product/partner/provider commitments must be cross-checked? |
| RTO | Which scenario, how are T0/T4 defined, and what is the minimum service level? |
| RPO | Which data, which consistency point, how is loss measured, and what reconciles it? |
| Azure architecture | Single points of failure, zone/region dependencies, replication, backups, networking, identity? |
| Evidence | SLI dashboards, alerts, latest restore/DR drill results, actual RTO/RPO? |
| Operations | Runbooks, failover approvers, on-call, comms, rollback/failback? |
| Cost and approval | Which trade-offs were accepted, and when are targets reviewed? |

Update this documentation whenever regions, SKUs, databases, data flows, traffic, release cadences, or business requirements change. Good SLO/RTO/RPO targets have clear owners, consistent measurements, and repeated verification evidence.

## 12. Practice Exercises and Self-Check

### Exercise 1: Calculate SLI, Error Budget, and Burn Rate

The Orders application has a **99.9%** successful order-creation request SLO over **28 days**. Over the last window, verified telemetry shows **1,200,000** eligible requests, with **1,198,500** good requests.

Task: calculate the SLI, bad request count, error budget, remaining bad requests allowed, and conclude whether the SLO passed or missed.

**Reference solution:**

- SLI = 1,198,500 / 1,200,000 × 100% = **99.875%**.
- Bad requests = 1,200,000 − 1,198,500 = **1,500**.
- Allowable error budget = 1,200,000 × 0.001 = **1,200 bad requests**.
- Remaining budget = 1,200 − 1,500 = **−300**: exceeded by 300 bad requests, **SLO missed**.
- Observed error fraction = 1,500 / 1,200,000 = **0.125%**. Window-wide burn rate = 0.125% / 0.1% = **1.25×**.

### Exercise 2: Verify RTO/RPO

An application has **RTO ≤ 30 minutes** and **RPO ≤ 10 minutes** for regional loss. An outage begins at **14:00**; operations receives the alert at **14:05**, completes failover at **14:25**, and the first new transaction succeeds at **14:38**. The latest consistently recovered record timestamps to **13:53**.

**Reference solution:**

- Actual RTO = 14:38 − 14:00 = **38 minutes** → **missed** the 30-minute RTO. Completing technical failover at 14:25 does not prove the service is operational.
- Actual RPO = 14:00 − 13:53 = **7 minutes** → **met** the 10-minute RPO on timing, provided recovered transactions are consistent and reconciled.
- RTO improvements: shorten incident confirmation, automate safe traffic switching, pre-warm secondary compute, and test networking/identity/dependencies and canary checks.

### Exercise 3: Choose Architecture Options

An internal dashboard can reload data from source systems after 24 hours. Meanwhile, a payment API must never report success and then lose transactions on failover. Propose **distinct** SLIs/SLOs and RTO/RPO targets for the two systems, explaining choices for backups, replicas, reconciliation, and budget. Do not apply a single number to both.

### Self-Check Questions

1. Why are CPU metrics or replica counts poor primary SLIs for the order-creation journey?
2. An API returns HTTP 200 yet creates an incorrect order: how should a business SLI classify this request?
3. Why can a request-based error budget not be converted directly into "minutes of downtime"?
4. Does meeting this month's SLO prove post-disaster RPO? Why or why not?
5. Why does geo-replication not automatically guarantee RPO = 0 or replace independent backups?
6. Why must actual RTO end at business-journey recovery rather than when a failover command succeeds?
7. When designing DR for an app spanning Front Door, App Service, Entra ID, Azure SQL, and Service Bus, what dependencies beyond compute must you check?

**Key takeaway:** Choose **SLIs that measure real user experience**, set **SLOs with windows and error budgets**, derive **RTO/RPO from business impact and failure scenarios**, and use Azure Monitor/Application Insights, per-service redundancy/recovery features, and DR drills to verify. Targets only hold operational value when they are measurable, owned, and backed by pass/fail evidence.
