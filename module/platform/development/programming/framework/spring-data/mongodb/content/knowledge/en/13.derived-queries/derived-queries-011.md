# Checking Supported Keywords and Generated BSON

## 1. Why Not Look Only at the Method Name?

In the **Derived Queries** chapter of **Spring Data MongoDB**, repositories can derive queries directly from Java method names without writing MongoDB commands manually. For example, `findByStatusAndStockGreaterThanEqual` expresses a filter using property names and a comparison operator. This mechanism makes common CRUD lookups quick and readable.

However, a method that looks grammatically valid in Java does not guarantee a **BSON filter carrying the business meaning you expect**. You must distinguish:

- **Keywords supported by the method-name parser**: `And`, `Or`, `GreaterThan`, `In`, `Containing`, `IsNull`, `OrderBy`, and others.
- **Recognized Java properties**: `name`, `stock`, or `supplier.countryCode`; the property must exist in the model.
- **Actual BSON fields**: `display_name`, `stock_qty`, `supplier.country_code` may differ from Java property names due to `@Field`.
- **Executed MongoDB commands**: filter, sort, limit, skip, projection, and sometimes different commands for `exists` or `count`.
- **Correctness and performance**: null/missing handling, regexes, arrays, indexes, collation, paging, and concurrent reads all affect outcomes.

In this lesson, we build a reference mapping *method name → meaning → equivalent BSON*, then **observe the actual commands** via integration tests. That aligns with Spring Data MongoDB best practices: use repositories for straightforward queries, know when to switch to `MongoTemplate` or aggregation, and diagnose slow or wrong queries accurately.

> Examples target Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. BSON snippets in tables are **semantic illustrations**; drivers may encode regexes, parameters, and count/exists commands differently from Extended JSON below. Use command monitoring or the MongoDB profiler on your exact project versions to inspect the actual BSON sent.

## 2. Sample Data and Mapping Rules

For consistency, we use the `catalog_products` collection. A document has the following BSON shape (omitting `_class` metadata):

~~~json
{
  "_id": "prd-101",
  "sku": "BOTTLE-500",
  "display_name": "Insulated Water Bottle",
  "status": "ACTIVE",
  "stock_qty": 12,
  "priceVnd": 129000,
  "featured": true,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" },
  "tags": ["drinkware", "outdoor"],
  "supplier": {
    "name": "Supplier A",
    "country_code": "VN"
  }
}
~~~

The `archivedAt` field is absent in this document; this matters when evaluating `IsNull` and `Exists`.

**SupplierInfo.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.mapping.Field;

public record SupplierInfo(
        String name,
        @Field("country_code") String countryCode) {
}
~~~

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String sku,
        @Field("display_name") String name,
        String status,
        @Field("stock_qty") int stock,
        long priceVnd,
        boolean featured,
        Instant createdAt,
        Instant archivedAt,
        List<String> tags,
        SupplierInfo supplier) {
}
~~~

All repository examples below live in package `com.example.catalog`, where Spring Boot scans entities and repositories under proper configuration. `@MongoId(FieldType.STRING)` keeps `_id` as BSON String; do not confuse a 24-hex-character string with a BSON ObjectId.

| Java property | Stored BSON field |
|---|---|
| `id` | `_id` |
| `sku` | `sku` |
| `name` | `display_name` |
| `stock` | `stock_qty` |
| `status` | `status` |
| `priceVnd` | `priceVnd` |
| `supplier.countryCode` | `supplier.country_code` |
| `tags` | `tags` |
| `archivedAt` | `archivedAt` |

Spring Data maps **Java property paths to BSON paths** when repositories derive queries from entities. When using the MongoDB shell or raw driver with raw BSON, write the actual stored field names. In the tables below, `...` represents arguments and data-returning methods are assumed to be called on `CatalogProductRepository`.

## 3. How Does the Method-Name Parser Work?

Method name example:

~~~java
List<CatalogProduct> findByStatusAndStockGreaterThanEqual(
        String status, int minimumStock);
~~~

Read as:

1. `find`: selects an entity-returning query operation.
2. `By`: separates the query introducer from the predicate.
3. `Status`: property `status`.
4. `And`: logical conjunction between conditions.
5. `StockGreaterThanEqual`: property `stock` with `>=` comparison.
6. The two Java parameters bind sequentially to the two conditions.

