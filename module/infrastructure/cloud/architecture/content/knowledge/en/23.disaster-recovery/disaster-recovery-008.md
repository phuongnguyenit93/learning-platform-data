# Post-Incident Failback and Restoring Normal Operations

When a primary region suffers an outage, the system can fail over to a standby region to keep serving. However, the original region coming back online does not mean the system should immediately shift traffic back to it. During failover, the standby region may have processed new transactions, modified data, emitted events, sent notifications, and become the sole holder of the latest state. Merely switching DNS or turning the old database back on can lose transactions, create dual writes, send duplicate messages, or split data into two inconsistent sources.

**Failback** is the controlled process of returning workloads, write authority, data, and traffic from the currently serving DR environment back to the target operating topology. The goal is not just returning to the original region, but restoring a stable, consistent, operable, and verified state.

This lesson belongs to the **Disaster Recovery** chapter of the **CLOUD_ARCHITECTURE** module. It connects reliability, data, networking, compute, identity, security, and operations. A failback plan must define start conditions, data sync order, writer authority, drift checks, traffic shifting, transaction reconciliation, abort/rollback options, and incident-closure evidence.

## 1. Failover and Failback Are Two Distinct Procedures

**Failover** shifts services away from a failing environment to one capable of serving. **Failback** transitions workloads and operational authority from the DR environment back to the target topology after the incident is resolved.

For example, the Booking Platform uses Region A for normal operations and Region B as warm standby. When A loses connectivity, operations fence writer A, promote database B, and shift traffic to B. Over the next several hours or days, B accepts new bookings, payment statuses, cancellations, and events. When A recovers, A usually lags behind current data in B.

~~~mermaid
flowchart LR
    A["Pre-incident<br/>A = Primary"] --> F["Failover<br/>A failed"]
    F --> B["DR operation<br/>B = Active writer"]
    B --> R["Region A recovers"]
    R --> S["Assess / repair / reverse sync"]
    S --> C["Controlled failback"]
    C --> N["Normal topology restored"]
~~~

Differences in data flow direction:

| Stage | Authoritative Data Holder | Sync Direction |
|---|---|---|
| Pre-incident | Region A | A → B |
| Post-failover | Region B | B → A or awaiting sync |
| During failback preparation | Region B remains writer | B → A |
| At switchover | Controlled write handoff | Complete B → A then change owner |
| Post-failback | Region A becomes new writer | A → B |

Core rule: **never reverse replication or switch writers merely because Region A came back online.** Identify where the most accurate data resides and keep it authoritative until write authority is handed off safely.

## 2. Preconditions to Start Failback

Failback is a risky production change. Establish readiness before executing.

### 2.1. The Original Region Has Recovered Stably

Do not rely solely on VMs or databases reporting healthy. Verify:
- The incident root cause is understood and resolved.
- Compute, storage, networking, and databases are no longer degraded.
- Required AZs and dependencies are operational.
- Capacity suffices for projected load.
- No remaining signs of packet loss, abnormal latency, throttling, or control plane errors.
- External-to-region monitoring and alerting work.
- Consecutive checks demonstrate stability over a defined observation window.

Do not pick an arbitrary stability window. Observation requirements should reflect fault type, incident history, and recurrence risk. A brief network flap warrants different evaluation from data corruption or security compromise.

### 2.2. The Root Cause Has Been Fixed

If failover stemmed from a faulty schema migration, credentials, policies, or an application bug, failback will not automatically fix those issues. Ensure:
- Root cause analysis has a sufficiently reliable conclusion.
- Fixes have been tested.
- Required policies, secrets, and certificates are restored.
- Matching artifacts and configuration are deployed.
- Evidence confirms the fault does not recur in testing or canary environments.

If root cause remains unknown, failback can push traffic straight back into the original failure mode. In that case, keep running on Region B and investigate further unless compelling business reasons force a move.

