# Regex, Case Sensitivity, and Index Impact

## 1. Context and Objectives

In **Spring Data MongoDB**, `Query` and `Criteria` help you write query conditions on BSON documents without manually concatenating JSON strings. For the **Mini Commerce** sales system consisting of `Product`, `Customer`, and `Order`, searching products by name, SKU, category, or recipient details can raise diverse requirements:

- Find products whose name **starts with** a prefix.
- Find product names **containing** a text fragment.
- Find an exact SKU **case-insensitively**.
- Support Vietnamese names with and without diacritics according to predefined rules.
- Ensure listing pages stay fast as the collection grows from hundreds to millions of documents.

A common mistake is replacing every string comparison with `$regex` using the `i` option, then believing that adding a case-insensitive index will make the query fast. That is incorrect: MongoDB **does not use a collation index to optimize `$regex` the way it optimizes collation-based equality**. This lesson specifically explains the differences among **regex**, **collation**, **normalized search fields**, and **index types**.

After studying this lesson, you will be able to:

1. Write `$regex` expressions in `mongosh` and in `Criteria.regex(...)`.
2. Distinguish **prefix** (`^prefix`), **suffix** (`suffix$`), **contains**, and **full-string** regexes.
3. Understand options `i`, `m`, `s` and limitations when handling Unicode/Vietnamese text.
4. Explain when a B-tree index helps a regex query and when an `IXSCAN` still scans too many keys.
5. Use **collation** for case-insensitive equality/sort, paired with an index carrying the matching collation configuration.
6. Design a normalized field such as `nameSearch` when stable prefix search performance is required.
7. Protect APIs from regex injection, CPU-heavy patterns, unbounded queries, and unindexed sorts.
8. Test semantics and inspect `explain("executionStats")` on a real MongoDB instance.

**Prerequisites:** Java 17+, Spring Boot with `spring-boot-starter-data-mongodb`, a running MongoDB instance, understanding of `@Document`, `@Id`, `@Field`, `MongoTemplate`, `MongoRepository`, `Query`, and `Criteria`. Most examples use the synchronous API; the BSON/index principles also apply to the reactive stack.

## 2. Distinguishing Four Search Needs

There is no single best string search operation for every requirement.

| Requirement | Usually Suitable Filter | Example | Index Notes |
| --- | --- | --- | --- |
| Exact equality, case-sensitive | `{ sku: "KBD-001" }` | Exact character-for-character SKU | Equality index fits very well |
| Exact equality, case-**insensitive** | Equality with **collation** | `"BAN PHIM"` equals `"ban phim"` under collation | Requires an index with the **same collation** |
| Starts with string, case-sensitive | `{ name: { $regex: "^Ban" } }` | Name starting with `Ban` | Can optimize using a **prefix index range** |
| Starts with string, case-insensitive | `{ name: { $regex: "^ban", $options: "i" } }` | `Ban` and `BAN` | Not optimized like equality via a collation index |
| Contains a fragment anywhere | `{ name: { $regex: "Mini" } }` | `"Chuột Mini"` | Prefix index optimization generally does not apply |
| Accent-insensitive, typo-tolerant, autocomplete, ranking | Normalized field or dedicated search engine | `"ban phim"` → `"Bàn phím"` | Requires dedicated search design/index |

**Starting rule:** if you only need **equality**, use equality; if you only need **prefix**, express a proper prefix; if you need **full-text/fuzzy/autocomplete**, consider an appropriate search system. Never reach for regex arbitrarily just because the API is easy to write.

## 3. Mini Commerce Data for Practice

### 3.1. Product and Search Fields

In this lesson, the `Product` entity has a display name field `name` and an optional `nameSearch` field used for the normalization strategy later on.

```java
package com.example.minicommerce.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;
    private String category;
    private boolean active;

    @Field("name_search")
    private String nameSearch;

    @Field(name = "unit_price", targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    public Product() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getCategory() { return category; }
    public void setCategory(String category) {
        this.category = category;
    }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public String getNameSearch() { return nameSearch; }
    public void setNameSearch(String nameSearch) {
        this.nameSearch = nameSearch;
    }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
```

In the entity above, Java property `nameSearch` is stored in BSON as `name_search` via `@Field`. Similarly, `price` is stored as `unit_price` of type Decimal128. `Criteria.where(...)` calls associated with `Product.class` use **Java property names**; `mongosh` and the raw driver use **BSON names**.

### 3.2. Fixture Demonstrating Case and Vietnamese Diacritics

Run in an **isolated test** database:

```javascript
use mini_commerce

db.products.insertMany([
  {
    _id: "regex-p1",
    sku: "KBD-001",
    name: "Ban phim Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("129900.00")
  },
  {
    _id: "regex-p2",
    sku: "KBD-002",
    name: "BAN PHIM Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("159900.00")
  },
  {
    _id: "regex-p3",
    sku: "KBD-003",
    name: "Bàn phím Mini",
    name_search: "ban phim mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("179900.00")
  },
  {
    _id: "regex-p4",
    sku: "MOU-001",
    name: "Chuột Mini",
    name_search: "chuot mini",
    category: "phu-kien",
    active: true,
    unit_price: NumberDecimal("99000.00")
  }
]);
```

