# `Is`, `Not`, `And`, and `Or` Conditions

Spring Data Elasticsearch lets you define queries directly in repository method names. This mechanism is commonly called query derivation: Spring Data parses the method name, identifies properties and keywords such as `Is`, `Not`, `And`, and `Or`, and generates the corresponding Elasticsearch query.

These keywords make it easy to write common conditions without manually constructing JSON Query DSL. To use them properly, you need to understand that `Is` expresses an equality condition, `Not` negates a condition, `And` requires all joined conditions to be true, and `Or` allows any branch to match. For queries with multiple conditions, how Spring Data groups `And` and `Or` directly affects the results.

## 1. Repository method name structure

A derived query method typically follows the form:

```text
findBy<Property><Operator>
```

Or combines multiple properties:

```text
findBy<PropertyA><Operator>And<PropertyB><Operator>
```

Repository example:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    Optional<ProductDocument> findBySkuIs(String sku);

    List<ProductDocument> findByStatusNot(String status);

    List<ProductDocument> findByStatusIsAndCategoryIdIs(
            String status,
            String categoryId);

    List<ProductDocument> findByStatusIsOrCategoryIdIs(
            String status,
            String categoryId);
}
```

Spring Data parses the part after `By` based on the Java property names of the document. For example, `CategoryId` typically maps to property `categoryId`; `Status` maps to `status`. Property names must match the document model, rather than arbitrarily taking JSON field names if they differ from the Java property names.

Document example:

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

    // Constructors, getters and setters
}
```

In the examples below, `status`, `sku`, and `categoryId` are `keyword` fields so equality/inequality conditions have exact value-matching semantics.

## 2. The `Is` condition

`Is` expresses an equality condition against the passed value. It is the explicit form of an equality condition in a method name.

```java
Optional<ProductDocument> findBySkuIs(String sku);

List<ProductDocument> findByStatusIs(String status);
```

Calling the repository:

```java
Optional<ProductDocument> product =
    productRepository.findBySkuIs("COFFEE-001");

List<ProductDocument> published =
    productRepository.findByStatusIs("PUBLISHED");
```

The condition `findByStatusIs("PUBLISHED")` finds documents whose `status` equals `PUBLISHED`. In Elasticsearch, an equality condition on a `keyword` field is typically executed with an exact query such as `term`.

### `Is` can be omitted

For simple equality conditions, Spring Data usually allows writing:

```java
List<ProductDocument> findByStatus(String status);
```

This method has the same equality meaning as `findByStatusIs(status)`. Using `Is` helps make the condition clearer in the method name when combined with other operators.

### `Is` and mapping types

Method names do not replace mapping definitions. If you need exact matching on a code or status, use `keyword`. With `text`, content is split into tokens by an analyzer; an equality query does not necessarily mean comparing the entire raw string as in SQL.

For example, if `name` is `text`, the product name `"Coffee maker"` may be analyzed into multiple tokens. You should not use `findByNameIs("Coffee maker")` expecting it to always act as a full-string comparison. If you need both full-text search and exact-value matching/sorting, declare a multi-field with a `keyword` subfield and query the corresponding property if the Java model exposes the subfield, or use a custom query.

## 3. The `Not` condition

`Not` negates the condition on a property. Example:

```java
List<ProductDocument> findByStatusNot(String status);
```

Invocation:

```java
List<ProductDocument> notDeleted =
    productRepository.findByStatusNot("DELETED");
```

The meaning is to retrieve documents that do not match the condition `status = DELETED`. In terms of Query DSL, negation is typically expressed using `bool.must_not` wrapping the corresponding condition.

Example illustrating query semantics:

```json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "DELETED"
          }
        }
      ]
    }
  }
}
```

This is a logical interpretation for a `keyword` field; the actual JSON emitted by Spring Data may differ in structure depending on version and query type.

### `Not` is not synonymous with `IsNull`

Elasticsearch does not have `NULL` semantics identical to relational databases. A missing field or one with a JSON `null` value is typically not indexed as a matchable value. Therefore, a `must_not` query can also return documents missing that field, in addition to documents whose value differs from the negated one.

For example, `findByStatusNot("DELETED")` should not be assumed by default to mean "status exists and is not DELETED". If the business requirement demands that the field exist, add an appropriate existence condition. Some Spring Data versions support keywords such as `IsNotNull`/`IsNull`; verify your version's query derivation and inspect the actual generated query.

Mappings with the `null_value` setting can also change how Elasticsearch indexes null values. Review your mapping configuration before drawing conclusions about negation results.

### Do not pass `null` to express negation

Do not call `findByStatusNot(null)` expecting it to always mean "status is not null". The behavior of null arguments and null keywords depends on query derivation and mappings. Use explicitly supported existence/non-existence conditions, or write a custom query when null semantics are critical.

## 4. Combining conditions with `And`

`And` requires all joined conditions to be satisfied. Example:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIs(
        String status,
        String categoryId);
