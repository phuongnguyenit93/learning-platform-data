# Declaring Aggregations and Reading Their Results

Elasticsearch aggregations summarize data directly on the index—for example, computing average price, total revenue, document counts per category, or grouping events by day. In Spring Data Elasticsearch, you can declare aggregations with `NativeQuery` and read their results via `SearchHits` and `ElasticsearchAggregations`.

Aggregations are not the same as pulling all documents into Java and grouping/calculating manually. Elasticsearch performs the aggregation over indexed data and returns buckets or metrics. This typically reduces the amount of data transferred to the application while leveraging the cluster's distributed processing.

## 1. What Is an Aggregation?

An aggregation is part of the Elasticsearch Query DSL used for data analysis. A single search request can return both document hits and aggregation results.

For example, on a `products` index, an application might need to:

- Compute minimum, maximum, average, and sum of prices.
- Count products by category.
- Count products by status.
- Group products into price ranges.
- Count events by day or month.
- Count distinct values of a field.

The typical processing flow is:

```text
NativeQuery
   |-- Query: filters the input document set
   |-- Aggregations: declares summary operations
            |
            v
ElasticsearchOperations.search(...)
            |
            v
SearchHits<T>
   |-- list of document hits
   |-- total hits / score / metadata
   |-- AggregationsContainer
            |
            v
ElasticsearchAggregations
   |-- ElasticsearchAggregation
            |
            v
Elasticsearch Java API Aggregate
            |
            v
Metric values / Bucket values
```

## 2. Main Aggregation Categories

Elasticsearch offers many aggregations, which fall into four primary categories:

| Category | Purpose | Examples |
|---|---|---|
| Metric | Computes one or more statistics over a document set | `avg`, `sum`, `min`, `max`, `stats`, `cardinality` |
| Bucket | Splits documents into groups by condition or value | `terms`, `range`, `date_histogram`, `filters` |
| Pipeline | Computes values based on outputs of other aggregations | `derivative`, `moving_fn`, `bucket_script` |
| Parent/child and nested | Aggregates across nested document structures or special relations | `nested`, `reverse_nested`, `children` |

Metric aggregations return statistical values. Bucket aggregations produce groups where each bucket can include document counts and sub-aggregations. Pipeline aggregations read results from other buckets or metrics to perform further calculations.

## 3. Sample Document and Mapping

Suppose an application manages sales orders:

```java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "sales")
public class SaleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double amount;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
```

Appropriate mapping is critical:

- `category` and `status` are `keyword`, suitable for terms aggregations.
- `amount` and `quantity` are numeric, suitable for sum, average, min, max, and range aggregations.
- `createdAt` is `date`, suitable for date histograms.

Do not run terms aggregations on a `text` field if the goal is grouping by exact whole values. `text` fields are tokenized by an analyzer; fielddata is normally disabled by default due to memory overhead. If you need both full-text search and aggregation by raw values, use a multi-field with a `keyword` subfield and aggregate on that subfield.

## 4. Declaring Aggregations with `NativeQuery`

Spring Data Elasticsearch's `NativeQuery` integrates with the Elasticsearch Java API Client (ELC). You can use the client's builders to declare queries and aggregations.

Example creating two aggregations: statistics on `amount` and order counts by `category`.

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Query query = NativeQuery.builder()
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ))
    )
    .build();
```

Aggregation names (`amount_stats`, `sales_by_category`) are chosen by the application. These names are used to retrieve results after execution. Fields in aggregations must match actual Elasticsearch field names, and their mapping types must match the aggregation type.

### Combining Query Conditions and Aggregations

Aggregations run over the document set matching the top-level query. For example, summarizing only completed orders:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("status")
        .value(v -> v.stringValue("COMPLETED"))
    ))
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t.field("category").size(20)))
    )
    .build();
```

In this example, both `amount_stats` and `sales_by_category` calculate only over documents with `status = COMPLETED`. Exact lambda syntax and builder types depend on the Elasticsearch Java Client version managed by Spring Data; the example uses the modern ELC API, not the legacy `RestHighLevelClient` API.

## 5. Executing the Query and Getting the Aggregation Container

Use `ElasticsearchOperations.search(...)` to execute the query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<SaleDocument> searchHits =
    operations.search(query, SaleDocument.class);
