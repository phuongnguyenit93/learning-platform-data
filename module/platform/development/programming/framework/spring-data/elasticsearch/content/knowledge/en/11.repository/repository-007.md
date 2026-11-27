# Supported Return Types and Missing-Data Contracts

Spring Data Elasticsearch repository methods can return several different types, depending on how many results are expected and how much search metadata is needed. Choosing the right return type helps application code clearly express an operation's contract: whether one document was found, no document was found, multiple results exist, or pagination and relevance scores are needed.

For finding a single document by ID, **Optional<T>** is usually the clearest choice because the document might not exist. For queries returning multiple documents, you can use **List<T>**, **Iterable<T>**, **Page<T>**, or specialized search result types. Spring Data Elasticsearch also offers reactive repositories, where **Mono<T>** and **Flux<T>** represent asynchronous results.

This lesson covers common return types, what missing data means, how to handle empty results, and the errors that arise when the return contract does not match the actual number of documents.

## 1. Choosing a Return Type by Result Cardinality

Before declaring a repository method, determine how many documents the query can return:

- Zero or at most one document.
- Zero or multiple documents.
- One page within a large result set.
- Search results accompanied by metadata such as relevance scores, total hits, or highlights.
- A stream of data consumed incrementally.

Common return-type groups:

| Need | Common return type | When no results exist |
|---|---|---|
| Find by ID | **Optional<T>** | **Optional.empty()** |
| Find at most one document | **Optional<T>** or **T** | Empty Optional or null depending on declared type |
| Retrieve multiple documents | **List<T>**, **Iterable<T>** | Empty collection |
| Retrieve one page | **Page<T>** | Empty Page |
| Retrieve one chunk and know if a next page exists | **Slice<T>** | Empty Slice |
| Retrieve per-hit metadata | **SearchHits<T>**, **SearchHit<T>** | SearchHits with no hits |
| Reactive search | **Mono<T>**, **Flux<T>** | Publisher completes without emitting items |
| Existence check | **boolean** or **Mono<Boolean>** | false |
| Count results | **long** or **Mono<Long>** | 0 |

Do not pick a return type simply because it is convenient to type. Choose the type that accurately models valid result cardinality and how the application handles missing documents.

## 2. Finding One Document: Optional<T>

**Optional<T>** represents a value that may or may not be present. This is the right contract when a query expects at most one document.

Example repository:

~~~java
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);
}
~~~

Calling the method:

~~~java
Optional<Product> result = productRepository.findBySku("KB-1001");

if (result.isPresent()) {
    Product product = result.get();
    System.out.println(product.getName());
} else {
    System.out.println("Product not found");
}
~~~

It can be handled concisely using Optional methods:

~~~java
Product product = productRepository.findBySku("KB-1001")
        .orElseThrow(() -> new ProductNotFoundException("KB-1001"));
~~~

Or by supplying a default value:

~~~java
Product product = productRepository.findBySku("KB-1001")
        .orElseGet(Product::new);
~~~

Only supply a default value when the business domain genuinely defines a valid default object. Do not instantiate an empty Product merely to avoid handling the not-found case, as that obscures the fact that the document does not exist.

### findById and findAllById

Inherited CRUD methods carry important contracts:

~~~java
Optional<Product> product = productRepository.findById("p-1001");

Iterable<Product> products =
        productRepository.findAllById(List.of("p-1001", "p-1002"));
~~~

- **findById(id)** returns Optional. If the ID does not exist, the result is an empty Optional.
- **findAllById(ids)** returns whichever documents are found from the ID list. Missing IDs do not produce placeholder elements or null entries in the result.
- The order of documents returned by **findAllById** does not necessarily match the input ID order. If business logic needs input order preserved, sort or reconstruct the order by ID after receiving the results.

Example handling multiple IDs:

~~~java
List<String> ids = List.of("p-1001", "p-1002", "p-9999");

List<Product> found = new ArrayList<>();
productRepository.findAllById(ids).forEach(found::add);

Set<String> foundIds = found.stream()
        .map(Product::getId)
        .collect(Collectors.toSet());

List<String> missingIds = ids.stream()
        .filter(id -> !foundIds.contains(id))
        .toList();
~~~

This makes it easy to distinguish found IDs from IDs without matching documents. If the application must raise an error whenever any ID is missing, compare the count or ID sets after querying.

## 3. Querying One Document with Type T

A repository query method can return the entity type directly:

~~~java
Product findBySku(String sku);
~~~

