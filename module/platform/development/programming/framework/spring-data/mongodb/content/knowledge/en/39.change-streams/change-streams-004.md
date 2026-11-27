# ChangeStreamOptions, Pipeline Filters, and Event Data Types

> **Chapter:** Change stream  
> **Module:** `SPRING_DATA_MONGODB`

An order application wants to update a dashboard when a new order is created, when its status transitions from `NEW` to `PAID`, or when an order is deleted. Instead of repeatedly asking MongoDB "what's new?" via polling, the application can open a **change stream** to receive change events from a supported collection, database, or deployment.

In Spring Data MongoDB, `ChangeStreamOptions` controls **which events are returned, whether the full document is looked up after an update, and where to resume reading from**. The result is typically `ChangeStreamEvent<T>`: a wrapper containing operation metadata, the resume token, timestamp, and payload converted to type `T`. A MongoDB event is not the business document itself; you must distinguish `fullDocument`, `documentKey`, and `updateDescription` to avoid mishandling `update` and `delete` operations.

This lesson belongs to the `SPRING_DATA_MONGODB` module, where we connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories, design queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics. The direct scope here is **`ChangeStreamOptions`, pipeline filters, and event data types**, along with checkpoint/recovery consumer examples and tests.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between a **MongoDB document** and a **change event envelope**.
2. Read the structure of `_id`/resume tokens, `operationType`, `ns`, `documentKey`, `fullDocument`, `updateDescription`, and `clusterTime`.
3. Build `ChangeStreamOptions` using `builder()`, `filter(Aggregation)` or `filter(Document...)`, `returnFullDocumentOnUpdate()`, and resume options.
4. Write `$match` pipelines on `operationType` and `fullDocument` without accidentally dropping bodyless events.
5. Explain why `_id` (the resume token) must never be removed or altered in the pipeline.
6. Use `ReactiveMongoTemplate`/fluent `changeStream(...).listen()` to obtain `Flux<ChangeStreamEvent<T>>`, and recognize the imperative listener container alternative.
7. Distinguish `getBody()`, `getBodyBeforeChange()`, `getRaw()`, and `getResumeToken()`, especially when updates/deletes lack a full document.
8. Understand `resumeAfter`, `startAfter`, and `resumeAt`, oplog limits, and the requirement to keep pipelines/options stable across resumes.
9. Design post-processing checkpoints, idempotency, backpressure, and invalidation/consumer failure handling.
10. Write integration tests against a replica set verifying filters, event types, tokens, and mappings without relying on fixed sleeps.

## 2. Prerequisites for Using Change Streams

MongoDB change streams only work on **supported replica sets or sharded clusters**; ordinary standalone MongoDB cannot fully support this mechanism. Applications need a compatible driver/Spring Data version, credentials with appropriate watch/read privileges, network reachability to the topology, and **a long-lived consumer to maintain the cursor**.

```text
MongoDB replica set / sharded cluster
             |
             | committed changes
             v
       change stream cursor
             |
             | event envelope + resume token
             v
   Spring Data ChangeStreamEvent<T>
             |
             +-- operationType / documentKey
             +-- body or raw updateDescription
             +-- resumeToken / clusterTime
             |
             v
    Consumer -> business processing
             |
             v
       Persist checkpoint
```

Change streams are not a standalone message broker. Account for **oplog history retention limits**, network errors, elections, slow consumers, duplicate delivery after resume, and events that invalidate streams. Never treat opening a cursor as an end-to-end "exactly once" guarantee.

### 2.1. Stream scope

| Scope | What is watched | Payload type to choose |
| --- | --- | --- |
| Collection | Changes in a single collection, e.g. `orders` | `OrderDocument` if all event bodies share the same schema |
| Database | Multiple collections in one database | `org.bson.Document` or an envelope dispatched by namespace |
| Deployment/cluster | Multiple databases/collections where API and privileges allow | Raw `Document` + routing by `ns`, never force all collections into one entity |

A database-scoped stream does not guarantee every document matches `OrderDocument`. When collections have different schemas, use `Document` for the raw body or build a router based on `getCollectionName()` and convert deliberately.

### 2.2. When should you use change streams?

- Syncing a read model or search index after MongoDB changes.
- Updating dashboards from new events when UX accepts eventual consistency.
- Triggering idempotent downstream processing keyed by `operationId`/resume token.
- Recording data changes for auditing/monitoring when privileges, payloads, and retention are properly designed.

Do not use change streams to replace a transaction when two operations must **commit atomically**. Do not rely on them as the sole source of truth before proper deployment/resume is in place; if business rules strictly forbid losing events beyond oplog retention, use a more durable architecture such as a transactional outbox or replay/snapshot strategy.

## 3. Sample Data: Stateful Orders

File `OrderDocument.java`:

```java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String status,
    long totalMinor,
    Instant updatedAt
) {}
```

A BSON document:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  status: "NEW",
  totalMinor: NumberLong(50000),
  updatedAt: ISODate("2026-11-20T02:00:00Z")
}
```

In these examples, IDs use the `ORD-` prefix for clarity. `tenantId` only illustrates filtering; authorization must come from authentication/application policies, never from a self-reported client tenant string.

## 4. A Change Event Is Not an OrderDocument

Illustrative BSON/JSON insert event:

```javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "insert",
  clusterTime: Timestamp( /* server timestamp */ ),
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "ORD-101" },
  fullDocument: {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    status: "NEW",
    totalMinor: NumberLong(50000)
  }
}
```

This is an **illustrative structure**, not a verbatim `mongosh` command; exact fields and formatting vary by MongoDB version, operation, sharding, and stream options.

### 4.1. Key fields

| Change event field | Meaning | Notes |
| --- | --- | --- |
| `_id` | Opaque **resume token** identifying stream position | Not the order's `_id`; never alter or strip |
| `operationType` | `insert`, `update`, `replace`, `delete`, `invalidate`, and others | Must handle by type; events do not always carry a body |
| `ns.db` / `ns.coll` | Source namespace of the operation | Used to route wider-scope watches |
| `documentKey` | Key identifying the affected document, typically containing `_id` | Essential for deletes since no default `fullDocument` exists |
| `fullDocument` | Complete document when available | May be **absent/null**, especially on updates/deletes |
| `updateDescription` | Update delta: updated fields, removed fields, truncated arrays, ... | Meaningful only for corresponding updates |
| `clusterTime` | Logical BSON timestamp of the event | Not the user's device wall-clock time |
| `wallTime` | Wall-clock time if provided by server/version | Do not use instead of a resume token |
| `fullDocumentBeforeChange` | Pre-image when enabled/configured and still retained | Not present by default |

### 4.2. Two kinds of `_id`

```text
event._id                    -> change stream RESUME TOKEN
event.documentKey._id        -> ID of the modified document
event.fullDocument._id       -> ID inside the document when fullDocument is present
```

Confusing these two values is a common mistake. Never take `event._id` and pass it to `repository.findById(...)` to look up an order; the token is not a business key. Conversely, never treat `documentKey._id` as a resume token: it does not identify stream position and cannot be passed to `resumeAfter(...)`.

### 4.3. Common event types

| Operation | Default `fullDocument` | `documentKey` | `updateDescription` |
| --- | --- | --- | --- |
| `insert` | Usually carries the inserted document | Yes | No |
| `replace` | Usually carries the replacement document | Yes | Not an update-delta style |
| `update` | By default usually **absent**; update lookup can be enabled | Yes | Carries delta |
| `delete` | No post-delete full document | Yes | No |
| `invalidate` | No business document | Not a regular document key | No |
| DDL/expanded events | Depends on event type/option/version | Depends | Depends |

Never write a handler that assumes `event.getBody()` is non-null for **every** event. That will drop events or throw `NullPointerException` on deletes or updates without lookup.

## 5. Update Events: Inspect the Delta Before Looking Up the Full Document

Example update:

```javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { status: "PAID" } }
)
```

The update envelope typically contains:

```javascript
{
  _id: { _data: "<another-opaque-token>" },
  operationType: "update",
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "ORD-101" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: [],
    truncatedArrays: []
  }
  // fullDocument may be absent unless updateLookup is enabled.
}
```

If a consumer only needs to signal "`status` was set to `PAID`", `updateDescription.updatedFields.status` may suffice without querying the full document. However, for pipeline updates or `replace`, MongoDB can emit different representations; if you must catch **every** status change, consider `replace`/`insert` and explicit business rules.

### 5.1. Do not assume every update includes `status`

Another update:

```javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { updatedAt: new Date() } }
)
```

Here `updateDescription.updatedFields` will not include `status`. Filtering by `operationType="update"` and always reading `updatedFields.status` while treating null as "order canceled" is a domain logic bug.

### 5.2. `updatedFields` is not a snapshot

`updateDescription.updatedFields` reflects only the fields changed by **one update command**, not the entire document. It does not include unchanged fields like `tenantId` when the command only set `status`. Hence a filter on `fullDocument.tenantId` and a filter on `updateDescription.updatedFields.status` carry different semantics; never interchange them carelessly.

## 6. `ChangeStreamOptions`: A Stream Configuration Object

In Spring Data MongoDB, `org.springframework.data.mongodb.core.ChangeStreamOptions` collects options passed to the MongoDB driver when creating a cursor. Use `ChangeStreamOptions.builder()`:

```java
import org.springframework.data.mongodb.core.ChangeStreamOptions;

ChangeStreamOptions options =
    ChangeStreamOptions.builder()
        .returnFullDocumentOnUpdate()
        .build();
