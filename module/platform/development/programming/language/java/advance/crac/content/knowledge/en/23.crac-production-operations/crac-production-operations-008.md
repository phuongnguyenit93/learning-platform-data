# Rolling Back a Release Without Reusing Invalid Business State

When a new Java release fails in production, operations teams usually want to revert to the previous version as quickly as possible. With CRaC-enabled applications, this action introduces an additional factor to control: a checkpoint stores the state of a process at a point in time, while business data and external systems continue changing.

Therefore, rolling back a release must restore the exact **compatible application code and runtime**, while reloading **current business state from authoritative data sources**. Do not assume that the previous release's heap snapshot still reflects current order status, balances, inventory, access permissions, or processing progress. A checkpoint may be technically valid yet contain stale data or data no longer compatible with the active schemas and events.

## 1. Distinguishing Application Rollback from Data Rollback

Application rollback reverts the workload to a known-stable software artifact: OCI image, application version, JDK/CRaC runtime, configuration, and corresponding checkpoint. Data rollback alters persistent data back to an earlier state or executes compensating operations to correct business outcomes.

These two activities are not synonymous:

| Activity | What Changes | Automatically Restores Business Data? |
|---|---|---|
| Deployment rollback | Pod template, image digest, release configuration | No |
| Restore checkpoint | JVM process state at checkpoint time | Does not restore databases, brokers, or external services |
| Invalidate/rebuild cache | Derived state in memory/cache | Does not modify the primary data source |
| Compensating transaction | Writes new business record to offset a prior action | Can fix business effects, but does not erase history |
| Database point-in-time recovery (PITR) | Restores database to a specific point in time | May lose transactions after that point without replay/reconciliation |

For example: version `2.4.0` records an order successfully, but later a tax calculation bug is discovered. Redeploying `2.3.5` only changes the code handling subsequent requests. It does not automatically fix orders already written by `2.4.0`, nor does it delete published messages. If data was written incorrectly, a separate data repair or business compensation procedure is required.

## 2. Why Can an Old Checkpoint Contain Invalid Business State?

A checkpoint is a snapshot of process state, not a consistent snapshot of the entire distributed system. The heap may contain:

- Business objects loaded before checkpoint such as orders, inventory, or workflow state.
- Caches built from the database at an earlier point in time.
- User sessions or authorization details that have changed.
- In-flight messages, consumer offsets, or cursors.
- Leader flags, lease owners, or distributed lock state.
- Tokens, DNS results, service addresses, and environment-dependent connections.
- Counters or IDs generated in memory instead of from a durable ID source.

While the process was not running, another Pod or another service may have updated the database, processed messages, changed permissions, revoked tokens, or acquired a new lease. When restoring an old checkpoint, objects in the heap do not automatically synchronize with those changes.

For example, the checkpoint stores `inventoryAvailable = 5`. While the Pod was stopped, another replica sold all 5 items. If the restored Pod continues using the value in the heap, it may accept additional orders based on stale inventory. The authoritative source of inventory must be the database or inventory service; the in-heap cache must be invalidated or refreshed before serving requests.

## 3. Classifying State Before Deciding on Reuse

Each component in the application needs clear rules during rollback:

| State Type | Example | Handling on Rollback/Restore |
|---|---|---|
| Immutable structures | Route metadata, serializer metadata, object graphs without mutable data | Can be kept if compatible with the release and runtime |
| Derived caches | Product prices, inventory, permissions, profiles, database-backed configs | Invalidate or refresh from the authoritative source |
| In-memory workflow state | In-progress orders, payment steps, running tasks | Reconcile with durable store; resume via state machine and idempotency |
| Connections and OS resources | Sockets, connection pools, file descriptors, threads | Close before checkpoint; recreate after restore |
| Credentials and sessions | Tokens, TLS contexts, user sessions | Read/refresh per current policy; verify version and expiry |
| Consumer/queue state | Offsets, subscriptions, in-flight messages | Read durable cursors, re-acknowledge/claim per broker semantics |
| Leadership and leases | Leader flags, lock owners, lease deadlines | Acquire/renew with current identity; use fencing tokens |
| Durable business data | Orders, payments, ledger, inventory | Keep authoritative source; modify only via migration or controlled compensation |

