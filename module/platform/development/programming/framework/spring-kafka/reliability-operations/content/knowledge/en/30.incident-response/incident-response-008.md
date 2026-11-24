# Runbook for Topic Data Loss

This runbook guides incident response when a Kafka topic is suspected of having lost records, lost part of its history, or no longer providing data needed by consumers. The first priority is to protect remaining data and determine exactly what happened. Only then should you choose a recovery method from a trustworthy data source.

An empty topic or a consumer failing to read records is not enough to conclude that Kafka lost data. Records may have expired past retention, been removed by compaction, been skipped by a consumer group commit, been filtered at the application layer, or reside on another cluster/topic. Each scenario has a different remedy. In particular, resetting consumer offsets does not restore records already deleted from the log.

## 1. Incident Response Principles

Throughout the incident, follow these principles:

1. **Preserve evidence before changing configuration.** Record topic metadata, topic configs, partition offsets, consumer group offsets, broker health, logs, and timestamps.
2. **Determine scope before recovering.** Identify affected topics, partitions, time windows, keys, or record groups; identify related producers, consumers, and downstream systems.
3. **Distinguish log data from consumer position.** Kafka stores records in partition logs; consumer groups store committed offsets. These two states are independent.
4. **Do not treat replicas as backups.** Replicas provide broker fault tolerance. Record deletions, retention, and compaction are replicated across replicas via the replication mechanism.
5. **Do not reset offsets or republish data without a duplicate-prevention plan.** Replaying can re-trigger side effects such as charging payments, sending notifications, or creating orders.
6. **Do not delete and recreate a topic to try to fix the issue.** Doing so can cause further data loss, change the topic identity, and break links with consumer groups or schema registries.
7. **Close the incident only after verifying data and business flows.** A topic having healthy leaders and ISRs does not prove business data is complete.

If possible, appoint an incident commander to coordinate, a Kafka operator to collect cluster state, and producer/consumer owners to verify business data. Record the start time, recent changes, and every action taken.

## 2. Identify the Exact Incident Type

First, describe what users or systems observe:

- The topic does not exist or is inaccessible.
- One or more partitions contain fewer records than expected.
- Records within a specific time window are missing.
- The consumer group advanced to newer offsets, yet business processing is incomplete.
- Consumer lag rises, stalls, or suddenly drops to 0.
- A key no longer has a value or lacks expected history.
- The producer reports send success, yet the consumer cannot find the records.

Distinguish three concepts:

| Concept | Meaning | Initial check |
|---|---|---|
| Log start offset | Earliest offset still retained in the partition | Compare against the timeframe and offsets under investigation |
| Log end offset | Current end boundary offset of the partition | Correlate with write rate and producer metadata |
| Consumer committed offset | Position the group committed to resume reading | Inspect group, partitions, and commit history |

Offsets are sequential numbers within a partition, not a contiguous count of business records. Compaction, transactions, and internal operations can create offset gaps. Therefore, seeing offset gaps alone does not prove records were lost.

## 3. Initial Response: Preserve State

### 3.1. Record Incident Details

Record at minimum:

- Cluster name, environment, topic, and consumer group.
- Last time data was confirmed complete and first time an anomaly was observed.
- List of affected partitions or undetermined scope.
- Producer/consumer application names and recently deployed versions.
- Recent changes: topic create/delete, partition changes, retention, cleanup policy, ACLs, brokers, storage, or consumer config.
- Correlation/event IDs, sample keys, and authoritative data sources for reconciliation.

Normalize timezones when comparing broker, producer, consumer, and business system logs. Save the command, output, timestamp, and operator for every action taken during the incident.

### 3.2. Inspect Topic and Partitions

Use Kafka CLI with the bootstrap server and authentication details of the exact cluster:

~~~bash
kafka-topics.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --topic orders
~~~

Inspect output per partition:

- Does the partition have a leader or is it offline?
- Does the replica list match expectations?
- Is the ISR missing any replicas?
- Are any partitions leaderless or persistently under-replicated?
- Does the partition count match pre-incident configuration?

