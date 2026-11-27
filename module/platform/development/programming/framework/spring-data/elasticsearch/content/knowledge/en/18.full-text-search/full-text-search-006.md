# `minimum_should_match` and Mandatory Conditions When Combining `bool`

Elasticsearch's Bool Query lets you combine multiple search conditions using four clause groups: `must`, `filter`, `should`, and `must_not`. `must` and `filter` express mandatory conditions; `must_not` excludes documents from results; `should` expresses alternative choices or relevance-boosting conditions. When a query contains `should` together with `must` or `filter`, the `should` clauses can become optional by default. This is a common reason why a query returns documents that satisfy only the filter conditions without matching any content in the `should` branches.

The `minimum_should_match` property lets you specify the minimum number of `should` clauses that must match. Combining it properly with `must` and `filter` clearly expresses requirements such as: the product must belong to the chosen category, must be active, and must match at least two of four search terms.

This lesson explains the semantics of each Bool clause, the default rules of `should`, the value forms of `minimum_should_match`, its scope inside nested bools, and how it differs from the identically named parameter in the `match` query.

## 1. Bool Query Structure

A Bool Query can contain four clause groups:

```json
{
  "bool": {
    "must": [],
    "filter": [],
    "should": [],
    "must_not": [],
    "minimum_should_match": 1
  }
}
```

| Clause | Condition | Effect on `_score` |
|---|---|---|
| `must` | Every clause in the group must match | Computes relevance score |
| `filter` | Every clause in the group must match | Does not compute relevance score |
| `should` | Number of matching clauses must meet `minimum_should_match` | Matching clauses can contribute score |
| `must_not` | Documents matching a clause are excluded from results | Does not compute relevance score |

Clauses coexisting within a bool are combined logically as:

- Every `must` must match.
- Every `filter` must match.
- No `must_not` clause may match.
- The number of matching `should` clauses must satisfy `minimum_should_match` if a threshold applies.

You can visualize this as:

```text
Document
   |
   +--> All MUST match? ------------ No --> Exclude
   |
   +--> All FILTER match? ---------- No --> Exclude
   |
   +--> Any MUST_NOT match? -------- Yes -> Exclude
   |
   +--> Matching SHOULD >= threshold? No -> Exclude
   |
   +--> Keep result and compute relevance from scoring clauses
```

`minimum_should_match` only governs the `should` group of the Bool Query on which it is declared. It does not change the required count of `must`, `filter`, or `must_not` conditions.

## 2. Distinguishing Mandatory and Optional Conditions

Suppose we need to find products satisfying:

- Product must have `active = true`.
- Product must belong to category `keyboards`.
- Product name should match `mechanical` or `gaming`.

The first two conditions are mandatory, and the last two terms are alternatives. The query can be written:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

A document must pass both filters and match at least one of the two `should` clauses. If you omit `minimum_should_match`, the default for a bool with `filter` is `0`; then a document only needs the right category and active status, even if its name contains neither `mechanical` nor `gaming`.

### 2.1. `must` and `filter` are both mandatory, differing in scoring

Both `must` and `filter` require clauses to match. The main difference is scoring:

- Use `must` for full-text search conditions that should influence ranking, such as whether a name or description matches keywords.
- Use `filter` for structural or exact conditions such as status, category, tenant, price range, or dates.

Example combining full-text search with filters:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "mechanical keyboard"
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": { "lte": 3000000 } } }
      ]
    }
  }
}
```

Here, documents must match the name content and all three filter conditions. `_score` primarily reflects how well `match` fits; the filters add no score.

### 2.2. `must_not` is an exclusion condition

Example excluding discontinued products:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "must_not": [
        { "term": { "status": "DISCONTINUED" } }
      ]
    }
  }
}
```

Documents must have `active = true` and must not have `status = DISCONTINUED`. `must_not` is not a positive condition to match; it removes documents matching the inner clauses.

## 3. Default Rules for `should`

This is the most important rule to remember when combining Bool Queries:

- If a bool has at least one `should` and **no** `must` or `filter`, at least one `should` must match by default.
- If a bool has `must` or `filter`, the default `minimum_should_match` is `0`. The `should` clauses are then optional.

`must_not` does not alter this default rule.

### 3.1. Only `should`: at least one must match by default

```json
{
  "query": {
    "bool": {
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } },
        { "match": { "description": "quiet typing" } }
      ]
    }
  }
}
```

There is no `must` or `filter`, so Elasticsearch requires at least one of the three `should` clauses to match by default. Logically, this is an OR condition group.

