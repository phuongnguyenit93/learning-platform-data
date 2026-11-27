# Evaluating Changes in Serialization, Header Mappers, and Error Handlers

## Objectives

When upgrading Spring Cloud Stream, Spring Boot, binders, or Kafka, RabbitMQ, and Pulsar client libraries, an application may still start up successfully yet **fail to read older messages**, drop custom headers, or turn a previously retried error into an ACKed state. These regressions are hard to catch with unit tests that only invoke `Function<T, R>` directly.

Three components must be evaluated together:

- **Serialization and deserialization:** the rules for converting Java objects into bytes on the broker and vice versa. Changes to converters, serializers, deserializers, Serdes, or schemas can alter the wire format.
- **Header mapper:** the rules mapping between Spring `MessageHeaders` and Kafka record headers, AMQP properties/headers, or Pulsar message properties. Mapper changes can drop metadata, change value types, or break routing/tracing.
- **Error handler:** the rules for handling failures across byte reading, data conversion, function invocation, output publishing, and ACK/commit. Changes to handlers, retries, or DLQs can alter delivery guarantees.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_STREAM** module. Examples are framed around event processing with `Supplier`, `Function`, `Consumer`, bindings, Kafka, RabbitMQ, Pulsar, and Kafka Streams; the focus is the **compatibility evaluation workflow before deployment**, not merely how to set a single property.

After this lesson, you can:

- Classify source code, configuration, and dependency changes that affect the wire contract.
- Distinguish framework message conversion from native serializers/deserializers and Kafka Streams Serdes.
- Evaluate readability of historical data, including events stored in topics, DLTs, or state stores.
- Inspect `contentType`, header mapping, Kafka `headerPatterns`, and required headers.
- Distinguish native deserialization failures from framework conversion or function handler failures.
- Evaluate retries, error channels, nack/requeue, DLQ, and ACK/offsets when changing handlers.
- Build a test matrix covering old/new producers, old/new consumers, and failure windows.
- Roll out compatibility changes in phases with monitoring metrics and a rollback plan.

## 1. Upgrading libraries is more than bumping versions

A new version can affect multiple processing stages even when the business function does not change.

~~~mermaid
flowchart LR
    P[Producer object] --> S[Serializer / MessageConverter]
    S --> O[(Broker bytes + headers)]
    O --> H[Broker header mapper]
    H --> D[Deserializer / MessageConverter]
    D --> F[Function]
    F --> E{Processing result}
    E -->|Success| A[ACK / commit / output]
    E -->|Failure| R[Retry / error handler / DLT]
~~~

Three changes can fail independently or in combination:

| Change | Symptom | Risk |
|---|---|---|
| JSON converter changes ObjectMapper config | Fields fail to parse | Old messages become poison messages |
| Switching from framework conversion to native serialization | Wire bytes or Java payload type changes | Old/new consumers become incompatible |
| Kafka header mapper filters out `x-correlation-id` | Header missing at consumer | Lost tracing or misrouted messages |
| `contentType` header changes from String to another type | Converter selects wrong processing path | Fails to deserialize |
| Error handler starts ignoring deserialization errors | No exception visible in handler | Messages silently skipped and unprocessed |
| Retry count or backoff changes | Downstream call count increases/decreases | Duplicates or increased dependency load |
| DLQ policy changes | Failed messages stop going to old DLT | Loss of investigation/replay path |
| ACK/commit timing changes | Messages confirmed prematurely or redelivered | Lost tasks or duplicate side effects |

An application can report health `UP` and bindings `STARTED` while still failing to process messages accurately. Verify end-to-end across **bytes, headers, status/acks, and business outcomes**, not just startup success.

## 2. Establishing a baseline before upgrading

Do not start by editing YAML. First, build an inventory of the currently running version.

| Item | What to record |
|---|---|
| Framework | Spring Boot, Spring Cloud Stream, Spring for Apache Kafka/AMQP/Pulsar |
| Binder | Regular Kafka, Kafka Streams, RabbitMQ, or Pulsar; artifact/version |
| Broker/client | Kafka client/broker, RabbitMQ broker, or Pulsar client/broker versions |
| Binding | Function name, binding name, destination, group/subscription |
| Inbound format | JSON/Avro/Protobuf/String/bytes, serializer/Serde, schema ID |
| Outbound format | Actual broker bytes, content type, headers |
| Header policy | List of critical headers, types, and mapping rules |
| Error policy | Framework retries, binder retries, nack/requeue, DLQ, producer failures |
| Delivery | ACK/offset commit, idempotency key, transaction/outbox if any |
| State | Kafka Streams store/changelog Serde if topology is stateful |

Example inventory:

~~~text
Binding: processOrders-in-0
Destination: orders.created
Group: inventory-service
Input bytes: UTF-8 JSON object
Key: String orderId
Required headers: x-event-id, x-correlation-id, x-schema-version
Spring contentType: application/json
Retry: 3 attempts, exponential backoff
DLQ: orders.created.dlt
Consumer side effect: inventory reservation in DB transaction
Idempotency: unique event_id in inbox table
~~~