If the topic is not found, verify bootstrap servers, cluster, topic name, access permissions, and metadata before concluding the topic was deleted. A client pointing at the wrong cluster can look identical to a missing topic.

### 3.3. Capture Topic Configuration

~~~bash
kafka-configs.sh \
  --bootstrap-server broker1:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Record settings related to retention and durability:

- **cleanup.policy:** `delete`, `compact`, or combined `compact,delete`.
- **retention.ms** and **retention.bytes:** time-based or size-based data retention limits.
- **delete.retention.ms:** how long tombstones are retained in a compacted topic.
- **segment.ms** and **segment.bytes:** log segment roll thresholds.
- **min.insync.replicas:** minimum replicas required in ISR when producers use `acks=all`.

Check broker-level defaults as well if the topic has no overrides. Effective values may differ from defaults remembered by operations prior to the incident.

### 3.4. Record Offsets for Each Partition

~~~bash
kafka-get-offsets.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --time -2

kafka-get-offsets.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --time -1
~~~

With Kafka CLI versions supporting `kafka-get-offsets.sh`, `--time -2` retrieves the earliest offset and `--time -1` retrieves the latest offset. Save outputs for all partitions. If your Kafka version uses different syntax, use the corresponding tool for that version and note the method used.

These two boundaries show the range of log still readable at inspection time. They do not indicate which business records are missing. Compare them against previously recorded offsets or timestamps, producer metadata, consumer logs, and original data sources.

### 3.5. Record Consumer Group State

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group orders-service
~~~

Record current/committed offsets, log end offsets, lag, and partition assignments. To list all groups if needed:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --list
~~~

Consumer group offsets indicate where the group will resume reading. They do not prove records prior to that offset were successfully processed. If the application commits before completing side effects, or commits while asynchronous work is still unfinished, the group can skip records even though business processing never completed.

## 4. Determine Root Cause

Use the indicators below to narrow down the cause. An incident can involve multiple causes at once; for example, a broker outage occurring after retention already deleted part of the history.

### 4.1. Retention Purged Old Data

**Symptoms:** the partition's log start offset has moved past the target offset range; `retention.ms` or `retention.bytes` is bounded; timestamps of missing records fall outside the retained window.

Kafka deletes old log segments once they exceed time or size limits. Segment deletion does not necessarily occur at the exact expiration instant of each individual record; segments are managed at the log segment unit level.

**Verification:**

- Compare target event timestamps against effective retention.
- Check `retention.ms`, `retention.bytes`, broker configs, and segment deletion timestamps in broker logs.
- Compare current log start offsets with offsets recorded prior to the incident.
- Review data growth rate and disk usage during the relevant period.

**Action:** increasing retention protects remaining data in undeleted segments, but does not restore already deleted segments. Recovering lost data requires replaying from the original data source, backups, or an independent copy retaining the needed window.

### 4.2. Log Compaction Removed Older Versions

**Symptoms:** topic has `cleanup.policy=compact` or `compact,delete`; consumer looks for an older event, yet the key now holds only the latest value.

Compaction retains the latest value per key in compacted logs. This fits topics storing current state by key, but does not guarantee preservation of full event history. With `compact,delete`, data is also subject to retention limits.

A tombstone is a record with a key and a null value, representing key deletion in a compacted topic. After `delete.retention.ms`, compaction can remove tombstones and associated older values per compaction rules.

**Verification:**

- Inspect `cleanup.policy`, `delete.retention.ms`, and configuration change history.
- Confirm whether business requirements call for latest state or full event history.
- Reconcile missing keys against creation, update, and tombstone events from the source.

**Action:** if compaction has already removed older versions, increasing retention or changing cleanup policy cannot make them reappear. Restore from an event store, backup, or replay source. If full history must be preserved, design an event-history topic with an appropriate retention policy rather than relying on a compacted topic.

### 4.3. Consumer Group Committed Past the Records

