# Defining RPO, RTO, and Workload Tiering on GCP

When an application on Google Cloud goes down or data becomes corrupted, the first question is not "which backup should we enable?", but rather: **how long can the business tolerate an outage, and how much data can it afford to lose at most?** These two answers form the basis for designing, budgeting, prioritizing recovery, and testing disaster recovery capabilities.

This lesson belongs to the **Backup and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_GCP** module. Along the path of learning Google Cloud from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases, this lesson helps learners translate business objectives into measurable technical requirements, choose appropriate backup/DR strategies, and monitor reliability alongside cost.

This lesson focuses on **defining objectives and tiering workloads**, without assuming that every system must be active-active or have an RPO of 0.

After this lesson, you will be able to:

- Explain Recovery Point Objective (RPO), Recovery Time Objective (RTO), MTPD, and their relationship with availability.
- Calculate data loss and recovery time from a hypothetical timeline.
- Conduct a Business Impact Analysis (BIA), identify dependencies, and rank workloads by impact level.
- Establish illustrative tiers and map each tier to an RPO/RTO approved by the business owner.
- Distinguish between backup, replication, high availability, and disaster recovery.
- Make a preliminary selection of cold/warm/hot strategies and Google Cloud building blocks per workload.
- Write a recovery plan, verify RPO/RTO through drills, and track residual risk.

> **Principle:** RPO and RTO are *target objectives*, not parameters automatically guaranteed by Google Cloud just because you enable a service. Only by performing test restores under appropriate scenarios, measuring duration, and reconciling data does the team have evidence of actual recovery capability.

## 1. What is RPO?

**Recovery Point Objective (RPO)** is the maximum time interval of data loss that the business can tolerate when a severe incident occurs.

If RPO = 15 minutes, the design must allow data to be recovered to a point in time no more than 15 minutes before the incident disrupted data writes. RPO describes the **maximum age of a recoverable data point**, not directly the number of records or monetary value lost.

~~~mermaid
flowchart LR
    A["10:00<br/>Last recovery point"]
    B["10:15<br/>Incident"]
    C["Post-incident<br/>Restore dataset"]
    A -->|"Potential data loss window: 15 minutes"| B
    B --> C
~~~

### 1.1. Example of calculating observed RPO

Suppose:

- 09:50:00: the most recent valid recovery point exists.
- 10:00:00: the system experiences an incident causing loss of all unprotected data.
- 10:30:00: the restoration completes.

Then:

\[
RPO_{\text{observed}} = 10{:}00 - 09{:}50 = 10\ \text{minutes}
\]

The restoration may complete 30 minutes after the incident, yet the RPO is still 10 minutes. The time spent waiting for the system to recover is counted under **RTO**, not RPO.

If during those 10 minutes the system processes an average of 50 orders/minute, the number of orders requiring reconciliation or at risk of loss according to a rough estimate is:

\[
50\ \text{orders/minute} \times 10\ \text{minutes} = 500\ \text{orders}
\]

The figure of 500 is an *estimate based on transaction rate*, not a guaranteed amount of data loss. Depending on replication, committed transactions, queues, replay capability, and reconciliation mechanisms, actual impact may differ.

### 1.2. What RPO does not prove

- RPO = 0 does **not** mean business logic errors will never happen.
- Having a backup every 15 minutes does **not automatically** guarantee a 15-minute RPO: jobs can run late, fail, be inconsistent, or fail to replicate to the recovery region in time.
- Near-real-time replication does **not necessarily** mean RPO equals 0: an asynchronous replica can lag and miss the final transactions.
- Backing up only the database does not prove the entire workload meets its RPO: attachments, queues, caches, search indexes, or external state may have different recovery points.

**RPO must be evaluated for critical business data across both the write path and dependent systems, not just for a single standalone backup job.**

## 2. What is RTO?

**Recovery Time Objective (RTO)** is the maximum outage duration that the business tolerates, measured from the moment the service stops meeting the agreed functional level until the service is restored and verified to be fit for operation.

For example: RTO = 60 minutes means the operations team must restore the service sufficiently to serve the business within one hour from when the outage began. "The server is running" does not necessarily mean RTO has been met if the database is not ready or users cannot sign in or place orders.

### 2.1. Which steps does RTO include?

~~~mermaid
flowchart LR
    F["Incident starts"] --> DET["Detect / identify"]
    DET --> DEC["Decide to activate DR"]
    DEC --> REST["Restore data and infrastructure"]
    REST --> VAL["Technical / business validation"]
    VAL --> TRA["Switch traffic / open service"]
    TRA --> OK["Service fit for operation"]
~~~

An RTO budget can be broken down as follows:

| Component | Illustrative target time |
|---|---:|
| Detection and triage | 5 minutes |
| Failover approval | 5 minutes |
| Infrastructure provisioning / data restoration | 25 minutes |
| Testing and verification | 15 minutes |
| Traffic/DNS/route cutover | 10 minutes |
| **Total** | **60 minutes** |

In a real incident, steps may overlap, but detection time, verification, or slow traffic cutover must not be silently omitted. Measurement must follow a consistent baseline approved by the business owner.

### 2.2. Observed RTO

Suppose users cannot place orders starting at 10:00, business smoke tests on the standby infrastructure PASS at 10:42, and traffic is reopened at 10:45. The observed RTO is **45 minutes**, not 42 minutes.

If the infrastructure team reports "instance Ready" at 10:20, yet the service still fails authentication until 10:45, 20 minutes cannot be claimed as the application-wide RTO.

