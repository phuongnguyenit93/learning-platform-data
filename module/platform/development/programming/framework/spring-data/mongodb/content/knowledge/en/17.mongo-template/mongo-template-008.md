# Callback `execute` to Use `MongoDatabase` or `MongoCollection`

> **Chapter:** MongoTemplate  
> **Module:** `SPRING_DATA_MONGODB` — connecting, mapping documents, and operating on MongoDB via `MongoTemplate` or repositories; practicing queries, indexes, transactions, reactive access, testing, and performance diagnostics.  
> **Goal:** Know when direct MongoDB Java Driver access is needed, use `MongoTemplate.execute(...)` overloads properly, distinguish `DbCallback` from `CollectionCallback`, manage cursors/resources, understand mapping and transaction boundaries, and test raw BSON operations safely.

## 1. Why does `MongoTemplate` have an `execute` callback?

Most everyday operations can be expressed using `MongoRepository` or `MongoTemplate`:

~~~java
// Query using the entity and Java properties.
template.find(
    Query.query(Criteria.where("state").is("PAID")),
    OrderDocument.class
);
~~~

Sometimes, however, an application needs a lower-level capability or a specific **MongoDB Java Driver** API: inspecting index metadata, running database commands, setting specialized driver options, accessing `MongoCollection<Document>`, or working with BSON structures without a convenient entity mapping.

`MongoTemplate.execute(...)` lets you place driver operations inside a **callback** receiving an object provided by Spring Data:

- `DbCallback<T>` receives `com.mongodb.client.MongoDatabase`.
- `CollectionCallback<T>` receives `com.mongodb.client.MongoCollection<org.bson.Document>`.

Spring Data selects the database/collection per template configuration and provides a consistent entry point for low-level operations, including translating eligible MongoDB errors into Spring's `DataAccessException` hierarchy.

~~~mermaid
flowchart TD
    A["Application service"] --> B["MongoTemplate / MongoOperations"]
    B --> C{"What operation is needed?"}
    C -->|Domain CRUD| D["find / insert / update / remove"]
    C -->|MongoDatabase| E["execute(DbCallback<T>)"]
    C -->|MongoCollection| F["execute(CollectionCallback<T>)"]
    D --> G["MongoDB driver"]
    E --> G
    F --> G
    G --> H[("MongoDB")]
~~~

**Key point:** the `execute` callback is an **entry point to the driver**, not an automatic transaction, nor a way to force the driver to automatically understand entity mapping annotations. Raw driver access gives flexibility while requiring you to manage BSON, IDs, resources, and write side effects explicitly.

## 2. Three main overloads to remember

Common `MongoOperations` signatures in Spring Data MongoDB:

~~~java
<T> T execute(DbCallback<T> action);

<T> T execute(
    Class<?> entityClass,
    CollectionCallback<T> action
);

<T> T execute(
    String collectionName,
    CollectionCallback<T> action
);
~~~

| Overload | Object passed to callback | When to use | How target is determined |
| --- | --- | --- | --- |
| `execute(DbCallback<T>)` | `MongoDatabase` | Inspect database, run commands, manage DB-level metadata | Database configured on `MongoTemplate` |
| `execute(OrderDocument.class, CollectionCallback<T>)` | `MongoCollection<Document>` | Raw operations on the entity's collection | `@Document` mapping and naming strategy |
| `execute("orders_execute_demo_008", CollectionCallback<T>)` | `MongoCollection<Document>` | Exact collection name is known | Passed collection name string |

`T` is the **callback return type**: `Long`, `Boolean`, `Document`, `List<Document>`, `UpdateResult`, or an application-defined result DTO. Callbacks may return `null` if business logic permits, so never auto-unbox `Long` or `Boolean` without handling `null`.

The two `execute` forms accepting a collection differ in how the target is resolved. When `@Document(collection = "...")` is present, passing `Class` avoids hard-coding collection names; when working with system collections or data without an entity, passing the explicit name is more suitable.

### 2.1. Required imports

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.DbCallback;
import org.springframework.data.mongodb.core.CollectionCallback;
~~~

These examples use the **synchronous driver** API in `MongoTemplate`. Never mix `com.mongodb.client.MongoCollection` with the reactive driver's `com.mongodb.reactivestreams.client.MongoCollection`: they expose different execution methods.

## 3. Preparing the sample collection and entity

### 3.1. Dedicated dataset for practice

In `mongosh` connected to an **isolated learning database**, insert test data:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_execute_demo_008;

