# Disjunction Max and Combining Scores Across Multiple Fields

In full-text search, the same keywords can appear across multiple fields of a document: title, product name, description, author name, or detailed body. Elasticsearch needs a way to combine relevance scores from those fields to rank the results.

**Disjunction max**, commonly abbreviated as **dis_max**, is a query that combines multiple child queries by favoring the highest score. It fits cases where a document can match across several fields, yet a strong match in the most important field should largely determine the rank.

The `dis_max` formula is:

~~~text
score = max(scores of child queries)
        + tie_breaker × sum of remaining child query scores
~~~

With `tie_breaker` equal to 0, only the highest score is used. When `tie_breaker` is greater than 0, the other child queries also contribute a fraction to the final score. This mechanism differs from a `bool` query with multiple `should` clauses, where scores of matching clauses are typically summed together.

In Spring Data Elasticsearch, you can use `NativeQuery` to build `dis_max` or `multi_match` using Elasticsearch Query DSL. This article explains how scoring works, how to choose `tie_breaker`, how to combine multiple fields, and when to use `dis_max`, `bool`, or `multi_match`.

## 1. The Multi-Field Search Problem

Suppose a product document has this structure:

~~~json
{
  "id": "P-1001",
  "title": "Wireless Mouse",
  "subtitle": "Ergonomic Bluetooth Mouse",
  "description": "A wireless mouse for office and travel use",
  "brand": "Northwind"
}
~~~

A user searches for `wireless mouse`. The phrase can appear in:

- title: short product name, usually very important.
- subtitle: supplementary info, potentially important but less than the title.
- description: longer text that may contain the keywords, though usually with lower relevance.
- brand: brand name, carrying different semantics from descriptive text.

If you search only in `title`, you may miss documents whose keywords appear in `description`. If you simply sum scores across every field, documents with long descriptions or repeated keywords across fields may be pushed too high.

One approach is to run separate queries per field and combine their scores using `dis_max`. Another approach is to use `multi_match` with an appropriate `type`.

## 2. What Is Disjunction Max (dis_max)?

`dis_max` takes a list of child queries. A document only needs to match at least one child query to be included in the results. When multiple child queries match the same document, Elasticsearch picks the highest score as the main portion of the score.

REST DSL example:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": "wireless mouse"
          }
        },
        {
          "match": {
            "subtitle": "wireless mouse"
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ]
    }
  }
}
~~~

A document matching any of these three fields can be returned. If a document matches both `title` and `description`, the highest-scoring child query dominates the result when `tie_breaker` is not set.

### 2.1. Why Is It Called Disjunction Max?

- **Disjunction** represents OR logic: a document can match any one of the child queries.
- **Max** indicates that the best child query's score takes precedence.

`dis_max` both combines conditions with OR logic and applies a dedicated scoring rule. It does not require a document to match every field.

### 2.2. dis_max Does Not Automatically Mean More Accurate Matching

`dis_max` is a score-combination mechanism, not an analyzer or a distinct matching type. Each child query still retains its own semantics: `match`, `term`, `range`, or another query.

For example, all three child queries are `match` queries, so each field is analyzed with its corresponding analyzer. If a field has an incorrect mapping or unsuitable analyzer, `dis_max` cannot fix that issue.

## 3. How dis_max Calculates Scores

Suppose a document gets three scores from child queries:

| Field | Query score |
|---|---:|
| title | 8.0 |
| subtitle | 4.0 |
| description | 2.0 |

With `tie_breaker = 0`:

~~~text
score = 8.0 + 0 × (4.0 + 2.0)
      = 8.0
~~~

With `tie_breaker = 0.1`:

~~~text
score = 8.0 + 0.1 × (4.0 + 2.0)
      = 8.6
~~~

With `tie_breaker = 0.5`:

~~~text
score = 8.0 + 0.5 × (4.0 + 2.0)
      = 11.0
~~~

With `tie_breaker = 1`:

~~~text
score = 8.0 + 1 × (4.0 + 2.0)
      = 14.0
~~~

General formula:

\[
S_{\text{dis\_max}} = S_{\max} + t \sum_{i \ne \max} S_i
\]

