# Combining and, or, not, and Grouped Expressions

Spring Data Elasticsearch's CriteriaQuery lets you compose multiple search conditions using **and**, **or**, **not**, and nested condition groups. This is a step-by-step way to build queries in Java when an application needs dynamic filters, such as finding active products in specific categories, within a price range, and not in a hidden list.

The most important point when combining conditions is preserving the intended logical meaning. A simple chain of `and` or `or` is usually easy to follow, but when an expression mixes both operators, the application must clearly specify which groups should be evaluated together. Spring Data Elasticsearch provides **subCriteria(...)** to create subgroups. If the expression is too complex or requires exact control over Elasticsearch's Bool Query, you can use **NativeQuery** or **StringQuery**.

## 1. From Business Expressions to CriteriaQuery

Suppose a product search page has the following conditions:

- The product must be published.
- The product belongs to the books or games category.
- The price is less than 500.
- The product is not marked as discontinued.

Logical expression:

~~~text
status = "published"
AND (category = "books" OR category = "games")
AND price < 500
AND NOT discontinued
~~~

CriteriaQuery helps express each condition as a **Criteria**, then combine them into a **Query**:

~~~java
Criteria criteria = new Criteria("status").is("published")
        .subCriteria(
                new Criteria().or("category").is("books")
                        .or("category").is("games")
        )
        .and("price").lessThan(500)
        .and("discontinued").not().is(true);

Query query = new CriteriaQuery(criteria);
~~~

This example illustrates how to group conditions. Method signatures and how certain operations are interpreted can vary across release trains; check the Javadoc of the exact Spring Data Elasticsearch version your project uses.

Before writing Criteria, write the query out as a logical expression or condition table. That lets you identify which conditions are mandatory, which are alternatives, and which groups need parentheses.

## 2. Meaning of AND

**and(...)** combines conditions using AND logic. A document satisfies an AND group only when all component conditions are true.

Example:

~~~java
Criteria criteria = new Criteria("status").is("published")
        .and("category").is("books")
        .and("price").lessThan(500);

Query query = new CriteriaQuery(criteria);
~~~

Corresponding expression:

~~~text
status = "published"
AND category = "books"
AND price < 500
~~~

You can use Criteria on the same field to combine multiple bounds. For example, finding products priced from 100 to under 500:

~~~java
Criteria priceCriteria = new Criteria("price")
        .greaterThanEqual(100)
        .lessThan(500);
~~~

Conditions added to the same Criteria are also combined with AND. This style is useful for range queries or when the same field requires multiple constraints.

### 2.1. AND Across Multiple Fields

Each call to `and("fieldName")` creates the next Criteria in the chain:

~~~java
Criteria criteria = Criteria.where("country").is("VN")
        .and("active").is(true)
        .and("age").greaterThanEqual(18);
~~~

Results include only documents where country is VN, active is true, and age is 18 or above.

### 2.2. AND Across Conditions on the Same Field

~~~java
Criteria criteria = Criteria.where("price")
        .greaterThan(100)
        .lessThanEqual(500);
~~~

This condition requires price greater than 100 and less than or equal to 500. This combination corresponds to a price range with differing endpoint inclusivity.

## 3. Meaning of OR

**or(...)** combines conditions using OR logic. A document only needs to satisfy at least one branch in the OR group.

Example:

~~~java
Criteria criteria = new Criteria().or("category").is("books")
        .or("category").is("games");

Query query = new CriteriaQuery(criteria);
~~~

Expression:

~~~text
category = "books"
OR category = "games"
~~~

You can read this query as "products belonging to the books or games category". With only a single condition, OR adds no benefit; it becomes meaningful when there are two or more branches.

### 3.1. OR Across Different Fields

OR can also combine different fields:

~~~java
Criteria criteria = new Criteria().or("sku").is("KB-100")
        .or("barcode").is("893000000001");
~~~

Expression:

~~~text
sku = "KB-100"
OR barcode = "893000000001"
~~~

This covers cases where a user enters a code and the system looks for that code across multiple identifier fields.

### 3.2. OR Is Not a Match Query

