# Business Impact Analysis and Selecting RTO and RPO

## 1. Disaster Recovery Starts from Business Impact

Disaster Recovery (DR) is the ability to restore services and data after a severe incident that prevents a system or an infrastructure domain from continuing to operate normally. An incident may be the loss of an availability zone, a region failure, data corruption, ransomware, a widespread configuration error, a provider connectivity outage, or an operational failure.

A good DR plan does not start with the question "how many replicas do we need?" or "should we use active-active?". It starts with the question: **which services are critical, how long can the business tolerate an outage, how much data can be lost, and which dependencies must be restored for business processes to resume operating?**

Two commonly used metrics:

- **RTO (Recovery Time Objective):** the target time to restore a service after a disruption. This is the time limit an organization sets for restoring a function at a defined service level.
- **RPO (Recovery Point Objective):** the target data recovery point, representing the time-based amount of data loss the business can accept when recovering from a copy/backup/replica.

RTO and RPO are **business objectives**, not automatic guarantees of a cloud feature. Configuring hourly backups does not prove a one-hour RPO; you must account for when the backup is actually consistent, incident detection time, data scope, and the restore procedure. Similarly, having a standby region does not prove a 15-minute RTO if DNS, identity, quotas, data, or operational personnel take several hours to recover.

In the **CLOUD_ARCHITECTURE** module, selecting RTO/RPO connects business requirements with networking, compute, storage, databases, security, and deployment models. Decisions must balance **reliability, security, performance, scalability, cost, and operations** following a Well-Architected mindset.

Running example: a booking platform with property search, room holds, payments, booking management, email notifications, and reporting. Search can degrade temporarily; payments and booking state require tighter protection; analytical reports can be regenerated from transactional data.

## 2. Time Concepts to Distinguish

RTO and RPO are often used alongside several other concepts. Definitions must be aligned with the business owner, operations team, and providers:

| Concept | Meaning | Key Question |
| --- | --- | --- |
| **MTPD/MAO** | Maximum Tolerable Period of Disruption / Maximum Acceptable Outage: the maximum downtime a business can tolerate before consequences become unacceptable | How long can the service be down at most? |
| **RTO** | The target time to restore a function/service after an incident | How quickly must the service be brought back? |
| **RPO** | The acceptable amount of data loss measured in time when recovering | How much recent change prior to the incident can be lost? |
| **WRT (Work Recovery Time)** | The time required after technical systems recover to verify, reconcile, and clear backlogged business work | Once systems are up, how long until staff and workflows operate normally? |
| **MTTR** | Mean Time To Repair/Recover, an observed metric of average repair/recovery time as defined by the organization | How long did past incidents actually take? |
| **MTBF** | Mean Time Between Failures, the average time between failures under a defined measurement method | How frequently do incidents occur? |

MTPD/MAO is not a recovery target. It represents the ultimate disruption threshold the business can withstand. RTO should be shorter than MTPD/MAO to leave room for WRT and backlog processing.

A common planning relationship:

~~~text
RTO + WRT < MTPD
~~~

This is a simple expression for establishing a buffer. Some organizations define MTPD, MAO, or WRT slightly differently; the glossary and start/end milestones must be clearly documented in the BIA.

## 3. Business Impact Analysis (BIA)

**BIA** is the process of analyzing business activities, their criticality, and the consequences when they are disrupted. BIA produces evidence to prioritize recovery and determine appropriate RTO/RPO targets.

Avoid asking the business owner a generic question such as "how important is this service?". Ask them to describe the impact over time across customer scope, revenue, legal/regulatory compliance, safety, reputation, and dependencies.

### 3.1. Impact Dimensions

| Impact Dimension | Example Questions |
| --- | --- |
| Revenue/financial | How much direct/indirect loss does each 15 minutes, 1 hour, or 1 day of disruption cause? |
| Customers | How many customers cannot place bookings, access bookings, or receive support? Are there workarounds? |
| Legal/contractual | Are reporting deadlines, retention obligations, or partner SLAs violated? |
| Operational | Can staff switch to manual procedures? How fast does the backlog grow? |
| Safety and privacy | Does the incident corrupt transaction state, leak data, or break access controls? |
| Reputation | How does it affect trust, brand image, and customer retention? |
| Supply chain/partners | Are payment providers, identity providers, DNS, or integration partners affected? |

