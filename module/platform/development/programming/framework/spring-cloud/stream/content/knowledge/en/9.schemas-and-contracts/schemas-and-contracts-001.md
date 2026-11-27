# Designing Event Contracts Independent of Internal Storage Models

In event-driven systems, producers and consumers are often developed, deployed, and scaled by different teams at different times. If a producer sends a JPA entity or database table structure directly to the broker, internal storage changes can break consumers even when the business meaning has not changed.

An event contract needs to describe a business fact that services care about together. It must be stable in business language, versioned, and transformed from the internal model through an explicit mapping layer. Spring Cloud Stream provides bindings and binders to transport that contract over Kafka, RabbitMQ, or Pulsar; the framework does not automatically decouple the contract from the entity if the application sends the entity directly as the payload.

## 1. Why Not Send Persistence Entities Directly?

A persistence entity is designed to serve read/write operations within a single service. It typically contains details that do not belong in an inter-service contract:

- Primary keys, foreign keys, and database relational structures.
- Fields for optimistic locking, internal auditing, soft deletes, or lazy loading.
- Column names and ORM-dependent data representations.
- Transient state, caches, proxies, or circular references.
- Sensitive data or data owned exclusively by the service.

Simple entity example:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Column(name = "customer_fk")
    private Long customerDatabaseId;

    private String status;
    private BigDecimal subtotal;
    private BigDecimal discountAmount;
    private BigDecimal totalAmount;
    private String internalRiskFlag;
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    // getters, setters, and persistence behaviors
}
~~~

If the producer serializes this entity, consumers may inadvertently depend on column names, internal IDs, ORM relationships, or private fields. When the service migrates from JPA to a document database, normalizes tables, or changes how discounts are calculated, the external contract changes along with it.

An entity can also trigger lazy-loading queries, circular references, or unnecessary data retrieval. Serializing an entity after the transaction has closed can also throw errors due to uninitialized proxies. These are symptoms of a storage model leaking across the communication boundary.

Treat the entity as an internal model of the producer. The payload emitted to the broker is a public data type designed specifically for recipients.

## 2. Distinguishing Domain Model, Entity, and Event Contract

The three models serve different purposes:

| Model | Purpose | Key Question |
|---|---|---|
| Domain model | Expresses business rules and behaviors inside a service | What does the business allow to happen? |
| Persistence model / entity | Stores and queries internal state | How is the data stored? |
| Event contract | Publishes events and required data for consumers | What business fact has occurred? |

A service can have a domain aggregate `Order`, an entity `OrderEntity`, and an event `OrderPlacedV1`. These three types may share a few values such as `orderId`, but they do not need to have the same structure.

~~~text
                Orders Service
+---------------------------------------------+
| Domain aggregate                            |
|      |                                      |
|      +----> Persistence mapper ----> Entity |
|      |                             Database |
|      |                                      |
|      +----> Event mapper ------> Event DTO  |
+---------------------------------------------+
                                      |
                                      v
                              Outbox / Publisher
                                      |
                                      v
                              Broker destination
                                      |
                                      v
                           Consumer-owned contract
                                      |
                                      v
                             Consumer read model
~~~

The producer owns the storage model and is responsible for transforming it into the event contract. The consumer reads the contract and maps it to its own model. The consumer does not need to know which tables, entities, or aggregates the producer uses.

## 3. Designing Events Around Business Facts

An event describes something that has happened, typically named in the past tense such as `OrderPlaced`, `PaymentAuthorized`, or `ShipmentDispatched`. An event is not a command asking another service to perform an action. For example:

- `OrderPlaced` states that an order has been placed successfully.
- `PlaceOrder` is a command requesting the system to place an order.
- `OrderPlacementRejected` describes a rejection outcome, if that is an event that needs to be published.

A good contract should have these characteristics:

1. **Clear business meaning:** event names and field names reflect the language shared by both producer and consumer.
2. **Storage independence:** do not include table names, internal foreign keys, column names, or ORM annotations in the contract.
3. **Immutability over time:** an event records a fact at the time it occurred and does not change when the current state of the aggregate changes.
4. **Sufficient data for consumption:** consumers can process the event without querying back to the producer just to understand it.
5. **No unnecessary data exposure:** include only fields needed for the business process and permitted for the authorized consumers.
6. **Evolvability:** add fields and evolve schemas according to agreed-upon compatibility rules.

For example, an `OrderPlaced` event might contain the public order ID, integration customer ID, total amount, currency, and placement timestamp. It does not need the `orders` table row ID, the `customer_fk` column name, or internal risk flags.

### Choosing Between Snapshots and References

When a consumer needs data as it stood at the exact moment the event occurred, consider including the required snapshot in the event. For example, `OrderPlaced` should contain the total amount and currency at order placement time. If you only send `orderId` and require consumers to call the producer's API for the current total, the returned data may have already changed after the event was emitted.

Conversely, do not copy the entire aggregate into every event. Only include attributes needed for the event's purpose and intended consumers. For large, sensitive, or frequently changing data, you can send a stable reference along with a controlled access mechanism, while accepting that consumers will depend on that lookup service.

Distinguish snapshot data from current state. The `OrderPlaced` event records the price and total when the order was placed; a subsequent `OrderCancelled` event does not alter the content of the earlier `OrderPlaced` event.

## 4. Building Dedicated Event DTOs

Create a record or class dedicated to the event contract. For example:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderPlacedV1(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency,
    Instant placedAt
) {}
~~~

This data type contains only the fields belonging to the `OrderPlaced` contract. It has no JPA annotations, ORM relationships, database primary keys, or internal state.

You can define an envelope wrapping the payload:

~~~java
import java.time.Instant;

public record EventEnvelope<T>(
    String eventId,
    String source,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String correlationId,
    String causationId,
    T data
) {}
~~~

The envelope holds shared metadata; `data` holds the content of the specific event type. This is an application convention. If the system already uses CloudEvents, consider using the standard CloudEvents envelope and attributes instead of inventing a competing format.

Example published JSON:

~~~json
{
  "eventId": "evt-7d0b",
  "source": "orders-service",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T10:15:30Z",
  "correlationId": "corr-checkout-9001",
  "causationId": "cmd-place-order-9001",
  "data": {
    "orderId": "ord-9001",
    "customerId": "cus-2001",
    "total": 125000.00,
    "currency": "VND",
    "placedAt": "2026-11-24T10:15:29Z"
  }
}
~~~

In this contract, `eventId` identifies the event emission; `source` identifies the producer; `eventType` identifies the event type; `schemaVersion` identifies the contract version; `occurredAt` is the time the event was recorded; `correlationId` links the workflow; `causationId` references the command or event that caused it. The `data` field is the business payload.

You can use camelCase or snake_case field names. What matters is sticking to one convention consistently and keeping names and meanings stable across versions. Do not use generic fields like `value` or `data1` if consumers cannot infer their business meaning.

## 5. Mapping from Internal Models to Event Contracts

Create a dedicated mapper to convert from the domain/entity to the event DTO. The mapper acts as an anti-corruption boundary preventing storage details from leaking:

~~~java
import java.time.Instant;

public class OrderEventMapper {

    public OrderPlacedV1 toOrderPlaced(Order order, Instant occurredAt) {
        return new OrderPlacedV1(
            order.getPublicOrderId(),
            order.getCustomerReference(),
            order.getFinalTotal(),
            order.getCurrencyCode(),
            occurredAt
        );
    }
}
~~~

`Order` is the producer's domain object. `OrderPlacedV1` is the public contract. The mapper decides which values are published and how they are represented. When the entity changes from `customerDatabaseId` to `customerReference`, only the mapper and domain logic need to be adjusted if the contract keeps `customerId` unchanged.

