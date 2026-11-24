# Log group id and listener id

When operating a Spring Kafka application, a log like “received record” is rarely enough to determine which consumer actually processed the data. A topic can be read independently by multiple consumer groups; each group in turn has multiple members, listener containers, and Kafka clients. If logs record only topic and offset, operations cannot easily tell which **business processing stream** the record belongs to, which container owns the partition, or why one group lags while another remains healthy.

Two identifiers must be distinguished: **Kafka group id** and **Spring Kafka listener id**. Group ID identifies the consumer group in Kafka, affecting partition assignment and committed offsets. Listener ID identifies the endpoint/container inside the Spring application, supporting lifecycle management, event observation, and correlating logs with a specific listener. There are also **client ID**, **pod/instance ID**, and **listener info**; each serves a distinct purpose and cannot substitute for another.

This lesson belongs to the **Logging and Diagnostics** chapter of Spring Kafka Reliability Operations. Its goal is designing logs with enough context to investigate consumer groups, listener containers, concurrency, rebalances, lag, retries, and DLTs without exposing sensitive data or exploding metric cardinality.

## 1. Distinguishing identifier types

| Identifier | Scope | Who uses it? | Primary role |
|---|---|---|---|
| **group.id** | Kafka consumer group | Kafka broker and consumer client | Groups consumer members together; manages assignment and committed offsets. |
| **listener id** | Spring application context | Spring Kafka container/registry and app | Identifies endpoint/container for logging, lifecycle management, and event correlation. |
| **client.id** | Kafka client instance | Kafka client, broker logs, and metrics | Identifies a client for observability, quotas, or diagnostics. |
| **pod/instance id** | Runtime/deployment | Kubernetes, logging/monitoring | Distinguishes replicas running the same service. |
| **listener info** | Application-set metadata | Spring Kafka message headers/listener | Attaches custom metadata to records when received by the listener. |
| **event id** | Business | Application and downstream | Identifies the same event across retries, DLTs, and replays. |

Example of a service running three replicas, each with one listener at concurrency two:

~~~text
Deployment: orders-service
  Pod A
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-a-0
    client.id      = orders-client-a-1

  Pod B
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-b-0
    client.id      = orders-client-b-1

  Pod C
    group.id       = orders-validation-v1
    listener id    = orders-listener
    client.id      = orders-client-c-0
    client.id      = orders-client-c-1
~~~

Client names above are illustrative. Spring Kafka/Kafka clients may generate or suffix client IDs depending on concurrency configuration. The key point is that **the same group ID and listener ID can appear across many pods**, whereas client ID should distinguish individual Kafka client instances.

## 2. group.id is the Kafka consumer group identifier

Kafka uses `group.id` to identify consumers participating in one group. Consumers in the same group share partition assignments of subscribed topics. Each group maintains its own committed offsets.

Example topic `orders` with three partitions:

~~~text
Topic: orders

partition 0  ------------------+
partition 1  ------------------+----> group.id = orders-validation-v1
partition 2  ------------------+

                              Consumer members:
                                member A
                                member B
~~~

If a group has two members and three partitions, Kafka assigns partitions to members according to the assignor and group state. At any moment, one partition belongs to only one consumer member within the same group under standard group subscription.

Another consumer group can read the same topic independently:

~~~text
                    Topic: orders
                    /           \
                   /             \
                  v               v
       group.id = validation   group.id = analytics
          |                         |
          v                         v
    Validate orders            Build reports
    separate committed offsets separate committed offsets
~~~

This means:

- Two services needing to **read the same stream independently** typically use different group IDs.
- Multiple replicas sharing one workload typically use the same group ID to split partitions.
- Accidentally changing group ID makes Kafka treat it as a brand-new group; the consumer may start per `auto.offset.reset` without prior committed offsets.
- If two listener containers share the same group ID and subscribe to the same topic, they join the same group and split work instead of each receiving every record.

**Group ID is part of delivery behavior**, not merely a log label. Changing group ID can cause data to be re-read or skipped depending on offset state and reset config.