Save **actual message fixtures** from a test broker or standardized contract test suite. Fixtures must include key/value bytes, header names, header bytes/typed representations, topic/queue, and schema version. Do not only save pretty-printed JSON and discard metadata.

### Distinguishing actual baseline from config intent

YAML only states what the app is configured to do. Final wire bytes and header mappings also depend on the binder, serializer, converter, broker, and producer code. To know the real contract, publish an event, consume it with an independent client, and inspect the record.

If the application uses multiple binders or producers in different languages, build a separate baseline for each data path.

## 3. Serialization is a wire contract

Serialization turns objects into bytes. Deserialization turns bytes back into objects. The broker does not know whether a byte array is a Java record, JSON, Avro, or Protobuf; producers and consumers must agree on representation.

Example event:

~~~java
public record OrderCreated(
        String eventId,
        String orderId,
        long amountMinor
) {}
~~~

Corresponding JSON payload:

~~~json
{
  "eventId": "evt-1042",
  "orderId": "O-1042",
  "amountMinor": 12500
}
~~~

Two implementations may share the `OrderCreated` class yet produce different bytes. For example, one uses JSON while the other uses a binary serializer or Jackson with a custom naming strategy. In that case, matching Java signatures does not guarantee the consumer can read the message.

An upgrade must answer all four questions:

1. **New producer → new consumer**: does the new active path work properly?
2. **Old producer → new consumer**: can historical data still retained in the broker be read?
3. **New producer → old consumer**: during a rolling deployment, can the old binary handle new events?
4. **Old DLQ/replay → new consumer**: can messages stored days/months earlier still be replayed?

If Kafka Streams state stores or retained topics exist, also evaluate materialized data. Changing converters does not automatically migrate bytes inside state stores or changelogs.

## 4. Framework conversion vs. native serialization

In regular Spring Cloud Stream Kafka/RabbitMQ binders, the framework can use Spring Messaging `MessageConverter` to convert payloads based on `contentType`. When native serialization/decoding is enabled, the client library uses the serializer/deserializer configured by the application.

| Mechanism | Payload conversion | What determines wire format |
|---|---|---|
| Framework conversion | Spring `MessageConverter` | `contentType`, target type, converter/ObjectMapper |
| Native Kafka producer | Kafka client `Serializer` | `value.serializer` and `key.serializer` |
| Native Kafka consumer | Kafka client `Deserializer` | `value.deserializer` and `key.deserializer` |
| Kafka Streams binder | Native `Serde` by default; framework conversion path for value when configured | Key/value Serde or converter per selected mode |
| RabbitMQ/Pulsar | Adapter/client and dedicated mapping | Converter/schema/client config of binder/version |

One conversion mode is not automatically equivalent to another. Switching from framework conversion to native encoding may bypass the binding's `contentType` for marshalling and delegate formatting to the Kafka client serializer. Likewise, enabling native decoding causes the deserializer to return a Java type before the framework passes it into the function.

### Example choosing framework conversion

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          group: order-normalizer
          content-type: application/json
          consumer:
            use-native-decoding: false
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: application/json
          producer:
            use-native-encoding: false
~~~

In this example, the framework handles conversion according to the binding and function signature. Verify the actual version because converter behavior can depend on container and binder.

### Example native Kafka decoding/encoding

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          group: order-normalizer
          consumer:
            use-native-decoding: true
        normalizeOrder-out-0:
          destination: orders.normalized
          producer:
            use-native-encoding: true
      kafka:
        bindings:
          normalizeOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.apache.kafka.common.serialization.StringDeserializer
          normalizeOrder-out-0:
            producer:
              configuration:
                key.serializer: org.apache.kafka.common.serialization.StringSerializer
                value.serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

The second example assumes the function works with `String`, not an `OrderCreated` POJO. If the function still accepts `OrderCreated`, you must configure a JSON deserializer with the proper target type or adjust the function. Enabling native decoding alone will not make Kafka's `StringDeserializer` produce a POJO.

When switching modes, test the **actual Java payload type**, key type, and **actual bytes** before and after. Do not rely solely on `content-type: application/json` as proof that a native serializer is emitting JSON.

## 5. contentType precedence and converter changes

With framework conversion, content type selection order is usually:

1. The message's `contentType` header.
2. `content-type` declared on the binding.
3. Framework default, typically `application/json`.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.created
          content-type: application/json
~~~

If an incoming message has header `contentType=text/plain`, the framework may choose a different conversion path than the JSON binding, depending on payload type and converter. Changing the header mapper can lose or change the type of `contentType`; thus a change thought to be "headers only" can break JSON deserialization.

Do not assume every header carried by the broker maps verbatim to `MessageHeaders.CONTENT_TYPE`. Check all of:

- Does the header exist on the broker?
- Does the binder map the header into the Spring Message?
- Is the header typed as `String`, `MimeType`, or `byte[]`?
- Which converter is effective?
- Is the function target type a POJO, `Message<POJO>`, `String`, or `byte[]`?
- Does the output message carry a new `contentType` on its own?

For a function returning a plain payload, Spring Cloud Stream may create a new message without preserving the input `contentType` header, letting the output binding apply its own content type. For a function returning a manually constructed `Message<?>`, the developer controls headers; do not blindly copy headers to output.

