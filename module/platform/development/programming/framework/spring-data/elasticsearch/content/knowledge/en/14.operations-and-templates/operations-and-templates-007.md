# Retrieving Result Metadata Instead of Only Document Content

When searching in Elasticsearch, results are not just the documents matching the criteria. Each hit can also carry its ID, source index, relevance score, sort values, highlight snippets, and other metadata. The overall response can contain total hit counts, whether that count is exact or an estimate, aggregations, and suggestions.

If an application only retrieves a list of **Product** objects or only reads **_source**, this metadata can be lost. In Spring Data Elasticsearch, **SearchHits<T>** and **SearchHit<T>** retain both entity content and search information. **ElasticsearchOperations** lets you execute queries and receive this result structure so the service can decide which data to return to upper layers.

This lesson focuses on distinguishing document content from hit-level metadata and response-level metadata, retrieving them using Operations, and preserving metadata when mapping results to DTOs or API responses.

## 1. Document Content and Search Metadata Are Two Separate Parts

A document in Elasticsearch typically has a **_source** section containing the indexed business data. For example:

~~~json
{
  "_index": "products-000042",
  "_id": "p-100",
  "_score": 2.41,
  "_source": {
    "name": "Wireless Mechanical Keyboard",
    "category": "accessories",
    "price": 89.5
  },
  "sort": [89.5, "p-100"]
}
~~~

In this example:

- **_source** contains the document content: name, category, and price.
- **_id** is the document identifier in the index.
- **_index** indicates which physical index the document came from.
- **_score** is the hit's relevance score for the query.
- **sort** contains the values used to sort the hit.

A search response can also contain total hit count, aggregations, suggestions, and pagination control information.

A Java entity usually describes the data inside _source:

~~~java
@Document(indexName = "products-read")
public class Product {

    @Id
    private String id;

    private String name;
    private String category;
    private Double price;

    // constructors, getters, setters
}
~~~

The Product entity may not contain _index, _score, or sort values. This information belongs to the search result and is not necessarily a business property of the document. Therefore, you should not add all search metadata fields to the entity just to keep them after a search.

### Three Layers of Data to Distinguish

| Layer | Examples | Scope |
|---|---|---|
| Document content | name, category, price | One document |
| Hit metadata | ID, index, score, sort values, highlights | One matching result |
| Response metadata | total hits, max score, aggregations, suggestions | Entire search request |

This distinction helps choose the right return type. If only the document is needed, the entity is sufficient. If per-hit information is needed, use SearchHit<T>. If both search results and request-level statistics are needed, keep SearchHits<T>.

## 2. SearchHits and SearchHit in Spring Data Elasticsearch

Spring Data Elasticsearch provides two key abstractions:

- **SearchHits<T>** is the container for the entire search result and response-level metadata.
- **SearchHit<T>** is a wrapper for a single matching document along with that hit's own metadata.

Their relationship can be visualized as:

~~~text
ElasticsearchOperations.search(...)
                |
                v
          SearchHits<Product>
          /       |          \
         /        |           \
        v         v            v
  SearchHit  SearchHit ...  Response metadata
      |          |           |
      v          v           +-- total hits
   Product    Product        +-- total hits relation
   hit meta   hit meta       +-- max score
                             +-- aggregations
                             +-- suggestions
~~~

Example:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : searchHits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getId());
    System.out.println(hit.getScore());
}
~~~

**getContent()** returns the entity converted by Spring Data from the document. Other methods on SearchHit let you read metadata for that specific hit.

Do not call getContent() and discard the wrapper too early if subsequent steps still need the score, source index, highlights, or sort values.

## 3. Retrieving Per-Hit Metadata

### Document ID and Source Index

SearchHit<T> provides the ID and index name of the returned document:

~~~java
for (SearchHit<Product> hit : searchHits) {
    String documentId = hit.getId();
    String indexName = hit.getIndex();
    Product product = hit.getContent();
}
~~~