### 3.2. Time-Based Analysis

Impact does not necessarily grow linearly. A 10-minute outage might be absorbed via buffer inventory or a hotline; after 4 hours, however, backlog, refunds, complaints, and reconciliation obligations spike sharply.

| Outage Duration | Illustrative Impact on the Booking Platform |
| --- | --- |
| 0–15 minutes | Requests fail, customers retry; on-call team scopes the issue and switches to fallback procedures |
| 15–60 minutes | Conversion rate drops; customer support receives many tickets; in-flight transactions need reconciliation |
| 1–4 hours | Backlog grows; partners and enterprise clients must be notified; risk of SLA breaches |
| 4–24 hours | Significant financial/reputational impact; backup staffing, manual processes, and reconciliation become heavy |
| Over 24 hours | May exceed tolerance threshold; requires executive decisions, legal/contractual notifications, and long-term recovery |

This is only an illustrative example. Each business must quantify impact using data, contracts, and input from the business owner.

### 3.3. BIA Questionnaire Template

For each activity, record:

1. Who uses it, and which customers/partners depend on it?
2. When is the activity most critical (peak hours, month-end, travel season)?
3. What is the minimum acceptable service level when degraded?
4. Can it switch to manual or offline processing? For how long and at what capacity?
5. What is the impact after 15 minutes, 1 hour, 4 hours, 1 day, and multiple days?
6. Which lost data would cause irreversible damage or require manual reconciliation?
7. What consequences are acceptable, and who has authority to approve them?
8. How much time is needed to clear the backlog after the system returns?

## 4. Decomposing the Business into Services and Capabilities

A single application name may encompass many capabilities with different levels of criticality. Assigning one RTO/RPO to the entire platform can cause the organization to over-invest in reporting or under-protect payments.

Example decomposition:

| Capability | Illustrative Criticality | When Disrupted |
| --- | --- | --- |
| Authentication/authorization | Very high | Users cannot sign in or verify permissions; if security fails, fail-safe must take priority |
| Booking/Inventory | Very high | Cannot hold rooms/confirm transactions; risk of double-booking and lost revenue |
| Payment integration | Very high | Payment status is unknown; must neither lose collected funds nor confirm incorrectly |
| Customer booking view | High | Customers cannot view existing bookings; support load increases |
| Property search | Medium–high | Customers struggle to find results; can use cache/bounded stale data |
| Notification | Medium | Emails/SMS are delayed; can resend from event/outbox |
| Analytics/report | Lower for real-time operations | Can be delayed or regenerated from source data |
| Static media | Product-dependent | CDN/backup may serve it; substitutability depends on caching |

Criticality must be based on the BIA, not engineering guesswork. A service that looks "auxiliary" such as identity, DNS, or secrets may be a mandatory dependency for many critical services.

## 5. Selecting RTO from Business Impact

RTO is chosen so the service returns to a defined operating level before impact exceeds acceptable thresholds. You must define what "recovered" means:

- System processes can start?
- API health check returns 200?
- Users can sign in?
- Can search and hold a room?
- Can complete a booking and verify payment?
- Backlog has been cleared and normal SLOs have resumed?

A green health check does not mean the business process is restored. You should define **minimum viable service** and **full service restoration** separately if partial recovery is possible.

### 5.1. RTO by Service Tier

Illustrative example:

| Tier | Capability | Example Target RTO | Recovery Condition |
| --- | --- | ---: | --- |
| Tier 0 – Critical | Identity, booking, payment status | 15 minutes | Can authenticate, control transactions, and reconcile |
| Tier 1 – Essential | Search, customer booking view | 1 hour | Customers can search/look up bookings; some features may be degraded |
| Tier 2 – Important | Notification, partner sync | 4 hours | Backlog processed, no lost events |
| Tier 3 – Deferrable | Analytics, historical reports | 24 hours | Can rebuild from stored data sources |