```

Or if you want default behavior:

```java
ChangeStreamOptions options = ChangeStreamOptions.empty();
```

The builder configures **how the stream behaves**, not consumer state storage. On every restart, the application must still load its durable checkpoint and pick the right offset or resume token.

### 6.1. Options to know

| Builder method | Meaning | Notes |
| --- | --- | --- |
| `filter(Aggregation)` | Applies an aggregation pipeline after the change-stream stage | Spring Data field mapping follows specific rules |
| `filter(Document...)` | Sends raw BSON pipeline stages | Easy to target envelope fields without domain-mapping interference |
| `returnFullDocumentOnUpdate()` | Requests `FullDocument.UPDATE_LOOKUP` on updates | Reads current document; not guaranteed to be an event-time snapshot |
| `fullDocumentLookup(FullDocument)` | Selects the driver's full-document policy | Semantics depend on enum and MongoDB version |
| `fullDocumentBeforeChangeLookup(FullDocumentBeforeChange)` | Selects the pre-image policy | Requires server-side pre-image configuration |
| `returnFullDocumentBeforeChange()` | Requests pre-images when available | Does not make the DB retain history automatically |
| `resumeAfter(BsonValue)` / `resumeToken(BsonValue)` | Resumes after a valid token | Used after stream interruptions, not after invalidate |
| `startAfter(BsonValue)` | Starts a stream after a token, including invalidate where supported | Does not blindly replace `resumeAfter` in all cases |
| `resumeAt(Instant)` / `resumeAt(BsonTimestamp)` | Starts from a timestamp/cluster time | Bounded by oplog; `BsonTimestamp` is more exact than `Instant` |
| `collation(Collation)` | Collation rules for supported pipelines | Does not alter token metadata or event handling |
| `showExpandedEvents(boolean)` | Requests expanded event types when server supports | Version-dependent; check your Spring Data/driver release |

Do not mix `resumeAfter`, `startAfter`, and `resumeAt` inconsistently: at the MongoDB change stream level, these offset modes are **mutually exclusive**.

### 6.2. Minimal configuration for order statuses

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(
        new Document("$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert", "update", "replace"))))
    )
    .returnFullDocumentOnUpdate()
    .build();
```

`filter(Document...)` takes a `$match` stage here. It filters `delete`, `drop`, `rename`, or `invalidate` out of the **pipeline output** when excluded; however, stream-invalidating operations can still close or error the cursor per MongoDB semantics. Never expect a filter pipeline to "prevent a collection from being dropped".

### 6.3. Requesting `fullDocument` adds extra read work

`returnFullDocumentOnUpdate()` uses `FullDocument.UPDATE_LOOKUP` so the server looks up the matching document in the collection. This is handy when consumers want the complete entity, yet it incurs extra cost and is not an immutable snapshot at update time.

If a use case only needs `documentKey` and the `updateDescription` delta, **leave update lookup disabled**. If enabled, measure:

- Update event frequency.
- Document size and network overhead.
- Volume of full-document lookups.
- Cases where the entity is deleted or modified again before lookup finishes.
- Impact on consumer latency and memory/backpressure.

Never assume "an update event happened" implies "`getBody()` is always non-null" even with update lookup enabled.

## 7. Pipeline Filtering: Matching by `operationType`

Change streams accept a pipeline **after the `$changeStream` stage** generated by MongoDB/the driver. Allowed stages are restricted; the common safe choice is `$match` followed (if genuinely needed) by a projection that preserves the resume token.

Raw MongoDB example:

```javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace"]
      }
    }
  }
], {
  fullDocument: "updateLookup"
})
```

Corresponding Spring Data `ChangeStreamOptions` using raw `Document`:

```java
Document matchTypes = new Document("$match",
    new Document("operationType",
        new Document("$in",
            List.of("insert", "update", "replace"))));

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(matchTypes)
    .returnFullDocumentOnUpdate()
    .build();
```

**Effect:** only the listed operation types reach the consumer through this pipeline. Never add `delete` to the list and then route to a single handler expecting `body != null`.

### 7.1. Receiving inserts only

```java
ChangeStreamOptions insertOnly = ChangeStreamOptions.builder()
    .filter(new Document("$match",
        new Document("operationType", "insert")))
    .build();
```

Here update lookup is unnecessary. For inserts, `fullDocument` is normally included. Even so, oversized events, incompatible mappings, or bad projections can still fail; test against real schema data.

### 7.2. Receiving only updates that change `status`

A delta-based filter:

```javascript
db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": {
        $exists: true
      }
    }
  }
])
```

Spring Data raw:

```java
Document matchStatusChange = new Document(
    "$match",
    new Document("operationType", "update")
        .append("updateDescription.updatedFields.status",
            new Document("$exists", true)));

ChangeStreamOptions statusChanges = ChangeStreamOptions.builder()
    .filter(matchStatusChange)
    .build();
```

**Meaning:** matches update events where `status` appears inside `updatedFields`. It does not cover `replace` operations, document-restructuring updates, or alternative server representations of changes. If you need "every case where order status changes", define a clear contract across write types and test thoroughly.

### 7.3. Path-shaped `updateDescription` entries

For nested paths like `shipping.status`, MongoDB may emit:

```javascript
updateDescription: {
  updatedFields: {
    "shipping.status": "DELIVERED"
  }
}
```

This is a key **containing a literal dot** in the `updatedFields` BSON document, rather than a nested `shipping: { status: ... }` subdocument by default. When parsing raw BSON, respect key/path semantics. Cases where field names contain literal dots or numeric keys may require `disambiguatedPaths` (when supported by server version and options).

Do not write parsers assuming every dot in a key always means a Java nested property; you may need to distinguish real fields, array indexes, and keys with special characters.

## 8. `filter(Aggregation)`: When to Use Instead of Raw `Document`?

`ChangeStreamOptions.ChangeStreamOptionsBuilder.filter(Aggregation)` accepts a Spring Data pipeline and leverages `Aggregation`/`Criteria`. Example:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("operationType")
            .in("insert", "update", "replace")));

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(pipeline)
    .returnFullDocumentOnUpdate()
    .build();
```

`operationType` is a **reserved event field** kept at the envelope level by Spring Data; it does not get prefixed with `fullDocument.`. Other properties may be treated by the mapper as domain entity fields and **automatically prefixed with `fullDocument.`**.

### 8.1. Crucial difference between event fields and domain fields

For the `filter(Aggregation)` overload, Spring Data documentation specifies:

- `operationType`, `ns`, `documentKey`, and `fullDocument` are reserved event field names resolved at the event envelope level.
- Other expression fields may be mapped/prefixed to `fullDocument.<field>`.
- `TypedAggregation` maps Java property names to BSON field names renamed with `@Field`.

Therefore:

```text
Event predicate:
  operationType == "update"

Domain field predicate:
  status == "PAID"     (may be mapped to fullDocument.status)

Raw BSON predicate:
  "updateDescription.updatedFields.status" exists
```

When filtering directly on `updateDescription` or less common metadata, a raw `Document` pipeline is often **easier to verify** because it keeps the exact field path written. Never blindly write `Aggregation.match(Criteria.where("updateDescription..."))` where mapping context might turn it into `fullDocument.updateDescription...`.

### 8.2. A rule of thumb to avoid confusion

| Want to filter on | Consider |
| --- | --- |
| `operationType` | `Aggregation.match(Criteria.where("operationType")...)` or raw `Document` |
| Entity field inside `fullDocument` | Typed aggregation or raw `Document("fullDocument.<field>", ...)` |
| `documentKey._id` | Raw envelope path or aggregation with verified mapping |
| `updateDescription.updatedFields` | Raw `Document` for BSON metadata structure |
| `ns.coll` / `ns.db` in broad streams | Raw envelope path |
| Multi-schema conditional event routing | Raw `Document` + `getRaw()/getCollectionName()` |

### 8.3. Example filter by tenant and event type

```java
Document match = new Document("$match",
    new Document("operationType",
        new Document("$in",
            List.of("insert", "update", "replace")))
        .append("fullDocument.tenantId", "TENANT-A"));

ChangeStreamOptions tenantStream = ChangeStreamOptions.builder()
    .filter(match)
    .returnFullDocumentOnUpdate()
    .build();
```

This is an **example filter for events carrying `fullDocument`**. On deletes, `fullDocument` is absent, so this filter drops deletes. On updates, `UPDATE_LOOKUP` may return a **document version later than the event**, or fail to find a deleted document; therefore filtering by `fullDocument.tenantId` does not reliably classify an update by "tenant at the exact update instant".

**If strict multi-tenant auditing/security is needed across all operations,** prefer tenant-separated collections or outbox/event envelopes carrying a durable tenant identity. Never rely on change-stream filters as a substitute for authorization in other APIs.

### 8.4. Do not treat filters as casual authorization

A user calling an API saying "watch tenant B" does not mean they are allowed to watch tenant B. Backend consumers usually hold a MongoDB account with broad privileges to read change streams. Thus:

1. The backend must authenticate and authorize the tenant itself.
2. Never expose raw change events directly to arbitrary clients.
3. Never let clients pass unvalidated HTTP inputs into `filter(Document...)`.
4. When fanning out results to user groups, authorize in the service layer and classify sensitive data.

Change streams are purely a database technical stream—they do not enforce tenant isolation by themselves.

## 9. Pipeline Projections: Do Not Break the Resume Token

MongoDB change events use `_id` as the resume token. Starting with MongoDB 4.2, change stream pipelines that attempt to alter the change event's `_id` are rejected. This includes pipelines that strip or overwrite the token via `$project`/`$unset`/`$replaceRoot`.

### 9.1. Anti-pattern: dropping `_id` to shrink payloads

```javascript
// ANTI-PATTERN — DO NOT use with change streams.
db.orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      fullDocument: 1
    }
  }
])
```

A regular aggregation query might drop `_id`, yet change streams **require the resume token to recover cursors**. Do not carry the familiar "`$project: { _id: 0 }`" habit from report aggregations into stream pipelines.

### 9.2. Projection example preserving the token

```javascript
db.orders.watch([
  {
    $match: {
      operationType: { $in: ["insert", "update", "replace"] }
    }
  },
  {
    $project: {
      _id: 1,
      operationType: 1,
      ns: 1,
      documentKey: 1,
      fullDocument: 1,
      updateDescription: 1,
      clusterTime: 1
    }
  }
])
```

This is an example of **deliberate field selection**, not a mandate that "every stream must `$project`". If `$project` drops a field the app needs (like `ns` for routing or `fullDocument` for conversion), handlers will see missing data. Start with `$match` and add projections only after measuring payload overhead.

### 9.3. Every pipeline change needs a resume regression test

MongoDB recommends **keeping the exact same pipeline and options when resuming from a token**. Changing filters or projections between saving a token and restarting can produce unexpected behavior or cause resume failures. Version stream configuration alongside checkpoints; when deploying a new pipeline, prepare a cutover or read-model rebuild plan per business requirements.

### 9.4. Filters can exclude required events

For example, filtering solely for `operationType: "insert"`:

- Suits building a read model that **only cares about creations**.
- Is **unsuitable** for keeping a read model synced with all mutations, because updates and deletes are dropped.
- Must not exclude deletes if the read model is subsequently treated as an accurate current snapshot.

A consumer tracking an **entity's full lifecycle** should subscribe to the corresponding operation types, including `replace` and `delete` whenever the product performs them.

## 10. `ChangeStreamEvent<T>`: Spring Data's Return Type

Typical reactive API usage:

```java
Flux<ChangeStreamEvent<OrderDocument>> events =
    reactiveTemplate.changeStream(OrderDocument.class)
        .watchCollection("orders")
        .listen();
