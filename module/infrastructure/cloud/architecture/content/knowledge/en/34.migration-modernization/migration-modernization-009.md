# Decommissioning Legacy Systems and Handling Remaining Data

## 1. Why Does Migration Not End When the New System Runs Smoothly?

In a **migration and modernization** program, moving an application to the cloud or transitioning to a new architecture solves only half the problem. The remaining half is **decommissioning/retirement** of the legacy system and handling leftover data, links, resources, and operational obligations. Skipping this step can leave an organization paying for two systems, maintaining unpatched security exposures, running unowned integrations, or losing audit-required data.

For example, an enterprise replaces an on-premises order management application with a cloud service. Users now operate on the new application, yet the legacy system still holds:

- A database containing years of order history and invoices.
- A scheduled month-end reporting job and a quarterly integration.
- Backups, snapshots, CSV exports, and logs containing personal data.
- Domains, certificates, service accounts, API keys, VPN links, and monitoring servers.
- Retention obligations for certain records under contracts or regulations.

Shutting down servers immediately could drop the quarterly job or prevent users from retrieving past invoices. Keeping the entire system running indefinitely creates unnecessary cost and risk. A cloud architect must design the **post-migration target state**: which capabilities moved to the new system, which data is still needed, where it lives, how it is retrieved, who owns it, and when it can be safely deleted.

> **Principle:** A system is truly retired only when its capabilities have been replaced or intentionally terminated, dependencies have been resolved, remaining data has an explicit disposition, and completion evidence is preserved.

## 2. Distinguishing States and Decommissioning Scope

Do not use the following terms interchangeably:

| State | Meaning | Key Consideration |
|---|---|---|
| **Cutover** | Shifting primary traffic or business operations to the new system | The legacy system may still receive events, run background jobs, or retain data |
| **Read-only** | Stopping new writes while allowing reads during transition | Still requires access management, patching, and monitoring |
| **Quarantine / isolated** | Isolating the legacy system from production flows while preserving controlled recovery | Isolation does not replace data governance and retention policies |
| **Decommission** | Stopping operations and dismantling associated infrastructure, links, and accounts | Execute only after verifying zero remaining dependencies |
| **Data disposition** | Moving each dataset to its decided state: migrate, archive, retain, anonymize, or delete | May continue even after compute has been decommissioned |

Decommissioning scope extends beyond VMs or containers. Cover **compute, networking, data, identities and access, encryption keys, integrations, operational tooling, costs, and business processes**.

### 2.1. Three Questions to Answer

1. **Who or what still depends on the legacy system?** Users, APIs, batch jobs, webhooks, reporting systems, partners, disaster recovery environments, and infrequent cycles can all be dependencies.
2. **What value or obligations does the remaining data carry?** Transactional data, legal records, personal data, audit logs, caches, derived copies, and backups are not handled identically.
3. **How do we prove it is safe to shut down or delete?** Auditable metrics and evidence are required, never assumptions like “nobody uses it anymore.”

## 3. Surveying the Legacy System and Mapping Dependencies

Decommissioning starts with **inventory** and **dependency mapping**. For each asset, identify the business owner, technical owner, environment, criticality, retention window, and actual usage status.

| Asset Group | Items to Inventory | Risk If Missed |
|---|---|---|
| Compute | VMs, physical servers, containers, job schedulers, functions, agents, licenses | Silent background tasks keep running; ongoing cost or business errors |
| Network & entry points | DNS, load balancers, IPs, NAT, firewalls, VPNs, private endpoints, certificates | Legacy clients keep calling or unmaintained endpoints remain exposed |
| Database & storage | Tables, schemas, files, objects, volumes, snapshots, replicas, search indexes | Data loss, lingering sensitive data, prolonged storage fees |
| Messaging & integrations | Queues, topics, webhooks, ETL/ELT, CDC, SFTP, API contracts | Lost events, duplicate processing, broken downstream data feeds |
| Identity & secrets | IAM roles, service accounts, tokens, API keys, SSH keys, KMS keys | Unowned access paths, leaks, or inability to decrypt archives |
| Operations | Backups, monitoring, logs, alerts, CMDB, runbooks, DR plans | False alarms, recovering the wrong system, missing audit trail |
| Business & vendors | Reports, approval workflows, partner integrations, support contracts | Accidentally breaching obligations or elevating operational risk |

