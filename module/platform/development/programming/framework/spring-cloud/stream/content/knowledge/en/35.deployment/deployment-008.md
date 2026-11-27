# Autoscaling by Lag or Queue Depth

In an event-driven architecture, load is not reflected solely by application CPU usage. A Spring Cloud Stream consumer may use very little CPU because it is waiting on a database, while Kafka **consumer lag** or RabbitMQ/Pulsar **queue depth** still grows rapidly. Scaling replicas solely on CPU can prevent the system from processing events within business deadlines. **Event-driven autoscaling** adjusts the number of processing instances based on pending work volume while controlling maximum capacity and cost.

This lesson belongs to the **Deployment** chapter in the `SPRING_CLOUD_STREAM` module. Its scope covers Spring Cloud Stream applications using the `Supplier`/`Function`/`Consumer` functional model, bindings, and binders connecting to **Kafka, RabbitMQ, or Pulsar**. We will configure autoscaling with Kubernetes, HPA, and KEDA, calculate replica counts from backlogs, evaluate consumer groups/partitions/subscriptions, distinguish scale-to-zero from regular scale-down, and test under retries, DLQs, rebalancing, and broker disconnections.

## 1. Why Is CPU Not Enough to Decide Scaling?

Suppose service `order-projection` receives order events to update a database:

```text
Producer -> Broker -> Spring Cloud Stream Consumer -> Database
                |                  |
                |                  +-- CPU: 25%, waiting on slow DB
                +-- Backlog grows from 5,000 to 80,000 events
```

When the database slows down, consumers spend most of their time waiting on I/O. CPU below a 60% threshold does not trigger CPU autoscaling while data grows stale. A temporary spike at the producer can also create a backlog surge not yet visible in CPU. For message-processing consumers, lag/backlog is much closer to **unfinished work** than CPU, though CPU, memory, and latency are still needed to spot other bottlenecks.

A good autoscaler does not merely answer "how long is the queue?"—it must also consider **whether the queue is growing or shrinking**, **how fast each replica actually processes**, and **how far parallelism can scale**. Adding replicas will not speed up an already saturated database; on the contrary, scaling too aggressively can crash downstream systems under overload.

## 2. Terms to Distinguish

| Term | Meaning | Typical Measurement Source |
|---|---|---|
| Backlog | Number of unprocessed/unacknowledged messages at an observation point | Queue/broker/subscription |
| Consumer lag | Distance between latest offset and consumer group committed offset | Kafka group/topic/partition |
| Queue depth | Messages remaining in a queue; distinguish ready vs. unacknowledged | RabbitMQ management/queue API |
| Subscription backlog | Entries/messages not yet acknowledged by a subscription per Pulsar semantics | Pulsar Admin/metrics |
| Arrival rate \(\lambda\) | New messages arriving per second | Broker producer metrics |
| Processing rate \(\mu\) | Messages successfully processed per second per worker/replica | Consumer/application metrics |
| Drain time | Estimated time to clear backlog when total capacity exceeds arrival rate | Calculation or load test |
| Desired replicas | Replica count requested by the autoscaler from metrics and policy | HPA/KEDA |
| Ready replicas | Replicas genuinely ready to process after startup, binding, and health checks | Kubernetes Deployment |

These metrics are not identical. For example, Kafka lag is an offset distance, not an exact count of "business events" when transactions, log compaction, or filtered records exist. RabbitMQ distinguishes **ready** and **unacknowledged** messages; Pulsar backlogs are tracked per subscription and cursor. When setting thresholds, understand which metric the scaler reads and how it treats acks/redeliveries.

## 3. Kubernetes HPA and KEDA Architecture

Kubernetes **Horizontal Pod Autoscaler (HPA)** automatically adjusts Pod replicas based on metrics. HPA typically uses CPU/memory via Metrics Server; using broker backlogs requires external metrics provided by an adapter. **KEDA (Kubernetes Event-driven Autoscaling)** reads metrics from event sources and manages the corresponding HPA for the workload.

```text
             Kafka / RabbitMQ / Pulsar
                       |
                 broker metrics
                       |
                       v
                  KEDA Scaler
                       |
               ScaledObject + metrics
                       |
                       v
                Kubernetes HPA
                       |
                 desiredReplicas
                       |
                       v
             Spring Cloud Stream Deployment
                 Pod A / Pod B / Pod C
```

KEDA polls lag/backlog on a `pollingInterval` cadence. When a workload is active, HPA uses external metrics to decide replica counts on the HPA controller's cycle. KEDA also supports scaling from 0 replicas for triggers with suitable semantics and prerequisites. KEDA does not replace consumer group, subscription, or application error-handling configurations.

> **Version note:** YAML examples below illustrate common KEDA metadata. Field names, authentication modes, scale-to-zero support, and lag calculations may vary by KEDA/scaler version. Always check the CRDs and docs matching your target cluster and test against a real broker before applying production thresholds.

## 4. Preparing a Spring Cloud Stream Consumer with Stable Identity

To prevent autoscaling from turning into multiple independent applications receiving duplicate messages, each replica of the same workload must use a **consistent subscription/consumer group identifier**. With the Kafka Binder, set a fixed `group`; with Pulsar, use a stable subscription name; with Kafka Streams, instances of the same topology share `applicationId`.

Example order-processing consumer:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String eventId, String orderId, String status) {}

@Configuration(proxyBeanMethods = false)
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder(OrderService orderService) {
        return event -> orderService.applyIdempotently(event);
    }
}
```

In this example, `OrderService` is the application's business component; `applyIdempotently` must complete durable data updates or safely hand off work ownership **before the handler returns success**. If it merely submits the event to a thread pool and returns, the binder's ack/offset mechanism may mark the message done before actual work finishes.

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 1
```

This is the common binding section. You must add the corresponding binder dependency and broker configuration. The `concurrency` setting here illustrates the Kafka Binder or binders that support it; verify the exact meaning of `concurrency` per binder rather than assuming it behaves identically across Kafka, RabbitMQ, and Pulsar.

## 5. Deploying the Target Deployment to Scale

