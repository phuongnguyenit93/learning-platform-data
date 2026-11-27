# Equality, Inequality, Greater Than, Less Than, and Value Ranges

In **Spring Data MongoDB**, you can create queries simply by declaring method names on a repository interface. For instance, `findByCategory` expresses equality, `findByPriceCentsGreaterThan` expresses greater-than, and `findByPriceCentsBetween` expresses a value range. Spring Data parses the method name, maps entity properties to BSON fields, and builds the MongoDB query when the method is called.

This lesson belongs to the **Derived Queries** chapter of the `SPRING_DATA_MONGODB` module. Beyond repository queries, this knowledge helps you use `MongoTemplate`, cross-check real MongoDB commands, design indexes, handle dates and times, write boundary tests, and diagnose slow queries. These operations also apply to document mapping, aggregations, transactions, and reactive access.

The most important takeaway is **understanding exact comparison boundaries**. Method names look like natural language, yet differences between `GreaterThan` and `GreaterThanEqual`, between `Between(a, b)` and `Between(Range.closed(a, b))`, or between `Not(value)` and `NotNull()` can produce completely wrong result sets.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Is`/`Equals`, `Not`, `GreaterThan`, `GreaterThanEqual`, `LessThan`, `LessThanEqual`, and `Between`.
2. Write valid repository method names and predict the corresponding MongoDB operators: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`.
3. Identify **open** and **closed** bounds accurately; use `org.springframework.data.domain.Range` to express intervals explicitly.
4. Combine conditions with `And` and `Or`, and add sorting, limits, and pagination.
5. Distinguish `null`, missing fields, strings, and numbers, as well as cases where comparisons behave unexpectedly.
6. Build timezone-aware date/time range filters using **exclusive** upper bounds to avoid missing or double-counting records.
7. Write equivalent queries with `MongoTemplate` or `@Query` when method names become overly long or inflexible.
8. Test boundary values, use indexes, and run `explain` to evaluate performance.

## 2. How Method Name Parsing Works

Consider the example:

```java
List<Product> findByCategoryAndPriceCentsGreaterThan(
        String category, long threshold);
```

Spring Data splits the method name into:

```text
find        By   Category       And   PriceCents       GreaterThan
│           │   │               │     │                │
Subject     │   Property 1      AND   Property 2       Comparison operator
            Subject/predicate delimiter
```

Equivalent logic in MongoDB:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gt: 100000 }
});
```

Key principles:

- Everything after `By` references the entity's **Java property names**, such as `priceCents`, not necessarily the BSON field name if `@Field` is used.
- Derived operators translate into queries specific to the **datastore**. `Between` on another database store does not necessarily share MongoDB's exact boundary rules.
- Repository methods are processed by Spring Data when creating the repository proxy; you do not implement each method manually.
- Typographical errors in property names or unparseable method names can prevent the application context from starting; run integration tests to verify mapping.
- Predicates execute on MongoDB Server. Java does not load the entire collection into memory to filter standard repository methods.

`MongoRepository` works well for simple, reusable queries; `MongoTemplate` is better suited when filters depend on multiple optional parameters, need complex conditions, or require fine-grained query control.

## 3. Running Dataset for This Lesson

Suppose the system has a `catalog_products` collection. Each product has a category, price stored in the **smallest currency unit**, stock quantity, status, publication timestamp, and warranty period (which may be absent).

Java entity:

```java
package dev.learning.catalog;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("catalog_products")
public record Product(
        @Id String id,
        String category,
        long priceCents,
        int stock,
        String status,
        Instant publishedAt,
        Integer warrantyMonths) {
}
```

Using integer `long` for `priceCents` keeps numeric comparison examples consistent without depending on `BigDecimal`/`Decimal128` representation details. If your business domain requires decimal arithmetic, still choose the appropriate BSON representation.

Sample test data:

| `_id` | `category` | `priceCents` | `status` | `warrantyMonths` |
| --- | --- | ---: | --- | --- |
| `book-099` | books | 99 000 | ACTIVE | Field absent |
| `book-100` | books | 100 000 | ACTIVE | 0 |
| `book-150` | books | 150 000 | ACTIVE | 12 |
| `book-200` | books | 200 000 | ARCHIVED | 24 |
| `book-201` | books | 201 000 | ACTIVE | 12 |
| `device-150` | devices | 150 000 | ACTIVE | 12 |

You can insert this data to experiment using `mongosh`:

```javascript
db.catalog_products.insertMany([
  {
    _id: "book-099", category: "books", priceCents: NumberLong("99000"),
    stock: 6, status: "ACTIVE", publishedAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "book-100", category: "books", priceCents: NumberLong("100000"),
    stock: 7, status: "ACTIVE", warrantyMonths: 0,
    publishedAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: "book-150", category: "books", priceCents: NumberLong("150000"),
    stock: 8, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-03T08:00:00Z")
  },
  {
    _id: "book-200", category: "books", priceCents: NumberLong("200000"),
    stock: 9, status: "ARCHIVED", warrantyMonths: 24,
    publishedAt: ISODate("2026-11-04T08:00:00Z")
  },
  {
    _id: "book-201", category: "books", priceCents: NumberLong("201000"),
    stock: 2, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-05T08:00:00Z")
  },
  {
    _id: "device-150", category: "devices", priceCents: NumberLong("150000"),
    stock: 4, status: "ACTIVE", warrantyMonths: 12,
    publishedAt: ISODate("2026-11-06T08:00:00Z")
  }
]);
```

Use an **isolated test database** because `insertMany` writes real documents and will throw duplicate `_id` errors if re-run on an uncleaned collection. In Java, `priceCents` is `long`, so BSON `NumberLong` clearly reflects its type.

## 4. Declaring the Repository with Comparison Operators

```java
package dev.learning.catalog;

