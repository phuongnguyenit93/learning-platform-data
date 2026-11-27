# Resetting Offsets for Recovery and Assessing Impact Scope

Kafka tracks consumption progress separately for each consumer group and each partition. When a consumer processes data incorrectly, misses a range of events, or needs to rebuild a projection, operations teams can reset committed offsets so the group re-reads from a selected position. Conversely, when skipping a known unnecessary segment of data is desired, offsets can be moved forward.

Resetting offsets changes a group's consumption progress; it does not edit or delete records in the topic. Therefore, the impact scope depends on the chosen group, topic, and partitions. Resetting backward can cause messages to be reprocessed and duplicate side effects; resetting forward can cause unprocessed messages to be skipped. In a Spring Cloud Stream application, every instance sharing the same group is affected by that offset change.

This lesson guides you through inspecting group status, planning resets, using the Kafka CLI in dry-run mode, evaluating the impact of each offset option, and recovering safely in a Spring Cloud Stream environment.

## Learning Objectives

After this lesson, you will be able to:

- Explain committed offsets and the scope of a consumer group.
- Identify the exact group, topic, and partitions needing recovery.
- Read current offset, log end offset, log start offset, and consumer lag.
- Distinguish backward resets for replay from forward resets for skipping data.
- Use `kafka-consumer-groups.sh` to simulate and execute resets.
- Choose `earliest`, `latest`, explicit offset, `shift-by`, or timestamp appropriately.
- Assess the impact on all Spring Cloud Stream instances sharing a group.
- Plan snapshots, rollbacks, idempotency, and post-reset monitoring.
- Distinguish regular consumer offset resets from Kafka Streams state recovery.

## 1. Offsets Are Stored per Group and Partition

Kafka appends records in each partition with monotonically increasing offsets. A consumer group stores committed offsets independently for every partition it consumes. For example, group `order-processor` might have committed:

| Topic | Partition | Committed offset | Log end offset | Illustrative lag |
|---|---:|---:|---:|---:|
| orders | 0 | 120 | 150 | 30 |
| orders | 1 | 95 | 110 | 15 |
| orders | 2 | 210 | 210 | 0 |

The committed offset typically indicates the next position the consumer will read. If partition 0's committed offset is 120, the consumer resumes from record offset 120 provided that record still exists in the log. Resetting back to 80 lets the consumer re-read from offset 80 through newer data. Resetting forward to 140 causes the consumer to skip records 120 through 139 under the group's new progress.

When a topic has multiple groups, each group maintains independent progress. Resetting group `order-processor` does not alter committed offsets of group `order-audit`. Within the same group, all instances sharing partitions are affected by the new committed offsets upon their next assignment/startup.

~~~mermaid
flowchart TD
    T["Kafka topic: orders"] --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    P0 --> G1["Group: order-processor<br/>offset 120"]
    P1 --> G1
    P2 --> G1
    P0 --> G2["Group: order-audit<br/>independent offset"]
    P1 --> G2
    P2 --> G2
~~~

Resetting offsets does not modify data in the topic, does not alter other groups' offsets, and does not clear DLQs. It only changes the position from which the group is instructed to resume consuming.

## 2. When Should You Reset Offsets?

Common scenarios:

- A consumer had a logic bug and persisted bad state; a range of events must be re-run after fixing the bug.
- A projection or read model needs to be rebuilt from retained source data.
- A slice of records is confirmed invalid and a business decision approves skipping them.
- A consumer group was advanced too far forward due to misconfiguration or operator mistake.
- A time window must be replayed for data reconciliation.
- Group progress needs to be resynchronized after changing processing logic.

Before resetting, answer three questions:

1. **What is the goal?** Re-read to repair state, or skip data?
2. **What scope needs changing?** One partition, one topic, or all topics of the group?
3. **What side effects could be repeated or skipped?** Database writes, sending emails, issuing payment commands, or updating external services?

Never reset simply because consumer lag increased. Lag can be caused by slow processing throughput, too few partitions, slow dependencies, or stopped consumers. Resetting offsets does not fix throughput bottlenecks; resetting forward can drop pending work.

## 3. Assessing Impact Scope Before Acting

A reset command must specify accurately:

- Kafka cluster and bootstrap servers.
- Consumer group ID.
- Target topic.
- Specific partitions or all partitions of the topic.
- New offset position.
- Running instances using that group.
- Downstream systems that might receive messages again.

In Spring Cloud Stream, the group is declared on the input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
~~~

