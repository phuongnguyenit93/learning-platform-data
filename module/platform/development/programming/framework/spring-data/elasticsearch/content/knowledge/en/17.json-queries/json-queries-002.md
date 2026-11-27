# Declaring Queries with `@Query` on Repositories

Spring Data Elasticsearch lets you declare queries directly on repository methods using the `@Query` annotation. Instead of having Spring infer the query from the method name, the developer writes the JSON Query DSL directly that Elasticsearch will execute. This approach is useful when a query needs `bool`, `match`, `term`, `range`, `ids`, nested conditions, or when a derived method name becomes long and hard to read.

`@Query` keeps most query code close to the repository interface while Spring Data still handles parameter binding, result mapping to entities, and return types such as `List`, `Page`, or `SearchHits`. To use it effectively, you need to understand the JSON the annotation accepts, placeholder rules, SpEL, pagination, and the limitations of declared queries compared to `NativeQuery` or `ElasticsearchOperations`.

## 1. When Should You Use `@Query`?

Spring Data Elasticsearch provides several ways to build queries:

| Query Approach | How It Works | Best Suited When |
|---|---|---|
| Derived query | Spring parses method names like `findByCategoryAndPriceGreaterThan` | Simple conditions where the method name stays readable |
| `@Query` | Declares JSON Query DSL on a repository method | You need control over query structure while still using the repository abstraction |
| `@SearchTemplateQuery` | Invokes a search template stored in Elasticsearch | Query templates are managed separately on the cluster and reused |
| `CriteriaQuery` | Builds queries using `Criteria` objects | You want to construct queries using a fluent Java API |
| `NativeQuery` | Uses the Elasticsearch Java API Client query builders | You need broader Search API features or advanced Query DSL |

You do not need `@Query` for every method. A method like `findByStatus(String status)` is usually easier to read when Spring Data generates the query automatically. However, if you need to combine `must`, `filter`, `should`, `minimum_should_match`, nested queries, or a specific Query DSL structure, `@Query` is often clearer.

## 2. Sample Repository and Entity Structure

The examples in this article use a `Product` entity stored in the `products` index:

```java
package com.example.catalog.domain;

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

    @Field(type = FieldType.Long)
    private Long priceInCents;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters and setters
}
```

What this mapping means:

- `name` is `text`, suitable for full-text queries such as `match`.
- `category` is `keyword`, suitable for exact matching with `term` or `terms`.
- `priceInCents` is `long`, suitable for numeric range queries.
- `active` is `boolean`, suitable for true/false conditions.

The repository extends `ElasticsearchRepository`:

```java
package com.example.catalog.repository;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import com.example.catalog.domain.Product;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

The `@Query` annotation is imported from `org.springframework.data.elasticsearch.annotations.Query` and placed directly on methods of the repository interface.

## 3. Your First Query with `@Query`

Example searching products by name using `match`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
    List<Product> searchByName(String text);
}
```

`?0` is the placeholder for the first parameter of the method. When calling:

```java
List<Product> products = productRepository.searchByName("mechanical keyboard");
```

Spring Data binds the parameter value into the query and produces a search request with a query section equivalent to:

```json
{
  "query": {
    "match": {
      "name": {
        "query": "mechanical keyboard"
      }
    }
  }
}
```

The value of `@Query` must be valid JSON Query DSL. Spring Data uses this string as the value of the `query` section in the search request. Therefore, the annotation content typically starts with a query clause such as `match`, `bool`, `term`, or `range`; do not wrap it in an outer `{"query": ...}` object.

### 3.1. Using Java Text Blocks for Readable JSON

With Java 15 and later, text blocks avoid having to escape every double quote:

```java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
List<Product> searchByName(String text);
```

If the project uses an older Java version, use a standard Java string and escape double quotes as in the first example. Both approaches declare the exact same JSON query.

## 4. Placeholders `?0`, `?1`, `?2`

Repository method parameters can be inserted into the query using 0-based numbered placeholders:

- `?0`: first bindable parameter.
- `?1`: second bindable parameter.
- `?2`: third bindable parameter.

