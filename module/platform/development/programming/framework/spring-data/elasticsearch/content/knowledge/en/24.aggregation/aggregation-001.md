# Distinguishing Aggregations from the List of Matched Documents

In Elasticsearch, a search request can return two different types of information: **documents matching the query** and **aggregation results computed over that set of documents**. The document list usually resides in `hits.hits`; aggregations reside in the `aggregations` section of the response. Both sections can appear together, but they solve two different needs.

For example, a product listing page needs to display 20 products matching a keyword. Those are the hits results. At the same time, the UI might need to know how many products exist per category, the average price, or the price range to build filters. Those are aggregations. You should not try to fetch thousands of documents into Java to count or average them yourself if Elasticsearch can perform the calculation directly.

An aggregation is not another form of pagination, and a bucket is not a document. A bucket is a group created by a value or condition; a metric is a number computed over the documents within the aggregation's scope. A search response can have empty hits while still having complete aggregations.

## 1. Hits and aggregations live in different parts of the response

Suppose the `products` index contains these documents:

```json
[
  { "sku": "KB-01", "name": "Mechanical Keyboard", "category": "keyboard", "price": 120 },
  { "sku": "KB-02", "name": "Wireless Keyboard", "category": "keyboard", "price": 180 },
  { "sku": "MS-01", "name": "Wireless Mouse", "category": "mouse", "price": 40 },
  { "sku": "MN-01", "name": "Gaming Monitor", "category": "monitor", "price": 300 }
]
```

A search request can both return documents and count products by category:

```http
GET /products/_search
{
  "size": 10,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
```

The response has two main sections:

```json
{
  "hits": {
    "total": {
      "value": 4,
      "relation": "eq"
    },
    "hits": [
      {
        "_id": "KB-01",
        "_source": {
          "sku": "KB-01",
          "name": "Mechanical Keyboard",
          "category": "keyboard",
          "price": 120
        }
      }
    ]
  },
  "aggregations": {
    "products_by_category": {
      "buckets": [
        { "key": "keyboard", "doc_count": 2 },
        { "key": "monitor", "doc_count": 1 },
        { "key": "mouse", "doc_count": 1 }
      ]
    }
  }
}
```

The abbreviated response example illustrates only one hit; an actual response can contain up to `size` hits. The `hits` section contains the returned documents and search metadata. The `aggregations` section contains the `products_by_category` group with buckets and the number of documents in each bucket.

| Component | Content | Used for |
|---|---|---|
| `hits.hits` | Specific documents | Displaying a list or reading the content of each document |
| `hits.total` | Total documents matching the query according to the tracking mode | Displaying total results or page count when needed |
| `aggregations` | Buckets and metrics | Statistics, facets/filters, charts, analytics |
| `bucket.doc_count` | Number of documents in a group | Counting documents by category, status, price range, etc. |
| Metric value | One or more numeric values | Calculating sum, average, min/max, cardinality, etc. |

## 2. Hits are the list of matched documents

`hits.hits` is the list of document results returned in the response. Each hit can contain:

- `_index`: the physical index containing the document.
- `_id`: the document identifier.
- `_score`: the relevance score if the query uses scoring.
- `_source`: the document content if requested to be returned.
- `sort`: the sort values, useful for `search_after`.
- `highlight`: highlighted fragments if highlighting is configured in the request.
- Other metadata depending on the request.

### 2.1 `size` controls the number of hits, not the aggregation

For example:

```json
{
  "size": 20,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
```

