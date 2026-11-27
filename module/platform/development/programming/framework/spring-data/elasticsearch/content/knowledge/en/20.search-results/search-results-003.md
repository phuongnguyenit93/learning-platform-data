# Reading _score, Sort Values, Index Name, and Result Identifiers

When searching with Elasticsearch, results are not just a list of documents. Each result also carries metadata that helps the application understand why the document was returned, its sort order, which index it resides in, and what its identifier is.

In Spring Data Elasticsearch, this metadata is provided via `SearchHit<T>` and `SearchHits<T>`. When working directly with the Java API Client, the corresponding information resides inside each hit of `SearchResponse<T>`.

Four pieces of information to read accurately:

- **`_score`**: relevance score calculated by Elasticsearch for the result when the query involves scoring.
- **Sort values**: the actual values used to sort a hit, which can also serve as a cursor for `search_after`.
- **Index name (`_index`)**: the physical index containing the returned document.
- **Document ID (`_id`)**: the document identifier within that index.

This metadata is useful when building search result pages, explaining ordering, performing deep pagination, handling index versioning, and creating links to specific documents.

## 1. SearchHit and SearchHits in Spring Data Elasticsearch

When calling `ElasticsearchOperations.search(...)`, Spring Data Elasticsearch typically returns `SearchHits<T>` rather than just a list of entities.

The two types serve different roles:

| Type | Role |
|---|---|
| `SearchHit<T>` | Represents a single result, consisting of the entity and the hit's metadata |
| `SearchHits<T>` | Wraps the entire search result and response-level metadata |

Example:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    String index = hit.getIndex();
    float score = hit.getScore();
    List<Object> sortValues = hit.getSortValues();
}
~~~

A `SearchHit<T>` typically provides:

- `getContent()`: entity converted from the document by Spring Data.
- `getId()`: document ID, corresponding to `_id` metadata.
- `getIndex()`: name of the index containing the document.
- `getScore()`: relevance score `_score` of the hit.
- `getSortValues()`: list of sort values in the order of the sort clauses.
- Other metadata such as highlights or explanation when the response and query request them.

`SearchHits<T>` provides result-set level information, such as total hits, max score, hit list, and aggregations if present.

Do not simply call `getContent()` and discard the entire `SearchHit` if the UI needs to display relevance scores, source index, identifiers, or support pagination via sort values.

## 2. What Is _score?

`_score` is the relevance score that Elasticsearch computes for a document against the current query. With full-text search queries like `match`, this score helps rank documents by how well they match the keywords and relevant factors in the scoring algorithm.

Example:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

A result might look like:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 3.82,
  "_source": {
    "name": "Wireless Mechanical Keyboard"
  }
}
~~~

Where:

- `_score: 3.82` is the hit's relevance score for this query.
- Higher scores generally indicate a better match within the same query context.
- The score is not a percentage, probability, or absolute quality rating.

### Where Does _score Come From?

For full-text search, Elasticsearch typically uses the BM25 algorithm as its default similarity. The score can depend on:

- Term matching between the query and document.
- Term frequency in the document.
- Term rarity across the document collection.
- Field length relative to average field length.
- Query structure, boosts, and configured scoring functions.

Because the score depends on both the query and the data in the index, you should not directly compare `_score` values across two different queries as if they share the same scale.

### When Is Score Not Meaningful for Ranking?

Not every query needs scoring:

- `term` inside `filter` restricts results without calculating a relevance score.
- `exists` inside `filter` only checks whether a field has indexed values.
- Filter-only queries do not use relevance scores to determine order.
- `match_all` may return the same score for all documents, so the score does not distinguish relevance.

If a query has scoring but the request sorts by a field such as price or date, result order is determined by the sort field. Elasticsearch may skip computing scores when sorting by a field unless score tracking is requested.

### Keeping Scores When Sorting by a Field

