# `CriteriaQuery`: Comparing Values, Ranges, Dates, and Sets

Spring Data Elasticsearch provides the Criteria API to build queries using Java objects instead of writing raw JSON Query DSL directly. `Criteria` describes conditions on a field; `CriteriaQuery` wraps those conditions into a query that can be sent through `ElasticsearchOperations` or `ElasticsearchRestTemplate`.

The Criteria API is useful when filters are assembled from multiple request parameters, such as status, category, price range, time range, or a list of codes. Operators like `is`, `greaterThan`, `between`, `in`, and `notIn` express conditions clearly in code. To get accurate results, proper mapping is still required: code and status comparisons usually use `keyword`, prices use numeric types, and timestamps use `date`.

## 1. Role of `Criteria` and `CriteriaQuery`

`Criteria` represents a search condition. You can create a condition for one field and then combine it with other conditions using `and` or `or`.

`CriteriaQuery` takes a `Criteria` and provides a query for Spring Data Elasticsearch. `ElasticsearchOperations` executes the query on the target index and maps the results to the document class.

General flow:

```text
Request / Search criteria
        |
        v
Build Criteria
        |
        v
Create CriteriaQuery
        |
        v
ElasticsearchOperations.search(...)
        |
        v
Elasticsearch index
        |
        v
SearchHits / ProductDocument
```

Unlike query derivation, the Criteria API lets you add conditions conditionally in code. Unlike string-concatenated JSON, each condition is expressed with a Java API and parameters are passed directly.

## 2. Sample Document and Mapping

Suppose an application needs to search products by status, category, price, creation timestamp, and tags. The document can be declared as follows:

```java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    // Constructors, getters and setters
}
```

The mapping determines how Elasticsearch interprets each value:

| Field | Mapping type | Reason |
|---|---|---|
| `status` | `keyword` | Exact status comparison |
| `categoryId` | `keyword` | Category code comparison |
| `priceMinorUnits` | `long` | Numeric comparison and price range |
| `createdAt` | `date` | Time-based range query |
| `tags` | `keyword` | Finding documents with one or more tags |
| `available` | `boolean` | True/false filtering |

If `text` is used for codes or statuses, an analyzer can split and transform the content. Conditions requiring exact matches should typically use `keyword`. For monetary amounts, storing values in minor units as `long` avoids floating-point precision issues in business logic.

## 3. Creating a Simple Query with `is`

`is(value)` expresses an equality condition against a value. For example, finding products with status `PUBLISHED`:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Criteria criteria = new Criteria("status").is("PUBLISHED");
Query query = new CriteriaQuery(criteria);
```

Executing the query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ProductDocument> findPublished(
        ElasticsearchOperations operations) {

    Criteria criteria = new Criteria("status").is("PUBLISHED");
    Query query = new CriteriaQuery(criteria);

    return operations.search(query, ProductDocument.class);
}
```

For `keyword` fields, this condition typically has exact-match semantics. Do not confuse `is()` on a `text` field with a full-string SQL comparison; if full-text search on an analyzed field is needed, use an appropriate operator like `matches()` or an explicit full-text query.

## 4. Greater Than, Less Than, and Numeric Ranges

The Criteria API supports range operators. Commonly used operators include:

| Operator | Meaning | Bounds |
|---|---|---|
| `greaterThan(value)` | Greater than | Excludes boundary value |
| `greaterThanEqual(value)` | Greater than or equal to | Includes lower bound |
| `lessThan(value)` | Less than | Excludes boundary value |
| `lessThanEqual(value)` | Less than or equal to | Includes upper bound |
| `between(from, to)` | Within range | Check the boundary convention of your API/version; typically represents a range inclusive on both ends |

For example, finding products priced greater than or equal to 1,000,000 and less than 5,000,000 minor units:

```java
Criteria priceCriteria = new Criteria("priceMinorUnits")
    .greaterThanEqual(1_000_000L)
    .lessThan(5_000_000L);

Query query = new CriteriaQuery(priceCriteria);
```

This expression corresponds to the half-open interval:

\[
1{,}000{,}000 \leq priceMinorUnits < 5{,}000{,}000
\]

Using a pair of greater-than/less-than operators gives you explicit control over closed or open bounds. For example, the price range `[min, max]` uses `greaterThanEqual(min)` and `lessThanEqual(max)`; `[min, max)` uses `greaterThanEqual(min)` and `lessThan(max)`.

