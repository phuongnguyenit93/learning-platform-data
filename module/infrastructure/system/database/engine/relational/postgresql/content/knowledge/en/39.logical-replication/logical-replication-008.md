# Data Conflicts, Apply Errors, and Handling Data Drift in PostgreSQL Logical Replication

## 1. Why Can Logical Replication Stop?

PostgreSQL logical replication transmits changes at the logical row-operation level from a publisher to a subscriber. The publisher writes WAL; logical decoding reads WAL and generates a change stream; the replication connection sends changes; the apply worker on the subscriber applies transactions to target tables.

This flow works smoothly when schemas, replica identities, constraints, and data on the subscriber match changes from the publisher. However, the subscriber may already hold different data, receive local writes, or have an incompatible structure. When the apply worker attempts to apply a transaction that the subscriber rejects, that transaction can fail and replication cannot advance past the failing position.

Common scenarios:

- An incoming INSERT collides with a primary key/unique key on the subscriber.
- An UPDATE or DELETE cannot find the matching row.
- A row on the subscriber has different values due to local writes or manual edits.
- A constraint on the subscriber rejects data sent by the publisher.
- Schemas on the two sides are incompatible.
- Replica identity is insufficient to locate rows for UPDATE/DELETE.
- Initial table synchronization encounters data or constraint conflicts.
- A failing transaction is retried yet keeps failing because the root cause has not been fixed.

```text
PUBLISHER
   |
   | WAL / logical decoding
   v
Logical replication stream
   |
   v
SUBSCRIBER apply worker
   |
   +-- Valid transaction
   |       |
   |       v
   |    COMMIT / advance origin
   |
   +-- Conflict / SQL error
           |
           v
       Transaction abort
           |
           v
       Apply progress stops
           |
           v
       Diagnose -> repair / resync / controlled skip
```

**Logical replication does not automatically merge two divergent datasets into one consistent dataset.** When a conflict occurs, find the cause, determine the business source of truth, and choose a controlled remediation.

### Learning Objectives

After this lesson, you will be able to:

1. Describe publisher, logical decoding, replication stream, and subscriber apply worker.
2. Distinguish logical replication from physical streaming replication.
3. Identify duplicate key, missing row, and constraint conflicts.
4. Understand the role of replica identity in UPDATE/DELETE.
5. Analyze schema drift, publication filters, and subscriber-side writes.
6. Distinguish apply errors from initial table synchronization errors.
7. Read pg_stat_subscription, pg_stat_subscription_stats, and replication origin status.
8. Locate the failing transaction/LSN in PostgreSQL logs.
9. Diagnose errors in order from schema, identity, and constraints down to row contents.
10. Repair subscriber data without losing valid transactions.
11. Understand the risks of skipping transactions.
12. Design a workflow to resync a table or an entire subscription.
13. Prevent conflicts through ownership, schema migrations, and write routing.
14. Verify data after the apply worker resumes.
15. Build runbooks and monitoring to detect data drift early.

---

## 2. How Does Logical Replication Work?

Logical replication uses a publication on the publisher and a subscription on the subscriber.

- **Publisher:** the database emitting changes.
- **Publication:** defines tables and types of changes published.
- **Logical decoding:** converts WAL into logical changes.
- **Replication slot:** retains WAL needed by a logical consumer.
- **Subscription:** configures connection, publications, and apply behavior on the subscriber.
- **Apply worker:** receives and applies changes.
- **Table synchronization worker:** performs initial copy for newly synchronized tables when needed.

```text
Publisher table
      |
      v
WAL records
      |
      v
Logical decoding
      |
      v
Publication stream
      |
      v
Subscription connection
      |
      v
Apply worker
      |
      v
Subscriber table
```

### 2.1. Transaction Boundaries

Logical replication transmits changes per transaction. The apply worker applies changes belonging to a transaction and commits on the subscriber via replication mechanics.

If a transaction encounters a constraint violation, it cannot commit normally on the subscriber. Subsequent transactions cannot be applied past the failing transaction in stream order.

### 2.2. A Subscription Has Multiple Workers

In addition to the main apply worker, PostgreSQL can run table synchronization workers for initial table copies. When investigating, distinguish errors in the main apply worker from errors during per-relation copy/synchronization.

### 2.3. Logical Replication Is Not Automatic Multi-Master

Built-in logical replication primarily transmits changes unidirectionally from publisher to subscriber. If applications write concurrently on both sides or multiple publishers write the same data, you must design conflict resolution/ownership yourself. Never treat a subscription as an automatic multi-master system.

## 3. How Logical Replication Differs from Physical Replication

| Characteristic | Physical replication | Logical replication |
|---|---|---|
| Unit of transfer | Physical-level WAL records | Logical row changes/transactions |
| Scope | Whole cluster at physical level | Tables/objects selected by publications |
| Schema | Data files and catalogs travel together | Schema must be managed separately |
| Subscriber | Standby in recovery | Independent operating database |
| Writes on replica | Standby is normally read-only | Subscriber can accept local writes, though risky for conflicts |
| Cross-version | Requires physical compatibility | Useful for certain migrations/version upgrades |
| Conflicts | Recovery/replication consistency issues | Unique, missing row, constraints, schema/data drift |
| PITR | Base backup + WAL | Separate backups needed for publisher/subscriber; logical stream does not replace PITR |

### 3.1. Schema Does Not Replicate Automatically

Logical replication does not automatically transmit CREATE TABLE, ALTER TABLE, CREATE INDEX, or any other DDL. Schema changes must be deployed on the subscriber in a compatible order.

### 3.2. Sequences Are Not Synchronized Like Table Rows

Sequence values/identity states are not automatically synchronized by logical replication in a way that guarantees the subscriber always has the right next value. After migration/failover or before allowing writes on a subscriber, check sequence state.

### 3.3. Objects Outside Publication Scope

Roles, grants, extensions, large objects, and objects outside logical table publications must be managed via separate workflows.

## 4. What Is a Conflict?

A conflict occurs when the subscriber cannot apply a logical change given its current data/structural state.

They can be grouped into categories:

| Group | Example | Symptom |
|---|---|---|
| Key conflict | INSERT duplicates primary key | duplicate key value violates unique constraint |
| Missing row | UPDATE/DELETE cannot find row | could not find row / affected row mismatch |
| Constraint conflict | CHECK/FK/NOT NULL/unique | violates constraint |
| Schema conflict | Missing column/table or incompatible type | column/relation/type error |
| Identity conflict | Cannot identify row to UPDATE/DELETE | replica identity/key error |
| Initial sync conflict | Copying data into target hits duplicate/constraint | table sync worker error |
| Operational conflict | Permissions, triggers, DDL, or object state | permission denied / relation missing |

### 4.1. Conflicts Do Not Always Originate from the Publisher

The subscriber may have received local writes, an operator may have edited rows manually, a migration may have altered schemas, or another job may have created keys before replication applied.

### 4.2. An Apply Error Can Halt the Entire Subscription

A failing transaction usually prevents the apply worker from advancing past that transaction. The worker launcher may try restarting it, yet the same deterministic error will repeat until the root cause changes.

### 4.3. Never Skip Errors Just to Lower Lag

If the apply worker resumes after skipping a transaction while missing data remains absent, the subscriber can diverge permanently. Identify affected data and the repair method before proceeding.

## 5. Duplicate Key on INSERT

Suppose the publisher emits:

```sql
INSERT INTO public.customers (customer_id, email)
VALUES (1001, 'a@example.com');
```

