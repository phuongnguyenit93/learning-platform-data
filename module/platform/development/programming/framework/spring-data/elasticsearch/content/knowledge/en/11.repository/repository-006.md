# Distinguishing CRUD Methods and Custom Query Methods

## 1. Repositories in Spring Data Elasticsearch

Spring Data Elasticsearch provides the Repository abstraction so the service layer can interact with documents through Java methods. Instead of constructing HTTP requests manually for every operation, the application declares a repository interface extending Spring Data's base interface.

Example product entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

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

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters, and setters
}
~~~

Repository:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

`ElasticsearchRepository<Product, String>` indicates that the repository manages the `Product` entity and its identifier type is `String`. The repository inherits foundational operations such as saving, finding by ID, counting, and deleting.

When the application needs to query by business criteria, additional methods can be declared directly in the interface. Spring Data supports two common approaches:

- **Derived query:** Spring Data parses the method name and generates a query from it.
- **Declared query:** the developer explicitly declares the query content, usually via the `@Query` annotation containing Elasticsearch Query DSL.

Additionally, repositories can be extended with custom implementations when building dynamic queries or handling complex search behavior.

## 2. What Are CRUD Methods?

CRUD stands for Create, Read, Update, and Delete. These are the fundamental operations for managing documents.

CRUD methods are inherited from Spring Data's repository interfaces. For example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

You do not need to redeclare basic methods. They can be used directly:

~~~java
productRepository.save(product);
productRepository.findById("p-100");
productRepository.findAll();
productRepository.existsById("p-100");
productRepository.count();
productRepository.deleteById("p-100");
productRepository.delete(product);
~~~

Common methods:

| Method | Meaning |
|---|---|
| `save(entity)` | Save a document; if the ID already exists, the corresponding document may be overwritten with the new data |
| `saveAll(entities)` | Save multiple entities |
| `findById(id)` | Find a single document by identifier |
| `findAll()` | Retrieve all documents |
| `findAll(Pageable)` | Retrieve documents with pagination |
| `findAll(Sort)` | Retrieve documents in sorted order |
| `existsById(id)` | Check whether a document with that ID exists |
| `count()` | Count documents |
| `deleteById(id)` | Delete a document by ID |
| `delete(entity)` | Delete the document corresponding to the entity |
| `deleteAll()` | Delete all documents within the repository's scope |

CRUD focuses on operating on documents by identifier or across the full dataset. These methods do not express custom search criteria such as product name, category, price range, or status.

### CRUD is not synonymous with business queries

Suppose the requirement is to find all products in the `audio` category with a price less than or equal to 2,000,000. CRUD does not provide a built-in method carrying that condition. We need to declare a query method:

~~~java
List<Product> findByCategoryAndPriceLessThanEqual(
    String category,
    Double maxPrice
);
~~~

The difference lies in the origin and purpose of each method:

- CRUD methods are inherited from the base repository.
- Custom query methods are added according to application requirements and encode specific conditions.

## 3. What Are Custom-Declared Query Methods?

A custom-declared query method is a method named by the developer in the repository to represent a search condition. Spring Data reads the method name, parses parts such as `find`, `By`, property names, and operators, and constructs the corresponding query.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndActiveTrue(String category);

    List<Product> findByPriceLessThan(Double maxPrice);

    List<Product> findByCategoryAndPriceLessThanEqual(
        String category,
        Double maxPrice
    );
}
~~~

The methods above need no body. Spring Data creates the implementation during repository initialization.

Example call:

~~~java
List<Product> products =
    productRepository.findByCategoryAndPriceLessThanEqual(
        "audio",
        2_000_000.0
    );
~~~

Spring Data parses the method name:

- `findBy`: find documents matching conditions.
- `Category`: the entity's `category` property.
- `And`: combine two conditions.
- `Price`: the `price` property.
- `LessThanEqual`: less-than-or-equal operator.

Conceptually, the query may correspond to:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "audio"
          }
        },
        {
          "range": {
            "price": {
              "lte": 2000000
            }
          }
        }
      ]
    }
  }
}
~~~

This illustrates the search criteria. The actual Query DSL generated depends on the Spring Data Elasticsearch version and the mapping type of each field.

## 4. Structure of Derived Query Method Names

Method names typically consist of an operation prefix, the `By` delimiter, properties, and operators.

~~~text
findBy + Category + And + Price + LessThanEqual
  |        |                  |        |
  |        |                  |        +-- Comparison operator
  |        |                  +----------- Second property
  |        +------------------------------ First property
  +--------------------------------------- Operation type
~~~

Common prefixes:

| Prefix | Purpose |
|---|---|
| `findBy...` | Find documents matching conditions |
| `readBy...` | Read documents matching conditions |
| `getBy...` | Get documents matching conditions |
| `queryBy...` | Query documents matching conditions |
| `countBy...` | Count documents matching conditions |
| `existsBy...` | Check whether any document matches conditions |
| `findFirstBy...` | Retrieve the first result matching conditions |
| `findTopBy...` | Retrieve top results up to a limit |

Supported keywords and operator combinations depend on the Spring Data module and version. Do not assume every keyword supported in JPA is supported in Spring Data Elasticsearch.

Property names must match properties on the Java entity. For example, if the entity has a `category` property, the method should use `findByCategory`, even if Elasticsearch mapping renames the stored field via `@Field(name = "...")`. Spring Data uses mapping metadata to link Java properties to stored fields.

## 5. Common Query Operators

Several common operators can be expressed via method names:

| Operator | Method name example | Meaning |
|---|---|---|
| Equal | `findByCategory` or `findByCategoryEquals` | Matches category value |
| Not equal | `findByCategoryNot` | Not equal to specified value |
| Less than | `findByPriceLessThan` | Price strictly less than given value |
| Less than or equal | `findByPriceLessThanEqual` | Price does not exceed given value |
| Greater than | `findByPriceGreaterThan` | Price strictly greater than given value |
| Greater than or equal | `findByPriceGreaterThanEqual` | Price at least equal to given value |
| Within range | `findByPriceBetween` | Price falls within range |
| In list | `findByCategoryIn` | Matches one of the values |
| Not in list | `findByCategoryNotIn` | Not in the list |
| Has value | `findByNameIsNotNull` | Field has a non-null value |
| Has no value | `findByNameIsNull` | Field is null or has no indexed value per Elasticsearch semantics |
| Boolean true | `findByActiveTrue` | `active` field is true |
| Boolean false | `findByActiveFalse` | `active` field is false |

Combined examples:

~~~java
List<Product> findByPriceBetween(Double min, Double max);

List<Product> findByCategoryIn(Collection<String> categories);

List<Product> findByActiveTrueAndPriceGreaterThan(Double minPrice);

long countByCategory(String category);

boolean existsByCategoryAndActiveTrue(String category);
~~~

Methods returning `count` or `exists` fit when the application only needs a count or existence check instead of loading all matching documents into memory.

For text conditions, distinguish field types:

- `keyword` is usually used for exact matching, filtering, and aggregations.
- `text` is processed by an analyzer and suits full-text search.
- Method names can express basic conditions, yet text search behavior also depends on the analyzer and the query Spring Data generates.

Consult the documentation for your exact version to confirm specific operators, especially for wildcard, fuzzy, phrase, and geo queries.

## 6. Combining AND, OR Conditions and Sorting

Multiple conditions can be combined with `And` and `Or`:

~~~java
List<Product> findByCategoryAndActiveTrue(String category);

List<Product> findByCategoryOrActiveTrue(String category);
~~~

`And` requires combined conditions to match together. `Or` allows results matching either branch. When an expression uses multiple logical operators, carefully inspect how Spring Data parses the method name and groups operator precedence.

Sort order can be declared directly in the name:

~~~java
List<Product> findByCategoryOrderByPriceAsc(String category);

List<Product> findByActiveTrueOrderByPriceDesc();
~~~

You can pass `Sort` when ordering needs to be decided at call time:

~~~java
List<Product> findByCategory(
    String category,
    Sort sort
);
~~~

Example:

~~~java
List<Product> products = productRepository.findByCategory(
    "audio",
    Sort.by(Sort.Direction.ASC, "price")
);
~~~

Property names used in `Sort` are typically the Java property names of the entity. Verify field mappings and data-type sort support in the version you are using.

## 7. Pagination and Return Types

Query methods can accept `Pageable` to limit results and request pagination:

~~~java
Page<Product> findByCategory(String category, Pageable pageable);
~~~

Invocation:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
);

Page<Product> page =
    productRepository.findByCategory("audio", pageable);
~~~

Common return types:

| Return type | When to use |
|---|---|
| `Product` | Expect at most one result |
| `Optional<Product>` | May return zero or one result |
| `List<Product>` | Need a list of results |
| `Page<Product>` | Need current page data along with total pages/elements info |
| `Slice<Product>` | Only need to know if there is a next page, if supported for the method and version |
| `SearchHits<Product>` | Need search metadata such as scores, highlights, or hit info |
| `SearchPage<Product>` | Need search results combined with pagination metadata |

With `Page`, total result counts may cause Elasticsearch to perform extra work counting or tracking total hits. For large datasets, consider whether you truly need total page counts or only need to fetch the next page.

Unpaginated `findAll()` can load a huge amount of data. In real applications, use `Pageable`, result limits, or a scrolling/search pagination mechanism suited to your requirements and Elasticsearch version.

