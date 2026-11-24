# Canary Consumer Instances in Spring Kafka: Step-by-Step Rollout and Risk Control

## 1. Problem and Goal

A Spring Kafka service is running steadily with three replicas, all consuming topic `orders.events`. The development team has updated order-processing logic and wants to roll out the new version to production without replacing every active consumer at once. The typical answer is deploying a **canary consumer instance**: running a small number of instances on the new version, observing real behavior, and then expanding.

For HTTP services, a canary usually shifts a percentage of requests via ingress or a service mesh. **Kafka consumers do not work like HTTP load balancing.** Within a single consumer group, Kafka distributes **partition ownership**—it does not route "1% of messages" according to an arbitrary canary ratio. Adding a new consumer to the group can trigger a rebalance and move ownership of one or more partitions from stable instances to the canary.

This is the essential starting point for **"Canary Consumer Instances,"** in the **Deployment and Configuration** chapter of **Spring Kafka Reliability Operations**.

After this lesson, you will know how to:

1. Distinguish a canary in the **same live-processing group** from an **independent shadow-group** canary.
2. Choose between approaches based on business safety, side effects, and observability needs.
3. Configure a Spring Kafka consumer with the same group ID, tune concurrency, and tag revisions.
4. Deploy separate stable and canary Deployments in Kubernetes.
5. Observe partition assignments, consumer lag, retries, DLT, business errors, and latency before scaling up.
6. Apply idempotency, versioning rules, and offset-commit boundaries to avoid incorrect results during rebalances.
7. Design promotion criteria, rollbacks, crash handling, and practical pre-deploy tests.
8. Explain why a canary receiving zero partitions **is not** proof the new version is safe.

Examples use Java 17+, Spring Boot 3.x, Spring Kafka 3.x, Apache Kafka, and Kubernetes. Exact APIs, partition assignment strategies, and consumer group behavior must be verified against your Kafka client, broker, and group protocol versions.

## 2. Consumer Canaries Differ from HTTP Canaries

Canary deployment means rolling out a new version with a **controlled blast radius**, gathering quality signals, and deciding whether to expand or roll back.

With HTTP:

```text
                  HTTP ingress
                      |
                 routing 95/5
                 /          \
           stable 95%     canary 5%
```

With Kafka consumers sharing a group:

```text
Topic orders.events
  partitions: P0 P1 P2 P3 P4 P5
                  |
                  v
       Group: orders-processors
                  |
         Kafka group coordinator
             /             \
        Stable pods      Canary pod
          v1               v2
       P0 P1 P2 P3       P4 P5
```

This diagram illustrates one possible assignment. **There is no guarantee Kafka assigns P4–P5 to the canary or splits evenly by message volume.** Partition assignment depends on member counts, subscriptions, assignors, and group state.

Implications:

- A canary can receive 0 partitions if consumers outnumber partitions.
- A canary can receive a very "hot" partition carrying most of the system's events.
- Any given partition is owned by at most one consumer in a stable group; stable and canary do not both process each record.
- When a canary joins or leaves the group, rebalances, brief pauses, and redeliveries around offset commits can occur.
- Because the canary processes live data, bugs in it can directly corrupt production state.

**Same-group canaries are not a mechanism for slicing exactly 1%, 5%, or 10% of events.** If business requirements demand strict percentage routing by business key, build explicit topic/partition/routing pipelines or isolated event streams and prove correctness rather than relying on replica counts.

## 3. Two Canary Models to Distinguish

### 3.1. Same-Group Canary: Live Production Processing

Stable and canary share `group.id=orders-processors`:

```text
               Topic orders.events
                       |
              Consumer group G
                /           \
           Stable v1       Canary v2
         live handling   live handling
                \           /
                  Business DB
```

The canary owns a subset of partitions and **is responsible for live processing** of their records.

Strengths:

- Tests the real processing flow, offset commits, retries, and target systems.
- Exercises realistic production load without re-reading the entire topic.
- Gradual promotion to the new revision works simply by shifting replica counts.

Risks:

- Buggy canary code can write bad data or push records to the DLT.
- No fine-grained control over message percentages.
- Rebalances can briefly raise lag or cause redeliveries.
- If the canary gets zero partitions, the test has zero coverage.
- Traffic on assigned partitions may not represent all event types or key distributions.

### 3.2. Shadow Canary: Separate Consumer Group, No Side Effects

The canary registers a **distinct group ID**, such as `orders-processors-shadow-v2`:

```text
                  Topic orders.events
                    /           \
                   v             v
        Group orders-processors  Group orders-shadow-v2
            Stable v1               Canary v2
          live handling         validation/metrics
               |                    |
           Business DB         No real DB writes,
                               no real events emitted
```

Two independent groups can both read all partitions of the same topic. The shadow canary runs parsers, validators, or dry-run logic under controlled observation while **applying zero changes to production systems**.

Strengths:

- Safer when logic changes carry high risk of corrupting data.
- Observes broad message variety without competing with the stable group.
- Leaves stable group offsets untouched.
- Can compare results using an isolated test-result store.

Limitations:

- Adds extra fetch requests and CPU load on brokers.
- If the shadow group starts from `earliest`, it can pull huge retained volumes.
- Does not verify live production side effects of the new version.
- Code must genuinely suppress **all** side effects: DB writes, HTTP calls, emails, Kafka publishes, production DLTs, etc.
- Shadow group offsets are separate and cannot track stable group progress.

### Model Selection Matrix

