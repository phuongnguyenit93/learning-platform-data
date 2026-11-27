# Data Synchronization, Reconciliation, and Switching Write Ownership

Migrating an application to serverless often entails changing how data is stored and processed. A legacy system may write to a monolith database, while new Java functions running on serverless platforms need to read from and write to a new database or datastore. During the transition period, both environments must coexist: the legacy app keeps serving users, new functions roll out incrementally, and data continues changing every second.

The hardest challenge is not just copying the initial data. The system must catch up with every change that occurs during copying, handle duplicate or out-of-order messages, prove that target data matches source data, and then transfer write ownership without creating two sources of truth. Simply swapping a connection string to a new database risks losing recent updates, causing duplicate writes, or rolling back to the legacy system after new data has already been written to the target.

This lesson focuses on the **baseline snapshot → change data capture (CDC) → reconciliation → cutover** workflow for serverless applications. You will learn how to maintain checkpoints, apply changes idempotently, reconcile at a consistent point in data, manage write ownership, switch the write source incrementally, and build a rollback plan grounded in actual data state.

## Learning Objectives

After this lesson, you will be able to:

- Plan a data migration while the monolith and serverless systems operate side by side.
- Distinguish baseline snapshots, CDC, replication, and application-level dual writes.
- Choose a CDC start position that leaves no gap between the snapshot and the change stream.
- Design consumers that apply change events with checkpoints, ordering, and idempotency.
- Handle inserts, updates, deletes, schema changes, and late-arriving data.
- Reconcile row counts, per-partition checksums, and business invariants.
- Transfer write ownership using write fences and a verifiable cutover boundary.
- Build a rollback strategy when the target has already accepted new writes.
- Control sync load, database connections, retries, and backpressure in serverless.
- Use Java to model change events, apply ledgers, and reconciliation results.

## 1. The Data Migration Challenge While Serving Live Traffic

Suppose an e-commerce application currently runs as a monolith. Orders, customers, and inventory live in the legacy database. The engineering team wants to gradually move order creation APIs and event processing to Java functions. The new database could be a managed relational database, document store, or datastore selected for serverless workloads.

During migration, three streams operate concurrently:

1. **The legacy application** continues accepting requests and writing to the current source.
2. **Data synchronization** copies the baseline and forwards ongoing changes from source to target.
3. **The new application** is deployed, tested, and gradually receives traffic; initially it typically performs shadow reads or trial reads from the target.

~~~mermaid
flowchart LR
    U["Users / upstream systems"] --> OLD["Legacy application"]
    OLD --> SRC[("Source database")]
    SRC --> SNAP["Consistent snapshot"]
    SRC --> CDC["CDC change stream"]
    SNAP --> LOAD["Baseline loader"]
    LOAD --> DST[("Target database")]
    CDC --> APPLY["Idempotent CDC applier"]
    APPLY --> DST
    DST --> NEW["Serverless Java functions"]
    NEW --> U
~~~

The goal of migration is not merely "copy all tables." You must preserve these properties:

- Zero missed changes committed at the source.
- No single change applied multiple times causing repeated side effects.
- Preserved ordering for changes affecting the same entity where required.
- Target data accurately reflects source state at a well-defined point.
- Only one system is authorized to accept business writes at a time, unless a controlled multi-writer protocol is explicitly designed.
- Ability to pause, resume, reconcile, and recover migration progress.

### Concepts to Distinguish

| Concept | Meaning |
|---|---|
| Baseline snapshot | A consistent copy of data at a point in time or transaction snapshot |
| CDC | Stream of insert/update/delete changes after a specific log position |
| Checkpoint/watermark | Position successfully read or applied in the change stream |
| Reconciliation | Comparing data and business invariants between source and target |
| Write ownership | Which system is currently authorized to accept business writes |
| Cutover | Shifting traffic and write authority to the target at a verified boundary |
| Rollback | Restoring operations to the prior system without losing or diverging data |

## 2. Choosing a Synchronization Strategy

There are multiple ways to move data from source to target. Choose a strategy based on allowable downtime, data volume, CDC capabilities, consistency requirements, and reversibility.

| Strategy | How It Works | Best Suited For | Risks / Considerations |
|---|---|---|---|
| Offline migration | Stop writes, export/import, verify, then open the new system | Small datasets or when downtime is acceptable | Downtime depends on copy and verification time |
| Snapshot + CDC | Copy baseline, then continuously apply ongoing changes | Systems requiring low downtime | Must manage log positions, ordering, and lag |
| Application dual-write | Application writes to both source and target | Controlled transition stages | Two writes are not atomic; easy to drift |
| Outbox + replication consumer | Write business state and outbox in one transaction; worker updates target | When the source app can be modified | Requires schema/event contracts and replay |
| Database change log/CDC | Read source transaction logs and apply at target | Minimizing changes to legacy code | Requires managing schemas, log retention, and read privileges |

### Why a Standalone Snapshot Is Usually Not Enough

If you copy the `orders` table at 10:00 while writes continue until 10:30, the snapshot lacks orders created after 10:00. If you only start CDC after copying finishes, changes made during the copy window may be missed.

