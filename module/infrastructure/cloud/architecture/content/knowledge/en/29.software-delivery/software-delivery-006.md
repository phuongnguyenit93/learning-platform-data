# Application Rollback, Data Roll-Forward, and Recovery Limits

A new release can slow down an API, cause processing errors, or produce incorrect business results. The instinctive reaction is to roll back to the previous application version. However, if the new version altered the database schema, wrote data in a new format, emitted new events, or triggered external side effects, reverting old code alone may fail to restore the system. Old code might fail to read new data, misunderstand new events, or overwrite valid changes that already occurred.

**Application rollback** reverts the runtime or traffic to a prior software version. **Data roll-forward** advances data or schemas into a valid, compatible state through corrective migrations, transforms, or controlled replays. **Restore** recovers data from a backup or point-in-time recovery snapshot to an earlier moment. These three operations serve distinct purposes and are not freely interchangeable.

This lesson belongs to the **Software Delivery** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to design post-deployment recovery plans that protect data and transactions, understand rollback limits once state has mutated, choose appropriately among rollback, roll-forward, and restore, and organize release pipelines, migrations, verification, and operations according to Well-Architected principles.

## 1. Code Rollback Does Not Equal Data Rollback

Applications, schemas, and data evolve over time, and they cannot always rewind together.

Example:
- Version 1 reads the `phone_number` column.
- Version 2 adds `phone_e164` and begins writing both columns.
- Version 3 stops writing `phone_number` and reads only `phone_e164`.
- Later, Version 3 is found defective and the team wants to revert to Version 1.

If new records were written only to `phone_e164`, Version 1 will read an empty or deleted `phone_number`. Rolling back code does not magically repopulate old columns.

Similarly, a release can:
- Modify enums or JSON payloads stored in the database.
- Emit new event schemas to consumers.
- Execute migrations that drop or merge columns.
- Send emails, payment requests, webhooks, or notifications.
- Create transformed files or write new object versions.
- Change cache keys, session formats, or token claims.
- Update models or configurations that the old version cannot parse.

~~~mermaid
flowchart TB
    R1["Release N<br/>Old application"] --> D1[("Database schema/data N")]
    R2["Release N+1<br/>New application"] --> M["Migration / new writes"]
    M --> D2[("Database schema/data N+1")]
    D2 --> Q{"Rollback app N safe?"}
    Q -->|"Compatible"| R1
    Q -->|"Incompatible"| F["Forward-fix / transform / restore"]
    F --> D3[("Compatible corrected data")]
    D3 --> R1
~~~

A release plan must evaluate at least four dimensions:
1. **Application compatibility:** does old code work with current dependencies and schemas?
2. **Data compatibility:** can new data be safely read and updated by old code?
3. **External side effects:** can transactions already dispatched externally be reversed?
4. **Operational state:** are caches, queues, sessions, feature flags, and configs compatible?

## 2. Distinguishing Rollback, Roll-Forward, Restore, and Replay

| Action | What Changes | When Typically Used | Limitations |
|---|---|---|---|
| Application rollback | Reverts code/image/traffic to prior version | Regression caused by new code or config | Does not automatically revert schemas, data, or side effects |
| Roll-forward | Advances schema/data/code to a valid state | Migration already ran; rollback is unsafe | Requires accurate migration, testing, and approval |
| Backup restore | Recovers data from a backup snapshot | Corruption, accidental deletion, disaster | May lose writes after the recovery point |
| Point-in-time recovery (PITR) | Restores database to a specific timestamp | Need to rewind before a faulty operation | Involves downtime/cutover and reconciling post-recovery transactions |
| Event replay | Reprocesses events to rebuild state | Rebuilding projections or backfilling data | Risks duplicates and side effects if not idempotent |
| Compensating transaction | Issues an offsetting business operation | Side effects whose history cannot be erased | Not every action can be reversed |
| Forward-fix | Ships a subsequent patched release | Defect can be fixed in a new version | Requires blast-radius and data-integrity controls |

Rollback operates on software versions. Restore operates on stored data. Roll-forward repairs current state. Replay and compensation recover along business workflows.

