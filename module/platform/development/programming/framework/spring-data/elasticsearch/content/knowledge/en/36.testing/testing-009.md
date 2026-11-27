# Testing Sorting, Pagination, Highlighting, and Aggregations

A search feature often has to do several things at once: filter matching documents, sort results according to user criteria, split results into pages, highlight matching text snippets, and return summary statistics. In Spring Data Elasticsearch, these four features—**sorting**, **pagination**, **highlighting**, and **aggregations**—can all be configured on a single search request, yet each has its own rules regarding mappings, performance, and reading results.

Testing each feature in isolation is not enough. For example, sorting may work on the first page yet produce duplicate or skipped records across page transitions; hits may be filtered accurately while aggregations count the entire index; highlighting may return snippets of a field that should not be exposed. A thorough test suite needs to verify hit contents, ordering, page boundaries, snippets, and statistical buckets together.

This lesson uses the **products** index with fields such as `productId`, `name`, `description`, `category`, `brand`, `price`, `createdAt`, and `status`. Examples focus on Spring Data Elasticsearch and the Elasticsearch Java API Client. Some API signatures vary across Spring Data versions; the REST Query DSL illustrates Elasticsearch semantics, while Java snippets should be matched against your project's specific dependencies.

## 1. Four Features in a Single Search Request

A single search request can perform simultaneously:

- **Sort:** determines document order by price, creation date, name, or multiple criteria.
- **Pagination:** limits the number of returned hits and specifies the page position.
- **Highlight:** returns text fragments containing parts matching the query.
- **Aggregation:** computes counts, distributions, min/max/avg, or histograms over the queried document set.

For example, a product listing page may require:

1. Finding only `ACTIVE` products.
2. Sorting by price ascending, then `productId` ascending for deterministic order.
3. Returning 20 products per page.
4. Highlighting search keywords in `name` and `description`.
5. Computing product counts by `category` and price ranges.

An illustrative request:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "must": [
        { "multi_match": {
          "query": "mechanical keyboard",
          "fields": ["name", "description"]
        }}
      ]
    }
  },
  "sort": [
    { "price": { "order": "asc" } },
    { "productId.keyword": { "order": "asc" } }
  ],
  "highlight": {
    "fields": {
      "name": {},
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 10
      }
    }
  }
}
~~~

The search response contains hits, sort values, highlight fragments, and aggregations. The application must read each part properly; not all returned data lives inside the source document.

## 2. Mappings Govern Sorting and Aggregation Capabilities

Before writing sort or aggregation tests, verify the mapping. Elasticsearch distinguishes field types and how auxiliary query structures are stored.

An illustrative mapping:

~~~json
PUT /products
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "brand": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Important fields:

| Field type | Common usage | Sort / aggregation |
|---|---|---|
| keyword | IDs, category, status, brand, identifiers | Suitable |
| text | Content requiring full-text search | Usually not sorted/aggregated directly |
| integer/long/double | Quantities, prices, scores | Suitable |
| date | Timestamps | Suitable |
| boolean | On/off flags | Suitable |
| nested | Object arrays preserving per-element relationships | Requires corresponding nested query/sort/aggregation |

A `text` field is analyzed into tokens for searching. It normally lacks doc values, and Elasticsearch prevents sorting or aggregating directly on `text` fields by default. To sort by name, a `keyword` multi-field like `name.keyword` is usually used.

Do not enable `fielddata` on `text` just to sort or aggregate unless you understand the memory cost. Fielddata can consume substantial heap. Designing a `keyword` multi-field is generally more suitable.

## 3. Verifying Mappings Before Testing

You can retrieve the mapping via REST:

~~~http
GET /products/_mapping
~~~

In integration tests, verify:

- Fields used for sorting exist.
- Fields used for terms aggregations are `keyword` or another suitable type.
- Numeric/date fields have accurate types.
- Multi-fields such as `name.keyword` were created.
- Nested fields are declared `nested` if queries/sorts/aggregations require nested semantics.
- The test index is created with the intended mapping instead of relying on accidental dynamic mapping.

A common error is tests running on an old index whose mapping differs from deployment mapping. When tests fail to create the index explicitly or clear old fixtures, outcomes can depend on execution order.

## 4. Basic Sorting by a Single Field

Elasticsearch supports ascending or descending sort:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "sort": [
    { "price": { "order": "asc" } }
  ]
}
~~~

- `asc`: ascending.
- `desc`: descending.

Numeric sorting compares numerical values rather than strings. If `price` were mapped as `keyword`, ordering would be lexicographical—for example, `"100"` coming before `"20"`. Therefore tests must verify the mapping, not just a couple of coincidental results.

Example test expecting ascending prices:

| productId | price |
|---|---:|
| p-001 | 19.50 |
| p-003 | 35.00 |
| p-002 | 120.00 |

Seed fixtures with values that expose string-sort bugs, including pairs like `9`, `20`, and `100`.

## 5. Multi-Field Sorting and Precedence