## 3. RPO, RTO, availability, and related concepts

| Term | Question | Example |
|---|---|---|
| RPO | How much *data time* can be lost at most? | 15 minutes |
| RTO | How long can the system be down at most? | 1 hour |
| MTPD/MAO | Maximum outage before damage becomes unacceptable? | 4 hours |
| Availability SLO | Percentage of time the service can serve requests? | 99.9% monthly |
| SLA | Service commitment and legal/contractual terms? | Commitments, exclusions, liabilities, service credits |
| Backup retention | How long are recovery points kept? | 30 days |
| Data durability | Probability that data remains safely stored over time? | Property of the storage solution |
| Recovery consistency | Is restored data transactionally valid? | No orders missing line items |

**RTO should not exceed MTPD**, and typically needs buffer time for the business to verify operations and transition manual workarounds back to normal.

RPO, RTO, and availability are related, yet cannot substitute for one another. A system with high monthly uptime can still violate its RPO during severe data corruption; a system with good backups can still take hours to restore.

### 3.1. High Availability differs from Disaster Recovery

**High Availability (HA)** reduces disruption from localized component failures, such as a single zone or instance. **Disaster Recovery (DR)** prepares recovery when major failures happen: region loss, accidental deletion, ransomware, data corruption, widespread misconfiguration, or loss of operational capability.

| Scenario | Can HA help? | Is DR typically needed? |
|---|---|---|
| Single VM failure | Yes, if using an instance group/replica | Maybe not |
| Single zone failure | Yes, with regional/multi-zone design | Depends on severity |
| Entire region unavailable | Single-region HA is insufficient | Yes |
| Accidental data deletion | Replicas may propagate bad writes/deletes | Needs backup/PITR |
| Ransomware/credential compromise | Replicas may also be affected | Needs isolated/immutable backups and IAM recovery |
| Bad release causing all APIs to return 500 | Fast rollback may suffice | Needs scope-limiting runbook |
| Loss of key required to decrypt backups | HA does not solve this | Must design key and permission recovery |

Enabling multi-zone does not automatically create multi-region DR; enabling a cross-region replica also does not replace clean backups for recovering deleted or corrupted data.

## 4. Starting with Business Impact Analysis (BIA)

BIA helps determine priorities based on **business impact**, rather than on the engineering team's preference for a particular service.

### 4.1. BIA inputs

Each workload should be assessed across:

1. **Business function:** what does the system serve, and which activities stop when it fails?
2. **Revenue/financial:** revenue, penalty/compensation costs, manual labor costs, supply chain impact.
3. **Legal/compliance:** mandatory data retention, notification obligations, reporting deadlines, data residency.
4. **Customers:** how many users are affected, and how severely?
5. **Safety/operations:** does it affect human safety, access control, or fraud prevention?
6. **Data:** write rate, confirmed events, replay capability, and upstream source of truth.
7. **Timing:** does month-end, peak hours, nightly batch, or quarter-end differ from normal days?
8. **Dependencies:** identity systems, network, DNS, KMS, secrets, partner APIs, queues, databases.
9. **Manual workarounds:** if the system stops, can work continue via another process?
10. **Budget and operational capacity:** cost of maintaining standby capacity, on-call staff, automation maturity.

### 4.2. Interviewing business owners

Avoid simply asking "what RTO do you want?", because most business stakeholders will answer "as short as possible". Try questions tied to impact:

- If the system stops for 15 minutes, what happens? What about 1 hour, 4 hours, or 24 hours?
- Are there transactions already confirmed to customers that must never be lost?
- If 10 minutes of data are lost, can they be reconstructed from event logs, payment systems, or source batches?
- After the API comes back online, how long do staff need to verify balances or complete manual catch-up work?
- Which systems must be running first for this workload to return?
- What cost level is acceptable to reduce RTO from 8 hours to 1 hour?

### 4.3. Sample BIA table

| Workload | Impact after 1 hour | After 8 hours | After 24 hours | Is data replayable? | Owner |
|---|---|---|---|---|---|
| Checkout/Orders | Lost transactions, stalled orders | Major revenue and customer support impact | Unacceptable | Partially | Commerce Lead |
| Identity/SSO | Users cannot sign in | Many dependent systems paralyzed | Unacceptable | Not the primary issue | Security Lead |
| Analytics dashboard | Reports temporarily unavailable | Operations team loses visibility | Delayed reporting | Reprocessable | Data Lead |
| Reconciliation batch | Delay during normal hours | Risk of missing deadline | Depends on settlement schedule | Yes, if events/inputs remain | Finance Ops |
| Historical document archive | Minor impact | Minor impact | Some retrieval requests delayed | No if source files are lost | Records Lead |

**Sensitive time windows** must also be recorded: a reconciliation batch might be Tier 2 on normal days but Tier 1 on financial close days. Tier design may require profiles based on operational periods.

## 5. Choosing RPO/RTO from impact, not from service features

Decision process:

1. Determine MTPD from the maximum tolerable damage.
2. Set the **target RTO** lower than MTPD, leaving a buffer for customer communication, verification, and manual tasks.
3. Determine the value of newly written data: which transactions can be reconstructed, and which are legal records.
4. Set the **target RPO** from the maximum acceptable data loss.
5. Identify whether the workload must recover together with its dependent systems.
6. Propose at least two technical options with different cost/complexity profiles.
7. Have the business owner and risk/compliance owner sign off on the target levels.
8. Test the solution, measure actual RPO/RTO, and confirm any gaps.

### 5.1. Formula for quantifying data loss

