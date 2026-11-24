# Designing Transported Data Objects Independently from Persistence Entities

In a Spring application, data often exists in multiple forms. The database stores data according to a persistence model; the domain model expresses business rules; messages transport data between components or systems; API DTOs serve communication with clients. These models may contain some of the same information, yet they have different purposes and lifecycles.

When a persistence entity is sent directly as a message payload, the message structure becomes inadvertently coupled to how the application stores data. A change to a JPA relationship, column name, or table layout can affect consumers even though the business contract has not changed. Designing a dedicated message DTO gives you precise control over what data is published, keeps the communication contract stable, and protects the boundary between persistence and messaging.

## 1. Distinguishing Types of Data Models

### Persistence entity

A persistence entity is an object mapped by an ORM such as JPA/Hibernate to stored data. It typically carries database-oriented details:

- Annotations such as **@Entity**, **@Table**, **@Id**, **@Column**, **@OneToMany**, or **@ManyToOne**.
- Relationships between entities and collections that may be lazily loaded.
- Persistence-related state such as version, foreign keys, audit fields, or soft-delete flags.
- Methods and rules serving the persistence lifecycle.

Entities may contain ORM-generated proxies, bidirectional relationships, and circular references. Those details fit the persistence context, yet are rarely part of a data contract that an external consumer needs to know.

### Domain model

The domain model expresses business concepts and rules. It can be a domain entity, aggregate, value object, or service. The domain model focuses on protecting invariants and business behavior; it does not have to match the database table layout or message payload.

### Data Transfer Object (DTO)

A DTO is an object that carries data across a communication boundary. A DTO typically contains only the fields the receiver needs. DTOs can be used for REST APIs, messages, RPC, or another application layer. Each boundary may need its own DTO because the receivers, purposes, and compatibility policies differ.

### Message contract

A message contract is the data contract that the producer publishes and consumers rely on. It includes the payload, field meanings, data types, nullability rules, time formatting, versioning, and related metadata. A message DTO is one concrete way to represent a payload according to that contract.

Not every DTO is a message contract, and not every message must be represented by a Java DTO. What matters is that the payload has a clear structure, is independent of storage details, and is understood consistently by all parties.

## 2. Why Should You Not Send Persistence Entities Directly?

Suppose an orders table is mapped to an entity containing customer details, line items, internal notes, and storage state. A consumer receiving an order event only needs the order ID, customer ID, total amount, and occurrence timestamp. If the producer sends the entire entity, multiple issues can arise.

### 2.1. Exposing database details externally

Field names in an entity may reflect storage design such as **customerForeignKey**, **deletedFlag**, **rowVersion**, or legacy column names. Consumers should not have to change merely because the producer reorganizes its database.

When the payload is a dedicated DTO, the producer can change tables, switch ORMs, or split one entity into multiple tables without breaking the message contract, as long as the published data semantics remain intact.

### 2.2. Lazy loading and unintended queries

Hibernate can use proxies and lazy collections to load relationships only when accessed. When a serializer traverses the object graph to produce JSON, it can trigger unexpected database queries. If the persistence context is already closed, accessing them can throw errors such as **LazyInitializationException**.

Sending a DTO mapped inside the transaction boundary ensures the payload holds concrete data and does not depend on the persistence context state. Mapping should be performed while the required data is accessible, or through a clearly designed projection query.

### 2.3. Bidirectional relationships and circular references

An **Order** entity might reference **Customer**, while **Customer** holds a list of **Order** instances. A serializer following these links can loop infinitely, produce an oversized payload, or require serializer-specific annotations to break reference cycles.

A DTO contains only selected fields, such as **orderId** and **customerId**, avoiding pulling the entire ORM object graph into the message.

### 2.4. Data leakage and payload bloat

An entity might contain emails, addresses, internal notes, payment details, tokens, or staff-only fields. Sending the raw entity easily publishes more data than the consumer needs.

Larger payloads consume more bandwidth, broker memory, serialization cost, and processing time. Put only necessary data into the message. For files or large content, store the content in object storage and send a reference with controlled access permissions.

### 2.5. Tight coupling between producer and consumer

If the consumer depends directly on the producer's entity class, both sides become tightly coupled to packages, class versions, and persistence libraries. The consumer might even be forced to add JPA dependencies just to read a message.

An independent message contract allows producer and consumer to evolve separately, provided changes remain compatible with the published contract.

## 3. Designing a Good Message DTO

A transported DTO should express a clear business event or command. Choose fields by asking: what does the consumer need to know to fulfill its responsibility?

### 3.1. Include only necessary data

For example, an **OrderPlaced** event might contain:

- **eventId:** unique identifier of the event.
- **orderId:** business identifier of the order.
- **customerId:** customer identifier if the consumer needs to look up or correlate.
- **totalAmount:** total amount at the time the order was placed.
- **currency:** currency code.
- **occurredAt:** timestamp when the event occurred.

Do not include persistence-only fields such as internal foreign keys, lazy proxy state, table names, internal audit info, or confidential notes. If the consumer needs additional information, weigh including a minimal snapshot in the event versus letting the consumer query via a controlled API.

### 3.2. Use well-defined data types

Choose data types according to business semantics:

- IDs should have stable types and formats. You can use String in a JSON contract or a clearly standardized identifier type.
- Money should use **BigDecimal** or be represented in the smallest currency unit as an integer, accompanied by a currency code. Do not use floating-point numbers to represent money where precision is required.
- Absolute points in time should use **Instant** or an ISO-8601 string with a time zone, such as UTC with a Z suffix.
- Statuses should have stably agreed values; avoid relying on Java enum ordinals because enum declaration order can change.
- Collections must clearly specify the meaning of an empty list, missing field, and null value.

A contract must clearly define how data types are serialized. For instance, BigDecimal can be represented as a decimal string to avoid precision loss across systems using different numeric types. Instant is typically serialized in ISO-8601. Do not leave each consumer to guess the format.

### 3.3. Prefer immutable payloads

Because a message represents an event that occurred, the data should reflect a snapshot as of publication time. Java records are a good fit for simple immutable DTOs:

~~~java
public record OrderPlacedV1(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
~~~

Records provide concise data declarations and final components. However, immutability at the record level does not automatically make every referenced object immutable. For collections, create immutable copies; for mutable types, consider defensive copies.

### 3.4. Separate payload data from transport metadata

The payload holds business content. Message headers hold metadata for transport or observability, such as correlation ID, content type, trace context, or routing information.

Avoid placing the same information in both payload and headers without a clear reason. Information the consumer needs to understand the event belongs in the message contract; metadata for delivery/tracing can be placed in headers according to system conventions.

## 4. Mapping from Entity to Message DTO

Mapping is the step of translating data from the internal model to the published contract. Place mapping in the application layer or a dedicated mapper, where it is easy to see which fields are allowed out.

For example, a persistence entity may have more fields than the payload:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private String id;

    private String customerId;

    private BigDecimal totalAmount;

    private String currency;

    private String internalNote;

    @Version
    private long version;

    // Constructors, getters, and setters omitted.
}
~~~

This snippet illustrates a persistence entity using JPA; it requires JPA dependencies and is not a standalone program. The **internalNote** and **version** fields are for internal use and do not need to appear in the event.

The message DTO is defined separately:

~~~java
public record OrderPlacedV1(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        String currency,
        Instant occurredAt
) {}
~~~

The mapper selects only the published data:

~~~java
public final class OrderEventMapper {

    private OrderEventMapper() {}

    public static OrderPlacedV1 toOrderPlaced(
            OrderEntity order,
            String eventId,
            Instant occurredAt) {

        return new OrderPlacedV1(
                eventId,
                order.getId(),
                order.getCustomerId(),
                order.getTotalAmount(),
                order.getCurrency(),
                occurredAt
        );
    }
}
~~~

Manual mapping works well for small contracts and makes every field visible. With many DTOs, you can use MapStruct to generate mapping code at compile time. Regardless of the tool used, still review the mapping rules and verify that no internal fields leak out.

Several mapping rules need explicit decisions:

- Should a null entity value become null, an omitted field, or a default value?
- Do collections need sorting so the payload is deterministic?
- Should entity relationships be converted only to IDs, or do they need a snapshot of selected attributes?
- Should monetary amounts and timestamps be normalized?
- Does the event represent the state before or after the database update?
- When an internal field is renamed or changes type, does the message contract need to change?

Do not let a DTO access repositories or invoke lazy relations itself. A DTO should only describe data; fetching data and mapping belong to the application/service or mapper.

## 5. Sending DTOs via Spring Messaging

Spring Messaging represents a message with **Message<T>**, where the payload has type T and headers hold metadata. **MessageBuilder** helps build messages. **MessageChannel** is the abstraction for sending messages.

Once the DTO is created, the producer can wrap the DTO as the payload:

~~~java
OrderPlacedV1 event = mapper.toOrderPlaced(order, eventId, occurredAt);

Message<OrderPlacedV1> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventType", "OrderPlaced")
        .setHeader("schemaVersion", 1)
        .build();

boolean accepted = outputChannel.send(message);
~~~

This snippet illustrates Spring Messaging usage and requires the corresponding beans and imports. It shows that the payload is **OrderPlacedV1**, not **OrderEntity**. Sending through a channel does not by itself determine how serialization or broker storage works; that depends on the configured channel, adapter, message converter, and transport.

