# Assessing Real Costs, Operability, and Residual Risk

## 1. Why Must Architecture Assessment Look Beyond System Diagrams?

A cloud architecture can look clean on a diagram: decoupled services, managed databases, autoscaling apps, backed-up data, and multi-AZ networking. Yet that architecture may still fail the business if:

- Real bills after three months double the forecast due to network egress, logs, backups, and non-prod environments.
- The system spans many components while operations lacks on-call staff, permissions, dashboards, or recovery procedures.
- Software meets latency goals under normal load yet cannot prove recovery when an availability zone or dependency fails.
- Implemented controls still leave risks of data loss, outages, data leaks, or vendor lock-in with no accountable owner.

In the **CLOUD_ARCHITECTURE** module, architecture assessment must connect **business requirements → networking, compute, data, and deployment choices → real costs → operability → residual risk**. This applies **Well-Architected** thinking: asking not just whether the system *works*, but whether it *runs sustainably, securely, scalably, and recoverably within existing resources*.

**Learning objectives:** After this lesson, you will be able to build a verifiable Total Cost of Ownership (TCO) model; assess operational readiness; build a residual risk register; compare options by criteria, constraints, and evidence; and decide whether to approve, add controls, or defer deployment.

### 1.1. Three Core Questions

| Assessment Dimension | Question to Answer | Minimum Evidence |
|---|---|---|
| **Real Cost** | How much does it cost to build, sustain, scale, and recover? How does spend vary with load? | Cloud bills, usage metrics, pricing assumptions, TCO sheets, scenario models |
| **Operability** | Can the team safely detect, triage, recover, and modify the system? | SLOs, dashboards, alerts, runbooks, restore/failover drills, ownership assignments |
| **Residual Risk** | After controls are applied, which risks remain; who can accept and track them? | Risk register with cause, impact, controls, residual level, owner, and review date |

These three dimensions interlock: an option with cheap infrastructure can be expensive in ops labor; costlier redundancy can reduce outage losses; strong security controls can add cost and latency. Never optimize one dimension without measuring the others.

## 2. Defining Scope and Comparison Baselines Before Calculating

There is no "best architecture" without context. Before an architecture review, confirm at minimum:

1. **Business context:** transaction volumes, revenue or outage impact, peak windows, seasonality, critical data.
2. **Workload:** requests, successful transactions, data sizes, read/write ratios, cache hit rates, internal and external cloud traffic.
3. **Service quality:** availability, latency, and error SLOs; RTO and RPO per data/function class.
4. **Security and compliance:** access controls, encryption, secrets management, network segmentation, data residency, log retention.
5. **Delivery constraints:** budget, launch schedule, team skills, on-call capacity, existing tech, vendor lock-in tolerance.
6. **Analysis horizon:** current monthly cost, year one, three years; baseline load, peak load, single-zone outage, and growth.

### 2.1. Separating Mandatory Conditions from Optimization Criteria

**Mandatory conditions (hard constraints/gates)** must be checked before scoring:

- Personal data must never reside outside compliant data-residency regions.
- Payment flows must prevent duplicate processing and maintain sufficient audit logs.
- Transaction data RPO must not exceed business-approved limits.
- The option must have an on-call rotation and tested recovery procedures.

If an option violates a mandatory condition, a low cost score **does not** make it acceptable. Trade-off criteria such as lower latency, flexibility, automation, or lower spend should only decide **among options that passed all gates**.

### 2.2. Baseline Table and Evidence Sources

| Attribute | Hypothetical Example Value | Real Source to Verify |
|---|---|---|
| API requests/month | 2,000,000 | API gateway and application metrics |
| Completed orders/month | 100,000 | Business system / ledger |
| Operating hours | ~730 hours/month | Service uptime, regions, peak hours |
| Internet and cross-region traffic | Measured in GB or TB/month | Billing, network flow logs, CDN, and NAT metrics |
| Projected growth | 0%, 30%, 100% scenarios | Business forecasts, historical data |
| SLOs and RPO/RTO | Approved by business owners | SLAs, BIA (business impact analysis), DR policy |
| Labor cost | Hours worked × fully loaded rate | Timesheets, HR, allocated unit rates |

**Note:** Figures in this lesson are illustrative data for learning calculation methods. They **do not** represent real cloud provider quotes or real SLO performance for any configuration.

## 3. Assessing Real Costs: From Bills to Total Cost of Ownership

