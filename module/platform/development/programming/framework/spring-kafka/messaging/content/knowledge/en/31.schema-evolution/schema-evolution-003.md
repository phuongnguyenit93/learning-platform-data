# Adding Backward-Compatible Fields

Adding a field to an event is a common schema change when business requirements need to store additional data. This change can be safe during a rolling deployment if new consumers can still read old events and old consumers can ignore the new field. To achieve that, the new field typically needs to be optional, have a clear default value, and avoid changing the meaning of existing fields.

In the SPRING_KAFKA_MESSAGING module, producers send events with KafkaTemplate and consumers receive events with @KafkaListener. Kafka stores record bytes; serializers and deserializers on both sides interpret those bytes according to the data contract. Because producers and consumers can be deployed at different times, the schema must remain compatible with the versions running concurrently.

## 1. Two compatibility directions to distinguish

Two concepts are often loosely grouped under backward compatibility, yet they actually describe two different directions:

| Compatibility direction | Question | Example when adding a field |
|---|---|---|
| Backward compatibility | Can consumers using the new schema read data written by the old producer? | New consumer reads old events without the priority field |
| Forward compatibility | Can consumers using the old schema read data written by the new producer? | Old consumer encounters the priority field it does not yet know |
| Full compatibility | Can both directions read data produced by the other side? | Rolling deployment with old and new producers/consumers running concurrently |

In a Kafka system, producers and consumers are usually not upgraded simultaneously. Therefore, when adding a field, clarify whether backward, forward, or full compatibility is required. Adding an optional field with an appropriate default is typically the easiest change to support in both directions, provided old consumers have a policy to ignore unknown fields.

## 2. Example event before and after adding a field

Suppose topic orders.created emits events containing eventId, orderId, and total. A new version needs to add priority so downstream services can determine processing priority.

Old event:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "total": 1250000
}
~~~

New event:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "total": 1250000,
  "priority": 2
}
~~~

The priority field needs a rule when absent. For example, old events without priority are interpreted as default priority 0. Do not let each consumer independently interpret a different default value.

## 3. Safe rules when adding a field

- Add the new field as optional or with a default supported by the schema format.
- Define the business meaning of the default value; avoid picking a valid value that causes incorrect behavior.
- New consumers must handle the field being absent in old events.
- Old consumers must ignore the new field if the format and libraries allow unknown fields.
- Do not change the name, data type, or meaning of existing fields in the same change.
- Do not make the new field required immediately while old producers are still emitting events.
- Update the schema contract and test across all supported producer/consumer versions.

A field with a default in the schema is not necessarily written into every payload. The default may only be applied when the reader interprets old data. With JSON, the default keyword in JSON Schema is typically an annotation; validators do not automatically insert the value into JSON. The application must apply the default when the field is missing.

## 4. Adding a field in Java DTOs and JSON

Example old DTO:

~~~java
import java.math.BigDecimal;

public record OrderCreatedV1(
        String eventId,
        String orderId,
        BigDecimal total
) {}
~~~

New DTO adding priority:

~~~java
import java.math.BigDecimal;

public record OrderCreatedV2(
        String eventId,
        String orderId,
        BigDecimal total,
        Integer priority
) {
    public OrderCreatedV2 {
        priority = priority == null ? 0 : priority;
    }
}
~~~

Using Integer instead of int distinguishes an absent or null field from an explicitly sent value of 0. The compact constructor normalizes missing/null cases to the default business value. If null represents a different business state from 0, do not merge those two states.

When a new consumer reads old JSON, Jackson instantiates the new DTO without priority in the payload; the constructor applies the default 0. When an old consumer reads new JSON containing priority, ObjectMapper must be configured to ignore unknown properties:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper objectMapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

OrderCreatedV1 oldConsumerView = objectMapper.readValue(
        newEventJson,
        OrderCreatedV1.class
);
~~~

In Spring Kafka, JsonDeserializer must use an ObjectMapper with the matching policy if the application expects old consumers to ignore new fields. Configure the mapper on the actual deserializer used by ConsumerFactory; creating a standalone ObjectMapper in a test does not alter the mapper running inside the listener container.

Do not rely on the JsonProperty(defaultValue = "0") annotation as an automatic default-injection mechanism during deserialization. The defaultValue attribute is primarily metadata for tooling/schemas; apply defaults explicitly in the constructor, mapper, or data-conversion layer.

## 5. Configuring the JSON deserializer in Spring Kafka

For a consumer receiving only OrderCreatedV2, you can configure the target type explicitly and trust the event package:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.acme.orders.OrderCreatedV2
        spring.json.use.type.headers: false
        spring.json.trusted.packages: com.acme.orders
~~~

This example disables type headers so the consumer uses the configured target type. If the system uses type headers or type mappings, keep that configuration consistent between producer and consumer. Type headers determine the target class, while ObjectMapper's unknown-field policy determines how new properties in JSON are handled.

For applications requiring a customized ObjectMapper, pass that mapper into the JsonDeserializer used by ConsumerFactory. Ensure that mapper handles unknown properties per compatibility requirements while preserving the contract's rules for date/time, numbers, naming strategy, and validation.

