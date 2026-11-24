# Replaying Records from an Older Offset

## 1. What is record replay?

Kafka stores records in order within each partition. A consumer group maintains committed offsets for each topic-partition pair. When older data needs to be reprocessed, you can move the consumer group's read position back to an earlier offset and restart the consumers to re-read records from that new position.

This operation is commonly called replay or offset rewind. It changes the consumer group's read position without deleting records from Kafka and without automatically undoing side effects created during previous processing.

For example, consumer group `orders-projection` has read topic `orders` up to offset 900. After discovering a logic bug that corrupted data starting at offset 850, operations can stop all consumers in the group, reset the corresponding partition to offset 850, and restart the application.

~~~mermaid
flowchart LR
    A["Topic orders, partition 0"] --> B["Offsets 840 ... 849"]
    B --> C["Offset 850: start replay"]
    C --> D["Offsets 850 ... 899 re-read"]
    D --> E["Offset 900: previous position"]
    F["Consumer group orders-projection"] --> G["Committed offset reset to 850"]
    G --> C
~~~

Replay is an operational action that directly affects output data. Before running it, confirm the exact group, topic, partition, starting offset, data scope, and how the application handles duplicate records.

## 2. Understanding what offsets mean

An offset is a record's position within a partition, starting from 0 and increasing along the log. Offsets are not topic-wide global sequence numbers; every partition has its own offset sequence.

A consumer group's committed offset indicates the next read position the consumer will resume from. For example:

| Committed offset | Meaning |
|---:|---|
| 100 | Consumer will read from position 100 onward |
| 250 | Positions prior to 250 are confirmed per commit policy; next read begins at 250 |
| 900 | Consumer will resume at 900 |

If you reset committed offset to 850, the consumer begins reading at position 850 if that record is still available. Do not reset to 849 just to read record offset 850; the offset value is already the starting read position.

Offsets can have gaps. Log compaction can remove older records while keeping the offsets of surviving records; aborted transactions can also create offset gaps that consumers with `isolation.level=read_committed` do not return. Therefore, do not assume every integer offset maps to a readable record.

## 3. When is replay needed?

Common operational scenarios requiring replay:

- An application bug caused a batch of records to be processed incorrectly.
- A projection or read model must be recomputed after fixing business logic.
- Input data was supplemented or corrected and downstream workflows must re-run.
- A consumer committed offsets prematurely due to misconfiguration or a handling bug.
- Data needs to be recreated in a test or recovery environment.
- A new consumer group needs to read retained history.

Do not replay simply to test a small change against production consumers. For logic testing, create a dedicated consumer group targeting a separate database/schema to avoid disrupting live streams.

## 4. Replaying with the same group vs. a new group

Two common strategies exist:

| Strategy | Approach | Impact |
|---|---|---|
| Reset existing group's offsets | Move the active group's committed offsets back to an earlier position | Current consumers re-read records; side effects may repeat |
| Create a new group | Use a new group ID and pick the starting read position | Existing group stays untouched; can run in parallel to verify or rebuild |

Use the existing group when recovering the live processing stream itself and duplicate-handling is already in place.

Use a new group when you need to:

- Compare results from a new consumer version against the current version.
- Rebuild projections into a separate table or database.
- Run historical tests without altering production offsets.
- Add an independent subscriber that must receive all retained data.

When a new group has no committed offsets yet, consumers use `auto.offset.reset`. With `earliest`, consumers start from the earliest retained log position; with `latest`, consumers start at the end of the log at the time initial offset is resolved. Never assume a new group always reads from the beginning.

## 5. Prerequisites before resetting offsets

Kafka requires a consumer group to have no active members when resetting offsets with standard admin tools. Stop every instance sharing that group ID.

Before executing:

1. Confirm the application's exact `group.id`.
2. List the topics and partitions the group consumes.
3. Record current committed offsets so the position can be restored.
4. Check each partition's log start offset and log end offset.
5. Determine the target offset and the justification for choosing it.
6. Stop all consumer instances belonging to the group.
7. Verify the group has zero active members.
8. Run dry-run and review output before executing.

Pausing listener containers alone is usually not enough. Consumers may still remain registered members of the group. Stop the containers or shut down all application instances/replicas, then verify group state and member list.