`size: 20` requests at most 20 documents in `hits.hits`. It does not mean the aggregation is only computed over those 20 documents. The aggregation is computed over the document set within the query scope (and the aggregation's scope), before taking the slice of hits according to `from`/`size`.

This point is crucial for paginated UIs: the first page might only display 20 products, yet the category facet still aggregates over the entire set of products matching the query, not just the 20 visible products.

### 2.2 `hits.total` differs from the sum of buckets

`hits.total` is the total number of documents matching the main query according to the total-hit tracking configuration. `bucket.doc_count` is the number of documents belonging to a specific bucket. The sum of `doc_count` across an aggregation does not always equal `hits.total`:

- A document can belong to multiple buckets, for example with terms on an array field.
- A terms aggregation might only return the top buckets (the aggregation's `size`).
- Some buckets might not be returned due to limits or bucket ordering.
- An aggregation can have its own filter/scope, making its document set differ from the main query.

Do not sum `doc_count` and treat it as the total matched documents without verifying the aggregation semantics.

## 3. Aggregations are statistical results over documents

An aggregation computes over the set of documents it receives. Common categories include:

- **Bucket aggregations:** partition documents into groups, such as terms, range, date histogram, or filters.
- **Metric aggregations:** compute values such as `sum`, `avg`, `min`, `max`, `stats`, or `cardinality`.
- **Pipeline aggregations:** compute based on the results of other aggregations, such as derivative, moving average, or bucket calculations depending on the type.

Aggregations can be nested. For example, grouping products by category and then computing the average price within each category.

### 3.1 Bucket aggregation

A terms aggregation groups documents by field value:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
```

`size: 0` at the search request level instructs Elasticsearch not to return document hits. Aggregations are still computed and returned. This is a common approach when an endpoint only needs statistics/facets.

Note that there are two different `size` properties in the example:

- Search-level `size: 0`: the number of document hits returned is 0.
- Aggregation-level `terms.size: 20`: at most 20 category buckets are returned.

These two values control completely different things.

### 3.2 Metric aggregation

A metric aggregation computes numbers on numeric fields:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
```

`stats` returns values such as count, min, max, avg, and sum. `avg` returns only the average value. These calculations are executed by Elasticsearch over the matching documents without requiring the application to load all documents to compute them in Java.

### 3.3 Nested aggregations

You can combine buckets and metrics:

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "max_price": {
          "max": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Each category bucket has its own `doc_count`, `average_price`, and `max_price`. This is how you generate data for an "average price by category" chart without fetching individual products into the application.

## 4. Document scope used by aggregations

Normally, top-level aggregations run on the set of documents matching the main query. If the query has a filter, the aggregation also receives that filtered set.

For example, aggregating only ACTIVE products:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
```

The `by_category` aggregation only aggregates ACTIVE documents because the main query restricts the document set.

### 4.1 Query filters affect both hits and aggregations

Conditions in `query.bool.filter` determine which documents participate in both the hits results and top-level aggregations. If the UI needs facets computed over all products regardless of the selected filters, you must design a different scope rather than placing all conditions in the main query.

### 4.2 `post_filter` only filters hits after aggregations

`post_filter` is a filter applied to hits after aggregations have been computed. This is useful for faceted navigation: a user selects a facet to narrow down the product list, yet wants that facet to still show counts for other options within the initial query scope.

Example:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "post_filter": {
    "term": {
      "color": "black"
    }
  },
  "aggs": {
    "colors": {
      "terms": {
        "field": "color"
      }
    }
  }
}
```

Hits only contain black products, but the `colors` aggregation is computed over products matching `name = keyboard` before `post_filter` is applied. Therefore, the facet can still display other colors along with their counts.

### 4.3 Filter aggregation

If only one aggregation needs an extra condition of its own, use a `filter` aggregation:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
      },
      "aggs": {
        "average_active_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

The `active_products` aggregation has its own scope of ACTIVE documents, while the main query still matches everything. You can create multiple filter buckets if you need statistics for different condition groups in the same response.

### 4.4 Global aggregation

A `global` aggregation ignores the top-level query scope and computes over all documents in the index targeted by the search request (subject to permissions/index limits and related constraints). It is useful when you need to compare filtered results against statistics for the entire index.

For example, the main query filters ACTIVE products, while a global aggregation computes the average price across all products:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "all_average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Do not use a global aggregation if you want to preserve the main query's filter. Because it expands the scope, be especially careful with multi-tenancy and authorization conditions. Security constraints must be enforced at the appropriate authorization/document-level security layer; do not rely on a normal query having a filter and assume a global aggregation automatically preserves that filter.

## 5. Common aggregation types

### 5.1 Terms aggregation: counting by value

Suitable for category, status, brand, or `keyword` fields:

```json
"aggs": {
  "by_status": {
    "terms": {
      "field": "status",
      "size": 10,
      "order": {
        "_count": "desc"
      }
    }
  }
}
```

By default, terms usually returns the buckets with the highest document count. `size` limits the number of buckets returned, not the number of documents in each bucket.

A distributed terms aggregation across multiple shards can have bucket count inaccuracies because each shard sends a number of candidate buckets to the coordinator. The response may include `doc_count_error_upper_bound` and `sum_other_doc_count`. If you need accuracy or all buckets, you must understand distributed limits and consider `shard_size`, composite aggregation, or a different design.

### 5.2 Range aggregation: grouping by numeric ranges

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 100 },
          { "from": 100, "to": 250 },
          { "from": 250 }
        ]
      }
    }
  }
}
```

Ranges use an inclusive lower bound and an exclusive upper bound according to range aggregation semantics. For example, a document with price exactly 100 belongs to the second range, not the first.

### 5.3 Date histogram: grouping by time

```http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "+07:00",
        "min_doc_count": 0
      }
    }
  }
}
```

Date histogram groups documents by calendar time intervals. `calendar_interval` suits calendar days/months/years; `fixed_interval` suits fixed durations like 15 minutes or 1 hour. Timezone affects bucket boundaries. If you need empty buckets for intervals with no documents, configure extended bounds and min doc count according to your display goal.

### 5.4 Metrics: sum, avg, min, max, stats

```json
"aggs": {
  "total_revenue": {
    "sum": {
      "field": "amount"
    }
  },
  "average_order_value": {
    "avg": {
      "field": "amount"
    }
  },
  "largest_order": {
    "max": {
      "field": "amount"
    }
  }
}
```

These metrics compute over documents that have suitable values in the field. Documents missing the field or having values not indexed as numeric do not contribute as regular numeric values.

### 5.5 Cardinality: counting unique values

```json
"aggs": {
  "unique_customers": {
    "cardinality": {
      "field": "customerId"
    }
  }
}
```

Cardinality is typically an approximate count based on the HyperLogLog++ algorithm. It is suitable for estimating unique customers over large sets. If the business requires an exact count, do not assume cardinality is an exact count; evaluate the cost and alternative data approaches.

### 5.6 Composite aggregation: iterating over many buckets

A terms aggregation returns a limited number of top buckets. If you need to paginate through a large number of buckets, a composite aggregation supports bucket pagination via `after_key`.

```http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "sources": [
          { "category": { "terms": { "field": "category" } } },
          { "brand": { "terms": { "field": "brand" } } }
        ]
      }
    }
  }
}
```

The response includes `after_key` when there are more buckets to fetch. The next request passes `after` equal to the exact `after_key` returned. Composite aggregation is designed for bucket pagination; it differs from `search_after`, which is used to paginate document hits.

## 6. Empty hits with populated aggregation results

A common case is an endpoint that only needs statistics and does not need documents. Set search-level `size: 0`:

```http
GET /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "createdAt": {
        "gte": "2025-01-01",
        "lt": "2026-01-01"
      }
    }
  },
  "aggs": {
    "revenue": {
      "sum": {
        "field": "amount"
      }
    },
    "orders_by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

The response still contains `aggregations.revenue` and `aggregations.orders_by_status`, while `hits.hits` is an empty array. This is an efficient pattern for dashboards or statistics APIs that do not display a document list.

`size: 0` does not mean no documents matched; it only requests not returning document hits. `hits.total` may still be computed if tracking is enabled, though if you only need aggregations you typically do not need exact total-hit counting.

## 7. `hits.total` and `track_total_hits` are not aggregations

Elasticsearch returns the total hit count in `hits.total`. Counting can be capped to improve performance:

```json
"track_total_hits": true
```

Requests an exact count of total documents matching the query. On large indices, this can increase cost.

You can set a threshold:

```json
"track_total_hits": 10000
```

When the threshold is exceeded, the response may return the `gte` relation, meaning the total is at least the reported value. `track_total_hits: false` does not request an exact total.

The `value_count` aggregation can also count the number of values for a field, but it is not the same as `hits.total`: a field can be missing or a multi-valued array, so value count counts indexed values rather than necessarily counting documents.

Example:

```json
"aggs": {
  "sku_values": {
    "value_count": {
      "field": "sku"
    }
  }
}
```

If each document has only one SKU, value count can match the number of documents with a SKU. However, if the field can be missing or contain multiple values, the two numbers differ.

## 8. Aggregations and hit pagination are independent

`from`/`size` control which hits are returned. They do not paginate aggregation buckets. For example:

```json
{
  "from": 20,
  "size": 10,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 5
      }
    }
  }
}
```

The request returns hits starting at offset 20, up to 10 documents, and up to 5 category buckets per the terms configuration. The two parts have independent sizes and rules.

If you need to paginate through all buckets, use a composite aggregation and `after_key`; do not use hit `from`/`size` to control buckets.

## 9. Aggregations in Spring Data Elasticsearch

Spring Data Elasticsearch executes aggregations via `ElasticsearchOperations` along with a query object, typically `NativeQuery` when flexible DSL is needed. Search results are represented by `SearchHits<T>`; document hits and aggregations are accessed separately.

### 9.1 Declaring an aggregation with NativeQuery

Example using the Elasticsearch Java API Client in Spring Data Elasticsearch 5.x:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t
        .field("category")
        .size(20)
    )
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("by_category", byCategory)
    .build();
