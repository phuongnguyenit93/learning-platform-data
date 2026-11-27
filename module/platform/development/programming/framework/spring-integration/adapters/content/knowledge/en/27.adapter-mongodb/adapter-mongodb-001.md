# MongoDB Inbound Channel Adapter in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Understand the role of the **MongoDB inbound channel adapter** in reading data from MongoDB and publishing it to a Spring Integration `MessageChannel`.
- Distinguish between **MongoDB polling**, **change stream**, **outbound adapter**, and **outbound gateway**.
- Configure `MongoOperations` / `MongoTemplate`, collection, query, entity class, and poller using **Spring Integration Java DSL** or XML.
- Distinguish between a **`List<T>` payload (default)** and a **single object `T` payload** when `expectSingleResult(true)` is enabled; understand the function of a splitter.
- Clearly determine `fixedDelay`, `maxMessagesPerPoll`, the size of each query, and how to choose a reasonable batch size.
- Identify the risk of **re-reading documents across multiple polls**, and design appropriate processing states, idempotency, claim/lease, retry, and transactions.
- Test queries, message payloads, source collection headers, connection errors, and endpoint lifecycles.
- Integrate MongoDB data with files, SFTP, HTTP, JMS, AMQP, Kafka, databases, or other systems via `MessageChannel`.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; it also emphasizes message contracts, error handling, and connection lifecycles. Here, **MongoDB is the data source**, and Spring Integration turns query results into messages so that a business flow can receive, transform, and forward them.

## 1. Problem: Fetching Pending Events in MongoDB

A system writes telemetry records into the `inbox_events` collection. Another service needs to periodically read documents with `status=NEW`, then validate and forward the data to a business processor.

Example data in MongoDB:

~~~json
{
  "_id": "evt-101",
  "type": "DEVICE_READING",
  "deviceId": "node-7",
  "temperatureC": 26.5,
  "status": "NEW",
  "createdAt": "2026-11-01T08:00:00Z"
}
~~~

Expected flow:

~~~mermaid
flowchart LR
    DB["MongoDB<br/>inbox_events"] -->|"Scheduled query"| MS["MongoDbMessageSource"]
    P["Poller<br/>fixed delay"] -.-> MS
    MS -->|"Message<List<InboxEvent>>"| C["MessageChannel"]
    C --> S["Splitter"]
    S -->|"Message<InboxEvent>"| V["Validate / Service"]
    V --> OUT["HTTP / Kafka / AMQP / DB"]
~~~

**Key takeaway:** The MongoDB inbound adapter is a **polling consumer**. It does not actively listen on a new connection socket like UDP, nor does it subscribe to a MongoDB change stream by default. It only runs the MongoDB query when the **poller triggers**, and then sends the result into the message flow.

A successful query also **does not mean** the document has been processed exactly once. If you keep querying `status=NEW` without changing the status, the same documents will continue to appear in subsequent polls.

## 2. How Does the MongoDB Inbound Adapter Differ from Other Components?

| Component | Who triggers it? | Action | Result |
|---|---|---|---|
| **MongoDB inbound channel adapter** | Scheduled poller | Queries MongoDB | Emits a Spring `Message` from the search results |
| **MongoDB change stream inbound adapter** | Subscription/event from MongoDB | Watches collection/database changes | Emits change events when changes occur |
| **MongoDB outbound channel adapter** | Message arriving on input channel | Writes/updates MongoDB data | Primarily a write side effect, not a periodic query channel |
| **MongoDB outbound gateway** | Request message arriving on channel | Queries/updates per gateway contract | Returns a response message to the reply channel |
| **MongoDB message store** | Channel/aggregator/app using store | Stores messages or message groups | Provides persistence for certain Integration patterns |
| **Spring Data MongoTemplate directly** | Application code calling methods | Operates on MongoDB via API | Returns objects directly to the caller |

The MongoDB inbound adapter is suitable when **the data source is a collection scanned on a schedule**. If you need near real-time reactions to MongoDB changes and the environment supports it, consider **change stream**. If you want to look up documents **per specific request** from HTTP or another message, a gateway is usually more appropriate.

## 3. Architecture of a Polling Inbound Adapter

In Spring Integration, this mechanism consists of the following layers:

~~~mermaid
flowchart TD
    T["Trigger: fixedDelay / cron"] --> P["SourcePollingChannelAdapter"]
    P --> R["MongoDbMessageSource.receive()"]
    R --> Q["MongoOperations.find/findOne"]
    Q --> DB["MongoDB collection"]
    DB --> Q
    Q --> M{"Has results?"}
    M -->|No| N["Do not emit message"]
    M -->|Yes| C["Output MessageChannel"]
    C --> H["Splitter / Transformer / Handler"]
~~~

- **`MongoDbMessageSource`** describes how to query MongoDB. It does not schedule `receive()` calls on its own.
- **Poller** determines the frequency and number of `receive()` calls in a cycle.
- **`MessageChannel`** decouples where data is fetched from where it is processed.
- **Handler/transformer/splitter** determines the message structure and handles business logic.
- **The MongoDB collection** remains the source of truth; creating a message does not mean a document automatically disappears or changes status.

### 3.1. A Poll Can Produce a List Payload

According to the `MongoDbMessageSource` API, by default `expectSingleResult=false`. In this case, the adapter uses the operation corresponding to `MongoOperations.find(Query, Class)`. The payload of a message is a **list of mapped documents**. An empty list is treated as no message.

Example of a query returning three documents:

~~~text
Poller triggers
    |
    v
MongoDB finds 3 documents
    |
    v
1 Message<List<InboxEvent>>
    payload.size() = 3
    |
    v
Splitter
    |
    +--> Message<InboxEvent> evt-101
    +--> Message<InboxEvent> evt-102
    +--> Message<InboxEvent> evt-103
~~~

**Do not confuse message count with document count:** a `Message<List<InboxEvent>>` is still **one message** from the message source.

### 3.2. When expectSingleResult=true Is Enabled

With `expectSingleResult(true)`, the adapter uses `findOne(...)` and the payload is **a single document**. If no object is found, `receive()` does not produce a message.

| Configuration | Read operation | Payload when found | Use splitter? |
|---|---|---|---|
| `expectSingleResult(false)` (default) | `find(...)` | `List<InboxEvent>` | Usually yes, to process each document individually |
| `expectSingleResult(true)` | `findOne(...)` | `InboxEvent` | Not needed if one event per message |

When selecting a single document in order, configure a query with a **deterministic sort** if ordering matters. Do not assume the first document returned by MongoDB is always the oldest document.

## 4. Project Setup and MongoDB Connection

### 4.1. Dependencies

For a Spring Boot project with dependency management compatible with Spring Integration:

~~~xml
<!-- Inside <dependencies> of pom.xml -->
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
~~~

The MongoDB starter example here uses the naming convention of **Spring Boot 3.x**. When using a different major version, check the corresponding starter artifact and BOM; do not mix Spring Data, Spring Integration, and MongoDB Driver from incompatible major versions. If using the MongoDB module directly, choose the appropriate synchronous driver. This lesson focuses on the **blocking/polling inbound adapter**, not the reactive driver.

### 4.2. URI Configuration for the Lab

