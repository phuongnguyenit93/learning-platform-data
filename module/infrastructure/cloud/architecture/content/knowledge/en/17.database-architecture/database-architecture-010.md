# Data Migration, Reconciliation, and Integrity Verification

## 1. Why Does Migration Require a Verification Process?

Data migration is the transfer of data and business serving capability from a source to a target: changing database engines, upgrading versions, moving to the cloud, splitting a monolith into services, changing schemas, or moving historical data onto a new platform. The job does not end when a copy command returns success. A system can transition to its new operating state only after proving target data is complete, semantically accurate, consistent, and ready for applications to continue processing business transactions.

A migration faces many risks:

- Records missing, duplicated, truncated, or cast to wrong types.
- Broken table relationships, foreign keys, or logical references.
- Source mutations occurring mid-copy so the snapshot and target reflect different points in time.
- New schemas interpreting timestamps, currencies, collations, nulls, or encodings differently from the source.
- Triggers, sequences, identities, defaults, indexes, constraints, or permissions not migrated properly.
- CDC or dual-writes dropping changes, applying out of order, or replaying the same change repeatedly.
- Cutover finishes while an application, report, background job, or consumer still writes to the old source.
- Rollback becomes non-trivial because new writes have already occurred on the target system.

Therefore, a migration plan must answer four questions: **what moves, how it moves, how correctness is proven, and what happens when discrepancies are found?**

In the **CLOUD_ARCHITECTURE** module, data migration must be designed as an architectural change affecting reliability, security, scalability, cost, and operations. Reconciliation and integrity verification form the evidence base for deciding whether to proceed with cutover, pause, or recover.

### Learning Objectives

After this lesson, you can:

1. Build an inventory of data, dependencies, schemas, and downtime constraints before migrating.
2. Choose offline migration, online migration, snapshots, replication, or CDC.
3. Design an expand-migrate-contract strategy and controlled cutover.
4. Design batching, checkpoints, retries, and safely re-runnable migration jobs.
5. Reconcile counts, aggregates, checksums, keys, relationships, and business invariants.
6. Handle ongoing mutations during migration, duplicate events, and source/target drift.
7. Prepare rollbacks, ongoing reconciliation, observability, and acceptance criteria.

## 2. Distinguishing Migration, Replication, Synchronization, and Reconciliation

These terms are related but not synonymous:

| Concept | Purpose | Example |
|---|---|---|
| **Migration** | Move data or workloads to a new system, schema, or location | Database moving from VM to managed database |
| **Replication** | Maintain copies of data from source to one or more targets | Read replica receiving transaction logs |
| **Synchronization** | Keep two datasets aligned under defined rules | Syncing customer profiles between two services |
| **CDC (Change Data Capture)** | Capture source changes occurring after a checkpoint | Reading WAL/binlog/change streams and applying to target |
| **Reconciliation** | Compare data or outputs across sides to detect drift | Comparing daily booking totals and listing mismatched records |
| **Integrity verification** | Verify data remains intact structurally and semantically | File checksums, constraints, per-batch hashes |

Replication can run smoothly while the target is still wrong due to schema mappings or transformation bugs. Two systems can share identical record counts while holding different field values. Identical checksums on dump files do not prove the application queries and calculates correctly post-import. Multiple verification layers are therefore essential.

## 3. Start with Inventory and Impact Analysis

Never pick tools before knowing which datasets and dependencies must move.

### 3.1. Data Inventory

For each dataset/table/collection/file group, record:

| Attribute | Details to Gather |
|---|---|
| Owner | Business and technical owning teams |
| Source / destination | Systems, databases, schemas, buckets, regions |
| Volume | Record/object counts, storage size, growth rate |
| Change rate | Inserts/updates/deletes per second or per day |
| Access patterns | Reads/writes, primary queries, batch jobs, and reports |
| Schema | Columns/types, indexes, keys, constraints, enums, collations |
| Relationships | Foreign keys, logical references, joins, event contracts |
| Sensitivity | PII, payment data, secrets, classification |
| Retention | Retention windows, legal holds, deletion rules, and copies |
| Downtime tolerance | Acceptable maintenance/outage window |
| Recovery | RPO, RTO, and fallback options |
| Validation | Counts, aggregates, checksums, invariants, and sample queries |

### 3.2. Dependency Inventory

A database is rarely used by just one API. Find every component that reads or writes:

- Web/mobile APIs and internal services.
- Background workers, scheduled jobs, and serverless functions.
- Data warehouses, BI dashboards, ETL/ELT pipelines, and exports.
- Search indexes, caches, materialized views, and read replicas.
- Webhooks, event consumers, integration partners, and reconciliation jobs.
- Admin consoles, manual scripts, and operational tasks.

Missing a single writer means post-cutover it keeps writing to the old source, forking data. A missed reader may continue displaying stale data after the primary API cuts over.

### 3.3. Profiling Data Characteristics

Inspect upfront:

- Are primary keys unique, stable, and non-null?
- Are there missing foreign keys or references pointing to deleted objects?
- Are there timezone-naive timestamps, decimal precision quirks, negative numbers, extreme values, or special encodings?
- Are there business-key duplicates despite distinct primary keys?
- Are there engine-specific triggers, stored procedures, generated columns, sequences, identities, or defaults?
- Are there long transactions, lock contention, table partitions, large objects, or compressed blobs?
- Are there row-level security, encryption, collations, case-sensitivity, or sort-order differences?

This catches engine incompatibilities before they turn into corrupted data after cutover.

## 4. Choosing a Migration Strategy

### 4.1. Offline Migration (Maintenance Window Cutover)

Applications pause writes or enter maintenance mode; data is exported, transformed, imported, verified, and service resumes on the target.

**Fits when:** datasets are small/medium, downtime is acceptable, maintenance windows are clear, or change rates are low.

**Pros:** simpler workflow, uses a single consistent snapshot, avoids concurrent sync complexity.

**Trade-offs:** downtime scales with volume, export/import speed, and verification time. If migration fails, you keep serving from the source or restore from backup.

### 4.2. Online Migration (Minimizing Downtime)

Copy a baseline while the source keeps serving, while capturing ongoing changes to bring the target near real-time parity. At cutover, briefly pause or fence writes, wait for lag to drain below threshold, verify, and shift traffic.

**Fits when:** databases are large, writes are continuous, downtime tolerance is low, or business availability demands are high.

**Trade-offs:** higher operational complexity; must handle transaction ordering, deletes, schema changes, duplicates, lag, consistency, and failure recovery.

### 4.3. Comparing Transfer Methods

| Method | Characteristics | Key Risks |
|---|---|---|
| Full export/import | Dump everything and load into target | Downtime, snapshot consistency, speed, and dump storage |
| Snapshot/backup restore | Create consistent snapshot and restore | Engine/version compatibility, log replay, restore duration |
| Replication | Source continuously streams changes to target | Lag, format/version compatibility, failover behavior |
| CDC | Captures changes from transaction logs/change streams | Checkpoints, offsets, ordering, schema evolution, duplicates |
| App-level dual-write | Application writes to both source and target | Partial success, transaction differences, retries |
| Bulk batch migration | Transfers by key range/partition/time window | Batch boundaries, checkpoints, skipped or duplicated rows |

No single approach fits every dataset. Combining bulk load for the baseline, CDC for deltas, and reconciliation before cutover is common.

## 5. Online Migration Strategy: Baseline + CDC

High-level flow:

~~~mermaid
flowchart TD
    Source[("Source database")]
    Snapshot["Consistent snapshot + watermark"]
    Bulk["Bulk copy / transform"]
    Target[("Target database")]
    Log["Transaction log / change stream"]
    CDC["CDC capture + apply"]
    Reconcile["Reconciliation"]
    Cutover["Controlled cutover"]
    Source --> Snapshot
    Snapshot --> Bulk
    Bulk --> Target
    Source --> Log
    Log --> CDC
    CDC --> Target
    Target --> Reconcile
    Reconcile --> Cutover
~~~

Reference workflow:

1. Establish a snapshot/watermark tied to a transaction log or CDC position.
2. Export the baseline from the consistent snapshot.
3. Load the baseline into the target in checkpointed batches.
4. Capture all changes occurring after the watermark.
5. Apply CDC events to the target while preserving supported ordering and transaction semantics.
6. Monitor replication lag, apply errors, skipped records, and schema compatibility.
7. Run continuous reconciliation across source and target.
8. Pause writers or engage a write fence at cutover time.
9. Wait for the final delta to apply, verify invariants, and shift traffic.
10. Monitor the target while keeping the source read-only/standby during the approved rollback window.

Watermarks must use the tool's true position semantics: log sequence numbers, binlog positions, change tokens, or snapshot IDs. Never substitute an arbitrary wall-clock timestamp when concurrent transactions can commit out of timestamp order.