**Verification sources should combine:** architecture diagrams, asset inventories, deployment code, scheduler configs, access logs, network flow logs, metrics, DB queries, report catalogs, contracts, and business owner interviews. Short-term traffic observation misses monthly, quarterly, or annual processes; cross-check business calendars and integration contracts.

### 3.1. Establishing the Post-Cutover “System of Record”

Explicitly confirm which system is the **system of record** for each entity such as customers, orders, invoices, and inventory. If the legacy system accepts writes while the new system also writes, data will diverge:

- If **write authority moved to the new system**: lock or block legacy write paths, drain pending events, and verify zero active writers remain.
- If **temporary parallel run is required**: specify sync direction, conflict handling, idempotency, event ordering, and parallel-run exit criteria.
- If **a business capability is not being replaced**: reassign it to a designated system or record an owner-approved termination decision.

The diagram below shows a common target state after migrating a monolith to cloud services:

~~~mermaid
flowchart LR
    U[Users and partners] --> E[New DNS / API gateway]
    E --> N[New cloud application]
    N --> D[(Operational database)]
    N --> Q[New queue / event bus]
    O[Legacy application] -. Writes stopped .-> D
    O --> H[Historical data store]
    H --> R[Controlled retrieval]
    O -. Decommission post-acceptance .-> X[Shut down compute, network, identities]
    B[(Old backups / snapshots)] --> P{Classification and retention limits}
    P --> H
    P --> Z[Delete per policy]
~~~

**Note:** The arrow from the legacy application to the historical store represents a one-time export/transfer before decommissioning, not a sync pipeline kept forever. The historical store needs retrieval mechanisms independent of the legacy app if the goal is retiring that app.

## 4. Classifying and Deciding the Fate of Remaining Data

No single handling rule fits all data. Every dataset must carry an **owner, security classification, usage purpose, storage location, retention period and legal basis, dependencies, retrieval method, and end-of-life action**.

### 4.1. Five Disposition Paths

| Decision | When to Choose | Implementation | Key Trade-Offs |
|---|---|---|---|
| **Migrate** (move to new system) | Still active in daily operations or needed for online queries | Schema conversion, record reconciliation, load into target store | Conversion, testing, and hot-data operating costs |
| **Archive** (long-term retention) | Rarely accessed yet still needed for lookup, audit, or reconciliation | Export in durable format, encrypt, store in appropriate tier, build retrieval path | Cheaper than running the legacy app, though retrieval has higher latency |
| **Retain in place temporarily** (time-bounded hold) | Unresolved dependencies, disputes, or recovery conditions remain | Isolate, minimize access, set review date and owner | Ongoing cost/security exposure; requires a strict deadline |
| **Transform / anonymize** | Only statistical analytics needed, no personal identification required | Aggregate, strip identifiers, or apply vetted anonymization methods | Detail loss; pseudonymized data may still count as personal data |
| **Delete** | No remaining business need, retention expired, and no legal hold | Execute controlled deletion including copies, logs, snapshots, backups | Potentially irreversible; requires evidence and approval |

**Never infer retention periods from technology type.** An invoice table, access log, or attachment may face different mandates depending on jurisdiction, contracts, processing purpose, and company policy. Legal, security, and data owners must confirm applicable policies. “Keep it just in case” is not a complete retention policy.

### 4.2. Data Decision Matrix

