# Reactive MongoDB Adapters in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **blocking MongoDB** from **reactive MongoDB** across drivers, factories, `MongoOperations`/`ReactiveMongoOperations`, endpoints, and execution models.
- Understand `Publisher`, `Mono`, `Flux`, **subscriptions**, backpressure, cancellation, and the difference between constructing a publisher and actually executing a MongoDB query/write.
- Configure `ReactiveMongoDbMessageSource` via the Java DSL `MongoDb.reactiveInboundChannelAdapter(...)`, poller, splitter, and `FluxMessageChannel`.
- Explain why **a reactive inbound source returns `Message<Flux<T>>` or `Message<Mono<T>>`**, rather than `Message<List<T>>` like the blocking source.
- Configure `ReactiveMongoDbStoringMessageHandler` via `MongoDb.reactiveOutboundChannelAdapter(...)`; track the `Mono<Void>` result rather than merely checking `send()==true`.
- Choose `ReactiveMongoDatabaseFactory` or `ReactiveMongoOperations`, and configure mapping, queries, collections, tenant filters, and limits.
- Distinguish **reactive MongoDB polling** from **MongoDB change streams** and outbound request/reply gateways.
- Regulate document counts, concurrency, retries, timeouts, and error handling on reactive pipelines without breaking non-blocking execution via `block()`.
- Write tests with Reactor `StepVerifier` and a test MongoDB instance, handling empty publishers, connection errors, and unsubscribed flows.
- Design idempotency, ACK/commit, shutdown/restart, and recovery when MongoDB is one link among Kafka, JMS, AMQP, HTTP, UDP, files, or SFTP.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing integration across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while emphasizing message contracts, errors, and connection lifecycles. In this lesson, the focus is **reactive MongoDB I/O** in Spring Integration flows; non-blocking execution does not automatically create transactions or exactly-once semantics.

> Spring Integration's reactive MongoDB APIs were introduced in version **5.3**. Examples use Java 17+, Spring Boot 3.x, and compatible Spring Integration/Spring Data versions. Specifically, the `handleReactive(...)` terminal operator was introduced in Spring Integration **6.1**. When applying these examples, verify the BOM/APIs matching your project's version.

## 1. Problem: Receiving Telemetry and Saving to MongoDB Without Blocking I/O

A service receives events from HTTP or Kafka and needs to store them in MongoDB:

~~~json
{
  "_id": "evt-1001",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "sequence": 1001,
  "status": "NEW",
  "temperatureC": 26.5,
  "observedAt": "2026-11-23T02:00:00Z"
}
~~~

At the same time, a worker periodically reads `NEW` documents to forward to an analytics system. If every request holds a thread waiting for MongoDB to respond, resources can exhaust under load; the reactive driver models I/O as publishers consumed on subscription.

~~~mermaid
flowchart LR
    A["HTTP / Kafka / AMQP"] --> M["MessageChannel"]
    M --> F["FluxMessageChannel"]
    F --> W["ReactiveMongoDbStoringMessageHandler"]
    W -->|"subscribe write Mono"| DB[("MongoDB")]
    P["Poller"] --> S["ReactiveMongoDbMessageSource"]
    S -->|"Message<Flux<T>>"| SP["Splitter"]
    SP --> C["FluxMessageChannel"]
    C --> H["Reactive handler"]
    DB -.->|"reactive query"| S
~~~

Three milestones must be separated:

1. **Spring Message accepted** on the channel.
2. **MongoDB publisher subscribed and completed** per driver result.
3. **Business state committed** and upstream ACKed per contract.

Milestone 1 does not prove milestone 2; milestone 2 likewise does not prove that a Kafka offset, JMS ACK, HTTP response, or file/SFTP state has completed.

## 2. Mono, Flux, Publisher, and Subscription

| Concept | Meaning | Note |
|---|---|---|
| `Publisher<T>` | Reactive Streams data source | Does not necessarily perform I/O before subscription |
| `Mono<T>` | Zero or one value | `Mono.empty()` differs from a Message with a null payload |
| `Flux<T>` | Zero, one, or many values | `Flux` is not an already-materialized `List` |
| `Subscription` | Registration, demand, and cancellation | The subscriber decides when the stream starts |
| `onNext` | An emitted element | Does not prove downstream committed |
| `onComplete` | Stream ended normally | For a write `Mono`, signals operation completion per contract |
| `onError` | Stream failed | May occur only after subscription |
| Backpressure | Downstream demand | Does not replace query limits, pool caps, or concurrency limits |

### 2.1. A MongoDB Publisher Is Usually Cold

~~~java
Flux<TelemetryEvent> pending =
    reactiveMongoOperations.find(
        Query.query(Criteria.where("status").is("NEW")),
        TelemetryEvent.class,
        "telemetry_events");
~~~

Creating `pending` **is not enough to claim the database was queried**. Only a subscriber or a subscribed reactive `IntegrationFlow` triggers the MongoDB operation.

~~~java
// Illustrates how a subscriber receives signals;
// in production, let the framework manage subscriptions.
pending.subscribe(
    record -> System.out.println(record.id()),
    error -> System.err.println(error.getMessage()));
~~~

**Never call `subscribe()` arbitrarily inside a business handler** if the caller needs to know whether the write succeeded/failed or needs clean shutdown control. Instead, **return the publisher** so the framework composes it into the pipeline and manages terminal signals.

### 2.2. Creating a Mono and Discarding It Writes Nothing

~~~java
// Wrong: MongoDB save may never run because the Mono is discarded.
reactiveMongoOperations.save(event, "telemetry_events");

// Right inside a method returning Mono<Void>:
return reactiveMongoOperations
        .save(event, "telemetry_events")
        .then();
~~~

Never add `block()` just to "make sure it runs" on a WebFlux/event-loop thread. Connect the pipeline to a real subscriber and use `StepVerifier` in tests.

### 2.3. Non-Blocking Does Not Mean Infinite Parallelism

Reactive MongoDB avoids blocking threads while waiting on sockets, yet the MongoDB server, client connection pool, network, throughput, data sizes, and CPU remain finite. Using unbounded `flatMap` writes or unbounded `onBackpressureBuffer` can still OOM the app or overload the database.

## 3. Classes and APIs: Blocking vs. Reactive

| Role | Blocking | Reactive |
|---|---|---|
| Java driver | `mongodb-driver-sync` | `mongodb-driver-reactivestreams` |
| Database factory | `MongoDatabaseFactory` | **`ReactiveMongoDatabaseFactory`** |
| Spring Data template | `MongoTemplate` | **`ReactiveMongoTemplate`** |
| Operations interface | `MongoOperations` | **`ReactiveMongoOperations`** |
| Query multiple documents | `List<T> find(...)` | **`Flux<T> find(...)`** |
| Query single document | `T findOne(...)` | **`Mono<T> findOne(...)`** |
| Save | Synchronous return/exception | **`Mono<T> save(...)`** |
| Spring Integration source | `MongoDbMessageSource` | **`ReactiveMongoDbMessageSource`** |
| Spring Integration writer | `MongoDbStoringMessageHandler` | **`ReactiveMongoDbStoringMessageHandler`** |
| Default inbound Message payload | `List<T>` | **`Flux<T>`** |
| Single-result inbound Message payload | `T` | **`Mono<T>`** |
| Reactive-aware MessageChannel | — | **`FluxMessageChannel`** |