## 6. Schema Migration and Expand-Migrate-Contract

Data migrations frequently accompany schema changes. Abrupt schema changes can break old or new application versions.

The **expand-migrate-contract** pattern stages changes:

1. **Expand:** add new columns/tables/indexes compatibly without removing legacy fields.
2. **Dual-compatible application:** applications read/write old and new schemas under a controlled strategy.
3. **Backfill:** migrate historical data to new fields/schemas in batches.
4. **Verify:** confirm new data is complete and applications read accurately.
5. **Switch reads/writes:** shift code paths to the new schema while watching for drift.
6. **Contract:** drop legacy columns/tables/APIs only after verifying zero consumers or writers remain.

~~~mermaid
flowchart LR
    A["Old schema"] --> B["Expand: add new schema"]
    B --> C["App compatible with both"]
    C --> D["Backfill old data"]
    D --> E["Verify and switch traffic"]
    E --> F["Contract: remove old schema"]
~~~

### Example: Adding a New Column

Suppose `full_name` is being replaced by `display_name`:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200);
~~~

Do not drop `full_name` immediately. New code reads `display_name` if populated and falls back to `full_name`; backfills populate older rows; only after all clients switch and data is verified do you schedule the contract step.

### Notes on Dual-Writing Fields

If applications write both old and new fields, they can diverge when one write succeeds and the other fails. Define a single authoritative field, retry/reconciliation rules, and a sunset plan for dual-writes. For major schema shifts, prefer CDC or checkpointed/versioned backfills over relying indefinitely on dual-write logic across multiple app versions.

## 7. Batch Processing, Checkpointing, and Idempotency

At large scale, batching bounds memory usage, transaction duration, and retry scope. Batch boundaries must be explicit.

### 7.1. Choosing a Batch Key

Partition batches by:

- Primary key ranges when keys are stable and well-distributed.
- Time windows when timestamps are reliable and late-arriving records are rare.
- Native database partitions.
- Hash buckets when uniform load distribution is needed.

Avoid large `OFFSET` pagination, which degrades in performance and shifts positions as source rows are inserted or deleted. Keyset pagination over a stable key is much easier to checkpoint.

### 7.2. Checkpoints

Each batch should record at least:

| Field | Meaning |
|---|---|
| `migration_id` | Migration run identifier |
| `dataset`/`table` | Data scope |
| `lower_bound` / `upper_bound` | Key range or partition processed |
| `source_watermark` | Source position or CDC offset |
| `status` | `PENDING`, `RUNNING`, `VERIFIED`, `FAILED` |
| `rows_read` / `rows_written` | Source and target record counts |
| `checksum`/`aggregate` | Batch verification proof |
| `attempt` | Execution attempt number |
| `started_at` / `completed_at` | Timing telemetry |
| `error_reference` | Error link/log reference without secrets |

### 7.3. Safely Re-Runnable Jobs

Migration jobs must be idempotent or track batch completion cleanly. Deterministic keys and controlled upserts help, though upserts alone do not resolve conflicts if source records change after the watermark.

Rules:

- Never mark a batch `VERIFIED` before verifying target records.
- If a job crashes after writing the target but before saving the checkpoint, reruns must detect or handle duplicates safely.
- Never use worker wall-clock timestamps as sole proof of data ordering.
- Record counts of rejected, quarantined, or skipped rows; never drop records silently.
- Rate-limit workers so neither source nor target exhausts connections, IOPS, or throughput.

~~~text
for each key_range in migration_plan:
    if checkpoint[key_range] == VERIFIED:
        continue

    source_rows = read_source_consistently(key_range)
    transformed = transform_and_validate(source_rows)
    write_target_idempotently(transformed)

    result = compare_batch(source_rows, transformed, target_rows)
    if result.matches:
        save_checkpoint(key_range, VERIFIED, result.metrics)
    else:
        save_checkpoint(key_range, FAILED, result.error_reference)
        stop_or_quarantine_according_to_policy()
~~~

This pseudocode shows control logic; exact snapshot, transaction, upsert, and checkpoint mechanics depend on your database and migration tooling.

## 8. Multi-Layer Data Reconciliation

A single check is rarely enough. Effective reconciliation progresses from macro counts down to field details and business invariants.

### 8.1. Layer 1 — Row/Object Counts

Compare record/object counts by dataset, partition, time window, and status.

