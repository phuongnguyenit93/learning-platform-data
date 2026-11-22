# Rolling Back the JDK or Application When Data and Dependencies Have Changed

## 1. Why Is Rollback After a Java Migration Not Simply Swapping Back the Image?

A **Java Advance Compatibility Migration** effort can include many simultaneous changes: JDK 17 to JDK 21, major version upgrades to frameworks and ORMs, new dependencies, new message formats, new database schemas, new data encryption methods, and new container configurations. Initially everything works, yet after release a regression surfaces: p99 spikes, transactions misbehave, a native library crashes, or old consumers fail to read data.

The natural reaction is **rolling back to the previous JDK or application version**. However, deploying back to the old artifact does not mean data already written by the new artifact remains readable, does not mean old dependencies still exist, and does not guarantee external systems (databases, brokers, caches, search indexes, object storage) return to a compatible state.

Example:

~~~text
Before migration:
  App A + JDK 17 + old ORM + Schema S1

New deployment:
  App B + JDK 21 + new ORM + Schema S2

While App B is running:
  - Write new column, drop old column
  - Emit event schema v2
  - Write session or cache in new format
  - Change sequence/ID and transaction statuses

Error detected → redeploy App A + JDK 17
  - Can App A read Schema S2?
  - Can App A read data written by B?
  - Can old consumers read event v2?
  - Do old config/dependencies still run on current infrastructure?
~~~

Key takeaway: **a successful rollback means restoring the ability to serve according to the business contract, not merely bringing an old process back to the Running state**.

This lesson belongs to the **Release and Operations** chapter, focusing on rollback when the Java runtime, application artifacts, dependencies, and data have all changed.

After this lesson, the reader will be able to:

1. Distinguish among JDK, application, configuration, schema, and data rollbacks.
2. Determine when in-place rollback is safe versus when a forward fix or controlled recovery is required.
3. Design bidirectionally compatible database migrations across a release window.
4. Analyze compatibility across ORM, frameworks, serialization, message schemas, cache/sessions, and security.
5. Build a rollback plan grounded in RTO, RPO, backup/PITR, and business integrity.
6. Organize canary/blue-green/rolling deployments alongside compatibility gates.
7. Write runbooks and rehearse in staging before production migration.
8. Measure and prove rollback using real functional, data, and operational metrics.

## 2. Distinguishing Five Types of Rollback

| Type | What changes? | What is not automatically restored |
|---|---|---|
| **JDK rollback** | JVM/JDK runtime back to previous version. | New source/binary, DB schema, events, dependencies, and config may remain new. |
| **Application rollback** | Container image/JAR/WAR and application config back to previous release. | Database and out-of-process state do not automatically revert. |
| **Configuration rollback** | JVM flags, feature flags, endpoints, certificates, or deployment manifests. | Code and already-written data may remain changed. |
| **Schema rollback** | DDL/database schema back to previous form. | Transformed data may be lost or non-reversible. |
| **Data recovery/restore** | Restore data to a snapshot/backup or recover via logs. | Transactions occurring after the recovery point, side effects, and state in other systems. |

A release may require coordinating several types. For example, rolling back the container image and application config while **keeping the expanded schema intact** to avoid losing new data. Or keeping the current image and only disabling the offending feature flag. In cases of data destruction, evaluate restore, reconciliation, or forward fix before acting.

### 2.1. Rollback Is Not Always the Best Option

Three primary strategies:

- **Rollback:** re-run the old version when it remains compatible with the new state.
- **Forward fix:** release a fix compatible with the current state rather than trying to turn data back into the past.
- **Recovery/restore:** restore data from backup/PITR and reprocess required events; this can be a disruptive operation requiring its own plan.

If the new version altered data in an irreversible way, running the old app can cause more severe errors. In such cases, a forward fix or read-only mode to protect data may be safer.

### 2.2. Minimum Conditions for In-Place Rollback

Rolling back to App A/old JDK should only be considered valid once verified:

1. Artifact A still starts up on the target runtime/infrastructure.
2. A's dependencies, agents, native libraries, and TLS/security policies remain compatible.
3. A can read the schema and data written by B.
4. A writes new data without breaking the contract of any components still running B.
5. A can read/process existing messages/caches/sessions or has an isolation mechanism.
6. No new irrecoverable side effects cause A to misbehave.
7. The runbook has rehearsal evidence and authorized decision-makers.

Missing any critical condition must transition the status to **ROLLBACK BLOCKED / alternative plan needed**, rather than "try it first and see".

## 3. State Is What Makes Rollback Hard

In a stateless service, swapping binaries can be relatively simple. However, enterprise applications are rarely truly stateless even if containers can be replaced at any time.

State can reside in:

~~~text
                       Application release
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
      Database              Message bus          Shared cache
          │                    │                    │
          ▼                    ▼                    ▼
   Schema + rows         Events + offsets       Keys + serialized
   + procedures          + consumers            values + sessions
          │                    │                    │
          ├────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   Object storage        Search indexes       External systems
   + file formats        + mappings            payment/email/API
~~~

Even when the old JAR runs on the old JDK, part of the state may already be in the format or semantics of the new version.

### 3.1. Technical State and Business State

**Technical state**: cache entries, sessions, serialization metadata, search index mappings, job checkpoints, and broker offsets.

**Business state**: orders, payments, inventory, balances, change history, contract statuses, and accounting documents.

Caches can be flushed in a controlled manner if losing cache efficiency is acceptable; however, committed transactions or an externally executed payment cannot be erased just because you want to return to an old release.

### 3.2. Rolling Back Binaries Does Not Roll Back Committed Transactions

For example, App B creates Order #501 and charges via a payment gateway. If the DB is restored to before the order was created, the payment gateway may still have captured the charge.

~~~text
T0: DB backup
T1: App B creates Order #501
T2: Payment provider charge succeeds
T3: Bug detected, restore DB to T0

DB: Order #501 is gone
Payment provider: transaction at T2 still exists
~~~

Therefore, data recovery may require **reconciliation**, compensating transactions, ledger matching, and audit trails—not running a single SQL DOWN script.

## 4. Compatibility Matrix Before Release

Given two versions App A (old), App B (new), and schemas S1/S2, evaluate these combinations:

| Combination | Purpose | Question to prove |
|---|---|---|
| A + S1 | Baseline | Is the old release serving properly? |
| B + S1 | Rolling start | Can B run before schema migration finishes? |
| A + S2 | Rollback | Does A continue reading/writing properly on the expanded schema? |
| B + S2 | Target | Does B run well after migration? |
| A/B coexisting on S2 | Mixed-version window | Do both apps write data without conflicting? |

In **expand-contract**, the A + S2 condition is usually the key to rollback. If schema S2 drops a column required by A, a code rollback to A may no longer be safe.

### 4.1. The Matrix Must Include JDK, Dependencies, and State

The real-world model spans multiple axes:

~~~text
Java runtime:    JDK 17 / JDK 21
Application:     App A / App B
Schema:          S1 / S2
Data format:     V1 / V2
Events:          E1 / E2
Dependencies:    D1 / D2
Environment:     image, OS, agent, config
~~~

It is not necessary to test every Cartesian product if the cost is prohibitive; test the combinations that will exist during rollout and rollback, especially **A reading state created by B**.

### 4.2. Distinguish Reading From Writing

Read compatibility is not enough. For example, App A can read a new column, yet when updating a record it might write null into an unknown field, wiping out data created by B.

For each data type, ask:

- Can A read records created by B?
- Can A update records without wiping out new metadata?
- Can B read records created by A?
- Do concurrent writes by A and B to the same record violate invariants?
- Which external consumers process which events/schemas?

