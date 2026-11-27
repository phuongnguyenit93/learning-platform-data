# DR Drills and Post-Incident Reviews

## 1. Lesson Objectives

**Disaster Recovery (DR)** is the capability to restore services and data to an acceptable level after a severe disruption. A DR design is trustworthy only once the operations team has **drilled** it, measured outcomes, found gaps, and fixed them. Having backups, replicas, or a standby region does not prove the system recovers within business limits.

In the **Reliability and Disaster Recovery** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lesson ties together Azure components—subscriptions, resource groups, Microsoft Entra ID, virtual networks, VMs or app services, storage, databases, monitoring, security, and cost control—into one operational loop: **prepare → DR drill → collect evidence → post-incident review → remediate → re-drill**.

After this lesson, learners will be able to:

1. Distinguish DR drills from HA tests, backup tests, and live incident response.
2. Plan a drill with RTO/RPO targets, scope, safety preconditions, owners, and abort criteria.
3. Choose scenarios covering zone loss, region loss, data loss, or dependency loss; rehearse failover/failback suited to Azure services.
4. Capture timestamps and measure downtime, data loss, data integrity, and post-cutover serving capacity.
5. Write blameless post-incident reviews, analyze systemic causes, and track preventive actions through measurable re-tests.

**A drill's final outcome is not merely "we switched to standby"—it must prove users can complete critical transactions, data meets RPO, recovery time meets RTO, and operations can repeat the process.**

## 2. Distinguishing HA, DR, Backups, and Test Types

| Concept | Problem solved | How it is evaluated |
| --- | --- | --- |
| **High Availability (HA)** | Reduces disruption when an instance, node, or Availability Zone fails | Remove one replica/zone from rotation; verify automatic traffic shift |
| **Disaster Recovery (DR)** | Restores service after losing an environment, region, or critical dependency group | Cut over to standby environment; test data and business flows |
| **Backup & restore** | Recovers data state from an earlier timestamp or version | Restore copy into isolated environment; check consistency and usability |
| **Business Continuity (BC)** | Sustains business workflows and human operations during crises | Drill communications, manual fallbacks, service prioritization, and decision chains |
| **Incident response** | Detects, contains, and mitigates an active outage | Test alerts, role assignments, comms, and decision procedures |
| **Post-incident review** | Learns from events to lower likelihood/impact of future failures | Analyze timelines, systemic factors, corrective actions, and re-tests |

A system can **run multi-AZ inside one region** and still lack DR if the entire region goes dark. Conversely, an off-site backup helps restore data yet does not ensure APIs, DNS, identities, permissions, and networking spin up in time.

Every drill must state **which layer** it tests: shutting down one VM and watching the load balancer shift traffic does not prove region-level DR.

### 2.1. Drill Maturity Levels

| Level | Activity | What it proves | Limitations |
| --- | --- | --- | --- |
| **Tabletop** | Team walks through a paper scenario, discussing decisions and runbooks | Roles, dependency maps, steps, and unclear areas | Does not prove technical systems recover |
| **Component restore** | Restore a database, VM, or files from backup into a test target | Backups are readable and restore workflows work | Does not prove end-to-end business flows |
| **Isolated test failover** | Spin up DR copy on an isolated network; test apps and data | Workloads can boot in the standby environment | Does not prove real traffic cutover |
| **Controlled switchover** | Shift synthetic or controlled traffic to DR | Entry points, identities, dependencies, and end-to-end ops | Requires change control, rollback, and write controls |
| **Full exercise** | Test end-to-end from detection through recovery and return to steady state | Real RTO/RPO, organizational readiness, and operational capability | Higher cost/risk; requires strict scoping |

Progress gradually across maturity tiers over time. Never substitute a tabletop exercise for measuring RTO in a complete failover.

## 3. Turning Business Requirements into Measurable Targets

Before drafting a runbook, pick **priority business transactions** and agree on what counts as recovered. For example, an `orders` system has two flows: customers placing orders and admins viewing placed orders.

### 3.1. SLI/SLO, RTO, RPO, MTTD, and MTTR

| Metric | Meaning | How measured in drills |
| --- | --- | --- |
| **SLI** | Service Level Indicator, e.g., order success rate, p95 latency | External synthetic probes plus real transaction telemetry |
| **SLO** | Target for an SLI over a time window | Compare observed results against agreed thresholds |
| **RTO** (*Recovery Time Objective*) | Maximum allowed time from service disruption until acceptable recovery | `T_recovered - T_impact`, per defined recovery criteria |
| **RPO** (*Recovery Point Objective*) | Maximum tolerable data loss upon recovery | Compare pre-fault acknowledged data against surviving data post-failover/restore |
| **MTTD** (*Mean Time To Detect*) | Average time from user impact until detection | Tracked across incidents/drills, not inferred from one run |
| **MTTR** (*Mean Time To Recover/Repair*) | Average time to restore/repair per organizational definition | Tracked across incidents using consistent start/end milestones |