There is no universal command to clear all stale objects from the heap. Design resources and cache providers for selective refreshing, and block readiness until mandatory state has been verified.

## 4. Tying Checkpoints to the Exact Release

Checkpoints must be managed as immutable artifacts tied to the version that produced them. Do not select a checkpoint based only on a name like `latest` or a shared directory that can be overwritten.

A release bundle should record at minimum:

| Metadata | Purpose |
|---|---|
| Application version and OCI image digest | Selects the exact built code and dependencies |
| JDK vendor/version and CRaC runtime version | Identifies the runtime that created the checkpoint |
| OS, kernel/architecture, and restore conditions | Checks platform compatibility |
| Checkpoint ID and SHA-256 manifest | Selects the exact snapshot and verifies contents |
| Configuration version | Identifies configuration used when creating the checkpoint |
| Database schema range | Determines whether the release can run against the current schema |
| Event/message schema range | Determines whether the release can read messages currently in queues |
| Migration version | Tracks which migrations have been applied |

Example release metadata:

```yaml
release:
  applicationVersion: "2.3.5"
  image: "registry.example.com/orders-api@sha256:..."
  jdk: "vendor-jdk-version"
  cracRuntime: "runtime-version"
  checkpointId: "orders-api-2.3.5-build-1842"
  checkpointManifestSha256: "..."
  configVersion: "orders-api-config-17"
  databaseSchema:
    minimum: 41
    maximum: 43
  eventSchema:
    readable: ["order.v1", "order.v2"]
    writable: ["order.v1"]
  migrationVersion: 43
```

Values in the example only illustrate the metadata schema. The pipeline must generate actual values from the build and migration ledger. The checkpoint manifest must be verified before the runtime reads the image.

Do not restore a checkpoint from `2.4.0` and try to run `2.3.5` code unless the two versions share a verified compatibility contract. A heap snapshot can contain object layouts, class metadata, framework state, and data tied to the code of the checkpoint-creating version. Use the checkpoint created by the exact build/runtime compatible with the rollback image. If no compatible checkpoint exists, cold-starting the older version is usually safer than forcing restore of a mismatched release snapshot.

## 5. Business State Must Be Reloaded from Authoritative Sources

After restore, identify which data is the source of truth. For example:

- Balances and financial transactions: ledger/database with transactions and audit trails.
- Orders: order database or order-owning service.
- Inventory: inventory service/database with reserve/commit mechanisms.
- Access permissions: current identity provider or authorization store.
- Workflow state: durable state machine, event store, or job table.
- Consumer progress: broker offsets/acks and inbox/outbox tables.

An in-heap cache is only a derived copy. If the checkpoint may contain stale cache entries, invalidate the cache before opening admission or reload from the primary source. Do not silently fall back to values inside the checkpoint when the authoritative source is unreachable if doing so could lead to wrong business decisions.

For certain public or immutable data, retaining cache entries may be valid. Attach TTL/version and verify freshness. For data impacting money, inventory, permissions, or order state, enforce stricter policies and validate against the authoritative source.

## 6. CRaC Lifecycle for State Requiring Refresh