Replicas of the same application using group `order-processor` belong to the same consumer group. Resetting this group affects consumption progress across all replicas, not just one pod or one instance.

If multiple bindings share the group or another application also uses that group ID, they may share the same consumption progress. Inspect deployment configurations and group members before executing.

### Inspecting Group Status

List groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

View offsets and lag:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

View group state and members (depending on Kafka CLI version):

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor \
  --state
~~~

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor \
  --members \
  --verbose
~~~

Inspect the output to confirm whether the group is stable or rebalancing, which partitions are assigned to which members, and where lag sits. Flag names can vary across distributions or versions; check `kafka-consumer-groups.sh --help` on the exact Kafka CLI you are operating.

## 4. Stop Consumers Before Resetting

The Kafka CLI requires the group to have no active consumers when resetting offsets. If the group still has members, reset commands are typically rejected or risk conflicting with active consumption progress. Therefore:

1. Stop all replicas of the application using the target group.
2. Pause autoscalers or controllers that might automatically recreate pods.
3. Stop any other jobs, workers, or applications sharing the same group ID.
4. Wait until the group has no active members.
5. Re-check group status and offsets.
6. Run dry-run, review the output, and only then execute.

Do not merely scale one deployment to 0 if another application uses the same group. Also check scheduled jobs or consumers running outside Kubernetes.

After resetting, restart consumers only once you have confirmed the new offsets and scope match the plan.

## 5. Snapshot Committed Offsets Before Making Changes

Before an operation affecting production, save current offsets so progress can be restored if a reset goes wrong. The Kafka CLI supports exporting group offsets to a file during the reset workflow.

Example exporting offsets as a snapshot:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-current \
  --dry-run \
  --export > order-processor-offsets.csv
~~~

The example redirects exported stdout data to `order-processor-offsets.csv`. Depending on the Kafka version, combining `--export` with `--dry-run` may behave differently. Check your installed CLI's help and verify the file was created with group, topic, partition, and offset intact. Never treat a command run as a valid snapshot without inspecting the actual file.

An offset snapshot file must be protected like operational data. Record:
- Cluster and export timestamp.
- Group ID.
- Topic/partition.
- Pre-reset committed offset.
- Operator or process executing it.
- Goal and reason for the reset.

Do not manually edit an export file without verifying its format. If using the file to import/restore offsets, preserve the exact structure required by the CLI.

## 6. Always Dry-Run Before Execute

The Kafka CLI supports `--reset-offsets` in simulation mode and execution mode. Without `--execute`, reset commands normally display proposed offset changes without writing changes to the group. Pass `--dry-run` to make simulation intent explicit.

Example previewing the impact of resetting all partitions of a topic to earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Review the output for every partition:
- Current offset.
- Proposed offset after reset.
- Whether the partition is modified.
- Whether any partition has no data left or an unexpected state.

Only when the output matches the approved scope should you re-run with `--execute`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Never skip dry-run because a reset command can alter many partitions simultaneously. If dry-run output looks wrong, stop and verify group, topic, partitions, and reset options before proceeding.

## 7. Choosing a New Position: earliest, latest, and Explicit Offset

The Kafka CLI supports several offset placement strategies. Each strategy has a different impact scope.

| Option | Target position | When to use |
|---|---|---|
| `--to-earliest` | Earliest retained offset in each selected partition | Rebuild data from all retained log history |
| `--to-latest` | Current end of log | Skip backlog and consume only new data |
| `--to-offset N` | Offset N in selected partitions | Restart from a known milestone |
| `--shift-by N` | Shift current committed offset by N | Move backward or forward by a relative count |
| `--to-datetime` | Position matching a timestamp | Replay starting from a point in time |
| `--by-duration` | Position going back a duration from now | Replay a time window |
| `--to-current` | Keep current position | Export/reconcile offsets without changing progress |

### Resetting to earliest

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-rebuild \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

`earliest` is the smallest readable offset still in the log, not necessarily 0. If retention has deleted older segments, resetting cannot recover those records.

### Resetting to latest

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group live-monitor \
  --topic system-events \
  --reset-offsets \
  --to-latest \
  --dry-run
~~~

`latest` moves the read position to the current end of the log. The group skips any backlog existing at reset time and receives only records written afterward. Use only when skipping old data has been approved.

### Resetting to an Explicit Offset

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:1 \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
~~~

This example targets partition 1 of topic `orders`. Offset 500 is where the consumer will begin reading next if that offset is valid in the partition. Check log start/end offsets beforehand; out-of-range offsets may be rejected or trigger the out-of-range reset policy when the consumer starts.

