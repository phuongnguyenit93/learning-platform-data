# Separating Domain Events from Persistence Entities

In a Spring Kafka application, data published to Kafka is often consumed by other services, retained for long periods, or replayed months later. Therefore, message structure must remain stable as an integration contract. A persistence entity, by contrast, is designed to serve how the application stores and queries data today. These two models serve different purposes, lifecycles, and rates of change.

If you serialize a JPA entity directly to send to Kafka, changes in database mapping can accidentally alter the public payload. Lazy relationships, Hibernate proxies, bidirectional reference cycles, internal fields, sensitive data, and persistence annotations can also leak into serialization. Consumers then become coupled to the producer's database structure and Java classes.

A safe design keeps persistence entities at the storage boundary, represents events with an independent object, and maps the data to be published onto an integration event contract. An event describes a business fact that has occurred, with an explicit schema and semantics, without carrying an ORM-managed object graph.

This lesson focuses on separating persistence entities, domain events, and integration events; mapping data; serializing with Spring Kafka; evolving schemas without breaking old consumers; and publishing reliably using a transactional outbox.

## Learning Objectives

After this lesson, you will be able to:

- Explain why JPA entities should not be sent directly to Kafka.
- Distinguish domain entities, persistence entities, domain events, and integration events.
- Design event contracts independent of database structure.
- Select data to include in an event and exclude internal or sensitive fields.
- Write mappers from persistence models to event DTOs.
- Handle lazy relationships when constructing events.
- Configure JSON serializers/deserializers and type headers in Spring Kafka.
- Choose schema evolution strategies compatible with deployed consumers.
- Distinguish snapshot events from reference-only events.
- Use a transactional outbox to coordinate database commits and Kafka publishing.
- Test mappers, serialization, compatibility, and duplicate delivery.
- Plan a migration from publishing entities to publishing stable event contracts.

## 1. Persistence entities and events solve two different problems

A persistence entity describes the state an application stores in its database. It typically contains primary keys, relationships, audit columns, optimistic locking versions, internal flags, and JPA annotations.

An event describes a fact meaningful to the business or other systems. For example, `OrderCreated` expresses that an order has been created. Consumers need to know which order was created, when it occurred, the data required for their business logic, and how to identify the event. Consumers do not need to know which columns the `orders` table has, what JPA relationships the entity defines, or which proxy Hibernate uses.

| Criterion | Persistence entity | Event contract |
|---|---|---|
| Purpose | Store and query state | Publish a business fact or state change |
| Lifecycle | Scoped to a transaction and persistence context | Can be stored, replayed, and read long-term |
| Structure | Tied to database schema and ORM | Governed by producer-consumer contract |
| Relationships | May contain object graphs and lazy proxies | Should contain values or deliberate snapshots |
| Evolution | Can change alongside database migrations | Requires managing consumer compatibility |
| Annotations | `@Entity`, `@Id`, `@ManyToOne`, `@Version` | Needs no JPA annotations |
| Data | May include internal fields | Contains only data authorized for publication |

Example entity:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    @Column(name = "internal_risk_score")
    private Integer internalRiskScore;

    @Version
    private long version;

    @Column(name = "created_by")
    private String createdBy;

    // getters, setters and persistence behavior
}
~~~

If `OrderEntity` is sent directly, the payload may expose or be affected by `customer`, `lines`, `internalRiskScore`, `version`, and other attributes. Changing a JPA relationship or adding a database column could alter the payload without any intentional event versioning decision.

An event should be a dedicated data type containing only the information to publish:

~~~java
public record OrderCreatedV1(
        UUID eventId,
        UUID orderId,
        String orderNumber,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        String correlationId,
        List<OrderLineCreatedV1> items
) {
    public OrderCreatedV1 {
        items = List.copyOf(items);
    }
}

public record OrderLineCreatedV1(
        String sku,
        String productName,
        int quantity,
        long unitPriceMinor
) {}
~~~

The event contains no `CustomerEntity`, `OrderLineEntity`, Hibernate proxies, or JPA annotations. The `items` list is copied so the event remains immutable after creation.

## 2. Distinguishing domain entities, persistence entities, and domain events

These terms can be structured differently across architectures, but their responsibilities must remain clear.

**Domain entity** is a business object with identity and behavior. It enforces invariants, such as an order not transitioning to paid unless it has been confirmed.

