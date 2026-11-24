# Messaging Incident Runbook

A Kafka incident can surface in many places: producers fail to send records, brokers reject requests, consumer groups lose partition assignments, listeners slow down, offsets stop advancing, retries spike, or dead-letter topics accumulate backlogs. Jumping straight to config edits after reading a single error log can cause data loss, duplicates, or wider blast radius.

A runbook gives operations a structured response sequence: confirm impact, isolate the failing component, collect evidence, apply reversible mitigation, restore the stream, and verify outcomes. With Spring Kafka, you must inspect Kafka clients, listener containers, error handlers, serializers/deserializers, transactions, and business dependencies together.

This lesson belongs to the **Operations** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on building and using runbooks for messaging incidents in Spring Kafka applications.

## Learning Outcomes

After this lesson, you can:

- Classify incidents across producer, broker, topic/partition, consumer, listener, and dependencies.
- Assess severity and incident blast radius.
- Collect logs, metrics, topic metadata, consumer groups, and offsets before modifying the system.
- Diagnose producer send failures, consumer lag, rebalances, serialization errors, and DLT backlogs.
- Select safe, reversible mitigations.
- Avoid resetting offsets, deleting topics, or bulk-replaying without impact analysis.
- Recover consumer groups and verify data stream stability.
- Handle dead-letter records and perform controlled replays.
- Know when to escalate to Kafka platform, network, security, or business owners.
- Document timelines, decisions, and post-incident lessons.

## 1. The runbook and its scope

A runbook is a concrete operational guide for a specific operational scenario. A good runbook tells the on-call engineer:

1. Which signals trigger the procedure.
2. Which data to check first.
3. Which commands or dashboards isolate the issue.
4. Which conditions confirm a hypothesis.
5. Which actions are authorized.
6. When to stop or escalate.
7. How to verify recovery.
8. Who owns the step and what must be logged.

A runbook does not replace system understanding or approval authority. For actions that risk data loss, alter semantics, or impact multiple consumers, follow your organization's change/incident policies.

This lesson targets a typical Spring Kafka pipeline:

~~~text
Producer service
      |
      v
Kafka broker / topic / partition
      |
      v
Consumer group / listener container
      |
      v
Business service / database / downstream
      |
      +---- retry / recovery / DLT
~~~

An incident can originate in one component or cascade across several. For example, a slow database stalls listeners, driving consumer lag up, disrupting the poll loop, and triggering retries.

## 2. Starting an incident: confirm impact before fixing

When an alert fires or a user reports an issue, determine first:

- Which services are affected.
- Which topics and consumer groups are involved.
- When the issue started.
- How many records are delayed, failing, or unprocessed.
- Whether data loss is confirmed or if it is currently just a backlog.
- Business impact: delayed orders, stale inventory, unsent notifications, or missing audit trails.
- Whether the incident affects one partition, one topic, or the entire cluster.
- Whether any deployment, config, secret, ACL, or infrastructure changes occurred around the start time.

Do not declare "lost messages" solely from rising consumer lag. Lag indicates consumers have not processed/committed up to the log end offset yet; records may still reside within retention and can be consumed once recovered.

Start an incident timeline recording timestamps, observations, actions, and outcomes. Use a consistent timezone (usually UTC) to align producer, broker, and consumer logs.

## 3. Severity classification

Use the following severity matrix and adapt it to organizational policy:

| Level | Reference scenario | Action |
|---|---|---|
| SEV-1 | Widespread inability to send/receive, widespread offline partitions, suspected data loss, or severe business impact | Trigger incident process, assign incident lead, escalate immediately. |
| SEV-2 | A critical business stream stopped processing, rapid lag growth, sharp DLT/retry spike | Coordinate service owners and Kafka platform, mitigate impact promptly. |
| SEV-3 | Specific partitions or tenants impacted, degraded throughput with available workaround | Monitor, follow runbook, and update owners. |
| SEV-4 | Minor alert, isolated error, or issue with no current business impact | Log ticket, investigate on schedule, and track trends. |

