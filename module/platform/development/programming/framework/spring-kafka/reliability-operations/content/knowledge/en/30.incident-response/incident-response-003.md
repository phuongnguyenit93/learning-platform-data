# Runbook for DLT Spikes

## Objective and Scope

This runbook guides incident response when the number of records routed to a Dead Letter Topic (DLT) increases rapidly in a Spring Kafka application. The incident objectives are:

1. Confirm the impact scope and isolate the failing listener, consumer group, topic, partition, or message type.
2. Prevent errors from amplifying through uncontrolled retries, rebalances, or replays.
3. Preserve messages along with the metadata required for investigation and reprocessing.
4. Restore normal processing flow, then perform a controlled replay of messages that entered the DLT.
5. Reconcile to prove that no messages were lost, processed twice, or skipped.

A DLT stores records that the error handling mechanism decided not to retry further or could not continue processing under the current policy. A DLT spike is usually a symptom of an error in the consumer, data, dependency, or retry configuration. The DLT itself may still be working properly while accepting failed messages.

This runbook applies to both common implementations in Spring Kafka:

- **Blocking retry**: the container invokes `DefaultErrorHandler`, retries the record according to `BackOff`, and then sends records that exhaust retries through `DeadLetterPublishingRecoverer`.
- **Non-blocking retry**: `@RetryableTopic` routes records across scheduled retry topics; once attempts are exhausted, the record is sent to the DLT. This pattern usually has a `@DltHandler` or a dedicated listener to process the DLT.

Actual topic names and behavior depend on application configuration. For example, `DeadLetterPublishingRecoverer` often uses names formatted as `<topic>.DLT`, while retry-topic infrastructure typically uses the `-dlt` suffix; applications may also define custom names. Always verify topic names from the running configuration before taking action.

## When to Trigger This Runbook

Trigger when one or more of the following signals appear:

- The rate of new writes to the DLT exceeds the normal baseline across several consecutive measurement windows.
- A DLT alert by topic, consumer group, or service transitions to critical.
- The error handling rate or recoverer invocation count surges after a deployment.
- Retry topic backlog grows rapidly and many messages eventually land in the DLT.
- The DLT consumer falls behind, causing DLT backlog to keep growing even after the new write rate drops.

Distinguish between two metrics: **DLT ingress rate** is the rate of new messages written to the DLT; **DLT consumer lag** is the number of messages waiting for the DLT consumer to process. A rising ingress rate indicates many records are failing in the business flow. Rising lag may indicate that the DLT consumer or a system downstream of the DLT is slow. Both issues can occur together but require separate handling.

An example alerting threshold might be a DLT ingress rate higher than three times the baseline for five minutes, or exceeding an absolute threshold set by the operations team. This is only a starting point; use each system's baseline, traffic profile, and SLO to configure real thresholds.

## Severity Levels and Roles

Assess severity based on business impact, growth rate, topic scope, and recoverability:

| Severity | Reference indicators | Response direction |
|---|---|---|
| SEV-1 | Multiple critical flows failing together; core data or transactions stalled; unable to process safely | Activate high-severity incident process, appoint an Incident Commander, notify dependent teams, and prioritize service restoration |
| SEV-2 | One critical business flow has continuously rising DLT volume; backlog or latency breaches SLO | Coordinate application, Kafka, and relevant dependency owners; provide status updates on short intervals |
| SEV-3 | Narrow scope, workaround available; messages are safely stored and SLO is not yet significantly impacted | Service owner team follows the runbook and closely monitors ingress rate and backlog |

The Incident Commander coordinates decisions and status updates. The Application Owner analyzes exceptions, releases, and listener logic. The Kafka/Platform Owner checks brokers, topics, ACLs, producers, and consumer groups. Data or downstream Owners assist with checking schemas, data, and dependencies. One person records timestamps, changes applied, and the outcome of each step.

## Information to Capture

Before changing configuration or replaying, create an incident record containing at minimum:

| Category | Fields to record |
|---|---|
| Timing | Start time, alert time, detection time, timezone |
| Scope | Environment, service, listener/container, consumer group, source topic, related DLT and retry topics |
| Kafka | Partition, offset, consumer lag, DLT write rate, DLT read rate, broker and producer status |
| Application | Running version, latest deploy time, retry/backoff config, consumer instance count and concurrency |
| Errors | Exception class, error message scrubbed of sensitive data, sample stack trace, counts by error group |
| Message | Key, timestamp, schema/version if applicable, correlation/trace ID, and present DLT headers |
| Impact | Affected business flow, estimated record count, SLO, and active workaround |

Store full payloads only in authorized, access-controlled locations. Logs, tickets, or incident channels must not contain tokens, personal identifiers, payment data, or sensitive payloads. Use keys, offsets, and trace IDs to correlate records whenever possible.

## Initial Response Procedure: 0–5 Minutes

### 1. Confirm the Alert

1. Check dashboards and logs to verify new messages are actually being written to the DLT.
2. Compare the ingress rate against the baseline for the same time window; inspect metrics per topic and partition.
3. Verify whether the alert reflects an old DLT backlog or genuinely new failures.
4. Record when the spike began and correlate it with the latest deployment, config change, schema change, or dependency incident.

Do not diagnose an incident solely from the current total message count in the DLT. A DLT with long retention can hold an old backlog even when the system is operating normally.

### 2. Narrow Down the Scope

Check in order:

- Are one or multiple source topics pushing messages into the DLT?
- Are one or multiple consumer groups affected?
- Do errors occur across all partitions or concentrate on a few partitions/keys?
- Are multiple services failing together or only one service?
- Did retry topics grow before the DLT spiked?
- Is the DLT consumer able to read messages?

If multiple services and topics fail simultaneously, prioritize checking shared dependencies, brokers, network, credentials, or platform changes. If only one topic or group of keys fails, prioritize checking payloads, schemas, and that service's processing logic.

### 3. Preserve Evidence

Sample multiple representative messages for each exception group, rather than only the first message. Record the topic, partition, offset, key, timestamp, trace ID, schema/version, and original headers. Count occurrences by exception class, source topic, and partition to determine whether failures share a single root cause or stem from multiple causes.

Do not purge the DLT, reset offsets, run bulk replays, or set infinite retries during the confirmation phase. Those actions can destroy evidence, create error loops, or overload an already struggling dependency.

### 4. Verify the DLT Write Path

Confirm that the recoverer's producer can write to the DLT:

- The target topic exists and has enough partitions for the routing strategy in use.
- The producer has write permissions; ACLs, credentials, and TLS are valid.
- Brokers are healthy, with no abnormal network, quota, ISR, or metadata errors.
- Logs from `DeadLetterPublishingRecoverer` and the producer report no send failures or timeouts.
- The recoverer's send-result handling configuration matches the application's reliability requirements.

If sending to the DLT fails, resolve the write path failure first. Never assume a message is preserved merely because the error handler invoked the recoverer; confirm that the publish operation succeeded according to the acknowledgment mechanism configured by the application.

## Root Cause Diagnosis

Use the table below to choose an investigation path. A single exception is not enough to confirm root cause; correlate with timing, scope, and logs on both the consumer and dependency sides.

| Symptom | Possible cause | What to check | Priority action |
|---|---|---|---|
| Multiple topics spike together after deploy | Regression, contract change, or shared configuration change | Release diff, image/config versions, startup logs, serializer/deserializer changes | Evaluate rollback or hotfix per release process |
| `DeserializationException` or schema error concentrated on one message type | Malformed payload, incompatible schema, or serializer/deserializer version mismatch | Schema ID/version, subject compatibility, `ErrorHandlingDeserializer`, data sent by producer | Fix the contract or handle bad data; validate with a sample before replaying |
| `ClassCastException`, conversion, or mapping exception | Consumer expects a different data type than the actual message | DTOs, type headers, message converters, schemas, and model changes | Fix mapping or release a compatible consumer |
| Timeouts, connection resets, or DB/API access errors | Slow dependency, lost connectivity, exhausted pool, or overloaded downstream | Dependency latency/error rate, connection pools, timeouts, circuit breakers, and network | Restore the dependency; throttle or selectively pause consumption if needed |
| `AuthorizationException` or authentication error | ACLs, credentials, secret rotation, or wrong principal | Consumer/producer principal, read permission on source and write permission on DLT, secret rotation timestamp | Restore properly scoped permissions or credentials |
| Errors concentrated on a single partition or key | Poison data, ordering dependency, partition skew, or specific business state | Keys, adjacent offsets, partition assignment, payload, and data state | Isolate the failing message group and address the cause by key/partition |
| Retry topic grows first, then DLT spikes | Dependency or business condition does not recover within the retry window | Retry attempts, delays, attempt counts, message age, and dependency health | Fix the root cause; do not merely extend retries to hide errors |
| DLT ingress is steady but DLT lag increases | Slow DLT consumer, DLT processing errors, or overloaded downstream behind DLT | Consumer group lag, listener errors, concurrency, dependencies, and throughput | Restore the DLT consumer or the next receiving system |
| Logs report recoverer send failure or DLT does not grow as expected | DLT producer, topic, ACL, or broker failure | Producer callback/result, topic metadata, partition count, ACLs, and broker logs | Restore the DLT write path; check records not yet confirmed as processed |

