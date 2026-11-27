# Consumer Not Receiving Due to Wrong Destination, Group, or Routing Key

A Spring Cloud Stream application can start up, connect to the broker, and report health as UP, yet the `Consumer<T>` function is still never invoked. A common cause is that the producer is publishing to a **different destination**, the consumer belongs to the **wrong group/subscription**, or RabbitMQ fails to route messages from the exchange to the queue because the **routing key does not match the binding key**. The exact same symptom can stem from completely different root causes.

This lesson provides an evidence-based diagnostic procedure for Kafka, RabbitMQ, and Pulsar. The goal is to pinpoint how far the message travels before changing any configuration, avoiding risky operations such as resetting offsets, changing production groups, or deleting queues.

## 1. Classify the Symptom Accurately

| Observation | Likely Cause | What to Check |
|---|---|---|
| No consumer listener exists | Function not activated, wrong binding name | function.definition, Actuator bindings |
| Consumer is STARTED but no messages arrive | Destination, broker, group/offset, or routing | Broker topology and group state |
| Broker delivered but handler failed | Converter, Serde, schema, retry, exception | Error logs, DLT/DLQ, retry metrics |
| Pod A receives nothing, Pod B receives | Competing consumers/partition assignment | Members, partitions, subscription type |
| Producer reports success, Rabbit queue is empty | Wrong exchange or mismatched routing/binding key | Exchange, queue, bindings, mandatory returns |

A message may have **already been received and processed** by another instance in the same group. It may also have **failed processing and moved to the DLQ** before you looked for success logs. Do not equate "no handler logs on this Pod" with "the broker never delivered it."

## 2. Isolate the Path of a Single Event

~~~mermaid
flowchart TD
    A[Producer publish] --> B[Output binding and binder]
    B --> C[Broker / cluster / vhost / namespace]
    C --> D{Middleware}
    D --> E[Kafka topic + partition]
    D --> F[Rabbit exchange + routing key]
    D --> G[Pulsar topic + subscription]
    E --> H[Kafka group + offset/assignment]
    F --> I[Queue + binding key + consumers]
    G --> J[Subscription + cursor/type]
    H --> K[Input binding]
    I --> K
    J --> K
    K --> L[Message conversion/Serde]
    L --> M[Consumer function]
    L --> N[Error handling / DLQ]
~~~

To reproduce, pick **a single unique eventId**, record the publish timestamp, source destination, and producer send result. Then check the exact broker and topology. Never change three configurations at once and guess the root cause.

## 3. Distinguish Function, Binding, Destination, and Group

Spring Cloud Stream uses this convention:

- **Consumer** named `handleOrder` → input binding `handleOrder-in-0`.
- **Supplier** named `produceOrder` → output `produceOrder-out-0`.
- **Function** named `enrichOrder` → input `enrichOrder-in-0`, output `enrichOrder-out-0`.

