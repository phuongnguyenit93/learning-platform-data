# Bool Query with must, should, must_not, and filter

A Bool query is how Elasticsearch combines multiple search conditions into a single query. It lets you require certain conditions to match, let others act purely to boost relevance scores, exclude unacceptable documents, and apply filters without relevance scoring.

Spring Data Elasticsearch supports Bool Queries through several query-building mechanisms, most commonly NativeQuery with the Elasticsearch Java Client or JSON DSL declared with `@Query` on repositories. CriteriaQuery can also express many standard conditions, but when you need explicit control over must, should, must_not, filter, and minimum_should_match, NativeQuery usually conveys intent more accurately.

Four clauses to distinguish:

- **must:** the document must match; the condition participates in relevance scoring.
- **filter:** the document must match; the condition does not participate in relevance scoring.
- **should:** optional or score-boosting condition; whether matching is mandatory depends on minimum_should_match and the bool structure.
- **must_not:** the document must not match; used to exclude results and does not compute relevance score.

Understanding the exact semantics of each clause is essential. A query can execute successfully yet return wrong results if `should` is used with unexpected defaults or if a filter condition is placed in the wrong group.

## 1. What Is a Bool Query?

A Bool query combines subqueries using Boolean logic. Each subquery can be a term, match, range, exists, nested, or another bool query.

For example, a product search page needs:

- Product name must relate to the phrase entered by the user.
- Product must belong to the electronics category.
- Price must be from 100 to under 500.
- Product must not have status discontinued.
- Products from a preferred brand should rank higher.

Business expression:

~~~text
MATCH name
AND category = electronics
AND 100 <= price < 500
AND NOT status = discontinued
OPTIONAL boost when brand = preferred
~~~

A Bool query organizes these conditions into meaningful groups:

~~~text
bool
  ├── must
  │     └── match name
  ├── filter
  │     ├── term category
  │     └── range price
  ├── must_not
  │     └── term status = discontinued
  └── should
        └── term brand = preferred
~~~

Each clause can hold multiple subqueries. Elasticsearch combines them according to the semantics of each clause, rather than merely chaining conditions in order of appearance.

## 2. Role of must

must holds conditions that are required to match. If a bool query has multiple must conditions, a document must match all of them.

Example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        },
        {
          "match": {
            "description": "office equipment"
          }
        }
      ]
    }
  }
}
~~~

A document must match both the name query and the description query. Queries in must also participate in score calculation, so match quality can affect result ordering.

### 2.1. When to use must?

Use must when a condition is both mandatory and relevant to scoring. For example:

- User-entered keywords must appear in the title or body.
- Product name must relate to the search phrase.
- Article body must match a full-text query.

With match queries, scoring ranks more relevant documents higher. This is why full-text conditions are typically placed in must.

### 2.2. Multiple must conditions mean AND

Example:

~~~json
{
  "bool": {
    "must": [
      { "term": { "status": "published" } },
      { "term": { "language": "vi" } }
    ]
  }
}
~~~

Results must have status published and language vi. However, if conditions are purely exact constraints that do not need relevance scoring, filter is usually a better choice.

## 3. Role of filter

filter is also a mandatory condition that must match, but it runs in filter context and does not contribute to score. It is the right choice for structural filtering conditions.

Example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lt": 500
            }
          }
        }
      ]
    }
  }
}
~~~

Documents must match the name match query and all filters. Filters neither increase nor decrease a document's score.

### 3.1. Conditions suited for filter

Conditions commonly placed in filter:

- Statuses such as published, active, or archived.
- Categories, product codes, tenants, or document types.
- Boolean flags such as available or enabled.
- Price, quantity, or time ranges.
- Field existence conditions.
- Server-enforced access control or data scope constraints.

Filter separates relevance from business constraints. On a search page, users enter keywords ranked by score, while category, status, and price range filters simply determine which documents are allowed to appear.

### 3.2. Filter does not compute score

A query placed in filter context only determines whether a document satisfies the condition. It does not boost relevance scores. Therefore, if a condition should influence result order, consider placing it in must or should.

