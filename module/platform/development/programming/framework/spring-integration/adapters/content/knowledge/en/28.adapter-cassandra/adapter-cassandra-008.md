# Mapping payloads to rows with Spring Integration and Apache Cassandra

## 1. Problem: a Spring Message does not become a Cassandra row automatically

A service receives `OrderPaid` JSON from HTTP, JMS, or Kafka. Spring Integration wraps that data into a `Message<?>` and pushes it over a `MessageChannel` to the Cassandra outbound adapter. If the payload remains a `String` or `Map<String, Object>`, the Cassandra adapter in `INSERT` mode **cannot automatically know** that `orderId` maps to column `order_id` or which table should receive an arbitrary JSON object as a row.

We must clearly define the boundaries:

~~~mermaid
flowchart LR
    A["HTTP/JMS/Kafka body: JSON"] --> B["Deserialize / validate"]
    B --> C["Business DTO: OrderPaidEvent"]
    C --> D["Spring Integration Transformer"]
    D --> E["@Table entity: OrderEventRow"]
    E --> F["CassandraMessageHandler: INSERT"]
    F --> G["ReactiveCassandraOperations"]
    G --> H["MappingCassandraConverter"]
    H --> I["CQL INSERT with bound values"]
    I --> J[("Cassandra row")]
~~~

**Mapping a payload to a row** is more than renaming fields. It includes business identity, partition keys, Java↔CQL types, timestamps/timezones, null/UNSET semantics, serialization, entity metadata, and how conversion errors affect source acknowledgment.

This lesson belongs to the **Adapter Cassandra** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module teaches connecting external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing exchange flows over files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. While the exercises focus on Cassandra, the validate → transform → map → persist pattern also applies regardless of which source adapter feeds the flow.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish transport payloads, business DTOs, Spring Messages, Cassandra entities, and CQL rows.
2. Declare `@Table`, `@PrimaryKey`, `@Column`, and composite keys via `@PrimaryKeyClass`/`@PrimaryKeyColumn`.
3. Use `MappingCassandraConverter`/`ReactiveCassandraOperations` to map entities to CQL columns and back.
4. Write a `Transformer` in Java DSL to convert `Message<OrderPaidEvent>` into `Message<OrderEventRow>`.
5. Handle `text`, `int`, `bigint`, `decimal`, `timestamp`, `uuid`, collections, and JSON text types.
6. Distinguish Spring Integration `Type.INSERT`, `ingestQuery`, and `statementFunction`; know when to pick direct CQL/`RowMapper`.
7. Design error handling, idempotency, replay, schema versioning, and mapping tests against real Cassandra.

## 2. Five data representations on the same flow

| Data layer | Example | Cassandra annotations? | Who owns it? |
|---|---|---|---|
| **Transport payload** | JSON bytes/string in JMS/HTTP/Kafka | No | Inbound adapter + message converter |
| **Domain event DTO** | `OrderPaidEvent(eventId, orderId, ...)` | Usually no | Contract validation, normalization |
| **Spring Message** | `Message<OrderPaidEvent>` + headers | No | Channels, transformers, routing, error paths |
| **Persistence entity** | `@Table("order_event") OrderEventRow` | Yes | `MappingCassandraConverter`, repository/template |
| **Cassandra row** | `event_id text`, `occurred_at timestamp` | CQL schema | Cassandra driver/coordinator/replicas |

There is no universal out-of-the-box conversion from **any arbitrary JSON String** into an entity matching a CQL table. Spring Data offers convention-based mapping, yet an integration system dealing with multiple contracts/schema versions should **explicitly declare table names, column names, keys, data types, and validation**.

### 2.1. Inbound and outbound use two meanings of "converter"

On the inbound side, **Spring Messaging/Jackson/message converters** turn JSON/XML/bytes into a Java object matching the business contract. On the outbound side, **Spring Data `CassandraConverter`**, usually `MappingCassandraConverter`, turns an **entity** and its property metadata into CQL values. These are **two distinct layers**.

~~~text
JSON "amountMinor": 150000
   |
   | Jackson / source deserialization
   v
OrderPaidEvent.amountMinor() : long
   |
   | Domain mapper
   v
OrderEventRow.amountMinor() : long
   |
   | MappingCassandraConverter + Java Driver codec
   v
Cassandra amount_minor : bigint
~~~

A `RowMapper` from Spring Data CQL works in the reverse direction: **Cassandra Row → Java object**, when querying manually with `CqlTemplate`/`ReactiveCqlTemplate`. It is not a component that converts inbound JSON into a row.

## 3. Designing a CQL schema tied to the business contract

Examples use Java 17+, compatible Spring Data Cassandra 4.x/5.x, Spring Integration 6.x/7.x, and a test Cassandra cluster with keyspace `shop_integration` already provisioned.

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    schema_version int,
    occurred_at timestamp,
    amount_minor bigint,
    currency text,
    payload_json text
);
~~~

**Why use `event_id` as the primary key?** This lesson illustrates looking up a single event by `eventId` and avoiding duplicate rows when a broker redelivers the exact same event. If you need order-history queries by `orderId`, design a **separate table** with suitable partition/clustering keys instead of scanning all of `order_event` and filtering by `order_id`.

A valid JSON input:

~~~json
{
  "eventId": "evt-8001",
  "orderId": "ORD-8001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-23T03:00:00Z",
  "amountMinor": 150000,
  "currency": "VND"
}
~~~

Field alignment:

| JSON/domain field | Java type | Cassandra column/type | Rule |
|---|---|---|---|
| `eventId` | `String` | `event_id text PRIMARY KEY` | Non-blank, stable across retries |
| `orderId` | `String` | `order_id text` | Non-blank, matches tenant/authorization context |
| `eventType` | `String` | `event_type text` | Allowlist of supported event types |
| `schemaVersion` | `int` | `schema_version int` | Serializer version; accept only supported versions |
| `occurredAt` | `Instant` | `occurred_at timestamp` | UTC semantics, millisecond precision |
| `amountMinor` | `long` | `amount_minor bigint` | Smallest currency unit, never floating point |
| `currency` | `String` | `currency text` | Validated currency code |
| Full raw/canonical payload | `String` | `payload_json text` | Controlled audit/troubleshooting; never store secrets |

**Cassandra does not auto-generate IDs like SQL auto-increment.** Mapped entities must already carry their primary key when calling `insert`. Use the business event's `eventId` rather than generating a fresh UUID whenever a consumer re-receives a message.

### 3.1. Decoupling the API contract from table layout

Producers do not need to know Cassandra table names. For instance, an HTTP request carries `amountMinor`, while Cassandra stores `amount_minor`. Mapping belongs to the **consumer/adapter application**, rather than forcing producers to reshape JSON property names around storage layout.

Conversely, if the Cassandra schema changes from `amount_minor bigint` to `amount_decimal decimal`, you cannot expect `MappingCassandraConverter` to guess currency scaling rules automatically. Migrations and versioned mappers are required.

## 4. Declaring the DTO and entity separately

### 4.1. Business event DTO

~~~java
import java.time.Instant;

public record OrderPaidEvent(
        String eventId,
        String orderId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        long amountMinor,
        String currency) {
}
~~~

This DTO **carries no `@Table`** because it describes the event contract, not the database schema. For JSON deserialization, configure Jackson/Spring Boot appropriately for Java records, `Instant`, and timezones.

### 4.2. Entity mapped to the CQL table

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEventRow(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("schema_version") int schemaVersion,
        @Column("occurred_at") Instant occurredAt,
        @Column("amount_minor") long amountMinor,
        @Column("currency") String currency,
        @Column("payload_json") String payloadJson) {
}
~~~

We annotate **every regular field with `@Column`** to eliminate reliance on naming conventions or differing `NamingStrategy` behavior across project versions. Modern Spring Data Cassandra supports immutable domain objects/records, though very old versions should be checked for constructor-binding support.

**Never import `@Id` or `@PrimaryKey` from JPA without checking.** Import the Spring Data Cassandra package. Cassandra's `@Table` is likewise not `jakarta.persistence.Table`.

### 4.3. Two models evolving independently

~~~mermaid
flowchart TD
    C["OrderPaidEvent - business contract"] --> M["OrderPaidToRowMapper"]
    M --> E["OrderEventRow - persistence model"]
    E --> MC["MappingCassandraConverter"]
    MC --> R[("Cassandra order_event row")]
    SC["CQL schema migration"] --> R
    V["Event schema version"] --> C
    N["Table/column naming rules"] --> E
~~~

Separating domain DTOs from persistence entities helps you:

- Avoid breaking Kafka/JMS schemas on every Cassandra migration.
- Persist **only** intended data, avoiding accidental storage of auth tokens, headers, or transient fields.
- Write clean unit mapping tests and round-trip integration tests.
- Centralize normalization such as timestamp precision, currency allowlists, and JSON canonicalization.
- Evolve table layouts or bucketing without forcing every producer to update in lockstep.

## 5. Writing the mapper: validate → normalize → serialize → build row

This is the layer most often skipped. Entity annotations only specify **which column receives which field**; annotations do not verify payload versions, tenant permissions, or whether an `OrderPaid` event with `amountMinor=-100` is valid.