Topic/partition specification syntax and `--to-offset` behavior can depend on CLI version. Always inspect dry-run output per partition.

## 8. Shifting Offsets with shift-by

`--shift-by` changes the current offset by a relative count:

- Negative value: shifts backward to re-read previously processed records.
- Positive value: shifts forward to skip some unprocessed records.
- Zero: leaves position unchanged.

Example shifting back 100 records on each selected partition:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --shift-by -100 \
  --dry-run
~~~

Example shifting forward 20 records:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --shift-by 20 \
  --dry-run
~~~

Shift-by is computed relative to each partition's committed offset, not across a single global offset range for the whole topic. For partitions with different write rates, the same shift can represent very different time spans.

The resulting offset must lie within readable log bounds. Inspect dry-run output to spot offsets clamped to log start or exceeding log end. Do not calculate new offsets manually assuming every partition has identical progress.

## 9. Resetting by Timestamp or Duration

When you know the time of an incident, you can reset offsets by timestamp rather than guessing an offset number.

Example starting reads from a specific timestamp:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-datetime 2026-11-20T09:30:00.000 \
  --dry-run
~~~

Or re-reading data from the last 2 hours:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --by-duration PT2H \
  --dry-run
~~~

Kafka looks up offsets using record timestamps and partition time-index metadata. If a partition has no matching record or the timestamp falls outside retained data, results may differ from expectations. Verify proposed offsets for every partition before executing.

Distinguish among:
- Business time inside the payload, such as `occurredAt`.
- Kafka record timestamp.
- Time when the consumer received or processed the message.

`--to-datetime` uses the Kafka record timestamp, not business timestamp fields inside the payload. If producers use inconsistent timestamps or data was backfilled, timestamp-based replay may not align precisely with business time.

## 10. Scoping by Topic and Partition

A reset command can target:
- One specific topic.
- One specific partition of a topic.
- Multiple explicitly listed topics.
- All topics consumed by the group, using the corresponding CLI option.

Prefer targeting only the topic and partitions that require recovery. Do not use `--all-topics` if an incident affects only one topic. One group may consume multiple topics; resetting the entire group can cause unrelated business streams to re-read or skip data outside the incident scope.

Example resetting only partition 2:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:2 \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

If a topic has multiple partitions and only one partition failed, resetting only that partition minimizes replay scope. However, if business logic requires cross-entity ordering or keys span multiple partitions, check the relationship between partitions and data before doing a partial reset.

## 11. Impact of Backward Resets: Duplicates and Side Effects

Resetting backward causes the consumer to re-read records that may have already been processed successfully. This can produce:
- Duplicate database records.
- Re-sent emails or notifications.
- Payment or refund commands executed multiple times.
- Re-emitted downstream events.
- Double-counted counters or metrics.
- Projections re-applying older events.

Before resetting backward:
1. Verify whether the consumer is idempotent.
2. Check inbox/deduplication keys by event ID.
3. Check whether external APIs support idempotency keys.
4. Identify which side effects must be paused or run in replay mode.
5. Check event versions and aggregate ordering.
6. Test on a separate group or staging environment if possible.
7. Rate-limit replay so it does not overload downstream systems.

Do not rely on Kafka producer idempotence to stop consumers from reprocessing duplicates. Producer idempotence protects against certain send retries within a producer session; it does not prevent a consumer from repeating side effects when a group re-reads records.

## 12. Impact of Forward Resets: Skipping Data

Resetting forward can cause a consumer to never read records between the old committed offset and the new offset. This risks dropping application-level processing even though the records still remain in the Kafka topic.

Before resetting forward:
- Confirm records in the skipped range truly do not need processing.
- Reconcile business state or prepare compensating reports.
- Check whether another consumer group retains the data for reconciliation.
- Save a snapshot of old offsets.
- Document the reason, offset range, and approver.
- Prepare a backfill process in case the decision to skip turns out wrong.

For example, the committed offset is 100 and you reset to 150. The consumer resumes at 150; records 100 through 149 will not be processed by this group through normal flow. Records still existing in the topic do not mean the consumer will automatically go back to read them.

## 13. Safe Reset Plan in Spring Cloud Stream

A production workflow can be split into phases:

### Phase A: Preparation