**Persistence entity** is the representation used for storage by an ORM or persistence framework. In simple applications, the domain entity and persistence entity may share one class. In layered architectures, they may be two separate types.

**Domain event** is a business fact that occurred inside a bounded context. Names typically use past tense, such as `OrderCreated`, `OrderConfirmed`, or `PaymentCaptured`. The event should carry the data needed to describe the occurrence without holding references to an ORM-managed object graph.

**Integration event** is the contract published to other services or bounded contexts. It can be mapped from a domain event and versioned independently of internal models.

The flow can be organized as follows:

~~~mermaid
flowchart TD
    A["Use case / Application service"] --> B["Domain model"]
    B --> C["Domain event"]
    B --> D["Persistence mapping"]
    D --> E["JPA persistence entity"]
    C --> F["Integration event mapper"]
    F --> G["Versioned event contract"]
    G --> H["Outbox / KafkaTemplate"]
    H --> I["Kafka topic"]
    I --> J["Consumer service"]
~~~

Not every application needs two separate event layers. In smaller systems, the domain event and integration event can share one class if semantics and ownership are designed cleanly. However, never let a persistence entity class automatically become the event contract merely because it already holds the data.

## 3. Why is serializing JPA entities directly risky?

### 3.1. Lazy loading and persistence context

JPA commonly loads relationships with a `LAZY` strategy. When a serializer accesses `customer` or `lines` after the transaction closes, Hibernate may throw `LazyInitializationException`. If the transaction stays open, serialization can trigger unexpected extra queries.

Example:

~~~java
kafkaTemplate.send("orders", orderEntity.getId().toString(), orderEntity);
~~~

The serializer must invoke getters to produce JSON. If a getter accesses a lazy relationship, serialization can trigger SQL queries or fail because the persistence context has closed.

### 3.2. Bidirectional reference cycles

An `Order` entity may reference `Customer`, while `Customer` holds a list of orders. A serializer traversing these relationships can enter infinite recursion or produce huge payloads.

~~~text
Order
  -> Customer
       -> Orders
            -> Customer
                 -> ...
~~~

Jackson annotations such as `JsonManagedReference`, `JsonBackReference`, or `JsonIgnore` can make the JSON serializable, yet they are merely patching entity export rather than establishing a stable integration contract.

### 3.3. Database changes accidentally alter messages

Adding an `internalStatus` column, renaming a property, altering a relationship, or changing a data type can alter the serialized JSON. Old consumers may fail to understand new fields, or new consumers may start depending on internal fields that should never have been exposed.

Database migrations and event schema evolution are two distinct processes. Never let database migrations dictate Kafka payload changes.

### 3.4. Exposing data not meant for consumers

Entities may hold emails, phone numbers, addresses, internal notes, risk scores, audit metadata, or operational fields. Serializing the entire entity broadcasts those fields to multiple services and retains them long-term in Kafka.

Event contracts should apply the data minimization principle: publish only the data consumers are authorized and genuinely need to receive.

### 3.5. Consumers become coupled to producer Java classes

If a serializer sends a type header containing the full class name, consumers may need to know the producer's package and class name. When the producer refactors packages, consumers may fail to deserialize even if JSON fields remain unchanged.

Spring Kafka supports type headers and type mappings, but type headers are serialization metadata, not a domain contract. In multi-service or polyglot systems, identify payload types via stable schemas or event types rather than internal class names.

## 4. Designing an independent event contract

A well-designed event contract should answer:

- What event occurred?
- Which aggregate or business object is involved?
- When did the event occur?
- What data do consumers need to react?
- How can the event be identified and deduplicated?
- How do consumers know which schema or event type is being sent?
- Which fields are required, optional, or defaulted?

An envelope typically includes metadata:

| Field | Meaning |
|---|---|
| `eventId` | Unique identifier of an event |
| `eventType` | Stable event name |
| `schemaVersion` | Contract version |
| `occurredAt` | Business occurrence timestamp |
| `producer` | Service emitting the event |
| `correlationId` | Links to an originating request or workflow |
| `aggregateId` | Identity of the associated aggregate |

This metadata can live in the payload, Kafka headers, or schema registry metadata. Choose one consistent convention and document it in the contract. Avoid conflicting sources of truth, such as `eventType` in JSON differing from the header.

