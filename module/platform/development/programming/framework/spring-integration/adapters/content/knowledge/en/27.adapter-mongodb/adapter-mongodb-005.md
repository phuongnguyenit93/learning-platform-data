# Query Expressions and Collections in Spring Integration MongoDB

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between **static `query`**, **`query-expression` (SpEL)**, and **`queryFunction`** when using the MongoDB inbound adapter and outbound gateway.
- Understand precisely **when expressions are evaluated**: per poll in inbound adapters or per request message in outbound gateways.
- Distinguish between **`collection-name`**, **`collection-name-expression`**, `collectionNameFunction`, and `collectionNameSupplier`, while avoiding confusing **collection** with **database**.
- Use **`MongoOperations`/`MongoTemplate`**, `Query`, `Criteria`, `Sort`, and projections to bound data scope.
- Configure a **MongoDB inbound channel adapter** with dynamic queries/collections without assuming the poller has a `payload` or `headers`.
- Configure **`MongoDbOutboundGateway`** to accept typed requests, derive queries from `payload`, select collections via an allowlist, and return replies to the right caller.
- Use a **MongoDB outbound storing handler** to select target collections; recognize that the writer has no `query-expression` because its job is storing payloads.
- Design validation, tenant isolation, query-injection prevention, batch limits, idempotency, and error observability at the proper layer.
- Test collection routing, query limits, empty results, poll updates/retries, request/reply, and concurrency.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems to Spring Integration using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing files, SFTP, HTTP, JMS, AMQP, Kafka, and databases with emphasis on **message contracts, errors, and connection lifecycles**. In this lesson, we focus on two decisions per MongoDB operation: **what to query** and **which collection to access**.

## 1. Problem: One Application, Multiple Ways to Read and Write MongoDB

Suppose a telemetry ingestion system has two collections:

~~~text
Database: telemetry_lab

telemetry_live
  _id, deviceId, tenantId, status, temperatureC, observedAt

telemetry_archive
  _id, deviceId, tenantId, status, temperatureC, observedAt
~~~

There are three integration flows:

1. **Inbound polling:** every 5 seconds fetch up to 50 documents in `telemetry_live` with `status=NEW` and push them onto a `MessageChannel`.
2. **Outbound gateway:** when an API receives `SearchRequest(deviceId, dataset, limit)`, query `telemetry_live` or `telemetry_archive` and return the document list.
3. **Outbound channel adapter:** when a normalized message needs persistence, choose an allowed target collection and invoke MongoDB save.

~~~mermaid
flowchart LR
    DB["MongoDB: live/archive"] -->|"query + collection per poll"| I["MongoDB inbound"]
    P["Poller"] -.-> I
    I --> C1["MessageChannel: newTelemetry"]

    API["HTTP / JMS request"] --> C2["mongoSearchRequests"]
    C2 --> G["MongoDbOutboundGateway"]
    G <-->|"query + collection per request"| DB
    G --> R["Caller's reply channel"]

    B["Processed event"] --> C3["toMongo"]
    C3 --> W["MongoDB storing handler"]
    W -->|"collection expression + save"| DB
~~~

**All three endpoints access MongoDB, yet expressions are not evaluated in the same context.** Notably, inbound polling has no external request `Message` from which to read `payload.deviceId`.

## 2. Core Terminology: Query, Expression, Collection

| Term | Meaning | Example |
|---|---|---|
| **Query** | Document selection criteria and search options | `{ status: "NEW" }`; `Query.limit(50)` |
| **`query`** | A static query declared in endpoint configuration | `query("{ 'status': 'NEW' }")` |
| **`query-expression`** | SpEL string evaluated to produce a **MongoDB query string** or Spring Data `Query` | `@readPlan.currentQuery()`, `@queryFactory.forRequest(payload)` |
| **`queryFunction`** | Java Function accepting `Message<P>` and returning `Query`, for DSL outbound gateway | `message -> Query.query(...)` |
| **Collection** | A set of documents inside **one database** | `telemetry_live` |
| **`collection-name`** | Fixed collection | `collectionName("telemetry_live")` |
| **`collection-name-expression`** | SpEL returning a collection name, typically a String | `@collectionPolicy.resolve(payload.dataset)` |
| **`collectionNameFunction`** | Java Function accepting request Message and returning collection name | `message -> allowedName(...)` |
| **`collectionNameSupplier`** | Collection name supplier on MongoDB inbound source, evaluated each receive | `() -> readPlan.currentCollection()` |
| **Entity class** | Java type used to map documents | `TelemetryEvent.class` |

**Query differs from collection:** the query chooses **which documents** within a collection, while the collection specifies **which dataset** is queried/written. Changing the collection **does not change the database** connected by `MongoOperations` or `MongoDatabaseFactory`.

### 2.1. query Is MongoDB JSON, query-expression Is SpEL

These two configurations are not syntactically equivalent:

~~~java
// Static MongoDB query (DSL gateway).
.query("{ 'status': 'NEW' }")

// SpEL expression returning a Query object (DSL gateway).
.queryExpression("@queryFactory.forRequest(payload)")
~~~

The first line is **query data**, while the second is an **expression to be evaluated by the framework**. Do not assume putting `"{ 'status': 'NEW' }"` into `queryExpression(...)` behaves identically to `query(...)`; when a literal expression is needed, it must follow SpEL string literal syntax or return a `Query` from a bean.

### 2.2. queryExpression Differs from Update Expressions

On a MongoDB inbound message source, there are:

- **Query expression:** determines which documents are read.
- **Collection expression:** determines which collection is read.
- **Update expression (optional):** describes updating documents after the source fetches them.

An update preventing a document from matching the next poll's query **does not mean downstream has processed it successfully**, nor does it automatically create an exactly-once claim/transaction across concurrent workers.

## 3. Comparison of Endpoints and Expression Evaluation Contexts

| Endpoint | When is query evaluated? | When is collection evaluated? | Notable root context |
|---|---|---|---|
| **MongoDB inbound polling** | **Every `MessageSource.receive()`** | **Every `receive()`** | No input request Message; usually calls a bean/provider or supplier |
| **MongoDB outbound gateway** | **Every request message** | **Every request message** | Can read `payload`, `headers` of the request |
| **MongoDB outbound storing adapter** | No document lookup query | **Every message to store** | Has `payload`/`headers` of the message being written |
| **MongoDB change stream inbound** | Dedicated pipeline/subscription | Subscription on the target collection/database | Not equivalent to polling queries |
| **`MongoOperations` called from service** | Per Java method call | Per method and template/factory | Not an Integration endpoint expression |