orders.insertMany([
  {
    _id: "o801",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 150000,
    version: NumberLong(0)
  },
  {
    _id: "o802",
    tenant_id: "t01",
    state_code: "NEW",
    amount_vnd: 300000,
    version: NumberLong(0)
  },
  {
    _id: "o803",
    tenant_id: "t02",
    state_code: "PAID",
    amount_vnd: 500000,
    version: NumberLong(0)
  },
  {
    _id: "o804",
    tenant_id: "t01",
    state_code: "CANCELLED",
    amount_vnd: 90000,
    version: NumberLong(0)
  }
]);

orders.createIndex(
  { tenant_id: 1, state_code: 1 },
  { name: "tenant_state_idx" }
);
~~~

Run `insertMany` only against a test collection that does not already hold these IDs, since re-running triggers duplicate-key errors. Read examples below assume the fixtures **have not yet been modified** by the update examples.

With the original dataset: there are 4 orders; tenant `t01` has 3 orders; tenant `t01` with status `PAID` has exactly 1 order (`o801`).

### 3.2. Java entity whose property names differ from BSON names

~~~java
// OrderDocument.java
package com.example.templatecallback;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_execute_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
    public Long getVersion() { return version; }
}
~~~

This difference is deliberate: **Java properties** are named `tenantId`, `state`, `amountVnd`; **BSON fields** are named `tenant_id`, `state_code`, `amount_vnd`. Calls like `MongoTemplate.find(Query, OrderDocument.class)` use mapping metadata to translate property paths, whereas raw driver calls inside callbacks require you to use **actual BSON names**.

With `@MongoId(FieldType.STRING)`, `_id` values remain BSON strings, avoiding surprises from `@Id String` when strings resemble ObjectIds.

## 4. `DbCallback<T>`: accessing `MongoDatabase`

### 4.1. Getting the configured database name

~~~java
import org.springframework.data.mongodb.core.DbCallback;

String dbName = template.execute(
    (DbCallback<String>) db -> db.getName()
);
~~~

Here `template` is an injected `MongoTemplate`. `db` has type `MongoDatabase`; `db.getName()` returns the database the template targets without opening a new connection.

A handy diagnostic use is debugging "document not found": before rewriting queries, confirm **which database** the program is actually hitting. Never expose database names, URIs, or sensitive connection details through public APIs.

### 4.2. Running a connectivity check via `runCommand`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.DbCallback;

Document reply = template.execute(
    (DbCallback<Document>) db ->
        db.runCommand(new Document("ping", 1))
);

Number ok = reply.get("ok", Number.class);
boolean healthy = ok != null && ok.doubleValue() == 1.0;
~~~

`ping` is a database-level MongoDB command, so `DbCallback` fits better than `CollectionCallback`. The response is a raw BSON `Document`, not a domain entity. In production, rely on health checks/Actuator instead of running `ping` on every HTTP request.

### 4.3. Listing collections in a database

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.DbCallback;

List<String> names = template.execute(
    (DbCallback<List<String>>) db ->
        db.listCollectionNames().into(new ArrayList<>())
);
~~~

Here the driver is accessed through `MongoDatabase`. Listing all collections may require specific permissions and should never be leaked to end users. In multi-tenant or multi-database setups, carefully verify which database the template points to.

### 4.4. Retrieving a collection inside DbCallback

~~~java
Long count = template.execute(
    (DbCallback<Long>) db ->
        db.getCollection("orders_execute_demo_008")
            .countDocuments(new Document("tenant_id", "t01"))
);
~~~

This works, yet when operating on **one specific collection**, `CollectionCallback` is usually cleaner: the template picks the collection for you, avoiding `db.getCollection(...)` and letting you use the entity-class overload.

**Do not confuse:** `DbCallback` gives access to the configured database, not permission to read arbitrary databases/collections if the MongoDB account lacks privileges. Server-side permissions are still enforced.

## 5. `CollectionCallback<T>`: accessing `MongoCollection<Document>`

### 5.1. Counting documents by BSON criteria

~~~java
import com.mongodb.client.model.Filters;
import org.springframework.data.mongodb.core.CollectionCallback;

Long tenantCount = template.execute(
    "orders_execute_demo_008",
    (CollectionCallback<Long>) collection ->
        collection.countDocuments(
            Filters.eq("tenant_id", "t01")
        )
);
// On original data: tenantCount == 3.
~~~

The collection-name overload passes the driver's `MongoCollection<Document>` to the callback. Instead of Spring Data's `Query` or `Criteria`, the code uses the driver's `Filters`.

### 5.2. Selecting the collection via entity class

