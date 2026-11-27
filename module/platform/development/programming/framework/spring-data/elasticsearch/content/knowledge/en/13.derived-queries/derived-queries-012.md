# When Method Names Become Too Long or Unclear

Spring Data Elasticsearch supports query derivation: simply name repository methods by convention, and Spring Data parses the name to create an Elasticsearch query. This is very convenient for simple conditions such as looking up by code, status, price range, or combining a few properties.

However, when method names stretch across many `And`/`Or` conditions, multiple logical branches, optional filters, or requirements involving scoring, nested queries, and aggregations, method names become hard to read and brittle to change. That is the right point to move to `@Query`, `ElasticsearchOperations`, or a custom repository fragment. The goal is letting method names express business intent while placing query structure where its complexity belongs.

## 1. Query derivation suits simple queries

A derived method typically looks like `findBy<Property><Operator>`. Spring Data reads property names and keywords to construct the query.

Example document:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Long)
    private Long priceMinorUnits;

    // Constructors, getters and setters
}
```

With common conditions, method names stay short and clear:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySku(String sku);

    List<ProductDocument> findByStatusAndAvailableTrue(String status);

    List<ProductDocument> findByCategoryIdAndPriceMinorUnitsBetween(
            String categoryId,
            Long minPrice,
            Long maxPrice);
}
```

These methods are easy to read because each expresses one clear purpose with few conditions. Query derivation works well when:

- Conditions are primarily equality, range, existence, Boolean, or other keywords supported by Spring Data.
- There are few conditions and they can be understood directly from the method name.
- AND/OR combinations do not need complex parenthesized grouping.
- The query does not need optional branches, custom scoring, or specialized Query DSL structures.

Long method names themselves do not make Elasticsearch run slower. The real issue is code readability, logical verification, maintainability, and testability. Actual runtime performance depends on the query sent, mappings, data, shards, and Elasticsearch execution.

## 2. Signs that a method name has grown too long

For example, a method might start looking like this:

```java
List<ProductDocument>
findByStatusAndCategoryIdAndAvailableTrueAndPriceMinorUnitsBetweenAndCreatedAtAfterAndBrandIdIn(
        String status,
        String categoryId,
        Long minPrice,
        Long maxPrice,
        Instant createdAfter,
        Collection<String> brandIds);
```

This method name exposes extensive technical detail. Readers must decode each property and operator one by one to figure out its business purpose. If you later add an `Or`, negation, or optional filter, the method becomes even harder to follow.

Signs you should consider another approach:

1. The method name spans multiple lines and remains hard to read even when formatted.
2. The method mixes multiple `And` and `Or` groups, forcing readers to mentally insert parentheses to understand the logic.
3. Some parameters are only applied when non-null, spawning many near-duplicate methods.
4. The query requires `bool`, `nested`, `minimum_should_match`, boosting, or custom sorting.
5. The method name describes Query DSL mechanics rather than business intent.
6. Every minor filter change forces editing a giant method name or adding extra overloads.
7. The query needs aggregations, highlighting, source filtering, or score metadata.

There is no fixed character limit beyond which you must abandon query derivation. Use readability and logical stability as your criteria. A moderately long name expressing one unambiguous filter may be acceptable; a shorter name with confusing OR grouping should still be replaced.

## 3. Long names can hide AND/OR logic bugs

When mixing `And` and `Or`, how the parser groups parts directly affects results. Example:

```java
findByStatusAndCategoryIdOrAvailableTrue(...)
```

This is normally grouped as:

```text
(status = ?0 AND categoryId = ?1)
OR available = true
```

It does not mean:

```text
status = ?0
AND (categoryId = ?1 OR available = true)
```

If business intent is `status = PUBLISHED AND (categoryId = coffee OR categoryId = tea)`, a long method name may fail to express the parenthesized grouping readers expect. Explicit queries reveal the `bool` structure and `minimum_should_match` right at the definition site.

Before converting a method, write out its logical expression with parentheses. This preserves behavior when migrating from a derived query to `@Query` or a custom repository.

## 4. Approach 1: naming methods by business intent

Sometimes you can make a method clearer without moving to a custom query yet. Instead of letting a method merely list every property, name it after its business intent where repository conventions still permit.