Concrete event example:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        String orderNumber,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt,
        String correlationId
) {}
~~~

The name `OrderConfirmedV1` indicates version 1 of the event contract. Putting the version in the class name is only a code-organization choice; the wire contract still needs an explicit `eventType`/schema version and should not depend on Java class names.

### Name events after facts that occurred

Prefer:

- `OrderCreated`
- `OrderConfirmed`
- `PaymentCaptured`
- `ShipmentDispatched`

Avoid generic or imperative names:

- `Order`
- `UpdateOrder`
- `ProcessPayment`
- `DoShipment`

An event describes something that already happened. A command describes something requested to happen. Distinguishing the two message types helps consumers interpret semantics properly and avoid treating an event as an unconfirmed request.

## 5. Choosing snapshot vs. reference-only events

There are two common ways to represent data in an event.

A **snapshot event** carries the necessary values as of the moment the event occurred. For example, `OrderCreated` carries `orderNumber`, `customerId`, total amount, currency, and confirmed line items.

A **reference event** carries only `orderId` or `aggregateId` so consumers call an API or query the source when more details are needed.

| Approach | Advantages | Trade-offs |
|---|---|---|
| Snapshot | Consumers process independently; replays reproduce point-in-time data | Larger payloads; requires managing sensitive data |
| Reference | Small payloads; reduces data duplication | Consumers depend on source API/database and may read current state instead of state at event time |

If a consumer needs the order price at creation time, the event should carry a snapshot of the price and currency. If it carries only `orderId` and calls an API hours later, prices may have changed and the consumer cannot reconstruct the original event.

Do not send the entire entity just to create a snapshot. Select the exact contract fields and convert relationships into scalar values or defined nested value objects.

## 6. Mapper from persistence entity to event

The mapper is the translation boundary between the persistence model and the event contract. It should be explicit, easy to test, and extract only required data.

Manual mapper example:

~~~java
@Component
public class OrderEventMapper {

    public OrderCreatedV1 toOrderCreated(
            OrderEntity order,
            UUID eventId,
            Instant occurredAt,
            String correlationId) {

        List<OrderLineCreatedV1> items = order.getLines()
                .stream()
                .map(line -> new OrderLineCreatedV1(
                        line.getProduct().getSku(),
                        line.getProduct().getName(),
                        line.getQuantity(),
                        line.getUnitPriceMinor()
                ))
                .collect(Collectors.toList());

        return new OrderCreatedV1(
                eventId,
                order.getId(),
                order.getOrderNumber(),
                order.getCustomer().getId(),
                order.getTotalAmountMinor(),
                order.getCurrency(),
                occurredAt,
                correlationId,
                items
        );
    }
}
~~~

This example shows that the event receives only the required values. It retains no references to `order`, `customer`, or `product` entities.

If using MapStruct, the mapper should likewise take entities and return event DTOs. Do not let MapStruct automatically map unneeded relationships. Declare fields explicitly, ignore non-contract fields, and inspect generated mappings when schemas change.

### Controlling lazy relationships

The mapper in the example accesses `customer`, `lines`, and `product`. Ensure required data is loaded within the transaction.

Repository example using an entity graph:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @EntityGraph(attributePaths = {
            "customer",
            "lines",
            "lines.product"
    })
    Optional<OrderEntity> findWithEventDataById(UUID id);
}
~~~

Application service calling the mapper while the transaction and persistence context are active:

~~~java
@Transactional(readOnly = true)
public OrderCreatedV1 buildEvent(UUID orderId) {
    OrderEntity order = orderRepository
            .findWithEventDataById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    return orderEventMapper.toOrderCreated(
            order,
            UUID.randomUUID(),
            Instant.now(),
            null
    );
}
~~~

In this example, `eventId` is generated when constructing the event. For events stored in an outbox, `eventId` must be generated once and saved with the outbox record so republished attempts preserve the same identity.

Do not enable Open Session in View just so serializers can access lazy entities. That hides persistence boundaries and can trigger uncontrolled queries during serialization.

## 7. Creating events from domain events instead of reading entities in the Kafka layer

In a domain-oriented architecture, an application service can receive domain events after an aggregate changes state. An integration adapter maps the domain event to an integration event.

Domain event example:

~~~java
public record OrderConfirmedDomainEvent(
        UUID orderId,
        UUID customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt
) {}
~~~

