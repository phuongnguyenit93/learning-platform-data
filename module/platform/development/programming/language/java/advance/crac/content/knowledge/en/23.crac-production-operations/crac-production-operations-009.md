# Controlling Duplication of Tasks, Consumers, and Singleton-Role Components

A CRaC checkpoint saves the state of a JVM process at a point in time. When the same image is restored into multiple instances, each instance resumes from a copy of the checkpointed heap and static state. The replicas may carry the same counters, status flags, schedules, consumer metadata, UUIDs generated before checkpoint, or “I am currently the leader” information.

This creates an operational risk: multiple processes may concurrently perform a task that before checkpoint only one process executed. For example, two replicas running nightly reports simultaneously, multiple consumers processing the same message, two instances refreshing a shared cache together, or multiple processes believing they hold the leader role.

CRaC does not by itself provide a cluster-wide singleton coordination mechanism. A `static` field, singleton bean, `synchronized` block, or `AtomicBoolean` only coordinates threads within a single JVM. When an image is restored multiple times, each JVM has an independent copy of those states. Ownership of shared tasks must be decided by an external coordination system, such as a database, distributed coordination service, broker, or scheduler with a claim/lease mechanism.

The goal of this lesson is to design the lifecycle so that each instance after restore:

- Identifies its own new incarnation.
- Pauses and releases ownership before checkpoint.
- Rejoins the consumer group or leader election after restore.
- Runs singleton tasks only when holding current ownership.
- Processes messages/jobs safely under retries or duplicate execution.
- Does not open readiness before coordination state has been verified.

## 1. Why Can Restoring Multiple Times Duplicate Behavior?

Imagine the application has a singleton in the heap:

~~~java
public final class BackgroundCoordinator {
    private static boolean leader = true;
    private static long nextJobNumber = 1200;
}
~~~

Before checkpoint, only one JVM is running and `leader` is `true`. If the image is restored across three workers, each worker has its own copy of this field:

| Instance | `leader` in heap | `nextJobNumber` in heap |
|---|---:|---:|
| Restore A | true | 1200 |
| Restore B | true | 1200 |
| Restore C | true | 1200 |

The three processes do not share the same `static` field. Each process believes it is the leader and may issue the same next job number. A `synchronized` method also locks only within one JVM, not across two different JVMs.

Similarly, a restored scheduler or consumer object does not automatically know that another replica was just restored too. If each replica keeps emitting messages or running schedules, the behavior will be multiplied.

### Heap Copies and External Ownership

| State | When Restoring Multiple Instances |
|---|---|
| Java objects and static fields | Each JVM has its own copy |
| In-memory counters | May start from the same value |
| UUIDs generated before checkpoint | May be reused across multiple instances |
| `isLeader` or `isActive` flags | Each replica may hold the same value |
| Schedulers and task definitions | Each instance may continue registering tasks |
| Old consumer clients and metadata | May no longer be valid; must rejoin per API |
| External database locks or leases | May have expired or been granted to another instance |
| External files/ports/sockets | May be claimed by another instance or no longer valid |

Key takeaway: a snapshot can duplicate **in-memory intent and data**, but it does not validly duplicate ownership in external systems. Ownership must be re-verified.

## 2. Distinguishing a JVM Singleton from a Cluster Singleton

The term “singleton” is often used in two different senses:

**JVM singleton** ensures one object instance within a class loader or application context. It is useful for sharing configuration, local caches, or coordinators across threads of the same process.

**Cluster singleton** ensures only one instance across multiple processes is permitted to perform a role at a time. It requires an external coordination mechanism such as leases, leader election, or database transactions/claims.

A framework singleton bean does not automatically become a cluster singleton. If there are five replicas, there are typically five singleton beans.

### Classifying Work Before Designing

Not every background task needs a single leader. Classify them by requirement:

| Work Type | Suitable Model | Example |
|---|---|---|
| Each instance must run independently | Per-instance | Flush local metrics, clean local cache |
| Only one instance cluster-wide | Cluster singleton | Run migrations, generate system-wide reports |
| Partitioned by partition/key | Partition ownership | Kafka consumers, shard workers |
| Multiple instances process concurrently without duplicate impact | Competing consumers + idempotency | Send outbox emails, process orders |
| Can rerun if missed | Durable scheduled job | Reconciliation, retry queues |
| Role changes over time | Leader/lease | Failover coordination, shared resource refresh |

Misclassification leads to solutions that are too weak or overly complex. For example, there is no need to elect a leader for a per-process metric flush task; conversely, an `AtomicBoolean` cannot guarantee that only one process in the cluster runs database migrations.