Base severity on business impact, blast radius, expected recovery time, and data risk—not raw error-log volume alone.

## 4. General triage workflow

~~~mermaid
flowchart TD
    A[Alert or incident report] --> B[Confirm service, topic, group and business impact]
    B --> C[Capture logs, metrics and timestamps]
    C --> D{Where is the failure?}
    D -->|Producer| E[Check send errors, broker reachability and ACL]
    D -->|Broker/topic| F[Check partitions, leaders, ISR and broker health]
    D -->|Consumer| G[Check group state, assignment, lag and listener]
    D -->|Payload| H[Check serializer, schema and headers]
    D -->|Recovery| I[Check retry, DLT and recoverer]
    E --> J[Choose reversible mitigation]
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[Verify processing and business outcome]
    K --> L[Monitor stability and close incident]
~~~

Priority order:

1. Gather evidence before restarting or changing configs.
2. Determine whether the error is recurring or transient.
3. Scope the issue by topic, partition, group, and event ID.
4. Pick the smallest mitigation that reduces impact.
5. After each change, re-measure metrics and verify business outcomes.
6. If lacking evidence or authorization, escalate rather than guessing randomly.

## 5. Minimum information to collect

Before diagnosing, record:

| Group | Details |
|---|---|
| Application | Service name, version, instance/pod, deployment time. |
| Kafka | Cluster, bootstrap endpoint, broker version if known. |
| Stream | Topic, partition, consumer group, transactional ID if any. |
| Record | Event ID/correlation ID, masked key, timestamp, source offset if known. |
| Timing | Start time, latest failure time, timezone. |
| Producer | Send rate, ack latency, error/timeout rate. |
| Consumer | Assignments, per-partition lag, processing latency, retry count. |
| Recovery | DLT backlog, exception class, pending record count. |
| Infrastructure | CPU, memory, GC, disk, network, database/downstream health. |
| Recent changes | Releases, configs, ACLs, secret rotations, broker maintenance. |

Protect sensitive data. Never attach passwords, full JAAS configs, bearer tokens, payloads with personal data, or private keys to incident tickets.

## 6. Dashboards and metrics to check first

A baseline messaging dashboard should include:

- Producer acknowledged rate, failed rate, and send latency p95/p99.
- Producer request latency, retries, and buffer pool wait time.
- Consumer records consumed rate and listener processing p95/p99.
- Consumer lag by topic/partition/group.
- Consumer group member count and partition assignments.
- Rebalance rate or partition revoke/assign counts.
- Listener error, retry, and recovery rates.
- DLT incoming rate, backlog, and consumer lag.
- Broker offline partitions, under-replicated partitions, and ISR shrink events.
- Application/broker CPU, heap, GC, network, and disk.
- Database connection pools, query latency, and downstream HTTP errors/latency.

Align metrics on the same time window. If lag started climbing right when database latency spiked, the dependency is likely the root cause; restarting consumers may just add disruption without fixing the bottleneck.

## 7. Runbook A: Producer unable to send records

**Symptoms**

- `KafkaTemplate.send()` futures complete exceptionally.
- Producer timeouts or retries spike.
- Logs show `TimeoutException`, `NotLeaderOrFollowerException`, `RecordTooLargeException`, `TopicAuthorizationException`, or serialization errors.

**Checks**

1. Confirm bootstrap servers and DNS/networking from the exact application instance.
2. Check that brokers are up and listeners serve the right port/protocol.
3. Verify the topic exists and partitions have leaders.
4. Check SASL/TLS authentication and `WRITE`/`DESCRIBE` ACLs.
5. Check serializers, payload size, and broker/topic message size limits.
6. Check producer acks, retries, delivery timeout, and buffer wait.
7. Cross-check broker logs and producer exceptions at matching timestamps.

Topic inspection command:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

**Mitigation**

