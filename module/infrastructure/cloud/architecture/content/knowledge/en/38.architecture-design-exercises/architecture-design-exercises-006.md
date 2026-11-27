# Planning Recovery and Running Regional Outage Drills

## 1. Context and Objectives

When a server or an Availability Zone (AZ) fails, an application can stay online using multiple replicas and intra-region failover. However, when an **entire region** becomes unavailable, load balancers, compute, databases, queues, and endpoints confined to that region can all stop serving. To recover, the architecture team must prepare a **standby region**, recoverable data, an independent coordination path, and a safe write-authority transfer procedure.

This exercise belongs to the **Design Exercises** chapter of the **CLOUD_ARCHITECTURE** module. Learners turn business requirements into networking, compute, data, and deployment plans; explain trade-offs across reliability, security, scalability, cost, and operations; and evaluate the solution in the spirit of **Well-Architected**.

By the end of this lesson, you must be able to:

1. Analyze the impact of a region outage per business journey.
2. Set **RTO**, **RPO**, acceptable functional degradation, and verification criteria.
3. Compare backup/restore, pilot light, warm standby, and active/active before choosing.
4. Design a two-region architecture covering replication, routing, single-writer control, IAM, backups, queues, and observability.
5. Write **failover** and **failback** runbooks along with GO/NO-GO gates.
6. Organize safe drills; measure RTO/RPO, reconcile data, and prove outcomes.
7. Document residual risks, owners, remediation deadlines, and architectural decisions.

> All numbers in this lesson are **assumptions for practice**, not SLA commitments from AWS, Azure, or Google Cloud. Before real implementation, verify limits, replication capabilities, quotas, regional availability, and pricing for the chosen services.

## 2. Running Case Study: A Task Management SaaS

An enterprise operates a SaaS application allowing users to sign in, create/edit tasks, attach files, track task boards, and receive notifications.

The current architecture lives solely in **region A**:

- DNS/CDN/WAF and HTTPS ingress route to stateless API applications running in containers.
- Managed PostgreSQL stores accounts, teams, tasks, update versions, and activity history.
- Object storage holds file attachments; Redis cache accelerates reads.
- Queues/workers send notifications, generate file previews, and update search indexes.
- IAM, KMS, secret manager, monitoring, audit logs, CI/CD, and declarative infrastructure.

Assumed scale: 300 requests/second normal, 1,200 requests/second peak; PostgreSQL 500 GB, object storage 6 TB. Region B is permitted to store standby data under company policy.

### Targets Assumed Agreed with the Business

| Business flow | Illustrative target | Scope |
| --- | --- | --- |
| Sign in, read/update tasks | **RTO ≤ 45 minutes** | From when A stops serving until core functions in B run and are verified |
| Task data | **RPO ≤ 5 minutes** | Maximum data-loss time window approved by the business, plus procedures to identify and handle affected changes |
| File attachments | Must have separately approved durability target | Object storage RPO cannot be inferred from PostgreSQL replication |
| Notifications, previews, search index | Allowed to recover slower than core API | Events do not cause duplicate side effects; backlog can replay |
| Rebuildable analytics data | RPO can be longer, e.g., 24 hours | Distinguish source-of-truth data from recomputed data |
| Privacy and security | Never lower protections in B | Comply with data residency, least privilege, encryption, and auditing |

**RPO ≤ 5 minutes does not mean "zero records lost."** If the business mandates that an acknowledged operation **must never be lost**, set an RPO matching that mandate and choose a provable write/replication mechanism rather than using async replication and assuming it is safe.

### Failure Domains

| Incident | Primary protection | Limitation |
| --- | --- | --- |
| Single VM/pod failure | Restarts, health checks, replicas | Does not handle database or zone failure |
| Single AZ failure | Multi-AZ, spread replicas, intra-region HA database | Insufficient if the entire region fails |
| Entire region A failure | Data/resources in B, routing, and DR runbook | Must protect write authority and unsynced data |
| Shared service between A and B fails | Reduce coupling, independent operational access, response plan | "Global" does not mean immune to failure modes |

## 3. Understanding and Measuring RTO/RPO Correctly