You can use MapStruct to generate mapping code for simple fields. However, you should not rely on automatic mapping to decide event semantics. Decisions such as price snapshots, currency representation, handling missing data, or stripping internal information must be written and tested explicitly.

Several guidelines when mapping:

- Use stable business IDs instead of row keys that only have meaning inside the database.
- Translate internal enums to published contract values that have clear evolution rules.
- Normalize timestamps to UTC and clearly define whether a timestamp represents the business occurrence time or the publish time.
- Use exact numeric types for money along with currency; never use floating-point types for monetary amounts.
- Do not serialize proxies, entity relationships, or objects with circular references.
- Handle nulls and optional fields according to the schema; never force consumers to guess the meaning of empty values.
- Do not publish passwords, tokens, sensitive PII, or internal fields with no consumption purpose.

## 6. Publishing Events via Spring Cloud Stream

After constructing the DTO, you can create an envelope and store it in the outbox. Factory example:

~~~java
import java.time.Instant;
import java.util.UUID;

public class OrderEventFactory {

    private final OrderEventMapper mapper;

    public OrderEventFactory(OrderEventMapper mapper) {
        this.mapper = mapper;
    }

    public EventEnvelope<OrderPlacedV1> create(
            Order order,
            String correlationId,
            String causationId,
            Instant occurredAt) {

        OrderPlacedV1 data = mapper.toOrderPlaced(order, occurredAt);

        return new EventEnvelope<>(
            UUID.randomUUID().toString(),
            "orders-service",
            "OrderPlaced",
            1,
            occurredAt,
            correlationId,
            causationId,
            data
        );
    }
}
~~~

In a real application, the event ID and envelope content must be created once per business event. When resending due to a timeout or relay restart, replay the exact same event ID and payload. Do not invoke the factory to generate a new event ID on each retry of the same outbox record.

You can declare an output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPlaced-out-0:
          destination: orders.placed
          content-type: application/json
~~~

The binding name is an example for an output sent via `StreamBridge`. When using `StreamBridge`, you can send the created envelope to the binding named `orderPlaced-out-0`:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;

public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(EventEnvelope<OrderPlacedV1> event) {
        return streamBridge.send("orderPlaced-out-0", event);
    }
}
~~~

The snippet above illustrates sending a constructed DTO. For business flows requiring atomic consistency between database updates and event emission, do not treat calling `send` inside a database transaction as a distributed transaction. Store the serialized envelope in an outbox table within the same business transaction, then have a relay publish the outbox record. If the relay succeeds in sending but fails to mark the record as sent, the event may be redelivered; consumers need idempotency based on the event ID.

The Kafka, RabbitMQ, or Pulsar binder transports the message according to its corresponding configuration. Contract DTOs should not contain broker-specific logic. When switching binders, the goal is to keep the payload meaning intact and only adjust connection configuration and verified transport semantics.

## 7. Consumers Have Their Own Models Too

Consumers receive the contract and map it to their own read model or domain model. For example, an analytics service might only need `orderId`, `total`, `currency`, and `placedAt`:

~~~java
import java.time.Instant;

public record SalesOrderProjection(
    String orderReference,
    long totalInMinorUnit,
    String currencyCode,
    Instant orderTime
) {}
~~~

A consumer-side mapper transforms `OrderPlacedV1` into its own projection. The consumer does not need to reuse the producer's `OrderEntity`, and the producer does not need to know the consumer's reporting table structure.

~~~java
public class SalesProjectionMapper {

    public SalesOrderProjection toProjection(OrderPlacedV1 event) {
        long totalInMinorUnit = event.total()
            .movePointRight(2)
            .longValueExact();

        return new SalesOrderProjection(
            event.orderId(),
            totalInMinorUnit,
            event.currency(),
            event.placedAt()
        );
    }
}
~~~

The example above assumes the currency has two decimal places. For multi-currency systems, the decimal precision rule must be determined per currency or use a standardized monetary representation in the contract. Do not apply `movePointRight(2)` unconditionally across all currencies.