### 3.1. Distinguishing List Price, Actual Spend, and TCO

- **List price:** unit rates per hour, GB, request, IOPS, or data volume; may not reflect discounts, usage commitments, taxes, or current configs.
- **Actual spend:** amount incurred in a period per billing and contracts, potentially adjusted for credits, discounts, and taxes depending on reporting rules.
- **Total Cost of Ownership (TCO):** infrastructure, third-party services, and staffing resources required to build, operate, secure, support, modify, and recover the system over a period.
- **Unit economics:** cost per unit of business value, e.g., USD/successful order, USD/1,000 processed transactions, or cost per active customer.

Never infer TCO from compute price tables alone. A service with cheap CPU can incur steep NAT, data transfer, support, or manual ops costs.

### 3.2. Required Items in a Cost Inventory

| Category | Components to Include | Easy-to-Miss Traps |
|---|---|---|
| **Compute** | VMs, containers, serverless, load balancers, background jobs, autoscaling, idle resources | 24/7 instances, minimum replicas, cold starts driving over-provisioning |
| **Database** | Instances, vCPU/RAM, storage, IOPS, read replicas, backups, PITR, replication | Billed I/O, storage growth, standby regions, trial restores |
| **Storage** | Object storage, block/file storage, snapshots, retention, retrieval, lifecycle | Multiple object versions, cold-tier retrieval fees, duplicate backups |
| **Networking** | Internet egress, cross-region/cross-zone traffic, NAT gateways, private endpoints, CDN, DNS | Per-GB plus per-hour fees; chatty cross-AZ service calls |
| **Messaging & integration** | Queues, brokers, event streams, API calls, notifications, ETL | Retries, DLQs, retention, and read/write operation counts |
| **Observability** | Log ingestion, retention, metric cardinality, traces, SIEM, alerting | Debug logs left on, excessive tracing, high-cardinality labels |
| **Security** | WAF, secrets managers, KMS, vulnerability scans, audit logs, key rotation | Per-request, per-key, per-API-call, and audit volume charges |
| **DR / HA** | Cross-region backups, standby capacity, replication, failover headroom, drills | Always-on standby resources or traffic surges during failover |
| **Non-prod environments** | Dev, test, staging, preview, CI/CD runners, benchmarks | Production-sized test envs left running off-hours |
| **People & processes** | On-call rotation, incident response, patching, upgrades, compliance, audits, training | SRE/DBA toil missing from cloud bills |
| **One-time costs** | Migration, training, IaC, refactoring, data backfill, integration setup | Overlooking conversion effort and dual-running overlap periods |

**Cost counting boundaries must be explicit:** support fees may allocate account-wide; monitoring platforms may bundle log storage separately. Avoid double-counting when calculating TCO, and document allocation rules for shared costs.

### 3.3. Formulas and Analysis Cadence

~~~text
Cost_month =
    Compute
  + Data_platform
  + Storage_and_backup
  + Network
  + Messaging_and_integration
  + Observability
  + Security_and_support
  + DR_and_other_shared_allocations

Operations_month =
    Sum(Hours_by_role * Fully_loaded_hourly_rate)
  + External_support_services

TCO_month_equivalent =
    Cost_month
  + Operations_month
  + One_time_migration_cost / Amortization_months

Cost_per_successful_order =
    Allocated_TCO_month / Successful_orders_month

TCO_12_months =
    Sum(monthly_actual_or_forecast_TCO over 12 months)
~~~

The **monthly equivalent** aids option comparison, though it is not a binding accounting rule: capitalization, depreciation, amortization, and cash timing follow company finance policy. Keep one-time costs clearly separated so year-one and steady-state years are not obscured.

For hourly infrastructure, rough cost equals **usage hours × effective unit price**. For transaction-billed services, use **request count × tier-appropriate unit price**, adding data transfer fees where applicable. When applying discounts/commitments, distinguish **amortized** costs from period cash outlays.

### 3.4. FinOps-Style Actual vs. Estimate Reconciliation

A monthly cost review loop:

1. **Allocate:** tag services, environments, owning teams, cost centers, workloads, and products; define shared-cost split rules.
2. **Reconcile:** match issued invoices against cost explorer and usage data, locking periods and handling credits/taxes/discounts.
3. **Explain variance:** separate cost changes caused by **usage volume**, **unit price/tier shifts**, **architectural changes**, and **one-time fees**.
4. **Measure unit economics:** cost per successful transaction, per GB processed, or per active customer; also track failed transaction counts.
5. **Act:** adjust right-sizing, retention, routing, caching, reservations/commitments, or non-prod schedules; assign owners and expected savings.
6. **Verify outcome:** measure spend and SLOs post-optimization so cost cuts never raise error rates or weaken safety.

A common mistake is seeing a 20% bill increase and blaming the architecture when order volume grew 50%. Evaluate **total spend and unit cost** together. Conversely, falling unit cost while total spend breaches budget still requires a business decision.

## 4. Quantitative Example: Choosing a Deployment Option

Suppose an ordering system has two candidates:

- **Option A:** modular monolith on managed containers running across multiple availability zones in one region; managed database with backups and restore; no cross-region warm standby.
- **Option B:** multiple decoupled services plus a **warm standby** DR region; adds cross-region replication, queues, and failover orchestration tooling.

Both must be evaluated on the exact same workload: **2 million API requests and 100,000 successful orders per month**. Assume load, log retention, security controls, and unit rates are normalized into USD/month for comparison. The table below is strictly a **hypothetical dataset**, not market pricing.

### 4.1. Illustrative Cost Breakdown (USD/month)

| Line Item | Option A | Option B |
|---|---:|---:|
| Application compute and background jobs | 1,200 | 1,900 |
| Database | 950 | 1,450 |
| Cache, queue, integration | 280 | 650 |
| Storage and backups | 260 | 460 |
| Internet egress, NAT, cross-zone | 720 | 1,260 |
| Logs, metrics, tracing | 420 | 800 |
| WAF, secrets, support, and shared allocations | 310 | 510 |
| Cross-region DR infra and replication | 0 | 1,180 |
| **Total cloud services / month** | **4,140** | **8,210** |

To factor in **operability**, assume:

- Ongoing operational effort is **90 hours/month** for A and **160 hours/month** for B.
- Assumed fully loaded labor rate is **45 USD/hour**.
- One-time setup/migration cost: A **1,800 USD**, B **5,400 USD**, amortized over **12 months** for comparison.

| Metric | A | B |
|---|---:|---:|
| Cloud services / month | 4,140 | 8,210 |
| Operations / month | 90 × 45 = 4,050 | 160 × 45 = 7,200 |
| Amortized one-time cost / month | 1,800 / 12 = 150 | 5,400 / 12 = 450 |
| **Monthly equivalent TCO** | **8,340** | **15,860** |
| **12-month TCO (constant load assumed)** | **100,080** | **190,320** |
| **TCO / successful order** | **0.0834 USD** | **0.1586 USD** |

Under these assumptions, Option B carries **90,240 USD higher year-one TCO**. This is **not** proof that A is always better: B may satisfy DR mandates that A cannot meet, or cut outage losses. Furthermore, real ops effort and cross-region fees must be measured/estimated using the team's own data; applying dummy tables to a real system yields wrong conclusions.

### 4.2. Bringing Service Quality into the Comparison

Suppose the business requires restoring ordering in another region within **60 minutes** with at most **5 minutes of data loss** if the primary region fails completely. This example requirement must be approved by system owners. Then:

- **A** is cheaper yet **fails the DR gate** if it relies solely on backups without proving sub-60-min restore and sub-5-min RPO.
- **B** is a better **candidate** thanks to warm standby, yet still requires drills verifying RTO/RPO, write fencing, and replication lag; having standby infra does not guarantee meeting targets.
- A cheaper **Option C** might emerge—for instance, a modular monolith with cross-region DB replication and failover runbooks. Price and test it before declaring B optimal.

If the problem does not require cross-region DR or allows wider RTO/RPO, B's operational overhead may outweigh its benefits. Conversely, if each hour of checkout downtime causes massive losses, the extra 90,240 USD/year may be justified—only after quantifying **actual risk reduction**.

### 4.3. Sensitivity Analysis

Single-point estimates hide cost risk. Model at least three scenarios per option:

| Scenario | Changes to Simulate | Risk Signals |
|---|---|---|
| **Base** | Baseline load and traffic | Average spend, current operational capacity |
| **High growth** | Higher requests/orders, storage, and logs; hotspots | How compute autoscale, DB IOPS, egress, and logs scale |
| **Failure / DR** | Region outage, traffic shift, queue replay, restores | Data transfer spikes, standby scaling, on-call strain |
| **Provider pricing change** | Discount drops or commitment expires | Exposure to list rates and commitment lock-in |
| **Low usage** | Lower transactions while fixed baseline stays flat | Rising TCO/order; underutilized commitments |