```

`withMaxResults(0)` requests returning no document hits in API versions that support this setting. You can configure a page size of 0 according to your version's API. Method names and how zero hits are represented can vary across Spring Data versions; the Elasticsearch request goal remains search-level `size: 0`.

Execution:

```java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> searchHits = operations.search(query, Product.class);
```

`searchHits.getSearchHits()` contains the hit list (empty when size is 0). `searchHits.getTotalHits()` is the total number of matching documents according to total-hit tracking. Aggregations are retrieved via `searchHits.getAggregations()`.

### 9.2 Reading aggregations from SearchHits

The return type of `getAggregations()` is `AggregationsContainer<?>`. Spring Data Elasticsearch uses the implementation corresponding to the configured client; with the Elasticsearch Java Client, the common implementation is `ElasticsearchAggregations`.

Access skeleton example:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.AggregationsContainer;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;

SearchHits<Product> searchHits = operations.search(query, Product.class);

AggregationsContainer<?> container = searchHits.getAggregations();
if (container instanceof ElasticsearchAggregations aggregations) {
    // Retrieve the registered aggregations under the name "by_category".
    // The wrapper structure and specific Aggregate type depend on the client version.
    var aggregationMap = aggregations.aggregations();
}
```

This snippet illustrates the entry point at the Spring Data level. When retrieving specific buckets/metrics, you need to use the Elasticsearch Java Client's aggregate types and the registered aggregation name. Wrapper accessor structure can vary by version; check the Javadoc for your exact dependency to read `StringTermsAggregate`, `LongTermsAggregate`, `DoubleTermsAggregate`, or the corresponding bucket type. Do not force all aggregations into the same bucket type because terms on keyword and numeric fields can have different aggregate types.