| Requirement | Same-Group Live Processing | Independent Shadow Group |
| --- | --- | --- |
| Test production offset-commit paths | Fits well | Not fully representative |
| Guarantee zero business data writes | No, unless separate safeguards exist | Fits if code is genuinely read-only |
| Avoid rebalancing the stable group | No | Avoids altering stable group membership |
| Inspect all message types for validation | Not guaranteed | Can observe the whole topic within chosen offsets |
| Extra Kafka read cost | Minimal, partitions are split | Adds an independent consuming group |
| Measure production writer performance | Yes | No, if side effects are disabled |
| Blast radius on parser/validator bug | Affects partitions owned by canary | Normally isolated to shadow group |
| Stepwise rollout to new version | More direct | Run shadow first, then move to same-group canary |

**A common safe progression:** run shadow first to verify parsing, validation, and compatibility; then launch a same-group canary for end-to-end verification with idempotency, guardrails, and rollback ready. Not every system needs both stages.

## 4. Same-Group Canary Does Not Mean "One Replica = Fixed Traffic Share"

Suppose a topic has 12 partitions, stable runs 3 consumer threads, and canary runs 1 consumer thread:

```text
Total consumers in group = 4
Total topic partitions   = 12
Average                 = 3 partitions/member
```

If partitions carry equal volume and the assignor splits evenly, the canary gets ~25% of partitions. That still does not equal 25% of **messages**, **CPU**, **revenue**, or **business risk**.

Skewed traffic example:

| Partition | Messages/sec |
| --- | ---: |
| P0 | 50 |
| P1 | 60 |
| P2 | 40 |
| P3 | 1,500 |
| P4 | 50 |
| P5 | 70 |

If the canary is assigned P3, it processes the majority of traffic while owning only one partition. Therefore, monitor **per-partition message rates and business key distributions**, not just partition counts.

In groups with more consumers than partitions, the canary may receive 0 partitions. In that state, `pod Ready` and `Kafka listener running` do not prove the new code processed a single record.

### Need Exact Rollout Percentages?

Consider dedicated designs such as:

- Routing a curated set of business keys to a test topic via a controlled producer/router.
- Mirroring a subset of events for a canary with isolated side effects.
- Sharding data/workloads by designated tenants or key ranges.

Each option changes architecture and can affect ordering, idempotency, or event distribution. Never manually assign a partition to a canary while the same group subscribes to that topic without explicit ownership design, because manual assignment and group subscription are separate coordination models.

## 5. Prerequisites Before Deployment

Before deploying a new consumer revision to production, verify:

1. **Topic and schema:** the new version can read both existing retained events and newly produced events.
2. **Business effects:** writers enforce idempotency keys and versioning rules to prevent duplicates or out-of-order regressions.
3. **Offset strategy:** auto-commit, container ack mode, manual ack, or Kafka transactions? Which commit boundaries are protected?
4. **Error recovery:** retry policy, backoff, DLT, and rules for which records may be skipped.
5. **Group protocol:** assignor, cooperative/eager rebalance, static membership, and compatibility with the stable version.
6. **Observability:** dashboards and alerts distinguish stable vs. canary via release/pod labels.
7. **Rollback:** old image remains runnable; clear procedure to stop canary and return partitions to stable.
8. **Security:** canary holds required Kafka/DB rights and no excess privileges.
9. **Capacity:** brokers, DBs, connection pools, and consumer threads have headroom for rebalances.
10. **Rollout evidence:** visibility into which partitions the canary owns and how many events produced verified outcomes.

Define measurable goals upfront—for example, "canary processed at least 10,000 unique events covering target event types, error rate/lag stayed within thresholds, zero duplicate writes occurred, and no abnormal DLT spikes appeared." These numbers are **illustrative thresholds**, not universal defaults.

## 6. Base Configuration for a Spring Kafka Consumer

Suppose the app reads order events from `orders.events`. Core `application.yml` settings:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${APP_KAFKA_GROUP_ID:orders-processors}
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      max-poll-records: 200
    listener:
      ack-mode: record
      concurrency: 1

app:
  kafka:
    orders:
      topic: ${APP_KAFKA_TOPIC:orders.events}
  release:
    track: ${APP_RELEASE_TRACK:stable}
    version: ${APP_RELEASE_VERSION:unknown}
```

Explanation:

- `group-id`: determines whether instances share a group or run as an isolated shadow group.
- `enable-auto-commit=false`: delegates offset management to the Spring Kafka listener container per ack mode.
- `ack-mode: record`: commits progress per record under container lifecycle rules; with synchronous handlers returning normally, the container records the record as processed.
- `concurrency: 1`: one consumer thread per application instance in this example; increasing concurrency adds members and alters partition distribution.
- `max-poll-records`: controls batch size per poll and processing time; it does not set canary traffic share.
- `auto-offset-reset: earliest`: applies only when a group/partition lacks valid committed offsets; does not rewind an active stable group.
- `track`/`version`: release metadata for logs, traces, and dashboards, not built-in Kafka group properties.

In production, configure SSL/SASL, secrets, topic authorization, retries, and error handlers per infrastructure standards. Never commit Kafka passwords in Git YAML.

**Note on shadow groups:** a new group with `earliest` can consume all retained history, creating unexpected load. To inspect only fresh events, set `latest` before the group has offsets and start the consumer prior to emitting test traffic—while understanding events produced before assignment completes may be missed.

## 7. Live-Processing Listener with `@KafkaListener`

A consumer sharing the group can be implemented as:

```java
package com.example.orders.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventConsumer.class);

    private final ObjectMapper mapper;
    private final OrderEventService service;
    private final String releaseTrack;
    private final String releaseVersion;

    public OrderEventConsumer(
            ObjectMapper mapper,
            OrderEventService service,
            @Value("${app.release.track}") String releaseTrack,
            @Value("${app.release.version}") String releaseVersion) {

        this.mapper = mapper;
        this.service = service;
        this.releaseTrack = releaseTrack;
        this.releaseVersion = releaseVersion;
    }

    @KafkaListener(
        id = "orders-processor",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void onMessage(ConsumerRecord<String, String> record)
            throws Exception {

        OrderEvent event =
            mapper.readValue(record.value(), OrderEvent.class);

        service.apply(event);

        log.info(
            "event=order.consumed releaseTrack={} version={} " +
            "partition={} offset={} eventId={}",
            releaseTrack,
            releaseVersion,
            record.partition(),
            record.offset(),
            event.eventId()
        );
    }
}
```

Illustrative event model:

```java
package com.example.orders.kafka;

