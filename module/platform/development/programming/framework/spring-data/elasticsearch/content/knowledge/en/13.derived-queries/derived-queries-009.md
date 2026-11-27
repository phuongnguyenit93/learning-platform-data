# findBy, countBy, existsBy, and deleteBy Support Capabilities

Spring Data Elasticsearch lets you declare many queries directly in repository method names. Instead of building queries manually for simple conditions, you can name methods by convention such as findBySku, countByActiveTrue, or existsByEmail. Spring Data parses the method name, identifies properties and predicates, and generates an appropriate Elasticsearch query.

Common prefixes serve distinct purposes:

- **findBy** searches and returns documents matching the condition.
- **countBy** counts documents matching the condition.
- **existsBy** checks whether any document matches the condition.
- **deleteBy** deletes documents matching the condition.

Not all Spring Data query keywords are supported uniformly in Spring Data Elasticsearch. Derivation capabilities depend on version, field types, mappings, and the query backend. Therefore, use derived queries for simple conditions confirmed to be supported in your project's version; for complex queries or unclear semantics, use @Query or ElasticsearchOperations.

## 1. Method name structure

A derived query typically follows the form:

~~~text
<operation><By><property><predicate><And/Or><property>...
~~~

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByActiveTrue();

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

Spring Data parses the operation prefix to determine the action type and the segment after By to determine properties and conditions.

For findBySku:

- findBy indicates a read query.
- Sku resolves to the domain type's sku property.
- Parameter String sku supplies the lookup value.
- Return type List<Product> requests matching documents.

For countByCategory:

- countBy indicates counting.
- Category is the category property.
- Result is the count of matching documents, typically long.

For existsBySku:

- existsBy indicates only a boolean answer is needed.
- There is no need to load full document payloads into the service when the goal is merely checking whether a match exists.

For deleteBySku:

- deleteBy indicates deleting documents matching the condition.
- This is a write/delete operation and must be scoped with clear conditions.

Property names must match the domain model. If the entity defines skuCode, findBySku(...) will not automatically know it means skuCode. Spring Data typically throws an error when a property cannot be resolved.

## 2. Entity and repository used in examples

Suppose an application manages products:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByCategory(String category);

    List<Product> findByActiveTrue();

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

Example usage:

~~~java
List<Product> products =
    productRepository.findByCategory("accessories");

long total =
    productRepository.countByCategory("accessories");

boolean exists =
    productRepository.existsBySku("SKU-1001");
~~~

These examples assume the corresponding properties and mappings already exist on the index. Method names are parsed against the Java domain model, while query semantics also depend on Elasticsearch mappings.

## 3. findBy: finding documents matching conditions

findBy is the most common method group. It generates read queries from properties in the method name.

Query by one property:

~~~java
List<Product> findBySku(String sku);
~~~

Query by multiple conditions joined with AND:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);
~~~

Query with OR condition:

~~~java
List<Product> findBySkuOrName(String sku, String name);
~~~

In multi-condition methods, parameter order follows property order in the method name. For example, findBySkuAndCategory(String sku, String category) takes sku first, then category.

Keep methods short and expressive of business intent. When a method has many conditions, multiple OR branches, and many modifiers, an explicit query is usually easier to read, control, and debug.

### 3.1. findBy with return types

Common return types include:

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByCategory(String category);

Page<Product> findByActiveTrue(Pageable pageable);
~~~

Meaning:

- Optional<Product>: appropriate when business logic expects at most one match. If data may yield multiple matches, do not use a single Optional.
- List<Product>: returns a list of results, suitable when result counts are reasonably bounded.
- Page<Product>: returns a page along with pagination info and total hits according to the query/page mechanism in use.

If SKU is guaranteed unique in the domain, you can use Optional<Product> findBySku(...). If uniqueness is not enforced, a query may match multiple documents; in that case use List or handle duplicates explicitly.

