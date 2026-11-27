# Name Queries, @Query, and NativeQuery in Reactive Flows

A product search application may need to return multiple results by name, additionally filter by active status, or combine full-text search with business conditions. When using Spring Data Elasticsearch in the reactive model, read operations return Publishers such as **Mono** and **Flux**. Queries are still sent to Elasticsearch, while results flow into a reactive pipeline for asynchronous processing.

There are three common ways to construct queries:

- **Derived queries**: naming repository methods following Spring Data conventions, such as searching products by name.
- **@Query**: declaring JSON Query DSL directly on a repository method when the query structure should be explicit.
- **NativeQuery**: building queries with the Elasticsearch Java API Client and calling them via **ReactiveElasticsearchOperations** when greater flexibility is needed.

This lesson covers searching by name with reactive repositories, writing custom queries with @Query, building NativeQuery instances, reading results as entities or SearchHit objects, combining pagination and filters, and structuring reactive pipelines properly.

## 1. Reactive Queries in Spring Data Elasticsearch

In imperative data access, a method typically returns an entity or collection once the call finishes. In reactive data access, the method returns a Publisher describing the operation to be executed. With Spring Data Elasticsearch, the two common types are:

- **Mono<T>**: emits at most one element and completes.
- **Flux<T>**: emits zero to many elements and completes.

Example:

~~~java
Mono<Product> product = repository.findById("P-100");

Flux<Product> products = repository.findByName("Wireless Keyboard");
~~~

When calling these methods, the application receives a Publisher. The query is typically executed only upon subscription. The Publisher can be composed with Reactor operators before subscription occurs.

Overall flow:

~~~text
Controller / Service
        |
        v
Reactive repository or ReactiveElasticsearchOperations
        |
        v
Publisher: Mono / Flux
        |
        v
Elasticsearch reactive client
        |
        v
Elasticsearch query
        |
        v
Response and entity mapping
        |
        v
Elements emitted into the reactive pipeline
        |
        v
Subscriber
~~~

Reactivity does not change the meaning of Query DSL. It changes how the application receives and processes results, handles errors, manages cancellation, and regulates demand.

### Reactive Does Not Mean Queries Automatically Scan the Whole Index

Elasticsearch still applies search request result limits and pagination. A method returning Flux does not mean the request automatically fetches every document in the index. If the query does not specify a size or appropriate iteration mechanism, Elasticsearch still applies its default limit.

Distinguish between:

- Flux is the emission type within the application.
- Pageable/size is the limit on the search request.
- Scroll or an appropriate iteration mechanism is how large datasets are processed across multiple requests.

Do not use Flux as a substitute for pagination design or large data export strategies.

## 2. Declaring the Entity and Reactive Repository

Example Product entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters and setters
}
~~~

The **name** field is mapped as text to support full-text search. **status** is a keyword suited for exact conditions or filters. **active** is a boolean.

Reactive repository:

~~~java
public interface ProductReactiveRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByName(String name);

    Flux<Product> findByNameAndActive(String name, boolean active);

    Mono<Product> findFirstByName(String name);
}
~~~

Spring Data generates implementations for methods following naming conventions. You do not need to write implementations manually for supported derived queries.

### Choosing Mono or Flux Based on Cardinality

Use Flux when a query can return multiple products. Use Mono when at most one product is expected, such as looking up by a unique key or a method constrained with first/top.

If a query can match multiple documents yet the business method uses Mono, check the semantics and handle multi-result cases according to the method contract. Do not pick Mono just because the caller wants to grab the first element.

### Derived Queries and Field Semantics

Method names describe conditions, yet the exact query Spring Data generates depends on supported keywords, mappings, and versions. Do not assume every method searching a String field carries the exact same full-text relevance semantics as a match query.

For text fields, when analyzer-driven token matching is specifically required, write an explicit match query using @Query or NativeQuery. For keyword fields or keyword subfields, use appropriate exact-match conditions.

## 3. Searching by Name with Derived Queries

A simple repository method:

~~~java
Flux<Product> findByName(String name);
~~~

The caller can compose it into a pipeline:

~~~java
public Flux<Product> findProducts(String name) {
    return repository.findByName(name);
}
~~~

