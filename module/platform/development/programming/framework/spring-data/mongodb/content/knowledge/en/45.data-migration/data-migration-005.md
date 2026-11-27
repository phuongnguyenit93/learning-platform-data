# Designing Versioned Migrations with Tools or Standalone Tasks

In a **Spring Data MongoDB** application, data structure changes do not necessarily come with an `ALTER TABLE` statement as in relational databases. Old and new documents can coexist in the same collection, while Java entities, repositories, `MongoTemplate`, aggregations, and indexes may have already moved to the new read model. As a result, an application release can start up successfully yet still mishandle historical data.

**Versioned migration** is a set of transformation steps with clear identities, ordering, execution history, and verification criteria. You can use a dedicated tool such as **Mongock** or run a **standalone task** (Spring Boot CLI, Kubernetes Job, deployment pipeline, etc.). The goal is to know *which steps ran, in which environment, with which source code, and with what outcome*, and to recover safely if interrupted.

## 1. Why Shouldn't Data Transformations Be Placed Arbitrarily Inside the App?

Suppose the `customers` collection currently holds:

~~~json
{
  "_id": "CUS-1001",
  "name": "Nguyễn Minh An",
  "status": "ACTIVE"
}
~~~

The new application version wants to use `displayName` instead of `name`. If you only rename the property in `@Document` and deploy, older documents will lack a `displayName` value. If you also call an uncontrolled `updateMany` during application startup, you risk running concurrently across multiple instances, corrupting data, overloading MongoDB, or marking the application ready before the conversion completes.

A well-managed migration must be:

- **Traceable:** each step has an ID/version, purpose description, author, timestamp, result, and content verification digest (*checksum*).
- **Ordered and dependency-aware:** never run a step that drops an old field before all consumers can read the new field.
- **Safe to re-run:** restarting after failure does not duplicate data, overwrite newer data, or trigger unintended side effects.
- **Protected from unintended concurrency:** multiple pods/workers do not race to transform the same dataset.
- **Observable and verifiable:** tracks total records to process, processed count, remaining errors, latency, and system impact.
- **Planned for rollout and recovery:** defines safe stopping points, cross-version compatibility, and handling after partial conversion.

## 2. Distinguishing Migration Version, Application Version, and Document Version

Three types of versions serve three distinct needs:

| Type | Example | Purpose |
| --- | --- | --- |
| Application version | `orders-service 2.8.0` | Identifies the running code version |
| Migration version | `V005__backfill_customer_display_name` | Identifies which *data transformation step* has executed |
| Document schema version (design-dependent) | `schemaVersion: 2` inside each document | Lets read/write logic distinguish coexisting document shapes |

An application can release many times without needing a new migration. A migration can also run before deploying a new application version. Do not substitute `schemaVersion` inside individual documents for system-wide **migration history**: the two coincide only when the architecture intentionally designs them to.

### Naming Conventions

Migration source code can be organized sequentially:

~~~text
migrations/
  V001__create_customer_indexes
  V002__introduce_display_name
  V003__backfill_display_name
  V004__verify_display_name
  V005__remove_legacy_name     # run only after the compatibility phase
~~~

These names are **illustrative conventions**. A tool may use sequence numbers and its own annotations; a standalone task may use configuration files or a registry of classes. What matters is a stable ID, deterministic ordering, meaningful naming, and never reusing an ID for a different purpose.

**Immutability principle:** Once `V003` has executed in an environment, never silently edit its body while keeping the same ID. The system must validate checksums to detect divergence, or introduce a new migration `V006` to fix data. If an emergency fix is forced by a deployment failure, follow an explicit governance and reconciliation process.

## 3. Two Organizational Approaches: Migration Tool vs. Standalone Task

| Approach | Characteristics | Consider when |
| --- | --- | --- |
| Dedicated tool (e.g., Mongock) | Manages change units, execution history, and locking according to tool features/version; integrates with Java/Spring | Many small migrations; need standardized management across environments |
| Spring Boot CLI / standalone job | Full control over sequencing, checkpoints, batching, run conditions, and metrics; uses `MongoTemplate` or driver | Large datasets; must run outside the web app lifecycle; need custom rate limiting and monitoring |
| Running a migration tool **inside** a standalone job | Leverages the tool's history/locking while controlling execution at deploy time | Want both a unified execution contract and explicit control over when it runs |

### With Tools Like Mongock

