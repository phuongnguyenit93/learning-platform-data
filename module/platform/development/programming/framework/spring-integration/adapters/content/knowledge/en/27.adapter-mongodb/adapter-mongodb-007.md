# Query Fields, Sort, and Limit in Spring Integration MongoDB

## Learning Objectives

After this lesson, you will be able to:

- Read and build a Spring Data MongoDB `Query` with **filter**, **fields/projection**, **sort**, and **limit** matching your business contract.
- Understand why the MongoDB inbound channel adapter **`MongoDbMessageSource`** and outbound gateway **`MongoDbOutboundGateway`** need bounds on document counts, payload sizes, and result ordering.
- Use `Query.fields().include(...)` and `exclude(...)` to select returned fields; understand the special rule for `_id` and its impact on entity mapping.
- Use `Query.with(Sort.by(...))` for ascending/descending sorting; add a secondary `_id` tie-breaker when sort keys can collide to achieve deterministic total ordering.
- Use `Query.limit(n)` to bound **returned document count**, without confusing it with Spring Integration's `maxMessagesPerPoll` or the number of Spring Messages after a splitter.
- Compare **offset pagination** (`skip` + `limit`) and **keyset/cursor pagination** over changing datasets.
- Choose indexes aligned with filter + sort, inspect `explain` in a test environment, and distinguish **reducing returned data** from **speeding up queries**.
- Build an inbound polling flow, outbound request/reply gateway, transformer/splitter, and tests ensuring queries preserve tenant filters, result caps, and allowed fields only.
- Identify risks of **duplicate reads**, **skipped documents**, **overwriting due to missing entity fields**, **overly broad queries**, and handle retries/idempotency with multiple concurrent workers.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing files, SFTP, HTTP, JMS, AMQP, Kafka, and databases with emphasis on **message contracts, errors, and connection lifecycles**. Here, query fields, sort, and limit are decisions **at the MongoDB query layer** that directly impact payloads and performance in the downstream message flow.

## 1. Scenario: Reading Only Necessary Data for a Telemetry Pipeline

A `telemetry_events` collection holds millions of records. Each record has many fields and may carry a sizable device payload:

~~~json
{
  "_id": "evt-102",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "status": "NEW",
  "sequence": 102,
  "temperatureC": 26.5,
  "observedAt": "2026-11-20T08:00:01Z",
  "rawPayload": "large-sensor-frame-..."
}
~~~

The system has two needs:

1. **Background worker:** every 5 seconds poll up to 50 `NEW` events for `tenant-a`, fetching only the fields needed for processing, ordered oldest `observedAt` first.
2. **Request/reply API:** when a user looks up device history, return at most the 20 newest records with only displayable fields, excluding `rawPayload`.

If you simply write `find({ status: "NEW" })` with no bounds:

- A single poll can read huge numbers of documents and produce a **massive `Message<List<T>>`**.
- The splitter can emit thousands of messages in one cycle.
- An HTTP request can pull too much data into RAM, time out, or leak sensitive fields.
- Undefined sorting causes "newest" or "oldest" to be misinterpreted.
- Retrying a poll can re-read the same documents if their status still matches the query.

The solution is defining a **bounded, testable query contract**:

~~~mermaid
flowchart LR
    R["Poller or Request"] --> F["Criteria / Filter"]
    F --> S["Sort"]
    S --> L["Limit"]
    L --> P["Fields / Projection"]
    P --> DB[("MongoDB")]
    DB --> M["Message<List<T>> or Message<T>"]
    M --> H["Splitter / Reply / Handler"]
~~~

The diagram illustrates the clauses of a query; it does not claim MongoDB physically executes in that exact box order. The server has a query planner and can leverage indexes/optimizations; use `explain` to inspect actual execution.

## 2. Distinguishing Filter, Fields, Sort, Limit, and Skip

| Component | Question it answers | Spring Data API | Meaning |
|---|---|---|---|
| **Filter / criteria** | **Which documents** match? | `Query.query(Criteria.where(...))` | Filters by tenant, status, device, time |
| **Fields / projection** | **Which fields** are returned from each document? | `query.fields().include(...)` / `exclude(...)` | Reduces network bytes, constrains payload contract |
| **Sort** | In **what order** are results returned? | `query.with(Sort.by(...))` | ASC/DESC, tie-break with `_id` |
| **Limit** | At most **how many documents** to return? | `query.limit(n)` | Bounds batch/result size |
| **Skip** | How many leading results to skip? | `query.skip(n)` | Offset pagination; costly at large offsets |
| **Collection** | Which document set to query? | `find(query, Class, "collection")` | Collection within the selected database |
| **Entity class** | Which Java type to map results into? | `find(query, Event.class, ...)` | Spring Data MongoDB conversion |
| **Poller** | When to run the query? | `Pollers.fixedDelay(...)` | Spring Integration config, **not part of MongoDB `Query`** |

Same query in `mongosh`:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  { _id: 1, tenantId: 1, deviceId: 1, sequence: 1, observedAt: 1 }
).sort({ observedAt: 1, _id: 1 }).limit(50)
~~~

And in Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(Sort.by(
                Sort.Order.asc("observedAt"),
                Sort.Order.asc("_id")))
        .limit(50);

query.fields()
        .include("id")
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

In Java, `id` is the `@Id`-annotated property that Spring Data maps to `_id`. When using the raw MongoDB driver/`mongosh` directly, you must write the actual BSON field name such as `_id` since no Java mapping occurs automatically.

## 3. Dependencies and Lab Data

### 3.1. Maven Dependencies

A **Spring Boot 3.x** project can rely on Boot's dependency management:

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
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The examples use Java 17+, Spring Data `MongoOperations`, and the **blocking MongoDB driver**. For other Spring Boot/Spring Integration major versions, verify the BOM, starters, and APIs instead of copying isolated versions or mixing blocking/reactive.

In the lab's `application.yml` (Spring Boot 3.x):

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_query_lab
~~~

**Use a local URI for learning only.** Production requires secret management, appropriate TLS/roles, timeouts, pooling, and authorization. If Spring Boot already provides `MongoTemplate`/`MongoOperations`, reuse that bean.

### 3.2. Seeding Data with Colliding Sort Values

In `mongosh`, create data to distinguish ordering and projections:

~~~javascript
use adapter_query_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-101", tenantId: "tenant-a",
    deviceId: "node-7", status: "NEW", sequence: 101,
    temperatureC: 25.5,
    observedAt: ISODate("2026-11-20T08:00:00Z"),
    rawPayload: "private-frame-101"
  },
  {
    _id: "evt-102", tenantId: "tenant-a",
    deviceId: "node-7", status: "NEW", sequence: 102,
    temperatureC: 26.5,
    observedAt: ISODate("2026-11-20T08:00:01Z"),
    rawPayload: "private-frame-102"
  },
  {
    _id: "evt-103", tenantId: "tenant-a",
    deviceId: "node-8", status: "NEW", sequence: 103,
    temperatureC: 27.1,
    observedAt: ISODate("2026-11-20T08:00:01Z"),
    rawPayload: "private-frame-103"
  },
  {
    _id: "evt-104", tenantId: "tenant-a",
    deviceId: "node-8", status: "DONE", sequence: 104,
    temperatureC: 26.8,
    observedAt: ISODate("2026-11-20T08:00:02Z")
  },
  {
    _id: "evt-201", tenantId: "tenant-b",
    deviceId: "node-7", status: "NEW", sequence: 201,
    temperatureC: 29.4,
    observedAt: ISODate("2026-11-20T08:00:02Z")
  }
])
~~~

The worker's query for `tenant-a` and `status=NEW` returns `evt-101`, `evt-102`, and `evt-103` ordered by `observedAt ASC, _id ASC`. Document `evt-104` is `DONE` so it does not match, and `evt-201` belongs to another tenant so it must be excluded.

**Never run seeds on production.** Running `insertMany` again with duplicate IDs triggers duplicate-key errors. For integration tests, use an isolated database/collection and unique test IDs, cleaning up only the test documents you created.

### 3.3. Entity Mapping

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        String status,
        long sequence,
        BigDecimal temperatureC,
        Instant observedAt,
        String rawPayload) {
}
~~~

`@Document(collection="telemetry_events")` sets the entity's default collection when an operation does not pass another collection name. Spring Integration inbound/gateway endpoints can **select a collection explicitly**, so always verify the `MongoOperations` bean, database, and collection when diagnosing query mismatches.

## 4. Query.fields(): What Is Projection?

**Projection** means selecting only a subset of fields in MongoDB query results rather than loading the entire BSON document. That is what **fields** means in this lesson's title, not Java reflection fields.

For instance, a document has a large `rawPayload` but the handler only needs ID, tenant, device, sequence, and timestamp. We ask MongoDB to return only those fields:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  {
    _id: 1,
    tenantId: 1,
    deviceId: 1,
    sequence: 1,
    observedAt: 1
  }
)
~~~

Example output:

~~~json
{
  "_id": "evt-101",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "sequence": 101,
  "observedAt": "2026-11-20T08:00:00Z"
}
~~~

**`rawPayload`, `status`, and `temperatureC` are omitted from the response** even though they remain in the underlying document. This reduces network bandwidth and bytes mapped by the app, though it does not automatically guarantee the query only reads those fields from disk; actual performance depends on indexes and the query planner.

### 4.1. Including Fields: include

Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"));

query.fields()
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

When at least one field is included, MongoDB returns only the included fields **plus `_id` by default**. You do not need `.include("id")` solely to keep the ID. Still, when a project uses `@Id` mappings across different classes, test actual field names and results.

### 4.2. Excluding Fields: exclude

If you want most of the document while dropping the raw payload:

~~~java
query.fields().exclude("rawPayload");
~~~

This statement is **an alternative** to the `include(...)` chain above; do not combine including regular fields and excluding other regular fields on the same query.

### 4.3. Special Rule for _id

In MongoDB projections:

- `_id` is **included by default** unless explicitly excluded.
- You may include other fields and **exclude `_id`**.
- You generally cannot mix **include** and **exclude** across other fields—`_id` is the exception.

Example returning only device ID and sequence without `_id`:

~~~java
query.fields()
        .include("deviceId")
        .include("sequence")
        .exclude("id"); // Mapped @Id -> MongoDB _id
~~~

Equivalent `mongosh` query:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a" },
  { deviceId: 1, sequence: 1, _id: 0 }
)
~~~

**Think carefully before omitting `_id`.** For flows requiring deduplication, ACKs, retries, or marking `DONE`, the event ID is usually a critical key. If projection strips it, downstream may lack the data needed for idempotency.

### 4.4. Nested Fields and @Field

Suppose the entity has property `deviceId` while MongoDB stores `device_id`:

~~~java
@org.springframework.data.mongodb.core.mapping.Field("device_id")
String deviceId;
~~~

With `MongoTemplate` and entity mapping, you can use property name `deviceId` in `Criteria` or `query.fields()`, letting Spring Data translate to the BSON field. With the **raw driver/`mongosh`**, however, you must use the actual BSON name `device_id`.

For nested documents, select fields using dot notation:

~~~java
query.fields().include("device.location.city");
~~~

When projecting a small branch of a nested document, sibling fields will be absent after mapping. Verify deserialized object types and schema versions, especially with Java records having required fields.

## 5. Projection and Entity Class: Avoid Reading Half a Document and Saving It Back

If you use `TelemetryEvent.class` from section 3 while projecting only `id`, `tenantId`, `deviceId`, `sequence`, and `observedAt`, unreturned fields become **null/default** depending on type and mapping. For example:

~~~text
Original MongoDB document:
  _id, tenantId, deviceId, status, sequence,
  temperatureC, observedAt, rawPayload

Projection:
  _id, tenantId, deviceId, sequence, observedAt

Mapped entity:
  id = "evt-101"
  status = null
  temperatureC = null
  rawPayload = null
~~~

**Never pass a partially read entity straight into MongoDB outbound `save(...)` to update a single field.** `save` can replace the entire document by ID, wiping out fields omitted from the projection or overwriting them with null/default values.

### 5.1. Use a DTO Matching the Projection

Create a class/record containing only the queried fields:

~~~java
package example.mongodb;

import java.time.Instant;

import org.springframework.data.annotation.Id;

public record TelemetrySummary(
        @Id String id,
        String tenantId,
        String deviceId,
        long sequence,
        Instant observedAt) {
}
~~~

When only a summary is needed, read with `MongoOperations`:

~~~java
List<TelemetrySummary> summaries = mongoOperations.find(
        query, TelemetrySummary.class, "telemetry_events");
~~~

In Spring Integration, if an inbound/gateway query reads summaries, set `entityClass(TelemetrySummary.class)` and keep the projection aligned. Because the DTO lacks `status` and `rawPayload`, downstream **cannot assume** those fields exist.

When you need to update a full entity, query all required fields per contract or perform a **conditional partial update** using `MongoOperations.updateFirst` / `findAndModify` instead of saving a field-incomplete object.

### 5.2. Projection Does Not Replace Authorization

Restricting fields is a protective layer, but **it is insufficient for authorization**. Queries must also enforce server-authenticated tenant/owner filters, and the MongoDB account should have least privilege. Never rely on frontend UI hiding to prevent reading another tenant's collections or fields.

## 6. Query.with(Sort): Business-Meaningful Ordering

Sort defines the order of documents **in the query result**.

