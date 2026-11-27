# MongoTemplate and MongoDbFactory in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Clearly explain the **MongoDB Java driver**, `MongoClient`, **`MongoDatabaseFactory`**, **`MongoTemplate`**, `MongoOperations`, and `MongoConverter`.
- Understand why legacy docs refer to **MongoDbFactory**, whereas modern Spring Data MongoDB APIs use **MongoDatabaseFactory**, and know how to update imports/configuration to match your version.
- Configure MongoDB for a Spring Boot application via auto-configuration or manual Java/XML configuration without creating duplicate clients/templates.
- Choose between `MongoOperations` and `MongoDatabaseFactory` dependencies when building a **MongoDB inbound channel adapter**, **outbound channel adapter**, and **outbound gateway**.
- Design entity mapping with `@Document`, `@Id`, `@Field`, timestamp and decimal types; know when custom converters are needed.
- Separate databases, collections, tenants, credentials, and transactions; safely use `@Qualifier` when an application connects to multiple MongoDB instances.
- Analyze connection pooling, blocking vs. reactive, driver errors, transactions, timeouts, retries, and lifecycle concerns related to integration flows.
- Write unit/integration tests verifying `MongoTemplate`, factory wiring, and the `MessageChannel`-to-MongoDB path.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module teaches connecting external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing integration with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases while paying attention to message contracts, errors, and connection lifecycles. **`MongoTemplate` and `MongoDatabaseFactory` are the connection and data-access layer used by MongoDB adapters**, rather than being message channels or pollers themselves.

## 1. Problem: What Components Does an Adapter Need to Connect to MongoDB?

Suppose an application has three requirements:

1. Periodically fetch `status=NEW` documents from the `inbox_events` collection and put them onto a `MessageChannel`.
2. Receive a normalized `Message<Reading>` from HTTP/UDP/Kafka and store it into the `readings` collection.
3. When an HTTP request asks for a device's latest data, query MongoDB and return `Message<List<Reading>>`.

All three rely on MongoDB connectivity and Java ↔ BSON mapping. Rather than having each endpoint open its own socket, Spring Data provides these layers:

~~~mermaid
flowchart TB
    A["Spring Integration inbound / outbound / gateway"] --> O["MongoOperations / MongoTemplate"]
    O --> V["MongoConverter / MappingMongoConverter"]
    O --> F["MongoDatabaseFactory"]
    V -.-> O
    F --> C["MongoClient<br/>MongoDB Java Driver"]
    C --> DB["MongoDB server / replica set"]
    P["Poller"] -.->|"Only for inbound polling"| A
    A --> M["MessageChannel"]
~~~

**Separation of responsibilities:**

- `MongoClient` manages driver-level communication with MongoDB, including connection pooling and server discovery.
- `MongoDatabaseFactory` provides access to a `MongoDatabase` by database name and integrates session info with Spring Data.
- `MongoTemplate` implements `MongoOperations`, offering high-level Java APIs such as `find`, `save`, `updateFirst`, and `remove`.
- `MongoConverter` maps Java data to/from BSON documents, supporting query mapping, entity reads/writes, and custom conversions.
- **Spring Integration adapters/gateways** accept those beans as dependencies to receive/send Spring Messages.
- **Poller** decides when to invoke an inbound message source; that is not a responsibility of `MongoTemplate`.

## 2. MongoDbFactory and MongoDatabaseFactory Across Versions

The lesson title uses **MongoDbFactory** because that term appears in older MongoDB configuration documentation.

| Name | Role | In modern code |
|---|---|---|
| `MongoDbFactory` | Factory interface in older Spring Data MongoDB versions | Check project version; do not blindly use historical imports |
| **`MongoDatabaseFactory`** | Replacement factory interface in modern Spring Data MongoDB | **Use** in this lesson's examples |
| **`SimpleMongoClientDatabaseFactory`** | Implementation backed by synchronous `MongoClient` | Use when manually configuring a database factory |
| `MongoTemplate` | Implementation of `MongoOperations` | Use for CRUD/queries and inject into Integration endpoints |
| `MongoConverter` / `MappingMongoConverter` | Java object ↔ MongoDB document | Needed when choosing a factory path with a dedicated converter |
| `ReactiveMongoDatabaseFactory` | Factory for the reactive driver | Cannot directly substitute for blocking `MongoDatabaseFactory` |

**Exact imports for current APIs**:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.convert.MongoConverter;
~~~

**Do not write** `org.springframework.data.mongodb.core.MongoDatabaseFactory` — this interface resides in the `org.springframework.data.mongodb` package. If an older example uses `MongoDbFactory` or legacy MongoDB driver classes/constructors, check the corresponding Spring Data/Spring Integration version before porting to modern code.

Note that the XML attribute **`mongodb-factory`** and bean variable name **`mongoDbFactory`** may still appear in current configurations. Those are **configuration/bean names**, not an indication that the Java interface in a new project is still `MongoDbFactory`.

## 3. Data Layers That Should Not Be Conflated