**Common pitfall:** copying an outbound gateway's `payload.deviceId` expression into a polling inbound's `query-expression`. The inbound source receives no such request Message payload; the expression will fail or lack data to evaluate.

### 3.1. Dynamic Queries Do Not Mean Arbitrary Client Queries

Dynamism should serve a **bounded application contract**, for example:

- Inbound switching from reading `status=NEW` to eligible `RETRY` documents.
- Gateway looking up a specific device in live/archive collections based on a **dataset enum**.
- Writer routing a validated event type to its corresponding collection.

Do not use dynamic expressions to allow HTTP requests to read arbitrary collections, omit tenant conditions, or supply raw MongoDB JSON queries from untrusted input.

## 4. Preparing the MongoDB Lab, Dependencies, and Entity

### 4.1. Project Dependencies

With Spring Boot **3.x** and aligned version dependency management:

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

When using a different Spring Boot major version, verify starter names and compatible BOMs. This lesson uses **blocking `MongoOperations`** with the synchronous MongoDB Java driver, without mixing in `ReactiveMongoOperations`.

Example `application.yml` for the lab:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/telemetry_lab
~~~

A local URI without credentials is only for exercises. In real environments, use a secret manager/environment variables, TLS, and collection-level permissions. Never put credentials in source code or logs.

### 4.2. Test Data in mongosh

~~~javascript
use telemetry_lab

db.telemetry_live.insertMany([
  {
    _id: "live-101",
    deviceId: "node-7",
    tenantId: "tenant-a",
    status: "NEW",
    temperatureC: 26.5,
    observedAt: ISODate("2026-11-20T10:00:00Z")
  },
  {
    _id: "live-102",
    deviceId: "node-8",
    tenantId: "tenant-a",
    status: "DONE",
    temperatureC: 25.8,
    observedAt: ISODate("2026-11-20T10:01:00Z")
  }
])

db.telemetry_archive.insertOne({
  _id: "arc-201",
  deviceId: "node-7",
  tenantId: "tenant-a",
  status: "DONE",
  temperatureC: 24.9,
  observedAt: ISODate("2026-10-01T10:00:00Z")
})
~~~

Test queries:

~~~javascript
db.telemetry_live.find(
  { deviceId: "node-7", tenantId: "tenant-a", status: "NEW" }
).sort({ observedAt: -1, _id: -1 }).limit(20)

db.telemetry_archive.find({ deviceId: "node-7" })
~~~

When re-running multiple times, seeding the same `_id` triggers duplicate-key errors. Use dedicated test collections/databases; you can use `updateOne(..., { upsert: true })` for repeatable test seeding. Never delete production data.

### 4.3. Typed Entity

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_live")
public record TelemetryEvent(
        @Id String id,
        String deviceId,
        String tenantId,
        String status,
        BigDecimal temperatureC,
        Instant observedAt) {
}
~~~

`@Document(collection = "telemetry_live")` defines the default collection **when an operation does not specify another collection**. When an Integration endpoint supplies `collectionName("telemetry_archive")`, the endpoint's collection **overrides the mapping default**; therefore do not rely on the annotation to guess the actual runtime collection.

Across two collections sharing the same schema, a single `TelemetryEvent.class` can be used for reading. For differing schemas, use separate entities/DTOs or controlled transformations.

## 5. Inbound Adapter: Static Query + Static Collection

Start with a flow periodically reading the `telemetry_live` collection:

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
public class StaticMongoInboundConfig {

    @Bean("newTelemetry")
    public MessageChannel newTelemetry() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow staticMongoInbound(MongoOperations mongo) {
        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongo, "{ 'status': 'NEW' }")
                        .collectionName("telemetry_live")
                        .entityClass(TelemetryEvent.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("newTelemetry")
                .get();
    }
}
~~~

**Explanation:**

1. `MongoDb.inboundChannelAdapter(mongo, queryString)` configures the MongoDB query source.
2. `.collectionName("telemetry_live")` selects a static collection.
3. `.expectSingleResult(false)` is the default: each receive can produce a **`Message<List<TelemetryEvent>>`**.
4. `.split()` splits the list into individual `Message<TelemetryEvent>` instances.
5. `Pollers.fixedDelay(5000)` triggers polling; `maxMessagesPerPoll(1)` limits message source invocations, **not to one document**.
6. If no documents match, the message source emits nothing.
7. The `status=NEW` query **will re-read the same documents** on subsequent cycles unless a status claim/update step exists.

To give the `DirectChannel` a subscriber in the lab, add a simple handler (in a separate Java file):

~~~java
package example.mongodb;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class NewTelemetryObserver {

    @ServiceActivator(inputChannel = "newTelemetry")
    public void handle(TelemetryEvent event) {
        System.out.printf("Received event id=%s, device=%s%n",
                event.id(), event.deviceId());
    }
}
~~~

This handler merely observes; a successful log **is not** proof that the document was claimed, committed to another system, or won't be re-polled. In tests, swap the handler for a `QueueChannel` test sink to assert each message.

Because the query string here is fixed at configuration time, it **does not read headers/payloads from other messages**. To change conditions on each poll, use a source with an appropriate expression/supplier.

## 6. Inbound: query-expression Evaluated on Every Poll

In an inbound source, `queryExpression` is a Spring `Expression` evaluated **on every `receive()`**. There is no input request message from which to read `payload.deviceId` or `headers.tenantId` like in an outbound gateway.

### 6.1. A Bean Holding the Allowed Poll Policy

This provider builds a bounded query; in real applications, tenant/status values come from **managed configuration or trusted coordination state**, never a user-supplied raw JSON query.

~~~java
package example.mongodb;

import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoReadPlan")
public class MongoReadPlan {

    private final AtomicReference<String> activeStatus =
            new AtomicReference<>("NEW");

    public Query currentQuery() {
        String status = activeStatus.get();

        return Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is(status))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(50);
    }

    public String collection() {
        return "telemetry_live";
    }

    public void changeStatusByAdmin(String nextStatus) {
        if (!Set.of("NEW", "RETRY").contains(nextStatus)) {
            throw new IllegalArgumentException(
                    "Polling status not allowed");
        }
        activeStatus.set(nextStatus);
    }
}
~~~