Assume only these four fixtures exist when checking results:

| ID | `name` | `name_search` |
| --- | --- | --- |
| `regex-p1` | Ban phim Mini | ban phim mini |
| `regex-p2` | BAN PHIM Mini | ban phim mini |
| `regex-p3` | Bàn phím Mini | ban phim mini |
| `regex-p4` | Chuột Mini | chuot mini |

The fixtures clearly illustrate three different notions of "equal": **byte/string equality**, **case-insensitive equality**, and **equality after diacritic stripping per application rules**. Do not conflate these three concepts.

Re-running `insertMany` will fail with duplicate `_id` errors. In integration tests, use test-scoped IDs and dedicated cleanup; never run fixtures on production.

## 4. $regex Syntax in MongoDB

MongoDB supports regex in filters:

```javascript
// Regex as a string:
db.products.find({ name: { $regex: "^Ban" } });

// Regex literal in mongosh:
db.products.find({ name: /^Ban/ });

// Case-insensitive:
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

In modern MongoDB, the server uses the **PCRE2** regex engine starting from MongoDB 6.1. When writing Java `Pattern`, remember that the pattern is sent to MongoDB for execution; do not assume every feature, Unicode flag, or performance characteristic of Java regex and PCRE2 is identical across all versions.

### 4.1. Common Symbols

| Pattern | Meaning | Example Match |
| --- | --- | --- |
| `^Ban` | String starts with `Ban` | `Ban phim Mini` |
| `Mini$` | String ends with `Mini` | `Chuột Mini` |
| `Mini` | `Mini` appears anywhere | All four fixtures |
| `^Ban phim Mini$` | Matches start to end, exact case | Only `regex-p1` |
| `^Ban.*Mini$` | Starts with `Ban`, any characters, ends with `Mini` | `regex-p1` |
| `^ban` + `i` | Starts with `ban`, case-insensitive | `regex-p1`, `regex-p2` |
| `B.n` | `.` matches one character (except newline without option `s`) | Can match `Ban` |

Regex is a **pattern language**, not plain text matching. For example, characters like `.`, `*`, `+`, `?`, `[`, `(`, or `|` entered by a user can completely alter query semantics if left unescaped.

### 4.2. Distinguishing Prefix, Contains, and Suffix

```javascript
// Prefix: case-sensitive.
db.products.find({ name: { $regex: "^Ban" } });
// Only regex-p1.

// Contains: checks occurrence of Mini.
db.products.find({ name: { $regex: "Mini" } });
// regex-p1, regex-p2, regex-p3, regex-p4.

// Suffix.
db.products.find({ name: { $regex: "Mini$" } });
// All four fixtures.

// Exact case-sensitive.
db.products.find({ name: { $regex: "^Ban phim Mini$" } });
// Only regex-p1.
```

If you only need exact matching without regex semantics, use:

```javascript
db.products.find({ name: "Ban phim Mini" });
```

Equality is both easier to read and usually allows more effective index usage. `^...$` is not a default substitute for equality.

### 4.3. Options i, m, s, x

| Option | Meaning | Application Example |
| --- | --- | --- |
| `i` | Case-insensitive regex matching | `"^ban"` matches `Ban`/`BAN` |
| `m` | Multiline: `^` and `$` match line boundaries | Multi-line product descriptions |
| `s` | Dotall: `.` can match newline characters | Cross-line patterns |
| `x` | Extended mode: allows whitespace/comments in pattern per regex rules | Complex patterns, rarely needed in product search |

```javascript
// Pattern must start at the beginning of a line in the description.
db.products.find({
  description: { $regex: "^Khuyen mai", $options: "im" }
});
```

Do not enable `m`/`s` mechanically: they change semantics and can make patterns harder to optimize. For prefix indexes, the pattern actually needs to be anchored at the **start of the string**, not merely the start of any line.

## 5. Spring Data MongoDB: Criteria.regex(...)

`Criteria` provides overloads accepting String, String + options, Java `Pattern`, or `BsonRegularExpression`. The snippets below illustrate common forms:

```java
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// 1. Case-sensitive prefix:
Query prefix = Query.query(
    Criteria.where("name").regex("^Ban"));

// 2. Case-insensitive prefix:
Query prefixIgnoreCase = Query.query(
    Criteria.where("name").regex("^ban", "i"));

// 3. Java Pattern:
Pattern exact = Pattern.compile(
    "^Ban phim Mini$", Pattern.CASE_INSENSITIVE);
Query withPattern = Query.query(
    Criteria.where("name").regex(exact));

// 4. Literal substring, case-sensitive:
Query containsMini = Query.query(
    Criteria.where("name").regex("Mini"));

List<Product> products =
    mongoTemplate.find(prefixIgnoreCase, Product.class);
```

Make sure `Product` is imported from the right package and `MongoTemplate` is constructor-injected in the service. `Criteria.where("name")` uses the **Java property name**; when Spring Data builds the BSON query for `Product.class`, it applies mapping metadata.

### 5.1. Combining Regex with Business Conditions

In Mini Commerce, the product search API should constrain at least by `active` and category (if category is provided):

```java
Query query = Query.query(
    Criteria.where("active").is(true)
        .and("category").is("phu-kien")
        .and("name").regex("^Ban"));

List<Product> result = mongoTemplate.find(query, Product.class);
```

Logical BSON:

```javascript
{
  active: true,
  category: "phu-kien",
  name: { $regex: "^Ban" }
}
```

In multi-store schemas, also add `tenantId` or access-control permissions to the filter; adding only `active = true` is not authorization. For optional conditions, use `Query.addCriteria(...)` or deliberately assemble `Criteria` instead of concatenating JSON strings.

### 5.2. Repository Derived Queries Can Generate Regex

`MongoRepository` supports derived query keywords:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    List<Product> findByNameStartingWith(String prefix);

    List<Product> findByNameStartingWithIgnoreCase(String prefix);

    List<Product> findByNameContainingIgnoreCase(String fragment);

    List<Product> findByNameEndingWith(String suffix);
}
```

Spring Data MongoDB typically translates `StartingWith` to a prefix regex, `Containing` to a substring regex, and `IgnoreCase` to a regex with `i`. Do not assume `findByNameStartingWithIgnoreCase(...)` automatically optimizes with a collation index. Inspect the actual BSON and query plan.

### 5.3. @Query When Controlling the JSON Filter

`@Query` supports parameter placeholders instead of JSON concatenation:

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'name': { '$regex': ?0, '$options': 'i' } }")
List<Product> searchByPatternIgnoreCase(String pattern);
```

This method must live inside `ProductRepository`. `?0` is the first parameter and is bound by Spring Data; however, **binding does not automatically turn user-supplied regex into a safe literal**. Callers must still enforce length limits, format checks, and escaping if search allows only plain strings.

Never pass raw HTTP request content such as `.*` or `^(a+)+$` into an API allowing arbitrary regexes.

## 6. User Input: Escaping Patterns and Limiting Cost

If a user types a `.`, they probably want to find products with a dot in their name, not a regex wildcard character. Use `Pattern.quote` to express a **literal string**:

```java
import java.util.regex.Pattern;

public List<Product> searchPrefix(String userPrefix) {
    if (userPrefix == null) {
        throw new IllegalArgumentException("Prefix is required");
    }

    String prefix = userPrefix.trim();
    if (prefix.isEmpty() || prefix.length() > 64) {
        throw new IllegalArgumentException(
            "Prefix length must be between 1 and 64");
    }

    String pattern = "^" + Pattern.quote(prefix);

    Query query = Query.query(
        Criteria.where("active").is(true)
            .and("name").regex(pattern));

    query.limit(20);
    query.maxTime(java.time.Duration.ofSeconds(2));

    return mongoTemplate.find(query, Product.class);
}
```

This method snippet belongs to a service with an injected `MongoTemplate mongoTemplate` and appropriate imports for `Product`, `Query`, and `Criteria`. In production APIs, also add rate limiting, tenant isolation, and return only the required DTO.

**Important for indexes:** `Pattern.quote` can produce a pattern containing `\Q...\E`. Depending on the query engine and version, escaped constructs can affect index prefix optimization **differently** from a simple pattern like `^Ban`. Therefore, measure with `explain`; if you need genuinely fast prefix queries over diverse inputs, consider a **normalized field** restricted to an allowed character set as shown in section 10.

### 6.1. Do Not Rely Solely on maxTime

`maxTime`/timeouts cap runaway queries, yet do not replace:

- Input validation and pattern length limits.
- Rate limiting and page size caps.
- Proper indexes or search design.
- Controlling which fields may be searched, under which permissions.
- Monitoring CPU/latency, examined keys, and examined documents.

If users genuinely need advanced regex (for instance, an internal admin tool), place it behind dedicated permissions, restrict pattern complexity, and scope it to bounded datasets.

## 7. Case-Insensitive Regex Is Not the Same as Collation

This is the central point of the lesson:

- `{ name: { $regex: "^ban", $options: "i" } }` uses the **regex engine** with the `i` flag.
- `{ name: "ban phim mini" }` with `collation: { locale: "vi", strength: 2 }` uses **ICU string comparison rules** for equality.
- MongoDB **does not treat `$regex` as collation-aware**. An index configured as case-insensitive via collation **does not let `$regex` leverage the index's case-insensitivity the way equality does**.

### 7.1. Case-Insensitive Regex

```javascript
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

With the fixtures, this query returns `regex-p1` and `regex-p2`. `regex-p3` has `à`, so **do not assume** `i` also strips diacritics: `"Ban"` and `"Bàn"` are not treated as equal merely by enabling `i`.

### 7.2. Collation on Equality

To compare **exact names** case-insensitively, you can use:

```javascript
db.products.find({
  name: "ban phim mini"
}).collation({
  locale: "vi",
  strength: 2
});
```

At collation strength 2, comparison is **case-insensitive while still distinguishing diacritics**. With the fixtures, `regex-p1` and `regex-p2` match; `regex-p3` has diacritic `à` so it does not match the unaccented string.

To match **ignoring both case and diacritics** at the primary level:

```javascript
db.products.find({
  name: "ban phim mini"
}).collation({
  locale: "vi",
  strength: 1
});
```

Strength 1 compares only base characters per locale rules and generally ignores differences in diacritics and case. Still, whether two names count as equivalent depends on **ICU locale rules and business rules**; test real Vietnamese data rather than assuming all `đ`/`d` or combining Unicode cases behave identically.

**Collation does not turn equality into substring search.** An equality query with collation still requires matching the **entire** name under comparison rules; it will not match `"Mini"` inside `"Chuột Mini"`.

### 7.3. Collation in MongoTemplate

```java
import java.util.List;

import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Collation caseInsensitive = Collation.of("vi")
    .strength(Collation.ComparisonLevel.secondary());

Query sameNameIgnoreCase = Query.query(
    Criteria.where("name").is("ban phim mini"))
    .collation(caseInsensitive);

List<Product> matches = mongoTemplate.find(
    sameNameIgnoreCase, Product.class);
```

Import `Product` and inject `MongoTemplate` in the service. This is **equality with collation**, not `Criteria.regex(..., "i")`.

## 8. Which Indexes Support Regex?

MongoDB can use a B-tree index on a string field for case-sensitive `$regex`, particularly when the pattern has a **fixed prefix**.

### 8.1. Anchored Prefix: The Optimizable Case

Create an index:

```javascript
db.products.createIndex({ name: 1 });
```

Query:

```javascript
db.products.find({
  name: { $regex: "^Ban" }
}).explain("executionStats");
```

If an index is suitable and chosen by the planner, MongoDB can bound an **index range** for names starting with `Ban`. This avoids inspecting every name in the collection.

Three seemingly equivalent patterns:

```javascript
{ name: { $regex: "^Ban" } }
{ name: { $regex: "^Ban.*" } }
{ name: { $regex: "^Ban.*$" } }
```

yet they **differ in cost**. Per the MongoDB Manual, a clean prefix pattern like `^Ban` can stop once past the prefix range; appending `.*` and `$` can force extra matching work. Do not append redundant trailing wildcards to prefixes.

**There is no absolute guarantee that every regex with `^` uses an index.** Available indexes, collation, selectivity, server version, and query plans all influence MongoDB's choice.

### 8.2. Contains and Suffix Lack a Useful Prefix Range

```javascript
db.products.find({
  name: { $regex: "Mini" }
}).explain("executionStats");

db.products.find({
  name: { $regex: "Mini$" }
}).explain("executionStats");
```

Because MongoDB does not know any fixed prefix that matching names must **start with**, the optimizer normally cannot narrow the index range the way `^Ban` does. You may still see a wide `IXSCAN` or `COLLSCAN`; `IXSCAN` **does not guarantee** the query is fast if it has to scan huge numbers of keys.

### 8.3. Regex with i Is Not Optimized by a Case-Insensitive Index

```javascript
db.products.find({
  name: { $regex: "^ban", $options: "i" }
}).explain("executionStats");
```

MongoDB `$regex` is **not collation-aware**. Creating an index with `{ locale: "vi", strength: 2 }` on `name` does not turn a regex `i` query into an efficient collation prefix range scan. That is why you should never advise "just add a case-insensitive index" for arbitrary name search features.

Comparing on a sufficiently large dataset is essential. On four fixture documents, the planner may pick `COLLSCAN` even with a valid index because a direct scan is cheaper.

## 9. Collation Indexes for Case-Insensitive Equality

If business logic needs to look up an **exact name** or business key with case-insensitive equality, create an index with collation:

```javascript
db.products.createIndex(
  { name: 1 },
  {
    name: "idx_name_vi_ci",
    collation: { locale: "vi", strength: 2 }
  }
);
```

The query must specify the **same collation** to leverage the index for string comparison:

```javascript
db.products.find({
  name: "ban phim mini"
})
.collation({ locale: "vi", strength: 2 })
.explain("executionStats");
```

In a collection with no default collation like our fixture, omitting `collation(...)` on the query causes MongoDB to use default binary comparison; a strength-2 collation index **does not automatically apply to binary queries**.

**If accent-insensitivity is needed**, create a separate index or choose collation strength 1 matching the data contract, and ensure queries pass the identical configuration. Never mix strength 1 and strength 2 arbitrarily in the same API.

### 9.1. Do Not Use a Collation Index to "Fix" Regex i

The following two filters have a key difference:

```javascript
// Equality, case-insensitive via collation:
db.products.find({ name: "ban phim mini" })
  .collation({ locale: "vi", strength: 2 });

// Regex, case-insensitive via regex engine:
db.products.find({
  name: { $regex: "^ban", $options: "i" }
});
```

The first filter can leverage a **collation index** because it is a locale-based string comparison. The second filter is a regex; it **does not** gain the same benefit from a case-insensitive index.

### 9.2. Do Not Confuse Collation Indexes with Full-Text Search

A collation index handles language-aware string comparison and sorting. It does not automatically provide fuzzy matching, stemming, synonyms, or phrase autocomplete suggestions. Those requirements need a dedicated search design, such as MongoDB Search with appropriate indexes/analyzers if supported by your platform.

## 10. Normalized Fields: A Solution for Accent-Insensitive Prefixes

In Mini Commerce, users might type `ban phim` to search for display name `Bàn phím`. If **prefix search** is needed frequently, one option is to store **an additional** normalized field:

```text
name          = "Bàn phím Mini"
name_search   = "ban phim mini"

name          = "BAN PHIM Mini"
name_search   = "ban phim mini"
```

Then query `name_search` using a **case-sensitive prefix regex**:

```javascript
db.products.createIndex({
  active: 1,
  category: 1,
  name_search: 1
});

db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
});
```

With the four fixtures, the query returns `regex-p1`, `regex-p2`, and `regex-p3`. Because `name_search` is already normalized to lowercase without diacritics per Mini Commerce's contract, **there is no need to enable `i`** in this regex.

### 10.1. Illustrative Normalization Function

```java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchTextNormalizer {

    private SearchTextNormalizer() {}

    public static String normalize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Text required");
        }

        String lower = Normalizer.normalize(
            raw, Normalizer.Form.NFD).toLowerCase(Locale.ROOT);

        return lower
            .replace('đ', 'd')
            .replaceAll("\\p{M}+", "")
            .replaceAll("[^a-z0-9 ]+", " ")
            .replaceAll("\\s+", " ")
            .trim();
    }
}
```

The illustrative function normalizes Unicode, replaces `đ` with `d`, strips combining marks, and reduces characters to `a-z`, digits, and spaces. This is an **example business policy**, not a complete Vietnamese search algorithm. It can strip information from product symbols, model codes, or other scripts; consider separate search fields if products span multiple languages.

If this normalization rule is adopted in a service, apply it consistently during **inserts**, **name updates**, **imports**, **migrations**, and **queries**. Do not normalize only queries while leaving legacy documents without `name_search`.

### 10.2. Querying by Mapped Java Property

```java
public List<Product> searchNormalizedPrefix(
        String rawPrefix, String category) {

    if (rawPrefix == null || rawPrefix.length() > 64) {
        throw new IllegalArgumentException("Invalid prefix");
    }

    String normalized = SearchTextNormalizer.normalize(rawPrefix);
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException(
            "Prefix contains no searchable characters");
    }

    // normalize() retains only [a-z0-9 ], leaving no regex metacharacters.
    String safePrefixPattern = "^" + normalized;

    Query query = Query.query(
        Criteria.where("active").is(true)
            .and("category").is(category)
            .and("nameSearch").regex(safePrefixPattern));

    query.limit(20);

    return mongoTemplate.find(query, Product.class);
}
```

In MongoDB, Java property `nameSearch` maps to BSON `name_search`. The input is transformed to a restricted character set, so the regex string contains no arbitrary metacharacters. **Never skip the step guaranteeing a safe character set** and concatenate raw user input into a regex.

### 10.3. Trade-Offs of a Denormalized Search Field

| Benefit | Cost / Risk |
| --- | --- |
| Simple prefix can use index range scans | Extra field and index, increasing write cost |
| No `$options: "i"` needed when always lowercase | Every write path must keep `name` and `name_search` in sync |
| Explicit diacritic-stripping policy | Can collapse distinct strings together; requires business agreement |
| Fixed query shape, easy to benchmark | Legacy data needs backfill; missed updates create stale search fields |

For matching substrings at arbitrary positions, a normalized field plus an unanchored regex can still scan many index entries. Do not treat normalization as a universal replacement for a dedicated search engine.

## 11. Compound Indexes and How to Read explain

To filter active products by category and then search names starting with a prefix, an index worth testing:

```javascript
db.products.createIndex({
  active: 1,
  category: 1,
  name_search: 1
});
```

Query:

```javascript
db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
})
.limit(20)
.explain("executionStats");
```

This index has two leading equality fields (`active`, `category`) and a trailing prefix/range field (`name_search`). This is a helpful design pattern **when the query shape actually matches it**. If most queries search by prefix without category, or need sorting by price, the optimal index may differ.

### 11.1. Metrics to Inspect

| Field in explain | Question to Answer |
| --- | --- |
| `winningPlan` | Did the planner choose `IXSCAN`, `FETCH`, `COLLSCAN`, or a `SORT` stage? |
| `indexBounds` (if present) | Does the prefix regex produce a narrow index range or a wide scan? |
| `totalKeysExamined` | How many index entries were traversed? |
| `totalDocsExamined` | How many actual documents were read/inspected? |
| `nReturned` | How many results were returned? |
| `executionTimeMillis` | Execution time for this explain run; also measure under representative workloads |

Do not see `IXSCAN` and immediately assume the query is optimal. If `totalKeysExamined` is huge compared to `nReturned`, an index scan can still be prohibitively expensive.

### 11.2. Controlled Comparison of Three Query Shapes

```javascript
// A. Case-sensitive prefix; a name index can be helpful.
db.products.find({ name: { $regex: "^Ban" } })
  .explain("executionStats");

// B. Case-insensitive prefix; does not use collation index like equality.
db.products.find({
  name: { $regex: "^ban", $options: "i" }
}).explain("executionStats");

// C. Prefix on normalized field, with a matching compound index.
db.products.find({
  active: true,
  category: "phu-kien",
  name_search: { $regex: "^ban" }
}).explain("executionStats");
```

Record `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `winningPlan`, and dataset size. The three queries above **do not have completely equivalent filters**, so raw latency comparison alone does not prove one algorithm is universally better; test business queries at comparable selectivity on a sufficiently large dataset.

**On a collection with four fixtures**, every query runs fast even with `COLLSCAN`. To evaluate indexes, generate a large test dataset with realistic name distributions and inspect plans rather than concluding from a handful of documents.

## 12. Regex on Embedded Fields, Arrays, and Mismatched Types

### 12.1. Embedded Documents

Suppose an order stores:

```json
{
  "_id": "order-001",
  "customerId": "customer-001",
  "shippingAddressSnapshot": {
    "recipient": "Nguyen Thi Lan",
    "city": "TP Ho Chi Minh"
  }
}
```

You can search by recipient name:

```javascript
db.orders.find({
  "shippingAddressSnapshot.recipient": {
    $regex: "^Nguyen"
  }
});
```

With Spring Data:

```java
Query query = Query.query(
    Criteria.where("shippingAddressSnapshot.recipient")
        .regex("^Nguyen"));

List<Order> found = mongoTemplate.find(query, Order.class);
```

The `Order` declaration needs a `shippingAddressSnapshot` property with an embedded subtype containing `recipient`. If `@Field("ship_to")` is used on the address, query mapping bound to `Order.class` can translate the Java path to BSON `ship_to.recipient`.

### 12.2. String Arrays

For example `Product.tags = ["office", "Featured"]`:

```javascript
db.products.find({
  tags: { $regex: "^fea", $options: "i" }
});
```

MongoDB inspects string elements inside the array and matches if **at least one element** fits. An index on `tags` becomes a **multikey index**, though unanchored or case-insensitive regexes can still scan broadly.

### 12.3. Null, Missing, and BSON Types

Regular regex queries apply to **string values**; missing fields, `null`, or non-string BSON numbers should not be assumed to automatically coerce into strings before matching.

```javascript
db.products.find({
  name: { $type: "string", $regex: "^Ban" }
});
```

If legacy data stored `name` as an object or number, perform migration/validation. `$regex` is neither a data-cleaning tool nor a substitute for schema validation.

## 13. Pagination, Sorting, and Resource Control

A search endpoint might invoke:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Query search = Query.query(
    Criteria.where("active").is(true)
        .and("category").is("phu-kien")
        .and("nameSearch").regex("^ban"))
    .with(PageRequest.of(
        0, 20,
        Sort.by(Sort.Order.asc("nameSearch"),
                Sort.Order.asc("id"))));

List<Product> page = mongoTemplate.find(search, Product.class);
```

Notes:

- `PageRequest` starts at **page 0**.
- Use a sort with a unique tie-breaker like `id`/`_id` to stabilize order when multiple products share the same `nameSearch`.
- With unanchored or unindexed regexes, `limit(20)` does not mean the server examines only 20 documents.
- When `Page<Product>` requires `totalElements`, a count query with the same filter can be very expensive. For "load more" UX, consider `Slice`, bounded results, or cursor scrolling.
- When sorting by `nameSearch` where the BSON field is `name_search`, use the Java property with `MongoTemplate.find(..., Product.class)`; in raw `mongosh`, use the BSON name.

For search UIs, consider returning a lean DTO containing `sku`, `name`, `price` and avoiding unnecessary large embedded objects. Projection shrinks payload transfer, yet does not fix a regex query scanning an entire collection.

## 14. Reactive MongoDB and Transactions

The reactive stack uses `ReactiveMongoTemplate` or `ReactiveMongoRepository`. BSON filters, regex rules, collation, and indexes **do not change**, only the return type is a publisher:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("active").is(true)
        .and("name").regex("^ban", "i"));