Example:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderEvent> handleOrder(OrderService service) {
        return event -> service.apply(event);
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          content-type: application/json
~~~

| Value | Meaning | Often Confused With |
|---|---|---|
| handleOrder | Function/Consumer bean name | Topic name |
| handleOrder-in-0 | Input **binding** name | Physical destination |
| orders.created | Configured **destination** | Rabbit queue name |
| fulfillment-service | **Consumer group** | Function name |

If **destination** is omitted, the default is the binding name. In that case the consumer may listen on **handleOrder-in-0**, while the producer publishes to **orders.created**. Those two names will not connect automatically.

## 4. Errors from function.definition or Binding Aliases

Incorrect example:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

The actual bean is named **handleOrder**, so the default input binding is **handleOrder-in-0**. The configuration above uses the wrong key and may prevent the intended destination/group from being applied.

When using an alias:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      function:
        bindings:
          handleOrder-in-0: orderInput
      bindings:
        orderInput:
          destination: orders.created
          group: fulfillment-service
~~~

After mapping an alias, extended binding properties for Kafka/Rabbit/Pulsar must also use the actual binding name according to the mapping contract. When debugging, build a table: **bean → implicit binding → alias (if any) → destination**.

Errors to check before touching the broker:

- Bean was not created due to a profile or conditional annotation.
- Name in `function.definition` is misspelled.
- Function composition produced different binding names than expected.
- Bean has multiple inputs/outputs and uses the wrong `-in-0`, `-in-1` index.
- Multiple binders are on the classpath, and the wrong binder was chosen.
- A Spring profile or environment variable overrides the destination name.

## 5. Fast and Safe Diagnostic Procedure

1. Lock down the event ID, timestamp, and the broker the producer actually uses.
2. Read publish logs: success/failure, topic/exchange, and routing key.
3. Read effective configuration with secrets redacted: function definition, binding name, binder, destination, and group.
4. Check whether the binding is created and STARTED.
5. Verify topology on the right broker: Kafka topic, Rabbit exchange/queue/binding, or Pulsar topic/subscription.
6. Check offset, backlog, assignment, and consumer count.
7. Publish a **new event** with its own ID; do not replay the entire topic.
8. Only if the broker delivered it: inspect deserialization, validation, retries, and DLT/DLQ.
9. Fix only one configuration group at a time, then verify with a test event and monitoring.

Do not start with `resetOffsets: true`, purging a Rabbit queue, or deleting a Pulsar subscription. Those actions alter consumption progress and can create duplicates or data loss.

## 6. Inspect Binding State via Actuator

Spring Cloud Stream provides a bindings actuator endpoint. When the application includes Actuator and the endpoint is secured:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,bindings"
~~~

~~~bash
curl -s http://localhost:8080/actuator/bindings
curl -s http://localhost:8080/actuator/bindings/handleOrder-in-0
~~~

If `handleOrder-in-0` does not appear, investigate function definition, bean scanning, aliases, or binder initialization. A STARTED binding means the lifecycle endpoint has started; **it does not prove messages were delivered**.

The endpoint can start/stop bindings. Only read state during investigation; do not send POST STARTED/STOPPED without an operational decision. Stopping/starting can trigger a Kafka rebalance or message redelivery.

If the endpoint returns not found, it does not mean the binder is not running: Actuator may be missing, bindings may not be exposed, or you may be hitting the wrong management port/path.

## 7. Wrong Binder or Wrong Broker Despite Identical Destination Names

Two Kafka clusters can both contain a topic named `orders.created`. Two RabbitMQ virtual hosts can both contain an exchange named `orders.events`. Two Pulsar namespaces can both have topics ending in `orders.created`.

Therefore, the actual resource identity includes:

| Broker | Must Compare |
|---|---|
| Kafka | Bootstrap servers, cluster, topic, group |
| RabbitMQ | Host/port, virtual host, exchange, queue, routing |
| Pulsar | Service URL, tenant, namespace, topic, subscription |
| Multi-binder | Binder alias, per-binder environment, and binding selection |

Example of a Kafka consumer pointing to the wrong cluster:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          binder: kafkaPayments
~~~

The producer is on `kafkaOrders` while the consumer uses `kafkaPayments`. Both applications may report connected and healthy without ever exchanging the same events.

Never log JAAS strings, passwords, tokens, or private keys when inspecting effective configuration.

## 8. Kafka: Destination Is a Topic, Not a Routing Key

Kafka Binder maps destination to a topic; Kafka **has no AMQP routing key**. Kafka producers route by topic, while record keys usually determine the partition.

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          binder: kafka
      kafka:
        binder:
          brokers: localhost:9092
~~~

If the producer sends to `orders.events` while the consumer listens on `orders.created`, tweaking routing-key settings is meaningless. Compare the physical topic in the producer send result against the input destination.

Topic inspection commands (locally or in an authorized environment):

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.created
~~~

Clusters with TLS/SASL require client properties via `--command-config`. If the topic does not exist or ACLs deny Describe/Read, resolve provisioning/authorization instead of randomly changing the group.

## 9. Kafka: Group Is Already at the End of the Log

Kafka stores committed offsets per partition per group. Example:

~~~text
Topic orders.created, partition 0
Log end offset:         251
Group committed offset: 251
Lag:                    0
~~~

The consumer has caught up with the topic. On restart, it will not re-read records below offset 251 while the committed offset remains valid.

- Named group **with no committed offset yet**: Kafka Binder normally defaults to starting from earliest.
- Anonymous group **with no committed offset yet**: typically defaults to latest.
- Group with committed offsets: committed offset takes precedence over `startOffset`.
- Expired offsets or brand-new group: `startOffset`/`auto.offset.reset` decides the starting point.

Check:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group fulfillment-service
~~~

Examine TOPIC, PARTITION, CURRENT-OFFSET, LOG-END-OFFSET, LAG, CONSUMER-ID, and assignment. When LAG=0, publish a **new event** instead of resetting the group just to see old records.

## 10. Kafka: Instances Sharing a Group Split Partitions

~~~text
Topic orders.created (3 partitions)

Group fulfillment-service
  partition 0 -> Pod A
  partition 1 -> Pod B
  partition 2 -> Pod C
~~~

Each record is normally processed by the single member owning that partition. Pod A not receiving records from partition 2 is expected behavior.

If `fulfillment-service` and `analytics-service` accidentally share the group `order-workers`, they will split partitions instead of each service receiving every record. Two independent services require two distinct groups, whereas replicas of **the same service** share a group.

Do not change a production group without accounting for offsets: a new group with no committed offsets may start reading from earliest, causing duplicate payments, emails, or shipments.

## 11. Kafka: Partition Assignment and Concurrency

If a topic has only 2 partitions while the group has 5 consumer instances, some consumers receive no partition assignments and thus receive no messages.

Check:

- Partition count of the topic.
- Number of active group members and partition assignments.
- Value of `spring.cloud.stream.bindings.<name>.consumer.concurrency`.
- Record keys and partitioner behavior.
- Rebalance loops when an instance fails or restarts.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          consumer:
            concurrency: 3
~~~

Concurrency does not automatically create more Kafka partitions. If one key always routes to partition 0, only the member holding partition 0 receives those records. Use varied keys or inspect assignments during load testing.

## 12. Kafka: startOffset Does Not Automatically Override Committed Offsets

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: false
~~~

`startOffset` mainly applies when the group has no committed offsets yet. Setting `resetOffsets: true` requests seeking to `startOffset` at the appropriate lifecycle point, which can cause replays.

**Do not enable resetOffsets on a production consumer just because you see no logs.** Evaluate the current group, offsets, number of records that could replay, idempotency, and downstream impact before acting.

A safer check is publishing a new event with a unique eventId and observing the group offset advance.

## 13. Kafka: Distinguish Kafka Binder from Kafka Streams Binder

Applications accepting `KStream`, `KTable`, and `GlobalKTable` belong to the Kafka Streams model. They use **application.id**, task assignment, internal topics, and state stores.

When a Kafka Streams function receives nothing:

- Verify you are using the Kafka Streams binder, not the Kafka message-channel binder.
- Check the source destination.
- Check the `application.id` configured for the processor.
- Observe RUNNING/REBALANCING state and task assignments.
- Check state restore/changelog lag and deserialization handlers.
- Do not infer consumer membership from a regular Kafka binder `group`.

Changing `application.id` "just to test" creates a new logical application that re-reads state and offsets from a different history. Perform a proper migration plan rather than changing it mid-incident.

## 14. RabbitMQ: Destination Is an Exchange, Group Usually Determines the Queue

By default, Rabbit Binder creates a topic exchange from the destination. With a named group, the queue is usually named `destination.group`.

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment
          binder: rabbit
~~~

The default topology is typically:

~~~text
Exchange: orders.events
Exchange type: topic
Queue: orders.events.fulfillment
Binding key: #
~~~

Producers publish to the **exchange**, and consumers read from the **queue**. If the consumer expects to read an infrastructure-provisioned queue named `fulfillment_queue`, while the binder declares `orders.events.fulfillment`, having both queues exist will not deliver messages to the right queue.

Rabbit consumers without a group typically use an anonymous auto-delete queue; that queue can disappear when the application stops. Do not use anonymous consumers if you need backlogs to survive restarts.

## 15. RabbitMQ: Routing Key and Binding Key

~~~mermaid
flowchart LR
    P[Producer] -->|routing key order.created| E((orders.events topic exchange))
    E -->|binding order.*| Q1[Fulfillment queue]
    E -->|binding payment.*| Q2[Accounting queue]
    E -->|binding #| Q3[Audit queue]
~~~

With a topic exchange:

- `*` matches **exactly one word** between dots.
- `#` matches zero or more words.
- `order.*` matches `order.created` but not `order.eu.created`.
- `order.#` matches deeper hierarchies.
- Direct exchanges match keys **exactly**.
- Fanout exchanges ignore routing keys when routing.
- Headers exchanges route based on binding arguments/headers.

**By default, Rabbit Binder uses binding key `#`** on non-partitioned topic exchanges. So if you have not customized keys, check for wrong exchange, prefix, or queue before blaming the routing key.

## 16. Configuring RabbitMQ Routing Keys on Both Producer and Consumer

Consumer receiving `order.*`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment
          binder: rabbit
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: "order.*"
~~~

Producer emitting `order.created` (assuming output binding named `publishOrder-out-0`):

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          binder: rabbit
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKey: "order.created"
~~~

If the consumer uses `bindingRoutingKey: "payment.*"`, an `order.created` message will not route to that queue even though the producer sent it successfully.

Distinguish:

| Producer | Consumer | Purpose |
|---|---|---|
| routingKey | bindingRoutingKey | Publish key and queue binding pattern |
| routingKeyExpression | bindingRoutingKey | SpEL to compute routing key and queue pattern |
| destination | destination | Physical exchange must match |
| requiredGroups | group | Can pre-provision queue/group ahead of consumer |

For expressions, inspect the **computed and published** key, not just the expected header name. If keys mismatch due to a wrong header name, fix the producer expression or header contract.

## 17. RabbitMQ: Existing Queues and queueNameGroupOnly

Suppose resources already exist:

~~~text
Exchange: orders.events
Queue: fulfillment_queue
Binding: order.*
~~~

By default, Rabbit Binder names the queue `orders.events.fulfillment_queue` when the group is `fulfillment_queue`. To consume from the pre-bound existing queue:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment_queue
          binder: rabbit
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              queueNameGroupOnly: true
              bindQueue: false
              declareExchange: false
~~~

- `queueNameGroupOnly`: uses the group as the queue name.
- `bindQueue=false`: skips auto-declaring/binding the queue.
- `declareExchange=false`: skips auto-declaring the exchange.
- You must ensure the exchange, queue, binding key, and permissions are **already provisioned** beforehand.

If provisioning is disabled before the queue is created, the listener may log missing queue errors and retry repeatedly. Changing the routing key cannot fix a missing queue.

## 18. RabbitMQ: Sent Successfully but Not Routed to Queue

A publisher confirm means the broker accepted the publish under RabbitMQ semantics; it does not mean a consumer received it or any queue matched the route.

Scenario:

~~~text
Exchange: orders.events (topic)
Queue: orders.events.fulfillment
Binding key: payment.*
Published routing key: order.created
Result: not routed to queue fulfillment
~~~

Check:

1. Does the exchange exist in the **right virtual host**?
2. Is the exchange type topic/direct/fanout as expected?
3. Do the queue and binding exist?
4. Does the actual routing key match the pattern?
5. What is the return/unroutable behavior when no queue matches?
6. What are the publish, deliver, ack, and reject rates?
7. Is another consumer pulling messages off the queue?

`messages_ready=0` alone does not prove no delivery happened: a consumer might be reading and acking very rapidly.

## 19. RabbitMQ: Commands to Inspect Topology

On a test broker or authorized environment:

~~~bash
rabbitmqctl list_vhosts

rabbitmqctl -p /orders list_exchanges name type durable

rabbitmqctl -p /orders list_queues \
  name messages_ready messages_unacknowledged consumers

rabbitmqctl -p /orders list_bindings \
  source_name destination_name destination_kind routing_key
~~~

In the RabbitMQ Management UI, select the exact **vhost**, then inspect exchanges, queue bindings, consumer counts, and message rates.

Do not purge queues, delete queues, or delete bindings just to test. Send a test message with a unique eventId and known routing key, then observe exchange/queue counters.

## 20. RabbitMQ: Prefix, exchangeType, and Partitioning

Rabbit Binder supports a prefix added to exchange/queue names. If the producer uses prefix `prod.` while the consumer does not, both can specify the logical destination `orders.events` while connecting to **two completely different exchanges**.

With `exchangeType: direct`, wildcards like `order.*` do not carry topic-exchange semantics. If the exchange already exists with a different type, re-declaring it can trigger a precondition failure.

When partitioned bindings are enabled, routing/binding keys may receive partition or instance index suffixes such as:

~~~text
orders.events-0
orders.events-1
~~~

Check:

- Producer `partition-count` and partition key/selector.
- Consumer `partitioned`, `instance-count`, and `instance-index`.
- Actual routing key computed by the binder.
- Actual binding key on the Rabbit exchange.
- Corresponding queue and configured consumer instance.

Do not raise concurrency to fix a routing mismatch caused by a wrong partition suffix.

## 21. Pulsar: Destination Is a Topic, Not a Rabbit Routing Key

Pulsar uses topics and subscriptions. A fully qualified topic name typically looks like:

~~~text
persistent://<tenant>/<namespace>/<topic>
~~~

Example:

~~~text
persistent://sales/events/orders.created
~~~

If the producer sends to namespace `sales/events` while the consumer subscribes to `public/default`, having the same short topic suffix does not make them the same topic.

Spring Cloud Stream Pulsar consumer example:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: persistent://sales/events/orders.created
          group: fulfillment
          binder: pulsar
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
~~~

In Spring Cloud Stream, `group` describes the logical consumer group. Pulsar Binder uses Pulsar's subscription mechanism and consumer properties supported by Spring Pulsar. **Verify the actual subscription name** of the application and any overrides instead of assuming it is always identical to a Kafka group ID.

To avoid confusion, use fully qualified topic names when deploying across multiple tenants/namespaces. Verify principal permissions across tenant, namespace, and topic.

## 22. Pulsar: Subscription Type Can Keep an Instance "Silent"

| Subscription Type | Distribution |
|---|---|
| Exclusive | Only one consumer is active on the subscription; others may be rejected |
| Failover | One active consumer, other consumers act as standbys for the respective data |
| Shared | Consumers share messages without global single-consumer ordering |
| Key_Shared | Distributes by key, preserving per-key ordering under supported conditions |

If two Pods share a `Failover` subscription, the standby Pod will receive no messages while the active Pod is healthy. That is valid policy, not a routing error.

Check subscription name, type, consumer count, active/standby status, backlog, and unacknowledged messages. With `Key_Shared`, record the message keys: only one consumer receiving records for a given key may be exact intended behavior.

Do not change subscription types or delete subscriptions in production without assessing ordering, backlog, replay, and acknowledgment semantics.

## 23. Pulsar: Inspecting Topics and Subscriptions

Pulsar Admin CLI/API lists topics, subscriptions, and stats. Local example:

~~~bash
pulsar-admin topics list sales/events

pulsar-admin topics stats \
  persistent://sales/events/orders.created

pulsar-admin topics subscriptions \
  persistent://sales/events/orders.created
~~~

Pulsar versions may differ in exact field names and Admin API permissions. Check:

- Topic belongs to the right tenant and namespace.
- Subscription with the expected name exists.
- Consumers are connected, active, or standby.
- `msgBacklog` and unacknowledged count.
- Publish rate vs dispatch/ack rate.
- Subscription cursor and initial position.
- Redelivery, retry topic, or dead-letter topic.
- Whether Authentication/TLS/ACLs block the consumer from subscribing.

If the topic has new records while the subscription has no consumers, go back and check function activation, bindings, and URLs. If the subscription backlog grows while consumers are connected, check handler errors, schemas, and acknowledgments.

## 24. Multi-Binder: Upstream Publishes to a Different Broker

A bridge application may read from Kafka and emit to RabbitMQ:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: enrichment
          binder: kafka
        enrichOrder-out-0:
          destination: orders.fulfillment
          binder: rabbit
~~~

If the output accidentally points to Kafka, the downstream Rabbit consumer receives nothing even though the input and function are completely valid.

Check each binding independently:

1. Which binder does the input use?
2. Which binder does the output use?
3. What is the destination name on the target broker?
4. Do the named binder's connection settings point to the right cluster/vhost?
5. Did the producer confirm publish and routing?
6. Does the downstream consumer use the right exchange/topic and group?

Do not rely on `spring.cloud.stream.default-binder` to explain all bindings if individual bindings explicitly declare their own `binder`.

## 25. Message Delivered by Broker, but Conversion Fails

Example message:

~~~json
{
  "eventId": "evt-test-004",
  "orderId": "order-104",
  "total": 250000
}
~~~

Consumer function:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long total
) {}