With Spring Boot 3.x, example `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

This is a **local MongoDB in a lab environment**. For real environments, use externalized security configuration outside source code (secret manager, environment variables, or managed configuration); do not hard-code usernames/passwords in the repository. Grant only the read or update permissions on the collections needed by the adapter.

Spring Boot can auto-create `MongoTemplate`/`MongoOperations` when the MongoDB starter and connection configuration are valid. If the application has multiple MongoDB connections, inject the right bean or use an explicit qualifier.

### 4.3. Creating Test Data in mongosh

Select the database and create two events:

~~~javascript
use adapter_lab

db.inbox_events.insertMany([
  {
    _id: "evt-101",
    type: "DEVICE_READING",
    deviceId: "node-7",
    temperatureC: 26.5,
    status: "NEW",
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "evt-102",
    type: "DEVICE_READING",
    deviceId: "node-8",
    temperatureC: 25.9,
    status: "NEW",
    createdAt: ISODate("2026-11-01T08:00:01Z")
  }
])

db.inbox_events.find({ status: "NEW" })
~~~

If you run tests multiple times, `insertMany` with the same `_id` will fail with a duplicate key error. You can replace the seed with `updateOne(..., { upsert: true })` or clean up data **only in the lab database** following a safe procedure; never drop or delete a real collection.

## 5. Data Model (Entity Class)

Using Java 17+ and Spring Data MongoDB:

~~~java
package example.mongodb;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inbox_events")
public record InboxEvent(
        @Id String id,
        String type,
        String deviceId,
        double temperatureC,
        String status,
        Instant createdAt) {
}
~~~

Spring Data MongoDB is responsible for mapping fields in the document to a Java object. This record is an **illustrative entity**; real applications must validate version/schema, null fields, value ranges, device identifiers, and business requirements before forwarding.

If you use `entityClass(InboxEvent.class)`, the payload will consist of entities mapped by MongoDB. If no entity class is configured, the default type depends on the version and API; **you should not rely on the default raw type** when writing handlers with a strict contract.

## 6. Java DSL Example: Polling MongoDB and Emitting Each Event

The configuration consists of a message source, a poller, and a channel. This example is **read-only** so learners can see the flow; it does not update document status yet.

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
public class MongoInboundFlowConfig {

    @Bean("mongoEvents")
    public MessageChannel mongoEvents() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboundFlow(
            MongoOperations mongoTemplate) {

        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongoTemplate, "{ 'status': 'NEW' }")
                        .collectionName("inbox_events")
                        .entityClass(InboxEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("mongoEvents")
                .get();
    }
}
~~~

Components:

1. `MongoDb.inboundChannelAdapter(mongoTemplate, query)` creates a DSL spec for `MongoDbMessageSource`.
2. `collectionName("inbox_events")` specifies the collection to read.
3. `entityClass(InboxEvent.class)` maps results into strongly typed entities.
4. `expectSingleResult(false)` selects `find(...)`, creating one message whose payload is the entity list when results are found.
5. `Pollers.fixedDelay(5000)` schedules execution after a fixed pause between polls; the unit here is milliseconds.
6. `maxMessagesPerPoll(1)` specifies a maximum of **one message retrieval from the source per poll cycle**, **not** a limit of one document.
7. `split()` splits `List<InboxEvent>` into an individual message for each entity.
8. `mongoEvents` is the channel for the downstream handler.

**Lab warning:** because the query only filters `status=NEW` and does not update the status yet, **both documents can be re-emitted on every poll**. This is normal behavior for a repeated query, not Spring Integration magically providing "exactly once". In the demo, observe only a few cycles and then stop the adapter. Later sections cover how to update status and limit duplicates.

### 6.1. Handler Receiving a Single Event

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.support.MongoHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class InboxEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(InboxEventHandler.class);

    @ServiceActivator(inputChannel = "mongoEvents")
    public void handle(Message<InboxEvent> message) {
        InboxEvent event = message.getPayload();

        if (event.id() == null || event.id().isBlank()
                || event.deviceId() == null
                || !Double.isFinite(event.temperatureC())) {
            throw new IllegalArgumentException(
                    "Invalid inbox document");
        }

        String collection = message.getHeaders()
                .get(MongoHeaders.COLLECTION_NAME, String.class);

        log.info("MongoDB event id={}, device={}, collection={}",
                event.id(), event.deviceId(), collection);

        // Demo only logs. In production: process idempotently and commit.
    }
}
~~~

For results from MongoDB inbound, the `MongoHeaders.COLLECTION_NAME` header (actual name `mongo_collectionName`) indicates which collection was queried. This header is **Spring Message metadata**, not a field automatically added to the MongoDB document.

If downstream needs to forward the event to HTTP, Kafka, JMS/AMQP, or file/SFTP, explicitly define which fields are allowed to be forwarded; do not automatically serialize all headers to external systems.

### 6.2. Testing Expected Output

After starting the Spring context and connecting to MongoDB, during a poll that returns results:

~~~text
MongoDB event id=evt-101, device=node-7, collection=inbox_events
MongoDB event id=evt-102, device=node-8, collection=inbox_events
~~~

Each event appears as an individual payload **after the splitter**. If there is no completion-marking logic yet, the log lines above may repeat in the next cycle. If no records match the query, `MongoDbMessageSource.receive()` does not create a message and the handler is not invoked.

## 7. Tuning Batch Size and Query Ordering

### 7.1. maxMessagesPerPoll Differs from Record Count

This is a common mistake:

~~~text
maxMessagesPerPoll(1)
  = at most one MessageSource.receive() per poll
  ≠ at most one MongoDB document returned in the query
~~~

For example, `find(...)` returning 10,000 documents can still be **one message with a List containing 10,000 elements**. The splitter will then push every element downstream. The system can consume significant RAM and tie up the poller thread for a long time.

**Bound the result size at the query level** or use `expectSingleResult(true)` when appropriate. A long poll interval does not by itself eliminate the risk of an unbounded query.

### 7.2. Query with Explicit Limit and Sort

When you want to fetch at most 50 `NEW` documents ordered by `createdAt`, use a Spring Data `Query` and the DSL overload that accepts `MongoDatabaseFactory`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;

@Bean
public IntegrationFlow boundedMongoInboundFlow(
        MongoDatabaseFactory mongoDatabaseFactory) {

    Query query = new Query(Criteria.where("status").is("NEW"))
            .with(Sort.by(Sort.Direction.ASC, "createdAt"))
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
            .channel("mongoEvents")
            .get();
}
~~~

**This is an alternative** to the previous `mongoInboundFlow`; do not register both flows scanning the same `NEW` set in the lab unless you intentionally want to study duplicate reads.

If multiple records share the same `createdAt`, add a sort by `_id` for stable ordering:

~~~java
.with(Sort.by(Sort.Order.asc("createdAt"),
              Sort.Order.asc("_id")))
~~~

This sort snippet is a replacement expression for the `with(...)` call above; **do not chain both** when you only want one sort order.

### 7.3. When You Want One Document per Poll

Use:

~~~java
MongoDb.inboundChannelAdapter(
        mongoTemplate, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(true)
~~~

In this case, the payload is **a single `InboxEvent`**, and you omit the `split()` step in the flow. However, if you do not update the status/read marker, `findOne(...)` can pick **the exact same document** in the next cycle.

## 8. The Biggest Risk: Repeating the Same Data Across Polls

Suppose the collection contains:

~~~text
evt-101: NEW
evt-102: NEW
~~~

After two polls without changing status:

~~~text
Poll 1: evt-101, evt-102
Poll 2: evt-101, evt-102
Poll 3: evt-101, evt-102
...
~~~

The impact can be severe when downstream writes to a database, charges fees, sends emails, or publishes Kafka events: one document can cause **multiple side effects**.

### 8.1. Simple Solution: Update on Read

The Spring Integration MongoDB inbound message source supports **`updateExpression`**; the Java DSL provides `update(...)`. Example:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongoTemplate, "{ 'status': 'NEW' }")
    .collectionName("inbox_events")
    .entityClass(InboxEvent.class)
    .expectSingleResult(false)
    .update(new Update().set("status", "CLAIMED"))
~~~

The update causes queried documents to no longer match `status=NEW` in the next poll. This example is a **simple duplicate-read avoidance mechanism**, not a delivery guarantee.

**What to understand before using it:**

- Updating at the message source is tied to the **read/poll phase**, not an ACK that the entire downstream has committed.
- If a document is changed to `CLAIMED` and then the service crashes before finishing processing, the record can become **stuck**, no longer matching the `NEW` query.
- If multiple instances run the same query, simply adding `update(...)` **does not inherently guarantee that each document is atomically claimed by exactly one instance**.
- If an entity's `status` was read as `NEW` before the update, the payload sent downstream may still contain the **old** value; do not treat the field in the payload as the post-update DB state.
- You need a retry policy, concurrency control, and observability for stuck documents.

### 8.2. Processing States with Lease and Recoverability

A more sound state machine for critical workloads:

~~~mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> PROCESSING: Claim with owner + lease
    PROCESSING --> DONE: Process and commit successfully
    PROCESSING --> RETRY: Transient error
    RETRY --> PROCESSING: Backoff + re-claim
    PROCESSING --> RETRY: Lease expired / worker died
    RETRY --> DEAD: Exceeded max attempts / unrecoverable error
~~~

You can store the following fields:

~~~json
{
  "_id": "evt-101",
  "status": "PROCESSING",
  "claimOwner": "worker-3",
  "leaseUntil": "2026-11-23T09:00:00Z",
  "attempt": 2,
  "lastErrorCode": null
}
~~~

In production applications, if multiple instances read concurrently, use a MongoDB **conditional atomic claim** operation, such as logic based on `findAndModify` or an equivalent pattern suited to your document and transaction model. Ensure:

1. Only claim records that are `NEW` or records whose lease is eligible for reclamation.
2. Assign `claimOwner`, `leaseUntil`, and `attempt` atomically when claiming.
3. The worker processes the document within the lease window; renew the lease if the work takes longer.
4. Upon success, mark `DONE` conditioned on the appropriate owner/version.
5. Upon failure, record `RETRY` and `nextAttemptAt`, or `DEAD`.
6. Design **idempotency** at the business side effect because retries can produce duplicates.

**Important:** if atomic claiming across multiple instances is required, the default polling message source model should be evaluated and may need a **custom MessageSource / outbound gateway / claim service**. Do not imply that the adapter's default `query + update` is a transaction guaranteeing exactly-once execution.

### 8.3. Do Not Confuse Transaction Synchronization with MongoDB Transactions

Spring Integration provides **transaction synchronization** for pollers, allowing actions to run after commit or rollback of a managed transaction. The documentation also mentions `PseudoTransactionManager` to trigger synchronization callbacks when no real transaction exists.

**`PseudoTransactionManager` does not magically make MongoDB operations atomic.** If you need MongoDB multi-document transactions, you must configure a real transaction manager/replica set and design proper transactions. Even a real database transaction does not turn HTTP/Kafka side effects into a distributed exactly-once transaction.

## 9. Headers and Message Contract

A message from MongoDB inbound may include:

~~~text
Message<List<InboxEvent>>:
  payload = [evt-101, evt-102]
  headers:
    mongo_collectionName = "inbox_events"
    id = Spring Message UUID
    timestamp = Message creation time
~~~

After the splitter, each `Message<InboxEvent>` may carry appropriate headers from the input message plus splitter sequence/group metadata depending on configuration.

| Component | Source | Meaning |
|---|---|---|
| `Message.payload` | `find()` or `findOne()` | MongoDB query data |
| `MongoHeaders.COLLECTION_NAME` | MongoDB message source | Collection that was queried |
| `MessageHeaders.ID` | Spring Messaging | Internal message identifier |
| `MessageHeaders.TIMESTAMP` | Spring Messaging | Message creation time |
| `InboxEvent.id` | MongoDB document `_id` | Business/document identifier, suitable as idempotency basis |
| `status / attempt / leaseUntil` | Document if defined by application | Processing and recovery state |

**Do not use the Spring Message UUID as a durable event ID.** A re-polled document creates a new message with a different message UUID. For deduplication, use the document's `_id` or a stable business key.

If forwarding the payload to JMS, AMQP, Kafka, or HTTP, map it to an explicit DTO/event schema. Do not automatically expose all message headers externally, especially internal operational metadata or Java objects meaningful only in-process.

## 10. XML Namespace Example

Projects using Spring Integration XML can configure the equivalent as follows:

~~~xml
<int-mongodb:inbound-channel-adapter
        id="mongoInboundAdapter"
        channel="mongoQueryResults"
        mongo-template="mongoTemplate"
        collection-name="inbox_events"
        entity-class="example.mongodb.InboxEvent"
        query="{ 'status': 'NEW' }"
        auto-startup="false">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

The snippet above must sit inside a Spring XML file with properly versioned `int` and `int-mongodb` namespaces declared, along with the `mongoTemplate` bean and `mongoQueryResults` channel.

- `query` accepts a static query.
- `query-expression` accepts a SpEL expression returning a query string or `Query` object depending on the API; **do not configure simultaneously** with `query`.
- `collection-name` and `collection-name-expression` are two ways to select the collection.
- `mongo-template` and `mongodb-factory` are alternative configuration paths; **do not specify both** on the same adapter.
- `entity-class` specifies the object type to read.
- `auto-startup=false` is suitable when you want to start explicitly during tests/maintenance; production can allow automatic startup with the lifecycle.

The XML example does not automatically configure a splitter. If `expectSingleResult` is left at its default, the downstream of `mongoQueryResults` must handle a `List` payload or configure a separate splitter.

## 11. Polling vs. Change Stream

| Criterion | Polling inbound | Change stream inbound |
|---|---|---|
| Mechanism | Periodic query | Subscribes to changes emitted by MongoDB |
| Latency | Depends on poll schedule, query time, and processing | Typically low while the change stream is active |
| Payload | Entity or List query result | ChangeStreamEvent or body depending on config |
| DB load | Queries run even when no changes occur | Proportional to change stream activity and subscriptions |
| State tracking | Requires app-designed query/update/claim or checkpoint | Requires storing resume tokens and proper retry/resubscription handling |
| Environment requirements | Normal MongoDB query connection | MongoDB deployment supporting change streams and appropriate privileges |
| Best-fit scenarios | Simple work queues, batch imports, periodic processing | Reacting to updates/inserts, CDC-style integration |

Spring Integration provides `MongoDbChangeStreamMessageProducer` and the Java DSL `MongoDb.changeStreamInboundChannelAdapter(...)` for change stream scenarios. **This is a different endpoint** from `MongoDb.inboundChannelAdapter(...)` covered in this lesson. Do not assume polling MongoDB inbound automatically maintains resume tokens or tracks every insert in chronological order.

## 12. Error Handling, Retry, and Lifecycle

### 12.1. Error Classification

| Error | Origin | How to handle |
|---|---|---|
| MongoDB unreachable | During a poll/query | Emit appropriate metrics/error channel events, backoff/retry, check timeouts |
| Wrong collection or permissions | When querying MongoDB | Fix configuration and DB roles; do not retry blindly forever |
| Query too broad | `find()` returns a huge List | Constrain query, use limit/sort/projection and indexes |
| Unmappable document | During Mongo mapping/conversion | Validate schema/version, error handling/quarantine |
| No results | `receive()` returns null | Not an error; no message emitted |
| HTTP/Kafka/DB handler error | Downstream of channel | Bounded retry, idempotency, do not mark DONE before commit |
| Process dies after claim | Stuck `PROCESSING` state | Lease timeout, recovery/reconciliation |
| Multiple instances reading concurrently | Duplicate claims/side effects | Atomic claim, owner/version checks, and idempotency |
| Consumer backlog | Queue/executor full | Reduce batch/rate, bounded queues and backpressure |
| Poller restart | Source restarts and resumes querying | No built-in replay guarantee without designed state |

### 12.2. Adapter Lifecycle

The polling inbound endpoint is managed by Spring's lifecycle. With `autoStartup=true`, the endpoint may begin polling as soon as the context starts. If the DB is not ready yet, you need proper error/health policies and retry; do not assume context startup means a query has succeeded.

When `stop()` is called, the poller stops initiating new receives per lifecycle; messages already fetched or handed off for asynchronous processing may still be in flight. If using `QueueChannel`/`ExecutorChannel`, plan for **draining** and verify commits during shutdown.

**Do not rely on `Thread.sleep` to guarantee everything has finished processing.** Measure queue depth, active tasks, DB state, and shutdown conditions with deadlines. For durable data-reading flows, recovery after restart depends on how documents are claimed/acked, not just Spring endpoint startup.

### 12.3. Poller and Error Channel

When an exception occurs during polling or downstream execution, Spring Integration provides error channel/advice mechanisms depending on synchronous/asynchronous configuration. Verify the **actual error path** of the poller in your application:

- Query errors can occur **before any message payload exists**.
- Validation errors occur **after the message has been created**.
- Commit errors occur **after business processing**.
- Documents skipped because they do not match the query **do not generate an ErrorMessage**.

Do not simply catch every exception, log it, and move on; know when to retry, which document state should transition to `RETRY`, and which errors should trigger alerts.

## 13. Observability and Operational Tuning

Appropriate metrics include:

| Metric | Purpose |
|---|---|
| `mongo_poller_runs_total` | Number of poll executions |
| `mongo_query_duration_seconds` | Query latency |
| `mongo_query_results_total` | Number of documents fetched |
| `mongo_empty_polls_total` | Queries returning no results |
| `mongo_inbound_messages_total` | Number of Spring Messages emitted by the adapter |
| `mongo_handler_processed_total` | Number of documents processed successfully |
| `mongo_handler_errors_total` | Number of downstream processing errors |
| `mongo_processing_lease_expired_total` | Number of expired `PROCESSING` documents needing recovery |
| `mongo_processing_lag_seconds` | Time from `createdAt` until processing |
| `mongo_queue_depth` | Number of jobs waiting downstream |

**Do not confuse:**
- Count of `Message<List<InboxEvent>>` with document count.
- A successful poll with successful business processing.
- `update(status=CLAIMED)` with an ACK that downstream has committed.
- `MessageHeaders.ID` with `InboxEvent.id`.

In production, create indexes matching your query, for example when filtering by `status` and sorting by `createdAt`:

~~~javascript
db.inbox_events.createIndex({ status: 1, createdAt: 1, _id: 1 })
~~~

Do not create indexes arbitrarily on large collections without evaluating index build cost and write load. When `DONE` documents grow significantly, establish an appropriate retention/archival policy so the collection does not grow unbounded.

With multiple instances, record metrics per instance and aggregate appropriately; do not use per-`_id` or per-device-ID labels if cardinality is very high.

## 14. Testing the MongoDB Inbound Adapter

### 14.1. Unit Testing Processing Logic

Decouple business logic from Spring Integration where possible:

~~~java
public final class InboxValidator {

    public void validate(InboxEvent event) {
        if (event == null
                || event.id() == null
                || event.id().isBlank()
                || event.deviceId() == null
                || event.deviceId().isBlank()
                || !Double.isFinite(event.temperatureC())) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB inbox event");
        }
    }
}
~~~

JUnit test:

~~~java
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InboxValidatorTest {

    @Test
    void acceptsValidDocument() {
        InboxEvent event = new InboxEvent(
                "evt-101", "DEVICE_READING", "node-7",
                26.5, "NEW", Instant.parse("2026-11-01T08:00:00Z"));

        assertDoesNotThrow(
                () -> new InboxValidator().validate(event));
    }

    @Test
    void rejectsMissingDeviceId() {
        InboxEvent event = new InboxEvent(
                "evt-102", "DEVICE_READING", null,
                25.9, "NEW", Instant.parse("2026-11-01T08:00:00Z"));

        assertThrows(IllegalArgumentException.class,
                () -> new InboxValidator().validate(event));
    }
}
~~~

This is a **unit test**; it does not verify that the MongoDB query or poller works.

### 14.2. Integration Testing with Real MongoDB

You can use a CI-managed MongoDB test instance or **Testcontainers** when the runner supports Docker. Testing should follow:

~~~text
Seed MongoDB document
       |
       v
MongoDbMessageSource + poller
       |
       v
QueueChannel test sink
       |
       v
JUnit receive(timeout) + assert
~~~

A dedicated test flow can terminate at a `QueueChannel` instead of the real handler:

~~~java
@Bean("mongoTestSink")
public org.springframework.integration.channel.QueueChannel testSink() {
    return new org.springframework.integration.channel.QueueChannel(16);
}
~~~

In the **test-specific** configuration, route the splitter output to `mongoTestSink`. JUnit waits:

~~~java
Message<?> result = testSink.receive(5000);
assertNotNull(result, "No MongoDB event received");
assertInstanceOf(InboxEvent.class, result.getPayload());
assertEquals("evt-101", ((InboxEvent) result.getPayload()).id());
~~~

This is an **illustrative assertion snippet**, placed in a test class that injects `testSink` and uses a seeded context. Separate the test flow from the business handler so two consumers do not compete for the same `QueueChannel`.

Cases to cover:

1. Query returns **0 documents**: no message arrives in the test sink after a finite timeout.
2. Query returns **1 or more documents**: verify the `List` payload before the splitter and individual entities after the splitter.
3. Two `NEW` documents exist: ensure `maxMessagesPerPoll(1)` is not misunderstood as returning only one document.
4. Let the read-only query run for multiple cycles: confirm duplicate message emission occurs.
5. Enable `update(...)` in a **separate test**: inspect the MongoDB status after polling and evaluate a crash before processing.
6. Simulate MongoDB going down and coming back up: verify error policy, readiness, and retry.
7. Run two instances with the same query: test duplicate claims/idempotency rather than assuming the adapter solves it automatically.
8. Stop/start the endpoint: verify non-`DONE` documents can be recovered according to policy.

**Clean up lab data** using a dedicated test collection/database; never run destructive test suites against production MongoDB.

## 15. Security and Access Control

- Use a MongoDB account with **least privilege**: read only the required collections and grant update only if the adapter genuinely needs to modify status.
- Never hard-code credentials, connection strings containing passwords, or tokens in source code/logs.
- Configure TLS, network policies, connection permissions, secret rotation, and appropriate timeouts per environment.
- Restrict untrusted `query-expression` / `collection-name-expression`; **never let user input arbitrarily control the collection/query**.
- Validate document types/sizes/schemas before publishing to HTTP, Kafka, JMS/AMQP, or email.
- If documents contain sensitive data, log by `eventId` and error code rather than dumping the entire document.
- With frequent polling, configure indexes, batch limits, and backoff to avoid overloading MongoDB.

MongoDB is a durable data source, but **source durability does not equal end-to-end pipeline reliability**. If a handler sends data to another system and then crashes, the record may need a retry; when retried, duplicate side effects must be prevented.

## 16. Comprehensive Hands-On Lab

Exercise: build a **MongoDB → Spring Integration → telemetry processing** service, extensible to Kafka or HTTP as needed.

### Part A — Basic Polling

1. Create the `adapter_lab` database, `inbox_events` collection, and seed two `status=NEW` documents.
2. Write `InboxEvent` with `@Document`, `@Id`, and the corresponding fields.
3. Configure `MongoDb.inboundChannelAdapter(...)`, `entityClass(InboxEvent.class)`, `collectionName("inbox_events")`.
4. Use `Pollers.fixedDelay(5000).maxMessagesPerPoll(1)`, logging each query and each processed message.
5. Try **removing `split()`**: observe the `List` payload. Add `split()` back so each event arrives in its own message.
6. Run across two cycles without updating status; explain why the same documents reappear.

### Part B — Query and Lifecycle

1. Use a `Query` with `limit(50)`, sorted by `createdAt` and `_id`; explain why `maxMessagesPerPoll` does not replace a query limit.
2. Create a few additional `status=DONE` documents and verify the `NEW` query does not read them.
3. Stop MongoDB in the lab environment, observe poll errors, restart it, and verify recovery.
4. Stop/start the polling endpoint; distinguish between unread documents, documents emitted as messages, and documents business-committed.

### Part C — Reliability

1. Use `update(new Update().set("status", "CLAIMED"))` in a separate test and check whether the documents still match the `NEW` query.
2. Simulate a crash after claiming but before processing; propose a lease and recovery mechanism.
3. Run two workers reading the same collection; describe the race risk and use an atomic claim when needed.
4. Create a downstream unique key from `_id` to prevent duplicates on retry.
5. Distinguish Spring Integration transaction synchronization from real MongoDB transactions.
6. Design metrics for query count, document count, processing lag, retries, and errors.

### Part D — Integrating Other Systems

1. Transform `InboxEvent` into a DTO sent to Kafka/JMS/AMQP via `MessageChannel`, selecting only allowed fields.
2. If replacing polling with a change stream, list the prerequisites and how to manage resume tokens.
3. For large data volumes or replay requirements, consider the outbox/broker pattern and idempotent consumers.
4. Compare the MongoDB inbound adapter with the outbound gateway when reading a document on an HTTP request.

**Self-assessment questions:**

- Who triggers `MongoDbMessageSource.receive()`?
- Why can `expectSingleResult(false)` produce a `Message<List<T>>`?
- Does `maxMessagesPerPoll(1)` limit the query to returning exactly one document?
- Why does a repeated `status=NEW` query re-read data?
- Does `update(...)` at the source mean the handler has committed?
- How do you prevent two instances from processing the same document concurrently?
- What information does `MongoHeaders.COLLECTION_NAME` provide?
- When there are no documents, does the adapter emit an empty message or create no message?
- Why does `PseudoTransactionManager` not automatically turn all MongoDB operations into a transaction?
- When should you choose change stream or outbound gateway instead of polling inbound?

## 17. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): inbound adapter, query, XML, update expression, change stream, reactive, and transaction synchronization.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): `inboundChannelAdapter` factory, MongoOperations/MongoDatabaseFactory overloads.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): `find`/`findOne`, List or entity payloads, empty results.
- [Spring Integration API — MongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): `entityClass`, `collectionName`, `expectSingleResult`, `update`.
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html): poller, fixed-delay, max-messages-per-poll, transaction.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoTemplate`, `Query`, entity mapping, indexes, and transactions.

## Conclusion

The **MongoDB inbound channel adapter** is the component that **reads MongoDB on a poll schedule** and places results onto a `MessageChannel`. When using `MongoDbMessageSource`, remember that **a single poll can emit one message containing a List of documents**; the splitter and `expectSingleResult` determine how data reaches the handler.

In **SPRING_INTEGRATION_ADAPTERS**, the adapter only solves **how data is received from the source**. Business reliability also depends on queries, batch limits, processing state, claim/lease, idempotency, retries, transactions, and lifecycle management. To connect data from MongoDB to HTTP, Kafka, JMS, AMQP, files, SFTP, or other databases, define clear message contracts and decide when a document is truly considered **completely processed**.