~~~java
Long paidForTenant = template.execute(
    OrderDocument.class,
    (CollectionCallback<Long>) collection ->
        collection.countDocuments(
            Filters.and(
                Filters.eq("tenant_id", "t01"),
                Filters.eq("state_code", "PAID")
            )
        )
);
// On original data: paidForTenant == 1.
~~~

Spring Data inspects `@Document(collection = "orders_execute_demo_008")` to choose the collection. That is a nice benefit of the class-based overload. However, **inside the callback you are still using the raw driver API**, so `"state_code"` is the physical BSON name, not the Java property `"state"`.

### 5.3. Fetching a raw document

~~~java
import org.bson.Document;
import com.mongodb.client.model.Filters;

Document raw = template.execute(
    OrderDocument.class,
    collection ->
        collection.find(Filters.eq("_id", "o801")).first()
);

if (raw != null) {
    String stateCode = raw.getString("state_code"); // "PAID".
    String tenant = raw.getString("tenant_id");     // "t01".
}
~~~

`first()` returns `null` if no document matches. Do not assume every field is always present or has the expected type, especially across schema versions. When you want Java entities, prefer `MongoTemplate.findById("o801", OrderDocument.class)` so the converter maps them.

### 5.4. Fetching only selected fields via driver projection

~~~java
import java.util.ArrayList;
import java.util.List;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import org.bson.Document;

List<Document> summaries = template.execute(
    "orders_execute_demo_008",
    collection -> collection
        .find(Filters.eq("tenant_id", "t01"))
        .projection(Projections.include(
            "_id", "state_code", "amount_vnd"
        ))
        .limit(10)
        .into(new ArrayList<>())
);
~~~

`Projections.include(...)` instructs MongoDB to return only the chosen fields, reducing network payload. In the driver, `_id` is returned by default unless excluded; here we include it explicitly to clarify the output contract. This is a **BSON field projection**, not a Spring Data interface projection.

**Limitation:** if the callback returns a huge list, `into(new ArrayList<>())` materializes everything in memory. Bound result size or iterate a cursor inside the callback.

## 6. Writing via callbacks: flexible, but mapping rules are on you

### 6.1. Updating a field with the driver

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

UpdateResult result = template.execute(
    OrderDocument.class,
    collection -> collection.updateOne(
        Filters.and(
            Filters.eq("_id", "o802"),
            Filters.eq("tenant_id", "t01"),
            Filters.eq("state_code", "NEW")
        ),
        Updates.set("state_code", "PAID")
    )
);

if (result != null && result.wasAcknowledged()) {
    long matched = result.getMatchedCount();
    long modified = result.getModifiedCount();
    // On original data: matched=1, modified=1.
}
~~~

This is a **real write operation**: run only on test data. On a second run, `state_code` on `o802` is no longer `NEW`, so `matchedCount` becomes 0. Depending on write concern, count getters are only valid when the write is acknowledged.

### 6.2. The raw driver does not apply entity mapping automatically

In `OrderDocument`, Java property `state` maps to BSON `state_code`. Compare:

~~~java
// Spring Data: Criteria uses Java properties.
template.updateFirst(
    Query.query(Criteria.where("id").is("o802")),
    new Update().set("state", "PAID"),
    OrderDocument.class
);

// Driver callback: filter/update use physical BSON names.
template.execute(OrderDocument.class, collection ->
    collection.updateOne(
        Filters.eq("_id", "o802"),
        Updates.set("state_code", "PAID")
    )
);
~~~

If you mistakenly write `Updates.set("state", "PAID")` inside the callback, the driver creates a **new BSON field named `state`** instead of updating `state_code`. The Spring Data entity still reads `state` from `state_code`, leaving two similarly named fields in the document that are hard to debug.

Calls like `collection.insertOne(new Document(...))`, `updateOne`, or `deleteMany` are driver APIs. They **do not automatically run entity conversion, auditing, entity callbacks, or mapping events like `MongoTemplate.save/insert`**. If your application relies on those hooks, raw callbacks are not a drop-in replacement.

### 6.3. `@Version` is not automatically checked on raw updates

The entity in section 3 includes:

~~~java
@Version
private Long version;
~~~

Through compatible Spring Data mapping paths, `@Version` detects updates/deletions made against stale entity snapshots. However, in a raw driver command:

~~~java
collection.updateOne(
    Filters.eq("_id", "o802"),
    Updates.set("state_code", "PAID")
);
~~~

no version filter or increment is added automatically. If a raw writer mutates data without incrementing `version`, a Spring Data flow holding a stale entity **will fail to detect** the concurrent change via optimistic locking.