### 3.1. RTO: Time to Restore Useful Service

**Recovery Time Objective** is the target duration for a business flow to recover within a defined incident scope. Do not count only the DNS switch click, because the process includes detection, triage, blocking writes at the old source, promoting data, scaling capacity, shifting routing, and verification.

~~~text
Measured RTO = elapsed time from T0 (outage begins)
               to T7 (core flows in B PASS and open to users)
~~~

Illustrative budget for a 45-minute RTO:

| Step | Max duration | Cumulative |
| --- | ---: | ---: |
| Detect fault and verify impact | 5 minutes | T+05 |
| Incident commander decides to activate DR | 5 minutes | T+10 |
| Fence A, verify data state in B | 5 minutes | T+15 |
| Promote DB in B and scale compute | 12 minutes | T+27 |
| Shift routing and verify connectivity | 7 minutes | T+34 |
| Smoke tests and open core features | 8 minutes | T+42 |
| Delay buffer | 3 minutes | T+45 |

This table is a **coordination target**, not proven performance. If starting B takes 18 minutes instead of 12, fix the design or report RTO missed; never skip data verification just to beat the clock.

### 3.2. RPO: Maximum Age of Recovered Data State

**Recovery Point Objective** bounds data loss, typically expressed as a time window. **Asynchronous** replicas can lag behind: a transaction may commit in A without being durably applied in B before A vanishes.

Suppose A stops serving at **10:00:00** and B has consistently applied data up to **09:57:30**: the lag is **2 minutes 30 seconds**, within the 5-minute threshold if backed by evidence. Yet comparing two wall-clock timestamps **does not prove** every transaction before that mark was applied; inspect **log positions/transaction sequences**, apply state, and missing or failed transactions.

Document explicitly:

- Last **durably committed** position in A, if observable.
- Last **durably applied** position in B.
- Recovery point selected to open B and associated datasets.
- Set of operation IDs acknowledged to clients near the outage.
- Set of IDs/versions and files actually recovered in B.
- Discrepancies, remediation steps, and who is authorized to accept losses.

### 3.3. RTO, RPO, and SLA Do Not Substitute for One Another

A service recovering in 20 minutes may **meet RTO** yet **miss RPO** if 12 minutes of data are lost. Likewise, a DB that caught up on replication while the API still fails due to missing secrets or network rules has **missed RTO**. A single cloud service's SLA also does not automatically prove the SaaS's end-to-end SLO.

## 4. Selecting a DR Option and Explaining Trade-Offs

| Strategy | Region B before incident | Strengths | Risks / costs |
| --- | --- | --- | --- |
| **Backup and restore** | Backups and IaC ready; most apps idle | Low standby operating cost | Restoring large datasets can take long; RPO dictated by backup interval |
| **Pilot light** | Core data/minimal components live; compute boots or scales on failure | Cheaper compute than warm standby | Provisioning/scaling time can breach RTO |
| **Warm standby** | B runs continuously at reduced capacity with DB replica and testable endpoints | Faster switchover if scaling and replication keep pace | Pay for parallel runtime; must protect consistency/failback |
| **Active/active** | Both A and B serve normal traffic | Can reduce traffic-shift time | Hard to manage writer ownership, conflicts, latency, data relations, and cost |

**Reference choice for this lesson:** *warm standby in B*, because the business requires API recovery in 45 minutes and can fund running baseline compute/data in B. This choice is only valid once drills prove recovery timing, replication lag, scaling speed, and missing-data handling.

No strategy automatically guarantees RPO = 0 or sub-minute RTO. Even active/active can suffer **split-brain** if two independent databases accept writes concurrently.

## 5. Reference DR Architecture Diagram

