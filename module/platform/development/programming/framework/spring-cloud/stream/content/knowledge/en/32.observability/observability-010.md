# Structured Logging with Event IDs, Correlation IDs, and Broker Metadata

In a Spring Cloud Stream application, an event can traverse multiple functions, bindings, binders, and brokers before completing its business flow. When an error occurs, a log line merely stating "processing failed" is rarely enough to locate the exact message among millions of records. Logs need to indicate which event was being processed, which business flow it belonged to, which broker and partition it traversed, how many times it was redelivered, and which step failed.

Structured logging solves this by using consistently named and typed fields, typically emitted as JSON. `event-id`, `correlation-id`, `causation-id`, `trace-id`, and broker metadata link logs by event, by business journey, and by technical execution.

This lesson explains how to design a logging contract, propagate IDs via message headers, place data into MDC/structured logging, extract metadata from Kafka, RabbitMQ, or Pulsar, and verify logs in deployment environments.

## 1. From plain-text logs to structured logs

Plain-text logs typically combine multiple pieces of information into a single sentence:

~~~text
Received order order-101 from kafka partition 2 offset 1842
~~~

A human reader can understand that sentence, but log systems struggle to filter accurately if the topic name, partition, or event ID shifts position or format. Structured logging represents each value as a distinct field:

~~~json
{
  "@timestamp": "2026-11-24T08:30:00Z",
  "log.level": "INFO",
  "service.name": "order-enricher",
  "message": "order event received",
  "event_id": "evt-01JDC8K5P3",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-01JDC8JYQ1",
  "broker": "kafka",
  "destination": "orders.created",
  "partition": 2,
  "offset": 1842
}
~~~

A log platform can filter `event_id` with an exact match, group by `destination`, count errors by `broker`, or locate every processing step sharing the same `correlation_id`. Each field has a uniform meaning, so dashboards, alerts, and queries do not need to parse free-form strings.

## 2. Distinguishing types of IDs

Do not use one ID for every purpose. The following IDs have different lifecycles and meanings:

| ID | Meaning | Lifecycle | Example |
|---|---|---|---|
| `event_id` | Unique identifier of a business event. | Remains unchanged when the event is retried, resent, or reprocessed. | `evt-01JDC8K5P3` |
| `correlation_id` | Groups events and processing steps belonging to the same business journey. | Can span multiple services and multiple messages. | `checkout-7842` |
| `causation_id` | Indicates which event directly caused the current event. | Changes along the causal chain between events. | `evt-01JDC8JYQ1` |
| `message_id` | Transport-layer message identifier provided by the application or broker. | Depends on the broker and publish/redelivery behavior. | Kafka record metadata, RabbitMQ message ID, Pulsar message ID. |
| `trace_id` | Identifier of a distributed trace in the tracing system. | Scoped to a trace; may differ from the long lifecycle of a business process. | 32-hex-character W3C Trace ID. |
| `span_id` | Identifier of a specific operation within a trace. | Each service or operation creates its own span. | 16-hex-character W3C Span ID. |

**Event ID** identifies the business event content, such as `OrderCreated`, `PaymentAuthorized`, or `InventoryReserved`. Producers should generate the ID once when creating the event and keep it unchanged when resending the same event. Consumers can use this ID as an idempotency key. Generating a new ID on every retry makes it hard for consumers to recognize redeliveries of the same event.

**Correlation ID** links related events across a long-running journey. One checkout might produce `OrderCreated`, `PaymentRequested`, `PaymentAuthorized`, and `ShipmentRequested`. Those events have different event IDs but share the same correlation ID. The ID is normally created at the entry boundary of the business flow; if an incoming message already carries a valid correlation ID, downstream services continue using it.

**Causation ID** records the event that directly triggered a new event. For example, `PaymentAuthorized` can carry a causation ID equal to the event ID of `PaymentRequested`. This field helps reconstruct causal chains when workflows branch or execute asynchronously.

**Trace ID and Span ID** belong to distributed tracing. A trace can contain many spans across HTTP, message brokers, and services. Correlation ID carries business semantics and often outlives a single trace; do not replace correlation ID with trace ID or vice versa. A workflow lasting several hours may spawn a fresh trace on each processing step while keeping the original correlation ID.