HPA/KEDA scales a declared Kubernetes workload, typically a `Deployment`. Condensed example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-projection
  namespace: event-processing
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-projection
  template:
    metadata:
      labels:
        app: order-projection
    spec:
      terminationGracePeriodSeconds: 90
      containers:
        - name: application
          image: registry.example.com/order-projection:1.0.0
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
```

The `definition`, `destination`, and `group` properties are declared in `application.yml` as in section 4, or supplied via a verified ConfigMap. Avoid guessing environment variable names from hyphenated binding keys with `-in-0` suffixes; verify the actual loaded binding configuration. In production, add appropriate readiness/liveness/startup probes, `securityContext`, service account, image pull secrets, and resource policies.

When KEDA manages replicas, do not also configure another independent HPA scaling the same `Deployment` with conflicting rules. KEDA typically creates/manages an HPA bound to the `ScaledObject`; two HPAs writing to the `scale` subresource can cause unpredictable replica oscillation.

## 6. Kafka Lag: Measuring by Consumer Group and Partition

Kafka stores records by partition. Lag for a consumer group is typically estimated as log end offset minus committed offset per partition, then summed. Because offsets are tied to a group, a consumer group that has **never committed an offset** may have no clear lag for the scaler. In that case, plan offset reset/initialization or group bootstrapping deliberately.

```text
Topic orders.events (4 partitions)

P0: end=12000, commit=10500 -> lag=1500
P1: end= 8800, commit= 8300 -> lag= 500
P2: end= 9300, commit= 8500 -> lag= 800
P3: end= 7000, commit= 6500 -> lag= 500
--------------------------------------------
Total lag (illustrative)          = 3300
```

When a consumer group processes a topic together, each partition is assigned to **one consumer in the group at a time**. Consequently, the number of actively working consumers on a topic cannot exceed its partition count, even if Kubernetes runs more Pods. A single Pod can host multiple consumer threads (`concurrency`), so the effective ceiling depends on total consumers, not just Pods.

If a consumer group processes multiple topics, decide whether to scale on total lag or a specific topic. A trigger watching only `orders.events` will miss backlog building up on `payments.events`. When using multiple triggers, understand how HPA aggregates replica recommendations and avoid double-counting correlated metrics that cause over-scaling.

## 7. KEDA Kafka ScaledObject — Basic Example

Suppose Kafka topic `orders.events` has 12 partitions, each Pod runs one Kafka consumer (`concurrency: 1`), and the group is `order-projection`:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-kafka
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 12
  triggers:
    - type: kafka
      metadata:
        bootstrapServers: kafka-bootstrap.messaging.svc:9092
        consumerGroup: order-projection
        topic: orders.events
        lagThreshold: "1000"
        activationLagThreshold: "10"
```

Meaning of parameters:

| Property | Meaning |
|---|---|
| `scaleTargetRef.name` | Deployment whose replicas are scaled up/down |
| `pollingInterval: 30` | KEDA checks trigger state roughly every 30 seconds |
| `cooldownPeriod: 300` | Wait period when KEDA handles scaling to 0 per activation rules; not the full HPA scale-down policy |
| `minReplicaCount: 1` | Always keep at least one Pod, avoiding bootstrapping the group from 0 |
| `maxReplicaCount: 12` | Never scale past 12 Pods under this autoscaling policy |
| `consumerGroup` | Must match the Spring Cloud Stream consumer's `group` |
| `topic` | Topic to measure lag on; must match actual `destination` |
| `lagThreshold: "1000"` | Target lag per replica in the scaler model |
| `activationLagThreshold: "10"` | Threshold activating the scaler from inactive state per KEDA semantics |

`lagThreshold` is **not** a command saying "when lag hits 1,000, add one Pod immediately." The scaler supplies the metric; HPA compares it against the target and current replicas to compute desired replicas. Actual scaling is further constrained by metric caching, HPA sync cycles, `minReplicaCount`, `maxReplicaCount`, partition caps, and stabilization policies.

This example assumes the Kafka broker is reachable from the KEDA operator. Production requires configuring TLS/SASL via `TriggerAuthentication`/`ClusterTriggerAuthentication` and Kubernetes Secrets; never put passwords in `ScaledObject` or Git.

## 8. Do Not Confuse Lag-Based Replica Math with Processing Efficiency

An approximate scaler model based on backlog is:

\[
R_{desired} \approx \left\lceil\frac{L}{L_{target\;per\;replica}}\right\rceil
\]

With total lag \(L=8,400\) and a target of 1,000 records/replica, raw math gives roughly 9 replicas before other limits apply. However, actual KEDA/HPA results may differ due to metric resolution, trigger activation, and partition caps. If the topic has only 6 partitions and each Pod has one consumer, only 6 Pods can hold partitions; adding a 7th Pod does not reduce lag faster.

Moreover, 1,000 records processed in one second is very different from 1,000 records taking one minute. The same backlog with heavy payloads, a slow database, or frequent retries requires a different replica count. Choose thresholds from **benchmarked successful throughput per second** and latency targets, not arbitrary round numbers.

## 9. Low Consumer Lag Does Not Mean the App Is Healthy

If a consumer continually reads records and commits offsets before durable side effects finish, Kafka lag can read 0 while real work still sits in thread pools or the database. The scaler will scale Pods down thinking the queue is empty, dropping in-flight work if proper draining is absent.

Design must guarantee:

1. Handlers do not signal success before business side effects reach a safe state.
2. Idempotency ensures crash redeliveries do not repeat side effects.
3. Dedicated metrics track processing errors, in-flight work, and end-to-end event age.
4. Probes and shutdown ensure Pods are not terminated while critical work remains.

With stateful Kafka Streams, throughput depends on task assignment, state stores, and state restoration. Temporary lag spikes during rebalancing/restoration do not necessarily mean too few Pods. Overly aggressive scaling during restoration can trigger further rebalances, pushing lag even higher.

## 10. Kafka Partition Caps and Concurrency

For a single topic with 8 partitions, the number of instances providing useful parallelism is bounded by partitions and concurrency:

| Replicas | Consumers/Pod | Total Consumers | Max Active Consumers with Partitions |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 |
| 2 | 1 | 2 | 2 |
| 4 | 2 | 8 | 8 |
| 8 | 2 | 16 | 8 |
| 12 | 2 | 24 | 8 |

When each Pod sets `concurrency: 2`, 8 consumers fit on 4 Pods, subject to assignment and resource balance. Scaling up to 12 Pods when the topic only has 8 partitions wastes resources without parallelizing any additional partitions.

The KEDA Kafka scaler offers options to cap scaling by partition count and idle consumers in supported versions; do not assume every configuration caps accurately across multiple topics and multi-threaded Pods. Set `maxReplicaCount` based on partition count **and** actual `concurrency`, and inspect consumer assignments after scaling.

## 11. RabbitMQ: Measuring Queue Depth on the Exact Consumer Group Queue

RabbitMQ does not use Kafka offset lag. The RabbitMQ Binder typically creates a **queue** for a `destination` and consumer `group`. Producers publish to an exchange; the binder/queue binding routes messages to the corresponding queue. The autoscaler must read **the exact queue** consumed by the application, not guess from exchange or function names.

```text
Producer -> exchange orders.events
                   |
                   v
         queue orders.events.order-projection
                   |
             consumers A, B, C
                   |
              Database
```

Under default naming conventions, the queue may be named `orders.events.order-projection`; the binder can alter naming rules via `prefix`, `queueNameGroupOnly`, partitioning, or topology settings. **Verify the actual queue name in the RabbitMQ Management UI/API** instead of copying examples blindly.

Important RabbitMQ metrics:

| Metric | What It Reflects | Autoscaling Caveats |
|---|---|---|
| `messages_ready` | Messages waiting to be delivered to consumers | Good for spotting queued waiting backlog |
| `messages_unacknowledged` | Messages delivered but not yet acked by consumers | Can grow when prefetch is high or processing slows |
| `messages` / queue total | Total ready and unacknowledged messages per API measurement | Know whether the scaler uses AMQP or HTTP and which metric |
| `publish_rate` | Incoming messages over time | Estimates backlog growth rate |
| `ack_rate` | Acknowledged messages over time | Estimates sustainable processing rate |
| `consumer_count` | Consumers attached to the queue | Does not mean all consumers are active |

Queue depth can grow because consumers are stalled, the DB is failing, broker flow control kicked in, or producers spiked. Adding Pods helps if consumer capacity is the bottleneck; if all Pods share an already saturated database, scaling out can worsen queue wait times due to DB connection contention.

## 12. RabbitMQ: KEDA ScaledObject by Queue Length

Example where the queue is provisioned by the RabbitMQ Binder and the app must retain at least one Pod:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-rabbitmq
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 10
  triggers:
    - type: rabbitmq
      metadata:
        hostFromEnv: RABBITMQ_URL
        queueName: orders.events.order-projection
        mode: QueueLength
        value: "100"
        activationValue: "5"
```

Here `value: "100"` targets roughly 100 queued messages per replica per RabbitMQ scaler metric semantics, **not** a broker queue length limit. `activationValue` is the activation threshold. Verify parameters for your running KEDA version.

`RABBITMQ_URL` must exist in the Deployment container because the scaler reads it via `hostFromEnv` in supported KEDA versions. Example injecting from a secret:

```yaml
env:
  - name: RABBITMQ_URL
    valueFrom:
      secretKeyRef:
        name: rabbitmq-consumer-credentials
        key: url
```

The secret key `url` here is a **reference**; never put URLs containing usernames/passwords into committed YAML files. Grant least-privilege metrics read access; KEDA can use `TriggerAuthentication` to access the broker via a separate mechanism, isolating scaler credentials from the runtime application. AMQP/HTTP Management API connection parameters, TLS, and vhosts depend on KEDA scaler mode and version, and must be tested against production-like broker configuration.

## 13. RabbitMQ: Prefetch and Consumer Count Must Be Measured Alongside Depth

The RabbitMQ Binder supports `prefetch`, `concurrency`, and other provisioning options. Example:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            concurrency: 2
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              prefetch: 20
```

`concurrency: 2` creates multiple consumers inside a Pod per binder/container support. `prefetch: 20` lets each consumer pull up to 20 unacked messages ahead of time; messages can move from `ready` to `unacknowledged` very quickly even while business processing stays slow. If the autoscaler watches only `ready`, it may scale down replicas before in-flight work finishes. Measure actual processing duration, prefetch, and both `ready` and `unacked` before selecting metrics/thresholds.

With **Single Active Consumer** queues, multiple consumers register while only one active consumer receives deliveries. Scaling from 1 to 10 Pods does not create 10 active consumers on the same queue; the extra Pods mostly sit on standby. To raise throughput while keeping per-key ordering, partition across multiple queues by key and autoscale or size capacity per queue (or have workers read multiple queues per policy). Do not enable queue-length autoscaling expecting SAC to become parallel processing.

If a queue uses TTL, DLX, or max-length policies, backlog changes are not solely driven by consumer acks. Messages may expire or get dead-lettered. An empty queue seen by a scaler does not prove messages succeeded; monitor rejects, retries, DLQs, and business ack rates.

## 14. Pulsar: Backlog Is a Per-Subscription Metric

Pulsar tracks message consumption state per **subscription cursor**. With a durable subscription, the broker stores the subscription's backlog; multiple consumers can join one subscription under `Shared`, `Key_Shared`, `Failover`, or `Exclusive` modes. The autoscaler must know the **full topic name** and **subscription name**, not just the consumer bean name.

```text
Topic: persistent://acme/orders/orders.events
                      |
                      +--> Subscription order-projection
                      |        backlog = 12,000 messages
                      |        Pod A / Pod B / Pod C
                      |
                      +--> Subscription audit-service
                               backlog = 80 messages
```

Two subscriptions maintain independent backlogs. If KEDA measures `audit-service` while scaling the `order-projection` Deployment, both systems behave incorrectly. Match the exact subscription name created by the Pulsar Binder from `group` or the corresponding binding/subscription property in your release.