The standard approach is to establish a CDC start position before or synchronized with the snapshot boundary, take a consistent snapshot at that boundary, and then replay every change after that boundary. Exact mechanics depend on the database and migration tool: some systems provide a consistent snapshot paired with a log position; others require starting capture first, retaining logs long enough, and using the tool-provided checkpoint.

Never pair an application timestamp with a log offset on your own and assume they represent the same point. Use the snapshot/CDC coordination mechanism supported by your database or replication tool.

### CDC Is Not a Business Event

CDC usually reflects changes at the database row/transaction level. A business event like `OrderPaid` expresses business intent. A row update from `PENDING` to `PAID` does not necessarily carry the reason, actor, policy, or business context.

Use CDC to migrate data state where appropriate. Use domain events/outbox when consumers need business semantics. Do not synthesize domain events by guessing from arbitrary row updates without explicit mapping rules.

## 3. Planning the Baseline Snapshot and CDC Boundary

The snapshot + CDC pipeline must guarantee zero gaps:

~~~mermaid
sequenceDiagram
    participant S as Source database
    participant M as Migration tool
    participant T as Target database
    M->>S: Establish consistent snapshot and log position L0
    S-->>M: Snapshot at boundary L0
    M->>T: Load baseline rows
    M->>S: Read changes after L0
    S-->>M: CDC transactions L1, L2, L3...
    M->>T: Apply changes in order
    Note over M,T: Continue until target catches up
~~~

General steps:

1. Verify the source database has logging/CDC enabled with sufficient retention.
2. Determine the snapshot mode and corresponding log position supported by the tool.
3. Start change capture according to the tool's mechanism.
4. Capture a consistent snapshot and record boundary `L0`.
5. Load the snapshot into the target in resumable batches.
6. Read CDC after `L0`, applying according to transaction/ordering semantics.
7. Save checkpoints after each batch/transaction is durably applied.
8. Monitor replication lag until near zero.
9. Reconcile at a well-defined point before cutover.

Log position names vary by database, such as LSN, SCN, binlog position, or stream sequence. Never compare offsets directly across two different database engines. A CDC checkpoint is a position in the source log; it is not a row primary key or timestamp.

### Snapshot Consistency

The snapshot must represent a consistent state of data. If you export tables at different times while transactions update multiple tables, the target could contain a newly created order without its corresponding order lines or payment records.

Use consistent snapshots, transaction isolation, or a migration tool capable of database-level snapshot coordination. For very large datasets, snapshots can be chunked/partitioned; ensure all chunks belong to the same snapshot boundary or that CDC can reconcile changes occurring during the read.

### Log Retention and Copy Speed

The source must retain transaction logs longer than the time required for snapshotting, loading, and catching up. If a CDC consumer lags so far behind that log positions are purged, you may need to re-initialize the snapshot or run a tool-supported recovery procedure.

Rough estimate:

~~~text
required source log retention
  > snapshot duration
    + target load duration
    + expected catch-up duration
    + recovery margin
~~~

This is an operational estimate. Measure actual log generation rate, copy speed, apply throughput, and database log storage capacity.

## 4. Designing Change Events and Apply Ordering

CDC records typically need enough metadata to identify the source, transaction, and row:

- Source database/table or stream.
- Row primary key.
- Operation: INSERT, UPDATE, or DELETE.
- Before/after images depending on capture configuration.
- Commit position or transaction sequence.
- Schema/table version if available.
- Transaction boundary and order within the transaction.
- Snapshot marker if the record belongs to the baseline.

An illustrative Java model:

~~~java
import java.util.Map;

public enum ChangeOperation {
    INSERT,
    UPDATE,
    DELETE
}

public record SourcePosition(
        String stream,
        String transactionId,
        String commitPosition,
        int eventSequence) {
}

public record RowChange(
        String table,
        String primaryKey,
        ChangeOperation operation,
        Map<String, Object> afterImage,
        SourcePosition position,
        int schemaVersion) {
}
~~~

This is a neutral model. Actual CDC adapters map database/tool metadata into this object. Never assume every connector provides before images, transaction IDs, or identical sequence semantics.

### Global Ordering vs. Per-Entity Ordering

Some database logs have a global transaction order; some streams partition/shard data and guarantee order only within a partition. If updates for the same order travel across different partitions, the target could apply an older version after a newer one.

Options:
- Partition by primary key/aggregate ID if supported by the connector and broker.
- Use versions/commit sequences to reject stale updates.
- Preserve transaction ordering when multiple rows must change together.
- Run a sequential applier for scopes requiring strict ordering.
- Parallelize only across independent partitions.

Strict global ordering is unnecessary if business logic does not depend on ordering across distinct entities. However, explicitly document the consistency boundary: per row, aggregate, partition, or transaction.

### Deletes Must Be Explicitly Represented

If CDC only sends post-update rows without delete tombstones, the target may retain rows deleted at the source. For delete events, you need the primary key and commit position so the target deletes the right record. If using soft deletes, decide whether `deleted_at` or an archived status is the canonical semantic.

