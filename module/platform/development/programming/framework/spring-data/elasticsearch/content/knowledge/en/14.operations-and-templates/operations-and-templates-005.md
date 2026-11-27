# Executing Search, Count, and Multi-Search via Supported APIs

Spring Data Elasticsearch provides high-level operation APIs for Java applications to search documents, count matching documents, and send multiple queries in a single call. These operations are usually performed through `ElasticsearchOperations`, an abstraction suitable when queries need more flexibility than repository CRUD or query derivation methods.

The three operations serve different purposes:

- **Search** executes a query and returns documents along with metadata such as total result count, scores, highlights, or sort values.
- **Count** returns the number of documents matching query criteria without needing to load all documents into the application.
- **Multi-search** sends a group of independent queries in a single multi-search request, reducing network round trips when multiple result sets are needed.

Choosing the right API ensures the application only fetches required data, avoids reading the entire index just to count, and organizes multiple related queries efficiently.

## 1. ElasticsearchOperations and Search APIs

### 1.1. Role of ElasticsearchOperations

`ElasticsearchOperations` is a high-level abstraction in Spring Data Elasticsearch. It provides operations such as:

- Saving, reading, and deleting documents.
- Creating and executing queries.
- Searching and retrieving result metadata.
- Counting documents by query.
- Performing multi-search.
- Working with indices via IndexOperations.

Example of injecting operations into a service:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Spring Boot typically configures the operations implementation based on the Elasticsearch client and mapping converter in the application context. Services do not need to create an HTTP client for every search.

### 1.2. When to Use Operations Instead of Repository?

Repositories are suitable for CRUD and predetermined queries, whereas Operations is useful when building dynamic queries or extracting detailed metadata.

| Need | Appropriate API |
|---|---|
| Save a document by ID | ElasticsearchRepository or ElasticsearchOperations |
| Find by a declared method | ElasticsearchRepository |
| Dynamic Query DSL with multiple conditions | ElasticsearchOperations |
| Retrieve SearchHit, score, highlight | ElasticsearchOperations |
| Count by query criteria | ElasticsearchOperations.count |
| Send multiple independent queries | ElasticsearchOperations.multiSearch |
| Dynamically select index at runtime | Operations with IndexCoordinates |
| Manage settings/mapping/index | IndexOperations |

You do not have to pick a single API for the entire application. One service can use repositories for simple operations and Operations for advanced search screens.

### 1.3. Search Execution Flow

~~~mermaid
flowchart TD
    A[Service creates Query] --> B[ElasticsearchOperations.search]
    B --> C[Mapping converter and query infrastructure]
    C --> D[Elasticsearch Java client]
    D --> E[Elasticsearch cluster]
    E --> D
    D --> F[Search response]
    F --> G[SearchHits and SearchHit]
    G --> H[Service processes results]
~~~

`Query` describes search conditions and options. `ElasticsearchOperations` converts the query into an appropriate request, the client sends the request to the cluster, and the response is mapped into Spring Data result structures.

## 2. Creating a Query for Searching

### 2.1. Query Describes a Search Request

Spring Data Elasticsearch has the `Query` abstraction. Common implementations include:

- `NativeQuery`: builds queries in Elasticsearch Query DSL using the Elasticsearch Java API Client.
- `CriteriaQuery`: expresses conditions in criteria form, convenient for simple filters.
- `StringQuery`: supplies a JSON query as a string when appropriate.

The choice of query type depends on complexity and library version. For full-text, bool, nested, aggregation, or scoring queries, `NativeQuery` usually provides fuller expressiveness.

### 2.2. NativeQuery for Full-Text Search

Example searching products by name:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("wireless keyboard")
    ))
    .build();
~~~

`match` is a full-text query. Elasticsearch analyzes the search string using the analyzer configured for the field before matching tokens in the inverted index.

The field name in the query is the actual Elasticsearch field name. If the entity has `@Field(name = "product_name")`, the Query DSL must reference `product_name`, unless the query is constructed via an abstraction/property path that supports metadata in the version being used.

### 2.3. Combining Conditions with bool Query

A product search often combines content matching with category and availability filtering:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
        ))
        .filter(f -> f.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .filter(f -> f.term(t -> t
            .field("available")
            .value(true)
        ))
    ))
    .build();