### Ownership Matrix

Before integrating CRaC, create a table documenting:

| Component | Ownership Scope | Source of Truth | Behavior Before Checkpoint | Behavior After Restore |
|---|---|---|---|---|
| Scheduler singleton | Cluster-wide | Lease/database | Pause, drain, release lease | Reacquire lease before scheduling |
| Consumer group | Partitions in group | Broker coordinator | Stop poll, process/commit or abort cleanly | Create new consumer and rejoin |
| Job worker | Job ID | Durable job store | Stop claiming new jobs, finish or release claim | Re-claim with new lease/attempt |
| Leader controller | One role | Coordination service | Release role or let lease expire cleanly | Elect/select new leader |
| Cache refresh | Key or cache partition | Lease/key ownership | Stop refresh and release lease | Refresh only claimed keys |
| Outbox dispatcher | Record/partition | Database claim | Stop fetching new records | Re-claim incomplete records |

Each component needs an owner responsible for its lifecycle and a source of truth to verify ownership.

## 3. Generating a New Incarnation ID After Restore

A process may keep the same service name, replica configuration, or checkpoint ID, yet each restore is a new execution incarnation. An incarnation ID helps distinguish logs, metrics, leases, and actions across replicas.

Do not generate a unique incarnation ID once before checkpoint and retain it in the heap. If the image is restored multiple times, all replicas could receive that same value.

Generate a new ID after restore using an entropy source or an ID generator independent of the checkpointed heap. For systems requiring strict uniqueness within a business scope, use an ID issued by a database/coordination service or combine the checkpoint ID with a unique restore-attempt nonce provided by the orchestrator.

Examples of identifying information:

| ID | Meaning | Can Be Preserved Across Checkpoint? |
|---|---|---|
| Service ID | Logical identifier of the application | Yes |
| Replica/slot ID | Replica position per orchestrator | May change per deployment |
| Checkpoint ID | Source image being restored | Yes |
| Incarnation ID | A specific execution run of the process | Must be regenerated after restore |
| Job ID | A durable logical job | Kept stable |
| Job attempt ID | One execution attempt of a job | Generated anew for each attempt |
| Lease/fencing token | Ordered ownership credential | Reissued by an external authority |

### Example Generating an Incarnation ID

~~~java
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

public final class ProcessIdentity {

    private final AtomicReference<UUID> incarnation =
            new AtomicReference<>();

    public UUID startFresh() {
        UUID id = UUID.randomUUID();
        incarnation.set(id);
        return id;
    }

    public UUID afterRestore() {
        UUID id = UUID.randomUUID();
        incarnation.set(id);
        return id;
    }

    public UUID current() {
        UUID id = incarnation.get();
        if (id == null) {
            throw new IllegalStateException("Process identity is not initialized");
        }
        return id;
    }
}
~~~

The example uses `UUID.randomUUID()` after restore to illustrate generating a new value instead of retaining a UUID from the snapshot. If the threat model or platform has special entropy requirements, use an identity/nonce issued by the runtime or orchestration system. Do not use PID as the sole incarnation ID: PIDs can be reused and can differ across PID namespaces.

Attach the incarnation ID to logs, traces, controlled metric labels, lease owners, and job attempts. Do not use it in place of stable business IDs such as order IDs or message IDs.

## 4. Pausing Schedulers and Job Workers Before Checkpoint

Schedulers are one of the easiest places for duplicate tasks to arise. A scheduler running inside the JVM may store task definitions, trigger state, executors, and next execution times in the heap. When restoring multiple replicas, each replica may continue registering the same schedule.

### Why Can Tasks Run Multiple Times?

Common causes:

- Each instance starts the scheduler and registers the same cron expression.
- A task was scheduled before checkpoint; after restore, the task is registered a second time.
- An active job is checkpointed mid-run, and then multiple replicas continue the same job.
- A fixed-rate schedule tries to catch up missed executions from while the process was paused.
- The old scheduler lease expired, but the `isLeader` flag in the heap is still true.
- Two instances claim the same job simultaneously because the claim operation is not atomic.

Do not treat scheduler state in the heap as the source of truth for permission to run jobs. Schedules can be stored in a database or scheduler service; each execution needs an independent claim/lease.

### Pre-Checkpoint Sequence

For schedulers with shared side effects, the sequence should:

1. Close admission for new jobs.
2. Stop triggers from firing additional runs.
3. Wait for active jobs to finish within a chosen deadline, or stop/cancel them per policy.
4. Persist durable progress state if the job is resumable.
5. Commit results or release the claim/lease.
6. Close executors/clients that need to be recreated.
7. Allow checkpoint only when state is quiescent.