The consumer receives the payload per the contract:

~~~java
@Service
public class OrderProjectionHandler {

    public void handle(Message<OrderPlacedV1> message) {
        OrderPlacedV1 event = message.getPayload();

        // Update the read model using data from the event.
        updateOrderProjection(
                event.orderId(),
                event.customerId(),
                event.totalAmount(),
                event.currency()
        );
    }

    private void updateOrderProjection(
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            String currency) {
        // Read model update logic is implemented here.
    }
}
~~~

In real applications, the consumer may receive messages through **@ServiceActivator**, **@RabbitListener**, **@KafkaListener**, or an adapter matching the integration technology. Ensure the message converters on producer and consumer agree on payload format, data types, and schema.

## 6. Versioning and Evolving Message Contracts

Messages can be held in a broker, retried, or processed by a consumer after the producer has deployed a new version. Therefore, contracts need to remain compatible over time.

### 6.1. Compatible changes

Changes that are typically easier to keep compatible include:

- Adding an optional field that old consumers can ignore.
- Adding metadata that consumers are not required to understand.
- Expanding documentation and field descriptions without altering existing semantics.

Changes that risk breaking compatibility include:

- Removing or renaming a field currently used by consumers.
- Changing the data type, unit of measurement, or meaning of a field.
- Changing enum values in ways old consumers do not recognize.
- Turning an optional field into a required one without a migration strategy.

Not every serialization format handles unknown or missing fields the same way. With JSON, consumers must be designed to handle extra fields and missing values according to explicit rules. With Avro or Protobuf, follow that format's schema evolution rules.

### 6.2. Placing version in the contract name or metadata

You can use type names such as **OrderPlacedV1**, **OrderPlacedV2**, or keep the event name stable and publish the schema version in metadata. Choose one consistent convention so consumers know how to interpret the payload.

A version in a Java class name does not automatically guarantee compatibility. What matters is the published schema, serializer, deserializer, and deployment policy between producer and consumer.

### 6.3. Maintaining compatible consumers

A common strategy is deploying consumers capable of reading both old and new versions, and only then switching producers to the new version. When compatibility cannot be maintained, you can use a new topic/queue, a new event type, or a controlled migration process.

Do not alter the meaning of an already-published event. For example, if **totalAmount** previously meant the total after discounts and taxes, do not change it to the total before discounts merely because the field name stays the same.

## 7. Choosing a Snapshot DTO or Sending Only an ID?

There are two common design styles, each suited to different needs.

### Sending a snapshot of required data

The event contains the values the consumer needs at the moment the event occurred, such as order ID, total amount, currency, and product display name. The consumer can process it without calling back to the producer.

This approach is useful when:

- The consumer needs to know the state at the exact moment the event occurred.
- Producer and consumer need to reduce dependency on querying each other's APIs.
- The required data is small, clearly defined, and contains no unnecessary sensitive information.

Snapshots can become stale later, yet that is the nature of historical events: they record what happened at a point in time.

### Sending only an identifier and reference

The event contains only an ID or reference for the consumer to query current data via an API or read model. This makes payloads smaller and reduces data duplication, yet the consumer depends on the availability and access permissions of the system owning the data.

If the consumer queries the entity after the event is emitted, it may read newer state rather than the snapshot at event time. Choose this approach when business logic needs the latest data and query coupling is acceptable.

You can combine both: send the fields needed for common processing, along with an ID for further querying when needed. Do not send the entire entity merely to avoid designing a payload.

## 8. Persistence Transactions and Message Publishing

An important problem is synchronizing database changes with event publishing. If the application commits an order yet sending the message fails, consumers never know the order was created. If the message is sent first and the database transaction rolls back, consumers receive an event for data that was never saved.

A common solution is **Transactional Outbox**:

1. Within the same database transaction, save the business change and an outbox record containing the event DTO or enough data to construct the event.
2. After the transaction commits, a separate publisher reads unsent outbox records.
3. The publisher sends the event to the broker and marks the record as published using a resilient process.
4. Consumers process idempotently because the publisher may resend if the send status was not recorded.

Outbox helps eliminate the gap between committing data and recording the intent to emit an event. It does not by itself guarantee end-to-end exactly-once delivery; producer and consumer still need to handle duplicates, retries, and error observability.

## 9. Java 17 Example: Mapping an Entity to an Independent DTO

The following example uses records to simulate persistence data and a message DTO. The **OrderEntity** class serves as a simple persistence model; in a real application, a JPA entity would have annotations, relationships, and ORM state. The DTO holds only the published data.

