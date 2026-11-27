# Rolling Updates with the Same Group and Consumer Rebalancing

When deploying a new version of an event-processing application built with Spring Cloud Stream, operations teams usually want to replace Pods or instances gradually without stopping the entire pipeline. In Kubernetes, that is a **rolling update**: new versions roll out in batches while old versions are stopped once replacement criteria are met. When instances consume the same Kafka topic using the **same consumer group**, new members joining or old members leaving the group affects partition assignment and can trigger a **consumer rebalance**.

Rolling updates help sustain processing capacity, yet they do not inherently guarantee zero processing pauses, zero message redeliveries, or no repeated business side effects. Kafka stores offsets by group and partition; the Spring Cloud Stream binder manages the underlying consumers; Kubernetes manages container lifecycles. These three mechanisms must align with in-flight message completion times, offset commits, and system load capacity.

This lesson focuses on Kafka consumer groups in Spring Cloud Stream while highlighting differences when an application uses the RabbitMQ binder, Pulsar binder, or Kafka Streams binder. Configuration examples serve as starting points that must be validated against your exact Spring Boot, Spring Cloud Stream, Kafka client/broker versions, and deployment environment.

## Learning Objectives

After this lesson, you can:

- Explain how a rolling update differs from changing consumer groups.
- Predict partition assignments when new Pods join and old Pods leave the same Kafka group.
- Distinguish eager, cooperative rebalancing, and the new consumer group protocol.
- Understand the roles of `group.id`, `concurrency`, `group.instance.id`, and timeouts.
- Configure the Spring Cloud Stream Kafka binder with a fixed group.
- Design Kubernetes RollingUpdate, readiness, liveness, and graceful termination.
- Reduce pause duration and avoid message loss when Pods stop.
- Handle duplicate deliveries, transaction boundaries, and per-partition ordering.
- Monitor lag, rebalances, assignments, processing errors, and drain durations.
- Test rolling updates, failed rollouts, and rollbacks with real data.

## 1. Same Group Means Sharing Work, Not Broadcasting Copies to Every Pod

Consider topic `orders.created` with **6 partitions** and a Spring Cloud Stream application named `order-processor` running **3 Pods**. Each Pod creates a Kafka consumer in group `order-processing`.

~~~text
Kafka topic: orders.created (6 partitions)

Partition:   P0   P1   P2   P3   P4   P5
              \   /     \   /     \   /
Group:       Pod A       Pod B       Pod C
             v1.0        v1.0        v1.0
~~~

This is an illustrative assignment diagram. The actual Kafka assignor decides which partitions belong to which consumer; never assume P0/P1 always go to A and P2/P3 to B.

In a standard consumer group, each partition is assigned to **one consumer member at a time**. Multiple Pods in the same group process different partitions concurrently. If you want every version to receive all events for parallel testing, you must use a different group—though business side effects may then occur twice if both groups write to live systems.

### 1.1. What Happens During a Rolling Update?

Suppose the Deployment creates Pod D running v2 before stopping Pod A:

~~~text
T0: A(v1), B(v1), C(v1)          -> group has 3 members
T1: A(v1), B(v1), C(v1), D(v2)   -> new member joins
T2: B(v1), C(v1), D(v2)          -> A leaves the group
T3: B(v1), C(v1), D(v2), E(v2)   -> another member joins
...
Tn: D(v2), E(v2), F(v2)          -> new version rollout complete
~~~

Whenever a member joins or leaves, the group coordinator may adjust partition assignments. Some consumers pause briefly to hand off or receive partitions, while the topic remains intact, producers continue writing, and records wait in the Kafka log. The rollout goal is to minimize slowdowns and ensure new consumers resume from valid offsets.

### 1.2. Two Versions Coexisting in One Group

A Kubernetes rolling update creates an interval where v1 and v2 coexist. Both must be able to read schemas emitted by current producers and write mutually compatible side effects.

For example, if v2 begins requiring a `currency` field unknown to v1, deploy schema-compatible changes following expand/contract first. Do not enable an incompatible change while v1 Pods are still reading events.

## 2. How Does Kafka Rebalancing Work?

A group member may need reassignment when:

- A new consumer joins the group.
- A consumer closes or leaves the group.
- A consumer misses heartbeats past the session timeout.
- Assignments change because the topic gains partitions or subscriptions change.
- A consumer fails to call `poll()` within `max.poll.interval.ms`.
- The broker/group coordinator changes or encounters a fault.