Supported return types and SearchHits/SearchPage variants can differ across Spring Data Elasticsearch versions. Check the docs/APIs of your project's dependency before choosing advanced return types.

### 3.2. Pagination with Pageable

You can pass Pageable to limit result counts and select a page:

~~~java
Page<Product> findByCategory(
    String category,
    Pageable pageable
);
~~~

Usage:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "name")
);

Page<Product> page =
    productRepository.findByCategory("accessories", pageable);

List<Product> products = page.getContent();
long total = page.getTotalElements();
int pageCount = page.getTotalPages();
~~~

Pageable describes page number, page size, and sort. In Elasticsearch, deep pagination via from/size has practical limits and can be resource-heavy. When scanning large datasets, consider search_after or an appropriate scroll mechanism instead of increasing page numbers without bound.

Page normally requires total hit information. If a screen only needs to know whether a next page exists, use Slice if supported by your version and repository method, or choose a query form that fetches only the needed count. Do not ask for exact totals when business logic does not require them.

### 3.3. Sorting via method name

You can declare a fixed sort using OrderBy:

~~~java
List<Product> findByCategoryOrderByPriceInCentsAsc(String category);

List<Product> findByCategoryOrderByPriceInCentsDesc(String category);
~~~

The method name specifies the sort property and ascending/descending direction. When dynamic sorting per request is needed, pass Sort or Pageable if supported by the method and version.

Sort fields must have compatible mappings. For analyzed text fields, sorting usually requires an auxiliary keyword field such as name.keyword rather than the text field itself. Check the actual mapping before sorting.

## 4. countBy: counting documents matching conditions

countBy returns the number of documents matching the predicate.

~~~java
long countByCategory(String category);

long countByActiveTrue();

long countByCategoryAndActiveTrue(String category);
~~~

Usage:

~~~java
long activeAccessories =
    productRepository.countByCategoryAndActiveTrue("accessories");
~~~

This is the direct way to express needing only a count. Avoid loading a List of Products into the application just to call size():

~~~java
// Do not load all results just to get the count:
long total = productRepository
    .findByCategory("accessories")
    .size();
~~~

That approach transfers many documents over the network, allocates Java objects, and wastes memory. countBy is better because the goal is counting.

Still, counting requires Elasticsearch to evaluate the condition across relevant indexes/shards. It is not a free operation. Avoid calling countBy repeatedly on every request when counts do not need constant real-time updates.

### 4.1. countBy vs. count()

Distinction:

| Method | Scope |
|---|---|
| count() | Counts all documents within the repository's scope |
| countByCategory(category) | Counts documents with category matching the passed value |
| countByActiveTrue() | Counts documents with active = true |
| countByCategoryAndActiveTrue(category) | Counts documents satisfying both conditions |

count() is typically inherited from the base repository interface. countBy... is a derived query driven by business conditions.

### 4.2. Return type and scale

Use long for counts to avoid the lower limit of int:

~~~java
long total = productRepository.countByCategory("accessories");
~~~

If a particular countBy method is unsupported in your current version, use ElasticsearchOperations.count with a corresponding Query. Never replace it with findBy loading full documents just to count.

## 5. existsBy: checking only whether matches exist

existsBy returns a boolean. It fits cases where a service only needs to know whether any document satisfies a condition.

~~~java
boolean existsBySku(String sku);

boolean existsByCategoryAndActiveTrue(String category);
~~~

Example:

~~~java
if (productRepository.existsBySku("SKU-1001")) {
    throw new IllegalArgumentException("SKU already exists");
}
~~~

existsBy differs from countBy in both return type and intent:

- existsBy only needs to know whether at least one match exists.
- countBy needs the total count of matches.

When only a boolean is needed, do not call countBy and compare greater than 0 if an equivalent existsBy is supported by your version. An existence query can skip exact counting work.

### 5.1. existsById and existsBySku

existsById is a standard repository method for checking by document ID. existsBySku is a derived query checking the sku property.

