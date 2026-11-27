# Data Backfilling and Multi-Step Schema Change Strategies

When a Spring Data JPA application needs to alter the structure of a table holding a large dataset, modifying the schema and deploying code all at once can break older application instances, hold long table locks, or leave old and new data inconsistent. A safer approach is to break the change into smaller steps, keeping concurrently running application versions able to read and write data throughout the transition period.

The common strategy is **Expand – Migrate – Contract**:

1. **Expand:** extend the schema in a backward-compatible way, typically by adding new columns/tables without removing old structures.
2. **Migrate:** deploy compatible code, backfill existing data in batches, verify data integrity, and gradually switch reads to the new structure.
3. **Contract:** once no code depends on the old schema and the rollback window has passed, drop old columns/tables in a separate deployment.

Backfilling is the process of transforming or populating existing data to satisfy the new schema/model. It must be re-runnable, track progress, limit database impact, and produce verifiable results.

## 1. Why Are Multi-Step Schema Changes Needed?

Suppose the `orders` table currently has a `customer_name` column. The application wants to switch to `customer_display_name` to clarify its purpose and normalize the data model.

If you deploy new code that only reads/writes `customer_display_name` while simultaneously renaming or dropping `customer_name`, old application instances during a rolling deployment may still access the old column and trigger SQL errors. If you backfill millions of rows inside a single migration transaction, lock duration, transaction logs, replication lag, and rollback difficulty can become severe issues.

Multi-step changes solve these risks by maintaining a period during which the schema can serve both old and new code.

Primary goals:

- Old application versions keep running while the new version is deployed.
- New data is written under consistent rules during the transition period.
- Legacy data is transformed in batches with checkpoints and retry capability.
- Metrics confirm the backfill completed and the data is accurate.
- Old structures are dropped only when no consumers still depend on them.

## 2. The Expand – Migrate – Contract Model

| Phase | Schema | Application | Data |
|---|---|---|---|
| Before change | Old column only | Reads/writes old column | Existing data |
| Expand | Add new column, keep old column | Old version keeps running | New column may still be NULL |
| Migrate – compatibility | Keep both columns | New code dual-writes both columns, initially still reads old column | Backfill legacy data in batches |
| Migrate – switch reads | Keep both columns | New code reads new column, continues dual-writing during rollback window | Reconcile data and monitor drift |
| Contract | Finally drop old column | Code no longer references old column | Schema contains only the new structure |

This sequence has a vital prerequisite: before the backfill finishes, every active writer must follow the synchronization rule. If an old instance writes only to `customer_name` after a row was already backfilled, the new column can become stale. You can solve this by waiting until all old writers are replaced, using application dual-writes, or using a temporary trigger if all writers cannot be upgraded simultaneously.

## 3. Example: Changing a Column Across Deployments

### 3.1. Expand: add the new column

Use a versioned migration to add a nullable column:

```sql
ALTER TABLE orders
ADD COLUMN customer_display_name VARCHAR(200);
```

Keep `customer_name` intact. Do not add `NOT NULL` yet if legacy data has not been backfilled and missing-value handling is not yet in place.

This is an illustrative SQL example; exact syntax, lock duration, and online execution support depend on the database management system. For large tables, check your database's DDL documentation and test on production-scale data.

In Spring Boot, schemas can be managed with Flyway or Liquibase. Example Flyway file:

```text
src/main/resources/db/migration/
  V042__add_customer_display_name.sql
```

Older application versions can usually keep running if you only add a nullable column they do not know about. Still, check `SELECT *` queries, stored procedures, views, triggers, replication consumers, and code dependent on column ordering.

### 3.2. Migrate: deploy dual-write

Once the new schema exists in all environments, deploy an application version capable of writing both columns. Initially, keep reading the old column so the switch does not depend on whether the backfill has finished.

The entity can map both fields during the transition period:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @Column(name = "customer_name")
    private String legacyCustomerName;

    @Column(name = "customer_display_name")
    private String customerDisplayName;

    public void changeCustomerDisplayName(String value) {
        this.legacyCustomerName = value;
        this.customerDisplayName = value;
    }
}
```

Place the synchronization rule inside a shared business method or mapper so write paths never forget to update one of the two fields. If the new value requires normalization, use the exact same conversion function for both live writes and the backfill.

If old instances that only write the old column are still running, dual-writing in the new version alone is not enough to guarantee consistency. Wait for the rollout to complete before backfilling, or deploy a compatible database synchronization mechanism. Never switch reads to the new column while any writer can still update only the old column.

### 3.3. Backfill: migrate existing data

Once compatible writers are deployed, backfill rows missing the new value. For example, if the transformation is a direct copy:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE customer_display_name IS NULL;
```

