# Canary Rollouts, Metric Monitoring, and Rollback Planning

Upgrading a Spring Cloud Stream application should be deployed in observable and reversible stages. A new version may start up successfully yet still misprocess messages, increase consumer lag, produce duplicates, corrupt state stores, or emit data the old version cannot read. Therefore, a rollout needs a baseline, a trial stage, continue/stop criteria, an accountable owner, and a pre-tested rollback plan.

This lesson focuses on three tasks: running a trial deployment on part of the workload, monitoring technical and business metrics while scaling out, and rolling back to a stable version when bad signals appear. Across Kafka, RabbitMQ, and Pulsar, a canary strategy must account for consumer groups, subscriptions, partitions, queues, offsets, acknowledgments, and stateful processing. Splitting HTTP traffic by percentage is not the same as splitting a message stream.

## 1. Safe rollouts start from a baseline

A baseline is the measured state of the stable running version prior to upgrading. Without a baseline, it is hard to tell whether post-rollout latency, throughput, error rate, or backlog actually degraded or merely fluctuated normally.

Before deploying, record:

- Application, Spring Boot, Spring Cloud Stream, binder, and broker client versions.
- Image digest or artifact checksum, commit SHA, and runtime configuration.
- Instance count, consumer concurrency, partitions/queues/subscriptions, and consumer groups.
- Message/s and byte/s throughput per binding.
- Processing latency p50, p95, p99 and end-to-end business latency.
- Consumer lag or backlog, oldest message age, and backlog growth/drain rate.
- Errors, retries, redeliveries, DLQ counts, and acknowledgment/commit failures.
- CPU, heap, allocations, GC pauses, thread pools, and connection pools.
- Broker health, replication, disk, network, and request latency.
- Business metrics such as order acceptance rate, payment success rate, or rejected events.

The baseline should span a period covering both normal load and recent peak traffic. Record the measurement window, time zone, metric sources, and special events such as batch jobs, traffic campaigns, or broker maintenance.

### 1.1. Sample baseline table

The numbers below illustrate how to record measurements, not standard thresholds for every system.

| Metric | Example baseline | Window | Notes |
|---|---:|---|---|
| Inbound throughput | 2,000 msg/s | 30 minutes | Total across three partitions |
| Processing p95 | 85 ms | 30 minutes | From handler entry to completion |
| Processing p99 | 210 ms | 30 minutes | Excludes upstream wait time |
| Kafka consumer lag | 1,200 records | 5 minutes | Not continuously climbing |
| Oldest message age | 4 seconds | 5 minutes | Measured by normalized event timestamp |
| Handler error rate | 0.08% | 30 minutes | Calculated over invocation count |
| DLQ rate | 0.002% | 1 hour | Categorized by error type |
| Average CPU | 48% | 30 minutes | Relative to container limit |
| Heap after GC | 55% | 30 minutes | Not climbing steadily |
| Business success rate | 99.7% | 1 hour | Per business event definition |

Do not compare two numbers whose definitions differ. For instance, handler duration is not end-to-end latency; Kafka lag in record counts is not equivalent to message age; publish confirm counts do not prove downstream processing completed.

## 2. Choosing a deployment strategy

Common strategies vary in control and complexity.

| Strategy | How it works | When suitable | Risks to manage |
|---|---|---|---|
| Rolling update | Gradually replaces old instances with new ones | Backward-compatible changes, stateless workloads, or tested consumer groups | Two versions running together; rebalances; schema/state changes |
| Canary | Runs the new version on part of traffic or workload | Need to verify real behavior before scaling out | Must determine accurately which traffic/messages reach the canary |
| Blue-green | Stands up a parallel new environment then switches traffic | Need fast cutover and ability to revert to old environment | Both environments may consume messages or write side effects simultaneously |
| Shadow | Sends a copy of events to the new version without main side effects | Verify deserialization, logic, and performance | Extra load; sensitive data; must block real publishing or mutations |