Example:

```java
List<ProductDocument> findPublishedProductsByCategoryId(String categoryId);

List<ProductDocument> findAvailableProductsByCategoryId(String categoryId);
```

Descriptive text before `By` can make methods easier to read, though conditions after `By` still have to follow query derivation rules. You cannot write an arbitrary business sentence at the start of a method name and expect Spring Data to infer all remaining logic.

If two methods share a baseline filter, you can extract common logic into a service method or repository helper. However, avoid piling up wrapper layers just to hide an overly complex query; once logic branches out, express it clearly in a custom query.

## 5. Approach 2: using `@Query` for static queries

`@Query` lets you declare Elasticsearch Query DSL directly on a repository method. This fits well when:

- The query structure is relatively fixed.
- Conditions require explicit parenthesized grouping that method names struggle to express.
- You need `bool`, `nested`, `minimum_should_match`, boosting, or Query DSL options.
- The query is concise enough for its JSON to stay readable and maintainable inside the annotation.

Example finding visible products matching one of two statuses while belonging to the requested category:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Query("""
    {
      "bool": {
        "filter": [
          { "term": { "categoryId": "?0" } },
          { "term": { "available": true } },
          {
            "bool": {
              "should": [
                { "term": { "status": "?1" } },
                { "term": { "status": "?2" } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
    """)
    List<ProductDocument> findVisibleProducts(
            String categoryId,
            String firstStatus,
            String secondStatus);
}
```

The query clearly shows the expression:

```text
categoryId = ?0
AND available = true
AND (status = ?1 OR status = ?2)
```

`filter` is used for filtering conditions that do not need relevance scoring. The `should` branch sits inside an inner bool query with `minimum_should_match: 1`, so at least one status must match.

The example uses a Java text block, requiring Java 15 or later. On older Java versions, adjust the string literal syntax while keeping the JSON unchanged. Placeholder syntax and parameter binding must match your project's Spring Data Elasticsearch version; check your version's docs if the query involves special types or structures.

### Advantages and limitations of `@Query`

The advantage is keeping the query structure right next to the method—much clearer than an oversized method name—without creating a separate implementation class. The limitation is that JSON lives in a string, field names must match mappings, and queries become awkward when the number of conditions varies per request.

If a query has many optional filters, do not write a huge JSON annotation full of placeholders or try passing nulls for omitted filters. Use a custom repository so only requested conditions are added.

## 6. Approach 3: using custom repository fragments for dynamic queries

When queries are assembled from optional criteria, a custom repository fragment cleanly separates search construction from the main repository interface.

For example, a user may filter products by one or more criteria:

```java
public record ProductSearchCriteria(
        String categoryId,
        String status,
        Boolean available,
        Long minPrice,
        Long maxPrice,
        String keyword) {
}
```

Define the fragment interface:

```java
import java.util.List;

public interface ProductSearchOperations {
    List<ProductDocument> search(ProductSearchCriteria criteria);
}
```

Main repository extends the fragment:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String>,
                ProductSearchOperations {
}
```

The fragment implementation can use `ElasticsearchOperations` and `NativeQuery` to build Query DSL. The example below illustrates a query with several conditions; builder APIs may vary by Spring Data Elasticsearch/client major version:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Repository;

@Repository
public class ProductSearchOperationsImpl implements ProductSearchOperations {

    private final ElasticsearchOperations operations;

