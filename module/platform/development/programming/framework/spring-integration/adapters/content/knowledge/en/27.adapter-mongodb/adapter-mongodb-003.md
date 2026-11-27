# MongoDbOutboundGateway in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of **`MongoDbOutboundGateway`** in a **request/reply** model, as opposed to MongoDB inbound/outbound channel adapters.
- Configure a MongoDB outbound gateway using **Java DSL**, a Java bean, or **XML** to receive requests from a `MessageChannel` and emit responses to a reply channel.
- Choose `MongoOperations`, collection, `entityClass`, and either a static query or a dynamic query using `queryFunction`/`queryExpression`.
- Distinguish between a **`List<T>` result by default** and a **single `T`** when `expectSingleResult(true)` is enabled, including how missing data is handled.
- Build per-request query APIs with `@MessagingGateway`, while understanding why a **static reply channel** and a caller's **temporary reply channel** should not be mixed.
- Use `MessageCollectionCallback` for specialized operations such as `countDocuments()`, without combining a callback with query attributes on the same endpoint.
- Constrain batch sizes, sorting, projections, timeouts, and authorization to prevent unsafe queries or returning excessive data.
- Test payloads, reply headers, empty results, DB errors, request timeouts, lifecycle, and scenarios involving HTTP, JMS, AMQP, Kafka, or other adapters.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module teaches connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing flows across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while emphasizing message contracts, errors, and connection lifecycles. In this lesson, **MongoDB is the query target**, and the application requests an answer for **a specific request**.

## 1. Problem: Querying MongoDB Immediately Upon Request

An HTTP endpoint receives a request: "Find the new telemetry records for device `node-7`." Data is stored in the `telemetry_events` collection:

~~~json
{
  "_id": "evt-101",
  "deviceId": "node-7",
  "sequence": 101,
  "status": "NEW",
  "temperatureC": 26.5,
  "createdAt": "2026-11-23T02:00:00Z"
}
~~~

The application needs to:

1. Receive `FindEventsRequest("node-7", 20)`.
2. Build a MongoDB `Query` filtering by device ID, status, and limiting to 20 documents.
3. Execute the query as a MongoDB operation at the outbound gateway.
4. Receive a reply of `List<TelemetryEvent>`.
5. Use the list to build an HTTP response, aggregate, or forward to another system.

~~~mermaid
sequenceDiagram
    participant A as HTTP / Messaging caller
    participant C as Request MessageChannel
    participant G as MongoDbOutboundGateway
    participant D as MongoDB
    A->>C: Message<FindEventsRequest>
    C->>G: Request + replyChannel header
    G->>D: find(query, TelemetryEvent.class)
    D-->>G: List<TelemetryEvent>
    G-->>A: Reply Message<List<TelemetryEvent>>
    Note over A: Caller inspects result, does not poll on its own
~~~

Difference from the MongoDB **inbound channel adapter**: **there is no poller to read the collection periodically**. The outbound gateway queries only when a **request message** arrives, and then produces a reply per the endpoint contract.

## 2. Distinguishing MongoDbOutboundGateway from Similar Components

| Component | Who triggers it? | Data direction | Main result |
|---|---|---|---|
| **MongoDB inbound channel adapter** | Poller invokes source periodically | MongoDB → MessageChannel | Emits messages from scheduled queries |
| **MongoDB outbound channel adapter** | Message on input channel | MessageChannel → MongoDB | **Writes** payload; one-way |
| **`MongoDbOutboundGateway`** | **Request message** arrives | MessageChannel → MongoDB → reply channel | **Queries and returns reply** |
| **MongoDB change stream inbound adapter** | MongoDB emits change event | MongoDB → MessageChannel | Notifies insert/update/delete per subscription |
| **`MongoTemplate` directly** | Java code calls method | Java service ↔ MongoDB | Returns values directly, no Integration endpoint needed |
| **MongoDB message store** | Queue/aggregator/claim-check | Spring Integration ↔ MongoDB | Stores message/group state, not a business query gateway |

**The word "outbound" indicates the direction in which the request is sent from the application to MongoDB**; it does not mean every outbound endpoint is one-way. `MongoDbOutboundGateway` extends `AbstractReplyProducingMessageHandler` and thus provides request/reply behavior; `MongoDbStoringMessageHandler` is a one-way writer.

### 2.1. When Should You Use a Gateway?

Use the outbound gateway when:

- You need lookups based on **per-request parameters**.
- You need results returned to an HTTP handler, command handler, validator, or workflow.
- You want to keep transform/filter/enrich/routing steps within an `IntegrationFlow`.
- You want to query a known collection and bound the returned data.
- You need a specialized operation based on `MessageCollectionCallback`.

Do not use the gateway as a "hidden poller". If the use case is periodically reading all `NEW` documents without a caller, use an **inbound adapter + poller**, a change stream, or an appropriate background job.

## 3. Nature of Requests, Replies, and Headers

A message arriving at the gateway contains:

~~~text
Request Message<FindEventsRequest>
  payload = FindEventsRequest("node-7", 20)
  headers:
    id = <Spring Message ID>
    replyChannel = <reply target>
    errorChannel = <error target>  (if present)
    correlationId = "lookup-101"
~~~

The gateway builds the MongoDB query, executes it, and produces a **reply message** containing the result. Appropriate headers are typically carried over according to Spring Integration's reply mechanism; system headers or filtered headers may not be copied verbatim. **Test actual header behavior** if downstream depends on `correlationId`, trace IDs, or tenant context.

