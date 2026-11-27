# Testing Derived Queries, CriteriaQuery, @Query, and NativeQuery

Spring Data Elasticsearch supports multiple ways to express queries: deriving queries from repository method names, building conditions with `CriteriaQuery`, declaring JSON DSL via the `@Query` annotation, or using `NativeQuery` to build queries with the Elasticsearch Java API Client.

These approaches differ in abstraction level and expressiveness, yet all of them must ultimately produce requests Elasticsearch understands. Therefore, testing needs to answer two separate questions:

- **Is the query constructed properly in code?** This can be partially checked with unit tests covering query-building logic, parameters, and conditional branches.
- **Does Elasticsearch execute the query against real mappings and data with the right semantics?** This requires repository integration tests running against real Elasticsearch.

Mocking a repository cannot verify derived queries, `@Query`, mappings, or DSL. Likewise, checking only that a method throws no exception is insufficient: a syntactically valid query filtering on the wrong field can return an empty list and still pass if assertions do not verify content.

## 1. Four Query Approaches and Testing Scope

| Query approach | Where declared | Strengths | What to test on Elasticsearch |
|---|---|---|---|
| Derived query | Repository method name like `findByStatusAndPriceLessThan` | Concise, readable, suits common conditions. | Property names, operators, mappings, and actual results. |
| `CriteriaQuery` | Java code using `Criteria` | Builds dynamic conditions across business branches. | Fields, operators, AND/OR combinations, ranges, and actual results. |
| `@Query` | JSON query DSL in repository annotation | Declares static queries with visible DSL. | JSON DSL, placeholders, data types, and actual results. |
| `NativeQuery` | Java API Client query DSL | Expresses complex queries, aggregations, nested, join, and engine-specific features. | Serialized DSL, mappings, and engine semantics. |

These styles can coexist in a single repository. Choose the simplest style that expresses the requirement clearly, then test it at the layer owning that responsibility.

## 2. Shared Data and Mapping Setup for Examples

Suppose the application manages products with the fields:

- `id`: document ID.
- `sku`: unique product code, used for exact lookup.
- `name`: product name, used for full-text search.
- `status`: status, used for exact filtering.
- `price`: price, used for range queries and sorting.

Entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-query-it")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private double price;

    public Product() {
    }

    public Product(String id, String sku, String name, String status, double price) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.status = status;
        this.price = price;
    }

    // Getters and setters.
}
```

Mapping is part of the query contract. `term` fits `keyword`, while full-text `match` is typically used on `text`. If `status` were changed to `text`, exact value matching could have different semantics due to the analyzer.

Repository:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByStatusAndPriceLessThan(String status, double maxPrice);

    Optional<Product> findBySku(String sku);

    @Query("{\"term\": {\"status\": \"?0\"}}")
    List<Product> findByStatusUsingJsonQuery(String status);
}
```

The repository defines one derived query, one query returning at most one result, and one method using JSON DSL via `@Query`.

## 3. Setting Up Elasticsearch Integration Tests

To verify queries reliably, you need an Elasticsearch instance compatible with your project's Spring Data Elasticsearch and Java API Client versions. Testcontainers is a popular choice because each test suite can start an explicitly pinned Elasticsearch version.

Illustrative Gradle dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:elasticsearch'
}
```

Manage the Testcontainers version via the project's BOM/dependency management. Pin the Elasticsearch image to a compatible version; avoid `latest` in CI.

Example base test class:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

@Testcontainers
@SpringBootTest
abstract class AbstractProductQueryIT {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    DockerImageName.parse(
                            "docker.elastic.co/elasticsearch/elasticsearch:8.15.0"
                    )
            ).withEnv("xpack.security.enabled", "false");

    @DynamicPropertySource
    static void configureElasticsearch(DynamicPropertyRegistry registry) {
        registry.add("spring.elasticsearch.uris", elasticsearch::getHttpHostAddress);
    }

    @Autowired
    protected ProductRepository repository;

    @Autowired
    protected ElasticsearchOperations operations;

    @BeforeEach
    void resetIndex() {
        IndexOperations index = operations.indexOps(Product.class);
        index.delete();
        index.createWithMapping();
    }

    protected void insertProducts() {
        repository.saveAll(List.of(
                new Product("P-100", "SKU-100", "Mechanical Keyboard", "ACTIVE", 250.0),
                new Product("P-101", "SKU-101", "Wireless Mouse", "ACTIVE", 45.0),
                new Product("P-102", "SKU-102", "Keyboard Wrist Rest", "INACTIVE", 30.0),
                new Product("P-103", "SKU-103", "USB-C Hub", "ACTIVE", 80.0)
        ));
        indexRefresh();
    }

    protected void indexRefresh() {
        operations.indexOps(Product.class).refresh();
    }
}
```