| Layer | Example | Responsibility |
|---|---|---|
| Network driver | `com.mongodb.client.MongoClient` | Connections, pooling, server selection, running MongoDB commands |
| Factory | `MongoDatabaseFactory` | Database retrieval and session coordination in Spring Data |
| Operations | `MongoOperations` | High-level contract for query/write operations |
| Template | `MongoTemplate` | Common implementation of `MongoOperations` |
| Converter | `MongoConverter` | Mapping IDs, fields, types, custom conversions |
| Integration endpoint | `MongoDbMessageSource`, `MongoDbStoringMessageHandler`, `MongoDbOutboundGateway` | Bridges Spring Messages and DB operations |
| Integration channel | `DirectChannel`, `QueueChannel`, ... | Routes messages between endpoints |

**Do not use `MongoClient.getDatabase(...)` as a default replacement for `MongoTemplate`** when you need domain mapping, `@Id`, `@Field`, or Spring Data exception translation/transactions. Raw driver access remains useful for specialized commands, but the developer must handle BSON, timeouts, sessions, and schemas manually.

## 4. Adding Dependencies and Choosing Blocking vs. Reactive

For **Spring Boot 3.x** using a BOM to manage compatible versions, a blocking MongoDB adapters application can declare:

~~~xml
<!-- Inside the dependencies section of pom.xml -->
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

- Spring Data MongoDB provides `MongoTemplate`, `MongoDatabaseFactory`, and entity mapping.
- Spring Integration MongoDB provides adapters/gateways, DSL, and message sources/handlers.
- The MongoDB **synchronous driver** must be present; the blocking MongoDB starter typically provides it transitively.
- Different Spring Boot major versions may use different starter/property names. Always use the dependency BOM compatible with your **actual project version**; never mix major versions arbitrarily.

**Reactive** is a separate branch: `ReactiveMongoOperations`, `ReactiveMongoTemplate`, `ReactiveMongoDatabaseFactory`, and the reactive streams driver. Do not pass a reactive factory to a blocking `MongoDbStoringMessageHandler` constructor expecting the compiler to convert it. Conversely, calling blocking `MongoTemplate` on an event loop can block threads and cause stalls.

## 5. Option A: Letting Spring Boot Auto-Configure MongoTemplate

With **Spring Boot 3.x**, lab configuration in `application.yml`:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_lab
~~~

When auto-configuration conditions are met, Spring Boot automatically creates `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate`, and the converter. In that case, **simply inject the existing bean**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Service
public class ReadingsQueryService {

    private final MongoOperations mongo;

    public ReadingsQueryService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public Reading findById(String id) {
        Query query = Query.query(Criteria.where("_id").is(id));
        return mongo.findOne(query, Reading.class, "readings");
    }
}
~~~

**Option A requires no extra manual `MongoTemplate` bean.** Letting Boot create a template while also declaring a manual bean of the same type/name can cause unintended auto-configuration back-off, bean ambiguity, or an endpoint writing to the wrong database. If you already have a Boot-managed `MongoOperations`, reuse it across `IntegrationFlow`s targeting the same database.

### 5.1. Keeping Credentials Out of Source Code

In the lab, the URI has no password. Production should use environment variables or a secret manager supplied by the deployment platform, such as overriding `spring.data.mongodb.uri` via environment configuration. Never commit usernames/passwords, access tokens, or certificate private keys into repositories or logs.

When running inside Docker, `127.0.0.1` points to the **current container**, not automatically to MongoDB on the host or another container. Use the configured network hostname/port and verify DNS, firewall, and TLS.

## 6. Option B: Manually Configuring MongoClient → Factory → Template

If the application does not use Spring Boot auto-configuration, uses multiple databases, or needs specialized control, you can declare the beans manually.

~~~java
package example.mongodb;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration
public class ManualMongoConfiguration {