### 2.3. Capacity and Dependencies Are Ready

Region A needs enough resources to absorb production load, while Region B needs enough resources to keep serving if failback fails.

Check:
- Compute quotas, instance/GPU quotas, IP and subnet capacity.
- Database/storage throughput and connection limits.
- Cache warm-up and queue consumer capacity.
- Identity, KMS/HSM, secret manager, DNS, certificates, and registries.
- Network paths to internal services, partners, and SaaS.
- Autoscaling, deployment pipelines, and break-glass permissions.
- Backups/replication and recovery options if switchover is interrupted.

Never scale down Region A's capacity completely before A finishes verification, and keep B able to continue serving.

## 3. Keep a Single Authoritative Write Source

After failover, Region B has typically become the writer. Before and during failback preparation, keep B as the authoritative data source.

Rules:
1. Explicitly confirm which region/database currently holds write authority.
2. Block the old writer or resources that lost write rights.
3. Do not let applications in A automatically write just because the database restarted.
4. Establish B → A replication using a supported mechanism.
5. Monitor lag and apply errors throughout the process.
6. Switch writers only after switchover preconditions pass.
7. Use appropriate fencing/epochs/leases to block the old writer from continuing to write.

### 3.1. Split-Brain When Both Regions Accept Writes

If both A and B accept writes, it can cause:
- Two bookings reserving the same resource.
- Differing payment states across regions.
- Two events with conflicting contents.
- Misupdated counters or inventory.
- Overwritten data when replication converges.

Not every conflict can be resolved by taking the higher timestamp. Clocks can drift, updates carry different semantics, and transactions may depend on business ordering.

### 3.2. Fencing and Write Authority

A fencing mechanism can use monotonically increasing epochs/terms. When B is promoted, it carries a new epoch; databases or write layers must reject operations from older writers bearing lower epochs.

Fencing tokens work only if every write path validates the token or equivalent authority. Changing DNS, updating load balancers, or stopping one pod is insufficient if legacy clients, batch jobs, or old workers can still write directly.

## 4. Reverse Replication: Syncing from DR Back to the Original Region

After failover, new data was created in B. Failback must bring those changes back to A before A becomes writer.

~~~mermaid
flowchart TB
    B["Region B<br/>Current authoritative writer"] --> LOG["Transaction log / change stream"]
    LOG --> XFER["Reverse replication B → A"]
    XFER --> A["Region A<br/>Recovering replica"]
    A --> VERIFY["Validate lag / consistency / checksums"]
    VERIFY --> READY["Candidate for writer"]
~~~

Reverse replication mechanisms vary by data type:
- **Databases:** transaction logs, streaming replication, change data capture, or native cross-region replication.
- **Object storage:** object version replication, inventory/diffs, and copying changed objects.
- **Event streams:** replicate partitions/events by offset, preserving event IDs and ordering semantics.
- **File/block storage:** snapshots, volume replication, or block-level synchronization.
- **Search indexes/caches:** usually rebuildable from the source of truth rather than replicated directly.

Not every service supports safe replication reversal. Some mechanisms are unidirectional or require recreating the relationship. Verify provider/API operations, version/engine constraints, permissions, and limits before running.

### 4.1. Do Not Confuse Zero Lag with Consistent Data

Zero replication lag at a given instant is a good sign yet does not by itself prove all systems are consistent. Check:
- Is the replication stream paused or hitting apply errors?
- Are all required partitions/tables/object prefixes covered?
- Are there open or uncommitted transactions?
- Is any data filtered/excluded from replication?
- Are sequences/offsets continuous?
- Have secondary indexes, materialized views, and search indexes caught up?
- Are metadata, ownership, tags, ACLs, and encryption key references complete?

With object storage, some asynchronous replication operations do not guarantee cross-object ordering. If file metadata in the DB points to an unreplicated object, the application may display the record yet fail to load the file. Check data relationships, not just object counts.

