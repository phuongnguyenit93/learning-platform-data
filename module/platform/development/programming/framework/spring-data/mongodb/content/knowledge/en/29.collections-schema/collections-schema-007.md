# Collation for Collections, Queries, and Aggregations

> **Chapter:** Collections and Schema  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and manipulate data via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Objective:** Understand collation at the collection, index, and operation levels; configure string comparison rules accurately for language, case, and accents; use `Collation`, `Query.collation(...)`, `@Document`, `@Query`, and `AggregationOptions`; verify impact on `$match`, `$sort`, `$group`, unique indexes, query plans, and migrations.

## 1. Problem: One String, Multiple Potentially Valid Matches

Suppose a store has three product names:

~~~javascript
{ _id: "p701", display_name: "cafe" }
{ _id: "p702", display_name: "CAFÉ" }
{ _id: "p703", display_name: "Café" }
~~~

The question "find products named `cafe`" **has no single answer** until comparison rules are defined:

- **Binary comparison (`simple`):** `"cafe"` differs from `"CAFÉ"` and `"Café"`.
- **Case-insensitive yet accent-sensitive** (e.g., `locale:"en", strength:2`): `"CAFÉ"` equals `"Café"`; `"cafe"` does not equal `"Café"`.
- **Both case-insensitive and accent-insensitive** (e.g., `locale:"en", strength:1`): all three are treated as equal for collation-aware comparisons.

MongoDB's **collation** feature defines these rules using ICU (International Components for Unicode). Collation affects not only `find`, but also **equality matching, sorting, grouping, certain conditional updates/deletes, and index uniqueness constraints**.

~~~mermaid
flowchart TD
    A["App wants to compare display_name"] --> B{"Effective collation?"}
    B --> C["simple: binary comparison"]
    B --> D["en + strength 2: ignore case, keep accents"]
    B --> E["en + strength 1: ignore case and accents"]
    C --> F["$match / $sort / $group"]
    D --> F
    E --> F
    F --> G["Results + ability to use matching index"]
~~~

**Key idea:** collation is a **comparison rule**; it does not alter strings stored inside documents, does not turn `"CAFÉ"` into `"cafe"`, and is not a full-text search engine.

## 2. Structure of a Collation Document

MongoDB represents collation using a document:

~~~javascript
{
  locale: "en",
  strength: 2,
  caseLevel: false,
  caseFirst: "off",
  numericOrdering: false,
  alternate: "non-ignorable",
  backwards: false,
  normalization: false
}
~~~

`locale` is **required** whenever supplying collation. Other options are optional; **defaults can depend on the locale**. Use `{locale:"simple"}` when binary comparison is needed.

| Attribute | Purpose | Example |
| --- | --- | --- |
| `locale` | Language/ICU rules | `"en"`, `"fr"`, `"vi"`, `"simple"` |
| `strength` | Sensitivity to characters, accents, case | `1`, `2`, `3` |
| `caseLevel` | Whether to consider case separately at strength 1/2 | `true` or `false` |
| `caseFirst` | Upper/lower ordering preference when applicable | `"upper"`, `"lower"`, `"off"` |
| `numericOrdering` | Compares non-negative integer digit sequences numerically | `true` |
| `alternate` | Handling of whitespace/punctuation | `"shifted"` or `"non-ignorable"` |
| `maxVariable` | Characters treated as variable when `alternate:"shifted"` | `"space"`, `"punct"` |
| `backwards` | Evaluates accents from end of string, used in some language rules | `true` |
| `normalization` | Checks/normalizes Unicode during comparison | `true` |

### 2.1. Strength 1, 2, and 3

| Level | Distinguishes Base Letters | Distinguishes Accents/Diacritics | Distinguishes Case by Default |
| --- | --- | --- | --- |
| `strength:1` | Yes | No | No |
| `strength:2` | Yes | Yes | No |
| `strength:3` | Yes | Yes | Yes |

At strength 1/2, `caseLevel:true` can be enabled to add case sensitivity. Strengths 4/5 also exist for specialized ICU needs; do not pick them arbitrarily if business rules do not require them.

**Do not assume Vietnamese characters follow English comparison rules.** Examples here use locale `en` so results on `cafe/Café` are clear. Vietnamese applications should select locale `vi` when appropriate, while explicitly testing `đ`, accented characters, and Unicode normalization against real data.

### 2.2. Numeric Ordering Does Not Turn Strings into Numbers

When `numericOrdering:true`, **contiguous substrings of non-negative integer digits** are compared by numeric value. For instance, `"item2"` sorts before `"item10"`.

Limitations to keep in mind:

- Does not parse `-2.5` as a complete negative or decimal number.
- Does not treat periods, commas, `+`/`-` signs, or scientific notation as arithmetic.
- Never use `numericOrdering` instead of real numeric BSON types for prices, quantities, or range queries.

### 2.3. One Operation Has Only One Collation

MongoDB applies **a single collation to the entire operation**; you cannot assign different collations per field in one `find` or per stage in one `aggregate`.

~~~javascript
// There is no syntax to use strength 1 for name and
// strength 3 for category in a single standard find().
db.products.find({
  name: "cafe",
  category: "Drink"
}).collation({ locale: "en", strength: 1 });
~~~

Here both collation-aware string comparisons share strength 1. If one field is a technical code needing binary comparison while another is a display name needing language comparison, you may need **two queries**, an additional **normalized key field**, or a different schema/index design.

## 3. Collation Scope: Collection, Index, Operation

MongoDB supports configuring collation at these key locations:

| Scope | How It Is Set | Scope of Effect |
| --- | --- | --- |
| **Collection** | `db.createCollection(...,{collation:...})` | Default for operations/indexes unless overridden |
| **Index** | `createIndex(...,{collation:...})` | Index keys, comparisons, and uniqueness per index collation |
| **Operation** | `find(...).collation(...)`, `aggregate(...,{collation:...})` | Overrides collection default **for that operation** |
| **Spring Data entity** | `@Document(collation=...)` | Metadata for mapped operations and corresponding collection/index creation when executed via proper paths |
| **Spring Data query** | `Query.collation(...)`, `@Query(collation=...)` | Rules for a single query |
| **Spring Data aggregation** | `AggregationOptions.builder().collation(...)`, `@Aggregation(collation=...)` | Rules for the entire pipeline |