1. Identify the actual input binding and group ID.
2. Identify the Kafka cluster and topic.
3. Read offsets/lag per partition.
4. Inspect members in the group.
5. Stop all consumer instances and prevent autoscalers from recreating them.
6. Export/snapshot committed offsets.
7. Determine the new target position and topic/partition scope.
8. Assess duplicate or skipped records.

### Phase B: Simulation

1. Run `--reset-offsets` with the intended option and `--dry-run`.
2. Read the complete output for every partition.
3. Compare old and new offsets.
4. Calculate how many records will be replayed or skipped.
5. Check log start/end offsets and retention.
6. Save dry-run output alongside the change record.

### Phase C: Execution

1. Confirm the group has zero active consumers.
2. Re-run the exact dry-run command with `--execute`.
3. Read CLI output and verify the new committed offsets.
4. Do not start consumers if offsets or scope are wrong.

### Phase D: Startup and Observation

1. Start one instance first if deployment procedures allow.
2. Check logs for group assignment and actual read position.
3. Monitor consumer lag, throughput, and error rate.
4. Monitor duplicate suppression, DLQ, and side effects.
5. Scale remaining instances once the stream is stable.
6. Reconcile business outcomes and close the change record.

In Spring Cloud Stream, `startOffset` is not a regular reset tool for a group that already has committed offsets. Once offsets exist, the binder typically resumes from those offsets. Operational resets via the Kafka CLI have clearer scope and must be coordinated with consumer state.

## 14. Rolling Back a Bad Reset

An offset reset can be reversed by resetting the group back to the saved snapshot offsets, provided the corresponding data still exists in retention and the group is inactive. However, rolling back consumption progress does not automatically undo side effects that already occurred.

For example, a backward reset caused the consumer to resend emails. Moving offsets back to the old value cannot recall already sent emails. A forward reset caused the group to skip payments; moving offsets back can allow reprocessing those records, but only safely if business logic prevents duplicates.

A rollback plan needs:
- Pre-change offset snapshot.
- Verified restore command or import file.
- Procedure to stop consumers before rollback.
- Assessment of side effects triggered during the reset window.
- Business state reconciliation after rollback.
- Recording final offsets and outcome.

If using an exported offset file to restore, verify `--from-file` format for your Kafka CLI version. Run dry-run with the file first, inspect every partition, and only then execute. Never use a snapshot file from another cluster or another group.

Example simulating restore from a snapshot file:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --reset-offsets \
  --from-file order-processor-offsets.csv \
  --dry-run
~~~

Re-run with `--execute` only after verifying that group, topic, partitions, and offsets in the file are all accurate.

## 15. Offset Reset Differs from Kafka Streams State Recovery

The Kafka Streams binder maintains state stores and changelog topics to recover application state. Resetting an input consumer group's committed offsets with `kafka-consumer-groups.sh` does not clear or rebuild state stores.

If you reset only input offsets while keeping old state stores, the application can reapply records onto state that already contains results from the previous run. Outcomes can become corrupt or produce duplicates in state/output.

With Kafka Streams:
- Identify the application ID and input topics.
- Inspect state stores, changelogs, and output topics.
- Stop the application before resetting.
- Use the version-appropriate Kafka Streams application reset procedure when state needs rebuilding.
- Decide whether to clear/rebuild local state and internal topics.
- Never manually delete changelog or internal topics without understanding the impact.
- Test state recovery in an isolated environment before running in production.

A Kafka Streams application reset is a broader process than a regular consumer offset reset. Use Kafka Streams-specific tools and guidance instead of only running group offset reset commands.

## 16. Testing Offset Resets

Tests should use a dedicated Kafka broker or Testcontainers, with topics and groups that can be created/deleted safely.

### Testing Dry-Run

1. Create a multi-partition topic and write sample records.
2. Run a consumer group to establish committed offsets.
3. Stop the consumer.
4. Run reset to earliest with dry-run.
5. Verify the CLI prints proposed offsets while committed offsets remain unchanged.
6. Run reset to latest with dry-run and compare the skipped range.

### Testing Execute

1. Run the verified reset command with execute.
2. Re-read group offsets with `--describe`.
3. Start the consumer.
4. Verify records are read from the new position.
5. Check side effects and duplicate suppression.

### Testing Partition Scope

- Reset one partition and verify other partitions retain their offsets.
- Reset one topic in a multi-topic group and verify remaining topics are unchanged.
- Test both a new group and a group with existing committed offsets.
- Test offsets near log start and log end.
- Test timestamps with no matching records.

### Testing Operational Errors

