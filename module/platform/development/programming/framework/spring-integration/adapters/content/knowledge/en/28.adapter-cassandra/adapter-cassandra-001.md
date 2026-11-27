# Cassandra outbound channel adapter

## 1. Problem: writing data from IntegrationFlow into Cassandra

An e-commerce application receives an `OrderPaid` event over HTTP or JMS. The system needs to store a copy of the event for lookup and reconciliation by `eventId` in **Apache Cassandra**, and then continue processing other flows. If you write CQL statements directly in every handler, database connection logic becomes scattered across the integration flow, making it hard to standardize timeouts, error handling, and observability.

Spring Integration's **Cassandra outbound channel adapter** solves this integration point: a `MessageChannel` delivers a **Spring Message** to the adapter, and the adapter uses **Spring Data for Apache Cassandra** to execute the operation against the Cassandra cluster. This is a **one-way outbound endpoint**: its primary job is to write/execute the operation, and it **does not emit a business reply** back to the flow.

In the **SPRING_INTEGRATION_ADAPTERS** module, learners connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing message contracts, error handling, and connection lifecycles with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. The **Adapter Cassandra** chapter extends that knowledge to a distributed data model, reactive persistence, and Cassandra-specific transactional boundaries.

**After this lesson you will be able to:**

1. Explain the roles of `CassandraMessageHandler`, `ReactiveCassandraOperations`, and `Cassandra.outboundChannelAdapter(...)`.
2. Configure a **Spring Message → Cassandra** flow for an entity mapped with `@Table` and `@PrimaryKey`.
3. Choose the right mode (`INSERT`, `UPDATE`, `DELETE`, or `STATEMENT`) and the right payload type.
4. Distinguish a **one-way adapter** from a **Cassandra outbound gateway** that produces a reply.
5. Understand the **asynchronous** default and its consequences for exceptions, acknowledgment, retries, and write outcomes.
6. Design Cassandra keyspace/table schemas, timeouts, consistency, idempotency, backpressure, and integration tests.

## 2. Architecture overview and responsibility boundaries

~~~mermaid
flowchart LR
    A["HTTP/JMS/File inbound endpoint"] --> B["Transformer + Validator"]
    B --> C["Spring Message<OrderEvent>"]
    C --> D["MessageChannel"]
    D --> E["Cassandra outbound channel adapter"]
    E --> F["CassandraMessageHandler"]
    F --> G["ReactiveCassandraOperations"]
    G --> H["Cassandra driver + CqlSession"]
    H --> I[("Apache Cassandra cluster")]
~~~

| Component | Responsibility | Does not guarantee on its own |
|---|---|---|
| `MessageChannel` | Hands off Spring Messages between endpoints | Not a durable queue if the channel is in-memory |
| `Cassandra.outboundChannelAdapter(...)` | Creates the spec for the outbound handler | Does not create the Cassandra cluster or keyspace |
| `CassandraMessageHandler` | Reads the payload, selects the operation type, calls the reactive API | Does not act as a transaction manager across HTTP/JMS/Cassandra |
| `ReactiveCassandraOperations` | Executes Cassandra operations and entity mapping | Does not automatically choose an optimal data model for all queries |
| `CqlSession`/driver | Connections, routing, driver-level timeout/consistency | Does not perform business deduplication on its own |
| Cassandra cluster | Stores data by partition/replica | Does not provide multi-table ACID transactions like an RDBMS |

Spring Integration has supported the **Cassandra outbound channel adapter and outbound gateway since version 6.0**. According to the Spring Integration endpoint summary table, the Cassandra module **does not provide a dedicated Cassandra inbound channel adapter** like JDBC polling inbound. If you need to detect Cassandra changes to trigger a flow, you must choose another architecture, such as an event source, an appropriate CDC mechanism, or a purposefully implemented poller; do not invent `Cassandra.inboundAdapter(...)`.

### 2.1. Journey of an event

~~~mermaid
sequenceDiagram
    participant P as Event producer
    participant Flow as Spring Integration flow
    participant Handler as CassandraMessageHandler
    participant Ops as ReactiveCassandraOperations
    participant DB as Cassandra
    P->>Flow: Spring Message<OrderEvent>
    Flow->>Handler: handle()
    Handler->>Ops: INSERT entity (reactive)
    Ops->>DB: CQL write
    DB-->>Ops: Write completion or error
    Ops-->>Handler: Success/error signal
    Note over Flow,Handler: Async mode determines when the caller can learn the outcome
~~~

Note: **`MessageChannel.send(...)` returning success does not necessarily prove Cassandra has finished writing.** Especially when the outbound handler runs asynchronously, the call may complete before the CQL operation finishes. This differs from a service using synchronous `CassandraTemplate` and directly awaiting the result.

## 3. Preparing dependencies and environment

The examples target **Spring Integration 6+**, a compatible Spring Data for Apache Cassandra version, Java 17+, and a test Cassandra cluster. Spring Integration 7+ still includes the core APIs presented here; **do not mix versions manually** across Spring Integration, Spring Data, the driver, and the Spring Boot BOM.

If using Spring Boot with its BOM, the core dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cassandra</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra-reactive</artifactId>
</dependency>
~~~

`spring-integration-cassandra` contains the integration endpoints. Spring Data Cassandra reactive provides `ReactiveCassandraOperations`; the driver connects to the cluster via `CqlSession`. The Spring Boot starter is one auto-configuration option; if not using Boot, you must declare compatible beans for reactive Cassandra operations and the driver.

An illustrative Spring Boot configuration for a **local development environment**:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

This is an **example Spring Boot application configuration**, not a lesson metadata YAML file. `datacenter1` must match the datacenter name advertised by your Cassandra broker/test container; do not assume a real cluster uses the same name. Addresses/ports, authentication, and TLS must be managed through appropriate configuration/secrets mechanisms. Application startup does not mean the keyspace/table already exists.