## 3. listener id is the Spring Kafka endpoint/container identifier

The `id` attribute of `@KafkaListener` identifies the listener endpoint/container inside the Spring application context. The application can use this ID to:

- Retrieve the container via `KafkaListenerEndpointRegistry`.
- Pause/resume or stop/start the container by listener.
- Correlate application events with the listener.
- Distinguish listeners within the same service in logs and dashboards.
- Apply operational configurations or policies per endpoint.

Example:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
        id = "orders-created-listener",
        topics = "orders.created",
        groupId = "orders-validation-v1"
    )
    public void onOrderCreated(String payload) {
        orderService.validate(payload);
    }
}
~~~

In this example:

- `orders-validation-v1` is the Kafka group ID.
- `orders-created-listener` is the Spring listener ID.

These two values serve two different identity systems. Changing listener ID for container management does not create a new consumer group if group ID stays unchanged. Changing group ID can alter the offset namespace and partition assignment even if listener ID stays the same.

**Listener ID should be stable and unique within one Spring application context.** Across multiple pods in the same deployment, sharing the same listener ID is normal because each pod has its own application context. Logs must add pod/instance ID to distinguish running instances.

## 4. Relationship between @KafkaListener id, groupId, and idIsGroup

`@KafkaListener` has important attributes:

| Attribute | Meaning |
|---|---|
| `id` | ID of the listener endpoint/container. |
| `groupId` | Overrides group ID for the listener, corresponding to consumer `group.id`. |
| `idIsGroup` | Controls using `id` as group ID when `groupId` is not declared; typically defaults to `true`. |
| `clientIdPrefix` | Prefix for the listener's Kafka client ID; useful to distinguish clients and concurrency members. |
| `topics` / `topicPattern` | Topics or pattern the listener subscribes to. |
| `containerFactory` | Factory creating the listener container. |

Explicit declaration example:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    idIsGroup = false,
    clientIdPrefix = "orders-validation-client",
    topics = "orders.created"
)
public void onOrder(String payload) {
    orderService.validate(payload);
}
~~~

When `groupId` is specified, that is the group ID the listener uses. `idIsGroup` mainly matters when `groupId` is omitted: by default, the listener ID can be used as the group ID; set `idIsGroup = false` to avoid using ID as group ID and let the consumer factory supply the configured group ID.

Example when wanting group ID from the consumer factory:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    idIsGroup = false,
    topics = "orders.created"
)
public void onOrder(String payload) {
    orderService.validate(payload);
}
~~~

In that case, make sure the consumer factory has an appropriate `group.id`, such as via Spring Boot properties. Otherwise, the consumer may lack a valid group ID as required by application configuration.

**Do not let `idIsGroup` and `groupId` become undocumented implicit configuration.** In services with multiple listeners, declaring group ID explicitly generally makes logs, operations, and reviews clearer.

## 5. Group ID configuration sources and override order

A Spring Boot application can set a default group ID for the consumer factory:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-validation-v1
      enable-auto-commit: false
~~~

A specific listener can override it via `groupId`:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void onOrder(String payload) {
    // ...
}
~~~

If no group ID is set on the annotation, the listener uses the consumer factory's group ID according to configuration rules and `idIsGroup`. Also inspect custom consumer properties in factories; do not check only `application.yml` if the app defines multiple `ConsumerFactory` beans.

Another configuration may live in Java:

~~~java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-validation-v1");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

DefaultKafkaConsumerFactory<String, String> consumerFactory =
        new DefaultKafkaConsumerFactory<>(props);
~~~

When investigating, record the **effective group ID** of the running consumer rather than guessing from a single config file. Annotation overrides, custom factory beans, or profile properties can make runtime values differ from defaults.

## 6. group.id vs. client.id

These two names often appear near each other in Kafka logs yet mean different things.

| Characteristic | group.id | client.id |
|---|---|---|
| Represents | Consumer group | A single Kafka client instance |
| Used for | Assignment, group membership, and offsets | Metrics, logs, quotas/diagnostics |
| Shared across members? | Yes, that defines a group. | Usually needs to distinguish each client instance for observability. |
| Impact of changing | Creates a new group/offset namespace, changes assignment. | Renames identifier/metrics; does not create a new group. |
| Should contain pod ID? | Usually no, if replicas must share one group. | Can use a pod/instance suffix. |