### 5.1. Complete mapper with Jackson

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public final class OrderPaidToRowMapper {

    private static final Set<String> CURRENCIES =
            Set.of("VND", "USD");

    private final ObjectMapper objectMapper;

    public OrderPaidToRowMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderEventRow map(OrderPaidEvent event) {
        validate(event);

        // CQL timestamp uses millisecond precision.
        Instant canonicalTime =
                event.occurredAt().truncatedTo(ChronoUnit.MILLIS);

        OrderPaidEvent canonical = new OrderPaidEvent(
                event.eventId(),
                event.orderId(),
                event.eventType(),
                event.schemaVersion(),
                canonicalTime,
                event.amountMinor(),
                event.currency());

        final String json;
        try {
            json = objectMapper.writeValueAsString(canonical);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Failed to serialize OrderPaidEvent", ex);
        }

        if (json.getBytes(StandardCharsets.UTF_8).length > 64 * 1024) {
            throw new IllegalArgumentException("Payload exceeds lab limit");
        }

        return new OrderEventRow(
                canonical.eventId(),
                canonical.orderId(),
                canonical.eventType(),
                canonical.schemaVersion(),
                canonical.occurredAt(),
                canonical.amountMinor(),
                canonical.currency(),
                json);
    }

    private static void validate(OrderPaidEvent event) {
        if (event == null
                || event.eventId() == null || event.eventId().isBlank()
                || event.orderId() == null || event.orderId().isBlank()
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "Missing eventId, orderId, or occurredAt");
        }
        if (!"OrderPaid".equals(event.eventType())
                || event.schemaVersion() != 1
                || event.amountMinor() <= 0
                || event.currency() == null
                || !CURRENCIES.contains(event.currency())) {
            throw new IllegalArgumentException(
                    "OrderPaidEvent does not match schema version 1 contract");
        }
    }
}
~~~

This example uses the **Jackson 2 API** (`com.fasterxml.jackson.databind.ObjectMapper`) common in Spring Boot 3.x apps. On Spring Framework 7 / Spring Boot 4 with Jackson 3, serialization imports/APIs differ; use the mapper configured for your framework version rather than copying old namespaces. For `Instant`, configure Java Time support, UTC serialization, and consistent formatting.

**The 64 KiB cap is illustrative only**, not a Cassandra hard limit. Production must enforce payload limits aligned with actual row/partition sizing and avoid persisting entire sensitive objects solely for debugging.

### 5.2. Why normalize timestamp precision?

CQL `timestamp` stores timestamps at **millisecond precision**. `java.time.Instant` can carry nanoseconds; if an app uses timestamp inside a clustering key and compares Java objects against read-back rows, precision mismatch causes subtle bugs. Canonicalize precision before building keys or rows.

~~~text
Input Instant:    2026-11-23T03:00:00.123456789Z
Canonical value:  2026-11-23T03:00:00.123Z
CQL timestamp:    2026-11-23T03:00:00.123Z
~~~

Never use `LocalDateTime.now()` or the JVM default timezone to "fill in" a missing event timestamp. A retry minutes later would generate different data; if the timestamp is part of the primary key, that spawns a brand-new business row.

### 5.3. One business event, multiple storage models

For example, `OrderPaidEvent` might be:

- Stored as a row in `order_event` keyed by `event_id` for fast lookup.
- Stored in a timeline table keyed by `(tenant_id, order_id, month)` for history queries.
- Fed into a current-state projection guarded by version checks.

Three storage targets can use three entity/mapping classes. **Never force one entity to carry every partitioning scheme** and rely on a primary key incapable of serving every query.

### 5.4. What happens when deserialization already failed?

If incoming JSON has syntax errors, misses a non-nullable field, or has an unparseable `Instant`, the mapper is **never reached**. Failure occurs at the **deserialize/contract** layer; retrying identical raw bytes will never succeed. Route "poison messages" to quarantine or a DLQ instead of hot-retrying and clogging the source.

## 6. Spring Integration Java DSL: transforming DTOs into Cassandra entities

Spring Integration uses a `Transformer` to convert a Spring Message payload from one Java type to another, typically preserving headers per framework messaging rules. Place the transform **before** `CassandraMessageHandler`.

### 6.1. Illustrative dependencies

When using Spring Boot BOM to manage compatible versions:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
~~~

Depending on the source, you may also need `spring-integration-jms`, `spring-integration-kafka`, `spring-integration-http`, or matching adapters; this lesson assumes **messages already arrive on a channel**. Do not add every adapter starter randomly just to run a Cassandra flow.

Example `application.yml` for the **lab application**, not a lesson metadata YAML file:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

Local DC must match real Cassandra metadata; tables/keyspaces must be provisioned via migrations or lab setup.

