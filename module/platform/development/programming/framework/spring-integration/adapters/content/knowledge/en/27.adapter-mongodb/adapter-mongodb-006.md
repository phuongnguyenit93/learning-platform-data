# MongoDbMessageSource Polling in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Explain what **`MongoDbMessageSource`** is, why it belongs to the **Polling Consumer** pattern, and why it must pair with `SourcePollingChannelAdapter` / a poller to create a continuous data flow.
- Distinguish the roles of `MongoOperations`, `MongoTemplate`, `MongoDatabaseFactory`, `MongoDbMessageSource`, `MessageChannel`, and downstream `MessageHandler`s.
- Use Spring Integration Java DSL or XML to read a MongoDB collection on a `fixedDelay`, `fixedRate`, or cron schedule.
- Understand precisely **`expectSingleResult(false)` → `find()` → `Message<List<T>>`** and **`expectSingleResult(true)` → `findOne()` → `Message<T>`**; know how to handle empty results.
- Distinguish **`maxMessagesPerPoll`** from **`Query.limit`**, batch bounds, sorting, projections, indexes, and memory consumption.
- Build dynamic queries/collections using **SpEL expressions** evaluated on each poll, rather than reading a non-existent request `payload`.
- Understand the **`updateExpression`** option to update documents just read, while identifying risks of crashes, races, duplicates, and marking before downstream commits.
- Design **claim/lease, retry, idempotency, transaction**, error channel, observability, and graceful shutdown policies when multiple workers read concurrently.
- Write unit tests for processing logic, tests for `MongoDbMessageSource.receive()`, and integration tests for MongoDB → Spring Message → test channel.

This lesson belongs to the **Adapter MongoDB** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. The module covers connecting external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing flows across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases along with message contracts, error handling, and connection lifecycles. **`MongoDbMessageSource` is the bridge from MongoDB into the upstream end of a flow**; it is not a durable queue, does not automatically provide exactly-once guarantees, and does not replace a synchronized claim mechanism across multiple instances.

## 1. Problem: Polling Pending Documents

An application receives sensor data from HTTP or UDP and stores it in MongoDB's `inbox_events` collection. Another Integration service needs to periodically fetch documents with `status=NEW`, normalize them, and forward them to an analytics system or broker.

Illustrative document:

~~~json
{
  "_id": "evt-101",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "temperatureC": 26.5,
  "status": "NEW",
  "createdAt": "2026-11-20T08:00:00Z"
}
~~~

Requirements:

1. Check the `inbox_events` collection every 5 seconds.
2. Fetch only documents belonging to `tenant-a` with status `NEW`.
3. Cap each query at 50 documents, sorted by `createdAt` then `_id`.
4. Emit **each event as its own Spring Message** to the handler.
5. Never re-send already-processed events forever; recover if a worker dies mid-flight.
6. Do not claim processing succeeded just because a document was queried.

~~~mermaid
flowchart LR
    T["Poller<br/>every 5 seconds"] --> S["MongoDbMessageSource.receive()"]
    S --> Q["MongoOperations.find(Query)"]
    DB[("MongoDB<br/>inbox_events")] <--> Q
    Q --> L["Message<List<InboxEvent>>"]
    L --> SP["Splitter"]
    SP -->|"Message<InboxEvent>"| CH["MessageChannel"]
    CH --> H["Validate / Business handler"]
    H --> O["HTTP / Kafka / JMS / AMQP / DB"]
~~~

**Core takeaway:** the source **does not maintain a change-stream-style push connection**. It executes queries on the poller's schedule. The MongoDB collection can hold the same data across multiple cycles, so **processing state and idempotency** are the responsibility of business design.

## 2. Where Does MongoDbMessageSource Fit in the Architecture?

Related components:

| Component | Role | Who triggers it? |
|---|---|---|
| `MongoClient` | MongoDB Java driver, connections/server selection/pool | Used by client and Spring Data |
| `MongoDatabaseFactory` | Supplies configured database and sessions | Spring Data |
| `MongoOperations` / `MongoTemplate` | `find`, `findOne`, `save`, `update` operations | Message source or handler |
| **`MongoDbMessageSource`** | Executes query and creates Spring `Message` | **Poller calls `receive()`** |
| **`SourcePollingChannelAdapter`** | Schedules source calls and sends messages | Spring Integration lifecycle/scheduler |
| `MessageChannel` | Carries messages from source into flow | Adapter sends, handler receives |
| `Splitter` | Splits `List<T>` into multiple `Message<T>`s | Flow when payload is a list |
| `@ServiceActivator` | Processes each event | Incoming message |
| `MongoDbOutboundGateway` | Queries MongoDB for **each request/reply** | Caller sends request message |
| `MongoDbStoringMessageHandler` | Writes payload to MongoDB | Message from upstream |
| `MongoDbChangeStreamMessageProducer` | Watches change-stream events | Subscription; different endpoint |

**Do not confuse `MongoDbMessageSource` with the MongoDB outbound gateway.** The source reads data on a schedule without needing a request message. The gateway receives a message containing the caller's payload/headers, queries per request, and returns a reply.

### 2.1. Mechanics of a Poll Cycle

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as MongoDbMessageSource
    participant M as MongoOperations
    participant D as MongoDB
    participant C as MessageChannel
    P->>S: receive()
    S->>M: find(query, entityClass, collection)
    M->>D: MongoDB query
    D-->>M: List documents
    M-->>S: List<InboxEvent>
    alt List is non-empty
        S-->>P: Message<List<InboxEvent>>
        P->>C: send(message)
    else No documents
        S-->>P: null
        Note over P: No Message sent
    end
~~~

When the source returns `null` because no data matched, that is a **normal empty poll**, not a MongoDB exception.

## 3. Payload Contract: List by Default, Entity When Single Is Selected

`MongoDbMessageSource` Javadoc describes two modes:

| Configuration | MongoOperations API | Payload when found | When empty |
|---|---|---|---|
| `expectSingleResult(false)`, **default** | `find(Query, Class, collection)` | **`List<InboxEvent>`** in **one Message** | Empty list is treated as no Message |
| `expectSingleResult(true)` | `findOne(Query, Class, collection)` | **`InboxEvent`** in **one Message** | `null` → no Message |

Example with three documents matching the query:

~~~text
Poller.run()
  └─ source.receive()
       └─ MongoDB.find() -> [evt-101, evt-102, evt-103]
            └─ 1 Message<List<InboxEvent>>
                 └─ splitter
                     ├─ Message<InboxEvent>(evt-101)
                     ├─ Message<InboxEvent>(evt-102)
                     └─ Message<InboxEvent>(evt-103)
~~~

**A list of 50 documents is still one message** at the message source output. When `split()` is used, downstream receives 50 individual messages.

### 3.1. When to Use expectSingleResult(true)?

Choose single-result when you want **each `receive()` to pick at most one document**, such as a simple job selected by sort order. However:

- `findOne` **does not mark the document as consumed**.
- If the query still matches the same document, subsequent polls can pick **the exact same document**.
- If "first document" has business meaning, sort explicitly; never assume MongoDB returns the oldest record by default.
- With multiple workers, `findOne + update` is not automatically an atomic claim operation.

### 3.2. Set entityClass Explicitly

Set `entityClass(InboxEvent.class)` so the handler contract is explicit. When omitted, the default type depends on the API/version; avoid writing handler code that blindly casts to `InboxEvent` when the source returns a different BSON/driver type.

### 3.3. Message Headers

The MongoDB inbound source provides collection metadata:

~~~text
Message<List<InboxEvent>>
  payload:
    - InboxEvent(evt-101)
    - InboxEvent(evt-102)
  headers:
    mongo_collectionName = "inbox_events"
    id = <Spring Message ID>
    timestamp = <Spring Message timestamp>
~~~

In Java, access it via the constant `MongoHeaders.COLLECTION_NAME` in `org.springframework.integration.mongodb.support.MongoHeaders`. This header describes the **source collection**, not a MongoDB field saved inside each document.

When the splitter creates child messages, headers are propagated per Spring Integration rules and sequence headers may be added. If downstream relies on a specific header, assert its presence and type in an integration test.

## 4. Creating the Project and Test Data

### 4.1. Maven Dependencies

For a **Spring Boot 3.x** project with compatible dependency management:

~~~xml
<!-- Place inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
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
~~~

Choose a BOM/version compatible with your Spring Boot/Spring Data/Spring Integration versions. This lesson uses **blocking `MongoOperations`** and the synchronous MongoDB driver, not the reactive API.

### 4.2. Local MongoDB URI

In the lab's `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

Passwordless local MongoDB is only an example. Production must manage credentials via a secret manager/config, enable TLS as needed, restrict permissions by database/collection, and configure appropriate timeouts and pools.

If Spring Boot already creates `MongoTemplate`/`MongoOperations`, **inject that bean**. Do not declare a duplicate `MongoClient`/factory/template without a clear architectural reason.

### 4.3. Creating Data with mongosh

~~~javascript
use adapter_lab

db.inbox_events.insertMany([
  {
    _id: "evt-101",
    tenantId: "tenant-a",
    deviceId: "node-7",
    temperatureC: 26.5,
    status: "NEW",
    createdAt: ISODate("2026-11-20T08:00:00Z")
  },
  {
    _id: "evt-102",
    tenantId: "tenant-a",
    deviceId: "node-8",
    temperatureC: 25.8,
    status: "NEW",
    createdAt: ISODate("2026-11-20T08:00:01Z")
  },
  {
    _id: "evt-103",
    tenantId: "tenant-a",
    deviceId: "node-9",
    temperatureC: 24.9,
    status: "DONE",
    createdAt: ISODate("2026-11-20T08:00:02Z")
  }
])

db.inbox_events.find({
  tenantId: "tenant-a",
  status: "NEW"
}).sort({ createdAt: 1, _id: 1 }).limit(50)
~~~

Running the seed a second time with existing IDs throws a duplicate-key exception. Use a dedicated test database and an idempotent seed process; never delete a production collection to reset the lab.

### 4.4. Java 17+ Entity

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inbox_events")
public record InboxEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        BigDecimal temperatureC,
        String status,
        Instant createdAt) {
}
~~~

Spring Data MongoDB uses the configured mapping/converter to turn documents into `InboxEvent`. If a collection contains heterogeneous data, validate before forwarding to other systems; successful Java mapping does not prove every business field is valid.

## 5. Java DSL Configuration: Inbound Adapter with Polling

The most readable approach is Java DSL with the `MongoDb.inboundChannelAdapter(...)` source factory:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoInboxInboundConfig {

    @Bean("inboxEvents")
    public MessageChannel inboxEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboxInboundFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongoOperations,
                            "{ 'tenantId': 'tenant-a', 'status': 'NEW' }")
                        .collectionName("inbox_events")
                        .entityClass(InboxEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("inboxEvents")
                .get();
    }
}
~~~

**Part-by-part explanation:**

1. `MongoDb.inboundChannelAdapter(MongoOperations, String)` creates a `MongoDbMessageSourceSpec` with a static query.
2. `collectionName("inbox_events")` specifies the dataset to read.
3. `entityClass(InboxEvent.class)` maps documents into a strongly typed object.
4. `expectSingleResult(false)` calls `find()` and emits `Message<List<InboxEvent>>`.
5. `Pollers.fixedDelay(5000)` triggers the source periodically with a **fixed delay** of 5,000 ms between completions and next starts.
6. `maxMessagesPerPoll(1)` caps at **one source message receive per poll task**, **not** one document.
7. `.split()` splits the list into individual `InboxEvent` messages.
8. `.channel("inboxEvents")` sends messages to the application's registered consumer.

**Lab warning:** because the query only reads `status=NEW`, `evt-101` and `evt-102` can appear **repeatedly on every cycle**, even though the splitter and handler work correctly. This is not a framework bug. Start with the simple read exercise, then move to the claim/retry sections for production handling.

### 5.1. An Observer Handler for Events

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class InboxEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(InboxEventObserver.class);

    @ServiceActivator(inputChannel = "inboxEvents")
    public void handle(Message<InboxEvent> message) {
        InboxEvent event = message.getPayload();

        if (event.id() == null || event.id().isBlank()
                || event.deviceId() == null
                || event.tenantId() == null
                || event.status() == null) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB inbox event");
        }

        String collection = message.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME, String.class);

        log.info("Polled event id={}, deviceId={}, collection={}",
                event.id(), event.deviceId(), collection);

        // Demo only observes; no ACK, no claim, no DONE write yet.
    }
}
~~~

