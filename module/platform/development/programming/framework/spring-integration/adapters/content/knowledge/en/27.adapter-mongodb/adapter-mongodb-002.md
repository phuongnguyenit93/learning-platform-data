# MongoDB Outbound Channel Adapter in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Describe how the **MongoDB outbound channel adapter** receives a `Message<?>` from a `MessageChannel` and writes the payload to a collection.
- Distinguish between a **one-way outbound adapter**, a **request/reply outbound gateway**, a poller-driven inbound adapter, and a reactive outbound adapter.
- Create a `MongoDbStoringMessageHandler` with `MongoOperations`, attach it to an IntegrationFlow using Java DSL `.handle(...)`, and write the equivalent XML configuration.
- Select a fixed collection or use an expression on a **controlled** header; understand the roles of `MongoTemplate` and `MongoConverter`.
- Distinguish between `save`, `insert`, `updateFirst`, and `upsert`; understand how a stable `_id` helps prevent duplicate records without automatically creating end-to-end exactly-once semantics.
- Preprocess `byte[]`, JSON, DTOs, and `List<T>`; verify mapping, write errors, transactions, write concern, retries, and idempotency.
- Test the message-to-document path using a MongoDB test instance, and monitor latency, queue depth, and consumer lifecycle.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, practicing flows across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases along with message contracts, errors, and connection lifecycles. In this lesson, **MongoDB is the write target**, and Spring Integration delivers normalized data to the storage handler.

## 1. Problem: Writing Telemetry from an External System to MongoDB

A Spring Boot service receives events from UDP, HTTP, or Kafka and wants to persist records after validation:

~~~json
{
  "_id": "evt-1001",
  "deviceId": "node-7",
  "sequence": 42,
  "temperatureC": 26.5,
  "measuredAt": "2026-11-23T02:00:00Z",
  "source": "udp"
}
~~~

~~~mermaid
flowchart LR
    A["UDP / HTTP / Kafka / SFTP"] --> B["Inbound adapter or gateway"]
    B --> C["Deserialize + validate"]
    C --> D["MessageChannel: toMongo"]
    D --> E["MongoDbStoringMessageHandler"]
    E --> F["MongoOperations.save"]
    F --> G["MongoDB collection<br/>telemetry_events"]
~~~

The producer sends `Message<TelemetryRecord>` to the input channel; the MongoDB writer takes the **payload** and writes it. The saved object is typically queried back via `MongoTemplate` or a repository if business logic needs to inspect the result.

**Note:** The outbound adapter **does not automatically send a reply message** containing the document ID or write result. If the business flow requires a response over a channel, you must design a gateway/service with an appropriate response contract. Also, a successful `send()` does not prove that the business chain across all systems has completed.

## 2. Position of MongoDB Outbound in Spring Integration

| Component | Role | Trigger Mechanism |
|---|---|---|
| **MongoDB inbound channel adapter** | Queries MongoDB and pushes results to an output channel | **Poller** |
| **MongoDB outbound channel adapter** | Writes the payload into a MongoDB collection | Message arriving on **input channel** |
| **MongoDB outbound gateway** | Queries MongoDB and returns a response message | Request message and reply channel |
| **MongoDB change stream inbound** | Emits messages when change events occur | Subscription/change stream |
| **Reactive MongoDB outbound adapter** | Writes using ReactiveMongoOperations | Reactive/asynchronous pipeline |
| **MongoOperations in a service** | Executes custom CRUD/transactions | Application code call |

**The MongoDB outbound adapter does not need its own poller.** It is a message consumer: when upstream emits a message, the handler processes it according to the channel's semantics. For instance, an SFTP inbound adapter uses a poller to fetch files and forwards them to MongoDB outbound; the poller lives on **SFTP inbound**, not on the writer.

### 2.1. Using the Right Class and DSL

In Spring Integration, the blocking writer class is:

~~~java
org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler
~~~

The Java DSL can accept that bean via `.handle(handler)`. Do not confuse it with `MongoDb.outboundGateway(...)` — that is a query gateway with a reply. The `MongoDb.reactiveOutboundChannelAdapter(...)` API is for **reactive** pipelines; do not assume a blocking factory named `MongoDb.outboundChannelAdapter(...)` exists in every version.