With compacted streams or tombstone-based datastores, do not purge tombstones too early if consumers lag or replay is needed.

## 5. Applying CDC Idempotently at the Target

CDC delivery often repeats when consumers retry after errors or uncommitted checkpoints. The applier must handle redelivering the same change event without producing incorrect state.

One approach is storing an apply ledger keyed by source position/event identity:

~~~sql
CREATE TABLE migration_apply_ledger (
    source_stream       VARCHAR(200) NOT NULL,
    source_position     VARCHAR(300) NOT NULL,
    event_sequence      INTEGER NOT NULL,
    applied_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_stream, source_position, event_sequence)
);
~~~

Inside the same transaction, the applier:

1. Attempts to insert the ledger key.
2. If the key already exists, the change was already applied; skip it.
3. If the insert succeeds, apply the row change to the target.
4. Commit both the ledger and target mutation in the same transaction.

If the ledger commits before the target mutation or vice versa, a crash can leave inconsistent state: marked processed without writing the row, or row written and retried causing repeated side effects. Both changes belong in the same transaction when targeting the same database.

### Version-Guarded Upsert

A complementary pattern stores the source version/commit position on the target row and applies only newer updates:

~~~sql
INSERT INTO target_order (
    order_id, status, source_version, updated_at
)
VALUES (
    :order_id, :status, :source_version, :updated_at
)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    source_version = EXCLUDED.source_version,
    updated_at = EXCLUDED.updated_at
WHERE target_order.source_version < EXCLUDED.source_version;
~~~

This works only if `source_version` has a valid total order for that entity. String-encoded LSNs/SCNs do not necessarily sort properly lexicographically; parse them into typed representations or numeric connector sequences. If events originate from multiple sources, never compare versions independently without a shared ordering rule.

### Deletes Also Need Versions/Tombstones

If a row is deleted at version 12 and a stale update from version 11 arrives late, the target must not resurrect the deleted row. Persist tombstones or deletion markers with source versions for the required retention window:

~~~sql
CREATE TABLE target_order_tombstone (
    order_id        VARCHAR(100) PRIMARY KEY,
    source_version  BIGINT NOT NULL,
    deleted_at      TIMESTAMPTZ NOT NULL
);
~~~

On delete, record the versioned tombstone. On upsert, compare versions against the tombstone; recreate the row only if the change is genuinely newer and the contract permits it. Tombstone retention must cover replay windows and late events.

## 6. Checkpoints: Advance Only After Data Is Durable

Checkpoints track where the CDC consumer has safely applied changes. A core rule:

**Never advance the checkpoint before the target mutation commits.**

If the checkpoint advances first, a crash can skip changes not yet written to the target. If the target commits first and the checkpoint lags behind, the consumer may replay changes; therefore, applying must be idempotent.

When processing batches:
- Identify the batch/transaction boundary.
- Apply all necessary changes.
- Commit target mutations and ledger entries.
- Then commit the corresponding checkpoint per connector semantics.
- If a crash occurs before checkpointing, replaying the batch is safe.
- Once the checkpoint commits, every change prior to that position must be durable.

Some connectors manage offsets/checkpoints internally or use separate distributed offset stores. Follow the connector's protocol; never write an arbitrary offset assuming it equals a broker commit.

### Multi-Row Transactions

If a source transaction updates `order`, `order_lines`, and `inventory`, applying them row by row can expose temporary inconsistency at the target. If consumers require atomic transaction visibility, preserve the transaction boundary and apply rows in one target transaction, or use staging/version markers to expose the batch only upon completion.

If migration only requires per-table eventual consistency and the target is not yet open to business reads, intermediate states during loading may be acceptable. Never open the target to users while cross-table invariants are violated.

## 7. Data Transformation and Schema Mapping

Source and target can differ in data types, naming, normalization, or data models. Migrations require versioned and tested mappings.

Examples:

| Source | Target | Risk |
|---|---|---|
| Integer amount in minor units | Decimal/amountMinor | Unit mismatch or precision loss |
| Timestamp without timezone | UTC Instant | Wrong timezone interpretation |
| Padded CHAR | VARCHAR | Trailing spaces break key matching |
| Case-insensitive collation | Case-sensitive key | Previously equal keys become distinct |
| Nullable field | Required field | Legacy rows missing values |
| Numeric enum | String enum | Unmapped unknown values |
| Soft delete flag | Physical delete | Loss of audit/restore capability |

Never convert currency through floating point. Use integer minor units or decimals with explicit precision/scale. When normalizing timezones, distinguish local date-times from UTC instants; do not blindly tag legacy timestamps as UTC if the source stored ambiguous local times.

### Versioning Transformations

A transformation should specify:
- Mapping version/commit.
- Input schema version.
- Output schema version.
- Rules for nulls, defaults, and unknown values.
- Rules for rounding, timezones, collations, and enums.
- How invalid records are handled.
- Representative test fixtures and expected outputs.

If mapping rules change while CDC is running, track which records were transformed by which version. Either rebuild the target from source with the new transformation, or create a new migration version with a controlled backfill. Never silently alter mapping logic mid-load without auditing.