Basic imports:

~~~java
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`ReactiveMongoDatabaseFactory` lives in package `org.springframework.data.mongodb`; do not confuse it with `ReactiveMongoTemplate`'s package. **Reactive adapters do not accept blocking `MongoOperations`**.

## 4. Installing Dependencies and Configuring the Connection

### 4.1. Maven — Spring Boot 3.x

~~~xml
<!-- Place inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

In applications **not using starters**, you need the reactive MongoDB driver `org.mongodb:mongodb-driver-reactivestreams` and compatible Spring Data MongoDB versions. Never mix driver/Integration/Data major versions without checking the BOM.

### 4.2. Lab MongoDB

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/reactive_adapter_lab
~~~

A local URI without credentials is **for labs only**. Production requires secrets/TLS, least-privilege roles, and proper pools/timeouts. If Boot auto-configuration already creates `ReactiveMongoOperations`, **inject that bean**; never create a separate `MongoClient` per request.

### 4.3. Manual Configuration — Alternative to Spring Boot Auto-Config

~~~java
package example.reactivemongo;

import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.SimpleReactiveMongoDatabaseFactory;

@Configuration
public class ManualReactiveMongoConfiguration {

    @Bean(destroyMethod = "close")
    public MongoClient reactiveMongoClient() {
        return MongoClients.create(
                "mongodb://127.0.0.1:27017");
    }

    @Bean
    public ReactiveMongoDatabaseFactory reactiveMongoFactory(
            MongoClient reactiveMongoClient) {
        return new SimpleReactiveMongoDatabaseFactory(
                reactiveMongoClient, "reactive_adapter_lab");
    }

    @Bean
    public ReactiveMongoTemplate reactiveMongoTemplate(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTemplate(factory);
    }
}
~~~

This manual approach **replaces** Boot auto-configuration in a separate lab/profile. Never run both configurations together and cause bean ambiguity; `MongoClient` is a singleton managed and closed by Spring on shutdown. Collections reside in the factory's selected database; `collectionName("...")` **does not switch databases**.

## 5. Entity Contract and Sample Data

~~~java
package example.reactivemongo;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        String status,
        Instant observedAt) {
}
~~~

In `mongosh` on the lab database:

~~~javascript
use reactive_adapter_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-1001",
    tenantId: "tenant-a",
    deviceId: "node-7",
    sequence: 1001,
    temperatureC: NumberDecimal("26.5"),
    status: "NEW",
    observedAt: ISODate("2026-11-23T02:00:00Z")
  },
  {
    _id: "evt-1002",
    tenantId: "tenant-a",
    deviceId: "node-8",
    sequence: 1002,
    temperatureC: NumberDecimal("25.8"),
    status: "NEW",
    observedAt: ISODate("2026-11-23T02:00:01Z")
  },
  {
    _id: "evt-1003",
    tenantId: "tenant-b",
    deviceId: "node-7",
    sequence: 1003,
    temperatureC: NumberDecimal("29.1"),
    status: "DONE",
    observedAt: ISODate("2026-11-23T02:00:02Z")
  }
])
~~~

A second seed run with the same `_id`s will throw duplicate-key errors. Never run against production. Verify entity mapping of Decimal128, `Instant`, `@Id`, and required fields against a **real test MongoDB**.

### 5.1. Validating Before Writing

~~~java
package example.reactivemongo;

public final class TelemetryValidator {

    public void validate(TelemetryEvent event) {
        if (event == null
                || event.id() == null || event.id().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || event.sequence() < 0
                || event.temperatureC() == null
                || event.observedAt() == null) {
            throw new IllegalArgumentException("Invalid telemetry");
        }
    }
}
~~~

Validation here is synchronous and lightweight, runnable before constructing the `Mono`. Production also needs schema/version contracts, tenant authorization, data bounds, and event IDs stable across retries.

## 6. Reactive Inbound Source: Message Containing a Publisher

Main class:

~~~java
org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource
~~~

It is a `MessageSource<Publisher<?>>`: **the poller calls `receive()`, while the MongoDB query executes when the payload publisher is subscribed to**.

| Mode | Spring Data API | Message payload after `receive()` |
|---|---|---|
| `expectSingleResult(false)` — default | `ReactiveMongoOperations.find(...)` | **`Flux<TelemetryEvent>`** |
| `expectSingleResult(true)` | `ReactiveMongoOperations.findOne(...)` | **`Mono<TelemetryEvent>`** |

### 6.1. A Poll Creates a Publisher Before Results Arrive

~~~text
Poll #1
  -> source.receive()
  -> Message<Flux<TelemetryEvent>>
  -> split / FluxMessageChannel / subscriber
  -> ReactiveMongoOperations.find(query)
  -> onNext(evt-1001), onNext(evt-1002)
  -> onComplete
~~~

**Do not cast `message.getPayload()` to `List` or `TelemetryEvent` immediately when the source returns a message.** When a query matches no data, a `Flux` is still created and **completes empty** upon subscription—unlike the blocking source, which returns `null` when `find` returns an empty list.

A `Mono<T>` matching no document likewise signals `onComplete` with no `onNext`. It never becomes a Spring Message with a `null` payload.

### 6.2. Source Headers

The inbound source may attach `MongoHeaders.COLLECTION_NAME` indicating the queried collection. This is Spring Integration metadata, not a BSON field on each document. When the splitter produces child messages, **test actual header behavior** if used for routing/tracing.

## 7. Java DSL Reactive Inbound: Poller + Splitter + FluxMessageChannel

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
@EnableIntegration
public class ReactiveMongoInboundConfig {