Never choose restore merely because a code rollback fails. Restoring can wipe out legitimate transactions committed after the backup point. Assess impact and recovery points first.

## 3. Scoping and Classifying Incidents Before Recovery

Before acting, classify the failure:
- **Code regression:** new logic is buggy while schemas and data remain compatible.
- **Configuration regression:** faulty feature flag, environment variable, policy, or routing.
- **Schema migration failure:** migration failed mid-way or created an incompatible schema.
- **Data corruption:** data was written incorrectly or accidentally deleted.
- **External side effect:** payments, emails, webhooks, or events already dispatched.
- **Dependency failure:** database, queue, identity, network, or third-party outage.
- **Security incident:** unauthorized data access or tampering; requires containment and evidence preservation.
- **Capacity/performance regression:** the new release consumes excessive resources.

Each failure class demands a different recovery path. For a security compromise, rolling back the application may restore clean code but does not revoke leaked credentials or remove persistence. For data corruption, a code forward-fix stops new errors but does not automatically repair corrupted records.

### 3.1. Triage Checklist

1. Which services or workflows are affected?
2. Which deployment, config change, or migration triggered it?
3. Is the fault in a code path, schema, data, events, or an external dependency?
4. What data has been written, deleted, or transformed?
5. Are there in-flight transactions or unprocessed queue messages?
6. Is the previous version compatible with the current schema and data?
7. Have external side effects already been emitted?
8. Can traffic or writes be paused, or functionality degraded?
9. What is the recovery objective: availability, consistency, or zero data loss?
10. Is forensic preservation or auditing needed before mutating the system?

Never initiate a rollback without knowing how far migrations progressed. Some migrations run in batches, some run in atomic transactions, and some commit partially. Inspect migration history and actual database state first.

## 4. Designing Backward-Compatible Migrations

A core strategy is maintaining compatibility across multiple application versions over a transition window. This allows rolling deployments, canaries, and code rollbacks without immediately reversing schemas.

### 4.1. Expand–Contract Pattern

**Expand** adds new structures while keeping old ones so current and new versions operate together. **Migrate** shifts data or traffic gradually to the new representation. **Contract** removes old structures only after all consumers have migrated and the rollback window closes.

~~~mermaid
flowchart LR
    E["1. Expand<br/>Add new column/table"] --> D["2. Dual-read/write<br/>Backfill and validate"]
    D --> S["3. Switch consumers<br/>Read new structure"]
    S --> W["4. Stop legacy writes"]
    W --> C["5. Contract<br/>Remove old structure"]
~~~

Example: migrating `phone_number` to `phone_e164`:

**Phase 1 — Expand**
- Add nullable `phone_e164`.
- Keep `phone_number`.
- Old code continues reading and writing `phone_number`.
- New code writes both columns using consistent logic.

**Phase 2 — Backfill**
- Transform historical records into `phone_e164` in batches.
- Enforce checkpoints, retries, and progress metrics.
- Validate parsing/normalization and handle invalid records.
- Avoid a single giant transaction on large tables.

**Phase 3 — Switch Reads**
- Deploy code reading `phone_e164`.
- Continue dual-writing during the compatibility window.
- Compare both columns and alert on mismatches.
- Code rollback still reads `phone_number` safely.

**Phase 4 — Stop Legacy Writes**
- Once all old instances stop serving traffic, stop writing `phone_number`.
- Observe across an adequate stabilization window.
- Confirm every job, report, and consumer has transitioned.

**Phase 5 — Contract**
- Drop `phone_number` only after no legacy consumers remain and the rollback window has closed.
- This step is difficult to reverse; require backups, approvals, and maintenance/online migration plans.

### 4.2. Why Is a Compatibility Window Necessary?

Rolling deployments temporarily run versions `N` and `N+1` simultaneously. Autoscaling or rollbacks can also spin up version `N` again. Batch consumers and workers often deploy on a different cadence than APIs. Therefore, the schema must support all coexisting versions—not just the latest one.

Compatibility windows must account for:
- Full fleet rollout duration.
- Worker and cron job update schedules.
- Queue backlogs and message retention periods.
- Autoscaling or scale-to-zero cold starts launching older images.
- Rollback windows and defect detection times.
- External consumers or partner APIs.