Do not checkpoint while a job holds an unpersisted transaction, lock, or side effect without durable state if the application lacks an explicit recovery mechanism.

### Post-Restore Sequence

- Generate a new incarnation ID.
- Register the instance with the scheduler/coordination service.
- Reacquire ownership only if the role requires a singleton.
- Load schedules from a durable source or register schedules with a unique key.
- Do not blindly catch up missed runs in bulk.
- Enable job triggers only after claims/leases and dependencies are ready.

### Policy for Missed Schedules

While a process is paused, cron or timer fire times may pass. Make an explicit decision:

| Policy | Behavior | Suitable When |
|---|---|---|
| Skip | Drop missed executions, wait for next scheduled run | Work only needs to run periodically and newer data will be processed later |
| Coalesce | Merge multiple missed runs into a single execution | Refresh/reconciliation tasks do not need to run for every tick |
| Backfill | Re-execute each missed interval | Each period is a business unit that must be processed |
| Resume | Continue job from a business checkpoint | Jobs have durable progress and support resumption |

This policy must live in the scheduler/job store or business logic, not depend on a restored timer object.

### Fixed-Rate and Fixed-Delay

`scheduleAtFixedRate` attempts to maintain cadence against scheduled fire times; if a task runs slowly, executions may bunch up or catch up depending on the scheduler. `scheduleWithFixedDelay` measures the wait interval after the previous execution completes. After restore, both require verifying how the library handles clocks, missed executions, and running tasks.

For critical business tasks, prefer durable schedules with job IDs and execution state in a durable store. In-JVM timers should serve only as a mechanism to wake workers, not as the sole place storing schedules.

## 5. Claiming Jobs Using a Durable State Store

A worker should claim jobs via atomic operations. For example, a database has a job table with states `READY`, `RUNNING`, `DONE`, lease expiration, and attempt number.

A claim must verify in the same transaction:

- The job is in an eligible status to be claimed.
- Any old lease has expired or there is no current owner.
- Attempt/generation is incremented atomically.
- The owner is recorded using the incarnation ID.
- A lease deadline is set.

Illustrative pseudo-SQL:

~~~sql
UPDATE scheduled_job
SET owner_id = :incarnation_id,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt = attempt + 1,
    status = 'RUNNING'
WHERE job_id = :job_id
  AND status IN ('READY', 'RUNNING')
  AND (lease_until IS NULL OR lease_until < CURRENT_TIMESTAMP)
RETURNING job_id, attempt, lease_until;
~~~

Interval and `RETURNING` syntax vary by database. What matters is that the claim is atomic, checks lease expiration, and returns the exact granted attempt. Do not execute separate `SELECT` then `UPDATE` without locking or concurrency control; two workers could both read the job as ready.

Upon completion, the worker may mark the job done only if it still owns the current attempt/generation. If the lease expired and the job was granted to another worker, the old worker must not overwrite the newer result.

### Leases and Heartbeats

Timed leases allow the system to reclaim ownership if a process dies or loses connectivity. A worker must renew its lease before expiration. If renewal fails, the worker must stop initiating new side effects and handle in-flight state per policy.

Do not use the JVM's local clock as the sole source for lease expiration if the database/coordination service has its own clock. Use time and atomic operations from the lease-owning authority.

### Fencing Tokens Against Stale Owners

A lease alone is not enough if an old worker is paused for a long time, its lease expires, a new worker acquires the lease, and then the old worker resumes execution. Both could believe they hold ownership.

A fencing token is a monotonically increasing generation number issued by an external authority each time ownership is granted. Every write operation to a shared resource must carry the token; the target resource rejects any token lower than the latest accepted token.

Example:

| Owner | Lease generation | Outcome |
|---|---:|---|
| Instance A | 41 | Granted initial ownership |
| Instance A paused | 41 | Lease expires |
| Instance B | 42 | Granted new ownership |
| Instance A resumes | 41 | Write operation rejected due to stale token |

Fencing is effective only if the resource receiving the operation validates the token. A counter inside the JVM cannot replace a fencing token issued by an external authority.

## 6. Consumers Must Rejoin the Group After Restore

Message consumers typically hold network, heartbeat, assignment, offset, and processing buffer state. Those states may no longer be valid after a checkpoint interval. Do not assume a consumer object in the heap can safely continue polling.

With consumer groups like Kafka, the broker coordinator manages membership and partition assignments. After restore, the consumer must be recreated or recovered per the client-supported lifecycle, then rejoin the group and receive new assignments. Other members may have continued processing while this instance was paused.

### Before Checkpoint

A common workflow:

1. Stop receiving new records by pausing or stopping polling via the client API.
2. Wait for in-flight records to finish processing within a deadline.
3. Commit offsets after side effects have completed per application semantics.
4. If completion is not possible, leave records for reprocessing and ensure handlers are idempotent.
5. Close the consumer client using the library API.
6. Release threads/event loops and connections owned by the client.

Do not commit offsets solely to speed up checkpointing. Committing before durable side effects can lose processing if the process stops. Conversely, committed side effects without committed offsets can lead to reprocessing; handlers require idempotency or appropriate transactions.

### After Restore

- Create a new consumer client via supported APIs.
- Use the current group ID and client configuration.
- Re-authenticate workload identity/credentials.
- Join the group and wait for partition assignments.
- Check offsets and in-flight state per policy.
- Open processing only after the consumer has assignments and dependencies are ready.

Do not manually restore partition assignments from a checkpointed field. The broker coordinator is the source of truth for current assignments.

### Rebalances and Pause Duration

While the process is paused, heartbeats may stop and the broker may evict the member from the group. Other consumers will take over partitions. Upon restore, the old instance returns as a new member or a rejoining member depending on the client/protocol.

This can trigger rebalances and temporarily increase latency. If many instances restore simultaneously, they can trigger a large wave of joins/rebalances. Rate-limit rollouts, use backoff/jitter, and monitor rebalance count, assignment duration, and consumer lag.

### Offsets and Side Effects

There is no single commit order suitable for every application. For example:

| Order | Risk |
|---|---|
| Commit offset before side effect | Process dying after commit can cause records to be skipped |
| Side effect before committing offset | Process dying before commit can cause records to be reprocessed |
| Commit in the same transaction supported by broker/database | Can provide stronger semantics within supported scope |

Even when using broker transactions or exactly-once features, side effects to systems outside that transaction still require idempotency or separate coordination mechanisms. Do not claim “exactly once” solely based on enabling a consumer flag.

## 7. Making Handlers Idempotent

During restore, rebalance, or retry, the same message/job may be redelivered. An idempotent handler ensures multiple executions do not produce unintended duplicate business effects.

A common approach is using the message ID or business key as an idempotency key and storing the processing outcome in the same transaction as the business update.

Example pseudo-code:

~~~java
public void handle(OrderCreated event) {
    transactionTemplate.executeWithoutResult(tx -> {
        boolean firstDelivery =
                processedMessageRepository.insertIfAbsent(event.messageId());

        if (!firstDelivery) {
            return;
        }

        orderService.applyCreatedEvent(event);
    });
}
~~~

`insertIfAbsent` must be implemented with a unique constraint or atomic operation inside the same database transaction. If you only check `exists` and then insert, two consumers could both pass the check.

### Idempotency Keys Must Be Stable

Do not generate a new message ID each time a handler receives a redelivered record. The ID must be generated at the message source and remain stable across retries. The attempt ID may change, but the business/message ID must stay the same.

### Outbox Pattern

If a consumer needs to update the database and emit a downstream message, an outbox persists business changes and outgoing events in the same database transaction. A dispatcher can claim each outbox record; if sent twice, the receiving consumer must be idempotent.

CRaC does not replace transactions, outboxes, or deduplication. It only changes how a process resumes after a checkpoint.

## 8. Coordinating Singleton-Role Components

Components typically designed as “single-instance only”:

- Leader controller or cluster coordinator.
- Scheduler running migrations or system-wide reports.
- Shared cache warmer/refresh job.
- Outbox dispatcher or cleanup worker.
- Service discovery publisher holding a lease.
- Worker managing an external resource or an exclusive device.
- Component managing a shared port, file lock, or socket path.

For each component, answer:

1. Is uniqueness scoped to one JVM, one host, one namespace, or the whole cluster?
2. Who grants ownership?
3. Does ownership have a lease/expiration?
4. How must the owner renew it?
5. Can the target resource reject a stale owner using a fencing token?
6. What happens when the owner dies, pauses, or loses network connectivity?
7. After restore, must the component re-elect or re-register?

### Leader Election

Leader election must rely on a coordination service or database with appropriate consistency semantics. A `leader=true` variable in the heap is merely a snapshot of a past decision.

After restore:

- Clear stale leader state from runtime decisions.
- Rejoin the election or request a new lease.
- Receive a new fencing token/generation.
- Perform leader actions only while the lease remains valid.
- Stop acting immediately when the lease is lost or cannot be renewed.

### Distributed Locks

Locks with TTLs enable recovery when an owner disappears, but a paused process can resume after the lock expires. Therefore, write operations must carry a fencing token or version condition on the target resource.