This observer may receive the same ID across multiple polls. **Successful logging does not mean downstream committed**; to guarantee business effects, mark completion conditionally after processing.

### 5.2. Message Transport and Channel Type Differences

In the example flow, `DirectChannel` dispatches synchronously to the subscriber. If the business handler makes slow HTTP/Kafka/DB calls, it lengthens the poll execution. Placing an `ExecutorChannel` or `QueueChannel` between the source and handler decouples threads, yet complicates **acknowledgment, error propagation, and processing order**.

**Do not conclude "poll finished" equals "handler durably persisted".** With a queue/executor, messages may only be accepted in memory. If the process crashes, messages not yet persisted to a durable store can be lost.

## 6. Poller: fixedDelay, fixedRate, maxMessagesPerPoll

The poller configures **frequency** and **how many times `MessageSource.receive()` is called**. For an inbound adapter, a poller is required unless the project defines an appropriate global default poller.

| Property | Meaning | Example |
|---|---|---|
| `fixedDelay` | Schedules next trigger after a delay from previous completion | `fixedDelay(5000)` |
| `fixedRate` | Runs on a fixed periodic cadence | `fixedRate(5000)` |
| `cron` | Schedule by cron expression | Every minute/hour per business rules |
| `maxMessagesPerPoll` | Max **`receive` calls** per poll task | `1` |
| `receiveTimeout` | Controls message send/receive timeout at polling layer depending on endpoint/channel | **Not the MongoDB query timeout** |
| Poller `taskExecutor` | Runs poll tasks on a thread pool when configured | Requires concurrency control |
| `autoStartup` | Whether endpoint starts automatically on context start | true/false |
| `errorChannel` | Destination for poller-handled errors per configuration | Needs subscriber and retry policy |

### 6.1. maxMessagesPerPoll Does Not Cap Document Count

~~~text
Poller configuration: maxMessagesPerPoll(1)
MongoDB query:        find(status=NEW)
MongoDB result:       300 documents

Source receive():     1 call
Message payload:      List<InboxEvent> of length 300
Splitter output:      300 Message<InboxEvent>
~~~

If each poll should process at most 50 documents, set **`Query.limit(50)`** or use single-result with proper state design; do not just tweak `maxMessagesPerPoll`.

### 6.2. Do Not Set maxMessagesPerPoll=-1 Arbitrarily

For `SourcePollingChannelAdapter`, the default `maxMessagesPerPoll` is **1** (unlike some `PollingConsumer`s reading from queues). When set to **-1**, the poller keeps invoking the source until it returns `null`.

With a read-only MongoDB query that always returns data:

~~~text
receive() -> List containing evt-101
receive() -> List containing evt-101 again
receive() -> List still containing evt-101
...
~~~

If status is never updated and the query never returns empty, a poll task with `maxMessagesPerPoll(-1)` can **loop for a very long time or never terminate**, overloading the database and downstream. Use a negative value only when you **prove** the source genuinely drains and has a reliable stop condition.

In Spring Integration versions that support it, `maxMessagesPerPoll(0)` can temporarily skip `receive()` calls (e.g., when controlling an endpoint via Control Bus); do not treat it as a clean shutdown of all connected components.

### 6.3. Fixed Delay vs. Fixed Rate

~~~text
fixedDelay(5000)
Poll A: start t=0, complete t=2s
Poll B: start ~t=7s

fixedRate(5000)
Poll A: start ~t=0
Poll B: next schedule ~t=5s
~~~

This is an idealized timeline; the scheduler, thread pool, query/handler duration, and startup all affect actual timings. Do not assume fixed rate automatically permits overlapping polls: that depends on the configured scheduler and task executor.

With blocking MongoDB I/O or slow downstreams, **fixed delay** is usually easier to throttle. For hourly/daily business schedules, consider cron and the system's explicit time zone.

### 6.4. Poller Timeout Is Not the MongoDB Driver Timeout

If MongoDB has not responded to a query, changing `receiveTimeout` on the poller does not alter the driver's `serverSelectionTimeout` or socket/read timeout. Distinguish:

- **Poll trigger**: decides when to call `receive()`.
- **MongoDB driver timeouts**: decide how long to wait for server/connection/I/O.
- **`QueueChannel.receive(timeout)`** in tests: how long JUnit waits for a Spring Message.
- **Business handler timeouts**: downstream HTTP/DB/Kafka limits per contract.

Place timeouts and retries at the **layer where the cost actually occurs**.

## 7. Limiting Results with Query.limit and Sort

To fetch only the 50 newest or oldest documents, use a Spring Data `Query` bounded at MongoDB.

Example with **`MongoDatabaseFactory`** and the DSL overload taking `Query`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;

@Bean
public IntegrationFlow boundedMongoInboxFlow(
        MongoDatabaseFactory mongoDatabaseFactory) {

    Query query = Query.query(
            Criteria.where("tenantId").is("tenant-a")
                    .and("status").is("NEW"))
            .with(Sort.by(
                    Sort.Order.asc("createdAt"),
                    Sort.Order.asc("_id")))
            .limit(50);

    return IntegrationFlow
            .from(
                MongoDb.inboundChannelAdapter(
                        mongoDatabaseFactory, query)
                    .collectionName("inbox_events")
                    .entityClass(InboxEvent.class),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("inboxEvents")
            .get();
}
~~~

**This is an alternative** to `mongoInboxInboundFlow` in section 5; do not register both polling the same `NEW` collection in the lab unless studying contention/duplicate reads.

### 7.1. When Is Sorting by _id Needed?

If multiple documents share the same `createdAt`, sorting solely by timestamp leaves ties in an indeterminate order. Adding `_id` establishes a deterministic secondary order by **`_id` value**, though `_id` does not necessarily reflect real-world event order.

### 7.2. Indexing for Filter + Sort

In the lab `mongosh`:

~~~javascript
db.inbox_events.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1,
  _id: 1
})
~~~

An index helps queries on tenant/status sorted by `createdAt`, but inspect query plans, collection size, and actual write overhead before deploying to production. Do not create indexes for arbitrary combinations if using varied filters/sorts.

### 7.3. Projection and Entity Types

If only a few fields are needed:

~~~java
query.fields()
        .include("_id")
        .include("deviceId")
        .include("tenantId")
        .include("status");
~~~

Fields omitted from the query return as `null`/default values when mapped into the entity. If the handler requires `temperatureC` and `createdAt`, do not exclude them expecting a complete entity. Consider a dedicated projection DTO or fetch all required fields.

