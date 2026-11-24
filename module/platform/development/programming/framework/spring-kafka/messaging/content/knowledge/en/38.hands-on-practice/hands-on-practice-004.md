# Configuring JSON Serialization

Kafka stores keys and values as bytes, so a Spring Kafka application must convert Java objects into JSON when publishing and convert JSON back into objects when consuming. Spring Kafka provides `JsonSerializer` and `JsonDeserializer` for both directions. Properly configuring the serializer, deserializer, and type metadata allows producers and consumers to exchange DTOs reliably while avoiding type mismatches, package mismatches, or failures when reading older records.

In this hands-on lab, we build an `OrderCreated` flow: the producer sends events using `KafkaTemplate<String, OrderCreated>`, Kafka stores JSON, and `@KafkaListener` receives `OrderCreated` objects. We also cover how to configure type headers, type mapping, trusted packages, `ObjectMapper`, deserialization error handling, and testing with Embedded Kafka.

## 1. Object-to-JSON Conversion Flow and Back

Sending and receiving involve two conversion steps:

```text
Producer application                         Consumer application

OrderCreated object
       |
       v
JsonSerializer
       |
       v
JSON bytes + optional type headers
       |
       v
      Kafka topic
       |
       v
JSON bytes + headers
       |
       v
JsonDeserializer
       |
       v
OrderCreated object
```

`JsonSerializer` uses Jackson to serialize objects into JSON bytes. `JsonDeserializer` reads bytes and instantiates Java objects. The serializer and deserializer must agree on JSON structure, field names, data types, and how type metadata is handled.

JSON serialization only formats the payload. It does not automatically provide a schema registry, does not fully validate business contracts, and does not guarantee producer/consumer compatibility when DTOs change. If strict schema governance is required, combine it with JSON Schema/Schema Registry or consider Avro or Protobuf according to system needs.

## 2. Creating an Event DTO with a Clear Contract

An event should represent a business event that has occurred, with an identifier and a contract version. For example:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt,
        int eventVersion) {
}
```

The fields in the example each have a specific purpose:

- `eventId`: unique identifier for tracing and duplicate prevention.
- `orderId`: aggregate key, commonly used as the Kafka record key to keep events for the same order on one partition.
- `customerId`: information required by the consumer.
- `totalAmount`: uses `BigDecimal` for monetary values instead of `double`.
- `occurredAt`: timestamp when the business event occurred; timezone and format should be standardized.
- `eventVersion`: contract version managed by the application.

Do not directly serialize JPA entities or internal objects with lazy associations. Create a dedicated event DTO containing only the data that needs to be published and avoiding exposure of internal details.

## 3. Configuring JsonSerializer and JsonDeserializer with Spring Boot

With Spring Boot, you can declare the serializer and deserializer in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: true
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
```

In the example, the producer sends string keys and JSON values. The consumer deserializes the value into a type inferred from the type header or configured as a default. `trusted.packages` restricts the packages containing Java types that the deserializer is allowed to instantiate when processing type metadata.

Replace `com.example.orders.events` with your actual DTO package. Do not configure the `*` wildcard for trusted packages in production unless there is an evaluated security justification.

`auto-offset-reset` and `enable-auto-commit` are consumer settings independent of JSON. They are included so the example can work in a standard listener application; Spring Kafka containers typically manage offsets and set `enable.auto.commit=false` by default unless configured otherwise.

## 4. Sending JSON with KafkaTemplate

When the producer factory uses `JsonSerializer`, `KafkaTemplate` can send DTOs directly:

```java
import java.time.Instant;
import java.util.UUID;
import java.math.BigDecimal;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String customerId,
                        BigDecimal totalAmount) {
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(),
                orderId,
                customerId,
                totalAmount,
                Instant.now(),
                1);

        kafkaTemplate.send("orders", orderId, event);
    }
}
```

Producers do not need to manually call `ObjectMapper.writeValueAsBytes()` in each service. The serializer configured on the producer factory performs the conversion when `KafkaTemplate.send()` sends the record.

In production code, handle the asynchronous result of `send()`: record callbacks/futures when the broker acknowledges or when sending fails. If publishing must stay atomic with a database transaction, use the Outbox pattern or an appropriate transaction coordination mechanism; a JSON serializer does not solve dual writes.