### Poison Rows and Quarantine

One malformed row can repeatedly crash a CDC batch. Never silently skip it, because advancing the checkpoint would leave unmigrated data behind.

Quarantine design:
- Record source key, source position, schema version, and error category.
- Protect payloads under sensitive-data policies.
- Hold the checkpoint or flag the failing partition per connector capabilities.
- Fix the mapping or source data via an audited procedure.
- Replay quarantined rows after remediation.
- Block cutover if failures affect mandatory fields or critical invariants.

If skipping certain non-essential fields is acceptable, get a decision from the business owner and document the exception.

## 8. Data Reconciliation: Proving Target Equivalence

Finishing the initial copy and reaching zero CDC lag do not prove data correctness. Mapping bugs, missed deletes, timezone errors, or out-of-order applies may still exist. **Reconciliation** compares source and target at the same logical point and verifies both raw data and business invariants.

Layers of reconciliation:

1. **Completeness:** row counts, partition counts, key coverage.
2. **Integrity:** per-partition or per-record checksums/hashes.
3. **Business invariants:** monetary totals, order counts by status, parent-child relationships.
4. **Freshness:** CDC lag and applied source position.
5. **Exception review:** quarantined rows, mapping exceptions, and duplicates.

### Why Compare at the Same Point in Time?

If the source continues receiving writes while reconciliation scans for several minutes, source and target can change mid-read. A row difference is not necessarily a migration bug; the source might have updated after the target was read.

Approaches:
- Take a source snapshot/consistent read at a boundary.
- Compare against target state applied up to that exact CDC position.
- Or pause writes briefly during final reconciliation.
- If writes cannot pause, use snapshot isolation or watermarks/vector positions to bound the comparison scope.

Never query "current" source and "current" target with two uncoordinated queries and treat differences as reliable findings.

### Row Counts per Partition

Instead of comparing only a single total row count, slice by key range, tenant, date, or hash bucket:

| Partition | Source Rows | Target Rows | Difference |
|---|---:|---:|---:|
| tenant 00–19 | 125,000 | 125,000 | 0 |
| tenant 20–39 | 118,400 | 118,399 | -1 |
| tenant 40–59 | 132,050 | 132,050 | 0 |
| tenant 60–79 | 121,900 | 121,900 | 0 |
| tenant 80–99 | 119,700 | 119,700 | 0 |

This example shows how total counts can look nearly right while one partition is missing a row. Partitioning isolates investigations and lets you rerun only the failing slice.

### Per-Partition Checksums

Compute checksums over canonicalized fields sorted by primary key. Conceptual example:

~~~text
partition_checksum =
  HASH(
    CONCAT(
      canonical(row_1),
      canonical(row_2),
      ...
      canonical(row_n)
    )
  )
~~~

Checksums are useful only when canonicalization is deterministic:
- Same row sort order.
- Same null representation.
- Same numeric precision.
- Same timezone formatting.
- Same character encoding and collation.
- Exclude volatile fields like migration timestamps unless their semantics match.

A partition checksum mismatch only indicates that data differs; it does not identify which row differs. Subdivide partitions and compare keys/fields to locate the root cause. For massive datasets, Merkle trees or hierarchical checksums narrow down differences without transferring the entire dataset.

### Reconciling Business Invariants

Row counts and checksums can miss semantic bugs when row counts match yet field mappings are wrong. Also verify:

- Order counts grouped by status.
- Amount totals grouped by currency and date.
- Order line counts per order.
- Non-negative inventory totals balanced per warehouse.
- Count of successful payments matching payment references.
- Zero orphaned foreign keys/references.
- Soft-deleted rows retained or purged per policy.
- Uniqueness of business keys.

Never sum amounts across different currencies into one combined total. Group by currency and scale; verify rounding matches contracts.

## 9. Java: Modeling Reconciliation Results

Standardize reconciliation results into objects for logging, dashboards, or migration reports:

~~~java
import java.time.Instant;

public record PartitionReconciliation(
        String partitionId,
        long sourceCount,
        long targetCount,
        String sourceChecksum,
        String targetChecksum,
        long sourcePosition,
        long targetAppliedPosition,
        Instant checkedAt) {

    public boolean countsMatch() {
        return sourceCount == targetCount;
    }

    public boolean checksumsMatch() {
        return sourceChecksum.equals(targetChecksum);
    }

    public boolean caughtUp() {
        return targetAppliedPosition >= sourcePosition;
    }

    public boolean passed() {
        return countsMatch() && checksumsMatch() && caughtUp();
    }
}
~~~

This is an illustrative model. `sourcePosition` and `targetAppliedPosition` must share a comparable ordering system; if the target tracks only internal checkpoints, map back to the applied source log position. Never compare raw offsets from two independent streams as though they share an ordering.

Report builder example:

~~~java
import java.util.List;

public final class ReconciliationReport {
    private final List<PartitionReconciliation> partitions;

    public ReconciliationReport(List<PartitionReconciliation> partitions) {
        this.partitions = List.copyOf(partitions);
    }