public record OrderEvent(
    String eventId,
    String orderId,
    long version,
    String status
) {}
```

Key points:

- Stable and canary replicas can share **the same listener code and group ID** while running different image versions.
- `id="orders-processor"` is the per-application-instance container ID; each pod does not need a distinct KafkaListener ID since each pod runs its own JVM/context.
- Release metadata is logged to separate canary activity from stable.
- The handler never catches exceptions and returns success silently. On failure, let the container error handler apply retry/recovery policies.
- Logging one `INFO` line per event is illustrative only; at high volume, switch to aggregated metrics or sampling to save CPU/I/O.
- Never log raw payloads, tokens, sensitive data, or PII.

### Sharing a Group Means Sharing Offsets

Stable and canary sharing `group.id` share the group's committed offsets per topic-partition. When a partition moves from stable to canary, the canary resumes from the group's committed offset rather than replaying from the beginning via `auto-offset-reset`.

Conversely, a separate shadow group keeps its own committed offsets. **Never switch a production consumer's group ID to roll back or bypass errors**, as that changes work distribution and read positions simultaneously.

## 8. Idempotent Business Handlers Limit Canary Blast Radius

During rebalances, crashes, or failed offset commits, Kafka can redeliver records already processed by the business service. Under at-least-once processing, the canary must handle redeliveries safely.

PostgreSQL example with two tables:

```sql
CREATE TABLE processed_order_event (
    consumer_projection VARCHAR(80) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_projection, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(120) PRIMARY KEY,
    last_version BIGINT NOT NULL,
    current_status VARCHAR(40) NOT NULL
);
```

Service:

```java
package com.example.orders.kafka;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderEventService {

    private final JdbcTemplate jdbc;

    public OrderEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {

        int inserted = jdbc.update(
            """
            INSERT INTO processed_order_event (
                consumer_projection, event_id
            ) VALUES ('orders-main', ?)
            ON CONFLICT (consumer_projection, event_id)
            DO NOTHING
            """,
            event.eventId()
        );

        if (inserted == 0) {
            // Event was already recorded previously.
            return;
        }

        jdbc.update(
            """
            INSERT INTO order_projection (
                order_id, last_version, current_status
            ) VALUES (?, ?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET
                last_version = EXCLUDED.last_version,
                current_status = EXCLUDED.current_status
            WHERE order_projection.last_version
                < EXCLUDED.last_version
            """,
            event.orderId(),
            event.version(),
            event.status()
        );
    }
}
```

This assumes `JdbcTemplate` uses a datasource managed by the app's transaction manager. Marker and projection updates share **the same database transaction**. If the process crashes before commit, both roll back; if redelivered after DB commit yet before Kafka offset commit, the marker suppresses duplicate updates.

`last_version` guards against older event versions overwriting newer state. It does not automatically enforce gap detection or strict sequential ordering if business rules forbid skipping versions—add explicit gap-detection and recovery rules when needed.

**Important:** Database transactions and Kafka offset commits do not share a distributed transaction by default. A redelivery window always remains; idempotent design protects final state. Kafka transactions can support Kafka-to-Kafka exactly-once semantics where applicable, yet do not turn external databases or APIs into exactly-once automatically.

## 9. Rebalances When a Canary Joins the Group

When a same-group canary starts:

```text
Stable A, B, C reading partitions
                 |
            Canary D joins
                 |
                 v
       Group membership changes
                 |
                 v
       Partition assignment updates
                 |
            +----+----+
            |         |
          Stable     Canary
     keep reading   receives partitions
```

Depending on protocol and assignor, Kafka uses eager or cooperative rebalancing. With cooperative assignment, not all partitions need to be revoked; only reassigned partitions change owners.

Operational practices:

- Track which partitions are revoked and assigned to the canary.
- Tune timeouts and handler durations so consumers keep polling within bounds.
- Never block rebalance callbacks with slow network calls or unbounded locks.
- Verify records completed before/after revocation under your ack/transaction policy.
- Monitor duplicate business effects, retries, and committed offsets.

### Configuring the Assignor (Where Applicable)

In environments using compatible client group protocols/assignment, you can configure `CooperativeStickyAssignor`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Never change the assignor solely on the canary assuming the whole group switches automatically. Members must share compatible configs; migrating from eager to cooperative assignment may require a phased upgrade depending on client and protocol versions.

In Kafka releases using new broker-side consumer group protocol assignment, assignment properties behave differently. Verify the active group protocol before changing settings.

## 10. Configuring Stable and Canary Deployments in Kubernetes

One same-group deployment pattern runs a stable Deployment alongside a separate canary Deployment with distinct replica counts, images, and release labels.

Abbreviated stable Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer-stable
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-consumer
      track: stable
  template:
    metadata:
      labels:
        app: order-consumer
        track: stable
    spec:
      containers:
        - name: consumer
          image: registry.example.com/order-consumer:1.8.0
          env:
            - name: SPRING_KAFKA_BOOTSTRAP_SERVERS
              value: "kafka-bootstrap:9092"
            - name: APP_KAFKA_GROUP_ID
              value: "orders-processors"
            - name: APP_RELEASE_TRACK
              value: "stable"
            - name: APP_RELEASE_VERSION
              value: "1.8.0"
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              memory: "768Mi"
```