If you must use the raw driver on a versioned entity, enforce the versioning policy **explicitly**—for example, filtering by `_id + version` and atomically incrementing `version`:

~~~java
import com.mongodb.client.result.UpdateResult;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

long expectedVersion = 0L; // In practice, obtained from previously read data.

UpdateResult changed = template.execute(
    OrderDocument.class,
    collection -> collection.updateOne(
        and(
            eq("_id", "o802"),
            eq("version", expectedVersion),
            eq("state_code", "NEW")
        ),
        combine(
            set("state_code", "PAID"),
            inc("version", 1L)
        )
    )
);

if (changed == null || changed.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Order not found, state changed, or version conflict"
    );
}
~~~

This is an **alternative example branch**, not meant to run right after the earlier snippet that already transitioned `o802` to `PAID`. Reset the fixture if you want to observe `matchedCount=1`. Using `inc("version", 1L)` must match the actual BSON type of `version`, and every other writer must follow the same versioning convention.

## 7. Reading cursors inside callbacks and managing resources

### 7.1. Never return a raw cursor outside the callback

A MongoDB driver cursor ties up connection and server cursor resources. If a callback returns a raw `FindIterable` or `MongoCursor` for the caller to consume later, the query lifecycle detaches from the session/transaction lifecycle and leaks resources.

Always **consume and close the cursor inside the callback** when working with raw data:

~~~java
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

List<Document> selected = template.execute(
    "orders_execute_demo_008",
    collection -> {
        List<Document> rows = new ArrayList<>();

        try (MongoCursor<Document> cursor = collection
                .find(Filters.eq("tenant_id", "t01"))
                .projection(Projections.include(
                    "_id", "state_code", "amount_vnd"
                ))
                .sort(Sorts.ascending("_id"))
                .limit(100)
                .iterator()) {

            while (cursor.hasNext()) {
                rows.add(cursor.next());
            }
        }

        return rows;
    }
);
~~~

`try-with-resources` closes `MongoCursor` even if an error occurs mid-iteration. Limit `100` is purely illustrative: on large collections, do not raise the limit unboundedly; process in batches or streams.

### 7.2. When to use `MongoTemplate.stream`?

When business logic needs to stream mapped Java entities sequentially, `MongoTemplate.stream(Query, Class)` is often preferable because it still uses the converter:

~~~java
import org.springframework.data.util.CloseableIterator;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
);

try (CloseableIterator<OrderDocument> cursor =
         template.stream(query, OrderDocument.class)) {

    while (cursor.hasNext()) {
        OrderDocument order = cursor.next();
        // Process domain objects one by one.
    }
}
~~~

`stream` must also be closed; streaming does not mean processing millions of records cannot hit timeouts, network drops, or concurrent modifications. When resume-on-failure is required, design checkpoints over a stable sort key, retries, and idempotency.

## 8. Inspecting index metadata and specialized driver operations

### 8.1. Checking whether an index already exists

~~~java
import org.bson.Document;

Boolean hasIndex = template.execute(
    OrderDocument.class,
    collection -> {
        for (Document index : collection.listIndexes()) {
            if ("tenant_state_idx".equals(index.getString("name"))) {
                return true;
            }
        }
        return false;
    }
);
~~~

`listIndexes()` belongs to the MongoDB Java Driver and returns BSON metadata. This is a clean use case for `CollectionCallback` when checking index options not conveniently exposed by higher-level `MongoTemplate` APIs.

Never assume "an index with that name exists" means **its definition is right**. To verify thoroughly, inspect `key`, `unique`, `partialFilterExpression`, `collation`, and other relevant options.

### 8.2. Creating an index via the driver

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

String name = template.execute(
    OrderDocument.class,
    collection -> collection.createIndex(
        Indexes.compoundIndex(
            Indexes.ascending("tenant_id"),
            Indexes.ascending("state_code")
        ),
        new IndexOptions().name("tenant_state_idx")
    )
);
~~~

This command **modifies collection metadata**; run it in test environments only when you know the index does not exist yet or matches the existing definition. Production index creation needs an operational plan, load assessment, and data cleanup (especially for unique indexes).

For standard projects, consider `@Indexed`, `IndexOperations`/`IndexResolver`, or managed migrations. Driver callbacks are not mandatory for creating indexes.

### 8.3. Database-level commands vs collection CRUD

Commands operating at the database level (`ping`, inspecting settings, authorized admin commands) belong in `DbCallback`. Never execute destructive collection/database commands just because `MongoDatabase` exposes `runCommand`; obey authorization and migration policies.

If you simply need to execute a MongoDB command from Spring Data, `MongoTemplate.executeCommand(...)` is another high-level API worth considering that avoids writing a `DbCallback` manually.