Pulsar backlogs are also affected by ack mode, negative acknowledgment/redelivery, message TTL, DLQs, and retention. A subscription with high backlog cycling messages between a retry topic and DLQ requires investigation before scaling; autoscaling does not fix poison messages.

## 15. Pulsar: Illustrative KEDA ScaledObject

KEDA provides a Pulsar scaler driven by subscription backlog in supported versions. Common structure example:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: order-projection-pulsar
  namespace: event-processing
spec:
  scaleTargetRef:
    name: order-projection
  pollingInterval: 30
  cooldownPeriod: 300
  minReplicaCount: 1
  maxReplicaCount: 8
  triggers:
    - type: pulsar
      metadata:
        adminURL: http://pulsar-admin.messaging.svc:8080
        topic: persistent://acme/orders/orders.events
        subscription: order-projection
        msgBacklogThreshold: "1000"
        activationMsgBacklogThreshold: "10"
        isPartitionedTopic: "true"
```

**Verify version details carefully:** the Pulsar scaler may change metadata field names and backlog calculation rules for partitioned topics. `adminURL` above is an illustrative internal URL; production should use HTTPS with tokens/mTLS and `TriggerAuthentication` if needed. Never embed Kubernetes Secrets containing tokens directly in docs or manifests. Ensure the Admin API token has permission to read subscription stats without superuser privileges where narrower roles exist.

`msgBacklogThreshold` is the per-replica backlog target for the scaler; it is not the partition count. `isPartitionedTopic` must reflect actual topology; if wrong, the scaler may undercount or fail to locate metadata. Inspect actual topics/subscriptions with the Pulsar Admin API before trusting scaler numbers.

## 16. Pulsar Subscription Types Govern Scaling Limits

| Subscription | Behavior When Adding Consumers | Impact on Autoscaling |
|---|---|---|
| `Exclusive` | Only one consumer can subscribe per subscription | Scaling Pods does not parallelize consumption; extra Pods may fail to connect |
| `Failover` | Active/standby; on partitioned topics, active ownership distributes across partitions | Throughput depends on partition count and active assignment |
| `Shared` | Broker distributes messages across multiple consumers | Enables parallel scaling without global ordering guarantees |
| `Key_Shared` | Routes by key | Scales by key; requires key and batching aligned with semantics |

Autoscaling must keep `subscription` fixed across Pods. If each Pod creates its own subscription, each subscription receives a logical copy of the stream instead of sharing load, causing duplicate business output and misleading backlog metrics.

Even with some subscription types, adding consumers on partitioned topics may not scale linearly due to hot keys or active ownership limits. Therefore, pick `maxReplicaCount` after measuring **consumers actively receiving messages**, not solely from partition count.

## 17. Comparing All Three Metric Types Before Choosing a Scaler

| Aspect | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Observation point | Consumer group + topic + partition | Specific consumer group queue | Durable subscription + topic |
| Primary metric | Offset lag | Queue depth / ready / unacked | Subscription backlog |
| Parallelism unit | Partitions/consumer group | Consumers/queue, limited by SAC/exclusive | Subscription type, partitions/keys |
| Work completion | Offset commit | Message ack | Ack/cursor advancement |
| Failure tracking | Retries/DLQ/custom error handling | Nack/requeue/DLX/DLQ | Negative ack/redelivery/DLQ |
| Useless scaling cases | Out of partitions or hot partition | SAC/exclusive or saturated downstream | Exclusive/Failover limits or hot keys |
| Scale-to-zero | Group/offset metric must be readable at 0 Pods | Queue must pre-exist and be reachable by scaler | Durable subscription must exist with readable backlog |

Do not lump `lag = 1000`, `queue length = 1000`, and `Pulsar backlog = 1000` into one generic threshold and treat them as equivalent. Processing time, payload size, ack logic, and startup cost vary widely. Benchmark each stream to determine its own threshold.

## 18. Formula for Estimating Replicas from Target Drain Time

Assume arrival rate is \(\lambda\) messages/second, each replica sustainably completes \(\mu\) messages/second at steady state, current backlog is \(L\), and you want to clear the backlog within \(T\) seconds.

With \(R\) replicas, net backlog drain capacity is \(R\mu-\lambda\) when positive. Estimate:

\[
T_{drain}\approx\frac{L}{R\mu-\lambda}\quad\text{when }R\mu>\lambda
\]

To achieve \(T_{drain}\le T\), theoretical minimum replicas required:

\[
R\ge\left\lceil\frac{\lambda + L/T}{\mu}\right\rceil
\]

Example: backlog of 24,000 messages, producer still sending 600 messages/second, one Pod measured at 200 messages/second, target drain time 120 seconds:

\[
R\ge\left\lceil\frac{600+24000/120}{200}\right\rceil=4
\]

Four Pods provide \(4\times200-600=200\) messages/second of net drain capacity, taking roughly 120 seconds. Five Pods provide 400 messages/second net, draining in roughly 60 seconds with extra margin for variance. This is a **simplified estimate**: it ignores startup delay, rebalancing, retries, payload skew, network overhead, and broker/downstream limits; effective Pods are also capped by partitions/consumer assignments.

If \(R\mu\le\lambda\), backlog will never shrink even if the autoscaler holds \(R\). You must add valid capacity, optimize processing, throttle producers, or reduce downstream latency. Never set arbitrarily tiny thresholds to force HPA past partition or database limits.

## 19. Choosing Thresholds from SLOs Instead of Pretty Numbers

Steps to pick `lagThreshold`/`value`/`msgBacklogThreshold`:

1. Define an SLO: e.g., "95% of events processed within 60 seconds" or "drain 50,000 messages within 5 minutes after a burst."
2. Measure **successfully acked/committed** latency and throughput of a single Pod under realistic load.
3. Estimate allowable backlog within the SLO window given arrival rate and processing time.
4. Pick a per-Pod target backlog so the autoscaler scales out in time before breaching the SLO.
5. Cap `maxReplicaCount` within actual parallelism and sustainable downstream capacity.
6. Test bursts, broker glitches, and slow databases; measure scale-out and drain times.
7. Tune thresholds, polling, and stabilization/cooldown from observed results.

Little's Law \(L\approx\lambda W\) relates average items in the system, arrival rate, and residence time at steady state. It helps sanity-check thresholds, **not** guarantee per-message processing latency or predict a rapidly growing backlog.

## 20. Scale-to-Zero: Attractive, Yet Not Always Appropriate

KEDA can scale from 0 to positive replicas when supported and configured on the trigger. However, scale-to-zero is safe only when **the broker retains messages itself and the scaler can still observe backlog with zero consumers running**.

Setting `minReplicaCount: 0` requires answering:

- Does the Kafka consumer group already exist with committed offsets? How does the scaler treat new groups/offsets?
- Is the RabbitMQ queue pre-provisioned as durable, or does the application have to run to declare it?
- Does the Pulsar durable subscription already exist, or does it only appear once a consumer connects for the first time?
- What preserves topic/group/subscription metadata at 0 Pods?
- Is cold-start scaling from 0 fast enough to meet latency SLOs?
- Does startup require schema registry, databases, DNS, TLS, state restoration, or topic provisioning?
- If the metric endpoint errors at 0 Pods, is there a safe fallback?

**Starting recommendation:** for business pipelines requiring low latency, strict message ordering, stateful Kafka Streams, or unverified bootstrapping, keep `minReplicaCount: 1`. Drop to 0 only after thoroughly testing provisioning, metrics, warm-up, redelivery, and backlog persistence.

## 21. Scale-Down Requires Draining and Graceful Shutdown

When scaling Pods down, a consumer mid-message may receive SIGTERM. If the process exits before ack/commit or before database transactions finish, work may be redelivered. That is acceptable under at-least-once processing **if** handlers are idempotent and never mark completion prematurely.

Good sequence:

```text
KEDA/HPA lowers desired replicas
           |
           v
