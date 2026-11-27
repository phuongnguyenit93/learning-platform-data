# Distinguishing Document Content and SearchHit Metadata

When searching with Spring Data Elasticsearch, a result does not contain only the document's data. Elasticsearch also returns information describing the matched hit, such as the index containing the document, ID, relevance score, sort values, highlights, and related nested hits.

Spring Data Elasticsearch separates the data mapped into an entity from the search result metadata. The entity represents the document content; `SearchHit<T>` wraps that entity along with the metadata of a single hit; `SearchHits<T>` contains the list of hits and metadata at the level of the entire search response.

Distinguishing these layers helps the application avoid confusing `_score` with a document field, losing highlights when converting results to DTOs, accidentally writing metadata into `_source`, and knowing when to use `SearchHit<T>` instead of only retrieving `T`.

## 1. A Search Result Has Multiple Layers of Information

Suppose Elasticsearch returns a hit with a simplified structure:

~~~json
{
  "_index": "catalog-products-v3",
  "_id": "product-1001",
  "_score": 4.82,
  "_source": {
    "sku": "KB-1042",
    "name": "Mechanical Keyboard",
    "price": 129.5,
    "category": "accessories"
  },
  "sort": [
    129.5,
    "product-1001"
  ],
  "highlight": {
    "name": [
      "Mechanical <em>Keyboard</em>"
    ]
  }
}
~~~

The response has two main groups of information:

| Elasticsearch response part | Meaning | How Spring Data typically represents it |
| --- | --- | --- |
| _source | Stored document content | SearchHit<T>.getContent() after mapping |
| _id | Document ID in the index | SearchHit<T>.getId() and can be mapped into an @Id property |
| _index | Physical index returning the hit | SearchHit<T>.getIndex() |
| _score | Relevance score of the hit | SearchHit<T>.getScore() |
| sort | Values used to sort the hit | SearchHit<T>.getSortValues() |
| highlight | Highlighted text snippets | SearchHit<T>.getHighlightFields() |
| inner_hits | Child hits from nested or parent/child queries | SearchHit<T>.getInnerHits() |
| matched_queries | Names of matched named queries | SearchHit<T> metadata if the query uses named queries |

The `_source` part is business data. Fields such as `_score`, `sort`, and `highlight` describe the result of a specific search execution. They do not automatically become fields of the stored document.

## 2. Distinguishing Document, Entity, and SearchHit

In Spring Data Elasticsearch, the word “document” can refer to the JSON content stored in Elasticsearch or the Spring Data `Document` type.

### 2.1. Document Is the Storage Data Structure

`org.springframework.data.elasticsearch.core.document.Document` is a Map-like document representation that Spring Data uses in mapping APIs and low-level operations. It contains field name and value pairs corresponding to the document content.

Example of document content:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

Document document = Document.create();
document.put("sku", "KB-1042");
document.put("name", "Mechanical Keyboard");
document.put("price", 129.5);
~~~

This is the data corresponding to the document content. It is not the entire search response and does not carry meanings such as relevance score, highlights, or sort values.

### 2.2. Entity Is the Java Model of Document Content

Spring Data uses mapping metadata and `MappingElasticsearchConverter` to convert between a Java entity and the document representation:

~~~text
                 On write
Entity Java  ----------------->  Document / _source
                 Converter

                 On read
Entity Java  <-----------------  Document / _source
                 Converter
~~~

Example:

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private double price;

    // Constructors, getters, and setters
}
~~~

The `ProductDocument` entity describes the data the application wants to read/write. Annotations such as `@Id`, `@Field`, `@Transient`, and custom conversions affect how Spring Data maps the entity.

### 2.3. SearchHit Is a Single Search Result

`SearchHit<T>` wraps the content mapped into type `T` along with the metadata attached to that hit:

~~~text
SearchHit<ProductDocument>
├── content: ProductDocument
├── id: product-1001
├── index: catalog-products-v3
├── score: 4.82
├── sortValues: [129.5, product-1001]
├── highlightFields
└── innerHits
~~~