| Need | Sort | Notes |
|---|---|---|
| Oldest events first | `Sort.by(ASC, "observedAt")` | Add `_id` to handle timestamp ties |
| Newest events first | `Sort.by(DESC, "observedAt")` | History APIs, dashboards |
| Highest priority first | `Sort.by(DESC, "priority")` | Requires a tie-breaker rule |
| FIFO by inbox insertion | `createdAt ASC, _id ASC` | Only "FIFO" if `createdAt` matches contract |
| Stable-key pagination | `observedAt DESC, _id DESC` | Useful for keyset pagination |

### 6.1. Deterministic Sorting with a Tie-Breaker

Suppose `evt-102` and `evt-103` share the same `observedAt`. Sorting solely by timestamp leaves their relative order non-deterministic in MongoDB.

Configuration:

~~~java
Sort oldestFirst = Sort.by(
        Sort.Order.asc("observedAt"),
        Sort.Order.asc("_id"));

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(oldestFirst)
        .limit(50);
~~~

Expected result on lab data:

~~~text
evt-101  2026-11-20T08:00:00Z
evt-102  2026-11-20T08:00:01Z
evt-103  2026-11-20T08:00:01Z
~~~

Adding `_id` makes ordering deterministic when timestamps tie, though **it does not prove IDs encode real-world time**. If "exact occurrence order" is required, you need reliable timestamps/sequences, late-arrival policies, and clock-drift handling.

### 6.2. ASC and DESC

~~~java
// Oldest first:
Sort.by(
    Sort.Order.asc("observedAt"),
    Sort.Order.asc("_id"));

// Newest first:
Sort.by(
    Sort.Order.desc("observedAt"),
    Sort.Order.desc("_id"));
~~~

These are **two alternatives**. Do not chain multiple `.with(...)` calls guessing how sorts merge; build one complete `Sort` for a query contract.

### 6.3. Sort Applies Even If Fields Are Projected Out

MongoDB can sort on fields omitted from the returned projection. For example, a query sorts by `observedAt` while the API returns only device ID and sequence. However, if the API uses **cursor pagination**, it may need the sort fields to build the next-page cursor; keep required cursor fields in the DTO/cursor.

### 6.4. Indexes and Sorting

An unindexed sort may scan many documents or trigger an in-memory sort on the server. Never assume `limit(20)` prevents MongoDB from reading/examining extra documents.

Inspect `explain("executionStats")` in the lab to see `IXSCAN`, `COLLSCAN`, or sort stages. Plan details vary with MongoDB version, data distribution, and indexes; never hard-code expectations of a single plan for every dataset.

## 7. Query.limit(): Limits Documents, Not Poll Count

`Query.limit(50)` requests at most **50 documents** for that single query execution:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(Sort.by(
                Sort.Order.asc("observedAt"),
                Sort.Order.asc("_id")))
        .limit(50);
~~~

If 1,000 documents match, this query returns at most 50. However, it **does not remove** those 50 documents from the collection; if the next poll still runs `status=NEW`, it can fetch the exact same 50 documents again.

### 7.1. maxMessagesPerPoll(1) Is Completely Different from limit(1)

| Setting | Layer | What it bounds |
|---|---|---|
| `Pollers.fixedDelay(5000)` | Spring Integration poller | When to invoke the source |
| `maxMessagesPerPoll(1)` | Polling endpoint | Max `receive()` calls per poll cycle |
| `Query.limit(50)` | MongoDB query | Max documents returned in **one query** |
| `expectSingleResult(true)` | MongoDB message source | Uses `findOne`, one document per `receive()` |
| `.split()` | Spring Integration | One `List` message → multiple individual messages |
| `QueueChannel(64)` | Spring Messaging | Capacity in Spring Messages on the queue |
| `replyTimeout=5000` | Messaging gateway | Caller wait timeout for a reply, not a query limit |

Example:

~~~text
MongoDB has 10,000 NEW documents
Poller.maxMessagesPerPoll(1)
Source uses find(query.limit(50))
=> At most 1 Message<List<50 documents>> from source
=> Splitter produces at most 50 Message<T>
=> No claim state? Next poll can re-read those same 50 documents.
~~~

This is why both **query limits** and **downstream rate/capacity bounds** are necessary.

### 7.2. Limit Alone Does Not Cap Bytes

If each document carries several MB of binary/raw payload, 50 documents can still be a huge batch. Combine **fields projection**, document size caps, record validation, and lowering limits to 10 or fewer based on real load measurements.

### 7.3. Why limit(0) Is Not a Safe Cap

In MongoDB/Spring Data, `limit(0)` typically means **no effective document count limit**. For user-supplied requests, validate a positive bound. Never let an input of `0` become an unbounded query thinking it will return zero documents.

Validation example:

~~~java
public record SearchTelemetryRequest(
        String deviceId, int limit) {

    public SearchTelemetryRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "deviceId invalid or limit out of [1,100]");
        }
    }
}
~~~

### 7.4. Limit Does Not Replace Retries, Dedup, or Transactions

Even with `limit(1)` to grab one job, two instances can see the same job before either updates its status. Exclusive claiming requires an **atomic conditional MongoDB update** such as `findAndModify` in a work-queue design. Sort + limit only **selects**; it does not **acquire ownership**.

## 8. Combining Criteria, Fields, Sort, and Limit into a Complete Query

Extract query builders into a dedicated class for unit testing:

~~~java
package example.mongodb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class MongoReadQueries {

    private MongoReadQueries() {}

    public static Query inboxBatch(
            String tenantId, int requestedLimit) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "tenantId must be authorized");
        }
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException(
                    "Batch size must be 1..100");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(requestedLimit);

        query.fields()
                .include("tenantId")
                .include("deviceId")
                .include("sequence")
                .include("observedAt");

        // MongoDB still returns _id by default.
        return query;
    }

    public static Query recentByDevice(
            String tenantId, SearchTelemetryRequest request) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing authorized tenant");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("deviceId").is(request.deviceId()))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(request.limit());

        query.fields()
                .include("tenantId")
                .include("deviceId")
                .include("sequence")
                .include("observedAt");

        return query;
    }
}
~~~

**The two queries serve different purposes:**

- `inboxBatch(...)` serves workers: filters `status=NEW`, **oldest first**, bounded batch.
- `recentByDevice(...)` serves search APIs: filters device ID and tenant, **newest first**, bounded by request.

In the example, `tenantId` is a parameter for demo clarity; in production it must come from a **server-authenticated identity/authorization context**, never trusted blindly from client input.

### 8.1. Testing Queries Before Wiring an IntegrationFlow

You can invoke `MongoTemplate` directly:

~~~java
List<TelemetrySummary> batch = mongoOperations.find(
        MongoReadQueries.inboxBatch("tenant-a", 50),
        TelemetrySummary.class,
        "telemetry_events");
~~~

This helps verify query logic at the Spring Data layer before adding adapters/pollers. If the query is wrong at `MongoOperations`, wrapping it in a `MessageChannel` will not fix it.

