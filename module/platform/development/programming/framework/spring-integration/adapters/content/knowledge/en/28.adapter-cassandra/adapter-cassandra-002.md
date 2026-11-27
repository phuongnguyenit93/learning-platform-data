# CassandraMessageHandler

## 1. Role of CassandraMessageHandler in Spring Integration

Suppose an e-commerce system receives an `OrderPaid` event over JMS. After validation, the application needs to store the event in Apache Cassandra for lookup by `eventId`. One option is writing CQL directly in every service activator, but that mixes persistence, connection management, and result handling with business logic.

`CassandraMessageHandler` is the **Spring Integration Cassandra** component responsible for receiving a **Spring Message** and executing an operation on Cassandra through **Spring Data `ReactiveCassandraOperations`**. The class resides in the package:

~~~java
org.springframework.integration.cassandra.outbound.CassandraMessageHandler
~~~

Since Spring Integration **6.0**, this class supports two usage modes:

- **Outbound channel adapter:** receives a message and executes a one-way Cassandra operation; by default it **produces no reply**.
- **Outbound gateway:** uses the same handler with reply production enabled, allowing the flow to receive query/write results.

In terms of inheritance, `CassandraMessageHandler extends AbstractReplyProducingMessageHandler`. It therefore possesses the capabilities of a reply-producing handler, yet **extending a class named ReplyProducing does not mean every configuration sends a reply**. `setProducesReply(boolean)` is the switch that distinguishes the two roles.

In the **SPRING_INTEGRATION_ADAPTERS** module, inbound/outbound adapters, gateways, pollers, and `MessageChannel` connect files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while managing message contracts, errors, and connection lifecycles. The **CassandraMessageHandler** topic of the **Adapter Cassandra** chapter dives deep into the exact seam between Spring Integration and Cassandra: payload types, CQL modes, reactive execution, results, errors, and write correctness.

### Learning objectives

After this lesson, you will be able to:

1. Explain how the handler receives `Message<?>` and interacts with `ReactiveCassandraOperations`.
2. Create the handler directly in Java and via Java DSL.
3. Choose the right `Type.INSERT`, `UPDATE`, `DELETE`, or `STATEMENT`.
4. Use entities, entity lists, an ingest matrix, parameterized CQL queries, and driver `Statement<?>`.
5. Distinguish `setAsync(false)` from the default async mode, as well as `setProducesReply(true)`.
6. Configure `WriteOptions`, propagate errors to the right boundary, and prevent duplicate processing.
7. Test the handler against a real Cassandra broker or test container instead of relying solely on mocks.

## 2. Where does the handler sit in an integration flow?

~~~mermaid
flowchart LR
    I["HTTP / JMS / Kafka / File inbound"] --> T["Transformer + Validator"]
    T --> M["Spring Message<OrderEvent>"]
    M --> C["MessageChannel"]
    C --> H["CassandraMessageHandler"]
    H --> R["ReactiveCassandraOperations"]
    R --> D["Cassandra driver / CqlSession"]
    D --> K[("Apache Cassandra cluster")]
    H -. "Only when producesReply=true" .-> O["Spring reply channel"]
~~~

| Component | Responsible for | Must not be mistaken for |
|---|---|---|
| `Spring Message<?>` | Payload and headers inside the JVM | Not a Cassandra row |
| `MessageChannel` | Delivering messages within `IntegrationFlow` | Not a durable queue by default |
| `CassandraMessageHandler` | Selecting operation, reading payload, executing reactive Cassandra, optionally replying | Not the Cassandra cluster/driver itself |
| `ReactiveCassandraOperations` | Entity mapping and executing Cassandra operations | Does not design the right partition key for your domain |
| `CqlSession`/driver | Connections, routing, request timeout, consistency, and codecs | Does not guarantee application idempotency |
| `CassandraMessageHandlerSpec` | Java DSL API for configuring the handler | Not a handler instance to invoke manually at runtime |

### How does a message pass through the handler?

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as Spring MessageChannel
    participant H as CassandraMessageHandler
    participant O as ReactiveCassandraOperations
    participant DB as Cassandra

    P->>C: Message<OrderEvent>
    C->>H: handleMessage(request)
    H->>H: Select Type + validate payload
    H->>O: insert/update/delete/execute
    O->>DB: Cassandra request
    DB-->>O: Completion / result / error
    O-->>H: Reactive signal
    alt producesReply = true
        H-->>C: Reply per async/sync mode and channel
    else producesReply = false
        H-->>H: No business reply emitted
    end
~~~

**Key point:** if the handler runs **async**, the moment `MessageChannel.send(...)` returns can differ from when Cassandra confirms the write. For JMS/Kafka sources, this difference directly affects when the source message is acknowledged or its offset committed.

## 3. Essential APIs: constructors, setters, and operation types

In Spring Integration 6.x/7.x, the public constructors are:

~~~java
new CassandraMessageHandler(ReactiveCassandraOperations operations);

new CassandraMessageHandler(
        ReactiveCassandraOperations operations,
        CassandraMessageHandler.Type queryType);
~~~

`Type` is an enum containing:

~~~java
CassandraMessageHandler.Type.INSERT
CassandraMessageHandler.Type.UPDATE
CassandraMessageHandler.Type.DELETE
CassandraMessageHandler.Type.STATEMENT
~~~

Key methods to remember:

| API | Purpose | When to use |
|---|---|---|
| `setProducesReply(boolean)` | Enable/disable handler replies | One-way adapter or gateway |
| `setAsync(boolean)` | Choose asynchronous execution vs awaiting completion | Determines completion and error boundaries |
| `setWriteOptions(WriteOptions)` | Attach options for entity write operations | INSERT/UPDATE/DELETE |
| `setIngestQuery(String)` | Configure CQL ingest; switches to INSERT mode | Payload is a matrix of value rows |
| `setQuery(String)` | Parameterized CQL, switches to STATEMENT mode | E.g., SELECT by key |
| `setParameterExpressions(Map<String, Expression>)` | Bind named parameters into the query | Only meaningful alongside `setQuery(...)` |
| `setStatementExpression(Expression)` | SpEL producing a driver `Statement<?>` | Dynamic CQL derived from the message |
| `setStatementExpressionString(String)` | String-expression variant | Direct SpEL configuration |
| `setStatementProcessor(MessageProcessor<Statement<?>>)` | Build a driver statement from the message | Custom Java logic, easy to unit test |
| `setOutputChannel(MessageChannel)` | Destination for replies | Only used when producing replies |