## 9. Comparing raw callbacks vs entity-mapped queries

| Aspect | `MongoTemplate.find/update/insert` | `MongoTemplate.execute(... CollectionCallback)` |
| --- | --- | --- |
| Typical inputs | Java entities, `Query`/`Criteria`/`Update` | `MongoCollection<Document>`, driver BSON/filters |
| Field names in queries | Java properties and mapping metadata | **Physical BSON field names** |
| `@Field("state_code")` | Handled by converter/query mapper | Does not translate `"state"` to `"state_code"` |
| `@MongoId` / `@Id` | Applies ID mapping rules | Must supply matching BSON type for `_id` |
| Custom converters | Applied in appropriate mapping flows | Not applied automatically on raw `Document` calls |
| `@Version` | Supported on compatible operations | Must manage conditions and increments manually |
| Auditing / entity callbacks | Active for corresponding entity operations | Not invoked automatically for raw driver CRUD |
| Access to special driver options/commands | May be constrained by high-level API | More flexible |
| Exception translation | Yes | `execute` translates eligible driver exceptions |
| Transactions | Participates when session/manager configured | Can participate via `execute` session proxy, yet **does not start a transaction itself** |

### 9.1. Not every operation needs a callback

If all you need is:

~~~java
template.find(
    Query.query(Criteria.where("state").is("PAID")),
    OrderDocument.class
);
~~~

do not rewrite it as:

~~~java
template.execute(OrderDocument.class, collection ->
    collection.find(Filters.eq("state_code", "PAID"))
        .into(new java.util.ArrayList<>())
);
~~~

The second version adds manual responsibility for BSON names, mapping, and resources; choose it only when a specific driver capability or specialized handling justifies it.

### 9.2. Never treat `MongoCollection` as an automatic repository

A Java entity may carry `@Document`, `@Indexed`, `@Version`, converters, and callbacks. Yet passing `OrderDocument.class` into `execute` **only helps the template resolve the collection**; it does not "upgrade" raw driver calls on that collection into Spring Data entity-aware operations.

This distinction is vital when maintaining codebases that mix repositories with raw callback tasks.

## 10. Exception translation and error handling

The MongoDB Java Driver throws driver-specific exceptions for connection failures, duplicate keys, timeouts, or authorization errors. Inside `MongoTemplate.execute`, Spring Data attempts to translate eligible MongoDB errors into **Spring's `DataAccessException` hierarchy** via `MongoExceptionTranslator`.

Example service handling Spring exception types:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;

try {
    template.execute("orders_execute_demo_008", collection -> {
        collection.insertOne(
            new Document("_id", "o801")
                .append("tenant_id", "t01")
                .append("state_code", "NEW")
        );
        return null;
    });
} catch (DuplicateKeyException duplicate) {
    // Expected case if ID o801 already exists.
    // Return an appropriate business response.
} catch (DataAccessException dataAccessFailure) {
    // Record logs/metrics and classify the database error.
}
~~~

**Run write examples only on test databases.** Not every Java exception thrown inside a callback is translated to `DataAccessException`: for instance, a `NullPointerException` or custom logic exception propagates directly. In operations, preserve root causes in logs/diagnostics without exposing connection strings or sensitive data in public API responses.

Never write `catch (Exception)` and return a fake success result. If the callback runs inside a transaction, swallowing exceptions can commit an unintended partial state.

## 11. Sessions and transactions: `execute` does not mean atomic

### 11.1. One callback can contain multiple operations

~~~java
template.execute(
    "orders_execute_demo_008",
    collection -> {
        collection.updateOne(
            Filters.eq("_id", "o801"),
            Updates.set("state_code", "PAID")
        );
        collection.updateOne(
            Filters.eq("_id", "o802"),
            Updates.set("state_code", "PAID")
        );
        return null;
    }
);
~~~

Even inside **one lambda**, those two updates **are not atomic across both documents**. If the first succeeds and the second fails, the first modification may already be committed.

MongoDB guarantees atomicity for a write on a single document; multiple operations or multiple documents require a transaction when business rules demand all-or-nothing.

### 11.2. Using `MongoTransactionManager` when transactions are needed

~~~java
// MongoTransactionConfiguration.java
package com.example.templatecallback;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

In a Spring service:

~~~java
// RawOrderService.java
package com.example.templatecallback;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RawOrderService {
    private final MongoTemplate template;

    public RawOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void markTwoOrdersPaid() {
        template.execute(OrderDocument.class, collection -> {
            collection.updateOne(
                Filters.eq("_id", "o801"),
                Updates.set("state_code", "PAID")
            );
            collection.updateOne(
                Filters.eq("_id", "o802"),
                Updates.set("state_code", "PAID")
            );
            return null;
        });
    }
}
~~~