Do not hold a lock object in the heap and assume the external lock still belongs to the instance after restore. Verify the owner and expiration with the lock service.

### File Locks and Ports

File locks and port bindings are operating system resources. When restoring multiple replicas on the same host/namespace, multiple processes may contend for the same path or port. When restoring on another host, the corresponding resource may or may not exist.

Before checkpoint, close and release resources per API. After restore, rebind/reacquire them and handle conflict errors. Do not use a checkpointed boolean to conclude that a port/file lock still belongs to the process.

## 9. Coordinating Lifecycle with a Single Coordinator

When multiple components depend on one another, have an explicit coordinator controlling the order. For example, the scheduler must not run before a lease is granted; consumers must not process before credentials and group assignments are ready; readiness must not open before mandatory components are active.

A simple state machine:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> QUIESCING: beforeCheckpoint
    QUIESCING --> CHECKPOINT_READY: tasks drained, leases released
    CHECKPOINT_READY --> RESTORING: image restored
    RESTORING --> REJOINING: new incarnation
    REJOINING --> ACTIVE: consumers and roles verified
    REJOINING --> NOT_READY: recovery failed
    NOT_READY --> REJOINING: bounded retry
~~~

The states in the diagram are application-managed states, not a mandatory CRaC enum. Use a state machine to prevent initialization methods from being invoked twice and to log progress clearly.

### A Single Resource Coordinating Components

The example below illustrates a single coordinator. The interfaces represent adapters for the scheduler, consumer group, lease service, and readiness gate.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.util.UUID;

public final class RuntimeCoordinationResource implements Resource {

    public interface Identity {
        UUID createNewIncarnation() throws Exception;
    }

    public interface Scheduler {
        void pauseTriggersAndDrain() throws Exception;
        void startIfLeader(long fencingToken) throws Exception;
    }

    public interface Consumers {
        void stopPollingDrainAndClose() throws Exception;
        void createJoinAndVerify() throws Exception;
    }

    public interface Leadership {
        void release() throws Exception;
        LeadershipGrant acquireIfAvailable(UUID incarnation) throws Exception;
    }

    public interface Readiness {
        void close();
        void open();
    }

    public record LeadershipGrant(boolean leader, long fencingToken) {
    }

    private final Identity identity;
    private final Scheduler scheduler;
    private final Consumers consumers;
    private final Leadership leadership;
    private final Readiness readiness;

    private UUID incarnation;
    private boolean active;

    public RuntimeCoordinationResource(
            Identity identity,
            Scheduler scheduler,
            Consumers consumers,
            Leadership leadership,
            Readiness readiness) {
        this.identity = identity;
        this.scheduler = scheduler;
        this.consumers = consumers;
        this.leadership = leadership;
        this.readiness = readiness;
        Core.getGlobalContext().register(this);
    }

    public synchronized void initializeForFreshStart() throws Exception {
        readiness.close();
        activateNewIncarnation();
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        readiness.close();
        active = false;
        scheduler.pauseTriggersAndDrain();
        consumers.stopPollingDrainAndClose();
        leadership.release();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        readiness.close();
        active = false;
        activateNewIncarnation();
    }

    private void activateNewIncarnation() throws Exception {
        incarnation = identity.createNewIncarnation();

        // Rejoin the consumer group; the broker assigns current partitions.
        consumers.createJoinAndVerify();

        // A cluster-wide role is granted by an external authority.
        LeadershipGrant grant = leadership.acquireIfAvailable(incarnation);
        if (grant.leader()) {
            scheduler.startIfLeader(grant.fencingToken());
        }

        active = true;
        readiness.open();
    }
}
~~~

This is an illustrative structure, not an adapter ready for direct use in every framework. In a real application:

- `pauseTriggersAndDrain()` must block new tasks and wait for active tasks up to a deadline.
- `stopPollingDrainAndClose()` must handle in-flight records and offsets according to consumer semantics.
- `release()` must release external leases/locks and handle fencing tokens.
- `createJoinAndVerify()` must wait for the consumer to receive necessary assignments, not merely construct the object.
- `acquireIfAvailable()` must use an atomic operation of the coordination service.
- `startIfLeader()` must pass the fencing token to all relevant write operations.
- If any step fails, readiness stays closed and the error must be surfaced for the runtime/orchestrator to handle.

In the example, the consumer group is joined by every instance, while the scheduler runs only when the instance receives a leadership grant. If the consumer is also a cluster singleton, require acquiring the role before joining or before starting to poll.

### Why Consolidate Into One Coordinator?