### 3.1. Precedence on the MongoDB Server

1. If the **operation specifies a collation**, use the operation's collation.
2. Otherwise, if the **collection has a default collation**, use the collection default.
3. If neither specifies one, use **simple/binary**.

**An index does not impose its collation on a query merely by existing.** An index carries its own collation to serve compatible operations; the query's effective collation must match for the index to assist string comparisons.

### 3.2. Collation Does Not Automatically Propagate Everywhere

For example, if a collection defaults to `en/strength 2` while a query specifies `en/strength 1`, the query executes under **strength 1** despite the collection's original setting.

An `en/strength 2` index **does not turn a strength 1 query into strength 2**. To leverage an index for strength 1 string matching, you need a matching index or a different query design.

## 4. Fixture: Collection with Default Collation

Run these commands only on an **isolated test database**. Do not touch live product collections; fixed IDs will trigger duplicate key errors if re-inserted.

### 4.1. Creating the Collection Before Inserting

~~~javascript
use spring_data_mongodb_lab

db.createCollection("catalog_collation_demo_007", {
  collation: {
    locale: "en",
    strength: 2
  }
});

const products = db.catalog_collation_demo_007;
~~~

This collection uses a collation that is **case-insensitive yet still accent-sensitive** for collation-aware string comparisons.

### 4.2. Inserting Data

~~~javascript
products.insertMany([
  {
    _id: "p701",
    tenant_id: "t01",
    display_name: "cafe",
    category: "Drink",
    code: "item2",
    price_vnd: 50000
  },
  {
    _id: "p702",
    tenant_id: "t01",
    display_name: "CAFÉ",
    category: "drink",
    code: "item10",
    price_vnd: 60000
  },
  {
    _id: "p703",
    tenant_id: "t01",
    display_name: "Café",
    category: "DRINK",
    code: "item3",
    price_vnd: 65000
  },
  {
    _id: "p704",
    tenant_id: "t01",
    display_name: "Tea",
    category: "Food",
    code: "item20",
    price_vnd: 30000
  },
  {
    _id: "p705",
    tenant_id: "t01",
    display_name: "tea",
    category: "food",
    code: "item11",
    price_vnd: 32000
  },
  {
    _id: "p706",
    tenant_id: "t02",
    display_name: "cafe",
    category: "Drink",
    code: "item1",
    price_vnd: 55000
  }
]);
~~~

| ID | Tenant | Name | Category | Code |
| --- | --- | --- | --- | --- |
| `p701` | t01 | cafe | Drink | item2 |
| `p702` | t01 | CAFÉ | drink | item10 |
| `p703` | t01 | Café | DRINK | item3 |
| `p704` | t01 | Tea | Food | item20 |
| `p705` | t01 | tea | food | item11 |
| `p706` | t02 | cafe | Drink | item1 |

Tenant filtering is **independent of collation**: multi-tenant logic must always restrict to the authorized tenant. Never allow lenient name matching to bleed across tenants.

### 4.3. Inspecting Default Collation

~~~javascript
const infos = db.getCollectionInfos({
  name: "catalog_collation_demo_007"
});

printjson(infos[0].options.collation);
// Shows locale "en" and strength 2 if the collection was created properly.
~~~

If the collection **already exists**, calling `db.createCollection` with the same name fails; it does not "fix collation" on an existing collection. Never drop shared collections just to redo a demo.

## 5. `find`: Default Matching and Overrides

### 5.1. Using Default Collation `en/strength 2`

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "cafe" },
  { _id: 1, display_name: 1 }
);
// p701: "cafe".
~~~

`"CAFÉ"` and `"Café"` carry the `é` accent, so they differ from `"cafe"` when strength 2 still considers diacritics. They remain equivalent **to each other** under case-insensitive matching.

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "Café" },
  { _id: 1, display_name: 1 }
);
// p702 and p703.
~~~

### 5.2. Overriding to Strength 1

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "cafe" },
  { _id: 1, display_name: 1 }
).collation({
  locale: "en",
  strength: 1
});
// p701, p702, p703.
~~~

The tenant filter still holds. Removing the tenant filter would also match `p706` from t02.

### 5.3. Overriding to Simple/Binary

~~~javascript
products.find(
  { tenant_id: "t01", display_name: "Café" },
  { _id: 1, display_name: 1 }
).collation({ locale: "simple" });
// Only p703, because the string matches identically by binary comparison.
~~~

`Collation.simple()` in Spring Data corresponds to this rule. Do not confuse `simple` with "use collection default": **simple is an explicit binary rule**, and can override a non-simple collection default.

### 5.4. Comparing Three Outcomes

| Query in t01 | Effective Collation | Matching IDs |
| --- | --- | --- |
| `display_name:"cafe"` | Collection default en/2 | `p701` |
| `display_name:"Café"` | Collection default en/2 | `p702,p703` |
| `display_name:"cafe"` | Explicit en/1 | `p701,p702,p703` |
| `display_name:"Café"` | Explicit simple | `p703` |

**Important:** collation does not alter returned values: `p702` still returns `display_name:"CAFÉ"`, never transformed into `"Café"` or `"cafe"`.

## 6. How Collation Affects `sort`

### 6.1. Language-Aware String Sorting

~~~javascript
products.find(
  { tenant_id: "t01" },
  { _id: 1, display_name: 1 }
).sort({ display_name: 1, _id: 1 });
~~~

With collection default en/2, sorting by `display_name` uses ICU rules. `CAFÉ` and `Café` compare equal under strength 2; sorting solely by `display_name` leaves their relative order indeterminate. Adding `_id` acts as a **tie-breaker** for stable output order.

Do not assume Unicode code-point order matches linguistic order; `simple` versus ICU sorting can yield different orderings.

### 6.2. Sorting with `numericOrdering`

Fixture values:

~~~text
item2, item10, item3, item20, item11
~~~

Under ordinary string sorting (without numeric ordering), `item10` precedes `item2` because `"1" < "2"` at the first differing character.

~~~javascript
products.find(
  { tenant_id: "t01" },
  { _id: 0, code: 1 }
).sort({ code: 1, _id: 1 })
 .collation({
   locale: "en",
   strength: 2,
   numericOrdering: true
 });

// Expected:
// item2, item3, item10, item11, item20
~~~