```

`SearchHits<T>` contains matching documents and search response metadata. Aggregation results are retrieved via `getAggregations()`:

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) searchHits.getAggregations();
```

`getAggregations()` may return null if the request declared no aggregations or the response contains none. When using queries with aggregations, check for null before casting or accessing results. Exact container types and accessors depend on the Spring Data Elasticsearch version.

Spring Data wraps ELC results in `ElasticsearchAggregations`. Each aggregation can be looked up by its declared name, and then accessed using the corresponding Elasticsearch Java Client aggregate type.

## 6. Reading Metric Aggregation Results

For a `stats` aggregation, Elasticsearch returns count, min, max, avg, and sum.

```java
import co.elastic.clients.elasticsearch._types.aggregations.StatsAggregate;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;

ElasticsearchAggregation amountAggregation =
    aggregations.get("amount_stats");

StatsAggregate amountStats =
    amountAggregation.aggregation().stats();

long count = amountStats.count();
double min = amountStats.min();
double max = amountStats.max();
double average = amountStats.avg();
double sum = amountStats.sum();
```

Results can be mapped into a DTO for reporting APIs:

```java
public record AmountSummary(
        long count,
        double min,
        double max,
        double average,
        double sum) {
}

AmountSummary summary = new AmountSummary(
    amountStats.count(),
    amountStats.min(),
    amountStats.max(),
    amountStats.avg(),
    amountStats.sum()
);
```

`stats` is convenient when you need multiple metrics on the same field. If you only need a single value, use `avg`, `sum`, `min`, `max`, or `value_count` so the response includes only what is needed.

### Commonly Used Metrics

| Aggregation | Result |
|---|---|
| `count` | Number of documents in a bucket or counted values depending on aggregation type |
| `value_count` | Number of indexed values for the field, which can differ from document count for array fields |
| `sum` | Sum of numeric values |
| `avg` | Arithmetic mean |
| `min` / `max` | Minimum / maximum value |
| `stats` | Count, min, max, avg, and sum |
| `extended_stats` | Adds statistics such as standard deviation and variance |
| `cardinality` | Approximate count of distinct values |
| `percentiles` | Percentiles of a numeric distribution |

`cardinality` is an approximation based on a probabilistic algorithm; do not treat its result as an exact distinct count in every case. If business requirements demand an exact figure, evaluate alternative calculation methods and their computational costs.

## 7. Reading Terms Aggregation Results

A terms aggregation creates buckets for distinct values of a field. Example counting orders by category:

```java
Aggregation.of(a -> a.terms(t -> t
    .field("category")
    .size(20)
))
```

Reading buckets:

```java
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;

StringTermsAggregate categoryTerms =
    aggregations.get("sales_by_category").aggregation().sterms();

for (StringTermsBucket bucket : categoryTerms.buckets().array()) {
    String category = bucket.key().stringValue();
    long documentCount = bucket.docCount();

    System.out.println(category + ": " + documentCount);
}
```

`sterms()` is used for terms aggregations over string values. For integer or floating-point fields, results may use `lterms()` or `dterms()` respectively. The aggregate accessor must match the actual field type and response.

### What Does `size` Mean?

`size(20)` requests up to the top 20 buckets according to default or configured ordering. It does not mean the aggregation only processes 20 documents. Elasticsearch evaluates all matching documents to build the buckets and then returns the requested number of buckets.

Distributed terms aggregations may require tuning `shard_size` to improve top-bucket accuracy in multi-shard clusters. Increasing `size` or `shard_size` increases memory usage and inter-shard data transfer; measure before setting large values.

## 8. Sub-Aggregations: Computing Metrics Inside Each Bucket

You can nest child aggregations inside bucket aggregations. For example, calculating total revenue and average amount for each category:

```java
Query query = NativeQuery.builder()
    .withAggregation(
        "sales_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ).aggregations(
            "revenue_sum",
            Aggregation.of(sub -> sub.sum(s -> s.field("amount")))
        ).aggregations(
            "average_amount",
            Aggregation.of(sub -> sub.avg(avg -> avg.field("amount")))
        ))
    )
    .build();
```

