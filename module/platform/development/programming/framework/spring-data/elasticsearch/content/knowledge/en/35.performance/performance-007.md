# Reducing Aggregation Cost, Total Counting, and Deep Pagination

## 1. Why can search be expensive even when returning only a few documents?

An Elasticsearch request may return 20 documents while having to process millions of documents matching the query. A small returned payload does not equate to a small amount of search work.

A single request often involves multiple tasks: finding matching documents, counting total matching documents, computing aggregations over the matching set, sorting results, skipping hits from previous pages, and reading and serializing data to return to the application.

For example, a product listing UI displays 20 products while also requesting the total product count, product count per category, average price per brand, total number of unique brands, and page 500 of the search results.

Even though the response contains only 20 products, Elasticsearch may still need to scan a huge document set to compute counts and aggregations, while retaining many intermediate hits to serve deep pagination.

To reduce cost, first determine what kind of results the application actually needs:

1. Does it need a list of documents or just a number?
2. Does it need an exact total or an estimate?
3. Does it need top buckets or must it iterate through all buckets?
4. Do users need to jump to an arbitrary page or only paginate forward?
5. Does it need a stable snapshot while data is changing?

Options such as the Count API, `track_total_hits`, composite aggregations, `search_after`, and Point in Time (PIT) address different requirements. There is no single parameter that makes every query type faster.

## 2. Distinguishing document counts, value counts, and bucket counts

Before optimizing, understand what the numbers in the response represent.

| Metric type | Question | Commonly used mechanism |
|---|---|---|
| Total hits | How many documents match the query? | `hits.total`, Count API |
| Value count | How many values exist for a field? | `value_count` aggregation |
| Bucket `doc_count` | How many documents belong to a bucket? | `terms`, `filters`, `date_histogram` |
| Cardinality | How many unique values exist? | `cardinality` aggregation |
| Sum or average | What is the sum/average of a field? | `sum`, `avg` aggregation |

These metrics are not interchangeable.

For example, given three documents:

~~~json
[
  {
    "id": "p-1",
    "tags": ["audio", "sale"]
  },
  {
    "id": "p-2",
    "tags": ["audio"]
  },
  {
    "id": "p-3",
    "tags": ["sale", "new"]
  }
]
~~~

There are three documents, yet five occurrences of tags. The cardinality of `tags` is three because there are three distinct values: `audio`, `sale`, `new`.

If you run a terms aggregation on `tags`, the sum of `doc_count` across buckets can exceed total hits because a single document can belong to multiple buckets.

When designing dashboards, name metrics accurately according to their meaning. For instance, `totalProducts`, `tagAssignments`, and `uniqueTags` are three distinct metrics.

## 3. When should you use the Count API?

If the application only needs to know how many documents match a condition, consider the Count API instead of the Search API.

Example using Search API solely to get a count:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 0,
  "track_total_hits": true
}
~~~

This request returns no hits, yet still uses the Search API to compute an exact hit total.

You can use the Count API instead:

~~~http
GET /products/_count
{
  "query": {
    "term": {
      "category": "audio"
    }
  }
}
~~~

The response looks like:

~~~json
{
  "count": 125430,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  }
}
~~~

The Count API returns only the number of matching documents. It does not return hit lists, sorts, highlights, or aggregations.

### Benefits of the Count API

- The request clearly expresses counting-only intent.
- No need to construct a hit response.
- No need to return document sources or sort values.
- Well suited for simple total-count statistics endpoints.

The Count API still has to determine matching documents across shards. It does not make a complex query or a huge dataset free. Query conditions, mappings, shard layout, and filters still affect cost.

### When not to use the Count API?

If the same request needs both a product list and aggregations, use the Search API to avoid sending multiple unnecessary independent requests.

If you only need top categories and do not need the document total, use the Search API with `size: 0` and aggregations, and consider disabling total hit tracking.

## 4. Spring Data Elasticsearch: counting with ElasticsearchOperations

Spring Data Elasticsearch provides `count` methods on `ElasticsearchOperations`.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public long countAudioProducts() {
        CriteriaQuery query = new CriteriaQuery(
            Criteria.where("category").is("audio")
        );

        return operations.count(query, Product.class);
    }
}
~~~

`operations.count(query, Product.class)` executes a count operation using the query and entity mapping. When only a number is needed, this API is cleaner than running a search and reading `SearchHits.getTotalHits()`.

More complex queries can be used:

~~~java
Criteria criteria = new Criteria("category").is("audio")
    .and("active").is(true);

CriteriaQuery query = new CriteriaQuery(criteria);

long count = operations.count(query, Product.class);
~~~

For queries that do not fit the Criteria API, you can use `StringQuery` or another query implementation supported by Spring Data.

Do not issue a separate Count API call for every widget on a dashboard if multiple metrics can be computed in one aggregation request. Consider combining metrics that share the same input document set.

