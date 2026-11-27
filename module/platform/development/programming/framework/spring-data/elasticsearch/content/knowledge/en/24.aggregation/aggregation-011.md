# Declaring Aggregations with NativeQuery and Reading Client Wrappers

Aggregations in Elasticsearch summarize data over the set of documents matching a query. Instead of only retrieving individual documents, an application can count products by category, compute average prices, find minimum/maximum prices, or aggregate monthly revenue.

In Spring Data Elasticsearch, you can declare aggregations using the **Elasticsearch Java API Client `Aggregation` type**, attach them to `NativeQuery`, and execute them via `ElasticsearchOperations.search(...)`.

The key takeaway of this lesson is distinguishing between two types:

- **Request aggregation**: `co.elastic.clients.elasticsearch._types.aggregations.Aggregation` describes the aggregation to run.
- **Response aggregate**: `co.elastic.clients.elasticsearch._types.aggregations.Aggregate` is a union type holding the result of a specific aggregation type.

Spring Data wraps these results in `ElasticsearchAggregations` and `ElasticsearchAggregation`. To read buckets or metrics, the application retrieves the wrapper from `SearchHits`, unwraps it, and accesses the matching variant of `Aggregate`.

## 1. What are aggregations used for?

Suppose the `products` index stores products with these fields:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORIES",
  "price": 1299000,
  "status": "PUBLISHED",
  "createdAt": "2026-10-20T08:30:00Z"
}
~~~

A reporting screen might need to:

- Count products by category.
- Compute the average price per category.
- Find the lowest and highest price.
- Count products created per month.
- Aggregate only published products or those belonging to a specific tenant.

The search query determines the **input document set**. The aggregation determines **how that document set is summarized**.

~~~mermaid
flowchart TD
    A["NativeQuery"] --> B["Query DSL: select documents"]
    A --> C["Aggregation DSL: describe the aggregation"]
    B --> D["Elasticsearch search request"]
    C --> D
    D --> E["Elasticsearch processes matching documents"]
    E --> F["Search hits"]
    E --> G["Aggregation results"]
    F --> H["SearchHits<T>"]
    G --> I["ElasticsearchAggregations wrapper"]
~~~

A single request can return both search hits and aggregation results. If the application only needs summary reports, you can set the number of returned document hits to 0 to avoid loading unnecessary data.

## 2. Distinguishing request Aggregation from response Aggregate

Their names look similar, yet their roles differ:

| Type | Package | Role |
|---|---|---|
| `Aggregation` | `co.elastic.clients.elasticsearch._types.aggregations.Aggregation` | Describes the aggregation sent to Elasticsearch |
| `Aggregate` | `co.elastic.clients.elasticsearch._types.aggregations.Aggregate` | Holds the aggregation result returned back |
| `ElasticsearchAggregation` | `org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation` | Spring Data wrapper for a single aggregation response |
| `ElasticsearchAggregations` | `org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations` | Spring Data wrapper for a collection of aggregation responses |
| `AggregationsContainer<?>` | `org.springframework.data.elasticsearch.core.AggregationsContainer` | Spring Data abstraction for the aggregation container |
| `SearchHits<T>` | `org.springframework.data.elasticsearch.core.SearchHits` | Search result containing hits and the aggregation container |

These are the two most important types to tell apart:

~~~java
// Request: declare the aggregation to run
co.elastic.clients.elasticsearch._types.aggregations.Aggregation requestAggregation;

// Response: result of the aggregation
co.elastic.clients.elasticsearch._types.aggregations.Aggregate responseAggregate;
~~~

For example, a request aggregation might ask to compute the average on the `price` field. When the response returns, `Aggregate` holds the average variant and the calculated mean value.

Never pass a response `Aggregate` into `NativeQuery`. Conversely, you cannot read results from a request `Aggregation`: the request only describes the work Elasticsearch should execute.

## 3. Preparing mappings for aggregations

Aggregations require fields with appropriate data types.

~~~java
import java.math.BigDecimal;
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
    private String productId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