### 7.4. Huge Batches Cost More Than Just RAM

A huge `Message<List<T>>` also causes:

- Increased query duration and MongoDB network payload.
- The splitter emitting many back-to-back messages, consuming threads/CPU.
- Downstream HTTP/Kafka/JMS/AMQP potentially getting overwhelmed.
- Long poll task durations, causing scheduler drift.
- Complicated batch-wide retries if just a single document fails.

Reduce batch size in the query, bound downstream concurrency, and measure **documents per poll**, not just **source messages per poll**.

## 8. Creating MongoDbMessageSource Directly as a Java Bean

The Java DSL factory is concise. When you need to manage the source as a dedicated bean or configure advanced expressions, instantiate the class directly.

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class ExplicitMongoSourceConfig {

    @Bean("inboxMongoSource")
    public MongoDbMessageSource inboxMongoSource(
            MongoOperations mongo) {

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo,
                new LiteralExpression(
                    "{ 'tenantId': 'tenant-a', 'status': 'NEW' }"));

        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.setExpectSingleResult(false);
        return source;
    }

    @Bean
    public IntegrationFlow fromExplicitMongoSource(
            MongoDbMessageSource inboxMongoSource) {
        return IntegrationFlow
                .from(inboxMongoSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("inboxEvents")
                .get();
    }
}
~~~

**This configuration is an alternative** to section 5 and expects `inboxEvents`/handler beans in the same context. Avoid registering two sources running the same query and then being surprised by duplicates.

The two main source constructors in the current API:

~~~java
new MongoDbMessageSource(
        mongoOperations, queryExpression);

new MongoDbMessageSource(
        mongoDatabaseFactory, queryExpression);
~~~

In both cases, `queryExpression` is a **Spring Expression** returning a MongoDB JSON query string or a `Query` object. With the factory path, the source may need a converter matching the app's entity mapping; with a configured `MongoOperations`, mapping goes through the Spring Data template.

### 8.1. Caution with Reused Source Beans

If `inboxMongoSource` is already wired into a flow with a poller, **never call `source.receive()` manually in an HTTP request or a concurrent test**. Extra calls contend with the poller for the same data and cause unexpected results in tests or business logic.

To test a source directly, create a **separate test source with no background poller**, or stop the endpoint before testing in an isolated data environment.

## 9. Dynamic Query and Collection Expressions per Poll

A MongoDB inbound source **has no incoming request Message**. Expressions must pull parameters from a managed bean/config or controlled state source, **not `payload.deviceId`** from an HTTP caller.

Example provider creating a fresh `Query` on each read:

~~~java
package example.mongodb;

import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("inboxReadPolicy")
public class InboxReadPolicy {

    private final AtomicReference<String> status =
            new AtomicReference<>("NEW");

    public Query currentQuery() {
        String selected = status.get();

        return Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is(selected))
                .with(Sort.by(
                    Sort.Order.asc("createdAt"),
                    Sort.Order.asc("_id")))
                .limit(50);
    }

    public String currentCollection() {
        return "inbox_events";
    }

    public void selectStatusFromAdmin(String next) {
        if (!Set.of("NEW", "RETRY").contains(next)) {
            throw new IllegalArgumentException(
                    "Unsupported polling status");
        }
        status.set(next);
    }
}
~~~

Configuring the source with SpEL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public MongoDbMessageSource policyMongoSource(
        MongoOperations mongo) {

    SpelExpressionParser parser = new SpelExpressionParser();

    MongoDbMessageSource source = new MongoDbMessageSource(
        mongo,
        parser.parseExpression(
            "@inboxReadPolicy.currentQuery()"));

    source.setCollectionNameExpression(
        parser.parseExpression(
            "@inboxReadPolicy.currentCollection()"));
    source.setEntityClass(InboxEvent.class);
    source.setExpectSingleResult(false);

    return source;
}
~~~

**Prerequisite:** `inboxReadPolicy` must exist in the Spring context, and `MongoDbMessageSource` must be Spring-managed so SpEL can resolve `@beanName`. The source must be wired into an `IntegrationFlow` with a poller as in section 8.

When an admin switches status to `RETRY`, the updated query applies on the **next `receive()`**. There is no guarantee all instances switch together since the example holds state in RAM. Production requires a managed coordination source updated atomically with consistency checks.

### 9.1. Do Not Share a Mutable Query

A `Query` holds limits/sorts/filters. If multiple threads mutate a shared `Query` object used by the source, race conditions occur. The provider above builds a **new `Query` per call**, giving each poll a clean snapshot.

### 9.2. Collection Expressions Do Not Switch Databases

`setCollectionNameExpression(...)` can select collections dynamically, yet they still reside within **the database of the injected `MongoOperations`/`MongoDatabaseFactory`**. To poll a different database, use a separate authorized template/factory bean rather than taking a user string to switch connections.

### 9.3. Query and Collection Should Form One Consistent Policy

If a worker updates query status and collection in two independent fields right as a poll starts, mismatched combinations can occur. For complex dynamic policies, store **one immutable policy object** holding status/collection/limit and swap it atomically or serialize updates at a clean lifecycle boundary.

## 10. updateExpression: Marking Documents Just Read

Since Spring Integration 5.5, the MongoDB inbound source supports **`updateExpression`** to update documents immediately after retrieval. A common idea: query `NEW` documents and flip them to `CLAIMED` so subsequent polls skip them.

### 10.1. Java DSL Example

~~~java
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.integration.mongodb.dsl.MongoDb;

MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(false)
    .update(new Update().set("status", "CLAIMED"));
~~~

This is an **alternative builder snippet** that needs to be attached to a flow with a poller and downstream. Do not run it concurrently with the read-only source from section 5 when evaluating business logic.

### 10.2. What Is Updated and What Is Not Guaranteed?

Spring Integration documentation states `updateExpression` modifies entities **already retrieved from the collection by the source**, preventing them from matching the query again if the update alters the filtered field.

However:

- **Changing `status=CLAIMED` does not mean the business handler has finished.**
- An app crash after the update but before sending to Kafka/HTTP/JMS leaves documents stuck in `CLAIMED`.
- A fetched list may be split downstream where individual handlers succeed or fail independently.
- If multiple instances query concurrently, **read then update** does not automatically become a per-document atomic claim.
- The payload may still hold the pre-update field value; do not assume `message.payload.status` automatically becomes `CLAIMED`.
- `updateExpression` is only a source-level technical step; the application still needs retries, leases, and concurrency control.