Where:

- S_i is the score of the i-th child query.
- S_max is the highest score among matching child queries.
- t is `tie_breaker`, typically in the range 0 to 1.

If only one child query matches, `tie_breaker` does not change the score because there are no secondary scores to add.

## 4. How Does tie_breaker Affect Ranking?

`tie_breaker` controls how much non-maximum child queries contribute.

| tie_breaker | Combination Behavior | Meaning |
|---:|---|---|
| 0 | Takes only the highest score | The best-matching field determines the rank |
| 0.1 | Adds 10% of the remaining child scores | Recognizes multi-field matches while still favoring the best field |
| 0.3 | Adds 30% of secondary scores | Matching across multiple fields has clearer impact |
| 0.5 | Adds half of secondary scores | More balanced between strongest match and matches in other fields |
| 1 | Adds all secondary scores | Score approaches the sum of matching child queries |

The default `tie_breaker` for `dis_max` is 0 if unspecified.

### 4.1. Example Comparing Two Documents

Searching for `wireless mouse` with two documents:

| Document | title | description |
|---|---:|---:|
| A | 8.0 | 0.0 |
| B | 6.0 | 5.0 |

With `tie_breaker = 0`:

- A scores 8.0.
- B scores 6.0.
- A ranks above B.

With `tie_breaker = 0.5`:

- A scores 8.0.
- B scores 6.0 + 0.5 × 5.0 = 8.5.
- B can rank above A.

Thus `tie_breaker` can flip rankings. Choose a value based on how your product wants to evaluate relevance, then validate with a query set and real expected results.

### 4.2. tie_breaker Is Not Field Boost

These two settings solve different problems:

- Field boost changes the importance of a field or child query.
- `tie_breaker` determines how much of the score from additional matching child queries gets added to the maximum score.

Both can be used together. For example, `title` has a high boost, with a small `tie_breaker` to reward documents that also match in `description`.

## 5. Using dis_max with Field Boosts

Field boosts allow prioritizing a field. Boost syntax in Query DSL is typically expressed with a caret in a field list or with the `boost` property on a query.

Example:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "subtitle": {
              "query": "wireless mouse",
              "boost": 2
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.15
    }
  }
}
~~~

Meaning:

- `title` is boosted 4x via the query's boost factor.
- `subtitle` is boosted 2x.
- `description` keeps the default boost of 1.
- `tie_breaker` 0.15 lets other fields contribute a small fraction when also matched.

Boost multiplies the corresponding query's score, and then `dis_max` combines the adjusted scores. The final score still depends on query, analyzer, term statistics, mapping, and actual data; boost cannot be understood as a fixed additive bonus.

### 5.1. Boost Is Not a Probability Percentage

A boost of 4 does not mean the document is four times as relevant or has four times the probability of being right. It is an internal ranking score influence factor.

Do not compare scores across two different queries as absolute probabilities. Use scores to rank within the same query and verify results on a representative dataset.

## 6. How Does Combining Queries with dis_max Differ from bool should?

Both `dis_max` and `bool` `should` can express OR choices, but their scoring rules differ.

### dis_max

With `dis_max`, the highest score dominates, and remaining scores contribute only via `tie_breaker`:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

### bool should

With a `bool` query having multiple `should` clauses, the scores of matching clauses are typically summed:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

| Characteristic | dis_max | bool.should |
|---|---|---|
| Match logic | OR across child queries | OR across should clauses, per minimum_should_match |
| Score when multiple clauses match | Max + tie_breaker × sum of remaining scores | Usually sums scores of matching clauses |
| Strongest field | Clearly dominates | Can be overtaken by the sum of multiple weaker fields |
| Control over minimum clauses matched | No direct minimum_should_match on dis_max | Has minimum_should_match |
| Typical use case | A very strong match in one field matters more than weak matches across many fields | Wanting multiple matching signals to contribute strongly to the score |

### 6.1. When to Use bool.should?

Use `bool.should` when multiple matching signals represent cumulative evidence of relevance.

For example:

- Product name matches.
- Brand matches.
- Category matches.
- An important tag matches.

