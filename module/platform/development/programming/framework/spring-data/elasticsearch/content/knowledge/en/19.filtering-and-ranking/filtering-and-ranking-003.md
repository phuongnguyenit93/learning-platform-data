# Boosting Individual Fields and Clauses

In Elasticsearch, a query may find the exact right set of documents yet still produce an order that does not match business expectations. For example, a user searches for "wireless keyboard"; the application wants articles containing the phrase in `title` to rank higher than articles that only mention the phrase in `content`. Or a product from a preferred brand needs to rank above another product even though both match the search text.

**Boosting** is the way to adjust how much a field or a query clause contributes to the relevance score. Field-level boosts are usually configured in `multi_match` or `query_string`, such as `title^4`. Clause-level boosts are set on individual queries inside a compound query—for example, `match` on `title` having `boost: 2.0` while `match` on `description` keeps the default `1.0`.

Boosting affects score-based ranking. It does not change data in `_source`, does not modify mappings, and does not guarantee a document always stays at a fixed position. The score also depends on match quality, term frequency, field length, index statistics, query type, and other clauses.

## 1. Relevance Score and the Meaning of Boost

Full-text queries such as `match` and `multi_match` typically produce a relevance score for each hit. Elasticsearch uses the score to sort results in descending order if the request does not specify another sort.

Suppose two articles both match the query "spring data":

- Article A has the phrase in its title.
- Article B only mentions the phrase inside a long body.

If you only use a `multi_match` with equal weights across fields, the scores of the two articles may not reflect the importance the search product expects. Boosting `title` gives title matches greater influence.

In Elasticsearch, the default boost of a query is `1.0`. A boost greater than `1.0` increases that query's impact on the score; a boost less than `1.0` reduces its relative impact. Think of boost as a relevance adjustment factor, not as the final score or a probability that a document is correct.

### 1.1 Boost Is Not a Filter

Boost does not decide whether a document is allowed to appear. It adjusts the score of documents that already satisfy the query. If a document does not match a mandatory condition, a high boost will not make it appear.

Example:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": "wireless keyboard"
          }
        }
      ],
      "should": [
        {
          "match": {
            "title": {
              "query": "wireless keyboard",
              "boost": 3.0
            }
          }
        }
      ]
    }
  }
}
```

A document still has to match `content` because that is a `must` condition. If the title also matches, the `should` clause contributes additional score. If the title does not match, the document can still appear via `must`, just without that extra score contribution.

### 1.2 Boost Does Not Guarantee Absolute Ordering

A boosted document can still rank behind another document if the other document matches more strongly in the remaining parts of the query. For instance, an article whose title matches one token might score lower than an article whose title and content match multiple tokens.

If business logic requires an absolute order by an attribute—such as lowest price first or newest timestamp first—use `sort`. Boost is meant for relevance ranking, where multiple signals are combined into a score.

## 2. Field-Level Boost in multi_match

When searching a string across multiple fields, `multi_match` lets you attach a separate weight to each field using the `^` syntax.

Example article mapping:

```json
PUT /articles
{
  "mappings": {
    "properties": {
      "title": { "type": "text" },
      "summary": { "type": "text" },
      "content": { "type": "text" },
      "status": { "type": "keyword" }
    }
  }
}
```

Searching across all three fields while prioritizing the title:

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data elasticsearch",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
```

Weights are interpreted relatively:

| Field | Boost | Design Intent |
|---|---:|---|
| `title` | 4 | Strongest signal |
| `summary` | 2 | Important, but lower than title |
| `content` | 1 (default) | Baseline signal |

If `^` is omitted, the field has a default boost of `1.0`. The `title^4` syntax is equivalent to setting a boost for that field in the query configuration. It does not alter the mapping or indexed data.

### 2.1 Why Prioritize title?

Titles are usually written to express a document's main topic. If search keywords appear in the title, that is often a stronger relevance signal than the keywords appearing once inside a long body.

However, this is a product assumption that should be verified. For some datasets, `description`, `tags`, or `category` might matter more than `title`. Boosts should reflect actual search behavior and relevance evaluation rather than field names alone.

### 2.2 Field Boost in query_string

`query_string` also supports field boosts:

```json
GET /articles/_search
{
  "query": {
    "query_string": {
      "query": "spring data elasticsearch",
      "fields": [
        "title^4",
        "summary^2",
        "content"
      ]
    }
  }
}
```

