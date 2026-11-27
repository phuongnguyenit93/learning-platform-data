# Between, LessThan, GreaterThan, Before, and After

When searching data in Spring Data Elasticsearch, many use cases need to restrict results to a range of values: products within a price range, orders created before a point in time, or events occurring after a timestamp. The keywords **`Between`**, **`LessThan`**, **`GreaterThan`**, **`Before`**, and **`After`** let you declare these conditions directly in Repository method names.

Spring Data parses the method name and generates the corresponding range query for Elasticsearch. This keeps common conditions readable without manually writing Query DSL. To query accurately, you need appropriate mappings for numeric or date fields, a clear understanding of which bounds are inclusive, and interval conventions that fit the business logic.

## 1. What are range queries used for?

A range query selects documents whose field value falls within or outside specified limits. The field is typically numeric or a date/time type.

Example product document:

```json
{
  "sku": "SKU-1001",
  "name": "Wireless Headphones",
  "priceInCents": 12990,
  "createdAt": "2026-10-15T09:30:00Z"
}
```

An application might need conditions such as:

- Price from 10,000 to 50,000 cents.
- Price lower than 20,000 cents.
- Price higher than 100,000 cents.
- Products created before a campaign start date.
- Events recorded after a specific point in time.

In Elasticsearch Query DSL, bounds are expressed using the operators `gt`, `gte`, `lt`, and `lte`:

| Operator | Meaning | Boundary value included? |
|---|---|---|
| `gt` | Greater than | No |
| `gte` | Greater than or equal | Yes |
| `lt` | Less than | No |
| `lte` | Less than or equal | Yes |

This is the foundation for understanding derived query keywords in Spring Data.

## 2. Declaring mappings for numeric and date/time fields

Before writing the Repository, declare fields with appropriate mapping types. Example entity `ProductDocument`:

```java
package com.example.catalog.product.document;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    protected ProductDocument() {
    }

    public ProductDocument(
            String id,
            String sku,
            String name,
            Long priceInCents,
            Instant createdAt) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.priceInCents = priceInCents;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public Long getPriceInCents() {
        return priceInCents;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Two important fields in this example:

- `priceInCents` uses `long` mapping, suitable for integer comparisons.
- `createdAt` uses `date` mapping, suitable for time-based range queries.

Storing prices in cents (or the system's smallest currency unit) helps avoid floating-point precision issues when comparing monetary values. If the business requires storing decimals, choose an appropriate mapping and representation such as `scaled_float` with an explicitly designed scaling factor; do not assume `double` is an exact currency type.

For date/time fields, `Instant` represents an absolute point in time in UTC. This keeps comparisons consistent across requests and data from different time zones. Spring Data converts Java values to the date format supported by Elasticsearch according to mapping/converter configuration.

**Note:** Annotations only describe the desired mapping when creating an index. If the `products` index already exists with different field types, editing annotations does not automatically alter the running index's mapping. Always inspect the actual mapping before running range queries.

## 3. `Between`: finding values within a range

`Between` is used when both lower and upper bounds are needed. For example, finding products priced from 10,000 to 50,000 cents:

```java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

import com.example.catalog.product.document.ProductDocument;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByPriceInCentsBetween(
        Long minPrice,
        Long maxPrice
    );
}
```

Calling the Repository:

```java
List<ProductDocument> products = productRepository
    .findByPriceInCentsBetween(10_000L, 50_000L);
```

The `Between` condition in a derived query is interpreted as inclusive on both bounds: the value must be greater than or equal to the lower bound and less than or equal to the upper bound. In terms of a range query, the corresponding condition is:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "gte": 10000,
        "lte": 50000
      }
    }
  }
}
```

Thus, products priced at exactly 10,000 or exactly 50,000 cents are included in the results.

The method name must use the Java property name `priceInCents`, not the index name or a renamed field name if the mapping configures a different field name. Spring Data relies on entity metadata to determine the corresponding Elasticsearch field.

### 3.1. `Between` with dates and times

`Between` also works with date/time fields:

```java
List<ProductDocument> findByCreatedAtBetween(
    Instant from,
    Instant to
);
```

Example:

```java
Instant from = Instant.parse("2026-10-01T00:00:00Z");
Instant to = Instant.parse("2026-11-01T00:00:00Z");

List<ProductDocument> products = productRepository
    .findByCreatedAtBetween(from, to);
```

The query includes both documents where `createdAt` equals `from` and documents where `createdAt` equals `to`. If `to` is used as the start timestamp of the next period, including both endpoints can cause a document sitting right on the boundary to appear in two consecutive intervals. A later section covers half-open intervals to avoid this issue.

## 4. `LessThan`: strictly smaller than a value

`LessThan` is used when only an upper bound is needed and the boundary value itself is excluded.