```

`ReactiveMongoTemplate` yields `Flux<ChangeStreamEvent<OrderDocument>>`; `OrderDocument` is the target type used by the converter for `fullDocument` when present. The **event envelope still carries separate metadata**.

### 10.1. Getters to use

| Spring Data `ChangeStreamEvent<T>` | Data type | Related MongoDB field |
| --- | --- | --- |
| `getBody()` | `T` or null | Converted `fullDocument` |
| `getBodyBeforeChange()` | `T` or null | `fullDocumentBeforeChange` when pre-image is present |
| `getRaw()` | `ChangeStreamDocument<Document>` or null | Raw driver event |
| `getResumeToken()` | `BsonValue` or null | Event `_id` (opaque token) |
| `getOperationType()` | `OperationType` or null | `operationType` |
| `getCollectionName()` | `String` or null | `ns.coll` |
| `getDatabaseName()` | `String` or null | `ns.db` |
| `getTimestamp()` | `Instant` or null | `clusterTime` converted to `Instant` |
| `getBsonTimestamp()` | `BsonTimestamp` or null | `clusterTime` preserving increment precision |

The API's nullable annotations indicate you **must not assume every getter is non-null**. In particular, delete events usually lack `getBody()`.

### 10.2. Reading typed body and raw envelope

```java
package com.example.orders;

import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.changestream.UpdateDescription;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public final class OrderChangeDebugFormatter {

    private OrderChangeDebugFormatter() {}

    public static String describe(
            ChangeStreamEvent<OrderDocument> event) {

        OperationType type = event.getOperationType();
        BsonValue token = event.getResumeToken();
        OrderDocument body = event.getBody();
        ChangeStreamDocument<Document> raw = event.getRaw();

        String docId = "<not-available>";
        String changedFields = "<not-an-update>";

        if (raw != null) {
            BsonDocument key = raw.getDocumentKey();
            if (key != null && key.containsKey("_id")) {
                docId = key.get("_id").toString();
            }

            UpdateDescription delta =
                raw.getUpdateDescription();
            if (delta != null
                    && delta.getUpdatedFields() != null) {
                changedFields =
                    delta.getUpdatedFields().toString();
            }
        }

        return "operation=" + type
            + ", documentId=" + docId
            + ", hasFullDocument=" + (body != null)
            + ", hasResumeToken=" + (token != null)
            + ", changedFields=" + changedFields;
    }
}
```

This is demo code **for learning event classification**; never log raw `token`/BSON payloads in production if they contain sensitive data. `getUpdatedFields()` and other metadata may be empty or null depending on operation and driver version. Real applications should guard against nulls, summarize field names, and redact before logging.

### 10.3. Do not turn `getBody()` into a condition that drops events

Anti-pattern:

```java
// WRONG when consumers still must handle deletes/updates lacking fullDocument.
return events
    .map(ChangeStreamEvent::getBody)
    .filter(order -> order != null);
```

In Reactor, `map` forbids returning null: if `getBody()` is null, it triggers a reactive error rather than simply passing through to `filter`. Even more importantly, **a delete event has a null body yet remains a meaningful change**.

The right pattern checks `operationType` first, then extracts keys, documents, or deltas per type:

```java
return events.concatMap(event -> {
    OperationType type = event.getOperationType();
    if (type == OperationType.DELETE) {
        return handleDeleteByDocumentKey(event);
    }
    if (event.getBody() != null) {
        return handleCurrentDocument(event.getBody());
    }
    return handleWithoutFullDocument(event);
});
```

This is pseudocode inside a service defining `handleDeleteByDocumentKey`, `handleCurrentDocument`, and `handleWithoutFullDocument` returning `Mono<Void>`. `concatMap` preserves processing order. In production, distinguish `insert`/`replace`/`update` and never assume every body is an update-time snapshot.

## 11. `ReactiveMongoTemplate`: A Complete Stream-Listening Example

File `OrderChangeStreamSource.java`:

```java
package com.example.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class OrderChangeStreamSource {

    private final ReactiveMongoTemplate template;

    public OrderChangeStreamSource(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<OrderDocument>>
            watchOrderMutations() {

        Document match = new Document("$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert",
                            "update",
                            "replace",
                            "delete"))));

        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .filter(match)
            .returnFullDocumentOnUpdate()
            .build();

        return template.changeStream(
            "orders", options, OrderDocument.class);
    }
}
```

The overload `changeStream(String collectionName, ChangeStreamOptions options, Class<T> targetType)` takes the options object directly. With the fluent API, `withOptions(...)` takes a `Consumer<ChangeStreamOptionsBuilder>`, **not** a `ChangeStreamOptions` object; you can configure it fluently via `.withOptions(builder -> builder.returnFullDocumentOnUpdate())`. This example intentionally uses the options-accepting overload to avoid confusing the two signatures.

### 11.1. Do not create a stream and forget to subscribe

```java
Flux<ChangeStreamEvent<OrderDocument>> flux =
    source.watchOrderMutations();

// Creating the Publisher alone does not listen to events yet.
```

With reactive APIs, **subscription** starts the stream lifecycle; cancellation/disposal closes underlying resources. Never treat a `Flux` like a self-draining queue without a subscriber.

### 11.2. Do not place `subscribe()` casually in every request

Anti-design:

```java
@GetMapping("/start-watching")
public Mono<String> startWatching() {
    source.watchOrderMutations().subscribe(
        event -> handle(event));
    return Mono.just("started");
}
```

Every HTTP request spawns **another cursor, another consumer, and duplicate events**. There is no proper lifecycle, cancellation, or backpressure. For app-wide listeners, create a component managing start/stop, cross-replica ownership, and checkpoints; if exposing per-user SSE/WebSockets, design dedicated authorization, fan-out, and resource limits.

### 11.3. Processing must happen before checkpointing

```text
Receive event E with resume token R
          |
          v
Validate / deduplicate / process E
          |
          v
Confirm durable side effects
          |
          v
Persist checkpoint R
```

If you write the token **before** processing E and the process crashes, upon resuming from R the app skips E and can lose a side effect. If processing E finishes and it crashes **before** writing the token, E may be redelivered: therefore consumers must be **idempotent**.

Never put an unconditional `checkpointStore.save(event.getResumeToken())` inside `doOnNext` ahead of downstream processing. `doOnNext` does not wait for an asynchronous Publisher; compose and await terminal success.

## 12. Imperative: `MessageListenerContainer`

Applications not using Reactor can still consume change streams through Spring Data's messaging abstraction. Because watching a cursor with the sync MongoDB Java driver is a **long-running blocking** task, Spring Data provides `DefaultMessageListenerContainer` to manage subscription tasks.

Condensed example:

```java
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequestOptions;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.Subscription;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);
container.start();

MessageListener<ChangeStreamDocument<Document>, OrderDocument>
    listener = message -> {
        OrderDocument body = message.getBody();
        // Inspect metadata/raw using the Message API as needed.
        // Body can be null on delete events.
    };

ChangeStreamRequestOptions requestOptions =
    new ChangeStreamRequestOptions(
        "shop", "orders", ChangeStreamOptions.empty());

Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, requestOptions),
    OrderDocument.class);

// When the application stops: cancel/stop per lifecycle.
container.stop();
```

This snippet illustrates the **core classes**, not an application that starts and immediately stops in sequence; in production, `container.stop()` belongs in shutdown lifecycle rather than right after `register`. Spring Data documentation notes that `DefaultMessageListenerContainer` integrates with `SmartLifecycle` when registered as a bean.

When a listener hits errors, do not rely on default logging as data-loss protection. Configure an `ErrorHandler`, checkpoint/recovery, clean shutdown, and clear monitoring. Across multiple consumer instances, each instance can receive events independently; change streams do not form a competing-consumers group like a message broker.

### 12.1. Choosing reactive or imperative?

| Criterion | Reactive `Flux` | Imperative `MessageListenerContainer` |
| --- | --- | --- |
| Thread used to await events | Does not require a dedicated blocking thread per stream like sync | Sync-cursor watch task uses blocking execution |
| Metadata | `ChangeStreamEvent<T>` | `Message<ChangeStreamDocument<Document>, T>` |
| Error propagation | `onError` and Reactor operators | `ErrorHandler`/container lifecycle |
| Backpressure/processing | Reactor flow operators, still bound downstream work | Configure appropriate queues/executors/flow control |
| Resource cleanup | Dispose/cancel subscription | Stop/cancel `Subscription`/container |
| Token durability | **Must design yourself** | **Must design yourself** |

Never assume "reactive" means "never loses events", or "imperative" means "always blocks HTTP request threads". Both styles require cursor management, error handling, and checkpoints.

## 13. Resume Tokens: The Most Important Data for Recovering a Stream

Each change event carries a resume token in event `_id`. Spring Data exposes it via:

```java
import org.bson.BsonValue;

