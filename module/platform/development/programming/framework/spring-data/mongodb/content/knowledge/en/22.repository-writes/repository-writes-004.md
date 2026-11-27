# Matching All Documents and Pagination Keyword Limitations

> **Chapter:** Repository Writes  
> **Module:** `SPRING_DATA_MONGODB` — connecting, mapping documents, and operating on MongoDB via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objective:** Understand the write scope of `@Update` repository methods; distinguish selecting documents by method name from limiting read results; recognize that `Top`, `First`, and pagination **do not limit the number of updated documents**; build safe solutions when business logic requires updating only N documents; verify actually modified document counts and handle write contention.

## 1. Problem: Does `findTop2...` really update only two documents?

Suppose the system has 50 orders in `NEW` status. You want to transition only the **first two orders** to `REVIEW`. The repository method below looks plausible:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findTop2ByState(String state);
~~~

Someone familiar with derived queries for **reading** might reason:

> `Top2` means take only two results, so only two documents are modified.

**This reasoning is wrong for Spring Data MongoDB repository update methods.** The official documentation specifies that an `@Update` operation applies to **all documents matching the query criteria**; you cannot narrow the update scope with limiting keywords such as `Top`/`First` or with pagination.

With 50 `state = NEW` documents, the call above can update **all 50 documents**, not two. The returned `long` is the number of **modified documents**, not the size of a fetched page.

### 1.1. Core rules

| Query approach | Does `Top/First/Pageable` limit scope? | Effect type |
| --- | --- | --- |
| Read-only derived finder `findTop2ByState(...)` returning `List<OrderDocument>` | **Yes**, limits read results | Reads at most two documents |
| Read-only derived finder `findByState(..., Pageable)` returning `Page<OrderDocument>` | **Yes**, paginates read results | Reads one window of documents |
| `@Update` on `findTop2ByState(...)` returning `long` | **No**, update scope remains all matching documents | Writes multiple documents |
| `@Update` intending to use `Pageable` to limit to N | **Pagination is not supported to limit updates** | Do not use as a write guardrail |
| `MongoTemplate.updateFirst(...)` / fluent `.first()` | **Yes**, updates at most one document | Writes one document |
| `MongoTemplate.updateMulti(...)` / fluent `.all()` | Updates all matching documents | Writes multiple documents |

The difference lies in the **executed operation type**, not just the method name. `Top2` is a result-limiting clause for **finders**; with `@Update`, the update executor uses the predicate to identify the document set and applies the update to **the entire matching set**.

~~~mermaid
flowchart TD
    M["Method name findTop2ByState"] --> A{"Has @Update?"}
    A -->|No| R["Read query with limit 2"]
    A -->|Yes| U["Extract predicate: state = NEW"]
    U --> W["Apply update to all matching documents"]
    W --> N["Return modified document count"]
~~~

**Short conclusion:** Never rely on `Top`/`First`/`Pageable` as a safety fence to limit an `@Update` operation.

## 2. Creating sample data for verification

### 2.1. Practice collection

Open `mongosh` and select an **isolated learning database**; never run the write examples in this lesson against production:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_repository_writes_demo_004;