### Using `between`

When a two-ended range is needed, you can write:

```java
Criteria priceCriteria = new Criteria("priceMinorUnits")
    .between(1_000_000L, 5_000_000L);
```

`between` is concise when the application's range semantics match how the API translates it into a range query. If business rules depend strictly on whether bounds are inclusive or exclusive, choose explicit `greaterThanEqual`/`greaterThan` and `lessThanEqual`/`lessThan`, and inspect the actual query produced by your Spring Data version.

### Ranges with Floating-Point Numbers

For `double`, `float`, or `scaled_float` fields, range operators still work. However, you must consider precision and field quantization. With `scaled_float`, values are rounded according to `scaling_factor`; a threshold between two representable steps can yield different results from an exact decimal comparison in Java.

## 5. Comparing Dates, Times, and Time Intervals

Elasticsearch uses the `date` type to store points in time and supports range queries. In Java, `Instant` is usually appropriate when representing an absolute point in time in UTC.

For example, finding products created in a time interval from `from` to before `to`:

```java
import java.time.Instant;

public SearchHits<ProductDocument> findCreatedBetween(
        ElasticsearchOperations operations,
        Instant from,
        Instant to) {

    Criteria criteria = new Criteria("createdAt")
        .greaterThanEqual(from)
        .lessThan(to);

    Query query = new CriteriaQuery(criteria);
    return operations.search(query, ProductDocument.class);
}
```

The time interval above has the form `[from, to)`: inclusive of the start instant and exclusive of the end instant. This is useful when partitioning data by day or month because adjacent intervals do not overlap:

```text
Day 1: [2026-11-01T00:00:00Z, 2026-11-02T00:00:00Z)
Day 2: [2026-11-02T00:00:00Z, 2026-11-03T00:00:00Z)
```

A document timestamped exactly at midnight on day 2 belongs only to day 2's interval and is not counted twice.

### Choosing Time Types in Java

- `Instant`: an absolute point in time, suited for event timestamps.
- `OffsetDateTime`: a point in time with an explicit UTC offset.
- `LocalDate`: a calendar date without time of day, suited for birth dates or calendar effective dates.
- `LocalDateTime`: date and time without timezone; requires an explicit timezone convention before converting to a stored value.

For system logs and events, store timestamps in UTC and convert to the user's timezone in the presentation layer. If you receive a range as local calendar days, convert the start of the day and the start of the next day in that timezone to `Instant` before creating Criteria.

Example converting a local day to a UTC interval:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate day = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();

Criteria dateCriteria = new Criteria("createdAt")
    .greaterThanEqual(from)
    .lessThan(to);
```

Do not blindly add a fixed 24 hours to an `Instant` to find the next day in every timezone, because some timezones observe daylight saving time transitions. Computing the start of the next day from `LocalDate` and `ZoneId` preserves exact calendar-day semantics.

## 6. Filtering by Sets with `in`

`in(...)` finds documents whose field value lies within a set of values. This is a good choice when the client selects multiple categories, statuses, or codes.

For example, finding products belonging to one of three categories:

```java
import java.util.List;

List<String> categoryIds = List.of("coffee", "kitchen", "home");

Criteria criteria = new Criteria("categoryId").in(categoryIds);
Query query = new CriteriaQuery(criteria);
```

For `keyword` fields, this condition has semantics similar to a terms query: the field matches one of the values in the list. Equivalent JSON Query DSL conceptually:

```json
{
  "query": {
    "terms": {
      "categoryId": ["coffee", "kitchen", "home"]
    }
  }
}
```

`in` works well for finite value sets. If the list is very large, consider limiting the element count, request overhead, and alternative data modeling approaches. Do not send tens of thousands of values in a single terms query without measuring the impact.

## 7. Excluding Sets with `notIn`

`notIn(...)` expresses the condition that a field does not belong to the specified set of values.

For example, excluding the `DELETED` and `ARCHIVED` statuses:

```java
List<String> excludedStatuses = List.of("DELETED", "ARCHIVED");

