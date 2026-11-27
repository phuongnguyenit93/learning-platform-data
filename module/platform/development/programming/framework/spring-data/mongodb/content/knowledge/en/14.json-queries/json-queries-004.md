# Configuring sort, collation, and hint Based on Version Capabilities

## 1. Purpose and Use Cases

In MongoDB, the same filter can return documents in different orders if no sort is specified. Even with `sort` applied, Vietnamese string ordering can differ from expectations if a language-specific comparison rule is not declared. At scale, MongoDB must also pick an appropriate index and execution plan; occasionally `hint` is needed to test a specific index.

In the **SPRING_DATA_MONGODB** module, we query MongoDB using `MongoRepository`, the `@Query` annotation, or `MongoTemplate`. This lesson belongs to the **JSON Queries** chapter and focuses on three query-attached options:

- **`sort`:** Result ordering, including tie-breaker keys for stable pagination.
- **`collation`:** Language- and strength-based string comparison rules, affecting both matching and ordering.
- **`hint`:** Directing MongoDB to use a specific index on supported operations, typically for diagnostics or when evidence proves a better plan.

Available APIs, annotations, and attributes vary across Spring Data MongoDB, MongoDB Java driver, and server versions. Alongside syntax, this lesson emphasizes **verifying version capabilities and the actual BSON sent**. Understanding these three options also helps evaluate indexes, pagination, testing, and performance diagnostics instead of tuning by guesswork.

After this lesson, you will be able to:

1. Write JSON queries and repositories with explicit sort order instead of relying on natural collection order.
2. Apply an appropriate `collation` for Vietnamese data and recognize its effect on indexes and comparisons.
3. Use `hint` by index name or key pattern in mongosh, then apply it via Spring Data when supported by your version.
4. Distinguish static `@Query` options from dynamic `Sort`/`Pageable` or programmatic `Query`.
5. Inspect `explain("executionStats")` and recognize cases where sorting misses an index or a hint degrades a query.

## 2. Sample Data and Three Query Needs

Suppose an order management system serves multiple stores, each with its own `tenantId`. Every business query must constrain to the authenticated user's tenant.

```javascript
db.orders.insertMany([
  {
    _id: "order-001",
    tenantId: "tenant-a",
    customerName: "An",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    totalAmountVnd: NumberLong("120000")
  },
  {
    _id: "order-002",
    tenantId: "tenant-a",
    customerName: "Ân",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    totalAmountVnd: NumberLong("150000")
  },
  {
    _id: "order-003",
    tenantId: "tenant-a",
    customerName: "Đức",
    status: "PAID",
    createdAt: ISODate("2026-11-19T10:00:00Z"),
    totalAmountVnd: NumberLong("250000")
  },
  {
    _id: "order-004",
    tenantId: "tenant-a",
    customerName: "Bình",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-20T07:00:00Z"),
    totalAmountVnd: NumberLong("200000")
  },
  {
    _id: "order-005",
    tenantId: "tenant-b",
    customerName: "An",
    status: "READY_TO_SHIP",
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    totalAmountVnd: NumberLong("500000")
  }
]);
```

This is illustrative data for a test environment, not a script to run as-is against a production collection. Three needs to solve:

| Code | Requirement | Filter | Sort and Options |
| --- | --- | --- | --- |
| Q1 | 20 newest ready-to-ship orders of a tenant | `tenantId + status` | `createdAt DESC, _id DESC` |
| Q2 | Tenant customer names in Vietnamese alphabetical order | `tenantId` | `customerName ASC, _id ASC`; Vietnamese collation |
| Q3 | Compare performance of two indexes for Q1 | Same as Q1 | Keep filter/sort, test hints one by one |

Q1 and Q2 are **real business queries**. Q3 is a **diagnostic activity**, not a sign that the application should hardcode hints onto every query.

## 3. Sort in MongoDB JSON Queries