Because the method returns Flux, the service can filter or transform results with Reactor:

~~~java
public Flux<ProductSummary> findProductSummaries(String name) {
    return repository.findByName(name)
        .filter(Product::isActive)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName(),
            product.getPrice()
        ));
}
~~~

This example filters active products at the application layer after results have been read. If the active condition can be pushed down to Elasticsearch, include it in the query to reduce documents transferred over the network and entities mapped.

### Combining Conditions in Method Names

Example:

~~~java
Flux<Product> findByNameAndActive(String name, boolean active);

Flux<Product> findByStatusAndActive(String status, boolean active);
~~~

Derived queries work well when conditions are simple, stable, and supported by Spring Data. When a query needs multiple bool branches, boosts, nested queries, ranges, or explicit full-text options, long method names become hard to express. In those cases, use @Query or NativeQuery.

### Searching by Exact Name vs. Text Content

There are two distinct requirements:

- Searching by exact name, such as matching the exact string Wireless Keyboard.
- Searching content containing the tokens Wireless and Keyboard according to an analyzer.

If name is text, a match query usually fits full-text search. When exact matching is needed, the mapping can define a multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

You can then use name for full-text search and name.keyword for exact filtering or sorting. Only reference a keyword subfield if the actual mapping defines it.

## 4. Declaring @Query on a Reactive Repository

The **@Query** annotation lets you declare JSON Query DSL on a repository method. The method still returns Mono or Flux; the annotation simply specifies the query sent to Elasticsearch.

Example matching by name:

~~~java
public interface ProductReactiveRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0"
            }
          }
        }
        """)
    Flux<Product> searchByName(String name);
}
~~~

The **?0** placeholder references the method's first parameter. With multiple parameters, placeholder indices match parameter positions according to Spring Data's binding rules.

Calling the method:

~~~java
Flux<Product> products =
    repository.searchByName("wireless keyboard");
~~~

Spring Data binds parameters into the query and wraps results in a Publisher matching the return type. Check placeholder syntax and supported parameter types against your project's Spring Data Elasticsearch version.

### Combining Match with a Filter

Example finding only active products:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": "?0"
              }
            }
          }
        ],
        "filter": [
          {
            "term": {
              "active": true
            }
          }
        ]
      }
    }
    """)
Flux<Product> searchActiveByName(String name);
~~~

In this query:

- **must** contains the match query on the name field.
- **filter** restricts active using a boolean condition.
- The match query contributes to relevance scoring.
- The filter narrows documents without calculating relevance scores for that condition.

Pushing filterable conditions down into Elasticsearch reduces the number of hits the application must receive and process.

### Exact Match on a Keyword Subfield

If you want an exact match using a keyword subfield:

~~~java
@Query("""
    {
      "term": {
        "name.keyword": "?0"
      }
    }
    """)
Flux<Product> findByExactName(String name);
~~~

This query only works as intended if the mapping actually includes a name.keyword field. If the field is only text without a keyword subfield, the query will not behave as expected.

### @Query Fits Static Query Structures

@Query is helpful when the query structure is relatively fixed yet cannot or should not be expressed as a derived method. Examples:

- match or multi_match across a group of fields.
- bool queries with must, filter, and must_not.
- range queries combined with text conditions.
- nested queries with a fixed path.
- queries with fixed boosts or options.

When the query structure changes substantially based on runtime inputs, NativeQuery is usually easier to organize.

## 5. Parameters in @Query and Passing Values

Placeholders in @Query substitute method arguments into the JSON query:

~~~java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
Flux<Product> searchByName(String name);
~~~

When invoked:

~~~java
repository.searchByName("mechanical keyboard");
~~~

Parameter values are bound via Spring Data Elasticsearch's parameter binding mechanism. Never concatenate user strings into JSON queries to build dynamic queries.

With multiple parameters:

~~~java
@Query("""
    {
      "bool": {
        "must": [
          {
            "match": {
              "name": {
                "query": "?0"
              }
            }
          }
        ],
        "filter": [
          {
            "term": {
              "status": "?1"
            }
          }
        ]
      }
    }
    """)
Flux<Product> searchByNameAndStatus(String name, String status);
~~~

The first placeholder corresponds to name, and the second corresponds to status.