## 5. Receiving JSON with @KafkaListener

When the consumer factory uses `JsonDeserializer`, listeners can receive DTOs directly:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    private final OrderProjectionService projectionService;

    public OrderCreatedListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(topics = "orders", groupId = "order-projection")
    public void onOrderCreated(OrderCreated event) {
        projectionService.apply(event);
    }
}
```

If the producer and consumer share a contract class, type headers can help the deserializer determine the type. If you do not want to couple to the producer's Java package, use type mapping or configure an explicit target type.

## 6. Type Headers: Which Java Type Does the Producer Send?

Under Spring Kafka's common default configuration, `JsonSerializer` adds type information to Kafka headers. `JsonDeserializer` can use this header to decide which class to instantiate. Type metadata headers typically include type ID information, and for complex structures may include key/content type information.

This is convenient when producer and consumer share the exact same Java type. However, if the header contains a fully qualified class name such as `com.producer.contract.OrderCreated`, a consumer in a different package may fail to find the matching class or should not depend on the producer's package name.

There are three common approaches:

1. Share a contract artifact and keep class/package names stable between producer and consumer.
2. Use type mapping to map a stable token to the corresponding class in each application.
3. Disable type headers and configure a default target type on the consumer.

Choose one clear strategy. Do not let a producer rename DTO packages without checking consumers that rely on type headers.

## 7. Type Mapping to Decouple Contracts from Java Packages

Type mapping lets the serializer write a short token into the header instead of the full class name. The consumer maps that token to its own class.

Producer:

```yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.producer.events.OrderCreated
```

Consumer:

```yaml
spring:
  kafka:
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: orderCreated:com.example.consumer.contract.OrderCreated
        spring.json.trusted.packages: com.example.consumer.contract
```

Both applications use the same `orderCreated` token while using Java classes in different packages. The JSON structure of both classes must still be compatible. Type mapping only maps type IDs; it does not rename fields or transform payloads.

When using mappings, check both key and value if the application serializes objects for both. Mapping tokens must match between producer and consumer; changing a token requires a planned rollout.

## 8. Configuring a Default Type and Disabling Type Headers

If a topic only carries a single payload type, the consumer can use a fixed target type instead of reading type headers:

```yaml
spring:
  kafka:
    producer:
      properties:
        spring.json.add.type.headers: false
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.use.type.headers: false
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.trusted.packages: com.example.orders.events
```

In this mode, the producer does not add type headers; the consumer ignores type headers and deserializes the value as `OrderCreated`. This is a simple choice for topics with a single fixed payload schema.

If the same topic carries multiple event types, a single default type is not enough. In that case, you need type mapping, an envelope with an `eventType` field, or separate topics per event type. Do not rely on ad-hoc type inference from JSON content.

## 9. Trusted Packages and Deserialization Safety

When `JsonDeserializer` uses type headers to instantiate objects, you must restrict which packages are allowed. `spring.json.trusted.packages` serves as an allowlist of types permitted for deserialization.

For example, trusting only the contract package:

```yaml
spring:
  kafka:
    consumer:
      properties:
        spring.json.trusted.packages: com.example.orders.contract
