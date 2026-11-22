# Leases, distributed locks, and expired owner terms

In a Java system running multiple replicas, sometimes only one process is allowed to perform a task at a time. For example: one replica running a data aggregation job, a worker owning a partition, a process executing a migration, or a scheduler publishing a periodic report. When multiple instances run concurrently, the system needs a coordination mechanism to determine who currently holds ownership of the work.

A distributed lock is commonly used to ensure only one party is authorized to execute a section of work. A lease is a time-limited form of ownership: the owner must renew before expiration; otherwise, the system can grant ownership to another process. However, an expired lease does not automatically stop the old process from continuing to run. A process that hangs, loses connectivity, or is checkpointed can wake up after ownership has already been transferred to another instance.

This is an especially important issue with CRaC (Coordinated Restore at Checkpoint). A process can be checkpointed while holding a lease, then stay dormant longer than the lease duration. During that time, the lease can expire and another replica can become the new owner. When the old process is restored, variables in the heap may still remember that it used to be the owner. If the process continues writing data or performing side effects based on stale information, two owners may act concurrently.

A safe design needs to treat a lease as time-limited authority verified by the coordination system, use a fencing token or owner epoch to reject operations from old owners, and require a restored process to verify or reacquire ownership before doing work.

## 1. What problem does a distributed lock solve?

Within a single JVM, synchronized, ReentrantLock, or Semaphore can coordinate threads of the same process. However, if the application runs across multiple machines or multiple containers, each process has its own memory. Using synchronized in replica A does not prevent replica B from entering the same logic section.

For example, a service has three replicas A, B, and C. All three check whether an end-of-day closing job needs to run. If only a boolean variable isRunning in the heap is used, each process has its own copy and all three can see false at the same time, and then run the job concurrently.

A distributed lock provides a shared coordination point for processes to contend for ownership. A lock protocol typically has the operations:

- Acquire: request ownership if there is no valid owner yet.
- Renew: extend existing ownership.
- Release: relinquish ownership.
- Validate: confirm that ownership is still valid.
- Expire: the coordination system automatically expires ownership after a period of time if not renewed.

A distributed lock is not merely a variable named locked. It requires an atomic protocol at the shared state store, along with rules for timeouts, renewal, network errors, and permission to perform side effects.

## 2. What is a lease?

A lease is time-limited ownership granted by a coordination system. When a client receives a lease, it has the right to perform a task during the granted interval. Before the lease expires, the client must successfully renew. If not renewed, ownership becomes invalid and the system can grant a new lease to another owner.

A lease typically contains:

- The protected resource or job name.
- Owner ID identifying the process or instance currently holding the lease.
- Lease ID or a random token to distinguish each grant.
- Expiration timestamp or TTL managed by the coordination system.
- Revision, generation, or fencing token if supported by the system.
- Information for renewal and release.

For example, worker A acquires a lease for daily-report for 30 seconds. A must renew before expiration. If A stops operating or cannot contact the lease service, ownership expires. Worker B can acquire a new lease and continue the work.

~~~text
Time --------------------------------------------------------->

Worker A:  Acquire lease A -------- Renew -------- Renew
Lease:     [------------------- valid --------------------]
Worker B:                                                  Acquire lease B
Lease:                                                      [----- valid ----]
~~~

TTL is the time-to-live duration of the lease. A short TTL helps detect an inactive owner faster but increases renewal frequency and sensitivity to network latency. A long TTL reduces renewal overhead but slows down ownership transfer when an owner truly dies.

A lease is not like an indefinite lock. With an indefinite lock, if the owner dies without releasing, the system can remain locked forever unless a recovery mechanism exists. A lease expires automatically after a period of time, but in return the owner must regularly prove that ownership is still valid.

## 3. Distinguishing lock, lease, and owner

These terms are often used interchangeably but have different meanings:

| Concept | Meaning | What to pay attention to |
|---|---|---|
| Lock | Mutual exclusion right over a resource or work section | Must have acquire/release rules and failed-owner handling |
| Lease | Time-limited ownership | Can expire when the client is paused or loses connectivity |
| Owner | Process or entity currently recognized by the system as holding authority | The owner in the heap may be stale compared to central state |
| Lease ID | Identifier of a specific lease grant | Used to renew/release the right lease |
| Owner epoch / generation | Generation number incremented on each ownership transfer | Helps distinguish a new owner from an old owner |
| Fencing token | Monotonically ordered token attached to ownership | Target system can reject operations from an old owner |