### 4.2. Data That Cannot Be Replicated Directly

Some state must be regenerated or reconciled at the application tier:
- Caches can be invalidated and warmed back up from the database.
- Search indexes can be rebuilt from source tables or event logs.
- Ephemeral sessions may expire or require re-authentication.
- Ephemeral queues may need replay from outboxes/event stores.
- Scheduled jobs must designate a new owner to avoid running twice.
- Temporary files/incomplete uploads need inspection and cleanup per upload session.

List every data store and classify it: replicate, restore, rebuild, reconcile, or discard per policy.

## 5. Reconciling Data and Transactions Created During DR

While B served traffic, transactions may have occurred around replication lag windows or when A lost connectivity. Before failback, know exactly what was committed.

### 5.1. Reconciliation

Reconciliation goes beyond comparing row counts. Verify business invariants:
- Every `CONFIRMED` booking has a valid resource and time range.
- Every captured payment has a matching transaction/reference.
- Cancellations are not overwritten by stale states.
- Critical events are neither lost nor processed twice.
- Aggregate inventory/availability matches source transactions.
- Object metadata points to real, readable objects.
- Stream sequences/offsets have no unexplained gaps.

Tools to use:
- Partition-level row counts and checksums.
- Engine-specific transaction IDs/LSNs/GTIDs/commit sequences.
- Event IDs and idempotency keys.
- Reconciliation queries against the source of truth.
- Totals, quantities, and state counts by business aggregate.
- Object inventory and metadata comparisons.

### 5.2. Indeterminate Transaction Outcomes

A request may have been processed in B without the client receiving a response. A client retrying in another region could submit the same request again. During reconciliation, distinguish:
- Never committed.
- Committed, yet response was lost.
- External side effect executed, yet state not recorded.
- Recorded in database, yet event not emitted.
- Event emitted, yet consumer not processed.

Idempotency keys and transaction references determine whether an operation already happened. Never create a new transaction without looking up prior state first.

### 5.3. Events/Outboxes and Consumers

For event-driven architectures, reconcile:
- Whether outbox events were published.
- Whether event IDs remain identical during replay.
- Whether consumers already processed side effects.
- Whether broker offset/ack state aligns with the database.
- Whether DLQs accumulated messages during DR.
- Whether replay could generate duplicate notifications/payment commands.

Failback is a prime moment for duplicates if both regions run schedulers, outbox publishers, or consumers concurrently. Enforce clear ownership per partition/workload.

## 6. Syncing Applications, Configuration, and Schemas

Data is not the only thing that can drift between regions. During DR, Region B may have received hotfixes or run a different image from Region A.

Verify parity for:
- Container image digests and package versions.
- Application config, feature flags, and environment variables.
- Database schema/migration versions.
- API/event schemas and compatibility.
- Model artifacts/feature versions if ML is used.
- Secret versions, certificates, trust bundles, and expirations.
- IAM roles/policies, workload identities, and network policies.
- Autoscaling parameters, quotas, and runtime settings.
- Scheduled jobs, worker concurrency, and retry policies.

Never blindly deploy A's old version onto B's newer data or vice versa. Schemas must be compatible with the application version running post-failback. Use expand-contract when synchronizing schemas while regions/consumers run differing versions.

### 6.1. Immutable Artifacts and Configuration Drift

Compare using:
- Image digests rather than mutable tags.
- Artifact checksums/signatures.
- IaC and deployment manifest versions.
- Controlled config revisions or hashes.
- Secret references/versions—never export secret values.
- Database migration histories.
- Policy snapshots or policy-as-code evaluations.

Classify drift as mandatory, temporarily acceptable, or requiring remediation before failback. Do not wipe hotfixes in B before understanding how they affected data or user flows.

## 7. Preparing Traffic and Health Checks

Once data is synchronized, verify A can serve before sending live traffic.

### Region-Level Readiness Checks