Rolling updates are simple, yet do not automatically create a percentage-based message canary. Blue-green is also not automatically safe if both environments read the same stream and update the same database. Clearly define message and side-effect ownership before picking a rollout strategy.

## 3. Rolling updates with Kubernetes

A Kubernetes Deployment can replace Pods using a rolling strategy:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
        release: v2
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: registry.example.com/order-consumer:2.4.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

This manifest illustrates only the rolling strategy and readiness. The readiness endpoint must be enabled and configured appropriately in the application. For message consumers, readiness does not automatically stop pulling messages from the broker; combine it with graceful shutdown and binder lifecycle management.

Meaning of the two parameters:

- maxSurge: number of Pods allowed to run above the desired replica count during updates.
- maxUnavailable: number of Pods allowed to be unavailable during updates.

A maxUnavailable of 0 keeps the desired Pod count ready per Deployment rules, yet does not guarantee sufficient consumer capacity if the broker distributes partitions or queues unevenly. A large maxSurge can temporarily raise the consumer count, shifting partition assignments or increasing downstream load.

Before rollout, confirm the cluster has enough CPU, memory, broker connections, and database connections for the maximum Pod count during surge. Set the termination grace period based on measured drain time rather than an arbitrary number.

## 4. HTTP canaries and message consumer canaries differ

For HTTP services, an ingress or service mesh can split requests by weight, e.g., 5% of requests to the new version. For broker consumers, messages are distributed according to broker semantics:

- Kafka: consumers in the same group share partitions; each partition is assigned to at most one consumer in the group at a time.
- RabbitMQ: multiple consumers on the same queue receive deliveries according to prefetch, consumer capacity, and channel state.
- Pulsar: consumers in the same subscription receive messages according to subscription type and dispatch policy.

You cannot assume adding one new Pod will receive exactly 5% of messages. Kafka distributes by partition assignment, not per-record percentages. RabbitMQ and Pulsar likewise do not guarantee exact percentages by consumer count.

### 4.1. Canary in the same consumer group

When the new version joins the same consumer group/subscription and reads the same queue:

- Both versions share workload via broker mechanics.
- Kafka may rebalance partitions onto the new consumer.
- RabbitMQ may dispatch deliveries to old or new consumers.
- Pulsar dispatches messages to consumers per subscription type.

This tests the new version on real messages without actively duplicating the entire stream. However, the new version can receive messages for any partition or key; there is no guarantee the canary receives only a small steady fraction. Ensure both versions remain compatible on schemas, outputs, and databases while running concurrently.

### 4.2. Canary using a separate consumer group/subscription

A separate consumer group or subscription normally receives the entire stream independently:

- A new Kafka group reads the topic using its own offsets.
- RabbitMQ requires a separate queue/binding to receive a copy of messages.
- An independent Pulsar subscription receives messages via its own cursor.

This fits shadow processing or logic verification, but may reprocess entire history depending on offsets/cursors and retention. If the new consumer sends emails, deducts funds, updates databases, or publishes real events, side effects can be duplicated.

An independent canary must enforce one of these safeguards:

1. Run read-only or write only to a test database/schema.
2. Disable output bindings or redirect outputs to an isolated destination.
3. Use controlled event mirroring with data filtering and rate limiting.
4. Use idempotency keys and an explicitly designed side-effect gate.
5. Never reset offsets to earliest on a production topic without evaluating load and impact.

### 4.3. Choosing a canary by goal

| Goal | Suitable approach |
|---|---|
| Verify app startup and connectivity | One new instance with consumer intake paused or controlled bindings |
| Verify deserialization/schemas | Replay scrubbed historical events into a test environment |
| Measure handler performance | Shadow consumer with isolated outputs |
| Test real production traffic | Join the same group after verifying compatibility; monitor actual distribution |
| Test stateful Kafka Streams changes | Dedicated state store migration plan with tested snapshot/restore and rollback |

