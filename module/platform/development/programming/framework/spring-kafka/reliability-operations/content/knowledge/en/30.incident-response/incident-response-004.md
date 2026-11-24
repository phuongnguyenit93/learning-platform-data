# Runbook for Continuous Rebalancing

## Purpose and Scope

This runbook guides handling an Apache Kafka consumer group that continuously changes membership or partition assignments when an application uses Spring for Apache Kafka. The goal is to restore stable membership, minimize processing disruption, and preserve offset correctness.

A single rebalance can be normal behavior when deploying a new version, adding consumers, changing partition counts, or when a consumer leaves the group. An incident occurs when rebalances repeat within a short interval, causing partitions to be continuously revoked and reassigned, leaving listeners without enough time to process, destabilizing the consumer group, or increasing consumer lag.

This runbook focuses on consumer groups and Spring Kafka listener containers. Log formats, metric names, and configuration options may differ across Kafka client, broker, Spring Kafka, and group protocol versions. Before applying configurations, verify the cluster's actual versions and protocol.

## Symptoms and Impact

Common symptoms:

- Consumer logs repeatedly show messages about joining the group, starting/completing rebalances, revoking partitions, or receiving new assignments.
- Callbacks `onPartitionsRevoked`, `onPartitionsAssigned`, or `onPartitionsLost` are invoked frequently.
- Rebalance counts rise continuously while consumer count and subscription configuration have no planned changes.
- The consumer group oscillates between `PreparingRebalance`, `CompletingRebalance`, and `Stable`, or continuously increments generation.
- Consumer lag rises, throughput drops, processing pauses intermittently, or end-to-end latency increases.
- The application logs commit errors such as `CommitFailedException`, processing errors because partitions were already revoked, or records redelivered after a rebalance.

Rebalancing can pause consumption while the coordinator assigns partitions. Uncommitted records may be redelivered, so handlers must remain safe against duplicate processing. Rebalancing does not automatically prove a broker failure; the root cause may lie in listeners taking too long, restarting pods, flapping autoscaling, networking, or consumer configuration.

## Handling Principles

1. Identify the exact cluster, consumer group, and incident timeframe before altering configuration.
2. Collect group state, logs, and metrics before restarting or scaling consumers. Preserve timestamps and client IDs to correlate application and broker logs.
3. Find what causes consumers to leave the group or forces the coordinator to recompute assignments. Do not treat increasing timeouts as a default fix.
4. Change only one parameter group per intervention, record old values, and observe results.
5. Never delete the consumer group, reset offsets, or change partition counts as an emergency workaround without a dedicated plan and operational approval.

## Incident Response Procedure

### 1. Confirm Scope and Impact

Record the following details:

| Information | What to determine |
|---|---|
| Environment and cluster | Production/staging, bootstrap servers, and deployment region |
| Consumer group | Exact `group.id`, subscribed topics |
| Application | Service name, release version, Spring Kafka and Kafka client versions |
| Timing | Start time, rebalance frequency, most recent changes prior to the incident |
| Scope | One group, multiple groups on the same cluster, or multiple clusters |
| Impact | Lag, throughput, processing errors, latency, and affected business flows |

Correlate the start time with deployments, pod restarts, replica/concurrency changes, autoscaling, topic/partition changes, broker restarts, or network incidents. If multiple independent groups are affected simultaneously, prioritize checking brokers, coordinators, and network infrastructure before tuning individual listeners.

### 2. Snapshot Consumer Group State

Run commands from a host with Kafka CLI and cluster access. Replace environment variables with details for the environment under investigation:

```bash
export BOOTSTRAP_SERVERS="broker-1:9092,broker-2:9092"
export GROUP_ID="orders-consumer-v1"

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server "$BOOTSTRAP_SERVERS" \
  --describe \
  --group "$GROUP_ID" \
  --members \
  --verbose
```

Depending on the Kafka version, `--state`, `--members`, and `--verbose` options may vary. If the current CLI does not support them, use the basic `--describe --group` command and gather member details from admin tools or broker logs.