For small tables, a single statement may suffice. For large tables, do not run one massive UPDATE by default. Break it into small batches so each batch has a short transaction and can be retried.

### 3.4. Switch reads to the new column

Once the backfill is complete and data is verified, deploy an application version that reads `customer_display_name`. During the rollback window, keep writing both columns so the old version still has data if a rollback is needed.

Once no instances, workers, reports, or integrations read or write the old column, stop dual-writing and prepare to contract.

### 3.5. Contract: drop the old column

Drop the old column only after:

- No old application instances remain.
- Workers, scheduled jobs, scripts, reports, and integrated systems have switched to the new schema.
- The rollback window requiring the old column has elapsed.
- New data has been verified and a suitable recovery plan is in place.
- Views, indexes, constraints, triggers, and foreign keys referencing the old column have been checked.

The contract migration can be:

```sql
ALTER TABLE orders
DROP COLUMN customer_name;
```

This step breaks the old code's ability to read legacy data. Never combine this step into the expand or backfill migration. Deploying contract separately preserves a compatibility window and reduces rollback risk.

## 4. Batched Backfills, Keysets, and Checkpoints

### 4.1. Why split into batches?

A single transaction updating too many rows can:

- Hold row locks for a long time and block business requests.
- Generate huge transaction logs/WAL, increasing replication lag.
- Retain undo/version records for too long and increase vacuum/cleanup pressure depending on the database.
- Increase memory usage if loading all entities into the persistence context.
- Force a massive rollback if it fails.
- Make it hard to resume from the last completed position.

Batching bounds the number of rows per transaction, lets you pace work according to database load, and supports partial retries.

There is no single optimal batch size for every system. You can start with a few hundred or a few thousand rows, measure transaction duration, lock waits, CPU, I/O, and replication lag, then tune accordingly. Too-small batches incur excessive round-trips and commits; too-large batches create long transactions.

### 4.2. Prefer keysets over OFFSET

On large tables, `OFFSET` pagination grows increasingly expensive because the database must skip rows preceding the requested position. Use an ascending or stable key to resume from the last processed value.

Example query selecting IDs via keyset; the `LIMIT` syntax below fits PostgreSQL and several other databases—adjust for your dialect:

```sql
SELECT id
FROM orders
WHERE id > :lastId
  AND id <= :upperBound
  AND customer_display_name IS NULL
ORDER BY id
LIMIT :batchSize;
```

After fetching the batch of IDs, update that exact set:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE id IN (:ids)
  AND customer_display_name IS NULL;
```

The `customer_display_name IS NULL` predicate makes the operation idempotent: re-running the batch does not overwrite new values already dual-written by the application. `NamedParameterJdbcTemplate` can expand the `:ids` collection into bind parameters. Batch size must stay within the database/driver's bind parameter limit.

If source data can be NULL, clearly distinguish whether NULL is a valid value or erroneous data. If NULL is valid, you cannot rely solely on the target column being NULL to infer a row is unprocessed; use an ID checkpoint or a conversion status column and dedicated verification rules.

### 4.3. Persist checkpoints in the same transaction as the batch

A checkpoint table can track progress for each migration job:

```sql
CREATE TABLE migration_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    upper_bound_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

In each batch:

1. Read the current checkpoint.
2. Select the next set of IDs.
3. Update the batch's data.
4. Update `last_processed_id` to the last selected ID.
5. Commit both the data update and the checkpoint in the same transaction.

If the transaction rolls back, both the data and the checkpoint revert to the pre-batch state. When the job restarts, it reprocesses the uncommitted batch. If the checkpoint were written in a separate transaction, the checkpoint could advance while data was not updated, silently skipping records.

Lock or coordinate the checkpoint if multiple workers run the same job. To distribute work across multiple workers, design explicit claim/lease or row-locking mechanisms; never let multiple workers advance a simple single checkpoint without synchronization.

### 4.4. Example service processing one chunk

The following example uses `NamedParameterJdbcTemplate` and assumes the database supports `LIMIT` syntax. This illustrates a single chunk method, not a complete class:

```java
@Service
public class OrderBackfillChunkService {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderBackfillChunkService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ChunkResult process(
            long lastId,
            long upperBoundId,
            int batchSize) {

        var parameters = new MapSqlParameterSource()
                .addValue("lastId", lastId)
                .addValue("upperBound", upperBoundId)
                .addValue("batchSize", batchSize);

        List<Long> ids = jdbc.query("""
                SELECT id
                FROM orders
                WHERE id > :lastId
                  AND id <= :upperBound
                  AND customer_display_name IS NULL
                ORDER BY id
                LIMIT :batchSize
                """,
                parameters,
                (rs, rowNum) -> rs.getLong("id"));

        if (ids.isEmpty()) {
            return new ChunkResult(lastId, 0, true);
        }

        int updated = jdbc.update("""
                UPDATE orders
                SET customer_display_name = customer_name
                WHERE id IN (:ids)
                  AND customer_display_name IS NULL
                """,
                new MapSqlParameterSource("ids", ids));

        long nextId = ids.get(ids.size() - 1);

        // Update the checkpoint in the same transaction here.
        // If updating the checkpoint fails, the chunk's data changes also roll back.

        return new ChunkResult(nextId, updated, false);
    }

    public record ChunkResult(
            long lastProcessedId,
            int updatedRows,
            boolean finished
    ) {}
}
```

The orchestrator calls the chunk method from a separate Spring bean so each invocation runs in its own transaction. Avoid calling another `@Transactional` method on the same object via self-invocation, because internal calls bypass Spring's default transaction proxy.

The example above omits checkpoint saving/locking to keep chunk boundaries clear. In real implementations, update the checkpoint in the same transaction as the UPDATE statement. When `ids` is empty, run a final verification pass before marking the job complete.

### 4.5. Choosing a high-water mark and handling concurrent inserts

At job start, you can record `upper_bound_id` as the highest ID in the dataset to backfill. This bounds the job so it does not run indefinitely while the application continues inserting new rows.

However, sequences/identities may be allocated before an insert transaction commits. A transaction assigned an ID below the high-water mark may commit late after the backfill cursor has passed that position. Therefore:

- The new application must dual-write so newly created records always populate both values.
- After the main keyset pass, run a reconciliation pass to find any missing rows within the range.
- Account for late-committing records or source values modified during the backfill.
- Do not mark completion merely because the cursor passed the high-water mark; base completion on verified data conditions.

If using multiple workers, the database may support `FOR UPDATE SKIP LOCKED` so workers claim disjoint rows. This syntax is database-dependent and requires a matching checkpoint/lease strategy.

## 5. Idempotency, Retries, and Error Handling

A safe backfill must be re-runnable without corrupting already-migrated data. Guidelines:

- Update only unmigrated rows or rows explicitly identified as needing correction.
- Never overwrite newer values written by the application during dual-write.
- Use deterministic transformations: identical inputs must yield identical outputs.
- Commit data and checkpoints in the same transaction.
- Record counts of rows read, updated, skipped, and failed.
- Cap retries and distinguish transient errors from data errors.
- Log failed record IDs for separate remediation; never silently ignore them.

If a batch fails due to a deadlock or lock timeout, retry the batch transaction using a backoff policy. Do not retry indefinitely on schema errors, conversion failures, or invalid data. On repeated failures, halt the job or route problematic records to an error list for operator review.

For complex transformations, store an algorithm version or migration tag as well. When transformation logic changes, you need to know which records were processed by which version and whether they must be re-run.

## 6. Synchronizing Data While the Application Is Live

Backfills usually run while the system serves live traffic, creating contention between the job and the application.

For example, the job reads `customer_name = 'An'` while a concurrent request updates it to `'Anh An'`. If the job writes the stale value after the request commits, the new column can be overwritten incorrectly.

Mitigations:

1. **Dual-write before backfilling:** new code writes both old and new columns in the same transaction.
2. **Conditional updates:** backfill writes only when the new column is still NULL, avoiding overwriting newer values.
3. **Clear deployment ordering:** wait for all legacy writers to be upgraded or have a sync trigger before switching reads.
4. **Reconciliation:** after backfilling, scan for missing rows or mismatches against the transformation rule.
5. **Optimistic locking or version checks:** use when transformations must detect concurrent modifications rather than silently overwriting.
6. **Rate limiting:** throttle the job when database load or replication lag spikes.

Never use a single massive transaction for the entire backfill just to avoid races. Long transactions hold locks longer and create far greater impact. Use small batches, control write ordering, and apply appropriate update predicates.

## 7. Validating Data After Backfilling

Do not rely solely on a "job completed" log message. Validate data against defined invariants.

For the column-copy example:

```sql
-- Rows still missing the new value
SELECT COUNT(*)
FROM orders
WHERE customer_name IS NOT NULL
  AND customer_display_name IS NULL;

-- Rows with mismatched values
SELECT COUNT(*)
FROM orders
WHERE customer_display_name IS DISTINCT FROM customer_name;
```