If you want more matching signals to push the document higher, `bool.should` is usually appropriate.

### 6.2. When to Use dis_max?

Use `dis_max` when fields are alternative places to find the same information, and a strong match in the most important field should dominate.

For example, searching a person's name across `firstName` and `fullName`. If a document matches strongly on `fullName`, you do not necessarily want to sum the full score of `firstName` as an independent signal.

## 7. multi_match and the best_fields Type

Elasticsearch provides `multi_match` to run the same query across multiple fields. With `type` set to `best_fields`, Elasticsearch builds logic roughly equivalent to `dis_max` over the specified fields.

Example:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "best_fields",
      "fields": [
        "title^4",
        "subtitle^2",
        "description"
      ],
      "tie_breaker": 0.15
    }
  }
}
~~~

In this example:

- The same query string is applied across multiple fields.
- `title` is prioritized with boost 4.
- `subtitle` is prioritized with boost 2.
- `best_fields` picks the best score as the primary component.
- `tie_breaker` lets the remaining fields contribute extra score.

When fields share compatible analysis styles, `multi_match` `best_fields` is a concise way to express multi-field search using `dis_max` principles.

### 7.1. best_fields and operator

Example:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "best_fields",
      "fields": ["title", "description"],
      "operator": "and"
    }
  }
}
~~~

With `best_fields`, the `operator` condition applies within each per-field query. Therefore, a document with `wireless` in `title` and `mouse` in `description` may fail to match if no single field contains all tokens required by AND.

If tokens need to span across different fields, consider `cross_fields`.

## 8. Distinguishing best_fields, most_fields, and cross_fields

`multi_match` has several types with different semantics:

| Type | Combination Method | When Suitable |
|---|---|---|
| best_fields | Favors field with best score, via dis_max logic | One field typically contains most of the relevant content |
| most_fields | Sums scores from multiple fields | Multiple analyses of the same content contribute together |
| cross_fields | Processes term-by-term across fields with compatible analyzers | Query words can appear in different fields |
| phrase | Searches for phrase in each field | Requires token order/proximity within a field |
| phrase_prefix | Searches for phrase with final token as prefix | Phrase auto-completion suggestions |
| bool_prefix | Searches by tokens with prefix on the final token | Search-as-you-type in certain designs |

### 8.1. best_fields

Use when a single field should contain most of the query:

~~~http
POST /people/_search
{
  "query": {
    "multi_match": {
      "query": "Will Smith",
      "type": "best_fields",
      "fields": ["firstName", "lastName", "fullName"]
    }
  }
}
~~~

A document whose `fullName` matches the whole phrase can receive a high score. `best_fields` fits when fields are alternatives rather than pieces that must be combined.

### 8.2. most_fields

`most_fields` adds scores from matching fields. It is useful when the same content is stored across multiple fields with different analyzers or representations.

For instance, a product name has a standard `title` field, `title.shingles`, and `title.stemmed`. These fields represent different analytical views of the same content:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "type": "most_fields",
      "fields": [
        "title",
        "title.shingles",
        "title.stemmed"
      ]
    }
  }
}
~~~

Scores from the fields are summed to rank documents matching across multiple analyses higher. This differs from `dis_max`, where the highest-scoring field dominates.

### 8.3. cross_fields

`cross_fields` fits when parts of the query may reside in different fields.

For example, a user searches for `Will Smith`, while the data is stored separately:

~~~json
{
  "firstName": "Will",
  "lastName": "Smith"
}
~~~

Using `best_fields` with operator AND can require both tokens to appear in the same field, causing no match. `cross_fields` processes in a term-centric manner across fields with compatible analyzers:

~~~http
POST /people/_search
{
  "query": {
    "multi_match": {
      "query": "Will Smith",
      "type": "cross_fields",
      "fields": ["firstName", "lastName"],
      "operator": "and"
    }
  }
}
~~~

`cross_fields` has requirements on analyzers and field grouping. Fields with different analyzers may be placed into separate groups, causing semantics to differ from expectations. Check the mapping/analyzer of each field before choosing this type.

### 8.4. Choosing a Type Based on Data Structure