The sort array is evaluated in declared order. The first field is the primary criterion; subsequent fields break ties when prior values are equal.

~~~http
POST /products/_search
{
  "sort": [
    { "price": { "order": "asc" } },
    { "createdAt": { "order": "desc" } },
    { "productId": { "order": "asc" } }
  ]
}
~~~

This order means:

1. Lower prices come first.
2. If prices tie, newer products come first.
3. If both price and timestamp tie, `productId` decides the final order.

Tests should create at least two documents with identical price and timestamp to confirm the tie-breaker actually takes effect. Without tied values in fixtures, the test never proves the secondary or tertiary criteria work.

Do not rely on Elasticsearch's default order when multiple documents share the same sort value. Order among tied documents can change across shards, refreshes, or executions.

## 6. Deterministic Sorting and Unique Tie-Breakers

Pagination requires deterministic ordering. If you only sort by `price` and multiple products share the same price, a document can shift pages after a refresh or data change.

Add a unique field with doc values as a tie-breaker, such as a `keyword` `productId`. Avoid sorting directly on the special `_id` field by default: Elasticsearch has specific limitations and costs for sorting on `_id`. Storing a separate `keyword` business ID is usually easier to control.

Example:

~~~json
"sort": [
  { "price": "asc" },
  { "productId": "asc" }
]
~~~

Stability test:

- Index multiple documents with the same `price`.
- Run the same query multiple times.
- Compare `productId` order across runs.
- Step through consecutive pages.
- Verify no IDs are duplicated or skipped while the dataset is unchanged.

The tie-breaker must actually be unique within the search scope. If `productId` is only unique within a tenant and queries always filter by tenant, that can suffice; if a query spans multiple tenants, use a cluster/index-wide unique ID.

## 7. Sorting on Text Fields and Keyword Multi-Fields

If `name` is mapped as `text`, the following request is usually unsuitable:

~~~http
POST /products/_search
{
  "sort": [
    { "name": "asc" }
  ]
}
~~~

Use a `keyword` multi-field:

~~~http
POST /products/_search
{
  "sort": [
    { "name.keyword": { "order": "asc" } }
  ]
}
~~~

The mapping can declare:

~~~json
"name": {
  "type": "text",
  "fields": {
    "keyword": {
      "type": "keyword",
      "normalizer": "lowercase_normalizer"
    }
  }
}
~~~

For case-insensitive sorting, configure a normalizer on the `keyword` field. Ensure the normalizer is declared in settings when creating the index.

Tests should use names like `Alpha`, `alpha`, and `BETA` to confirm sorting rules. Without a normalizer, keyword sorting is case-sensitive according to term order.

## 8. Missing Values and Unmapped Fields

Some documents may lack the field used for sorting. Elasticsearch supports the `missing` setting to place missing values first or last:

~~~http
POST /products/_search
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": "_last"
      }
    }
  ]
}
~~~

Common choices include `_first`, `_last`, or an explicit fallback value matching the field type.

When searching across multiple indices with different mappings, a field may not exist in one index. You can set `unmapped_type` in sort to declare the expected type for unmapped fields. However, this is for schema compatibility; do not use it to mask an index that should have had a mapping but was created wrongly.

Tests should include a document missing `price` and verify its position. Also test index aliases pointing to multiple backing indices with compatible mappings.

## 9. Sorting on Multi-Valued Fields

A field can hold multiple values—for example, regional prices or multiple timestamps. When sorting on a multi-valued field, Elasticsearch picks a representative value using a sort `mode`.

Example:

~~~http
POST /products/_search
{
  "sort": [
    {
      "regionalPrices": {
        "order": "asc",
        "mode": "min"
      }
    }
  ]
}
~~~

Common modes:

- `min`: use the smallest value.
- `max`: use the largest value.
- `avg`: average.
- `sum`: sum.
- `median`: median.

Supported modes depend on field type and sort semantics. Tests must create a document with multiple distinct values to verify the mode rather than seeding single-element arrays.

## 10. Nested Sorting

When data consists of nested objects, sorting must specify the nested `path` and may need a nested `filter`. For instance, a product with multiple offers:

~~~json
{
  "productId": "p-1001",
  "offers": [
    { "region": "VN", "price": 120 },
    { "region": "SG", "price": 135 }
  ]
}
~~~

If `offers` is mapped as `nested`, sorting by offer price in `VN` requires specifying the nested path and filter:

~~~http
POST /products/_search
{
  "sort": [
    {
      "offers.price": {
        "order": "asc",
        "mode": "min",
        "nested": {
          "path": "offers",
          "filter": {
            "term": {
              "offers.region": "VN"
            }
          }
        }
      }
    }
  ]
}
~~~

If `offers` is just an ordinary `object` rather than `nested`, Elasticsearch does not preserve per-element attribute correlation the way nested queries require. Tests must use mappings and fixtures matching the true data model.

## 11. Pagination with from and size

The familiar pagination mechanism uses `from` and `size`:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "sort": [
    { "createdAt": { "order": "desc" } },
    { "productId": { "order": "asc" } }
  ]
}
~~~