Integration contract:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        String orderId,
        String customerId,
        long totalAmountMinor,
        String currency,
        Instant occurredAt
) {}
~~~

Mapper:

~~~java
@Component
public class OrderIntegrationEventMapper {

    public OrderConfirmedV1 toIntegrationEvent(
            OrderConfirmedDomainEvent event,
            UUID eventId) {

        return new OrderConfirmedV1(
                eventId,
                event.orderId().toString(),
                event.customerId().toString(),
                event.totalAmountMinor(),
                event.currency(),
                event.occurredAt()
        );
    }
}
~~~

Domain events and integration events may share data, yet they do not have to share identical structures or names. Domain events reflect the bounded context's internal language; integration events reflect what external consumers are allowed to rely on.

When an internal domain refactor does not affect the integration contract, the mapper can keep the integration event unchanged. That is a major benefit of the translation boundary.

## 8. Publishing events with KafkaTemplate

Once the event DTO is constructed, the producer sends only that contract. Never pass a persistence entity into `KafkaTemplate`.

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedV1> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedV1> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedV1>> publish(
            OrderCreatedV1 event) {

        return kafkaTemplate.send(
                "orders.created",
                event.orderId().toString(),
                event
        );
    }
}
~~~

The key is typically the aggregate ID or a stable business key so events for the same aggregate land in the same partition of a topic. Do not use `eventId` as the key if business logic requires ordering per `orderId`.

Example consumer listener receiving the contract:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreatedV1 event) {
    billingService.prepareInvoice(event);
}
~~~

The consumer does not need dependencies on `OrderEntity`, `CustomerEntity`, or producer repositories. It only needs to understand the event contract and the data it publishes.

The example uses `CompletableFuture` because Spring Kafka 3.0 and later return `CompletableFuture` from `KafkaTemplate.send()`. In Spring Kafka 2.x, the API returns `ListenableFuture` and callbacks must match that version. Examples using Java `record` assume Java 16 or later; older projects can use immutable classes with constructors and getters.

## 9. Configuring JSON serialization independently of entity classes

Spring Kafka provides Jackson-based `JsonSerializer` and `JsonDeserializer`. The serializer converts objects to JSON bytes; the deserializer needs either a target type or type metadata to determine the target class.

Spring Boot configuration example:

~~~yaml
spring:
  kafka:
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.add.type.headers: false

    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.contract.OrderCreatedV1
        spring.json.trusted.packages: com.example.contract
        spring.json.use.type.headers: false
~~~

This example is for a consumer group receiving only `OrderCreatedV1`. If a topic holds multiple event types, design type mapping or an envelope with `eventType` and configure an explicit resolver. Do not disable type headers and expect a single default deserializer to identify multiple payload types automatically.

### Type headers and class names

By default, Spring Kafka can add type information to Kafka headers. That header typically carries info identifying the payload's Java type. When producer and consumer are independent services, depending on the producer's package/class name increases coupling.

You can choose one of these approaches:

- Use a fixed target type for a single-event-type topic and omit type headers.
- Use type mapping with stable tokens, mapping tokens to each service's local class.
- Use an envelope with an explicit `eventType` and a resolver accepting only permitted types.
- Use Schema Registry with Avro, Protobuf, or JSON Schema when centralized schema management is required.

Add only genuinely trusted packages to trusted packages. Do not configure wildcards across all packages just to bypass deserialization errors. Type metadata arriving in messages must be treated as untrusted external input.

Spring Kafka documentation describes `ADD_TYPE_INFO_HEADERS`, `USE_TYPE_INFO_HEADERS`, `VALUE_DEFAULT_TYPE`, `TRUSTED_PACKAGES`, and `TYPE_MAPPINGS`; check your exact dependency version because serializer APIs and class names can evolve across Spring Kafka generations. <https://docs.spring.io/spring-kafka/reference/kafka/serdes.html>

## 10. Do not share a persistence module between producer and consumer

A common anti-pattern is creating a shared module containing entities and having both producer and consumer import it. Whenever an entity changes, both services may have to upgrade module versions even if the consumer uses only a subset of fields.

A contract module should contain only public event types and related schemas—never JPA entities, repositories, or persistence configuration.

You can organize modules like this:

~~~text
order-service
  domain/
  persistence/
    OrderEntity
    OrderRepository
  integration/
    OrderEventMapper
    OrderEventPublisher

order-contract
  OrderCreatedV1
  OrderConfirmedV1
  OrderLineCreatedV1

billing-service
  messaging/
    OrderCreatedListener
  application/
    BillingService
~~~

Some systems avoid sharing Java contract modules altogether and instead manage schemas in Schema Registry or a dedicated schema repository. Consumers can then be written in Java, Go, Python, or .NET and still understand the same wire contract.

If using a shared library, keep it small and versioned independently. Avoid pulling the producer's domain or persistence packages into consumer dependencies.

## 11. Schema evolution is the event's own contract

Database schemas can evolve for query tuning, normalization, or storage changes. Event schemas evolve when consumers need new data or when event semantics change.

Not every entity change requires an event change. For example, adding an `internalRiskScore` column used only by an internal fraud engine does not mean `OrderCreated` must add that field.

Conversely, if consumers need a new `deliveryMethod`, that is a contract change requiring compatibility evaluation.

### Common compatibility directions

| Mode | General meaning | When to consider |
|---|---|---|
| Backward | New schema can read data written under old schema | New consumers must read old records |
| Forward | Old consumer/schema can read data written under new schema | New producers deploy before consumers |
| Full | Both backward and forward | Two generations of producers/consumers must remain mutually compatible |
| None | No compatibility check | Use only when accepting planned breaking changes |

Exact names and check directions depend on the Schema Registry. For long-retention event topics, consider historical data too; transitive modes validate against multiple older versions rather than only the preceding version.

Do not look solely at the names `BACKWARD` or `FORWARD` and apply them mechanically. Check your Registry, format (Avro/Protobuf/JSON Schema), and how serializers/deserializers resolve schema IDs.

## 12. Rules for safe event changes

Usually lower-risk changes:

- Adding optional fields with sensible defaults.
- Adding metadata that does not alter existing semantics.
- Adding a new value to an enum if old consumers have a strategy for unknown values.
- Adding an optional nested object with an explicit schema.
- Enriching contract documentation without changing wire format.

Changes that can break consumers:

- Removing a field still used by consumers.
- Renaming a field without a transition phase.
- Changing data types, such as `String` to `Integer`.
- Changing timestamp units from milliseconds to seconds.
- Changing a field's meaning while keeping the same name.
- Changing currency or rounding rules without declaring semantics.
- Adding a new enum value when old consumers cannot handle unknown values.
- Replacing a snapshot event with a reference event without coordination.

One key rule: a new field must not become mandatory for old consumers if producers can emit messages that old consumers do not understand.

### Example adding an optional field

Version 1:

~~~json
{
  "eventId": "e-100",
  "orderId": "o-100",
  "currency": "VND",
  "totalAmountMinor": 250000
}
~~~

Version 2 adds `sourceChannel`:

~~~json
{
  "eventId": "e-100",
  "orderId": "o-100",
  "currency": "VND",
  "totalAmountMinor": 250000,
  "sourceChannel": "MOBILE"
}
~~~

If old consumers ignore unknown fields and the contract permits optional fields, they can keep operating. New consumers must define behavior when reading old records missing `sourceChannel`.

Do not rely on a particular serializer to assume every consumer ignores unknown fields. Test actual Jackson configurations, schema formats, and running versions.

## 13. When is a new event version needed?

You do not need a new version simply for adding a compatible optional field. However, create a new version or event type when semantics change or old consumers cannot safely interpret the data.

Examples:

- `OrderCreatedV1` carries totals in minor currency units.
- A change switches `totalAmount` to a decimal string with a different scaling rule.
- The old event represented order creation; the new event changes to mean order paid and inventory reserved.

Do not keep the same `eventType` while changing its meaning. Consumers might deserialize cleanly yet process business logic wrongly—a failure far more dangerous than a parse error.

Versioning strategies:

1. Add compatible schema fields on the same topic.
2. Use a new `eventType`/version on the same topic if consumers dispatch by type.
3. Use a new topic when parallel rollout or clear ownership isolation is needed.
4. Dual-publish both contracts during a controlled migration period.
5. Retire the old version once confirmed no consumers require it.

Do not publish two equivalent events without an `eventId` or explicit migration plan. Consumers might process both and produce duplicate side effects.