## 5. track_total_hits and the cost of total counting in Search API

The Search API can return the total matching document count in `hits.total`. Tracking the exact total can increase query cost.

The `track_total_hits` parameter controls counting precision:

| Value | Behavior |
|---|---|
| `true` | Tracks exact total hits |
| `false` | Does not compute total hits |
| Integer `N` | Tracks accurately up to threshold N; beyond the threshold, the result may only be a lower bound |

By default, Elasticsearch tracks accurately up to 10,000 hits. Above that threshold, the response can have relation `gte` instead of `eq`.

Example:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

`gte` means there are at least 10,000 hits; the number is not an exact total.

### Disable tracking when total is not needed

Example request needing only the result list:

~~~http
GET /products/_search
{
  "track_total_hits": false,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 20,
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

The application still receives matching hits without asking Elasticsearch to compute total hits.

This is useful for autocomplete, search pages that only need to know if there is a next page, feeds or timelines, cursor-based APIs, and queries where the total count is never displayed.

### Only need totals up to a threshold

For example, the UI only displays `10,000+ results` and does not need to know whether the exact count is 12,345 or 1,200,000:

~~~http
GET /products/_search
{
  "track_total_hits": 10000,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "size": 20
}
~~~

When hits do not exceed the threshold, Elasticsearch can return the exact total. When exceeded, the application should inspect `relation` to know it is only a lower bound.

Do not read only `value` and always display it as an exact count.

### When is exact counting mandatory?

Some business workflows require exact totals, such as reconciliation reports or user-committed statistics. In those cases, use `track_total_hits: true` or the Count API.

Remember that exact counting on large datasets has a cost. If a screen requires exact totals every time a user changes a filter, consider caching, pre-aggregation, or a dedicated statistics read model.

## 6. size: 0 does not make aggregations free

When only aggregations are needed, you can set `size: 0`:

~~~http
GET /products/_search
{
  "size": 0,
  "track_total_hits": false,
  "query": {
    "term": {
      "active": true
    }
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
~~~

`size: 0` means no document hits are returned. It eliminates hit fetch and source serialization cost, yet Elasticsearch still has to find matching documents and compute the aggregations.

If an aggregation spans millions of distinct values, `size: 0` does not eliminate bucket creation overhead.

When only aggregations are required, combine `size: 0`, `track_total_hits: false` if an exact total is unnecessary, query filters to narrow the dataset, and aggregations suited to the field cardinality and display requirements.

Do not confuse search hit `size` with terms aggregation `size`. They control two different parts of the response.

## 7. Reducing cost by filtering before aggregating

Aggregations normally compute over the document set matching the query. Therefore, narrowing the input set is one of the most direct ways to lower cost.

For example, a dashboard summarizing only active products within a time window:

~~~http
GET /products/_search
{
  "size": 0,
  "track_total_hits": false,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2027-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
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
~~~

Conditions inside `bool.filter` do not compute relevance scores. They are well suited for status, tenant, date, and permission constraints.

If your application has a tenant ID, apply the tenant filter before aggregating. Do not let an aggregation scan all tenants' data and then filter the results in Java.

### Query filter and filter aggregation differ

The top-level query limits the document set used across the entire search, including hits and aggregations.

A `filter` aggregation creates a sub-scope inside the aggregation tree:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-7"
    }
  },
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "active": true
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
  }
}
~~~

In this example, all aggregations see only tenant 7's documents; the `active_products` aggregation narrows further to active products.

If every aggregation shares the same condition, a top-level query is usually clearer and more efficient than wrapping each aggregation in an identical `filter` aggregation.

### Note on post_filter

`post_filter` filters hits only after aggregations have been computed. If you put a condition there thinking it reduces aggregation input, results will still summarize the broader set.

For instance, a faceted search UI may intentionally use `post_filter` to keep facet counts unchanged when a user selects a facet. That is intentional behavior, not an optimization for reducing aggregation cost.

## 8. Choosing the right field type for aggregations

Aggregations typically read field values via doc values. Consequently, mappings directly affect performance.

Commonly suitable field types:

- `keyword` for categories, codes, statuses, and normalized names.
- `long`, `integer`, `double` for numbers.
- `date` for time-based histograms.
- `boolean` for status flags.

Avoid running terms aggregations directly on analyzed `text` fields without a clear reason. Usually declare a multi-field:

~~~json
{
  "mappings": {
    "properties": {
      "brand": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Aggregate on `brand.keyword`:

~~~json
{
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "size": 20
      }
    }
  }
}
~~~

`text` fields store analyzed tokens for full-text search. `keyword` fields store intact values suitable for grouping, sorting, and terms aggregations.