## 3. Payload and MessageHeaders Are Not the Same Data

A Spring message entering the MongoDB writer:

~~~text
Message<TelemetryRecord>
  payload:
    id = "evt-1001"
    deviceId = "node-7"
    sequence = 42
    measuredAt = 2026-11-23T02:00:00Z
  headers:
    id = Spring Message UUID
    timestamp = Spring Message creation time
    correlationId = ...
    mongoTargetCollection = ...
~~~

`MongoDbStoringMessageHandler` takes the **message payload** to save. Message headers are Spring Integration metadata; they **do not automatically become fields in the BSON document**.

| Component | Purpose | Stored in MongoDB by default? |
|---|---|---|
| Entity `id` / `@Id` | Maps to document `_id` | Yes, if the converter is configured accordingly |
| `deviceId`, `sequence` | Business fields | Yes |
| `MessageHeaders.ID` | Internal message identifier | Not automatically |
| `MessageHeaders.TIMESTAMP` | Time the message was created | Not automatically |
| `headers['mongoTargetCollection']` | Selects collection if expression is configured | Not automatically |
| `correlationId` | Traces a message flow | Only if explicitly mapped into the payload |

A retried event may be wrapped in a **new message** with a different UUID. To identify the business record and support idempotency, use a **stable event ID** in the payload, not `MessageHeaders.ID`.

## 4. Preparing Dependencies and Connection

For a **Spring Boot 3.x** project using synchronized dependency management:

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
~~~

When using another Spring Boot major version, verify the starter artifact names, BOM, and Spring Integration/Spring Data compatibility. This lesson uses **blocking MongoOperations**, not `ReactiveMongoOperations`.

In the lab's `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

The URI above is only **local MongoDB for learning**. Production requires secrets/TLS, connection timeouts, write concern, least-privilege access permissions, and the proper database/collection. Spring Boot typically creates a `MongoTemplate` bean that can be injected as `MongoOperations` when the MongoDB starter is properly configured.

## 5. Designing an Entity with a Durable Identifier

Java 17+:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryRecord(
        @Id String id,
        String deviceId,
        long sequence,
        BigDecimal temperatureC,
        Instant measuredAt,
        String source) {
}
~~~

Meaning:

- `id` (e.g., `evt-1001`): event ID **stable across retries**; mapped to `_id`.
- `deviceId` and `sequence`: source identifier and business sequence, usable for contract-based deduplication.
- `temperatureC`: `BigDecimal` value, subject to Spring Data/`MongoConverter` mapping.
- `measuredAt`: timestamp when the data was generated at the source, not necessarily when MongoDB writes it.
- `source`: application-normalized source such as `udp`, `http`, or `kafka`.

**Do not generate a new random ID on every retry of the same event** if the goal is avoiding duplicate documents. Any field from an external source must be validated, including `id`, `deviceId`, measurements, and timestamps.

## 6. Java DSL Configuration: Writing a Message to MongoDB

Create a `DirectChannel` as the input channel, a `MongoDbStoringMessageHandler` bean, and an `IntegrationFlow` wiring them together:

~~~java
package example.mongodb;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoOutboundConfig {

    @Bean("toMongo")
    public MessageChannel toMongo() {
        return new DirectChannel();
    }

    @Bean("mongoWriter")
    public MongoDbStoringMessageHandler mongoWriter(
            MongoOperations mongoOperations) {

        MongoDbStoringMessageHandler handler =
                new MongoDbStoringMessageHandler(mongoOperations);

        handler.setCollectionNameExpression(
                new LiteralExpression("telemetry_events"));

        return handler;
    }

    @Bean
    public IntegrationFlow mongoOutboundFlow(
            @Qualifier("mongoWriter")
            MongoDbStoringMessageHandler writer) {

        return IntegrationFlow.from("toMongo")
                .handle(writer)
                .get();
    }
}
~~~

Explanation:

1. `toMongo` is the input channel for the MongoDB writer.
2. `MongoDbStoringMessageHandler(mongoOperations)` receives the database-connected Spring Data object.
3. `LiteralExpression("telemetry_events")` sets a static collection; do not let external requests decide arbitrarily.
4. `.handle(writer)` registers a **service-activating outbound endpoint**, without opening a poller.
5. With `DirectChannel`, dispatching to the handler is **synchronous** on the caller thread per channel semantics. Slow MongoDB writes can block the producer.
6. There is no default reply channel returning the `save` result. If a result/error response message is needed, it must be defined explicitly.

### 6.1. Producer Sending a Record

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class TelemetryPublisher {

    private final MessageChannel toMongo;

    public TelemetryPublisher(
            @Qualifier("toMongo") MessageChannel toMongo) {
        this.toMongo = toMongo;
    }

    public void publish(TelemetryRecord record) {
        if (record == null || record.id() == null
                || record.id().isBlank()
                || record.deviceId() == null
                || !record.deviceId().matches("[A-Za-z0-9_-]{1,64}")
                || record.sequence() < 0
                || record.temperatureC() == null
                || record.measuredAt() == null
                || record.source() == null
                || record.source().isBlank()) {
            throw new IllegalArgumentException("Invalid telemetry");
        }

        boolean accepted = toMongo.send(
                MessageBuilder.withPayload(record).build());
        if (!accepted) {
            throw new IllegalStateException(
                    "MongoDB outbound message was not accepted");
        }
    }

    public void publishExample() {
        publish(new TelemetryRecord(
                "evt-1001",
                "node-7",
                42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp"));
    }
}
~~~

With this configuration, `publishExample()` sends a single `Message<TelemetryRecord>` to the MongoDB writer. If no error occurs, the handler saves the payload into the configured collection.

**Do not interpret `send()==true` as a business-level MongoDB commit ACK in all architectures.** In a synchronous flow with `DirectChannel`, MongoDB exceptions typically propagate back to the caller; if swapped for an `ExecutorChannel`/`QueueChannel`, the producer may receive the `send` return value before the database write finishes.

### 6.2. Verifying with mongosh

After publishing once in the lab environment:

~~~javascript
use adapter_lab

db.telemetry_events.findOne({ _id: "evt-1001" })
~~~

The expected result contains `_id`, `deviceId`, `sequence`, `temperatureC`, `measuredAt`, and `source`. The actual BSON types for timestamps/numbers may depend on the converter; in tests, read back using the entity class and assert **business values**, rather than strictly comparing a display JSON string.

## 7. Distinguishing save, insert, partial update, and upsert

In the blocking implementation, `MongoDbStoringMessageHandler` persists payloads via **`MongoOperations.save(payload, collectionName)`**. Therefore, **save** behavior is central to the outbound adapter.

| Operation | Example API | When document already exists | When to use |
|---|---|---|---|
| **save** | `mongoOperations.save(record, collection)` | May replace/overwrite the document by `_id`, subject to mapping/version rules | Saving full document state |
| **insert** | `mongoOperations.insert(record, collection)` | Duplicate `_id` typically throws duplicate key | Immutable events, create-only semantics |
| **partial update** | `updateFirst(Query, Update, ...)` | Modifies specified fields | Patching status, counters, or metadata |
| **conditional upsert** | `upsert(Query, Update, ...)` | Updates if matched; inserts if absent | Conditional/business upserts |
| **findAndModify** | `findAndModify(...)` | Conditionally modifies and returns document per options | Claiming jobs/leases |
| **outbound gateway** | MongoDb gateway query | Produces a reply message | Need query results rather than write-only |

### 7.1. Save with the Same _id Is Not "Ignore Duplicate"

Suppose document `evt-1001` already has a `status=DONE` field updated by another service. If you `save` an old payload without the `status` field, `save` may **replace the document** and lose the new field, depending on schema/versioning.

Principles to remember:

- **Save is not a patch.** Do not use the default outbound writer when you only want to update one field of an existing record.
- **Same `_id` avoids creating extra documents, not overwriting newer data.**
- If optimistic locking is needed, study `@Version` and corresponding `MongoTemplate.save` behavior, then test version conflicts.
- If an event must be written once and updates are disallowed, use a custom handler calling `insert`, combined with unique keys and business-level duplicate classification.
- If updating conditionally such as `status=PROCESSING`, use `updateFirst`/`findAndModify` with appropriate owner/version conditions.

### 7.2. Status Update Example: A Separate Handler, Not a Writer Option

The following snippet is **not a patch mode of `MongoDbStoringMessageHandler`**. It is a separate Service Activator when the application needs field-level updates:

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StatusPatchHandler {

    private final MongoOperations mongoOperations;

    public StatusPatchHandler(MongoOperations mongoOperations) {
        this.mongoOperations = mongoOperations;
    }

    @ServiceActivator(inputChannel = "statusPatches")
    public void handle(StatusPatch request) {
        Query query = Query.query(
                Criteria.where("_id").is(request.eventId())
                        .and("status").is("PROCESSING"));
        Update update = new Update().set("status", "DONE");

        var result = mongoOperations.updateFirst(
                query, update, "telemetry_events");

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "No PROCESSING event: " + request.eventId());
        }
    }

    public record StatusPatch(String eventId) {}
}
~~~