In the A/B table, if **networking** alone doubles while all else stays constant, cloud spend rises by **720 USD/month** for A and **1,260 USD/month** for B. This is a **sensitivity test**, not a prediction that traffic will double. Inspect whether growth stems from internet egress, cross-zone chatter, or replication to target optimizations accurately.

Report estimate ranges and confidence levels (e.g., P50/P90 from simulations when historical data exists), highlighting **which assumptions swing outcomes most**. Never slap a "P90" label onto three manual guesses.

## 5. Operability: Assessing Both Systems and People

A well-operated architecture requires **observable systems**, **practiced procedures**, and **clear human ownership**. A diagram showing "managed" services does not mean the cloud provider takes over deployments, permissions, data recovery, or business incident response.

### 5.1. Capabilities That Must Be Proven

| Capability | Needed in Design | Assessment Evidence |
|---|---|---|
| Ownership / on-call | System owners, rotation, escalation, comms channels | RACI, on-call schedule, per-service assignments |
| Observability | Metrics, logs, traces, correlation IDs, health checks | Dashboards and end-to-end single-request trace |
| SLO / error budget | User-facing SLOs separating dependency faults | SLI reports, alert policies, error breakdowns |
| Incident response | Severity tiers, incident commander, comms mechanics | Runbooks and drill minutes |
| Backup / restore | Backups, retention, encryption, restore tests, permissions | Actual restore records and measured recovery times |
| DR / failover | Failure scope, promotion rules, fencing, failback | RPO/RTO drill results, data validation |
| Deployment / rollback | CI/CD, IaC, canary/blue-green, rollback, feature flags | Change logs and trial rollout results |
| Security operations | Secrets, patching, IAM, audits, threat response | Scan reports, access reviews, rotations, audits |
| Capacity / performance | Peak load tests, saturation, autoscaling, quotas | Load tests, CPU/memory/IOPS, p95/p99 latency |
| Data operations | Rollback-safe migrations, schema versioning, reconciliation | Migration plans, backfill and restore tests |
| Cost operations | Budgets, anomaly alerts, tags, unit cost, owners | Spend reports and executed optimizations |
| Knowledge transfer | Docs, backup staff, handover routines | Runbook executed successfully by a second engineer |

### 5.2. SLOs and Signals Must Tie to User Experience

Example checkout SLIs:

~~~text
Availability SLI =
    Valid checkout requests handled successfully per criteria
    /
    Total valid checkout requests

Latency SLI =
    Ratio of valid requests processed <= committed threshold
~~~

Define exactly what counts as **valid** and **successful**: properly rejecting an out-of-stock order may not be a service failure, whereas returning HTTP 202 and letting a saga stall for hours can still violate **order completion time**.

An illustrative **99.9% success over a 30-day window** SLO gives a **0.1% error budget**—or **43.2 minutes over 30 days** if converted via continuous uptime. That is not an architectural uptime guarantee; real measurement follows the exact SLI formula, traffic profile, and evaluation window.

Operations needs alerts on **customer-impacting symptoms** (error rates, latency, backlogs, stalled orders) paired with causal signals (CPU, IOPS, replication lag, quotas). Over-alerting on raw resource thresholds with no actionable step fuels alert fatigue.

### 5.3. Quantifying Operational Readiness

Use a pragmatic **0–2** scale per capability:

- **0 – Missing:** no owner or no mechanism/evidence.
- **1 – Designed:** documented and configured, not yet tested under production-like conditions.
- **2 – Proven:** clear owner, deployed, with recent test/drill evidence.

Hypothetical assessment example:

| Capability | A | B | Notes |
|---|---:|---:|---|
| Dashboards and checkout SLOs | 2 | 2 | Both have dashboards and alerts |
| Database restore | 2 | 1 | B has not tested restoring cross-region dependencies |
| Failover / failback | 1 | 0 | B has a complex design, never rehearsed |
| Deployment rollback | 2 | 1 | B lacks coordinated multi-service rollback |
| On-call / escalation | 2 | 1 | B has not completed runbook handover |
| **Illustrative total (out of 10)** | **9** | **5** | Measures **readiness**, not final architecture quality |