~~~

Some principles:

- Use `keyword` for categories, statuses, codes, and values requiring exact grouping.
- Use numeric types such as `integer`, `long`, `double`, or `scaled_float` for arithmetic calculations.
- Use `date` for timestamps and date histograms.
- Do not use a `text` field directly for standard terms aggregations unless fielddata is enabled. With multi-fields, use a keyword subfield such as `name.keyword`.

Corresponding mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "status": {
        "type": "keyword"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

If the mapping does not support aggregations on the field, the request may fail or yield unexpected results. Check the actual mapping in the cluster rather than relying solely on Java types.

## 4. Declaring a terms aggregation with Java API Client

A terms aggregation partitions documents into buckets based on a field's values.

Example counting products by category:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);
~~~

In this example:

- `Aggregation.of(...)` constructs the request aggregation.
- `terms(...)` selects the terms aggregation type.
- `field("category")` specifies the grouping field.
- `size(20)` requests at most 20 buckets to be returned.

If the documents are:

| productId | category | price |
|---|---|---:|
| P-1001 | ACCESSORIES | 1299000 |
| P-1002 | ACCESSORIES | 990000 |
| P-1003 | KEYBOARD | 1599000 |
| P-1004 | MONITOR | 4500000 |

The aggregation can return these buckets:

- ACCESSORIES: 2 documents.
- KEYBOARD: 1 document.
- MONITOR: 1 document.

Each bucket has a key and matching document count, typically read via `key()` and `docCount()`.

## 5. Declaring metric aggregations

Metric aggregations calculate one or more numeric values over a document set.

### Average

Compute average price:

~~~java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg
                .field("price")
        )
);
~~~

### Sum

Compute sum of field values:

~~~java
Aggregation totalPrice = Aggregation.of(a -> a
        .sum(sum -> sum
                .field("price")
        )
);
~~~

### Min and max

~~~java
Aggregation minPrice = Aggregation.of(a -> a
        .min(min -> min
                .field("price")
        )
);

Aggregation maxPrice = Aggregation.of(a -> a
        .max(max -> max
                .field("price")
        )
);
~~~

### Stats

When you need count, min, max, average, and sum in a single aggregation:

~~~java
Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats
                .field("price")
        )
);
~~~

Each metric is an independent aggregation. You can attach multiple aggregations to the same `NativeQuery` using distinct names.

## 6. Attaching aggregations to NativeQuery

Spring Data Elasticsearch provides `NativeQuery` to use Query DSL and aggregations from the Elasticsearch Java API Client.

Example counting products by category only:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .build();
~~~

`by_category` is the aggregation's name in the request. The application uses this exact name to look up the result in the response.

You can attach multiple aggregations:

~~~java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats.field("price"))
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withAggregation("price_stats", priceStats)
        .build();
~~~

Aggregation names must be unique within the same level. Choose names that express business intent, such as `products_by_category`, `average_price`, or `orders_by_month`.

### Combining queries and aggregations

Aggregations run on the set of documents remaining after the main query filters the data.

Example aggregating only published products:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query publishedOnly = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("PUBLISHED"))
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .build();
~~~

Category buckets and average price are then computed only over documents with `status = PUBLISHED`.

If you need to filter documents for an aggregation while keeping other hits in the same response, use a filter aggregation or separate aggregation structure. Distinguish the top-level query from filters placed inside an aggregation.

## 7. Executing and retrieving the aggregation container from SearchHits

Execute `NativeQuery` via `ElasticsearchOperations.search(...)`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> searchHits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

Aggregations are returned in `SearchHits.getAggregations()`. The return type is the `AggregationsContainer<?>` abstraction, not directly a map of buckets.

With the ELC client used by Spring Data Elasticsearch, the concrete implementation is `ElasticsearchAggregations`. You can cast the wrapper to the concrete type to read results:

~~~java
import org.springframework.data.elasticsearch.core.AggregationsContainer;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

AggregationsContainer<?> container = searchHits.getAggregations();