Even so, declare `minimum_should_match` explicitly if the branch requirement is an important part of business rules. Explicit configuration helps readers understand the condition immediately and prevents unintended behavior shifts when the query is extended.

### 3.2. With `must` or `filter`: `should` is optional by default

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } }
      ]
    }
  }
}
```

Because the bool has `filter`, the default threshold is `0`. An active product can be returned even if its name matches neither word. If it does match `mechanical` or `gaming`, those clauses can still raise `_score` and move the product higher in results.

This is the right behavior when `should` is used solely to boost results. If business rules say the product must match at least one phrase, add:

```json
"minimum_should_match": 1
```

### 3.3. Default behavior table

| `must` | `filter` | `should` | Default `should` threshold |
|---|---|---|---:|
| No | No | Yes | 1 |
| Yes | No | Yes | 0 |
| No | Yes | Yes | 0 |
| Yes | Yes | Yes | 0 |
| Any | Any | No | Not applicable |

If there are no `should` clauses, `minimum_should_match` has no practical effect. If `must` or `filter` is present and no threshold is set, `should` clauses only affect scoring when matched and do not decide whether documents are kept.

## 4. What Is `minimum_should_match`?

`minimum_should_match` specifies the minimum number of clauses in the `should` array that must match for the Bool Query to be considered a match.

Example with four `should` clauses:

```json
{
  "bool": {
    "should": [
      { "match": { "name": "mechanical" } },
      { "match": { "name": "gaming" } },
      { "match": { "description": "quiet" } },
      { "match": { "description": "wireless" } }
    ],
    "minimum_should_match": 2
  }
}
```

A document must match at least two of the four clauses. A clause may be a `match`, `term`, `range`, or nested bool; at the current bool level, each direct element in the `should` array counts as one clause.

`minimum_should_match` does not count words in a sentence and does not count documents. It counts how many direct `should` clauses of that Bool Query match.

## 5. Value Forms of `minimum_should_match`

Elasticsearch supports several ways to express the threshold. You can use integers, negative integers, percentages, negative percentages, or conditional expressions.

### 5.1. Positive integer: minimum number of clauses that must match

```json
"minimum_should_match": 2
```

Requires at least two `should` clauses to match, regardless of how many clauses are in the list. If there are five clauses, only two are required.

### 5.2. Negative integer: number of clauses allowed not to match

```json
"minimum_should_match": -1
```

`-1` means one clause may be missed; all remaining clauses must match. With five clauses, at least four must match.

With `-2`, two clauses may be missed. With five clauses, at least three must match.

### 5.3. Positive percentage

```json
"minimum_should_match": "75%"
```

A positive percentage calculates the minimum number of clauses that must match. The percentage result is rounded down (floored).

For example, with five clauses:

```text
floor(5 * 75%) = floor(3.75) = 3
```

Hence `75%` requires at least three out of five clauses to match.

### 5.4. Negative percentage

```json
"minimum_should_match": "-25%"
```

A negative percentage calculates how many clauses may be missed, then subtracts that number from the total clause count.

With five clauses:

```text
Allowed misses = floor(5 * 25%) = 1
Minimum required = 5 - 1 = 4
```

Thus `-25%` requires at least four out of five clauses to match.

### 5.5. Why do `75%` and `-25%` differ?

With four clauses, both expressions require three clauses to match. With five clauses, however, the results differ:

| `should` clause count | `75%` required matches | `-25%` required matches |
|---:|---:|---:|
| 4 | 3 | 3 |
| 5 | 3 | 4 |
| 8 | 6 | 6 |
| 9 | 6 | 7 |

A positive percentage computes the required count; a negative percentage computes the allowed misses. The two representations only happen to yield the same result for certain clause counts.

### 5.6. Conditional expressions

When the number of clauses varies widely, you can use threshold-based conditions:

```json
"minimum_should_match": "2<-25% 9<-3"
```

The expression reads as:

- If there are up to two clauses, require all of them to match.
- If there are three to nine clauses, allow missing 25% of clauses.
- If there are more than nine clauses, allow missing three clauses.

Conditions are written in ascending order of clause count, separated by spaces. Each condition has the form `<clause count><rule applied when exceeded`.

Another example:

```json
"minimum_should_match": "3<90%"
```

If there are three clauses or fewer, require all to match. If there are more than three clauses, require 90% of clauses to match (rounded down per the positive percentage rule).

Conditional expressions establish stricter thresholds for small lists and more flexible thresholds for large lists. Test values on both sides of each threshold to confirm desired behavior.

## 6. Example Combining Mandatory Conditions and `minimum_should_match`

Suppose an e-commerce site needs to find products meeting these requirements:

1. Product must be active.
2. Product must belong to the selected category.
3. Price must not exceed budget.
4. Content must match at least two of four related phrases.
5. Results matching more phrases can receive higher relevance scores.

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "keyboards" } },
        { "range": { "priceInCents": { "lte": 3000000 } } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "name": "gaming" } },
        { "match": { "description": "hot swap" } },
        { "match": { "description": "wireless" } }
      ],
      "minimum_should_match": 2
    }
  }
}
```

