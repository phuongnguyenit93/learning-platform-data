# Separating Schema Changes from Long-Running Data Migrations

## 1. Why separate schema migrations from data migrations?

An application change may require modifying both database structure and stored data. For example, a system might need to change an order status column from free-form strings to standardized status codes, move data from an old column to a new structure, or split a large table into specialized tables.

These two tasks have different operational characteristics:

- **Schema migration** changes database structure: adding columns, tables, indexes, constraints, or changing data types.
- **Data migration** transforms existing records into a new representation, often requiring reading and writing large volumes of data.

Combining both into a single deployment transaction can prolong release duration, lock tables, spike database load, and make application rollback difficult. A long-running migration can also stall the pipeline for hours while old and new applications need to operate together during transition.

The solution is separating structural expansion, data transformation, and legacy removal into independent phases. The application must remain schema-compatible throughout the transition. Data migrations run in batches, support pausing and resuming, and produce sufficient evidence to decide when to switch read/write flows to the new structure.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, this practice makes release pipelines traceable, controls deployment duration, verifies data, protects availability, and prepares recovery options. The goal is not just updating the database successfully, but keeping the application functioning properly throughout the change.

## 2. Distinguishing schema migration from data migration

| Aspect | Schema migration | Data migration |
|---|---|---|
| Target | Database structure | Record contents |
| Operations | CREATE, ALTER, ADD INDEX, ADD CONSTRAINT | Reading, mapping, normalizing, updating, or copying data |
| Duration | May be short, depending on engine and DDL type | Can span minutes to many hours or days |
| Impact | Locks, metadata changes, table or index rewrites | CPU, I/O, WAL/redo logs, replication lag, row locks |
| Deployment approach | Versioned migrations, lock and compatibility checks | Jobs with batching, checkpoints, retries, throttling, and validation |
| Recovery | May require a new migration to reverse structure | Usually requires forward-fix, compensating data, or backup/PITR |
| Completion criteria | New structure exists and is verified | Data is completely and accurately migrated and verified |

For example, adding the **normalized_status** column is a schema change. Populating new values for tens of millions of orders from the **legacy_status** column is a data migration. The two are related, yet should not be executed together by default.

An `ALTER TABLE` statement may be instant on one database version yet trigger locking or a table rewrite on another. Similarly, a simple `UPDATE` can generate massive WAL volume if run across an entire table. Therefore, evaluate DDL costs and data-transformation costs separately.

## 3. Compatibility principles during transition

During a release, the following may exist simultaneously:

- Old application version serving requests.
- Newly deployed application version.
- Workers executing the data migration.
- Background consumers or jobs still reading the old schema.
- Database replicas synchronizing data.

Consequently, the new schema must be designed so the old version does not break when the structure expands. Likewise, the new version must operate while part of the data has not yet been transformed.

A useful principle is **expand-contract**:

- **Expand:** extend the schema to support both old and new representations.
- **Migrate:** transform data gradually while the system keeps running.
- **Switch:** shift the application to read or write using the new structure.
- **Contract:** remove the old structure only when no component needs it anymore.

~~~mermaid
flowchart TD
    A["Old schema and old app"] --> B["EXPAND: add compatible new structure"]
    B --> C["Deploy app compatible with both schemas"]
    C --> D["BACKFILL: migrate data in batches"]
    D --> E["VALIDATE: reconcile and check invariants"]
    E --> F{"Data meets criteria?"}
    F -- "No" --> D
    F -- "Yes" --> G["SWITCH: shift reads/writes to new structure"]
    G --> H["Monitor and hold safety window"]
    H --> I["CONTRACT: drop old structure"]
    I --> J["Complete"]
~~~

Not every project requires dual-write or backfills. If a table is small and can convert in a brief transaction with controlled locking, a simple migration may suffice. Expand-contract is especially valuable when data is large, the application needs continuous uptime, or multiple versions coexist.

## 4. Application and schema compatibility matrix

Before deploying, build a matrix specifying which application versions can operate against each schema state.

Example when migrating from **legacy_status** to **normalized_status**:

| Database state | Old application | New application | Notes |
|---|---|---|---|
| Old column only | Works | Cannot deploy yet | Initial state |
| New column added, not backfilled | Works | Works if handling NULL | Expand phase |
| Both columns synced, backfill running | Works | Works | Transition phase |
| New data complete, app reads new column | Can work if old column is maintained | Works | Switch phase |
| Old column removed | Fails | Works | Only run after all old consumers stop |

This matrix determines release ordering. If the new application reads the new column before the schema has it, deployment fails. If the schema drops the old column before old instances are replaced, in-flight requests can fail.

Account for background workers, batch jobs, reports, admin tools, message consumers, and other applications sharing the database. Web services are not the only schema consumers.

## 5. Expand phase: adding new structures without breaking old ones

The expand phase creates new structures in a backward-compatible manner.

Example:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(32);
~~~

After this step, the old column still exists and the old application keeps reading and writing as before. The new column may contain NULL initially.

Common tasks in the expand phase:

- Adding nullable new columns.
- Creating new tables or mapping tables.
- Adding indexes in a manner suited to the database engine.
- Adding constraints in a non-disruptive mode if supported by the engine.
- Adding required metadata or version fields.
- Deploying structures that the old application can ignore.

Do not rush to add `NOT NULL` or drop old columns before data is migrated and all application versions are compatible. Constraints can be added after backfill and validation succeed.

### 5.1. Evaluating whether DDL acquires locks

An `ALTER TABLE` statement is not automatically instantaneous. Its impact depends on the database engine, version, change type, table size, and active transactions.

Before applying to production, review:

- What lock types the DDL acquires.
- Whether the DDL rewrites the entire table or indexes.
- Lock duration and impact on running queries.
- Whether online/concurrent operations are available.
- Whether timeouts prevent indefinite lock waits.
- Whether replicas can keep up with generated logs.

For example, PostgreSQL supports `CREATE INDEX CONCURRENTLY` to minimize write blocking in many cases, though this command has limitations and cannot run inside a normal transaction block. If it fails, the index may remain in an invalid state and must be cleaned up before retrying. Check documentation and behavior for your actual database version.

### 5.2. Creating constraints incrementally

On large tables, adding a constraint can require scanning existing data. If the database supports unvalidated constraints, the team can create the constraint first, verify data separately, and validate later.

Example in PostgreSQL:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_normalized_status_check
CHECK (
  normalized_status IS NULL
  OR normalized_status IN ('PENDING', 'PAID', 'CANCELLED')
) NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT orders_normalized_status_check;
~~~

Check exact syntax and locking severity per version. The multi-step approach decouples establishing the rule from scanning all existing rows.

## 6. Deploying a compatible application before migrating data

Once the new schema exists, deploy an application version able to work with both old and new data.

A transitional version can:

- Read the old column when the new column lacks a value.
- Write both old and new columns inside the same transaction.
- Handle NULL or unconverted values.
- Emit metrics for records still missing new data.
- Avoid requiring the new column to be `NOT NULL` yet.
- Avoid assuming all other workers or instances have upgraded.

Example transitional read logic:

~~~sql
SELECT
  CASE
    WHEN normalized_status IS NOT NULL THEN normalized_status
    ELSE map_legacy_status(legacy_status)
  END AS effective_status
FROM orders
WHERE id = :order_id;
~~~

The mapping function represents conversion rules defined by the application. Ensure the identical rule is used in both the backfill and the transitional read path, avoiding cases where two places map the same legacy value to different outcomes.

If the application writes both columns, execute within the same database transaction when both belong to the same database. If writing across two independent systems, direct dual-write risks partial failure where one side succeeds and the other fails. In such cases, consider a transactional outbox, CDC, idempotent retries, or reconciliation workflows.

## 7. Data backfill: transforming data in batches

Backfilling reads existing data and populates or converts it into the new structure. On large tables, do not run a single `UPDATE` across the whole table by default.

A batched backfill can:

1. Select a primary key range or subset of records.
2. Read source data.
3. Apply transformation rules.
4. Write target values for that subset.
5. Commit the transaction.
6. Persist a checkpoint.
7. Proceed to the next batch.