This is an illustrative configuration. Connection properties, security settings, and container startup must match your project's Spring Boot/Testcontainers/Elasticsearch versions. If your test environment requires security enabled, configure credentials and TLS accordingly instead of disabling security.

`resetIndex()` creates a fresh mapping for each test. `insertProducts()` seeds sample data and refreshes so Search API queries see the documents. Do not use `Thread.sleep` to wait for refresh.

## 4. Testing Derived Queries

Derived queries are generated from method names. For example:

```java
List<Product> findByStatusAndPriceLessThan(String status, double maxPrice);
```

Spring Data parses the method name into an equivalent condition:

```text
status = :status AND price < :maxPrice
```

Integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class ProductDerivedQueryIT extends AbstractProductQueryIT {

    @Test
    void derivesEqualityAndLessThanConditions() {
        insertProducts();

        List<Product> results =
                repository.findByStatusAndPriceLessThan("ACTIVE", 100.0);

        assertThat(results)
                .extracting(Product::getId)
                .containsExactlyInAnyOrder("P-101", "P-103");
    }
}
```

This test verifies several things at once:

- Spring Data recognizes the property names `status` and `price`.
- The `And` operator combines both conditions.
- `LessThan` translates into a strictly less-than range condition.
- Both fields' mappings are compatible with the query.
- Actual search results contain the expected documents.

### 4.1. Testing Single-Result Methods

```java
@Test
void derivesQueryForUniqueSku() {
    insertProducts();

    Optional<Product> found = repository.findBySku("SKU-100");

    assertThat(found)
            .isPresent()
            .get()
            .extracting(Product::getId)
            .isEqualTo("P-100");
}
```

`sku` is mapped as `keyword`, suitable for exact lookup. If data can contain duplicate SKUs, returning `Optional<Product>` no longer reflects the business cardinality; in that case enforce uniqueness at the data source or return a collection and handle duplicates explicitly.

### 4.2. Testing Boundary Operators

For range queries, test values just below, equal to, and just above the threshold:

```java
@Test
void lessThanDoesNotIncludeTheBoundary() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndPriceLessThan("ACTIVE", 80.0);

    assertThat(results)
            .extracting(Product::getId)
            .containsExactly("P-101");
}
```

`LessThan(80.0)` excludes products priced at exactly 80.0. If business logic requires including the boundary, use `LessThanEqual` and write a corresponding boundary test.

### 4.3. Derived Queries Must Verify Mapping and Field Names

The Java property name and the Elasticsearch field name can differ when using `@Field(name = "...")`. Derived queries generally reference entity properties; Spring Data mapping translates properties to the corresponding field names.

If the entity declares:

```java
@Field(name = "product_status", type = FieldType.Keyword)
private String status;
```

then tests must verify queries against the real `product_status` mapping rather than assuming the index field is named `status`.

## 5. Testing `@Query` with JSON DSL

`@Query` lets you declare a JSON query directly on a repository method:

```java
@Query("{\"term\": {\"status\": \"?0\"}}")
List<Product> findByStatusUsingJsonQuery(String status);
```

`?0` is the placeholder for the first parameter. For methods with multiple parameters, `?1`, `?2`, etc. reference parameters by position. Never concatenate user input directly into JSON DSL strings.

Integration test:

```java
class ProductAnnotatedQueryIT extends AbstractProductQueryIT {