Enabling `fielddata` on `text` can consume large amounts of heap. Do so only after fully understanding the cost and with a specific justification; in most cases, a `keyword` multi-field is the right choice.

## 9. Terms aggregation: limiting returned buckets

Terms aggregations are commonly used to retrieve top categories, brands, or statuses.

Example:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand.keyword",
        "size": 10
      }
    }
  }
}
~~~

`size: 10` caps returned buckets at 10. If the field has millions of distinct values, the request may still examine many values to find the top 10, but the response and reduce phase are much smaller than requesting all buckets.

Do not set an enormous `size` just to retrieve every value. If you need to iterate through the complete list of buckets, look at `composite` aggregations.

### shard_size and accuracy

Terms aggregations execute in a distributed manner. Each shard returns a set of candidate buckets to the coordinating node to reduce into global top buckets.

`shard_size` controls how many candidate buckets each shard sends. Larger values can improve top-term accuracy while increasing shard and coordinating-node memory, inter-node data transfer, reduce work, and intermediate response sizes.

Example:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand.keyword",
        "size": 10,
        "shard_size": 50,
        "show_term_doc_count_error": true
      }
    }
  }
}
~~~

`show_term_doc_count_error` returns error bounds on `doc_count` in cases where Elasticsearch can estimate the bound.

The response can include `doc_count_error_upper_bound`, an upper bound on counting error, and `sum_other_doc_count`, the document count belonging to unreturned buckets, according to aggregation semantics.

This is helpful when top terms are used in reporting. Do not assume distributed terms aggregation `doc_count` is always 100% exact under every configuration.

### Avoid ascending _count sort if exact results are required

Sorting terms by ascending count (`_count: asc`) can yield inaccurate results in multi-shard environments. If you need the least popular terms, consider alternatives such as using `composite` to iterate buckets and processing in the application layer, or maintaining business-specific statistics.

## 10. Composite aggregation for iterating all buckets

If you need all buckets of a high-cardinality field, a `terms` aggregation with a huge `size` is not the right approach.

Composite aggregations allow paginating buckets using an `after` key.

Example:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

The response returns buckets along with an `after_key` if more data remains. The next request passes `after`:

~~~http
GET /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "composite": {
        "size": 500,
        "after": {
          "brand": "Brand Z"
        },
        "sources": [
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

The `after` value must come from the previous response's `after_key`. Do not construct it manually from the last bucket when Elasticsearch already returns `after_key`.

Execution flow:

~~~text
Request composite page 1
          |
          v
   500 buckets + after_key
          |
          v
Request page 2 with after_key
          |
          v
   500 buckets + after_key
          |
          v
         ...
          |
          v
     No more buckets
~~~

Composite aggregations fit exporting or sequentially iterating all buckets. They are not a tool for finding the top 10 most frequent buckets; use `terms` aggregation for top-N.

If data changes while paginating buckets, results can shift between requests. When a stable snapshot is needed, evaluate pairing with PIT according to your Elasticsearch version and aggregation capabilities.

## 11. Cardinality aggregation is approximate

When you need to count unique values, such as unique customers, you can use a `cardinality` aggregation:

~~~http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "unique_customers": {
      "cardinality": {
        "field": "customerId"
      }
    }
  }
}
~~~

Cardinality uses the HyperLogLog++ algorithm to estimate distinct value counts. It typically uses far less memory than building a bucket per value, though the result is an approximation and has some error margin.

Do not use `cardinality` if business logic strictly requires an exact number.

### precision_threshold

You can tune the accuracy threshold:

~~~json
{
  "aggs": {
    "unique_customers": {
      "cardinality": {
        "field": "customerId",
        "precision_threshold": 10000
      }
    }
  }
}
~~~

Higher `precision_threshold` values generally improve accuracy at low and medium cardinalities at the cost of higher memory usage. Elasticsearch supports up to 40,000; the default is 3,000.

This is a precision tuning threshold, not a hard limit on unique values. Cardinalities above the threshold are still estimated.

If an exact distinct count is required over a very large dataset, consider a dedicated summary table or read model, batch pre-computation, a normalized unique key counted appropriately, or accepting higher cost if the business genuinely needs exactness.

Do not replace `cardinality` with a `terms` aggregation of huge `size` when the goal is only a unique count.

## 12. Deeply nested aggregations and bucket explosion

An aggregation tree can cause bucket counts to grow explosively.

Example:

~~~json
{
  "aggs": {
    "by_country": {
      "terms": {
        "field": "country",
        "size": 100
      },
      "aggs": {
        "by_city": {
          "terms": {
            "field": "city.keyword",
            "size": 100
          },
          "aggs": {
            "by_category": {
              "terms": {
                "field": "category",
                "size": 50
              }
            }
          }
        }
      }
    }
  }
}
~~~