Criteria criteria = new Criteria("status").notIn(excludedStatuses);
Query query = new CriteriaQuery(criteria);
```

In terms of Query DSL, exclusion is typically expressed using `bool.must_not` containing the corresponding terms condition.

Note: documents without the field or with an unindexed field can be treated as not matching the excluded condition and therefore appear in the results. If business rules require the field to exist, combine an appropriate existence condition or use an explicit query. Do not assume `notIn` means "the field exists and has a value outside the list".

## 8. Combining Comparisons, Ranges, Dates, and Sets

Conditions can be combined with `and`. For example, finding products that:

- Have status `PUBLISHED`.
- Belong to one of the selected categories.
- Have a price from the minimum up to below the maximum.
- Were created within the requested time interval.
- Are currently available.

```java
import java.time.Instant;
import java.util.Collection;

Criteria criteria = new Criteria("status").is("PUBLISHED")
    .and("categoryId").in(categoryIds)
    .and("priceMinorUnits").greaterThanEqual(minPrice)
    .lessThan(maxPrice)
    .and("createdAt").greaterThanEqual(from)
    .lessThan(to)
    .and("available").is(true);

Query query = new CriteriaQuery(criteria);
```

Corresponding logic:

```text
status = PUBLISHED
AND categoryId IN categoryIds
AND priceMinorUnits >= minPrice
AND priceMinorUnits < maxPrice
AND createdAt >= from
AND createdAt < to
AND available = true
```

Criteria expressions can be built by chaining. When there are many optional conditions, add each condition only when the parameter is actually provided.

### Combining with `or`

For example, finding products with status `PUBLISHED` or `FEATURED`:

```java
Criteria statusCriteria = new Criteria("status").is("PUBLISHED")
    .or("status").is("FEATURED");

Query query = new CriteriaQuery(statusCriteria);
```

OR can be used for multiple values of the same field. When one field needs to match one of several values, `in(...)` is usually more concise:

```java
Criteria statusCriteria = new Criteria("status")
    .in(List.of("PUBLISHED", "FEATURED"));
```

### When Complex Parenthesized Grouping Is Needed

If you need logic such as:

```text
(status = PUBLISHED OR status = FEATURED)
AND (categoryId = coffee OR categoryId = tea)
AND available = true
```

check the grouping capabilities of `Criteria` in your version. With multi-level nested bool queries, `NativeQuery` typically expresses this more clearly because `must`, `filter`, `should`, `must_not`, and `minimum_should_match` are represented directly. Do not chain multiple `.and()`/`.or()` calls without verifying the final condition grouping.

## 9. Building Dynamic Criteria from Search Parameters

In search APIs, many parameters are optional. For instance, a user might pass only category, or also add a price range and date range. Do not build queries with arbitrary default values for conditions if that alters the search meaning.

Create a criteria DTO:

```java
import java.time.Instant;
import java.util.List;

public class ProductSearchCriteria {
    private String status;
    private List<String> categoryIds;
    private Long minPrice;
    private Long maxPrice;
    private Instant createdFrom;
    private Instant createdTo;
    private Boolean available;

    // Getters and setters
}
```

Build Criteria only from parameters that have values:

```java
public Query buildQuery(ProductSearchCriteria request) {
    String status = request.getStatus() == null || request.getStatus().isBlank()
        ? "PUBLISHED"
        : request.getStatus();
    Criteria criteria = new Criteria("status").is(status);

    if (request.getCategoryIds() != null
            && !request.getCategoryIds().isEmpty()) {
        criteria = criteria.and("categoryId").in(request.getCategoryIds());
    }

    if (request.getMinPrice() != null) {
        criteria = criteria.and("priceMinorUnits")
            .greaterThanEqual(request.getMinPrice());
    }

    if (request.getMaxPrice() != null) {
        criteria = criteria.and("priceMinorUnits")
            .lessThan(request.getMaxPrice());
    }

    if (request.getCreatedFrom() != null) {
        criteria = criteria.and("createdAt")
            .greaterThanEqual(request.getCreatedFrom());
    }

    if (request.getCreatedTo() != null) {
        criteria = criteria.and("createdAt")
            .lessThan(request.getCreatedTo());
    }

    if (request.getAvailable() != null) {
        criteria = criteria.and("available").is(request.getAvailable());
    }

    return new CriteriaQuery(criteria);
}
```

In this example, `PUBLISHED` is the use case's default filter. If the request passes status, that value overrides the default; the code adds only one status condition. Resolving the value before building Criteria avoids accidentally requiring a field to equal two different statuses at once.

### Handling Empty Lists

Empty lists need explicit rules:

- If an omitted or empty list means "do not filter by list", skip the `in` condition.
- If an empty list means "no values are allowed", return an empty result immediately or create a query that matches nothing.
- If an empty list is invalid input, return a validation error.

Do not rely on terms-query behavior with an empty list to determine business behavior. Handle this case before building Criteria.

### Validating Input Ranges

Before building a range, check `minPrice <= maxPrice` and `createdFrom < createdTo`. If bounds are invalid, return a validation error instead of sending a nonsensical query.

## 10. Executing Queries with `ElasticsearchOperations`

After creating a `CriteriaQuery`, call `ElasticsearchOperations.search(...)`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(Query query) {
        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();
    }
}
```