Record:

- Whether the group is `Stable` or currently rebalancing.
- Member count, consumer ID, client ID, host, and partitions assigned to each member.
- Whether members disappear and reappear, or whether multiple new client IDs appear sequentially.
- Whether any partitions have no assigned consumer, or assignments shift between checks.
- Lag per partition and the rate of lag increase/decrease.

Capture state snapshots multiple times, spaced closely enough to match the incident frequency. A single snapshot may catch the group mid-rebalance and fail to show which member is dropping out.

### 3. Correlate Application Logs and Metrics

Search logs by `group.id`, `client.id`, pod/host, and timestamp. Useful loggers typically include:

- `org.apache.kafka.clients.consumer.internals.ConsumerCoordinator`
- `org.apache.kafka.clients.consumer.internals.AbstractCoordinator`
- `org.springframework.kafka.listener.KafkaMessageListenerContainer`
- Loggers for the listener and the dependencies it calls.

Look for messages indicating a consumer left the group, lost connection to the coordinator, exceeded `max.poll.interval.ms`, failed heartbeats, had partitions revoked/assigned, or container stop/start events. Exact messages depend on the Kafka client version.

If the application exports Kafka client metrics via JMX or Micrometer, correlate the corresponding metrics available in the running version:

| Metric group | How to use |
|---|---|
| `rebalance-total`, `rebalance-rate-per-hour` | Confirm rebalance count and rate |
| `assigned-partitions` | Track the number of partitions assigned to a consumer |
| `heartbeat-rate`, `heartbeat-response-time-max` | Detect slow heartbeats or abnormal responses |
| `poll-idle-ratio-avg`, `time-between-poll-max` (if available) | Identify consumers spending too much time outside the poll loop |
| `records-lag-max` and per-partition lag | Assess impact on data catch-up capability |

Metric names and export paths vary by Kafka client and observability stack. Do not conclude a metric does not exist merely because the current dashboard does not collect it. Also inspect JVM pauses/GC, CPU throttling, memory pressure, thread pools, connection pools, and response times of databases or APIs called by the listener.

### 4. Identify Root Cause from Signals

#### A. Listener Processing Exceeds `max.poll.interval.ms`

This is a common cause when listeners process synchronously. Consumers must call `poll()` frequently enough. In Spring Kafka, the time a listener spends processing a record or entire batch usually runs on the container's execution path; if processing exceeds the limit between two polls, the Kafka client may proactively leave the group and trigger a rebalance.

Check:

- p95/p99 and maximum processing duration for a record or batch.
- Whether a batch listener processes many records sequentially or waits on a slow dependency.
- Whether the listener calls external APIs, queries databases, waits on locks, or performs synchronous retries.
- Whether the error handler/backoff holds the listener thread in a long wait state.
- Whether logs report the consumer exceeded `max.poll.interval.ms` or failed to poll in time.

Remediation:

1. Measure actual duration at each step of the listener to find slow dependencies.
2. Reduce `max.poll.records` to bound the work per poll if the current batch is too large.
3. Optimize queries, use appropriate bulk operations, set timeouts on external calls, and bound per-batch processing time.
4. Increase `max.poll.interval.ms` only when long processing times are intentional and measured. Choose a value with buffer based on the worst-case acceptable processing time; also check business and transaction timeouts.

Increasing `max.poll.interval.ms` can prevent consumers from being evicted during long processing, but delays detection of hung consumers. It does not fix CPU overload, disconnected dependencies, or infinitely blocked listeners.

#### B. Unstable Heartbeats, Session Timeouts, Network, or JVM

A consumer may be marked inactive by the coordinator if heartbeats do not arrive on time. Causes can include network interruptions, DNS/TLS issues, overloaded brokers/coordinators, JVM stop-the-world pauses, CPU throttling, or hung processes.

Check:

- Logs for heartbeat timeouts, coordinator unavailable, disconnect/reconnect, and request timeouts.
- Heartbeat metrics, response latency, and timestamps when members disconnect.
- JVM GC pauses, CPU throttling, node pressure, packet loss, DNS, and broker connectivity.
- Broker logs for coordinator activity, request queues, network threads, and restarts/failovers.

With the classic group protocol, review `session.timeout.ms` and `heartbeat.interval.ms` along with broker-permitted limits. Do not raise session timeout blindly on gut feeling: larger values slow dead-consumer detection, while values too low make the group sensitive to jitter. Adjust only after ruling out network, JVM, and broker issues. With the new consumer group protocol (`group.protocol=consumer`), some heartbeat/session parameters are managed on the broker and configured differently from the classic protocol; consult documentation for the running Kafka version.

#### C. Members Continuously Added, Removed, or Restarted

Deployments, pod crashes, overly aggressive liveness probes, flapping autoscaling, or `concurrency` changes all alter membership. In these cases, rebalancing is the group's reaction to changing members.

Check:

- Rollout history, pod restart counts, OOMKilled events, liveness/readiness probes, and node evictions.
- Replica count and `spring.kafka.listener.concurrency` before and after the incident start time.
- Whether the autoscaler repeatedly scales replicas up and down around a lag or CPU threshold.
- Actual total consumers, approximately `replicas × listener concurrency` per corresponding listener container.
- Whether `group.instance.id` is duplicated across members if using static membership.

Remediation:

- Stabilize replicas and concurrency during investigation; configure autoscaling with appropriate cooldown/stabilization windows to prevent rapid scale oscillation.
- Fix root causes of pod restarts, probe timeouts, OOMs, or overly rapid rollouts.
- Perform controlled rolling updates and allow containers to shut down gracefully so consumers leave the group cleanly.
- If using static membership, assign a unique, stable `group.instance.id` to each member. Avoid reusing the same ID across two concurrently running pods. Verify how Spring Kafka generates IDs for child containers when `concurrency > 1` for your library version.

Static membership can reduce rebalances from brief restarts, but an old member may hold its slot until session timeout expires if it does not return. Do not enable static membership if the system cannot guarantee unique IDs and stable member lifecycles.

#### D. Changes to Subscriptions, Partitions, or Assignment Strategy

A group can rebalance when topics are added/removed, pattern subscriptions match new topics, partition counts change, or members have incompatible subscriptions or assignment strategies.

Check:

- The list of topics each application subscribes to; pay attention to `topic pattern` and metadata changes.
- Partition count changes, newly created topics, or permission changes.
- `partition.assignment.strategy` across all group members and client versions.
- Whether listener/container config comes from Spring Boot properties or a custom `ConsumerFactory`/`ConcurrentKafkaListenerContainerFactory`.

With the classic group protocol, `CooperativeStickyAssignor` can reduce the number of partitions revoked during membership changes. Switch assignment strategies only after confirming all group members support it and following the migration guide for your Kafka client version. Cooperative assignment reduces disruption when rebalances are needed; it does not fix members repeatedly leaving the group. With `group.protocol=consumer`, assignor mechanisms and related configs differ from the classic protocol.

#### E. Broker or Group Coordinator Issues

If multiple consumer groups on the same cluster become unstable together, or application logs show the coordinator repeatedly unavailable, check brokers and infrastructure before tuning listeners.

Check broker restarts/failovers, controller/coordinator logs, request queues, network processors, disk/I/O, network latency, and client-to-broker connection errors. Group incidents by the broker acting as coordinator for each group. If escalating, provide timestamps, group ID, relevant broker/coordinator, client IDs, logs from both sides, and pre/post-incident metrics.

### 5. Apply Controlled Mitigations

Choose mitigations backed by evidence. The Spring Boot configuration example below illustrates limiting batch size and setting certain consumer properties; values are starting points to tune for actual load, not universal defaults:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-consumer-v1
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 600000
        "[partition.assignment.strategy]": org.apache.kafka.clients.consumer.CooperativeStickyAssignor
    listener:
      concurrency: 3
