# Do not use checkpoints as a substitute for database backups or transaction logs

CRaC (Coordinated Restore at Checkpoint) saves and restores the state of a Java process. A checkpoint image can hold the heap, thread states, and other process state as supported by the JVM, CRaC, and the platform. It helps an application resume quickly from a prepared state, yet **it is not a durable database backup and does not replace transaction logs/WAL**.

A database manages data durability through its own mechanisms: transactions, write-ahead logs (WAL), redo/undo logs, backups, replication, and recovery workflows. That data belongs to the database's lifecycle and storage. An application's CRaC image does not automatically back up database data files, does not guarantee logs have been durably archived, and does not provide the ability to restore a database to an arbitrary point in time.

A production system needs both mechanisms: checkpoints to shorten the time to bring the Java application back into operation, and backups/transaction logs to protect and recover database data. The two processes must coordinate around in-flight transactions, schema versions, credentials, and service status, yet they serve separate goals and have separate verification methods.

## 1. Distinguishing CRaC checkpoints, database checkpoints, and database backups

The word “checkpoint” is used across multiple layers, yet does not mean the same thing.

| Mechanism | Saved scope | Primary goal | Does it replace database backups? |
| --- | --- | --- | --- |
| CRaC process checkpoint | Java process state per runtime/platform support: heap, threads, and process state regions | Restore the application quickly from a prepared state | No. |
| Database checkpoint | Internal database mechanism writing/syncing data pages and recovery state per engine design | Bound the amount of log needing replay and support database recovery | Not an independent backup. |
| Database backup | Copy of database data, which may be full, differential, incremental, or consistent snapshot per database/storage tools | Recover data after loss, corruption, or operational error | This is the backup mechanism; combine with logs if point-in-time recovery is desired. |
| Transaction log / WAL archive | Records of data changes and transaction metadata in database format | Crash recovery, replication, and point-in-time recovery per engine capabilities | Does not replace full backups in every system; usually must combine with base backups. |
| Replication | Copy of data shipped to another node | Availability and failover | Does not replace backups; accidental deletions/corruption can replicate to replicas. |

A CRaC checkpoint and a database checkpoint are two operations at two distinct layers. When saying “create a checkpoint”, clarify whether you mean the Java process image or the database's internal checkpoint to avoid confusion in operational procedures.

## 2. Why is a CRaC image not a database backup?

A CRaC image saves the state of the checkpointed process. The application may hold on the heap:

- Domain objects and data read from the database.
- Caches, query results, and temporary data.
- `DataSource` objects, connection pools, and configuration details.
- Transaction contexts or objects representing active transactions.
- Application buffers not yet sent or not yet committed.

These objects are not a complete, consistent, independently restorable copy of the database. They are merely the application's in-memory state at one moment.

For example, the application read a data row onto the heap. After checkpointing, that row was updated or deleted in the database. Upon restore, the old object may still sit on the heap even though source data changed. Conversely, a transaction committed successfully in the database before checkpointing persists under the database's durability policy, even if the application restores from an older image.

Likewise, if the application was accumulating changes in buffers or an ORM persistence context without committing, the objects remaining on the heap do not prove those changes were durably persisted. Database backups and transaction logs must be managed at the database layer.

CRaC also does not automatically create an independent copy of database data files managed by another server. If the database runs on another machine/cluster, a Java process checkpoint saves only Java process state; the database maintains its own independent lifecycle. Even if the database runs on the same host or inside the same container, saving a process image is still not equivalent to backing up database files and may also depend on how storage is managed.

## 3. Transactions in flight at checkpoint time

The most critical risk when checkpointing an application with database connections is transaction state. A request may be midway through multiple steps:

```text
Receive request
    |
    v
BEGIN transaction
    |
    v
Read/write data
    |
    +---- checkpoint occurs here
    |
    v
COMMIT or ROLLBACK
    |
    v
Return response
```

If a checkpoint occurs while a transaction has not completed, the process image may contain transaction-related objects and context. However, the database server can time out, roll back the transaction when the connection drops, or clean up sessions under its own rules. Never assume a transaction can safely continue merely because Java objects remain on the heap.

A safe preparation procedure typically performs:

1. Stop accepting new requests or work that could use the database.
2. Wait for active requests/transactions to finish within a bounded deadline.
3. For work unable to complete within the deadline, apply an explicit cancel/rollback policy.
4. Confirm no application transactions remain that need to stay open across the checkpoint.
5. Close or release connection pools/sockets using supported APIs.
6. Only once application state is safe proceed to create the CRaC checkpoint.

Never arbitrarily invoke `commit()` inside a callback to “rescue” all open transactions. Committing is a business decision, not merely a technical step. Callbacks should coordinate with the transaction manager and request lifecycle so every transaction commits or rolls back according to its proper business logic.

## 4. Durability is handled by the database

Databases commonly use transaction logs or WAL to ensure changes are written according to durability rules. Depending on engine and configuration, a successful transaction commit may require logs to be flushed to durable storage before acknowledging commit.

Conceptual example:

```text
Application sends UPDATE
       |
       v
Database processes transaction
       |
       v
Write change log (WAL/redo log)
       |
       v
Flush log per durability policy
       |
       v
COMMIT is acknowledged
       |
       v
Application receives commit result
```

Details differ by database engine, synchronous commit settings, storage, and replication configuration. The application should not infer durability solely from calling `Connection.commit()`; understand the database configuration and ensure storage/backups meet system requirements.

CRaC does not replace database logging steps. If an application checkpoints immediately after receiving a commit acknowledgment, committed data is protected by database durability mechanisms and backup policies. If the process restores from an older image and re-runs the same business operation, the application must still handle potential duplicate operations.

## 5. Transaction logs, WAL, and point-in-time recovery

Transaction logs record information needed for a database to recover changes after a crash and, depending on the system, reconstruct state at a point in time. WAL (Write-Ahead Logging) is a common principle: log records must be durably written before the corresponding data pages are written in engine-specified order.

In many databases, point-in-time recovery (PITR) requires:

- A suitable base/full backup.
- A continuous chain of transaction logs/WAL from backup time to the target recovery time.
- Metadata and configuration needed by the database engine to replay logs.
- A restore procedure following database documentation.

A CRaC process image does not contain the full WAL chain and cannot replace a base backup. Nor is it an authoritative source for database LSN/SCN or recovery position unless a specialized integration workflow extracts that metadata from the database and manages it in an engine-supported manner.

Example of two independent flows:

```text
Java application flow                   Database protection flow
---------------------                   ------------------------
Prepare Resource                        Database generates WAL/redo log
      |                                         |
      v                                         v
CRaC checkpoint                         Back up database
      |                                         |
      v                                         v
Restore process                         Replay log when PITR is needed
      |                                         |
      v                                         v
Reopen traffic                          Database is recovered
```

Both flows may need a coordinated plan, yet success of one flow does not prove the other completed.

## 6. Backups, replication, and checkpoints serve different goals

| Mechanism | Recover from data errors/loss | Fast failover/switchover | Restore application state |
| --- | --- | --- | --- |
| CRaC checkpoint | No | Can shorten process startup time on compatible environments | Yes |
| Full/incremental backup | Yes, within backup scope and timestamp | Usually requires restore time | No |
| WAL/transaction log archive | Supports replay/PITR given base backup and continuous logs | Architecture-dependent | No |
| Database replication | Can aid failover to a replica; does not protect against all logical errors | Yes | No |
| Application cache snapshot | Recovers only cached data if custom-designed | Possibly | Only part of application state |

Replication is not an independent backup. If an accidental delete statement commits and replicates, replicas can receive the same change. Backups with retention and PITR allow recovering to a point before the mistake according to database capabilities.

CRaC helps the Java process come back faster, yet it does not make the primary/replica database healthier, does not create extra backups, and cannot repair deleted or miswritten data.

## 7. Designing Resource lifecycle for databases

A `Resource` can coordinate a connection pool across the CRaC cycle. The goal is bringing the application to a state with zero open transactions and recreating connections after restore.

```java
import org.crac.Context;
import org.crac.Resource;

public final class DatabaseResource implements Resource {
    private final DatabaseWorkCoordinator workCoordinator;
    private final DatabasePoolProvider poolProvider;

    public DatabaseResource(
            DatabaseWorkCoordinator workCoordinator,
            DatabasePoolProvider poolProvider) {
        this.workCoordinator = workCoordinator;
        this.poolProvider = poolProvider;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        workCoordinator.stopAcceptingNewWork();
        if (!workCoordinator.awaitTransactionsToFinish()) {
            throw new IllegalStateException(
                    "Database transactions did not drain before checkpoint");
        }

        poolProvider.closeCurrentPool();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        poolProvider.createAndValidateNewPool();
        workCoordinator.resumeAcceptingNewWork();
    }
}
```