`numericOrdering` only helps sorts/searches compare **strings containing integer digit runs**; it does not change BSON types into numbers. Never store `"2"`/`"10"` as strings in place of numeric types for arithmetic.

### 6.3. Unstable Sorts When Multiple Values Compare Equal

If `display_name` is compared at strength 1, `"cafe"`, `"CAFÉ"`, and `"Café"` compare equal. Without a tie-breaker, actual order can shift with query plans and concurrent data changes.

For pagination, include a **unique, stable** tie-breaker field such as `_id`. Even so, stable sorting does not turn multi-request pagination into an immutable snapshot if inserts/deletes occur between page reads.

## 7. Aggregation: One Collation for the Entire Pipeline

An aggregation pipeline's `$match`, `$group`, and `$sort` stages all execute within **a single operation**. That operation's collation affects:

- `$match` string comparisons.
- `$sort` string ordering.
- `$group` merging string keys treated as equal under the collation.
- Certain string comparisons in expressions and other stages per MongoDB rules.

### 7.1. Grouping by Category Using Collection Default

~~~javascript
products.aggregate([
  { $match: { tenant_id: "t01" } },
  {
    $group: {
      _id: "$category",
      products: { $sum: 1 }
    }
  },
  { $sort: { products: -1 } }
]);
~~~

With default `en/strength 2`:

- `"Drink"`, `"drink"`, `"DRINK"` are equivalent → **group of 3 products**.
- `"Food"` and `"food"` are equivalent → **group of 2 products**.

**The displayed group `_id` can keep whichever spelling appeared from the input documents** (such as `"Drink"` or `"drink"`); never rely on MongoDB normalizing casing. Assert only group counts and totals. If an API requires a canonical label, store a normalized field or add an explicit projection.

### 7.2. Overriding with `strength:1`

~~~javascript
products.aggregate(
  [
    { $match: { tenant_id: "t01" } },
    {
      $group: {
        _id: "$display_name",
        products: { $sum: 1 }
      }
    }
  ],
  { collation: { locale: "en", strength: 1 } }
);
~~~

In t01, `"cafe"`, `"CAFÉ"`, and `"Café"` collapse into **one group of 3**. `"Tea"` and `"tea"` form **one group of 2**. Thus output has **2 groups**, even though t01 has 5 products.

### 7.3. Overriding with `simple`

~~~javascript
products.aggregate(
  [
    { $match: { tenant_id: "t01" } },
    { $group: { _id: "$category", products: { $sum: 1 } } }
  ],
  { collation: { locale: "simple" } }
);
~~~

In t01, there are five distinct category spellings:

~~~text
Drink, drink, DRINK, Food, food
~~~

Hence simple grouping yields **5 groups of 1 document each**. That contrasts with **2 groups (3 and 2)** under en/2.

### 7.4. Why Does Collation Matter for Reporting?

If a "products by category" report previously separated `Drink` and `drink`, switching collation can merge them. **Group counts change without altering a single document.** Whenever reports feed billing, commissions, analytics, or reconciliation, specify **collation in the report contract** and regression-test numbers after changes.

You cannot set different collations on separate stages of a single aggregate command. If truly different comparisons are needed, split into separate pipelines/operations or store pre-normalized fields.

## 8. Index-Level Collation and Index Usability

### 8.1. Indexes Inherit the Collection Default

~~~javascript
products.createIndex(
  { tenant_id: 1, display_name: 1 },
  { name: "ix_tenant_name_en2" }
);
~~~

Because the collection defaults to `en/strength 2`, an index created without its own collation **inherits the collection default**.

~~~javascript
products.getIndexes();
// Inspect key, name, and collation of each index.
~~~

### 8.2. Creating Indexes with the Same Keys but Different Collations

~~~javascript
products.createIndex(
  { tenant_id: 1, display_name: 1 },
  {
    name: "ix_tenant_name_en1",
    collation: { locale: "en", strength: 1 }
  }
);
~~~

MongoDB permits multiple indexes with the **same key pattern** and **different collations**, provided they have **distinct index names**. They can serve queries needing different comparison rules, at the expense of storage and index write maintenance.

### 8.3. Condition for Using an Index on String Comparisons

A query using `en/strength 1` **cannot rely on an `en/strength 2` index to evaluate string comparisons under a different collation**. Likewise, a `simple` query does not match an `en/strength 2` index's string rules.

~~~javascript
products.find({
  tenant_id: "t01",
  display_name: "cafe"
}).collation({
  locale: "en",
  strength: 1
}).explain("executionStats");
~~~

Inspect `winningPlan`, `indexName`, `totalKeysExamined`, and `totalDocsExamined`. **Do not assert** the planner always picks a specific index on tiny fixtures: a collection scan can legitimately be cheaper. What is verifiable is the **collation compatibility** between index and query.

### 8.4. Compound Indexes with Non-String Parts

In some cases, an index with a mismatched collation may still assist **non-string** fields in a prefix under an eligible query plan; that does not mean it supports incompatible string comparisons. Evaluate based on **field types, index key order, and actual `explain` output**.

### 8.5. Collation-Aware Keys Have Storage Cost

Linguistic collation indexes store ICU collation keys, which can be larger than binary keys. Maintaining `simple`, `en/1`, and `en/2` indexes on the same key pattern multiplies **disk usage, RAM footprint, and write amplification**. Create multiple indexes only when workload and performance testing justify them.

## 9. Unique Indexes with Collation: Case-Insensitive Uniqueness

Collation does not only affect reads. A **unique index** applies **its own collation** to decide whether string keys collide.

### 9.1. Independent Fixture

~~~javascript
const customers = db.customers_collation_unique_007;