## 14. Events are historical facts, not copies of current entities

An event must preserve the truth at the time it occurred. If `OrderCreated` is emitted at 10:00 and the order's address changes at 11:00, replaying `OrderCreated` must still reflect the 10:00 data per contract.

Do not re-serialize the current entity whenever an old event needs to be replayed. The entity may have changed, relationships may have been deleted, or fields may have migrated.

If an event carries a snapshot, construct the payload at the business moment and store that exact payload in an outbox/event store if replay is needed.

If an event carries only a reference, explicitly document that consumers fetch current state from the source API; that is a different semantic from a historical snapshot.

Do not use events as a mechanism to dump entire database rows. Events are contracts communicating business facts.

## 15. Transactional outbox: storing events in the business transaction

If an application service updates the database and calls `KafkaTemplate` directly inside the same `@Transactional` method, a standard database transaction and a Kafka producer transaction do not automatically form one atomic transaction.

Possible failure modes:

- Database commit succeeds, Kafka publish fails: consumers never receive the event.
- Kafka publish succeeds, database rolls back: consumers receive an event for an uncommitted change.
- Publish succeeds, service crashes before recording completion: retries may publish duplicates.

The transactional outbox pattern solves this by writing business state and an outbox row within the same database transaction. A separate relay reads the outbox and publishes to Kafka.

~~~mermaid
flowchart TD
    A["Application service"] --> B["DB transaction"]
    B --> C["Update order"]
    B --> D["Insert outbox row"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["KafkaTemplate"]
    G --> H["Kafka topic"]
    H --> I["Consumer"]
~~~

Minimal outbox entity example:

~~~java
@Entity
@Table(name = "outbox_message")
public class OutboxMessage {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String aggregateId;

    @Column(nullable = false)
    private String eventType;

    @Column(nullable = false)
    private int schemaVersion;

    @Lob
    @Column(nullable = false)
    private String payload;

    @Column(nullable = false)
    private Instant createdAt;

    private Instant publishedAt;

    // status, attempts and persistence methods
}
~~~

Application service constructs the event DTO, serializes it to a payload, and persists the outbox record:

~~~java
@Transactional
public void createOrder(CreateOrderCommand command) {
    OrderEntity order = orderFactory.create(command);
    orderRepository.save(order);

    UUID eventId = UUID.randomUUID();
    Instant occurredAt = Instant.now();

    OrderCreatedV1 event = orderEventMapper.toOrderCreated(
            order,
            eventId,
            occurredAt,
            command.correlationId()
    );

    String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    }
    catch (JsonProcessingException ex) {
        throw new EventSerializationException(ex);
    }

    outboxRepository.save(
            OutboxMessage.pending(
                    event.eventId(),
                    event.orderId().toString(),
                    "OrderCreated",
                    1,
                    payload,
                    occurredAt
            )
    );
}
~~~

`OrderEntity` and the outbox row commit or roll back in the same database transaction. Kafka is not called inside this business transaction.

The relay reads unpublished outbox rows, sends payloads to their topics, and marks them published after broker acknowledgment. Design locking/claiming so multiple relay instances do not process the same row concurrently.

### Outbox can still publish duplicates

If Kafka accepts the record but the relay crashes before updating `publishedAt`, the row will be re-sent when the relay restarts. This is standard at-least-once outbox behavior.

Preserve the exact `eventId` across every publish retry and make consumers idempotent by `eventId`. Never generate a new `eventId` when the relay retries the same outbox row.

If per-aggregate ordering is required, the relay must preserve publish order for the same aggregate or use sequence numbers checked by consumers. Multiple parallel relays can publish events of the same aggregate out of order without proper claiming/partitioning.

## 16. Why `@TransactionalEventListener(AFTER_COMMIT)` is insufficient for critical publishes

Spring's `@TransactionalEventListener(phase = AFTER_COMMIT)` can publish after the database transaction commits, preventing publishing when a transaction rolls back.

However, a window exists between the database commit and the Kafka send callback. If the process crashes in that gap, the event is lost and no outbox row exists for a relay to recover.

Therefore:

- Use `AFTER_COMMIT` for non-critical or reconstructible side effects.
- Use a transactional outbox when event emission must be durable alongside the business transaction.
- Never claim either mechanism provides an atomic database-to-Kafka transaction without true distributed coordination.