**Prerequisites:** MongoDB must support transactions (such as a replica set or compatible sharded cluster), Spring must have `MongoTransactionManager`, and `MongoTemplate` must share **the same `MongoDatabaseFactory`** as the manager. Callbacks executing within a managed template context receive **session-proxied** driver objects so commands carry the proper session. Failures roll back the transaction when exceptions propagate across the transaction boundary; test against real infrastructure.

In this setup, never manually start another `MongoClient`/`ClientSession` inside the callback or call raw `template.getCollection(...)` outside the session mechanism assuming those calls belong to the active transaction.

### 11.3. `getCollection`/`getDb` vs `execute` in sessions

Spring Data documentation distinguishes:

- Collection/database objects passed **into `execute` callbacks** can be proxies bound to the template's `ClientSession` within transaction/session scope.
- Gateways obtained directly via `MongoTemplate.getCollection(...)`/`getDb()` must not be assumed to be session-proxied; when using them directly, you may need to pass `ClientSession` explicitly per driver API.

That does not mean every `execute` call runs inside a transaction. **A transaction must be started first** in the right scope. With proxy-based `@Transactional`, watch out for self-invocation: calling another method on the same bean can bypass the transaction proxy.

### 11.4. Not every operation is valid inside a transaction

MongoDB restricts certain commands, DDL operations, topologies, and transaction lifetimes. For example, avoid putting index or collection metadata modifications inside transactional business flows without understanding server constraints. Just because a callback can invoke `createIndex` does not mean it is valid inside an active transaction.

## 12. Reactive counterpart: `ReactiveMongoTemplate.execute`

Spring Data MongoDB provides an analogous callback mechanism in the reactive API:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

In the reactive API:

- `execute(ReactiveDatabaseCallback<T>)` returns `Flux<T>`.
- `execute(Class<?>, ReactiveCollectionCallback<T>)` returns `Flux<T>`.
- `execute(String, ReactiveCollectionCallback<T>)` returns `Flux<T>`.

Counting documents example:

~~~java
Mono<Long> count = reactiveTemplate
    .execute("orders_execute_demo_008", collection ->
        Mono.from(collection.countDocuments(
            Filters.eq("tenant_id", "t01")
        ))
    )
    .next();
// count emits 3 if the test data has not been modified.
~~~

Here `reactiveTemplate` is a `ReactiveMongoTemplate` bean, and `collection` comes from the **MongoDB Reactive Streams driver**. Calling `execute` only builds the publisher; execution happens upon subscription. Never call `block()` on the event loop.

Reading multiple documents:

~~~java
Flux<String> ids = reactiveTemplate.execute(
    OrderDocument.class,
    collection -> Flux.from(
        collection.find(Filters.eq("tenant_id", "t01"))
    ).map(doc -> doc.getString("_id"))
);
~~~

Reactive supports composition and backpressure, yet does not speed up unindexed queries. Manage publisher lifecycles, transaction contexts (`ReactiveMongoTransactionManager`/`TransactionalOperator`), and error handling; never wrap a synchronous `MongoCollection` inside a reactive chain pretending it is non-blocking.

## 13. Structuring code to keep callbacks maintainable

Rather than scattering raw lambdas through controllers, encapsulate them in a focused service or adapter:

~~~java
// RawOrderMetricsGateway.java
package com.example.templatecallback;

import com.mongodb.client.model.Filters;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
public class RawOrderMetricsGateway {
    private final MongoTemplate template;

    public RawOrderMetricsGateway(MongoTemplate template) {
        this.template = template;
    }

    public long countPaidOrders(String tenantId) {
        Objects.requireNonNull(tenantId, "tenantId");

        Long count = template.execute(
            OrderDocument.class,
            collection -> collection.countDocuments(
                Filters.and(
                    Filters.eq("tenant_id", tenantId),
                    Filters.eq("state_code", "PAID")
                )
            )
        );

        return Objects.requireNonNull(
            count, "MongoDB count callback returned null"
        );
    }
}
~~~

Benefits:

- Restricts where BSON field names `tenant_id`/`state_code` must be known.
- Simplifies adding metrics, input validation, and integration tests.
- Gives a single place to replace with `MongoTemplate.count(...)` if raw driver access becomes unnecessary.
- Keeps tenant authorization separate from the callback; **the tenant ID must come from an authenticated user context at the caller layer**, never trusting unverified client parameters.