High-level sequence:

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant N as New Pod
    participant C as Kafka Coordinator
    participant O as Old Pod
    K->>N: Start v2
    N->>C: Join group
    C-->>O: Request assignment change if needed
    O->>O: Finish/close active work per lifecycle
    C-->>N: Assign partitions
    N->>N: Poll and process
    K->>O: SIGTERM when rollout conditions met
    O->>C: Leave/close consumer
    C-->>N: Update assignment if needed
~~~

This is a conceptual model, not an exact callback schedule for all assignors and protocols. Ordering also depends on Kafka version, Spring Kafka container, and shutdown configuration.

### 2.1. Group Membership and Committed Offsets

Kafka stores committed offsets per consumer group, topic, and partition combination. When a partition moves from Pod A to Pod D, D resumes at the offset committed by the group rather than restarting at offset 0 just because the Pod or image is new.

Example:

~~~text
P2: offsets 100 101 102 103 104 105 106 ...
    A executed business side effects for 104
    last committed group offset is 104
    (next position to read after committed work)

    A dies before committing the next position
    D receives P2, resumes reading from committed offset
~~~

In the example above, D may reprocess the record whose side effect A already executed. Offset representation should follow the convention "committed offset is the next position to read"; avoid confusing it with "ID of the last processed record." Duplicates can occur whenever side effects and offset commits are not inside the same transaction.

### 2.2. Eager Rebalance

With **eager** rebalancing, consumers participating in reassignment may have to revoke all existing assignments before receiving new ones. This creates noticeable pauses when the group is large or a rollout repeatedly adds and removes members.

### 2.3. Cooperative Rebalance

Cooperative rebalancing (such as `CooperativeStickyAssignor` in the classic protocol) can keep partitions that do not need to move, revoking only partitions that change owners. This typically reduces disruption, though it does not eliminate rebalances, duplicates, or waits for unfinished work.

With the **classic group protocol**, Kafka client configuration typically uses `partition.assignment.strategy`. Kafka 4.4 documentation lists `RangeAssignor, CooperativeStickyAssignor` as the default; because Range comes first, **do not assume cooperative mode is active by default**. Changing the assignor requires a compatibility plan and sequential rollout, especially when v1 and v2 share the group.

### 2.4. The New Consumer Group Protocol

Modern Kafka versions support `group.protocol` accepting `classic` or `consumer`. Classic uses client-side assignors; the `consumer` protocol (KIP-848) uses broker-side assignment and a different assignment update flow. With `consumer`, `group.remote.assignor` and broker-side timeouts become key; classic `heartbeat.interval.ms` and `session.timeout.ms` are not the corresponding tuning knobs.

Do not copy a classic configuration verbatim to the new protocol. Before upgrading protocols, verify support in the broker, Kafka client, Spring Kafka, Spring Cloud Stream binder, and migration guides; test in staging at the same group scale.

## 3. Keeping a Fixed Group in Spring Cloud Stream

Example handler function:

~~~java
@SpringBootApplication
public class OrderProcessorApplication {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService service) {
        return service::handle;
    }
}

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        Instant occurredAt) {}
~~~

Configuration example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processing
          consumer:
            concurrency: 1
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              autoRebalanceEnabled: true
~~~

Here:

- `processOrder-in-0` is the input binding name under the functional model.
- `destination` is the Kafka topic.
- `group` selects the group sharing offsets across all replicas.
- `concurrency` sets the number of consumer threads/containers per replica for binders that support it.
- `autoRebalanceEnabled=true` lets Kafka manage partition assignment via the group. When set to `false`, the binder uses static partition assignment based on `instanceCount`/`instanceIndex`; that is a different strategy requiring separate instance identity management and should not be mixed into a standard rolling group example.

**Do not change `group` in v2** if you want to continue from the old group's offsets. A new group has its own offsets and may reread historical data or start according to the offset reset policy; that changes the nature of the rollout.

### 3.1. Partition Count, Pod Count, and Concurrency

If a topic has `P` partitions, a Deployment has `R` replicas, and each replica has `C` consumer threads, the theoretical consumer member count is roughly `R × C`. Partition count caps parallel consumption within a group:

\[
\text{useful parallel consumers}
\leq
\min(P, R \times C)
\]

Examples:

| Partitions | Pods | Concurrency/Pod | Total Consumers | Notes |
|---:|---:|---:|---:|---|
| 6 | 3 | 1 | 3 | Each consumer can receive roughly 2 partitions |
| 6 | 3 | 2 | 6 | Can distribute 1 partition per consumer |
| 6 | 4 | 2 | 8 | At least 2 consumers sit idle without partitions, depending on assignment |
| 3 | 5 | 1 | 5 | Multiple Pods process zero partitions |

Increasing `replicas` or `concurrency` can make rebalances more frequent and raise connections, CPU, RAM, and DB pool usage. During a rollout with `maxSurge`, temporary consumer count rises even higher than steady state. Check headroom on both the application and downstream systems.

### 3.2. Do Not Enable Offset Reset on Rolling Deployments

For a group that already has committed offsets, new consumers should resume from those offsets. Never set `resetOffsets=true` to "start clean" during a rollout; doing so can re-read or skip large volumes of records depending on configuration. Settings like `startOffset`/`auto.offset.reset` apply only when no valid offset exists yet or an offset is missing/out of range per specific semantics.

## 4. Kubernetes RollingUpdate Strategy

A Deployment has two key parameters:

- `maxSurge`: Maximum extra Pods above desired replica count during an update.
- `maxUnavailable`: Maximum Pods allowed to be unavailable during the rollout.

Example for a Kafka processing application:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-processor
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-processor
  template:
    metadata:
      labels:
        app: order-processor
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: app
          image: registry.example.org/order-processor:2.0.0
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
~~~

Explanation:

- With 3 replicas and `maxSurge: 1`, Kubernetes can create at most 1 extra Pod above desired replicas during rollout.
- `maxUnavailable: 0` aims not to reduce the number of Kubernetes-Available Pods during updates; this does not guarantee the Kafka consumer holds partitions the instant the readiness probe succeeds.
- `terminationGracePeriodSeconds: 90` gives the container up to roughly 90 seconds to stop under the Kubernetes lifecycle; this is an illustrative number, not a universal default or optimal value for every handler.
- `startupProbe` grants startup time and prevents liveness restarts before initialization completes.
- Liveness and readiness here use Spring Boot Actuator probes; enable and expose the endpoints if your project configuration has not already done so.

The example assumes the application runs an HTTP web server with Spring Boot Actuator listening on port 8080. A consumer-only service without a web server will not expose these HTTP endpoints; in that case, explicitly configure an appropriate management HTTP endpoint or choose a different probe mechanism before applying the manifest.

Kubernetes uses Pod readiness/availability to pace rollouts, **not Kafka partition assignments or consumer lag directly**. Therefore, a v2 Pod can be HTTP-Ready before its consumer joins the group or receives partitions. If your SLA requires stricter guarantees, check bind/consumer assignment capability separately and tune readiness intentionally.

### 4.1. When Should `maxUnavailable` Be Greater Than 0?

If fast updates are prioritized and the pipeline tolerates a brief backlog, `maxUnavailable: 1` may be acceptable. However, with only 1 replica, that value can leave zero active consumers during replacement; if continuity is required, run multiple replicas and size the rollout budget properly.

`maxSurge: 1`, `maxUnavailable: 0` is a conservative starting configuration for 3 replicas, not proof of zero downtime. Test with real throughput and handler durations.

### 4.2. PodDisruptionBudget and Rollouts

`PodDisruptionBudget` (PDB) limits voluntary evictions via the Eviction API, such as node drains. Deployment rolling updates do not rely on PDB to enforce `maxSurge` and `maxUnavailable`. Configure both for their respective purposes; do not expect a PDB alone to make rolling updates safe.

## 5. Graceful Shutdown and Offset Commits

When Kubernetes deletes a Pod under normal lifecycle rules, the Pod enters `Terminating`; kubelet runs `preStop` if configured, then asks the container to stop (typically via SIGTERM). Once the grace period expires, the runtime can send SIGKILL. If the JVM misses the signal or gets killed too early, the Spring application context and consumer containers never get to shut down cleanly.

Spring Boot provides phased shutdown timing:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 60s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
~~~

In current Spring Boot versions, graceful shutdown of the embedded web server is enabled by default. You can explicitly set `server.shutdown: graceful` when making the policy explicit; verify your Spring Boot version. More importantly, **graceful shutdown of the HTTP server does not automatically prove Kafka listeners have finished processing**. Kafka listener containers have their own lifecycles and timeouts depending on the Binder/Spring Kafka.

### 5.1. Desired Shutdown Order

A safe shutdown workflow should achieve:

1. Pod stops accepting new HTTP traffic if HTTP ingress exists.
2. Consumers stop polling/accepting new records per lifecycle; stop/pause must coordinate with Spring Kafka containers.
3. In-flight messages finish or remain safe to reprocess.
4. Offsets commit only for successful processing; never commit early to "shut down faster."
5. Producers sending outputs are flushed/closed per binder policy.
6. Consumers close and leave the group; partitions reassign to surviving consumers.
7. JVM exits before Kubernetes exhausts its grace period.

Depending on implementation, containers may finish polled records in the current batch before stopping or require custom stop controls. Never promise "on SIGTERM all fetched records complete"; test with the longest handler duration and your configured ack mode.

### 5.2. Shutdown Time Budget

Choose `terminationGracePeriodSeconds` greater than the expected sum of:

\[
T_{\text{preStop}} + T_{\text{drain}} + T_{\text{flush}} + T_{\text{close}} + \text{buffer}
\]

For instance, if a message takes 40 seconds to process, producer flush takes 10 seconds, and container teardown needs extra time, Kubernetes's default 30 seconds will be insufficient. In the example config, the Spring lifecycle timeout is 60 seconds and Pod grace is 90 seconds; verify actual phases fit within the budget.

If using `preStop`, hook execution time **counts inside** the termination grace period. Do not add arbitrary sleeps: they can hold the consumer longer and starve the critical shutdown phases. Only use a hook for a clear purpose, such as signaling drain before a specific action, and test it.

### 5.3. Avoid Turning Liveness into a Kafka Lag Check

Liveness should reflect whether the process can still operate. If the broker pauses briefly or lag rises and liveness immediately reports DOWN, Kubernetes may mass-restart consumers, worsening rebalances and lag.

Readiness can reflect whether the app is ready for the traffic it serves; if using readiness on a consumer-only worker, understand exactly what Spring/Kubernetes will do when the probe fails. Tie readiness to assignment only when rollout rules genuinely demand it, avoiding a deadlock loop of "not assigned so not Ready, not Ready so rollout stalls."

## 6. Timeouts That Affect Rebalancing

Important Kafka settings:

| Setting | Meaning | Risk If Misconfigured |
|---|---|---|
| `max.poll.interval.ms` | Max gap between consumer `poll()` calls | Slow handlers may be deemed stalled; assignments shift |
| `session.timeout.ms` | Timeout to detect missing member heartbeats in classic protocol | Too short: spurious rebalances; too long: slow failover |
| `heartbeat.interval.ms` | Heartbeat cadence in classic protocol | Must align with session timeout |
| `max.poll.records` | Max records returned per poll | Large batches can stretch processing time |
| `group.instance.id` | Static member identity (if used) | Duplicate IDs cause fencing; unstable IDs lose benefits |
| `partition.assignment.strategy` | Classic-protocol assignor | Unplanned changes cause churn/mismatches |
| `group.protocol` | Selects `classic` or `consumer` | Each protocol uses different heartbeat/assignment configs |

Example Kafka consumer client config on a binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                "max.poll.records": 100
                "max.poll.interval.ms": 300000
~~~

In environments using `classic`, configure session and heartbeat settings compatible with the broker. With `group.protocol=consumer`, heartbeat/session timings are broker-governed; do not use classic knobs as substitutes. The values above are illustrative and do not prove a 100-record batch finishes within 5 minutes.

**Do not infinitely raise timeouts to mask slow handlers.** First measure P95/P99 processing duration, bound batch sizes, configure retry/backoff, and avoid blocking the consumer poll thread for too long.

## 7. Static Membership: Useful, Yet Not Default for Deployments

Kafka supports static group membership via `group.instance.id`. When a member with a stable ID restarts briefly, the coordinator can skip some rebalances. However:

- The ID must be unique per live consumer member in the group.
- Sharing an ID across multiple Pods leads to fencing or contention.
- Deployment rolling updates create new Pods with new names/UIDs and sometimes run concurrently with old Pods; keeping a stable, unique ID across overlap is hard.
- If session timeout is long, an unexpected old consumer crash can delay partition reassignment and increase lag.
- Spring Kafka `ConcurrentMessageListenerContainer` with concurrency > 1 may append suffixes to `group.instance.id` for child containers; verify ID generation in your runtime version.

If stable static membership is genuinely needed, consider a `StatefulSet` with ordinal-based Pod names and an appropriate update strategy. Even then, test the overlap case where an old Pod still holds membership as the new Pod appears; two members cannot use the same `group.instance.id` simultaneously.