~~~mermaid
flowchart TB
    U[Users and API clients] --> G[Global DNS / traffic manager / CDN]
    G -->|Normal| IA[Ingress A]
    G -. During DR .-> IB[Ingress B]
    subgraph A[Region A - primary]
      IA --> AA[API containers A]
      AA --> PA[(PostgreSQL primary)]
      AA --> OA[(Object storage A)]
      PA --> XA[(Transactional outbox)]
      XA --> QA[Queue / worker A]
    end
    subgraph B[Region B - warm standby]
      IB --> AB[API containers B]
      AB --> PB[(PostgreSQL standby)]
      AB --> OB[(Object storage B)]
      AB --> QB[Queue / worker B]
    end
    PA -->|Async log replication| PB
    OA -->|Cross-region object replication| OB
    XA -. Replay by checkpoint / ID .-> QB
    DR[DR control + observability independent of A] --> IB
    DR --> PB
    BK[Independent backup with tested restore] -. Restore if needed .-> PB
~~~

Arrows depict **logical roles**; actual product mechanics must be verified against the chosen vendor/cloud service. Outbox data in the diagram represents records typically written **in the same transaction and database as business data**, not a separate database by default.

### What Must Be Prepared in B?

| Component | Preparation | Mandatory verification |
| --- | --- | --- |
| DNS/traffic manager/ingress | Ingress in B, health checks, TLS, WAF, routes | Failover procedure, stale DNS/connection caching, origin reachability |
| Compute/containers | Compatible images/versions, autoscaling, quotas, IAM | Scale from standby to core load within time budget |
| PostgreSQL | Consistent standby, log replication, backups/PITR, DB permissions | Apply position, promotion, read/write, schema, RTO/RPO |
| Object storage | Replicas and lifecycles in B, encryption, metadata files | Checksums, DB links, read permissions, replication lag |
| Queue/events | Outbox, replay mechanism, DLQ, idempotency, worker B | Zero lost events, zero duplicate side effects |
| Cache/search | Rebuildable data, priority indexes | Cache warm-up, backpressure, rebuild duration |
| IAM/KMS/secrets | Valid workload identities and keys in B | Can authenticate and decrypt even with A unreachable |
| CI/CD, IaC, registry | Independent artifacts, state, pipelines, and operator permissions | Can scale/deploy B while A is down |
| Metrics/logs/audit | Dashboards and alerting independent of A | Observe from outside A; store evidence and communicate |

### Key Principle: A Single Authoritative Writer

At all times, **a given dataset has only one authoritative writer**. When failing over A → B, you must prove the old write path is blocked (**write fencing**) before opening B for writes, or enforce a leadership mechanism meeting the same safety invariant.

Changing DNS alone **does not stop** legacy app instances and workers still running. During a network partition, some clients may still hit A while others hit B. If two independent databases accept writes, state diverges.

Exact mechanisms vary by system: leader election with fencing tokens, data-tier write locks, verified leases, writer isolation via a healthy control plane, or database-native failover. If write exclusivity cannot be verified, the safe move is **keep writes closed in B**, log the incident, and escalate per response procedures.

## 6. Architectural Decisions to Record as ADRs

Before running drills, write **Architecture Decision Records (ADRs)** for:

1. **Choosing warm standby** over backup/restore, pilot light, or active/active, with RTO/RPO rationale and cost estimates.
2. **PostgreSQL replication:** asynchronous vs. synchronous, how lag is measured, and how recovery points are finalized.
3. **Fencing and promotion:** who is authorized to promote B, verification gates, and split-brain prevention when A is unreachable.
4. **Object handling:** when uploads report success; durability level, replication/checksum reconciliation.
5. **Queues and outbox:** events may be redelivered; consumers must be idempotent; who monitors the DLQ.
6. **DR traffic routing:** DNS TTL/health checks, clients holding stale connections, how routes to A are disabled.
7. **Operations and access:** break-glass IAM, KMS in B, auditing, secrets, and data residency impacts.
8. **Failback:** strategy to re-seed A from B or reverse-replicate—never auto-merge two diverged databases.

Each ADR must record at minimum context, options, decision, accepted risks, test evidence, and a review date.

## 7. Input Artifacts and Role Assignments