customers.createIndex(
  { tenant_id: 1, username: 1 },
  {
    name: "ux_tenant_username_ci",
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
);

customers.insertOne({
  _id: "u701",
  tenant_id: "t01",
  username: "Alice"
});

customers.insertOne({
  _id: "u702",
  tenant_id: "t02",
  username: "alice"
});
// Succeeds: different tenant.

customers.insertOne({
  _id: "u703",
  tenant_id: "t01",
  username: "alice"
});
// E11000: t01 already has Alice; strength 2 collation ignores case.
~~~

This is a **compound unique index scoped by tenant**. If the index were only `{username:1}`, two different tenants using equivalent usernames would collide **across the entire collection**.

### 9.2. Accent-Sensitive vs. Accent-Insensitive

At `strength:2`, `"Alice"` and `"alice"` collide on case, yet accented vs. unaccented strings can still differ depending on locale. At `strength:1`, collation ignores accent differences evaluated at the secondary level as well.

Therefore, **changing a unique index's collation changes which keys count as duplicates**. Before deploying a new policy on populated collections, check for duplicates under the **new comparison rules**, resolve conflicts cleanly, and then coordinate the index change.

### 9.3. Uniqueness Is Not "Relaxed" by Query Collation

If a query runs with `simple` against a collection with an `en/2` unique index, that **does not stop the `en/2` unique index from enforcing collisions**. Uniqueness rules belong to the index, while query collation controls how queries match.

### 9.4. Collation Does Not Replace Validation

A case-insensitive unique index does not validate username length, allowed characters, email domains, normalization rules, or tenant authorization. For real usernames/emails:

- Enforce valid string inputs and consistent normalization.
- Pick locale/collation matching business requirements.
- Scope indexes by tenant and use partial filters if fields are optional.
- Catch `E11000`/`DuplicateKeyException` on write rather than relying on `existsBy...` before insert.

## 10. Spring Data: `Collation` and Fluent Options

Spring Data MongoDB provides `org.springframework.data.mongodb.core.query.Collation`.

~~~java
import org.springframework.data.mongodb.core.query.Collation;

Collation binary = Collation.simple();

Collation caseInsensitive = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());

Collation accentAndCaseInsensitive = Collation.of("en")
    .strength(Collation.ComparisonLevel.primary());

Collation numericNames = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary())
    .numericOrderingEnabled();
~~~

`Collation` instances are **configuration values** for operations; instead of concatenating raw JSON strings, fluent builders make intent clear in code.

### 10.1. Numeric Strength vs. Named Comparison Levels

~~~java
Collation strengthTwo = Collation.of("en").strength(2);

Collation namedLevel = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());
~~~

Both express strength 2. `ComparisonLevel` reads clearly in code reviews, whereas integers align directly with MongoDB's BSON syntax.

### 10.2. Building a Rule Set with Multiple Options

~~~java
Collation rules = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary())
    .numericOrderingEnabled()
    .normalizationEnabled();
~~~

Enable normalization only when Unicode data requirements justify it; it adds processing overhead that should be measured under load. Never use it as a substitute for identifier normalization or application validation.

### 10.3. Printing Collation BSON for Debugging

~~~java
org.bson.Document bson = rules.toDocument();
System.out.println(bson.toJson());
~~~

In real systems, avoid logging full queries containing personal data or tokens. A collation document itself is normally just configuration, whereas commands containing filters can carry sensitive values.

## 11. Creating Collections via `MongoTemplate` with the Right Collation

### 11.1. Entity and `@Document(collation=...)`

~~~java
// ProductDocument.java
package com.example.collation;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(
    collection = "catalog_collation_demo_007",
    collation = "{ 'locale': 'en', 'strength': 2 }"
)
public class ProductDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("display_name")
    private String displayName;

    private String category;
    private String code;

    @Field("price_vnd")
    private long priceVnd;

    protected ProductDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getDisplayName() { return displayName; }
    public String getCategory() { return category; }
    public String getCode() { return code; }
    public long getPriceVnd() { return priceVnd; }
}
~~~

`@Document(collation=...)` is **Spring Data metadata** applied to mapped queries/indexes/collection creation when invoked via supporting APIs. It **does not guarantee** the MongoDB collection already has that default if the collection was created **implicitly** on first write.

### 11.2. Explicit Collection Creation

~~~java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;

// template is an injected MongoTemplate.
Collation defaultRules = Collation.of("en")
    .strength(Collation.ComparisonLevel.secondary());

if (!template.collectionExists(ProductDocument.class)) {
    template.createCollection(
        ProductDocument.class,
        CollectionOptions.just(defaultRules)
    );
}
~~~

In production, treat collection creation as **coordinated migration/DDL**; plain `if (!exists)` is a learning example, **not a lock against startup races** across multiple instances. Choose creation timing, verify DDL privileges, and inspect actual options before opening traffic.

### 11.3. The Auto-Create Trap

If code calls:

~~~java
template.insert(productDocument);
~~~

when the collection **does not exist yet**, MongoDB creates it implicitly. Spring Data documentation notes that **collation from `@Document` is not used when MongoDB implicitly creates a collection on first interaction**.

Therefore, `@Document(collation=...)` **does not replace** explicit collection creation when a database-level default collation is mandatory.

### 11.4. Default Collation Cannot Be Changed In-Place

MongoDB requires defining a collection's default collation at **creation time**; once created, you cannot alter default collation via ordinary `collMod`.

To change the default on a production collection:

- Analyze queries and indexes relying on the old default.
- Prepare a new collection with the new default and an appropriate copy/migration strategy.
- Check for unique conflicts under the new collation.
- Coordinate cutover, DDL privileges, backfill, metadata verification, and rollback.
- If only **certain operations** need different rules, consider operation-level collation and matching indexes instead of replacing the collection.

**Never `drop()` a production collection to "fix collation"**: doing so destroys data and indexes without a safe migration workflow.

## 12. Spring Data `MongoTemplate` Queries with Collation

### 12.1. Default Query per Entity/Collection

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
);

List<ProductDocument> values =
    template.find(query, ProductDocument.class);
~~~

With `ProductDocument.class`, Spring Data maps `tenantId` to `tenant_id` and `displayName` to `display_name`. Collation follows metadata/operation/server precedence; to guarantee specific rules for a use case, set it **explicitly** on `Query`.

### 12.2. Explicit Query Collation

~~~java
Query flexible = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
).collation(
    Collation.of("en")
        .strength(Collation.ComparisonLevel.primary())
);

List<ProductDocument> matches =
    template.find(flexible, ProductDocument.class);

// On the original fixture: p701, p702, p703 (order unspecified).
~~~

If ordering is needed:

~~~java
import org.springframework.data.domain.Sort;

flexible.with(Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
));
~~~

Query collation governs **all string comparisons in the operation**, including sorting. Never pass a separate collation just for sort—MongoDB forbids multiple collations in one operation.

### 12.3. Intentionally Using Binary

~~~java
Query exact = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("Café")
).collation(Collation.simple());