## 6. JSON schemas and compatibility

Serialization changes often happen via Java models and ObjectMapper.

| JSON change | Risk level | What to check |
|---|---|---|
| Add optional field | Usually low if consumer ignores unknown fields | Do old consumers accept unknown fields? |
| Rename field | High | Alias or migration; old consumers stop seeing field |
| Change String to number | High | Coercion, validation, large numbers/overflow |
| Add required field | High | Historical data lacking the field needs default or versioning |
| Change enum values | High | Do old consumers have a fallback? |
| Change timestamp format/time zone | High | Parsing, precision, UTC |
| Change decimal/double | High | Precision and rounding |
| Change null/tombstone semantics | High | Data deletion vs. schema error |
| Change binary field encoding | High | Base64, raw bytes, and schema |

Example backward-compatible strategy for a new field:

~~~java
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderCreatedV2(
        String eventId,
        String orderId,
        long amountMinor,
        String currency
) {}
~~~

The annotation ignores unknown fields; it does **not** supply a missing value for `currency`. If old records omit this field, code needs an explicit policy: valid default, validation, or migration. For immutable records, check constructors/`@JsonCreator` and relevant ObjectMapper modules.

### Versioning the event contract

Explicitly specify:

- Event type and schema version.
- Required, optional, and nullable fields.
- JSON property naming, enum representation, and timestamp format.
- How long legacy data stays within retention.
- Backward, forward, or full compatibility depending on rollout flow.
- Policy for handling unknown fields.
- Field used as the idempotency key.

For Avro/Protobuf/Schema Registry, check schema IDs/subject naming, compatibility policies, generated classes, and deserializers. Do not assume setting a schema registry URL is enough to switch from JSON to Avro.

## 7. Kafka Streams Serdes and state stores during upgrades

The Kafka Streams binder requires separate evaluation. Kafka Streams processes records using `KStream`, `KTable`, and key/value `Serde`s. Current binder documentation states native decoding is the default for values, while keys use native Serdes. However, the binder also offers a framework conversion path for values when native decoding/encoding is explicitly disabled.

Example per-binding Serde definition:

~~~yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.created
        aggregateOrders-out-0:
          destination: orders.aggregated
      kafka:
        streams:
          bindings:
            aggregateOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: orderCreatedSerde
            aggregateOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: orderAggregateSerde
~~~

Names like `orderCreatedSerde` and `orderAggregateSerde` illustrate typed Serde beans registered by the app, if the release supports resolving beans that way; class names or bean configuration may be needed depending on version. Do not assume all versions infer Serdes in the same order.

When changing a Serde, evaluate three places:

1. **Source/sink topics:** reading legacy records and writing contract-compliant outputs.
2. **Repartition topics:** the topology may re-encode keys/values internally.
3. **State stores/changelogs:** historical RocksDB/changelog bytes must deserialize during restoration.

A topology can successfully read new events yet fail when restoring a state store because the changelog uses an older schema. If state is incompatible, consider creating a new store, new applicationId, backfill, or controlled migration. Do not change `applicationId` or delete changelogs merely to make errors vanish without a data replay plan.

### Kafka Streams deserialization error handler

The Kafka Streams binder has its own configuration, separate from the regular Kafka binder's error handler:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            deserializationExceptionHandler: logAndFail
~~~

Depending on the release, options may include `logAndFail`, `logAndContinue`, or `sendToDlq`. The binding level can override it:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            aggregateOrders-in-0:
              consumer:
                deserializationExceptionHandler: sendToDlq
~~~

A `logAndContinue` policy skips corrupt records, whereas `logAndFail` halts the topology. `sendToDlq` routes failed records to an isolation topic if configured and provisioned properly. This is a **change in which data is processed**, not simply a log level change.

## 8. Header mappers as a metadata translation layer

Spring Message headers do not necessarily share the same representation as broker headers:

- **Kafka:** record headers store names and byte-array values.
- **RabbitMQ:** AMQP properties (e.g., content type) and headers table with typed values.
- **Pulsar:** properties and message metadata; mapping depends on binder/client.

A custom `x-correlation-id` header may be a `String` in Spring Message but become `byte[]` in Kafka. When read back, the mapper may decode it as String or keep raw bytes depending on mapping and version.

### What can change when upgrading a mapper?

- Headers filtered out by patterns.
- Headers preserved but converted between `String` ↔ `byte[]`.
- JSON type-info headers appearing or disappearing.
- Standard binder headers renamed or mapped differently.
- Metadata such as topic, partition, key, or message ID placed under different headers.
- Content type no longer recognized.
- Messages bridged across Kafka/Rabbit/Pulsar losing custom headers.
- Oversized headers truncated or rejected by the broker.

Do not use an in-memory Spring Message as proof that headers will reach another consumer. Read the actual record with an independent client.

## 9. Evaluating Kafka headerPatterns

The regular Kafka binder has the producer property `headerPatterns` to select which Spring headers map to Kafka record headers.

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              headerPatterns: "x-correlation-id,x-event-id,x-schema-version,contentType"
~~~