If the average rate of new transaction creation is V (transactions/minute) and RPO is measured in M minutes:

\[
\text{Estimated transactions at risk} = V \times M
\]

For example, a checkout system creating 200 transactions/minute with a 5-minute target RPO:

\[
200 \times 5 = 1,000\ \text{transactions}
\]

One thousand transactions at risk may be unacceptable to the business. In that case, consider a lower RPO, durable event logs, idempotent replay, or a different replication/commit architecture. Do not claim an RPO of 0 without proving how confirmed transactions are preserved.

### 5.2. Estimated outage cost

~~~text
Outage cost ≈
  affected revenue/profit
  + emergency labor and operations
  + penalties/compensation
  + customer churn and reputational damage (hard to quantify)
~~~

This is an analytical framework, not a standard accounting formula. Avoid double-counting revenue and profit, or equating delayed revenue with permanently lost revenue.

## 6. Workload tiering: Tier 0, 1, 2, 3

There is no single default set of Tier 0–3 thresholds applicable to every company or published by Google Cloud as an SLA. The table below is only an **internal policy sample** for exercises. Each organization must define and approve its own thresholds.

| Illustrative tier | Impact level | Illustrative target RPO | Illustrative target RTO | Examples |
|---|---|---:|---:|---|
| Tier 0 – Mission critical | Outage causes lost transactions / widespread disruption with severe risk | ≤ 1 minute | ≤ 15 minutes | Payment systems or core identity with strict requirements |
| Tier 1 – Critical | Major impact on revenue/customers | ≤ 15 minutes | ≤ 1 hour | Orders API, scheduling, business transactions |
| Tier 2 – Essential | Temporary alternative operations exist | ≤ 4 hours | ≤ 8 hours | Internal admin tools, near-daily ETL |
| Tier 3 – Deferrable availability | Infrequent access, can wait | ≤ 24 hours | ≤ 72 hours | Historical archives, lab environments |

The thresholds above are **not achieved capabilities** of Cloud Run, Cloud SQL, Cloud Storage, or any specific solution. They are business objectives used to evaluate designs.

### 6.1. Tiering criteria

Choose a tier across multiple dimensions, not solely from requests/second:

| Criterion | Higher tier when | Lower tier when |
|---|---|---|
| Financial damage | Every minute of downtime causes significant loss | Low cost impact, deferrable |
| Data | Confirmed transactions cannot be recreated | Can be replayed from other sources |
| Legal/compliance | Violates critical obligations/deadlines | Flexible handling window |
| Affected users | Most customers and staff | Small group, non-urgent |
| Dependencies | Many critical workloads depend on it | Few dependent systems |
| Workaround | None | Proven manual process exists |
| Sensitive timing | Peak hours, period close, settlement | Batch jobs can be postponed |

**Tiers must be agreed upon by the business**, while engineering evaluates feasibility and cost. Do not choose Tier 0 merely because a system uses new technology.

### 6.2. Example scoring method

A 1–5 scoring matrix across four axes can be used, with illustrative weights for each axis:

| Axis | Illustrative weight |
|---|---:|
| Business and customer damage | 40% |
| Data loss / compliance risk | 30% |
| Dependency of other systems | 20% |
| Lack of alternative operational workaround | 10% |

~~~text
Risk score =
  0.40 × business_impact
+ 0.30 × data_compliance_impact
+ 0.20 × dependency_impact
+ 0.10 × workaround_absence
~~~

If Orders API scores 5, 4, 4, 4, then:

\[
0.4(5) + 0.3(4) + 0.2(4) + 0.1(4) = 4.4
\]

A score of 4.4 suggests high priority, but **does not automatically derive RPO/RTO**. The business owner must weigh time-based impact, replayability, and cost to finalize concrete targets. Internal scoring rules can be established, provided they are reviewed periodically.

## 7. Dependency tiers: when a lower-tier workload becomes a failure point for Tier 0

Workloads do not exist in isolation. A Checkout API may require IAM/SSO, DNS, secrets, a message broker, a database, a payment gateway, and VPC configuration.

~~~mermaid
flowchart TD
    CHECK["Checkout API<br/>Tier 1"] --> DB["Cloud SQL orders<br/>Tier 1"]
    CHECK --> ID["Identity / SSO<br/>Shared dependency"]
    CHECK --> SEC["Secret Manager + KMS"]
    CHECK --> NET["DNS / Load Balancer / VPC"]
    CHECK --> MQ["Pub/Sub order events"]
    MQ --> WORKER["Fulfillment worker<br/>Tier 2 if delayed processing is acceptable"]
~~~

If a lower-tier dependency is a **mandatory prerequisite** to recover checkout, that dependency's recovery target must be evaluated along the end-to-end recovery path. For instance, if login cannot work because SSO is down, the Orders API may be running yet still not count as recovered.

However, not every dependency must run before the service recovers. If email sending can be queued, the email system may have a longer RTO. Distinguish between:

- **Hard dependency:** without it, the core business flow cannot function.
- **Soft dependency:** without it, the service has a degraded mode, queue, cache, or catch-up processing.
- **Recovery dependency:** not in the normal request path, yet required for DR—for example Cloud KMS keys, Terraform state, backup vaults, DNS/IAM break-glass permissions.

A shared service may have to meet the **strictest target** among the hard dependencies it serves, or provide a verified fallback option.

## 8. Building a Workload Recovery Register

A register helps govern tiering and handoffs:

| Field | Example |
|---|---|
| Workload ID | orders-api-prod |
| Business owner | Commerce Lead |
| Technical owner | Platform Team |
| Function | Order placement and payment |
| Tier | Tier 1 |
| RPO target | 15 minutes |
| RTO target | 60 minutes |
| MTPD | 4 hours |
| Peak load | 500 requests/minute |
| Data stores | Cloud SQL PostgreSQL, Cloud Storage |
| Hard dependencies | IAM, DNS, VPC, Cloud SQL, Secret Manager |
| Threat scenarios | Zone/region outage, corruption, accidental deletion |
| DR pattern | Warm standby or approved option |
| Backup/replication | PITR + cross-region recovery plan |
| Runbook | Internal link or versioned document |
| Last drill / achieved RPO | Date, minutes, result |
| Last drill / achieved RTO | Date, minutes, result |
| Exception & owner | If target is not yet met |
| Review date | Next BIA review date |

Example YAML recording requirements (this is only a documentation template, **not a GCP manifest**):

~~~yaml
workload_id: orders-api-prod
service_name: orders-api
business_owner: commerce-lead
technical_owner: platform-team
classification:
  tier: 1
  rpo_target_minutes: 15
  rto_target_minutes: 60
  mtpd_minutes: 240
recovery_scope:
  scenarios:
    - regional_outage
    - database_corruption
    - accidental_deletion
  hard_dependencies:
    - cloud-sql-orders
    - runtime-identity
    - dns
    - kms-key
evidence:
  last_drill_date: null
  measured_rpo_minutes: null
  measured_rto_minutes: null
  approved_by: null
~~~

Note: an empty `measured_*` field means **there is no evidence yet**. Do not fill it in with the target value.

## 9. Distinguishing zone loss, region loss, and logical data corruption

RPO/RTO must be defined **per scenario**. An architecture may achieve a very low RTO for a single-zone machine failure while recovering slowly when an entire region has an outage.

| Scenario | Potential impact | What to check |
|---|---|---|
| VM/pod crash | Single instance stops running | Restart, autoscaling, health checks |
| Zone outage | Part of compute/storage in the region fails | Multi-zone deployment, regional HA |
| Region outage | Regional compute/network/database unavailable | Secondary region, data availability, DNS/routing |
| Accidental data deletion | Logical data is wrong while infrastructure stays up | Backup/PITR, versioning, deletion protection |
| Ransomware/compromised admin | Live data and backups affected together | IAM separation, immutable vault, recovery credentials |
| Bad deploy | Incompatible code/schema | Rollback/roll-forward, schema compatibility, backups |
| Third-party outage | External payment/SSO/email outage | Fallback, queue, degrade, contract/SLA |
| Cloud KMS key unavailable | Cannot decrypt data/backups when needed | Key location, IAM recovery, and cross-region plan |

A DR plan may have multiple targets: Tier 1 with RTO ≤15 minutes for a zone outage but ≤60 minutes for a region outage, if approved by the business. Exceptions must be stated explicitly in the SLA/SLO and runbook, rather than using a single number to mask all scenarios.

## 10. Cold, warm, and hot: three fundamental DR patterns

The Google Cloud Disaster Recovery Planning Guide describes three strategy groups: **cold, warm, hot**.

~~~mermaid
flowchart LR
    A["Cold<br/>Restore from backup<br/>Minimal standby resources"] --> B["Warm<br/>Partial infrastructure ready<br/>Data synchronized"]
    B --> C["Hot<br/>Infrastructure ready to serve<br/>Faster, more complex"]
~~~

| Pattern | Standby state | Qualitative expected RTO/RPO | Cost and complexity | Suitable for |
|---|---|---|---|---|
| Cold | Store backups/IaC, create or start resources on incident | Long RTO; RPO depends on backup | Lower, heavy restore steps | Tier 3, some Tier 2 |
| Warm | Partial infra/data replica ready, needs promote/scale/cutover | Moderate RTO; RPO depends on lag | Moderate | Tier 1/2 depending on targets |
| Hot | Multiple components actively running at DR site, fast routing/failover | Low RTO; RPO depends on replication/commit | High, complex | Strict Tier 0/1 |

**Hot does not mean RPO equals 0.** If both regions use asynchronous replication, transactions not yet replicated to the secondary can still be lost. With active-active, conflicts, ordering, idempotency, and consistency must be solved; you cannot simply deploy two Cloud Run instances and call it active-active DR.

### 10.1. Questions when selecting a pattern

- Does data change continuously, or is it imported only once a day?
- Are capacity and quota available in the standby region?
- How fast can web/app layers be recreated with IaC?
- Does the database require a full restore, or is a replica available to promote?
- Are network, secrets, IAM, DNS, and certificates recovered in sync?
- Is the latest data verified before allowing the system to accept writes?
- Who has authority to trigger the runbook when the primary region is unreachable?

The design must account for **idle standby cost** and **drill operational cost**, not just backup storage fees.

## 11. Mapping Google Cloud building blocks