Yet the subscriber already has customer_id = 1001. The apply worker can fail with:

```text
ERROR: duplicate key value violates unique constraint
DETAIL: Key (customer_id)=(1001) already exists.
```

Possible causes:
- The subscriber previously received local writes.
- The row was inserted manually or by another batch job.
- Initial copy re-ran onto an unclean target table.
- Another subscription emitted the same row.
- Data was restored from mismatched snapshots.
- Publisher and subscriber used unsynchronized key generation.

### 5.1. Inspect Rows on Both Sides

Publisher:

```sql
SELECT *
FROM public.customers
WHERE customer_id = 1001;
```

Subscriber:

```sql
SELECT *
FROM public.customers
WHERE customer_id = 1001;
```

Compare all relevant business columns, not just the primary key.

### 5.2. Do Not Automatically Delete Subscriber Rows

The row may hold valid new data written locally by an application. Determine ownership and source of truth before deleting or overwriting.

### 5.3. If the Subscriber Row Is a Removable Duplicate

Save evidence, verify there are no foreign key/business dependencies, and apply the fix in a transaction with backup per policy. Then let the apply worker retry the publisher transaction.

### 5.4. If the Subscriber Row Holds Data That Must Be Kept

Perform reconciliation: merge fields, move local data to another table, or adjust keys/ownership per design. Do not default to skipping.

## 6. UPDATE Cannot Find Row

The publisher updates:

```sql
UPDATE public.orders
SET status = 'SHIPPED'
WHERE order_id = 5001;
```

If the subscriber lacks row order_id = 5001, apply may fail to find the tuple to update.

Causes:
- Row was deleted locally on the subscriber.
- Initial sync was incomplete or skipped.
- Row was excluded by a publication row filter.
- Publisher/subscriber did not start from compatible snapshots.
- Replica identity mismatched.
- Schema/partition routing placed the row in a different relation.
- An earlier skip omitted the INSERT that created the row.

### 6.1. Check Both Sides

Look up the row on both publisher and subscriber. Verify whether the publication includes that table/row and whether the subscriber relation is in ready state.

### 6.2. Check Replica Identity

If UPDATE/DELETE cannot identify the tuple on the subscriber via the transmitted identity, apply can fail. Review replica identity and table definitions.

### 6.3. Restoring a Missing Row

If the publisher is the source of truth, you can retrieve the current row from the publisher and insert it into the subscriber via a repair workflow. However, account for subsequent transactions in the stream and avoid creating duplicates.

## 7. DELETE Cannot Find Row

The publisher emits DELETE, yet the subscriber has no matching row. This can happen because:
- The row was deleted locally.
- The row was never initially synced.
- A prior INSERT transaction was skipped.
- Row filter/publication scope changed.
- Subscriber data drifted.

### 7.1. Confirm Whether the Row Should Actually Exist

If the subscriber is designed to hold only a subset of data, the row may fall outside the current publication/filter. Do not treat every missing row as corruption before checking publication semantics.

### 7.2. Check Operation History

Inspect audit logs, application logs, migration scripts, and manual SQL to learn when the row was deleted.

### 7.3. Repair According to Source of Truth

If the row was validly deleted on the publisher, the subscriber must reflect that state. If the row was accidentally deleted on the subscriber, restore/merge the row before continuing if needed.

## 8. Constraint Conflicts

The subscriber can reject a row due to an incompatible constraint.

Common types:

- PRIMARY KEY / UNIQUE: duplicate key.
- FOREIGN KEY: referenced row missing or deleted out of order.
- CHECK: value violates condition.
- NOT NULL: publisher sends NULL into a required column.
- Exclusion constraint: value violates exclusion rule.
- Trigger: logic on subscriber modifies/rejects the row.

### 8.1. Subscriber Has a Stricter Constraint Than Publisher

For example, the publisher allows status = 'PENDING_REVIEW', while the subscriber's CHECK allows only 'NEW', 'PAID', 'SHIPPED'. Valid publisher data still fails on apply.

### 8.2. Foreign Key Dependencies

If a publication omits the parent table while the subscriber enforces an FK to that parent table, inserting a child fails because the referenced row does not exist yet. Synchronize full dependencies or design appropriate constraints.

### 8.3. Triggers on the Subscriber

Triggers can execute side effects, alter data, or raise exceptions. Identify which triggers run in the apply context and whether they truly belong on the subscriber.

### 8.4. Do Not Drop Constraints Just to "Keep Running"

Temporarily dropping constraints lets invalid data enter the subscriber. If a constraint must change, evaluate business invariants and synchronize schemas on both sides.

## 9. Replica Identity and UPDATE/DELETE

Logical replication must identify which row changed. Replica identity determines what old-row information is used to find the tuple on the subscriber.

By default, PostgreSQL uses the primary key as replica identity if available.

Check:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity,
    c.relhasindex
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
```

### 9.1. Modes

- DEFAULT: uses primary key if the table has one.
- USING INDEX: uses a suitable unique index as identity.
- FULL: uses all old row values as identity.
- NOTHING: records no identity for UPDATE/DELETE; typically appropriate only for INSERT-only tables in publications.

Catalog characters may be d/f/i/n for the modes; verify against your version.

### 9.2. Tables Without a Primary Key

If a table publishes UPDATE/DELETE without a suitable replica identity, logical replication may be unable to identify rows. Create an eligible unique index or consider REPLICA IDENTITY FULL.

### 9.3. REPLICA IDENTITY FULL

Example:

```sql
ALTER TABLE public.events
REPLICA IDENTITY FULL;
```

FULL can enlarge WAL/logical change payloads and make row lookups on the subscriber more expensive, especially on wide/large tables. Prefer a suitable unique index when design permits.

### 9.4. USING INDEX

Example:

```sql
ALTER TABLE public.devices
REPLICA IDENTITY USING INDEX devices_replica_key;
```

The index must satisfy PostgreSQL requirements for replica identity. Verify uniqueness, non-partiality, non-expression structure, and column suitability before using.

## 10. Schema Drift Is a Common Source of Errors

Logical replication does not automatically synchronize DDL. If publisher and subscriber schemas drift, the apply worker can hit:
- Relation does not exist.
- Column does not exist.
- Incompatible data type.
- NOT NULL column missing a default on subscriber.
- Differing constraints/indexes.
- Incorrect partition/table mapping.
- Differing triggers/functions.

### 10.1. Compare Schemas Before Enabling Publications

Use migration tools or controlled schema diffs. Compare table names, column names/types, nullability, defaults, identity, constraints, and related indexes.

### 10.2. Order of Deploying Schema Changes

A common workflow:
1. Add compatible structures on the subscriber first.
2. Deploy publisher changes per plan.
3. Verify apply.
4. Backfill if needed.
5. Switch application usage.
6. Drop old structures only after all consumers have transitioned.

Exact ordering depends on migration type; do not apply one rigid sequence to every DDL change.

### 10.3. Adding Columns

If the publisher starts sending a new column before the subscriber has the matching column, apply can fail. Prepare the subscriber schema before the publisher emits changes.

### 10.4. Dropping/Renaming Columns

Do not assume logical replication maps column renames automatically. Deploy compatible changes and check column mapping behavior for your version.

### 10.5. Data Types

Types may require casting/compatibility. Do not compare type names alone; verify domains, enum labels, collations, typmods, and semantics.

## 11. Publication Scope, Row Filters, and Column Lists

A subscriber does not necessarily receive every row from the publisher. A publication can restrict:
- Tables.
- Operation types: INSERT/UPDATE/DELETE/TRUNCATE.
- Row filters.
- Column lists.

Inspect publication tables:

```sql
SELECT
    pubname,
    schemaname,
    tablename
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