| Artifact | Minimum contents | Suggested owner |
| --- | --- | --- |
| **BIA (Business Impact Analysis)** | Business journeys, downtime impact, RTO/RPO, acceptable data loss | Business owner |
| **Dependency map** | Regional/global services, partners, write flows, queues, files, IAM | Architect |
| **DR diagram** | A/B, network topology, replication, backups, writer authority, trust boundaries | Architect/SRE |
| **Failover/failback runbook** | Steps, timeouts, gates, permissions, failure branches | SRE/DBA |
| **Test plan** | How to simulate region loss, seed data, metrics, rollback tests | QA/SRE |
| **Risk register** | Issues, severity, owners, deadlines, risk sign-offs | System owner |
| **Cost model** | Compute B, replication, egress, backups, logs, extended B operations | FinOps |

The **Incident Commander (IC)** leads the incident and authorizes switchover; the **DBA** verifies data checkpoints and write authority; **SRE/platform** handles routing/compute/monitoring; the **application lead** validates business flows/workers; the **security lead** enforces security and compliance; and the **business owner** decides acceptable data loss.

Never delegate data-loss acceptance solely to infrastructure operators when losses affect business commitments.

## 8. Pre-Activation GO/NO-GO Gates

| Gate | GO condition | NO-GO condition |
| --- | --- | --- |
| Scope | Participants, environment, tenants, and test window agreed | Risk of impacting out-of-scope data/users |
| Data | B has consistent replication/apply point; RPO calculation known | Lag unknown, apply errors, or missing audit logs |
| Single-writer | Rehearsed mechanism to fence A and promote B | Planning DNS flip only with active writers left running |
| Security | IAM, KMS, secrets, certificates, and data residency valid in B | Cannot decrypt, overly broad permissions, disallowed region |
| Capacity | B has quotas and scaling ability for critical flows | Insufficient capacity; DB connections untested at target load |
| Observability | Independent metrics, logs, alerts, and comms outside A | Cannot measure timing, data state, or service quality |
| Mistake recovery | Independent backup restore-tested; abort plan exists | No recovery plan if promotion/routing fails |
| Failback | Defined path to bring new B data back to A | Planning to point DNS back to A as soon as A "comes back" |

This table guides decision-making. In a real disaster, not every gate has complete telemetry; authorized decision makers must log **assumptions and risks** when proceeding. Data-safety gates must never be marked passed merely due to an absence of error signals.

## 9. Failover Runbook: A → B

### Phase A — Detection and Activation

1. Record **T0** when A stops serving per scenario. Use synthetic probes from B/outside A and independent dashboards to distinguish a region outage from one operator's local network drop.
2. Check status of business flows, dependencies, and likelihood of A recovering within remaining budget.
3. IC pages the right on-call teams, confirms authorization, and issues **GO DR / HOLD / NO-GO**; log timestamp T2 and rationale.

### Phase B — Verify Write Authority and Lock Data Checkpoint

4. Block or fence write paths into A across enforceable layers: API, DB, workers, schedulers, webhooks. If A is unreachable, use the pre-designed split-brain-safe failover protocol—never infer safety merely because A stops answering pings.
5. DBA locks **recovery point W** from durably applied log/transaction sequences in B. Record replication lag, apply errors, unarrived transactions, and checksums if available.
6. Check RPO per dataset; if breached, IC and business owner decide per policy. Never claim "met" when authoritative sources cannot be reconciled.

### Phase C — Promote Data and Services

7. Promote PostgreSQL B using the platform's supported procedure; verify schemas, sequences, app read/write, and permissions.
8. Scale compute in B; verify quotas, connection pools, autoscaling signals, app health checks, and downstream dependencies.
9. Start workers in B from the matching outbox/event checkpoint. Use idempotency keys and DLQ for retries/replays; never run two parallel schedulers producing duplicate side effects.
10. Verify object storage in B: checksums, metadata, task links, and decryption permissions. For un-replicated files, apply the business-approved recovery/hide/re-upload policy.

### Phase D — Shift Routing, Open Service, and Monitor

11. Switch traffic manager/ingress to B. Verify TLS, WAF, DNS caches, external reachability, and watch for lingering requests still hitting A.
12. Run synthetic transactions covering login, reading/editing tasks, test file upload/download, emitting events, and observing workers. Cross-check request IDs, DB state, and side effects; HTTP 200 alone does not prove transaction correctness.
13. Open live traffic progressively, watching error rates, p95/p99, DB saturation, queue backlog, and partner links. If capacity falls short, activate approved degraded modes.
14. IC confirms **T7**, computes RTO = T7 − T0, and records RPO evaluation, discrepancies, remaining degraded features, owners, and stakeholder communications.