In the worst case, this tree can produce hundreds of thousands of buckets. Each bucket can carry its own sub-aggregations. Memory and reduce cost scale with bucket count and depth.

Ways to reduce this:

- Reduce `size` at each level.
- Use filters to narrow scope.
- Compute sub-aggregations only on buckets that genuinely need them.
- Use `composite` when you need to iterate all combinations.
- Avoid nesting multiple high-cardinality `terms` aggregations.
- Do not send duplicate aggregations over the same field if results can be reused.

Elasticsearch enforces `search.max_buckets` to protect the cluster from responses with too many buckets. Raising the limit just to make a request run can increase the risk of exhausting heap. Reduce bucket counts or change the strategy first.

## 13. value_count, sum, avg, min, and max

If you only need a metric over a field, use the corresponding metric aggregation instead of creating buckets.

Example:

~~~http
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "total_amount": {
      "sum": {
        "field": "amount"
      }
    },
    "average_amount": {
      "avg": {
        "field": "amount"
      }
    },
    "minimum_amount": {
      "min": {
        "field": "amount"
      }
    },
    "maximum_amount": {
      "max": {
        "field": "amount"
      }
    },
    "amount_values": {
      "value_count": {
        "field": "amount"
      }
    }
  }
}
~~~

Meaning:

- `sum`: sum of values.
- `avg`: average.
- `min`: minimum value.
- `max`: maximum value.
- `value_count`: number of values in the field, not always the number of documents.

If a field is multi-valued, one document can contribute multiple values to `value_count`. If you need to count documents where a field exists, clarify semantics and use an appropriate document-counting approach.

## 14. Nested aggregations and the meaning of doc_count

With `nested` mapping, a parent document can contain multiple nested documents. A nested aggregation counts nested documents within the nested path scope, not necessarily parent documents.

For example, an order has three line items. A nested aggregation on `items` can report `doc_count = 3`, even though there is only one order.

If you need to step back up to count parent documents, use a `reverse_nested` aggregation.

~~~json
{
  "aggs": {
    "items": {
      "nested": {
        "path": "items"
      },
      "aggs": {
        "by_sku": {
          "terms": {
            "field": "items.sku"
          },
          "aggs": {
            "parent_orders": {
              "reverse_nested": {}
            }
          }
        }
      }
    }
  }
}
~~~

When reading dashboards, verify whether an aggregation counts root documents, nested documents, or field values. Wrong semantics can yield numbers that look plausible yet misrepresent business reality.

## 15. Reducing script and runtime field cost in aggregations

Aggregating on a field that already has doc values is usually more efficient than evaluating a complex expression for every document.

Example runtime field:

~~~json
{
  "runtime_mappings": {
    "netAmount": {
      "type": "double",
      "script": {
        "source": "emit(doc['grossAmount'].value - doc['discount'].value)"
      }
    }
  },
  "aggs": {
    "average_net_amount": {
      "avg": {
        "field": "netAmount"
      }
    }
  }
}
~~~

Runtime fields are convenient when logic must change without reindexing. However, if the aggregation runs frequently over millions of documents, script evaluation can become a significant cost.

If the computed value is stable and used often:

1. Compute the value in the application or an ingest pipeline.
2. Store it in an appropriate numeric/keyword field.
3. Index the field so it has doc values.
4. Run metric or bucket aggregations directly on it.

This is a trade-off between schema flexibility and query-time cost. Not every runtime field is slow, but measure on real data before deploying in high-frequency dashboards.

## 16. Global ordinals and terms aggregations

Terms aggregations on `keyword` fields often leverage global ordinals to group values. Global ordinals map terms to shard-wide ordinals, though building them can consume memory and time after refreshes.

For frequently aggregated fields, consider:

~~~json
{
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "eager_global_ordinals": true
      }
    }
  }
}
~~~

`eager_global_ordinals: true` builds global ordinals during refresh instead of waiting for the first query that uses them. This can lower first-query latency while shifting the cost to refresh and increasing resource consumption.

It does not eliminate the cost of building ordinals. If data changes continuously, eager global ordinals can make refreshes more expensive.

Enable it only when the field's cardinality and aggregation frequency fit, query latency matters more than refresh latency, heap and refresh load have been measured, and repeated aggregations target that field.

## 17. Shallow pagination with from and size

The familiar pagination approach:

~~~http
GET /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

Next page:

~~~http
GET /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    }
  ]
}
~~~

This works well for the first pages. However, `from` and `size` scale in cost with depth.

When requesting `from: 9900` and `size: 100`, each shard may have to collect and retain far more hits than the final returned slice. The coordinating node also needs to reduce those intermediate results.

The total hits considered grow according to:

\[
from + size
\]

Example:

| Page | from | size | Total hits to consider |
|---:|---:|---:|---:|
| 1 | 0 | 20 | 20 |
| 10 | 180 | 20 | 200 |
| 100 | 1,980 | 20 | 2,000 |
| 500 | 9,980 | 20 | 10,000 |
| 1,000 | 19,980 | 20 | 20,000 |

The deeper the page, the higher the cost.

### index.max_result_window

Elasticsearch limits `from + size` to 10,000 by default via the `index.max_result_window` setting.

If a request exceeds the limit, Elasticsearch returns an error rather than allowing uncontrolled deep pagination.

Do not raise the limit to hundreds of thousands just to support a "Last page" button. Doing so can spike cluster memory and CPU. Consider cursor-based pagination or a dedicated export flow.

## 18. Why does deep pagination easily duplicate or miss documents?

Even if `max_result_window` is increased, offset pagination runs into issues when data changes between two requests.

Example:

1. Page 1 request returns 20 documents.
2. A new document is inserted at the top of the list.
3. Page 2 request uses `from: 20`.
4. Document positions have shifted.
5. The user may see duplicate or skipped documents.

If the sort field is not unique, ordering among documents sharing the same sort value can also be unstable.

Therefore, pagination requires two things: a traversal mechanism that avoids skipping massive numbers of prior results, and deterministic ordering within the traversal scope.

`search_after` and PIT are designed to address these issues.

## 19. Using search_after instead of from/size

`search_after` uses the sort values of the last hit from the previous page to request the next page.

Example first request:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ]
}
~~~

Suppose the last returned hit has sort values:

~~~json
[
  "2026-10-15T09:30:00.000Z",
  "product-120"
]
~~~

The next request passes that exact sort values array:

~~~http
GET /products/_search
{
  "size": 20,
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ],
  "search_after": [
    "2026-10-15T09:30:00.000Z",
    "product-120"
  ]
}
~~~

Elasticsearch continues after the last hit's position. It does not need to collect and discard all hits from earlier pages.

### Sort must have a tie-breaker

If multiple documents share the same `createdAt`, sorting only by timestamp may not yield a unique order.

Add a unique field with doc values, such as a `keyword` field `productSortId`:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "productSortId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Do not rely arbitrarily on `_id` as a sort field because `_id` is not designed for doc-values sorting like a regular field. Copy the ID into a dedicated `keyword` field at index time.

Sort order, query, and related parameters must remain unchanged across pages. `search_after` is not an offset and cannot be combined with `from` to jump to an arbitrary page.

## 20. Point in Time (PIT) to preserve a stable snapshot

`search_after` alone does not freeze a data snapshot. If documents are added, deleted, or updated while a user paginates, result order and membership can change.

Point in Time (PIT) creates a consistent view of the index for a period of time. Combining PIT with `search_after` is appropriate for deep pagination needing consistency.

### Opening a PIT

~~~http
POST /products/_pit?keep_alive=2m
~~~

The response returns a PIT ID.

### Searching the first page within a PIT

~~~http
GET /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID_FROM_RESPONSE",
    "keep_alive": "2m"
  },
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ]
}
~~~

### Searching the next page

Use the sort values of the last hit from the previous page:

~~~http
GET /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID_FROM_RESPONSE",
    "keep_alive": "2m"
  },
  "query": {
    "term": {
      "category": "audio"
    }
  },
  "sort": [
    {
      "createdAt": "desc"
    },
    {
      "productSortId": "asc"
    }
  ],
  "search_after": [
    "2026-10-15T09:30:00.000Z",
    "product-120"
  ]
}
~~~

In some versions or scenarios, the response may return a new PIT ID. The application must use the latest returned ID for the subsequent request.

PIT `keep_alive` is how long Elasticsearch retains the search context from the request, not a fixed total lifetime regardless of activity. Each subsequent request can extend the PIT retention time.

### Closing the PIT

When the user finishes browsing or the export completes:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Closing the PIT frees search context resources promptly.

### PIT and tie-breakers

When using PIT, Elasticsearch can append `_shard_doc` as an internal tie-breaker if the sort lacks its own tie-breaker. The application must still preserve all returned sort values and send them back verbatim in `search_after`.

An explicit unique `keyword` field is still useful when business-level ordering control is needed. `_shard_doc` suits snapshot traversal, but its order is not a stable business order across different PIT sessions.

## 21. When should you use Scroll?

The Scroll API is designed for retrieving large result sets in batches, such as exporting millions of documents, data migrations, batch processing, reindexing, or offline processing.

Scroll retains a search context for a duration and returns a scroll ID for fetching the next batch.

Example opening a scroll:

~~~http
GET /products/_search?scroll=1m
{
  "size": 1000,
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

Fetching the next batch:

~~~http
POST /_search/scroll
{
  "scroll": "1m",
  "scroll_id": "SCROLL_ID_FROM_RESPONSE"
}
~~~

When finished, clear the context:

~~~http
DELETE /_search/scroll
{
  "scroll_id": ["SCROLL_ID_FROM_RESPONSE"]
}
~~~

Scroll suits large sequential batch processing, but is not a good fit for interactive user pagination. For UIs stepping through pages, `search_after` + PIT is usually more suitable.

Do not keep scroll contexts open longer than necessary. A large number of open scrolls can consume cluster resources.

## 22. Choosing a pagination strategy

| Need | Choice |
|---|---|
| First page and a few subsequent pages | `from` + `size` |
| Users need to jump to an arbitrary page number | `from` + `size`, within reasonable limits |
| Traversing tens of thousands or millions of hits sequentially | `search_after` |
| Stable traversal while data may change | PIT + `search_after` |
| Large data export/batch scan | Scroll or PIT + `search_after` |
| Retrieving all aggregation buckets | Composite aggregation with `after_key` |

Do not pick `search_after` solely because it is newer. If a UI only has 5 result pages, `from` + `size` is simpler and appropriate.

If a UI has a "Last page" button or allows entering very deep page numbers, reconsider the product design. Cursor-based pagination does not support jumping directly to page 50,000 without traversing prior pages to obtain cursors.

## 23. Spring Data Elasticsearch: shallow pagination with Pageable

Spring Data Elasticsearch supports `Pageable` to express page number and page size.

Example:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("category")
            .value("audio")
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`PageRequest.of(0, 20)` requests the first page with 20 results. The next page can use `PageRequest.of(1, 20)`.

This fits shallow pagination. As page number grows, offset increases and cost grows just like Elasticsearch's `from` + `size`.

Do not raise `index.max_result_window` just to make `PageRequest.of(10000, 20)` work. Use cursor-based pagination if users need deep traversal.

## 24. Spring Data Elasticsearch: reducing total hits cost

With `NativeQuery`, you can configure total hit tracking. Current Spring Data Elasticsearch builder APIs provide `withTrackTotalHits(...)`:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .matchAll(m -> m)
    )
    .withPageable(PageRequest.of(0, 20))
    .withTrackTotalHits(false)
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

When an exact total is not needed, disabling tracking saves Elasticsearch unnecessary total-hit counting work.

If the application converts `SearchHits` into a `Page`, check the semantics the API exposes. `Page` typically exposes total elements and total pages; if total hits is only a lower bound or untracked, do not present it as an exact total.

### Page, Slice, and SearchHits

| Result type | Information | When suitable |
|---|---|---|
| `Page<T>` | Content, pageable, total elements, and total pages | UI truly needs exact totals |
| `Slice<T>` | Content and whether a next page exists | UI only needs Next/Previous |
| `SearchHits<T>` | SearchHit metadata, total hits, sort values, and aggregation container | Need full control over Elasticsearch results |
| `List<T>` | Entity content only | API needs no pagination metadata |

Direct `Slice` support depends on repository query types and Spring Data version. When cursor pagination is needed, a custom service returning a DTO with the hit list and next cursor is usually clearer than forcing cursors into `Page`.

### Avoid counting totals when only checking if a next page exists

A common technique is fetching `pageSize + 1` hits:

1. Request 21 hits when page size is 20.
2. If 21 hits are returned, a next page exists.
3. Return the first 20 hits.
4. No exact total hits needed.

With cursor pagination, you can also request one extra hit to determine `hasNext`. This lowers cost for feeds or infinite-scroll APIs.

## 25. Spring Data Elasticsearch: reading aggregations from SearchHits

Spring Data Elasticsearch can send aggregations via `NativeQuery` and return aggregation metadata inside `SearchHits`.

Example building an aggregation query using the Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.NativeQuery;