An outbox adds a table, relay, and cleanup job, but provides durable state to retry publishing after restarts.

## 17. Managing currency, time, and data types in contracts

An event contract must define semantics, not just Java types.

### Currency

Never use `double` or `float` for money. Two common choices:

- Integer in minor units, such as 1250 VND minor units or 1099 cents depending on currency.
- Decimal string with documented scale and rounding rules.

If using `totalAmountMinor`, the contract must specify how the currency exponent is determined. Do not assume every currency has two decimal digits.

### Time

Use timestamps with explicit timezone/offset, typically UTC `Instant` or ISO-8601. Specify that `occurredAt` is the business occurrence time, not when Kafka received the record.

If publish time is needed, use a separate `publishedAt` field. Never change units between milliseconds and seconds across versions without a contract change.

### Enums and unknown values

Old consumers may receive new enum values. Define unknown-value behavior: ignore, log, quarantine, or map to `UNKNOWN` if schema and business rules allow.

### Null and absent fields

`null`, absent fields, and default values can carry distinct semantics. The contract must state which fields are required, nullable, optional, and defaulted. Do not rely on how Jackson serializes nulls to implicitly define the contract.

## 18. Protecting data and bounding event payloads

Events can persist in Kafka longer than database rows and be read by multiple services. Treat payloads as data crossing a system boundary.

Before adding a field, determine:

- Which consumers need this field?
- Does it contain personal or sensitive data?
- Can an identifier be sent instead of sensitive values?
- Are topic retention and access controls appropriate?
- Is encryption or masking required?
- Could the field appear in logs, tracing, or dead-letter topics?

Never put passwords, access tokens, secrets, full payment credentials, or internal fields into events. Kafka ACLs control who reads a topic; they do not replace minimizing data inside payloads.

If an event must carry personal data, define its purpose, access rights, retention, and erasure/deletion compliance procedures per system data policy.

## 19. Testing the boundary between persistence and event contracts

Do not merely assert that a mapper returns a different object from the entity. Verify that the contract is independent of the database schema and works with real serialization.

Test layers:

### Mapper unit tests

- Build an entity with `customer`, `lines`, and `product`.
- Verify the mapper extracts only published fields.
- Verify `internalRiskScore`, JPA `version`, or audit user fields do not appear in the event.
- Verify null/optional relationships behave predictably.
- Verify the snapshot matches the state at event creation time.

### Serialization contract tests

- Serialize the event to JSON.
- Check field names, data types, and timestamp formatting.
- Deserialize the payload using the target type used by consumers.
- Verify the producer class name is not needed in type headers if the contract does not depend on it.
- Verify unknown fields and missing fields behave per defined rules.

### Compatibility tests

- New consumers read old version payloads.
- Old consumers read new version payloads if the compatibility policy requires it.
- New enum values are handled properly.
- Field changes do not alter existing semantics.
- Schema Registry rejects breaking changes when policies are enabled.

### Outbox integration tests

- On database rollback, neither business row nor outbox row exists.
- On database commit, both rows exist together.
- If Kafka publish succeeds and the relay crashes before marking published: the event can be re-sent with the exact same `eventId`.
- Multiple relay instances do not lose rows.
- Consumers receiving duplicates apply side effects only once.
- Event ordering for the same aggregate is preserved as required.

Use Testcontainers for the database and Kafka when validating real integration behavior. Use static JSON fixtures to test wire contracts; avoid simply serializing and deserializing the exact same class, as producer and consumer could share the same bug while tests pass.

## 20. Migrating from publishing entities to publishing event DTOs

If the system currently sends JPA entities directly, migrate in controlled steps:

1. Inventory topics, producers, and consumers reading the entity payload.
2. Document which fields consumers actually use, including fields read from nested relationships.
3. Define a new event contract driven by integration needs rather than copying the whole entity.
4. Implement mappers and unit tests for published fields.
5. Choose a versioning path: compatible field additions, a new type, or a new topic.
6. Configure serializers/deserializers and type mappings for the contract.
7. Deploy consumers able to read the new contract before switching producers fully.
8. Trial-publish or dual-publish during transition if needed, with clear event identity and deduplication.
9. Monitor consumer lag, deserialization errors, schema errors, and business processing outcomes.
10. Retire the old entity payload after confirming no consumers depend on it.
11. Remove persistence dependencies from any shared contract module.
12. Retain fixtures of old payloads to test replay and migrations.