Consumers can store projections in their own database, use a document model, update a cache, or emit a new event. Changing the consumer's storage structure does not change the event contract as long as the business purpose remains the same.

## 8. Selecting Stable Data and Avoiding Internal Leaks

Before adding a field to a contract, ask:

- What business logic does the consumer need this field for?
- Does this value have stable meaning outside the publishing service?
- Is this a business ID or a technical ID that only exists inside the database?
- Should the value reflect state at event time or current state?
- Is it safe to expose this field to all consumers authorized to read the destination?
- If the producer changes its storage mechanism, will this field retain the same meaning?

Examples of fields to avoid publishing:

| Internal Field | Problem | Suitable Alternative |
|---|---|---|
| databaseRowId | Key tied to database and data import mechanisms | Stable business `orderId` |
| customer_fk | Column name and storage relationship | `customerId` or `customerReference` |
| hibernateVersion | Serves internal optimistic locking | Omit from event if consumers do not need it |
| internalRiskFlag | Internal rules and data that may be sensitive | Separate access-controlled event if a valid business need exists |
| entityStatusCode = 7 | Numeric code carrying no contract meaning | Public enum value such as `PLACED` |
| lazy-loaded customer object | ORM proxy/relationship that may pull unnecessary data | Snapshot of needed fields or a well-defined reference |

Not every technical field is forbidden. Event ID, source, schema version, and emission timestamp are useful technical metadata for the contract. What to avoid is tying the contract to how the producer organizes tables or its persistence framework.

## 9. Evolving Contracts Without Breaking Consumers

Producers and consumers are not deployed simultaneously. A new producer version may emit events before all consumers are upgraded. Therefore, schema changes must follow compatibility rules.

Generally safer changes:

- Adding optional fields that older consumers can ignore.
- Setting sensible default values for new fields when using a schema format that supports defaults.
- Adding new enum values if consumers are designed to handle unknown values.
- Adding metadata without changing the meaning of existing fields.

Changes that carry breaking risks:

- Removing fields that consumers are using.
- Renaming fields or changing data types.
- Reusing an existing field with a different business meaning.
- Changing currency units or measurement units while keeping the same field name.
- Changing null/default rules in a way that causes consumers to interpret data differently.
- Adding enum values when old consumers treat any unlisted value as an unrecoverable error.

If a change is incompatible, you can create a new event type or contract version, such as `OrderPlacedV2`, or use an appropriate destination/versioning strategy. A migration path typically involves publishing the new contract, updating consumers, running both in parallel during a transition period, monitoring consumption rates, and retiring the old contract once consumers have migrated.

Do not bump `schemaVersion` just because the producer has a new release if the contract has not changed. Application versions and event contract versions are two different things.

## 10. Schema Formats and Schema Registry

JSON is human-readable and well suited when quick integration is needed. However, when multiple teams and languages co-develop producers and consumers, schemas should be managed with a format and tooling that enforce clear compatibility rules.

| Format | Characteristics | When Suitable |
|---|---|---|
| JSON Schema | Human-readable; describes types, required fields, enums, and constraints | JSON APIs/events and polyglot integrations |
| Avro | Schema separated from payload; supports schema resolution | Kafka streams and systems needing schema evolution |
| Protocol Buffers | IDL schema, compact binary payload, multi-language code generation | Systems requiring strict contracts and transport efficiency |

A Schema Registry stores schemas, manages versions, and can check compatibility before a producer emits data. The registry does not replace designing business semantics. A schema can be structurally valid yet still cause misinterpretation if a producer changes units or field meanings.

Define a compatibility policy aligned with your deployment model:

- Backward compatibility: consumers using a new schema can read data written with an old schema, according to the format's rules.
- Forward compatibility: consumers using an old schema can read data written with a new schema.
- Full compatibility: supports both directions.
- Transitive compatibility: checks compatibility across multiple prior versions, not just the most recent one.

