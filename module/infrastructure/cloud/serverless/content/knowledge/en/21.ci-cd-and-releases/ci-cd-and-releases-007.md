# Coordinating Producer, Consumer, and Compatible Schema Releases

In event-driven serverless systems, producers and consumers are often deployed independently. One Java function may emit an event into a queue or event bus; another function receives that event milliseconds or hours later. When a producer renames a field, changes a data type, or alters event semantics, old consumers may still be running and continuing to receive messages already sitting in the queue.

Therefore, releasing a service is not just deploying new code. Teams must coordinate **event contracts**, **schema evolution**, rollout ordering, ability to read historical messages, and rollback procedures. A syntactically valid schema can still break business logic if it alters field meaning, currency units, event semantics, or ordering rules.

This lesson teaches how to design contracts for Java producers/consumers, evaluate backward/forward compatibility, evolve schemas step by step, test compatibility in CI/CD, and release safely when multiple revisions run concurrently.

## Learning Objectives

After this lesson, you will be able to:

- Describe an event contract including envelope, payload, schema, and semantics.
- Distinguish event type/version from schema version and application version.
- Explain backward, forward, and full compatibility.
- Evolve JSON, Avro, or Protobuf schemas without breaking running consumers.
- Apply expand-contract to release producers and consumers in stages.
- Design consumers tolerant of new fields, missing fields, old events, and duplicate messages.
- Write producer/consumer contract tests and validate schemas in pipelines.
- Plan canaries, rollbacks, replays, and handling of messages in DLQs.
- Identify schema changes that are structurally compatible yet break business semantics.

## 1. Producers, Consumers, and Event Contracts

A **producer** is the component creating and sending events. A **consumer** is the component receiving and processing events. They may run on different functions, services, teams, or release schedules.

Example in an ordering system:

- `order-api` creates an order and emits `OrderPlaced`.
- `inventory-worker` reserves stock upon receiving `OrderPlaced`.
- `payment-worker` initiates payment.
- `notification-worker` sends notifications after the order is confirmed.

~~~mermaid
flowchart LR
    A["order-api<br/>Producer"] --> Q["Queue / Event bus"]
    Q --> B["inventory-worker<br/>Consumer"]
    Q --> C["payment-worker<br/>Consumer"]
    Q --> D["notification-worker<br/>Consumer"]
    B --> DB1["Inventory"]
    C --> DB2["Payment provider"]
    D --> DB3["Notification provider"]
~~~

An event contract is more than a JSON structure. It must describe at least:

1. **Identity:** stable event ID for deduplication and tracing.
2. **Type:** event name expressing the business fact that occurred, e.g., `com.example.order.placed`.
3. **Source/producer:** system generating the event.
4. **Time:** when the business event occurred, distinct from when a consumer receives it.
5. **Schema:** field names, types, required/optional flags, formats, and evolution rules.
6. **Semantics:** what fields mean, units, and permitted states.
7. **Delivery behavior:** ordering, duplicates, retries, retention, and dead-letter behavior.
8. **Ownership:** team responsible for changing the contract and notifying consumers.

### Envelope and Payload

Separate transport metadata from business data. Envelope example:

~~~json
{
  "eventId": "evt-01J8QX8K6J4P",
  "eventType": "com.example.order.placed",
  "schemaVersion": "2.0",
  "source": "orders-api",
  "occurredAt": "2026-11-17T10:15:30Z",
  "data": {
    "orderId": "ord-1042",
    "customerId": "cus-77",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

- `eventId` is the identifier of an occurred event; retries must preserve the exact ID.
- `eventType` identifies the business event category.
- `schemaVersion` indicates the payload/envelope structural version by convention.
- `occurredAt` is when the business event occurred, not when the message was delivered.
- `data` holds the payload conforming to the schema.

If the system uses CloudEvents, follow the standard CloudEvents envelope and attributes rather than inventing an incompatible envelope. If using a schema registry, define subjects/names and versions as required by the registry.

Never use Lambda/Cloud Run revision version numbers as schema versions. One revision may emit the same schema as the previous revision; one schema may be used across multiple application versions.

## 2. Schema Compatibility: Backward, Forward, and Full

Compatibility describes the ability of readers/consumers and writers/producers to work with data created under schemas from different points in time.

Suppose schema v1 has fields `orderId` and `totalAmount`. Schema v2 adds `currency`.

| Compatibility Type | Meaning | Example |
|---|---|---|
| **Backward** | New code/schema can read data written under the old schema | New consumer reads v1 events missing `currency` |
| **Forward** | Old code/schema can read data written under the new schema | Old consumer ignores the new `currency` field |
| **Full** | Both directions are compatible | New consumer reads old events and old consumer reads new events |
| **Breaking** | One or both directions are incompatible | Changing `totalAmount` from integer to object that old consumers cannot parse |

The terms backward/forward are sometimes described from a writer/reader or schema registry perspective. In this lesson, backward means new readers can read old data; forward means old readers can read new data. When using a registry, verify the registry's specific mode definitions and check scope (latest vs. transitive).

### Example: Adding an Optional Field

Schema v1:

~~~json
{
  "type": "object",
  "required": ["orderId", "totalAmount"],
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "integer" }
  }
}
~~~

Schema v2 adds optional `currency`:

~~~json
{
  "type": "object",
  "required": ["orderId", "totalAmount"],
  "properties": {
    "orderId": { "type": "string" },
    "totalAmount": { "type": "integer" },
    "currency": { "type": "string" }
  }
}
~~~

Consumer v1 can continue reading v2 events if parsers/schema policies allow ignoring unknown properties. Consumer v2 must handle v1 events lacking `currency`. If historical contracts guarantee all `totalAmount` values were VND, the new consumer can fall back to VND for old events; if currency was previously undetermined, never guess.

In JSON Schema, the `default` keyword is primarily an annotation; validators do not necessarily inject default values into payloads. Consumers must apply fallbacks themselves or producers must emit the value. Also, schemas using `additionalProperties: false` can reject new fields; weigh that policy when old consumers must accept expanded payloads.

### Common Compatible vs. Incompatible Changes

| Change | Risk | How to Handle |
|---|---|---|
| Add optional field | Low if consumers ignore unknown fields | Add field, verify old parsers |
| Add required field | New consumers may fail to read old events | Provide meaningful default or release major contract |
| Remove field | Old consumers may still need field | Deprecate first, measure usage before deleting |
| Rename field | Old consumers cannot find field | Dual-write/alias during transition |
| Change field type | Parsers may fail or lose precision | Add new field, migrate gradually |
| Change unit or meaning | Schema stays valid but business logic breaks | New field or new event type; document semantics |
| Add enum value | Consumers with non-default switches may fail | Consumers must handle unknown values |
| Change ordering/delivery semantics | Consumers may compute wrong state | Dedicated contract and behavior tests |

Structural compatibility does not guarantee business compatibility. For example, `totalAmount: 1000` remains an integer, yet if it previously meant dong and later switches to cents, consumers could miscalculate by 100x without any parse error.

## 3. Evolution Rules for JSON Events

JSON is flexible and readable, yet every consumer must handle schema evolution intentionally.

Recommended principles:

- Add new fields as optional before requiring consumers to use them.
- Consumers ignore unknown fields when permitted by the contract.
- Consumers have explicit fallbacks for missing fields; never guess values.
- Do not rename or change types of widely used fields.
- Never repurpose an existing field for a new meaning.
- Never change units while keeping the same field name.
- Enum consumers must handle unknown values.
- Only delete fields after the compatibility period ends and consumers stop using them.
- Keep event fixtures for historical schema versions to test replay.

### Java Consumer Tolerant of New Fields

With Jackson, DTOs can be configured to ignore unknown properties:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderPlacedV1(
        String orderId,
        String customerId,
        Long totalAmount) {
}
~~~

The consumer can read both old events and new events with added fields. However, if required fields are missing or mistyped, the application still needs validation. `ignoreUnknown=true` does not solve field renames, unit changes, or missing fields.

If currency is added and the contract guarantees all older events used VND, normalize explicitly:

~~~java
public record OrderPlacedPayload(
        String orderId,
        String customerId,
        Long totalAmount,
        String currency) {

    public String effectiveCurrency() {
        return currency == null || currency.isBlank()
                ? "VND"
                : currency;
    }
}
~~~

This fallback is only valid when the v1 contract guaranteed `totalAmount` was always VND. Without that guarantee, the consumer should reject events missing currency or route them to quarantine/DLQ per policy rather than assigning a value on its own.

### Enums and Unknown Values

A consumer may encounter a new status like `PARTIALLY_REFUNDED` after a producer extends an enum. If code uses an exhaustive switch or parses the enum directly, messages may fail.

A safer approach is keeping the wire value as a String and mapping it:

~~~java
public enum PaymentStatus {
    PENDING,
    AUTHORIZED,
    CAPTURED,
    REFUNDED,
    UNKNOWN;

    public static PaymentStatus fromWire(String value) {
        if (value == null) {
            return UNKNOWN;
        }
        try {
            return PaymentStatus.valueOf(value);
        } catch (IllegalArgumentException ignored) {
            return UNKNOWN;
        }
    }
}
~~~

Not every unknown status can be treated as UNKNOWN and continued. For payment operations, consumers may need to quarantine the event and raise an error instead of defaulting to an assumed safe state. Define an unknown-value policy for each event type.

## 4. Avro and Protobuf: Schemas with Distinct Compatibility Rules

JSON Schema, Avro, and Protobuf do not share the same semantics. Never apply one format's rules to another.

### Avro

Avro uses a writer schema and reader schema to resolve data on read. A new field added to the reader schema typically needs a default so readers can parse records written under old schemas lacking that field.

Example adding currency with a default:

~~~json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalAmount", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
~~~

The default is only valid if historical semantics genuinely guarantee currency is VND. Avro readers apply the default when a field is absent from the writer schema; this differs from JSON Schema annotation defaults.

### Protobuf

Protobuf uses field numbers to encode the wire format. Key rules:

- Never change published field numbers.
- Never reuse deleted field numbers.
- Use `reserved` for retired field numbers/names.
- Avoid incompatible wire type changes.
- Consumers must tolerate unknown fields per runtime/protobuf version.
- For enums, keep numeric values stable and include an appropriate UNKNOWN/UNSPECIFIED value.

Example:

~~~protobuf
syntax = "proto3";

message OrderPlaced {
  string order_id = 1;
  int64 total_amount = 2;
  string currency = 3;

  reserved 4;
  reserved "legacy_customer_code";
}
~~~

Never reuse tag 4 for a new field, even after the old field is removed from source. Old data or replayed messages may still contain that tag.

### Schema Registry

A schema registry can store versions, check compatibility upon registering new schemas, and issue schema IDs for messages. Some ecosystems support Avro, Protobuf, and JSON Schema; features and compatibility modes depend on the product in use.

Policies such as backward, forward, full, or transitive variants can be configured. Transitive modes check compatibility against multiple prior versions, not just the latest one. Choose modes based on how consumers receive and replay messages: queues with long retention or historical replay typically require checking more versions.

A registry does not replace business testing. It cannot know that `totalAmount` switched from dong to cents if the type remains integer. Contract owners must still review semantics.

## 5. Versioning Events and Schemas

Not every change requires changing the event type. Distinguish:

- **Event type:** business event, e.g., `order.placed`.
- **Schema version:** payload structure of the event type.
- **Application version:** producer/consumer code version.
- **Deployment revision:** revision or version run by the platform.

An event type can evolve from schema 1 to schema 2 while keeping the same event type if changes remain compatible. When semantics change drastically or compatibility cannot be preserved, create a new event type or new major version.

Example:

~~~text
eventType = com.example.order.placed
schemaVersion = 1.0
~~~

After compatible expansion:

~~~text
eventType = com.example.order.placed
schemaVersion = 1.1
~~~

If event meaning changes significantly—such as `OrderPlaced` previously emitted after the order saved, but now emitted before transaction commit—that is a semantic change. You need a new contract or an explicit migration process; simply bumping schemaVersion does not make the behavior change safe.

Do not create a new version for every field or every deployment. Versioning should help consumers interpret events and preserve replayability.