Aggregation byCategory = Aggregation.of(a -> a
    .terms(t -> t
        .field("category")
        .size(20)
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .term(t -> t
            .field("active")
            .value(true)
        )
    )
    .withMaxResults(0)
    .withTrackTotalHits(false)
    .withAggregation("by_category", byCategory)
    .build();

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

`withMaxResults(0)` requests no document hits; `withAggregation` attaches the aggregation to the request. Exact builder APIs must match the Elasticsearch Java API Client version used by Spring Data.

Aggregation results are accessed via `SearchHits.getAggregations()`. Container types and bucket retrieval depend on the specific aggregation and client version. Convert aggregation responses into application DTOs at the service boundary, avoiding leaking low-level client types into controllers.

If only aggregations are needed, no entity hits are required. Use a query returning `size: 0` and keep only the aggregation response.

## 26. Spring Data Elasticsearch: using Count API instead of Page when data is not needed

An anti-pattern is fetching a `Page` solely to get the total count:

~~~java
Page<Product> page = repository.findByCategory(
    "audio",
    PageRequest.of(0, 1)
);

long total = page.getTotalElements();
~~~

If the application only needs the number, this request still builds a paginated result and may involve fetching an unnecessary hit.

Use the Count API through operations:

~~~java
long total = operations.count(
    new CriteriaQuery(Criteria.where("category").is("audio")),
    Product.class
);
~~~

If both count and aggregations are needed, you can use a single search request with `size: 0`, considering whether exact total hits are required. A combined request can save round trips; a separate Count API call is simpler when only counting.

Do not call the Count API after every write just to inspect total document counts if the application does not need the figure immediately. Consider caching or event-driven counter updates if the metric is read frequently.

## 27. Creating a cursor DTO for Spring Data APIs

When using `search_after`, the API should return an opaque cursor for the client to pass back on the next request.

Example DTO:

~~~java
import java.util.List;

public record CursorPage<T>(
    List<T> content,
    String nextCursor,
    boolean hasNext
) {
}
~~~

The cursor can encode the PIT ID, sort values of the last hit, a query/filter fingerprint, expiration timestamp, and cursor format version.

Do not allow clients to edit sort values or PIT IDs freely. Serialize the cursor in a versioned format and sign or integrity-protect it if clients are untrusted.

Example response:

~~~json
{
  "content": [
    {
      "id": "p-120",
      "name": "Wireless Headphones"
    }
  ],
  "nextCursor": "eyJwaXQiOi4uLiwic29ydCI6Wy4uLl19",
  "hasNext": true
}
~~~

On the next request, the backend decodes the cursor, verifies the query/filter shares the same semantics, and sends `search_after` and the PIT ID. When results end, the backend closes the PIT and returns `hasNext: false`.

Do not put an unbounded-lifetime cursor into public URLs. PITs are time-bound resources; cursors should expire accordingly.

## 28. Choosing batch size and page size

Larger page sizes are not always better.

Increasing `size` causes:

- Elasticsearch to collect more hits.
- Larger responses.
- Higher network and JSON serialization cost.
- Higher application memory usage to retain results.
- Longer-lived PIT or scroll contexts if clients process slowly.

For UIs, a page size of 20–100 is often enough in many cases, though it must be measured against document payload and complexity.

For exports, batch sizes can be larger while balancing throughput against memory. Test multiple sizes on real data, tracking heap, latency, shard count, and response size.

Do not use a single batch size for both UI and export. Those two flows have different requirements.

## 29. Index sorting and sort fields

Sorting can be expensive, especially when sorting on unsuitable fields or large hit sets.

Key principles:

- Sort on fields with doc values.
- Avoid sorting directly on `text`.
- Use `keyword` multi-fields for strings.
- Add a unique tie-breaker when using `search_after`.
- Keep sort field data types consistent across documents.
- Avoid script sorts when values can be materialized.
- Consider index sorting when workloads rely on a fixed, heavily used sort order.

Example mapping:

~~~json
{
  "settings": {
    "index": {
      "sort.field": ["createdAt", "productSortId"],
      "sort.order": ["desc", "asc"]
    }
  },
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "productSortId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Index sorting orders documents within segments at index time. It can help compatible sorted queries, at the expense of higher indexing cost and configuration constraints. Index sorting cannot be changed arbitrarily on an existing index; it must be designed at index creation or via a new index and reindex.

Enable it only when the actual query workload matches the index sort order.

## 30. Query cache and aggregations

Elasticsearch provides a query cache for certain filter contexts. The query cache can accelerate repeated filters on the same segments, though not every query is cached.

Do not expect an aggregation request to be cached automatically simply because it resembles an earlier request. Aggregation results depend on query, segments, and how requests execute.

Principles:

- Place eligible filter conditions in filter context.
- Keep queries stable if you want to benefit from caching.
- Avoid creating thousands of query variants due to minor parameter differences.
- Monitor cache hits/misses rather than assuming them.
- Do not rely on caching to mask an aggregation tree suffering from bucket explosion.

If a dashboard needs the exact same metrics repeatedly, application-layer caching or materialized statistics may fit better.

## 31. Using the Profile API and measuring performance

Before optimizing, measure where time is actually spent.

The Profile API helps inspect query and aggregation execution times across shards:

~~~http
GET /products/_search
{
  "profile": true,
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "size": 20
      }
    }
  }
}
~~~

Profiling adds overhead and produces sizable responses. Enable it only for diagnostic requests, never by default on production traffic.

Measure separately: query latency, aggregation latency, exact total hit tracking, sort latency, response size, CPU and heap on shards/coordinating nodes, bucket counts and cardinality, and shards queried.

When testing performance, use production-like datasets and concurrency. A query that runs fast on an index of a few thousand documents can slow drastically when cardinality reaches millions.

## 32. Common mistakes

**Using Search API only to count.** If neither hits nor aggregations are needed, the Count API expresses intent better.