Scores merely prioritize remediation. If **failover** is a mandatory gate, Option B scoring **0** there remains **not ready to deploy**, even if its total score looks high. Record **evidence** and **test dates**, never bare numbers alone.

### 5.4. Estimating Real Operational Effort

Separate three effort categories:

1. **Repetitive toil:** manual fixes, noisy alert triage, restarting services, replaying failed jobs, automatable tasks.
2. **Planned maintenance:** patching, runtime/DB upgrades, cert management, schema migrations, DR drills, security hardening.
3. **Incident response & engineering:** incidents, postmortems, reliability work, training, performance tuning.

Track **hours by task type and service**, incident frequency, detection time, and recovery time; then convert to cost. Never treat on-call as "$0" merely because staff are salaried. Avoid double-counting the same engineering hours in both monthly ops and one-time project lines.

### 5.5. Runbooks Need Concrete Actions

A minimal database recovery runbook should answer:

~~~text
Trigger:
  Recovery needed due to data loss / logical corruption / region unavailable.

Detect & scope:
  Identify affected data stores and applications.
  Record timestamps, commit/replication positions, and uncertain in-flight requests.

Decide:
  Incident commander confirms incident class and restore scope.
  Data owner confirms acceptable RPO and which workflows must pause writes.

Execute:
  Isolate fault source.
  Restore backup/snapshot in a safe environment.
  Verify integrity and lock unauthorized access.
  Execute switchover or promotion via approved mechanism.

Verify:
  Run controlled test reads/writes; check business metrics and latency.
  Reconcile transactions, events, payments, or pending jobs.

Communicate & close:
  Log actual RTO/RPO, recovery timestamp, and customer impact.
  Create action items with owners and due dates.
~~~

Runbooks must be **rehearsed** by engineers outside the original design team to verify executable steps; a polished doc requiring permissions nobody holds remains an operational risk.

## 6. Residual Risk: From List of Worries to Acceptance Decisions

### 6.1. Distinguishing Inherent Risk, Controls, and Residual Risk

**Inherent risk** is risk before accounting for controls. A **control** is a preventive, detective, or corrective safeguard. **Residual risk** is the exposure remaining **after** evaluating implemented controls and their proven effectiveness.

Example:

~~~mermaid
flowchart LR
    T[Threat event: accidental data deletion] --> I[Uncontrolled impact]
    I --> C[Controls: IAM, backups, PITR, restore drills]
    C --> E{Controls proven effective?}
    E -->|With evidence| R[Assess residual risk]
    E -->|No evidence| U[Risk not yet proven reduced]
    R --> D{Residual level within risk appetite?}
    D -->|Yes| A[Owner signs risk acceptance]
    D -->|No| M[Mitigate / avoid / transfer / redesign]
~~~

Writing "backups enabled" does not reduce risk if never restored; writing "WAF enabled" does not prove zero security risk.

### 6.2. Risk Register Structure

Each row should include:

- **ID and risk statement:** *Because of cause X, event Y may occur, causing impact Z on business goals.*
- **Affected assets/scope:** data, services, customers, third parties, regions, transaction types.
- **Likelihood and impact** pre-/post-control, noting method and confidence.
- **Current controls**, test/monitoring evidence, remaining gaps.
- **Treatment:** mitigate, avoid, transfer, or accept; cost and architectural impact.
- **Decision owner, action owner, deadline**, status, and review date.
- **Triggers** invalidating the assessment: traffic growth, regulatory/contract edits, incidents, EOL, provider changes.

Hypothetical example:

| ID | Risk Statement & Impact | Existing Controls | Residual Risk | Owner & Action |
|---|---|---|---|---|
| R-01 | Primary region loss halts checkout past RTO | Cross-region backups, standby, DNS failover | **High** until promotion and transaction reconciliation are tested | SRE lead: rehearse failover/failback, measure RTO/RPO |
| R-02 | Faulty schema migration loses/corrupts data | Migration pipeline, versioned schemas, PITR | **Medium** as data rollback remains untested | DBA: rehearse on realistic sanitized copy |
| R-03 | Traffic spike breaches downstream quotas causing long backlogs | Autoscaling, queues, retries/backoff | **Medium** as provider overload is untested | Platform owner: load tests and quota plan |
| R-04 | Leaked secrets lead to unauthorized access | Secrets manager, least-privilege IAM, audits | **Medium/High** without rotation and incident drills | Security owner: rotation, detection, rehearsal |
| R-05 | Cloud egress and logs exceed budget | Budget alerts, retention, tagging | **Medium** as forecast omits failover traffic | FinOps owner: per-service alerts, cost-spike tests |