`query_string` has its own syntax parser and allows users to specify operators or target fields. It fits cases where the application intentionally supports advanced query syntax. For a free-text search box, `multi_match` is usually easier to control because user input is not interpreted as a full query expression.

## 3. Field Boost Across multi_match Types

Field boosts combine with the `multi_match` type to produce different score combination behaviors. You should not tweak multipliers while ignoring the `type` of `multi_match`.

### 3.1 best_fields

`best_fields` is a common type when a strong match in a single field can represent the document's overall relevance. The query is constructed in a disjunction-max style: the best score among the fields is the primary component; `tie_breaker` can add a fraction of the scores from the other fields.

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "type": "best_fields",
      "fields": ["title^4", "summary^2", "content"],
      "tie_breaker": 0.2
    }
  }
}
```

This type fits when matching strongly in one important field matters more than keywords appearing scattered across several fields. `tie_breaker` lets scores from other matching fields contribute extra weight at a tuned proportion.

### 3.2 most_fields

`most_fields` sums scores across multiple matching fields. This type can be useful when the same content is indexed through multiple analyses or complementary field representations.

```json
GET /articles/_search
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "type": "most_fields",
      "fields": ["title^3", "title.shingles", "title.stemmed"]
    }
  }
}
```

Because scores from multiple fields can be summed, a document matching across multiple fields can be favored. Verify whether this is the desired signal or whether it biases results because the same content is repeated across fields.

### 3.3 cross_fields

`cross_fields` treats multiple fields in a term-centric way: query terms can be matched across multiple fields as if they belonged to a single logical field group. This type is helpful when data is split across fields while users search for a combined piece of information, such as `first_name` and `last_name`.

```json
GET /people/_search
{
  "query": {
    "multi_match": {
      "query": "nguyen an",
      "type": "cross_fields",
      "fields": ["firstName^2", "lastName"]
    }
  }
}
```

`cross_fields` has constraints regarding analyzers and field grouping. Check the mapping so the fields have compatible analyzers. Do not use it as a generic replacement for `best_fields` or `most_fields`.

### 3.4 Which Type to Choose?

| Type | Primary Combination Method | Typical Use Case |
|---|---|---|
| `best_fields` | Favors the field with the best score | A strong match in one field is the main signal |
| `most_fields` | Combines scores from multiple fields | Multiple fields complement the same content |
| `cross_fields` | Combines term-by-term across a field group | A single piece of information is split across multiple fields |

Field boosts do not behave identically across all types. Choose the `multi_match` semantics first, then tune field multipliers.

## 4. Boosting a Query Clause

Clause-level boost is declared on an individual query. This approach fits when a query combines multiple kinds of signals: main content, brand, category, featured status, or preferred phrases.

For example, the main query searches content, while a title match receives additional score:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": {
              "query": "spring data elasticsearch"
            }
          }
        }
      ],
      "should": [
        {
          "match": {
            "title": {
              "query": "spring data elasticsearch",
              "boost": 3.0
            }
          }
        }
      ]
    }
  }
}
```

`must` determines the required content match. `should` adds a ranking signal. A boost of `3.0` gives the title clause's score stronger influence than the default when that clause matches.

### 4.1 Boosting Individual Clauses in bool