    public ProductSearchOperationsImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<ProductDocument> search(ProductSearchCriteria criteria) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> {
                if (criteria.categoryId() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("categoryId")
                        .value(criteria.categoryId())
                    ));
                }
                if (criteria.status() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("status")
                        .value(criteria.status())
                    ));
                }
                if (criteria.available() != null) {
                    b.filter(f -> f.term(t -> t
                        .field("available")
                        .value(criteria.available())
                    ));
                }
                if (criteria.minPrice() != null || criteria.maxPrice() != null) {
                    b.filter(f -> f.range(r -> {
                        r.field("priceMinorUnits");
                        if (criteria.minPrice() != null) {
                            r.gte(co.elastic.clients.json.JsonData.of(criteria.minPrice()));
                        }
                        if (criteria.maxPrice() != null) {
                            r.lte(co.elastic.clients.json.JsonData.of(criteria.maxPrice()));
                        }
                        return r;
                    }));
                }
                return b;
            }))
            .build();

        SearchHits<ProductDocument> hits =
            operations.search(query, ProductDocument.class);

        return hits.getSearchHits().stream()
            .map(hit -> hit.getContent())
            .toList();
    }
}
```

This snippet illustrates adding a filter only when the corresponding criterion is non-null. Elasticsearch Java Client lambda APIs—especially the `range` builder—may vary across versions; adapt to the dependency resolved in your project. The key design point is that the interface accepts a criteria object, the implementation builds the query, and the service stays decoupled from Query DSL details.

If using Java older than 16, replace `record` with a regular DTO class. If pagination, sorting, highlighting, or scores are needed, choose an appropriate return type (`SearchHits`, `Page`, or a result DTO) instead of converting everything into `List`.

### Why is a criteria object useful?

A `ProductSearchCriteria` object groups optional filters into a named structure. Instead of a method taking eight separate parameters, the service passes one object representing the search request. When new filters are added, you extend the criteria and implementation without spawning dozens of similar methods.

A criteria object is also a convenient place to validate price bounds, cap filter counts, normalize keywords, and apply default pagination. Business-level validation should still live clearly in the appropriate layer.

## 7. Using `CriteriaQuery` for simple dynamic conditions

If a query mainly combines equality/range conditions without needing full Query DSL power, `CriteriaQuery` is another option in Spring Data Elasticsearch.

Illustrative example:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public SearchHits<ProductDocument> searchByCategoryAndStatus(
        String categoryId,
        String status) {

    Criteria criteria = new Criteria("categoryId").is(categoryId)
        .and(new Criteria("status").is(status));

    Query query = new CriteriaQuery(criteria);

    return operations.search(
        query,
        ProductDocument.class,
        IndexCoordinates.of("products")
    );
}
```

`CriteriaQuery` works well when filters are chained conditionally. Verify chaining syntax and supported operators for your Spring Data Elasticsearch version. For deeply nested OR logic, nested queries, or complex scoring, `NativeQuery` usually reflects Query DSL structure more clearly.

## 8. Separating responsibilities between service and repository

Do not place huge JSON Query DSL blocks inside business services. Nor should you stuff all business decisions into an unclearly named repository method.

A maintainable organization:

```text
ProductController
    |
    v
ProductSearchService
    |-- validate criteria and access permissions
    |-- apply defaults for paging/sort
    |
    v
ProductRepository
    |-- basic ElasticsearchRepository CRUD
    |-- ProductSearchOperations fragment
            |-- build NativeQuery / CriteriaQuery
            |-- call ElasticsearchOperations
```

The service owns business semantics: which fields users may filter on, default values, and authorization rules. The repository translates criteria into Elasticsearch queries.

For static queries, `@Query` directly on the repository is usually enough. For dynamic queries, many optional criteria, or reusable search logic, fragments are the right place to organize implementations.

## 9. Choosing the right tool by complexity

| Scenario | Recommended style | Reason |
|---|---|---|
| Lookup by a single ID, SKU, or status | Derived query | Short and easy to read |
| Two or three simple AND conditions | Derived query | Method name still expresses logic clearly |
| A query with fixed OR/AND groups | `@Query` | Parentheses and `minimum_should_match` are visible |
| Fixed Query DSL with nested/boost | `@Query` or custom repository | Expresses Elasticsearch structure directly |
| Filters varying per request | Custom repository + criteria DTO | Adds only present conditions |
| Multiple queries sharing filter logic | Custom repository/service helper | Avoids duplication and centralizes logic |
| Aggregations, highlights, scores, or custom results | `ElasticsearchOperations` | Fine-grained control over queries and result types |

You do not need to convert every derived query into a custom repository. Derived queries remain the best choice for simple, clear, stable methods.

## 10. Refactoring a long method without changing behavior

When refactoring a derived method, do not rewrite JSON by guesswork. Determine the exact old logic first.

Suppose the legacy method is:

```java
List<ProductDocument> findByStatusAndCategoryIdAndAvailableTrueOrFeaturedTrue(
        String status,
        String categoryId);
```

Before changing it, confirm how the parser grouped conditions. Under standard PartTree precedence, the expression has the form:

```text
(status = ?0 AND categoryId = ?1 AND available = true)
OR featured = true
```

If actual business intent was:

```text
status = ?0
AND categoryId = ?1
AND (available = true OR featured = true)
```

then the old method may not have expressed the intended meaning. Refactoring is the moment to confirm desired behavior with product owners and sample datasets. Never silently alter logic just because a new query looks more sensible.

Migration steps:

1. Write down the old method's logical expression with explicit parentheses.
2. Check each field's mapping type and how nulls/missing fields are handled.
3. Build test data covering every AND/OR branch.
4. Write the new query using `@Query`, `CriteriaQuery`, or `NativeQuery`.
5. Compare returned ID sets from the old and new queries on the same data.
6. Verify pagination, sorting, scoring, and boundary arguments.
7. Once results match requirements, migrate callers to the new method and delete the old one if unused.

If the goal is fixing an existing logic bug, document the behavior change in tests and notes rather than forcing the new query to match the old query's buggy output.

## 11. Testing queries and checking mappings

Neither a short method name nor pretty JSON guarantees correct results. Test queries against real mappings and documents.

Mapping:

```http
GET /products/_mapping
```

Verification query:

```http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "categoryId": "coffee" } },
        { "term": { "available": true } },
        {
          "bool": {
            "should": [
              { "term": { "status": "PUBLISHED" } },
              { "term": { "status": "FEATURED" } }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
```

Include representative test cases:

- Documents matching only the first status condition.
- Documents matching only the second status condition.
- Documents matching both branches.
- Documents missing filtered fields.
- Documents with null fields or empty values if source data allows them.
- Documents at boundary values such as min/max prices.
- Documents matching none of the branches.

For paginated queries, verify total counts, first page, last page, and sort order. For scored queries, verify `_score` and result ranking; for filter-only queries, do not expect relevance scores to carry ranking meaning.

## 12. Common pitfalls when method names grow too long

### Adding one condition changes logical grouping

Appending `Or` at the end of a method name can widen results via an independent branch. Write out the parenthesized expression and verify expected behavior before editing the method name.

### Creating many near-identical methods for optional filters

With five optional filters, creating method combinations quickly bloats the repository. Use a criteria DTO and custom repository to build queries from whichever filters are actually present.

### Using `@Query` for overly dynamic queries

Annotations fit static JSON. When many clauses must be added or omitted depending on arguments, a large JSON string full of placeholders is brittle and hard to maintain. Move query construction into an implementation class.

### Dumping all query logic into the service

Services should coordinate use cases, validate criteria, and invoke repositories. Keep Query DSL inside repositories or custom fragments so data access logic has a single home.

### Skipping field mapping checks

`term` on a `text` field may not behave as expected. Check `keyword` mappings, analyzers, and field names before blaming query derivation or Query DSL.

### Ignoring nulls and missing fields

Negated branches or optional filters can treat missing fields differently from SQL. Clarify `exists`, `must_not`, and `null_value` conditions whenever business logic relies on them.

## 13. Decision workflow

When starting to write a repository query, follow these steps:

1. Write the search goal in business terms.
2. List the fields and mapping types involved.
3. Write the parenthesized AND/OR expression before choosing an implementation style.
4. If there are only a few simple conditions, use a derived query.
5. If the query is static but has complex bool/nested structure, use `@Query`.
6. If filters are optional or built per request, use a custom fragment with `ElasticsearchOperations`.
7. Name methods after business intent instead of turning method names into mirrors of Query DSL.
8. Test results with documents matching each branch and missing-data edge cases.
9. Verify paging, sorting, scoring, and mappings when the query uses them.

## 14. Conclusion

Query derivation keeps repositories concise for simple queries. When method names grow too long, contain multiple AND/OR groups, involve optional filters, or require specialized Query DSL, move to `@Query` or a custom repository. `@Query` fits static structures; custom fragments paired with `ElasticsearchOperations` fit dynamic queries and reusable search logic.

When refactoring, write out the parenthesized logical expression, inspect mappings, and compare results on representative data. Keep method names focused on business intent while placing complex queries in clearly structured implementations. This makes repositories easier to read and reduces the risk of breaking search behavior when filters evolve.