The Search request supports `track_scores`. When enabled, Elasticsearch still computes and returns scores even though results are sorted by a field.

Request example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

Results are sorted by ascending price, while scores are still computed and returned so the application can display or analyze them. Enabling `track_scores` adds computation cost; use it only when the application actually needs scores alongside field sorting.

## 3. Reading Score with SearchHit

Service example:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void printResults(Query query) {
        SearchHits<ProductDocument> results =
                operations.search(query, ProductDocument.class);

        for (SearchHit<ProductDocument> hit : results) {
            ProductDocument product = hit.getContent();

            System.out.println("Name: " + product.getName());
            System.out.println("Score: " + hit.getScore());
        }
    }
}
~~~

`getScore()` reads the score returned for each hit. If the query or sorting approach does not require scoring, do not assume the score is a useful ranking signal. Verify whether the query involves scoring and whether score tracking is enabled when sorting by a field.

At the API layer, decide whether to return scores to the client. Often, scores are useful for debugging, relevance tuning, or specialized UIs; most business APIs do not need to expose this score publicly as a quality metric.

## 4. What Are Sort Values?

When the Search API sorts results, each hit can contain a `sort` array in the response. These are the actual values of each sort clause for that document.

Request example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "createdAt": {
        "order": "desc"
      }
    }
  ]
}
~~~

A hit might return:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 1.74,
  "sort": [
    1299000,
    "2026-10-20T08:30:00.000Z"
  ],
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000,
    "createdAt": "2026-10-20T08:30:00.000Z"
  }
}
~~~

The sort array has two elements because the request has two sort clauses:

1. `1299000` is the value of the `price` field.
2. `"2026-10-20T08:30:00.000Z"` is the value of the `createdAt` field.

The order in the array must match the order of the request's sort clauses. Data types are also preserved according to the sort value type: number, string, or the corresponding type returned by Elasticsearch.

Sort values are neither the full entity data nor a list of field names. They are the values used to determine the hit's position in the result ordering.

### Reading Sort Values with Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    List<Object> values = hit.getSortValues();

    System.out.println("Sort values: " + values);
}
~~~

If sorting by `price` then `createdAt`, the sort values list follows the corresponding order. When these values are needed for subsequent pagination, preserve the entire list and its order; do not convert every value into a string yourself.

## 5. Using Sort Values for search_after

For standard pagination, applications can use `from` and `size`. However, when going deep into many pages, `from/size` becomes increasingly expensive because Elasticsearch must process and retain results prior to the target position.

`search_after` allows continuing from the sort values of the last hit on the previous page.

First page example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 2,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ]
}
~~~

Suppose the last hit of the first page has sort values:

~~~json
"sort": [1299000, "P-1002"]
~~~

The next page request passes that exact array into `search_after`:

~~~http
POST /products/_search
Content-Type: application/json

{
  "size": 2,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [1299000, "P-1002"]
}
~~~

The next request must keep the same query and sort order. Elasticsearch returns hits appearing after the position indicated by the sort values.

### Why Is a Stable Sort Order Needed?

If you sort only by `price`, many documents may have the same price. In that case, the order among equal-priced documents can be unstable across requests, causing paginated results to duplicate or skip items.

Add a unique tie-breaker field, such as `productId` of type `keyword` with doc values:

~~~json
{
  "mappings": {
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

You should not sort directly on `_id` metadata like a regular field. `_id` is not designed for sorting/aggregating the way a `keyword` field with doc values is. If a business tie-breaker is needed, store that ID additionally in a dedicated `keyword` field such as `productId`.

For stable pagination across multiple requests while data may change, consider Point in Time (PIT) combined with `search_after`. PIT maintains a consistent view of the index for a specified duration; Elasticsearch can use `_shard_doc` as an internal tie-breaker when searching through a PIT.

## 6. Sort Fields Must Have Appropriate Mappings

Not every field can be sorted efficiently.

| Field type | Sortable | Notes |
|---|---|---|
| `keyword` | Yes | Suitable for codes, statuses, names requiring sorting |
| Numeric (`integer`, `long`, `double`) | Yes | Suitable for price, quantity, score |
| `date` | Yes | Suitable for creation date, update date |
| `text` | Not suitable by default | Usually uses a `keyword` subfield for sorting |
| `object` | Not directly sortable as a scalar | Must select a child field |
| `nested` | Requires nested sort configuration | Must specify the nested path |

Entity example with multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Full-text search uses `name`; sorting by name uses `name.keyword`.

If a field has multiple values, sorting may need a `mode` such as `min`, `max`, `avg`, or `median` depending on data type and requirements. For nested objects, declare a nested sort so Elasticsearch knows which child values to use.

### Handling Documents Missing a Sort Value

Sorting supports the `missing` option to place documents missing a value first or last:

~~~json
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

`missing: "_last"` only determines the position of documents missing the value in the ordering. It does not exclude those documents from results. If you only want documents that have a price, add an `exists` filter to the query.

## 7. Index Name in Search Results

Each hit has `_index` metadata, indicating the actual index containing the document.

Example of an application searching via an alias:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Suppose the `products` alias points to two indices:

- `products-v1`
- `products-v2`

The response may contain hits from both indices. Each hit returns `_index` corresponding to the physical index holding the document, for example:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_source": {
    "name": "Wireless Keyboard"
  }
}
~~~

The alias name is the request target. The `_index` value in the hit indicates the specific index from which the document was read.

This is important when:

- An alias points to multiple indices during a migration phase.
- You need to trace which index version holds the data.
- You need to build a link to the document or perform follow-up operations.
- You need to analyze whether results come from a historical index or the current index.

### Reading Index Name in Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String actualIndex = hit.getIndex();
    System.out.println("Index: " + actualIndex);
}
~~~

`getIndex()` tells you the source index of the hit. If the application only searches a single fixed index, this value usually matches the target index. When searching across an alias or multi-index wildcard, hits may come from different physical indices.

## 8. Document ID in Results

`_id` is a document identifier within the scope of a single index. It is not automatically unique across the entire cluster.

Example:

| Index | _id | Meaning |
|---|---|---|
| `products-v1` | `P-1001` | Document in index v1 |
| `products-v2` | `P-1001` | Different document in index v2 |
| `orders` | `P-1001` | Document in the orders index |

The same ID can exist in multiple indices. Therefore, when you need to uniquely identify a hit in a multi-index search result, treat the pair **(`_index`, `_id`)** as the location identifier of the document.

### Reading ID with Spring Data

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String documentId = hit.getId();
    ProductDocument product = hit.getContent();

    System.out.println("ID: " + documentId);
    System.out.println("Product name: " + product.getName());
}
~~~

The ID obtained from `SearchHit.getId()` is document ID metadata. It does not necessarily have to be read from a field in `_source`.

### Relation to @Id in an Entity

Spring Data Elasticsearch uses the annotation:

~~~java
import org.springframework.data.annotation.Id;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;
}
~~~

`@Id` maps the Java `id` property to `_id` metadata. Whether a document is indexed with an application-assigned ID or an Elasticsearch-generated ID, Spring Data can populate the identifier value into the entity according to mapping metadata.

If the application has a separate business key such as `sku`, clearly distinguish the business key from the document ID. `sku` is a business field with its own mapping; `_id` is document identity metadata.

### When Retrieving the Document Subsequently by ID

If you already have a hit and want to read the document directly, you need the exact index and ID. With custom routing, a Get operation also needs the same routing value used when indexing the document.

Do not keep only the ID if results can come from multiple indices. ID `P-1001` in `products-v1` is different from the same ID in `products-v2`.

## 9. Reading Score, Sort Values, Index, and ID Together