import java.time.Instant;
import java.util.List;

import org.springframework.data.domain.Range;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    // Equality / inequality
    List<Product> findByCategory(String category);
    List<Product> findByCategoryIs(String category);
    List<Product> findByStatusNot(String status);

    // Price thresholds
    List<Product> findByPriceCentsGreaterThan(long value);
    List<Product> findByPriceCentsGreaterThanEqual(long value);
    List<Product> findByPriceCentsLessThan(long value);
    List<Product> findByPriceCentsLessThanEqual(long value);

    // Price ranges
    List<Product> findByPriceCentsBetween(long lower, long upper);
    List<Product> findByPriceCentsBetween(Range<Long> range);

    // Combining conditions
    List<Product> findByCategoryAndPriceCentsBetween(
            String category, Range<Long> range);

    // Date/time comparisons
    List<Product> findByPublishedAtAfter(Instant moment);
    List<Product> findByPublishedAtBefore(Instant moment);
    List<Product> findByPublishedAtBetween(Range<Instant> range);

    // Null/missing
    List<Product> findByWarrantyMonthsIsNull();
    List<Product> findByWarrantyMonthsIsNotNull();
    List<Product> findByWarrantyMonthsExists(boolean exists);
}
```

In the following sections, each operator is explained alongside its MongoDB query and result set on the `books` data. When you want only `books`, add a `Category` condition or an equivalent `@Query`, since standalone `findByPriceCents…` methods also match the `devices` category.

## 5. Equality Comparisons: Is, Equals, or No Suffix

Three common forms:

```java
List<Product> findByCategory(String category);
List<Product> findByCategoryIs(String category);
List<Product> findByCategoryEquals(String category);
```

All express **equality comparison** on `category`. With argument `"books"`, the equivalent query is:

```javascript
db.catalog_products.find({ category: "books" });

// Explicit semantic representation:
db.catalog_products.find({ category: { $eq: "books" } });
```

On the `books` data, this returns `book-099`, `book-100`, `book-150`, `book-200`, and `book-201`.

**Points to note:**

- Default string comparison is **case-sensitive**, depending on the collation in use. `"books"` usually differs from `"BOOKS"`.
- If querying by `@Id String` whose value looks like an ObjectId, Spring Data may convert the type when mapping `_id`. Always verify the actual BSON type.
- Equality on an entire **subdocument** can depend on field order and BSON structure; in many cases, compare one or more **child properties** instead of the whole object.
- When case-insensitive comparison is needed, Spring Data supports `IgnoreCase` for certain property types, but you should evaluate the generated query, indexes, and collation.

Example comparing a nested field:

```java
// If Product has a supplier property with a country property:
List<Product> findBySupplierCountry(String country);
```

For nested property paths, make sure the parser resolves the method name accurately; where nested names could be ambiguous, use an underscore per Spring Data's convention to mark the traversal boundary (e.g., `findBySupplier_Country`).

## 6. Inequality Comparisons: Not and `$ne` Semantics

```java
List<Product> findByStatusNot(String status);
```

Invocation:

```java
repository.findByStatusNot("ARCHIVED");
```

Logical query:

```javascript
db.catalog_products.find({
  status: { $ne: "ARCHIVED" }
});
```

Results include documents whose `status` differs from `ARCHIVED`, including the `ACTIVE` items in the sample dataset.

### 6.1. Common Trap: `$ne` Also Matches Missing Fields

For a non-`null` value, the `$ne` operator can also match documents **missing the checked field**.

```javascript
db.catalog_products.insertOne({
  _id: "book-missing-status",
  category: "books",
  priceCents: NumberLong("130000"),
  stock: 1,
  publishedAt: ISODate("2026-11-07T08:00:00Z")
});