| Order Management Data | Illustrative Handling | Mandatory Checkpoints |
|---|---|---|
| Open orders, inventory, active transactions | Migrate to the new database | Can continue processing with zero lost state and zero dual-writes |
| Closed order history | Partial migrate or archive | Authorized users can still look up and reconcile records |
| Invoices, vouchers, contracts | Archive per approved schedule and retention rules | Integrity preserved, decryptable/readable, access controlled |
| Temporary CSV exports, rebuildable caches | Delete once unneeded and free of retention holds | Zero jobs or systems still depend on them |
| Logs containing personal data | Retain/delete per purpose, horizon, and log policy | Do not retain indefinitely merely because logging is easy |
| DB replicas, snapshots, backups | Evaluate each type and cycle separately | Do not confuse backups with searchable archives |
| Datasets under legal hold | Hold and restrict access; defer deletion | Hold decision recorded, scope clear, named person to release hold |
| Encryption keys used for archives | Retain and manage lifecycle long enough to read held data | Never disable or delete keys before the data requiring decryption |

### 4.3. Data Copies and Deletion Challenges

Primary tables are rarely the only place data exists. Copies may live in **replicas, snapshots, database dumps, staging tables, caches, search indexes, object versions, CDNs, dead-letter queues, file exports, logs, partner-sent data, and DR copies**.

When deletion is required, architects must scope every copy and verify what each platform supports. Immutable backups may disallow deleting a single record immediately; in that case, design backup expiration windows, restrict restores, re-apply deletion requests if restored, and document limits per legal requirements. Never claim that deleting a row in a database removes data from the entire ecosystem.

**Crypto-erasure** (destroying keys to render encrypted data unreadable) can work in some architectures, provided key scoping is exact, no plaintext copies or differently keyed copies exist, and retention rules are respected. Never delete a key shared with data that must still be retained.

## 5. Designing an Independent Historical Archive

If data must be kept without operating the legacy application, design a **historical archive** accessible independently of retired servers or databases.

A common approach:

1. Export data from the legacy source at a controlled point; select complete datasets by business criteria.
2. Standardize formats and schemas: CSV/Parquet/JSON for structured data as appropriate; PDF and original formats for documents where needed.
3. Generate metadata: schema version, source, export timestamp, record count, checksums, business linking keys, retention policy, owner.
4. Encrypt in transit and at rest; choose storage region, access controls, keys, and storage tier per requirements.
5. Provide lookup/retrieval: an interface for authorized staff, catalog queries, or controlled data-export workflows.
6. Test retrieval and integrity with representative business samples before shutting down the legacy source.

Archive storage choices directly affect **cost, retrieval latency, and availability**:

| Design | Best Fit | Constraints to Account For |
|---|---|---|
| Managed read-only database | Frequent interactive queries, complex relationships | Higher compute and operational cost than object storage |
| Object storage + catalog/query | Large volumes, infrequent lookup/reconciliation | Must manage schemas, partitions, data-level permissions, retrieval workflow |
| Archive / deep archive tiers | Rarely accessed, tolerates long restore times | Retrieval fees, restore lead time, minimum storage duration per service |
| Dedicated records management app | Approval flows, search, legal evidence chains | Vendor lock-in and service contract dependencies |

**Archives differ from backups.** Backups primarily restore a system state after an incident; archives preserve and retrieve historical data per policy, typically using independent formats, permissions, and indexes. Never treat backup existence as proof users can search historical records.

### 5.1. Reconciling Data During Migration or Archival

Compare **quantitatively** (record counts, total transaction value, distribution by date/status) and **qualitatively** (business rules, relationships, formats, access controls). Hashes/checksums verify artifact or normalized-dataset integrity, yet do not prove two schemas preserve equivalent business semantics.

Example read query to reconcile order data (illustrative PostgreSQL syntax):

~~~sql
SELECT
    DATE(created_at) AS order_date,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= :start_time
  AND created_at < :end_time
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
~~~

Run equivalent queries on source and target at the same **locked data watermark**; explain any legitimate variances from schema conversions, currencies, time zones, or rounding rules. For high-precision datasets, add ID-level checks, foreign-key checks, targeted sampling, and post-cutover totals verification.

### 5.2. Controlling Retention and Access