~~~java
boolean existsById(String id);

boolean existsBySku(String sku);
~~~

The two methods are not equivalent:

- existsById looks up a document by Elasticsearch document ID.
- existsBySku searches for documents whose sku field matches the value.

If SKU is not unique, existsBySku still returns only a boolean. It does not tell you how many products share that SKU.

### 5.2. existsBy does not replace uniqueness constraints

The following pattern is vulnerable to race conditions:

~~~java
if (!productRepository.existsBySku(sku)) {
    productRepository.save(product);
}
~~~

Two concurrent requests can both check and receive false before either writes data. Both then write the same SKU.

Elasticsearch does not automatically enforce a unique constraint on a keyword field like a relational database. If business logic requires uniqueness, derive the document ID deterministically from SKU or use conditional writes and handle conflicts properly. Never treat existsBy as a lock or uniqueness constraint.

## 6. deleteBy: deleting documents matching conditions

deleteBy expresses deletion by predicate:

~~~java
void deleteByCategory(String category);

void deleteByActiveFalse();
~~~

Example:

~~~java
productRepository.deleteByCategory("discontinued");
~~~

This method mutates data. Before using it, verify that the condition targets the exact intended scope and add safeguards against empty or invalid inputs.

### 6.1. Distinguishing deleteById, deleteAllById, and deleteBy

| Method | Purpose |
|---|---|
| deleteById(id) | Delete one document by ID |
| deleteAllById(ids) | Delete documents by a set of IDs |
| deleteBySku(sku) | Delete documents matching the SKU condition |
| deleteByCategory(category) | Delete documents matching the category condition |
| deleteAll() | Delete all documents in repository scope per implementation semantics |

deleteBy... is a conditional query method. deleteById and deleteAllById are standard CRUD methods. deleteAll() has broad impact and must be used with caution.

### 6.2. Return value of deleteBy

Return-type support for derived delete methods can vary across Spring Data Elasticsearch versions and query implementations. Simple example:

~~~java
void deleteByCategory(String category);
~~~

If you need to know how many documents were deleted, confirm whether your version supports numeric return types on derived delete methods. If the API does not provide the count as needed, use controlled delete/query operations via ElasticsearchOperations or the Elasticsearch Delete By Query API.

Do not assume a deleteBy method always returns the deleted count merely because another Spring Data module behaves that way.

### 6.3. Cost and scale of deleteBy

Conditional deletion may require Elasticsearch to locate matching documents and then execute deletions. Implementation details vary by version and query type. At large scale, inspect actual requests and consider the Delete By Query API or appropriate batching.

A large delete operation can:

- Consume CPU and I/O locating matching documents.
- Place load across multiple shards.
- Run for an extended duration.
- Impact concurrent reads and writes.
- Require handling timeouts, retries, and partial results depending on the API.

Do not execute broadly scoped deleteBy calls in production without verifying scope first. For critical data, run a read query beforehand to inspect the count and sample documents that will be affected.

## 7. Common predicates and support limits

Spring Data defines naming conventions for many condition types. Spring Data Elasticsearch supports a specific subset and semantics depending on version. Common groups in query derivation include:

| Group | Example method name | Intended meaning |
|---|---|---|
| Value match | findBySku, findBySkuIs | Equality |
| AND combination | findByCategoryAndActiveTrue | Both conditions hold |
| OR combination | findBySkuOrName | Either condition holds |
| Boolean | findByActiveTrue, findByActiveFalse | Value is true/false |
| Numeric comparison | findByPriceInCentsGreaterThan | Greater than |
| Boundary comparison | findByPriceInCentsGreaterThanEqual | Greater than or equal |
| Range | findByPriceInCentsBetween | Within range |
| Set membership | findByCategoryIn | In a set of values |
| Set exclusion | findByCategoryNotIn | Not in a set of values |
| String | findByNameStartingWith | Starts with string |
| Null | findByDescriptionIsNull | Null value per supported semantics |