Do not call a new consumer group a 5% canary if it reads the entire topic. Explicitly document how messages are selected, how side effects are isolated, and how the canary is stopped.

## 5. Controlled rollout stages

A rollout can be divided into steps:

1. **Preflight:** verify artifacts, config, secrets, schema compatibility, capacity, and rollback package.
2. **Trial deploy:** run smoke tests, health checks, and broker connectivity on one instance or staging environment.
3. **Canary:** open part of the workload/traffic using the defined mechanism; keep outputs safe.
4. **Observe:** compare metrics against baseline across a full observation window.
5. **Expand:** gradually increase instances or weight once all gates pass.
6. **Complete:** deploy everywhere, confirm consumer groups/queues/subscriptions stabilize, and close the release.

~~~mermaid
flowchart TD
    A["Preflight: artifact, config, schema, rollback"] --> B["Trial deploy / smoke test"]
    B --> C{"Health and contract pass?"}
    C -- No --> R["Stop rollout / rollback"]
    C -- Yes --> D["Canary workload"]
    D --> E["Monitor metrics and business SLIs"]
    E --> F{"All rollout gates pass?"}
    F -- No --> R
    F -- Yes --> G["Expand 25% / 50% / 100%"]
    G --> H["Verify whole system"]
    H --> I["Complete release"]
    R --> J["Investigate and recover"]
~~~

Percentages like 25%, 50%, and 100% are illustrative only. With Kafka, consumer instance ratios do not map linearly to record ratios. With RabbitMQ and Pulsar, dispatch is also affected by queue backlog, prefetch, subscription type, and consumer capacity.

## 6. Defining rollout gates before deploying

A rollout gate is a quantitative criterion for deciding to proceed, pause, or roll back. Gates must be defined before viewing results to avoid moving goalposts to justify a bad rollout.

A gate should specify:

- Exact metric and definition.
- Data source and observed binding/service.
- Comparison baseline or SLO.
- Evaluation window and minimum sample size.
- Warning threshold and rollback threshold.
- Authorized decision-maker.
- Action when metric data is missing.

### 6.1. Rollout gate examples

The thresholds below are illustrative examples only. Real systems must choose thresholds based on SLOs, traffic, and baselines.

| Gate | Proceed when | Stop/rollback when |
|---|---|---|
| Instance health | Pods Ready, no abnormal restarts | CrashLoop, startup failure, or repeated readiness failures |
| Handler error rate | No significant increase vs. baseline | Exceeds absolute threshold or climbs sharply across windows |
| Processing p99 | Within latency budget | Breaches SLO continuously and impacts backlog |
| Consumer lag/oldest age | Stable or shrinking at comparable load | Climbing continuously; message age exceeds SLO |
| Retry/DLQ | No new spikes | Abnormal spike or schema/contract errors appear |
| Business success rate | No drop vs. baseline | Business success rate drops noticeably |
| Resources | CPU/heap/GC maintain headroom | CPU throttling, OOM, or GC pauses exceed budget |
| Broker health | No new connection/replication errors | Broker request errors, queue alarms, or replication degradation |

Do not roll back over a single latency sample. Use a sufficiently large window, yet do not wait long when there are signs of data loss, duplicate side effects, or security issues. Conditions like schema incompatibility, message corruption, or publishing to the wrong destination require stopping immediately.

## 7. Metrics to monitor in Spring Cloud Stream

Monitor by binding, function, destination, consumer group, and release version. Application-wide totals can mask one congested binding while other bindings look healthy.

### 7.1. Application-layer metrics

- Messages received, succeeded, and failed.
- Processing duration p50/p95/p99.
- Active handlers and internal queue depth.
- Retry count, retry exhaustion, and DLQ count.
- Deserialization/schema validation failures.
- Output messages published and publish failures.
- Business success/failure by event type.
- Idempotency duplicate hits.
- Thread pool active/queued/rejected counts.
- Database connection wait time, query latency, and transaction rollbacks.

### 7.2. Binder and broker-layer metrics