**Hypothetical business-chosen example** (not an Azure SLA or guarantee):

- Target RTO for order placement: **30 minutes**.
- Target RPO for confirmed orders: **5 minutes**.
- Post-recovery, order transaction success rate must stay at least **99%** over a 10-minute window, with p95 latency under **2 seconds**.
- Target initial notification to coordinators and stakeholders: **within 5 minutes** of detection.

For financial-grade orders, a 5-minute RPO may be **unacceptable**. Business owners must define exact preservation rules and whether reconciliation, compensation, replay, or idempotency mechanisms apply.

### 3.2. Measuring RTO/RPO Without Misleading Conclusions

Define milestones:

~~~text
T_impact     = 10:00:00   Users begin failing to place orders
T_detected   = 10:02:10   Alert / staff detects issue
T_declared   = 10:04:00   Incident Commander declares DR execution
T_failover   = 10:17:00   Routing cutover / traffic drain finishes
T_recovered  = 10:22:30   Transactions meet predefined SLI/SLO
~~~

**Measured RTO** = 22 minutes 30 seconds, from `T_impact` to `T_recovered`. Starting at `T_declared` hides detection and decision delays, making reports look rosier than reality.

**RPO is not measured by downtime duration.** Prove it with data:

- `last_acknowledged_write`: last write reported successful to a user before the fault.
- `last_recoverable_write`: newest valid record present in the recovered environment.
- Unique-ID test events to check **missing, duplicate, out-of-order, and orphaned records**.

If a fault strikes at 10:00:00, the last confirmed write was at 09:59:50, and the recovered copy only reaches 09:57:00, the potential data-loss window is roughly **2 minutes 50 seconds** to the recovery point—while record-by-record reconciliation reveals exact losses. Timestamps alone are approximate when clocks skew, writes are async, or data arrives out of order. Always verify with transaction IDs and commit states.

### 3.3. Multi-Dimensional Success Criteria

A drill fails if the API returns HTTP 200 yet cannot read orders, send notifications, or process queues. Define criteria across:

1. **Availability:** which user journeys work, and at what SLIs?
2. **Data integrity:** are acknowledged records complete, free of duplicates, with valid keys and relations?
3. **Security:** do RBAC, Managed Identities, Key Vault, TLS, and audit logs hold true in DR?
4. **Operations:** do dashboards, alerts, logs, on-call staff, and support workflows cover the DR environment?
5. **Performance/capacity:** does standby handle expected load and post-failover backlogs?
6. **Cost:** do recovery, replication, data transfer, and temporary DR resources fit budget?

## 4. Inventorying the System and Mapping Dependencies

In Azure, real service DR spans multiple subscriptions/resource groups and supporting services. Example architecture:

~~~mermaid
flowchart TB
    C["Client / mobile / web"] --> DNS["DNS / Front Door / ingress"]
    DNS --> API["Primary region API"]
    API --> DB["Primary database"]
    API --> Q["Queue / broker"]
    Q --> W["Worker"]
    W --> ST["Blob Storage"]
    API --> ID["Entra ID / Managed Identity"]
    API --> KV["Key Vault"]
    API --> NET["VNet / Private DNS / Private Endpoint"]
    M["Azure Monitor / Log Analytics"] -.-> API
    M -.-> DB
    M -.-> Q
    DAPI["Standby region API"] --> DDB["Standby region data"]
    DNS -. "Steer on failover" .-> DAPI
    DB -. "Replication / backup per config" .-> DDB
~~~

Dashed arrows show **designed capabilities** that must be configured and verified, not automatic replication across all Azure services. For example, an app might boot in the standby region yet fail to reach Key Vault, DNS, or the database's Private Endpoint.

Build a fillable inventory table:

| Component | Owner | Primary / DR | Recovery method | Evidence to collect |
| --- | --- | --- | --- | --- |
| Frontend / ingress | Platform team | Addresses, routes, DNS configured in both envs | Switch routes/priority to healthy region | Updated route, external probes |
| Compute / API | App team | Replicas or pre-built deployment in DR | Scale/boot from IaC and controlled images | Deployment hash, readiness, SLIs |
| Database | Data team | Replica/failover group or matching backups | Promote/failover or restore | Transaction IDs, point-in-time, RPO |
| Blob / storage | Data team | Redundancy matching requirements | Read replica / restore copy | Object checksums, accessibility |
| Queue / worker | App team | DR broker or drain/replay plan | Switch consumers, reprocess | Message IDs, duplicates, backlog |
| VNet / DNS / Private Endpoint | Network team | Configured in both sites | Controlled route/endpoint switch | DNS resolution, TLS connections |
| Identity / Key Vault | Security team | Identities, roles, secrets, and keys with DR plan | Restore access with least privilege | RBAC, secret access, audits |
| Monitoring | SRE team | Dashboards/alerts for both primary and DR | Detect and confirm state | Timeline, alerts, synthetic probes |

**Check dependencies in both directions:** after failover, a worker in DR might send messages to a broker existing only in primary, creating a hidden backward dependency on the failed region. Also verify quotas, SKUs, VM allocation capacity, and service limits in the standby region.

## 5. Choosing Meaningful Drill Scenarios

Not every fault warrants a full-region failover. Classify **scope and impact** before picking actions.

| Scenario | Safe injection / simulation | Expected action | What to measure |
| --- | --- | --- | --- |
| **Single-instance fault** | Drain/remove one test backend | Load balancer shifts requests to other backends | Error rate, backend eviction time |
| **Single-AZ outage** | Isolate one zone's backends in test env | Remaining zones carry load; stateful tier stays up | N-1 capacity, latency, quorum |
| **Primary region loss** | Tabletop or controlled failover to DR | Restore ingress, API, data, and dependencies in DR | RTO/RPO, DNS, queue state, transactions |
| **DB loss / bad write** | Use test dataset and known backup point | Restore exact point-in-time, reconcile data | RPO, restore duration, integrity |
| **Network / Private DNS fault** | Adjust policy/network in isolated env | Pinpoint cause, restore paths without exposing service | Reachability, TLS, alerts |
| **Auth / permission failure** | Simulate missing RBAC with a test identity | Remediation preserves least privilege | Detection time, audit, recovery |
| **Bad release / global config** | Deploy rollback-ready faulty build in staging | Halt rollout, roll back, or restore config | Detection, recovery time, recurrence prevention |

Distinguish **fault injection** (controlled fault simulation), **test failover** (instantiating a test environment from replication), and **real failover** (cutting over live service). Never treat the three as carrying equal risk.

Include at least one **happy path** and one **negative path**—for example, failover runs yet a secret is missing in DR, or DR boots yet queue backlog spikes. Negative paths uncover unmodeled gaps.

## 6. Drill Planning: Entry Gates, Roles, and Stop Mechanisms

Before drill day, turn the plan into an auditable document instead of merely saying "let's test failover this weekend."

### 6.1. Exercise Charter Template

~~~yaml
exercise_id: dr-orders-2026-11
system: orders
environment: staging-isolated
scenario: primary-region-unavailable
objectives:
  rto_minutes: 30
  rpo_minutes: 5
  essential_journeys:
    - create-order
    - read-order
    - process-order-event
scope:
  includes:
    - application
    - database
    - private-network
    - ingress
    - monitoring
  excludes:
    - production-payment-provider
roles:
  incident_commander: "Role: SRE lead"
  exercise_controller: "Role: test coordinator"
  application_owner: "Role: app lead"
  data_owner: "Role: DBA / data engineer"
  observer: "Role: timeline scribe"
controls:
  data: synthetic-only
  outbound_notifications: disabled
  test_network: isolated
  stop_if: "Real production traffic appears or out-of-scope production impact"
evidence:
  - timeline-utc
  - synthetic-transactions
  - monitoring-query-results
  - database-reconciliation
  - failover-operation-logs
~~~

This is a **planning template**, not an Azure-executable config. Replace placeholders with your actual environments, owners, criteria, and schedules.

### 6.2. Roles to Separate

- **Incident Commander (IC):** sets priorities, switches states, delegates tasks, and communicates within approved bounds.
- **Exercise Controller:** orchestrates the scenario and fault injection, enforces test limits, and holds authority to halt the drill.
- **Technical Leads:** app, data, network, and platform leads executing and verifying steps in their domains.
- **Observer/Scribe:** logs timestamps, outcomes, evidence, assumptions, and actions; avoids jumping into fixes unless assigned.
- **Business representative:** confirms critical journeys recovered and approves acceptable degradation levels.
- **Communications owner:** posts status updates to stakeholders; clearly marks all messages as drill communications.

In small teams, one person may wear multiple hats, yet **decision authority** and **evidence recording** must remain explicitly assigned.

### 6.3. Go / No-Go Criteria