A **write compatibility test** is worth far more than merely testing a single SELECT row.

## 5. Migration Lifecycle: Expand → Migrate → Contract

A common database strategy to keep the rollback window open is **expand-contract**.

~~~text
S1 + App A
   │
   ▼
EXPAND: add new structure, keep old structure
   │
   ▼
S2-compatible + App A keeps running
   │
   ▼
App B gradually shifts reads/writes to new model
   │
   ▼
BACKFILL / VERIFY / CUTOVER
   │
   ▼
Observe for full rollback window
   │
   ▼
CONTRACT: drop old part only when no consumers remain
~~~

**Expand:** add compatible columns/tables/indexes/formats without immediately removing what the old version depends on.

**Migrate:** backfill data, perform dual-read/dual-write or controlled writer cutover; monitor status and correctness.

**Contract:** remove the old schema/API/format once all consumers have migrated and rollback to A is no longer supported.

### 5.1. Compatibility Window

For a period of time, the schema should serve both App A and App B:

~~~text
T0   S1 + A
T1   Expand S2
T2   Deploy B canary, A and B coexist
T3   Full B, keep old schema
T4   Rollback window ended / conditions met
T5   Contract: drop old columns/tables
~~~

After T5, rolling back to A may no longer be supported. This must be documented in the release plan as a **rollback boundary**, not merely a comment in a pull request.

### 5.2. Do Not Cram Everything Into a Single Deploy

A release can consist of at least three independent changes:

1. Database expand migration.
2. Application cutover and backfill.
3. Database contract cleanup.

Splitting the rollout increases the chance of stopping at the right point and rolling back the app without needing a DB restore. However, it also requires managing migration state and compatibility during the transition period.

## 6. Example: Safely Renaming Column `name` to `display_name`

Suppose the old version uses this table:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
~~~

The new version aims to use `display_name`. A dangerous migration:

~~~sql
ALTER TABLE customer RENAME COLUMN name TO display_name;
~~~

If App A still queries `customer.name`, it will fail immediately after migration. In-place column renaming is unsuitable if rolling deployments and rollback must support A.

### 6.1. Expand Step: Add the New Column

Conceptual SQL example:

~~~sql
ALTER TABLE customer
    ADD COLUMN display_name VARCHAR(120);
~~~

The old version continues reading/writing `name`. The new version can be designed to read `display_name` when present, falling back to `name` otherwise.

This is a data-model example; syntax, lock behavior, and online schema-change capability depend on the specific database engine/version.

### 6.2. Backfill Data

For a small table in a test environment:

~~~sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
~~~

On large production tables, a full-table UPDATE can cause long transactions, lock contention, replication lag, and transaction log pressure. Backfill in batches with idempotency, throttling, and progress monitoring; the SQL above illustrates logic only.

At the same time, handle **data changing during backfill**. If App A still writes `name` after a record was backfilled, `display_name` can become stale. Choose a well-designed synchronization mechanism rather than assuming a one-off backfill suffices.

### 6.3. Dual-Read

In version B:

~~~java
public final class CustomerNameSelector {
    public static String readName(String displayName, String legacyName) {
        return displayName != null ? displayName : legacyName;
    }
}
~~~

This snippet illustrates read precedence, not a full repository implementation. Determine whether null/empty string share the same semantics and how discrepancies between the two columns are resolved.

### 6.4. Dual-Write or Intentional Synchronization

During the rollback window, one option is for B to write **both `name` and `display_name`** with the same value in one transaction.

~~~text
Write customer name = "Linh"
        │
        ▼
Transaction:
  name         = "Linh"
  display_name = "Linh"
        │
        ▼
Commit
~~~

However, if App A still writes `name` while B prioritizes reading `display_name`, data can diverge. Handle **the old writer** using one of the evaluated strategies:

- Keep `name` as the source of truth during the mixed-version period.
- Use an appropriate DB trigger to synchronize within approved limits.
- Restrict one version to be the writer at a time while keeping the other read-only.
- Use event-driven replication with idempotency and reconciliation, accepting eventual consistency semantics where appropriate.

Do not enable naive dual-write across services without solving transaction boundaries, retries, ordering, and conflict resolution.

### 6.5. Contract Only After the Rollback Window Ends

Once all consumers use `display_name` and rollback to App A is no longer committed:

1. Verify all records have been backfilled.
2. Verify no writers to `name` remain.
3. Apply constraints to `display_name` appropriate to the data and engine.
4. Observe long enough to detect any remaining consumers of `name`.
5. Only then consider dropping the `name` column.

Dropping a column can cause data loss irreversible by simple schema operations. The contract decision needs to be a separate release milestone.

## 7. Database Migration Tools and Limits of DOWN Scripts

Tools like Flyway or Liquibase help version and run schema migrations in a controlled way. They assist in tracking schema versions, but **do not automatically guarantee business-correct data rollback**.

### 7.1. A Forward Migration Does Not Necessarily Have an Inverse Migration

Example:

~~~sql
-- Forward migration: merge two columns
UPDATE person
SET full_name = first_name || ' ' || last_name;
~~~

Once `first_name` and `last_name` are dropped, splitting `full_name` back into the exact two original columns is uncertain. People with multi-part names make splitting ambiguous.

This is a **lossy transformation**; a DOWN script that merely restores the old column names cannot recover the original information.

### 7.2. Version History Is Not a Backup

A migration history table stating "schema is currently at V42" does not fully store:

- Row values prior to changes.
- Committed transactions.
- Side effects outside the database.
- State in dependent systems.
- Published messages already processed by consumers.

Therefore, **migration history and backup/PITR solve two different problems**. Both are required when data risk is high.

### 7.3. DDL May Not Be Transactional

The ability to roll back DDL inside a transaction varies by database engine and operation type. A migration may auto-commit, hold locks, or be disallowed inside a transaction.

Before deploying, confirm:

- Does the engine/version support transactional DDL for the specific statement?
- Does the migration run in one transaction or multiple transactions?
- How do locks/replication lag impact production?
- If the job halts midway, what state are the schema/data left in?
- Is there an idempotent resume/repair plan?

Do not paste a DROP/ALTER statement straight to production just because it worked on a small test database.

## 8. Rollback When the JPA/ORM Provider Has Changed

Upgrading the JDK often comes with upgrading the framework or JPA provider, such as changing Hibernate generations, EclipseLink, or Jakarta Persistence integration.

Rollback issues may lie in:

- Mapping annotations and entity scanning.
- Identifier generation, sequence allocation, and identity columns.
- Timestamp, timezone, enum, and decimal mappings.
- JSON/UUID/custom SQL types.
- Lazy loading, dirty checking, cascade, and orphan removal.
- Schema generation/dialect and SQL semantics.
- Transaction propagation, flushing, and locking.
- Second-level cache and serialized cache entries.

An old entity class may compile/run yet **write data with wrong semantics** once the schema/provider has changed.

### 8.1. Example of Changing ID Generation

App A uses one sequence allocation strategy; App B switches to hi/lo or a different allocation size. If both run concurrently sharing the same sequence with incompatible configurations, collisions or unusual gaps can occur depending on setup.

Before a mixed-version rollout:

1. Finalize the ID/sequence generation strategy.
2. Verify concurrency between A and B.
3. Verify no duplicate primary keys are generated.
4. Monitor sequence state and rollback behavior.
5. Do not reset a sequence back to an old value once new IDs exist.

Do not call a sequence gap a data error if the ID model does not guarantee continuity; what matters is uniqueness and the business contract.

### 8.2. Jakarta Namespace Is a Binary Boundary

