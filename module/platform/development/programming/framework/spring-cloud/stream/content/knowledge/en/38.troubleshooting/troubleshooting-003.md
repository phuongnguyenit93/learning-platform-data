# Sent Successfully Locally but Broker or Consumer Has Not Received the Data

A Spring Cloud Stream application logs "sent successfully" or calls `StreamBridge.send(...)` which returns `true`, yet the Kafka topic shows no record, the RabbitMQ queue remains empty, or the Pulsar consumer does not run. This issue is very misleading: **"sent successfully" at one point in the application does not mean the broker has confirmed storing or routing the message; nor does the broker receiving it guarantee the consumer has completed its business logic**.

To diagnose this, trace each boundary along the event path: the message-producing function, output binding, binder/producer client, broker, input binding, and consumer function. This lesson establishes a method applicable to Spring Cloud Stream using `Supplier`, `Function`, `Consumer`, and `StreamBridge` over Kafka, RabbitMQ, or Pulsar. The examples emphasize observable evidence, configuration, inspection commands, reproducible tests, and fixes that avoid dropping or duplicating data.

## 1. Which Milestone Does "Success" Belong To?

A message flow has multiple independent confirmation milestones:

~~~mermaid
flowchart LR
    A["Producer: build Message"] --> B["Spring Integration channel / binding"]
    B --> C["Binder + client buffer"]
    C --> D["Broker ACK / publisher confirm"]
    D --> E["Topic log or queue/subscription"]
    E --> F["Consumer poll / delivery"]
    F --> G["Deserialize + invoke Function"]
    G --> H["Business side effect"]
    H --> I["Commit / ACK"]
~~~

| Milestone | Evidence That Can Be Collected | Valid Conclusion | Not Yet Proven |
|---|---|---|---|
| 1. Function invoked | Producer logs, unit test of `Function` | Code reached the point of emitting the message | Binding received the message |
| 2. Sent to channel successfully | `StreamBridge.send(...) == true` or no exception during handoff | Local send path accepted the message under current semantics | Broker persisted it or consumer received it |
| 3. Producer/binder sent over network | Send/request metrics, client logs, callbacks | Producer is communicating with the broker | Broker ACKed successfully |
| 4. Broker confirmed | Kafka `RecordMetadata`, Rabbit publisher confirm/return, Pulsar send result | Broker confirmed according to protocol and configuration | A subscriber exists or consumer processed it |
| 5. Record exists / routed properly | Kafka topic/partition/offset, Rabbit queue/routing, Pulsar topic stats | Data is in the right destination or routing path | Application consumer is reading |
| 6. Consumer received message | Group/subscription metrics, entrypoint logs | Client received or broker delivered the message | DTO deserialized properly or business logic succeeded |
| 7. Business logic processed | Business logs, DB transaction, idempotency record | Side effect succeeded per contract | Commit/ACK always completed |
| 8. Offset commit/ACK | Kafka committed offset, Rabbit ACK/queue count, Pulsar subscription cursor | Broker recorded consumption progress | Business side effect is strictly exactly-once |

**The diagnostic goal is to find the first boundary lacking evidence.** If the broker already has the record in the right topic while the consumer is not receiving it, tweaking producer retries usually will not fix it. If the producer has not yet received broker confirmation, resetting Kafka consumer offsets will not help either.

### Example of Sending "Successfully" Without Broker ACK Evidence

~~~java
boolean accepted = streamBridge.send(
        "orders-out",
        MessageBuilder.withPayload(event)
                .setHeader("event-id", event.eventId())
                .build());

log.info("orders-out accepted={}", accepted);
~~~

The value `true` reflects that the send path through Spring Integration/binding accepted the call, **not a durable confirmation receipt from Kafka/RabbitMQ/Pulsar**. Spring Cloud Stream allows `StreamBridge.setAsync(true)` to send on another thread; in asynchronous mode, the moment the application finishes the call is even less valid as evidence of broker ACK. Both synchronous-style sends and async mode require checking producer outcomes when reliable delivery is required.

## 2. Start with a Single Event ID and a Correlatable Trace

Before changing any configuration, pick a test message with a stable identifier:

~~~json
{
  "eventId": "diag-order-2026-11-24-001",
  "orderId": "order-101",
  "amount": 250000
}
~~~

Put `event-id` in the message header and payload if the contract permits. Record at minimum:

- Environment, application instance, application version, and binder type.
- Active `spring.cloud.function.definition`.
- Binding names on producer and consumer.
- Actual destination: Kafka topic, Rabbit exchange/queue, or Pulsar topic.
- Broker address, cluster, Rabbit virtual host/Pulsar namespace, and consumer group or subscription.
- UTC timestamp, event ID, correlation ID, and key/routing key.
- Status of producer send result, broker counters, and consumer logs.

Do not generate a new event ID for the same message on retry. If the same message is redelivered, a stable event ID helps detect duplicates and correlate attempts. Do not log full payloads or tokens in diagnostic logs if they contain sensitive data.

**Structured log template:**

~~~json
{
  "timestamp": "2026-11-24T09:00:00Z",
  "service": "order-api",
  "operation": "message.publish.accepted",
  "event_id": "diag-order-2026-11-24-001",
  "binding": "orders-out",
  "broker": "kafka",
  "destination": "orders.events",
  "accepted_locally": true,
  "broker_confirmation": "pending"
}
~~~

`broker_confirmation=pending` means *confirmation evidence does not yet exist at log time*, not that the broker rejected it. Use states `pending`, `confirmed`, `failed`, or `unknown` to distinguish "not yet known" from "failed."

## 3. Quick Diagnostic Decision Tree

~~~mermaid
flowchart TD
    A["App logs 'sent successfully'"] --> B{"Producer ACK / send result?"}
    B -->|"Missing or error"| C["Check channel, binder, serialization, broker address, ACL, network, async error channel"]
    B -->|"Yes"| D{"Broker has record/route?"}
    D -->|"Wrong topic or unrouted"| E["Check destination, KafkaHeaders.TOPIC, exchange/routing key, namespace"]
    D -->|"Yes"| F{"Consumer binding is RUNNING?"}
    F -->|"No"| G["Check function definition, group, binder, lifecycle, subscription"]
    F -->|"Yes"| H{"Broker delivered / consumer fetched?"}
    H -->|"No"| I["Check offset/cursor, consumer lag, assignment, queue name"]
    H -->|"Delivered"| J{"Function processed it?"}
    J -->|"No"| K["Check contentType, Serde/schema, retry, DLT/DLQ, filter, exception"]
    J -->|"Yes"| L["Compare side effects, transactions, ACK/commit, and idempotency"]
