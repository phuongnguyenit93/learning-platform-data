# Distinct, First, Top, count, and exists

In **Spring Data MongoDB**, many common queries can be defined right in the method names of `MongoRepository` without writing MongoDB commands by hand. Spring Data parses syntax like `findFirstByStatusOrderByCreatedAtDesc`, `findTop3ByStatus`, `countByCategory`, or `existsBySku` to generate the corresponding queries. This is the **derived queries** mechanism.

The keywords **`Distinct`, `First`, `Top`, `count`, and `exists`** share the same naming mechanism, yet serve very different goals: finding unique values, fetching one or a few top documents, counting documents, and checking existence. Understanding them well prevents loading unnecessary data, drawing wrong conclusions due to missing sorts, or confusing "counting documents" with "counting distinct values".

This lesson belongs to the **Derived Queries** chapter of the `SPRING_DATA_MONGODB` module. Beyond repository syntax, we will use `MongoTemplate` when needing **distinct values of a specific field**, examine MongoDB Server indexes, Java/BSON mapping, testing, and performance diagnostics. More complex needs may call for aggregation; transactions and reactive access do not alter the semantics of these query operations.

After this lesson, you will be able to:

- Write repository methods using `First`, `Top`, `countBy`, and `existsBy` with appropriate return types.
- Distinguish `Distinct` in derived method names from MongoDB's `distinct(field)` operation, especially when fetching a list of **unique values of one field**.
- Understand how `OrderBy`, `Sort`, `Pageable`, BSON data types, and indexes affect results.
- Choose `MongoTemplate.findDistinct` or aggregation when derived method names cannot express a requirement cleanly.
- Test empty results, duplicate values, timestamp ties, and concurrent data changes.

## 1. How Spring Data Reads Method Names

In a simple example, a derived query name has two parts:

```text
findTop3ByStatusOrderByCreatedAtDescIdDesc
└─────┘  └─┘└──────┘└─────────────────────┘
Subject   By Condition      Static sort
(Top3)         (Status)  (createdAt DESC, id DESC)
```

The part **before `By`** describes the operation: `find`, `count`, `exists`, and limits such as `First`/`Top`; the part **after `By`** expresses conditions using Java properties. `And`, `Or`, `GreaterThan`, `In`, `Between`, etc. build compound criteria; `OrderBy` specifies fixed ordering. Only recognized segments create valid queries; a long method name **does not guarantee an optimal command**.

| Method name | Intent | MongoDB operation form |
| --- | --- | --- |
| `findFirstByStatusOrderByCreatedAtDescIdDesc` | Fetch the first record in deterministic order | `find` + `sort` + `limit(1)` |
| `findTop3ByStatusOrderByCreatedAtDescIdDesc` | Fetch up to the first 3 records | `find` + `sort` + `limit(3)` |
| `countByStatus` | Count documents matching filter | Filtered count operation |
| `existsBySku` | Does at least one matching document exist? | Existence check query |
| `findDistinct...By...` | Requests distinct in the method subject | **Must clarify "distinct on which field?" and test behavior** |

**Note:** derived query interpretation depends on entity metadata and Spring Data version. `Distinct` is the most easily misunderstood case: in MongoDB, **distinct values of a field** is an operation with an explicit target field; do not assume putting `Distinct` in a method name automatically returns unique categories. We cover the explicit API for that need in Section 5.

## 2. Sample Data and Repository Used Throughout