- Data repeated across fields with different analyses: consider `most_fields`.
- Alternative fields where the best field should decide: `best_fields`.
- A single query distributed across component fields: `cross_fields`.
- Need custom queries per field and explicit scoring rules: direct `dis_max`.

## 9. Nesting dis_max Inside a bool Query

`dis_max` can be one branch inside a `bool` query. This is useful when you want multi-field max-score search while applying business filters.

Example:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "dis_max": {
            "queries": [
              {
                "match": {
                  "title": {
                    "query": "wireless mouse",
                    "boost": 4
                  }
                }
              },
              {
                "match": {
                  "description": "wireless mouse"
                }
              }
            ],
            "tie_breaker": 0.1
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

Here:

- `dis_max` combines scores of `title` and `description`.
- `must` requires documents to match `dis_max`.
- `filter` narrows results by `active` and `category` without adding relevance score.
- Filters do not alter the ranking order determined by `dis_max` scores.

This is a common pattern in product search: the full-text part decides relevance, while status and category act as filter conditions.

## 10. Building dis_max with Spring Data Elasticsearch NativeQuery

With Spring Data Elasticsearch 5.x using the Elasticsearch Java API Client, `NativeQuery` can accept the client's query type.

Example building child queries:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query titleQuery = Query.of(q -> q
    .match(m -> m
        .field("title")
        .query("wireless mouse")
        .boost(4.0f)
    )
);

Query descriptionQuery = Query.of(q -> q
    .match(m -> m
        .field("description")
        .query("wireless mouse")
    )
);

Query disMaxQuery = Query.of(q -> q
    .disMax(d -> d
        .queries(List.of(titleQuery, descriptionQuery))
        .tieBreaker(0.1)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(disMaxQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

In the example:

- `Query` is `co.elastic.clients.elasticsearch._types.query_dsl.Query`.
- `NativeQuery` is `org.springframework.data.elasticsearch.client.elc.NativeQuery`.
- `queries(...)` accepts a list of child queries.
- `tieBreaker(0.1)` sets the contribution of secondary scores.
- `boost(4.0f)` prioritizes `title`.

This example follows the Spring Data Elasticsearch 5.x and Elasticsearch Java API Client generation. Package names, builder methods, and boost numeric types must match the minor version in your project. Do not mix Criteria API `Query` with Elasticsearch Java API Client `Query`.

## 11. Using multi_match in NativeQuery

If the same string is searched across multiple fields and `best_fields` is desired, `multi_match` can be shorter to write than manual `dis_max`.

Example with Elasticsearch Java API Client:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query multiMatchQuery = Query.of(q -> q
    .multiMatch(m -> m
        .query("wireless mouse")
        .fields(List.of(
            "title^4",
            "subtitle^2",
            "description"
        ))
        .type(TextQueryType.BestFields)
        .tieBreaker(0.15)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(multiMatchQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Elasticsearch Java API Client builder syntax may vary across versions. If your IDE does not recognize `TextQueryType` or the `fields`/`type`/`tieBreaker` methods, check the Javadoc of your actual dependency and use that version's enum/type.

### 11.1. When Should You Write dis_max Manually Instead of multi_match?

Use `multi_match` when:

- The same query string applies to multiple fields.
- You need field boosts.
- You want `best_fields` or another `multi_match` type.

Write `dis_max` manually when:

- Each field needs a different child query.
- Fields need separate analyzers, operators, or conditions.
- One branch uses `match`, while another uses `term`/`prefix`/`fuzzy`.
- You want to combine child queries beyond full-text on the same string.

Example where `title` uses `match_phrase` while `description` uses `match`:

~~~http
POST /products/_search
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match_phrase": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

`multi_match` is not a direct drop-in replacement for every such combination of child queries.

## 12. Understanding Per-Field Scores

A `match` query's score is typically based on the BM25 algorithm configured in Elasticsearch. Influencing factors include:

- Term frequency in the document.
- Term rarity across the document collection.
- Field length and length normalization.
- Analyzers and generated tokens.
- Query boosts and related factors.

Therefore, `title` and `description` scores do not depend solely on the number of matching words. A rare term in `title` may score differently from the same term in `description` due to statistics and field length.

When using `dis_max`, do not assume `title` will always score higher than `description` merely because `title` is short. If `title` must be prioritized for business reasons, set a boost and verify the actual results.

### 12.1. Field Length and Repeated Content

`description` is typically longer than `title`. BM25 has length normalization, yet a long field can still contain many matching signals. If you sum scores from every field via `bool.should` or `most_fields`, repeated content can inflate a document's score.

`dis_max` mitigates this cumulative effect by adding only a fraction of secondary scores. However, it does not eliminate all effects of field length, term statistics, or analyzers.

## 13. Debugging Rankings with the Explain API

When a document lands in the wrong position, inspect where its score came from rather than guessing `tie_breaker`.

Elasticsearch Explain API:

~~~http
GET /products/_explain/P-1001
{
  "query": {
    "dis_max": {
      "queries": [
        {
          "match": {
            "title": {
              "query": "wireless mouse",
              "boost": 4
            }
          }
        },
        {
          "match": {
            "description": "wireless mouse"
          }
        }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

Explain returns information explaining why a document matched or did not match and what components contributed to its score. You can inspect:

- Which child queries matched.
- The score of each branch.
- How boosts were applied.
- The secondary score portion from `tie_breaker`.
- Which terms contributed points.

The Search API also supports `explain: true` to fetch explanation info for every hit:

~~~http
POST /products/_search
{
  "explain": true,
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "tie_breaker": 0.1
    }
  }
}
~~~

Explain can produce large responses and is expensive. Enable it only when debugging a few documents or in test environments; do not turn it on broadly for all production requests.

### 13.1. Profile API

The Profile API provides detailed information about query execution time on shards. It is useful when investigating performance, though it adds overhead and is not an accurate tool for measuring production latency.

Example:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "dis_max": {
      "queries": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ]
    }
  }
}
~~~

Use Explain to understand scores; use Profile to study query execution structure and time. The two tools answer different questions.

## 14. Combining dis_max with filter and minimum_should_match

`dis_max` does not have a `minimum_should_match` parameter like a `bool` query. It only requires one child query to match for a document to qualify.

If business logic requires at least two out of three signals to match, use `bool.should` with `minimum_should_match`:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        { "match": { "title": "wireless mouse" } },
        { "match": { "subtitle": "wireless mouse" } },
        { "match": { "description": "wireless mouse" } }
      ],
      "minimum_should_match": 2,
      "filter": [
        { "term": { "active": true } }
      ]
    }
  }
}
~~~

If only one field needs to match while letting the highest-scoring field dominate, `dis_max` is more suitable. If you must enforce a minimum number of matching fields/signals, `bool.should` is the appropriate structure.

Note: in a `bool` query, when `must` or `filter` is present, `should` clauses usually become optional by default if `minimum_should_match` is not set. Set the value explicitly if `should` must act as a required condition.

## 15. Common Design Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Documents matching multiple fields do not rank higher | `tie_breaker` defaults to 0 | Choose `tie_breaker > 0` if multi-field matches should contribute |
| Documents with long descriptions rank too high | Summing scores across fields via `bool.should` or `most_fields` | Consider `dis_max` and field boosts |
| Title is not prioritized | `title` field is not boosted | Use `title^N` or boost the child query |
| Results matching only one word are still returned | `match` defaults to OR | Use `operator` AND or `minimum_should_match` |
| Keywords split across fields fail to match | `best_fields` with AND requires all tokens in a single field | Consider `cross_fields` |
| Scores change after adding a field | Term statistics and field/query composition changed | Use Explain and re-test ranking on a query set |
| Overly large `tie_breaker` makes rankings unpredictable | Secondary scores contribute too heavily | Lower `tie_breaker` and re-measure |
| Searching the right field yet score is low | Analyzer, mapping, or boost is unsuitable | Check mapping, Analyze API, and Explain |
| `NativeQuery` fails to compile | Mixed `Query` types/imports or different client API version | Check packages and client version |
| Search is slow | Many child queries, large fields, or shard fan-out | Limit fields, filter first, and measure Profile/metrics |

## 16. Ranking Tuning Workflow

Do not choose boosts and `tie_breaker` based on guesswork. Create a representative query set along with a list of documents expected to rank at the top.

Suggested workflow:

1. Identify which field is the most important source of information.
2. Write a baseline query using `multi_match` `best_fields` or `dis_max`.
3. Set initial boosts for key fields such as `title`.
4. Set `tie_breaker` low or leave it at default 0 to establish a baseline.
5. Run the sample query set and inspect top results.
6. Use Explain to understand why documents were ranked that way.
7. Change one factor at a time: boost, `tie_breaker`, analyzer, or query type.
8. Compare before/after rankings using suitable evaluation criteria.
9. Keep configurations that show consistent improvement across many queries, not just a single example.

Ranking evaluation metrics may include Precision@k, Recall@k, Mean Reciprocal Rank (MRR), or Normalized Discounted Cumulative Gain (NDCG), depending on search goals. If you do not yet have a relevance judgment set, collect real queries and perform structured manual evaluation.

## 17. When Should You Not Use dis_max?

`dis_max` is not the default choice for every multi-field query.

You do not necessarily need `dis_max` when:

- Independent signals should accumulate strongly to raise rank.
- Keywords must be distributed across fields like `firstName` and `lastName`.
- A minimum number of fields/signals must match.
- The query requires complex AND/OR grouping logic.
- A single field already has a mapping/structure suited for a simpler query.

Alternatives:

| Requirement | Suitable Structure |
|---|---|
| Favor the best-matching field | `dis_max` or `multi_match` `best_fields` |
| Sum scores from multiple analyses | `multi_match` `most_fields` |
| Match tokens across component fields | `multi_match` `cross_fields` |
| Sum scores from multiple independent signals | `bool.should` |
| Require at least N clauses to match | `bool.should` + `minimum_should_match` |
| Mandatory filtering without adding score | `bool.filter` |
| Adjust scores with custom rules | `function_score` or `script_score` when truly needed |

## 18. Pre-Release Checklist for Application Ranking

- Searched fields have appropriate `text`/`keyword` mappings.
- Field analyzers are well understood and consistent with query types.
- Important fields have reasonable boosts.
- `tie_breaker` is chosen based on test results.
- `dis_max` is clearly distinguished from `bool.should` and `multi_match` types.
- If AND across tokens spanning fields is needed, `cross_fields` has been evaluated.
- If a minimum number of matching signals is required, `minimum_should_match` is placed properly.
- Sample query set and expected results exist for evaluation.
- Explain has been used when needed to understand scores.
- `explain`/`profile` are not enabled broadly in production.
- Latency and load have been measured with realistic field/child-query counts.
- `NativeQuery` matches the exact Elasticsearch Java API Client version.

## 19. Quick Reference Table

| Purpose | Usage |
|---|---|
| Combine multiple queries by highest score | `dis_max` |
| Allow secondary query scores to contribute slightly | `tie_breaker` from 0 to 1 |
| Prioritize `title` over `description` | Field boost, e.g., `title^4` |
| Search the same query across fields by max score | `multi_match` `best_fields` |
| Sum scores from multiple fields | `multi_match` `most_fields` or `bool.should` |
| Search tokens spread across `firstName`/`lastName` | `multi_match` `cross_fields` |
| Require at least N signals to match | `bool.should` + `minimum_should_match` |
| Filter status without affecting score | `bool.filter` |
| Explain a single document's score | Explain API |
| Analyze query execution time | Profile API |
| Use from Java in Spring Data | `NativeQuery` + Elasticsearch Java API Client |

Disjunction max combines multiple queries by favoring the highest score while letting other child queries contribute partially through `tie_breaker`. When searching across multiple fields, choose among `dis_max`/`best_fields`, `most_fields`, `cross_fields`, and `bool.should` according to your data structure and ranking goals. Field boost expresses business importance; `tie_breaker` expresses the degree of score addition when multiple fields match. Use Explain and a representative query set to tune rankings rather than picking numbers arbitrarily.