~~~

Always compare **the same environment, same cluster, and same event ID**. An application pointing at a dev broker while an operator inspects production is a surprisingly common cause of the "empty topic" symptom.

## 4. Check the Function and Binding Before Looking at the Broker

Spring Cloud Stream maps function beans to input/output bindings. If a binding name is wrong, the application can run normally while messages are sent to a different output.

Example:

~~~java
record OrderEvent(String eventId, String orderId, long amount) {
}

interface OrderService {
    void handle(OrderEvent event);
}

@Bean
Consumer<Message<OrderEvent>> consumeOrder(OrderService orderService) {
    return message -> {
        log.info("Consumer entered event-id={}",
                message.getHeaders().get("event-id"));
        orderService.handle(message.getPayload());
    };
}
~~~

For the function `consumeOrder`, the default input binding is `consumeOrder-in-0`. Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
        orders-out:
          destination: orders.events
~~~

Here `orders-out` is a binding name used by `StreamBridge`, not a function bean name. When sending via `StreamBridge.send("orders-out", message)`, the corresponding configuration maps to the `orders.events` destination.

### Configuration Mistakes to Check First

| Case | Consequence | How to Verify |
|---|---|---|
| `spring.cloud.function.definition` does not point to the receiving function | Desired input binding is not created | Check function beans and startup binding logs |
| Wrong `-in-0`, `-out-0` suffix | Binding config is not applied to the real port | Match function name against binding name |
| `StreamBridge.send` uses wrong name | Can create another dynamic destination | Log the binding name and query binding status |
| Output binding has unexpected `destination` | Messages go to another topic/exchange | Check runtime config, not only source YAML files |
| `KafkaHeaders.TOPIC` override enabled | Producer can write to a header-specified topic | Check Kafka binder `useTopicHeader` and actual headers |
| Multiple binders present, wrong one picked | Messages go via Rabbit instead of Kafka or vice versa | Check per-binding binder or `StreamBridge` `binderName` arg |
| Test Binder on the classpath | Messages only pass through in-JVM channels | Check actual binder, do not rely on passing tests |
| Consumer binding stopped | Broker has data but function does not run | Check binding lifecycle and health |

When `spring.cloud.function.definition` contains `functionA|functionB`, binding names depend on function composition and can differ from individual beans. When using a semicolon to activate multiple independent functions, each function gets its own bindings. Do not guess binding names; check startup logs, `/actuator/bindings`, and effective configuration.

## 5. Inspect Binding Status via Actuator

Add Spring Boot Actuator and expose the bindings endpoint for administrators:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Read-only queries:

~~~http
GET /actuator/bindings
GET /actuator/bindings/consumeOrder-in-0
GET /actuator/bindings/orders-out
GET /actuator/health
~~~

The bindings endpoint shows whether a binding is running, stopped, or in another lifecycle state. If a consumer binding is `STOPPED`, investigate actuator/admin/config or startup errors; do not automatically re-send events before confirming the path.

The bindings endpoint also supports state-changing actions, but **do not POST START/STOP as a default diagnostic step** in production. Doing so can trigger rebalances, alter processing order, and impact consumer groups. Only act according to an authorized runbook with a rollback plan.

For Kafka Streams, also inspect the state of the `KafkaStreams` instance, threads, and tasks; a Spring Boot process can stay alive even after a stream thread has died. For RabbitMQ or Pulsar, check listener/subscription connections on the broker to confirm the binding actually registered.

## 6. Use Logs and Metrics at the Right Layers

Log at four distinct moments:

1. `publish.requested` — application builds the message.
2. `publish.accepted_locally` — send call was accepted.
3. `publish.broker_confirmed` or `publish.failed` — producer/broker result arrived.
4. `consume.received` and `consume.processed` — consumer received and completed business processing.

Do not log "delivered" at step 2. Without a confirmation callback from the binder, use "accepted," "dispatched," or "pending."

A dashboard can include:

| Metric | Reason |
|---|---|
| Producer local attempts/success/failure | Know whether the app actually issued sends |
| Producer client request/error/retry rate | Detect timeouts, authorization, and connection issues |
| Broker accepted/published rate | Verify the broker is accepting traffic |
| Topic/queue/subscription backlog | Identify where messages are accumulating |
| Consumer assignments, poll/delivery rate | Confirm consumers are fetching/receiving |
| Conversion error, retry, DLT/DLQ rate | Detect messages received but failing before the business function |
| Business success/failure rate | Correlate events with side effects |

High-cardinality event IDs belong in logs or traces; **do not use them as metric labels**. Metrics should use application, destination, status, broker, and other dimensions with bounded cardinality.

## 7. When Spring Integration Test Binder Misleads Results

Spring Cloud Stream provides `spring-cloud-stream-test-binder` for testing without Kafka/RabbitMQ/Pulsar. Test Binder passes messages in-JVM. When it is on the test classpath and active in the Spring context, `OutputDestination.receive(...)` can receive messages even with no real broker running.

Therefore:

- Unit/integration tests with Test Binder only validate function flow and simulated bindings.
- Testing producer delivery requires starting a real binder and real broker (e.g., Testcontainers).
- Do not mix Test Binder and real middleware binders in the same test module without explicit separation; Spring Cloud Stream documentation recommends separate test modules.
- In production runtime, confirm binder type and broker connectivity via logs and metrics, never by assuming context startup implies broker connectivity.

**Symptom:** Test logs "send true, OutputDestination received," while Kafka console consumer or Rabbit Management shows no messages. This is not evidence that the broker dropped data; the entire test may have executed purely in-JVM.

## 8. Kafka: Obtain Evidence of Producer Broker Confirmation