These numbers are not universal recommendations for every company. Choose them based on MTPD, revenue, customers, workarounds, WRT, and budget.

### 5.2. Accounting for Human Time as Well

Actual recovery time may include:

~~~text
T_detect       = time to detect and confirm the incident
T_decide       = time to declare DR and select the runbook
T_provision    = time to provision/prepare standby infrastructure
T_data         = time for restore/replication catch-up
T_validate     = time to validate data and functionality
T_traffic      = time to shift routing and stabilize load
T_operational  = time for the business to return to minimum viable level

Actual RTO = sum of relevant intervals along the recovery path
~~~

Not all components are sequential; some can run in parallel. Measure during drills to identify the critical path, avoiding the mistake of summing only script execution times while forgetting detection, approvals, DNS, certificates, quotas, or business testing.

## 6. Selecting RPO from Data Loss Tolerance

RPO answers: **when recovery is required, how much recent data can be missing while remaining acceptable to the business?**

If RPO is 15 minutes, the organization accepts that in the defined recovery scenario, unprotected changes within that maximum window may be lost. This does not mean exactly 15 minutes are always lost, nor does it mean running a backup every 15 minutes is sufficient.

### 6.1. RPO Differs from Backup Frequency

Suppose:

- Backups are scheduled every 4 hours.
- The backup starts at 10:00 but completes and reaches consistency at 10:25.
- An incident occurs at 12:10.
- The most recent usable backup is the 10:25 snapshot.

The most recent protected data point is 10:25, so the potential data loss window up to the incident is 1 hour 45 minutes. A frequency of "every 4 hours" is not the actual RPO. If transaction logs are continuously archived and point-in-time restore can recover to 12:05, the RPO can be significantly smaller; however, that depends on log availability, consistency, and verified restore capability.

### 6.2. RPO by Data Type

| Data Type | Acceptable Data Loss | Rationale |
| --- | --- | --- |
| Confirmed bookings | Near-zero or very low RPO | Losing confirmed bookings causes disputes with customers and partners |
| Payment ledger/status | Very low RPO, plus reconciliation | Must avoid losing track of collected/authorized funds |
| Search index | Regenerable; RPO based on event retention | Not the authoritative source |
| Notification queue | Replayable if event/outbox remains | Delays acceptable if no events are lost |
| Analytics projection | Higher RPO acceptable if rebuildable | Can be recreated from transactional sources |
| Property photos | Per durability and backup/copy policy | Can be re-uploaded in some cases, though cost and permissions must be evaluated |

### 6.3. RPO Is Not Just Database Data

A business process can depend on many types of state:

- Database transactions and transaction logs.
- Objects/documents stored in object storage.
- Message brokers, outboxes, event logs, and consumer offsets.
- Secrets, keys, certificates, and infrastructure configuration.
- DNS, identity, policies, and metadata.
- Search index mappings/versions and cache generations.

If a database is restored to a point in time while object storage or event logs are not synchronized to that same point, the application may reference non-existent objects or process duplicate events. RPO must be defined for **the entire dataset required for business consistency**, not just the primary database.

## 7. Combining RTO, RPO, MTPD, and WRT

Each capability needs at least one justified set of targets:

| Capability | Example MTPD | Example RTO | Example WRT | Example RPO |
| --- | ---: | ---: | ---: | ---: |
| Booking | 2 hours | 30 minutes | 30 minutes | 1 minute |
| Payment status | 1 hour | 15 minutes | 45 minutes reconciliation | Near 0 |
| Search | 8 hours | 2 hours | 30 minutes | 15 minutes or rebuild |
| Notification | 24 hours | 8 hours | 2 hours backlog | 5 minutes or event replay |
| Analytics | 3 days | 24 hours | 4 hours data verification | 24 hours if sources fully retained |

Suppose Booking has an MTPD of 2 hours. Choosing an RTO of 30 minutes and a WRT of 30 minutes leaves a 1-hour buffer for variance, cascading incidents, and operational fluctuations. If WRT itself takes 2 hours, a 30-minute RTO target will not get the business back to operating within MTPD.