Illustrative MongoDB filter:

~~~json
{
  "status": "ACTIVE",
  "stock_qty": { "$gte": 5 }
}
~~~

Spring Data's parser does not read BSON field names from method names. It resolves Java properties from entity metadata, then the MongoDB mapping layer emits corresponding BSON field names. Thus:

~~~java
// Correct: uses the Java property named name.
List<CatalogProduct> findByName(String name);
~~~

The equivalent MongoDB filter is `{ "display_name": "..." }`, **not** `{ "name": "..." }`. A method like `findByDisplay_name` is not how you write BSON names and may fail to parse as expected.

If a property name is wrong or criteria tokens cannot be parsed, the repository may fail at startup or when queries are lazily initialized. Typical errors involve `PropertyReferenceException`. Never treat successful application startup alone as proof that every method works properly against real data.

## 4. Common Keyword Groups and Equivalent BSON

The tables below show **illustrative filters**. In actual commands, field order inside BSON does not matter for independent `AND` conditions; drivers may also normalize expressions differently. In particular, regexes may be encoded as BSON RegularExpression values rather than separate `$regex` and `$options` Extended JSON fields.

### 4.1. Equality, Inequality, and Comparisons

| Derived method | Meaning | Equivalent BSON filter |
|---|---|---|
| `findBySku("BOTTLE-500")` | Equality | `{ "sku": "BOTTLE-500" }` |
| `findBySkuIs("BOTTLE-500")` | Equivalent to equals | `{ "sku": "BOTTLE-500" }` |
| `findBySkuEquals("BOTTLE-500")` | Equivalent to equals | `{ "sku": "BOTTLE-500" }` |
| `findBySkuNot("X")` | Not equal | `{ "sku": { "$ne": "X" } }` |
| `findByStockGreaterThan(5)` | Greater than | `{ "stock_qty": { "$gt": 5 } }` |
| `findByStockGreaterThanEqual(5)` | Greater than or equal to | `{ "stock_qty": { "$gte": 5 } }` |
| `findByStockLessThan(5)` | Less than | `{ "stock_qty": { "$lt": 5 } }` |
| `findByStockLessThanEqual(5)` | Less than or equal to | `{ "stock_qty": { "$lte": 5 } }` |
| `findByStatusAndStockGreaterThanEqual("ACTIVE", 5)` | Combined with AND | `{ "status": "ACTIVE", "stock_qty": { "$gte": 5 } }` |

Each keyword alters the **operator** on the preceding property, never the field name. For `Instant` timestamps, `Before` and `After` express point-in-time comparisons; verify BSON Date conversion and millisecond precision.

### 4.2. Value Sets, Booleans, and Null

| Method | Interpretation | Equivalent BSON filter |
|---|---|---|
| `findByStatusIn(List.of("ACTIVE", "PENDING"))` | In set | `{ "status": { "$in": ["ACTIVE", "PENDING"] } }` |
| `findByStatusNotIn(List.of("DELETED", "BLOCKED"))` | Not in set | `{ "status": { "$nin": ["DELETED", "BLOCKED"] } }` |
| `findByFeaturedTrue()` | Boolean true | `{ "featured": true }` |
| `findByFeaturedFalse()` | Boolean false | `{ "featured": false }` |
| `findByArchivedAtIsNull()` | Null value or missing field | `{ "archivedAt": null }` |
| `findByArchivedAtIsNotNull()` | Not null | `{ "archivedAt": { "$ne": null } }` |
| `findByArchivedAtExists(true)` | BSON field exists | `{ "archivedAt": { "$exists": true } }` |
| `findByArchivedAtExists(false)` | BSON field does not exist | `{ "archivedAt": { "$exists": false } }` |

**Null does not mean missing field.** In MongoDB, filtering for `null` matches both documents with BSON null and documents missing the field. `$exists: true` also matches `null` values when the key exists. If you need **only explicit BSON null**, write an explicit query combining `$exists` with `null` per server semantics. Never infer from `IsNull` that it matches "only records having the key set to null".

For `$ne` and `$nin`, check exactly how MongoDB treats missing fields; negation operators can return documents missing the field when comparing against non-null values. When null/missing semantics matter, write integration tests with three documents: **missing field, null field, populated field**.