Canary Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer-canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-consumer
      track: canary
  template:
    metadata:
      labels:
        app: order-consumer
        track: canary
    spec:
      containers:
        - name: consumer
          image: registry.example.com/order-consumer:1.9.0
          env:
            - name: SPRING_KAFKA_BOOTSTRAP_SERVERS
              value: "kafka-bootstrap:9092"
            - name: APP_KAFKA_GROUP_ID
              value: "orders-processors"
            - name: APP_RELEASE_TRACK
              value: "canary"
            - name: APP_RELEASE_VERSION
              value: "1.9.0"
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              memory: "768Mi"
```

This assumes the image and Kafka bootstrap service exist and TLS/credentials are supplied via Secrets or cluster mechanisms. This is a minimal topology illustration, **not a complete production manifest**: add security contexts, health probes, termination grace periods, service accounts, topology spread constraints, and applicable policies.

### Key Characteristics

- **Shared `group.id`:** stable and canary compete for partition ownership and commit to the same group offset set.
- **Distinct `track`/`version` labels:** enable separate monitoring, log filtering, and targeted pod selection on rollback.
- **No Service/Ingress needed for Kafka traffic:** consumers connect outbound to brokers directly.
- **One canary pod does not guarantee one consumer member** if `concurrency > 1` or multiple listeners share the group.
- **`replicas: 1`** caps initial canary process count, not a fixed event ratio.
- If stable uses HPA or an autoscaler, account for total consumer threads in the group so the canary still receives enough traffic to observe.

For production, pin images by digest or verified provenance so rollbacks pull the exact tested artifact.

## 11. Consumer Concurrency and Topic Capacity

In Spring Kafka, `ConcurrentKafkaListenerContainerFactory.setConcurrency(n)` (or its YAML property) spawns multiple consumer threads.

Suppose:

```text
Stable: 3 pods × concurrency 2 = 6 consumers
Canary: 1 pod × concurrency 2 = 2 consumers
Topic:  6 partitions
```

Eight members compete for six partitions. Some consumers will receive zero assignments. A canary processing zero records may simply reflect topology rather than broken canary code.

Investigation steps:

1. Verify the `group.id` of every member.
2. Count actual partitions and total consumer threads.
3. Read live partition assignments, not just `kubectl get pods`.
4. Check events/sec actually processed by the canary.
5. If stronger coverage is needed, test on a topic with enough partitions or use a shadow group.

**Never raise concurrency just to "make the canary get more traffic"** without weighing rebalances, DB load, ordering, and partition counts. Kafka assigns per partition, never splitting one partition across multiple consumers in the same group.

## 12. Shadow Canary: Separate Group and Read-Only Handling

To dry-run without writing production data, deploy with a dedicated group:

```yaml
env:
  - name: APP_KAFKA_GROUP_ID
    value: "orders-processors-shadow-v2"
  - name: APP_CONSUMER_MODE
    value: "shadow"
  - name: SPRING_KAFKA_CONSUMER_AUTO_OFFSET_RESET
    value: "latest"
  - name: APP_RELEASE_TRACK
    value: "shadow"
  - name: APP_RELEASE_VERSION
    value: "1.9.0"
```

For a fresh group, `latest` starts from the log tail when no committed offsets exist. However, it **does not guarantee reading events produced before assignment finishes**. To test a specific corpus, anchor timestamps/offsets or manage a dedicated test group and offset reset.

### Protecting Against Side Effects in Code

A clean pattern uses a separate listener bean for shadow mode without injecting production business writers:

```java
package com.example.orders.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    name = "app.consumer.mode",
    havingValue = "shadow"
)
public class ShadowOrderConsumer {

    private static final Logger log =
        LoggerFactory.getLogger(ShadowOrderConsumer.class);

    private final ObjectMapper mapper;
    private final ShadowOrderValidator validator;

    public ShadowOrderConsumer(
            ObjectMapper mapper,
            ShadowOrderValidator validator) {
        this.mapper = mapper;
        this.validator = validator;
    }

    @KafkaListener(
        id = "orders-shadow",
        topics = "${app.kafka.orders.topic}",
        groupId = "${spring.kafka.consumer.group-id}"
    )
    public void validate(ConsumerRecord<String, String> record)
            throws Exception {

        OrderEvent event =
            mapper.readValue(record.value(), OrderEvent.class);

        validator.validateWithoutSideEffects(event);

        log.debug(
            "event=orders.shadow.validated partition={} offset={}",
            record.partition(), record.offset()
        );
    }
}
```

The validator service can check schemas, classify events, compute dry-run projections, or emit metrics; **it must never call repositories updating live data, emit live events, or write to the production DLT by default**.

When the app also includes the live `OrderEventConsumer` from earlier, gate the live listener with a complementary condition:

```java
@Component
@ConditionalOnProperty(
    name = "app.consumer.mode",
    havingValue = "active",
    matchIfMissing = true
)
public class OrderEventConsumer {
    // Active listener implementation as shown earlier.
}
```

In real configs, only one listener activates per mode, preventing shadow pods from accidentally starting side-effecting consumers via other auto-configs.

### Never Rely Solely on `if` Flags to Guard Side Effects

A branch like:

```java
if (shadowMode) {
    return;
}
businessService.apply(event);
```

is easily bypassed if an earlier helper writes state or if `@RetryableTopic`/DLT publishers trigger side effects. For sensitive systems, enforce **separate bean wiring**, read-only credentials, sandbox databases, or Kafka ACLs granting `READ` only on the source topic.

A new shadow group adds broker read load and deserialization CPU; still cap throughput and monitor its lag separately.

## 13. Schema/Event Compatibility When Two Versions Run Concurrently

When stable v1 and canary v2 share a group, producers still emit events under a shared schema. Both consumer versions coexist for minutes or longer, requiring **bidirectional runtime compatibility**, not just the canary understanding new events.

Example:

```json
{
  "eventId": "evt-912",
  "orderId": "ord-42",
  "version": 7,
  "status": "PAID",
  "currency": "VND"
}
```

If v2 requires `currency` while retained older events omit it, the canary can fail when assigned a partition holding older records. If v2 writes new columns or formats to the shared database, stable v1 may fail to read or overwrite new fields.

Check before rollout:

- The new consumer reads all retained events, including optional/unknown fields.
- The old consumer keeps working alongside new producers or consumers.
- Database migrations stay compatible with both active versions.
- Data written by v2 does not break v1 if a partition moves back.
- Event keys, partitioning logic, serializers, and group/offset policies stay unchanged unless intentionally migrated.

A canary reading a subset of events cannot replace full corpus schema compatibility testing. Where coverage is thin, run shadow/replay checks against sanitized data or representative fixtures.

## 14. Observing Partition Assignments to Confirm the Canary Is Actually Working

At least three distinct states exist:

1. Kubernetes created the canary Pod and marked it ready.
2. The Spring Kafka listener container started and joined the group.
3. The consumer actually **received partition assignments and is processing records**.

Only the third state proves the canary is receiving real workload.

With `@KafkaListener`, inspect the container via `KafkaListenerEndpointRegistry`:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ConsumerAssignmentInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerAssignmentInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isListenerRunning() {
        MessageListenerContainer container =
            registry.getListenerContainer("orders-processor");

        return container != null && container.isRunning();
    }
}
```