You can attach different boosts to each clause:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "spring data",
            "fields": ["title", "content"]
          }
        }
      ],
      "should": [
        {
          "term": {
            "status": {
              "value": "FEATURED",
              "boost": 2.0
            }
          }
        },
        {
          "match": {
            "title": {
              "query": "elasticsearch",
              "boost": 1.5
            }
          }
        },
        {
          "match_phrase": {
            "title": {
              "query": "spring data",
              "boost": 3.0
            }
          }
        }
      ],
      "filter": [
        { "term": { "published": true } }
      ]
    }
  }
}
```

The `should` clauses contribute to the score when matched. The `filter` clause restricts eligible documents without contributing a relevance score. `must_not` also excludes documents and is not used as a score-boosting signal.

### 4.2 Clause Boost vs. Field Boost

Both approaches can produce similar-looking queries, yet they operate at different levels:

- Field boost in `multi_match` adjusts the influence of a field when the same query runs across multiple fields.
- Clause boost adjusts the influence of a child query inside a compound query.

Field boost example:

```json
"multi_match": {
  "query": "spring data",
  "fields": ["title^4", "content"]
}
```

Clause boost example:

```json
"bool": {
  "should": [
    { "match": { "title": { "query": "spring data", "boost": 4 } } },
    { "match": { "content": "spring data" } }
  ]
}
```

Field boost is convenient when a single string is searched across multiple fields. Clause boost is more flexible when each signal has its own query type or separate AND/OR logic.

## 5. Roles of must, should, filter, and must_not

When boosting clauses in a `bool` query, you need to understand the semantics of each group:

| Clause | Must Match? | Contributes Score? | Role |
|---|---|---|---|
| `must` | Yes | Yes | Mandatory condition with scoring |
| `should` | Depends on context | Yes when matched | Ranking signal or alternative condition |
| `filter` | Yes | No | Restricts document set, no relevance scoring |
| `must_not` | Must not match | No | Excludes documents |

### 5.1 should Purely for Boosting

When a `bool` query already has `must` or `filter`, `should` clauses are optional by default. They raise the score for matching documents without excluding documents that fail `should`.

This is a common pattern for "preferring" results:

```json
{
  "bool": {
    "must": [
      { "match": { "content": "spring data" } }
    ],
    "should": [
      { "match": { "title": { "query": "spring data", "boost": 3.0 } } }
    ]
  }
}
```

Documents matching only content are still returned. Documents that also match title are prioritized via a higher score.

### 5.2 minimum_should_match Turns should into a Condition

If at least a certain number of `should` clauses must match, use `minimum_should_match`:

```json
{
  "bool": {
    "must": [
      { "match": { "content": "spring data" } }
    ],
    "should": [
      { "term": { "status": "FEATURED" } },
      { "match": { "title": "elasticsearch" } }
    ],
    "minimum_should_match": 1
  }
}
```

With this configuration, a document must match content and at least one of the two `should` clauses. `should` is no longer just an optional boosting signal; it participates in document selection.

If the goal is purely boosting, do not set `minimum_should_match` in a way that accidentally filters out documents matching the main query.

### 5.3 Do Not Put Boosts Inside filter Expecting Higher Scores

Filters are optimized for non-scoring conditions. For example:

```json
"filter": [
  { "term": { "status": { "value": "FEATURED", "boost": 5 } } }
]
```

is not the right way to prioritize FEATURED by relevance, because `filter` contributes no score. If you need prioritization, place that condition into a scoring clause such as `should` or use an appropriate scoring function. You can still keep mandatory conditions in `filter` to restrict the dataset.

## 6. Combining Field Boosts and Clause Boosts

A real-world query can use both levels:

1. Use `multi_match` to search content across multiple fields with different weights.
2. Use `should` to add independent signals such as a preferred brand or a phrase match.
3. Use `filter` for mandatory conditions unrelated to relevance.

Example:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "type": "best_fields",
            "fields": [
              "name^4",
              "shortDescription^2",
              "description"
            ]
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "Northwind",
              "boost": 2.0
            }
          }
        },
        {
          "match_phrase": {
            "name": {
              "query": "wireless keyboard",
              "boost": 3.0
            }
          }
        },
        {
          "term": {
            "featured": {
              "value": true,
              "boost": 1.5
            }
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "computer-accessories" } }
      ]
    }
  }
}
```

In this example:

- `name^4` is prioritized over `shortDescription^2` and `description`.
- `brand = Northwind` increases the score if the document belongs to that brand.
- Phrase match in `name` acts as a stronger signal when words appear in exact order.
- `featured = true` adds another preference signal.
- `active` and `category` are mandatory filters that do not affect the score.

A document cannot bypass the active/category filters merely because of a brand or featured boost. This cleanly separates eligibility from ranking.

## 7. Disjunction Max and tie_breaker

When searching across multiple fields, how scores are combined shapes the effect of field boosts. `dis_max` picks the highest score among child queries and can add a fraction of the remaining queries' scores via `tie_breaker`.

Example:

```json
GET /articles/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "spring data",
              "boost": 4.0
            }
          }
        },
        {
          "match": {
            "summary": {
              "query": "spring data",
              "boost": 2.0
            }
          }
        },
        {
          "match": {
            "content": "spring data"
          }
        }
      ],
      "tie_breaker": 0.2
    }
  }
}
```