Example:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM reservations
GROUP BY status
ORDER BY status;
~~~

Run matching logic on source and target at aligned snapshots/checkpoints. Two totals can match even when one record is missing and another is duplicated, so counts are only a first check.

### 8.2. Layer 2 — Aggregate Reconciliation

Compare aggregates such as:

- Sum of `amount` grouped by currency, status, and date.
- Booking counts by tenant/property.
- Min/max timestamps or IDs.
- Total quantities, balances, or counts per partition.
- Counts of nulls, out-of-range values, and business-key duplicates.

~~~sql
SELECT
    currency,
    status,
    COUNT(*) AS txn_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY currency, status
ORDER BY currency, status;
~~~

Never sum amounts across multiple currencies into one total without explicit FX conversion rules and rate timestamps. Decimal precision and rounding rules must also match.

### 8.3. Layer 3 — Key-Level Comparison

Diff primary/business key sets:

- Keys present in source but missing in target.
- Keys present in target but absent in source.
- Duplicates by business key.
- Keys altered/truncated or reformatted during transform.

For huge datasets, partition the key space and use anti-joins, hash buckets, or manifests. Always compare at aligned snapshots/CDC watermarks; comparing two live systems at slightly different times produces false mismatches.

### 8.4. Layer 4 — Field-Level Comparison

Compare critical fields per mapping rules:

- Nullability and defaults.
- Numeric types, precision, scale, and overflow limits.
- Timestamps, timezones, and sub-second precision.
- String encoding, Unicode normalization, collations, and case sensitivity.
- Enum/code mappings.
- JSON/document structures.
- Binary/blob payloads.

Byte-for-byte equality is not always necessary when migrating across engines with different storage formats but identical semantics. Define explicit canonicalization rules upfront to verify business equivalence.

### 8.5. Layer 5 — Referential and Business Invariants

Examples:

- Every `CONFIRMED` reservation must reference a valid property.
- Every payment capture must link to a valid payment intent/booking.
- Account ledger balances must equal total credits minus debits per rules.
- No property has two overlapping `CONFIRMED` bookings where policy forbids overlaps.
- Child record `tenant_id` matches parent `tenant_id`.
- Inventory quantities are never negative.

This is the most meaningful semantic check: datasets can match on counts and checksums yet still violate domain rules if transforms or mappings were flawed.

## 9. Checksums, Hashes, and Their Limits

Checksums/hashes detect payload differences, especially across files, batches, or objects.

### 9.1. Per-Batch Hashing

Conceptual workflow:

1. Select identical record sets by key range and source watermark.
2. Normalize fields under agreed canonicalization rules.
3. Serialize in deterministic field order and encoding.
4. Hash individual rows or chunks.
5. Compare aggregate/manifest hashes across source and target.
6. On mismatch, bisect chunks to isolate the differing records.

Never hash JSON with arbitrary key ordering and declare payloads different; require canonical serialization. Never put plaintext sensitive fields into manifests or logs.

### 9.2. File Checksums Do Not Prove Database Logic Is Right

When an export file hash matches after transfer, you only know file bytes did not corrupt in transit under that hash algorithm. That does not prove:

- The import loaded every row.
- Schema mappings were accurate.
- Indexes and constraints work.
- Triggers, defaults, and sequences were configured properly.
- Queries and business logic behave identically to the source.

Always pair checksums with row counts, aggregates, key comparisons, constraint checks, and application tests.

## 10. Referential Integrity and Load Ordering

When databases enforce foreign keys, load ordering and constraint strategies matter.

A typical load order:

1. Lookup/reference tables.
2. Parent/master entities.
3. Child/detail entities.
4. Association/join tables.
5. Ledger/event/history tables by dependency.
6. Materialized views, search indexes, and regenerable derived data.

Depending on the engine, you can defer constraints or disable and re-validate post-load. Never leave constraints disabled in production; explicitly verify all constraints are enabled and validated.

### Checking Orphan Records

~~~sql
SELECT r.reservation_id
FROM reservations r
LEFT JOIN properties p ON p.property_id = r.property_id
WHERE p.property_id IS NULL;
~~~

The expected result is zero orphans, unless business rules permit historical references preserved as snapshots or tombstones. Any exceptions must be explicitly documented rather than hidden by leaving constraints off.

### Duplicate Business Keys

~~~sql
SELECT tenant_id, external_reference, COUNT(*) AS duplicates
FROM payments
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;
~~~