### Distinguishing Business Errors from Infrastructure Errors

- **Business/data errors** usually repeat for the same payload type, key, or schema; other messages continue processing normally.
- **Dependency errors** usually correlate with DB/API latency, timeouts, or error rates; multiple message types may fail together.
- **Kafka/platform errors** usually affect multiple consumers or producers and show up in brokers, network, ACLs, quotas, metadata, or rebalances.
- **Retry configuration errors** usually manifest as unexpected attempt counts, wait intervals, exception classifications, or DLT routing.

Inspect both the first exception and the final exception. A message may pass through multiple retries and only be recorded with the final exception; logs from the first attempt may hold clues about the initial cause.

## Spring Kafka Checkpoints

### Blocking Retry with `DefaultErrorHandler`

Inspect the `DefaultErrorHandler` bean and related configurations:

- Whether `BackOff` is fixed, exponential, or custom; how many retries and what interval between attempts.
- Which exceptions are retried and which are classified as non-retryable.
- Whether the actual recoverer is `DeadLetterPublishingRecoverer` or another implementation.
- Whether retries are configured per record or per batch; which ack mode the listener uses.
- How errors are handled when publishing to the DLT fails and how offset commit/recovery acknowledgment is configured.
- Whether exceptions are wrapped or misclassified, causing non-retryable errors to be retried excessively.

With `DefaultErrorHandler`, a record may be retried within the container's processing flow before the recoverer is called. Once retries are exhausted, the recoverer typically publishes the record to the DLT. Commit/ack behavior after recovery depends on the ack mode, error handler configuration, transactions, and Spring Kafka version. Before altering offset or ack behavior, verify the running configuration and assess the risk of duplicate processing.

### Non-Blocking Retry with `@RetryableTopic`

Check:

- Attempt count, backoff, delays, and the actual list of retry topics.
- Topic naming rules, DLT suffix, and partition counts of each retry topic.
- What `@DltHandler` or the DLT listener does: logging, persistence, alerting, or business logic.
- Whether retry topics have adequate partitions, retention, and access permissions.
- Which retry topic messages are waiting in and the age of the oldest message.

Non-blocking retry moves messages across different topics, so processing order among messages with the same key can change. When recovering or replaying, evaluate the ordering impact on business logic before running in parallel.

### DLT Headers and Metadata

Spring Kafka commonly adds headers describing origin and error details, for example:

- `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `DLT_ORIGINAL_PARTITION`, `DLT_ORIGINAL_OFFSET`.
- `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` and `DLT_ORIGINAL_TIMESTAMP_TYPE`.
- `KafkaHeaders.DLT_EXCEPTION_FQCN`, `DLT_EXCEPTION_MESSAGE`, `DLT_EXCEPTION_STACKTRACE`.
- `KafkaHeaders.DLT_ORIGINAL_CONSUMER_GROUP`.

Exact header names and presence depend on version, recoverer, and configuration. Inspect the actual headers on sample messages. When replaying, preserve source metadata needed for auditing and correlation; avoid letting old exception headers trick the replay processing path into thinking the old error is still happening.

## Mitigation Actions by Cause

Make one change at a time, recording the operator, timestamp, reason, and before/after metrics. After each change, observe for at least one window long enough to establish a trend.

### If Errors Started After a Deployment

1. Confirm the versions and configurations of running instances.
2. Diff changes affecting listeners, DTOs, serializers/deserializers, schemas, exception handling, and dependency clients.
3. If there is evidence of a regression and rollback is safe, roll back per release procedures.
4. Monitor DLT ingress rate, new errors, and consumer lag after rollback.
5. Retain messages already in the DLT for processing once a compatible version is restored.

### If a Dependency Is Slow or Unavailable

1. Coordinate with the dependency owner to confirm status and estimated recovery time.
2. Check retry/backoff, timeouts, connection pools, and circuit breakers to avoid generating extra load.
3. If continued consumption increases errors or causes overload, consider pausing the listener or reducing consumption rate at the narrowest possible scope. Record the affected consumer group, listener, and partitions.
4. Check retention on source topics and retry topics to ensure messages have enough time to wait for dependency recovery.
5. Resume incrementally once the dependency is healthy; observe error rate and latency before restoring full concurrency.

Do not mechanically increase concurrency or retry counts. When a dependency is the bottleneck, those changes can raise load and prolong the incident.

### If Messages Are Invalid or Schema-Incompatible

1. Group messages by schema/version, exception, key, and producer.
2. Verify whether the producer emitted messages violating the contract or the consumer recently changed deserialization logic.
3. Choose whether to fix the contract, add backward compatibility, or establish a separate handling flow for invalid data.
4. If a class of data must be skipped, there must be a documented business decision, an exact list of messages, and archival/audit evidence.
5. Replay only messages confirmed to be processable.

Do not delete messages simply because a group of records triggers errors. Discarding data requires business approval and reconciliation evidence per system policy.

### If the DLT Write Path Fails

1. Check target topic, partition count, ACLs, credentials, producer config, and broker health.
2. Verify whether the recoverer receives publish success or failure outcomes.
3. Check transactions and the error handler to see whether the consumer retries, stops, or continues when DLT publishing fails.
4. Restore the DLT write path before allowing the error handling flow to resume normally.
5. Reconcile source offsets/records against the DLT to locate records whose publish was not confirmed.

Do not manually create topics or change partition mappings in production without verifying the recoverer's routing strategy. Incompatible changes can cause DLT publishing to keep failing.

## Recovering and Replaying Messages from the DLT

Replaying carries the risk of duplicate or out-of-order processing. Start only after the root cause is fixed or a verified workaround is in place, Kafka read/write paths are stable, and the business owner approves the replay scope.

### Pre-Replay Conditions

- Source topic, DLT, retry topics, consumer group, and routing strategy are identified.
- Messages are classified by exception, schema/version, key, partition, and offset range.
- The set of messages to replay is selected; messages already handled manually or confirmed unnecessary are excluded.
- The current consumer version can read the payloads and is schema-compatible.
- Receiving dependencies are healthy and have sufficient capacity.
- Business logic has idempotency or an appropriate deduplication mechanism.
- A plan is defined to preserve ordering, partition mapping, source metadata, and audit trails.
- Tested on a small batch or representative test environment.

### Safe Replay Steps

1. **Build a manifest**: record DLT topic, partition, offset, key, timestamp, trace ID, error type, and replay decision for each group.
2. **Choose the destination**: decide whether to replay to the source topic, a dedicated replay topic, or a controlled processing flow. Choose based on application design and business rules.
3. **Check partitions**: if preserving original partitions, ensure the destination topic has matching partitions. Verify keys and partitioners to prevent unexpected partition shifts.
4. **Run a small pilot**: replay a small subset of selected messages; confirm the consumer processes them successfully, target data is accurate, and no duplicate side effects occur.
5. **Ramp up gradually**: split into bounded batches and increase according to observed capacity. Monitor throughput, latency, consumer lag, error rate, and DLT ingress rate after each batch.
6. **Record results**: track counts read, published successfully, processed successfully, failed again, and still pending; link to the manifest and traces.
7. **Stop on bad signals**: halt the next batch if DLT ingress rises again, dependencies cross thresholds, consumer lag grows uncontrollably, or duplicate side effects are detected.

### Controls Required

- **Idempotency**: the same message may be reprocessed if a consumer created a side effect before committing the offset, or if a replay runs multiple times. Use idempotency keys, unique constraints, an inbox/deduplication store, or your system's equivalent mechanism.
- **Ordering**: if business logic requires per-key ordering, replay by partition/key and do not parallelize arbitrarily. Retry topics may have already altered the original order.
- **Offsets**: replay using a separate consumer group or dedicated tool per operational procedures. Never reset offsets of a production consumer group as a substitute for selective replay.
- **Headers**: keep source metadata needed for auditing; add a new replay ID or correlation ID if supported by the system; handle old error headers under a clear policy.
- **Transactions**: republishing and marking a DLT message as handled may be two separate operations. Without transactions or proper compensation, design replay to be safely re-runnable.
- **Retention**: check DLT retention before and during the incident. Never alter retention to purge data without reconciliation and an approved archive.

Do not use advancing offsets, deleting the DLT, or replaying an entire topic as the default recovery approach. Those actions can skip unprocessed messages or cause duplicate business side effects.

## Post-Mitigation Monitoring

After the root cause is addressed, monitor the following metrics together:

| Metric | Post-mitigation expectation |
|---|---|
| DLT ingress rate | Returns to baseline or drops to normal thresholds; no new error groups appear |
| Source consumer lag | Decreases steadily without climbing back after concurrency is restored |
| Retry topic backlog | Drains as planned; does not keep mass-routing to the DLT |
| DLT consumer lag | Processed within confirmed capacity; no new errors in the DLT listener |
| Consumer error rate | Returns to normal levels; original exception does not recur |
| Dependency latency/error rate | Stable below SLO thresholds with enough capacity for recovery load |
| Replay result | Counts read, published, processed, failed, and pending are reconciled |

Continue monitoring through at least several evaluation windows suited to the system's traffic. For low-volume flows, observe long enough for representative traffic to appear; do not close the incident simply because instantaneous metrics read zero.

## Incident Closure Criteria

Close only when all applicable criteria are confirmed:

- Root cause or workaround is documented with an assigned owner.
- DLT ingress rate and consumer error rate have returned to acceptable levels over the agreed observation window.
- Source consumers, retry topics, and DLT consumers show no abnormal backlog growth.
- Related dependencies are stable and have capacity for normal traffic.
- Messages in the DLT are accounted for: replayed successfully, queued for handling with an owner/SLA, or discarded under an audited business decision.
- Counts of messages received, processed, pending, and discarded are reconciled.
- Temporary changes such as paused listeners, reduced concurrency, or config overrides have been reverted or promoted to reviewed permanent changes.
- Dashboards, alerts, and operational documentation are updated if the incident exposed gaps.

## Incident Record Template

Copy the template below into the ticket or incident log:

```text
Incident ID:
Environment:
Service / Listener:
Consumer group:
Source topic(s):
Retry topic(s):
DLT topic(s):
First seen / Alert time (timezone):
DLT ingress rate / baseline:
Source lag / DLT lag:
Affected partitions / offsets:
Top exception groups:
Last deployment or config change:
Dependency status:
Business impact:

Mitigation applied:
Owner and timestamp for each change:
Root cause / current hypothesis:
Replay manifest:
Replay read / published / processed / failed / pending:
Reconciliation result:
Follow-up actions and owners:
Incident closed by / time:
```

## Quick Checklist for On-Call

- [ ] Confirm whether DLT ingress rate is rising or only DLT consumer lag is growing.
- [ ] Identify source topic, consumer group, listener, partitions, and start time.
- [ ] Correlate with deployments, schema changes, credential rotations, and dependency incidents.
- [ ] Safely sample messages; group by exception, key, and schema/version.
- [ ] Check retry topics and the DLT publish path, including topic, partitions, ACLs, and producer results.
- [ ] Choose mitigation based on root cause; record every change.
- [ ] Replay only after building a manifest and verifying idempotency, ordering, capacity, and required approvals.
- [ ] Monitor post-mitigation metrics and fully reconcile messages.
- [ ] Document root cause, decisions, owners, and preventive actions before closing the incident.