When an operation is merely a standard `countDocuments`, `MongoTemplate.count` already handles it cleanly with mapping. This service serves as a **raw-driver boundary example**, not a recommendation to write callbacks just to count.

## 14. Testing callbacks against real MongoDB

Unit tests mocking `MongoTemplate.execute` verify how a service processes return values, yet cannot confirm field-name mapping, driver filter syntax, or write concerns. Use integration tests with real MongoDB/Testcontainers for critical raw operations.

### 14.1. Test matrix

| Test case | What to verify |
| --- | --- |
| `execute(DbCallback)` reads database | Matches database configured in test profile |
| `execute(OrderDocument.class, ...)` | Selects right collection per `@Document` |
| Raw `state_code` query | Queries exact BSON alias, not mistakenly Java property `state` |
| `countDocuments` | Counts matching tenant and status accurately |
| Conditional raw update | `matchedCount`/`modifiedCount` match expectations |
| `@Version` with raw writer | Does not assume version auto-increments |
| Exception translation | Duplicate key/driver failures map to expected exception types |
| Cursor iteration | Cursor closes cleanly on both success and failure |
| Two-document transaction | Rolls back on error in a supported topology |
| Reactive callback | Publisher subscribes cleanly and emits expected results |

### 14.2. Testing BSON reads with proper aliases

This test assumes a Spring Boot test setup with a dedicated MongoDB instance, never production collections:

~~~java
package com.example.templatecallback;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.Objects;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class MongoTemplateExecuteCallbackTest {
    @Autowired MongoTemplate template;

    @Test
    void callbackUsesNativeBsonFieldNames() {
        String fixtureId = "fixture-execute-008";
        var collection = template.getDb()
            .getCollection("orders_execute_demo_008");

        collection.deleteOne(Filters.eq("_id", fixtureId));
        try {
            collection.insertOne(
                new Document("_id", fixtureId)
                    .append("tenant_id", "test-tenant")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 123000)
            );

            Long matching = template.execute(
                OrderDocument.class,
                nativeCollection -> nativeCollection.countDocuments(
                    Filters.and(
                        Filters.eq("_id", fixtureId),
                        Filters.eq("tenant_id", "test-tenant"),
                        Filters.eq("state_code", "PAID")
                    )
                )
            );

            Long wrongAlias = template.execute(
                OrderDocument.class,
                nativeCollection -> nativeCollection.countDocuments(
                    Filters.and(
                        Filters.eq("_id", fixtureId),
                        Filters.eq("state", "PAID")
                    )
                )
            );

            assertThat(Objects.requireNonNull(matching))
                .isEqualTo(1L);
            assertThat(Objects.requireNonNull(wrongAlias))
                .isEqualTo(0L);
        } finally {
            collection.deleteOne(Filters.eq("_id", fixtureId));
        }
    }
}
~~~

This test proves raw filters do not apply `@Field("state_code")` automatically. The fixture inserts and deletes a real document under a fixed ID, so **run only on a dedicated test database**. It does not yet test transactions or exception translation; those require dedicated tests with matching topology/configuration.

### 14.3. Testing transaction rollback

With `MongoTransactionManager` and a test MongoDB replica set configured:

1. Prepare two test documents.
2. Enter a `@Transactional` method through the Spring proxy.
3. Execute a callback updating the first document, then intentionally throw an exception before updating the second.
4. Assert **the first document still holds its original value** after rollback.
5. Clean up fixtures and check for leftover resources/sessions.

Never test against standalone MongoDB (which lacks multi-document transaction support) and conclude "callbacks do not roll back". Verify transactions are actually enabled and the template shares the same factory.

## 15. Troubleshooting common issues

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| `execute(OrderDocument.class, ...)` hits wrong collection | `@Document` or naming strategy differs from expectation | Compare metadata collection against real data |
| Callback `find` returns empty while `template.find` finds data | Raw filter used Java property instead of BSON field, or wrong `_id` type | Inspect `@Field`, `@MongoId`, and `mongosh` |
| Raw update creates an unintended new field | `Updates.set("state", ...)` instead of `"state_code"` | Compare BSON before/after; centralize field constants |
| Raw update fails to increment `version` | Driver does not apply `@Version` automatically | Add manual predicate/increment or use mapped updates |
| Callback builds huge list causing OOM | Unbounded `find().into(new ArrayList<>())` | Add limits, batching, cursor iteration, or `template.stream` |
| `MongoCursor` leaks resources | Forgot to close iterator, or returned cursor outside callback | Use `try-with-resources`, finish processing inside callback |
| Driver exception not translated as expected | Not a MongoDB error covered by translator, or callback threw custom Java error | Inspect root cause and exception translator configuration |
| `execute` runs two updates, only one succeeds | Callbacks do not create transactions automatically | Configure `MongoTransactionManager`/sessions or compensation |
| Inside transaction yet raw call misses session | Grabbed `MongoCollection` outside callback, wrong factory, or self-invocation bypassing proxy | Use callback in properly scoped template/session; write integration test |
| Reactive callback never modifies data | Publisher was never subscribed to | Chain into reactive flow or verify with `StepVerifier` |
| Index exists by name yet queries remain slow | Index keys/sort mismatch, or low predicate selectivity | Inspect full `listIndexes` definition and `explain("executionStats")` |
| Unexpected database name | Active profile or URI/database config differs | Use `DbCallback.getName` to verify active profile and connection |

