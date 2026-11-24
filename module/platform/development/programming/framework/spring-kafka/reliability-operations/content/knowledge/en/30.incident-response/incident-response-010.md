# Pausing Before Repairing Data

During a production incident, fixing a bad record in a database can look simple: find the row, run an `UPDATE`, and verify the result. Yet if a Spring Kafka consumer is still processing related messages, the data can be overwritten right after the fix. A message sitting in a retry topic may come back, another consumer may update the same aggregate, or a scheduled job may introduce further changes while operators are remediating.

Therefore, before repairing data in a live system, you must control any flows that can keep writing to the affected data region. **Pausing before repairing data** creates a controlled quiet window so operators can confirm current state, preserve evidence, apply bounded changes, and resume processing in a safe sequence.

Pausing does not fix corrupted data on its own, cancel an external side effect that already happened, or guarantee every writer in the system has stopped. It works only when the exact scope is identified and every related write path is confirmed to be under control.

## 1. Why Pause Before Repairing?

Consider a consumer receiving `OrderPaid` events and updating order status. Operators discover a batch of orders in the wrong state and prepare to run SQL to correct them. If the consumer remains active, the following scenarios can happen:

- The consumer is actively processing the exact order an operator is about to fix. SQL runs first, then the consumer writes the stale status back.
- Two events for the same aggregate are handled in two separate flows. A manual fix gets overwritten by the other update.
- The consumer already called the payment provider or created a shipment without yet persisting the outcome to the DB. Fixing DB status can cause the next retry to call the provider a second time.
- An older event waiting in a retry topic or DLT is replayed while data is being repaired.
- Another application, batch job, or admin API still has write access to the same table even though the Kafka listener is paused.

In those cases, data can shift right while the operator is verifying it. The fix may look accurate when SQL completes yet become wrong seconds later. Worse, editing a status table without understanding related inbox, outbox, or effect ledger records can cause the system to lose track of an executed side effect or execute it a second time.

Pausing establishes a clear operational boundary: which flows are permitted to continue, which flows are stopped, what in-flight work remains, and which data may be modified during the maintenance window.

## 2. When Is Pausing Needed?

Pausing is appropriate when you need a window to investigate or repair a data region that consumers could still mutate. Common scenarios include:

| Scenario | Why pause |
|---|---|
| Fixing wrong business state caused by an earlier event | Prevent new or retried events from overwriting the fix |
| Investigating duplicate processing or duplicate side effects | Keep data stable while reconciling events, offsets, and provider history |
| Repairing reference data actively read by consumers | Prevent consumers from reading half-repaired state |
| Running backfills or repair scripts overlapping consumer write scope | Prevent two competing write flows |
| Handling incidents causing continuous retry storms | Buy time to pinpoint root cause and retry policy |
| Preparing to replay a group of events | Control ordering, scope, and idempotency preconditions before republishing |

Not every error requires pausing the whole system. If an independent consumer handles an unrelated topic and does not write to the affected data region, it can stay running. Pause scope should be as narrow as possible while still covering every writer capable of mutating the data under repair.

If bad data is being written continuously or poses financial, security, or operational risk, prioritize controlling write paths before continuing deep investigation. When you also need to stop producers from generating more messages, you may have to pause upstream ingress or business features. Pausing the consumer alone does not stop producers from writing new records to Kafka.

## 3. Identify the Full Impact Scope

Before hitting pause, know exactly what writes the data and what will be affected by stopping. One consumer group does not always map one-to-one with a single business flow; a topic can have multiple independent groups, and an application can host multiple `@KafkaListener` endpoints.

List at minimum these components:

| Component | What to identify |
|---|---|
| Source topic | Topic name, partitions, keys, and time range containing relevant records |
| Consumer group | Group ID, participating instances, listener IDs, and concurrency |
| Retry topics | Tiered retry topics, retry schedules, and retry consumers |
| Dead-letter topic | DLT, existing investigation and replay workflows |
| Database | Tables, aggregates, primary keys, relationships, and transactions that can update the data |
| External side effects | Payments, email, SMS, shipping, provisioning, or other APIs |
| Other write paths | REST APIs, schedulers, batch jobs, CDC consumers, admin tools, or other apps |
| Outbox/inbox/effect ledger | Pending publish records, received events, and unresolved side effects |

Specifically, distinguish **consumer group** from **listener container**. A group can span multiple instances across different pods or hosts. Pausing a listener in one pod controls only that container. Other instances in the same group can still process partitions assigned to them. Other groups reading the same topic also continue running independently.

An incident scope sheet should record clearly:

```text
Incident: INC-2026-0042
Affected service: billing-service
Listener ID: billing-order-listener
Consumer group: billing-orders-v2
Source topic: order-paid
Affected partitions: 2, 5
Affected order IDs: ORD-1001, ORD-1008, ORD-1012
Database tables: orders, payment_attempts, external_effect
Other writers: refund scheduler, manual operations API
Retry/DLT paths: order-paid-retry-*, order-paid-dlt
```

This is an example of documenting scope, not a default configuration. Use your system's actual names and verify each component before taking action.

## 4. How Does Pausing Work in Spring Kafka?

Spring Kafka exposes pause/resume APIs at the listener container level. This is usually the right way to control consumers managed by `@KafkaListener`.

When calling `pause()` on a listener container:

- The container instructs the consumer to stop fetching additional records from assigned partitions.
- The pause takes effect at an appropriate consumer poll cycle; calling `pause()` does not abort an in-progress callback.
- The consumer continues polling per container mechanics to maintain consumer group membership and heartbeats.
- Paused partitions remain assigned to that consumer. Other consumers do not automatically take over partitions merely because they are paused.
- When `resume()` is called, the consumer resumes receiving records from its current position based on confirmed offsets and state.

Thus, pausing is not the same as killing the process or deleting the consumer group. It creates a pause in receiving new records while keeping the consumer in the group. Records already polled or currently inside a listener invocation must still finish and be verified per the application's ack/commit mechanics.

### 4.1. Controlling Listener Containers via the Registry

Assign an explicit `id` to listeners so the exact container can be looked up via `KafkaListenerEndpointRegistry`:

```java
@KafkaListener(
    id = "billing-order-listener",
    topics = "order-paid",
    groupId = "billing-orders-v2",
    concurrency = "3"
)
public void onOrderPaid(OrderPaid event) {
    billingService.handle(event);
}
```

A control service can request pause or resume:

```java
@Component
public class KafkaListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + listenerId);
        }

        container.pause();
    }

    public void resume(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + listenerId);
        }

        container.resume();
    }
}
```

This is a minimal control API example. In production applications, add authorization, audit logging, incident ID validation, current pause status reporting, and safeguards against targeting the wrong listener. Never expose public pause/resume endpoints without proper authentication and authorization.

For `ConcurrentMessageListenerContainer`, pausing the parent container applies to the child consumer containers belonging to that listener. However, one application's registry controls only the listeners managed by that application instance. If the service has multiple replicas, control and verify state across every relevant replica. One paused pod does not mean the entire consumer group is paused.

### 4.2. Never Call KafkaConsumer Directly from Management Threads

A Kafka consumer is not thread-safe for arbitrary calls from any thread. When Spring Kafka manages consumers, use the listener container API to request pause/resume. Never extract an internal `KafkaConsumer` and call `pause()` directly from an HTTP controller or scheduler thread.

If an application manages Kafka consumers manually without a listener container, pause/resume must happen on the consumer's owning thread or via a safe control mechanism built by the application. Never share a single consumer instance across processing threads and management threads.

### 4.3. Container Pause vs. Partition Pause

Pausing the entire listener fits when all partitions of that listener fall inside the incident scope. If only a subset of partitions is affected and your Spring Kafka version supports partition-level control, pausing specific partitions can be considered.