    public boolean passed() {
        return !partitions.isEmpty()
                && partitions.stream().allMatch(
                        PartitionReconciliation::passed);
    }

    public List<PartitionReconciliation> failedPartitions() {
        return partitions.stream()
                .filter(result -> !result.passed())
                .toList();
    }
}
~~~

In production, reports should include mapping version, snapshot boundary, CDC stream identity, schema version, quarantined row count, and operator/run ID. Report PASS only when every mandatory check succeeds; never average partitions or ignore failing slices.

## 10. Shadow Reads and Comparison Before Traffic Cutover

Once baseline and CDC catch up, run shadow reads: live requests still return responses from the source while a copy of the request runs against the target for comparison.

Shadow reads must:
- Produce zero side effects on the target.
- Use identical inputs and equivalent access permissions.
- Compare semantically equivalent fields.
- Normalize non-deterministic fields like timestamps, generated IDs, or unguaranteed ordering.
- Cap sampling/rates to avoid overloading the target.
- Never let target failures fail live requests served from the source.

Classify shadow mismatches into:
- Missing records in target.
- Field mapping differences.
- Stale CDC lag.
- Differences from business rules or data freshness.
- Expected differences by target design.
- Authorization/tenant filter bugs.

Do not compare responses byte-for-byte if the two systems order arrays differently or emit different metadata. Compare semantic fields per contract.

### Shadow Writes Carry Higher Risk

Never send a live business write request to both systems hoping both writes succeed together. If the source commits and the target fails, or vice versa, the systems diverge. If shadow writes are used, design them as a migration protocol: idempotency keys, outbox/CDC, error ledgers, replay, and reconciliation. Do not implement it as two consecutive repository calls.

## 11. Dual-Write and Write Ownership

During migration, a pivotal decision is which system owns canonical writes.

### Why Naive Application Dual-Write Is Unsafe

Example code:

~~~java
sourceRepository.save(order);
targetRepository.save(order);
~~~

If the first call succeeds and the second fails, source and target diverge. Reversing the order merely reverses the failure mode. Without an explicit distributed transaction protocol, two databases do not commit atomically.

Safer alternatives:
- Source as single writer; CDC/outbox replicates changes to target.
- Target as single writer; reverse replication syncs changes back to source during supported rollback windows.
- A single write service coordinating via transactional outbox.
- Accepted dual-write with explicit reconciliation/compensation when a single writer is impossible.

### Write Ownership

A control service or control plane should record the active write authority:

~~~text
write_owner = LEGACY
migration_phase = CDC_CATCH_UP
migration_epoch = 12
~~~

After cutover:

~~~text
write_owner = SERVERLESS
migration_phase = TARGET_ACTIVE
migration_epoch = 13
~~~

This is control metadata, not a local variable inside individual functions. Every writer must check ownership or receive versioned/fenced configuration. Updating an environment variable on only some instances lets old instances keep writing to the source after traffic shifts.

### Fencing Old Writers

To prevent legacy writers from continuing to write:
- Pause or disable legacy routes/consumers.
- Revoke write privileges from legacy identities after draining.
- Use database roles/permissions or a centrally checked write gate.
- Use migration epochs/fencing tokens if supported by the architecture.
- Verify no old connections or jobs write past the cutover boundary.

Changing DNS or load balancers alone does not stop legacy cron jobs, queue consumers, or batch processes from writing. Inventory every writer: APIs, workers, schedulers, admin tools, ETLs, triggers, and external integrations.

## 12. Phased Cutover Process

A low-downtime cutover should progress through explicit gates.

~~~mermaid
flowchart TD
    A["1. Inventory writers and readers"] --> B["2. Baseline snapshot + CDC"]
    B --> C["3. Load and catch up"]
    C --> D["4. Reconcile and shadow read"]
    D --> E["5. Freeze / fence source writes"]
    E --> F["6. Drain in-flight work and final CDC"]
    F --> G["7. Final reconciliation at watermark"]
    G --> H{"All gates pass?"}
    H -->|No| I["Abort cutover; keep legacy owner"]
    H -->|Yes| J["8. Switch write owner to target"]
    J --> K["9. Route traffic and monitor"]
    K --> L["10. Retire old writer after rollback window"]
~~~

### Phase 1: Inventory

Catalog:
- All services/functions capable of writing to the source.
- Readers depending on the source.
- Queues, scheduled jobs, batches, and external integrations.
- Tables, sequences, triggers, stored procedures, and constraints.
- Data owners, retention, and compliance rules.
- Downtime SLOs, RTO, RPO, and rollback requirements.

### Phase 2: Baseline + CDC

Take a consistent snapshot, load the target, and start applying CDC from the boundary. Monitor:
- Snapshot progress.
- Source log retention.
- CDC lag / oldest unapplied position.
- Apply throughput and error rates.
- Quarantine count.
- Target database load.

### Phase 3: Catch-Up and Reconciliation

Let CDC catch up to near-zero lag. Run counts/checksums/business invariants against a comparable snapshot or watermark. Resolve all required mismatches. Run shadow reads to validate query semantics and authorization.