If another deployment accidentally uses the same group ID, stop it as well. Resetting while a consumer remains active can fail or be overwritten immediately when the consumer commits its old offset.

## 6. Inspecting the consumer group before replay

Use the Kafka consumer groups CLI to inspect group status:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --describe \
  --group orders-projection
~~~

Output normally shows topic, partition, current offset, log end offset, and lag. These columns establish the current position and pending backlog.

To check log start offset and log end offset directly, Kafka distributions include `kafka-get-offsets.sh`:

~~~bash
kafka-get-offsets.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --topic orders \
  --time -2

kafka-get-offsets.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --topic orders \
  --time -1
~~~

`--time -2` queries the earliest offset still in the log; `--time -1` queries the latest offset. Script names may differ or be packaged differently in some Kafka versions; use the offset tool included with your distribution.

Inspect members and assignments:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --describe \
  --members \
  --verbose
~~~

Inspect group state if your CLI version supports it:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --state
~~~

Before resetting, verify the group has no active members and is in a state permitting the reset. Exact column and state names can vary by Kafka version. If members remain, locate the running deployment/pod and stop it per operational procedure.

Do not rely solely on an earlier describe run. Re-check right before resetting in case an instance auto-restarted mid-procedure.

## 7. Backing up current committed offsets

Before modifying offsets, save the group's current positions. The Kafka consumer groups CLI provides an export option in reset mode:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --all-topics \
  --export > orders-projection-offsets-before.csv
~~~

The exported file is critical operational data. Store it with restricted access, link it to the change ticket or replay ID, and retain it according to audit policy.

You can export only the topic being replayed instead of all topics in the group, provided the backup covers the full scope needed for rollback. Verify the exported file contains the expected partitions and offsets before proceeding.

Do not hand-edit the export file to guess older offsets. If rollback is needed, use the original saved file and verify with dry-run before executing.

## 8. Choosing the target offset

Target offsets must be chosen from evidence: the offset of a failing record, the offset where faulty logic started, or the timestamp from which data must be reprocessed.

Common position options:

| Option | Meaning |
|---|---|
| `--to-offset N` | Set read position to offset N |
| `--to-earliest` | Move to the earliest retained log start offset |
| `--to-latest` | Move to the log end offset, skipping current backlog |
| `--to-datetime` | Select position based on record timestamp |
| `--by-duration PT2H` | Shift back by a duration relative to current time |
| `--shift-by -N` | Shift current position backward by N offsets |
| `--from-file file.csv` | Set offsets from a prepared export file |

`--to-earliest` does not recover records deleted by retention or removed by compaction. It only moves the consumer to the earliest position currently remaining in the log.

`--to-latest` does not replay old data; it moves the consumer to the end of the log and can skip pending records.

`--to-datetime` relies on Kafka record timestamps. Results depend on the timestamp type and actual timestamps stored in the log. If producers use `CreateTime`, producer clock skew applies; if the topic uses `LogAppendTime`, brokers assign timestamps on append. Verify timezone and timestamp type beforehand.

`--shift-by -N` is relative to the current position. It is convenient for stepping back a fixed count, though error-prone if offsets shifted or partitions have differing log start offsets. For scoped replays, explicit absolute offsets are easier to review.

## 9. Replaying a single partition from a specific offset

Suppose only partition 0 of topic `orders` needs to be reprocessed from offset 850. First run dry-run:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --to-offset 850 \
  --dry-run
~~~

Dry-run previews proposed offset changes without persisting them to the group. Verify:

- Exact group ID.
- Exact topic and partition.
- Current offset matches the backup.
- Target offset equals the intended starting position.
- Target offset falls within the available log range.
- No out-of-scope partitions are altered.

Once the preview is reviewed and the consumer group is completely stopped, execute:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --to-offset 850 \
  --execute
~~~

After executing, run describe again to confirm the new committed offset. Start consumers only after confirming the new position.

## 10. Replaying multiple partitions or an entire topic

To replay all partitions of a topic from the log start offset:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

After reviewing, re-run with `--execute`.

If each partition needs a distinct offset, reset partition-by-partition or prepare an accurate offset CSV file. Never assume a single target offset fits every partition, as write rates, retention, and data ranges can differ per partition.