Create the file **MessageDtoDemo.java**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public class MessageDtoDemo {

    record OrderEntity(
            String id,
            String customerId,
            BigDecimal totalAmount,
            String currency,
            String internalNote,
            long persistenceVersion
    ) {}

    record OrderPlacedV1(
            String eventId,
            String orderId,
            String customerId,
            BigDecimal totalAmount,
            String currency,
            Instant occurredAt
    ) {
        OrderPlacedV1 {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(customerId);
            Objects.requireNonNull(totalAmount);
            Objects.requireNonNull(currency);
            Objects.requireNonNull(occurredAt);
        }
    }

    static OrderPlacedV1 toMessageDto(
            OrderEntity entity,
            String eventId,
            Instant occurredAt
    ) {
        return new OrderPlacedV1(
                eventId,
                entity.id(),
                entity.customerId(),
                entity.totalAmount(),
                entity.currency(),
                occurredAt
        );
    }

    public static void main(String[] args) {
        OrderEntity storedOrder = new OrderEntity(
                "ORD-42",
                "CUS-7",
                new BigDecimal("129900.00"),
                "VND",
                "INTERNAL: manual review",
                3L
        );

        OrderPlacedV1 event = toMessageDto(
                storedOrder,
                "evt-001",
                Instant.parse("2026-11-07T03:00:00Z")
        );

        System.out.println("Message event: " + event.eventId());
        System.out.println("Order: " + event.orderId());
        System.out.println("Customer: " + event.customerId());
        System.out.println("Total: " + event.totalAmount()
                + " " + event.currency());
        System.out.println("Occurred at: " + event.occurredAt());
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac MessageDtoDemo.java
java MessageDtoDemo
~~~

Output:

~~~text
Message event: evt-001
Order: ORD-42
Customer: CUS-7
Total: 129900.00 VND
Occurred at: 2026-11-07T03:00:00Z
~~~

The **toMessageDto** method selects only the fields belonging to the event contract. **internalNote** and **persistenceVersion** remain on the entity and do not appear in the DTO. As a result, consumers do not depend on internal fields of the persistence model.

This example only illustrates mapping and the Java payload. When sending through a broker, the application still needs an appropriate serializer/message converter and corresponding transport configuration.

## 10. Testing Message DTOs and Contracts

You should not merely verify that the mapper does not throw an exception. You need to verify the exact published payload:

- **Mapping test:** verify every field is mapped accurately, internal fields do not appear, and null values are handled per convention.
- **Serialization test:** serialize the DTO and deserialize it back, verifying values and formats are preserved.
- **Contract test:** producer and consumer share published schemas or fixtures; verify the consumer can read sample messages of the current version.
- **Compatibility test:** when adding or modifying fields, run tests against both old and new version payloads.
- **Privacy test:** verify passwords, tokens, internal notes, and unnecessary data are absent from the payload.
- **Failure test:** check that messages with missing fields, unrecognized enums, or malformed timestamps are handled according to policy.

If using JSON, consider storing sample published payloads in source control or a schema registry to catch incompatible changes. Do not rely solely on two Java classes compiling together, because producer and consumer may run at different versions.

## 11. Common Design Mistakes

- **Sending raw JPA entities:** couples the message contract to database schemas, lazy loading, and ORM relationships.
- **Sharing a single DTO across all APIs and events:** each boundary has different needs; changing an API can accidentally break message consumers.
- **Putting too much data into the payload:** increases transport costs and risk of data exposure.
- **Sending only an ID when the consumer needs a snapshot:** the consumer may query newer state and process the wrong business point in time.
- **Changing fields or semantics without versioning:** old messages may be retried or read by new consumers, causing hard-to-trace errors.
- **Using enum ordinals or inappropriate numeric types:** changing enum order or using floating-point representations can cause data to be misinterpreted.
- **Letting DTOs contain database access logic:** couples the data boundary to persistence and makes testing difficult.
- **Not testing actual serialization:** Java objects may look right, yet the transmitted JSON or schema may be incompatible.

## 12. Process for Designing a Message DTO

When preparing to publish a new message, follow this process:

1. Determine whether the message is a command or an event and which consumers need to receive it.
2. Write the business contract: name, meaning, data type, nullability, units, and timing of each field.
3. Select the minimum data the consumer needs; distinguish snapshot data from ID references.
4. Create a dedicated DTO, preferring immutable types and avoiding persistence annotations.
5. Write a mapper from the domain/persistence model to the DTO at the application boundary.
6. Define the serializer, content type, schema version, and message headers.
7. Test mapping, serialization, compatibility, and sensitive data exclusion.
8. Define transaction, retry, deduplication, ordering, and outbox policies if needed.

Designing independent DTOs frees the producer to evolve storage while maintaining a meaningful messaging contract. A message should publish only necessary, stable, and clearly defined data. When combining explicit mapping, schema evolution, contract testing, and safe duplicate handling, components can exchange information without being tied to entity structure or ORM lifecycles.