if (container instanceof ElasticsearchAggregations aggregations) {
    // Read ElasticsearchAggregation entries by name.
}
~~~

This type check prevents a failed cast when a response lacks an aggregation container or uses a different implementation.

For a query known to use ELC and return aggregations, you can cast directly:

~~~java
ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) searchHits.getAggregations();
~~~

Avoid blind casts if the query might execute against a different implementation. The `AggregationsContainer<?>` abstraction lets Spring Data keep a uniform API, while the ELC wrapper grants access to the Java Client's response types.

## 8. Unwrapping the wrapper to read Aggregate

From `ElasticsearchAggregations`, retrieve an aggregation by its declared name:

~~~java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;

ElasticsearchAggregation categoryResult =
        aggregations.get("by_category");

Aggregate categoryAggregate = categoryResult.aggregation();
~~~

There are three classes to remember:

1. `ElasticsearchAggregations`: the collection of aggregation results.
2. `ElasticsearchAggregation`: wrapper for one specific aggregation.
3. `Aggregate`: the Elasticsearch Java API Client response union type.

`Aggregate` has many variants such as string terms, long terms, average, sum, stats, date histogram, and many others. Verify the right variant before reading data.

For instance, if the request is a terms aggregation on a keyword field, the response is typically string terms. If the request is average, the response is an average aggregate.

You cannot call `sterms()` on an average result or `avg()` on a terms result. Use variant-checking methods like `isSterms()`, `isAvg()`, and `isStats()` before extracting contents.

## 9. Reading buckets of a terms aggregation

Suppose the request declared:

~~~java
Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
);
~~~

Because `category` has a `keyword` mapping, the result is typically the string terms variant.

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

Aggregate categoryAggregate =
        aggregations.get("by_category").aggregation();

if (categoryAggregate.isSterms()) {
    for (StringTermsBucket bucket :
            categoryAggregate.sterms().buckets().array()) {

        String category = bucket.key().stringValue();
        long documentCount = bucket.docCount();

        System.out.println(category + ": " + documentCount);
    }
}
~~~

Components:

- `isSterms()`: checks whether the response is a string terms aggregate.
- `sterms()`: extracts the string terms aggregate payload.
- `buckets().array()`: retrieves the bucket list when the response uses array format.
- `bucket.key().stringValue()`: gets the string key.
- `bucket.docCount()`: number of documents belonging to the bucket.

The Java Client uses `FieldValue` for the key of a string terms bucket. For keyword fields, read the value via `stringValue()`.

### Numeric fields for terms aggregations

When grouping by a numeric field, the response may be long terms or double terms instead of string terms. For example, a `long` `rating` field can return the long terms variant:

~~~java
Aggregate ratingAggregate =
        aggregations.get("by_rating").aggregation();

if (ratingAggregate.isLterms()) {
    ratingAggregate.lterms().buckets().array().forEach(bucket -> {
        long rating = bucket.key();
        long count = bucket.docCount();

        System.out.println(rating + ": " + count);
    });
}
~~~

The response variant depends on the field mapping and aggregation type. Never assume every terms aggregation is `StringTermsAggregate`.

## 10. Reading metric aggregations

Metric aggregations do not have a bucket list like terms aggregations. They return calculated numeric values.

### Reading average

~~~java
Aggregate averageAggregate =
        aggregations.get("average_price").aggregation();

if (averageAggregate.isAvg()) {
    double average = averageAggregate.avg().value();
    System.out.println("Average price: " + average);
}
~~~

### Reading sum

~~~java
Aggregate sumAggregate =
        aggregations.get("total_price").aggregation();

if (sumAggregate.isSum()) {
    double total = sumAggregate.sum().value();
    System.out.println("Total price: " + total);
}
~~~

### Reading stats

~~~java
Aggregate statsAggregate =
        aggregations.get("price_stats").aggregation();

if (statsAggregate.isStats()) {
    var stats = statsAggregate.stats();

    System.out.println("Count: " + stats.count());
    System.out.println("Min: " + stats.min());
    System.out.println("Max: " + stats.max());
    System.out.println("Average: " + stats.avg());
    System.out.println("Sum: " + stats.sum());
}
~~~