- If broker/network outage: hand off to the Kafka/network owner and keep producer retries within configured bounds.
- If ACL mismatch: grant the right permissions to the principal via security workflow.
- If topic missing: verify cluster and provisioning before creating.
- If payload too large: check contracts and limits before raising message sizes; consider storing large payloads externally and sending references.
- If serialization error: roll back the release or restore compatible serializer/contract.

Do not raise retries or delivery timeouts unboundedly to mask broker errors. Prolonged retries tie up buffers and inflate service-wide latency.

**Verification**

- Send futures complete successfully.
- Brokers record messages on expected topics/partitions.
- Producer error rates return to baseline.
- Consumers process records by event ID.
- No business duplicates arise from producer retries.

## 8. Runbook B: Growing consumer lag

**Symptoms**

- Lag on one or more partitions climbs steadily.
- Consumer throughput lags behind producer throughput.
- Business events arrive downstream late.
- Listener processing latency or dependency latency rises.

**Checks**

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --describe --group orders-fulfillment
~~~

Check:

1. Does the group have active members?
2. Which consumer is assigned each partition?
3. Is lag rising across all partitions or only one?
4. Is the listener hitting exceptions, retries, or blocking?
5. Are database/HTTP dependencies slow or out of connection pool capacity?
6. Does consumer concurrency align with partition count?
7. Are continuous rebalances or poll timeouts occurring?
8. Are consumers committing offsets after processing?

**Interpretation**

- Lag rising evenly across all partitions: consumer capacity or downstream may be insufficient.
- One partition lagging far more: check hot keys, slow records, or partition-specific issues.
- Consumer members have no assignments: check subscriptions, group protocol, concurrency, and rebalances.
- Lag rising alongside retries/DLT: investigate failing records or dependencies.
- Lag rising while listener timers look low: check pre-listener waits, fetches, commits, rebalances, and metric coverage.

**Mitigation**

- Restore slow dependencies before raising consumer concurrency.
- Add replicas/instances or concurrency only if unassigned partitions and downstream capacity remain.
- Throttle producers temporarily if upstream supports backpressure.
- Pause the stream safely if downstream is down and retention has headroom.
- For hot keys, address key distribution root causes; avoid arbitrary partitioning changes mid-incident.

**Verification**

- Lag trends downward sustainably.
- Consumer throughput meets or exceeds publish rate during catch-up.
- No abnormal rebalances remain.
- Business state updates cleanly with no duplicate side effects.

## 9. Runbook C: Continuous consumer group rebalancing

**Symptoms**

- Partitions are repeatedly revoked and reassigned.
- Consumer logs contain `CommitFailedException`, `RebalanceInProgressException`, `FencedInstanceIdException`, or heartbeat/session timeout messages.
- Lag grows while throughput drops.

**Checks**

- Are instances/pods restarting, crashing, or hitting OOM?
- Are listeners processing longer than `max.poll.interval.ms`?
- Are consumers making blocking dependency calls on the poll thread?
- Are `session.timeout.ms`, `heartbeat.interval.ms`, and `max.poll.interval.ms` compatible?
- Are multiple consumer instances sharing the same static membership identity?
- Are deployments/scaling events or network flaps occurring?
- Did partition assignments shift due to topic/subscription updates?

**Mitigation**

- Fix crashes, OOMs, network instability, or dependency blocks.
- If processing time is genuinely long, revisit batch size, concurrency, and processing design; adjust max poll interval only after assessing impact.
- Remove duplicate static member IDs or configure per-instance identities properly.
- Use low-disruption rollout strategies if rebalances stem from deployments.

Never raise session timeout/max poll interval blindly. Oversized timeouts delay detecting dead consumers or mask hung listeners.

**Verification**

- Group membership stabilizes.
- Rebalance count returns to baseline.
- Assignments stop thrashing.
- Lag and processing latency recover.

## 10. Runbook D: Serialization or deserialization failures

**Symptoms**

