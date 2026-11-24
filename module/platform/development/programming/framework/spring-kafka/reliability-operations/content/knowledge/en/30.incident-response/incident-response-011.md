# Controlled Replay

In Spring Kafka operations, replaying is the act of re-reading and reprocessing Kafka records that a consumer previously processed or skipped due to an incident. Replaying is useful when fixing data after a business bug, rerunning with a patched code version, recovering a consumer after an incorrect offset commit, or reprocessing a range of messages sitting in a Dead Letter Topic (DLT).

Replaying directly affects data and side effects. A replay can recreate orders, charge accounts, send emails, or emit downstream events. Therefore, a replay must have a clear scope, defined start and end boundaries, duplicate-prevention guards, rate limits, an assigned owner, and stop conditions. In incident response workflows, replaying is a controlled recovery operation, not arbitrary message retrying.

## 1. What Is Replaying and When Should You Use It?

Kafka stores records by partition. Consumer groups store committed offsets to mark the next read position for each partition. Replaying returns a consumer to older offsets or creates another consumer group to re-read data from a chosen position.

Common scenarios requiring a replay include:

- A buggy consumer version wrote incorrect data; the code has been fixed and affected events need to be rerun.
- A consumer was misconfigured, committed offsets past processed data, or skipped a range of records.
- A downstream service was temporarily unavailable and the system needs to reprocess retained events.
- A read model, search index, cache, or projection needs to be rebuilt from the event log.
- Messages routed into a DLT need to be reprocessed after fixing the underlying error.

Replaying is not suitable for every error. If a message only failed transiently and the retry policy is working properly, retries may suffice. If the original data expired past retention or was removed by log compaction, replaying from Kafka may not restore full state. If a side effect already occurred while the response timed out, reconcile state before replaying to avoid triggering the effect a second time.

### Distinguishing Retry, DLT, and Replay

| Mechanism | Purpose | Scope |
|---|---|---|
| Retry | Retry a failed processing attempt | Usually applied inline in the processing flow or via retry topics |
| Dead Letter Topic | Quarantine records that cannot be processed under the retry policy | Holds failed records for investigation or later handling |
| Replay | Re-read an existing set of records | Can target one partition, an offset range, a time window, or all retained data |

A DLT does not automatically undo side effects executed before an exception was thrown. Likewise, replaying does not automatically guarantee executing a side effect only once. Replay consumers must still enforce idempotency and business state checks.

## 2. Define the Exact Replay Scope

Before running a replay, describe the scope using verifiable parameters:

- **Topic:** the data source to re-read.
- **Partitions:** the affected partitions. Do not assume every partition needs replaying.
- **Start offset:** the first offset to process on each partition.
- **End offset exclusive:** the upper bound offset, excluded from processing. Capture this value before starting so the replay does not chase continuously arriving new records.
- **Consumer group or replay job ID:** identifier for the replay flow and its checkpoints.
- **Business filter:** event types, tenants, aggregates, or operations within the incident scope.
- **Target:** database, service, or read model receiving the replay's effects.

For example, an incident might affect only events on partitions `0` and `2` of topic `orders`, with offset ranges `[1200, 1450)` and `[800, 920)`. This notation means the start offset is included and the end offset is excluded. Every partition has its own offset sequence; a single global offset cannot represent the entire topic.

When defining scope by time, translate timestamps into per-partition offsets. Kafka does not guarantee one timestamp maps to the same offset across partitions. Record timestamps may also reflect producer creation time or broker append time depending on timestamp configuration.

### Offset Is the Next Read Position

A committed offset is the position the consumer will read next, not the sequence number of the last processed record. For example, committing offset `1201` typically means the record at offset `1200` has been processed and the next read starts at `1201`.

When specifying a replay range, use the explicit `[startOffset, endOffsetExclusive)` convention. This avoids over-processing the trailing record or missing the leading record. Remember also that logs can contain offset gaps from compaction, transaction markers, or purged records; not every integer in the range corresponds to a readable record.

## 3. Choose the Appropriate Replay Strategy

Three organizational patterns are common. The right choice depends on whether you need to repair a live consumer group, reprocess data in isolation, or republish events through a dedicated flow.

### Option A: Use a Separate Consumer Group for Replay

This is usually the easiest approach to control when reprocessing data without altering production consumer offsets. Create a group ID dedicated to the incident or replay job, e.g. `orders-replay-incident-2026-11-16`.

Advantages:

- Production offsets remain untouched.
- New code can run in an isolated consumer.
- Speed can be throttled and the replay stopped without halting production flows.
- Results can be reconciled before deciding to update official data.

Risks to control:

- If the replay consumer writes to the same database or calls the same external services, side effects can still repeat.
- If a new group has no committed offsets, `auto.offset.reset=earliest` can cause it to read all data within retention.
- Creating a new group ID every time an interrupted job is retried discards the previous run's checkpoint.

For replays with fixed offset ranges, configure `auto.offset.reset=none` so the consumer fails clearly if no offset is specified or the offset is no longer valid. Seek explicitly to the approved start offset. Reuse a stable group ID for the same replay job so it can resume from checkpoints; create a new ID only when starting a genuinely separate job.

### Option B: Reset Offsets of the Existing Consumer Group

Offset resetting fits when the intent is for the production consumer itself to re-read from an earlier position, such as recovering a group that committed past durable processing. This directly affects progress of the live group serving the system.

Safe operational sequence:

1. Identify the exact group, topic, and partitions to reset.
2. Record current offsets, lag, and consumer state for comparison or rollback.
3. Stop all consumers belonging to the group and confirm the group has no active members.
4. Run the reset command in `--dry-run` mode and inspect results for every partition.
5. Execute only after the new start offsets are approved and production impact is accounted for.
6. Restart consumers and monitor lag, throughput, errors, and side effects.

Example checking current offsets:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --describe \
  --group <production-group>
```

Example previewing resetting a topic's partitions to the earliest retained offset:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --group <production-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

Only after verifying the output and confirming the group is completely stopped, re-run with `--execute`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <broker:9092> \
  --group <production-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --execute
```

Script extensions may be `.sh` or `.bat` depending on distribution and OS. Other reset options include `--to-offset`, `--to-datetime`, `--to-latest`, and `--shift-by`; exact flags must match your Kafka CLI version.

Never run an offset reset on a group with active consumers. Consumers may keep committing new offsets, rebalance, or produce unpredictable results. `--to-earliest` can also make production reprocess all retained records of the specified topic. Without sink idempotency, resetting can double business side effects.

### Option C: Republish to a Replay Topic

A job can read records from the source topic and publish copies to a dedicated topic, such as `orders-replay`. A replay consumer processes that topic using a separate group and configuration.

This works well when you want to:

- Test a new handler version in an isolated environment.
- Keep the production topic and current consumer progress untouched.
- Apply filters, attach incident metadata, or split the replay into batches.
- Create a dedicated input stream for repairing a read model or running reconciliation.

When copying records, preserve the business event ID, key, schema version, and required headers. You may add metadata such as `original-topic`, `original-partition`, `original-offset`, `replay-job-id`, and `replay-reason`. If per-aggregate ordering is required, preserve the same key and ensure events for an aggregate land in the same partition on the target topic. There is no global ordering across partitions.

A replay topic holds republished events, yet it does not create an atomic transaction between reading the source and publishing the copy. If the publisher stops after publishing but before persisting progress, records may be republished. Use an outbox or proper checkpointing and keep the target consumer idempotent. Avoid publishing back into the original source topic without loop-prevention guards.

### Comparing Options

| Strategy | Impact on production group | Best suited when | Controls needed |
|---|---|---|---|
| Separate replay group | Leaves production offsets unchanged | Independent replay, testing new code, controlled reprocessing | Group ID, offset range, side effects at sink |
| Reset existing group | Mutates production offsets | Recovering the live running group itself | Stop consumers, dry-run, duplicates, lag spike |
| Replay topic | Leaves source offsets unchanged if publisher uses separate group | Separate replay pipeline or extra metadata needed | Duplicate publishes, keys, ordering, and schemas |

## 4. Implementing Bounded Replay in a Spring Kafka Application

With `@KafkaListener`, a replay listener should have its own `groupId` and configuration. Never share the production group ID when the goal is an independent replay.

Example dedicated replay listener:

```java
@Component
public class OrderReplayListener {

    private final OrderReplayService replayService;

    public OrderReplayListener(OrderReplayService replayService) {
        this.replayService = replayService;
    }

    @KafkaListener(
        id = "orders-replay-listener",
        topics = "${replay.orders.topic}",
        groupId = "${replay.orders.group-id}",
        autoStartup = "false"
    )
    public void onMessage(ConsumerRecord<String, OrderEvent> record) {
        replayService.process(
            record.key(),
            record.value(),
            record.topic(),
            record.partition(),
            record.offset()
        );
    }
}
```