## 6. Expand-Contract: Non-Disruptive Producer and Consumer Releases

When producers and consumers deploy independently, the safe pattern is **expand first, contract later**.

Suppose v1 has `customerName` and we want to move to `customerDisplayName`.

Do not switch the producer immediately to send only the new field because old consumers still need `customerName`. Use multiple phases.

~~~mermaid
flowchart TD
    A["1. Expand consumer"] --> B["2. Deploy tolerant consumers"]
    B --> C["3. Producer dual-writes old + new fields"]
    C --> D["4. Observe usage and migrate consumers"]
    D --> E["5. Producer stops old field"]
    E --> F["6. Contract: remove old field after retention window"]
~~~

### Phase 1: Expand Consumer

The new consumer can read both the old field and the new field. If the new field is missing, the consumer uses the old field per defined compatibility rules. Do not change the producer yet.

### Phase 2: Deploy Tolerant Consumers

Deploy consumers capable of reading both forms. If multiple teams own consumers, confirm all active consumers are updated, including scheduled consumers and consumers that may replay DLQs.

### Phase 3: Producer Dual-Write

The producer emits both `customerName` and `customerDisplayName` with consistent values. Keep semantics clear if the two fields are not strictly identical.

~~~json
{
  "customerName": "Nguyen An",
  "customerDisplayName": "An Nguyen"
}
~~~

Do not dual-write two fields if they carry different meanings that old consumers could misinterpret. In that case, create a new event type/version or a dedicated mapping adapter.

### Phase 4: Migrate and Observe Consumers

Update consumers to use the new field. Monitor version/schema metrics, parse failures, DLQs, and how many consumers still read the old field. Usage logs should avoid personal data; metrics should only count by consumer/version without attaching user names.

### Phase 5: Stop Emitting the Old Field

Only stop emitting the old field when:

- All running consumers have been upgraded.
- Queues/topics hold no remaining old messages needing processing, or new consumers can still read them.
- DLQs and replay stores have been handled.
- Scheduled or infrequently active consumers have been verified.
- Rollback windows and retention windows have been agreed upon.

### Phase 6: Contract

After the compatibility window, the producer can remove the old field and consumers can remove fallback branches. Remove fields from the schema registry only if registry policy and replay needs permit; never delete historical schema versions needed to read old messages.

## 7. Producer and Consumer Deployment Order

Deployment order depends on compatibility direction.

| Change | Typically Safe Order | Condition |
|---|---|---|
| Add optional field, old consumers ignore unknown | Producer can deploy first or consumer first | Old parsers must accept new fields |
| Consumer starts using new field | Tolerant consumer deploys first, then producer emits field | Consumer has fallback before field appears |
| Rename field | Consumer supports old/new names first, producer dual-writes next | Observation window and rollback plan in place |
| Remove old field | Consumers stop depending on it first, producer stops emitting next | No old messages still need that field or consumers can read it |
| Incompatible type/meaning change | Create new contract, deploy new consumer before new producer | Isolated route/topic/version and migration plan |
| Change ordering semantics | Consumers and infrastructure prepared first | Clear partition key, ordering, and replay policies |

There is no single deployment order valid for every change. Before rollout, identify every producer/consumer combination that may coexist: old producer with new consumer, new producer with old consumer, and new consumer reading older messages still sitting in queues.

### Rollout Compatibility Matrix

| Producer | Old Consumer | New Consumer |
|---|---|---|
| Old producer | Current combination | New consumer must read old schema |
| New producer | Old consumer must read new schema or producer retains old field | Target combination |
| Replaying old messages | Old consumer can read | New consumer must support history within retention/replay window |

If a new producer emits messages incompatible with old consumers and consumers cannot deploy first, use a new topic/queue/event type version to isolate the stream. Never send incompatible events into the same queue without consumers able to handle them.

## 8. Java Producer: Emitting Events from a Defined Contract

Producers should construct explicit event DTOs and serialize through an adapter. Never send JPA entities or internal objects directly, because database model changes could accidentally alter the event contract.