- **Retention:** define the trigger event (creation date, contract close, transaction completion...), retention duration, calculation method, and expiration action. Use lifecycle rules where compatible; manage exceptions and legal holds separately.
- **Access:** enforce least privilege, role-based access by record group and purpose, and audit logging of retrievals. Historical data read access should not belong automatically to every app administrator.
- **Encryption:** define key ownership, rotation/revocation procedures, and decryptability across the entire retention horizon.
- **Integrity:** store checksums, version metadata, and import/export logs; periodically verify data readability and retrieval workflow health.
- **Location & transfer:** evaluate data residency, cross-border transfers, processors, and network paths before selecting archive locations.
- **End of life:** once retention expires with zero holds, trigger an approved disposition task, check all copies, and archive completion evidence.

## 6. Gate-Based Decommissioning Process

An auditable process should advance through **gates** rather than scheduling a teardown date and hoping dependencies vanished.

### Phase A — Discovery and Scope Alignment

- Inventory assets, data, and consumers; confirm sign-off authorities.
- Define which capabilities the new system assumes, which terminate, and which stay.
- Review long business cycles, quarterly/annual reports, partner integrations, and disaster recovery procedures.
- Define post-cutover SLOs and stability metrics, data to reconcile, observation window, and stop conditions.

**Gate A:** asset and dependency list with owners, migration scope, preliminary disposition per dataset, and verification plan complete.

### Phase B — Capability and Data Transition

- Deploy target system, route users/APIs, migrate data, and reconcile.
- Confirm legacy jobs are migrated or terminated. Inspect queue lag, CDC lag, error events, and dead-letter queues.
- Promote target as authoritative write source; record cutover timestamp and handle pre-cutover deltas.
- Verify core functions and edge cases: refunds, invoice edits, month-end reconciliation, partners resending old messages.

**Gate B:** business operates on the new system, reconciliation passes agreed thresholds, zero uncontrolled writers remain on legacy source.

### Phase C — Freeze, Monitor, and Isolate

- Place legacy source in read-only mode or block writes at appropriate app, DB, and integration layers.
- Maintain a soak period matching risk and business cycles; inspect metrics, logs, tracing, and flow logs for stray access.
- Shift remaining active DNS, webhooks, certificates, schedulers, and alerts to the new target.
- Isolate legacy permissions and network paths; disable service accounts no longer serving active systems.

**Gate C:** zero required business traffic/dependencies left, alerts route accurately, recovery or rollback within allowed window verified.

### Phase D — Data Disposition and Infrastructure Teardown

- Execute the disposition matrix: migrate, archive, time-bounded hold, anonymize, or delete.
- Verify archive retrieval **before** removing legacy databases/compute.
- Decommission in layers favoring reversible steps first: repoint endpoints, disable jobs, stop compute, then delete resources and process data per approvals.
- Remove network rules, DNS records, load balancers, service accounts, API keys, secrets, certificates, storage, database instances, and backup schedules following dependency order.
- Update inventories, diagrams, runbooks, DR plans, catalogs, billing tags, contracts/licenses, and audit records.

**Gate D:** each asset closed with status and evidence; retained data remains retrievable/decryptable; zero orphaned resources or stale permissions remain.

### Phase E — Post-Decommission Verification

- Monitor business errors, hits to legacy endpoints, failed jobs, alerts, and security posture.
- Reconcile actual bills/costs over appropriate billing cycles; storage, snapshots, egress, static IPs, licenses, and support contracts can still accrue charges.
- Test retention schedules and archive retrieval workflows, including locating a specific record under authorized permissions.
- Close acceptance sign-off once business, operations, security, and data owners finish their checks.

**Gate E:** decommissioning proven via asset states, test results, and billing data—not merely “the servers are off.”

## 7. Architectural Risks When Dismantling Cloud Components

### 7.1. Shared Resources

A security group, subnet, route, KMS key, storage bucket, cluster, private DNS zone, observability workspace, or CI/CD agent may serve multiple applications. Deleting a resource simply because its name resembles the old system is unsafe. Independently verify **consumers** and **owners** for every resource.