OR in Criteria combines multiple query conditions. It is not synonymous with an analyzer matching words using an OR operator inside a single text field.

For example:

~~~java
Criteria criteria = new Criteria().or("category").is("books")
        .or("category").is("games");
~~~

creates two condition branches on the category field. If you need to search text containing one of several words, choose a match query and configure the match operator appropriately. Distinguish logic between Criteria clauses from content analysis logic on a text field.

## 4. Meaning of NOT

NOT negates a condition. In the Criteria API, **not()** sets the negating flag on Criteria. You can use it before the comparison to be negated:

~~~java
Criteria criteria = Criteria.where("status")
        .not()
        .is("deleted");
~~~

The meaning is documents that do not satisfy `status = deleted`.

When excluding a set of values, you can use **notIn(...)**:

~~~java
Criteria criteria = Criteria.where("status")
        .notIn("deleted", "archived");
~~~

Both approaches express negation at the field condition level. For a set of values, `notIn` is usually easier to read.

### 4.1. NOT and Missing Fields

In Elasticsearch, a negated condition is typically represented using `must_not`. Documents without the field can also fail to match the negated condition, and therefore still appear in the results.

For example, a condition excluding deleted status may still return documents lacking a status. If business rules require status to exist and not be deleted, combine an `exists` condition:

~~~java
Criteria criteria = Criteria.where("status").exists()
        .not()
        .is("deleted");
~~~

Because combining negation and entries in Criteria can be hard to read, for `exists` plus negation verify the Query DSL generated in your version. When explicit control is needed, use a Bool Query with `filter` containing `exists` and `must_not` containing the excluded condition.

### 4.2. NOT Over a Set of Values

Elasticsearch Query DSL example:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

This query excludes documents whose status matches deleted or archived. If you also need to exclude documents missing status, add `exists` to `filter`.

### 4.3. NOT Over a Group of Expressions

Negating a complex group requires identifying the exact scope of negation. For example:

~~~text
NOT (category = "books" OR category = "games")
~~~

By De Morgan's law, the equivalent expression is:

~~~text
category != "books"
AND category != "games"
~~~

When negating an entire OR group, do not merely add `not()` to an individual field. Use `must_not` wrapping a bool group or an appropriate nested Criteria structure. This avoids accidentally negating only one branch instead of the entire expression.

## 5. Why Do Conditions Need Grouping?

AND and OR can be combined into complex expressions. When they are, grouping order matters greatly.

Example:

~~~text
status = "published"
AND (category = "books" OR category = "games")
~~~

If parentheses are omitted and combined incorrectly, the query may be interpreted as:

~~~text
(status = "published" AND category = "books")
OR category = "games"
~~~

These two expressions differ. In the first, every document must be published. In the second, any document in games can appear even if its status is not published.

Do not rely on method call order assuming Criteria automatically applies Java or SQL-like precedence. Use **subCriteria(...)** to represent subgroups explicitly.

## 6. Using subCriteria to Create Grouped Expressions

`subCriteria(...)` adds a child Criteria to a parent Criteria. According to Spring Data Elasticsearch documentation, `subCriteria` is combined with the parent Criteria using AND. Inside the child Criteria, you can build its own AND or OR chain.

For example, finding people with last name Miller and first name John or Jack:

~~~java
Criteria criteria = new Criteria("lastName").is("Miller")
        .subCriteria(
                new Criteria().or("firstName").is("John")
                        .or("firstName").is("Jack")
        );

Query query = new CriteriaQuery(criteria);
~~~

Expression:

~~~text
lastName = "Miller"
AND (
    firstName = "John"
    OR firstName = "Jack"
)
~~~

This is a common pattern for a mandatory condition paired with a group of alternatives.

### 6.1. Multiple Subgroups ANDed Together

You can attach multiple `subCriteria` under a parent Criteria. Subgroups are combined with AND:

~~~java
Criteria criteria = new Criteria()
        .subCriteria(
                new Criteria().or("status").is("published")
                        .or("status").is("featured")
        )
        .subCriteria(
                new Criteria().or("category").is("books")
                        .or("category").is("games")
        );
~~~

Expression:

~~~text
(status = "published" OR status = "featured")
AND
(category = "books" OR category = "games")
~~~

Each subgroup independently governs how its inner conditions are joined with OR. The parent Criteria combines the two groups with AND.

### 6.2. An OR Group of AND Groups

For the expression:

~~~text
(status = "published" AND price < 100)
OR
(featured = true AND category = "books")
~~~

You can create an unbound OR Criteria and add each AND group as a `subCriteria`:

~~~java
Criteria criteria = Criteria.or()
        .subCriteria(
                new Criteria("status").is("published")
                        .and("price").lessThan(100)
        )
        .subCriteria(
                new Criteria("featured").is(true)
                        .and("category").is("books")
        );

Query query = new CriteriaQuery(criteria);
~~~

`Criteria.or()` is a factory method creating a Criteria with the OR operator and not bound to a specific field. Subgroups preserve their own AND logic. The `Criteria.and()` factory method can be used similarly when a parent group needs to combine subgroups with AND.

The factory methods `Criteria.and()`, `Criteria.or()`, and `subCriteria(...)` were added in Spring Data Elasticsearch 4.1. If your project uses an older version, check available APIs and pick a compatible representation.

## 7. Translating Grouped Expressions into Bool Queries

CriteriaQuery is translated into an Elasticsearch query. Conceptually:

- AND is represented by bool `must`.
- OR is represented by bool `should`.
- NOT is represented by bool `must_not`.

Example of last name Miller and first name John or Jack:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "lastName": "Miller"
          }
        },
        {
          "bool": {
            "should": [
              {
                "term": {
                  "firstName": "John"
                }
              },
              {
                "term": {
                  "firstName": "Jack"
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ]
    }
  }
}
~~~

Bool Query allows nesting bool queries inside one another, enabling multi-level parenthesized grouping.

### 7.1. must and filter

Elasticsearch has both `must` and `filter` to combine AND conditions:

| Clause | Meaning | Relevance scoring |
|---|---|---|
| must | Condition must match | Contributes to score |
| filter | Condition must match | Does not calculate score; suitable for filter conditions |
| should | Alternative condition or boosts relevance | Can affect score |
| must_not | Condition must not match | Does not calculate score |

CriteriaQuery may place conditions in query context or filter context depending on the Criteria type and how Spring Data constructs the query. Do not assume every AND condition always becomes a filter. If precise control over scoring or filter context is needed, use NativeQuery with an explicit Bool Query.

### 7.2. minimum_should_match

In Elasticsearch, `should` can act as optional. The default value of `minimum_should_match` depends on the bool structure:

- If bool contains only `should`, by default at least one branch must match.
- If bool contains `must` or `filter`, by default `should` branches may only boost score and are not required to match.

Therefore, when writing a Bool Query manually and wanting an OR group to strictly require at least one matching branch, set:

~~~json
{
  "minimum_should_match": 1
}
~~~

When using CriteriaQuery, inspect the actual DSL if an OR expression resides in a group alongside `must`/`filter` conditions. For critical logic, do not let bool query defaults dictate unintended results.

## 8. Complete CriteriaQuery Example for Product Search

Suppose the application needs to filter:

1. Product must have status `published`.
2. Belongs to category `books` or `games`.
3. Price from 100 to under 500.
4. Not marked as `discontinued`.

Abbreviated entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private Boolean discontinued;
}
~~~

Criteria:

~~~java
Criteria categoryGroup = new Criteria()
        .or("category").is("books")
        .or("category").is("games");

Criteria criteria = new Criteria("status").is("published")
        .subCriteria(categoryGroup)
        .and("price").greaterThanEqual(100)
        .and("price").lessThan(500)
        .and("discontinued").not().is(true);

Query query = new CriteriaQuery(criteria);
~~~

Executing the search:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    System.out.println(product.getName());
}
~~~

`categoryGroup` creates an OR group, and `subCriteria` combines this group with the `status` condition. Two price bounds are added to the main Criteria. The `discontinued` condition is negated.

In real usage, ensure `category` and `status` have mappings suited for exact matching. If a field is `text`, term-level operations may not behave as expected. Also decide how to handle documents missing `discontinued`: if the field is absent, a negated condition may still allow the document to appear.