Example searching products by category and price range:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "category": "?0" } },
          { "range": { "priceInCents": {
            "gte": ?1,
            "lte": ?2
          } } }
        ]
      }
    }
    """)
List<Product> findInCategoryAndPriceRange(
        String category,
        Long minimumPrice,
        Long maximumPrice);
```

Calling the method:

```java
List<Product> products = repository.findInCategoryAndPriceRange(
        "keyboards", 500000L, 2000000L);
```

The JSON string after binding has an equivalent structure:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": {
          "gte": 500000,
          "lte": 2000000
        } } }
      ]
    }
  }
}
```

### 4.1. Quoting Placeholders According to JSON Data Type

Each placeholder must sit in the position of the JSON type that Elasticsearch expects:

| Parameter Value | How to Place the Placeholder |
|---|---|
| Single string | `"?0"` |
| Integer/decimal number | `?0` |
| Boolean | `?0` |
| JSON collection/array | `?0` without quotes |
| JSON object | Place the placeholder at the object position if the binding supports that structure |

Numeric example:

```java
@Query("{\"range\": {\"priceInCents\": {\"gte\": ?0}}}")
List<Product> findWithMinimumPrice(Long minimumPrice);
```

String example:

```java
@Query("{\"term\": {\"category\": \"?0\"}}")
List<Product> findByExactCategory(String category);
```

Do not wrap a collection in `"?0"` if the query expects a JSON array. Quoting it incorrectly causes Elasticsearch to receive a string instead of an array, returning a parse error or failing to achieve the intended semantics.

### 4.2. Placeholders Are Not Manual String Concatenation

Let Spring Data bind parameters into the query. Avoid manually splicing user values into JSON using `String.format`, the `+` operator, or string templates before calling the client. Manual string concatenation easily produces malformed JSON when values contain quotes, backslashes, or special characters.

Placeholder indices follow the order of query parameters, not byte offsets or variable names. Whenever you reorder method parameters, re-check every `?0`, `?1`, and subsequent placeholder.

## 5. Declaring Common Query DSL Types

`@Query` is not limited to `match`. Any valid Elasticsearch query clause supported by repository query execution can be declared as JSON.

### 5.1. Full-Text Query with `match`

```java
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
List<Product> searchNameContainingAllTerms(String text);
```

`match` analyzes the search string using the field's search analyzer. With `operator: and`, all analyzed terms must satisfy the condition; if `operator` is omitted, the default for `match` is typically `or`.

### 5.2. Exact Matching with `term`

```java
@Query("""
    {
      "term": {
        "category": "?0"
      }
    }
    """)
List<Product> findByCategoryExact(String category);
```

`term` matches an indexed term value. It is usually suitable for `keyword`, IDs, status codes, or classification values. Do not use `term` on a `text` field expecting Elasticsearch to analyze the string like `match`.

### 5.3. Value Sets with `terms`

`terms` checks whether a field matches any of the supplied values:

```java
@Query("{\"terms\": {\"category\": ?0}}")
List<Product> findByAnyCategory(Collection<String> categories);
```

When called with `List.of("keyboards", "mice")`, the query receives a JSON array:

```json
{
  "query": {
    "terms": {
      "category": ["keyboards", "mice"]
    }
  }
}
```

The collection placeholder is written without quotes because the value must be a JSON array.

### 5.4. Price Ranges with `range`

```java
@Query("""
    {
      "range": {
        "priceInCents": {
          "gte": ?0,
          "lt": ?1
        }
      }
    }
    """)
List<Product> findByPriceRange(Long fromInclusive, Long toExclusive);
```

`gte` includes the lower bound; `lt` excludes the upper bound. The `gte` and `lt` pair is often useful when querying consecutive ranges without overlapping at boundaries.

### 5.5. Combining Conditions with `bool`

Example finding products with a matching name, exact category, minimum price, and active status:

```java
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
          { "term": { "category": "?1" } },
          { "range": { "priceInCents": { "gte": ?2 } } },
          { "term": { "active": true } }
        ]
      }
    }
    """)
List<Product> searchActiveProducts(
        String text,
        String category,
        Long minimumPrice);
```

In `bool`:

- `must` requires the clause to match and usually contributes to the score.
- `filter` requires the clause to match without calculating a relevance score; suited for exact filtering criteria.
- `should` expresses optional/boosted conditions or OR conditions, depending on `minimum_should_match` and the bool structure.
- `must_not` excludes documents matching the clause from results.

### 5.6. Querying by IDs with `ids`

```java
@Query("{\"ids\": {\"values\": ?0}}")
List<Product> findDocumentsByIds(Collection<String> ids);
```

The `ids` query accepts an array of document IDs. This is useful when you already have a list of IDs and want to retrieve the corresponding documents in one query instead of calling `findById` repeatedly.

### 5.7. Checking Field Existence with `exists`

```java
@Query("{\"exists\": {\"field\": \"category\"}}")
List<Product> findProductsWithCategory();
```

`exists` checks whether a field has an indexed value according to Elasticsearch semantics. It is not simply equivalent to checking whether a Java property is non-`null`, because mappings, `null_value`, empty values, and `_source` can affect the outcome.

## 6. Using SpEL in `@Query`

In addition to positional placeholders, Spring Data Elasticsearch supports SpEL expressions inside queries declared with `@Query`. SpEL is useful when you need to reference parameters by name, read properties from a parameter object, transform a collection, or read a Spring bean.

### 6.1. Referencing Parameters by Name

Example using `@Param` to give a parameter a stable name:

```java
import org.springframework.data.repository.query.Param;