### JSON Queries Have Fixed Structure

@Query is not a general-purpose Query DSL builder. The JSON structure is fixed in the annotation and placeholders only substitute supported values. If you need to add or omit query clauses conditionally, building a NativeQuery in the service is cleaner.

Never pass raw JSON fragments from clients into placeholders to dictate query structure. APIs should accept typed business parameters, validate them, and construct queries server-side.

### Handling Special Characters

Strings containing quotes, escape characters, spaces, or Unicode characters must be bound safely. Rely on the framework's parameter binding and test edge values. Avoid manual escaping via string replacement or concatenation, which easily produces invalid JSON or unintended query semantics.

## 6. Using NativeQuery with ReactiveElasticsearchOperations

When you need to build queries in Java rather than writing JSON inside annotations, use **NativeQuery**. This suits queries with multiple branches, runtime parameters, or combinations of Elasticsearch query types.

Example injecting reactive operations:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Creating a match-by-name query:

~~~java
public Flux<Product> searchByName(String name) {
    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .build();

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

In this example:

- NativeQuery holds the query model built using the Elasticsearch Java API Client.
- ReactiveElasticsearchOperations executes the query via the reactive API.
- search returns a Flux of SearchHit items.
- map extracts the entity content from each hit.

The NativeQuery package and builder types depend on your Spring Data Elasticsearch release train. In modern versions, NativeQuery resides in the ELC client package and uses the Elasticsearch Java API Client query builders. Check your project dependencies before copying imports.

### Combining Bool, Match, and Filter

Example searching by name while restricting to active products within a price range:

~~~java
public Flux<Product> searchActiveProducts(
        String name,
        double minPrice,
        double maxPrice) {

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .must(m -> m.match(mm -> mm
                .field("name")
                .query(name)
            ))
            .filter(f -> f.term(t -> t
                .field("active")
                .value(true)
            ))
            .filter(f -> f.range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(minPrice)
                    .lte(maxPrice)
                )
            ))
        ))
        .build();

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

This example uses the modern Elasticsearch Java API Client builders. RangeQuery structure and overloads may vary across client versions. The query's meaning is matching name, filtering active, and filtering price between minPrice and maxPrice.

### Why Use NativeQuery Instead of String-Concatenated JSON?

NativeQuery offers several advantages:

- Queries are represented with the client's Java types.
- IDEs provide autocomplete and the compiler catches structural errors.
- Conditional query branches are easy to assemble.
- Query fragments are easy to reuse.
- No manual JSON string escaping is required.
- Spring Data mapping and conversion via ReactiveElasticsearchOperations remain intact.

NativeQuery itself does not make a query reactive. Reactivity comes from executing it through ReactiveElasticsearchOperations and keeping results in Mono/Flux.

## 7. Building Dynamic Queries from Input

Suppose a search API lets users pass optional name, status, and price range parameters. You can construct a bool query that adds filters only when parameters have values.

Pseudocode illustrating structure:

~~~java
public Flux<Product> search(ProductSearchCriteria criteria) {
    NativeQuery query = buildQuery(criteria);

    return operations.search(query, Product.class)
        .map(SearchHit::getContent);
}
~~~

A dedicated builder method keeps query construction separate:

~~~java
private NativeQuery buildQuery(ProductSearchCriteria criteria) {
    // Build a bool query from validated criteria.
    // Add match on name if keyword is present.
    // Add term filter on status if status is present.
    // Add range filter when min/max price are present.
    // Add pageable/sort as requested.
    // Return NativeQuery.
}
~~~

This is pseudocode outlining service structure. When implementing, construct Query objects using the Java API Client builders for your version.

Validate input before building the query:

- Keyword does not exceed maximum length.
- minPrice is not greater than maxPrice.
- Status belongs to an allowed set of values.
- Page number is non-negative.
- Page size stays within bounds.
- Sort field belongs to a server-side allowlist.

Never let clients pass arbitrary field names directly into Query DSL. That can allow APIs to query internal fields or trigger expensive workloads.

## 8. Reading SearchHit and SearchHits in Reactive Flows

Two result types are commonly useful:

**Flux<SearchHit<Product>>** preserves per-hit metadata such as ID, score, sort values, and highlights when requested by the query.