- API health and synthetic user journeys.
- Database read/write paths under authorized permissions.
- Feature flags, caches, and object access.
- Authentication, authorization, and token renewal.
- Payment/email/partner connectivity via sandbox or safe checks.
- Queue publish/consume using deduplicatable test events.
- TLS/certificates, DNS, private endpoints, and network routes.
- p95/p99 latency and error rates.
- Capacity when receiving projected traffic slices.

Never run tests that write real customer data without cleanup/approval. Use synthetic tenants or clearly tagged test objects.

### Do Not Shift Traffic All at Once

Traffic managers can support weighted routing. Once A is ready:
1. Keep B as primary writer.
2. Shift a small slice of read traffic or an internal cohort to A if data/consistency permits.
3. Observe latency, errors, auth, caches, and returned data.
4. If healthy, increase percentages in planned steps.
5. Hand over write authority via a controlled switchover.
6. After A becomes writer, continue shifting traffic per plan.
7. Keep B ready for rollback/DR throughout the observation window.

For single-writer systems, **never let both A and B accept parallel writes merely for canary traffic.** You can canary read-only or shadow requests, while write ownership remains singular.

## 8. Switchover: Handing Over Write Authority at Failback

Switchover is the most delicate step. It requires a clear plan, an operator, stop conditions, and verified states.

A reference sequence for a single-writer system:

~~~mermaid
sequenceDiagram
    participant OPS as Operations
    participant APP as Applications
    participant B as Region B writer
    participant A as Region A candidate
    OPS->>APP: Enable maintenance/admission control
    APP->>B: Stop accepting new writes
    B->>B: Drain in-flight transactions
    B->>A: Final replication catch-up
    A-->>OPS: Lag zero / consistency checks pass
    OPS->>B: Fence writer B
    OPS->>A: Promote A with new epoch
    OPS->>APP: Route write traffic to A
    APP->>A: Controlled write verification
    OPS->>APP: Restore normal traffic
~~~

Details vary by engine/service:
- Halt or restrict new writes for a brief window.
- Drain in-flight requests/transactions.
- Stop schedulers or publishers capable of side effects.
- Record the final replication position on B.
- Wait for A to apply up to that position.
- Run final consistency checks.
- Fence B and confirm no write paths remain.
- Promote A via the database/broker's supported mechanism.
- Issue a new epoch/lease if the architecture uses fencing.
- Update service discovery/connection strings/traffic routing.
- Gradually open write traffic.
- Verify a test transaction and read it back from the authoritative source.

In some databases, promoting a standby and reversing replication carry specific ordering constraints. Always follow procedures supported by the database/provider; the diagram illustrates overall logic rather than literal commands for every engine.

### 8.1. Maintenance Windows and Admission Control

If brief downtime is acceptable, enable a maintenance window to reject or queue new writes while continuing to serve read-only traffic. If writes cannot stop, you need a stronger ownership-handoff protocol supporting zero-downtime cutover.

Notify users and partners when required. Requests rejected during maintenance need safe retry behavior, idempotency keys, and clear messages.

## 9. Rollback When Failback Hits Trouble

Failback can fail too. Define rollback criteria before starting rather than improvising mid-incident.

Stop triggers:
- Replication lag stops shrinking or apply errors appear.
- Consistency checks fail.
- Old writer cannot be fenced.
- A fails health, SLO, or capacity checks.
- Identity/KMS/networking operates unstably.
- Error rates or latency breach thresholds after traffic shift.
- Data mismatches or duplicate side effects appear.
- Ambiguity over which region is authoritative.

### 9.1. Before vs. After A Accepts Writes

**Before A accepts writes:** cancel the switchover, keep B as writer, and investigate. This is generally the simpler rollback.