Business keys must be defined per domain. Two records with different primary keys can still represent the exact same business transaction.

## 11. Migrating Continuously Changing Data: CDC and Ordering

CDC streams changes from source to target while live traffic runs. Understand:

- **Capture point:** are changes read from WAL/binlog/change feeds or triggers?
- **Checkpoints/offsets:** which position has been read and acknowledged?
- **Ordering:** is order preserved per partition, per table, or per transaction?
- **Deletes:** are deletes represented as tombstones or explicit delete events?
- **Schema evolution:** are column/type changes compatible with downstream consumers?
- **Duplicates:** can consumers receive replayed changes after restarts or failovers?
- **Backpressure:** if the target slows down, how fast does lag climb, and does source log retention threaten disk space?
- **Snapshot coordination:** do baseline snapshots and change streams avoid gaps and overlaps?

CDC typically provides at-least-once semantics or replayability depending on the tool. Apply processes must be idempotent or key off source transaction identities so replayed changes never corrupt state.

Never assume all events arrive in one global total order. Many pipelines preserve order only within a partition or key. If an entity needs strict serialization, design partition keys and apply logic around that entity.

## 12. Post-Cutover Reconciliation Jobs

Reconciliation does not run just once before cutover. During parallel operations or post-migration stabilization, run periodic jobs to catch drift.

A reconciliation pipeline:

~~~mermaid
flowchart TD
    Schedule["Scheduled reconciliation"] --> Scope["Select dataset / time window"]
    Scope --> Extract["Read source / target snapshot"]
    Extract --> Compare["Count + aggregate + key + invariant"]
    Compare --> Result{"Match?"}
    Result -->|Yes| Record["Record manifest and results"]
    Result -->|No| Classify["Classify mismatch"]
    Classify --> Repair["Repair / replay / manual review"]
    Repair --> Verify["Re-run reconciliation"]
    Verify --> Result
    Record --> Monitor["Dashboard / alert"]
~~~

### Classifying Mismatches

| Mismatch Type | Example | Remediation |
|---|---|---|
| Missing | Record exists in source, missing in target | Replay by key/checkpoint or reload batch |
| Extra | Record in target not in source | Determine whether duplicate, valid new write, or garbage |
| Value mismatch | Amount/timezone/status differs | Check transforms, rounding, mappings, and source of truth |
| Relationship mismatch | Invalid foreign key/reference | Restore parent, fix ID mapping, or handle orphan per policy |
| Timing mismatch | One side has newer changes | Wait for CDC catch-up or compare at aligned watermark |
| Business invariant violation | Negative inventory, payment lacking booking | Halt cutover or repair via audited domain workflow |

Never blindly overwrite source or target based solely on whichever has the newer timestamp. Verify which system is the source of truth per field and whether users/partners performed actions post-migration.

## 13. Cutover: Controlled Transfer of Serving Authority

Cutover is the moment traffic or write authority shifts from source to target. It carries the highest risk of creating split sources of truth.

### 13.1. Sequential Cutover Checklist

1. Freeze related schema and code changes except controlled migration steps.
2. Confirm backups and source recovery points are ready.
3. Verify target capacity, indexes, constraints, permissions, monitoring, and security.
4. Run baseline reconciliation and check CDC lag.
5. Announce maintenance/degraded mode if applicable.
6. Pause or fence all source writers; verify no stray writers remain.
7. Wait for in-flight transactions and CDC apply to reach the chosen watermark.
8. Run final validation on data and critical invariants.
9. Switch connection strings, DNS, routing, or feature flags per plan.
10. Execute controlled smoke and read/write tests.
11. Monitor error rates, latency, connections, constraint failures, and business flows.
12. Keep the source non-writable through the approved rollback window.

### 13.2. Write Fencing

A write fence blocks the old system from accepting writes after cutover. It can use maintenance mode, revoking write permissions, application feature flags, routing policies, or equivalent mechanisms. Flipping a flag in one API service is insufficient if batch jobs, admin scripts, or integrations still write directly.

### 13.3. Canary and Gradual Cutover

Where supported, shift a small percentage of traffic or a subset of tenants first. Ensure any single tenant/request has only one authoritative writer at a time. If some requests write to the source and others write to the target without bidirectional ownership/sync rules, data will diverge.

## 14. Rollback and Roll-Forward

Rolling back a migration is not always flipping a connection string back to the source. Post-cutover, the target may hold new writes absent from the source.