The ID is useful when the UI needs to build links to a detail page or when the service needs to perform follow-up operations on the document. The source index is useful in systems with multiple indices behind an alias, especially for tracing data or investigating migrations.

Do not assume the source index is always identical to the alias name the application called. An alias is a routing name; hit metadata can reveal the physical index storing the document.

Some results can also provide routing metadata. This value is useful when the application uses custom routing and needs to know which key routed the document. Only use it if the use case requires it and your version's API provides it.

### Relevance Score

getScore() returns the hit's relevance score for the query:

~~~java
for (SearchHit<Product> hit : searchHits) {
    float score = hit.getScore();
    Product product = hit.getContent();

    System.out.printf(
        "name=%s, score=%f%n",
        product.getName(),
        score
    );
}
~~~

Score helps the application:

- Display or explain search result ordering.
- Compare relative relevance among hits of the same query.
- Diagnose why one document ranked ahead of another.
- Build presentation logic based on relevance if required by business rules.

Do not treat score as a probability. A score value does not mean how likely a document is to be correct in percentage terms. Score is only meaningful in the context of the query, field statistics, similarity, and how Elasticsearch computes scoring.

If a request only sorts by a field and does not compute relevance, score may have no useful meaning. In that case, do not expose score in the API contract as an always-comparable value.

### Sort Values

When a request includes sorting, each hit can contain the values used for sorting:

~~~java
for (SearchHit<Product> hit : searchHits) {
    List<Object> sortValues = hit.getSortValues();
}
~~~

Example request:

~~~http
POST /products-read/_search
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
      "_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

The first hit may have sort values corresponding to price and _id. These values can be used as the starting point for the next request using search_after.

For stable deep pagination, you need to:

1. Define a fixed sort order.
2. Add a unique tie-breaker if the primary sort field can have duplicate values.
3. Extract sort values from the last hit of the current page.
4. Pass those exact values into the next request.
5. If consistent results are needed while the index is changing, consider Point in Time (PIT) according to your Elasticsearch and Spring Data version capabilities.

Do not reconstruct sort values from entity properties manually. Elasticsearch may return normalized values or specific ordering and data types; using the exact metadata values from the hit prevents pagination drift.

### Highlight Fields

Highlighting returns text snippets containing the parts that matched the query. This is hit metadata, not a modified _source value.

Example request:

~~~http
POST /products-read/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {}
    },
    "pre_tags": ["<em>"],
    "post_tags": ["</em>"]
  }
}
~~~

After the request is sent via Operations, each hit can contain a highlight map:

~~~java
for (SearchHit<Product> hit : searchHits) {
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    List<String> nameFragments = highlights.get("name");
}
~~~

A field can have multiple fragments. Fragments can contain markup tags configured by the request. When rendering on the web, handle markup safely; never inject untrusted highlight strings directly into HTML without sanitization.

Highlights do not replace _source. If the application needs to display the full product name, use hit.getContent().getName(). If it needs to show query-matching snippets, use highlight fragments.

### Inner Hits

For queries on nested objects or parent-child relationships, Elasticsearch can return matching child hits via inner_hits.

Example mapping with nested lines:

~~~java
@Document(indexName = "orders")
public class PurchaseOrder {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
}
~~~

A nested query can request inner hits:

~~~http
POST /orders/_search
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "term": {
          "lines.productCode": "KB-100"
        }
      },
      "inner_hits": {}
    }
  }
}
~~~

At the parent hit level, inner hits metadata indicates which nested documents matched:

~~~java
for (SearchHit<PurchaseOrder> hit : searchHits) {
    Map<String, SearchHits<?>> innerHits = hit.getInnerHits();
}
~~~

Detailed structure and access types depend on the version's API. Inner hits are only present if the query requests them and Elasticsearch returns that data. Marking a property as nested in the mapping does not mean every search response automatically includes inner hits.