### Illustrative Milestone Table

| Milestone | Primary owner | Evidence to save |
| --- | --- | --- |
| T+05 | SRE confirms region loss | External probes outside A, telemetry, incident opened |
| T+10 | IC activates DR | Decision log and approver |
| T+15 | DBA/SRE complete fencing, checkpoint W | Fencing state, replication/apply position |
| T+27 | DBA and platform ready B | DB writable, compute healthy, queue checks |
| T+34 | Network lead shifts ingress | DNS/TLS/route test outputs |
| T+42 | App lead finishes smoke tests | End-to-end results, test data, metrics |
| T+45 | IC signs off RTO assessment | Measured timeline, recovery status |

If smoke tests fail at T+42, **protect data integrity**, report RTO missed, and troubleshoot. Never open broken writes just to hit a number on a report.

## 10. Designing Regional Outage Drills

### 10.1. Drill Levels

| Level | Execution | Purpose |
| --- | --- | --- |
| **Tabletop** | Each role walks through questions and decision gates on paper | Finds gaps in procedures, permissions, and comms |
| **Component drill** | Test restore, DB promote, worker startup, route switch in test env | Validates individual technical steps |
| **End-to-end staging** | Simulate losing A in a two-region staging env; fail over to B | Validates full runbook sequence and real timings |
| **Scoped game day** | Drill on approved workload/tenants | Tests near-production conditions with bounded risk |
| **Full DR drill** | Broad regional cutover under an approved change plan | Measures real operational readiness including failback |

Start with tabletops and staging, then increase realism as evidence accumulates. Never take down a real production region without defined scope, data owners, schedule, and executive sign-off.

### 10.2. Seed Dataset

In staging, prepare:

- 10,000 tasks across multiple tenants, with **task ID** and **version** incrementing on every edit.
- 500 writes right around the failure point; clients track request IDs and acknowledged calls.
- 100 attached objects with independent checksums.
- 200 outbox events; seed a backlog to test replay and deduplication.
- Negative test requests: one tenant trying to read/modify another tenant's tasks.
- A load generator scaling from 300 to 1,200 requests/second and recording client-side latency/errors.

Do not use real sensitive data outside approved bounds. The dataset must represent realistic size, read/write mix, and data relationships to uncover recovery bugs.

### 10.3. Mandatory Test Scenarios

**Scenario 1 — Complete disappearance of A.** Sever routes to A's apps and services in staging. Operators fail over to B via the runbook; measure T0→T7, RPO, task/version sets, object checksums, access controls, and backlog.

**Scenario 2 — Network partition.** Some clients still reach A while the IC sees A unreachable. Goal: prove two simultaneous writers cannot exist. If fencing is uncertain, writes must **fail closed** rather than blindly opening B.

**Scenario 3 — Lag exceeds RPO.** Inject 7 minutes of replication lag right before the outage against a 5-minute RPO target. The right outcome is **RPO FAIL/NO-GO or a formal policy exception by the authorized owner**—never "round" 7 down to 5.

**Scenario 4 — Insufficient capacity in B.** Fail over to B with low standby compute and ramp load in steps. Measure scaling duration, connection pools, CPU/memory, IOPS, p95, error rate, and queue age. Verify degraded mode protects core flows.

**Scenario 5 — Replayed events.** Have publishers/consumers redeliver the same events post-failover. Verify no duplicate notifications occur thanks to event IDs, idempotency, DLQ, and processed state.

**Scenario 6 — KMS/secret failure in B.** Revoke one permission in staging to observe app behavior; verify alerts, runbooks, and remediation without relying on region A.

### 10.4. Drill Abort Criteria

Abort or narrow scope if concurrent writes are not prevented, sensitive files/data leak, out-of-scope environments are impacted, or observability goes blind. The facilitator logs the abort timestamp, preserves logs, and resumes only after fixing defects and obtaining re-approval.