`AtomicReference` makes reading/writing the status thread-safe in the demo. However, **this is in-memory state only**—it is not synchronized across instances, is not a durable checkpoint, and resets on app restart. To coordinate multiple workers, use a managed state/schedule source with clear permissions and semantics.

### 6.2. Java DSL with MongoDbMessageSource and SpEL

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.data.mongodb.core.MongoOperations;

@Configuration
@EnableIntegration
public class DynamicMongoInboundConfig {

    @Bean
    public MongoDbMessageSource dynamicMongoSource(
            MongoOperations mongo) {

        SpelExpressionParser parser = new SpelExpressionParser();

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongo,
                parser.parseExpression("@mongoReadPlan.currentQuery()"));

        source.setCollectionNameExpression(
                parser.parseExpression("@mongoReadPlan.collection()"));
        source.setEntityClass(TelemetryEvent.class);
        source.setExpectSingleResult(false);

        return source;
    }

    @Bean
    public IntegrationFlow dynamicMongoInbound(
            MongoDbMessageSource dynamicMongoSource) {
        return IntegrationFlow
                .from(dynamicMongoSource,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("newTelemetry")
                .get();
    }
}
~~~

**The configuration above replaces the static flow in section 5** within a lab; do not enable both pollers over the same dataset unless intentionally testing duplicate reads. The `newTelemetry` bean is declared in shared configuration or section 5's example.

- `@mongoReadPlan.currentQuery()` is SpEL invoking a Spring-context bean; it returns a **Spring Data `Query`**.
- `@mongoReadPlan.collection()` is SpEL returning the collection name **`String`**.
- The source evaluates expressions on every `receive()`, so an **authorized** status change takes effect on subsequent polls.
- A Spring-managed `BeanFactory`/`ApplicationContext` is required for SpEL to resolve `@mongoReadPlan`.
- Dynamic configuration does not mean an immediate query runs when status changes; it takes effect **when the next poll runs**.

**Important note:** a fresh Spring Data `Query` is created inside `currentQuery()` each time—never reuse a mutable `Query` and mutate it across threads. If multiple values must change together (tenant, status, limit), swap **an immutable policy object** atomically to avoid reading a new status paired with an old collection.

### 6.3. XML Equivalent

~~~xml
<!-- Inside Spring XML with int and int-mongodb namespaces -->
<int-mongodb:inbound-channel-adapter
    id="mongoDynamicInbound"
    channel="mongoLists"
    mongo-template="mongoTemplate"
    query-expression="@mongoReadPlan.currentQuery()"
    collection-name-expression="@mongoReadPlan.collection()"
    entity-class="example.mongodb.TelemetryEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

This XML illustrates **another configuration style**: the `mongoReadPlan` bean must exist, the `mongoLists` channel must be declared, and downstream must accept a `List` or pass through a splitter. Do not also specify `query` when using `query-expression`, nor specify both `collection-name` and `collection-name-expression` on the same endpoint.

### 6.4. When to Choose collectionNameSupplier

The MongoDB inbound DSL supports:

~~~java
MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionNameSupplier(
        () -> mongoReadPlan.collection())
    .entityClass(TelemetryEvent.class);
~~~

Here `mongoReadPlan` is a bean injected into the configuration class. This is an **alternative builder snippet**, not a complete `IntegrationFlow`. `collectionNameSupplier` reduces the need for SpEL if you only want a Java function selecting the collection per `receive()`; still enforce an allowlist and consistency with the query.

## 7. Outbound Gateway: Querying per Request Message

Unlike inbound polling, **`MongoDbOutboundGateway`** receives a request `Message`. SpEL and Java Functions can directly read the request's `payload` or `headers` to choose the query and collection.

### 7.1. Defining a Typed Request and Collection Catalog

~~~java
package example.mongodb;

public enum Dataset {
    LIVE,
    ARCHIVE
}

public record SearchRequest(
        String deviceId,
        Dataset dataset,
        int limit) {

    public SearchRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || dataset == null
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "Invalid MongoDB search request");
        }
    }
}
~~~

Using an enum instead of raw collection names constrains client choices. However, in multi-tenant applications, passing a valid `ARCHIVE` enum is **not enough** to permit reading the archive: verify **role/tenant authorization** before calling MongoDB.

### 7.2. Shared Query Builder and Collection Policy

~~~java
package example.mongodb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoQueryPolicy")
public class MongoQueryPolicy {

    public Query forRequest(SearchRequest request) {
        // Request constructor already validated deviceId/dataset/limit.
        // tenantId must come from an authenticated context.
        String authorizedTenant = "tenant-a"; // Lab only.

        return Query.query(
                Criteria.where("tenantId").is(authorizedTenant)
                        .and("deviceId").is(request.deviceId()))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(request.limit());
    }

    public String collectionFor(Dataset dataset) {
        return switch (dataset) {
            case LIVE -> "telemetry_live";
            case ARCHIVE -> "telemetry_archive";
        };
    }
}
~~~

**Never hard-code tenant `tenant-a` in production.** Replace it with an authenticated tenant ID, ensuring it is enforced in the server-side `Criteria`. Never trust a `tenantId` inside a caller-editable `payload` unless authorization checks validate it.

### 7.3. Java DSL with queryFunction and collectionNameFunction

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class MongoSearchFlowConfig {

    @Bean
    public IntegrationFlow mongoSearchFlow(
            MongoOperations mongo,
            MongoQueryPolicy policy) {

        return IntegrationFlow.from("mongoSearchRequests")
                .handle(MongoDb.outboundGateway(mongo)
                    .entityClass(TelemetryEvent.class)
                    .expectSingleResult(false)
                    .queryFunction(
                        (Message<SearchRequest> message) ->
                            policy.forRequest(message.getPayload()))
                    .collectionNameFunction(
                        (Message<SearchRequest> message) ->
                            policy.collectionFor(
                                message.getPayload().dataset())))
                .get();
    }
}
~~~

Key takeaways:

1. `queryFunction` receives a **request message**, not an input-less `MessageSource.receive()`.
2. `collectionNameFunction` also receives the request; the same `SearchRequest` determines both query and collection.
3. `queryFunction` returns a **Spring Data `Query`** with filter, sort, and limit—without concatenating client query strings.
4. `collectionNameFunction` selects one of **two allowlisted collections**.
5. `expectSingleResult(false)` produces a reply containing a list of `TelemetryEvent`s.
6. The flow does not force replies onto a static `QueueChannel`, allowing `@MessagingGateway` to use a **temporary reply channel** per caller.
7. This is a **blocking gateway**; configure MongoDB socket/query timeouts and connection pools for concurrent traffic.

### 7.4. Per-Caller Request/Reply Proxy

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface MongoSearchApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetryEvent> search(SearchRequest request);
}
~~~

Calling it:

~~~java
List<TelemetryEvent> found = searchApi.search(
        new SearchRequest("node-7", Dataset.LIVE, 20));
~~~

The `searchApi` call belongs inside a service injected with that interface. `@IntegrationComponentScan` in the configuration above discovers and registers the gateway proxy when scanning includes the interface package.

**Do not share a single reply `QueueChannel` and have multiple HTTP requests call `receive()` concurrently.** A message belonging to request A can be consumed by request B. Temporary reply channels managed by `@MessagingGateway` match each response to its caller.

## 8. queryExpression and collectionNameExpression with SpEL

Java Functions are usually easier to unit-test, while SpEL is useful in XML configurations or when referencing policy beans.

### 8.1. Gateway: Expressions Reading the Request Payload

Replace the two functions in the previous flow with:

~~~java
MongoDb.outboundGateway(mongo)
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false)
    .queryExpression(
        "@mongoQueryPolicy.forRequest(payload)")
    .collectionNameExpression(
        "@mongoQueryPolicy.collectionFor(payload.dataset)")
~~~

In the outbound gateway:

- `payload` is the `SearchRequest` sent by the caller.
- `@mongoQueryPolicy` is the Spring bean resolved in the expression context.
- `forRequest(payload)` must return a `Query`, while `collectionFor(...)` returns a collection name `String`.
- If a method or field name is wrong, an error surfaces **when the expression is evaluated for a request**.

**Do not declare `query(...)`, `queryExpression(...)`, and `queryFunction(...)` simultaneously** on one gateway: they are mutually exclusive alternatives. Likewise, pick only one of `collectionName(...)`, `collectionNameExpression(...)`, or `collectionNameFunction(...)`.

### 8.2. Query Expressions on Headers

If a header is set by **trusted application code** after authorization, SpEL can read it:

~~~java
.queryExpression(
    "@mongoQueryPolicy.forRequest(payload)")
.collectionNameExpression(
    "@mongoCollectionPolicy.fromApprovedHeader(headers['datasetKind'])")
~~~

`mongoCollectionPolicy` must be a declared bean, and `fromApprovedHeader` must enforce an **allowlist**. Never write directly:

~~~java
.collectionNameExpression(
    "headers['collection']")
~~~

in a flow receiving headers from untrusted users without authorization and collection constraints. That is an **unsafe pattern** when the source data is uncontrolled.

### 8.3. Static Query Example Ignoring Payload

~~~java
MongoDb.outboundGateway(mongo)
    .collectionName("telemetry_live")
    .query("{ 'status': 'NEW' }")
    .entityClass(TelemetryEvent.class)
    .expectSingleResult(false)
~~~

This query runs on each request message, yet **the filter does not depend on the request**. Do not expect sending payload `"node-7"` to change the MongoDB filter unless you configured an expression/function using that payload.

## 9. Outbound Storing Adapter: Collection Expression, No Search Query

The MongoDB outbound channel adapter typically uses `MongoDbStoringMessageHandler` to **store payloads**. It **has no `query-expression` to search documents** like an inbound source or gateway. The dynamic aspect on a writer is **selecting the collection to save the payload into**.

~~~mermaid
flowchart LR
    P["Producer Message<TelemetryEvent>"] --> V["Validate + routing policy"]
    V --> C["toMongo: MessageChannel"]
    C --> H["MongoDbStoringMessageHandler"]
    H -->|"collectionNameExpression"| DB["MongoDB live / archive"]
~~~

### 9.1. Java DSL Example with SpEL and Allowlist

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class MongoDynamicWriteConfig {

    @Bean("toMongo")
    public MessageChannel toMongo() {
        return new DirectChannel();
    }

    @Bean
    public MongoDbStoringMessageHandler mongoWriter(
            MongoOperations mongo) {

        MongoDbStoringMessageHandler writer =
                new MongoDbStoringMessageHandler(mongo);

        SpelExpressionParser parser = new SpelExpressionParser();
        writer.setCollectionNameExpression(
            parser.parseExpression(
                "@mongoCollectionPolicy.fromApprovedHeader("
                    + "headers['approvedDataset'])"));

        return writer;
    }

    @Bean
    public IntegrationFlow mongoWriteFlow(
            MongoDbStoringMessageHandler mongoWriter) {
        return IntegrationFlow.from("toMongo")
                .handle(mongoWriter)
                .get();
    }
}
~~~

Policy bean for the writer:

~~~java
package example.mongodb;

import org.springframework.stereotype.Component;

@Component("mongoCollectionPolicy")
public class MongoCollectionPolicy {

    public String fromApprovedHeader(String category) {
        if (category == null) {
            throw new IllegalArgumentException(
                    "approvedDataset is missing");
        }

        return switch (category) {
            case "LIVE" -> "telemetry_live";
            case "ARCHIVE" -> "telemetry_archive";
            default -> throw new IllegalArgumentException(
                    "Unknown or unauthorized dataset");
        };
    }
}
~~~

A **trusted** producer sends a validated message with a server-assigned header:

~~~java
Message<TelemetryEvent> message =
        MessageBuilder.withPayload(event)
            .setHeader("approvedDataset", "LIVE")
            .build();

toMongo.send(message);
~~~

This snippet assumes `event` and `toMongo` are already declared/injected, along with `Message` and `MessageBuilder` imports. The `approvedDataset` header must be **set after authorization and event-type validation**, never copied verbatim from unauthenticated HTTP/UDP/Kafka headers.

### 9.2. Writer save Is Not a Partial Update

`MongoDbStoringMessageHandler` normally uses `MongoOperations.save(payload, collectionName)`. If the payload has an `@Id`, `save` may overwrite/replace the document by ID. Do not treat this as a field patch or insert-only operation.

