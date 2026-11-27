# elemMatch, all, size, and Array Conditions

## 1. Why Does Querying Arrays Require Different Thinking from Scalar Queries?

In the **Query and Criteria** chapter of **Spring Data MongoDB**, arrays are one of the places where it is easiest to write a query that is **syntactically valid yet semantically wrong**. MongoDB lets a BSON field hold an array of numbers, an array of strings, or an array of documents. Operators such as `$elemMatch`, `$all`, and `$size` answer different questions about that array.

Suppose a product has a list of variants by color and warehouse:

~~~json
{
  "_id": "p-101",
  "tags": ["outdoor", "premium"],
  "variants": [
    { "sku": "R-1", "color": "RED", "quantity": 2, "warehouse_code": "HCM" },
    { "sku": "B-1", "color": "BLUE", "quantity": 15, "warehouse_code": "HN" }
  ],
  "ratings": [2, 5]
}
~~~

Three seemingly similar requirements have distinct semantics:

1. **Is there at least one variant that is both red and has at least 10 items?** Use `$elemMatch` to force the conditions onto **the same element** of `variants`.
2. **Does the product have both tags `outdoor` and `premium`?** Use `$all`, not `$in`.
3. **Does the product have exactly two variants?** Use `$size: 2`, not a length comparison via `$gte` directly inside `$size`.

If you write:

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
});
~~~

MongoDB can return `p-101`: the **red** element has quantity 2, while the **blue** element has quantity 15. The two dot-path conditions are satisfied by **two different elements**. To require *the same variant*, you must express it explicitly with `$elemMatch`.

This lesson aims to explain array operator semantics on BSON, write `Query`/`Criteria` via `MongoTemplate`, verify field name mapping, handle empty/null/missing cases, and analyze performance with **multikey indexes**. It goes beyond syntax to show how to test and catch false positives.

> Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. BSON structures in this lesson are illustrative representations matching the schema shown here; verify exact behavior against your project's MongoDB/Spring Data version and real data.

## 2. Operator Selection Table by Business Question

| Question | Typical BSON Condition | Key Semantics |
|---|---|---|
Does `tags` contain tag `outdoor`? | `{ "tags": "outdoor" }` | Scalar equality matches if any array element equals it |
Does it have tag `outdoor` **or** `travel`? | `{ "tags": { "$in": ["outdoor", "travel"] } }` | Any matching value |
Does it have both `outdoor` **and** `premium`? | `{ "tags": { "$all": ["outdoor", "premium"] } }` | Every required value must be present, regardless of order |
Does it have exactly 2 tags? | `{ "tags": { "$size": 2 } }` | Array length is strictly 2 |
Is there a red variant? | `{ "variants.color": "RED" }` | At least one element has color red |
Is there a variant that is **red and quantity ≥ 10**? | `{ "variants": { "$elemMatch": { "color": "RED", "quantity": { "$gte": 10 } } } }` | Both conditions on the same element |
Is there a rating in [4, 5)? | `{ "ratings": { "$elemMatch": { "$gte": 4, "$lt": 5 } } }` | A single number in the array satisfies both bounds |
Does the `tags` field exist? | `{ "tags": { "$exists": true } }` | Checks field presence, not array length |

`$in`, `$all`, and `$elemMatch` all apply in array contexts yet **do not replace one another**. The right query must accurately reflect whether conditions must hold across *any element*, *all required values*, or *one single element*.

## 3. Shared Spring Data MongoDB Model

To run the code, assume the application includes `spring-boot-starter-data-mongodb`, a valid MongoDB URI, and package `com.example.catalog` within Spring Boot's component scan. Each type is placed in its corresponding Java file; the article uses `MongoTemplate` to build typed queries.

**Variant.java** — an embedded subdocument inside the array:

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.mapping.Field;

public record Variant(
        String sku,
        String color,
        int quantity,
        @Field("warehouse_code") String warehouseCode) {
}
~~~

**CatalogProduct.java** — the root document:

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
        @Field("display_name") String name,
        String status,
        List<String> tags,
        List<Variant> variants,
        List<Integer> ratings,
        Instant createdAt) {
}
~~~

Deliberate design choices:

- `@MongoId(FieldType.STRING)` keeps `_id` as a BSON String; conditions on Java property `id` map to `_id`.
- `@Field("display_name")` and `@Field("warehouse_code")` demonstrate mapping applies at both root and embedded document levels.
- `tags` is `List<String>`, `ratings` is `List<Integer>`, and `variants` is `List<Variant>`; they are stored as BSON arrays with different element types.
- `Variant` needs no separate `@Document` annotation because it is embedded inside `CatalogProduct`. It has no standalone collection or `_id`.
- In the example, `quantity` is non-negative and `createdAt` is creation time; these are business rules to validate at the application layer, not guarantees enforced by `List`.

### Three Documents for Result Comparison

**Product p-101** has a *low-stock* red variant and a *well-stocked* blue variant:

~~~json
{
  "_id": "p-101",
  "display_name": "Insulated Bottle",
  "status": "ACTIVE",
  "tags": ["outdoor", "premium"],
  "variants": [
    { "sku": "R-1", "color": "RED", "quantity": 2, "warehouse_code": "HCM" },
    { "sku": "B-1", "color": "BLUE", "quantity": 15, "warehouse_code": "HN" }
  ],
  "ratings": [2, 5],
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**Product p-102** has a well-stocked red variant:

~~~json
{
  "_id": "p-102",
  "display_name": "Outdoor Bag",
  "status": "ACTIVE",
  "tags": ["outdoor", "premium", "new"],
  "variants": [
    { "sku": "R-2", "color": "RED", "quantity": 12, "warehouse_code": "HCM" },
    { "sku": "B-2", "color": "BLUE", "quantity": 0, "warehouse_code": "HN" }
  ],
  "ratings": [4],
  "createdAt": { "$date": "2026-11-20T09:00:00Z" }
}
~~~

**Product p-103** has empty arrays:

~~~json
{
  "_id": "p-103",
  "display_name": "Notebook",
  "status": "INACTIVE",
  "tags": ["premium"],
  "variants": [],
  "ratings": [],
  "createdAt": { "$date": "2026-11-20T10:00:00Z" }
}
~~~

The queries below will explicitly show which IDs must match. When inspecting results from the MongoDB shell, use the BSON names `display_name` and `warehouse_code`; in Java code passing `CatalogProduct.class`, prefer Java property paths and let Spring Data perform mapping.

## 4. Checking Element Membership: Equality, $in, and Dot Notation

### 4.1. Matching a Single Value in an Array

For a scalar array such as `tags`:

~~~javascript
db.catalog_products.find({ tags: "outdoor" });
~~~

The query returns `p-101` and `p-102` because each `tags` array contains an element equal to `"outdoor"`. A scalar equality filter **does not require the entire array to equal the scalar**.

Equivalent Java code:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> tagged(
        MongoTemplate mongo, String tag) {
    return mongo.find(
            Query.query(Criteria.where("tags").is(tag)),
            CatalogProduct.class);
}
~~~

When you require **the entire array to have an exact structure and order**, comparing against another array has its own order-sensitive semantics. Do not use it to replace `$all` when order does not matter. If data has nested arrays, MongoDB's array comparison rules must also be checked against the actual schema.

### 4.2. $in Is OR Over a Set of Values

~~~javascript
db.catalog_products.find({
  tags: { $in: ["outdoor", "travel"] }
});
~~~

A product is returned if it has **at least one tag** in the search set. This means "has outdoor **or** travel", not requiring both.

Spring Data Criteria:

~~~java
Query query = Query.query(
        Criteria.where("tags").in("outdoor", "travel"));
List<CatalogProduct> matches =
        mongo.find(query, CatalogProduct.class);
~~~

If the API accepts a client-supplied list of values, validate element count, string lengths, and data types. An `$in` with thousands of elements can bloat the query and hurt efficiency; batch or redesign the query when exceeding normal usage bounds.

### 4.3. Dot Notation on Document Arrays

~~~javascript
db.catalog_products.find({
  "variants.color": "RED"
});
~~~

Dot notation finds documents with **at least one array element** having `color = RED`. In Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("variants.color").is("RED"));
List<CatalogProduct> redProducts =
        mongo.find(query, CatalogProduct.class);
~~~

This works well when there is only one condition to check per variant. However, when combining different conditions, you must decide whether they must hold **on the same element** or simply **somewhere in the array**.

## 5. $elemMatch: Conditions Must Hold on the Same Element

### 5.1. Counter-Example: Two Dot Paths Can Match Two Different Elements

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
});
~~~

With the data in section 3, this query returns both `p-101` and `p-102`:

- `p-101`: the red variant has `quantity = 2`, while the blue variant has `quantity = 15`. Two independent conditions still match.
- `p-102`: the red variant has `quantity = 12`. Both conditions match on the same variant.

If a user wants to buy **a red product with at least 10 units in stock**, `p-101` is a **false positive**.

### 5.2. Writing Correctly with $elemMatch

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: {
      color: "RED",
      quantity: { $gte: 10 }
    }
  }
});
~~~

The result contains only `p-102`. Under `$elemMatch`, both `color` and `quantity` must be satisfied by **a single document element** in `variants`.

Java with `Criteria.elemMatch(...)`:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CatalogProduct> redVariantsWithStock(
        MongoTemplate mongo, int minimumQuantity) {
    Criteria sameVariant = Criteria.where("variants").elemMatch(
            Criteria.where("color").is("RED")
                    .and("quantity").gte(minimumQuantity));

    return mongo.find(
            Query.query(sameVariant), CatalogProduct.class);
}
~~~