### 3.1. Ascending and Descending Order

In MongoDB, `1` means ascending and `-1` means descending:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

With the sample data, Q1 yields `order-004`, `order-002`, `order-001`. The last two orders share the same `createdAt`, so order is broken by `_id DESC`.

**Why add `_id`?** Sorting only by `createdAt` does not guarantee consistent ordering for documents sharing the same timestamp. When paginating, a stable tie-breaker key avoids records shifting positions randomly between calls. Never treat unsorted return order as an application contract.

MongoDB also lets you sort on multiple fields, keeping in mind **key declaration order**: the first field is the primary sort criterion, and subsequent fields break ties when earlier keys are equal.

### 3.2. Sorting by Nested Fields

If documents contain `shippingAddress.city`, you can write:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ "shippingAddress.city": 1, _id: 1 });
```

Before applying, verify the actual BSON field name. If the Java domain renames it via `@Field("city_name")`, the physical path may be `shippingAddress.city_name`. In mongosh and raw JSON/BSON, always use the name **stored in the database**.

### 3.3. Missing Values, Null, and Mixed Types

Sorting by a field does not guarantee that field exists in every document. MongoDB has BSON comparison rules across types and values; documents missing the field or holding `null` may appear at positions unexpected by business logic.

When the application requires "orders with a valid creation time", enforce data constraints and handle documents missing `createdAt` instead of merely adding `sort`. In particular, mixing BSON Date and date Strings does not share the same sort semantics.

## 4. Sort in MongoTemplate and Repositories

### 4.1. Mapped Java Model

Java 17+ example:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String customerName,
    String status,
    Instant createdAt,
    long totalAmountVnd
) {}
```

Property `id` maps to BSON `_id`; remaining fields in this example share identical Java and BSON names. This model serves the sort/collation/hint lesson; real applications need validation, authorization, state transitions, and other invariants.

### 4.2. MongoTemplate: Query.with(Sort)

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchService {
    private final MongoTemplate mongoTemplate;

    public OrderSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<OrderDocument> readyToShip(String tenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is("READY_TO_SHIP")
        );
        query.with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ));
        query.limit(20);
        return mongoTemplate.find(query, OrderDocument.class);
    }
}
```

When `Query` runs with `OrderDocument.class`, mapping metadata translates property `id` to `_id`. If using `MongoTemplate.find(query, Document.class, "orders")` or the driver directly, do not assume Java field names will be translated the same way as with a domain type.

### 4.3. Repository: Static Sort in @Query

In Spring Data MongoDB versions supporting the `sort` attribute of `@Query`:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderQueueRepository
    extends Repository<OrderDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        sort = "{ 'createdAt': -1, '_id': -1 }"
    )
    List<OrderDocument> findQueue(
        String tenantId,
        String status
    );
}
```

Note: this method has no result count cap; it only demonstrates **static sort**. In production, supply `Pageable` or cap results per use case to avoid loading the entire queue.

`?0` and `?1` are **parameter placeholders** handled by the query annotation binding mechanism. Never concatenate user input strings to build JSON queries manually. `tenantId`/`status` must be in the query from the start so other tenants' data is never returned.

### 4.4. Repository: Dynamic Sort and Pageable

For flexible sorting needs, define a repository method accepting `Pageable`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderPageRepository
    extends Repository<OrderDocument, String> {

    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    Slice<OrderDocument> findQueue(
        String tenantId,
        String status,
        Pageable pageable
    );
}
```

In the service:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest page = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

var result = orderPageRepository.findQueue(
    authenticatedTenantId,
    "READY_TO_SHIP",
    page
);
```

`Slice` fits when you only need to know whether a next page exists rather than total record count; `Page` may issue an additional count query. Still, large offsets remain resource-intensive, so for very deep lists consider keyset/cursor pagination.