Each change unit typically has an identifier, ordering, execution body, and optional rollback/recovery declarations depending on the chosen API version. When used with Spring Data MongoDB, transformation code should share evaluated connection settings, converters, and transaction policies; check documentation for your exact tool version to configure scanners, drivers, and locks.

Do not assume a tool automatically makes **every data change atomic**, that rollback is always possible, or that a lock keeps a task safe once its lease expires. Those guarantees still depend on MongoDB, transactions, runtime duration, retry policies, and migration logic.

### With a Standalone Task

A job can accept explicit parameters:

~~~text
java -jar migration-runner.jar \
  --spring.profiles.active=production \
  --migration.to-version=V003 \
  --migration.batch-size=500 \
  --migration.dry-run=false
~~~

This is an **illustrative CLI interface** for a custom-built runner; `migration.*` options only work if your application defines and handles them. Do not assume Spring Boot or MongoDB provides these flags out of the box.

In a pipeline, run the job with proper permissions and resource limits, wait for verified completion, inspect the data, and then proceed to the next deployment stage. Avoid letting every web instance execute long-running migrations via `CommandLineRunner` or `@PostConstruct` without explicit coordination.

## 4. Online Data Change Workflow: Expand → Migrate → Contract

To rename `customers.name` to `customers.displayName` while keeping the system live, break the change into compatible phases:

~~~mermaid
flowchart LR
    A[Release A: reads both fields] --> B[Migration: copy and validate legacy data]
    B --> C[Release B: prefer the new field]
    C --> D[Observe and confirm no legacy consumers remain]
    D --> E[Later migration: drop legacy field]
~~~

1. **Expand:** deploy code that reads `displayName` and falls back to `name`. If older instances still write `name`, design compatible writing such as temporary *dual-write* or defer conversion until all writers understand the new schema.
2. **Backfill:** copy `name` to `displayName` for records lacking the new field. Populate only missing values and define how to resolve records where both fields exist with different values.
3. **Verify:** count unconverted records, find conflicts, inspect sample data across groups, and validate the new application against real data.
4. **Switch:** move readers and writers to `displayName`, monitor errors, and verify no legacy-schema write flows remain.
5. **Contract:** in a later release, drop the old `name` field and obsolete indexes/logic; do so only when certain no dependent consumers remain.

Never combine "copy field" and "drop old field" into a single migration while application versions are rolling out. If old writers remain active, new records created after the backfill runs can lack `displayName`; you need compatible writes, catch-up migrations, or a controlled write freeze.

## 5. Example of an Idempotent Migration with `MongoTemplate`

The example below illustrates **the data transformation portion of a migration step**, using `MongoTemplate` to access the `customers` collection and a MongoDB **update pipeline** to copy the field. Pipeline updates are supported since MongoDB 4.2. The code updates only documents that have `name` but lack `displayName`, keeping `name` intact during the compatibility phase.