## 5. How Reversible Are Migrations?

Not every migration can be safely reversed.

| Migration | Reversibility | Rationale |
|---|---|---|
| Add nullable column | Generally easier | Old column remains; no data lost |
| Add new table/index | Schema rollback possible if unused | Check locking impact and consumers |
| Add enum value | Can be hard to remove | Records using new values may break old code |
| Rename column | Unsafe while old app versions run | Requires compatibility views or add-copy-switch |
| Drop column/table | Hard or impossible without backups | Data has been removed |
| Change type with lossy conversion | May lose precision or information | Original values cannot be reconstructed accurately |
| Merge/split records | Requires mapping and reconciliation | Original relationships may no longer be intact |
| Re-encrypt / re-key | Depends on key/version retention | Cannot decrypt if old keys are destroyed |
| Delete objects/files | Recoverable only with versioning/backups | Prior versions may not exist |
| Send payment/email/webhook | Cannot be rolled back via code | Side effects already occurred externally |

Having a `down` script does not prove data rollback is safe. `down` scripts must be tested against production-like data, realistic scale, and edge cases. If a migration is lossy, do not label it reversible.

### 5.1. Destructive Migrations

Before dropping or overwriting data:
- Identify every consumer.
- Take appropriate backups or snapshots.
- Verify restore paths and encryption key access.
- Archive retained data or mapping tables.
- Run row-count, checksum, and invariant checks.
- Obtain formal approval.
- Define the point of no return.
- Close the rollback window deliberately.

Never combine a destructive schema change and an application deployment in a single step without a verified recovery path.

## 6. Deciding Whether an Application Rollback Is Safe

Before reverting to an older version, verify:

| Question | If Not Met |
|---|---|
| Can the old version run against the current schema? | Do not roll back code; forward-fix or apply compatibility migration |
| Can the old version parse new events/messages? | Keep new consumers or transform/replay messages |
| Can the old version read/write new data without data loss? | Block the old version from writing to that dataset |
| Are caches, sessions, and tokens still compatible? | Perform controlled invalidation/translation or deploy a compatibility layer |
| Can already-emitted side effects be handled? | Reconcile or compensate; never assume rollback undoes them |
| Are artifacts, configs, and secrets ready for the old version? | Re-stage runtime prerequisites before shifting traffic |
| Would rolling back reintroduce a security vulnerability? | Prefer a forward-fix or a patched prior build |
| Can you canary and observe post-rollback? | Design progressive traffic shift and stop criteria |

For a pure code regression with a compatible schema, rollback is usually the fastest recovery path. If migrations broke compatibility, a forward-fix or data recovery may be safer.

## 7. Blue–Green, Canary, and Traffic Rollback

Your deployment strategy governs rollback speed and blast radius.

### 7.1. Blue–Green Deployment

Two environments coexist:
- Blue is the currently serving version.
- Green is the newly deployed and verified version.
- Traffic switches from Blue to Green after readiness checks pass.
- On failure, traffic can switch back to Blue rapidly.

The advantage is rapid traffic rollback when both versions are compatible with shared data and dependencies. However, blue–green does not automatically provide an isolated, safe database copy. If Green wrote an incompatible schema or executed external side effects, routing traffic back to Blue remains dangerous.

### 7.2. Canary Rollout

Shift a small slice of traffic to the new version, monitoring SLIs/SLOs and business metrics before expanding.

~~~mermaid
flowchart LR
    U["User traffic"] --> R["Traffic router"]
    R --> OLD["Version N"]
    R --> NEW["Version N+1<br/>Canary 5%"]
    NEW --> M["Metrics / error / business checks"]
    M --> D{"Healthy?"}
    D -->|"Yes"| G["Increase traffic gradually"]
    D -->|"No"| B["Stop rollout / route back"]
~~~

Canaries reduce blast radius, but watch out for pitfalls:
- 5% of traffic may not represent critical tenants or regions.
- Database migrations may affect the entire database even when canary traffic is small.
- Background workers might run at 100% even if the API receives only 5%.
- New event consumers might process all queued events before API traffic increases.
- Routing traffic back does not undo writes already committed.

### 7.3. Rolling Deployment