When moving from `javax.persistence` to `jakarta.persistence`, the two APIs have different binary names. Rolling back the framework/JPA provider may require swapping the **entire compatible bundle**, not just downgrading a single JAR version.

If App A relies on the `javax` generation of framework, Servlet container, and ORM, yet the deployment environment has completely switched to a Jakarta runtime, swapping back `app.jar` alone may fail to run even if the JDK remains compatible.

Maintain a **complete old image/artifact**, including the approved runtime/container/provider/config, instead of saving only a single JAR file.

### 8.3. ORM Cache

Second-level cache entries encoded under the new provider/config may not be understood by the old provider. If the cache is not the source of truth, assign a separate namespace/cache version per app release or invalidate in a controlled manner.

Do not wipe caches without considering traffic spikes to the database, cache warm-up, session semantics, and consistency of write-through/write-behind caches.

## 9. JDK Rollback and Bytecode Compatibility

Reverting the runtime from JDK 21 to JDK 17 requires the bytecode of the entire artifact and runtime dependencies to match Java 17.

Example class-file major versions:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

If App B was compiled to class major 65, it cannot run on Java 17 simply by changing the base image. A Java 17 JVM will refuse to load Java 21 classes.

### 9.1. Three Types of JDK Rollback

**Type 1 — App B still targets Java 17:**

~~~text
Compiler JDK 21 + javac --release 17
                │
                ▼
App B bytecode Java 17
                │
                ├── Runtime JDK 21
                └── Runtime JDK 17 (if dependencies/APIs compatible)
~~~

You can try rolling back the JVM before rolling back the application, **provided** all dependencies, agents, native components, and APIs support Java 17. `--release 17` does not downgrade the bytecode of external dependencies.

**Type 2 — App B requires Java 21:**

~~~text
App B bytecode major 65 + Java 21 dependency
                │
                ▼
Cannot simply replace JDK 21 with JDK 17
~~~

You must roll back **both the application and dependencies** to a Java 17-compatible bundle, or release a version B' targeting Java 17 if engineering and contracts permit.

**Type 3 — The new version changed data formats:**

Even when rolling back the entire app to A + JDK 17, A still might not be able to read data written by B. Here the problem lies in state, requiring a compatibility bridge, forward fix, or recovery plan.

### 9.2. Direct and Transitive Dependencies

JDK rollback requires checking:

- Maven/Gradle resolved `runtimeClasspath`.
- Bytecode target of every loaded JAR.
- Java SE APIs used by dependencies.
- JNI/JNA/native libraries by OS/architecture/libc.
- Java agent/JVMTI and instrumentation bytecode versions.
- TLS/crypto providers and security configuration.
- Servlet/Jakarta EE application server compatibility.
- Startup flags added or removed on the older JDK.

Class major 61 does not guarantee full compatibility with an older runtime if code depends on a native library, reflective API, or mismatched classpath dependency.

### 9.3. Do Not Confuse the Java Toolchain With the Production Runtime

The Gradle daemon might run JDK 21, the compiler use JDK 21 with `options.release 17`, yet the production Docker image might run JDK 21 while the rollback image runs JDK 17.

Always inspect the JDK in the **production process**, rather than concluding from a developer's `JAVA_HOME` or `./gradlew --version` on CI.

## 10. Runtime Flags and Environment Can Also Block Rollback

Reverting to an older JDK while keeping the newer JDK's startup flags can prevent the process from starting:

~~~text
Unrecognized VM option
Could not create the Java Virtual Machine
~~~

Examples:

- A GC/JFR/module-access flag does not exist in the older JDK.
- `--add-opens`/`--add-exports` or module names differ.
- A new Java agent requires a newer JVMTI/JDK.
- The older JDK does not handle cgroups v2 the same way as the newer JDK.
- TLS defaults, truststores, or crypto providers differ.
- Native libraries were built against a newer OS/architecture.

Rollback artifacts should be accompanied by a **versioned old runtime profile**:

~~~text
Release bundle:
  application image digest
  JDK image/build
  JVM flags and env/config references
  agents and native dependency versions
  compatible schema/data/event versions
  deployment manifest revision
~~~

Do not use a fixed immutable flag set across all JDK versions without testing. In particular, avoid "ignore unrecognized VM options" to silently skip critical settings.

## 11. Serialization and Data Format Changes

A serializer change can cause an application rollback to fail even if the database schema did not change.

Common areas:

- Java Object Serialization.
- JSON field names, enum string values, null handling.
- XML/JAXB bindings and schema namespaces.
- Protobuf/Avro schema evolution.
- Kafka/event payloads.
- Cache/session serialization.
- File objects in S3-compatible object storage.
- Database JSON/JSONB columns.

### 11.1. Java Object Serialization

Java serialization involves compatibility factors such as class name, `serialVersionUID`, serializable fields, and class evolution rules. If B alters `serialVersionUID` or changes the class hierarchy incompatibly, A may fail to deserialize objects written by B.

Even if A manages to deserialize the object, **semantics** can still be wrong because B introduced new state that A ignores.

Storing native Java serialization as a long-term interchange format between independent services is discouraged without a specific reason; during migration, versioning and compatibility tests are required if the system depends on it.

### 11.2. JSON: Tolerant Reader Is Not Enough

Example event v1:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "o-142",
  "amount": "125.50"
}
~~~

Event v2:

~~~json
{
  "eventType": "OrderCreated",
  "orderId": "o-142",
  "amount": {
    "value": "125.50",
    "currency": "VND"
  },
  "schemaVersion": 2
}
~~~

If App A expects `amount` to be a string, it can fail when reading events produced by B. Adding `schemaVersion` does not automatically teach A the new structure.

A safe approach:

1. Keep event v1 during the compatibility window.
2. Add optional fields with clear semantics or emit a separate event type/version.
3. Upgrade consumers to read both v1 and v2 **before** producers switch to v2.
4. Drop v1 only when no old consumers remain and the rollback policy has changed.

### 11.3. Protobuf/Avro and Schema Evolution

These serializers have specific evolution rules that do not guarantee every change is backward/forward compatible. For example, in Protobuf, preserve field numbers, avoid reusing deleted fields, and obey field type/presence semantics.

With Avro/schema registry, distinguish backward/forward/full compatibility modes and how writer/reader schemas are resolved.

For rollback, **an old consumer reading new writer data** is a direct condition that must be tested. Knowing only that "a new reader reads old data" does not prove rollback is safe.

## 12. Messaging: An Emitted Event Cannot Simply Be Recalled

Once B publishes event E2, the message may already have been:

- Written to Kafka/logs or a durable queue.
- Processed by a consumer with committed offsets.
- Forwarded to other systems.
- Used to trigger emails, payments, notifications, or index updates.

Rolling the producer back to A neither deletes those events nor restores consumers that already processed them.

### 12.1. Cases to Verify

| Scenario | Rollback question |
|---|---|
| A consumer encounters event E2 | Can it deserialize/process correctly? |
| A producer continues emitting E1 | Do B consumers still support E1 during the mixed window? |
| B already committed offsets | Will A in the same consumer group skip or re-read anything? |
| B triggered external side effects | Can they be compensated and reconciled? |
| B changed partition key | Did ordering for the business entity change? |
| B changed idempotency key | Will retries/rollback cause duplicate processing? |

### 12.2. Do Not Reset Offsets Arbitrarily

Moving Kafka consumer offsets back into the past can cause messages to be reprocessed, leading to duplicate charges, duplicate emails, or double writes if handlers are not idempotent.

A rollback plan must specify:

- Which consumers own which offsets/checkpoints.
- How replay works, if any.
- Idempotency keys and deduplication windows.
- Quarantine/dead-letter policies.
- Reconciliation for already-executed side effects.