- Producers report serialization exceptions.
- Consumers fail to deserialize objects from records.
- Listeners are never invoked despite records sitting in the topic.
- Error handlers or DLTs receive failed records.
- Logs show JSON parse errors, class resolution errors, schema mismatches, or type mapping errors.

**Checks**

1. Identify whether failure happens in the producer serializer or consumer deserializer.
2. Capture topic, partition, offset, and event ID.
3. Check serializer/deserializer settings on the actual factories.
4. Inspect payload bytes, content type, type headers, and schema/version.
5. Check class/package mappings, trusted packages, and default target types.
6. Identify producer/consumer versions deployed near the failure start.
7. If using a DLT, preserve raw key/value bytes and headers for investigation.

**Mitigation**

- If a new release emits incompatible payloads: roll back the producer or republish a compatible contract.
- If consumers lack a mapping/type: deploy consumer support for the new token/type before producers emit it.
- If payloads are corrupted: quarantine records rather than guessing byte edits.
- If schema mismatch: verify backward/forward compatibility and rollout sequence.
- Route via DLT/recovery per policy instead of silently skipping poison pills.

Never manually deserialize an untrusted payload using arbitrary classes. Type headers are producer-supplied metadata, not proof safe enough to load arbitrary classes.

**Verification**

- Consumers deserialize test records cleanly.
- Error rates and DLT ingest rates return to baseline.
- Raw failed records remain preserved for audit.
- Old and new consumers remain payload-compatible during rollout.

## 11. Runbook E: Rising retries or listener processing failures

**Symptoms**

- Listener exceptions spike.
- Retry/backoff durations stretch out.
- Processing throughput drops.
- Consumer lag rises.
- Same event ID appears across multiple attempts.

**Checks**

- Exception classes and root causes.
- Whether records hit permanent data errors or transient dependency failures.
- Whether retryable/non-retryable classifications are accurate.
- Whether retry topics or blocking retries are active.
- Whether database transactions roll back cleanly.
- Whether listener side effects are idempotent.
- Whether the error handler recovers too early or retries infinitely.

**Mitigation**

- Transient dependency issues: restore the dependency and keep bounded retries.
- Permanent payload/validation errors: route to DLT and handle via workflow.
- Post-release code bugs: roll back or deploy a compatible fix.
- Retry storms: throttle or safely stop the stream per runbook to protect downstream.
- Ensure side effects are idempotent prior to redelivery/replay.

Never raise retry counts for unrecoverable failures like incompatible schemas or permanent validation errors. That only swells backlogs and delays recovery.

**Verification**

- Retry rate returns to baseline.
- Listener success rate recovers.
- DLT backlog does not grow unexpectedly.
- Event IDs produce no duplicate side effects.

## 12. Runbook F: Growing dead-letter topic backlog

**Symptoms**

- DLT incoming rate climbs.
- DLT consumer lag or backlog grows.
- Exception classes cluster around one error type.
- Old records remain unclassified or unowned.

**Checks**

1. Identify source topic, partition, and original offset from DLT headers.
2. Classify exceptions and pinpoint start times.
3. Verify whether raw payloads can be deserialized.
4. Find root cause: code, schema, dependency, config, or business rule.
5. Check whether events already applied partial side effects.
6. Check DLT retention, storage, and consumer groups.
7. Assign an owner and status per case.

**Mitigation**

- Fix root cause before replaying.
- Store raw payloads and headers in a controlled quarantine store.
- Test-replay a single record or small batch.
- Preserve event ID, correlation ID, and required keys.
- Attach replay ID and audit trail.
- Enforce idempotency to prevent duplicate side effects.
- Rate-limit and cap replay batch sizes.

Never replay the entire DLT before fixing the root cause. Never delete a DLT to shrink a backlog; doing so destroys evidence and recoverable data.

**Verification**

- Test records process cleanly.
- DLT incoming rate drops.
- Backlog drains per plan.
- Source metadata and replay audit records are saved.
- Business state is reconciled before/after replay.

## 13. Runbook G: Offline or under-replicated partitions

**Symptoms**