BsonValue token = event.getResumeToken();
```

`event` is a `ChangeStreamEvent<OrderDocument>` inside the consumer. The token is an **opaque BSON value**, not an integer timestamp or `OrderDocument.id`. In common releases, tokens are usually `BsonDocument` values with internal binary/hex data; never peel out `_data` to "increment by one" or fabricate tokens from document IDs.

### 13.1. Resuming after a processed event

```java
import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

BsonValue lastProcessedToken = checkpointStore.load();

ChangeStreamOptions options =
    ChangeStreamOptions.builder()
        .resumeAfter(lastProcessedToken)
        .returnFullDocumentOnUpdate()
        .build();
```

This example assumes `checkpointStore.load()` returned a **non-null** token from a properly structured checkpoint store. Real code needs two branches:

- Valid checkpoint exists → build options with `resumeAfter(token)`.
- No event ever processed → choose a startup strategy (current time, server timestamp, or snapshot + stream cutover), **never pass null** to the builder.

Never automatically "fallback start now" when resume fails due to an expired token: doing so silently drops changes during downtime. Raise an error, check oplog retention, and run an approved resnapshot/reconciliation workflow.

### 13.2. Storing BSON tokens without losing data types

Snippet illustrating `BsonDocument` token conversion via Extended JSON:

```java
import org.bson.BsonDocument;
import org.bson.BsonValue;

public final class ResumeTokenCodec {

    private ResumeTokenCodec() {}

    public static String serialize(BsonValue token) {
        if (!(token instanceof BsonDocument doc)) {
            throw new IllegalArgumentException(
                "Expected BsonDocument resume token");
        }
        return doc.toJson();
    }

    public static BsonDocument deserialize(String json) {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException(
                "Checkpoint JSON is blank");
        }
        return BsonDocument.parse(json);
    }
}
```

In a real project, store alongside **stream identity**, collection scope, pipeline version, and processing metadata; prefer native BSON if your store supports it. Avoid logging full tokens in production unless needed, and never encode them as arbitrary `String`s that lose type/format.

**Important:** the stored token must come from a **durably processed event**, not an event merely received and not yet processed.

### 13.3. Checkpointing and event processing

A processing model:

```text
Event E(token=R) received
      |
      v
Has E been processed already?
  +-- yes --> verify state, update/keep checkpoint if safe
  |
  +-- no
       |
       v
  Apply idempotent business effect
       |
       v
  Confirm effect durable
       |
       v
  Persist R as processed checkpoint
```

If both the effect and checkpoint reside in the **same MongoDB database** and transactions are supported, you can write both inside a short transaction to shrink the failure window. Still, prevent a consumer from triggering continuous changes on the **watched collection**, causing feedback loops; put checkpoint/read-model collections separately and configure filters/routing properly.

For effects in external systems (HTTP, Kafka, email), a MongoDB transaction alone cannot guarantee exactly-once across all systems. Use idempotency keys, outbox/inbox tables, or reconciliation.

### 13.4. Why is idempotency needed despite resume tokens?

```text
t0  Receive event E
t1  Write target read model successfully
t2  Process crashes before saving E's token
t3  Restart from previous token
t4  Receive E again
```

If you apply a non-idempotent update (e.g., `$inc: {points:10}` without event deduplication), you can add points twice. Because redelivery is possible, design targets so "one event ID/token applies its effect at most once", or deterministically rebuild state from the source of truth.

### 13.5. Oplog retention and expired tokens

Resume tokens enable replay only while the cluster retains sufficient matching history. When a consumer stops too long, MongoDB may evict the needed oplog segment; resuming will **fail**, with no infinite replay fallback.

Monitor:

- `resume token age` and consumer lag relative to latest changes.
- Actual oplog window across replica-set members/shards.
- Stream reconnect frequency, resume failures, and pending event backlog.
- Backfill/rebuild read-model plans when resuming is impossible.

Never put an infinite retry loop around expired-token errors; that only keeps the service failing while data drifts out of sync.

## 14. `resumeAfter`, `startAfter`, `resumeAt`: Three Different Starting Points

| Option | Starting position | Typical case |
| --- | --- | --- |
| `resumeAfter(token)` | After a known event/token | Normal consumer restart |
| `startAfter(token)` | After a token and allows opening a new stream after `invalidate` per MongoDB rules | Collection drop/rename/invalidation already handled |
| `resumeAt(Instant)` | At a chosen timestamp | Initializing/recovering from a server timestamp still in the oplog |
| `resumeAt(BsonTimestamp)` | At a more exact logical cluster timestamp | Exact offset recovery when a `BsonTimestamp` is available |

Never arbitrarily combine these three in one builder. MongoDB specifies `resumeAfter`, `startAfter`, and `startAtOperationTime` as **mutually exclusive** offset options.

### 14.1. Builder examples per case

```java
ChangeStreamOptions fromToken = ChangeStreamOptions.builder()
    .resumeAfter(previousToken)
    .build();

ChangeStreamOptions fromInvalidate = ChangeStreamOptions.builder()
    .startAfter(invalidateToken)
    .build();

ChangeStreamOptions fromTime = ChangeStreamOptions.builder()
    .resumeAt(serverTime)
    .build();
```

Here `previousToken`/`invalidateToken` are non-null `BsonValue`s; `serverTime` is a `BsonTimestamp` or `Instant` from a reliable source. Do not use `Instant.now()` from an application host for exact no-loss recovery: host clocks can drift and timestamps have different resolution than cluster time.

### 14.2. Invalidate is not a normal disconnect

Dropping or renaming a collection can emit **`invalidate`**, closing the corresponding change stream scope. After invalidation, `resumeAfter(token)` is **not** an allowed recovery method for continuing the old stream; `startAfter(token)` can open a new stream after invalidate per MongoDB rules.

From a business perspective, a dropped/renamed collection may no longer match expected schemas or scopes. Never call `startAfter` and carry on as if nothing happened: verify collection name, mapping, privileges, and whether downstream data needs rebuilding.

### 14.3. Changing the pipeline makes resuming unpredictable

If checkpoint R was produced by pipeline P1 filtering `status=PAID`, restarting with pipeline P2 filtering `tenantId=TENANT-B` can alter the meaning of skipped events and cause unpredictable behavior. MongoDB recommends using the **same pipeline and options** that created the token.

Store `streamName` and `pipelineVersion` beside the token so deployments can:

1. Detect a changed filter version.
2. Decide if migration or read-model rebuild is required.
3. Follow a deliberate version upgrade path rather than blindly resuming with an unverified old token.

### 14.4. Do not use tokens as business sequence numbers

An opaque resume token is not a field you can compare arithmetically or sort in Java. Never convert `_data` into a long, increment it, or treat it as a timestamp. If you need business ordering, define rules using `clusterTime`, stream order, and idempotency; never assume every event has a unique cluster time.

## 15. `getTimestamp`, `getBsonTimestamp`, and Resume Anchor Precision

`getTimestamp()` returns an `Instant` helpful for logging and observability, yet `Instant` does not carry the increment part of `BsonTimestamp`. In MongoDB, `BsonTimestamp` contains **seconds** and **increment** for logical operation ordering.

```java
import org.bson.BsonTimestamp;
import java.time.Instant;

Instant wallRepresentation = event.getTimestamp();
BsonTimestamp logicalOffset = event.getBsonTimestamp();
```

Both getters are shown for reading; both can return null per the API. **Prefer resume tokens** for event-level recovery. Use timestamps only when you have a trustworthy anchor and understand time-based start limits.

### 15.1. Two events can share the same `clusterTime`

Do not use `clusterTime` as a unique event key in transactions or sharded clusters. Events can share a logical timestamp under oplog/transaction semantics. For deduplication, an event-level resume token or durable business event ID is usually more suitable.

### 15.2. Do not rely solely on system clock to measure lag

`Instant.now() - event.getTimestamp()` is an approximation susceptible to clock skew, scheduler delays, and timestamp format differences. When monitoring, combine:

- Application-measured event processing latency.
- MongoDB cluster/oplog metrics.
- Checkpoint age.
- Downstream queue length and processing time.

Zero events for 10 seconds does not mean the stream hung: there may simply be no changes.

## 16. `fullDocument` and `fullDocumentBeforeChange`: Different Policies

When MongoDB emits an update event, by default it usually contains the **delta** in `updateDescription` without the full document. Spring Data lets you configure this policy via options.

### 16.1. `UPDATE_LOOKUP`: reading current state after an update

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build();
```

Or specifying the driver enum:

```java
import com.mongodb.client.model.changestream.FullDocument;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentLookup(FullDocument.UPDATE_LOOKUP)
    .build();
```

This option can populate `event.getBody()` on `update` events. However, MongoDB looks up the **latest majority-committed version of the document at lookup time**, not necessarily the snapshot **immediately after the operation that produced the event**.

Timeline:

```text
t0: Order.status = NEW
t1: update status = PAID         --> Event E1
t2: update status = SHIPPED      --> Event E2
t3: updateLookup for E1

Possible E1.fullDocument.status = SHIPPED
Even though E1.updateDescription.updatedFields.status = PAID.
```

This is not a Spring Data bug; it is the inherent nature of **lookup at stream-processing time**. If business logic must emit an exact signal that "a status change to PAID happened", rely on the delta or an appropriate event payload—never read `getBody().status()` and deduce operation sequence.

### 16.2. `WHEN_AVAILABLE` and `REQUIRED` for post-images