**After A has accepted writes:** A has become the new source of truth. Never simply point traffic back to B and enable writes without syncing new writes from A to B or confirming B holds complete data. Instead:
1. Fence the current writer under a fresh procedure.
2. Identify transactions committed on A.
3. Sync or reconcile data A → B.
4. Ensure neither side writes concurrently.
5. Promote B only after consistency and recovery criteria are satisfied.
6. Document the incident and decisions.

Once new writes exist, "rolling back to B" is effectively a **new failover**, not reverting a config change.

### 9.2. Keeping B as a Recovery Path

For a period post-failback, keep B ready with A → B replication re-established. Do not delete B's data or reclaim all standby capacity immediately. How long to retain standby depends on DR policy and confidence in the newly restored environment.

## 10. Failback by Data Type

Not every data store uses the same strategy:

| Component | Failback Approach | Critical Checks |
|---|---|---|
| Relational database | Reverse replication, catch-up, fence, and promote | Transaction positions, schemas, constraints, lag |
| NoSQL database | Replication reversal or provider-supported export/import | Conflicts, consistency, partition ownership |
| Object storage | Replicate new versions/objects back to original region | Version IDs, metadata, lifecycles, checksums |
| Event broker | Mirror/replay by partition and offset | Event IDs, ordering, duplicates, consumer offsets |
| Cache | Can invalidate and warm from source | Cache keys/versions, cold-start load |
| Search index | Rebuild from source or replicate index | Index versions, document counts, freshness |
| File share/block volume | Snapshots/replication and mount checks | Crash/application consistency, permissions |
| Session store | Replicate or require session refresh/re-auth | TTLs, token validity, user impact |
| Analytics warehouse | Catch-up/backfill partitions | Late data, deduplication, watermarks |
| Scheduled jobs | Transfer ownership via leases/leaders | No duplicate runs or missed schedules |

Some data is cheaper to regenerate than replicate. For example, caches/search indexes can be rebuilt, whereas payment ledgers require strict transaction preservation and tight reconciliation.

## 11. Shared Dependencies During Failback

A region may have operated during DR via fallback settings, yet returning to A still requires checking dependencies. In particular:
- Identity issuers and workload federation.
- KMS/HSM key access, key rotation, and decrypt permissions.
- Secret managers, config stores, and certificate authorities.
- DNS/traffic management and resolver caches.
- Container/image registries, package repositories, and model artifacts.
- CI/CD, IaC state, and deployment authority.
- Network hubs, firewalls, NAT, egress, and private endpoints.
- Monitoring, alerting, tracing, and incident communication.
- External provider quotas, webhook callbacks, and IP allowlists.
- Backups, replication coordinators, and control planes.

Region A may look healthy at the compute layer yet remain unready if certificates expired, secrets did not sync, registries are blocked, or workload identities changed during DR.

### Pre-Failback Dependency Checklist

| Dependency | Mandatory Check | Evidence |
|---|---|---|
| Identity | Principals/roles/tokens work from both regions | Authentication tests |
| KMS | Runtimes and operators read/decrypt data properly | Decrypt tests/audits |
| Secrets | Secret/certificate versions valid and consistent | Secret version checks |
| DNS | Records, TTLs, health policies, and endpoints accurate | External DNS probes |
| Registry | Promoted artifacts are pullable | Image digest verification |
| Network | Private routes, firewalls, and egress work | Connectivity tests |
| CI/CD/IaC | Approved failback pipeline exists | Deployment rehearsal |
| Observability | Independent alerts and dashboards for both regions | Synthetic monitors |
| External APIs | Quotas, allowlists, and callback endpoints ready | Contract/smoke tests |

## 12. Security and Change Control During Failback

Failback typically requires elevated privileges: promoting databases, altering routing, granting keys, editing policies, and shutting down writers. This is a high-risk moment for operator mistakes or privilege abuse.