Instances are replaced incrementally. Multiple versions operate concurrently throughout the rollout. APIs, schemas, caches, events, and sessions must remain cross-version compatible during the rollout window.

Enforce readiness/liveness probes, graceful shutdown, `maxUnavailable`, surge capacity, and version-distribution monitoring. If old and new versions are incompatible, rolling deployments can fail even when each version works cleanly in isolation.

## 8. Roll-Forward and Forward-Fix

Roll-forward fits scenarios where the system has already accepted new data/schemas or where rollback poses excessive risk.

Forms include:
- **Code forward-fix:** ship the next patched release while preserving the current schema.
- **Compatibility patch:** add an adapter or dual-read logic so old and new versions both succeed.
- **Forward data transform:** normalize malformed records into the valid format.
- **Forward schema migration:** add columns, indexes, tables, or compatible adjustments to resolve issues.
- **Event compensation:** emit compensating events or commands to correct downstream state.
- **Config/feature flag change:** disable the faulty code path without redeploying if flags were designed in.

A forward-fix should:
1. Halt further erroneous writes.
2. Identify the exact dataset affected.
3. Preserve necessary evidence and snapshots.
4. Design idempotent, resumable repair migrations.
5. Test against a representative copy of the data.
6. Verify invariants and transform results.
7. Deploy via canary or controlled rollout.
8. Monitor data correctness and business outcomes.
9. Reconcile records processed earlier.
10. Document the change/incident and exit criteria.

Never execute ad-hoc data-repair scripts directly on production without dry runs, checkpoints, backups, and resume/rollback procedures.

## 9. Database Restore and Point-in-Time Recovery

When data is corrupted or accidentally deleted, restore or PITR may be required. However, restores reconstruct a database as of an earlier timestamp and do not automatically merge valid transactions committed afterward.

~~~mermaid
flowchart LR
    T0["Last known good backup"] --> LOG["Transaction logs / WAL"]
    LOG --> PITR["Replay to selected time T"]
    PITR --> DB["Recovered database"]
    DB --> V["Validate and reconcile"]
    V --> CUT["Controlled cutover"]
~~~

A PITR workflow requires:
- Pinpointing when corruption or the faulty operation began.
- Selecting a recovery point immediately prior to that time.
- Verifying backup chains and complete transaction logs/WALs.
- Restoring into an isolated environment.
- Running integrity checks and business validation queries.
- Comparing transactions committed after the recovery point.
- Deciding whether to replay, import, or compensate valid post-cutoff transactions.
- Cutting over traffic per plan while retaining the damaged instance for forensic analysis if needed.

### 9.1. Practical RPO of Restores

RPO does not depend solely on backup frequency. With PITR, recoverability also depends on log continuity, retention windows, replication state, and encryption key availability. If WAL/binlog segments are missing or expired, the desired recovery point may be unreachable.

### 9.2. Avoid Full-Database Restore When Scoped Recovery Works

Options include:
- Restore into a temporary database and export only the affected tables or rows.
- Recover a single partition or object prefix.
- Rebuild projections from an event log.
- Use audit logs or CDC streams to isolate mutations.
- Compensate transactions at the business-operation level.

Selective recovery minimizes reprocessing of valid transactions, though it increases operational complexity and demands deep knowledge of data relationships.

## 10. Post-Migration Data and Consumer Compatibility

An application may be compatible with the database yet incompatible with another service's events or APIs.

### 10.1. Event Schema Evolution

When evolving message schemas:
- Prefer adding optional fields with clear defaults.
- Never alter the type or semantics of existing fields still used by old consumers.
- Preserve schema versions and event IDs.
- Consumers must ignore unknown fields when contracts permit.
- Producers can dual-publish during a migration window when needed.
- Upgrade consumers before producers emit breaking schemas.
- Replays must be idempotent and handle legacy event formats.

For instance, adding `booking_source` to a `BookingCreated` event is generally safe, whereas changing `booking_id` from a string to an object is breaking. Once new events enter a queue, rolling back old consumers can cause deserialization failures or misinterpretation.

### 10.2. Queue Backlogs and Retries