**Flux<Product>** retains only entity content after mapping from SearchHit.

Example preserving SearchHit:

~~~java
public Flux<SearchHit<Product>> searchHits(String name) {
    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .build();

    return operations.search(query, Product.class);
}
~~~

If only the entity is needed:

~~~java
public Flux<Product> searchProducts(String name) {
    return searchHits(name)
        .map(SearchHit::getContent);
}
~~~

Preserve SearchHit when you need:

- Score to display or analyze relevance.
- Highlight fragments to emphasize matched terms.
- Sort values to support cursor pagination.
- Document ID or index metadata.
- Inner hits or other request-specific metadata.

Do not map to entities too early if the caller still needs hit metadata.

### Retrieving SearchHits with Total Result Counts

In modern reactive APIs, ReactiveElasticsearchOperations provides a page-oriented search method that can return Mono<SearchHits<T>>. Exact method names and overloads should be verified against your version.

Usage example:

~~~java
Mono<SearchHits<Product>> searchPage(NativeQuery query) {
    return operations.searchForPage(query, Product.class);
}
~~~

SearchHits holds the list of SearchHit items along with details such as totalHits, maxScore, and aggregation metadata depending on the query. If you only use Flux<SearchHit<T>>, the caller receives emitted hits without as convenient access to aggregated response metadata as SearchHits provides.

## 9. Pagination with NativeQuery

Elasticsearch search requests normally cap returned hits. You can configure Pageable on NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query(name)
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

PageRequest.of(0, 20) requests the first page with up to 20 results. Subsequent pages increment the page index.

In a service, you can accept page and size from the API while validating limits before creating a PageRequest:

~~~java
public Flux<SearchHit<Product>> search(
        String name,
        int page,
        int size) {

    if (page < 0 || size < 1 || size > 100) {
        return Flux.error(
            new IllegalArgumentException("Invalid page request")
        );
    }

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
            .field("name")
            .query(name)
        ))
        .withPageable(PageRequest.of(page, size))
        .build();

    return operations.search(query, Product.class);
}
~~~

The size cap is an illustrative application rule. Your maximum should reflect SLAs, Elasticsearch configuration, and entity size.

### Deep Pagination

from/size has limits and grows more expensive at deep pages. For large result sets, consider search_after with stable sorting or scroll/PIT mechanisms compatible with your Elasticsearch version.

When using search_after:

- Query and sort must remain consistent across calls.
- Sort should include a stable tie-breaker.
- Retain all sort values from the last hit.
- Do not recompute sort values from the entity.
- Handle index changes during traversal if a consistent snapshot is required.

Reactive Publishers do not solve deep pagination by themselves. They only dictate how the application consumes results.

### Page<T> Is Not Always Needed

In reactive repositories, synchronous Page<T> types do not fit the asynchronous multi-element model as a single returned collection. You can use Flux<T> with Pageable, or search APIs returning SearchHits/Mono<SearchHits<T>> depending on metadata needs and version.

When a response needs content, totalHits, and page metadata, design a dedicated DTO built from search results instead of forcing an imperative Page type into a reactive pipeline.

## 10. Combining Sort with Name Queries

You can add sorting to NativeQuery, for instance sorting by price or by a keyword field. Sorting by price ascending requires the price field to have a numeric mapping:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query(name)
    ))
    .withSort(s -> s.field(f -> f
        .field("price")
        .order(SortOrder.Asc)
    ))
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Sort builder structure depends on your Java API Client version. If sorting by name, use a keyword subfield instead of a text field unsuitable for sorting.

Sorting can change the effect of relevance. If a query matches by name yet sorts by price, result order is governed by price rather than score. If you want relevance first and then price, declare sorts in that order.

Never accept raw sort field names from users without an allowlist. The server should map options like priceAsc or nameAsc to permitted fields.

## 11. Combining Highlights with Reactive Queries

When the UI needs to show highlighted keywords, the query can request highlights. With NativeQuery, configure highlighting using the Spring Data/Java API Client abstraction for your version.

Results should retain SearchHit:

~~~java
Flux<SearchHit<Product>> hits =
    operations.search(queryWithHighlight, Product.class);
~~~

Then read the entity and highlight fields:

~~~java
return hits.map(hit -> {
    Product product = hit.getContent();

    List<String> nameFragments =
        hit.getHighlightFields()
            .getOrDefault("name", List.of());

    return new ProductSearchItem(
        product.getId(),
        product.getName(),
        nameFragments
    );
});
~~~

DTO example:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    List<String> nameHighlights
) {}
~~~

Do not map SearchHit to the entity and discard metadata if the API needs fragments. Also, highlight fragments may contain markup; the frontend must render them following the application's HTML safety policy.

## 12. Reactive Pipelines: map, flatMap, and filter

Once the repository or Operations emits results, use Reactor operators to process them.

### map for Synchronous Transformations

~~~java
Flux<ProductSummary> summaries =
    repository.findByName(name)
        .map(product -> new ProductSummary(
            product.getId(),
            product.getName()
        ));
~~~

map fits when each element is transformed directly within the pipeline without invoking another Publisher.

### flatMap for Subsequent Reactive Operations

Suppose you need inventory details from a reactive service:

~~~java
Flux<ProductAvailability> results =
    repository.findByName(name)
        .flatMap(product ->
            inventoryService.findAvailability(product.getId())
                .map(stock -> new ProductAvailability(product, stock))
        );
~~~

flatMap flattens inner Publishers into a single result Flux. If input ordering must be preserved, consider concatMap or an order-preserving alternative rather than defaulting to flatMap.

### filter to Exclude Results in the Application

~~~java
Flux<Product> availableProducts =
    repository.findByName(name)
        .filter(Product::isActive);
~~~

If active is an important search condition, it is better to push it into the Elasticsearch query to reduce transferred data. filter in the reactive pipeline fits conditions evaluated after receiving entities or conditions that cannot be expressed in the query.

### switchIfEmpty for No-Result Cases

~~~java
Mono<Product> findFeaturedProduct(String name) {
    return repository.findFirstByName(name)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(name)
        ));
}
~~~

Use switchIfEmpty when business logic needs to translate an empty state into a specific result or error.

## 13. Cold Publishers, subscribe, and block

Reactive repositories typically return lazy Publishers. Without a subscriber, the operation may never execute.

Example:

~~~java
Flux<Product> products = repository.findByName("keyboard");
~~~

This line only creates a Publisher. When the web framework subscribes to the Publisher returned by the controller, the query executes.

A WebFlux controller can return it directly:

~~~java
@GetMapping("/products")
public Flux<Product> search(@RequestParam String name) {
    return searchService.search(name);
}
~~~

There is no need to call subscribe in the controller or service. The web framework manages subscription and writes results to the response.

### Avoid Manual subscribe in Services

Avoid:

~~~java
public void search(String name) {
    repository.findByName(name)
        .subscribe(product -> log.info("Found {}", product.getId()));
}
~~~

This detaches work from the caller's lifecycle, making errors and cancellation hard to manage, while a void method gives no indication of when the operation finishes.

Return the Publisher instead:

~~~java
public Flux<Product> search(String name) {
    return repository.findByName(name);
}
~~~

### Avoid block on Reactive Request Paths

Never call block() to wait for results inside a controller or service running on an event loop. Blocking forfeits non-blocking benefits and can cause stalls or deadlocks depending on the execution context.

If you must integrate an imperative library lacking a reactive API, isolate the blocking portion on an appropriate scheduler with a clear boundary. Never turn the entire pipeline synchronous just to call one blocking method.

## 14. Error Handling in Reactive Queries

Errors can arise while building queries, sending requests, mapping responses, or executing downstream operators. Reactive pipelines propagate errors via the onError signal.

Example translating technical errors into application errors:

~~~java
public Flux<Product> search(String name) {
    return repository.findByName(name)
        .onErrorMap(
            ElasticsearchException.class,
            ex -> new ProductSearchException(
                "Unable to search products",
                ex
            )
        );
}
~~~

Exact exception types depend on the client and Spring Data version. Choose exceptions matching your actual dependencies.

### Do Not Turn Every Error into an Empty List

The example below can mask system failures:

~~~java
return repository.findByName(name)
    .onErrorResume(ex -> Flux.empty());
~~~

When Elasticsearch loses connectivity or a query is malformed, the caller receives an empty result identical to having no matching products. This makes monitoring and business debugging difficult.