### Phase 4: Cutover Preparation

- Deploy serverless functions and configure runtime identities.
- Verify connection pools/max instances will not overload the target.
- Prepare write gates/fencing.
- Freeze unrelated deployments and schema changes during the cutover window.
- Assign operators, dashboards, rollback decision owners, and communication channels.
- Rehearse in staging with representative datasets and traffic.

### Phase 5: Freeze and Drain

- Block new writes on the source in a verifiable way.
- Allow in-flight requests to finish or terminate cleanly.
- Stop/disable legacy consumers, scheduled jobs, and batch writers.
- Record the final source high-water mark.
- Wait for CDC to apply up to that exact mark.
- Run final reconciliation at the frozen data boundary.

If all writers cannot be frozen, you must have an ownership/epoch protocol guaranteeing no two writers operate concurrently. Never cut over traffic just because queue lag looks "near zero"; know the exact final watermark.

### Phase 6: Switch

- Atomically update write ownership/epoch.
- Enable the target writer and verify write access.
- Route requests/triggers to serverless functions.
- Verify a canary transaction traces end-to-end from request to database/events.
- Confirm legacy writers are fenced with zero new source writes.
- Monitor error rates, latency, queue age, and business metrics.

### Phase 7: Maintain the Rollback Window

Do not delete the source immediately after the target starts serving traffic. Keep the source read-only or on standby for an agreed window, preserve schemas/backups, and continue checking for drift. Retire the source only after the rollback window closes and owners approve.

## 13. Rollback After Target Accepts Writes

Data rollback is harder than code rollback. Before cutover, the source holds canonical state. Once the target accepts new writes, the source does not automatically receive those updates.

Three primary strategies:

| Strategy | How Rollback Works | Preconditions |
|---|---|---|
| Reversible replication | CDC/reverse sync from target back to source | Reverse mappings exist and target changes fit source schema |
| Freeze and reconcile | Halt target writes, copy necessary changes back to source, reconcile, then switch | Downtime/maintenance window available |
| Forward recovery | Keep target as source of truth, roll back code while still writing to target | Old code or adapter can talk to target |

Never simply point the connection string back to the source if the target has accepted writes not replicated backward. Doing so drops new orders/payments or splits data history.

### Rollback Gate

Before cutover, answer:
- Has the target received business writes yet?
- Is reverse CDC/replication tested and ready?
- Does the target schema contain fields the source cannot represent?
- Have external side effects like payments/emails occurred?
- Can events be replayed from an outbox to recover?
- What is the rollback RPO?
- Who holds rollback authority and what is the maximum decision window?

Without reverse replication, prefer **forward recovery**: keep the target as the write source and redeploy a stable application version compatible with the target. That is usually safer than reverting to a stale source.

## 14. Serverless-Specific Concerns in Data Migration

Serverless scales workers rapidly, yet migrations require controlled throughput. If CDC backlog spikes, autoscalers can spin up many function instances at once and overwhelm the target database.

### Backpressure and Concurrency

Configure limits:
- Max concurrency/instances or max function concurrency.
- CDC consumer batch size and parallelism.
- Connection pool size per instance.
- Total target connection budget.
- Rate limits for write amplification/index maintenance.
- Retries/backoff with jitter.

An estimate to check:

~~~text
maximum database connections
  ≈ max active instances × pool size per instance
     + other application/admin connections
~~~

This is an approximate upper bound. Pools may open connections lazily; some drivers/proxies multiplex connections. Always load-test to verify real limits.

### Serverless Workers Should Be Stateless

Every invocation must be able to resume from a durable checkpoint. Never hold the sole CDC offset in a static field or container-local file. When an instance is recycled, another worker must read the checkpoint and continue safely.

### Batching and Retries

- Smaller batches shrink transaction duration and retry scope.
- Larger batches raise throughput at the cost of longer locks, more memory, and wider blast radius.
- If one poison row rolls back an entire batch, isolate the failing row and quarantine it.
- Never advance checkpoints past unapplied rows.
- Retry transient errors with backoff; permanent/schema errors must halt or quarantine cleanly.

### Database Connections

Function scale-out can cause connection storms. Use bounded connection pools, database proxies/pooling services where appropriate, and cap max instances. Never open a new connection per row in a batch. Reuse clients/connections within the execution environment according to driver thread-safety and lifecycle guidelines.

## 15. Java: Applier with Ledger and Transaction

An abstraction separates CDC adapters from apply logic:

~~~java
public interface ChangeApplier {
    ApplyResult apply(RowChange change);
}

public enum ApplyResult {
    APPLIED,
    ALREADY_APPLIED,
    QUARANTINED
}
~~~