@Bean
Consumer<OrderEvent> handleOrder(OrderService service) {
    return event -> service.apply(event);
}
~~~

The message may reach the binding yet the converter fails to instantiate `OrderEvent` because of:

- Incompatible content-type header.
- Payload is not valid JSON.
- Native decoding enabled with the wrong consumer Serde.
- Avro/Protobuf schema differs from producer.
- Field type changed or cannot be coerced.
- Missing header, null payload, or unhandled tombstone.

Logs should include the exception class and metadata like topic/partition/offset or queue, without exposing sensitive payloads. With Kafka Streams, deserialization handlers execute ahead of the topology; with Pulsar, the schema layer can likewise reject records before the function runs.

Do not alter the destination to fix a converter failure. Confirm delivery occurred and fix the serialization/schema contract.

## 26. Retries and DLQ Make the Consumer Look Unresponsive

When a handler throws an exception, the binder may retry it and then route the record to a DLT/DLQ or apply an error policy.

| Broker | Evidence to Look For |
|---|---|
| Kafka | Handler/deserialization errors, committed offset, DLT such as error.topic.group |
| RabbitMQ | Deliver/reject/ack rates, queue ready/unacked counts, and DLQ depth |
| Pulsar | Retry/redelivery, dead-letter topic, subscription backlog/cursor |