### 3.1. CQL schema for the exact lookup pattern

Choose a simple goal: **write and read by `eventId`**. On a test cluster, create the keyspace and table:

~~~sql
-- Use SimpleStrategy only for a single-datacenter/single-node test environment.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    occurred_at timestamp,
    payload_json text
);
~~~

**Why choose `event_id` as the partition key?** Because the lab primarily checks a record with `WHERE event_id = ?` and wants retries with the same event ID to write to the same key. If a new requirement asks for `SELECT ... WHERE order_id = ? ORDER BY occurred_at`, the current table is **not optimal**. Cassandra is designed around **query patterns**; you must build a different table/partition/clustering key rather than expecting `ALLOW FILTERING` or arbitrary indexes to solve every query.

Do not copy `SimpleStrategy` into multi-datacenter production; you must choose the replication strategy, replication factor, consistency, and topology according to real Cassandra operational design.

### 3.2. Entity model using Spring Data Cassandra

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("occurred_at") Instant occurredAt,
        @Column("payload_json") String payloadJson) {
}
~~~

`@Table` specifies the Cassandra table; `@PrimaryKey` and `@Column` explicitly map Java fields to CQL column names. `Instant` maps appropriately to Cassandra `timestamp` under the active codec/mapping setup. The record above is immutable, so each event has a stable `eventId` and a JSON payload that has been serialized/validated **before** being sent to the outbound adapter.

If an event requires a composite business key, Spring Data Cassandra supports `@PrimaryKeyClass`/`@PrimaryKeyColumn` with partition/clustering columns, but it must be designed based on queries and partition size; do not pick keys arbitrarily just to "have a composite key".

## 4. Java DSL: Cassandra outbound channel adapter writing an entity

Spring Integration uses the factory:

~~~java
Cassandra.outboundChannelAdapter(reactiveCassandraOperations)
~~~

or the overload specifying `CassandraMessageHandler.Type`. In the hands-on exercise, **explicitly choose the `INSERT` mode** and set `async(false)` so write errors are easily observed within the same call when running over a synchronous channel:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;

@Configuration
@EnableIntegration
public class OrderEventCassandraConfig {

    @Bean
    public IntegrationFlow saveOrderEventToCassandra(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("cassandraOrderWrite")
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Here:

- `ReactiveCassandraOperations` is a **Spring Data Cassandra bean**, typically implemented by `ReactiveCassandraTemplate`. The adapter does **not** directly accept `JdbcTemplate`, imperative `CassandraTemplate`, or `DataSource`.
- `Cassandra.outboundChannelAdapter(...)` creates a `CassandraMessageHandler` as the channel consumer.
- `Type.INSERT` expects the payload to be an **entity mapped with `@Table`**, or a supported list of entities; in this example, `OrderEvent`.
- `endpoint.async(false)` sets a more synchronous handler execution mode: Spring Integration calls `Mono.block()` to wait for the operation to finish. This is an appropriate option for **labs and flows that require observing errors synchronously**, not the highest-throughput default.
- The adapter **does not emit a reply** to a Spring `replyChannel`. If you need the `WriteResult`, use the outbound **gateway** presented in section 7.

Having `async(false)` does not turn the operation into an ACID transaction across HTTP/JMS/another DB; it only changes when the caller waits for and receives the completion signal of the Cassandra operation.

### 4.1. Sending a Spring Message to the input channel

~~~java
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel cassandraOrderWrite;

    public OrderEventPublisher(
            @Qualifier("cassandraOrderWrite") MessageChannel cassandraOrderWrite) {
        this.cassandraOrderWrite = cassandraOrderWrite;
    }

    public void publish(String eventId, String orderId, String json) {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("Missing JSON");
        }

        OrderEvent event = new OrderEvent(
                eventId, orderId, "OrderPaid", Instant.now(), json);

        boolean sent = cassandraOrderWrite.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventType", event.eventType())
                        .setHeader("eventId", event.eventId())
                        .build());
        if (!sent) {
            throw new IllegalStateException(
                    "Spring Message was not delivered to the Cassandra endpoint");
        }
    }
}
~~~

The snippet above is a realistic service in a Spring application that has the flow from section 4, the corresponding channel bean, and a working Cassandra connection. `MessageBuilder` wraps `OrderEvent` as the payload; headers serve routing/tracing purposes but are **not automatically written as Cassandra columns**. Entity mapping determines which columns are inserted.

**Do not confuse `send(true)` with "durably persisted":** on a `DirectChannel` with an `async(false)` handler, the method may only return after the Cassandra operation reports completion, yet the outcome still depends on timeouts/consistency and cluster state. If you switch to an `ExecutorChannel` or enable async, sending on the channel can finish **before the CQL write**.

### 4.2. Valid and invalid payloads

| Spring Message payload | Adapter mode | Consequence |
|---|---|---|
| `OrderEvent` with `@Table` | `INSERT` | Spring Data maps the entity to a CQL INSERT |
| `List<OrderEvent>` | `INSERT` | Can perform a batch operation according to Spring Data |
| `String` JSON containing the event | `INSERT` | **Does not** parse JSON into an entity by default; requires a transformer |
| `Map<String,Object>` | `INSERT` | Not a mapped entity in this example; do not assume it maps to a table |
| Driver `Statement<?>` | `STATEMENT` | Executes a custom statement without using INSERT entity mapping |
| `List<List<?>>` | `ingestQuery(...)` | Interpreted as a matrix of parameter rows for CQL ingest |

If the inbound message arrives from HTTP/JMS with a JSON `String` payload, **deserialize/validate** it in a transformer before sending it to the Cassandra endpoint:

~~~java
// Fragment inside IntegrationFlow; objectMapper is already injected.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, OrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("Invalid OrderEvent JSON", ex);
    }
})
.channel("cassandraOrderWrite")
~~~

This is a fragment, not a complete Java flow. Using `OrderEvent` directly on `MessageChannel` avoids unnecessary re-serialization/deserialization when systems inside the JVM already have the DTO.

## 5. INSERT, UPDATE, DELETE, and STATEMENT: choosing the right mode

`CassandraMessageHandler.Type` has **four values**: `INSERT`, `UPDATE`, `DELETE`, and `STATEMENT`.

| Mode | Expected payload | Purpose | Warning |
|---|---|---|---|
| `INSERT` | A `@Table` entity or list of entities | Write data via mapping | Standard Cassandra INSERT has **upsert semantics** |
| `UPDATE` | A `@Table` entity or list of entities | Update data from entity | No optimistic locking/compare-and-set by default |
| `DELETE` | A `@Table` entity or list of entities | Delete data based on mapping/key | Cassandra creates tombstones; delete scale must be controlled |
| `STATEMENT` | `Statement<?>` or result of query/expression/processor | Execute a custom CQL statement | CQL must use bind values and be constrained to business rules |

Example of changing an adapter's mode:

~~~java
// Fragment: a separate flow dedicated to DELETE.
.handle(Cassandra.outboundChannelAdapter(
        operations, CassandraMessageHandler.Type.DELETE),
        endpoint -> endpoint.async(false))
~~~

Do not mutate the mode of the same singleton handler based on an arbitrary header while multiple messages are being processed. If you need one flow for insert and another for delete, use a **router** to route Spring Messages to separate channels/handlers with clear contracts.

### 5.1. Cassandra INSERT is an upsert, not "insert if absent"

With a standard statement:

~~~sql
INSERT INTO shop_integration.order_event (
    event_id, order_id, event_type, occurred_at, payload_json
) VALUES (
    'evt-1501', 'ORD-1501', 'OrderPaid',
    '2026-11-23T03:00:00Z', '{"eventId":"evt-1501"}'
);
~~~

Sending the same `event_id` again can **overwrite/merge column values** according to write timestamps and Cassandra last-write-wins rules. Cassandra **does not** reject duplicate records by default the way a relational database with a unique constraint fails an `INSERT` when the key already exists.

If the business requires **writing only if absent**, you must use a **lightweight transaction**/conditional CQL `IF NOT EXISTS` or an idempotency strategy with proper consistency/race analysis, and inspect `[applied]`. Switching the adapter to normal `INSERT` **does not enable LWT automatically**.

### 5.2. UPDATE and DELETE also require the key

Cassandra `UPDATE` can create a new row when the key does not exist, depending on the statement and data; do not infer that a simple UPDATE operation means "modify only an existing row". DELETE creates tombstones and affects storage/compaction; bulk deletion by partition key is a design decision, not merely "removing from RAM".

For order status transitions, evaluate the **last-write-wins model and event ordering**; if `OrderCancelled` arrives before `OrderPaid` due to asynchrony, event-based upserts can regress the state. Use a version/guard or LWT when atomic compare-and-write within a partition is required.

## 6. Ingest query: sending multiple rows via a value matrix

`CassandraMessageHandler.setIngestQuery(...)` and Java DSL `ingestQuery(...)` enable ingestion using a CQL INSERT with placeholders. According to Spring Integration documentation, the payload must then be **`List<List<?>>`**, where each inner list represents a row of values matching the order of question marks in the CQL.

Example:

~~~java
@Bean
public IntegrationFlow bulkOrderEventIngest(
        ReactiveCassandraOperations operations) {

    String cql = """
            INSERT INTO order_event
              (event_id, order_id, event_type, occurred_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """;

    return IntegrationFlow.from("cassandraBulkWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .ingestQuery(cql),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Assume a default keyspace `shop_integration` is configured on the Cassandra session. Payload sent to `cassandraBulkWrite`:

~~~java
import java.time.Instant;
import java.util.List;

List<List<?>> rows = List.of(
    List.of("evt-1501", "ORD-1501", "OrderPaid",
            Instant.parse("2026-11-23T03:00:00Z"), "{\"eventId\":\"evt-1501\"}"),
    List.of("evt-1502", "ORD-1502", "OrderPaid",
            Instant.parse("2026-11-23T03:01:00Z"), "{\"eventId\":\"evt-1502\"}")
);

cassandraBulkWrite.send(MessageBuilder.withPayload(rows).build());
~~~

`cassandraBulkWrite` is an injected `MessageChannel`, and `MessageBuilder` is imported from Spring Messaging as before. **The number of elements in each inner list must match the number of placeholders**; all values must have a supported Cassandra type/codec. If nullable fields are needed, do not use `List.of(...)` for a list containing `null` (Java disallows it).

**Batch warning:** A Cassandra batch is not a tool to compress an entire multi-million-row CSV file into one faster transaction. Multi-partition batches can consume significant coordinator resources and degrade throughput. Use small chunks, control memory and concurrency, and monitor p95 latency; batching should only be used when clearly supported by the domain and driver. `ingestQuery` does not turn Cassandra into a multi-partition ACID transactional database.

## 7. STATEMENT: safely building custom CQL and distinguishing the outbound gateway

`STATEMENT` mode provides fine-grained CQL control that Spring Data entity mapping cannot express directly. Three approaches are supported by `CassandraMessageHandler`:

1. **`query(String)`** with `parameter(...)` to bind named parameters.
2. **`statementExpression(...)`** using SpEL that returns a driver `Statement<?>` object.
3. **`statementFunction(...)`** building a `Statement<?>` from a Spring Message via a Java function.

### 7.1. Statement function using bind values, not string concatenation of input

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow writeOrderEventStatement(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraStatementWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, occurred_at, payload_json) "
                                + "VALUES (?, ?, ?, ?, ?)",
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.occurredAt(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(String, Object...)` uses **bind values** instead of concatenating HTTP/JMS data into the CQL string. This reduces injection risks for **values**, while letting the driver manage types/codecs. **Keyspace/table/column names must not be assembled from user input**; allow only predefined identifiers.

If you need to use DataStax Java Driver `QueryBuilder`, you can construct a statement with the builder and pass it directly as the payload or return it from `statementFunction(...)`. For standard business logic, Spring Data entity mapping is simpler and easier to govern than generating every CQL query manually.

### 7.2. CQL query with named parameters

~~~java
// Fragment inside IntegrationFlow; use only when STATEMENT mode is needed.
.handle(Cassandra.outboundChannelAdapter(operations)
        .query("INSERT INTO order_event "
             + "(event_id, order_id, event_type) "
             + "VALUES (:eventId, :orderId, :eventType)")
        .parameter("eventId", "payload.eventId")
        .parameter("orderId", "payload.orderId")
        .parameter("eventType", "payload.eventType"),
        endpoint -> endpoint.async(false))
~~~

According to Spring Integration, **`.query(...)` automatically selects `STATEMENT` mode**, and `.parameter(...)` provides expressions evaluated against the Spring Message. These are **named bind values**; avoid concatenating CQL strings with unvalidated values.

**Do not use parameters in other modes and expect them to take effect:** `parameterExpressions` are used with `query(String)`, not with default entity `INSERT` or a manually built driver `Statement`.

### 7.3. How is an outbound adapter different from an outbound gateway?

A `CassandraMessageHandler` can operate in two roles:

| Requirement | Endpoint to choose | Effect on Spring MessageChannel |
|---|---|---|
| Only send entity to write, no reply needed | `Cassandra.outboundChannelAdapter(...)` | Does not actively produce a Spring reply |
| Want to read write result or SELECT | `Cassandra.outboundGateway(...)` | Produces a reply based on the operation |
| Want synchronous result to drive business logic | Gateway `async(false)` | Operation result is awaited and returned to the flow |
| Want to maintain end-to-end reactive processing | Async gateway and appropriate `FluxMessageChannel` | Publisher/reply is handled in a reactive flow |

Example gateway returning the INSERT result:

~~~java
@Bean
public IntegrationFlow writeOrderEventWithReply(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraWriteRequests")
            .handle(Cassandra.outboundGateway(operations,
                            CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .channel("cassandraWriteResults")
            .get();
}
~~~

According to Spring Integration documentation, in **async gateway** mode, the Cassandra handler produces a `Mono<WriteResult>` and further processing depends on the `MessageChannel` type; with `async(false)`, the handler can call `Mono.block()` to obtain the result. For a truly reactive pipeline, `FluxMessageChannel` is usually more suitable than a blocking channel. This is an **alternative gateway flow** to the adapter in section 4; do not attach both endpoints to the same input channel when only a single write is intended.

**Note:** A gateway does not turn the result into a distributed transaction or guarantee "exactly once"; `WriteResult` reflects the completion of the Cassandra operation according to the driver/session/consistency and must be interpreted per the specific API and operation.

## 8. XML namespace and plain Java configuration

Spring Integration also provides the `int-cassandra` XML namespace. To use XML, you must declare the proper namespace/XSD for your version and create the `ReactiveCassandraOperations` bean.

~~~xml
<int:channel id="cassandraOrderWrite"/>

<int-cassandra:outbound-channel-adapter
        id="orderEventCassandraWriter"
        channel="cassandraOrderWrite"
        cassandra-template="reactiveCassandraTemplate"
        mode="INSERT"
        async="false"
        auto-startup="true"/>
~~~

This is a fragment: it requires the `int` and `int-cassandra` namespaces, a bean named `reactiveCassandraTemplate` that actually implements `ReactiveCassandraOperations`, and a configured Cassandra session. In XML, the `cassandra-template` attribute references the **reactive** template/operations; do not pass synchronous `CassandraTemplate` just because the attribute name sounds similar.

If the application uses Spring Boot auto-configuration, the bean name may differ from the example; set the reference according to the actual bean name. Register either Java DSL **or** XML for the same writer, avoiding two consumers accidentally executing the same operation.

### Plain Java configuration without DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraOrderWrite")
public MessageHandler cassandraOrderWriter(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setAsync(false);
    return handler;
}
~~~

Here `@ServiceActivator` routes messages from the `cassandraOrderWrite` channel to the handler. This is an **alternative** to `Cassandra.outboundChannelAdapter(...)` in Java DSL; both use `CassandraMessageHandler`. Do not create a `MessageHandler` bean and forget to register it as a consumer on the channel, otherwise Spring Messages may have nowhere to be handled.

## 9. Asynchrony, reactive execution, and error reporting paths

`CassandraMessageHandler` uses `ReactiveCassandraOperations` and, according to Spring Integration documentation, **defaults to `async=true`**. This strongly affects how the application knows whether an operation succeeded or failed.

### 9.1. Comparing the two modes

| Aspect | `async=true` (default) | `async=false` |
|---|---|---|
| Execution flow | Asynchronous/reactive | Handler blocks for the reactive operation result |
| Caller on `DirectChannel` | Can return before Cassandra completion | Can observe operation errors on the same call path |
| Throughput | Reduces thread blocking but requires in-flight limits | Easier to reason about; threads may wait long on DB |
| Error handling | Late results/errors require an appropriate error observation path | Exceptions can propagate back to synchronous channel callers |
| Interaction with source transaction | Does not keep the source transaction open until Cassandra finishes | Still no distributed transaction with Cassandra |
| Use case | Well-managed reactive pipelines and high load | Labs, simple migrations, when synchronous completion is required |

Spring Data Cassandra documentation emphasizes that **reactive publishers are lazy**: creating a `Mono`/`Flux` performs no I/O until subscribed. The Spring Integration handler handles subscribing the publisher within the endpoint. If you use `ReactiveCassandraTemplate.insert(entity)` directly in custom code, **there must be an actual subscriber**; calling the API and discarding the `Mono` will not persist data.

### 9.2. A timeout does not prove the write failed

Suppose the cluster processed an INSERT, but the client lost the connection before receiving the success response. The caller may observe a timeout, retry, and send the same event a second time. Therefore:

- For normal Cassandra upserts, use a **stable primary key** and immutable event data to minimize the impact of duplicate deliveries.
- If write-once semantics are required, use a conditional write/LWT scoped properly to the partition and inspect the `[applied]` status.
- If an error occurs after a JMS/Kafka source has already acknowledged/committed, you cannot assume increasing retries on the Cassandra endpoint achieves exactly-once delivery.
- Do not merely log `MessageChannel.send()==true` and report "saved" to the business when the endpoint is async.

### 9.3. `errorChannel`, exceptions, and message sources

Entity mapping errors, CQL syntax errors, timeouts, authentication failures, or unavailability can happen:

1. **Before the reactive operation is scheduled**, such as an invalid payload type or missing query configuration.
2. **During operation execution**, such as Cassandra unavailable or a write timeout.
3. **After Cassandra applied the operation but the client did not receive confirmation**, leaving an uncertain outcome.

With a sync handler and a `DirectChannel` path, exceptions can propagate back to the inbound endpoint. With an async handler or `ExecutorChannel`, errors may surface after upstream already returned success; configure an appropriate **error channel, monitoring, or reactive error handling**, and verify via integration tests that errors are actually captured in your version.

**Do not conclude that `errorChannel` automatically retries or creates a DLQ.** It is a Spring Integration channel carrying `ErrorMessage`, not a transaction, broker queue, or recovery strategy. Never catch and ignore an exception if it represents a failure that must be remediated.

## 10. `WriteOptions`: TTL, consistency, timeouts, and idempotency

`CassandraMessageHandler` allows specifying Spring Data Cassandra `WriteOptions`, typically used with `INSERT`, `UPDATE`, or `DELETE`. This is configuration **for the database write**, unlike JMS `timeToLive`, HTTP timeouts, or Spring `MessageChannel.sendTimeout`.

### 10.1. Example setting TTL for demo records

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;

@Bean
public WriteOptions demoEventWriteOptions() {
    return WriteOptions.builder()
            .ttl(Duration.ofDays(7))
            .build();
}

@Bean
public IntegrationFlow eventWriteWithTtl(
        ReactiveCassandraOperations operations,
        WriteOptions demoEventWriteOptions) {

    return IntegrationFlow.from("cassandraTtlWrite")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(demoEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

This is **an alternative flow** to the basic example, not a requirement to write the same event twice. Cassandra TTL defines the time-to-live of the written cells (depending on the operation and schema), not "delete the row instantly after seven days" like a scheduled job. Expired data produces tombstones and compaction behavior; many varying TTLs can also increase operational overhead.

**Do not set arbitrary TTLs on payment events, audit records, or data required for long-term reconciliation.** Retention must be approved against data contracts and storage policies.

### 10.2. Consistency level and timeout

Cassandra uses **consistency levels** such as `ONE`, `LOCAL_QUORUM`, or other options to define required responses from replicas within the replication topology. `WriteOptions` or DataStax driver execution profiles can carry consistency/timeout settings; the right choice depends on keyspace replication, local datacenter, and SLAs.

| Setting | What to ask before choosing? | What must not be inferred |
|---|---|---|
| `ConsistencyLevel.ONE` | What read/write guarantees does the application accept? | Does not mean data has replicated to all replicas |
| `LOCAL_QUORUM` | How many replicas per DC? What consistency do reads and writes use? | Does not create ACID transactions across partitions |
| Request timeout | What is the network/cluster p99? Are retries enabled? | A timeout **does not prove** the server did not write the data |
| Cassandra TTL | How long must the data be retained? | TTL is not operation latency |
| Idempotent execution flag | Is the statement safe for driver retries? | Setting the flag does not make every INSERT/UPDATE business-idempotent |

Conceptual diagram (not a specification of every consistency level):

~~~mermaid
flowchart LR
    C["Client sends write CL=LOCAL_QUORUM"] --> K["Coordinator"]
    K --> R1[("Replica 1")]
    K --> R2[("Replica 2")]
    K --> R3[("Replica 3")]
    R1 --> K
    R2 --> K
    K --> A["Return success once enough replicas acknowledge"]
~~~

In a three-replica model within one local DC, `LOCAL_QUORUM` typically requires two replicas to respond. If the architecture is multi-DC with different distribution and replication, recalculate based on actual topology. `CL=QUORUM/LOCAL_QUORUM` does not replace analyzing conflict resolution, timestamps, or event ordering.

### 10.3. Conditional operations: `IF NOT EXISTS`

When you need to **create a record only once** per primary key, you can use CQL:

~~~sql
INSERT INTO order_event (
    event_id, order_id, event_type, occurred_at, payload_json
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

This is a Cassandra **lightweight transaction (LWT)**, unlike general SQL `BEGIN/COMMIT`. The operation can return `[applied]` information; read the result via a gateway/driver to know whether the statement actually applied or a row already existed.

LWT incurs higher coordination cost and latency than regular writes. Do not enable it for every event just because of the word "transaction"; if the use case only needs the same `eventId` to rewrite the **same immutable content**, an upsert with a stable primary key is often the better design once business semantics are properly evaluated.

## 11. When the source is JMS/Kafka: why are idempotent writes needed?

An integration flow might look like:

~~~mermaid
flowchart LR
    A[("JMS or Kafka")] --> B["Inbound adapter"]
    B --> C["Validate and transform"]
    C --> D["Cassandra outbound adapter"]
    D --> E[("Cassandra order_event")]
    B -. "Ack/offset commit belongs to source" .-> A
~~~

**The message source and Cassandra are two systems with separate transactions/acknowledgments.** Enabling transacted JMS sessions, Kafka manual acknowledgment, or `async(false)` on the handler does not form an atomic distributed transaction between the source and Cassandra.

### 11.1. Two failure windows

| Sequence | Risk | Mitigation design |
|---|---|---|
| **Cassandra write completes → app crashes → JMS ack/Kafka offset uncommitted** | Source may redeliver the same event | Use a stable `eventId` primary key and idempotent operations |
| **Source acks/commits → async Cassandra write fails** | Source may not redeliver; event is lost | Choose the right acknowledgment boundary or durable handoff |
| **Cassandra times out but actually wrote** | Retry sends another operation | Upsert immutable data or LWT/guard per contract |
| **Event v2 processed before v1** | State record may regress | Versioning, partition-key ordering, or conditional writes |

If you use a `JMS message-driven inbound adapter` with `DirectChannel` and a synchronous `async(false)` Cassandra handler, certain synchronous exceptions can propagate to the JMS listener to roll back the message. This **helps**, yet does not provide a two-resource atomic commit; a Cassandra write that already happened can still be replayed if the JMS commit fails.

If you switch to an `ExecutorChannel` or the default async Cassandra handler, the JMS listener may finish/commit before the real Cassandra write completes. Later DB errors then **cannot automatically roll back the source JMS message**. You must design separate retry and durable handoff mechanisms, or adjust the boundary so the source only acks after completion when the infrastructure supports it.

### 11.2. Event contract deduplication

A JSON contract may contain:

~~~json
{
  "eventId": "evt-1501",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "orderId": "ORD-1501",
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

Practices:

1. Validate the schema, required fields, and producer permissions.
2. Keep `eventId` **unchanged** across retries/redeliveries/replays.
3. Use `eventId` as the partition key in the **immutable event store** table as shown in the example.
4. Ensure the same `eventId` does not arrive with unexpectedly altered content; if a conflict occurs, flag a contract error.
5. For an **orderId-based state** table, consider `aggregateVersion` or conditional updates to prevent state regression.

A "data-idempotent" write and a "driver-level idempotent" operation are two different criteria. For instance, incrementing a counter `value = value + 1` is generally **unsafe for blind retries**, even with the same event ID in the payload. Always evaluate the actual CQL effect.

## 12. Backpressure, concurrency, and batching under high load

### 12.1. Reactive does not mean infinite capacity

Because it uses `ReactiveCassandraOperations`, the Cassandra handler can perform I/O via reactive execution. However, if producers push into a `DirectChannel` faster than Cassandra responds and the handler is async, the number of in-flight operations can exceed driver/cluster limits.

Questions to answer before increasing concurrency:

- How many writes/s can Cassandra currently sustain at p95/p99?
- How many coordinators/replicas does the cluster have? Is a single partition key hot?
- How large is each event/JSON payload? Is there TTL/tombstone pressure?
- Are buffers and `maxConcurrency` bounded in the reactive pipeline?
- How much extra load will retries add when the cluster is degraded?
- On shutdown, are in-flight operations drained or is replay from the source acceptable?

### 12.2. Batching is not a default speedup tool

Cassandra batches serve atomicity/ordering of related mutations (especially within the same partition), whereas **multi-partition logged batches** can be expensive. Do not put 100,000 events into one `List<OrderEvent>` expecting a single handler to write faster than 100,000 distributed and rate-controlled writes.

Safe practices:

1. Choose small chunks bounded by both record count and byte size.
2. Prefer grouping operations by partition when business requirements allow.
3. Monitor JVM GC/heap, blocked threads under `async(false)`, and in-flight count under `async(true)`.
4. Measure p95/timeouts and load distribution across nodes before and after tuning batches.
5. Reduce concurrency and increase backoff when Cassandra reports overload/unavailable; avoid creating a retry storm.

### 12.3. When to use synchronous channels?

| Channel in flow | Benefit | Risk |
|---|---|---|
| `DirectChannel` + sync Cassandra handler | Operation errors propagate easily to synchronous callers | Caller thread can be blocked by DB |
| `ExecutorChannel` + sync handler | Decouples upstream threads | Downstream errors can occur after source ack |
| `FluxMessageChannel` + reactive handler/gateway | Fits Reactive Streams pipelines | Requires managing subscription, backpressure, and async errors |
| In-memory `QueueChannel` | Reduces temporal coupling inside the JVM | Queue is not durable across crashes without a persistent message store |

If the application requires that **every received JMS event is either persisted to Cassandra or redelivered by the broker**, choose a strategy with a clear acknowledgment boundary and test crashes; do not select a channel solely based on normal-condition throughput benchmarks.

## 13. Common errors and troubleshooting

| Symptom | Possible cause | Diagnosis and fix |
|---|---|---|
| `ReactiveCassandraOperations` bean not found | Missing reactive dependency, auto-configuration not triggered, bad connection config | Verify starters/beans and driver configuration |
| Application startup keyspace error | `keyspace-name` not created yet or user lacks permissions | Provision keyspace/schema upfront and grant appropriate ACLs |
| Cannot connect to Cassandra | Wrong `local-datacenter`, contact-points, port, TLS, or credentials | Inspect driver logs and cluster metadata |
| CQL table does not exist | Schema not applied or session points to wrong keyspace | Check keyspace, `DESCRIBE TABLE`, and migrations |
| `String` JSON not written in `INSERT` mode | Handler expects an entity mapped with `@Table` | Add a JSON → entity transformer or use an appropriate statement mode |
| `Instant`/codec mapping error | Java type and CQL column type mismatch | Check mappings, annotations, and driver codecs |
| `send()` succeeds but no row exists | Async handler, completion errors unobserved, wrong keyspace | Check async mode, error handling, trace the operation, and CQL SELECT by key |
| An event's content changes after retry | Cassandra INSERT upserts; duplicate key with different payload | Keep events immutable, check conflicts, or use conditional writes |
| `SELECT` by `order_id` fails or is very slow | Table only has `event_id` as partition key | Design tables around query patterns; do not rely on `ALLOW FILTERING` |
| Bulk write is slower than single writes | Batch too large, multi-partition, coordinator bottleneck | Split into chunks, reduce concurrency, try unlogged/partition-aware where appropriate |
| Timeouts/retries cause load spikes | Overlapping driver/app/source retries | Set a retry budget, exponential backoff, and monitor in-flight requests |
| Data with TTL disappears | `WriteOptions.ttl` or CQL TTL set too short | Check retention policies, expired cells, and compaction |
| `IF NOT EXISTS` does not report applied | LWT result not read on a one-way adapter | Use a gateway/driver to inspect `[applied]` |
| Cassandra cluster has a hot partition | Partition key not distributed evenly | Redesign key/distribution based on workload |
| DB error does not trigger JMS redelivery | Async channel or error swallowed by error flow | Inspect thread/ack boundaries; use durable handoff or sync handling |

### Classifying exceptions before retrying

**Potentially transient:** interrupted connections, brief cluster unavailability, overload with backoff, request timeouts with unknown outcome.

**Usually does not improve on blind retry:** invalid CQL syntax, missing keyspace/table, access denied, invalid entity mapping/codec, contract-violating data.

Do not retry permanent errors indefinitely. For invalid data, quarantine it along with the `eventId` and failure reason; for transient infrastructure issues, retry with limits and monitoring. With JMS/Kafka events, the source system may redeliver independently, so avoid multiplying **application retries × broker retries** into an error storm.

### Minimum observability

| Metric | Reason |
|---|---|
| Inbound messages/s | Understand incoming flow volume |
| Cassandra writes/s succeeded/failed | Know whether the adapter is actually writing |
| Write latency p50/p95/p99 | Detect high load and slow replicas |
| In-flight reactive operations | Detect missing concurrency limits |
| Timeout/Unavailable/Overloaded errors | Classify cluster and network errors |
| Retry count & elapsed time | Prevent retry storms and measure total latency |
| Cassandra coordinator/node metrics | Detect hot partitions/GC/compaction/timeouts |
| Source JMS queue depth/Kafka lag | Check upstream backpressure |
| Duplicate eventId/conflicting payload count | Detect redeliveries and duplicate producers |
| TTL/expired data/tombstone warnings | Verify retention and deleted data |

Logs should include `eventId`, `operationType`, keyspace/table name, correlation/tracing ID, and exception type; do not log raw JSON containing PII, credentials, tokens, or secrets. In multi-tenant setups, the Cassandra user/role must be granted least-privilege access only to the required keyspaces/tables.

## 14. Hands-on lab: flow saving order events to Cassandra

**Environment:** local/test-container Cassandra (e.g., single node), Spring Integration 6+, Spring Data Cassandra reactive, Java 17+, table `shop_integration.order_event`. Use dummy data only; never operate against a production keyspace. You need a test consumer/producer sending entities into `cassandraOrderWrite` and a CQL query tool such as `cqlsh`.

### Part A — Initialize connection and table

1. Create the keyspace/table from section 3; verify the schema with `cqlsh`.
2. Set `spring.cassandra.contact-points`, `local-datacenter`, and `keyspace-name` to match the running cluster.
3. Start the application and verify that the `ReactiveCassandraOperations` bean is created and the driver connects.
4. On `NoHostAvailable`/connection errors, check port 9042, auth/TLS, and datacenter before editing the flow.

### Part B — INSERT entity via outbound adapter

1. Create the flow from section 4 with `Type.INSERT` and `endpoint.async(false)`.
2. Call `OrderEventPublisher.publish("evt-1501", "ORD-1501", json)`.
3. In `cqlsh`, query:

~~~sql
SELECT event_id, order_id, event_type, occurred_at
FROM shop_integration.order_event
WHERE event_id = 'evt-1501';
~~~

4. Verify the row matches the entity and `occurred_at` is stored as a timestamp.
5. Send the same `eventId` a second time and observe upsert semantics; do not mistake this for a unique-key exception.

### Part C — Payload/statement/batch

1. Replace the entity payload with a JSON `String` and observe the type/mapping error when trying `INSERT`; do not ignore the error.
2. Add a `String → OrderEvent` transformer with validation and run again.
3. Run the `statementFunction(...)` flow from section 7 with two new events; verify bind values do not rely on user-input string concatenation.
4. Run `ingestQuery(...)` with a two-row `List<List<?>>` payload and check that the rows were written.
5. Increase batch size in a controlled way (2 → 20 → 100 records) and measure latency/throughput without assuming larger batches are always better.

### Part D — Comparing sync and async

1. With `async(false)`, disconnect Cassandra and call the publisher; inspect the exception/timeout and caller-thread wait time.
2. Switch to the default `async(true)` and retry. Check when `MessageChannel.send(...)` returns and where the error surfaces.
3. Configure proper error reporting/metrics for async completion and prove errors are not lost in logging.
4. Use `Cassandra.outboundGateway(...)` to observe the operation result instead of one-way execution; distinguish gateway results from a no-reply adapter.
5. If using a Reactor pipeline, use an appropriate `FluxMessageChannel` and measure the in-flight operation count.

### Part E — Consistency, TTL, and ambiguous failures

1. Use `WriteOptions.ttl(Duration.ofDays(7))` on demo data; query and check the TTL using the appropriate CQL/tool.
2. Compare consistency settings suitable for the test cluster. On a single node, do not extrapolate the test to multi-replica/production environments.
3. Simulate a timeout after a write may have been received; resend the same `eventId`.
4. Verify the event payload is immutable across retries; if "insert only if absent" is desired, try CQL `IF NOT EXISTS` via gateway/driver and read `[applied]`.
5. Send an event with an `aggregateVersion` lower than the persisted state and verify a non-regressing strategy if required by the domain.

### Part F — JMS/Kafka source and idempotency

1. Create a JMS or Kafka test source sending `eventId=evt-1501` with the same payload twice.
2. With synchronous Cassandra outbound and `DirectChannel`, induce a Cassandra error and observe how the JMS/Kafka source handles ack/offset per its config.
3. Insert an `ExecutorChannel` or enable async, and observe when source ack/commit can happen.
4. Let the Cassandra write succeed and simulate a crash before source ack; confirm replay does not produce incorrect business data.
5. Send the same event ID with different JSON content; decide whether it is a valid duplicate or a **conflicting event** requiring quarantine rather than silently picking the later one.

### Acceptance criteria matrix

| Check | PASS when |
|---|---|
| Entity mapping | `@Table`/`@PrimaryKey` writes to the expected table/columns |
| Outbound adapter | Receives a Spring Message and runs a one-way Cassandra write |
| No-reply | No Spring reply is expected from the adapter |
| Gateway alternative | Returns a result when needed; understands `Mono<WriteResult>` vs sync completion |
| Payload contract | JSON String goes through a transformer or appropriate CQL statement |
| Cassandra upsert | Retrying the same key is not mistaken for a unique-insert exception |
| LWT | `IF NOT EXISTS` is verified via the `[applied]` result |
| Async failure | An observation/handling path exists for post-completion errors |
| Source acknowledgment | Does not ack prematurely when Cassandra write completion is required |
| Batch/capacity | No unbounded batches; p95 and in-flight counts are measured |
| Retention | TTL and keyspace replication are chosen for the target environment |

Checks for timeouts, consistency, batch performance, and source acks **must be tested against a real Cassandra cluster or test container**, and with real JMS/Kafka if proving redelivery/offset behavior. Unit tests mocking `ReactiveCassandraOperations` only verify that the flow invokes the right API; they do not prove Cassandra persisted data or validate consistency/transaction boundaries.

## 15. Self-assessment questions

1. How does the Cassandra outbound channel adapter differ from the outbound gateway regarding replies?
2. Why is `ReactiveCassandraOperations` a more important dependency than `JdbcTemplate` for this adapter?
3. What do Spring Data Cassandra use `@Table` and `@PrimaryKey` for?
4. Why doesn't a JSON `String` payload become a Cassandra entity automatically?
5. What does the asynchronous default of `CassandraMessageHandler` mean for `MessageChannel.send()`?
6. When should you explicitly configure `endpoint.async(false)`?
7. How do `Type.INSERT`, `UPDATE`, `DELETE`, and `STATEMENT` differ in payload/operation?
8. Why is Cassandra `INSERT` not equivalent to a PostgreSQL unique insert?
9. What payload shape does `ingestQuery(...)` require? Why are oversized batches dangerous?
10. Why is using bind values in `SimpleStatement` safer than concatenating CQL strings from user input?
11. How does `WriteOptions.ttl(...)` differ from JMS TTL and request timeouts?
12. How can Cassandra `IF NOT EXISTS` help prevent duplicates by key, and what are the trade-offs?
13. Why must Cassandra table design start from query patterns?
14. Why can increasing the number of consumers writing to the same partition key overload Cassandra?
15. When a Cassandra write completes but the JMS commit fails, what can happen?
16. What effect does switching from `DirectChannel` to `ExecutorChannel` have on error/ack boundaries?
17. Why must Cassandra driver retries and source broker redeliveries be balanced together?
18. Which metrics help distinguish an unavailable cluster from missing backpressure in the application?

## 16. References

- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): adapter, gateway, `CassandraMessageHandler`, reactive modes, ingest, query/statement, and XML.
- [Spring Integration API — Cassandra DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): `outboundChannelAdapter(...)` and `outboundGateway(...)`.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): `ingestQuery`, `writeOptions`, `statementFunction`, `query`, `parameter`.
- [Spring Integration API — CassandraMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.html): type/mode, handler, and operation options.
- [Spring Integration Reference — Integration Endpoints](https://docs.spring.io/spring-integration/reference/endpoint-summary.html): endpoint comparison for Cassandra outbound adapter/gateway, with no built-in Cassandra inbound adapter.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraTemplate`, subscription, exception translation, and reactive execution.
- [Spring Data Cassandra Reference — Persisting Entities](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): entity mapping, insert/update/delete, and CQL operations.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): TTL and write-level options.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, data modeling, replication, consistency, batches, and lightweight transactions.

**Key takeaway:** The Cassandra outbound channel adapter delivers a **Spring Message** from a `MessageChannel` to Apache Cassandra via `CassandraMessageHandler` and `ReactiveCassandraOperations`. Choose the right entity/mode (`INSERT`, `UPDATE`, `DELETE`, `STATEMENT`), understand the **async default**, and use an outbound gateway only when a reply is needed. Cassandra is a distributed data store with its own upsert, partitioning, consistency, and timeout semantics; to integrate safely with JMS/Kafka/HTTP, use stable event keys, bounded retries, completion observability, and acknowledgment-boundary tests rather than assuming sending a message equals successful persistence.