Start only after confirming: isolated test environment; backups/replicas present and fresh; authorized approval of scope; budgets/quotas set on paid or temporary resources; clear rollback/cleanup path; working dashboards and synthetic transactions; and test data incapable of triggering real payments, emails, or webhooks.

Example **stop conditions**: production customer requests hit the test environment, observability is lost, replication behaves anomalously, or actions drift beyond approved scope. In that event, the controller halts injection, freezes changes, and reassesses—never chase RTO at the cost of safety.

## 7. Chronological DR Drill Workflow

A complete drill progresses through these stages:

~~~mermaid
flowchart LR
    P["Prepare & baseline"] --> F["Inject fault scenario"]
    F --> D["Detect & confirm"]
    D --> A["Decide DR cutover"]
    A --> O["Failover / Restore"]
    O --> V["End-to-end & data tests"]
    V --> S["Stabilize & monitor"]
    S --> B["Controlled failback / cleanup"]
    B --> R["Post-incident review"]
    R --> X["Corrective actions & re-drill"]
~~~

### Stage A — Pre-Fault Baseline

Before injection, record the healthy system:

1. Snapshot architecture diagrams and deployed versions (commits/image tags or artifact IDs).
2. Confirm resource groups, subscriptions, regions, SKUs/tiers, quotas, identities, and DNS/ingress targets.
3. Capture baseline metrics: RPS, success rate, p95 latency, queue depth, replication health/lag, and last successful backup.
4. Generate **synthetic transactions** with unique IDs reconcilable across primary and DR.
5. Verify dashboards, alerts, on-call roster, and comms channels; standardize logs to UTC.

### Stage B — Controlled Incident Activation

The Exercise Controller triggers the approved scenario—for instance, taking the test environment's primary endpoint offline to simulate region loss. Log exact `T_impact`. For replication test failovers, stand up an isolated test zone rather than cutting production traffic.

Observe whether alerts flow cleanly through **alert → on-call → acknowledgment → decision**; observers record without intervening unless a stop condition hits.

### Stage C — Recovery Decision and Execution

The IC confirms blast radius and states the data strategy and exposure: "fail over to DR replica within RPO budget" or "restore latest backup and reconcile missing transactions." Technical leads execute **service-specific** runbooks—never a generic "fail over all of Azure" command.

Actions may include: starting DR workloads, promoting database roles per service procedures, configuring ingress, and verifying DNS/Private DNS, certificates, Managed Identities, network rules, and outbound access. If primary might still accept writes, resolve **split-brain** and dual-writer risks before opening DR transactions.

### Stage D — User-Perspective Verification

Never stop at a control-plane "failover succeeded" message. Re-run synthetic journeys:

- Submit an order with an idempotency key and receive the same transaction ID on retry.
- Read the newly created order from the public endpoint / expected access path.
- Confirm workers process the emitted message once in business effect even if the broker redelivers.
- Retrieve required blobs/objects and verify checksums or version IDs.
- Verify sign-in, secret retrieval, DNS resolution, TLS, and auditing.
- Test under design load and watch DR capacity.

Record `T_recovered` **when acceptance criteria hold steadily** across the defined window—not merely when the final technical command finishes.

### Stage E — Stabilization, Failback, and Cleanup

Depending on the scenario, DR may stay active or fail back once primary heals. **Failback is its own high-risk change**: resync data, designate the authoritative source, fence unauthorized concurrent writers, validate networking and data, cut over controllably, and then return primary to service.

For isolated test failovers, **clean up** test VMs/networks/resources per service procedure and confirm source replication remains intact. Never leave billable test resources or accidentally exposed endpoints behind.

## 8. Applying Azure Tools by DR Pattern

Each service has its own limits and workflow. The guidance below helps **choose drill methods**, not prescribe universal commands across every account.

### 8.1. Azure Site Recovery (ASR) for Supported Workloads

**Azure Site Recovery** replicates and orchestrates recovery for supported VMs/workloads. Using **test failover**, ASR boots recovered test VMs, typically inside an **isolated test network**.

Operational flow:

1. Verify replication health, policy, recovery points, workload compatibility, permissions, and test network.
2. Select the protected item or recovery plan in the Recovery Services vault and run **Test failover** from the chosen recovery point.
3. Access the recovered VM via the test network; verify OS, services, apps, DNS, test data connectivity, and synthetic transactions.
4. Log timings, results, boot issues, config gaps, and manual steps.
5. Run **Cleanup test failover** per ASR workflow, confirming test resources are removed and source replication stays healthy.

**Test failover is not production failover.** Live failover commits, reprotect, and failback vary by source/target type; follow the workload's updated runbook. Never run an unplanned failover just to test when test failover serves the goal.