Per-partition pausing requires understanding key distribution, assignments, concurrency, and business data. An order may be processed on another partition if producers do not guarantee consistent keys; a retry flow may move records to a different topic and partition. Never pause only the partition holding the visible error while ignoring related paths.

When repairing a single aggregate, the data scope may be narrower than a partition. Yet unless you can prove every event for that aggregate always traverses the same partition and every side effect runs through the same listener, widen your control scope until clear evidence proves otherwise.

## 5. Pausing Does Not Mean All Processing Has Stopped

This is the most common misconception in incident response. A pause command is a control request; it is not a synchronous barrier around the entire application.

After calling `pause()`, the following may still exist:

- A listener callback still processing a record from the previous poll.
- A batch listener still processing records already in its batch.
- An asynchronous task already handed off by the listener to a separate executor.
- An HTTP request to a provider awaiting response.
- A DB transaction already started but not yet committed or rolled back.
- A scheduled job or another listener writing to the same table.
- Another instance in the same group or a different consumer group still actively running.

Therefore, include a **drain** step (allowing in-flight work to complete or be classified) after requesting pause. Never run data-repair SQL immediately after the pause API returns.

### 5.1. Confirm the Listener Is Paused

Depending on your Spring Kafka version, monitor container state and events such as `ConsumerPausedEvent` or `ConsumerResumedEvent`. Combine logs containing listener ID, client ID, group ID, pod/instance, and partitions to verify each consumer has paused.

Signals to verify:

1. Pause request sent to the exact listener ID across all instances in scope.
2. Container emitted an event or state confirming pause took effect.
3. No new records are entering that listener's callback.
4. Active callbacks and related async tasks have dropped to 0 or been classified.
5. No DB transactions or external requests with unknown outcomes can mutate the data under repair.

Do not rely solely on a log line saying "pause requested." Distinguish between a pause request being issued and the consumer actually reaching paused state. Exact state inspection and event behavior depend on Spring Kafka version and container setup.

### 5.2. Handle In-Flight Work

For an active callback, prefer letting it finish within a bounded wait window. Then inspect DB transactions and offsets. If a callback is hung on an HTTP request, determine whether the provider may already have executed the side effect. A timeout or canceled future does not prove the external call never happened.

If an in-flight task must be stopped, you must know its commit and side-effect state. Do not kill a pod merely to force active callbacks to zero without knowing whether the request reached the provider or the transaction committed. Killing the process can cause message redelivery even though the external action already completed.

For asynchronous processing, the listener may return before background work ends. In that case, container pause status does not reflect executor status. The application must separately track active tasks, internal queues, and controlled executor shutdown.

## 6. Inspect Offsets and Consumer Group Status

Before repairing data, record the offset state of relevant partitions. Offsets answer how far the consumer has confirmed, what records remain pending, and whether lag is rising or falling.

Use Kafka consumer groups CLI to inspect group status:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <consumer-group-id> \
  --describe