A test observing that a document is no longer `NEW` after a poll **does not prove the event was delivered to the target system**.

### 10.3. When Should You Not Enable Update Immediately?

- When first learning how the source returns `List<T>` and inspecting payloads.
- When downstream must confirm success itself before changing status.
- When multiple consumers exist without owner/lease coordination.
- When you must distinguish read data from committed data.
- When the query could still re-select the document because the update didn't change the filtered field.

For production reliability, design an appropriate claim/lease or transaction mechanism rather than merely tacking on an update statement.

## 11. Designing Claim, Lease, ACK, and Idempotency

A suitable state machine:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: Atomic claim + owner/lease
    PROCESSING --> DONE: Business commit succeeded
    PROCESSING --> RETRY: Transient processing error
    PROCESSING --> RETRY: Lease expired
    RETRY --> PROCESSING: Retry with backoff
    RETRY --> DEAD: Exceeded max attempts
~~~

The document may contain:

~~~json
{
  "_id": "evt-101",
  "status": "PROCESSING",
  "claimOwner": "worker-13",
  "leaseUntil": "2026-11-23T03:00:00Z",
  "attempt": 2,
  "nextAttemptAt": null,
  "lastErrorCode": null
}
~~~

**The JSON example illustrates business state only**, not fields automatically created by `MongoDbMessageSource`.

### 11.1. Race When Multiple Instances Poll

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as MongoDB
    A->>D: find(status=NEW)
    B->>D: find(status=NEW)
    D-->>A: evt-101
    D-->>B: evt-101
    A->>D: update status=CLAIMED
    B->>D: update status=CLAIMED
    Note over A,B: Both may process the same evt-101
~~~

**Adding `updateExpression` alone does not prove atomic claiming.** If each job requires a single owner, consider:

1. Using `MongoOperations.findAndModify(...)` with conditional status/lease/owner criteria in **one atomic per-document MongoDB operation**.
2. Setting `claimOwner`, `leaseUntil`, `attempt`, and version conditionally.
3. Having the worker mark `DONE` only if it still holds valid owner/version.
4. Moving expired `PROCESSING` jobs back to `RETRY` per policy.
5. Attaching an **idempotency key** to downstream side effects, usually derived from `_id` or a durable event ID.
6. Monitoring stuck jobs, duplicates, attempt counts, and dead-letters.

When using atomic claims as an **`IntegrationFlow` source**, you may need a **custom `MessageSource`** or dedicated service running `findAndModify` to emit Spring Messages. Never call a standard read-only flow "exactly-once" without concurrency controls.

### 11.2. Source ACK vs. Business ACK

A durable event-processing system distinguishes:

~~~text
1. MongoDB query returns document
2. Spring Message is created
3. Message is accepted by channel
4. Handler begins processing
5. Target Kafka/JMS/HTTP/DB confirms result
6. MongoDB status transitions to DONE conditioned on owner/version
~~~

Marking `DONE` at step 2–3 can lose work if a crash occurs at step 4–5. For outbound brokers/HTTP, define how to handle **target received it, but response was lost**; retries can cause duplicates, requiring stable IDs and idempotent consumers.

### 11.3. Transaction Synchronization Does Not Guarantee a MongoDB Transaction

Spring Integration provides transaction synchronization around pollers with before/after commit/rollback callbacks. Examples sometimes use `PseudoTransactionManager` to trigger callbacks.

**`PseudoTransactionManager` does not turn MongoDB operations into real transactions.** For MongoDB multi-document transactions, you need a supported topology, `MongoTransactionManager`, and proper transaction boundaries. Nor does a MongoDB transaction **automatically span Kafka/JMS/HTTP** as a distributed transaction.

## 12. XML Configuration of the MongoDB Inbound Adapter

An equivalent configuration in Spring Integration XML:

~~~xml
<!-- XML declaring valid int and int-mongodb namespaces -->
<int:channel id="mongoRawResults"/>

<int-mongodb:inbound-channel-adapter
        id="mongoInboxInboundAdapter"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'tenantId':'tenant-a', 'status':'NEW' }"
        entity-class="example.mongodb.InboxEvent"
        auto-startup="false">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

This configuration **has an output channel receiving a `List`** when `expectSingleResult` remains at its default `false`. Downstream needs a handler accepting `List` or a separate splitter.

`auto-startup="false"` is useful in labs when starting manually; production may choose auto-start depending on architecture. If the inbound endpoint is not started, the poller does not run merely because MongoDB has data.

### 12.1. Dynamic XML query-expression

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboxDynamic"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        query-expression="@inboxReadPolicy.currentQuery()"
        collection-name-expression="@inboxReadPolicy.currentCollection()"
        entity-class="example.mongodb.InboxEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

**An alternative option**; do not declare two adapters sharing the same channel/dataset unintentionally. The `inboxReadPolicy` bean must exist in the context; `query-expression` returns a MongoDB JSON query string or Spring Data `Query`.

### 12.2. Attributes Never to Mix Carelessly

| Attribute | Contract |
|---|---|
| `query` or `query-expression` | **One of the two** |
| `collection-name` or `collection-name-expression` | **One of the two** |
| `mongo-template` or `mongodb-factory` | **One of the two**, per endpoint config |
| `entity-class` | Java type of mapped documents |
| `auto-startup` | Endpoint lifecycle |
| `poller` | Source `receive` schedule, message count, and error handling |
| `update-expression` (if used) | Updates retrieved documents; not a downstream ACK |

Never attach `query` and `poller` to a **MongoDB outbound storing adapter** treating it as an inbound source. The writer handles messages arriving from a channel, whereas the source queries MongoDB on a schedule.

## 13. Comparing MongoDB Polling with Change Stream and Outbound Gateway

| Criterion | MongoDbMessageSource | Change stream inbound | MongoDbOutboundGateway |
|---|---|---|---|
| Trigger mechanism | **Poller** | MongoDB change stream subscription | **Request Message** |
| Reads via | `find` or `findOne` | MongoDB change stream API | `find`/`findOne` or callback per request |
| Output data | Queried List/entity | Change event or body per config | Reply to caller |
| Has input request payload? | No | Not in gateway style | **Yes** |
| Latency | Depends on poll schedule | Depends on subscription and environment | Depends on request/DB latency |
| Re-reads if stateless? | **Possible** | Needs dedicated resume/checkpoint | Caller can re-query |
| Best suited for | Batch/queue-like polling | CDC/near-real-time updates | Per-request search/lookup APIs |
| Recovery mechanism | Query/claim/lease/idempotency | Resume token/re-subscription | Caller retry/error/timeout |