You must declare the `statusPatches` channel and have a producer send `StatusPatch` separately. In multi-worker systems, add owner/version/lease conditions so one worker cannot mistakenly complete another worker's job.

## 8. Selecting a Collection with LiteralExpression or SpEL

### 8.1. Fixed Collection

Configuration from section 6:

~~~java
handler.setCollectionNameExpression(
        new LiteralExpression("telemetry_events"));
~~~

This is the safe choice for a fixed event stream: easy to authorize, index, and monitor.

### 8.2. Collection from a Controlled Header

Suppose trusted upstream logic has set a header:

~~~text
headers["mongoTargetCollection"] = "telemetry_events"
~~~

You can configure:

~~~java
import org.springframework.expression.spel.standard.SpelExpressionParser;

handler.setCollectionNameExpression(
        new SpelExpressionParser().parseExpression(
            "headers['mongoTargetCollection']"));
~~~

This **replaces** `LiteralExpression`; do not use both at once. Spring Integration evaluates the expression per message to select the collection.

**Risk:** if external HTTP/Kafka/UDP requests are allowed to attach a header containing any collection name, a client could force the writer into the wrong collection or cross tenant boundaries. Before the handler, map validated logical codes through an allowlist:

~~~java
String allowedCollection = switch (trustedCategory) {
    case "telemetry" -> "telemetry_events";
    case "audit" -> "audit_events";
    default -> throw new IllegalArgumentException(
            "Unsupported MongoDB target");
};
~~~

Here `trustedCategory` must be an application-authorized value, not an untrusted header. For multi-tenant systems, enforce **tenant ownership/authorization**, not just a regex on the collection name.

### 8.3. Two Ways to Instantiate the Handler

~~~java
// Option A: Pre-configured Spring Data MongoOperations/MongoTemplate:
MongoDbStoringMessageHandler a =
        new MongoDbStoringMessageHandler(mongoOperations);

// Option B: Using MongoDatabaseFactory and a custom MongoConverter:
MongoDbStoringMessageHandler b =
        new MongoDbStoringMessageHandler(mongoDatabaseFactory);
b.setMongoConverter(mongoConverter);
~~~

Only use `setMongoConverter` per the API contract for a factory-constructed handler; **do not also call it on a handler constructed with `MongoOperations`** if the API forbids it. In XML, `mongo-template` and `mongodb-factory` are alternatives—do not declare both for the same adapter.

## 9. Payload Types: DTO, JSON, byte[], and List

| Payload received from upstream | Recommendation |
|---|---|
| `TelemetryRecord` with `@Id` | Pass to writer after validation |
| `org.bson.Document` | Can be saved via MongoDB mapping; validate schema and BSON types |
| `Map<String,Object>` | Explicitly define mapping, ID, and valid fields |
| JSON `String` | Parse/validate into a DTO or Document before writing |
| `byte[]` from UDP/SFTP/file | Decode with charset/protocol and build a DTO |
| `List<TelemetryRecord>` | Use a **splitter** to turn elements into individual messages |

For example, a MongoDB inbound adapter might emit `Message<List<InboxEvent>>`. Do not assume the outbound writer automatically saves each list element as a separate document. Add a splitter:

~~~mermaid
flowchart LR
    A["Message<List<TelemetryRecord>>"] --> B["Splitter"]
    B --> C["Message<TelemetryRecord>"]
    C --> D["toMongo"]
    D --> E["MongoDB writer"]
~~~

Sub-flow:

~~~java
@Bean
public IntegrationFlow batchToMongoFlow() {
    return IntegrationFlow.from("batchInput")
            .split()
            .channel("toMongo")
            .get();
}
~~~

In a real context, `batchInput` and `toMongo` must be declared. This snippet **does not automatically add batch insert/bulk write**; each split message typically results in one handler write call. If bulk operations are required, design a dedicated handler with appropriate batch size, transaction/retry, and idempotency.

**Conversion principle:** do not pass unvalidated bytes from UDP or unvalidated JSON directly to the database writer expecting `MongoConverter` to enforce all business schema constraints.

## 10. Equivalent XML Configuration

When the project uses Spring Integration XML:

~~~xml
<!-- XML file with appropriate int and int-mongodb namespaces -->
<int:channel id="toMongoXml"/>

<int-mongodb:outbound-channel-adapter
        id="mongoOutboundWriter"
        channel="toMongoXml"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"/>
~~~

Here `mongoTemplate` is an already-declared bean; `channel` is the **input channel** of the outbound adapter.

If using a factory/converter:

~~~xml
<int-mongodb:outbound-channel-adapter
        id="mongoOutboundWithFactory"
        channel="toMongoXml"
        mongodb-factory="mongoDbFactory"
        mongo-converter="mongoConverter"
        collection-name="telemetry_events"/>
~~~

These two snippets are **two alternatives**; do not register both at the same time expecting every message to be delivered to both. With multiple subscribers on a `DirectChannel`, messages are not broadcast to all subscribers; if fan-out is intended, use `PublishSubscribeChannel` or a wire tap per your architecture.

Attributes of the outbound writer:

- `collection-name`: static collection.
- `collection-name-expression`: SpEL expression returning the collection name.
- `mongo-template`: Spring Data `MongoTemplate` bean.
- `mongodb-factory` and `mongo-converter`: alternative configuration.
- `channel`: channel consumed by the endpoint.

**Do not use query/poller attributes from the MongoDB inbound adapter** assuming the outbound writer will "scan a collection on a schedule". Data flows in opposite directions.

## 11. Write Errors, Timeouts, and Error Channels

Common failure modes:

| Scenario | Possible cause | How to respond |
|---|---|---|
| Connection timeout | MongoDB down, DNS/route issue, exhausted pool | Bounded retry, backoff, alerting |
| Permission denied | Credentials/role lack write privileges | Fix configuration/roles; do not retry infinitely |
| Mapping/validation error | Missing fields, wrong types | Reject/quarantine; do not retry deterministically invalid data |
| Duplicate key | Unique index/`_id` violated during insert | Classify duplicates by event ID |
| Optimistic locking conflict | `@Version` older than DB | Re-read/reconcile per business rules |
| Ambiguous write result | Timeout after server may have already written | Retry with stable ID; check state before deciding |
| Slow MongoDB | I/O, indexes, connection pool, overload | Bounded queues, measure latency, scaling |
| Business flow fails after save | Subsequent step fails | Design transactions/outbox and idempotency |
| Wrong target collection | Unvalidated header routing | Allowlist, authorization checks, and tracing |

### 11.1. DirectChannel and Synchronous Errors

~~~text
producer.send(message)
    |
    v
DirectChannel
    |
    v
MongoDbStoringMessageHandler
    |
    v
MongoOperations.save(...)
    |
    +-- Normal: call returns
    +-- Exception: may propagate to caller (MessagingException)
~~~

With a synchronous configuration like section 6, the producer thread waits on MongoDB I/O. This is a simple choice, though timeouts on HTTP/UDP producers or calling services must be considered.

### 11.2. ExecutorChannel, QueueChannel, and Asynchronous Errors

If an executor or queue sits between the producer and writer, message acceptance may happen **before** MongoDB finishes saving. Exceptions may go to an error channel or be handled in the worker/poller rather than reaching the caller.

You should design:

1. Queues with **bounded capacity**.
2. Retry/backoff/jitter by error category; never retry infinitely.
3. Dead-letter/quarantine for schema-invalid payloads.
4. The same **event ID** across all attempts.
5. Metrics distinguishing `accepted`, `save succeeded`, and `business committed`.
6. A durable outbox/broker if process crashes must not lose pending messages.

**An in-memory `QueueChannel` does not become a durable queue**, and `MessageChannel.send()==true` does not mean MongoDB has acknowledged the write.

## 12. Idempotency, Write Concern, and Transactions

### 12.1. When a Write Times Out, the Outcome May Be Unknown

A scenario:

~~~mermaid
sequenceDiagram
    participant S as Producer
    participant I as Integration flow
    participant M as MongoDB
    S->>I: Event evt-1001
    I->>M: save(_id=evt-1001)
    M-->>I: Response lost
    Note over I: Timeout, unknown whether write succeeded
    S->>I: Retry same event ID
    I->>M: save(_id=evt-1001) again
~~~

If a retry generates a new ID, duplicate documents can be created. If using **the same `_id`**, the retry may not create an extra document, yet it can still **overwrite** other changes. If events are immutable, evaluate an **insert-only + unique key** design instead of replace.

### 12.2. Business Unique Key

One way to strengthen protection when devices emit sequenced events:

~~~javascript
db.telemetry_events.createIndex(
  { deviceId: 1, sequence: 1 },
  { unique: true }
)
~~~

**Lab example only.** If a device resets its sequence on reboot, include an `epoch` or global event ID in the unique key. Before creating a unique index on a real collection, check for existing duplicates, index overhead, retention, and schema compatibility.

### 12.3. MongoDB ACK and Business ACK Are Not the Same

MongoDB provides **write concern** to specify write acknowledgment in a given deployment (such as primary or majority acknowledgment). However, a MongoDB write ACK **does not prove that the Kafka offset is committed, the HTTP client received its response, or the source file was marked complete**.

Example:

~~~mermaid
sequenceDiagram
    participant K as Kafka consumer
    participant F as Integration flow
    participant M as MongoDB
    K->>F: Event evt-1001
    F->>M: save(evt-1001)
    M-->>F: Write acknowledged
    Note over F: Crash before committing offset
    K->>F: Redelivery of same event
    F->>M: Save again, idempotency required
~~~

For files/SFTP, delete or move the source file per contract only after data has been written successfully. For JMS/AMQP, design broker ACKs/transactions. Raw UDP does not guarantee delivery; when certainty is needed, add application-level ACKs or switch transports.

### 12.4. MongoDB Transactions Do Not Automatically Cover Other Systems

If business logic needs to modify **multiple documents atomically**, you need MongoDB transactions on a supported deployment, `MongoTransactionManager`, and proper transaction boundaries. Do not assume `MongoDbStoringMessageHandler` opens a multi-document transaction automatically.

Even when a MongoDB transaction commits, it does not span HTTP, Kafka, JMS, or the filesystem. Synchronizing state across systems usually requires **outbox, saga, retries, and reconciliation**.

## 13. Lifecycle and Graceful Shutdown

The outbound handler is a consumer endpoint managed by Spring Integration:

- Beans, input channels, and subscriptions are wired during Spring context initialization.
- While the endpoint is running, messages arriving on the channel are handled according to dispatch rules.
- The writer has no poller of its own; connection errors may surface **when handling a message**, even if the application started successfully earlier.
- During shutdown, coordinate stopping producers, halting new message intake, and finishing in-flight operations.
- When using `ExecutorChannel`/`QueueChannel`, pending messages may still remain. Stopping the endpoint does not guarantee those messages have been durably written.
- If the business cannot tolerate lost events, use a durable source/outbox and a post-restart resume process.

Separate these milestones clearly:

~~~text
A. Producer creates message
B. Channel accepts message
C. MongoDB handler starts save
D. MongoDB acknowledges write per write concern
E. Business confirms completion / upstream ACK
~~~

Do not issue a business ACK at **B** if the contract requires waiting for **D or E**. When a write times out with an unknown result, reconcile using the event ID and proceed with appropriate retry/reconciliation.

## 14. Testing the MongoDB Outbound Adapter

### 14.1. Unit Testing the Validator

Separate validation logic from I/O:

~~~java
package example.mongodb;

public final class TelemetryValidator {

    public void validate(TelemetryRecord value) {
        if (value == null
                || value.id() == null || value.id().isBlank()
                || value.deviceId() == null
                || value.deviceId().isBlank()
                || value.temperatureC() == null
                || value.measuredAt() == null
                || value.sequence() < 0) {
            throw new IllegalArgumentException("Invalid telemetry");
        }
    }
}
~~~

JUnit:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TelemetryValidatorTest {

    @Test
    void validEventIsAccepted() {
        TelemetryRecord event = new TelemetryRecord(
                "evt-1001", "node-7", 42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp");

        assertDoesNotThrow(
                () -> new TelemetryValidator().validate(event));
    }

    @Test
    void missingIdIsRejected() {
        TelemetryRecord event = new TelemetryRecord(
                null, "node-7", 42L,
                new BigDecimal("26.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "udp");

        assertThrows(IllegalArgumentException.class,
                () -> new TelemetryValidator().validate(event));
    }
}
~~~

Unit tests **do not verify the MongoDB connection, mapping, or writer**.

### 14.2. Integration Testing with a MongoDB Test Instance

Use a dedicated test MongoDB instance (or Testcontainers when Docker is available on the runner). The test sends a message through `toMongo` and reads the document back:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoOutboundIntegrationTest {

    @Autowired
    @Qualifier("toMongo")
    MessageChannel toMongo;

    @Autowired
    MongoOperations mongoOperations;

    @Test
    void writesPayloadIntoExpectedCollection() {
        String id = "test-" + UUID.randomUUID();
        TelemetryRecord event = new TelemetryRecord(
                id, "node-test", 43L,
                new BigDecimal("24.5"),
                Instant.parse("2026-11-23T02:00:00Z"),
                "test");

        try {
            assertTrue(toMongo.send(
                    MessageBuilder.withPayload(event).build()));

            TelemetryRecord stored = mongoOperations.findById(
                    id, TelemetryRecord.class, "telemetry_events");

            assertNotNull(stored);
            assertEquals("node-test", stored.deviceId());
            assertEquals(43L, stored.sequence());
            assertEquals(0, stored.temperatureC()
                    .compareTo(new BigDecimal("24.5")));
        } finally {
            mongoOperations.remove(
                Query.query(Criteria.where("_id").is(id)),
                "telemetry_events");
        }
    }
}
~~~

**Prerequisite:** configure the context to point to a real **test** MongoDB instance. This code does not start a server or container on its own and must never point to a production database when tests perform cleanup. When placing classes into a project, use matching packages or proper imports.

### 14.3. Recommended Test Matrix

| Test case | What to assert |
|---|---|
| Send a valid DTO | Document exists in the expected collection |
| Resend same ID and payload | No extra documents created when saving by contract ID |
| Send same ID with different payload | Detect risk of replace/overwrite |
| Null ID | Validator rejects before DB auto-generates an ID |
| Upstream sends JSON string | Parse/validate step runs before writer |
| Message contains List | Split into individual messages or use a dedicated bulk handler |
| MongoDB temporarily down | Error handling, retries, and metrics behave properly |
| Dynamic collection | Allowlist and authorization are accurate |
| Producer via ExecutorChannel | Do not treat `send == true` as DB commit |
| Crash after DB write before source ACK | Redelivery requires idempotency |

Do not claim "exactly once" just because a test sees one document remaining after saving the same ID twice; **two write operations** may have executed.

## 15. Observability, Performance, and Security

Suggested metrics, to be implemented or mapped from actual instrumentation:

| Metric | Meaning |
|---|---|
| `mongo_outbound_received_total` | Messages arriving at writer |
| `mongo_outbound_validation_rejected_total` | Payloads rejected before save |
| `mongo_outbound_save_attempt_total` | Number of save attempts |
| `mongo_outbound_save_success_total` | Writes succeeded per contract |
| `mongo_outbound_save_error_total` | Write errors |
| `mongo_outbound_write_duration_seconds` | Write duration |
| `mongo_outbound_retry_total` | Retry count |
| `mongo_outbound_pending_depth` | Messages in queue/outbox |
| `mongo_outbound_dead_letter_total` | Messages sent to quarantine |
| `mongo_outbound_business_committed_total` | Events completed per business contract |

Be careful with metric labels by `eventId`/`deviceId` because they can cause unbounded cardinality growth.

**Performance:** do not send huge `List`s without understanding handler semantics; consider dedicated bulk writes with batch sizes, proper indexes, and bounded queues. MongoDB enforces a **maximum 16 MiB BSON document** limit in standard configurations; measure mapped data size, not only JSON string length. Blocking `MongoOperations` are unsuitable for running directly on non-blocking reactive event loops.

**Security:** use a least-privilege MongoDB account, TLS where needed, and a secret manager. Never allow unvalidated headers to choose collections arbitrarily. Validate schemas/versions/IDs, enforce length limits, and avoid logging raw sensitive documents. Bound retries so DB outages do not amplify load; check auditing and retention per business data rules.

## 16. Comprehensive Hands-On Lab

Build an **HTTP/UDP/Kafka → Spring Integration → MongoDB** pipeline:

1. Create MongoDB `adapter_lab`, collection `telemetry_events`, and connect using `MongoOperations`.
2. Define the `TelemetryRecord` entity with `@Id` and validated fields.
3. Create `toMongo`, `MongoDbStoringMessageHandler`, `LiteralExpression("telemetry_events")`, and `IntegrationFlow.from("toMongo").handle(writer)`.
4. Send `Message<TelemetryRecord>` and verify the document via `mongosh` and an integration test.
5. Resend the same ID/same payload, then same ID/changed payload: explain the difference between idempotency and overwrite.
6. Try custom `insert` to require insert-only and `updateFirst` to patch; do not assume the default writer switches operations per message.
7. Connect an upstream producing `Message<List<T>>` and add a splitter.
8. Switch collection selection from static to dynamic **only after an allowlist step**.
9. Stop the lab MongoDB, observe errors on `DirectChannel`; try `ExecutorChannel` and distinguish send success from commit.
10. Propose an outbox, retry/backoff, unique key, and a crash test after DB write but before source ACK.
11. Add metrics for received, save attempts/success/error, latency, queue depth, and retries.
12. If a reply containing query data is desired, compare this adapter with `MongoDb.outboundGateway(...)`.

**Self-assessment questions:**

- Why does the MongoDB outbound channel adapter not have its own poller?
- How do `MongoDbStoringMessageHandler` and `MongoDb.outboundGateway(...)` differ?
- Does the handler save the message payload or all message headers?
- Should `MessageHeaders.ID` be used as a document's idempotency key?
- How does `save` differ from `insert` and `updateFirst`?
- When can `save` overwrite changes made by another writer?
- If you only need to update `status`, what approach should you use?
- Why should `List<T>` pass through a splitter when writing individual documents?
- Why does `send()==true` with `ExecutorChannel` not prove the DB has written?
- After a timeout, why does keeping the same event ID matter?
- Does MongoDB write concern cover Kafka offsets or HTTP responses?
- How do you secure collection selection driven by a header?

## 17. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB outbound adapter, XML, outbound gateway, and reactive variants.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): constructors, collection name expression, and converter.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): inbound, gateway, and reactive factories.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`, `ExecutorChannel`, and queue semantics.
- [Spring Data MongoDB — CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): save, insert, update, upsert, optimistic locking, and transactions.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoTemplate`, entity mapping, converters, indexes, and transactions.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): definitions and write acknowledgment levels.

## Conclusion

The **MongoDB outbound channel adapter** is a Spring Integration **payload-writing** endpoint. In the blocking API, `MongoDbStoringMessageHandler` receives a `Message` on its input channel and persists the payload into a MongoDB collection via `MongoOperations`; it can be configured using Java DSL or XML.

Proper design requires **strongly typed entities with stable IDs**, explicit collections, understanding that **`save` is neither insert-only nor a partial update**, and controlling errors/timeouts, transactions, and idempotency. A write ACK from MongoDB does not prove that associated HTTP, SFTP, Kafka, JMS, AMQP, file, or UDP systems have completed the entire business workflow; that relies on ACK contracts, outbox patterns, retries, transactions, and end-to-end operational procedures.