### 7.2. Asynchronous Systems and In-Flight Data

Blocking HTTP traffic does not mean messages are empty. Before shutting down workers and brokers, check **queue depth, consumer lag, in-flight messages, retries, dead-letter queues, CDC replication lag**, and reconcile event IDs. For replayable tasks, require idempotency to avoid lost or duplicated business effects.

### 7.3. Backups and Disaster Recovery

Legacy backups may be retained per policy even after the app shuts down. Distinguish:

- **Short-term rollback backups:** held for the defined rollback window, controlled and rehearsed.
- **Compliance-retention backups:** kept until valid expiration dates with restricted access and scheduled deletion.
- **Searchable archives:** independently operated with search and export workflows.

Do not keep backing up a retired server merely because a backup schedule was forgotten. Conversely, never destroy keys or backups while retained data still requires decryption or recovery.

### 7.4. Irreversibility

Stopping a VM can usually be reversed by starting it; deleting storage, snapshots, keys, or identity configurations can make recovery very difficult or impossible. Therefore, plans must state the **point of no return**, approvers, and evidence required before crossing it. Once data has been permanently deleted per policy, rolling back to the legacy system is no longer valid.

## 8. Designing Rollback Plans and Acceptance Criteria

Rollback fits best during traffic shifting or temporary isolation while source data remains consistent and legally retainable. Returning to the legacy system is viable only after analyzing new target writes, reverse-sync mechanics, conflicts, and data processing obligations. Never assume flipping DNS back to old servers makes the service safe.

A plan must specify:

| Component | Questions to Answer |
|---|---|
| Trigger | Which failures force halt or rollback: lost transactions, reconciliation drift, latency breach, archive access failure? |
| Decision owner | Who holds authority to decide during the change window? |
| Window | Until what point can we roll back without causing data divergence? |
| State/data | How are post-cutover writes handled if reverting to legacy source? |
| Verification | Which metrics, tests, and checks confirm recovery succeeded? |
| Irreversible actions | Which resources/keys/data stay untouched until the rollback window closes? |

Example measurable **acceptance criteria**:

- 100% of critical capabilities have owners in the new system or approved termination decisions.
- Zero valid business requests hit legacy endpoints during the agreed monitoring window after covering infrequent cycles.
- All required migrated/retained data reconciled and retrieval-tested against approved criteria.
- Zero active writers or critical consumers remain on legacy infrastructure; backlogs and error events resolved.
- Assets, access grants, keys, backups, and contracts closed or scheduled with clear owners.
- Approvals, test evidence, and deletion/archival logs saved to change records.

Specific thresholds (such as zero record variance on financial transactions or SLO error limits) must match system characteristics; never apply one generic threshold to all data types.

## 9. Decommissioning Records and Audit Evidence

A **decommission manifest** aligns business, data, and operations teams around one view. Below is an illustrative template, not an executable auto-deletion configuration:

~~~yaml
system_id: order-legacy
business_owner: order-operations
technical_owner: cloud-platform
target_system: order-service-v2
cutover_at: "YYYY-MM-DDTHH:MM:SSZ"
rollback_deadline: "Per approved change record"

dependencies:
  - name: monthly-invoice-job
    disposition: migrated
    evidence: "Link to rehearsal and acceptance results"
  - name: partner-sftp
    disposition: retired
    evidence: "Confirmation from integration owner"

datasets:
  - name: open_orders
    classification: confidential
    disposition: migrate
    destination: order-service-v2
    owner: order-data
    verification: "Reconciled by ID, status, monetary total"
  - name: closed_invoices
    classification: restricted
    disposition: archive
    destination: controlled-records-store
    retention_policy: "Reference approved policy"
    legal_hold: false
    retrieval_test: passed
  - name: obsolete_temp_export
    classification: internal
    disposition: delete
    approval: "Reference change record and data owner"