### 14.1. Pre- and Post-Cutover States

| Stage | Source | Target | Reversibility |
|---|---|---|---|
| Pre-baseline | Authoritative | Empty | No rollback needed |
| Baseline copy | Authoritative | Initial copy | Stop job and keep source |
| CDC catch-up | Authoritative + change capture | Updating replica | Can stop and fix pipeline while source owns writes |
| Final sync before cutover | Temporarily fenced writers | Caught up | Can reopen source if final validation fails |
| Post-cutover, target-only writes | Read-only/standby | Authoritative | Returning to source requires reverse migration/CDC or write replay |

### 14.2. When Is Roll-Forward Safer?

Once the target accepts new writes absent from the source, flipping back risks losing transactions. If the issue is an application bug or target misconfiguration fixable quickly, rolling forward may be safer. If rollback is mandatory:

- Stop/fence target writers.
- Identify all writes committed since cutover.
- Reverse-replicate or export/replay back to the source using verified mappings.
- Reconcile and verify invariants before reopening the source.
- Handle new IDs/sequences/transactions and external side effects.

Never promise bidirectional rollback unless reverse CDC and schema compatibility were explicitly designed and tested. Two schema versions may not invert cleanly.

## 15. Performance and Limits During Migration

Bulk copies, checksums, and CDC place significant load on both source and target.

### Parameters to Control

- Batch size and worker parallelism.
- Read/write throughput, IOPS, and network bandwidth.
- Connection pools and transaction sizes.
- Lock durations, replication log retention, and CDC lag.
- Index builds, constraint validation, and engine vacuum/maintenance.
- Snapshot/export/import/restore durations.
- Reconciliation runtime and impact on online traffic.

### Practical Rules

1. Benchmark with representative datasets, not empty databases.
2. Ramp concurrency gradually while watching source latency.
3. Throttle migration throughput to protect production traffic.
4. Separate CPU-heavy transforms from database I/O where possible.
5. Avoid one giant transaction covering the entire dataset unless engine mechanics fit.
6. Implement pause/resume and backpressure controls.
7. Estimate CDC catch-up time from source change rate and target apply throughput.

If the source generates 5,000 changes/sec while the target applies only 3,000 changes/sec, lag will keep growing even after bulk copy completes. Raise apply throughput, throttle source churn where possible, or pick a quieter cutover window.

## 16. Security and Governance During Migration

Data in transit during migration must obey the exact same classification and policies as live production data:

- Use a dedicated migration identity scoped strictly to reading source and writing target.
- Transfer over encrypted channels; encrypt staging files and delete temporary files per policy.
- Never log rows containing PII, payment credentials, or secrets in error logs.
- Use synthetic or masked data for testing per policy.
- Keep source and target within approved regions/networks; control cross-region transfers.
- Manage job credentials via secret managers and rotate them post-migration.
- Audit who starts jobs, changes mappings, reads data, reruns batches, and approves cutover.
- Protect manifests and checksums from tampering so verification evidence remains trustworthy.

If using external vendors or managed migration services, verify data-processing boundaries, operator access, staging-copy retention, and intermediate cleanup procedures.

## 17. Observability, Manifests, and Acceptance Evidence

Every migration should produce a manifest summarizing scope, checkpoints, verification results, and approvals.

### 17.1. Metrics

| Metric | Meaning | Alert Condition |
|---|---|---|
| Rows read / written | Copy progress | Written count falls behind expectations |
| Batches verified / failed | Verified completion progress | Failed batches or prolonged pending batches |
| CDC lag | Gap between source and target | Lag climbs steadily or exceeds cutover threshold |
| Apply errors | Unapplied target writes | Schema, constraint, or permission errors |
| Mismatch count | Reconciliation discrepancies | Mismatches on critical fields/invariants |
| Throughput | Copy/apply rate | Failing to keep up with change rate |
| Source latency | Production impact | Exceeds SLO |
| Restore/rollback duration | Recoverability | Exceeds RTO |
| Quarantine count | Records rejected by transforms | Unusual spikes or unowned backlog |

### 17.2. Manifest Example

~~~yaml
migration:
  id: booking-db-2026-11
  source: booking-primary
  target: booking-managed
  snapshot_ref: snapshot-2026-11-18T03-00Z
  cdc_watermark: source-log-position-0042
  datasets:
    - name: reservations
      source_count: 1250000
      target_count: 1250000
      missing_keys: 0
      extra_keys: 0
      value_mismatches: 0
      invariant_failures: 0
      status: VERIFIED
  cutover_approved: false