A document is returned only if it satisfies all three filters and at least two of the four `should` clauses. Matching `should` clauses still contribute relevance scores, so a product matching three or four phrases can rank higher than one matching only two, depending on individual query scores.

### 6.1. When only one mandatory full-text condition is needed

If every product must match a name query, while additional secondary signals may boost score:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "mechanical keyboard" } }
      ],
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "description": "gaming" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Here `minimum_should_match: 0` explicitly states that the two secondary signals are only for boosting score, not mandatory conditions. Omitting this property gives the same default of 0 because the bool has `must` and `filter`.

### 6.2. When at least one of the options is required

If a product must match at least one branch in a group of alternative keywords:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "keyboard" } },
        { "match": { "name": "keypad" } },
        { "match": { "description": "typing device" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Documents must be active and match at least one of the three branches. This is a common combination of mandatory conditions and an OR keyword group.

## 7. `minimum_should_match` in Nested Bool Queries

Bool Queries can be nested. Each bool has its own `should` group and its own threshold. `minimum_should_match` applies only to the direct `should` clauses of the bool where it is declared.

For example: the product must be active; and it must satisfy at least one of two groups:

- Name matches `mechanical` or `gaming`.
- Description matches `wireless` or `quiet`.

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "must": [
        {
          "bool": {
            "should": [
              { "match": { "name": "mechanical" } },
              { "match": { "name": "gaming" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "should": [
        {
          "bool": {
            "should": [
              { "match": { "description": "wireless" } },
              { "match": { "description": "quiet" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "minimum_should_match": 0
    }
  }
}
```

The bool inside `must` requires name to match at least one of the two words. The bool inside `should` requires description to match at least one of the two words, while the entire description group is optional in the outer bool because the outer `minimum_should_match` is 0. If matched, the description group can boost score.

In the outer bool, the nested bool inside the `should` array counts as one clause. Elasticsearch does not separately count the two `match` queries inside the nested bool when evaluating the outer bool's threshold.

### 7.1. Placing the threshold at the wrong level changes logic

The following example requires at least two direct branches in the outer bool to match:

```json
{
  "bool": {
    "should": [
      { "bool": { "should": [{ "match": { "name": "keyboard" } }] } },
      { "bool": { "should": [{ "match": { "description": "wireless" } }] } },
      { "term": { "featured": true } }
    ],
    "minimum_should_match": 2
  }
}
```

The three direct branches here are two nested bools and one `term`. `minimum_should_match: 2` counts those three branches, not the `match` queries inside the two nested bools.

When nested queries get complex, indent cleanly and place `minimum_should_match` right beside the `should` array it governs. This helps avoid confusing a parent bool's threshold with a child bool's threshold.

## 8. Distinguishing `minimum_should_match` on `bool` vs `match`

Elasticsearch also has a `minimum_should_match` property inside the `match` query. The name is the same, but its scope differs.

### 8.1. `minimum_should_match` on bool

It counts direct query clauses in the Bool Query's `should` array:

```json
{
  "bool": {
    "should": [
      { "match": { "name": "mechanical" } },
      { "match": { "description": "quiet" } },
      { "term": { "category": "keyboards" } }
    ],
    "minimum_should_match": 2
  }
}
```

A document must match at least two of the three clauses.

### 8.2. `minimum_should_match` on match query

A `match` query analyzes a string into multiple terms. The property of the same name inside a `match` query controls the minimum number of analyzed terms that must match:

```json
{
  "match": {
    "description": {
      "query": "quiet mechanical keyboard",
      "minimum_should_match": "2"
    }
  }
}
```

If the analyzer produces three terms, the query requires at least two terms to match per `match` query semantics. This is not the count of `should` branches in a Bool Query.

### 8.3. Both levels can be used in one query

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        {
          "match": {
            "name": {
              "query": "mechanical gaming keyboard",
              "minimum_should_match": "2"
            }
          }
        },
        { "match": { "description": "wireless" } },
        { "term": { "featured": true } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

In this example:

- `minimum_should_match: 2` inside `match` requires at least two terms from the name query string to match.
- `minimum_should_match: 1` outside requires at least one of the three bool-level `should` clauses to match.

The two thresholds operate independently at two different query levels.

## 9. Using `@Query` on a Spring Data Elasticsearch Repository

You can declare a Bool Query directly using the `@Query` annotation on a repository method:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              { "term": { "active": true } },
              { "term": { "category": "?0" } }
            ],
            "should": [
              { "match": { "name": "?1" } },
              { "match": { "description": "?1" } },
              { "term": { "featured": true } }
            ],
            "minimum_should_match": 2
          }
        }
        """)
    List<Product> searchActiveProducts(
            String category,
            String text);
}
```

`?0` is category, `?1` is the search string. Both filters are always mandatory. Out of the three `should` clauses, the document must match at least two. The JSON query in `@Query` is the query clause placed by Spring Data into the `query` section of the search request; do not add another `query` wrapper inside the annotation.

If the repository method also accepts `Pageable`, Spring Data can apply pagination and sorting according to the query method contract:

```java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "active": true } },
          { "term": { "category": "?0" } }
        ],
        "should": [
          { "match": { "name": "?1" } },
          { "match": { "description": "?1" } }
        ],
        "minimum_should_match": 1
      }
    }
    """)
Page<Product> search(
        String category,
        String text,
        Pageable pageable);
```

Placeholders must match JSON types. Category and text are strings so they are quoted; the threshold is a number so it is unquoted. Verify the bound query in an integration test when using collections, SpEL, or complex parameters.

## 10. Using `CriteriaQuery` or `NativeQuery` When Dynamic Queries Are Needed

`@Query` fits queries with relatively fixed structure. If the number of `should` conditions or the threshold varies per request, building the query in Java can be easier to maintain.

`CriteriaQuery` provides a fluent abstraction for several common conditions. For advanced Bool Query structures or Query DSL options needing precise control, `NativeQuery` lets you use the Elasticsearch Java API Client's query builder.

Conceptual example using a native bool query:

```java
// Build a co.elastic.clients.elasticsearch._types.query_dsl.Query
// with a BoolQuery containing filter, should and minimumShouldMatch.
// Pass it to NativeQuery.builder().withQuery(query).build().
// Execute the result through ElasticsearchOperations.search(...).
```

Builder names and method signatures of the Elasticsearch Java API Client depend on the client version used by your Spring Data release train. When implementing, consult the Javadoc of your actual dependency; do not add a different major version of the client just to copy an example.

## 11. Calculating Thresholds in Practical Scenarios

Suppose a query has eight `should` clauses. The table below shows the minimum number of clauses that must match for several configurations:

| Value | Minimum clauses to match | Clauses allowed not to match |
|---|---:|---:|
| `1` | 1 | 7 |
| `3` | 3 | 5 |
| `-1` | 7 | 1 |
| `-2` | 6 | 2 |
| `75%` | 6 | 2 |
| `-25%` | 6 | 2 |
| `100%` | 8 | 0 |

With eight clauses, `75%` and `-25%` both yield six. With five clauses, the two expressions differ as shown earlier.

### 11.1. When to choose an integer?

Use an integer when the business requirement states an explicit count, such as "must match at least two branches in the list."

### 11.2. When to choose a percentage?

Use a percentage when the clause count varies while you want to keep the match ratio relatively stable. For example, queries generating multiple branches from a list of synonyms or search fields.

### 11.3. When to choose a negative value?

Use a negative number when the requirement is naturally phrased in terms of allowed misses, such as "must match all except at most one branch."

### 11.4. When to use a conditional expression?

Use a conditional expression when small lists should be stricter than large lists. For example, with up to two options all must match, whereas with many options a fixed percentage or count may be missed.

Do not pick a value merely because it yields more or fewer results in a trial query. Define the business meaning clearly, then test with documents matching 0, 1, exactly the threshold, and above the threshold.

## 12. Common Mistakes

### Forgetting `minimum_should_match` when bool has `filter`

This is the most common mistake. Authors think `should` acts as a mandatory OR selection, yet because bool has `filter`, the default threshold becomes 0. Documents only satisfying the filter are still returned. Set `minimum_should_match: 1` if at least one `should` branch is required.

### Using `must` instead of `should` when OR is intended

If you place multiple branches in `must`, all of them must match. To require one of several options, place them in `should` and specify an appropriate threshold.

### Using `minimum_should_match` as a substitute for a mandatory condition

If a condition must always hold, put it in `must` or `filter`. Do not place a mandatory condition in `should` hoping the threshold will somehow guarantee it, especially when the `should` group contains other options.

### Thinking `must_not` makes `should` mandatory

`must_not` only excludes documents matching its clauses. It does not change the default rule for `should`; if bool has no `must` or `filter`, the default remains at least one `should`.

### Putting `minimum_should_match` on the parent bool instead of the child bool

The threshold only counts direct `should` clauses in the bool containing it. With nested bools, place the threshold at the exact level you want to control.

### Confusing clause count with word count

Bool `minimum_should_match` counts clauses in the `should` array. If one clause is a `match` containing three words, it still counts as one clause at the bool level. To control the number of terms inside `match`, use `minimum_should_match` inside the `match` query.

### Confusing positive percentages with negative percentages

`75%` computes the number of clauses that must match; `-25%` computes the number of clauses allowed to miss. With five clauses, the results are three and four respectively. Calculate against the actual clause count.

### Putting every condition in `must`

Exact conditions like category, status, and price ranges generally belong in `filter` so they do not affect score. Use `must` for full-text or conditions that should contribute to relevance.

### `should` only boosts while the author thinks it is mandatory

When `must`/`filter` is present and threshold is 0, `should` can still boost score. A document not matching `should` is still returned. Clearly distinguish filter conditions from ranking signals.

## 13. Testing Bool Queries

To verify logic, create data covering representative cases:

| Document | Active | Category | Matching `should` branches | Result when threshold = 2 |
|---|---:|---|---:|---|
| A | true | keyboards | 0 | No match |
| B | true | keyboards | 1 | No match |
| C | true | keyboards | 2 | Match |
| D | true | keyboards | 3 | Match |
| E | false | keyboards | 4 | No match due to filter |
| F | true | mice | 4 | No match due to filter |

With this dataset, the query must return C and D. E and F must not be returned even though they match all `should` clauses, because filter is mandatory. A and B do not meet the `should` branch count.

### 13.1. Checking the default when threshold is omitted

Run the same query with `minimum_should_match` removed:

- Because bool has `filter`, A, B, C, and D can all be returned since they satisfy the filter.
- E and F are still excluded for failing the filter.
- Documents matching more `should` clauses may rank higher.

This test highlights the difference between the default threshold of 0 and an explicit threshold of 2.

### 13.2. Using the Explain API to understand relevance scores

If documents are returned but in an unexpected order, inspect `_score` and run the Explain API on a specific document:

```http
GET products/_explain/p-100
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } }
      ],
      "should": [
        { "match": { "name": "mechanical" } },
        { "match": { "description": "wireless" } }
      ],
      "minimum_should_match": 1
    }
  }
}
```

Explain reveals why a document matched or did not match and what components contributed to its score. It is helpful for separating condition logic bugs from ranking issues.

## 14. Bool Query Design Workflow

When building a query with multiple conditions, follow this sequence:

1. List conditions that must always hold and place them in `must` or `filter`.
2. Choose `must` for content that should contribute to relevance score; choose `filter` for structural conditions needing no scoring.
3. List alternative choices or ranking signals and place them in `should`.
4. Decide whether the `should` group is mandatory or only for boosting.
5. If mandatory, set `minimum_should_match` explicitly; if only boosting, keep threshold 0 or rely on the default when bool has `must`/`filter`.
6. Choose integer, percentage, negative value, or conditional expression according to business rules.
7. With nested bools, place thresholds at the exact level holding the clauses to count.
8. Check direct clause counts separately from term counts inside `match` queries.
9. Test data matching below threshold, at threshold, and above threshold.
10. Use the Explain API when investigating why documents were retained or ranked a certain way.

## 15. Summary

In a Bool Query, `must` and `filter` are mandatory conditions; `must` participates in scoring while `filter` does not. `must_not` excludes documents matching its conditions. `should` can express OR choices or score-boosting signals. If bool has `must` or `filter`, `should` is optional by default (`minimum_should_match = 0`); if only `should` is present without `must`/`filter`, at least one clause must match by default.

`minimum_should_match` controls the minimum number of `should` clauses that must match. It accepts integers, negative integers, percentages, negative percentages, and conditional expressions. This value counts only direct clauses of the bool where it is declared; in nested bools, each level has its own threshold. Distinguish it from `minimum_should_match` inside a `match` query, where the threshold applies to terms analyzed from text.

When designing full-text queries, put mandatory business conditions in `must`/`filter`, place search alternatives in `should`, and choose an explicit threshold. This separation ensures correct filtering logic while making full use of Elasticsearch relevance scoring.

## References

- [Elasticsearch – Boolean query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch – `minimum_should_match` parameter](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-minimum-should-match)
- [Elasticsearch – Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Spring Data Elasticsearch – Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