Suppose a store's `products` collection has `sku`, `status`, `category`, `priceVnd`, and `createdAt`. Each product has a stable string ID:

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "products")
public record CatalogProduct(
        @MongoId String id,
        String sku,
        String status,
        String category,
        long priceVnd,
        Instant createdAt
) {}
```

Here `@MongoId` keeps the ID as `String` by design. `Instant` maps to BSON Date via the default converter; verify settings and timezones when using other date types.

Illustrative data in `mongosh`:

```javascript
db.products.insertMany([
  { _id: "P-100", sku: "BK-001", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("80000"),
    createdAt: ISODate("2026-11-01T00:00:00Z") },
  { _id: "P-101", sku: "BK-002", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("90000"),
    createdAt: ISODate("2026-11-05T00:00:00Z") },
  { _id: "P-102", sku: "PN-001", status: "ACTIVE",
    category: "PEN", priceVnd: NumberLong("20000"),
    createdAt: ISODate("2026-11-05T00:00:00Z") },
  { _id: "P-103", sku: "PN-002", status: "DRAFT",
    category: "PEN", priceVnd: NumberLong("21000"),
    createdAt: ISODate("2026-11-09T00:00:00Z") },
  { _id: "P-104", sku: "OF-001", status: "ACTIVE",
    category: "OFFICE", priceVnd: NumberLong("150000"),
    createdAt: ISODate("2026-11-08T00:00:00Z") },
  { _id: "P-105", sku: "BK-003", status: "ACTIVE",
    category: "BOOK", priceVnd: NumberLong("120000"),
    createdAt: ISODate("2026-11-08T00:00:00Z") }
]);
```

> The dataset above is strictly for **isolated development or test databases**. `insertMany` fails on duplicate `_id`; do not re-run on a collection already holding these IDs unless intentionally resetting sample data in an authorized environment.

Repository:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Optional<CatalogProduct>
    findFirstByStatusOrderByCreatedAtDescIdDesc(String status);

    List<CatalogProduct>
    findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);

    long countByStatus(String status);

    long countByStatusAndPriceVndGreaterThan(
            String status, long minPriceVnd);

    boolean existsBySku(String sku);

    boolean existsByCategoryAndStatus(String category, String status);
}
```

All methods use **Java property names** (`createdAt`, `priceVnd`) rather than arbitrary raw document names, letting Spring Data map them to BSON fields via metadata. A typo in a property name or unsupported method structure typically prevents the repository bean from initializing or produces a different query than intended.

## 3. `First`: Fetching the First Record

`First` is used when only **one** record is needed, such as the newest ACTIVE product. Given:

```java
Optional<CatalogProduct>
findFirstByStatusOrderByCreatedAtDescIdDesc(String status);
```

Invocation:

```java
Optional<CatalogProduct> newest =
        repository.findFirstByStatusOrderByCreatedAtDescIdDesc("ACTIVE");

newest.ifPresent(p -> System.out.println(p.id()));
// On sample data: P-105.
```

Semantically equivalent MongoDB query:

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(1);
```

In the sample data, both `P-104` and `P-105` share `createdAt` on November 8. Adding descending `_id` sort selects **`P-105` deterministically**. With only `OrderByCreatedAtDesc` when documents share timestamps, which record comes "first" among ties **is not guaranteed**.

### 3.1. Why Does `First` Need No Number?

`findFirstBy...` and `findTopBy...` both express a default limit of **one result**. When more are needed, supply a count such as `Top3` or `First5`. Method names can attach `OrderBy` or accept a `Sort` parameter in appropriate overloads.

Never use `First` when the requirement is "pick any arbitrary match equally" without defining what *first* means. In business logic, define an explicit sort criterion (newest by creation time, highest by sales, etc.).

### 3.2. Return Type When Nothing Matches

`Optional<CatalogProduct>` cleanly represents **no result** via `Optional.empty()`. At the API layer, services can map empty to 404 for mandatory lookups, or treat "no ACTIVE products" as a valid empty state.

Never call `get()` on `Optional` without checking presence. Also never treat `First` as a **uniqueness** check: if 100 products match, it still returns **one** result; enforcing uniqueness requires constraints/indexes or dedicated validation.

## 4. `Top`: Fetching Up to N Records

`TopN` behaves like `FirstN`, though its phrasing is often more natural for leaderboards or "top N newest" lists:

```java
List<CatalogProduct>
findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);
```

```java
List<CatalogProduct> latest3 =
        repository.findTop3ByStatusOrderByCreatedAtDescIdDesc("ACTIVE");

List<String> ids = latest3.stream()
        .map(CatalogProduct::id)
        .toList();
// On sample data: [P-105, P-104, P-102].
```

Equivalent:

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3);
```

If only two documents match, the list contains **two elements**, with no `null` padding. If none match, an empty list is returned. `Top3` limits the **number of returned documents**, not three distinct categories, and does not return the remaining match count.

### 4.1. Do `First` and `Top` Differ in Execution?