Filter context suits exact conditions and can leverage Elasticsearch's caching mechanisms in appropriate scenarios. Do not assume every filter is guaranteed to be cached; caching depends on the query, data, and cluster state.

### 3.3. Both must and filter are mandatory, differing in scoring

| Criterion | must | filter |
|---|---|---|
| Document must match | Yes | Yes |
| Computes score | Yes | No |
| Suitable for | Full-text, conditions affecting relevance | Status, codes, categories, price/date ranges |
| Result ordering | Can affect score | Does not alter score |

Do not put every condition in must simply because they are all mandatory. Separate full-text search conditions from structural filter constraints.

## 4. Role of should

should holds optional or alternative conditions. It has two common uses:

1. When neither must nor filter is present, at least one should condition must match by default.
2. When bool already has must or filter, should conditions can act purely to boost scores and are not required to match by default.

This default rule is the most common source of bugs when writing Bool Queries.

### 4.1. should as a mandatory OR group

Example finding products in category books or games:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "category": "books"
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
}
~~~

Because bool has only should, at least one branch must match. You can declare it explicitly:

~~~json
{
  "query": {
    "bool": {
      "should": [
        { "term": { "category": "books" } },
        { "term": { "category": "games" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

minimum_should_match makes explicit that at least one should condition must match.

### 4.2. should as a score-boosting condition

Suppose all products must match a keyword and belong to category electronics. If the brand is Acme, the product gets prioritized:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        }
      ]
    }
  }
}
~~~

In this structure, must and filter already hold mandatory conditions. By default, should is not required to match; it can boost the score for Acme products. Products from other brands can still appear if they satisfy must and filter.

This is how should is used to boost relevance without excluding other matching results.

### 4.3. When should must match despite must/filter

If business rules require matching must/filter AND at least one should branch, set minimum_should_match:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        },
        {
          "term": {
            "brand": "Contoso"
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

A document must match at least one of the two brands, while also satisfying must and filter.

### 4.4. Default behavior table for should

| Clauses present in bool | Default minimum_should_match |
|---|---:|
| Only should | 1 |
| must or filter alongside should | 0 |
| No should | Not applicable |

If business logic depends on whether should is mandatory or not, declare minimum_should_match explicitly rather than relying on defaults.

## 5. Role of must_not

must_not holds conditions that a document must not match. If a document matches any subquery inside must_not, it is excluded from results.

Example excluding discontinued products:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        }
      ]
    }
  }
}
~~~

must_not can be combined with must and filter:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "laptop"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        },
        {
          "term": {
            "visibility": "private"
          }
        }
      ]
    }
  }
}
~~~

Results must match name, be available, and must not be discontinued or private.

### 5.1. must_not does not compute score

must_not is an exclusion condition. It does not increase or decrease the score of retained documents. If you need a condition that positively contributes to relevance, use must or should depending on requirements.

### 5.2. Documents missing a field when using must_not

An important detail: a document lacking a field typically does not match a term query on that field. Therefore, when a term query is placed inside must_not, documents missing the field can still be kept.

Example:

~~~json
{
  "bool": {
    "must_not": [
      {
        "term": {
          "status": "deleted"
        }
      }
    ]
  }
}
~~~

The query excludes documents with status equal to deleted. A document without status also does not match term status=deleted, so it can still appear.

If business logic requires status to exist and not be deleted, add exists inside filter:

~~~json
{
  "bool": {
    "filter": [
      {
        "exists": {
          "field": "status"
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "deleted"
        }
      }
    ]
  }
}
~~~

Do not confuse "does not have a forbidden value" with "has a valid value". Those are two distinct data rules.

## 6. Combining All Four Clauses in One Query

Complete example for a product search page:

- Name or description must relate to the search phrase.
- Category must be electronics.
- Price must be from 100 to under 500.
- Product must be available.
- Product must not be discontinued or private.
- Brands Acme or Contoso receive higher score priority.

Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "electronics"
          }
        },
        {
          "term": {
            "available": true
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lt": 500
            }
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": "Acme"
          }
        },
        {
          "term": {
            "brand": "Contoso"
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "discontinued"
          }
        },
        {
          "term": {
            "visibility": "private"
          }
        }
      ]
    }
  }
}
~~~