Kubernetes sends SIGTERM
           |
           v
App stops taking new work / closes consumers orderly
           |
           v
In-flight messages complete or roll back cleanly
           |
           v
Ack/commit durably processed messages
           |
           v
Consumers leave group/subscription, Pod exits
```

`terminationGracePeriodSeconds` must cover normal shutdown and reasonable in-flight work. With Spring Boot, configure web server graceful shutdown and lifecycle timeouts per your version; do not equate graceful HTTP shutdown with **all binder consumers having finished draining**. Inspect logs and test shutdown on your exact binder. Messages that cannot finish in time must be redelivered/retried safely.

Adding a `preStop` sleep of a few seconds does not automatically ensure messages are acked properly. If using `preStop`, give it a specific purpose (such as waiting for traffic routing to drain), rather than substituting it for idempotency and controlled consumer lifecycles.

## 22. Preventing Continuous Replica Oscillation (Flapping)

If backlog oscillates around the threshold, HPA can scale up and down repeatedly. Every Pod addition or removal changes consumer membership: Kafka may rebalance, Kafka Streams may restore state, and RabbitMQ/Pulsar may shift consumer/subscription assignments. These side effects temporarily lower throughput, pushing lag back up and triggering another scaling cycle.

Mitigations:

- Set the activation threshold distinct from the target threshold to avoid waking Pods for a few stray messages.
- Use a sufficiently long HPA scale-down stabilization window to avoid scaling down too fast.
- Rate-limit how many Pods can be added/removed per interval.
- Match `pollingInterval` to load change speed; polling too fast does not necessarily make HPA react instantaneously.
- Keep minimum replicas above 0 when startup, state restoration, or business latency is sensitive.
- Track rebalance/consumer restart counts and processing pause durations.

KEDA supports passing HPA behavior configuration via `advanced.horizontalPodAutoscalerConfig` in supported versions. Example snippet inside a `ScaledObject` `spec`:

```yaml
advanced:
  horizontalPodAutoscalerConfig:
    behavior:
      scaleUp:
        stabilizationWindowSeconds: 0
        policies:
          - type: Percent
            value: 100
            periodSeconds: 60
      scaleDown:
        stabilizationWindowSeconds: 300
        policies:
          - type: Pods
            value: 1
            periodSeconds: 60
```

These illustrative values permit relatively fast scale-up while scaling down one Pod at a time after roughly a 5-minute stabilization window. Check your KEDA CRD manifest and the actual generated HPA behavior after deployment. KEDA's `cooldownPeriod` and HPA's `stabilizationWindowSeconds` govern different scopes; do not treat them as two names for the same setting.

## 23. Combining Backlog and CPU/Memory: Choose Triggers Intentionally

A workload can be constrained by either CPU or lag. KEDA allows multiple triggers; HPA computes desired replicas per metric and generally picks the highest recommendation among valid metrics. Example adding a CPU trigger to an existing Kafka lag `ScaledObject`:

```yaml
triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka-bootstrap.messaging.svc:9092
      consumerGroup: order-projection
      topic: orders.events
      lagThreshold: "1000"
  - type: cpu
    metricType: Utilization
    metadata:
      value: "70"
```

This is an illustrative `spec.triggers` snippet, not a standalone Kubernetes resource. Some KEDA CPU scaler versions use `metadata.type: Utilization` instead of `metricType`; check the scaler schema for your release, and CPU utilization requires Pods to specify `resources.requests.cpu`. If CPU metrics cannot be verified, start with the lag trigger alone and enable the CPU trigger after integration tests pass.

Scaling on both CPU and lag suits CPU-heavy transforms; however, if downstream is a saturated database, combining CPU and lag may drive scaling beyond DB capacity. Set grounded `maxReplicaCount`, connection-pool limits, and rate limits. When memory rises from a leak, adding Pods does not fix the root cause; autoscaling is no substitute for fixing memory leaks or heap sizing.

## 24. Securing Metrics Access from KEDA

KEDA must connect to brokers or monitoring APIs to read backlogs. This access belongs to the **control plane**, distinct from runtime consumer credentials.

| Component | Recommended Least Privilege | What Not to Grant |
|---|---|---|
| KEDA Kafka scaler | Read topic/consumer group offsets and relevant metadata | Cluster admin rights unless required |
| KEDA RabbitMQ scaler | Read queue/vhost stats or minimal AMQP access needed | Root account across all vhosts |
| KEDA Pulsar scaler | Access topic/subscription stats via Admin API per broker policy | Shared superuser token across all scalers |
| Spring Cloud Stream consumer | Consume from inputs and publish/ack/retry per business needs | Full broker administrative privileges |
| Kubernetes workload | Read secrets/ConfigMaps in its own namespace | Cluster-wide Secret read access |

Use Kubernetes Secrets or a secret manager with KEDA `TriggerAuthentication` to bind credentials per `ScaledObject`. Example referencing a separately created authentication object:

```yaml
triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka-bootstrap.messaging.svc:9093
      consumerGroup: order-projection
      topic: orders.events
      lagThreshold: "1000"
    authenticationRef:
      name: order-kafka-metrics-auth