## 4. Metadata at the Whole SearchHits Level

In addition to per-hit metadata, SearchHits<T> holds information for the entire request.

### Total Hits

~~~java
long totalHits = searchHits.getTotalHits();
~~~

This is the hit count reported by Elasticsearch for the query. However, you should also check the relation of that number:

~~~java
var relation = searchHits.getTotalHitsRelation();
~~~

The total hit count can be exact or merely a lower bound, depending on how the request asks for counting and Elasticsearch settings. For example, when setting a count threshold to optimize performance, Elasticsearch may stop exact counting after the threshold and report that the actual total is at least the returned value.

Therefore, do not always display totalHits as an exact absolute number. If the API or UI needs accurate reporting, preserve the total hits relation and design queries to count according to business requirements.

### Max Score

getMaxScore() returns the highest score among hits in the response when scoring is meaningful:

~~~java
float maxScore = searchHits.getMaxScore();
~~~

Max score helps gauge the score scale of a response or aids display/debugging. Do not compare max score across different queries as an absolute quality metric, because score depends on query structure and index data.

### Aggregations

Aggregations return statistics over matching documents or over a scope defined by the aggregation. For example:

~~~http
POST /products-read/_search
{
  "size": 0,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "aggs": {
    "average_price": {
      "avg": {
        "field": "price"
      }
    },
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

The response contains buckets and metrics, not document entities. Spring Data keeps aggregation metadata on the search result; it can be accessed from SearchHits via the corresponding aggregation API for your version.

Do not try to convert an aggregation into a Product. A by_category bucket is a statistical group, whereas Product is a document. Convert aggregation results into a separate DTO if they need to be returned to a controller or report.

### Suggest

A search response can contain suggestions generated by the Suggest API, such as spelling suggestions or fuzzy phrase completions. If the application uses suggestions, read suggestion metadata from the Operations result instead of trying to infer it from the entity list.

Suggestions have their own structure and are not regular hits. Access and conversion depend on the client API and release train.

### Scroll ID and Point in Time

Some pagination or large dataset reading workflows may use scroll or Point in Time. The response can contain an ID for the next request. This is read-session control metadata, not business data.

If using scroll/PIT:

- Keep the latest ID returned by the server according to the API rules.
- Send the next request with that ID.
- Close or release the context when finished.
- Handle timeouts and expired contexts.
- Do not expose the ID in public URLs unnecessarily.

Exact APIs and how SearchHits exposes these values depend on the Spring Data Elasticsearch version. For large data processing flows, read the documentation for your specific release train.

## 5. Executing Search with ElasticsearchOperations

ElasticsearchOperations is the high-level abstraction for running queries and converting results into Java entities. When calling search, instead of receiving just a list of documents, you receive SearchHits<T>.

Service example:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(String keyword) {
        Query query = /* build query for name */;

        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }
}
~~~

IndexCoordinates allows explicitly selecting an index or alias. This is useful when the application reads via a read alias or needs to search a specific index. If the entity already declares a default index and the use case targets that index, you can use the overload without coordinates.

Queries can be created with CriteriaQuery or NativeQuery. For complex queries, NativeQuery allows using features of the Elasticsearch Java API Client. Builder syntax varies across versions, so verify against your actual dependencies.

Example simple query with Criteria:

~~~java
Criteria criteria = new Criteria("category").is("accessories");
Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

The result still retains both content and metadata. There is no need to call REST endpoints manually just to retrieve IDs or scores.

### Iterating Results While Preserving the Wrapper

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    String id = hit.getId();
    String sourceIndex = hit.getIndex();
    float score = hit.getScore();
    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    // Process entity and metadata according to the use case.
}
~~~

If code only needs the content, it can use hit.getContent(). If metadata is needed, process the wrapper before converting to a plain entity collection.

## 6. Repositories Can Also Return Metadata-Aware Results