Principles:
- Separate approvers from executors for high-risk actions.
- Use controlled, time-bound, audited break-glass access.
- Enforce step-by-step least privilege; avoid standing permanent admin credentials.
- Log who changed writers, policies, DNS, secrets, and traffic.
- Never print secrets or signed URLs into logs/tickets.
- Protect backups, replication channels, and temporary data.
- Verify encryption keys and data residency before copying.
- Review security findings from DR before returning A to production.
- Upon completion, revoke emergency access and temporary credentials.
- Verify Region A's configuration did not weaken security posture to ease recovery.

If the original incident could have been a security compromise, never return Region A automatically just because infrastructure boots. Verify containment, persistence checks, identity trust, and integrity before letting it handle production data.

## 13. Observability and Success Criteria

Failback must be measured as a process, not just a DNS switch.

### 13.1. Metrics to Track

- Replication lag/position and apply errors.
- Queued transactions, in-flight writes, and drain times.
- Data reconciliation mismatches.
- Database connections, locks, CPU, IOPS, and storage latency.
- API p50/p95/p99, error rate, and success rate.
- Queue depth, oldest message age, duplicates, and DLQ arrivals.
- Cache warm-up, hit ratios, and stale responses.
- Authentication, authorization, KMS decrypt, and secret retrieval failures.
- Traffic weights by region and user cohort.
- Cost/network egress/replication throughput during catch-up.

### 13.2. Timeline and Audit

For every failback, record:
- Incident ID and change ID.
- Commander, approvers, and operators.
- Current region and current writer.
- Start time, checkpoints, cutover, and end time.
- Pre/post replication positions.
- Fence/promote timestamps and writer ownership.
- Traffic routing changes.
- Smoke test and reconciliation results.
- Errors, rollbacks, or deviations.
- Actual RTO/RPO of the original incident and failback duration.
- Post-incident action items.

Never rely on one system-wide aggregated dashboard to declare success. Break down metrics by Region A/B, application version, database writer, and workload.

## 14. Reference Failback Runbook

~~~text
PHASE 0 — AUTHORIZATION AND READINESS
  - Confirm incident cause is resolved.
  - Confirm target region and failback window.
  - Name incident commander, data owner and operators.
  - Confirm rollback and stop criteria.
  - Verify quota, identity, KMS, secrets, network and artifacts.

PHASE 1 — RECOVER TARGET REGION
  - Restore infrastructure and service dependencies.
  - Deploy approved application/runtime versions.
  - Verify schema/config/security parity.
  - Keep target region out of production write traffic.
  - Run health and synthetic checks.

PHASE 2 — REVERSE DATA SYNCHRONIZATION
  - Keep current DR region as sole writer.
  - Configure reverse replication.
  - Verify coverage, lag, errors and data integrity.
  - Rebuild cache/search/index as required.
  - Reconcile transactions, events and objects.

PHASE 3 — CUTOVER PREPARATION
  - Confirm target capacity and dependency readiness.
  - Notify stakeholders and enable maintenance/admission control if needed.
  - Stop new writes and drain in-flight work.
  - Record final replication position.
  - Wait for target to catch up and pass final checks.

PHASE 4 — WRITER SWITCH
  - Fence old writer.
  - Promote target with new ownership/epoch.
  - Validate one authoritative writer.
  - Switch routing gradually.
  - Run controlled business transaction and read-back.

PHASE 5 — STABILIZATION
  - Monitor latency, errors, queue, data and dependency health.
  - Keep former DR region ready and replicate from new writer.
  - Stop or reverse traffic shift if a criterion fails.
  - Reconcile post-cutover transactions.

PHASE 6 — CLOSE
  - Confirm SLO and business journeys.
  - Record actual RTO/RPO and failback timeline.
  - Revoke temporary access and clean up safely.
  - Update diagrams, runbooks and action items.
~~~

Exact commands must match the database engine, cloud provider, and routing service. Runbooks need reviewed commands, expected outputs, executors, rollback triggers, and verification steps after each action; never write generic commands assuming they run everywhere.

## 15. Failback Drills and Recovery Testing