```

This is a **reference**; the `TriggerAuthentication` itself must configure SASL/TLS/OAuth compatible with the specific broker and scaler. Never commit literal passwords, tokens, or certificate private keys in Git. Restrict `NetworkPolicy` so KEDA reaches only required endpoints; for the RabbitMQ Management API or Pulsar Admin API, always enforce TLS over untrusted networks.

A scaler that fails to fetch metrics cannot scale out, or HPA lacks data to decide. Alert on KEDA metric/authentication errors rather than mistaking a "silent autoscaler" for an empty queue.

## 25. Checking Status After Applying ScaledObject

After installing KEDA and creating the `ScaledObject` in the appropriate namespace, inspect state with Kubernetes commands:

```bash
kubectl -n event-processing get scaledobjects
kubectl -n event-processing describe scaledobject order-projection-kafka
kubectl -n event-processing get hpa
kubectl -n event-processing describe hpa
kubectl -n event-processing get deployment order-projection
kubectl -n event-processing get pods -l app=order-projection
```

Checklist of observations:

1. Does `ScaledObject` show healthy ready/active conditions?
2. Did KEDA create an HPA targeting the right `Deployment`?
3. Can HPA read current and target metric values?
4. Do desired replicas increase when lag/backlog grows?
5. Do new Pods become `Ready` and establish actual consumer subscriptions?
6. Does message processing/ack rate increase accordingly?
7. When load drops, do Pods scale down cleanly after stabilization and graceful shutdown?

Never conclude autoscaling succeeded merely because `desiredReplicas` increased. If Pods stay `Pending`, `CrashLoopBackOff`, or `NotReady`, effective processing capacity has not grown. Investigate image pulls, CPU quotas, node capacity, secrets, broker auth, schema mismatches, database connections, and startup times.

## 26. Readiness, Liveness, and Startup When New Pods Appear

Actuator exposes Spring Boot health endpoints once dependencies and exposure settings are configured. Example:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Illustrative Kubernetes probes when Actuator listens on HTTP port 8080:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  failureThreshold: 30
  periodSeconds: 5
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
```

For consumers without an HTTP server, add a web starter or choose another appropriate probe. These probes only report application status via Spring Boot health groups; `Readiness=UP` does not automatically prove a consumer received partitions or is ready to process. If a workload must wait for Kafka Streams state restoration or broker connection before being considered capable, build an appropriate signal and measure readiness latency.

**Do not blindly put broker availability into liveness.** During a shared broker outage, restarting all Pods simultaneously makes matters worse. For readiness, evaluate carefully before adding binder health: a broker outage can mark all Pods unready, impacting service routing and availability even when applications self-reconnect.

## 27. Stateful Kafka Streams: Scaling Too Often Can Slow Things Down

The Kafka Streams Binder uses tasks, threads, and state stores; new instances often must restore state from changelogs before processing tasks. When scaling out:

```text
Increase replicas
   -> rebalance tasks
   -> move active/standby tasks
   -> restore state stores if needed
   -> resume processing
```

During restoration, lag may keep rising, prompting the autoscaler to add even more Pods. Adding more causes extra task migrations and network/disk I/O. To prevent a feedback loop, set `minReplicaCount` to fit baseline load, use conservative scale-up policies, configure scale-down stabilization, and benchmark restore duration against real state sizes.

For a `StatefulSet` or topologies relying on local state placement, verify KEDA/HPA `scaleTargetRef` supports the target workload properly and ensure each replica has its own state directory. Do not vary `applicationId` by Pod name; replicas must participate in the same logical Kafka Streams application. Standby tasks speed up recovery, yet do not count as extra active processing capacity.

## 28. Backpressure: When Downstream Cannot Speed Up

Suppose a database handles at most 1,200 operations/second. Each Pod can push 400 operations/second in an isolated benchmark, yet running 10 Pods cannot drive 4,000 operations/second without saturating the database.

```text
Broker backlog grows
      |
      v
KEDA scales Pods from 3 -> 10
      |
      v
DB connection pool exhausted / timeouts rise
      |
      v
Retries surge -> backlog grows even faster
```

Protective measures:

- Cap `maxReplicaCount` to what downstream can sustain.
- Size per-Pod connection pools with a bounded total (`pool size × replicas`).
- Limit consumer `concurrency` or `prefetch` when processing slows down.
- Apply circuit breakers/rate limiters, backoff, and jitter appropriately.
- Separate transient errors from poison messages to avoid retry storms.
- Enforce broker/network/CPU/memory quotas within allowed capacity.
- Monitor downstream p95/p99 latency, timeouts, and saturation alongside backlog.

When upstream produces data faster than total **sustainable** downstream capacity, scaling consumers alone will never catch up. You may need to throttle producers, tier queues, scale database capacity, or revise SLOs. Autoscaling must be part of capacity planning, not a band-aid hiding system limits.

## 29. How Do Retries and DLQs Affect Trigger Metrics?

Continuously failing messages can inflate backlogs even while adding replicas fails to raise successful throughput. For example, a consumer hits deserialization errors, retries each message three times, and then dead-letters it. If bad messages make up 50% of traffic, adding Pods simply produces more exceptions and DLQ volume, adding extra broker load.