To replay every topic subscribed by the group, you can use `--all-topics`. This has broad blast radius and risks unintended reprocessing; use it only after verifying every topic in the group needs replay.

## 11. Time-based replay

When only the incident timestamp is known, you can pick positions by timestamp:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-16T08:30:00.000 \
  --dry-run
~~~

Replace the example timestamp with a normalized timestamp, preferably in UTC. The tool looks up the offset matching the record timestamp in each partition; partitions with no records at or after that timestamp may be set to the end of the log depending on tool behavior.

For a relative duration, you can use:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders \
  --reset-offsets \
  --by-duration PT2H \
  --dry-run
~~~

`PT2H` represents two hours in ISO-8601 duration format. Inspect the dry-run output for every partition; never treat timestamps as exact absolute offsets. If an issue started mid-burst among closely timestamped records, inspect metadata to determine exact offsets before resetting.

## 12. Relative offset shifting

If a partition's current committed offset is 900 and you need to replay roughly the latest 50 offsets, you can test `--shift-by -50`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --topic orders:0 \
  --reset-offsets \
  --shift-by -50 \
  --dry-run
~~~

The expected result moves the read position 50 offsets earlier than the current committed offset. Check dry-run output to confirm the new offset stays within log start/end bounds and covers the exact intended range.

If the current offset moves, the same shift-by command yields a different result. Never save relative commands as fixed runbooks without recording the group's prior state.

## 13. Restoring offsets from a backup

If replay causes issues and you must return the group to its prior position, use the saved export file:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --from-file orders-projection-offsets-before.csv \
  --dry-run
~~~

Review every partition in the output. Once verified, execute:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker.example.com:9092 \
  --command-config client.properties \
  --group orders-projection \
  --reset-offsets \
  --from-file orders-projection-offsets-before.csv \
  --execute
~~~

Restoring offsets changes only the next read position. It does not erase side effects already applied during replay. If consumers wrote extra rows to a database or called external APIs, run corresponding compensation or output rebuild procedures.

## 14. Safe replay workflow in production

A workflow suitable for an operational runbook:

~~~mermaid
flowchart TD
    A["Identify incident and scope"] --> B["Select group/topic/partition/offset"]
    B --> C["Back up committed offsets"]
    C --> D["Stop all consumers in group"]
    D --> E["Verify group has no members"]
    E --> F["Run reset --dry-run"]
    F --> G{"Result correct?"}
    G -->|No| H["Abort and investigate"]
    G -->|Yes| I["Review changes"]
    I --> J["Run reset --execute"]
    J --> K["Describe to verify new offsets"]
    K --> L["Start consumers"]
    L --> M["Monitor lag, throughput, and output"]
    M --> N["Reconcile replay results"]
~~~

Detailed operational steps:

1. Open a change record documenting the replay reason and owner.
2. Identify the affected records or start timestamp.
3. Check retention, compaction, and log start offsets.
4. Export current offsets.
5. Stop every consumer instance in the group.
6. Confirm zero active members remain.
7. Run reset dry-run and save the output.
8. Review target topics, partitions, and new offsets.
9. Execute the reset.
10. Describe the group to confirm committed offsets.
11. Start consumers gradually if load throttling is needed.
12. Monitor lag, processing rate, errors, duplicates, and output data.
13. Reconcile results, then close the change record.

For large replays, split by partition or time windows to control load and simplify verification.

## 15. Preventing duplicate side effects

Replaying causes old records to be processed again. Kafka does not automatically know whether business logic already applied a side effect earlier.

Example listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreatedEvent event) {
    orderProjectionRepository.apply(event);
}
~~~

If `apply()` adds amounts to total revenue on every invocation, replay will double-count. Design idempotency using an event ID or business key:

~~~java
@Transactional
public void apply(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
        .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjectionRepository.upsert(
        event.orderId(),
        event.status()
    );
}
~~~

This example must ensure inserting the event ID and updating the projection occur within the same database transaction. Enforce a unique constraint on the event ID so two concurrent consumers cannot process the same event twice either.

Other strategies:

- Upsert state instead of blindly incrementing totals.
- Maintain a processed-events table with a unique key.
- Pass idempotency keys when calling external APIs.
- Use a transactional outbox for downstream event publishing side effects.
- Have compensation workflows when side effects cannot be made idempotent.