### 11.1. Row Filters

If a publication only emits rows meeting a condition, the subscriber is not a full mirror of the publisher table. When filter conditions change, understand how stale/newly qualifying rows are synchronized for your version.

### 11.2. Column Lists

If a publication emits only certain columns, subscriber schemas and defaults must match. Subscriber columns not sent can retain defaults/local values per design, though ownership must be clearly defined.

### 11.3. Publish Options

Options such as publish INSERT/UPDATE/DELETE/TRUNCATE dictate which change types are emitted. If an operation is unpublished, the subscriber may intentionally differ from the publisher.

### 11.4. Do Not Label Every Difference an Error

Data differences may be an expected subset from a publication/filter. Compare the subscriber against the exact publication contract, not blindly against the full publisher table.

## 12. Local Writes on the Subscriber

This is dangerous because it can introduce divergence without an immediate apply error.

Example:
1. Publisher creates customer_id = 1001.
2. Subscriber receives a local write for customer_id = 1001.
3. Publisher emits INSERT with the same key or UPDATE on the row.
4. Apply worker hits a conflict or subscriber data gets overwritten/diverges on subsequent operations.

### 12.1. Unidirectional Flows Require Clear Ownership

If the publisher is the source of truth, applications must write to the publisher. The subscriber primarily serves reads, analytics, or migration consumers.

### 12.2. When the Subscriber Needs to Write

Separate subscriber-local data into dedicated schemas/tables outside the publication, or design an explicit merge/ownership mechanism.

### 12.3. Do Not Assume the Subscriber Is Read-Only by Default

A logical subscriber can accept local writes. Enforce control via roles/permissions, application routing, and operational policies.

### 12.4. Multiple Publishers

If multiple publishers send changes to the same subscriber table, handle key collisions, ordering, ownership, and conflict resolution at the architectural layer. Built-in logical replication does not automatically resolve multi-master conflicts.

## 13. Initial Table Synchronization

When creating a subscription with initial data copy, PostgreSQL can run table synchronization workers. This process copies a snapshot and coordinates WAL changes to bring each table to a consistent state.

Conflicts can appear if:
- The subscriber table already holds old data.
- Local writes occur during the copy.
- Constraints/schemas mismatch.
- A table sync worker lacks privileges.
- The table structure changes mid-sync.
- Publication membership changes during the copy.

### 13.1. Checking Relation Synchronization State

The pg_subscription_rel catalog stores per-relation synchronization state:

```sql
SELECT
    s.subname,
    r.srrelid::regclass AS relation_name,
    r.srsubstate,
    r.srsublsn
FROM pg_subscription_rel AS r
JOIN pg_subscription AS s
  ON s.oid = r.srsubid
ORDER BY s.subname, relation_name;
```

Internal state codes can vary by version; check matching documentation/catalogs before automating.

### 13.2. Table Sync Workers and Apply Workers Differ

A table may not be ready yet even while the main apply worker is running. Monitor worker types and relation states.

### 13.3. copy_data

When creating/refreshing a subscription, the copy_data option determines whether existing data for relations newly added to the subscription under that workflow is copied. Do not toggle it arbitrarily without understanding relation states.

### 13.4. Do Not Arbitrarily Run Initial Copy on Non-Empty Target Tables

If a subscriber table already has data, initial copy can create duplicate/constraint conflicts. Prepare empty tables or follow a pre-designed seed/snapshot procedure.

## 14. Apply Workers and Subscription Status

On the subscriber, inspect:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relation_name;
```

View and column definitions may differ by PostgreSQL major version; use queries suited to your server.

### 14.1. pid

PID shows the active worker at the time of inspection. If NULL or rows are missing unexpectedly, check subscription enabled state and logs.

### 14.2. received_lsn

The latest WAL/logical stream position received by the worker per view semantics. It does not prove by itself that transactions were applied/committed.

### 14.3. latest_end_lsn and latest_end_time

These fields help track stream progress and the last processed/reported timestamp. Cross-reference with publisher and replication origin status to understand apply progress.

### 14.4. Worker Type

Some versions include a field distinguishing apply workers from table synchronization workers. Use it to see which worker is running; verify the view schema on your server.

## 15. Subscription Error Statistics

On PostgreSQL versions featuring pg_stat_subscription_stats:

```sql
SELECT
    subname,
    apply_error_count,
    sync_error_count,
    stats_reset
FROM pg_stat_subscription_stats
ORDER BY subname;
```

These counters show whether apply or table synchronization errors occurred. Availability/columns depend on version.

### 15.1. Counters Do Not Replace Logs

Counters show error counts, not the full transaction, constraint, row key, or root cause. Read PostgreSQL server logs.

### 15.2. Stats Reset

Counters can be reset. Record reset timestamps and track deltas instead of comparing raw cumulative totals without a timeframe.

### 15.3. Steadily Rising Counters

The worker may be retrying a deterministic error. Identify the transaction/LSN and fix the root cause instead of merely restarting the subscription.

## 16. Replication Origin Status

Logical apply uses replication origins to track progress of remote changes.

Inspect via:

```sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status
ORDER BY external_id;
```

### 16.1. remote_lsn

The remote WAL/logical stream position applied/recorded for the origin per replication origin semantics.

### 16.2. local_lsn

The corresponding local WAL position for recorded progress on the subscriber.

### 16.3. Origins Are Not Data Diffs

Origin status shows progress, not that rows on publisher and subscriber are identical. Skipped transactions or subscriber-local writes can cause drift even while progress advances.

### 16.4. Never Advance Origins Arbitrarily

Replication origin management functions can cause the subscriber to skip changes. Never call advance manually to "fix lag" without a full reconciliation and verification plan.

## 17. Reading PostgreSQL Logs to Locate Failing Transactions

When apply fails, logs are usually the primary source to determine:
- Subscription name.
- Apply worker PID.
- SQLSTATE/error message.
- Constraint/table/column.
- Key values if logged by the server.
- Transaction/remote LSN context.
- Error timestamp and retry count.

### 17.1. Start from the First Error

Subsequent repeated errors may simply be worker retries. Find the first log entry after the subscription stopped advancing.

### 17.2. Record the Transaction Finish LSN If Present

Some errors/log contexts provide the remote transaction's LSN. Save this value before restarting/skipping so you can correlate accurately.

### 17.3. Avoid Overly Broad Long-Term Logging

Logging all statements/parameters can create huge log volumes and expose sensitive data. Increase logging only selectively for a controlled window.

### 17.4. SQLSTATE and Constraint Names

SQLSTATE categorizes the error; constraint name/table/key helps locate the row to investigate. Preserve original details in incident records.

## 18. General Diagnostic Procedure

When a subscriber stops applying:

1. Identify the subscription and publisher/subscriber pair.
2. Check whether the subscription is enabled.
3. Check the apply worker/table sync workers.
4. Read the first error log and identify SQLSTATE.
5. Record the transaction/remote LSN if available.
6. Identify the relation and operation (INSERT/UPDATE/DELETE).
7. Compare schema, replica identity, publication scope, and constraints.
8. Compare the row on publisher and subscriber.
9. Check subscriber-local writes/triggers/jobs.
10. Choose row/schema repair, table resync, or controlled skip.
11. Restart/enable apply per runbook.
12. Monitor LSN/origin progress and verify data after apply resumes.

### 18.1. Preserve Evidence Before Fixing

Save logs, row snapshots, schema definitions, LSNs, subscription state, and timestamps. Never alter data before capturing evidence needed for investigation.

### 18.2. Do Not Look at Lag Alone

Growing lag is a symptom. Find the first unapplied transaction and why it failed.

### 18.3. Distinguish Transient vs. Deterministic Errors

Network disconnects/temporary storage issues may self-recover. Duplicate keys, missing rows, or schema mismatches usually require data/structural fixes before retries succeed.

## 19. Controlled Repair of Duplicate Keys

Suppose logs show INSERT of key 1001 hit a duplicate.

Procedure:

1. Read row 1001 on both publisher and subscriber.
2. Determine whether the subscriber row came from an application, import, or replication.
3. Check foreign keys and references.
4. Determine the source of truth.
5. Back up/export the row and audit evidence.
6. Choose action: keep row, merge, re-key, or delete duplicate.
7. Execute within an appropriate transaction.
8. Verify unique constraints.
9. Allow the apply worker to resume.
10. Verify post-error transactions and related data.

Example deleting a subscriber row only after confirming it is a removable seed/duplicate:

```sql
BEGIN;