Here should only prioritizes brands. Because bool has must and filter, products not belonging to Acme or Contoso can still appear if they satisfy the mandatory conditions. If business rules allow only those two brands, add minimum_should_match: 1.

## 7. Logical Combination Rules and Nested bool Groups

Bool queries can be nested to express parenthesized expressions. Each child bool has independent must, should, filter, and must_not rules.

Suppose the requirement is:

~~~text
status = published
AND
(
    category = books
    OR
    (category = games AND featured = true)
)
AND NOT discontinued
~~~

This can be expressed as:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "published"
          }
        },
        {
          "bool": {
            "should": [
              {
                "term": {
                  "category": "books"
                }
              },
              {
                "bool": {
                  "filter": [
                    {
                      "term": {
                        "category": "games"
                      }
                    },
                    {
                      "term": {
                        "featured": true
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

The second nested bool group only matches when category is games and featured is true. The outer bool requires one of the two should branches to match. minimum_should_match is set explicitly to preserve OR semantics.

### 7.1. Do not rely on clause appearance order

A Bool query does not execute like a sequential list of imperative statements. Clause ordering in JSON does not create sequential execution flow like an `if` chain in Java. Design groups around Boolean semantics and use nested bools to represent parentheses.

### 7.2. Using should for multiple text-matching strategies

Another example is searching articles by title or content:

~~~json
{
  "bool": {
    "should": [
      {
        "match": {
          "title": {
            "query": "spring data elasticsearch",
            "boost": 3
          }
        }
      },
      {
        "match": {
          "content": "spring data elasticsearch"
        }
      }
    ],
    "minimum_should_match": 1
  }
}
~~~

A document only needs to match title or content. Title has a higher boost, so a title match can rank above a content-only match.

## 8. `minimum_should_match` in More Detail

minimum_should_match specifies the minimum number or percentage of should conditions that must match. It can accept an integer, negative integer, percentage, or conditional expression.

Example:

| Value | Meaning |
|---|---|
| 1 | At least one should must match |
| 2 | At least two shoulds must match |
| 75% | At least 75% of shoulds must match |
| -1 | Allows missing one should |
| -25% | Allows missing 25% of shoulds |

With 4 should conditions:

- 75% requires at least 3 conditions to match.
- -25% allows missing 1 condition, also requiring 3 conditions to match.

With other counts of conditions, positive percentages and negative percentages can round differently. Check the Elasticsearch documentation and test with the actual branch count.

Conditional expressions can also be used, for example:

~~~json
{
  "bool": {
    "should": [
      { "term": { "tag": "java" } },
      { "term": { "tag": "spring" } },
      { "term": { "tag": "elasticsearch" } },
      { "term": { "tag": "search" } }
    ],
    "minimum_should_match": "2<-25% 9<-3"
  }
}
~~~

Conditional expressions let the minimum required matches vary with the total number of should clauses. Only use the advanced form when search requirements genuinely demand it; for most use cases, an integer such as 1 is clearer and easier to test.

## 9. Using Bool Query in Spring Data Elasticsearch with NativeQuery

When explicit control over all four clauses is needed, NativeQuery is a good fit in Spring Data Elasticsearch versions backed by the Elasticsearch Java Client.

Example entity:

~~~java
import java.math.BigDecimal;

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

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String brand;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Building a NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<Product> searchProducts(String text) {
    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("category")
                            .value(FieldValue.of("electronics"))
                    ))
                    .filter(f -> f.term(t -> t
                            .field("available")
                            .value(FieldValue.of(true))
                    ))
                    .mustNot(mn -> mn.term(t -> t
                            .field("status")
                            .value(FieldValue.of("discontinued"))
                    ))
                    .should(s -> s.term(t -> t
                            .field("brand")
                            .value(FieldValue.of("Acme"))
                    ))
            ))
            .build();

    return operations.search(query, Product.class);
}
~~~

This snippet illustrates the Elasticsearch Java Client builder API used by Spring Data Elasticsearch. The NativeQuery package, FieldValue type, and certain overloads may differ by release train; verify your project's dependency and Javadoc before copying verbatim.

In the example, should only boosts brand Acme because bool already has must and filter. If you want only Acme results, add minimumShouldMatch("1") to the BoolQuery builder.

### 9.1. Adding minimum_should_match in NativeQuery

Example:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query(text)
                ))
                .should(s -> s.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("Acme"))
                ))
                .should(s -> s.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("Contoso"))
                ))
                .minimumShouldMatch("1")
        ))
        .build();