Each bucket in the result contains `doc_count`, `revenue_sum`, and `average_amount`. Result-reading code navigates from the parent aggregation down to child aggregations within each bucket. The ELC API uses the `Aggregate` union type, so check the appropriate bucket and metric variants before reading.

Sub-aggregations are useful for reports such as revenue per category, order counts by status, or average price by brand. Instead of sending a separate query per category, Elasticsearch performs all summarizations within a single request.

## 9. Date Histogram: Grouping Data Over Time

Date histogram splits documents into buckets by time intervals such as hour, day, week, or month. Example summarizing order counts per day:

```java
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;

Query query = NativeQuery.builder()
    .withAggregation(
        "sales_per_day",
        Aggregation.of(a -> a.dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Day)
            .timeZone("Asia/Ho_Chi_Minh")
        ))
    )
    .build();
```

`calendarInterval` uses calendar units such as day or month; `fixedInterval` uses fixed durations. For example, calendar days can be affected by timezones and daylight saving transitions, whereas fixed intervals always have a constant duration.

Reading daily buckets:

```java
import co.elastic.clients.elasticsearch._types.aggregations.DateHistogramAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.DateHistogramBucket;

DateHistogramAggregate daily =
    aggregations.get("sales_per_day").aggregation().dateHistogram();

for (DateHistogramBucket bucket : daily.buckets().array()) {
    String dateLabel = bucket.keyAsString();
    long documentCount = bucket.docCount();
}
```

If you need zero-count buckets across a date range, look into `min_doc_count: 0` together with `extended_bounds` so Elasticsearch generates empty buckets within the specified bounds. Without those settings, intervals with no documents may be omitted from the response.

When reporting by local day, specify the timezone explicitly in the aggregation. Do not merely convert timestamps to local time in Java after aggregating in UTC, because day boundaries can differ.

## 10. Range Aggregation and Numeric Histogram

Range aggregation divides numeric values into buckets according to predefined intervals. Example grouping orders by amount:

```json
{
  "aggs": {
    "amount_ranges": {
      "range": {
        "field": "amount",
        "ranges": [
          { "to": 100 },
          { "from": 100, "to": 500 },
          { "from": 500 }
        ]
      }
    }
  }
}
```

Intervals follow `[from, to)`: inclusive of the lower bound and exclusive of the upper bound. The example splits into under 100, from 100 up to under 500, and 500 and above.

Histogram aggregation splits values into equal-width intervals based on `interval`, making it suitable for price or quantity distribution charts. Unlike range aggregation, buckets are generated from a fixed interval width.

When reading range/histogram results, each bucket typically includes `key` or `key_as_string`, `from`/`to`, and `doc_count`. The exact bucket class depends on the declared aggregation type; read the matching variant on `Aggregate` instead of assuming all buckets are string terms.

## 11. Filter Aggregation and Aggregated Document Scope

There are two common places to filter documents before summarizing:

1. Top-level query: restricts both document hits and the input dataset for all regular aggregations.
2. Filter aggregation: creates a child bucket containing only documents matching a specific condition; sub-aggregations inside that bucket summarize only that subset.

For example, the query fetches all orders in the index, while computing revenue specifically for completed orders:

```json
{
  "size": 0,
  "aggs": {
    "completed_sales": {
      "filter": {
        "term": {
          "status": "COMPLETED"
        }
      },
      "aggs": {
        "total_amount": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

If the top-level query already filters `status = COMPLETED`, there is no need to repeat the same filter inside the aggregation unless serving a separate purpose. Another distinction is `post_filter`: it filters returned hits after aggregations run, so aggregations still reflect a broader document set than hits. Choose the filter location that matches the report's semantics.

## 12. Nested Aggregation for Nested Fields

If a document contains an array of objects mapped as `nested`, aggregations on nested properties must wrap inside a nested aggregation to enter the nested document context.

Mapping example:

```java
@Field(type = FieldType.Nested)
private List<OrderLineDocument> lines;
```

To aggregate by SKU of each order line, use a nested aggregation on path `lines`, and then place a terms aggregation on `lines.sku`. You may need `reverse_nested` if you want to step back up to the parent document context.

If the field is only a regular `object`, do not use a nested aggregation. Choosing the wrong context causes query errors or results that fail to reflect relationships within array elements as expected.

## 13. Reading Aggregations Safely and Mapping to DTOs

Aggregation results are structured data and should not leak raw client objects directly to public APIs. Map them into application DTOs:

```java
public record CategoryCount(String category, long count) {
}