**Broker message ID** or record position identifies a specific delivery on the broker. Kafka uses topic, partition, and offset; RabbitMQ has a message ID if set by the producer and a channel-scoped delivery tag; Pulsar has a broker-assigned message ID. These values do not replace event ID because they have separate scopes and lifecycles.

## 3. Business header conventions

Standardize header names across services exchanging events:

| Header | Data type | Rule |
|---|---|---|
| `event-id` | String | Required for business events; preserved across retries. |
| `correlation-id` | String | Required for workflows needing cross-service tracing. |
| `causation-id` | String | May be empty for root events; points to the event that caused the current event. |
| `event-type` | String | Event type name, e.g., `OrderCreated`. |
| `schema-version` | String or integer | Payload contract version. |
| `traceparent` | String | W3C trace context when supported by tracing and the binder. |

Header names form part of the application contract; use consistent spelling and data types in both producers and consumers. Avoid naming custom headers `id`, `timestamp`, `ID`, or `Id`: Spring Messaging reserves system headers with those names and some binders apply special mapping rules. Use `event-id` to distinguish the business ID from the framework's internal message ID.

Do not cram entire business objects into headers. Headers are meant for IDs, event types, versions, and short metadata. Business data belongs in the payload; broker headers often have size limits and distinct serialization rules.

## 4. Attaching IDs to messages in the producer

Spring Cloud Stream allows producers to emit `Message<T>` instead of only the raw payload. Custom headers can be set with `MessageBuilder`:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderCreated(
        String orderId,
        String eventId,
        String correlationId,
        String causationId) {
}

@Configuration
class OrderEventConfiguration {

    @Bean
    Function<OrderCreated, Message<OrderCreated>> publishOrderCreated() {
        return event -> MessageBuilder
                .withPayload(event)
                .setHeader("event-id", event.eventId())
                .setHeader("correlation-id", event.correlationId())
                .setHeader("causation-id", event.causationId())
                .setHeader("event-type", "OrderCreated")
                .setHeader("schema-version", "1")
                .build();
    }
}
~~~

In real applications, IDs are usually created in the event-emitting layer or domain event publisher. Do not regenerate the event ID inside each binder resend. When a service emits a new event after handling an input event, the new event receives a new event ID and a causation ID pointing to the input event ID.

~~~text
OrderCreated
  event-id       = evt-order-101
  correlation-id = checkout-7842
  causation-id   = checkout-command-7842

PaymentRequested
  event-id       = evt-payment-202
  correlation-id = checkout-7842
  causation-id   = evt-order-101
~~~

## 5. Reading IDs and logging in the Consumer

Consumers can accept `Message<T>` to access both payload and headers together. Use the SLF4J 2 fluent logging API to attach key/value pairs to log events:

~~~java
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderConsumerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerConfiguration.class);

    @Bean
    Consumer<Message<OrderCreated>> consumeOrderCreated(OrderService service) {
        return message -> {
            String eventId =
                    message.getHeaders().get("event-id", String.class);
            String correlationId =
                    message.getHeaders().get("correlation-id", String.class);
            String causationId =
                    message.getHeaders().get("causation-id", String.class);

            try (
                    MDC.MDCCloseable eventContext =
                            eventId == null ? null
                                    : MDC.putCloseable("event_id", eventId);
                    MDC.MDCCloseable correlationContext =
                            correlationId == null ? null
                                    : MDC.putCloseable(
                                            "correlation_id", correlationId)
            ) {
                log.atInfo()
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("causation_id", causationId)
                        .log("order event received");

                service.handle(message.getPayload());

                log.atInfo()
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("outcome", "success")
                        .log("order event processed");
            }
            catch (RuntimeException ex) {
                log.atError()
                        .setCause(ex)
                        .addKeyValue("operation", "order.consume")
                        .addKeyValue("event_id", eventId)
                        .addKeyValue("correlation_id", correlationId)
                        .addKeyValue("outcome", "failure")
                        .addKeyValue("exception_type",
                                ex.getClass().getName())
                        .log("order event processing failed");
                throw ex;
            }
        };
    }
}
~~~

`MDC.putCloseable` adds IDs to the thread's diagnostic context and automatically removes them when the try block ends. Cleaning up context is critical because consumer threads are typically reused for the next message. Leaving old IDs behind can stamp the wrong correlation ID onto a subsequent message's logs.

The example above logs on receipt, on success, and on failure. The exception is rethrown so Spring Cloud Stream/the binder can execute configured retries or error handling; logging the error does not mean message handling is finished.