`findFirstBy...` and `findTopBy...` both limit to 1. `findFirst3By...` and `findTop3By...` both limit to 3 when supported by the parser. Pick whichever name reads clearest to your team; what matters more are **filters, sort order, limits, and indexes**.

For instance, to return the "five highest-priced ACTIVE products", sort by price with a tie-breaker:

```java
List<CatalogProduct>
findTop5ByStatusOrderByPriceVndDescIdAsc(String status);
```

Do not confuse `Top5` with deduplicating categories. It still returns up to 5 **documents**, even if all belong to category BOOK.

### 4.2. `Top` Is Not Infinite Pagination

A fixed `Top3` method fits a "3 latest items" widget well, but should not be used to paginate millions of products. For list pages, use `Pageable`, `Sort`, and indexes, or keyset pagination for deep pages. If combining `Top` with `Pageable`, understand how limits and total counts interact in your Spring Data version — do not assume it behaves identically to an unbounded query.

## 5. `Distinct`: Distinguishing Distinct Documents from Distinct Values of a Field

### 5.1. Business Questions Must Specify "Distinct by What?"

Suppose there are three products in category BOOK and one in category PEN. Two requirements are **different**:

- **List products without duplicate IDs:** each product already has its own `_id`; three BOOK products remain three distinct products.
- **List unique categories:** BOOK appears once, PEN once, OFFICE once.

In Spring Data, `Distinct` can appear in the **subject** of a derived method like `findDistinct...By...`. Yet in MongoDB, `distinct` requires **explicitly naming the field** whose unique values you want. Never infer from `Distinct` in an entity-returning method name that the repository will automatically deduplicate by `category`.

Specifically, `findDistinctByStatus("ACTIVE")` — however handled by your framework/parser version — **is not a clear contract for "return distinct category Strings"**. When you need unique values of a field, use a distinct operation naming the field explicitly and test against real BSON data.

### 5.2. Using `MongoTemplate.findDistinct` to Fetch Unique Categories

This expresses the intent directly without relying on how readers interpret a derived method's subject:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Illustrative snippet in a service with injected mongoTemplate.
Query activeProducts = Query.query(
        Criteria.where("status").is("ACTIVE")
);

List<String> categories = mongoTemplate.findDistinct(
        activeProducts,
        "category",
        CatalogProduct.class,
        String.class
);
// Contains BOOK, PEN, OFFICE; do not rely on returned order.
```

Semantically equivalent MongoDB command:

```javascript
db.products.distinct("category", { status: "ACTIVE" });
// Example: ["BOOK", "OFFICE", "PEN"].
```

`"category"` is the **field to distinct**; `activeProducts` is the filter. `CatalogProduct.class` supplies metadata so Spring Data maps field names and types; `String.class` specifies the target element type.

**Never assume the ordering of `distinct` results.** If the UI requires an alphabetical list, sort the small result list in Java, or design an aggregation pipeline when server-side sorting, filtering, and pagination are needed.

### 5.3. Easily Overlooked Details with `distinct`

- `distinct(field)` returns **unique values of the field**, not root documents. Hence `List<String>` fits a string field like `category`.
- If the field holds an **array**, MongoDB can return each unique element of the arrays; verify with your exact data structure.
- `null`, missing fields, and mixed types can yield unexpected values. Standardize schemas and clean up legacy data before concluding "how many categories exist".
- `"BOOK"` and `"book"` are distinct values under default collation. For case-insensitive distinct values, enforce consistent collation or data normalization.
- `distinct` is not a `unique index`. Querying unique values **does not prevent** inserting documents with duplicate categories or SKUs.
- A high-cardinality distinct field can consume significant memory or hit result-size limits; for large outputs or pagination, consider aggregation or a dedicated collection.

### 5.4. Counting Distinct Categories Differs from `countByStatus`

Given 5 ACTIVE documents in the sample dataset:

- `countByStatus("ACTIVE")` = **5 documents**.
- Unique ACTIVE categories = **BOOK, PEN, OFFICE**, which is **3 values**.

To count distinct categories server-side, use aggregation:

```javascript
db.products.aggregate([
  { $match: { status: "ACTIVE" } },
  { $group: { _id: "$category" } },
  { $count: "distinctCategoryCount" }
]);
// Result: { distinctCategoryCount: 3 }.
```

Never assume names like `countDistinct...By...` (even if accepted by a parser) mean "count distinct values of a field inferred from the method name". **Counting documents and counting distinct field values are not the same**. Aggregation lets you state the grouping field and filter explicitly.

## 6. `countBy`: Counting Matching Documents

In the repository:

```java
long countByStatus(String status);