Benefits:

- Bounds lock hold durations.
- Reduces transaction size.
- Limits sudden WAL/redo log spikes.
- Allows throttling according to load.
- Simplifies retries and resuming after worker restarts.
- Enables tracking progress and estimating remaining time.

Batch sizes should not be hardcoded identically for every database. A batch of 1,000 rows may fit one system yet be too small or too large for another. Measure transaction duration, lock waits, replication lag, I/O, and request latency to tune it.

## 8. Idempotency and resumability

A data migration running for hours may stop due to deployments, connection drops, timeouts, or intentional pauses to ease load. Therefore, the job must be re-runnable without corrupting data.

**Idempotent migration** means re-running the same step over already-processed data does not produce incorrect results or unintended changes.

Example updating only rows lacking a new value:

~~~sql
UPDATE orders
SET normalized_status =
  CASE legacy_status
    WHEN 'new' THEN 'PENDING'
    WHEN 'settled' THEN 'PAID'
    WHEN 'void' THEN 'CANCELLED'
    ELSE 'UNKNOWN'
  END
WHERE id >= :start_id
  AND id < :end_id
  AND normalized_status IS NULL;
~~~

The `NULL` predicate prevents overwriting fresh values written by the application while the backfill runs. However, clarify whether `'UNKNOWN'` is acceptable or must be routed to a manual remediation queue.

A checkpoint can store:

- Migration ID and version.
- Completed key range.
- Last committed batch.
- Counts of rows read, updated, skipped, and failed.
- Start time and latest resume timestamp.
- Transformation rule version.

Update checkpoints only after the data batch commits successfully. Recording a checkpoint before committing data risks skipping an unprocessed batch. Committing data before updating the checkpoint means a batch may re-run; hence logic must still be idempotent.

### 8.1. Choosing a stable checkpoint

Use an ascending primary key, partition key, or set of IDs. Avoid large `OFFSET` pagination on continuously mutating tables because scanning becomes slow and row ordering can shift.

For new data created while backfilling, ensure coverage via:

- Dual-write from the new application.
- CDC or event streams.
- Re-scanning records updated after the start timestamp.
- A final reconciliation pass before cutover.

If you only backfill IDs present at start time, records inserted afterward may be missed if the application does not yet write the new column.

## 9. Throttling load and protecting the database

Data migrations compete for resources with live application requests. A backfill running too fast can spike latency, replication lag, lock waits, or log volume.

Control measures:

- Limit concurrent batches.
- Commit per batch rather than holding large transactions.
- Set timeouts and backoff retries.
- Adjust batch size dynamically based on actual load.
- Pause when latency, lock waits, or replication lag exceed thresholds.
- Run during off-peak hours if business constraints allow.
- Avoid unnecessary repeated full table scans.
- Monitor WAL/redo log growth and storage capacity.
- Rate-limit reads and writes.
- Choose indexes supporting the backfill filter predicates.

A migration can self-throttle. For example, if replica lag rises or request latency breaches thresholds, workers shrink batch size or pause briefly before continuing.

Do not rely on fixed sleeps as the sole throttling mechanism. Reading real telemetry and adjusting via policy is far better.

## 10. Dual-write, CDC, and transactional outbox

During transition, the system may need to keep two data representations synchronized.

### 10.1. Dual-write within the same database

If both columns live in the same database and transaction, the application can update both:

~~~sql
UPDATE orders
SET legacy_status = :legacy_value,
    normalized_status = :normalized_value
WHERE id = :order_id;
~~~

This is straightforward, yet every write path must be updated: APIs, workers, batches, admin tools, and operational scripts. If one consumer writes only the old column, the new column becomes missing or stale.

Add metrics or constraints to detect divergence between columns. Do not keep dual-write longer than needed, as it adds complexity and drift vectors.

### 10.2. CDC when syncing across systems

Change Data Capture (CDC) reads changes from database logs or equivalent mechanisms and streams them elsewhere. CDC is helpful when data must be copied or transformed into a new store without blocking live requests.