With `tie_breaker` equal to 0, the best score is the primary component. Values greater than 0 let other child queries contribute extra score. Higher values give multi-field matches greater influence.

`multi_match` of type `best_fields` uses a mechanism closely aligned with `dis_max`. If you want to control each field as a separate query, you can use `dis_max` directly. Do not increase `tie_breaker` without understanding how adding scores from multiple fields changes the ranking.

## 8. Demotion Boosts and Advanced Scoring Signals

Boosts are usually used to raise influence, but sometimes business logic needs to lower the priority of a group of results while still keeping them in the result set.

### 8.1 Boosting Query

The `boosting` query pairs a positive query with a negative query. Documents matching positive can still appear; if they also match negative, their score is multiplied by `negative_boost`.

```json
GET /articles/_search
{
  "query": {
    "boosting": {
      "positive": {
        "match": {
          "content": "spring data"
        }
      },
      "negative": {
        "term": {
          "status": "ARCHIVED"
        }
      },
      "negative_boost": 0.2
    }
  }
}
```

ARCHIVED documents can still be returned if they match positive, but their score is reduced. If business logic wants to completely exclude ARCHIVED, use `must_not` or an appropriate filter instead of demoting.

### 8.2 Function Score

If ranking depends on metrics like popularity, freshness, or rating, simply adding static clause boosts may not suffice. `function_score` lets you combine the query score with functions computed from fields or formulas.

General example:

```json
GET /products/_search
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "name": "wireless keyboard"
        }
      },
      "field_value_factor": {
        "field": "popularity",
        "modifier": "log1p",
        "factor": 1.2,
        "missing": 0
      },
      "boost_mode": "multiply"
    }
  }
}
```

Here the relevance score is adjusted by a popularity signal. Function score is more powerful than static boosts and requires managing scale, missing values, modifiers, and combination mode (`boost_mode`). Use it when ranking depends on quantitative data; do not use it merely to replace a simple field boost.

### 8.3 Rescore

For complex ranking, you can use rescore to apply a more expensive query to a top subset of initially selected results. For example, the first query runs a fast match, and rescore runs a phrase match to refine the top documents.

Rescore can reduce cost compared to applying a complex query across the entire document set, though it only acts within the configured rescore window. It should be evaluated alongside pagination, shards, and result ordering.

## 9. Boosting in Spring Data Elasticsearch Using NativeQuery

With Spring Data Elasticsearch using the Elasticsearch Java API Client, `NativeQuery` lets you build Query DSL using Java builders. Field boosts are passed in `multi_match`'s field list; clause boosts are placed on child queries.

### 9.1 Field Boost in multi_match

```java
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query("wireless keyboard")
        .fields(List.of(
            "name^4",
            "shortDescription^2",
            "description"
        ))
    ))
    .build();
```

`fields` holds field boost syntax identical to JSON Query DSL. `name` has weight 4, `shortDescription` has weight 2, and `description` uses the default. The query is executed via `ElasticsearchOperations`:

```java
SearchHits<Product> hits = operations.search(query, Product.class);
```

### 9.2 Clause-Level Boost in a bool Query

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.match(mm -> mm
            .field("description")
            .query("wireless keyboard")
        ))
        .should(s -> s.match(mm -> mm
            .field("name")
            .query("wireless keyboard")
            .boost(3.0f)
        ))
        .should(s -> s.match(mm -> mm
            .field("brandDescription")
            .query("Northwind")
            .boost(1.5f)
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(v -> v.booleanValue(true))
        ))
    ))
    .build();
```

In this example, the `must` clause defines the required content match. Two `should` clauses raise the score when the name or brand description matches. The `active` filter only restricts documents. Because `bool` already has `must`, `should` is optional by default and does not exclude documents that fail to match those two preference signals.

Builder types and numeric types for `boost` depend on the Elasticsearch Java Client version managed by Spring Data. If your project's API expects `Float` or a different overload, follow the dependency's Javadoc; the Query DSL structure and boost semantics remain as in the JSON examples.

### 9.3 Combining Field Boost, Clause Boost, and Filter

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.multiMatch(mm -> mm
            .query("wireless keyboard")
            .fields(List.of(
                "name^4",
                "shortDescription^2",
                "description"
            ))
        ))
        .should(s -> s.term(t -> t
            .field("featured")
            .value(v -> v.booleanValue(true))
            .boost(1.5f)
        ))
        .should(s -> s.matchPhrase(mp -> mp
            .field("name")
            .query("wireless keyboard")
            .boost(3.0f)
        ))
        .filter(f -> f.term(t -> t
            .field("active")
            .value(v -> v.booleanValue(true))
        ))
    ))
    .build();
```