If the broker delivered the message and the DLQ contains that event ID, **the problem is not inbound routing**. Investigate the original exception, retry policy, and recovery/replay procedure.

In particular, a Rabbit message **not routed to any queue** differs from a message **received by a consumer and then dead-lettered**. The two require different investigation paths.

## 27. autoStartup, STOPPED, PAUSED, and Health

The common consumer property `autoStartup` defaults to true:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          consumer:
            autoStartup: true
~~~

If set to false or if the binding was stopped via `BindingsLifecycleController`/Actuator, the application keeps running while the consumer receives nothing.

Check state via `/actuator/bindings`, operator command history, and application lifecycle logs. STARTED does not prove throughput; STOPPED indicates you must find who or what stopped it. PAUSED/RESUMED is not uniformly supported across all binders.

Note that a Kubernetes Pod being NotReady does not automatically pause broker consumers. Readiness controls traffic through Kubernetes Services, not necessarily Kafka polling or Rabbit/Pulsar subscriptions.

## 28. Metric Matrix to Pinpoint the Failing Layer

| Metric / Signal | Clue |
|---|---|
| Producer send confirmation | Whether the broker accepted the publish or threw an error |
| Kafka topic end offset | Whether the topic has new records |
| Kafka group LAG=0 | Group is caught up or no new records exist |
| Kafka group LAG increasing | Consumer is slow, stopped, or failing |
| Kafka assigned partitions=0 | Instance is idle, unassigned, or rebalancing |
| Rabbit exchange publish rises, queue deliver=0 | Routing/binding mismatch or no consumer |
| Rabbit queue ready rises | Routed to queue, not yet delivered |
| Rabbit unacked rises | Consumer received but has not acked |
| Rabbit DLQ depth rises | Processing failure or queue policy |
| Pulsar msgBacklog rises | Subscription holds unprocessed messages |
| Pulsar active consumers=0 | No consumer actually attached |
| Function invocation count rises | Code is being called; check side effects |
| Binder health UP | Connection/lifecycle may be fine; does not prove message flow |