```

This command is read-only observation. Save the output alongside timestamp, group ID, topic, and partitions in the incident record. Some environments may require a different script path or syntax depending on the Kafka distribution.

When reading the output, note:

- `CURRENT-OFFSET` is the position the consumer group has committed, usually representing the next offset to be read.
- `LOG-END-OFFSET` is the end of the log as displayed by the tool.
- `LAG` shows the gap between log end and committed offset as calculated by the tool.
- `CONSUMER-ID`, `HOST`, and `CLIENT-ID` identify the member currently holding the partition.

Committed offset does not necessarily equal the last successfully processed record under every configuration. With manual acks, async processing, or transactions, cross-check offsets with processing logs, DB records, and side-effect states. If the listener fetched a record without committing the offset, that record can be redelivered after a crash or restart.

**Never reset offsets just to zero out lag or "sync" with repaired data.** Resetting offsets is a decision to replay or skip records that can alter the group's entire processing history. It requires its own scope, start/end boundaries, idempotency plan, and operational approval.

## 7. Preserve Evidence Before Running Repairs

Once consumers and related writers are controlled, save pre-repair state. This establishes what the repair changed, whether any unintended impact occurred, and how to revert if needed.

Information to capture:

| Category | Data to save |
|---|---|
| Incident | Incident ID, operator, start time, reason for pause, and approved scope |
| Kafka | Topic, partition, offset, key, event ID, group ID, and committed offset |
| Application | Service version, pod/instance, listener ID, concurrency, and pause state |
| Database | Primary keys, pre-repair values, versions, timestamps, relationships, and affected row count |
| Side effects | Effect keys, provider references, status, attempt count, and reconciliation results |
| Retry/DLT | Related records, headers, exceptions, retry count, and replay history |
| Operations | Logs, trace IDs, dashboard snapshots, and commands executed |

For critical data, create a retrievable backup or snapshot before modifying. For a small batch of records, export pre-repair values into an audit table or a file stored in a controlled location. The backup must capture enough information to restore modified columns accurately and must be protected like production data.

Record both count and scope. For instance, if 12 orders are slated for repair, write down the 12 IDs and confirm a `SELECT` returns exactly 12 rows before running `UPDATE`. A SQL statement missing a filter condition can turn a small repair into a full-table mutation.

## 8. Execute Controlled Data Repairs

A good repair has a clear business goal, bounded scope, pre-execution verification, and a post-execution audit trail.

### 8.1. Define the Invariant to Restore

Before writing SQL, express the valid state as a verifiable rule. For example:

- A `payment_attempt` in `SUCCEEDED` status must have a valid provider reference.
- An already-paid order must not revert to `PENDING_PAYMENT` simply because an old event is replayed.
- An effect confirmed successful by the provider must not transition back to `PENDING`.
- An event recorded in the inbox with a created effect intent must maintain consistent referential integrity.

Never repair by guessing from a single status column. Understand the aggregate, relationships, version, event history, and associated side effects.

### 8.2. Run SELECT Before UPDATE

Always run a read query with the exact conditions planned for the write statement:

```sql
SELECT order_id, status, version, updated_at
FROM orders
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
ORDER BY order_id;
```

Compare every row against the approved list. If row count, status, or version differs from expectations, stop and investigate before executing any write command.

### 8.3. Use Transactions and Scope Guards

The example below illustrates a verified repair on PostgreSQL. `status` and `version` predicates are illustrative only; replace them with actual business invariants.

```sql
BEGIN;

UPDATE orders
SET status = 'PAID',
    version = version + 1,
    updated_at = now()
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
  AND status = 'PAYMENT_PENDING'
  AND version = 7;

-- Check changed row count and re-read state inside the transaction.
SELECT order_id, status, version, updated_at
FROM orders
WHERE order_id IN ('ORD-1001', 'ORD-1008', 'ORD-1012')
ORDER BY order_id;