- `from`: number of hits to skip before returning results.
- `size`: maximum number of hits to return.

First page of 20 items: `from = 0, size = 20`.

Second page of 20 items: `from = 20, size = 20`.

Third page of 20 items: `from = 40, size = 20`.

For page-based interfaces, use `PageRequest` in Spring Data:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("productId")
        )
);
~~~

A repository can declare:

~~~java
Page<Product> findByStatus(String status, Pageable pageable);
~~~

Example invocation:

~~~java
Page<Product> page =
        productRepository.findByStatus("ACTIVE", pageable);
~~~

Exact behavior of `Page`, `Pageable`, and sort fields depends on the repository/API and version. With custom queries, verify that pageable and sort are actually applied to the request sent to Elasticsearch.

## 12. Reading Page and SearchHits Results

`Page` typically provides:

- `content`: list of items on the current page.
- `number`: page index.
- `size`: page size.
- `totalElements`: total matching items.
- `totalPages`: total number of pages.
- `hasNext`/`hasPrevious`: pagination navigation flags.

With `ElasticsearchOperations`, search returns `SearchHits<T>`. Each `SearchHit` can provide:

- `content`: converted entity.
- `id` and `index`.
- `score`.
- `sortValues`.
- `highlightFields`.
- hit-related metadata.

Example:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
            hit.getHighlightFields();
}
~~~

Verify type names and getters against your version. Do not assume `SearchHit` content already embeds highlight fragments; highlights are returned in separate metadata.

When aggregations are needed, read aggregations from `SearchHits` via the aggregation container abstraction provided by Spring Data. Exact structure depends on the Java API Client and Spring Data Elasticsearch version.

## 13. Deep Pagination Limits with from/size

Elasticsearch typically enforces a default `max_result_window` limit of 10,000 for `from + size`. Querying deep pages can be rejected or consume substantial resources.

For example:

- Page 1: `from 0, size 20`.
- Page 100: `from 1,980, size 20`.
- Page 500: `from 9,980, size 20`.
- Page 501: `from 10,000, size 20`.

When `from + size` exceeds the limit, the request can return a `result window too large` error.

Do not raise `max_result_window` indefinitely just to support a "next page" button. Each shard must retain and sort more hits for deep offsets, increasing memory and merge overhead.

When users need to jump to distant pages, reconsider the UX or use a cursor/`search_after` strategy. `from`/`size` suits early pages and moderate result counts.

## 14. Search_after for Deep Pagination

`search_after` uses the sort values of the last hit on the current page as the starting point for the next page. It avoids skipping large offsets like `from`/`size`.

First page:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Suppose the last hit has sort values:

~~~json
[
  "2026-11-13T08:30:00Z",
  "p-020"
]
~~~

The next page sends the exact same sort and `search_after`:

~~~http
POST /products/_search
{
  "size": 20,
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "search_after": [
    "2026-11-13T08:30:00Z",
    "p-020"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

`search_after` must preserve the exact sort order and returned value types. Do not construct a cursor using only `createdAt` if the sort also includes `productId`. Every sort key must be passed in the exact order.

`search_after` is not combined with `from > 0` for ordinary offset pagination. It suits next-page/cursor flows rather than arbitrary jumps to page 500.

## 15. PIT Combined with search_after

If data changes while a user is paginating, ordering or the result set can shift between requests. **Point in Time (PIT)** maintains a consistent view of the index for a bounded duration.

General flow:

1. Open a PIT for the index.
2. Send the first search with PIT, sort, and size.
3. Read the sort values of the last hit.
4. Send the next request with the same PIT and `search_after`.
5. Repeat until no hits remain.
6. Close the PIT when finished or when the session expires.

Open PIT:

~~~http
POST /products/_pit?keep_alive=1m
~~~

Search with PIT:

~~~http
POST /_search
{
  "size": 20,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "sort": [
    { "createdAt": "desc" },
    { "productId": "asc" }
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

The next page adds `search_after` from the last hit. The response may return a new PIT ID; if so, use the latest ID for the next request.

Close PIT:

~~~http
DELETE /_pit
{
  "id": "PIT_ID"
}
~~~

A PIT consumes cluster resources while open. Keep `keep_alive` appropriately short, close it when done, and handle cases where the client stops paginating. Do not open a brand new PIT for every page if a consistent sequence of results is needed.

## 16. Testing Pagination Without Duplicates or Skipped Hits

A basic pagination test needs enough documents to span multiple pages. For example, create 45 products with page size 10, expecting 5 pages.

Assertions should cover:

- Page 0 has 10 hits.
- Page 1 has 10 hits.
- The last page has 5 hits.
- Total elements equal 45.
- No duplicate IDs appear across pages.
- The union of all IDs across all pages equals the fixture set.
- Sorting is right on every page.
- No out-of-filter hits appear.
- Empty results return empty content and `totalElements` equal to 0.

If sort fields have duplicate values, add a tie-breaker so the test does not rely on random ordering.

With `search_after`, loop requests using the last hit's sort values, collect all IDs, and verify no duplicates or missing documents occur within a fixed PIT.

## 17. Pagination When Data Changes

Do not conclude pagination is stable under concurrent writes based solely on a static-dataset test. With `from`/`size` and inserts/updates occurring between page fetches, documents can shift positions.

Example:

1. Page one returns sort values 100 down to 91.
2. A new document with sort value 110 is inserted.
3. Page two uses `from = 10`.
4. A document can be duplicated or skipped as offsets shift.

PIT + `search_after` fits when traversing a consistent snapshot. If the product accepts data changing between pages, define the UX and test against those semantics.

Do not promise duplicate-free pagination under all conditions if the application lacks snapshots while data mutates.

## 18. How Does Highlighting Work?

Highlighting returns field fragments containing query matches. It is commonly used to show users why a document matched.

Example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mechanical keyboard"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

If source `description` is:

~~~text
A compact wireless keyboard with mechanical switches.
~~~

A highlight fragment may be:

~~~html
A compact <mark>wireless</mark> <mark>keyboard</mark> with mechanical switches.
~~~

Elasticsearch selects fragments based on matching content and highlighter rules. Fragments are not guaranteed to be complete sentences or contain every query term.

Highlighting does not modify the source document. It is returned in search hit metadata; the application decides how to display and escape the content.

## 19. Important Highlight Configurations

| Setting | Meaning |
|---|---|
| `fields` | Fields to highlight |
| `pre_tags` | Markup inserted before matching terms |
| `post_tags` | Markup inserted after matching terms |
| `fragment_size` | Target fragment size |
| `number_of_fragments` | Maximum number of fragments |
| `no_match_size` | Prefix length returned when no match occurs, if configured |
| `require_field_match` | Whether to highlight only fields matched by the query |
| `type` | Highlighter type |
| `boundary_scanner` | How fragment boundaries are chosen |
| `order` | Fragment ordering, e.g., by `score` |

Settings can be configured per field:

~~~json
"highlight": {
  "pre_tags": ["<em>"],
  "post_tags": ["</em>"],
  "fields": {
    "name": {
      "number_of_fragments": 0
    },
    "description": {
      "fragment_size": 150,
      "number_of_fragments": 3
    }
  }
}
~~~

`number_of_fragments = 0` requests returning the entire highlighted field instead of splitting into fragments. This can return long strings; consider payload size and field access permissions.

## 20. Choosing the Right Highlighter

Elasticsearch offers several common highlighters:

- **unified:** the default choice in many cases, supporting many query types and fragment analysis.
- **plain:** simple highlighter driven by the query and field content.
- **fvh (Fast Vector Highlighter):** suitable when fields store term vectors with appropriate offsets/positions.
- **semantic:** intended for semantic search cases and depends on version/configuration.

FVH may require mapping `term_vector` with positions and offsets. If the mapping does not store the required data, the highlighter may not work as expected or fall back.

Do not pick a highlighter by name alone. Test against real query types: `match`, `multi_match`, `phrase`, `nested`, synonyms, or multi-clause queries.

## 21. Highlighting Multiple Fields and multi_match

When a query searches multiple fields, each field can be highlighted individually:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless keyboard",
      "fields": ["name", "description", "brand"]
    }
  },
  "highlight": {
    "fields": {
      "name": {},
      "description": {
        "fragment_size": 100,
        "number_of_fragments": 2
      },
      "brand": {
        "number_of_fragments": 0
      }
    }
  }
}
~~~

Tests should verify:

- Which fields are actually highlighted.
- Fragments contain matching terms.
- Unconfigured fields do not unexpectedly produce highlights.
- Multi-field queries do not drop highlights on any intended field.
- Highlight fragments are not confused with full source values.

If the query uses field aliases or multi-fields, verify the highlighter recognizes the queried fields properly.

## 22. Reading Highlights from SearchHit in Spring Data

With `ElasticsearchOperations`, each `SearchHit` can expose highlighted fields.

Example:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    List<String> nameFragments =
            hit.getHighlightField("name");

    List<String> descriptionFragments =
            hit.getHighlightField("description");
}
~~~

Exact method names vary by version; the API generally provides a `highlightFields` map or per-field getters. Check `SearchHit` in your project's dependencies.

Do not assume `Product.name` contains highlight tags. When returning snippets to the frontend, build a dedicated response DTO:

~~~java
public record ProductSearchResult(
        Product product,
        List<String> nameHighlights,
        List<String> descriptionHighlights
) {
}
~~~

Map `SearchHit` to the DTO:

~~~java
ProductSearchResult toResult(SearchHit<Product> hit) {
    return new ProductSearchResult(
            hit.getContent(),
            hit.getHighlightField("name"),
            hit.getHighlightField("description")
    );
}
~~~

Separating metadata from the entity prevents saving HTML tags into the source document or accidentally persisting highlighted fragments when saving entities.

## 23. Safe Highlight Rendering

Highlights normally contain `pre_tags` and `post_tags` configured by the application. If the frontend renders fragments as HTML, guard against XSS.