**Do not blindly mix static sort and dynamic sort and guess precedence.** When a method uses both `@Query(sort=...)` and `Sort`/`Pageable`, combination behavior can depend on the specific library version. Pick one clear source of ordering per query, inspect the executed BSON, and write integration tests.

## 5. Collation: Language-Aware String Comparison Rules

### 5.1. Why Default Sorting Falls Short for People's Names

Default binary comparison order (simple collation) does not always reflect user expectations when sorting Vietnamese names, uppercase/lowercase, or diacritics. MongoDB supports locale-based **collation**, letting you specify string comparison rules.

Example:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 });
```

`locale: "vi"` requests Vietnamese rules. `strength: 2` typically compares up to accent differences while ignoring case differences at that comparison level. Exact ordering should be verified with Vietnamese name fixtures, because `đ/Đ`, tone marks, vowel diacritics, and digraphs follow language-specific rules.

### 5.2. Common Collation Options

| Property | Example | Primary Meaning |
| --- | --- | --- |
| `locale` | `"vi"`, `"en"`, `"simple"` | Language/comparison rules; `simple` uses binary comparison |
| `strength` | `1`, `2`, `3` | Sensitivity distinguishing base letters, diacritics, and case across levels |
| `caseLevel` | `true` | Adds case sensitivity at lower strength levels |
| `numericOrdering` | `true` | Orders contiguous digit sequences numerically per ICU rules |
| `normalization` | `true` | Handles Unicode normalization forms under collation rules |

Example sorting `"Sản phẩm 2"` and `"Sản phẩm 10"`:

```javascript
db.products.find({ tenantId: "tenant-a" })
  .sort({ displayName: 1 })
  .collation({
    locale: "vi",
    numericOrdering: true
  });
```

With numeric ordering, numeric substrings are evaluated numerically within supported bounds, so `"2"` can sort before `"10"`. This is not an excuse to store monetary amounts or quantities as Strings; numeric business fields should use proper BSON numeric types.

### 5.3. Collation Also Affects Equality Comparisons

Collation does not only change sort order. It can change whether a **String comparison** considers two values equivalent:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  customerName: "An"
}).collation({
  locale: "vi",
  strength: 1
});
```

At low strength, some case or accent differences may be ignored under locale rules. This is very useful for user-friendly name lookup, but **should not be applied blindly to every field**, especially order codes, usernames, or identifiers requiring exact matching.

Two important caveats:

- A single collation normally applies to the **entire operation** within supported scope; you cannot set different strengths per field within one `find`.
- `$regex` does not share the same collation-based case-insensitivity semantics as collation-based equality. Do not assume a collated index automatically optimizes every regex query.

## 6. Choosing Indexes Compatible with Collation

### 6.1. Default Indexes vs. Collated Indexes Differ

A MongoDB index is created with a specific collation or inherits the collection's default collation. Example index serving Q2:

```javascript
db.orders.createIndex(
  { tenantId: 1, customerName: 1, _id: 1 },
  {
    name: "ix_orders_tenant_customer_vi",
    collation: { locale: "vi", strength: 2 }
  }
);
```

Query using the same rules:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 })
  .limit(20);
