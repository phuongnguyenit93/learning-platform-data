# Evolving Data Contracts and Handling Incompatible Messages

> **Chapter:** Reliability  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Focus:** Designing message contracts that can evolve when producers and consumers deploy independently; understanding backward/forward/full compatibility, schema registries, writer/reader schemas, data transformation, quarantining unreadable messages, and safe recovery in Spring Cloud Function applications.  
> **Context:** Examples use Java 21 and Spring Cloud Function. Schema Registry compatibility rules are stated according to Confluent's implementation; do not assume they are universal mandatory rules across every registry.

## 1. Why Must Data Contracts Evolve Under Control?

In event-driven systems, producers and consumers are typically built, deployed, and scaled independently. A producer may emit new events while older consumers are still running; queues may hold messages across multiple deployments; a message emitted last week may be replayed after the current schema has changed.

For example, an Order service publishes:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "currency": "VND"
}
~~~

Months later, the team wants to add `discountCode`, rename `customerId` to `buyerId`, and change `total` from an integer to a decimal. Those changes look small in code, yet can affect:

- Consumers currently reading old messages.
- Older consumers still receiving new messages during a rollout.
- Consumers re-reading long-lived archived messages.
- Consumers written in other languages or frameworks.
- Messages held in a DLQ and replayed after code upgrades.
- Analytics or audit systems reading historical data.

**A data contract is an agreement between writer and reader.** Changing one Java DTO does not automatically upgrade every producer, consumer, queue, or stored record.

Spring Cloud Function helps decouple business logic from invocation protocols. To preserve that benefit, the application needs an adapter/converter layer capable of recognizing data versions, transforming messages into application types, and failing explicitly when conversion is impossible.

## 2. Three Version Layers to Distinguish

Never collapse every kind of version into a single `version` field.

| Concept | Meaning | Example |
| --- | --- | --- |
| Event type/version | Business event kind and occurrence semantics. | com.acme.order.created.v1 |
| Schema version | Data structure used for serialization/deserialization. | Avro subject order-created, version 3 |
| Application/runtime version | Version of code processing the message. | orders-consumer 2.7.0, Java 21 |

An event type can remain unchanged when the schema gains an optional field. Conversely, a change in business meaning may require a new event type even if the JSON fields look nearly identical.

When using CloudEvents, `specversion` is the envelope specification version; it is not the payload version. Identify the schema version via `dataschema`, a registry schema ID/version, or an explicit application convention.

### 2.1. Event Type Answers "What Happened?"

Examples:

- com.acme.order.created.v1
- com.acme.order.cancelled.v1
- com.acme.order.refunded.v1

The type is not a function bean name. One `order.created` event can be handled by multiple functions: updating inventory, sending email, writing audits, or awarding points.

### 2.2. Schema Version Answers "Which Structure Does the Payload Have?"

For example, schema version 1 has:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000
}
~~~

Schema version 2 adds an optional field:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "discountCode": null
}
~~~

Both payloads can describe the same `order.created` occurrence. Whether the new schema can read old data depends on the format, defaults, required fields, and compatibility policy.

## 3. Writer Schema and Reader Schema

When serializing a message, the producer uses the **writer schema**. When deserializing, the consumer holds the **reader schema** expected by its current code.

For example:

- Producer version 1 writes `OrderCreatedV1`.
- Consumer version 2 reads `OrderCreatedV2`.
- A schema resolver needs both the writer schema and the reader schema to decide whether conversion can succeed.

~~~mermaid
flowchart LR
    P["Producer v1"] --> WS["Writer schema v1"]
    WS --> M["Message + schema reference"]
    M --> R["Consumer v2"]
    RS["Reader schema v2"] --> R
    R --> D["Schema resolution"]
    D -->|Compatible| O["Application object"]
    D -->|Incompatible| Q["Quarantine / DLQ"]
~~~

In Avro, binary payloads do not embed full field names and types for the consumer to guess the schema. The reader needs the writer schema to decode the bytes, after which Avro performs schema resolution between writer and reader schemas. https://avro.apache.org/docs/current/specification/

In some other serializers, schema ID metadata sits in a wire-format prefix or message header. Never assume every message carries schema references the same way.

### 3.1. Example of a Potentially Compatible Change

Old schema:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"}
  ]
}
~~~