`autoStartup = "false"` lets the application initialize the listener while starting it only once the replay job is prepared. A coordinator can control the listener via `KafkaListenerEndpointRegistry` after verifying configuration, group ID, scope, and checkpoints. To seek to specific offsets, Spring Kafka supports `ConsumerSeekAware` or listener container operations; seeking must happen once the consumer has been assigned partitions. Seeking to the start offset alone is not enough to enforce an end offset, so the coordinator must still track the upper boundary of each partition and stop the job when reached.

For replays requiring strict `[start, end)` bounds, you can implement a worker using the Kafka `Consumer` directly inside the Spring application. The example below illustrates assigning partitions, seeking to approved offsets, capturing end offsets, and passing only records within bounds to the handler. Consumer creation, event decoding, and job state persistence are supplied by the application:

```java
public final class BoundedReplayWorker {

    private final Consumer<String, OrderEvent> consumer;
    private final OrderReplayService replayService;

    public BoundedReplayWorker(
            Consumer<String, OrderEvent> consumer,
            OrderReplayService replayService) {
        this.consumer = consumer;
        this.replayService = replayService;
    }

    public void run(Map<TopicPartition, Long> startOffsets) {
        Set<TopicPartition> partitions = startOffsets.keySet();
        consumer.assign(partitions);

        Map<TopicPartition, Long> beginning = consumer.beginningOffsets(partitions);
        Map<TopicPartition, Long> endExclusive = consumer.endOffsets(partitions);

        for (TopicPartition partition : partitions) {
            long start = startOffsets.get(partition);
            long earliest = beginning.get(partition);
            long end = endExclusive.get(partition);

            if (start < earliest || start > end) {
                throw new IllegalArgumentException(
                    "Replay offset is outside the retained range: " + partition
                );
            }

            consumer.seek(partition, start);
        }

        Map<TopicPartition, Long> nextOffsets = new HashMap<>(startOffsets);
        Set<TopicPartition> completed = new HashSet<>();

        while (completed.size() < partitions.size()) {
            ConsumerRecords<String, OrderEvent> records =
                consumer.poll(Duration.ofMillis(500));

            for (ConsumerRecord<String, OrderEvent> record : records) {
                TopicPartition partition = new TopicPartition(
                    record.topic(), record.partition()
                );
                long end = endExclusive.get(partition);

                if (record.offset() >= end) {
                    continue;
                }

                replayService.processIdempotently(record);
                nextOffsets.put(partition, record.offset() + 1);
            }

            for (TopicPartition partition : partitions) {
                if (consumer.position(partition) >= endExclusive.get(partition)) {
                    completed.add(partition);
                    nextOffsets.put(partition, endExclusive.get(partition));
                }
            }

            Map<TopicPartition, OffsetAndMetadata> commit = new HashMap<>();
            nextOffsets.forEach((partition, next) ->
                commit.put(partition, new OffsetAndMetadata(next))
            );
            if (!commit.isEmpty()) {
                consumer.commitSync(commit);
            }
        }
    }
}
```

This is an illustrative skeleton for a synchronous worker, not a complete replay framework. In production code, add consumer closing, timeouts, job cancellation, durable checkpoints, rate limiting, exception handling, and result reporting. `endExclusive` is captured before reading so new records written afterward are excluded from the current replay. When `poll` returns records past the boundary, the worker skips them and marks the partition complete once consumer position reaches the end offset.

A worker consumer configuration can start like this:

```java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
props.put(ConsumerConfig.GROUP_ID_CONFIG, replayGroupId);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "none");
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 100);
```

`replayGroupId` should be dedicated to the job. `enable.auto.commit=false` ensures the application commits only after the handler completes. `auto.offset.reset=none` prevents accidentally reading from the beginning or end of the topic if an offset is invalid. `isolation.level=read_committed` fits when the topic has transactional producers and replay should observe only committed records. For non-transactional topics, this setting still works safely.

In the worker example, `processIdempotently` must complete the sink transaction before `commitSync` is invoked. If the handler fails mid-batch, uncommitted offsets can be re-read on the next run. That is why the sink requires idempotency. Never commit Kafka offsets before target data has been durably persisted.

When running multiple workers, each partition must be owned by only one worker within the same replay job. If workers concurrently write checkpoints for the same partition, they can overwrite progress or process out of order. Partition work cleanly and use locks/leases or job coordination to guarantee ownership.

## 5. Protecting Data and Side Effects During Replay

Replay re-reads old records, yet the target system may have changed since initial processing. Therefore, the handler must clearly decide whether the replay updates state, rebuilds a projection, or re-executes a business command.