These are example patterns illustrating naming conventions, not a guarantee that every keyword is implemented across all versions or field types of Spring Data Elasticsearch.

Before adopting a new predicate, check the supported keywords list for your exact version. If a method is unsupported, Spring may fail at repository creation time or the generated query may behave differently from what you expect.

### 7.1. Numeric and date comparisons

Predicates such as GreaterThan, LessThan, Between, Before, and After are commonly used for numeric/date types when supported by the version:

~~~java
List<Product> findByPriceInCentsGreaterThan(Long minimum);

List<Product> findByPriceInCentsBetween(
    Long minimum,
    Long maximum
);
~~~

Mappings must be compatible with comparison semantics. Numeric fields should use appropriate integer/long/double types; date fields need date mapping and consistent formats.

Do not run range comparisons on keyword fields merely because values look numeric. Keywords are compared lexicographically as strings, which can produce a different order than numeric ordering.

### 7.2. String conditions and analyzers

On a text field like name, queries may be analyzed according to the analyzer. On a keyword field like sku, matching usually compares intact values.

Examples:

~~~java
List<Product> findByName(String name);

List<Product> findBySku(String sku);
~~~

Both methods share the same naming structure yet do not necessarily share search semantics because their mappings differ.

Keywords such as Containing, StartingWith, EndingWith, Like, or IgnoreCase must be checked carefully against your Spring Data Elasticsearch version. Do not assume they behave identically to Spring Data JPA or Java's String.contains().

If you need wildcards, regexp, fuzzy, phrase, custom analyzers, or multilingual search, build explicit queries and inspect mappings/analyzers instead of relying on simple method names.

## 8. Property paths and nested field names

Spring Data parses property paths from method names. With nested entities:

~~~java
public class Address {
    private String city;
}

@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private Address address;
}
~~~

You may want to query by a nested property:

~~~java
List<Customer> findByAddressCity(String city);
~~~

The name AddressCity resolves to property address.city if the mapping context can locate that path.

If property names could be ambiguous, underscores can separate path segments in Spring Data conventions:

~~~java
List<Customer> findByAddress_City(String city);
~~~

Nested/object query support still depends on mappings. Elasticsearch distinguishes object and nested mappings; queries over arrays of objects require nested semantics when conditions must match on the same element. Derived queries do not alter mappings to turn object into nested.

For complex nested queries, use @Query or ElasticsearchOperations to express nested paths and conditions explicitly.

## 9. Combining AND, OR, and condition order

You can chain multiple predicates:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);

List<Product> findByCategoryAndPriceInCentsLessThan(
    String category,
    Long maximumPrice
);
~~~

OR:

~~~java
List<Product> findBySkuOrName(
    String sku,
    String name
);
~~~

When mixing AND and OR in the same method name, pay close attention to how the parser groups conditions and to readability. A long name can create different logic than the author intended if method-name parsing rules are misunderstood.

If an expression requires parenthesized logic, multiple branches, or explicit control over bool clauses (must/should/filter/must_not), use explicit queries. Explicit queries expose the logical structure directly and are easy to compare against REST requests.

## 10. Using @Query when derived queries fall short

Spring Data Elasticsearch lets you declare Elasticsearch queries with @Query on repository methods in supported versions.

Example query by SKU:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"term\":{\"sku\":\"?0\"}}")
    List<Product> findExactSku(String sku);
}
~~~

Placeholder ?0 references the first method argument. For complex JSON queries, escape strings properly and confirm valid JSON syntax.

Example price-range query:

~~~java
@Query("""
{
  "range": {
    "priceInCents": {
      "gte": ?0,
      "lte": ?1
    }
  }
}
""")
List<Product> findInPriceRange(Long minimum, Long maximum);
~~~

Text block syntax requires Java 15 or later. If the project targets an older Java version, use escaped Java strings or a query declaration supported by that version.

