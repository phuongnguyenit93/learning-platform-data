# Testing Multiple Replicas to Detect Duplicate IDs and Repeated Side Effects

A CRaC checkpoint can be used as a starting point for multiple Java processes. This helps replicas skip time-consuming initialization, but also has an important consequence: every replica can start from the same heap state. Values generated before checkpoint such as instance IDs, local counters, random generator seeds, scheduler state, consumer metadata, or leader flags may be cloned across multiple replicas.

When replicas operate concurrently, bugs can appear as duplicate IDs, two instances both believing they own a resource, both processing the same message, or both executing the same side effect. These bugs are often hard to reproduce when testing only a single restore. You need to spawn multiple replicas from the same checkpoint image, run them concurrently, and observe the outcomes in authoritative systems such as the database, broker, payment provider, or distributed coordinator.

The goal of the test is to prove two things:

- Each replica has its own identity and resources within the appropriate scope, while service identity and shared data remain consistent.
- A business operation produces only the number of side effects permitted by its contract, even when multiple replicas receive the same request/message or restore together from a single image.

## 1. Why Test Multiple Replicas from the Same Checkpoint?

Testing a single JVM checkpoint followed by one restore only proves a single path. It does not expose values cloned across multiple processes. When two or more replicas restore the same image together, their initial state can be identical even though each process has its own memory space.

For example, an application creates IDs during startup:

~~~java
public final class InstanceState {
    static final String INSTANCE_ID = UUID.randomUUID().toString();
    static long nextSequence = 50_000;
    static boolean leader = true;
}
~~~

If the checkpoint is created after these fields have been initialized, multiple replicas may receive the same INSTANCE_ID, the same nextSequence, and the same leader value. From that point on:

- Logs and metrics cannot distinguish which replica produced an event.
- Local counters can issue the same ID across replicas.
- Multiple instances can perform work meant for the leader at the same time.
- Consumers may share a member identity or session metadata.
- Schedulers may run the same job on all replicas.
- Local resources may contend over the same file path, socket path, or lock name.

Not every shared value is a bug. Service names, schema versions, consumer groups, or immutable configuration are often intentionally shared. Tests must know which values must match and which values are required to differ.

### 1.1. Distinguishing ID Types

| Identifier type | Scope | Expectation across replicas |
|---|---|---|
| Service identity | One logical service | Usually identical |
| Workload identity | One authorized workload | May be identical per platform policy |
| Replica/instance ID | One running replica | Must differ if used to distinguish replicas |
| Process incarnation ID | One specific run/restore | Must be new per incarnation if required by the system |
| Consumer member ID | One member in a group | Must follow the broker's contract; usually unique per member |
| Business entity ID | Order, payment, account | Unique according to business rules |
| Idempotency key | One retryable operation | Must remain stable for the same operation, even when retried via another replica |
| Lease/fencing token | Ordered ownership | Issued and verified by the coordinator; not taken from the snapshotted heap |

A test that only checks “every ID must be different” is too coarse. For example, two replicas of orders-api need the same service identity to be routed as one service, yet must have different replica IDs. An order-creation request needs to keep the same idempotency key across retries; generating a new key on each replica can cause the same operation to be executed twice.

### 1.2. Distinguishing Duplicate IDs from Repeated Side Effects

Duplicate IDs and repeated side effects are related, yet they are two distinct bugs:

- A duplicate ID is when two independent entities receive the same identifier within a scope requiring uniqueness.
- A repeated side effect is when a single business operation causes multiple external state changes.

A system can generate unique IDs and still send the same payment command twice. Conversely, a request can be properly deduplicated while logs still show duplicate instance IDs, making investigation difficult. Both categories need separate tests.

## 2. Designing a Multi-Replica Test Environment

A reliable test needs to use the same checkpoint image for multiple replicas. Each replica must run as an independent process, with its own runtime resources, and be observed using a test identifier.

### 2.1. Creating a Canonical Checkpoint

Workflow:

1. Build the application with a pinned CRaC JDK/runtime and dependencies.
2. Start one instance with the test configuration.
3. Complete the warm-up intended to be saved in the image.
4. Bring the application to a safe state according to pre-checkpoint callbacks.
5. Create the checkpoint image.
6. Record the digest, JDK build, engine, configuration, and dependency versions.
7. Keep the canonical image unchanged to reuse for every replica in the same test run.

Do not create a separate checkpoint per replica if the goal is to detect cloned state. Doing so can hide bugs because each image might generate a different identity or seed.

### 2.2. Restoring the Same Image into Multiple Processes

A harness can launch N restored processes from the same image:

~~~text
checkpoint-image/
  replica-a/
  replica-b/
  replica-c/
~~~

The directories above only illustrate separate workspaces for each restore; how the runtime references the image depends on the engine. If the engine supports restoring from the same source multiple times, keep the original image immutable and provide separate destination/runtime state for each process per the engine's documentation.

Each replica needs:

- A separate process/container.
- A separate writable directory or overlay.
- Separate logs or logs with a replica tag.
- A separate port, or dynamic port binding followed by advertising the actual port.
- Separate replica metadata if provided by the platform.
- Separate connections and sessions per application policy.