Never allow users to control `pre_tags`/`post_tags` arbitrarily. Field content may contain user-submitted HTML or scripts; the highlighter is not an HTML sanitizer.

Guidelines:

- Use fixed tags such as `mark` or `em`.
- Escape untrusted content according to the frontend's rendering mechanism.
- Permit only controlled markup.
- Do not blindly inject fragments into HTML via `innerHTML`.
- Do not write marked-up fragments back to the document.
- Verify sensitive fields are not highlighted and exposed to unauthorized roles.

Tests should seed a `description` containing special HTML characters alongside search keywords. Verify the response is handled safely and does not execute scripts when rendered.

## 24. What Are Aggregations?

Aggregations compute statistics across the queried document set. Instead of returning only a list of documents, Elasticsearch can return buckets and metrics.

Three common groups:

- **Bucket aggregations:** group documents into buckets, e.g., by category, brand, or price range.
- **Metric aggregations:** compute values such as min, max, avg, sum, or cardinality.
- **Pipeline aggregations:** compute values derived from the results of other aggregations.

Example terms aggregation by category:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
~~~

The response may contain:

~~~json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        {
          "key": "keyboard",
          "doc_count": 12
        },
        {
          "key": "mouse",
          "doc_count": 8
        }
      ]
    }
  }
}
~~~

When only statistics are needed, `size = 0` avoids returning hit documents. Still, the query must filter the intended scope of documents properly.

## 25. Terms Aggregations and Bucket Size

A terms aggregation groups documents by each value of a `keyword` field:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand",
        "size": 20,
        "order": {
          "_count": "desc"
        }
      }
    }
  }
}
~~~

`size` here is the maximum number of buckets returned, distinct from search hits `size`.

Concepts to distinguish:

- Search `size`: number of hit documents returned.
- Aggregation terms `size`: number of buckets returned.
- `shard_size`: number of buckets each shard sends to the coordinator to improve accuracy.
- `doc_count`: document count in a bucket.
- `sum_other_doc_count`: document count belonging to unreturned buckets.
- `doc_count_error_upper_bound`: upper bound on count error under certain distributions/orders.

Terms aggregations fit displaying top categories or brands. To iterate over all high-cardinality values, avoid simply setting a huge `size`.

## 26. Testing Terms Aggregation Accuracy

Fixtures should have a known distribution. For example:

| Category | Document count |
|---|---:|
| keyboard | 5 |
| mouse | 3 |
| monitor | 2 |

Tests verify:

- Bucket `keyboard` has `doc_count` 5.
- Bucket `mouse` has `doc_count` 3.
- Bucket `monitor` has `doc_count` 2.
- Bucket ordering matches `_count desc`.
- No buckets outside the fixture set appear.
- If `size` is smaller than the category count, only the top-N buckets appear.
- `sum_other_doc_count` matches if verifying truncated buckets.

Do not assert only the number of buckets. A bug can return the right three buckets with wrong per-bucket counts if the query filter is incorrect.

Across multi-shard datasets, terms aggregations can be approximate depending on `shard_size` and ordering. Small single-shard integration tests do not prove exactness on large multi-shard clusters. When exact counts per bucket are required, understand the semantics and pick an appropriate aggregation strategy.

## 27. Metric Aggregations: min, max, avg, sum, and cardinality

Example price statistics:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_stats": {
      "stats": {
        "field": "price"
      }
    },
    "unique_brands": {
      "cardinality": {
        "field": "brand"
      }
    }
  }
}
~~~

`stats` typically returns count, min, max, avg, and sum. `cardinality` estimates distinct value counts using a probabilistic algorithm; results are not guaranteed exact on large datasets.

Tests with small fixtures can assert exact min/max/avg/sum. For cardinality, pick suitable fixtures and settings, understand `precision_threshold`, and avoid assuming it is always an exact count.

Common metric aggregations:

| Aggregation | Purpose |
|---|---|
| `min` | Minimum value |
| `max` | Maximum value |
| `avg` | Average |
| `sum` | Sum |
| `value_count` | Count of field values |
| `cardinality` | Estimated count of distinct values |
| `stats` | Multiple basic metrics at once |
| `extended_stats` | Adds standard deviation and related stats |
| `percentiles` | Percentiles |
| `top_hits` | Returns representative hits per bucket |

## 28. Histogram and Range Aggregations

Histograms bucket numeric values into fixed-width intervals:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "histogram": {
        "field": "price",
        "interval": 50,
        "min_doc_count": 0
      }
    }
  }
}
~~~

Range aggregations let you define custom intervals:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 50 },
          { "from": 50, "to": 100 },
          { "from": 100 }
        ]
      }
    }
  }
}
~~~

Ranges are commonly used for UI facets such as under 50, 50 to 100, and 100+. Define boundaries clearly; Elasticsearch treats `from` as inclusive and `to` as exclusive.

Tests should seed values right at boundaries—for example `49.99`, `50`, `99.99`, and `100`—to catch off-by-one boundary mistakes.