If a required ID is missing from a message, log a warning with `outcome=missing_required_header`, destination, and binding name, then apply the application's contract policy. Never synthesize a new event ID on the consumer side to hide a producer bug, as doing so breaks idempotency and traceability.

## 6. Enabling structured logging in Spring Boot

Spring Boot supports JSON log output in popular formats such as ECS, GELF, and Logstash in versions supporting structured logging. The example below uses ECS:

~~~yaml
spring:
  application:
    name: order-enricher

logging:
  structured:
    format:
      console: ecs
      file: ecs
    ecs:
      service:
        name: order-enricher
        version: "1.4.0"
        environment: production
~~~

Key/value pairs added via the SLF4J fluent API and values in MDC are included in the JSON output. When using a custom Logback or Log4j2 configuration, configure Spring Boot's corresponding encoder/layout so it honors the structured format property; setting the property alone while a custom encoder ignores it can leave logs in plain text.

If your log ingestion pipeline expects Logstash JSON, you can set:

~~~yaml
logging:
  structured:
    format:
      console: logstash
      file: logstash
~~~

Pick one consistent log schema across the environment. Do not let service A emit `event_id`, service B emit `eventId`, and service C emit `event-id` when all three represent the same concept.

### JSON log example

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.123Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.OrderConsumerConfiguration"
  },
  "service": {
    "name": "order-enricher",
    "version": "1.4.0",
    "environment": "production"
  },
  "message": "order event received",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-checkout-001",
  "operation": "order.consume",
  "broker": "kafka",
  "destination": "orders.created",
  "consumer_group": "order-enricher"
}
~~~

Exact field names depend on the format and rename/add/exclude settings. Finalize a shared schema for your logging platform before building dashboards and alerts.

## 7. Fields to include in log events

Not every log line needs every field. Define a common schema and add metadata tailored to each operation type.

| Group | Suggested fields | Purpose |
|---|---|---|
| Timing | `@timestamp`, `duration_ms` | Ordering events and measuring processing time. |
| Service | `service.name`, `service.version`, `environment`, `instance_id` | Identifying the emitting service and instance. |
| Operation | `operation`, `message`, `outcome`, `stage` | Knowing whether publishing, receiving, processing, retrying, or dead-lettering. |
| Event | `event_id`, `event_type`, `schema_version` | Identifying the business event and data contract. |
| Relationships | `correlation_id`, `causation_id` | Linking workflows and causal relationships. |
| Trace | `trace_id`, `span_id` | Opening the corresponding distributed trace. |
| Broker | `broker`, `destination`, `consumer_group` or `subscription` | Identifying the middleware and intake stream. |
| Position | `partition`, `offset`, `routing_key`, `message_id` | Locating a specific message inside the broker. |
| Delivery | `redelivered`, `delivery_attempt`, `redelivery_count`, `ack_mode` | Analyzing retries and duplicates. |
| Error | `exception_type`, `error_code`, `error_category` | Classifying errors without parsing stack traces. |

Keep field names consistent and values properly typed. For instance, partition, offset, and duration_ms are numbers; event_id, correlation_id, and destination are strings; redelivered is a boolean.

Never log the full payload or the entire headers map. Payloads can contain personal data, payment details, or secrets; headers can carry tokens, credentials, or internal routing data. Allowlist only operationally useful fields, cap lengths, and mask sensitive data before logging.

## 8. Broker metadata is not business metadata

Each broker has its own identification and delivery concepts. When logging, preserve the original semantics of each piece of metadata:

| Broker | Useful metadata | Meaning |
|---|---|---|
| Kafka | Topic, partition, offset, record key, timestamp, consumer group | Record position in the partitioned log and processing consumer group. |
| RabbitMQ | Exchange, routing key, queue, message ID, correlation ID, delivery tag, redelivered | Routing path and channel-level delivery state. |
| Pulsar | Topic, message ID, key, publish time, event time, producer name, redelivery count, schema version | Message identifier and subscription dispatch/redelivery info. |

Do not assume all binders map broker metadata to the exact same Spring header names. Binders have their own header mappers, type conversions, and properties. Verify actual headers for your binder and version before building field mappings.

## 9. Logging Kafka metadata

Spring Kafka provides headers in `KafkaHeaders` to access metadata of an incoming record:

| Header | Data |
|---|---|
| `KafkaHeaders.RECEIVED_TOPIC` | Topic from which the record was received. |
| `KafkaHeaders.RECEIVED_PARTITION` | Partition of the record. |
| `KafkaHeaders.OFFSET` | Offset within the partition. |
| `KafkaHeaders.RECEIVED_KEY` | Record key if present. |
| `KafkaHeaders.RECEIVED_TIMESTAMP` | Record timestamp. |
| `KafkaHeaders.RECORD_METADATA` | Metadata of a successful send, when using a producer metadata channel. |

Example Consumer receiving `Message` and logging metadata:

~~~java
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

void logKafkaRecord(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "kafka")
            .addKeyValue("destination",
                    headers.get(KafkaHeaders.RECEIVED_TOPIC))
            .addKeyValue("partition",
                    headers.get(KafkaHeaders.RECEIVED_PARTITION))
            .addKeyValue("offset",
                    headers.get(KafkaHeaders.OFFSET))
            .addKeyValue("record_key",
                    headers.get(KafkaHeaders.RECEIVED_KEY))
            .addKeyValue("broker_timestamp",
                    headers.get(KafkaHeaders.RECEIVED_TIMESTAMP))
            .log("kafka record received");
}
~~~

### Metadata on successful publish

The Kafka binder supports `recordMetadataChannel` on output bindings. Configure a channel to receive send results:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrderCreated-out-0:
            producer:
              record-metadata-channel: kafkaSendResults
~~~

The `kafkaSendResults` channel must exist in the application context. Messages sent to this channel carry the `KafkaHeaders.RECORD_METADATA` header containing `RecordMetadata`, which includes the topic, partition, and offset where the record was written.

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;

void logKafkaSendResult(Message<?> result) {
    RecordMetadata metadata = result.getHeaders()
            .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);

    if (metadata != null) {
        log.atInfo()
                .addKeyValue("broker", "kafka")
                .addKeyValue("destination", metadata.topic())
                .addKeyValue("partition", metadata.partition())
                .addKeyValue("offset", metadata.offset())
                .log("kafka record published");
    }
}
~~~

This metadata proves the broker acknowledged the write under the configured producer semantics. If sending fails, the binder uses the producer error channel when configured; never log a record as successfully published merely because the function built a message or called send.

### Header mappers and special headers

The Kafka binder maps Spring message headers to Kafka record headers. In modern Kafka versions, custom headers generally pass through naturally; a custom `KafkaHeaderMapper` or `headerPatterns` can alter which headers are transmitted. `id` and `timestamp` are special framework headers and are not mapped like ordinary custom headers by default.

Therefore:

- Use `event-id` and `correlation-id` for business metadata.
- If a custom header mapper is configured, include required business headers in the mapper.
- Verify data types when converting between `byte[]` and `String`.
- Do not log raw Kafka headers or the full `ConsumerRecord`; extract only needed fields.
- Log the consumer group from binding configuration or deployment context; do not assume it is always present as a message header.

## 10. Logging RabbitMQ metadata

RabbitMQ uses exchanges, routing keys, and queues. Spring AMQP maps these details into `AmqpHeaders`:

| Header | Data |
|---|---|
| `AmqpHeaders.RECEIVED_EXCHANGE` | Exchange that received the message. |
| `AmqpHeaders.RECEIVED_ROUTING_KEY` | Routing key used to route the message. |
| `AmqpHeaders.MESSAGE_ID` | Message ID if set by the producer. |
| `AmqpHeaders.CORRELATION_ID` | AMQP correlation ID if set by the producer. |
| `AmqpHeaders.DELIVERY_TAG` | Delivery tag of the message delivery on the channel. |
| `AmqpHeaders.CONSUMER_TAG` | Consumer tag receiving the message. |
| `AmqpHeaders.REDELIVERED` | Flag indicating the broker marked the message as redelivered. |

Example:

~~~java
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.Message;

void logRabbitDelivery(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "rabbitmq")
            .addKeyValue("exchange",
                    headers.get(AmqpHeaders.RECEIVED_EXCHANGE))
            .addKeyValue("routing_key",
                    headers.get(AmqpHeaders.RECEIVED_ROUTING_KEY))
            .addKeyValue("message_id",
                    headers.get(AmqpHeaders.MESSAGE_ID))
            .addKeyValue("amqp_correlation_id",
                    headers.get(AmqpHeaders.CORRELATION_ID))
            .addKeyValue("delivery_tag",
                    headers.get(AmqpHeaders.DELIVERY_TAG))
            .addKeyValue("consumer_tag",
                    headers.get(AmqpHeaders.CONSUMER_TAG))
            .addKeyValue("redelivered",
                    headers.get(AmqpHeaders.REDELIVERED))
            .log("rabbit message delivered");
}
~~~