Repositories are not forced to always return List<T>. Depending on the Spring Data Elasticsearch version and query type, repository methods can support return types such as SearchHits<T>, SearchPage<T>, or a list of SearchHit<T>.

Example method signature:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    SearchHits<Product> findByCategory(String category);
}
~~~

With metadata-aware return types, callers can inspect hit information instead of receiving only entities. However, check the supported return types list in your Spring Data Elasticsearch version; not every return type from other Spring Data modules can be applied verbatim.

If a method returns List<Product>, wrapper metadata is no longer present in the result. If the service needs scores, highlights, or source index, choose a return type that preserves SearchHit or use ElasticsearchOperations.

### SearchPage When Both Pagination and Metadata Are Needed

SearchPage<T> combines pagination information with search hits. It is useful when an API needs page number, page size, total count, and per-hit metadata together.

A common flow:

~~~java
SearchHits<Product> searchHits =
    operations.search(query, Product.class);

// Convert to SearchPage using the version's supported API.
SearchPage<Product> page =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

SearchPage retains SearchHit<T> instances rather than just entity content. Converting immediately to Page<Product> can cause the application to lose per-hit metadata. Choose the page type based on what callers need.

## 7. Mapping SearchHit to DTOs Without Losing Metadata

The API layer should generally avoid returning framework objects directly if the API contract needs to remain stable. You can map each hit into a clear DTO.

Example DTO:

~~~java
public record ProductSearchItem(
    String id,
    String index,
    float score,
    Product product,
    List<Object> sortValues,
    Map<String, List<String>> highlights
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toItem(SearchHit<Product> hit) {
    return new ProductSearchItem(
        hit.getId(),
        hit.getIndex(),
        hit.getScore(),
        hit.getContent(),
        hit.getSortValues(),
        hit.getHighlightFields()
    );
}
~~~

Search-level response:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    long totalHits,
    String totalHitsRelation,
    float maxScore
) {}
~~~

The service can build the response:

~~~java
public ProductSearchResponse searchProducts(Query query) {
    SearchHits<Product> result =
        operations.search(query, Product.class);

    List<ProductSearchItem> items =
        result.getSearchHits().stream()
            .map(this::toItem)
            .toList();

    return new ProductSearchResponse(
        items,
        result.getTotalHits(),
        result.getTotalHitsRelation().name(),
        result.getMaxScore()
    );
}
~~~

This is an illustrative example; exact enum types and APIs should be checked against the version in use. In a real API, total hits relation can be represented by an enum or a clearly meaningful string.

Benefits of DTOs:

- The public API exposes only the metadata the client actually needs.
- Domain entities do not have to carry search-specific fields.
- Spring Data implementations can change without forcing clients to depend on framework types.
- Sensitive data can be controlled and returned information bounded.
- Cursors or sort values can be included in the response for pagination.

Do not return all internal metadata just because the framework provides it. Only expose fields meaningful to the use case.

## 8. Preserving Metadata When Building Search APIs

A search endpoint often needs more than a list of documents:

~~~json
{
  "items": [
    {
      "id": "p-100",
      "index": "products-000042",
      "score": 2.41,
      "product": {
        "name": "Wireless Mechanical Keyboard",
        "category": "accessories",
        "price": 89.5
      },
      "highlights": {
        "name": [
          "Wireless <em>Mechanical</em> <em>Keyboard</em>"
        ]
      }
    }
  ],
  "totalHits": 124,
  "totalHitsRelation": "EQUAL_TO",
  "maxScore": 2.41
}
~~~

The example shows metadata preserved alongside content. A real API may not need index or score; instead, it might return a nextCursor built from sort values.

If returning highlight fragments, clearly specify whether the client receives HTML fragments or text fragments. Do not let the API accidentally turn highlight strings into executable HTML. Use appropriate escaping/sanitization at the presentation layer.

### Which Metadata Should Stay on the Backend?

Some metadata is only needed on the backend:

- Physical index for tracing or debugging.
- Internal routing keys.
- Full score explanations.
- Scroll ID or PIT ID if managed server-side.
- Aggregations not used in the current UI.

Some metadata can be useful to clients:

- Total hits and exact/approximate relation.
- Highlight fragments.
- Sort values or cursor tokens.
- Score if the UI needs to display relevance.
- Aggregations converted into DTOs.

Define the API contract by use case rather than serializing the raw SearchHits object by default.

## 9. Metadata and Deep Pagination with search_after

Pagination with from and size suits the first pages. When stepping deeply into large result sets, Elasticsearch recommends considering search_after instead of increasing from unboundedly.

search_after requires the sort values of the last hit on the current page. This is why SearchHit.getSortValues() is critical.

Example first request:

~~~http
POST /products-read/_search
{
  "size": 20,
  "sort": [
    { "price": "asc" },
    { "_id": "asc" }
  ],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Suppose the last hit on the page has sort values:

~~~json
[129.9, "p-120"]
~~~

The next request uses those values:

~~~http
POST /products-read/_search
{
  "size": 20,
  "sort": [
    { "price": "asc" },
    { "_id": "asc" }
  ],
  "search_after": [129.9, "p-120"],
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

In a Spring Data application, retrieve sortValues from the last hit and pass them into the next query using the supported API for your version. Do not take price and id from the entity yourself and assume they always match Elasticsearch's returned sort values identically.

If data can change while a user pages through results, results may shift. PIT can help maintain a consistent view across a pagination session. When using PIT, manage the ID and context lifecycle according to Elasticsearch documentation for your deployed version.

## 10. Metadata and Aggregations in the Same SearchHits

One request can return both document hits and aggregations:

~~~http
POST /products-read/_search
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
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

SearchHits<Product> contains the list of hits and response metadata. Aggregations do not belong to a specific Product, but to the entire query result.

A service can return a combined result:

~~~java
public record ProductSearchSummary(
    List<ProductSearchItem> items,
    long totalHits,
    Map<String, Object> statistics
) {}
~~~

The statistics section is a DTO built by the service from the aggregation response. Do not let controllers decode aggregation containers themselves or depend directly on client response types.

Aggregation APIs in Spring Data have evolved across versions as underlying clients changed. Read the documentation for your release train to access buckets/metrics and convert them into DTOs.

## 11. Explaining Scores When Investigating Results

When a document appears in an unexpected position, looking at the score alone may not be enough. Elasticsearch can provide an explanation if the request enables the corresponding option.

Explanation describes the components that contributed to the relevance score. It can be very verbose and enlarge responses, so enable it only in debug environments or use cases that need to explain results.

Investigation workflow:

1. Record the query and index being queried.
2. Identify the hit with an unexpected score.
3. Enable explain for the request or use the Explain API on the specific document.
4. Inspect analyzers, tokens, field boosts, and similarity.
5. Compare with a document that has similar content.
6. Adjust the query or mapping if the result is genuinely inappropriate.

Score is not fixed data stored inside the document. It is calculated from the query and index data at search time.

## 12. Common Pitfalls When Working with Metadata

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Have Product but missing score/index | Caller kept only getContent() or repository returned plain entities | Retain SearchHit<T>/SearchHits<T> |
| Highlight map is empty | Query did not request highlights or field had no matching fragments | Check highlight request and field |
| Sort values are empty | Request declared no sort or API did not return sort metadata | Check sort clauses and response |
| Total hits shown as exact when it is a lower bound | Ignored total hits relation | Retain and check relation |
| Aggregations do not appear in entities | Aggregations are response metadata, not _source | Read aggregations from search result |
| UI does not know which index holds the document | Serialized only entity content | Retain SearchHit.getIndex() if needed |
| Deep pagination duplicates or skips hits | Reconstructed cursor from entity or lacked stable tie-breaker | Use raw sort values and stable sorting |
| Inner hits are empty | Query did not declare inner_hits or had no nested matches | Check nested query |
| API response bloats | Returned full highlights, explain, aggregations, or internal metadata | Map to a DTO keeping only needed fields |
| Score varies across queries | Comparing scores across different queries or index contexts | Interpret scores only within the same query context |

### Most Common Mistake: Converting SearchHits to an Entity List Too Early

Example:

~~~java
List<Product> products = operations.search(query, Product.class)
    .getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

This snippet is completely valid if the caller only needs entities. However, after this step, hit ID, source index, score, highlights, and sort values are no longer present in the list.

If the use case needs metadata, map directly from SearchHit to a DTO:

~~~java
List<ProductSearchItem> items =
    operations.search(query, Product.class)
        .getSearchHits()
        .stream()
        .map(this::toItem)
        .toList();
~~~

## 13. Testing Search Result Metadata

Unit tests for services can verify how SearchHits are mapped into DTOs, but some metadata is only produced accurately when Elasticsearch executes the real query.

Verify scenarios such as:

- A query returning multiple hits with accurate IDs and indices.
- Score presence when the query uses relevance scoring.
- Sort values matching the declared sort order.
- Highlights appearing when the request configures the proper field.
- Total hits relation handled properly when counting is capped.
- Aggregations mapped accurately to DTOs.
- Empty results still returning valid metadata.
- Pagination cursors taken from the last hit, not the first hit.

Example service-level test verifying the mapper:

~~~java
@Test
void mapsHitMetadataIntoSearchItem() {
    // Create SearchHit/Product test fixture according to the version's API.
    // Invoke mapper.
    // Assert ID, index, score, and content are preserved.
}
~~~

For integration tests, use a compatible Elasticsearch version and deterministic test data. Highlight tests should check analyzers and queries; aggregation tests need mappings with doc values; sort tests need sortable fields.

Do not write tests that only check getContent() if the goal of the use case is to preserve metadata.

## 14. Design Rules When Returning Metadata

- Keep SearchHits<T> until the service has finished processing response-level metadata.
- Keep SearchHit<T> when per-document metadata is needed.
- Only convert to List<T> if the caller truly only needs entities.
- Distinguish _source from ID, index, score, sort values, and highlights.
- Do not interpret score as a probability.
- Check total hits relation before claiming a result total is exact.
- Use sort values returned by Elasticsearch when building search_after cursors.
- Add a stable tie-breaker when paginating by a sort field that may have duplicates.
- Use highlights to display snippets while keeping entity content as source data.
- Keep aggregations and suggestions at the response level, mapping them to separate DTOs if needed.
- Do not expose internal metadata or session IDs if the client does not need them.
- Verify SearchHit, SearchHits, SearchPage, and aggregation APIs against the running Spring Data Elasticsearch version.

## 15. Checklist Before Discarding Metadata from Results

- [ ] Does the caller only need _source content or metadata as well?
- [ ] Is the ID or source index needed for each hit?
- [ ] Is score needed for ranking or explaining results?
- [ ] Are sort values needed to paginate further?
- [ ] Are highlight fragments needed for the UI?
- [ ] Does the query return inner hits?
- [ ] Is the total hits relation needed to distinguish exact counts from lower bounds?
- [ ] Are there aggregations or suggestions at the response level?
- [ ] Does metadata need to be mapped to a DTO before returning from the API?
- [ ] Is SearchHits<T> being converted to List<T> too early?
- [ ] Has metadata been tested against a compatible Elasticsearch instance?

When querying with Spring Data Elasticsearch, the entity is only part of the result. SearchHit<T> holds per-document metadata, while SearchHits<T> holds overall request information. Using ElasticsearchOperations to receive and process these wrappers enables the application to retain IDs, source indices, scores, sort values, highlights, aggregations, and information needed for pagination or presentation. Only discard metadata once you have verified that upper business layers no longer require it.