| Component | Role | Notes |
|---|---|---|
| `requestChannel` | Channel from which gateway reads requests | Usually a `DirectChannel` |
| `replyChannel` | Channel receiving replies | Can be a statically configured channel or a temporary caller channel |
| `MessageHeaders.REPLY_CHANNEL` | Header indicating where to send replies | Not a field stored inside a MongoDB document |
| `MessageHeaders.ERROR_CHANNEL` | Suggests error routing path in some flows | Synchronous errors may throw back to the caller |
| `correlationId` | Links request and reply at messaging layer | Must be preserved in async/multi-branch flows |
| `query / queryFunction` | Defines the MongoDB filter | Never trust client payload/headers by default |
| `entityClass` | Result mapping type | Defaults to `org.bson.Document` if unspecified |

Do not use `MessageHeaders.ID` (internal message UUID) in place of MongoDB's business `_id`. A new request gets a new message ID even when retrieving the same document.

## 4. Preparing Spring Boot and MongoDB

### 4.1. Dependencies

For a Spring Boot **3.x** project with compatible BOM-managed versions:

~~~xml
<!-- Place these dependencies inside <dependencies> of pom.xml -->
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

Depending on the Spring Boot major version, the MongoDB starter name or compatible versions may vary. Use your project version's dependency management and the **blocking MongoDB driver**; do not mix with the reactive driver while learning synchronous `MongoOperations` calls.

### 4.2. MongoDB URI in the Lab

Example `application.yml` for Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/mongo_gateway_lab
~~~

The application will typically expose a `MongoTemplate`/`MongoOperations` bean when the MongoDB starter and connection configuration are valid. In production, URIs/credentials must come from managed secrets/configs, never placing passwords directly in docs or source code.

### 4.3. Seeding Data with mongosh

Run only against the lab database:

~~~javascript
use mongo_gateway_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-101",
    deviceId: "node-7",
    sequence: 101,
    status: "NEW",
    temperatureC: 26.5,
    createdAt: ISODate("2026-11-23T02:00:00Z")
  },
  {
    _id: "evt-102",
    deviceId: "node-7",
    sequence: 102,
    status: "NEW",
    temperatureC: 26.8,
    createdAt: ISODate("2026-11-23T02:00:01Z")
  },
  {
    _id: "evt-103",
    deviceId: "node-8",
    sequence: 103,
    status: "DONE",
    temperatureC: 25.9,
    createdAt: ISODate("2026-11-23T02:00:02Z")
  }
])

db.telemetry_events.find(
  { deviceId: "node-7", status: "NEW" }
).sort({ createdAt: 1, _id: 1 })
~~~

Calling `insertMany` a second time with the same `_id` causes a duplicate-key error. When repeating the lab, use new IDs or seed via upsert in the **test database**; never delete production collections.

## 5. Entity and Result Contract

Define a Java 17+ entity:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String deviceId,
        long sequence,
        String status,
        BigDecimal temperatureC,
        Instant createdAt) {
}
~~~

Spring Data MongoDB converts MongoDB documents into `TelemetryEvent` using mapping and converters. Key considerations:

- `@Id` maps the Java `id` property to the MongoDB `_id` field.
- When `entityClass(TelemetryEvent.class)` is configured, the gateway returns objects of this type, not a JSON string.
- When `entityClass` is omitted, the default result type is typically `org.bson.Document`.
- Do not assume a record is valid just because MongoDB mapping succeeded: fields could be missing, status wrong, timestamp null, or values out of range.
- If a collection contains multiple schemas/versions, map to a dedicated response DTO instead of exposing every entity field directly over HTTP.

A request should also be **strongly typed data**, not an arbitrary JSON query:

~~~java
package example.mongodb;

public record FindEventsRequest(String deviceId, int limit) {

    public FindEventsRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Invalid deviceId or limit (must be 1..100)");
        }
    }
}
~~~

**This is application-layer input validation.** In a multi-tenant system, add authentication and a **mandatory tenant filter derived from a trusted identity**, not just string validation on `deviceId`.

## 6. Java DSL: Static Query and Returning Replies via a Test Channel

Start with a fixed `status=NEW` query to illustrate the query/reply mechanism.

~~~mermaid
flowchart LR
    A["Request producer"] --> R["mongoListRequests: DirectChannel"]
    R --> G["MongoDbOutboundGateway"]
    G -->|"find: status=NEW"| DB["MongoDB"]
    DB -->|"List<TelemetryEvent>"| G
    G --> Q["mongoListReplies: QueueChannel"]
    Q --> T["Consumer/JUnit<br/>receive(timeout)"]
~~~

Spring Integration configuration:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoStaticQueryFlow {

    @Bean("mongoListRequests")
    public MessageChannel mongoListRequests() {
        return new DirectChannel();
    }

    @Bean("mongoListReplies")
    public QueueChannel mongoListReplies() {
        return new QueueChannel(16);
    }

    @Bean
    public IntegrationFlow mongoFindNewFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoListRequests")
                .handle(MongoDb.outboundGateway(mongoOperations)
                        .collectionName("telemetry_events")
                        .query("{ 'status': 'NEW' }")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false))
                .channel("mongoListReplies")
                .get();
    }
}
~~~

**This flow uses a static reply channel**, suitable for illustration and testing. There is no `Pollers.fixedDelay(...)`: the query executes only when a message is sent to `mongoListRequests`.