If you need conditional `status` updates or optimistic locking, use a service invoking `MongoOperations.updateFirst` or `findAndModify` directly. **Selecting the right collection is necessary, not sufficient for idempotency.**

### 9.3. Collection Expressions Do Not Change the MongoDB Database

If the `MongoOperations` bean connects to database `telemetry_lab`, expressions returning `telemetry_live` or `telemetry_archive` both select **collections inside `telemetry_lab`**.

To access a different database, use a **`MongoOperations`/`MongoDatabaseFactory`** connected to that database or dedicated service-layer routing. Never attempt to cram a client-supplied database name into `collectionNameExpression` to switch connections.

## 10. XML: query-expression and collection-name-expression

Spring Integration supports the XML namespace when applications do not use the Java DSL.

### 10.1. Inbound Polling: Expressions on a Policy Bean

~~~xml
<!-- Inside Spring XML with int and int-mongodb namespaces declared -->
<int-mongodb:inbound-channel-adapter
        id="mongoDynamicPoller"
        channel="mongoInboundResults"
        mongo-template="mongoTemplate"
        query-expression="@mongoReadPlan.currentQuery()"
        collection-name-expression="@mongoReadPlan.collection()"
        entity-class="example.mongodb.TelemetryEvent">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

`mongoReadPlan` is a Spring-managed bean; `mongoInboundResults` is the channel receiving `Message<List<TelemetryEvent>>` when data is found, unless a splitter is attached.

### 10.2. Outbound Gateway: Expressions on the Request

~~~xml
<int:channel id="mongoQueryRequests"/>
<int:channel id="mongoQueryReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoDynamicLookup"
        request-channel="mongoQueryRequests"
        reply-channel="mongoQueryReplies"
        mongo-template="mongoTemplate"
        query-expression="@mongoQueryPolicy.forRequest(payload)"
        collection-name-expression="@mongoQueryPolicy.collectionFor(payload.dataset)"
        entity-class="example.mongodb.TelemetryEvent"/>
~~~

**This XML example uses a static reply channel**, suitable when a single test consumer or dispatcher handles correlation. For multiple concurrent HTTP requests, use a gateway proxy with temporary reply channels rather than routing all results into one shared competing queue.

### 10.3. Outbound Storing Adapter: Collection Selection Only

~~~xml
<int:channel id="toMongoXml"/>

<int-mongodb:outbound-channel-adapter
        id="mongoStoreByCategory"
        channel="toMongoXml"
        mongo-template="mongoTemplate"
        collection-name-expression=
          "@mongoCollectionPolicy.fromApprovedHeader(headers['approvedDataset'])"/>
~~~

Depending on your XML parser/formatter, keep the entire attribute expression on one line when copying. Never add `query-expression` to an outbound writer because the endpoint is neither a poller nor a query gateway.

### 10.4. Mutually Exclusive Option Pairs

| Endpoint | Must choose one |
|---|---|
| Inbound | `query` **or** `query-expression` |
| Inbound | `collection-name` **or** `collection-name-expression` |
| Gateway | `query`, `query-expression`, **or** Java DSL `queryFunction` |
| Gateway | `collection-name`, `collection-name-expression`, **or** Java DSL `collectionNameFunction` |
| Gateway | Query attributes **or** `collection-callback` |
| Writer | `collection-name` **or** `collection-name-expression` |
| Any compatible MongoDB endpoint | `mongo-template` **or** `mongodb-factory` (plus converter if required by API) |

These pairs are **mutually exclusive alternatives**, not a fallback precedence system if both are specified. When using a custom converter bean, ensure the constructor/factory overload supports it and mapping stays consistent.

## 11. Query Performance and Data Bounds

With inbound `expectSingleResult(false)` or outbound gateway list queries, a broad query can produce **a single `Message` holding a very large `List`**.

Example `Query` with conditions and bounds:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is(authorizedTenant)
                .and("deviceId").is(request.deviceId()))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .limit(Math.min(request.limit(), 100));

query.fields()
        .include("_id")
        .include("deviceId")
        .include("tenantId")
        .include("observedAt");
~~~

**Projection note:** if you still map into `TelemetryEvent` while omitting some fields, omitted fields become `null`/defaults. Use a dedicated projection DTO or include all required fields.

| Control measure | Effect |
|---|---|
| Mandatory `tenantId` filter | Prevents reading another tenant's data |
| `Query.limit(n)` | Bounds documents returned by DB |
| Deterministic `Sort` with `_id` | Reproducible ordering and pagination |
| Projection | Reduces network bytes and avoids exposing unneeded fields |
| Index matching filter + sort | Avoids overly broad collection scans |
| Query time limit and driver timeout | Caps resources on slow queries |
| Request rate limit | Reduces MongoDB DoS risk |
| Cursor/keyset pagination | Often better than large `skip` on big datasets |
| Latency/count monitoring | Catches bad query plans or collection routing bugs |

Example index for a query filtering on tenant + device + timestamp:

~~~javascript
db.telemetry_live.createIndex({
  tenantId: 1,
  deviceId: 1,
  observedAt: -1,
  _id: -1
})
~~~

Indexes should be evaluated against **real workloads and query plans**, never added indiscriminately in production. When queries frequently filter by `status`, evaluate where `status` sits in the compound index per query patterns.

### 11.1. maxMessagesPerPoll Does Not Limit Document Count

In inbound adapters, `maxMessagesPerPoll(1)` means at most one message retrieval from the source per cycle—**it does not mean the query returns one document**. To fetch at most 50 documents, add `Query.limit(50)` or the equivalent query limit.

An outbound gateway has no poller of its own: there is no `maxMessagesPerPoll` on a gateway to bound results. The bound lives inside **`Query`**.

### 11.2. Sorting and Pagination

When requesting "latest", sort explicitly on timestamp (usually paired with ID). Never assume MongoDB `findOne` returns the newest document without a sort.

With offset pagination, large `skip` values add load and cause unstable pages when the collection mutates. Consider **keyset** pagination on `(observedAt, _id)` and keep the contract consistent across query, index, and cursor.

## 12. Duplicate Reads, updateExpression, and Business Correctness

With a MongoDB inbound query:

~~~text
Query: status=NEW
Poll #1 -> live-101
Poll #2 -> live-101
Poll #3 -> live-101
~~~