For multi-VM apps with dependencies, review recovery plans, boot sequencing, automation scripts, and when databases/queues actually become ready; a "Running" VM does not mean the app has recovered.

### 8.2. Azure Backup and Data Recovery

A **restore** drill must prove backups are readable, keys/permissions allow recovery, data is valid, and restore speed fits RTO. For example:

- Pick a recovery point with verified timestamp and retention.
- Restore into a dedicated **test resource group or target** where supported.
- Keep permissions/networking isolated and ensure zero production impact.
- Run schema, row-count, foreign-key/checksum, and application transaction checks.
- Record gaps between the recovery point and acknowledged writes, then run reconciliation/replay if supported by design.

Never mark "RPO met" just because a backup job shows `Succeeded`: inspect **usable recovery points** and restored data contents. Backups recover accidental deletes and corruption even when a DR replica already replicated the bad change.

### 8.3. Azure SQL and Failover-Capable Data Services

When using **Azure SQL Database failover groups** or geo-replication/HA features, check:

- Exact primary/secondary roles, lag, and replication health before testing.
- App usage of proper listeners/endpoints; DNS caching and connection pooling affect switchover speed.
- Data-loss impact of **forced/unplanned failover** under async replication; never promise RPO=0 for cross-region async replication.
- App reconnection latency, idempotency, and indeterminate in-flight transactions.
- Failback mechanics, data written while in DR, and resynchronization order.

Practice role switches in a **test environment** following service procedures and authorized permissions. Control-plane failover success means nothing if apps still point to the old endpoint.

### 8.4. Azure Storage and Redundancy Choices

Azure Storage offers **LRS, ZRS, GRS, GZRS**, and read-access secondary variants depending on account type and region. Geo-replication, secondary reads, and **account failover** are separate concepts.

Before any storage failover drill, verify:

- Whether the current SKU supports the planned action.
- Async replication to the secondary region can lag; primary-acknowledged writes may be absent on secondary.
- Account failover alters replication posture, billing, or configuration—never treat it as a harmless, instantly reversible test button.
- Whether apps use queue, table, file, or blob APIs with specific limitations.

For recovery testing, prefer **supported secondary reads or restoring into test resources** before considering actions that alter production accounts.

### 8.5. Networking, Traffic Steering, and Identity

Routing layers like **Azure Front Door**, DNS, load balancers, Application Gateway, and VNet/Private Endpoint setups play distinct roles. Pick the right architecture component and verify health probes, origin priorities, and routing policies. DNS TTLs never guarantee every client switches simultaneously due to caching, persistent connections, and varied resolvers.

For cross-region DR, verify NSGs, routes, NAT/outbound dependencies, Private DNS Zone links, certificates, service endpoints, and connection limits. Test Managed Identities, RBAC, Azure Key Vault, and data permissions in the standby region/scope—never copy secrets manually into logs or reports.

### 8.6. Confirming Azure Scope Before Drilling

Read-only Azure CLI commands help gather pre- and post-drill evidence safely:

~~~bash
# Verify the active CLI session's subscription and tenant.
az account show \
  --query "{subscription:id, tenant:tenantId}" \
  -o json

# Inventory resources in the test resource group.
az resource list \
  --resource-group rg-orders-dr-test \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# Inspect configuration of a known resource ID.
az resource show \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-orders-dr-test/providers/<provider>/<type>/<resource-name>" \
  -o json
~~~

`<...>` symbols are placeholders to replace with real resource IDs. These commands do not trigger failovers. Live failover steps may require specific Azure Portal actions, APIs, or service CLI extensions; verify exact syntax and permissions beforehand.

## 9. Collecting Evidence: Metrics, Logs, Timelines, and Data

To run a solid post-incident review, **define the evidence package before the drill**. During execution, the scribe logs UTC timestamps, operators, actions, outcomes, and links to logs/traces. Preserve enough detail to verify conclusions while keeping secrets, tokens, PII, and sensitive data out of reports.

### 9.1. Application Insights via Log Analytics Query Examples

For apps sending request telemetry to a workspace with `AppRequests`, inspect per-minute failure rates:

~~~kusto
AppRequests
| where TimeGenerated between (datetime(2026-11-20T09:55:00Z) .. datetime(2026-11-20T10:45:00Z))
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
    by bin(TimeGenerated, 1m), AppRoleName
| extend FailureRatePercent = iff(Requests == 0, real(null), 100.0 * Failures / Requests)
| order by TimeGenerated asc
~~~

This is a sample query for the `AppRequests` schema; table/column names, sampling, and actual data vary by Application Insights setup. `ItemCount` estimates counts under sampling, yet results must still be cross-checked against synthetic tests and business events.