With metrics, understand your input data and measurement units. For example, if `price` is stored in minor units (dong or cents), average and sum results use those same units. Do not convert to major currency units without explicit rounding rules.

## 11. Reading sub-aggregations inside buckets

Aggregations can be nested. For example:

- Group products by category.
- Within each category, calculate average price.

Declaration:

~~~java
Aggregation byCategoryWithAverage = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(20)
        )
        .aggregations(
                "average_price",
                Aggregation.of(sub -> sub
                        .avg(avg -> avg.field("price"))
                )
        )
);
~~~

When reading results, each bucket has its own sub-aggregation map:

~~~java
Aggregate categoryAggregate =
        aggregations.get("category_with_average").aggregation();

if (categoryAggregate.isSterms()) {
    for (var bucket :
            categoryAggregate.sterms().buckets().array()) {

        String category = bucket.key().stringValue();
        long count = bucket.docCount();

        Aggregate averagePriceAggregate =
                bucket.aggregations().get("average_price");

        double averagePrice = averagePriceAggregate.avg().value();

        System.out.println(
                category + ": count=" + count
                        + ", averagePrice=" + averagePrice
        );
    }
}
~~~

In this example:

- The parent bucket represents one category.
- `bucket.docCount()` is the number of documents in that category.
- `bucket.aggregations().get("average_price")` retrieves the sub-aggregation by name.
- `avg().value()` returns the average price inside that parent bucket.

Sub-aggregations compute over the parent bucket's document set, not over the entire index's document set.

When reading sub-aggregations of different types, you must still check the corresponding `Aggregate` variant.

## 12. Combining multiple aggregation types in one request

A dashboard may need both buckets and metrics:

~~~java
Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t.field("category").size(20))
);

Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation priceStats = Aggregation.of(a -> a
        .stats(stats -> stats.field("price"))
);

NativeQuery dashboardQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withAggregation("price_stats", priceStats)
        .build();

SearchHits<ProductDocument> dashboardHits =
        operations.search(dashboardQuery, ProductDocument.class);
~~~

After execution, read each aggregation using its exact name:

~~~java
ElasticsearchAggregations dashboardAggregations =
        (ElasticsearchAggregations) dashboardHits.getAggregations();

Aggregate categories =
        dashboardAggregations.get("by_category").aggregation();

Aggregate average =
        dashboardAggregations.get("average_price").aggregation();

Aggregate stats =
        dashboardAggregations.get("price_stats").aggregation();
~~~

Extract result-reading logic into dedicated helper methods or mappers when a dashboard uses many aggregations. This keeps services from mixing query-construction logic with DTO-mapping logic.

## 13. Returning aggregations only without document hits

If a screen only needs aggregated figures, returning many document hits is unnecessary. Set maximum hits to 0 in the query:

~~~java
NativeQuery aggregationOnlyQuery = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withAggregation("average_price", averagePrice)
        .withMaxResults(0)
        .build();
~~~

The response still includes aggregation results while avoiding returning document lists in hits.

This is a useful pattern for dashboards or statistics APIs. `SearchHits.getTotalHits()` and aggregation bucket counts represent two different concepts:

- `getTotalHits()` refers to the total documents matching the query.
- `bucket.docCount()` refers to the number of documents inside a bucket.
- Metric aggregations return aggregated values, not the number of returned document hits.

If you need both a document list and statistics, keep an appropriate page size and read both sections from the same response.

## 14. Date histogram aggregation

Date histogram groups documents by time intervals such as day, week, or month. It is a standard way to chart order counts or revenue over time.

Declaring by month:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;

Aggregation byMonth = Aggregation.of(a -> a
        .dateHistogram(d -> d
                .field("createdAt")
                .calendarInterval(CalendarInterval.Month)
        )
);
~~~

Attaching to NativeQuery:

~~~java
NativeQuery monthlyQuery = NativeQuery.builder()
        .withQuery(publishedOnly)
        .withAggregation("products_by_month", byMonth)
        .withMaxResults(0)
        .build();
~~~

Date histogram results contain buckets keyed by timestamp boundaries. Each bucket typically includes:

- Timestamp key (milliseconds).
- String key if the response provides `key_as_string`.
- Document count.
- Sub-aggregations if declared.

Abbreviated response example:

~~~json
{
  "aggregations": {
    "products_by_month": {
      "buckets": [
        {
          "key_as_string": "2026-09-01T00:00:00.000Z",
          "key": 1788220800000,
          "doc_count": 120
        },
        {
          "key_as_string": "2026-10-01T00:00:00.000Z",
          "key": 1788220800000,
          "doc_count": 145
        }
      ]
    }
  }
}
~~~

When using date histogram, pick timezone and calendar vs. fixed interval according to business rules. A calendar month differs from a fixed 30-day interval. For local-timezone reports, configure an appropriate timezone so day/month boundaries do not shift.

## 15. Terms aggregations have a bucket limit

A terms aggregation does not return every distinct value by default. The `size` parameter limits returned buckets, typically sorted by descending document count.

Example:

~~~java
Aggregation topCategories = Aggregation.of(a -> a
        .terms(t -> t
                .field("category")
                .size(10)
        )
);
~~~

This request asks for at most 10 categories. If 200 categories exist, the remaining 190 categories do not appear in that result.

Points to remember:

- `size` is the number of buckets returned, not the number of documents in each bucket.
- `shard_size` affects how many buckets each shard sends to the coordinator and can affect top-bucket accuracy.
- With high cardinality when all buckets must be traversed, consider composite aggregation instead of raising `size` arbitrarily.
- When sorting by a metric sub-aggregation or by key, configure `order` explicitly.

Do not take top 10 terms and assume the sum of those 10 buckets equals the total documents in the entire index. Omitted buckets may contain remaining documents.

## 16. Safely reading aggregations and converting to DTOs

Do not couple controllers directly to low-level Elasticsearch Java Client response types. Services can unwrap wrappers and map data into application DTOs.

Example DTO:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}
~~~

Mapper reading terms results:

~~~java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

public List<CategoryCount> readCategoryCounts(
        ElasticsearchAggregations aggregations
) {
    ElasticsearchAggregation result =
            aggregations.get("by_category");

    Aggregate aggregate = result.aggregation();

    if (!aggregate.isSterms()) {
        throw new IllegalStateException(
                "Expected string terms aggregation"
        );
    }

    List<CategoryCount> counts = new ArrayList<>();

    for (StringTermsBucket bucket :
            aggregate.sterms().buckets().array()) {
        counts.add(new CategoryCount(
                bucket.key().stringValue(),
                bucket.docCount()
        ));
    }

    return counts;
}
~~~

DTOs decouple the application interface from client response structures. If you later rename an aggregation or switch from terms to composite, you only adjust the mapper instead of modifying every controller.

In real services, handle cases where:

- `SearchHits.getAggregations()` is null.
- The named aggregation is missing.
- The `Aggregate` response has a different variant than expected.
- The bucket list is empty.
- A metric has no value because no documents matched.

Never assume every query always returns all aggregations as expected, especially when templates or filters are constructed dynamically.

## 17. Distinguishing aggregations from SQL group-by

You can roughly compare a terms aggregation to SQL `GROUP BY`:

~~~sql
SELECT category, COUNT(*)
FROM products
WHERE status = 'PUBLISHED'
GROUP BY category;
~~~

In Elasticsearch:

- Query/filter corresponds to selecting documents.
- Terms aggregation corresponds to grouping by category.
- `doc_count` corresponds to the number of documents in the bucket.
- Metric aggregations correspond to aggregate functions like AVG, SUM, MIN, MAX.

However, Elasticsearch aggregations have distinct properties:

- Results are distributed across multiple shards and then merged.
- Terms aggregations limit bucket counts and can exhibit distributed error in some configurations.
- Buckets and sub-aggregations can nest across multiple levels.
- Aggregations run over indexed fields/doc values rather than SQL operations over raw JSON sources.

Do not assume every aggregation behaves identically to an SQL statement running on a single table.

## 18. Common mistakes

### Mixing up imports for Aggregation and Aggregate

Requests use `Aggregation`; responses use `Aggregate`. Both live in the same package yet serve opposite roles. Name variables like `byCategoryAggregation` and `categoryAggregate` to tell them apart easily.

### Reading results directly from NativeQuery

`NativeQuery` holds only the request. Results live in `SearchHits.getAggregations()` after calling `ElasticsearchOperations.search(...)`.

### Forgetting the aggregation name

The name passed to `withAggregation("by_category", ...)` must match the name passed to `aggregations.get("by_category")`. Mismatched names prevent finding expected results.

### Casting responses to the wrong type

Terms on keywords typically return string terms; terms on numerics can return long terms or another type. Average returns an avg aggregate. Check `isSterms()`, `isLterms()`, `isAvg()`, `isStats()` before calling accessors.

### Aggregating on a text field

Text fields are generally unsuitable for terms aggregations because fielddata is disabled by default. Use a keyword subfield or declare a keyword mapping from the start.

### Thinking size is a document count

`terms.size(20)` is the maximum number of buckets returned, not 20 documents. `withMaxResults(0)` controls hit count independently from bucket count.

### Confusing bucket count with total hits

`SearchHits.getTotalHits()` is the total documents matching the query. `bucket.docCount()` is the number of documents in a single bucket. The two numbers can differ and serve different purposes.

### Skipping null checks on the aggregation container

If a response has no aggregations, `getAggregations()` can be null or empty. Check for null and verify container type before casting.

### Treating terms as a complete list of all values

Terms aggregations cap buckets by `size`. For high cardinality, consider composite aggregation and bucket pagination.

### Ignoring mappings and numeric units

Average or sum is only meaningful when numeric fields are mapped accurately and data units are consistent. For currency, do not sum amounts across different currencies without filtering or converting per business rules.

## 19. Workflow for implementing aggregations with NativeQuery

When building a reporting API:

1. Define the target document set and construct the corresponding query/filter.
2. Check mappings for fields used in buckets, metrics, and date histograms.
3. Choose the aggregation type: terms, avg, sum, stats, date histogram, or another suitable type.
4. Build the request `Aggregation` using the Java API Client.
5. Attach the aggregation to `NativeQuery` with a stable name.
6. Use `withMaxResults(0)` if document hits are not needed.
7. Execute via `ElasticsearchOperations.search(...)`.
8. Retrieve `SearchHits.getAggregations()` and check for null.
9. Cast the wrapper to `ElasticsearchAggregations` when using ELC.
10. Look up `ElasticsearchAggregation` by name and call `aggregation()`.
11. Verify the right `Aggregate` variant before reading buckets or metrics.
12. Map results into application DTOs.
13. Check bucket limits, distributed error bounds, and data units.
14. Test against empty indices, zero matching documents, and buckets exceeding limits.

## References

- [Spring Data Elasticsearch 5.4 — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/5.4/elasticsearch.html)
- [Spring Data Elasticsearch 5.4 — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch 5.4 — ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
- [Spring Data Elasticsearch 5.4 — ElasticsearchAggregation API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregation.html)
- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch Java API Client — Aggregations](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/aggregations.html)

## Conclusion

In Spring Data Elasticsearch, declare aggregations using the Elasticsearch Java API Client `Aggregation` type and attach them to `NativeQuery` via `withAggregation(name, aggregation)`. After calling `ElasticsearchOperations.search(...)`, retrieve the container from `SearchHits.getAggregations()`, cast to `ElasticsearchAggregations`, look up each `ElasticsearchAggregation` by name, and read the corresponding `Aggregate` response type. Always distinguish request `Aggregation` from response `Aggregate`, verify the right terms/metric variant, and map aggregated data into DTOs tailored to your application.