```java
List<ProductDocument> findByPriceInCentsLessThan(Long maxPrice);
```

Invocation:

```java
List<ProductDocument> affordable = productRepository
    .findByPriceInCentsLessThan(20_000L);
```

Equivalent condition:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "lt": 20000
      }
    }
  }
}
```

A product priced at 19,999 cents matches; a product priced at exactly 20,000 cents does not match.

If you want to include the boundary value, use `LessThanEqual`:

```java
List<ProductDocument> findByPriceInCentsLessThanEqual(Long maxPrice);
```

`LessThanEqual` corresponds to `lte`.

## 5. `GreaterThan`: strictly larger than a value

`GreaterThan` is used when only a lower bound is needed and the boundary value itself is excluded:

```java
List<ProductDocument> findByPriceInCentsGreaterThan(Long minPrice);
```

Invocation:

```java
List<ProductDocument> premiumProducts = productRepository
    .findByPriceInCentsGreaterThan(100_000L);
```

Corresponding range query:

```json
GET products/_search
{
  "query": {
    "range": {
      "priceInCents": {
        "gt": 100000
      }
    }
  }
}
```

A document priced at 100,001 cents matches; a document priced at exactly 100,000 cents does not match.

If you want to include the lower boundary value, use `GreaterThanEqual`:

```java
List<ProductDocument> findByPriceInCentsGreaterThanEqual(Long minPrice);
```

`GreaterThanEqual` corresponds to `gte`.

## 6. `Before` and `After`: comparing timestamps

`Before` and `After` are commonly used when the property is a date/time type. They express temporal semantics more clearly than `LessThan` and `GreaterThan`.

Repository example:

```java
import java.time.Instant;
import java.util.List;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCreatedAtBefore(Instant cutoff);

    List<ProductDocument> findByCreatedAtAfter(Instant cutoff);
}
```

Find products created before a cutoff timestamp:

```java
Instant cutoff = Instant.parse("2026-11-01T00:00:00Z");

List<ProductDocument> olderProducts = productRepository
    .findByCreatedAtBefore(cutoff);
```

`Before` corresponds to `lt`:

```json
GET products/_search
{
  "query": {
    "range": {
      "createdAt": {
        "lt": "2026-11-01T00:00:00Z"
      }
    }
  }
}
```

Find products created after a cutoff timestamp:

```java
List<ProductDocument> newerProducts = productRepository
    .findByCreatedAtAfter(cutoff);
```

`After` corresponds to `gt`:

```json
GET products/_search
{
  "query": {
    "range": {
      "createdAt": {
        "gt": "2026-11-01T00:00:00Z"
      }
    }
  }
}
```

Documents whose timestamp equals `cutoff` are excluded from both `Before` and `After`, because both are strict comparisons. If you need to include that timestamp, use `LessThanEqual` or `GreaterThanEqual` on the date/time field:

```java
List<ProductDocument> createdAtOrBefore(Instant cutoff);
List<ProductDocument> createdAtOrAfter(Instant cutoff);
```

In an actual Repository, declare the proper derived query names:

```java
List<ProductDocument> findByCreatedAtLessThanEqual(Instant cutoff);
List<ProductDocument> findByCreatedAtGreaterThanEqual(Instant cutoff);
```

`Before`/`After` can be seen as temporally named aliases for less-than/greater-than conditions. They still generate a range query on the date field, not a separate Elasticsearch query type.

## 7. Keyword comparison table

| Derived query keyword | Condition | Range operator |
|---|---|---|
| `Between(min, max)` | `min <= value <= max` | `gte` + `lte` |
| `LessThan(max)` | `value < max` | `lt` |
| `LessThanEqual(max)` | `value <= max` | `lte` |
| `GreaterThan(min)` | `value > min` | `gt` |
| `GreaterThanEqual(min)` | `value >= min` | `gte` |
| `Before(time)` | `value < time` | `lt` |
| `After(time)` | `value > time` | `gt` |

These keywords can be used with fields of compatible types. `Before` and `After` generally make method names clearer when the field represents time; `LessThan` and `GreaterThan` are commonly used for numbers.

## 8. Combining ranges with other conditions

A practical use case often combines a range with an exact match condition. For example, finding products in the `audio` category priced between 10,000 and 50,000 cents:

```java
List<ProductDocument> findByCategoryAndPriceInCentsBetween(
    String category,
    Long minPrice,
    Long maxPrice
);
```

Calling the Repository:

```java
List<ProductDocument> products = productRepository
    .findByCategoryAndPriceInCentsBetween(
        "audio",
        10_000L,
        50_000L
    );