For standard Deployments with dynamic Pod identities, dynamic membership is usually easier to operate. Never hard-code the exact same constant string for `group.instance.id` across all replicas.

## 8. Offset Commits, Duplicates, and Delivery Guarantees

Rolling updates typically do not lose records from the Kafka log; the main concern is what was committed and where side effects occurred.

| Event Sequence | After Old Pod Stops | Outcome |
|---|---|---|
| Offset committed before DB write succeeds | New Pod reads past committed offset | Business side effects may be lost |
| DB write succeeds, crash before offset commit | New Pod re-reads record | Side effects may execute twice |
| Side effect and dedupe marker committed in one DB transaction | New Pod re-reads record | Duplicate is recognized and skipped |
| Kafka read-process-write using Kafka transactions within proper scope | Transaction commits/aborts outputs and offsets together | Protects Kafka outputs and offsets within Kafka scope |

Do not alter commit modes just to make rollouts "smoother" without understanding semantics. For external DBs, HTTP calls, or payments, Kafka transactions do not automatically include those side effects.

### 8.1. Idempotent Consumer

Pattern using a processed-events table with a unique constraint:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Illustrative handler:

~~~java
@Service
class OrderService {

    private final ProcessedEventRepository processedEvents;
    private final OrderRepository orders;

    OrderService(
            ProcessedEventRepository processedEvents,
            OrderRepository orders) {
        this.processedEvents = processedEvents;
        this.orders = orders;
    }

    @Transactional
    public void handle(OrderCreated event) {
        boolean firstTime =
                processedEvents.insertIfAbsent("order-processing", event.eventId());

        if (!firstTime) {
            return; // already processed by an old Pod or earlier delivery
        }

        orders.applyOrderCreated(event);
    }
}
~~~

