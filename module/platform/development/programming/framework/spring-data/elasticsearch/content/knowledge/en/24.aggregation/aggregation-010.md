# Composite Aggregation and Bucket Pagination

Elasticsearch's composite aggregation groups documents across one or more value sources and reads the resulting buckets page by page. It is especially useful when you need to iterate through all data groups—such as every category, every category–status pair, or every date–region combination—whereas a `terms` aggregation primarily returns only a top subset of buckets.

The core mechanism of composite aggregation is a **pagination cursor**. The initial request declares `sources` and `size`. The response returns buckets along with an `after_key` if another page remains. The next request passes `after` equal to the received `after_key` to continue. The application repeats until no buckets remain.

Composite aggregation does not use `from`/`size` like document pagination. It paginates over buckets produced by the aggregation, so you must manage the cursor separately and keep the order and structure of sources identical across requests.

## 1. Why is Composite aggregation needed?

Suppose the `sales` index contains millions of orders. A report needs total revenue across all product categories. You could use a `terms` aggregation:

```json
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

This request returns at most 20 buckets per `terms.size`. That works for a dashboard showing the top 20 categories, yet it is not a pagination mechanism for sequentially fetching every category.

If thousands or hundreds of thousands of combinations must be read, setting `terms.size` to a huge number can spike memory usage and cluster load. Composite aggregation is designed to traverse buckets page by page, using `after_key` to resume from the previous position.

### When to use Composite aggregation?

- Exporting all grouped results to CSV, a data warehouse, or a reporting system.
- Iterating through all value combinations across multiple fields, such as `category` + `status`.
- Computing statistics per day and per tenant.
- Synchronizing high-cardinality facets in batches.
- Offline group processing where returning all buckets in one response is impossible.

### When to use `terms` aggregation?

- Needing the top N buckets by document count or metric.
- Bucket counts are small and bounded.
- The UI displays only the few most popular facets.
- Cursor-based traversal of all buckets is not required.

Composite aggregation returns buckets ordered by keys determined by the sources rather than automatically picking top buckets by `doc_count`. If the goal is top best-selling categories, a `terms` aggregation with appropriate ordering is usually the more direct choice.

## 2. Structure of a Composite aggregation

A composite aggregation has three main parts:

1. `sources`: list of sources generating bucket keys. Each source has a name and a type such as `terms`, `histogram`, `date_histogram`, or `geotile_grid`.
2. `size`: maximum number of buckets returned in a single page.
3. `after`: cursor used to resume after the key processed on the previous page.

The response can include:

- `buckets`: the buckets in the current page.
- `key`: an object holding each source's value for the bucket.
- `doc_count`: the number of documents in the bucket.
- Sub-aggregations if declared in the request.
- `after_key`: cursor for the next page if more data remains.

Example of a two-dimensional bucket:

```json
{
  "key": {
    "category": "books",
    "status": "PAID"
  },
  "doc_count": 125
}
```

The key here is the combination `category = books` and `status = PAID`. Each unique combination of source values forms a distinct bucket.

## 3. One-dimensional example: paginating by category

Initial request:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "sales_by_category": {
      "composite": {
        "size": 2,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
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

`size: 0` at the search request level means no document hits are needed. `composite.size: 2` means each aggregation page returns at most two buckets. These two `size` settings operate at different levels and do not replace each other.

Abbreviated response might look like:

```json
{
  "hits": {
    "hits": []
  },
  "aggregations": {
    "sales_by_category": {
      "after_key": {
        "category": "electronics"
      },
      "buckets": [
        {
          "key": { "category": "books" },
          "doc_count": 125,
          "total_amount": { "value": 82500.0 }
        },
        {
          "key": { "category": "electronics" },
          "doc_count": 98,
          "total_amount": { "value": 194000.0 }
        }
      ]
    }
  }
}
```

`after_key` is returned by Elasticsearch to continue pagination. Preserve this exact object for the next request.

## 4. Next request with `after`

Suppose the first page response returned:

```json
{
  "category": "electronics"
}
```

The second page request adds `after`:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "sales_by_category": {
      "composite": {
        "size": 2,
        "after": {
          "category": "electronics"
        },
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
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

The second request must keep the same aggregation name, `sources` order and definitions, field types, query filters, and any settings affecting buckets. Only replace `after` with the newly received cursor.

Do not grab the key of the last bucket and guess the cursor. Elasticsearch can return an `after_key` that differs from the last bucket's key; always use the exact `after_key` from the response.

## 5. Multi-dimensional pagination

Composite aggregations can combine multiple sources. Example report counting orders by category and status:

```http
POST /sales/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "by_category_and_status": {
      "composite": {
        "size": 3,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      }
    }
  }
}
```

Each bucket has a key with two components:

```json
{
  "key": {
    "category": "books",
    "status": "PAID"
  },
  "doc_count": 125
}
```

With 5 categories and 3 statuses, up to 15 combinations could theoretically exist, though by default only combinations containing documents appear. Composite returns combinations in key order; `size: 3` fetches at most three buckets per page.

### Source order matters

The declaration order of sources determines the sort order of composite keys. If you swap the order of `category` and `status` between two requests, the previous `after` cursor no longer aligns with the same pagination sequence.

Therefore, throughout an entire scan:

- Keep source names identical.
- Keep source order identical.
- Keep each source's aggregation type identical.
- Keep each source's sort order identical.
- Update only the `after` cursor.

## 6. Types of composite sources

Composite aggregation supports several source types for generating keys.

| Source | Used for | Example |
|---|---|---|
| `terms` | Group by exact field value | `category`, `status`, `tenantId` |
| `histogram` | Group numbers into uniform intervals | Price in steps of 100, quantity in steps of 10 |
| `date_histogram` | Group dates/times by calendar or fixed intervals | Daily/monthly revenue |
| `geotile_grid` | Group geographic locations into map tiles | Event counts per tile |

### Terms source

```json
{
  "category": {
    "terms": {
      "field": "category"
    }
  }
}
```

Typically used with `keyword`, numeric, or exact-value fields. For `text` fields needing full-value grouping, use a `keyword` subfield.

### Histogram source

```json
{
  "price_range": {
    "histogram": {
      "field": "price",
      "interval": 100
    }
  }
}
```

Keys are generated at numeric intervals. This creates uniform interval groups, not an arbitrary list of custom ranges.

### Date histogram source

```json
{
  "month": {
    "date_histogram": {
      "field": "createdAt",
      "calendar_interval": "month",
      "time_zone": "Asia/Ho_Chi_Minh",
      "format": "yyyy-MM"
    }
  }
}
```

`calendar_interval` fits calendar periods such as day/month; `fixed_interval` fits fixed durations. `time_zone` sets bucket boundaries in the desired timezone. `format` affects how the key renders as a string without changing the underlying instant.

### Geotile grid source

```json
{
  "tile": {
    "geotile_grid": {
      "field": "location",
      "precision": 7
    }
  }
}
```

Used with appropriate `geo_point` or `geo_shape` fields. Higher precision creates smaller tiles and potentially more buckets.

## 7. `after_key` is a cursor, not a page number

Composite pagination has no `page=1`, `page=2` like UI pagination. `after_key` is an object containing keys for the continuation point in the composite ordering.

Example with two sources:

```json
{
  "category": "electronics",
  "status": "PAID"
}
```

The application persists this exact object and sends it back inside `after`:

```json
{
  "after": {
    "category": "electronics",
    "status": "PAID"
  }
}
```

Do not convert the cursor into a numeric offset, do not store only part of the key, and do not reorder its properties. Preserve all source names and values with their exact types.

### Do not infer `after_key` from the last bucket

Elasticsearch explicitly notes that `after_key` need not match the key of the last returned bucket. Therefore, the safe practice is to extract `after_key` from the response and pass it verbatim to the next request.

### When does iteration end?

Normally, loop until the response contains no buckets. Do not rely solely on the current page having fewer buckets than `size`; termination should be driven by the actual response and cursor. A page can contain fewer or exactly `size` buckets and still have a subsequent page or not depending on response state.

## 8. `missing_bucket` and missing field values

By default, a composite source skips documents lacking an indexed value for the source field. If you need a bucket representing missing values, enable `missing_bucket`:

```json
{
  "category": {
    "terms": {
      "field": "category",
      "missing_bucket": true,
      "missing_order": "last"
    }
  }
}
```

When enabled, a bucket may have a `null` key for that source. `missing_order` controls where the missing bucket sits in the sort order, if configured and supported by that source type/version.

Distinguish clearly:

- Field does not exist.
- Field is written as JSON `null`.
- Field has empty string `""`.
- Field holds an application-defined sentinel value.

Elasticsearch normally does not index JSON `null` as a standard term value unless the mapping specifies `null_value`. Consequently, missing buckets do not necessarily distinguish every null-source variant in the SQL sense.

## 9. Key ordering and sorting buckets

Composite aggregation sorts buckets by the order of its sources, according to each source's configuration. With a `terms` source, you can set `order` ascending or descending:

```json
{
  "category": {
    "terms": {
      "field": "category",
      "order": "desc"
    }
  }
}
```

When there are multiple sources, the first source takes primary sort precedence; ties fall through to subsequent sources. This is key ordering for pagination, not ordering by `doc_count` or metric sub-aggregations.

If you need to rank top buckets by revenue, a `terms` aggregation ordered by a metric is usually more suitable. Composite is built to traverse the key space via cursor, not to find top N by an arbitrary metric.

## 10. Sub-aggregations inside composite buckets

Composite aggregations can contain sub-aggregations to compute metrics for each key combination.

Example grouping by category and status while computing total revenue and average price:

```json
{
  "size": 0,
  "aggs": {
    "sales_groups": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      },
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
        }
      }
    }
  }
}
```

Each bucket contains `key`, `doc_count`, `total_amount`, and `average_amount`. As pages advance, sub-aggregations are computed for the current page's buckets. The application can process and persist each bucket to its destination before fetching the next page.

### Sub-aggregations do not change the cursor

Cursors are derived from composite key sources, not from metrics. Do not use `total_amount` or `doc_count` to construct `after`.

## 11. Aggregated document scope

The top-level query restricts the input document set for the composite aggregation. Example aggregating only paid orders within a time window:

```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PAID"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2026-02-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "sales_groups": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          }
        ]
      }
    }
  }
}
```

Every subsequent composite page must keep the exact same query filter. Changing the query mid-scan can cause the cursor to resume on a different bucket set, making scan results logically inconsistent.

## 12. Data and multidimensional result example

Suppose the data is:

| Order | Category | Status | Amount |
|---|---|---|---:|
| o-1 | books | PAID | 100 |
| o-2 | books | PAID | 200 |
| o-3 | books | PENDING | 50 |
| o-4 | electronics | PAID | 500 |
| o-5 | electronics | PENDING | 150 |
| o-6 | toys | PAID | 80 |

Composite sources `category` and `status` produce these buckets:

| Key category | Key status | `doc_count` | Total amount |
|---|---|---:|---:|
| books | PAID | 2 | 300 |
| books | PENDING | 1 | 50 |
| electronics | PAID | 1 | 500 |
| electronics | PENDING | 1 | 150 |
| toys | PAID | 1 | 80 |

With `size: 2`, the application receives the first two buckets, saves the `after_key` cursor, and fetches the remaining buckets on subsequent pages. Composite does not generate a bucket for `toys + PENDING` because no documents match that combination, unless configuration and data represent it otherwise.

## 13. Using Composite aggregation in Spring Data Elasticsearch

Spring Data Elasticsearch integrates the Elasticsearch Java API Client via `NativeQuery`. A composite aggregation is declared using ELC's `Aggregation` type and attached to the query via `withAggregation(name, aggregation)`.

Illustrative example of a composite aggregation by category:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.CompositeAggregationSource;
import co.elastic.clients.elasticsearch._types.aggregations.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

import java.util.List;
import java.util.Map;

Map<String, FieldValue> afterKey = null;

Aggregation compositeAggregation = Aggregation.of(a -> a.composite(c -> {
    c.size(100);
    c.sources(List.of(
        Map.of("category", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("category"))
        ))
    ));
    if (afterKey != null) {
        c.after(afterKey);
    }
    return c;
}));

Query query = NativeQuery.builder()
    .withMaxResults(0)
    .withAggregation("sales_by_category", compositeAggregation)
    .build();
```