With `minimumQuantity = 10`, the result is `p-102`. Note that `Criteria.where("variants")` specifies the **array** field name; the argument inside `elemMatch` describes the conditions on **an element**.

### 5.3. Checking Nested Fields Annotated with @Field

To find products having a variant **in warehouse HCM and in stock**, add `warehouseCode`:

~~~java
Criteria inStockAtHcm = Criteria.where("variants").elemMatch(
        Criteria.where("warehouseCode").is("HCM")
                .and("quantity").gt(0));

Query query = Query.query(inStockAtHcm);
List<CatalogProduct> products =
        mongo.find(query, CatalogProduct.class);
~~~

In Java, the property is `warehouseCode`; in BSON, it is `warehouse_code` due to the annotation on `Variant`. With typed query `CatalogProduct.class`, Spring Data applies the subdocument's mapping metadata to build the equivalent condition:

~~~json
{
  "variants": {
    "$elemMatch": {
      "warehouse_code": "HCM",
      "quantity": { "$gt": 0 }
    }
  }
}
~~~

Do not assume `query.getQueryObject()` before execution reflects **all** mapped field names; entity mapping is applied along the execution path. When you need confirmation, inspect the BSON command or run tests against raw documents.

### 5.4. $elemMatch with Number Arrays

`$elemMatch` is not limited to object arrays. For `ratings`, requiring **one rating from 4 up to under 5**:

~~~javascript
db.catalog_products.find({
  ratings: {
    $elemMatch: { $gte: 4, $lt: 5 }
  }
});
~~~

Result `p-102` (rating 4), whereas `p-101` does not match even though `[2, 5]` has one element under 5 and one element 4 or higher.

In Spring Data:

~~~java
Criteria oneRatingInRange = Criteria.where("ratings")
        .elemMatch(new Criteria().gte(4).lt(5));

List<CatalogProduct> rated =
        mongo.find(Query.query(oneRatingInRange), CatalogProduct.class);
~~~

Compared to two independent conditions:

~~~javascript
db.catalog_products.find({
  ratings: { $gte: 4, $lt: 5 }
});
~~~

when a field is an array, independent conditions should not be interpreted as forcing the same single value to satisfy both bounds. `$elemMatch` clearly expresses the "same element" requirement.

### 5.5. $elemMatch Also Requires the Field to Be an Array

A document where `variants` is a **single object** rather than an array might match certain dot-notation conditions, whereas `$elemMatch` requires an array element to inspect. This helps surface schema discrepancies. Do not rely on `$elemMatch` to automatically coerce a single object into an array.

With only a single condition on a nested field, dot notation and `$elemMatch` can sometimes return similar results when schemas are consistent, yet should not be treated as equivalent in every case involving **missing arrays, wrong types, or special values**.

## 6. $all: Array Contains Every Required Value

To find products that have both the `outdoor` tag and the `premium` tag:

~~~javascript
db.catalog_products.find({
  tags: { $all: ["outdoor", "premium"] }
});
~~~

The results are `p-101` and `p-102`. `p-103` only has `premium`, so it does not match.

Spring Data Criteria:

~~~java
Query query = Query.query(
        Criteria.where("tags").all("outdoor", "premium"));

List<CatalogProduct> matches =
        mongo.find(query, CatalogProduct.class);
~~~

`$all` does not require tags to be stored in the same order as the input. An array `["premium", "outdoor"]` also satisfies it. Nor is it an **exact-set equality** check: `["premium", "outdoor", "new"]` still matches, which is why `p-102` is returned.

### 6.1. Comparing all, in, and Equality

| `tags` Data | `tags: "outdoor"` | `$in: ["outdoor", "travel"]` | `$all: ["outdoor", "premium"]` |
|---|---|---|---|
| `["outdoor", "premium"]` | Yes | Yes | Yes |
| `["outdoor", "premium", "new"]` | Yes | Yes | Yes |
| `["premium"]` | No | No | No |
| `["travel"]` | No | Yes | No |
| `[]` | No | No | No |

If the collection contains duplicate tags, `$all` checks **the presence of the required values**, not how many times a tag appears. If you need "tag A appears twice", the data model or counting logic must represent that requirement explicitly.

### 6.2. Do Not Turn an Empty Selection List into an Empty $all

In a search API, if the user selects no tags, **do not automatically generate `$all: []`** expecting MongoDB to treat it as "no filter". Decide explicitly: does an empty tag list mean **omit the tags condition**, or is it an input error? Only add `Criteria.where("tags").all(...)` when appropriate.

Dynamic query building example:

~~~java
import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Query searchByAllTags(Collection<String> requiredTags) {
    Query query = Query.query(Criteria.where("status").is("ACTIVE"));

    if (requiredTags != null && !requiredTags.isEmpty()) {
        query.addCriteria(Criteria.where("tags").all(requiredTags));
    }
    return query;
}
~~~

This is a Query builder method. The application must bound list length and enforce tag normalization rules; otherwise unexpected filters or oversized queries can arise.