`setAsync(...)` and `setOutputChannel(...)` are **inherited** from base Spring Integration handler classes; they are not Cassandra driver APIs. Beyond public getters/setters, `handleRequestMessage(Message<?>)` is a **protected hook** on the base class, **not a method business code should call directly**.

### 3.1. Rule: configure before the handler starts processing

A handler is typically a singleton Spring bean. Set `Type`, query, parameter expressions, `WriteOptions`, `async`, and `producesReply` **before the endpoint begins receiving messages**. Do not mutate configuration fields of a shared handler from per-event worker threads; doing so risks race conditions and unpredictable behavior.

If an application needs multiple distinct operations (INSERT, DELETE, SELECT), the maintainable approach is **multiple statically configured handlers/endpoints** with a router/flow choosing the right endpoint. Never let an untrusted `operationType` header from a client freely swap the enum or CQL.

## 4. Preparing the environment and test data model

Examples target **Spring Integration 6+**, Java 17+, Spring Data Cassandra reactive, and Apache Cassandra. Use the Spring Boot BOM to manage compatible versions:

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

`spring-integration-cassandra` provides the handler; Spring Data reactive provides `ReactiveCassandraOperations`/`ReactiveCassandraTemplate`. Do not pass `JdbcTemplate` or imperative `CassandraTemplate` as the constructor argument.

Example Spring Boot configuration for a development Cassandra node:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: shop_integration
~~~

The datacenter name and address must match your active cluster; `datacenter1` is only an example. Production requires environment-appropriate authentication, TLS, topology, replication, and secrets management.

Create the keyspace and table using `cqlsh` on the test Cassandra broker:

~~~sql
-- SimpleStrategy/replication_factor=1 is only for a single-DC/single-node lab.
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

`event_id` is chosen as the partition key because the lab queries **by eventId**. Cassandra is not an RDBMS for arbitrary filtering by `order_id` on this table; if you need to query by order, design a separate table around that query pattern. For multi-replica/multi-DC production, do not use the single-node sample replication settings.

Java entity:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEvent(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {
}
~~~

`@Table` and `@PrimaryKey` tell Spring Data how to map the entity to CQL; the `record` represents an immutable event. Producers should send the same `eventId` across retries of the same event. **Same key does not prove unchanged data**: a normal Cassandra INSERT can upsert/overwrite if the payload differs.

## 5. Approach 1: creating CassandraMessageHandler directly as a service activator

This is a convenient way to understand the **actual handler** that Java DSL builds under the hood. In a `@Configuration` class with Spring Integration enabled:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraWriteInput")
public MessageHandler cassandraMessageHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setProducesReply(false);
    handler.setAsync(false);
    return handler;
}
~~~

Line-by-line explanation:

- The constructor receives `ReactiveCassandraOperations` connected to Cassandra, then explicitly selects `Type.INSERT`.
- `setProducesReply(false)` enforces **one-way** behavior: no response is sent to `replyChannel` or `outputChannel`. This is also the Cassandra handler's default mode.
- `setAsync(false)` tells the handler to **await the reactive operation result** via Spring Integration's synchronous mechanism, making I/O errors propagate easily back to the caller in a synchronous flow.
- `@ServiceActivator(inputChannel=...)` binds the handler to the `cassandraWriteInput` channel. Creating just a `@Bean` without registering a consumer/channel means Spring Messages will not automatically reach the handler.

### 5.1. Sending an entity to the handler

With `cassandraWriteInput` created/registered by Spring Integration:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final MessageChannel input;

    public OrderEventPublisher(
            @Qualifier("cassandraWriteInput") MessageChannel input) {
        this.input = input;
    }

    public void publish(String eventId, String orderId, String payloadJson) {
        OrderEvent event = new OrderEvent(
                eventId, orderId, "OrderPaid", payloadJson);

        boolean accepted = input.send(
                MessageBuilder.withPayload(event)
                        .setHeader("eventId", eventId)
                        .build());
        if (!accepted) {
            throw new IllegalStateException("Failed to deliver Spring Message");
        }
    }
}
~~~

The handler expects an **`OrderEvent` payload**, not raw JSON from which to synthesize an entity. The `eventId` header can be used for logging/tracing, but **does not automatically map to a Cassandra column**. Columns come from entity mapping.

Place validators before sending (non-empty `eventId`, valid `payloadJson`, allowlisted `eventType`). Never persist payloads containing tokens, passwords, or unauthorized personal data.

### 5.2. Why can't every `send()` still be treated as a business commit?

On a `DirectChannel` with an `async(false)` handler, the call stack can wait until the Cassandra operation finishes or throws an exception. However:

- Cassandra can return a **timeout** even though the cluster executed the write: the outcome is **ambiguous**, requiring idempotency on retry.
- Consistency settings only describe replica acknowledgment level, not a cross-system transaction with JMS/HTTP/Kafka.
- If the channel changes to `ExecutorChannel` or the handler reverts to its async default, the caller can see `send()` succeed before Cassandra finishes.

### 5.3. When to use the direct handler instead of DSL?

Use a direct `CassandraMessageHandler` when you need to:

- Explicitly configure several handler-specific setters.
- Create a reusable handler bean in an existing `@ServiceActivator` setup.
- Test handler parameters at the component level or integrate with XML/annotation configuration.

If the main goal is describing a read–transform–write flow of endpoints, **Java DSL is usually easier to follow**.

## 6. Approach 2: creating the handler via Java DSL