List<ProductDocument> rows =
    template.find(exact, ProductDocument.class);
// Only p703 on the fixture.
~~~

This makes intent clear whenever values like `SKU`, tokens, or technical codes require binary matching.

### 12.4. Collation and Filtered Updates/Deletes

`Query.collation(...)` is not restricted to `find`. For update/delete APIs supporting collation, string filters obey the same comparison rules:

~~~java
Query byName = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("displayName").is("cafe")
).collation(
    Collation.of("en")
        .strength(Collation.ComparisonLevel.primary())
);

// Illustrates scope risk: query can match 3 documents.
// Do NOT run updateMulti if you only meant to edit 1 product!
// template.updateMulti(byName, new Update().set("priceVnd", 0),
//                      ProductDocument.class);
~~~

Switching from binary to strength 1 can broaden the matched set; this is especially hazardous with `updateMulti` or `remove`. Before any wide write operation, inspect predicates, tenant scope, expected affected counts, and privileges.

## 13. Collation on Spring Data Repositories

### 13.1. Static `@Query(collation=...)`

~~~java
// ProductRepository.java
package com.example.collation;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'displayName': ?1 }",
        collation = "{ 'locale': 'en', 'strength': 1 }"
    )
    List<ProductDocument> findAccentInsensitive(
        String authorizedTenantId,
        String displayName
    );

    @Query(
        value = "{ 'tenantId': ?0, 'displayName': ?1 }",
        collation = "{ 'locale': 'en', 'strength': 2 }"
    )
    List<ProductDocument> findCaseInsensitive(
        String authorizedTenantId,
        String displayName
    );
}
~~~

Spring Data binds parameters and maps Java properties inside `@Query` using entity metadata. `@Query(collation=...)` specifies rules for **that method**, which can differ from `@Document` or the collection default.

### 13.2. Passing Dynamic `Collation` as a Method Parameter

Spring Data MongoDB supports a `Collation` parameter on repository query methods:

~~~java
// Add to ProductRepository:
List<ProductDocument> findByTenantIdAndDisplayName(
    String tenantId,
    String displayName,
    org.springframework.data.mongodb.core.query.Collation collation
);
~~~

Usage:

~~~java
Collation primary = Collation.of("en").strength(1);

List<ProductDocument> products = repository
    .findByTenantIdAndDisplayName("t01", "cafe", primary);
~~~

This is a derived finder; `Collation` is a **special query-control parameter**, not a property parsed in `By...`.

### 13.3. Precedence in Spring Data Repositories

Per Spring Data documentation, for repository queries:

1. Explicit non-null **`Collation` method argument** overrides.
2. **Method-level collation** declared via `@Collation` / `@Query(collation=...)`.
3. **Domain metadata** `@Document(collation=...)`.
4. **Collection/server default** when no application option is sent.

`@Collation` directly on a method is an alternative with annotation-specific precedence; when combining multiple annotations, check your exact Spring Data version docs and verify the generated query.

Do not assume `@Document` "locks" collation for all methods; a repository method or parameter can still override it.

### 13.4. Testing Both Methods and Metadata

Running the same input `("t01","cafe")`:

- `findCaseInsensitive` with en/2: **p701**.
- `findAccentInsensitive` with en/1: **p701,p702,p703**.
- Derived finder with parameter `Collation.simple()`: **p701**.

Checking only output counts suffices for a tiny demo, but production tests should also verify **IDs**, tenant scope, and index plans.

## 14. Spring Data Aggregation with `AggregationOptions.collation`

### 14.1. Aggregation DTO

~~~java
// CategoryTotal.java
package com.example.collation;

public record CategoryTotal(
    String categoryName,
    long total
) {
}
~~~

### 14.2. Typed Aggregation Using `en/strength 2`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Collation;

TypedAggregation<ProductDocument> pipeline =
    Aggregation.newAggregation(
        ProductDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.group("category")
            .count().as("total"),
        Aggregation.project("total")
            .and("_id").as("categoryName")
            .andExclude("_id")
    ).withOptions(
        AggregationOptions.builder()
            .collation(
                Collation.of("en")
                    .strength(Collation.ComparisonLevel.secondary())
            )
            .build()
    );

List<CategoryTotal> totals =
    template.aggregate(pipeline, CategoryTotal.class)
        .getMappedResults();
~~~

On the t01 fixture, this produces **two groups** with counts **3** and **2**. `categoryName` may preserve the casing from a representative document; when asserting expected outputs, normalize **only in tests** or check counts rather than assuming MongoDB lowercases group keys.

### 14.3. Overriding Aggregation to Binary

~~~java
TypedAggregation<ProductDocument> strictGroups =
    Aggregation.newAggregation(
        ProductDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.group("category")
            .count().as("total"),
        Aggregation.project("total")
            .and("_id").as("categoryName")
            .andExclude("_id")
    ).withOptions(
        AggregationOptions.builder()
            .collation(Collation.simple())
            .build()
    );
~~~

Grouping by `category` now distinguishes five spellings—`Drink`, `drink`, `DRINK`, `Food`, `food`—yielding **5 groups**. The underlying BSON fields did not change; only the operation's grouping rule changed.

### 14.4. `strictMapping` and Collation Are Separate Concerns

~~~java
AggregationOptions options =
    AggregationOptions.builder()
        .strictMapping()
        .collation(Collation.of("en").strength(2))
        .build();
~~~

`strictMapping()` validates property/domain mapping references when Spring Data renders the pipeline; `collation(...)` controls **string comparison on the MongoDB server**. Enabling strict mapping does not make queries case-insensitive, and setting collation does not catch misspelled property names.

## 15. `@Aggregation(collation=...)` on Repositories

Repository aggregations also accept a `collation` attribute to pair comparison rules with the pipeline.

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductReportRepository
        extends MongoRepository<ProductDocument, String> {

    @Aggregation(
        pipeline = {
            "{ '$match': { 'tenantId': ?0 } }",
            "{ '$group': { '_id': '$category', " +
                "'total': { '$sum': 1 } } }",
            "{ '$project': { '_id': 0, " +
                "'categoryName': '$_id', 'total': 1 } }"
        },
        collation = "{ 'locale': 'en', 'strength': 2 }"
    )
    List<CategoryTotal> groupCategories(String tenantId);
}
~~~