### 8.2. Never Share and Mutate One Query Across Threads

`Query` is a mutable object holding fields, sort, and limit. Never create a singleton `Query` and let concurrent HTTP requests or pollers mutate its `limit` per caller.

**Create a new `Query` per operation**, like the two factory methods above. This eliminates race conditions and lets each request be tested with independent criteria.

## 9. Inbound Polling: Fields/Sort/Limit in MongoDbMessageSource

In MongoDB inbound, the **poller** invokes `MongoDbMessageSource.receive()`. The source runs the configured query and emits a message when data exists. By default per source contract:

- `expectSingleResult(false)` calls `MongoOperations.find(...)` and returns **`Message<List<T>>`**.
- `expectSingleResult(true)` calls `findOne(...)` and returns **`Message<T>`**.
- An empty list is treated as no message.

### 9.1. Java DSL with a Bounded, Projected Query

Create a batch-bounded inbound adapter:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class BoundedMongoInboundConfig {

    @Bean("inboxSummaries")
    public MessageChannel inboxSummaries() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboxFlow(
            MongoDatabaseFactory mongoDatabaseFactory) {

        return IntegrationFlow
            .from(
                MongoDb.inboundChannelAdapter(
                        mongoDatabaseFactory,
                        MongoReadQueries.inboxBatch("tenant-a", 50))
                    .collectionName("telemetry_events")
                    .entityClass(TelemetrySummary.class)
                    .expectSingleResult(false),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("inboxSummaries")
            .get();
    }
}
~~~

**API note:** Spring Integration Java DSL provides `MongoDb.inboundChannelAdapter(MongoDatabaseFactory, Query)`. Do not assume a `(MongoOperations, Query)` overload exists on the blocking factory in every version; with `MongoOperations`, the DSL provides **query-string** overloads. If you already have `MongoTemplate` and want to pass a `Query` object directly, configure `MongoDbMessageSource` with an `Expression` returning `Query` as in section 10.

In the example, `TelemetrySummary` has only the selected fields, so downstream cannot expect status, temperature, or raw payload. If a handler needs `status` to branch logic, **add that field to the projection/DTO** or formalize a contract where the source only fetches `NEW`.

### 9.2. Handler Receiving a Summary

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class SummaryObserver {

    private static final Logger log =
            LoggerFactory.getLogger(SummaryObserver.class);

    @ServiceActivator(inputChannel = "inboxSummaries")
    public void observe(TelemetrySummary summary) {
        log.info("Polled id={}, tenant={}, device={}, sequence={}",
                summary.id(), summary.tenantId(),
                summary.deviceId(), summary.sequence());

        // Observe only. Does not mark DONE or ACK source.
    }
}
~~~

**This is a read-only demo.** After 5 seconds, the `NEW` documents just read still exist in the collection and keep matching the query; even with `limit(50)`, the first batch can be read **repeatedly forever**. Production requires claim/lease, retries, and idempotency (section 14).

### 9.3. Why maxMessagesPerPoll and limit Must Work Together

Suppose 5,000 `NEW` documents exist:

~~~text
fixedDelay(5000)
maxMessagesPerPoll(1)
Query.limit(50)
    |
    v
1 MongoDB query <= 50 documents
    |
    v
1 Message<List<TelemetrySummary>>
    |
    v
Splitter => <= 50 Message<TelemetrySummary>
~~~

Setting `maxMessagesPerPoll(1)` alone does not stop the query from returning 5,000 documents. Setting `limit(50)` alone does not stop continuous polls from re-emitting the same 50 documents if state never changes.

## 10. MongoDbMessageSource Accepting a Dynamic Query via SpEL

If using Boot's auto-configured `MongoOperations`, the source can accept an `Expression` returning a fresh `Query` on every `receive()`.

### 10.1. A Provider Building a Query per Poll

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoInboxQueryPlan")
public class MongoInboxQueryPlan {

    public Query nextBatch() {
        // In production, tenant/work type must come from
        // an authorized policy, not unvalidated input.
        return MongoReadQueries.inboxBatch("tenant-a", 50);
    }
}
~~~

### 10.2. Configuring the Source with an Expression

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;

@Configuration
@EnableIntegration
public class SpelMongoSourceConfig {

    @Bean
    public MongoDbMessageSource boundedSource(
            MongoOperations mongoOperations) {

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongoOperations,
                new SpelExpressionParser().parseExpression(
                    "@mongoInboxQueryPlan.nextBatch()"));

        source.setCollectionNameExpression(
                new LiteralExpression("telemetry_events"));
        source.setEntityClass(TelemetrySummary.class);
        source.setExpectSingleResult(false);
        return source;
    }

    @Bean
    public IntegrationFlow boundedSourceFlow(
            MongoDbMessageSource boundedSource) {

        return IntegrationFlow
            .from(boundedSource,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("inboxSummaries")
            .get();
    }
}
~~~

This example is an **alternative** to section 9; do not register both flows scanning `NEW` data in the same context. `MongoInboxQueryPlan` must be a Spring bean with the matching `inboxSummaries` channel/handler.

**Context reminder:** inbound polling **has no incoming request Message**, so expressions like `payload.deviceId` make no sense as they do in an outbound gateway. On the source, use a policy bean, configuration, scheduler-controlled state, or managed query provider.

### 10.3. Dynamic Queries Also Need Limits Across All Branches

If `nextBatch()` occasionally returns a `Query` missing `limit`, having limits on other branches will not save that poll. Verify query contracts in unit tests across `NEW`/`RETRY` branches, tenants, and post-restart states.

## 11. Outbound Gateway: Per-Request Queries with Fields, Sort, and Limit

`MongoDbOutboundGateway` is a **request/reply endpoint**, unlike inbound polling. It receives a request `Message`, executes the query, and returns a reply over the appropriate channel.

### 11.1. Java DSL Configuration

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
    public IntegrationFlow searchFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoSearchRequests")
            .handle(MongoDb.outboundGateway(mongoOperations)
                .collectionName("telemetry_events")
                .entityClass(TelemetrySummary.class)
                .expectSingleResult(false)
                .queryFunction(
                    (Message<SearchTelemetryRequest> message) ->
                        MongoReadQueries.recentByDevice(
                            "tenant-a",
                            message.getPayload())))
            .get();
    }
}
~~~

Here `queryFunction` receives the **request `Message`**, extracts the validated DTO from `payload`, and builds a `Query` with filter + fields + sort + limit. Treat `"tenant-a"` as a lab placeholder: real applications must obtain the tenant from a trusted authentication/authorization context, never a client-supplied string.

The flow **does not force replies onto a static `QueueChannel`**, because concurrent callers need their own `replyChannel`. To expose a clean API, use a `@MessagingGateway` interface.

### 11.2. @MessagingGateway to Pair Request and Reply

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface TelemetrySearchApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetrySummary> recent(
            SearchTelemetryRequest request);
}
~~~