A `Resource` can close resources before checkpoint and refresh state after restore:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class BusinessStateResource implements Resource {
    private final BusinessStateCache cache;
    private final ConnectionManager connections;
    private final LeaseManager leases;

    public BusinessStateResource(
            BusinessStateCache cache,
            ConnectionManager connections,
            LeaseManager leases) {
        this.cache = cache;
        this.connections = connections;
        this.leases = leases;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        cache.stopRefreshJobs();
        leases.releaseIfOwned();
        connections.close();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        connections.reconnect();
        cache.invalidateAll();
        cache.reloadCriticalEntries();
        leases.acquireOrConfirmCurrentLease();
    }
}
```

This is an architectural example; the `BusinessStateCache`, `ConnectionManager`, and `LeaseManager` APIs are application abstractions. Ordering inside callbacks must reflect actual dependencies: if the cache needs the database, the database must be opened before reloading the cache. If the lease service needs fresh identity, identity must be refreshed before the lease manager.

`afterRestore` should complete only when mandatory state is valid. If an optional cache has not finished loading, it can warm up in the background if the request path has a safe fallback. If inventory or authorization has not been verified, do not open readiness for features depending on them.

## 7. Database Schema Changes and Backward Compatibility

A code rollback can fail if the new release altered the schema in a way the old version does not understand. Therefore, database migrations must be designed together with the release strategy.

### 7.1. Expand-Contract

The expand-contract pattern breaks schema changes into compatible steps:

1. **Expand:** add new tables/columns/indexes in a way that does not break old code; keep old columns.
2. **Deploy compatible code:** the new version can read/write the expanded schema; the old version can still run during the rollback window.
3. **Migrate data:** backfill data in batches, with checkpoints/cursors, safely resumable.
4. **Switch usage:** gradually switch reads/writes to the new schema, with observability and ability to revert.
5. **Wait rollback window:** retain the old schema and compatibility until rollback to the old release is no longer needed.
6. **Contract:** only then drop old columns, tables, or constraints.

Example adding `display_name` while old code still uses `full_name`:

```sql
-- Expand: add new column, do not drop old column yet.
ALTER TABLE customer ADD COLUMN display_name VARCHAR(200);