This checks listener state only, **not** whether partitions are assigned. On `ConcurrentMessageListenerContainer`, inspect `getAssignedPartitions()` where supported, or monitor rebalance events and Kafka client metrics.

A rebalance listener can be attached to the container factory:

```java
import java.util.Collection;

import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;

public class CanaryRebalanceObserver
        implements ConsumerAwareRebalanceListener {

    private static final Logger log =
        LoggerFactory.getLogger(CanaryRebalanceObserver.class);

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info(
            "event=kafka.assigned partitions={}",
            partitions
        );
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        log.info(
            "event=kafka.revoked partitions={}",
            partitions
        );
    }
}
```

Register the observer via `ConcurrentKafkaListenerContainerFactory.getContainerProperties().setConsumerRebalanceListener(...)`.

Notes:

- Never store assignments in a singleton field assuming every callback belongs to one member; multiple consumer threads may run.
- Callbacks behave differently under eager vs. cooperative rebalances or partition loss.
- When reading assignment metrics from Kafka/`AdminClient`, distinguish a group mid-rebalance from a stabilized group.
- Callback logs never replace verified processed-event counts and accurate business data.

## 15. Metrics to Watch While the Canary Runs

The goal is not merely "zero exceptions." You must know whether the canary actually receives traffic and handles it safely.

| Group | Example Signals | Interpretation |
| --- | --- | --- |
| **Exposure** | Partitions owned by canary; events/sec; unique events | Confirms canary receives representative data |
| **Liveness** | Consumer running, assignments, poll timestamps, offset progress | Catches stuck canaries even while pod stays alive |
| **Latency** | p50/p95/p99 processing duration, queue time | Tracks SLA impact |
| **Errors** | Parse errors, business exceptions, retry rate, DLT rate | Separates transient errors from terminal failures |
| **Lag** | Consumer lag by group/topic/partition | Catches canaries falling behind |
| **Rebalances** | Rebalance count, handoff duration, revoked/lost partitions | Assesses rollout stability |
| **Business correctness** | Duplicate suppressions, invalid transitions, reconciliation mismatches | Catches corrupt writes even when jobs/consumers "succeed" |
| **Resources** | CPU, heap, GC, threads, DB pool utilization | Catches performance regressions and saturation |
| **Downstream** | DB latency, HTTP errors, outbound Kafka send failures | Separates handler bugs from target-system outages |

Attach `service`, `releaseVersion`, `releaseTrack`, `groupId`, and topic labels where cardinality permits. Never put `eventId`, `orderId`, or high-churn consumer instance IDs onto time-series metric labels arbitrarily.

**Be careful comparing stable vs. canary:** both sets of pods may own partitions with very different traffic volume and event mixes. Comparing "canary had 20 errors vs. stable had 100" means nothing without normalizing by event volume, event type, complexity, and key distribution.

For shadow groups, lag and read rates are independent of the stable group. Never mistake shadow lag for a production group backlog.

## 16. Choosing Quality Gates for the Observation Phase

An illustrative gate suite:

| Gate | Illustrative Condition | If Not Met |
| --- | --- | --- |
| Exposure | Canary processed at least 10,000 unique events with representative traffic | Continue observing; do not promote |
| Assignment | Canary owns at least one suitable partition or has verified shadow coverage | Investigate topology |
| Processing errors | Normalized canary error rate does not exceed baseline | Halt expansion / roll back |
| DLT | No abnormal surge in business-critical DLT records | Block rollout |
| Lag | Lag does not grow continuously and recovers post-rebalance within SLA | Throttle / roll back |
| Latency | p95 latency stays within the defined SLA budget | Block rollout |
| Duplicate effects | Zero duplicate side effects in reconciliation checks | Roll back and audit data |
| Schema | Zero new parse errors on target event types | Roll back / fix compatibility |
| Resources | CPU, heap, and connection pools retain headroom | Reduce concurrency, optimize |
| Stability | No abnormal rebalance loops triggered by canary | Inspect config/timeouts |

Thresholds like 10,000 events or specific p95 targets must fit your system. For low-volume topics, supplement with test corpora or shadow/replays rather than promoting after a few quiet minutes.

A 30-minute observation window with **0 events on the canary** proves nothing about code quality. Exposure gates must require actual message volume and business coverage, not just elapsed wall-clock time.

### Classifying Incidents