```

This is a **reasonable candidate** for MongoDB to fetch results in the desired order without an extra in-memory sort over a large dataset. Actual index choice, however, depends on the query planner, data distribution, and other indexes; always verify with `explain`.

### 6.2. Why Must Query and Index Match Collation?

An index on strings stores keys ordered under the collation active at index creation. If a query requests a different collation, MongoDB may be unable to use that index for certain string comparisons or sorts. In some cases, a **non-String prefix** of a compound index can still help the filter, which does not mean the String sort portion will be index-supported.

| Scenario | Expectation to Check |
| --- | --- |
| Query `locale: "vi", strength: 2`; index with same config | Can use the index for compatible string comparisons/sorts |
| Query simple; index uses `vi/strength: 2` | May fail to use the index portion for the desired string ordering |
| Query `vi/strength: 1`; index `vi/strength: 2` | Different rules; not automatically equivalent |
| Query with numeric filter and string sort | May partially leverage index depending on key pattern; inspect plan |

If you create a new index with the same key pattern but a different collation, you must assign a distinct index name and check server/version constraints. Every index costs storage and write overhead; do not create every combination of locale/strength merely because the app lets users pick languages.

**Unique indexes are affected too:** A uniqueness constraint under collation can treat certain distinct Strings as equivalent. Before applying a collated unique index to emails or codes, define exact case/diacritic sensitivity policies, inspect existing duplicate data, scope by tenant, and check sharding requirements if applicable.

## 7. Hint: Directing the Server to Use an Index

### 7.1. Hint Is Neither Sort Nor Index Creation

`hint` gives the server an instruction for index selection on supported operations. It **does not create indexes**, does not guarantee the index fits the filter or sort, and does not replace collation.

Candidate index for Q1:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "ix_orders_tenant_status_recent" }
);
```

Run the query normally:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Force a known index by **name**:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20);
```

Or by the corresponding **key pattern** in mongosh:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint({ tenantId: 1, status: 1, createdAt: -1, _id: -1 })
  .limit(20);
```

Hint forms can differ across driver APIs, operation types, and versions. In Spring Data, prefer explicitly managed **index names** if the API accepts hint as a String; for key patterns, verify how your version's API interprets JSON strings.

### 7.2. When Should Hint Be Used?

Legitimate scenarios:

1. **Diagnostics:** Comparing `explain("executionStats")` between planner-chosen index selection and a forced index.
2. **Evidenced regression:** A critical query shape where the planner consistently chooses a poor plan under a specific data distribution.
3. **Index migration validation:** Evaluating a new index before deciding to keep, replace, or drop an old one.

Situations where you **should not** default to hints: wanting "a guaranteed fast query", not having measured on representative data, frequently renaming indexes, or serving multiple tenants with very different data distributions.

A bad hint can increase keys/documents scanned, force an expensive sort, or error out if the named index does not exist or violates operation constraints. Maintain tests and operational procedures whenever renaming or dropping an index referenced by a hint.

## 8. MongoTemplate: Configuring sort, collation, and hint on One Query

In Spring Data MongoDB versions providing `Query.withHint(...)` and `Query.collation(...)`, all three can be configured at the `Query` level:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class CustomerNameSearch {
    private final MongoTemplate template;

    public CustomerNameSearch(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> sortedCustomers(String tenantId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
        );
        query.with(Sort.by(
            Sort.Order.asc("customerName"),
            Sort.Order.asc("id")
        ));
        query.collation(
            Collation.of("vi")
                .strength(Collation.ComparisonLevel.secondary())
        );
        query.withHint("ix_orders_tenant_customer_vi");
        query.limit(20);
        return template.find(query, OrderDocument.class);
    }
}
```

Here:

- `Sort.by(...)` uses **Java properties**. Field `id` is translated by the mapper to `_id`.
- `Collation.of("vi").strength(...)` corresponds to the intent `locale: "vi", strength: 2`.
- `withHint("ix_orders_tenant_customer_vi")` specifies an existing index name; it does not create the index.
- `limit(20)` caps returned documents. You cannot rely solely on `limit` as a substitute for real pagination.

Do not copy this template verbatim and force every query to use this hint: an index only fits when filter, sort, and collation align. For status/time queries like Q1, the index and query shape differ.

### 8.1. JSON Queries as BasicQuery

Continuing the "JSON Queries" theme, Spring Data MongoDB offers `BasicQuery` when you want to express filters as JSON strings:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.BasicQuery;

BasicQuery query = new BasicQuery(
    "{ 'tenantId': 'tenant-a', 'status': 'READY_TO_SHIP' }"
);
query.with(Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
));
query.withHint("ix_orders_tenant_status_recent");
query.limit(20);
```