Do not let multiple replicas write to the same writable directory designed for a single process. Sharing an immutable checkpoint image is different from sharing a runtime directory, logs, or temporary files.

### 2.3. Synchronizing Start Timing

Race conditions often only appear when replicas perform operations nearly simultaneously. After restore, use a barrier in the test harness:

1. Launch all replicas.
2. Wait for each replica to report that bootstrap has completed and it is in a ready-for-test state.
3. Send a shared start signal.
4. All replicas concurrently generate IDs or process the same type of work.
5. Collect results from each replica and authoritative data sources.

If launched sequentially, one replica may finish registering or acquire a lock before the next replica starts; race conditions will rarely appear.

### 2.4. Increasing Difficulty in a Controlled Way

Run multiple variants:

- Two replicas to check basic bugs.
- Three or more replicas to increase collision probability.
- Concurrent restore and staggered restore.
- Multiple repeated restores from the same image.
- Short pauses, long pauses, and pauses exceeding TTLs/leases.
- One replica starting slowly or losing connectivity during bootstrap.
- One replica being killed and recreated from the same image.

Do not run only once and conclude there are no collisions. Some bugs depend on scheduling, entropy, timestamps, or concurrent load. Repeat tests an adequate number of times based on risk and record the iteration count.

## 3. Building the Test Harness

The harness orchestrates the checkpoint image, launches replicas, synchronizes activity, and collects evidence. It can be built with shell scripts, Testcontainers, JUnit, a Kubernetes Job, or a dedicated test controller.

### 3.1. Harness Responsibilities

The harness should:

- Verify that the checkpoint image exists and has the expected digest.
- Launch N replicas from the same image.
- Assign replica names for observation purposes, without using those names as proof that the application itself generates proper identities.
- Wait for bootstrap and readiness.
- Collect service ID, replica ID, and incarnation ID from a safe diagnostic endpoint.
- Synchronize operations through a barrier.
- Send concurrent requests/messages.
- Query the database, broker, and simulated side-effect systems.
- Check unique ID counts, record counts, and actual side-effect counts.
- Save logs, metrics, traces, configuration, and runtime information for the test run.
- Clean up resources after the test completes.

### 3.2. Not Confusing Test Labels with Application Identity

The harness may name processes replica-a and replica-b. However, the application itself must publish the identity generated or verified after restore. If an endpoint merely returns an environment variable assigned by the harness, the test has not proved that the application's identity generation logic works.

Collect both:

- The test label assigned by the harness to identify which process produced the output.
- The application identity generated by the application or obtained from platform metadata.

Then verify the mapping between the two values. Test labels do not need to be secrets; do not pass real credentials in environment variables just to tag replicas.

### 3.3. Orchestration Pseudocode

~~~java
List<ReplicaHandle> replicas =
        checkpointHarness.restoreMany(checkpointImage, 4);

try {
    for (ReplicaHandle replica : replicas) {
        replica.awaitBootstrap(Duration.ofMinutes(2));
    }

    List<ReplicaIdentity> identities = replicas.stream()
            .map(ReplicaHandle::readIdentity)
            .toList();

    assertUniqueReplicaIds(identities);

    TestBarrier barrier = new TestBarrier(replicas.size());
    List<Future<TestResult>> results = replicas.stream()
            .map(replica -> executor.submit(() -> {
                barrier.awaitReady();
                return replica.performConcurrentOperation();
            }))
            .toList();

    List<TestResult> completed = collect(results);
    assertBusinessInvariants(completed);
    assertExternalEffects(checkpointHarness.effectStore());
} finally {
    replicas.forEach(ReplicaHandle::stop);
}
~~~

The types CheckpointHarness, ReplicaHandle, ReplicaIdentity, TestBarrier, and TestResult are hypothetical components of the test harness, not built-in CRaC APIs. The pseudocode illustrates the testing sequence: restore the same image, wait for bootstrap, read identities, synchronize operations, and verify results from authoritative sources.

## 4. Testing Duplicate IDs

Do not inspect IDs only in logs. Retrieve IDs from the application and verify them in the scope where the IDs are used. If an ID is a database key, a database unique constraint is stronger evidence than a list of IDs collected inside the JVM.

### 4.1. Instance ID and Process Incarnation ID

Scenario:

1. Create a checkpoint after the application has initialized.
2. Restore at least two replicas from the same image.
3. Call the diagnostic endpoint or collect metadata from each process.
4. Verify that service identity is the same if that is the contract.
5. Verify that replica identity is different.
6. If each restore must have its own incarnation, verify that the incarnation ID also differs.
7. Repeat with the same image and multiple restore rounds.

Criteria:

- No two running replicas share the same replica ID within a scope requiring uniqueness.
- IDs are generated after restore or derived from current metadata.
- Logs and traces distinguish each replica.
- When a replica restarts/restores again, the incarnation ID changes if required by policy.

### 4.2. Local Counters in the Heap

A snapshotted static counter or AtomicLong may start from the same value across multiple replicas. The test should have all replicas allocate a range of IDs concurrently:

~~~java
long id = localSequence.incrementAndGet();
idRepository.insert(id, replicaIdentity);
~~~

If two replicas both start from sequence 1000, both can issue 1001. The database must have a unique constraint on the ID to catch collisions rather than silently overwriting.

Tests need to:

- Restore multiple replicas from the same image.
- Synchronize all replicas before issuing IDs.
- Have each replica allocate a large number of IDs in a short time.
- Write all IDs to a table with a unique constraint.
- Verify there are no duplicates and no swallowed insert errors.
- Check the authoritative ID source rather than only checking changes to local variables.

If the application needs global IDs, use a database sequence, an ID service, an appropriate UUID/ULID, or non-overlapping allocated ID ranges. Synchronization within one JVM does not solve collisions across multiple processes.

### 4.3. UUIDs and Random Generators

Do not conclude that UUIDs will definitely collide or definitely not collide solely from replicas restoring the same image. The outcome depends on the implementation, provider, entropy state, and how the JDK handles generators across checkpoint. Test on the exact JDK/runtime and provider being deployed.

Tests should:

- Generate many UUIDs after restore across all replicas.
- Record the counts and check for collisions in the dataset.
- Verify the SecureRandom provider and entropy policy.
- Test multiple restores, multiple processes, and concurrent start times.
- Do not use a fixed seed or a lone timestamp as the sole source.

A test finding no collisions is only empirical evidence within the sampled scope, not a mathematical proof of uniqueness. If absolute uniqueness is required, use a constraint or an authoritative allocator.

### 4.4. Snowflake IDs and Node IDs

Snowflake-style ID generators typically combine a timestamp, a node/worker ID, and a sequence. If the node ID is configured or generated before checkpoint and then cloned, two replicas can generate the same ID within the same millisecond.

Test:

- Restore multiple replicas from the same image.
- Have each replica generate IDs concurrently within the same time window.
- Check each replica's node ID.
- Write IDs to storage with a unique constraint.
- Test clock moving backward or identical timestamps.
- Test sequence overflow and how the generator waits for the next millisecond.

The node ID needs to be uniquely assigned by a coordinator or derived from platform metadata under a clear contract. Do not use a snapshotted worker ID number as the permanent identity for all replicas.

### 4.5. Consumer Member IDs

Brokers typically distinguish the consumer group from group members. The group ID can be identical because multiple replicas join the same group; member IDs or generation/session metadata must follow the broker's rules.

Test:

- Restore multiple consumers from the same checkpoint.
- Have all of them join the same group nearly simultaneously.
- Observe member IDs, generations, and partition assignments managed by the broker.
- Verify that no member is rejected due to duplicate identity.
- Stop one member and restore it again; verify group rebalance and valid new membership.

Do not hard-code member IDs before checkpoint if the broker requires each member to have a distinct identity. Prefer letting the client/broker generate or negotiate member identities according to the protocol.

### 4.6. Local Resource IDs and Paths

Some IDs are not UUIDs yet still must be separate:

- Temporary file names and spool directories.
- Unix domain socket paths.
- PID files and lock files.
- Consumer checkpoint files.
- Cache namespaces or local database directories.
- Internal ports and endpoints.

Tests need to verify that each replica writes to its own path or uses a shared mechanism with proper locking. If using dynamic ports, verify the actual bound port. Do not assume a snapshotted port value can still be bound across multiple processes.

## 5. Testing Repeated Side Effects

Repeated side effects typically occur at uncertainty boundaries: the application sent a request but does not know whether the server executed it; a message was processed but the offset was not committed; a transaction committed but the response did not reach the client; a scheduler restarted and re-ran an already executed occurrence.

### 5.1. Identifying Side Effects to Protect

List actions that mutate external state:

- Creating orders, payments, refunds, or reservations.
- Sending emails, SMS, or webhooks.
- Creating resources via external APIs.
- Sending messages/events to a broker.
- Updating a database or object storage.
- Recording offsets, acknowledgments, or job completion.
- Running periodic tasks with side effects.

For each action, define whether “once” is counted per request, per business operation, per message ID, or per scheduled run. You cannot verify API call counts without understanding that API's idempotency contract.

### 5.2. Idempotency Keys Must Be Stable Across Retries

A request retried by another replica must still carry the same idempotency key if it represents the same business operation.

HTTP example:

~~~http
POST /payments
Idempotency-Key: pay-order-8392
Content-Type: application/json

{
  "orderId": "order-8392",
  "amount": 125000
}
~~~

The payment service needs to store the key alongside the result and reject or return the previous result when the same key is sent again. If each replica generates a new key upon restore, the provider will treat them as different operations and may execute multiple payments.

Criteria:

- The same business operation retains the same idempotency key across checkpoint/restore and retries.
- Two replicas sending the same key do not create two business effects.
- The same key with a different payload must be detected per the provider's contract.
- The key has a retention period long enough relative to the system's retry window.
- Logs can correlate operations without exposing sensitive data.

### 5.3. Transactional Outbox