This snippet highlights the main pieces: `CompositeAggregationSource` defines each source, `size` sets buckets per page, and `after` receives the cursor. Exact ELC builder syntax can vary by the Elasticsearch Java API Client version managed by Spring Data; check the Javadoc of your actual dependency if `sources` overloads or `after` types differ. Do not mix classes from legacy `RestHighLevelClient` with ELC's `co.elastic.clients` package.

In versions with `NativeQueryBuilder.withMaxResults(0)`, you can set maximum document hits to 0 when only aggregations are needed. If your API version uses another configuration method, the REST-level goal remains `size: 0`.

### Composite aggregation with multiple sources

Add a `status` source:

```java
Aggregation compositeAggregation = Aggregation.of(a -> a.composite(c -> c
    .size(100)
    .sources(List.of(
        Map.of("category", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("category"))
        )),
        Map.of("status", CompositeAggregationSource.of(s -> s
            .terms(t -> t.field("status"))
        ))
    ))
));
```

When paginating, `afterKey` must include both `category` and `status`. Do not send only the first source.

## 14. Reading composite buckets in Spring Data

After execution:

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<SaleDocument> hits = operations.search(query, SaleDocument.class);

if (hits.getAggregations() instanceof ElasticsearchAggregations aggregations) {
    var composite = aggregations
        .get("sales_by_category")
        .aggregation()
        .composite();

    for (var bucket : composite.buckets().array()) {
        Map<String, FieldValue> key = bucket.key();
        long documentCount = bucket.docCount();

        String category = key.get("category").stringValue();
    }

    Map<String, FieldValue> nextAfterKey = composite.afterKey();
}
```

`ElasticsearchAggregations` is Spring Data's container for ELC aggregation responses. `aggregation().composite()` extracts the composite variant; `buckets().array()` holds the current page's buckets; `bucket.key()` is the map of source values; `docCount()` is the bucket's document count; `afterKey()` is the next cursor if returned in the response.

For numeric, date, or geo sources, read `FieldValue` using the matching accessor—for example `longValue()`, `doubleValue()`, or `stringValue()` depending on key type. Do not call `stringValue()` on every source if the actual key is numeric or null.

When the response has no `afterKey`, or the next page has no buckets, the scan is complete. Handle the case where `afterKey()` can be null/empty and never assume a cursor is always present.

## 15. Bucket pagination loop in the application

General flow:

```text
afterKey = null