Kafka producers typically operate asynchronously. To know where a record was acknowledged by the broker, the Kafka binder provides `recordMetadataChannel` for output bindings.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out:
          destination: orders.events
          producer:
            error-channel-enabled: true
      kafka:
        bindings:
          orders-out:
            producer:
              record-metadata-channel: kafkaPublishMetadata
~~~

Register the channel and listener to receive successful results:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
class KafkaPublishDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPublishDiagnostics.class);

    @Bean("kafkaPublishMetadata")
    MessageChannel kafkaPublishMetadata() {
        return new DirectChannel();
    }

    @ServiceActivator(inputChannel = "kafkaPublishMetadata")
    void onPublished(Message<?> message) {
        RecordMetadata metadata = message.getHeaders()
                .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);
        if (metadata != null) {
            log.info("Broker confirmed topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(),
                    metadata.offset());
        }
    }
}
~~~

`KafkaHeaders.RECORD_METADATA` holds the `RecordMetadata` returned by the Kafka client on a successful send, including topic, partition, and offset. **This is far stronger evidence than `StreamBridge.send() == true`.** If the callback never arrives, check client/binder errors, timeouts, callback registration, and producer state; do not jump to assuming the record was lost.

### Catching Asynchronous Send Errors

Common property:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out:
          producer:
            error-channel-enabled: true
~~~

For binders supporting async results, send errors can be routed to the corresponding producer error channel. Register an error handler matching the binder/version channel name (or handle via the global Spring Integration `errorChannel` if routed there) and log the error type, destination, event ID, and a sanitized stack trace. Do not treat `error-channel-enabled` as an automatic retry or durable storage mechanism: the application must decide how to alert, persist, or retry appropriately.

Example errors to look for in a Kafka producer:

- `TimeoutException` when the broker does not respond within the delivery limit.
- `SerializationException` or payload conversion errors before sending.
- `TopicAuthorizationException`, `ClusterAuthorizationException`, or ACL denials.
- `UnknownTopicOrPartitionException` if the topic does not exist and auto-provisioning is unavailable.
- `RecordTooLargeException` or incompatible message size policies.
- `NotEnoughReplicasException` when replicas/min-ISR do not satisfy configuration.

An error can surface synchronously during send or asynchronously after the method returns; monitor both exceptions at the caller and callbacks/error channels.

## 9. Kafka: Inspect the Broker, Topic, and Partitions

Use the Kafka CLI with proper permissions and the exact cluster endpoint. The command below is a read-only diagnostic example:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-broker:9092 \
  --describe \
  --topic orders.events
~~~

Check topic existence, partition count, leaders, replicas/ISR, ACLs, and whether the producer can write to the right cluster. Topics with the same name in two different clusters are not the same data source.

Read messages with a **dedicated diagnostic consumer group** rather than the production group to avoid disrupting assignments:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka-broker:9092 \
  --topic orders.events \
  --group diag-orders-001 \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

`--from-beginning` applies to a group without a committed offset (or partitions without offsets) depending on configuration. When a group already has committed offsets, Kafka prioritizes the stored offsets; changing a console-consumer flag does not automatically reset group progress. If messages contain sensitive data, use only test payloads or authorized topics; do not print personal data to a terminal.

Once you see a record with a specific key/partition/offset, record those details and move to the consumer layer. If the probe group cannot read anything, do not immediately conclude no record exists: check retention, timestamps, ACLs, offsets, cluster name, and broker health.

### Kafka Native Key and Topic Override

When using `KafkaHeaders.KEY`, identical keys are consistently routed by the producer to partitions based on the partition count at send time. A hot key can concentrate records in one partition, leaving consumers on other partitions idle even while the topic has traffic.

The Kafka binder supports `useTopicHeader`: when enabled, the `KafkaHeaders.TOPIC` header can override the output binding's destination. If the application publishes to dynamic topics, inspect **the final topic from `RecordMetadata`**, not just the binding name in source code.

## 10. Kafka: Consumer Group, Offsets, and Lag

When the broker holds records yet the consumer logs nothing, the cause is often group state or offsets. Check first:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-broker:9092 \
  --describe \
  --group order-worker
~~~

Compare `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG` **per partition**; examine `CONSUMER-ID`, `HOST`, and `CLIENT-ID` to verify assignments.

| Observation | Possibility | Next Step |
|---|---|---|
| Group does not exist | Consumer not created, wrong group name, or never committed | Check function definition, binding destination/group, and app logs |
| Group has members but no matching partition assignment | Rebalancing, more consumers than partitions, or topic mismatch | Check metadata, subscription, and partition count |
| Lag is 0 and group has committed the latest offset | Consumer already read/committed or skipped earlier | Check consumer function, side effects, retry/DLT, and offset history |
| One partition lags while others are near 0 | Hot key, slow processing, or unstable consumer | Check key skew and poll/process/commit latency |
| Lag growing across all partitions | No active consumer, missing read permissions, or insufficient throughput | Check connectivity, ACLs, group, and capacity |
| New group does not read history | Offset reset policy is latest or group started after records were produced | Test an isolated group with earliest if history is genuinely needed |

**Important:** the initial offset policy (`startOffset` / Kafka `auto.offset.reset`) normally applies only when a consumer group has no valid committed offset. Changing this property does not automatically replay already-committed records. The Spring Cloud Stream Kafka binder defaults to `startOffset=earliest` for bindings with an explicit group and `latest` for anonymous groups; actual behavior also depends on `resetOffsets`.

Example for a new consumer group:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
      kafka:
        bindings:
          consumeOrder-in-0:
            consumer:
              start-offset: earliest
              reset-offsets: false
~~~

`reset-offsets: false` means **do not force-reset already committed progress**. Never enable `reset-offsets: true` on a production group just to "see if it reads," as this can trigger mass replays, duplicate side effects, and alter confirmed progress.

### Commit Does Not Equal Business Success

If a consumer reads a message and swallows an exception, logs "ignored," or ACKs before a DB transaction commits, the offset/cursor may advance even though business work never finished. Conversely, if the DB commits successfully but the consumer crashes before committing the Kafka offset, the message can be redelivered: the consumer needs idempotency.

