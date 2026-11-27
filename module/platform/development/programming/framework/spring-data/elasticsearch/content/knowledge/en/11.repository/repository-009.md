# Recognizing Repository Limits and When to Switch to Operations

Spring Data Elasticsearch provides the repository abstraction so applications can work with documents using familiar Java methods. For CRUD and common queries, repositories keep code concise, readable, and decoupled from Elasticsearch specifics.

However, repositories are not the right API for every search operation. When you need fine-grained control over complex Query DSL, runtime index or alias selection, reading aggregations, accessing hit metadata, combining dynamic conditions, or executing specialized Elasticsearch workflows, **ElasticsearchOperations** is usually the better fit.

The key is recognizing the boundary between the two abstractions. Repositories model domain-level data access; Operations provides deeper control over Elasticsearch operations. Both can coexist in the same application: repositories for standard paths and Operations for use cases requiring fine-grained control.

## 1. What Problems Do Repositories Solve?

A repository is a Spring Data abstraction allowing applications to work with a single entity type without managing HTTP requests or calling the Elasticsearch client in every service.

Example entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters, setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    Optional<Product> findByName(String name);
}
~~~

A service can use the repository as a regular dependency:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

Spring Data generates the repository implementation at startup. Services only need to know the entity type, ID type, and repository methods. Beneath the surface, Spring Data Elasticsearch components translate calls into the appropriate Elasticsearch operations.

Repositories are usually a good fit when:

- The use case is saving, reading, updating, or deleting documents.
- Query criteria are simple and clearly expressed by method names.
- A fixed query can be declared with **@Query**.
- Repository return types already contain all the data the service needs.
- The entity always targets the default index or alias declared in **@Document**.
- The service does not need low-level request control or special response sections.

Repositories make business code easier to read. Method names like **findByCategory** express data-access intent while keeping HTTP endpoints and request payloads out of the service.

## 2. Key Capabilities of Repositories

### Entity and ID-based CRUD

Repository interfaces provide foundational operations such as:

- **save(entity)** to save an entity.
- **saveAll(entities)** to save multiple entities.
- **findById(id)** to read by document ID.
- **existsById(id)** to check document existence.
- **findAll()** to read entities.
- **deleteById(id)** and **delete(entity)** to delete.
- **count()** to count within repository scope.

Foundational methods cover document lifecycles without manual request assembly. Remember that **findById** is a lookup by document ID; it is not equivalent to a full-text search.

### Derived queries from method names

Spring Data can parse method names and generate queries by convention:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndPriceLessThan(
        String category,
        Double maxPrice
    );

    List<Product> findByPriceBetween(
        Double minPrice,
        Double maxPrice
    );

    List<Product> findByNameContaining(String phrase);

    long countByCategory(String category);

    boolean existsByCategory(String category);
}
~~~

Derived queries fit simple, stable conditions that read clearly from the method name. When method names grow long, nest multiple conditions, or stop expressing business intent clearly, consider another way to represent the query.

Not every Spring Data JPA keyword shares the same semantics or support in Spring Data Elasticsearch. Check the list of supported query methods in your project version, especially for operations involving collections, nulls, nested fields, geo data, or full-text matching.

### Queries declared via annotations