Never blindly reset production offsets as a way to "go back to before release" without analyzing business semantics.

### 12.3. Outbox and Transaction Boundaries

Transactional outbox coordinates database writes with event publishing in certain architectures, yet rollback still requires ensuring outbox schema/payload version and consumer compatibility.

If a new release alters the outbox structure in a way A cannot read, publisher rollback will be blocked. Maintain compatible payload readers or separate versioned outbox consumers per plan.

## 13. Cache and Session Rollback

Cache/session is a form of state easily overlooked because it can be lost on restart, yet in distributed systems it typically lives outside the application process.

### 13.1. Cache Keys and Value Formats

App B might switch from:

~~~text
cache key: customer:42
value: JSON v1
~~~

to:

~~~text
cache key: customer:v2:42
value: binary schema v2
~~~

If A rolls back and reads `customer:42` while B wrote a different format to the same key, A may deserialize incorrectly. A helpful solution is **version namespacing** for cache keys with defined TTL/invalidation:

- A uses namespace v1.
- B uses namespace v2.
- Neither overwrites the other.
- Account for cache warm-up cost and database load on rollback.

Do not flush all caches in production without calculating load spikes, consistency semantics, and effects on sessions/authentication.

### 13.2. Session Serialization

With sticky sessions or shared session stores, App B may alter the session object structure. During an A/B rollout, users may switch between versions and get logged out or hit errors.

Options:

- Use a backward-compatible session schema during the compatibility window.
- Use temporary session affinity with clear limits.
- Version/namespace sessions; accept user re-authentication if policy allows.
- Move session state to a more stable format if the system requires long-running rolling upgrades.

For authentication/security state, do not arbitrarily flush sessions if doing so impacts user obligations or compliance. User-facing policy and security review are required.

## 14. Database Restore, Snapshots, and Point-in-Time Recovery (PITR)

If data has been corrupted or a migration has no valid inverse, the team may consider restoring from backup or PITR.

**Snapshot/backup:** a copy of state at a point in time or per a specific storage mechanism.

**PITR:** the ability to recover a database to a point in time/log position as supported by the engine, typically relying on backups plus write-ahead logs or a similar mechanism.

### 14.1. Two Operational Objectives

| Concept | Meaning |
|---|---|
| **RPO — Recovery Point Objective** | Maximum acceptable data loss, measured in time or defined state. |
| **RTO — Recovery Time Objective** | Maximum acceptable time to restore service per contract. |

Example:

~~~text
Target RPO: 5 minutes
Target RTO: 30 minutes
~~~

You cannot conclude the system meets these targets simply because backups exist. Perform **actual restore rehearsals**, measure timings, and verify data/integrity.

### 14.2. PITR Is Not Selective Transaction Undo

Restoring a database to T0 can wipe out **all transactions** that occurred after T0, not just those affected by App B. It can erase valid transactions from other users or services.

Therefore, before choosing PITR:

1. Identify the affected database/schema/tenant scope.
2. Estimate how many valid transactions would be lost.
3. Identify external side effects emitted outside the DB.
4. Evaluate safe replay/reconciliation methods.
5. Consider restoring to an isolated instance to compare/extract if appropriate.
6. Obtain approval from data/business owners commensurate with risk.

In many cases, **restoring to an isolated environment and selectively repairing data** is safer than rolling the entire production DB back in time; the choice depends on the type of corruption and consistency guarantees.

### 14.3. Backups Must Be Verified

A valid backup requires:

- Clear timestamp, retention, and data scope.
- Integrity verification.
- Inclusion or proper coordination of schemas, transaction logs, and encryption keys.
- Access permissions available during an incident.
- An engine/version-specific restore plan.
- Rehearsal in a recovery environment.
- Evidence of actual RTO/RPO timings.

**A backup that has never been test-restored must not be treated as a reliable rollback plan.**

## 15. Rollback When the Database Engine or Driver Has Changed

A Java migration may upgrade the JDBC driver or change the database engine/version.

Common risks:

- Old JDBC driver does not support the new database server.
- Default TLS authentication protocols/ciphers differ.
- SQL dialect or reserved keywords changed.
- Timestamp, timezone, JSON/UUID/LOB semantics differ.
- Index/query planner and performance differ.
- Stored procedures, extensions, and functions changed.
- Database file/storage format does not support engine downgrade.

### 15.1. Do Not Assume Database Downgrade Works

If the **database server** was upgraded to a new major version, reverting to the old database server binary may not be supported by the engine due to storage format or internal catalog changes.

JDK/app rollback and database server rollback are two distinct problems. You may need to keep the new server while choosing a compatible old driver/app, or use an engine-supported backup/replication strategy.

### 15.2. Drivers and Dependency Sets

When rolling back the application:

1. Identify App A's JDBC driver.
2. Test that driver against the current DB server.
3. Verify minimum Java and TLS/security features.
4. Run transaction/query integration tests against a representative DB.
5. Verify pooling, failover, and timeout behavior.

Do not fix connection issues by lowering TLS security or disabling certificate verification.

## 16. Dependency Rollback Is Not Just Changing a Version in Maven/Gradle

A dependency upgrade can introduce breaking changes across:

- Minimum Java runtime and bytecode.
- Public API/binary signatures.
- Jakarta `javax`/`jakarta` namespaces.
- Native library/OS ABI.
- SQL/serializer defaults.
- Crypto provider/security configuration.
- Framework auto-configuration.
- `ServiceLoader`/`META-INF/services` discovery.
- Logging/tracing agent integration.

### 16.1. Lock the Entire Release Bundle

In Java builds, keeping only `pom.xml`/`build.gradle` is insufficient if dependency versions can shift during resolution.

A release can record:

~~~text
Git commit + source revision
Gradle Wrapper/Maven version
Dependency locks or resolved dependency graph
Build JDK, JavaCompile release target
Application artifact checksum
Runtime container image digest
JDK/agent/native dependency builds
Configuration revision
Schema/event compatibility declaration
~~~

When rolling back, deploy the **verified artifact** rather than rebuilding the old release against today's dependency repository and hoping to get identical bytecode.

### 16.2. Artifact Sources May Have Vanished

A dependency served by an internal registry or legacy vendor might no longer be reachable. If the rollback plan relies on rebuilding "during an incident", the team can be blocked by:

- Artifact repository outage.
- Unpublished/retired dependencies.
- Base image tags now pointing to different digests.
- Expired build certificates/credentials.
- Old JDK removed from infrastructure due to security policy.

The solution is retaining immutable artifacts and runtime images per retention/security policy, along with a deployment rehearsal in DR/staging.

## 17. Rolling Back Container Images or Java Runtimes on Kubernetes

Kubernetes Deployment stores ReplicaSet history and supports rollout management commands. However, **`rollout undo` only affects configuration/deployment history** and does not restore external state.

Example observation commands:

~~~bash
kubectl rollout history deployment/customer-service -n staging
kubectl rollout status deployment/customer-service -n staging
~~~

Example Deployment rollback usable in staging once compatibility is verified:

~~~bash
kubectl rollout undo deployment/customer-service -n staging
kubectl rollout status deployment/customer-service -n staging
~~~

The commands above **were not executed while authoring this lesson** and are merely operational examples for authorized environments. Before a production rollback, select the exact revision/image digest, configuration, schema, and state rather than relying blindly on the most recent revision.

### 17.1. Pitfalls of `rollout undo`