## 11. Reconciling Data to Prove RPO

Do not just compare row counts between A and B. Two sets with identical counts can miss one task while holding an extra one, or share an ID with a stale version.

Lock comparison anchors:

- **W_A:** last known durable commit position in A (if still accessible).
- **W_B:** last durable apply position in B before promotion.
- **W:** chosen recovery point for restoration.
- **ACK set:** request IDs for which clients received success acknowledgments.
- **Recovered set:** tasks/versions, objects, and events actually present in B.

When A is unreachable, a reliable W_A may not exist. Reconcile the **ACK set**, logs outside A, and proven transaction checkpoints to bound what failed to reach B, explicitly stating uncertainty—never claim "zero data loss."

| Reconciliation layer | Check | Reason |
| --- | --- | --- |
| Keys | Are acknowledged task IDs present in B? | Detects missing/extra rows even when counts match |
| Contents | `version`, `owner`, `status`, updated fields | Detects stale or corrupted records |
| References | `task`–`project`–`tenant`–`attachment` | Prevents orphans or cross-tenant reads |
| Objects | Hash/checksum, size, decryption permissions | Metadata may reach B before the file payload |
| Events | IDs, outbox status, DLQ, side effects | Detects dropped or duplicated notifications |
| Aggregates | Counts by tenant/day/status | Quickly spotlights suspect data slices |

Example query on the same dataset at a consistent checkpoint:

~~~sql
SELECT tenant_id, status,
       COUNT(*) AS task_count,
       MAX(version) AS highest_version
FROM tasks
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

This is a **screening check**, not proof of every individual row. Follow up by comparing IDs/versions in mismatched groups and transactions near W. Quantify discrepancy counts, severity, remediation method, owners, and post-fix status.

### RPO Result Sheet

~~~text
Failure time T0:
DB apply/log position in B:
Recovery point W:
Missing or stale-version ACK set items:
Measured RPO lag and uncertainty:
Tasks/versions needing remediation:
Unsynced objects / checksum mismatches:
Missing / duplicate events:
Business impact approver:
Verdict PASS / FAIL / NOT_VERIFIED:
~~~

If measured RPO is 6 minutes against a 5-minute target, mark **FAIL** even if the app came back in 25 minutes. If checkpoint evidence is missing, mark **NOT_VERIFIED**.

## 12. Failback: Returning the System to A

After failover, region B accepts writes. When A comes back, A's data is stale. **Failback is never just flipping DNS back**: you must transfer authoritative data back under strict control.

Procedure:

1. Keep **B as the sole primary**; bring A back in an isolated/read-only state.
2. Investigate the root cause and check whether A accepted isolated writes during a split-brain.
3. **Re-seed A from B's state** or use tested, platform-supported reverse replication; never ad-hoc merge two primaries.
4. Establish a new sync checkpoint **W2** and reconcile all tasks, objects, outbox rows, and operations confirmed by B.
5. Pick a failback window and fence/block writes in B. Wait until A durably applies up to W2.
6. Transfer write authority to A, shift routing, run smoke tests, and monitor. Workers run only where write authority resides.
7. Return B to standby, verify reverse replication/backups, IAM permissions, quotas, and runbooks.

If A cannot safely accept new writes, the right move may be **keeping B as primary long-term** until A is rebuilt cleanly.

| State | Safe decision |
| --- | --- |
| Zero new writes in B | Can return to A after confirming A's state remains authoritative |
| B accepted 500 new updates | Never point directly back to A; transfer all 500 updates and reconcile |
| Both A and B accepted writes | Halt writes, preserve evidence, resolve split-brain via business and engineering decision |

## 13. Well-Architected Evaluation

