# Adding Metadata or Trace Context

A Kafka record can carry metadata alongside its key and payload via **headers**. Applications often use headers to pass `correlation-id`, event type, schema version, tenant, or trace context between producers and consumers. Spring Kafka also provides `ProducerInterceptor`, `RecordInterceptor`, `KafkaHeaderMapper`, and Micrometer Observation to standardize adding, reading, and observing metadata in the messaging pipeline.

It is important to distinguish business metadata from trace context. `correlation-id` helps link operations belonging to the same business request; `traceparent` and `tracestate` carry information following distributed tracing standards. Both can be used on the same record, but one value should not be used arbitrarily as a substitute for the other.

## 1. How do Kafka headers store data?

A Kafka record consists of topic, partition, offset, key, value, timestamp, and headers. Each header has a name and a `byte[]` value. A record can contain multiple headers with the same name, so when reading you must explicitly decide whether to take the first value, the last value, or all values.

Example of an order event:

```text
Topic: order-events
Key:   order-42
Value: { "orderId": "order-42", "status": "CONFIRMED" }
Headers:
  event-type       = OrderConfirmed
  schema-version   = 2
  correlation-id   = req-8f31
  tenant-id        = tenant-17
  traceparent      = 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

Headers fit auxiliary information for routing, tracing, schema compatibility, or cross-service processing. The payload should hold the primary business data. The key is typically used to determine the partition and maintain ordering per entity; do not cram all metadata into the key because doing so affects partitioning.

Some common metadata names:

| Header | Purpose | Example |
|---|---|---|
| `correlation-id` | Link operations of the same business request | `req-8f31` |
| `event-type` | Identify the event type | `OrderConfirmed` |
| `schema-version` | Identify the payload structure version | `2` |
| `tenant-id` | Distinguish tenants in multi-tenant apps | `tenant-17` |
| `traceparent` | Carry trace context per W3C Trace Context | `00-...-...-01` |
| `tracestate` | Carry tracing vendor extension state | `vendor=value` |

Headers are not automatically encoded as Strings or JSON by Kafka. Applications must agree on encoding between producer and consumer; the common choice for text metadata is UTF-8.

## 2. Adding metadata when sending with KafkaTemplate

When adding metadata per event, the most direct way is creating a `ProducerRecord`, adding headers, and sending via `KafkaTemplate`:

```java
ProducerRecord<String, OrderConfirmed> record =
        new ProducerRecord<>("order-events", event.orderId(), event);