Only use an empty fallback when that is genuinely the business policy. Otherwise, propagate the error or map it to a meaningful domain exception.

### Retries

Transient errors can be retried with a bounded policy:

~~~java
return repository.findByName(name)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
    );
~~~

Do not retry every exception. Mapping errors, malformed queries, or authentication failures are rarely resolved by resending. For read-only searches, retries may suit transient network or overload errors; monitor retries to avoid amplifying load when the cluster is struggling.

### Logging and Metrics

Use doOnError, doOnNext, or appropriate instrumentation to record status. The doOn... operators are for observational side effects and should not be used to alter data flow or execute mandatory business logic without error handling.

Avoid logging full query parameters or documents if they contain sensitive data.

## 15. Cancellation and Backpressure

Reactive Streams has demand and cancellation mechanisms. When an HTTP client disconnects or downstream no longer needs data, the subscription may be canceled. Pipelines should allow cancellation to propagate to the source when supported by the API.

Key considerations:

- Do not spawn external work outside the Publisher that stays orphaned if the subscriber cancels.
- Avoid unmanaged nested subscriptions.
- Cap concurrency when using flatMap.
- Do not call collectList on very large result sets unless holding everything in memory is necessary.
- Use pagination or stream/scroll APIs suited to large datasets.
- Verify timeouts across client, server, and web layers.

Backpressure does not mean Elasticsearch only sends one document each time downstream requests one. The client may receive a page or response payload and emit hits using its own buffering mechanism. Monitor actual page sizes and memory usage.

## 16. When to Use ReactiveElasticsearchRepository vs. Operations?

| Need | Suitable choice |
|---|---|
| Search by a few fields via method names | ReactiveElasticsearchRepository |
| Static query requiring explicit JSON DSL | Repository method with @Query |
| Dynamic query with multiple bool/filter/range clauses | ReactiveElasticsearchOperations with NativeQuery |
| Need to preserve SearchHit metadata | ReactiveElasticsearchOperations.search |
| Need SearchHits and total hit metadata | Corresponding page-search API for your version |
| Need low-level request/response control | Direct reactive client with a dedicated adapter |
| Basic reactive CRUD | ReactiveElasticsearchRepository |

Repositories are usually the best choice for simple, stable queries. Operations fits when the service must construct queries dynamically or inspect rich metadata.

You do not need NativeQuery for every query. Conversely, do not force complex dynamic queries into long method names or overly large JSON annotations.

## 17. Testing Reactive Queries with StepVerifier

With Reactor, **StepVerifier** lets you verify emitted signals without calling block to retrieve results.

Example:

~~~java
@Test
void returnsProductsMatchingName() {
    StepVerifier.create(repository.findByName("keyboard"))
        .expectNextMatches(product ->
            product.getName().contains("keyboard")
        )
        .thenCancel()
        .verify();
}
~~~

This demonstrates verifying a Publisher. Test data, case sensitivity, and query semantics must match the index mapping and analyzer.

To verify the Publisher completes:

~~~java
StepVerifier.create(repository.findByName("no-such-product"))
    .verifyComplete();
~~~

### Testing @Query

Create test documents whose names contain search tokens, invoke the @Query method, and assert matching results. Also test cases with no matches and parameters containing special characters.

### Testing NativeQuery

Verify:

- Match query finds the right names.
- Active filter excludes inactive documents.
- Price range includes/excludes boundaries as expected.
- Pageable caps the number of hits properly.
- Sort orders by the right field and direction.
- SearchHit retains score/highlights/sort values when requested by the query.
- Mapping or Elasticsearch errors propagate as onError.
- Cancellation leaves no lingering side subscriptions.

### Integration Testing with Elasticsearch

Service unit tests can mock ReactiveElasticsearchOperations, yet mocks do not verify Query DSL or real mappings. Maintain integration tests against a compatible Elasticsearch version to verify derived queries, @Query, and NativeQuery.

After indexing test data, wait for a refresh or use an appropriate refresh policy before searching. Avoid relying on arbitrary timing via fixed sleeps when the test framework supports deterministic state transitions.