```

Invocation:

```java
List<ProductDocument> products =
    productRepository.findByStatusIsAndCategoryIdIs(
        "PUBLISHED",
        "coffee"
    );
```

The result includes only documents where `status = PUBLISHED` and simultaneously `categoryId = coffee`.

You can add more conditions:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIsAndAvailableIsTrue(
        String status,
        String categoryId);
```

The method above requires all three conditions: status equals the passed value, category equals the passed value, and `available` is `true`.

At the Query DSL level, AND logic is typically represented by clauses inside `bool.filter` or `bool.must`. `filter` fits filtering conditions that do not need relevance scoring; `must` is a mandatory clause that may contribute to scoring depending on the query type. The exact query Spring Data generates is determined by the version's implementation.

## 5. Combining conditions with `Or`

`Or` allows results to satisfy at least one condition branch.

```java
List<ProductDocument> findByStatusIsOrCategoryIdIs(
        String status,
        String categoryId);
```

Invocation:

```java
List<ProductDocument> products =
    productRepository.findByStatusIsOrCategoryIdIs(
        "FEATURED",
        "coffee"
    );
```

The results include documents with `status = FEATURED`, or `categoryId = coffee`, or both at the same time.

In Query DSL, OR is typically expressed with `bool.should`. When there are no other mandatory clauses, at least one `should` clause must match. If you manually write a bool query containing both `must`/`filter` and `should`, pay attention to `minimum_should_match`, because Elasticsearch's default behavior can make `should` clauses optional once `must` or `filter` is present.

OR logic example:

```json
{
  "query": {
    "bool": {
      "should": [
        { "term": { "status": "FEATURED" } },
        { "term": { "categoryId": "coffee" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

## 6. Combining `And` and `Or` in the same method name

When a method name contains both `And` and `Or`, condition grouping is critical. Spring Data splits `Or` parts into separate branches; within each branch, `And` conditions are combined together.

Example:

```java
List<ProductDocument> findByStatusIsAndCategoryIdIsOrAvailableIsTrue(
        String status,
        String categoryId);
```

This method is grouped logically as:

```text
(status = ?0 AND categoryId = ?1)
OR available = true
```

It returns products matching both the status and category, or any product with `available = true`. If business intent differs from this grouping, the result set may be broader than expected.

Conversely:

```java
List<ProductDocument> findByStatusIsOrCategoryIdIsAndAvailableIsTrue(
        String status,
        String categoryId);
```

Is grouped into:

```text
status = ?0
OR (categoryId = ?1 AND available = true)
```

Read method names by `Or` groups rather than sequentially like a plain sentence. When logic has multiple branches, a long, hard-to-understand method name is a sign to consider an explicit query.

### What if you want to express `(A OR B) AND C`?

A simple PartTree-style method name cannot always clearly express arbitrary parenthesized nesting. For example, if you need:

```text
(status = PUBLISHED OR status = FEATURED)
AND available = true
```

consider a custom query to express the OR group inside an AND group, rather than trying to craft an overly long and error-prone method name.

## 7. Comprehensive repository example

A repository can define methods by purpose:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    // Equality
    Optional<ProductDocument> findBySkuIs(String sku);

    // Negation
    List<ProductDocument> findByStatusNot(String status);

    // AND
    List<ProductDocument> findByStatusIsAndCategoryIdIs(
            String status,
            String categoryId);

    // OR
    List<ProductDocument> findByStatusIsOrCategoryIdIs(
            String status,
            String categoryId);

    // One AND group, then OR another condition
    List<ProductDocument> findByStatusIsAndCategoryIdIsOrAvailableIsTrue(
            String status,
            String categoryId);
}
```

Example method calls:

```java
Optional<ProductDocument> bySku =
    productRepository.findBySkuIs("COFFEE-001");

List<ProductDocument> notArchived =
    productRepository.findByStatusNot("ARCHIVED");

List<ProductDocument> publishedCoffee =
    productRepository.findByStatusIsAndCategoryIdIs(
        "PUBLISHED",
        "coffee"
    );

List<ProductDocument> featuredOrCoffee =
    productRepository.findByStatusIsOrCategoryIdIs(
        "FEATURED",
        "coffee"
    );
```

## 8. Using `@Query` when explicit logical grouping is needed

When conditions involve multiple AND/OR groups, nested queries, ranges, boosting, or specific Query DSL requirements, you can define an explicit query with `@Query`.

Example requiring `(status = PUBLISHED OR status = FEATURED) AND available = true`:

```java
import org.springframework.data.elasticsearch.annotations.Query;

@Query("""
{
  "bool": {
    "filter": [
      { "term": { "available": true } },
      {
        "bool": {
          "should": [
            { "term": { "status": "?0" } },
            { "term": { "status": "?1" } }
          ],
          "minimum_should_match": 1
        }
      }
    ]
  }
}
""")
List<ProductDocument> findVisibleByStatuses(
        String firstStatus,
        String secondStatus);
```