### 9.3 Using Java Client to build metric aggregations

Example declaring `avg` and `sum`:

```java
Aggregation averagePrice = Aggregation.of(a -> a
    .avg(v -> v.field("price"))
);

Aggregation totalPrice = Aggregation.of(a -> a
    .sum(v -> v.field("price"))
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .withMaxResults(0)
    .withAggregation("average_price", averagePrice)
    .withAggregation("total_price", totalPrice)
    .build();
```

After execution, both metric results reside in the aggregation container, not inside the `Product` list.

### 9.4 Reading hits and aggregations together

A search page may need both a document list and category facets:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(PageRequest.of(0, 20))
    .withAggregation("by_category", byCategory)
    .build();

SearchHits<Product> result = operations.search(query, Product.class);

List<Product> products = result.getSearchHits().stream()
    .map(SearchHit::getContent)
    .toList();

long totalMatches = result.getTotalHits();
AggregationsContainer<?> aggregations = result.getAggregations();
```

`products` is used to render the list. `totalMatches` is used for result metadata if total-hit tracking is properly configured. `aggregations` is used to build facets or statistics. Do not try to convert aggregation buckets into `Product` instances because a bucket does not represent a document.

### 9.5 Do not treat `SearchHits` as if it only had hits

`SearchHits<T>` is the wrapper for the entire search response at the Spring Data level. Besides the list of `SearchHit<T>`, it also contains total hits, max score, aggregations, and other metadata depending on the version. When an endpoint only needs aggregations, you can still use `SearchHits<T>` while configuring zero hits; there is no need to load documents only to discard them.

## 10. Reading buckets and metrics: data type examples

An aggregation response is structured data of its own. Example terms aggregation:

```json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        { "key": "keyboard", "doc_count": 12 },
        { "key": "mouse", "doc_count": 8 }
      ]
    }
  }
}
```

Each bucket has a key and a document count. If it is a terms aggregation on a numeric field, the key may be returned as a number; if it is a date histogram, the bucket may have `key` as epoch millis and `key_as_string`.

Metric response:

```json
{
  "aggregations": {
    "average_price": {
      "value": 152.5
    },
    "price_stats": {
      "count": 20,
      "min": 20.0,
      "max": 500.0,
      "avg": 152.5,
      "sum": 3050.0
    }
  }
}
```

Simple metrics typically return `value`; stats metrics return multiple properties. Therefore, the code reading results must know which aggregations were declared and the expected result types. Avoid parsing every aggregation using a single fixed JSON structure.

## 11. Terms aggregations have limits and accuracy bounds

A terms aggregation typically returns top buckets by document count. If category has 10,000 distinct values but `size` is 10, only the top 10 buckets are returned. That does not mean only 10 categories exist.

The response may contain:

- `sum_other_doc_count`: the number of documents belonging to buckets not returned (according to aggregation semantics).
- `doc_count_error_upper_bound`: the upper bound on the bucket count error in certain distributed modes.

When you need to iterate over all buckets, consider a composite aggregation. When you need to count unique values, cardinality may fit, though it is approximate. Choose the aggregation type based on accuracy requirements and the number of distinct values.

### 11.1 Fields must be suitable for aggregations

Terms aggregations are typically used on `keyword`, numeric, or other aggregatable fields. `text` fields usually lack doc values and are not suitable for default terms aggregations. If you need facets by name, use a keyword multi-field such as `name.raw`.

Example mapping:

```json
"name": {
  "type": "text",
  "fields": {
    "raw": {
      "type": "keyword"
    }
  }
}
```

Aggregating by name uses:

```json
"terms": {
  "field": "name.raw"
}
```

Do not enable fielddata on text fields just to run aggregations without evaluating memory and cardinality; a keyword multi-field is usually the better design.

## 12. Aggregations do not automatically scope to the current page

A common mistake is thinking an aggregation only computes over documents on the current page. In reality, top-level aggregations usually run over all documents matching the query, not just `hits.hits` returned by `from`/`size`.

For example:

```json
{
  "from": 40,
  "size": 20,
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
```

Hits represent the third page of up to 20 ACTIVE products. The `by_category` aggregation aggregates all ACTIVE products matching the query, not just the 20 documents on that page.

If you want an aggregation on a specific subset, use a filter aggregation or an appropriate query scope. Do not try to use `from`/`size` to restrict aggregation scope.

## 13. When to use aggregations instead of fetching hits into Java?

Use aggregations when you need to:

- Count documents by category, status, brand, or time interval.
- Compute sum, average, min, max, or stats on numeric fields.
- Build facets for users to filter results.
- Build daily/monthly revenue charts.
- Estimate the number of unique values.
- Group and analyze data on the Elasticsearch side.

Use hits when you need to:

- Display the content of individual documents.
- Read business fields of individual records.
- Edit or process individual documents in the application.
- Export full data in batches.
- Retrieve highlights or metadata attached to each hit.

The two parts are often used together. For example, a product search page displays 20 hits while also showing category, brand, and price range facets.

Do not fetch millions of hits into Java just to count or compute an average. Conversely, do not use aggregations if the application needs the detailed content of each document.

## 14. Common mistakes

### 14.1 Thinking `size: 0` stops aggregations from running

`size: 0` only disables the document hits list. Aggregations are still computed and returned. This is the standard pattern for dashboards/facets that only need statistics.

### 14.2 Confusing search `size` with terms `size`

Search-level `size` is the number of document hits. `terms.size` is the number of buckets returned. They do not affect each other.

### 14.3 Thinking aggregations only compute over the current page

Top-level aggregations compute over the document set in the query scope, unrestricted by hits `from`/`size`. Use a filter aggregation if you need a separate scope.

### 14.4 Summing bucket `doc_count` and treating it as `hits.total`

A document can belong to multiple buckets or buckets may be capped. The sum of bucket counts does not necessarily equal total hits.

### 14.5 Using terms aggregation on a text field

Text fields usually lack doc values and are unsuitable for default terms aggregations. Use a keyword sub-field or an appropriate mapping design.

### 14.6 Thinking cardinality is an exact count

Cardinality is usually approximate. If absolute accuracy is required, choose another approach or evaluate the error margin for the business.

### 14.7 Thinking all terms buckets are returned

`terms.size` only returns a number of top buckets. Use a composite aggregation to paginate through large bucket sets.

### 14.8 Reading aggregations from the SearchHit list

Aggregations live in `SearchHits.getAggregations()`, not as entity fields or inside each regular `SearchHit`. Handle the aggregation container separately.

### 14.9 Using global aggregation and forgetting security scope

Global aggregation bypasses the top-level query scope. If the system has tenants or data access permissions, ensure security scope is still enforced at the appropriate layer.

### 14.10 Enabling exact track_total_hits when unnecessary

Counting exact total hits has a cost. If an endpoint only needs facets/metrics, set `size: 0` and only enable total tracking when the business requires it.

## 15. Inspecting aggregations in REST responses

When an aggregation looks wrong, check step by step:

1. Does the main query select the right set of documents?
2. Does the aggregation field have an appropriate mapping (`keyword`, numeric, date, etc.)?
3. Is `size` in terms limiting the number of returned buckets?
4. Is `post_filter`, a filter aggregation, or a global aggregation changing the scope?
5. Are there missing/null fields or mismatched data types?
6. Is a distributed terms aggregation reporting bucket errors?
7. Is cardinality being treated as an exact count?
8. Does the search response have `aggregations` while Java code mistakenly reads `hits`?

Check the mapping:

```http
GET /products/_mapping
```

Run an aggregation alone without hits:

```http
GET /products/_search
{
  "size": 0,
  "query": {
    "match_all": {}
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
```

Inspect `hits.total`, `hits.hits`, and `aggregations` to verify each section reflects its intended purpose.

## 16. Design principles

- Use hits when you need specific documents; use aggregations when you need statistics/grouping.
- Combine both in a single request when a search page needs both a list and facets.
- Set search-level `size: 0` when only aggregations are needed.
- Remember that hits `size` and terms aggregation `size` are two independent settings.
- Top-level aggregations typically compute over the entire document set matching the query, not just the current page of hits.
- Use `query`/`filter` to define the overall scope; use `post_filter` when you need to filter hits while keeping broader facets.
- Use filter aggregations for per-statistic scopes; use global aggregations only when you truly want to bypass the query scope.
- Choose appropriate field mappings for aggregations; prefer keyword sub-fields over fielddata on text.
- Understand top-bucket limits, terms error bounds, and cardinality approximation.
- Use composite aggregations to iterate over many buckets; do not use hits `search_after` for buckets.
- In Spring Data, read hits via `getSearchHits()` and aggregations via `getAggregations()`.
- Do not save an entity constructed from a projection/source-filtered response as if it were a full document.
- Only enable exact total-hit tracking when the application actually needs it.

## 17. Summary

The matched document list and aggregations are two independent parts of a search response. `hits.hits` contains specific documents returned according to `from`/`size`; `hits.total` describes the total documents matching the query under the tracking mode; `aggregations` contains buckets and metrics computed over the document set in the corresponding scope.

Aggregations are not restricted by the current page of hits. Search-level `size: 0` can suppress the document list while still returning full aggregations. Conversely, `terms.size` limits the number of returned buckets rather than documents. Query/filter, post_filter, filter aggregations, and global aggregations determine the document scope being aggregated. Terms, range, date histogram, metric, cardinality, and composite aggregations serve different statistical needs, each with constraints regarding mapping, bucket limits, or accuracy.

In Spring Data Elasticsearch, `ElasticsearchOperations.search(...)` returns `SearchHits<T>`; the document list is read via `getSearchHits()`, while aggregations are read separately via `getAggregations()`. Use hits to display/process documents and aggregations for statistics/facets. Separating these two purposes reduces data transferred to the application, leverages Elasticsearch's computation capabilities, and avoids confusing buckets with documents.

## References

- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-terms-aggregation.html)
- [Elasticsearch — Metric aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics.html)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-composite-aggregation.html)
- [Elasticsearch — Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