When logs show the function never ran despite group offsets advancing, inspect layers ahead of the function: deserializer, content conversion, filters, retries, and DLT/handlers. Do not claim "Kafka lost data" solely because offsets moved forward.

## 11. Kafka: Producer Config, Network, Security, and Transactions

Producer verification steps:

1. Read the **effective config** of the binder: `spring.cloud.stream.kafka.binder.brokers`, security protocol, SASL/TLS, and producer properties.
2. Verify the producer connects to the right bootstrap servers; returned metadata must advertise listener addresses reachable from the app/container.
3. Check topic ACLs: `Describe` and `Write` or other required permissions.
4. Observe broker producer requests, timeouts, and callbacks; do not rely solely on `KafkaProducer` init logs.
5. Check `acks`, `delivery.timeout.ms`, `retries`, `enable.idempotence`, topic ISR, and cluster error policies.
6. If the binder enables transactions, check transaction commits/aborts, transaction fencing, and consumer `isolation.level`.

**Kafka transactions:** a producer can send records inside an uncommitted transaction; a consumer using `read_committed` will not see uncommitted or aborted records, even though the producer called send and received an internal per-record callback. A "send callback succeeded" inside a transaction does not replace a **successful transaction commit**. Observe the entire transaction lifecycle.

For simple non-transactional publishers, Kafka `acks=all` provides stronger replica durability than `acks=1` per broker policy, but it does not create exactly-once business processing on its own. Do not arbitrarily alter `acks` or `min.insync.replicas` during an investigation without assessing durability and availability trade-offs.

## 12. RabbitMQ: Exchange Receives Messages but Queue Is Empty

RabbitMQ publishes to an **exchange**, which then routes to queues based on bindings and routing keys. If the exchange exists without a matching queue/binding, messages may reach no queue. The producer can still receive a publisher confirm indicating the broker processed the publish, even when the message was unroutable.

~~~mermaid
flowchart LR
    A["Spring Cloud Stream Rabbit producer"] --> B["Exchange: orders.events"]
    B -->|"matching routing key"| C["Queue: orders.events.order-worker"]
    B -->|"No matching binding"| D["Unroutable / returned if mandatory"]
    C --> E["Consumer group order-worker"]
~~~

**Distinguish two RabbitMQ signals:**

- **Publisher confirm (ACK/NACK):** the broker confirms/handles the publish command on the producer side under the confirm protocol.
- **Publisher return:** for `mandatory` publishes, the broker returns messages that cannot be routed to any queue (rather than silently dropping them).

A publisher confirm ACK **does not guarantee a consumer processed the message**, nor does it guarantee routing to a queue when no route exists. Observe both returned messages and queue counters.

### Callback and Error Channel Configuration

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq
    port: 5672
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orders-out:
          destination: orders.events
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orders-out:
            producer:
              confirm-ack-channel: rabbitPublishConfirms
~~~

The Rabbit binder supports `confirmAckChannel` for positive publisher confirms and `useConfirmHeader` for obtaining results via correlation-data futures; these are mutually exclusive alternatives, **do not enable both**. In the example, the application must configure the channel/listener to observe ACKs. The connection factory must support correlated publisher confirms. To catch unroutable returns, enable publisher returns and the appropriate mandatory/return behavior; verify against your Spring Boot, Spring AMQP, and binder versions.

The Rabbit binder can route returned messages and negative publisher confirms to an error channel when the supported options are enabled. Returned messages include the reply code/text, exchange, and routing key; this is strong evidence of a routing failure.

### Inspect Queue Topology on the Broker

In the RabbitMQ Management UI or HTTP API, check:

- Do producer and consumer share the same vhost?
- Does exchange `orders.events` exist with the expected type?
- What is the actual queue name? With a group, the binder normally forms a name from destination + group (unless `queueNameGroupOnly` or a prefix changes it).
- Is the queue bound to the exchange with the right routing key/pattern?
- How are `publish`, `deliver`, `ack`, `messages_ready`, and `messages_unacknowledged` counters changing?
- Are there alternate exchanges, TTLs, max-length limits, overflows, dead-letter exchanges, or auto-delete/exclusive queues?

`messages_ready=0` does not prove the producer failed to send: the consumer may be reading/ACKing very fast. `messages_unacknowledged>0` indicates messages were delivered but not yet ACKed. If `publish` rises while the queue stays flat and returns report `NO_ROUTE`, the problem lies in routing/topology.

## 13. RabbitMQ: Queue Exists but Consumer Sees No Messages

After proving messages are routed to the queue, check the **actual consumer**, not only queued message counts:

| RabbitMQ Symptom | Possible Interpretation | How to Address |
|---|---|---|
| Queue has `messages_ready > 0`, `consumers = 0` | No consumer attached | Check function definition, binding group, vhost, and service availability |
| Queue has `messages_ready > 0`, active consumers | Consumers blocked by prefetch, flow control, or low throughput | Check unacked count, listener errors, connections, and thread pools |
| `messages_unacknowledged` grows steadily | Messages delivered but never ACKed | Check hung listeners, DB/API timeouts, and acknowledgment mode |
| Queue stays empty while consumer logs events | Consumer processes fast enough that queue does not build up | Verify business outcomes and ACKs |
| DLQ grows | Consumer received then rejected/exhausted retries or hit TTL/delivery limits | Check DLX, error logs, retry policy, and failing payloads |
| Another queue receives data | Wrong queue/group name or different `queueNameGroupOnly`/prefix | Compare destination/group on both sides |
| Queue disappears after restart | Anonymous/auto-delete/exclusive/ephemeral queue | Check durability, autoDelete, group, and declarations |

In the Rabbit binder, an explicit consumer group usually creates a queue named from destination and group. If a producer publishes before the queue/binding is created, messages are not automatically buffered for future consumers merely because the exchange exists. For systems that must not drop messages, provision queues/bindings early and configure publisher confirms/returns, durability, persistent delivery, and retries.

Consumer group example:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
~~~

If the broker has a queue `orders.events.other-worker` while the application uses `group=order-worker`, looking at the first queue leads to the wrong conclusion. Compare effective vhost, exchange, queue, binding key, and consumer group.

### ACK, Requeue, and Dead Letter