Example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-validation-v1
      client-id: orders-validation-client
~~~

If multiple consumer clients exist in one application, ensure client IDs can be distinguished in metrics/logs. Spring Kafka may append concurrency suffixes depending on config; verify actual runtime names rather than assuming the final string always matches the prefix verbatim.

Never set group ID to `orders-validation-pod-a`, `orders-validation-pod-b` if the goal is for pods to share one workload. Doing so creates independent groups, and each group may read the entire stream on its own offsets.

## 7. Stable naming conventions

Good IDs help on-call engineers recognize the service and processing flow immediately. One convention you can use:

~~~text
group.id:
  <domain>-<purpose>-v<generation>

listener id:
  <topic-or-domain>-<handler>-listener

client.id prefix:
  <service>-<consumer-role>-client

pod/instance:
  <deployment-pod-name>
~~~

Examples:

| Type | Example name | Rationale |
|---|---|---|
| group ID | `orders-validation-v1` | Expresses domain and workload; stable across replicas. |
| listener ID | `orders-created-listener` | Logs immediately show the endpoint handling orders.created. |
| client ID prefix | `orders-validator-client` | Groups Kafka client metrics/logs. |
| pod ID | `orders-service-7c9d8-p2x4m` | Distinguishes physical instances. |

Avoid putting build numbers or pod IDs into group ID unless intentionally creating a new group. Changing group ID on every deploy can create new groups, abandon prior committed offsets, and start reading per `auto.offset.reset`.

If migrating to a new group ID is required, plan clearly for:
- Starting offset of the new group.
- Records that may be reprocessed.
- Impact on side effects and idempotency.
- Timing of traffic cutover and stopping the old group.
- Ability to roll back to the previous group.

## 8. Logging group ID and listener ID inside listener methods

A useful log identifies both the processing stream and record position:

~~~java
private static final String GROUP_ID = "orders-validation-v1";
private static final String LISTENER_ID = "orders-created-listener";

@KafkaListener(
    id = LISTENER_ID,
    groupId = GROUP_ID,
    topics = "orders.created"
)
public void onOrder(ConsumerRecord<String, String> record) {
    log.info(
        "Kafka record received: groupId={}, listenerId={}, " +
        "topic={}, partition={}, offset={}, key={}",
        GROUP_ID,
        LISTENER_ID,
        record.topic(),
        record.partition(),
        record.offset(),
        record.key());

    orderService.validate(record.value());
}
~~~

Recommended fields:
- `groupId`: which group is processing the record.
- `listenerId`: which endpoint/container received the record.
- `topic`, `partition`, `offset`: exact position in Kafka.
- `key`: log only if keys contain no sensitive data.
- `eventId`: business identifier if available.
- `pod`/`instance`: which replica actually executed it.
- `attempt`/`deliveryAttempt`: delivery pass if the error handler supplies reliable metadata.

In the example, Java constants are shared with the annotation to avoid logging a different group ID than the listener actually uses. If group ID comes from profile/environment, inject the same configuration property into both the annotation and logging component rather than hardcoding two separate values.

**ConsumerRecord does not inherently carry group ID inside the raw Kafka record.** Group ID is consumer group metadata, not a field producers attach to each message. Do not confuse `record.headers()` with the effective group ID.

## 9. Using MDC so group ID and listener ID appear in every log

If every log inside a listener invocation needs group ID and listener ID, place them in **Mapped Diagnostic Context (MDC)**:

~~~java
private static final String GROUP_ID = "orders-validation-v1";
private static final String LISTENER_ID = "orders-created-listener";