    @Test
    void executesJsonQueryWithBoundParameter() {
        insertProducts();

        List<Product> results =
                repository.findByStatusUsingJsonQuery("ACTIVE");

        assertThat(results)
                .extracting(Product::getId)
                .containsExactlyInAnyOrder("P-100", "P-101", "P-103");
    }
}
```

This test verifies the JSON query is valid, the placeholder is bound to the passed argument, and the `term` query filters status correctly.

### 5.1. Using `match` for Text Fields

Example method searching product names via full-text search:

```java
@Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
List<Product> searchByName(String text);
```

Test:

```java
@Test
void executesMatchQueryForTextField() {
    insertProducts();

    List<Product> results = repository.searchByName("keyboard");

    assertThat(results)
            .extracting(Product::getId)
            .contains("P-100", "P-102");
}
```

`match` uses the `name` field's analyzer. Results depend on the analyzer and indexed data; tests should use keywords with stable semantics under the configured analyzer.

### 5.2. Testing Multiple Placeholders

A static query can accept multiple parameters:

```java
@Query("""
        {
          "bool": {
            "filter": [
              { "term": { "status": "?0" } },
              { "range": { "price": { "lt": ?1 } } }
            ]
          }
        }
        """)
List<Product> findByStatusAndMaximumPrice(String status, double maxPrice);
```

Text blocks require a Java version supporting text blocks. If the project targets an older Java version, use escaped string literals.

Test:

```java
@Test
void bindsMultipleQueryParameters() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndMaximumPrice("ACTIVE", 100.0);

    assertThat(results)
            .extracting(Product::getId)
            .containsExactlyInAnyOrder("P-101", "P-103");
}
```

Verify that placeholders are substituted in the right positions and data types are represented properly in JSON. For numeric ranges, do not wrap the placeholder in quotes if the DSL expects a JSON number.

### 5.3. Key Checks When Testing `@Query`

- JSON must be valid and compatible with your Elasticsearch version.
- Field names must match the mapping, including names customized via `@Field(name = ...)`.
- `term` suits exact values/keywords; `match` suits full-text fields.
- Placeholders must sit inside the right JSON type: quoted for strings, unquoted for numbers/booleans.
- Never interpolate raw user input into the query string.
- Test with both matching data and non-matching data to catch overly broad queries.
- If the query includes sorting, paging, or filters, verify each behavior separately.

## 6. Testing `CriteriaQuery`

`CriteriaQuery` is useful when conditions depend on optional parameters or business logic. For example, a user may filter by status and maximum price.

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = new CriteriaQuery(
        new Criteria("status").is("ACTIVE")
                .and("price").lessThan(100.0)
);
```

Execute via `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<Product> hits = operations.search(query, Product.class);

List<Product> products = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

### 6.1. Integration Test for CriteriaQuery

```java
class ProductCriteriaQueryIT extends AbstractProductQueryIT {

    @Test
    void combinesStatusAndPriceCriteria() {
        insertProducts();

        Query query = new CriteriaQuery(
                new Criteria("status").is("ACTIVE")
                        .and("price").lessThan(100.0)
        );

        SearchHits<Product> hits = operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
                .extracting(hit -> hit.getContent().getId())
                .containsExactlyInAnyOrder("P-101", "P-103");
    }
}
```

The test runs `CriteriaQuery` through Spring Data's converter and the real Elasticsearch engine. It catches bugs in field names, operators, mappings, or condition chaining.

### 6.2. Testing Optional Conditions

A service may add conditions only when the caller supplies parameters:

```java
public Query buildProductSearch(String status, Double maxPrice) {
    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria = criteria.and("status").is(status);
    }

    if (maxPrice != null) {
        criteria = criteria.and("price").lessThanEqual(maxPrice);
    }

    return new CriteriaQuery(criteria);
}
```

With builders like this, you can write unit tests to verify query construction branches and integration tests for representative combinations.

Cases to cover:

- No filters provided.
- Only status provided.
- Only max price provided.
- Both status and max price provided.
- Price exactly equal to threshold when using `lessThanEqual`.
- Status with zero matches.

There is no need to run every trivial logic combination through Elasticsearch if the query builder is unit-tested separately, provided integration tests verify execution against the real mapping.

### 6.3. Combining OR and AND

The Criteria API supports grouping conditions. For example, finding active products in either of two price ranges or matching a name. Pay attention to precedence and grouping because shifting `and`/`or` positions can alter semantics.

Conceptual example:

```java
Criteria status = new Criteria("status").is("ACTIVE");
Criteria priceRange = new Criteria("price").lessThan(50.0)
        .or("price").greaterThan(200.0);