This example uses a **static JSON string**. For user parameters, prefer `Criteria`/`Query` or repository placeholders to avoid unescaped concatenation, BSON type mix-ups, and filter tampering risks. With `BasicQuery`, distinguish physical field names from Java properties when reading results as a domain type.

## 9. @Query: sort, collation, and hint by Version

### 9.1. Three Attributes Declared in the Annotation

In Spring Data MongoDB versions supporting these annotation elements, you can define a static query:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.repository.Repository;

public interface OrderNameRepository
    extends Repository<OrderDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0 }",
        sort = "{ 'customerName': 1, '_id': 1 }",
        collation = "{ 'locale': 'vi', 'strength': 2 }",
        hint = "ix_orders_tenant_customer_vi"
    )
    Slice<OrderDocument> findCustomers(
        String tenantId,
        Pageable pageable
    );
}
```

The example calls with `PageRequest.of(0, 20)` **without dynamic sort**, leaving ordering control to the static `sort` in the annotation. Do not assume this method compiles across all library generations: inspect the actual `org.springframework.data.mongodb.repository.Query` API in your Spring Data version. If `collation` or `hint` is unavailable or interpreted unexpectedly, use `MongoTemplate` per section 8 for clearer control.

In systems with frequent index migrations, embedding index names inside annotations couples code to database structure. Use static hints only when the decision has been measured and is managed alongside index migrations.

### 9.2. Which Writing Style Should You Prefer?

| Need | Usually Suitable Approach |
| --- | --- |
| Simple, fixed filter/sort | Repository `@Query(sort = "...")` when supported by version |
| User-selected sort from an allowlist | `Pageable`/`Sort` via repository or `Query.with(Sort)` |
| Fixed collation for a business use case | `@Query(collation = "...")` if available; or `Query.collation(...)` |
| Locale-dependent collation (controlled) | Build `Collation` in the service and use `MongoTemplate` |
| Diagnostic hint | Mongosh `hint(...)` + `explain(...)`, then consider `Query.withHint(...)` |
| JSON query with complex expressions | `@Query` with placeholders or `BasicQuery`/`MongoTemplate` with clear tests |
| Aggregation pipeline | Aggregation API and its own options; do not assume `@Query` applies to every stage |

More important than syntax is **verifying version behavior**: whether the method exists, how the query is encoded, how dynamic/static sorts combine, and whether the collation matches the index collation.

## 10. Version Constraints to Check

Do not treat documentation for a modern Spring Data release as a guarantee for a project running older libraries. Four version layers can affect behavior:

| Layer | What to Check |
| --- | --- |
| MongoDB server | Does it support collation, hint, and that option on the specific operation? |
| MongoDB Java driver | Do `FindIterable`/other API configuration methods accept sort, collation, and hint as expected? |
| Spring Data MongoDB | Are `Query.collation`, `Query.withHint`, and `@Query`'s `sort`/`collation`/`hint` attributes present? |
| Spring Boot/autoconfiguration | Actual dependency versions and whether `MongoTemplate`/repositories share the same mapping? |

MongoDB server has supported **collation since version 3.4**. That is a server capability milestone, not a guarantee that every Spring Data MongoDB version before or after has identical annotation syntax. Likewise, server-level hints and repository-annotation hints are **two separate API layers**.

### 10.1. Compatibility Verification Workflow

1. Record the actual MongoDB server, Spring Data MongoDB, Spring Boot, and driver versions in your environment.
2. Check method/annotation signatures from the **exact locked artifact version** in the project, not merely newer-version examples.
3. Write small integration tests for filter, sort, collation, and hint through repositories/templates.
4. Observe actual queries at the database and run the same queries in mongosh.
5. Use `explain("executionStats")` to verify indexes and sorting; do not treat error-free Java execution as proof of performance.
6. After upgrades, re-run tests covering accented names, tie-key values, unindexed queries, and large tenant datasets.

If an annotation attribute is unsupported, the Java compiler reports an error on the missing annotation element; if the server does not support an option, errors occur at runtime. Do not treat such exceptions as an unplanned "automatic fallback mechanism".

### 10.2. Do Not Generalize to Every Operation

The examples above mainly apply to **find queries**. `countDocuments`, `distinct`, `findAndModify`, update, delete, and aggregation each have their own options and limits; some commands or versions do not accept sort/collation/hint identically. When moving from `find` to another operation, read that operation's API and check server support rather than copying `@Query` attributes blindly.

## 11. Combining sort, collation, and Indexes for Performance

### 11.1. Query Shape Determines Index Key Order

For Q1:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Candidate index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
```