On MongoDB versions supporting **document pre/post images** (MongoDB 6.0+ for this feature), `FullDocument` policies such as `WHEN_AVAILABLE` and `REQUIRED` retrieve the **stored post-image** rather than performing a standard update lookup.

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentLookup(
        FullDocument.WHEN_AVAILABLE)
    .build();
```

This **requires the server and collection to be configured to store change stream pre/post images**; if not enabled or history expired, `WHEN_AVAILABLE` may yield no body while `REQUIRED` errors the stream when a required image is missing.

Do not set this enum assuming every deployment holds historical images. Check server version, FCV, collection configuration, retention, and privileges before choosing a policy.

### 16.3. Pre-images for state before update/delete

Example:

```java
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;

ChangeStreamOptions options = ChangeStreamOptions.builder()
    .fullDocumentBeforeChangeLookup(
        FullDocumentBeforeChange.WHEN_AVAILABLE)
    .build();
```

When a pre-image is available, `ChangeStreamEvent<T>.getBodyBeforeChange()` can provide the document version **before the change**. An application needing permission/tenant checks when a document is deleted may consider pre-images, keeping in mind:

- Pre/post images must be enabled on the collection ahead of time.
- Pre-images are not retroactively generated for changes made **before enabling**.
- Images are not guaranteed to be kept forever.
- `WHEN_AVAILABLE` permits missing images; handlers must still handle null.
- `REQUIRED` can fail the stream if the image is gone.

Example enabling the setting on a **test collection** in MongoDB 6.0+:

```javascript
// Run only with proper privileges and topology on a TEST cluster.
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
})
```

Do not run `collMod` casually on production while studying; evaluate storage overhead, retention, and operational rules first.

### 16.4. Pre-images do not replace durable audit records

If a product has multi-year legal auditing requirements, change stream pre/post images and oplog retention likely cannot satisfy that retention window. A dedicated audit log or outbox with its own schema and retention policy fits better. Change streams are for **observing changes**, not replacing multi-year immutable evidence stores.

### 16.5. Filtering on post-images can mislead

If a pipeline matches `"fullDocument.status": "PAID"` while `updateLookup` returns `SHIPPED` due to a later update, event `E1` can be filtered out. Never design an audit for "every transition to PAID" relying solely on `updateLookup` snapshots; filter `updateDescription.updatedFields.status` or use explicit domain events with clear semantics.

## 17. Event Data Types in Java: Typed, Raw, and Domain Events

There are three layers you should not conflate:

```text
Raw ChangeStreamDocument<Document>
  - operationType
  - documentKey
  - updateDescription
  - fullDocument (BSON)
             |
             v
Spring ChangeStreamEvent<OrderDocument>
  - typed getBody() when present
  - typed getBodyBeforeChange() when available
  - getRaw() preserves envelope
             |
             v
Application DomainEvent / DTO
  - stable business ID
  - tenant and authorization policy
  - fields needed by consumer
  - version / idempotency key
```

`ChangeStreamEvent<T>` is a **technical MongoDB event**. Never expose it straight to browsers or send it raw to external systems without a domain contract and security rules.

### 17.1. Avoid mapping a database-wide stream to a single entity

```java
// For streams watching multiple collections, Document is appropriate.
Flux<ChangeStreamEvent<Document>> allCollections =
    reactiveTemplate.changeStream(Document.class)
        .listen();
```

On receipt, inspect `getCollectionName()`/`getDatabaseName()` and `getRaw()` to classify. Using `OrderDocument.class` for `orders`, `customers`, and `inventory` causes the converter to mismap or drop fields, leading business logic to act on incomplete data.

### 17.2. Using `documentKey` for deletes

Simple example:

```java
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public static String deletedOrderId(
        ChangeStreamEvent<OrderDocument> event) {

    if (event.getOperationType() != OperationType.DELETE) {
        throw new IllegalArgumentException("Not a delete");
    }
    ChangeStreamDocument<Document> raw = event.getRaw();
    if (raw == null) {
        throw new IllegalStateException("Missing raw event");
    }
    BsonDocument key = raw.getDocumentKey();
    if (key == null || !key.containsKey("_id")) {
        throw new IllegalStateException("Missing documentKey._id");
    }
    return key.get("_id").asString().getValue();
}
```

This helper assumes the document ID is a **BSON String**; if the collection uses `ObjectId` or a composite shard key, `asString()` will fail. In production, use an appropriate mapper/codec and keep all fields in the document key to identify records safely.

### 17.3. `UpdateDescription` carries other change shapes

For update events, `UpdateDescription` contains more than `updatedFields`. It also includes:

- `removedFields`: fields removed by `$unset` or update semantics.
- `truncatedArrays`: descriptions of arrays shortened in applicable operations.
- `disambiguatedPaths`: helps disambiguate paths containing dots or numeric keys where server/expanded events support it.

Never rely solely on `updatedFields` claiming you know **all** changes in an event. Operations can truncate arrays, remove fields, or replace the entire document (`replace`).

### 17.4. Creating a small domain event

```java
package com.example.orders;

public record OrderStateChanged(
    String operationId,
    String orderId,
    String tenantId,
    String newStatus
) {}
```

To build this event from a change stream:

1. Have a stable `operationId` stored during the business write, or a non-colliding ID derived deterministically from the event token.
2. Obtain a trustworthy `tenantId`, rather than guessing from missing delta fields.
3. For `update`, read `updateDescription` or the post-image per your chosen semantics.
4. Do not emit the business event twice when the change stream resumes or retries.

Never set `operationId = orderId` for all status transitions: one order can emit many distinct events. Choose idempotency keys at the **event or business-operation level**, not always the entity level.

## 18. A Reactive Consumer with Ordered Processing and Checkpointing

The model below intentionally uses abstract interfaces for processing and checkpoint writing. Its goal is to illustrate **Publisher call order**, not a complete message broker system.

File `OrderStreamProcessor.java`:

```java
package com.example.orders;

import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class OrderStreamProcessor {

    public interface OrderEventHandler {
        Mono<Void> process(
            ChangeStreamEvent<OrderDocument> event);
    }

    public interface CheckpointWriter {
        Mono<Void> save(BsonValue token);
    }

    private final OrderEventHandler handler;
    private final CheckpointWriter checkpoints;

    public OrderStreamProcessor(
            OrderEventHandler handler,
            CheckpointWriter checkpoints) {
        this.handler = handler;
        this.checkpoints = checkpoints;
    }

    public Mono<Void> processEvent(
            ChangeStreamEvent<OrderDocument> event) {

        BsonValue token = event.getResumeToken();
        if (token == null) {
            return Mono.error(
                new IllegalStateException(
                    "Event has no resume token"));
        }

        // Process first, checkpoint afterward.
        // process(...) must be idempotent/durable per policy.
        return handler.process(event)
            .then(checkpoints.save(token));
    }

    public Flux<Void> consume(
            Flux<ChangeStreamEvent<OrderDocument>> source) {
        // concatMap = preserve processing order, avoid
        // concurrent competing checkpoint writes.
        return source.concatMap(this::processEvent);
    }
}
```

This is an **orchestration pattern** and does not solve every case alone:

- If `handler.process` writes externally and succeeds, then `checkpoints.save` fails, the event may replay. Handlers must be idempotent.
- If multiple instances run independently, each can receive the same events; use ownership/sharding/leader election or inbox deduplication.
- With a single checkpoint value, never save a **later** event's token before an **earlier** event finishes.
- If a pipeline uses a different filter, tag checkpoints with stream identity/version.
- When processing is slow, streams can lag; add backpressure/metrics and recovery mechanics.
- `Flux<Void>` emits no `onNext` items as each `Mono<Void>` completes; subscribers should observe completion/error/cancellation and lifecycle. For long-lived streams, normal completion occurs only when the stream closes.

In real applications, coordinate subscriptions via lifecycle components and store checkpoints durably. Never call `subscribe()` per HTTP request and discard the `Disposable` reference, or you lose control over stopping and observing the consumer.

### 18.1. Why not use `flatMap` by default?

```java
// ANTI-PATTERN if checkpoint is a single sequential offset.
source.flatMap(event ->
    handler.process(event)
        .then(checkpoints.save(event.getResumeToken())));
```

`flatMap` can execute multiple events concurrently and finish **out of order**. If E2 checkpoints before E1 finishes and the process crashes, resuming from E2 skips E1. With a sequential checkpoint, `concatMap` preserves order; if parallelism is required, design partitioning and checkpoint watermarks per partition/processing unit.

### 18.2. Both pre- and post-checkpoint pipelines need error policies

Do not write:

```java
// ANTI-PATTERN: hides business errors and still checkpoints.
handler.process(event)
    .onErrorResume(ex -> Mono.empty())
    .then(checkpoints.save(event.getResumeToken()));