To inspect p95 latency:

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = count(),
    P95LatencyMs = percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m), AppRoleName
| order by TimeGenerated asc
~~~

Latency queries use captured telemetry events; when sampling is on, note representativeness limits. Never rely on low CPU or one HTTP 200 probe to declare business recovery.

### 9.2. What Belongs in a Timeline File?

| UTC | Evidence source | Event | Impact | Scribe / operator |
| --- | --- | --- | --- | --- |
| 10:00:00 | Synthetic order probe | Timeouts begin | Order success rate drops | Observer |
| 10:02:10 | Azure Monitor alert | Alert fired | On-call paged | SRE |
| 10:04:00 | Bridge log | IC triggers DR runbook | Recovery begins | IC |
| 10:11:00 | Database event | DR DB assumes writer role | State validation can start | DBA |
| 10:17:00 | Ingress metrics | Traffic shifts to DR | Entry path switched | Platform |
| 10:22:30 | Synthetic + SLI | Targets met within acceptance window | Service declared recovered | Business owner |

Timestamps are **illustrative figures**. If telemetry is missing or clocks disagree, record uncertainty ranges instead of inventing false precision.

### 9.3. Sample Order Data Reconciliation

Before the drill, generate synthetic orders with unique `exercise_id` and `order_id` values, recording commit states and timestamps in an independent evidence store. After failover:

~~~text
Expected:
  order-A: ACKNOWLEDGED, amount=100, checksum=X1
  order-B: ACKNOWLEDGED, amount=200, checksum=X2
  order-C: PENDING,      amount=300, checksum=X3

Recovered:
  order-A: PRESENT, amount=100, checksum=X1
  order-B: PRESENT, amount=200, checksum=X2
  order-C: MISSING
~~~

If `order-C` was never confirmed to the user, business logic can retry or cancel it cleanly. If `order-B` was acknowledged yet went missing, that is **confirmed data loss**—report and reconcile it even if timestamp-based RPO looked acceptable.

Also check duplicate orders, outbox/inbox messages, sequences, idempotency keys, audit logs, and downstream states. **Data integrity is an independent criterion** and cannot be inferred from replication lag alone.

## 10. Scoring and Reporting Drill Outcomes

Suppose a test-environment drill reports these numbers:

| Measurement | Target | Actual observed | Verdict |
| --- | --- | --- | --- |
| **RTO** | ≤ 30 minutes | 22 minutes 30 seconds | Passed on timing |
| **RPO** | ≤ 5 minutes | Recovery point lagged 2 min 50 sec; records reconciled | Passed timing; data still checked |
| **Order placement success** | ≥ 99% in recovery window | 99.5% over 10 minutes | Passed |
| **p95 latency** | < 2 seconds | 1.8 seconds | Passed |
| **Confirmed orders lost** | 0 per business target | 1 order missing post-reconciliation | **Failed** |
| **Stakeholder notification** | ≤ 5 minutes after detection | 7 minutes | **Failed** |
| **Cleanup** | Zero out-of-scope test resources left | One test NIC/VM left behind | **Failed** |

**Never mark an entire drill "PASS" merely because RTO/RPO met timing targets.** The example above lost a confirmed order, lagged on notifications, and left cleanup incomplete. Overall scoring should report **PARTIAL/FAILED per pre-agreed acceptance criteria**, breaking down each pass and fail item.

Key points to highlight in the conclusion:

- **Redundancy in action:** what percentage of journeys ran in DR, and for how long?
- **Repeatability:** did any step rely on tribal memory, temporary permissions, or manual tweaks?
- **Measurement limits:** metric sampling, missing traces, clock skew, or test load below real peak?
- **Indirect impacts:** queue backlogs, duplicate messages, lost permissions, lag, throughput, or cost?
- **Return to steady state:** after failback/cleanup, did primary and secondary return to desired posture?

## 11. Post-Incident Review: Evaluating to Improve the System

A **post-incident review** (or postmortem) drives learning after both **real incidents** and **drills**. Its goal is understanding how the system behaved, which conditions worsened impact, how well detection and response worked, and what must change.

Take a **blameless** approach: examine technical conditions, processes, and information available at decision time. This does not remove ownership accountability; it surfaces fixable systemic causes without encouraging teams to hide data.

### 11.1. Structure of an Actionable Report

~~~markdown
# DR Exercise / Incident Review: <incident-id>

**Date/Time (UTC):** ...
**Environment, subscription, region:** ...
**Impact level and incident type:** ...
**Incident Commander / Exercise Controller:** ...
**Affected services and journeys:** ...