- The old revision may reference an image tag rather than an immutable digest.
- ConfigMap/Secret contents may have changed even if the Deployment reverts to an old revision.
- The database has already run new migrations.
- Queues/caches still hold new state.
- A Helm/GitOps controller may automatically reconcile back to the current desired state.
- ReplicaSet history may no longer retain the version you want to restore.

Therefore, before rolling back, pause/coordinate the GitOps/Helm configuration source and specify the exact target revision. Do not treat `kubectl rollout undo` as a complete runbook.

### 17.2. Blue-Green and Canary

Blue-green maintains two application/runtime stacks to switch traffic quickly when appropriate. Canary gradually rolls out a slice of traffic.

Advantages:

- Can reduce blast radius.
- Detects regressions early.
- Allows shifting traffic back to A faster than rebuilding.

However, **blue-green does not duplicate database state by default**. If B already wrote a new format to the shared DB, shifting traffic back to A still hits compatibility issues. Both strategies only make binary/traffic rollback easier when data contracts are properly designed.

### 17.3. Rolling Deployments Have a Window Where A and B Coexist

Kubernetes can let old and new pods serve simultaneously during a rollout. Hence **forward and backward compatibility between A and B** not only serves emergency rollback, it is a prerequisite for normal rollout itself.

Tests should cover:

- A and B concurrently reading/writing the shared database.
- Events produced by B seen by A consumers.
- Sessions moving across pods.
- Software reading cache written by the other version.
- Backfill running while A/B update records.

If mixed-version behavior cannot be guaranteed, a cutover strategy or separate maintenance window with explicit write pauses is required.

## 18. Rolling Back on VM/systemd or Application Servers

On VM/systemd, rollback may involve switching an artifact symlink, switching the JDK executable, and updating the unit/drop-in before restarting the service. These steps must be versioned and verified:

~~~text
Release A:
  /opt/apps/customer/releases/A/app.jar
  JDK 17 installation / image
  Config profile A

Release B:
  /opt/apps/customer/releases/B/app.jar
  JDK 21 installation / image
  Config profile B
~~~

In this example, one deployment approach points the `current` path to the chosen release atomically, then performs a controlled service restart. Do not swap the JDK while leaving B's flags intact if JDK A does not support them.

### 18.1. systemd Rollback Must Address Multiple Details

- `ExecStart` and the actual Java executable.
- `EnvironmentFile`, JVM flags, and agent paths.
- `WorkingDirectory`, `User`/`Group`, filesystem permissions.
- systemd cgroup CPU/`MemoryMax`.
- Logging/heap dumps/truststores.
- Service dependency ordering.
- Restart policy and graceful shutdown.

After changing unit/drop-in files, run `daemon-reload` and restart per operational procedure; however, **restarting the service does not roll back the database**.

### 18.2. Application Servers and WARs

With Java EE/Jakarta EE, WAR rollback can be blocked by:

- Container/server already upgraded to the Jakarta namespace.
- Changed DataSource/JNDI names.
- Server-provided JPA/Validation implementations.
- Incompatible Servlet filters/REST providers.
- Session replication state/version.

If version A uses `javax.servlet` while the server moved to `jakarta.servlet`, merely redeploying WAR A may fail to run. You must roll back the entire server/runtime bundle or keep a compatible deployment target.

## 19. Managing Clear Rollback Boundaries

A **rollback boundary** is the point beyond which reverting to the previous release is no longer guaranteed through normal mechanisms.

Example:

~~~text
Phase 1: Expand schema
  Rollback App A: SAFE if tests prove it

Phase 2: Deploy App B, dual-read/write
  Rollback App A: SAFE WITH CONDITIONS

Phase 3: B writes new-only event/data
  Rollback App A: BLOCKED if A cannot read it

Phase 4: Contract/drop legacy column
  Rollback App A: NOT SUPPORTED
~~~

Each boundary must specify:

- Which change/release creates the boundary.
- Timestamp, flag, or migration ID milestone.
- Why rollback becomes dangerous.
- Who can approve crossing the boundary.
- What forward fix/recovery plan exists as an alternative.
- Until when backups/PITR/checkpoints remain viable.

Do not bundle a destructive migration into the same release pipeline without recording that it closes the rollback window.

### 19.1. The "Stop the World" Principle When Danger Strikes

If data is just discovered being written in the wrong format, letting App B keep serving writes increases the volume of data needing repair. An incident runbook may require:

1. Disabling the harmful feature or write path.
2. Putting the API into read-only/maintenance mode if designed and business-appropriate.
3. Preserving evidence and current state for analysis.
4. Assessing whether rolling back to A can read the state.
5. Selecting rollback, forward fix, or recovery per approved decision.

Read-only mode must be tested beforehand; if background workers still write to the DB, disabling HTTP write endpoints alone may not stop data mutation.

## 20. Feature Flags to Decouple Code Deploy From Data Changes

Feature flags allow deploying code that supports both old and new models, then activating the new behavior separately.

An example:

~~~text
Phase A:
  new_reader_enabled = true
  new_writer_enabled = false

Phase B:
  new_reader_enabled = true
  new_writer_enabled = true
  legacy_writer_enabled = true

Phase C:
  all consumers upgraded
  legacy_writer_enabled = false

Phase D:
  compatibility window ended
  remove old schema
~~~

Flag names are an illustrative model, not built into any framework. Sequence the steps according to data characteristics, avoiding enabling the new writer before old readers can read it.

### 20.1. Kill Switch Differs From Binary Rollback

When B fails on a new feature, disabling a feature flag can mitigate the incident quickly without rolling back the JDK/framework. However, a flag only stops future behavior—**it does not automatically revert already-written data**.

The runbook must document:

- Which flag disables the new writer.
- Whether flag updates take effect immediately or require a restart.
- Whether background jobs and consumers respect the flag.
- Whether already-created data requires reconciliation.
- Whether B's binary can still be rolled back after disabling the flag.

### 20.2. Flags Do Not Exempt Concurrency Testing

When multiple versions run simultaneously, flag propagation is not instantaneous. A window may exist where pods A/B apply different flags. If an atomic cutover is required, design an appropriate synchronization/leader-election/write-gating mechanism.

## 21. Rehearsing Rollback Before Production

An untested rollback plan is an assumption. Rehearsals must prove that **the combination of old code + new state** operates per contract.

### 21.1. Staging Test Scenario

~~~text
1. Initialize baseline data on App A + Schema S1.
2. Run expand schema migration.
3. Deploy App B + target JDK.
4. Create/modify data and emit events using B.
5. Run backfill/dual-write per procedure.
6. Stop/reduce B traffic per runbook.
7. Redeploy App A + old JDK + old config.
8. Have A read and update records created by B.
9. Run business invariants and consumer tests.
10. Confirm zero data loss and no duplicate side effects.
~~~

This is a real rollback rehearsal, unlike simply booting App A against an empty database without new data.

### 21.2. Mandatory Tests

| Category | Acceptance criteria |
|---|---|
| Startup | App A/old JDK starts with current schema and old runtime profile. |
| Read | A reads B-created and backfilled records without errors. |
| Write | A updates B-created records without destroying new data that must be preserved. |
| Transactions | Commit/rollback, idempotency, and constraints hold true. |
| Events | A reads events published by B or valid quarantine mechanism works. |
| Sessions/cache | No crashes/mis-deserialization; invalidation strategy exists. |
| External effects | No double-charge/double-notify on retry or replay. |
| Security | Authentication, authorization, and TLS remain correct. |
| Operational | Liveness/readiness, GC, memory, and shutdown PASS. |
| Recovery | Restore/PITR drill meets RTO/RPO when required. |

### 21.3. Test Data Must Reflect Migration Characteristics

Do not use just 3 simple records. Include:

- Null/legacy fields, unicode, timezones, decimal precision.
- Legacy/un-backfilled records and new records.
- Concurrent updates and retries.
- Transactions failing midway.
- Entities with complex associations/cascades.
- Multi-version event schemas.
- Users with sessions created by A and B.
- Records with already-triggered external side effects.

Protect sensitive data; use synthetic or anonymized data per policy.

## 22. Designing Quality Gates Before and After Rollback

A migration can enforce these gates:

~~~text
PRE-RELEASE:
  Compatibility matrix tests
  Schema expand/backfill dry run
  Restore/PITR drill
  JDK + dependency runtime test

ROLLOUT:
  Canary and business metrics
  Data integrity reconciliation
  Read/write compatibility checks

ROLLBACK DECISION:
  Boundary check
  Stop harmful writes
  Select safe target bundle
  Evaluate external side effects

POST-ROLLBACK:
  Functional invariants
  Data correctness
  Error rate/latency/GC
  Events and reconciliation
~~~

### 22.1. Hard Blockers

Examples of conditions blocking rollback:

- A cannot read data written by B.
- B ran a destructive schema migration that A still depends on.
- New event schema lacks old-reader compatibility.
- A lacks a critical security fix required in the current environment.
- A/old JDK cannot start with the new OS/container/native dependencies.
- Backup/restore plan has not been verified in a data-loss incident.
- Unresolved irreversible external side effects remain.

These blockers must not be ignored just because image rollback is fast.

### 22.2. When Is Configuration Rollback Enough?

If a regression is caused by a new `-XX` flag, GC thread count, container CPU limit, or wrong feature flag while code/data remain compatible, **configuration** can be rolled back without rolling back the application. However, test that the config change fixes the incident without side effects.

In particular, never downgrade the JDK solely to fix a faulty JVM flag when flags can be safely corrected on the target JDK.

## 23. Decision Workflow When a Production Incident Occurs

A decision tree:

~~~text
Regression detected after Java migration
                │
                ▼
Is data or security impacted?
         │                 │
        Yes            Unclear/No
         │                 │
         ▼                 ▼
Stop risky write path         Collect runtime metrics,
and assess integrity          identify error
         │                 │
         └────────┬────────┘
                  ▼
          Can rollback config/flag?
             │             │
            Yes            No
             │             │
             ▼             ▼
       Execute with     Is App A compatible
       verification      with the new state?
                           │             │
                          Yes            No
                           │             │
                           ▼             ▼
                     Rollback tested   Forward fix or
                     bundle            recovery/reconciliation
                           │             │
                           └──────┬──────┘
                                  ▼
                      Verify data + SLO
                      before closing incident
~~~

This workflow is directional. In a real incident, the runbook must specify authority, responsibilities, escalation, security/data owners, communication, and infrastructure-specific steps.

### 23.1. Do Not Destroy Evidence Before Diagnosing

If a process crashes or data is corrupted:

- Preserve application/JVM logs, traces, and metrics per retention policy.
- Record image digest, JDK version, flags, and schema migration IDs.
- Keep stack traces/core/heap dumps per information security policy.
- Save snapshots/checkpoints if appropriate and approved.
- Avoid deleting queues/DLQs or clearing DB tables arbitrarily.

Diagnostic data may contain PII/secrets; share only in authorized internal channels, never publicly.

## 24. Sample Runbook for Rolling Back App B → App A

Runbooks should be written, reviewed, and rehearsed prior to deployment. Sample:

~~~text
RUNBOOK: rollback customer-service B -> A

1. Trigger:
   - Error/latency/data-integrity thresholds breached
   - Incident owner authorizes rollback assessment

2. Preconditions:
   - Schema at expected compatible version
   - App A can read B-produced data/events
   - App A runtime image/JDK available and approved
   - No unresolved irreversible data change

3. Containment:
   - Pause harmful write paths/background jobs
   - Preserve current metrics/logs and state snapshot
   - Announce incident/change window

4. Choose action:
   - Config/feature flag rollback
   - Binary/runtime rollback
   - Forward fix
   - Recovery/PITR with data owner approval

5. Execution:
   - Select immutable release bundle A
   - Coordinate GitOps/Helm/systemd desired state
   - Shift traffic / deploy and monitor rollout
   - Do not run destructive schema down migrations
     without a separately approved data plan

6. Validation:
   - Functional critical paths
   - Reads/writes to migrated records
   - Event processing, sessions/cache
   - Data reconciliation and external effects
   - Operational SLOs, GC, OOM and restarts

7. Completion:
   - Incident owner records outcome
   - Backfill/replay and monitoring follow-ups
   - Re-enable traffic/writers when safe
   - Document residual risks and next release plan
~~~

The runbook above is a **guidance template**, not automated commands to execute directly. Replace placeholders with actual service details, dashboards, owners, artifact digests, and conditions.

### 24.1. "Who Decides?" Matters as Much as "Which Command to Run?"

For incidents affecting data or financial transactions, a restore/PITR decision may require:

- Incident commander/on-call.
- Application owner.
- DBA/data platform owner.
- Security/compliance if relevant.
- Product/business owner for RPO or transaction reconciliation.

When approval authority is unclear, operations teams can waste critical time during an incident or execute unapproved data-losing actions.

## 25. Common Complex Scenarios

### 25.1. B Added a New NOT NULL Constraint

If App A does not provide a value for the new field, rollback can cause INSERTs to fail. This can be avoided by applying constraints only after all writers are compatible, or using defaults/backfills with clear semantics during the compatibility window.

Do not arbitrarily drop an important constraint just to let App A run again if doing so risks losing invariants.

### 25.2. B Changed Enum Values

App B saves status `ORDER_PENDING_REVIEW`, while App A's enum lacks this value. When A reads the record, ORM/JSON mapping may throw an exception.

Possible solutions include:

- Upgrading A to tolerant-read unknown values before B writes new values.
- Feature-gating so new values are not generated during the rollback window.
- Applying an approved, business-meaningful adapter/translation.

Do not blindly map every new status to an arbitrary old status, especially in payment/order processing.

### 25.3. B Wrote a New JSON Format Into the Same DB Column

Even though the database schema did not change, JSON content can be incompatible with the old parser. This illustrates that **schema-level compatibility does not equal data-level compatibility**.

Version payloads and run old-reader tests, or use a new column/new namespace when formats change incompatibly.

### 25.4. B Enabled New Java Serialization for Sessions

If App A cannot deserialize new sessions, logging out/recreating sessions or separating session namespaces may be needed. This decision can affect user experience and security, requiring control and communication depending on the product.

### 25.5. B Updated the JDBC Driver Because the Database Enabled a New TLS Policy

Reverting to App A with the old driver may fail to connect due to TLS/authentication changes. Keep a driver release that is both compatible with App A and compliant with security policy, or forward-fix a verified A branch.

Do not downgrade TLS/security settings merely to restore connectivity if it violates policy.

### 25.6. B Emitted Events That External Consumers Cannot Process

Rolling the producer back to A does not fix event E2 already sitting in the broker. Classify, quarantine/replay, apply schema translation, or update consumers in a controlled way; already-emitted side effects must be reconciled.

### 25.7. B Sped Up Processing Yet Introduced Calculation Precision Drift

If B changed floating-point/`BigDecimal` rounding or locale rules, already-written data may differ from before. Rolling back A does not automatically fix historical rows. Determine affected transactions, standard rounding rules, audit trails, and an approved correction plan.

### 25.8. A Native Agent Only Supports the New JDK

An instrumentation agent or JNI library that only ships binaries for the new JDK/OS can prevent runtime rollback. Release bundle A must include its corresponding agent/native dependencies, or have a safe operational policy when the agent cannot load.