## 16. Practice exercises

The exercises below assume `orders_execute_demo_008` from section 3 is freshly loaded. Write exercises change state for subsequent ones; run in an isolated test environment.

### Exercise 1 — Pick the right overload

You need to retrieve the name of the database the application is connected to. Which callback do you use?

**Answer:** `DbCallback`, for example:

~~~java
String dbName = template.execute(
    (DbCallback<String>) MongoDatabase::getName
);
~~~

Because the work operates on **`MongoDatabase`**, no collection selection is needed.

### Exercise 2 — Count orders in a collection

Count orders for tenant `t01` with `state_code: "PAID"` using the entity-class overload.

**Answer:**

~~~java
Long count = template.execute(
    OrderDocument.class,
    collection -> collection.countDocuments(
        Filters.and(
            Filters.eq("tenant_id", "t01"),
            Filters.eq("state_code", "PAID")
        )
    )
);
// On original data: 1.
~~~

### Exercise 3 — Why a raw query returns empty

The entity has `@Field("state_code") private String state;`. A callback writes `Filters.eq("state", "PAID")`. Why does it find no orders?

**Answer:** The callback talks to the MongoDB driver directly without mapping `state` to `state_code`. Use `Filters.eq("state_code", "PAID")`, or switch back to `MongoTemplate.find(Query...)` to use mapping.

### Exercise 4 — Checking optimistic locking

One writer calls `MongoTemplate.save(entity)` with `@Version`. Another writer runs `collection.updateOne(Filters.eq("_id", id), Updates.set("state_code", "PAID"))`. What is the risk?

**Answer:** The raw writer neither checks nor increments `version`; the mapped writer may fail to detect out-of-band modifications. Fix this by unifying write paths or explicitly checking and incrementing `version` in the raw update.

### Exercise 5 — Returning a result from a callback

Write a callback returning the order count for tenant `t01` without loading full documents:

~~~java
Long count = template.execute(
    "orders_execute_demo_008",
    collection -> collection.countDocuments(
        Filters.eq("tenant_id", "t01")
    )
);
~~~

**Explanation:** Uses the driver's `countDocuments` directly instead of `find().into(...)` followed by `.size()`. On the original fixture, the result is 3.

### Exercise 6 — Two updates in one lambda

A callback invokes `updateOne` for `o801` and `o802`, and the second command fails. Are both guaranteed to roll back?

**Answer:** No. Callbacks do not create transactions automatically. When multi-document atomicity is required, configure MongoDB transactions on a supported topology with the proper manager/session and test rollback; otherwise, design compensation logic.

### Exercise 7 — Reactive callback

What does `ReactiveMongoTemplate.execute("orders_execute_demo_008", ...)` return, and when does the command execute?

**Answer:** It returns a `Flux<T>`; execution is deferred until a subscriber subscribes. For a single count result, you can chain `.next()` to obtain `Mono<Long>`. Never use the synchronous `MongoCollection` inside a reactive callback.

## References

- [Spring Data MongoDB — Template API / Execute Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `DbCallback`, `CollectionCallback`, return values, and exception translation.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `execute(...)` signatures and command/query APIs.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): overload and behavior details.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): session proxies, `MongoTransactionManager`, and transaction boundaries.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Field`, `@MongoId` metadata, and converters.
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): entity mapping callbacks and lifecycle events.
- [Spring Data MongoDB — ReactiveMongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): reactive callbacks and `Flux<T>`.
- [MongoDB Java Driver — CRUD Fundamentals](https://www.mongodb.com/docs/drivers/java/sync/current/crud/): driver `MongoCollection`, `Filters`, `Updates`, and results.
- [MongoDB Java Driver — Work with Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/): `listIndexes`/`createIndex` and index options.