`delivery_tag` is meaningful only within the current channel and is not a durable message ID. Never use delivery tag as `event_id` or an idempotency key. `redelivered` is a broker redelivery signal, not a total attempt count; if you need to count dead-letter/requeue cycles, inspect `x-death` metadata per RabbitMQ configuration and log selected values.

With the RabbitMQ binder, queues and exchanges are created based on destination/group and binder properties. Log `destination`, group, and routing key to identify the path. `consumerTagPrefix` helps identify consumers inside the broker; this is consumer configuration, not a business ID.

If the application needs publisher confirms, log from the actual confirmation mechanism such as `confirmAckChannel` or correlation data headers/confirm futures. Calling `StreamBridge.send` or creating a message does not by itself prove the broker confirmed the publish.

## 11. Logging Pulsar metadata

Pulsar has message metadata and user properties. Spring for Apache Pulsar provides `PulsarHeaders`; the Pulsar binder converts required metadata between Pulsar messages and Spring Messaging.

Commonly useful fields:

| Header | Data |
|---|---|
| `PulsarHeaders.MESSAGE_ID` | Pulsar-assigned message ID. |
| `PulsarHeaders.TOPIC_NAME` | Topic name. |
| `PulsarHeaders.KEY` | Message key if present. |
| `PulsarHeaders.PUBLISH_TIME` | Publish timestamp. |
| `PulsarHeaders.BROKER_PUBLISH_TIME` | Broker publish timestamp if available. |
| `PulsarHeaders.EVENT_TIME` | Event time set by the producer. |
| `PulsarHeaders.PRODUCER_NAME` | Producer name. |
| `PulsarHeaders.REDELIVERY_COUNT` | Redelivery count tracked by the broker. |
| `PulsarHeaders.SCHEMA_VERSION` | Message schema version. |
| `PulsarHeaders.SEQUENCE_ID` | Producer sequence ID. |

Example extracting values for logging:

~~~java
import org.springframework.messaging.Message;
import org.springframework.pulsar.support.PulsarHeaders;

void logPulsarDelivery(Message<OrderCreated> message) {
    var headers = message.getHeaders();

    log.atInfo()
            .addKeyValue("broker", "pulsar")
            .addKeyValue("destination",
                    headers.get(PulsarHeaders.TOPIC_NAME))
            .addKeyValue("message_id",
                    headers.get(PulsarHeaders.MESSAGE_ID))
            .addKeyValue("message_key",
                    headers.get(PulsarHeaders.KEY))
            .addKeyValue("publish_time",
                    headers.get(PulsarHeaders.PUBLISH_TIME))
            .addKeyValue("event_time",
                    headers.get(PulsarHeaders.EVENT_TIME))
            .addKeyValue("producer_name",
                    headers.get(PulsarHeaders.PRODUCER_NAME))
            .addKeyValue("redelivery_count",
                    headers.get(PulsarHeaders.REDELIVERY_COUNT))
            .addKeyValue("schema_version",
                    headers.get(PulsarHeaders.SCHEMA_VERSION))
            .log("pulsar message delivered");
}
~~~

Exact package names and available headers depend on the Spring for Apache Pulsar/Pulsar binder version. Use `PulsarHeaders` from your application's actual dependency and verify the binder's header mapper before deploying.

The Pulsar binder has a default `PulsarHeaderMapper` and allows replacing it with a custom mapper. If a mapper only permits certain patterns, `event-id`, `correlation-id`, or `causation-id` headers might not pass through. When using a JSON header mapper, deserialize objects only from trusted packages; never open trusted packages broadly for broker-supplied data.

## 12. Retry, redelivery, and dead-letter logs

An event may be delivered multiple times due to transient errors, timeouts, process restarts, or incomplete acknowledgments. Logs should distinguish:

- **Attempt:** the application's current processing attempt.
- **Redelivery:** the broker delivering a previously delivered message again.
- **Retry:** the application or binder scheduling another processing attempt.
- **Dead-letter:** the message moving to an error destination after exhausting retry policies or being rejected.