New schema adding a field with a default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "customerId", "type": "string"},
    {
      "name": "discountCode",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

When the new reader schema reads data written with the old schema, `discountCode` can be populated with default `null`. This is a common backward-compatible change pattern in Avro.

### 3.2. Defaults Do Not Automatically Fix Invalid Data

Defaults only operate according to the format's resolution rules. They cannot:

- Turn `"unknown"` into a valid customer ID.
- Convert currency units from VND to thousands of VND.
- Infer a missing currency.
- Repair a field written wrongly by a producer.
- Resolve a change in a field's business semantics.

Never supply fake defaults like `0`, `""`, or current timestamps just to get the parser past errors. A message that parses cleanly with wrong business meaning can do more harm than a rejected message.

## 4. Backward, Forward, and Full Compatibility

These terms describe readability between producer and consumer schemas. The conventions below reflect the common Schema Registry interpretation:

| Compatibility | Question | Reading Direction |
| --- | --- | --- |
| Backward | Can the new reader schema read data written by the old schema? | New reader ← Old writer |
| Forward | Can the old reader schema read data written by the new schema? | Old reader ← New writer |
| Full | Do both directions work? | New reader ↔ Old writer |
| None | Are compatibility checks run before registering a schema? | No guarantee from registry |

In Confluent Schema Registry, `BACKWARD` is the default and checks the new schema against the latest registered version. `BACKWARD_TRANSITIVE` checks against all prior versions. `FORWARD`, `FULL`, and their transitive variants behave analogously. Exact rules vary across Avro, Protobuf, and JSON Schema. https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html

### 4.1. Backward Compatibility

The new schema can read data written using the old schema.

Example: a new consumer reads an old message lacking `discountCode`; the reader schema supplies default `null`.

Backward compatibility helps when upgrading consumers first, then letting producers emit the new schema. New consumers are already prepared to read old messages before producers switch formats.

### 4.2. Forward Compatibility

The old schema can read data written using the new schema.

Example: a new producer adds an optional field, and the old consumer skips unknown fields if its format and parser permit it.

Forward compatibility helps when producers upgrade first while older consumers remain active. Still, not every parser ignores unknown fields; a closed JSON Schema object can reject new fields.

### 4.3. Full Compatibility

Full compatibility requires both backward and forward directions to hold.

This helps during rolling deployments when old and new producers and consumers coexist temporarily. Even so, full compatibility between two adjacent versions does not guarantee compatibility with much older messages.

### 4.4. Transitive Compatibility

Suppose a system has schemas v1, v2, v3, and v4:

- Non-transitive checks v4 only against v3.
- Transitive checks v4 against all prior versions covered by the policy.

This matters for long-retention queues, event archives, replays, or consumers offline for months. A change can be compatible with the immediate predecessor while breaking v1.

### 4.5. Compatibility Does Not Imply Semantic Correctness

A registry can verify structural compatibility without knowing that:

- `total` used to be VND and the producer now sends USD.
- `customerId` changed from a CRM ID to a loyalty ID.
- `createdAt` used to be UTC and is now sent in local time.
- A new enum value carries meaning that old consumers do not understand.

Schema compatibility is an important guardrail, yet never replaces contract reviews and business testing.

## 5. Safe Changes vs. Breaking Changes

### 5.1. Changes That Are Usually Easier to Keep Compatible

- Adding optional fields with appropriate defaults.
- Adding metadata that does not alter existing field meanings.
- Adding extensions that consumers are designed to ignore.
- Expanding enums when consumers have an unknown-value strategy.
- Adding new fields when existing consumers already ignore extra properties.

Actual compatibility still depends on format and parser configuration. There is no universal "adding a field is always safe" rule across every system.

### 5.2. Changes That Risk Breaking Consumers

| Change | Risk |
| --- | --- |
| Removing a field consumers require | Consumers fail to read or lose data. |
| Adding a required field without a default | Old or new readers may fail to instantiate objects. |
| Renaming a field | Old consumers cannot find the field; new data may not map. |
| Changing a field's data type | Deserialization fails or loses precision. |
| Changing a field's meaning or unit | Parses cleanly yet produces wrong business behavior. |
| Removing an enum value still in use | Consumers or producers fail on historical values. |
| Changing nesting/path | JSONPath expressions, mappers, or generated code can break. |
| Changing timestamp timezone/format | Wrong point in time even when values still parse. |

### 5.3. Example: Renaming a Field

Never rename `customerId` directly to `buyerId` in one deploy if consumers are not synchronized.

A phased transition:

1. Producer emits both `customerId` and `buyerId` during migration, provided both fields genuinely mean the same thing.
2. New consumers read `buyerId` while still supporting legacy `customerId`.
3. Monitor how many consumers still rely on the old field.
4. Stop emitting the old field once all consumers have migrated.
5. Remove the old field only in a later schema version after accounting for retention and replay windows.

If the two fields do not mean the same thing, never mirror values solely to preserve compatibility. Introduce a new event type or schema version with explicit business mapping.

## 6. Evolution Rules by Schema Format

A single compatibility mode does not behave identically across serialization formats. Know the rules for your chosen format.

### 6.1. Avro

Avro performs schema resolution using both writer schema and reader schema.

Practical notes:

- When adding a field to a record, the reader schema needs a default to read older data lacking the field.
- Nullable fields typically use a union with `null`, e.g. `["null", "string"]`.
- A field's default in Avro must match the first branch of its union.
- Fields present in the writer schema and omitted in the reader schema can be ignored per resolution rules.
- Type changes are safe only for Avro-supported promotions; never assume all numeric changes are safe.
- Binary payloads require the writer schema for accurate deserialization.

Example optional field:

~~~json
{
  "name": "deliveryNote",
  "type": ["null", "string"],
  "default": null
}
~~~

Do not confuse nullable with having a default. A field allowing `null` without a `default` still fails when an old message omits the field entirely.

Documentation: https://avro.apache.org/docs/current/specification/

### 6.2. Protocol Buffers

Protobuf uses field numbers as wire identifiers. Field names can sometimes change without breaking binary wire decoding, whereas field numbers must never be changed or reused.

Example:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  string customer_id = 2;
  int64 total_minor_units = 4;

  reserved 3;
  reserved "legacy_customer_code";
}
~~~