**MongoDB change streams** require a supporting deployment, privileges, and MongoDB capabilities. It is not merely an upgraded polling `MongoDbMessageSource`; it is a **different endpoint with its own semantics**.

## 14. Errors, Timeouts, and Error Channels

### 14.1. Error Classification

| Symptom | Where it can occur | Handling |
|---|---|---|
| MongoDB connection down | Driver/`MongoOperations` during poll | Bounded retry, backoff, health/metrics |
| Bad auth / missing read privileges | Connecting/querying collection | Fix roles/secrets; no blind retries |
| Wrong collection | Query returns empty or config errors | Check DB/collection names, `MongoOperations` bean |
| Query expression error | Before DB query runs | Test expressions and BeanFactory/SpEL context |
| Document mapping failure | `MongoConverter` | Classify schema issues, quarantine/reconcile |
| No documents | `receive()==null` | Not an error; track empty polls |
| Handler error after splitter | Downstream service | Flow error channel/advice; retry/claim |
| Query too broad | DB returns large list | Limits/sorts/indexes/projections |
| Poll task runs long | Slow MongoDB or blocking handler | Timeouts, batch sizing, bounded concurrency |
| Duplicate reads after restart | No checkpoint/claim | DB state and idempotency |
| Stuck `PROCESSING` document | Worker crash / unrecovered lease | Recovery/retry scheduler |
| Concurrent polling duplicates | Multiple instances query before update | Atomic claim/owner/version |
| Outbound message ACKed too early | Async queue or pre-commit update | Clear ACK boundary and `DONE` transition |

### 14.2. Synchronous and Asynchronous Errors

With a `DirectChannel` and synchronous handler, downstream exceptions propagate to the poll task. With an executor or asynchronous channel, exceptions may route to an error channel on another thread.

**Do not assume every error becomes a single `ErrorMessage`.** A query returning an empty list is not an exception; a DB query error happens **before a payload exists**; an HTTP/Kafka handler failure happens **after the message was produced**. Place logs/metrics at the exact boundaries.

### 14.3. Poller error-channel in XML

In an application with `mongoPollingErrors` configured as a channel and an appropriate error handler:

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboxWithErrors"
        channel="mongoRawResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        query="{ 'status':'NEW' }"
        entity-class="example.mongodb.InboxEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"
                error-channel="mongoPollingErrors"/>
</int-mongodb:inbound-channel-adapter>
~~~

**This is an alternative configuration**; do not declare it alongside the other example adapters. You must add `mongoPollingErrors` and a consumer handling `ErrorMessage` appropriately. Never forward raw sensitive errors to a public channel; classify transient vs. permanent errors and enforce retry budgets.

## 15. Lifecycle, Shutdown, and Backpressure

Spring manages endpoints via `SmartLifecycle`:

- On `ApplicationContext` start, inbound endpoints may auto-start and trigger the poller.
- Poll tasks call `source.receive()` on trigger.
- On `stop`, no new poll tasks should be scheduled; **messages already fetched or queued** may still be processing depending on architecture.
- The MongoDB client/pool belongs to reusable Spring Data beans; never instantiate a new client per poll.
- On restart, the source may re-query matching documents; **there is no automatic durable cursor for query polling**.
- When scaling to multiple instances, never rely on in-memory flags to coordinate who claimed which document.
- If downstream uses an in-memory `QueueChannel`, decide explicitly how pending events are handled if a process dies.

### 15.1. Backpressure Is Not an Automatic Feature of MongoDB Queries

If a source returns 10,000 documents in one cycle and the splitter emits 10,000 messages, downstream systems can overload despite a 5-second poller.

Mitigations:

1. Bound `Query.limit` and MongoDB resources.
2. Choose `fixedDelay` aligned with processing duration.
3. Bound concurrency and queue capacities.
4. Monitor queue depth, handler latency, and retries.
5. Throttle/pause polling when downstream falls behind.
6. Use a durable broker/outbox when data loss is unacceptable.
7. If the source acts as a work queue, design **claim/release** rather than re-scanning the entire collection every poll.

A polling message source does not provide automatic end-to-end backpressure across MongoDB → JMS/Kafka/HTTP.

## 16. Unit Testing MongoDbMessageSource

There are two distinct test scopes: **business logic** without MongoDB, and **`source.receive()`** with mocked `MongoOperations` or a test database.

### 16.1. Unit Testing the Validator

~~~java
package example.mongodb;

public final class InboxEventValidator {

    public void validate(InboxEvent event) {
        if (event == null
                || event.id() == null || event.id().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || event.temperatureC() == null
                || event.status() == null) {
            throw new IllegalArgumentException(
                    "Invalid inbox event");
        }
    }
}
~~~

JUnit 5:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InboxEventValidatorTest {

    @Test
    void acceptsValidEvent() {
        InboxEvent event = new InboxEvent(
                "evt-101", "tenant-a", "node-7",
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-20T08:00:00Z"));

        assertDoesNotThrow(
                () -> new InboxEventValidator().validate(event));
    }

    @Test
    void rejectsMissingDeviceId() {
        InboxEvent event = new InboxEvent(
                "evt-102", "tenant-a", null,
                new BigDecimal("25.8"), "NEW",
                Instant.parse("2026-11-20T08:00:01Z"));

        assertThrows(IllegalArgumentException.class,
                () -> new InboxEventValidator().validate(event));
    }
}
~~~

These tests do not start a Spring context or test polling, yet they quickly validate the business contract.

### 16.2. Testing source.receive() with Mocked MongoOperations

To verify a source actually invokes `MongoOperations.find(...)` and turns the list into a `Message`, use Mockito and `LiteralExpression`. This test **has no poller**, so it does not compete with another endpoint.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MongoDbMessageSourceUnitTest {

    @Test
    void findReturnsOneMessageHoldingList() {
        MongoOperations mongo = mock(MongoOperations.class);

        InboxEvent event = new InboxEvent(
                "evt-101", "tenant-a", "node-7",
                new BigDecimal("26.5"), "NEW",
                Instant.parse("2026-11-20T08:00:00Z"));

        when(mongo.find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events")))
            .thenReturn(List.of(event));

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo, new LiteralExpression(
                    "{ 'tenantId':'tenant-a', 'status':'NEW' }"));

        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.setExpectSingleResult(false);
        source.afterPropertiesSet();

        Message<?> result = source.receive();

        assertNotNull(result);
        assertInstanceOf(List.class, result.getPayload());
        assertEquals(1, ((List<?>) result.getPayload()).size());
        assertEquals("inbox_events", result.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME));

        verify(mongo).find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events"));
    }

    @Test
    void emptyFindReturnsNoMessage() {
        MongoOperations mongo = mock(MongoOperations.class);

        when(mongo.find(
                any(Query.class),
                eq(InboxEvent.class),
                eq("inbox_events")))
            .thenReturn(List.of());

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo, new LiteralExpression("{ 'status':'NEW' }"));
        source.setCollectionNameExpression(
                new LiteralExpression("inbox_events"));
        source.setEntityClass(InboxEvent.class);
        source.afterPropertiesSet();

        assertNull(source.receive());
    }
}
~~~