## 8. CRUD Methods vs. Derived Queries: Side-by-Side Example

Consider the product repository:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    // Inherited CRUD: no need to declare manually
    // save(Product)
    // findById(String)
    // findAll()
    // deleteById(String)

    // Derived queries: conditions inferred from method names
    List<Product> findByCategory(String category);

    List<Product> findByCategoryAndActiveTrue(String category);

    List<Product> findByCategoryAndPriceLessThanEqual(
        String category,
        Double maxPrice
    );

    Optional<Product> findFirstByName(String name);

    Page<Product> findByActiveTrue(Pageable pageable);
}
~~~

Comparison table:

| Need | How to call | Method kind |
|---|---|---|
| Save a product | `save(product)` | Inherited CRUD |
| Find product by ID | `findById(id)` | Inherited CRUD |
| Delete by ID | `deleteById(id)` | Inherited CRUD |
| Find by category | `findByCategory(category)` | Derived query |
| Find active products | `findByActiveTrue()` | Derived query |
| Find by category and max price | `findByCategoryAndPriceLessThanEqual(...)` | Derived query |
| Find the first result by name | `findFirstByName(name)` | Derived query |
| Retrieve active products by page | `findByActiveTrue(pageable)` | Derived query |

Key takeaway: CRUD methods are supplied by parent interfaces, whereas derived queries are added according to the domain model's properties and conditions.

## 9. Declared Queries Using @Query

Method names can become long or awkward when a query has many conditions. In such cases, `@Query` lets you declare Elasticsearch Query DSL directly.

Example:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": \"?0\"}}")
    List<Product> searchByName(String keyword);
}
~~~

`@Query` takes a JSON string representing the query. The placeholder `?0` refers to the first method parameter. The second parameter can be referenced with `?1`, the third with `?2`, and so on.