infrastructure:
  - resource: old-app-vm
    action: decommission
    dependency_check: passed
  - resource: shared-kms-key
    action: retain
    reason: "Other archive still depends on it"

evidence:
  migration_reconciliation: "Link to reconciliation results"
  archive_retrieval: "Link to retrieval test report"
  access_revocation: "Link to access revocation log"
  cost_verification: "Post-decommission cost verification period"
approvals:
  business: pending
  data_governance: pending
  security: pending
  operations: pending
~~~

At multi-application scale, track this manifest in change management or an asset catalog. Automation should execute only after conditions and evidence pass verification; **never treat a field containing “delete” as automatic authorization to destroy**.

### 9.1. Technical Checks Before Irreversible Operations

Decision logic can be expressed in pseudocode:

~~~text
can_destroy(asset):
    require asset.owner is known
    require dependencies(asset) are resolved
    require workload_is_not_receiving_valid_traffic(asset)
    require business_and_technical_signoff(asset)

    for dataset in datasets_affected_by(asset):
        require dataset.disposition is approved
        require required_migration_or_archive_is_verified(dataset)
        require retention_and_legal_hold_are_respected(dataset)
        require restoration_or_retrieval_path_is_tested_if_needed(dataset)

    require shared_resources_are_excluded_or_separately_approved(asset)
    require rollback_window_is_closed_for_irreversible_actions(asset)
    return true
~~~

This is a **control model**, not an automated dependency discovery algorithm. Dependency lists and approval sign-offs must still originate from accountable sources.

### 9.2. Suggested Responsibility Matrix

| Role | Primary Responsibilities |
|---|---|
| Business owner | Confirm capabilities are replaced/terminated, retrieval needs, and business UAT |
| Data owner / governance | Classify data, decide migrate/archive/delete, enforce retention, legal holds, and access rights |
| Cloud architect | Design target state, dependencies, acceptance gates, and architectural trade-offs |
| Platform / SRE | Execute cutover, monitor, decommission infrastructure, verify operations and cost |
| Security / compliance | Verify permissions, encryption, key lifecycle, compliance rules, and audit evidence |
| Application / integration team | Migrate batch jobs, APIs, event consumers, and test business cases |

In small teams, one person may hold multiple roles, yet **decision authority and approval evidence** must remain explicit.

## 10. Well-Architected Trade-Offs

Legacy decommissioning is an architectural decision spanning multiple pillars, not merely cost cutting:

| Perspective | Architectural Decision | Metrics or Evidence to Track |
|---|---|---|
| **Operational Excellence** | Explicit gates, runbooks, inventories, owners, approved automation | Asset closure rate, open exceptions, complete change records |
| **Security** | Remove old access paths, classify and encrypt data, govern keys | Unused IAM/secrets removed, archive access logs, residual data count |
| **Reliability** | Verify dependencies, reconcile, drain queues, honor rollback window | Post-cutover errors, valid data ratio, retrieval test results |
| **Performance Efficiency** | Match historical store and retrieval path to actual query frequency | Historical lookup/restore latency, resources kept running |
| **Cost Optimization** | Eliminate idle compute, licenses, orphans; pick fitting storage tiers | Cloud/on-prem spend, post-decommission archive and retrieval costs |
| **Sustainability** | Shut down unused infrastructure, right-size storage to actual needs | Always-on resources retired, unnecessary storage removed |

Two contrasting scenarios highlight the trade-off:

- **Daily historical lookups:** an indexed data store with a search UI costs more than cold object storage yet slashes latency and support toil.
- **Lookups only a few times a year:** archiving to a colder tier saves money, provided restore delays, retrieval fees, and timely fulfillment workflows are acceptable.

Target cost is **total lifecycle cost**: storage + retrieval + processing + security + operations + retention obligations—not storage price per GB alone.

## 11. Practice Scenario: Retiring a Legacy Ordering System

**Context:** An enterprise moved ordering to cloud microservices. The legacy app still has a 2 TB database, 12 VMs, a month-end reconciliation job, a partner API sending quarterly data, multi-point snapshots, and electronic invoices requiring policy retention.