Caller:

~~~java
List<TelemetrySummary> results = searchApi.recent(
        new SearchTelemetryRequest("node-7", 20));
~~~

The call sits inside a service injected with `TelemetrySearchApi`. `@IntegrationComponentScan` must scan the package containing the interface, or an equivalent proxy registration must be active.

**Do not share a single reply `QueueChannel`** and let two HTTP requests call `receive()` without correlation; caller A's reply could be stolen by caller B. `@MessagingGateway` creates temporary reply channels to match each reply to its call.

### 11.3. Reading One Document with expectSingleResult(true)

When `expectSingleResult(true)` is enabled, the gateway calls `findOne(...)` and returns one entity when present. **It does not pick "the newest document" if the `Query` lacks a sort.** `Query.limit(20)` does not turn `findOne` into a 20-document list. When no document exists, verify the no-result/no-reply contract and timeout; never assume a Spring `Message` carries a `null` payload.

### 11.4. Reply Payload Is a List Even for One Result

With `expectSingleResult(false)`, `find(...)` returns a `List<TelemetrySummary>`. If the DB contains only one document, the reply still wraps a **`List`** rather than unwrapping automatically. For empty queries, the list gateway path can emit an empty list; business APIs should define returning `[]` distinctly from database errors.

## 12. Pagination: skip/limit vs. Keyset

API queries often require pagination rather than a single fixed limit.

### 12.1. Offset Pagination with skip

Page 3, 20 items per page:

~~~java
int pageNumber = 3; // 1-based
int pageSize = 20;

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("deviceId").is("node-7"))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .skip((long) (pageNumber - 1) * pageSize)
        .limit(pageSize);
~~~

**Advantages:** easy to understand, suited to small datasets or UIs with fixed page numbers.

**Limitations:** large offsets are costly because the server must walk past many records to skip them; when documents are inserted or deleted while a user paginates, items can **duplicate or be skipped across pages** even with a deterministic sort.

Cap page numbers, page sizes, and total allowed offset. Never let clients request massive skips without a resource budget.

### 12.2. Keyset Pagination Using Tuple (observedAt, _id)

With newest-first sorting `observedAt DESC, _id DESC`, the next page fetches documents whose key is **less than the last item of the previous page**:

~~~text
last page item:
  observedAt = 2026-11-20T08:00:01Z
  _id = "evt-102"

next page condition:
  observedAt < lastObservedAt
  OR (observedAt == lastObservedAt AND _id < lastId)
~~~

Spring Data query:

~~~java
import java.time.Instant;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Instant lastObservedAt = Instant.parse(
        "2026-11-20T08:00:01Z");
String lastId = "evt-102";

Criteria afterCursor = new Criteria().orOperator(
        Criteria.where("observedAt").lt(lastObservedAt),
        new Criteria().andOperator(
            Criteria.where("observedAt").is(lastObservedAt),
            Criteria.where("_id").lt(lastId)));

Query query = Query.query(
        new Criteria().andOperator(
            Criteria.where("tenantId").is("tenant-a"),
            Criteria.where("deviceId").is("node-7"),
            afterCursor))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .limit(20);

query.fields()
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

This example **illustrates keyset pagination with String BSON `_id` matching the lab data**. If production uses `ObjectId` or another ID type, use matching BSON/mapping types in comparisons; never assume String ID comparison equals `ObjectId` ordering in every case.

Keyset advantages:

- Avoids large `skip` offsets.
- Pairs well with stable sort keys and supporting indexes.
- Maintains better performance than offset pagination as datasets grow.

Limitations:

- Hard to "jump directly to page 500".
- Must retain all sort keys to construct the cursor.
- Cursor sort fields should be **non-null** and not mutated arbitrarily.
- Updating `observedAt` or deleting documents between requests can still affect results.
- Cursors should be encoded/validated against tampering or bind query filter/tenant to prevent cross-tenant cursor reuse.

Spring Data MongoDB also supports **`ScrollPosition`/`KeysetScrollPosition`** in compatible versions; if using that API, read the exact version Javadocs and test ID mapping/sorting. The example above uses plain `Criteria` so conditions remain explicit.

### 12.3. Never Use skip to "Mark Already Polled"

Some developers write inbound sources like:

~~~text
Poll #1: skip=0, limit=50
Poll #2: skip=50, limit=50
Poll #3: skip=100, limit=50
~~~

This is **unsafe** when documents are processed, change status, or get deleted between polls: positions shift and documents get skipped. For work queues, use **claim/lease** or a checkpoint/keyset with well-defined, recoverable semantics.

## 13. Optimizing Indexes for Filter + Sort

Suppose a worker queries:

~~~text
Filter: tenantId = tenant-a, status = NEW
Sort:   observedAt ASC, _id ASC
Limit:  50
Fields: _id, tenantId, deviceId, sequence, observedAt
~~~

Suggested lab index:

~~~javascript
db.telemetry_events.createIndex({
  tenantId: 1,
  status: 1,
  observedAt: 1,
  _id: 1
})
~~~

This supports equality filtering on `tenantId`/`status` and sorting on `observedAt`/`_id`. Actual effectiveness depends on data, cardinality, MongoDB version, and query plans; always verify with `explain` instead of assuming an index works just because it exists.

In `mongosh`:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  { _id: 1, tenantId: 1, deviceId: 1,
    sequence: 1, observedAt: 1 }
).sort({ observedAt: 1, _id: 1 })
 .limit(50)
 .explain("executionStats")
~~~

Inspect `totalDocsExamined`, `totalKeysExamined`, returned document count, and execution stages, comparing on data matching production scale and distribution.

### 13.1. Projection Does Not Automatically Create a Covered Query

The query above projects `deviceId`/`sequence`, which are not in the suggested index. MongoDB still has to fetch full documents to read those fields. For a **covered query**, the index must include all filter/sort/projected fields (subject to multikey/collation rules); overly wide indexes increase write costs and storage size.

**Never index every field combination just for coverage** unless workload metrics justify it. Balance read speed, write throughput, RAM, and operational cost.

### 13.2. Sorting on Missing or Null Fields

When some documents lack `observedAt`, sorting and keyset semantics become brittle. In critical telemetry pipelines, validate sort and cursor fields before storing; consider partial indexes, schema migrations, or legacy-record policies.

### 13.3. Collation and Comparison Types

String sorting can vary with collation/case sensitivity. Lab `_id` values like `evt-101` work cleanly under controlled lexicographic comparison; if production mixes String/`ObjectId` types, enforce a consistent schema before relying on keyset cursors.

## 14. Safe Polling: Sort + Limit Does Not Prevent Duplicates

A common misconception:

> "I sorted by time and set limit 50, so each poll automatically fetches the next 50 jobs."