- Producer timeouts or leader unavailable errors.
- Topic describe shows leader as -1 / none.
- ISR is smaller than replication factor.
- Brokers alert on disk, network, or log directory errors.

**Checks**

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

Inspect:

- Which brokers are offline or recently restarted.
- Leader/replicas/ISR for each partition.
- Disk usage, I/O errors, and log directories.
- Broker-to-broker networking.
- Controller/quorum health.
- Ongoing reassignments or recoveries.
- Producer acks and min.insync.replicas.

**Mitigation**

- Escalate to Kafka platform owners when cluster health is degraded.
- Recover brokers/disks/networking per platform procedures.
- Monitor followers catching up and ISR recovery.
- Never force leader elections or lower min ISR to mask the condition.
- Never enable unclean leader election without explicit data-loss assessment and approval.

**Verification**

- Partitions hold valid leaders.
- ISR recovers to expected replication factor.
- Offline/under-replicated metrics return to baseline.
- Producer/consumer requests succeed and lag stabilizes.

## 14. Runbook H: Authentication, authorization, or TLS failures

**Symptoms**

- Clients fail to connect to brokers.
- Logs report `SaslAuthenticationException`, `SSLHandshakeException`, `TopicAuthorizationException`, or `GroupAuthorizationException`.

**Checks**

- Bootstrap endpoints and listener protocols.
- SASL mechanism, username, password/token, and JAAS config.
- Whether secrets recently rotated or expired.
- Broker certificates, truststores, and hostname verification.
- Actual client principal.
- ACLs on topics, consumer groups, transactional IDs, or cluster operations.

**Mitigation**

- Restore valid secrets via the secret manager.
- Replace expired certificates per platform procedure.
- Grant least-privilege ACLs to the principal.
- Restart/recreate clients if the mechanism requires credential reload.
- Never disable TLS hostname verification or downgrade to PLAINTEXT as a production workaround.

**Verification**

- Producers/consumers/AdminClient authenticate under the intended principal.
- Authorized topic/group operations succeed.
- Negative tests confirm unauthorized principals are still rejected.
- No secrets appear in logs or incident tickets.

## 15. Runbook I: Transaction aborts, fencing, or commit failures

**Symptoms**

- Transaction commit/abort rates spike.
- Logs show `ProducerFencedException`, transaction timeouts, or coordinator errors.
- Consumers see redeliveries after rollbacks.
- Outputs never appear to `read_committed` consumers.

**Checks**

- Whether transactional IDs/prefixes are unique per application instance.
- Whether old and new pods overlap using the same transactional ID.
- Whether transaction durations exceed timeout.
- Whether listeners run slow work inside transactions.
- Whether `KafkaTransactionManager` and `KafkaTemplate` share the same transaction.
- Whether downstream consumers set `isolation.level=read_committed` as required.

**Mitigation**

- Clear stale instances or transactional ID collisions per deployment lifecycle.
- Fix long-running transactions rather than only raising timeouts.
- Roll back releases with broken transaction manager configs.
- Enable after-rollback/retry handling per policy.
- Reconcile external side effects separately since Kafka transactions do not roll back databases or HTTP calls.

**Verification**

- Transaction commit/abort rates return to normal.
- Producer fencing stops recurring.
- Outputs and input offsets align consistently within Kafka transactions.
- Non-Kafka side effects are reconciled and idempotent.

## 16. Runbook J: Consumers not committing offsets

**Symptoms**

- Listeners run yet committed offsets never advance.
- Records redeliver after restarts.
- Lag fails to drop even though listener logs show success.

**Checks**

- Active AckMode: RECORD, BATCH, MANUAL, or MANUAL_IMMEDIATE.
- Whether listeners invoke acknowledgment in manual modes.
- Whether error handlers seek/redeliver or recover.
- Whether transactions commit or roll back.
- Whether auto-commit was unexpectedly disabled or misconfigured.
- Whether the consumer group rebalances or loses partition ownership.
- Whether offset commits are denied by ACLs.