DTO example:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
        String eventId,
        String eventType,
        String schemaVersion,
        String source,
        Instant occurredAt,
        T data) {
}

public record OrderPlacedV2(
        String orderId,
        String customerId,
        long totalAmount,
        String currency) {
}
~~~

Build events at the application boundary:

~~~java
import java.time.Clock;

public final class OrderEventFactory {
    private final Clock clock;
    private final EventIdGenerator eventIds;

    public OrderEventFactory(Clock clock, EventIdGenerator eventIds) {
        this.clock = clock;
        this.eventIds = eventIds;
    }

    public EventEnvelope<OrderPlacedV2> placed(
            String orderId,
            String customerId,
            long totalAmount) {

        return new EventEnvelope<>(
                eventIds.nextId(),
                "com.example.order.placed",
                "2.0",
                "orders-api",
                clock.instant(),
                new OrderPlacedV2(
                        orderId,
                        customerId,
                        totalAmount,
                        "VND"));
    }
}

public interface EventIdGenerator {
    String nextId();
}
~~~

In production, inject an appropriate ID generator (such as UUID) and generate the ID exactly once when writing the event into the outbox alongside the business transaction. Publish retry workers must re-read and send the exact stored event rather than calling the generator to create a new ID. Consumers must still be idempotent because brokers may redeliver. Currency in the example is fixed to VND only because the illustrative contract specifies it; multi-currency systems must obtain currency from business data.

### Outbox Keeps Events Consistent with the Database

If a producer writes an order to the database and then publishes the event directly, two failure modes arise: database commits while publish fails, or publish succeeds while the database transaction rolls back. A transactional outbox writes the business record and event in the same transaction; a worker publishes the outbox afterward.

When the worker retries publishing, it resends the same event ID. Consumers must still remain idempotent because brokers may redeliver. An outbox does not automatically create end-to-end exactly-once delivery.

## 9. Java Consumer: Safely Reading Multiple Schema Versions

Consumers should have an adapter layer that deserializes events and normalizes them into internal commands. Business logic does not need to know whether old or new wire fields arrived.

Example payload accepting both `customerName` and `customerDisplayName` during migration:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record CustomerData(
        String customerName,
        @JsonProperty("customerDisplayName")
        String customerDisplayName) {

    public String effectiveDisplayName() {
        if (customerDisplayName != null
                && !customerDisplayName.isBlank()) {
            return customerDisplayName;
        }
        if (customerName != null && !customerName.isBlank()) {
            return customerName;
        }
        throw new IllegalArgumentException(
                "event has no customer display name");
    }
}
~~~

If you need both JSON properties to map to the same logical property, you can use `@JsonAlias` or a custom deserializer; pick an approach where the two fields do not conflict. The example above keeps two distinct properties to explicitly prioritize the new field.

Once new consumers are deployed and the producer dual-writes, consumers can use `effectiveDisplayName()`. Only delete the fallback after no old messages remain in queues, DLQs, or replayable archives.

### Normalizing Wire Events to Commands

~~~java
public record NotifyCustomerCommand(
        String orderId,
        String customerDisplayName) {
}

public final class OrderEventMapper {
    public NotifyCustomerCommand toCommand(
            OrderPlacedPayload payload,
            CustomerData customer) {
        if (payload.orderId() == null || payload.orderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }

        return new NotifyCustomerCommand(
                payload.orderId(),
                customer.effectiveDisplayName());
    }
}
~~~

The mapper is responsible for validating required fields and translating old/new schemas into a stable internal model. If an old event cannot be normalized because essential data is missing, quarantine the message and raise an investigable error; never fabricate ungrounded business values.

## 10. Contract Testing Between Producers and Consumers

Producer unit tests prove code constructs objects properly. Consumer unit tests prove consumers process objects properly. Yet both separate tests can pass while the actual JSON mismatches—for example, the producer renames a field without the consumer noticing.

Contract tests verify compatibility at the serialization boundary.

### Producer Contract Tests

- Serialize events from the producer.
- Verify event type, schema version, and required fields.
- Validate payloads against registered schemas.
- Verify event ID stability across retries/outbox.
- Compare against golden fixtures or schema compatibility rules.