| Symptom | Metrics to Inspect | Action |
|---|---|---|
| High lag, low error rate, high CPU | CPU, processing rate, lag slope | Can add replicas if partitions and downstream capacity remain |
| High lag, high error rate | Retries/exceptions/DLQ, error classes | Fix schema/code/data; do not scale indefinitely |
| Low queue ready, high unacked | Consumer processing duration, prefetch | Check for stuck handlers, slow DB, or excessive prefetch |
| High Pulsar backlog, heavy redeliveries | Redeliveries, negative acks, subscription | Check timeouts/poison messages and subscription type |
| Low lag yet high end-to-end latency | In-flight count, processing duration, external work | Avoid premature acks; measure business completion time |
| Lag rises due to prolonged rebalancing | Rebalances, restore rate, active threads | Reduce scaling churn; inspect state restoration |

With RabbitMQ DLQs, the dead-letter queue is typically a separate queue. Never accidentally point the main worker scaler at the DLQ, or misconfigure scaling on unconsumed error messages. DLQs need dedicated investigation and replay workflows; a separate DLQ processor can have its own controlled autoscaling if designed intentionally.

## 30. End-to-End Observability and Alerting

Autoscaling can reach desired replicas and still miss SLOs. Production dashboards should combine:

- Current lag/backlog and **slope** (rising or falling per minute).
- Arrival rate, successful ack/commit rate, and error/retry rate.
- Age of oldest event / end-to-end processing latency.
- Desired, current, available, and ready replicas.
- KEDA scaler errors, HPA metric fetch failures, and time from trigger to Pod Ready.
- Partition assignments, consumer membership, rebalance counts, and Kafka Streams restore times.
- CPU, memory, heap/GC, per-Pod concurrency, and connection pool usage.
- RabbitMQ ready/unacked, Pulsar subscription backlog/redeliveries.
- DLQ backlog and messages stalled behind ordering gaps.
- Quotas, node autoscaler latency, and `Pending` Pod count.

Alert when lag rises continuously while replicas are pinned at `maxReplicaCount`, when replicas increase without processing rate rising, or when the scaler fails to fetch metrics. These signal **capacity limits**, **downstream failures**, or **measurement issues** requiring human intervention.

## 31. Autoscaling Test Matrix

| Scenario | How to Execute | What to Observe |
|---|---|---|
| Idle load | Send no messages; `minReplicaCount:1` | One replica stays active without flapping |
| Sudden burst | Send a burst of 50,000 events | Replicas scale per metric; end-to-end latency stays within bounds |
| Moderate load | Send steady traffic near target threshold | Replicas stay stable without scaling up/down every cycle |
| Producer outpaces capacity | Drive \(\lambda\) above processing rate | Backlog grows predictably and triggers alerts |
| Fewer partitions than max Pods | Kafka 4 partitions, set `maxReplicaCount` 12 | Extra consumers do not activate extra partitions |
| RabbitMQ SAC | Two or more Pods on same SAC queue | Only one active consumer; throughput does not scale linearly |
| Pulsar Shared/Key_Shared | Multiple Pods sharing subscription | Proper assignment and processing per ordering contract |
| Bad broker auth | Set invalid credentials for scaler | Scaler/metric errors reported; never silently treated as empty queue |
| Slow database | Inject DB latency or lower connection limit | Backlog and timeouts rise; autoscaler does not crush DB |
| Poison messages | Emit repeated failing payloads | DLQ/retries work; no runaway scale storm |
| Pod killed | Kill a Pod with in-flight work | Safe redelivery with no duplicate side effects |
| Scale-down | Drain backlog back to 0 | Pods drain cleanly without losing messages before ack |
| Scale-to-zero | Scale to 0 Pods on supported trigger | Subscription/queue persists; new messages wake Deployment |
| Kafka Streams restore | Restart instance with large state | Measure rebalance/restore; no pointless scale loops |

These tests require a Kubernetes environment with KEDA/HPA and real brokers or an equivalent integration setup. `spring-cloud-stream-test-binder` verifies function logic, yet **does not** simulate consumer group lag, RabbitMQ queue depth, Pulsar subscription backlogs, or Kubernetes autoscaling loops.

## 32. Practical Walkthrough: From One Pod to Six Pods

Suppose the system has a 12-partition Kafka topic `orders.events`, one group `order-projection`, and one consumer thread per Pod. During testing, the producer emits 400 events/second and each Pod sustainably processes 150 events/second without saturating the database. Initial backlog is 18,000 messages. Target: drain the backlog within at most 120 seconds.

Initial calculation:

\[
R\ge\left\lceil\frac{400+18000/120}{150}\right\rceil
=\left\lceil3.67\right\rceil=4
\]

Four Pods provide \(4\times150-400=200\) messages/second of net drain capacity, estimating 90 seconds to drain (excluding startup). Six Pods provide 500 messages/second net, draining in roughly 36 seconds if the DB holds up. With 12 partitions, partition assignment allows six concurrent active consumers. However, if the DB starts slowing past four Pods, six Pods may not run faster; verify on dashboards.

Practice procedure:

1. Run the Deployment at one Pod, verifying the group commits offsets properly without premature acks.
2. Apply a `ScaledObject` with `minReplicaCount:1`, `maxReplicaCount:6`, and benchmark-backed target lag.
3. Send a burst and measure time for KEDA to detect it, HPA to raise desired replicas, and new Pods to become Ready.
4. Inspect `kubectl get hpa`, `describe scaledobject`, and group partition assignments.
5. Measure successful commits/second, database latency, and backlog slope.
6. Intentionally fail one Pod and verify redelivery causes zero duplicate side effects.
7. Drop traffic and verify scale-down never interrupts in-flight tasks.
8. Repeat with a throttled database and poison messages to validate real limits.

If the app uses `concurrency: 2` per Pod, recalculate total consumer threads vs. partition count rather than treating Pod count as worker count. When moving to stateful Kafka Streams, factor in restore/changelog overhead rather than reusing stateless benchmarks.