## 18. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Query does not execute despite calling method | Publisher was never subscribed to | Return Publisher to the framework or subscribe at an appropriate boundary |
| Service returns Flux with no data | Derived query semantics do not match requirements | Inspect mapping and actual generated query |
| Name search does not tokenize as expected | Using exact/term semantics on an unsuitable field | Use match on a text field |
| @Query reports invalid JSON | Placeholders or quotes produce malformed JSON | Use parameter binding and validate the query JSON |
| @Query binds parameters incorrectly | Misordered placeholders or unsupported types | Check parameter order and binding for your version |
| NativeQuery fails to compile | Java Client API changed across releases | Check dependency version and matching builders |
| Flux returns only a subset of hits | Query has a page size or default size limit | Configure Pageable or appropriate iteration mechanism |
| Missing scores or highlights | Mapped SearchHit to entity too early | Keep SearchHit until the layer needing metadata |
| Controller hangs or stalls | Called block or subscribed manually | Return Publisher and let the framework manage it |
| Elasticsearch errors turn into empty results | onErrorResume converts all errors to Flux.empty | Classify errors and preserve errors that must fail |
| Search slows down under flatMap | Concurrency too high or per-hit service calls | Cap concurrency or batch enrichment |
| Test misses newly indexed document | Index not refreshed yet | Wait for search visibility deterministically |

## 19. Complete Service Example for Name Search

Example service using NativeQuery to search by name, filter active products, and paginate results:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Flux<ProductSearchItem> search(
            String name,
            int page,
            int size) {

        if (name == null || name.isBlank()) {
            return Flux.error(
                new IllegalArgumentException("name is required")
            );
        }

        if (page < 0 || size < 1 || size > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid pagination")
            );
        }

        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                    .field("name")
                    .query(name)
                ))
                .filter(f -> f.term(t -> t
                    .field("active")
                    .value(true)
                ))
            ))
            .withPageable(PageRequest.of(page, size))
            .build();

        return operations.search(query, Product.class)
            .map(hit -> new ProductSearchItem(
                hit.getId(),
                hit.getContent().getName(),
                hit.getScore()
            ));
    }
}
~~~

DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    float score
) {}
~~~

The service encapsulates query construction and maps SearchHit to a DTO. The controller simply returns Flux:

~~~java
@GetMapping("/products/search")
public Flux<ProductSearchItem> search(
        @RequestParam String name,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    return productSearchService.search(name, page, size);
}
~~~

Exact imports and NativeQuery builder overloads depend on your Spring Data Elasticsearch and Java API Client versions. Use the exact APIs of your project's dependencies; this structure illustrates coordinating reactive operations with query builders and DTO mapping.

## 20. Checklist for Choosing a Reactive Query Approach

- [ ] Repository extends ReactiveElasticsearchRepository if reactive CRUD/query methods are needed.
- [ ] Methods return Mono for at most one result and Flux when multiple results are possible.
- [ ] Derived queries only use operators supported by the version.
- [ ] Name fields are mapped appropriately as text or keyword according to search needs.
- [ ] Use match for full-text search and term for exact/filter semantics.
- [ ] @Query has valid JSON DSL and properly positioned placeholders.
- [ ] Never concatenate user input directly into JSON queries.
- [ ] Use NativeQuery when query structure varies at runtime.
- [ ] Execute NativeQuery via ReactiveElasticsearchOperations to preserve reactive flow.
- [ ] Keep SearchHit when score, highlights, or sort values are needed.
- [ ] Configure Pageable and enforce explicit size limits.
- [ ] Do not confuse Flux with unbounded full-index reads.
- [ ] Never call subscribe or block inside reactive services or controllers.
- [ ] Classify errors before retrying or falling back.
- [ ] Control concurrency and memory when processing many hits.
- [ ] Maintain both StepVerifier unit tests and integration tests with compatible Elasticsearch.

Derived queries allow writing simple queries concisely via method names. @Query fits fixed-structure JSON Query DSL with bound parameters. NativeQuery builds queries via the Java API Client for dynamic conditions or complex queries, while ReactiveElasticsearchOperations keeps results as Flux/SearchHit. Choosing the right tool for query complexity, preserving Publishers across services and controllers, and explicitly handling pagination, errors, and cancellation keeps asynchronous search applications both fast and predictable in Elasticsearch.