The contract of a single-entity return type is that the query must match at most one document. When nothing is found, Spring Data may return **null**. If more than one result matches while the method declares a single value, the framework throws a result-size exception, typically **IncorrectResultSizeDataAccessException**.

Therefore, when not-found is a normal case, **Optional<Product>** is usually clearer and safer.

Comparison:

~~~java
// May return null if not found.
Product findBySku(String sku);

// Missing result is represented explicitly.
Optional<Product> findBySku(String sku);
~~~

Do not use a single-entity return type when the query criteria do not guarantee uniqueness. For example, if multiple products share the same category, the following method is inappropriate:

~~~java
// Inappropriate if a category can have multiple products.
Product findByCategory(String category);
~~~

Change it to a collection or multi-result return type:

~~~java
List<Product> findByCategory(String category);
~~~

If business rules require SKU uniqueness, enforce uniqueness through data rules and write workflows. Elasticsearch does not automatically enforce a unique constraint on an ordinary field the way a relational database unique constraint does.

## 4. Returning Multiple Documents: List and Iterable

When a query can return multiple documents, use **List<T>** or **Iterable<T>**:

~~~java
List<Product> findByCategory(String category);

Iterable<Product> findAll();
~~~

**List<T>** is convenient when you need indexed access, Stream API processing, or direct return values from services/controllers. If the query matches no documents, an empty collection is returned.

Example:

~~~java
List<Product> products =
        productRepository.findByCategory("accessories");

if (products.isEmpty()) {
    System.out.println("No products in category");
} else {
    products.forEach(product ->
            System.out.println(product.getName()));
}
~~~

**Iterable<T>** fits general CRUD APIs such as **findAll()**. It allows iterating over results without requiring the List interface.

Do not assume **findAll()** can always load an entire large index safely. Consider default result limits, pagination, and memory usage. For large datasets, use **Pageable**, a scrolling mechanism, or an appropriate search API.

### What does an empty collection mean?

An empty collection indicates the query executed and matched zero documents. This is a valid outcome, not an error.

Example:

~~~java
List<Product> products = productRepository.findByCategory("unknown");

if (products.isEmpty()) {
    // Return empty list to client.
}
~~~

Do not return **null** instead of an empty collection. Returning an empty collection lets callers iterate or check **isEmpty()** without defensive null checks.

## 5. Pagination: Page<T> and Pageable

When datasets can grow large, repositories should return pages instead of loading every result.

Method declaration:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Page<Product> findByCategory(String category, Pageable pageable);
}
~~~

Calling the query:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "name")
);

Page<Product> page =
        productRepository.findByCategory("accessories", pageable);

List<Product> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

The first page has index **0**. The example above requests up to 20 products in the accessories category, sorted ascending by name.

**Page<T>** provides:

- **getContent()**: list of documents on the current page.
- **getNumber()**: current page index.
- **getSize()**: requested page size.
- **getNumberOfElements()**: actual number of items on the page.
- **getTotalElements()**: total number of items matching the query.
- **getTotalPages()**: total number of pages.
- **hasNext()** and **hasPrevious()**: check whether a next or previous page exists.

When no documents match, Page still exists with empty content:

~~~java
Page<Product> page =
        productRepository.findByCategory(
                "unknown",
                PageRequest.of(0, 20)
        );

if (page.isEmpty()) {
    System.out.println("No matching products found");
}
~~~

Total elements equal 0 and total pages equal 0. There is no need to null-check Page before using it.

### Page and the cost of counting total results

**Page<T>** usually needs the total result count to compute **getTotalElements()** and **getTotalPages()**. That can trigger an extra count operation or total-hits tracking, depending on implementation and version.

If the UI only needs to know whether more results exist, **Slice<T>** may be a better fit.

## 6. Slice<T> When Total Counts Are Not Needed

**Slice<T>** represents a slice of results. It provides the current content and whether a next page exists, without requiring total element and total page counts like Page.

Declaration:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Product> findByCategory(String category, Pageable pageable);
~~~

Calling the method:

~~~java
Slice<Product> slice =
        productRepository.findByCategory(
                "accessories",
                PageRequest.of(0, 20)
        );

List<Product> products = slice.getContent();

if (slice.hasNext()) {
    Pageable nextPage = slice.nextPageable();
    // Fetch the next slice of results.
}
~~~

When no results exist, Slice is empty and **hasNext()** returns false.