If multiple independent Resources close/open interdependent components separately, callback ordering can become an implicit assumption. Using one coordinator makes the order explicit: close readiness, drain work, close consumers, release leases; after restore create incarnation, join consumers, reacquire roles, start the scheduler, and finally open readiness.

If still using multiple Resources, use an ordering mechanism supported by the runtime/framework documentation and test the actual execution order. Do not rely on incidental registration order if it is not guaranteed.

### Handling Mid-Way Failures

If consumers closed but reacquiring leadership fails, do not open readiness for features requiring a leader. If secret refresh fails before consumer recreation, do not let consumers start processing. Each step needs a timeout, cleanup, and deterministic error state.

Do not catch an exception and still open readiness. If the system supports background recovery, readiness must stay closed until mandatory components complete. Retries must use backoff, jitter, and deadlines; avoid creating reconnect loops that overload dependencies.

## 10. Avoiding Duplicate Scheduler and Listener Registration

Another cause is initializing components multiple times. When objects are restored, the framework does not necessarily re-invoke constructors or startup hooks like a fresh JVM. However, restore callbacks may invoke task registration logic again if the code does not distinguish state.

### Common Pitfalls

- Calling `schedule()` in both the constructor and `afterRestore`.
- Creating a new executor without stopping the old executor.
- Registering listeners/event handlers again after restore.
- Opening two polling loops on the same consumer wrapper.
- Adding duplicate shutdown hooks or recurring timers.
- Inserting the same job definition into the scheduler store multiple times.

### Using a Stable Registration Key

For durable schedulers, use a stable logical key for the job definition, such as `(service, jobName, scheduleVersion)`. Register via an upsert/unique constraint operation instead of inserting on every process start.

Do not use the incarnation ID as the job definition key if the goal is a single cluster-wide schedule. The incarnation ID identifies the process; the job key identifies the logical schedule. Separate the two concepts so each restore does not create a new schedule.

### In-JVM Guards Are Only Local Protection

You can use an `AtomicBoolean` or state machine to prevent a single JVM from registering the same listener twice:

~~~java
if (started.compareAndSet(false, true)) {
    scheduler.start();
}
~~~

This is useful protection against competing threads within the same process. It does not guarantee another JVM is not performing the same work. Cluster ownership must still be confirmed externally.

## 11. Handling Jobs Running at Checkpoint Time

Checkpointing in the middle of a side effect can create ambiguous state. For example, the process sent a payment command to an external system without recording the result yet; after restore, the job might resend the command.

### Identifying the Business Commit Point

For each job, determine:

- Where does the job start and what state is persisted durably?
- What side effects can occur outside the transaction?
- Is there an idempotency key?
- Are results committed before or after acknowledgment?
- If the process stops between two steps, will the job retry, resume, or require reconciliation?

Do not treat the fact that the heap was checkpointed as proof that business progress was committed. The heap stores only process state; transactions/databases/brokers are the durable source of truth.

### Choosing How to Handle

| State When Preparing Checkpoint | How to Handle |
|---|---|
| Job not started | Do not claim new jobs after admission closes |
| Job running, can finish quickly | Drain within deadline and commit result |
| Long-running job with business checkpoint | Save durable progress and stop safely |
| Job emitted side effect but result not recorded | Use idempotency key or reconciliation |
| Cannot determine if side effect occurred | Move to a reconciliation-needed state; do not blindly rerun |

### Do Not Hold Business Locks Across a Checkpoint

If a job holds a database transaction or distributed lock during checkpoint, the pause duration may cause the transaction to time out or the lease to expire. Before checkpoint, finish/roll back transactions and release locks per protocol. After restore, start a new transaction and claim fresh ownership.

## 12. Multiple Instances Restoring the Same Image

The most critical scenario is the same checkpoint image being restored simultaneously across multiple hosts or pods.

Example:

~~~text
                 checkpoint image
                  /      |      \
                 /       |       \
             restore A restore B restore C
                |         |         |
             JVM A     JVM B     JVM C
                |         |         |
                +---- external coordination ----+
                          |
                  lease / group / job store
~~~

The instances may start with identical:

- Static counters and cache state.
- Scheduler registration state.
- Consumer group ID and client metadata.
- Leader flags and lease metadata stored in the heap.
- UUID or random generator state initialized before checkpoint.
- Internal queues and pending task lists.

Therefore, testing a single restore on one machine is not enough. Restore the same image into at least two instances and verify that external systems grant ownership only per policy.

### Controlled Rollout

When multiple replicas restore:

- Limit the number of instances restored concurrently.
- Avoid having all consumers join the group simultaneously if the broker cannot handle a large rebalance.
- Use backoff/jitter when acquiring leases or secrets.
- Monitor leader counts, consumer assignments, and job claims.
- Keep readiness closed until the instance finishes rejoining.
- Ensure scale-down also releases leases and stops consumers safely.