do:
    query = buildCompositeQuery(afterKey)
    response = execute(query)
    aggregation = readComposite(response)

    for each bucket in aggregation.buckets:
        process(bucket.key, bucket.doc_count, bucket.metrics)

    afterKey = aggregation.after_key

while afterKey exists and current page has buckets
```

Java pseudocode example:

```java
Map<String, FieldValue> after = null;

while (true) {
    Query query = buildCompositeQuery(after);
    SearchHits<SaleDocument> hits = operations.search(query, SaleDocument.class);

    ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) hits.getAggregations();

    var composite = aggregations
        .get("sales_by_category")
        .aggregation()
        .composite();

    var buckets = composite.buckets().array();
    if (buckets.isEmpty()) {
        break;
    }

    for (var bucket : buckets) {
        processBucket(bucket);
    }

    after = composite.afterKey();
    if (after == null || after.isEmpty()) {
        break;
    }
}
```

`buildCompositeQuery(after)` must recreate the exact same aggregation definition while changing only the cursor. In production code, verify that the container/aggregation exists and matches the expected type before casting; this example focuses on the cursor loop.

If a response returns a page of buckets without `after_key`, that is usually the final page. If your API version or wrapper represents the cursor differently, check the JSON response and corresponding accessors.

## 16. Persisting the cursor to resume jobs

If a job runs continuously within a single process, keeping `after_key` in memory may suffice. If the job must resume after a crash, persist the cursor durably alongside job metadata:

```json
{
  "jobId": "monthly-sales-export-2026-01",
  "index": "sales-2026-01",
  "aggregation": "sales_groups",
  "pageSize": 500,
  "afterKey": {
    "category": "electronics",
    "status": "PAID"
  },
  "processedBuckets": 1500,
  "updatedAt": "2026-02-01T02:15:00Z"
}
```

To resume accurately, besides the cursor, also store the logical definition of the scan:

- Source index or alias.
- Query filter and time window.
- List, order, and types of sources.
- Page size and ordering settings.
- Job or schema version.
- Status of successfully written output.

If you change sources, filters, or indices while reusing an old cursor, the resumption point no longer matches the same bucket set.

### Cursor storage and output must be consistent

Suppose the application writes buckets to a target database and then saves `after_key`. If the process crashes after writing buckets but before saving the cursor, those buckets may be reprocessed. Therefore, output writes should be idempotent or keyed uniquely by the composite key.

Conversely, if you save the cursor before writing output and the process crashes afterward, buckets can be skipped. Determine commit ordering and design idempotency/checkpointing accordingly.

## 17. Mutating data during pagination

Each composite page is a separate search request. If the index mutates between requests, buckets can shift with new data, causing scan results not to reflect a single consistent snapshot.

For example:

- The first page already read the `books` bucket.
- While the job runs, a new document is added to `books`.
- Subsequent requests will not recompute the already-read bucket.
- A new key added in the unread key region may appear on a later page.

When consistent reports are required:

- Run against an immutable index or an index frozen from writes during export.
- Bound data using a settled watermark/time range.
- Use snapshot/PIT within the same search flow if your Elasticsearch version supports combining PIT with aggregations and the application preserves the PIT ID.
- Or create a stable copy of the data before aggregating.

PIT is a search-context snapshot mechanism, not a cursor replacing `after_key`. When supported in your deployment version, PIT pins the data view while composite `after_key` still advances across buckets. Check PIT compatibility and lifecycle for your running Elasticsearch version.

## 18. Composite aggregation vs. `terms` aggregation

| Criterion | `terms` | `composite` |
|---|---|---|
| Goal | Top buckets by count or metric | Paginate buckets by key |
| Return limit | Top `size` buckets | `size` buckets per page |
| Cursor | No full `after_key` pagination mechanism | Has `after_key` and `after` |
| Default order | By `doc_count` descending | By source keys |
| Multi-dimensional | Can nest bucket aggregations | Multiple sources produce flat composite keys |
| Scan all buckets | Not the primary choice | Primary design goal |
| Top N by metric | More suitable | Less suitable than terms |
| Large bucket export | Memory-heavy if size is raised high | Split into pages |

Composite does not replace every use of terms. Choose by business question: "what are the top N groups?" usually uses terms; "iterate through all groups by key" usually uses composite.

## 19. Composite aggregation and `bucket_sort`

`bucket_sort` is a pipeline aggregation that can sort or truncate buckets already generated by its parent aggregation. It is not a full key-space pagination mechanism like composite.

If you need top buckets by metric, consider terms ordered by metric or an appropriate pipeline. If you need every bucket sequentially by key, use composite `after_key`.

Do not use `bucket_sort` to simulate cursor pagination. It only operates on buckets already produced by the parent aggregation in the current request; it does not resume across the key space over multiple requests.

## 20. Source mappings and data types

Composite aggregation relies on source field mappings and doc values.

| Source field | Suitable mapping | Notes |
|---|---|---|
| Code, status, category | `keyword` | Do not use text when grouping by full value |
| Quantity, price, score | `integer`, `long`, `double`, `scaled_float` | Choose precision matching business needs |
| Timestamp | `date` or `date_nanos` | Specify timezone and calendar/fixed interval |
| Location | `geo_point` or `geo_shape` | Use appropriate geotile grid source |

Fields generally require doc values for aggregations to operate efficiently. For keyword and numeric types, doc values are enabled by default. Do not disable doc values on fields needed for composite aggregations without a specific reason.

### Multi-valued fields

If a source field contains multiple values in a single document, that document can participate in multiple buckets. When composite has multiple multi-valued sources, bucket combinations can multiply by the Cartesian product of each source's values.

For example, a document with `tags = [java, spring]` and `regions = [vn, sg]` can contribute to the combinations:

```text
(java, vn)
(java, sg)
(spring, vn)
(spring, sg)
```

This can cause bucket cardinality to grow quickly. Inspect multi-valued data and use multidimensional composite only when Cartesian combination semantics are what the business requires.

## 21. Performance and limits

Composite aggregation enables bucket pagination, yet it does not make aggregation free. Elasticsearch must still read and group matching data on shards to construct buckets.

Some guidelines:

- Choose a page size large enough to reduce round trips without inflating responses excessively.
- Filter documents using a top-level query before aggregating.
- Use fields with doc values and appropriate mappings.
- Avoid sources with excessively high cardinality if not truly needed.
- Reduce unnecessary sub-aggregations and computation depth.
- Read only the buckets and metrics needed for output.
- Monitor per-page latency, heap, CPU, search thread pool, and shard load.
- Limit the number of concurrent composite jobs.
- Do not raise page size unboundedly just to cut request count.

Larger page sizes reduce call count at the cost of more buckets and sub-aggregations per response. Smaller page sizes reduce per-response memory at the cost of higher round-trip overhead. Measure with key distributions and data close to production.

### Cardinality and bucket counts

If the first source has 100,000 values and the second source has 20 values, the theoretical key space can be enormous. Composite returns only one page at a time, yet total work remains proportional to the number of buckets traversed. Estimate the combination count and verify whether exporting everything is genuinely needed or whether top N suffices.

## 22. Common mistakes

### Setting a huge `terms.size` to fetch all buckets

Raising size produces huge responses, consumes heavy memory, and still lacks general cursor pagination. Use composite when scanning all buckets.

### Using the last bucket key for `after` instead of `after_key`

`after_key` may not match the last key in the buckets array. Always use the cursor returned by Elasticsearch.

### Changing sources between pages

Changing source names, order, or types invalidates cursor logic. Keep the aggregation definition identical throughout the scan.

### Changing the query filter between pages

The cursor is anchored to the key space of the original query. Changing filters mid-scan can skip or duplicate buckets. Keep the query consistent.

### Stopping whenever a page has fewer buckets than size

Do not treat fewer buckets than page size as the sole termination condition. Check `after_key` and subsequent pages based on actual responses.

### Confusing composite with top N

Composite traverses by key; it does not rank by revenue or `doc_count`. Use terms when the goal is top buckets by metric.

### Ignoring missing-field buckets

By default, documents lacking source values may be omitted from buckets. If missing values must be grouped, consider `missing_bucket: true` and `missing_order` rules.

### Non-idempotent output handling

If a job restarts and re-reads a prior page, the same buckets can be written twice. Use the composite key as a unique key or apply proper transactions/checkpointing.

### Letting data mutate across pages

Independent requests can observe different snapshots. For snapshot-consistent exports, use immutable indices, watermarks, or compatible PIT.

## 23. Testing composite pagination

Prepare test data that includes:

- More keys than page size to force multiple pages.
- Multiple sources to verify composite keys.
- Documents missing one source field.
- Multi-valued fields if the system actually uses them.
- Buckets with metric sub-aggregations.
- Keys sitting near sort boundaries.

Behaviors to verify:

1. The first page returns at most page-size buckets.
2. `after_key` from the first page passes verbatim into `after` on the next page.
3. No buckets are duplicated across pages on a stable dataset.
4. No buckets are skipped.
5. Multi-source combinations have accurate keys and preserve sort order.
6. Sub-aggregations are read accurately for each bucket.
7. Missing-field buckets appear or are omitted per `missing_bucket`.
8. The loop terminates when no buckets/cursor remain.
9. Restarting from a saved cursor does not write duplicate output.
10. Query filters remain consistent across pages.

Do not check only the total bucket count. Compare the set of unique composite keys from the scan against expected sets from fixture data.

## 24. Workflow for implementing a bucket export job

An export job can follow this sequence:

1. Identify the source index/alias and query filter for the dataset.
2. Select sources and key sort order for grouping.
3. Choose page size based on bucket count, sub-aggregation size, and processing capacity.
4. Send the initial request without `after`.
5. Read buckets and convert keys/metrics into DTOs or output records.
6. Write output idempotently keyed by the composite key.
7. Extract `after_key` from the response and persist a checkpoint if resume is needed.
8. Send the next request with `after` set to the latest cursor.
9. Repeat until no buckets or cursor remain.
10. Close PIT if a snapshot was used.
11. Record total buckets processed, duration, and completion status.

## 25. Conclusion

Composite aggregation is a bucket pagination mechanism for cases requiring traversal of all data groups or multidimensional field combinations. Requests declare `sources` and `size`; responses return `buckets` plus `after_key`; subsequent requests pass that exact cursor in `after`. Always use the `after_key` returned by Elasticsearch, never infer it from the last bucket, and keep source/query definitions consistent across pages.

In Spring Data Elasticsearch, composite aggregations are declared via `NativeQuery` and the Elasticsearch Java API Client, then read from `SearchHits.getAggregations()` through `ElasticsearchAggregations`. Each bucket holds a composite key, `doc_count`, and optional metric sub-aggregations. `terms` suits top N queries, while composite suits cursor scans over all buckets. For long-running jobs, design checkpoints, idempotent outputs, and handling for data mutating across pages; choose page size based on empirical measurement.

## References

- [Elasticsearch – Composite aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-composite-aggregation)
- [Elasticsearch – Terms aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-terms-aggregation)
- [Elasticsearch – Date histogram aggregation](https://www.elastic.co/docs/reference/aggregations/search-aggregations-bucket-datehistogram-aggregation)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Spring Data Elasticsearch – NativeQuery and search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – ElasticsearchAggregations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchAggregations.html)