Flux<Product> products =
    reactiveMongoTemplate.find(query, Product.class);
```

The snippet assumes `reactiveMongoTemplate` is injected in the service. With `Flux`, the query executes when subscribed. Never call `block()` on the WebFlux event loop; Reactor backpressure also does not turn a broad regex scan into an index-optimized query.

Transactions can ensure writing `Order` and updating `Product.stock` happen consistently on supported topologies. However, transactions do not make `$regex` faster, do not turn collation into a regex index, and do not shield endpoints from CPU-heavy regex patterns.

If there is a feature looking up an SKU **to check before inserting**, use a unique index or an atomic conditional write to prevent duplicates; a regex query or `exists` check prior to insert is vulnerable to race conditions.

## 15. Testing Against Real MongoDB

A unit test checking only Java's `Pattern.compile(...)` does not prove the MongoDB server applies the same semantics, `@Field` mapping, or index behavior. Run integration tests against a real MongoDB instance or Testcontainers on an isolated test database.

### 15.1. Integration Test Comparing Case and Diacritics

```java
package com.example.minicommerce;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import com.example.minicommerce.domain.Product;

@SpringBootTest
class ProductRegexCriteriaIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void differentiatesRegexCaseCollationAndNormalizedPrefix() {
        List<String> ids = List.of(
            "regex-test-p1",
            "regex-test-p2",
            "regex-test-p3",
            "regex-test-p4");