    @Bean
    public IntegrationFlow reactiveMongoInboundFlow(
            ReactiveMongoOperations mongo) {

        return IntegrationFlow.from(
                MongoDb.reactiveInboundChannelAdapter(
                        mongo,
                        "{ 'tenantId':'tenant-a', 'status':'NEW' }")
                    .collectionName("telemetry_events")
                    .entityClass(TelemetryEvent.class)
                    .expectSingleResult(false),
                e -> e.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel(c -> c.flux("reactiveMongoEvents"))
            .get();
    }
}
~~~

Explanation:

1. `reactiveInboundChannelAdapter(...)` creates the reactive MongoDB message source.
2. A poller is **still required** to trigger `receive()`: this source is not a change stream.
3. `expectSingleResult(false)` emits `Message<Flux<TelemetryEvent>>`.
4. `split()` consumes the `Publisher` and emits messages containing individual `TelemetryEvent`s.
5. `FluxMessageChannel` participates in reactive composition and propagates downstream demand.
6. **A consumer/subscriber on `reactiveMongoEvents` is required**; declaring the channel alone does not prove the DB query was subscribed to.
7. `status=NEW` is not modified by `find` alone; subsequent polls can **re-emit the same documents**.

### 7.1. Single Result

~~~java
MongoDb.reactiveInboundChannelAdapter(
        mongo,
        "{ 'status':'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(true);
~~~

This is an **alternative builder**. The source payload will be `Mono<TelemetryEvent>`; a splitter can unwrap at most one element. `findOne` does not pick "oldest" without a sort and does not create an atomic claim.

### 7.2. maxMessagesPerPoll Differs from Query Limit

~~~text
Pollers.fixedDelay(5000)
    -> when the poll task triggers

maxMessagesPerPoll(1)
    -> at most one receive() call per poll

Query.limit(50)
    -> at most 50 MongoDB documents in the query

FluxMessageChannel demand
    -> regulates emission demand via subscriber
~~~

A single `Message<Flux<T>>` can hold a publisher emitting 50, 500, or thousands of documents once subscribed. Always combine `Query.limit`, projections, indexes, and bounded downstream capacity.

## 8. Downstream Must Subscribe: Terminal Reactive Handler

Since Spring Integration **6.1**, you can place `handleReactive(...)` at the end of a flow:

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
public class ReactiveMongoProcessConfig {

    @Bean
    public IntegrationFlow readAndProcess(
            ReactiveMongoOperations mongo,
            TelemetryReactiveProcessor processor) {

        return IntegrationFlow.from(
                MongoDb.reactiveInboundChannelAdapter(
                        mongo, "{ 'status':'NEW' }")
                    .collectionName("telemetry_events")
                    .entityClass(TelemetryEvent.class),
                e -> e.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel(c -> c.flux("reactiveProcessEvents"))
            .handleReactive(message ->
                processor.process(
                    (TelemetryEvent) message.getPayload()))
            .get();
    }
}
~~~

Example processor returning `Mono<Void>`:

~~~java
package example.reactivemongo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class TelemetryReactiveProcessor {

    public Mono<Void> process(TelemetryEvent event) {
        return Mono.fromRunnable(() ->
            System.out.println("Observed " + event.id()));
    }
}
~~~

**This flow replaces section 7**; do not enable both pollers querying `NEW` in the same lab unless studying duplicate reads. `Mono.fromRunnable` only indicates logging completed when the publisher finishes, **not** a Kafka/DB/HTTP downstream commit. Replace it with a real reactive client publisher and define ACKs per contract.

If your Spring Integration version is older than 6.1, use `ReactiveMessageHandler`/spec in a flow with `FluxMessageChannel` per that version's API; do not switch to a blocking `@ServiceActivator` assuming the pipeline remains fully backpressure-aware.

## 9. The Fire-and-Forget Mistake in Reactive Handlers

**Avoid:**

~~~java
public void handle(TelemetryEvent event) {
    reactiveMongoOperations.save(event).subscribe();
    // Method returns before knowing whether save succeeded/failed.
}
~~~

This breaks the link between business ACK and MongoDB completion, makes shutdown subscription cancellation hard, and hides errors in uncoordinated logs.

**Return the publisher instead:**

~~~java
public Mono<Void> handle(TelemetryEvent event) {
    return reactiveMongoOperations
            .save(event, "telemetry_events")
            .then();
}
~~~

The caller/framework must compose or subscribe to this `Mono`. **Never call `block()` on a Reactor event loop** to force synchronous execution. Only isolate unavoidable legacy blocking calls onto a bounded scheduler (like `boundedElastic`) if no reactive API exists.

## 10. Reactive Outbound Channel Adapter: One-Way MongoDB Writer

Main class:

~~~java
org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler
~~~

It is a `ReactiveMessageHandler`: when invoked with a `Message<?>`, the handler builds the write operation and returns a **`Mono<Void>`**. With `FluxMessageChannel`, Spring Integration composes it into `ReactiveStreamsConsumer` so the subscriber awaits completion and handles `onError`.

The DSL offers two options:

~~~java
MongoDb.reactiveOutboundChannelAdapter(reactiveMongoOperations);

MongoDb.reactiveOutboundChannelAdapter(reactiveMongoDatabaseFactory);
~~~

Never use `MongoDb.outboundGateway(mongoOperations)` as a reactive writer substitute: that is a **blocking request/reply query gateway** with a different contract.

### 10.1. Java DSL with FluxMessageChannel

~~~java
package example.reactivemongo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Configuration
@EnableIntegration
public class ReactiveMongoOutboundConfig {

    @Bean
    public IntegrationFlow reactiveMongoOutbound(
            ReactiveMongoOperations mongo) {

        return IntegrationFlow.from("toReactiveMongo")
                .channel(MessageChannels.flux())
                .handle(
                    MongoDb.reactiveOutboundChannelAdapter(mongo)
                        .collectionName("telemetry_events"))
                .get();
    }
}
~~~

- `toReactiveMongo` is the flow's input channel (created by the DSL if no bean with that name exists).
- Placing a reactive channel before the writer lets the framework compose `Mono<Void>`.
- The writer persists the **message payload**, not all Spring headers automatically into BSON.
- `collectionName("telemetry_events")` chooses a static collection in `MongoOperations`'s database.
- The adapter **does not emit a reply with the saved document** like an outbound gateway.
- An upstream producer must send validated `Message<TelemetryEvent>` instances to `toReactiveMongo`.
- `MessageChannel.send()==true` may only reflect channel-level acceptance, **not that the MongoDB write finished**.

### 10.2. How Does a Reactive Handler Behave on a DirectChannel?

Without reactive stream composition (e.g., placing a reactive handler in an imperative flow with `DirectChannel`), Spring Integration can use `ReactiveMessageHandlerAdapter` to **subscribe immediately** to `Mono<Void>`.

While this executes the operation, **it does not provide end-to-end backpressure** like a `FluxMessageChannel` flow. Likewise, the `send` caller should not equate dispatch success with MongoDB commit; check your architecture's exact endpoint/caller contract.

### 10.3. Instantiating the Handler Class Directly

~~~java
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;

ReactiveMongoDbStoringMessageHandler writer =
        new ReactiveMongoDbStoringMessageHandler(
                reactiveMongoOperations);

writer.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

This is a **fragment** creating the handler, not a full `IntegrationFlow`. Factory option:

~~~java
ReactiveMongoDbStoringMessageHandler writer =
        new ReactiveMongoDbStoringMessageHandler(
                reactiveMongoDatabaseFactory);

writer.setMongoConverter(mongoConverter);
writer.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

`setMongoConverter(...)` is only appropriate per API when constructed with **`ReactiveMongoDatabaseFactory`**; never use this setter expecting to swap the converter inside an already-built `ReactiveMongoOperations`.

## 11. MongoDB save Is Neither Insert-Only Nor a Partial Update

The reactive storing handler persists payloads using Spring Data MongoDB's `save` semantics. Other business behaviors require different handlers/services.

| Operation | ReactiveMongoOperations example | Characteristics |
|---|---|---|
| **save** | `save(entity, collection)` | Inserts if new or writes by ID, potentially replacing document |
| **insert** | `insert(entity, collection)` | Create-only; duplicate ID throws error |
| **updateFirst** | `updateFirst(query, update, ...)` | Patches specific fields when query matches |
| **upsert** | `upsert(query, update, ...)` | Updates or inserts conditionally |
| **findAndModify** | `findAndModify(query, update, ...)` | Atomic conditional update on one document |
| **Outbound adapter** | `ReactiveMongoDbStoringMessageHandler` | One-way writer using `save` semantics |

### 11.1. Saving with the Same ID Does Not Mean Exactly-Once

If event `evt-1001` is written and Kafka redelivers the same ID:

- `save` may not create a second document.
- Yet it can overwrite newer field changes in MongoDB.
- If events must be immutable, consider `insert` and unique keys.
- When transitioning `PROCESSING → DONE`, use conditional updates with owner/version checks.
- With `@Version`, understand optimistic locking and version conflict behavior in `ReactiveMongoTemplate`.

A timeout after writing can leave an **ambiguous outcome**: the server may have committed even though the client received `onError`. On retry, keep the same business ID and reconcile state rather than generating a new random event ID.

### 11.2. Reactive Partial Update

Example service updating status only when the document is currently `PROCESSING`:

~~~java
package example.reactivemongo;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public final class CompletionRepository {

    private final ReactiveMongoOperations mongo;

    public CompletionRepository(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<Boolean> markDone(String id) {
        Query query = Query.query(
            Criteria.where("_id").is(id)
                .and("status").is("PROCESSING"));

        Update update = new Update().set("status", "DONE");

        return mongo.updateFirst(
                query, update, "telemetry_events")
            .map(result -> result.getMatchedCount() == 1);
    }
}
~~~

Add owner/version/lease checks in multi-worker systems. `matchedCount==1` does not prove Kafka/HTTP business side effects succeeded; it is solely the MongoDB operation result.

## 12. Safe Dynamic Collection Selection

The reactive writer supports `collectionNameFunction` reading the request `Message`:

~~~java
MongoDb.reactiveOutboundChannelAdapter(mongo)
    .collectionNameFunction(
        (org.springframework.messaging.Message<TelemetryEvent> message) ->
            collectionPolicy.allowedCollection(
                message.getHeaders()
                    .get("approvedDataset", String.class)));
~~~

`collectionPolicy` is an injected bean:

~~~java
package example.reactivemongo;

import org.springframework.stereotype.Component;

@Component
public class ReactiveMongoCollectionPolicy {

    public String allowedCollection(String approvedDataset) {
        if (approvedDataset == null) {
            throw new IllegalArgumentException(
                    "Missing collection category");
        }

        return switch (approvedDataset) {
            case "LIVE" -> "telemetry_events";
            case "ARCHIVE" -> "telemetry_archive";
            default -> throw new IllegalArgumentException(
                    "Unapproved MongoDB collection");
        };
    }
}
~~~

**Never let users submit raw collection names or SpEL expressions.** `approvedDataset` must be attached server-side **after authorization and message-type validation**, never copied blindly from untrusted HTTP/Kafka/UDP headers.

Collection policies do not switch the **MongoDB database**. For another database/cluster, use a distinct `ReactiveMongoOperations`/factory configured with dedicated credentials and roles.

## 13. Bounded Queries: Criteria, Sort, Fields, and Limit

Reactive Streams fetches data on demand, yet an unbounded query still pressures memory, network, and the server. Bound queries at MongoDB.

~~~java
package example.reactivemongo;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ReactiveTelemetryQueries {

    private ReactiveTelemetryQueries() {}

    public static Query newBatch(
            String authorizedTenant, int batchSize) {

        if (authorizedTenant == null
                || authorizedTenant.isBlank()
                || batchSize < 1 || batchSize > 100) {
            throw new IllegalArgumentException(
                    "Unauthorized tenant or invalid batch size");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(batchSize);

        query.fields()
            .include("_id")
            .include("tenantId")
            .include("deviceId")
            .include("sequence")
            .include("temperatureC")
            .include("status")
            .include("observedAt");

        return query;
    }
}
~~~

In the lab example:

~~~java
MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        ReactiveTelemetryQueries.newBatch("tenant-a", 50))
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false);
~~~

This is a **builder**, not a registered flow until wired into `IntegrationFlow.from(...)` with a poller. Both `(ReactiveMongoOperations, Query)` and `(ReactiveMongoDatabaseFactory, Query)` overloads are provided by the Spring Integration DSL in compatible versions.

### 13.1. Limit Differs from Demand and maxMessagesPerPoll

| Bound | Layer | Meaning |
|---|---|---|
| `maxMessagesPerPoll(1)` | Poller | Number of `receive()` calls per poll task |
| `Query.limit(50)` | MongoDB | Number of documents in one query |
| `request(n)` | Reactive Streams | Downstream demand on a publisher |
| `flatMap(..., 8)` | Reactor operator | At most 8 concurrent inner subscriptions in this operator |
| `QueueChannel(64)` | Message channel | Queue capacity in messages |
| `maxFetchSize` | Remote file adapter | Remote files fetched, not MongoDB documents |

One `Message<Flux<T>>` can emit many documents; `maxMessagesPerPoll(1)` **does not mean one document**.

### 13.2. Projections and Partial Entities

If you query only a few fields, a mapped `TelemetryEvent` may lack `temperatureC`, `status`, or `observedAt`, yielding nulls/defaults. Never pass a field-incomplete projected entity back to `save` on the full document, as it risks data loss.

Use a matching projection DTO or include all required fields when business updates are needed. `_id` is returned by default in MongoDB projections unless explicitly excluded; keep the ID when dedup/ACK is required.

### 13.3. Indexing for Filter and Sort

In `mongosh` on the test database:

~~~javascript
db.telemetry_events.createIndex({
  tenantId: 1,
  status: 1,
  observedAt: 1,
  _id: 1
})
~~~

This index can support filter + sort. Measure with `explain("executionStats")` on realistically sized data, comparing examined keys/docs and latency rather than assuming any created index is optimal.

## 14. Query/Collection Expressions in Reactive Inbound

You can construct the source with an `Expression`:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;

ReactiveMongoDbMessageSource source =
    new ReactiveMongoDbMessageSource(
        reactiveMongoOperations,
        new SpelExpressionParser().parseExpression(
            "@mongoReadPolicy.nextQuery()"));
~~~

`mongoReadPolicy` is a Spring bean returning a fresh valid `Query` on each receive. The source must be Spring-managed so SpEL resolves the bean reference. **Inbound polling has no incoming request Message**, so never use `payload.deviceId` like an outbound gateway.

The source spec also supports a collection supplier:

~~~java
MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        "{ 'status':'NEW' }")
    .collectionNameSupplier(
        () -> trustedPolicy.currentCollection())
    .entityClass(TelemetryEvent.class);
~~~

`trustedPolicy` is an injected bean choosing an allowlisted collection. If query and collection mutate independently across threads, you risk pairing a **new policy's query** with an **old policy's collection**; keep an immutable policy snapshot or serialize changes at lifecycle boundaries.

**Expressions are evaluated when the source receives**, while the reactive MongoDB operation executes upon subscription. Do not assume results reflect exact query/collection policy state at subscriber delivery time if policies can change while an operation is pending; test against the exact API and contract you use.

## 15. updateExpression and Re-Polling Documents

Since Spring Integration **5.5**, the reactive source supports `updateExpression`:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.reactiveInboundChannelAdapter(
        reactiveMongoOperations,
        "{ 'status':'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

This snippet is **an illustrative builder only**. The source can update retrieved documents so they no longer match the `NEW` query on the next poll. However:

- **`CLAIMED` does not prove downstream finished processing.**
- If the app crashes after the update but before Kafka/HTTP/JMS completion, documents can get stuck.
- Multiple instances querying `NEW` concurrently before updates can duplicate work.
- Query/find plus update does not automatically form an atomic multi-instance claim.
- If the update does not change the filtered field, subsequent polls will re-emit the same documents.
- You still need durable business event IDs, leases/owners, recovery, retries, and idempotent downstreams.

For critical work queues, consider a **custom reactive `MessageSource`** using conditional `ReactiveMongoOperations.findAndModify(...)` for atomic document claims. Design lease release/renewal, owner/version fencing, and transitioning to `DONE` only after business commit.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as MongoDB
    A->>DB: find(status=NEW)
    B->>DB: find(status=NEW)
    DB-->>A: evt-1001
    DB-->>B: evt-1001
    Note over A,B: Both may process the same event
~~~

A reactive publisher does not provide exactly-once delivery on its own. This is a **delivery and business-state problem**, not a blocking vs. non-blocking issue.

## 16. Backpressure, Concurrency, and Ordering

### 16.1. Bounded Concurrency with flatMap

In a Reactor service subscribed to by a caller:

~~~java
public Flux<TelemetryEvent> saveBatch(
        Flux<TelemetryEvent> events,
        ReactiveMongoOperations mongo) {

    return events.flatMap(
        e -> mongo.save(e, "telemetry_events"),
        8);
}
~~~

This operator runs at most 8 concurrent inner publishers, **without preserving input order**. If strict ordering is required:

~~~java
return events.concatMap(
    e -> mongo.save(e, "telemetry_events"));
~~~

`concatMap` runs sequentially, which can reduce throughput. If ordering is only needed per `deviceId`, use key/partition routing instead of serializing all events into a single queue.

### 16.2. Backpressure Does Not Replace Query Bounds

- `FluxMessageChannel` coordinates demand with subscribers.
- `Query.limit` bounds how many documents are requested from MongoDB.
- `flatMap(concurrency)` caps concurrent I/O at **that stage**, not system-wide.
- Queue sizes, prefetch, buffers, and thread schedulers still impact memory.
- Putting a blocking handler or eager `subscribe()` inside the flow can break end-to-end backpressure.

Never use `onBackpressureDrop`/`onErrorContinue` casually on order or payment data; silent message loss is usually unacceptable.

### 16.3. Do Not Call block() on the Event Loop

If a downstream step uses a blocking JDBC/SDK call, offload that specific step onto a bounded scheduler (e.g., `boundedElastic`). Prefer true reactive clients; wrapping blocking APIs in Reactor does not magically yield non-blocking scalability.

## 17. Error Handling in Reactor: onError Occurs After Subscription

Code creating a `Mono` cannot catch MongoDB network errors using a surrounding `try/catch`:

~~~java
try {
    Mono<TelemetryEvent> pending =
        reactiveMongoOperations.save(
            event, "telemetry_events");
    // No subscriber yet, so DB has not emitted onError here.
} catch (Exception ex) {
    // Wrong place to catch asynchronous I/O errors.
}
~~~

Instead, compose operators on the publisher:

~~~java
public Mono<Void> saveWithLogging(
        TelemetryEvent event,
        ReactiveMongoOperations mongo) {

    return mongo.save(event, "telemetry_events")
        .doOnSuccess(saved ->
            System.out.println("Saved id=" + saved.id()))
        .doOnError(ex ->
            System.err.println(
                "MongoDB error: "
                + ex.getClass().getSimpleName()))
        .then();
}
~~~

This only logs; `onError` still propagates. Never mistake logging for retries or dead-letter handling.

### 17.1. Bounded Retries and Error Classification

~~~java
import java.time.Duration;
import org.springframework.dao.TransientDataAccessException;
import reactor.util.retry.Retry;

public Mono<Void> saveWithRetry(
        TelemetryEvent event,
        ReactiveMongoOperations mongo) {

    return mongo.save(event, "telemetry_events")
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(ex ->
                    ex instanceof TransientDataAccessException))
        .then();
}
~~~

**This predicate is illustrative** and does not cover every driver/write-concern error. Never retry mapping, validation, or auth failures infinitely. For timeouts where MongoDB may have written already, retries require stable IDs, duplicate handling, and state reconciliation.

### 17.2. Never Mask onError with Mono.empty()

~~~java
// Dangerous if upstream ACKs on onComplete:
return mongo.save(event)
    .onErrorResume(e -> Mono.empty())
    .then();
~~~

If MongoDB is down, this turns a failure into a completion signal, causing upstream to commit early and drop the event. Any fallback must first persist durably to a retry queue/dead-letter/outbox or have an explicit loss-tolerant contract.

### 17.3. errorChannel and Reactive Streams onError

- In imperative flows, exceptions usually travel to the caller or endpoint `errorChannel`.
- In reactive flows, errors can arrive at the **subscriber's `onError`** after the `Message` was dispatched.
- Know who owns the subscription, advice, and error policy; **never assume every `onError` automatically becomes an `ErrorMessage`**.
- MongoDB `Flux.empty()` means **no documents**, whereas `Flux.error(...)` means **failure**—handle them differently in metrics and responses.
- A successful source query followed by a downstream Kafka failure is a post-query error; never misclassify it as a MongoDB read failure.

## 18. Timeouts, Cancellation, and Lifecycle

### 18.1. Different Types of Timeouts

| Layer | Example | What does it control? |
|---|---|---|
| Poller | `Pollers.fixedDelay(5000)` | When `receive()` is invoked |
| MongoDB driver | Server selection/socket timeout | How long client waits for MongoDB server/I/O |
| MongoDB query | Query max time/read preference | Query execution time and server selection policy |
| Reactor | `Mono.timeout(Duration)` | Publisher-level timeout |
| HTTP/request caller | API/gateway response timeout | When client stops waiting for response |
| Graceful shutdown | Application stop deadline | Window to complete in-flight work |

**Reactor timeout/cancellation does not prove MongoDB did not write.** The server may have committed before the response was lost or while the operation was still finishing. On ambiguous write outcomes, use stable event IDs and reconciliation rather than generating new IDs.

### 18.2. Reactive Inbound Lifecycle

~~~text
ApplicationContext start
  -> SourcePollingChannelAdapter starts
  -> Poller triggers
  -> ReactiveMongoDbMessageSource.receive()
  -> Message<Publisher<?>> created
  -> Splitter / FluxMessageChannel / downstream subscribes
  -> MongoDB query executes
  -> onNext / onComplete or onError
  -> Next poll
~~~

Key points:

- The source is a **polling source**, not a push-based MongoDB change listener.
- Without a downstream subscriber, publishers may never execute.
- On stop, cancel/stop the poller and active subscriptions per lifecycle.
- On restart, the query can see the same `NEW` documents again because **there is no automatic checkpoint**.
- `FluxMessageChannel` is not a durable queue; pending in-RAM messages are lost if the process crashes.
- With multiple instances querying `status=NEW`, use claims/leases or idempotent downstreams.

### 18.3. Shutdown for Reactive Outbound

To avoid ACKing upstream prematurely:

1. Stop accepting new messages from HTTP/Kafka/JMS/AMQP.
2. Wait for in-flight reactive `Mono<Void>` writes to reach terminal signals within a deadline.
3. Persist incomplete messages in a durable broker/outbox or keep retry state across restart.
4. Avoid hidden `subscribe()` calls in handlers that prevent framework tracking.
5. Close the Spring-managed MongoDB client cleanly.
6. After restart, resume using contract IDs/leases/checkpoints.

Never treat `cancel()` as a business transaction rollback; it is purely a subscription cancellation signal.

## 19. Reactive MongoDB Transactions

Spring Data provides `ReactiveMongoTransactionManager` for MongoDB transactions when the deployment supports them (typically a replica set or compatible sharded cluster).

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Bean
public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}

@Bean
public TransactionalOperator reactiveMongoTxOperator(
        ReactiveMongoTransactionManager txManager) {
    return TransactionalOperator.create(txManager);
}
~~~

This is a **`@Configuration` fragment**. The factory/transaction manager and operations must share the same configuration; a manager for Cluster A cannot manage operations on Cluster B.

### 19.1. TransactionalOperator in a Pipeline

Example combining two MongoDB operations in the same database/transaction:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public Mono<Void> saveAndAcknowledgeInbox(
        TelemetryEvent event,
        ReactiveMongoOperations mongo,
        TransactionalOperator tx) {

    Mono<Void> work = mongo
        .save(event, "telemetry_events")
        .then(mongo.updateFirst(
            Query.query(
                Criteria.where("_id").is(event.id())
                    .and("status").is("PROCESSING")),
            new Update().set("status", "DONE"),
            "inbox_events"))
        .flatMap(update -> {
            if (update.getMatchedCount() != 1) {
                return Mono.error(new IllegalStateException(
                    "Inbox state no longer PROCESSING"));
            }
            return Mono.empty();
        });

    return work.as(tx::transactional);
}
~~~

**Example limitations:** there is no claim owner/version/lease yet. It illustrates reactive transaction composition, not a complete work queue. You must run on a transaction-capable MongoDB topology and test failures. MongoDB transactions do not cover Kafka consumer offsets, HTTP responses, JMS ACKs, or file renames.

### 19.2. Why Outbox and Idempotency Are Still Needed

If a MongoDB transaction commits and the process crashes before ACKing Kafka, Kafka redelivers the event. If downstream received an HTTP/Kafka publish but the response was lost, retries can create duplicates. Robust solutions combine **durable inbox/outbox patterns, unique business keys, bounded retries, state reconciliation, and idempotent consumers**.

Neither reactive nor blocking APIs eliminate the distributed-transaction problem.

## 20. Reactive Inbound Polling, Change Streams, and Request/Reply

| Criterion | Reactive MongoDB polling | MongoDB change stream | MongoDB outbound gateway |
|---|---|---|---|
| Endpoint | `ReactiveMongoDbMessageSource` | `MongoDbChangeStreamMessageProducer` | `MongoDbOutboundGateway` |
| Trigger | **Poller** | MongoDB change stream subscription | Request Message |
| Data | `Flux`/`Mono` of query results | `ChangeStreamEvent`/body per config | Query reply |
| Java DSL | `reactiveInboundChannelAdapter` | `changeStreamInboundChannelAdapter` | `outboundGateway` |
| Has poller? | **Yes** | Not like query polling | No |
| When to use? | Scheduled backlog/`NEW` scanning | CDC / near-real-time changes | Per-request lookups |
| Recovery | Status/claim/lease/idempotency | Resume token / resubscribe | Caller timeouts/retries |
| Driver | Reactive | Reactive | Current API is typically blocking |

### 20.1. Change Stream Is a Separate Endpoint

Java DSL example:

~~~java
@Bean
public IntegrationFlow reactiveChangeStreamFlow(
        ReactiveMongoOperations mongo) {

    return IntegrationFlow.from(
            MongoDb.changeStreamInboundChannelAdapter(mongo)
                .collection("telemetry_events")
                .domainType(TelemetryEvent.class))
        .channel(c -> c.flux("mongoChanges"))
        .get();
}
~~~

This is a **different** flow from reactive polling, not just swapping the query on `ReactiveMongoDbMessageSource`. MongoDB change streams require supporting deployments, roles, and capabilities; the default payload may carry `ChangeStreamEvent<T>` rather than `T`. Design resume tokens, reconnects, and checkpoints per API; never assume the channel itself is durable.

### 20.2. Is There a reactiveOutboundGateway?

Spring Integration offers `MongoDbOutboundGateway` for MongoDB **request/reply queries** using blocking `MongoOperations`. The reactive MongoDB factories in the Java DSL include `reactiveInboundChannelAdapter` and `reactiveOutboundChannelAdapter`; **do not assume `MongoDb.reactiveOutboundGateway(...)` exists** unless explicitly published in your version's API.

When WebFlux needs to return `Mono<T>`/`Flux<T>` per request, create a **reactive Spring Data service** and compose its publisher into the response rather than inventing a non-existent DSL method.

~~~java
package example.reactivemongo;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactiveTelemetryLookup {

    private final ReactiveMongoOperations mongo;

    public ReactiveTelemetryLookup(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Flux<TelemetryEvent> findNew(
            String authorizedTenant, String deviceId) {

        Query query = Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                    .and("deviceId").is(deviceId)
                    .and("status").is("NEW"))
                .limit(50);

        return mongo.find(
                query, TelemetryEvent.class, "telemetry_events");
    }
}
~~~

This is a Spring Data reactive service, **not** a Spring Integration outbound gateway. If EIP routing, correlation, and true messaging request/reply are needed, design a message gateway/custom endpoint that tracks reactive completion properly.

## 21. Testing with StepVerifier and a Test MongoDB Instance

**`StepVerifier` verifies publisher signals**: `onNext`, `onComplete`, `onError`, cancellation, and data/ordering. It distinguishes "a publisher was created" from "the publisher ran and emitted expected data".

### 21.1. Integration Test for ReactiveMongoOperations

Use Testcontainers when Docker is available, or a dedicated test MongoDB. Example Spring Boot Test targeting a test database—never production:

~~~java
package example.reactivemongo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveMongoOperationsIT {

    @Autowired
    ReactiveMongoOperations mongo;

    @Test
    void savesThenReadsAndCleansUp() {
        String id = "it-" + UUID.randomUUID();

        TelemetryEvent event = new TelemetryEvent(
                id, "tenant-test", "node-test", 1L,
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-23T02:00:00Z"));

        Query byId = Query.query(Criteria.where("_id").is(id));

        Mono<TelemetryEvent> exercise =
            mongo.save(event, "telemetry_events")
                .then(mongo.findById(
                    id, TelemetryEvent.class, "telemetry_events"))
                .flatMap(readBack ->
                    mongo.remove(byId, "telemetry_events")
                        .thenReturn(readBack));

        StepVerifier.create(exercise)
            .expectNextMatches(readBack ->
                id.equals(readBack.id())
                    && "tenant-test".equals(readBack.tenantId())
                    && readBack.sequence() == 1L)
            .verifyComplete();
    }
}
~~~

This test verifies save/read/delete inside a **subscribed reactive chain**. If `save` or `findById` fails before cleanup, `flatMap` does not execute `remove`; advanced tests should use `Mono.usingWhen` or independent test teardown to clean up on failure paths too. It **does not yet test the Spring Integration flow**.

### 21.2. Testing a Reactive Source Returning a Publisher Message

In a test with seeded MongoDB data, build a standalone source **with no background poller**:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.inbound.ReactiveMongoDbMessageSource;
import org.springframework.messaging.Message;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

ReactiveMongoDbMessageSource source =
    new ReactiveMongoDbMessageSource(
        mongo,
        new LiteralExpression("{ '_id': 'evt-1001' }"));

source.setCollectionNameExpression(
    new LiteralExpression("telemetry_events"));
source.setEntityClass(TelemetryEvent.class);
source.setExpectSingleResult(false);
source.afterPropertiesSet();

Message<Publisher<?>> msg = source.receive();
assertNotNull(msg);
assertInstanceOf(Publisher.class, msg.getPayload());

StepVerifier.create(Flux.from(msg.getPayload()))
    .expectNextMatches(value ->
        value instanceof TelemetryEvent event
            && "evt-1001".equals(event.id()))
    .verifyComplete();
~~~

This is a **fragment** inside a JUnit class with `@Autowired ReactiveMongoOperations mongo` and test data, not a standalone Java test file. It verifies **post-subscription results**, not merely `receive() != null`.

### 21.3. Testing Single-Result, Empty, and Error Cases

Build a separate source with `setExpectSingleResult(true)`:

- When the document exists: `Message<Mono<TelemetryEvent>>` and subscriber receives one event.
- When missing: `Mono.empty()` completes with no `onNext`.
- When MongoDB is down or unauthorized: the publisher emits `onError`; never equate with an empty publisher.
- When a Flux query expects three documents: `StepVerifier` should assert all three IDs/tenants rather than only `thenConsumeWhile`, which passes on an empty `Flux`.

When testing `@beanName` in SpEL, provide a valid Spring `BeanFactory`/`EvaluationContext`; use `LiteralExpression` when testing core source behavior.

### 21.4. Directly Testing the Reactive Storing Handler

You can test the handler outside an `IntegrationFlow` to verify `Mono<Void>` subscription:

~~~java
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.outbound.ReactiveMongoDbStoringMessageHandler;
import org.springframework.messaging.support.MessageBuilder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

ReactiveMongoDbStoringMessageHandler handler =
    new ReactiveMongoDbStoringMessageHandler(mongo);

handler.setCollectionNameExpression(
    new LiteralExpression("telemetry_events"));
handler.afterPropertiesSet();

Mono<Void> write = handler.handleMessage(
    MessageBuilder.withPayload(event).build());

StepVerifier.create(write).verifyComplete();

StepVerifier.create(
        mongo.findById(
            event.id(), TelemetryEvent.class, "telemetry_events"))
    .expectNextMatches(saved ->
        event.id().equals(saved.id()))
    .verifyComplete();
~~~

This is a test fragment assuming `mongo` and `event` come from a test fixture with cleanup. Match your project version's `ReactiveMessageHandler` API. **Direct handler tests do not replace testing `FluxMessageChannel` wiring and consumer lifecycles.**

### 21.5. End-to-End Test Matrix

| Test case | What to assert |
|---|---|
| `Mono` created but unsubscribed | Never claim DB wrote it |
| `Flux` source with two matches | After subscription, emits both events |
| `Flux` source empty | `onComplete` with zero `onNext` |
| Single `Mono` with no data | `Mono.empty()` |
| MongoDB temporarily down | Explicit `onError`; retry/error policy works |
| Invalid collection header | Policy rejects before writing |
| `Query.limit(20)` | At most 20 documents |
| Projection omits fields | Partial entity never accidentally passed to `save` |
| `FluxMessageChannel` | Consumer actively subscribes |
| Slow/full pool | Bounded concurrency and timeouts |
| Two pollers reading `NEW` | Detects duplicates/claim race |
| Retrying same event ID | Never generates a new ID per attempt |
| `save` alters fields | Understands replacement vs. patch |
| Stop/restart | In-flight/pending recovery works |
| Business ACK | Emitted only when commit conditions hold |

**Never assert `MessageChannel.send()==true` alone** and conclude MongoDB committed. Verify the write's terminal signal or bounded readback, and separate business ACKs from DB ACKs.

## 22. Observability, Security, and Operations

### 22.1. Suggested Metrics

| Metric | What it distinguishes |
|---|---|
| `reactive_mongo_polls_total` | Source `receive` invocations |
| `reactive_mongo_publisher_created_total` | Publishers created |
| `reactive_mongo_publisher_subscribed_total` | Publishers actually subscribed to |
| `reactive_mongo_documents_emitted_total` | Documents emitted from queries |
| `reactive_mongo_query_empty_total` | Queries returning no results |
| `reactive_mongo_write_attempt_total` | Write operations started |
| `reactive_mongo_write_success_total` | Writes reaching `onComplete` |
| `reactive_mongo_write_error_total` | Writes reaching `onError` |
| `reactive_mongo_inflight_operations` | Operations awaiting terminal signal |
| `reactive_mongo_operation_latency_seconds` | End-to-end latency |
| `reactive_mongo_retry_total` | Retry count |
| `reactive_mongo_cancel_total` | Cancellations |
| `reactive_mongo_pending_depth` | Backlog depth if queued |
| `reactive_mongo_business_committed_total` | Business events fully completed |

These are **illustrative metric names**; do not assume the framework emits identical names automatically. Never put `eventId`, `deviceId`, MongoDB URIs, unbounded dynamic collection names, or tokens into metric labels.

### 22.2. Separating Logs by Stage

~~~text
event_received
publisher_created
publisher_subscribed
mongo_write_started
mongo_write_completed
mongo_write_failed
business_committed
~~~

When switching schedulers/threads, MDC/`ThreadLocal` logging context does not automatically propagate intact. Use Reactor `Context` or configured context propagation, carrying durable correlation/business IDs across retries.

### 22.3. Security

- Use a **least-privilege** MongoDB account; never grant admin rights to the adapter.
- Protect secrets/TLS and network access; never log credentials.
- Bound queries with server-side tenant filters, `limit`, sorting, and appropriate indexes.
- Use collection allowlists; never let clients supply headers or raw SpEL directly.
- Validate bytes/JSON, schemas/versions/IDs, and payload sizes before the MongoDB writer.
- Never log full sensitive documents; log error class, operation type, and correlation ID.
- Configure backpressure, queue capacities, concurrency caps, and retry budgets to prevent resource exhaustion.
- Design retention/indexing/backups and recovery aligned with business SLAs.
- If the reactive flow calls another blocking SDK, avoid running it directly on the event loop.

## 23. Common Errors

| Symptom | Possible cause | Fix |
|---|---|---|
| Source emits Message but no data appears | Nothing subscribed to `Flux` payload | Add splitter, `FluxMessageChannel`, and downstream consumer |
| Casting message payload to `List` | Confusing blocking vs. reactive source | Handle `Publisher`/`Flux`/`Mono` |
| Write never executes | `Mono` created and discarded | Compose/subscribe managed by framework |
| `send()==true` yet doc missing in DB | `send` only confirms channel dispatch | Observe write terminal signal/readback |
| `MongoTemplate` injected into reactive builder | Mixing blocking API | Use `ReactiveMongoOperations`/factory |
| `block()` stalls system | Blocking Reactor event loop | Use reactive API or isolate blocking call |
| `Flux` reads huge numbers of documents | Missing `Query.limit`/projection | Bound queries, batches, and demand |
| `flatMap` writes out of order | Concurrent inner publishers | Use `concatMap` or keyed sequencing |
| `onError` swallowed | `onErrorResume` returning empty | Use contract-based retry/DLQ |
| Polls keep re-reading `NEW` | No state/claim tracking | Leases/idempotency and updates |
| Stuck `PROCESSING` after crash | Updated before business commit | Lease expiry and recovery jobs |
| Two workers duplicate one document | `find`+`update` is not an atomic claim | `findAndModify`/owner/version |
| Empty query yet `source.receive()!=null` | Message wraps empty `Flux` | Test post-subscription signals |
| MongoDB timeout yet write committed | Response lost | Retry with same ID and reconcile |
| Reactivity doesn't cut latency | Query/index/pool/server bottleneck | `explain`, pool metrics, limits |
| Change stream fails to run | Unsupported MongoDB topology/roles | Fix deployment and resume tokens |
| Reactor `cancel` treated as rollback | No such guarantee | Reconcile DB state |
| Shutdown loses pending items | In-memory queues, fire-and-forget | Durable upstream/outbox and draining |

Isolation path:

~~~text
Producer/Poller
  -> Spring Message
  -> Reactive source/handler
  -> Publisher created
  -> Subscribe/demand
  -> ReactiveMongoOperations
  -> MongoDB driver/database/collection
  -> onNext/onComplete/onError
  -> Business ACK/commit
~~~

## 24. Comprehensive Hands-On Lab

Build an **HTTP/Kafka → Spring Integration reactive MongoDB outbound → MongoDB → reactive inbound polling → event processing** system.

### Part A — API and Subscription

1. Set up test MongoDB and the Spring Boot reactive MongoDB starter.
2. Inject `ReactiveMongoOperations` and define `TelemetryEvent` with `@Id`.
3. Create a `Mono` from `save` without subscribing; explain why no DB ACK occurs yet.
4. Use `StepVerifier` to subscribe, read back data, and clean up.
5. Compare `Message<Flux<T>>`, `Message<Mono<T>>`, `Message<List<T>>`, and `Message<T>`.

### Part B — Inbound Polling

1. Build `MongoDb.reactiveInboundChannelAdapter(...)` querying `status=NEW`.
2. Attach a `fixedDelay` poller, splitter, `FluxMessageChannel`, and real consumer.
3. Seed N `NEW` documents and assert N events are emitted **after subscription**.
4. Switch to `expectSingleResult(true)` in another flow; test an empty publisher.
5. Add `Query.limit`, tenant filters, sorting, and projections.
6. Try `updateExpression`, then simulate a crash in `CLAIMED` to design recovery.

### Part C — Outbound Writer

1. Build `MongoDb.reactiveOutboundChannelAdapter(reactiveMongoOperations)`.
2. Place a `FluxMessageChannel` ahead of the handler.
3. Send events from upstream and await DB write/readback with bounded timeouts.
4. Use `collectionNameFunction` with a `LIVE`/`ARCHIVE` allowlist.
5. Test missing headers, authorization errors, MongoDB down, and mapping failures.
6. Send the same event ID multiple times; distinguish `save`, `insert`, and partial updates.

### Part D — Reliability and Performance

1. Compare `flatMap(..., 8)` vs. `concatMap` for throughput and ordering.
2. Simulate timeouts/cancellations and explain why DB state reconciliation is mandatory.
3. Use unique keys and idempotency to handle Kafka/JMS redeliveries.
4. Run two pollers querying `NEW` to discuss atomic claiming.
5. Configure `ReactiveMongoTransactionManager` across related MongoDB operations.
6. Instrument metrics for publishers created/subscribed, documents emitted, write success/error, and in-flight counts.
7. Test shutdown with pending writes in flight, verifying durable retry/outbox handling.
8. Compare reactive polling against change streams and blocking adapters to justify architectural choices.

**Self-assessment questions:**

- How do `Mono` and `Flux` differ?
- Why is creating a `Mono` insufficient for a MongoDB write to actually execute?
- What type does `ReactiveMongoDbMessageSource.receive()` return?
- Does `expectSingleResult(false)` mean the reactive source returns `List<T>`?
- When no data matches, how does `Flux.empty()` differ from `receive() == null`?
- Why does a reactive inbound adapter still require a poller?
- What does `FluxMessageChannel` provide, and what are its limits?
- Does `maxMessagesPerPoll(1)` limit the result to one MongoDB document?
- Why is `Query.limit(50)` distinct from backpressure demand?
- Why is `send()==true` not a write ACK?
- Why can `save` overwrite an existing document sharing the same ID?
- When should you use partial updates or insert-only operations?
- How do `flatMap` and `concatMap` differ in ordering?
- Why can `onErrorResume(Mono.empty())` drop events?
- Does cancellation prove the DB has not committed?
- Does `ReactiveMongoTransactionManager` automatically commit Kafka offsets or JMS ACKs?
- How does a reactive polling source differ from a MongoDB change stream?
- Why should you not assume `reactiveOutboundGateway` exists if not published in your Java DSL API?
- What must `StepVerifier` tests assert to avoid false positives?
- When multiple instances poll `NEW`, what kind of claim mechanism is needed?

## 25. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB reactive channel adapters, inbound/outbound, and change streams.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): `reactiveInboundChannelAdapter` and `reactiveOutboundChannelAdapter` factories.
- [Spring Integration API — ReactiveMongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/ReactiveMongoDbMessageSource.html): Messages with `Flux`/`Mono` payloads and subscription.
- [Spring Integration API — ReactiveMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/ReactiveMongoDbMessageSourceSpec.html): collection, `entityClass`, `expectSingleResult`, and `update`.
- [Spring Integration API — ReactiveMongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/ReactiveMongoDbStoringMessageHandler.html): `Mono<Void>`, `collectionNameExpression`, and converter.
- [Spring Integration API — ReactiveMongoDbMessageHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/ReactiveMongoDbMessageHandlerSpec.html): `collectionName`, `collectionNameFunction`.
- [Spring Integration Reference — Reactive Streams Support](https://docs.spring.io/spring-integration/reference/reactive-streams.html): `FluxMessageChannel`, `ReactiveMessageHandler`, splitters, and polling.
- [Spring Data MongoDB — Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html): `ReactiveMongoDatabaseFactory` and `ReactiveMongoTemplate`.
- [Spring Data MongoDB — CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`, `insert`, `update`, `MongoOperations`.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ReactiveMongoTransactionManager` and transactions.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): `subscribe`, `onError`, `flatMap`, `concatMap`, cancellation.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): testing publishers.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): write durability and write acknowledgment.

## Conclusion

**Reactive MongoDB adapters** in Spring Integration comprise **`ReactiveMongoDbMessageSource`** for poller-driven MongoDB reads emitting `Message<Flux<T>>` or `Message<Mono<T>>`, and **`ReactiveMongoDbStoringMessageHandler`** for writing payloads via the reactive driver. The single most important takeaway is that **a publisher must be subscribed to** before reactive I/O executes; `FluxMessageChannel` together with `ReactiveMessageHandler` composes demand-driven flows.

In **SPRING_INTEGRATION_ADAPTERS**, production designs must also govern **queries/collections/tenants, batching/concurrency/backpressure, errors/timeouts/cancellations, properly scoped transactions, stable event IDs, retries/idempotency, and business ACKs**. **Reactive improves I/O efficiency; it does not automatically provide exactly-once delivery or eliminate the need for crash recovery.**