```

This derived query combines a category filter with a price range. The `category` field should use `keyword` mapping, while `priceInCents` should be a numeric field.

Semantically equivalent Query DSL:

```json
GET products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "priceInCents": {
              "gte": 10000,
              "lte": 50000
            }
          }
        }
      ]
    }
  }
}
```

Range filters generally do not need relevance scoring. When building queries manually, placing them inside `bool.filter` clearly marks them as filtering clauses. With derived queries, Spring Data constructs the query structure from the method name.

## 9. Paginating and sorting range results

If a price range can return many products, the Repository can return a `Page` and accept a `Pageable`:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<ProductDocument> findByPriceInCentsBetween(
    Long minPrice,
    Long maxPrice,
    Pageable pageable
);
```

Usage:

```java
PageRequest pageRequest = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "priceInCents")
);

Page<ProductDocument> page = productRepository
    .findByPriceInCentsBetween(10_000L, 50_000L, pageRequest);
```

Spring Data translates `Pageable` into limits and ordering on the Elasticsearch query. The sort field should have a type that supports doc values, such as numeric, date, or `keyword`. Do not sort directly on a `text` field unless the mapping has an appropriate `keyword` subfield.

For typical pagination, `PageRequest` is convenient. However, Elasticsearch limits the depth of `from`/`size` pagination. If you need to read hundreds of thousands of documents in a range for export or batch processing, consider `search_after` with a stable sort and Point in Time (PIT) depending on your Elasticsearch version instead of incrementing the page number indefinitely.

## 10. Half-open time intervals: `[from, to)`

For time-based data, a very useful convention is an interval that **includes the start bound and excludes the end bound**:

\[
[from, to)
\]

That is:

\[
value \ge from \quad \text{and} \quad value < to
\]

For example, fetching events in October:

- `from = 2026-10-01T00:00:00Z`
- `to = 2026-11-01T00:00:00Z`

This condition includes every instant from the start of October up to right before the start of November. A document at exactly `2026-11-01T00:00:00Z` belongs to November and is not double-counted.

You can declare a derived query combining two operators:

```java
List<ProductDocument> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
    Instant from,
    Instant to
);
```

This is well suited for daily or monthly reports and contiguous time windows. It avoids calculating `23:59:59.999...` for the upper bound, which easily breaks when timestamp precision or serialization format changes.

If you use `Between`, both bounds are inclusive. Choose between `Between` and a half-open interval according to the exact business definition.

## 11. Time zones, formats, and timestamp precision

Elasticsearch stores dates internally as numeric values and formats them according to the date mapping. Range queries can accept ISO-8601 date strings, epoch millis, or formats permitted by the mapping.

A few points to note:

- Prefer `Instant` for absolute timestamps and pass values with `Z` or an explicit offset.
- If business logic is based on local calendar dates, determine the time zone before converting to `Instant`.
- Do not compare arbitrary date/time strings if the mapping is not declared as `date`.
- Determine timestamp precision. Standard `date` mapping usually uses millisecond precision; if nanosecond precision is required, consider `date_nanos` and check support in your Elasticsearch/Spring Data version.
- Use the same time zone convention across writes, query parameters, and reports.