Do not disable a mandatory security agent without an alternative control mechanism.

### 25.9. Search Index Changed Mapping

App B creates a new index format; A querying with the old mapping may error or return different results. Support index aliases/versions, dual-indexing, or monitored rebuilds; rolling app rollback does not automatically revert the index to its old shape.

### 25.10. Data Encryption or Key Rotation

If B starts encrypting with a new format/key, A may be unable to decrypt. A safe pattern is usually **new reader supports old keys first**, maintaining key lifecycles per security policy and never deleting old keys until a complete decryption/re-encryption plan exists.

Do not log plaintext or keys to "firefight". Key revocation/retention must be coordinated with security/compliance.

## 26. Reconciliation After Rollback

After the service recovers, verify that business outcomes remain accurate; an HTTP 200 dashboard alone is insufficient.

A reconciliation report may include:

| Invariant | Verification |
|---|---|
| No lost confirmed transactions | Compare business ledger, external provider receipts, and database rows. |
| No duplicate payments/messages | Cross-check idempotency keys and transaction IDs. |
| Consistent balances/inventory | Verify totals and domain-specific reconciliation rules. |
| Migrated record counts | Compare counts, checksums, or appropriate sample validation. |
| Error-free sessions/cache | Monitor deserialization failures and auth metrics. |
| Event processing progress | Consumer lag, DLQ, retry failures, and ordering. |
| Database constraints | Check violations and un-backfilled data. |
| No lingering writes in broken new schema | Audit by writer version/feature flag. |

### 26.1. Reconciliation Is Not Just Comparing `COUNT(*)`

Two tables with identical row counts can still differ in monetary amounts, states, foreign keys, or timestamps. For critical data, use invariants, row-level checksums, IDs/versions, or business ledger comparisons depending on the domain.

If discrepancies exist, classify them:

- Lost data.
- Duplicate data.
- Incompletely migrated data.
- Syntactically compatible yet business-wrong data.
- Events processed outside the DB with no corresponding DB record.

Remediation actions must have an audit trail and idempotency so they do not make the issue worse.

## 27. Observability and Metrics During Rollout/Rollback

Useful signals typically include:

- Error rate by endpoint, HTTP/gRPC status, and exception classes.
- p95/p99 latency by request type, throughput, and queue depth.
- JVM crashes, `OutOfMemoryError`, OOMKilled, GC, and native memory.
- DB connection pool, deadlocks, constraint violations, slow queries.
- Schema migration/backfill progress, replication lag.
- Cache misses, session invalidation, deserialization errors.
- Message lag, DLQ, retries, and duplicate rates.
- Payment/email/webhook side-effect reconciliation.
- Readiness, liveness, restart loops, and canary health.

### 27.1. Thresholds Must Tie to Rollback Decisions

Illustrative policy example:

~~~text
Canary 5% traffic for a defined observation window
Abort if:
  critical data invariant violation > 0
  unauthorized access violation > 0
  OOMKilled/unexpected crash in canary
  p99 latency exceeds approved regression budget
  event deserialization failure appears

Before rollback:
  verify A can read B-generated data
  verify schema rollback boundary not crossed
~~~

The 5% figure is an example only; observation windows and traffic volume must be sufficient to detect errors. Do not auto-roll back blindly if the boundary has been crossed: instead perform containment/forward fix/recovery.

### 27.2. Missing Metrics Are Also an Incident

If monitoring loses data during canary, do not assume "no errors" because the dashboard is blank. A rollout gate can require sufficient samples, healthy telemetry, and data-integrity checks before proceeding.

## 28. Sample Release Bundle Metadata

A useful release record:

~~~yaml
releaseId: "customer-service-2026-11-B"
application:
  artifactDigest: "sha256:example-placeholder"
  sourceRevision: "example-commit"
runtime:
  javaMajor: 21
  jvmVendor: "vendor-placeholder"
  imageDigest: "sha256:runtime-placeholder"
  jvmProfile: "jvm-21-profile-v2"
dependencies:
  lockRevision: "example-lock-revision"
database:
  expandedSchemaVersion: "S2"
  destructiveContractApplied: false
  backfillState: "complete"
dataContracts:
  reads: ["customer-v1", "customer-v2"]
  writes: ["customer-v1", "customer-v2"]
events:
  reads: ["order-event-v1", "order-event-v2"]
  writes: ["order-event-v1"]
rollback:
  targetRelease: "customer-service-A"
  targetRuntimeJava: 17
  allowedUntilContractPhase: true
  rehearsalEvidence: "staging-run-placeholder"
~~~

This file is an **illustrative schema**, not an existing file or directly runnable automated tool. In real systems, version/validate fields using a policy agreed upon by the owning team.

Notably, a release record captures both **data compatibility** and **rollback window**, not merely an image name.

## 29. QA/CI Matrix for Rollback Readiness

CI/Pre-release can design these jobs:

| Job | What it runs | Criteria |
|---|---|---|
| Compile/runtime matrix | A/old JDK, B/new JDK per support contract. | No class-version, missing API/agent errors. |
| Expand migration | Run schema expand on production-like data. | App A continues reading/writing as before. |
| New data fixture | B creates new rows/events. | A can read or has clear boundary, no silent corruption. |
| Mixed-version write | A/B concurrently update fixtures. | No data loss or invariant violations. |
| Persistence integration | ORM A/B against corresponding DB schema. | Transactions, IDs, queries correct. |
| Serialization | A deserializes formats written by B. | Matches compatibility contract. |
| Cache/session | Mix A/B or shift traffic. | No crashes; auth/session policy holds. |
| Backup/PITR rehearsal | Restore in an isolated environment. | Meets approved RTO/RPO, integrity PASS. |
| Rollback smoke | Redeploy A over state created by B. | Functional + operational tests PASS. |
| Security regression | TLS, authorization, critical audits. | No blocker regressions. |

### 29.1. Do Not Require Every Job on Every Pull Request

Some tests can be time-consuming, especially restore/PITR or long-running backfills. Tier them:

- PR: unit, contract, schema compatibility, simulated mixed-version.
- Pre-release: full database integration and runtime/JDK matrix.
- Release candidate: restore rehearsal, rollback drill, and operational gates.
- Staging/canary: test with near-production infrastructure and traffic.

Mandatory jobs for release decisions must be defined beforehand; do not skip them because they take long once lightweight jobs turn green.

### 29.2. "Old Tests Passed" Is Not Enough

App A booting on S1 does not prove A works on S2. Rollback tests must **take the state after B has run**, not just run A's smoke tests on stale fixtures.

## 30. RPO, RTO, and Strategy Selection

| Scenario | Commonly considered option | Decision condition |
|---|---|---|
| Config/JVM flag causes error, data unchanged | Rollback config, controlled restart/rollout. | JDK and app remain safe, old flag supported. |
| B code buggy, schema remains backward compatible | Roll back app/runtime bundle A. | A reads/writes B-created data and events. |
| B wrote new format A cannot understand | Forward fix/compatibility patch or writer containment. | Zero data loss and a way to read new state exists. |
| Schema already dropped column A needs | Forward fix or planned recovery. | Rollback A is blocked due to missing data/schema. |
| Scoped data corruption | Targeted repair/reconciliation from audit/backup. | Affected records and invariants identified. |
| Broad data corruption, cannot repair selectively | PITR/restore and replay/compensation. | RPO/RTO, side effects, business/data approval. |
| Upgraded DB engine does not support downgrade | Keep new DB server, compatible app/driver or restore. | Engine support matrix/backup evidence. |
| Old JDK lacks mandatory security patch | Forward fix or hotfix on safe branch. | Security policy forbids downgrade. |