public record SalesReport(
        AmountSummary amount,
        List<CategoryCount> categories) {
}
```

Service example reading stats and terms:

```java
import java.util.ArrayList;
import java.util.List;

import co.elastic.clients.elasticsearch._types.aggregations.StatsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SalesReport toReport(SearchHits<SaleDocument> hits) {
    if (!(hits.getAggregations() instanceof ElasticsearchAggregations aggs)) {
        throw new IllegalStateException("Expected aggregations in search response");
    }

    StatsAggregate stats = aggs.get("amount_stats").aggregation().stats();
    AmountSummary amount = new AmountSummary(
        stats.count(),
        stats.min(),
        stats.max(),
        stats.avg(),
        stats.sum()
    );

    StringTermsAggregate terms =
        aggs.get("sales_by_category").aggregation().sterms();

    List<CategoryCount> categories = new ArrayList<>();
    for (StringTermsBucket bucket : terms.buckets().array()) {
        categories.add(new CategoryCount(
            bucket.key().stringValue(),
            bucket.docCount()
        ));
    }

    return new SalesReport(amount, categories);
}
```

This example reads the two aggregations declared above. In production code, check that each aggregation exists and matches the expected type before accessing it; a misspelled name or reading the wrong aggregate variant causes runtime errors. You can extract helpers like `readStats`, `readStringTerms`, and `readDateHistogram` to avoid duplicating conversion logic.

### Avoid Arbitrary Type Casting

The Elasticsearch Java API Client represents many aggregation types within one union type `Aggregate`. A response can hold `sterms`, `lterms`, `dateHistogram`, `stats`, or other variants. Call the matching variant accessor or check `is...()` before reading. Do not force a numeric bucket into `StringTermsAggregate` merely because keys can be formatted as strings.

## 14. Returning Only Aggregations Without Document Hits

Summary reports sometimes do not need a list of documents. In that case, set hit size to 0 to shrink the response payload. In Spring Data versions supporting `setMaxResults`, you can configure the query to return no document hits:

```java
NativeQuery query = NativeQuery.builder()
    .withAggregation(
        "amount_stats",
        Aggregation.of(a -> a.stats(s -> s.field("amount")))
    )
    .build();

query.setMaxResults(0);

SearchHits<SaleDocument> hits =
    operations.search(query, SaleDocument.class);
```

Verify your version's query API to confirm how `size: 0` is configured. Even when no hits are returned, the response still contains aggregations. This is ideal for dashboards that display only summary numbers.

## 15. Bucket Pagination and Terms Aggregation Limits

Terms aggregations return a bounded number of buckets controlled by `size`. They work well for top-N categories, statuses, or brands. If you need to traverse a very large number of buckets, do not simply set `size` to an enormous value.

Composite aggregation is designed for paginating through buckets. The response returns `after_key`; the next request passes `after` to resume from that position. This is well suited when iterating over all value combinations, such as every `category` and `status` pair.

Distinction:

- `terms`: fetches top buckets by ordering/priority, convenient for dashboards.
- `composite`: paginates through buckets in a controlled manner.

Do not treat `terms.size` as an exact pagination mechanism for all buckets. For high-cardinality analysis, choose composite and handle `after_key`.

## 16. Performance and Accuracy of Aggregations

Aggregations can consume significant CPU, heap, and network bandwidth, especially with high cardinality or deeply nested buckets. Key guidelines:

- Aggregate on `keyword`, numeric, or date fields with proper mappings.
- Do not enable fielddata on `text` solely for terms aggregations when a `keyword` subfield can be created.
- Declare only the aggregations needed for the screen or report.
- Cap terms `size` and nested bucket counts.
- Place filters in the top-level query to shrink the input dataset when all aggregations share that filter.
- Treat `cardinality` as an approximation, not an exact count by default.
- Check top-terms accuracy in multi-shard clusters and adjust `shard_size` deliberately.
- Avoid multi-level high-cardinality aggregations without measuring resource impact.
- Consider caching or precomputing summary results for dashboards with repeated queries where strict real-time data is unnecessary.

`doc_values` are widely used for aggregations, sorting, and columnar field value access. Most keyword and numeric fields enable doc values by default. Do not disable doc values if the application needs to aggregate or sort on that field.

## 17. Testing Aggregations via REST API

Before translating a query into `NativeQuery`, you can test it directly in Elasticsearch Dev Tools to understand the response:

```http
GET /sales/_search
Content-Type: application/json