    @Bean(destroyMethod = "close")
    public MongoClient mongoClient(
            @Value("${app.mongo.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean
    public MongoDatabaseFactory mongoDatabaseFactory(
            MongoClient mongoClient) {
        return new SimpleMongoClientDatabaseFactory(
                mongoClient, "adapter_lab");
    }

    @Bean
    public MongoTemplate mongoTemplate(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTemplate(mongoDatabaseFactory);
    }
}
~~~

Property configuration for this example:

~~~yaml
app:
  mongo:
    uri: mongodb://127.0.0.1:27017
~~~

**Option B is an alternative to Option A**; do not register both in the same Spring context. If multiple clients/templates exist, use explicit bean names and `@Qualifier` as shown in section 12.

Lifecycle explanation:

1. `MongoClients.create(uri)` creates a synchronous `MongoClient`.
2. `SimpleMongoClientDatabaseFactory(client, "adapter_lab")` selects the database and exposes the factory API.
3. `new MongoTemplate(factory)` creates the CRUD/query template; by default, Spring Data creates/configures an appropriate converter.
4. `@Bean(destroyMethod="close")` binds closing **`MongoClient`** to the Spring context lifecycle.
5. `MongoTemplate` and the factory are reused across messages; **never create a new `MongoClient` per handler invocation**.
6. If MongoDB is temporarily down, instantiating client/template objects may not fail immediately; the actual error may surface on the first I/O call.

If multiple databases live on **the same MongoDB deployment**, separate factories can share a single `MongoClient` pool while selecting different database names. If databases live on **different clusters**, separate `MongoClient`s with distinct URIs, pools, and credentials are required.

### 6.1. When to Pass a Factory + MongoConverter to MongoTemplate?

Spring Data provides a constructor taking a factory and converter:

~~~java
MongoTemplate template =
        new MongoTemplate(mongoDatabaseFactory, mongoConverter);
~~~

`mongoConverter` must be **properly configured/initialized** for Spring Data, such as a `MappingMongoConverter` with an appropriate mapping context and custom conversions. Do not construct a minimal throwaway converter just to satisfy the constructor; doing so can alter `@Id`, `@Field`, enum, timestamp, or custom type behavior between inbound and outbound flows.

A useful rule of thumb: if the application has no special mapping requirements, **prefer the Boot-configured template**. If a custom converter is needed, configure and test it at the Spring Data layer before wiring it into Spring Integration.

## 7. What Are MongoTemplate/MongoOperations Used For?

`MongoOperations` is the interface describing document operations in Spring Data's model. `MongoTemplate` is its primary implementation.

| API | Meaning | When used in Integration |
|---|---|---|
| `find(Query, T.class, collection)` | Fetches a list of documents mapped as entities | MongoDB inbound polling / outbound gateway |
| `findOne(Query, T.class, collection)` | Finds one entity or null | Single-document lookup gateway |
| `findById(id, T.class, collection)` | Looks up by ID | Lookup service |
| `save(object, collection)` | Inserts new or writes by ID, potentially replacing document | MongoDB outbound storing handler |
| `insert(object, collection)` | Inserts new without replacing by ID | Custom handler requiring insert-only |
| `updateFirst(Query, Update, ...)` | Conditionally modifies fields | Status marking, claiming, patching |
| `upsert(Query, Update, ...)` | Updates if matched, inserts otherwise | Key-based state sync |
| `remove(Query, ...)` | Deletes documents matching query | Test cleanup or authorized business workflows |
| `findAndModify(...)` | Conditional query + update in one atomic operation | Job/lease claiming |
| `execute(...)` | Raw collection API access when needed | Operations not cleanly expressed via template |

Example querying and writing a document:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class ReadingRepositoryLikeService {

    private final MongoOperations mongo;

    public ReadingRepositoryLikeService(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<Reading> recentNewReadings(String deviceId) {
        Query query = Query.query(
                Criteria.where("deviceId").is(deviceId)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(50);

        return mongo.find(query, Reading.class, "readings");
    }

    public void store(Reading reading) {
        mongo.save(reading, "readings");
    }

    public long markDone(String eventId) {
        Query query = Query.query(
                Criteria.where("_id").is(eventId)
                        .and("status").is("PROCESSING"));
        Update update = new Update().set("status", "DONE");

        return mongo.updateFirst(
                query, update, "readings")
                .getModifiedCount();
    }
}
~~~

`markDone` uses a **partial update** rather than calling `save` to change one field when concurrent modifications might be overwritten. A result of `getModifiedCount()==0` may mean the document did not match the query, the status was already `DONE`, or another writer modified it—verify according to your contract.

**Distinguish read/write APIs from message integration:** calling `MongoOperations.find(...)` does not emit a Spring `Message`. Only when you wire it into a `MessageSource`/`MessageHandler`/gateway or send the result onto a channel does it become an `IntegrationFlow` step.

## 8. MongoConverter and Entity Mapping

To give MongoDB documents clear types, use Spring Data mapping annotations:

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "readings")
public record Reading(
        @Id String id,
        @Field("device_id") String deviceId,
        long sequence,
        @Field(targetType = FieldType.DECIMAL128)
        BigDecimal temperatureC,
        String status,
        Instant observedAt) {
}
~~~

The corresponding document might look like:

~~~json
{
  "_id": "evt-101",
  "device_id": "node-7",
  "sequence": 101,
  "temperatureC": { "$numberDecimal": "26.5" },
  "status": "NEW",
  "observedAt": { "$date": "2026-11-23T02:00:00Z" }
}
~~~

**The JSON snippet is illustrative Extended JSON**, not necessarily how the MongoDB driver prints every document. In Spring Data code, `@Field("device_id")` affects the field name written to BSON; queries using `Query` based on domain property names can be translated by the converter/query mapper. Test with real data when combining raw queries, raw aggregations, or direct driver callbacks.

### 8.1. Role of the Converter

- `@Id` maps the Java entity's ID to the document's `_id`.
- `@Field` renames the Java/BSON field or specifies the BSON type.
- `MongoConverter` maps Java objects ↔ MongoDB documents; `MappingMongoConverter` is the standard implementation.
- The converter handles type metadata, custom conversions, and complex data types.
- `BigDecimal` needs an explicit storage representation, such as Decimal128 for decimal precision; do not assume every configuration stores it identically to the example.
- `Instant` and time zones require a clear contract; MongoDB dates represent UTC instants, while display formatting depends on the client.

When you supply a `MongoTemplate` with a custom converter, **every adapter using that template** shares that mapping behavior. If you switch to the factory + converter path on an Integration endpoint, ensure the converter matches and remains consistent with the rest of the flow.

### 8.2. Custom Conversions

If you need to store a specialized value object, Spring Data supports `MongoCustomConversions` with read/write converters. Converters must be registered on `MappingMongoConverter` and tested round-trip.

**Never call `toString()` and store an entire DTO as a JSON String** when you intend to query by `deviceId`, `status`, timestamps, or indexes. Data not matching proper BSON schemas is hard to query, hard to index, and prone to conversion bugs later.

## 9. Choosing Template or Factory for the MongoDB Inbound Adapter

With Spring Integration Java DSL, the direct approach uses **`MongoOperations`**:

~~~java
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
public class ReadingInboundConfig {

    @Bean("mongoReadings")
    public MessageChannel mongoReadings() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow pollNewReadings(MongoOperations mongo) {
        return IntegrationFlow
                .from(
                    MongoDb.inboundChannelAdapter(
                            mongo, "{ 'status': 'NEW' }")
                        .collectionName("readings")
                        .entityClass(Reading.class)
                        .expectSingleResult(false),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(1)))
                .split()
                .channel("mongoReadings")
                .get();
    }
}
~~~

**This flow only illustrates reading.** It does not mark `status=DONE`; therefore the same `NEW` documents can be re-emitted in subsequent cycles. In real deployments, add conditional update/claim, retries, idempotency, and backlog management.

An **alternative** approach using the factory directly:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(Criteria.where("status").is("NEW"))
        .limit(50);

MongoDb.inboundChannelAdapter(mongoDatabaseFactory, query)
        .collectionName("readings")
        .entityClass(Reading.class)
        .expectSingleResult(false);
~~~

This factory snippet configures a spec to pass to `IntegrationFlow.from(sourceSpec, pollerConfig)`, **not a second flow to run concurrently**. Running both flows against the same collection increases the risk of duplicate reads.

### 9.1. One Poll Does Not Mean One Document

By default, one `MongoDbMessageSource.receive()` call with `expectSingleResult(false)` can return a `Message<List<Reading>>`. `maxMessagesPerPoll(1)` limits how many times the source is invoked per cycle, **not how many documents** a query returns. Use `Query.limit(...)`, sorting, indexes, and a splitter to regulate load.

## 10. Configuring the MongoDB Outbound Storing Handler

When upstream sends `Message<Reading>` to a channel, the blocking writer can use the configured template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.outbound.MongoDbStoringMessageHandler;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public MongoDbStoringMessageHandler readingWriter(MongoOperations mongo) {
    MongoDbStoringMessageHandler handler =
            new MongoDbStoringMessageHandler(mongo);
    handler.setCollectionNameExpression(
            new LiteralExpression("readings"));
    return handler;
}

@Bean
public IntegrationFlow writeReadings(
        MongoDbStoringMessageHandler readingWriter) {
    return IntegrationFlow.from("toMongoReadings")
            .handle(readingWriter)
            .get();
}
~~~

This is a fragment of a `@Configuration` class where the input channel `toMongoReadings` is declared. `MongoDbStoringMessageHandler` saves the **payload**, not all Spring Message headers automatically. It typically uses `MongoOperations.save(...)`, meaning it can **replace a document by ID** rather than performing a partial update.

Alternative approach using the factory:

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;

MongoDbStoringMessageHandler writer =
        new MongoDbStoringMessageHandler(mongoDatabaseFactory);
writer.setMongoConverter(mongoConverter);
writer.setCollectionNameExpression(
        new LiteralExpression("readings"));
~~~

**This is an alternative**, so do not create two writers competing on the same `DirectChannel`. `setMongoConverter(...)` is only intended for handler instances constructed with **`MongoDatabaseFactory`**, per the API contract. If the handler already received a full `MongoOperations`, the converter lives inside the template; do not call the setter assuming you can swap the template's converter.

## 11. Configuring the MongoDB Outbound Gateway (Request/Reply)

If a flow needs to read MongoDB **per request** and return results:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;

@Bean
public IntegrationFlow searchNewReadings(MongoOperations mongo) {
    return IntegrationFlow.from("readingQueryRequests")
            .handle(MongoDb.outboundGateway(mongo)
                    .collectionName("readings")
                    .query("{ 'status': 'NEW' }")
                    .entityClass(Reading.class)
                    .expectSingleResult(false))
            .get();
}
~~~

When the caller provides a valid `replyChannel` (such as via a `@MessagingGateway` proxy), the outbound gateway emits a response, typically containing a `List<Reading>` when `expectSingleResult(false)`. The gateway **needs no poller** and differs from the one-way outbound storing handler.

The Java DSL also supports factory + converter:

~~~java
MongoDb.outboundGateway(
        mongoDatabaseFactory, mongoConverter)
    .collectionName("readings")
    .query("{ 'status': 'NEW' }")
    .entityClass(Reading.class)
    .expectSingleResult(false);
~~~

**Important:** for the gateway, the factory path requires **`MongoConverter`** when using this factory overload. Do not assume every MongoDB endpoint needs only a factory and shares an identical implicit converter.

### 11.1. Configuring a Callback or Query

The gateway can use `query(...)` / `queryFunction(...)` or `collectionCallback(...)` to run a collection operation. These paths have distinct APIs/semantics; **do not mix collection callbacks with query options** on the same gateway.

When queries depend on HTTP/Kafka input, prefer typed DTOs, `Criteria`, and limits; never allow users to supply arbitrary MongoDB JSON queries or unvalidated collection names.

## 12. Using Multiple MongoDBs/Databases Safely

Suppose an application uses two databases on **the same cluster**: `business_db` and `audit_db`. Two factories can share one `MongoClient`:

~~~java
import com.mongodb.client.MongoClient;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration
public class MultiDatabaseMongoConfig {

    @Bean("businessFactory")
    public MongoDatabaseFactory businessFactory(MongoClient client) {
        return new SimpleMongoClientDatabaseFactory(
                client, "business_db");
    }

    @Bean("auditFactory")
    public MongoDatabaseFactory auditFactory(MongoClient client) {
        return new SimpleMongoClientDatabaseFactory(
                client, "audit_db");
    }

    @Bean("businessMongo")
    public MongoOperations businessMongo(
            @Qualifier("businessFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }

    @Bean("auditMongo")
    public MongoOperations auditMongo(
            @Qualifier("auditFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }
}
~~~

This is a **dedicated configuration option**: it assumes the application already has exactly one `MongoClient` bean and should not be run alongside the manual template configuration in section 6 without coordination. When injecting into an endpoint, select the exact template:

~~~java
@Bean
public MongoDbStoringMessageHandler auditWriter(
        @Qualifier("auditMongo") MongoOperations mongo) {
    MongoDbStoringMessageHandler handler =
            new MongoDbStoringMessageHandler(mongo);
    handler.setCollectionNameExpression(
            new LiteralExpression("audit_events"));
    return handler;
}
~~~

**Sharing one `MongoClient` means sharing connections/credentials per client**, while using different database names. Separating databases **does not automatically isolate access permissions**: configure appropriate MongoDB roles, tenant policies, and auditing.

### 12.1. Do Not Confuse Database with Collection

- **Database** is chosen by the factory/template, e.g., `business_db`.
- **Collection** is chosen by `MongoOperations` or the Integration endpoint, e.g., `readings`.
- Changing `collectionNameExpression` from `readings` to `audit_events` **does not switch to the `audit_db` database**.
- To switch target databases safely, use the corresponding bean/template and explicit routing/authorization; never let an untrusted header pick arbitrary database names.

### 12.2. Two Separate Clusters

If `audit_db` resides on a different cluster, use a separate `MongoClient` with its own URI/credentials/pool. Name beans clearly like `auditClient`/`auditFactory`/`auditMongo` and inject with `@Qualifier`. When multiple candidates exist, autowiring solely by `MongoOperations` type is usually ambiguous; never rely on accidental bean selection.

In multi-tenant designs, do not grant a client read/write access across all tenants unless required. A factory does not replace authorization.

## 13. XML Configuration: mongo-template and mongodb-factory

The Spring Integration MongoDB XML namespace uses attributes such as:

| Attribute | Meaning |
|---|---|
| `mongo-template` | Ref to configured `MongoTemplate` / `MongoOperations` |
| `mongodb-factory` | Ref to a bean implementing `MongoDatabaseFactory` |
| `mongo-converter` | Ref to `MongoConverter` when using the factory path |
| `collection-name` | Fixed collection name |
| `collection-name-expression` | Expression to select collection per message |
| `query / query-expression` | Read filter on inbound/gateway, not a standard writer attribute |

Two **alternative** configurations for a MongoDB outbound writer:

~~~xml
<!-- Example A: using pre-created template -->
<int-mongodb:outbound-channel-adapter
    id="mongoWriterWithTemplate"
    channel="toMongo"
    mongo-template="mongoTemplate"
    collection-name="readings"/>
~~~

~~~xml
<!-- Example B: using factory + converter -->
<int-mongodb:outbound-channel-adapter
    id="mongoWriterWithFactory"
    channel="toMongo"
    mongodb-factory="mongoDbFactory"
    mongo-converter="mongoConverter"
    collection-name="readings"/>
~~~

**Do not register both endpoints on the same input `DirectChannel`** if the intent is to write each message once. Two subscribers on a `DirectChannel` do not both receive a copy of every message; in some cases they compete for messages.

**Never specify both `mongo-template` and `mongodb-factory` on the same adapter/gateway** per the XML contract. If a custom converter is needed, verify that both template and factory paths use compatible conversion settings.

If you declare the factory bean in Spring XML, the current implementation class is `org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory`, and the Java interface is `org.springframework.data.mongodb.MongoDatabaseFactory`. The XML bean ID `mongoDbFactory` is just a name, not a legacy Java import.

## 14. Connection Pooling, Threading, and Performance

`MongoTemplate` is normally registered as a **reusable singleton bean**. Sending a message through a MongoDB adapter must never instantiate a new `MongoClient`.

| Scenario | Risk | Mitigation |
|---|---|---|
| Creating client per message handler | Pool/socket explosion, slowness, resource leaks | Use a singleton `MongoClient` bean |
| Inbound polling too fast | Continuous DB queries and duplicate reads | Tune poller, query limits/indexes, processing state |
| Writer on `DirectChannel` | MongoDB I/O blocks caller thread | Set timeouts or controlled async branches |
| Writer on `ExecutorChannel` | Overloaded queues/workers | Bounded capacity, retry policy, error channel |
| Gateway returns huge `List` | Memory, latency, and thread pressure | `Query.limit`, projection, pagination |
| Client pool exhausted | Requests queue waiting for connections | Monitor pool, tune throughput and pool settings |
| Database down | Server selection/write timeout | Circuit breaker, backoff, health/readiness |
| Multiple templates with multiple clients | Total pool count multiplies | Separate clients only for distinct clusters/credentials |

**Do not mix blocking and reactive arbitrarily:** if using a reactive flow to handle high concurrency without blocking threads, choose `ReactiveMongoOperations` and true reactive MongoDB adapters. Calling blocking `MongoTemplate` on a Reactor event loop defeats non-blocking benefits.

### 14.1. What Does a Successful Send Mean?

- `MessageChannel.send(...)` returning true indicates the message was accepted/dispatched per channel semantics.
- With `DirectChannel`, the blocking DB handler runs on the same thread before `send` returns; MongoDB errors usually appear as exceptions.
- With a queue/executor, `send` succeeding **does not prove** data has been written yet.
- With MongoDB write concern, the ACK defines how thoroughly the server confirmed the write; it **does not guarantee** the upstream Kafka/JMS/SFTP/HTTP event has completed its transaction in the other system.

Separate metrics for **message accepted**, **query/write attempted**, **DB acknowledged**, and **business completed**.

## 15. Errors, Retries, and Transactions

### 15.1. Error Classification

| Error | Where it occurs | Appropriate action |
|---|---|---|
| DNS/TLS/auth failure | `MongoClient` server selection/connection | Fix configuration, roles, TLS; alert |
| Server selection timeout | Driver cannot pick a MongoDB server | Bounded retry/backoff, inspect topology |
| Pool exhausted | Long wait for a connection | Tune pool size, throttle workload |
| Mapping error | Converter/reading document | Validate schema, fix converter, quarantine |
| Duplicate key | Insert or unique index violation | Check idempotency key; do not retry forever |
| Write concern timeout | DB has not confirmed at required level | Outcome may be unknown; retry with same ID and reconcile |
| Optimistic locking | `@Version` conflict | Re-read/reconcile; do not blindly overwrite |
| Query too broad | Scanning too many documents | Indexes, limits, projections, authorization |
| Transaction aborted | MongoDB transaction failure | Retry transaction per contract; avoid duplicate side effects |
| Downstream failure after DB save | External system fails to complete | Outbox/reconciliation/idempotency |

Spring Data typically translates driver errors into `DataAccessException` subclasses; exceptions may be wrapped into `MessagingException` by Spring Integration depending on the flow. **Do not claim all errors automatically route to `errorChannel`**; with synchronous `DirectChannel`, errors may throw directly to the caller, whereas executors/pollers require explicit error handling.

### 15.2. Transaction Manager

If the MongoDB deployment supports transactions, declare `MongoTransactionManager` for **the exact factory**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Bean
public MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory) {
    return new MongoTransactionManager(mongoDatabaseFactory);
}
~~~

**MongoDB multi-document transactions** require a supported MongoDB topology, typically a replica set or supported sharded cluster. The code above is a **configuration fragment**; it does not make an arbitrary standalone MongoDB support transactions.

If you have two `MongoDatabaseFactory`/transaction managers, inject the exact manager matching the database used by the operation; one transaction cannot span two independent clusters or span Kafka and MongoDB.

### 15.3. Do Not Confuse PseudoTransactionManager

Spring Integration has **transaction synchronization** for pollers, and examples sometimes use `PseudoTransactionManager` to trigger before/after callbacks. A pseudo manager **does not turn MongoDB operations into real transactions**; use a real transaction manager/session to guarantee MongoDB atomicity.

To avoid losing events across multiple systems, rely on **durable outbox/inbox patterns, ACK after commit, idempotency, and retries** rather than inferring exactly-once from having a `MongoTemplate`.

## 16. Testing Factories, Templates, and Integration Flows

### 16.1. Unit Testing Mapping and Business Rules

Unit tests verify DTOs/validators without requiring MongoDB:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReadingValidationTest {

    @Test
    void hasStableIdentityAndValues() {
        Reading event = new Reading(
                "evt-101", "node-7", 101,
                new BigDecimal("26.5"),
                "NEW", Instant.parse("2026-11-23T02:00:00Z"));

        assertEquals("evt-101", event.id());
        assertEquals("node-7", event.deviceId());
        assertEquals(101L, event.sequence());
    }

    @Test
    void decimalIsNotAFloatApproximation() {
        BigDecimal decimal = new BigDecimal("26.5");
        assertEquals(0,
                decimal.compareTo(new BigDecimal("26.50")));
    }
}
~~~

This unit test **does not prove `MongoConverter` actually writes Decimal128**, nor does it verify URIs, database names, or Spring Integration connectors.

### 16.2. Integration Testing MongoTemplate Against a Test Database

Use a test MongoDB instance or Testcontainers when the runner provides Docker. Goal: `save` then `findById`, verifying mapped values:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoTemplateIntegrationTest {

    @Autowired
    MongoOperations mongo;

    @Test
    void roundTripsMappedReading() {
        String id = "it-" + UUID.randomUUID();
        Reading original = new Reading(
                id, "node-test", 7,
                new BigDecimal("26.5"),
                "NEW", Instant.parse("2026-11-23T02:00:00Z"));

        try {
            mongo.save(original, "readings");

            Reading stored = mongo.findById(
                    id, Reading.class, "readings");

            assertNotNull(stored);
            assertEquals("node-test", stored.deviceId());
            assertEquals(7L, stored.sequence());
            assertEquals(0, stored.temperatureC()
                    .compareTo(new BigDecimal("26.5")));
        } finally {
            mongo.remove(
                Query.query(Criteria.where("_id").is(id)),
                "readings");
        }
    }
}
~~~

**Run only against an explicitly configured test MongoDB**; never point to a production database because the test inserts and deletes records. If the application has multiple `MongoOperations` beans, use `@Qualifier` and verify the selected database.

### 16.3. Testing an IntegrationFlow Using MongoTemplate

You can attach a `QueueChannel` as an output sink after the inbound adapter:

~~~text
MongoDB test collection
      |
      v
MongoDb.inboundChannelAdapter(...)
      |
      v
Splitter
      |
      v
QueueChannel test sink
      |
      v
JUnit receive(timeout) and assert
~~~

Or test the outbound writer by sending `Message<Reading>` to `toMongoReadings` and reading the document back via `MongoOperations`. For a gateway, send a request and inspect the reply payload on a queue or via the `@MessagingGateway` proxy.

**Important tests to include:**

1. Factory selects the right database; template uses the right converter.
2. `@Id`, `@Field("device_id")`, and Decimal128 map accurately.
3. Inbound `expectSingleResult(false)` produces a `List`, and splitter splits into the expected type.
4. Empty query creates no message in inbound polling; list gateway follows its response contract.
5. Writer with the same ID: verify save/overwrite semantics rather than assuming insert-only.
6. Two `MongoOperations` beans: `@Qualifier` routes messages to the right database without cross-writes.
7. MongoDB down: timeouts, `errorChannel`, and retries behave as designed.
8. Empty collection: poller does not repeat stale messages or generate null payloads.
9. Shutdown/restart: connection pool is managed and backlog/claims recover per business rules.
10. Multi-document transactions: test only when the MongoDB topology genuinely supports them.

### 16.4. Catching Wrong-Database Bugs with Assertions

When using multiple databases, a test should write a unique ID into `business_db.readings` and assert it is **absent** from `audit_db.readings`. Beyond asserting document counts, verify the selected database/collection, credentials, and mapped fields. Identical collection names across two DBs are completely valid, so logs showing only `collectionName` are insufficient to diagnose routing errors.

## 17. Security, Configuration, and Observability

- **Secrets/TLS:** load URIs/credentials from a secret manager or environment variables; enable TLS and enforce certificate trust as required.
- **Least privilege:** an inbound reader account does not necessarily need write permissions; an outbound writer account should only write to authorized collections.
- **Tenant isolation:** a `collection-name-expression` does not change databases; use dedicated templates per tenant/DB and verify permissions from a trusted identity.
- **No raw query injection:** never let HTTP/Kafka clients control queries/collections freely; use `Criteria`, limits, and allowlists.
- **Payload contract:** validate schemas, IDs, required fields, and numeric/time types before `MongoOperations`.
- **Never log secrets or sensitive documents:** log error classes, endpoint IDs, logical database IDs, allowlisted collections, and necessary event IDs.
- **Indexes and retention:** maintain query/unique indexes matching the workload; never build large indexes ad hoc.
- **Pool limits:** reuse clients and monitor connection pool utilization and server selection latency.
- **Error and retry budgets:** distinguish permanent auth failures from transient network errors; never retry infinitely and cause cascading load.
- **Sessions/transactions:** never manually share sessions across threads if the API/driver forbids it; rely on Spring transaction scopes.
- **Metrics:** separate `mongo_connect_errors_total`, `mongo_query_latency_seconds`, `mongo_save_attempt_total`, `mongo_save_success_total`, `mongo_poll_empty_total`, `mongo_integration_errors_total`, `mongo_pending_work_depth`.

These are **illustrative metric names**; do not assume every Spring Integration version emits these exact names automatically. Avoid unbounded high-cardinality labels such as `deviceId`, `_id`, IP/port, or MongoDB URIs containing credentials.

## 18. Common Errors and How to Isolate Them

| Symptom | Common cause | Check |
|---|---|---|
| No `MongoTemplate` bean | Missing starter / auto-config excluded or misconfigured | Dependencies, bean graph, profiles |
| Multiple `MongoOperations` beans | Multi-database setup injected without qualifier | Bean names, `@Qualifier`, intentional `@Primary` |
| Compile error on `MongoDbFactory` | Using legacy API import | Switch to version-appropriate `MongoDatabaseFactory` |
| Compile error on factory package | Mistakenly using `org.springframework.data.mongodb.core` | Import `org.springframework.data.mongodb.MongoDatabaseFactory` |
| XML reports factory/template conflict | Both `mongo-template` and `mongodb-factory` specified | Choose a single configuration path |
| Incorrect field mapping | Missing custom converter config or raw driver usage | Check `@Id`/`@Field`, converter, DB documents |
| Writer writes to wrong DB | Wrong template/factory injected | `@Qualifier`, factory DB name, target URI |
| Query returns empty despite DB data | Wrong database/collection, field mapping, or filter | Direct `find` in test DB, logs |
| Adapter polls duplicates continuously | Document not marked as processed | Claim/lease, status, and idempotency |
| App starts even when MongoDB is down | Client connects lazily / on first I/O | Readiness probes, server selection timeout |
| Duplicate writes on retry | Unstable ID or fresh insert every time | Stable event ID, unique index |
| Throughput bottleneck | Small pool, broad query, `DirectChannel` blocking | Pool metrics, query plan, channel timing |
| Transaction fails to start | Standalone MongoDB / unsupported topology | Replica set, transaction manager, session |
| Reactive flow blocked | Blocking `MongoTemplate` called on event loop | `ReactiveMongoOperations` or proper executor |

**Isolate along the chain:** request → `MessageChannel` → Integration endpoint → `MongoOperations`/converter → `MongoDatabaseFactory` → `MongoClient` → MongoDB server. A failure at one layer should not be blamed blindly on the entire system.

## 19. Comprehensive Hands-On Lab

Build a Spring Boot and MongoDB lab application implementing two **alternative** wiring styles:

### Part A — Understanding the Layers

1. Draw a diagram from `MessageChannel` to `MongoClient`, noting each bean's responsibility.
2. Verify the exact imports for `MongoDatabaseFactory` and `SimpleMongoClientDatabaseFactory`.
3. Explain why the XML bean name `mongoDbFactory` is not the current Java interface name.
4. Compare `MongoOperations.find`, `MongoDatabaseFactory.getDatabase()`, and `MongoClient.getDatabase()`.

### Part B — Boot and Manual Configuration

1. Use Boot 3.x with `spring.data.mongodb.uri`; inject the auto-configured `MongoOperations` and save a `Reading`.
2. In **another** lab profile, manually configure `MongoClient`, the factory, and `MongoTemplate` as in section 6.
3. Try enabling both in the same context to observe bean ambiguity/auto-config back-off, then **fix** it by picking one approach.
4. Create a `Reading` with `@Id`, `@Field`, Decimal128, and timestamp; read it back via `MongoTemplate` to assert mapping.

### Part C — Adapter Integration

1. Use `MongoDb.inboundChannelAdapter(mongoOperations, query)` + poller + splitter to fetch `status=NEW`.
2. Try switching to the `MongoDatabaseFactory` overload in a separate lab flow without running two competing pollers.
3. Configure `MongoDbStoringMessageHandler(mongoOperations)` to persist `Message<Reading>`.
4. Switch to the factory constructor + appropriate `setMongoConverter`; verify identical schema mapping.
5. Use `MongoDb.outboundGateway(mongoOperations)`, then test the factory+converter overload in a separate flow.
6. Distinguish one `Message<List<Reading>>` from multiple `Message<Reading>`; verify `maxMessagesPerPoll` differs from `Query.limit`.

### Part D — Concurrency and Operations

1. Create two databases in the lab with two qualified factories/templates; verify the writer never cross-writes DBs.
2. Stop MongoDB and observe server selection errors, error handling, and bounded retries.
3. Send the same event ID twice to observe `save` vs. `insert` semantics; propose a unique index and idempotency.
4. Verify post-restart behavior to ensure the Spring-managed `MongoClient` closes cleanly.
5. If MongoDB has a replica set, add a transaction manager and test a real transaction; explain why it does not cover Kafka/HTTP.
6. Design metrics for query/write latency, pool usage, poll count, queue depth, and business commits.

**Self-assessment questions:**

- What is the difference between `MongoClient`, `MongoDatabaseFactory`, and `MongoTemplate`?
- Why can the name `MongoDbFactory` in older docs cause import errors in new projects?
- Which Java package does `MongoDatabaseFactory` belong to?
- Why should you inject `MongoOperations` instead of creating a `MongoClient` on every message?
- When should an Integration endpoint use `MongoOperations` vs. factory + converter?
- Why can `setMongoConverter` only be called on `MongoDbStoringMessageHandler` depending on the constructor used?
- How do `@Field("device_id")` and `@Id` affect how MongoDB stores data?
- Does `maxMessagesPerPoll(1)` mean the query returns exactly one document?
- Does a dynamic collection name switch to a different database?
- Why does using one factory/transaction manager not create a cross-cluster transaction?
- When should `ReactiveMongoOperations` be used instead of `MongoTemplate`?
- Does `send()==true` through a `QueueChannel` mean MongoDB has finished writing?

## 20. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): `MongoDatabaseFactory`, blocking/reactive, inbound/outbound adapters, gateway, and XML.
- [Spring Integration API — MongoDb Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): overloads accepting `MongoOperations`/`MongoDatabaseFactory`/`MongoConverter`.
- [Spring Integration API — MongoDbStoringMessageHandler](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/outbound/MongoDbStoringMessageHandler.html): constructors and `setMongoConverter` constraints.
- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html): factories, templates, and reactive counterparts.
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): CRUD/query API and converters.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Document`, `@Id`, `@Field`, and custom conversions.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, client sessions, and transaction limits.
- [MongoDB Manual — Connection Pooling](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): `MongoClient` pools and driver options.

## Conclusion

**`MongoTemplate`** provides the high-level API for MongoDB operations via `MongoOperations`; **`MongoDatabaseFactory`** selects the database and coordinates connections/sessions at the Spring Data layer; **`MongoClient`** is the driver that actually communicates with the server; and **`MongoConverter`** controls how Java objects map to BSON and back. The name **`MongoDbFactory`** appears in historical documentation, whereas modern Spring Data MongoDB code uses `MongoDatabaseFactory`.

In **SPRING_INTEGRATION_ADAPTERS**, let Spring Boot auto-configure the template when appropriate or build **one** clean client → factory → template pipeline with a clear lifecycle. Inbound adapters, outbound storing handlers, and outbound gateways can accept a template or factory/converter depending on the API; your choice must align with mapping, databases, access permissions, transactions, and delivery goals. **Proper connection configuration is only a prerequisite; reliable message processing also requires bounded queries, idempotency, retries, monitoring, and sound business design.**