Criteria combined = status.and(priceRange);
Query query = new CriteriaQuery(combined);
```

Write integration tests containing documents matching each OR branch, documents matching neither branch, and documents with a different status to verify actual grouping. Do not check only the result count, since two different wrong result sets can happen to have the same count.

## 7. Testing `NativeQuery`

`NativeQuery` fits when you need the Elasticsearch Java API Client's DSL directly. It supports specific query types such as `bool`, `nested`, `has_child`, `geo_distance`, `function_score`, along with sorting, aggregations, and advanced options.

Example query finding products whose name matches `keyboard` and status is `ACTIVE`:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query nativeDsl = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nativeDsl)
        .build();
```

Execution:

```java
SearchHits<Product> hits = operations.search(nativeQuery, Product.class);
```

### 7.1. Integration Test for NativeQuery

```java
class ProductNativeQueryIT extends AbstractProductQueryIT {

    @Test
    void executesBoolQueryWithMustAndFilter() {
        insertProducts();

        Query nativeDsl = Query.of(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(mm -> mm
                                        .field("name")
                                        .query("keyboard")
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value(FieldValue.of("ACTIVE"))
                                )
                        )
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(nativeDsl)
                .build();

        SearchHits<Product> hits = operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
                .extracting(hit -> hit.getContent().getId())
                .containsExactly("P-100");
    }
}
```

This query requires both conditions: `name` matching `keyboard` and exact `status` `ACTIVE`. `P-102` matches by name but is inactive, so the filter must exclude it.

### 7.2. Why Use `NativeQuery` Instead of `@Query`?

Choose `NativeQuery` when:

- The query has multiple `bool`/`nested` clauses or complex DSL structure.
- You need newer features of the Elasticsearch Java API Client.
- The query is constructed dynamically from many conditions.
- You need sorting, aggregations, highlighting, suggestions, or advanced options.
- You want the type-safe builders of the Java API Client instead of assembling JSON strings.

`@Query` works well for small, static queries that are easy to read right on the repository method. Do not rewrite every query into `NativeQuery` when method derivation or `@Query` is already clear.

## 8. Testing Aggregations in NativeQuery

When a `NativeQuery` includes aggregations, tests must verify the bucket/metric results rather than merely confirming search threw no errors.

Example creating a terms aggregation by status:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation byStatus = Aggregation.of(a -> a
        .terms(t -> t.field("status"))
);

NativeQuery query = NativeQuery.builder()
        .withQuery(Query.of(q -> q.matchAll(m -> m)))
        .withAggregation("products_by_status", byStatus)
        .build();
```

After calling search, read the aggregation from `SearchHits`/the aggregation container according to the Spring Data version in use. Aggregation wrapper types and bucket accessors have changed across API generations; use the exact types provided by your project's dependencies.

An aggregation integration test should verify:

- Bucket keys, e.g., `ACTIVE` and `INACTIVE`.
- Bucket document counts.
- Metric values if using `avg`, `sum`, `min`, `max`.
- Results when zero documents exist.
- Whether the query/filter scope applies to the aggregation properly.

Do not hardcode the entire JSON response as a single string for comparison. Extract meaningful values and assert keys/counts/values so tests are less fragile to formatting changes.

## 9. Testing Sorting and Pagination

A query with the right filter but broken sorting or paging can still make the API return incorrect results.

Repository methods can accept `Pageable` or `Sort` when the method signature supports it:

```java
Page<Product> findByStatus(String status, Pageable pageable);
```

Integration tests should verify:

- The first page and next page do not duplicate documents.
- Total element count matches the query.
- Ascending/descending sorting uses the intended field.
- A stable tie-breaker exists when multiple documents share the same sort value.
- The field mapping supports sorting, such as `keyword` or numeric fields.

Sorting example:

```java
Pageable pageable = PageRequest.of(
        0,
        2,
        Sort.by(Sort.Direction.DESC, "price")
);

Page<Product> page = repository.findByStatus("ACTIVE", pageable);
```

Tests should assert the ID/price ordering against deterministic data. If using a `text` full-text field like `name`, sorting may need a `keyword` subfield rather than sorting directly on the text field.

## 10. Testing Query Builders Separately from Query Execution

When a query is complex, you can extract query construction into a pure component:

```java
public class ProductQueryFactory {