`IS DISTINCT FROM` is PostgreSQL syntax for NULL-safe comparison; other databases may require an equivalent expression. If the transformation normalizes values, compare using the business rule, such as `LOWER(TRIM(customer_name))`.

Verification steps may include:

- Total rows within the backfill scope.
- Counts of migrated, remaining, and failed rows.
- Comparing old/new values against transformation rules.
- Checking duplicates, foreign keys, and uniqueness.
- Spot-checking a sample of records manually.
- Verifying active writers continue producing valid data.
- Monitoring drift over an observation window before switching reads.

If NULL is a valid value, separate "processed with NULL result" from "unprocessed." Use ID checkpoints, a status table, or a migration marker column to distinguish them.

## 8. Adding Constraints Once Data Is Ready

A new column is typically added nullable so old code does not break. Add `NOT NULL`, unique constraints, or foreign keys only after backfilling and verifying data.

Example:

```sql
ALTER TABLE orders
ALTER COLUMN customer_display_name SET NOT NULL;
```

The syntax above is PostgreSQL. On other databases, syntax and locking levels differ. Some engines support adding constraints in an unvalidated state and validating existing rows separately to reduce impact on live tables. Check online DDL capabilities and lock times in your target database.

Before adding constraints:

- Confirm no disallowed NULLs remain.
- Check for duplicates before unique constraints.
- Check for orphan records before foreign keys.
- Decide whether a default carries real business meaning or merely masks missing data.
- Evaluate locks, index builds, and replication lag.
- Deploy constraints only after all writers comply with the new rule.

Never add an arbitrary default solely to make a migration pass. A synthetic default can make invalid data appear valid while violating business semantics.

## 9. Organizing Migrations with Flyway or Liquibase

Flyway and Liquibase are well suited for managing versioned schema changes and deployment history. You can split steps across multiple migrations:

```text
V042__expand_add_customer_display_name.sql
V043__add_backfill_checkpoint_table.sql
V044__add_indexes_for_backfill.sql
V050__contract_drop_customer_name.sql
```

Migration files should focus on small, predictable, sequentially ordered schema changes. Backfilling millions of rows is usually better handled by a dedicated job with checkpoints, metrics, retries, and pause/resume support rather than a long-running startup migration.

Flyway/Liquibase can create checkpoint tables or record backfill logic versions. The job runs only after the expand migration has been applied. The contract migration deploys in a later release once no dependencies remain.

In production, manage schemas via controlled migrations and configure Hibernate in mapping verification mode, for example:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Do not rely on `ddl-auto=update` for critical schema changes in production. Hibernate cannot replace the expand/backfill/validate/contract workflow.

Note that DDL may implicitly commit or be non-rollbackable depending on the database. Never assume all schema statements execute inside a rollbackable transaction. Test migrations against the exact database type and version you run.

## 10. Backfilling with JDBC or JPA?

| Approach | Advantages | Limitations |
|---|---|---|
| Batched JPA entities | Reuses application mappings, converters, lifecycle callbacks, and validation | Persistence context memory overhead; entity-by-entity processing can be slow |
| JDBC/NamedParameterJdbcTemplate | Direct SQL, efficient bulk updates, and precise control | Bypasses entity listeners, dirty checking, cascades, and automatic auditing |
| Stored procedures | Runs close to the database and cuts round-trips | Database-dependent logic, harder to test and port |
| Spring Batch | Built-in chunks, checkpoints, retries, skips, and job metadata | Requires additional job/step design and operations |

When backfilling via JDBC, explicitly handle audit and version fields. Direct UPDATE statements do not trigger `@PreUpdate`, `AuditingEntityListener`, or `@Version` increments. If a technical actor must be recorded, pass an explicit value such as `migration:customer-display-name`; if this is strictly a technical migration not considered a business update, establish a policy on whether `updated_at` stays untouched.

JDBC also does not synchronize an open persistence context. If earlier operations in the same transaction loaded entities, flush pending JPA changes before running bulk SQL, then refresh/clear affected entities appropriately. After updating outside Hibernate, consider evicting related L2/query caches if the application uses caching.

## 11. Rollback and Recovery Planning

Rolling back code is not the same as rolling back data. After backfilling, the new column holds data; once new code starts writing new data, the old column must stay synchronized so the old version can still read it.

During the compatibility window:

- Retain both old and new columns.
- Continue dual-writing throughout the rollback window.
- Never drop the old column in the same release that switches reads.
- Keep backfill checkpoints and logs to know which ranges were processed.
- Prepare a reconciliation or recovery plan if the transformation had bugs.

Once contract has run and dropped the old column, rolling back requires restoring the schema and potentially recovering data from backups or reconstructing it from the new column. Never assume a drop-column migration can be reversed without data loss.