{
  "size": 0,
  "query": {
    "term": {
      "status": "COMPLETED"
    }
  },
  "aggs": {
    "amount_stats": {
      "stats": {
        "field": "amount"
      }
    },
    "sales_by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_amount": {
          "avg": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

The response will contain `aggregations.amount_stats` and `aggregations.sales_by_category.buckets`. Inspect aggregation names, keys, `doc_count`, and metric values before writing mapping code. Once the response structure is clear, map it to `NativeQuery` and the corresponding ELC types.

## 18. Common Mistakes

### Aggregating on a `text` Field

Terms aggregations require unanalyzed values, whereas `text` fields are tokenized. Use a `keyword` subfield or an appropriate field mapping. Do not enable fielddata casually, as it can consume large amounts of heap.

### Failing to Read Aggregations from `SearchHits`

The query may not have declared the aggregation, the lookup name may not match the declared name, or the code may cast the container to the wrong type. Check `getAggregations()` and the actual response.

### Calling the Wrong `Aggregate` Accessor

ELC uses a union type for aggregation responses. String terms use `sterms()`, stats metrics use `stats()`, and date histograms use `dateHistogram()`. Choose the type matching the declared request.

### Missing Buckets

Terms aggregations return only up to `size` buckets and distribute top-bucket selection across shards. When all buckets are needed, use composite aggregation; when improving top-terms accuracy, consider `shard_size`.

### Dates Grouped in the Wrong Timezone

Date histograms default to UTC if no timezone is specified. For local-day reporting, set `time_zone` in the aggregation and clearly decide between calendar interval and fixed interval.

### Metrics Do Not Match Expected Dataset

Aggregations compute over the document set selected by the top-level query. Inspect the query, filter aggregations, and `post_filter` to understand the exact aggregated data scope.

### Cardinality Value Differs from Exact Distinct Count

Cardinality is typically an estimate. If exact counts are required, choose an appropriate calculation strategy and evaluate its cost.

## 19. Workflow for Building Reports with NativeQuery

When implementing a report, follow these steps:

1. Define the input document set using the top-level query.
2. Identify required metrics: sum, avg, min, max, stats, cardinality, or percentiles.
3. Identify required buckets: terms, range, date histogram, filters, or nested.
4. Verify each field's mapping; use keyword for string grouping and numeric/date for corresponding computations.
5. Assign stable, descriptive, unique aggregation names within the query.
6. Use `NativeQuery.builder().withAggregation(...)` to declare aggregations.
7. Execute via `ElasticsearchOperations.search(...)`.
8. Retrieve `ElasticsearchAggregations` from `SearchHits` and read the right `Aggregate` variant.
9. Convert results into application DTOs so client types do not leak into your API unnecessarily.
10. Verify bucket limits, cardinality, timezones, filter scopes, and resource costs on production-like data.

## 20. Conclusion

In Spring Data Elasticsearch, `NativeQuery` allows declaring metric, bucket, and nested aggregations using the Elasticsearch Java API Client. Use `withAggregation(name, aggregation)` to attach aggregations to the query, execute through `ElasticsearchOperations.search(...)`, retrieve `ElasticsearchAggregations` from `SearchHits`, and access results by name.

Metric aggregations like `stats`, `sum`, and `avg` return statistical summaries; bucket aggregations like `terms`, `range`, and `date_histogram` group documents; sub-aggregations compute metrics within each bucket. Mappings must support the aggregation type, the top-level query controls the input document set, and results must be read via the matching `Aggregate` variant. For large bucket sets, high cardinality, or time-series reporting, pay attention to limits, accuracy, timezones, and performance. Mapping responses to clear DTOs keeps the reporting layer decoupled from the Elasticsearch client API.