-- Backfill in batches in a separate migration.
UPDATE customer
SET display_name = full_name
WHERE display_name IS NULL;
```

Only after all rollback-eligible releases have reached end-of-life does a new contract migration drop `full_name`. Do not execute the contract migration in the same initial deployment step if code rollback capability must be preserved.

### 7.2. Do Not Automatically Roll Back Migrations When Rolling Back the Application

`kubectl rollout undo` or changing an image tag does not automatically revert database migrations. Automatically running reverse migrations can lose data written by the new version into new columns/tables.

In most systems, an application rollback should run against the current schema if that schema remains backward-compatible. Migrations are generally designed forward-only; data rollback requires a separate decision. If the schema was already contracted and old code is no longer compatible, the safe option may be a forward-fix in code instead of redeploying the old version.

### 7.3. Resumable and Reconcilable Data Migrations

Long-running backfills need:

- Durably persisted cursor or processed key range.
- Batch size and load limits.
- Idempotent updates so rerunning does not create duplicate data.
- Metrics for succeeded/failed record counts and remaining time.
- Rules for handling new records created during the backfill.
- A rollback or forward-repair plan if migration stops midway.

Do not rely on a counter variable in the checkpoint heap as the sole cursor for a business migration. Persist the cursor in a database or durable store so any release can resume from the actual state.

## 8. Event, Queue, and Message Compatibility

Rolling back an application can revert consumers to older code while queues already contain messages produced by the newer version. If the message schema is not backward-compatible, old consumers may fail to parse or silently drop critical fields.

Manage event schemas as an independent contract:

- Add new fields as optional/defaulted before old consumers are retired.
- Avoid changing semantics or reusing field names for different meanings.
- Keep old consumers able to read new message versions during the rollback window.
- Use a schema registry or versioned envelopes if the system needs schema governance.
- For event stores, use upcasters to translate old events to current read models; do not arbitrarily rewrite event history.
- For queues, keep acknowledgments/offsets durable and idempotent so messages can be redelivered.

Example envelope:

```json
{
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "eventId": "evt-7b9d...",
  "occurredAt": "2026-11-13T07:30:00Z",
  "payload": {
    "orderId": "ord-123",
    "currency": "VND",
    "total": 250000
  }
}
```

If the old version only understands `schemaVersion: 1`, it needs an adapter/upcaster or the producer must continue emitting the old version during the compatibility phase. Do not assume that merely rolling back the consumer will convert messages already sitting in the queue.

For consumers processing a message at checkpoint time, clearly determine whether the message was acknowledged, whether the transaction committed, and whether side effects may have occurred. Use inbox/outbox, idempotency keys, or broker/database integrated transactions if available to prevent duplicate processing on restore or rollback.

## 9. Caches, Sessions, and Derived Data

Caches are often the easiest place to accidentally reuse stale state because the checkpoint heap keeps objects without any obvious connection errors. Tie caches to versions or data sources:

- Cache keys can include tenant, schema version, or data generation.
- Critical cache values should carry `loadedAt`, source version, or TTL.
- After restore, invalidate data that could have changed while the process was stopped.
- Reload critical caches before readiness; non-critical caches can warm up in the background.
- Never allow stale caches to write outdated data back to authoritative sources.

User sessions also require a policy. Sessions in the heap or local memory may have expired, been revoked, or no longer match a newer serialization version. Use a shared session store or current token validation; do not trust an old session merely because the object still exists after restore.

If the session format changes between releases, version serialization and support reading multiple versions during the rollback window. When safe conversion is impossible, forcing re-authentication is preferable to using incompatible sessions.

## 10. Leases, Leader Election, and Distributed Locks

A checkpoint may hold `isLeader = true`, a lease token, or a lock handle in the heap. When the old Pod stops or the release is rolled back, the lease may have expired and been acquired by another instance.

After restore or rollback:

1. Do not treat an in-heap leader flag as proof of current ownership.
2. Recreate the coordination service client connection.
3. Read the current lease from the authoritative source.
4. Acquire/renew the lease using the current instance identity.
5. Use fencing tokens or monotonically increasing versions to prevent an old owner from writing after a new owner.
6. Run leader jobs only after the lease is confirmed.

When using the Kubernetes Lease API, `holderIdentity` must reflect the current Pod/process rather than copying the value from the checkpoint. When using distributed locks in a database/Redis, require TTLs and fencing to avoid stale locks after network partitions or process pauses.

## 11. Release Rollback Procedure with CRaC

A safe rollback procedure can be broken into the following steps.

### Before Release

1. Store the immutable image digest and checkpoint artifact of the running release.
2. Retain the previous release artifacts throughout the rollback window.
3. Verify checkpoint manifest, signatures, JDK/CRaC versions, OS, and architecture.
4. Check the compatibility matrix between old/new releases and database/event schemas.
5. Apply expand migrations before deploying code that requires the new schema.
6. Maintain backups/PITR aligned with RPO/RTO and test database restore capability.
7. Identify in-heap state that must be invalidated/reloaded after restore.

### When a New Release Is Found Faulty

1. Halt the rollout or stop shifting traffic to the faulty release.
2. If the bug could write corrupted data, restrict or pause the affected write paths.
3. Record the release ID, checkpoint ID, schema migration version, and affected time window.
4. Select the image digest of the previous stable release.
5. Select the checkpoint matching that release's exact build/runtime; if no compatible checkpoint exists, cold-start the old release.
6. Do not automatically execute reverse migrations solely because code was rolled back.
7. After restore, refresh identity, credentials, connections, caches, sessions, leases, and queue cursors.
8. Reconcile in-progress workflows with the durable store; use idempotency when resuming.
9. Open readiness only after schema and business state are verified.
10. Monitor errors, latency, newly written data, and consumer lag after rollback.

### After Rollback

1. Determine whether the new release wrote corrupted data or only caused processing errors.
2. If corrupted data exists, create repair migrations or compensating transactions with an audit trail.
3. If PITR is needed, evaluate transactions occurring after the recovery point and plan replay/reconciliation.
4. Retain logs, events, and checkpoint metadata for investigation.
5. Do not delete the faulty release's artifacts until analysis is complete and retention policy permits.

## 12. Kubernetes Deployment Rollback

Deployment revisions store Pod templates; they do not store database snapshots or CRaC checkpoints with business semantics. You can view history and roll back templates:

```bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production
```

If a specific revision needs to be selected:

```bash
kubectl rollout undo deployment/orders-api \
  --to-revision=12 \
  -n production
```

The rollback command only restores the Pod template of the selected revision. The pipeline must ensure that template references the image digest and checkpoint artifact of the exact release. If an old template points to a mutable tag or a `latest` checkpoint path, rollback could accidentally run the newer artifact. Prefer immutable digests and explicit checkpoint IDs/versions.

After `rollout undo`, new Pods still go through restore, resource refresh, and readiness. Old Pods may continue serving during the rollout if the strategy allows; ensure both old and new versions remain compatible with schemas/messages during the overlap period.

## 13. Example Guard for Checking Release/Checkpoint Compatibility

An application can store release metadata outside the checkpoint and verify it before restore. This Java example illustrates checking the application version and schema range:

```java
public record ReleaseDescriptor(
        String applicationVersion,
        String imageDigest,
        String checkpointId,
        String jdkVersion,
        String cracRuntimeVersion,
        int minDatabaseSchema,
        int maxDatabaseSchema) {
}