long countByStatusAndPriceVndGreaterThan(
        String status, long minPriceVnd);
```

Examples:

```java
long activeTotal = repository.countByStatus("ACTIVE");
// 5

long expensiveActive = repository
        .countByStatusAndPriceVndGreaterThan("ACTIVE", 100_000L);
// 2: P-104 and P-105.
```

Semantically equivalent to a server-side filtered count:

```javascript
db.products.countDocuments({ status: "ACTIVE" });
// 5

db.products.countDocuments({
  status: "ACTIVE",
  priceVnd: { $gt: NumberLong("100000") }
});
// 2
```

`GreaterThan` means **strictly greater** (`$gt`), excluding equality. If the business rule requires "price from 100,000 upwards", use `GreaterThanEqual`/`$gte`. Off-by-one boundary mistakes are common in reporting queries.

### 6.1. `countBy` Differs from `findAll().size()`

Never load all documents into Java just to count them:

```java
// Avoid on large datasets:
long count = repository.findAll().stream()
        .filter(p -> "ACTIVE".equals(p.status()))
        .count();
```

That loads every document from MongoDB into application memory before filtering, wasting RAM, bandwidth, and CPU. `countByStatus` pushes filtering and counting to the server; only the numeric count travels back.

Even so, **filtered counting is not automatically O(1)**. The server still evaluates the filter, uses indexes when helpful, and may scan many index keys or documents. For huge datasets or high-frequency dashboards, benchmark performance and consider maintained counters/summaries.

### 6.2. Exact Filtered `count` vs. Estimated Collection Count

`countBy...` performs an **exact count of documents matching the predicate at query time** according to MongoDB query behavior. It is not an approximate metadata estimate. MongoDB also offers estimated counts for different use cases; never swap `countByStatus` for an estimated count when exact filtered counts are required.

Even when a count accurately reflects documents visible at read time, **data can change immediately afterward**. Never rely on `countBy...` to enforce future invariants without conditional updates or transactions.

### 6.3. Using `MongoTemplate` for More Dynamic Criteria

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query filter = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("priceVnd").gte(100_000L)
);

long total = mongoTemplate.count(filter, CatalogProduct.class);
```

This snippet lives inside a service with an injected `mongoTemplate`. `MongoTemplate` fits well when filters are assembled conditionally from optional parameters instead of creating dozens of long, hard-to-read repository methods.

## 7. `existsBy`: Checking Whether at Least One Document Exists

`existsBy` answers yes/no questions like "Does this SKU already exist?" or "Is there an ACTIVE product in category PEN?":

```java
boolean existsBySku(String sku);
boolean existsByCategoryAndStatus(String category, String status);
```

Usage:

```java
boolean skuExists = repository.existsBySku("PN-002");
// true: P-103, even though its status is DRAFT.

boolean activePenExists =
        repository.existsByCategoryAndStatus("PEN", "ACTIVE");
// true: P-102.

boolean unknownExists = repository.existsBySku("UNKNOWN-SKU");
// false.
```

MongoDB can check existence by finding one matching document without transferring full payloads:

```javascript
db.products.find(
  { sku: "PN-002" },
  { _id: 1 }
).limit(1);
```

This is a **semantic illustration**, not a claim that every Spring Data version emits that exact command. Remember that `existsBy...` returns a **boolean**, not an entity, not a count, and does not prove only one record exists.

### 7.1. When to Use `existsBy` Instead of `countBy`?

When you only need to know "does at least one record exist?", `existsBy` communicates intent more clearly than `countBy... > 0` and can avoid counting remaining matches. Still, do not make absolute speed claims without verifying queries and indexes on MongoDB Server.

| Question | Recommended API | Return value |
| --- | --- | --- |
| Does SKU `BK-001` exist? | `existsBySku("BK-001")` | `boolean` |
| How many ACTIVE products exist? | `countByStatus("ACTIVE")` | `long` |
| What is the newest ACTIVE product? | `findFirstByStatusOrderBy...` | `Optional<CatalogProduct>` |
| What are the 3 newest ACTIVE products? | `findTop3ByStatusOrderBy...` | `List<CatalogProduct>` |
| What are the distinct ACTIVE categories? | `MongoTemplate.findDistinct(..., "category", ...)` | `List<String>` |