**Symptoms:** records still exist in the log, yet the group's committed offset has moved past the target position; application logs show successful commits before business processing finished.

Common scenarios:

- Consumer commits offsets before writing to a database or calling downstream services.
- Asynchronous processing sends acknowledgments before tasks finish.
- A buggy deployment recorded offsets after skipping records.
- An operator moved offsets forward, or the application used a different group ID than expected.

**Verification:** compare log start/end offsets, committed offsets, processing timestamps, and transaction/DB logs. Determine whether the records are still in the log. Inspect group ID, `auto.offset.reset`, acknowledgment mode, manual commits, and asynchronous processing logic.

**Action:** if the records remain in the log, replay using a dedicated recovery consumer group to verify and reprocess. If the current group's offsets must be modified, account for running consumers, duplicates, and side effects; see the offset recovery procedure below.

### 4.4. Producer Never Wrote or Wrote Elsewhere

**Symptoms:** producer has no acknowledgment metadata, send errors, or timeouts; records appear in a different topic/cluster; partition traffic is lower than upstream metrics.

Check:

- Producer logs, callback errors, retries, delivery timeouts, and buffer exhaustion.
- `acks`, idempotence, retries, and transaction commits.
- Bootstrap servers, topic name, serializer, partitioner, keys, and schemas.
- Whether ACLs allow the producer to write to the right topic.
- Whether the producer wrote to a different cluster due to environment config or secrets.

If the producer uses `acks=0`, the client receives no broker confirmation that records were written. With `acks=1`, the leader can acknowledge before followers replicate. `acks=all` waits for the ISR per Kafka mechanics and pairs with `min.insync.replicas` to enforce durability. Current producer config does not prove the config at incident time; inspect deployment history and corresponding metrics.

### 4.5. Replica or Leader Election Lost Unreplicated Data

**Symptoms:** broker outage, ISR shrink, under-replicated partitions, abnormal leader elections, or logs mentioning unclean leader election around the data loss timeframe.

If an old leader acknowledged records before replicas caught up, an out-of-sync replica could be elected leader under configurations permitting unclean election. In that case, records acknowledged by the old leader may no longer exist on the new leader's log.

**Verification:**

- Inspect broker logs, controller logs, ISR changes, leader changes, and broker disconnect timestamps.
- Correlate producer acknowledgments, `min.insync.replicas`, and ISR state at send time.
- Inspect metrics for under-replicated partitions, replica fetch lag, and storage errors.
- Determine whether any broker or old replica still holds un-overwritten segments; preserve disks and logs for dedicated Kafka team investigation.

**Action:** restoring a broker/replica helps only if required data still exists on a usable copy. Do not force an old replica to become leader or alter election policies arbitrarily. If no valid replica retains the records, an independent recovery source is required.

### 4.6. Topic Was Deleted and Recreated

**Symptoms:** topic vanished and reappeared; partition offsets restarted from 0; topic ID or metadata differs from before; audit logs or admin commands show topic deletion.

Recreating a topic with the same name does not restore old logs. The new topic may have the same partition count, yet data and topic identity are different. Check audit trails, broker/controller logs, automation, and deployment scripts for delete/create operations.

**Action:** halt automation that might keep deleting/recreating topics. Preserve relevant cluster logs and storage. Restore from backups or upstream sources into a separate recovery topic, verify completeness, and only then transition consumers to the recovery flow as planned.

### 4.7. Records Exist but Application Does Not See Them

**Symptoms:** offsets and broker metrics show records were written, yet consumers show no processing or business dashboards show no data.

Check:

- Is the consumer subscribed to the right topic and pattern?
- Are group ID, partition assignments, and ACLs correct?
- Is a `read_committed` consumer skipping uncommitted or aborted transactional records?
- Are filters, deserializer errors, schema incompatibilities, exception handlers, or error handlers routing records to a DLT?
- Are records being dropped by business logic or downstream queries?
- Is the dashboard filtering by the wrong timestamp, tenant, key, or status?