    public Query build(String status, String keyword) {
        // Return the Elasticsearch Java API Client Query.
    }
}
```

Unit tests for the factory can check input branches—for instance, null status omits the filter, blank keyword omits the match clause. However, unit-testing the factory alone does not prove Elasticsearch executes the DSL properly.

A balanced strategy:

1. Unit test the query factory for logic branches and parameters.
2. Write integration tests for representative queries and boundary cases.
3. Add dedicated integration tests for engine-specific features like nested, geo, join, aggregations, or scripts.

There is no need to test every single builder line twice if an integration test already covers important behavior thoroughly. Choose tests based on query risk and complexity.

## 11. Testing Empty Results and Non-Matching Conditions

A query that throws no error yet returns empty could be correct or a sign of a broken query. Include control data.

Example:

```java
@Test
void returnsEmptyWhenNoProductMatchesStatus() {
    insertProducts();

    List<Product> results =
            repository.findByStatusAndPriceLessThan("DELETED", 100.0);

    assertThat(results).isEmpty();
}
```

For complex queries, seed documents that:

- Match all conditions.
- Match only the first condition.
- Match only the second condition.
- Match no conditions.
- Have null/missing fields if the query must handle those cases.

This detects missing filters, inverted AND/OR logic, or ignored null conditions.

## 12. Testing Null Data and Missing Fields

In Elasticsearch, fields without values and fields with `null` generally do not create indexed terms like regular values. `exists`, `must_not exists`, and range queries have specific semantics.

If a query must find documents missing a field:

```java
Query missingBrand = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("brand"))
                )
        )
);
```

Tests should include a document omitting `brand`, a document having `brand`, and a document with `brand: null` if the source converter can produce that case. Verify actual results according to the mapping and any `null_value` setting.

Do not assume Java `null`, JSON `null`, and missing fields are always treated identically in every query.

## 13. Refresh Is Part of Query Integration Tests

The Search API is near-real-time. After `repository.save(...)`, `@Query`, derived queries, `CriteriaQuery`, and `NativeQuery` may not see new documents until the index refreshes.

Unstable:

```java
repository.save(product);
assertThat(repository.findBySku(product.getSku())).isPresent();
```

More reliable:

```java
repository.save(product);
operations.indexOps(Product.class).refresh();

assertThat(repository.findBySku(product.getSku())).isPresent();
```

Do not use `Thread.sleep` to wait for refresh. If the test verifies the Get API by ID, `findById` has real-time semantics by default and needs no refresh simply to read the new document.

For bulk setup, save all data first and refresh once afterward rather than refreshing after each document.

## 14. Testing Repositories with Custom Index Names and Aliases

Tests should use a dedicated index like `products-query-it`, never pointing to production or a local index used for development.

If the application uses aliases, you can create a versioned index in the test and attach the corresponding alias. This verifies:

- The repository uses the alias declared in `@Document`.
- The alias points to the right physical index.
- Queries execute through the alias.
- Write operations target the write index when an alias spans multiple indices.

For tests focused solely on query DSL, a dedicated index does not need to simulate full alias migrations. Only include alias behavior when it is part of the contract under test.

## 15. Checking Mapping Before Concluding a Query Is Wrong

A query can return wrong results due to the mapping rather than the query builder.

Examples:

- `term` on an analyzed `text` field may fail to match the original string.
- `match` on a `keyword` field lacks the tokenization semantics of `text`.
- Range queries on strings compare lexicographically rather than numerically.
- Sorting on a `text` field may be rejected or require a `keyword` subfield.
- Nested queries work only when the field is mapped as `nested`.
- Geo queries require proper `geo_point`/`geo_shape` mappings.

When an integration test fails, inspect the actual mapping:

```http
GET /products-query-it/_mapping
```

Do not tweak the query until the test passes if the mapping itself is the root cause. Query and mapping form a single contract; both must align with business requirements.

## 16. Testing Queries with Deterministic Data

Test data should be small yet clearly distinguish cases. For instance, the four products at the start of this lesson suffice to test status, full-text search, and price range.

Principles:

- Fixed IDs for readable assertions.
- Clear values on filtered fields.
- Boundary values for ranges and sorting.
- No random data when expected results depend on content.
- Each test creates its own data and does not depend on other tests.
- Use unique IDs/indices when running in parallel.
- Clean up indices/documents after tests or use a dedicated container.

There is no need to generate thousands of documents for basic query verification. Large datasets are only needed when testing pagination, performance, or distribution-dependent behavior.

## 17. Testing Query Errors and Mapping Rejections

Certain error conditions should be covered in integration tests:

- Non-existent fields or queries using invalid field paths.
- Invalid query DSL.
- Value types incompatible with the mapping.
- Nested paths on non-nested mappings.
- Invalid scripts or missing fields.
- Aggregations on fields that do not support aggregation.

Do not write tests asserting that every invalid query throws the exact same exception class across all versions. Exception wrapping can vary across Spring Data, Java API Client, and server releases. Verify standardized application-level error types or status/error types stable for your pinned version.

## 18. Unit Tests for Services Calling Repository Queries

A service may decide which repository method to invoke based on the request:

```java
public List<Product> search(ProductFilter filter) {
    if (filter.status() != null && filter.maxPrice() != null) {
        return repository.findByStatusAndPriceLessThan(
                filter.status(), filter.maxPrice());
    }

    if (filter.sku() != null) {
        return repository.findBySku(filter.sku()).stream().toList();
    }

    return repository.findAll().stream().toList();
}
```

Unit tests can mock the repository and verify the service picks the right method and arguments for each filter. They do not need to know what DSL the query method generates; that belongs in repository integration tests.

Separating tests this way pinpoints bugs at the right layer:

- Service calls the wrong method or passes wrong parameters: service unit test.
- Repository method generates the wrong query: repository integration test.
- Field mapping is incompatible with the query: repository integration test.

## 19. Reactive Queries Need the Same Strategy

With `ReactiveElasticsearchRepository`, derived queries return `Mono` or `Flux`. `ReactiveElasticsearchOperations` also supports `CriteriaQuery`/`NativeQuery` via corresponding reactive APIs.

Service unit tests can mock publishers:

```java
when(repository.findByStatus("ACTIVE"))
        .thenReturn(Flux.just(product1, product2));