### 7.2. `existsBy` Does Not Replace Unique Indexes or Atomic Updates

Suppose two requests run concurrently:

```java
if (!repository.existsBySku("BK-999")) {
    // Another request can insert BK-999 right here.
    repository.insert(newProduct);
}
```

Both requests can observe `false` and both attempt to insert. Thus **check-then-insert does not guarantee uniqueness under concurrency**. When SKUs must be unique, create a unique index:

```javascript
db.products.createIndex({ sku: 1 }, { unique: true });
```

Then handle `DuplicateKeyException`/`E11000` errors on concurrent inserts. `existsBySku` is useful for early UI validation warnings, while the server-side unique index is the true data-integrity guard.

Similarly, to enforce "allow adding items only while under limit N", a standalone `countBy...` or `existsBy...` cannot stop concurrent requests from racing past the limit. Design atomic single-document updates, optimistic versioning, or transactions when required.

## 8. Combining Criteria, Sorting, and Return Types

Derived queries let you combine keywords to express specific needs. For example, finding the three highest-priced ACTIVE products in category BOOK:

```java
import java.util.List;

List<CatalogProduct>
findTop3ByStatusAndCategoryOrderByPriceVndDescIdAsc(
        String status, String category);
```

Semantically equivalent:

```javascript
db.products.find({
  status: "ACTIVE",
  category: "BOOK"
})
.sort({ priceVnd: -1, _id: 1 })
.limit(3);
```

Results on sample data: `P-105` (120,000), `P-101` (90,000), `P-100` (80,000). When adding `Or`, watch out for how the parser groups conditions; queries with complex logical parentheses are usually clearer via `@Query`, `Criteria`, or aggregation than overly long method names.

### 8.1. Dynamic Sorting When Users Change Sort Criteria

If the UI lets users choose "newest" or "highest price", you do not need twenty `OrderBy...` methods. You can declare:

```java
import java.util.List;
import org.springframework.data.domain.Sort;

// Additional method in CatalogProductRepository:
List<CatalogProduct> findTop3ByStatus(String status, Sort sort);
```

Invocation:

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(Sort.Order.desc("priceVnd"),
                    Sort.Order.asc("id"));

List<CatalogProduct> mostExpensive =
        repository.findTop3ByStatus("ACTIVE", sort);
```

`Sort` uses mapped property names. For client-supplied inputs, **whitelist allowed sort fields** (e.g., `priceVnd` and `createdAt`), avoiding arbitrary field paths that cause uncontrolled queries and unindexed sorts.

### 8.2. Return Types Must Match Semantics

| Query operation | Recommended Java type | Do not confuse with |
| --- | --- | --- |
| `findFirst...` or `findTop...` limited to 1 | `Optional<CatalogProduct>` | Guarantee of uniqueness |
| `findTop3...` | `List<CatalogProduct>` | A page carrying total counts, or a category-deduplicated set |
| `countBy...` | `long` | `int` when document counts can grow large |
| `existsBy...` | `boolean` | Document count or the document itself |
| Distinct field values via template | `List<String>` for String fields | `List<CatalogProduct>` |

Spring Data supports many result shapes (entities, projections, `Page`, `Slice`, `Stream`, reactive publishers...), yet not every method-name and return-type combination shares identical semantics or cost. Pick types **matching the intended API**, test 0, 1, and N matches, and check your framework version.

## 9. Indexes: Keeping Derived Methods Fast as Data Grows

Derived queries only build the **query**; they do not ensure MongoDB Server picks an efficient plan. For the sample data and screens above, start by evaluating candidate indexes:

```javascript
// First/Top: filter ACTIVE, sort by timestamp and ID.
db.products.createIndex({
  status: 1,
  createdAt: -1,
  _id: -1
});

// Count by status and price range.
db.products.createIndex({
  status: 1,
  priceVnd: 1
});

// Exists by SKU, also enforcing uniqueness if required by business rules.
db.products.createIndex({ sku: 1 }, { unique: true });