A lock is only useful if every party follows the protocol. If a process holds the variable isOwner = true in memory while the lease has already expired in the central system, that variable is no longer proof of ownership.

## 4. Why does a lease need a TTL?

In a distributed environment, a client can crash, lose network connectivity, or be stopped unexpectedly. Relying solely on explicit release operations could leave a lock abandoned after an incident.

TTL allows the coordination system to automatically reclaim authority after a period of time. The owner must renew periodically to prove it is still alive and still wants to keep ownership.

For example, with a 30-second TTL, the client can renew every 10 seconds. This is only an illustrative configuration; the renewal interval needs to account for latency, jitter, GC pause duration, system load, and reliability of the lease service.

Some principles:

- Renew before too little time remains.
- Use a timeout for each renewal.
- Do not treat a timeout as a successful renewal.
- If renewal success cannot be confirmed, stop starting new work.
- Do not wait until right before expiration to handle errors.
- After restore, verify the lease with the central system instead of relying on an old timestamp in the heap.

TTL does not guarantee that the old owner has stopped running when the lease expires. It only allows the coordination system to grant new ownership. The old owner may still be running on a network-isolated machine, or may be resumed after a long pause.

## 5. A distributed lock does not by itself stop an old owner from operating

Consider the scenario:

1. Worker A acquires a lease and starts processing partition 7.
2. A undergoes a long pause due to stop-the-world, VM hang, network disconnection, or being checkpointed.
3. A fails to renew the lease.
4. The TTL expires.
5. Worker B acquires a new lease for partition 7 and starts processing.
6. A is resumed or restored and continues from the next instruction in memory.

At this moment, A may still believe it is the owner because the variable in the heap has not been updated. B is also a valid owner according to the coordination system. If both write to the database or emit messages, the system can suffer overwrites, lost updates, or duplicate processing.

~~~text
Time --------------------------------------------------------------->