`DatabaseWorkCoordinator` and `DatabasePoolProvider` are application abstractions. In real implementations:

- `stopAcceptingNewWork()` must prevent new requests/jobs from starting transactions.
- `awaitTransactionsToFinish()` must have a deadline and not wait indefinitely.
- Active transactions must finish or roll back per business logic.
- `closeCurrentPool()` must use the pool's proper API after draining borrowed connections.
- `createAndValidateNewPool()` must build a pool matching current credentials/endpoints and validate database connectivity.
- Resume traffic only once the new pool and required dependencies are ready.

If a pre-checkpoint callback fails after stopping new work or closing the pool, the application needs its own rollback/resume path for an aborted checkpoint. Do not rely on `afterRestore` to undo a failed checkpoint. Coordination and rollback must belong to the lifecycle coordinator or deployment state machine.

## 8. Do not hold transactions open across a checkpoint

A transaction is normally tied to a specific connection and session. The session can be timed out or closed by the database while the application is in checkpoint state. Even if the process restores successfully, the old transaction context is not implicitly still valid.

Practical principles:

- Keep transactions short; avoid long network calls or user interactions inside transactions.
- Never open a transaction before waiting on a callback, timer, or background task that could linger.
- Before checkpointing, drain transactions and conclude them per business rules.
- Never serialize or hold a `Connection` expecting to resume the transaction after restore.
- After restore, open new connections and start new transactions once the application is ready.
- For multi-step long-running operations, use durable workflows, sagas, or state machines persisted in the database rather than holding transactions open for long periods.

If business logic needs a multi-step sequence, each step should persist its state durably so it can resume or compensate after a process stops. Database transactions must not be used as a locking mechanism spanning a checkpoint interval.

## 9. Handling requests that committed while the response never reached the client

An easily overlooked scenario:

1. The application submits a transaction and the database commits successfully.
2. The application is checkpointed or stopped before the response reaches the client.
3. The client does not know the outcome and retries the request after the service restores.
4. The business operation might execute a second time.

Database backups do not automatically solve duplicate requests. Applications need idempotency keys or deduplication mechanisms for operations with side effects.

For example, a client sends `POST /payments` with an `Idempotency-Key`. The server saves the key and result within the same business transaction. When the request is retried, the server looks up the key and returns the committed result instead of creating a second payment.

An idempotency table can contain:

| Column | Role |
| --- | --- |
| `idempotency_key` | Unique key for a business request. |
| `request_hash` | Detects reusing the same key with a different payload. |
| `status` | Status `IN_PROGRESS`, `COMPLETED`, or a defined failure status. |
| `result_reference` | Reference to the committed result to return on retry. |
| `created_at` / `expires_at` | Supports retention and cleanup of deduplication records per policy. |

Writing the idempotency record and the business change must happen in the same transaction or an equivalent consistency mechanism. Otherwise, the system might record the key without recording the business change, or record the business change without recording the key.

## 10. Transactional outbox and inbox

If a database transaction also needs to emit an event to a message broker, committing the database and sending the message are two separate operations. The process can be checkpointed/stopped between those two operations.

Transactional outbox solves this by writing the business change and an outbox record inside the same database transaction. A separate publisher reads the outbox and sends events; after sending, the record is marked processed using an idempotent mechanism.

```text
BEGIN DB transaction
      |
      +--> Update business row
      |
      +--> Insert outbox event
      |
      v
COMMIT
      |
      v
Outbox publisher sends event
      |
      v
Mark event published / retry safely
```

If a checkpoint occurs after commit yet before the publisher sends the event, the outbox record remains in the database and the publisher can send it after restore. If the publisher sends successfully yet stops before marking published, the event may be sent again; consumers should be idempotent.

A transactional inbox or consumer-side deduplication table helps prevent processing one message multiple times. CRaC does not replace outbox/inbox and does not guarantee an external side effect outside the database executes at most once.