**False unless the query filter or document state changes.** MongoDB does not track which documents were returned by independent `find()` calls. Repeating the query returns the same still-matching documents.

~~~mermaid
flowchart TD
    A["Poller"] --> Q["find(status=NEW, sort, limit=50)"]
    Q --> R["50 docs"]
    R --> M["Message<List<T>>"]
    M --> H{"Claim/ACK present?"}
    H -->|"No"| Q
    H -->|"Yes + completed"| U["DB state changes"]
    U --> N["Next query can select a different batch"]
~~~

### 14.1. updateExpression Is Not a Business ACK

The MongoDB inbound adapter can be configured to update retrieved documents, e.g., flipping `NEW` to `CLAIMED`:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongoOperations, "{ 'status': 'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

**This is only a builder snippet** that needs to be placed into a flow with a poller. It shows how to stop documents from matching the next query; it **does not guarantee downstream committed** and does not turn query+update into an atomic multi-worker claim.

### 14.2. When Two Workers Run

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as MongoDB
    A->>D: find(status=NEW).sort(...).limit(50)
    B->>D: find(status=NEW).sort(...).limit(50)
    D-->>A: evt-101..evt-150
    D-->>B: evt-101..evt-150
    Note over A,B: Both may process the same set
~~~

Production solution when exclusivity is needed: **atomic per-document claim** (typically `findAndModify` with status/lease conditions), owner/version, lease expiration, retry/backoff, idempotency keys, and marking `DONE` only after business completion.

### 14.3. Projection Must Retain ID to Complete Work

If downstream marks `DONE` by `_id`, the projection must include the ID. Stripping `_id` to "save bytes" leaves the handler unable to identify which document to ACK or deduplicate.

### 14.4. Data Mutating During Pagination

If you use offset pagination over `NEW` documents while marking each processed document `DONE`, the matching set shrinks and the next poll's `skip` will skip over documents. For work queues, **never advance `skip` as a checkpoint**. Use claims + re-querying `NEW`/`RETRY` or a durable keyset with clear conditions depending on your business model.

## 15. XML: query-expression Returning a Query with Fields, Sort, Limit

Spring Integration MongoDB XML allows `query-expression` to return a Spring Data `Query`. Not all options like `fields/sort/limit` have separate XML attributes on the inbound adapter; they can be defined inside the `Query` object.

Policy bean example:

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoReadPlan")
public class MongoReadPlan {

    public Query queryForPoll() {
        return MongoReadQueries.inboxBatch("tenant-a", 50);
    }
}
~~~

XML inbound adapter:

~~~xml
<!-- XML with version-appropriate int and int-mongodb namespaces -->
<int:channel id="inboxBatchResults"/>

<int-mongodb:inbound-channel-adapter
        id="mongoBoundedInbound"
        channel="inboxBatchResults"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query-expression="@mongoReadPlan.queryForPoll()"
        entity-class="example.mongodb.TelemetrySummary">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

In this XML snippet, the output channel receives **`Message<List<TelemetrySummary>>`** when results exist; if the handler wants individual events, add an external splitter or implement the handler accordingly.

**Choose either `query` or `query-expression`.** When using `query-expression` to supply a `Query`, never also set `query="{...}"` expecting the framework to merge them.

### 15.1. XML Outbound Gateway Also Supports query-expression

Example when requests are validated DTOs:

~~~xml
<int:channel id="mongoSearchRequests"/>
<int:channel id="mongoSearchReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoSearchGateway"
        request-channel="mongoSearchRequests"
        reply-channel="mongoSearchReplies"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query-expression="@mongoReadQueryPolicy.forRequest(payload)"
        entity-class="example.mongodb.TelemetrySummary"/>
~~~

The `mongoReadQueryPolicy` bean must exist; `forRequest(payload)` returns a `Query` with filter/projection/sort/limit. This is an **illustrative request/reply flow with a static reply queue**, not safe by default for multiple concurrent HTTP requests. With multiple callers, use temporary reply channels created by `@MessagingGateway` or an explicit correlation scheme.

## 16. Testing Query Builders Without MongoDB

### 16.1. Unit Testing Fields/Sort/Limit and Tenant Conditions

JUnit 5:

~~~java
package example.mongodb;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

class MongoReadQueriesTest {

    @Test
    void inboxQueryHasRequiredLimitsAndFields() {
        Query query = MongoReadQueries.inboxBatch(
                "tenant-a", 50);

        Document filter = query.getQueryObject();
        Document projection = query.getFieldsObject();
        Document sort = query.getSortObject();

        assertEquals("tenant-a",
                filter.getString("tenantId"));
        assertEquals("NEW",
                filter.getString("status"));
        assertEquals(50, query.getLimit());

        assertEquals(1, projection.getInteger("deviceId"));
        assertEquals(1, projection.getInteger("sequence"));
        assertFalse(projection.containsKey("rawPayload"));

        assertEquals(1, sort.getInteger("observedAt"));
        assertEquals(1, sort.getInteger("_id"));
    }

    @Test
    void queryRejectsInvalidBatchLimit() {
        assertThrows(IllegalArgumentException.class,
            () -> MongoReadQueries.inboxBatch("tenant-a", 0));
        assertThrows(IllegalArgumentException.class,
            () -> MongoReadQueries.inboxBatch("tenant-a", 101));
    }

    @Test
    void searchQueryIsNewestFirst() {
        Query query = MongoReadQueries.recentByDevice(
            "tenant-a",
            new SearchTelemetryRequest("node-7", 20));

        assertEquals("node-7",
                query.getQueryObject().getString("deviceId"));
        assertEquals(20, query.getLimit());
        assertEquals(-1,
                query.getSortObject().getInteger("observedAt"));
        assertEquals(-1,
                query.getSortObject().getInteger("_id"));
    }
}
~~~

**These assertions inspect the `Query` object before Spring Data maps Java properties to BSON fields.** If an entity uses `@Field("device_id")`, `MongoTemplate`'s query mapper translates field names according to the entity class. To verify fields **in real MongoDB**, run an integration test.

### 16.2. Testing Ordering, Batch Size, and Projection Against a Real Database

Use a lab MongoDB or Testcontainers (if supported by the runner), seeding documents with deterministic IDs and timestamps:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoReadProjectionIntegrationTest {

    @Autowired
    MongoOperations mongoOperations;

    @Test
    void returnsBoundedOldestFirstSummaries() {
        List<TelemetrySummary> items = mongoOperations.find(
                MongoReadQueries.inboxBatch("tenant-a", 2),
                TelemetrySummary.class,
                "telemetry_events");

        assertEquals(2, items.size());

        assertEquals("evt-101", items.get(0).id());
        assertEquals("evt-102", items.get(1).id());

        assertEquals("tenant-a", items.get(0).tenantId());
        assertNotNull(items.get(0).observedAt());
    }
}
~~~