Verify raw records using a test consumer in a separate group; never use the production group for probing. If a new group reads the records, the issue likely lies in consumer offsets or consumer logic. If raw records are absent as well, continue investigating retention, compaction, producers, or replication.

## 5. Quick Investigation Decision Tree

~~~text
Business record is missing
        |
        v
Correct cluster, topic, and partition?
   | No                     | Yes
   v                        v
Fix endpoint/name        Record still in log?
                            | Yes                | No
                            v                    v
                    Check group offsets,     Check retention,
                    ACLs, filters, schema,   compaction, delete,
                    transactions, DLT        producer, and replication
                            |                    |
                            v                    v
                    Controlled replay        Find backup or independent
                    if needed                data source to replay
~~~

This diagram helps pick the first investigation branch. Do not treat a single branch as a final conclusion before reconciling logs and business data.

## 6. Data Recovery Procedure

### 6.1. Select a Recovery Source

Prioritize sources that can prove data completeness and ordering:

1. **Original source of truth:** database, transactional outbox, event store, or the system that generated the events.
2. **Backup or independent copy:** backup cluster, object storage holding events, MirrorMaker/Cluster Linking, or DR system retaining the target window.
3. **Reconstructible business source:** historical data sufficient to rebuild events with matching IDs, keys, timestamps, and payloads.
4. **DLT or retry topics:** use only if confirmed to contain the exact records needing recovery; DLTs typically hold only failed records, not a full copy of the topic.

Replicas in the same cluster are not a backup source for records removed by retention, compaction, or deletion. Once a deletion replicates, all replicas may lose those records together.

### 6.2. Create an Isolated Recovery Area

Prefer restoring into a separate topic, such as `orders-recovery-incident-2026`, or a recovery cluster. This allows you to:

- Verify counts, partitions, keys, timestamps, and payloads before impacting production consumers.
- Pilot the recovery consumer and measure duplicates.
- Keep original data and replayed data separated for auditing.
- Switch traffic only once the business owner confirms results.

Choose partition count, replication factor, cleanup policy, retention, and ACLs per recovery requirements. If per-key ordering is mandatory, use the same partitioning rules and ensure records with the same key route to the intended partitions. Do not assume republishing with a different partition count preserves equivalent ordering to the old topic.

### 6.3. Define the Data Range to Replay

Build a manifest by partition or business key:

- Start and end timestamps in UTC.
- Start/end offsets if reliable checkpoints exist.
- Keys or event IDs to recover.
- Expected record count and byte volume.
- Downstream processing status.

Do not mechanically infer lost record counts by subtracting offsets. Compaction, transactions, and offset gaps can make offset deltas differ from business record counts. Use event IDs or the source of truth to determine the exact record set whenever possible.

### 6.4. Replay Safely

Before replaying:

- Confirm the business owner approves re-running side effects.
- Use idempotency keys or deduplication by event ID.
- Choose a dedicated replay group or isolated recovery consumer.
- Throttle replay speed so databases/APIs are not overloaded.
- Record the source, incident ID, replay window, and outcome.
- Define how to handle late-arriving events and partially processed events.

When producers republish data, preserve original keys, schemas, headers, and business timestamps if downstream systems depend on them. You may add headers indicating the record is a replay and its incident ID, but do not overwrite source metadata needed for audits.

If downstream is not idempotent, stage records in a validation area and build a reconciliation workflow before allowing live processing. Never replay directly into a topic actively consumed by production consumers without controlling duplicates and ordering.

## 7. Recovering Consumer Offsets When Records Still Exist

Use this section only after confirming the records to be re-read still exist in the log. Resetting offsets changes where the group reads; it does not recreate deleted data.

### 7.1. Prefer a Separate Recovery Group

Creating a dedicated consumer group for testing/replaying is generally safer than altering offsets on the production group. A separate group can re-read data without disrupting the live application's committed positions. However, consumer side effects must still be controlled.

### 7.2. Preview Before Resetting