orders.insertMany([
  {
    _id: "o401",
    tenantId: "t01",
    state: "NEW",
    attempts: 0,
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o402",
    tenantId: "t01",
    state: "NEW",
    attempts: 1,
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o403",
    tenantId: "t01",
    state: "NEW",
    attempts: 2,
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "o404",
    tenantId: "t01",
    state: "PAID",
    attempts: 0,
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "o405",
    tenantId: "t02",
    state: "NEW",
    attempts: 0,
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "o406",
    tenantId: "t01",
    state: "CANCELLED",
    attempts: 0,
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
]);

orders.createIndex({
  tenantId: 1,
  state: 1,
  createdAt: 1,
  _id: 1
});
~~~

Before running any updates, the initial document breakdown is:

| ID | Tenant | State | Attempts | Matches `tenant=t01, state=NEW`? |
| --- | --- | --- | ---: | --- |
| `o401` | t01 | NEW | 0 | Yes |
| `o402` | t01 | NEW | 1 | Yes |
| `o403` | t01 | NEW | 2 | Yes |
| `o404` | t01 | PAID | 0 | No |
| `o405` | t02 | NEW | 0 | No |
| `o406` | t01 | CANCELLED | 0 | No |

There are **three** orders matching `tenantId = "t01"` and `state = "NEW"`. Even if `Top2` appears in a repository update method name, the expected outcome is still **three** updated documents when transitioning all NEW orders to REVIEW.

**Fixture note:** `_id` values are fixed; re-running `insertMany` while documents already exist will throw a duplicate key error. The update examples across different sections should be treated as **independent scenarios against the initial data**. Use a fresh test collection, or perform a controlled reset on IDs you own, instead of running every example back-to-back against the same expectations.

### 2.2. Java entity

Example classes belong to package `com.example.repositorywrites`, each placed in its own corresponding file:

~~~java
// OrderDocument.java
package com.example.repositorywrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_repository_writes_demo_004")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String state;
    private int attempts;
    private Instant createdAt;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public int getAttempts() { return attempts; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` keeps `_id` as a BSON string matching the sample data. The class omits `@Version` in the core examples so `modifiedCount` clearly reflects `$set`/`$inc` effects; `@Version` and optimistic locking are covered in a dedicated section.

In a real domain, also enforce tenant/authorization checks in the **service**. Having a `tenantId` field does not cause Spring Data to automatically inject tenant filtering into every query.

## 3. `@Update` creates repository write methods

Spring Data MongoDB supports declaring updates directly on repositories using `org.springframework.data.mongodb.repository.Update`.

### 3.1. Complete repository

~~~java
// OrderRepository.java
package com.example.repositorywrites;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    // Pure read derived finder: Top2 genuinely limits read results.
    List<OrderDocument>
        findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
            String tenantId, String state
        );

    Page<OrderDocument> findByTenantIdAndState(
        String tenantId, String state, Pageable pageable
    );

    // Derived UPDATE: every document matching tenantId and state
    // has attempts incremented without loading entities first.
    @Update("{ '$inc': { 'attempts': ?2 } }")
    long findAndIncreaseAttemptsByTenantIdAndState(
        String tenantId, String state, int amount
    );

    // Misleading signature: Top2 does NOT limit the update.
    @Update("{ '$set': { 'state': ?2 } }")
    long findTop2ByTenantIdAndState(
        String tenantId, String currentState, String nextState
    );

    // Names starting with update require @Query to declare the predicate.
    @Query("{ 'tenantId': ?0, 'state': ?1 }")
    @Update("{ '$set': { 'state': ?2 } }")
    long updateAllByTenantAndState(
        String tenantId, String currentState, String nextState
    );
}
~~~

In this interface:

- `findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc` **has no `@Update`**: this is a genuine finder, reading only two documents in the specified order.
- `findAndIncreaseAttemptsByTenantIdAndState` has `@Update`: the `ByTenantIdAndState` portion builds the predicate; the `$inc` expression defines the write.
- `findTop2ByTenantIdAndState` has `@Update`: despite `Top2` in the name, it still updates **every** matching document.
- `updateAllByTenantAndState` uses both `@Query` and `@Update`: the filter is explicitly given in JSON rather than derived from the `update` prefix.

### 3.2. Why do update method names still start with `find`?

In Spring Data MongoDB, an update method **relying on a derived query** uses the `find...By...` naming structure to form the predicate. The official documentation states that methods starting with `update...`, such as `updateAllByLastname(...)`, are only valid when paired with an explicit `@Query` specifying the criteria.

~~~java
// Valid: derives criteria using the derived-query prefix find.
@Update("{ '$inc': { 'attempts': 1 } }")
long findAndIncrementAttemptsByState(String state);

// Valid: supplies explicit criteria, allowing updateAllBy... naming.
@Query("{ 'state': ?0 }")
@Update("{ '$inc': { 'attempts': 1 } }")
long updateAllByState(String state);

// Do not name a method without @Query expecting auto-derived update:
// long updateAllByState(String state);
~~~

In a real repository, avoid declaring two methods with identical names and parameter signatures. The snippet above illustrates naming rules; you can add these methods to `OrderRepository` provided they do not conflict with existing ones.

### 3.3. `@Update` defines the update, not a result page

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId,
    String state,
    int amount
);
~~~

Call:

~~~java
long modified = repository
    .findAndIncreaseAttemptsByTenantIdAndState(
        "t01", "NEW", 1
    );
// Against initial data: modified == 3.
~~~

Conceptually equivalent BSON predicate:

~~~javascript
{ tenantId: "t01", state: "NEW" }
~~~

BSON update:

~~~javascript
{ $inc: { attempts: 1 } }
~~~

Thus `o401`, `o402`, and `o403` all have `attempts` incremented by one. There is no `findTop2` or `PageRequest` step inside this method selecting a subset.

## 4. The `Top` and `First` trap on `@Update` methods

### 4.1. Read query with `Top2`

~~~java
List<OrderDocument> earliest = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "t01", "NEW"
    );

// Against initial data: o401, o402.
~~~

This is a **read** query; `Top2` truly limits the number of returned entities. `OrderByCreatedAtAscIdAsc` establishes a deterministic order so the first two documents are well-defined.

### 4.2. Update with `Top2`

~~~java
long modified = repository.findTop2ByTenantIdAndState(
    "t01",
    "NEW",
    "REVIEW"
);

// Result against initial data: modified == 3, NOT 2.
~~~

The derived condition is `tenantId = t01` and `state = NEW`. No two-document limit applies to the write operation. After the call, the state of `o401`, `o402`, and `o403` all become `REVIEW`.

**Why is this dangerous?** If you name a method `findTop100By...` as a "100-record safety limit" in an operational tool while 1,000,000 documents actually match, the `@Update` command can update all one million documents.

### 4.3. `First` does not limit scope either

~~~java
// Trap demonstration; add to a repository only in test environments.
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findFirstByTenantIdAndState(String tenantId, String state);
~~~

With `@Update`, `First` does not guarantee "modify only the first document". Official documentation notes that **limiting keywords do not restrict update scope**. If you need to modify at most one document, pick an API with true **single-document update** semantics, such as `MongoTemplate.updateFirst` or fluent `.first()`.

### 4.4. Do not equate method names with terminal operation behavior

A name like `findFirstBy...` does not convert execution into MongoDB `updateOne()` when annotated with `@Update`. Always read the method declaration **together with its annotations** and return contract rather than just the English words in the name.

During code reviews, flag `@Update` methods whose names include `Top`, `First`, `Page`, `Limited`, or `Recent`. If limiting is genuinely required, change the **execution strategy**, not merely the name.

## 5. Do `Pageable`, `Page`, `Slice`, and `Limit` limit updates?

### 5.1. Pagination on finders

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<OrderDocument> page = repository.findByTenantIdAndState(
    "t01",
    "NEW",
    PageRequest.of(
        0,
        2,
        Sort.by(Sort.Order.asc("createdAt"),
                Sort.Order.asc("id"))
    )
);

// page.getContent(): o401, o402.
// page.getTotalElements(): 3, while data is unchanged.
~~~

For finders, `Pageable` supplies `offset`, `limit`, and `sort` to the read query. `Page` also carries total count metadata, potentially running a count query. `Slice` is used when you only need to know if another page exists; both remain **read-result consumption mechanisms**.

### 5.2. Do not apply `Pageable` as a write quota

For repository `@Update`:

> You cannot restrict the number of updated documents by "passing a page" or using limiting keywords.

Therefore, do not write workflows like "pass `PageRequest.of(0, 10)` into an update method to guarantee only 10 records are modified". Depending on signature and framework version, that parameter/return combination may be rejected or fail to behave as intended; **even if accepted, pagination does not become a safe update limit**.

~~~java
// WRONG reasoning, never rely on this as a safety contract:
// @Update("{ '$set': { 'state': 'REVIEW' } }")
// long findByTenantIdAndState(
//     String tenantId, String state, Pageable pageable);
//
// Do not expect pageable to cap the number of written documents.
~~~

`Pageable`, `Sort`, `Top`/`First` keywords, and `Limit` parameters are great tools **for read query methods**. Do not carry their contract over to repository update methods where the update documentation specifies separate rules.

### 5.3. Why doesn't an update method return `Page<OrderDocument>`?

An update command typically does not re-read and materialize every modified entity. With `@Update`, supported return types are `void` or **numeric types** for the modified document count. It is not a query returning `Page<OrderDocument>`.

If an API needs to return the list of orders just transitioned, design an **appropriate read step or find-and-update operation**, keeping in mind data can change between write and read.

## 6. Return value: **modified** document count, not an ID set

A repository update method can return `void`:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
void findAndMarkReviewByTenantIdAndState(
    String tenantId, String state
);
~~~

or return `long`:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkReviewCountByTenantIdAndState(
    String tenantId, String state
);
~~~

Under the Spring Data MongoDB contract, the numeric type represents the **modified document count**. With an `$inc` `@Update`, every matching document with a valid numeric field changes; the returned number usually matches the matching count in the fixture.

However, **matched ≠ modified** in MongoDB:

~~~javascript
// Document o404 already has state: "PAID".
orders.updateOne(
  { _id: "o404" },
  { $set: { state: "PAID" } }
);
// matchedCount = 1; modifiedCount = 0.
~~~

Consequently:

- A `0` returned from a numeric repository update does not distinguish "no document matched" from "document matched but BSON did not change".
- A `3` does not tell you the list of modified IDs, update order, or total array elements affected.
- If the entity has `@Version` and mapped operations auto-increment version, version may change even if `$set` repeats an existing value; verify actual behavior on your Spring Data version.
- With an unacknowledged write concern, do not rely on counts to assert business outcomes.

### 6.1. When you need both matchedCount and modifiedCount

Use `MongoTemplate` to obtain `UpdateResult`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

UpdateResult result = template.updateMulti(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Write was not acknowledged");
}

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

`MongoTemplate.updateMulti` also updates **all matching documents** and returns richer metadata; it does not limit to N unless you implement a subset selection strategy yourself.

## 7. Combining `@Query` and `@Update` to control scope

Every document matching the filter is an update target, so **writing accurate filters** matters far more than putting a limiting keyword in the method name.

### 7.1. Query derived from properties

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId,
    String state,
    int increment
);
~~~

Spring Data derives criteria from `TenantIdAndState`; `?2` binds the third method parameter, using 0-based parameter indexing.

### 7.2. Explicit query with `@Query`

~~~java
@Query("{ 'tenantId': ?0, 'state': ?1 }")
@Update("{ '$set': { 'state': ?2 } }")
long updateAllByTenantAndState(
    String tenantId,
    String previousState,
    String nextState
);
~~~

Here the `updateAllBy...` prefix is permitted thanks to the explicit `@Query`. `@Query` determines **which documents match**; `@Update` determines **the write operation**.

In both cases, if the query matches 3 orders, the update affects **3 orders**, not a page inferred from the method name.

### 7.3. Why must tenant be included in the filter?

In the fixture, `state=NEW` has four orders: `o401`, `o402`, `o403`, and `o405`. If a method filters only by state:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkByState(String state);
~~~

then calling `findAndMarkByState("NEW")` can modify order `o405` belonging to tenant `t02`. Adding `Top2` **does not protect** against this.

In multi-tenant systems, the tenant must be extracted/verified from an authenticated user context and **included in every write predicate**. Do not treat an arbitrary client-supplied `tenantId` as sufficient authorization.

### 7.4. A status condition also prevents overwrites

If only `NEW` orders are allowed to transition to `REVIEW`, place `state=NEW` inside the filter instead of reading status first and updating later:

~~~javascript
orders.updateMany(
  { tenantId: "t01", state: "NEW" },
  { $set: { state: "REVIEW" } }
);
~~~

MongoDB evaluates the condition when executing the update; for each individual document, the write is atomic. A client that already moved `o402` to another state before the update will no longer match `state=NEW`. This does not turn the whole batch into a single atomic transaction, yet it prevents invalid writes per document at update time.

## 8. `@Update` with parameters, SpEL, and aggregation pipelines

### 8.1. Direct value binding

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

`?2` is bound from Java parameter `amount`. Never inject raw user input into JSON queries/updates via string concatenation, as it creates syntax risks, type mismatches, and loss of command control.

### 8.2. Use SpEL only when truly needed

Spring Data MongoDB supports SpEL parameters in `@Update`, e.g., equivalently:

~~~java
@Update("{ '$inc': { 'attempts': ?#{[2]} } }")
long findAndIncreaseUsingExpressionByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

SpEL makes expressions more flexible, though harder to review. When you only need to bind a simple parameter, `?2` is clearer and easier to test.

### 8.3. Repository update pipelines

For logic computing a new value from an existing value, `@Update` provides a `pipeline` attribute:

~~~java
@Update(pipeline = {
    "{ '$set': { 'attempts': { '$add': [ '$attempts', ?2 ] } } }"
})
long findAndRecalculateAttemptsByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

Here MongoDB computes `attempts + amount` for **every matching document**. Aggregation pipeline updates do not alter scope rules: they still apply to **all documents** selected by the query method.

When using pipelines, verify MongoDB version support, input BSON types, and missing/null handling rules; a non-numeric `attempts` value can make the expression fail. For simple numeric increments, `$inc` is usually more concise.

### 8.4. Does not automatically emit lifecycle events

Spring Data MongoDB documentation explicitly states: **repository update methods do not emit persistence/mapping lifecycle events**. Therefore:

- Do not assume `BeforeConvertCallback`, `BeforeSaveCallback`, or listeners run as in an entity save flow.
- Do not use `@Update` as a shortcut around audit/validation logic that currently lives only in entity callbacks.
- If audit/outbox writes are needed, design dedicated operations with transactions or appropriate guarantees.

`@Update` is a **query-based document update**, not "load all entities, invoke setters, then `repository.saveAll`".

## 9. When you truly want to update at most one document

If the goal is "update **any single** NEW order for the tenant", use `MongoTemplate.updateFirst(...)`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

UpdateResult result = template.updateFirst(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

`updateFirst` modifies at most **one document**, though if the filter matches multiple documents, **you should not rely on guessing which one**. When targeting one specific ID, add the `id` condition:

~~~java
Query byIdAndState = Query.query(
    Criteria.where("id").is("o401")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
);

UpdateResult result = template.updateFirst(
    byIdAndState,
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

### 9.1. Fluent API with `first()` and `all()`

~~~java
// At most one document:
UpdateResult one = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(new Update().set("state", "REVIEW"))
    .first();

// Every matching document:
UpdateResult many = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(new Update().set("state", "REVIEW"))
    .all();
~~~

These two snippets are **two independent comparison branches**—do not run them back-to-back on the same fixture expecting the second branch to still see `NEW` orders. `first()` and `all()` are **terminal operations of the fluent API** that genuinely govern single- vs. multi-document scope, unlike the `First` keyword in an `@Update` repository method name.

### 9.2. Selecting the oldest document with sorting

A requirement to "claim the oldest NEW order" is more than updating an arbitrary document. On MongoDB servers **prior to 8.0**, `MongoTemplate.updateFirst` does not support sorting to pick the target document; use `findAndModify`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query oldest = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);
oldest.with(Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
));

OrderDocument claimed = template.findAndModify(
    oldest,
    new Update().set("state", "PROCESSING"),
    FindAndModifyOptions.options().returnNew(true),
    OrderDocument.class
);
~~~

Against the initial fixture, `o401` is t01's oldest NEW order. `findAndModify` finds and updates one document in **the same operation**, reducing races between reading the first document and writing later. Include `id` as a tie-breaker when multiple documents share the same `createdAt`.

Note: newer MongoDB versions may support sorting for certain single-document updates; verify your driver, server, and Spring Data versions in practice. `findAndModify` remains useful whenever you need the pre- or post-update document returned.

## 10. When business rules allow updating only N documents

Concrete example:

> In a single job run, select only the **2 oldest NEW orders** of tenant t01 to transition to REVIEW.

Repository `@Update` has no safe "limit 2" option for this requirement. Two common patterns exist.

### 10.1. Approach A: read N IDs, then update that ID set

Step 1 — use a `Top2` finder, **solely to select IDs**:

~~~java
List<OrderDocument> selected = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "t01", "NEW"
    );

List<String> ids = selected.stream()
    .map(OrderDocument::getId)
    .toList();
// Initial data: ["o401", "o402"].
~~~

Step 2 — build a **write query with `id IN (...)`**:

~~~java
if (!ids.isEmpty()) {
    Query selectedIds = Query.query(
        Criteria.where("id").in(ids)
            .and("tenantId").is("t01")
            .and("state").is("NEW")
    );

    UpdateResult result = template.updateMulti(
        selectedIds,
        new Update().set("state", "REVIEW"),
        OrderDocument.class
    );

    long modified = result.getModifiedCount();
    // On an unchanged fixture: modified == 2.
}
~~~

Key takeaway: the limit of N happens in the **ID-selection step**, and the write step is constrained to **only those selected IDs**. Never pass `Pageable` to an `@Update` method assuming the server will cap the updates.

#### Can we still write through a repository?

You can declare a `@Query` + `@Update` method accepting only the selected IDs:

~~~java
// Add to OrderRepository if keeping writes on the repository API.
@Query("{ 'tenantId': ?0, 'state': ?1, '_id': { '$in': ?2 } }")
@Update("{ '$set': { 'state': ?3 } }")
long updateSelectedIds(
    String tenantId,
    String currentState,
    List<String> selectedIds,
    String nextState
);
~~~

Usage:

~~~java
if (!ids.isEmpty()) {
    long modified = repository.updateSelectedIds(
        "t01", "NEW", ids, "REVIEW"
    );
}
~~~

In this pattern, the `@Update` operation still updates **all documents matching the filter**, but **the filter itself has been narrowed to a specific ID list**. It is the ID list that constrains the result set, not a `Top2` keyword on the update method.

#### Limitation of Approach A: race between read and write

Selecting IDs and updating are **two separate operations**:

1. At read time, `o401` and `o402` are the two oldest NEW orders.
2. Before the update runs, another writer might transition `o401` to PAID, or insert an even older NEW order.
3. The update query requiring `state=NEW` will not modify `o401` once its state changed.
4. As a result, only **one** order may be modified, and the query will not automatically pick another order to compensate.

This behavior is acceptable when the goal is "only touch the orders selected during evaluation". It does **not** guarantee "always claim N unclaimed orders" under high contention.

If business rules require set-wide atomicity or selecting the N oldest at a consistent snapshot, design an appropriate transaction or consistency condition.

### 10.2. Approach B: loop `findAndModify` to claim one document at a time

For work queues, a common pattern is claiming **each document in an atomic operation**:

~~~java
package com.example.repositorywrites;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderClaimService {
    private final MongoTemplate template;

    public OrderClaimService(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> claimOldest(String tenantId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        List<OrderDocument> claimed = new ArrayList<>();

        for (int i = 0; i < limit; i++) {
            Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                    .and("state").is("NEW")
            );
            query.with(Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id")
            ));

            OrderDocument next = template.findAndModify(
                query,
                new Update().set("state", "PROCESSING"),
                FindAndModifyOptions.options().returnNew(true),
                OrderDocument.class
            );

            if (next == null) {
                break; // No more NEW orders left to claim.
            }
            claimed.add(next);
        }
        return List.copyOf(claimed);
    }
}
~~~

On a single run against the initial fixture, `claimOldest("t01", 2)` returns `o401` and `o402` transitioned to PROCESSING; `o403` remains NEW.

**Advantages:** the `state=NEW` condition and the state transition execute together on **each document**. When two workers claim concurrently, a document already moved to PROCESSING no longer matches the other worker's `state=NEW`. This is a much better fit for **job claiming** than "load a page then write back".

**Limitations:** a loop of N iterations does not form a single atomic transaction over all N documents. If an error occurs mid-loop, previously claimed documents remain in PROCESSING. You need timeouts/reclaim/leases or retries per queue design; transactions are a separate decision.

### 10.3. Comparing the two ways to limit N

| Criterion | Select IDs then `updateMulti` | Loop `findAndModify` |
| --- | --- | --- |
| Maximum documents | Never exceeds selected IDs | Never exceeds loop limit |
| Round trips | One read + one main write | Up to N find-and-modify calls |
| Status precondition at write time | Yes if included in update query | Yes within each atomic operation |
| When an order changes state before write | May modify fewer than N | Can claim the next eligible order |
| Returns modified documents? | Requires separate query/extra design | `findAndModify` can return the document |
| Multi-document all-or-nothing? | Not by default | Not by default |
| Best suited for | Batch updating a selected set | Worker queue / claiming jobs one by one |

Do not optimize round trips by stripping away business preconditions. For large jobs, use batching, checkpoints, indexes, transactions, or a dedicated queue mechanism as required.

## 11. `@Version` neither limits scope nor protects every operation automatically

Suppose the entity adds:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

`@Version` supports optimistic locking in appropriate entity-aware operations. However, a repository update method remains a **query update** affecting the matching document set.

### 11.1. Three things to distinguish

1. **Scope:** which documents the query selects, e.g., `tenantId=t01 AND state=NEW`.
2. **Version bump:** Spring Data can auto-increment version when a mapped update does not specify version in the update definition.
3. **Optimistic check:** to protect a version the user previously read, the query must contain the **expected version value**.

Auto-incrementing version does not turn `findTop2By...` into an update of at most two documents. Nor does it guarantee the query contains the version precondition the client expects.

### 11.2. Example checking expected version with `MongoTemplate`

With an entity having `@Version`, suppose order `o401` is at version 3:

~~~java
Query query = Query.query(
    Criteria.where("id").is("o401")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
        .and("version").is(3L)
);

UpdateResult result = template.updateFirst(
    query,
    new Update().set("state", "REVIEW"),
    VersionedOrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order missing, changed state, or stale version"
    );
}
~~~

`VersionedOrderDocument` is an **illustrative entity variant containing `@Version` and matching collection mapping**, not the class defined in Section 2.2. This snippet focuses on explaining optimistic locking filters; when applying it, declare the real entity and prepare versioned fixtures.

If you previously held an entity at version 3, updating by a query containing only `_id` **has no way to know** you wanted to protect version 3. When updating individual versioned aggregates, use `repository.save(entity)` or a version-conditioned update command by design.

### 11.3. Repository updates do not run entity callbacks

Do not rely on `@BeforeSave`/entity callbacks to enforce version checks, auditing, or access control for `@Update`. Official documentation states repository update methods do not emit lifecycle events. Critical rules must live in the filter, update, or tested service/transaction logic.

## 12. Atomicity: one document vs. multiple documents

MongoDB guarantees a write operation on **one document** is atomic. Yet a repository `@Update` can modify multiple documents.

~~~text
Repository @Update:
  filter tenant=t01,state=NEW
       |
       +-- o401: atomic update at document level
       +-- o402: atomic update at document level
       +-- o403: atomic update at document level

Does NOT mean o401+o402+o403 commit/rollback together as a transaction.
~~~

Therefore, do not assume:

> One Java call `repository.findAndMark...()` runs once, so all 3 documents change simultaneously.

If a multi-document operation is interrupted, some documents may be written while others are not. If all-or-nothing behavior is mandatory, you need MongoDB transactions and a properly configured `MongoTransactionManager`.

### 12.1. Transaction example through a service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewBatchService {
    private final OrderRepository repository;

    public ReviewBatchService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public long markAllNewForTenant(String tenantId) {
        return repository.updateAllByTenantAndState(
            tenantId, "NEW", "REVIEW"
        );
    }
}
~~~

The example above **only works as a transaction** when `MongoTransactionManager` is configured, template/repository share the `MongoDatabaseFactory`, and MongoDB runs on a transaction-capable topology. Otherwise, merely adding the annotation does not make writes all-or-nothing.

Note: transactions also carry lock, resource, duration, and retry overhead. Do not blindly wrap an update of millions of documents in a long-running transaction merely because a repository method modifies many documents.

### 12.2. Idempotency and retries

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkReviewByTenantIdAndState(
    String tenantId, String state
);

@Update("{ '$inc': { 'attempts': 1 } }")
long findAndIncreaseByTenantIdAndState(
    String tenantId, String state
);
~~~

If both calls are retried after a timeout:

- `$set(state, REVIEW)` typically leaves the value unchanged when re-applied with the same state (aside from version/audit or other conditions).
- `$inc(attempts,1)` is **not idempotent**: re-executing it can increment a second time.

When matching document counts are large, duplicate retry effects become even more severe. Design status preconditions, idempotency keys, or event/batch markers to avoid unintentionally re-applying increments or decrements.

## 13. Choosing indexes and measuring the impact of broad updates

With filter:

~~~javascript
{ tenantId: "t01", state: "NEW" }
~~~

index:

~~~javascript
orders.createIndex({
  tenantId: 1,
  state: 1,
  createdAt: 1,
  _id: 1
});
~~~

can support both finding documents by tenant/state and finders sorting by timestamp. However, an index **does not turn `Top2` on an update method into an N-document cap**.

### 13.1. Why are multi-document updates still expensive?

- MongoDB must locate every document matching the filter.
- Each document may require updating data and affected indexes.
- Write load can trigger replication lag, lock contention, and higher latency for other traffic.
- `$inc` or complex pipelines incur per-document evaluation overhead.
- When a filter omits tenant or state, the affected count can spike sharply.

Monitor modified document counts, write durations, p95/p99 latency, write conflicts, replication, I/O cost, and collection/index health.

### 13.2. Estimating scope before writing

~~~javascript
const filter = { tenantId: "t01", state: "NEW" };

const candidates = orders.countDocuments(filter);
print({ candidates });
// Initial fixture: 3.
~~~

This is a useful scale check before writing, **not a guarantee** that the update will affect that exact count: documents can change between counting and updating. To prevent updating more than N records, use an ID-selection/claim strategy as in Section 10 rather than:

~~~text
if (count <= 2) {
    repository.updateAllBy...();
}
~~~

Two separate commands introduce a race condition. For risky operations, restrict access permissions, include dry-run/operational approval, enforce tight filters, and prepare audit/rollback strategies.

### 13.3. `explain` checks the plan, not a substitute for update tests

~~~javascript
orders.find({ tenantId: "t01", state: "NEW" })
  .sort({ createdAt: 1, _id: 1 })
  .explain("executionStats");
~~~

When inspecting indexes, look at `winningPlan`, `totalKeysExamined`, and `totalDocsExamined`. This analyzes only the **candidate lookup step**, not the full write cost. Even if a `find` query has `limit(2)` and runs instantaneously, a separate `@Update` command **can still modify all matching documents**.

## 14. Reactive repositories: publishers do not limit scope

In WebFlux applications, Spring Data MongoDB offers `ReactiveMongoRepository`. A reactive update method typically uses a publisher returning a numeric result:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Update;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Update("{ '$inc': { 'attempts': ?2 } }")
    Mono<Long> findAndIncreaseAttemptsByTenantIdAndState(
        String tenantId, String state, int amount
    );
}
~~~

`Mono<Long>` executes when subscribed; the emitted number represents the modified document count under the update method contract. **Reactive does not alter scope semantics**: every matching document remains a target.

If you want controlled single- or multi-document updates, use `ReactiveMongoTemplate`:

~~~java
Mono<com.mongodb.client.result.UpdateResult> one =
    reactiveTemplate.update(OrderDocument.class)
        .matching(
            Criteria.where("tenantId").is("t01")
                .and("state").is("NEW")
        )
        .apply(new Update().set("state", "REVIEW"))
        .first();

Mono<com.mongodb.client.result.UpdateResult> all =
    reactiveTemplate.update(OrderDocument.class)
        .matching(
            Criteria.where("tenantId").is("t01")
                .and("state").is("NEW")
        )
        .apply(new Update().set("state", "REVIEW"))
        .all();
~~~

These are two **independent illustrative branches**; do not subscribe to them sequentially on one fixture expecting the second to match the original state. In reactive transactions, use an appropriate `ReactiveMongoTransactionManager`/`TransactionalOperator`; never call `block()` on an event loop.

## 15. Mandatory integration tests for the `Top2` trap

If you merely mock `OrderRepository` to return `2`, the test **will fail to catch** that Spring Data actually sends a broad update to MongoDB. Write integration tests against a real MongoDB (e.g., Testcontainers) to verify:

1. There are **three** matching documents for the tenant/state.
2. The `findTop2...` `@Update` method returns a modified count of **3**.
3. After execution, all three documents changed state.
4. Documents of another tenant remained unchanged.
5. A `Top2` finder without `@Update` indeed returns only two documents.

### 15.1. Test implementation with `@DataMongoTest`

Example running in a Spring Boot app configured with a **dedicated test MongoDB**:

~~~java
package com.example.repositorywrites;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class RepositoryUpdateScopeTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void topKeywordDoesNotLimitRepositoryUpdate() {
        List<String> ids = List.of(
            "fixture-rw004-a",
            "fixture-rw004-b",
            "fixture-rw004-c",
            "fixture-rw004-other"
        );

        var collection = template.getDb()
            .getCollection("orders_repository_writes_demo_004");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(1))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(2))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(3))
                    .append("tenantId", "another-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0)
            ));

            long modified = repository.findTop2ByTenantIdAndState(
                "test-tenant-004", "NEW", "REVIEW"
            );

            assertThat(modified).isEqualTo(3L);

            long reviewed = collection.countDocuments(
                Filters.and(
                    Filters.in("_id", ids.subList(0, 3)),
                    Filters.eq("state", "REVIEW")
                )
            );
            assertThat(reviewed).isEqualTo(3L);

            Document other = collection.find(
                Filters.eq("_id", ids.get(3))
            ).first();
            assertThat(other).isNotNull();
            assertThat(other.getString("state")).isEqualTo("NEW");
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

The test creates and cleans up **exactly four fixture IDs** inside an isolated test database. Do not share these IDs with other tests running in parallel. The test verifies `@Update` behavior between Spring Data MongoDB and real MongoDB; it does not replace tenant authorization, transaction, or multi-million-document performance tests.

### 15.2. Adding a control test for the `Top2` finder

Before changing state, insert three documents sharing tenant/state with distinct `createdAt` values and call:

~~~java
List<OrderDocument> two = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "test-tenant-004", "NEW"
    );
assertThat(two).hasSize(2);
~~~

This snippet is only meaningful when the fixture includes valid `createdAt` values and the update has not yet run. If executed against the Section 15.1 fixture (which lacks `createdAt`), it can still limit results to two but will not demonstrate date ordering. To test sorting, include BSON Dates with distinct timestamps during insertion and assert the exact IDs.

### 15.3. Test matrix for real systems

| Scenario | What to verify |
| --- | --- |
| Derived `@Update` without `Top` | Every matching document is modified |
| `@Update` with `Top2` | Still modifies every matching document, not just two |
| Finder `Top2` without `@Update` | Reads at most two documents |
| Finder accepting `Pageable` | Reads the expected page, unrelated to separate updates |
| Numeric update method | Returns modified count, not an ID list |
| Update with no matching document | Does not insert; modified count equals 0 |
| `@Query` + `@Update` | Filter accurately checks tenant/state/ID |
| Select two IDs then update | Only that ID set is a write candidate |
| State changes between ID selection and update | Does not overwrite documents whose state changed |
| Calling `findAndModify` claim twice | Each call grabs one document, no duplicate claim |
| `$inc` retry | Detects risk of applying the update twice |
| Lifecycle callbacks | Do not assume entity callbacks fire on repository updates |
| `@Version` | Do not assume optimistic lock from a versionless query |
| Reactive `@Update` | Publisher is subscribed; scope remains all-matching |

## 16. Common mistakes

| Symptom / assumption | Why it is wrong | Resolution |
| --- | --- | --- |
| `findTop2...` with `@Update` updates only two documents | `Top2` limits finders, not repository updates | Read two IDs then update by ID, or `findAndModify` one by one |
| `findFirst...` with `@Update` becomes `updateOne` | Limiting keywords do not change all-match update semantics | Use `MongoTemplate.updateFirst`/fluent `first()` |
| Passing `Pageable` limits update count | Pagination is unsupported as a scope limiter on `@Update` | Do not rely on `Pageable`; change write strategy |
| `Page<OrderDocument>` is a natural return type for `@Update` | Updates return `void` or modified count, not a page of entities | Separate reads/writes, pick proper API |
| `updateAllBy...` auto-derives a predicate | `update` prefix is not a default derived-update schema | Add explicit `@Query` alongside `@Update` |
| `long modified=0` means no document matched | Document may have matched with no change needed | Use `MongoTemplate.UpdateResult` and inspect data |
| Omitting tenant because "only updating Top2" | Query can modify another tenant's documents | Include verified tenant in every write predicate |
| Treating `repository.saveAll(...)` as equivalent to `@Update` | `save` has different mapping and callback/version semantics | Choose API based on consistency and side-effect needs |
| `@Update` auto-triggers entity audit callbacks | Repository updates do not emit persistence/mapping events | Build separate audit/transaction logic |
| Having `@Version` rejects all stale writers | Query updates ignore client-read version unless constrained | Use queries with expected version or entity `save` |
| Counting first via `countDocuments` guarantees at most N | Race exists between count and update | Select IDs then update, or atomic claim |
| A repository method updating many documents is a transaction | Multi-updates are not automatically all-or-nothing | Configure transactions or batch with retries |
| Unindexed update runs fast in small tests | Large workloads scan too many documents | Design indexes, measure query plans and write times |
| Reactive `Mono<Long>` emits one item so it updates one doc | Single-item publisher emits the **modified count**, not scope | Inspect filter and actual operation type |

## 17. Safe review checklist for repository write methods

Before approving an `@Update` method, verify:

1. **Identify the operator:** `$set`, `$inc`, `$push`, pipeline, or other? Is it idempotent?
2. **Read the predicate:** which documents will the properties after `By` or the `@Query` JSON match?
3. **Distrust limiting keywords:** `Top`, `First`, and `Pageable` do not cap repository update scope.
4. **Audit tenant/authorization:** does the filter include all required permission and business boundaries?
5. **Estimate volume:** how many documents can match in real data; is an N-cap required?
6. **If N is needed:** select IDs then conditionally update, or use `findAndModify` to claim one record at a time.
7. **Check return type:** `void` or modified count; when matched vs. modified must be distinguished, use `MongoTemplate.UpdateResult`.
8. **Check version/auditing:** does the query-based operation skip callbacks or lack expected version?
9. **Evaluate transactions/retries:** multi-document updates can be interrupted; `$inc` cannot be blindly retried.
10. **Measure and test:** integration tests with **more matching documents than N in the method name**, verifying both modified count and untouched out-of-scope data.

## 18. Practice exercises

The exercises below assume collection `orders_repository_writes_demo_004` starts in the initial state from Section 2. Each exercise is an independent scenario.

### Exercise 1 — Read or write?

Given two methods:

~~~java
List<OrderDocument> findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
    String tenantId, String state
);

@Update("{ '$set': { 'state': 'REVIEW' } }")
long findTop2ByTenantIdAndState(
    String tenantId, String state
);
~~~

**Question:** With `("t01", "NEW")`, how many orders does each method affect?

**Answer:** The finder returns **two** orders (`o401`, `o402`); the update method modifies **all three** orders (`o401`, `o402`, `o403`). `Top2` does not limit updated document count.

### Exercise 2 — Can `Pageable` save it?

A developer adds `PageRequest.of(0, 2)` to an update method as a safety cap. Is this valid?

**Answer:** No. Under the MongoDB repository update method contract, pagination/limiting keywords **cannot be used to restrict update scope**. Use a finder to collect IDs or a dedicated single-document update/claim operation.

### Exercise 3 — Counting modified documents

Call:

~~~java
long modified = repository
    .findAndIncreaseAttemptsByTenantIdAndState(
        "t01", "NEW", 1
    );
~~~

**Answer:** On the initial fixture, `modified=3`. `attempts` for `o401`, `o402`, and `o403` go from 0/1/2 to 1/2/3 respectively; `o405` in the other tenant remains untouched.

### Exercise 4 — Why is `@Query` required?

~~~java
@Query("{ 'tenantId': ?0, 'state': ?1 }")
@Update("{ '$set': { 'state': ?2 } }")
long updateAllByTenantAndState(
    String tenantId, String currentState, String nextState
);
~~~

**Answer:** `@Query` defines the predicate because the method name starts with `update`, not the derived-query prefix `find`. `@Update` defines the update operator. Every document matching the query is an update candidate.

### Exercise 5 — Selecting the N oldest orders

Requirement: modify only the two oldest NEW orders of t01. Name two options.

**Reference answer:** (1) `Top2` finder sorted by `createdAt ASC, id ASC` to get IDs, followed by `updateMulti` with `id IN IDs`, tenant, and state. (2) Loop `findAndModify` with a deterministic sort to claim each document atomically. Both differ from putting `Top2` directly on `@Update`.

### Exercise 6 — Race between read and write

You selected `o401`/`o402`, but another writer just moved `o401` from NEW to PAID. What should the write query include?

**Answer:** Keep `id IN ["o401","o402"]` **and** `state=NEW` plus tenant. Then `o401` will not be overwritten; perhaps only `o402` gets modified. If the workflow strictly requires two orders, redesign with atomic claiming or a transaction as needed.

### Exercise 7 — Retrying `$inc`

A repository update increments `attempts` for all NEW orders of t01, and the request times out. Should you immediately retry?

**Answer:** Do not blindly retry `$inc`. The first attempt may have updated all three, and the retry would increment them a second time. You need idempotency/event markers or strong enough state preconditions to know whether the operation was already applied.

### Exercise 8 — Tenant protection

Why is `findTop2ByState("NEW")` annotated with `@Update` unsafe in a multi-tenant system?

**Answer:** Because it can modify **every NEW order across all tenants**, not merely two orders or the caller's tenant. Include an authenticated tenant in the query, verify authorization, and never use `Top2` as a security filter.

### Exercise 9 — `@Version` and optimistic locking

A client viewed an order at version 3. An `@Update` method filters only by `_id`. Does it reliably protect the client from stale updates?

**Answer:** No. You must put the expected version in the predicate or use an entity save mechanism with proper optimistic locking; framework auto-incrementing of version does not mean the old version was verified.

### Exercise 10 — Minimum test to expose the dangerous bug

To prove `Top2` does not limit `@Update`, how many matching documents must the test seed?

**Answer:** **More than two documents**, e.g. three. If a test seeds only two documents, both the false assumption "Top2 updates only two" and the true behavior "updates all three or fewer" produce the same result and hide the bug.

## References

- [Spring Data MongoDB — MongoDB-specific Data Manipulation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html): `@Update` contract, all matching documents, no limiting via `Page`/limiting keywords, numeric modified return type, `@Query` + `@Update` syntax, and no lifecycle events emitted.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): `Top`/`First`, `Pageable`, `Page`, `Slice`, `Limit`, and how derived finders limit read results.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): finders, derived queries, pagination, and query parameters.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `updateFirst`, `updateMulti`, fluent `first()/all()`, `findAndModify`, versioning, and `UpdateResult`.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): sessions, `MongoTransactionManager`, and transaction boundaries.
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `updateOne`, `updateMany`, and affected document counts.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomicity, multi-document write limits, and transactions.
- [MongoDB Manual — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/): choosing indexes for filters and sorts.