record.headers()
        .add("event-type", "OrderConfirmed".getBytes(StandardCharsets.UTF_8))
        .add("schema-version", "2".getBytes(StandardCharsets.UTF_8))
        .add("correlation-id", correlationId.getBytes(StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

The producer sends header values as bytes. Key and value serializers still operate separately; a JSON payload serializer does not automatically decide the header format.

If the application already uses Spring Messaging `Message`, metadata can be added with `MessageBuilder`:

```java
Message<OrderConfirmed> message = MessageBuilder
        .withPayload(event)
        .setHeader("event-type", "OrderConfirmed")
        .setHeader("schema-version", "2")
        .setHeader("correlation-id", correlationId)
        .build();

kafkaTemplate.send(message);
```

With this approach, the converter's `KafkaHeaderMapper` is responsible for mapping `MessageHeaders` to Kafka headers. Sending with `ProducerRecord` is useful when exact byte control is needed or when communicating with non-Spring consumers.

## 3. Reading metadata on the consumer

When receiving a `ConsumerRecord`, read headers by name. Since a header may be missing or have multiple values, handle missing cases and pick the appropriate read method:

```java
@KafkaListener(topics = "order-events", groupId = "order-projection")
public void consume(ConsumerRecord<String, OrderConfirmed> record) {
    Header header = record.headers().lastHeader("correlation-id");

    String correlationId = header == null
            ? null
            : new String(header.value(), StandardCharsets.UTF_8);

    orderProjection.update(record.value(), correlationId);
}
```

`lastHeader()` returns the last header with the matching name. If the contract allows multiple values with the same name, use `headers().headers(name)` to iterate over all of them instead of silently picking one value.

Spring Kafka also populates record metadata into dedicated headers such as `KafkaHeaders.RECEIVED_TOPIC`, `KafkaHeaders.RECEIVED_PARTITION`, `KafkaHeaders.OFFSET`, `KafkaHeaders.RECEIVED_TIMESTAMP`, and `KafkaHeaders.RECEIVED_KEY`. You can retrieve them via `@Header` in the listener or by accepting `ConsumerRecordMetadata`. These are metadata mapped by the framework from the Kafka record; they differ from custom headers added by the application.

Example receiving metadata via annotations:

```java
@KafkaListener(topics = "order-events")
public void consume(
        OrderConfirmed event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    log.info("Received order event from {}-{} at offset {}",
            topic, partition, offset);
    orderProjection.update(event);
}
```

## 4. KafkaHeaderMapper and cross-service compatibility

When using `Message<?>`, Spring Kafka uses `KafkaHeaderMapper` to convert between `MessageHeaders` and native Kafka `Headers`. Two common mappers exist:

- `SimpleKafkaHeaderMapper` preserves values as `byte[]`; it can be configured to convert Strings using a charset. This is the predictable choice when exchanging data with non-Spring applications.
- `JsonKafkaHeaderMapper` supports headers with rich data types. The mapper writes an extra `spring_json_header_types` header describing the types to restore upon receipt.

Example mapper configuration:

```java
@Bean
MessagingMessageConverter kafkaMessageConverter() {
    MessagingMessageConverter converter = new MessagingMessageConverter();
    JsonKafkaHeaderMapper mapper = new JsonKafkaHeaderMapper();
    mapper.setRawMappedHeaders(Map.of("correlation-id", true, "event-type", true));
    converter.setHeaderMapper(mapper);
    return converter;
}
```

Set this converter on `KafkaTemplate` and the listener container if the application configures them manually; in Spring Boot, an appropriate converter bean can be picked up by auto-configuration. With `rawMappedHeaders`, configured String headers are mapped to bytes using the charset instead of JSON encoding. On the receiving side, the corresponding byte values can be converted back to Strings. This is useful when services need to exchange text headers in a simple format.

`JsonKafkaHeaderMapper` only trusts certain default packages when deserializing typed headers. If custom types must be supported, add only the exact required packages using `addTrustedPackages()`. Do not configure `*` for untrusted data sources because that permits deserializing arbitrary types on the classpath. When exchanging with polyglot systems, prefer Strings or bytes with an explicit schema rather than sending Java objects in headers.

## 5. Using interceptors in the right place

Interceptors fit cross-cutting behavior across many records, such as adding default metadata, checking required headers, tracing processing, or collecting metrics. There are two main locations:

| Type | Where it runs | Suitable use case |
|---|---|---|
| Kafka client `ProducerInterceptor` | On the producer when sending and receiving acknowledgments | Common policy across multiple sends from the same producer |
| Spring Kafka `RecordInterceptor` | In the listener container, before the listener and with callbacks after listener success/failure | Checking or observing records at a specific listener |

`ProducerInterceptor` belongs to the Kafka client, not managed by Spring. Therefore, Spring dependency injection does not work automatically inside this interceptor. If dependencies must be passed, configure them via the map in `configure()` or a custom initialization mechanism. The `onSend()` callback sits on the send path, so keep processing very fast, do not wait on I/O, and do not call back into the Kafka producer.

Example adding static `source-service` metadata to every record passing through a producer:

```java
public class SourceServiceProducerInterceptor
        implements ProducerInterceptor<String, OrderConfirmed> {

    @Override
    public ProducerRecord<String, OrderConfirmed> onSend(
            ProducerRecord<String, OrderConfirmed> record) {

        if (record.headers().lastHeader("source-service") == null) {
            record.headers().add(
                    "source-service",
                    "order-service".getBytes(StandardCharsets.UTF_8));
        }
        return record;
    }

    @Override
    public void onAcknowledgement(RecordMetadata metadata, Exception exception) {
        // Only record the send outcome; do not perform synchronous I/O here.
    }

    @Override
    public void close() {
    }

    @Override
    public void configure(Map<String, ?> configs) {
    }
}
```

Register the interceptor in producer properties using `ProducerConfig.INTERCEPTOR_CLASSES_CONFIG`. Per-request metadata like `correlation-id` should still be added where the `ProducerRecord` is built, since a shared interceptor does not know the business context of each send.

`RecordInterceptor` is invoked before the listener. If it returns `null`, the listener is skipped. Since Spring Kafka 2.7, interceptors have callbacks when the listener succeeds or throws an exception; you can use them to record outcomes. If the sole goal is filtering records by a business condition, `RecordFilterStrategy` expresses the intent more clearly.

Example registering a `RecordInterceptor` to check correlation ID and log outcomes:

```java
factory.setRecordInterceptor(new RecordInterceptor<String, OrderConfirmed>() {

    @Override
    public ConsumerRecord<String, OrderConfirmed> intercept(
            ConsumerRecord<String, OrderConfirmed> record,
            Consumer<String, OrderConfirmed> consumer) {

        Header correlation = record.headers().lastHeader("correlation-id");
        if (correlation == null) {
            log.warn("Record has no correlation-id: {}-{}",
                    record.topic(), record.partition());
        }
        return record;
    }

    @Override
    public void success(ConsumerRecord<String, OrderConfirmed> record,
                        Consumer<String, OrderConfirmed> consumer) {
        log.debug("Listener processed {} at offset {}",
                record.topic(), record.offset());
    }

    @Override
    public void failure(ConsumerRecord<String, OrderConfirmed> record,
                        Exception exception,
                        Consumer<String, OrderConfirmed> consumer) {
        log.warn("Listener failed for {} at offset {}",
                record.topic(), record.offset(), exception);
    }
});
```

Do not call `seek()`, `commitSync()`, or operations altering consumer position inside an interceptor; the listener container must manage offsets. If an interceptor returns a new `ConsumerRecord`, topic, partition, and offset must remain unchanged to avoid losing or duplicating records. With transactional containers, interceptors are invoked before the transaction starts by default since Spring Kafka 2.8; you can set `interceptBeforeTx = false` if the interceptor needs to run inside the transaction. If an interceptor might throw an exception and you want that exception to roll back the container transaction, do not let the interceptor run before the transaction.

## 6. Propagating trace context with Micrometer Observation

Trace context links the message-sending span in the source service with the receiving and processing span in the target service. The W3C Trace Context standard defines `traceparent` and `tracestate`; baggage can carry certain allowed contextual values between services.

Since Spring Kafka 3.0, `KafkaTemplate` and listener containers support Micrometer Observation. Enable observation on both sides:

```java
@Bean
KafkaTemplate<String, OrderConfirmed> kafkaTemplate(
        ProducerFactory<String, OrderConfirmed> producerFactory) {

    KafkaTemplate<String, OrderConfirmed> template =
            new KafkaTemplate<>(producerFactory);
    template.setObservationEnabled(true);
    return template;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderConfirmed> orderListenerFactory(
        ConsumerFactory<String, OrderConfirmed> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderConfirmed>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setObservationEnabled(true);
    return factory;
}
```

For real trace propagation, the application also needs Micrometer Tracing, a tracer implementation such as OpenTelemetry or Brave, and tracing observation handlers/propagators registered in the `ObservationRegistry`. Spring Boot can auto-configure these components when the right dependencies and tracing properties are present. Enabling Observation with `micrometer-core` alone can produce metrics/observations, but is insufficient to create and propagate trace context without a tracing handler.

When sender and receiver observations are properly configured, the tracing handler writes context into the message carrier upon send and restores context upon receipt. If using the W3C propagator, headers like `traceparent` and `tracestate` are transmitted through Kafka. The receiving service creates a child span continuing the same trace; the trace ID is preserved, while the parent/span IDs change per the parent-child relationship. You do not need to manually generate `traceparent` in a `ProducerInterceptor` when Micrometer Tracing already manages propagation.

You can add attributes to spans using `KafkaTemplateObservationConvention` or `KafkaListenerObservationConvention`. Since Spring Kafka 3.0.6, the observation context provides the `ProducerRecord` or `ConsumerRecord` for creating dynamic tags. Only put bounded-cardinality values such as `event-type` or `listener-id` into metric tags; do not use `correlation-id`, order ID, or user ID as low-cardinality metric tags because they cause excessive cardinality. Detailed IDs belong in traces or logs instead.

## 7. Distinguishing correlation ID and trace context

These two kinds of information can coexist in one record, answering two different questions:

| Attribute | Correlation ID | Trace context |
|---|---|---|
| Purpose | Link a business request or workflow | Track the path and timing relationships of distributed operations |
| Who creates it | Application or gateway per business contract | Tracing instrumentation/propagator |
| Format | System-defined, e.g., UUID | Standard propagator format such as W3C or B3 |
| Lifecycle | May stay constant across multiple events in one workflow | Trace ID stays the same in the trace; each span has its own span ID |
| Where queried | Logs, audit, business tools | Tracing systems such as Zipkin or Jaeger |

For example, an order has `correlation-id=order-flow-42` across multiple related events. Each time a service sends or receives a message, it may create a separate span while still belonging to the same trace. When a business workflow spans several minutes or creates multiple processing branches, the correlation ID helps find all business events while trace context shows causal and timing relationships of individual calls.

## 8. Verifying metadata and trace context

Verify both header contents and trace continuity between producer and consumer:

1. Send a `ProducerRecord` with `correlation-id`, `event-type`, and `schema-version`.
2. Read the record via `ConsumerRecord` and verify header names, UTF-8 values, and behavior when headers are missing.
3. Send through an Observation-enabled listener; verify `traceparent` is present when Micrometer Tracing and the W3C propagator are configured.
4. Check traces in the backend: the send span and receive span share the same trace ID with the proper parent-child relationship.
5. Send a record without custom headers to verify the application handles missing headers per contract without throwing `NullPointerException`.
6. Test duplicate header names to verify the consumer picks `lastHeader()` or iterates through all values as required.

Example quick header check after receiving a record:

```java
assertThat(record.headers().lastHeader("correlation-id")).isNotNull();
assertThat(new String(
        record.headers().lastHeader("correlation-id").value(),
        StandardCharsets.UTF_8)).isEqualTo("req-8f31");

assertThat(record.headers().lastHeader("event-type")).isNotNull();
```

For traces, do not assert a fixed `traceparent` string since trace IDs and parent IDs are dynamically generated. Verify that the header exists, has a valid structure, and that the trace backend records spans belonging to the same trace.

## 9. Common mistakes when passing metadata

**Reading headers directly as Strings.** Kafka header values are `byte[]`; decode with the right charset or use a configured mapper.

**Assuming headers always exist.** Legacy producers, non-Spring applications, or manually created records may lack headers. Define which headers are mandatory and handle missing ones cleanly.

**Using headers in place of authentication.** Producer-supplied `tenant-id`, `user-id`, or roles in headers do not automatically become trusted information. Consumers must verify origin and access permissions via dedicated security mechanisms.

**Putting sensitive data in headers.** Headers can appear in logs, observability tools, DLTs, or intermediate systems. Do not send access tokens, passwords, sensitive personal data, or service secrets.

**Letting headers grow unbounded.** Large headers increase record size and network/storage costs. Only pass short, necessary values; do not copy all HTTP request headers into Kafka.

**Manually overwriting trace context.** If Micrometer Tracing manages propagation, do not manually add `traceparent` via an interceptor. Overwriting or crafting invalid headers can break traces or corrupt span relationships.

**Using JSON headers for every system.** `JsonKafkaHeaderMapper` adds its own type metadata and trusted package rules. For non-Spring consumers, raw UTF-8 headers or explicit byte schemas are usually more compatible.

**Doing heavy work inside interceptors.** Interceptors run on the send or receive path. Do not call REST endpoints, query databases, or wait on long tasks in callbacks; doing so lowers throughput and increases processing latency.

## 10. Key Takeaways

- Kafka headers are pairs of names and `byte[]`; a record can have multiple headers with the same name.
- Use `ProducerRecord.headers()` or `MessageBuilder` to add metadata; use `ConsumerRecord.headers()` or `@Header` to read them.
- `KafkaHeaderMapper` maps `MessageHeaders` to Kafka headers; choose raw String/bytes for polyglot contracts and restrict trusted packages when using JSON.
- `ProducerInterceptor` applies at the Kafka producer level; `RecordInterceptor` applies in the listener container with callbacks before/after the listener.
- Do not change topic, partition, offset, or consumer position inside `RecordInterceptor`.
- Spring Kafka 3.0+ supports Observation for `KafkaTemplate` and listener containers; trace propagation requires Micrometer Tracing along with propagators/observation handlers.
- Use `correlation-id` for business correlation and `traceparent`/`tracestate` for distributed tracing; do not overwrite trace context managed by instrumentation.
- Keep metadata small, non-sensitive, consistently named, and handle missing or duplicate headers cleanly.

## References

- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
- [Spring for Apache Kafka — Message Listener Containers, Record Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Monitoring and Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html)
- [Spring for Apache Kafka — Producer and Consumer Interceptors](https://docs.spring.io/spring-kafka/reference/kafka/interceptors.html)
- [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