**Technical note:** the example calls `afterPropertiesSet()` because the source is instantiated manually outside a Spring context. Tests may need `BeanFactory` setup if replacing `LiteralExpression` with `@bean.method()`. Check Javadocs for your dependency version's initialization API; avoid mocking behavior that diverges from the real source.

Source unit tests verify **query response → message** conversion, not real MongoDB connectivity or poller scheduling.

### 16.3. Testing expectSingleResult(true)

Create a separate source with `setExpectSingleResult(true)` and stub:

~~~java
when(mongo.findOne(
        any(Query.class),
        eq(InboxEvent.class),
        eq("inbox_events")))
    .thenReturn(event);
~~~

In this mode, `result.getPayload()` must be an `InboxEvent` rather than a `List`. If `findOne` returns null, `receive()` returns null. **Never call a source that is actively being polled by the application** in direct tests.

## 17. Integration Testing MongoDB → QueueChannel

An integration test must verify the **real query**, **message payload**, **headers**, and **polling adapter wiring**.

~~~mermaid
flowchart LR
    S["JUnit seeds test MongoDB"] --> DB["Test MongoDB collection"]
    DB --> P["MongoDbMessageSource + Poller"]
    P --> SP["Splitter"]
    SP --> Q["QueueChannel: mongoTestSink"]
    Q --> A["JUnit receive(timeout) + asserts"]
~~~

With Spring Boot Test and a CI-managed test MongoDB instance or Testcontainers (when Docker is available), configure a dedicated sink:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;

@Bean("mongoTestSink")
public QueueChannel mongoTestSink() {
    return new QueueChannel(32);
}
~~~

In a **test-only `IntegrationFlow`**, route the splitter into `mongoTestSink` instead of the production business handler:

~~~java
// Trailing portion of a test-only flow:
.split()
.channel("mongoTestSink")
.get();
~~~

JUnit assertion in a class with a test context and a seeded `NEW` document:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

@Autowired
@Qualifier("mongoTestSink")
QueueChannel testSink;

@Test
void receivesPolledDocument() {
    Message<?> received = testSink.receive(5000);

    assertNotNull(received, "Poll did not produce a Message");
    assertInstanceOf(InboxEvent.class, received.getPayload());

    InboxEvent event = (InboxEvent) received.getPayload();
    assertEquals("evt-101", event.id());
    assertEquals("tenant-a", event.tenantId());
}
~~~

This is a **test class fragment**, not a standalone Java file. Configure the Spring test context, test MongoDB instance, data seed/cleanup, and remaining imports. Never run this integration test against a production database.

### 17.1. Key Test Cases

| Test | Assertion |
|---|---|
| No matching documents | No message arrives at sink within finite timeout |
| One matching document | One `InboxEvent` after splitter |
| Three matching documents | Three payloads after splitter; not confused with three `source.receive` calls |
| `expectSingleResult(true)` | Source returns one entity; flow needs no splitter |
| Query `limit(2)` | At most two documents per query |
| Query sorted by `createdAt/_id` | Result list order matches contract |
| `MongoHeaders.COLLECTION_NAME` | Header reflects the queried collection |
| Query without status update | Event can reappear on subsequent poll |
| With `updateExpression` | Field changes in MongoDB, yet downstream commit is not proven |
| MongoDB down | Retry/error channel/health behave without hanging forever |
| Two pollers running same query | Duplicates detected, demonstrating need for atomic claims |
| Restart endpoint | Non-`DONE` documents recover per state policy |

**Avoid false positives:** if a query should return `evt-101` but the test only asserts `list.size() <= 50`, an empty list passes even when the endpoint is broken. Seed specific IDs, assert exact payload IDs, and verify the collection.

### 17.2. Writing Non-Flaky Tests

- Use isolated collections/databases and test-namespaced random IDs.
- For polling, await messages with `QueueChannel.receive(timeout)` instead of fixed `Thread.sleep` waits.
- Drain queues between tests or use isolated contexts.
- Stop endpoints before cleaning up data to avoid polls racing teardown.
- When asserting **no message**, recognize a finite timeout only proves the queue stayed empty during that window.
- Never attach two consumers reading the same `QueueChannel` test sink if JUnit expects to receive the message.
- When testing a source directly, ensure no background poller shares that source.
- Run across multiple cycles to detect duplicates; single-cycle tests rarely prove idempotency.

## 18. Observability and Security

Suggested metrics (do not assume the framework emits these exact names automatically):

| Metric | Meaning |
|---|---|
| `mongo_poller_run_total` | Poll trigger count |
| `mongo_poller_empty_total` | Polls finding no data |
| `mongo_query_duration_seconds` | MongoDB query latency |
| `mongo_query_result_documents` | Documents read |
| `mongo_inbound_message_total` | `Message<List<T>>` emitted by source |
| `mongo_split_messages_total` | `Message<T>` after splitter |
| `mongo_handler_success_total` | Documents completed per business contract |
| `mongo_handler_errors_total` | Downstream errors |
| `mongo_claim_conflicts_total` | Claim contentions |
| `mongo_lease_expired_total` | Expired `PROCESSING` jobs |
| `mongo_retry_scheduled_total` | Scheduled retries |
| `mongo_inbox_lag_seconds` | Age of pending documents |
| `mongo_pending_work_depth` | Waiting job count |