        var raw = template.getCollection("products");
        Document fixtureFilter = new Document(
            "_id", new Document("$in", ids));
        raw.deleteMany(fixtureFilter);

        try {
            raw.insertMany(List.of(
                product(ids.get(0), "Ban phim Mini", "ban phim mini"),
                product(ids.get(1), "BAN PHIM Mini", "ban phim mini"),
                product(ids.get(2), "Bàn phím Mini", "ban phim mini"),
                product(ids.get(3), "Chuột Mini", "chuot mini")
            ));

            Query caseSensitive = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").regex("^Ban"));
            assertEquals(
                Set.of(ids.get(0)),
                resultIds(template.find(caseSensitive, Product.class)));

            Query ignoreCase = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").regex("^ban", "i"));
            assertEquals(
                Set.of(ids.get(0), ids.get(1)),
                resultIds(template.find(ignoreCase, Product.class)));

            Query equalityWithCollation = Query.query(
                Criteria.where("id").in(ids)
                    .and("name").is("ban phim mini"))
                .collation(Collation.of("vi").strength(
                    Collation.ComparisonLevel.secondary()));
            assertEquals(
                Set.of(ids.get(0), ids.get(1)),
                resultIds(template.find(
                    equalityWithCollation, Product.class)));

            Query normalizedPrefix = Query.query(
                Criteria.where("id").in(ids)
                    .and("nameSearch").regex("^ban"));
            assertEquals(
                Set.of(ids.get(0), ids.get(1), ids.get(2)),
                resultIds(template.find(
                    normalizedPrefix, Product.class)));
        } finally {
            raw.deleteMany(fixtureFilter);
        }
    }

    private static Document product(
            String id, String name, String nameSearch) {
        return new Document("_id", id)
            .append("sku", id)
            .append("name", name)
            .append("name_search", nameSearch)
            .append("category", "phu-kien")
            .append("active", true);
    }

    private static Set<String> resultIds(List<Product> products) {
        return products.stream()
            .map(Product::getId)
            .collect(Collectors.toSet());
    }
}
```

The test explicitly inserts raw BSON containing `name_search` to verify mapping `nameSearch` via `@Field`. Verifying index performance requires a separate benchmark on a large dataset; this test verifies **semantic results**, not the query plan.

Only delete fixtures in a dedicated test database and never run tests on production. If another service concurrently edits the same fixture IDs, tests can flake; isolate databases/collections per test suite.

### 15.2. Expanded Test Matrix

| Case | Expectation |
| --- | --- |
| `^Ban` case-sensitive | Matches only names starting strictly with `Ban` |
| `^ban` with `i` | Matches `Ban` and `BAN`, does not strip accents from `Bàn` |
| Equality + collation strength 2 | Case-insensitive, still accent-sensitive |
| Equality + collation strength 1 | Verify accent-stripping rules under `vi` locale and real input |
| `nameSearch` prefix `^ban` | Matches all three normalized names |
| Regex input containing `.` or `[` | When literal search is intended, escaped and not treated as wildcard/syntax |
| Empty or overly long input | API rejects instead of scanning all documents |
| BSON field `name_search` | Java uses `nameSearch` property, raw queries use BSON name |
| Prefix index `{ name: 1 }` | `explain` measures index range and examined keys |
| Collation index `strength: 2` | Equality with matching collation can use the index |
| Regex `i` on collation index | Do not assume equality-like optimization |
| Missing or null `name` | Query does not report false success; schema validation |
| Large dataset + pagination | Latency, size, sort, and timeouts stay within SLA |
| Reactive query | `StepVerifier` verifies emitted results upon subscription |

## 16. Common Pitfalls and How to Fix Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `^ban` does not find `Ban` | Regex is case-sensitive by default | Use `i` when needed, or a normalized field |
| Enabling `i` still misses `Bàn` when searching `ban` | Case-insensitive **does not mean** accent-insensitive | Use normalization or suitable collation equality |
| Created collation index yet regex remains slow | `$regex` is not collation-aware | Do not rely on collation indexes for regex `i` |
| Contains regex `Mini` scans broadly | No fixed start-of-string prefix | Use a dedicated search engine or switch to prefix requirements |
| `^Ban.*` is slower than `^Ban` | Redundant wildcard forces extra matching work | Keep prefixes simple when semantics match |
| Query shows `IXSCAN` yet is slow | Scanning many index keys, low-selectivity filter | Check `totalKeysExamined`/`nReturned` |
| Prefix index does not improve performance | Index does not match filter/sort/collation | Inspect the actual plan and query shape |
| Equality fails to use case-insensitive index | Query lacks matching collation | Match `locale`/`strength` on both index and query |
| User enters `.*` and returns too much data | User input interpreted as regex | `Pattern.quote`/character policy, limit, and validation |
| User sends pattern spiking CPU | Complex regex pattern, missing limits | Block arbitrary patterns, add timeouts/rate limits |
| Search misses updates after product rename | `name_search` was not synced | Update both fields, test migration/backfill |
| Querying `nameSearch` finds no BSON key | Stored under `name_search` | Check `@Field` and raw documents |
| Vietnamese sort differs from expectations | No collation configured, binary sort used | Choose language collation and matching index |
| Using repository `IgnoreCase` still scans | Derived query generates regex `i` | Inspect BSON/index, switch to collation equality if appropriate |
| Search UI loads too many documents | Missing limit, pagination, or projection | Bound size, use DTOs, measure performance |

## 17. Practice Exercises

**Exercise 1 — Regex Basics.** Insert the four `Product` fixtures. Write `mongosh` and `Criteria.regex(...)` queries to find names: starting with `Ban`, containing `Mini`, ending with `Mini`, and matching exact `Ban phim Mini`. Record matching IDs.

**Exercise 2 — Case and Vietnamese Diacritics.** Write `^ban` with `$options: "i"`. Compare results against equality with `collation: { locale: "vi", strength: 2 }`, then strength 1. Explain why those three approaches do not share identical semantics in all cases.

**Exercise 3 — Regex Injection.** Given inputs `M.ni`, `.*`, `[abc`, and a very long string, build a service treating inputs as **literal** via `Pattern.quote`, enforcing length and result caps. Verify that a string containing a dot does not behave as a wildcard.

**Exercise 4 — Prefix Indexes.** Create index `{ name: 1 }` on a large dataset. Compare `^Ban`, `Ban`, `Mini$`, and `^ban` with `i` using `explain("executionStats")`. Check `indexBounds`, `totalKeysExamined`, and `nReturned`.

**Exercise 5 — Collation Indexes.** Create index `{ name: 1 }` with `locale: "vi", strength: 2`. Run an **equality** query with the same collation and test a regex `i` query. Explain why equality performance cannot be extrapolated to regex.

**Exercise 6 — Normalized Field.** Write a function producing `nameSearch` per project rules. Backfill fixtures and test prefix `^ban` on `name_search`, combined with `active` and `category` filters. Create a compound index, inspect the query plan, and verify handling of `đ`, diacritics, and special symbols.

**Exercise 7 — API Integration.** Build a product search endpoint supporting category, prefix, and page limits. Whitelist sorts, add `active`/tenant filters, DTOs, and timeouts. Write integration tests with real MongoDB or Testcontainers.

**Extension Exercise — Choosing a Search Tool.** Analyze requirements for autocomplete, accent-insensitive search, fuzzy typo tolerance, and relevance ranking. Assess when standard MongoDB `$regex` is no longer suitable and MongoDB Search or a dedicated search engine is needed.

### Self-Check Questions

1. What are the differences among `^Ban`, `Ban`, and `^Ban.*` in terms of both results and index usage?
2. Does option `i` strip Vietnamese diacritics or only perform case-insensitive matching?
3. Why does a strength-2 collation index not automatically optimize a regex `i` query?
4. When should you use equality + collation instead of `$regex`?
5. How do `Criteria.regex(String, String)` and `Criteria.regex(Pattern)` express filters?
6. Why must user input be escaped when the goal is literal string matching?
7. Does `Pattern.quote` guarantee every prefix regex will be index-optimized?
8. Why is `IXSCAN` alone not enough to conclude a query is fast?
9. What data and migration costs does a `nameSearch` strategy introduce?
10. What other factors besides regex protect performance: filters, sorts, limits, projections, indexes, timeouts?

**Expected outcomes:** learners can write `Criteria` and repository regexes accurately, clearly distinguish **case-insensitive regex** from **collation-based equality**, explain why only certain prefix regexes use indexes effectively, and read `explain`. Learners can also design a safe normalized search field, test with Vietnamese data, and select an appropriate search solution as data scales.

## References

- [MongoDB Manual — $regex](https://www.mongodb.com/docs/manual/reference/operator/query/regex/) — syntax, options, PCRE2, prefix expressions, and index usage.
- [MongoDB Manual — Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — collation indexes and why `$regex` does not benefit from case-insensitive indexes.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale, strength, and index matching.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Query`, `Criteria`, query matching, collation, and index hints.
- [Spring Data MongoDB — Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html) — Java `Collation` API and attaching it to queries/indexes.
- [Spring Data MongoDB API — Criteria](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html) — `regex(String)`, `regex(String, options)`, and `regex(Pattern)` overloads.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — `StartingWith`, `Containing`, and `IgnoreCase` keywords.
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `winningPlan`, `indexBounds`, and `executionStats`.