This is not an automatic command-lookup table; every option must depend on business, security, and data damage as well as feasibility.

### 30.1. When JDK Rollback May Be Forbidden for Security

An older JDK version may no longer receive patches or may have been removed from infrastructure policy. Even if App A runs, returning an old JVM to production can create unacceptable security/compliance risk.

An alternative is a hotfix on the target JDK or rebuilding the old branch with a patched/compatible runtime, if the product and dependencies permit.

The decision must go through formal risk acceptance with an approver; "this runtime used to work fine" is not sufficient.

## 31. Common Mistakes

| Mistake | Risk | Remediation principle |
|---|---|---|
| Rolling back the image means rolling back the system. | DB, events, and external effects remain new. | Verify the entire state. |
| Having a DOWN migration means data will recover. | Transformations can be lossy. | Expand-contract, backups, and reconciliation. |
| Running DROP column in the same release as B. | Immediately locks out rollback to A. | Contract only after the rollback window. |
| A can read S2 means A can write safely. | A may overwrite new data. | Test reads **and writes**. |
| Dual-write guarantees synchronization automatically. | Races, retries, split transactions, divergence. | Clarify source of truth and reconciliation. |
| Testing rollback on an empty DB. | Misses formats written by B. | Use B-created data fixtures. |
| JDK 21 → 17 just by changing `JAVA_HOME`. | New bytecode/dependencies may fail to run. | Runtime/bytecode/API matrix. |
| Reusing JVM flags from the newer JDK. | Startup failures or differing semantics. | Versioned runtime profiles. |
| Mixing `javax`/`jakarta` providers. | Binary API/classloading mismatch. | Roll back the entire compatible stack. |
| Downgrading a database server is as easy as an app. | Storage/catalog format may not support it. | Follow engine docs and restore rehearsals. |
| Resetting Kafka offsets to "undo". | Replay/duplicate side effects. | Idempotency and event recovery plan. |
| Clearing caches/sessions without weighing consequences. | DB load spikes or logged-out users. | Cache namespaces and rollout policy. |
| Restoring DB without checking side effects. | Payments/emails/APIs already happened. | Ledger reconciliation/compensation. |
| Having backups equals meeting RTO/RPO. | Backups may restore too slowly or be invalid. | Rehearse restores. |
| A 5% canary means rollback is always safe. | Canary still writes to the shared DB. | Data compatibility gates. |
| `rollout undo` handles GitOps/ConfigMap automatically. | Desired state and secrets stay new. | Bundle/manifest coordination. |
| Seeing the service Running means rollback succeeded. | Business data or messages may be wrong. | End-to-end invariants and monitoring. |
| Treating forward fix as failure. | Might roll back wrongly and corrupt data. | Pick the option that best reduces risk. |
| Reusing an EOL JDK to firefight. | Security/compliance regression. | Security approval or safe hotfix. |

## 32. Complete Process Before a High-Risk Java Migration

**Step 1 — Inventory the current release.** Record source, JDK/vendor/update, JVM flags, framework, ORM, JDBC driver, agents, OS/container, database schema, event formats, cache/sessions, and external integrations.

**Step 2 — Identify data changes.** Classify additive, compatible, destructive, lossy, format changes, and external side effects. Flag changes that create rollback boundaries.

**Step 3 — Design the compatibility matrix.** Confirm A/S1, A/S2, B/S1, B/S2 along with required data/event versions. Test reading **and writing**.

**Step 4 — Separate expand-contract.** Apply additive migrations first, keep old columns/formats during the compatibility window, deploy B and backfill, and contract only after exit criteria are met.

**Step 5 — Lock artifact/runtime bundles.** Store image digests, old/new JDKs, dependency locks, agents, and deployment configs; ensure artifacts remain redeployable.

**Step 6 — Define feature flags.** Decouple code rollout from new writers, support kill switches, and clarify flag propagation and rollback implications.

**Step 7 — Prepare backup/PITR and RTO/RPO.** Verify restore credentials, encryption keys, transaction logs, and reconciliation capabilities.

**Step 8 — Rehearse rollback with B-generated state.** In staging, have B write realistic new-style data, revert to A, and run contract tests, event/session tests, and data integrity checks.

**Step 9 — Establish gates/canary.** Choose thresholds for data integrity, errors, latency, OOM, message processing, and rollback boundaries.

**Step 10 — Phased rollout.** Monitor the mixed-version window, backfill progress, old consumer count, and side effects.

**Step 11 — During an incident, contain first.** Stop risky write paths, preserve evidence, and determine whether config, app/JDK can roll back, or forward fix/recovery is needed.

**Step 12 — Verify after rollback.** Measure business invariants, reconcile DB/events/external effects, verify security and operational SLOs.

**Step 13 — Intentionally close the rollback window.** Run destructive contract migrations only when no old writers/readers remain, no rollback target depends on the old schema, and approval is obtained.

**Step 14 — Postmortem.** Document root cause, affected data, runbook effectiveness, actual RTO/RPO timings, and improvements to CI/rollback tests.

## 33. Pre-Release Approval Checklist

- [ ] List of changes across JDK, app, dependencies, schema, and data formats is documented.
- [ ] Immutable artifact/runtime bundles A and B exist and are redeployable.
- [ ] Java bytecode targets and runtime dependencies for A/B are identified.
- [ ] Minimum Java, native agents, JPA/Servlet stack, and startup flags are checked.
- [ ] Compatibility matrix of old/new app against old/new schema/data/events exists.
- [ ] A can read and **write** data created by B per contract.
- [ ] Destructive/lossy migrations and rollback boundaries are clearly marked.
- [ ] Backfill has batches, idempotency, progress metrics, and a resume plan.
- [ ] Dual-read/dual-write has clear source-of-truth/conflict resolution.
- [ ] Event consumers/offsets, cache/sessions, and external side effects are reviewed.
- [ ] Database backup/PITR is verified through a restore drill.
- [ ] RTO/RPO have concrete values, owners, and feasibility evidence.
- [ ] Feature kill switches/containment exist to stop risky writes.
- [ ] Canary/rolling/blue-green strategy does not assume automatic DB rollback.
- [ ] Runbook clearly specifies rollback, forward fix, and recovery decision branches.
- [ ] Escalation, approvals, and communication plan are in place.
- [ ] Functional, data-integrity, and operational post-rollback gates exist.
- [ ] No downgrading to a JDK/dependency that violates security policy.
- [ ] Contract cleanup occurs only after the rollback window closes.

The checklist is a planning guide; every checked item needs real evidence from tests, release policy, or rehearsal.

## 34. Conclusion

**Rolling back the JDK or application when data and dependencies have changed is a system-wide compatibility problem, not merely a Java executable or container image problem.** An old JVM may not execute new bytecode/dependencies; an old application may not read new schemas/events/sessions; and a database restore can discard valid transactions that occurred after the restore point while failing to undo external side effects.

The safe strategy is designing for rollback from the start: preserve redeployable release bundles, use **expand → migrate → contract**, clearly mark **rollback boundaries**, test both old-reader and old-writer against data written by the new version, and maintain event/cache/session compatibility throughout the support window. Alongside this, prepare rehearsed backups/PITR, clear RTO/RPO, business reconciliation, kill switches, and a decision tree distinguishing rollback from forward fix or recovery.

In **Java Advance Compatibility Migration**, rollback success is not measured by whether the previous deploy command finished or the Pod turned green again. It is proven when **the application continues serving accurately, data and transactions remain consistent, external side effects are handled, and the system meets committed operational/security criteria**.