`SearchHits` contains search result metadata such as total hits, score information, and the list of `SearchHit` objects. Each `SearchHit` has the document content along with associated metadata. If the application needs scores, highlights, or total result counts, keep `SearchHits` instead of converting straight to `List<ProductDocument>`.

### Specifying an Index or Alias

You can specify an explicit index/alias using `IndexCoordinates`:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

SearchHits<ProductDocument> hits = operations.search(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products-read")
);
```

This is useful when the application reads through an alias or an index different from the name declared in the document class. Ensure the alias points to an index whose mapping is compatible with `ProductDocument`.

## 11. Pagination and Sorting

CriteriaQuery can be combined with `Pageable` to limit results and sort them.

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Query query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.asc("priceMinorUnits"))
));

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
```

The example retrieves the first page, 20 documents per page, sorted by price ascending. The sort field name must match a sortable mapping; `text` is usually unsuitable for direct sorting, so use a `keyword` subfield or a dedicated field.

With large datasets, avoid deep pagination with `from`/`size` exceeding the result window limit. Consider `search_after` and a stable sort when paging through many pages. CriteriaQuery can still supply the filter conditions; the pagination strategy may need a more suitable query/operations API depending on the version.

## 12. Distinguishing `is`, `matches`, and Set Conditions

The Criteria API offers operators for several search styles. Choose based on mapping and goal:

| Operator | Typical meaning | Suitable mapping |
|---|---|---|
| `is(value)` | Value/term matching | `keyword`, boolean, numeric, date |
| `matches(text)` | Full-text match after analysis | `text` |
| `greaterThan` / `lessThan` | Open range | Numeric, date |
| `greaterThanEqual` / `lessThanEqual` | Range closed on one end | Numeric, date |
| `between` | Range between two values | Numeric, date |
| `in(values)` | Matches one value in a set | Usually `keyword`, numeric |
| `notIn(values)` | Excludes values in a set | Usually `keyword`, numeric |

Full-text example:

```java
Criteria textCriteria = new Criteria("description")
    .matches("coffee maker");
```

`matches` uses analyzed text search semantics, which differ from an exact term condition. When searching text content, configure an analyzer suited to the language and inspect tokens using `_analyze`.

## 13. Null, Missing Fields, and Empty Values

Elasticsearch does not handle null identically to SQL. A field absent from a document or sent as JSON `null` generally does not produce an indexable term for matching. Therefore:

- `is(null)` should not be assumed equivalent to SQL `column IS NULL` without checking how Criteria translates it into a query.
- `notIn(...)` may include documents missing the field.
- An empty string `""` is a distinct value from a missing field.
- A mapping's `null_value` setting can change how null is indexed.

If you need to check whether a field exists or does not exist, use the `exists` condition or an explicit query supported by your Spring Data version. For critical rules, inspect the Query DSL and real data rather than inferring SQL semantics.

## 14. When Is CriteriaQuery No Longer Appropriate?

CriteriaQuery fits relatively straightforward filter conditions: equality, ranges, sets, and ordinary combinations. When complex Query DSL structures are needed, consider `NativeQuery` or a custom repository.