### 6.3. $all with Multiple $elemMatch Clauses

When you need products that have **an in-stock red variant** *and* **an in-stock blue variant**, you can write:

~~~javascript
db.catalog_products.find({
  variants: {
    $all: [
      { $elemMatch: { color: "RED", quantity: { $gt: 0 } } },
      { $elemMatch: { color: "BLUE", quantity: { $gt: 0 } } }
    ]
  }
});
~~~

`p-101` matches because it has a red variant with 2 items and a blue variant with 15 items. `p-102` does not match because its blue variant has `quantity = 0`.

**Two `$elemMatch` expressions inside `$all` can be satisfied by two different elements.** This precisely expresses "there must exist one element satisfying group A and one element satisfying group B". By contrast, **a single `$elemMatch`** containing both groups only applies when both sets of conditions can be true simultaneously on one element.

## 7. $size: Array Length Must Equal an Exact Value

MongoDB uses `$size` to check the count of **direct elements** in an array:

~~~javascript
db.catalog_products.find({
  variants: { $size: 2 }
});
~~~

Results are `p-101` and `p-102`, as each document has two variants. `p-103` has `variants: []`, so it only matches `$size: 0`.

In Java:

~~~java
Query withTwoVariants = Query.query(
        Criteria.where("variants").size(2));

List<CatalogProduct> products =
        mongo.find(withTwoVariants, CatalogProduct.class);
~~~

`$size` counts elements directly under `variants`—it **does not** count fields inside a variant, sum all `quantity` values, or count documents in the collection. When each element is a nested document, array length still counts each document as one element.

### 7.1. There Is No $size: { $gte: ... } Syntax

The requirement "has at least 3 variants" **cannot be written as**:

~~~javascript
// Invalid semantics/syntax: $size takes an exact integer, not $gte.
db.catalog_products.find({
  variants: { $size: { $gte: 3 } }
});
~~~

If you need a relative count, choose another solution:

- A filter on the **third element's index** like `{ "variants.2": { "$exists": true } }` can detect arrays of length at least 3 in a consistent array schema; this is an array-index technique, not a general counting query for arbitrary field types.
- Use `$expr` combining the aggregation `$size` operator with a comparison.
- If filtering by length is frequent, consider storing a `variantCount` field kept consistently in sync when adding/removing variants and indexing it. Denormalized count fields can drift if any write path bypasses the synchronization mechanism.

Example of `$expr` with `$ifNull` to treat missing or null arrays as empty:

~~~javascript
db.catalog_products.find({
  $expr: {
    $gte: [
      { $size: { $ifNull: ["$variants", []] } },
      3
    ]
  }
});
~~~

This snippet assumes `variants`, when present, is **an array or null**. If malformed schema data stores `variants` as a non-array scalar/document, `$size` inside the expression can throw an error; validate or guard with `$isArray`/`$cond` appropriately.

### 7.2. Performance Cost of $size

A multikey index does not maintain a per-document element-count key allowing `$size` to look up length directly from the index. Array-length queries may need to inspect candidate documents and struggle to use indexes for the **length predicate**. Measure with `explain("executionStats")`, especially when collections are large and `$size` is the primary filter.

If the business requirement is "at least one variant" and the schema guarantees `variants` is always an array, approaches like `"variants.0": { "$exists": true }` can work, though you should test null/missing cases and exercise care if the schema is inconsistent.

## 8. Combining elemMatch, all, and size with Filters and Sort

Example: find **ACTIVE products** having both `outdoor` and `premium` tags, plus **an in-stock variant at warehouse HCM**:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductArraySearchService {
    private final MongoTemplate mongo;

    public ProductArraySearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> findAvailableAtHcm() {
        Criteria conditions = new Criteria().andOperator(
                Criteria.where("status").is("ACTIVE"),
                Criteria.where("tags").all("outdoor", "premium"),
                Criteria.where("variants").elemMatch(
                        Criteria.where("warehouseCode").is("HCM")
                                .and("quantity").gt(0)));

        Query query = Query.query(conditions);
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        query.limit(20);

        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

The code uses `Criteria.andOperator` to combine document-level conditions. `$elemMatch` scopes the **same-element** boundary solely to the warehouse and stock conditions; the tag requirement still applies to the separate `tags` array.

Equivalent BSON intent:

~~~json
{
  "$and": [
    { "status": "ACTIVE" },
    { "tags": { "$all": ["outdoor", "premium"] } },
    {
      "variants": {
        "$elemMatch": {
          "warehouse_code": "HCM",
          "quantity": { "$gt": 0 }
        }
      }
    }
  ]
}
~~~

Across the three sample documents, both `p-101` and `p-102` match because both have at least one HCM variant with quantity greater than 0. If the condition is changed to `quantity >= 10`, only `p-102` matches.

When building filters from HTTP requests, never accept arbitrary field names or BSON operators from clients and splice them into raw JSON. Whitelist supported conditions, validate values, add the tenant condition from the authenticated context, and cap `limit`.

## 9. $elemMatch in Filters Differs from $elemMatch in Projections

A very easy point to confuse:

- **`$elemMatch` in a query filter:** determines **which documents match** based on at least one array element satisfying the condition.
- **`$elemMatch` in a `find` projection:** restricts **the returned array** to **the first matching element** according to the projection condition.

### 9.1. Filters Do Not Automatically Trim Arrays in Results

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: { color: "RED", quantity: { $gte: 10 } }
  }
});
~~~