Kafka transactions can coordinate Kafka outputs and offsets within Kafka's boundary. They do not roll back databases, emails, payments, or HTTP calls when records are replayed.

## 16. Replaying to rebuild a projection

If the goal is to recompute an entire read model after fixing code, resetting the live production group may not be the safest option. A lower-risk strategy is rebuilding into a new projection:

1. Create a new target table or database.
2. Create a new consumer group, e.g., `orders-projection-v2-rebuild`.
3. Select the starting offset and configure `auto.offset.reset` appropriately.
4. Run the new consumer to read retained history.
5. Verify record counts, states, and business invariants.
6. Reconcile data between the old and new projections.
7. Switch read traffic to the new projection once criteria are met.
8. Keep the old projection for the defined rollback window.

This lets you compare both outputs and roll back traffic without resetting the group serving production. Handle new records arriving during the rebuild—for instance, by replaying up to a high-water mark and catching up the tail before cutover.

## 17. Limits from retention, compaction, and transactions

Replay can only read data still present in the Kafka log.

**Retention:** records older than the retention time or size limits may already be deleted. `--to-earliest` only moves the consumer to the current log start offset; it cannot restore purged data.

**Log compaction:** Kafka can retain only the latest record per key and discard older values. If every historical state transition is needed, a compacted topic may no longer hold all events. Tombstones can also be purged after their configured retention delay.

**Transactional records:** consumers with `isolation.level=read_committed` only see records from committed transactions. Records from aborted transactions are not returned as valid data, and open transactions can stall the read boundary at the last stable offset.

**Timestamps:** `CreateTime` depends on producer clocks; `LogAppendTime` is assigned by brokers. Time-based replay must account for the topic's timestamp type.

Before replaying long histories, check retention, compaction, log start/end offsets, timestamps, and isolation level. If data is no longer in Kafka, rely on an archive or appropriate backup source.

## 18. Replaying from inside a Spring Kafka application

For one-off operational replays, resetting a consumer group via Kafka CLI is usually easier to review and audit. In certain application flows, a consumer may need to seek to a specific offset programmatically.

Spring Kafka supports `ConsumerSeekAware` so a listener receives callbacks when partitions are assigned and can invoke seek. Illustrative example:

~~~java
import java.util.Map;

import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.listener.ConsumerSeekAware;
import org.springframework.kafka.annotation.KafkaListener;

public class ReplayAwareListener implements ConsumerSeekAware {

    @Override
    public void onPartitionsAssigned(
            Map<TopicPartition, Long> assignments,
            ConsumerSeekCallback callback) {

        assignments.forEach((partition, position) -> {
            if (partition.topic().equals("orders")
                    && partition.partition() == 0) {
                callback.seek("orders", 0, 850L);
            }
        });
    }

    @KafkaListener(
        topics = "orders",
        groupId = "orders-projection-replay"
    )
    public void handle(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Business processing.
    }
}
~~~

This example illustrates the concept of seeking upon partition assignment. In real applications, the listener container must manage callbacks properly across its lifecycle; seeks must be scoped by partition, replay condition, and consumer state. Never hard-code an offset in a production listener, as every rebalance re-invokes the callback.

Seeking changes the consumer's current read position. To persist that position across restarts, commit offsets per policy. Across multiple instances in a group, only the consumer currently owning a partition can seek that partition.

Never call `Consumer.seek()` arbitrarily from business threads outside the consumer thread. Use Spring Kafka seek APIs such as `ConsumerSeekCallback`, `ConsumerSeekAware`, or supported container mechanisms.

## 19. Testing replay before production

Test the procedure on a dedicated test topic and consumer group:

1. Create a topic with several partitions.
2. Send records with deterministic keys and event IDs.
3. Run the test consumer group to process and commit offsets.
4. Stop the consumer group.
5. Export committed offsets.
6. Dry-run reset to an earlier offset.
7. Execute the reset.
8. Restart the consumer.
9. Verify records are redelivered.
10. Verify idempotency prevents duplicate side effects.
11. Test restoring offsets from the exported file.

Tests should also cover edge cases:

- Target offset below log start offset.
- Target offset above log end offset.
- Partition with no records at the chosen timestamp.
- Group still having active members.
- Compacted topic missing historical records.
- Consumer using `read_committed` on a transactional topic.
- Replaying multiple partitions with distinct offsets.
- Application restart mid-replay.

Use Embedded Kafka or Testcontainers for integration tests. For ACLs, TLS, and SASL, enable matching security mechanisms on test brokers; an unsecured broker does not prove offset-reset permissions in production.

## 20. Monitoring during and after replay

During replay, monitor:

| Metric | Meaning |
|---|---|
| Current/committed offset | Position confirmed by the consumer group |
| Log end offset | End of partition log |
| Consumer lag | Offsets remaining to catch up as reported by Kafka |
| Records consumed rate | Record reading rate |
| Processing latency | Time to process each record |
| Error/retry/DLT rate | Errors arising during replay |
| Duplicate/idempotency count | Records recognized as already processed |
| Database/API load | Impact of replay on dependencies |

Lag can rise or fall depending on ongoing producer write rates versus replay speed. Replaying one partition concentrates load on one consumer; replaying many partitions at once can spike load on downstream databases or APIs.

If dependencies start overloading, stop or reduce concurrency per runbook. Never raise concurrency beyond useful partition count or downstream capacity.

## 21. Security and administrative permissions

Resetting offsets is a consumer group administrative operation. Use an operational principal with least-privilege permissions for the relevant group and topics.

- Do not use superuser credentials for routine replays.
- Use `--command-config` to supply TLS/SASL settings from a secured file.
- Never enter passwords or JAAS strings directly into shell command history.
- Store export files and dry-run outputs in access-controlled locations.
- Record an audit log: group, topic, partition, old offset, new offset, timestamp, and operator.
- Stop only the consumer group being replayed; do not disrupt unrelated groups on the same topic.

On Windows, Kafka distributions typically ship `kafka-consumer-groups.bat`. Option syntax is the same; adjust the script name and file redirection for your shell.

## 22. Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Reset rejected because group is active | Consumer members still running | Stop all instances and verify group state |
| Replay misses older records | Target offset below log start or data purged by retention | Check log start offset and archives |
| Consumer re-reads too much data | Used `--to-earliest` or new group with wrong scope | Pick explicit offsets and review dry-run |
| Consumer skips backlog | Unintentionally used `--to-latest` | Reset to desired offset before starting |
| Offsets jump right after reset | Old consumer still running or app commits immediately on restart | Stop all members and verify group before/after reset |
| Replay output differs from expectations | Timestamp type, timezone, or compaction | Check timestamps and retention/cleanup policy |
| Database has duplicate rows | Non-idempotent side effects | Use event IDs, unique constraints, or upserts |
| Replay overloads downstream | Read rate exceeds dependency capacity | Limit concurrency/rate and chunk replay scope |
| Cannot restore prior state | Forgot to export offsets before resetting | Always back up committed offsets prior to changes |

## 23. Checklist for replaying records from an older offset

- [ ] Confirmed exact consumer group.
- [ ] Confirmed topic, partitions, and starting offsets.
- [ ] Checked log start/end offsets and retention.
- [ ] Checked compaction, timestamp type, and isolation level.
- [ ] Exported current committed offsets.
- [ ] Stopped all consumers in the group.
- [ ] Verified zero active members remain in the group.
- [ ] Ran `--reset-offsets --dry-run`.
- [ ] Reviewed every partition and proposed offset.
- [ ] Used `--execute` only after confirming the preview.
- [ ] Re-described the group to verify new offsets.
- [ ] Started consumers and monitored lag, errors, and throughput.
- [ ] Protected side effects with idempotency/deduplication.
- [ ] Reconciled output data after replay.
- [ ] Saved audit records and offset backup files.
- [ ] Prepared an offset rollback and side-effect compensation plan if needed.

Replaying records from an older offset is a practical way to recover from bugs or rebuild projections, but it alters the consumer group's read position and re-executes business logic. Stop the group, back up offsets, check log bounds, run dry-run, execute under control, and reconcile outputs. When consumers are idempotent and dependencies are shielded from traffic spikes, replay in Spring Kafka becomes predictable and safe.