| Need | Option to consider |
|---|---|
| Filtering by status, category, price, and date | `CriteriaQuery` |
| Adding optional filters from a request | Dynamically built `Criteria` |
| Simple full-text search on one field | Criteria `matches` or match query |
| Multiple nested bool groups, `minimum_should_match` | `NativeQuery` |
| Nested query on an array of objects | `NativeQuery` with nested query |
| Aggregations, highlighting, or specialized scoring | `NativeQuery`/`ElasticsearchOperations` |
| Short, fixed Query DSL | `@Query` |

Do not force the Criteria API to express unreadable logic just to avoid JSON Query DSL. Pick the API that lets maintainers see the exact conditions and logical grouping.

## 15. Verifying Queries and Results

When CriteriaQuery returns unexpected results, inspect each layer step by step.

### Check Mapping

```http
GET /products/_mapping
```

Confirm that `status` and `categoryId` are `keyword`, `priceMinorUnits` is numeric, `createdAt` is `date`, and fields used for sorting are sortable.

### Check Sample Data

Create documents with prices right on and outside the bounds, timestamps at the exact start/end of the interval, categories inside/outside the list, and missing fields. Then run the same conditions via direct Query DSL to compare with CriteriaQuery results.

### Check Timezone

For timestamps, confirm inputs have been converted to the right timezone and that `[from, to)` or `[from, to]` matches requirements. Timezone bugs often cause missing or extra documents at the start/end of a day.

### Check Lists

Confirm lists passed to `in`/`notIn` are validated, contain no unintended nulls, and have clear rules when empty.

### Inspect Actual Queries

You can enable logging in development environments to observe Elasticsearch requests or build the equivalent JSON and run it in Dev Tools. Logger names and levels depend on the version. Avoid logging payloads containing sensitive data in production.

## 16. Common Pitfalls

### Using `is()` on a `text` Field

`text` fields are tokenized by an analyzer; a term condition is not a SQL-style whole-string comparison. Use `keyword` for equality or `matches` for full-text.

### Using Ranges on String Fields

If prices or timestamps are mapped as `keyword`, range queries may compare lexicographically rather than numerically/chronologically. Declare proper numeric or `date` types from the start.

### Accidentally Including Time Boundaries

Using `lessThanEqual(to)` instead of `lessThan(to)` can cause two adjacent intervals to both include the boundary instant. For time partitioning, half-open intervals `[from, to)` generally avoid double counting.

### Passing an Empty List to `in`

An empty list may not carry the intended meaning and can produce an invalid or non-matching query. Handle it explicitly before creating Criteria.

### Combining AND/OR Without Verifying Grouping

Long Criteria chains can obscure logical structure. Write out the parenthesized expression first; for nested groups, use NativeQuery if clearer.

### Not Distinguishing Null from Missing Fields

Elasticsearch does not share SQL's null semantics. Check exists, `null_value`, and how the serializer writes documents.

### Sorting on Non-Sortable Fields

Sorting on `text` may fail or behave unexpectedly. Use a `keyword` subfield or an appropriate numeric/date field.

## 17. Workflow for Building CriteriaQuery

When implementing a search screen, you can follow this sequence:

1. List the fields users are allowed to filter on and identify their mapping types.
2. Determine the operator for each field: equality, greater/less than, range, set membership, or full-text.
3. Explicitly define whether price and time range bounds are inclusive or exclusive.
4. Normalize timezones and Java types before constructing date ranges.
5. Handle empty lists, null parameters, and invalid input ranges.
6. Build Criteria for each condition that has a value.
7. Wrap with `CriteriaQuery` and add pagination/sorting if needed.
8. Execute via `ElasticsearchOperations` and process `SearchHits`.
9. Verify mapping, queries, and results against boundary data.
10. Switch to `NativeQuery` when bool/nested logic or scoring exceeds what Criteria expresses cleanly.

## 18. Conclusion

CriteriaQuery helps build Elasticsearch queries with a Java API. `is` handles value equality, `greaterThan`/`lessThan` and their `Equal` variants handle numeric or time ranges, and `in`/`notIn` filter by sets. Conditions can be combined using `and` and `or`, then executed via `ElasticsearchOperations`.

The mapping must match the comparison: `keyword` for codes/statuses, numeric types for prices, `date` for timestamps, and `text` for full-text content. For dates, standardize timezones and choose range bounds explicitly; for sets, handle empty lists per business rules. When nested bool groups or specialized Query DSL are needed, use `NativeQuery` to express the logic directly rather than making the Criteria chain hard to understand.