Do not assume all instances must become leaders. Typically, only one instance holds the lease for a role; the remaining instances stay in follower or standby state.

## 13. Monitoring Ownership and Tasks After Restore

If you monitor only the number of running processes, it is very hard to detect two instances executing the same role concurrently. Metrics and logs must reflect actual ownership.

### Metrics to Include

| Metric | Meaning |
|---|---|
| `process_incarnation_info` | Identifies the running incarnation |
| `cluster_role_leader` | Whether the current instance holds the leader role |
| `leadership_lease_valid` | Whether the lease is still valid and verified |
| `leadership_fencing_token` | Current generation issued by the authority |
| `scheduler_active` | Whether the scheduler is accepting triggers or paused |
| `scheduler_inflight_jobs` | Number of running jobs |
| `job_claim_conflicts_total` | Number of failed claims because another worker claimed it |
| `job_duplicate_suppressed_total` | Number of duplicate executions blocked by idempotency |
| `consumer_group_rebalance_total` | Number of consumer group rebalances |
| `consumer_assigned_partitions` | Number of partitions assigned to the instance |
| `consumer_lag` | Message processing lag |
| `consumer_inflight_records` | Number of records currently being processed |
| `restore_rejoin_duration_seconds` | Time to rejoin groups/roles after restore |
| `readiness_state` | Whether the instance is ready to accept traffic |

Metric names are suggestions. Avoid putting very high-cardinality incarnation IDs, job IDs, or message IDs into metric labels. Use logs/traces for detailed IDs and metrics for aggregate status.

### Structured Logs

Each coordination event should log:

- `checkpoint_id`
- `restore_attempt_id`
- `incarnation_id`
- `service_id`
- `role_name`
- `lease_generation` or `fencing_token`
- `consumer_group_id`
- `assigned_partitions`
- `job_id` and `attempt_id` when needed
- `event` and `result`

Do not write tokens, passwords, or secrets in these fields. Record the credential version ID if rotation investigation is needed.

### Critical Alerts

- More than one leader exists for the same role.
- Two incarnations hold an invalid lease generation simultaneously.
- Lease expired while a worker continues producing side effects.
- Singleton scheduler runs without a leadership grant.
- Consumer processes records before receiving partition assignments.
- Consumer lag or rebalances spike sharply after restore.
- A new job attempt starts while the previous attempt's outcome is still undetermined.
- Readiness opens while the coordinator is still in `REJOINING` state.

If the system has multiple singleton roles, count leaders per `role_name`, not just the total leader count across the cluster.

## 14. Testing Multi-Replica Restores

Tests must simulate a scenario where a single checkpoint image is restored into multiple independent processes. Running a single instance cannot detect duplicated static flags, counters, or schedulers.

### Basic Test Scenario

1. Start the application and let the scheduler, consumer, and leader role run.
2. Record the incarnation ID, leader/lease generation, consumer assignments, and job state.
3. Close admission, drain jobs, pause the scheduler, stop consumers, and release leases.
4. Create the checkpoint.
5. Restore the same image into at least two independent instances.
6. Verify each instance generates a distinct incarnation ID.
7. Verify the broker coordinator distributes partitions according to the current group.
8. Verify only one instance holds the lease for a singleton role.
9. Verify the scheduler runs only on the authorized owner.
10. Send messages/jobs with fixed IDs and verify business side effects occur only once.
11. Stop the current owner and verify lease/failover works.
12. Resume the old instance after the lease was granted to a new owner; verify the fencing token blocks stale operations.

### Scenario Matrix

| Scenario | What to Verify |
|---|---|
| Restore a single instance | Consumer rejoins, lease is granted, and scheduler works properly |
| Restore two instances from the same image | Incarnations differ; singleton has only one owner |
| Restore many instances concurrently | Coordination service and broker handle join/claim bursts |
| Lease expires while process is paused | Old instance cannot write with an old fencing token |
| Consumer evicted from group | Restored instance rejoins and receives current assignments |
| Message processed but offset uncommitted | Redelivery produces no duplicate side effects |
| Offset committed before side effect | Tests confirm no business work is lost |
| Job stopped mid-side-effect | Retry/reconciliation uses idempotency key |
| Scheduler registered twice | Registration key/unique constraint blocks duplicate schedules |
| Restore after cron fire time passed | Skip/coalesce/backfill per defined policy |
| Checkpoint while job is running | Admission/drain prevents ambiguous business state snapshot |
| Leadership service unavailable | Readiness stays closed; instance does not self-assume leadership |
| Scale down instance | Consumer closes, lease releases, and job claims are handled |
| Restore on different host | No dependence on old PID, hostname, or local locks |