Example service extracting metadata for each result:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductResultService {

    private final ElasticsearchOperations operations;

    public ProductResultService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void printMetadata(Query query) {
        SearchHits<ProductDocument> results =
                operations.search(query, ProductDocument.class);

        System.out.println("Total hits: " + results.getTotalHits());
        System.out.println("Max score: " + results.getMaxScore());

        for (SearchHit<ProductDocument> hit : results) {
            String id = hit.getId();
            String index = hit.getIndex();
            float score = hit.getScore();
            List<Object> sortValues = hit.getSortValues();

            ProductDocument content = hit.getContent();

            System.out.println("ID: " + id);
            System.out.println("Index: " + index);
            System.out.println("Score: " + score);
            System.out.println("Sort values: " + sortValues);
            System.out.println("Name: " + content.getName());
        }
    }
}
~~~

The example illustrates how to read metadata from `SearchHits`. Query and entity types need to be imported according to your project; when using `NativeQuery`, the inner query type is the Elasticsearch Java Client `Query`, while the operations parameter is Spring Data's `Query` abstraction.

If the response has no sort clauses, the sort values list may be empty. If there is no scoring, the score should not be treated as a ranking signal. Always interpret metadata in the context of the request that produced it.

## 10. Building NativeQuery with Sort

With Spring Data Elasticsearch 5.x, Query DSL can be constructed using the Elasticsearch Java API Client and wrapped in `NativeQuery`.

Example searching by name and sorting by ascending price, then by product ID:

~~~java
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.domain.PageRequest;

Query query = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(query)
        .withSort(
                SortOptions.of(s -> s.field(f -> f
                        .field("price")
                        .order(SortOrder.Asc)
                )),
                SortOptions.of(s -> s.field(f -> f
                        .field("productId")
                        .order(SortOrder.Asc)
                ))
        )
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

In the example, `price` and `productId` are the two sort clauses. The order of sort values on each hit will correspond to price and product ID, respectively.

If you need to read scores while sorting by a field, enable track scores via the appropriate builder API of the Spring Data Elasticsearch version in use, or set `track_scores: true` in the search request. Do not assume scores are always computed when sorting by a field.

## 11. Using Sort Values for Deep Pagination

`SearchHit.getSortValues()` provides the values for the application to store the cursor for the next page.

In terms of the request, the next page looks like:

~~~json
{
  "size": 20,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "search_after": [1299000, "P-1002"]
}
~~~

In Spring Data, you can obtain the sort values from the last hit:

~~~java
SearchHit<ProductDocument> lastHit =
        hits.getSearchHits().get(hits.getSearchHits().size() - 1);

List<Object> nextSearchAfter = lastHit.getSortValues();
~~~

Then pass `nextSearchAfter` into the `search_after` mechanism of the query builder/API corresponding to the version in use. `NativeQuery` and `search_after`-supporting APIs can vary by version; verify against the exact project dependency.

Required principles:

- Keep the query identical across pages.
- Preserve the exact order and data types of sort values.
- Use a stable sort order with a unique tie-breaker.
- For continuously changing data, consider PIT to maintain a consistent snapshot.
- Do not reconstruct sort values from the entity if the response already provides the exact values.

Do not use a large `from` to simulate `search_after`. `search_after` is designed for deep pagination and avoids skipping large numbers of hits from previous pages.

## 12. Difference Between Hit Metadata and _source Data

A hit can contain both metadata and source:

~~~json
{
  "_index": "products-v2",
  "_id": "P-1001",
  "_score": 2.17,
  "sort": [1299000, "P-1001"],
  "_source": {
    "productId": "P-1001",
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

Distinction:

| Component | Source | Purpose |
|---|---|---|
| `_index` | Hit metadata | Physical index containing the document |
| `_id` | Hit metadata | Document ID |
| `_score` | Hit metadata | Relevance score |
| `sort` | Hit metadata | Values used for sorting and `search_after` |
| `_source` | Document content | Entity/document data |

A `productId` property inside `_source` may have the same value as `_id`, but the two values serve different roles. If source filtering removes the `productId` field, `_id` metadata can still be returned.

Conversely, if a request disables or filters source, the application may not have enough fields to build a complete entity, yet can still read hit metadata.

## 13. Using Metadata When Searching Across an Alias or Multiple Indices

An alias can point to one or more indices. Example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

If the `products` alias points to `products-v1` and `products-v2`, results may contain documents from both places.

The application should retain metadata:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    String sourceIndex = hit.getIndex();
    String documentId = hit.getId();

    // Record the index + id pair to trace the result.
}
~~~

This is especially important when:

- The same document ID exists in multiple indices.
- Mapping versions are being transitioned.
- You need to know which documents come from a historical index.
- Duplicate results need to be handled at the application layer.

If two indices both contain a product, Elasticsearch can return two separate hits. An alias does not automatically merge documents with duplicate IDs across indices. If deduplication by business key is needed, the application needs an explicit merging rule.

## 14. Common Pitfalls

### Treating _score as a Match Percentage

Score is an internal ranking value based on the query and index data. Do not display `0.82 = 82% match` without a dedicated calibration model.

### Comparing Scores Across Two Different Queries

Changing the query, analyzer, corpus, or index can change the scoring scale. Do not use scores from two independent requests to conclude which document is absolutely better.

### Sorting by Field While Expecting Score to Be Returned

When sorting by a field, score might not be computed unless track scores is enabled. If the UI needs both field sorting and scores, configure `track_scores`.

### Forgetting a Tie-Breaker When Using search_after

Multiple documents can have the same price or date. Add a unique keyword field at the end of the sort for a stable order.

### Using _id as a Sort Field

`_id` is identity metadata and is not a field with doc values for sorting/aggregating like a regular keyword field. Store a copy of the ID in a keyword field if business sorting or tie-breaking is needed.

### Storing Only ID and Omitting Index Name

When searching across multiple indices, the same ID can appear in multiple places. Keep the index and ID pair when precise result identification is needed.

### Confusing Alias with Returned Index Name

The request may use the `products` alias, while hit metadata reports the physical index such as `products-v2`. These are two different concepts.

### Reconstructing Sort Values from Source

Sort values may have been normalized or processed according to mapping, missing policy, nested sort, or multi-value mode. Use `getSortValues()` from the hit as the `search_after` cursor.

### Failing to Keep Sort Identical Across Pages

`search_after` requires the same sort order and query. Changing the sort or value types can break pagination.

## 15. Workflow for Using Result Metadata

When building a search API or UI:

1. Choose a query and sort suited to the search goal.
2. Decide whether to display scores or only use scores for debugging.
3. If sorting by a field while still needing scores, enable track scores.
4. Read the entity via `SearchHit.getContent()`.
5. Read the identifier via `getId()` and the source index via `getIndex()`.
6. Read sort values via `getSortValues()` when `search_after` is needed.
7. Use fields with sort-supporting mappings; do not sort directly on `text` or `_id` metadata.
8. Add a unique tie-breaker for a stable order.
9. For deep pagination or changing data, use `search_after` combined with PIT.
10. When querying through a multi-index alias, retain index + ID for traceability.
11. Return only necessary metadata in the API response; do not expose all Elasticsearch internals to clients.
12. Verify actual mappings, queries, and responses before relying on metadata in business logic.

## Conclusion

`SearchHit<T>` holds the entity along with each result's metadata: score, sort values, index name, and document ID. `_score` reflects relevance within the query context; sort values record sorting values and support `search_after`; `_index` identifies the physical index holding the hit; `_id` identifies the document in that index. In Spring Data Elasticsearch, retain `SearchHit` when metadata is needed, use sorting with a stable tie-breaker, and treat the index + ID pair as the result's location identifier when searching across multiple indices.