@KafkaListener(
    id = LISTENER_ID,
    groupId = GROUP_ID,
    topics = "orders.created"
)
public void onOrder(ConsumerRecord<String, String> record) {
    try (MDC.MDCCloseable group =
                 MDC.putCloseable("kafka.group.id", GROUP_ID);
         MDC.MDCCloseable listener =
                 MDC.putCloseable("kafka.listener.id", LISTENER_ID)) {

        MDC.put("kafka.topic", record.topic());
        MDC.put("kafka.partition", Integer.toString(record.partition()));
        MDC.put("kafka.offset", Long.toString(record.offset()));

        try {
            log.info("Start processing order");
            orderService.validate(record.value());
            log.info("Order processed");
        } finally {
            MDC.remove("kafka.topic");
            MDC.remove("kafka.partition");
            MDC.remove("kafka.offset");
        }
    }
}
~~~

Key imports:

~~~java
import org.slf4j.MDC;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
~~~

`MDC.putCloseable(...)` removes the corresponding keys when the scope closes. Topic/partition/offset keys are removed in `finally` so they do not leak to the next record on the same consumer thread.

Kafka listener threads are usually reused. Setting MDC without cleanup causes subsequent record logs to carry stale offsets or group IDs, misleading incident investigations.

You can standardize a helper:

~~~java
public final class KafkaLogContext implements AutoCloseable {

    public KafkaLogContext(
            String groupId,
            String listenerId,
            String topic,
            int partition,
            long offset) {

        MDC.put("kafka.group.id", groupId);
        MDC.put("kafka.listener.id", listenerId);
        MDC.put("kafka.topic", topic);
        MDC.put("kafka.partition", Integer.toString(partition));
        MDC.put("kafka.offset", Long.toString(offset));
    }

    @Override
    public void close() {
        MDC.remove("kafka.group.id");
        MDC.remove("kafka.listener.id");
        MDC.remove("kafka.topic");
        MDC.remove("kafka.partition");
        MDC.remove("kafka.offset");
    }
}
~~~

Usage:

~~~java
try (KafkaLogContext ignored = new KafkaLogContext(
        GROUP_ID,
        LISTENER_ID,
        record.topic(),
        record.partition(),
        record.offset())) {

    orderService.validate(record.value());
}
~~~

This helper is illustrative code; in real applications consider preserving existing MDC context if multiple layers write keys. One option is using `MDC.putCloseable` individually per key with nested scopes.

## 10. Configuring the logging pattern

With Logback, you can include MDC keys in the pattern:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] traceId=%X{traceId} groupId=%X{kafka.group.id} listenerId=%X{kafka.listener.id} topic=%X{kafka.topic} partition=%X{kafka.partition} offset=%X{kafka.offset} - %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This is an example Logback configuration. If your project uses a JSON encoder or structured logging, emit MDC keys as separate fields rather than concatenating them into a hard-to-query string.

A formatted log line after configuration may look like:

~~~text
2026-11-15 18:30:12.123 INFO [KafkaListenerEndpointContainer#0-0-C-1]
traceId=4bf92f... groupId=orders-validation-v1
listenerId=orders-created-listener topic=orders.created
partition=2 offset=1875 - OrderListeners - Start processing order
~~~

Thread names are illustrative. Do not rely on thread names to deduce group ID or listener ID; log each identifier explicitly.

## 11. Injecting group ID via listener header when needed

In some Spring Kafka versions, `KafkaHeaders.GROUP_ID` can be used to receive the group ID as a method argument when the listener adapter supplies it. Check your running version's API:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void onOrder(
        ConsumerRecord<String, String> record,
        @Header(KafkaHeaders.GROUP_ID) String groupId) {

    log.info("Processing with groupId={}", groupId);
}
~~~

Imports:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
~~~

If your version or adapter does not supply this header, do not try reading group ID from `ConsumerRecord`. Use known listener config or consumer metadata supported by the framework. With listeners using different group IDs, maintain a clear mapping configuration object instead of guessing from topic names.

Another diagnostic option is injecting the consumer via `KafkaHeaders.CONSUMER` in supported versions and calling `consumer.groupMetadata().groupId()` **on the listener thread**. Consumer objects are not thread-safe; never store them in singletons or pass them to executors for use after the method returns.