When a new release emits messages in a new format:
- Keep consumers compatible or stop emitting the new format.
- Never purge a queue merely to clear errors.
- Route poison messages to a DLQ in a controlled manner.
- Replay after fixing consumers and confirming idempotency.
- Monitor message age, retry counts, and duplicate rates.

Purging queues destroys legitimate work; non-idempotent replays can send duplicate emails, payments, or webhooks.

## 11. Side Effects and Compensating Transactions

A business operation already committed in an external system cannot be undone by deploying old code.

Examples:
- A payment provider already captured funds.
- Confirmation emails were delivered.
- Webhooks were received by partners.
- Reservations became visible to partners or other users.
- Files were downloaded.
- Push notifications were sent to devices.

You may need a **compensating transaction**: a new business action offsetting an earlier outcome, such as refunding a payment or canceling a booking. Compensation does not erase history; it creates a new audited transaction with its own state.

Design for:
- Business-operation idempotency keys.
- Transactional outbox patterns.
- Provider references and reconciliation.
- Bounded retry policies.
- Saga state machines and explicit compensation steps.
- Manual review queues for ambiguous states.

Never issue automatic refunds solely because the application hit a timeout. The provider may have captured funds while the response was lost. Query provider state by reference before triggering compensation.

## 12. Feature Flags as a Behavioral Rollback Layer

Feature flags let you disable a feature or processing path without immediately swapping container images. Useful when:
- A new ranking model or algorithm misbehaves.
- An external integration becomes unstable.
- A new workflow must be paused temporarily.
- Traffic needs to fall back to legacy logic.

However, flags are also production configuration and carry risks:
- Flags may be cached too long or applied inconsistently.
- Legacy code branches may have gone untested.
- Flags do not undo database migrations or already-committed side effects.
- Accumulated flags create combinatorial complexity.
- Global flags can impact every tenant simultaneously.

Every flag needs an owner, purpose, default, scope, expiration/review date, audit trail, and tests for both states. Emergency flags require strict access controls and change logging.

## 13. Session, Cache, and Token Compatibility

Application rollbacks can fail at ephemeral state layers even when the database did not change.

Examples:
- The new version serializes sessions in a new structure.
- Cache keys change prefixes or payload formats.
- New required JWT claims are enforced.
- Refresh tokens rotate under a new policy.
- Workers store checkpoints in a modified format.

Mitigations:
- Use versioned cache and session formats.
- Read both current and prior formats during compatibility windows.
- Never require old versions to enforce newly added required claims before migration completes.
- Invalidate caches only if rebuilding is safe, evaluating cold-start database load first.
- Support session fallbacks or scheduled re-authentication notices.
- Overlap token signing and verification keys per rotation policy; never roll back keys carelessly.

Never treat a full cache flush as a universal cure for deployment bugs. Caches may hold business state, or mass invalidation can trigger a database stampede.

## 14. Artifact, Configuration, and Infrastructure Compatibility

Rollback works only if prior artifacts and environmental dependencies remain available.

Prepare:
- Immutably stored container images or packages for prior versions.
- Image digests, signatures, SBOMs/provenance, and runtime dependencies.
- Verified last-known-good configuration revisions.
- Matching secret references/versions without reckless secret copying.
- Database migration histories and compatibility matrices.
- IaC and provider versions if infrastructure changes are involved.
- Feature flag states and routing policies.
- Compatible certificates and trust bundles.
- Independent deploy/rollback permissions and pipelines.

Never roll back IaC by blindly applying an old commit. Infrastructure may have evolved incompatibly or contain newly provisioned resources. Inspect plans, state, and dependencies before modifying production infrastructure.

### 14.1. Last-Known-Good Is Not Any Arbitrary Old Build

A release that worked well months ago may not be safe today. It might:
- Contain a newly disclosed security vulnerability.
- Be incompatible with current schemas or APIs.
- Reference expired secrets or certificates.
- Fail to parse new data formats.
- Lack updated policies or dependencies.

Maintain an actively verified list of rollback-compatible versions rather than merely retaining old images.

## 15. Scenario Matrix: Rollback vs. Forward-Fix