`insertIfAbsent` is a business repository method that must be implemented with an atomic insert and DB unique constraint, such as `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL. Do not implement it as "SELECT then INSERT," because two consumers can race. Both the DB marker and the order mutation must share the same transaction, and the Spring proxy must actually enforce `@Transactional`.

When the function bean invokes the proxied service, the transaction commits before the handler returns success. If the app dies after DB commit but before offset commit, the record may be redelivered; the marker prevents repeating side effects. If side effects involve HTTP calls or sending emails, use an idempotency key on the target system or an outbox, because a local DB transaction does not cover external APIs.

### 8.2. Processing Order

Kafka preserves record order within **one partition** by offset. During rebalancing, partition ownership changes; in-flight work or application-spawned async tasks may finish after the partition has already moved to a new member unless the application coordinates properly.

Do not assume topic-wide ordering across multiple partitions. If ordering by `orderId` is required, producers must partition by a stable key and consumers must avoid uncontrolled concurrent processing on the same key. Use sequence or version checks to detect stale, duplicate, or out-of-order events.

## 9. Using KafkaBindingRebalanceListener to Manage Assignments

The Spring Cloud Stream Kafka binder provides `KafkaBindingRebalanceListener` to observe or customize behavior when partitions are revoked and assigned. It helps applications maintain local caches, custom checkpoints, or partition-ownership-aware logic.

Example logging partition changes only:

~~~java
@Bean
KafkaBindingRebalanceListener partitionLifecycleLogger() {
    return new KafkaBindingRebalanceListener() {
        @Override
        public void onPartitionsRevokedAfterCommit(
                String bindingName,
                org.apache.kafka.clients.consumer.Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions) {
            log.info(
                    "Binding {} revoked partitions {}",
                    bindingName, partitions);
        }

        @Override
        public void onPartitionsAssigned(
                String bindingName,
                org.apache.kafka.clients.consumer.Consumer<?, ?> consumer,
                Collection<TopicPartition> partitions,
                boolean initial) {
            log.info(
                    "Binding {} assigned partitions {} (initial={})",
                    bindingName, partitions, initial);
        }
    };
}
~~~

In Spring Cloud Stream, a listener bean can apply to the application's Kafka consumer bindings. Do not perform slow I/O, blocking waits, or external service calls inside rebalance callbacks. If custom seeking is needed, thoroughly understand callback and offset commit semantics before implementing.

Binder documentation also specifies not using `resetOffsets=true` when providing a `KafkaBindingRebalanceListener`. Never call `seekToBeginning` inside a rebalance callback during rollouts if the goal is to resume from committed offsets.

## 10. How Do Rolling Updates Differ for the Kafka Streams Binder?

Kafka Streams runs topologies with tasks and local state stores; when instances change, Streams may:

- Move active tasks across instances.
- Restore state stores from changelog topics.
- Update partition/task ownership.
- Use standby replicas if configured to reduce recovery time.

A Kafka Streams app may need extra time to restore state before processing efficiently. The Spring Cloud Stream Kafka Streams binder has a different binding mechanism and Streams lifecycle than the Kafka message-channel binder; do not blindly apply every classic consumer property above to a Streams application.

When deploying stateful Streams:

- Keep `application.id` stable if you want to retain existing state/changelogs.
- Ensure state directories and changelog retention match requirements.
- Monitor restore lag, task assignment, and rebalance duration.
- Evaluate standby tasks and cache/state store sizing.
- Test instance readiness during restoration, avoiding confusing "process Running" with "topology fully serving."
- Never change `application.id` casually, as that equates to switching to a different logical Streams application.

## 11. RabbitMQ and Pulsar During Rolling Updates

This lesson focuses on Kafka consumer rebalancing, yet the same Spring Cloud Stream module includes RabbitMQ and Pulsar. Neither uses Kafka `group.id` or Kafka partition assignors.

| System | Work-Sharing Mechanism | Effect When a Pod Leaves |
|---|---|---|
| Kafka binder | Group membership and partition assignment | Rebalance, partition ownership shifts, reads from committed offsets |
| RabbitMQ binder | Consumers on same queue share deliveries; broker tracks acks | Unacked deliveries can be requeued/redelivered when channel/connection closes |
| Pulsar binder | Subscription name + type like Shared, Failover, Key_Shared | Unacked/redelivery, active consumer switch or key/subscription ownership shift |

### 11.1. RabbitMQ

Multiple consumers on the same queue receive deliveries based on broker scheduling and prefetch, without a Kafka-style group rebalance. During shutdown, delivered but unacked messages can be redelivered when the channel closes. If a handler completes side effects before acking, duplicates can still occur. Adding Pods does not form a Kafka-style consumer group; check queue name/group bindings, prefetch, ack mode, retries, and DLQs.

### 11.2. Pulsar

Pulsar `Shared` lets multiple consumers share a subscription and split messages without global message ordering. `Failover` promotes a standby consumer when the active consumer leaves. `Key_Shared` aims to keep messages with the same key on the same consumer, subject to redelivery/rebalance caveats by broker version. Do not equate Pulsar subscription names with Kafka groups or extrapolate Kafka-like partition assignment.

For both RabbitMQ and Pulsar, you still need drained shutdown windows, post-processing acks, idempotency, and monitoring of backlogs, errors, and DLQs.

## 12. Deploying New Versions with Backward Compatibility

During a rolling update, v1 and v2 may run concurrently for several minutes or longer. Check:

1. **Message schema:** v1 can read events produced by current producers; v2 handles older events still sitting in the Kafka log.
2. **Database schema:** Expand-first migrations so both v1 and v2 work; contract only after all v1 instances terminate.
3. **Headers, content types, and serialization:** Avoid sudden changes that cause v1 to fail deserialization.
4. **Event keys/partitioning:** Changing keys or partition counts can disrupt per-entity ordering.
5. **Retries/DLQ:** v2 errors must not silently divert messages onto unexpected paths without operator visibility.
6. **Idempotency:** Event IDs and dedupe keys stay consistent across both versions.
7. **External side effects:** Downstream endpoints tolerate both payload variants during the overlap window.

If a change cannot be backward compatible, a same-group rolling update may be unsuitable. Plan data/schema migrations, preserve backlogs, and execute controlled downtime.

## 13. Metrics to Monitor During Rollouts

Do not watch `kubectl rollout status` alone. A Kubernetes rollout marked successful can still leave consumer lag spiking.

| Signal | What to Observe |
|---|---|
| Kafka group state, member count | Whether the group is stable or churning |
| Assignment per topic/partition | Whether any partition goes unconsumed for a long period |
| Total and per-partition consumer lag | Whether backlog spikes briefly or keeps growing |
| Records consumed/second | Actual group processing throughput |
| Handler P95/P99 duration | Whether processing latency rises when v2 enters |
| Rebalance count/duration | Rebalance frequency and cost |
| Commit failures | Stale consumers committing late or after losing ownership |
| Retry/DLQ count | Errors appearing after schema or logic upgrades |
| Duplicate dedupe count | Rate of redelivered messages across Pod swaps |
| DB pool, CPU, memory | Whether surge overloads downstream systems |
| Pod restarts, readiness, termination reasons | Whether Pods are killed or restarted by health probes |

### 13.1. Inspection Commands

~~~bash
kubectl rollout status deployment/order-processor
kubectl get pods -l app=order-processor -o wide
kubectl describe deployment order-processor
kubectl logs deployment/order-processor --since=10m
~~~

Check the Kafka group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.org:9092 \
  --describe \
  --group order-processing

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.org:9092 \
  --describe \
  --group order-processing \
  --state
~~~

Kafka CLI tools, group protocols, and client versions may alter column layouts/options. Check `CURRENT-OFFSET`, `LOG-END-OFFSET`, `LAG`, and per-partition member assignments. Micrometer/Prometheus metrics complement CLI checks for historical tracking.

### 13.2. Alert Thresholds

Configure alerts around throughput and SLAs:

- Lag grows for several minutes after rollout stabilizes.
- Group lacks active consumers or continuously rebalances.
- Handler processing time exceeds thresholds before commit.
- Errors/retries/DLQ spike on v2.
- Pods hit `OOMKilled`, `CrashLoopBackOff`, or exceed termination grace.
- End-to-end event age breaches SLA.

Do not treat a brief lag blip during rebalancing as an incident if the system drains the backlog quickly. Conversely, low lag does not prove side effects weren't duplicated; check dedupe/error metrics too.

## 14. Testing Rolling Updates and Failure Injection

Before production, run tests in an environment with a real broker and production-like group, partition count, and concurrency settings:

| Scenario | Expectation to Verify |
|---|---|
| Deploy v1 with 3 Pods, upgrade one by one to v2 | Group operates, partitions reassign, zero lost events |
| v2 joins while v1 is still alive | Group assignment updates cleanly without two consumers owning one partition in stable assignment |
| SIGTERM on a Pod handling a long record | Handler finishes or event is reprocessed safely |
| Pod receives SIGKILL/OOM between side effect and offset commit | Duplicate is deduplicated without repeating side effects |
| Kafka coordinator disruption | Rebalance and recovery follow configured timeouts |
| v2 deserializes old events | No unintended poison records/DLQ spikes |
| More Pods than partitions | Extra Pods/consumers stay idle; do not mistake for scaled throughput |
| Rollback v2 to v1 | Schemas and DB migrations remain compatible; group offsets continue cleanly |
| Kafka Streams stateful rollout | Changelog restoration, task assignment, and state correctness |

### 14.1. Testing with Stable Event IDs

Emit a batch of events with unique IDs and check final business outcomes in the database or downstream sink:

- Every expected event produces a valid final outcome.
- Zero missing events after Pods are replaced.
- No side effects applied multiple times even if Kafka redelivers.
- Group offsets advance and lag drops after rollout.
- DLQ does not grow due to the new schema version.

The test binder is useful for function logic, yet it does not fully simulate consumer group coordinators, rebalancing, SIGTERM, or offset commits. Use integration tests with real Kafka/Testcontainers and test Kubernetes rollouts whenever deployment reliability is the target.

## 15. Operational Rollout Procedure

### Before Rollout

1. Check topic, partition count, group ID, and current consumer concurrency.
2. Verify committed offsets and lag prior to updating.
3. Verify schema/message, database, and external API compatibility between v1 and v2.
4. Measure P99 handler duration and pick a termination grace period with headroom.
5. Verify idempotency, retries/DLQ, and failure paths.
6. Ensure the cluster and downstream systems handle Pod/connection surges under `maxSurge`.
7. Prepare dashboards, alerts, runbooks, and rollback authorization.

### During Rollout

1. Start v2 according to chosen `maxSurge` and `maxUnavailable`.
2. Watch readiness and Kafka group membership/partition assignments.
3. As v1 Pods receive termination signals, monitor graceful shutdown/commit/leave.
4. Watch lag, processing duration, rebalances, and DLQ.
5. Pause the rollout if incompatibility, errors, or lag breach thresholds.
6. Proceed to the next replacement wave only after the system stabilizes.

### After Rollout

1. Confirm all Pods run the expected v2 image.
2. Group shows expected member count and assignments.
3. Lag returns to normal with no stalled partitions.
4. No abnormal errors or duplicate side effects appear.
5. Record rollout duration, rebalance count, peak lag, and verification results.
6. Adjust partitions/concurrency and shutdown budgets if SLOs were missed.

## 16. Troubleshooting and Rollback

| Symptom | Causes to Check | Action |
|---|---|---|
| Lag surges during rollout | Eager rebalance, slow v2 processing, insufficient capacity | Check assignments, pause rollout, compare rates |
| Partitions remain unassigned for long | Unexpired member session, static ID conflict, broken group | Inspect group state, timeouts, and coordinator logs |
| Duplicate message processing | Side effect succeeded before offset commit; Pod killed | Enable/strengthen idempotency, inspect ack mode |
| Consumers keep joining/leaving | Liveness restarts, OOM, overly short timeouts | Inspect Pod events, resource limits, heartbeats |
| `CommitFailedException` or rebalance errors | Member lost partition ownership or processed too slowly | Check max poll, handler duration, rebalancing |
| Pod Ready yet not consuming | Not yet assigned or no spare partitions | Check group assignment and partition count |
| Rollout stalled | Readiness failing, bad image, insufficient resources | Inspect Deployment conditions and Pod events |
| Rollback hits v1 schema errors | v2 emitted incompatible payloads/DB schema | Execute safe compatibility/roll-forward plan |

Operational commands:

~~~bash
kubectl rollout pause deployment/order-processor
kubectl rollout resume deployment/order-processor
kubectl rollout undo deployment/order-processor
~~~

Rollback restores the image/Pod template from Deployment history; it **does not revert Kafka committed offsets or database state**. If v2 already committed offsets or wrote new schemas, v1 must remain compatible with that state. Never manually reset offsets just to "undo" a deployment.

## 17. Common Misconceptions

1. **Changing group ID on v2 upgrade:** Creates a separate offset group; no longer a same-group rolling update.
2. **Believing Pod Ready means partitions are assigned:** HTTP readiness and Kafka assignment are separate signals.
3. **Treating `maxUnavailable=0` as zero downtime:** Only constrains Available Pod count; rebalances can still pause processing.
4. **Setting replicas above partition count:** Extra consumers/Pods do not increase group parallelism.
5. **Raising concurrency without measuring downstream:** Can overload DBs and increase rebalances/retries.
6. **Using the same static `group.instance.id` for all Pods:** Causes fencing; requires unique, stable IDs.
7. **Assuming cooperative assignor without checking effective config:** In classic protocol, RangeAssignor may still be selected.
8. **Using classic timeouts for `group.protocol=consumer`:** The new protocol manages heartbeats/sessions differently.
9. **Assuming SIGTERM guarantees messages committed:** Must verify listener stop, processing, and offset commits.
10. **Setting shutdown grace too short:** Pods receive SIGKILL while work or producer flushes remain unfinished.
11. **Committing offsets before side effects:** Risks losing business work if a Pod dies.
12. **Lacking idempotency:** Redelivered records trigger duplicate charges, updates, or emails.
13. **Calling `seekToBeginning` in a rebalance callback:** Can accidentally replay history.
14. **Failing liveness on broker disconnect:** Triggers a restart storm and extra rebalances.
15. **Treating RabbitMQ/Pulsar like Kafka groups:** Brokers have distinct assignment and acknowledgment mechanics.
16. **Assuming image rollback equals data rollback:** Offsets and DB state do not automatically rewind.

## Conclusion

Rolling updates of Spring Cloud Stream consumers in the same Kafka group gradually swap the members owning partitions. Kafka may rebalance as new members join or old members leave; cooperative assignment and the new protocol can reduce pauses under suitable conditions, yet they do not remove the need to handle redelivered messages.

A reliable design keeps `group` fixed, matches Pod count/concurrency to partition count, aligns RollingUpdate with graceful shutdown, avoids premature offset commits, and keeps side effects idempotent. Monitor group state, partition assignments, lag, rebalance durations, handler times, and errors throughout rollouts. Test SIGTERM, SIGKILL, schema compatibility, and rollbacks before declaring the strategy production-safe.

## References

- [Spring Cloud Stream — Partitioning with the Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/partitions.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — KafkaBindingRebalanceListener](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/rebalance_listener.html)
- [Spring Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Apache Kafka 4.4 — Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 — Group Configs](https://kafka.apache.org/44/configuration/group-configs/)
- [Kubernetes — Deployments / Rolling Update](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Apache Pulsar — Messaging and Subscription Types](https://pulsar.apache.org/docs/4.2.x/concepts-messaging/)