| Workload/data type | Available tools | Risks to note |
|---|---|---|
| Compute Engine disks | Snapshots, machine images, Backup and DR, regional disk where suitable | Snapshots are not app-consistent by default; VM/network restore takes time |
| Cloud SQL | Automated backups, PITR, HA, cross-region replica, enhanced backup | Single-region HA differs from cross-region DR; PITR and replicas serve different scenarios |
| GKE | Regional cluster, Backup for GKE, IaC, image registry | Backups do not create the target cluster; Kubernetes object/PVC restores must be tested |
| Cloud Run | Container images, IaC, multi-region deployment, LB routing | Stateless services rebuild easily, but secrets, network, and databases do not auto-recover |
| Cloud Storage | Soft delete, Object Versioning, dual-/multi-region, turbo replication | Replication is asynchronous; versioning does not protect against deleting the entire bucket |
| BigQuery | Time travel, fail-safe, table snapshots, cross-region replication as needed | Retention periods and recovery capabilities vary by feature |
| Terraform/state | GCS backend with versioning, IAM, procedural config exports | State and credentials can be recovery dependencies |
| Secret Manager / Cloud KMS | Replication/location, secret versions, key IAM and access recovery | Without permissions/keys to decrypt, backups are unusable |
| Audit logs | Cloud Logging buckets, sinks, retention | Logs are needed for investigation immediately when the production project fails |

Features have conditions regarding region, edition, database engine, tier, or support status. Before finalizing an option, check current documentation and execute a proof-of-recovery on the specific workload.

### 11.1. Cloud SQL: backup, PITR, and HA

- **Automated backup** stores recovery points on a schedule with retention; data is restored to the state at backup time.
- **PITR** uses backups/transaction logs to recover near a point in time prior to a logical error; in Cloud SQL PostgreSQL, PITR creates a **new instance**, requiring connection/route reconfiguration and data verification.
- **Regional HA** enables failover between zones within the same region; it does not protect against a full region outage.
- **Cross-region replica** can help build a regional DR strategy, but replication lag and promotion must be observed; a read replica is not a clean historical backup.

Do not assign a fixed RTO to Cloud SQL because PITR/restore time varies by data volume, quota, configuration, network, and validation steps. Each edition and instance creation method may have different PITR defaults; **verify the actual configuration**, rather than assuming from the service name.

### 11.2. Cloud Storage: durability does not mean zero RPO

Regional Cloud Storage stores data redundantly across multiple zones within the same region. Dual-region and multi-region distribute data across separate geographic regions, though cross-region replication is asynchronous by default.

In dual-region setups, **turbo replication** can support an objective of replicating new objects to the second region within 15 minutes per service characteristics. That does not prove the entire Orders API system has a 15-minute RPO: databases, queues, and metadata still have their own limits.

**Soft delete** helps recover deleted objects/buckets within the configured retention window. **Object Versioning** retains noncurrent versions to restore prior object states; this feature does not protect against deleting the bucket itself. Choose based on the threat model and manage lifecycle/cost.

### 11.3. Backup for GKE

Backup for GKE provides BackupPlan/RestorePlan to protect Kubernetes resource manifests and selected volumes as configured. Restores can target another cluster, but the **target cluster must exist** and have the required agent/add-on. Secrets, cluster-scoped resources, external cluster data, and namespace security must be verified in testing.

Do not assume Backup for GKE automatically restores external Cloud SQL databases, DNS, IAM, or all infrastructure resources. Use IaC and dedicated backup/restore mechanisms for hard dependencies.

### 11.4. Backup and DR service

Backup and DR is a service that manages policies, backup schedules, and recovery across supported workloads. Backup vaults provide WORM-based immutability/indelibility controls to reduce the risk of backup deletion or modification.

Immutability settings must be designed alongside retention, RBAC, and break-glass access. Do not treat an immutable backup vault as sufficient if data was encrypted/corrupted **before the backup was taken** or if recovery keys/identities are lost.

## 12. Tiering example in an e-commerce system

An e-commerce system comprises a frontend, checkout, queues, warehouse, analytics, and an invoice archive. A BIA might produce an illustrative profile:

| Workload | Tier | Target RPO | Target RTO | Preliminary solution |
|---|---|---|---|---|
| Checkout/Orders DB | Tier 1 | ≤ 5 minutes | ≤ 60 minutes | PITR + tested cross-region DR/replication |
| Customer identity | Tier 1 | ≤ 15 minutes | ≤ 60 minutes | Redundant identity path and credential recovery |
| Stateless web frontend | Tier 1 | N/A for versioned images | ≤ 30 minutes | Multi-region image deploy and traffic routing |
| Fulfillment events | Tier 1 | ≤ 15 minutes | ≤ 60 minutes | Durable queue/replay, idempotency |
| Analytics reporting | Tier 2 | ≤ 4 hours | ≤ 8 hours | Backup/export and reprocessing |
| End-of-day batch reports | Tier 2, or Tier 1 during close window | ≤ 4 hours | ≤ 8 hours or shorter | Snapshot and batch replay |
| Invoice archive | Tier 3 for access; strict retention for data | ≤ 24 hours or zero loss per legal obligation | ≤ 72 hours | Retention/immutability/soft delete + restore |

**N/A for a stateless frontend** applies only to **runtime state reconstructible** from images/IaC. If the frontend stores user uploads, sessions, or non-reconstructible cache, that data has its own RPO.

This example also shows that **availability tier** and **data preservation level** must sometimes be evaluated separately. An invoice archive does not need to be online within 15 minutes, yet legal records may not permit losing even a single file.

## 13. Calculating RPO/RTO for an Orders API scenario

Suppose the business approves:

- Orders API and PostgreSQL have a 5-minute target RPO and 60-minute target RTO.
- Peak transaction rate: 120 transactions/minute.
- An outage impacts the database and Cloud Run app starting at 14:00.
- The restored and reconciled recovery point has a timestamp of 13:56.
- 14:08: DR decision finalized.
- 14:32: new database ready.
- 14:43: backend business checks PASS.
- 14:49: frontend opens traffic and users successfully place orders.

Measured results:

\[
RPO_{\text{measured}} = 14{:}00 - 13{:}56 = 4\ \text{minutes}
\]

\[
RTO_{\text{measured}} = 14{:}49 - 14{:}00 = 49\ \text{minutes}
\]

In terms of timing, this test **meets** the 5-minute and 60-minute targets, but only holds if the recovery point is truly consistent and order counts reconcile accurately. Transactions at risk requiring reconciliation based on average rate:

\[
120 \times 4 = 480\ \text{transactions}
\]

If the business cannot accept losing any confirmed transaction, even with a time-based RPO of 5 minutes, the design needs durable order events or reconciliation/replay. This demonstrates that a time-based RPO alone cannot replace transactional integrity criteria.

### 13.1. When only daily backups exist

If backups run daily at 01:00 and an incident occurs at 23:45, the nearest recovery point can be 22 hours and 45 minutes old. This design fails a 5-minute RPO, even if the restore operation itself is fast.

### 13.2. When PITR can recover close to the failure time

PITR can provide a closer recovery point than daily backups, yet transaction log availability, consistency, and new instance creation capability must still be verified. Actual RPO comes from the **point that can be successfully restored**, not merely from an enabled "PITR" flag.

## 14. End-to-end RTO is the critical path, not the sum of individual machines

In a multi-component system, some steps run in parallel; the workload's overall RTO is determined by the **critical path** from incident start to business usability.

~~~mermaid
flowchart TD
    INC["Incident"] --> DEC["Declare DR"]
    DEC --> DATA["Restore / promote database"]
    DEC --> APP["Deploy app in standby region"]
    DEC --> IAM["Verify IAM / Secret / KMS"]
    DATA --> INT["Integration validation"]
    APP --> INT
    IAM --> INT
    INT --> TRA["Switch traffic"]
    TRA --> BIZ["Business smoke test"]
~~~

For example, the database takes 45 minutes, app deployment takes 15 minutes, IAM takes 10 minutes, and these steps begin simultaneously after the DR decision. If integration validation takes 10 minutes, traffic cutover 5 minutes, and business testing 5 minutes, the RTO is not simply 45+15+10+10+5+5 = 90 minutes. When branches run in parallel, the critical path may be 45+10+5+5 plus detection/decision time.

Conversely, if the app cannot be deployed before the DB exists or IAM requires manual provisioning post-restore, RTO may exceed plan. Draw a dependency graph with duration and owner per node.

## 15. Designing a recovery plan from a Tier

A recovery plan can follow this sequence:

1. **Select scenario:** zone loss, region loss, data corruption, ransomware, misconfiguration, or partner failure.
2. **Select targets:** RPO/RTO per scenario based on BIA.
3. **Build inventory:** data, applications, hard dependencies, IAM, DNS, keys, and network.
4. **Select pattern:** cold, warm, hot, or a hybrid per component.
5. **Design data protection:** backup frequency, log retention, replication, restore point, consistency.
6. **Design compute recovery:** images, IaC, capacity/quota in DR region, deployment.
7. **Design permissions and network:** recovery identities, KMS/secret replication, certificates, LB routing.
8. **Write runbook:** decision makers, procedures, checklists, rollback/failback.
9. **Add observability:** lag, backup success, restore time, health, and traffic.
10. **Drill and measure:** capture actual RPO/RTO, data verification, owner sign-off.
11. **Record exceptions:** unmet targets, residual impact, remediation plan, and deadline.

### 15.1. Essential information in a runbook

| Field | Content |
|---|---|
| Incident trigger | Conditions to activate DR, who may declare |
| Recovery scope | Which services and data are recovered |
| Authority | Incident commander, DBA, network lead, business owner |
| Target | RPO/RTO and RTO checkpoints |
| Prerequisites | IAM, quota, backups, credentials, KMS, images, DNS |
| Steps | Conditional procedures and tested commands |
| Validation | Data consistency, API, auth, sample transactions |
| Traffic cutover | DNS/LB/routing, exact moment primary changes |
| Rollback/failback | Conditions and how to prevent split-brain |
| Communication | Internal, customer, and legal notifications |
| Evidence | Event timeline, logs, measured results, sign-off |

Do not store the entire runbook solely inside the region/project that could suffer an outage. Maintain a separate copy and emergency access aligned with security policy.

## 16. DR drills: evidence matters more than enabling backups

A system with hourly backups that has never been restored **has not proven** its RTO or data usability.

### 16.1. Test matrix

| Drill | Example frequency | Criteria |
|---|---|---|
| Restore an accidentally deleted object | Monthly | Correct object generation and metadata |
| Point-in-time Cloud SQL restore | Quarterly | Correct schema/data, restored within window |
| Restore a GKE namespace | Quarterly | Manifests/PVC/app functional |
| Deploy Cloud Run in standby region | Quarterly | Correct image, IAM, secrets, VPC |
| Database replica promotion | Per approved schedule | Measure lag, write fencing, business checks |
| Region outage tabletop | Quarterly | Runbook, owners, quota |
| Full end-to-end DR | At least per risk governance cycle | Measured RPO/RTO, sign-off |

Frequencies in the table are illustrative. Tier 0/1 workloads may require more frequent testing and re-testing after major architectural changes.

### 16.2. Procedure for measuring actual RPO

1. Generate a test dataset with event IDs, commit timestamps, and checksums.
2. Perform controlled writes on the source system close to the simulated incident time.
3. Lock the incident timestamp T_incident.
4. Restore following the runbook without changing targets mid-drill unless necessary.
5. Inspect the latest ID/timestamp that was **committed and remains consistent**.
6. Compute actual RPO = T_incident - latest recoverable committed timestamp.
7. Compare against target and record items needing reconciliation.