```

Avoid `spring.json.trusted.packages: '*'` in production unless genuinely necessary. Topics can receive data from other producers or untrusted environments; arbitrary type metadata must not be allowed to trigger instantiation of classes outside the contract scope.

If the consumer uses a fixed target type with type headers disabled, you can configure the deserializer for that specific class. Even so, still validate the data source, payload size, and business rules. Successful deserialization does not mean a record is valid.

## 10. ObjectMapper and Date/Time Formatting

Jackson's `ObjectMapper` governs how fields, enums, numbers, dates/times, naming strategies, and nulls are serialized/deserialized. Producer and consumer must share consistent conventions.

Expected JSON example:

```json
{
  "eventId": "b3e2c0d0-1234-4567-890a-123456789abc",
  "orderId": "order-42",
  "customerId": "customer-7",
  "totalAmount": 125000.50,
  "occurredAt": "2026-11-17T04:30:00Z",
  "eventVersion": 1
}
```

For `Instant`, use ISO-8601 UTC formatting to avoid depending on the host machine's default timezone. For monetary amounts, use `BigDecimal` and standardize scale/rounding according to business rules. Do not serialize `BigDecimal` as a string on one side if the consumer on the other side expects a JSON number.

Spring Boot normally supplies a configured `ObjectMapper` via Jackson auto-configuration. Spring Kafka also provides an enhanced mapper in its default configurations. If customization is needed, ensure both serializer and deserializer share the same conventions. For example, when adding the Java Time module, verify the module is registered and test the actual output format.

Do not create a divergent `ObjectMapper` per service without contract tests. Differences in `PropertyNamingStrategy`, enum representation, null handling, or unknown properties can make payloads unreadable or misinterpreted.

## 11. Handling JSON Errors with ErrorHandlingDeserializer

If JSON is malformed or cannot be deserialized into the DTO, `JsonDeserializer` can throw an exception directly during `poll()`. When you want the container error handler to handle deserialization errors and route records to recovery/DLT, wrap the delegate with `ErrorHandlingDeserializer`.

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.value.default.type: com.example.orders.events.OrderCreated
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.example.orders.events
```

`ErrorHandlingDeserializer` invokes the delegate deserializer. If the delegate fails, Spring Kafka stores exception metadata in the record headers so the container error handler can process it. Configure an appropriate `DefaultErrorHandler`/recoverer to retry or route failed records to a DLT.

Do not turn every deserialization error into a null value and process it like a valid record. Clearly distinguish valid null payloads, tombstones, and deserialization failures. In compacted topics, a tombstone is a record with a key and a null value that signifies state deletion; it must not be confused with corrupt JSON.

## 12. JSON Schema Evolution and Versioning

JSON does not carry schema compatibility rules by itself. When adding fields, older consumers can ignore new fields if the deserializer/validator permits it. When renaming or removing fields, newer consumers may fail to read older records without fallbacks or defaults in code.

Some guidelines:

- Prefer adding optional fields before requiring producers to populate new fields.
- Consumers should handle potentially missing or null fields according to business rules.
- Never reuse a field name with a different meaning.
- When renaming, deploy consumers that read both old and new names, then have producers dual-write during the transition period if appropriate.
- You can add `eventVersion` or a version header to manage contract changes.
- If automated compatibility validation is needed, use JSON Schema and Schema Registry rather than relying solely on Jackson DTOs.

Do not blindly enable ignoring all unknown properties without evaluation. Ignoring new fields helps forward compatibility, but can also mask contract bugs or drop required data silently.

## 13. Testing JSON Serialization with Embedded Kafka

Integration tests should use real serializers/deserializers to verify that objects survive transit through the broker intact. Example using `@EmbeddedKafka` with a dedicated topic:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.stereotype.Component;