~~~

In this example:

- `must` holds the full-text condition that can contribute to the relevance score.
- `filter` restricts results by exact conditions without adding to the relevance score.
- Multiple filters in a bool query are combined with AND logic.

For a `category` field of type keyword, a term query is suitable for exact filtering. For a `name` field of type text, a match query is suitable for searching analyzed content.

### 2.4. CriteriaQuery for Simple Filters

When a query consists only of straightforward conditions, you can use the Criteria API:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("category").is("ACCESSORY")
    .and(new Criteria("available").is(true));

Query query = new CriteriaQuery(criteria);
~~~

Then execute:

~~~java
SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

The Criteria API is easy to read for basic conditions. For advanced Query DSL features, switch to NativeQuery instead of trying to express everything with Criteria.

### 2.5. StringQuery When Direct JSON Queries Are Needed

JSON queries can be used when you want to store or pass Query DSL as a string:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless keyboard"
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "ACCESSORY"
        }
      }
    ]
  }
}
""");
~~~

StringQuery is useful for static JSON queries or queries generated from a controlled source. If interpolating user input into a JSON string, you must serialize/escape it properly. Do not concatenate strings arbitrarily as it can produce invalid JSON or alter query structure unintentionally.

## 3. Executing Search

### 3.1. Calling operations.search

After creating a query, call the search API:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);
~~~

This overload uses the index determined from entity metadata, such as `@Document(indexName = "products")`.

If you need to specify the index at runtime, pass `IndexCoordinates`:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("products-v2")
    );
~~~

This is useful when an application uses versioned indices, aliases, or needs to select an index from runtime configuration. Ensure the mapping of the selected index is compatible with the entity class.

### 3.2. Reading Document Content from SearchHits

Search results usually have type `SearchHits<T>`, not just a List of entities.

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();
    System.out.println(product.getName());
}
~~~

`SearchHits` contains `SearchHit` results along with overall metadata. `SearchHit` represents a single hit and can provide:

- `getContent()`: mapped Java entity.
- `getId()`: document ID.
- `getScore()`: relevance score.
- `getSortValues()`: returned sort values.
- `getHighlightFields()`: highlight content if requested by the query.
- Other metadata depending on version and response.

Example reading the score:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    System.out.printf(
        "id=%s, score=%s, name=%s%n",
        hit.getId(),
        hit.getScore(),
        hit.getContent().getName()
    );
}
~~~

Score helps observe relevance according to the scoring algorithm Elasticsearch uses. Do not interpret score as a percentage accuracy or probability that a result is correct.

### 3.3. Overall SearchHits Metadata

Commonly used properties:

~~~java
long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

List<SearchHit<ProductDocument>> hits =
    searchHits.getSearchHits();
~~~

`getTotalHits()` returns the total hit count reported according to the query and configured total-hit tracking. `getMaxScore()` returns the highest score in the results. `getSearchHits()` returns the list of hits for the current page.

Total hits and the number of hits currently in the list can differ because the query limits page size. For example, total matches may be 125 while the current page contains only 20 hits.

### 3.4. Extracting Only Entities When Metadata Is Not Needed

If a service only needs entity content, you can convert SearchHits into a list of contents:

~~~java
List<ProductDocument> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

This is simple for data-returning APIs. However, if the UI needs relevance scores, highlights, or sort values, keep SearchHit so metadata is not lost.

### 3.5. Highlighting Results

For text search, highlights help display snippets containing the matched keywords. You can configure a highlight query in NativeQuery; the specific builder depends on the Elasticsearch Java API Client version:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("description")
        .query("wireless keyboard")
    ))
    .withHighlightQuery(h -> h.fields(
        "description",
        f -> f.preTags("<em>").postTags("</em>")
    ))
    .build();
~~~

Check the highlight overloads for your project version and verify that the field supports highlighting.

Reading highlight data from a hit:

~~~java
for (SearchHit<ProductDocument> hit : searchHits) {
    List<String> fragments =
        hit.getHighlightField("description");

    System.out.println(fragments);
}
~~~

Highlight fragments are content generated by Elasticsearch from indexed data. When rendering in an HTML UI, handle content and markup safely; do not assume fragments can be rendered directly as trusted HTML.

## 4. Pagination and Sorting in Search

### 4.1. Adding Pageable to a Query

To limit the number of returned hits, add pageable to the query:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "price")
);

Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("keyboard")
    ))
    .withPageable(pageable)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

This example fetches the first page with up to 20 results, sorted by descending price. The sort field must have a mapping that supports sorting. For text fields, a keyword subfield or a separate field designed for sorting is usually used.

### 4.2. Creating a Page from SearchHits

If you need a Spring Data Page structure, you can use an appropriate conversion utility for your version, such as `SearchHitSupport.searchPageFor`:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

`SearchPage` retains SearchHit content and pagination info. If an API only needs a simple page of entities, it can return the content along with page metadata fields constructed by the service.

### 4.3. Distinguishing Total Results from Items in a Page

Suppose a query matches 240 documents, while pageable requests 20 items:

- `getTotalHits()` can report a total of 240 depending on total-hit tracking.
- `getSearchHits().size()` is the number of hits actually returned on the current page, usually 20.
- The second page has an offset corresponding to page index 1.

Do not use the current list size as the total result count. Conversely, if total hits are capped or not fully tracked by configuration, understand total-hit tracking semantics before displaying the number as an absolute total.

### 4.4. Deep Pagination

Offset pagination works well for early pages. For very deep pages, Elasticsearch must process many intermediate results and enforces a result window limit. For large dataset traversal, consider:

- `search_after` to continue from the sort values of the previous hit.
- Point-in-time (PIT) to maintain a stable view during pagination when needed.
- Scroll for certain batch/export tasks according to version APIs and guidelines.

These APIs require proper queries/sorts and cursor management; do not expand page size or result window indefinitely as a substitute.

## 5. Executing Count

### 5.1. Count Returns the Number of Matching Documents

When you only need the count of documents matching a query, use `ElasticsearchOperations.count`:

~~~java
long count = operations.count(
    query,
    ProductDocument.class
);
~~~

You can specify an index explicitly:

~~~java
long count = operations.count(
    query,
    ProductDocument.class,
    IndexCoordinates.of("products")
);
~~~

Count is suitable for:

- Displaying search result counts.
- Checking whether any documents match a condition.
- Counting products by category.
- Estimating the number of records to process in a job.
- Verifying data after import or migration.

### 5.2. Count Does Not Load All Documents

Elasticsearch's Count API only computes the number of documents matching the query. It does not need to return `_source` for each document for the application to convert into Java objects.

This is generally much more efficient than calling search with a huge page size and counting the list in application code. Do not use `findAll()` or search everything just to count.

Example creating a match-all query to count all documents for an entity:

~~~java
Query allQuery = NativeQuery.builder()
    .withQuery(q -> q.matchAll(m -> m))
    .build();

long totalProducts =
    operations.count(allQuery, ProductDocument.class);
~~~

If you need to count by condition, use the same query/filter logic required by the business rule.

### 5.3. Count by Condition

Example counting available products in the ACCESSORY category:

~~~java
Query availableAccessories = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .filter(f -> f.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .filter(f -> f.term(t -> t
            .field("available")
            .value(true)
        ))
    ))
    .build();

long total = operations.count(
    availableAccessories,
    ProductDocument.class
);
~~~

The filters used are identical to search criteria. If search and count must display the same dataset, reuse the query-building logic to prevent the two places from accidentally having different conditions.

### 5.4. Search Total Hits vs. Count Usage

Search returns documents and metadata; count returns only the number. If a screen needs both a list and a total result count, you can:

- Call search and use total hits if the query/search request tracks total hits appropriately.
- Call count separately when only the count is needed or when avoiding loading documents.
- Weigh the cost of two requests if calling both search and count for the same criteria.

There is no need to call count separately just to get a total if the search response already provides total hits matching requirements. Conversely, if total-hit tracking is capped or omitted in search, call count separately when business logic needs the full number.

### 5.5. Count Is Not for Every Type of Statistics

Count returns the number of documents matching a query. It does not provide breakdowns by category, sum of prices, averages, or date histograms.

If you need statistics such as product counts per category, total inventory value, average price by brand, or document counts by date range, use aggregations. Do not loop multiple count requests per group when a single aggregation can return the results more efficiently.

### 5.6. Count and Data Consistency

Elasticsearch is a near-real-time search system. A newly written document may not appear in search/count until a refresh makes the data searchable.

Therefore, if an application writes and immediately counts or searches, the observed result may depend on refresh behavior and configuration. Do not assume every write is immediately visible via search. Define consistency requirements and only use an explicit refresh policy when truly needed.

## 6. Executing Multi-Search

### 6.1. What Needs Does Multi-Search Solve?

A search page may require multiple independent queries:

- Product list by keyword.
- Featured products list.
- Category suggestions.
- Related results.
- Multiple content sections on the same screen.

If each query is sent sequentially, the application makes multiple round trips to the cluster. Multi-search allows sending multiple queries in a single `_msearch` request.

Multi-search reduces request/response round-trip overhead, but sub-queries are still executed independently by Elasticsearch. It does not create a transaction and does not guarantee all queries see the exact same data snapshot.

### 6.2. Calling multiSearch from ElasticsearchOperations

Spring Data Elasticsearch provides a multi-search API on Operations in supported versions. For multiple queries mapping to the same entity class, you can use:

~~~java
List<Query> queries = List.of(
    NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query("wireless keyboard")
        ))
        .withPageable(PageRequest.of(0, 5))
        .build(),

    NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
            .field("category")
            .value("ACCESSORY")
        ))
        .withPageable(PageRequest.of(0, 5))
        .build()
);

List<SearchHits<ProductDocument>> results =
    operations.multiSearch(queries, ProductDocument.class);
~~~

Exact signatures of multiSearch and its overloads may differ across Spring Data Elasticsearch versions. Check the API of your project's dependency, especially when specifying IndexCoordinates or different entity types.

### 6.3. Reading Each Result Group

Each element in the result list corresponds to an input query in the request/response order of multi-search:

~~~java
for (int i = 0; i < results.size(); i++) {
    SearchHits<ProductDocument> group = results.get(i);

    System.out.println("Query group " + i);
    System.out.println("Total hits: " + group.getTotalHits());

    for (SearchHit<ProductDocument> hit : group) {
        System.out.println(hit.getContent().getName());
    }
}
~~~

In a real application, name or describe queries in the service so you know which result group belongs to which UI section. Do not rely on implicit ordering if the service reorders or transforms the query list before sending.

### 6.4. Specifying an Index for Multi-Search

If all queries search the same index or alias, use the overload supporting `IndexCoordinates`:

~~~java
List<SearchHits<ProductDocument>> results =
    operations.multiSearch(
        queries,
        ProductDocument.class,
        IndexCoordinates.of("products")
    );
~~~

If queries need to search multiple indices or use different entity types, check the multi-search overloads provided in your version. Lower-level client APIs may be needed to represent individual requests with separate target indices.

### 6.5. Multi-Search Is Not a Bool Query

Distinguish between:

- **Bool query**: combines multiple conditions to produce a single result set.
- **Multi-search**: sends multiple independent queries and receives multiple separate result sets.

For example, to find products that are both in category ACCESSORY and have a name containing keyboard, use a bool query. To display two separate lists—"keyboard products" and "new products in ACCESSORY"—use multi-search.

Do not use multi-search merely to replace a bool query that can be expressed as a single request.

### 6.6. Errors in Multi-Search

Sub-queries are processed independently. One query can succeed while another encounters a syntax, mapping, or permission error depending on how Elasticsearch/the client reports results.

Determine how your Spring Data version represents multi-search errors. Some APIs may throw an exception when the response contains an error item; lower-level client APIs may expose per-item status. Do not assume the entire list succeeded just because the outer HTTP request was accepted.

For independent UI sections, the service can handle errors per group so a secondary query failure does not lose all results, if the abstraction API allows identifying individual errors. If the abstraction throws an exception for the whole operation, consider executing queries separately or using lower-level client responses when independent error handling is needed.

## 7. Optimizing Request Count and Returned Data

### 7.1. Fetch Only Necessary Fields

If the UI only displays name and price, there is no need to load every large field in the document. You can use source filtering or a projection mechanism supported by the query API.

How source includes are configured on the NativeQuery builder may vary by client version. Check builder support for source filtering and verify that entity mapping can still construct valid objects from the selected fields.

If required fields or constructor properties are omitted, objects may be created with default/null values. Therefore, source filtering should go hand in hand with clear DTO or entity projection design.

### 7.2. Limit Page Size

Do not fetch thousands of documents just because an API allows it. Set page size limits at the service layer and validate input parameters.

~~~java
int safePage = Math.max(page, 0);
int safeSize = Math.min(Math.max(size, 1), 100);

Pageable pageable = PageRequest.of(safePage, safeSize);
~~~

Upper bounds should be chosen based on document size, latency, and UI requirements. For exports or batch processing, use an appropriate traversal mechanism rather than expanding page size indefinitely.

### 7.3. Avoid Unnecessary Count Calls

A screen might call search and then call count separately for the same query even though SearchHits already contains total hits. This creates extra load and requests.

Determine what the UI actually needs:

- Displaying only a page of results: search may be enough.
- Displaying an exact total according to requirements: use appropriate total-hit tracking or count.
- Checking only if results exist: limit search to one hit or use exists/count appropriately.
- Grouping statistics: use aggregations.

### 7.4. Multi-Search Is Not Always Faster

Multi-search reduces round trips, but the number of sub-queries, response size, and total work on shards still exist. An overly large multi-search request can create load bursts on the cluster.

Limit the number of queries in a batch, avoid repeating identical queries, and measure end-to-end latency. If queries have different priorities, separate them into groups to better control timeouts and failures.

## 8. Choosing Index and Entity Type

### 8.1. Using the Index from @Document

For an entity with:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // ...
}
~~~

the call:

~~~java
operations.search(query, ProductDocument.class);
~~~

can obtain the index from entity metadata.

### 8.2. Using IndexCoordinates

When the index is chosen dynamically:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-v2");

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

This approach is commonly used with aliases or versioned indices. Ensure the target index has a mapping compatible with ProductDocument. If the index contains documents with a different schema, the converter may fail to map data accurately.

### 8.3. One Entity, Multiple Indices

You can search the same document type across multiple indices when schemas are compatible:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-v1", "products-v2");

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

This demonstrates selecting multiple indices in overloads supporting IndexCoordinates. Before using, check your API version and ensure mappings across the indices are sufficiently compatible. If fields share a name but differ in type or structure, results may error or be inconsistent.

## 9. Processing SearchHits in the Service Layer

### 9.1. Creating Response DTOs

You do not have to return SearchHits or Elasticsearch entities directly from controllers. You can convert them into API-appropriate DTOs:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    float score
) {
}
~~~

Conversion:

~~~java
List<ProductSearchItem> items = searchHits.getSearchHits()
    .stream()
    .map(hit -> new ProductSearchItem(
        hit.getId(),
        hit.getContent().getName(),
        hit.getContent().getPrice(),
        hit.getScore()
    ))
    .toList();
~~~

This keeps the API decoupled from internal Spring Data metadata. If highlights are needed, you can add a fragments field to the DTO after sanitizing/escaping the content for display.

### 9.2. Distinguishing Total Hits from Returned Hits

Example response DTO for a page:

~~~java
public record ProductSearchResponse(
    List<ProductSearchItem> items,
    long totalHits,
    int page,
    int size
) {
}
~~~

The service can read total from SearchHits and content from the hit list:

~~~java
ProductSearchResponse response = new ProductSearchResponse(
    items,
    searchHits.getTotalHits(),
    pageable.getPageNumber(),
    pageable.getPageSize()
);
~~~

If total-hit tracking is capped, clearly communicate the semantics of the total result count to the client rather than presenting it as an exact absolute figure.

## 10. Testing Search, Count, and Multi-Search

### 10.1. Unit Tests for Query-Building Logic

You can test service logic for building queries, normalizing inputs, capping page sizes, and converting results to DTOs in isolation. These tests do not replace integration tests against Elasticsearch.

### 10.2. Integration Tests with Elasticsearch

To verify Query DSL and mappings, run against a compatible Elasticsearch instance, such as a test container or dedicated test environment.

A basic scenario:

1. Create the index with the required mapping and analyzers.
2. Index a set of sample documents.
3. Execute search and assert returned IDs/contents.
4. Execute count with the same conditions and compare totals.
5. Send multi-search with two different queries and verify each result group.
6. Test pagination, sorting, and missing fields.
7. Test queries with no results.
8. Test a failing sub-query in multi-search according to how your API version reports errors.
9. Clean up the test index when finished.

Do not merely mock ElasticsearchOperations and conclude the Query DSL is right. Mocks test how the service calls the API; integration tests verify Elasticsearch executes the actual query and mapping.

### 10.3. Datasets Should Include Edge Cases

Include documents that:

- Omit optional fields.
- Have null fields or empty collections.
- Contain mixed casing, diacritics, and special characters.
- Have numeric values on filter boundaries.
- Belong to different categories and statuses.
- Have long text or nested objects if used by queries.
- Have duplicate IDs on rewrite to test update semantics.

Such data helps uncover discrepancies between expected queries, analyzers, mappings, and real data.

## 11. Common Pitfalls

| Symptom | Possible Cause | Troubleshooting |
|---|---|---|
| Search returns empty list | Query mismatch, wrong field name, or incompatible analyzer | Check mapping, _analyze, and Query DSL |
| Search has hits but content misses fields | Source filtering or document lacks the field | Check _source, mapping, and projection |
| Total hits differs from list size | Query uses pagination | Use getTotalHits for total and getSearchHits().size() for current page |
| Count lower than expected right after write | Document not yet searchable due to refresh timing | Check refresh behavior and consistency requirements |
| Count and search use different criteria | Query logic built separately in two places | Reuse query/filter builder |
| Sorting does not work | Text field does not support sorting or field missing | Use a keyword field and check mapping |
| Search score is 0 or unexpected | Query/filter context or scoring strategy | Check bool clauses and query type |
| Multi-search misses a result group | Sub-query failed or item responses handled differently | Check per-item errors according to API/client version |
| Multi-search too slow | Too many sub-queries or each query is heavy | Reduce query count, optimize each query, and measure load |
| Error when specifying dynamic index | Target index mapping incompatible with entity | Check IndexCoordinates and live mapping |
| Search times out | Broad query, heavy wildcard/aggregation, or overloaded cluster | Inspect profile/query, shard load, and timeouts |

When investigating, inspect the actual request DSL and response from Elasticsearch. Do not look only at method names or Java Query objects.

## 12. API Selection Workflow

When building a search feature, determine in order:

1. **Need documents or only a count?** If only a count is needed, use count. If content and metadata are needed, use search.
2. **One query or multiple independent queries?** A single set of criteria uses search with a bool query; multiple separate result sets can use multi-search.
3. **What metadata is needed?** If scores, highlights, or sort values are needed, retain SearchHits/SearchHit.
4. **Which index is the target?** Use @Document metadata when fixed; use IndexCoordinates when dynamic selection is needed.
5. **How should pagination work?** Pageable for early/normal pages; search_after or scroll for large data traversal.
6. **Is total hits needed?** Use total hits if search already tracks enough; call count when an independent count is needed.
7. **Is the query dynamic and complex?** Choose NativeQuery, CriteriaQuery, or StringQuery as required.

## 13. Key Takeaways

- ElasticsearchOperations provides high-level APIs for search, count, and multi-search.
- Query describes criteria; NativeQuery is suitable when full Query DSL is needed.
- Search returns SearchHits, where each SearchHit contains entity content and metadata such as ID, score, highlights, or sort values.
- Distinguish total hits from the number of hits actually returned on a page.
- Count only counts matching documents without loading full documents.
- Multi-search bundles multiple independent queries into one request; it is not a bool query and not a transaction.
- IndexCoordinates allows explicitly selecting an index or alias.
- Limit page size, avoid redundant count/search calls, and measure multi-search performance under workload.
- Integration tests with Elasticsearch are essential to validate mappings and actual Query DSL.
- API signatures and builders may vary across Spring Data Elasticsearch / Elasticsearch Java Client versions; verify project dependencies before applying examples.

Understanding the differences between search, count, and multi-search allows you to choose the right operation for each screen or task, retrieve only necessary data, and better control the number of requests sent to the Elasticsearch cluster.