db.catalog_products.find({
  status: { $ne: "ARCHIVED" }
});
// Can include "book-missing-status" even though it has no status field.
```

If "not ARCHIVED" also requires `status` **to exist and be non-null**, express both conditions. One explicit way uses `$nin` to exclude invalid values and `$exists` to exclude documents missing the field:

```javascript
db.catalog_products.find({
  status: { $nin: ["ARCHIVED", null], $exists: true }
});
```

In Spring Data, when conditions grow complex or must distinguish existence/non-null, use `MongoTemplate` or `@Query` to make intent explicit. Never infer from `findByStatusNot("ARCHIVED")` that every returned document has a valid status.

### 6.2. How Does Not(null) Differ from IsNotNull?

Spring Data supports `IsNull` / `IsNotNull` and `Not`:

```java
List<Product> findByWarrantyMonthsIsNull();
List<Product> findByWarrantyMonthsIsNotNull();
List<Product> findByWarrantyMonthsNot(Integer value);
```

BSON cases:

| Query | Interpretation |
| --- | --- |
| `{ warrantyMonths: null }` | Matches field equal to null **or missing field**. |
| `{ warrantyMonths: { $ne: null } }` | Matches field **present and non-null**. |
| `{ warrantyMonths: { $exists: true } }` | Matches field present, even if its value is null. |
| `{ warrantyMonths: { $exists: false } }` | Matches missing field only. |
| `{ warrantyMonths: { $ne: 12 } }` | Matches values other than 12; usually includes null/missing. |

For example, `findByWarrantyMonthsIsNull()` returns `book-099` if the field is missing; `findByWarrantyMonthsIsNotNull()` returns documents with warranties of 0, 12, and 24. Distinguish **unknown**, **not applicable**, and numeric `0` right in your domain model.

## 7. Greater Than and Greater Than or Equal

| Derived method | MongoDB operator | Logical condition |
| --- | --- | --- |
| `findByPriceCentsGreaterThan(x)` | `$gt` | `priceCents > x` |
| `findByPriceCentsGreaterThanEqual(x)` | `$gte` | `priceCents >= x` |

With `x = 150000`:

```java
List<Product> strict =
        repository.findByPriceCentsGreaterThan(150_000L);

List<Product> inclusive =
        repository.findByPriceCentsGreaterThanEqual(150_000L);
```

MongoDB equivalents:

```javascript
db.catalog_products.find({
  priceCents: { $gt: NumberLong("150000") }
});

db.catalog_products.find({
  priceCents: { $gte: NumberLong("150000") }
});
```

In the `books` category:

- `$gt: 150000` returns only `book-200` and `book-201`.
- `$gte: 150000` returns `book-150`, `book-200`, and `book-201`.

When calling these two methods in Java **without a category filter**, `device-150` is also returned by `$gte`. Read all conditions carefully rather than assuming a query implicitly targets only one category.

**Rule of thumb:** for a minimum acceptable price, choose `GreaterThanEqual`. For "more expensive than X", choose `GreaterThan` when X itself should be excluded.

## 8. Less Than and Less Than or Equal

| Derived method | MongoDB operator | Logical condition |
| --- | --- | --- |
| `findByPriceCentsLessThan(x)` | `$lt` | `priceCents < x` |
| `findByPriceCentsLessThanEqual(x)` | `$lte` | `priceCents <= x` |

With `x = 150000`:

```java
List<Product> strict =
        repository.findByPriceCentsLessThan(150_000L);

List<Product> inclusive =
        repository.findByPriceCentsLessThanEqual(150_000L);
```

```javascript
db.catalog_products.find({
  priceCents: { $lt: NumberLong("150000") }
});

db.catalog_products.find({
  priceCents: { $lte: NumberLong("150000") }
});
```

In the `books` category:

- `$lt: 150000` returns `book-099` and `book-100`.
- `$lte: 150000` also includes `book-150`.

There is no "auto-add 1" rule when choosing operators. For integer values, you *could* rewrite `x < k` as `x <= k - 1` under controlled conditions, but that easily breaks if data types or units change. Use the exact relational operator directly.

## 9. Between: Identifying Open vs. Closed Boundaries

This is the most important part of the lesson.

According to **Spring Data MongoDB**'s keyword table, the **two-argument** `Between` method translates into an **open interval**:

```java
List<Product> findByPriceCentsBetween(
        long lower, long upper);

repository.findByPriceCentsBetween(100_000L, 200_000L);
```

```javascript
db.catalog_products.find({
  priceCents: {
    $gt: NumberLong("100000"),
    $lt: NumberLong("200000")
  }
});
```

Among `books`, only `book-150` matches. Both `100000` and `200000` **are excluded**.

### 9.1. `Range<T>` Expresses Intent Precisely

Spring Data MongoDB also supports `org.springframework.data.domain.Range` with `Between`:

```java
import org.springframework.data.domain.Range;