### 4.3. Strings, Regex, and Case-Insensitive Matching

| Method | Meaning | Illustrative BSON filter |
|---|---|---|
| `findByNameStartingWith("Insulated")` | Starts with | `{ "display_name": { "$regex": "^Insulated" } }` |
| `findByNameEndingWith("Bottle")` | Ends with | `{ "display_name": { "$regex": "Bottle$" } }` |
| `findByNameContaining("Water")` | Contains substring | `{ "display_name": { "$regex": ".*Water.*" } }` |
| `findByNameIgnoreCase("INSULATED WATER BOTTLE")` | Exact name match, ignoring case | Anchored start/end regex with option `i` |
| `findByNameContainingIgnoreCase("WATER")` | Contains substring, ignoring case | Substring regex with option `i` |
| `findByNameRegex("^Insulated")` | Uses caller-supplied regex | `{ "display_name": { "$regex": "^Insulated" } }` |

These illustrate **search intent**, not a guarantee that the driver always sends `.*term.*` or `^term` verbatim. Spring Data can escape special input characters for string-matching keywords, whereas `Regex` treats the argument as a regex pattern. Verify actual BSON before relying on a specific optimization shape.

**Important caveats:**

- `Containing` on **strings** is generally regex-based, **not** full-text or linguistic search.
- Unanchored regexes, patterns starting with `.*`, or case-insensitive regexes may fail to leverage B-tree indexes efficiently; check with `explain`.
- For user-supplied input, avoid exposing raw regexes needlessly. Complex regexes burn CPU; enforce length bounds, input validation, and timeouts.
- `IgnoreCase` and **collation** are different mechanisms. To compare/sort text by linguistic rules or leverage collation indexes, choose an explicit mechanism instead of assuming regex `i` covers every requirement.
- For large collections and word searches, consider text indexes or a dedicated search engine; derived `Containing` is no substitute for ranked search.

### 4.4. Nested Property Paths and Arrays

| Method | Expected BSON field | Illustrative filter |
|---|---|---|
| `findBySupplier_CountryCode("VN")` | `supplier.country_code` | `{ "supplier.country_code": "VN" }` |
| `findBySupplierName("A")` | `supplier.name` | `{ "supplier.name": "A" }` |
| `findByTagsIn(List.of("outdoor", "travel"))` | `tags` | `{ "tags": { "$in": ["outdoor", "travel"] } }` |
| `findByIdIn(List.of("prd-101", "prd-102"))` | `_id` | `{ "_id": { "$in": ["prd-101", "prd-102"] } }` |

The underscore in `Supplier_CountryCode` **explicitly marks the property path boundary** when Spring Data parses the method name. It does not represent the BSON underscore; `@Field("country_code")` declares the stored field name.

When `tags` is a String array, `$in` matches if **at least one element** belongs to the target set. That differs from "contains all tags simultaneously", which needs a different operator/logic. For arrays of **subdocuments**, if multiple conditions must hold on the same element, use `$elemMatch` via `MongoTemplate` or `@Query`; do not assume independent dotted-path conditions target the same element.

### 4.5. Value Ranges and AND/OR Precedence

`Between` is supported for comparable types, yet **never guess whether endpoints are inclusive or exclusive** from the English word "between". Inspect the generated BSON and test boundary values, especially with timestamps.

When requirements clearly state "price from 100,000 to 200,000 inclusive on both ends", explicit method names are safer:

~~~java
List<CatalogProduct>
findByPriceVndGreaterThanEqualAndPriceVndLessThanEqual(
        long minimum, long maximum);
~~~

Equivalent filter:

~~~json
{
  "priceVnd": {
    "$gte": 100000,
    "$lte": 200000
  }
}
~~~

Methods using `And` and `Or` do not support **arbitrary grouping parentheses** like a full query language. In particular, mixing `AND`/`OR` groups can cause parser precedence to diverge from business intent. For example, to express:

~~~text
status = "ACTIVE" AND (featured = true OR stock >= 10)
~~~

instead of guessing precedence with a long method name, use `MongoTemplate` to specify grouping explicitly:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> activeFeaturedOrWellStocked(
        MongoTemplate mongo) {
    Criteria condition = new Criteria().andOperator(
            Criteria.where("status").is("ACTIVE"),
            new Criteria().orOperator(
                    Criteria.where("featured").is(true),
                    Criteria.where("stock").gte(10)));

    return mongo.find(Query.query(condition), CatalogProduct.class);
}
~~~