Never change payloads on a topic without inventorying consumers. An old consumer may still be running in a slow-updating deployment or an infrequent replay job.

If dual-publishing, avoid emitting two semantically identical events without consumers knowing they represent two representations of the same fact. Use stable `eventId`s, separate topics/versions, and an explicit retirement plan.

## 21. Common design mistakes

**Serializing JPA entities directly.** Payloads depend on ORM, lazy loading, and database mappings. Create dedicated event DTOs.

**Using entities as shared contracts.** Consumers become coupled to the producer's persistence module. Create an independent contract module or manage schemas separately.

**Mapping the entire object graph.** Payloads grow huge, risk reference cycles, and leak internal data. Select fields to publish and replace relationships with IDs or value snapshots.

**Mapping entities after the transaction closes.** Lazy relationships can throw `LazyInitializationException`. Fetch needed data and map within the transaction or use projections.

**Adding a database column and accidentally adding an event field.** Contracts change without compatibility review. Mappers must map fields explicitly.

**Using type headers containing class names as the contract.** Consumers couple to producer packages. Use stable `eventType`/schemas or type mappings.

**Disabling type headers without configuring a target type.** Consumers do not know which class to deserialize into. Configure a default type or explicit resolver.

**Trusting all packages during deserialization.** Messages could trigger unintended class resolution. Allowlist only permitted packages/types.

**Changing semantics without changing versions.** Consumers deserialize cleanly yet misinterpret events. Create a new event type/version when meaning changes.

**Sending references while expecting historical snapshots.** Source APIs return current state, not state at event time. Choose snapshots if exact replay is needed.

**Publishing directly to Kafka inside a database transaction and assuming atomicity.** Database and Kafka can commit independently. Use an outbox or proper coordination.

**Generating a new `eventId` on each relay retry.** Consumers cannot deduplicate the same fact. Persist `eventId` in the outbox and reuse it on retries.

**Testing only round-trips of the same class.** Tests miss contract coupling. Use JSON fixtures and cross-version compatibility tests.

## 22. Checklist for separating events from persistence entities

- [ ] Persistence entities serve only storage and querying.
- [ ] Event contracts have no JPA annotations or ORM proxies.
- [ ] Domain events and integration events have clear ownership.
- [ ] Event names describe facts that occurred.
- [ ] Stable `eventId` and appropriate `aggregateId`/business keys exist.
- [ ] `occurredAt` and time semantics are clearly defined.
- [ ] Only fields genuinely needed by consumers are published.
- [ ] Internal fields, secrets, or unnecessary sensitive data are excluded.
- [ ] Entity relationships are converted into IDs or snapshot value objects.
- [ ] Mappers are tested independently.
- [ ] Lazy relationships are deliberately fetched before mapping.
- [ ] JSON serializers/deserializers have clear target types or type mappings.
- [ ] Wire contracts do not depend on producer class names or packages.
- [ ] Trusted packages are restricted.
- [ ] Schema evolution follows a compatibility policy.
- [ ] Semantic changes introduce a new event type/version.
- [ ] Snapshot vs. reference is chosen based on replay and consistency needs.
- [ ] Database updates and Kafka publishing use an appropriate reliability mechanism.
- [ ] Outbox preserves `eventId` across retries.
- [ ] Consumers are idempotent by `eventId`.
- [ ] Mapper, serialization, compatibility, and outbox integration tests exist.
- [ ] A migration plan exists if topics currently carry entity payloads.

## Conclusion

Persistence entities model stored data and ORM relationships; domain events express business facts; integration events are public contracts published to other services. Never serialize entities directly to Kafka, as doing so drags database schemas, lazy relationships, proxies, internal fields, and producer Java classes into the public payload. Create independent event DTOs, map explicitly, choose snapshots or references based on semantics, manage type and schema versions, and test compatibility. When events must be emitted alongside database changes, a transactional outbox persists business state and event intent in the same transaction; since relays can republish, stable `eventId`s and idempotent consumers remain essential.

## References

- [Spring Kafka – Serialization, Deserialization, and Message Conversion](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)
- [Spring Kafka – Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Apache Kafka – Design and Implementation](https://kafka.apache.org/documentation/#design)