~~~java
import java.util.List;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class V003BackfillCustomerDisplayName {
    private final MongoTemplate mongoTemplate;

    public V003BackfillCustomerDisplayName(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long execute() {
        return mongoTemplate.execute("customers", collection -> {
            Bson missingNewField = Filters.and(
                Filters.exists("name", true),
                Filters.exists("displayName", false)
            );

            // "$name" in an update pipeline references the legacy field value.
            List<Bson> pipeline = List.of(
                new Document("$set", new Document("displayName", "$name"))
            );

            UpdateResult result = collection.updateMany(missingNewField, pipeline);
            return result.getModifiedCount();
        });
    }
}
~~~

Notable details:

- Filtering on `displayName` **not existing** ensures re-runs skip already-converted documents and avoids overwriting newer user values. Each single-document update still follows MongoDB's document-level atomicity.
- In an update pipeline, `"$name"` is an expression reading the `name` field; if used in a standard `$set` update, literal `"$name"` will not behave as intended.
- `updateMany` can update **multiple documents**, but the entire operation does not become a single atomic transaction across all documents. This example fits medium-scale data; do not run it unbounded on a massive collection during peak hours.
- `modifiedCount` aids observability, **not** as a substitute for post-condition checks. A document containing both fields with mismatched values will not be repaired by this task automatically.

After backfilling, check for remaining documents missing the field:

~~~javascript
db.customers.countDocuments({
  name: { $exists: true },
  displayName: { $exists: false }
});
~~~

Check for records having both fields with differing values (if business rules require them to match during this phase):

~~~javascript
db.customers.countDocuments({
  name: { $exists: true },
  displayName: { $exists: true },
  $expr: { $ne: ["$name", "$displayName"] }
});
~~~

If this migration runs concurrently with user writes, checks must be evaluated alongside dual-write logic or a controlled write pause. A count of 0 at one point in time **does not guarantee** older writers won't insert unconverted documents afterward.

### For Very Large Datasets

Replace one large `updateMany` with bounded batches, usually iterating by `_id` or a stable key and saving a **checkpoint**. For instance, fetch up to 500 `_id`s per batch, update missing records, confirm successful writes, and only then record the last scanned key. Watch for documents inserted or modified during traversal: an `_id` checkpoint does not automatically catch new records whose keys fall before the scanned cursor. Therefore, you need writer synchronization, catch-up scans, or a bounded input dataset.

Avoid increasing `skip` offsets on changing datasets: large offsets are costly and easily skip records. Configure batch limits, write throttling, backoff retries, timeouts, and monitor replication lag, query latency, and index size. For huge datasets, favor small-batch backfills over a single transaction spanning millions of documents.

## 6. Migration Runners Must Manage History and Execution Locks

Simply "putting a version number in the name" is not enough. The runner needs a dedicated history store, such as a `migration_history` collection:

~~~json
{
  "_id": "V003__backfill_customer_display_name",
  "version": 3,
  "checksum": "sha256:<digest-of-immutable-migration-definition>",
  "status": "APPLIED",
  "startedAt": "2026-11-20T02:00:00Z",
  "finishedAt": "2026-11-20T02:03:11Z",
  "runnerVersion": "1.4.0",
  "modifiedCount": 73420
}
~~~

This is an **illustrative contract**, not a fixed schema mandated by MongoDB or Mongock. In production, store timestamps as BSON Date, enforce unique IDs (`_id` is inherently unique), and persist error codes and checkpoint details in appropriate locations.

### Recommended Execution Flow

~~~mermaid
flowchart TD
    A[Start job] --> B[Acquire execution lock]
    B --> C[Read migration history]
    C --> D{Already APPLIED?}
    D -->|Yes, checksum matches| E[Skip this step]
    D -->|Yes, checksum differs| F[Stop for investigation]
    D -->|No| G[Check preconditions]
    G --> H[Run resumable migration]
    H --> I[Check postconditions]
    I --> J{Passed?}
    J -->|Yes| K[Record APPLIED and checkpoint]
    J -->|No| L[Record failure and keep pending state]
    E --> M[Release lock]
    F --> M
    K --> M
    L --> M
~~~

The workflow must exit with an error code if acquiring the lock fails, checksums mismatch, preconditions fail, or final verification fails. Deployment pipelines must **halt** rather than proceeding as if the migration succeeded.

### Locks, Checkpoints, and Mid-Run Failures

- **One execution at a time:** use a tool-provided lock or build a lock document with atomic conditional updates, owner identity, lease expiration, and renewal. Account for workers still running after lease expiration; use a *fencing* mechanism or ensure stale workers cannot keep writing. A TTL/lease alone without fencing stale workers is insufficient.
- **Status and checksums:** `APPLIED` + matching checksum skips execution. `APPLIED` + mismatched checksum halts for inspection. Leftover `FAILED`/`RUNNING` states must be reconciled and recovered per migration rules; never blindly reset them to unrun.
- **Checkpoint ordering:** record progress only after the corresponding batch is written and verified. If the task stops after writing data but before updating the checkpoint, re-running may revisit that batch—which is why operations must be idempotent.
- **Interrupted runs:** `updateMany`, `bulkWrite`, or a batch sequence may have partially modified data. Store processed counts, errors, last key, and a way to resume from completed progress.
- **Do not overuse transactions:** MongoDB supports multi-document transactions on compatible replica sets/sharded clusters, but large, long-running transactions consume resources, hold locks, and risk timeouts. Use transactions only for short units of work that genuinely require multi-document atomicity; configure `MongoTransactionManager` when using `@Transactional` with Spring Data MongoDB and ensure code participates properly in the transaction.

If a migration must create indexes, update validators, or alter collections, evaluate administrative operations separately for your MongoDB version. Do not assume DDL operations and all backfill stages can be bundled inside one transaction. Index-related migrations must consider index build load and active queries.

## 7. Designing Execution Gates in the Deployment Pipeline

A release plan typically splits responsibilities across the **application**, **migration job**, and **verification**:

| Step | Actor/System | Gate criteria |
| --- | --- | --- |
| 1. Backup and scope | Pipeline + ops | Restorable backup verified; in-scope record count measured |
| 2. Deploy compatible code | Deployment system | Readers and writers accept both old and new schemas by design |
| 3. Dry run (read-only) | Migration job | Identifies record count, conflicts, estimated duration; zero writes |
| 4. Run backfill | Standalone job or tool | Valid lock; batches and retries monitored; full logs |
| 5. Verify postconditions | Job + integration tests | Zero unconverted records, discrepancies within limits, app healthy |
| 6. Switch traffic/reads | New application | No legacy writers/consumers remain; metrics stable |
| 7. Cleanup in later release | Contract migration | All components off legacy schema; recovery plan in place |

Let the pipeline decide whether to proceed based on job **exit codes**, verification checks, and monitoring metrics. Avoid passing credentials directly on the command line or leaking secrets in logs; use a secret manager and least-privilege accounts scoped to each migration.

### Logging and Metrics

For each step, logs should include `migrationId`, `checksum`, `executionId`, collection, expected total, inspected count, modified count, error count, checkpoint, duration, and status. Never log raw documents containing personal information. For throughput analysis, track documents/second, batch latency, CPU/I/O load, connections, slow queries, and replication lag.

In particular, **modified record count** does not equal **correct record count after migration**. Verify postconditions with independent queries and check sample records or business invariants as needed.

## 8. Testing Migrations Before Production

Test against real MongoDB (e.g., a Testcontainers environment configured as a replica set if transactions are needed), using datasets covering both old and new cases as well as anonymized copies of tricky edge cases.

| Scenario | Expectation |
| --- | --- |
| Fresh database, no prior migrations | Steps run in order and record `APPLIED` history |
| Re-running exact same code | No unintended data changes; already-applied steps are skipped |
| Existing ID with modified migration code | Runner detects checksum mismatch and halts |
| Document with only `name` | `displayName` copied; `name` preserved during expand phase |
| Document already having `displayName` | New value is not overwritten by backfill |
| Both fields exist with differing values | Conflict reported; resolved per approved business rules |
| Mid-run stop and restart | Resumes from checkpoint or safely re-runs; nothing missed |
| Two workers racing on same migration | Only valid worker writes; worker losing lease stops writing |
| Legacy writer active during backfill | Compatibility strategy or catch-up scan prevents missed new records |
| Large dataset, replica lag | Batch limits and alerts engage; no degradation beyond thresholds |

Also verify the **contract** phase in realistic lifecycle tests: after dropping `name`, no classes, queries, aggregation pipelines, indexes, reports, ETL jobs, or consumers still read that field. When using `@Field` or custom converters in Spring Data MongoDB, verify mapping between Java property names and physical field names so migrations do not target the wrong field.

## 9. Common Pitfalls and How to Avoid Them

**Editing an already-released migration:** keeping the same version while changing code causes environments to diverge in history. The fix is creating a new migration step and enforcing checksum checks.

**Running on every pod's startup:** multiple instances starting concurrently cause contention and prolong readiness checks. The fix is a single coordinated job or a locked tool with explicit lease handling.

**Dropping fields immediately during backfill:** breaks older running versions and complicates rollbacks. The fix is multi-release expand–backfill–contract.

**Marking `APPLIED` before verification:** the system records success while data is only partially converted. The fix is batch checkpointing and finalizing history only after postcondition checks pass.

**Assuming transactions solve everything:** a massive transaction is not the default way to backfill millions of documents. The fix is idempotent batches, checkpoints, and invariant-based verification.

**Having no recovery plan:** many lossy transformations cannot be reversed simply by running an inverse script. The fix is tested backup/restore, retaining legacy fields during transition, or designing compensating steps while accounting for newly created data.

## 10. Choosing a Strategy for Spring Data MongoDB Systems

If the number of steps is small, runtime is short, and governance needs are straightforward, a tool like Mongock standardizes identification, ordering, history, and locking according to your version's capabilities. If migrations must process millions of documents, throttle load, checkpoint across hours, or run on an independent deployment schedule, prefer a **dedicated runner/job** with equivalent history, locking, and reconciliation mechanisms. You can combine both by invoking the migration tool from a deployment job.

In either approach, **Spring Data MongoDB provides the APIs to access and update data; migration rules govern when, in what order, under which locks, and under what verification criteria a step is considered complete**. A step is only finished once data is verified, `APPLIED` state is reliably recorded, and the system remains compatible with all related application versions.