## 9. Using NativeQuery When Expressions Become Too Complex

CriteriaQuery fits common field conditions and logical groups. When queries need deep bool branches, `minimum_should_match`, nested queries, scripts, function scores, aggregations, or specialized Elasticsearch syntax, NativeQuery is usually clearer.

DSL example for the expression:

~~~text
status = "published"
AND (
    (category = "books" AND price < 100)
    OR
    (featured = true AND category = "games")
)
AND NOT discontinued
~~~

Bool Query:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "status": "published"
          }
        },
        {
          "bool": {
            "should": [
              {
                "bool": {
                  "must": [
                    {
                      "term": {
                        "category": "books"
                      }
                    },
                    {
                      "range": {
                        "price": {
                          "lt": 100
                        }
                      }
                    }
                  ]
                }
              },
              {
                "bool": {
                  "must": [
                    {
                      "term": {
                        "featured": true
                      }
                    },
                    {
                      "term": {
                        "category": "games"
                      }
                    }
                  ]
                }
              }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "discontinued": true
          }
        }
      ]
    }
  }
}
~~~

NativeQuery uses Elasticsearch Java Client query types and lets you define bool structures explicitly. NativeQuery builder APIs may vary by client version, but the DSL structure above reflects the logical intent to achieve.

If you already have a JSON query, StringQuery is also an option. Whether using CriteriaQuery, NativeQuery, or StringQuery, inspect the actual request and verify fields match the mapping.

## 10. Combining Criteria with Dynamic Conditions

Search pages often have optional filters. Users might enter category, status, price range, or featured flag. Do not add an empty condition or a null value to the query when the user did not select that filter.

Example building Criteria from input:

~~~java
public Query buildProductQuery(
        String status,
        List<String> categories,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        Boolean featured) {

    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria.and("status").is(status);
    }

    if (categories != null && !categories.isEmpty()) {
        criteria.subCriteria(
                new Criteria().or("category").in(categories)
        );
    }

    if (minPrice != null) {
        criteria.and("price").greaterThanEqual(minPrice);
    }

    if (maxPrice != null) {
        criteria.and("price").lessThanEqual(maxPrice);
    }

    if (featured != null) {
        criteria.and("featured").is(featured);
    }

    return new CriteriaQuery(criteria);
}
~~~

This pattern illustrates adding conditions based on input. Verify how an unbound Criteria handles sub-chains in your project's version; with multiple dynamic groups, you can build individual Criteria and combine them with `and(...)`, `or(...)`, or `subCriteria(...)`.

Rules to follow:

- Do not add a condition when the input was not provided.
- Decide explicitly whether an empty collection skips the filter or returns empty results.
- Keep OR groups separate; avoid chaining directly onto the parent Criteria if doing so alters condition scope.
- Validate input values and data types before creating Criteria.
- Limit the number of OR branches if input comes from users.

## 11. Common Pitfalls When Combining AND, OR, and NOT

### 11.1. Not Grouping OR Before Combining with AND

The desired expression is `A AND (B OR C)`, yet the code builds a flat chain without `subCriteria`. Create a child Criteria containing `B OR C` and attach it to `A` via `subCriteria(...)`.

### 11.2. Assuming Criteria Infers SQL-Like Precedence

Do not rely on method order assuming AND always takes precedence over OR. Express parentheses explicitly with `subCriteria` so query structure stays clear.

### 11.3. Applying NOT to the Wrong Scope

`not()` on a Criteria negates that Criteria's condition. It does not automatically negate the entire parent expression. If you need `NOT (A OR B)`, use a negated bool group or NativeQuery with `must_not` containing a nested bool.

### 11.4. Forgetting Documents Missing a Field

A negated condition can still return documents missing the field. If business logic requires the field to exist, add `exists` to `filter`.

### 11.5. Using OR Without Controlling minimum_should_match

When manually building a Bool Query that has both `must`/`filter` and `should`, explicitly decide whether at least one `should` branch must match. If so, set `minimum_should_match` accordingly.

### 11.6. Using the Wrong Mapping