| System | Metrics to monitor | Question to answer |
|---|---|---|
| Kafka | Consumer lag, records consumed, rebalances, commit failures, request latency, under-replicated partitions | Are consumers keeping up with partitions and committing offsets? |
| RabbitMQ | Ready/unacked messages, consumer count, publish/ack rate, redeliveries, connections/channels, memory/disk alarms | Is the queue backing up, or are consumers blocked or redelivering heavily? |
| Pulsar | Backlog, subscription/consumer count, dispatch rate, redeliveries, acknowledgments, BookKeeper storage health | Is the subscription keeping up and is storage healthy? |

Broker metrics do not replace business metrics. Low Kafka lag can still accompany misprocessed business events; an empty RabbitMQ queue can come from consumers acking prematurely; shrinking Pulsar backlog does not prove messages produced the right outcomes.

### 7.3. Business metrics

Choose metrics reflecting user or business outcomes:

- Ratio of accepted orders to total valid orders.
- Payment success rate and declined transaction rate.
- Events rejected due to schema/business validation.
- Time from event emission to business completion.
- Orders reprocessed or skipped due to idempotency.
- Record discrepancies between source and target systems.

Use bounded labels such as service, binding, event type, and release version. Never use event IDs, order IDs, customer IDs, or very high-cardinality values as metric labels.

## 8. Comparing canary against baseline

Compare the new and old versions within the same load window, event mix, and infrastructure conditions. If traffic shifts significantly, normalize by message count or byte count.

Example:

| Metric | Old version | Canary | Difference | Assessment |
|---|---:|---:|---:|---|
| Processing p95 | 85 ms | 91 ms | +7.1% | Watch |
| Processing p99 | 210 ms | 285 ms | +35.7% | Exceeds example threshold |
| Handler error | 0.08% | 0.35% | +0.27 pp | Investigate |
| CPU | 48% | 63% | +15 pp | Headroom left? |
| Consumer lag | 1,200 | 4,800 | +3,600 | Check drain rate |
| Business success | 99.7% | 99.1% | -0.6 pp | Failed |

These illustrative figures show that a canary may succeed on most messages while p99 and business success have already degraded. Decisions must rely on pre-defined gates, not a single metric in isolation.

## 9. Dashboards and alerts

A rollout dashboard should display:

1. Version, image digest, old/new Pod counts, and rollout start time.
2. Throughput by binding and release version.
3. Processing latency p50/p95/p99.
4. Consumer lag or backlog alongside oldest message age.
5. Errors, retries, redeliveries, DLQ, and schema failures.
6. Business success/failure.
7. CPU, memory, GC, thread pools, and connection pools.
8. Broker health, replication, disk, and network.
9. Current rollout gate status and proceed/stop decision.

Conceptual PromQL examples:

~~~promql
sum(rate(stream_handler_errors_total[5m]))
/
clamp_min(sum(rate(stream_handler_invocations_total[5m])), 1)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le, binding) (
    rate(stream_handler_duration_seconds_bucket[5m])
  )
)
~~~

The metric names in these examples are custom application instrumentation names; Spring Cloud Stream does not provide these exact names out of the box across every version. When implementing, substitute actual Micrometer/binder metrics and verify units, labels, counter resets, and scrape intervals.

Alerts should prioritize meaningful symptoms:

- Consumer lag or oldest message age climbing continuously.
- Processing p99 exceeding SLO.
- Sharp spike in errors/retries/DLQ.
- Drop in business success.
- Broker connection/commit/ack failures.
- Pod restarts, OOMs, or CPU throttling.

Do not alert merely on a monotonically increasing counter. Use rates, ratios, windows, and proper thresholds to avoid false alarms.

## 10. Monitoring Kafka during rollout

For Kafka, monitor at least:

- Lag by topic, partition, and consumer group.
- Offset commit rate and commit failures.
- Rebalance count/reason and duration partitions spend unassigned.
- Lagging record count and oldest lagging record age.
- Producer send errors, retries, and request latency.
- Under-replicated partitions, offline partitions, and ISR shrinks.
- Kafka Streams task/state restoration if the app is stateful.

A same-group canary alters partition assignments. When new Pods join or old Pods leave the group, rebalances can introduce a brief processing pause. Monitor rebalances and lag during rollout to distinguish handoff cost from application bugs.

Do not look only at total lag. One congested partition can be masked by other empty partitions. Under key skew, a few partitions carry most traffic; inspect per-partition lag and key distribution.

## 11. Monitoring RabbitMQ during rollout

For RabbitMQ, monitor:

- Ready messages and unacknowledged messages.
- Consumer count and consumer capacity.
- Publish, deliver, ack, nack, and redelivery rates.
- Queue depth and oldest message age if instrumented.
- Connection/channel churn.
- Publisher confirm latency and unroutable messages.
- Memory/disk alarms, flow control, and node health.

When adding new consumers to a queue, messages may be dispatched to old or new consumers depending on prefetch and load. Adding consumers does not guarantee proportional throughput gains if a downstream database is the bottleneck.

When rolling back consumers, unacked deliveries may be requeued. Monitor redelivery rates and idempotency. Never purge a queue just to zero out a dashboard during an incident.

## 12. Monitoring Pulsar during rollout

For Pulsar, monitor:

- Backlog by topic and subscription.
- Dispatch rate, ack rate, and redeliveries.
- Consumer count, subscription type, and ownership.
- Unacked messages and acknowledgment timeouts.
- Producer send latency/failures.
- Broker/BookKeeper health, storage latency, and ledger errors.
- Partitioned topic distribution and per-partition backlog.

When a canary uses a separate subscription, it can receive all messages independently. Verify whether the subscription starts at `earliest` or `latest`, along with retention and backlog, before opening the consumer. A new subscription reading deep history can spike broker and storage load.

## 13. Schemas and contracts while two versions run together

Rolling/canary deployments usually create a period where old and new versions coexist. Producers, consumers, and schemas must stay compatible throughout this window.

Questions to answer:

- Can the old consumer read messages emitted by the new producer?
- Can the new consumer read old messages still sitting in queues/topics/backlogs?
- Do new fields have appropriate defaults or optionality?
- Did any enum, number type, timestamp format, or field meaning change?
- Do retry topics and DLQs still retain older schemas?
- Did content types, serializers, or schema registry subjects change?

An expand-contract strategy is generally safer:

1. Expand the schema so both old and new versions can read it.
2. Deploy the new consumer while still supporting old fields.
3. Switch producers to emit new fields once consumers are compatible.
4. Wait out the retention/retry window for old messages.
5. Only then remove old fields or contracts.

Do not delete fields or change types in the same release while old consumers are still running. Verify schema compatibility with registry tools or contract tests before rollout.

## 14. Database migrations and rollback readiness

Rolling back an application does not automatically roll back database schemas. If a new release adds columns, indexes, or tables, the old version must still run during rollback.

Apply expand-contract:

- Expand: add nullable columns, new tables, or compatible indexes.
- Deploy: ship code capable of reading both old and new shapes.
- Migrate data: controlled backfill, monitoring locks and load.
- Switch: shift reads/writes to the new structure.
- Contract: drop old structures in a separate release after the rollback window closes.

Do not run destructive migrations right before a canary rollout without backups and tested restores. Every migration needs an owner, estimated duration, lock impact, and post-run verification query.

Rolling back code may require keeping the new schema. Do not automatically run down-migrations when reverting binaries; down-migrations can delete data that the old version cannot recover.

## 15. State stores and Kafka Streams

If an application uses Kafka Streams through Spring Cloud Stream, a rollout can affect state stores, changelog topics, repartition topics, task assignments, and restore times.

Before upgrading:

- Identify `application.id` and associated state stores/changelogs.
- Verify state store schemas and serialized keys/values.
- Check changelog retention and restoration capability.
- Check whether topology changes create new repartition topics.
- Measure task migration and state restoration duration.
- Verify whether the new version can read state written by the old version and vice versa.

Do not arbitrarily change `application.id` for a "canary". A different `application.id` creates an independent processing/state group and may re-read the entire input from its own offsets, causing duplicate side effects or extra load. If parallel execution is necessary, isolate outputs and state.

If the state format is not backward-compatible, rolling back the old binary may fail to read new state. Choose one of these tested options:

1. Keep state serialization compatible across multiple releases.
2. Use a new state store with controlled migration/backfill.
3. Snapshot/back up state and test restoring with the old version.
4. Use a separate `application.id`/state namespace when controlled replay is acceptable and side effects are isolated.

Rolling back a stateful application must be rehearsed; swapping the image tag alone is not enough.

## 16. Defining rollback triggers

Roll back when the benefit of keeping the new version is outweighed by the risk of continuing to run it. Triggers should distinguish self-recovering issues from issues causing data impact.

### 16.1. Roll back immediately

- Messages lost due to faulty ack/commit logic.
- Severe duplicate side effects such as double charges or duplicate orders.
- New schema breaks deserialization on existing consumers.
- Publishing to wrong destinations or routing keys causing data misdelivery.
- Data corruption or unrecoverable state stores.
- Security vulnerabilities or data exposure.

### 16.2. Pause rollout and investigate

- p95/p99 rises without breaching rollback threshold.
- Consumer lag rises briefly during rebalance.
- CPU rises while headroom remains.
- A few downstream errors recover via retries.
- Canary has not gathered enough samples to conclude.

If metrics are missing or dashboards are stale, do not expand the rollout. Pause to restore observability.

### 16.3. Do not use rollback to mask data bugs

If the new version already wrote incompatible data or produced side effects, reverting to the old binary does not fix that data. A separate incident runbook is needed to scope impact, pause producers if needed, reconcile, repair data, or perform a controlled replay.

## 17. Preparing rollback before deployment

Every release needs a rollback package containing:

- Artifact/image digests of the current and previous versions.
- ConfigMap/secret versions or versioned configuration.
- Dependency and binder version list.
- Database migrations and migration status.
- Schema compatibility report.
- Relevant Kafka topics/partitions/groups, Rabbit vhosts/exchanges/queues, and Pulsar topics/subscriptions.
- State stores/changelogs and restoration steps if applicable.
- Commands or procedures to halt rollout, redeploy, and verify.
- Rollback approver and incident communication channels.

Do not write just "revert deployment". Record exact artifacts, configs, executed migrations, and which steps are reversible.

### 17.1. Sample rollback runbook

| Step | Action | Verification |
|---|---|---|
| 1 | Halt rollout expansion; keep dashboards and logs | No new Pods continue being created |
| 2 | Assess whether to pause failing producers or bindings | Message emission rate and side effects are under control |
| 3 | Select image digest and config of previous stable release | Artifact/config match release record |
| 4 | Redeploy previous version per rolling policy | Pods Ready and consumers connected to right destinations |
| 5 | Verify schema, database, and state store compatibility | Zero deserialization/migration/state-restore errors |
| 6 | Monitor lag, queues/backlogs, retries, DLQ, and business SLIs | Metrics return within thresholds |
| 7 | Reconcile messages and side effects within the incident window | No unresolved data discrepancies remain |
| 8 | Document root cause, decisions, and closure time | Complete incident/release record |

This is a reference sequence; in some incidents, consumers or producers must be paused before rolling back to keep errors from spreading. That decision must follow system runbooks and backlog impact analysis.

## 18. Kafka offsets during rollback

Kafka offsets track a consumer group's reading progress. When reverting to an older version, keeping the same consumer group generally resumes from committed offsets. Do not reset offsets to `earliest` or `latest` as a default rollback step.

Before manipulating offsets:

- Record group ID, topic, partitions, and committed offsets.
- Identify records already processed but not yet committed.
- Verify whether the old version can read any remaining new records.
- Check transactions/producer outputs and emitted side effects.
- Replay only a defined offset range with idempotency and reconciliation procedures.

Resetting offsets can cause duplicates or skip data. When a replay is required, test first in an isolated environment or a new group with outputs blocked; never run generic reset commands without knowing the exact scope.

## 19. RabbitMQ and Pulsar during rollback

### RabbitMQ

- Keep queues and unacked messages intact.
- When the new consumer stops, unacked messages may be requeued.
- Verify the rolled-back consumer shares the same contract, routing, and permissions.
- Do not delete queues, purge messages, or alter bindings to "clean up" a rollout without a data plan.
- Check DLQs and retry queues since failed messages may be waiting there.

### Pulsar

- Record topic, subscription name, subscription type, and cursor/backlog.
- Durable subscriptions normally preserve progress independently of consumer processes.
- Do not delete subscriptions or reset cursors as a default rollback step.
- Verify the old version can read remaining backlog messages and messages produced during the canary.
- If the canary used a separate subscription, stop that subscription as planned and evaluate backlog/retention before cleanup.

In both systems, unacked messages may be redelivered. Handlers must be idempotent and outbound side effects must be reconciled.

## 20. Blue-green and traffic switching

Blue-green maintains two environments:

- Blue: current version serving traffic.
- Green: new version deployed and verified.

For HTTP, Service/Ingress can route to Green and revert to Blue. For message consumers, you must decide which environment owns the subscription/consumer group and which is allowed to write side effects.

A safer pattern for consumers is:

1. Deploy Green without receiving production messages yet, or run it in shadow mode.
2. Verify health, schemas, state restore, and dependencies.
3. Stop intake on Blue via a drain procedure.
4. Transfer consumer group or subscription ownership to Green.
5. Monitor backlog, redeliveries, and business SLIs.
6. Keep Blue ready for rollback, but never allow both environments to emit side effects simultaneously.

If both Blue and Green consume with separate groups/subscriptions, both receive the same messages. This is only safe when shadow outputs are isolated or business operations are designed to prevent duplication.

## 21. Feature flags and rapid kill switches

Feature flags can decouple code deployment from enabling new behavior. When a logic bug appears while the new version's runtime remains healthy, disabling a flag can reduce impact faster than rolling back the entire artifact.

A feature flag requires:

- A safe default value.
- Reading from a trustworthy configuration source.
- An audit trail of who toggled it and when.
- Metrics showing which code branch is executing.
- A cleanup plan to remove the flag after migration finishes.

Flags do not solve binary incompatibilities, memory leaks, dependency conflicts, schema serialization bugs, or state store incompatibilities. If the bug lies in the runtime/framework, roll back the artifact.

## 22. Testing the rollback plan

A rollback is only trustworthy after it has been rehearsed. Test in staging with production-like data and topology:

1. Deploy the old version, send representative messages, and record a baseline.
2. Deploy the new canary, generating normal and peak load.
3. Intentionally trip a failure gate such as elevated latency or schema validation failures.
4. Stop the rollout and redeploy the old artifact.
5. Verify the consumer group/subscription resumes from the right progress point.
6. Inspect unacked messages, retries, and DLQs.
7. Reconcile the database, output topics/queues, and business results.
8. For Kafka Streams, verify state restoration or migration rollback.
9. Measure time from rollback decision until metrics stabilize.
10. Document missing manual steps, permissions, or dependencies.

A rehearsal does not need to cause dangerous data corruption. Use test events, isolated sinks, and test databases to verify the path.

### 22.1. Test matrix by binder

| Scenario | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| New consumer joins | Rebalance and partition assignment | Consumer count and dispatch | Subscription dispatch/ownership |
| Consumer stops | Offset commit and uncommitted records | Unacked deliveries/requeue | Ack state/redelivery |
| Binary rollback | Same group/offset, schema compatibility | Same queue/routing/permissions | Same subscription/cursor |
| Replay | Controlled offset adjustment | Procedural republish/requeue | Subscription cursor/replay |
| Stateful processing | Changelog/state store restore | App state external to broker | External state or application store |