@SpringBootTest
@EmbeddedKafka(
        topics = "orders-json-it",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers")
class OrderJsonSerializationTest {

    @Autowired
    KafkaTemplate<String, OrderCreated> kafkaTemplate;

    @Autowired
    TestOrderListener listener;

    @Test
    void serializesAndDeserializesOrderCreated() throws Exception {
        OrderCreated event = new OrderCreated(
                "event-1", "order-42", "customer-7",
                new BigDecimal("125000.50"),
                Instant.parse("2026-11-17T04:30:00Z"), 1);

        kafkaTemplate.send("orders-json-it", event.orderId(), event)
                .get(10, TimeUnit.SECONDS);

        OrderCreated received = listener.received()
                .poll(10, TimeUnit.SECONDS);

        assertNotNull(received);
        assertEquals(event.eventId(), received.eventId());
        assertEquals(event.orderId(), received.orderId());
        assertEquals(event.totalAmount(), received.totalAmount());
        assertEquals(event.occurredAt(), received.occurredAt());
        assertEquals(event.eventVersion(), received.eventVersion());
    }
}

@Component
class TestOrderListener {

    private final BlockingQueue<OrderCreated> received =
            new LinkedBlockingQueue<>();

    @KafkaListener(
            topics = "orders-json-it",
            groupId = "orders-json-it-group")
    void listen(OrderCreated event) {
        received.add(event);
    }

    BlockingQueue<OrderCreated> received() {
        return received;
    }
}
```

The example assumes the test application has matching producer/consumer JSON properties and `TestOrderListener` is picked up by component scan or declared as a bean. When using `@SpringBootTest`, make sure the test does not accidentally connect to an external local broker outside Embedded Kafka. Use `bootstrapServersProperty` to inject the embedded broker address into Spring Boot configuration.

Do not only assert object equality; also verify the type ID header if the application depends on type headers. If using type mapping or disabling headers, add tests confirming the expected default type or token is applied.

## 14. Inspecting Raw JSON Bytes and Headers When Needed

When diagnosing whether an issue lies in the serializer or deserializer, inspect the raw record with a consumer using `ByteArrayDeserializer` or the Kafka CLI to read the payload. Compare:

- Do the JSON bytes have the right field names and data types?
- Does the payload include required fields or `eventVersion`?
- Are type headers present and is the token/type ID accurate?
- Are correlation ID, trace ID, and event type headers preserved?
- Is the consumer using the right default type, trusted packages, and type mapping?

If the JSON bytes are already wrong, inspect the producer's `ObjectMapper` and DTO. If the bytes are right but deserialization fails, inspect the consumer's deserializer, classpath, type headers, trusted packages, and schema version. Separating these two steps prevents modifying the consumer when the real bug is in the producer.

## 15. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `ClassNotFoundException` on consume | Type header contains a class name missing on the consumer | Use a shared contract, type mapping, or default type |
| `IllegalArgumentException` about trusted packages | DTO package is not in the allowlist | Add the exact required package; do not open a wildcard arbitrarily |
| Consumer receives wrong DTO type | Incorrect type header or mapping | Check `spring.json.type.mapping` and `use-type-headers` |
| JSON parse error | Malformed payload, producer serialization bug, or corrupt record | Inspect raw bytes, configure `ErrorHandlingDeserializer` and DLT |
| New field is null | Old records lack the field or producer is not dual-writing yet | Consumer uses appropriate fallback/default and rolls out in phases |
| Date/time timezone mismatch | `ObjectMapper` or producer uses inconsistent timezones | Use ISO-8601 UTC and test `Instant`/`OffsetDateTime` |
| Enum deserialization fails | Enum constant no longer exists or representation changed | Keep enum contracts compatible or write explicit mapping |
| Consumer unexpectedly ignores type header | `spring.json.use.type.headers=false` or fixed default type | Check deserializer config and whether topic carries multiple event types |
| Listener receives null value | Tombstone or deserialization failure handled by `ErrorHandlingDeserializer` | Distinguish tombstones from errors via headers/error handler |

## 16. Implementation Checklist

- [ ] Producer uses `JsonSerializer` for DTOs and consumer uses matching `JsonDeserializer`.
- [ ] `KafkaTemplate` declares generic types matching the actual payload.
- [ ] Event DTO has a stable contract, event ID, and version where needed.
- [ ] Explicitly chose between type headers, type mapping, or default type.
- [ ] If using type headers, consumer has matching classes/mapping and restricted trusted packages.
- [ ] No arbitrary trusted packages wildcard in production.
- [ ] Producer/consumer align on dates/times, enums, decimals, nulls, and unknown fields.
- [ ] Deserialization errors are routed through `ErrorHandlingDeserializer` and an appropriate error handler/DLT.
- [ ] Tombstones are distinguished from malformed JSON payloads.
- [ ] JSON round-trip tested using real serializer/deserializer.
- [ ] Raw JSON bytes and headers inspected when diagnosing issues.
- [ ] Schema evolution strategy in place when adding, renaming, or removing fields.

JSON serialization in Spring Kafka is configured on the producer and consumer factories: `JsonSerializer` converts DTOs to JSON bytes, and `JsonDeserializer` restores objects. Type headers and type mapping govern class selection; trusted packages restrict which types may be deserialized; `ObjectMapper` governs data formatting. When these pieces are aligned and tested through a broker, producers and consumers can exchange JSON events reliably while keeping clear handling paths for malformed payloads and contract changes.