### 6.2. Flow for payloads already deserialized to OrderPaidEvent

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class OrderPaidCassandraFlowConfig {

    @Bean
    public IntegrationFlow orderPaidToCassandra(
            OrderPaidToRowMapper mapper,
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("validatedOrderPaidEvents")
                .transform(OrderPaidEvent.class, mapper::map)
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Contract:

- `validatedOrderPaidEvents` accepts **`Message<OrderPaidEvent>`**, not raw JSON text.
- The transformer converts **`OrderPaidEvent` into an `@Table`-annotated `OrderEventRow`**.
- The Cassandra outbound adapter with `Type.INSERT` invokes `ReactiveCassandraOperations`, using `MappingCassandraConverter` to map entity fields into CQL columns.
- `endpoint.async(false)` makes the endpoint await the operation synchronously before returning; helpful for tests and JMS error propagation, though it **blocks the thread**.
- The adapter is **one-way**; it emits no business reply to callers.

With the default `async(true)`, Cassandra writes can finish **after** upstream `send()` returns. That affects JMS/Kafka source acknowledgment, not merely throughput.

### 6.3. If the input is still a JSON String

Create a dedicated decoder class. With Spring Boot 3 / Jackson 2:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidJsonDecoder {

    private final ObjectMapper objectMapper;

    public OrderPaidJsonDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public OrderPaidEvent decode(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("Empty JSON input");
        }
        try {
            return objectMapper.readValue(json, OrderPaidEvent.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Invalid OrderPaid JSON", ex);
        }
    }
}
~~~

Two-step transform flow:

~~~java
@Bean
public IntegrationFlow rawJsonOrderPaidToCassandra(
        OrderPaidJsonDecoder decoder,
        OrderPaidToRowMapper mapper,
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("rawOrderPaidJson")
            .transform(String.class, decoder::decode)
            .transform(OrderPaidEvent.class, mapper::map)
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

This is an **alternative flow** to section 6.2 when sources deliver JSON Strings. Do not register two endpoints on the same input channel in one lab expecting each message to persist once. If the inbound HTTP/JMS/Kafka adapter already converts JSON to a DTO, **skip the decoder** and use the flow in section 6.2.

### 6.4. Sending messages matching the contract

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderPaidPublisher {

    private final MessageChannel channel;

    public OrderPaidPublisher(
            @Qualifier("validatedOrderPaidEvents") MessageChannel channel) {
        this.channel = channel;
    }

    public void publish(OrderPaidEvent event) {
        boolean accepted = channel.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", event.eventId())
                        .setHeader("sourceSystem", "payment-service")
                        .build());
        if (!accepted) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

The `eventId` header aids tracing/routing, while the **entity primary key** is still drawn by the mapper from `event.eventId()`. If a source supplies headers conflicting with the payload, enforce validation policies; never let untrusted headers overwrite a business ID.

**Do not interpret `send(true)` as "Cassandra write committed" in every setup.** With async channels or handlers, the boolean reflects channel handoff semantics only.

## 7. Mapping the read path: Cassandra row → entity → response DTO

Bidirectional mapping does not have to be completely symmetrical. A row may lack a regular column due to schema migrations or historical data; a response DTO may hide sensitive fields; an older event schema version may need upcasting before returning over an API.

### 7.1. ReactiveCassandraOperations.selectOneById

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class OrderEventReader {

    private final ReactiveCassandraOperations operations;

    public OrderEventReader(ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<OrderEventRow> findRow(String eventId) {
        if (eventId == null || eventId.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "eventId is required"));
        }
        return operations.selectOneById(eventId, OrderEventRow.class);
    }
}
~~~

`selectOneById` returns **`Mono<OrderEventRow>` or `Mono.empty()`** if no row matches. `MappingCassandraConverter` maps CQL columns into record constructor parameters. **Never mistake `Mono.empty()` for a Cassandra connection failure**; it can simply mean a legitimate "not found".

### 7.2. Creating a separate read DTO to avoid leaking stored payloads

~~~java
import java.time.Instant;

public record OrderEventView(
        String eventId,
        String orderId,
        String eventType,
        Instant occurredAt,
        long amountMinor,
        String currency) {
}
~~~

~~~java
public Mono<OrderEventView> findView(String eventId) {
    return operations.selectOneById(eventId, OrderEventRow.class)
            .map(row -> new OrderEventView(
                    row.eventId(),
                    row.orderId(),
                    row.eventType(),
                    row.occurredAt(),
                    row.amountMinor(),
                    row.currency()));
}
~~~

This is a method fragment in a service with an injected `operations`. `OrderEventView` **omits `payloadJson`**, keeping full stored payloads hidden from HTTP/API clients.

### 7.3. When "not found" needs explicit meaning

~~~java
return operations.selectOneById(eventId, OrderEventRow.class)
        .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Event does not exist")));
~~~

This is a fragment, not an optimal production API error mapping. The HTTP layer should map "not found" to 404 via domain exceptions/handlers, while classifying Cassandra connection timeouts separately rather than turning them into 404s. Never swallow `DataAccessException` and return `Mono.empty()` for all errors.

### 7.4. Projections and queried columns

If clients only need `eventId`, `eventType`, and `occurredAt`, avoid `SELECT *` or fetching large JSON payloads needlessly. Spring Data Cassandra supports projections/`as(...)` on the fluent template API (subject to version mapping/limits), or selecting explicit CQL columns and mapping a DTO via `RowMapper`.

In Cassandra, `SELECT` must still match the **partition key and query pattern**; selecting fewer columns will not turn a query missing a partition key into an efficient query.

## 8. Composite primary key: mapping payloads for a timeline table

An `event_id PRIMARY KEY` schema fits ID lookups. When the use case needs order history, add a table such as:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.events_by_order_month (
    tenant_id text,
    order_id text,
    bucket_month text,
    occurred_at timestamp,
    event_id text,
    event_type text,
    payload_json text,
    PRIMARY KEY (
        (tenant_id, order_id, bucket_month),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Here `tenant_id + order_id + bucket_month` form the **Cassandra partition key**; `occurred_at` and `event_id` are clustering columns. A simple `@PrimaryKey("event_id")` is **no longer sufficient**.

### 8.1. Key class

~~~java
import java.io.Serializable;
import java.time.Instant;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public record OrderTimelineKey(
        @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                type = PrimaryKeyType.PARTITIONED)
        String tenantId,

        @PrimaryKeyColumn(name = "order_id", ordinal = 1,
                type = PrimaryKeyType.PARTITIONED)
        String orderId,

        @PrimaryKeyColumn(name = "bucket_month", ordinal = 2,
                type = PrimaryKeyType.PARTITIONED)
        String bucketMonth,

        @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
                type = PrimaryKeyType.CLUSTERED,
                ordering = Ordering.DESCENDING)
        Instant occurredAt,

        @PrimaryKeyColumn(name = "event_id", ordinal = 4,
                type = PrimaryKeyType.CLUSTERED,
                ordering = Ordering.ASCENDING)
        String eventId
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Records provide value-based `equals/hashCode` and a full constructor. Spring Data Cassandra documentation requires composite keys to provide **value-equality semantics** matching database key equality. If an older Spring Data version lacks expected support for record keys, write a `@PrimaryKeyClass` class with getters/setters, a no-arg constructor, and `equals/hashCode`, then verify mapping via tests.

### 8.2. Timeline entity

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_order_month")
public record OrderTimelineRow(
        @PrimaryKey OrderTimelineKey key,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

### 8.3. Mapper must derive the bucket from event timestamp

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public final class TimelineRowMapper {

    private static final DateTimeFormatter MONTH =
            DateTimeFormatter.ofPattern("uuuu-MM");

    private TimelineRowMapper() {}

    public static OrderTimelineRow map(
            String authenticatedTenantId,
            OrderEventRow event) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || event == null
                || event.occurredAt() == null) {
            throw new IllegalArgumentException(
                    "Missing tenant or event timestamp");
        }

        Instant time = event.occurredAt()
                .truncatedTo(ChronoUnit.MILLIS);
        String month = MONTH.format(time.atOffset(ZoneOffset.UTC));

        OrderTimelineKey key = new OrderTimelineKey(
                authenticatedTenantId, event.orderId(), month,
                time, event.eventId());
        return new OrderTimelineRow(
                key, event.eventType(), event.payloadJson());
    }
}
~~~

This mapper uses `authenticatedTenantId` verified by the application from **source identity/context**, never an unverified HTTP client header. In multi-tenant systems, partition-key mapping is part of the **security boundary**.

### 8.4. Why not use processing date for the bucket?

~~~text
Event occurred:           2026-11-30T23:59:59Z
Consumer processed:       2026-12-01T00:00:05Z
Consumer replayed:        2027-01-15T10:00:00Z

Bucket from UTC occurredAt: 2026-11 in all three runs.
Bucket from LocalDate.now:  2026-12 or 2027-01 (WRONG).
~~~

If an event is redelivered with the same `eventId` yet a **different bucket**, it writes a row into a **different partition**. That creates a duplicate business event from unchanged input. Share the **exact same timezone, precision, key schema, and hashing rules** across all producers, consumers, and backfills.

### 8.5. Queries must supply the full partition key

~~~sql
SELECT event_id, occurred_at, event_type
FROM shop_integration.events_by_order_month
WHERE tenant_id = 'tenant-42'
  AND order_id = 'ORD-8001'
  AND bucket_month = '2026-11'
LIMIT 50;
~~~

Filtering solely by `WHERE tenant_id = ?` on this composite partition key does not identify a Cassandra partition. Do not patch it with `ALLOW FILTERING` as a default query pattern; design a separate table if querying by tenant without order/month is needed.

## 9. Mapping Java types to CQL types

Spring Data Cassandra combines the **driver `CodecRegistry`** with Spring converters to map property values. For complex structures, verify that Java types and CQL types match properly; matching field names alone **is not enough**.

| Cassandra type | Recommended Java type | Notes |
|---|---|---|
| `text`/`varchar` | `String` | Length/payload validated in application |
| `int` | `int`, `Integer` | Check range and overflow when parsing JSON |
| `bigint` | `long`, `Long` | Suitable for minor currency units within range |
| `decimal` | `BigDecimal` | Scale/rounding rules must belong to the contract |
| `boolean` | `boolean`, `Boolean` | Null/missing differs from `false` in partial updates |
| `uuid` | `java.util.UUID` | Never mint a new UUID when retrying an existing event |
| `timestamp` | `java.time.Instant` | UTC semantics; CQL stores milliseconds |
| `date` | `java.time.LocalDate` | Date-only with no timezone |
| `blob` | `java.nio.ByteBuffer` | Does not automatically serialize arbitrary Java Objects |
| `list<text>` | `List<String>` | Cap list length/item sizes |
| `set<text>` | `Set<String>` | No logical ordering like `List` |
| `map<text,int>` | `Map<String,Integer>` | Generic type metadata must match codecs |
| `frozen<UDT>` | `@UserDefinedType` or driver `UdtValue` | Use only when schema/model truly fits |

### 9.1. Avoid `double` for monetary amounts

~~~java
public record PaymentAmount(long amountMinor, String currency) {}
~~~

For `VND`, `amountMinor=150000` represents 150,000 minor units per contract. For currencies with fractional units, define scaling and rounding explicitly; **never use `double` for exact monetary math** simply because CQL supports `double`.

### 9.2. Nullable regular fields

With a Java record:

~~~java
@Column("payload_json") String payloadJson
~~~

When `payloadJson` is null, Spring Data `INSERT` normally **omits null fields from the mutation** (see Spring Data template docs). **`UPDATE`** and partial updates can behave differently: CQL `NULL` typically creates a tombstone/deletes the prior value, whereas driver `UNSET` skips that field. Never assume "JSON omitted field" equals "delete column" (or vice versa) without verifying your API/mapper strategy.

For incoming `PATCH` events, prefer a DTO that **distinguishes missing vs explicit null** paired with intentional update operations, instead of mapping a sparsely populated object with nulls and calling `update(entity)` hoping it behaves as a partial patch.

### 9.3. Collections, UDTs, and nested JSON

Two common approaches:

- **Typed CQL columns:** use `list`/`set`/`map`/`@UserDefinedType` for structured data that needs stable querying/reading.
- **A `payload_json text` column:** stores canonical JSON for auditing/schema compatibility; serialized/deserialized in the app, accepting that its internals are not arbitrarily queryable like relational columns.

Never construct a `Map<String,Object>` holding arbitrary Java types expecting the driver to guess codecs for nested objects. Specifically, **Cassandra JSON syntax** and a **JSON String inside a `text` column** are two different things: `INSERT ... JSON '...'` is a separate CQL feature, not the default behavior of `CassandraMessageHandler.Type.INSERT`.

## 10. Mapping annotations: declare explicitly, never guess from field names

| Annotation | Where used? | Effect |
|---|---|---|
| `@Table("order_event")` | Entity class/record | Selects the CQL table |
| `@PrimaryKey("event_id")` | Entity field/record component | Marks a single primary key, or field holding a composite key class |
| `@PrimaryKeyClass` | Composite key class | Describes multiple PK columns |
| `@PrimaryKeyColumn` | Key component / flat entity key field | Partitioned/clustered, `ordinal`, `ordering` |
| `@Column("amount_minor")` | Regular entity property | Maps Java property to exact CQL column |
| `@Transient` | Entity field | Excludes field from persistence |
| `@CassandraType` | Field/property | Specifies CQL type when auto-mapping isn't enough |
| `@UserDefinedType` | UDT value class | Maps a Cassandra UDT |
| `@Embedded` | Embedded value class | Flattens properties per mapping rules |
| `@Version` | Entity field | Optimistic locking per Spring Data Cassandra rules |

### 10.1. `@Transient` prevents persisting non-Cassandra fields

~~~java
import org.springframework.data.annotation.Transient;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("demo_event")
public class DemoEvent {

    @PrimaryKey("event_id")
    private String eventId;

    private String eventType;

    @Transient
    private String processingTraceId; // Application-only field

    public DemoEvent() {}

    // Getters/setters for fields omitted for brevity.
}
~~~

Because unannotated fields may be mapped by convention in Spring Data, adding `processingTraceId` to an entity and assuming it won't be persisted is risky. `@Transient` states intent explicitly. With immutable objects/constructor binding, avoid mandatory transient constructor parameters that the mapper cannot materialize from a row.

### 10.2. `@Version` does not replace `eventId` idempotency

Spring Data Cassandra supports `@Version` for optimistic locking when saving versioned entities. However:

- It tracks the **persistence entity's** version per Spring Data rules, not the JSON `schemaVersion`.
- It does not tie into broker offsets or JMS sequences.
- It does not provide cross-table or cross-partition transactions.
- Under concurrent writers, verify actual mapping/version handling/LWT behavior in your exact Spring Data version.

**Never reuse one `schemaVersion` field for both serializer selection and optimistic locking without an explicit contract.**

### 10.3. NamingStrategy and migrations

If `@Column` is omitted, Spring Data falls back to the Java property name and `NamingStrategy`. Conventions like snake_case are convenient, yet if one service maps `orderId` → `order_id` while another keeps `orderId`, subtle mismatches arise.

For integration events and shared tables across services, **explicit column names** paired with schema integration tests are far more maintainable. When renaming columns, use migrations/backfills with compatibility windows; never change an annotation in one deploy expecting legacy data to transform automatically.

## 11. Custom conversions: when a Java value object is not a native CQL type

`MappingCassandraConverter` can use Spring `Converter<S,T>` instances **explicitly registered** via `CassandraCustomConversions`. It does not auto-scan every converter on the classpath, avoiding unintended side effects on other type mappings.

### 11.1. Value object example

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid EmailAddress");
        }
    }
}
~~~