SELECT *
FROM public.customers
WHERE customer_id = 1001
FOR UPDATE;

-- Execute DELETE only after confirming ownership
-- and saving required evidence/backups.

COMMIT;
```

Do not run automated DELETE examples in production. The actual fix depends on real data and business ownership.

## 20. Controlled Repair of Missing Rows

If the publisher has a row that the subscriber lacks:

1. Determine whether the row is missing due to a filter or data corruption.
2. Check whether the transaction that created the original row was skipped.
3. Verify the publication emits INSERT for the table.
4. Check subscriber relation state.
5. Check identity and schema.
6. Fetch an accurate snapshot/row from the publisher.
7. Ensure dependent rows/constraints follow proper order.
8. Insert/merge the row per repair procedure.
9. Let the apply worker retry the failing transaction.
10. Verify data is not duplicated or wrongly overwritten.

If the publisher modified the row multiple times after it went missing on the subscriber, decide whether to apply current state or reconstruct history. A single snapshot INSERT is not always enough to restore exact transaction semantics.

## 21. Fixing Constraint/Schema Conflicts

If errors stem from constraints:
- Compare definitions on both sides.
- Determine whether data is valid under business rules.
- Align CHECK/FK/UNIQUE/NOT NULL semantics.
- Check defaults/generated expressions.
- Check triggers and permissions.
- Deploy migrations in a compatible order.
- Revalidate constraints if using a NOT VALID workflow.
- Resume apply and inspect rows.

### 21.1. Never Permanently Relax Constraints Just to Keep Replication Running

If a constraint protects a critical invariant, keep the invariant on both sides. Find why publisher data did not conform or which migration was missed.

### 21.2. Do Not Add Stricter Subscriber Constraints That the Publisher Cannot Meet

The subscriber must accept every row sent under the publication contract, unless an explicit architectural exception exists.

### 21.3. Type/Domain/Enum Changes

Synchronize enum labels, domain constraints, type casts, and extension definitions before the publisher emits new values.

## 22. Transaction Skip: A Controlled Last Resort

Some PostgreSQL versions support:

```sql
ALTER SUBSCRIPTION sub_orders
SKIP (lsn = '0/16B6C50');
```

This command tells the subscription to skip one remote transaction at the specified LSN per version semantics. Syntax, conditions, and when the worker processes the skip must be verified against your PostgreSQL major version.

### 22.1. Skips the Entire Transaction

Skipping does not omit just one row/statement inside a transaction. It can skip the entire remote transaction, including changes across many other tables.

### 22.2. Data Consequences

The publisher committed the transaction while the subscriber skipped it, so the subscriber may miss rows or retain stale state. Apply progress advances while data divergence remains.

### 22.3. When Should It Be Considered?

Only when:
- The failing transaction is identified precisely.
- Its full impact is understood.
- A data compensation/repair plan exists.
- The business owner accepts the consequences.
- Evidence and LSN are recorded.
- Post-skip verification exists.

### 22.4. Do Not Use Skip for Every Duplicate Key

A duplicate may be a single conflicting row inside a transaction containing many other valid changes. Prefer repairing subscriber state whenever possible.

### 22.5. Never Advance Origins Manually Instead of Skipping

Arbitrarily changing replication origins can skip a wider range of changes than the failing transaction. Use only documented mechanisms with a recovery plan.

## 23. Pausing and Restarting a Subscription

You can control a subscription:

```sql
ALTER SUBSCRIPTION sub_orders DISABLE;
ALTER SUBSCRIPTION sub_orders ENABLE;
```

### 23.1. DISABLE

Stops the subscription's apply worker. Use when repairing schemas/data or investigating without letting the worker retry continuously.

### 23.2. ENABLE

Restarts apply per configuration. If the root error is unfixed, the worker may hit the same transaction again.

### 23.3. Do Not Restart Repeatedly

Restarting does not fix duplicate keys, missing rows, or schema drift. Re-enable only after fixing the root cause or deciding on a skip/resync.

### 23.4. Monitor After Enabling

Verify apply worker PID, latest_end_lsn, origin progress, logs, and relevant table data.

## 24. Resynchronizing a Single Table

If a table has drifted severely, row-by-row repair may no longer be reliable. You may need to resync the table from the publisher per procedure.

Approaches can include:
- Using a publication membership/refresh workflow so the table runs initial sync again per version and catalog state.
- Stopping apply and performing a controlled snapshot copy.
- Using dump/restore for the table within a consistency-planned window.
- Creating a new subscription/table and cutting over after verification.

### 24.1. Never Arbitrarily TRUNCATE the Subscriber

TRUNCATE can destroy local data or drop rows not managed by the publisher. Confirm the subscriber table is strictly a replica of the source and take a backup.

### 24.2. Publication Remove/Add Workflow

Some workflows remove a relation from a publication, refresh the subscription, and re-add it to trigger initial copy. Exact behavior depends on version, subscription state, and copy_data. Test in staging before applying.

### 24.3. Snapshot Consistency

The snapshot used to copy the table must align with a consistent point compatible with the WAL stream applied afterward. If snapshot and replication origin mismatch, changes can be lost or duplicated.

### 24.4. Verify Before Cutover

Compare row counts, key ranges, checksums/aggregates, constraints, and application queries. Mark the table ready only after verification passes.

## 25. Resynchronizing an Entire Subscription

When multiple tables have drifted or replication origins are no longer trustworthy, rebuilding the subscription/consumer may be necessary.

A plan may look like:
1. Identify the source of truth and maintenance window.
2. Back up the current subscriber.
3. Record subscription/publication definitions and slot identity.
4. Stop apply.
5. Prepare the subscriber schema.
6. Obtain a consistent snapshot/base data.
7. Create the new subscription/slot per plan.
8. Copy data and start applying WAL from a compatible point.
9. Compare critical data.
10. Cut over application reads.
11. Monitor lag/errors.
12. Clean up old subscriptions/slots only after proving no consumer depends on them.

### 25.1. Slot Lifecycle

Replication slots on the publisher retain WAL for subscribers. Dropping/recreating slots can lose resumability from the old position and require a full resync.

### 25.2. Avoid Two Apply Workers Writing the Same Table

During transition, never let both old and new subscriptions apply to the same target table unless the workflow is explicitly designed to avoid duplicates/conflicts.

### 25.3. Keep a Rollback Point

Retain a subscriber snapshot/backup and record LSN/slot/origin states before making changes. If resync fails, you must have a path back to a controlled state.

## 26. Inspecting Publication and Subscription Definitions

On the publisher:

```sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
```

Table list:

```sql
SELECT
    pubname,
    schemaname,
    tablename
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
```

On the subscriber:

```sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications,
    subbinary