Example operations:

| Operation | Fields to log | When |
|---|---|---|
| `message.received` | `event_id`, `correlation_id`, broker metadata, attempt/redelivered | When the consumer receives a message. |
| `message.processed` | IDs, `outcome=success`, `duration_ms` | When business processing completes. |
| `message.retry_scheduled` | IDs, `delivery_attempt`, `retry_delay_ms`, `exception_type` | When a retry is scheduled. |
| `message.failed` | IDs, `outcome=failure`, `exception_type`, `error_code` | When the current attempt fails. |
| `message.dead_lettered` | IDs, source destination, DLQ destination, redelivery count | When moving the message to DLQ/DLT. |
| `message.published` | IDs, destination, and broker publish metadata | When the broker confirms publish. |

`event_id` and `correlation_id` should remain constant across retries. `delivery_attempt` or `redelivery_count` changes according to the binder/broker mechanism. Do not infer retry count from a boolean `redelivered` flag alone; RabbitMQ has `x-death` for dead-letter cycles, Pulsar has redelivery count, and Kafka retry/DLT can use topics/headers and metadata provided by the binder or application.

When logging errors, record `exception_type`, error code, operation, and IDs. Stack traces may be needed for unexpected errors, but never embed the full payload inside exception messages if payloads contain sensitive data.

## 13. Tracing and correlation in Spring Cloud Stream

Spring Cloud Stream integrates observability via Micrometer. For imperative functions, when required tracing/observation dependencies are present, the framework can create an observation for each function invocation. For reactive functions, the function builds the pipeline once, and per-element observation must be placed inside the reactive chain using the appropriate observation API.

Common dependencies in a Spring Boot application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

You can use another tracing bridge matching your platform. Configure an exporter/reporter if shipping traces to a backend such as Zipkin or OpenTelemetry Collector.

When Micrometer Tracing is enabled, Spring Boot populates `traceId` and `spanId` into MDC; structured logging can emit these fields alongside log events. This represents the current trace, while `event-id` and `correlation-id` remain application-managed business headers.

Example baggage configuration:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-context
      correlation:
        fields:
          - tenant-context
~~~

Baggage suits a small set of short metadata that must travel with a trace and is configured to propagate across instrumented transports. Do not use baggage as a dumping ground for every event header; specifically, never put sensitive data, payloads, or long ID lists into baggage. With message brokers, confirm that the binder and instrumentation actually propagate trace context via message headers.

The Kafka binder has `spring.cloud.stream.kafka.binder.enableObservation` to enable observation on its bindings. Defaults and observation support vary by binder/version; check documentation for your exact binder rather than assuming all brokers enable tracing identically.

### Reactive functions and context propagation

MDC is typically thread-bound. In reactive pipelines, callbacks can execute across different threads; calling `MDC.put` on one thread does not ensure the value appears on another thread. Use Micrometer Context Propagation/Observation or Reactor context propagation as configured.

For reactive functions in Spring Cloud Stream, observability guidance requires attaching observations to the pipeline segment you want to measure, such as with `tap(Micrometer.observation(registry))`. Without per-segment observation, logs may still appear while traces fail to represent individual messages as intended.

## 14. Never let MDC pollute the next message's logs

MDC is typically stored per thread, and consumer threads are reused. Always restore or clear context:

~~~java
String previousEventId = MDC.get("event_id");
try {
    MDC.put("event_id", eventId);
    process(event);
}
finally {
    if (previousEventId == null) {
        MDC.remove("event_id");
    }
    else {
        MDC.put("event_id", previousEventId);
    }
}
~~~

`MDC.putCloseable` with try-with-resources is usually cleaner when adding only a few fields. If managing the MDC map manually, restore prior values instead of always calling `clear()` on the entire context, because the tracing framework may hold `traceId`/`spanId` in the same context.

For `@Async`, custom executors, or callbacks running on other threads, configure appropriate context propagation or task decorators. Never assume MDC transfers automatically across every executor, scheduler, or reactive boundary.

## 15. Designing logs around the message lifecycle

Logging too little makes investigations hard; logging every detail at every step raises storage costs and noise. A practical convention:

| Log level | Usage |
|---|---|
| `ERROR` | Unrecoverable message failure, configuration error, broker error, or unexpected error requiring action. |
| `WARN` | Message missing a required header, retries exceeding threshold, unusual redeliveries, or fallback triggered. |
| `INFO` | Major business state transitions such as publish/consume completion, DLQ routing, or processing status changes. |
| `DEBUG` | Detailed per-message metadata on high-volume flows during investigations. |
| `TRACE` | Very fine-grained details like conversion steps or header mapping during diagnostics. |

For high-volume systems, you can sample success logs while keeping all error and DLQ logs. Sampling must preserve queryability by `event_id` or `correlation_id` for selected events; do not sample in a way that drops logs mid-workflow during an investigation.

Do not use logs in place of metrics. Throughput, consumer lag, retry rate, processing latency, and DLQ rate belong in metrics; logs retain details of individual executions or state transitions.

## 16. Avoiding logging sensitive data and untrusted headers

Message brokers are boundaries receiving data from other systems. Headers and payloads may be controlled by external producers. Before logging them:

- Allowlist permitted headers: event ID, correlation ID, event type, schema version, and essential broker metadata.
- Never log access tokens, authorization headers, passwords, cookies, API keys, or raw credentials.
- Never log payment payloads, personal data, or confidential content; use non-sensitive business IDs if identification is needed.
- Bound string lengths and strip control characters to prevent log injection.
- Never serialize entire header objects or native broker records.
- Normalize `event_type`, `destination`, and `error_code` to avoid excessive cardinality.
- Never use `event_id`, `correlation_id`, or `message_id` as metric labels; high-cardinality IDs belong in logs/traces.

If using a Pulsar custom JSON header mapper or Kafka custom header mapper, map only known headers with explicit deserialization rules. Never deserialize arbitrary classes from external messages.

## 17. Testing structured logs

Log tests should verify both content and context cleanup:

1. On a valid message, logs contain `event_id`, `correlation_id`, `operation`, and destination.
2. On successful processing, logs contain `outcome=success` and processing duration.
3. On failed processing, logs contain `outcome=failure`, `exception_type`, and still rethrow exceptions per retry policy.
4. When a message lacks required IDs, a warning is logged and the defined contract policy runs.
5. After processing completes, the thread's MDC no longer holds the previous message's `event_id` or `correlation_id`.
6. Kafka logs include topic/partition/offset; RabbitMQ logs include exchange/routing key/delivery metadata; Pulsar logs include topic/message ID/redelivery metadata when those headers are present.
7. Log output parses as JSON with fields retaining proper data types.
8. No sensitive payloads or credentials appear in logs.

### Checking JSON logs

You can run tests with structured logging enabled and parse output with a JSON parser in your test harness or CI. Assert on individual fields rather than comparing whole log lines verbatim, as timestamps, PIDs, thread names, and trace IDs change between runs.

### Testing header round-trip

For each binder, send a message carrying `event-id`, `correlation-id`, and `causation-id`, consume it on the other side, and verify values arrive intact. Tests should run against a real binder if the goal is verifying header mappers and broker serialization.

For Kafka, test both header mappers and reserved headers. For RabbitMQ, test AMQP header mapping and routing metadata. For Pulsar, test `PulsarHeaderMapper`, schemas, and user properties for your binder version.

## 18. Example cross-service log records

Suppose checkout creates an order and emits `OrderCreated`. `order-enricher` receives the event, enriches it, and emits `OrderEnriched`. The logs can share the same correlation ID while having distinct event IDs:

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.100Z",
  "service.name": "order-service",
  "message": "order event published",
  "operation": "order.publish",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "cmd-checkout-7842",
  "event_type": "OrderCreated",
  "broker": "kafka",
  "destination": "orders.created",
  "outcome": "success"
}
~~~

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.140Z",
  "service.name": "order-enricher",
  "message": "order event received",
  "operation": "order.consume",
  "event_id": "evt-order-101",
  "correlation_id": "checkout-7842",
  "causation_id": "cmd-checkout-7842",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "broker": "kafka",
  "destination": "orders.created",
  "partition": 2,
  "offset": 1842,
  "consumer_group": "order-enricher"
}
~~~

~~~json
{
  "@timestamp": "2026-11-24T08:30:00.170Z",
  "service.name": "order-enricher",
  "message": "enriched order published",
  "operation": "order.publish",
  "event_id": "evt-order-enriched-102",
  "correlation_id": "checkout-7842",
  "causation_id": "evt-order-101",
  "event_type": "OrderEnriched",
  "broker": "kafka",
  "destination": "orders.enriched",
  "outcome": "success"
}
~~~