```

A swallowed exception lets the checkpoint advance, marking an event processed even though its business effect failed. If an error is deliberately skippable (e.g., an event type genuinely out of scope), classify it explicitly, emit metrics, and confirm checkpointing matches the contract.

## 19. Change Streams and Transactions: Emitting Only After Committed Changes

Change streams notify of changes committed under MongoDB semantics. Writes inside an uncommitted multi-document transaction are **not treated as committed business events** for consumers. When a transaction aborts, its uncommitted writes do not become confirmed change events.

Yet do not mistake change streams for an exactly-once event bus:

- Multiple documents in one transaction can emit multiple change events.
- Those events may share a `clusterTime`; never use timestamps as dedupe keys.
- Stream listeners can restart/replay.
- Never rely on an event for record A as proof that **record B's consumer** finished without a separate protocol/saga.
- Updating a single document may emit a `replace` representation when the server chooses that form.

When you need a single business event like `OrderPaid` across simultaneous changes, a **transactional outbox** writing one `OrderPaid` record in the same transaction is a clear pattern. A change stream can watch the **outbox collection** to deliver events downstream while business state lives in other collections.

## 20. Integration Testing Change Streams on a MongoDB Replica Set

Unit tests that merely construct `ChangeStreamOptions` verify Java configuration, yet do not prove MongoDB Server **actually emits the right event types**, that `getBody()`/`getRaw()` match writes, or that resume tokens work. You need a **test replica set** or suitable sharded cluster test; standalone is not enough.

### 20.1. Test matrix

| Test | Data/operation | What to assert |
| --- | --- | --- |
| Insert event | `insertOne` with unique `_id` | `operationType=insert`, converted body, `documentKey`, and token |
| Update event | `$set(status=PAID)` | `updateDescription.updatedFields.status=PAID`, body present/absent per update lookup |
| Replace event | `replaceOne` | `operationType=replace` or valid server representation; handler accepts valid forms |
| Delete event | `deleteOne` | `operationType=delete`, `documentKey._id` present, body may be null |
| Filter event type | `$match(operationType=insert)` | Updates/deletes do not appear in the filtered stream |
| Filter `fullDocument` | `tenantId` per sample data | Only events with matching `fullDocument`; explains why deletes lack bodies |
| Resume | Save token R, create subsequent event | `resumeAfter(R)` receives events after R while oplog retains them |
| Token and projection | `$project` preserving `_id` | Resume remains valid; token unaltered |
| Cancellation | Dispose subscription | Cursor/resources close per lifecycle |
| Invalidation | Drop/rename on **isolated test cluster** | Confirm `resumeAfter` does not replace `startAfter` |
| Pre-image | Enable pre/post images on test collection | `getBodyBeforeChange()` is populated when image is available |

### 20.2. A unit test for `ChangeStreamOptions`

File `OrderChangeStreamOptionsTest.java`:

```java
package com.example.orders;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

import static org.assertj.core.api.Assertions.assertThat;

class OrderChangeStreamOptionsTest {

    @Test
    void filterAndUpdateLookupArePresent() {
        Document filterStage = new Document(
            "$match",
            new Document("operationType",
                new Document("$in",
                    List.of("insert", "update"))));

        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .filter(filterStage)
            .returnFullDocumentOnUpdate()
            .build();

        assertThat(options.getFilter()).isPresent();
        assertThat(options.getFullDocumentLookup()).isPresent();
    }

    @Test
    void emptyOptionsDoNotSpecifyResumeToken() {
        ChangeStreamOptions empty =
            ChangeStreamOptions.empty();

        assertThat(empty.getResumeToken()).isEmpty();
    }
}
```

This test verifies the **options object**, not server execution. To verify the filter serializes properly to `$match` or `fullDocument` comes back, run integration tests.

### 20.3. Testing event mapping independently of MongoDB

You can design an adapter mapping metadata to a testable record:

```java
package com.example.orders;

import com.mongodb.client.model.changestream.OperationType;
import org.springframework.data.mongodb.core.ChangeStreamEvent;

public record OrderChangeSummary(
    OperationType operation,
    String orderId,
    boolean hasBody,
    boolean hasToken
) {
    public static OrderChangeSummary from(
            ChangeStreamEvent<OrderDocument> event) {
        String id = null;
        var raw = event.getRaw();
        if (raw != null
                && raw.getDocumentKey() != null
                && raw.getDocumentKey().containsKey("_id")) {
            id = raw.getDocumentKey().get("_id").toString();
        }

        return new OrderChangeSummary(
            event.getOperationType(),
            id,
            event.getBody() != null,
            event.getResumeToken() != null);
    }
}
```

The adapter intentionally does not require `getBody()` to be non-null. You can unit-test with event fixtures without starting MongoDB, provided fixtures are built using your exact driver/converter version APIs. Never mock `getBody()` alone to claim `updateLookup` works: that is database/driver behavior.

## 21. Integration Testing with `StepVerifier`: Avoiding Subscribe–Write Races

Because a change stream is a **long-lived cursor**, `StepVerifier` cannot simply call `verifyComplete()` on a stream without `take(...)`. Meanwhile, calling `subscribe()` and immediately inserting can **hit a race** if the server has not initialized the cursor yet.

### 21.1. Proper test structure

```text
Setup MongoDB replica set TEST and collection "orders"
        |
        v
Establish controlled resume point R
        |
        v
Write a uniquely identified order E1
        |
        v
Build stream with resumeAfter(R)
        |
        v
StepVerifier.create(stream.filter(event -> matches E1).take(1))
        |
        v
Assert event type, raw documentKey, typed body, token
        |
        v
verifyComplete()
        |
        v
Cleanup only IDs created by test
```

Establishing resume point R **must use a genuine valid R** from an earlier observed event/driver cursor, not a fabricated token. Given the same pipeline/options and remaining oplog history, the test can write E1 before subscribing to the resumed stream, eliminating the "cursor not ready during write" race.

Without a token fixture, another option is creating a subscriber and awaiting a **server-side cursor readiness signal** from the test harness/driver instrumentation before writing. Never use `Thread.sleep(500)` as proof that a watcher is ready.

### 21.2. `StepVerifier` skeleton for an event with an existing resume token

File `OrderChangeStreamIntegrationTest.java` (method excerpt; `template` and `resumeToken` are set up by the test fixture):

```java
import java.time.Duration;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.BsonValue;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

void verifiesInsertAfterKnownCheckpoint(
        BsonValue resumeToken,
        String expectedOrderId) {

    ChangeStreamOptions options = ChangeStreamOptions.builder()
        .resumeAfter(resumeToken)
        .build();

    Flux<ChangeStreamEvent<OrderDocument>> flux =
        reactiveTemplate.changeStream(
            "orders", options, OrderDocument.class);

    Flux<ChangeStreamEvent<OrderDocument>> matching =
        flux.filter(event -> event.getBody() != null
            && expectedOrderId.equals(
                event.getBody().id()))
            .take(1);

    StepVerifier.create(matching)
        .assertNext(event -> {
            assertThat(event.getOperationType())
                .isEqualTo(OperationType.INSERT);
            assertThat(event.getResumeToken()).isNotNull();
            assertThat(event.getRaw()).isNotNull();
        })
        .expectComplete()
        .verify(Duration.ofSeconds(30));
}
```

This is a **test skeleton**, not a standalone runnable class: `reactiveTemplate`, `assertThat`, test replica set, and `resumeToken` must be wired up. Use unique IDs per test; client-side filtering in this example to isolate E1 **does not replace server-side pipeline filters**. When testing server-side filters, place `$match` in `ChangeStreamOptions` and assert no excluded event arrives within a bounded observation window.

### 21.3. Do not treat `expectNoEvent()` as absolute proof

`expectNoEvent(Duration.ofSeconds(1))` only proves **no event was emitted during a bounded interval** assuming the test started properly. It does not prove MongoDB will never emit an event; startup lag, network/scheduler delays, or uncommitted writes can yield false positives.

To verify an "inserts only" filter more reliably:

1. Establish a stable resume point R.
2. Write an update/delete and an insert with distinct test IDs.
3. Resume from R with the insert filter.
4. Assert you receive the **expected insert event**, and receive zero disallowed operation types before `take(1)` completes.
5. In a separate test, verify an unfiltered stream does see the corresponding update/delete.

### 21.4. Testing `updateLookup` and null bodies

For update events:

```text
ChangeStreamOptions.empty():
  update event
  raw.updateDescription populated
  getBody() may be null

ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build():
  update event
  getBody() may contain looked-up OrderDocument
  getBody() can still be null if lookup unavailable