~~~

This manifest is illustrative, not a vendor-specific schema. Real manifests should include checksum references, execution timestamps, transform versions, CDC lag, exception lists, verifier identities, and sign-offs.

### 17.3. Acceptance Criteria

- Every dataset in scope has an explicit status.
- Missing/extra keys equal 0, or every exception is classified and approved.
- Critical aggregates and business invariants match.
- Referential integrity is validated.
- CDC lag is 0 or within approved threshold at the final watermark.
- Zero unmanaged writers remain on the source.
- Applications, batch jobs, reports, and integrations point to the target properly.
- Backups, restores, monitoring, alerts, and runbooks are ready.
- Business and technical owners sign off on cutover.

## 18. Case Study: Moving a Booking Database to a Managed Cloud Database

**Context:** An accommodation platform runs a relational database on VMs with `customers`, `properties`, `reservations`, `payments`, and `reservation_events` tables. APIs require under 10 minutes of downtime. Writes arrive continuously, especially during peak hours. The target managed database runs a newer engine version requiring data-type and collation adjustments.

### 18.1. Scope and Risks

| Dataset | Risks | Primary Verification |
|---|---|---|
| `customers` | Unicode, email normalization, PII | Counts, keys, canonical string comparisons, access policies |
| `properties` | References, locations, statuses | Orphan checks, enum mappings, per-tenant aggregates |
| `reservations` | Concurrent updates and booking overlaps | Counts/statuses, business keys, inventory invariants |
| `payments` | Decimal precision and auditability | Sums by currency/status, provider references, duplicates |
| `reservation_events` | High volume and ordering | Time ranges, event IDs, partitions, ordering/sequences |

### 18.2. Plan

1. Inventory all writers/readers, stored procedures, reports, and integrations.
2. Benchmark target; verify data types, collations, indexes, constraints, and connection limits.
3. Take a consistent snapshot and run baseline export/import by key range.
4. Run versioned transforms; quarantine invalid records with reasons and owners.
5. Enable CDC from the matching watermark; monitor lag and apply errors.
6. Reconcile counts, payment totals by currency, reservation states, key-level diffs, and orphans.
7. Run shadow reads for read-only queries, comparing outputs without altering user responses.
8. Rehearse cutover and rollback in staging with representative data and load.
9. In the cutover window, fence all source writers, wait for CDC catch-up, run final checks, and switch endpoints.
10. Run smoke tests: search properties, create a test reservation, verify payment status via sandbox, and read history.
11. Monitor SLOs, locks, connections, query plans, replication, and mismatches during stabilization.

### 18.3. Decisions When Mismatches Occur

- Missing counts in a key range: halt cutover, isolate the batch/checkpoint, replay, and re-reconcile.
- Payment total discrepancy: break down by currency, status, rounding, and duplicate provider references rather than summing blindly.
- Orphan properties: verify ID mappings or whether historical tombstones are valid; never fabricate fake parent rows.
- High CDC lag: keep source authoritative, tune apply throughput, and wait for catch-up within the approved window.
- Source fenced but final validation fails: do not open target traffic; reopen source per runbook if the target accepted zero writes.
- Target accepted new writes and a severe bug surfaces: halt writers and evaluate roll-forward or reverse migration; never point endpoints back while discarding new writes.

### 18.4. Completion Criteria

Cut over production serving to the target only after critical datasets reconcile, business invariants hold, application smoke tests pass, all old writers are fenced, backups/restores are verified, and owners sign off. Decommission the old source only after the approved rollback/retention window closes.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Comparing only total row counts | One missing row and one extra row still balance out | Compare keys, aggregates, and invariants |
| Copying a live source without a watermark | Snapshot and deltas have gaps or overlaps | Coordinate snapshots with CDC checkpoints |
| Treating matching file checksums as valid DB data | Imports, schemas, or constraints can still be broken | Verify post-import via DB checks and business queries |
| Running one-shot jobs without checkpoints | Hard to resume, slow, prone to duplicates | Idempotent batches, checkpoints, and manifests |
| Disabling constraints and forgetting to re-validate | Target accumulates orphans or duplicates | Re-enable and validate before cutover |
| Cutting over while CDC still has lag | Tail updates lost | Fence writers and verify final watermark |
| Forgetting batch jobs or integrations as writers | Source and target diverge post-cutover | Full writer inventory and system-wide write fence |
| Letting both databases take writes post-cutover | Conflicts and ambiguous source of truth | Single write authority or designed conflict resolution |
| Rolling back simply by flipping connection strings | Loses new writes committed on the target | Reverse CDC/replay or roll forward |
| Running unversioned transforms | Impossible to reproduce or explain data changes | Version mappings/code and log in manifest |
| Skipping failing rows to keep migration moving | Silent data loss | Quarantine with metrics, owners, and acceptance rules |
| Using unprotected production data in test runs | PII/secret leaks | Masking, synthetic data, and strict access controls |