**Prerequisite:** the test DB has the exact seed from section 3 and is not modified by other tests. When using a fresh Testcontainers instance, seed in test setup. This test does not start a MongoDB server itself; never run it against production.

To verify actual projection, read raw `Document`s with the configured `Query` and assert `rawPayload` is absent, or inspect BSON sent/received in the test setup. Checking that `TelemetrySummary` lacks a `rawPayload` property is **insufficient** to prove MongoDB's projection excluded it over the wire; assert `Query.fields()` or raw results.

### 16.3. Testing the Outbound Gateway per Request

With `TelemetrySearchApi` from section 11:

~~~java
@Autowired
TelemetrySearchApi searchApi;

@Test
void searchRespectsLimitAndTenantScope() {
    List<TelemetrySummary> results = searchApi.recent(
            new SearchTelemetryRequest("node-7", 2));

    assertTrue(results.size() <= 2);
    assertTrue(results.stream().allMatch(
        item -> "tenant-a".equals(item.tenantId())
                && "node-7".equals(item.deviceId())));
}
~~~

This is a **fragment inside a test class with a Spring context and seeded test DB**. To avoid false positives, add `assertFalse(results.isEmpty())` or assert seeded IDs; `allMatch` alone returns true on an empty list and can mask wiring bugs.

### 16.4. Testing Inbound Polling via QueueChannel

Configure a test-only flow:

~~~text
Test MongoDB collection
   -> MongoDbMessageSource + Poller
   -> Message<List<TelemetrySummary>>
   -> Splitter
   -> QueueChannel test sink
   -> JUnit receive(timeout)
~~~

Assertions should include:

1. Await messages via `receive(5000)` instead of fixed sleeps.
2. Assert payload type `TelemetrySummary` after the splitter.
3. Assert exact ID/tenant/sequence/timestamp values.
4. Assert the `MongoHeaders.COLLECTION_NAME` header matches.
5. With 60 `NEW` documents and `limit=50`, verify **one query** returns at most 50.
6. When no results exist, verify the source does not fabricate null payloads.
7. Never run two pollers querying the same test data if deterministic results are expected.
8. When testing `Query.limit`, avoid upstream status updates or mutations interfering with assertions.
9. Use an isolated test collection and stop the poller before cleanup.
10. Run across two cycles to catch re-polling when not claiming.

## 17. Common Errors

| Error / symptom | Cause | Fix |
|---|---|---|
| `limit(50)` yet handler receives 50 messages | Splitter splits one `List` into 50 Messages | Expected contract; distinguish documents from source messages |
| `maxMessagesPerPoll(1)` yet loads huge data | One `find()` returns a large `List` | Set `Query.limit` |
| `limit(0)` returns tons of documents | `0` does not mean "return 0" in the API | Validate `n >= 1` |
| Sorted only by `observedAt`, results swap order | Multiple documents share identical timestamps | Add `_id` tie-breaker |
| Sorted newest first yet order looks random | Missing `with(Sort)` on final query | Unit test `getSortObject` |
| Java entity has missing fields | Projection excluded those fields | Use a dedicated projection DTO or fetch all needed fields |
| Saving projected entity loses data | Overwrites document with missing fields | Use partial update, never blind `save` |
| Query has tenant filter yet test finds nothing | Wrong DB/collection or field-name mapping | Check `MongoOperations`, `Query`, and seed |
| Query returns huge `List` despite slow poller | Poller does not bound query results | Projection + limit + bounded downstream |
| Skip pagination misses records | Dataset mutates between pages | Appropriate keyset/claim/checkpoint |
| Keyset misses records when sort key is null | Cursor condition mishandles missing fields | Validate/migrate sort keys |
| `_id` missing from result | Projection explicitly excluded `id` | Keep `id` if needed for dedup/ACK |
| Query ignores index | Index does not match filter/sort/collation | Run `explain` on realistic test data |
| Outbound gateway times out | Heavy query or wrong reply channel | Query limit/index/timeouts/correlation |
| Poll re-reads 50 documents repeatedly | State/claim not updated | Claim/lease/idempotency |
| Multiple workers process duplicates | Concurrent `NEW` queries before update | Atomic claim by owner/version |
| App RAM spikes | Huge `List`, `rawPayload`, and queues | Fields projection, smaller batches, bounded queues |
| Another tenant's data appears | Missing tenant filter, weak authorization | Server-side tenant scope + security tests |

Always isolate in sequence:

~~~text
Business request / Poller
   -> Query builder (filter + fields + sort + limit)
   -> MongoOperations / MongoTemplate
   -> MongoDB database & collection
   -> find/findOne result
   -> MongoDbMessageSource / MongoDbOutboundGateway
   -> Message payload/headers
   -> Splitter / channel / handler
~~~

Do not conclude "MongoDB returned incomplete data" before checking projections. Do not conclude "Spring Integration created duplicates" before checking whether the query repeatedly matches documents still in `NEW`.

## 18. Operations: Performance, Errors, Timeouts, and Security

### 18.1. Measuring Accurate Counts and Latency

Suggested metrics (must be instrumented or mapped from your monitoring system):

| Metric | What it reveals |
|---|---|
| `mongo_query_runs_total` | Number of query executions |
| `mongo_query_result_documents` | Documents returned per query |
| `mongo_query_projection_bytes` | Data volume read/exchanged per observation |
| `mongo_query_latency_seconds` | Query duration |
| `mongo_query_limit_rejected_total` | Requests exceeding limit policy |
| `mongo_query_timeout_total` | Query/driver timeouts |
| `mongo_inbound_source_messages_total` | `Message<List<T>>` emitted by source |
| `mongo_splitter_messages_total` | `Message<T>` emitted after splitter |
| `mongo_inbound_empty_polls_total` | Queries returning no results |
| `mongo_gateway_requests_total` | Request/reply workload |
| `mongo_index_scan_ratio` | Query scan efficiency metric |
| `mongo_inbox_oldest_age_seconds` | Age of oldest unprocessed event |
| `mongo_claim_conflicts_total` | Multi-worker claim contentions |

**Never confuse source message count with document count.** One source message can carry a 50-element `List`; message counts differ before and after the splitter.

### 18.2. Layering Timeouts Properly

- `Pollers.fixedDelay(5000)`: poll schedule, **not a query timeout**.
- `QueueChannel.receive(5000)` in tests: JUnit wait for a Message, **does not bound MongoDB query execution**.
- `@Gateway(replyTimeout=...)`: caller wait for a reply, **does not immediately cancel DB operations upon expiry**.
- MongoDB driver server-selection/socket timeouts and query `maxTime`: govern actual DB I/O.
- Downstream business timeouts: HTTP/Kafka/JMS/AMQP operations have their own deadlines.

When a MongoDB query error occurs, it may happen **before any Message is created**. A query returning no data is normally just an empty poll, not an `ErrorMessage`. Handler errors after the splitter follow the channel/poller error propagation path (synchronous or asynchronous).