| Scenario | Typical Response | Rationale |
|---|---|---|
| API code regression, schema unchanged | Application rollback | Fast, and data remains compatible |
| New feature failing, isolated behind flag | Disable flag | Fast mitigation without redeploying |
| Expand migration ran, new code fails | Code rollback usually viable | Schema still supports old version |
| Contract migration dropped column | Forward-fix / compatibility migration | Old version lacks required data |
| Partial faulty data transformation | Halt writers, snapshot, forward repair or selective restore | Prevents rollback from overwriting valid data |
| External payment already captured | Reconcile / compensate | Side effects cannot be erased by code |
| New event schema entered queue | Consumer compatibility, transform, or replay | Preserves events and avoids loss or duplicates |
| Secret/credential leaked | Revoke, rotate, and redeploy clean | Code rollback does not revoke exposed credentials |
| Widespread database corruption | PITR/restore and reconciliation | Needed to recover uncorrupted data |
| Security exploit in new release | Contain, roll back to patched build, or forward-fix | Never revert to an exploitable artifact |

This matrix is directional; final decisions depend on blast radius and data semantics.

## 16. Observability and Recovery Exit Criteria

During rollback or roll-forward, track both technical health and business correctness.

### 16.1. Technical Signals

- Deployment versions and traffic split.
- Request rates, p50/p95/p99 latencies, error rates, and timeouts.
- Database migration state, locks, replication lag, and connection pools.
- Queue depth, oldest message age, retries, and DLQ counts.
- Cache hit/miss rates, evictions, and warm-up load.
- Resource saturation and autoscaling behavior.
- Feature flag and config revisions.
- External provider latency, quotas, and response statuses.

### 16.2. Data and Business Signals

- Valid booking/payment state counts.
- Duplicate or orphan transactions.
- Post-transform row counts and checksums.
- Event publish vs. consume gaps.
- File/object availability and checksums.
- Workflow completion rates.
- Reconciliation mismatches.
- Pending side-effect compensations.
- Affected user/tenant cohorts.

Do not equate a green deployment status with incident resolution. Recovery completes only when services meet SLOs, data invariants pass, queues stabilize, side effects are reconciled, and owners sign off on the recovered state.

## 17. Reference Release Recovery Runbook

~~~text
PHASE 0 — TRIAGE
  - Identify release, config, migration and affected user journeys.
  - Freeze risky rollout and capture current versions.
  - Determine whether data/schema/external side effects changed.
  - Preserve logs, snapshots and relevant evidence.

PHASE 1 — CHOOSE RECOVERY PATH
  - Check old application compatibility with current schema/data/events.
  - If compatible, prepare application rollback.
  - If incompatible, stop writes or isolate affected workflow.
  - Choose forward-fix, data repair, compensation or PITR as needed.

PHASE 2 — PROTECT DATA
  - Confirm current source of truth and writer.
  - Take a verified snapshot where appropriate.
  - Record transaction/event positions and affected scope.
  - Check backup, key access and restore path.

PHASE 3 — EXECUTE
  - Roll back traffic/code, or deploy a forward-fix.
  - Run migration/data transform in bounded, resumable batches.
  - Keep operations idempotent and checkpoint progress.
  - Reconcile external provider and event side effects.

PHASE 4 — VERIFY
  - Check SLO, user journeys and business invariants.
  - Verify schema, row counts/checksums and queue status.
  - Check duplicate, orphan and pending compensation.
  - Confirm security, config and artifact versions.

PHASE 5 — CLOSE
  - Restore normal release controls.
  - Record incident timeline and data impact.
  - Remove temporary flags/access only after validation.
  - Update compatibility matrix, tests and runbook.
~~~

Runbooks must bind concrete commands to your specific database, orchestrator, and deployment platform, with expected outputs, owners, and stop conditions for every step. Never rely on generic pseudo-commands across different clouds or engines.

## 18. Well-Architected Trade-Offs