### Use Event IDs and Operation IDs to Prevent Duplicates

Keep the original `eventId` during replay. Do not generate a new event ID merely because a record is republished to a replay topic. If an event carries a `businessOperationId`, use it to recognize the same business intent even when the event is re-wrapped or carries new replay metadata.

An inbox table with a unique key such as `(consumerName, eventId)` prevents a consumer from applying the same event multiple times. If a replay might generate a new event ID for the same business action, business keys must also be enforced. External service calls require stable idempotency keys; for instance, every retry of the same charge must reuse the same payment key.

Idempotency must also account for logic versions. A previously processed event might need to update a projection under patched code. If the existing inbox blocks every previously seen event, replay will not run the new logic. In that case, use a separate consumer/version scope for the new projection, build a new read model, or design a checkpointed rebuild process. Never wipe the production inbox en masse just to force a replay to run.

### Preserve Required Ordering

Kafka guarantees order within a single partition. Replaying multiple partitions in parallel can alter completion order across partitions. If business logic depends on per-aggregate order, preserve the same key and process that aggregate's events sequentially. Never assume an event in partition `0` finishes before an event in partition `1`.

If a replay topic has a different partition count than the source topic, keys may map to different partitions. Verify partitioning strategies and ordering requirements before moving data. For certain domains, events must be grouped by aggregate and ordered using a payload sequence/version rather than relying on timestamps.

### Check Retention and Log Compaction

Replay can read only data that still exists. If the start offset is lower than current `beginningOffsets`, the needed data has already been removed from the log by retention or administrative action. Never automatically seek to earliest in this scenario, as that silently alters the replay scope. Stop the job, document the missing data range, and look for alternate recovery sources such as archives, backups, or database audits.

With compacted topics, Kafka may retain only the latest value per key and discard older records. Such topics suit certain current-state recoveries, but do not necessarily provide a full event history to reconstruct every transition. Tombstones also signify deletions and must be handled properly during rebuilds.

## 6. Throttling Speed and Limiting Blast Radius

Replaying too quickly can spike database load, exhaust connection pools, breach external service rate limits, or cause resource contention for production consumers. Treat replay as a distinct workload with its own resource budget.

Common controls:

- Cap `max.poll.records` to control batch size.
- Tune concurrency according to partition count and sink capacity.
- Use a rate limiter or records-per-second cap.
- Pilot on one partition or a small offset slice before scaling up.
- Pause the replay when latency, error rates, or database load exceed defined thresholds.
- Use isolated connection pools, thread pools, and quotas if replay could impact production.
- Avoid running replays concurrently with migrations, backups, or heavy batch jobs competing for the same resources.

Do not rely solely on `max.poll.records` to throttle speed. That parameter caps records returned per poll, not records/second. If handlers finish quickly, workers can still generate heavy load. Use an actual rate limiter or pacing when downstream capacity is constrained.

## 7. Incident Response Procedure for a Replay

An operational procedure you can apply:

### Step 1: Identify Root Cause and Impact

Record the consumer group, topic, partitions, affected offsets or timeframe, application version, incident start/end times, and type of bad data. Determine which side effects succeeded before the failure occurred. If bad writes could still occur, fix or pause the fault source before replaying.

### Step 2: Capture Pre-Replay State

Collect committed offsets, partition beginning/end offsets, consumer lag, DLT record counts, affected business record counts, and current checkpoints. Save these alongside the incident ID for post-run comparison.

### Step 3: Select Strategy and Target Environment

Decide whether to use a replay group, reset the existing group, or use a replay topic. Determine whether replay targets staging, a new read model, or the production sink. If replay will trigger payments, emails, or side-effecting services, verify idempotency keys and business state before authorizing.

### Step 4: Lock the Replay Window

Choose the start offset and exclusive end offset for each partition. Snapshot the end offset at a fixed point in time. Verify start offsets are still within retention and record schemas are compatible with replay code. Document business filters and excluded record types.

### Step 5: Dry Run and Small-Scope Pilot

Verify group ID, topic, partitions, offsets, sink, rate, and permissions. When using offset reset, reviewing `--dry-run` output is mandatory. When using a replay worker, run on one partition or a narrow slice and reconcile counts read, applied, skipped, and side effects.

### Step 6: Run in Batches and Monitor

Run partition by partition or offset slice by offset slice per plan. Watch lag, throughput, errors, retries, DLT, database latency, rate limits, and compensation status. Stop if thresholds are breached, unexpected duplicates appear, or record counts mismatch expectations.