This pattern demonstrates two boost levels coexisting in a single query. If a client version's builder lacks a matching overload, you can create the query via JSON/native request or use the query builder API for that exact version. There is no need to turn all logic into JSON strings when the Java Client already provides type-safe builders.

## 10. Boosting with Repository `@Query`

For static queries, you can declare Query DSL in `@Query`:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("{\"multi_match\":{\"query\":\"?0\",\"fields\":[\"title^4\",\"summary^2\",\"content\"]}}")
    List<Article> searchBoosted(String text);
}
```

The query annotation is convenient for simple, stable queries. If you need dynamic boosts by user type, varying field lists, or conditional clauses, `NativeQuery` is usually easier to structure and test.

Never concatenate raw user strings directly into a JSON query. Use placeholder binding or parameterized builders to avoid escaping bugs and maintain a clear boundary between input data and query structure.

## 11. Boost and BM25: Understanding Scores Properly

Elasticsearch typically uses BM25 by default for full-text scoring. BM25 considers several factors such as:

- How often a term appears in the document.
- How rare or common the term is across the entire index.
- Field/document length relative to the average length.
- Similarity parameters and mapping/index settings.

Boost adjusts the score produced by a query, but it does not erase these factors. A field with boost 4 does not mean every document matching that field will always rank above a document with boost 1. A document with more matching terms, suitable frequencies, or multiple matching clauses can still achieve a higher score.

### 11.1 Do Not Interpret Boost as a Percentage

A boost of `2.0` does not mean a document is twice as relevant or has a 100% higher probability of being right. It is a multiplier influencing the query's scoring. The final score still depends on query structure and other signals.

### 11.2 Do Not Set Arbitrarily Huge Boosts

If `title` is given a boost of `1000`, the title signal can overwhelm almost every other signal. That can cause documents with weak title matches to outrank documents with much more relevant content.

Start with moderate factors—for example `title^3`, `summary^2`, and `content` at default—then evaluate on a sample query set. This is only a starting point for experimentation, not a universal formula.

### 11.3 Scores Are Not Stable Across Different Indexes or Queries

Scores are affected by term statistics and index layout. When shards/indexes or datasets change, scores can shift. Do not persist scores as durable business metrics or directly compare scores from two structurally different queries.

## 12. When to Use Boost vs. Sort or function_score?

These three mechanisms solve different requirements:

| Mechanism | Goal | Example |
|---|---|---|
| Boost | Adjust relevance of a field/query clause | Prefer title over body |
| Sort | Order by values with a deterministic order | Price ascending, newest timestamp |
| Function score | Combine relevance with computed signals | Popularity, freshness, rating |

If the requirement is "documents with keywords in the title should be preferred," use field/clause boosts. If the requirement is "lowest price must come first regardless of content," use sort. If the requirement is "combine relevance with popularity via a formula," consider `function_score` or an appropriate ranking pipeline.

Do not use boost to simulate a deterministic order when sort expresses it directly.

## 13. Inspecting Scores with Explain and Profile

When ranking looks off, inspect the scores instead of just bumping boosts until results "look right."

### 13.1 Explaining a Document

`_explain` shows why a document matched and what components contributed to its score:

```http
GET /articles/_explain/article-1001
{
  "query": {
    "multi_match": {
      "query": "spring data",
      "fields": ["title^4", "summary^2", "content"]
    }
  }
}
```

The response explains which child queries matched, which boosts were applied, and the relevant scoring factors. Use it to confirm field boosts are taking effect and see which clauses gave the document its score.

### 13.2 Profiling a Search Request

The Profile API provides detailed timing information for executing query components:

```json
GET /articles/_search
{
  "profile": true,
  "query": {
    "multi_match": {
      "query": "spring data",
      "fields": ["title^4", "summary^2", "content"]
    }
  }
}
```

Profile is helpful for investigating query cost, but it adds overhead and creates large responses. Enable it only during investigation or on controlled requests; do not enable it by default on every production search.

### 13.3 Comparing a Representative Query Set

To tune boosts, create a representative query set with expected result ordering or relevance judgments. Compare:

1. Baseline query without boosts.
2. Query with field boosts.
3. Query with clause boosts.
4. Query combining both.

Evaluate cases with title matches, body matches, multi-field matches, common keywords, and long queries. You can use metrics such as Precision@K, Recall@K, MRR, or NDCG if relevance labels are available.

Do not test only one favorable query. Good boosts should improve quality across many queries without severely hurting other query groups.

## 14. Common Mistakes

### 14.1 Putting Boost in filter and Expecting Score to Increase

Filters do not compute relevance scores. Place preference signals into a scoring query like `should`, or use `function_score` if a formula is needed.

### 14.2 Using should and Accidentally Turning It into a Mandatory Condition

When `must` or `filter` is present, `should` is normally optional. Setting `minimum_should_match` may filter out documents that do not match `should`. Decide whether `should` is purely for boosting or truly a selection condition.

### 14.3 Using Field Boost Without Checking multi_match Type

`best_fields`, `most_fields`, and `cross_fields` combine scores differently. Pick the type based on semantics before tuning field boosts.

### 14.4 Overly Large Boosts Unbalancing Ranking

Large multipliers can overpower BM25 and other signals. Start with moderate factors, measure relevance, and adjust incrementally.

### 14.5 Confusing Boost with Sort

Boost only influences scores. If you need deterministic ordering by price, date, or quantity, use sort.

### 14.6 Boosting Non-Scoring Filter Fields

`keyword` fields can participate in scoring queries such as `term` queries, but if placed in `filter`, boost has no effect. Distinguish field type from query clause placement.

### 14.7 Misunderstanding tie_breaker

In `dis_max`/`best_fields`, `tie_breaker` lets other matching fields contribute extra score. Values that are too large can let repeated content across multiple fields add more points than expected.

### 14.8 Treating Scores as Probabilities

Scores are not probabilities and should not be displayed as confidence percentages without a dedicated calibration model.

## 15. Boost Design Workflow

When building ranking for a search endpoint, follow this sequence:

1. Identify mandatory conditions: tenant, status, access rights, data type. Place them in `filter` or `must` according to semantics.
2. Identify the primary search content. Choose `match`, `multi_match`, or an appropriate query.
3. Identify which fields are more important and attach field boosts in `multi_match`.
4. Identify independent preference signals, such as phrase match, brand, or featured status. Put them in `should` with clause boosts.
5. Check `minimum_should_match` to ensure preference clauses have the right optional or mandatory role.
6. Choose `multi_match` type and `tie_breaker` based on desired score combination.
7. If ranking depends on numerical metrics, evaluate `function_score`; if strict ordering is needed, use sort.
8. Inspect `_explain`, profiling, and an evaluation query set.
9. Tune boosts incrementally and monitor quality after deployment.

## 16. Summary

Boost lets you tune relevance scores at two levels. Field boosts, typically used in `multi_match` or `query_string` with `field^n` syntax, prioritize one field over another. Clause boosts are placed on individual child queries to adjust the contribution of different signals inside `bool`, `dis_max`, or compound queries.

When using `bool` queries, `must` is both mandatory and scored; `should` can be an optional preference signal or become a condition via `minimum_should_match`; `filter` and `must_not` do not contribute to relevance scores. Understanding these roles prevents placing boosts in the wrong spot or accidentally filtering out documents.

In Spring Data Elasticsearch, `NativeQuery` lets you configure field boosts in `multi_match` and clause boosts in the Java Client query builders. Choose the right `multi_match` semantics, check `tie_breaker`, use explain to understand scores, and evaluate against a representative query set. Use boost for relevance, sort for deterministic ordering, and `function_score` when combining additional quantitative signals.

## References

- [Elasticsearch — Multi-match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-multi-match-query.html)
- [Elasticsearch — Boosting query clauses](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-boosting-query.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
- [Elasticsearch — Disjunction max query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-dis-max-query.html)
- [Elasticsearch — Function score query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-function-score-query.html)
- [Spring Data Elasticsearch Reference — Search Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