## 20. Migration Review Checklist

### Discovery and Design

- [ ] Inventory covers datasets, schemas, volumes, change rates, owners, and dependencies.
- [ ] All readers/writers, jobs, reports, integrations, and admin paths are identified.
- [ ] Access patterns, downtime tolerance, RPO/RTO, and data classifications are documented.
- [ ] Schema/type/collation/timezone/precision mappings are reviewed.
- [ ] Choice of offline/online/CDC/batch is justified against requirements.
- [ ] Snapshot/watermark and checkpoint semantics are explicit.

### Execution and Reconciliation

- [ ] Jobs enforce batch boundaries, checkpoints, retries, and idempotency.
- [ ] Transform code/versions are tracked and quarantining is implemented.
- [ ] Counts, aggregates, keys, fields, relationships, and business invariants are verified.
- [ ] Checksums use canonicalization and their limits are understood.
- [ ] CDC ordering, deletes, duplicates, schema evolution, and lag are managed.
- [ ] Constraints, indexes, sequences, and permissions are verified on target.

### Cutover and Recovery

- [ ] Write fence covers every legacy writer.
- [ ] Final sync and reconciliation run against a deterministic watermark.
- [ ] Cutover checklist, owners, and approvals are complete.
- [ ] Rollback/roll-forward decision tree exists and has been rehearsed.
- [ ] Handling of post-cutover target writes is explicitly planned.
- [ ] Backup/restore and RPO/RTO have been tested.

### Security and Operations

- [ ] Migration identity enforces least privilege, TLS, and encryption.
- [ ] Staging files/logs/manifests never leak secrets or PII.
- [ ] Dashboards cover throughput, lag, mismatches, quarantine, source impact, and cost.
- [ ] Runbooks exist for failed batches, CDC lag, mismatches, and cutover incidents.
- [ ] Business and technical owners sign off on acceptance.

## 21. Practical Exercise

**Context:** A booking platform is migrating its database from self-managed infrastructure to a managed database. The database holds 40 million reservation events, booking writes arrive continuously, the target uses a different collation, and maximum allowed downtime is 5 minutes. A financial report reads from the source; a worker updates payment status from webhooks.

Build a plan covering:

1. Reader/writer/dependency inventory and who holds approval authority for the migration.
2. Baseline snapshot, batch key, and CDC watermark selection.
3. Mappings for collation, timestamps, decimals, enums, and keys.
4. Checkpointing, retries, and quarantining invalid records.
5. Reconciliation suite covering per-partition counts, payment totals by currency/status, key diffs, orphans, and booking invariants.
6. Transitioning the financial report and webhook worker so zero writers hit the source after cutover.
7. Write fencing and final sync keeping downtime below the 5-minute threshold.
8. Decision tree for pre-cutover mismatches, post-target-write bugs, and rollbacks.
9. Dashboards, alerts, and evidence manifest.
10. Acceptance criteria for business owner sign-off.

**Self-check hints:** Never treat near-zero CDC lag as sufficient if payment totals or reservation invariants still diverge. Do not forget the webhook worker is a writer. Never open the target to live writes before knowing how you would handle returning to the source. Every step needs an explicit source of truth, checkpoint, and proof.

## 22. Key Takeaways

A successful migration is more than copying enough bytes or matching row counts. It must transfer data, relationships, business semantics, and change ownership accurately—backed by reconciliation proof and a tested recovery path.

A sound plan starts with inventory and invariants, picks the right snapshot/bulk/CDC strategy, uses checkpointed and safely retryable batches, reconciles across counts, aggregates, keys, fields, references, and domain rules, and executes cutover with a write fence and rollback plan. Post-cutover, continue reconciling and monitoring lag and errors, decommissioning the old source only after data, applications, and operations are formally accepted.