The query returns only `p-102`, yet the returned document **can still contain the entire `variants` array** with both red and blue variants unless the command specifies an appropriate projection.

### 9.2. Projection Returning One Matching Element

~~~javascript
db.catalog_products.find(
  { _id: "p-102" },
  {
    display_name: 1,
    variants: { $elemMatch: { color: "RED", quantity: { $gte: 10 } } }
  }
);
~~~

When a matching element exists, `variants` in the projection output contains only **the first element satisfying the condition**, not every red element. If the application needs all matching elements, consider aggregation `$filter` and define the projection output explicitly.

Spring Data `Query.fields()` provides `elemMatch` projection APIs in supported versions. However, filtering and projection must be tested separately: a repository API returning the right entity does not automatically mean the client only receives the array elements of interest.

**Never save back** an entity loaded with a field projection missing other elements via `save` as if it were the complete document. That can replace or erase the unloaded elements.

## 10. Empty Arrays, Null, Missing Fields, and Mismatched Data Types

Not every historical document follows a clean schema. The following variants must be distinguished:

~~~json
{ "_id": "legacy-missing" }
~~~

~~~json
{ "_id": "legacy-null", "tags": null }
~~~

~~~json
{ "_id": "legacy-empty", "tags": [] }
~~~

~~~json
{ "_id": "legacy-one", "tags": ["outdoor"] }
~~~

| Condition | Missing | Null | `[]` | `["outdoor"]` |
|---|---|---|---|---|
| `{ "tags": { "$exists": true } }` | No | Yes | Yes | Yes |
| `{ "tags": null }` | Yes | Yes | No | No |
| `{ "tags": { "$size": 0 } }` | No | No | Yes | No |
| `{ "tags": "outdoor" }` | No | No | No | Yes |
| `{ "tags": { "$all": ["outdoor"] } }` | No | No | No | Yes |

If you specifically need **an empty array**, `$size: 0` expresses intent far more clearly than `tags = null`. If you need to distinguish **missing field** from **null value**, use appropriate operators such as combining `$exists` with null checks; avoid assuming the two cases are identical.

A scalar field `tags: "outdoor"` can match string equality yet is not a valid schema array. When filters depend on array type, you may need `$type: "array"` or schema validation/migration so two representations are not mixed.

### 10.1. Nulls Inside Arrays and Subdocument Elements Missing Properties

An array can contain `null` or a subdocument missing a field. With `List<Variant>`, when materializing into Java, the converter may materialize elements with null/default values or fail if constructors/constraints are incompatible. Querying `variants.quantity` also differs semantically from an element truly having quantity 0.

Do not use primitive `int quantity` in a record while assuming missing fields in historical documents are always handled safely. If legacy data has an inconsistent schema, run a migration or design nullable types and validation explicitly.

### 10.2. Array Ordering and Duplicates

MongoDB preserves array element order when storing documents. However:

- `$all` checks value presence, not matching order.
- `$size` counts duplicate elements as well.
- `$elemMatch` checks whether an element satisfies the condition, without requiring it to be first, unless projected in a specific way.
- If business logic relies on variant order, array position is meaningful data; array updates must preserve the ordering policy or use an explicit `position` field.

## 11. Multikey Indexes and Array Query Performance

When creating an index on a field holding an array, MongoDB uses a **multikey index**. Instead of a single index key for the whole array, element values participate in the index to support query conditions.

Candidate index examples:

~~~javascript
db.catalog_products.createIndex(
  { status: 1, tags: 1 },
  { name: "idx_status_tags" }
);

db.catalog_products.createIndex(
  { status: 1, "variants.color": 1, "variants.quantity": 1 },
  { name: "idx_status_variant_color_qty" }
);
~~~

The second index references two fields **sourced from the same `variants` array**. Compound multikey indexes restrict indexing **multiple independent arrays** within a single document; you cannot arbitrarily combine arbitrary array fields into a compound index and expect MongoDB to allow it.

### 11.1. $elemMatch Also Affects How MongoDB Evaluates Index Bounds

When multiple conditions target fields inside the same array of documents, `$elemMatch` not only fixes *same-element* semantics, it can also help the query planner combine **tighter index bounds** on a suitable multikey index. Still, actual optimization depends on index paths, array structure, MongoDB version, filter, and selectivity. Do not assume every `$elemMatch` query is automatically faster.