JUnit example with Jackson:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrderEventSerializationTest {
    private final ObjectMapper mapper = new ObjectMapper()
            .findAndRegisterModules();

    @Test
    void writesThePublishedContract() throws Exception {
        var event = new EventEnvelope<>(
                "evt-100",
                "com.example.order.placed",
                "2.0",
                "orders-api",
                java.time.Instant.parse("2026-11-17T10:00:00Z"),
                new OrderPlacedV2(
                        "ord-1", "cus-1", 1250000L, "VND"));

        String json = mapper.writeValueAsString(event);

        assertTrue(json.contains("\"eventType\":\"com.example.order.placed\""));
        assertTrue(json.contains("\"schemaVersion\":\"2.0\""));
        assertTrue(json.contains("\"currency\":\"VND\""));
    }
}
~~~

In real projects, parse JSON into a tree or validate against JSON Schema rather than relying on `contains` for all assertions. Verify field types, required properties, and schema IDs/versions.

### Consumer Compatibility Tests with Historical Fixtures

Retain sample payloads for schema versions still within retention/replay windows:

~~~text
src/test/resources/events/
  order-placed-v1.json
  order-placed-v2.json
  order-placed-unknown-enum.json
  order-placed-missing-required-field.json
~~~

Consumer tests should verify:

- v1 events are read and normalized properly.
- v2 events with new fields are read properly.
- Unknown fields do not crash parsers when permitted by the contract.
- Missing required fields are classified as invalid.
- New enum values are handled per policy.
- Unsupported event types/schema versions are quarantined or rejected per policy.

Golden fixtures must be managed alongside the contract. When a producer changes, never edit old fixtures just to make tests pass; add new fixtures while retaining needed historical data.

### Consumer-Driven Contracts

With multiple independent consumers, each consumer can publish the fields and semantics it relies upon. Producers verify new changes do not break those contracts before releasing.

This helps when producers do not know every consumer upfront. However, consumer-driven contracts do not replace a schema registry and do not automatically test delivery, ordering, or business side effects.

## 11. Schema Compatibility in CI/CD

Pipelines should validate schemas before building/publishing artifacts or deploying producers.

~~~mermaid
flowchart TD
    A["Pull request: code + schema"] --> B["Lint / validate schema"]
    B --> C["Compatibility check against registry/history"]
    C --> D["Compile and unit tests"]
    D --> E["Producer serialization tests"]
    E --> F["Consumer tests with old/new fixtures"]
    F --> G["Contract / integration tests"]
    G --> H["Deploy tolerant consumers"]
    H --> I["Deploy producer canary"]
    I --> J["Observe errors, DLQ and business metrics"]
    J --> K{"Stable?"}
    K -->|Yes| L["Promote rollout"]
    K -->|No| M["Rollback producer or route to old contract"]
~~~

Verification steps:

1. **Schema lint:** check syntax, naming, required/optional flags, descriptions, and reserved fields.
2. **Compatibility check:** compare the new schema against current and historical versions per policy.
3. **Compile/code generation:** generate Java classes from Avro/Protobuf if using schema-first.
4. **Producer tests:** confirm serialized events match the contract.
5. **Consumer fixture tests:** read all schema versions still requiring support.
6. **Contract tests:** verify producer output satisfies consumer expectations.
7. **Integration tests:** verify broker, auth, serialization, retries, and DLQs.
8. **Deployment gate:** only promote once tolerant consumers are ready.
9. **Post-deploy verification:** monitor parse errors, unknown events, retries, DLQs, and business outcomes.

Do not let CI validate a new schema solely against itself. Compare it against published versions and versions still in use or replayable.

### Schema Registry in Pipelines

If using a schema registry, the pipeline can call its compatibility endpoint or corresponding command to register new schemas. The registry must be configured with proper policies per subject/event type. Do not assume every registry shares the same commands, authentication, or compatibility semantics; use the official tooling of the platform in operation.

A schema registry should serve as the historical contract store, while schema files remain version-controlled in the repository for review and reproducible builds. Record the schema ID/version in event metadata or message headers per serializer/registry conventions.

## 12. Canary, Rollout, and Rollback