DR plans often focus on failover while neglecting failback. Drill both directions.

| Test | Purpose | Expected Outcome |
|---|---|---|
| Reverse replication setup | Verify ability to reverse sync | Relationship established; no dual writes |
| Replication catch-up | Measure sync time for accumulated data | Lag shrinks as expected; no lost partitions |
| Writer fencing | Verify old writer is rejected | Only one writer holds write access |
| Transaction reconciliation | Verify data created during DR | Business invariants satisfied |
| Object/event recovery | Verify files, events, and offsets | No loss/duplicates beyond policy |
| Application/config parity | Detect cross-region drift | Artifacts, schemas, secret references, and policies match |
| Traffic canary | Validate target prior to full cutback | SLOs met for test cohort |
| Failback abort | Test stopping mid-procedure | DR region remains authoritative |
| Post-cutover rollback | Test recovery after target accepted writes | New failover and data catch-up workflow works |
| Full game day | End-to-end exercise | Measured timeline, RTO/RPO, and action items |

### 15.1. Criteria Not to Skip

- Ability to identify a single writer at all times.
- Ability to measure replication positions and data mismatches.
- Ability to abort prior to cutover without impacting the source of truth.
- Ability to recover if the target fails after accepting writes.
- Ability to reconstruct required data from backups/replicas/event logs.
- Emergency procedures still function when a shared dependency fails.
- Operators know when to proceed, when to stop, and who holds decision authority.

## 16. Well-Architected Trade-Offs

| Dimension | Benefit of Controlled Failback | Risks to Manage | Evidence |
|---|---|---|---|
| **Reliability** | Restores target topology, capacity, and recovery posture | Returning too early, split-brain, lost writes, or failback loops | Rehearsals, fencing tests, reconciliation |
| **Security** | Restores normal policies/privileges and revokes emergency access | Credential drift, broken key access, previously compromised region | IAM audits, key/decrypt tests, incident reviews |
| **Performance Efficiency** | Returns workloads to regions with optimal latency/capacity | Cold caches, warm-up, replication load, and traffic spikes | p95/p99, cache hits, DB/replication metrics |
| **Cost Optimization** | Releases excess DR capacity after stabilization | Bidirectional replication, standby, and data transfer | Cost timelines, storage/egress usage |
| **Operational Excellence** | Clear runbooks, ownership, timelines, and state | Manual steps, undocumented drift, single-expert reliance | Game days, change logs, runbook reviews |
| **Sustainability** | Removes temporary resources and unneeded replication | Retaining redundant copies or deleting recovery data by mistake | Lifecycle reviews, inventories, cleanup audits |

Key trade-offs:
- Maintenance windows simplify cutover while introducing planned downtime.
- Zero-downtime switchovers avoid disruption while demanding tighter writer coordination and consistency.
- Reverse replication cuts data copy volume while depending on service support.
- Backup/restore can simplify data flow direction while lengthening RTO.
- Keeping the DR region warm longer raises cost while preserving fast recovery fallback.
- Canary traffic catches issues early while requiring protection of single-writer ownership.

## 17. Illustrative ADR — Booking Platform Failback from Region B to Region A

> **Context:** Region A suffered an outage and failed over to B. Over 36 hours, B processed bookings, cancellations, and payment statuses. A recovered, yet its database replica trails B and A's application runs older images/config.
>
> **Option A:** Switch DNS back to A as soon as health checks turn green. Fast to execute, yet risks serving stale data, missing objects/events, and creating split-brain if writer B stays active.
>
> **Option B:** Keep B as writer, restore A as a replica, sync B → A, reconcile transactions, fence B at cutover, and promote A.
>
> **Illustrative Decision:** Choose B. B stays authoritative during preparation. Cut over only when replication positions catch up, data checks pass, dependency parity is reached, and A's capacity is confirmed.
>
> **Cutover:** Pause writes for a brief window, drain requests, finish final sync, fence B, promote A, and shift traffic by cohort.
>
> **Rollback:** Before A accepts writes, abort and keep B. After A accepts writes, any return to B is treated as a fresh failover with A → B reverse sync.
>
> **Verification:** Booking/payment reconciliation, event deduplication, object checksums, auth/KMS, p95/p99, queue backlogs, canary, and failback abort drill.
>
> **Closure Criteria:** A meets stable SLOs, A → B replication is re-established, B regains DR readiness, emergency access is revoked, and timeline/action items are recorded.