The first two fields are equality filters, followed by sort keys. This typically aligns with the **Equality–Sort–Range (ESR)** guideline when planning compound indexes. However, it is a heuristic—not a guarantee the planner will pick that index or that it will always be fastest.

For Q2, the query requires Vietnamese collation and sorting by `customerName`, so the Q1 index does not solve it directly. This is why you cannot just create "one index for every query".

### 11.2. Signs of an Expensive Sort

If a query cannot retrieve data in index order, the server may have to perform an in-memory sort. On large datasets, this consumes CPU and memory and in some situations can spill or hit resource limits. Looking only at `nReturned = 20` is misleading: MongoDB may have processed many documents before returning those 20 results.

An easily missed case: an index with the right key pattern but **the wrong collation**. When sorting Strings with locale `vi` against an index built with simple collation, MongoDB may still perform a separate sort stage even though the developer sees `customerName` in the index.

### 11.3. Using Hint as a Controlled Experiment

Compare two plans:

```javascript
// Let MongoDB choose the index automatically.
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

// Ask to test the known index.
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20)
  .explain("executionStats");
```

To draw conclusions, do not compare just single-run milliseconds. Use representative datasets, check keys and documents examined, sort stages, varied tenant distributions, and common vs. rare statuses. When using `explain`, plan statistics and plan caching behave differently from normal production execution; combine with application-level benchmarks/monitoring.

## 12. Reading explain Output Properly

| Signal | Question to Answer |
| --- | --- |
| `winningPlan` | Which strategy did the server choose? |
| `IXSCAN` / `COLLSCAN` | Did it scan an index or scan the whole collection? |
| `indexName` | Does the index actually used match the hinted/proposed name? |
| `SORT` stage or equivalent | Did it require a separate sort or leverage index order? |
| `totalKeysExamined` | How many index keys did the server examine? |
| `totalDocsExamined` | How many documents had to be read/checked? |
| `nReturned` | How many results were returned? |
| `executionTimeMillis` | What latency was observed under these test conditions? |

Plan structures can vary across server versions and query engines. Therefore, avoid writing brittle tests tied to a single JSON path inside `winningPlan` if upgrades are planned.

**Interpretation example:** Q1 returns 20 documents, yet `totalDocsExamined` is very high and a separate sort stage appears. That signals you should revisit filter/index/sort alignment. Conversely, if a hint drives `totalKeysExamined` sharply upward, the forced index may be worse than the planner's natural choice.

### 12.1. Hint Does Not Fix a Broken Query

If a filter uses the wrong `tenantId`, wrong BSON type for `createdAt`, or wrong collation for name matching, hint will not fix incorrect results. A sound investigation order:

```text
Filter matches right data and access permissions?
    ↓
Sort keys and directions correct?
    ↓
Collation has right language/strength?
    ↓
Suitable index exists and collation matches?
    ↓
Explain natural planner choice
    ↓
Test hint only with a clear diagnostic goal
```

## 13. Stable Pagination and User-Chosen Sorts

### 13.1. Offset Pagination and Tie-Breaker Keys

When fetching pages:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20)
  .limit(20);