- Attempt a reset while the group still has active members and verify the CLI rejects it.
- Attempt an out-of-range offset.
- Test snapshot/export and restore from file.
- Simulate a consumer restarting while a reset is being coordinated; verify autoscalers or supervisors do not restart consumers prematurely.

## 17. Reference Commands: Inspecting and Resetting

The examples below use the Kafka CLI against an illustrative environment. Substitute your actual bootstrap server, group, topic, and partition; run `--help` to verify options supported in your installed version.

Inspect group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

Simulate resetting one topic to earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Execute after approving dry-run output:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Simulate resetting a specific partition to a chosen offset:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --group order-processor \
  --topic orders:1 \
  --reset-offsets \
  --to-offset 500 \
  --dry-run
~~~

Verify offsets after the change:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group order-processor
~~~

CLI outputs should be saved with the change record. Do not save only the commands run; also save dry-run output, execute output, and post-reset offsets.

## 18. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Reset is rejected | Group still has active consumers | Stop all members and verify group is inactive |
| Offsets did not change | Ran only dry-run or wrong group/topic | Inspect output and run execute after approval |
| Unexpected partitions were reset | Topic/group scope was too broad | Specify only the required topic and partitions |
| Consumer re-reads old data | Backward reset or selected earliest | Verify idempotency and side effects |
| Consumer skips data | Forward reset or selected latest | Reconcile the skipped offset range |
| New offset is outside log | Chosen offset is before log start or after log end | Check log start/end and run dry-run |
| Consumer lag spikes after reset | Replaying a large volume of records | Rate-limit and scale to downstream capacity |
| Consumer restarts mid-reset | Autoscaler or deployment controller | Pause controller and verify zero members remain |
| Rolled back offsets but data is duplicated | Side effects already ran during replay | Use inbox/idempotency and business reconciliation |
| Kafka Streams state is wrong after reset | Reset only input offsets while keeping old state stores | Use the dedicated application/state reset procedure |

## 19. Lab Exercise: Recovering Group order-processor

Suppose consumer `order-processor` discovered faulty processing logic starting at an identified offset milestone. Build a replay plan:

1. Identify the Kafka cluster, topic `orders`, and group `order-processor`.
2. Inspect group state, members, committed offsets, log start/end offsets, and lag.
3. Stop every instance using the group and pause autoscalers.
4. Save a snapshot of committed offsets across partitions.
5. Identify the exact partitions and earliest offset milestone to re-read.
6. Run reset `--dry-run` for the target partitions.
7. Calculate how many records will be re-read and assess side effects.
8. Confirm the consumer has an inbox/idempotency key by event ID.
9. Execute the reset once dry-run output is approved.
10. Verify new committed offsets using `--describe`.
11. Start one instance and observe the first records read.
12. Monitor lag, throughput, duplicate suppression, DLQ, and business state.
13. If offsets are wrong, stop the consumer and restore from the snapshot using dry-run then execute.
14. Record replay outcomes and close the change record.

Acceptance table:

| Item | Verification criteria |
|---|---|
| Group scope | Exact group ID and all members stopped |
| Topic/partition | Scoped strictly to the area needing recovery |
| Snapshot | Pre-reset offsets saved and verified |
| Dry-run | Proposed offsets reviewed for every partition |
| Execute | Executed only after scope approval |
| Offset verification | Post-reset committed offsets match target |
| Idempotency | Replay does not duplicate unintended side effects |
| Backlog | Lag and processing rate remain within thresholds |
| Rollback | Can restore offsets from snapshot |
| Kafka Streams | State stores/changelogs handled via dedicated procedure |

## Conclusion

Resetting offsets changes a consumer group's progress across selected partitions. Backward resets recover by re-reading records but can repeat side effects; forward resets skip records within the shifted range. It does not modify topic data or alter other groups' progress.

In Spring Cloud Stream, identify the right group from the input binding, stop all instances sharing that group, snapshot offsets, run dry-run, and execute only after evaluating every partition's scope. Monitor offsets/lag upon restart, protect business logic with idempotency, and prepare a rollback plan. If the application uses Kafka Streams, input offset resets must accompany a plan for recovering state stores and changelogs.

## References

- [Apache Kafka – Consumer Group CLI](https://kafka.apache.org/documentation/#basic_ops_consumer_group)
- [Apache Kafka – Consumer Configs](https://kafka.apache.org/documentation/#consumerconfigs)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Kafka Streams – Application Reset Tool](https://kafka.apache.org/documentation/streams/developer-guide/app-reset-tool.html)