List<Product> findByPriceCentsBetween(Range<Long> range);
```

There are four ways to declare bounds:

| Java Range | Mathematical notation | BSON filter on priceCents |
| --- | --- | --- |
| `Range.open(100_000L, 200_000L)` | `(100000, 200000)` | `$gt: 100000, $lt: 200000` |
| `Range.closed(100_000L, 200_000L)` | `[100000, 200000]` | `$gte: 100000, $lte: 200000` |
| `Range.leftOpen(100_000L, 200_000L)` | `(100000, 200000]` | `$gt: 100000, $lte: 200000` |
| `Range.rightOpen(100_000L, 200_000L)` | `[100000, 200000)` | `$gte: 100000, $lt: 200000` |

With the `books` data:

| Bounds | Matching products |
| --- | --- |
| Both open | `book-150` |
| Both closed | `book-100`, `book-150`, `book-200` |
| Left open | `book-150`, `book-200` |
| Right open | `book-100`, `book-150` |

Java code:

```java
Range<Long> inclusive =
        Range.closed(100_000L, 200_000L);

Range<Long> exclusive =
        Range.open(100_000L, 200_000L);

Range<Long> halfOpen =
        Range.rightOpen(100_000L, 200_000L);

List<Product> products =
        repository.findByPriceCentsBetween(inclusive);
```

**Selection rule:** when the UI states "price from 100,000 to 200,000" and both endpoints are inclusive, use `Range.closed` or `GreaterThanEqual`/`LessThanEqual`. When slicing time intervals or consecutive non-overlapping buckets, `[from, to)` is usually better.

### 9.2. Range with an Unbounded Endpoint

Spring Data Commons' `Range` API supports unbounded endpoints such as `Range.rightUnbounded(...)` or `Range.leftUnbounded(...)`. However, for optional search filters, a clearer approach is often **building a dynamic `Query`** based on which parameters are actually present:

- Neither min nor max: add no price filter.
- Only min: use `$gte`.
- Only max: use `$lte`.
- Both: construct an interval with business-defined inclusive/exclusive bounds.

Avoid forcing every request into `Between(min, max)` by inventing sentinel values like `0` or `Long.MAX_VALUE` without considering their data meaning.

### 9.3. Validating Input Before Querying

```java
public Range<Long> priceRange(long min, long max) {
    if (min < 0 || max < 0 || min > max) {
        throw new IllegalArgumentException("Invalid price range");
    }
    return Range.closed(min, max);
}
```

When `min == max`, a **closed** interval `[x, x]` means equality with `x`; an **open** interval `(x, x)` matches nothing. Never silently swap `min` and `max` if a user enters them reversed when the API contract requires a validation error.

## 10. Combining Multiple Conditions with And/Or

Example: "products in books, priced between 100,000–200,000, and ACTIVE":

```java
List<Product> findByCategoryAndPriceCentsBetweenAndStatus(
        String category,
        Range<Long> priceRange,
        String status);
```

Call:

```java
repository.findByCategoryAndPriceCentsBetweenAndStatus(
        "books",
        Range.closed(100_000L, 200_000L),
        "ACTIVE");
```

Equivalent BSON:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 },
  status: "ACTIVE"
});
```

Results: `book-100` and `book-150`; `book-200` is excluded because it is `ARCHIVED`.

### 10.1. Clarify Logical Grouping When Using Or

A method name such as:

```java
List<Product> findByCategoryAndStatusOrPriceCentsGreaterThan(
        String category, String status, long threshold);
```

may mean **(category AND status) OR priceCents > threshold**, not **category AND (status OR priceCents > threshold)**. When explicit parentheses are required, prefer `@Query` or `MongoTemplate`:

```javascript
db.catalog_products.find({
  category: "books",
  $or: [
    { status: "ACTIVE" },
    { priceCents: { $gt: 200000 } }
  ]
});
```

The shorter and clearer domain method names are, the easier code reviews become. For many dynamic conditions, creating repository methods for every parameter combination leads to bloated, hard-to-maintain APIs.

## 11. Date/Time Comparisons: After/Before and Half-Open Intervals

`After`/`Before` keywords are commonly used with timestamps:

```java
List<Product> findByPublishedAtAfter(Instant time);
List<Product> findByPublishedAtBefore(Instant time);
List<Product> findByPublishedAtBetween(Range<Instant> range);
```

Equivalent:

```javascript
db.catalog_products.find({
  publishedAt: { $gt: ISODate("2026-11-01T00:00:00Z") }
});

db.catalog_products.find({
  publishedAt: { $lt: ISODate("2026-11-02T00:00:00Z") }
});
```

`After` is **strictly greater than**, and `Before` is **strictly less than**. To query documents published during **a UTC day**, use `[startOfDay, nextStartOfDay)`:

```java
import java.time.Instant;
import org.springframework.data.domain.Range;

Instant start =
        Instant.parse("2026-11-03T00:00:00Z");
Instant nextStart =
        Instant.parse("2026-11-04T00:00:00Z");

Range<Instant> dayRange =
        Range.rightOpen(start, nextStart);

List<Product> results =
        repository.findByPublishedAtBetween(dayRange);
```

Advantages of half-open intervals:

- Includes every instant starting at `start` (including midnight itself).
- Excludes the exact start of the next day.
- Eliminates guessing "23:59:59.999" or precision differences across data sources.
- Consecutive days `[day1, day2)` and `[day2, day3)` **never overlap**.