### 7.1. Do Not Force One Target on the Entire System

A system has multiple tiers:

- The API may be operational after 15 minutes while reports are not ready yet.
- Booking may accept new transactions while reconciliation of older payments is still running.
- Search may serve an older index labeled stale while booking still verifies directly.
- Notifications may accumulate a backlog and catch up later without blocking transactions.

Define recovery states by capability and dependency rather than a single "application restored" checkbox.

## 8. Building a Dependency Map and Recovery Sequence

BIA identifies critical activities; dependency mapping identifies the systems that must be restored for those activities to run.

~~~mermaid
flowchart TD
    USER["Customers / staff"]
    EDGE["DNS / CDN / WAF / Load balancer"]
    AUTH["Identity / Secrets"]
    API["Booking API / Compute"]
    DB["Booking DB"]
    PAY["Payment provider / Payment ledger"]
    QUEUE["Outbox / Event broker"]
    SEARCH["Search index"]
    NOTIFY["Notification worker"]
    USER --> EDGE --> API
    API --> AUTH
    API --> DB
    API --> PAY
    DB --> QUEUE
    QUEUE --> SEARCH
    QUEUE --> NOTIFY
~~~

If the API is running but DNS is not pointed properly, identity cannot issue tokens, or secrets cannot be decrypted, the capability is still not recovered. If the database is restored but the payment provider webhook endpoint still points to the old region, transaction state updates may be missed.

### 8.1. Dependency Classification

| Dependency Type | Examples | What Must Be Clarified |
| --- | --- | --- |
| Critical path runtime | Booking database, identity, DNS | Must be available immediately to restore minimum service |
| Data dependency | Object storage, event log, payment ledger | Consistency, RPO, restore order |
| Control plane | IAM, cloud console/API, deployment system | Can infrastructure be controlled when the primary region is lost? |
| External provider | Payment, SMS, identity federation | Are fallback endpoints/credentials/contracts in place? |
| Human/process | On-call, approver, finance reconciliation | Who has authority to declare DR and handle ambiguous transactions? |
| Observability | Monitoring, logs, alerting | Does it operate independently of the primary failure domain? |

### 8.2. Single Points of Failure Outside the Application

You must also inspect:

- DNS zones, registrar, certificate authority, and domain administration access.
- Identity provider, KMS, secret manager, and key recovery.
- Artifact registry, container images, packages, and IaC state.
- CI/CD, accounts/roles, and deployment permissions in the standby region.
- Monitoring, paging, chat/bridge, and runbook documentation.
- Cloud quotas, IP addresses, load balancer capacity, and licenses.

A DR plan can fail even when data is well replicated because the operations team cannot sign in or deploy into the standby environment.

## 9. Choosing a DR Strategy by RTO/RPO and Cost

Common strategies yield different availability levels and costs. Names may vary across providers; what matters is describing the actual state of compute, data, and routing.

| Strategy | Description | Relative RTO/RPO | Cost/Complexity |
| --- | --- | --- | --- |
| Backup and restore | Back up data/configuration; provision infrastructure and restore when an incident occurs | Longer RTO; RPO depends on backups/logs | Low standby cost; restore can take a long time |
| Pilot light | Keep minimal core platform always ready, with data replicated/backed up | Medium RTO; RPO depends on replication | Lower than warm standby, but requires scaling/provisioning on failover |
| Warm standby | Scaled-down system pre-running in the standby region, data synchronized | Shorter RTO; RPO can be low | Ongoing operating cost and standby capacity |
| Active-active / multi-site | Multiple sites actively serving traffic together | Very low RTO possible; RPO can be very low depending on data | Highest cost, consistency, routing, and operational complexity |

No strategy automatically guarantees a specific RTO/RPO figure. For example, backup and restore can achieve a few hours of RTO if data is small, IaC is complete, and restore is optimized; warm standby can still require many hours if database failover or identity is not automated.

### 9.1. Backup and Restore

Suitable for capabilities with a longer MTPD or that can be regenerated. Requires:

- Automated, encrypted backups with separate access controls and retention.
- Backup copies stored outside the failure domain being protected against.
- Point-in-time recovery if required by RPO.
- Complete IaC and artifacts to rebuild network/compute/identity/configuration.
- A restore runbook with data verification and application testing steps.

### 9.2. Pilot Light

Keeps the necessary foundation ready: networking, permissions, database replicas or backup data, artifacts, and some essential components. On failover, compute, workers, and endpoints are scaled up. You must verify quota/instance provisioning times, image pulls, autoscaling, and control plane dependencies.

### 9.3. Warm Standby

The standby region runs a nearly complete stack at reduced capacity, continuously running health checks and receiving replication. Failover involves scaling up capacity, shifting traffic, checking dependencies, and processing backlog. You must verify whether standby can handle 100% of production load.

### 9.4. Active-Active

Multiple regions serve traffic simultaneously. Must address routing, data consistency, conflict resolution, write ownership, idempotency, sessions, caching, global rate limiting, and failback. Multi-region active-active is not appropriate merely for a low RTO; if the business cannot tolerate conflicts or the team cannot operate it reliably, a simpler model may be safer.

## 10. Choosing Data Topology and Replication

RPO is usually governed by how data is replicated and how transactions are recovered:

| Method | Characteristics | DR Questions |
| --- | --- | --- |
| Periodic snapshot/backup | Captures state at points in time | Is the latest backup consistent and restorable? |
| Continuous log shipping | Sends transaction logs/WAL/binlog | Are logs protected out-of-region and to what point can they be replayed? |
| Asynchronous replication | Primary commits, then sends changes to replica | What is the maximum replication lag; can acknowledged transactions be lost? |
| Synchronous replication | Commit waits for replica acknowledgment per DB mechanism | How do latency/availability change when cross-region links fail? |
| Object replication | Copies objects/versions across buckets/regions | How are deletes, metadata, encryption keys, and replication status handled? |
| Event streaming replication | Replicates logs/streams and offsets | Are ordering, retention, consumer positions, and replay preserved? |

### 10.1. Replication Does Not Replace Backup

If data is accidentally deleted, encrypted by malware, or mass-corrupted by bad writes, replication can copy the corruption to the standby region. Backups with versioning/immutability and separated delete permissions protect against logic bugs or malicious actions.

A sound data strategy typically combines replication to shorten failover time with backups to recover to a clean historical point.

### 10.2. Replication Lag and Acknowledged Writes

With asynchronous replication, the primary may return success before the replica receives the record. If the primary fails abruptly, transactions already acknowledged to users may not exist on the standby. You must:

- Measure replication lag in time and bytes/LSN/offsets.
- Determine RPO during abrupt disconnection failures, not just normal operation.
- Have a policy to block or degrade writes when lag exceeds a threshold if the business requires it.
- Reconcile ambiguous transactions after failover.

Do not describe "near-real-time replication" as zero RPO without evidence of commit acknowledgment and failure semantics.

## 11. Quantitative Example of BIA and RTO/RPO

Suppose the business owner analyzes the booking function:

- MTPD: 2 hours.
- The organization needs 30 minutes for staff to verify in-flight bookings, perform reconciliation, and resume customer support (WRT).
- The business wants a 30-minute buffer in case the incident lasts longer than expected.
- No confirmed booking may be lost; unconfirmed inventory holds can be recalculated from source transactions.

Initial targets can be proposed:

~~~text
RTO target = 30 minutes
WRT target = 30 minutes
Operational buffer = 60 minutes
MTPD = 120 minutes
RPO = 1 minute (subject to transaction and replication validation)
~~~

The proposal is only valid after feasibility testing and approval by the business owner. If testing reveals a technical RTO of 90 minutes, the organization must invest further or renegotiate targets/business mitigations; it must not unilaterally change the RTO to 90 minutes just to justify the current architecture.

### 11.1. Estimating Financial Impact

One way to support the discussion is to quantify loss over time intervals:

~~~text
Estimated impact =
  lost contribution margin
  + recovery and overtime cost
  + customer compensation
  + partner/contract penalties
  + expected regulatory/remediation cost
~~~