Therefore, `SearchHit<ProductDocument>` is neither another entity nor a copy of `_source`. It is a search result wrapper.

### 2.4. SearchHits Is the Entire Result Set

`SearchHits<T>` contains multiple `SearchHit<T>` instances along with response-level information:

~~~text
SearchHits<ProductDocument>
├── totalHits
├── maxScore
├── executionDuration
├── aggregations
├── suggest
└── searchHits
    ├── SearchHit<ProductDocument>
    ├── SearchHit<ProductDocument>
    └── SearchHit<ProductDocument>
~~~

`SearchHits<T>` answers questions about the entire search execution: how many hits there are, what the highest score is, whether there are aggregation or suggest results, and what the individual hits are.

## 3. SearchHit<T>: Content and Metadata of Each Hit

Commonly used members of `SearchHit<T>`:

| Method | Meaning |
| --- | --- |
| getContent() | Entity or projection mapped from the document content |
| getId() | Elasticsearch document ID |
| getIndex() | Elasticsearch index name returned for the hit |
| getScore() | Relevance score of the hit |
| getSortValues() | List of sort values in the order of the sort clauses |
| getHighlightFields() | Map from field name to highlight snippets |
| getInnerHits() | Nested/child hit groups by name |
| getMatchedQueries() | Names of matched named queries, if any |
| getExplanation() | Score explanation information when the request enables explain and the API version provides it |

Detailed APIs may vary depending on the Spring Data Elasticsearch version. When using less common properties, check the Javadoc of the actual dependency.

### 3.1. Retrieving Content and Metadata