The new producer sends DTO V2 via KafkaTemplate:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedV2> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedV2> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedV2>> publish(
            OrderCreatedV2 event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

The new consumer receives DTO V2 via @KafkaListener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService projectionService;

    public OrderProjectionListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @KafkaListener(topics = "orders.created", groupId = "orders-projection")
    public void onOrderCreated(OrderCreatedV2 event) {
        projectionService.apply(event);
    }
}
~~~

The application service contract invoked by the listener:

~~~java
public interface OrderProjectionService {
    void apply(OrderCreatedV2 event);
}
~~~

This example assumes the producer factory uses JsonSerializer for values and the consumer factory uses JsonDeserializer with target type V2 and the ObjectMapper described above. DTO types and serializer/deserializer settings must be configured in sync; changing a Java DTO does not automatically update schemas or configurations in other services.

## 6. JSON Schema: new fields should be optional

With JSON Schema, the new field can be declared in properties without adding it to the required list:

~~~json
{
  "type": "object",
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "total": { "type": "number" },
    "priority": { "type": "integer", "default": 0 }
  },
  "required": ["eventId", "orderId", "total"],
  "additionalProperties": true
}
~~~

Here priority is not in required, so old events remain valid under the new schema. additionalProperties: true lets the old schema accept the new field when producers emit events with priority. If the current contract sets additionalProperties: false, old consumers/schemas may reject new events; review the unknown-fields policy before rollout.

JSON Schema default does not automatically mutate the payload during validation. Consumers must apply defaults at the application layer, such as normalizing the DTO after deserialization. If using Schema Registry, verify the compatibility mode and validate the actual schema with registry tooling; do not infer compatibility solely from the presence of a default attribute in JSON Schema.

## 7. Avro: new fields must have a default in the reader schema

Avro supports schema resolution between the writer schema and reader schema. When a new consumer reads a record written with an old schema, a field present in the reader schema but absent from the writer schema needs a default in the reader schema.

Old schema:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" }
  ]
}
~~~

New schema adding priority:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "total", "type": "long" },
    { "name": "priority", "type": ["int", "null"], "default": 0 }
  ]
}
~~~

Default 0 must match the first branch of the union type in this example. If using the union ["null", "int"], the default must be null because the first branch is null. Avro's default rule is part of schema resolution, unlike JSON Schema's default annotation.

Old consumers using the old reader schema can ignore the priority field added by the new writer schema. New consumers using the new reader schema can read old records and receive the default 0 for priority. This is why adding an Avro field with a default is usually a well-compatible change.

## 8. Protobuf: add fields with a new field number

With Protobuf, field numbers are critical wire identifiers. You can add a new optional field with an unused number:

~~~proto
syntax = "proto3";

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  int64 total = 3;
  optional int32 priority = 4;
}
~~~

Old consumers unaware of field number 4 skip the unknown field on the wire format. New consumers reading old messages without priority see the field as unset; for proto3 scalars, the default getter value is 0. The optional keyword lets you check presence via hasPriority() to distinguish an omitted field from an explicitly sent 0.

Proto3 optional is supported in modern protoc versions (from 3.12 onward); check the project's compiler/plugin before using this syntax.

Do not reuse deleted field numbers. If removing a field, reserve both the number and name in the message schema:

~~~proto
message OrderCreated {
  reserved 4;
  reserved "priority";
}
~~~

Do not change the field number or alter the wire type of an existing field simply because its name stays the same. With Protobuf, changing numbers or types can cause consumers to misinterpret bytes.

## 9. Adding a field with a default does not make it required

A default is a fallback value when old data lacks the field. It neither means new producers must always emit that field nor proves every new event is business-valid.

Before adding a field, answer:

- What is the default value and who owns that business decision?
- Can the field be null, or only absent?
- Are 0, false, or an empty string real valid values?
- Does the consumer need to distinguish "unknown" from "default value"?
- Does historical data need backfilling or only read-time defaults?

For example, priority = 0 might mean "normal", whereas an absent field means "unspecified". If the two states differ, use a nullable/presence-aware type instead of collapsing every case to 0.

## 10. Safe rolling deployment execution

When producers and consumers are deployed independently, the rollout order reduces risk as follows:

1. **Expand consumers first:** deploy new consumers able to read old events missing the field and tolerate the new field if present.
2. **Verify compatibility:** confirm new consumers can read historical data and the current producer version.
3. **Upgrade producers:** only after new consumers are ready do new producers begin emitting the priority field.
4. **Monitor:** track deserialization errors, validation failures, missing-field rates, and default business behavior.
5. **Maintain compatibility during the support window:** do not remove fallbacks while old records still remain in retention, retry topics, or DLT that could be replayed.

If old consumers can still run while new producers emit events, verify that old consumers ignore unknown fields. Otherwise, complete the consumer rollout before enabling the new producer or use a versioned topic/contract to separate streams.

## 11. Schema Registry and compatibility modes

If using Schema Registry, the compatibility policy checks the relationship between the new schema and already-registered schemas:

| Mode | High-level check direction | Meaning when adding a field |
|---|---|---|
| BACKWARD | New schema reads data from the previous schema | New consumer reads old records |
| BACKWARD_TRANSITIVE | New schema reads data from all previous versions | Suitable when very old historical records exist |
| FORWARD | Previous schema reads data from the new schema | Old consumer reads new records |
| FULL | Checks both backward and forward | Useful for rolling deployments needing both directions |
| FULL_TRANSITIVE | Both directions across all previous versions | Stricter policy for multi-version history |

Mode names and applicability depend on the Schema Registry in use. With Avro, a new field having a default is a key rule for backward compatibility. With JSON Schema, check required/additionalProperties and how the validator enforces the schema. With Protobuf, keep field numbers and wire types safe.

Registry compatibility checks do not replace integration tests. The registry validates schemas according to format rules; it does not know all business invariants, Java validations, or listener side effects.

## 12. Changes you should not bundle with adding a field

Avoid combining a field addition with changes that break the contract:

- Renaming an old field without keeping a compatible alias/mapping.
- Changing a numeric type from int to string or altering the wire type.
- Changing a field's unit, such as total from VND to thousands of VND, while keeping the same name.
- Adding a field to required in JSON Schema while old producers are not yet sending it.
- Adding @NotNull validation for the new field before all old events have been processed/backfilled.
- Changing the meaning of the default value across consumers.
- Removing an old field as soon as new producers start emitting the new field.

If an incompatible change is needed, consider an explicit event version, a new topic version, or a dedicated expand/contract phase. Do not use schemaVersion to rationalize consumers being unable to read payloads; concrete routing and compatibility logic is still required.

## 13. Compatibility testing for Spring Kafka

Build a test matrix across producer and consumer versions:

| Producer | Consumer | Outcome to verify |
|---|---|---|
| Old | Old | Existing behavior unchanged |
| Old | New | New field receives the proper default |
| New | Old | Old consumer ignores the new field |
| New | New | New field is read and processed properly |

Key tests:

- **JSON old-to-new:** deserialize old payload into new DTO; verify priority receives the intended default.
- **JSON new-to-old:** deserialize new payload into old DTO; verify unknown fields are ignored according to the actual ObjectMapper configuration.
- **Avro resolution:** read records written with the old writer schema using the new reader schema.
- **Protobuf compatibility:** old consumer reads new messages with the new field number; new consumer reads old messages and checks presence/defaults.
- **Spring Kafka integration:** send records via KafkaTemplate and receive via @KafkaListener using real serializers/deserializers.
- **Rolling deployment test:** verify old and new consumer/producer versions coexist during upgrades.
- **Replay test:** re-read old records from retry topics/DLT after consumers have been upgraded.

Use Embedded Kafka or Testcontainers for Spring Kafka flows. If using Schema Registry, run compatibility checks on candidate schemas before publishing the new schema and test serialization/deserialization through real serializers.

## 14. Common pitfalls

- **Confusing backward with forward compatibility:** new consumer reading old data and old consumer reading new data are two distinct directions.
- **Making a field required immediately:** old events missing the field will fail deserialization or validation.
- **Assuming JSON Schema default auto-inserts values:** the application must apply defaults when a field is absent.
- **Failing to configure Jackson's unknown-property policy:** old consumers may reject JSON containing new fields.
- **Using primitives and failing to distinguish missing from zero:** choose nullable/presence-aware types when business logic requires distinguishing them.
- **Avro union default not matching the first branch:** schema resolution fails.
- **Reusing Protobuf field numbers:** old data may be misinterpreted.
- **Testing DTOs only with a separate ObjectMapper:** ConsumerFactory's real JsonDeserializer configuration may differ.
- **Upgrading producers before consumers:** old consumers may receive new payloads they do not yet support.
- **Removing fallbacks too early:** historical records, retries, and DLT messages may still be replayed.
- **Relying solely on Schema Registry compatibility:** a valid schema does not guarantee compatible business logic.

## 15. Checklist for adding a compatible field

- [ ] Identified the required compatibility direction: backward, forward, or full.
- [ ] The new field has a clear type and business meaning.
- [ ] A default/fallback is defined and tested.
- [ ] JSON Schema does not require the new field while old producers remain.
- [ ] Old JSON consumers handle unknown properties per a clear policy.
- [ ] New Avro fields have a valid default matching the union branch.
- [ ] Protobuf uses a new field number and does not reuse reserved numbers.
- [ ] Spring Kafka JsonDeserializer/serializer uses the proper contract and ObjectMapper.
- [ ] Schema Registry compatibility mode aligns with the rollout strategy.
- [ ] New consumers are deployed before new producers when required.
- [ ] A test matrix exists for old/new producers against old/new consumers.
- [ ] Retry topics, DLT, and historical records remain readable after rollout.
- [ ] Renames, type changes, or semantic changes are not bundled into the same migration.

Adding a compatible field is more than editing a DTO. You must define the compatibility direction, default rules, unknown-field handling, and producer/consumer rollout order. When both schema and application support old and new data together, Spring Kafka can continue operating smoothly through rolling deployments without forcing every service to upgrade simultaneously.