## 23. Checklist before expanding a canary

- [ ] Artifacts, image digests, and configs are recorded.
- [ ] Technical and business baselines have explicit measurement windows.
- [ ] Appropriate rolling/canary/blue-green/shadow strategy is selected.
- [ ] Consumer groups/subscriptions and actual message distribution are understood.
- [ ] Side effects of separate shadow/canary runs are isolated.
- [ ] Schemas and message contracts are compatible with the old version.
- [ ] Database migrations follow expand-contract and stay within the rollback window.
- [ ] Kafka Streams state/changelogs have a restoration plan if used.
- [ ] Dashboards display metrics by binding and release version.
- [ ] Rollout gates, evaluation windows, and decision-makers are agreed upon.
- [ ] Alerts for lag/backlog, latency, errors, retries, DLQ, and business SLIs are active.
- [ ] Rollback artifacts/configs and a tested runbook are ready.
- [ ] Offsets/cursors are not reset and queues are not purged as a default rollback step.
- [ ] A plan exists to reconcile messages and side effects after rollback.
- [ ] An operator is actively watching the rollout and logging decisions.

## 24. Checklist when deciding to roll back

- [ ] Halt rollout expansion and log the decision timestamp.
- [ ] Classify whether the fault is in code, config, schema, state, broker, or dependencies.
- [ ] Control producers/consumers if the bug continues generating bad data.
- [ ] Select the exact image digest and config of the stable version.
- [ ] Verify database migration and state compatibility before starting the old version.
- [ ] Keep offsets/cursors/queues intact unless following an explicit replay plan.
- [ ] Deploy the old version and verify readiness plus binder connections.
- [ ] Monitor lag, backlog, redeliveries, retries, DLQ, and business success.
- [ ] Reconcile side effects, duplicates, and data emitted during the fault window.
- [ ] Close the incident only after metrics stabilize and backlogs return to acceptable levels.

## 25. Operational principles

1. Measure a baseline before rollout and compare using identical metric definitions.
2. Separate HTTP rollouts from message consumer rollouts; brokers have distinct distribution semantics.
3. Do not call an isolated consumer group a partial canary if it reads the entire stream.
4. Isolate side effects when running shadow or replay flows.
5. Enforce rollout gates agreed upon before deployment.
6. Monitor both technical metrics and business SLIs.
7. Evolve schemas and databases in a backward-compatible direction.
8. Maintain a dedicated plan for Kafka Streams state stores/changelogs.
9. Prepare rollback artifacts, configs, and runbooks before starting.
10. Never reset offsets, cursors, or purge queues reflexively.
11. Rehearse rollbacks with production-like brokers and test data.
12. After rolling back, reconcile messages and business side effects before closing the incident.

## Official references

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling updates, `maxSurge`, and `maxUnavailable`.
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): readiness, termination, and lifecycle.
- [Argo Rollouts](https://argo-rollouts.readthedocs.io/): canary, blue-green, and analysis gates.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/): bindings, binders, and consumer configuration.
- [Apache Kafka Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers): partition assignment, groups, and offsets.
- [Apache Kafka Streams Operations](https://kafka.apache.org/documentation/streams/): state stores, changelogs, and operating Kafka Streams.
- [RabbitMQ Consumers](https://www.rabbitmq.com/docs/consumers): consumer dispatch, acknowledgments, and prefetch.
- [RabbitMQ Queues](https://www.rabbitmq.com/docs/queues): queue behavior, durability, and dead lettering.
- [Apache Pulsar Messaging](https://pulsar.apache.org/docs/next/concepts-messaging/): subscriptions, cursors, acknowledgments, and redelivery.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): instrumenting metrics and observations in Spring applications.