## 18. Practice Exercise: Failback After 24 Hours Running in DR

A booking platform uses Region A as primary and Region B as warm standby. A suffers an infrastructure outage and operations successfully fails over to B. Over 24 hours, B processes:
- 18,000 new bookings and booking updates.
- 2,500 cancellations.
- 7,000 payment status events.
- 40,000 notification events, with some landing in the DLQ.
- 600 GB of object uploads.
- One configuration update and one hotfix container version.

A comes back online. Database A is running, yet the old replication relationship is broken. DNS health checks report A healthy. The team wants to fail back today.

**Requirements:**
1. Identify readiness conditions to verify before starting.
2. Build an inventory of data to replicate, rebuild, replay, or reconcile.
3. Specify during which phases B remains the writer.
4. Propose reverse replication and how to measure catch-up.
5. Design reconciliation for bookings, cancellations, and payments.
6. Handle notifications/DLQ to avoid duplicate sends.
7. Verify the 600 GB of object uploads and metadata.
8. Sync the hotfix container, config, schemas, identity, and secrets.
9. Design cutover, fencing, and traffic migration.
10. Describe rollback before and after A accepts writes.

### Solution Guidance

- DNS health checks prove only partial reachability; verify outage root cause, database, networking, identity, KMS, secrets, registries, capacity, and synthetic business flows.
- Keep B as authoritative writer until reverse sync and reconciliation complete.
- Transactional data requires replication/change streams per database semantics and transaction positions. Caches can rebuild; search indexes rebuild or catch up; events must preserve event IDs, offsets, and ordering.
- Reconcile bookings/cancellations/payments by business invariants and transaction references, not merely row counts.
- For notifications, inspect event IDs, provider delivery status, and DLQs; consumers must be idempotent before replay.
- For objects, compare inventories, versions, checksums, metadata, ACLs, and encryption key references; mark files `COMPLETE` only when real objects are readable.
- Compare image digests, config revisions, DB schemas, secret versions, IAM policies, and feature flags; deploy only approved artifacts.
- Cut over via maintenance/admission control if needed, drain writes, record final replication position, wait for A to catch up, fence B, promote A, canary traffic, then open fully.
- Before A accepts writes, abort cutover and keep B. After A accepts writes, returning to B requires A → B sync and a fresh failover, not just switching DNS.

### Self-Check Questions

1. Why can failback not be performed simply by pointing DNS back to the old region?
2. After failover, why does the DR region usually hold the authoritative data?
3. How does reverse replication differ from restoring a backup?
4. Is zero replication lag enough to prove data consistency?
5. How can split-brain happen during switchover?
6. How do fencing tokens protect the system from an old writer?
7. Why is business reconciliation required beyond comparing row counts?
8. Which data can be rebuilt rather than replicated?
9. Why must image/config/schema drift be checked before failback?
10. How does pre-cutover rollback differ from rollback after the target region has accepted writes?
11. Which shared dependencies can make an old region look healthy yet remain unready?
12. What evidence is required to declare the system back to normal operations?

Safe failback is a process of **controlled data ownership and traffic handoff.** Keep the DR region authoritative while recovering, reverse-syncing, and reconciling data, verify dependency/config parity, and only then fence the current writer, promote the target region, and shift traffic in stages. Close only once SLOs, consistency, security, observability, and renewed DR readiness are verified.