Date histograms bucket data over time:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "created_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
~~~

Tests must account for timezones, daylight saving where applicable, and the difference between `calendar_interval` and `fixed_interval`.

## 29. Nested Aggregations and Filter Aggregations

For nested data, aggregations must traverse the nested path:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "offers": {
      "nested": {
        "path": "offers"
      },
      "aggs": {
        "by_region": {
          "terms": {
            "field": "offers.region"
          }
        }
      }
    }
  }
}
~~~

To aggregate over a subset, use a filter aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "active_products": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

A filter aggregation restricts only its child aggregations. If a response contains multiple aggregations, each branch needs its own filter semantics. For tenant isolation, place the tenant filter on the root query to restrict both hits and all aggregations; never filter only a child bucket.

## 30. Composite Aggregations to Paginate Many Buckets

Terms aggregations return top buckets up to `size`, not general pagination over all buckets. For high cardinality where you need to iterate through every group, use a `composite` aggregation with `after_key`.

First page:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "all_categories": {
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
            "brand": {
              "terms": {
                "field": "brand"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

The response returns `after_key`. The next page sends it back in `after`:

~~~json
"after": {
  "category": "keyboard",
  "brand": "acme"
}
~~~

Composite aggregations suit exporting or scanning all groups in batches. They differ from terms `size` and should not be replaced by cranking terms `size` arbitrarily high.

Tests should:

- Read all bucket pages until `after_key` is absent.
- Verify no duplicate keys.
- Verify no category/brand combinations are missed.
- Keep `sources` in the exact same order across requests.
- Handle the final response with no `after_key`.
- Maintain consistent query filters and snapshot semantics if data changes.

## 31. Combining Aggregations with Query Filters

Aggregations run by default over documents matching the root query. Therefore, the query filter must reflect the exact dataset the user is authorized to see.

Example filtering by `ACTIVE` and tenant before computing category statistics:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-a" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

Do not apply the tenant filter solely to hit retrieval while computing aggregations via another query or request. An endpoint could return the right product list while leaking statistics across all tenants.

Tests should seed a category that exists only in tenant B. When tenant A searches, that category and its count must not appear.

## 32. Aggregations Do Not Necessarily Match Hits After post_filter

Elasticsearch has `post_filter`. It filters hits after aggregations have already been computed, so aggregations can reflect a broader document set than the returned hits.

This is useful in faceted navigation: hits apply every selected filter, while certain facets are computed over a broader set so users still see alternative options. However, it is also a source of confusion when the application expects aggregations to reflect only returned hits.

For example, a root query filtering `status = ACTIVE` and a `post_filter` on `category = keyboard` leaves only keyboards in hits while the `category` aggregation still counts all `ACTIVE` products.

Tests must verify the intended semantics:

- If aggregations must match the exact hit set, put filters in `query`.
- If facets intentionally ignore a filter, use `post_filter` deliberately and assert the results.
- Never use `post_filter` for tenant isolation; tenant boundaries must live in the root `query`.

## 33. Reading Aggregations in Spring Data Elasticsearch

When using `ElasticsearchOperations`, search returns `SearchHits<T>`. Aggregation metadata can be accessed via `getAggregations()` and the version's container type.

Skeleton example:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

AggregationsContainer<?> container = hits.getAggregations();

if (container != null) {
    Object aggregations = container.aggregations();
    // Convert or read aggregations according to implementation/version.
}
~~~

With the Elasticsearch Java API Client, aggregation responses provide corresponding typed objects. You can inspect them directly when fine-grained control is needed.

Do not cast aggregation containers blindly. Check the concrete implementation and declared aggregation names. Extract response conversion into a small mapper/service so controllers do not contain aggregation parsing logic.

When aggregations are a core API feature, define clean DTOs:

~~~java
public record CategoryCount(
        String category,
        long count
) {
}

public record ProductSearchSummary(
        List<CategoryCount> categories,
        double averagePrice,
        long totalHits
) {
}
~~~

DTOs avoid leaking Elasticsearch's internal aggregation objects to clients and keep application APIs stable across library upgrades.

## 34. NativeQuery in Spring Data Elasticsearch

With Spring Data Elasticsearch backed by the Elasticsearch Java API Client, `NativeQuery` lets you configure advanced query DSL. An illustrative example for search, sort, pageable, and aggregation:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("ACTIVE")
                ))
                .must(m -> m.multiMatch(mm -> mm
                        .query("keyboard")
                        .fields("name", "description")
                ))
        ))
        .withPageable(PageRequest.of(0, 20))
        .withSort(SortOptions.of(s -> s.field(f -> f
                .field("price")
                .order(SortOrder.Asc)
        )))
        .withAggregation(
                "by_category",
                Aggregation.of(a -> a.terms(t -> t
                        .field("category")
                        .size(10)
                ))
        )
        .build();
~~~

This is an illustrative skeleton for the `NativeQuery`/Java API Client API. Imports, builder overloads, highlight setup, and aggregation response types vary by version. In your project, use the exact API provided by your managed dependencies.