With `CatalogProduct.class`, Spring Data maps `stock` to `stock_qty`. The equivalent MongoDB filter has an `$and` containing the `status` branch and an `$or` over `featured`/`stock_qty`. This is much easier to test than an unreadable repository name.

## 5. Sample Repository Combining the Keywords

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    List<CatalogProduct> findByStatus(String status);

    List<CatalogProduct> findByStatusAndStockGreaterThanEqual(
            String status, int minimumStock);

    List<CatalogProduct> findByPriceVndGreaterThanEqualAndPriceVndLessThanEqual(
            long minimum, long maximum);

    List<CatalogProduct> findByNameContainingIgnoreCase(String text);

    List<CatalogProduct> findBySupplier_CountryCode(String countryCode);

    List<CatalogProduct> findByTagsIn(Collection<String> tags);

    List<CatalogProduct> findByArchivedAtIsNull();

    List<CatalogProduct> findByArchivedAtExists(boolean exists);

    List<CatalogProduct> findByFeaturedTrue();

    boolean existsBySku(String sku);

    long countByStatus(String status);

    List<CatalogProduct> findTop5ByStatusOrderByCreatedAtDesc(String status);

    List<CatalogProduct> findByStatus(String status, Sort sort);

    Page<CatalogProduct> findByStatus(String status, Pageable pageable);
}
~~~

These methods are derived from Java property names, not SQL. Each method needs an **appropriate signature and return type**: `existsBy...` returns boolean, `countBy...` returns a numeric count, and `findBy...` returns entities, collections, or `Page`. A syntactically valid repository method does not guarantee its filter has an index.

Note that `@MongoId(FieldType.STRING)` keeps `_id` mapping consistent. With `@Id String` instead, Spring Data MongoDB can convert valid ObjectId-shaped strings into BSON ObjectIds; always inspect BSON types when ID lookups behave unexpectedly.

## 6. Result-Controlling Keywords: OrderBy, Top, First, Sort, and Pageable

Method names do not only generate **filters** — they also control **sorting and limits**:

~~~java
List<CatalogProduct> findTop5ByStatusOrderByCreatedAtDesc(String status);
~~~

Roughly equivalent to:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1 })
  .limit(5);
~~~

`Top` and `First` cap result counts; `OrderBy...Asc/Desc` define fixed sorting. Without deterministic sorting, a query limiting to N items **does not guarantee the same N items** across calls.

If multiple products share `createdAt`, append a unique secondary sort key (such as `id`) to keep pagination stable, meaning:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(5);
~~~

In Spring Data, pass dynamic `Sort` or `Pageable`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));

Page<CatalogProduct> page = repository.findByStatus(
        "ACTIVE",
        PageRequest.of(0, 20, sort));
~~~

`Sort` uses **Java properties**; `id` maps to `_id`. `PageRequest.of(0, 20, ...)` fetches the first page of size 20. With `Page<T>`, Spring Data may execute an extra count query to compute total elements; never assume one repository call equals a single network round trip.

If total element counts are unnecessary, consider `Slice<T>` or an appropriate paging return type to avoid count overhead; verify support in your repository version and signature. On large datasets with deep pages, `skip` cost grows; seek/keyset pagination or cursor queries may be more suitable.

**Inspecting actual sort:** in MongoDB commands, `sort` is typically a separate command field alongside `filter`, not nested inside `filter`. Likewise `limit` and `skip` appear as fields on the `find` command.

## 7. Existence, Count, and Delete Keywords Have Distinct Semantics

Three methods:

~~~java
boolean existsBySku(String sku);
long countByStatus(String status);
long deleteByStatus(String status);
~~~

express three distinct intents:

| Intent | Illustrative filter | What to note when observing commands |
|---|---|---|
| `existsBySku("BOTTLE-500")` | `{ "sku": "BOTTLE-500" }` | May use an optimized lookup checking for at least one match without loading entities |
| `countByStatus("ACTIVE")` | `{ "status": "ACTIVE" }` | Uses count command or pipeline depending on version; result does not lock data |
| `deleteByStatus("DELETED")` | `{ "status": "DELETED" }` | A **destructive write operation** requiring authorization and safety guards |