Pay attention to:

- Event ordering and replayability.
- At-least-once delivery causing duplicate events.
- Consumer idempotency.
- Event schema compatibility.
- Lag detection and dead-letter handling.
- Row count and content reconciliation after sync.

### 10.3. Transactional outbox

When an application must update a database and emit an event, writing to the database and publishing a message separately risks partial failure. A transactional outbox writes the business change and an event record in the same database transaction; a worker subsequently publishes events from the outbox.

An outbox prevents losing events between two independent writes, though consumers must still handle duplicates and retries. It does not by itself guarantee all downstream systems update instantaneously.

## 11. Validating data before switching reads

Do not switch the application to read the new structure simply because the backfill reported all batches finished. Verify the data.

Checks to run:

- Source vs. target record counts.
- Count of rows still NULL in the new column.
- Count of values outside the allowed set.
- Count of unmappable records.
- Conversion success rate.
- Sums or checksums across appropriate fields.
- Business invariants, such as monetary totals, item counts, or foreign key relationships.
- Comparing old and new read outputs over a representative sample.

Example validation queries:

~~~sql
SELECT COUNT(*) AS missing_new_status
FROM orders
WHERE normalized_status IS NULL;

SELECT normalized_status, COUNT(*)
FROM orders
GROUP BY normalized_status
ORDER BY normalized_status;
~~~

On large tables, full `COUNT` or full comparisons can be resource-intensive. Use partitions, key ranges, batched statistics, or dedicated reconciliation jobs. Understand each check's limits: matching row counts do not prove individual record contents match.

### 11.1. Shadow reads and result comparison

Before switching completely, the application can read both old and new representations while returning only the old result. New results are compared in shadow mode.

Ensure:

- Shadow reads cause zero side effects.
- Writes or transactions are never duplicated.
- Normalized representations are compared fairly.
- Mismatches are logged without leaking sensitive data.
- Sampling rates are capped to avoid excessive load spikes.
- Mismatches are categorized by root cause.

Only when mismatches drop to acceptable levels and data checks pass should the team switch the read path to the new structure.

## 12. Switch: shifting the application to the new structure

Switch is the moment the application treats the new structure as the primary read source or routes writes to the new model.

Use feature flags or versioned configuration to:

- Shift a subset of requests to the new read path.
- Enable by tenant or cohort.
- Ramp up scope gradually.
- Pause if mismatches or latency climb.
- Revert to the old read path while compatible data remains intact.

Before switching, confirm:

- Backfill meets completion criteria.
- New data created during backfill has been synchronized.
- All writers uphold required invariants.
- Shadow reads or reconciliation show no mismatches beyond thresholds.
- Old application versions are no longer permitted to write in ways that break sync.
- A rollback or forward-fix plan is ready.

After switching, keep the old column for a safety period if still needed for rollback or legacy consumers. Never drop the old structure in the same release that switches reads.

## 13. Contract: removing the old structure in a separate stage

Contract removes structures no longer in use: old columns, old tables, redundant indexes, compatibility code, or dual-write paths.

Execute only when:

- All application instances have moved to the new version.
- Workers, batch jobs, reports, and consumers no longer read/write the old structure.
- No queries or dashboards depend on the old column.
- New data has been verified.
- The direct rollback window has ended or an alternative recovery plan exists.
- Appropriate backups and recovery plans are in place.
- DDL has been assessed for locks and execution time.

Contract should usually ship in a separate release. This ensures a sufficiently long observation period to uncover overlooked consumers.

A destructive change like `DROP COLUMN` must not be treated as a trivial rollback step. After deletion, restoring data may require backups or point-in-time recovery.

## 14. Decoupling long migrations from application deploy time

Do not let every application replica run the same lengthy data migration at startup. Doing so can cause:

- Multiple instances running the backfill simultaneously.
- Startup timeouts or readiness probe failures.
- Lock contention.
- Difficulty controlling retries and progress.
- Unstable rollouts when rolling updates spawn extra instances.

Split into dedicated job types:

1. **Schema migration job:** executes necessary DDL, usually brief and tightly controlled.
2. **Backfill job:** migrates data in batches, running independently with pause/resume support.
3. **Application deployment:** rolls out the compatible version.
4. **Validation job:** reconciles data and verifies invariants.
5. **Cutover job:** enables new read/write paths after approval.
6. **Contract job:** removes old structures in a separate release.

Migration jobs need a mechanism ensuring only one coordinator runs per migration or partition. Use advisory locks, leases, or database lock records. Locks must have timeouts and dead-worker handling to avoid permanent deadlocks.

## 15. Versioning and managing migration scripts

Migration scripts must be managed like source code:

- Each migration has a unique ID or version.
- Stored alongside the application or in a managed database repository.
- Reviewed and tested before production execution.
- Already-applied scripts are never arbitrarily edited.
- Checksums or metadata detect modified migration files.
- Execution status, timestamps, and outcomes are logged.
- Schema migrations are separated from long data backfills when lifecycles differ.
- Critical migrations have designated owners and runbooks.

Tools like Flyway or Liquibase provide migration history and version management. However, tools do not make SQL safe automatically. Teams still must evaluate locks, transactions, compatibility, and resumability.

If a migration has run in one environment, do not edit the old file expecting other environments to share identical history. Create a new migration to fix mistakes or append changes. This preserves the audit trail and avoids checksum mismatches.

## 16. Testing migrations before production

Migrations must be tested on data closely matching real structure and scale.

Testing layers:

- **Mapping unit tests:** every legacy value maps accurately to the new value.
- **Schema tests:** DDL builds the expected structure and runs cleanly on the target database version.
- **Compatibility tests:** old and new app versions operate with the schema during transition.
- **Backfill tests:** batches can re-run, resume, and handle concurrent new writes.
- **Load tests:** measure locks, latency, I/O, log growth, and replication lag.
- **Data validation tests:** verify counts, nulls, uniqueness, foreign keys, and business invariants.
- **Failure tests:** worker killed mid-batch, dropped connections, retries, and resuming from checkpoints.
- **Rollback/forward tests:** verify recovery procedures under realistic data conditions.

A tiny dataset may fail to expose performance issues of a table with tens of millions of rows. Test on representative datasets or sanitized, protected staging environments.

## 17. Integrating into CI/CD pipelines

Pipelines should explicitly model the stages and their dependencies.

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Review migration script"]
    B --> C["Schema compatibility test"]
    B --> D["Mapping and backfill test"]
    C --> E["Build release artifact"]
    D --> E
    E --> F["Expand schema"]
    F --> G["Deploy compatible app"]
    G --> H["Checkpointed backfill job"]
    H --> I["Data validation"]
    I --> J{"Gates pass?"}
    J -- "No" --> K["Hold, investigate, and resume"]
    J -- "Yes" --> L["Approve cutover"]
    L --> M["Switch read/write"]
    M --> N["Monitor"]
    N --> O["Contract in a separate release"]
~~~

Exact sequencing varies by deployment pattern and compatibility guarantees. In many systems, schema expand must run before deploying the new application. Backfills can run concurrently once compatible writers are deployed. Contract always waits until all legacy consumers are eliminated.

### 17.1. Pseudocode pipeline example

~~~yaml
pipeline:
  validate:
    steps:
      - check_migration_version
      - test_schema_compatibility
      - test_mapping_rules
      - test_backfill_idempotency

  release:
    steps:
      - build_once
      - publish_immutable_artifact

  expand:
    requires:
      - release
    steps:
      - acquire_migration_lock
      - apply_expand_schema
      - verify_schema
      - release_migration_lock

  deploy_compatible_application:
    requires:
      - release
      - expand
    steps:
      - deploy_compatible_artifact
      - verify_application_health

  backfill:
    requires:
      - expand
      - deploy_compatible_application
    execution:
      mode: resumable_job
      checkpoint: database_migration_progress
      batch_size: configured_and_tunable
      max_concurrency: bounded
      pause_when:
        - database_latency_high
        - replication_lag_high
        - lock_wait_exceeded

  validate_data:
    requires:
      - backfill
    steps:
      - compare_counts
      - check_nulls_and_constraints
      - verify_business_invariants

  cutover:
    requires:
      - validate_data
      - approval
    steps:
      - switch_read_path
      - verify_shadow_or_canary
      - monitor

  contract:
    requires:
      - cutover
      - compatibility_window_completed
      - approval
    steps:
      - verify_no_legacy_consumers
      - remove_old_schema