This still returns **two groups** for t01. `@Aggregation` pipelines receive domain-type mapping where supported by the framework; output DTO fields must match the final stage's `categoryName` and `total` aliases.

### 15.1. When Dynamic Collation Is Needed

The `@Aggregation` annotation also supports parameter placeholders in `collation` per the documentation:

~~~java
@Aggregation(
    pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$category', 'total': { '$sum': 1 } } }"
    },
    collation = "?1"
)
List<org.bson.Document> groupByDynamicRules(
    String tenantId,
    String locale
);
~~~

This example varies only the **locale** string accepted by the framework; detailed options like strength require JSON collation strings or appropriate objects. Never pass arbitrary client-supplied locales without an **allowlist**, since query rules, index usage, and resource cost can shift significantly.

When dynamic collation logic is complex, `MongoTemplate` with typed `AggregationOptions` is usually easier to control and test.

### 15.2. Do Not Confuse `Pageable` with Collation

`Pageable`/`Sort` on repository aggregations affect output sorting/skip/limit per `@Aggregation`'s contract, but they **do not supply collation**. If string sorting requires specific linguistic rules, supply collation via the annotation or options.

## 16. Views, Text Indexes, and `$regex`: Limitations

### 16.1. Views Have Their Own Collation

MongoDB views do not inherit the source collection's default collation automatically. A view created without collation uses **simple**; a view created with collation uses that collation and does not permit per-operation overrides the way regular collections do.

When pipelines join multiple views (e.g., `$lookup`/`$graphLookup`), MongoDB enforces collation compatibility across views. Verify this before building cross-collection reports.

### 16.2. `$regex` Does Not Become Collation-Aware

~~~javascript
products.find({
  display_name: { $regex: "^caf", $options: "i" }
}).collation({
  locale: "en",
  strength: 1
});
~~~

Do not expect `$regex` to apply `strength:1` accent-folding like equality matches. MongoDB `$regex` is **not collation-aware**, and **case-insensitive collation indexes** do not accelerate `$regex` merely via collation.

For exact case/accent-insensitive matches, use **collated equality** where appropriate. For prefix, fuzzy, or full-text search, design dedicated indexes or search engines rather than expecting collation to fix regex queries.

### 16.3. Text Indexes and 2d Indexes

MongoDB text indexes and 2d indexes support only **simple binary collation**. If a collection has a non-simple default collation and needs one of these indexes, you must explicitly specify `collation:{locale:"simple"}` per MongoDB's index rules.

Nor does standard B-tree collation replace full-text tokenizers/analyzers.

## 17. Collation and Safe Schema/Collection Changes

Switching policy from `simple` to `en/2` or `vi/2` simultaneously affects:

- **Query results:** string equality may match more documents.
- **Sorting:** string order shifts; previously distinct strings may tie.
- **Grouping:** group counts shrink or change.
- **Unique indexes:** previously distinct values can become **duplicates**.
- **Index performance:** queries need indexes matching the new collation.
- **API expectations:** pagination and report totals change.

### 17.1. Recommended Change Workflow

1. **Redefine the business contract:** locale, strength, case, accents, numericOrdering per use case.
2. **Audit data** under the new rules: locate keys differing in character representation that become equivalent.
3. **Compare queries/reports** on representative data to confirm before/after match and group counts.
4. **Check unique conflicts** before building collated unique indexes.
5. **Assess collections and views:** current default collation, implicit collection creation risks, existing indexes.
6. **Design matching indexes** for new queries while limiting index count to control write overhead.
7. **Pick deployment path:** operation-level collation if only specific queries differ; collection migration if changing the overall default is required.
8. **Roll out gradually/staging**, monitoring errors, latency, explain plans, and raw BSON.
9. **Define rollback:** which operations/indexes revert and how data written under new rules is handled.

### 17.2. Detecting Duplicates Under a New Collation

To create a case-insensitive unique `username` per tenant, check before building the index:

~~~javascript
db.customers_collation_unique_007.aggregate(
  [
    {
      $group: {
        _id: {
          tenant: "$tenant_id",
          username: "$username"
        },
        count: { $sum: 1 },
        ids: { $push: "$_id" }
      }
    },
    { $match: { count: { $gt: 1 } } }
  ],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Grouping under en/2 puts usernames differing only in case into the **same group**, mirroring the target unique index's rules. On massive collections, avoid pushing unlimited IDs into one group document (16 MiB BSON limit); batch or shard the audit carefully.

**Never auto-delete duplicates** blindly from a group query: merging identities is a business decision.

## 18. Integration Testing: Covering Collections, Queries, and Aggregations

Mocking `MongoTemplate` does not prove collation was sent to MongoDB, does not verify collection metadata, and misses ICU grouping differences. Use an isolated MongoDB test instance (e.g., Testcontainers) with controlled fixture data.

### 18.1. Minimum Test Cases

| Test | Expectation |
| --- | --- |
| Collection default `en/2` | Present in collection metadata |
| Query `cafe`, default `en/2` | `p701` in tenant t01 |
| Query `Café`, default `en/2` | `p702`, `p703` |
| Query `cafe`, explicit `en/1` | `p701`, `p702`, `p703` |
| Query `Café`, explicit simple | Only `p703` |
| Aggregation group category default `en/2` | 2 groups with counts 3 and 2 |
| Aggregation group category simple | 5 groups with count 1 |
| Sort code, numericOrdering true | item2, item3, item10, item11, item20 |
| Unique index en/2 | Alice and alice in same tenant collide |
| Unique index en/2, different tenants | Allowed to share username |
| Index collation matches query | Can assist string comparisons; verify via explain |
| Query collation differs from index | Cannot use that index for incompatible string match |
| Repository `@Query`, `@Aggregation` | Sends right collation and returns right results |
| `$regex` | Do not assume collation index speeds up regex |
| Other tenant | Never leaks into t01 results |

### 18.2. Java Test Against Real MongoDB

Example test creating an isolated collection via the driver, then using `MongoTemplate` with entity metadata to verify collation. Run only on an **isolated test database** and avoid sharing this collection name across parallel tests.

~~~java
package com.example.collation;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.CollationStrength;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class CollationMongoOperationsTest {
    @Autowired MongoTemplate template;

    @Test
    void collectionDefaultCanBeOverriddenPerQuery() {
        String collection = "catalog_collation_it_007";

        // In an isolated test database, create collection before insert.
        if (!template.collectionExists(collection)) {
            var nativeRules =
                com.mongodb.client.model.Collation.builder()
                    .locale("en")
                    .collationStrength(CollationStrength.SECONDARY)
                    .build();

            template.getDb().createCollection(
                collection,
                new CreateCollectionOptions().collation(nativeRules)
            );
        }

        var nativeCollection =
            template.getDb().getCollection(collection);
        var ids = List.of(
            "it-collation-701",
            "it-collation-702",
            "it-collation-703",
            "it-collation-other"
        );

        nativeCollection.deleteMany(Filters.in("_id", ids));

        try {
            nativeCollection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "cafe"),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "CAFÉ"),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "test-tenant-007")
                    .append("display_name", "Café"),
                new Document("_id", ids.get(3))
                    .append("tenant_id", "another-tenant")
                    .append("display_name", "cafe")
            ));

            Query defaultQuery = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("cafe")
            );
            // No Query.collation passed: uses default en/strength 2.
            var defaultMatches = template.find(
                defaultQuery, ProductDocument.class, collection
            );
            assertThat(defaultMatches)
                .extracting(ProductDocument::getId)
                .containsExactly(ids.get(0));

            Query accentInsensitive = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("cafe")
            ).collation(Collation.of("en").strength(1));

            var allBaseNames = template.find(
                accentInsensitive, ProductDocument.class, collection
            );
            assertThat(allBaseNames)
                .extracting(ProductDocument::getId)
                .containsExactlyInAnyOrder(
                    ids.get(0), ids.get(1), ids.get(2)
                );

            Query binary = Query.query(
                Criteria.where("tenantId").is("test-tenant-007")
                    .and("displayName").is("Café")
            ).collation(Collation.simple());
            var exact = template.find(
                binary, ProductDocument.class, collection
            );
            assertThat(exact)
                .extracting(ProductDocument::getId)
                .containsExactly(ids.get(2));
        } finally {
            nativeCollection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

**Execution note:** `ProductDocument` in section 11 declares `@Document(collation=en/2)`. If a test wants to prove **purely server-default behavior**, ensure no explicit collation from entity metadata overlays the query; ideally add a parallel raw-driver check `nativeCollection.find(Filters.eq("display_name","cafe"))`. In the snippet above, entity `en/2` matches server default `en/2`, so results remain consistent even though both layers declare the same rules.

### 18.3. Testing Aggregations Without Relying on Group `_id` Casing

When grouping `Drink`/`drink`/`DRINK` under en/2, assert:

~~~java
// Conceptual assertion, with CategoryTotal having categoryName and total:
assertThat(totals)
    .extracting(CategoryTotal::total)
    .containsExactlyInAnyOrder(3L, 2L);
~~~

Never assert that the group name is definitely `"Drink"` unless the pipeline constructs a canonical label, because collation treats strings as equal without persisting a normalized casing.

### 18.4. Index Tests Must Inspect Metadata and Explain

Beyond outputs, verify `getIndexes()` includes:

- `key` matching BSON `tenant_id/display_name`.
- Index `collation` matching en/2 or en/1.
- `unique` and other options if it is a unique index.

Then inspect `explain("executionStats")` on representative queries. Never hardcode a winning plan assertion on a six-document fixture; the planner can reasonably choose a collection scan on tiny datasets.

## 19. Common Pitfalls

| Symptom | Common Cause | Remediation |
| --- | --- | --- |
| `@Document(collation=...)` present yet collection is still simple | Collection was implicitly created by MongoDB earlier | Create collection explicitly before writing; inspect metadata |
| Creating new collection with old name fails | Collection already exists | Do not treat `createCollection` as a default-update command; plan migration |
| Query `cafe` misses `Café` | Using strength 2 or simple, still accent-sensitive | If accents should be ignored, use strength 1 with proper locale |
| Query matches too many documents | Using strength 1 when accents matter or missing tenant filter | Enforce tenant scope and choose strength per contract |
| Sorting looks wrong for local alphabet | Using simple or wrong locale/strength | Use the right locale; test accented/Unicode data |
| Pagination repeats items across pages | Multiple names compare equal under collation without tie-breaker | Add `_id` to sort; address consistency |
| `$group` returns 2 groups instead of 5 | Collation is merging case/diacritic variants | Check collection default, operation override, and output |
| Query ignores index | Index and query collations are incompatible | Compare `getIndexes()`, operation collation, and `explain` |
| Case-insensitive regex remains slow | `$regex` is not collation-aware | Use collated equality or suitable search/index design |
| Inserting `Alice`/`alice` fails unique check | `en/2` unique index treats them as equal | Expected constraint behavior; handle conflicts cleanly |
| Same username across different tenants blocked | Global unique index instead of compound per-tenant index | Inspect key pattern and legacy indexes |
| Used `Collation.simple()` thinking it means "default" | `simple` is an explicit binary override | Omit collation to use server default or specify exact rules |
| `@Query(collation=...)` not applied in mock tests | Mocks do not execute the driver | Write integration tests against real MongoDB |
| Repository query and aggregation give different results | Two operations use different collations or filters | Compare effective collation on each command |
| `numericOrdering` sorts negative numbers wrongly | Supports only non-negative integer digit runs | Store numbers as numeric BSON types |
| `@Field` alias causes query to miss data | Used BSON name where Java property expected or vice versa | Check entity mapping and actual BSON |
| Text/2d index fails on collated collection | Those indexes support only simple collation | Create index with explicit simple collation per rules |
| View query rejects collation override | Views have fixed collation | Check view collation and redesign if needed |

## 20. Collation Design Checklist

1. **Clarify the requirement:** exact match, case-insensitive, accent-insensitive, natural number sort, or uniqueness.
2. **Pick concrete locale and strength**; test real accented/cased data, especially for Vietnamese.
3. **Distinguish collection default, entity annotation, operation override, and index collation.**
4. **Create collections explicitly** whenever a default collation is required.
5. **Do not expect `@Document` to alter** implicitly created or existing collections.
6. **One operation has one collation**; never expect per-field or per-stage rules inside one command.
7. **Enforce tenant/authorization** directly in filters, especially with strength 1.
8. **Add a sort tie-breaker** whenever multiple strings can compare equal.
9. **Verify `$group` outputs**, never assuming canonical casing/diacritic labels.
10. **Build indexes matching workload collations**, weighing multi-index write overhead.
11. **Audit unique conflicts** before changing comparison policies.
12. **Do not rely on regex** expecting case-insensitive collation indexes to accelerate it.
13. **Verify how Spring Data passes collation:** `Query.collation`, repository `@Query`, `AggregationOptions`, and `@Aggregation`.
14. **Write integration tests** with real BSON, collection/index metadata, and case/accent fixtures.
15. **Plan rollbacks** when migrating default collation or unique policies.

## 21. Practice Exercises

Each exercise uses the fixture in section 4, assuming no concurrent writers and unchanged data between questions.

### Exercise 1 — Collection Level

Why must `db.createCollection(...,{collation:...})` be called **before** the first insert?

**Answer:** If MongoDB creates the collection implicitly, default collation is not taken automatically from Spring Data's `@Document`; the collection can become `simple`. The default is fixed at creation time and cannot be changed directly afterward.

### Exercise 2 — Strength 2

Query `display_name:"cafe"` in t01 on the `en/2` collection. Which IDs match?

**Answer:** `p701`. `CAFÉ` and `Café` carry accents, and strength 2 still distinguishes accents from `cafe`.

### Exercise 3 — Strength 1

Override with `en/1` and search `"cafe"` in t01. Which IDs match?

**Answer:** `p701,p702,p703`. Both case and secondary-level accent differences are ignored.

### Exercise 4 — `simple`

Search `"Café"` in t01 using `Collation.simple()`.

**Answer:** Only `p703`; MongoDB performs binary comparison.

### Exercise 5 — Grouping by Category

With `en/2` and tenant t01, how many groups does `$group` by `category` return? How many under `simple`?

**Answer:** `en/2` returns **2 groups** with counts 3 and 2; `simple` returns **5 groups** because `Drink`/`drink`/`DRINK` and `Food`/`food` differ under binary comparison.

### Exercise 6 — Numeric Ordering

Given codes `item2,item10,item3,item20,item11`, what order does sorting under `en/2` with `numericOrdering: true` produce?

**Answer:** `item2,item3,item10,item11,item20`. Never use this to parse negative or floating-point numbers inside strings.

### Exercise 7 — Index Compatibility

A collection has index `{tenant_id:1,display_name:1}` with `en/2`. Can an `en/1` query definitely use that index to compare `display_name`?

**Answer:** No. Index and query collations must align for string comparisons. You can create an index with the same key pattern, `en/1` collation, and a different name if workload justifies it, then verify with `explain`.

### Exercise 8 — Unique Index and Case

`(t01,"Alice")` already exists in a compound unique `en/2` index. What happens on inserting `(t01,"alice")`? What about `(t02,"alice")`?

**Answer:** Same tenant raises `E11000`; different tenant succeeds because the compound key differs.

### Exercise 9 — Spring Data Annotation

Does `@Document(collation = "{'locale':'en','strength':2}")` alter the default collation of an earlier implicitly created collection?

**Answer:** No. It is Spring Data metadata for mapped operations; the collection's server default must be set at creation time, or a migration is needed.

### Exercise 10 — Query and Aggregation

Write how to configure `en/1` for a query and for an aggregation.

**Answer:**

~~~java
Query query = Query.query(
    Criteria.where("displayName").is("cafe")
).collation(Collation.of("en").strength(1));

AggregationOptions options = AggregationOptions.builder()
    .collation(Collation.of("en").strength(1))
    .build();
~~~

For aggregation, attach the options to the pipeline via `withOptions(options)`.

### Exercise 11 — Raw Aggregation vs. DTO

`en/2` collation merges `Drink`/`drink`/`DRINK` into one group. Is the group's `_id` guaranteed to be lowercase `"drink"`?

**Answer:** No. Collation defines **comparison equivalence**, not output normalization. Emit an explicit canonical label if the API expects a fixed spelling.

### Exercise 12 — Multi-Tenant Update

Which documents can an `updateMulti` matching `"cafe"` under `en/1` without a tenant filter modify?

**Answer:** In the fixture, `p701,p702,p703` (t01) as well as `p706` (t02). Always include the authorized tenant in the predicate rather than filtering by product name alone.

### Exercise 13 — Regex

Why doesn't `/cafe/i` automatically use an `en/1` index or handle all accent variants?

**Answer:** MongoDB `$regex` is not collation-aware; case-insensitive collation indexes do not optimize regex. Use collated equality when applicable, and appropriate search tooling/indexes for text search.

### Exercise 14 — Changing Collation on an Active Collection

Can you immediately switch the default from `en/2` to `en/1` via a simple `collMod` command?

**Answer:** No. Default collation is fixed when the collection is created; changing it requires a migration workflow, or applying operation-specific collation if only select use cases need it.

### Exercise 15 — Testing

Does a unit test mocking `MongoTemplate.find` to return three products prove MongoDB applied `en/1`?

**Answer:** Not yet. Integration tests against real MongoDB with case/accent fixtures, collection/index metadata checks, and query/aggregation execution are required.

## References

- [Spring Data MongoDB — Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html): fluent `Collation`, `@Document`, collection/index creation, `Query.collation`, and `AggregationOptions`.
- [Spring Data MongoDB — Repository Query Methods, Collation Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Query(collation=...)`, `Collation` parameter, and precedence order.
- [Spring Data MongoDB — `@Aggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Aggregation.html): `collation` attribute on repository aggregations.
- [Spring Data MongoDB — `Collation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Collation.html): `simple`, `of`, `strength`, `numericOrderingEnabled`.
- [Spring Data MongoDB — `@Document` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Document.html): entity-level collation metadata.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed aggregations, pipeline stages, and output mapping.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale, strength, case, numericOrdering, view, and index restrictions.
- [MongoDB Manual — `db.createCollection()`](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): collection default collation, creation timing, and modification limits.
- [MongoDB Manual — `db.collection.createIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/): index collation and index usage conditions.
- [MongoDB Manual — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/): strength 1/2 indexes and `$regex` limitations.
- [MongoDB Manual — `$regex`](https://www.mongodb.com/docs/manual/reference/operator/query/regex/): regex is not collation-aware.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): `$match`, `$group`, `$sort`.