Ratings above are **illustrative only**; real assessments must never assign "high/medium" without data, likelihood analysis, damage estimates, and control verification.

### 6.3. Likelihood × Impact Scoring and Its Limits

A qualitative matrix can use a 1–5 scale:

| Score | Likelihood | Impact |
|---|---|---|
| 1 | Very rare per internal definition | Minor impact, no serious SLO breach |
| 2 | Low | Quality dip within easily recoverable bounds |
| 3 | Possible | Single capability outage or notable intervention needed |
| 4 | High | Broad disruption or major business loss |
| 5 | Very high | Severe impact on users, finances, or compliance |

~~~text
Risk_score = Likelihood_score × Impact_score

Example:
  Likelihood = 3
  Impact = 4
  Residual_score = 12 / 25
~~~

**This is an organization-defined ordinal scale, not mathematical probability.** A score of 12 does not mean 12% probability, and scores cannot be summed mechanically into expected monetary loss. Low/medium/high thresholds and acceptance authorities must be agreed upon before reviews.

Where valid estimation data exists, you can compute **annualized expected loss**:

~~~text
Expected_annual_loss ≈ P(event in year) × Financial_impact_if_event

Hypothetical example:
  Annual incident probability = 0.08
  Impact if it occurs = 80,000 USD
  Expected loss ≈ 6,400 USD/year
~~~

Expected averages do not capture extreme tail losses, non-financial harm, or correlated failures (e.g., a bad config breaking both primary and replica). Never use expected loss to justify violating laws or mandatory gates. Compare a 4,000 USD/year control strictly against the **risk reduction that control delivers**, not against total uncontrolled loss.

### 6.4. Four Risk Treatments

| Treatment | Example | Notes |
|---|---|---|
| **Mitigate** | Add PITR, WAF, rate limiting, reconciliation, failover drills | Verify effectiveness and cost; update residual risk |
| **Avoid** | Disallow active-active writes on orders until split-brain is solved | Redesign, narrow features, or halt risky workflow |
| **Transfer / Share** | Insurance, vendor support contracts, managed services | Legal liability and customer trust impact rarely transfer fully |
| **Accept** | Tolerate a few minutes of cache staleness on non-critical data | Requires proper approver, expiry date, and re-review trigger |

Never leave an "accepted" status permanent. Revisit risks whenever products, data volumes, permissions, topologies, or major incidents shift.

## 7. Synthesizing All Three Dimensions into an Architectural Decision

### 7.1. Recommended Review Workflow

~~~mermaid
flowchart TD
    REQ[Confirm business requirements & constraints] --> OPT[Define options & boundaries]
    OPT --> G{Pass hard gates?}
    G -->|No| RED[Reject or redesign option]
    G -->|Yes| COST[Assess actual/TCO & load scenarios]
    COST --> OPS[Assess operational readiness with evidence]
    OPS --> RISK[Assess residual risk & owners]
    RISK --> DEC{Residual risk acceptable?}
    DEC -->|No| ACT[Add controls / redesign / hold launch]
    ACT --> COST
    DEC -->|Yes| ADR[Write decision record, conditions & expiry]
    ADR --> VERIFY[Measure post-launch; re-review on triggers]
~~~

Outputs must not be just one aggregate score. Clearly identify which options **failed mandatory gates**, which **need more evidence**, which **are conditionally approved**, and who holds accountability.

### 7.2. Weighted Scoring After Passing Gates

Example where the organization prioritizes reliability and operability:

| Criterion (1–5 score) | Weight | A | B |
|---|---:|---:|---:|
| Verified reliability | 25% | 3 | 5 |
| Operational readiness | 20% | 5 | 2 |
| Controlled risk | 30% | 4 | 4 |
| TCO / order | 15% | 5 | 2 |
| Latency / load capacity | 10% | 3 | 4 |
| **Weighted total score** | **100%** | **4.00** | **3.55** |

Calculation:

~~~text
Weighted_score(option) =
    Sum(weight_i × score_i), where Sum(weight_i) = 1