## Overview
- What user impact occurred, and over what timeframe?
- How did the system recover?
- How did results compare to RTO, RPO, and SLO targets?

## Timeline
| UTC | Event | Evidence | Decision / action |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## What Worked Well
- ...

## What Did Not Work or Remains Unknown
- ...

## Root Cause and Contributing Factors
- Trigger: ...
- Pre-existing conditions: ...
- Failed dependencies: ...
- Why alerts/runbooks did not detect or resolve sooner: ...

## Data and Security Impact
- Acknowledged transactions, indeterminate transactions, data needing reconciliation: ...
- Permissions, audits, logs, and exceptions: ...

## Follow-Up Actions
| ID | Action | Owner | Deadline | Acceptance evidence |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

## Re-Test Conditions
- ...
~~~

The snippet above is a **document template**, not a requirement to create separate files for every lesson. In practice, store reviews in your organization's incident system linked to queries, dashboards, logs, and code changes.

### 11.2. Tracing Root Causes and Contributing Factors

Avoid vague conclusions like "database failed" or "engineer was slow." Ask sequentially down the causal chain:

**Symptom:** After cutover, the DR API returned 5xx for 7 minutes.

**Why?** The API could not open database connections over private DNS.

**Why?** The DR VNet lacked a link to the Private DNS Zone serving the DR endpoint.

**Why?** DR environment IaC omitted that link, and validation checks only verified VMs and the DB were running.

**Why wasn't it caught earlier?** Readiness probes checked only process liveness with no synthetic transactions in DR, and the runbook did not require testing DNS from the workload.

This yields concrete actions:

1. Add the DR VNet Private DNS Zone link to IaC with peer review and controlled deployment.
2. Add a synthetic test validating DNS → TLS → database → order transaction from DR.
3. Add a "connectivity and permissions verified" gate before ingress cutover.
4. Re-drill with an intentionally misconfigured dependency to test alerts and troubleshooting steps.

**Not every failure has one single "root cause."** Multiple contributing conditions often align; state confidence levels, open hypotheses, and missing data clearly.

## 12. Corrective Actions: Turning Findings into Verifiable Changes

An effective action item specifies **owner, deadline, change scope, and completion criteria**. Avoid vague items like "improve monitoring" or "train staff" without stating how risk drops.

| Finding | Concrete action | Closure evidence |
| --- | --- | --- |
| DR VNet missing Private DNS link | Add IaC resource with pre-release validation | Pipeline checks link; synthetic test via DR passes |
| RTO stretched by DR VM provisioning | Keep warm capacity or reservation/quota plan | N-1 or regional failover drill meets RTO at target load |
| Backup job green yet restore failed | Schedule isolated restores and data validation | Automated restore report and checksum reconciliation |
| RPO unmeasurable | Log synthetic write IDs and ack timestamps externally | Last-ack vs. last-recoverable reconciliation report |
| Alert took 10 minutes to detect | Add end-to-end SLI alert routed to on-call | Next drill measures MTTD within target |
| Failback caused duplicate processing | Implement idempotency/outbox and fence writer pre-cutback | Replay/duplicate test yields zero duplicate orders or charges |
| Test resources left behind | Add cleanup checklist and inventory by `exercise_id` tag | Post-test inventory empty for teardown scope; costs reconciled |

Prioritize action items by risk (e.g., **P0: risks confirmed data loss; P1: increases RTO; P2: reduces operational visibility**). Priorities and SLAs belong to the organization, yet every serious finding needs an owner until verified fixed.

### 12.1. What Does Closing an Action Item Mean?

Merging a Pull Request or marking a ticket Done **is not enough**. Require evidence that system behavior changed under relevant conditions: IaC/deployment tests, new health probes, successful restores, synthetic checks, or a re-drill result. Where residual risk stays due to service limits or cost, record explicit **risk acceptance** with an approver and review date.

## 13. Common Mistakes in Drills and Reviews

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Checking only that resources are "Running" | Users still fail on DNS, auth, or DB | Test business journeys outside-in |
| Starting RTO clock when IC declares failover | Hides detection and decision delays | Start clock when service impact begins |
| Treating backup job success as RPO proof | Backup may be unreadable or stale | Restore, read data, and reconcile transactions |
| Treating test failover and production failover as identical | Misjudges risk and real readiness | Document test tier and evidence limits |
| Recovering only one VM of a multi-tier app | Queues, DNS, identities, or data missed | Inventory dependencies and test end to end |
| Running forced failover on async replicas without accepting data risk | Loses unreplicated writes | Inspect recovery points, lag, reconcile, and align with RPO |
| Lacking stop conditions | Test disruption leaks to production or live data | Isolated networks, synthetic data, scoped RBAC, stop triggers |
| Stopping evaluation once ingress switches | Unknown transaction, backlog, or data correctness | Watch full SLO window, data integrity, and monitoring |
| Writing postmortems to blame individuals | Hides systemic flaws and discourages transparency | Analyze timelines, dependencies, and contributing factors |
| Closing tickets without re-drilling | Unverified whether fixes actually work | Attach acceptance criteria and re-test |