### 11.1. Calendar Days in User Timezones

If an application serves users in Vietnam, a calendar day in `Asia/Ho_Chi_Minh` does not start at 00:00 UTC. Convert **start of day in `ZoneId`** to `Instant` before querying:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 3);

Instant start = day.atStartOfDay(zone).toInstant();
Instant nextStart = day.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();

Range<Instant> localDayRange =
        Range.rightOpen(start, nextStart);
```

This also handles regions with daylight saving time properly as long as you use an actual `ZoneId` instead of adding a fixed millisecond offset. BSON Date represents a UTC instant, while a timezone-based "day" is an **application-boundary rule**.

## 12. BSON Types, Null, and Comparison Correctness

MongoDB uses **BSON**, so when comparing numbers, strings, and dates, you must consider the actual types stored in documents.

### 12.1. Numbers and Strings Are Distinct Types

These two documents are not type-equivalent:

```javascript
{ _id: "P-1", priceCents: NumberLong("150000") }
{ _id: "P-2", priceCents: "150000" }
```

A numeric range query:

```javascript
db.catalog_products.find({
  priceCents: { $gte: 100000, $lte: 200000 }
});
```

matches **BSON numeric** values; do not expect it to parse the string `"150000"` into a number. MongoDB applies **type bracketing** for `$gt`/`$gte`/`$lt`/`$lte`. BSON numeric types `int`, `long`, `double`, and `decimal` are grouped together for comparisons, whereas strings do not belong to that group.

**Common bug:** a converter writes `BigDecimal` as a BSON string, while the application expects numeric filtering/sorting. When storage formats change, migrate legacy data and test real queries, not just Java deserialization.

### 12.2. String Comparisons and Collations

```javascript
{ category: "books" }
{ category: "BOOKS" }
```

Equality or range queries on strings depend on collation. By default, BSON/string comparison order may not match linguistic rules expected by users. `IgnoreCase` may generate a different query form (per Spring Data MongoDB docs, often regex-based), so it does not guarantee standard index usage like plain equality.

For diacritic-sensitive string searches and linguistic sorting, consider an appropriate collation and an index with the same collation. Do not confuse `LessThan` on strings with numeric comparisons over numbers stored as strings.

### 12.3. Null and Missing Fields

A `null` value in MongoDB and a **missing field** are two distinct states, yet certain predicates match both. Specifically:

- `{ warrantyMonths: null }`: typically matches **null or missing**.
- `{ warrantyMonths: { $ne: null } }`: matches **present and non-null**.
- `{ warrantyMonths: { $ne: 12 } }`: can match **missing fields**.
- `{ warrantyMonths: { $exists: true } }`: matches present fields, **even if null**.

If business logic must distinguish "not set" from "zero", avoid primitive `int` for optional fields. Use `Integer`, a status enum, or a dedicated status field paired with schema validation.

### 12.4. Arrays and Nested Fields

Comparison operators in MongoDB also have special rules when a field holds an array; for example, a numeric condition can match if any array element satisfies it. Never infer from a `greater-than` query on an array that *every* element in the array exceeds the threshold.

When multiple conditions must match **the same object element** in an array, check `$elemMatch` instead of putting two conditions on separate array paths. For embedded objects, Spring Data can derive property paths, though you should still verify the generated BSON field names.

## 13. When to Use `@Query` or `MongoTemplate`?

Query derivation fits well when methods are simple and have stable semantics. With dynamic filters or complex logical parentheses, explicit queries are easier to control.

### 13.1. `@Query`: Explicit Bounds and BSON Fields

```java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    @Query("{ 'category': ?0, 'priceCents': " +
           "{ '$gte': ?1, '$lte': ?2 } }")
    List<Product> findProductsWithinInclusivePrice(
            String category, long lower, long upper);
}
```

This `@Query` example sits directly on the repository interface alongside the derived methods above. Here `?0` is `category`, `?1` is lower, and `?2` is upper; closed bounds are stated explicitly with `$gte` and `$lte`.

Never concatenate user input directly into JSON query strings. Use parameter binding to avoid escaping errors and injection risks from external data.

### 13.2. `MongoTemplate`: Optional Price Range

```java
package dev.learning.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {
    private final MongoTemplate template;

    public ProductSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<Product> search(
            String category, Long min, Long max) {

        if (min != null && min < 0) {
            throw new IllegalArgumentException("Invalid min");
        }
        if (max != null && max < 0) {
            throw new IllegalArgumentException("Invalid max");
        }
        if (min != null && max != null && min > max) {
            throw new IllegalArgumentException("min must be <= max");
        }

        Query query = new Query();

        if (category != null && !category.isBlank()) {
            query.addCriteria(
                Criteria.where("category").is(category));
        }

        if (min != null || max != null) {
            Criteria price = Criteria.where("priceCents");
            if (min != null) {
                price = price.gte(min);
            }
            if (max != null) {
                price = price.lte(max);
            }
            query.addCriteria(price);
        }

        return template.find(query, Product.class);
    }
}
```

Using `Long` instead of `long` for optional min/max filters distinguishes **omitted parameter** from **0**. The service validates the range before querying; automatically swapping bounds can hide caller mistakes.

### 13.3. Dynamic Queries and Multiple Or Conditions

```java
Criteria wanted = new Criteria().orOperator(
        Criteria.where("status").is("ACTIVE"),
        Criteria.where("priceCents").gt(200_000L));