Multi-field sorting can be configured by adding multiple `SortOptions` via the corresponding API. For complex queries, build small helpers for each part: query filters, sort options, highlight queries, and aggregations. That allows testing each piece independently without duplicating the whole request builder.

## 35. Configuring Highlights in NativeQuery

Spring Data Elasticsearch provides abstractions for highlight queries. Some versions use `HighlightQuery` combined with `Highlight`/`HighlightField` objects; exact constructors and builders may vary.

Semantically, the configuration must specify:

- Fields to highlight.
- Pre/post tags.
- Fragment size.
- Number of fragments.
- Highlighter type if needed.

Equivalent REST DSL:

~~~json
{
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "name": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

If Java abstractions lack an option you need, use `NativeQuery`/Java API Client at an appropriate layer. Avoid mixing part of a query via abstractions and part via raw JSON in ways that bypass mapping or escaping controls.

## 36. Testing Sorting in Repositories and Operations

For repository methods supporting `Pageable`, you can test sorting via `PageRequest`:

~~~java
@Test
void returnsProductsSortedByPriceAscending() {
    Pageable pageable = PageRequest.of(
            0,
            10,
            Sort.by(
                    Sort.Order.asc("price"),
                    Sort.Order.asc("productId")
            )
    );

    Page<Product> result =
            repository.findByStatus("ACTIVE", pageable);

    assertThat(result.getContent())
            .extracting(Product::getPrice)
            .isSorted();
}
~~~

When a tie-breaker is present, test `productId` order specifically among products sharing the same price. Asserting on an already-sorted price list does not prove the secondary sort criterion works.

With `NativeQuery`, inspect `SearchHit` `sortValues` or the returned ID order. Where possible, construct the test request and confirm sort options are actually sent.

## 37. Testing Highlights

A highlight test requires fixtures containing keywords in the target field:

~~~java
@Test
void highlightsMatchingDescription() {
    SearchHits<Product> hits = operations.search(
            queryWithDescriptionHighlight("wireless"),
            Product.class
    );

    SearchHit<Product> hit = hits.getSearchHit(0);

    assertThat(hit.getHighlightField("description"))
            .isNotEmpty()
            .anySatisfy(fragment ->
                    assertThat(fragment).contains("<mark>wireless</mark>")
            );
}
~~~

This is an illustrative example; hit accessors and query setup must match your version's API.

Tests should confirm:

- Fragments contain the queried term.
- Pre/post tags match expectations.
- The intended fields are highlighted.
- Fragment count does not exceed configuration.
- Unconfigured fields are not highlighted when `require_field_match` or query semantics forbid it.
- The source document is unchanged after searching.
- Response DTOs separate highlights from the entity.

Do not assert the entire fragment character-for-character if the highlighter may shift fragment boundaries across analyzers or versions. Asserting stable properties like field, term, and count is more resilient.

## 38. Testing Aggregations

With a small fixture, you can assert exact bucket counts and metric values:

~~~java
@Test
void aggregatesProductsByCategory() {
    ProductSearchSummary summary = searchService.categorySummary();

    assertThat(summary.categories())
            .contains(
                    new CategoryCount("keyboard", 5),
                    new CategoryCount("mouse", 3)
            );
}
~~~

Tests must seed the expected document count, ensure refresh, and apply matching query filters. If multiple test cases share an index, delete data or use separate index namespaces so stale data does not skew counts.

For histograms/ranges, test boundary values. For cardinality, remember it can be approximate. For composite aggregations, test the full `after_key` loop.

## 39. Integration Testing All Four Features Together

An end-to-end integration test should model real UI requirements:

- Query finds `ACTIVE` products matching a keyword.
- Sort by price ascending, then `productId` ascending.
- Pagination of 10 items per page.
- Highlight `name` and `description`.
- Aggregate by `category` and `brand`.
- Total hits reflects only the filtered query set.
- No out-of-condition documents appear.

Scenario:

1. Create 25 fixture products with known categories and brands.
2. Include at least three products sharing the same price to exercise the tie-breaker.
3. Include a product containing the keyword in `name` and one containing it only in `description`.
4. Include `INACTIVE` products to verify filtering.
5. Create the index with an explicit mapping.
6. Index fixtures and refresh.
7. Search page one.
8. Verify 10 hits and sort order.
9. Verify highlight fragments.
10. Verify `category`/`brand` bucket counts.
11. Fetch pages two and three.
12. Collect all IDs and confirm no duplicates or missing items.
13. Verify total hits and total pages.

Combined tests catch bugs that isolated tests miss—such as a query filter applied to hits but omitted from aggregations, or a `Pageable` overriding sort options.

## 40. Testcontainers and Test Index Management

Use Testcontainers to run Elasticsearch compatible with your application's Spring Data Elasticsearch version. Test configuration should:

- Choose a compatible image/version.
- Start the cluster before creating the client.
- Create indices with explicit mappings/settings.
- Use dedicated test index names or clean data between tests.
- Wait for refresh or use an appropriate refresh policy.
- Close clients/containers according to lifecycle.
- Avoid concurrent tests on the same index if shared fixtures can collide.

If running tests in parallel, create uniquely named indices per test class or test run. Avoid order-dependent tests.

## 41. Common Errors When Combining Sorting, Pagination, Highlighting, and Aggregations

| Symptom | Possible cause | Resolution |
|---|---|---|
| Name sort fails | Sorting on a `text` field | Use a `keyword` multi-field |
| Price 100 comes before 20 | `price` mapped as `keyword` | Use a numeric mapping |
| Order changes across runs | Tied sort values without tie-breaker | Add a unique `keyword` field |
| Duplicate or missing hits across pages | Offset pagination on mutating data or unstable sort | Add tie-breaker; use PIT + `search_after` |
| Deep page rejected | `from + size` exceeds `max_result_window` | Use `search_after`/PIT |
| Last page missing or extra items | Wrong total/page math or stale fixtures | Check total hits, refresh, and test boundaries |
| Empty highlights | Field did not match, wrong mapping, or highlighter config | Check query, field, and analyzer |
| Highlights missing from entity | Reading source instead of `SearchHit` metadata | Read `highlightFields` and map to DTO |
| Snippet contains unsafe HTML | Rendering fragments directly | Escape/sanitize per frontend policy |
| Aggregations count more than hits | `query` and `post_filter` have different semantics | Clarify which dataset aggregations target |
| Terms buckets missing categories | Terms `size` too small | Increase `size` carefully or use `composite` |
| Bucket counts not exact | Distributed terms aggregation error | Inspect `shard_size`/error bound or pick a suitable approach |
| Wrong average price | Aggregation lacks the same filter | Put filter in `query` or appropriate bucket |
| Composite buckets repeat | Not sending returned `after_key` or changing `sources` | Preserve `sources` and `after_key` |
| Flaky tests | Non-deterministic fixtures, refresh, or sorting | Explicit mapping, refresh, and tie-breaker |

## 42. Testing Checklist

**Mapping and sorting**

- Sort fields have the right mapping type.
- Text sorting uses a `keyword` multi-field.
- Numeric sorting is numeric, not lexicographical.
- Missing values have an explicit rule.
- Multi-valued fields specify an appropriate sort `mode`.
- Nested sorting specifies the right `path` and `filter`.
- Multi-field sorting follows the intended precedence order.
- A unique tie-breaker is present.

**Pagination**

- First, middle, and last pages have the right sizes.
- Total hits and total pages are right.
- No duplicate IDs appear across pages on a fixed dataset.
- No IDs are lost across all pages.
- Deep pagination uses an appropriate strategy.
- `search_after` preserves all sort values.
- PIT is opened, reused, and closed cleanly if snapshot consistency is required.

**Highlighting**

- The intended fields are highlighted.
- Fragments contain matching terms.
- Pre/post tags match configuration.
- Fragment size and count match configuration.
- Source entity is not modified.
- Response does not leak sensitive fields.
- Rendered content is handled safely.

**Aggregations**

- Query filters apply to aggregations.
- Bucket keys and `doc_count` match expectations.
- Metrics match fixtures.
- Range boundaries are tested.
- Date histogram timezone is explicit.
- Cardinality is treated as an estimate when appropriate.
- Terms `size` and `shard_size` are chosen deliberately.
- Composite `after_key` neither duplicates nor skips buckets.

**Integration**

- Test both repository and Operations/`NativeQuery` paths actually used.
- Test indices are created with explicit mappings.
- Fixtures are refreshed before searching.
- Test requests combining sort, pagination, highlighting, and aggregations together.
- Never rely solely on mocks to prove real Query DSL behavior.

## 43. Design Principles

Sorting, pagination, highlighting, and aggregations are distinct parts of a search response that must be tested as a unified contract:

- Sorting needs right mappings and deterministic ordering.
- Pagination needs a stable tie-breaker; mutating data may require PIT and `search_after`.
- Highlights live in hit metadata, should be kept separate from entities, and rendered safely.
- Aggregations follow `query`/filter semantics; never assume they always match hits after `post_filter`.
- Search `size` and terms aggregation `size` are two distinct limits.
- Terms aggregations return top buckets; `composite` suits iterating across many buckets.
- Tests need fixtures with ties, boundaries, and known distributions.
- Integration tests must verify real Elasticsearch behavior against your project's mappings.
- When combining all four features, assert hit IDs, sort order, page boundaries, fragments, and bucket counts within the same request.

A reliable search feature does more than return the right product list. It maintains stable ordering, paginates without duplicates or omissions under its chosen semantics, highlights matching text accurately, and computes aggregations over the right document set. Spring Data Elasticsearch supplies abstractions to build requests and read `SearchHits`, while Elasticsearch determines final semantics from mappings and Query DSL. Combining query-builder unit tests with integration tests backed by real mappings and data—and exercising all four features in a complete search request—ensures the search contract holds end to end.