When a business function throws an exception, the Rabbit binder/listener can retry, reject, requeue, or route to a DLQ depending on configuration. Depending on policy, a message may vanish from the main queue and land in the DLQ; the main consumer will not log success. Check `autoBindDlq`, `republishToDlq`, delivery limits, TTL, and queue overflow before concluding a message was lost.

Do not endlessly requeue a poison message that cannot be deserialized: it can create a tight loop and block other messages. Record the event ID, exception type, routing key, redelivery count, and DLQ destination.

## 14. Pulsar: Producer Success Does Not Equal Subscription Consumption

The Spring Cloud Stream Pulsar binder uses the client and topic provisioner from Spring for Apache Pulsar. A topic typically looks like:

~~~text
persistent://public/default/orders.events
~~~

The tenant, namespace, topic, persistence type, and broker cluster must match the environment under inspection. A client can connect to Pulsar successfully yet write to a different namespace due to a default namespace or differing destination config.

Levels of evidence:

1. The application invoked send through the output binding.
2. The Pulsar producer client received a publish result (message ID or send result).
3. Topic stats show producers and `msgRateIn`/counters increasing.
4. The subscription is created and has consumers with the expected name/type.
5. Consumer stats show messages dispatched, acked, or redelivered.
6. The function processes the expected schema and produces side effects.

The return value of Spring Cloud Stream's `StreamBridge.send()` is not an API that awaits a Pulsar `MessageId`. When broker-level publish visibility is needed, use callbacks/metrics/send mechanisms supported by your Pulsar binder and Spring Pulsar version, or an independent verification client. Never label a log emitted right after `StreamBridge.send()` as "broker confirmed."

### Check Connection and Namespace

Common properties:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-broker:8080
  cloud:
    stream:
      bindings:
        orders-out:
          destination: persistent://public/default/orders.events
        consumeOrder-in-0:
          destination: persistent://public/default/orders.events
          group: order-worker
~~~

The Pulsar broker URL (`pulsar://...`) differs from the admin HTTP URL. If the topic provisioner lacks permissions or the admin URL points to the wrong cluster, consumers or producers can fail at startup even though parts of the application run normally. Do not use the admin URL in place of the producer/consumer service URL.

### Query Topic Stats

~~~bash
pulsar-admin topics stats persistent://public/default/orders.events
~~~

Fields worth inspecting in the output (exact names and placement can vary across Pulsar versions):

- `msgRateIn`, `msgInCounter`, and the `publishers` list.
- `msgRateOut`, `msgOutCounter`.
- `subscriptions` and subscription names.
- `msgBacklog`, `unackedMessages`, `msgRateRedeliver` per subscription.
- `consumers`, `availablePermits`, subscription type, and active consumer.

`msgRateIn > 0` proves the broker received traffic on the topic during the observation window, but does not prove the specific event ID you are tracing was published. Combine message IDs, timestamps, and producer/consumer logs. For partitioned topics, inspect internal partitions or aggregate stats accordingly so a single partition is not overlooked.

## 15. Pulsar: Subscriptions, Cursors, and Redelivery

Pulsar does not use Kafka-style consumer group offsets in the same way. Subscriptions maintain their own cursors; different subscription names track separate reading progress.

| Observation | Possibility | Where to Check |
|---|---|---|
| Topic `msgRateIn` increases but expected subscription is missing | Consumer has not subscribed or uses another name | Check function/group, service URL, and subscription name |
| Subscription has `msgBacklog > 0` and no consumers | Consumer stopped, connection failed, or subscription failed to attach | Check consumer instances, errors, and ACLs |
| `unackedMessages` is high | Broker dispatched messages but consumer has not ACKed | Check stalled processing, ack timeout, and listener errors |
| `msgRateRedeliver` increases | Messages redelivered due to NACK/timeout/retry | Check exceptions and DLQ/retry letter topics |
| New subscription misses older events | Subscription initial position created after messages, or retention/cursor policy | Check subscription creation time and initial position |
| Another Shared consumer gets the message | Multiple consumers on the same subscription split traffic | Check `Shared`/`Key_Shared` type and consumer assignments |
| Failover consumer sits idle | This consumer is a standby on a `Failover` subscription | Identify the active consumer |
| Schema error | Producer/consumer disagree on schema or payload type | Check native binder decoding, schema registry, and exceptions |

An `Exclusive` subscription allows only one active consumer; `Failover` uses active/standby; `Shared` distributes messages without ordering guarantees; `Key_Shared` uses keys to preserve per-key ordering under supported conditions. Do not treat one specific consumer not receiving a message as an error if the broker is delivering it to another consumer under the subscription semantics.

If a subscription is created after messages were already published, initial position and retention determine whether older events are read. **Do not reset a production cursor merely for diagnostic testing**: doing so can replay or skip messages. Use a fresh diagnostic subscription with an explicit initial position and proper access permissions.

## 16. Message Reaches Consumer, but Conversion Fails

A message may be fetched/delivered yet `Consumer<T>` is never invoked because a failure happens ahead of the function, such as:

- Byte array fails to convert into a DTO per content type.
- Producer enabled native encoding while consumer mistakenly uses framework decoding, or vice versa.
- Kafka key/value deserializer is incompatible with the serializer.
- Kafka Streams `Serde` or state store schema is incompatible.
- RabbitMQ AMQP content type or message converter differs from expectations.
- Pulsar JSON/Avro/Protobuf schema and message type mismatch.
- A header mapper strips required event type, correlation ID, key, or contentType headers.
- Payload exceeds size limits or has an invalid format.

Example of a function with an explicit target type:

~~~java
@Bean
Consumer<OrderEvent> consumeOrder(OrderService orderService) {
    return event -> orderService.handle(event);
}
~~~

If the wire payload is JSON while the consumer misconfigures `content-type` or the native `Deserializer`, an error can occur in the binder before the function is invoked. Inspect application logs, binding error channels, retry counters, and DLQ/DLT. Do not place logs only inside the `Consumer` body: you need logs or metrics at the binder/container layer to detect pre-invocation errors.

### Comparing Producer and Consumer Content Configuration