FROM pg_subscription
ORDER BY subname;
```

Some catalog columns vary by version. Query catalogs only with appropriately privileged roles and verify against your version.

### 26.1. Do Not Share Connection Strings

Catalogs can contain sensitive connection information. Never put passwords/conninfo into logs, tickets, or public docs.

### 26.2. Verify Publication Table Scope

If a table is missing from the publication, the subscriber receives no changes. That may be a missing configuration or intended behavior.

### 26.3. Check Whether the Subscription Is Enabled

When a subscription is disabled, the apply worker does not run. Do not investigate data conflicts before confirming subscription state.

## 27. Checking Row Differences

For small tables, you can compare key ranges directly. Example:

```sql
SELECT customer_id, email, status
FROM public.customers
WHERE customer_id BETWEEN 1000 AND 1100
ORDER BY customer_id;
```

Run on both publisher and subscriber, save results in a controlled manner, and compare.

### 27.1. Row Counts Are Not Enough

Two tables with equal row counts yet differing keys/values are still drifted. Compare primary keys and critical business columns.

### 27.2. Aggregate Checksums

You can compute aggregates/hashes over key ranges to pinpoint differing ranges, though checksums must be stable across encoding, NULL handling, column order, and collation.

### 27.3. Range Partitioning Comparisons

For large tables, divide by primary key/time partitions to isolate differences. Avoid simultaneous full table scans in production if costly.

### 27.4. Snapshot Consistency

If the publisher is still accepting writes during comparison, two queries may read snapshots from different points in time. Use a consistent snapshot/replication point or pause writes in a maintenance window.

## 28. Data Drift Without Apply Errors

A subscriber can drift even while the apply worker remains active:
- Subscriber received local writes.
- Table is not in the publication.
- Row filter excluded certain rows.
- Column list omitted some columns.
- Sequence state is unsynchronized.
- DDL differs.
- An earlier transaction was skipped.
- Application read from the wrong node/timeline.
- A table sync has not finished.

### 28.1. Healthy Apply Does Not Mean Identical Data

The apply worker may have processed the entire stream without covering data outside the publication contract.

### 28.2. Sequence Drift

Logical replication does not automatically sync sequence states. If the subscriber starts accepting writes after cutover, sequences may issue already-existing keys. Synchronize sequences per migration/cutover runbooks.

### 28.3. DDL Drift

If the subscriber has extra local columns or differing constraints, apply may succeed for a while and then fail once the publisher sends an incompatible value.

### 28.4. Audit by Ownership

Explicitly document which tables are publisher-owned, subscriber read-only, subscriber-local, or shared-by-design. Without ownership, every discrepancy is hard to explain.

## 29. Data Modified by Triggers

Triggers on the subscriber can:
- Modify values before writing.
- Create audit rows.
- Call auxiliary functions.
- Send notifications.
- Raise exceptions.
- Modify other tables.

### 29.1. Side Effects Can Repeat

Apply worker transaction retries can cause trigger side effects to execute repeatedly across transaction rollbacks/attempts, depending on implementation. Never send emails/payments directly from triggers during logical apply.

### 29.2. Triggers Must Be Idempotent or Controlled

If triggers are required on the subscriber, design safe side effects and understand replication apply behavior. External side effects should flow through an outbox/idempotent consumer.

### 29.3. Disabling Triggers Is Not the Default Fix

Disabling triggers can bypass business invariants. Do so only under a migration/repair plan with validation and rollback.

## 30. Foreign Keys and Data Ordering

Logical apply preserves stream transaction semantics, yet a publication may omit dependent tables. A subscriber enforcing FKs can reject rows if parent rows do not exist.

Example:
- Publisher emits INSERT into order_items.
- Publication does not emit the orders table.
- Subscriber enforces FK order_items.order_id → orders.id.
- Parent row does not exist yet on subscriber.
- Apply transaction fails.

### 30.1. Check Publication Dependencies

List all FKs and identify every parent/child table needing synchronization. Never assume publications automatically include related tables.

### 30.2. Never Drop FKs Without an Invariant Plan

If the subscriber needs FKs to protect data integrity, synchronize parent data/ordering properly.

### 30.3. Initial Copy Order

Table synchronization can run in parallel. FKs across tables during initial sync must be designed/tested for your PostgreSQL version and workflow; never assume tables copy in FK order.

## 31. TRUNCATE and Publications

Logical replication can publish TRUNCATE if the publication is configured for this operation per version. TRUNCATE differs from DELETE: it affects the entire table or partition set per semantics, with no row-by-row predicate.

### 31.1. Local Subscriber Data

If the subscriber contains local rows, a replicated TRUNCATE can wipe them out. This is another reason to isolate subscriber-local data from replicated tables.

### 31.2. Foreign Key Restrictions

TRUNCATE has restrictions with FKs, and publishing/applying it requires reviewing the entire relation set. Check PostgreSQL docs/version before enabling.

### 31.3. Do Not Use TRUNCATE to Reset Table Drift Without a Snapshot

You can lose valid data and expose an empty table to reading applications during resync.

## 32. Asynchronous DDL Migrations

A safe migration workflow must specify ordering for publisher/subscriber.

Example adding a column:
1. Add compatible column on subscriber first.
2. Add column on publisher.
3. Verify apply worker continues.
4. Deploy application code per rollout plan.
5. Backfill if needed.
6. Add constraints once data satisfies conditions.
7. Drop old column on both sides in a subsequent release.

### 32.1. Expand-Contract

An expand-contract strategy keeps schemas compatible while two versions run concurrently:
- Expand: add new structure.
- Migrate: dual-compatible reads/writes and backfill.
- Validate: verify data.
- Contract: remove old structure once all consumers have transitioned.

### 32.2. Enum Additions

If the publisher sends an enum label the subscriber lacks, apply can fail. Sync enum labels before applications/publisher emit new values.

### 32.3. Type Changes

Type changes require checking binary/text compatibility and column mapping. Test in staging with representative data.

## 33. Changing Publication Row Filters

Row filters determine which rows are emitted from the publisher. When a filter changes, the subscriber may lack full rows matching the new condition unless an appropriate backfill/sync workflow runs.

Example publication emitting only:

```sql
CREATE PUBLICATION pub_active_customers
FOR TABLE public.customers
WHERE (active = true);
```

If a row flips from active=false to true, the subscriber may begin receiving row updates/inserts per publication/version semantics. If it flips the other way, behavior and removing rows from the subscriber must be verified against PostgreSQL version/operations.

### 33.1. Filters Are Not Row-Level Security

Publication row filters define logical replication scope. They do not replace authorization/security policies.

### 33.2. Filter Changes Need a Backfill Plan

Document which rows are added/removed, how rows leaving scope are deleted, and how subscriber correctness is verified.

### 33.3. Do Not Compare Full Tables

Compare against the active publication contract and filter.

## 34. Binary Mode and Type Compatibility

Subscriptions may have a binary transfer option in supported versions. Binary representation can impose stricter type/encoding compatibility requirements than text conversion.

### 34.1. Do Not Enable Binary to Fix Apply Errors

If the error is a duplicate key or missing row, binary transfer does not solve the root cause.

### 34.2. Version/Type Compatibility

Check source/target major versions, type send/receive functions, extension types, and collations. Test all critical custom types.

### 34.3. Error Context

For cast/type errors, capture SQLSTATE, column/type name, and sanitized sample values before modifying schemas.

## 35. Permissions and Apply Roles

The apply worker connects per subscription configuration and needs appropriate privileges on the subscriber. Errors can stem from:
- Table owner/privileges.
- Schema USAGE.
- INSERT/UPDATE/DELETE grants.
- Sequence privileges in application workflows.
- Trigger/function permissions.
- RLS/policies or security settings.
- Missing extensions/functions.

### 35.1. Distinguish Permission Errors from Data Conflicts

permission denied is not a duplicate key. Read SQLSTATE and object names before applying fixes.

### 35.2. Least Privilege

Grant privileges required for replication apply per version/documentation. Never make the subscription user a superuser merely to bypass permission errors.

### 35.3. Verify After Migrations

A migration may alter owners or grants on the subscriber without touching the publisher. Include grants in schema deployment workflows.

## 36. Errors from Multiple Subscriptions or Publishers

If the same subscriber table receives changes from multiple subscriptions:
- Primary keys can collide.
- Transaction ordering across publishers is not guaranteed as a single stream.
- The same row can be updated in conflicting orders.
- Deletes/updates may fail to find rows.
- Constraint conflicts can arise intermittently.

### 36.1. Keyspace Design

If merging multiple sources is genuinely required, use distinct key namespaces/tenant/source identifiers.

### 36.2. Ownership Partitioning

Partition tables/rows by owner so each source writes only its own partition of data, or use an application-level merge pipeline.

### 36.3. Conflict Resolution Layer

Multi-source replication requires deterministic conflict resolution rules: last-write-wins, version vectors, owner priority, or domain-specific merges. Built-in subscription apply does not provide those business semantics automatically.

## 37. Pausing Apply to Investigate

When errors repeat and repair time is needed:

```sql
ALTER SUBSCRIPTION sub_orders DISABLE;
```

After fixing:

```sql
ALTER SUBSCRIPTION sub_orders ENABLE;
```

### 37.1. Targeted Stopping

A subscription can cover many tables. Disabling stops apply for that entire subscription, affecting all subscribed relations. Document the blast radius.

### 37.2. Do Not Halt Publisher Writes by Default

Publisher writes can continue if the slot retains WAL and storage suffices. However, monitor lag/WAL retention to prevent disk exhaustion.

### 37.3. Verify Capacity for Long Pauses

Replication slots retain WAL on the publisher. Leaving a subscription disabled for a long time can grow pg_wal.

## 38. Transaction Skip: Decision Procedure

Before skipping:
1. Identify the exact remote transaction LSN.
2. Save logs and transaction context.
3. List all tables/rows modified in the transaction if possible.
4. Determine the impact if the subscriber omits those changes.
5. Check whether subscriber rows can be repaired so the transaction applies normally.
6. If not, build a data repair plan for every skipped change.
7. Obtain approval from the appropriate owner per policy.
8. Execute the command matching your PostgreSQL version.
9. Monitor apply progress.
10. Reconcile data and record evidence.

### 38.1. Skipping Is Not Conflict Resolution

It only lets the stream advance past the selected transaction; it does not resolve data discrepancies.

### 38.2. Skipping Large Transactions

A transaction may modify thousands of rows/multiple tables. Never fix only the single row mentioned in the error message and blindly skip the whole transaction.

### 38.3. Never Skip an Unidentified Transaction

If logs do not identify the LSN/transaction or side effects remain unclear, pause and gather more evidence.

## 39. Verification After Apply Resumes

After repair/enable/skip, check:
- Apply worker is running.
- latest_end_lsn is advancing.
- Replication origin remote_lsn is advancing.
- Error counters stop increasing.
- Logs show no recurring old errors.
- Table sync states are ready.
- Affected rows match source-of-truth.
- FK/unique/check constraints are valid.
- Sequence states match the plan.
- Application read paths do not return stale/wrong data.

Example:

```sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relation_name;
```

### 39.1. LSN Progress Does Not Prove Data Equality

After a skip, origin progress can advance even though transaction changes were omitted. Data reconciliation is mandatory.

### 39.2. Check Transactions Following the Error

Ensure the stream does not apply just one transaction and halt again on the next.

### 39.3. Monitor Through a Representative Workload Window

An apply worker running for a few seconds does not prove stability across batch/peak workloads.

## 40. Monitoring and Alerting

A logical replication dashboard should include:

| Metric | Source | Purpose |
|---|---|---|
| Subscription enabled | pg_subscription | Detect disabled subscriptions |
| Apply worker PID | pg_stat_subscription | Detect non-running workers |
| Latest end LSN/time | pg_stat_subscription | Track progress |
| Apply/sync error counters | pg_stat_subscription_stats when supported | Detect errors |
| Replication origin LSN | pg_replication_origin_status | Track apply progress |
| Table sync state | pg_subscription_rel | Detect tables not yet ready |
| Slot retained WAL | pg_replication_slots | Detect WAL retention |
| Publisher WAL rate | LSN samples | Measure source pressure |
| PostgreSQL logs | Server logs | Root cause/SQLSTATE |
| Data drift checks | Reconciliation jobs | Detect silent divergence |

### 40.1. Alert When Apply Worker Disappears

An enabled subscription with no apply worker may be erroring, disabled, or idle depending on state. Combine logs and latest progress.

### 40.2. Alert When Progress Stalls

If the publisher has changes yet latest_end_lsn/origin progress stalls beyond threshold, investigate apply worker/connectivity.

### 40.3. Alert on Slot Retention

A failing subscriber can cause the publisher to retain WAL for a long time. Monitor disk headroom and retained distance.

### 40.4. Periodic Data Drift Checks

Select critical tables, key ranges, and aggregates for comparison at consistent snapshots. Do not wait for an apply error to uncover divergence.

## 41. Designing Ownership and Write Routing

To prevent conflicts, each table needs an ownership contract:

| Table class | Owner | Subscriber policy |
|---|---|---|
| Publisher-owned | Primary publisher | Subscriber read-only |
| Subscriber-local | Subscriber application | Excluded from publication |
| Shared/reference | Designated owner | Updated via controlled workflow |
| Aggregated | Pipeline/consumer | Has rebuild/reconciliation logic |
| Migration staging | Migration process | Isolated from production tables |

### 41.1. Permissions Enforce Ownership

Use database roles so subscriber applications cannot UPDATE/DELETE publisher-owned tables outside approved workflows.

### 41.2. Schema Separation

Example:
- public_replica: publisher-owned data.
- local_app: subscriber-only data.
- integration_stage: staging/reconciliation data.

Schema names are examples only; choose based on architecture.

### 41.3. Document the Source of Truth

Every table must have a documented owner, publication, expected filters, local-write policy, and recovery process.

## 42. Data Reconciliation Strategy

A reconciliation strategy may include:

1. Identify the source of truth.
2. Choose a snapshot/consistent point.
3. Define tables/key ranges to compare.
4. Compute row counts and key coverage.
5. Compare values of critical columns.
6. Compute checksums/aggregates per partition/key range.
7. Classify missing/extra/changed rows.
8. Identify root causes.
9. Build an audited repair set.
10. Apply repairs during a maintenance window or safe workflow.
11. Re-run comparison.
12. Save evidence and close the incident.

### 42.1. Do Not Auto-Merge All Differences

A newer value on the subscriber could be a valid local write. Business ownership/version semantics are needed.

### 42.2. Idempotent Repairs

Repair scripts should use explicit preconditions and verify pre-state and post-state. Re-running must not create duplicates or unintended overwrites.

### 42.3. Audit Repairs

Record keys, old/new values per data policy, source, reason, timestamp, operator, and ticket/change reference.

## 43. Example Runbook for Duplicate Key

**Scenario:** apply worker reports duplicate key on public.orders, order_id = 9001.

1. Disable the subscription if the worker is continuously retrying and an investigation window is needed.
2. Save logs, LSN, worker PID, and stats.
3. Query order 9001 on both publisher and subscriber.
4. Check application logs and audits to trace the origin of the subscriber row.
5. Check foreign keys/child rows.
6. Decide whether to keep the publisher row, merge the subscriber row, or fix keys.
7. Execute the repair inside a transaction with evidence saved.
8. Enable the subscription.
9. Confirm the apply worker advances past the failing transaction.
10. Compare the order and child rows.
11. Check error counters/logs.
12. Record corrective actions: block local writes or fix seeding procedures.

### 43.1. If the Publisher Row Is Correct

The subscriber row may need to be moved/merged or removed after verifying dependencies.

### 43.2. If the Subscriber Row Must Be Preserved

Do not delete it; reconcile into a single record with clear ownership and decide how the publisher continues emitting changes.

### 43.3. If the Duplicate Is Caused by Sequences

Logical replication does not automatically sync sequence states. Verify sequences/identities and key generation on the subscriber before cutting over writes.

## 44. Example Runbook for Missing Row UPDATE

**Scenario:** publisher UPDATEs order_id = 9001, yet the subscriber lacks the row.

1. Save the apply error and remote transaction context.
2. Query order 9001 on the publisher.
3. Verify whether the subscriber has the row.
4. Check publication/filters and initial sync state.
5. Check whether an earlier INSERT transaction was skipped.
6. Check subscriber local DELETEs/audits.
7. Fetch an appropriate row snapshot from the publisher.
8. Repair the subscriber row and dependent data.
9. Enable apply.
10. Confirm UPDATE applies and the stream continues.
11. Reconcile the table/range to detect other missing rows.
12. Fix the root cause.

If publisher transactions updated the row multiple times, choose an appropriate snapshot state and avoid replaying history incompatible with the repair.

## 45. Practice Exercises with Answers

### Exercise 1. What is a logical replication conflict?

**Answer:** A situation where the subscriber cannot apply a logical change because current data, schemas, identities, constraints, or state are incompatible.

### Exercise 2. Does logical replication automatically resolve duplicate keys?

**Answer:** No. Applying the transaction normally fails; investigate and repair data or use a controlled skip workflow per version.

### Exercise 3. What does a duplicate key on INSERT usually mean?

**Answer:** The subscriber already holds a key violating a unique/primary key when applying INSERT.

### Exercise 4. What can cause UPDATE to miss a row?

**Answer:** Locally deleted row, incomplete initial sync, filters, replica identity, or an earlier skipped transaction.

### Exercise 5. What can cause DELETE to miss a row?

**Answer:** Subscriber already lacked the row, data drifted, filters, or a prior change was not applied.

### Exercise 6. What does an apply error do to a subscription?

**Answer:** The apply worker cannot advance past the failing transaction; the worker may retry, yet deterministic errors repeat until the root cause is fixed.

### Exercise 7. Does logical replication automatically replicate DDL?

**Answer:** No. Schema changes must be managed separately on the subscriber.

### Exercise 8. Is sequence state synchronized automatically by logical replication?

**Answer:** Not in a way that guarantees the next value; check/synchronize per cutover plan.

### Exercise 9. What is replica identity used for?

**Answer:** Identifying the old row to UPDATE/DELETE on the subscriber.

### Exercise 10. What does replica identity DEFAULT usually use?

**Answer:** The primary key if the table has a primary key.

### Exercise 11. Can a table without a primary key replicate UPDATE/DELETE?

**Answer:** Yes, if configured with an eligible replica identity such as a valid unique index or FULL; NOTHING is insufficient for UPDATE/DELETE.

### Exercise 12. What is the trade-off of REPLICA IDENTITY FULL?

**Answer:** Records more old-row values and can increase WAL/lookup cost.

### Exercise 13. What can happen if the subscriber has a stricter CHECK constraint than the publisher?

**Answer:** Applying a row valid on the publisher gets rejected by the subscriber.

### Exercise 14. What error can occur if an FK parent is omitted from a publication?

**Answer:** Child row apply can fail because the referenced parent does not yet exist on the subscriber.

### Exercise 15. What risk do subscriber-local writes pose?

**Answer:** Creating duplicate/missing rows or silent data divergence from the publisher.

### Exercise 16. Is built-in logical replication multi-master?

**Answer:** No. It does not automatically resolve conflicts across multiple writers modifying the same data.

### Exercise 17. Can a publication row filter cause the subscriber to have fewer rows than the publisher?

**Answer:** Yes, that can be an expected subset per the publication contract.

### Exercise 18. Where is pg_stat_subscription queried?

**Answer:** On the subscriber, to inspect apply/table sync workers and progress by version.

### Exercise 19. What does pg_stat_subscription_stats provide?

**Answer:** On supported versions, provides apply_error_count and sync_error_count along with stats_reset.

### Exercise 20. What does pg_replication_origin_status show?

**Answer:** Remote/local LSN progress of replication origins; it does not prove row data is identical.

### Exercise 21. Why is reading PostgreSQL logs necessary?

**Answer:** Logs include SQLSTATE, constraints/tables, keys, and transaction context/LSNs to pinpoint the root error.

### Exercise 22. Does restarting a subscription fix a duplicate key?

**Answer:** No. It usually causes the same failing transaction to be retried.

### Exercise 23. When is DISABLE subscription used?

**Answer:** When pausing apply intentionally to investigate or repair while monitoring WAL retention.

### Exercise 24. What does SKIP transaction skip?

**Answer:** Skips the entire remote transaction at the specified LSN per version semantics, not just one row.

### Exercise 25. Why can skipping cause drift?

**Answer:** The publisher committed the changes while the subscriber omitted all changes in that transaction.

### Exercise 26. Should every duplicate key be skipped?

**Answer:** No. A transaction may contain many valid changes; prefer repairing the subscriber whenever possible.

### Exercise 27. When is resyncing a table necessary?

**Answer:** When drift is large/untrustworthy and row-by-row repair is unsuitable; a snapshot-consistent procedure is required.

### Exercise 28. Should you arbitrarily TRUNCATE a subscriber table to resync?

**Answer:** No. You risk losing local data and breaking consistency; confirm ownership, backups, and copy workflows.

### Exercise 29. What does pg_subscription_rel help with?

**Answer:** Shows per-relation synchronization state per catalog/version.

### Exercise 30. Are apply workers and table sync workers the same?

**Answer:** No. One applies the stream; table sync workers perform initial copy/sync for individual relations.

### Exercise 31. Can a subscriber drift even when the apply worker is healthy?

**Answer:** Yes, due to local writes, publication filters, skipped transactions, sequence/schema drift, or objects outside publications.

### Exercise 32. What does pg_publication_tables help with?

**Answer:** Lists tables belonging to publications to verify scope.

### Exercise 33. Why do schema migrations require ordering?

**Answer:** The publisher may send a new column/type before the subscriber is ready, causing apply to fail.

### Exercise 34. What is the benefit of expand-contract?

**Answer:** Keeps schemas compatible across multi-version rollouts and makes migrations safer.

### Exercise 35. Can triggers on the subscriber cause apply errors?

**Answer:** Yes. Triggers can raise exceptions or alter data/side effects.

### Exercise 36. Should emails/payments be sent directly from subscriber triggers?

**Answer:** No. Retries/rollbacks can trigger repeated side effects; use an outbox/idempotent consumer.

### Exercise 37. Should pg_replication_origin_advance be used to fix lag?

**Answer:** Never arbitrarily. It can skip a whole range of changes and cause data loss.

### Exercise 38. When does sequence drift usually surface?

**Answer:** When the subscriber begins receiving writes/at cutover and the next sequence value collides with existing keys.

### Exercise 39. Do equal row counts prove identical data?

**Answer:** No. Keys/values may still differ; key-range comparisons and checksum/semantic checks are required.

### Exercise 40. Why is snapshot consistency important during reconciliation?

**Answer:** Both sides may still have activity; comparing two snapshots from different instants creates false discrepancies.

### Exercise 41. What risks exist when multiple subscriptions write to one table?

**Answer:** Key collisions, ordering ambiguity, and update/delete conflicts; ownership/merge design is required.

### Exercise 42. Why watch WAL when a subscription is disabled?

**Answer:** The replication slot may retain WAL needed by the subscriber; long pauses can grow pg_wal.

### Exercise 43. Can pg_stat_subscription latest_end_lsn advance while data still drifts?

**Answer:** Yes, for instance if transactions were skipped or local data differs from the publication contract.

### Exercise 44. Is a permission denied error a data conflict?

**Answer:** No. It is a privilege/object access error; read SQLSTATE and fix grants appropriately.

### Exercise 45. Can TRUNCATE be published?

**Answer:** Yes, per publication operation options/version; evaluate full-table and FK impact.

### Exercise 46. How are table synchronization errors detected?

**Answer:** Combine logs, worker state, and pg_subscription_rel relation synchronization state.

### Exercise 47. How to perform a transaction skip safely?

**Answer:** Identify LSN/transaction, full impact, business approval, repair plan, and before/after verification.

### Exercise 48. How to prevent subscriber-local writes from causing conflicts?

**Answer:** Isolate local schemas/tables, enforce read-only permissions on publisher-owned tables, and document the source of truth.

### Exercise 49. When must an entire subscription be resynced?

**Answer:** When many tables/origin state have drifted severely or incremental repair is untrustworthy; a snapshot/slot/cutover plan is needed.

### Exercise 50. What is the closure criterion for an apply error incident?

**Answer:** Root cause fixed, worker advances past the error, no further retries, data reconciliation/constraints pass, and progress/evidence recorded.

## 46. Logical Replication Conflict Handling Checklist

| Phase | Question |
|---|---|
| Identification | Which publisher, subscriber, and subscription? |
| Status | Is the subscription enabled? |
| Worker | Is the apply worker or a table sync worker failing? |
| Logs | What are SQLSTATE and the first error? |
| Transaction | Is the remote transaction LSN available? |
| Relation | Which table and operation (INSERT, UPDATE, DELETE, or TRUNCATE)? |
| Identity | Is the replica identity appropriate? |
| Schema | Are columns/types/defaults/constraints compatible? |
| Publication | Are table, operation, filter, and column list correct? |
| Data | How do the rows on publisher and subscriber differ? |
| Ownership | Are there subscriber-local writes or trigger side effects? |
| Repair | Can row/schema be repaired so apply runs normally? |
| Skip | If skipping, what does the entire transaction affect? |
| Resync | Are snapshot and WAL/origin points compatible? |
| Retention | How much WAL is the slot retaining while apply is stopped? |
| Verification | Are workers, LSN/origin progress, and logs advancing cleanly? |
| Data QA | Do keys, values, constraints, and business invariants pass? |
| Prevention | Have ownership, permissions, and migration workflows been fixed? |
| Evidence | Are logs, LSNs, before/after states, and operator actions recorded? |

## 47. Official PostgreSQL Documentation

- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber architecture and limitations.
- [Logical Replication Conflicts](https://www.postgresql.org/docs/current/logical-replication-conflicts.html) — conflicts when applying changes.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences, and restrictions.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — publication tables and operation options.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — subscriptions and initial copy.
- [ALTER SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-altersubscription.html) — enable/disable, refresh, and skip options by version.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — subscription/replication monitoring views.
- [pg_replication_origin_status](https://www.postgresql.org/docs/current/view-pg-replication-origin-status.html) — replication origin progress.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html) — logical slot retention.
- [Replica Identity](https://www.postgresql.org/docs/current/logical-replication-publication.html) — identity requirements for published updates/deletes.

Logical replication behavior, skip syntax, catalog columns, worker views, and conflict observability vary across PostgreSQL major versions. Before running repair/resync commands, check server_version, catalog definitions, and the exact documentation for your running version.

## 48. Summary: Fix the Root Cause, Preserve Data, Verify Progress

```text
Apply error
    |
    v