Query query = new Query()
        .addCriteria(Criteria.where("category").is("books"))
        .addCriteria(wanted);
```

This query corresponds to `category == "books" AND (status == "ACTIVE" OR priceCents > 200000)`. Cross-check results on test data to avoid inverting logical parentheses.

## 14. Sorting, Limiting, and Pagination

Comparisons are often paired with sorting:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Range;

Page<Product> findByCategoryAndPriceCentsBetween(
        String category,
        Range<Long> range,
        Pageable pageable);

List<Product> findTop5ByCategoryOrderByPriceCentsAsc(
        String category);
```

Invocation:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest page = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("priceCents"),
            Sort.Order.asc("id")
        )
);

Page<Product> products =
        repository.findByCategoryAndPriceCentsBetween(
                "books",
                Range.closed(100_000L, 200_000L),
                page);
```

**Why also sort by ID?** Multiple products can share the same price. When paginating, adding `id` as a secondary tie-breaker keeps ordering **more stable** across ties. Even so, when documents are concurrently updated, offset pagination can still duplicate or skip records across requests; choose a pagination strategy matching your consistency requirements.

`Page<T>` typically requires a count query for total elements. If the UI only needs to know whether a next page exists, `Slice<T>` avoids some counting overhead. With millions of records and deep pagination, consider keyset pagination over price + ID instead of large offsets.

## 15. Indexes and Query Plans

Logically correct queries are not automatically fast. For the common query:

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 }
}).sort({ priceCents: 1, _id: 1 });
```

A reference compound index:

```javascript
db.catalog_products.createIndex(
  { category: 1, priceCents: 1, _id: 1 },
  { name: "category_price_id" }
);
```

**Why this key order:** `category` is an **equality** filter, `priceCents` is both a **range** filter and sort key, and `_id` breaks ties among identical prices. This choice stems from the sample workload, not a universal recipe for every schema.

### 15.1. Equality Before Range

A common guideline when designing compound indexes is considering equality, sort, and range conditions (ESR). Field order affects whether the index can serve both filters and sorting. Diverse workloads may need multiple indexes; avoid creating one index per query method without measuring write amplification and index size.

### 15.2. `$ne` Typically Has Low Selectivity

A query `{ status: { $ne: "ARCHIVED" } }` can match most of the collection. An index on `status` does not guarantee fast execution; the server may choose a collection scan if reading nearly every document. When business states are finite, a query **explicitly selecting desired states** is often clearer and more selective:

```javascript
db.catalog_products.find({
  status: { $in: ["ACTIVE", "DRAFT"] }
});
```

Replacing `Not` with `In` is only valid when the status set is exhaustively defined by business rules; never rewrite queries this way if new statuses could be introduced later.

### 15.3. Inspecting with `explain`

```javascript
db.catalog_products.find({
  category: "books",
  priceCents: { $gte: 100000, $lte: 200000 }
}).sort({ priceCents: 1, _id: 1 })
  .explain("executionStats");
```

Observe:

- Whether `winningPlan` uses the intended index.
- `totalKeysExamined` and `totalDocsExamined` relative to `nReturned`.
- Whether an in-memory `SORT` stage appears (depending on the plan).
- Execution time under representative data and load.

Indexes add storage and write-update overhead. Never optimize based on a handful of seed documents; check real data distribution, cardinality, hot categories, and frequent query shapes.

## 16. Automated Testing of Boundary Values

The most critical test for `Between` puts **values exactly equal to both boundaries** into the dataset. Testing only a midpoint cannot distinguish `$gt/$lt` from `$gte/$lte`.

### 16.1. Integration Test with MongoDB

The example below uses Spring Boot test, the repository, and a dedicated test database. The test wipes the collection before seeding, so **never run this class against a production configuration**.