| Configuration | Producer | Consumer |
|---|---|---|
| Framework JSON conversion | `content-type: application/json`, matching payload | Target type `OrderEvent`; content type propagated/interpreted properly |
| Kafka native serde | `use-native-encoding: true` + serializer | `use-native-decoding: true` + deserializer |
| Kafka Streams | Correct producer key/value serdes | Matching topology `Consumed.with(...)` or binder serde properties |
| Pulsar native schema | Matching `schema-type` and `message-type` | Compatible schema/message type |
| RabbitMQ | Appropriate AMQP headers and payload encoding | Message converter understands encoding and target type |

To isolate the issue, send a minimal JSON fixture with the simplest valid schema, test first with Test Binder to verify function conversion, and then test against a real broker to confirm wire encoding. Passing with Test Binder is not enough to rule out native serializer and broker schema issues.

## 17. Consumer Received the Message, but Business Side Effect Is Missing

Once the broker has dispatched the message and consumer logs appear, stop adjusting broker addresses or producer bindings. Investigate:

1. Did the function filter the event due to business rules or duplicate detection?
2. Did the consumer throw an exception that an error handler swallowed?
3. How many retries ran? Did the message move to a DLT/DLQ?
4. Did the DB transaction roll back after a Kafka offset or Rabbit/Pulsar ACK was already recorded?
5. Did the consumer call a downstream API asynchronously without awaiting or checking its result?
6. Did an idempotency store mark the event "processed" before the side effect actually completed?
7. Was "processed" logged before the transaction committed?

Suggested lifecycle log entries:

~~~text
event_id=evt-101 stage=consumer.received
event_id=evt-101 stage=deserialization.complete
event_id=evt-101 stage=business.started
event_id=evt-101 stage=business.committed outcome=success
event_id=evt-101 stage=message.acknowledged
~~~

You do not need to log every step at INFO under high throughput; keep INFO for errors and major state transitions and DEBUG for details. What matters is being able to reconstruct the sequence via event ID and broker metadata.

### ACK/Commit and Side Effects Are Two Separate Systems

Kafka offset commits, RabbitMQ ACKs, and Pulsar ACKs mark **consumption progress**, not database transaction commits. If you need to ensure the application does not produce duplicate side effects on retry, use an idempotency key based on `event-id`, unique constraints in the DB, or a suitable transaction/outbox/inbox strategy.

Kafka Streams' exactly-once semantics apply specifically to Kafka state and outputs; they do not automatically make an external HTTP call or external database atomic. Always state delivery guarantees per component boundary.

## 18. When the Producer Is Blocked by Resources or Network

Not every incident stems from a wrong destination. An application can still accept requests while the producer fails to complete delivery when:

- DNS or advertised listeners point to broker addresses unreachable from the container or Kubernetes Pod.
- Network policies, firewalls, TLS certificates, or SASL/ACLs fail.
- Producer buffers are full, too many in-flight requests accumulate, or timeouts occur.
- Brokers are under-replicated, out of disk, hitting quota/flow-control, or missing partition leaders.
- RabbitMQ memory/disk alarms trigger flow control and close publisher channels.
- Pulsar brokers/BookKeeper face backpressure, slow ledger writes, or topic load errors.
- Consumers are starved for CPU/threads, DB pools block, or unacked queues pile up.

Measure wait times for broker ACKs and callback failure rates. A local "accepted" log emitted before a timeout does not prove network health. Correlate client exceptions with broker logs/metrics in the same time window to separate producer, network, and broker issues.

### Uncertain State and Safe Retries

When a producer times out, the application sometimes cannot tell whether the broker persisted the record and the response was lost. This state is `unknown`, not definitively "unsent." Blind retries can create duplicates; conversely, ignoring it can lose events. Choose the right mechanism:

- Kafka idempotent producer, and transactions where appropriate and within scope.
- RabbitMQ publisher confirms/returns combined with application idempotency.
- Pulsar producer deduplication when configured on the cluster/producer.
- Transactional outbox to record publish intent alongside the database transaction.
- Consumer idempotency by event ID to handle at-least-once delivery.

Do not replay an entire topic or DLQ just because a few messages lack logs; first classify `confirmed`, `failed`, and `unknown` and reconcile by event ID.

## 19. Four Real-World Scenarios and Root-Cause Analysis

### Case A — `StreamBridge.send` Returns True, but No Kafka Record Appears

**Symptom:** API logs `accepted=true`. Kafka topic `orders.events` is empty when read with a diagnostic group.

**Hypotheses:** The application sent to a differently named dynamic binding; or the producer points to the wrong cluster; or an async send error occurred after the API returned.

**Steps:**

1. Log `bindingName` and effective `spring.cloud.stream.bindings.<name>.destination`.
2. Query `GET /actuator/bindings` to confirm the actual output binding.
3. Verify binder type and Kafka bootstrap servers.
4. Enable `recordMetadataChannel` and the producer error channel.
5. If metadata shows a different topic, fix the binding name, dynamic destination, or topic override.
6. If metadata is missing and callbacks report errors, resolve the underlying exception.
7. Only after determining the send outcome, decide whether the event needs a retry with the same event ID.

**Likely Conclusion:** The local call succeeded, but data went to `orders.event` (missing the "s") due to a dynamic binding created from a typo. Fix the configuration so `orders-out` points to `orders.events` and add an integration test checking the real topic.

### Case B — Kafka Topic Has Records, but Consumer Does Not Run

**Symptom:** Kafka producer metadata shows topic `orders.events`, partition 2, offset 1842; consumer group `order-worker` produces no logs.

**Steps:**

1. Check `/actuator/bindings/consumeOrder-in-0`; the consumer binding must be running.
2. Run `kafka-consumer-groups.sh --describe` to see if the group has members and assignments.
3. Verify the consumer destination is `orders.events`.
4. Compare the committed offset of partition 2 against offset 1842.
5. If the group already committed past that offset, inspect consumer history and the DLT rather than forcing a replay.
6. If lag is growing, inspect thread failures, deserializers, retries, and function error handlers.
7. If the group is new and sees no history, check `startOffset` and when the group was created.

**Likely Conclusion:** The consumer already read the message and routed it to the DLT after a schema error; logs appeared only in the error handler, never reaching the business function. Fix the Serde/schema or payload contract and add alerts for DLT growth.