### Step 7: Reconcile and Close the Incident

Compare expected record counts against processed counts, per-partition checkpoints, target data state, and external service side effects. Document unrecoverable records, records needing manual handling, and changes executed. Close the incident only once results are confirmed and the replay job is stopped.

## 8. Tracking Progress, Errors, and Resumability

A replay job must persist durable state rather than relying solely on console logs. Useful fields to store include:

| Field | Purpose |
|---|---|
| `replayJobId` | Identifier for the replay execution |
| `incidentId` | Link to the originating incident |
| `sourceTopic`, `partition` | Data source being processed |
| `startOffset`, `endOffsetExclusive` | Approved replay boundaries |
| `lastProcessedOffset` | Durably processed progress |
| `status` | `PLANNED`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`, or `CANCELLED` |
| `processedCount`, `skippedCount`, `failedCount` | Outcome counters |
| `startedAt`, `updatedAt`, `completedAt` | Operational timestamps |
| `lastError` | Most recent error for investigation |

Checkpoints must be updated after sink side effects commit. If the application stops after sink commit but before checkpointing, the record may be reprocessed; idempotency must protect that scenario. If the checkpoint is written before the sink commits, the application could skip the record on restart even though the effect never completed.

Metrics and logs should include `replayJobId`, `incidentId`, `topic`, `partition`, and offset. Useful metrics include records read/sec, records succeeded, records skipped, errors, retries, lag, per-record duration, checkpoint lag, and job age. Alert when a job stops making progress, a partition stalls, or error counts spike abnormally.

When pausing a job, save per-partition checkpoints and the reason for pausing. When resuming, reuse the same replay job ID and verify checkpoints remain valid. When canceling a job, explicitly record completed partitions and unrun ranges so operators do not mistakenly believe the entire scope was recovered.

## 9. Common Operational Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Resetting offsets while consumer group has active members | Consumers continue committing or rebalancing during reset | Stop all members and verify group is inactive |
| Creating a new replay group with `auto.offset.reset=earliest` without bounds | Re-reads all retained data in the topic | Use `none`, seek explicitly, and snapshot end offset |
| Replaying to the same sink without idempotency | Creates duplicate side effects | Use inbox, business keys, and downstream idempotency keys |
| Bounding only start offset without bounding end offset | Job keeps reading new incoming records indefinitely | Lock end offset exclusive for every partition |
| Relying solely on timestamps to pick offsets | Range may skew due to differing timestamps across partitions | Use `offsetsForTimes` per partition and verify output |
| Failing to check retention | Seeks to data that no longer exists | Compare start offset against beginning offset before running |
| Running replay too fast | Overloads sink or impacts production | Rate limit, pilot small, and watch thresholds |
| Committing offsets before sink commits | Loses business effects when process stops | Commit offsets after durable processing completes |
| Creating a new group ID when resuming an old job | Loses checkpoints and may replay from scratch | Reuse a stable ID tied to the replay job |

## 10. Pre- and Post-Replay Checklist

Before running:

- [ ] Incident has a clear root cause, data scope, and assigned owner.
- [ ] Topic, partitions, start offsets, and exclusive end offsets are defined.
- [ ] Start offsets are still within retention and data is readable.
- [ ] Replay strategy and group ID are explicitly chosen.
- [ ] Sink is idempotent or side effects are isolated under a plan.
- [ ] Replay code is schema-compatible and tested on a small slice.
- [ ] Rate limits, checkpoints, metrics, and stop criteria are configured.
- [ ] If resetting a group, all consumers are stopped and dry-run output is verified.

After running:

- [ ] All partitions reached approved end offsets or incomplete partitions are explicitly documented.
- [ ] Checkpoints were saved after sink commits.
- [ ] Counts of read, processed, skipped, and failed records are reconciled.
- [ ] Target data and side effects are verified.
- [ ] Failed records are routed to retry, DLT, or manual handling per policy.
- [ ] Replay workers/listeners are stopped and resources released.
- [ ] Outcomes and remaining limitations are recorded in the incident record.

## Conclusion

Controlled replay in Spring Kafka starts by identifying the exact topic, partitions, and replay window, then selecting a separate group, offset reset, or replay topic aligned with recovery goals. A safe replay requires fixed end offsets, sink idempotency, durable checkpoints, rate throttling, and post-run reconciliation. Turning these steps into a standard incident response workflow allows operations teams to reprocess affected data while keeping full visibility over scope, progress, and impact of every run.