Without a state transition, **the same document can be read repeatedly**. Changing a collection expression per poll does not create a consumer checkpoint or state on its own.

A simple approach is updating documents once read by the source:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongo, "{ 'status': 'NEW' }")
    .collectionName("telemetry_live")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

This is an **alternative builder snippet** merely illustrating `update`. It does not guarantee downstream committed when status becomes `CLAIMED`.

**Risks to manage:**

- App crashes after claiming but before finishing processing → document gets stuck.
- Two instances can contend for the same document without an atomic conditional claim.
- The payload read before the update may still contain `status=NEW` even though the DB already changed.
- If the query switches between `NEW` and `RETRY` across polls, retry policies must be explicit.
- If the collection expression changes while query/update runs, ensure each operation uses a **consistent query–collection pair** by design.
- When downstream sends to HTTP/Kafka/JMS/AMQP, enforce idempotency and target-system ACKs/transactions.

For reliable workflows, consider **atomic `findAndModify` claims**, owner/lease tracking, retry/backoff, unique event IDs, and dead-letter/quarantine queues. `PseudoTransactionManager` used for transaction synchronization does not turn MongoDB operations into real transactions.

## 13. Empty Results, Expression Errors, and Reply Timeouts

| Scenario | Impact | Handling |
|---|---|---|
| Inbound query finds no documents | Source emits no `Message` | Count as normal empty poll; do not fabricate errors |
| Gateway `find(...)` returns empty list | May return empty `List` | Caller handles empty result per API contract |
| Gateway `findOne(...)` finds nothing | Null result; flow may emit no reply | Handle no-reply/not-found and timeouts |
| Expression returns wrong type | Cannot build MongoDB `Query` or collection name | Validate expressions via unit/integration tests |
| Expression accesses `payload` in inbound | No request payload exists | Switch to a provider bean/supplier for the poller |
| Collection expression returns null/empty | No valid collection name | Fail fast with explicit default validation |
| Collection does not exist | Query may return empty or writer may create collection depending on roles | Validate allowlist and config; do not infer error blindly |
| Query mismatches schema/fields | Returns empty or mapping errors | Verify field names, converter, projections |
| MongoDB unreachable | Driver errors/timeouts | Bounded retries, health/metrics |
| Reply channel forced incorrectly | Caller receives no result | Use temporary reply channel or explicit correlation |
| Query too broad | CPU, RAM, network, and pool overload | Limits, indexes, projections, rate limits |

**Do not confuse "no data" with "MongoDB error".** When `findOne` returns null, Spring Messaging has no standard null-payload message; request/reply callers may need an explicit not-found policy.

### 13.1. Layering Timeouts

- `@Gateway` `replyTimeout`: how long the caller waits for a reply.
- MongoDB server selection/socket timeout: driver wait for server or I/O.
- Query max time: execution time cap if configured.
- `QueueChannel.receive(3000)`: test consumer waiting for a Spring Message.
- Poller fixed delay: interval between inbound receives.

**Reply timeout is not query cancellation:** a caller timing out does not immediately cancel the MongoDB operation. Set timeouts at the driver/query layer and bound result sizes to avoid tying up resources unnecessarily.

## 14. Security: SpEL Is Not a User-Facing Query Language

To protect an application using dynamic expressions:

1. **Never let users submit raw SpEL expression strings** for compilation/execution; SpEL can access context beans/methods and must be treated as **trusted** configuration.
2. **Never concatenate MongoDB JSON queries from unvalidated input**, as clients could inject unwanted MongoDB operators or dump entire collections.
3. **Use typed DTOs and `Criteria`** to enforce mandatory conditions such as tenant, status, deviceId, and limit.
4. **Never let headers pick arbitrary collections**; map a validated enum/code through a concrete allowlist.
5. **Enforce tenant authorization** before allowing `LIVE`/`ARCHIVE` access; a collection allowlist alone is insufficient.
6. **Least privilege** in MongoDB: grant accounts only the read/write privileges needed by each endpoint.
7. **Bound collection cardinality**: never create a new collection per request or event ID.
8. **Do not log queries containing sensitive data**; log operation name, query template ID, logical collection name, and controlled correlation IDs.
9. **Rate limits, timeouts, indexes**, and monitoring to guard against expensive-query DoS.
10. When using multiple databases, separate `MongoOperations`/factories and verify routing; never assume a collection name switches databases.

**Unsafe** example if driven by untrusted headers:

~~~text
query-expression = "payload"
collection-name-expression = "headers['collection']"
~~~

When `payload` is an arbitrary query and header `collection` is unchecked, a client can escape data boundaries. The **proper contract** is a bounded `SearchRequest` and a server-side policy bean producing both `Query` and collection.

## 15. Unit Testing Query Policies and Collection Routing

### 15.1. Testing Query/Collection Logic Without MongoDB

Using JUnit 5:

~~~java
package example.mongodb;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.query.Query;
import static org.junit.jupiter.api.Assertions.*;

class MongoQueryPolicyTest {

    private final MongoQueryPolicy policy =
            new MongoQueryPolicy();

    @Test
    void buildsBoundedTenantQuery() {
        Query query = policy.forRequest(
            new SearchRequest("node-7", Dataset.LIVE, 20));

        assertEquals(20, query.getLimit());
        assertEquals("node-7",
            query.getQueryObject().getString("deviceId"));
        assertEquals("tenant-a",
            query.getQueryObject().getString("tenantId"));
    }

    @Test
    void routesOnlyAllowedCollections() {
        assertEquals("telemetry_live",
            policy.collectionFor(Dataset.LIVE));
        assertEquals("telemetry_archive",
            policy.collectionFor(Dataset.ARCHIVE));
    }

    @Test
    void rejectsBadRequest() {
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("", Dataset.LIVE, 20));
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("node-7", Dataset.LIVE, 5000));
        assertThrows(IllegalArgumentException.class,
            () -> new SearchRequest("node-7", null, 20));
    }
}
~~~

These tests verify the builder and allowlist, **without proving the MongoDB adapter bound the right collection** or that the DB returns the right data. Use integration tests to verify end-to-end behavior.

### 15.2. Testing SpEL Expressions in the Proper Context

Goals:

- Outbound gateway: `@mongoQueryPolicy.forRequest(payload)` must handle `Message<SearchRequest>`.
- Inbound source: `@mongoReadPlan.currentQuery()` must work when **there is no request payload**.
- Collection policy: if header `approvedDataset` is missing/invalid, the writer must fail before calling MongoDB.

When unit-testing SpEL standalone, you need a **`BeanResolver`** and an `EvaluationContext` matching Spring Integration. Using a `StandardEvaluationContext` without registering a `BeanResolver` and concluding `@beanName` is broken makes for an invalid test. More simply, test expressions through a Spring Test context with real policy beans.

## 16. Integration Testing with a MongoDB Test Instance

Use a **dedicated test MongoDB** or Testcontainers when Docker is available. Seed documents with unique IDs and clean up the right collections after tests.

~~~mermaid
flowchart LR
    T["JUnit sends SearchRequest"] --> G["MongoDbOutboundGateway"]
    G -->|"Query + collection per policy"| DB["Test MongoDB"]
    DB --> G
    G --> R["Reply Message<List<TelemetryEvent>>"]
    R --> A["JUnit asserts IDs and collection"]
~~~

### 16.1. Testing Gateway Routing Across Two Collections

In a JUnit class with a Spring Boot test context and `MongoSearchApi` proxy:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoCollectionRoutingIT {

    @Autowired
    MongoSearchApi searchApi;

    @Test
    void searchesLiveCollection() {
        List<TelemetryEvent> result = searchApi.search(
            new SearchRequest("node-7", Dataset.LIVE, 20));

        assertTrue(result.size() <= 20);
        assertTrue(result.stream().allMatch(
            e -> "node-7".equals(e.deviceId())
                && "tenant-a".equals(e.tenantId())));
    }

    @Test
    void searchesArchiveCollection() {
        List<TelemetryEvent> result = searchApi.search(
            new SearchRequest("node-7", Dataset.ARCHIVE, 20));

        assertTrue(result.size() <= 20);
        assertTrue(result.stream().allMatch(
            e -> "node-7".equals(e.deviceId())));
    }
}
~~~

**Prerequisites:** the Spring context must include `MongoSearchFlowConfig`, `MongoSearchApi`, policy beans, and a seeded test MongoDB. The test above illustrates the pattern; it does not provision Testcontainers automatically and does not prove routing if both lists return empty.

**Strengthen assertions** in your lab: seed `live-101` and `arc-201` in their respective collections and assert that the ID sets returned by the two queries **differ**, avoiding false passes when queries return empty lists or hit the wrong collection.

### 16.2. Testing State-Driven Inbound Polling

1. Seed one `NEW` document and one `DONE` document in `telemetry_live`.
2. Start the inbound source with `MongoReadPlan.currentQuery()` returning `NEW`.
3. Receive messages from the test sink after the splitter; assert only `NEW` arrives and check the `MongoHeaders.COLLECTION_NAME` header.
4. Switch the read plan state via a controlled admin API to `RETRY` and seed a `RETRY` document.
5. Wait for the next poll and assert the `RETRY` document arrives without switching collections or tenants unexpectedly.
6. Stop the endpoint before cleanup; use a test DB to avoid affecting other data.
7. Explain why duplicate reads without claim/update require idempotency design.

### 16.3. Testing Writer Collection Expressions

- Send an event with server-set header `approvedDataset=LIVE` → verify document lands in `telemetry_live`.
- Send an event with `approvedDataset=ARCHIVE` → verify `telemetry_archive`.
- Missing header or value `INTERNAL` → writer must reject per policy.
- Verify the event appears only in the allowed collection and not the other.
- Send the same event ID twice, confirming `save` can overwrite; if insert-only is required, use another handler/operation.

**Never test against a production database** and never "wipe an entire collection" if it is shared.

## 17. Common Errors and How to Isolate Them

| Symptom | Possible cause | How to check |
|---|---|---|
| Expression cannot find bean `@mongoReadPlan` | Bean not registered or wrong context | Component scan / bean name / SpEL evaluation context |
| Inbound expression reports missing `payload` | Polling source has no input Message | Use provider bean / supplier |
| Query expression returns wrong type | String is not a Mongo query or SpEL error | Test return type/value with unit tests |
| Query returns unwanted data | Missing tenant filter, status, or query limit | Inspect `Query` object, roles, and test data |
| Collection not found | Wrong collection name or wrong DB/template | Verify `MongoOperations` DB and collection |
| Selected LIVE but read ARCHIVE | Function/policy or bean context bug | Seed distinct IDs; assert per collection |
| Writer writes to wrong collection | Unnormalized header or missing policy | Validate headers and audit routing |
| No messages after inbound poll | Query matches nothing or source not started | Probe DB, poller lifecycle, headers |
| `NEW` data repeats continuously | Poller does not claim/update state | Idempotency / claim / lease / retries |
| Gateway times out despite DB query succeeding | Wrong reply channel / caller timed out | Temporary reply channel, driver/query timeouts |
| Multiple requests receive wrong replies | Shared `QueueChannel` without correlation | `@MessagingGateway` or correlation router |
| Heap grows under load | Query returns large `List` without limit | Limits/projections/paging, DB indexes |
| XML fails to start | Both `query` and `query-expression` declared | Pick one corresponding option |
| User-supplied SpEL expression exploited | Allowing raw dynamic expressions | Forbid untrusted expressions; server-side policy |
| Tenant A sees Tenant B's data | Query lacks tenant scope or DB role too broad | Test server-side authorization/criteria |

To diagnose, trace the chain:

~~~text
Message / Poller
    -> Expression evaluation
    -> Query + collection selection
    -> MongoOperations/MongoTemplate
    -> MongoDatabaseFactory/connection
    -> MongoDB execution
    -> Message payload and headers
    -> Downstream business processing
~~~

A query matching no documents does not generate an `ErrorMessage`; exceptions during polling/gateway/handler execution also follow different error paths depending on synchronous/asynchronous channels and error handling.

## 18. Lifecycle and Observability

- The inbound adapter starts polling per Spring lifecycle and poller schedule; read-plan changes apply on the next `receive()`.
- The gateway executes only on incoming requests, with no poller of its own.
- The writer runs only when a message arrives on its input channel; it never scans collections.
- If MongoDB is temporarily down, errors may appear when an operation executes rather than when `MongoTemplate` is constructed.
- On shutdown, stop producers/pollers and drain in-flight messages per contract; in-memory queues are not durable.
- When deploying multiple instances, an in-memory read plan is not synchronized across processes; prevent duplicate reads/claims across workers with DB coordination.