Per current binder documentation, patterns support leading/trailing wildcards and `!` for negation; matching stops at the first matching rule. Spring's `id` and `timestamp` headers are not mapped by this rule.

Rule example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          normalizeOrder-out-0:
            producer:
              headerPatterns: "!x-internal-*,x-*"
~~~

The intent is to forward only the `x-*` group except internal headers. If you need to keep `contentType` or required framework headers, add matching rules and test; do not assume they are retained once an allowlist is introduced.

### Typical upgrade failure

The old version forwarded all custom headers. The new version added an allowlist but forgot `x-schema-version`:

~~~text
Producer Spring Message:
  x-event-id       = evt-1042
  x-correlation-id = corr-44
  x-schema-version = 3

Kafka record after new mapper:
  x-event-id       = bytes("evt-1042")
  x-correlation-id = bytes("corr-44")
  x-schema-version = MISSING
~~~

The consumer may parse JSON yet fail to determine the schema version, causing rejection or falling back to the wrong default parser. What needs checking is not whether the mapper bean initializes, but the **set of headers and value types** on the wire.

### Legacy embedded headers

Spring Cloud Stream has a `headerMode` property with values such as `headers`, `embeddedHeaders`, or `none` depending on binder capabilities. In modern Kafka environments, native headers are supported; embedded headers are primarily for compatibility with older integrations/versions.

Changing `headerMode` alters the payload bytes because embedded headers become part of binary framing rather than external metadata. Old and new consumers must understand the same protocol. When native serialization is enabled, `embeddedHeaders` has limitations or is ignored depending on the binder; consult the version-matched reference.

Do not change `headerMode` at the same time as changing a JSON schema without separate migration tests for each change.

## 10. Header contract: types, sizes, and trust

A header contract should include an explicit table:

| Header | Wire type | Required | Policy |
|---|---|---|---|
| `x-event-id` | UTF-8 String bytes | Yes | Preserve across retry/replay |
| `x-correlation-id` | UTF-8 String bytes | Yes | Preserve across service chain |
| `x-schema-version` | UTF-8 String bytes | Yes | Validate supported version |
| `contentType` | Framework/binder compatible format | Depends on conversion mode | Must match payload |
| `x-tenant-id` | UTF-8 String bytes | System-dependent | Trust only after source authentication |
| `x-internal-*` | Not emitted externally | No | Exclude from outbound |

Do not use Java class names as a wire contract for polyglot clients when an independent event type/schema ID can be used. Some Spring Kafka JSON serializers/deserializers can add/read type headers. When disabling type info or changing trusted packages, consumers may stop resolving the target type; configure target types explicitly and test.

Do not use headers supplied by untrusted producers to grant tenant access or roles. Header mappers transmit metadata, not security authentication.

## 11. Error handlers have multiple intervention points

An event can fail at any of these stages:

~~~mermaid
flowchart TD
    A[Broker record bytes] --> B{Native deserialize}
    B -->|Error| X[Deserializer error path]
    B -->|OK| C{Framework conversion}
    C -->|Error| Y[Conversion error path]
    C -->|OK| D{Function / business}
    D -->|Error| Z[Handler retry / recoverer]
    D -->|OK| E{Serialize / publish output}
    E -->|Error| W[Producer error path]
    E -->|OK| F[ACK / offset / confirm]
    X --> R[Policy per binder/version]
    Y --> R
    Z --> R
    W --> R
~~~

**No single error handler automatically catches every branch on every binder.** Exception names and access to raw payloads vary by processing path.

| Stage | Example | Reaches function? | What to check |
|---|---|---|---|
| Native deserialization | Kafka `SerializationException` | Usually no | Deserializer / container error handling |
| Framework conversion | JSON fails to map to POJO | Usually no | Converter / binder error channel |
| Business handler | DB timeout, validation exception | Yes | Retry/backoff, recovery |
| Outbound serialization | Serializer cannot encode object | Business side effects may already be done | Producer failure and outbox |
| Broker publish | Kafka auth/timeout; Rabbit return; Pulsar send failure | Function may already have executed | Confirm/callback, publish retry |
| ACK/commit | Process crashes after DB commit before ACK | Business side effects may already be committed | Redelivery, idempotency |

Changing a deserializer can shift an error from a "conversion error" to a "native deserialization error". If the old handler only caught conversion exceptions, post-upgrade behavior can differ completely.

## 12. Framework retries vs. broker retries

For functional imperative consumers, Spring Cloud Stream provides message-handler-level retry and error handling. Common shared properties:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: order-processing
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
~~~

Per general documentation, `maxAttempts` includes the initial attempt. Thus 3 attempts does not mean 3 retries after the first attempt; the total is normally 3 handler invocations.

Do not assume these properties have the same effect for:

- Native deserialization failing before the function receives a message.
- Kafka Streams DSL processing.
- Reactive `Function<Flux<T>, Flux<R>>`, where retries may be governed by Reactor operators.
- Native Pulsar consumer retries or redelivery on nack.
- Broker TTL/DLX or retry topics.