Java text blocks require Java 15 or later. If the project uses an older Java version, write the JSON string using standard string syntax. Parameter placeholders `?0`, `?1` and parameter binding syntax must follow your Spring Data Elasticsearch version; if the Java version does not support text blocks in source, change only the Java string syntax, not the Query DSL content.

`@Query` lets you see condition grouping directly, at the cost of managing JSON field names, data types, and query structure yourself. Validate the JSON against the real mapping and test the query before using it.

## 9. Data type and mapping considerations

### Equality and `keyword`

`Is` and `Not` conditions are commonly used for statuses, codes, types, or categories. These fields should have `keyword` mapping for exact matching.

```java
@Field(type = FieldType.Keyword)
private String status;

@Field(type = FieldType.Keyword)
private String categoryId;
```

If the field is `text`, the analyzer may transform the string into multiple tokens. An equality query on that field may not carry the full-string comparison meaning expected by users.

### Boolean

For Boolean fields, you can use keywords such as `True` or `False` in the method name:

```java
List<ProductDocument> findByAvailableIsTrue();

List<ProductDocument> findByAvailableIsFalse();
```

These are extended examples of writing simple conditions; verify the set of keywords supported by your Spring Data Elasticsearch version.

### Nested fields

For nested properties, the method name must represent a property path that Spring Data can resolve. If the model has multiple similarly named properties, use supported path separation or an explicit query to avoid the parser selecting the wrong property.

### Null and missing fields

Elasticsearch typically does not index null values as normal term values. Therefore, `Not` can include documents missing the field. If the business logic must distinguish "field absent", "field is null", and "field has a value", consider `null_value` mapping, `exists` queries, and how data is serialized.

## 10. Reading and verifying generated queries

Method names only express intent. When results differ from expectations, inspect the actual mapping and query.

You can check the mapping:

```http
GET /products/_mapping
```

Test with sample data:

```http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
```

In development, enable appropriate logging for the Spring Data Elasticsearch package or HTTP client to observe outgoing requests. Logger names and verbosity levels may vary by version. Do not enable logging of payloads/headers containing sensitive data in production.

Create a set of sample documents covering combinations of statuses, categories, Booleans, and missing fields to verify:

- `Is` returns only the expected matching values.
- Whether `Not` includes documents missing the field.
- `And` returns only documents satisfying all conditions.
- `Or` returns documents satisfying at least one branch.
- Method names combining `And` and `Or` are grouped as required by business logic.

## 11. Common errors

### Unresolved property name

The segment after `By` must point to a property on the document class. If you write `findByCategory(...)` when the class only has `categoryId`, Spring Data may throw a query creation error at startup.

### Using `Is` on a `text` field for full-string comparison

A `text` field is analyzed into tokens. Use `keyword` or a keyword subfield for exact equality; use full-text queries for content search.

### `Not` returning documents missing the field

A negation condition in Elasticsearch can match documents with no indexed value for the field. If the field must exist, combine it with an appropriate exists/null condition or write explicit Query DSL.

### Combining `And` and `Or` with unintended meaning

A method such as `findByAAndBOrC` is typically grouped as `(A AND B) OR C`, not `A AND (B OR C)`. Rewrite the method name according to grouping or use `@Query` to express parentheses explicitly.

### `Or` in a custom bool query not required to match

If you write a custom bool query containing both `filter`/`must` and `should`, check `minimum_should_match`. Without it, `should` clauses may act merely as score boosters rather than mandatory conditions.

### Using `null` like a regular value

A null or missing field is not the same as a valued term. Do not pass null into `Not` as a substitute for existence checking; use a query matching the required semantics.

## 12. Operator selection workflow

When creating a repository method, you can decide in sequence:

1. Identify the property in the Java document and the field's mapping type.
2. If an exact value match is needed, use `Is` (or the shortened equality form) on an appropriate field such as `keyword`.
3. If values must be excluded, use `Not` and define clearly how missing/null fields should be handled.
4. If all conditions must hold, join parts with `And`.
5. If any one branch being true is sufficient, use `Or`.
6. When both `And` and `Or` appear, write out the logical expression with parentheses first before converting it to a method name.
7. If parenthesized grouping cannot be expressed clearly in a method name, use `@Query` or a custom repository.
8. Verify the mapping and results using representative data, especially for `text` fields, nulls, and missing fields.

## 13. Conclusion

In Spring Data Elasticsearch query derivation, `Is` expresses equality, `Not` negates a condition, `And` combines conditions that must all hold simultaneously, and `Or` creates branches where only one needs to match. These operators are written into repository method names and translated by Spring Data into Elasticsearch queries.

Use `keyword` for exact equality/inequality conditions, keep in mind that `Not` can match documents missing the field, and pay attention to how branches are grouped when mixing `And` with `Or`. For logic with complex parentheses or specific Query DSL requirements, `@Query` or a custom repository is usually clearer than a long method name. Always verify against the mapping and test results on your project's actual Spring Data Elasticsearch version.