Never rely on a single metric to diagnose a failure. For example, Rabbit `queue ready=0` can happen because consumers process rapidly or because no messages were routed. Combine publish, deliver, ack, binding topology, and event IDs.

## 29. Scenario 1: Kafka Uses the Wrong Input Binding Name

**Code:**

~~~java
@Bean
Consumer<OrderEvent> handleOrder(OrderService service) {
    return event -> service.apply(event);
}
~~~

**Wrong configuration:**

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

The function creates `handleOrder-in-0`, not `receiveOrder-in-0`. As a result, the configuration applies to an unrelated binding.

**Fixed configuration:**

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

After fixing, check `/actuator/bindings` and the group on the broker. Do not reset offsets just because you fixed the config key name.

## 30. Scenario 2: Two Kafka Services Accidentally Share a Group

~~~text
fulfillment-service -> group orders-workers
analytics-service   -> group orders-workers
~~~

Both read `orders.created`, yet each service must process every event. Because they share a group, Kafka splits partitions across members instead of broadcasting a copy to each service.

Fix by giving each service its own group:

~~~yaml
# application.yml for fulfillment
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

Analytics can use group `order-analytics`. Check committed offsets for a new group before deploying; it may start reading from earliest and reprocess historical events.

## 31. Scenario 3: Rabbit Exchange Exists, but Binding Key Is Wrong