In Spring Data MongoDB, `deleteBy...` behavior can vary by **return type** (e.g., returning deleted document count vs. returning the list of deleted entities, where supported). Never infer cost or command count from the word `delete` alone: for bulk deletions, test the exact repository signature, transactions, and lifecycle callbacks.

Never run a derived delete method just to inspect "what BSON does it emit" on shared data. Use an isolated test database and disposable records. For conditional deletes tied to status/version, `MongoTemplate.remove(...)` with an explicit query or a dedicated workflow is often easier to control.

**`existsBy...` does not guarantee safe creation.** Two concurrent requests can both get `false` and then both insert; unique indexes and atomic conditional writes remain the true safeguards at write time.

## 8. How to Verify the Actual BSON Sent

Reading keyword tables helps predict queries, yet "checking supported keywords and generated BSON" requires going beyond **guessing**. Three complementary verification layers exist:

1. **Test repository outputs**: test with boundary values, null, missing fields, casing, and nested fields.
2. **Observe commands sent to MongoDB**: using the MongoDB Java Driver `CommandListener` or query logging enabled in test environments.
3. **Analyze query plans**: run `explain("executionStats")` on representative data to inspect filters, indexes, and keys/documents examined.

### 8.1. Integration Test with Real Data

Spring Boot 3.x provides `@DataMongoTest` to bootstrap repositories and mapping. This annotation **does not start MongoDB by itself**; connect an isolated test database such as MongoDB via Testcontainers.

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class CatalogProductDerivedQueryTest {
    @Autowired
    CatalogProductRepository products;

    @Test
    void queriesMappedFieldsAndNestedProperty() {
        products.deleteAll();
        products.save(new CatalogProduct(
                "prd-101", "BOTTLE-500", "Insulated Water Bottle",
                "ACTIVE", 12, 129000L, true,
                Instant.parse("2026-11-20T08:00:00Z"),
                null,
                List.of("drinkware", "outdoor"),
                new SupplierInfo("Supplier A", "VN")));

        assertThat(products.findByStatusAndStockGreaterThanEqual(
                "ACTIVE", 10)).extracting(CatalogProduct::id)
                .containsExactly("prd-101");

        assertThat(products.findBySupplier_CountryCode("VN"))
                .extracting(CatalogProduct::sku)
                .contains("BOTTLE-500");

        assertThat(products.findByNameContainingIgnoreCase("WATER"))
                .hasSize(1);

        assertThat(products.findByArchivedAtIsNull())
                .extracting(CatalogProduct::id)
                .contains("prd-101");
    }
}
~~~

This test verifies integration-level results and field mapping. If tests run in parallel or share a collection, `deleteAll()` causes interference; isolate databases/collections or manage fixture lifecycles cleanly.

### 8.2. Capturing `CommandStartedEvent` in Tests

The MongoDB Java Driver provides `CommandListener`. Registered on the client via `MongoClientSettingsBuilderCustomizer` (Spring Boot 3.x), the listener captures `find` commands and BSON `filter` documents produced by repositories. This is useful to confirm `stock` became `stock_qty`, `name` became `display_name`, or sort/limit were attached properly.

**Test-only** configuration example:

~~~java
package com.example.catalog;

import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.bson.BsonDocument;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class MongoCommandCaptureConfig {

    @Bean
    FindCommandCapture findCommandCapture() {
        return new FindCommandCapture();
    }

    @Bean
    MongoClientSettingsBuilderCustomizer captureMongoFind(
            FindCommandCapture capture) {
        return settings -> settings.addCommandListener(capture);
    }

    static final class FindCommandCapture implements CommandListener {
        final List<BsonDocument> commands = new CopyOnWriteArrayList<>();

        @Override
        public void commandStarted(CommandStartedEvent event) {
            if ("find".equals(event.getCommandName())) {
                commands.add(BsonDocument.parse(
                        event.getCommand().toJson()));
            }
        }

        @Override
        public void commandSucceeded(CommandSucceededEvent event) {}

        @Override
        public void commandFailed(CommandFailedEvent event) {}

        void clear() {
            commands.clear();
        }
    }
}
~~~