```java
package dev.learning.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.Range;

@SpringBootTest
class ProductDerivedQueryIntegrationTest {

    @Autowired
    ProductRepository repository;

    @BeforeEach
    void prepare() {
        repository.deleteAll(); // For isolated test database only.
        Instant published =
                Instant.parse("2026-11-03T08:00:00Z");

        repository.insert(List.of(
            new Product("book-099", "books",  99_000L, 6,
                    "ACTIVE", published, null),
            new Product("book-100", "books", 100_000L, 7,
                    "ACTIVE", published, 0),
            new Product("book-150", "books", 150_000L, 8,
                    "ACTIVE", published, 12),
            new Product("book-200", "books", 200_000L, 9,
                    "ARCHIVED", published, 24),
            new Product("book-201", "books", 201_000L, 2,
                    "ACTIVE", published, 12),
            new Product("device-150", "devices", 150_000L, 4,
                    "ACTIVE", published, 12)
        ));
    }

    @Test
    void betweenTwoArgumentsUsesOpenBounds() {
        var ids = repository.findByCategoryAndPriceCentsBetween(
                "books", Range.open(100_000L, 200_000L))
                .stream()
                .map(Product::id)
                .toList();

        assertThat(ids).containsExactlyInAnyOrder("book-150");
    }

    @Test
    void inclusiveBoundsIncludeBothEndpoints() {
        var ids = repository.findByCategoryAndPriceCentsBetween(
                "books", Range.closed(100_000L, 200_000L))
                .stream()
                .map(Product::id)
                .toList();

        assertThat(ids).containsExactlyInAnyOrder(
                "book-100", "book-150", "book-200");
    }

    @Test
    void greaterThanDiffersFromGreaterThanEqual() {
        var greater = repository
                .findByPriceCentsGreaterThan(200_000L)
                .stream().map(Product::id).toList();

        var inclusive = repository
                .findByPriceCentsGreaterThanEqual(200_000L)
                .stream().map(Product::id).toList();

        assertThat(greater).containsExactlyInAnyOrder("book-201");
        assertThat(inclusive)
                .containsExactlyInAnyOrder("book-200", "book-201");
    }

    @Test
    void missingWarrantyCanMatchIsNull() {
        var ids = repository.findByWarrantyMonthsIsNull()
                .stream().map(Product::id).toList();

        assertThat(ids).contains("book-099");
        assertThat(ids).doesNotContain("book-100");
    }
}
```

Assertions use `containsExactlyInAnyOrder` because the queries lack sorting, so MongoDB does not guarantee result order.

**Required addition:** `findByCategoryAndPriceCentsBetween(String, Range<Long>)` must be declared in `ProductRepository` as shown earlier. These tests check the `Range` overload's bounds; also add a direct test for the **two-argument** overload to confirm it uses `$gt/$lt`.

### 16.2. Direct Two-Argument Test

```java
@Test
void betweenWithTwoScalarArgumentsExcludesEndpoints() {
    var ids = repository
            .findByPriceCentsBetween(100_000L, 200_000L)
            .stream().map(Product::id).toList();

    // Both categories have an item priced at 150000.
    assertThat(ids).containsExactlyInAnyOrder(
            "book-150", "device-150");
}
```

The test suite should also cover:

| Scenario | Example | What to verify |
| --- | --- | --- |
| Equal to min | 100 000 | Included in `$gte`, excluded from `$gt`. |
| Equal to max | 200 000 | Included in `$lte`, excluded from `$lt`. |
| Inside interval | 150 000 | Included in both open and closed ranges. |
| Below min | 99 000 | Excluded from the range. |
| Above max | 201 000 | Excluded from the range. |
| Min = max | 150 000, 150 000 | Closed interval matches value; open interval matches nothing. |
| Min > max | 200 000, 100 000 | Service rejects input before querying. |
| Null/missing field | warranty absent | Verify `IsNull`, `IsNotNull`, `Not`. |
| Wrong BSON type price | `"150000"` | Not matched by numeric comparisons. |
| Midnight timestamp | `00:00:00Z` | Correct day-boundary handling. |

## 17. Reactive Repositories with the Same Operators

For reactive projects, Spring Data MongoDB provides `ReactiveMongoRepository`. Comparison keywords retain the same meaning, while return types become `Flux` or `Mono`:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Flux<Product> findByPriceCentsGreaterThanEqual(long value);

    Flux<Product> findByPriceCentsBetween(Range<Long> range);

    Mono<Long> countByCategory(String category);
}
```

Example:

```java
Flux<Product> filtered =
        reactiveRepository.findByPriceCentsBetween(
                Range.closed(100_000L, 200_000L));