Explanation:

1. `MongoDb.outboundGateway(mongoOperations)` creates a gateway builder using the Spring Data MongoDB blocking API.
2. `collectionName("telemetry_events")` selects a specific collection.
3. `query("{ 'status': 'NEW' }")` is a static MongoDB query that **ignores the request payload**.
4. `entityClass(TelemetryEvent.class)` specifies the result type.
5. `expectSingleResult(false)` is the default mode, calling `find(...)` and returning **a list of entities**.
6. `.channel("mongoListReplies")` routes the reply to a `QueueChannel` so tests/consumers can actively pull it.
7. `QueueChannel(16)` caps at 16 **reply messages**, not the number of documents inside a reply list.

### 6.1. Sending a Request and Reading the Reply from QueueChannel

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public final class ListRequestExample {

    private final MessageChannel requests;
    private final QueueChannel replies;

    public ListRequestExample(
            @Qualifier("mongoListRequests") MessageChannel requests,
            @Qualifier("mongoListReplies") QueueChannel replies) {
        this.requests = requests;
        this.replies = replies;
    }

    public void runOnce() {
        Message<String> request = MessageBuilder
                .withPayload("LIST_NEW")
                .setHeader("correlationId", "lookup-101")
                .build();

        if (!requests.send(request)) {
            throw new IllegalStateException(
                    "MongoDB request not dispatched");
        }

        Message<?> reply = replies.receive(3000);
        if (reply == null) {
            throw new IllegalStateException(
                    "No MongoDB reply in 3 seconds");
        }

        System.out.println(reply.getPayload());
    }
}
~~~

In this example, the request payload is merely a **trigger signal**, since the static query does not use the payload. The reply is then a `List<TelemetryEvent>` (even if only one document exists).

**Do not share a single `QueueChannel` across multiple concurrent HTTP requests.** Competing requests may receive each other's results unless explicit correlation/routing is implemented. For real request/reply APIs, use a `@MessagingGateway` with a temporary reply channel as shown in section 8.

## 7. expectSingleResult: One Entity or the Entire List?

The API defines:

| Configuration | Corresponding MongoOperations | Result payload | Usage |
|---|---|---|---|
| `expectSingleResult(false)` (default) | `find(Query, Class, collection)` | `List<TelemetryEvent>` | Search/list APIs, bounded batches |
| `expectSingleResult(true)` | `findOne(Query, Class, collection)` | `TelemetryEvent` | Single-document lookup APIs |

Single-document query example:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionName("telemetry_events")
        .query("{ '_id': 'evt-101' }")
        .entityClass(TelemetryEvent.class)
        .expectSingleResult(true)
~~~

When document `evt-101` exists, the reply payload is a `TelemetryEvent`. If not found, `findOne(...)` returns `null`; **Spring `Message` does not support a null payload**, so do not assume a `Message<TelemetryEvent>` with a `null` value will be produced. Depending on endpoint wiring, the flow may emit no reply, and the caller must handle timeout/no-reply per contract.

With `expectSingleResult(false)`, `find(...)` can return an **empty list** when no documents exist; check the exact result in integration tests and decide whether the application returns `[]` or a business error. **An empty result is not a MongoDB error by default.**

### 7.1. Do Not Treat a "Single-Row" Query as a Single Document

Even if a query typically finds only one document in test data, if `expectSingleResult(false)` is set, the payload still follows the **List** contract rather than automatically unwrapping to an entity. Write handlers with the matching type to avoid `ClassCastException`.

### 7.2. Ordering When Using findOne

If a query can match multiple documents, `findOne` returns just one document. **Do not assume "first" means the oldest record.** When fetching the newest or oldest record, build a `Query` with an explicit `Sort` or use an appropriate collection/query.

## 8. Per-Request Parameterized Queries with queryFunction

This is the most important use case for the gateway: a request is represented by a DTO, and the gateway constructs a `Query` from the payload and returns a **bounded** list.

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class MongoDynamicQueryFlow {

    @Bean
    public IntegrationFlow searchTelemetryFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoSearchRequests")
                .handle(MongoDb.outboundGateway(mongoOperations)
                        .collectionName("telemetry_events")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false)
                        .queryFunction(
                            (Message<FindEventsRequest> message) -> {
                                FindEventsRequest request =
                                        message.getPayload();

                                return Query.query(
                                    Criteria.where("deviceId")
                                            .is(request.deviceId())
                                            .and("status").is("NEW"))
                                    .with(Sort.by(
                                        Sort.Order.asc("createdAt"),
                                        Sort.Order.asc("_id")))
                                    .limit(request.limit());
                            }))
                .get();
    }
}
~~~

`mongoSearchRequests` is the **input channel** name for a Messaging Gateway or producer to send requests. The flow above **intentionally omits `.channel("mongoListReplies")` at the end**. A reply-producing handler can send results back to the **caller-supplied reply channel** in the header, which fits `@MessagingGateway` below.

Points to control:

- `FindEventsRequest` validates `deviceId` and `limit ∈ [1, 100]`.
- `queryFunction` builds a `Query` via Spring Data `Criteria`, without concatenating raw input into a MongoDB query string.
- The query enforces `status=NEW` and a specific `deviceId`, sorts by `createdAt` then `_id`, and limits the number of documents.
- `.limit(...)` bounds the documents returned **in the DB**, not the number of messages on the channel.
- This is still a **blocking query**. If MongoDB is slow, the request-dispatching thread remains blocked until the DB responds or times out.