**Do not equate** source message count with document count. One `Message<List<T>>` can carry many documents; after the splitter, message count changes.

Security requirements:

1. MongoDB account with **least privilege** for reading collections, granting update only when actually needed.
2. URIs, credentials, and certificates kept out of source/logs; use secrets/TLS.
3. Queries enforce tenant filters/allowlists; never accept raw JSON queries or SpEL from untrusted users.
4. Bound batch size, query time, and rate to prevent full-collection scans.
5. Validate schemas/versions/IDs before forwarding to HTTP/Kafka/JMS/AMQP.
6. Never log full sensitive documents in logs or metrics.
7. In multi-tenant setups, `collectionNameExpression` **does not switch databases** or verify tenant authorization automatically.
8. Unique indexes/idempotency keys must align with business contracts.
9. Monitor lease expirations, retries, and backlog to spot stuck workers after restarts.
10. Keep metric label cardinality bounded; never label per document ID.

## 19. Comprehensive Hands-On Lab

Practice building a **MongoDB inbox → Spring Integration → per-event processing → Kafka/JMS/HTTP/DB** pipeline.

### Part A — Source and Payload

1. Create MongoDB `adapter_lab` and seed three documents as in section 4.
2. Configure Spring Boot + MongoDB Integration dependencies.
3. Write `InboxEvent` with `@Document`, `@Id`, and corresponding fields.
4. Configure `MongoDb.inboundChannelAdapter(...)`, `Pollers.fixedDelay(5000)`, `maxMessagesPerPoll(1)`.
5. Before the splitter, use a test `QueueChannel` to verify the payload is `List<InboxEvent>`.
6. After the splitter, verify each message is a single `InboxEvent` with the proper collection header.
7. Test `expectSingleResult(true)` in **another flow**, remove the splitter, and compare payload and missing-data behavior.

### Part B — Batching, Querying, and Scheduling

1. Seed 200 `NEW` documents in the test database.
2. Run the source with `maxMessagesPerPoll=1` without a query limit: observe why a single `Message` can still hold huge numbers of documents.
3. Add `limit(50)`, sorted by `createdAt/_id`, and verify each batch.
4. Compare `fixedDelay` and `fixedRate` when downstream processing takes several seconds.
5. Test `maxMessagesPerPoll=-1` in an **isolated lab with a terminating query**; explain the infinite-loop risk on a read-only source that always returns results.
6. Design an index matching tenant/status/sort and inspect the query plan.

### Part C — Dynamic Queries and Updates

1. Use `InboxReadPolicy.currentQuery()` and SpEL in `MongoDbMessageSource`.
2. Switch status from `NEW` to `RETRY` via a controlled admin call and observe the query on the next poll.
3. Use `update(new Update().set("status","CLAIMED"))` in a separate test.
4. Simulate an app crash between `CLAIMED` and business completion; propose lease-based recovery.
5. Run two instances polling together to reproduce the read/update race; demonstrate atomic `findAndModify` claiming.
6. Design an idempotency key preserved across redeliveries.

### Part D — Testing and Operations

1. Unit test the validator; unit test `source.receive()` with Mockito for non-empty and empty lists.
2. Run an integration test against real MongoDB + `QueueChannel` sink with isolated seed/cleanup.
3. Test MongoDB down, auth failures, invalid mappings, and the error channel.
4. Test stopping/starting the endpoint and verify non-`DONE` data recovers.
5. Forward messages to Kafka/JMS/HTTP; define when `DONE` is marked or source is ACKed.
6. Propose metrics for document count, message count, lag, empty polls, claim conflicts, retries, and queue depth.

**Self-assessment questions:**

- Who actually invokes `MongoDbMessageSource.receive()`?
- Why is `MongoDbMessageSource` not a change stream subscriber?
- When `expectSingleResult(false)` and the query finds 20 documents, how many `Message`s does the source emit?
- Why does `maxMessagesPerPoll(1)` not limit the result to 1 document?
- What happens if `maxMessagesPerPoll=-1` is set while the query always returns a non-empty list?
- What is the difference between `fixedDelay` and `fixedRate`?
- How does `Query.limit(50)` help when the source returns a `List`?
- Why is sorting by both `createdAt` and `_id` needed in some workflows?
- Why is a source query evaluated per poll yet has no request payload?
- Does `updateExpression` mean downstream has committed?
- Can two instances both querying `NEW` process the same document twice?
- When are `findAndModify`, leases, and owners needed?
- What does `MongoHeaders.COLLECTION_NAME` help diagnose?
- Why does one successful poll test not prove there are no duplicates?
- When should you choose a change stream, outbound gateway, or broker instead of polling?

## 20. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound channel adapter, `query-expression`, `updateExpression`, change streams, and transaction synchronization.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): source, `find`/`findOne`, `List` payload, empty results, and collection header.
- [Spring Integration API — AbstractMongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/AbstractMongoDbMessageSource.html): `entityClass`, `expectSingleResult`, collection expression, and update expression.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): `inboundChannelAdapter` factory and overloads.
- [Spring Integration API — AbstractMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): `collectionName`, `collectionNameSupplier`, `entityClass`, `update`.
- [Spring Integration Reference — Configuring Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html): `SourcePollingChannelAdapter`, `maxMessagesPerPoll`, and polling controls.
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): triggers, fixed-delay, fixed-rate, error channels, transactions.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoOperations`, `Query`, `Criteria`, mapping, indexes, and `MongoTransactionManager`.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/): conditional document claiming operations.

## Conclusion

**`MongoDbMessageSource` is a polling-based MongoDB data source.** `SourcePollingChannelAdapter` calls `receive()` on schedule, runs `find()` or `findOne()`, and returns a Spring `Message` downstream when data exists. **By default the source emits one `Message` holding a `List` of documents**, so a splitter is needed if each document must become an individual message.

In **SPRING_INTEGRATION_ADAPTERS**, a pipeline is reliable only when distinguishing **poll frequency from batch size**, **successful queries from business commits**, **reads from atomic claims**, and **Spring Messages from business event IDs**. Bound queries, use appropriate sorting/indexes and batch sizes, design processing state/lease/idempotency/retry, verify error channels and shutdown, and test against real MongoDB when needed. **Polling is scheduled data retrieval, not an exactly-once delivery guarantee.**