- **Canary has no assignment:** insufficient data to judge, not yet a business bug.
- **Canary has assignments yet lag grows:** slow processing, stalled polls, retry loops, or DB contention.
- **Canary parse errors:** suspect schema compatibility or partition-specific payloads.
- **Canary sends heavily to DLT:** recovery policy or business rules shifted; check for lost business outcomes.
- **Stable hits the same error:** likely a shared outage rather than a canary-specific regression.
- **Canary wrote bad data:** rolling back the image does not undo committed writes; run compensation/reconciliation.

## 17. Phased Rollout Plan

An operational rollout plan can follow these phases:

### Phase 0 — Preflight

- Test schema compatibility and read/write compatibility with the stable version.
- Test handlers against edge-case fixtures, duplicate events, and replays.
- Verify commit/retry/DLT policies.
- Confirm metrics, logs, and dashboard sources.
- Prepare rollback images and data-remediation procedures.
- Verify group ID, static membership IDs (if used), ACLs, and partition counts.

### Phase 1 — Shadow (When Needed)

- Start a shadow consumer with its own group ID and side effects disabled.
- Verify real event parsing, deserialization, and validation.
- Record observed event counts, type coverage, and errors.
- Never compare shadow latency to a live production writer if the shadow skips writes.

### Phase 2 — Single Same-Group Canary

- Launch one canary pod on the new version sharing the stable group ID.
- Wait for rebalancing to settle; inspect canary partition assignments.
- Check exposure: confirm real events are processing and inspect event types.
- Compare business outputs and errors against the baseline.
- Never expand rollout if the group rebalances continuously, the canary receives no work, or traffic is unrepresentative.

### Phase 3 — Evidence-Based Expansion

Scale new-version consumers gradually—e.g., 1 → 2 → more instances—while scaling down the stable deployment. Each membership shift can trigger a rebalance. **Replica ratio is not message ratio**, so base decisions on live traffic metrics.

At each step, re-verify gates for the expanded scope. If the topic has fewer partitions than total members, adding replicas may not increase exposure.

### Phase 4 — Complete the Rollout

- Replace the stable version with the new version per deployment policy.
- Confirm the group holds all partitions and total lag recovers.
- Keep comparison dashboards open post-rollout to catch load-dependent regressions.
- Tear down shadow consumers once unneeded, managing offsets/group metadata per policy.

Even a promoted rollout needs observation; performance regressions sometimes surface only once 100% of partitions move to the new version.

## 18. Rolling Back a Same-Group Canary

If a severe defect appears:

1. **Halt expansion** and record active versions and blast radius.
2. **Stop the canary deployment** or scale canary replicas to 0 per operational procedure.
3. Wait for group rebalancing and confirm stable instances reclaim all partitions.
4. Watch lag, retries, DLT, and error rates after ownership shifts back.
5. Reconcile data written by the canary; if corrupt, apply compensation or controlled reprocessing.
6. Log an audit trail covering rollback triggers and root cause.

Example Kubernetes command:

```bash
kubectl scale deployment/order-consumer-canary \
  --replicas=0 \
  --namespace=production
```

Illustrative command; verify permissions, namespace, and cluster before executing.

**Never reset Kafka committed offsets back to the topic start on rollback.** A canary may already have legitimately processed and committed thousands of events. An unplanned offset reset feeds them back to stable; if handlers lack idempotency, side effects duplicate. Offset resets/replays require dedicated workflows verifying downstream state and replay safety.

### Code Rollback Is Not Data Rollback

If the canary wrote columns or states the old stable version cannot parse, stable instances may keep failing after the canary stops. Follow expand-and-contract patterns for schema/database changes, or roll back to a data-compatible version. Never run destructive migrations while two consumer versions coexist.

## 19. Shutdown and Kubernetes Readiness

Consumers need a clean window to close resources when pods stop. In Kubernetes, termination sends `SIGTERM` and waits before `SIGKILL`. Spring Kafka containers stop listeners, finish in-flight work per policy, and leave the consumer group cleanly.

Ensure:

- `terminationGracePeriodSeconds` covers completing an in-flight record/chunk.
- Handler HTTP/DB timeouts and retries are bounded.
- Poll threads never block indefinitely.
- Application shutdown hooks genuinely stop listener containers.
- Rebalance callbacks execute quickly.
- Rolling updates do not terminate too many stable members simultaneously.

Pod spec addition example:

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: consumer
      image: registry.example.com/order-consumer:1.9.0
      # Fill env/resources attributes completely as in the manifest.
```

A green readiness probe confirms your custom health checks passed—**it does not prove the consumer owns partitions or processed events**. Conversely, making "must own at least one partition" a readiness requirement can trap legitimate standby consumers in permanent not-ready states. Weigh that carefully against your topology.

In Kubernetes Deployments, use startup/liveness/readiness probes for process health, while relying on **Kafka-specific gates** for canary promotion.

## 20. Static Membership and `group.instance.id`

Kafka supports static membership under compatible configs/protocols via a stable `group.instance.id` per logical member. It can reduce rebalances during brief restarts of the same instance when configured correctly.

Dangerous mistake:

```yaml
spring:
  kafka:
    consumer:
      properties:
        group.instance.id: "orders-consumer"