~~~

Then, in addition to matching name, a document must match at least one of the two brands.

## 10. Using Bool Query in a Repository with `@Query`

If the query structure is fixed and only a few values change, you can declare JSON DSL using `@Query`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "must": [
              {
                "match": {
                  "name": "?0"
                }
              }
            ],
            "filter": [
              {
                "term": {
                  "category": "?1"
                }
              }
            ],
            "must_not": [
              {
                "term": {
                  "status": "discontinued"
                }
              }
            ]
          }
        }
        """)
    List<Product> searchAvailableProducts(String text, String category);
}
~~~

This representation fits when the DSL rarely changes. For queries with many optional branches, multiple bool groups, or business logic varying per request, building NativeQuery in a service is usually easier to read and test.

If the repository method needs pagination, you can combine Pageable according to version support. Pageable controls pagination; do not put it into the JSON Bool Query as an ordinary placeholder.

## 11. Use CriteriaQuery or NativeQuery?

CriteriaQuery is handy for common field conditions and basic AND/OR groups. NativeQuery is better suited when precise control over bool structure, minimum_should_match, nested queries, boosts, or other DSL features is needed.

| Requirement | Commonly suited approach |
|---|---|
| A few mandatory conditions on fields | CriteriaQuery or NativeQuery |
| Simple dynamic filters | CriteriaQuery |
| Explicit must, filter, must_not, and should | NativeQuery |
| should with specific minimum_should_match | NativeQuery or @Query JSON |
| Multi-level nested bools | NativeQuery |
| Fixed query changing only a few values | @Query |
| Nested queries, function score, or specialized DSL | NativeQuery |

There is no rule requiring a single API for all queries. Choose the representation that makes logic easy to understand, observe, and test.

## 12. How Mapping Affects Bool Queries

A Bool query combines subqueries, yet each subquery remains governed by its field mapping.

| Field mapping | Commonly used query | Notes |
|---|---|---|
| text | match, multi_match | Analyzes text via analyzer |
| keyword | term, terms | Matches exact values |
| integer, long, double | range, term | Parameter types must match |
| date, date_nanos | range | Format and timezone must be explicit |
| boolean | term | Uses true/false values |
| nested | nested query containing bool | Must use the right path and nested mapping |

For instance, using term on a text field may not match the entire string as expected because the field was tokenized by an analyzer. For codes, statuses, or categories, keyword is generally better. For full-text search content, match is usually the right choice.

### 12.1. Nested query containing a Bool Query

If a field is mapped as nested, conditions across properties of the same element must be placed inside a nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "range": {
                "variants.stock": {
                  "gt": 0
                }
              }
            }
          ]
        }
      }
    }
  }
}
~~~

The query requires the same nested object to have color black and stock greater than 0. If variants were a regular object rather than nested, query semantics would differ. Confirm the mapping before writing nested bool queries.

## 13. Common Mistakes

### 13.1. Putting every condition in must

This can unnecessarily include filter conditions in score computation. Put search keywords in must and structural constraints in filter when scoring is not needed.

### 13.2. Thinking should is always a mandatory OR

When bool has must or filter, should may not be mandatory by default. If at least one branch is required, declare minimum_should_match.

### 13.3. Using must_not while forgetting fields can be missing

Documents lacking the negated field may still be retained. If the field must exist, combine exists inside filter.

### 13.4. Placing minimum_should_match at the wrong level

If a query has nested bools, minimum_should_match applies to the should group of the bool containing it. Placing it on the parent bool does not control a child bool's should. Place the value on the exact group being constrained.

### 13.5. Using term on text

term does not analyze the input string like match. Inspect mappings and pick the matching query.

### 13.6. Confusing filter with must_not

filter requires documents to match. must_not requires documents not to match. The two clauses have opposite logical polarity.

### 13.7. Using should to boost but accidentally making it mandatory

If bool has only should, at least one branch must match by default. If you want all documents matching another query and merely boosted by should, include an appropriate must or filter in the bool.

### 13.8. Writing deeply nested queries without inspecting the DSL

A bool query can be valid JSON yet group logic incorrectly. Write out the Boolean expression first, inspect the emitted DSL, and test with data that has clear expected outcomes.

## 14. Testing Bool Queries

Test individual clauses separately before testing the combined query.

Example for the expression:

~~~text
name matches "keyboard"
AND category = electronics
AND available = true
AND NOT status = discontinued
AND (brand = Acme OR brand = Contoso)
~~~

Test dataset:

| Document | Name | Category | Available | Status | Brand | Result |
|---|---|---|---|---|---|---|
| A | Wireless keyboard | electronics | true | active | Acme | Selected |
| B | Office keyboard | electronics | true | active | Contoso | Selected |
| C | Wireless keyboard | electronics | true | active | Other | Excluded by OR group |
| D | Wireless keyboard | books | true | active | Acme | Excluded by category |
| E | Wireless keyboard | electronics | false | active | Acme | Excluded by available |
| F | Wireless keyboard | electronics | true | discontinued | Acme | Excluded by must_not |
| G | Wireless keyboard | electronics | true | active | missing | Excluded if brand is mandatory should |

For a query that only uses should for boosting without minimum_should_match, document C may be kept with a lower score than A or B. Tests should reflect the exact should mode in use.

Things to verify:

1. Each must truly requires a match.
2. Each filter truly excludes non-matching documents.
3. should behaves with the intended requirement level and boost.
4. must_not excludes the intended documents.
5. Missing fields are handled per business rules.
6. Scores and result ordering make sense.
7. Queries through aliases or multiple indices have compatible mappings.

### 14.1. Inspecting scores

When you need to understand why one document ranks ahead of another, use the Explain API for a specific document or query profiling in an appropriate environment. Do not enable profiling for every production query because it adds overhead.

Scores are affected by queries in query context such as must and should. Filter and must_not do not add score. If scoring is not a business requirement, avoid complicating queries just for unnecessary ranking tweaks.

## 15. Workflow for Building Queries from Business Requirements

A clear workflow:

1. List mandatory conditions separately.
2. Classify which conditions should affect relevance and which only filter.
3. List exclusion conditions.
4. Identify OR alternatives and the minimum number of branches that must match.
5. Add nested bool queries for parentheses where needed.
6. Check each field's mapping to select match, term, range, exists, or nested.
7. Build the appropriate NativeQuery or `@Query`.
8. Inspect the DSL sent to Elasticsearch.
9. Test with matching, non-matching, missing-field, and boundary cases.

Classification example:

| Requirement | Clause |
|---|---|
| Name relates to keyword | must |
| Category is electronics | filter |
| Price within valid range | filter |
| Product not discontinued | must_not |
| Prefer brand Acme | should |
| Only allow Acme or Contoso | should + minimum_should_match = 1 |

## 16. Conclusion

A Bool query combines four condition groups with distinct semantics. must and filter are both mandatory matches, but must participates in relevance scoring while filter does not. should provides alternatives or score boosting; when bool includes must or filter, should may not be mandatory by default. must_not excludes documents matching forbidden conditions without scoring.

minimum_should_match is a parameter requiring special attention. Set it explicitly whenever business logic demands one or more should branches to match. When expressions have parentheses or multiple logic levels, use nested bool queries to preserve each condition's scope.

In Spring Data Elasticsearch, NativeQuery is well suited for building Bool Queries via the Elasticsearch Java Client; `@Query` fits fixed DSL. Whichever approach you pick, verify queries against mappings, inspect the actual DSL, and test missing fields, OR branches, and exclusion conditions.