```

Never write an integration test asserting `getBody().status() == "PAID"` after intentionally issuing a subsequent update to `SHIPPED` before lookup: `UPDATE_LOOKUP` is not an exact snapshot of E1.

### 21.5. Testing delete and pre-images

For deletes without pre-images enabled:

- `getOperationType()==OperationType.DELETE`.
- `getRaw().getDocumentKey()` normally contains the key identifying the document.
- `getBody()` is normally null.

When pre-images are properly enabled in a test:

- `getBodyBeforeChange()` can hold the document before deletion.
- Under `WHEN_AVAILABLE`, the test must confirm the server actually recorded the image; avoid rigid assertions if setup is incomplete.
- Under `REQUIRED`, include a test case verifying a missing image errors per contract.

Never drop shared collections to test `invalidate`. When testing drops/renames, use a **dedicated test-job database** and lifecycle-managed fixtures—never touch dev or prod environments.

### 21.6. Testing resume, replay, and idempotency

An end-to-end integration test:

1. Consumer A receives E1, processes it successfully, and writes token R1.
2. Stop A, emit E2 while A is offline.
3. Consumer B reopens from `resumeAfter(R1)` with the **same pipeline/options**.
4. Verify E2 is received with token R2.
5. Simulate a crash after processing E2 but before checkpointing R2.
6. Resume again from R1, verifying E2 **can be redelivered**, yet the idempotent side effect applies only once.

This is what meaningfully verifies consumer durability. A test that merely runs `take(1)` and prints a log does not prove double-apply protection.

## 22. Performance, Backpressure, and Stream Operations

A change stream can stay open long-term, receiving thousands of events per second at peak load. When handlers run slower than the source rate, the challenge shifts from "receiving events" to **coordination, buffering, throughput, and keeping up with the oplog**.

### 22.1. Metrics to monitor

| Metric | Goal |
| --- | --- |
| `change_stream_open_total` / active subscriptions | Track open cursors/subscribers |
| `change_stream_reconnect_total` | Observe network/election/client recovery |
| `change_stream_resume_failed_total` | Detect invalid tokens, expired oplog, option mismatches |
| `change_stream_events_received_total` by `operationType` | Ratio of insert/update/delete/replace |
| `change_stream_events_processed_total` | Compare against received to detect backlog |
| `change_stream_processing_latency_seconds` | Slowness in downstream handlers |
| `change_stream_checkpoint_age_seconds` | Lag by processed checkpoint |
| `change_stream_checkpoint_write_failed_total` | Risk of replay/unrecoverability |
| `change_stream_duplicate_events_total` | Re-seen already-processed events |
| `change_stream_full_document_missing_total` | Track missing update lookups/pre-images |
| `change_stream_dead_letter_total` | Failed events requiring manual triage |
| `change_stream_resume_token_expired_total` | Oplog history insufficient |

Alert against **downstream data SLAs**. Zero new events is not automatically an error; pair with subscription/cursor health, heartbeat/server metrics, and checkpoint age relative to real writes.

### 22.2. Do not log every raw event

`ChangeStreamEvent.getRaw()` can carry full documents containing PII, transaction details, warehouse locations, or sensitive fields. Avoid:

```java
// ANTI-PATTERN in production:
events.doOnNext(System.out::println);
```

Log minimally: stream name, operation type, authorized namespace, non-sensitive hashed/correlation ID, processing status, latency, and error category. Never place resume tokens or full document keys into high-cardinality metric labels.

### 22.3. Do not open cursors per client connection uncontrollably

If a WebSocket/SSE app broadcasts order changes to 1,000 clients, opening **1,000 change stream cursors** imposes unnecessary load on MongoDB. Usually run a small set of managed backend consumers feeding a fan-out/broker/cache layer with proper tenant authorization.

When deploying multiple application replicas:

- Each replica opening a stream can receive the **same event**.
- Change streams do not provide Kafka-style consumer-group partitioning.
- If each event must execute business logic once, use ownership/partitioning and deduplication.
- On leader handoff, checkpoints must be durable and protected by fencing/locking so two owners cannot write simultaneously.

### 22.4. Bounded concurrency

`concatMap` preserves order sequentially, serving as a safe starting point for a linear checkpoint. When higher throughput is required, you can partition by entity/tenant and process in parallel, provided you:

1. Define ordering guarantees within each partition.
2. Never checkpoint past an unprocessed event.
3. Bound backlog growth.
4. Ensure effects are idempotent and retryable.
5. Maintain a rebuild strategy if tokens expire.

Never switch to `flatMap(..., 128)` and simply store the highest completed resume token; that risks marking still-running earlier events as "done".

### 22.5. When should you use an outbox?

If you only need to rebuild caches/read models from one collection with eventual consistency, watching the collection directly may suffice with checkpoints/rebuilds. When you need to emit a **stable business event** across multiple collections, side effects, and heterogeneous consumers, an outbox decouples domain semantics from `updateDescription`/`fullDocument` details.

Example:

```text
Order transaction:
  update orders.status = PAID
  insert outbox {
    eventId: "ORDER-PAID-OP-123",
    type: "OrderPaid",
    orderId: "ORD-101",
    tenantId: "TENANT-A"
  }
      |
      v
MongoDB COMMIT
      |
      v
change stream on outbox
      |
      v
idempotent dispatcher/consumer
```

Change streams help detect **committed outbox records**. They still do not replace duplicate-handling policies, checkpoints, and broker acknowledgments.

## 23. Troubleshooting Common Errors

| Symptom | Possible cause | Check / fix |
| --- | --- | --- |
| Opening stream reports unsupported | Standalone MongoDB | Use a supported replica set/sharded cluster |
| Writes exist but `Flux` emits nothing | Not subscribed, wrong filter, watcher not ready | Check subscription, source scope, pipeline, setup |
| Update event has null body | Update lookup not enabled or lookup found nothing | Read `getRaw().getUpdateDescription()`; consider `returnFullDocumentOnUpdate()` |
| Delete event throws `NullPointerException` | Handler assumed `getBody()` non-null | Use `documentKey` or pre-image when configured |
| Filter on `status` does not match | Aggregation mapping prefixed `fullDocument.status` or body missing | Inspect BSON pipeline, use raw `Document` when needed |
| `updateDescription.updatedFields.status` missing | Different field updated, `replace` event, or changed shape | Classify `operationType` and deltas accurately |
| Event processed twice | Resume replay or multiple app replicas | Idempotency/ownership/processed-event key |
| Event lost after crash | Checkpoint written before processing | Write checkpoint **after** durable effect |
| Backlog grows continuously | Slow consumer, heavy full lookups, downstream errors | Measure processing latency, scale/partition with safe checkpoints |
| Token expired | Consumer offline longer than oplog window | Alert and resnapshot/reconcile |
| Cannot resume after invalidate | Passing invalidate token to `resumeAfter` | Use `startAfter` when appropriate and check schema/scope |
| Pipeline changed and resume fails | Checkpoint lacks version/options tracking | Version stream contract, plan cutover |
| `$project` breaks stream | Removed/altered event `_id` | Preserve resume token |
| Events from another tenant appear | Broad watch scope, missing filter/authorization | Narrow collection, filter and route per policy |
| Multi-collection events mapped to wrong type | One domain class used for all collections | Use `Document`/router keyed by `ns` |
| `PAID` status event shows `fullDocument` `SHIPPED` | `UPDATE_LOOKUP` read a newer document | Rely on deltas or structured domain events |
| Pre-image null despite lookup configured | Pre/post images disabled on collection or expired | Check `collMod`/retention/version; handle `WHEN_AVAILABLE` |
| Sync listener stuck | Unmanaged blocking cursor task/lifecycle | Use `MessageListenerContainer` and monitor tasks |
| App shuts down leaving cursors / duplicate watchers | Subscriptions not disposed/stopped properly | Controlled lifecycle shutdown |
| Transaction updates not seen immediately | Transaction uncommitted or stream lag | Check commit, cluster health, cursor lag |
| Insert-only pipeline leaves deleted records in read model | Filter excluded required operations | Include needed event types and rebuild read model |

### 23.1. No events appearing: investigation checklist

In order:

1. **Topology:** replica set or sharded cluster? Which members are healthy?
2. **Authentication:** does the stream account hold required privileges for the namespace/scope?
3. **Subscription:** is `subscribe`/listener container actually running?
4. **Start position:** did the stream open before or after the write? Is there a valid checkpoint or `resumeAt`?
5. **Pipeline:** do `operationType`, `fullDocument`, and `ns` filters exclude the events?
6. **Full document policy:** is body null because of delete or default update?
7. **Resume state:** is the token still in the oplog, with matching pipeline/options?
8. **Errors:** were `onError` or `ErrorHandler` ignored or under-logged?
9. **Downstream:** were events received yet failed in handlers or channels?

Never trigger a full collection scan every time a change stream errors. Separate **not receiving events** from **receiving but failing to process**, and maintain a rebuild procedure when history is lost.

### 23.2. Branching cleanly by event body

A consumer may need:

```java
switch (event.getOperationType()) {
    case INSERT, REPLACE -> {
        // getBody() usually present; confirm non-null.
    }
    case UPDATE -> {
        // updateDescription may suffice; body depends on policy.
    }
    case DELETE -> {
        // Document key, and pre-image if enabled.
    }
    default -> {
        // Drop, rename, invalidate, DDL... apply explicit policy.
    }
}
```

This is a **switch skeleton** inside a method holding `event`, not a complete production handler. If `getOperationType()` can be null, guard before switching. `OperationType` can expand across driver/server versions; include `default` so unfamiliar types do not corrupt data.

### 23.3. Do not retry every error identically

An outer `retryWhen(Retry.max(Long.MAX_VALUE))` will not fix:

- Missing privileges.
- Invalid pipelines.
- Tokens evicted from the oplog.
- Poison-pill events that always fail the handler.
- Invalidation and schema changes on collections.

Classify **recoverable** errors (network/elections, where the driver can auto-resume) vs. **non-recoverable** ones (bad pipeline, unauthorized, invalid token). Use retry budgets/backoff/jitter, fail-fast/alert states, and manual reconciliation when necessary.

## 24. `ChangeStreamOptions` Design Checklist

1. **Choose the right scope:** single collection or whole database? Multiple schemas?
2. **Choose the right body type:** `OrderDocument` for one collection, `Document` when heterogeneous.
3. **Choose operation types:** do you need insert/update/replace/delete/invalidate?
4. **Choose raw vs. Aggregation filter:** are fields on the envelope or in `fullDocument`?
5. **Preserve `event._id`:** never project/unset/replace away the resume token.
6. **Choose `fullDocument` policy:** default delta, `UPDATE_LOOKUP`, or pre/post images?
7. **Never assume body is always present:** branch for delete/update/missing lookup.
8. **Use `updateDescription` accurately:** updated fields, removed fields, truncated arrays.
9. **Choose resume mode:** `resumeAfter`, `startAfter`, or `resumeAt` per scenario.
10. **Durable checkpointing:** persist tokens with stream identity and pipeline version.
11. **Right ordering:** durable processing → checkpoint, never reversed.
12. **Idempotency:** tolerate event replays after crashes or across replicas.
13. **Plan for oplog expiry:** cannot replay history forever.
14. **Manage lifecycle:** start/stop/cancel cursors, never spawn unbounded watchers.
15. **Backpressure:** avoid unbounded buffers or checkpointing past incomplete events.
16. **Security:** avoid exposing raw events/PII, authorize tenants after authentication.
17. **Test on a replica set:** verify event types, raw fields, typed bodies, and resuming.
18. **Test pipeline mapping:** `Aggregation` may prefix fields with `fullDocument.`.
19. **Test invalidate/pre-images:** only on isolated test databases with supported configs.
20. **Monitor:** lag, reconnects, resume failures, processing rate, checkpoint age, duplicates.

## 25. Practice Exercises

An e-commerce system stores `orders` and syncs an `order_search` read model. Order documents have `_id`, `tenantId`, `status`, `totalMinor`, and `updatedAt`. The read model must receive updates and deletes, and the consumer must restart without losing events.

### Exercise 1 — Classifying event structure

Inspect this event:

```javascript
{
  _id: { _data: "<opaque-token-E1>" },
  operationType: "update",
  documentKey: { _id: "ORD-101" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Answer:

1. Is `event._id` the resume token or the order ID?
2. Which field holds the order ID?
3. Why can `getBody()` be null?
4. Can you deduce `tenantId` from this event if the delta omits it?
5. Should you immediately emit `OrderPaid` just because `fullDocument.status` looks like `PAID` on lookup?

**Hint:** distinguish state at an update operation, post-update lookup snapshots, and authoritative domain/tenant data.

### Exercise 2 — Filtering with raw `Document`

Write `ChangeStreamOptions` accepting only:

- `insert`,
- `update`,
- `replace`,

and enable `returnFullDocumentOnUpdate()`. Then add `delete` and explain why handlers must not treat `getBody()` as non-null for every event.

Reference solution:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .filter(new Document("$match",
        new Document("operationType",
            new Document("$in",
                List.of("insert", "update",
                        "replace", "delete")))))
    .returnFullDocumentOnUpdate()
    .build();
```

In real code, add `Document`/`List` imports. Handle `delete` separately via `documentKey`.

### Exercise 3 — Filtering by delta

To receive only updates touching `status`, build:

```javascript
{
  $match: {
    operationType: "update",
    "updateDescription.updatedFields.status": {
      $exists: true
    }
  }
}
```

Explain:

1. Why does this filter not guarantee catching `replace`?
2. Why are updates changing only `updatedAt` excluded?
3. If `status` is updated and then the document is updated again immediately, why might `UPDATE_LOOKUP` return a different status?
4. When schemas contain field names with dots, what must you watch out for?

### Exercise 4 — Aggregation mapping vs. raw BSON

Compare:

```java
Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("operationType").is("update")));
```

with:

```java
new Document("$match",
    new Document("updateDescription.updatedFields.status",
        new Document("$exists", true)));