Suppose a schema stores emails as CQL `text`, while the domain model uses `EmailAddress`. You can declare converters:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class EmailToString
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}

@ReadingConverter
public final class StringToEmail
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

`@WritingConverter` specifies Java domain type → CQL-compatible value; `@ReadingConverter` specifies DB value → domain type. For primitive/basic types where converters could be ambiguous (e.g., `String`→`Long`), direction annotations are essential.

### 11.2. Registering converters properly

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.config.AbstractCassandraConfiguration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration
public class CassandraMappingConfig
        extends AbstractCassandraConfiguration {

    @Override
    protected String getKeyspaceName() {
        return "shop_integration";
    }

    @Override
    public CassandraCustomConversions customConversions() {
        return CassandraCustomConversions.create(config -> {
            config.registerConverter(new EmailToString());
            config.registerConverter(new StringToEmail());
        });
    }
}
~~~

This is an **alternative configuration approach** when the application explicitly owns Spring Data Cassandra Java config. If Spring Boot auto-configures templates and sessions, avoid introducing `AbstractCassandraConfiguration` accidentally and creating **duplicate beans/session factories**; plug custom conversions into your active project config.

### 11.3. Property-level converters

A global `String → EmailAddress` converter can affect every matching property discovered by mapping. When only a single field needs special formatting, Spring Data Cassandra offers **property-based converters** registered via `CassandraCustomConversions.create(...)` and `configurePropertyConversions(...)`.

Choose one:

- **Global type converter:** stable semantic meaning across many entities.
- **Property-specific converter:** only one column/field requires custom encoding, encryption, or normalization.

For encryption, never roll custom crypto inside a mapper and serialize secrets as plain text; use dedicated key-management/encryption designs and test reading old records after key rotation.

### 11.4. When to use custom converters?

| Need | Suitable approach |
|---|---|
 JSON body → `OrderPaidEvent` | Inbound JSON decoder/message converter |
 `OrderPaidEvent` → `OrderEventRow` | Domain `Transformer`/mapper |
 `EmailAddress` → Cassandra `text` | Spring Data custom conversion if entities use the value object |
 CQL `Row` → read DTO | `CqlTemplate` `RowMapper` or entity mapping + DTO mapper |
 Driver-supported `UUID`/`Instant` | Native codec; avoid writing redundant converters |
 Individually encrypted property | Property converter + security design |

**Do not confuse similar names:** a Spring Integration `Transformer` operates in the integration flow, whereas a Spring Data `Converter` operates in persistence mapping metadata. They live at different layers and are tested differently.

## 12. Manual mapping with CqlTemplate and RowMapper

Sometimes an app only reads a few columns, or uses queries/DTOs that do not align with a `@Table` entity. `CqlTemplate`/`ReactiveCqlTemplate` supports **`RowMapper`** to turn a CQL `Row` into a Java result.

### 12.1. Imperative RowMapper

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.stereotype.Repository;

@Repository
public final class EventSummaryDao {

    private final CqlOperations cql;

    public EventSummaryDao(CqlOperations cql) {
        this.cql = cql;
    }

    public List<EventSummary> findById(String eventId) {
        return cql.query(
                "SELECT event_id, event_type, occurred_at "
                + "FROM order_event WHERE event_id = ?",
                (row, rowNum) -> new EventSummary(
                        row.getString("event_id"),
                        row.getString("event_type"),
                        row.getInstant("occurred_at")),
                eventId);
    }
}

record EventSummary(
        String eventId, String eventType, Instant occurredAt) {}
~~~

`CqlOperations.query(String, RowMapper<T>, Object... args)` prepares/binds `eventId` and maps each driver `Row` into `EventSummary`. The query targets primary key `event_id`, avoiding `ALLOW FILTERING`. When expecting at most one row, `queryForObject(...)` with a `RowMapper` can be used while checking that overload's empty/exception behavior.

### 12.2. Reactive RowMapper

~~~java
import org.springframework.data.cassandra.core.cql.ReactiveCqlOperations;
import reactor.core.publisher.Flux;

// Fragment in a repository with ReactiveCqlOperations reactiveCql injected.
Flux<EventSummary> summaries = reactiveCql.query(
        "SELECT event_id, event_type, occurred_at "
        + "FROM order_event WHERE event_id = ?",
        (row, rowNum) -> new EventSummary(
                row.getString("event_id"),
                row.getString("event_type"),
                row.getInstant("occurred_at")),
        eventId);
~~~

`ReactiveCqlOperations` returns `Flux<T>`/`Mono<T>`; **without a subscription, I/O does not run**. Never call `collectList()` on an unbounded query lacking a partition predicate assuming memory is safe.

### 12.3. Entity mapping vs RowMapper

| Criterion | `MappingCassandraConverter` + entity | Manual `RowMapper` |
|---|---|---|
| Table/column metadata | `@Table`, `@Column`, `@PrimaryKey` | Getter code on driver `Row` |
| Works with template `insert` | Yes | Not automatically |
| Mapping records/domain objects | Automatic from metadata | Construct object manually |
| Reading a few columns outside full entity | Projection API available | Explicit and simple |
| Custom type conversion | `CassandraCustomConversions` | Convert manually or via codec |
| Schema migrations | Annotation/constructor compatibility | Getter names/types must be updated |
| Spring Integration `Type.INSERT` | Payload must be an entity | Does not use `RowMapper` |

Never pass a `RowMapper` into `CassandraMessageHandler.Type.INSERT` expecting it to map JSON to database rows; that endpoint does not follow such a contract. `RowMapper` is for **read mapping**, whereas write mapping uses entities or statements.

## 13. Three ways to feed payloads to CassandraMessageHandler

Spring Integration Cassandra (since **6.0**) provides `CassandraMessageHandler` backed by **`ReactiveCassandraOperations`**. The handler supports `INSERT`, `UPDATE`, `DELETE`, and `STATEMENT` modes, defaults to **asynchronous**, and can serve as a one-way outbound adapter or a replying outbound gateway.

### 13.1. Choosing the right input contract

| Mode/setting | Input Spring Message payload | Who performs mapping? | When to use? |
|---|---|---|---|
| `Type.INSERT` / `Type.UPDATE` / `Type.DELETE` | A `@Table` entity | Spring Data Cassandra converter | Domain-driven persistence |
| Entity mode with `List<entity>` | List of mapped entities | Spring Data batch operations | Deliberately grouped mutations |
| `ingestQuery(...)` | `List<List<?>>`, each inner list matching `?` positions | App builds matrix; handler binds CQL values | Ingesting rows with a fixed query shape |
| `query(...).parameter(...)` | Payload/headers providing bind values | Parameter expressions + driver | `SELECT`/`STATEMENT` with named markers |
| `statementFunction(...)` | DTO or any message | App constructs `Statement<?>` from message | Need direct control over CQL, values, and options |