public final class CompatibilityGuard {
    public void verify(
            ReleaseDescriptor release,
            RuntimeDescriptor runtime,
            int currentDatabaseSchema) {

        if (!release.jdkVersion().equals(runtime.jdkVersion())) {
            throw new IllegalStateException("JDK version mismatch");
        }
        if (!release.cracRuntimeVersion().equals(runtime.cracRuntimeVersion())) {
            throw new IllegalStateException("CRaC runtime mismatch");
        }
        if (currentDatabaseSchema < release.minDatabaseSchema()
                || currentDatabaseSchema > release.maxDatabaseSchema()) {
            throw new IllegalStateException(
                    "Database schema is outside the supported range");
        }
    }
}
```

`RuntimeDescriptor` is an abstraction providing actual runtime information. In deployment, checking the checkpoint manifest and image digest should take place in the entrypoint before JVM restore; code inside the heap cannot replace verifying the artifact before the runtime reads it. A post-restore guard can confirm the database schema and external contracts before readiness turns on.

Do not compare only version strings if the version does not reflect build identity. Use image digests, build IDs, and checkpoint IDs to accurately identify artifacts. If schema compatibility cannot be expressed as a simple numeric range, use a capability/schema registry or explicit migration contract.

## 14. In-Progress Workflow State and Side Effects

Rollback often happens after the new release has already processed part of a request or job. A request may have:

- Written to the database without returning a response.
- Published a message without committing the transaction.
- Called a payment API without recording the result back to the database.
- Sent an email or notification that cannot be retracted.
- Held a lock or reserved inventory for a limited time.

When reverting to an earlier version, you cannot simply restore request objects from the heap and replay everything. Check durable state to determine which steps committed. For write operations, use idempotency keys that remain stable across releases and retries. For multi-service workflows, use sagas/compensating actions to offset already-succeeded steps.

For example, if the payment gateway already captured funds but the database has not recorded `PAID`, do not send another capture request simply because a worker was restored. Query the payment provider using the transaction/idempotency ID, reconcile the outcome, and then continue the workflow.

## 15. Compensating Transactions and Point-in-Time Recovery

When business data has been erroneously modified, there are two distinct categories of options.

### Compensating Transactions

Create a new transaction to offset the effect of an erroneous transaction. For example, issue a refund for an erroneously captured payment or post an adjustment entry to the ledger. This preserves the audit trail and fits systems requiring immutable history.

Compensation must be idempotent, track its status, and be approved per business rules. Do not directly delete transaction history to make data look as though it never happened.

### Point-in-Time Recovery

PITR restores the database to a point in time before the error. It can discard valid transactions that occurred after that point. Before choosing PITR, determine:

- RPO: maximum amount of data loss acceptable.
- RTO: maximum time allowed for service recovery.
- How valid transactions after the PITR point will be replayed or reconciled.
- Whether the message broker, outbox, object storage, and database share a consistent checkpoint.
- How consumer offsets and idempotency records need to be adjusted.

Do not restore a database into the past while queues and external services still hold post-recovery-point state without a reconciliation plan. Distributed systems need to recover related data sources under a coordinated procedure.

## 16. Canary and Automated Rollback

Canary rollouts limit blast radius by sending a portion of traffic to the new release first. With CRaC, canary Pods must use a checkpoint from the same release and be observed like regular Pods.

Automated rollback triggers may include:

- HTTP 5xx rate exceeding threshold over a sufficiently long window.
- p95/p99 latency rising above SLO.
- Increasing restore failure rate or readiness timeouts.
- Abnormal number of OOMs/restarts.
- Business invariant violations, such as unbalanced ledger totals or negative inventory.
- Abnormal rise in consumer lag or dead-letter queues.

Do not automatically roll back over a noisy metric spike lasting only a few seconds. Use evaluation windows, baselines, and impact-based thresholds. For bugs risking corrupted writes, prioritize halting the affected write path even when infrastructure metrics appear normal.

Automated rollback must select an immutable release bundle and run the same refresh/validation process as manual rollback. It must never automatically revert schemas or restore old checkpoints containing stale business data.

## 17. Testing Rollback Before Production

Rollback must be rehearsed with production-like data and schemas. Scenarios to test:

1. Deploy a new release on an expanded schema, then roll back to old code; verify old code can still read/write.
2. Create a checkpoint of the old release, update the database from another replica, restore the old checkpoint; verify business caches are invalidated/reloaded.
3. Attempt to use a checkpoint from the new release with the old image; compatibility guard must reject it before restore.
4. Push new-schema messages into the queue and roll back the consumer; verify the old consumer can read them or messages are safely routed.
5. Stop a worker mid-workflow with side effects; restore/roll back and verify idempotency prevents duplicate actions.
6. Expire a lease while the Pod is stopped; verify the Pod does not continue acting as the old leader.
7. Simulate token or certificate rotation; verify resources refresh after restore.
8. Simulate a migration backfill stopping midway; verify the durable cursor enables resumption.
9. Simulate erroneously written business data; verify compensation/PITR procedures are separate from image rollback.
10. Run a canary, trigger automated rollback, and verify new Pods become Ready only after compatibility checks.

Testing must verify not only that the Pod runs, but also business invariants: no duplicate orders created, no double-captured payments, no overselling inventory, no lost messages, and no two leaders writing concurrently.

## 18. Logging and Auditing During Rollback

Each Pod after restore should log correlatable fields:

- Application version, build ID, and OCI image digest.
- Checkpoint ID, manifest digest, and runtime version.
- Pod UID, process run ID, and deployment revision.
- Database schema/migration version.
- Event schema version or relevant consumer group/offset.
- Start timestamps for rollback, restore, refresh, and readiness.
- Results of cache invalidation, credential refresh, lease acquisition, and reconciliation.
- Count of active workflows, retries, compensations, or DLQ entries.

Do not write tokens, secrets, or sensitive business payloads into logs. Use transaction IDs or correlation IDs to reconcile in systems with appropriate access controls.

## 19. Release Rollback Checklist

- [ ] Image digest and checkpoint artifact are matched to the exact release/build/runtime.
- [ ] Checkpoint manifest and signature are verified before restore.
- [ ] Cold-start fallback exists if no compatible checkpoint is available.
- [ ] Pods do not use stale business caches from the checkpoint heap.
- [ ] Current database schema remains compatible with the rollback release.
- [ ] Destructive/contract migrations have not run during the rollback window.
- [ ] Event/message schemas remain supported by old consumers.
- [ ] Consumer offsets, in-flight messages, and workflows are reconciled.
- [ ] Sockets, connection pools, tokens, DNS, and subscriptions are refreshed.
- [ ] Leases/leader election are reacquired with a new identity and fencing token.
- [ ] Readiness enables only after dependencies and business state are valid.
- [ ] Image rollback is not confused with data rollback.
- [ ] A plan for compensating transactions or PITR exists if data was corrupted.
- [ ] Rollback has been rehearsed and business invariants verified.
- [ ] Logs/audit link release, checkpoint, schema, and Pod identity.

## 20. References

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rollouts, revision history, and Pod template rollbacks.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): readiness, startup, and liveness in the Pod lifecycle.
- [CRaC Project](https://crac.org/): checkpoint/restore and managing resources before/after restore.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callbacks for managing resources across checkpoint and restore.
- [Martin Fowler — Parallel Change](https://martinfowler.com/bliki/ParallelChange.html): expand-contract technique for evolving schemas while maintaining compatibility during transition.
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/): identity and storage for stateful workloads.

A safe rollback reverts code to a known-stable release while respecting the current state of the system. Pair the image with a checkpoint of the exact build/runtime, keep schemas and message contracts compatible during the rollback window, and refresh caches, credentials, connections, leases, and workflow state from authoritative sources after restore. If business data was erroneously written, handle it with repair migrations, compensating transactions, or planned PITR separately; swapping an image or restoring an old heap cannot automatically undo side effects that have already happened.