This snippet avoids logging and uses a thread-safe list to prevent concurrency issues when the listener receives multiple commands. When running multiple tests or collections, filter further by collection name and test scope to avoid picking up background commands.

Inspecting the captured command in a dedicated test:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;

@DataMongoTest
@Import(MongoCommandCaptureConfig.class)
class DerivedQueryBsonTest {
    @Autowired CatalogProductRepository products;
    @Autowired MongoCommandCaptureConfig.FindCommandCapture capture;

    @Test
    void recordsMappedFilterInFindCommand() {
        capture.clear();
        products.findByStatusAndStockGreaterThanEqual("ACTIVE", 5);

        BsonDocument command = capture.commands.stream()
                .filter(c -> c.containsKey("find")
                        && c.getString("find").getValue()
                                .equals("catalog_products"))
                .findFirst()
                .orElseThrow();

        BsonDocument filter = command.getDocument("filter");
        assertThat(filter.getString("status").getValue())
                .isEqualTo("ACTIVE");
        assertThat(filter.getDocument("stock_qty")
                .getInt32("$gte").getValue()).isEqualTo(5);
    }
}
~~~

In real test runs, even when zero documents match, the `find` command is still sent and its filter can be verified. If an unexpected command is observed (e.g., `countDocuments` or health checks), verify the command name; never assume `existsBy`/`countBy` always issue `find`.

**Security:** Command monitoring can expose sensitive parameters in filters, updates, or business payloads. Enable it only in controlled test or diagnostic environments, never dump raw query parameters to production logs, and disable or scrub capture when not needed.

### 8.3. Checking the Query Plan

Example using an equivalent MongoDB shell query:

~~~javascript
db.catalog_products.find(
  { status: "ACTIVE", stock_qty: { $gte: 5 } }
).explain("executionStats");
~~~

A candidate index:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, stock_qty: 1 },
  { name: "idx_status_stock" }
);
~~~