**Never let a client submit an arbitrary `Query` object** when requests originate from untrusted HTTP/Kafka sources. In multi-tenant systems, inject a **mandatory** tenant scope into `Criteria` from an authenticated context, and enforce DB authorization as well.

### 8.1. Declaring @MessagingGateway for Callers

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface TelemetryLookupApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetryEvent> findEvents(FindEventsRequest request);
}
~~~

When `findEvents(...)` is invoked, the proxy creates a request message, sets a temporary reply channel per `@MessagingGateway`'s contract, sends it to `mongoSearchRequests`, awaits the reply, and unwraps the payload into the return type.

If using Spring Integration Java DSL and gateway interfaces in a project, ensure Spring discovers/registers the interface (via component scan or `@IntegrationComponentScan` as configured). You cannot simply write an interface and expect a proxy without enabling the appropriate registration mechanism.

Caller example:

~~~java
import java.util.List;

public final class TelemetryService {

    private final TelemetryLookupApi lookup;

    public TelemetryService(TelemetryLookupApi lookup) {
        this.lookup = lookup;
    }

    public List<TelemetryEvent> find(String deviceId) {
        return lookup.findEvents(new FindEventsRequest(deviceId, 20));
    }
}
~~~

**This is the proper request/reply pattern for multiple callers.** Unlike section 6, do not let HTTP requests share a single reply `QueueChannel` and call `receive`; a temporary reply channel ensures each call receives its own response.

### 8.2. Avoid Appending a Static Reply Channel to This Flow

If a flow always routes output into `mongoListReplies` while the `@MessagingGateway` proxy waits on a temporary reply channel, **the proxy may never receive a response** and will time out. Keep the configuration consistent:

- **Pattern A:** request channel → outbound gateway → **static QueueChannel**. A dedicated consumer/test reads the queue and handles correlation.
- **Pattern B:** `@MessagingGateway` → request channel → outbound gateway → **returns via `replyChannel` header**. Do not force replies onto a static queue that lacks a return path to the caller.

When you also need to publish results to another system simultaneously, configure an appropriate router/wire tap/pub-sub rather than redirecting the reply destination arbitrarily.

## 9. Static query, queryExpression, and queryFunction

Spring Integration provides several ways to specify queries:

| Approach | Example | Characteristics |
|---|---|---|
| **`query(String)`** | `query("{ 'status': 'NEW' }")` | Static query string |
| **`queryExpression(String)`** | SpEL using payload/headers | Dynamic query from expression; requires controlling the input source |
| **`queryFunction(...)`** | Java Function returning Spring Data `Query` | Ideal for typed DTOs, validation, limits, and sorting |
| **`collectionCallback(...)`** | Callback using raw driver `MongoCollection` | Replaces standard query/find operations |

**Do not configure `query`, `queryExpression`, and `queryFunction` simultaneously** to define a single request operation; pick one clear strategy. `collectionCallback` is a separate alternative branch—do not mix it with query properties.

### 9.1. queryExpression on Payload

Conceptual example:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionName("telemetry_events")
        .entityClass(TelemetryEvent.class)
        .queryExpression("payload")
~~~

In this configuration, the `payload` expression only makes sense when **the payload is genuinely a `Query` or valid MongoDB query string**. It does not automatically turn `FindEventsRequest` into a filter. For external input, this is usually **not the safest choice** because it may widen the query scope unexpectedly.

Prefer `queryFunction(...)` to construct typed queries and enforce non-bypassable constraints such as tenant, status, and limit.

### 9.2. Dynamic Collection Selection from a Header

You can use:

~~~java
MongoDb.outboundGateway(mongoOperations)
        .collectionNameExpression("headers['trustedCollection']")
        .query("{ 'status': 'NEW' }")
        .entityClass(TelemetryEvent.class)
~~~

**This is a standalone illustrative snippet** and does not alter the flow configured in section 8. Use it only when `trustedCollection` is set by **application code after checking an allowlist**; never let an HTTP or Kafka client specify arbitrary collection names.

Allowlist example:

~~~java
String collection = switch (validatedKind) {
    case "telemetry" -> "telemetry_events";
    case "audit" -> "audit_events";
    default -> throw new IllegalArgumentException(
            "Unsupported collection category");
};
~~~

In multi-tenant systems, an allowlist alone is insufficient: verify **tenant authorization for both the collection and individual documents**.

## 10. MessageCollectionCallback: Operations Beyond find/findOne

Sometimes a request needs to count documents, run an aggregation pipeline, or perform an operation not conveniently expressed with `find`/`findOne`. Spring Integration supports `MessageCollectionCallback` with access to the MongoDB collection and request message.

Example of **counting all documents** in the lab collection:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public IntegrationFlow countTelemetryFlow(
        MongoOperations mongoOperations) {

    return IntegrationFlow.from("mongoCountRequests")
            .handle(MongoDb.outboundGateway(mongoOperations)
                    .collectionName("telemetry_events")
                    .collectionCallback(
                        (collection, requestMessage) ->
                            collection.countDocuments()))
            .get();
}
~~~

The callback uses the raw MongoDB driver API; `collection.countDocuments()` returns the document count, and the gateway produces a reply containing that count when no error occurs. In this example, the callback does not need `requestMessage`. For request-driven operations, read validated input to build a safe `Bson` filter.