StepVerifier.create(service.findActive())
        .expectNext(product1, product2)
        .verifyComplete();
```

Repository integration tests must subscribe to publishers and verify results against real Elasticsearch:

```java
StepVerifier.create(repository.findByStatus("ACTIVE"))
        .expectNextCount(2)
        .verifyComplete();
```

Before running search, refresh the index if the test just wrote data. Reactive execution does not alter the Search API's near-real-time semantics.

Do not call `.block()` in services/controllers to make tests easier. Use `StepVerifier` to check `onNext`, `onComplete`, and `onError`.

## 20. Isolating Tests and Avoiding Order Dependencies

Elasticsearch does not automatically roll back documents when a test ends. `@Transactional` does not automatically delete indexed data.

Isolation options:

1. Recreate the index before each test as in `resetIndex()`.
2. Use unique IDs per test run and clean up after the test.
3. Create dedicated indices per class/suite or per test when running in parallel.
4. Use a dedicated container for the test suite.

If multiple tests share one index and run in parallel, Test A deleting the index while Test B queries it causes hard-to-reproduce failures. When parallel execution is needed, use separate index namespaces or share the container while giving each test its own index.

## 21. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Service tests pass but production query fails | Repository was mocked so query never ran. | Add repository integration tests with real Elasticsearch. |
| Derived query returns empty | Wrong property name, mapping, or unrefreshed data. | Check entity properties/mapping and refresh before searching. |
| `term` fails to match text value | Exact query used on analyzed `text` field. | Use a `keyword` field/subfield or matching query. |
| `match` returns too many results | Analyzer tokenizes/normalizes differently than expected. | Inspect analyzer and test with representative inputs. |
| `@Query` parse error | Invalid JSON or misplaced/wrongly typed placeholder. | Check JSON DSL, quotes, and index mapping. |
| `@Query` filters with wrong arguments | Wrong `?0`, `?1` index or placeholder inside wrong JSON type. | Verify parameter positions and JSON types. |
| CriteriaQuery drops conditions | Incorrect AND/OR chaining or optional branch logic. | Test every branch and documents matching only one condition. |
| NativeQuery compiles but returns wrong results | Valid DSL with wrong field path/operator/mapping. | Run engine integration tests and inspect mapping. |
| Sorting on text field fails | Field lacks doc values/sortable mapping. | Use a `keyword` subfield or sortable mapping. |
| Flaky pass/fail tests | Search runs before refresh. | Refresh explicitly or use `WAIT_UNTIL`. |
| Tests depend on old data | Shared index without cleanup. | Reset index, use unique IDs, or dedicated indices. |
| Parallel test conflicts | Multiple tests delete/create the same index. | Isolate indices per test or serialize that test group. |
| Wrong aggregation counts | Wrong query scope, mapping, or aggregation field. | Verify field type and assert each bucket/metric. |
| Query tests skipped in CI | Integration tests not wired into build tasks/pipelines. | Configure test tasks/source sets and container runtime clearly. |

## 22. Test Matrix for the Four Query Styles

| Item | Unit test | Repository integration test |
|---|---|---|
| Derived method name and service choosing right method | Can verify service calls. | Verifies query derivation and actual results. |
| `@Query` placeholders | Can verify method/arguments at service boundary. | Verifies JSON query and parameter binding. |
| `CriteriaQuery` builder | Verifies condition construction branches. | Verifies AND/OR/operators on the engine. |
| `NativeQuery` factory | Verifies logic branches and parameters. | Verifies DSL, mapping, and semantics. |
| Mapping/analyzer | No. | Yes. |
| Refresh visibility | No. | Yes. |
| Sort/pagination | Service can verify passed parameters. | Verifies actual order/pages. |
| Aggregation/nested/geo/join | Does not verify engine. | Yes. |
| Business error from query outcome | Yes. | Selective in service integration tests. |

## 23. Workflow for Writing Tests for a New Query

1. **Define semantics:** does the query need exact match, full-text, range, nested, or aggregation?
2. **Verify mapping:** are field types, analyzers, subfields, nested paths, and doc values appropriate?
3. **Choose the representation:** derived method, `CriteriaQuery`, `@Query`, or `NativeQuery`.
4. **Extract dynamic logic:** if the query builder has many branches, isolate it as a unit-testable component.
5. **Prepare test Elasticsearch:** use Testcontainers with an appropriately pinned version.
6. **Create index and data:** use production-like mapping and datasets with matching and non-matching cases.
7. **Refresh:** refresh after setup before running Search API queries.
8. **Assert results:** check IDs/content, not merely counts or absence of exceptions.
9. **Test boundaries:** empty results, null/missing fields, range boundaries, AND/OR, sorting, and paging where relevant.
10. **Isolate data:** reset index or use dedicated namespaces; avoid sleep and order dependencies.
11. **Wire into CI:** verify integration tests actually execute against an Elasticsearch container.

## 24. Key Takeaways

- Derived queries derive from method names; test properties, operators, and results against real mappings.
- `CriteriaQuery` suits dynamic conditions; test every branch and AND/OR grouping.
- `@Query` embeds JSON DSL; test JSON syntax, `?0`/`?1` placeholders, data types, and field mappings.
- `NativeQuery` uses Java API Client DSL for complex queries and specialized Elasticsearch features.
- Mocking repositories only tests the service; it never verifies the executed query.
- Repository integration tests should use real Elasticsearch, usually via version-pinned Testcontainers.
- `term` generally pairs with `keyword`; `match` pairs with `text`; ranges/sorts need compatible field types.
- The Search API is near-real-time; refresh explicitly in tests after writing data.
- Never use `Thread.sleep` to wait for refresh.
- Assert document IDs/content and boundary conditions; asserting counts alone can miss broken queries.
- Inspect the actual mapping whenever queries return unexpected results.
- Test sorting, pagination, aggregations, nested, geo, join, and routing at the integration layer when used.
- Use isolated indices/test data and do not assume `@Transactional` rolls back Elasticsearch.
- Reactive queries still require `StepVerifier` and refreshes; reactive does not change Search API semantics.

Testing derived queries, `CriteriaQuery`, `@Query`, and `NativeQuery` combines understanding query-building code with observing Elasticsearch's real behavior. Unit tests are ideal for verifying condition selection logic and service orchestration; repository integration tests verify mappings, DSL, parameter binding, refreshes, and engine search results. When each test type focuses on its own responsibility, query bugs are caught early and diagnosed accurately.

## References

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — CriteriaQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — `@Query` annotation](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Query.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Testcontainers — Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html)