Avoid mechanically multiplying average revenue by duration if traffic is seasonal or transactions can shift to later times. Analyze direct costs, remediation costs, and long-term consequences.

## 12. Translating Targets into Technical Requirements

After the BIA, architects work backward from RTO/RPO to determine controls:

| Target | Technical Requirements That May Arise |
| --- | --- |
| 15-minute RTO | Ready IaC, standby capacity, failover automation, appropriate DNS/routing TTLs, tested access/runbooks |
| 1-hour RTO | Pilot light/warm standby, clear scaling procedure, measured restore |
| Near-zero RPO | Strict replication/commit semantics, log shipping, transaction integrity, reconciliation |
| 15-minute RPO | Sufficiently frequent backups/log archives, lag alerts, PITR, and restore testing |
| Long MTPD | Can consider backup/restore and manual workarounds if lower cost |
| Short WRT | Automated reconciliation, audit trails, idempotent replay, clear state data |

A technical target must be backed by evidence: test results, measured recovery time, measured data loss, capacity, failover/failback, and an accountable owner. Vendor-advertised numbers do not replace testing under your real workload and configuration.

## 13. Incident Scenarios and Differing Targets

DR is not just losing an entire region. Each scenario has a different scope and recovery approach:

| Scenario | Impact | What Must Be in the Plan |
| --- | --- | --- |
| Loss of an availability zone | Compute/network/storage in that zone unavailable | Multi-zone placement, database quorum/failover, remaining capacity |
| Loss of a region | Multiple services and regional control plane affected | Cross-region data, network, DNS, identity, quotas, and routing |
| Database corruption | Logical data corrupted while service remains up | PITR, immutable backups, clean recovery point, and reconciliation |
| Ransomware/credential compromise | Backups or replicas may be deleted/encrypted | Immutable/offline copies, separated permissions, clean-room restore |
| Deploy/configuration error | Infrastructure-valid change that breaks functionality | Rollback, Git/IaC history, config versions, blast radius |
| Payment provider outage | An external dependency stops working | Circuit breaker, payment unknown state, fallback, and reconciliation |
| Loss of DNS/identity/KMS | Application may run but cannot be controlled/accessed | Fallback dependencies, break-glass access, key recovery |

An RTO/RPO may be achievable for a zone loss yet unachievable during ransomware. You must specify the **scenario, failure domain, data scope, and clean conditions** for each target.

## 14. Failover, Failback, and Recovery Order

Failover shifts operations to the standby environment. Failback returns operations to the preferred environment after repairs are complete. Failback is often riskier because data generated while DR served traffic must be synchronized back.

### 14.1. Failover Runbook

1. Detect and verify the incident; avoid declaring DR based on a single isolated alert.
2. Business/incident commander determines scope and activates the runbook under defined authority.
3. Block writes or isolate the old source if needed to prevent split-brain.
4. Select a valid data point/replica; record the achievable actual RPO.
5. Promote databases/restore services in dependency order.
6. Restore identity, secrets, networking, compute, queues, and endpoints.
7. Run technical health checks and sample business transactions.
8. Shift traffic gradually/canary if appropriate.
9. Open full traffic and monitor latency, errors, data consistency, backlog, and payment states.
10. Record actual recovery time, data point, and transactions needing reconciliation.

### 14.2. Preventing Split-Brain

When both primary and standby can accept writes due to a network partition or erroneous failover, data can diverge. A mechanism to establish write authority is required: fencing tokens, quorum/leases, promotion controls, or procedures to isolate the old primary. Do not rely solely on DNS changes; clients/workers may still hold connections to the old endpoint.

### 14.3. Failback

- Confirm the old region/cluster is clean and has sufficient capacity.
- Identify the current authoritative data source.
- Replicate/copy deltas from DR back to the primary environment.
- Verify consistency, schema/versions, and backlog.
- Choose a cutover window, pause or coordinate writes per the runbook.
- Switch routing and verify no writers remain on the old site.
- Monitor after cutover and keep a rollback plan.

Do not fail back merely because the primary region shows "green." Check recurrence risk and the ability to maintain DR readiness after switching.

## 15. DR Testing and Proving RTO/RPO