For fixed queries that are awkward to express via method names, **@Query** can be used:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0",
              "operator": "and"
            }
          }
        }
        """)
    List<Product> searchName(String phrase);
}
~~~

The annotation places Query DSL close to the repository method. This works well when the query does not need dynamic construction and the return type stays simple.

However, JSON queries inside annotations have practical limitations:

- The query is bound to one method and hard to reuse as a composable query object.
- When optional branches multiply, JSON becomes hard to read and maintain.
- Complex dynamic parameters can be awkward to represent.
- Sorting, aggregations, highlighting, source filtering, and extra options bloat the annotation.
- Changing the query often means editing annotation strings and revalidating repository methods.

Once a query has multiple variants or is assembled from runtime inputs, consider Operations and query builders.

### Basic pagination and sorting

Repositories support paginated return types matching the query method and Spring Data version:

~~~java
Page<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

Services can pass page and sort settings:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
    productRepository.findByCategory("accessories", pageable);
~~~

This works well for standard pagination when results only need entities and page metadata. However, if you need sorting on complex fields, special multi-sort rules, missing-value handling, script sorts, or other Search API options, Operations gives clearer request control.

Property names used in Sort must align with mapping metadata and actual fields. For multi-fields, you may need an Elasticsearch path such as **name.keyword**. Check exact sort-property mapping behavior in your Spring Data API version.

## 3. Common Repository Limitations

Repositories provide an intentional abstraction. They cover common operations, yet do not necessarily expose every capability of the Elasticsearch Search API.

### Limit 1: Dynamic queries with many conditional branches

Suppose a product search screen offers optional filters:

- Product name keyword.
- One or more categories.
- Minimum and maximum price.
- In-stock status.
- List of brands.
- Updated timestamp range.
- Multi-criteria sorting.
- Selecting only specific fields in results.

Creating a derived method for every combination causes method counts to explode. A long method name also obscures which conditions are mandatory versus applied only when the user supplies a value.

Operations lets you construct clauses per input and combine whichever filters are present:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> {
            b.filter(f -> f.term(t -> t
                .field("available")
                .value(true)
            ));

            if (category != null && !category.isBlank()) {
                b.filter(f -> f.term(t -> t
                    .field("category")
                    .value(category)
                ));
            }

            if (keyword != null && !keyword.isBlank()) {
                b.must(m -> m.match(mm -> mm
                    .field("name")
                    .query(keyword)
                ));
            }

            return b;
        })
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

This illustrates assembling clauses conditionally; exact imports and builder overloads depend on your Java API Client and Spring Data Elasticsearch version. The key benefit is building the query from actual runtime inputs rather than maintaining a separate repository method per filter combination.

When criteria become complex, extract query construction into a dedicated component so the service does not get cluttered with Query DSL details.

### Limit 2: Specialized Query DSL

Repository derived queries handle common matching patterns. When you need Query DSL such as:

- **bool** with multiple **must**, **filter**, **should**, and **must_not** branches.
- **nested** queries.
- **function_score** or queries shaping relevance.
- **geo_distance**, **geo_shape**, and geospatial queries.
- **script** queries or script scores.
- **match_phrase**, **multi_match** with detailed options.
- **terms_set**, **wildcard**, **regexp**, or specialized query types.
- Queries combining multiple levels and fields.

Operations with **NativeQuery** expresses these directly. You can construct the query via the Elasticsearch Java API Client and pass it to Operations so Spring Data still handles entity mapping and result conversion.

Seeing Query DSL does not automatically mean abandoning repositories. A short, fixed, readable query still fits **@Query**. Switch when the query needs composition, many parameters or options, or when repository methods become hard to maintain.

### Limit 3: Aggregations and non-entity responses

Repository methods usually aim to return entities, lists, or pages. Yet many use cases need aggregated summaries:

- Counting products by category.
- Calculating average price by brand.
- Generating price-range histograms.
- Grouping by day or month.
- Computing field cardinality.
- Nesting multiple aggregation levels.
- Returning buckets and metrics instead of documents.

Aggregations live in a separate section of the Search API response. When the application needs buckets, metrics, or pipeline aggregations, Operations fits better because it preserves and exposes the full response structure.

Example aggregation request:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
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

This request does not return a list of Product documents. It returns `category` buckets with `average_price` metrics. Trying to force this output into an entity type strips away the meaning of an aggregation response.

### Limit 4: Needing per-hit SearchHit metadata

Some use cases need more than entity contents—they also need:

- Document ID.
- Score.
- Sort values.
- Highlight fragments.
- Inner hits.
- Search-wide metadata such as total hits and hit relation.

If a repository returns **List<Product>**, the application receives only entities. That return type is unsuitable when the service needs per-hit metadata.

Operations can return **SearchHits<T>**:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    List<Object> sortValues = hit.getSortValues();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();
}
~~~

Exact types and methods on SearchHit can vary by version. Choose SearchHits whenever Elasticsearch metadata is genuinely part of the business output.

### Limit 5: Choosing the index or alias at call time

Repositories usually take their default index from **@Document(indexName = "...")**. This is convenient when an entity always targets one fixed index or alias.

However, an application may need to:

- Read from **products-read**.
- Write to **products-write**.
- Search tenant-specific indices.
- Run queries against a historical index.
- Compare results between two indices during a migration.

A repository bound to a single default index cannot distinguish all of those targets on its own. Operations lets you pass **IndexCoordinates** per operation:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products-read")
);

Product saved = operations.save(
    product,
    IndexCoordinates.of("products-write")
);
~~~

This helps when separating read aliases and write aliases. Make sure index/alias names come from trusted configuration, especially with tenant routing. Never concatenate arbitrary user input directly into index names.

### Limit 6: Source filtering or response shaping

Some screens only need a few document fields. The Search API can restrict `_source` to reduce network payload size:

~~~http
POST /products/_search
{
  "_source": ["name", "category", "price"],
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Operations lets you configure source filters and request options according to the version. Repositories may support some projections or annotations depending on release, yet when you need exact `_source` includes/excludes or combinations with specialized queries, Operations is usually clearer.

Distinguish source filtering from DTO projections. Source filtering controls what data Elasticsearch sends back; projections control which Java type the application maps results into. They can be combined, but they are not the same thing.

### Limit 7: Highlighting, collapsing, or specialized search options

The Search API includes many features beyond queries and sorting:

- Highlighting to return text snippets containing matched terms.
- Collapsing to group results by a field.
- **search_after** for deep pagination.
- **track_total_hits** to control total-hit counting.
- Routing or preference for directing searches.
- Runtime mappings.
- Rescoring and other advanced options.

When these features are part of the use case, Operations with a query builder usually expresses them better than a repository method.

## 4. What Is ElasticsearchOperations?

**ElasticsearchOperations** is Spring Data Elasticsearch's high-level abstraction for document and search operations. It lets the application construct queries, pick entity types and index coordinates, and execute operations.

Common operation groups:

| Group | Examples |
|---|---|
| Search | `search`, `searchSimilar` depending on version |
| Document reads | `get`, `multiGet` |
| Document writes | `save`, `bulkIndex` or equivalent bulk operations |
| Delete | `delete` |
| Index creation and management | Via `IndexOperations` |
| Mapping/conversion | Driven by `ElasticsearchConverter` and metadata |
| Index/alias selection | `IndexCoordinates` |

The standard implementation in modern versions is **ElasticsearchTemplate**. Services should depend on the **ElasticsearchOperations** interface to preserve abstraction and simplify testing.

Example injecting Operations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Using Operations does not mean manually serializing JSON or making raw HTTP calls. Spring Data still handles entity and result conversion through its converter while using the configured client.

## 5. Building Queries with Operations

### Using CriteriaQuery for simple dynamic conditions

Spring Data's Criteria API offers a way to assemble conditions without writing JSON directly:

~~~java
Criteria criteria = new Criteria("category").is("accessories")
    .and("price").between(20.0, 100.0);

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

CriteriaQuery is useful when building simple structured criteria dynamically from inputs. It remains a Spring Data abstraction and does not necessarily expose every feature of Elasticsearch Query DSL.

If a query needs specialized capabilities lacking a Criteria API representation, use **NativeQuery**.

### Using NativeQuery for Query DSL

NativeQuery in versions backed by the Elasticsearch Java API Client lets you build queries using typed client builders:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("mechanical keyboard")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value("accessories")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

The query has two parts:

- **must** performs full-text matching on `name`.
- **filter** restricts `category` without calculating relevance scores for the filter clause.

PageRequest supplies pagination parameters. `operations.search` executes against the default index from entity metadata unless `IndexCoordinates` is passed explicitly.

Exact imports and NativeQuery builder APIs vary across Spring Data Elasticsearch and Elasticsearch Java API Client versions. Match your implementation to your project's dependencies.

### Adding sorting

You can attach sorting to the query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("keyboard")
        )
    )
    .withSort(s -> s
        .field(f -> f
            .field("price")
            .order(SortOrder.Asc)
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

This example searches by name and sorts by ascending price. When sorting on a `text` property, use an appropriate keyword subfield such as **name.keyword**; the field mapping must support sorting.

### Reading SearchHits and metadata

The result of `operations.search` is usually **SearchHits<T>**:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

long totalHits = hits.getTotalHits();

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    System.out.println("id: " + hit.getId());
    System.out.println("score: " + hit.getScore());
    System.out.println("product: " + product.getName());
}
~~~

SearchHits<T> holds the list of hits and aggregate metadata. Each SearchHit<T> holds the entity alongside hit-specific details. This distinction matters whenever a service needs to explain or render search results.

If only entities are needed, the service can unwrap hits into a content list. Do not discard metadata prematurely if upstream APIs need scores, highlights, or sort values.

## 6. Aggregations Are a Clear Signal to Use Operations

Analytics reports typically return buckets and metrics rather than entities. Use Operations to execute aggregation queries and read aggregation responses.

Example request:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation(
        "by_category",
        Aggregation.of(a -> a
            .terms(t -> t.field("category"))
            .aggregations(
                "average_price",
                Aggregation.of(avg -> avg
                    .avg(v -> v.field("price"))
                )
            )
        )
    )
    .withMaxResults(0)
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

This illustrates attaching an aggregation to NativeQuery. Exact builder syntax and how aggregations are extracted from the response depend on the API version. When only aggregations are needed, setting max results to 0 keeps the response focused on statistics.

With modern Spring Data APIs, aggregations are accessed via search metadata or the corresponding response object. Do not expect SearchHits<T> to automatically turn buckets into entities. Extract aggregations using the result types provided by your active version.

### When should you create a DTO for aggregations?

When a service returns reports to a controller, map buckets and metrics into a dedicated DTO:

~~~java
public record CategorySummary(
    String category,
    long productCount,
    double averagePrice
) {}
~~~

DTOs describe business reporting results. The `Product` entity describes a stored document. Keeping the two types separate avoids confusing aggregated statistics with actual index documents.

## 7. Choosing Operations When Explicit Index/Alias Selection Is Needed

A common pattern is separating read and write aliases.

A repository with **@Document(indexName = "products")** normally uses the same default index/alias for all operations. When read and write aliases are separated, Operations lets you pick the exact target:

~~~java
public class ProductStore {

    private final ElasticsearchOperations operations;

    public ProductStore(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-read")
        );
    }

    public Product save(Product product) {
        return operations.save(
            product,
            IndexCoordinates.of("products-write")
        );
    }
}
~~~

This approach also fits querying historical indices or validating data during index migrations.

Obtain alias names from application configuration or a controlled routing map. Never pass arbitrary index names from public requests straight into IndexCoordinates.

## 8. Custom Repository Fragments: Keep Business APIs, Use Operations Underneath

Switching to Operations does not mean every service must know Query DSL. When a complex query is a core domain capability, encapsulate it in a custom repository fragment.

Example fragment interface:

~~~java
public interface ProductSearchRepository {
    SearchHits<Product> searchCatalog(ProductSearchCriteria criteria);
}
~~~

Main repository combining the fragment:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchRepository {
}
~~~

Fragment implementation using Operations:

~~~java
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Product> searchCatalog(
            ProductSearchCriteria criteria) {

        // Build CriteriaQuery or NativeQuery from criteria.
        // Execute using ElasticsearchOperations.
        Query query = buildQuery(criteria);

        return operations.search(query, Product.class);
    }

    private Query buildQuery(ProductSearchCriteria criteria) {
        // Query construction logic is encapsulated here.
        return new CriteriaQuery(
            new Criteria("category").is(criteria.category())
        );
    }
}
~~~

This illustrates the structure. Implementation naming conventions, constructors, and fragment configuration must match the rules of your project's Spring Data version.

Benefits:

- Services call a domain-focused API such as **searchCatalog**.
- Query DSL stays inside the adapter/repository fragment.
- The base repository continues providing CRUD operations.
- Criteria-to-query conversion logic can be unit tested in isolation.
- Changing query structure does not leak Elasticsearch details into the service.

Custom fragments work well when a complex query remains part of domain repository access. If an operation is a specialized search workflow used by only one service, a dedicated search component backed by Operations can be even cleaner.

## 9. Separating Responsibilities Across Service, Repository, and Operations

A maintainable structure separates responsibilities by layer:

~~~text
Controller
    |
    v
Application Service
    |
    +---- ProductRepository
    |         |
    |         v
    |    CRUD / derived query / simple @Query
    |
    +---- ProductSearchService or custom fragment
              |
              v
       ElasticsearchOperations
              |
              v
       Query builder / IndexCoordinates
              |
              v
       Elasticsearch Java API Client
~~~

Services orchestrate use cases and business rules. Repositories provide common data operations. Operations-backed components handle queries requiring fine-grained control.

Never let controllers construct Query DSL directly. Likewise, avoid cluttering business services with deeply nested builder callbacks when query logic can be encapsulated in a dedicated class.

### A service can use both Repository and Operations

Example:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;
    private final ElasticsearchOperations operations;

    public ProductService(
            ProductRepository repository,
            ElasticsearchOperations operations) {
        this.repository = repository;
        this.operations = operations;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Optional<Product> get(String id) {
        return repository.findById(id);
    }

    public SearchHits<Product> advancedSearch(Query query) {
        return operations.search(query, Product.class);
    }
}
~~~

This is a valid combination when a service genuinely needs both abstractions. In larger projects, extract `advancedSearch` into its own component so the service is not responsible for constructing or managing queries.

## 10. Comparing Repository and Operations

| Criterion | Repository | ElasticsearchOperations |
|---|---|---|
| Standard CRUD | Very well suited | Possible |
| Derived queries | Yes | Not primary purpose |
| Fixed JSON queries | `@Query` | Can use query objects |
| Multi-branch dynamic queries | Becomes cumbersome | Well suited |
| Specialized Query DSL | Limited by repository API | Better control |
| Aggregations | Depends on return type/API and version | Well suited |
| `SearchHit` metadata | Requires picking right return type | Returns `SearchHits<T>` directly |
| Per-call index/alias selection | Governed by entity/repository metadata | Explicit `IndexCoordinates` |
| Source filtering, highlights, search options | Depends on repository method support | Stronger request control |
| Mapping/index management | Not primary responsibility | Typically uses `IndexOperations` |
| CRUD conciseness | High | More verbose |
| Query builder reusability | Limited with method/annotation syntax | Easily encapsulated in components |

Operations provides greater control, at the cost of more verbose code. Do not rewrite every operation with Operations simply because it is more general.

## 11. Decision Process: Stay on Repository or Switch to Operations?

Ask these questions when designing a new use case.

### Step 1: Identify the result type

If the output is a single entity, a list of entities, or a plain page, repositories usually work well.

If the output involves aggregation buckets, metrics, highlights, scores, sort values, or specialized metadata, evaluate Operations.

### Step 2: Assess query complexity

If the query is clearly expressed by a short derived method, stay with the repository.

If the query is fixed with moderate DSL, consider **@Query**.

If the query is assembled from optional inputs, uses many bool branches, or needs specialized Query DSL features, switch to Operations.

### Step 3: Check index selection requirements

If the entity always uses one default index/alias, repositories are convenient.

If each call must pick a read alias, write alias, historical index, or tenant index, Operations with **IndexCoordinates** is clearer.

### Step 4: Check response requirements

If the caller only needs entities, repositories suffice.

If the caller needs SearchHit metadata or aggregation responses, choose the right return type or Operations.

### Step 5: Check maintainability

If repository methods start getting very long names, multiple overloads, or unreadable query annotations, pause and move query construction into a dedicated component.

If a query builder is used in one place with its own business logic, create a search component. If it represents shared data access on the domain repository, a custom fragment fits well.

## 12. Concrete Signs It Is Time to Switch to Operations

The following signs usually indicate the repository abstraction no longer expresses the use case cleanly:

1. **Overly long derived method names:** method names must encode many optional filters or nested logic.
2. **Unreadable annotation queries:** long JSON with many parameters, branches, and variants.
3. **Runtime-dependent query structure:** each request toggles different filters on or off.
4. **Aggregations required:** output is statistics or buckets rather than entities.
5. **Hit metadata required:** the service needs scores, highlights, sort values, or inner hits.
6. **Multiple indices/aliases required:** target index depends on use case or tenant.
7. **Specialized search options required:** collapsing, rescoring, **search_after**, runtime mappings, or advanced options.
8. **Exact source filtering required:** responses must contain only a specific field subset.
9. **Combining multiple query types:** bool, nested, geo, script, or function score queries.
10. **Dedicated adapter needed:** complex queries should be encapsulated and tested independently.

Even one critical requirement from this list can justify Operations. Do not wait until the repository becomes unmaintainable.

## 13. Common Mistakes When Moving from Repository to Operations

### Moving all CRUD to Operations

Operations can run save, get, delete, and search. However, where repositories already handle CRUD cleanly, migrating everything adds boilerplate and loses repository conciseness.

Keep repositories for simple operations. Use Operations where extra control is required.

### Putting Query DSL into Services

A service may need to invoke search, yet it does not need to contain raw builder code. For complex queries, extract `ProductQueryFactory`, `ProductSearchRepositoryImpl`, or `ProductSearchService` so business code stays readable.

### Using Operations while ignoring mapping metadata

When calling **operations.search(query, Product.class)**, Spring Data still relies on the entity class and mapping metadata. Passing the wrong class or field names can prevent proper result conversion.

Do not treat Operations as a raw client. It remains a Spring Data abstraction with converters, mapping metadata, and its own conventions.

### Using NativeQuery for every query

NativeQuery is more powerful, yet more verbose than derived queries or CriteriaQuery. Choose the simplest API that fulfills the requirement; reserve NativeQuery for complex Query DSL.

### Discarding needed metadata

If you switch to Operations and immediately unwrap SearchHits into `List<T>`, the service may lose scores, highlights, or sort values needed by callers. Determine the required result contract before stripping metadata.

### Failing to verify API versions

Classes like NativeQuery, builder methods, and aggregation result APIs change across release trains. Verify code examples against your running Spring Data Elasticsearch version rather than copying imports or builders from another version's docs.

## 14. Testing Repositories and Operations

Repositories and Operations have different testing focuses.

### Testing repositories

Verify behaviors that carry business meaning:

- Derived queries return the right documents for conditions.
- `@Query` produces expected results with bound parameters.
- Pagination and sorting work properly.
- CRUD targets the right index/alias.
- Return types match the use case.

### Testing query builders

If query construction is extracted, it can be tested independently:

- Inputs with no filters.
- Category filter only.
- Keyword combined with price range.
- Multiple combined conditions.
- Default sorting and optional sorting.
- Edge cases like empty lists, null values, or invalid price ranges.

You do not need a live Elasticsearch connection for every query-building decision if unit tests can inspect query objects or request structures. Still, integration tests against a compatible Elasticsearch instance are necessary to validate actual Query DSL and mapping semantics.

### Integration testing Operations

Some issues surface only when running against real Elasticsearch:

- Mapping lacks the queried field.
- `keyword` subfield does not exist.
- Query DSL is incompatible with the server version.
- Aggregations or sorts fail on the field type.
- `IndexCoordinates` points to the wrong alias.
- Response contains hits yet the converter cannot instantiate entities.

Integration tests should run an Elasticsearch version matching your deployment target. When using Testcontainers or a test cluster, pin the image version and configure mappings explicitly.

## 15. Complete Use-Case Design Example

Suppose a catalog has two types of operations:

- Product CRUD.
- Advanced search by keyword, category, and price range with sorting and pagination.

The repository handles CRUD and simple queries:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

A criteria object models search inputs:

~~~java
public record ProductSearchCriteria(
    String keyword,
    String category,
    Double minPrice,
    Double maxPrice,
    int page,
    int size
) {}
~~~

A search component uses Operations:

~~~java
@Service
public class ProductCatalogSearch {

    private final ElasticsearchOperations operations;

    public ProductCatalogSearch(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                if (criteria.category() != null
                        && !criteria.category().isBlank()) {
                    b.filter(f -> f.term(t -> t
                        .field("category")
                        .value(criteria.category())
                    ));
                }

                if (criteria.keyword() != null
                        && !criteria.keyword().isBlank()) {
                    b.must(m -> m.match(mm -> mm
                        .field("name")
                        .query(criteria.keyword())
                    ));
                }

                if (criteria.minPrice() != null) {
                    b.filter(f -> f.range(r -> r
                        .number(n -> n
                            .field("price")
                            .gte(criteria.minPrice())
                        )
                    ));
                }

                if (criteria.maxPrice() != null) {
                    b.filter(f -> f.range(r -> r
                        .number(n -> n
                            .field("price")
                            .lte(criteria.maxPrice())
                        )
                    ));
                }

                return b;
            }))
            .withPageable(PageRequest.of(
                criteria.page(),
                criteria.size()
            ))
            .build();

        return operations.search(query, Product.class);
    }
}
~~~

This example demonstrates building queries from present conditions. Range builder syntax and numeric value types can vary across Java API Client versions; adjust to your actual dependencies. In real applications, validate page, size, and price bounds before building queries.

The application service coordinates both abstractions:

~~~java
@Service
public class ProductApplicationService {

    private final ProductRepository repository;
    private final ProductCatalogSearch search;

    public ProductApplicationService(
            ProductRepository repository,
            ProductCatalogSearch search) {
        this.repository = repository;
        this.search = search;
    }

    public Product create(Product product) {
        return repository.save(product);
    }

    public Optional<Product> findById(String id) {
        return repository.findById(id);
    }

    public SearchHits<Product> search(ProductSearchCriteria criteria) {
        return search.search(criteria);
    }
}
~~~

As a result, the service still uses the repository for routine operations, while advanced queries are delegated to a specialized component using Operations.

## 16. Abstraction Selection Checklist

Before writing a new repository method, ask yourself:

- [ ] Is this standard CRUD or a simple query?
- [ ] Will the derived method name remain short and clear?
- [ ] If using `@Query`, is the JSON fixed and maintainable?
- [ ] Does the result only require entities or pages?
- [ ] Are aggregations or `SearchHit` metadata needed?
- [ ] Does the query have many optional criteria or specialized Query DSL?
- [ ] Does the index/alias need to be chosen dynamically per call?
- [ ] Are source filtering, highlighting, collapsing, or `search_after` required?
- [ ] Should query logic live in a custom fragment or search component?
- [ ] Is the builder API compatible with the project's Spring Data / Java client version?

If most requirements fall under CRUD, derived queries, and basic pagination, a repository is usually sufficient. When a use case demands fine-grained control over queries, responses, or target indices, Operations is the better abstraction.

Repositories and Operations are not mutually exclusive. Repositories keep everyday data access concise; Operations unlocks granular control whenever Elasticsearch search is central to a use case. Combining both layers in the right places keeps code readable while leveraging Elasticsearch's capabilities.