| Pillar | Good Design | Risks to Control | Evidence |
|---|---|---|---|
| **Reliability** | Compatibility windows, backups/PITR, canaries, forward recovery | Incompatible rollbacks, data loss, slow restores | Rollback drills, restore tests, reconciliation |
| **Security** | Clean artifacts, credential rotation, audits, evidence | Rollback reintroducing vulnerabilities, stale secrets, weak policies | Image provenance, IAM audits, key rotation |
| **Performance Efficiency** | Controlled cutovers, batched migrations, warm-ups | Restore load, cache stampedes, locks, migration lag | p95/p99 latency, DB load, queue age |
| **Cost Optimization** | Right-sized artifact/backup retention and scoped repairs | Oversized backups/retention, duplicate environments | Recovery cost, storage lifecycle policies |
| **Operational Excellence** | Runbooks, ownership, rollback criteria, postmortems | Tribal knowledge, manual heroics, lack of rehearsals | Drill success rates, MTTR, action items |
| **Sustainability** | Avoid full rebuilds/restores when narrow repairs suffice | Wasted compute/transfers, redundant replays | Resource utilization, transfer volume, replay counts |

Key trade-offs:
- Fast rollbacks lower downtime but risk data corruption if data has moved forward.
- Forward-fixes avoid rewinding data but require high confidence and strong testing.
- PITR restores a consistent point in time at the cost of discarding valid post-cutoff transactions.
- Expand–contract extends compatibility while increasing the duration of maintaining dual code/schemas.
- Canaries bound traffic blast radius but do not isolate cluster-wide database migrations.
- Dual-writes smooth transitions but risk divergence and require reconciliation.
- Frequent backups shrink potential RPO while raising storage, retention, and key-management costs.

## 19. Release Recovery Design Workflow

1. **Classify the release:** code, config, schema, data, events, infrastructure, and side effects.
2. **Define the compatibility matrix:** coexisting app, worker, consumer, and schema versions.
3. **Select migration patterns:** expand–contract, online migrations, batched backfills, or maintenance windows.
4. **Define rollback boundaries:** when code rollback remains valid and which migrations are irreversible.
5. **Protect data:** snapshots/backups, PITR, transaction log retention, and key access.
6. **Design forward-fixes:** idempotency, checkpoints, validation, and resumability.
7. **Control side effects:** outboxes, idempotency, provider references, and compensation.
8. **Stage rollback artifacts/configs:** verified compatible and security-patched last-known-good versions.
9. **Configure canaries and feature flags:** stop criteria, routing, and ownership.
10. **Define SLIs and business invariants:** concrete signals proving recovery succeeded.
11. **Write runbooks:** triage, decision trees, execution, verification, stop conditions, and rollbacks.
12. **Rehearse:** code rollbacks, failed migrations, PITR, event replays, and compensations.
13. **Close the recovery window:** contract or drop legacy structures only after consumers drain and rollback windows end.
14. **Review post-release/incident:** update tests, migration policies, and recovery assumptions.

### Pre-Production Release Checklist

| Item | PASS Criteria |
|---|---|
| Version compatibility | Prior version operates against schema/data throughout rollback window |
| Migrations | Expand–contract or maintenance strategy clearly defined |
| Reversibility | Destructive migrations flagged with verified recovery paths |
| Backups / PITR | Recovery points, log retention, and key access tested |
| Artifacts | Last-known-good images/configs retained and access-controlled |
| Events / APIs | Producer/consumer compatibility verified |
| Side effects | Idempotency, reconciliation, and compensation paths clear |
| Feature flags | Owners, scopes, defaults, expiration, and audits defined |
| Rollback criteria | SLIs, business impact thresholds, and decision owners assigned |
| Roll-forward | Tested forward-fix or data-repair patterns available |
| Validation | Data invariants, smoke tests, and SLO checks automated |
| Runbooks | Reviewed and rehearsed proportional to criticality |

## 20. Illustrative ADR — Changing the Booking Schema During a New Release