~~~text
Exchange: orders.events (topic)
Queue: orders.events.fulfillment
Binding key: payment.*
Published routing key: order.created
~~~

The consumer receives nothing because `payment.*` does not match `order.created`. If the business requires receiving orders:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              bindingRoutingKey: "order.*"
~~~

**After deploying, verify the real broker has the new binding.** If `bindQueue=false` or queues/exchanges are managed via IaC, editing properties will not change externally provisioned topology. Apply the change through the proper IaC/management workflow.

Do not widen the key to `#` carelessly, as that can flood the queue with unintended events.

## 32. Scenario 4: Existing Rabbit Queue Has a Different Name

Existing topology:

~~~text
Exchange: orders.events
Queue: fulfillment_queue
Binding key: order.*
~~~

An application specifying only `group: fulfillment_queue` defaults to targeting `orders.events.fulfillment_queue`, which is a different queue.

Configuration when IaC already provisioned all resources:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              queueNameGroupOnly: true
              bindQueue: false
              declareExchange: false
~~~

Combine this with `destination: orders.events` and `group: fulfillment_queue`. Verify the queue is bound to the right exchange and the user has consume permissions.

## 33. Scenario 5: Pulsar Has the Same Short Topic Name in a Different Namespace

~~~text
Producer: persistent://sales/events/orders.created
Consumer: persistent://public/default/orders.created
~~~