Use Slice when the UI provides a "Load more" button or incremental loading without displaying total result counts. Exact Slice support in query methods depends on your Spring Data Elasticsearch version and query type; check your project's API documentation.

## 7. SearchHit and SearchHits: Preserving Search Metadata

When only entity objects are needed, **List<Product>** or **Page<Product>** may be enough. In full-text search, however, Elasticsearch returns important metadata such as:

- Document ID.
- Relevance score (**score**).
- Highlight snippets.
- Source index name.
- Sort values.
- Query-level result info and aggregations.

Spring Data Elasticsearch provides **SearchHit<T>** and **SearchHits<T>** to preserve this metadata.

**SearchHit<T>** represents a single hit:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;

SearchHit<Product> hit = ...;

Product product = hit.getContent();
String id = hit.getId();
float score = hit.getScore();
Map<String, List<String>> highlights = hit.getHighlightFields();
~~~

**SearchHits<T>** contains the collection of hits and overall metadata:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.SearchHit;

SearchHits<Product> searchHits = ...;

long totalHits = searchHits.getTotalHits();

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();
    System.out.println(product.getName() + " score=" + hit.getScore());
}
~~~

Unlike **List<Product>**, SearchHits retains the information Elasticsearch provides per match. This is useful when building search result pages with highlights or relevance-based ranking.

### Repository methods returning SearchHits

A query method can declare SearchHits if supported by your Spring Data Elasticsearch version:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> findByName(String name);
~~~

When using specialized return types, verify support for your query type and Spring Data Elasticsearch version. If repository query methods cannot express the required query construction, use **ElasticsearchOperations.search(...)** to build the query explicitly and receive SearchHits.

## 8. SearchPage and Paginating Search Results

When both pagination and per-hit metadata are needed, Spring Data Elasticsearch offers **SearchPage<T>**. This type combines pagination details with SearchHit items.

Example declaration according to version-supported APIs:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchPage;

SearchPage<Product> searchByName(String name, Pageable pageable);
~~~

SearchPage provides page details alongside hit contents. Each hit still retains its score and search metadata.

In some versions, SearchPage generics and SearchHit types appear differently in the API. Check the supported repository method signatures rather than guessing generics from examples targeting another version.

When you only need entities, Page or List is simpler. When you need scores, highlights, or metadata, SearchHits/SearchPage is the right choice.

## 9. Stream<T> and Consuming Large Results

Some repository query methods can return **Stream<T>** or **Stream<SearchHit<T>>**, depending on query type and version. Streams allow processing items incrementally in application code:

~~~java
try (Stream<Product> products =
             productRepository.streamByCategory("accessories")) {
    products.forEach(product ->
            process(product));
}
~~~

When a stream is backed by resources or an Elasticsearch scroll context, it must be closed after use. A try-with-resources block ensures close is called even if processing throws an exception.

Do not collect a large stream into a List if your goal is saving memory. Also do not keep streams open longer than necessary, as they can hold client or server resources.

Stream methods may depend on how Spring Data Elasticsearch implements scrolling in your version. If you need to scan very large datasets, consider **SearchHitsIterator<T>** or the appropriate scrolling API, and always close resources per the API contract.

## 10. Reactive Repositories: Mono and Flux

Spring Data Elasticsearch provides separate reactive repositories, typically declared with **ReactiveElasticsearchRepository**. Reactive repositories use Reactor to represent asynchronous results.

Example:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByCategory(String category);
}
~~~

Meaning:

- **Mono<Product>** emits at most one Product and then completes.
- **Flux<Product>** emits 0 or more Products and then completes.
- If a single document is not found, Mono completes without emitting a value.
- If a multi-document query has no matches, Flux completes without emitting items.

Example handling an empty Mono:

~~~java
Mono<Product> result = reactiveProductRepository.findBySku("KB-1001");

return result.switchIfEmpty(
        Mono.error(new ProductNotFoundException("KB-1001"))
);
~~~

Example handling an empty Flux:

~~~java
Flux<Product> products =
        reactiveProductRepository.findByCategory("unknown");

return products.switchIfEmpty(
        Flux.empty()
);
~~~

In the Flux case, **switchIfEmpty(Flux.empty())** does not alter the outcome; this example simply illustrates that emitting zero items is a valid completion state. If you need custom handling when a sequence is empty, use **collectList()** and inspect the list, or operators like **hasElements()** depending on business needs.

Do not call **block()** inside normal reactive pipelines without clear justification. **block()** waits synchronously for results and undermines the reactive model, especially on event-loop threads.