// Distinct categories filtered by status.
db.products.createIndex({
  status: 1,
  category: 1
});
```

These indexes are **suggestions tailored to the example queries**, not a mandatory checklist for every project. Each index consumes storage and slows writes. For instance, `{status: 1, priceVnd: 1}` helps range filtering, yet does not make `count` free; measure on the server.

### 9.1. Inspecting First/Top Queries

```javascript
db.products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats");
```

Inspect `IXSCAN`/`COLLSCAN` plans, `totalKeysExamined`, `totalDocsExamined`, documents returned, and execution time. With only six sample documents, MongoDB may choose a collection scan even when an index exists; never base index strategies on tiny datasets.

### 9.2. Inspecting count, exists, and distinct

```javascript
db.products.find({ sku: "BK-001" }, { _id: 1 })
  .limit(1)
  .explain("executionStats");

db.products.find({
  status: "ACTIVE",
  priceVnd: { $gt: NumberLong("100000") }
}).explain("executionStats");

db.products.distinct("category", { status: "ACTIVE" });
```

Because the last command uses `distinct`, collecting explain stats differs by MongoDB Server version and API; use the appropriate explain command or build an equivalent aggregation to inspect plans. Do not treat the middle `find` output as **exact proof of count cost**, since the engine may execute counts differently. These commands help **verify filters and index coverage**, after which you measure real application operations directly.

### 9.3. Field Order in Compound Indexes Matters

`{status: 1, createdAt: -1, _id: -1}` fits equality on `status` followed by sorting on `createdAt`/`_id`. If `status` has low cardinality (low selectivity), MongoDB still weighs scan cost against returned documents. For `Top3`, index order allows the server to stop early once 3 matches are found.

Do not append `_id` as a tie-breaker thinking "ID already has an index so it is free": a compound index is its own structure, and adding `_id` increases disk and write cost. Include it when deterministic tie-breaking is needed and weigh the trade-off.

## 10. Reactive Access and Concurrency Limits

Spring Data MongoDB provides `ReactiveMongoRepository` with analogous derived methods returning `Mono` or `Flux`. Example:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveCatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Mono<CatalogProduct>
    findFirstByStatusOrderByCreatedAtDescIdDesc(String status);

    Flux<CatalogProduct>
    findTop3ByStatusOrderByCreatedAtDescIdDesc(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsBySku(String sku);
}
```

`Mono<CatalogProduct>` completes empty when no document matches; `Flux<CatalogProduct>` emits 0 to 3 documents for `Top3`. Publishers execute only when subscribed to under Reactive Streams semantics.

**Reactive does not alter filters, limits, or data consistency.** It does not add indexes, guarantee ordering without `OrderBy`, or eliminate the check-then-insert race on `existsBySku`. Enforcing uniqueness on creation still requires a unique index and handling write conflicts.

## 11. Testing Against Real MongoDB

To verify derived query parsing, Java/BSON mapping, ordering, and count/exists outputs, use **`@DataMongoTest` with an isolated test MongoDB instance**, such as Testcontainers. Mocked repositories only confirm a method was called, never testing the generated query or matched documents.