Never select `Type.INSERT` and push a JSON `String` expecting Spring Data to infer table/column names. Transform inputs into a **mapped entity** or pick the matching CQL mode.

### 13.2. Path 1 — Entity

~~~text
Message<OrderPaidEvent>
    -> .transform(mapper::map)
Message<OrderEventRow @Table>
    -> Cassandra.outboundChannelAdapter(Type.INSERT)
    -> ReactiveCassandraOperations
    -> MappingCassandraConverter
    -> CQL INSERT
~~~

This is the **easiest default path to maintain** when domain DTOs and entity mappings are stable. `WriteOptions`/`InsertOptions` can add consistency, TTL, timeouts, and operation behavior when configured at the right layer/version.

### 13.3. Path 2 — Ingest query with `List<List<?>>`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow ingestOrderEventRows(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("orderEventMatrixInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(
                            "INSERT INTO order_event "
                            + "(event_id, order_id, event_type, "
                            + "schema_version, occurred_at, amount_minor, "
                            + "currency, payload_json) "
                            + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Constructing a value matrix:

~~~java
import java.util.List;

// row is a validated and normalized OrderEventRow.
List<List<Object>> matrix = List.of(
        List.<Object>of(
                row.eventId(),
                row.orderId(),
                row.eventType(),
                row.schemaVersion(),
                row.occurredAt(),
                row.amountMinor(),
                row.currency(),
                row.payloadJson())
);
~~~

Then send `Message<List<List<Object>>>` to `orderEventMatrixInput`. Each inner list must carry **exactly eight values matching the eight `?` markers**. `List.of(...)` rejects nulls; if nullable columns exist, define the collection/contract and `null`/`UNSET` binding explicitly.

**Do not confuse `List<OrderEventRow>` with `List<List<?>>`.** The two payload shapes trigger **entity batching** vs **ingest query** respectively. Both can issue multiple Cassandra mutations, yet batch type, retry, and partition semantics must be evaluated separately.