~~~

This is pseudocode, not a specific CI platform schema. In real implementations, ensure backfill jobs can restart without duplicate execution, enforce locks and least-privilege database permissions, and prevent a pipeline retry from accidentally triggering a second migration.

## 18. Observing progress and backfill stop conditions

Long backfills need dedicated telemetry, not just Running or Success job statuses.

Monitor:

- Counts of processed, updated, skipped, and failed rows.
- Batch processing throughput.
- Duration per batch and transaction.
- Remaining row counts or progress estimates.
- Lock waits and deadlocks.
- Database CPU, I/O, and connection usage.
- WAL/redo log growth.
- Replication lag.
- Application latency and error rates.
- Mismatch counts during validation.

Pause conditions may include database latency exceeding thresholds, rising replication lag, prolonged lock waits, or application SLO breaches. Abort conditions may include faulty mappings corrupting data, severe invariant violations, or unsafe operations detected.

Do not treat completion percentage as the sole signal. A backfill might hit 99% while the remaining 1% holds the hardest-to-map legacy records. Verify both quantity and quality of remaining data before cutover.

## 19. Rollback and data recovery

Schema rollbacks and data rollbacks carry different levels of difficulty.

- Adding a nullable column can usually stay in place if reverting to the old application.
- Dropping a new column prior to verification can destroy new data.
- Dual-writing can leave divergent representations if one write path failed.
- A misconfigured backfill mapping can alter millions of rows.
- `DROP COLUMN` or lossy transformations may be irreversible.

For long migrations, prefer **roll-forward** when data has changed in ways that cannot be safely reversed. Roll-forward means fixing mapping rules or running a compensating migration to restore valid data state rather than relying on a simple down script.

Before executing, prepare:

- Backups and tested restore procedures.
- Point-in-time recovery if supported by the database.
- Tables storing job checkpoints and status.
- Error logs or dead-letter storage for unmappable records.
- Runbooks for pause, resume, abort, and forward-fix.
- Policies retaining source data until verification completes.
- Plans for managing old and new apps during recovery.

A backup is only useful if verified to restore within service recovery-time objectives. Having a snapshot alone does not prove rollback readiness.

## 20. Security and permissions in migrations

Data migrations often require read/write access across large datasets. Never use full database admin credentials if the job only needs to update specific tables and columns.

Principles:

- Grant privileges scoped to required tables, schemas, and operations.
- Separate DDL credentials from backfill credentials when appropriate.
- Use secret managers or workload identity.
- Never write sensitive data to logs or reports.
- Mask or tokenize data in staging.
- Restrict access to production data reads.
- Audit which user or job executed the migration.
- Enforce timeouts, locks, and concurrency limits.
- Protect checkpoint and migration state tables.
- Revoke temporary credentials after job completion.

If a migration processes personal data, define its purpose, scope, retention duration, and storage locations. Never use unprotected production dumps as routine test data.

## 21. Full example: migrating order statuses

Suppose the legacy system stores order status in **legacy_status** with free-form values such as `new`, `settled`, `void`. The new design requires **normalized_status** accepting only `PENDING`, `PAID`, or `CANCELLED`.

### Phase A: Expand

Add the new nullable column:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(32);
~~~

The old app keeps reading and writing the old column. Do not apply `NOT NULL` yet because existing rows have not been migrated.

### Phase B: Deploy compatible version

The new version:

- Reads the new column when populated.
- Temporarily falls back to mapping from the old column.
- Updates both columns in the same transaction when writing status.
- Emits metrics for records missing a normalized status.

### Phase C: Batched backfill

Example batch over an ID range:

~~~sql
UPDATE orders
SET normalized_status =
  CASE legacy_status
    WHEN 'new' THEN 'PENDING'
    WHEN 'settled' THEN 'PAID'
    WHEN 'void' THEN 'CANCELLED'
    ELSE NULL
  END
WHERE id >= :start_id
  AND id < :end_id
  AND normalized_status IS NULL;
~~~

Unmappable values stay `NULL` so they can be reported and handled separately. Do not automatically assign a default status if doing so alters business meaning.

### Phase D: Validate

- Check count of rows still `NULL`.
- Check for values outside the allowed list.
- Reconcile counts per status.
- Compare mapping outputs over sample records.
- Verify new requests continue syncing both columns.

### Phase E: Switch

Enable the feature flag to read the new column for a subset of requests or the whole service after gates pass. Monitor mismatches, latency, and business errors. Keep the old column during the safety window.

### Phase F: Contract

After confirming no instances, workers, or reports use the old column, create a separate migration to remove it. Assess locks and backups beforehand.

## 22. Common anti-patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Bundling DDL and millions-of-rows backfill in one transaction | Long locks, huge logs, expensive rollbacks | Separate expand and batched backfill |
| Every app replica running data migration itself | Duplicate runs and lock contention | Dedicated migration job with locking |
| Dropping old column right after adding new column | Old versions or background workers fail | Use expand-contract and compatibility windows |
| Non-idempotent backfill | Retries corrupt or duplicate data | Design conditional updates and checkpoints |
| Writing checkpoint before committing data | May skip incomplete batches | Update checkpoint after commit |
| Running unthrottled backfill | Impacts live requests and replication | Throttle based on telemetry |
| Comparing row counts only | Misses faulty mappings or corrupted data | Check invariants and content |
| Dual-writing to two systems without sync mechanism | One side succeeds while the other fails | Use outbox/CDC and reconciliation |
| Modifying an already-run migration | Environments diverge in history | Create a new migration |
| Treating app rollback as data rollback | New data may be incompatible | Prepare forward-fix, backups, and PITR |

## 23. Checklist before separating schema and data migrations

**Design and compatibility**

- [ ] Separated structural schema changes from data transformations.
- [ ] Built compatibility matrix across old app, new app, and each schema state.
- [ ] Expand does not immediately break the old version.
- [ ] All writers, workers, reports, and consumers are accounted for.
- [ ] Mapping rules are explicit and handle invalid data.

**Backfill**

- [ ] Batch size and concurrency are bounded.
- [ ] Job is idempotent and checkpointed.
- [ ] Supports pause, resume, and retry.
- [ ] New rows created during backfill are covered.
- [ ] Throttling responds to latency, lock waits, and replication lag.
- [ ] Progress logging avoids exposing sensitive data.

**Validation and cutover**

- [ ] Checks cover NULLs, uniqueness, foreign keys, and invariants.
- [ ] Source/target data reconciliation is in place.
- [ ] Shadow reads or equivalence checks run when needed.
- [ ] Minimum completeness threshold is enforced before switch.
- [ ] Cutover requires approval and observability.
- [ ] Old structures are contracted only after the compatibility window.

**Operations and recovery**

- [ ] Migration scripts are versioned and reviewed.
- [ ] Only one worker coordinates each migration or partition.
- [ ] Backups exist and restore procedures are tested.
- [ ] Runbooks exist for pause, resume, abort, and forward-fix.
- [ ] Stop conditions trigger if the database or app is impacted.
- [ ] Credentials have least privilege and are revoked after use.

## 24. Conclusion

Separating schema changes from lengthy data migrations lowers database lock risk, avoids prolonging deployment times, and keeps multiple application versions running during transition. Expand-contract creates new structures without breaking old ones; backfills migrate data in batches with checkpoints and idempotency; validation provides evidence before switching; and contract removes old structures only once every consumer has transitioned.

Pipelines must manage these stages as jobs with distinct lifecycles, permissions, telemetry, and clear stop conditions. When you can pause/resume, reconcile data, monitor impact, and prepare forward-fixes or recovery, database changes become a controlled part of CI/CD rather than a risky operation tightly coupled to release cutover moments.