```

If multiple pods share that value in one group, the coordinator can fence/evict members from the group. Never assign a single static membership ID across all stable and canary pods.

One approach keeps **dynamic membership** during initial rollouts. If static membership is used, IDs must be unique and stable per logical instance—matching StatefulSets or platforms providing stable pod identities—and accounting for `KafkaListener` concurrency and container member-ID suffixing.

Static membership does not eliminate the need to test rebalances and crashes; in some cases, losing a member takes longer to time out before partitions reassign.

## 21. Error Handlers, Retries, and DLT in Canaries

Canaries are often the first place new schema or business-logic errors surface. Agree on retry and DLT policies before rollout.

| Scenario | With Same-Group Canary | What to Decide |
| --- | --- | --- |
| Transient DB errors | Partition may slow down during retries | Retry limits, backoff, timeouts |
| Parse exceptions | May fail before reaching listener method | Error handler / deserialization strategy |
| Non-retryable business error | May route to DLT or stop processing | DLT policy, skip rules |
| Record sent to DLT and source committed | Stable will not automatically re-pick up recovered/committed records | Is DLT evidence and triage sufficient? |
| Crash before offset commit | May redeliver after rebalance | Side-effect idempotency |
| Async retry topics | Can alter end-to-end ordering | Versioning/ordering constraints |

**Do not ship major business-logic changes alongside major retry/DLT policy changes** when evaluating a canary regression. Changing too many variables obscures root cause and can cause unexpected commits or skips.

In shadow mode, audit every recoverer and DLT publisher: a shadow consumer must never accidentally push live messages to the production DLT or trigger side-effecting alert workflows.

### Never Equate "Zero Errors" with Success

If an error handler catches exceptions and recovers records to the DLT, the listener group keeps running and Kafka lag drops—yet the business operation **still failed**. Canary gates must track DLT/recovery outcomes alongside business reconciliation, not just application exception counts.

## 22. Pre-Deployment Testing with Embedded Kafka

With `spring-kafka-test`, you can create a multi-partition topic and run two consumer containers in one group to verify canary topology.

Example Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.awaitility:awaitility'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Test flow model:

```text
Embedded Kafka: topic "orders.canary.test", 6 partitions
Group: "orders-canary-test-group"

Start stable A
    |
    v
Wait until A owns 6 partitions
    |
    v
Start canary B, same group
    |
    v
Wait until assignment stable:
    union(partitions A,B) = all 6 partitions
    intersection(A,B) = empty
    canary B owns >= 1 partition
    |
    v
Publish event corpus
    |
    v
Check all event IDs handled;
check canary handled at least one;
check business results and retries
    |
    v
Stop B
    |
    v
Wait A owns all partitions again
```

Example assertion using Awaitility and container APIs:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        Set<TopicPartition> stableParts =
            Set.copyOf(stable.getAssignedPartitions());

        Set<TopicPartition> canaryParts =
            Set.copyOf(canary.getAssignedPartitions());

        assertFalse(canaryParts.isEmpty());

        Set<TopicPartition> all =
            new HashSet<>(stableParts);

        all.addAll(canaryParts);

        assertEquals(6, all.size());
        assertTrue(
            Collections.disjoint(stableParts, canaryParts)
        );
    });
```

This assumes `stable` and `canary` are started `ConcurrentMessageListenerContainer`s returning non-null assignments. In complete tests, convert `null` to an empty set before calling `Set.copyOf()` and isolate group IDs/topics per test. Never assert that the canary owns one specific partition number: assignments are decided by the group coordinator and assignor.

**This tests basic rebalancing and exposure, not full production canary readiness.** Add assertions for data processing, DLT, offsets, and transactions whenever handlers have side effects.

## 23. Testing Shadow Mode Without Writing Real Data

Another integration test uses **two consumer groups**:

```text
Group stable-test: reads test topic -> test business DB
Group shadow-test: reads test topic -> validation metrics only
```

The test can:

1. Create a test topic with several partitions and a representative event corpus.
2. Start independent stable and shadow consumer groups.
3. Wait until both groups receive partition assignments.
4. Publish N events with unique `eventId`s.
5. Assert stable produced N accurate business results.
6. Assert shadow validated N events while **creating zero extra business output**.
7. Inject a parse/validation error in shadow; verify stable keeps processing unaffected.
8. Confirm both groups manage committed offsets independently.

If shadow uses `auto.offset.reset=latest`, start and await assignment before publishing the test corpus; publishing before the group establishes a read position can skip events.

For sensitive side effects, give shadow read-only DB credentials or omit write permissions entirely. Tests can then prove even an accidental code call to write is blocked by infrastructure.

## 24. Testing Crashes, Rollbacks, and Duplicate Data

Embedded brokers combined with graceful `container.stop()` do not fully simulate hard process crashes. To evaluate real at-least-once guarantees, run independent tests:

```text
Test Kafka broker
        |
   Consumer canary process
        |
        +-- business DB commits event X
        |
        X process killed before Kafka offset commit
        |
        v
Stable consumer takes over partition
        |
        v
X may be redelivered
        |
        v
Idempotent handler detects X already processed
```

The test must control exactly where the fault occurs; killing at a random instant may hit after an offset commit and trigger zero replays.

A thorough suite verifies:

- Partition sets before/after crash and takeover time.
- Group committed offsets prior to crash.
- Event X is reprocessed if committed offsets hadn't passed X.
- Final business tables/side effects contain zero duplicates.
- Any records routed to the DLT are tracked and triaged.
- Rolling back to the old version leaves data schemas compatible.

Use Testcontainers, separate-process apps, network fault injection, or staging/chaos tests as appropriate. Never kill consumers or mutate offsets on a production broker solely for testing.

## 25. Analyzing Failed Rollout Scenarios

### 25.1. Canary Is Ready Yet Processes Zero Events

**Symptom:** Pod is green with zero errors, yet event rate metric stays at 0.

**Possible causes:** members outnumber partitions, assignor granted no partitions, wrong group ID, listener unsubscribed, or empty topic.

**Response:** check assignments, group, topic, and broker metadata; do not promote. To test parsing on a corpus, run a shadow group with controlled offsets/corpus.

### 25.2. Canary Receives Far More Traffic Than Expected

**Symptom:** one canary pod handles nearly as much volume as all stable pods combined.

**Possible causes:** key skew, hot partitions, or concurrency/assignment settings differing from expectations.