A service processing change events wraps the ledger and target mutation in a transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalChangeApplier implements ChangeApplier {
    private final ApplyLedgerRepository ledger;
    private final TargetRowRepository target;
    private final ChangeMapper mapper;

    public TransactionalChangeApplier(
            ApplyLedgerRepository ledger,
            TargetRowRepository target,
            ChangeMapper mapper) {
        this.ledger = ledger;
        this.target = target;
        this.mapper = mapper;
    }

    @Override
    @Transactional
    public ApplyResult apply(RowChange change) {
        boolean claimed = ledger.tryInsert(
                change.position().stream(),
                change.position().commitPosition(),
                change.position().eventSequence());

        if (!claimed) {
            return ApplyResult.ALREADY_APPLIED;
        }

        switch (change.operation()) {
            case INSERT, UPDATE -> target.upsert(mapper.toTarget(change));
            case DELETE -> target.delete(
                    change.table(), change.primaryKey(),
                    change.position());
        }

        return ApplyResult.APPLIED;
    }
}
~~~

This is a structural example. `tryInsert` must use a unique constraint/atomic insert; `upsert` and the ledger must share the same database transaction. If the mapper throws a data error, the transaction rolls back; quarantine records should be written in an intentional transaction/flow so changes are never marked applied when the target mutation failed.

If the target is a different datastore from the ledger, standard Spring transactions cannot span both. In that case, use conditional writes, an outbox, an apply state machine, or target-store idempotency mechanisms.

### Do Not Assume Checkpoints Commit Inside the Same Database Transaction

CDC connectors may store offsets in a broker or external offset store. A shared transaction between the target DB and offset store may not exist. The common pattern commits target + ledger first, then commits the offset; if a crash happens in between, replay is absorbed by the ledger. Never commit offsets before target mutations.

## 16. Migration Ledger and Operational State

Beyond the row-level apply ledger, track migration progress at the job/run level:

~~~sql
CREATE TABLE migration_run (
    migration_id       VARCHAR(100) PRIMARY KEY,
    source_name        VARCHAR(200) NOT NULL,
    target_name        VARCHAR(200) NOT NULL,
    snapshot_id        VARCHAR(300),
    start_position     VARCHAR(300),
    applied_position   VARCHAR(300),
    mapping_version   VARCHAR(100) NOT NULL,
    schema_version    VARCHAR(100) NOT NULL,
    status             VARCHAR(30) NOT NULL,
    started_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL,
    completed_at       TIMESTAMPTZ
);
~~~

Possible states include:
- PLANNED
- SNAPSHOT_RUNNING
- SNAPSHOT_COMPLETE
- CDC_CATCH_UP
- RECONCILING
- READY_FOR_CUTOVER
- CUTOVER_IN_PROGRESS
- TARGET_ACTIVE
- ROLLBACK_IN_PROGRESS
- COMPLETED
- BLOCKED

A state machine tells operators where migration stands and what preconditions gate each transition. Every transition should record actor, timestamp, migration epoch, and supporting evidence/reports—not just an environment variable or a log line.

## 17. Security and Data Governance During Migration

Migration workers typically read most of the source and write to the target. Because of the wide blast radius, give them dedicated identities.

- Use separate service accounts/roles for snapshot loaders, CDC appliers, and reconciliation workers when privileges differ.
- Grant the source identity read-only access strictly to required snapshots/logs.
- Grant the target identity write access strictly to target schemas/tables.
- Never grant database admin privileges if only INSERT/UPDATE/DELETE are needed.
- Enforce TLS and encryption at rest per policy.
- Never log full row images containing PII or secrets.
- Secure snapshot files, staging buckets, and quarantine stores.
- Audit access and purge temporary migration data according to retention rules.
- Maintain audit trails for mapping/transform versions and operator actions.

Do not copy secrets or tokens inside row images to the target as ordinary data. If the source stores hashed credentials, do not change hashing algorithms or salts during migration without a dedicated plan.

## 18. Tracking Migration Progress and Quality

A migration dashboard should include:

| Metric | Question Answered |
|---|---|
| Snapshot rows/bytes copied | How much baseline remains? |
| Snapshot throughput | Does copy speed meet the window? |
| CDC source position | How far has the source progressed? |
| CDC applied position | How far has the target applied? |
| Replication lag / oldest event age | How far behind is the target? |
| Apply rate / error rate | Is the consumer processing steadily? |
| Duplicate apply count | How much replay/idempotency is occurring? |
| Quarantine count | Are any rows unmigrated? |
| Reconciliation mismatch count | Which partitions/invariants are failing? |
| Target DB CPU/connections/IO | Is there overload risk? |
| Cutover write errors | Are target writers failing after the switch? |

Checkpoint positions do not map linearly to wall-clock time when log rates fluctuate. Track lag by both time and log position. Do not look only at "CDC running" or green job status.

### Essential Alerts

- CDC lag exceeds cutover threshold.
- Source log retention nearing exhaustion.
- Apply errors or quarantine counts rising.
- Target connection pool/database approaching limits.
- Reconciliation mismatches persist.
- Snapshot progress stalls.
- Legacy writers still writing after fencing.
- Target receiving writes during a migration phase that disallows them.

Every alert needs an owner, runbook, and migration halt condition. If mandatory data mismatches, never force cutover just to hit a release date.

## 19. Example Cutover Plan for an Orders Service

Suppose the system holds 20 million orders and the legacy application still serves live traffic.