## 11. Coordinating CRaC with backups and PITR

When a consistent recovery point is needed for both the application and the database, explicitly define the orchestration procedure. A standalone CRaC image does not create an atomic distributed snapshot across the process and database.

A procedure might include:

1. Switch the service into maintenance or quiesce mode and stop accepting new requests.
2. Drain active requests and transactions; confirm no application transactions need to stay open.
3. Verify database backups/WAL archiving are active according to database policy.
4. If a unified recovery point is required, record the database recovery marker/LSN/SCN or matching metadata via supported database tools.
5. Create the database backup/snapshot using native mechanisms and retain required transaction logs per retention policy.
6. Create the application's CRaC checkpoint once Resources are safely prepared.
7. Store linked metadata: application build, JDK/CRaC version, schema version, database identity, backup ID, and recovery position if available.
8. Test database restoration in its own workflow, then restore the application in a compatible environment and confirm it connects to the exact database state.

Exact ordering depends on consistency requirements, database engine, and backup tooling. On some systems, online backups run while the database accepts writes; on others, snapshots/locks or dedicated backup mechanisms are required. Never manually copy the data directory files while a database is running unless the database explicitly supports that method.

Even if a synchronized recovery point between app and DB is unnecessary, ensure that when the app restores it remains compatible with current database state: schema, data, credentials, endpoints, and event consumer offsets.

## 12. Schema migration and application version compatibility

A checkpoint can hold objects created by an older application version. Meanwhile, the database may have migrated to a newer schema or data may have been updated by a newer release.

Before using a checkpoint, verify:

- The application build inside the image is compatible with the current database schema.
- Migrations completed before restored instances accept traffic.
- Old code does not write to columns/tables that were removed or changed semantics.
- Enums, serialized objects, and cached data on the heap do not conflict with the new schema/version.
- Consumer offsets and event formats match the current message version.

The expand-and-contract strategy is often useful for rolling upgrades: add compatible schema changes first, deploy the new application, shift traffic, and only then drop old schema elements once zero old instances remain. Never restore an old checkpoint against an incompatibly changed database merely because the process image can still load.

## 13. Protecting backups, WAL, and checkpoints as separate assets

Database backups and WAL can contain complete business data. CRaC images can contain heap data, credentials, tokens, caches, and other sensitive information. Both must be protected, yet retention and access policies may differ.

For database backups/WAL:

- Encrypt at rest and in transit per database/organization policy.
- Restrict read, write, delete, and restore permissions.
- Maintain retention aligned with regulatory requirements and RPO.
- Store copies in separate failure domains when architecture requires.
- Monitor WAL archive continuity and backup failures.
- Run periodic restore drills; an untested backup does not prove recoverability.

For CRaC checkpoints:

- Store on storage with access controls and data protection.
- Attach build/runtime/host compatibility metadata.
- Never place images in public artifacts or logs.
- Enforce retention and old-image deletion procedures.
- Do not assume checkpoint images can recover databases or move arbitrarily across any hosts.

## 14. RPO and RTO: checkpoints do not replace backup objectives

RPO (Recovery Point Objective) is the maximum acceptable data loss, usually expressed in time. RTO (Recovery Time Objective) is the maximum tolerable time to restore service.

CRaC can primarily help trim part of application RTO by reducing JVM startup and state-preparation work. It does not satisfy database RPO on its own. RPO depends on backup cadence, WAL/log archiving, replication, and database durability policies.

| Objective | Primary mechanism | Role of CRaC |
| --- | --- | --- |
| Reduce application startup time | CRaC checkpoint/restore, images, and warm-up | Can reduce process initialization portion. |
| Reduce potential data loss | Backups, WAL archives, replication, and durability policies | Does not replace. |
| Restore database to before an erroneous operation | Base backups and transaction logs/PITR | Does not replace. |
| Bring application back after database recovers | CRaC restore combined with resource/config refresh and readiness | Can help the app become ready faster once dependencies are healthy. |

Do not advertise CRaC restore time as overall system RTO if database restore, DNS, credential refresh, schema compatibility, and dependency recovery have not been counted.

## 15. Easily confused scenarios