Example converting a local calendar day into a UTC interval:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 10, 15);

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();
```

These two values form a single local calendar day interval, then convert it to UTC for querying. Avoid adding a fixed 24 hours for every local day if the time zone observes daylight saving transitions; use `LocalDate` and `ZoneId` to find the start of the next day.

## 12. Handling boundary values and input parameters

Before calling the Repository, validate input bounds:

```java
public List<ProductDocument> searchByPriceRange(Long min, Long max) {
    if (min == null || max == null) {
        throw new IllegalArgumentException("Price bounds are required");
    }

    if (min < 0 || max < 0) {
        throw new IllegalArgumentException("Price cannot be negative");
    }

    if (min > max) {
        throw new IllegalArgumentException(
            "Minimum price must not exceed maximum price"
        );
    }

    return productRepository.findByPriceInCentsBetween(min, max);
}
```

This example demonstrates validating lower/upper bounds before querying. Whether zero is allowed depends on business rules. If an API allows omitting one bound, the Service can choose the corresponding `GreaterThanEqual` or `LessThanEqual` method instead of passing a null argument to `Between`.

Missing fields or fields with null values in documents normally do not match range queries. If the system needs to distinguish "no price" from "price is 0", design fields and queries explicitly; do not treat null as a numeric value.

## 13. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Range query returns empty even though data looks within range | Field mapping is `text`/`keyword` instead of numeric/date | Inspect actual mapping and use an appropriate field type. |
| Exact boundary value does not appear | Using `LessThan`/`GreaterThan` or `Before`/`After`, which exclude boundaries | Use `LessThanEqual`, `GreaterThanEqual`, or `Between` when bounds must be inclusive. |
| Document on month boundary counted twice | Using inclusive `Between` for adjacent periods | Use a `[from, to)` interval with `GreaterThanEqual` and `LessThan`. |
| Date query shifted by one day | Inconsistent time zone conversion or using UTC day start/end instead of business time zone | Build `Instant` from `LocalDate` and the appropriate `ZoneId`. |
| Monetary comparison behaves unexpectedly | Using floating-point numbers where exact precision is needed | Store smallest currency units as integers or use scaled decimal mapping. |
| Derived query fails to be created | Property name in method does not match entity, or keyword is unsupported in version | Check property names, imports, and Spring Data version docs. |
| Sorting range results fails | Sorting on a `text` field without a keyword subfield | Sort on numeric/date fields or a `keyword` subfield. |
| Query omits documents missing the field | Range queries do not match documents without a field value | Handle missing fields separately if business logic requires it. |

When investigating, check three things in order: the property name in the method, the real mapping on the index, and the values stored in `_source`. A correct method name with the wrong mapping can still produce a query that returns zero results.

## 14. When to use derived queries vs. Query DSL

Derived queries are suitable when conditions are concise and can be expressed clearly in a method name:

```java
Page<ProductDocument> findByPriceInCentsBetween(
    Long min,
    Long max,
    Pageable pageable
);
```

When a query needs multiple `bool` groups, nested fields, aggregations, scripts, function scoring, or complex dynamic filters, method names can become unreadable. In such cases, move the use case to `ElasticsearchOperations` with `NativeQuery` or a dedicated repository fragment.

A range query written directly in Elasticsearch DSL looks like:

```json
{
  "range": {
    "createdAt": {
      "gte": "2026-10-01T00:00:00Z",
      "lt": "2026-11-01T00:00:00Z"
    }
  }
}
```

This is the half-open interval `[from, to)`. Whether using a derived query or Query DSL, boundary semantics must be defined consistently and tested with data right on the bounds.

## 15. Testing range conditions

Range queries are especially prone to off-by-one boundary bugs. An integration test should create documents just below, exactly on, and just above each bound.

Example for a price range from 10,000 to 20,000 cents:

| Document | Price | `Between(10000, 20000)` result |
|---|---:|---|
| A | 9,999 | No match |
| B | 10,000 | Match |
| C | 15,000 | Match |
| D | 20,000 | Match |
| E | 20,001 | No match |

With `LessThan(20000)`, the document priced at exactly 20,000 does not match. With `GreaterThan(10000)`, the document priced at exactly 10,000 does not match.

Example Repository integration test with Elasticsearch:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProductRepositoryRangeTest {

    @Autowired
    private ProductRepository productRepository;

    @BeforeEach
    void setUp() {
        productRepository.deleteAll();

        Instant now = Instant.parse("2026-10-15T00:00:00Z");
        productRepository.saveAll(List.of(
            new ProductDocument("p1", "SKU-1", "Below", 9_999L, now),
            new ProductDocument("p2", "SKU-2", "Lower edge", 10_000L, now),
            new ProductDocument("p3", "SKU-3", "Middle", 15_000L, now),
            new ProductDocument("p4", "SKU-4", "Upper edge", 20_000L, now),
            new ProductDocument("p5", "SKU-5", "Above", 20_001L, now)
        ));
    }

    @Test
    void betweenIncludesBothBounds() {
        List<ProductDocument> result = productRepository
            .findByPriceInCentsBetween(10_000L, 20_000L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p2", "p3", "p4");
    }

    @Test
    void lessThanExcludesTheUpperBound() {
        List<ProductDocument> result = productRepository
            .findByPriceInCentsLessThan(20_000L);

        assertThat(result)
            .extracting(ProductDocument::getId)
            .containsExactlyInAnyOrder("p1", "p2", "p3");
    }
}
```

This example illustrates how to verify semantics. The test requires a compatible Elasticsearch instance and a properly created `products` mapping. If the test uses a pre-existing index, delete/recreate the test index to avoid stale mappings affecting results. In a test environment, `deleteAll()` only deletes documents via the Repository; it does not replace index/mapping management.

## 16. Summary of keyword selection

- Use `Between` when you need a range with both lower and upper bounds and want both bounds included.
- Use `LessThan` when you need values strictly below an upper bound, excluding the bound.
- Use `GreaterThan` when you need values strictly above a lower bound, excluding the bound.
- Use `Before` for timestamps before a cutoff and `After` for timestamps after a cutoff; both also exclude values equal to the cutoff.
- Use `LessThanEqual` and `GreaterThanEqual` when a single bound must be inclusive.
- For consecutive time intervals, prefer `[from, to)` using `GreaterThanEqual` combined with `LessThan` to prevent overlap at boundaries.

Most importantly, understand exact range boundaries, use appropriate numeric/date mappings, keep time zones consistent, and test documents right at boundary values. When these pieces are clear, Spring Data Elasticsearch derived queries keep search conditions concise, readable, and maintainable.