> **Context:** The Booking API currently stores `phone_number` and needs to standardize on `phone_e164`. The new release also updates the API response and emits `BookingUpdated` events with a new schema.
>
> **Option A:** Deploy new code and rename/drop `phone_number` in the same migration. Simpler short-term, but older versions cannot roll back if the release fails post-migration.
>
> **Option B:** Expand–contract. Add `phone_e164`, dual-write, backfill, shift reads, upgrade consumers, and drop `phone_number` only after closing the compatibility window.
>
> **Illustrative Decision:** Choose Option B. Deploy the schema expand step first; then ship API/workers reading the new structure while maintaining compatible writes. Event schemas add optional fields, and older consumers ignore unknown fields per contract.
>
> **Rollback:** Within the compatibility window, traffic can route back to the prior application version because `phone_number` remains populated. Never roll back consumers once queues contain incompatible messages.
>
> **Roll-Forward:** If dual-writes diverge, halt contraction, fix the transform, and re-backfill checkpointed rows without dropping the old column.
>
> **Validation:** Compare record counts, checksums/normalized values, invalid phone rates, event consumer lag, booking success, and API latency.
>
> **Contraction Criteria:** All APIs, workers, and consumers migrated, zero legacy reads/writes, reconciliation passing, and rollback window closed.

## 21. Hands-On Exercise: Failed Release After Schema Changes

The Booking Platform just deployed version 5.4:
- Added column `payment_status_v2` and backfilled from `payment_status`.
- The new API reads only `payment_status_v2`.
- The new worker emits `PaymentCaptured` events with schema version 2.
- Some payments have already been captured at the provider.
- After 15 minutes, confirmation failure rates spike sharply.
- Version 5.3 remains in the artifact registry, but it reads only `payment_status` and understands only event schema version 1.
- Several consumers have not been upgraded yet.

**Tasks:**
1. Determine whether you can immediately roll back the API to 5.3 and which conditions must be checked.
2. Assess migration status and whether new writes went exclusively to the v2 column.
3. Design a way to retain `PaymentCaptured` v2 events without crashing or confusing older consumers.
4. Decide on code rollback, forward-fix, or a combination.
5. Reconcile payments that were captured while confirmations failed.
6. Handle event queues, retries, and DLQs without causing duplicate side effects.
7. Define the exact criteria required before dropping legacy `payment_status`.
8. Write a runbook and recovery exit criteria.

### Solution Guide

- Do not route all API traffic back to 5.3 before verifying that `payment_status` continued receiving dual-writes and all necessary records hold compatible values.
- If the schema is still in the expand stage and the old column has complete data, you may canary-roll back the API; workers and consumers must be evaluated independently.
- If the provider already captured payment while confirmation failed, query the provider transaction reference before retrying captures or issuing refunds.
- Preserve v2 events in the durable queue; upgrade consumers to handle both v1 and v2, or apply versioned message transforms preserving event IDs. Never purge the queue.
- A forward-fix can repair mapping/confirmation in API 5.4.x while keeping the expanded schema; pick the lowest-risk option based on actual data state.
- Reconcile provider settlements, database payment states, outbox events, consumer offsets, and DLQs. Enforce idempotency keys to avoid duplicate captures or notifications.
- Drop `payment_status` only after all apps, workers, and consumers have migrated, legacy reads/writes hit zero, reconciliation passes, and the rollback window closes.
- Close recovery only when booking/payment workflows meet SLOs, no ambiguous states remain, queue backlogs/DLQs are resolved, data invariants pass, and owners approve.

### Self-Check Questions

1. Why does rolling back code not automatically restore a database?
2. How do rollback, roll-forward, restore, and replay differ?
3. How does expand–contract maintain compatibility between old and new versions?
4. Why is dropping a column a difficult point of no return?
5. When is a forward-fix safer than PITR?
6. Why can PITR lose valid transactions committed after the recovery point?
7. Can canary traffic isolate a database-wide migration?
8. How should new-schema events sitting in a queue be handled when rolling back consumers?
9. Why does a payment timeout not imply the provider failed to capture?
10. How does compensation differ from rollback?
11. What can feature flags revert, and what can they not?
12. What conditions authorize the contract phase to delete legacy structures?

Release recoverability depends on understanding what changed and what can safely be undone. **Application rollback is safe only when old code remains compatible with current schemas, data, events, and dependencies.** Once data or external side effects have moved forward, recovery typically requires forward-fixes, compatible migrations, reconciliation, or compensation; restore/PITR should be used only with a clear recovery point and plan to preserve valid transactions. Expand–contract design, tested backups, idempotency, canaries, and runbooks help teams recover from faulty releases without turning a deployment bug into a larger data-loss incident.