## 33. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| KEDA reads wrong consumer group | Scales based on another app's lag | Match `consumerGroup` to runtime `group` |
| KEDA RabbitMQ reads exchange name instead of queue | Fails to read true queue depth | Verify physical queue name on broker |
| KEDA Pulsar reads wrong subscription | Backlog metric mismatches workload | Verify durable subscription name |
| Group/subscription varies by Pod name | Each Pod gets its own stream copy, causing duplicates | Use a stable ID for one logical app |
| Max replicas exceeds useful parallelism | Wastes resources and increases rebalancing | Cap by partitions/tasks/queues and concurrency |
| Measuring only `ready` queue count | Ignores unacked backlog from prefetch | Monitor ready, unacked, and processing duration |
| Running SAC/Exclusive and scaling dozens of Pods | Extra Pods do not improve throughput | Change topology/subscription after reviewing ordering needs |
| Scale-to-zero before queue/subscription exists | Cannot measure backlog to wake workers | Pre-provision resources and verify scaler works from 0 |
| Embedding secrets directly in `ScaledObject` | Credential leakage | Use Secrets and `TriggerAuthentication` |
| Missing resource requests | HPA CPU metrics missing or inaccurate | Declare appropriate CPU/memory requests |
| Scaling Pods down as soon as lag hits 0 | In-flight messages interrupted | Graceful shutdown, idempotency, stabilization |
| Lag grows due to poison messages | Autoscaler fuels retry storms | Fix data/schema errors; use DLQs/rate limits |
| Independent HPA scales the same Deployment | Replica contention and oscillation | Keep one autoscaling controller per scale target |
| Missing broker metrics on disconnect | Scaler stalls or reports metric unknown | Alert on scaler errors, credentials, and networking |
| Confusing desired with ready replicas | Assuming capacity grew while Pods sit Pending | Monitor startup, readiness, quotas, and node capacity |

## 34. Production Operations Checklist

- [ ] Confirm workload is truly an event consumer; never scale on unrelated producer backlogs.
- [ ] Configure stable group/subscription/application IDs across all replicas.
- [ ] Verify broker metrics measure the exact topic, queue, or subscription.
- [ ] Define SLOs for message age, drain time, and end-to-end latency.
- [ ] Benchmark sustainable per-Pod processing rate including retries and downstream latency.
- [ ] Set `minReplicaCount` and `maxReplicaCount` aligned with partitions, ordering, and downstream capacity.
- [ ] Distinguish `pollingInterval`, KEDA cooldown, and HPA stabilization.
- [ ] Configure separate secrets/TLS/auth for scaler metrics vs. runtime clients.
- [ ] Configure appropriate liveness/readiness/startup probes without triggering broker-outage restart storms.
- [ ] Handlers are idempotent and ack/commit only after work is safe.
- [ ] Graceful shutdown and termination grace period tested during scale-down.
- [ ] Scale-to-zero tested if planned; queues/groups/subscriptions remain readable at 0 Pods.
- [ ] Dashboards cover lag, ready/unacked, backlog, processing rate, scaler errors, and Pod Ready state.
- [ ] Alerts fire when replicas hit max while lag still rises or when metrics go missing.
- [ ] Tested bursts, poison messages, broker outages, DB saturation, and rebalancing.

## 35. Self-Check Questions

1. Why does low CPU not prove a consumer is keeping up with incoming message rates?
2. Which offsets define Kafka consumer lag, and how do they relate to consumer groups?
3. How many consumers in the same group can a four-partition Kafka topic usefully utilize on a single simple input topic?
4. How does KEDA's `lagThreshold` differ from a per-message processing latency target?
5. Why must RabbitMQ distinguish between `messages_ready` and `messages_unacknowledged`?
6. Why do 10 replicas reading a RabbitMQ Single Active Consumer queue not process 10x faster?
7. With Pulsar, should the scaler measure backlog on the topic or on a specific subscription?
8. What can go wrong when scaling to 0 before a Kafka group commits offsets or a Pulsar subscription is created?
9. Why can adding Pods sometimes worsen lag on stateful Kafka Streams applications?
10. When backlog is 20,000, arrival rate is 200 messages/second, and one Pod processes 100 messages/second, what is the minimum number of Pods needed for backlog to **decrease**?
11. Why must HPA scale-down coordinate with graceful shutdown and idempotency?
12. What alerts should fire when replicas hit their ceiling yet backlog continues growing?

## Conclusion

Autoscaling Spring Cloud Stream by event volume responds much more accurately to real load than CPU alone. With **Kafka**, set thresholds on consumer group lag and respect partition/concurrency limits. With **RabbitMQ**, measure the consumer group's exact queue and understand ready/unacknowledged counts, prefetch, and Single Active Consumer behavior. With **Pulsar**, measure the durable subscription backlog and pick an appropriate subscription type. **KEDA** bridges broker metrics to **Kubernetes HPA**, yet it cannot fix broken consumers, slow databases, poison messages, or bad replays on its own. Derive thresholds from SLOs and throughput benchmarks, cap replicas by downstream capacity, secure scaler credentials, test scale-to-zero, graceful shutdown, and rebalancing, and monitor lag/backlog alongside processing rates so autoscaling stays both responsive and safe.

## References

- Spring Cloud Stream — Reference Documentation: https://docs.spring.io/spring-cloud-stream/reference/
- Spring Cloud Stream — Kafka Binder consumer properties: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html
- Spring Cloud Stream — RabbitMQ Binder consumer properties: https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html
- Spring Cloud Stream — Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Kubernetes — Horizontal Pod Autoscaling: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- KEDA — ScaledObject Specification: https://keda.sh/docs/latest/concepts/scaling-deployments/
- KEDA — Apache Kafka Scaler: https://keda.sh/docs/latest/scalers/apache-kafka/
- KEDA — RabbitMQ Queue Scaler: https://keda.sh/docs/latest/scalers/rabbitmq-queue/
- KEDA — Apache Pulsar Scaler: https://keda.sh/docs/latest/scalers/apache-pulsar/
- RabbitMQ — Queue Monitoring: https://www.rabbitmq.com/docs/monitoring
- Apache Pulsar — Subscriptions and Messaging: https://pulsar.apache.org/docs/4.0.x/concepts-messaging/