@Query is helpful when you need specific DSL control while keeping the method on the repository interface. If queries must be assembled dynamically from optional runtime conditions, ElasticsearchOperations is usually more flexible.

## 11. Using ElasticsearchOperations for dynamic queries

When filters vary per request, do not create dozens of repository methods for every combination of conditions.

Example using Criteria API:

~~~java
Criteria criteria = new Criteria("active").is(true);

if (category != null && !category.isBlank()) {
    criteria = criteria.and("category").is(category);
}

if (minimumPrice != null) {
    criteria = criteria.and("priceInCents").greaterThanEqual(minimumPrice);
}

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
    query,
    Product.class
);
~~~

This example illustrates assembling conditions from input values. Criteria syntax and query classes can change across Spring Data Elasticsearch versions; use the API corresponding to your project dependency.

Operations are appropriate when you need to:

- Add or omit filters dynamically per request.
- Run nested queries.
- Run aggregations.
- Control sorting, pagination, and source filtering.
- Query multiple indexes using IndexCoordinates.
- Use advanced Elasticsearch Query DSL features.

Repository derived queries suit simple, stable queries that are easily expressed by method names.

## 12. Pagination, totals, and query cost

A method returning Page may need total hit counts to populate Page.totalElements. On large datasets, computing exact totals carries a cost.

Example:

~~~java
Page<Product> findByCategory(String category, Pageable pageable);
~~~

If the UI only shows 20 results and a Next button, evaluate whether exact total page counts are truly necessary. You can pick a result structure without exact totals if supported by your Spring Data Elasticsearch version.

In addition:

- Cap page size.
- Avoid deep pagination with large offsets.
- Use deterministic sorting when iterating through data.
- For large datasets, consider search_after or scroll.
- Do not call countBy separately when Page already provides an acceptable total.
- Do not load an unbounded List only to filter in Java.

## 13. Safety when using deleteBy

Derived delete methods can remove many documents. Before calling them, ensure:

- Predicates are sufficiently specific.
- Nulls or blank strings are never passed unintentionally.
- You know which index/alias the repository targets.
- Authorization checks enforce who can perform the deletion.
- Appropriate logging/auditing exists for business requirements.
- Recovery or backup plans exist for critical data.

For example, instead of deleting directly using an unvalidated request category:

~~~java
productRepository.deleteByCategory(request.category());
~~~

validate inputs and permissions first:

~~~java
if (category == null || category.isBlank()) {
    throw new IllegalArgumentException("Category is required");
}

authorizationService.requireCanDeleteCategory(category);
productRepository.deleteByCategory(category);
~~~

Never design a deleteBy... method whose condition could become empty and accidentally wipe a broad scope. If business operations must delete many documents, consider scoped confirmation, batch limits, and result monitoring.

For complex conditions or bulk deletions, Elasticsearch Delete By Query may be better suited, though you must handle timeouts, version conflicts, throttling, and partial results per the API. Do not assume derived delete methods and Delete By Query share identical operational behavior.

## 14. Common errors

| Symptom | Possible cause | How to check |
|---|---|---|
| PropertyReferenceException | Property name in method does not exist | Cross-check field names in domain class |
| Repository fails to initialize | Unsupported predicate or return type | Check supported keywords and root cause |
| findBy returns empty | Wrong index, mapping, field name, or query semantics | Inspect @Document, mapping, and document _source |
| findBy on text misses expected matches | Analyzer differs from expectations | Check mapping and Analyze API |
| term-like query is not exact | Inappropriate keyword/text field or normalizer | Read mapping, use field matching semantics |
| countBy is slow | Query scans many shards or uses costly filters | Measure latency, narrow indexes, optimize filters |
| existsBy returns false | Wrong field, index, routing, or data not yet visible | Check ID/field, alias, routing, and refresh |
| deleteBy deletes too much | Overly broad predicate or unvalidated input | Run a read query first and check scope |
| Page with total is slow | Computing exact total hits is costly | Consider Slice/hit limits if supported |
| Nested property query fails | Incorrect object/nested mapping | Inspect mapping and use explicit nested queries |