For reactive functions, use operators such as `retryWhen`, `onErrorResume`, or routing according to Reactor semantics, then test errors and acknowledgements at the binder boundary.

### One failure, multiple retry layers

Suppose a service has:

- 3 handler invocations from framework retry.
- 5 broker redeliveries.
- An HTTP client retrying twice on its own.

In the worst case, downstream dependency calls can far exceed the number configured at any single layer. Do not multiply numbers without testing; measure attempts per layer and enforce a bounded total retry budget.

## 13. Regular Kafka binder: DLQ and native deserialization

The regular Kafka binder provides `enableDlq` on consumer bindings. A relatively simple configuration example using framework conversion:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
          consumer:
            max-attempts: 3
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.created.dlt
~~~

When a message flows through a binder-supported error path and retries are exhausted, the binder can publish it to the DLT. The topic name and partitions must be provisioned with appropriate ACLs. Do not treat `enableDlq=true` as a guarantee that every native serialization error is caught and written to the DLT.

### Native deserializer fails before the binder calls the handler

If a native Kafka deserializer throws an exception during polling, the failure can occur before a Spring Message is built. Spring Kafka provides `ErrorHandlingDeserializer`, which can store error details in record headers so the container error handler gets a chance to process it.

Configuration skeleton (String type used for illustration):

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            use-native-decoding: true
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                key.deserializer: org.apache.kafka.common.serialization.StringDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.value.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
~~~

This is **part** of configuring deserialization error handling. To isolate corrupt records, configure the error handler/DLQ/producer serializers compatible with raw data per your exact version's documentation. When native decoding is enabled, some setups require specifying `dlqProducerProperties.configuration.key.serializer` and `value.serializer`; the DLT serializer must not corrupt the raw bytes again.

A record failing native deserialization may not produce an `OrderCreated`; never assume the function is still invoked with a null POJO to decide on retries. Test with real malformed payloads, verify whether the offset advanced, and confirm the original record can be recovered/replayed.

### When upgrading the Kafka error handler

Verify:

- Final attempt count and backoff.
- Whether the failed record retains raw key/value and original headers.
- Dead-letter topic, partition mapping, and required ACLs.
- Whether the DLT serializer is compatible with raw bytes.
- Whether the offset commits after successful recovery.
- Whether the handler accidentally skips records and loses events.
- Whether the error handler runs when producer send fails.

## 14. RabbitMQ binder: reject, requeue, and republish

The RabbitMQ binder uses different error semantics from Kafka. A consumer can nack/reject a delivery so the broker requeues it or routes it to a dead-letter exchange (DLX) per queue configuration; the binder can also republish failed messages to a DLQ with exception headers.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            max-attempts: 3
      rabbit:
        bindings:
          processOrders-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              requeueRejected: false
~~~

Meaning of these properties:

- `autoBindDlq`: tells the binder to declare the DLQ and related DLX if topology is managed by the binder.
- `republishToDlq`: binder itself republishes failed messages with extra exception metadata.
- `requeueRejected`: policy for requeuing rejected deliveries when the binder does not republish through that path.
- `max-attempts`: framework-level retries if supported by the corresponding handler path.

If `republishToDlq` changes from false to true, the DLQ consumer may see new headers such as exception message/stack trace and a different publish path. This impacts message/header size, publish permissions, publisher confirms, and DLT analysis logic.

If DLQs are declared externally via infrastructure, `autoBindDlq` may be inappropriate. Do not automatically enable auto-provisioning in production when infrastructure manages queues/DLXs via IaC.

### Requeue storm

When a message fails consistently, `requeueRejected=true` can loop the message endlessly if there is no retry delay or cap. Error handler upgrades must test whether poison messages cause queue starvation, rising unacked counts, or increased latency for valid messages.

Test against a real RabbitMQ broker: inspect ready/unacked/DLQ queues and examine received AMQP headers. Test Binder does not fully reproduce reject/nack/routing and republish semantics.

## 15. Pulsar binder: ack, redelivery, retry letter, and DLT

Pulsar manages messages by subscription using ACK, negative acknowledgment, acknowledgment timeout, retry letter topics, and dead-letter policies. Policies can vary by subscription type and Pulsar broker/client version.

When changing the Pulsar binder's error handler, check:

1. Does the function failure path trigger nack or framework retry?
2. Was ack timeout enabled/disabled or changed in value?
3. Did negative-ack delay and redelivery backoff change?
4. Are retry letter topics and retries enabled?
5. Is the max redelivery count tracked durably across restarts?
6. Does the subscription type support DLQ in that version?
7. Are DLT topic/subscription and permissions still accurate?

Recent Pulsar documentation warns that negative-acknowledgment redelivery counters may be stored in memory only, causing DLQ limits to be enforced inconsistently across restarts/unloads. Use retry letter topics and message-stored retry counts when durable limits are required, and verify with integration tests.

Do not copy `@PulsarListener` ack mode config into the functional binder if the binder version does not expose the same API. Likewise, do not assume Kafka binder's `enableDlq` has an identical property on the Pulsar binder.

## 16. Changing error policy can cause lost or duplicate events

An error path that stops throwing exceptions can cause the framework to treat the message as successfully processed. Example:

~~~java
@Bean
Consumer<OrderCreated> processOrders(OrderService service) {
    return event -> {
        try {
            service.reserveInventory(event);
        }
        catch (Exception ex) {
            log.warn("Reservation failed", ex);
            // WRONG: swallowing the error and returning normally.
        }
    };
}
~~~

If the consumer completes normally, the binder may ack/commit even though inventory reservation failed. This is a change capable of causing **lost business processing**.

An alternative:

~~~java
@Bean
Consumer<OrderCreated> processOrders(OrderService service) {
    return event -> service.reserveInventory(event);
}
~~~

Let errors flow into the designed retry/recovery path. However, throwing errors can also trigger redelivery and duplicates. If the database committed before the message was acked, retries can repeat side effects. Use an event ID/inbox unique constraint or an idempotent handler.

### Do not confuse exactly-once with a good error handler

Retries, DLQs, and offset commits do not automatically provide end-to-end exactly-once across Kafka, databases, HTTP, and RabbitMQ/Pulsar. When broker transactions coexist with external side effects, consistency patterns like outbox/inbox/idempotency are still necessary.

During upgrades, also test crashing **after DB commit but before ACK**, not only failures before calling the DB.

## 17. Pre/post-upgrade compatibility matrix

A migration plan should include a table covering every old/new combination:

| Producer | Consumer | Payload bytes | Headers | Error policy | Required outcome |
|---|---|---|---|---|---|
| Old | Old | Baseline | Baseline | Baseline | Current behavior |
| Old | New | Retained data | Old headers | New handler | Backward compatibility |
| New | Old | New format | New headers | Old handler | Rolling-deploy compatibility |
| New | New | New format | New headers | New handler | Post-cutover happy path |
| Old DLT | New | Poison/replayed record | Old exception headers | New recovery | Replayable |
| New producer | Non-JVM consumer | New format | Metadata bytes | Own policy | Interoperability |
| Old Kafka Streams state | New topology | Old changelog/state bytes | Internal metadata | Restore handler | State recovery |

Do not test only new/new pairs. During rolling deployments, old and new versions typically coexist. If one version cannot read records from the other, use a versioned topic, schema migration, or coordinated cutover.

### Failure paths matrix

| Test input | Failure point | Assertion |
|---|---|---|
| Valid JSON | None | Function invoked, ACK/commit right, output matches contract |
| Malformed JSON | Converter/deserializer | Function not invoked; record not silently lost |
| Valid JSON but invalid schema | Conversion/validation | Proper retry or DLT |
| Missing required header | Header mapper/validation | Does not process wrong tenant/schema |
| Wrong header type | Mapper/converter | No infinite `ClassCastException` loop |
| Transient DB timeout | Handler | Accurate backoff and retry budget |
| DB committed then process dies | ACK boundary | Idempotent redelivery |
| DLT publish fails | Recoverer producer | Does not falsely confirm recovery |
| Output serializer fails | Producer | Does not record false success |
| Kafka Streams restore | State/changelog | Can read old state or intentionally migrated |

## 18. Contract test example for serialization

Start with unit tests for the chosen converter/serializer. Example of a JSON fixture read by both the current and new ObjectMapper:

~~~java
@Test
void readsHistoricalOrderEvent() throws Exception {
    String historicalJson = """
        {
          "eventId": "evt-1042",
          "orderId": "O-1042",
          "amountMinor": 12500
        }
        """;

    OrderCreated order = objectMapper.readValue(
            historicalJson, OrderCreated.class);

    assertThat(order.eventId()).isEqualTo("evt-1042");
    assertThat(order.amountMinor()).isEqualTo(12500L);
}
~~~

This test catches part of schema issues, but does not prove `MessageConverter`, header mapping, and the binder work right. Test next at the binding layer.

### Test Binder with InputDestination and OutputDestination