**Response:** inspect per-partition message rates, apply app-level rate limits where needed, shrink scope, or switch canary models. Never rely solely on replica ratios.

### 25.3. Lag Spikes Immediately When Canary Joins

**Symptom:** group lag climbs and logs show repeated `revoked`/`assigned` events.

**Possible causes:** prolonged rebalances, slow record processing, retry loops, missed heartbeats/polls, or DB bottlenecks.

**Response:** inspect rebalance duration, `max.poll.interval.ms`, handler latency, error handlers, and DB metrics; roll back if recovery misses SLAs.

### 25.4. Canary Emits High DLT Volume

**Symptom:** canary does not crash and offsets advance, yet business outputs are missing.

**Possible causes:** parser bugs, overly aggressive recover/skip rules, or special payloads localized to the canary's partitions.

**Response:** block promotion, group DLT records by error code/event type, assess business data loss, and plan safe replays.

### 25.5. Failures Persist Even After Rollback

**Symptom:** old stable version reclaims partitions yet keeps failing.

**Possible causes:** canary wrote incompatible data, broke backward schema compatibility, or triggered external non-Kafka side effects.

**Response:** keep the rollback image steady, resolve data compatibility/migrations and business compensation, and never reset offsets blindly.

## 26. Canary Consumer Deployment Checklist

| Item | Question to Answer Before Promoting |
| --- | --- |
| Group topology | Same-group canary or isolated shadow group? |
| Partition coverage | Does the canary have assignments and representative event exposure? |
| Consumer concurrency | Do total members exceed partition count? |
| Schema compatibility | Can both stable and canary read/write all active event versions? |
| Error handling | Are retries, DLT, parse failures, and offset commits clearly understood? |
| Idempotency | Will post-rebalance replays cause duplicate business effects? |
| Side effects | Are DB writes, publishes, and emails/APIs disabled in shadow mode? |
| Metrics | Are metrics split by release track/version with normalized error rates and lag? |
| Rollback | Can canary stop and hand back partitions without arbitrary offset edits? |
| Data compatibility | Can stable code process DB/data touched while canary ran? |
| Shutdown | Are `SIGTERM`, termination grace period, and in-flight work handled cleanly? |
| Capacity | Do Kafka, DB, CPU, memory, and connection pools have headroom? |
| Security | Are canary and shadow Kafka/DB permissions strictly scoped? |
| Audit | Are versions, timestamps, operators, gate results, and rollback reasons logged? |
| Validation | Were join/leave, crash/offset windows, idempotency, and DLT tested appropriately? |

Checklists support operational decisions—they never replace testing and evaluation in your real system.

## 27. Hands-On Exercise

Create a six-partition topic `orders.canary.lab`, a Spring Kafka app consuming `OrderEvent`, and PostgreSQL/H2 projection tables in a test environment.

### Part A — Same-Group Canary

1. Start two stable consumer instances with `groupId=orders-lab` and concurrency 1 each.
2. Send keyed, versioned events and verify projection accuracy.
3. Start one canary instance on a new version with the same group ID and concurrency 1.
4. Wait via Awaitility for group assignments to settle; record stable and canary partition sets.
5. Publish 60 more events across partitions and confirm zero lost business keys.
6. Measure how many events the canary received and compare against actual per-partition traffic.
7. Stop the canary and confirm stable reclaims all partitions without losing progress.

### Part B — Shadow Group

1. Launch a shadow instance with `groupId=orders-lab-shadow`.
2. Permit parsing/validation only, blocking writes to the main production/test projection table.
3. Send a corpus containing valid records, missing fields, old versions, and unrecognized statuses.
4. Confirm stable processes per policy while shadow reports errors independently.
5. Verify the shadow group keeps separate offsets and never rebalances stable.

### Part C — Retries and Correctness

1. Inject a transient DB fault and verify retries/backoff and committed offsets.
2. Commit a record to the DB, then trigger a controlled crash before Kafka offset commit.
3. Confirm the record replays and the idempotency marker prevents duplicate writes.
4. Send an older event version after a newer version and verify the projection does not regress.
5. Inject a non-retryable error, verify DLT routing, and ensure the event is not marked processed.

### Part D — Rollout Decision

Compile a report with these columns:

| Stage | Version | Group | Assigned Partitions | Unique Events | Error Rate | DLT | Lag | Decision |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Stable baseline | v1 | orders-lab | Observed | ... | ... | ... | ... | Baseline |
| Shadow | v2 | orders-lab-shadow | Observed | ... | ... | ... | ... | Go/No-go |
| Canary one pod | v2 | orders-lab | Observed | ... | ... | ... | ... | Go/No-go |
| Expanded rollout | v2 | orders-lab | Observed | ... | ... | ... | ... | Promote/Rollback |

Explain why canary pod percentage differs from processed-event percentage, why shadow mode does not prove end-to-end transactions, and why rolling back an image does not erase committed business side effects.

## 28. Summary

**Canary consumer instances** in Spring Kafka roll out new versions with a bounded blast radius, though control works very differently from HTTP. When stable and canary share **one consumer group**, Kafka distributes **partitions**, not guaranteed message percentages. The canary processes live production events, triggers rebalances, and requires strict offset, retry, DLT, idempotency, and rollback policies.

With a **separate shadow group**, a canary reads live streams to validate parsing/logic without disrupting stable group partition ownership—at the cost of extra broker load, separate offsets, and strict enforcement that all production side effects stay disabled. Shadow testing is a valuable stepping stone, not a replacement for live-processing verification.

A dependable rollout defines blast radius and topology → verifies schema/transactions/idempotency → deploys one new instance with release-scoped telemetry → confirms real assignments and event exposure → evaluates lag, errors, DLT, latency, and business correctness → promotes or rolls back deliberately. **A successful canary must prove data remains accurate across ownership handoffs and failures, not merely that a pod started.**