The example below only simulates resetting a group to the topic's earliest offset. CLI syntax may vary by Kafka version:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Inspect output carefully per partition. `--to-earliest` moves the group only to the currently remaining log start offset; it cannot re-read segments expired by retention or records removed by compaction.

If only one partition or offset range is affected, scope the reset accordingly. With `--to-offset`, verify the exact target offset and what that offset represents on each partition. With `--to-datetime`, verify timestamp and timezone; offsets are resolved by record timestamp, which does not guarantee alignment with exact business boundaries.

Execute the reset only after the owner approves the preview and group consumers are stopped or coordinated per procedure. For example, an execution command replaces `--dry-run`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

This operation mutates group state. Do not copy/paste and run this example during an incident; substitute the topic, group, partitions, and offsets from your investigation, then record approvals and output.

### 7.3. Monitor After Reset

Start consumers according to plan and monitor:

- Lag draining at the expected rate.
- Records processed in required order.
- Duplicates and side-effect errors.
- Retries, DLT volume, and commit errors.
- Database/API latency when replay generates heavy load.

If the group begins reprocessing previously completed data, reconcile via event IDs and idempotency keys. Do not declare success simply because lag reaches 0; verify business record counts and downstream results.

## 8. Useful Inspection Commands

The commands below are diagnostic examples. Substitute bootstrap servers, topics, groups, and authentication settings for your incident environment.

**Describe topic and replica status**

~~~bash
kafka-topics.sh --bootstrap-server broker1:9092 --describe --topic orders
~~~

**Inspect topic configuration**

~~~bash
kafka-configs.sh --bootstrap-server broker1:9092 --entity-type topics --entity-name orders --describe
~~~

**Inspect consumer group by partition**

~~~bash
kafka-consumer-groups.sh --bootstrap-server broker1:9092 --describe --group orders-service
~~~

**Get earliest offset**

~~~bash
kafka-get-offsets.sh --bootstrap-server broker1:9092 --topic orders --time -2
~~~

**Get latest offset**

~~~bash
kafka-get-offsets.sh --bootstrap-server broker1:9092 --topic orders --time -1
~~~

**Read records using an isolated inspection group**

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server broker1:9092 \
  --topic orders \
  --group orders-incident-inspection \
  --from-beginning \
  --property print.key=true \
  --property print.timestamp=true
~~~

An inspection consumer can read large volumes of data and load brokers. Limit duration, partitions, or message count using CLI flags supported by your version. Never use a production group ID for console consumer debugging.

## 9. Recovery Verification Criteria

Mark recovery complete only when evidence exists on both Kafka and business sides:

1. The required record set is identified by event ID, key, time range, or source of truth.
2. Recovered data matches the reference source in counts, schemas, keys, timestamps, and payloads.
3. Partitions and replication are healthy; no offline partitions or prolonged under-replicated partitions exceed operational thresholds.
4. The consumer group reads from the right topic and partitions and drains the backlog as planned.
5. Duplicates, late events, and per-key ordering have been verified.
6. Databases and downstream services reflect accurate business state after replay.
7. Producers continue writing to the right cluster/topic and metrics show no ongoing record loss.
8. The business owner confirms data completeness or explicitly accepts any unrecoverable portion.

If full data cannot be recovered, document the missing time range, partitions, keys or event IDs, sources checked, why recovery is impossible, and the business decision. Never report "recovered" based solely on the topic becoming operational again.

## 10. Post-Incident Monitoring

During the monitoring phase, watch:

- Producer send success/errors, retries, timeouts, and throughput by topic/partition.
- Broker leaders, ISR, under-replicated partitions, disk capacity, network, and request latency.
- Consumer lag, processing latency, commit errors, rebalances, and DLT rates.
- Log growth rate, effective retention window, and remaining disk capacity.
- Event counts at the source of truth compared to events processed downstream.

Keep dashboards under observation long enough to cover relevant traffic cycles. If the incident occurred during peak hours, re-verify during an equivalent load window.