~~~java
@SpringBootTest
@EnableTestBinder
class ConversionContractTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;
    @Autowired ObjectMapper mapper;

    @Test
    void convertsJsonAndKeepsCorrelation() throws Exception {
        byte[] raw = """
            {"eventId":"evt-1042",
             "orderId":"O-1042",
             "amountMinor":12500}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(
            MessageBuilder.withPayload(raw)
                .setHeader(
                    MessageHeaders.CONTENT_TYPE,
                    MimeTypeUtils.APPLICATION_JSON)
                .setHeader("x-correlation-id", "corr-44")
                .build(),
            "normalizeOrder-in-0"
        );

        Message<byte[]> result = output.receive(
                3_000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(mapper.readTree(result.getPayload())
                .path("orderId").asText())
                .isEqualTo("O-1042");
    }
}
~~~

If the function returns `Message<?>` and explicitly preserves correlation IDs, add the corresponding header assertion. If the function returns a plain payload and the framework does not propagate a header in your version, the test should reflect the actual contract.

Test Binder may not exercise native Kafka serializers, RabbitMQ message converters, or Pulsar schemas the way production does. Thus it is a **function/binding test**, not the final wire-format test.

## 19. Testing bytes and headers on a real broker

A broker integration test needs a real Kafka, RabbitMQ, or Pulsar instance in the test environment, which can run via Testcontainers if appropriate for your infrastructure.

Workflow:

1. Start the broker with topics/queues, authentication, and schema registry if needed.
2. Write fixture events using the **old-version** producer.
3. Start the **new-version** consumer.
4. Verify the exact count of processed events and DB/output state.
5. Read output bytes and headers using an independent client.
6. Verify `contentType`, custom headers, key/partition/routing, and schema version.
7. Send new events with the new producer; try reading with the old consumer.
8. Send invalid JSON, invalid headers, and poison events; observe retry/offset/DLT.
9. Kill the consumer between DB commit and ACK to verify idempotency.
10. Verify the DLT still retains raw bytes/headers sufficient for replay.

Example Kafka Java client inspecting headers at the byte level:

~~~java
ConsumerRecord<String, byte[]> record = kafkaConsumer
        .poll(Duration.ofSeconds(5))
        .records("orders.normalized")
        .iterator()
        .next();

Header h = record.headers().lastHeader("x-correlation-id");

assertThat(h).isNotNull();
assertThat(new String(h.value(), StandardCharsets.UTF_8))
        .isEqualTo("corr-44");
~~~

This is an illustrative verification snippet; fixture producer, consumer config, subscribe/seek, polling timeouts, and cleanup must be added in a real integration test. Use a unique event ID per test and isolate groups/offsets to avoid reading stale records.

## 20. Testing error handler policies

When changing error handling, do not merely assert that an exception is thrown. Observe broker side effects and business state.

~~~text
Test: malformed JSON -> DLT

Given:
  - Consumer runs the new binder version.
  - Input record has recorded key, bytes, and headers.
  - DLT topic and ACLs are ready.

When:
  - Publish malformed JSON to input.
  - Wait for retry/recovery to finish.

Then:
  - Business function is not invoked with invalid data.
  - Error is recorded once according to instrumentation.
  - DLT contains the appropriate record, preserving event ID/source metadata if available.
  - Input offset/ACK advances per designed policy.
  - No infinite retry loop is created.
~~~

Additional scenarios to include:

- Transient retry succeeds on attempt 2.
- Retries exhaust and route to DLT.
- Non-retryable errors are isolated early.
- DLT publish is rejected/times out.
- Broker restarts mid-redelivery.
- Producer fails after business DB has committed.
- Schema registry is unavailable.
- Interceptor or header mapper throws an exception before the function.

During execution, count **handler invocations**, **broker redeliveries**, **producer attempts**, and **DLT records** separately. Do not assume one failure corresponds to one DLT record in every case, especially with asynchronous retry/recovery.

## 21. Rollback-capable rollout plan

If the wire format is unchanged and only compatible libraries are upgraded, a rolling deployment can be used after testing the full matrix. If the format changes, phase the rollout:

### Expand-and-contract

1. Upgrade consumers to **read both old and new formats**.
2. Deploy all new consumers; verify historical data and DLT.
3. Upgrade producers to emit the new format.
4. Monitor serialization errors, header loss, retries, and backlogs.
5. Remove support for reading the old format only after the retention/replay window expires or migration completes.
6. Remove compatibility code in a separate release.

This is the preferred strategy when avoiding downtime and when a deserializer can read multiple schema versions.

### New topic version

If the format changes completely (e.g., JSON → Avro or changed key semantics), you can create a new topic:

~~~text
orders.created.v1 -> old consumers
orders.created.v2 -> new consumers
~~~

If dual-write is needed, watch for duplicates, ordering, and transaction boundaries; an outbox can ensure events needed on both streams are not lost. Only switch downstream to v2 once backfill, consumer readiness, and reconciliation conditions are met.

### Rollback

Rollback must be checked in both directions:

- Can the old binary read events published by the new producer?
- Can the old handler understand the new DLT/header format?

If the answer is "no", a simple binary rollback can make the system worse. Maintain topic versioning, consumer compatibility, or a controlled data recovery plan.

## 22. Post-upgrade observability

Monitor by binding, topic, consumer group, and deployed version:

| Metric/log | Why it is needed |
|---|---|
| Deserialization/conversion error rate | Detects wrong wire format or target type |
| Missing/invalid required header count | Detects header mapper or producer contract drift |
| Handler success/failure rate | Separates business errors from conversion errors |
| Retry attempts and backoff duration | Detects retry amplification |
| Consumer lag/backlog | Tracks processing capacity and poison messages |
| DLT ingress/rate/oldest age | Tracks messages needing investigation/replay |
| Producer send failures | Detects output serializer/broker errors |
| ACK/commit/redelivery | Detects loss/duplicates |
| State restoration failures | Essential for Kafka Streams binder |
| Payload size/header size | Detects bloating bytes or metadata |

Logs should include binding name, event ID, schema version, correlation ID, exception class, and build version. Do not log sensitive raw payloads, access tokens, passwords, or full stack traces as widely broadcast headers.

When comparing before and after, use matching sample events and representative load. Avoid declaring an upgrade safe simply because overall error rates are low during the first few minutes; older messages may only surface after a partition rebalance or replay.

## 23. Common evaluation mistakes

| Misconception | What to do instead |
|---|---|
| "Java class didn't change so bytes definitely didn't change" | Compare serializers and byte fixtures |
| "Changing contentType doesn't affect native serializers" | Check both native/framework paths and headers on both sides |
| "Test Binder passed so Kafka header mapper is right" | Read Kafka record headers with a real client |
| "Headers are Strings on every broker" | Pin wire types and test round-trip |
| "Enabling enableDlq catches every deserialization error" | Separate native polling/deserialization from handler errors |
| "Retry 3 means three retries plus the initial attempt" | Verify total attempts per framework |
| "Reactive functions share imperative handler retries" | Test Reactor error operators and binder boundaries |
| "Kafka Streams behaves like the regular Kafka binder" | Check Serdes and `deserializationExceptionHandler` separately |
| "DLQ records always preserve original payload/headers" | Inspect DLT bytes, exception headers, and partitions |
| "Producer send returned means DB and broker committed" | Check callbacks/confirms and outbox/idempotency |
| "Can immediately roll back binary after a schema change" | Test old consumers reading new events |
| "LogAndContinue only changes logging" | Check skipped records and business impact |
| "Header mappers only affect tracing" | Check `contentType`, key/routing/security metadata |

## 24. Pre-approval upgrade checklist

### Serialization

- [ ] Recorded dependency versions, binder types, and function signatures.
- [ ] Identified framework conversion vs. native encoding/decoding mode for each binding.
- [ ] Saved golden fixtures for key/value bytes and old JSON/schemas.
- [ ] Tested old→new, new→old, new→new.
- [ ] Checked `contentType` precedence and target types.
- [ ] Checked schema versions, unknown fields, enums/timestamps/nulls.
- [ ] If using Kafka Streams, tested Serdes for source/sink/repartition/state restore.

### Headers

- [ ] Listed required/optional/internal headers.
- [ ] Checked Kafka `headerPatterns` or corresponding header mapper.
- [ ] Verified header types and bytes on the broker.
- [ ] Verified `contentType`, event ID, correlation ID, schema version.
- [ ] Verified disallowed headers do not leak externally.
- [ ] Checked legacy `headerMode` if applicable.

### Error handling

- [ ] Tested native deserialization, framework conversion, handler, and producer failures.
- [ ] Defined retry budget, backoff, and non-retryable exceptions.
- [ ] Checked DLT routing, partitions, ACLs, raw bytes, and replay.
- [ ] Tested broker restart, consumer crash, and idempotency.
- [ ] Verified ACK/offset outcomes after recovery success/failure.
- [ ] Checked reactive/Kafka Streams/Pulsar-specific policies separately.

### Operations

- [ ] Prepared a canary or test environment with a real broker.
- [ ] Built dashboards separating conversion, header, and error-handler failures.
- [ ] Tested rollback procedure and defined rollout abort criteria.
- [ ] Assigned DLT ownership and replay/reconciliation procedures.
- [ ] Archived data contracts, golden fixtures, and test results.
- [ ] Set timeline to keep compatibility code per retention/replay window.

## Conclusion

Evaluating a Spring Cloud Stream upgrade must go deeper than comparing library versions. **Serialization** determines the bytes producers and consumers understand; the **header mapper** determines whether metadata reaches functions and recipients with the right names, types, and rules; and the **error handler** determines whether failed messages are retried, ACKed, requeued, skipped, or sent to a DLT. A change in one layer can alter behavior in another.

Establish a wire-contract baseline, thoroughly test old/new producers and old/new consumers, including historical data, DLTs, and Kafka Streams state where applicable. Separate native deserialization, framework conversion, business handlers, and outbound publishing into distinct failure paths to verify. Use expand-and-contract or versioned topics when wire contracts are incompatible; maintain idempotency, error observability, and a rollback plan.

**Consider an upgrade safe only when integration tests on the real binder and broker verify bytes, headers, error behavior, and business outcomes**, not merely when the application context boots or Test Binder returns output.

## Official References

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): `contentType`, native encoding/decoding, `headerMode`, retry properties.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): imperative retries, error channels, reactive function caveats.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): `headerPatterns`, `enableDlq`, native deserialization, producer/consumer config.
- [Spring Cloud Stream — Kafka Binder Tips, Tricks and Recipes](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html): handling native deserializer errors and `ErrorHandlingDeserializer`.
- [Spring Cloud Stream — Kafka Streams Record Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/record-serialization-and-deserialization.html): Serde inference, native defaults, and framework value conversion.
- [Spring Cloud Stream — Kafka Streams Error Handling](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/error-handling.html): `logAndFail`/`logAndContinue`/`sendToDlq` and per-binding control.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html): `autoBindDlq`, `republishToDlq`, `requeueRejected`.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html): property precedence and binder integration.
- [Spring Cloud Stream — Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream.html): `contentType` header/binding/default precedence and `MessageConverter`.

Links may open the current stable branch documentation and do not necessarily match your project's dependencies. Before applying a property or relying on a specific default, always cross-check the release guide and source/Javadoc for the exact Spring Cloud Stream, binder, and broker/client versions in deployment.