Even when contracts are compatible, release in stages because new code may still contain business bugs.

A rollout might:

1. Deploy the new consumer while still supporting old events.
2. Confirm the new consumer can read messages already in the queue.
3. Deploy the new producer with dual-write or optional fields.
4. Shift a fraction of producer traffic to the new revision if supported by the platform.
5. Monitor deserialization errors, consumer failures, DLQs, latency, and business outcomes.
6. Gradually ramp up the new producer share.
7. Contract old fields only after the compatibility period and once the rollback window closes.

### Rollback Is More Than Reverting Code

If a new producer has already emitted v2 events into a queue, rolling the producer back to v1 code does not erase published v2 messages. Consumer v1 may keep receiving them and fail.

A rollback plan must answer:

- Can old consumers read the new events?
- If not, can consumers roll back or must the new consumer stay live?
- Do v2 events need to be routed to a separate queue?
- Which consumer version can replay messages already sent to the DLQ?
- Does the registry still retain the old schema version?
- Do executed side effects need compensation?

For incompatible changes, deploy consumers supporting both v1/v2 before producers emit v2. If impossible, use a new event type/topic version and run v2 consumers in parallel.

### Dual-Read and Dual-Write

- **Dual-read:** consumers read both old and new fields during transition.
- **Dual-write:** producers emit both old and new fields.
- **Backfill/replay:** convert historical data/events when needed.
- **Contract:** remove old fields or routes after all consumers have migrated.

Do not leave dual-read/dual-write running indefinitely. Set deadlines, owners, and metrics proving when migration can conclude.

## 13. Queue Retention, Retries, DLQs, and Replay

Schema compatibility must account for messages stored prior to deployment. A new consumer may receive old events days later; a message in a DLQ may be replayed after multiple newer revisions have deployed.

Define:

- Maximum queue/topic retention.
- Retry window and delivery attempt limits.
- DLQ retention and replay permissions.
- Event archive or object storage holding historical payloads.
- Schema versions still supported.
- Consumer version used during replay.
- Handling for unparseable events or events with obsolete semantics.

Do not delete schema v1 right after producers move to v2 if queues or archives still hold v1 events. If replaying old events into new consumers, consumers must have compatibility tests covering those payloads.

### Poison Messages

A poison message is a message that consistently fails due to malformed payloads, unsupported schemas, or anomalous business data. Infinite retries can clog queues or drive up costs.

- Separate parse/schema errors from transient errors.
- Cap retries via trigger configuration.
- Route unprocessable messages to DLQ/quarantine.
- Log event ID, schema version, error category, and correlation ID; never log secrets or sensitive payloads.
- Fix the consumer or mapping, then replay in a controlled manner.
- Preserve the original event ID on replay so idempotency continues working.

Replay does not mean bypassing idempotency. If a side effect already succeeded before a consumer timed out, replay must not trigger the side effect a second time.

## 14. Event Ordering and Semantics

A schema can be 100% compatible while consumers still produce wrong results if event ordering changes.

Example:

~~~text
OrderCreated -> PaymentAuthorized -> OrderCancelled
~~~

If a consumer receives `OrderCancelled` before `PaymentAuthorized`, it needs explicit state-handling rules. Never assume every queue/event bus guarantees global ordering.

Questions to document in the contract:

- Is ordering guaranteed across the whole queue, per partition key, or not guaranteed?
- Can events duplicate?
- Can consumers receive delayed events?
- Is there a per-aggregate sequence/version?
- Which events can be processed in parallel?
- How do consumers handle an event older than current state?
- Is partitioning by orderId or aggregateId required?

You can include an aggregate version/sequence in the payload so consumers detect stale or missing events:

~~~json
{
  "orderId": "ord-1042",
  "aggregateVersion": 7,
  "status": "CONFIRMED"
}
~~~

Consumers can compare this version against stored state and decide whether to ignore, retry, or investigate gaps. Clearly define version semantics: whether it increments on every aggregate mutation or only on emitted events.

## 15. Idempotency and Event Identity

Event systems commonly exhibit at-least-once delivery or multi-layer retries. Consumers should treat duplicates as normal behavior.