These are two distinct topics. Update the consumer destination to the fully qualified topic used by the producer:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: persistent://sales/events/orders.created
          group: fulfillment
~~~

After fixing, inspect the actual subscription and permissions on `sales/events`. Do not delete the old subscription if it still holds backlog needed for retention or migration.

## 34. Scenario 6: Broker Delivered the Message, but Handler Failed

Rabbit deliver rates increase or Kafka offset/group state advances, yet no "order processed" log appears. Check:

1. Which instance owns the partition or queue consumer?
2. Was the function invoked?
3. What was the first exception in the retry chain?
4. Did the event enter the DLQ/DLT?
5. Was there a transaction rollback or idempotency skip?
6. Are logs filtered or sitting on a different Pod?

Once the broker has delivered the message, shift investigation to handler/conversion and error policy. Changing routing keys will not fix a business exception.

## 35. Testing with Testcontainers After Fixing

Unit-testing a function proves business logic only, not broker topology. Integration tests should:

1. Start a real broker with Testcontainers.
2. Initialize the Spring context with the real binder and dynamic endpoints.
3. Provision topics/exchanges/queues/subscriptions matching the contract.
4. Publish a unique eventId.
5. Assert the handler receives the expected event within a finite timeout.
6. Kafka: test distinct groups, committed offsets, and assignments.
7. Rabbit: test one matching routing key and one non-matching routing key.
8. Pulsar: test fully qualified topics and subscription name/type.
9. Test wrong content type/Serde and verify the error path.
10. Restart the consumer and verify backlog, redelivery, and idempotency.
11. Exclude Spring Integration Test Binder from the same test runtime when testing against a real broker.

Pseudo-Java example (project-defined test helper):

~~~java
OrderEvent event =
    new OrderEvent("evt-it-101", "order-it-101", 1000L);

brokerTestClient.publish("orders.created", event);

await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertThat(processedEvents.existsById(event.eventId()))
            .isTrue()
    );
~~~

For RabbitMQ, the helper must publish to the **exchange with a specific routing key**, not directly to the queue so the routing layer under test is exercised. For Pulsar, use the right tenant/namespace; for Kafka, verify topic/partition assignment.

## 36. Production Runbook: Observe Before Changing

~~~mermaid
flowchart TD
    A[No messages seen] --> B{Binding STARTED?}
    B -->|No| C[Function definition / alias / lifecycle]
    B -->|Yes| D{Binder + broker + destination correct?}
    D -->|No| E[Fix binding/endpoint]
    D -->|Yes| F{Messages on destination?}
    F -->|No| G[Check producer confirmation]
    F -->|Yes| H{Group/queue/subscription receiving?}
    H -->|No| I[Offset, assignment, routing, subscription type]
    H -->|Yes| J[Conversion, handler, retry, DLQ]
~~~

Before changing production:

- Capture effective configuration with secrets redacted.
- Record topic/queue/subscription, partitions, committed offsets, backlog, and cursors.
- Assess side effects: payments, shipments, emails, databases.
- Never reset groups, purge queues, or delete subscriptions without a plan.
- If broadening a Rabbit binding pattern, ensure consumers will not pull events belonging to another tenant.
- If switching destinations, check for remaining backlog on the old destination.
- After applying the fix, publish one safe test event, verify ack/commit, and save evidence.
- Monitor lag, queue depth, DLT, and retries post-deploy.

A minor configuration mistake should never be "fixed" with an action that causes a large-scale data replay.

## 37. Quick Error Reference by Root Cause

| Symptom | Possible Cause | Evidence | Fix |
|---|---|---|---|
| Missing binding | Wrong function/alias | Actuator bindings | Fix definition/key |
| Binding reads strange destination | Missing destination | Effective config | Declare destination |
| Kafka group lag=0 | Already at end of topic | consumer-groups describe | Publish a new test event |
| One Kafka Pod receives nothing | No partition assigned | Group member assignment | Check partitions/concurrency |
| Two services split data | Shared group | Member list | Separate groups, plan offsets |
| Kafka Streams silent | Application ID, tasks/Serde | Thread/restore/error logs | Fix per Streams semantics |
| Rabbit queue missing | Wrong group/prefix/provisioning | list_queues | Fix naming/IaC |
| Rabbit queue has no messages | Binding key mismatch | list_bindings/publish key | Fix routing |
| Rabbit existing queue ignored | queueNameGroupOnly=false | Queue names | Adjust property |
| Rabbit wrong vhost | Connected to another vhost | Connections/UI | Align vhost |
| Pulsar topic "right name" | Wrong namespace | Full topic name | Align tenant/namespace |
| Pulsar standby idle | Failover/Exclusive subscription | Subscription stats | Verify semantics |
| Messages landed in DLQ | Handler/Serde failure | DLT/DLQ, exceptions | Fix conversion/processing |
| Consumer STOPPED | autoStartup or operator | Binding state | Start per runbook |
| Fails only in production | Profile/env override | Config diff | Fix config source |

## 38. Final Checklist

- [ ] Bean name, `function.definition`, and input binding match.
- [ ] Explicit destination is set, avoiding accidental use of binding name as topic.
- [ ] Correct binder alias, cluster, Rabbit vhost, or Pulsar namespace.
- [ ] Kafka: topic, group, offsets, and partition assignment verified.
- [ ] Kafka Streams: `application.id`, task state, and Serdes verified.
- [ ] Rabbit: exchange type, queue, group, prefix, binding key, and publish routing key match.
- [ ] Rabbit: existing queues use `queueNameGroupOnly` and proper provisioning flags.
- [ ] Pulsar: fully qualified topic, subscription name/type, and cursor are correct.
- [ ] Binding is STARTED, not paused or stopped.
- [ ] Content type, serialization, retries, and DLQ checked.
- [ ] Used a fresh event with a unique ID for end-to-end tracing.
- [ ] Did not reset offsets or delete queues/subscriptions just to test.
- [ ] Real-broker integration test prevents regression.

## 39. References

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html), function input/output naming conventions and aliases.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html), destination, group, binder, autoStartup, concurrency.
- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html), competing consumers and anonymous groups.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html), bindings Actuator and lifecycle.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), Kafka consumer properties.
- [Spring Cloud Stream — Resetting Kafka Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/reset-offsets.html), startOffset, resetOffsets, committed offsets.
- [Spring Cloud Stream — RabbitMQ Existing Queues/Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html), exchange/queue naming rules and reusing existing queues.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html), bindingRoutingKey, queueNameGroupOnly, bindQueue.
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html), routingKey and routingKeyExpression.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges), direct/topic/fanout and routing.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), topic destinations, schemas, and binder properties.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html), subscription name/type, listeners, and concurrency.

**Conclusion:** When a Consumer receives no messages, isolate in order: **function/binding → binder/broker → destination → group/queue/subscription → offset/routing → conversion/handler**. Kafka primarily requires checking topic, group, offsets, and partition assignment; RabbitMQ requires comparing exchange, queue, routing key, and binding key; Pulsar requires verifying the fully qualified topic and subscription. Change configuration only after proving how far the event traveled; avoid turning a routing mistake into data loss or an unintended replay incident.