Compare:

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: {
      color: "RED",
      quantity: { $gte: 10 }
    }
  }
}).explain("executionStats");
~~~

with:

~~~javascript
db.catalog_products.find({
  "variants.color": "RED",
  "variants.quantity": { $gte: 10 }
}).explain("executionStats");
~~~

The two queries **have different semantics**, so do not evaluate performance in isolation from correctness. Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and execution time on representative data.

### 11.2. Indexes Do Not Automatically Optimize Every $all or $size Case

- For `$all` on tags, a multikey index on `tags` can help, though effectiveness depends on the number of required tags, tag frequencies, and how the planner intersects bounds.
- For `$size`, an index does not maintain each document's array length to answer length predicates via a normal index lookup.
- When sorting by `createdAt` in a query that also filters an array, a different index or an in-memory sort stage may be needed; index design must follow **real queries**, not a single filter in isolation.
- Indexing long arrays increases index entry counts and update costs; bound array sizes and measure write amplification.

If an array holds tens of thousands of elements and grows continually, consider **extracting it to a separate collection** with a foreign key referencing the parent document. MongoDB caps a single BSON document at **16 MiB**; long before hitting that limit, index and update overhead may already become problematic.

## 12. When to Use Aggregation Instead of Simple Criteria?

`Criteria` with `$elemMatch`, `$all`, and `$size` fits well when the goal is **selecting documents**. However, if you need to:

1. Return **only the variants** matching a condition, instead of the whole array.
2. Count **in-stock variants** rather than total variants.
3. Sum `quantity` across variants belonging to a warehouse.
4. Group products by attributes inside an array.

then aggregation is usually clearer. For example, using `$filter` to keep only variants with `quantity >= 10` in the output:

~~~javascript
db.catalog_products.aggregate([
  { $match: { status: "ACTIVE" } },
  {
    $project: {
      display_name: 1,
      availableVariants: {
        $filter: {
          input: "$variants",
          as: "v",
          cond: { $gte: ["$$v.quantity", 10] }
        }
      }
    }
  }
]);
~~~

Here `$match` selects documents, while `$project` with `$filter` transforms the array **in the output**. If documents have null/missing or wrongly typed `variants`, verify how `$filter` behaves and apply an appropriate fallback policy. `$lookup` is a separate stage for joining collections, not a direct substitute for array operators when data is already embedded.

In Spring Data, you can build pipelines with `Aggregation`/`MongoTemplate.aggregate`; exact builder syntax depends on the transformations and version. Do not try to cram complex element filtering or summation logic into a derived repository method when an explicit pipeline is much easier to test.

## 13. Impact on Array Updates and Consistency

Querying the right element **does not automatically mean** updating the right element. For example:

~~~javascript
db.catalog_products.updateOne(
  {
    _id: "p-102",
    variants: { $elemMatch: { sku: "R-2", quantity: { $gte: 2 } } }
  },
  { $inc: { "variants.$.quantity": -2 } }
);
~~~

This example uses the **positional operator `$`** bound to the array element matched by the query condition in MongoDB-supported update forms. Cases involving multiple arrays, multiple elements, or complex conditions may require `$[]` or `$[identifier]` with `arrayFilters`.

An explicit option for modifying multiple elements conditionally:

~~~javascript
db.catalog_products.updateOne(
  { _id: "p-102" },
  { $set: { "variants.$[v].quantity": 0 } },
  {
    arrayFilters: [
      { "v.warehouse_code": "HN" }
    ]
  }
);
~~~

This snippet **sets the quantity of every variant in warehouse HN to 0**, not just the first element. The difference between the filter selecting **the document** and the array filter selecting **elements to modify** must be clearly understood.

With `MongoTemplate` `Update` and array filters, verify field-name mapping rules in array filters for your API/version; some array-filter paths accept BSON/raw documents without remapping property names. When `@Field("warehouse_code")` is present, inspect the actual BSON command before deploying.

MongoDB guarantees atomicity for an update operation **on a single document**, yet does not prevent lost updates across two separate read-modify-write operations. When `quantity` represents stock, include the sufficient-stock condition directly inside the update filter and check matched/modified counts rather than reading first and subtracting afterward.

## 14. Testing Array Queries on Real MongoDB

Unit tests that merely invoke the `Criteria` builder do not prove Spring Data maps BSON correctly with `@Field`, nor that MongoDB evaluates `$elemMatch` properly on real arrays. Write integration tests against a real MongoDB instance, such as Testcontainers. In Spring Boot 3.x, `@DataMongoTest` configures the test MongoDB slice but **does not start a MongoDB server by itself**.