| Phase | Write Source | Activities | Gate to Advance |
|---|---|---|---|
| Prepare | Legacy | Create target schema, permissions, and CDC | Snapshot/CDC tests pass |
| Baseline | Legacy | Copy 20M orders via consistent snapshot | Row counts/chunk loads complete |
| Catch-up | Legacy | Continuously apply CDC | Lag within threshold |
| Shadow | Legacy | Compare target reads against source | Mismatches classified and resolved |
| Freeze | No new source writes | Drain requests/consumers, capture final watermark | Zero remaining legacy writers |
| Final sync | Source fenced | Apply to final watermark and reconcile | Counts/checksums/invariants PASS |
| Cutover | Serverless target | Switch write owner and route traffic | Canary writes/reads PASS |
| Observe | Serverless target | Monitor errors, lag, business metrics | Rollback window expires |
| Retire | Serverless target | Set source read-only/archive, then retire per policy | Owner approval |

Numbers and gates in this table are examples. CDC lag thresholds, freeze durations, sample rates, and rollback windows must match your system's real SLAs, RTO, RPO, and capacity.

## 20. Common Migration Pitfalls

| Pitfall | Consequence | Prevention |
|---|---|---|
| Copying only a snapshot without capturing changes during the copy | Writes occurring mid-migration are lost | Coordinated snapshot + CDC boundary |
| Starting CDC after snapshot finishes without a matching log position | Data gap | Capture/coordinate from a supported boundary |
| Advancing checkpoints before target commit | Missed changes after a crash | Commit target + ledger before offset |
| Non-idempotent duplicate applies | Repeated side effects or row mutations | Unique ledger and conditional/upsert writes |
| Ignoring deletes/tombstones | Target retains deleted records | Capture deletes and retain tombstones long enough |
| Comparing source and target at different points in time | False mismatches or missed bugs | Consistent snapshots/watermarks |
| Comparing only total row counts | Misses missing partitions or corrupted fields | Counts + checksums + business invariants |
| Direct dual writes to two databases | Split state when one write fails | Single writer + CDC/outbox or explicit protocol |
| Switching traffic while forgetting legacy crons/consumers | Legacy continues writing post-cutover | Inventory and fence all writers |
| Rolling back code by pointing back to a stale source | New target writes are lost | Reverse sync or forward recovery |
| Unbounded CDC consumer scaling | Connection storms, target overload | Backpressure, concurrency, and pool budgets |
| Deleting source immediately after cutover | No rollback or audit path | Keep read-only standby and rollback window |

## 21. Pre-Cutover Checklist

- [ ] Complete inventory of all readers, writers, jobs, triggers, and integrations.
- [ ] Source/target schemas and transformations are versioned.
- [ ] Baseline snapshot has an explicit consistency boundary.
- [ ] CDC start position is coordinated with the snapshot with zero gaps.
- [ ] Source log retention covers loading, catch-up, and recovery.
- [ ] CDC applies use an idempotency ledger/conditional writes.
- [ ] Ordering and transaction boundaries are preserved as required.
- [ ] Deletes/tombstones and late events are handled.
- [ ] Checkpoints advance only after durable target mutations.
- [ ] Quarantine has an owner, replay workflow, and audit trail.
- [ ] Reconciliation runs at a single snapshot/watermark.
- [ ] Row counts, checksums, and business invariants pass.
- [ ] Shadow reads cause zero side effects and mismatches are resolved.
- [ ] Only one write owner is active at any time.
- [ ] Legacy writers, schedulers, queue consumers, and admin paths are fenced.
- [ ] Target capacity, concurrency, connection pools, and backpressure are load-tested.
- [ ] Final watermark and cutover gates are documented.
- [ ] Rollback accounts for writes already accepted at target, not just code rollback.
- [ ] Reverse replication or forward recovery has been rehearsed.
- [ ] Source is retained per rollback/retention policies before retirement.

## Self-Check

1. Why is a standalone baseline snapshot insufficient while the source still accepts writes?
2. How must the CDC start position relate to the snapshot boundary?
3. Why is a database CDC record different from a domain event?
4. Should checkpoints commit before or after target mutations, and why?
5. How do you prevent late-arriving stale updates from overwriting newer state?
6. How long should deletes/tombstones be retained when replay is possible?
7. Why must reconciliation compare source and target at the same logical point?
8. What kinds of business errors can row counts and checksums miss?
9. Why can direct application dual writes to two databases create split state?
10. How do write ownership and fencing protect cutover?
11. If the target has already accepted new writes, what is required before rolling back to the source?
12. Why do serverless CDC consumers need concurrency and connection pool caps?

Safe data migration relies on a chain of evidence: a consistent snapshot, gap-free CDC, idempotent application, durable checkpoints, reconciliation at a shared watermark, and controlled transfer of write ownership. Once the target becomes the write source, rollback must account for all new writes and side effects that have occurred. For serverless Java functions, stateless workers, backpressure, dedicated identities, and a migration state machine allow synchronization to resume, be audited, and recover without relying on in-instance state.