### 13.4. Path 3 — `statementFunction` building a CQL statement

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow explicitOrderEventStatementFlow(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("orderEventStatementInput")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEventRow row =
                                (OrderEventRow) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, "
                                + "schema_version, occurred_at, amount_minor, "
                                + "currency, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                row.eventId(),
                                row.orderId(),
                                row.eventType(),
                                row.schemaVersion(),
                                row.occurredAt(),
                                row.amountMinor(),
                                row.currency(),
                                row.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, values...)` keeps values **separate from CQL syntax**. When prepared-query reuse is required, call `CqlSession.prepare(...)` and bind a `BoundStatement` inside a managed DAO/helper; never concatenate JSON values into CQL strings.

**`STATEMENT` mode bypasses entity-to-column mapping for manually built statements:** you own column order, types, null semantics, and key fields. Do not pick it merely to avoid `@Table` if domain mapping already fits.

### 13.5. When you just want SELECT with a reply

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow readEventGateway(
        ReactiveCassandraOperations operations) {
    return IntegrationFlow.from("readEventRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT event_id, order_id, event_type "
                           + "FROM order_event WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel(c -> c.flux("readEventResults"))
            .get();
}
~~~

`:eventId` is the **CQL named marker**; `"payload"` is **Spring Expression Language** reading the input Spring Message. The gateway produces a reply; handle the `STATEMENT` output according to the actual reply/publisher type of your Spring Integration/Spring Data version—**never assume it always returns `OrderEventRow`** the way `ReactiveCassandraOperations.selectOneById(...)` does.

If you need a cleanly mapped response DTO, a **service activator** calling `ReactiveCassandraOperations` followed by `.map(row -> dto)` (section 7) gives full contract control.

### 13.6. Adapters and gateways are not interchangeable

| Intent | Approach |
|---|---|
 One-way write ending at Cassandra | Outbound channel adapter + error/ack policy |
 `SELECT` returning results to requestor | Outbound gateway or replying service activator |
 LWT needing `[applied]` inspection | Driver/gateway/operations with access to conditional results |
 Converting JSON → entity | Transformer before handler, not CQL `RowMapper` |
 Using a DTO without `@Table` | CQL statement or inbound transformer; never push straight into entity mode |

A **one-way adapter** will not emit a Spring reply containing a row simply because the input message carries a `replyChannel` header. For request-reply, choose an endpoint and channel with **reply semantics**.

## 14. Handling multi-element payloads, batches, and partial failures

If the input carries `List<OrderPaidEvent>`, a clean design is:

~~~text
Message<List<OrderPaidEvent>>
 -> validate each event + batch-size/bytes + partition boundaries
 -> map each OrderPaidEvent to OrderEventRow
 -> Message<List<OrderEventRow>>
 -> Cassandra Type.INSERT (batch operation)
~~~

### 14.1. List mapping example

~~~java
import java.util.List;

public List<OrderEventRow> mapBatch(List<OrderPaidEvent> events) {
    if (events == null || events.isEmpty() || events.size() > 10) {
        throw new IllegalArgumentException("Lab batch requires 1..10 events");
    }
    return events.stream()
            .map(mapper::map)
            .toList();
}
~~~

This is a method fragment inside a component holding `OrderPaidToRowMapper mapper`. It can be wired via `.transform(List.class, ...)` with type checks. **Never blindly cast a list of JSON Strings to `List<OrderPaidEvent>`**: Java generics undergo type erasure; deserialize and validate every element.

### 14.2. A Spring list is not an atomic SQL transaction

When the Cassandra handler executes an entity batch, Cassandra enforces **`LOGGED`/`UNLOGGED`/`COUNTER` semantics** and partition constraints. Multi-partition batches offer no SQL-style snapshot isolation; one invalid event can fail the whole batch, and mid-flight network/coordinator errors leave uncertain partial outcomes.

Use batches intentionally, bounding:

- **Item count, serialized bytes**, and distinct Cassandra partition keys.
- Idempotency of every individual mutation.
- When to fail the whole batch vs split/quarantine individual items.
- The right batch type (small logged batches for related mutations; unlogged or bounded independent async writes elsewhere).
- Retry budgets when brokers redeliver the entire list.

**Never use a giant CQL batch to boost throughput for thousands of independent events.** Bounded independent asynchronous writes distribute coordinator load far better.

## 15. Schema evolution and contract versioning

When upstream starts emitting v2 events with a `paymentMethod` field, do not just add a property to the record expecting Cassandra to `ALTER TABLE` automatically. Choose deliberately:

1. **Ignore the new field:** if persistence does not need it.
2. **Store inside `payload_json`:** if needed for audit/compatibility without querying.
3. **Add a CQL column and entity field:** migrate the column first, deploy backward-compatible read/write code, and backfill if needed.
4. **Create a new table/projection:** when query patterns or partition keys change.

### 15.1. Compatible rollout sequence

~~~mermaid
flowchart TD
    A["Producer v1 running"] --> B["Migration adds nullable column"]
    B --> C["Consumer understands v1 + v2, versioned mapper"]
    C --> D["Producer rolls out v2 safely"]
    D --> E["Backfill / reconcile legacy data"]
    E --> F["Retire old contract after retention window"]
~~~

Cassandra does not backfill nulls across every legacy row when adding a column. A new `@Column` can read as `null` on historical rows; Java primitives like `int`/`long` cannot represent null, so **use boxed types** when missing columns are valid.

### 15.2. Schema version vs aggregation version

| Field | Meaning |
|---|---|
| `schemaVersion` | JSON/event format version |
| `aggregateVersion` | Business state transition sequence of an order |
| Spring Data `@Version` | Optimistic locking on a persistence entity |
| Cassandra write timestamp | Mutation conflict resolution |
| Kafka offset | Record position within a broker partition |

**Do not conflate** these versions. An order at aggregate version 17 can arrive under JSON schema version 2; write timestamps and Kafka offsets remain independent coordinates.

### 15.3. Historical data with mismatched types

If `amountMinor` was historically stored as `text` in an older table while the new app uses `bigint`, Spring Data will not convert arbitrary rows automatically. Migrate the data/table or implement explicit custom conversions with integration tests covering legacy rows and error cases. Never "fix" codec exceptions by catching them and returning zero amounts—that corrupts financial data.

## 16. Error handling: where should each layer's errors go?

An integration flow can fail during **deserialization**, **validation**, **domain mapping**, **Spring Data conversion**, **driver codecs/CQL**, or **Cassandra network/storage**. Proper classification prevents retrying **unrecoverable errors** and reduces premature source acknowledgments.

| Layer | Example error | Handling strategy |
|---|---|---|
| JSON deserialization | Missing brace, malformed `Instant` | Quarantine/DLQ; fix producer contract |
| Domain validation | Blank `eventId`, `amountMinor <= 0` | Fail fast; do not call Cassandra |
| Domain mapper | Canonical JSON serialization failure, invalid bucket/tenant | Classify as permanent error; fix mapping |
| Spring Data converter | Missing `@Table`/`@PrimaryKey` metadata, record constructor mismatch | Fix entity/schema/config |
| Driver codec | Java type vs CQL type mismatch, unsupported UDT | Fix schema/type/codec |
| Invalid CQL/schema | Missing table/column, wrong keyspace | Fix migration/config; retrying unchanged is futile |
| Auth/permissions | Cassandra role lacks privileges | Fix ACLs/secrets; do not hot-retry |
| Timeout/unavailable | Cluster overload, network glitch, slow replica | Bounded retry if idempotent; backoff/reconcile |
| Conditional result | `IF NOT EXISTS` returns `applied=false` | Separate benign duplicates from business conflicts |

**Data conversion errors differ from Cassandra cluster outages.** If a poisoned event keeps arriving with identical bad JSON, scaling Kafka consumers or JMS redeliveries will never repair it. Enforce separate retry/quota rules for permanent contract failures.

### 16.1. Spring Integration error channel

In Spring Integration, `errorChannel` receives `ErrorMessage` instances from endpoints and async paths. Still, it is a **Spring `MessageChannel`**, not automatically:

- A JMS broker DLQ;
- A Kafka dead-letter topic;
- A Cassandra transaction rollback;
- A durable inbox/outbox;
- A crash-recovery replay mechanism.

If a transacted source listener uses `DirectChannel`, a synchronous transformer/handler exception propagates back to the listener so the broker **can roll back/redeliver per config**. If an error handler swallows the failure and the listener sees success, the broker commits even though Cassandra never wrote.

### 16.2. Sync vs async impact on the source

~~~mermaid
sequenceDiagram
    participant JMS as JMS broker
    participant L as Inbound listener
    participant T as Mapper/Transformer
    participant C as Cassandra handler
    participant DB as Cassandra

    JMS->>L: Deliver evt-8001
    L->>T: Spring Message via DirectChannel
    T->>C: OrderEventRow entity
    C->>DB: INSERT, async=false
    alt Write completed
        DB-->>C: Success
        C-->>L: Handler returns
        L-->>JMS: Commit
    else Conversion/DB error
        C-->>L: Exception propagated
        L-->>JMS: Rollback per policy
    end
    Note over JMS,DB: Cassandra and JMS commits are not atomic
~~~

When using `ExecutorChannel`, an in-memory `QueueChannel`, or the default `async=true` Cassandra handler, **the source callback can finish before Cassandra completes**. Subsequent Cassandra errors **cannot automatically roll back an already-committed JMS message**.

### 16.3. A timeout does not prove Cassandra never wrote

~~~text
INSERT event_id='evt-8001' is applied by replicas.
    -> Response is lost on the network.
    -> Driver reports timeout.
    -> JMS listener rolls back; broker redelivers evt-8001.
    -> Mapper must rebuild the row with the same primary key and values.
~~~

Standard Cassandra `INSERT` uses **upsert semantics**, not an SQL unique insert rejecting duplicates. Retrying the same `eventId` with the same immutable payload makes idempotency manageable. If a retry alters `occurredAt`, `amountMinor`, `payloadJson`, or TTL, the outcome can change; enforce a strict invariant.

### 16.4. Detecting benign duplicates vs conflicting duplicates

Example:

~~~text
First event: eventId=evt-8001, amountMinor=150000
Retry:       eventId=evt-8001, amountMinor=150000
    -> Likely a valid redelivery.

Conflict:    eventId=evt-8001, amountMinor=250000
    -> Must not silently overwrite and claim idempotency.
~~~

If business rules dictate "accept each `eventId` only once", evaluate `INSERT ... IF NOT EXISTS`/LWT or an inbox/claim strategy. When `applied=false`, inspect whether the existing row matches the incoming content. **LWT does not form a distributed transaction with JMS/Kafka**, and claiming in table A before writing timeline table B still requires reconciliation if a crash hits in between.

### 16.5. Multi-layer retry budgets

One event can be retried by:

1. The Cassandra Java Driver retry policy;
2. Application-level Spring Retry/Resilience4j;
3. JMS broker redelivery or Kafka replay;
4. Manual DLQ replays;
5. Reconciliation jobs.

If every layer retries unboundedly, total writes multiply rapidly while Cassandra is overloaded. Bound **attempts, concurrency, backoff, deadlines, and error classification**. Schema-invalid JSON belongs in quarantine, never consuming database retry budgets.

## 17. Data control and security in mapping

### 17.1. Never persist uncontrolled headers or payloads

Spring Message headers may carry:

- JMS/Kafka metadata, correlation IDs, reply channels;
- Credentials/tokens attached by gateways or producers;
- Tracing baggage and internal metadata;
- Untrusted user-supplied tenant headers.

Never serialize `MessageHeaders` into `payload_json` or dump `message.toString()` as an audit record. Persist only **approved allowlisted fields** under PII and retention policies. Logs and traces should likewise avoid raw JSON with sensitive data.

### 17.2. Partition keys as a security boundary

In multi-tenant systems using `tenantId` in the Cassandra partition key, **verify the tenant from authenticated identity**, never trusting a client-supplied `tenantId` in JSON. The mapper should take `verifiedTenantId` from the authorization layer and check it against payload/context as appropriate.

Never pull keyspace, table, or column names from user messages to concatenate CQL:

~~~java
// DO NOT DO THIS: table name chosen by the client.
String unsafe = "INSERT INTO " + message.getHeaders().get("table") + "...";
~~~

Prepared statements only bind **values** in supported CQL positions; they **never** replace allowlists and authorization for database identifiers.

### 17.3. Payload limits and decompression

A Kafka/JMS event may carry huge JSON or deeply nested arrays. Before deserializing and writing to Cassandra:

- Bound raw message byte sizes and JSON nesting depth per parser/codec.
- Cap string lengths, collection item counts, and serialized row sizes.
- Validate charset/encoding on raw byte inputs.
- Enforce per-tenant/source quotas so one producer cannot exhaust heap.
- Never load entire Cassandra tables into an unbounded `List` or `collectList()`.

The `64 KiB` limit in the lab mapper is **only an example**; production ceilings must be benchmarked against Cassandra column/partition limits and broker constraints.

### 17.4. Transactions and data retention

Retaining `payload_json` for auditing requires defining TTL, encryption at rest, data minimization, and retention policies. **Cassandra TTL is not JMS/Kafka message TTL**, nor does it guarantee data vanishes from all backups/snapshots the instant TTL expires.

## 18. Observability: from `eventId` to Cassandra row

| Layer | What to measure | Why |
|---|---|---|
| Inbound adapter | Received count, source type, bytes | Understand inbound volume |
| Deserialization | Parse error rate, `schemaVersion` | Detect producer contract drift |
| Domain mapper | Validation failures, normalization latency | Track events rejected before DB |
| Spring transformer | Handler latency, transform error rate | Pinpoint app bottlenecks |
| Entity/driver | Codec/mapper exceptions, query types | Catch schema/type mismatches |
| Cassandra driver | In-flight requests, timeouts, retries, p95/p99 | Monitor DB pressure |
| Cassandra cluster | Per-node read/write latency, hot partitions, compaction | Evaluate data model health |
| Source broker | JMS queue depth / Kafka lag | See downstream slowness building backlog |
| Business | Duplicate/conflicting `eventId` counts | Govern idempotency |
| DLQ/quarantine | Failure reasons, oldest event age, replay counts | Remediate data-contract failures |

### 18.1. Log useful diagnostics without leaking data

At minimum log `eventId`, `traceId`, logical operation, CQL table alias (not necessarily full CQL), schema version, outcome/exception class, and elapsed time. Never log full `payloadJson` by default, especially when events carry payment details or PII.

Never use `eventId` as a per-event metric label, as cardinality will explode. Use logs/traces for per-event debugging and aggregate metrics by source, `eventType`, error category, and environment/region.

### 18.2. Mapping health checks

A passing Cassandra connection health check **does not prove the mapper still matches the schema**. Connectivity can succeed while a table lacks a column, a record constructor mismatches, codecs fail, or producers emit an unsupported `schemaVersion`.

Maintain **canary integration tests** or smoke tests writing/reading a test row in an appropriate environment, verifying fields, precision, and JSON contracts with proper cleanup; never write dummy rows into production tables without retention and access governance.

## 19. Mapping troubleshooting table

| Symptom | Possible cause | Fix |
|---|---|---|
| Adapter reports no mapped entity found | Payload is JSON `String`/`Map` instead of `@Table` entity | Decode/transform before `Type.INSERT` |
| Wrong `@Table` import | Used JPA annotation instead of Cassandra | Import `org.springframework.data.cassandra.core.mapping.Table` |
| Row missing `event_id` or null key | Mapper dropped `eventId` or producer omitted ID | Validate and preserve business `eventId` |
| `orderId` field skips `order_id` column | `NamingStrategy` or missing `@Column` | Map column names explicitly |
| Timestamp shifted by timezone | Converted `Instant` to `LocalDateTime` in JVM timezone | Keep UTC `Instant` and normalize precision |
| Read-back row differs in nanoseconds | Cassandra `timestamp` has millisecond precision | Canonicalize in mapper before writing |
| `amountMinor` precision errors | Used `double`/floating point, unclear scale | Use `long` minor units or contracted `BigDecimal` |
| `CodecNotFoundException` | Java type mismatches CQL type | Check schema, setters, codecs, and converters |
| `MappingException`/constructor error | Record fields mismatch row metadata | Fix annotations, constructors, and field names |
| Custom converter never runs | Annotated `@Component` without registering | Register via `CassandraCustomConversions` |
| Converter runs in wrong direction | Ambiguous `String` ↔ native types | Add `@WritingConverter`/`@ReadingConverter` |
| Converter causes duplicate beans | Added manual Cassandra config over Boot auto-config | Stick to one clear configuration approach |
| `@Transient` field gets persisted | Wrong import or unannotated field | Use `org.springframework.data.annotation.Transient` |
| JSON v2 fails into DTO v1 | Schema version changed without consumer upcasting | Add versioned decoder/mapper and compatibility tests |
| Partial update deletes data | Missing field treated as CQL `NULL` | Separate missing vs null vs `UNSET` update semantics |
| `ReactiveCassandraOperations.insert(...)` writes nothing | Missing subscriber | Return `Mono` to framework or attach subscriber |
| `send()` returns true yet row is absent | Async handler/channel | Await completion per ack policy and observe errors |
| Gateway `SELECT` does not return `OrderEventRow` | `STATEMENT` reply is not automatic entity mapping | Use `selectOneById` or map the reply explicitly |
| `ingestQuery` fails | Matrix missing/extra values, wrong order/codecs | Match `?` count, row width, and types |
| Query by `orderId` invalid | Table partitioned solely by `event_id` | Create a separate table per query pattern |
| Same event creates two timeline rows | Replay computed a different bucket/current time | Build deterministic keys from original `occurredAt` |
| Conflicting data after retry | Same `eventId` with different amount/payload | Add idempotency checks or LWT/inbox |
| JMS never redelivers on Cassandra error | Source acked before async completion | Use durable handoff or await completion |
| Kafka lag spikes suddenly | Slow Cassandra or poison messages | Classify errors, apply backpressure, cap retries |
| Logs expose sensitive data | Serialized full Spring headers/payloads | Enforce field allowlists, masking, and retention |

### 19.1. Pre-production review checklist

1. **Input contract:** clarify whether payloads arrive as DTOs, JSON text, or raw bytes.
2. **Schema:** table, keyspace, columns, and PK match current migrations.
3. **Domain mapper:** validation, `schemaVersion`, timezone/precision, and monetary types verified.
4. **Entity:** `@Table`, `@PrimaryKey`, `@Column`, and composite keys are exact.
5. **Converters:** register custom conversions only when needed with unambiguous read/write directions.
6. **Cassandra handler:** right mode (`INSERT`/`STATEMENT`/`ingestQuery`).
7. **Reactive:** publisher/subscription, async completion, and reply channels properly designed.
8. **Errors:** poison messages separated from DB outages; DLQ/quarantine and alerts configured.
9. **Idempotency:** `eventId`/full Cassandra key stays immutable across redeliveries and replays.
10. **Security:** verified tenant context, allowlisted fields, no excess secrets/PII stored.
11. **Performance:** row sizes, partition layout, in-flight concurrency, and timeouts tuned.
12. **Tests:** unit mapper tests + Cassandra integration round-trips + broker failure paths.

## 20. Hands-on lab: building a payload-to-row mapping pipeline

**Environment:** Java 17+, compatible Spring Integration Cassandra 6+ and Spring Data Cassandra; a Spring Boot app and Cassandra test cluster/Testcontainers. Use matching test brokers to verify JMS/Kafka redelivery. Never run `TRUNCATE`/`DROP` or chaos tests in production.

### Exercise A — Designing the DTO/entity contract

1. Create keyspace `shop_integration` and table `order_event` from section 3.
2. Create `OrderPaidEvent` record matching the JSON fields.
3. Create `OrderEventRow` record with `@Table("order_event")`, `@PrimaryKey("event_id")`, and explicit `@Column` annotations.
4. Document the mapping table: JSON field → Java type → CQL column/type.
5. Verify Cassandra annotation imports; never use JPA annotations.
6. Add a tracing field to the lab entity and apply `@Transient` to keep it out of persistence.

**PASS:** entity metadata matches schema, key fields are non-null, and non-persistent fields are excluded.

### Exercise B — Unit testing the domain mapper

Construct valid events and invoke the mapper directly **without connecting to Cassandra**. JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

class OrderPaidToRowMapperTest {

    private final ObjectMapper objectMapper =
            new ObjectMapper()
                    .registerModule(new JavaTimeModule())
                    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private final OrderPaidToRowMapper mapper =
            new OrderPaidToRowMapper(objectMapper);

    @Test
    void mapsValidEventAndNormalizesTimestamp() {
        OrderPaidEvent input = new OrderPaidEvent(
                "evt-8001", "ORD-8001", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00.123456789Z"),
                150000, "VND");

        OrderEventRow row = mapper.map(input);
        assertEquals("evt-8001", row.eventId());
        assertEquals("ORD-8001", row.orderId());
        assertEquals(150000, row.amountMinor());
        assertEquals(
                Instant.parse("2026-11-23T03:00:00.123Z"),
                row.occurredAt());
    }

    @Test
    void rejectsInvalidAmount() {
        OrderPaidEvent invalid = new OrderPaidEvent(
                "evt-8002", "ORD-8002", "OrderPaid", 1,
                Instant.parse("2026-11-23T03:00:00Z"),
                -1, "VND");
        assertThrows(
                IllegalArgumentException.class,
                () -> mapper.map(invalid));
    }
}
~~~

This example uses **Jackson 2** / Spring Boot 3.x; on Spring Boot 4 with Jackson 3, update imports/config per version. Unit tests verify **validation and object mapping**, not Cassandra driver codecs, primary-key/cluster behavior, or schema compatibility.

### Exercise C — Cassandra integration round-trip

1. Start a Cassandra test container/cluster and provision `order_event`.
2. Inject `ReactiveCassandraOperations`.
3. Build `OrderEventRow` via the mapper and call `operations.insert(row)`.
4. Ensure the `Mono` is subscribed via `StepVerifier`/a test subscriber.
5. Call `operations.selectOneById("evt-8001", OrderEventRow.class)`.
6. Compare all read-back fields, especially `Instant` millisecond precision and `payloadJson`.
7. Resend the same event ID and verify no **second row** appears under a different key.

~~~java
// Test fragment assuming "operations" and "row" exist:
reactor.test.StepVerifier.create(
        operations.insert(row)
                .then(operations.selectOneById(
                        row.eventId(), OrderEventRow.class)))
        .assertNext(found -> {
            org.junit.jupiter.api.Assertions.assertEquals(
                    row.eventId(), found.eventId());
            org.junit.jupiter.api.Assertions.assertEquals(
                    row.occurredAt(), found.occurredAt());
        })
        .verifyComplete();
~~~

**PASS:** CQL rows read back accurately matching entity metadata/types. Never claim from unit mocks alone that the driver maps every field properly against real Cassandra.

### Exercise D — Java DSL Transformer and outbound adapter

1. Configure `orderPaidToCassandra` from section 6.2.
2. Send `Message<OrderPaidEvent>` to `validatedOrderPaidEvents`.
3. Query Cassandra by `eventId` and verify the row.
4. Send a DTO with invalid `currency`/`amountMinor` and verify validation fails before calling Cassandra.
5. Send a `String` payload into the DTO-only channel and observe the transformer conversion error.
6. Switch `async(false)` to the async default and compare when `send()` returns vs write completion.

**PASS:** no raw JSON `String` reaches `Type.INSERT`; response/error boundaries are well understood.

### Exercise E — JSON decoder and versioned schemas

1. Wire `rawJsonOrderPaidToCassandra` from section 6.3 instead of the DTO-input flow.
2. Send valid JSON and verify deserialization, validation, mapping, and persistence.
3. Send malformed JSON, unparseable timestamps, and `schemaVersion=99`; classify each error.
4. Implement a v2 decoder supporting `paymentMethod` while remaining backward-compatible with v1.
5. Add a nullable column in Cassandra first before deploying the updated mapper.
6. Read legacy rows post-migration and verify no crashes when the new field is absent.

**PASS:** invalid/unsupported schema events are quarantined per policy rather than turning into Cassandra timeouts.

### Exercise F — Composite keys and timelines

1. Create `events_by_order_month` from section 8.
2. Define `OrderTimelineKey` with three partition columns and two clustering columns.
3. Map an event at the end of November and one at the start of December into two `OrderTimelineRow`s.
4. Query supplying full `tenant_id`, `order_id`, and `bucket_month`.
5. Replay the same event in January of the next year and confirm the bucket still uses the original `occurredAt`.
6. Pass an unverified `tenantId` header and confirm the mapper does not trust the client header directly.

**PASS:** deterministic composite key; redeliveries never spawn extra rows.

### Exercise G — RowMapper vs entity mapping

1. Use `OrderEventReader.findRow(...)` to read an entity.
2. Use `EventSummaryDao.findById(...)` to read 3 columns via a CQL `RowMapper`.
3. Test `ReactiveCqlOperations.query(...)` and subscribe to `Flux<EventSummary>`.
4. Measure latency/bytes when selecting 3 columns vs fetching full `payload_json`.
5. Test a query lacking a partition-key predicate, observe the failure or scan cost, and fix the schema/query.

**PASS:** knows when to use entity converters, `RowMapper`, and projections; never mistakes `RowMapper` for an outbound `Transformer`.

### Exercise H — Three modes of CassandraMessageHandler

1. With the same `OrderEventRow`, run `Type.INSERT` entity mode.
2. Convert the row into `List<List<Object>>` and run `ingestQuery`.
3. Run `statementFunction` returning a driver `SimpleStatement` with positional values.
4. Send a matrix missing one value: confirm schema/codec/binding errors surface clearly.
5. Send a JSON `String` into entity mode: confirm it does not auto-map into a row.
6. Wire a `SELECT` gateway and inspect the reply type; when `OrderEventRow` is desired, use `selectOneById` or explicit mapping.

**PASS:** selects handler mode by input contract and owns mapping at the proper layer.

### Exercise I — Error handling, retries, and idempotency

1. Use a transacted JMS listener or a test Kafka consumer with a defined offset policy.
2. Send a valid event over `DirectChannel` + sync Cassandra handler.
3. Simulate Cassandra unavailability and confirm exceptions propagate to the source boundary per config.
4. Let Cassandra write succeed, crash before source commit, and let the broker redeliver the same `eventId`.
5. Verify the mapper builds the **exact same row** on replay and preserves the event ID.
6. Resend the same `eventId` with a different amount; classify it as a conflicting duplicate requiring investigation.
7. Switch to an async channel/handler to observe Cassandra errors surfacing after the source callback finishes.
8. Add DLQ/quarantine/durable handoff appropriate to both error classes.

**PASS:** never claims Cassandra and the broker share a cross-system transaction; implements clean replay without swallowing errors.

### Verification matrix

| Topic | PASS outcome |
|---|---|
| JSON decoder | Correct types, timestamps, and `schemaVersion` |
| Domain validation | Rejects missing IDs or invalid amounts before DB |
| Entity mapping | `@Table`/`@PrimaryKey`/`@Column` align with CQL |
| Nullability & precision | No data loss from nulls or timestamp precision |
| Round-trip | Read-back row matches key and values |
| Composite key | Partition/clustering fields ordered accurately |
| Spring DSL | Transformer runs before Cassandra `INSERT` |
| Custom conversions | Registered with unambiguous read/write directions |
| `RowMapper` | CQL `Row` → DTO matches column count and types |
| Entity vs ingest | `List<entity>` not confused with `List<List<?>>` |
| Statements | Bound values used; no CQL concatenation from clients |
| Async/ack | Completion and errors cross the right boundaries |
| Idempotency | Preserves `eventId` and deterministic primary keys |
| Security | Untrusted tenants/headers/secrets never persisted |
| Migrations | Historical rows remain readable after schema evolution |

## 21. Self-assessment questions

1. Why doesn't the Cassandra outbound adapter in `Type.INSERT` mode automatically map a JSON `String` to a CQL row?
2. How do a Spring Message payload, message headers, and a Cassandra entity differ?
3. At which two layers do a Spring Integration `Transformer` and Spring Data `MappingCassandraConverter` operate?
4. What does `@Table("order_event")` do? Can a JPA annotation replace it?
5. Why declare `@Column("amount_minor")` explicitly instead of relying purely on naming conventions?
6. How does CQL `event_id text PRIMARY KEY` differ from regular column `order_id`?
7. Does Cassandra auto-assign `eventId` like SQL auto-increment on `insert`?
8. Why must a redelivered event preserve the original business `eventId`?
9. What are the benefits of separating `OrderPaidEvent` from `OrderEventRow`?
10. Should all Spring Message headers be serialized into `payload_json`? Why or why not?
11. Why normalize `Instant` to millisecond precision before persisting a CQL `timestamp`?
12. How does computing a bucket from `occurredAt` differ from using the consumer's processing date?
13. Why is Java `double` often unsuitable for monetary amounts?
14. Can a Java `String` property automatically map to a Cassandra `uuid` in every case?
15. When should you prefer `BigDecimal` vs `long amountMinor`?
16. How do CQL `NULL` and `UNSET` differ in a partial `UPDATE`?
17. Why shouldn't an omitted JSON field be interpreted automatically as "delete the Cassandra column"?
18. Which limits should be enforced on raw JSON and row sizes before writing?
19. When are `@PrimaryKeyClass` and `@PrimaryKeyColumn` used?
20. How do Cassandra partition keys and clustering columns affect order-history queries?
21. Why does a composite key class need value-based `equals/hashCode`?
22. If a source carries an unverified `tenantId`, how should the mapper handle it?
23. Does Spring Data `CassandraCustomConversions` auto-discover converters via component scanning?
24. How do `@WritingConverter` and `@ReadingConverter` differ in conversion direction?
25. When should you write a custom type converter vs just a domain `Transformer`?
26. Is `RowMapper` used for `INSERT` or `SELECT`? In which direction does it map?
27. What does `ReactiveCassandraOperations.selectOneById(...)` return when no row exists?
28. Why should you never swallow a Cassandra timeout and return `Mono.empty()`?
29. When should you use a projection/`RowMapper` instead of reading the entire `payload_json`?
30. What annotation metadata does `CassandraMessageHandler.Type.INSERT` expect on its payload?
31. What payload shape does `ingestQuery` require, and why does positional value order matter?
32. What does `statementFunction` accept and return?
33. Why don't bind parameters protect client-supplied table or column names?
34. How is `List<OrderEventRow>` handled differently from `List<List<?>>` by the handler?
35. How do `Cassandra.outboundChannelAdapter(...)` and `outboundGateway(...)` differ in reply contracts?
36. Why doesn't `MessageChannel.send(true)` always prove Cassandra finished writing?
37. How do `DirectChannel` + sync handler and `ExecutorChannel` + async differ on JMS failures?
38. Should JSON contract errors and Cassandra `UnavailableException` share the same retry policy?
39. When the same `eventId` arrives with a different payload, why isn't it a benign duplicate?
40. Is persistence entity `@Version` the same as JSON `schemaVersion`?
41. Does renaming a CQL column in a migration require updating entity annotations or transformers?
42. Why can't unit mapper tests replace integration tests for Cassandra codecs and schemas?
43. If a Kafka event commits its offset before a Cassandra write fails, what recovery mechanism is needed?
44. Name three metrics or traces that distinguish mapper failures from cluster timeouts.
45. Which rules ensure an event produces the **exact same Cassandra row key** across replays?

## 22. Official references

- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): `CassandraMessageHandler`, entity payloads, `List<entity>`, `ingestQuery`, `statementFunction`, adapters/gateways, and async behavior.
- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `MappingCassandraConverter`, `@Table`, `@PrimaryKey`, `@Column`, `@Transient`, `@PrimaryKeyClass`, and composite keys.
- [Spring Data Cassandra — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraTemplate`/`ReactiveCassandraTemplate`, `insert`/`selectOneById`, type conversion, and exception translation.
- [Spring Data Cassandra — Custom Conversions](https://docs.spring.io/spring-data/cassandra/reference/cassandra/converters.html): `CassandraCustomConversions`, `@ReadingConverter`/`@WritingConverter`, and explicit converter registration.
- [Spring Data Cassandra — Property-based Converters](https://docs.spring.io/spring-data/cassandra/reference/cassandra/property-converters.html): per-property conversion rather than global type conversion.
- [Spring Data Cassandra API — ReactiveCassandraOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/ReactiveCassandraOperations.html): `insert`, `selectOneById`, `selectOne`, and reactive results.
- [Spring Data Cassandra API — CqlTemplate](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/CqlTemplate.html): `query`/`queryForObject`, prepared binding, and `RowMapper`.
- [Spring Data Cassandra API — ReactiveCqlOperations](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/ReactiveCqlOperations.html): `Flux`/`Mono` `RowMapper` and reactive CQL operations.
- [Spring Data Cassandra API — MappingCassandraConverter](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/convert/MappingCassandraConverter.html): object mapping, CQL row → entity, and conversions.
- [Spring Integration — Message Transformation](https://docs.spring.io/spring-integration/reference/transformer.html): `Transformer` in `IntegrationFlow`.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage` and `errorChannel` under messaging semantics.
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): choosing partition keys and tables from query patterns.
- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): CQL `timestamp`, `bigint`, `decimal`, `uuid`, and collections.
- [Apache Cassandra Java Driver — Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): CQL parameters, codecs, binding, and routing metadata.

**Key takeaway:** Mapping payloads to Cassandra rows requires **at least two independent steps**: turning transport inputs into a **validated DTO**, and turning the **DTO into a schema-aligned entity or CQL values**. In Spring Integration, place a `Transformer` before `Cassandra.outboundChannelAdapter(..., Type.INSERT)` so the handler receives a **`@Table` entity**; never confuse entity mode with `ingestQuery(List<List<?>>)` or `statementFunction(Statement<?>)`. Spring Data's `MappingCassandraConverter` handles column names, primary keys, and Java↔CQL types, yet **never replaces** domain validation, tenant authorization, versioning, idempotency, or acknowledgment design with JMS/Kafka. Test both unit mappers and round-trips against real Cassandra before production.