## 11. Preventing Recurrence

### Design Retention Around Data Needs

- Choose `cleanup.policy` by purpose: event history needs retention of history; compacted topics fit latest-state-by-key.
- Set retention long enough for replay, investigation, and DR requirements.
- Forecast storage capacity by bytes/sec, replication factor, broker count, and disk headroom.
- Alert before log start offsets approach the minimum data retention window needed.

### Strengthen Write Durability

- Choose `acks=all` when durability requires ISR confirmation.
- Set `min.insync.replicas` consistent with replication factor and desired fault tolerance.
- Enable idempotence when compatible with your producer and Kafka version.
- Monitor ISR shrinks, under-replicated partitions, and replica fetch lag.
- Govern changes related to unclean leader election under operational policy.

### Protect Consumer Processing

- Commit only after processing meets defined acknowledgment criteria.
- For external side effects outside Kafka, consider transactions/outbox, idempotency, or deduplication mechanisms.
- Monitor commit errors, retries, DLT volume, and event processing lag.
- Test restarts, rebalances, and record reprocessing.

### Maintain Independent Recovery Capability

- Identify replayable original data sources and their retention periods.
- Establish independent backups/DR if business requirements demand recovery after deletion or corruption.
- Run periodic restore drills covering data validation, offsets, schemas, and access permissions.
- Document RPO/RTO and who has authority to fail over to a recovery cluster.

### Govern Changes and Administrative Actions

- Audit topic creation/deletion, partition changes, retention, cleanup policies, and ACLs.
- Require review for automation capable of deleting or recreating topics.
- Store desired topic configurations under version control and reconcile against live configuration.
- Test runbooks against test topics, including replays, offset resets, and backup restores.

## 12. Incident Action Checklist

### On Detection

- [ ] Confirm exact cluster, topic, group, and environment.
- [ ] Record the last timestamp when data was confirmed complete.
- [ ] Identify affected partitions, time ranges, keys, or event IDs.
- [ ] Halt unnecessary administrative changes and preserve logs/evidence.
- [ ] Capture topic metadata, topic configs, earliest/latest offsets, and group offsets.

### During Investigation

- [ ] Check effective retention and cleanup policy.
- [ ] Check producer send results, acks, retries, transactions, and endpoints.
- [ ] Check broker logs, leader elections, ISR, and storage.
- [ ] Check consumer commits, acknowledgments, filters, schemas, DLT, and group ID.
- [ ] Determine whether records remain in the log or require an independent recovery source.

### During Recovery

- [ ] Select a data source whose completeness can be proven.
- [ ] Define the replay window by partition/key/event ID.
- [ ] Use a dedicated recovery topic or group where appropriate.
- [ ] Verify idempotency, duplicate handling, ordering, and downstream load.
- [ ] Preview every consumer offset change before executing.
- [ ] Record approvers, commands, and execution outputs.

### Before Closing the Incident

- [ ] Reconcile Kafka data with the business source of truth.
- [ ] Confirm consumers and downstream systems processed records accurately.
- [ ] Confirm producers continue writing to the right destination.
- [ ] Document unrecoverable data and associated decisions.
- [ ] Create remediation follow-ups with owners, due dates, and completion criteria.

## 13. Incident Report Template

~~~text
Incident ID:
Cluster / Environment:
Topic:
Consumer group:
First observed (UTC):
Last known good (UTC):
Affected partitions:
Affected time window:
Affected event IDs / keys:

Observed symptoms:
Evidence collected:
Root cause:
Data still available in Kafka:
Recovery source:
Recovery method:
Replay window and volume:
Duplicate / ordering controls:
Validation result:
Unrecoverable data:
Business owner decision:

Follow-up actions:
Owner:
Due date:
~~~

This runbook standardizes investigation and recovery. Every incident still requires basing decisions on your Kafka version, actual configuration, broker evidence, and business requirements. While it remains uncertain where records still exist, continue preserving state and locating an independent data source before altering offsets or topics.