Identify transaction / LSN / relation
    |
    v
Classify root cause
    |
    +-- Duplicate key / missing row
    |
    +-- Constraint / replica identity
    |
    +-- Schema / publication mismatch
    |
    +-- Initial sync / permission / trigger
    |
    v
Choose controlled repair
    |
    +-- Repair subscriber data
    |
    +-- Align schema/configuration
    |
    +-- Resync table/subscription
    |
    +-- Skip whole transaction only with explicit repair plan
    |
    v
Resume apply
    |
    v
Verify LSN progress + row data + business invariants
```

Key principles:

1. **Logical replication is a unidirectional stream under a publication contract.** It does not automatically resolve multi-master conflicts.
2. **Duplicate keys and missing rows usually reflect data drift.** Compare both sides before editing.
3. **Replica identity determines how rows are located for UPDATE/DELETE.** Tables require an appropriate identity.
4. **DDL does not replicate automatically.** Schema migrations must be coordinated between publisher and subscriber.
5. **Subscriber-local writes are a major conflict source.** Enforce clear permissions and ownership.
6. **Apply worker errors normally halt at the failing transaction.** Restarting does not fix the root cause.
7. **Initial table sync has its own workers and states.** Check relation sync states during initial data copy.
8. **Transaction skip drops the entire transaction.** Use only when all changes are understood and a data compensation plan exists.
9. **Resyncs require snapshot/WAL consistency.** Never TRUNCATE or copy tables arbitrarily.
10. **Replication origin progress does not prove data equality.** Row/key/checksum/business validation is required.
11. **Archive/slot retention still matters when a subscription stops.** Monitor WAL capacity on the publisher.
12. **An incident closes only when apply advances and data is reconciled.** Keep logs, LSNs, before/after evidence, and corrective actions.

**One sentence to remember:** *When logical replication hits a conflict, find the transaction and why the subscriber cannot apply it; repair data/schemas per the source of truth, skip only when losses are fully understood, and verify both stream progress and data correctness.*