When investigating checkout, search `correlation_id=checkout-7842` to see all related services and events. When investigating duplicates of a single event, search `event_id=evt-order-101`. When investigating a specific Kafka record, combine topic, partition, and offset.

## 19. Common issues

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Consumer does not see `event-id` | Producer did not attach header or custom header mapper stripped it. | Inspect producer message and mappers on both sides. |
| `Id` header disappears through Kafka | Collides with Spring Messaging's reserved `id` header. | Use `event-id`; custom-map legacy headers only if required by contract. |
| Subsequent message logs carry old correlation ID | MDC was not cleaned up after processing or exception path skipped cleanup. | Use `MDC.putCloseable` or `try/finally`. |
| Trace ID exists but event ID is missing | Automatic tracing does not generate business IDs. | Propagate `event-id` and `correlation-id` via message headers. |
| Correlation ID changes after retry | Producer or retry handler generates a new ID. | Keep correlation ID and event ID unchanged for the same event. |
| Kafka log lacks offset | Logging before receiving record metadata or using the wrong header. | Read `KafkaHeaders.OFFSET` in consumers; use `recordMetadataChannel` in producers. |
| Rabbit delivery tag used as event ID | Confusing channel-scoped metadata with a business ID. | Keep event ID separate; log delivery tag only to trace the current delivery. |
| Pulsar missing redelivery count | Binder/header mapper version omits that header or message was not redelivered. | Check `PulsarHeaders` and mapper for your running version. |
| JSON logs missing MDC | Custom logging encoder/layout does not support structured format or MDC. | Configure Spring Boot's matching encoder/layout. |
| Logs too large and hard to query | Logging full payloads/headers or too many dynamic fields. | Allowlist fields, cap sizes, and standardize schema. |
| Trace fails to cross reactive pipeline | MDC/thread-local does not follow Reactor context or observation was not attached. | Use Micrometer Context Propagation/Observation and instrument reactive segments. |
| Metrics dashboard has too many series | Using event ID, message ID, or correlation ID as metric tags. | Move high-cardinality IDs to logs/traces; keep metric tags bounded. |

## 20. Pre-deployment checklist

- [ ] Consistent convention exists for `event-id`, `correlation-id`, `causation-id`, `event-type`, and `schema-version`.
- [ ] `event-id` stays constant across retries and redeliveries of the same event.
- [ ] Correlation ID is preserved across services in the same workflow.
- [ ] Causation ID points to the event that directly caused the new event.
- [ ] Trace ID and Span ID are kept distinct from business IDs.
- [ ] JSON structured logging is enabled with a unified schema.
- [ ] Logs include service, environment, operation, outcome, and timestamp.
- [ ] Logs capture only allowlisted headers and essential broker metadata.
- [ ] Kafka logs include topic/partition/offset/key when metadata is present.
- [ ] RabbitMQ logs include exchange/routing key/message ID/redelivery metadata when present.
- [ ] Pulsar logs include topic/message ID/key/publish time/redelivery count when present.
- [ ] Consumer group or subscription is recorded from configuration/deployment context.
- [ ] MDC is cleaned after each message and propagated properly across async/reactive boundaries.
- [ ] Retry, failure, and dead-letter logs include event ID, attempt, and error category.
- [ ] Payloads, tokens, credentials, and sensitive data are excluded from logs.
- [ ] Event ID and correlation ID are never used as high-cardinality metric labels.
- [ ] Tested JSON parsing, header round-trip, and MDC cleanup.

Structured logging gives Spring Cloud Stream operations visibility into both the business journey and the message's broker position. `event-id` identifies a single event, `correlation-id` links workflows, `causation-id` describes causality, and `trace-id`/`span-id` tie logs to distributed traces. Combining these IDs with Kafka topic/partition/offset, RabbitMQ exchange/routing key, or Pulsar message ID/redelivery count enables operations teams to locate exact messages, understand retries, and pinpoint failing services without logging full payloads.

## References

- [Spring Boot — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing and Log Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Cloud Stream — Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Apache Pulsar — Message Consumption and Headers](https://pulsar.apache.org/pulsar-spring/reference/pulsar/message-consumption.html)
- [SLF4J — MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html)