### 14.1. Seeding Data Deliberately Prone to False Positives

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ArrayCriteriaIntegrationTest {

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void seed() {
        // Delete only inside an isolated test database.
        mongo.remove(new Query(), CatalogProduct.class);

        mongo.insert(new CatalogProduct(
                "p-101", "Insulated Bottle", "ACTIVE",
                List.of("outdoor", "premium"),
                List.of(
                        new Variant("R-1", "RED", 2, "HCM"),
                        new Variant("B-1", "BLUE", 15, "HN")),
                List.of(2, 5),
                Instant.parse("2026-11-20T08:00:00Z")));

        mongo.insert(new CatalogProduct(
                "p-102", "Outdoor Bag", "ACTIVE",
                List.of("outdoor", "premium", "new"),
                List.of(
                        new Variant("R-2", "RED", 12, "HCM"),
                        new Variant("B-2", "BLUE", 0, "HN")),
                List.of(4),
                Instant.parse("2026-11-20T09:00:00Z")));

        mongo.insert(new CatalogProduct(
                "p-103", "Notebook", "INACTIVE",
                List.of("premium"),
                List.of(),
                List.of(),
                Instant.parse("2026-11-20T10:00:00Z")));
    }

    @Test
    void elemMatchRequiresTheSameVariant() {
        Query twoIndependentPaths = Query.query(
                Criteria.where("variants.color").is("RED")
                        .and("variants.quantity").gte(10));

        List<String> looselyMatchedIds =
                mongo.find(twoIndependentPaths, CatalogProduct.class)
                        .stream().map(CatalogProduct::id).toList();
        assertThat(looselyMatchedIds)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query sameElement = Query.query(
                Criteria.where("variants").elemMatch(
                        Criteria.where("color").is("RED")
                                .and("quantity").gte(10)));

        List<String> strictlyMatchedIds =
                mongo.find(sameElement, CatalogProduct.class)
                        .stream().map(CatalogProduct::id).toList();
        assertThat(strictlyMatchedIds)
                .containsExactly("p-102");
    }

    @Test
    void allSizeAndScalarElemMatchHaveDifferentMeanings() {
        Query hasAllTags = Query.query(
                Criteria.where("tags").all("outdoor", "premium"));
        assertThat(mongo.find(
                hasAllTags, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query hasTwoVariants = Query.query(
                Criteria.where("variants").size(2));
        assertThat(mongo.find(
                hasTwoVariants, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactlyInAnyOrder("p-101", "p-102");

        Query ratingInRange = Query.query(
                Criteria.where("ratings")
                        .elemMatch(new Criteria().gte(4).lt(5)));
        assertThat(mongo.find(
                ratingInRange, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactly("p-102");
    }

    @Test
    void mapsNestedPropertyNameToActualBsonField() {
        Query atHcm = Query.query(
                Criteria.where("variants").elemMatch(
                        Criteria.where("warehouseCode").is("HCM")
                                .and("quantity").gte(10)));

        assertThat(mongo.find(atHcm, CatalogProduct.class))
                .extracting(CatalogProduct::id)
                .containsExactly("p-102");

        Document raw = mongo.getCollection("catalog_products")
                .find(new Document("_id", "p-102")).first();
        assertThat(raw).isNotNull();
        List<Document> rawVariants =
                raw.getList("variants", Document.class);
        assertThat(rawVariants).hasSize(2);
        assertThat(rawVariants.get(0).getString("warehouse_code"))
                .isEqualTo("HCM");
        assertThat(rawVariants.get(0).containsKey("warehouseCode"))
                .isFalse();
    }
}
~~~

The test is structured so that a **semantically wrong** query (`variants.color` and `variants.quantity` independently) returns more results than the **semantically right** query (`$elemMatch`). This kind of test is far more valuable than only checking that one product matches.

If tests run in parallel, use isolated databases/collections instead of `remove(new Query(), ...)` on a shared collection. Results are asserted as ID sets when queries have no sort, avoiding reliance on MongoDB's natural return order.

### 14.2. Checking Null/Missing with Raw BSON

To test legacy documents missing an array, insert raw BSON into the **test** collection:

~~~java
mongo.getCollection("catalog_products").insertOne(
        new Document("_id", "legacy-missing")
                .append("status", "ACTIVE"));

boolean missingTags = mongo.exists(
        Query.query(Criteria.where("tags").exists(false)),
        CatalogProduct.class);

assertThat(missingTags).isTrue();
~~~

This snippet is just an additional illustration **inside a test** having `MongoTemplate` and AssertJ. Use `mongo.exists(...)` to check the condition without materializing a `CatalogProduct` with missing fields. If you need to target a specific document, include an ID condition so you do not accidentally match another record.

### 14.3. Observing BSON and Query Plans

With the driver, a `CommandListener` can subscribe to `CommandStartedEvent` to inspect `find` commands and their `filter` field. When verifying that `warehouseCode` was mapped to `warehouse_code`, capture the actual command sent to the test database; do not merely log `query.toString()` and assume all mappings were applied.

In the MongoDB shell, run:

~~~javascript
db.catalog_products.find({
  variants: {
    $elemMatch: { color: "RED", quantity: { $gte: 10 } }
  }
}).explain("executionStats");
~~~

From there, compare examined keys/documents, indexes, and latency. When filters contain user data or sensitive fields, do not dump full commands into production logs without a protection policy.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
Combining `variants.color` and `variants.quantity` thinking they match one element | False positives when conditions match across two elements | Use a single `$elemMatch` for conditions that must hold together |
Confusing `$in` with `$all` | OR becomes AND or vice versa | Explicitly state "at least one" vs "all values" |
Assuming `$all` requires an exact set with no extra values | Returns documents with extra tags | If exact-set is needed, add length/normalization conditions |
Assuming `$size` sums `quantity` | Returns variant count instead of total stock | Use aggregation `$sum` or a maintained total field |
Writing `$size: { $gte: 3 }` | Invalid query | Use `$expr`/`$size` or a count-field pattern |
Using `tags: null` to find empty arrays | Conflates null/missing with empty | Use `$size: 0` and test the schema |
Assuming field presence means non-empty array | Confuses empty arrays and nulls | Use appropriate array length/type conditions |
Overlooking `@Field` on subdocuments | Raw queries using `warehouseCode` fail | Check the actual `warehouse_code` BSON field |
Testing only single-element arrays | Fails to catch cross-element matching bugs | Seed arrays with multiple opposing elements |
Thinking `$elemMatch` filter trims returned arrays | Returns full arrays with unwanted items | Separate filter, projection, and aggregation `$filter` |
Building compound indexes on multiple independent arrays | Violates multikey constraints or incurs high write cost | Design indexes following actual data paths |
Assuming `$size` is fully index-optimized | Scans too many documents | Measure `explain`, consider a synchronized count field |
Saving an entity with only a partially loaded array | Loses unloaded elements when replacing document | Use targeted updates/`arrayFilters` or load fully with concurrency control |
Embedding unboundedly growing arrays | Large documents, higher read/write cost, risk hitting 16 MiB | Bound array sizes or extract to a separate collection |

## 16. Practice Exercises

**Exercise 1 — Matching the Exact Same Element.** Create a document with a RED variant of quantity 2 and a BLUE variant of quantity 15. Run `variants.color = RED` combined with `variants.quantity >= 10`, then rewrite it using `$elemMatch`. Explain why the results change.

**Exercise 2 — Tag Sets.** Given `tags = ["outdoor", "premium", "new"]`, compare the results of `$in` and `$all` when requiring `["outdoor", "premium"]`. Reverse the tag order and add a fourth tag; explain the difference between subset and exact-set.

**Exercise 3 — Array Size.** Write `Criteria.where("variants").size(0)`, `size(2)`, and a query finding at least 3 elements. Test empty arrays, nulls, missing fields, and 3-document arrays.

**Exercise 4 — Nested @Field.** Rename Java property `warehouseCode` to another property in an experiment while keeping BSON field `@Field("warehouse_code")`. Write a typed query with `MongoTemplate` and inspect the raw BSON. Explain why editing an annotation does not migrate old documents automatically.

**Exercise 5 — Rating Ranges.** Use `ratings = [2, 5]` and `ratings = [4]`. Compare a query with two independent conditions against `$elemMatch` for the range `[4, 5)`. Use an integration test to prove only one rating satisfies both bounds.

**Exercise 6 — Returning Only Matching Elements.** Write an `$elemMatch` filter finding documents with an in-stock RED variant, then use aggregation `$filter` to return only RED variants. Distinguish "matching documents" from "filtered output arrays".

**Exercise 7 — Indexes and explain.** Create an index on `status`, `variants.color`, `variants.quantity`; compare dot-path queries and `$elemMatch` on data with many variants. Record `keysExamined`, `docsExamined`, timing, and actual results. Do not conclude a query is "faster" if it returns the wrong set of documents.

**Exercise 8 — Updating Variants.** Design a command decrementing an SKU's quantity only when enough stock exists. Compare the array positional operator with `arrayFilters`, define atomic conditions, and check matched/modified counts. Test two concurrent requests subtracting stock from the same variant.

## 17. Key Takeaways

In **Spring Data MongoDB**, array queries must accurately express **the relationship between elements and conditions**:

- `$in`: contains **at least one** value in the set.
- `$all`: array contains **every required value**, regardless of order and still permitting extra values.
- `$size`: count of direct array elements **equals an exact** integer.
- `$elemMatch`: there exists **one element** simultaneously satisfying all inner conditions, preventing false positives from different elements.

With `MongoTemplate` and `Criteria`, write **Java properties** on typed entities and verify how `@Field` maps to BSON, especially for subdocuments. Do not confuse `$elemMatch` in filters with projections, do not treat `$size` as a range operator, and do not assume multikey indexes solve every array query.

Finally, deliberately test **multi-element opposing arrays, empty arrays, nulls, missing fields, wrongly typed data, and concurrent updates**. Result correctness always comes first before optimizing with multikey indexes, projections, or aggregation.