-- COMMIT only after results match the approved scope and invariant.
-- If they do not match, run ROLLBACK.
```

In practice, the operator must verify updated row counts before committing. If your DB client supports conditional scripts or stored procedures to assert row counts, use them to roll back automatically when counts mismatch. Never copy this example verbatim into production without adapting business conditions and statuses.

### 8.4. Keep an Audit Trail

Record repair ID, incident ID, operator, timestamp, script version, list of affected IDs, and before/after values. If the system maintains an audit table, use it per current standards. Avoid overwriting or deleting business history to make the new state look as if no error ever occurred.

If a repair might need to run multiple times, make the script idempotent: re-running creates no extra mutations or side effects. You may record a unique `repair_id` to track applied changes, while still verifying payload and scope when a repair ID already exists.

### 8.5. Never Delete Idempotency Records to Force Reprocessing

A common mistake is deleting inbox or effect ledger rows and then replaying events hoping the consumer will reprocess them. Doing so can make the system forget a payment already succeeded, an email was sent, or a shipment was created.

Before modifying inbox, outbox, deduplication records, or external effects, determine each record's role and reconcile with the provider. If business execution truly needs to run again, create a new execution with a new business identifier per domain rules, or use a designed replay flow. Never delete old idempotency keys just to bypass a unique constraint.

## 9. Flows to Control Beyond the Main Listener

Pausing one primary listener is not enough if affected data can still be written through another path.

### 9.1. Retry Topics and DLT

Spring Kafka can use retry topics or DLTs to route failed records into separate streams. Identify which listeners consume those topics. If the repair touches an event that could sit in a retry topic, control the retry listener as well.

Never replay a DLT while repairing data. Records in the DLT may be older than the aggregate's current state; replaying them without checking versions or business state can revert a newer decision.

### 9.2. Scheduled Jobs and Batch Processes

A reconciliation job, batch import, or scheduler may keep writing to the DB even when Kafka listeners are paused. Pause relevant jobs via the application's management controls and record their state. If a job is already running, wait for it to finish or classify its active transactions before repairing.

### 9.3. APIs and Admin Actions

If REST APIs or admin screens can update the same aggregate, enable maintenance mode or block write endpoints within the required scope. Merely telling operators "maintenance is underway" creates no technical safeguard; confirm new write requests are actually rejected or safely queued.

### 9.4. Outbox Publishers and CDC

If DB repairs create or modify outbox records, the publisher may emit new events once consumers resume. CDC connectors may also stream data changes to Kafka or other systems. Understand whether the repair counts as a business change that should be published or strictly an operational data correction.

Do not arbitrarily turn off outbox publishers or CDC without understanding impact on other flows. If pausing is necessary, record checkpoints and a plan to process queued records after recovery.

### 9.5. Upstream Producers

Pausing consumers does not stop producers from writing new records. Kafka continues storing records and lag can grow during maintenance. If record volume grows rapidly or upstream keeps emitting bad data, coordinate pausing event generation, applying rate limits, or switching upstream into maintenance mode.

Never delete Kafka records merely to reduce lag. Records may be required evidence for investigation and recovery.

## 10. Distinguishing Pause, Stop, and Reset Offset

These three operations have different effects and must not be used interchangeably.

| Operation | Primary effect | When to use |
|---|---|---|
| Pause container | Pauses fetching new records while keeping the consumer in the group and polling per container mechanics | Investigating or repairing data during a controlled pause |
| Stop container | Stops the listener; consumer leaves the group and partitions may rebalance to other members | Process maintenance or preparing an operation requiring zero active members in the group |
| Reset offset | Changes the position where the group will next read in the log | Replaying or skipping a planned range of records under an explicit plan |

If you pause one consumer while other members stay active, other members still process their assigned partitions. If you stop one member, its partitions can be reassigned to remaining members. Therefore, stopping one pod does not stop the entire group.

Some offset reset operations require the consumer group to have no active members. A paused consumer can still count as an active member. If an offset reset is required, stop all consumers in the group per plan, confirm the group is inactive, record current offsets, and execute a dedicated replay procedure.

Offset resets can cause records to be reprocessed or skipped. They do not fix DB data and do not automatically inspect side effects. Before replaying, prove the consumer is idempotent, effect keys are preserved, and providers return prior execution outcomes. For providers lacking idempotency, reconcile before replaying events with uncertain outcomes.

## 11. Resume Step by Step

After repairs finish, do not re-enable every flow at once without verifying state. Resuming is part of incident response and requires start preconditions, monitoring signals, and stop criteria.

### 11.1. Verify Data After Repair

First, re-run the read queries used to establish scope. Compare row counts, statuses, versions, relationships, and invariants. Verify inbox, outbox, effect ledger, and provider reference records remain consistent.

If the repair created changes meant to emit events, confirm outbox records and payloads are accurate. If the repair was strictly an internal data fix, confirm it did not accidentally trigger unexpected publishing or CDC streams.

### 11.2. Check Preconditions to Resume

Resume only when:

- Repair scripts completed and modified row counts match the approved scope.
- No transactions or background tasks with unclear status remain that could overwrite data.
- Side effects with unknown outcomes are logged with a reconciliation plan.
- Retry/DLT has no unplanned replay queued to run.
- Other writers are permitted to resume in the proper order.
- Dashboards, logs, and incident responders are ready to monitor the recovery phase.

If an `UNKNOWN` side effect remains, do not automatically flip it to `FAILED` just to let consumers proceed. Keep the unknown state and follow your defined reconciliation workflow.

### 11.3. Resume Listeners in a Controlled Manner

For paused listener containers, call `resume()` via the same control mechanism. If multiple replicas exist, confirm all instances resume across the intended scope. Never rely on a command on one pod to conclude the whole group is active again.

If the system supports per-partition pausing, you can resume one partition or a small subset first, observe results, and then expand. For high listener concurrency, consider restoring at lower load per approved operational configuration.

### 11.4. Monitor After Resuming

Monitor for long enough to cover normal processing cycles and relevant retry schedules. Signals to watch include:

| Signal | What to confirm |
|---|---|
| Consumer lag | Rises or falls at expected pace; no prolonged abnormal spikes |
| Listener error rate | The error that caused the incident does not reappear |
| Retry and DLT volume | No retry loops or sudden spikes |
| Duplicate detection | No rise in duplicate events or idempotency key conflicts |
| DB constraints and locks | No abnormal constraint violations, deadlocks, or lock waits |
| Business state | Aggregates continue transitioning per domain rules |
| External effects | No duplicate charges, emails, shipments, or API requests |
| `UNKNOWN` effects | Count and age of records drop per reconciliation plan |

If wrong data reappears, duplicate side effects occur, or a retry loop starts, pause the affected scope again and preserve evidence. Never keep applying consecutive fixes without understanding why the fault recurred.

## 12. Incident Example: Fixing Order Status After Incorrect Consumer Writes

Suppose `billing-service` consumes `OrderPaid` events and updates `orders.status`. A mapping bug caused several paid orders to be saved as `PAYMENT_PENDING`. Operators identify 12 affected orders.

**Step 1 — Open incident and scope.** Record the 12 `orderId`s, event IDs, topic, partitions, offsets, and processing timestamps. Identify listener `billing-order-listener`, group `billing-orders-v2`, all running pods, retry listeners, DLT listeners, and jobs capable of updating `orders`.

**Step 2 — Prevent further bad writes.** If the mapping bug is still live, pause upstream emission of faulty events or block write paths per incident procedure. Pause the target listener across all replicas. Pause retry listeners that could redeliver the same events. Control admin APIs or schedulers if they can write to these orders.

**Step 3 — Drain and capture offsets.** Wait for active callbacks to finish within a defined limit. Inspect payment requests with unclear outcomes. Record committed offsets and log end offsets for affected partitions; do not reset offsets.

**Step 4 — Reconcile data.** For each order, verify payment attempts, provider references, effect ledger, event inbox, and state transition history. Confirm all 12 orders were genuinely paid. If any order lacks provider confirmation, place it into a separate reconciliation list.

**Step 5 — Bounded repair.** Save a snapshot of pre-repair values. Run `SELECT` for the exact 12 IDs and verify counts and versions. Run a conditional `UPDATE` modifying only rows in the wrong state with the expected version. Re-read inside the transaction, confirm results, and commit. Record repair ID and before/after values.

**Step 6 — Verify recovery preconditions.** Confirm the 12 orders hold the right status, payment attempts and provider references did not change unexpectedly, and effect ledger records were neither deleted nor recreated. Confirm the mapping bug is fixed or guarded before reopening the consumer.

**Step 7 — Resume and monitor.** Resume listeners and retry paths in the defined order. Watch affected orders, duplicate detection, lag, DB errors, and side effects. If an older event flips an order back to `PAYMENT_PENDING`, pause again and investigate update guards or version checks in the consumer.

This example shows pausing is only one step in the workflow. Fixing 12 rows cleanly is still insufficient if an older event can overwrite state once the listener resumes.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Pausing one pod and assuming the whole group stopped | Other pods keep processing assigned partitions | Check all instances and related listeners |
| Running SQL right after sending pause | Old callbacks or transactions are still running | Wait for pause confirmation and drain active work |
| Pausing only the main listener | Retry, DLT, schedulers, or APIs keep writing data | Map all writers and replay paths |
| Killing pods to stop quickly | Messages may redeliver; side effects may have succeeded | Classify in-flight work and unknown outcomes before stopping |
| Resetting offsets so consumers skip errors | Can lose records or trigger unexpected replays | Separate offset resets into a controlled replay plan |
| Deleting inbox/effect records to force reprocessing | Loses record of executed side effects and creates duplicates | Reconcile with provider, preserve idempotency history |
| Fixing DB state without fixing root cause | Consumer writes bad state again after resume | Fix code/config or guard error condition before resuming |
| Resuming all writers at once | Sudden load spike and hard to trace recurring fault source | Re-enable in order, observe, and ramp load gradually |
| Not saving pre-repair values | Hard to audit or revert if a repair goes wrong | Snapshot, audit trail, and repair ID before writing |

## 14. Pause and Repair Record Template

During an incident, using a concise template updated step by step helps the next responder know the exact system state:

```text
Incident ID:
Coordinator:
Reason for pause:

Affected service:
Listener IDs:
Consumer group IDs:
Pods / instances:
Topics / partitions:
Retry topics / DLT:
Other writers paused or blocked:

Pause requested at:
Pause confirmed at:
In-flight callbacks remaining:
Async tasks remaining:
Unknown external requests:

Committed offsets captured at:
Database snapshot / backup reference:
Affected entity IDs:
Expected row count:
Actual row count before repair:
Repair script version:
Repair ID:
Rows changed:
Post-repair invariants checked:

Resume approved by:
Resume time:
Post-resume observations:
Remaining reconciliation items:
Incident status:
```

Store this record in your organization's incident system or audit log. Never put credentials, access tokens, card data, or unnecessary personal data into operational notes.

## 15. Pre-Repair Checklist

Before running any repair script, confirm all of the following:

- Business invariants to restore and the list of affected entities are defined.
- Every listener, consumer group, replica, retry topic, and DLT that can write related data is identified.
- Non-Kafka writers such as APIs, schedulers, batch jobs, admin tools, and CDC are controlled.
- Pause has been sent to the exact containers and confirmed effective across all relevant instances.
- Active callbacks, async tasks, DB transactions, and external requests are drained or classified.
- Topics, partitions, offsets, group IDs, and consumer state are recorded prior to repair.
- Data is snapshotted pre-repair alongside required logs, event IDs, effect keys, and provider references.
- `SELECT` was executed with the exact conditions planned for `UPDATE` and returned the exact row count.
- The repair script includes scope guards, audit trail, row count checks, and a rollback or compensation plan.
- No inbox, outbox, deduplication records, or effect ledger rows are deleted just to force replay.
- Clear criteria exist for resuming, post-resume monitoring, and re-pausing if errors recur.

## Conclusion

In incident response, pausing before repairing data creates the breathing room needed to understand and control write flows. With Spring Kafka, control the exact listener containers, confirm every replica paused, drain active work, and record offset state. Only then should you snapshot data, define invariants, and run bounded repairs.

Pausing one listener does not stop producers, retry paths, DLTs, schedulers, APIs, or other consumer groups. Nor does it undo side effects already sent to external systems. Therefore, pause scope must cover the entire live write path of the affected data.

After repairing, re-verify data and side effects, resume listeners in a controlled sequence, and monitor lag, retries, duplicates, and business state. If bad data reappears, pause the affected scope and investigate root cause before applying further repairs. This approach preserves evidence, reduces race conditions, and prevents a data repair from becoming a second incident.