Illustrative Spring Boot 3.x test using `CatalogProduct` and `CatalogProductRepository` from Section 2:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class DerivedQueryKeywordsTest {

    @Autowired CatalogProductRepository repository;
    @Autowired MongoTemplate template;

    @BeforeEach
    void seed() {
        // Run only on an isolated test MongoDB instance.
        repository.deleteAll();
        repository.insert(List.of(
            p("P-100", "BK-001", "ACTIVE", "BOOK",   80_000, "2026-11-01"),
            p("P-101", "BK-002", "ACTIVE", "BOOK",   90_000, "2026-11-05"),
            p("P-102", "PN-001", "ACTIVE", "PEN",    20_000, "2026-11-05"),
            p("P-103", "PN-002", "DRAFT",  "PEN",    21_000, "2026-11-09"),
            p("P-104", "OF-001", "ACTIVE", "OFFICE",150_000, "2026-11-08"),
            p("P-105", "BK-003", "ACTIVE", "BOOK",  120_000, "2026-11-08")
        ));
    }

    private CatalogProduct p(String id, String sku, String status,
                             String category, long price, String date) {
        return new CatalogProduct(
                id, sku, status, category, price,
                Instant.parse(date + "T00:00:00Z"));
    }

    @Test
    void firstAndTopHaveStableOrder() {
        assertThat(repository
                .findFirstByStatusOrderByCreatedAtDescIdDesc("ACTIVE")
                .map(CatalogProduct::id))
                .contains("P-105");

        List<String> topIds = repository
                .findTop3ByStatusOrderByCreatedAtDescIdDesc("ACTIVE")
                .stream().map(CatalogProduct::id).toList();
        assertThat(topIds).containsExactly(
                "P-105", "P-104", "P-102");
    }

    @Test
    void countAndExistsDoNotNeedToLoadAllProducts() {
        assertThat(repository.countByStatus("ACTIVE")).isEqualTo(5);
        assertThat(repository
                .countByStatusAndPriceVndGreaterThan("ACTIVE", 100_000L))
                .isEqualTo(2);
        assertThat(repository.existsBySku("PN-002")).isTrue();
        assertThat(repository.existsBySku("INVALID")).isFalse();
        assertThat(repository
                .existsByCategoryAndStatus("PEN", "ACTIVE")).isTrue();
    }

    @Test
    void distinctCategoriesAreNotDistinctProducts() {
        Query query = Query.query(Criteria.where("status").is("ACTIVE"));
        List<String> categories = template.findDistinct(
                query, "category", CatalogProduct.class, String.class);

        assertThat(categories)
                .containsExactlyInAnyOrder("BOOK", "PEN", "OFFICE");
    }
}
```

This test requires JUnit/AssertJ/Spring Boot Test dependencies and a **real test MongoDB Server**. `@DataMongoTest` does not automatically spin up a MongoDB Server in every project. Never run `repository.deleteAll()` against shared or production databases.

### 11.1. Boundary Tests to Add

| Case | Expected outcome |
| --- | --- |
| No `ARCHIVED` products | `findFirstByStatus...` returns `Optional.empty()`; `findTop3...` returns empty list |
| Only 2 matching products | `Top3` returns 2 documents with no `null` elements |
| Two products with identical `createdAt` | Secondary `_id` key produces deterministic order |
| Multiple products sharing a category | Distinct field returns that category once |
| Document missing `category` | Verify missing/null data policy and distinct output |
| `"BOOK"` vs. `"book"` | Check collation and case normalization |
| Price equal to 100,000 | `GreaterThan` excludes it; `GreaterThanEqual` includes it |
| Duplicate SKU in legacy data | `existsBySku` still returns true, does not prove uniqueness |
| Concurrent requests creating same SKU | Unique index prevents duplicates; service handles conflict |
| Large dataset | Verify index usage, latency, and scanned documents for key queries |

Verifying results is step one; to verify performance, inspect actual driver commands, server `explain`, execution time, and payload size. Avoid logging full queries containing sensitive parameters in production logs.

## 12. Common Misconceptions

| Misconception | Why it is wrong | Solution |
| --- | --- | --- |
| Using `findFirstByStatus` without `OrderBy` for "latest" | Order is unspecified; results shift with data or query plans | Add `OrderByCreatedAtDesc` and a tie-breaker like `IdDesc` |
| Thinking `Top3` fetched all ACTIVE products | `Top3` caps results at 3 documents | Use `countBy` for totals; use pagination for full lists |
| Using `Distinct` expecting deduplicated categories | Distinct documents differs from distinct **values of one field** | Specify the field via `findDistinct`/aggregation and test results |
| Treating `countByStatus` as the number of ACTIVE categories | `count` counts matching documents | Use `distinct("category")` or `$group` aggregation for unique categories |
| Using `findAll().size()` to count | Loads every document needlessly | Use `countBy...` or `MongoTemplate.count` |
| Using `countBy... > 0` everywhere for existence | May perform unnecessary counting work | `existsBy...` states intent cleanly |
| Using `existsBySku` as a uniqueness constraint | Two requests can both observe false then insert | Enforce unique index on MongoDB Server and handle duplicate keys |
| Thinking `First` only matches when unique | Still returns one when many match | Add unique constraints if business logic requires uniqueness |
| Confusing `GreaterThan` and `GreaterThanEqual` | Wrong results at threshold boundaries | Test values equal to thresholds to verify `$gt` vs. `$gte` |
| Returning unbounded `List` for large tables | High memory, latency, and load | Use `TopN` for capped widgets; `Pageable`/cursors for large lists |
| Reading only method names without checking indexes | Functionally correct queries can still be slow | Run `explain` and index for actual filters and sorts |
| Passing arbitrary user fields into `Sort` or queries | Uncontrolled performance and broken API contracts | Whitelist allowed fields and validate arguments |

## 13. Applied Exercise and Reference Solution

An order management system has an `orders` collection with `_id`, `customerId`, `status`, `totalVnd`, and `createdAt`. Requirements:

1. Fetch a customer's **most recent delivered order**; absent if none exists.
2. Fetch a customer's **5 highest-value orders** by `totalVnd`; break ties by ascending `_id`.
3. Count orders with `status = "PAID"` and `totalVnd` of 1,000,000 or more.
4. Check whether a customer has ever had a `DELIVERED` order.
5. Fetch the list of **distinct statuses** that customer has ever had without loading all orders into Java memory.

A set of repository methods can be written as:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {

    Optional<Order>
    findFirstByCustomerIdAndStatusOrderByCreatedAtDescIdDesc(
            String customerId, String status);

    List<Order>
    findTop5ByCustomerIdOrderByTotalVndDescIdAsc(
            String customerId);

    long countByStatusAndTotalVndGreaterThanEqual(
            String status, long minimum);

    boolean existsByCustomerIdAndStatus(
            String customerId, String status);
}
```