Exact names and details of policies depend on the Registry and schema format. Check the documentation of the tool you use before selecting a policy.

## 11. Contract Testing on Producer and Consumer

Do not merely test that JSON serialization succeeds. Verify content, semantics, and compatibility.

**Producer tests** should verify:

- The mapper does not leak persistence fields or internal data into the payload.
- Event type, schema version, and field names match the contract.
- Snapshot values reflect the point in time when the business event occurred.
- Retrying the same outbox record preserves the event ID and payload.
- Required fields, currency, timestamps, and units have valid values.

**Consumer tests** should verify:

- The consumer can read payloads conforming to the current contract.
- The consumer ignores extra fields it does not need, if the schema format permits.
- Unknown enum values or optional fields are handled according to policy.
- Mapping to its own read model does not depend on producer entities.
- Duplicate events do not trigger repeated side effects.

**Contract/integration tests** should verify:

- The producer emits a registered schema accepted by the compatibility policy.
- The consumer reads real messages through the binder and broker.
- Headers and payloads are converted accurately.
- Current consumer versions can read events from the new producer during rollout.
- DLQ and replay preserve the original event contract.

Verified sample payloads can be stored in a contract repository as fixtures. When changing a contract, update the fixtures and run compatibility tests before deploying the producer.

## 12. Design Checklist Before Publishing an Event

| Item | Question to Confirm |
|---|---|
| Name & meaning | Does the event describe a business fact that has occurred? |
| Owner | Which service is responsible for defining and emitting the contract? |
| Payload | Does it contain only the data needed by consumers? |
| Storage independence | Do any fields merely reflect tables, entities, or ORMs? |
| Snapshot | Do values accurately reflect the time the event occurred? |
| Identifiers | Are the event ID and business IDs stable? |
| Data types | Are money, timestamps, enums, nulls, and units clearly defined? |
| Security | Are any sensitive fields or internal data exposed? |
| Evolution | Is the new change compatible with existing consumers? |
| Testing | Are there mapper tests, contract tests, and broker integration tests? |
| Operations | Are outbox, idempotency, DLQ, and replay procedures in place? |

## 13. Practice Sequence and Completion Criteria

Perform an exercise with an order placement flow:

1. Create `OrderEntity` with persistence fields such as database ID, version, customer relationship, and internal status.
2. Define `OrderPlacedV1` containing only `orderId`, `customerId`, `total`, `currency`, and `placedAt`.
3. Write a mapper converting domain `Order` to `OrderPlacedV1`.
4. Create an envelope containing `eventId`, `source`, `eventType`, `schemaVersion`, `occurredAt`, `correlationId`, `causationId`, and `data`.
5. Save the event to the outbox in the same transaction as the order state change.
6. Use a relay to publish the envelope via a Spring Cloud Stream output binding.
7. Write a consumer that receives `OrderPlacedV1` and transforms it into a projection with its own structure.
8. Add a new internal field to the entity and demonstrate that the contract remains unchanged.
9. Add an optional field to the contract and verify that the old consumer can still read it.
10. Attempt a breaking change such as changing the type of `total` or removing `orderId`; determine the versioning strategy to use.

Complete the exercise when you can explain why an entity is not an event contract, write an independent event DTO, map from an internal model, publish with Spring Cloud Stream, and test contract changes without breaking older consumers.

## 14. Official References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — function, binding, and binder model.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — integrating event DTOs with `Supplier`, `Function`, and `Consumer`.
- [Spring Cloud Stream — Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html) — schema registry client and schema management.
- [Apache Avro Specification](https://avro.apache.org/docs/) — schema, writer/reader resolution, and Avro format.
- [Protocol Buffers Documentation](https://protobuf.dev/overview/) — designing message schemas and field evolution.
- [JSON Schema](https://json-schema.org/learn) — describing and validating JSON structures.
- [CloudEvents Specification](https://github.com/cloudevents/spec) — event envelope and metadata attributes.