**Key principles:**

- `collectionCallback(...)` **excludes** `query(...)` / `queryExpression(...)` / `queryFunction(...)` on the same spec.
- If you want paginated queries, projections, and typed mapping, use the standard query DSL.
- If a callback runs aggregations, counts, updates, or raw commands, **you are responsible** for return types, authorization, timeouts, transactions, input validation, and operation safety.
- Do not assume every `CollectionCallback` is read-only. Prevent write operations from unauthorized users.
- The result from a callback may not be a `TelemetryEvent`; downstream must expect the right payload type.

This is why the gateway **can handle custom operations**, though the query/find path is the clearest default for learning request/reply.

## 11. Direct Configuration via the MongoDbOutboundGateway Class

The Java DSL keeps code concise, but you can also declare the gateway bean directly using the Java API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mongodb.outbound.MongoDbOutboundGateway;
import org.springframework.messaging.MessageHandler;

@Bean
@ServiceActivator(inputChannel = "mongoDirectRequests")
public MessageHandler mongoDirectGateway(
        MongoOperations mongoOperations) {

    MongoDbOutboundGateway gateway =
            new MongoDbOutboundGateway(mongoOperations);

    gateway.setCollectionNameExpressionString(
            "'telemetry_events'");
    gateway.setQueryExpressionString(
            "'{''status'' : ''NEW''}'");
    gateway.setEntityClass(TelemetryEvent.class);
    gateway.setExpectSingleResult(false);
    gateway.setOutputChannelName("mongoDirectReplies");

    return gateway;
}
~~~

Here `setCollectionNameExpressionString` and `setQueryExpressionString` take **SpEL expression strings**, so the outer single quotes and escaping inside the query string are significant. To avoid confusion with two layers of quoting, Java DSL with `.collectionName(...)` and `.query(...)` is usually easier to read.

Declare `mongoDirectRequests`/`mongoDirectReplies` in the context when practicing. Do not create a second endpoint consuming `mongoDirectRequests` without an explicit routing purpose.

## 12. XML outbound-gateway Configuration

Projects using Spring Integration XML can describe request/reply as follows:

~~~xml
<!-- Inside Spring XML with int and int-mongodb namespaces declared -->
<int:channel id="mongoQueryRequests"/>

<int:channel id="mongoQueryReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoQueryGateway"
        request-channel="mongoQueryRequests"
        reply-channel="mongoQueryReplies"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query="{ 'status': 'NEW' }"
        entity-class="example.mongodb.TelemetryEvent"/>
~~~

Attributes:

| Attribute | Meaning |
|---|---|
| `request-channel` | Channel where gateway receives messages |
| `reply-channel` | Channel receiving result messages |
| `mongo-template` | Spring Data `MongoTemplate` bean |
| `mongodb-factory` | Option to use `MongoDatabaseFactory` instead of `mongo-template` |
| `mongo-converter` | Converter when configured via factory |
| `collection-name` | Static collection |
| `collection-name-expression` | SpEL determining collection per request |
| `query` | Static MongoDB query string |
| `query-expression` | SpEL producing query string or `Query` |
| `entity-class` | Result type |
| `collection-callback` | Alternative to query/find |

**Do not configure both `mongo-template` and `mongodb-factory`**, nor specify both `collection-callback` and query attributes. This XML example matches the **test flow with a static reply channel** in section 6, not a configuration for concurrent `@MessagingGateway` requests.

With the `@MessagingGateway` code in section 8, omit the static `reply-channel` or provide proper reply routing back to the caller.

## 13. Not Found, Errors, and Reply Timeouts

### 13.1. Not Found Is Not Necessarily an Exception

For lists:

~~~text
find(...): []
    |
    v
Reply payload = empty List (if handler emits list)
    |
    v
Caller returns []
~~~

For single-result:

~~~text
findOne(...): null
    |
    v
No valid entity payload
    |
    v
Flow may emit no reply
    |
    v
Caller handles no-reply / timeout
~~~

**This contract must be tested for your application's version and gateway style.** Do not write business logic assuming "no data" always yields an `Optional.empty()` from the MongoDB outbound gateway. If an HTTP API needs `404 Not Found` or a consistent `[]`, define it explicitly in a service/facade so a timeout is never mistaken for "document not found".

### 13.2. Different Types of Timeouts

| Timeout | Layer | When expired |
|---|---|---|
| `@Gateway` `replyTimeout` | Caller waiting for reply | May return no response even if query hasn't finished or produced no result |
| MongoDB `serverSelectionTimeout` | Driver selecting server | Connection error / unable to select server |
| MongoDB socket/read timeout | Driver waiting on I/O | I/O timeout error |
| Query `maxTimeMS` / appropriate deadline | Server/query | Query may be aborted for exceeding budget |
| `QueueChannel.receive(3000)` | Test/consumer waiting for a reply message | Returns `null` if queue remains empty past deadline |
| HTTP timeout | HTTP client or another gateway | May expire before the MongoDB query finishes |

**A reply timeout is not a DB query timeout.** Setting a 5-second reply timeout does not guarantee the driver cancels the MongoDB operation as soon as the caller stops waiting. Constrain timeouts at the driver/query level and bound result sizes so threads are not tied up too long.

### 13.3. Error Handling