Here `Order` is an illustrative entity mapped to the `orders` collection with properties matching the method names; define the class, imports, and database configuration in your project. For requirement 5, `MongoTemplate` specifies the distinct field explicitly:

```java
Query query = Query.query(
        Criteria.where("customerId").is(customerId)
);

List<String> statuses = mongoTemplate.findDistinct(
        query, "status", Order.class, String.class);
```

This snippet goes inside a service method with an injected `mongoTemplate`, importing `Query`, `Criteria`, and `List`. Returned status values have **no guaranteed order**; sort in Java if needed for display.

Initial indexes to evaluate:

```javascript
// Latest delivered order per customer:
db.orders.createIndex({
  customerId: 1, status: 1, createdAt: -1, _id: -1
});

// Top 5 by order total per customer:
db.orders.createIndex({
  customerId: 1, totalVnd: -1, _id: 1
});

// Count PAID orders above a price threshold:
db.orders.createIndex({ status: 1, totalVnd: 1 });
```

These are starting candidates based on the specific queries; final index counts and key orders must be verified against real queries and data statistics. Bonus question for the exercise: if `totalVnd` were stored as BSON String instead of an integer, would `GreaterThanEqual` and sorting still behave as expected? **No**: storage types govern server-side comparisons; check BSON types and standardize mapping.

### Checklist Before Putting Derived Queries in Production

1. **Is the goal one document, N documents, a count, existence, or unique field values?** Pick `First`, `Top`, `countBy`, `existsBy`, or distinct accordingly.
2. **"First" by what criterion?** Have you included `OrderBy` and a tie-breaker key?
3. **Distinct on which field?** Do you need to handle `null`, arrays, casing, or collation?
4. **Are comparison bounds exact?** `GreaterThan` differs from `GreaterThanEqual`.
5. **Does the return type express empty results cleanly?** Use `Optional`/`List`/`boolean`/`long` appropriately.
6. **Do indexes support both filter and sort?** Have you checked `explain` on representative data?
7. **Can concurrent writes invalidate count/exists?** Are you misusing them as data constraints?
8. **Is the derived method name still readable?** If too long or requiring aggregation, switch to `@Query`/`MongoTemplate`.
9. **Using reactive?** Ensure proper `Mono`/`Flux` types and never block the event loop.
10. **Have you written integration tests against real MongoDB?** Verify 0/1/N matches, ties, sorting, and BSON types.

**Key takeaway:** `First`/`Top` pick **one or several ordered documents**; `countBy` counts **documents**; `existsBy` checks for **at least one document**; and distinct on a field retrieves **unique values**. Derived queries keep CRUD concise, yet still demand choosing **return types, sorts, indexes, data constraints, and tests** aligned with MongoDB Server.