Example of performing a search via `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );

for (SearchHit<ProductDocument> hit : results.getSearchHits()) {
    ProductDocument product = hit.getContent();

    String documentId = hit.getId();
    String indexName = hit.getIndex();
    float score = hit.getScore();

    // Process entity content and hit metadata according to their respective purposes.
}
~~~

If only business data is needed, use `getContent()`. If ID, relevance score, highlights, or sort values are needed, keep `SearchHit<T>` until the required metadata has been extracted.

### 3.2. Hit ID and the @Id Property

Elasticsearch has a `_id` metadata field outside `_source`. Spring Data uses the `@Id` annotation to link the entity's ID property with the Elasticsearch document ID.

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
}
~~~

`hit.getId()` reads the ID from the hit metadata. `hit.getContent().getId()` reads the ID property after Spring Data maps the metadata into the entity. With a properly mapped entity, these two values usually correspond.

You should not assume the ID must necessarily appear inside `_source`. In standard mapping, `@Id` is used as the document ID; it is not a regular source field. If the business logic needs to store an additional identifier inside the document content, declare a separate field, such as `sku`.

### 3.3. Hit Index and the Alias Name Used by the Application

The application may search through an alias such as `catalog-products`, while Elasticsearch returns `_index` as the physical index holding the document, for example `catalog-products-v3`.

This is useful when operating versioned indices. You should not treat `hit.getIndex()` as the application's logical alias name; it describes the physical index returned for the hit.

## 4. Score and Result Ordering

`_score` is the relevance score computed by Elasticsearch based on the query and similarity configuration. `SearchHit.getScore()` exposes this value to the application.

### 4.1. Score Is Not a Business Field

For example, a product has `rating = 4.8` and `score = 7.2`:

- `rating` is business data in `_source`.
- `score` is the relevance score of a hit in a specific search execution.

Do not write `score` back to the entity as if it were a rating or a fixed property of the product.

### 4.2. Score Depends on the Query

A document can have different scores when:

- Search keywords change.
- Queries use different `match`, `multi_match`, `phrase`, or `bool` clauses.
- Analyzers or similarities change.
- Boost weights change.
- Scoring conditions differ.

Therefore, scores from two non-equivalent requests should not be compared as a fixed quality metric.

### 4.3. Filter Context and Score

Conditions in `bool.filter` are used to filter without contributing to the relevance score. For example, price ranges and stock status usually reside in `filter`, while a `match` query on product name resides in `must`.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 200
            }
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  }
}
~~~

In this case, the score mainly reflects text matching; `price` and `available` only filter results.

### 4.4. Sort Values Are Not Score

If the query sorts by price:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

Results are ordered by `price`. `getSortValues()` returns the hit's sort values in the order of the sort clauses. This value is not equivalent to `getScore()`.

When paginating deeply with `search_after`, the application often needs to keep the sort values of the last hit on the page as a cursor for the next page. Sorting must be stable and should include a tie-breaker to prevent hits with the same sort value from shifting positions between requests.

## 5. Highlight Fields Are Hit Metadata

Highlighting returns text snippets containing the parts that matched the query, usually with markup tags. Example:

~~~json
{
  "highlight": {
    "name": [
      "Mechanical <em>Keyboard</em>"
    ],
    "description": [
      "A compact <em>keyboard</em> for daily use"
    ]
  }
}
~~~

Spring Data provides highlight fragments via `SearchHit.getHighlightFields()`, usually as a map from field name to a list of fragment strings.

~~~java
for (SearchHit<ProductDocument> hit : results) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments =
        hit.getHighlightFields().get("name");

    // Use fragments to display the matched text.
}
~~~

### 5.1. Highlight Does Not Replace Document Content

The value of `product.getName()` remains the content mapped from `_source`. Highlight is an excerpt generated by Elasticsearch for the current search execution.

Example:

| Source | Value |
| --- | --- |
| Entity name | Mechanical Keyboard |
| Highlight fragment | Mechanical <em>Keyboard</em> |

Highlights can:

- Contain only part of the text rather than the entire field.
- Contain markup or tags configured by the application.
- Have multiple fragments for the same field.
- Be absent if the field is not highlighted or has no suitable matching snippet.

Do not use highlight fragments to overwrite canonical content in the entity or save them back to Elasticsearch.

### 5.2. Protecting When Rendering Highlights

If highlight fragments are rendered on a web UI, clearly specify which tags are allowed to render. You should not assume every string returned from Elasticsearch is safe HTML, especially when the original content is user-supplied.

A safe option is to use fixed highlight tags, escape the original content according to the frontend framework, or convert fragments into a DTO structure consisting of text segments and a matched status.

## 6. Inner Hits Are Also Metadata of the Parent Hit

When a query uses `nested` or parent/child, Elasticsearch can return matching child hits inside `inner_hits`.

Example:

~~~json
{
  "_index": "catalog-products-v3",
  "_id": "product-1001",
  "_source": {
    "sku": "KB-1042",
    "offers": [
      { "seller": "seller-a", "price": 120 },
      { "seller": "seller-b", "price": 95 }
    ]
  },
  "inner_hits": {
    "matching_offers": {
      "hits": {
        "hits": [
          {
            "_nested": {
              "field": "offers",
              "offset": 1
            },
            "_source": {
              "seller": "seller-b",
              "price": 95
            }
          }
        ]
      }
    }
  }
}
~~~

The parent hit still has `ProductDocument` as its content. The `matching_offers` group is extended metadata containing the matching nested hits.

Spring Data exposes these groups through the inner hits map:

~~~java
for (SearchHit<ProductDocument> productHit : results) {
    SearchHits<?> matchingOffers =
        productHit.getInnerHits().get("matching_offers");

    if (matchingOffers == null) {
        continue;
    }

    for (SearchHit<?> offerHit : matchingOffers.getSearchHits()) {
        Object matchedContent = offerHit.getContent();
        // Cast/convert to a type/DTO suitable for the mapping and version.
    }
}
~~~

The map key name must match the name set in `inner_hits.name`. If the query has multiple nested paths or multiple inner hit groups, assign a distinct name to each group to avoid confusion.

Inner hits do not automatically turn the main result into a list of child documents. The application needs to read them from each parent hit.

## 7. SearchHits<T>: Metadata at the Entire Result Level

`SearchHits<T>` represents the search response, not merely a `List<T>`.

Commonly used information:

| Method | Meaning |
| --- | --- |
| getSearchHits() | List of SearchHit<T> |
| getTotalHits() | Total number of hits reported by Elasticsearch |
| getMaxScore() | Highest score in the results |
| getAggregations() | Aggregation results if requested by the query |
| getSuggest() | Suggest results if requested by the query |
| getExecutionDuration() | Execution duration provided by the response |
| getScrollId() / PIT metadata | Information to continue or close certain search contexts, depending on API and version |

Not every search execution has aggregations, suggestions, a scroll ID, or a PIT ID. Check for presence before using them.

### 7.1. Reading Total Hits and Individual Hits

~~~java
SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

long totalHits = results.getTotalHits();
float maxScore = results.getMaxScore();

for (SearchHit<ProductDocument> hit : results) {
    ProductDocument product = hit.getContent();
    // Process each result
}
~~~

`getTotalHits()` is the number of hits reported by Elasticsearch. Depending on the `track_total_hits` configuration and Elasticsearch's counting limit, the total may be a lower bound rather than an exact count. If the UI requires an exact total, configure tracking appropriately and consider the cost.

### 7.2. Aggregations Do Not Reside in Content

An aggregation is an aggregated result over a set of documents, such as product count by category or price histogram. It belongs to `SearchHits`-level metadata and does not automatically appear inside each hit's entity.

Query DSL example:

~~~json
{
  "size": 10,
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

The response has two parts:

- `hits.hits`: list of matching documents.
- `aggregations.categories`: statistical buckets by category.

The application reads the product list via `SearchHit<ProductDocument>` and reads aggregations via `SearchHits.getAggregations()`. The exact aggregation structure depends on the query and the aggregation container of the Spring Data Elasticsearch version.

### 7.3. Suggest Is Not Highlight

Suggest returns proposals such as approximate keywords or completions. Highlight returns text snippets within a document that match the query.

Both features can appear in the same search response but serve different purposes. Suggest is usually read from `SearchHits`-level metadata, while highlight resides on each individual `SearchHit`.

## 8. How SearchHit and SearchHits Differ from List<Entity>

If only document content is needed, results can be converted into a list of entities:

~~~java
List<ProductDocument> products = results.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

After this step, hit metadata such as score, highlights, and sort values are no longer kept alongside the entities in the new list. The original `SearchHits` still retains them, but the `ProductDocument` list does not.

| Result type | Keeps entity content | Keeps per-hit metadata | Keeps response-level metadata |
| --- | --- | --- | --- |
| ProductDocument | Yes | No | No |
| List<ProductDocument> | Yes, multiple entities | No | No |
| SearchHit<ProductDocument> | Yes, one entity | Yes | No |
| SearchHits<ProductDocument> | Yes, via hits | Yes | Yes |

Choose the return type based on your needs:

- CRUD or queries that only need data: an entity or `List<Entity>` is usually sufficient.
- Result pages needing score, highlights, or sort values: keep `SearchHit<Entity>`.
- Search pages needing total hits, aggregations, suggestions, and per-hit metadata: keep `SearchHits<Entity>`.

## 9. Repositories Can Return SearchHit and SearchHits

Spring Data Elasticsearch supports search return types to preserve metadata, depending on the method and module version.

Repository example:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<SearchHit<ProductDocument>> findByName(String name);

    SearchHits<ProductDocument> findByCategory(String category);
}
~~~

With query methods returning `SearchHit<T>` or `SearchHits<T>`, the application can access search metadata. You should verify the supported return types for a specific query method in the Spring Data Elasticsearch version being used.

If precise control over Query DSL, sorting, highlighting, or aggregations is required, using `ElasticsearchOperations.search(...)` with `NativeQuery` is usually clearer than trying to express everything through repository method names.

## 10. SearchPage and Page

Spring Data can convert `SearchHits<T>` into a page type to integrate with Spring Data Commons' pagination abstraction.

`Page<T>` typically contains content, page number, page size, and total elements. If content is entity `T`, per-hit metadata may be lost. For search results that need to retain metadata, `SearchPage<T>` keeps the content as `SearchHit<T>`.

Conceptual example:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.SearchPage;
import org.springframework.data.elasticsearch.core.SearchHitSupport;

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);

SearchPage<ProductDocument> page =
    SearchHitSupport.searchPageFor(hits, pageable);
~~~

`SearchPage<T>` provides pagination alongside search hits. Check the API of your project's version if using page adapters or specific repository return types.

You should not immediately convert `SearchHits<T>` into `Page<T>` if the UI needs score, highlights, or inner hits. Determine which metadata must be preserved in the API contract before unwrapping content.

## 11. Source Filtering and Incomplete Entity Content

Elasticsearch allows limiting the fields returned in `_source`. This reduces network data transfer, but directly affects the entity mapped by Spring Data.

Example fetching only SKU and name:

~~~json
{
  "_source": [
    "sku",
    "name"
  ],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

When Spring Data converts the filtered `_source` into `ProductDocument`, unreturned properties may be `null` or default values. `getContent()` at this point is an entity built from a partial source, not the full original document.

### 11.1. Do Not Arbitrarily Save a Partial Entity Back

Suppose the entity has `sku`, `name`, `price`, and `description`. The query only returns `sku` and `name`. If the application takes the partial entity and calls `repository.save(entity)`, the missing fields may be written as `null` or lose their old values depending on the mapping and update behavior.

To avoid errors:

- Use a dedicated projection/DTO for read-only partial results.
- Do not call `save` on an entity created from source filtering without loading full data.
- If a partial update is needed, use the appropriate partial update API.
- If a full entity is needed, do not exclude fields from `_source`.

### 11.2. Stored Fields and _source

`_source` is the original JSON content stored with the document (if enabled). `stored_fields` are fields explicitly configured to be stored separately for retrieval. The two mechanisms are not the same.

If `_source` is disabled or only partially fetched, mapping a complete entity may not be feasible. When designing an index, clearly define data retrieval requirements and how the application needs to reconstruct entities.

## 12. Converting SearchHit to a Response DTO

You should not directly return `SearchHit<T>` or `SearchHits<T>` from a controller if the public API needs a stable response structure. Spring Data types are persistence/search abstractions, not necessarily a suitable API contract for a frontend.

You can create a DTO that separates the required content and metadata:

~~~java
public record ProductSearchItem(
    String id,
    String sku,
    String name,
    double price,
    float score,
    List<String> nameHighlights
) {}

public record ProductSearchResponse(
    long totalHits,
    List<ProductSearchItem> items
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toSearchItem(
        SearchHit<ProductDocument> hit) {

    ProductDocument product = hit.getContent();

    List<String> highlights = hit.getHighlightFields()
        .getOrDefault("name", List.of());

    return new ProductSearchItem(
        hit.getId(),
        product.getSku(),
        product.getName(),
        product.getPrice(),
        hit.getScore(),
        highlights
    );
}
~~~

Service:

~~~java
public ProductSearchResponse search(NativeQuery query) {
    SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);

    List<ProductSearchItem> items = hits.getSearchHits()
        .stream()
        .map(this::toSearchItem)
        .toList();

    return new ProductSearchResponse(
        hits.getTotalHits(),
        items
    );
}
~~~

The DTO example keeps only the fields the API actually needs. If the API needs sort values, inner hits, or aggregations, design corresponding DTO fields instead of serializing internal Spring Data objects wholesale.

## 13. Do Not Mix Search Metadata into Entities

A confusing practice is adding properties such as `score`, `highlight`, `indexName`, or `sortValues` to an entity solely to receive search results.

Example of how not to design a persistence entity:

~~~java
@Document(indexName = "catalog-products")
public class ProductDocument {

    private String name;
    private double price;

    // Do not treat the values below as business fields of the document
    private Float score;
    private String highlight;
    private String indexName;
}
~~~

These values belong to hit metadata, not document content. Putting them into the entity can cause:

- The mapping converter to treat them as persistence fields.
- The index to receive fields that do not belong to the business schema.
- Stale metadata values to be saved or overwritten.
- The entity to become coupled to a specific search execution.

Keep metadata in `SearchHit<T>` and convert to a response DTO when needed.

## 14. Highlight, Score, and Sort Have Different Lifecycles

These three metadata types all belong to the hit but have different semantics:

| Metadata | Where is it generated? | What does it depend on? | Should it be saved in the document? |
| --- | --- | --- | --- |
| Score | Elasticsearch scoring engine | Query, analyzer, similarity, boost, and data | No |
| Highlight | Elasticsearch highlight subsystem | Query, field, analyzer, and highlight configuration | No |
| Sort values | Sort clauses of the search request | Sort order and field values on the hit | No |

Example:

- A document can have a high score when searching for `keyboard` but a low score when searching for `mouse`.
- The highlight for the `name` field can differ between two keywords.
- Sort values can be `[129.5, "product-1001"]` when sorting by price then ID.

None of these three metadata types is a stable property of the document.

## 15. Matched Queries and Explanation

### 15.1. Named Query

A `bool` query can contain multiple branches. When naming a query branch, Elasticsearch can return the matched query names in `matched_queries`.

Example:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "match": {
            "name": {
              "query": "keyboard",
              "_name": "name_match"
            }
          }
        },
        {
          "match": {
            "description": {
              "query": "keyboard",
              "_name": "description_match"
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Query names help the application or debugging process identify which branch matched. Spring Data can expose this list of names via hit metadata if the version and response mapping support it.

### 15.2. Explanation

If a request enables `explain`, Elasticsearch returns an explanation of how the score was computed for the hit. This data is useful when investigating why a document has a high or low score.

Explanation can be quite large and expensive. Enable it only during debugging or for a small, controlled number of requests; do not enable it by default for all production queries.

## 16. SearchHit in Other Search Types

### 16.1. Search with Highlight

When a query requests highlighting, snippets are attached to each hit. The entity remains the content; highlights reside in hit metadata.

### 16.2. Search with Inner Hits

When a query uses `nested` or parent/child, inner hit groups reside in the parent hit's metadata. They do not change the main content type.

### 16.3. Search with Aggregation

Aggregations usually reside at the `SearchHits` level, not belonging to a single `SearchHit`. A bucket can aggregate over many documents, including documents not in the returned top hits.

### 16.4. Scroll and Point in Time

Some scroll or PIT operations return an ID/context to continue searching. This is metadata serving the search context lifecycle, not a document field. Close the search context via the corresponding API once finished.

## 17. Complete Example: Preserving Metadata When Searching Products

Suppose the search page needs:

- Product content.
- Document ID and physical index.
- Relevance score.
- Name highlights.
- Total number of results.

Service:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ProductSearchResponse search(NativeQuery query) {
        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        List<ProductSearchItem> items = hits.getSearchHits()
            .stream()
            .map(this::toItem)
            .toList();

        return new ProductSearchResponse(
            hits.getTotalHits(),
            items
        );
    }

    private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
        ProductDocument product = hit.getContent();

        return new ProductSearchItem(
            hit.getId(),
            hit.getIndex(),
            product.getSku(),
            product.getName(),
            product.getPrice(),
            hit.getScore(),
            hit.getHighlightFields()
                .getOrDefault("name", List.of())
        );
    }
}
~~~

DTO:

~~~java
public record ProductSearchItem(
    String id,
    String index,
    String sku,
    String name,
    double price,
    float score,
    List<String> highlights
) {}

public record ProductSearchResponse(
    long totalHits,
    List<ProductSearchItem> items
) {}
~~~

The query builder needs to configure highlighting for the `name` field. The highlight builder syntax of the Elasticsearch Java API Client depends on the version, but in terms of Query DSL, the equivalent request part is:

~~~json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {}
    }
  }
}
~~~

The example above shows how to keep metadata when needed and convert it into a clear response contract. In a real application, validate inputs, limit page size, and return only the metadata the frontend needs.

## 18. Common Pitfalls

**Only calling getContent() and expecting score and highlights to still be available.** `getContent()` returns the entity. Keep `SearchHit<T>` if per-hit metadata is needed.

**Treating _score as a document field.** Score depends on the query and is not business data. Read it via `SearchHit.getScore()`.

**Treating sort values as a list of entity fields.** Sort values reflect the request's sort clauses. Read them via `getSortValues()`.

**Assuming highlight alters source fields.** Highlights are separate snippets. Canonical content remains in the entity content.

**Using @Id and looking for the ID in _source.** ID is usually managed via `_id` metadata. Read `hit.getId()` or the ID property mapped by Spring Data.

**Assuming hit.getIndex() always equals the alias passed in the request.** Elasticsearch may return the physical index name. Distinguish logical aliases from physical indices.

**Ignoring inner hits.** A nested query returns the parent hit; to get matching nested objects, you must read inner hits.

**Confusing aggregations with the hit list.** Aggregations reside at the `SearchHits` response level, not in entity content.

**Converting SearchHits<T> to List<T> too early.** Unwrapping loses per-hit metadata in the new list. Only do so when certain metadata is not needed.

**Using source filtering and then saving the partial entity.** Excluded fields may become `null` or default values. Use a projection/DTO or partial update.

**Returning internal SearchHit types directly through an API without controlling the contract.** Convert to a DTO to avoid depending on Spring Data internals and exposing unnecessary metadata.

**Enabling explain for all queries.** Explanation has computational cost and produces large responses. Enable only for controlled debugging.

## 19. Workflow for Reading and Converting Results

When processing search results in Spring Data Elasticsearch:

1. Determine whether the application needs only document content or also hit metadata.
2. Use `operations.search(...)` or an appropriate repository return type to obtain `SearchHits<T>` when metadata is needed.
3. Use `SearchHit<T>.getContent()` to read the mapped entity.
4. Use `getId()` and `getIndex()` to read hit identity metadata.
5. Use `getScore()` when the query has relevance semantics.
6. Use `getSortValues()` for sorting or `search_after` if needed.
7. Use `getHighlightFields()` to retrieve display snippets.
8. Use `getInnerHits()` when the query uses `nested`/parent-child.
9. Read aggregations and suggestions at the `SearchHits` level.
10. Convert content along with required metadata into a response DTO before returning from the application layer.
11. Do not write score, highlights, or sort values into persistence entities.
12. Do not save a partial entity created from source filtering back without loading complete data.

## 20. References

- [Spring Data Elasticsearch - Search result types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): how to execute searches and use `SearchHits`.
- [Spring Data Elasticsearch API - SearchHit](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html): metadata of a single hit and mapped content.
- [Spring Data Elasticsearch API - SearchHits](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html): metadata at the search response level.
- [Elasticsearch - Search API response](https://www.elastic.co/docs/solutions/search/the-search-api): structure of hits, total, score, sort, highlight, and aggregations.
- [Elasticsearch - Highlighting](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting): configuration and content of highlight fragments.
- [Elasticsearch - Source filtering](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrieve-selected-fields): limiting fields returned from source.

Detailed APIs of `SearchHit`, `SearchHits`, and response types may vary depending on the Spring Data Elasticsearch version. Check the Javadoc of the project's dependency when using less common metadata properties.