When using async replication, do not treat "reported lag near 0" as a substitute for verifying the actual transaction boundary on the restored copy.

### 16.3. Procedure for measuring actual RTO

1. Record the timestamp when the workload stops meeting its business SLO.
2. Record timestamps for detection, DR declaration, restore start, data ready, and app ready.
3. Record technical smoke test and business validation results.
4. Cut over traffic and perform final functional checks.
5. Record the timestamp when users can complete the primary business flow.
6. Compute actual RTO from outage start to business function restoration.
7. Compare against target, attribute root causes of delays, and log action items.

Keep the event timeline in UTC/ISO 8601 timestamps to avoid timezone confusion across coordinating teams or regions.

## 17. Distinguishing disaster recovery and business data reconciliation

A system can meet its RTO while still having inconsistent business data. For example, the Orders API reopens in 30 minutes, yet 200 orders that already sent confirmation emails do not exist in the new database.

Therefore, DR acceptance criteria include:

- **Availability:** API or website is serving again.
- **Integrity:** database, files, and event logs are consistent.
- **Correctness:** core business operations execute properly.
- **Security:** IAM, encryption, networking, and auditing are not degraded after failover.
- **Financial reconciliation:** zero lost transactions, or an approved reconciliation/compensation ledger exists.
- **Recoverability:** new backup/DR pipelines continue operating after failover.

Once the application has written to the secondary, do not simply switch traffic back to the old primary. A **failback** strategy and source-of-truth determination are required to prevent split-brain.

## 18. Ransomware and immutable backups

DR is not only for natural disasters or infrastructure failures. Accidental deletion, compromised admin accounts, or ransomware often alter or delete online copies as well.

Key protective layers:

1. Backups do not reside in the same permission boundary as application runtime.
2. Enable retention/immutability as required in Backup and DR backup vaults or an appropriate solution.
3. Design least privilege, IAM Conditions, and audit logs for backup deletion/modification actions.
4. Protect KMS keys, secrets, and break-glass identities; manage key location if cross-region restore is required.
5. Maintain multiple recovery points, not just a single latest copy.
6. Scan for malware/corruption and identify a clean point in time before restoring.
7. Store test evidence and runbooks in a location accessible when the primary project fails.

**Replicating corrupted data very quickly is not successful DR.** Both working copies and clean historical recovery points are required.

## 19. Cost and trade-offs of strict targets

Low RPO/RTO typically requires:

- Frequent or synchronous replication per an acceptable architecture.
- Running standby compute or fast provisioning capability.
- Quota and capacity in the standby region.
- Backup retention, data transfer, storage, and monitoring.
- Automation, failover scripts, tests, and on-call staffing.
- More complex consistency, fencing, and failback design.

| Cost factor | Cold | Warm | Hot |
|---|---|---|---|
| Standby compute | Low | Partial | High |
| Replication/data transfer | Backup-dependent | Continuous or frequent | Usually continuous |
| Automation | Needed to reduce RTO | Recommended | Nearly mandatory |
| Failover testing | Required | Required | Required and complex |
| Target recovery time | Usually long | Moderate | Usually short |

For Tier 3, investing in dual-region active-active may not be justified compared to cold backups + IaC. For Tier 0, relying solely on daily snapshots generally fails requirements. Economic decisions should compare **DR solution cost** against **expected loss when the system fails to recover in time**, without overlooking non-monetary data protection obligations.

## 20. Common mistakes when defining RPO/RTO

| Mistake | Why it is dangerous | How to fix |
|---|---|---|
| Choosing RPO=0/RTO=0 for every workload | Cost and complexity can be unrealistic | Conduct BIA, define limits and trade-offs |
| Using backup frequency as committed RPO | Backups can fail/lag, restores untested | Measure actual recoverable point |
| Measuring only new VM creation time | Ignores detection, DB restore, IAM, smoke tests, traffic | Measure end-to-end RTO |
| Calling regional HA multi-region DR | A region outage can still stop the service | Design failure domains per scenario |
| Treating async replicas as backups | Accidental deletes/ransomware propagate to replicas | Historical backups and immutability |
| Not tiering IAM/DNS/KMS | DR app fails due to missing permissions/keys | Treat them as recovery dependencies |
| Engineering choosing tiers alone | Does not reflect business damage | Business owner approval |
| RTO smaller than measured restore time | Unrealistic target | Change pattern or renegotiate target |
| Skipping business transaction checks | API is healthy but data is wrong | Reconciliation and sign-off |
| No DR owner | Nobody dares promote/route production | Clear runbook and decision authority |
| Not checking capacity in DR region | Failover hits quota/capacity blocks | Quota reviews and capacity reservations where appropriate |
| Ignoring failback | Two primaries accept writes concurrently | Fencing and reconciliation before switchback |
| Failing to update tiers as workloads evolve | Targets become outdated after scaling or business shifts | Periodic BIA reviews |

## 21. Lab exercise: tiering four workloads

Suppose an e-commerce company operates:

- **Orders API:** 100–300 orders/minute; every confirmed order must be processed accurately.
- **Identity service:** most APIs require login tokens; fallback exists for some routes, but not all.
- **Analytics ETL:** ingests data from orders, replayable within the day.
- **Archive invoices:** infrequently accessed, but invoices must be retained for statutory periods.

### Task 1: complete the BIA