The `Cassandra.outboundChannelAdapter(operations, type)` factory builds a `CassandraMessageHandlerSpec`, configuring the handler without calling the constructor and `setProducesReply(false)` manually.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class CassandraIntegrationConfiguration {

    @Bean
    public IntegrationFlow orderEventWriteFlow(
            ReactiveCassandraOperations operations) {

        return IntegrationFlow.from("cassandraWriteInput")
                .handle(Cassandra.outboundChannelAdapter(
                                operations,
                                CassandraMessageHandler.Type.INSERT),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Inside `.handle(spec, endpoint -> ...)`:

1. `spec` defines the `CassandraMessageHandler` logic.
2. `endpoint.async(false)` configures the endpoint's async handling mode.
3. `IntegrationFlow.from("cassandraWriteInput")` defines the input channel; an application should have **one** logical consumer for the channel unless intentionally distributing steps.

**Do not register both** the `@ServiceActivator` in section 5 and the flow in section 6 on the **same input channel** and expect each event to write only once. The two examples are alternatives.

### 6.1. XML namespace creates the same handler

~~~xml
<int:channel id="cassandraWriteInput"/>

<int-cassandra:outbound-channel-adapter
        id="cassandraWriter"
        channel="cassandraWriteInput"
        cassandra-template="reactiveCassandraTemplate"
        mode="INSERT"
        async="false"/>
~~~

This is a **fragment**: it requires the `int` and `int-cassandra` namespaces and a `reactiveCassandraTemplate` bean that actually implements `ReactiveCassandraOperations`. The `cassandra-template` attribute in the namespace is a historical name and **does not mean** the handler accepts imperative `org.springframework.data.cassandra.core.CassandraTemplate`.

Define either Java DSL **or** XML for the same endpoint; avoid duplicate registrations when only one writer is wanted.

## 7. Handler modes and payload contracts

### 7.1. Four operating modes

| `Type` | Expected input | Typical Cassandra outcome | Important note |
|---|---|---|---|
| `INSERT` | `@Table` entity or `List<entity>` | Insert/upsert per mapping | Not a unique-insert by default |
| `UPDATE` | Entity or list of entities | Update per mapping | May have upsert semantics; inspect actual CQL |
| `DELETE` | Entity or list of entities | Delete/tombstone by key | Watch out for large deletes and tombstone accumulation |
| `STATEMENT` | Driver `Statement<?>`, query, or statement processor/expression | Executes custom CQL | Must bind parameters and constrain statements |

For entity modes (`INSERT`/`UPDATE`/`DELETE`), the Spring Integration Reference states that the handler expects a **`@Table`-annotated entity** in the payload. When the payload is a **list of entities**, the handler invokes the corresponding batch operation. It does not automatically convert a JSON `String` into an entity merely because field names match table columns.

~~~text
Valid:   Message<OrderEvent>        -> Type.INSERT
Valid:   Message<List<OrderEvent>>  -> Type.INSERT
Invalid: Message<String JSON>       -> Type.INSERT (not yet transformed)
Valid:   Message<Statement<?>>      -> Type.STATEMENT
~~~

### 7.2. When source data is JSON

An inbound JMS adapter often delivers a `TextMessage` body as a Spring `String` payload. Parse and validate it before sending it to Cassandra:

~~~java
// Java DSL fragment; objectMapper is an injected Jackson bean.
.transform(String.class, json -> {
    try {
        return objectMapper.readValue(json, OrderEvent.class);
    } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
        throw new IllegalArgumentException("Invalid OrderEvent JSON", ex);
    }
})
.channel("cassandraWriteInput")
~~~

Successful parsing does not mean a business-valid event. Validate `eventId`, `eventType`, schema version, authorization/tenant, and nullability rules. When mapping from an API DTO to a Cassandra entity, perform that mapping explicitly in a transformer rather than forcing the database layer to accept raw API payloads.

### 7.3. Cassandra upserts and retries

Standard CQL `INSERT` writes by primary key and has **upsert semantics**. Sending the same `event_id` twice does not automatically raise a unique constraint error like an RDBMS `INSERT`.

If the same ID carries different content, write timestamps/rules can overwrite row values. For an **event log**, keep events **immutable**: the same `eventId` must carry the same content; mismatched data is a contract violation, not a valid retry.

If you must write only when the key does not exist yet, use conditional CQL `IF NOT EXISTS` (lightweight transaction – LWT) or a dedicated idempotency design; in that case inspect `[applied]`, typically via a gateway or driver rather than a one-way adapter.

## 8. `setQuery(...)` and `setParameterExpressions(...)`

`setQuery(String)` lets the handler execute a CQL query with **named parameters**. According to Spring Integration documentation, calling this setter puts the handler into **`STATEMENT` mode**. Parameter expressions are evaluated against the **Spring Message**, not executed directly on the broker.

### 8.1. SELECT gateway via Java DSL

Example looking up an `order_event` record by `eventId`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow findOrderEventById(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraFindRequests")
            .handle(Cassandra.outboundGateway(operations)
                    .query("SELECT * FROM order_event WHERE event_id = :eventId")
                    .parameter("eventId", "payload"))
            .channel(c -> c.flux("cassandraFindResults"))
            .get();
}
~~~

The flow's input is a Spring Message carrying a `String eventId` payload. `parameter("eventId", "payload")` evaluates SpEL on the message to bind the value to the CQL parameter `:eventId`. The handler **never** builds a CQL string via string concatenation with `eventId`.

**Why use `outboundGateway`?** A SELECT needs to return results to the caller or downstream flow. `outboundChannelAdapter` uses a non-replying handler, so it executes the operation without emitting a Spring reply containing the matching row.

`FluxMessageChannel` works with reactive results without forcing the handler to block imperatively. Depending on the Spring Data API and query type, the result may be a publisher/collection or an operation-specific result object; write the consumer for the **payload type verified in integration tests**, rather than assuming every SELECT reply is a single `OrderEvent`.

### 8.2. Equivalent direct configuration

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraFindRequests")
public MessageHandler cassandraFindHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(operations);
    handler.setQuery(
            "SELECT * FROM order_event WHERE event_id = :eventId");

    SpelExpressionParser parser = new SpelExpressionParser();
    Map<String, Expression> params = Map.of(
            "eventId", parser.parseExpression("payload"));

    handler.setParameterExpressions(params);
    handler.setProducesReply(true);
    handler.setOutputChannelName("cassandraFindResults");
    return handler;
}
~~~

This example is an **alternative** to the Java DSL in section 8.1. If both listen on `cassandraFindRequests`, two service activators will compete and message distribution will differ from a single gateway.

Notes:

- `setParameterExpressions(...)` only applies when `setQuery(...)` is used. Do not attach these parameter expressions to an entity `INSERT` expecting the handler to use them.
- Expressions evaluate against message data. Missing fields, incompatible types, or invalid expressions can throw exceptions **before** a CQL operation is sent.
- Use only **allowlisted** CQL queries. Bind values do not replace validation and authorization.

### 8.3. Parameters sourced from headers

Spring Integration supports named parameters from payload or headers:

~~~java
// Fragment for an outbound gateway with a parameterized query.
.query("SELECT * FROM order_event WHERE event_id = :eventId LIMIT :limit")
.parameter("eventId", "payload")
.parameter("limit", message -> message.getHeaders().get("limit"))
~~~

The application must validate that `limit` is a positive integer within a safe cap, and ensure the query matches the table key. Never accept an unbounded `LIMIT` from external requests and load everything into memory. For specific CQL syntax, parameter binding support also depends on the driver/parser; verify against real Cassandra.

## 9. `setStatementProcessor(...)` and `statementFunction(...)`

When CQL cannot be conveniently expressed as a named query string or must be built from multiple fields, the handler supports:

- `setStatementExpression(Expression)` or `setStatementExpressionString(String)`.
- `setStatementProcessor(MessageProcessor<Statement<?>>)`.
- Java DSL `statementExpression(...)` or `statementFunction(...)`.

These configurations put the handler into **`STATEMENT` mode**. Spring Integration evaluates the expression or invokes the function to construct a `com.datastax.oss.driver.api.core.cql.Statement<?>` from the Spring Message.

### 9.1. Building a CQL statement with bind values

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow saveEventByStatement(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraStatementWrite")
            .handle(Cassandra.outboundChannelAdapter(operations)
                    .statementFunction(message -> {
                        OrderEvent event = (OrderEvent) message.getPayload();
                        return SimpleStatement.newInstance(
                                "INSERT INTO order_event "
                                + "(event_id, order_id, event_type, payload_json) "
                                + "VALUES (?, ?, ?, ?)",
                                event.eventId(),
                                event.orderId(),
                                event.eventType(),
                                event.payloadJson());
                    }),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`SimpleStatement.newInstance(query, values...)` passes **bind values** instead of concatenating CQL strings with JSON data. This is essential to prevent CQL injection via **values**. Keyspace, table, and column names generally cannot be bound as values; allow only preconfigured identifiers, never arbitrary user input.

**Difference from `INSERT` mode:** here the message still carries `OrderEvent`, yet the **statement function** decides what statement gets sent. Spring Data entity mapping is no longer the sole mechanism choosing table/column names; the handler author owns the CQL and driver codecs.

### 9.2. Passing a prebuilt driver `Statement<?>` as the payload

In `STATEMENT` mode, a message can also carry a preconstructed `Statement<?>`:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.messaging.support.MessageBuilder;

SimpleStatement statement = SimpleStatement.newInstance(
        "INSERT INTO order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "evt-2001", "ORD-2001", "OrderPaid",
        "{\"eventId\":\"evt-2001\"}");

cassandraStatementInput.send(
        MessageBuilder.withPayload(statement).build());
~~~

`cassandraStatementInput` must be an injected channel wired to a `STATEMENT`-mode handler. Do not share this channel with an `INSERT`-mode handler expecting entities, or the payload contract will break.

### 9.3. SpEL and QueryBuilder

Spring Integration documentation also allows `statementExpression(...)` with the DataStax QueryBuilder; Spring registers `QueryBuilder` as an import in the SpEL context. An example creating a SELECT statement without query parameterization:

~~~java
// Java DSL fragment: illustrates an expression returning a driver Statement.
.statementExpression("T(QueryBuilder).selectFrom('order_event').all().build()")
~~~

This is an unbounded SELECT, so it **only demonstrates the SpEL mechanism in a test environment**, never for production. For large tables, specify an explicit partition key and `LIMIT`/page size matching the contract. Destructive statements such as `TRUNCATE`/`DROP` must never be constructed from client-supplied metadata.

### 9.4. Do not mix three statement sources on one handler

| Chosen configuration | Handler expects | Must not combine with |
|---|---|---|
| `setQuery(...)` + parameter expressions | A fixed query string with bound parameters | A statement processor with a different contract |
| `setStatementProcessor(...)` | A processor building `Statement<?>` per message | A conflicting `setQuery(...)` |
| `setStatementExpression(...)` | SpEL returning `Statement<?>` | Another competing processor |
| `STATEMENT` mode, no generator | Payload already is `Statement<?>` | A plain entity unless converted to a statement |

Choose **one** CQL construction mechanism per handler endpoint. Even if the API lets setters be called sequentially, do not rely on override ordering or obscure fallbacks; design distinct endpoints and verify the actual queries in tests.

## 10. `setIngestQuery(...)`: accepting a multi-row matrix

`setIngestQuery(String)` supports writing multiple rows using a CQL ingest query with placeholders, switching the handler to **`INSERT` mode**. Unlike entity batches, **the payload must be `List<List<?>>`**: each inner list holds one row of values matching the placeholder order.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "cassandraIngestInput")
public MessageHandler cassandraIngestHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(operations);
    handler.setIngestQuery(
            "INSERT INTO order_event "
            + "(event_id, order_id, event_type, payload_json) "
            + "VALUES (?, ?, ?, ?)");
    handler.setAsync(false);
    return handler;
}
~~~

Producer constructing the payload:

~~~java
import java.util.List;
import org.springframework.messaging.support.MessageBuilder;

List<List<Object>> rows = List.of(
        List.<Object>of(
                "evt-2001", "ORD-2001", "OrderPaid",
                "{\"eventId\":\"evt-2001\"}"),
        List.<Object>of(
                "evt-2002", "ORD-2002", "OrderPaid",
                "{\"eventId\":\"evt-2002\"}")
);

cassandraIngestInput.send(
        MessageBuilder.withPayload(rows).build());
~~~

**Input checks:**

- Each row has exactly four values matching the four `?` placeholders.
- Java types have codecs compatible with the CQL column types.
- Java's `List.of(...)` **disallows null**; if the domain has nullable columns, choose a structure that permits nulls and test binding.
- Do not use an unbounded ingest matrix for millions of rows: chunk, measure latency, and limit load.

**Do not confuse ingest with a multi-row ACID transaction.** Cassandra batches have partition/cluster-specific characteristics and do not turn an entire message stream into an RDBMS-style database transaction.

## 11. `setWriteOptions(...)` for entity writes

`WriteOptions` belongs to **Spring Data Cassandra**, allowing configuration of write operation attributes. Spring Integration simply passes this object to the handler; it does not by itself make Cassandra writes safe for every workload.

Example setting a 7-day TTL for **demo** data:

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;

WriteOptions options = WriteOptions.builder()
        .ttl(Duration.ofDays(7))
        .build();

CassandraMessageHandler handler = new CassandraMessageHandler(
        operations, CassandraMessageHandler.Type.INSERT);
handler.setWriteOptions(options);
handler.setAsync(false);
~~~

`operations` in this fragment is an injected `ReactiveCassandraOperations` bean. This snippet demonstrates the setter and does not replace registering the bean/endpoint on a `MessageChannel`.

Depending on the Spring Data version, `WriteOptions` may also carry consistency, timeout, TTL, and other write-level settings. **Do not configure method names unsupported by your actual version**; check the Spring Data Javadoc in your dependency tree.

### 11.1. Cassandra TTL differs from JMS/Kafka TTL

| Value | Where does it live? | Meaning |
|---|---|---|
| Cassandra `WriteOptions.ttl(...)` | Cassandra storage layer | Time-to-live of the written data/cells |
| JMS `timeToLive` | JMS producer/broker | Expiration time of a JMS message |
| Kafka retention | Kafka topic/broker | Log record retention policy |
| Driver request timeout | Cassandra client driver | Wait limit for a single request's response |
| Spring `sendTimeout` | Messaging endpoint/channel | Wait limit for sending a message on a channel |

Setting a TTL in Cassandra does **not** cause the source JMS message to expire or become acknowledged. When a Cassandra cell's TTL expires, data involves tombstones and compaction; do not treat TTL as a second-accurate synchronous deletion job.

### 11.2. Do not apply `WriteOptions` blindly to every mode

The Spring Integration DSL describes `writeOptions(...)` for `INSERT`, `UPDATE`, and `DELETE`. For prebuilt `STATEMENT` operations, configure consistency/timeout **on the driver statement or execution profile** per the respective contract; do not assume `setWriteOptions(...)` rewrites arbitrary CQL statements.

### 11.3. Consistency and acknowledgment semantics

Cassandra uses consistency levels such as `ONE`, `LOCAL_QUORUM`, `ALL`, etc., suited to the replication topology. For instance, `LOCAL_QUORUM` in a datacenter with RF=3 typically requires at least two replicas to respond; recalculate if RF/topology differs.

**Write completion** means the operation was confirmed by the driver/cluster under the configured consistency and timeout; it does not guarantee an atomic transaction across PostgreSQL, HTTP requests, JMS acknowledgments, or Kafka offsets. A timeout can still happen **after Cassandra actually wrote the data**, so retries require idempotency.

## 12. Default async mode and how the handler produces replies

According to the Spring Integration Reference, `CassandraMessageHandler` **defaults to `async=true`**. Call `setAsync(false)` to switch to synchronous mode, in which Spring Integration can `block()` the reactive `Mono` to await the operation result.

### 12.1. Execution matrix

| Handler role | Async | What the caller/flow observes |
|---|---|---|
| Adapter `producesReply=false` | `true` (default) | No reply emitted; Cassandra completion can arrive after `send()` |
| Adapter `producesReply=false` | `false` | No reply emitted, but the handler awaits the operation synchronously |
| Gateway `producesReply=true` | `true` | Reactive publisher/result depending on operation and channel |
| Gateway `producesReply=true` | `false` | Awaits result and emits a reply per the operation |

The Spring Integration Reference states that with an **async gateway**, a write result can be a `Mono<WriteResult>`; how it is consumed depends on the output channel. For true reactive processing, the documentation recommends `FluxMessageChannel`. In **sync** mode, the handler calls `Mono.block()` to retrieve the reply value.

Do not assume every `SELECT`, `INSERT`, and `DELETE` returns the exact same Java reply class. Multi-row queries can have stream/publisher semantics different from writes; test the **payload type** on the output channel and attach matching transformers/consumers.

### 12.2. Java DSL gateway to retrieve write results

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow writeEventWithResult(
        ReactiveCassandraOperations operations) {

    return IntegrationFlow.from("cassandraWriteRequests")
            .handle(Cassandra.outboundGateway(
                            operations,
                            CassandraMessageHandler.Type.INSERT),
                    endpoint -> endpoint.async(false))
            .channel("cassandraWriteResults")
            .get();
}
~~~

Input `cassandraWriteRequests` holds `OrderEvent` entities. The gateway creates a reply from the operation result. Output `cassandraWriteResults` needs an **appropriate consumer** to receive the result; naming a channel without a consumer can cause the flow not to behave as expected.

### 12.3. Direct handler with explicit replies enabled

~~~java
@Bean
@ServiceActivator(inputChannel = "cassandraWriteRequests")
public MessageHandler cassandraReplyingWriteHandler(
        ReactiveCassandraOperations operations) {

    CassandraMessageHandler handler = new CassandraMessageHandler(
            operations, CassandraMessageHandler.Type.INSERT);
    handler.setProducesReply(true);
    handler.setAsync(false);
    handler.setOutputChannelName("cassandraWriteResults");
    return handler;
}
~~~

This is an **alternative** to the gateway in section 12.2. Enabling `producesReply` without a valid reply destination (an output channel or a request `replyChannel`) makes the flow unpredictable and can trigger reply-delivery failures. In production code, define clear request/reply contracts.

### 12.4. Do not call a blocking handler on a non-blocking event loop

`setAsync(false)` is convenient for a `DirectChannel` inside an imperative thread, yet it blocks the calling thread. When a WebFlux/Reactor event loop invokes the handler and the endpoint calls `Mono.block()`, the application can throw errors or suffer severe throughput degradation. For reactive pipelines, design the entire flow reactively with proper subscribers, backpressure, explicit retry/error strategies, and an appropriate `FluxMessageChannel`.

**Reactive does not mean infinite concurrency.** If inputs arrive faster than Cassandra can process them, in-flight requests can grow and overload the driver/cluster; bound concurrency, track p95/p99, and avoid unbounded buffering.

## 13. Exceptions, error channels, and transaction boundaries

A Cassandra operation can fail at different stages:

1. **Before I/O:** wrong payload type, SpEL parameter evaluation failure, missing CQL bind value, misconfigured query.
2. **During I/O:** auth/permission denied, missing table, cluster unavailable, overloaded, read/write timeout.
3. **After the cluster may have written:** client timeout/connection drop leaving it uncertain whether the write applied.

### 13.1. Sync handler and DirectChannel

~~~mermaid
flowchart LR
    A["JMS listener, transacted"] --> B["DirectChannel"]
    B --> C["CassandraMessageHandler async=false"]
    C --> D[("Cassandra cluster")]
    D -->|"Synchronous exception"| E["Exception propagates back to listener"]
    E --> F["JMS rollback / redelivery per broker policy"]
~~~

In a synchronous flow, exceptions can propagate back to the JMS listener and affect rollback/ack when the container is configured accordingly. **This does not create an atomic transaction between JMS and Cassandra**: Cassandra may have already written when the JMS commit fails, causing the event to arrive again.

### 13.2. Async handler or async channel

~~~mermaid
flowchart LR
    A["JMS listener"] --> B["MessageChannel"]
    B --> C["CassandraMessageHandler async=true"]
    C -. "operation runs later" .-> D[("Cassandra cluster")]
    B --> E["JMS callback can finish"]
    E --> F["JMS commit"]
    D -. "error after commit" .-> G["Reactive error handling / monitoring"]
~~~

If an `ExecutorChannel`/`QueueChannel` switches threads or the handler runs async, some Cassandra errors happen **after the source listener has already acked/committed**. You cannot expect the original JMS message to roll back merely by declaring a downstream `errorChannel`.

### 13.3. `errorChannel` is not automatically a retry queue

Spring Integration provides `ErrorMessage`/`errorChannel` to observe and classify failures. However:

- `errorChannel` is a **Spring MessageChannel**, not a broker DLQ.
- It does not automatically provide retry/backoff or an atomic handoff back to the message source.
- With async completion, verify that errors actually reach the error path your application monitors; never assume a `try/catch` around `send()` catches every error.
- If an error handler **swallows the exception** in a transacted JMS flow, the callback can appear successful and JMS will commit even though the database never persisted the record.

### 13.4. Retrying by error category

| Error | Retry raw message? | How to handle |
|---|---|---|
| Transient cluster unavailable | Potentially | Bounded backoff, reduce concurrency, alert |
| Write timeout with uncertain outcome | Potentially, requires idempotency | Keep `eventId`, avoid duplicate side effects |
| Invalid CQL syntax / missing table | Does not help until config is fixed | Fail fast, fix schema/config |
| Wrong entity mapping/codec | Usually not | Fix contract/transformer |
| Wrong permissions/auth | Does not help before remediation | Alert, fix ACLs/secrets |
| Duplicate event with identical data | No need to redo business work | Verify and finish intentionally |
| Same `eventId` with different payload | Never automatically | Quarantine and investigate data corruption |

If a JMS source redelivers 5 times and the application retries Cassandra 3 times per callback, a single event can trigger **up to 15 write attempts**. Manage the retry budget **end-to-end** to avoid amplifying load while the cluster is unhealthy.

## 14. Connections, lifecycle, and resource limits

`CassandraMessageHandler` is a Spring Integration endpoint using an externally configured `ReactiveCassandraOperations` bean and driver/session. It does **not** create a new Cassandra cluster per message, nor should it create a new `CqlSession` inside each `handleMessage` invocation.

### 14.1. Handler lifecycle

1. **Startup:** Spring creates `ReactiveCassandraOperations` and the handler; the endpoint registers as a consumer on the input channel.
2. **Receive:** the handler uses its prepared mode/query/statement settings to process the message.
3. **Execute:** Spring Data builds the reactive operation; the handler/endpoint determines subscribe/block behavior and reply/error paths.
4. **Stop:** the endpoint can stop accepting new messages, yet you must decide how to drain in-flight reactive writes.
5. **Restart/reconnect:** the driver/session can recover connections; the message source must still have an appropriate replay/idempotency strategy if writes were interrupted.

Do not rely on calling `stop()` on the endpoint as proof that **all pending writes were committed by Cassandra**. Verify shutdown behavior with your actual driver/handler versions and deployment orchestration.

### 14.2. Sharing ReactiveCassandraOperations properly

`ReactiveCassandraOperations` is normally a configured, reused singleton bean. Do not instantiate a new template per `eventId` or client header. Settings such as contact points, local DC, auth, TLS, timeouts, and execution profiles belong to connection/driver scope, must be managed centrally, and must not leak secrets in logs.

### 14.3. Query patterns, partition keys, and hot partitions

Cassandra optimizes by **partition key**. The table `order_event(event_id PRIMARY KEY, ...)` makes sense when primary lookups use `eventId`. If a workload needs all events for an order chronologically, design a dedicated table—for example partitioned by `orderId` and clustered by timestamp/sequence—with bounded partition sizes.

A handler calling the right API but hitting the wrong partition key can still bottleneck the cluster. Do not treat `ALLOW FILTERING` as a default workaround for missing indexes/query models; it can make queries prohibitively expensive.

## 15. Security, CQL control, and correctness

### 15.1. CQL bind values do not replace authorization

`setQuery(...)` and `statementFunction(...)` use bind parameters to pass **values** safely. Nevertheless:

- Never let clients supply arbitrary table names, column names, or CQL fragments.
- Never let an `operation=DELETE` header from an untrusted source invoke a delete handler without authorization and a business contract.
- Never pass raw SQL/CQL strings from an HTTP/JMS payload directly into `SimpleStatement`.
- Use a Cassandra role with least privilege on the required keyspace/tables, not an admin role for the application.

### 15.2. Do not treat headers as verified business data

`MessageHeaders` can contain `tenantId`, `eventType`, `traceId`, etc., set by external sources. Those values **do not prove access rights** or consistency with the payload. In multi-tenant systems, services must validate sender/tenant identity before routing to an authorized Cassandra table/partition.

### 15.3. Idempotency by eventId, not by a write success flag

Consider two messages with the same `eventId` but different payloads:

~~~json
{"eventId":"evt-2001","orderId":"ORD-2001","eventType":"OrderPaid"}
~~~

~~~json
{"eventId":"evt-2001","orderId":"ORD-2001","eventType":"OrderCancelled"}
~~~

Do not treat both as a normal retry of the same event. A Cassandra upsert on `event_id` can make the final row depend on write timestamps/conflict resolution rather than business order. Use **immutable content checks**, versioning, or conditional writes depending on the design.

If storing state by `orderId` instead of an event log, enforce an `aggregateVersion` rule to prevent out-of-order events (especially during JMS/Kafka redelivery) from regressing state. Relying solely on the receiving JVM's timestamp is insufficient.

## 16. Symptom-based troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| `ReactiveCassandraOperations` bean not found | Missing reactive starter/bean or auto-config not running | Dependencies, Spring Data config, bean types |
| Handler is never invoked | Missing `@ServiceActivator` or mismatched flow/channel name | Spring Integration graph, channel subscribers |
| `MessageDeliveryException` due to no subscribers | Handler bean created without registering an endpoint | Check input channel and consumer |
| Sending JSON `String` fails on `INSERT` | Handler expects a `@Table` entity | Add a JSON-to-entity transformer |
| `query(...)` fails to bind | Missing `parameterExpressions`, bad SpEL, incompatible type | Compare `:param` names against the map and message |
| `Statement<?>` throws ClassCastException | Incompatible mode/payload | Check `Type.STATEMENT` and statement source |
| Table/keyspace error | Schema missing or session targets another keyspace | Check keyspace, migrations, `DESCRIBE TABLE` |
| `CodecNotFound` error | CQL column and Java value lack a matching codec | Compare Cassandra schema and driver codecs |
| `send()` returns true but no row appears | Async handler, late error, queried wrong key | Check completion, error channel, query by partition key |
| Data changes after retry | INSERT upserted same key with different payload | Compare event contract, enforce immutable payload |
| Query timeout/overloaded | Hot partition, oversized batch, high in-flight count | Driver/node metrics, p95/p99, active tasks |
| TTL causes data to vanish | `WriteOptions.ttl` or CQL TTL too short | Review retention policy and table TTL |
| Gateway produces no reply | Still using one-way adapter or reply channel has no consumer | Check `producesReply` and output channel |
| JMS source does not redeliver on Cassandra error | Async boundary or exception swallowed by error flow | Inspect source ack/transaction boundary |
| App shutdown drops pending work | Async operations not drained; in-memory buffers | Shutdown tests, durable sources, idempotent replay |

### Metrics to measure

| Metric | Operational meaning |
|---|---|
| Spring Message input rate | Rate of messages entering the handler |
| Cassandra writes/queries completed | Operations that genuinely completed |
| Cassandra errors by type | Timeout, unavailable, auth, syntax, mapping |
| Operation latency p50/p95/p99 | Client/cluster latency, not merely `send()` speed |
| In-flight requests | Detects unbounded concurrency |
| Retry count/elapsed time | Risk of retry storms when the cluster is degraded |
| JMS queue depth / Kafka lag | Backpressure and upstream backlog |
| Hot partition/compaction/tombstones | Data model, TTL, and delete issues |
| Duplicate/conflicting event IDs | Data quality and idempotency signals |
| Gateway reply/error rate | Verifies reply and error paths are active |

Log `eventId`, `operationType`, keyspace/table, trace/correlation ID, and exception type; avoid logging raw payloads containing PII or credentials. Do not emit CQL statements containing sensitive values at debug level in production.

## 17. Hands-on lab: verifying CassandraMessageHandler end to end

**Environment:** Java 17+, Spring Integration Cassandra, Spring Data Cassandra reactive, a Cassandra test node/container, and the `shop_integration.order_event` keyspace/table from section 4. Keep only **one endpoint subscribed to the same input channel** per test to avoid unintended duplicate writes.

### Exercise A — Direct handler bean

1. Initialize `ReactiveCassandraOperations` connected to the test cluster.
2. Create `CassandraMessageHandler(operations, Type.INSERT)`, call `setAsync(false)`, and attach `@ServiceActivator(inputChannel="cassandraWriteInput")`.
3. Send `OrderEvent("evt-2001", "ORD-2001", "OrderPaid", json)` via `MessageChannel`.
4. Verify in `cqlsh`:

~~~sql
SELECT event_id, order_id, event_type
FROM shop_integration.order_event
WHERE event_id = 'evt-2001';
~~~

5. Resend the same `eventId` and observe upsert behavior; change the payload to a different event with the same ID and explain the risk of breaking the immutability contract.

### Exercise B — Java DSL vs @ServiceActivator

1. Replace the direct handler bean with the `Cassandra.outboundChannelAdapter(...)` flow.
2. Confirm data persists identically to Exercise A using the same entity.
3. Switch mode to `UPDATE` on a separate handler; observe entity-based CQL semantics.
4. Run `DELETE` on **test data** and explain tombstones.
5. Ensure the one-way endpoint emits no Spring reply.

### Exercise C — Named query and statement processor

1. Create a gateway `SELECT ... WHERE event_id = :eventId`, binding `eventId` from the payload.
2. Send an existing ID and a non-existent ID; observe the actual payload/result type on the reply channel.
3. Send an invalid ID to verify validation and the error path.
4. Run `statementFunction(...)` using `SimpleStatement.newInstance` with bind values.
5. Pass a value containing quotes in the payload and confirm **it is treated as a value**, not concatenated into CQL syntax.

### Exercise D — Ingest matrix and batching

1. Configure `setIngestQuery("INSERT ... VALUES (?, ?, ?, ?)")`.
2. Send a two-row `List<List<Object>>` with matching types and query back each `event_id`.
3. Send a row missing one value and verify a clear error is raised.
4. Run with 2, 20, and 100 rows and compare latency/heap without assuming larger batches are faster.
5. Test a `null` field using a data structure that permits nulls instead of `List.of(...)`.

### Exercise E — Async, replies, and errors

1. With Cassandra running, compare when `send()` returns for `async(true)` vs `async(false)`.
2. Disconnect Cassandra mid-write; inspect the sync exception and async error path.
3. Run `Cassandra.outboundGateway(...)` and verify a reply appears in the flow.
4. Run an async gateway with an appropriate `FluxMessageChannel`; inspect the publisher/result and payload type.
5. Test a handler with `producesReply(true)` but no output/reply channel, then fix the configuration.

### Exercise F — JMS source, duplicates, and shutdown

1. Wire a transacted JMS inbound adapter through `DirectChannel` to a sync Cassandra handler.
2. Induce a Cassandra failure and observe JMS rollback/redelivery when the exception propagates.
3. Enable async Cassandra or insert an `ExecutorChannel`; observe that the source callback can complete before DB completion.
4. Let the Cassandra write succeed, simulate a crash before source ack, and replay `eventId`; verify event data remains immutable.
5. Stop the application with many in-flight requests and examine the drain/recovery policy.

### Completion criteria

| Check | PASS result |
|---|---|
| Handler registered | Spring Message reaches the intended `CassandraMessageHandler` |
| Entity INSERT | CQL row has the expected key and values |
| JSON contract | JSON payload is transformed/validated before the entity handler |
| Mode selection | INSERT/UPDATE/DELETE/STATEMENT each have an appropriate endpoint |
| Named parameters | `:eventId` is bound from the Spring Message, not concatenated |
| Ingest | Matrix has matching size/types without unbounded batches |
| Async vs sync | Distinct completion and error boundaries measured |
| Gateway reply | Replies emitted only when `producesReply=true` and a reply path exists |
| Failure handling | Errors are captured with appropriate retry/backoff |
| Idempotency | Retrying the same event produces no incorrect business side effects |
| Shutdown/recovery | In-flight operations are not assumed to be durably preserved automatically |

For Cassandra consistency, timeouts, batching, and gateway output, **you must run integration tests against a real Cassandra cluster or test container**. Unit tests mocking `ReactiveCassandraOperations` only verify API interaction; they prove neither Cassandra persistence nor source delivery semantics.

## 18. Self-assessment questions

1. Which Spring input type does `CassandraMessageHandler` accept, and which API does it use to talk to Cassandra?
2. Why does this class extend `AbstractReplyProducingMessageHandler` yet remain one-way by default?
3. How do the two constructors differ in their parameters?
4. Does `setProducesReply(true)` automatically create an output channel if none is configured?
5. How does the `async=true` default affect `MessageChannel.send()`?
6. When should you use `setAsync(false)`, and what is its risk on a WebFlux event loop?
7. What payload does `INSERT` mode expect, and why isn't a JSON `String` always suitable?
8. Why choose `Type.STATEMENT` instead of entity mapping?
9. How does `setQuery(...)` change the mode? When is `setParameterExpressions(...)` used?
10. How do `setStatementProcessor(...)` and `setStatementExpressionString(...)` differ in how they build statements?
11. What payload structure does `setIngestQuery(...)` require?
12. Why should unbounded batches across many partitions be avoided?
13. How does `WriteOptions.ttl(...)` differ from JMS message TTL?
14. Does Cassandra `INSERT` automatically reject duplicate-key records?
15. When a JMS source has already acked and an async Cassandra write fails, what happens?
16. Does a Cassandra timeout prove the server did not write the data?
17. Why does an idempotent event log need a stable `eventId` and an immutable payload?
18. When selecting multiple rows, why should you check the reply type and use an appropriate reactive output channel?

## 19. References

- [Spring Integration Reference — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): introduction to `CassandraMessageHandler`, adapter/gateway modes, async, operation modes, ingest, and statements.
- [Spring Integration API — CassandraMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.html): constructors, `setIngestQuery`, `setQuery`, `setStatementProcessor`, `setWriteOptions`, and `setProducesReply`.
- [Spring Integration API — CassandraMessageHandler.Type](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/outbound/CassandraMessageHandler.Type.html): INSERT/UPDATE/DELETE/STATEMENT enum.
- [Spring Integration API — CassandraMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/CassandraMessageHandlerSpec.html): Java DSL `ingestQuery`, `parameter`, `statementFunction`, `query`, and `writeOptions`.
- [Spring Integration API — Cassandra DSL Factory](https://docs.spring.io/spring-integration/api/org/springframework/integration/cassandra/dsl/Cassandra.html): `outboundChannelAdapter(...)` and `outboundGateway(...)`.
- [Spring Data Cassandra Reference — Reactive Infrastructure](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): reactive operations, subscriptions, and error handling.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): TTL and write option configuration.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/): CQL, data modeling, consistency, replication, TTL, and lightweight transactions.

**Key takeaway:** `CassandraMessageHandler` is the **Spring Message → ReactiveCassandraOperations bridge**. The handler supports **INSERT/UPDATE/DELETE/STATEMENT**, defaults to **async** and **no reply**; enable `producesReply`/gateway only when results are needed. Set the right payload contract, query parameters, and write options; manage async errors, idempotency, and source acknowledgment. A message passing through `MessageChannel` does not by itself prove Cassandra wrote successfully, especially under reactive execution or network failures.