For one-way or lossy transformations, capture snapshots, exports, or staging tables before altering data. Clearly define who approves the contract step and what criteria must be met before executing it.

## 12. Operating and Monitoring Backfill Jobs

A production job should provide at minimum:

- Job name, algorithm version, and run ID.
- Upper bound, last processed ID, and current status.
- Expected total rows, rows processed, updated, skipped, and failed.
- Per-batch duration, throughput, and retry count.
- Lock waits, deadlocks, CPU/I/O, and replication lag.
- Start/end timestamps and the operator or service account that started it.
- Controlled pause/resume/cancel mechanisms.

Dry-run on staging with a realistic copy of data. When production load is high, reduce batch size or pause based on thresholds. Jobs should have time bounds and alerts if progress stalls or error counts cross thresholds.

Prevent unintended concurrent job runs. Use locks/leases or coordination mechanisms so only one runner owns the checkpoint, unless explicitly designed for multiple workers.

## 13. Testing the Schema Change Strategy

A thorough test suite should cover:

1. **Migration from legacy schema:** spin up a database at the previous version and run the expand migration.
2. **Legacy app compatibility:** confirm old code still reads/writes cleanly once the new column exists.
3. **Rolling deployment:** test old and new versions running side by side, especially writers.
4. **Dual-write:** verify an update keeps both columns consistent.
5. **Idempotent backfill:** run the same batch twice and confirm the second run does not corrupt valid data.
6. **Restart/resume:** stop the job mid-way, restart it, and verify checkpoints resume accurately.
7. **Concurrent writes:** update a record while backfilling and confirm newer values are not overwritten.
8. **Data validation:** check NULLs, mismatches, uniqueness, foreign keys, and error records.
9. **Contract:** test dropping the column only after old code and legacy consumers are gone.
10. **Rollback:** test reverting to the previous application version while the schema remains compatible.

Use the same database type as production in integration tests. H2 or in-memory databases can differ in DDL, locking, isolation, indexes, and SQL syntax; passing on H2 does not prove a migration is safe on real PostgreSQL/MySQL/Oracle.

## 14. Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Dropping/renaming a column in the same code release | Old instances fail accessing the schema | Expand first, contract later |
| Backfilling before all writers are compatible | New column goes stale when old writers update the old column | Wait for writer rollout or use temporary sync |
| Running one UPDATE across a large table | Long locks, log bloat, replication lag, and massive rollback | Split into batches, commit per chunk |
| Using OFFSET on large tables | Later pages become progressively slower | Use keysets on a stable key |
| Writing checkpoints in a separate transaction | Progress can advance ahead of uncommitted data | Update checkpoint in the chunk's transaction |
| Non-idempotent retries | Data gets overwritten or duplicated | Conditional updates and stable reconciliation keys |
| Relying only on completion logs | Failed rows or NULLs go unnoticed | Run reconciliation and verification queries |
| Adding NOT NULL before backfilling | Migration or old writers fail | Add nullable, backfill, validate, then enforce |
| Using ddl-auto=update in production | Uncontrolled schema changes | Use Flyway/Liquibase |
| Dropping old column before rollback window ends | Cannot safely roll back to old code | Separate contract into a later release |

## 15. Pre-Deployment Checklist

- [ ] Defined old schema, target schema, and data transformation rule.
- [ ] Expand migration adds only compatible structures without dropping old columns.
- [ ] Inventoried all writers/readers: web apps, workers, schedulers, reports, scripts, and external systems.
- [ ] Planned dual-write or a compatible synchronization mechanism.
- [ ] Backfill configured with batch size, keyset, upper bound, and checkpoints.
- [ ] Data updates and checkpoints commit in the same transaction.
- [ ] Update conditions are idempotent and do not overwrite newer data.
- [ ] Retry/backoff, error limits, and resume support are implemented.
- [ ] Reconciliation and data validation queries are prepared.
- [ ] Evaluated indexes, locks, transaction logs, replication lag, and online DDL.
- [ ] Decided handling for audit fields, `@Version`, caches, and persistence context when using JDBC.
- [ ] Tested migrations, backfills, restarts, and rollbacks on a production-equivalent database.
- [ ] Contract executes only after no legacy schema consumers remain and the rollback window has closed.

Multi-step schema changes keep the application running while data is transformed. Expand creates compatible new structures, migrate deploys dual-writes and checkpointed batched backfills, and contract removes old structures only after verification and once rollback is no longer needed. Designing idempotent, resumable backfills verified by data invariants is the foundation for safe deployments on large tables.