Processing pattern:

1. Receive event and extract stable event ID.
2. Attempt to claim the event ID in an idempotency store via unique constraint/conditional write.
3. If the event already succeeded, return acknowledgement per contract.
4. If claimed, execute business logic and persist results in an appropriate transaction.
5. If processing fails, preserve state for retry/lease recovery as designed.
6. Never mark complete before side effects are committed.

Do not use a broker-generated per-delivery request ID as the idempotency key if it changes across retries. Use the producer-generated, durably stored event ID.

For consumers that emit downstream events, a transactional outbox can commit business state and new events in the same transaction. This narrows the gap between database updates and message publishing.

## 16. Observing Compatibility in Production

Do not monitor only HTTP 5xx. For consumers, key signals include:

| Metric/Log | What to Know |
|---|---|
| Messages received by event type/schema version | Which contracts consumers are currently receiving |
| Deserialization/schema validation failures | Which payloads fail to parse |
| Unknown enum/value count | Whether producers started emitting new values |
| Retry count and delivery attempts | Whether consumers are failing repeatedly |
| DLQ depth/age | Whether failed messages are piling up |
| Processing latency | Whether consumers slowed down after changes |
| Duplicate/idempotency hits | Rate of redeliveries or producer retries |
| Business completion/failure | Whether events yield correct business outcomes |

Use low-cardinality metric labels such as event type, schema major version, consumer name, and outcome. Never put event ID, order ID, or customer ID into metric labels; those belong in controlled logs or traces.

During rollout, compare v1/v2 consumers and producer revisions over the same time window. You can maintain a `schema_compatibility_failure_total` metric or structured log events to catch issues early.

## 17. Producer/Consumer Release Checklist

- [ ] Every event type has a clear owner, purpose, schema, and semantics.
- [ ] Envelope includes stable event ID, event type, schema version, source, and occurred time.
- [ ] Schema version is not confused with application/revision version.
- [ ] Backward/forward/full compatibility is verified per registry/tooling.
- [ ] New fields are added as optional before consumers require them.
- [ ] Consumers ignore new fields or enforce an unknown-field policy.
- [ ] Missing fields use fallbacks only when historical semantics guarantee that value.
- [ ] Field names, types, units, or meanings are not changed without a migration.
- [ ] Enum consumers handle unknown values per policy.
- [ ] Avro defaults and Protobuf field number/reserved rules are respected.
- [ ] New schemas are tested against current and replayable historical versions.
- [ ] Tolerant consumers deploy before breaking/expanded producer output.
- [ ] Producer dual-writes occur only during a migration with an owner and deadline.
- [ ] Queue retention, DLQs, archives, and replay windows are accounted for.
- [ ] Consumers are idempotent and handle duplicates/out-of-order events per contract.
- [ ] CI runs producer serialization, consumer fixture, and contract tests.
- [ ] Canaries track parse errors, retries, DLQs, and business outcomes.
- [ ] Rollback plans account for new messages already in queues, not just code revisions.
- [ ] Old schemas are retired only after read/replay needs and rollback windows finish.

## Self-Check

1. What components make up an event contract besides the JSON payload?
2. How do backward compatibility and forward compatibility differ from a reader's perspective?
3. Why is adding an optional field usually safer than adding a required field?
4. Does JSON Schema `default` automatically insert values into payloads?
5. How does an Avro reader default differ from a JSON Schema default?
6. Why must Protobuf never reuse deleted field numbers?
7. What deployment order for consumers and producers does expand-contract require?
8. Why does rolling back a producer not remove v2 events already in a queue?
9. Does a compatible schema guarantee ordering and business semantics?
10. How must an event ID be preserved across retries/replays to keep consumers idempotent?

Producers and consumers release safely when contracts have owners, schemas are versioned, and every change is tested for reading old and new data. Expand-contract makes consumers tolerant before producers alter payloads; contract tests and schema registries catch structural mistakes in CI; and retries, DLQs, replays, and idempotency protect operations post-deployment. Always verify semantics, ordering, and side effects alongside schemas, because an event that parses cleanly can still corrupt business logic.