When deleting a field:

- Reserve the removed field number.
- Reserve the field name if protecting JSON/TextFormat compatibility.
- Never reuse an old tag number for a new field.
- Never change an active field's type merely because Java code can cast it.
- Adding enum values requires consumers to handle unknown values safely.

Reusing a field number can silently decode old bytes as a completely different field—far worse than a normal deserialization exception. https://protobuf.dev/programming-guides/proto3/

### 6.3. JSON Schema

JSON Schema describes JSON structure and validation. JSON Schema itself does not mandate one universal compatibility mode for every registry.

A key setting is whether an object allows undeclared fields:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "customerId": {"type": "string"}
  },
  "required": ["orderId", "customerId"],
  "additionalProperties": true
}
~~~

With `additionalProperties: true`, objects may carry fields beyond those listed. With `false`, consumers or validators may reject unknown new fields.

In Confluent Schema Registry, JSON Schema compatibility also depends on `compatibilityPolicy` (`LENIENT` vs. `STRICT`) and open vs. closed content models (`additionalProperties`). Always verify actual registry policy rather than reading only the JSON Schema file. https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html

### 6.4. Format Comparison

| Criterion | Avro | Protobuf | JSON Schema |
| --- | --- | --- | --- |
| How schema is described | Record/union/type in Avro schema. | Messages, field numbers, enums. | JSON Schema document. |
| Schema metadata | Writer schema must be resolved to decode binary. | Descriptor/proto contract and wire tags. | Schema URI / registry reference per app. |
| Adding a field | Supply suitable default for old/new readers. | Use a fresh tag number; optional fields fit. | Depends on `required`, `additionalProperties`, and registry policy. |
| Removing a field | Governed by reader resolution and defaults. | Reserve removed tag and name. | Check `required`, `properties`, and open/closed objects. |
| Special hazard | Missing writer schema or mismatched default. | Reusing field numbers corrupts wire decoding. | Closed parser/policy rejects new fields. |
| Verification tools | Avro schema resolution / registry. | `protoc` and compatibility checkers. | JSON Schema validator / registry compatibility check. |

## 7. What Does a Schema Registry Help With—and Not Help With?

A Schema Registry stores schemas by subject/version, supplies schema references to producers and consumers, and checks compatibility upon registering new schemas.

A typical workflow:

1. Producer obtains or derives the schema from the payload type.
2. Producer registers the schema with the registry.
3. Registry returns a schema version or ID.
4. Serializer writes schema reference/metadata into the message.
5. Consumer reads the reference to fetch the writer schema.
6. Consumer uses its application's reader schema to deserialize.
7. If incompatible or missing, errors follow the failure policy.

A Schema Registry can block breaking schemas before deployment when compatibility checks are enabled. It does not guarantee consumer code is free of business bugs, does not automatically upgrade running apps, and cannot rescue messages written with deleted schemas.

### 7.1. Compatibility Mode Must Match the Rollout

Confluent Schema Registry modes:

~~~text
BACKWARD
BACKWARD_TRANSITIVE
FORWARD
FORWARD_TRANSITIVE
FULL
FULL_TRANSITIVE
NONE
~~~

`NONE` skips compatibility checks; never select it just to push a schema through in production.

For long-term event replays, consider transitive modes. If new consumers only need to read the immediately preceding version and historical data has been migrated/retired, non-transitive may suffice—always decide based on retention and replay policies.

### 7.2. A Registry Is Not a Message Broker

The registry is not responsible for:

- Delivering messages.
- Consumer retries.
- Ack/nack.
- Partition ordering.
- Routing failed messages to a DLQ.
- Keeping schema IDs alive for as long as messages remain stored.

Align schema retention with message and archive retention. Deleting schemas still referenced by stored events renders historical messages unreadable.