Suggested metrics (must be instrumented explicitly or mapped per framework):

| Metric | Meaning |
|---|---|
| `mongo_inbound_poll_total` | Number of poll runs |
| `mongo_inbound_empty_total` | Polls returning zero documents |
| `mongo_query_expression_errors_total` | Errors building/evaluating queries |
| `mongo_collection_route_errors_total` | Collection policy errors |
| `mongo_query_duration_seconds` | DB query duration |
| `mongo_query_result_documents` | Documents returned per query |
| `mongo_gateway_requests_total` | Requests entering the gateway |
| `mongo_gateway_reply_timeout_total` | Requests missing a reply before deadline |
| `mongo_writer_save_success_total` | Successful writer operations |
| `mongo_writer_save_error_total` | Write errors |
| `mongo_pending_work_depth` | Pending backlog/queue depth if present |

Do not attach metric labels per `eventId`, user-supplied collection name, or unbounded `tenantId`. Logs should record the **allowlisted collection**, query kind, status, exception type, and controlled correlation ID.

## 19. Comprehensive Hands-On Lab

Design a **MongoDB → Spring Integration → MongoDB/HTTP** application using controlled dynamic queries and collections.

### Part A — Expression Fundamentals

1. Seed data for `telemetry_live` and `telemetry_archive` in the lab MongoDB.
2. Use `query("{ 'status': 'NEW' }")` and `collectionName("telemetry_live")` on an outbound gateway; explain why the request payload does not alter the query.
3. Use `queryExpression("@mongoQueryPolicy.forRequest(payload)")` in another flow; verify the return type.
4. Explain why `queryExpression("payload")` only works when the payload is already a `Query` or valid query string.
5. Distinguish `query`/`query-expression` from `collection-name`/`collection-name-expression`.

### Part B — Inbound Polling

1. Build `MongoReadPlan` returning a `Query` with fixed/managed status and tenant, limit 50.
2. Configure `MongoDbMessageSource` with a query expression calling the bean; attach a 5-second fixed-delay poller.
3. Use a collection expression or `collectionNameSupplier` selecting `telemetry_live`.
4. After a poll, inspect the `List` payload before the splitter and `Message<TelemetryEvent>` after the splitter.
5. Transition status `NEW` → `RETRY` via a controlled admin API and observe the next poll's query.
6. Discuss re-read risks and claim/lease strategies when running multiple instances.

### Part C — Per-Request Gateway

1. Define `SearchRequest`, the `Dataset` enum, and `MongoQueryPolicy`.
2. Write a flow using `queryFunction` + `collectionNameFunction` with no static reply channel.
3. Write `MongoSearchApi` with `@MessagingGateway` and test request/reply.
4. Seed distinct IDs for `LIVE`/`ARCHIVE`; assert the correct collection and tenant.
5. Test two concurrent requests, a 20-result cap, and a missing-data query.
6. Test `queryExpression` and `collectionNameExpression` against the policy bean and compare testability.

### Part D — Writer, Errors, and Security

1. Write `MongoDbStoringMessageHandler` with an expression choosing the collection from a validated header.
2. Test `LIVE`/`ARCHIVE`/unknown values; verify writes succeed only for allowed collections.
3. Verify the writer uses `save`, not partial updates or per-request queries.
4. Simulate a down test MongoDB instance, timeouts, and overly broad queries; design retry/backoff.
5. Write tests preventing Tenant A from accessing Tenant B's data and blocking raw client SpEL/JSON query injection.
6. Propose indexes, projections, pagination, and metrics for production.

**Self-assessment questions:**

- Why cannot an inbound `query-expression` read an HTTP request's `payload`?
- How do `queryFunction` and `queryExpression` differ in API typing and testability?
- What type must `collection-name-expression` return?
- Does changing the collection switch to a different database?
- Why does `maxMessagesPerPoll(1)` not limit how many documents a query returns?
- Why is a bounded, sorted `Query` safer than an unchecked raw JSON query?
- Why is a server-side tenant filter needed even after input DTO validation?
- Why should `collectionNameFunction` use an enum/allowlist?
- What happens if `MongoDbMessageSource` reads the same `NEW` documents every 5 seconds?
- When `findOne` finds no document, why is there not always a reply with a null payload?
- When should you use `MongoDbStoringMessageHandler` vs. `MongoDbOutboundGateway`?
- How do you test routing without false positives caused by two empty lists?

## 20. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): `query-expression`, `collection-name-expression`, inbound polling, outbound gateway, and storing adapter.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): per-`receive()` query expression evaluation, List or single results.
- [Spring Integration API — MongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbMessageSourceSpec.html): Java DSL source builder.
- [Spring Integration API — AbstractMongoDbMessageSourceSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/AbstractMongoDbMessageSourceSpec.html): `collectionNameExpression`, `collectionNameSupplier`, `entityClass`, `update`.
- [Spring Integration API — MongoDbOutboundGatewaySpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDbOutboundGatewaySpec.html): `queryFunction`, `queryExpression`, `collectionNameFunction`, collection callback.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): `collectionNameExpression` and payload persistence.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoOperations`, `Query`, `Criteria`, `Sort`, mapping, indexes, and transactions.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply, temporary reply channels, timeouts.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): indexing, query performance, and data selection.

## Conclusion

**Query expressions** decide **which documents to read**, while **collection expressions** decide **which collection to read from or write to**. In MongoDB inbound adapters, expressions are evaluated when the **poller calls `receive()`**, with no request payload; in `MongoDbOutboundGateway`, expressions/functions can access **each request's** `payload` and `headers`; in the outbound storing handler, expressions choose the collection to **save the payload into**.

In **SPRING_INTEGRATION_ADAPTERS**, prefer **typed DTOs, Spring Data `Criteria`, query limits, sorting, indexes, collection allowlists, and authenticated tenant scoping**. Never pass untrusted SpEL expressions or raw JSON queries from external sources, never equate collections with databases, and never treat a single successful query or save as completion of the entire business workflow. **Proper connectivity must be paired with message contracts, idempotency, retries, security, and operational observability.**