| Error | Where it can occur | How to handle |
|---|---|---|
| MongoDB unreachable | Driver/query call | Retry with backoff, alert, explicit timeouts |
| Missing DB/collection permissions | MongoDB authorization | Fix roles/config; do not retry infinitely |
| Malformed query | Expression / query parsing | Validate early, test expressions |
| Invalid mapping | `MongoConverter`/entity class | Fix schema/DTO, quarantine when needed |
| Query too broad | Missing limit/index | Add limit/sort/projection, inspect query plan |
| Empty result | No matching documents | Return `[]` or not-found per API contract |
| Single result with no reply | `findOne` returns null | Handle no-reply/timeout, define contract |
| Reply goes to wrong channel | Flow forces fixed output | Use consistent temporary or static reply config |
| Downstream reply processing error | Transformer/HTTP/Kafka after gateway | Error channel or exception per flow |
| Query retry after error | Transient DB/network issue | Bounded read-only retry; consider consistency |

In synchronous flows using `DirectChannel`, query errors typically propagate back to the caller as a `MessagingException` or wrapped exception. With `ExecutorChannel`/asynchronous flows, errors may route to `errorChannel` if configured. **Do not assume every error goes to a single error channel.**

## 14. Query Performance, Batching, Sorting, and Projection

A search API should never call `find({})` and load an entire collection into memory. With `expectSingleResult(false)`, the gateway can produce **a single `Message<List<T>>` containing huge numbers of documents**.

| Measure | Effect |
|---|---|
| `Query.limit(n)` | Caps number of returned documents |
| `Query.with(Sort)` | Deterministic ordering |
| `query.fields().include(...)` | Projects only needed fields |
| `Query.skip(n)` / keyset cursor | Paginates per contract |
| Appropriate MongoDB indexes | Avoids unnecessary collection scans |
| Driver/server query timeouts | Prevents runaway queries |
| Mandatory tenant scope | Prevents cross-scope queries |
| Rate limiting and caching | Prevents unbounded repeated MongoDB calls |

Example of a bounded query:

~~~java
Query query = Query.query(
        Criteria.where("deviceId").is("node-7")
                .and("status").is("NEW"))
        .with(Sort.by(
            Sort.Order.asc("createdAt"),
            Sort.Order.asc("_id")))
        .limit(50);

query.fields()
        .include("_id")
        .include("deviceId")
        .include("sequence")
        .include("status")
        .include("createdAt");
~~~

**Projection into an entity:** if the `TelemetryEvent` DTO has many fields that the query omits, missing fields receive null/default values during mapping. For production APIs, create a dedicated projection DTO or avoid entities with required primitive fields when not querying full documents.

Suggested MongoDB index for the filter + sort in the example:

~~~javascript
db.telemetry_events.createIndex(
  { deviceId: 1, status: 1, createdAt: 1, _id: 1 }
)
~~~

Evaluate this index against query plans, collection size, real data, and write overhead. Never create indexes in production without an operational plan.

### 14.1. Why maxMessagesPerPoll Does Not Apply

`MongoDbOutboundGateway` handles **one request at a time**, not a polling `MessageSource`. `maxMessagesPerPoll` applies only when an **upstream poller** reads a `QueueChannel`/DB/file or triggers a message source. Putting a poller on this gateway does not limit `find()` results; you must use a **query limit**.

### 14.2. Caution with Offset Pagination

Large `skip` values can be expensive and yield unstable results if data mutates between pages. For large telemetry datasets, consider keyset pagination on `(createdAt, _id)` or appropriate cursor semantics, and define consistency/read concern.

## 15. Consistency and Request/Reply Do Not Mean a System-Wide Snapshot

The gateway queries data **at the moment the DB processes the request**. If multiple clients read and write concurrently, results may vary across queries.

- An HTTP request may receive a list while new data is inserted after the query starts.
- Consecutive reads may differ when writers update documents.
- MongoDB read concern, read preference, and transactions/sessions affect consistency/freshness; configure them at Spring Data/driver level as needed.
- Querying a collection does not create a transaction spanning Kafka/JMS/HTTP and MongoDB.
- A request/reply gateway does not provide event replay, durable queues, or caching on its own.

If the goal is strong state lookups or consistent multi-document snapshots, evaluate real MongoDB transactions and read concerns. If you need to stream all changes, a **change stream** is better suited than repeatedly polling queries.

## 16. Testing MongoDbOutboundGateway

### 16.1. Unit Testing the Request Contract

JUnit 5 example:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FindEventsRequestTest {

    @Test
    void validRequestAccepted() {
        FindEventsRequest request =
                new FindEventsRequest("node-7", 20);

        assertEquals("node-7", request.deviceId());
        assertEquals(20, request.limit());
    }

    @Test
    void rejectsInvalidLimit() {
        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("node-7", 0));

        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("node-7", 101));
    }

    @Test
    void rejectsInvalidDeviceId() {
        assertThrows(IllegalArgumentException.class,
                () -> new FindEventsRequest("", 10));
    }
}
~~~

Unit tests only verify the request contract; **they do not prove `queryFunction` ran or that MongoDB returned data**.

### 16.2. Integration Testing with a MongoDB Test Instance

You can use **Testcontainers** or a dedicated test MongoDB when the runner supports it. Create a lab database/collection, seed data with unique IDs, and use a simple flow ending in a `QueueChannel` to collect replies.