## 12. listenerInfo is not listener id

Spring Kafka has a **listener info** concept configurable on container properties and added to record headers per supported version APIs. This is application-defined metadata, not synonymous with `@KafkaListener(id=...)` and not a Kafka group ID.

Example:

~~~java
factory.getContainerProperties()
       .setListenerInfo("orders-validation-pipeline");
~~~

The listener can receive this metadata via `KafkaHeaders.LISTENER_INFO` when supported by config/version:

~~~java
public void onOrder(
        ConsumerRecord<String, String> record,
        @Header(KafkaHeaders.LISTENER_INFO) String listenerInfo) {

    log.info("listenerInfo={}", listenerInfo);
}
~~~

Distinction:

| Value | Source | Purpose |
|---|---|---|
| `@KafkaListener(id=...)` | Endpoint annotation | Container management and listener identification. |
| `groupId` | Annotation or consumer factory | Kafka group membership and offsets. |
| `listenerInfo` | `ContainerProperties` | Custom metadata passed to listener/messages. |

Never put secrets, tokens, or personal data into listener info. Because it may enter message headers or logs depending on usage, restrict its content and control propagation through retries/DLT.

## 13. Finding a listener container by listener id

`KafkaListenerEndpointRegistry` retrieves containers by listener ID. That is a practical reason listener IDs must remain stable:

~~~java
@Service
public class OrderListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener orders-created-listener not found");
        }

        container.pause();
    }

    public void resumeOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-created-listener");

        if (container == null) {
            throw new IllegalStateException(
                    "Listener orders-created-listener not found");
        }

        container.resume();
    }
}
~~~

Key imports:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;
~~~

The registry is scoped to the current Spring application context. In multi-pod deployments, calling the registry on Pod A **does not control containers on Pod B**. To operate deployment-wide, coordinate commands across instances or use a desired-state/control plane.

When a listener uses concurrency, the registry typically returns the parent container for the listener; child containers manage individual consumer threads. Never assume listener ID equals child container ID or a single partition.

## 14. Using listener id when handling application events

Spring Kafka publishes several events carrying container/listener info. For instance, `NonResponsiveConsumerEvent`, idle events, pause/resume events, or stopped events can expose the listener ID via the corresponding API.

Example:

~~~java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onNonResponsive(NonResponsiveConsumerEvent event) {
        log.warn(
            "Non-responsive consumer: listenerId={}, elapsedMs={}, partitions={}",
            event.getListenerId(),
            event.getTimeSinceLastPoll(),
            event.getTopicPartitions());
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.warn(
            "Kafka consumer stopped: listenerId={}, reason={}",
            event.getListenerId(),
            event.getReason());
    }
}
~~~

Exact imports and event fields may vary by Spring Kafka version; check the class API you use before copying code into a project. The example illustrates the main point: **listener ID correlates events with the endpoint/container**. Group ID and pod ID should be logged additionally if the event does not supply them directly.

An event listener should run quickly: log, update metrics, or enqueue data for incident handlers. Never make long HTTP calls or synchronous database transactions inside event callbacks.

## 15. Logging group/listener in retries and DLT

When a listener hits errors, the same event can appear across multiple attempts or topics:

~~~text
orders.created
    |
    v
orders-created-listener
    |
    +-- attempt 1: exception
    |
    v
retry topic / blocking retry
    |
    +-- attempt 2: exception
    |
    v
DLT
~~~

Logs should distinguish:
- **Group ID of the consumer reading the current topic.** The consumer group reading a retry topic may differ from the main topic's group.
- **Listener ID of the current endpoint.** The retry/DLT listener may be a separate endpoint.
- **Original topic/partition/offset** of the source record.
- **Current topic/partition/offset** of the current delivery.
- **Delivery attempt/recovery metadata** from the error handler.
- **Stable event ID** to identify the same business event.

Structured log example:

~~~json
{
  "event": "kafka_record_recovered",
  "groupId": "orders-retry-v1",
  "listenerId": "orders-retry-listener",
  "topic": "orders-retry-1000",
  "partition": 1,
  "offset": 902,
  "originalTopic": "orders.created",
  "originalPartition": 2,
  "originalOffset": 1875,
  "eventId": "order-4821-created",
  "attempt": 3
}
~~~