A = 0.25×3 + 0.20×5 + 0.30×4 + 0.15×5 + 0.10×3 = 4.00
B = 0.25×5 + 0.20×2 + 0.30×4 + 0.15×2 + 0.10×4 = 3.55
~~~

**Critical caveat:** 1–5 ratings here are **illustrative assumptions**, not real review data and never substitutes for gates. If cross-region RTO/RPO is mandatory, A fails the gate and cannot be picked just for scoring 4.00. If B lacks failover tests or scores 2/5 on readiness due to missing runbooks, the decision should be **hold B until controls are proven**, or evaluate a third option.

"Controlled risk" in this table is scored "higher = safer"; if another sheet uses "higher risk score = worse," never mix the two conventions. Document definitions and evidence sources for every score.

### 7.3. Sample Architecture Decision Record (ADR)

A solid review record should include:

~~~markdown
# ADR: Architecture Selection for the Ordering System

## Context
- Workload: ...
- SLO requirements: ...
- RPO / RTO: ...
- Data and security constraints: ...

## Alternatives
- A: ... Pros / Cons ...
- B: ... Pros / Cons ...
- C (if any): ...

## Evidence
- Year-1 and 3-year TCO: ... (billing/forecast source, cutoff date)
- TCO per order: ...
- Load test, restore/failover drill results: ...
- Operational readiness and gaps: ...
- Residual risks (ID, residual level, owner): ...

## Decision
- Selected: ...
- Rationale: ... (mandatory conditions and trade-offs)
- Pre-production conditions: ...
- Risks accepted by: ... / date ...

## Follow-Up
- Accountable owner: ...
- Metrics/SLO/cost budget: ...
- Next review date: ...
- Early re-review triggers: ... (load spike, incident, pricing/architecture change)
~~~

An ADR must never just say "chose B because it's modern." State **why the selected option fits verified requirements**, remaining uncertainties, and what conditions trigger reconsidering the choice.

## 8. Lifecycle Architecture Assessment, Not Just Pre-Go-Live

### 8.1. Pre-Deployment

- Lock baselines and NFRs with business, security, SRE, and FinOps owners.
- Estimate TCO using illustrative or pilot data; list assumptions and unverified pricing scopes.
- Review SPOFs, access controls, data recovery, service limits, and external dependencies.
- Verify all hard gates; create a risk register with owners, mitigations, and due dates.
- Write runbooks; configure observability, backups, budget alerts, and verify emergency access.

### 8.2. During Pilot or Pre-Production

- Benchmark representative **average, peak, and hotspot** loads; measure autoscaling, throughput, and p95/p99.
- Test DB disconnects, downstream quotas, queue backlogs, and duplicate requests.
- Execute **real backup restores**, verifying data integrity and recovery durations.
- If cross-region DR exists, drill failover/failback, reconcile replication, and measure RPO/RTO.
- Track actual log, storage, traffic, and per-unit costs; update forecasts from live numbers.
- Conduct security reviews, threat modeling, secret rotations, and least-privilege IAM checks.

### 8.3. Post-Launch Operations

| Cadence | Focus Areas | Expected Output |
|---|---|---|
| Daily / event-driven | SLOs, incidents, budget anomalies, backlogs, security errors | Action on user-impacting signals |
| Weekly | Top cost drivers, hot services, alert noise, toil | Owned optimization tasks |
| Monthly | Actual vs. forecast, TCO/unit, residual risks, alert & quota reviews | Updated budget and risk decisions |
| Quarterly or risk-based | Restore/failover drills, access audits, capacity, vendor dependencies | Fresh DR/readiness evidence and improvement plan |
| Post-incident / major change | Re-review architecture, ADR, threat model, forecast | Updated controls, owners, scope, or decisions |

Cadences are suggestions; financial or sensitive-data systems may require tighter intervals. Any manual checks must have scheduled dates and logged outputs so they are never forgotten.

## 9. Common Assessment Anti-Patterns