**Always enabling track_total_hits: true.** Exact counts have a cost. Enable only when the UI or business logic needs exact totals.

**Treating gte as an exact total.** Check the `relation` of `hits.total` before displaying it.

**Thinking size: 0 makes aggregations free.** It only omits hits from the response; aggregations still process matching documents.

**Using terms aggregation with massive size.** When all buckets are needed, use `composite` aggregation and `after_key`.

**Increasing shard_size without measuring.** It can improve accuracy while increasing memory, network, and reduce costs.

**Treating cardinality as an exact count.** Cardinality is an estimate; raising `precision_threshold` only trades off memory for accuracy.

**Using fielddata on text for aggregations.** Usually use a `keyword` multi-field with doc values instead.

**Building overly deep aggregation trees.** Bucket explosion raises memory consumption and can exceed `search.max_buckets`.

**Confusing doc_count with parent document count.** Nested aggregations count nested documents; use `reverse_nested` to step back to parents.

**Using post_filter to reduce aggregation input.** `post_filter` does not filter aggregations; use top-level queries or `filter` aggregations as appropriate.

**Deep pagination with from and size.** Cost scales with `from + size` and is bounded by `index.max_result_window`.

**Raising max_result_window to support very deep pages.** This increases memory and CPU usage. Use `search_after` for sequential traversal.

**Using search_after with a non-unique sort.** Hits sharing sort values can produce unstable results. Add a tie-breaker.

**Using search_after without preserving a snapshot while data changes.** Pair with PIT if traversing a consistent view.

**Failing to close PIT or scroll.** Search contexts hold resources. Close them when done and set sensible `keep_alive` values.

**Using Scroll for UI pagination.** Scroll fits batch scans/exports; `search_after` + PIT fits cursor pagination.

**Using Page solely to determine hasNext.** If total pages are unnecessary, fetch one extra hit or use a `Slice`/cursor response.

**Using Page with total hits disabled while trusting totalPages.** Total pages require reliable total counts. Align API contracts with returned data.

**Not keeping sort values in the cursor.** `search_after` requires the exact sort values of the previous page's last hit.

**Using index sorting without evaluating ingest cost.** Index sorting helps matching sort workloads, but raises write cost and must be designed at index creation.

## 33. Process for choosing optimizations

Apply this sequence per endpoint:

1. Determine whether the endpoint needs hits, counts, aggregations, or all three.
2. If only total document count is needed, use the Count API.
3. If search is needed without totals, disable `track_total_hits`.
4. If totals are needed only up to a threshold, use an integer threshold and check `relation`.
5. If only aggregations are needed, set `size: 0`.
6. Narrow the document set using queries/filters before aggregating.
7. Use `keyword`/numeric/`date` fields with doc values.
8. Use `terms` for top-N buckets; use `composite` to iterate all buckets.
9. Use `cardinality` when approximate distinct counts are acceptable.
10. Limit bucket counts and aggregation tree depth.
11. Use `from`/`size` for shallow pagination.
12. Use `search_after` for sequential deep traversal.
13. Pair with PIT when a stable snapshot is required.
14. Use Scroll for large batch exports or scans.
15. In Spring Data, choose `count`, `NativeQuery`, `SearchHits`, `Page`, or cursor DTOs matching the contract.
16. Measure Profile API, latency, heap, response size, and shard load before and after changes.

## Conclusion

Reducing aggregation, total-counting, and deep-pagination costs starts with distinguishing the exact result types the application needs. The Count API fits when only document counts are needed; `track_total_hits` lets you skip or cap total counting in the Search API. `size: 0` eliminates hit return overhead without eliminating aggregation cost.

For aggregations, narrow input document sets, use fields with doc values, cap bucket counts, and pick the right aggregation type. `terms` fits top-N, `composite` fits iterating all buckets, and `cardinality` provides approximate distinct counts. For pagination, `from` and `size` fit early pages; `search_after` avoids skipping prior hits, and PIT preserves a stable snapshot while data changes. Scroll targets batch scans/exports.

In Spring Data Elasticsearch, `ElasticsearchOperations.count(...)` serves count-only needs; `NativeQuery` configures total hits, aggregations, and pagination; `SearchHits` exposes result metadata. Use `Page` only when total page counts are truly required. When the UI only moves forward, use a cursor or slice-style result to avoid unnecessary exact counting.

## References

- [Elasticsearch — Count API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-count)
- [Elasticsearch — Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch — Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch — Cardinality aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-metrics-cardinality-aggregation)
- [Elasticsearch — Search aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
- [Elasticsearch — Point in Time API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-open-point-in-time)
- [Elasticsearch — Scroll search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch — Index sorting](https://www.elastic.co/docs/reference/elasticsearch/index-settings/sorting)
- [Elasticsearch — Profile search requests](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-profile)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Query.html)