This JSON is an illustrative log schema. Exact header metadata depends on the recoverer and version. Do not assume every DLT consumer uses the original listener's group ID or listener ID; it may be an independent consumption pipeline.

Whether retries use the same consumer group or a different one affects assignments and offsets. Configure clearly and log the **actual group reading the retry topic** instead of only logging the initial stream's group ID.

## 16. Group ID and listener ID with multiple listeners

An application can host multiple listeners:

~~~java
@KafkaListener(
    id = "orders-created-listener",
    groupId = "orders-validation-v1",
    topics = "orders.created"
)
public void validateOrder(String payload) {
    // ...
}

@KafkaListener(
    id = "payments-created-listener",
    groupId = "payments-risk-v1",
    topics = "payments.created"
)
public void evaluatePayment(String payload) {
    // ...
}
~~~

Here the two listeners have distinct IDs and group IDs. Logs must distinguish them even when running inside the same pod.

Another case is two listeners subscribing to the same topic with the same group ID:

~~~java
@KafkaListener(
    id = "orders-handler-a",
    groupId = "orders-shared-v1",
    topics = "orders"
)
public void handleA(String payload) {
    // ...
}

@KafkaListener(
    id = "orders-handler-b",
    groupId = "orders-shared-v1",
    topics = "orders"
)
public void handleB(String payload) {
    // ...
}
~~~

Both endpoints join the same consumer group per subscription and container config; they do not automatically create two independent copies of the entire stream. If business logic requires both handlers to receive every record, use separate group IDs or an appropriate fan-out pattern.

**Do not use listener ID to infer group ID when annotations override it.** Always inspect effective group ID in config or runtime metadata.

## 17. Group ID and client ID in Kafka logs

Kafka broker/client logs commonly include group ID, member ID, client ID, generation, or coordinator details. During group rebalances, logs may show:
- Member join/leave.
- Partition assignment/revocation.
- Heartbeat or poll timeouts.
- Offset commit failures.
- Consumer fenced or coordinator unavailable.

To correlate with application logs, maintain a consistent mapping:

~~~text
service       = orders-service
pod           = orders-service-7c9d8-p2x4m
group.id      = orders-validation-v1
listener.id   = orders-created-listener
client.id     = orders-validation-client-0
topic         = orders.created
partition     = 2
offset        = 1875
~~~

The Kafka broker does not necessarily know the Spring listener ID because it is application-side metadata. `client.id` and group ID are what the Kafka client includes in logs/protocol as applicable. Thus, to link broker logs with Spring containers, log listener ID in the app and join across sources using pod/client ID.

## 18. Diagnostic log levels

When investigating listener lifecycle or consumer groups, raise log levels within limits:

~~~yaml
logging:
  level:
    org.springframework.kafka.listener: DEBUG
    org.springframework.kafka.config: DEBUG
    org.apache.kafka.clients.consumer: INFO
~~~

`DEBUG` can produce heavy volume under high traffic; enable only during investigation and consider per-pod log levels. For group coordination issues, you may need targeted Kafka client log levels depending on version, but never leave the entire `org.apache.kafka` package at `TRACE` long-term.

Log levels do not replace metrics:
- Logs provide details of a specific assignment, error, or record.
- Metrics show trends in lag, throughput, rebalances, and failure rates.
- Traces link processing steps across services.
- Group ID/listener ID serve as correlation keys tying those sources together.

## 19. Structured log design

A log record should have stable, meaningful fields with bounded cardinality:

| Field | Data type | Guidance |
|---|---|---|
| `service` | Service name | Application name. |
| `instance` | Pod/host | Runtime value distinguishing replicas. |
| `groupId` | Kafka group | Stable per workload. |
| `listenerId` | Spring endpoint | Stable per listener. |
| `clientId` | Kafka client | Useful to join client metrics/logs. |
| `topic` | Topic | Topic name. |
| `partition` | Integer | Partition being processed. |
| `offset` | Long | Record position. |
| `eventId` | Business identifier | Used for audit/deduplication; avoid as metric label if cardinality is high. |
| `attempt` | Integer | Delivery/retry count if backed by accurate metadata. |
| `traceId` | Trace identifier | Correlates distributed traces; does not replace event ID. |
| `outcome` | Enum | `success`, `failure`, `recovered`, `dlt`. |

Do not log:
- Passwords, SASL secrets, TLS private keys, or access tokens.
- Full payloads when containing personal/financial data.
- Headers containing credentials or uncontrolled baggage.
- Event IDs, order IDs, or user IDs as unbounded metric labels.
- Group IDs generated dynamically per request.

Logs with proper context let you locate the right consumer without opening payloads.

## 20. Metric labels: are group ID and listener ID suitable?

Group ID and listener ID usually have relatively low cardinality when named stably, making them suitable metric labels in many systems. Still, control the total count of listeners/groups and avoid minting new IDs per deployment/request.

Example application metrics:
- `app.kafka.listener.records.processed`
- `app.kafka.listener.processing.duration`
- `app.kafka.listener.errors`
- `app.kafka.listener.rebalances`
- `app.kafka.listener.nonresponsive.events`

These names are instrumentation examples, not mandatory default Spring Kafka metric names.

Labels can include:
- `group_id`
- `listener_id`
- `topic` (if topic count is governed)
- `outcome`
- `application`

Never put `partition`, `offset`, `event_id`, `order_id`, `trace_id`, or payloads into metric labels if they can create millions of series. Those belong in logs or traces.

When multiple pods share group ID/listener ID, aggregate metrics naturally roll up by workload; add `instance` when diagnosing a specific replica, mindful of series scaling with pod count.

## 21. Using group ID/listener ID when investigating lag

Lag is typically observed per consumer group and topic-partition. Looking only at a topic cannot reveal which group is falling behind since multiple groups maintain separate committed offsets.

Example:

~~~text
Topic: orders, partition 2

group.id = orders-validation-v1
  committed offset = 1800
  log end offset   = 2000
  lag              = 200

group.id = orders-analytics-v1
  committed offset = 1950
  log end offset   = 2000
  lag              = 50
~~~

The validation group is lagging more than analytics. To pinpoint which listener is responsible, cross-check group ID against listener ID and pod/assignment logs.

Group inspection command:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-validation-v1
~~~

To inspect members and assignments, pass the flags matching your Kafka CLI version:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --describe \
  --group orders-validation-v1 \
  --members --verbose
~~~

The CLI displays group, member, offset, and lag info per version capabilities; **it does not inherently know Spring listener IDs**. To map a partition owner to a listener, join with application logs/metrics.

## 22. Common naming and configuration mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Every pod reprocesses the whole topic | Group ID includes a pod suffix, turning each pod into an isolated group. | Share one group ID for workloads meant to split partitions. |
| Renaming listener ID makes consumer re-read from start | `idIsGroup=true` and group ID omitted so ID became group ID. | Declare group ID explicitly or set `idIsGroup=false` to use factory group ID. |
| Two listeners do not each receive a copy of every record | Sharing group ID and subscribing to the same topic splits assignments. | Use separate group IDs for independent fan-out. |
| Container not found in registry | Wrong listener ID or listener disabled/configured without creating container. | Verify `@KafkaListener(id=...)` and application context. |
| Pods' logs cannot be told apart | Logging only group ID and listener ID without instance/pod. | Add pod/instance ID and client ID. |
| Broker logs lack listener ID | Listener ID is Spring application-side metadata. | Log both listener ID and client ID/group ID to join sources. |
| Metrics have too many time series | Using event ID, offset, or dynamic partitions as labels. | Move high-cardinality details to logs/traces. |
| Next record log carries previous record's offset | MDC not cleaned up on reused consumer thread. | Use scope/try-finally and remove MDC keys. |
| Retry/DLT logs carry wrong group | Logging original listener's group instead of the group reading retry/DLT. | Log effective group of each endpoint. |