| Pillar | Questions for the DR plan | Required evidence |
| --- | --- | --- |
| **Operational Excellence** | Who activates DR, who is on call, who aborts, and is the process rehearsed? | Versioned runbooks, timelines, incident records, postmortems |
| **Security** | Does B enforce IAM/KMS, data residency, TLS, audits, and least privilege? | Security tests, config reviews, residency approvals |
| **Reliability** | Are RTO/RPO, single-writer, replication, and restore proven? | Fault injection, failover/failback drills, ID and log-position reconciliation |
| **Performance Efficiency** | Can B serve peak load or approved degraded mode? | Load tests, p95/p99, DB connections, queue backlog |
| **Cost Optimization** | Are standby, replication, backup, log, egress, and drill costs justified? | Dual-region TCO, failover operating cost, quotas, utilization |
| **Sustainability** | Can idle standby resources be trimmed while preserving RTO/RPO? | Scaling/right-sizing rules and post-tuning drill results |

Running low-capacity warm standby is usually cheaper than active/active, but must prove **scale-up speed** is fast enough. Replicating data to B and keeping long backups raises cost while lowering region-loss and accidental-delete risk. Never optimize one pillar by breaking mandatory constraints of another.

### Which Costs Need Budgeting?

- Compute/managed DB in B, intra-region HA, standby headroom, and reserved capacity if used.
- Cross-region data transfer, replication logs, object copies, independent backups, and restore tests.
- Load balancers/CDN/DNS, NAT, private connectivity, endpoints, and egress.
- Metrics, log retention, tracing, KMS calls, auditing, and security tooling.
- On-call staffing, drill preparation/execution, multi-day operation in B, and reverse sync to A.

Never budget only for steady-state healthy bills. An actual failover may require running A and B side-by-side for reconciliation before decommissioning or failing back.

## 14. Sample DR Plan and Drill Report

### 14.1. Target Manifest (Illustrative, Not Deployment Config)

~~~yaml
system: task-management-saas
primary_region: region-A
standby_region: region-B
strategy: warm-standby
critical_journeys:
  - name: "Sign in, read, and update tasks"
    rto_minutes: 45
    rpo_minutes: 5
    degraded_mode: "Search and notifications may be delayed"
  - name: "File attachments"
    rto_minutes: 45
    rpo_minutes: null
    note: "Requires separate durability policy approval"
write_authority:
  before_dr: "PostgreSQL A"
  after_dr: "PostgreSQL B only after fencing A completes"
replication:
  database: "Async log replication, verify apply position"
  objects: "Cross-region replication + checksums"
  events: "Outbox + idempotent replay"
decision_roles:
  activate_dr: "Incident commander"
  accept_data_loss: "Business owner per policy"
required_evidence:
  - "RTO timeline"
  - "Watermark and RPO reconciliation"
  - "Security / load / smoke tests"
  - "Failback and re-seed validation"
~~~

The attachment RPO is **null** because it is unresolved; this is an **open action item**, not an exemption. A real DR plan should not be approved while this critical item lacks a decision owner.

### 14.2. Drill Result Sheet

~~~text
Drill ID, date/time, timezone:
Environment / dataset / scope:
Participants, incident commander, business owner:
Incident scenario:
Target RTO, RPO by data class:
T0 - loss of A:
T1 - alert:
T2 - DR decision:
T3 - fencing and W selected:
T4 - DB B writable / compute B ready:
T5 - routing shifted to B:
T6 - smoke tests PASS:
T7 - core features opened:
Measured RTO = T7 - T0:
Recovery point W and DB apply position:
Measured RPO / unverified gaps:
Missing or stale task IDs/versions:
Object checksum mismatches:
Missing/duplicate events, DLQ/backlog:
p95/p99, error rate, DB utilization in B:
Permission and encryption checks in B:
Incurred cost, failback duration:
Verdict PASS / PARTIAL / FAIL / NOT_VERIFIED:
Risks, owners, remediation deadlines:
Result approver:
~~~

### 14.3. Overall PASS Criteria

A drill passes **within its tested scope** when both RTO and RPO meet targets with proof, no concurrent writers exist, transactions reconcile against the checkpoint, security controls remain intact, core business flows hold under target load, queues produce zero duplicate side effects, and operations can execute failback.

**If key evidence is missing, record NOT_VERIFIED**—never treat an "HTTP 200 endpoint" as proof of the whole system. Staging drills must also note differences from production in dataset size, traffic, quotas, regions, and integrations.

## 15. Example: Reading Results and Identifying Blockers

Suppose a staging drill yields:

| Check | Target | Result | Conclusion |
| --- | --- | --- | --- |
| Core API RTO | ≤ 45 minutes | 38 minutes T0→T7 | PASS within tested scope |
| Task RPO | ≤ 5 minutes | 3 minutes 20 seconds by apply log | PASS if ID/version reconciliation confirms |
| Transaction ACKs | Approved loss tolerance and remediation plan | 17 ACKed updates did not reach B | Analyze whether this matches published RPO contract |
| Object storage | Meets file durability pledge | 2 metadata rows exist without file payloads in B | FAIL if uploads reported success with zero-loss pledge |
| Event side effects | Zero duplicate notifications | 4 events delivered twice | FAIL on idempotency |
| Security | Tenant isolation | Cross-tenant reads rejected | PASS for this test |
| Load capacity | 1,200 req/s | Tested only at 600 req/s | NOT_VERIFIED |

Never declare an **overall PASS** just because RTO/RPO numbers look good on paper. Missing files, duplicate events, and untested peak load are serious defects. If the business promises zero data loss for confirmed actions, even 17 un-replicated ACKs are a blocker despite falling inside 5 minutes. User contracts and data-loss policies must align.

## 16. Independent Practice Exercise

An **appointment booking** application runs in region A with an API, PostgreSQL, Redis, medical-record object storage, email/SMS queues, and an external identity provider. It handles roughly 20,000 appointments/day with peak traffic 5x normal. Executive leadership requires:

- Viewing and creating appointments must recover within **30 minutes** of a region loss.
- **Confirmed appointments must never disappear** after failover.
- Email/SMS may lag up to 2 hours, but must never send duplicates.
- Sensitive records must stay strictly within approved regions; encryption and auditing must continue uninterrupted.
- B must have enough capacity to absorb peak load.

Complete the following tasks:

1. **BIA and RTO/RPO.** Build a per-flow matrix covering login, read/create appointments, records, and notifications. Set thresholds, success-confirmation policies, degradation options, and owners. Explain why plain async replication cannot prove zero lost confirmed appointments.
2. **Two-region architecture.** Draw DNS/ingress, compute, database, object storage, queues/outbox, IAM/KMS, backups, and observability. Choose backup/restore, pilot light, warm standby, active/active, or a hybrid; defend the choice using RTO/RPO and cost.
3. **Write authority and data.** Explain how B acquires write authority after fencing; when the API acknowledges an appointment; behavior during a network partition; and handling of un-replicated objects.
4. **Runbook.** Write at least 10 steps, each with owner, max duration, action, evidence, and NO-GO trigger. Check whether the sum genuinely fits inside 30 minutes.
5. **Drills.** Define at least three scenarios: total loss of A, A/B partition, replication lag + backlog; describe safe simulation, metrics, reconciliation data, and PASS/FAIL rules.
6. **Failback.** Suppose B created **500 new appointments**. Design re-seeding/reverse replication, checkpoint W2, write fencing, reconciliation, and conditions to move writes back to A.
7. **Well-Architected and ADR.** Analyze Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability. Write an ADR covering the DR choice, rejected options, residual risks, and review date.

**Submission package:** architecture diagram, BIA/RTO/RPO matrix, ADR, failover/failback runbook, drill plan, verification scorecard, and risk register with owners.

### Self-Assessment Criteria

A strong submission explicitly specifies **timestamps** for RTO, **transaction checkpoints and ID sets** for RPO, **single-writer** enforcement, region-loss vs. partition behavior, file/queue/side-effect handling, standby-region access controls, parallel-run costs, and failback gates. Every PASS claim must cite evidence; unverified items must be marked **NOT_VERIFIED**, never guessed.

## 17. Methodology to Remember

Effective DR design flows from **business impact → RTO/RPO → two-region topology and data → write-authority control → runbooks → drills → reconciliation → continuous improvement**. Having two regions, a database replica, and a DNS switch does not prove recovery readiness.

The final question of any review board is: **When region A fails right at peak hour, who decides to fail over, how long does it take, what data is at risk, what evidence proves B is serving accurately, and how do we return to normal without losing more data?**