A single change can both shorten RTO and raise cost, or shrink RPO while adding write latency. Base decisions on **business targets and test measurements**, not blindly maximizing redundancy.

## 14. Capstone Exercise: Game Day for an Ordering Application

**Assumed context:** The `orders` system runs in a primary Azure region with APIs, workers, database, blob storage, Key Vault, and private networking. A DR setup exists in a second region with ingress traffic steering. Targets: **RTO ≤ 30 minutes**, **RPO ≤ 5 minutes** for tolerated data-loss scope, and **zero lost confirmed transactions** in business flows requiring strict reconciliation.

### Task A — Draft Charter and Baseline

Complete the Section 4 dependency inventory and Section 6 charter template. Assign app/data/network owners; list service/tier, region, replication lag, backup recovery points, and baseline SLIs. Generate 30 synthetic orders with unique IDs and store ack records independently for later reconciliation.

### Task B — Execute Isolated Test Failover

Use **test failover or restore testing** suited to the deployed services. Never run changes against primary production. Trace every event from injection until DR serves transactions, logging UTC timestamps and evidence links. If errors occur, preserve logs/traces and follow approved stop conditions.

### Task C — Measure Results

Compute `T_recovered - T_impact` and reconcile transaction IDs and pre/post data states. Measure success rate and p95 latency across the recovery window. Verify Key Vault access, Private DNS, message consumption, worker backlogs, and load handling. Sum total cost of created test resources.

### Task D — Failback / Cleanup and Review

Revert or clean up per test type and verify source replication stays healthy. Write a review with timeline, targets vs. actuals, at least three contributing factors, and action items with owners, deadlines, and re-test evidence. Any unconfirmed cause must be labeled **unknown**, never guessed.

### Submission Summary Table

| Item | Required evidence |
| --- | --- |
| Scope and safety controls | Primary/DR, test data, isolation, stop conditions |
| Test evidence | UTC timeline, logs, dashboards, deployed versions |
| Metrics | Actual impact, MTTD, RTO, RPO, SLIs, throughput |
| Integrity | Present/missing/duplicate IDs, checksums, reconciliation actions |
| Operations | Decisions, roles, comms, manual steps, discovered errors |
| Failback / cleanup | Source system verified, replication healthy, temp resources and costs |
| Lessons learned | Causes/contributing factors, owners, deadlines, re-drill schedule |

**Pass criteria:** Learners can explain what was tested, provide evidence proving or disproving RTO/RPO, verify critical transactions stayed accurate, state residual risks clearly, and turn findings into re-tested corrective actions.

## 15. Embedding DR Drills into Long-Term Operations

Effective DR is a **repeatable lifecycle** tied to architectural changes—not a one-time event filed away in a binder. Triggers for review and re-drilling include: changing DB tiers/SKUs, migrating regions, modifying ingress or DNS, adding queues/workers, changing auth, altering IaC, moving subscriptions, switching backup/replication settings, and updating runbooks.

Set a **test cadence matched to system criticality** and organizational needs, rotating failure classes each cycle. Track trends in RTO/RPO, manual step counts, cleanup errors, and overdue action items. For every budget trade-off, weigh warm standby, backup retention, replication traffic, and DR drills against the business cost of downtime.

IaC and CI/CD pipelines keep primary and DR aligned on paper, yet only drills uncover hidden drift in permissions, networking, quotas, and state. Feed drill measurements back into runbooks, monitoring, capacity plans, and risk registers.

## 16. Summary

A strong DR drill answers four evidence-backed questions:

1. **What failed?** Scope, blast radius, and affected dependencies.
2. **How did service recover?** Procedures, decision-makers, timelines, and verified business readiness.
3. **Are data and security intact?** Recovery points, transaction reconciliation, permissions, and post-failover checks.
4. **How will the system improve?** Changes with owners, deadlines, completion gates, and the next verification drill.

In Azure, measure from the user's perspective, reconcile real data, verify services and configurations for the exact SKU/region, and use **post-incident reviews** to turn faults into lasting improvements. Disaster recovery holds value only when proven by a working system and a runbook clear enough to execute under pressure.