```

Adding `_id` guarantees deterministic ordering among documents with equal `createdAt`, but **does not freeze a snapshot** when documents are inserted or deleted while a user pages through. Offset pages can still duplicate or skip documents under concurrent changes. For large or continuously updated data, consider cursor/keyset pagination.

### 13.2. A Cursor Pagination Example

Suppose sorting descending by `createdAt`, then `_id`. Cursor from the previous page:

```javascript
const lastCreatedAt = ISODate("2026-11-18T08:00:00Z");
const lastId = "order-002";

db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

The example uses a String `_id`. If IDs are BSON ObjectIds, the cursor and filter must use matching BSON types. Collation can also affect ordering and cursor conditions when a pagination key is a language-collated String. Never use one sort on page 1 and switch collation or sort keys on subsequent pages.

### 13.3. Controlling Dynamic Sort from the API

If users pick a sort from the UI, restrict allowed fields to an allowlist such as `createdAt`, `totalAmountVnd`, or `customerName`, validate sort direction, and append a tie-breaker key. Avoid passing raw JSON sorts or arbitrary field paths from clients straight down to repositories or templates.

Restricting sort fields helps:

- Prevent querying/sorting on internal or sensitive fields not exposed by the API.
- Avoid unindexed sorts on unsupported fields.
- Keep pagination contracts stable.
- Select the right collation when sorting by name instead of timestamp or number.

## 14. Common Mistakes and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No `sort` specified and result order changes | Relying on natural collection order | Declare explicit sort per use case |
| Two records with same `createdAt` swap positions | Missing tie-breaker key | Add `_id` or another stable unique key |
| Accented names sort unnaturally | Simple/binary comparison | Set business-appropriate `locale` and `strength` |
| Query fast with numeric sort, slow with name sort | Index does not match string collation/sort | Verify query and index collations |
| `@Query(collation=...)` fails to compile | Spring Data version lacks annotation element | Check version; consider `MongoTemplate` |
| `@Query(hint=...)` fails at runtime | Index missing or option unsupported | Verify index, driver/server, and operation |
| Hint makes query slower | Forced index is unsuitable | Remove hint or re-test with an evidenced plan |
| Query returns fewer results than expected | Collation/equality or BSON type mismatch | Inspect actual filter and stored data |
| Multi-page sort duplicates/skips items | Offset pagination with concurrent writes | Use suitable keyset pagination; consider snapshot consistency |
| `Sort.by("id")` differs from mongosh `_id` | Confusing Java property name and BSON field name | Inspect mapping metadata and sent query |
| JSON query built from user params errors | Unsafe JSON string concatenation/escaping | Use placeholders or `Criteria` |
| Index hint does not appear as expected | API/operation/version does not apply it as assumed | Inspect actual plan and version capabilities |

## 15. Practice Exercises with Solutions

### Exercise 1 — Stable Queue Sort

**Problem:** Fetch up to 20 newest ready-to-ship orders for `tenant-a`. Multiple documents may share the same `createdAt`.

**Solution:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

`_id` acts as tie-breaker. If the query is critical and the collection is large, evaluate compound index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` and measure with `explain`.

### Exercise 2 — Vietnamese Sort

**Problem:** Customer name list must compare using Vietnamese rules with secondary-level accent sensitivity.

**Solution:**

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ customerName: 1, _id: 1 })
  .collation({ locale: "vi", strength: 2 });
```

To accelerate it, create an index with matching collation configuration and measure on real data. Test fixtures such as `An`, `Ân`, `Bình`, `Đức`; do not assume binary order matches language rules.

### Exercise 3 — Why Isn't the Customer Name Index Being Used?

**Problem:** The collection has index `{ tenantId: 1, customerName: 1 }` created with simple collation. A name-sorting query with `locale: "vi", strength: 2` still shows a sort stage.