```

State which fields belong to the **event envelope**, which belong to the **domain document**, why mapping may auto-prefix `fullDocument.`, and when to pick `TypedAggregation` vs. raw `Document`.

### Exercise 5 — Tokens and pipeline projections

A developer tries to shrink payloads with:

```javascript
{
  $project: {
    _id: 0,
    operationType: 1,
    documentKey: 1
  }
}
```

Fix it to keep `_id` and explain:

- Why is the token distinct from `documentKey._id`?
- Why can modifying `event._id` fail the stream starting in MongoDB 4.2?
- When changing a pipeline, why must you verify resumability from old checkpoints?

### Exercise 6 — `updateLookup` and pre-images

Given timeline:

```text
10:00:00  status=NEW
10:00:01  update NEW -> PAID       (E1)
10:00:02  update PAID -> SHIPPED   (E2)
10:00:03  consumer reads E1 with UPDATE_LOOKUP
```

Questions:

1. What is `E1.updateDescription.updatedFields.status`?
2. What might `E1.fullDocument.status` be?
3. What preconditions are needed for `getBodyBeforeChange()` to return the prior image?
4. If `WHEN_AVAILABLE` finds no image, what should the handler do?
5. When should an `OrderPaid` outbox event be used instead of inferring from `fullDocument`?

### Exercise 7 — Consumer and checkpointing

Given code:

```java
// ANTI-PATTERN:
source.flatMap(event ->
    checkpoints.save(event.getResumeToken())
        .then(handler.process(event)));
```

Identify at least three bugs:

1. The checkpoint is written **before** processing.
2. `flatMap` can write a later event's token before an earlier event completes.
3. A handler failure can cause the event to be skipped on resume.

Fix it with sequential `concatMap` processing, checkpointing only after `handler.process(event)` finishes durably, plus idempotency.

### Exercise 8 — Restarts and duplicates

Simulate:

```text
Event E1 processed
Checkpoint R1 saved
Event E2 processed
Crash before checkpoint R2
Restart with resumeAfter(R1)
E2 delivered again
```

Build deduplication by event ID/token or idempotent business writes. Describe how to avoid double-applying `$inc` or sending duplicate emails.

### Exercise 9 — Invalidation and oplog window

1. Drop an **isolated test** collection and observe `invalidate`.
2. Why is `resumeAfter(invalidateToken)` not equivalent to `startAfter(invalidateToken)`?
3. If a token was evicted from the oplog, why does infinite retrying not help?
4. How do you resnapshot/backfill a read model safely?
5. Why must pipeline/options stay consistent when resuming?

### Exercise 10 — `StepVerifier` test

On a test replica set:

1. Establish resume token R or a server-side cursor-readiness mechanism.
2. Insert an `OrderDocument` with a random ID into `orders`.
3. Subscribe to the stream from R, using `take(1)` after filtering for the test event.
4. Verify `operationType`, `getResumeToken()`, `getRaw().getDocumentKey()`, and `getBody()`.
5. Update and delete the document, verifying event types differ in body and delta.
6. Do not use fixed `Thread.sleep` to prove the watcher is ready.
7. Clean up only test IDs; do not drop a shared database.

### Exercise 11 — Designing a multi-tenant pipeline

A database watch stream sees `orders`, `customers`, and `audit_events`. Do the following:

- Use `ChangeStreamEvent<Document>` instead of forcing `OrderDocument`.
- Check `getCollectionName()` before converting.
- Verify `tenantId` from a trustworthy source.
- Avoid broadcasting raw events to unauthorized clients.
- Define how bodyless delete events will be tenant-routed.
- Propose an outbox design if tenant identity cannot be safely derived on deletes.

### Exercise 12 — Incident troubleshooting

The system reports:

```text
change_stream_events_received_total      increasing
change_stream_events_processed_total     flat
change_stream_checkpoint_age_seconds     increasing
change_stream_resume_failed_total        flat
```

Evaluate whether downstream handlers are failing/slow, queues are backed up, or `onError` went unobserved. Propose traces and metrics to pinpoint where events stalled, along with retry/dead-letter/alert policies that **never checkpoint unprocessed events**.

## 26. Self-Check Questions

| Question | Suggested answer |
| --- | --- |
| Do change streams work on standalone MongoDB? | Usually no; requires a supported replica set or sharded cluster |
| What is event `_id`? | Resume token, not document ID |
| When is `documentKey` used? | Document identification, especially on deletes |
| Does `getBody()` always exist on updates? | No; default is delta-only, and lookup can still return null |
| What does `getRaw()` give you? | Access to envelope, `updateDescription`/`documentKey`, and metadata missing from the entity |
| How do `filter(Aggregation)` and `filter(Document...)` differ? | Spring field mapping/prefixing vs. raw BSON stages |
| When to use `returnFullDocumentOnUpdate()`? | When looking up the current document on updates while accepting its limitations |
| Can `_id` be removed in `$project`? | No, must preserve the resume token |
| Can `resumeAfter` be used after invalidate? | No per MongoDB rules; consider `startAfter` |
| Do resume tokens stay valid forever? | No; bounded by oplog/history |
| When should checkpoints be written? | After durable processing |
| Why is idempotency needed? | Resumes/retries can replay events |
| Can every collection be mapped to `OrderDocument`? | No; with multiple schemas use raw `Document`/a router |
| Is `clusterTime` a unique event ID? | No; multiple events can share it |
| Does `Flux` emit before subscribing? | No |
| How does `concatMap` help checkpointing? | Preserves event processing order |
| Is a change stream a message broker consumer group? | No; each cursor can see the same events |

## 27. References

- Spring Data MongoDB — [Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html): imperative `MessageListenerContainer`, reactive `ChangeStreamEvent`, and resuming.
- Spring Data MongoDB API — [ChangeStreamOptions](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.html): builder, getters, stream options.
- Spring Data MongoDB API — [ChangeStreamOptionsBuilder](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html): `filter(Aggregation)`, `filter(Document...)`, `resumeAfter`, `startAfter`, `returnFullDocumentOnUpdate`.
- Spring Data MongoDB API — [ChangeStreamEvent](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamEvent.html): `getBody`, `getBodyBeforeChange`, `getRaw`, `getResumeToken`, timestamps.
- Spring Data MongoDB API — [ReactiveMongoOperations](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): `changeStream(String, ChangeStreamOptions, Class<T>)` and fluent API.
- Spring Data MongoDB API — [ReactiveChangeStreamOperation.ChangeStreamWithOptions](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveChangeStreamOperation.ChangeStreamWithOptions.html): `withOptions(Consumer<ChangeStreamOptionsBuilder>)`.
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changestreams/): resuming, invalidation, options/pipeline, oplog history.
- MongoDB Manual — [Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/): event envelope, `update`/`delete`/`replace`, and tokens.
- MongoDB Manual — [Update Event](https://www.mongodb.com/docs/manual/reference/change-events/update/): `updateDescription`, updated/removed fields, and path semantics.
- MongoDB Manual — [`$changeStream` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/): `fullDocument` policy, `resumeAfter`/`startAfter`, and pre/post images.
- MongoDB Manual — [Collection Watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/): watch options and cursor semantics.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscriptions, `concatMap`, error handling, and backpressure.

## Key Takeaways

**`ChangeStreamOptions` controls pipeline filters, full-document lookups, pre/post images, and where to start reading events; `ChangeStreamEvent<T>` is an envelope wrapping both the converted entity and MongoDB metadata.** `getBody()` may be null because default updates carry only `updateDescription` and deletes carry only `documentKey`. Distinguish event `_id` (resume token) from document `_id`; never strip tokens via `$project`. With `filter(Aggregation)`, understand the rule prefixing domain fields to `fullDocument.*`, whereas `filter(Document...)` keeps raw BSON paths. Save checkpoints only after durable processing; keep pipelines/options consistent on resume, monitor the oplog window, embrace event replay, and design idempotent consumers. Test inserts, updates, replaces, deletes, full documents, raw events, and resuming against a real MongoDB replica set before putting change streams into production.