```

Do not call `block()` on an event loop to convert reactive streams into `List` arbitrarily. BSON semantics and open/closed bounds remain identical in reactive mode; the differences lie in execution model, backpressure, error handling, and cancellation.

A reactive query does not automatically provide multi-document transactions. If a workflow must modify multiple documents atomically, configure an appropriate transaction manager/session and MongoDB topology.

## 18. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Assuming `Between(a, b)` includes both endpoints | Misses items equal to min/max | Use `Range.closed` or `$gte/$lte`. |
| Using `GreaterThan` instead of `GreaterThanEqual` | Drops exact threshold matches | Confirm boundary specs and test exact threshold values. |
| Using `Not(value)` to find "valid values" | Can return null or missing fields | Define valid states explicitly; add appropriate filters. |
| Assuming `IsNull` only matches BSON null | Can also match missing fields | Add `$exists` or `$type` when needed. |
| Storing prices as strings and comparing numerically | Broken filters, sorts, and aggregations | Store proper BSON numeric types and migrate old data. |
| Comparing `Instant` using local dates without timezone | Off-by-hours day filtering | Convert local dates to `Instant` intervals via `ZoneId`. |
| Writing overly long derived methods with Or/And | Wrong precedence and hard reviews | Use `@Query`/`MongoTemplate` with explicit grouping. |
| Mechanically indexing every property | More indexes, still slow queries | Design workload-driven compound indexes and check `explain`. |
| Assuming unordered queries return deterministic order | Flaky tests and unstable pagination | Add explicit sorting with a tie-breaker key. |
| Using comparison keywords on array fields without knowing semantics | Unexpected matches | Understand array comparison rules and `$elemMatch`. |
| Checking only compilation | Wrong property paths or slow plans | Run integration tests and inspect BSON query plans. |

## 19. Practice Exercises with Hints

**Exercise 1 — Price in a closed range.** Write a repository method finding `books` products priced from 100,000 to 200,000, **inclusive on both ends**. Describe the BSON and IDs from the sample dataset.

*Hint:* `findByCategoryAndPriceCentsBetween("books", Range.closed(100_000L, 200_000L))` → `$gte/$lte` → `book-100`, `book-150`, `book-200`.

**Exercise 2 — Price in an open range.** Use the `findByPriceCentsBetween(long, long)` overload for thresholds 100,000 and 200,000. Why is `book-100` excluded?

*Hint:* Spring Data MongoDB maps the two-parameter `Between` to `$gt` and `$lt`; exact threshold values are excluded.

**Exercise 3 — Checking warranty field.** Pick queries for three requirements: (a) missing field, (b) field present and non-null, (c) value different from 12 including unset. Compare `Exists`, `IsNotNull`, and `Not`.

*Hint:* (a) `$exists: false`, (b) `$ne: null`, (c) `$ne: 12`. Do not confuse (c) with "field must exist".

**Exercise 4 — Filtering a day in Vietnam time.** Given a `LocalDate` and `ZoneId.of("Asia/Ho_Chi_Minh")`, construct `Range.rightOpen(start, nextStart)`. Explain why you should not use `[00:00, 23:59:59]` in UTC.

*Hint:* The user's timezone defines day boundaries; half-open intervals do not overlap and avoid assuming millisecond precision across sources.

**Exercise 5 — Optimizing product search.** The workload filters by equality on `category`, range on `priceCents`, and sorts ascending by price then ID. Propose a compound index and verify with `explain("executionStats")`.

*Hint:* test `{ category: 1, priceCents: 1, _id: 1 }`; inspect keys/docs examined and keep the index only if it benefits the workload.

**Exercise 6 — Writing optional filters.** An API takes `category`, `minPrice`, and `maxPrice`, each optional. Write `MongoTemplate` code adding `Criteria.gte/lte` only when provided; reject `min > max`.

*Hint:* use nullable `Long` parameters for filters and validate before building `Query`; avoid creating a separate method name per combination.

## 20. Checklist and References

Before shipping a derived method to a service, verify:

- [ ] Java property names and BSON field mappings are correct.
- [ ] Correct choice of `Equal/Not/GreaterThan/GreaterThanEqual/LessThan/LessThanEqual`.
- [ ] For `Between`, open/closed bounds are verified and `Range` is used where appropriate.
- [ ] Tested with values **equal to each boundary**, below min, and above max.
- [ ] Semantics of `null` and missing fields are accounted for, especially with `$ne`.
- [ ] BSON types verified for numbers, dates, ObjectIds, and strings; no mixing numbers and strings.
- [ ] Currency units, timezones, and precision normalized before building queries.
- [ ] `And/Or` combinations use explicit parentheses when logic gets complex.
- [ ] Explicit sorting used whenever deterministic ordering or pagination is needed.
- [ ] Indexes designed for the workload and verified via `explain`.
- [ ] Integration tests run against the target MongoDB Server and driver versions.

### Official Sources

1. [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): keyword table for `Not`, `GreaterThan`, `LessThan`, `Between`, `After`, `Before`, and BSON representations.
2. [Spring Data MongoDB — Defining Query Methods](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html): method-name parsing, `And/Or`, sorting, paging, and limiting.
3. [Spring Data Commons — Range API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Range.html): `open`, `closed`, `leftOpen`, `rightOpen`, and unbounded ranges.
4. [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria`, and comparison operators.
5. [MongoDB Manual — Comparison Query Predicate Operators](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/comparison/): `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte` operators.
6. [MongoDB Manual — Type Bracketing](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/): impact of BSON types on comparisons.
7. [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): distinguishing null values from missing fields.
8. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): reading query plans and execution statistics.
9. [MongoDB Manual — The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): principles for designing compound indexes for equality, sort, and range.

**Remember:** Repository method names are a structured way to express queries. Correctness comes from understanding the generated MongoDB operators, BSON data types, open/closed bounds, and null/missing semantics. Verify them with boundary data and inspect execution plans before relying on them in production logic.