**Solution:** The query uses different string comparison rules than the index, so the simple index cannot satisfy Vietnamese name ordering. Create an appropriately collated index if workload justifies it; do not "fix" it by turning off collation to match the index when doing so breaks business requirements.

### Exercise 4 — Testing Hint to Compare Plans

**Problem:** An index named `ix_orders_tenant_status_recent` already exists. Instruct the server to use that index and inspect the execution plan.

**Solution:**

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "READY_TO_SHIP"
})
  .sort({ createdAt: -1, _id: -1 })
  .hint("ix_orders_tenant_status_recent")
  .limit(20)
  .explain("executionStats");
```

Compare against the exact same query **without hint**. If the hint increases keys/docs examined, revisit your hypothesis instead of keeping the hint just to "guarantee index usage".

### Exercise 5 — Choosing Repository or MongoTemplate

**Problem:** One screen always sorts by timestamp; another lets staff switch locale among a few approved values and test an index during diagnostics.

**Solution:** The fixed-query screen can use `@Query(sort = "...")` with bounded `Pageable`, depending on version. The runtime-varying screen should use `MongoTemplate` to construct `Query`, `Sort`, `Collation`, and optional hint in a controlled manner, verified against your version with integration tests for each supported locale.

### Exercise 6 — Why Shouldn't Every Sort Have a Hint?

**Problem:** Q1 has a good index, the planner already picks it, and `explain` shows low scan counts with no expensive sort. Should you add `@Query(hint = "...")`?

**Solution:** No compelling reason. Hints increase coupling to specific index names and can break during index migrations. When the plan is already good, keep the query simple and continue monitoring rather than unnecessarily pinning an index.

### Exercise 7 — Sort and Pagination

**Problem:** The app sorts only by `createdAt DESC`; two orders share the same timestamp. Users see duplicate items when turning pages.

**Solution:** Add a tie-breaker key like `_id DESC` and keep the sort consistent across all pages. If duplicates persist under concurrent inserts/deletes, evaluate cursor/keyset pagination instead of relying solely on offsets. Cursors must carry all sort keys and use consistent BSON types and collation strength.

## 16. Pre-Handoff Query Checklist

| Review Question | Evidence to Confirm |
| --- | --- |
| Does the query filter properly by tenant/owner? | BSON query and authorization tests |
| Do sort keys/directions reflect business rules? | Explicit `sort` and ordering tests |
| Is there a stable tie-breaker key? | `_id` or suitable unique key |
| Are results/pages bounded? | `limit`, `Slice`/`Pageable`, or cursor |
| Is collation genuinely needed? | Language requirements and comparison fixtures |
| Are locale/strength accurate? | Tests with accented/cased/tie names |
| Which collation was the index created with? | `getIndexes()` output and migration scripts |
| Does hint have evidenced benefit? | `explain` comparison against unhinted query |
| Is there risk of index rename/drop? | Synchronized migration/deployment process |
| Which attributes does the Spring Data version support? | Actual dependency API, compile/integration tests |
| Do server/driver support the option on that operation? | Verified on the same operation type in test environment |
| Is dynamic sort allowlisted? | Field/direction validation in service layer |
| Are JSON query parameters bound safely? | Placeholders/`Criteria`, no arbitrary string concatenation |
| Was it measured on representative data? | Keys/docs examined, sort stages, latency, and load |

### Key Takeaways

1. `sort` controls ordering; add a tie-breaker key to stabilize results, especially during pagination.
2. `collation` governs how strings compare, not just display; queries and indexes must use compatible rules to leverage indexes for string matching and sorting.
3. `hint` is a **conditional** index-plan control tool, never a fix for a broken query or a guarantee of performance.
4. `@Query`, `MongoTemplate`, and mongosh have **different syntax and support scopes**. Always verify against your project's exact Spring Data, driver, and MongoDB server versions.
5. Validate correctness and performance independently: test data accuracy, test ordering, verify collation, then inspect execution plans with `explain("executionStats")`.