## 8. Rolling Out Changes via Expand–Migrate–Contract

A safe rollout widens reading capability first, switches producers later, and cleans up old fields last.

~~~mermaid
flowchart TD
    A["1. Expand schema: add optional field"] --> B["2. Deploy consumer reading both old and new"]
    B --> C["3. Confirm all consumers are ready"]
    C --> D["4. Deploy producer writing new field"]
    D --> E["5. Monitor old, new, and replayed messages"]
    E --> F["6. Stop writing old field"]
    F --> G["7. Wait out retention / replay window"]
    G --> H["8. Contract: remove old field in a later schema"]
~~~

### 8.1. Expand

- Add new fields as optional when the format supports it.
- Supply meaningful defaults.
- Keep old fields in the schema.
- Register the schema and run compatibility checks.
- Verify consumers parse both old and new messages.

### 8.2. Migrate

- Deploy consumers first if using backward compatibility.
- Verify new consumers are live across all instances and regions.
- Begin emitting the new field from producers.
- Monitor metrics by schema version and consumer version.
- Watch message backlogs and DLQs.

### 8.3. Contract

- Stop emitting the old field.
- Wait out old message retention or ensure readers still support them.
- Remove the old field only after verifying all consumers, replay jobs, and analytics readers.
- Keep historical schemas as long as referenced data exists.

Never drop a field right after deploying the new producer. Queues can still hold older messages and DLQs can retain messages well past deployment time.

### 8.4. When Is Full Compatibility Needed?

During rolling deployments, producers and consumers may upgrade out of order. When rollout order cannot be enforced or many independent consumers exist, full compatibility lowers risk.

Still, full compatibility restricts schema evolution. For genuinely breaking changes, introducing a new versioned event type and running two paths in parallel is often cleaner than forcing one schema across incompatible generations.

## 9. Message Versioning and Upcasting Old Data

When consumers want one stable internal model, an adapter or upcaster can map older schemas into a canonical model.

Example:

~~~text
OrderCreatedV1 ----\
                    +--> OrderCreatedCanonical --> processOrder
OrderCreatedV2 ----/
~~~

- `OrderCreatedV1` preserves the old structure.
- `OrderCreatedV2` includes the new field.
- The upcaster converts both into `OrderCreatedCanonical`.
- The business function processes only the canonical model.

Java example:

~~~java
public record OrderCreatedV1(
        String orderId,
        String customerId,
        long total) {
}

public record OrderCreatedV2(
        String orderId,
        String customerId,
        long total,
        String discountCode) {
}

public record OrderCreatedCanonical(
        String orderId,
        String customerId,
        long total,
        String discountCode,
        int schemaVersion) {
}

public final class OrderUpcaster {

    public OrderCreatedCanonical fromV1(OrderCreatedV1 oldEvent) {
        return new OrderCreatedCanonical(
                oldEvent.orderId(),
                oldEvent.customerId(),
                oldEvent.total(),
                null,
                1);
    }

    public OrderCreatedCanonical fromV2(OrderCreatedV2 newEvent) {
        return new OrderCreatedCanonical(
                newEvent.orderId(),
                newEvent.customerId(),
                newEvent.total(),
                newEvent.discountCode(),
                2);
    }
}
~~~

This is a simple mapping example. In production, upcasters must validate required values, units, currencies, timestamps, and business invariants. Never plug in `null` if the new field is mandatory semantically; perform a proper business migration or reject the message.

### 9.1. Upcasting Does Not Mutate Original Messages

Keep the original message and schema reference intact for audits and replays. Upcasting produces an in-memory representation for the current consumer; never overwrite historical records without a dedicated migration process.

### 9.2. Do Not Use One Canonical Model to Hide Every Difference

If v1 and v2 carry different semantics, the canonical model must capture the difference or split event types. Forcing two differently defined payloads into one field lets parsing succeed while corrupting business logic.

## 10. Handling Incompatible Messages

An unreadable message can stem from multiple causes. Classify before choosing retry or quarantine.

| Cause | Typical Category | Action |
| --- | --- | --- |
| Schema ID missing due to transient registry outage | Transient | Bounded retry with backoff. |
| Schema ID permanently deleted | Permanent / configuration | Quarantine, restore schema or mapping. |
| Schema version newer than consumer supports | Incompatible version | Quarantine or route to newer consumer. |
| Malformed JSON syntax | Poison message | Quarantine; do not retry infinitely. |
| Missing required field | Contract violation | Quarantine and investigate producer. |
| Wrong or missing `Content-Type` | Integration / configuration | Fix adapter/producer; keep raw message for replay. |
| Consumer bug on valid payload | Application failure | Retry if transient; otherwise DLQ. |
| Temporary database outage | Transient | Retry per policy. |
| Payload parses yet violates business meaning | Semantic incompatibility | Reject/quarantine; fix contract or mapping. |