Test illustration for the **static configuration** in section 6:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoGatewayIntegrationTest {

    @Autowired
    @Qualifier("mongoListRequests")
    MessageChannel requests;

    @Autowired
    @Qualifier("mongoListReplies")
    QueueChannel replies;

    @Test
    void returnsListOfDocuments() {
        assertTrue(requests.send(
                MessageBuilder.withPayload("LIST_NEW").build()));

        Message<?> reply = replies.receive(5000);
        assertNotNull(reply, "No MongoDB reply");
        assertInstanceOf(List.class, reply.getPayload());

        List<?> result = (List<?>) reply.getPayload();
        assertFalse(result.isEmpty(), "No seeded NEW documents");
        assertInstanceOf(TelemetryEvent.class, result.get(0));
    }
}
~~~

**Test prerequisite:** a real test MongoDB instance configured and seeded with `status=NEW`. Tests should use isolated collections/cleanup; avoid letting another suite modify data and destabilize assertions. Never run destructive seed-cleanup tests against production.

### 16.3. Testing the Dynamic @MessagingGateway

With the flow from section 8, inject `TelemetryLookupApi` and assert the returned results:

~~~java
@Autowired
TelemetryLookupApi lookupApi;

@Test
void findsOnlyRequestedDevice() {
    List<TelemetryEvent> result =
            lookupApi.findEvents(
                new FindEventsRequest("node-7", 20));

    assertTrue(result.size() <= 20);
    assertTrue(result.stream().allMatch(
        e -> "node-7".equals(e.deviceId())
                && "NEW".equals(e.status())));
}
~~~

This is a method snippet inside a JUnit class that already has the Spring context, MongoDB test data, and imports; **it is not a standalone test file**. If response mapping or the proxy is not registered, the test fails before reaching assertions—which properly verifies request/reply wiring.

### 16.4. Testing Missing-Data Cases

Separate two cases:

1. With `expectSingleResult(false)`, querying a non-existent ID: verify search logic returns an empty list per the contract under test.
2. With `expectSingleResult(true)`, querying a non-existent ID: verify the response/no-reply timeout according to how the endpoint is wired. If the API needs consistent null/not-found handling, add an explicit adapter/facade.

Do not conflate a **DB connection timeout** with **not found** into the same response—those are completely different operational failures.

### 16.5. Error and Load Testing

| Case | Key assertion |
|---|---|
| MongoDB down | Receive proper exception/error response; never hang indefinitely |
| Missing read privileges | Authorization error; no blind retries |
| Unindexed query | Measure latency/explain in lab; enforce limits |
| User inputs limit 1,000,000 | DTO validation rejects early |
| User payload is raw query string | Never passed directly to DB |
| Two concurrent callers | Each caller receives its own reply; no reply-queue contention |
| Reply timeout shorter than query time | Distinguish proxy timeout from DB execution |
| Multi-document result | Assert limit and sort; do not expect multiple reply messages |
| Count callback | Payload is a `Long`/count, not `TelemetryEvent` |
| Tenant-scoped collection switching | Tenants cannot query beyond granted scope |

## 17. Observability, Errors, and Production Lifecycle

Suggested metrics (must be instrumented explicitly; do not assume the framework emits these exact names out of the box):

| Metric | Purpose |
|---|---|
| `mongo_gateway_requests_total` | Total requests entering the gateway |
| `mongo_gateway_replies_total` | Total replies actually emitted |
| `mongo_gateway_empty_results_total` | Empty list or not-found results per contract |
| `mongo_gateway_errors_total` | Query/mapping/auth errors |
| `mongo_gateway_query_duration_seconds` | DB query duration |
| `mongo_gateway_reply_latency_seconds` | End-to-end request/reply latency |
| `mongo_gateway_reply_timeout_total` | Callers timing out waiting for replies |
| `mongo_gateway_results_size` | Document count per reply |
| `mongo_gateway_inflight_requests` | Currently executing requests |
| `mongo_gateway_rejected_queries_total` | Requests rejected for invalid limit/tenant/scope |

Do not attach high-cardinality metric labels such as `_id`, `deviceId`, request ID, or unbounded URIs. Use bounded trace/correlation IDs in logs without logging full queries containing sensitive data.

### 17.1. Endpoint Lifecycle

- The Spring context creates the `MongoDbOutboundGateway` bean and registers a consumer on the input channel.
- When upstream sends a request, the handler executes the configured MongoDB query.
- The gateway **does not poll on its own**; hence `fixedDelay` is not an attribute of this endpoint.
- If MongoDB is unavailable, the app may still start, and queries will fail when processed.
- When the endpoint stops, new callers may fail or time out depending on channel/lifecycle behavior.
- On shutdown, stop accepting new requests, drain/manage in-flight requests with timeouts, and close resources safely.
- Using an `ExecutorChannel` decouples threads, but temporary reply channels/correlation must be handled cleanly if a caller has already timed out.

**Do not use an unbounded `QueueChannel` as a permanent reply sink.** For high-concurrency systems, use a gateway proxy with proper correlation or an event-driven pipeline with bounded queues, TTLs, and explicit error policies.

## 18. Securing MongoDB Queries via the Gateway

An outbound gateway can be abused because it runs queries on demand:

- **Never let external requests supply arbitrary MongoDB JSON queries**: this can expose other collections, other tenants, or full-collection dumps.
- **Construct queries via Java `Criteria`** from validated DTOs; enforce tenant/authorization filters from a trusted identity.
- **Enforce limits, sorting, projections, and query timeouts** to prevent resource exhaustion from unindexed scans.
- **Dynamic collections require an allowlist**, not just regex; verify caller authorization for the requested data scope.
- **Least privilege**: grant the MongoDB account read access only to needed collections. If using a write-capable `collectionCallback`, restrict privileges separately.
- **Never return raw entities containing sensitive fields**: map to a response DTO with only permitted fields.
- **Secrets and TLS**: manage URIs/passwords securely; enable TLS and network policies as required.
- **Rate limiting** at HTTP/gateway/queue layers before bursts hit MongoDB.
- **Do not log full queries** if they contain personal data; log request type, query template ID, and controlled correlation IDs.

Beyond application security, operational policies may require auditing, retention, and index governance. Version query contracts just like any other message contract in Spring Integration.

## 19. Comprehensive Hands-On Lab

Design an **HTTP → Spring Integration MongoDbOutboundGateway → MongoDB → HTTP response** service.

### Part A — Static Queries

1. Initialize the lab MongoDB and seed the three documents from section 4.
2. Create `TelemetryEvent` with `@Document`, `@Id`, and appropriate fields.
3. Create `mongoListRequests` as a `DirectChannel` and `mongoListReplies` as a bounded `QueueChannel`.
4. Write a Java DSL flow using `MongoDb.outboundGateway(mongoOperations)`, `query("{ 'status':'NEW' }")`, `entityClass(TelemetryEvent.class)`, and `expectSingleResult(false)`.
5. Send a request and read the reply with `receive(3000)`; verify the payload is `List<TelemetryEvent>`, not a single entity.
6. Switch to `expectSingleResult(true)` in **another experimental flow**, query by `_id`, and compare found vs. not-found behavior.

### Part B — Dynamic Queries and @MessagingGateway

1. Write `FindEventsRequest` validating `deviceId`/`limit`.
2. Use `queryFunction` to build `Criteria` filtering `deviceId`, `status=NEW`, sorted by `createdAt, _id`, with limit capped at 100.
3. Create the `TelemetryLookupApi` interface with `@MessagingGateway` and `@Gateway(requestChannel=...)`.
4. Build a service/controller calling the proxy and mapping entities to response DTOs without exposing unauthorized fields.
5. Send two concurrent requests; prove replies are never mixed up between callers.
6. Query a device with no data; define clear empty-response vs. no-reply contracts.

### Part C — Callback, XML, and Operations

1. Create **another** flow using `collectionCallback((collection, request) -> collection.countDocuments())` and assert a numeric reply.
2. Write XML configuration `int-mongodb:outbound-gateway` with request/reply channels, entity class, and static query.
3. Measure DB query latency, reply latency, inflight count, empty results, errors, and timeouts.
4. Simulate MongoDB down, bad permissions, short reply timeouts, and large result sets.
5. Add tenant scoping, collection allowlisting, and rate limiting. Prove one client cannot query another tenant's data.
6. Compare the gateway with MongoDB inbound polling and change streams, identifying when each is needed.

**Self-assessment questions:**

- Why does `MongoDbOutboundGateway` have "outbound" in its name yet still produce a reply?
- How does the gateway differ from `MongoDbStoringMessageHandler`?
- How many reply messages does `expectSingleResult(false)` return when the DB has 20 matching documents?
- Why does `findOne` finding no data not necessarily produce a `null` message payload?
- What advantages does `queryFunction` have over concatenating a JSON query string from HTTP input?
- Why can a static reply `QueueChannel` cause cross-caller response mix-ups under concurrency?
- When is `MessageCollectionCallback` needed instead of `query`?
- Why should `query` and `collectionCallback` not be placed on the same gateway?
- Does `maxMessagesPerPoll` limit the number of documents in an outbound gateway reply?
- Does a reply timeout make the MongoDB driver automatically cancel the query?
- Why must projections and tenant scoping be enforced when returning results?
- How do you test correlation, no-result cases, DB errors, and concurrency?

## 20. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): outbound gateway, Java DSL, Java/XML, collection callback, inbound, and reactive adapters.
- [Spring Integration API — MongoDbOutboundGateway](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbOutboundGateway.html): request/reply class, constructors, query/collection expressions, callbacks.
- [Spring Integration API — MongoDbOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbOutboundGatewaySpec.html): `query`, `queryExpression`, `queryFunction`, `expectSingleResult`, `collectionCallback`.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): `outboundGateway(MongoOperations)` factory and other adapters.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): `@MessagingGateway`, reply channels, timeouts, request/reply.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoOperations`, `Query`, `Criteria`, mapping, transactions, indexes.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): consistency/freshness of MongoDB queries.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): indexing and query optimization.

## Conclusion

**`MongoDbOutboundGateway` is a request/reply endpoint**: it receives query messages from an input channel, calls MongoDB through Spring Data, and emits results to a reply channel. The gateway fits per-request lookups from HTTP, JMS, AMQP, Kafka, or other integration flows, whereas the inbound channel adapter fits polling and the outbound channel adapter fits writes.

A resilient design requires **typed queries, bounded document counts, deterministic sorting, safe collection and tenant scoping, and controlled timeouts and error policies**. Understand whether the reply payload is a **List or single entity**, handle not-found and DB errors separately, and never confuse temporary reply channels with shared result queues. The gateway provides the integration structure; **reliability, consistency, and data access security** still depend on application contracts, MongoDB configuration, and operational procedures.