For each workload, fill in impact after 15 minutes, 1 hour, 8 hours, and 24 hours; workaround availability; replayability; dependencies; and owner.

### Task 2: propose tiers

An initial classification might look like:

| Workload | Reference tier | Notes |
|---|---|---|
| Orders API | Tier 1 | RPO may need to be stricter if zero order loss is required |
| Identity | Tier 1 | Hard dependency for many services; consider Tier 0 if enterprise-wide |
| Analytics ETL | Tier 2 | RPO can be longer because it is replayable |
| Archive invoices | Tier 3 for access; legal data protection | Do not equate slow access with permission to lose documents |

### Task 3: select patterns

For each workload, propose cold/warm/hot, GCP building blocks, estimated cost drivers, and a drill plan. Do not select solely by tier: inspect workload characteristics and the data needing protection.

### Task 4: simulate an incident

Simulate Orders API going down at 13:00, with the nearest consistent recovery point at 12:58, and the API serving again with business smoke tests PASSing at 13:42.

\[
RPO_{\text{measured}} = 2\ \text{minutes}, \qquad
RTO_{\text{measured}} = 42\ \text{minutes}
\]

If targets are RPO ≤5 minutes and RTO ≤60 minutes, this simulation meets both metrics, provided consistency was verified. Save the drill record and open action items if any dependencies remain untested.

## 22. DR policy approval checklist

- [ ] Every workload has a business owner and technical owner.
- [ ] BIA assesses time-based impact and critical time windows.
- [ ] Clear RPO, RTO, and MTPD targets exist with formal sign-off.
- [ ] Tiering is documented as internal policy, not confused with GCP SLAs.
- [ ] Data inventory, dependency graph, and recovery dependencies exist.
- [ ] Each failure scenario has an appropriate recovery scope and target.
- [ ] HA, backup, replication, and DR are distinguished in the architecture.
- [ ] Cold/warm/hot selection is based on requirements, feasibility, and cost.
- [ ] Cloud SQL PITR/backups are enabled and verified against actual edition/config.
- [ ] Compute Engine/GKE/Cloud Run/Cloud Storage each have dedicated recovery paths.
- [ ] Secrets, IAM, KMS, DNS, load balancers, networking, and quotas are factored into RTO.
- [ ] Backups are protected against accidental deletion and ransomware.
- [ ] Restore tests and test data validation are performed, not just backup job success checks.
- [ ] Actual RPO/RTO, data integrity, and business outcomes are measured after drills.
- [ ] A failback procedure exists that prevents split-brain or transaction loss.
- [ ] Unmet targets are never reported as met; exceptions have an owner and deadline.
- [ ] Budget, alerting, and a BIA/DR plan review cycle are established.

## 23. Self-check questions

**1. How do a 15-minute RPO and a 1-hour RTO differ?**

A 15-minute RPO limits the age of recoverable data at the time of an incident. A 1-hour RTO limits the downtime until business operations resume.

**2. If backups run every 30 minutes, is RPO = 30 minutes guaranteed?**

No. Backups can be delayed, fail, be inconsistent, or be unusable at the recovery site. The actual recovery point must be verified after restore.

**3. Why might a Tier 3 system still require very strict data protection?**

The system may not need to be online immediately, yet it stores invoices, records, or legally mandated data. A long RTO does not imply permission to lose data.

**4. What is the difference between HA and DR?**

HA typically reduces downtime from component failures such as VMs or zones. DR covers larger scenarios like region loss, data corruption, or ransomware, requiring the ability to recover data and business operations.

**5. Why does a Cloud SQL cross-region replica not replace PITR/backups?**

Replicas can propagate bad changes or accidental deletions. PITR/backups provide historical recovery points to revert before data was corrupted.

**6. To measure RTO accurately, when should the clock stop?**

When users or core business flows can operate again, after data, auth, dependencies, and traffic are verified—not simply when a VM becomes Ready.

**7. Why can KMS, IAM, and DNS affect the Orders API tier?**

These are hard or recovery dependencies. Without keys, permissions, or routing, Orders cannot function even after containers and databases are restored.

**8. Does near-zero RPO always require active-active?**

Not necessarily. Transactions, consistency, replication, and replayability must be analyzed. Active-active does not automatically guarantee zero loss and can increase conflict and failback complexity.

## 24. References

- [Google Cloud Architecture Center: Disaster recovery planning guide](https://cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Disaster recovery building blocks](https://cloud.google.com/architecture/dr-scenarios-building-blocks)
- [Disaster recovery scenarios for applications](https://cloud.google.com/architecture/dr-scenarios-applications)
- [Disaster recovery scenarios for data](https://cloud.google.com/architecture/dr-scenarios-data)
- [Cloud SQL for PostgreSQL: Backup and recovery overview](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL for PostgreSQL: Restore an instance](https://cloud.google.com/sql/docs/postgres/backup-recovery/restore)
- [Cloud SQL for PostgreSQL: Configure point-in-time recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/configure-pitr)
- [Cloud SQL for PostgreSQL: Perform point-in-time recovery](https://cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Google Cloud Backup and DR overview](https://cloud.google.com/backup-disaster-recovery/docs/concepts/backup-dr)
- [Backup for GKE overview](https://cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Compute Engine: About disk snapshots](https://cloud.google.com/compute/docs/disks/snapshots)
- [Cloud Storage: Availability and durability](https://cloud.google.com/storage/docs/availability-durability)
- [Cloud Storage: Object Versioning](https://cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://cloud.google.com/storage/docs/soft-delete)