### 10.1. Schema Incompatibility Is Usually Permanent for the Same Consumer Build

If a consumer does not understand schema version 5 and has no decoder/upcaster for it, retrying the exact same binary against the same build rarely helps.

Infinite retries can:

- Stall partition/queue backlogs.
- Increase cost.
- Block valid messages behind the failing one.
- Trigger retry storms.
- Obscure failing messages.

Quarantine or DLQ unrecoverable messages once identified. Conversely, when the schema registry is temporarily unreachable, that is a transient error suited for bounded retries.

### 10.2. Quarantine and DLQ Serve Different Roles

- **Quarantine:** an isolated store holding unprocessable messages, commonly used for invalid payloads/schemas or failures needing investigation.
- **DLQ:** a broker/binder destination receiving messages after retries exhaust or rejection per delivery policy.

A system may use a DLQ as its quarantine destination, provided ownership is clear for triage, fixes, and replays. Never let failed messages be deleted silently.

### 10.3. Metadata to Retain When Quarantining

An error record should keep:

- Raw payload or a safe copy of the original bytes.
- Message headers and content type.
- Schema ID/version or schema reference.
- Event ID and source/producer.
- Destination/topic/partition/offset or queue metadata when available.
- Consumer name and application build/version.
- Error category and error code.
- Receipt timestamp, attempt count, and correlation/trace ID.
- Processing status and redrive owner/procedure.

Never dump raw sensitive payloads into uncontrolled logs. Apply encryption, access policies, retention, and auditing.

## 11. Procedure for Redriving Failed Messages

Redriving replays quarantined messages. It carries the risk of duplicate side effects or repeated failures.

Before replaying:

1. Identify the root cause: producer contract, schema registry, consumer code, or dependency.
2. Fix the cause and deploy the needed decoder/upcaster.
3. Verify original schemas remain retrievable.
4. Check whether the message already produced partial side effects.
5. Preserve the original event ID and idempotency key.
6. Test a small batch in a controlled environment.
7. Rate-limit replay throughput to avoid load spikes.
8. Monitor successes/failures and record an audit trail.

Never hand-edit payloads in a DLQ without controlled procedures. When transforming data, preserve the original, the transformed record, and the mapping version.

## 12. Integrating with Spring Cloud Function

### 12.1. FunctionCatalog Is Not a Schema Registry

`FunctionCatalog` manages lookups/wrappers for functional beans, composition, and certain conversion mechanisms. It does not register schemas, retain writer schema histories, or enforce compatibility policies.

When a function accepts `Message<?>`, Spring Cloud Function uses `MessageConverter` and `ConversionService` to convert the payload into the function's parameter type. Converter selection depends on the target type and `contentType` header; if no converter matches, the framework throws an exception. https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html

Therefore, separate responsibilities:

| Component | Responsibility |
| --- | --- |
| Producer serializer | Serializes payloads using the chosen schema. |
| Schema Registry | Stores schemas/versions and checks compatibility per policy. |
| Broker / binder | Delivers messages, retries, ack/nack, DLQ per capability. |
| Adapter / message converter | Reads content type / schema reference, deserializes, builds `Message`. |
| `FunctionCatalog` | Looks up / wraps functions and integrates invocation/conversion. |
| Business function | Executes business logic on validated models. |
| Quarantine service | Persists unprocessable messages for triage/redrive. |

### 12.2. Spring Cloud Stream Integrates Avro Schema Registry

Spring Cloud Stream can use `SchemaRegistryClient` to register Avro schemas on send and look up writer schemas on receive. The converter encodes subject/version in `contentType`; on read, it fetches the writer schema and resolves it against the consumer's reader schema. `spring.cloud.stream.schema.avro.readerSchema` configures a local reader schema. https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html

This is a Spring Cloud Stream and schema-registry integration capability, not `FunctionCatalog` alone.

Illustrative binding configuration:

~~~properties
spring.cloud.function.definition=processOrder
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=orders-v2
spring.cloud.stream.bindings.processOrder-in-0.content-type=application/*+avro
~~~

The binding name `processOrder-in-0` derives from the function definition per functional binding conventions. Real deployments also require the appropriate binder, broker, and `SchemaRegistryClient`.

### 12.3. Consumer Function Receiving a Deserialized Model

~~~java
@Bean
public Consumer<OrderCreatedCanonical> processOrder(
        OrderService orderService) {

    return event -> orderService.createOrder(
            event.orderId(),
            event.customerId(),
            event.total(),
            event.discountCode());
}
~~~

The business function receives the canonical model. It does not need to know whether the wire message used Avro, JSON, or Protobuf once the adapter converts it cleanly.

### 12.4. When Should You Accept Raw Bytes?

To explicitly classify schema incompatibilities before business functions run, an adapter can receive `Message<byte[]>`:

~~~java
@Bean
public Consumer<Message<byte[]>> ingestOrder(
        OrderDecoder decoder,
        OrderQuarantine quarantine,
        OrderService orderService) {

    return message -> {
        try {
            OrderCreatedCanonical event =
                    decoder.decode(message.getPayload(), message.getHeaders());

            orderService.createOrder(event);
        } catch (UnsupportedSchemaException exception) {
            // Return normally only after quarantine persistence succeeds.
            quarantine.store(message, "UNSUPPORTED_SCHEMA", exception);
        } catch (TemporaryRegistryException exception) {
            // Let the binder/trigger retry per policy.
            throw new RetryableMessageException(exception);
        }
    };
}
~~~

This is illustrative code; `OrderDecoder`, `OrderQuarantine`, and exceptions are application abstractions. To genuinely receive raw bytes, the binding/adapter must preserve the raw payload (e.g. `application/octet-stream` or custom converters); changing the signature to `Message<byte[]>` alone does not guarantee every binder skips prior deserialization. In production:

- `UnsupportedSchemaException` is quarantined only after raw message persistence succeeds.
- If storing to quarantine fails, throw an exception so the message is not acked.
- Transient registry failures should use bounded retries.
- Never catch every `Exception` and return normally, or the binder may consider the message succeeded.
- If the framework deserializes before invoking the function, exceptions happen outside `ingestOrder`. Use raw bytes when you need control over decoding, or configure a binder-appropriate error handler.

## 13. Retries, DLQs, and Binder-Specific Behavior

Spring Cloud Function does not define one universal DLQ across all transports. With Spring Cloud Stream, the binder and broker govern available features.

### 13.1. Exceptions Must Reach the Error-Handling Layer

When a message handler throws, Spring Cloud Stream can forward the exception to the binder. The binder may retry and then drop, requeue, or route to a DLQ depending on configuration and middleware capabilities. Not every binder behaves identically. https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html

### 13.2. Kafka Binder Example

The Kafka binder supports DLQs for consumers belonging to a consumer group. Example configuration:

~~~properties
spring.cloud.function.definition=processOrder
spring.cloud.stream.bindings.processOrder-in-0.destination=orders
spring.cloud.stream.bindings.processOrder-in-0.group=orders-v2
spring.cloud.stream.bindings.processOrder-in-0.consumer.max-attempts=3
spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq=true
~~~

With DLQ enabled, the binder can forward failing records to a dead-letter topic after exhausting configured retries. DLQs are not enabled by default, and a consumer group is an essential requirement. Verify exact behavior against your active binder version. https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html

### 13.3. Classify Exceptions Before Retrying

A straightforward policy:

| Exception Category | Action |
| --- | --- |
| Temporary network / registry error | Bounded retry. |
| Database unavailable | Retry with backoff. |
| Unsupported schema version | Quarantine/DLQ; await newer consumer. |
| Invalid payload | Quarantine/DLQ; no infinite retries. |
| Business rule violation | Reject per business policy; do not retry like infrastructure errors. |
| Unknown application bug | Bounded retry, alert, and DLQ upon exhaustion. |

Never treat every `MessageConversionException` as transient. For a permanently malformed schema payload, retries change nothing. When a converter cannot reach the registry due to a network blip, retries can help.

### 13.4. Do Not Let Bad Messages Block a Partition Forever

In Kafka, a failing record can stop the consumer from committing offsets per policy, stalling the partition. Design retry topics, DLQs, or pause/retry strategies appropriately. On replay, preserve keys and ordering semantics when required by the business.

## 14. Idempotency When Converting or Replaying Messages

A message can re-run due to retries, redrives, consumer restarts, or historical replays. When a new schema upcasts from an old schema, the event still represents the same occurrence.

Use a stable key, such as:

~~~text
(source, eventId)
~~~

or the agreed business operation key. Never mint a new idempotency key merely because the consumer build or schema version changed.

If an upcaster generates derived events rather than just converting representations, distinguish:

- Original event identity.
- Derived event identity.
- Transformation/upcaster version.

Otherwise, a replay can repeat side effects or break trace correlation.

## 15. Scenario Walkthrough: Restructuring OrderCreated

Suppose schema v1 is:

~~~json
{
  "orderId": "ORD-42",
  "customerId": "CUS-18",
  "total": 1250000,
  "currency": "VND"
}
~~~

The team wants schema v2:

~~~json
{
  "orderId": "ORD-42",
  "buyer": {
    "id": "CUS-18",
    "segment": "GOLD"
  },
  "total": {
    "amount": "1250000.00",
    "currency": "VND"
  },
  "discountCode": null
}
~~~

This is a major change: `customerId` moves inside `buyer`, `total` changes from scalar to object, and `discountCode` is added.

Never deploy producer v2 immediately. A safe plan:

1. Define the canonical model and exact semantics for `total`.
2. Author schema v2 and check compatibility against v1.
3. Build an adapter/upcaster reading both v1 and v2.
4. Deploy consumers supporting both schemas.
5. Verify all consumer instances and replay workers have upgraded.
6. Begin emitting v2.
7. Monitor v1/v2 message ratios and decode errors.
8. Wait out backlogs, archives, and old DLQs.
9. Retire v1 support only after retention/replay windows expire or dedicated migration completes.

If the schema registry reports a breaking change, treat that as a signal to plan a migration or versioned subject/type—never weaken compatibility policies just to pass the check.

## 16. Contract Testing Before Deployment

A schema evolution test suite should cover:

| Test | Question to Answer |
| --- | --- |
| Old writer → new reader | Can the new consumer read old messages? |
| New writer → old reader | Can the old consumer read new messages? |
| Historical writer → latest reader | Are all schemas within retention still readable? |
| Missing optional field | Is the default valid for the business? |
| Unknown field | Does the parser ignore or reject per policy? |
| Unknown enum | Does the consumer handle it safely? |
| Type mismatch | Does a clear error occur before side effects? |
| Missing schema ID | Does it retry or quarantine based on cause? |
| Registry unavailable | Are retries bounded? |
| Malformed payload | Are raw bytes retained? |
| DLQ redrive | Do old messages decode after fixing the consumer? |
| Duplicate replay | Are side effects protected by idempotency? |

### 16.1. Contract Tests for Writer and Reader Schemas

Store fixture samples for each schema version in source control or a test artifact store. Whenever changing a consumer:

1. Read old fixtures with the new decoder.
2. Read new fixtures with the old decoder if the rollout requires forward compatibility.
3. Compare the canonical model after upcasting.
4. Assert business invariants.
5. Verify incompatible cases are quarantined properly.

Do not test JSON schemas with a text parser alone. Test actual serialized bytes produced by the real serializer alongside content-type and schema references.

### 16.2. Integration Testing with the Binder

- Send valid messages and confirm the function runs.
- Send incompatible messages and confirm raw payloads are preserved.
- Make the registry temporarily unreachable and verify retry/backoff.
- Make quarantine storage fail and confirm the message is not acked.
- Verify DLQ destination, metadata, and redrive.
- Send the same event twice and confirm idempotency.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Changing DTO assuming producer/consumer deploy together | Old consumer fails on new payloads. | Run compatibility checks and phased rollouts. |
| Adding a required field with no default | Historical messages fail deserialization. | Make it optional with default or version the contract. |
| Changing types without migration | Precision loss or conversion failures. | Introduce a new schema version and explicit adapter. |
| Dropping a field right when producer stops writing | Old DLQs/archives become unreadable. | Wait out retention/replay windows or keep an upcaster. |
| Checking only against the immediately prior schema | Very old messages break. | Use transitive compatibility when required. |
| Setting `NONE` to force schema registration | Breaking changes hit production. | Fix the schema or execute a controlled migration. |
| Using fake defaults to make parsers pass | Corrupt business data slips through silently. | Use only domain-meaningful defaults. |
| Retrying unsupported schemas infinitely | Backlogs and poison messages. | Quarantine/DLQ and wait for consumer support. |
| Catching exceptions and returning success | Broker may ack failed messages. | Return only after durable quarantine; throw on transient failures. |
| Deleting schema versions still referenced by messages | Historical messages cannot deserialize. | Match schema retention to data retention. |
| Expecting `FunctionCatalog` to manage Schema Registry | Wrong framework responsibility. | Configure converters, adapters, and `SchemaRegistryClient`. |
| Minting new event IDs during replay | Side effects execute again. | Preserve original event identity and idempotency keys. |

## 18. Case Study Exercises

### Exercise 1 — Choosing a Compatibility Mode

Producers currently use schema v1. New consumers deploy ahead of new producers. New consumers must read v1 messages sitting in the queue.

1. Should you verify backward or forward compatibility?
2. Why might field defaults be necessary?
3. If v1 messages still replay six months later, is non-transitive backward enough?

**Hint:** New readers must read old writers, requiring backward compatibility. If reading all historical versions, evaluate `BACKWARD_TRANSITIVE` and retain old schemas.

### Exercise 2 — New Field in JSON Schema

Old consumers use a JSON Schema with `additionalProperties: false`. New producers add `discountCode`.

1. Why can old parsers reject the payload?
2. How must consumer schemas change to accept new fields?
3. If the new field is semantically mandatory, is ignoring it safe?

### Exercise 3 — Protobuf Field Numbers

A developer removes `customer_id = 2` and adds `buyer_id = 2` with a different meaning.

1. Why is this change dangerous?
2. How must `reserved` be used?
3. If only renaming a field while keeping semantics and tag number, what must be checked for JSON/TextFormat?

### Exercise 4 — Temporary Schema Registry Outage

A consumer fails to fetch a writer schema due to a registry timeout.

1. Is this a permanent or transient failure?
2. How should retries and backoff be bounded?
3. If the schema ID genuinely does not exist, should retries continue?
4. Which metadata must be stored upon quarantine?

### Exercise 5 — Spring Cloud Function Receiving an Incompatible Message

A `Consumer<OrderCreated>` bean is never invoked because the payload fails conversion to `OrderCreated`.

1. Why can errors occur before the business function runs?
2. How do `contentType` and the function target type participate in conversion?
3. When should you use `Consumer<Message<byte[]>>`?
4. Why does `FunctionCatalog` not resolve schema versions automatically?

### Exercise 6 — Redriving After Upgrading Consumers

The DLQ holds 20,000 schema v1 messages. Current consumers handle only v2.

Design the procedure:

- Restore schema v1.
- Write an upcaster v1 → canonical model.
- Verify idempotency.
- Replay with rate limiting.
- Monitor processed messages and remaining failures.
- Keep an audit trail for the entire redrive.

### Exercise 7 — Changing a Field's Meaning

`total` used to hold VND amounts; now producers send USD while keeping the same field name and type.

1. Can a Schema Registry detect this change?
2. Why is this a breaking semantic change despite schema compatibility?
3. Should you introduce a new field/currency, event type, or schema version?
4. What consumer migration avoids miscalculating values?

## 19. Checklist Before Releasing a New Schema

| Item | What to Verify |
| --- | --- |
| Event contract | Do event type and semantics stay unchanged? |
| Schema identity | How are subject, schema ID/version, and retention managed? |
| Compatibility | Which of backward, forward, full, or transitive fits the rollout? |
| Format rules | Avro defaults, Protobuf reserved tags, JSON Schema open/closed policies. |
| Consumer coverage | Do all consumers and replay workers support the new schema? |
| Producer rollout | Are consumers ready before producers emit the new data? |
| Historical data | Are backlogs, archives, and old DLQs still readable? |
| Conversion | Are content type, writer schema, reader schema, and custom converters right? |
| Failure handling | Are unsupported schemas, corrupt payloads, and registry outages classified? |
| Quarantine / DLQ | Are raw payloads, schema references, error codes, and audit metadata preserved? |
| Idempotency | Do retries and redrives preserve event identity? |
| Testing | Have the old/new writer–reader matrix and binder integration tests run? |
| Rollback | Can you halt new producers or roll back consumers without losing messages? |

## 20. Summary and Official References

**Data contract evolution is a coordinated effort across producers, consumers, schemas, adapters, and brokers.** A schema change is safe only when running versions, stored messages, and replay procedures are all accounted for.

Key points:

- Backward: new reader reads old writer data.
- Forward: old reader reads new writer data.
- Full: both directions; transitive checks across schema history.
- Compatibility rules differ across Avro, Protobuf, and JSON Schema.
- Use meaningful defaults, optional fields, and expand–migrate–contract rollouts.
- Retain writer schemas / schema IDs for the lifetime of stored messages.
- Upcasters convert old data to canonical models while preserving original messages.
- Permanent schema incompatibilities go to quarantine/DLQ; transient registry outages can retry.
- `FunctionCatalog` is not a Schema Registry; `contentType`, target function type, and `MessageConverter` govern conversion in Spring Cloud Function.
- Retries, DLQs, and acknowledgements depend on the binder/broker; confirm messages only after durable processing or quarantine.
- Preserve event identity and idempotency keys during replays.

**Official References:**

1. Confluent Schema Registry — Schema Evolution and Compatibility: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
2. Confluent Schema Registry — Compatibility Types and Transitive Modes: https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html
3. Apache Avro — Specification, Schema Resolution: https://avro.apache.org/docs/current/specification/
4. Protocol Buffers — Proto3 Language Guide, deleting fields and reserving numbers: https://protobuf.dev/programming-guides/proto3/
5. Protocol Buffers — Proto3 Language Specification: https://protobuf.dev/reference/protobuf/proto3-spec/
6. JSON Schema — Core and Validation Specifications: https://json-schema.org/specification
7. Spring Cloud Function — Message Conversion and Programming Model: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
8. Spring Cloud Stream — Schema Registry and Avro Schema Resolution: https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html
9. Spring Cloud Stream — Error Handling and Retry: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html
10. Spring Cloud Stream — Kafka Binder Dead-Letter Topic Processing: https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html