```

Notes when applying:

- This example is appropriate only when the listener has measured long processing times and all group members support the chosen assignment strategy. Do not raise `max.poll.interval.ms` just to hide a hung listener.
- `max.poll.records` caps the records returned per poll; lowering it can shorten per-batch processing time, though overly small batches can reduce throughput.
- Total consumers in the same group depend on replicas and concurrency. When consumer count exceeds partition count, some consumers receive no partitions; this does not necessarily cause continuous rebalancing, but increases cost and operational complexity.
- If declaring a custom `ConsumerFactory` or listener container factory, verify the final configuration passed to the Kafka client/container. Custom beans can override Spring Boot properties.
- `group.instance.id` must be unique per member. Never use the same literal string across all replicas.
- Changing `partition.assignment.strategy` or group protocol requires a compatible rollout plan across every member in the group.

If the issue stems from synchronous retry/backoff, review error handling options supported by your Spring Kafka version. For long backoffs, `ContainerPausingBackOffHandler` (available in Spring Kafka versions supporting this mechanism) or retry topics may be better than holding listener threads idle for too long. Check offset semantics, processing order, and redelivery behavior before changing retry strategies.

Do not offload work to arbitrary threads and return from the listener without designing commits/acknowledgments, error handling, and partition ownership clearly. When a listener returns before work completes, offsets may be committed while business work is unfinished, or results may arrive out of order. If asynchronous processing is needed, design acknowledgments and bound in-flight work according to your Spring Kafka version's capabilities.

## Post-Mitigation Verification

Monitor for at least longer than the previous rebalance cycle and long enough to cover representative load. Verify:

- The consumer group remains `Stable`; member counts and assignments do not fluctuate outside planned changes.
- `rebalance-total` stops rising abnormally; revoke/assign callbacks no longer fire rapidly.
- No more logs showing exceeded `max.poll.interval.ms`, heartbeat timeouts, or abnormal disconnects/reconnects.
- Consumer lag decreases or stabilizes at an acceptable level; throughput and latency return to target.
- p95/p99 processing time remains within the chosen bounds for poll interval and business timeouts.
- No commit errors, lost records, or business errors from duplicate processing appear. Reconcile offsets and business outcomes against existing idempotency mechanisms.
- New consumers joining the group receive partitions as expected after rollout/scaling.

Record configuration changes, timestamps, operator, pre/post metrics, and monitoring outcomes. If rebalancing resumes, revert to the prior configuration if the new change worsened the situation, then continue investigating using fresh signals.

## When to Escalate

Escalate to the Kafka/platform team in any of the following cases:

- Multiple consumer groups on the same cluster rebalance simultaneously without corresponding application changes.
- Coordinators/brokers repeatedly disconnect, restart, or suffer prolonged request/network errors.
- A group cannot stabilize even though members and listeners are healthy and configurations are consistent.
- Broker-level settings, group protocol, or partition topology changes are needed, or actions could affect multiple consumer groups.

When escalating, attach cluster/environment, group ID, topic, timestamps and timezone, Kafka broker/client versions, Spring Kafka version, group protocol, member count, group state, lag, consumer/coordinator logs, rebalance/heartbeat/poll metrics, and recent deployment changes. State mitigations already attempted and their outcomes to avoid duplicated effort.

## Quick Action Checklist

- [ ] Confirm group ID, cluster, start time, and impact scope.
- [ ] Snapshot group state, members, assignments, and lag multiple times.
- [ ] Correlate consumer/container/coordinator logs with poll, heartbeat, and rebalance metrics.
- [ ] Inspect listener processing duration, batch size, retry/backoff, and slow dependencies.
- [ ] Check pod restarts, deployments, replicas, concurrency, autoscaling, and static member IDs.
- [ ] Check subscriptions, topic/partition changes, assignment strategy, and group protocol.
- [ ] If multiple groups are affected together, inspect brokers/coordinators and network.
- [ ] Apply one evidence-backed change, record the old value, and monitor the outcome.
- [ ] Confirm group stability, lag recovery, and absence of commit or business errors.