Compare `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and execution time with and without the index on representative data volumes. Never draw production performance conclusions from a handful of documents. Remember indexes add write overhead, take disk space, and may not suit every sort order or selectivity profile.

## 9. Recognizing Limits to Avoid Overusing Derived Queries

Derived keywords are convenient for relatively simple criteria. Signs you should switch to `@Query`, `MongoTemplate`, or aggregation:

| Need | Why method names fall short | Better alternative |
|---|---|---|
| Multiple parenthesized AND/OR groups | Cannot clearly express arbitrary logical grouping | `Criteria.andOperator/orOperator` or `@Query` |
| Aggregation with `$group`, `$lookup`, `$facet` | Method names cannot express pipelines | `Aggregation`/`MongoTemplate.aggregate` or `@Aggregation` |
| Object-array queries needing `$elemMatch` | Independent conditions can match different elements | `Criteria.elemMatch` or `@Query` |
| Full-text, ranked, or geo search | Requires specialized syntax/indexes | Dedicated MongoDB query/search APIs |
| Atomic conditional updates | `findBy` only reads data | `MongoTemplate.updateFirst`/`findAndModify` |
| Dynamic filtering across many optional fields | Explosion of repository methods | Criteria query builder or custom repository |
| Deep pagination or complex dynamic sorting | Requires cursor, keyset, and index management | Explicit query and pagination design |

An 80–120 character method name does not become "good practice" simply because Spring Data manages to parse it. Switch to an explicit query whenever logic is hard to audit or generated BSON is unclear.

### `@Query` Does Not Remove the Need to Verify Field Names

Example:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'status': ?0, 'stock_qty': { '$gte': ?1 } }")
List<CatalogProduct> activeWithStock(
        String status, int minimumStock);
~~~

This snippet **illustrates a declaration inside a repository interface** importing `org.springframework.data.mongodb.repository.Query`, not a standalone package-level method. With `@Query`, check the framework's mapping rules for JSON queries and field names; use physical BSON names in raw structures while verifying whether the API remaps properties. When building queries dynamically with strong entity context, `MongoTemplate` with `Criteria.where("stock")` and `CatalogProduct.class` is often easier to control.

## 10. Common Traps When Checking Keywords and BSON

| Mistake | Consequence | How to check / fix |
|---|---|---|
| Writing `findByDisplayName` because BSON is `display_name` when Java property is `name` | Parser fails to find property or queries wrong target | Check entity metadata and use `findByName` |
| Reading `GreaterThan` as inclusive | Off-by-one business bug | Compare `$gt` vs. `$gte` and test at boundaries |
| Testing `Between` only with an interior number | Misses inclusive/exclusive boundary errors | Test both endpoints and inspect BSON |
| Assuming `Containing` uses a full-text index | Regex query scans too much data | Inspect regex, `explain`, and pick suitable search/indexes |
| Assuming `IgnoreCase` equals a collation index | Unexpected execution plan and sort/match behavior | Check regex options, collation, and actual indexes |
| Thinking `IsNull` finds only BSON null fields | Also returns documents missing the field | Test null/missing and add `$exists` when needed |
| Mixing `And`/`Or` without checking grouping | Returns wrong records | Rewrite with explicit `Criteria` parentheses |
| Array conditions without `$elemMatch` | Conditions match two different elements | Write an element-scoped query |
| Inferring performance from short method names | N+1, slow regex, count, or sort bottlenecks | Capture commands, check plans and indexes |
| Assuming `Page` executes only one query | Overlooks count and skip overhead | Observe commands and consider `Slice`/cursors |
| Running `deleteBy` on real data to inspect filters | Unintended data loss | Use an isolated test database only |
| Expecting Extended JSON filters to match byte-for-byte across drivers | Brittle assertions across driver versions | Assert operator structure and semantics instead of fixed strings |

## 11. Practice Exercises

**Exercise 1 — Building a query table.** Using `CatalogProduct` from Section 2, create your own table "method name → property → BSON field → operator" for `findBySku`, `findByNameStartingWith`, `findByStockLessThanEqual`, `findByArchivedAtIsNull`, and `findBySupplier_CountryCode`. Verify the filters via command monitoring.

**Exercise 2 — Testing boundary values.** Insert four products into MongoDB with `stock_qty` equal to 0, 5, 10, and 11. Compare results of `GreaterThan(5)`, `GreaterThanEqual(5)`, `LessThan(10)`, and `LessThanEqual(10)`. Predict and then verify the `$gt`/`$gte`/`$lt`/`$lte` filters.

**Exercise 3 — Null and missing fields.** Create three documents: missing `archivedAt`, `archivedAt: null`, and a BSON Date. Call `findByArchivedAtIsNull`, `findByArchivedAtExists(true)`, and `findByArchivedAtExists(false)`. Record the returned ID sets and explain why.

**Exercise 4 — Nested mapping.** Change `@Field("country_code")` to another field name in an experimental model and re-run `findBySupplier_CountryCode`. Distinguish metadata changes from migrating legacy BSON documents, and inspect the failure mode when old documents remain unmigrated.

**Exercise 5 — Regex and indexes.** Across tens of thousands of product names, compare exact match, prefix, `Containing`, and `ContainingIgnoreCase`. Inspect actual filters, `explain` outputs, and index costs. Propose a long-term text search strategy.

**Exercise 6 — Sorting and pagination.** Write `findTop5ByStatusOrderByCreatedAtDesc` and a `Pageable` query sorting by `createdAt DESC, id ASC`. Inspect commands for `filter`, `sort`, and `limit/skip`; compare command counts between `Page` and a non-counting approach.

**Exercise 7 — Rewriting complex logic.** Express `ACTIVE AND (featured OR stock >= 10)` using `Criteria.andOperator/orOperator`. Insert a document with `featured=true` but `status=DELETED` and prove it is excluded. Explain why a long derived method name can easily misgroup conditions.

## 12. Summary

**Derived queries** in Spring Data MongoDB translate **method-name keywords** into query criteria based on **Java properties**, then apply entity metadata to target **BSON fields**. Common keyword groups include comparisons, value sets, booleans, null/existence, strings/regex, nested properties, sorting/limiting, and count/exists operations.

To validate any query, never stop at reading the method name: **test boundary cases, capture real BSON commands, and inspect indexes and query plans**. Whenever logic requires multiple logical groups, `$elemMatch` on arrays, aggregations, or atomic updates, switch to `MongoTemplate`, `@Query`, or dedicated APIs instead of forcing complex logic into method names.

A readable repository is one where method names, business intent, BSON fields, and test outcomes **all align** — not merely one where Spring Data accepts a long method name.