If the application both writes to a database and sends events, a single database transaction cannot automatically span the broker in every architecture. An outbox lets business updates and event records be written in the same transaction. A publisher reads the outbox and sends the message; if sending succeeds before marking it as published, the message may be sent again.

Therefore, the outbox needs to be combined with consumer idempotency or deduplication. A checkpoint may occur between the publish step and the marking step. Multiple replicas restoring from the same image may see the same outbox record if the claiming mechanism is not safe.

Test:

1. Create a committed outbox record.
2. Have the publisher send the message to the broker.
3. Simulate a lost response or checkpoint before the publisher marks the record complete.
4. Restore multiple replicas.
5. Have publishers process that record concurrently.
6. Verify that the event may be delivered multiple times, but the business effect at the consumer is applied only once.
7. Verify that the final outbox status is updated properly.

Do not demand that the transport always deliver exactly once if the architecture provides at-least-once delivery. Criteria should focus on a single business effect achieved via idempotency.

### 5.4. Inbox or Deduplication at the Consumer

The consumer can insert the message ID into an inbox table with a unique constraint in the same transaction as the business update. If the message is redelivered, a duplicate insert is detected and the consumer does not repeat the side effect.

SQL example:

~~~sql
CREATE TABLE processed_message (
    message_id VARCHAR(200) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(100) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

Transaction logic can:

1. Insert the message ID into processed_message.
2. If the insert succeeds, execute the business update.
3. Commit both changes in the same transaction.
4. Acknowledge the message only after committing.
5. If the message ID already exists, skip the business update and acknowledge according to protocol.

In a multi-replica test, have multiple consumers process the same message ID nearly simultaneously. The unique constraint and transaction must guarantee that only one transaction applies the business update.

### 5.5. Side Effects with External Systems

For payment providers, email services, or APIs that do not participate in database transactions, use idempotency keys, operation references, or reconciliation APIs.

A good test simulates the scenario:

- The provider receives the request and executes the side effect.
- The response is lost or delayed.
- The application checkpoints/restores or another replica retries.
- The provider receives the same idempotency key again.
- The business outcome is recorded only once.

If the provider does not support idempotency, the application needs an authoritative reconciliation mechanism before retrying. End-to-end exactly-once cannot be guaranteed merely by locking an in-heap variable.

## 6. Testing Schedulers, Workers, and Leader Ownership

Schedulers are a common source of repeated side effects. If schedules or “next run” state are snapshotted, multiple replicas can start together and execute the same work.

### 6.1. Scheduled Tasks

Example of a task sending invoices at 02:00:

- Checkpoint is created after the scheduler has registered the task.
- Multiple replicas restore the same image.
- All schedulers restore the same schedule and execute the task at the same time.

Test:

1. Create a checkpoint after the schedule has been registered.
2. Restore multiple replicas.
3. Synchronize execution timing.
4. Verify that only one job claims a business period if single execution is required.
5. If the job is allowed to run across multiple replicas, verify each partition/job key is claimed only once.
6. Verify that missed runs during the pause interval are handled according to policy.

Use a distributed scheduler, database claim, or lease with a fencing token. Do not rely on an in-heap isRunning variable to guarantee only one replica executes the job.

### 6.2. Leases and Leader Election

Before checkpoint, replica A may hold a lease. While the JVM is paused, the lease expires and replica B acquires a new lease. When A restores, the leader field in the heap may still be true.

Test:

1. Have A acquire the lease and receive fencing token N.
2. Checkpoint A.
3. Wait for the lease to expire.
4. Have B acquire the lease and receive a token greater than N.
5. Restore A.
6. Have A attempt a write with token N.
7. Storage/coordinator must reject the stale write.
8. A may run leader tasks only after acquiring a new lease.

Fencing tokens need to be checked where the side effect occurs. A local mutex or leader flag inside the JVM does not protect when multiple processes operate independently.

### 6.3. Worker Queues and Claiming Tasks

If workers pull tasks from a database or broker, checkpoint may happen after a task has been claimed but before completion. Check:

- Does the claim have a lease/visibility timeout?
- Is the task returned if the worker loses its heartbeat?
- Can two replicas claim the same task at the same time?
- Is the task idempotent?
- Is completion status persisted durably before acknowledgment?

Test with multiple replicas trying to claim the same task concurrently. Use database locking, atomic updates, unique constraints, or broker semantics to prove there is only one valid owner or that all repeated processing is idempotent.

## 7. Testing Concurrency and Race Conditions

Duplicate IDs and repeated side effects are often timing-dependent. Make tests capable of creating concurrent contention while keeping results analyzable.

### 7.1. Barriers and Timing Synchronization

Each replica reports “ready” to the harness. Once N replicas are ready, the harness issues a shared start command. Inside the application, a test-only endpoint or broadcast message can be used to start operations simultaneously.

Do not add dangerous endpoints to production just for testing. Test hooks can be enabled via a test profile, have restricted network access, and be completely disabled in production artifacts.

### 7.2. Generating Contention Load

Run multiple rounds:

- N replicas generating IDs simultaneously within a short time window.
- N replicas processing the same message concurrently.
- N replicas sending requests with the same idempotency key concurrently.
- N replicas claiming the same scheduled job concurrently.
- N replicas requesting a lease for the same resource concurrently.
- N replicas writing to the same namespace or file path concurrently.

Increase iteration counts, threads per replica, and randomized jitter. Keep the seed or schedule information of the test harness so a failure can be reproduced.

### 7.3. Avoiding Artificial Tests

Do not have all replicas share a single static variable in the test harness and call that JVM heap state. Each process has its own heap. Use a database, broker, or mock service over the network as the shared observation point.

Do not check only logs, because logs can be lost or written twice. Use an authoritative store to verify counts of business records, payments, email dispatches, or job completions.

## 8. Comprehensive Test Scenario

Suppose an Orders application has an HTTP endpoint to create orders, an outbox publisher, an event-processing consumer, and a scheduler that cleans up expired orders. One checkpoint image is used to spawn three replicas.

### 8.1. Preparation

1. Start the application and complete warm-up.
2. Create a checkpoint after resources have entered a safe state.
3. Record the image digest and runtime version.
4. Launch three replicas from the same image with separate writable state.
5. Wait for all three replicas to finish bootstrapping.
6. Collect service identity, replica identity, and incarnation ID.

### 8.2. Verifying Identities

- Service identity of the three replicas must match.
- Replica IDs must differ.
- Incarnation IDs must differ if required by policy.
- Consumer member IDs must be valid and not rejected by the broker.
- Local paths and endpoints must not conflict.

### 8.3. Verifying Business IDs

1. Send order-creation requests concurrently across the three replicas.
2. Use the same idempotency key for requests representing the same operation.
3. Send additional independent requests with different keys.
4. Collect the order IDs issued by the system.
5. Check unique constraints and the operation-key/order-ID mapping.

Expected results:

- The same operation key creates only one order record.
- Independent operations receive distinct IDs.
- No insert collision is swallowed or overwritten.

### 8.4. Verifying Side Effects

1. Have the publisher send an outbox event.
2. Simulate a lost broker response after the broker has received the message.
3. Restore or restart a replica so the publisher retries.
4. Allow all three consumers the chance to receive the same event via redelivery.
5. Inspect the inbox/deduplication table and business tables.

Expected results:

- The event may be redelivered according to delivery semantics.
- The business effect is applied only once.
- Acknowledgment occurs only after the outcome is durable.

### 8.5. Verifying Schedulers and Leases

1. Create a periodic job keyed by business date.
2. Have one replica hold the lease before checkpoint.
3. Let the lease expire during the pause interval.
4. Restore all three replicas.
5. Synchronize so all schedulers attempt to claim the job.
6. Verify that one valid owner is granted the lease and the other replicas do not execute the side effect.
7. Attempt a write using the old fencing token and verify it is rejected.

### 8.6. Final Assertions

- No duplicate replica IDs.
- No duplicate business IDs except where the same operation returns the same result.
- No two payments or two email dispatches for the same operation key.
- Consumers may receive redeliveries without repeating business effects.
- Schedulers do not double-run a single-owner job.
- Expired leases do not allow the old replica to write.
- Readiness opens only after bootstrap completes.
- Every outcome has evidence from the database, broker, mock provider, and incarnation-tagged logs.

## 9. Test Matrix

| Test group | Replicas / condition | Concurrent action | Expected result |
|---|---|---|---|
| Instance identity | 2, 3, N replicas from the same image | Read identity after restore | Replica IDs differ |
| Incarnation identity | Repeated restores of the same replica/image | Generate incarnation ID | Differ according to policy |
| Service identity | N replicas of the same workload | Read service identity | Match according to configuration |
| Local counter | N replicas with the same snapshotted counter | Allocate IDs concurrently | No collisions at the authoritative store |
| UUID/random | N replicas, multiple iterations | Generate a large set of IDs | No observed collisions; provider verified |
| Snowflake/node ID | N replicas from the same checkpoint | Generate IDs in the same millisecond | Distinct node IDs or allocator prevents duplicates |
| Consumer member | N consumers in the same group | Join group concurrently | Valid member identities and assignments |
| HTTP idempotency | N replicas with the same key | Send the same request | Single business effect |
| Payment provider | N replicas for the same operation | Retry with the same idempotency key | Single payment operation |
| Outbox publisher | N publishers on the same record | Publish concurrently | Redelivery possible; single consumer effect |
| Inbox consumer | N consumers on the same message | Process the same message ID | Single business update |
| Scheduler | N replicas with the same schedule | Trigger the same job key | Single claim/side effect per policy |
| Leader/lease | Old and new owners | Restore old owner after lease expiry | Fencing rejects old owner |
| Local file/path | N replicas sharing a volume | Create file/socket paths | Separate namespaces or proper locking |
| Delayed restore | Short and long pause durations | Restore after TTL/lease expiry | Refresh/reacquire before operating |
| Repeated restore | Multiple cycles | Repeat checkpoint/restore | No resource growth, no duplicates |
| Failure injection | One dependency fails | Restore and retry | No premature readiness; bounded retries |

## 10. Measurable Acceptance Criteria

Each test should specify preconditions, actions, expected outcomes, and evidence.

**AC-01 — Unique replica identity**

- Precondition: the same checkpoint image is restored into at least three replicas.
- Action: each replica reports its replica ID and incarnation ID.
- Outcome: all replica IDs differ; incarnation IDs differ if required by policy.
- Evidence: registry or diagnostic endpoint, logs by test label.

**AC-02 — Non-duplicate business IDs**

- Precondition: three replicas concurrently allocate at least 10,000 IDs in one synchronized test run.
- Action: write IDs into a table with a unique constraint.
- Outcome: no duplicates; no ignored unique violation errors.
- Evidence: record count, unique ID count, and allocator logs.

**AC-03 — Single side effect per operation**

- Precondition: three replicas receive requests with the same idempotency key.
- Action: send requests concurrently and retry after simulating a lost response.
- Outcome: only one business record/payment effect; all responses return the same operation result per contract.
- Evidence: database/provider effect ledger and idempotency records.

**AC-04 — Safe message redelivery**

- Precondition: the broker redelivers the same message ID to multiple consumers according to the test scenario.
- Action: consumers process concurrently.
- Outcome: one business update; acknowledgment after commit.
- Evidence: inbox table, business table, offset/ack, and consumer logs.

**AC-05 — Single-owner scheduler**

- Precondition: three replicas restore the same schedule with a unique job key.
- Action: trigger the job together within one time window.
- Outcome: one replica claims the job, or partitions are split without overlap per policy.
- Evidence: job claim record, lease owner, and side-effect ledger.

**AC-06 — Fencing token**

- Precondition: replica A checkpoints with token N; replica B receives token N+1 while A is paused.
- Action: restore A and have A attempt a write using N.
- Outcome: storage rejects the write; A may proceed only after acquiring new authority.
- Evidence: coordinator records and rejected write.

**AC-07 — Readiness**

- Precondition: a required dependency is not ready after restore.
- Action: check readiness and send traffic.
- Outcome: readiness remains closed; no business requests accepted until the dependency is ready.
- Evidence: probe responses, routing, and lifecycle logs.

Thresholds such as ID counts, iteration counts, and wait times must be chosen based on risk and expected load. A test with 10,000 IDs is a concrete test sample, not a proof of absolute uniqueness for every execution.

## 11. Error Handling and Edge Cases

### 11.1. One Replica Bootstraps Slowly

If one replica is slower than the others, the test harness should not ignore it. Record:

- Restore duration.
- Identity generation duration.
- Credential acquisition duration.
- Connection pool creation duration.
- Time to readiness.

Do not issue the shared start signal until the required number of replicas for the test scenario are ready. For dedicated startup-skew tests, intentionally delay one replica's startup and verify that the coordinator still handles it properly.

### 11.2. One Replica Is Killed After a Side Effect Occurs

Simulate:

1. Replica A sends a payment request.
2. The provider executes the payment.
3. A is killed before persisting the response.
4. Replica B handles the retry for the same operation.
5. The provider receives the same idempotency key.

The outcome must be a single payment effect. If the provider does not support idempotency, the application needs reconciliation before retrying.

### 11.3. Replicas Use Duplicate IDs Without Immediate Errors

Do not wait only for collisions to throw exceptions. If duplicate IDs are not used at the exact same moment, the system may silently accept them and fail later. Tests should proactively register all replicas in a registry with a unique constraint or submit IDs to a uniqueness-checking endpoint.

### 11.4. Retries After the Deduplication Retention Window Expires

If idempotency records are purged too early, a late retry after restore can execute the side effect again. Verify that deduplication record retention is longer than the retry window, maximum pause duration, and client retry horizon.

### 11.5. Clock Skew or Backward Jumps

Timestamp-based ID generators can collide or stall when the clock rolls back. Test:

- Initialize a mock clock or controllable test clock.
- Generate many IDs within the same millisecond.
- Move the clock backward.
- Give replicas clock skew.
- Verify that the generator behaves per contract or refuses to issue IDs.

Do not use a bare wall-clock timestamp as a unique ID.

### 11.6. Restoring from an Old Checkpoint

An old checkpoint image may contain outdated configuration, counters, or credentials. Test:

- Restoring an old image after the schema has changed.
- Restoring an old image after tokens/certificates were rotated.
- Restoring an old image after a lease expired.
- Restoring an old image after service endpoints or DNS changed.

The application must verify versions and current state before operating. If the image is no longer compatible, reject restore or fall back to the normal startup path per policy.

## 12. Observability and Evidence Collection

### 12.1. Logs

Every test-related log should contain:

- Test run ID.
- Checkpoint image digest or version.
- Replica's test label.
- Service identity.
- Replica identity.
- Process incarnation ID.
- Sanitized operation ID or message ID.
- Callback phase and timestamp.

Do not log tokens, private keys, passwords, or payloads containing sensitive data. Use correlation IDs to link events across multiple replicas.

### 12.2. Metrics

Suggested metrics:

| Metric | Purpose |
|---|---|
| restored_replica_count | Number of replicas restored from one image |
| replica_identity_collision_total | Number of identity collisions detected |
| business_id_collision_total | Number of duplicate business IDs |
| idempotency_replay_total | Number of times requests with the same key were replayed |
| duplicate_effect_prevented_total | Number of duplicate side effects prevented |
| message_redelivery_total | Number of redelivered messages |
| duplicate_message_suppressed_total | Number of duplicate messages deduplicated |
| job_claim_conflict_total | Number of job claim conflicts |
| stale_fencing_write_rejected_total | Number of writes using stale fencing tokens rejected |
| restore_to_ready_seconds | Time from restore to readiness |

These are suggested metric names. Do not place UUIDs, user IDs, or operation IDs into high-cardinality labels; keep those values in logs/traces or test artifacts.

### 12.3. Evidence from Authoritative Systems

Prioritize verifying:

- Database unique constraints and business record counts.
- Idempotency tables and provider effect ledgers.
- Broker offsets, acknowledgments, group membership, and redeliveries.
- Coordinator lease owners and fencing generations.
- Registry records of replicas.
- File identities, paths, and contents after restore.
- Readiness state and request routing.

Application logs are useful evidence, but do not replace committed state in external systems. A “payment success” log does not prove the provider executed the payment only once.

## 13. Test Layering

### 13.1. Unit Tests

Verify ID generation, idempotency, and callback logic:

- Identity is generated at the right lifecycle phase.
- Retries preserve the operation key.
- Resources do not register or start duplicate workers.
- Callbacks can be invoked cyclically without leaks.
- Allocator or coordinator failures keep the instance not-ready.

Unit tests can use fake clocks, fake ID allocators, and mock providers to test logic boundaries.

### 13.2. Integration Tests with Multiple JVMs

Run at least two real processes from the same checkpoint image. This is the layer required to catch cloned heap state. Use a shared database and broker to observe conflicts.

### 13.3. End-to-End Tests

Send requests through a load balancer or test router so replicas receive traffic. Verify IDs, idempotency, outbox/inbox, schedulers, and leases against real systems or production-like simulated environments.

### 13.4. Chaos/Fault Injection

Proactively:

- Drop responses after the provider has executed a side effect.
- Kill a replica between publish/commit/ack steps.
- Make the database or broker unavailable during restore.
- Let leases expire and grant them to another replica.
- Expire credentials.
- Create races when multiple replicas claim the same task.
- Restart a replica multiple times.

Run fault injection only in a controlled test environment, with mock data and mock providers or test accounts.

## 14. Procedure for Executing a Test Run

1. Select the invariants and acceptance criteria to verify.
2. Prepare test dependencies with an authoritative store and side-effect ledger.
3. Create a canonical checkpoint image.
4. Record the digest and JDK/engine details.
5. Restore N replicas from the same image with separate runtime directories.
6. Wait for bootstrap, collect application identities, and check readiness.
7. Verify IDs that must be unique and IDs that should be shared.
8. Synchronize replicas using a barrier.
9. Send concurrent requests/messages/jobs according to the test scenario.
10. Perform retries, redeliveries, or lease expiry if required by the scenario.
11. Query the database, broker, provider, and coordinator.
12. Evaluate each acceptance criterion.
13. Save logs, metrics, traces, image digest, and test parameters.
14. Clean up replicas and test resources.
15. Repeat with different replica counts, pause durations, and failure modes.

## 15. Result Report Template

A test report should include:

~~~text
Test run:
Checkpoint image digest:
JDK/runtime/engine:
Replica count:
Pause duration:
Dependency versions:
Scenario:

Replica identities:
- test-label:
  service-id:
  replica-id:
  incarnation-id:

ID allocation:
- IDs generated:
- unique IDs:
- collision:
- unique constraint violation:

Side effects:
- operations:
- requests/retries:
- message deliveries:
- business effects:
- duplicate effect prevented:

Lease/scheduler:
- owner before checkpoint:
- owner after restore:
- fencing token:
- job claim:

Readiness:
- restore-to-ready duration:
- dependency failures:
- premature traffic:

Result:
- PASS / FAIL / INCONCLUSIVE
Evidence:
Log/metric/trace:
Failure and reproduction steps:
~~~

Do not record secrets or sensitive payloads in the report. If a test detects duplicates, retain the image digest, schedule, test seed, sanitized operation keys, and data from the authoritative store for reproduction.

## 16. Pass, Fail, and Inconclusive Criteria

### Pass

- Replicas have distinct identities within the required scope.
- Business IDs do not collide according to constraints and allocator contracts.
- The same operation key creates only one business effect.
- Message redelivery does not duplicate business updates.
- Schedulers and workers adhere to single-owner or partition policies.
- Leases/fencing prevent old owners from continuing to write.
- Readiness opens only after bootstrap completes.
- Evidence exists from authoritative systems.

### Fail

- Two replicas share the same instance ID when the ID must be unique.
- Business ID collisions are ignored or overwritten.
- One operation creates multiple payments, orders, emails, or disallowed side effects.
- Consumer acknowledgment happens before commit, or duplicate messages create multiple business updates.
- Multiple replicas run a single-owner job concurrently.
- An old replica succeeds in writing with an expired lease/fencing token.
- An instance accepts traffic before identity, credentials, or dependencies are ready.

### Inconclusive

- The test checks only logs without verifying the authoritative store.
- Only one replica was restored.
- It was not proved that the replicas used the same checkpoint image.
- Operations were not synchronized, so race conditions were not actually exercised.
- The mock provider does not reflect the idempotency contract under test.
- The test stopped before observing commit/ack results.

Do not mark pass merely because no exception was observed. A duplicate may have been written to an external system without the application reporting an error.

## 17. Common Mistakes

| Mistake | Consequence | Correct testing approach |
|---|---|---|
| Restoring each replica from a different image | Fails to catch cloned heap state | Use the same image digest |
| Running replicas sequentially | Race conditions rarely surface | Use a barrier and concurrent operations |
| Checking instance IDs only in logs | May miss IDs used in the database/broker | Check registries and unique constraints |
| Using a new ID for each retry | The same operation is treated as a new operation | Keep the idempotency key stable |
| Checking only API call counts | The provider might deduplicate properly or improperly per contract | Verify actual business effects |
| Assuming broker exactly-once | Message redelivery can still occur depending on semantics | Test idempotent consumers and inbox/outbox |
| Using synchronized to protect multiple JVMs | The lock is scoped to a single process | Use database/coordinator/lease |
| Relying on an in-heap leader boolean | Old replica may continue acting as leader | Test lease expiry and fencing |
| Running only once | Fails to catch schedule-dependent bugs | Repeat multiple rounds and vary concurrency |
| Using only callback simulators | Does not test multiple processes and real runtime | Restore multiple JVMs from a real checkpoint |
| Not testing deduplication retention | Late retries may repeat side effects | Pause longer than the retry/retention window |
| Not testing repeated restores | Resources and IDs may leak or be reused incorrectly | Run multiple checkpoint/restore cycles |

## 18. Implementation Checklist

### Environment

- [ ] Create a canonical checkpoint image and record its digest.
- [ ] Use the same image for all replicas in a test run.
- [ ] Give each replica its own process/container and writable runtime state.
- [ ] Have a shared database, broker, coordinator, or mock provider for observation.
- [ ] Have a test barrier to synchronize operations.

### Identities and IDs

- [ ] Distinguish service, workload, replica, incarnation, and business IDs.
- [ ] Verify replica identity after restore.
- [ ] Test static counters and sequences.
- [ ] Test UUID/SecureRandom against the actual provider.
- [ ] Test Snowflake/node IDs if applicable.
- [ ] Test consumer member IDs.
- [ ] Test local file/socket paths and ports.
- [ ] Use unique constraints or an authoritative allocator.

### Side Effects

- [ ] Identify side effects and operation identities.
- [ ] Keep idempotency keys stable across retries.
- [ ] Verify payment/API providers using an effect ledger.
- [ ] Test outbox publishers when responses are lost.
- [ ] Test inbox/deduplication on message redelivery.
- [ ] Test scheduler/job claims and leases.
- [ ] Test fencing tokens when an old owner restores.

### Concurrency and Failures

- [ ] Restore two or more replicas concurrently.
- [ ] Repeat tests across multiple rounds and pause durations.
- [ ] Drop responses after side effects.
- [ ] Kill replicas at commit/publish/ack boundaries.
- [ ] Let leases/tokens expire.
- [ ] Make dependencies unavailable during bootstrap.
- [ ] Verify readiness does not open prematurely.

### Evidence

- [ ] Save image digests and runtime versions.
- [ ] Save test run IDs and replica mappings.
- [ ] Inspect the authoritative database/broker/provider/coordinator.
- [ ] Collect logs, metrics, and traces tagged by incarnation.
- [ ] Report PASS/FAIL/INCONCLUSIVE for each acceptance criterion.

## 19. Principles to Remember

- Use the same checkpoint image to detect cloned heap state across replicas.
- Restore multiple real processes and synchronize operation timing to trigger race conditions.
- Service identity may match; replica identity and incarnation ID must obey uniqueness scopes.
- Do not use a snapshotted local counter as a global ID source.
- Test random generators, Snowflake/node IDs, and consumer member identities on the actual runtime.
- Use unique constraints or an authoritative allocator to detect and prevent ID collisions.
- Keep the idempotency key stable for the same operation across retries and restores.
- Combine outbox/inbox, deduplication, and properly ordered acknowledgments to handle redeliveries.
- Test schedulers, leases, and fencing tokens because multiple replicas can restore the same schedule or leader state.
- Verify business effects in the database, broker, or provider rather than relying solely on logs.
- Repeat tests with varying replica counts, multiple restores, pause durations, and failure modes.
- Conclude pass only with evidence that identities, IDs, and side effects satisfy invariants.

Testing multiple replicas from the same checkpoint helps uncover bugs that a single restore cannot expose. When concurrently testing identities, business IDs, idempotency, message delivery, schedulers, and leases in authoritative systems, development teams can prove that replicas operate independently while maintaining exactly one business outcome per operation defined as unique.