`is` or `in` conditions on a `text` field may fail to match the full string because an analyzer split it into tokens. Use `keyword` for values needing exact matching and `text` for full-text search.

### 11.7. Trying to Express Overly Complex Queries with Criteria

If deeply nested Criteria makes code hard to read or verify, switch to NativeQuery. The goal is making logical structure easy to verify, not forcing every query through a single API.

## 12. How to Verify Generated Expressions

When results are wrong, check both the initial Criteria and the Query DSL Spring Data sends to Elasticsearch.

Steps:

1. Write the logical expression with parentheses before writing Java code.
2. Create Criteria for each condition group separately.
3. Use `subCriteria(...)` to represent subgroups.
4. Create `CriteriaQuery` from the root Criteria.
5. Enable request logging appropriate for your project's Elasticsearch Java Client and Spring Data Elasticsearch version, or inspect requests in a test environment.
6. Compare `must`, `should`, `must_not`, `filter`, and `minimum_should_match`.
7. Run the query against a small set of documents with clear expected outcomes.

A test dataset should include documents matching all conditions, documents matching only the first OR branch, documents matching only the second OR branch, documents failing an AND condition, documents excluded by NOT, and documents missing fields.

Example test table for `status=published AND (category=books OR category=games) AND NOT discontinued`:

| Document | Status | Category | Discontinued | Expected result |
|---|---|---|---|---|
| A | published | books | false | Selected |
| B | published | games | false | Selected |
| C | draft | books | false | Excluded by status |
| D | published | toys | false | Excluded by category |
| E | published | books | true | Excluded by NOT |
| F | published | games | missing | Must define rule for missing field |

Testing these boundary cases catches grouping bugs much earlier than testing only a single happy-path query.

## 13. Choosing Between CriteriaQuery, NativeQuery, and StringQuery

| Builder approach | Suitable when | Considerations |
|---|---|---|
| CriteriaQuery | Standard field conditions, moderate AND/OR and subgroups | Requires understanding how chains and `subCriteria` translate to bool queries |
| NativeQuery | Need control over DSL, deeply nested bools, scoring, nested queries, or aggregations | More tightly coupled to Elasticsearch Java Client |
| StringQuery | Already have a JSON query and want to send it directly | String JSON is harder to refactor and less type-safe |
| Repository query method | Simple, stable CRUD and basic conditions | Inconvenient for complex dynamic logical groups |

There is no requirement to use CriteriaQuery for every query. Pick the abstraction that makes the expression easiest to read, test, and match against the actual DSL.

## 14. Version Compatibility Notes

The Criteria API has evolved across Spring Data Elasticsearch versions. Key points to verify:

- `subCriteria(...)` and factory methods `Criteria.and()` / `Criteria.or()` were introduced in Spring Data Elasticsearch 4.1.
- `and`, `or`, `not`, `in`, `notIn` methods and overloads can change across release trains.
- How Criteria translates into Query DSL depends on the Spring Data and Elasticsearch client versions.
- NativeQuery uses the Elasticsearch Java Client API, so builders and parameter types must match your actual dependencies.
- Do not mix examples from 4.x, 5.x, and 6.x documentation without checking method signatures.

Official references:

- Spring Data Elasticsearch — Elasticsearch Operations and CriteriaQuery: https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html
- Spring Data Elasticsearch — Criteria API: https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html
- Elasticsearch — Boolean query: https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html

## 15. Conclusion

In CriteriaQuery, `and` combines mandatory conditions, `or` creates alternative choices, and `not` negates conditions. `subCriteria(...)` creates subgroups to represent logical parentheses, enabling expressions like `A AND (B OR C)` or `(A AND B) OR (C AND D)`.

Elasticsearch translates these combinations into a Bool Query with `must`, `should`, and `must_not`. When writing DSL manually, pay attention to `minimum_should_match`, filter context, and handling documents with missing fields. For complex expressions, NativeQuery provides clearer structural control.

Write out the logical expression first, group Criteria with matching parentheses, inspect the generated Query DSL, and test against representative data. Making each condition's scope explicit keeps queries understandable and prevents hard-to-spot AND, OR, NOT bugs.