When startup fails, read the full cause chain. A repository can be scanned successfully yet fail when Spring parses methods or builds queries. Not all repository errors are package-scanning problems.

## 15. Workflow for choosing how to declare queries

You can decide in the following order:

1. If conditions are simple and keyword support is clear, use findBy/countBy/existsBy/deleteBy.
2. If fixed JSON DSL is needed while keeping the method on the repository, use @Query.
3. If conditions vary per request, use ElasticsearchOperations.
4. If the query needs aggregations, nested clauses, scripts, geo, or complex scoring, use explicit query APIs.
5. If target indexes must be selected at runtime, use Operations with IndexCoordinates.

A combined repository example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByCategoryAndActiveTrue(String category);

    Page<Product> findByCategory(
        String category,
        Pageable pageable
    );

    long countByCategory(String category);

    boolean existsBySku(String sku);

    void deleteBySku(String sku);
}
~~~

These methods illustrate typical patterns. Before adding them to a project, verify supported keywords, return types, and overloads against your active Spring Data Elasticsearch version.

## 16. Verifying query methods with integration tests

Unit tests can verify that a service calls the right repository method, but only integration tests against Elasticsearch validate real mappings and queries.

Example:

~~~java
@Test
void shouldFindCountAndCheckExistence() {
    Product product = new Product(
        "P-1001",
        "SKU-1001",
        "Wireless Mouse",
        "accessories",
        259900L,
        true
    );

    productRepository.save(product);

    // Refresh index before checking query/search-derived methods
    indexOperations.refresh();

    assertThat(productRepository.findBySku("SKU-1001"))
        .hasSize(1);

    assertThat(productRepository.countByCategory("accessories"))
        .isEqualTo(1);

    assertThat(productRepository.existsBySku("SKU-1001"))
        .isTrue();
}
~~~

This is an illustrative example; the Product constructor, test setup, and indexOperations must match your actual entity and project. Get-by-ID and Search/Count have different visibility timing due to Elasticsearch's near-real-time refresh. In query method tests, refresh when newly written documents must be immediately searchable.

For deleteBy, tests should assert both that target documents were deleted and that non-matching documents remain:

~~~java
@Test
void shouldDeleteOnlyMatchingProducts() {
    productRepository.save(productA);
    productRepository.save(productB);

    indexOperations.refresh();

    productRepository.deleteBySku("SKU-DELETE");

    // Re-read by ID to confirm deletion scope.
    assertThat(productRepository.findById("P-DELETE")).isEmpty();
    assertThat(productRepository.findById("P-KEEP")).isPresent();
}
~~~

If checking with the Search API immediately after delete, you may need a refresh before asserting search results.

## 17. Quick reference table

| Need | Method/approach |
|---|---|
| Search by property | findByProperty(...) |
| Combine conditions | findByAAndB(...), findByAOrB(...) |
| Search and paginate | findByProperty(..., Pageable) |
| Count by condition | countByProperty(...) |
| Check whether matches exist | existsByProperty(...) |
| Check by document ID | existsById(id) |
| Delete by condition | deleteByProperty(...) if version supports |
| Fixed Query DSL | @Query |
| Dynamic or advanced queries | ElasticsearchOperations |
| Runtime index selection | Operations with IndexCoordinates |

findBy, countBy, existsBy, and deleteBy let you express simple queries right on repository interfaces. Pick the prefix matching the result you need, align property paths with the domain model, confirm predicate support in your Spring Data Elasticsearch version, and remember that mappings govern query semantics. For complex conditions, dynamic queries, or large-scale deletions, move to @Query or ElasticsearchOperations for clear control over DSL and impact scope.