Example combining full-text search and filters:

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
          "category": "?1"
        }
      },
      {
        "range": {
          "price": {
            "lte": "?2"
          }
        }
      }
    ]
  }
}
""")
List<Product> searchProducts(
    String keyword,
    String category,
    Double maxPrice
);
~~~

The snippet above uses a Java text block for readability. If a project runs on a Java version without text blocks, write the string using concatenation or escaped quotes.

Query meaning:

- `match` runs full-text search on `name`.
- `must` holds required query clauses that can affect relevance scoring.
- `filter` narrows results by category and price range without using filter clauses to compute relevance scores.
- `term` suits the `keyword`-typed `category` field.
- `range` caps the price at the provided argument.

`@Query` is still a custom-declared query method, except the query body is written explicitly by the developer rather than inferred from the method name.

## 10. When to Use Derived Queries vs. @Query?

Both approaches create query methods in the repository, but they suit different levels of complexity.

| Criterion | Derived query | `@Query` |
|---|---|---|
| Query source | Method name | Query DSL string |
| Code length | Concise for simple conditions | Can be longer |
| Readability | Easy to read with few conditions | Shows the exact query structure directly |
| Operators and clauses | Depends on parser and supported keywords | Can leverage full Query DSL capabilities |
| Modifying conditions | Change method name or parameters | Edit JSON query and placeholders |
| Dynamic queries | Limited when query structure varies heavily | Fits relatively fixed query shapes; complex dynamic queries should use custom implementations |
| Best suited for | Property filtering, comparisons, basic sorting | Full-text, `bool` queries, `range`, `nested`, or DSL structures needing control |

Choose derived queries when the method name stays short, expresses business intent clearly, and uses operators supported by Spring Data.

Choose `@Query` when you need direct control over Query DSL structure—for instance combining `match`, `bool`, `filter`, `range`, `nested`, or operators that derived queries do not express cleanly.

Do not turn a method name into a long sentence packed with `And`, `Or`, and conditions. Overly long method names are hard to read, hard to modify, and make exact boolean grouping unclear.

## 11. Custom Repository Implementations for Complex Queries

There are requirements where neither a method name nor a fixed `@Query` string is convenient, such as:

- Users picking arbitrary combinations of UI filters.
- Adding a clause only when its parameter is supplied.
- Combining query branches based on permissions or context.
- Needing aggregations, highlighting, suggestions, or special result metadata.
- Building Query DSL with dynamic structure.

You can extend the repository with a custom fragment:

~~~java
import java.util.List;

public interface ProductSearchExtension {

    List<Product> search(ProductSearchCriteria criteria);
}
~~~

Extend both the base repository and the fragment:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String>,
                ProductSearchExtension {
}
~~~

A fragment implementation class can inject `ElasticsearchOperations` to build queries:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchExtensionImpl
        implements ProductSearchExtension {

    private final ElasticsearchOperations operations;

    public ProductSearchExtensionImpl(
            ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<Product> search(ProductSearchCriteria criteria) {
        // Build Query or NativeQuery from present criteria.
        // Call operations.search(query, Product.class).
        // Convert SearchHits<Product> into a list of Product.
        throw new UnsupportedOperationException(
            "Implement query construction for the application's criteria"
        );
    }
}
~~~

This is a structural skeleton for a custom fragment. Query construction must be implemented for the application's actual fields and criteria using the query API corresponding to your Spring Data Elasticsearch version.

The advantage of this approach is isolating dynamic search logic into a dedicated component. The repository retains simple CRUD and derived query methods, while complex search logic can be organized, tested, and evolved independently.

Do not move every single query into a custom implementation. When `findByCategory` suffices, a derived query is shorter and clearer.

## 12. Key Things to Watch When Writing Method Names

**Property names must match the entity.** Spring Data analyzes Java properties rather than simply guessing JSON field names. If the entity has `productCategory`, the method should use `findByProductCategory`, even when mapping renames the field in Elasticsearch.

**Check supported operators.** Not every Spring Data JPA keyword applies to Elasticsearch. Verify against the keyword list of your active version.

**Distinguish `text` and `keyword`.** Equality matching on a `keyword` field has different semantics from full-text search on a `text` field. Pick mappings aligned with your search goals.

**Be careful with nested objects.** If conditions must match within the same element of a nested collection, query inside the proper `nested` scope. Do not assume every derived query over nested properties automatically emits a `nested` query matching business expectations; use `@Query` or `ElasticsearchOperations` when you need control over nested DSL.

**Avoid returning more results than expected.** Methods returning a single entity or `Optional` require conditions guaranteeing at most one result. If multiple documents can match, use `List` or an appropriate pagination type.

**Watch out for conditional delete methods.** Derived delete methods can delete many documents. Verify the condition and scope clearly before invoking them.

**Do not load an entire index.** `findAll()` on a large index can place heavy load on the system. Use filters, pagination, or streaming/scrolling search mechanisms as appropriate.

**Keep method names reflective of business intent.** A method named `findActiveProductsUnderPrice` may read better than a long chain of technical attributes, yet the name must still conform to derived-query syntax that Spring Data can parse. Once names become hard to read, consider `@Query` or a custom fragment.

## 13. Testing and Using Repositories in Services

Services should call repositories by business intent rather than constructing Elasticsearch requests everywhere.

Example:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Product save(Product product) {
        return productRepository.save(product);
    }

    public List<Product> findActiveProducts(String category) {
        return productRepository.findByCategoryAndActiveTrue(category);
    }

    public List<Product> findProductsUnderPrice(
            String category,
            Double maxPrice) {
        return productRepository.findByCategoryAndPriceLessThanEqual(
            category,
            maxPrice
        );
    }
}
~~~

When testing repositories, use integration tests against an Elasticsearch version compatible with your application. Verify at least:

1. CRUD: saving, finding by ID, updating, and deleting documents.
2. Derived queries: verifying `And`, `Or`, range, and sort conditions produce expected results.
3. Declared queries: verifying placeholders bind arguments properly and Query DSL enforces conditions.
4. Pagination: checking pages, ordering, and total counts when using `Page`.
5. Mapping: verifying `text`/`keyword` and `nested` fields are queried with the right semantics.
6. No-result cases, nulls, or missing fields according to the application's contract.

Do not merely mock the repository and conclude Elasticsearch queries work accurately. Mocks verify that the service calls the expected methods, but they do not prove that Query DSL, mappings, and analyzers actually return desired results.

## 14. Rules for Choosing a Method Approach

Use these guidelines when designing a repository:

- Use inherited CRUD for basic saving, updating, finding by ID, counting, and deleting.
- Use derived queries for simple, stable conditions that remain clear in a method name.
- Use `@Query` when you need explicit Elasticsearch Query DSL while keeping a relatively fixed query structure.
- Use custom repository fragments with `ElasticsearchOperations` when building dynamic queries, multi-branch conditions, or advanced search responses.
- Use `Pageable` or appropriate pagination instead of fetching everything.
- Check your Spring Data Elasticsearch version because parser capabilities, return types, and query APIs evolve.

## Conclusion

CRUD methods are foundational operations inherited from repositories for saving, reading, updating, and deleting documents. Custom-declared query methods add business criteria and can be implemented via derived queries, `@Query`, or custom repository fragments.

Derived queries fit simple, readable conditions. `@Query` provides direct control over Elasticsearch Query DSL. Custom implementations fit dynamic or complex search. Choosing the right method style keeps the repository interface clean, services easy to use, and Elasticsearch queries maintainable.

## References

- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch — Query Methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
- [Spring Data Elasticsearch — Custom Repository Implementations](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/custom-implementations.html)