**Goal:** eliminate legacy operating infrastructure while preserving order processing, reconciliation, and invoice lookup.

**Proposed Step-by-Step Design:**

1. **Decompose dependencies:** map users, partners, job schedules, queues, DB, and reporting systems. Move the partner API to the new gateway and replace scheduled jobs with target tasks; test with approved test data.
2. **Lock write authority:** switch order writes to the target database; stop old writers and inspect deltas, CDC lag, and backlogs. Use identical cutoffs and time zones during reconciliation.
3. **Process data:** migrate open orders; archive invoices and required history; delete temporary exports per approval; evaluate snapshots/backups separately under retention rules.
4. **Build lookup capability:** provide document lookup by order ID with role-based access and audit logging; test searching and opening representative records before tearing down the DB.
5. **Observe full cycles:** verify at least one successful month-end job run and coordinate with the partner to test quarterly integration—or gather equivalent test evidence if waiting a quarter is infeasible.
6. **Decommission infrastructure:** disable legacy endpoints, monitor; shut down the 12 VMs, remove dedicated resources and stale permissions once gates pass; avoid deleting shared subnets/KMS keys.
7. **Close out:** save reconciliation reports, retrieval test logs, revoked-access records, time-bounded retained asset inventory, and verify costs in the next billing cycle.

**Decision requiring business alignment:** if accounting must run ad-hoc queries across millions of invoices every month, ultra-cold archive storage may miss requirements; an indexing layer or dedicated query database is then a justified expense. If only a few ID lookups occur per year, keeping the entire old DB engine running is rarely optimal.

### Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Shutting down after a few days of zero traffic | Misses monthly/quarterly jobs and partner integrations | Combine telemetry, business catalogs, and owner confirmation |
| Treating snapshots as an archive | Unsearchable, slow restores, tied to legacy engines | Test independent retrieval via historical formats/tools |
| Keeping all data indefinitely | Higher cost, security exposure, governance liability | Enforce a retention matrix with owners, triggers, limits, and exceptions |
| Deleting buckets, roles, or keys by app name | Breaks other systems or destroys decryption capability | Verify shared-resource links and independent consumers |
| Reconciling row counts only | Misses wrong values, mappings, or business relationships | Combine quantitative, semantic, and transaction-sample checks |
| Deleting resources without updating operations | False alerts, stale DR docs, lingering charges | Close changes, CMDB, runbooks, billing, licenses, and post-checks |

## 12. Pre-Completion Checklist

Decommissioning is architecturally complete when the answer is **Yes** to every applicable item:

- [ ] Business capabilities, customers, partners, and scheduled jobs have been replaced or have approved termination decisions?
- [ ] All data owners classified datasets and decided **migrate / archive / temporary hold / anonymize / delete** under valid retention and legal-hold policies?
- [ ] Migrated and archived data reconciled; archives can be **searched, read, and decrypted** using target tools and permissions?
- [ ] Zero valid writers, consumers, webhooks, or network flows still require the legacy system; queues and retries drained?
- [ ] Rollback window and point of no return understood; deletions occur strictly after corresponding acceptance gates?
- [ ] Shared resources, backups, snapshots, object versions, logs, secrets, and encryption keys inventoried with explicit decisions?
- [ ] DNS, certificates, IAM, monitoring, backup policies, DR plans, runbooks, asset catalogs, licenses, and integration docs updated?
- [ ] State-change records, approvals, reconciliation/decommissioning evidence, and retained-data schedules archived?
- [ ] Accountable owners assigned to manage the archive, process deletion requests, and audit costs after the legacy system is gone?

**Conclusion:** Retiring a legacy system means designing and executing a verifiable new operational state. The right end state is one where the new application handles required capabilities, valuable data is retained and retrievable per policy, expired data is safely disposed of, and legacy resources create zero lingering dependencies or wasted costs. This final step is essential for modernization programs to truly realize gains in reliability, security, operability, and cost.