**Mitigation**

- Fix acknowledgment flows or container configuration.
- Restore commit/group permissions if ACLs were wrong.
- Fix transaction manager/producer fencing if transactions abort.
- Ensure listener side effects are idempotent before letting records redeliver.

Never reset offsets to zero out lag without knowing which records remain unprocessed. Resetting can skip data or trigger mass duplicates.

**Verification**

- Committed offsets advance cleanly per partition.
- Unexpected listener redeliveries stop.
- Business side effects match processed event IDs.
- Consumer lag returns to baseline.

## 17. Operations requiring special controls

The following actions can significantly alter data or semantics:

| Action | Risk | Preconditions before execution |
|---|---|---|
| Reset consumer group offsets | Skips or replays records | Target offsets, partition scope, backup/approval, and replay plan. |
| Delete topic | Data loss and offset/history reset | Approval, retention/archive check, and migration plan. |
| Replay entire DLT | Duplicate side effects, out-of-order execution | Root cause fixed, idempotency, batch limits, audit, and owner. |
| Increase partitions | Alters key-to-partition mapping and ordering | Key/ordering contract and consumer capacity review. |
| Lower min ISR | Reduces durability | Broker-loss assessment and risk sign-off. |
| Enable unclean leader election | Can lose unreplicated records | Platform decision with full trade-off awareness. |
| Increase retries/backoff | Extends backlog and dependency load | Retryable classification and capacity check. |
| Disable TLS/ACLs | Widens security exposure | Never use as a production workaround. |

Runbooks must state who can execute, who approves, and how to roll back. If lacking permissions or evidence, stop at evidence gathering and escalate.

## 18. Verifying recovery after mitigation

Do not close an incident simply because error logs stop appearing. Verify across layers:

1. **Broker health**: brokers online, partitions have leaders, ISR stable.
2. **Producer**: send acknowledgements succeed, errors/timeouts decline.
3. **Consumer group**: members stable, partition assignments intact.
4. **Throughput/lag**: consumers keep up with load, backlog drains steadily.
5. **Listener**: processing success climbs, retries/errors fall.
6. **DLT**: ingest rate stabilizes, backlog has an owner and plan.
7. **Business state**: databases/downstream reflect processed events accurately.
8. **Data integrity**: check duplicates, missing events, and ordering by event ID/aggregate.
9. **Security**: principals/ACLs/TLS properly restored.
10. **Monitoring**: dashboards and alerts stay at baseline over an agreed observation window.

If producer rates dropped because upstream stopped, lag hitting zero does not prove consumers recovered capacity. Verify under normal load or a controlled canary replay.

## 19. Escalation and ownership

A messaging incident often involves multiple owners:

| Team | When to escalate |
|---|---|
| Application owner | Listener code, serializers, business validation, release regressions. |
| Kafka platform | Offline brokers, partition leaders, ISR, controller/quorum, reassignments. |
| Network/platform | DNS, routing, firewalls, packet loss, connection resets. |
| Security/IAM | SASL, TLS certificates, secret rotations, ACLs. |
| Database/downstream | Connection pools, query latency, dependency outages. |
| Business owner | Decisions to replay, drop records, compensate, or fix business state. |

When escalating, provide actionable context:

- Incident ID and severity.
- Service/version/instance.
- Cluster, topic, partition, group.
- UTC time window.
- Error class and secret-scrubbed message.
- Metrics/screenshots/dashboard links per policy.
- Actions already taken and their outcomes.
- Business impact and decisions needed.

Never send raw payloads or credentials over unauthorized channels.

## 20. Incident timeline and handoff template

You can use this template in incident tickets:

~~~text
Incident ID:
Severity:
Incident lead:
Service / version:
Kafka cluster:
Topic / partition:
Consumer group:
First observed (UTC):
Business impact:

Timeline:
- HH:MM UTC - Alert fired:
- HH:MM UTC - Scope confirmed:
- HH:MM UTC - Evidence collected:
- HH:MM UTC - Mitigation applied:
- HH:MM UTC - Recovery verified:

Current metrics:
- Producer error rate:
- Consumer throughput:
- Consumer lag by partition:
- Listener p95/p99:
- Retry / DLT backlog:
- Broker offline / under-replicated partitions:

Root cause (known / suspected):
Actions taken:
Data integrity checks:
Outstanding risks:
Escalation owner:
Next update:
~~~

During an incident, update the timeline in real time. Clearly separate verified facts from hypotheses. During shift handoffs, state current status, active mitigations, items to watch, and the next owner.

## 21. Post-incident review

After recovery, conduct a review to prevent recurrence:

- Write an accurate timeline and impact scope.
- Identify root cause and contributing factors.
- Evaluate detection: did alerts fire early enough, and did dashboards show enough detail?
- Review which mitigations helped and which actions increased risk.
- Audit data integrity: missing events, duplicates, ordering, and DLT records.
- Update runbooks, dashboards, alert thresholds, and ownership.
- Create action items with owners and due dates.
- Add integration/load/failure tests covering what happened.
- Review secret rotation, deployment, or topic provisioning processes if relevant.

Keep reviews focused on systems and processes rather than blaming individuals. The goal is earlier detection and safer recovery next time.

## 22. Capstone exercise: Order Messaging incident drill

Suppose Order Service publishes to `orders.created`; Fulfillment consumer processes events and writes to a database. During the drill, consumer lag climbs, listeners retry, and the DLT begins receiving records.

Requirements:

1. Open an incident ticket with severity, owner, and UTC timeline.
2. Record service version, topic, partition, and group ID.
3. Collect producer send errors/latency, consumer throughput/lag, and listener processing latency.
4. Use Kafka CLI to inspect topic partitions, leaders, replicas, and ISR.
5. Use consumer group describe to locate high-lag partitions.
6. Check listener exceptions, database latency, and connection pools.
7. Classify failing records as transient, permanent, or data/schema issues.
8. Identify which records were retried and which went to the DLT.
9. Propose the smallest reversible mitigation.
10. Replay only a single canary record after fixing the root cause.
11. Verify event ID, idempotency, and business state.
12. Monitor lag, retries, DLT, and throughput over a stabilization window.
13. Write a handoff note for the next on-call shift.
14. Run a post-incident review and create action items.

The exercise is complete when operations can scope impact, isolate root cause, reduce blast radius, restore the stream, and prove business data suffered neither loss nor unexpected duplicates.

## 23. Learning sequence and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Incident basics | Severity, impact, timeline | Describe impact and blast radius accurately. |
| 2. Evidence | Logs, metrics, topic/group metadata | Gather sufficient evidence before making changes. |
| 3. Producer | Send failure, timeout, ACL, serializer | Isolate publish failures. |
| 4. Consumer | Lag, assignment, rebalance, offset | Identify affected partitions and groups. |
| 5. Payload | Serialization, schema, type headers | Handle poison pills and compatibility issues. |
| 6. Recovery | Retry, DLT, replay | Run controlled, idempotent replays. |
| 7. Broker | Leader, ISR, offline partition | Coordinate with platform to restore cluster health. |
| 8. Security/transaction | SASL, TLS, ACL, fencing | Distinguish auth, authorization, and transaction errors. |
| 9. Mitigation | Safe actions and escalation | Choose small, reversible actions. |
| 10. Verification | Throughput, lag, business integrity | Prove both stream and data recovered. |
| 11. Review | Timeline, root cause, action items | Update runbooks and prevent recurrence. |

This lesson is complete when you can follow a runbook from initial alert through recovery verification: gathering evidence, separating producer/broker/consumer faults, managing retries and DLTs, selecting safe mitigations, escalating to the right owners, and verifying data integrity.

A solid runbook helps operations act consistently under pressure. Confirm impact, gather data before making changes, recover in small steps, and close an incident only after verifying both the Kafka pipeline and business outcomes.