@Query("""
    {
      "term": {
        "category": "#{#category}"
      }
    }
    """)
List<Product> findByCategoryWithSpel(@Param("category") String value);
```

`#{#category}` references the parameter named `category`. Using `@Param` ensures the query does not depend on whether the compiler preserves Java parameter names.

### 6.2. Accessing Properties of a Parameter Object

You can pass an object holding multiple conditions:

```java
public record ProductSearchCriteria(String category, Long minimumPrice) {
}
```

Repository:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "category": "#{#criteria.category}" } },
          { "range": { "priceInCents": {
            "gte": #{#criteria.minimumPrice}
          } } }
        ]
      }
    }
    """)
List<Product> search(@Param("criteria") ProductSearchCriteria criteria);
```

SpEL accesses properties using dot notation. Make sure the property exists and has a data type compatible with the JSON position where it is used.

### 6.3. Passing Collections via SpEL

When using SpEL to insert a collection into `terms`, do not put the collection inside quotes:

```java
@Query("""
    {
      "terms": {
        "category": #{#categories}
      }
    }
    """)
List<Product> findByCategories(
        @Param("categories") Collection<String> categories);
```

With `List.of("keyboards", "mice")`, the expression produces a JSON array:

```json
{
  "terms": {
    "category": ["keyboards", "mice"]
  }
}
```

If the collection contains objects rather than strings, SpEL collection projection can extract the required property:

```java
public record CategoryFilter(String value) {
}
```

```java
@Query("""
    {
      "terms": {
        "category": #{#filters.![value]}
      }
    }
    """)
List<Product> findByCategoryFilters(
        @Param("filters") Collection<CategoryFilter> filters);
```

The `![value]` expression creates a new collection containing the `value` property from each element.

### 6.4. Referencing a Spring Bean

SpEL can also access a bean by name using the `@` symbol:

```java
@Query("""
    {
      "term": {
        "tenantId": "#{@tenantContext.currentTenantId()}"
      }
    }
    """)
List<Product> findForCurrentTenant();
```

In the example, Spring invokes the `tenantContext` bean to obtain the current tenant. This can be helpful for shared contextual values, though it couples the query to an external bean outside the repository. For complex business logic, consider creating a custom repository or service so dependencies and control flow stay clear.

SpEL expressions in annotations are developer-declared configuration. Never build expressions from arbitrary user-submitted content, and never allow users to control which expression gets executed.

## 7. Pagination and Sorting

Repository methods with `@Query` can accept `Pageable` for pagination:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query("""
    {
      "match": {
        "name": {
          "query": "?0"
        }
      }
    }
    """)
Page<Product> searchByName(String text, Pageable pageable);
```

Calling the method:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "priceInCents"));

Page<Product> page = repository.searchByName("keyboard", pageable);
```

`PageRequest.of(0, 20, ...)` retrieves the first page with up to 20 results sorted by ascending price. `Pageable` is a parameter that controls pagination and sorting, not a regular query placeholder to put into the JSON.

### 7.1. `Page`, `List`, and `SearchHits`

| Return Type | Contents |
|---|---|
| `List<Product>` | List of matched entities |
| `Page<Product>` | Content of a single page along with pagination/total element info |
| `SearchHits<Product>` | `SearchHit` metadata such as score, ID, sort values, and total hit info |
| `List<SearchHit<Product>>` | List of hits with per-result metadata |
| `Stream<Product>` or `Stream<SearchHit<Product>>` | Stream of results for sequential processing; must be closed when finished |
| `SearchPage<Product>` | Page of `SearchHit` entries, preserving search metadata |

Choose `Page` when the UI needs page numbers or total result counts. Choose `SearchHits` when you need scores or Elasticsearch metadata. Choose `List` when you only need entities and the result count is reasonably bounded.

### 7.2. Sorting on the Right Field

Elasticsearch cannot normally sort on arbitrary `text` fields. For data that needs both full-text search and sorting, a `keyword` multi-field is commonly declared:

```java
@Field(type = FieldType.Text, fielddata = false)
private String name;
```

The corresponding mapping can add a subfield:

```json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
```

When sorting by name, use the keyword field such as `name.keyword` if the mapping defines that field. Do not enable `fielddata` on `text` just for sorting without evaluating its memory cost.

## 8. Query Lookup Strategy

The Spring Data repository infrastructure needs to decide how to create a query for each method. Common strategies:

| Strategy | How It Works |
|---|---|
| `CREATE` | Builds a query from the method name |
| `USE_DECLARED_QUERY` | Requires a declared query; throws an error during repository initialization if none is found |
| `CREATE_IF_NOT_FOUND` | Looks for a declared query first and falls back to creating from the method name if absent; this is the default |

With `@Query`, the method has a declared query. Under the default `CREATE_IF_NOT_FOUND` strategy, Spring Data uses the declared query rather than trying to parse the method name as a derived query.

You can configure the strategy on `@EnableElasticsearchRepositories` if the application needs a uniform lookup rule. Normally you do not need to change the default just to use `@Query`.

## 9. `@Query` Describes Only the Query Clause, Not the Full Search API Request

An important point is that the string inside `@Query` is placed by Spring Data into the `query` section of the search request. For example, the annotation:

```java
@Query("{\"match\": {\"name\": \"?0\"}}")
List<Product> findByName(String name);
```

is wrapped in a search request equivalent to:

```json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
```

Do not declare the annotation like this:

```java
@Query("{\"query\": {\"match\": {\"name\": \"?0\"}}}")
```

because then an object with key `query` gets placed where a query clause is expected, resulting in invalid nesting.

`@Query` is suited for declaring the query section. When you need to control other parts of the Search API such as aggregations, highlighting, collapse, suggest, runtime mappings, search after, or other advanced options, consider `NativeQuery` and `ElasticsearchOperations`. Exact coverage depends on the Spring Data Elasticsearch version and corresponding client API.

## 10. When Should You Use `@SearchTemplateQuery`?

If a query is stored as a search template on Elasticsearch, a repository method can reference the template using `@SearchTemplateQuery`:

```java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

@SearchTemplateQuery(id = "product-by-title")
SearchHits<Product> searchByTitle(String title);
```

Method parameters are sent to the search template as key/value pairs using the parameter names. The search template must be created and managed on Elasticsearch before the method is called.

Key difference:

- `@Query` stores the JSON query inside the application's source code.
- `@SearchTemplateQuery` references a template stored on the cluster.

Search templates are useful when the same query needs to be managed or updated independently of application releases. If a query is used in only one repository and rarely changes, `@Query` is usually simpler.

## 11. Comparing `@Query` with `CriteriaQuery` and `NativeQuery`

| Criterion | `@Query` | `CriteriaQuery` | `NativeQuery` |
|---|---|---|---|
| Where defined | Annotation on repository method | Java code | Java code using Elasticsearch client query builders |
| Format | JSON Query DSL | `Criteria` objects | Native Elasticsearch query objects |
| Parameter binding | Placeholders and SpEL | Java variables | Java variables/builders |
| Pagination/sorting | Via repository parameters such as `Pageable` | Via query object | Via query builder |
| Complex queries | Good for static DSL structures with parameters | Good for dynamically assembled conditions | Good when specific Search API/DSL features are needed |
| Aggregations/highlight and search options | Not the primary goal of the annotation | Scope depends on the abstraction | Better suited when advanced request control is needed |

For instance, if the number of conditions varies per request, building the query in a service with `CriteriaQuery` or `NativeQuery` can be easier to maintain than a very long JSON annotation packed with SpEL expressions.

## 12. Common Mistakes When Declaring `@Query`

### Invalid JSON

The annotation contains a JSON string, so brackets, commas, quotes, and escapes must be valid. Malformed JSON can cause Elasticsearch to return a parse error when the query executes.

With regular Java strings, `"` must be escaped as `\"`. With Java text blocks, the JSON is easier to read but must still be valid JSON.

### Adding an Extra `query` Wrapper Inside the Annotation

`@Query` provides the query clause for the `query` section of the search request. Do not wrap it in an outer `query` object unless that structure is genuinely a valid Elasticsearch query clause.

### Using the Wrong Placeholder Index

Placeholders start at `?0`, not `?1`. Whenever adding or reordering parameters, review every placeholder.

### Quoting the Wrong Data Type

Strings typically belong inside JSON quotes; numbers and collections belong in JSON number/array positions respectively. Quoting a collection causes Elasticsearch to receive a string instead of an array.

### Using `term` for a `text` Field

`term` does not analyze the string like `match`. If you need full-text search on a `text` field, use `match`; if you need exact matching, use a `keyword` field and `term`.

### Using the Java Property Name Instead of the Elasticsearch Field Name

If the mapping renames a field with `@Field(name = "product_category")`, the Query DSL must reference the actual field name in the mapping. Check `_mapping` when a query fails to match or returns no results.

### Expecting `@Query` to Support All Search Options

`@Query` primarily declares the query clause. For aggregations, highlighting, or complex search options, use `NativeQuery` or `ElasticsearchOperations`.

### Using `query_string` When Only `match` Is Needed

`query_string` has its own syntax with operators, parentheses, and special characters. For ordinary full-text search, `match` is usually safer and easier to understand. Only use `query_string` when query string syntax is genuinely required.

### Not Checking Mappings and Analyzers

A valid query can still return empty results if a field has the wrong type or an unsuitable analyzer. Check the mapping and use the Analyze API when you need to inspect the tokens produced for a field or query.

## 13. Testing Repository Methods with `@Query`

You should test queries against a real Elasticsearch instance or Testcontainers when verifying Query DSL semantics, mappings, and analyzers. Example testing a category lookup method:

```java
@Test
void findsProductsByExactCategory() {
    repository.save(new Product(
            "p-100", "Mechanical Keyboard", "keyboards", 1299000L, true));
    repository.save(new Product(
            "p-200", "Wireless Mouse", "mice", 499000L, true));

    // Refresh or use a test refresh policy before asserting search results.
    List<Product> result = repository.findByExactCategory("keyboards");

    assertThat(result)
            .extracting(Product::getId)
            .containsExactly("p-100");
}
```

This test snippet illustrates the verification flow; constructors and test setup must match the actual entity. Elasticsearch is near-real-time, so account for refreshing before asserting search results immediately after writes.

Cases that should be included in integration tests:

- Strings containing quotes or special characters to verify binding.
- Numeric placeholders to confirm JSON numbers are not quoted as strings.
- Empty collections and multi-element collections.
- Boundary values for range queries.
- `match` on text fields and `term` on keyword fields.
- Pagination, sorting, and total hit counts.
- Queries returning no results and documents with missing/null fields.
- Field names renamed via mapping annotations.

Mocking the repository can verify that a service calls the right method, but it does not verify that Elasticsearch understands the JSON query or mapping as expected.

## 14. Workflow for Writing a Repository Method with `@Query`

When declaring a new query, you can follow this sequence:

1. Identify the actual fields and mapping types in Elasticsearch.
2. Choose the appropriate Query DSL: `match`, `term`, `terms`, `range`, `bool`, `ids`, `exists`, or another query.
3. Test the JSON query directly in Dev Tools or the REST API with representative data.
4. Put the query clause into `@Query` without an outer `query` wrapper.
5. Replace hardcoded values with `?0`, `?1` placeholders or SpEL as needed.
6. Place strings, numbers, booleans, and collections using their proper JSON types.
7. Choose a return type such as `List`, `Page`, `SearchHits`, or `SearchPage`.
8. Add `Pageable`/`Sort` if pagination or sorting is required.
9. Write integration tests with representative data and ensure index refresh.
10. If the query needs a dynamic structure or advanced search options, consider `CriteriaQuery`, `NativeQuery`, or a custom repository.

## 15. Summary

`@Query` lets you declare Elasticsearch JSON Query DSL directly on repository methods. Spring Data binds parameters using positional placeholders like `?0` and `?1`, supports collections and SpEL, and then executes the query and maps results to the repository return type. The annotation fits queries with a clear, stable structure that you want to keep in the repository interface.

When writing `@Query`, remember that the annotation string is the query clause placed into the `query` section of the search request; do not wrap it in `query` again. Place placeholders with the right JSON types, use `match` for full-text search, and use `term` for exact matches on appropriate fields. `Pageable` and return types add pagination, sorting, and metadata. When queries must be built dynamically or require full Search API features, switching to `CriteriaQuery`, `NativeQuery`, or `ElasticsearchOperations` is a better fit.

## References

- [Spring Data Elasticsearch – Query methods and `@Query`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch – Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch – Query DSL](https://www.elastic.co/docs/reference/query-languages/querydsl)
- [Elasticsearch – Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Elasticsearch – Term query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-term-query)
- [Elasticsearch – Bool query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