| Anti-Pattern | Why It Misleads | How to Fix |
|---|---|---|
| Comparing prices via one VM or DB | Misses networking, backups, logs, DR, and ops labor | Full cost inventory and workload-level TCO |
| Picking cheapest setup at average load | Blind to peaks, hotspots, and region failures | Data-backed scenarios and load tests |
| Projecting future spend from today's bill | Ignores growth, expiring discounts, and retention growth | Driver-based forecasts and sensitivity tests |
| Claiming HA from multi-AZ/multi-region diagrams | Shared dependencies, failover, and data remain untested | Fault injection, restores, RPO/RTO reconciliation |
| Using managed services to skip on-call ownership | Customers still own configs, IAM, and app operations | RACI and verified runbooks |
| Gut-feel risk ratings without owners | Nobody fixes or formally accepts risk | Evidence-backed risk register with deadlines and escalation |
| Summing qualitative risk scores into dollar losses | Mixes ordinal ranks with probabilities/financial impact | Keep qualitative or use explicit quantitative assumptions |
| Picking highest weighted score despite gate failure | Good cost scores mask mandatory risks | Enforce hard gates before weighted scoring |
| Measuring API uptime alone | Misses stalled sagas, data loss, and failed user goals | Business-outcome SLIs/SLOs |
| Letting review docs go stale | Decisions rest on outdated loads, laws, or pricing | Re-review triggers, owners, evidence expiry dates |

## 10. Practice Exercise: Preparing an Ordering System Review

### 10.1. Prompt

A team proposes deploying a checkout system to the cloud using Options A/B from Section 4. They have a **year-one budget of 160,000 USD**, a recovery target of **≤ 60 minutes**, and **RPO ≤ 5 minutes** upon total loss of the primary region, plus a mandate for on-call staff to resolve mismatched transactions.

All figures are **hypothetical**. Complete the following:

1. Check 12-month total costs, identifying which option exceeds budget and by how much without further optimization.
2. Explain why Option A cannot be chosen solely on TCO/order if A has not proven RTO/RPO.
3. List evidence B must produce before being declared ready: failover, data integrity, backups, write ownership, staffing, and monitoring.
4. Pick the three highest-impact residual risks specific to checkout, assigning owners and concrete actions.
5. Propose an **Option C** for additional evaluation; state under what conditions C makes sense.
6. Write a short ADR stating a provisional choice or hold pending verification, gates, costs, risk acceptance, and review date.

### 10.2. Reference Solution Guide

- From Section 4 calculations, **A = 100,080 USD/year**; **B = 190,320 USD/year**. Against a 160,000 USD budget, **B is 30,320 USD over budget**, while **A is 59,920 USD under budget**.
- **A cannot be approved** without evidence meeting the RTO/RPO gate; if backups alone fall short, add DR capabilities or redesign.
- **B is also not ready to deploy** while failover/failback are untested and ops readiness sits at design level. Measure real RPO/RTO, prove single write ownership, and reconcile uncertain orders/payments.
- Evaluate **C: multi-AZ modular monolith with cross-region DB replica/standby and fenced promotion**. Measure TCO, recoverability, and ops burden instead of assuming it is always cheaper or right.
- An appropriate decision while tests are missing is **"hold production approval; approve pilot/DR drill and cost-model update"** with specific owners, deadlines, and pass criteria. That is a valid review outcome, not a review failure.

### 10.3. Output Self-Assessment Checklist

- [ ] Specific workload, traffic, data, and SLO/RTO/RPO descriptions included.
- [ ] Cloud services, data transfer, observability, backups, DR, support, and operational effort fully accounted for.
- [ ] Actual/forecast costs cite sources, scope, periods, pricing assumptions, and allocation rules.
- [ ] Business unit economics and at least one sensitivity scenario included.
- [ ] Evidence exists for ownership, monitoring, runbooks, restore/failover, and rollback.
- [ ] Post-control risk register includes owners, deadlines, review triggers, and risk acceptors.
- [ ] Hard gates evaluated first, never offset by cost scores.
- [ ] ADR reflects trade-offs, evidence limits, and pre-production gates.
- [ ] Post-launch re-measurement scheduled—especially after incidents, load shifts, pricing edits, or topology changes.

## 11. Conclusion

Reliable cloud architecture assessment rests on **fully scoped, verifiable costs**, **practiced operability**, and **documented residual risks with clear accountability**. One deployment model may look cheap on paper yet burn engineering hours; another with multi-region standby cuts outage risk while adding spend, latency, and complexity.

The pragmatic workflow is **lock mandatory requirements → measure workload and TCO → rehearse operations → validate control effectiveness and residual risk → compare gate-passing options → record conditional decisions → monitor and re-assess**. That ensures architectures are selected for real business goals and capabilities rather than cloud service counts or polished diagrams.