Reactive repositories and imperative repositories are distinct APIs. Do not declare an imperative repository expecting it to return Mono/Flux like a reactive repository.

## 11. Contracts When Data Does Not Exist

An essential part of repository design is clearly defining what happens when a document does not exist.

Common contracts:

| Return type | Contract when no data exists | How the caller handles it |
|---|---|---|
| **T** | May return null for single-result query methods with no match | Check null or switch to Optional |
| **Optional<T>** | Empty Optional | Use isPresent, orElse, or orElseThrow |
| **List<T>** | Empty list | Use isEmpty and return empty collection |
| **Iterable<T>** | No elements | Iterate collection; do not assume elements exist |
| **Page<T>** | Empty Page | Check isEmpty; totalElements is 0 |
| **Slice<T>** | Empty Slice, no next page | Check isEmpty and hasNext |
| **SearchHits<T>** | No hits | Check getSearchHits().isEmpty() or getTotalHits() |
| **Mono<T>** | Mono.empty() | Use switchIfEmpty, defaultIfEmpty, or handle in subscriber |
| **Flux<T>** | Flux.empty() | Use appropriate reactive operators |

Do not confuse "document not found" with "query failed." For example:

- No document matching a given ID is a valid business outcome.
- Being unable to connect to Elasticsearch is an infrastructure error.
- Malformed query syntax is a query error.
- Incompatible mappings can cause queries to fail.
- Insufficient account permissions can cause Elasticsearch to return access errors.

Do not catch every exception and return Optional.empty or an empty list. Doing so turns system failures into "no data found," making incidents hard to detect.

## 12. From Missing Results to API Responses

The repository is typically the data-access layer. The service decides the business meaning of missing documents, while the controller maps outcomes to HTTP responses.

Example service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product getRequiredProduct(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }
}
~~~

Business exception:

~~~java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
~~~

The controller can map the exception to HTTP 404:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    public ResponseEntity<Product> getById(@PathVariable String id) {
        return ResponseEntity.ok(service.getRequiredProduct(id));
    }
}
~~~

Use a global exception handler to translate **ProductNotFoundException** into a 404 response:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<String> handleNotFound(
            ProductNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(exception.getMessage());
    }
}
~~~

For endpoints returning lists, it is standard to return HTTP 200 with an empty array when no items match, per the API contract. Do not return 404 solely because a list query returned zero items; 404 is better suited to a single addressed resource that does not exist.

## 13. Queries Returning Multiple Results When a Method Expects One

A common mistake is declaring a single-value return type when the query condition is not unique.

Example:

~~~java
Optional<Product> findByCategory(String category);
~~~

If multiple products share the same category, the method cannot represent all results with Optional. Spring Data can throw **IncorrectResultSizeDataAccessException** when the match count exceeds one.

The fix is changing the return type:

~~~java
List<Product> findByCategory(String category);
~~~

If business rules truly need an arbitrary product or the first product in a deterministic order, declare the selection rule explicitly, such as a result-limiting method with an appropriate sort. Do not rely on Elasticsearch's default ordering, because search hits may be ranked by score or query rules.

Example:

~~~java
Optional<Product> findFirstByCategoryOrderByPriceAsc(String category);
~~~

Exact naming and support for keywords like **First**, **Top**, or **OrderBy** depend on query derivation in your Spring Data Elasticsearch version. When strict ordering control is needed, you can use Pageable of size 1 with Sort.

## 14. Return Types for count, exists, and delete

Repositories also provide methods returning numeric or boolean outcomes:

~~~java
long countByCategory(String category);

boolean existsBySku(String sku);

long deleteByCategory(String category);
~~~

Meaning:

- **countBy...** returns the number of matching documents. If none match, the result is 0.
- **existsBy...** returns true if any matching document exists, false otherwise.
- Derived delete methods can return void or the deleted document count depending on declaration and version support.

Example:

~~~java
long count = productRepository.countByCategory("accessories");

boolean exists = productRepository.existsBySku("KB-1001");

if (!exists) {
    System.out.println("SKU does not exist yet");
}
~~~

Do not call **count()** just to check whether data exists if the repository already has an appropriate **existsBy...** method. Exists queries express intent more clearly and avoid counting all matching documents.

For conditional deletes, clearly understand the query scope and method contract before invoking them. Avoid vague method names or conditions that might accidentally match an entire index.

## 15. Projections and Custom Return Types