An untested runbook does not prove a system can recover. Each critical capability needs a drill schedule and recorded evidence:

| Test Type | Scope | Evidence to Retain |
| --- | --- | --- |
| Backup restore test | Restore database/objects from backup | Restore duration, checksums, missing data, permissions, and query results |
| PITR test | Recover to a point prior to an incident | Actual recovery point, transaction boundaries, and RPO |
| Component failover | Database, cache, broker, or service | Failover duration, client errors, replication lag |
| Zone/region exercise | Shift traffic to another failure domain | End-to-end RTO, capacity, dependencies, and business transactions |
| Cyber recovery/clean-room | Recover from clean copies after compromise | Permission isolation, clean images, credential/key rotation, clean data |
| Tabletop exercise | Practice decisions, communications, roles | Runbook gaps, approval authority, decision time |

### 15.1. Measuring the Right Timestamps

Record timestamps:

- T0: incident begins (if determinable).
- T_detect: system/operations team detects it.
- T_declared: DR is declared.
- T_data: data reaches the chosen recovery point.
- T_service: minimum viable service is ready.
- T_business: critical business process completes test transactions.
- T_full: service and backlog return to full capacity.

RTO should be measured from the agreed start milestone to the defined business recovery level. Reporting detection, decision, technical recovery, and WRT separately helps locate bottlenecks instead of hiding them inside a single number.

### 15.2. Controlled Testing

Failure injection requires a defined scope, environment, accountable owner, stop conditions, and rollback plan. Do not cause production data loss or interrupt customer traffic without appropriate approvals/controls. You can start with restore tests and game days in a production-like staging environment.

## 16. Governance, People, and Communication Plans

DR is an organizational process, not just automation. You must specify:

- Who has authority to declare a disaster and trigger failover?
- Who decides the recovery point when choosing between the most recent data and clean data?
- Who verifies payment/booking transactions requiring reconciliation?
- Who notifies customers, partners, vendors, and relevant authorities?
- Who holds break-glass credentials and how is usage audited?
- When key personnel are unavailable, who are the designated backups?
- Where are runbooks, contact lists, and document copies stored if the primary region is inaccessible?

A DR system needs backup administrative accounts/permissions, an out-of-band contact list outside the primary failure domain, offline/immutable documentation, and role-based drills. Never leave all recovery information solely inside a wiki that becomes inaccessible when SSO or the primary region goes down.

## 17. Cost and Investment Decisions

Shorter RTOs and lower RPOs generally require more standby capacity, faster replication, automation, frequent testing, and skilled operations staff. However, not every capability needs the maximum tier.

| Strategy | Ongoing Maintenance Cost | Recovery Cost/Latency | Risks to Manage |
| --- | --- | --- | --- |
| Backup and restore | Typically lower | Longer provisioning/restore | Unrestorable backups, missing capacity or documentation |
| Pilot light | Low–medium | Requires scaling/provisioning | Quotas, provisioning time, unstarted dependencies |
| Warm standby | Medium–high | Faster traffic shift/scaling | Replica lag, under-provisioned standby capacity |
| Active-active | High | Can reduce switchover time | Conflicts, split-brain, consistency, operational complexity |

### 17.1. Cost–Impact Analysis

Compare the total cost of the DR strategy against expected loss:

~~~text
Expected annual disruption impact =
  sum over scenarios (
    annual scenario probability
    * business impact at achieved recovery time
  )

DR investment decision =
  compare expected impact reduction
  against standby, replication, backup, testing and operating cost
~~~

Do not treat incident probability as exact when historical data is sparse. Use ranges/assumptions and sensitivity analysis. A rare incident with major legal or safety consequences may still require mandatory controls rather than optimizing solely for expected value.

## 18. Practice Exercise: Building a BIA and DR Targets for the Booking Platform

**Assumed context:** the platform operates in a primary region with three availability zones; the booking database has backups and an asynchronous replica in another region; the search index is rebuildable; property photos reside in object storage; payments go through a partner; notifications are processed via an event queue.

### Tasks