### Case C — Rabbit Publisher Confirm ACKs, but Queue Is Empty

**Symptom:** Positive publisher confirm; queue `orders.events.order-worker` still has no messages and the consumer does not run.

**Steps:**

1. Check the exchange, routing key, and queue in the right vhost.
2. Confirm the binding between exchange and queue.
3. Inspect publisher returns; if `NO_ROUTE` appears, the broker could not route the message.
4. Check whether the queue was created after the producer published the message.
5. Check alternate exchanges, TTL, auto-delete, and DLQ.
6. After fixing bindings, publish a new diagnostic event; do not expect already-discarded messages to reappear automatically.

**Likely Conclusion:** The producer published before the consumer group's queue/binding was provisioned. The exchange accepted the publish without a target queue. The fix is to provision topology beforehand, enable confirms/returns, and define storage/retry policies when routing fails.

### Case D — Pulsar Topic Receives Messages, but Consumer Does Not See Them

**Symptom:** Topic stats show `msgRateIn > 0`; the expected subscription has no records.

**Steps:**

1. Confirm producer and consumer share the same tenant, namespace, topic, and broker cluster.
2. Check `subscriptions`, consumer list, and subscription type in topic stats.
3. Verify the subscription name generated from group/config.
4. If the subscription was created after the record was published, check initial position and retention.
5. If `msgBacklog > 0`, inspect consumer attachment and `availablePermits`.
6. If `unackedMessages` or `msgRateRedeliver` grows, look for processing/ACK failures.
7. If `Shared` or `Key_Shared`, identify which consumer the broker actually delivered the message to.

**Likely Conclusion:** Producer and consumer share the topic, but the consumer belongs to a newly created subscription starting at the latest position; older events are not replayed. Pick the right initial position in tests or provision durable subscriptions early, rather than resetting production cursors arbitrarily.

## 20. Symptom → Evidence → Where to Fix Table

| Symptom | Most Important Evidence | Priority Investigation Branch | What Not to Do Immediately |
|---|---|---|---|
| Send true, no producer ACK | Callback/error channel, broker address, timeout | Binder/producer/client | Reset consumer offsets |
| Kafka RecordMetadata has offset, probe reads nothing | Cluster, topic, partition, retention, probe group | Broker/topic/reader policy | Mass re-send |
| Kafka probe reads, app receives nothing | App binding state, group assignment, committed offset | Consumer binding/group | Change producer `acks` |
| Kafka group lag is 0, DB lacks data | Processing logs, exception handler, idempotency table | Business transaction/ACK | Conclude event was never sent |
| Rabbit confirm ACK, no queue message | Routing key, binding, returns, vhost | Exchange/queue routing | Only raise prefetch |
| Rabbit queue `ready` grows, consumers=0 | Consumer connections, queue name/group | Listener/binding startup | Send more messages |
| Rabbit unacked grows | Listener threads, ACK mode, downstream latency | Consumer processing | Delete the queue |
| Pulsar msgIn rises, no subscription | Namespace/topic and subscription list | Consumer subscription | Adjust Kafka offsets |
| Pulsar backlog grows, consumer active | Consumer permits, unacked, schema errors | Subscription/consumer pressure | Clear the backlog |
| Consumer function silent, DLQ grows | Deserialization errors, retry/DLT headers | Conversion/error handler | Drop DLQ "to test" |
| Test Binder passes, broker empty | Test classpath and binder startup logs | Tests not using real middleware | Blame the broker |

## 21. Evidence-First, Non-Mutating Diagnostic Runbook

An effective runbook keeps its initial steps **read-only**:

1. Record the incident ID, UTC timestamp, environment, event ID, and application version.

2. Confirm producer and consumer target the same cluster/vhost/namespace.

3. Check effective `function.definition`, binding names, binder, and destination.

4. Query binding status and health without START/STOP unless authorized.

5. Collect producer callback evidence: Kafka metadata, Rabbit confirm/return, Pulsar send result. Classify as `confirmed`, `failed`, or `unknown`.

6. Inspect the corresponding broker: Kafka topic/partition, Rabbit exchange/queue, Pulsar topic/subscription.

7. Confirm the consumer is registered: Kafka group assignment, Rabbit consumer count, Pulsar consumer list.

8. Inspect lag/backlog/unacked and retry/DLQ; correlate by event ID.

9. Inspect business side effects and ACK/commit status.

10. Only choose controlled remediation/replay after pinpointing the broken boundary. Record the decision, evidence, and approver.

State-changing actions such as Kafka offset resets, Pulsar cursor resets, Rabbit queue purges/deletes, partition increases, group/subscription edits, or DLQ replays must follow separate runbooks that evaluate duplicates, ordering, retention, and rollback capability.

### Sample Incident Report

~~~text
Incident ID: INC-STREAM-2026-001
Event ID: diag-order-2026-11-24-001
Environment: staging
Producer app / instance: order-api / pod-1
Consumer app / instance: order-worker / pod-2
Binding producer -> destination: orders-out -> orders.events
Binding consumer -> destination: consumeOrder-in-0 -> orders.events
Broker and cluster: kafka / staging-kafka
Producer local accepted: true
Broker confirm: topic=orders.events, partition=2, offset=1842
Broker probe: record exists
Consumer group: order-worker
Consumer partition assignment: partition 2 -> pod-2
Lag / backlog: 0
Business side effect: missing
Observed first missing evidence: business commit
Next investigation: conversion/error handler, idempotency, DB transaction
Owner and action: assigned to consumer service team
~~~

This template focuses investigation on the consumer rather than repeatedly sending test events to the same topic.

## 22. Testing to Prevent Recurrence

### Layer 1 — Unit Tests

Verify `Supplier`/`Function`/`Consumer` logic, event ID stability, payload/headers, and exception handling:

- Local send logs `accepted_locally`, never `broker_confirmed`.
- When `StreamBridge.send` returns `false` or throws an exception, code handles it properly.
- When the business function throws an exception, errors are not swallowed outside retry policy.
- Idempotency prevents duplicate side effects when an event is redelivered.

### Layer 2 — Spring Integration Test Binder