## 23. Runbook: unknown which listener is consuming a partition

Suppose Kafka CLI shows `orders-2` belongs to a member of group `orders-validation-v1`, yet the app team has not identified which listener processes it.

**Step 1 — Verify the group.** Run consumer group describe and record group ID, member/client ID, host, and partition assignment.

**Step 2 — Locate the pod.** Match client ID, host, or member metadata to a pod/instance in Kubernetes and log aggregation.

**Step 3 — Locate the listener ID.** Search structured logs on that pod around the same time for `groupId=orders-validation-v1`, `topic=orders`, `partition=2`, and listener ID.

**Step 4 — Inspect the container.** Verify the listener ID exists in `KafkaListenerEndpointRegistry`, whether the container is running or paused, and actual concurrency.

**Step 5 — Verify configuration.** Check `@KafkaListener(id, groupId, idIsGroup, clientIdPrefix)` and consumer factory to see where runtime group ID comes from.

**Step 6 — Check lag/processing.** Compare committed offset, throughput, listener errors, retries/DLT, and dependency latency.

**Step 7 — Remediate on the right endpoint.** If pausing/resuming is needed, call the container by listener ID on the right instance/owner or via a deployment-wide control plane.

**Step 8 — Confirm.** Observe updated assignments, logs with clear identifiers, and advancing offsets.

Never deduce listener ID from group ID by splitting strings or guessing naming conventions; the relationship must be explicit in config/logging.

## 24. Runbook: new consumer group appears after deployment

A deployment can accidentally create a new group if group ID was derived from listener ID or a property changed.

1. Compare actual group IDs before/after deployment in Kafka CLI and logs.
2. Check annotation `groupId`, `idIsGroup`, consumer factory defaults, and profiles/environments.
3. Check whether the new group already has committed offsets; if not, check `auto.offset.reset`.
4. Assess whether the new group is re-reading all historical data or starting from latest offsets.
5. If the group ID change was unintentional, fix configuration to restore the old group ID deliberately; avoid running both groups concurrently and causing duplicate side effects.
6. If the group ID migration is intentional, define start offset, replay semantics, idempotency, and when to stop the old group.
7. Monitor lag and business effects across both old/new groups during transition.

**Do not delete the old group or reset offsets immediately upon spotting a new group.** First understand what data was processed, which consumers remain active, and whether the system can replay safely.

## 25. Implementation checklist

- [ ] Each listener has a stable, unique `id` within its application context.
- [ ] Each workload has a business-named group ID stable across replicas.
- [ ] `@KafkaListener.groupId` and consumer factory defaults follow clear override rules.
- [ ] `idIsGroup` is understood so listener ID never creates a new group ID accidentally.
- [ ] `client.id`/`clientIdPrefix` distinguishes Kafka client instances.
- [ ] Logs include group ID, listener ID, instance/pod, topic, partition, and offset.
- [ ] MDC keys are cleaned up so they never leak between records.
- [ ] Retry/DLT logs record the group ID and listener ID of the endpoint actually reading that topic.
- [ ] Event/registry operations use listener ID without confusing it with group ID.
- [ ] Metric labels have controlled cardinality.
- [ ] Credentials, sensitive payloads, and unnecessary metadata are never logged.
- [ ] Runbooks exist mapping Kafka group member/client IDs to pods and listener containers.
- [ ] A clear plan exists before changing group IDs or replaying data.

## 26. Conclusion

**Group ID and listener ID answer two different questions.** Group ID tells which Kafka consumer group a consumer belongs to, how partitions are shared, and where committed offsets live. Listener ID tells which endpoint/container in the Spring application does the work and serves as the key for container management and application event correlation.

By logging both alongside client ID, pod/instance, topic-partition-offset, and event ID, operations can bridge Kafka group metadata with Spring listener logs without mixing up identities. Stable naming, explicit group IDs, MDC cleanup, and controlled metric cardinality accelerate rebalance, lag, retry, and DLT investigations while preventing accidental group changes that alter delivery behavior.