A:  Acquire A ---- work ------- CHECKPOINT/PAUSE ------------ RESTORE -- keep writing
Lease A:           [---------- expired ----------------]
B:                                            Acquire B ---- work ------->
Lease B:                                         [----------- valid ------->

Risk: A continues writing after B has become the new owner.
~~~

This is the stale owner (*expired previous owner*) situation. A TTL-based distributed lock without a way to protect the target system against a stale owner may not be enough to guarantee correctness.

## 6. CRaC makes stale lease risk more apparent

CRaC allows saving process state at checkpoint and restoring later. A process can be prepared, checkpointed, stored as an image in an artifact repository, and only restored minutes or hours later. During that time, the old lease can certainly expire.

Values in the heap may still reflect the time before checkpoint:

- owner = true.
- leaseId of the old acquire.
- old leaseExpiresAt.
- old lastRenewal.
- old fencingToken.
- Counters or state of an in-progress job.
- Waiting background threads that will resume when the process is restored.

These values must not be treated as proof of current authority. They are only historical data of the process at the time of checkpoint.

In particular, do not put a process into checkpoint while it still holds a lease for work requiring exclusivity. Before checkpoint, the application should stop accepting work, finish or pause at a safe boundary, relinquish the lease per protocol, and confirm persistent state. After restore, the process must acquire a new lease or verify a new lease granted for the exact current run.

If the checkpoint is a shared image used to create multiple instances, do not carry the lease ID or owner identity of the preparation process over to every replica. Each instance must have its own identity and contend for ownership through the coordination mechanism when needed.

## 7. What is a fencing token?

A fencing token is a monotonically ordered value issued each time ownership is transferred. It allows the target system to recognize whether an operation comes from a new owner or an old owner.

Suppose the system issues tokens:

- Worker A receives token 41.
- Lease A expires.
- Worker B receives token 42.
- A resumes and sends an operation with token 41.
- B sends an operation with token 42.

If the target system only accepts tokens greater than or equal to the latest recorded token, A's operation will be rejected because 41 is less than 42.

~~~text
Lease service:
  A acquires resource -> token 41
  A expires
  B acquires resource -> token 42

Protected database:
  highest token = 42

Request from A (token 41) -> REJECTED
Request from B (token 42) -> ACCEPTED
~~~

The fencing token must be checked where side effects are performed, such as a database, storage service, or resource-protecting API. Issuing tokens only at the lock service without passing and checking them at the target system does not protect the data.

A random UUID can identify a lease but has no ordering. It does not replace a fencing token when it is necessary to know which owner is newer. Fencing tokens need to be issued in monotonic order by a source with appropriate consistency.

## 8. Owner epoch and owner term

An owner epoch (also called generation or term) is a generation number associated with ownership. Each time ownership is newly granted or transfers owners, the system increments the epoch.

Example:

| Grant | Owner | Epoch |
|---|---|---:|
| Grant 1 | worker-A | 101 |
| Grant 2 | worker-B | 102 |
| Grant 3 | worker-C | 103 |

Epoch helps distinguish two runs of the same instance. For example, container worker-A can restart or restore; the new run still has the same instance name but must receive a new epoch. Do not use hostname or pod name as proof that it is the same ownership term.

Some systems store the epoch in a database or metadata service. Each write operation needs to include the epoch and is rejected if the epoch is lower than the current value. For a resource with multiple owners, the epoch needs an explicit scope, such as per resource key or partition.

## 9. Protecting the database with a fencing token

The highest accepted token can be stored alongside the resource's state record. Each write operation needs to send the token. The database only permits the operation if the token is not older than the already accepted token.

Example state table:

~~~sql
CREATE TABLE resource_owner (
    resource_key VARCHAR(200) PRIMARY KEY,
    fencing_token BIGINT NOT NULL,
    payload      VARCHAR(2000)
);
~~~

An update operation can check the token within the same transaction:

~~~sql
UPDATE resource_owner
SET payload = :payload
WHERE resource_key = :resourceKey
  AND fencing_token <= :token;
~~~

However, the condition above alone may not be enough if the operation does not simultaneously update fencing_token to the new token. One approach is to update both token and payload in the same statement/transaction:

~~~sql
UPDATE resource_owner
SET fencing_token = :token,
    payload = :payload
WHERE resource_key = :resourceKey
  AND fencing_token <= :token;
~~~

If the number of updated rows equals 0, the token is stale or the resource does not exist. The application needs to treat this as an ownership-loss error and stop processing.

In systems with multiple operations, there should be a dedicated fencing table or a row representing the resource. Ensure that the token check and side effects are executed atomically within the same transaction. If the application checks the token first and then updates data in a separate transaction, an old owner can interleave between the two steps.

Example JDBC logic:

~~~java
public void writeWithFence(
        Connection connection,
        String resourceKey,
        long fencingToken,
        String payload) throws SQLException {

    String sql = """
        UPDATE resource_owner
           SET fencing_token = ?,
               payload = ?
         WHERE resource_key = ?
           AND fencing_token <= ?
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, fencingToken);
        statement.setString(2, payload);
        statement.setString(3, resourceKey);
        statement.setLong(4, fencingToken);

        int updated = statement.executeUpdate();
        if (updated != 1) {
            throw new StaleOwnerException(
                    "Lease owner is stale for " + resourceKey);
        }
    }
}
~~~

This is an illustration for a single protected state row. If the actual operation writes to multiple tables, the updates need to share the same transaction and the same fencing condition. Also define how rows are initialized, how competing operations are serialized, and how equal tokens are handled per the protocol.

## 10. Generating monotonically increasing tokens

Fencing tokens must be issued in order. A database sequence, the revision of a consistent data store, or a version number provided by a coordination system can be used.

Example with a sequence in the database:

~~~sql
CREATE SEQUENCE lease_fencing_seq START WITH 1 INCREMENT BY 1;
~~~

When issuing a new lease, the coordinator obtains a new sequence value and attaches it to the lease. The token is returned to the owner together with the lease ID.

Do not increment tokens in an AtomicLong variable of each JVM because each replica has its own counter. Also do not use local timestamps as tokens if node clocks can drift or move backward. Tokens need to be issued from a shared source with appropriate ordering and consistency.

If using a revision or transaction ID from a coordination system, verify that the value increases according to the exact resource scope. A global revision may fit; a version that increases only per key may also fit if the target system compares per key accurately.

## 11. Safe acquire/renew/release pattern

A lease client should provide a clear API and not let business code manually manipulate fragmented commands. General model:

~~~java
public interface LeaseService {
    Lease acquire(String resourceKey, Duration ttl);
    Lease renew(Lease lease, Duration ttl);
    void release(Lease lease);
    Lease current(String resourceKey);
}

public record Lease(
        String resourceKey,
        String ownerId,
        String leaseId,
        long fencingToken,
        Instant expiresAt) {
}
~~~

This is an illustrative application-defined interface, not a standard Java or CRaC API. acquire() must perform authorization atomically. If the resource currently has a valid lease, it must return a result indicating no authority or a corresponding error. renew() and release() need to verify the lease ID/owner token so an old client does not accidentally renew or delete a new owner's lease.

Release should be conditional. Do not delete a lock based solely on the resource key because a new lease may have already been granted to another owner. Compare the current lease ID or owner token before releasing.

A lease object in the heap is only a copy of previously granted information. Before each critical operation, the system needs to enforce fencing at the target or verify authority per protocol. Having a Lease object remaining in memory must not be treated as sufficient.

## 12. Example of using a lease with a fencing token in Java

A service processing a partition can acquire a lease and use the token on every write:

~~~java
public final class PartitionWorker {
    private final LeaseService leases;
    private final PartitionStore store;
    private final String ownerId;

    public PartitionWorker(
            LeaseService leases,
            PartitionStore store,
            String ownerId) {
        this.leases = leases;
        this.store = store;
        this.ownerId = ownerId;
    }

    public void runPartition(String partition) {
        Lease lease = leases.acquire(partition, Duration.ofSeconds(30));
        if (lease == null) {
            return;
        }

        try {
            processRecords(partition, lease.fencingToken());
        } finally {
            leases.release(lease);
        }
    }

    private void processRecords(String partition, long token) {
        for (Record record : loadPendingRecords(partition)) {
            store.apply(partition, token, record);
        }
    }
}
~~~

In the example, PartitionStore.apply() must check the token at the state store. If the token is stale, it must reject the operation. Checking the token only once at the start of runPartition() is not enough: the lease can expire in the middle of processing multiple records.

A real worker also needs to renew the lease while running. If renewal fails or the result is uncertain, the worker should stop accepting new records and not emit further side effects. If an operation is in progress, the target system still must check the fencing token to prevent a stale owner.

## 13. Lease renewal and handling renewal failures

Leases are usually renewed periodically. The client should not treat renewal as an optional background task that can fail while work continues indefinitely.

A renewal loop can be structured as follows:

1. Receive a lease with a TTL from the coordination system.
2. Schedule renewal with a safety margin before the expiration time.
3. Send renewal with the current lease ID.
4. If renewal is confirmed, update state and expiration time.
5. If renewal is rejected because the lease no longer belongs to the owner, mark ownership as lost.
6. If timeout or connection loss occurs, treat ownership state as uncertain and stop starting new side effects.
7. Only continue when the coordination system confirms the lease is still valid or grants a new lease.

Not every renewal error means the lease has definitely expired. For example, the response might be lost after the server already renewed. However, the client cannot assume on its own that renewal succeeded. Query status or execute a safe recovery protocol. While unconfirmed, stop work requiring exclusivity.

A ScheduledExecutorService can run the renewal loop, but must account for paused threads, GC pauses, CPU load, slow networks, and checkpoints. Do not merely schedule renewal every 10 seconds and assume the callback is guaranteed to run right on time.

## 14. Clocks, TTL, and time after checkpoint

Leases are time-based, yet machines do not necessarily have identical clocks. System.currentTimeMillis() is a wall clock that can change due to NTP or administrative operations. System.nanoTime() is suitable for measuring time intervals inside a running JVM, but its value uses an arbitrary origin and is not a global timestamp for long-term storage or cross-machine comparison.

Some principles:

- Let the authoritative lease system decide whether a lease has expired.
- Do not use client-generated timestamps as the sole source for granting authority.
- Do not store a deadline in the heap and trust it remains accurate after an undetermined checkpoint duration.
- Use a monotonic clock for internal timeouts within an appropriate execution span; do not use it as a distributed token or timestamp.
- After restore, re-read lease state from the coordination system and acquire or renew per protocol.
- Account for clock skew if the protocol requires the client to estimate expiration itself; keep a sufficiently large safety margin.

If a process is checkpointed for 20 minutes while the lease TTL is 30 seconds, the lease has long since expired according to the coordination system. There is no way to infer that ownership is still valid merely from an expiresAt variable restored from the heap.

## 15. Preparing for checkpoint while holding a lease

The simplest and safest approach for many workloads is not to create a checkpoint while the process still owns a lease for an exclusive task. Before checkpoint, the application can:

1. Stop accepting new work.
2. Stop dispatching new records or tasks to workers.
3. Wait for in-flight work to complete at a safe boundary.
4. Commit progress or save the workload's own business checkpoint.
5. Relinquish the lease via conditional release.
6. Confirm no worker is allowed to perform side effects anymore.
7. Allow CRaC to create the checkpoint.

After restore, the process must not resume automatically with the old lease ID. It needs to register its current identity, acquire a new lease, and receive a new fencing token. Only after having valid authority may work begin.

If a workload cannot stop completely, a recoverable pause/resume protocol needs to be designed. However, pausing a process via checkpoint is not a lease mechanism. The external coordination system continues counting TTL while the process is not running.

## 16. Using a CRaC Resource to release and reacquire a lease

A CRaC Resource can be used to coordinate the lease lifecycle. The pre-checkpoint callback asks workers to stop work and release the lease. The post-restore callback prepares new state; acquiring the lease can be performed after dependencies and identity are ready.

Example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LeaseCheckpointResource implements Resource {
    private final LeaseCoordinator coordinator;

    public LeaseCheckpointResource(LeaseCoordinator coordinator) {
        this.coordinator = coordinator;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        coordinator.stopClaimingWork();
        coordinator.drainInFlightOperations();
        coordinator.persistProgress();
        coordinator.releaseCurrentLease();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        coordinator.refreshInstanceIdentity();
        coordinator.clearRestoredLeaseState();
        coordinator.prepareForNewLease();
    }

    public interface LeaseCoordinator {
        void stopClaimingWork() throws Exception;
        void drainInFlightOperations() throws Exception;
        void persistProgress() throws Exception;
        void releaseCurrentLease() throws Exception;
        void refreshInstanceIdentity() throws Exception;
        void clearRestoredLeaseState() throws Exception;
        void prepareForNewLease() throws Exception;
    }
}
~~~

The LeaseCoordinator methods are an application-defined contract, not a CRaC API. The example intentionally does not yet acquire the lease in afterRestore() because many applications need to wait for service discovery, database, credentials, or worker pools to become ready first. A lifecycle coordinator can acquire the lease after dependencies are recovered and before opening traffic for the workload.

If beforeCheckpoint() cannot drain work or release the lease, the callback needs to report an error so the checkpoint process does not continue in an unclear state. If restore fails to obtain a lease, the instance can still run the web health endpoint but must not accept the portion of work requiring owner authority. Readiness needs to accurately reflect that role.

## 17. Creating a checkpoint from a preparation process and restoring multiple replicas

A checkpoint image can be used as a starting point for multiple instances if the JDK and platform support that model. However, the image should not contain an active lease or the owner identity of the preparation process.

Suppose the preparation process has a lease for scheduler-global with token 500. If the image is restored into 10 replicas, all 10 processes can start with the same token value 500 in the heap. They must not treat that as 10 valid leases. The original lease is only granted to one owner at a time and may already have expired before the image is used.

Appropriate design:

- Do not acquire a lease during the base image creation phase.
- If the application needs to run warm-up for an exclusive component, use a separate environment or resource that does not cause production side effects.
- Clear owner/lease state from the base configuration before checkpoint.
- Each replica creates its own owner ID after restore.
- Each replica only processes work after acquiring a valid lease.
- Every write operation carries the fencing token issued for the current ownership.
- If only one replica is allowed to run a global task, the remaining replicas wait for the lease instead of running autonomously based on a heap variable.

For partition-processing workers, multiple replicas can run concurrently, yet only the owner of each partition is allowed to process that partition. Leases and tokens need to be scoped per partition; do not use a single global variable to represent ownership of the entire workload if the protocol partitions ownership by key.

## 18. Systems commonly used to implement leases

Leases can be built on multiple storage or coordination systems. Each system has its own guarantees and limitations.

| Platform | Common implementation | Points to verify |
|---|---|---|
| Relational database | Row lock, advisory lock, lease row with expires_at and version | Transaction boundary, isolation, server time, atomic update, fencing |
| Redis | SET NX with TTL, ownership token, and compare-and-delete operation | Failover/replication, lock loss on primary switch, separate fencing token |
| ZooKeeper | Ephemeral node and version/zxid | Session expiration, watcher, reconnect, generation |
| etcd | Lease attached to key and revision | Lease revoke/expiry, revision, quorum, and retry |
| Consul | Session and lock delay | Session invalidation, behavior on disconnection, fencing at target |
| Kubernetes | Lease object in coordination API | Renewal deadline, resourceVersion, leader election, fencing in target system |

No single choice automatically protects every side effect. Read the documentation of the platform version, understand the consistency model, failover behavior, and limitations during network partitions. A distributed lock service can grant a new lease while the old owner is still running; fencing at the target system remains an essential layer of protection.

## 19. Database lease example

A simple approach is to store resource key, owner ID, expiration, and fencing token in a table. Acquire needs to execute atomically: only claim authority if the current lease has expired or has no owner. Each new grant must increment the token.

Illustrative table:

~~~sql
CREATE TABLE distributed_lease (
    resource_key  VARCHAR(200) PRIMARY KEY,
    owner_id      VARCHAR(200),
    lease_id      VARCHAR(200),
    expires_at    TIMESTAMP WITH TIME ZONE,
    fencing_token BIGINT NOT NULL
);
~~~

Acquire idea on a transaction-supporting database:

1. Begin transaction.
2. Lock the corresponding row using SELECT ... FOR UPDATE or an appropriate atomic mechanism.
3. Use the database's time to compare expires_at.
4. If the lease is still valid, do not grant authority.
5. If the lease has expired, increment fencing_token, assign the new owner_id, lease_id, and expires_at.
6. Commit and return the token to the client.

SQL pseudocode can be expressed as a conditional update statement, though syntax and support depend on the database. General example:

~~~sql
UPDATE distributed_lease
   SET owner_id = :owner,
       lease_id = :leaseId,
       expires_at = CURRENT_TIMESTAMP + :ttl,
       fencing_token = fencing_token + 1
 WHERE resource_key = :resource
   AND (expires_at IS NULL OR expires_at <= CURRENT_TIMESTAMP);
~~~

If one row is updated, the client can retrieve the new token within the same transaction or via RETURNING if the database supports it. If no row is updated, the resource currently has a valid lease or the key has not been initialized. Initial row creation must be handled so there is no race between two clients inserting simultaneously.

Renew must check both owner ID and lease ID:

~~~sql
UPDATE distributed_lease
   SET expires_at = CURRENT_TIMESTAMP + :ttl
 WHERE resource_key = :resource
   AND owner_id = :owner
   AND lease_id = :leaseId
   AND expires_at > CURRENT_TIMESTAMP;
~~~

If the update count equals 0, the client must not consider itself renewed. Release must also be similarly conditional and must not delete another owner's lease.

This is an illustrative model. In an actual system, check timestamp syntax, isolation, transactions, indexes, how the new fencing token is retrieved, and behavior during database failover. Using database-side time avoids having each client compare TTL using different local clocks.

## 20. Redis locks and limitations to understand

A common pattern with Redis is setting a key only if it does not already exist and attaching a TTL:

~~~text
SET lock:partition-7 <random-owner-token> NX PX 30000
~~~

NX requires setting only if the key does not exist; PX sets time-to-live in milliseconds. If the command succeeds, the client is permitted to hold the lock for the TTL according to the active protocol.

When releasing, do not use DEL lock:partition-7 unconditionally. Owner A may expire, B already acquired a new lock, and then A runs late and mistakenly deletes B's lock. An atomic operation is needed that deletes the key only if the current value still equals A's owner token, usually implemented with a Lua script or a supported compare-and-delete mechanism.

However, a random owner token only helps release the right lease; it does not by itself prevent A from sending stale write operations to the database after the lease expires. If protection against stale owners is needed, a monotonically increasing fencing token and token checks at the target system are required. Redis replication and failover must also be understood: a lock write may not be durably replicated before primary failure, depending on configuration. Do not assume the simple pattern is a strong linearizable lock protocol in every topology.

## 21. Leader election and leases

Leader election selects one process as leader in a group. Leases are commonly used to bound the leader's term: the leader must renew, and when the lease expires another member can be elected.

However, leader election only answers who is considered leader according to the coordination system. It does not automatically stop the old leader from continuing to issue commands to the target system. A critical system should attach a term/epoch to every command or write operation, so downstream rejects commands from an old term.

For example, a scheduler leader can issue a run-job command with term 77. After a new leader is elected with term 78, the database or job coordinator only accepts term 78 or higher. If the old process resumes and issues a term 77 command, the command is rejected.

For Kubernetes Lease, resourceVersion and the leader election record help coordinate leader selection. Yet the application still needs to design how to pass fencing/epoch to the resources the leader controls. Do not treat the fact that a pod once held a Lease object as proof it still has authority after a long checkpoint interval.

## 22. Leases, distributed locks, and transactions

Locks do not replace transactions. A lock can prevent two valid owners from starting work simultaneously, but does not guarantee database operations inside commit atomically. Conversely, a database transaction can guarantee an atomic group of operations but does not itself coordinate ownership of a long-running job across multiple processes.

Some ways to combine:

- Acquire a lease before starting an exclusive task.
- Use a fencing token in data-updating transactions.
- Save progress and business changes in the same transaction whenever possible.
- Use an idempotency key to handle retries after uncertain results.
- Release the lease after persistent state has been updated.
- If the lease expires mid-transaction, the fencing check at the database must prevent the old owner from committing side effects.

For long-running work, do not hold a database transaction open for the entire lease duration. Split the work into batches or small units, each batch having a short transaction and checking the fencing token.

## 23. Rules when a lease expires or renewal is uncertain

When the client cannot confirm that the lease is still valid, the safe behavior is to stop starting new side effects. Specifically:

1. Mark local ownership state as UNCERTAIN or LOST.
2. Stop accepting additional records/jobs.
3. Cancel or stop workers safely.
4. Do not send new write commands with the old token.
5. If an operation is waiting for a result, look up status by operation ID or let an idempotency mechanism handle retries.
6. When connectivity returns, query or acquire a new lease.
7. Only continue when holding a new token and downstream accepts that token.

Do not self-renew by adding TTL to expiresAt in the heap. Only the coordination server can confirm renewal. If a response times out, the server may have renewed without the client receiving it; query status or acquire per protocol instead of guessing.

## 24. Testing stale owners with checkpoint/restore

A useful test must reproduce the situation where an old owner is resumed after a new owner has already claimed authority.

Scenario:

1. Worker A acquires a lease for resource X and receives fencing token 10.
2. A processes a few records and writes token 10 to the database.
3. Checkpoint or pause A long enough for the lease to expire.
4. Worker B acquires a new lease and receives token 11.
5. B writes a change using token 11; the database accepts and stores the new token.
6. Restore or resume A.
7. A attempts to write using token 10.
8. The database must reject A's operation.
9. A must transition to the lost-ownership state and not continue the work.

Also test additional scenarios:

- Renewal timeout even though the server already renewed.
- Lease expires while the client is waiting for a response from the database.
- Two workers acquiring almost simultaneously.
- Owner releases after the lease has already been granted to someone else.
- Process restores from an image containing an old lease ID/token.
- Multiple replicas restore from the same image and concurrently try to acquire one resource.
- Database or lock service failover while granting a lease.
- Client clock skew or change.
- Downstream receives an old request after the new owner has already written data.

The result needs to confirm not only that the lock service reports the right owner. The target system must also reject operations from the stale owner.

## 25. Lease observability and operations

Metrics that help detect unstable lease operation:

| Metric | Meaning |
|---|---|
| Acquire success/failure | Rate of successful acquisitions and contention |
| Renew success/failure/timeout | Health of the renewal loop |
| Lease age and remaining TTL | How long the lease has existed and remaining time per authoritative source |
| Ownership changes | Number of owner transfers or epoch increments |
| Fencing rejection count | Number of operations rejected due to stale token |
| Work stopped after lease loss | Number of times a worker stopped when authority could not be confirmed |
| Restore-to-reacquire duration | Time from restore until a new lease is acquired |
| Stale operation count | Number of requests from old owners rejected by downstream |

Logs should include resource key, owner ID, suitably masked lease ID, fencing token, epoch, acquire/renew/release outcome, and correlation ID. Avoid logging credentials or secret tokens used for authentication.

A useful alert is repeated lease renewal failures or a sudden spike in fencing rejections. These may be signs of GC pauses, checkpoint/restore, network partitions, an overloaded lock service, or a TTL configured too short.

## 26. Common design mistakes

**Treating the isOwner variable in the heap as the source of truth.** This variable does not automatically change when the lease expires in the central system. Always verify authority and use fencing downstream.

**Using only TTL without a fencing token.** An old owner can resume and write after a new lease has been granted. Downstream must reject stale tokens.

**Unconditional lock release.** An old owner can delete another owner's new lease. Release must compare lease ID/owner token atomically.

**Using client timestamps as fencing tokens.** Clock skew or backward jumps can break ordering. Use an incrementing sequence/revision from a shared source.

**Continuing to work when renewal times out.** A timeout does not prove the lease is still valid. Stop new side effects until authority is verified.

**Checkpointing while still holding a lease.** The restored process may carry stale owner state. Release the lease before checkpoint and reacquire after restore.

**Using the same owner ID for every restored replica.** Replicas can be mistaken for the same entity. Each run needs its own identity; tokens must be issued by the system.

**Checking fencing only at the start of a job.** A lease can expire mid-job. Check the token at every write or transaction boundary.

**Assuming leader election automatically protects downstream.** An old leader can continue issuing commands. Attach term/epoch to commands and check at the target resource.

**Holding transactions as long as the lease duration.** This increases lock contention and database risk. Use short transactions and check the fencing token.

## 27. Lease design checklist for Java applications using CRaC

- [ ] Do resources requiring exclusivity have a clear lock or lease key?
- [ ] Does the lease-granting system guarantee atomicity and appropriate consistency?
- [ ] Have TTL, renewal interval, timeout, and safety margin been chosen based on real load?
- [ ] Does a renewal timeout lead to an uncertain ownership state and stop new work?
- [ ] Does release check lease ID/owner token to avoid deleting another owner's lease?
- [ ] Does each ownership grant have a monotonically increasing fencing token or owner epoch?
- [ ] Does downstream check the token in the same transaction as the side effect?
- [ ] Does the process release its lease and drain work before checkpoint?
- [ ] After restore, does the process discard old lease state and acquire a new lease?
- [ ] Do multiple replicas restored from the same image have distinct owner IDs?
- [ ] Are wall-clock or heap variables avoided as the sole source for confirming whether a lease is still valid?
- [ ] Can a job stop safely at a batch boundary when the lease is lost?
- [ ] Do progress and side effects have idempotency or durable transactions?
- [ ] Has stale owner resume been tested after a new owner has already been granted authority?
- [ ] Can metrics and logs trace acquire, renew, release, epoch, and fencing rejections?

## Conclusion

A lease is time-limited ownership; distributed locks help processes coordinate so they do not claim the same authority at the same time under the chosen protocol. However, when an owner is paused, loses connectivity, or is checkpointed longer than the TTL, the lease can expire and authority can be granted to another process. The old owner can still resume with un-updated state in the heap.

CRaC makes this situation require intentional handling: do not checkpoint while holding exclusive authority, drain work and release the lease before checkpoint; after restore, create a new identity and acquire a new lease. For critical data, use a monotonically increasing fencing token or owner epoch and require the target system to check the token in the same transaction as side effects. That way, even if the old process wakes up late, it cannot overwrite the new owner's results.