Use `InputDestination`/`OutputDestination` to verify function bindings, conversion, headers, and dynamic routing. Test Binder is fast, but it does not test Kafka broker ACKs, Rabbit routing/confirms, or Pulsar subscriptions.

### Layer 3 — Real Binder + Testcontainers

Start a real broker in integration tests to confirm the end-to-end path from producer to consumer over the network. A test can:

1. Send an event with a unique ID via `StreamBridge`.
2. Await the broker publisher outcome when the binder supports callbacks.
3. Verify topic/queue/subscription shows receipt of the message.
4. Wait for the consumer function to write the event ID to a test sink or test database.
5. Assert the side effect occurred once per contract, or verify idempotency on redelivery.
6. Cover wrong destination, missing route, schema errors, consumer restarts, and DLQ cases.

Example Kafka test container configuration via `@DynamicPropertySource`:

~~~java
@Testcontainers
@SpringBootTest
class OrderDeliveryIntegrationTest {

    @Container
    static final KafkaContainer KAFKA =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                KAFKA::getBootstrapServers);
    }

    // Create an event with a unique ID, send via StreamBridge,
    // verify the broker record, and await consumer business outcome.
}
~~~

This is a skeleton; add JUnit/Testcontainers imports, real Kafka binder configuration, function beans, producer callbacks, and assertions. Image/version are illustrative; pin a broker version compatible with your project. **Do not include `spring-cloud-stream-test-binder` in real-broker integration test modules** if the mock binder could claim the bindings.

### Fault Testing Matrix

| Scenario | Test Evidence to Verify |
|---|---|
| Wrong destination | Callback/metadata reports the actual topic; dashboard detects binding mismatch |
| Broker unreachable | Async failure/timeout is recorded; broker success is not logged |
| Kafka topic missing ACL | Producer reports authorization error; no false success state created |
| Kafka group already committed | Consumer does not replay unless policy requires it |
| Rabbit has no matching queue binding | Returned message/NO_ROUTE observed when mandatory/return are configured |
| Rabbit queue has no consumers | Queue ready count grows and consumer count is 0 |
| Pulsar wrong subscription | Topic msgIn grows while expected subscription receives nothing |
| Consumer deserialization error | Errors/retries/DLQ appear; business function is not treated as successful |
| Crash after DB commit before broker ACK | Redelivery is handled idempotently |
| Test Binder runs only in-JVM | Tests distinguish simulated outcomes from real brokers |

## 23. Preventive Design for Production

Measures to reduce the risk of recurrence:

- **Log by confirmation milestone:** local accepted, producer confirmed/failed, consumer received, business committed, and acknowledged.
- **Observable broker acknowledgments:** Kafka record metadata, Rabbit confirms/returns, and Pulsar publish results/metrics.
- **Explicit destinations/groups:** avoid relying on accidental defaults; review binding names, binder names, and environment overlays.
- **Track consumer progress:** lag/backlog/unacked, retries, DLQs, and binding health.
- **Standardize schemas and content types:** maintain producer/consumer contract tests and real-binder integration tests.
- **Idempotent consumers:** use event IDs as keys to prevent duplicate side effects during retries/replays.
- **Transactional outbox/inbox where appropriate:** bridge the gap between DB commits and publishing/consuming events.
- **Latency- and ratio-based alerts:** detect when producer accepted grows while broker confirmed lags, or broker intake rises while business completion stalls.
- **Bound retries and preserve poison messages:** configure DLQs with safe inspection/replay procedures.
- **Control access:** secure Actuator and broker inspection tools; never log sensitive payloads.

You cannot build an "exactly-once delivery across all side effects" guarantee from a single boolean returned by a send API. Delivery assurance is an end-to-end contract from producer to broker, broker to consumer, and consumer to storage, paired with handling for uncertain states.

## 24. Checklist Before Closing an Incident

- [ ] Correlated event ID, UTC timestamp, and exact environment.
- [ ] Producer and consumer use the same broker cluster/vhost/namespace.
- [ ] Function definition and binding names match the running application.
- [ ] Explicitly noted that `StreamBridge.send` status is not a broker ACK.
- [ ] Checked producer error channels and callbacks/confirms.
- [ ] For Kafka, obtained topic/partition/offset from `RecordMetadata` or a reliable probe.
- [ ] For Kafka, checked group assignment, committed offsets, and per-partition lag.
- [ ] For RabbitMQ, checked exchange, queue, routing, confirms/returns, and unacked counts.
- [ ] For Pulsar, checked topic, publishers, subscriptions, backlog, and redeliveries.
- [ ] Checked conversion/schema/Serde before concluding the consumer did not receive the message.
- [ ] Checked retries, DLT/DLQ, transactions, and business side effects.
- [ ] Avoided blind offset/cursor resets, queue purges, or blind replays during diagnosis.
- [ ] Root cause assigned to the exact layer with supporting evidence.
- [ ] Re-tested with a fresh diagnostic event after applying the fix.
- [ ] Evaluated duplicates, ordering, idempotency, and compensating data needs.
- [ ] Added alerts or regression tests to catch recurrence.

## Summary

In Spring Cloud Stream, an accepted send call inside the application is only **one link** in the delivery chain. To diagnose "sent successfully locally, but broker or consumer has not received the data," look for the **first missing piece of evidence**: producer confirmation, broker record/queue/topic, consumer registration and assignment, deserialized data, business side effect, or commit/ACK.

Kafka requires checking `RecordMetadata`, topic/partition/offset, group, and committed offsets. RabbitMQ requires checking publisher confirms **and** returned messages, exchange/queue bindings, and consumer ACKs. Pulsar requires checking message publish results, topic stats, subscription cursors, backlog, and redeliveries. With stable event IDs, visibility into async states, and real-broker tests, you can fix the exact failing layer without accidentally dropping or duplicating events.

## References

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Binding Properties and Producer Error Channel](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder and Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [Spring Cloud Stream — RabbitMQ Publisher Confirms and Error Channels](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream — Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [RabbitMQ — Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Exchanges and Routing](https://www.rabbitmq.com/tutorials/amqp-concepts)
- [Apache Pulsar — Topic and Subscription Statistics](https://pulsar.apache.org/docs/4.2.x/administration-stats/)
- [Spring Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