### 18.3. Security

- **Never let clients supply raw MongoDB Queries/JSON or SpEL strings** for server evaluation.
- Inject mandatory tenant/owner filters into `Criteria` from an authenticated identity.
- Cap limits, offsets, concurrent queries, and time budgets.
- Projections return only permitted fields; **never treat projection as a substitute for RBAC**.
- Enforce collection/database allowlists, least-privilege roles, TLS, and secret management.
- Log query template IDs, counts, durations, logical collection names, and error classes; never dump sensitive payloads.
- For tracing/metrics, avoid high-cardinality labels like per-`eventId` or per-device-ID tags.
- Under concurrency, test retries/idempotency and missing/duplicate data across workers.
- Run `explain` and load tests on realistically sized test datasets rather than assuming an index is optimal.

### 18.4. Graceful Shutdown and Backpressure

If a polling source returns 50 documents and the splitter pushes messages onto an `ExecutorChannel`/`QueueChannel`, some messages may still be **in flight** when the endpoint stops. Stop producers, drain in-flight work with a deadline, keep valid state/leases, and recover cleanly after restart. In-memory queues are not durable; if events cannot be lost, use durable sources/queues and idempotent handlers.

## 19. Comprehensive Hands-On Lab

Exercise: design a **MongoDB → Spring Integration → Kafka/JMS/HTTP/DB** service with bounded queries while also building a per-request device history lookup API.

### Part A — Query and Projection

1. Seed the five documents from section 3.
2. Query `tenant-a` / `status=NEW` in `mongosh`.
3. Use `query.fields().include(...)` to fetch only `tenantId`, `deviceId`, `sequence`, `observedAt`, and default `_id`.
4. Compare results when using `exclude("rawPayload")` in a **separate query**.
5. Try including one field while excluding another non-ID field; explain why the projection is invalid.
6. Create `TelemetrySummary` and verify mapping. Discuss why you must never `save` a partial entity.

### Part B — Sort and Limit

1. Sort by `observedAt ASC` and observe the two documents with identical timestamps.
2. Add `_id ASC` and assert the order `evt-101`, `evt-102`, `evt-103`.
3. Switch to `DESC` to fetch newest first.
4. Query with `limit(2)` and assert the exact two documents and expected IDs.
5. Test input `limit=0` and `limit=10000`, verifying validation rejects them.
6. Create an index on `tenantId/status/observedAt/_id` and compare `explain`/latency.

### Part C — Spring Integration Inbound

1. Use `MongoDb.inboundChannelAdapter(mongoDatabaseFactory, Query)` with `limit(50)` and `Pollers.fixedDelay(5000)`.
2. Assert one `Message<List<TelemetrySummary>>` before the splitter and individual messages after the splitter.
3. Create a `QueueChannel` test sink, wait with a finite timeout, and assert IDs/headers.
4. Seed 200 `NEW` documents and explain why `maxMessagesPerPoll=1` does not mean one document.
5. Let the poller run across two cycles without updating state; confirm events can repeat.
6. Propose claim/lease, retries, idempotency, and batch policies to avoid re-reading the same data forever.

### Part D — Gateway and Pagination

1. Define `SearchTelemetryRequest` with `limit` 1..100.
2. Use `MongoReadQueries.recentByDevice(...)` inside the outbound gateway's `queryFunction`.
3. Create `@MessagingGateway` returning `List<TelemetrySummary>`.
4. Send two requests for different devices and assert results belong only to the authorized tenant.
5. Test offset pagination with skip/limit; insert a document between pages to observe drift risks.
6. Test keyset pagination on `(observedAt, _id)` and verify cursor behavior when timestamps collide.
7. Propose a response DTO omitting `rawPayload` and sensitive fields.

### Part E — Operations and Reliability

1. Stop the test MongoDB instance to observe how query errors differ from empty polls.
2. Verify that driver timeouts, reply timeouts, and queue receive timeouts are three distinct layers.
3. Run two workers both reading `NEW` to explain duplicates despite sort/limit.
4. Simulate a crash after claiming but before business commit; propose leases and recovery.
5. Add metrics for document count, source message count, latency, empty polls, limit rejections, and retries.
6. Propose graceful shutdown, bounded queues, and how to ensure the source is not ACKed before the target finishes.

**Self-assessment questions:**

- How do filter, projection, sort, and limit differ?
- Why does `maxMessagesPerPoll(1)` alone not cap document count?
- In an `include` projection, is `_id` returned by default?
- Can you include field A while excluding non-`_id` field B?
- When using an entity with `@Field("device_id")`, which property name does `Query` use?
- Why does reading a partial entity and saving it back risk losing fields?
- When timestamps tie, why add sorting by `_id`?
- Does `limit(0)` always mean returning zero documents?
- Why does `Query.limit(50)` not prevent polling from re-reading the same 50 records?
- Can `skip + limit` skip records when the dataset mutates?
- Which sort fields must a keyset cursor retain?
- Why is a query projecting only a few fields not necessarily a covered query?
- How does an outbound gateway differ from an inbound polling source?
- When should you use atomic claims instead of sort + limit?
- How do you test tenant scope, IDs, counts, order, and returned fields accurately?

## 20. References

- [Spring Data MongoDB Reference — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria`, `fields()`, `with(Sort)`, `limit`, `skip`, and projections.
- [Spring Data MongoDB Reference — Repository Query Methods / Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): offset/keyset scrolling, pagination, and sorting.
- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB inbound polling, outbound gateway, `query-expression`, collections, and transaction synchronization.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): `inboundChannelAdapter(MongoDatabaseFactory, Query)` and `outboundGateway(MongoOperations)` overloads.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): `expectSingleResult`, list payloads, and empty queries.
- [MongoDB Manual — Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/): inclusion/exclusion and the `_id` exception.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): indexes, query plans, and query performance.
- [MongoDB Manual — explain](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/): inspecting execution plans and query statistics.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): pollers, `maxMessagesPerPoll`, and lifecycle.

## Conclusion

**Query fields, sort, and limit** govern **which fields are returned**, **result ordering**, and **maximum document count** from MongoDB, respectively. Paired with `MongoDbMessageSource`, these options define the size and content of a `Message<List<T>>`; paired with `MongoDbOutboundGateway`, they bound each request/reply result. **`maxMessagesPerPoll` bounds Spring Message retrieval attempts, not `Query.limit`.**

In **SPRING_INTEGRATION_ADAPTERS**, a well-designed query requires **an authorized tenant filter, DTO-aligned field projection, deterministic sorting, a capped positive limit, `explain`-verified indexes, and explicit timeouts**. Alongside this, a durable polling pipeline still needs **claim/lease, retries, idempotency, error handling, and shutdown/recovery**; sort + limit never marks documents as processed or guarantees exactly-once execution on its own.