1. List business capabilities and owners: identity, search, booking, payment, notification, media, analytics.
2. Conduct a BIA for each capability across financial, customer, legal, operational, and reputational impacts over time intervals.
3. Define MTPD/MAO, RTO, WRT, and RPO with justification; state who approves the targets.
4. Draw a dependency map including DNS, identity, KMS/secrets, network, compute, database, object storage, broker, search, and payment provider.
5. Select backup/restore, pilot light, warm standby, or active-active per capability; one strategy does not have to apply to the entire system.
6. Specify data to back up/replicate, retention, immutable copies, replication lag, and reconciliation methods.
7. Write failover/failback runbooks, recovery order, fencing/split-brain prevention, and traffic-opening criteria.
8. Plan tests for restore, PITR, zone loss, region loss, and clean-room recovery.
9. Calculate ongoing cost versus expected loss reduction; state assumptions and uncertainty ranges.
10. Write an ADR summarizing decisions, residual risks, and the next drill date.

### BIA/DR Worksheet Template

| Capability | Disruption Impact | MTPD | RTO | WRT | RPO | Preliminary Strategy |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Booking | Loss of ability to hold/confirm rooms | Defined by business | Defined by business | Booking reconciliation | Very low | Warm standby or equivalent |
| Payment | Unknown payment state | Defined by business | Defined by business | Reconciliation | Near 0 or per ledger | Replication/logs + reconciliation procedure |
| Search | Difficulty finding properties | Defined by business | Defined by business | Index quality check | Rebuildable | Reindex from source |
| Notification | Delayed notifications | Defined by business | Defined by business | Backlog processing | Per event retention | Queue replication/replay |
| Analytics | Delayed reports | Defined by business | Defined by business | Data reconciliation | Can be higher | Backup/rebuild |

### Completion Criteria

- Targets originate from the BIA and are approved by the business owner.
- RTO, RPO, MTPD, and WRT are clearly distinguished with defined measurement milestones.
- Dependency map includes control plane, identity, DNS, KMS, external providers, and people.
- Data strategy protects transactions, objects, events, and clean backups.
- Runbooks exist for failover/failback, split-brain prevention, and traffic-opening criteria.
- Drill scenarios prove recovery time and data points meet targets.
- Costs and residual risks are recorded in an ADR.

## 19. Well-Architected Checklist Before Approving DR

- [ ] Completed BIA with business owners and clear capability scope.
- [ ] Defined MTPD/MAO, RTO, RPO, and WRT; agreed glossary and measurement milestones.
- [ ] Targets broken down by capability rather than a single number for the entire application.
- [ ] Built dependency map covering data plane, control plane, external providers, and people.
- [ ] Analyzed failure scenarios: zone, region, corruption, ransomware, configuration, and dependency outage.
- [ ] Backups encrypted, separated by permissions/failure domain, with appropriate retention and immutable protection.
- [ ] Measured replication lag, acknowledged writes, log retention, and recovery points.
- [ ] Recovery plans cover databases, objects, events, identity, secrets, keys, and configuration.
- [ ] Capacity, quotas, networking, DNS, certificates, artifacts, and access exist in the standby environment.
- [ ] Runbooks include roles, DR declaration criteria, recovery sequence, and traffic-opening gates.
- [ ] Fencing/write authority prevents split-brain; failback has a separate plan.
- [ ] Reconciliation covers bookings, payments, events, and backlog after recovery.
- [ ] Restore/PITR/failover/failback/cyber recovery tested periodically with evidence stored.
- [ ] Measured end-to-end RTO and actual RPO, including decision time and WRT.
- [ ] Communication channels, documentation, and break-glass access exist independently of the primary failure domain.
- [ ] DR cost weighed against business impact and residual risk.
- [ ] ADR documents trade-offs across reliability, security, performance, cost, and operations.

**Core takeaway:** BIA tells you what needs protection and the consequences of disruption; MTPD/MAO expresses the tolerance threshold; RTO sets the service recovery target; RPO sets the data loss limit; WRT covers the work needed after technical systems return. Only when targets are tied to capabilities, dependencies, data strategies, and measured drills does DR become a proven capability rather than just a contingency document.