| Scenario | What CRaC can do | What the database/application still handles |
| --- | --- | --- |
| Database loses its data volume | Restore Java process from checkpoint | Restore database from backup and replay logs; then connect app to recovered database. |
| An uncommitted transaction during checkpoint | Save process state per checkpoint mechanism | Drain/commit/roll back transaction prior to checkpoint; never rely on Java objects to resume transactions. |
| Commit succeeded yet response missed client | Restore process from saved image | Idempotency/deduplication so retried requests do not execute business logic twice. |
| Message not yet published after commit | Restore publisher/process | Transactional outbox and publisher retries. |
| Message published yet not acked/marked | Restore consumer/publisher depending on architecture | Consumer idempotency/inbox to handle duplicates. |
| Data accidentally deleted and replicated | Restoring app does not undo changes | PITR from backup/WAL to before the deletion. |
| App restores from old build after migration | Recovers old process objects | Schema/version compatibility and rollout strategy. |
| Heap cache differs from current DB data | Restores stale cache | Invalidate, refresh, or check versions before use. |

## 16. Testing the end-to-end recovery workflow

A good test must verify recoverability of both process state and database data. It can be split into independent tests plus a coordinated test.

### Testing CRaC

1. Launch the application on a supported JDK/CRaC build.
2. Prepare Resources and drain transactions before checkpointing.
3. Create the checkpoint.
4. Restore the process in a compatible environment.
5. Verify new connection pools, credentials, and current endpoints.
6. Run health checks and sample read/write operations.

### Testing database backup/PITR

1. Create a base backup using database tooling.
2. Execute known transactions and confirm commits.
3. Ensure WAL/transaction logs are continuously archived.
4. Restore into a test environment from backup and replay logs to the recovery target.
5. Verify data at the recovery point matches expected transactions.
6. Measure restore time and potential data loss.

### Coordinated testing

1. Quiesce the application and drain transactions.
2. Record backup ID/recovery position alongside application build/checkpoint ID.
3. Create database backup/marker and CRaC checkpoint following the designed procedure.
4. Test a failure scenario: loss of a database node, transaction rollback, or PITR recovery in an isolated environment.
5. Restore the database before bringing the application back, if the scenario requires.
6. Restore the application and verify caches, pools, credentials, schema, and consumer offsets align with database state.
7. Send requests with idempotency keys and confirm zero duplicate side effects occur.
8. Verify real RPO/RTO through measurements.

Never test PITR on a production database serving live traffic without a safe procedure. Use an isolated recovery environment to validate backups and logs.

## 17. Operational checklist

- [ ] Clearly distinguish CRaC process checkpoints from database-native checkpoints.
- [ ] Maintain database backups independent of CRaC images.
- [ ] Maintain transaction log/WAL archiving and verify continuity per PITR requirements.
- [ ] Understand database and storage durability policies.
- [ ] Before checkpointing, stop accepting new work and drain active transactions.
- [ ] Never hold transactions/connections open across a checkpoint expecting to continue old sessions.
- [ ] Have explicit commit/rollback policies for in-flight requests.
- [ ] Handle idempotency when commit succeeds yet the response is lost or the request is retried.
- [ ] Use outbox/inbox when coordinating database transactions with message brokers.
- [ ] After restore, create new connection pools and validate database connectivity.
- [ ] Verify schema/version compatibility with the application checkpoint.
- [ ] Refresh caches, credentials, endpoints, and consumer offsets from authoritative sources.
- [ ] Protect backups, WAL, and checkpoints with appropriate access controls and retention.
- [ ] Maintain metadata linking build, checkpoint ID, backup ID, and recovery position when needed.
- [ ] Test backup/PITR restore and CRaC restore separately, then test end-to-end.
- [ ] Measure RPO/RTO for the whole system, not merely JVM restore time.

## 18. Conclusion

CRaC checkpoints save Java process state for fast application recovery. Database backups save durable data; transaction logs/WAL support crash recovery, replication, and point-in-time recovery per database capabilities. Database-native checkpoints are likewise an internal engine mechanism and are not synonymous with CRaC images.

Drain and conclude transactions according to business logic before checkpointing, close connections under supported lifecycles, and recreate pools after restore. Use backups/WAL to protect data, idempotency to handle request retries, outbox/inbox to coordinate databases with message brokers, and test PITR independently. CRaC can cut application startup time, yet data recoverability still relies completely on the database's backup and recovery strategy.