Applications do not always need to load an entire entity. Projections let you retrieve only a subset of data suited to a view or task.

Example interface projection:

~~~java
public interface ProductSummary {
    String getId();
    String getName();
    Double getPrice();
}
~~~

A repository method can declare a projection type if projections are supported by the version and query type:

~~~java
List<ProductSummary> findByCategory(String category);
~~~

Projections keep the service layer dependent only on needed fields. However, distinguish Spring Data-level projection from whether Elasticsearch actually returns only part of `_source`. Depending on the implementation, mapping/conversion may still process the document's source. If you want to restrict fields returned by Elasticsearch itself, build a query with source filtering using the appropriate API.

When using DTOs or projections, property names and conversion rules must be compatible with the document mapping. Do not assume all interface projections or DTO projections behave identically across versions.

## 16. Choosing Return Types in a Real Repository

Example repository combining common return types:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Optional<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    Page<Product> findByCategoryAndPriceBetween(
            String category,
            Double minPrice,
            Double maxPrice,
            Pageable pageable);

    SearchHits<Product> findByName(String name);

    boolean existsBySku(String sku);

    long countByCategory(String category);
}
~~~

Usage:

~~~java
Optional<Product> product = repository.findBySku("KB-1001");

List<Product> accessories =
        repository.findByCategory("accessories");

Page<Product> page = repository.findByCategoryAndPriceBetween(
        "accessories",
        20.0,
        100.0,
        PageRequest.of(0, 20)
);

SearchHits<Product> hits = repository.findByName("wireless keyboard");

boolean skuExists = repository.existsBySku("KB-1001");

long categoryCount = repository.countByCategory("accessories");
~~~

Each return type communicates a clear contract. Code readers can immediately tell whether a method expects one document, multiple documents, a page of results, or search metadata.

## 17. Common Pitfalls When Choosing Return Types

| Symptom | Possible cause | Resolution |
|---|---|---|
| NullPointerException when reading result | Query method returns a bare entity and finds no document | Use Optional or null-check per contract |
| IncorrectResultSizeDataAccessException | Method returns a single object but query matches multiple documents | Switch to List/Page or limit results explicitly |
| Cannot tell if another page exists | Using List instead of Page/Slice | Use Page or Slice with Pageable |
| Cannot access scores or highlights | Returning only entities drops hit metadata | Use SearchHit/SearchHits |
| Large datasets spike memory usage | Loading all results into a List | Use pagination, streams, or suitable scrolling mechanisms |
| Streams hold resources too long | Stream not closed after consumption | Use try-with-resources |
| Reactive pipeline produces no value | Mono completes empty while caller assumes an element | Use switchIfEmpty or handle Mono.empty |
| Confusing missing data with connection failures | Catching exceptions and turning them into empty results | Separate business, query, and infrastructure errors |
| Repository method does not support desired type | Return type or query derivation differs in active version | Check version docs and use ElasticsearchOperations when needed |

## 18. Principles for Designing Data Contracts

When declaring repository methods, follow these principles:

1. Use **Optional<T>** for queries expecting at most one document where non-existence is valid.
2. Use **List<T>** or **Iterable<T>** when queries return multiple documents and pagination metadata is unnecessary.
3. Use **Page<T>** when the UI needs total counts and page info.
4. Use **Slice<T>** when you only need to know whether a next page exists.
5. Use **SearchHits<T>** or SearchHit types when scores, highlights, and Elasticsearch metadata are needed.
6. Use **Mono<T>** or **Flux<T>** in reactive repositories; do not mix with imperative APIs.
7. Use boolean and numeric types for existence or count queries.
8. Never return null for a collection when no results match; return an empty collection.
9. Never turn infrastructure exceptions into empty results.
10. Ensure return types align with the number of results the query can produce.

Exact supported return types depend on the Spring Data Elasticsearch version, repository kind, and query construction style. For SearchHits, SearchPage, Stream, projections, or reactive return types, consult the reference documentation for your project's exact version. When repository query methods cannot fully express your requirements, **ElasticsearchOperations** lets you build explicit queries and control return types more cleanly.

Designing return types is part of the data contract between the repository and the business layer. **Optional** explicitly signals possible non-existence of a single document; empty collections represent multi-result queries finding no elements; Page and Slice represent paginated data; SearchHits preserves Elasticsearch metadata; Mono and Flux represent reactive outcomes. Choosing these contracts accurately makes normal flows easy to handle, reduces null bugs, and cleanly separates missing data from Elasticsearch access failures.