### Verify Side Effects, Not Just Logs

A “job started” log on one instance and “job started” on another shows two starts occurred, but does not yet prove two side effects occurred. Conversely, a single log does not prove the business action happened only once.

Verify results in target systems:

- Exactly one business record per idempotency key.
- A job state transitions to DONE exactly once.
- One valid lease owner at a given time.
- Fencing tokens increase monotonically.
- Partition assignments are never processed concurrently by two consumers in violation of the protocol.
- Outbox/events are emitted according to the designed semantics.

## 15. Anti-Patterns When Using CRaC with Background Work

| Anti-Pattern | Why It Is Dangerous | How to Handle |
|---|---|---|
| Keeping `isLeader=true` in a static field | Every restored replica may believe it is leader | Re-elect or reacquire lease |
| Using `synchronized` as a distributed lock | Lock is effective only within a single JVM | Coordination service/database |
| Using an in-heap counter to issue job IDs | Replicas may issue identical values | External sequence/ID generator |
| Keeping consumer object and continuing to poll | Network session and assignments may be stale | Close and create/rejoin a new consumer |
| Committing offsets before side effects | Processing may be lost if process stops | Appropriate transactions/idempotency |
| Executing side effect then committing offset without idempotency | Redelivery may produce duplicate effects | Deduplication/outbox/transactions |
| Holding a lease across checkpoint | Lease may expire during the pause | Release and reacquire; use fencing |
| Using TTL locks alone | Old owner may resume after a pause | Fencing token verified by target resource |
| Registering cron in every callback | Each restore may create another schedule | Durable schedules and registration keys |
| Catching up all missed ticks | Creates a job burst after restore | Policy-driven skip/coalesce/backfill |
| Opening readiness as soon as JVM resumes | Consumers/leases/clients may not be ready | Open only after coordinator verification |
| Using PID as a durable instance ID | PIDs can be reused and differ across namespaces | New incarnation ID |

## 16. Operations Checklist

### Before Checkpoint

- [ ] Each task is classified as per-instance, cluster singleton, partitioned, or competing consumer.
- [ ] Source of truth for ownership is identified for each role.
- [ ] Admission is closed and new work claiming is stopped.
- [ ] Scheduler triggers are paused and running tasks are drained.
- [ ] In-flight messages/jobs are handled per transaction and idempotency policies.
- [ ] Claims/leases are committed or released with proper semantics.
- [ ] Consumers are stopped and clients/threads requiring recreation are released.
- [ ] Leadership/leases are released and fencing generation is recorded.
- [ ] Never checkpoint with business locks/transactions lacking a recovery path.

### After Restore

- [ ] Generate a new incarnation ID.
- [ ] Refresh workload identity/credentials if clients require it.
- [ ] Rejoin consumer groups and await current assignments.
- [ ] Reacquire leases/leadership from external authority.
- [ ] Obtain a new fencing token and pass it to write operations.
- [ ] Start the scheduler only when the role is granted.
- [ ] Register schedules with stable logical keys to prevent duplicates.
- [ ] Define how missed schedules are handled.
- [ ] Open readiness only after all mandatory components are verified.

### Testing and Observability

- [ ] Restored the same image into multiple instances.
- [ ] Incarnation IDs differ across replicas.
- [ ] Only one owner holds each cluster singleton role.
- [ ] Consumer groups rejoin and rebalance as expected.
- [ ] Handlers/jobs are idempotent for redeliveries/retries.
- [ ] Fencing blocks stale owners after lease expiration.
- [ ] Metrics/logs clearly record role, incarnation, lease generation, and job attempt.
- [ ] Alerts exist for duplicate leaders, duplicate jobs, and premature readiness.
- [ ] Tested scale-down, restarts, network partitions, and concurrent restores.

## 17. Design Principles to Maintain

CRaC enables creating multiple instances from a prepared JVM state, but it does not turn in-heap state into distributed ownership. Anything local such as static fields, counters, scheduler objects, or consumer metadata can be duplicated alongside the image. Components with singleton roles must obtain ownership from an external authority after every restore.

Use incarnation IDs to identify each process, leases/leader election to grant ownership, fencing tokens to block stale owners, consumer groups to distribute partitions, idempotency to protect side effects, and durable job state to handle retries/resumption. Before checkpoint, close admission, drain work, and release ownership. After restore, create a new identity, rejoin, reacquire, and open readiness only when current state has been verified.