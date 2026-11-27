# min_score, rescore, and Conditions for Use

Elasticsearch ranks documents using a **relevance score**, typically exposed in the **_score** field. The score indicates how well a document matches the query under Elasticsearch's scoring model. When building search, you sometimes need to drop results with very low scores or refine the ordering of top results. Two features commonly used for this purpose are **min_score** and **rescore**.

The two features play different roles:

- **min_score** sets a minimum score threshold. Documents scoring below the threshold are omitted from the returned hits.
- **rescore** runs a second scoring pass over the top results from the initial query, then reorders that group using the new score.

Both are search-request-level options, not query clauses like **match**, **term**, or **range**. Choosing the right feature improves search quality while keeping execution cost under control.

This article uses the **products** index, with fields **name**, **description**, **category**, **status**, and **price**. Examples focus on product name search, data filtering, and refining result ordering.

## 1. Relevance Score in Elasticsearch

When running a scoring query, Elasticsearch calculates **_score** for each matching document. Scores typically depend on query content, term frequency, term rarity, field length, and similarity model factors.

Example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mechanical keyboard"
    }
  }
}
~~~

Part of the response might look like:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "p-1001",
        "_score": 5.8,
        "_source": {
          "name": "Wireless Mechanical Keyboard"
        }
      },
      {
        "_id": "p-1002",
        "_score": 2.1,
        "_source": {
          "name": "Wireless Mouse"
        }
      }
    ]
  }
}
~~~

The first document has a higher score because its relevance to the query is likely stronger. The numbers in this example are illustrative only; actual scores depend on mappings, analyzers, data, similarity, and query structure.

**_score is not a probability.** A score of 5.8 does not mean the document is 58% right, and there is no universal scale guaranteeing comparability across different queries. Never take a score cutoff from one query and apply it mechanically to all other queries.

When a query uses only conditions inside **bool.filter**, the goal is filtering rather than ranking. Filter clauses do not contribute to scores in the way query context does. If you need `min_score` or `rescore`, there must be a query part generating meaningful scores.

## 2. What Is min_score?

**min_score** is a search request option used to exclude hits scoring below a specified threshold.

Example returning only documents scoring 2.0 or higher:

~~~http
POST /products/_search
{
  "min_score": 2.0,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

In this example:

- Elasticsearch runs a `match` query on the `name` field.
- Documents are scored against the query.
- Documents scoring below 2.0 are excluded from the returned hits.
- Documents scoring equal to or above the threshold can be returned if they meet other conditions.

**min_score lives at the search request level**, alongside **query**, **from**, **size**, **sort**, and **aggs**. Do not place it inside a `match` or `bool` object.

Structurally incorrect example:

~~~json
{
  "query": {
    "bool": {
      "min_score": 2.0,
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

Correct example:

~~~json
{
  "min_score": 2.0,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

### How Does min_score Differ from filter?

Filters typically check data attributes like category, status, price, or time. `min_score` checks the relevance score computed by the query.

Example filtering active products in the accessories category with a matching name and a minimum score:

~~~http
POST /products/_search
{
  "min_score": 1.5,
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
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 200
            }
          }
        }
      ]
    }
  }
}
~~~

In this query:

- **must** forms the scored search portion.
- **filter** excludes products that fail the status, category, or price range checks.
- **min_score** drops hits whose relevance score falls below the threshold.

If you only need to filter products by `status` or `price`, use `filter`. Do not use `min_score` to replace a business rule that can be expressed with `term` or `range`.

## 3. When Should You Use min_score?

`min_score` is useful when an application wants to drop very weakly relevant results after a scored search.

Some use cases:

- Keyword product search, showing only results meeting a minimum relevance level.
- Searching articles, docs, or questions, removing weak matches.
- Multi-keyword queries requiring results to meet a sufficiently high match quality.
- Reducing noise on the results page when a broad query yields many low-relevance hits.

For example, a user searches for **"mechanical keyboard"**. The query might return documents containing only `mechanical` or only `keyboard`. If the application wants to show only results meeting a score cutoff, `min_score` can help prune weak hits.

However, `min_score` does not understand business meaning. It only compares numerical scores. A business-critical product might score low due to how analyzers, data, or queries are configured. Therefore, evaluate on a real query set before putting a threshold into production.

### When You Should Not Use min_score

Avoid `min_score` when:

- The query contains only filters and has no meaningful scoring part.
- The condition can be expressed exactly with `term`, `range`, or `exists`.
- You need to guarantee a field has a specific value.
- You want to limit the number of results; use `size`.
- You want to order by price or date; use `sort`.
- You want to exclude documents by business rules; use the appropriate query/filter.

An arbitrary score threshold can drop valid results. If a query's scores shift with content or corpus changes, the same document might pass the cutoff on one query and fail it on another.

## 4. Cost and Limitations of min_score

`min_score` requires a score to compare against. Hence, Elasticsearch must perform scoring on matching documents before deciding whether to keep or drop them. On large datasets, `min_score` can be more expensive than a simple filter query.

Things to consider:

- `min_score` does not replace filter context.
- Queries matching many documents still compute scores for comparison against the cutoff.
- Score cutoffs depend on the query and underlying data.
- Changing analyzers, similarity, boosts, or query structure shifts score distributions.
- When combined with `rescore`, verify actual behavior in your Elasticsearch version and evaluate thresholds against the final score.
- Do not set `min_score` overly high just to trim hit counts without checking recall.

**Recall** is the ability to retain genuinely relevant documents. If the cutoff is too high, relevant documents can be dropped. **Precision** is the proportion of returned results that are truly relevant. Raising `min_score` can improve precision on some datasets, but often risks lowering recall.

Evaluate both metrics using a representative query set and relevance labels rather than picking a cutoff from a handful of examples.

## 5. What Is rescore?

**Rescore** is a second scoring pass over a top subset of documents from the initial query. The idea is to use a fast, broad query to gather candidates, then run a more accurate or expensive query to refine the ranking within that candidate group.

Example:

- The first query finds products containing **wireless** or **keyboard**.
- Rescore runs `match_phrase` to favor names containing the phrase **wireless keyboard** in close proximity.
- The new score is combined with the initial score.
- Elasticsearch reorders the rescored group.

Rescore is not a standalone search query replacing the initial query. It is an extra stage inside a search request.

General flow:

~~~text
Search request
      |
      v
Initial query
      |
      v
High-scoring candidate set
      |
      v
Bounded by window_size per shard
      |
      v
Rescore query runs on candidate group
      |
      v
Combine old and new scores
      |
      v
Reorder results
      |
      v
Return paginated hits
~~~

Documents outside the rescore window are not rescored. Thus, rescore can only reorder candidates already selected in the first pass; it cannot pull a document ranked far down initially into the top group if it falls outside the window.

## 6. Query Rescorer: Basic Example

A request can run an initial `match` query and a `match_phrase` in the rescore stage:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mechanical keyboard",
        "operator": "or"
      }
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless mechanical keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 0.2,
      "rescore_query_weight": 2.0
    }
  }
}
~~~

Meaning:

- **query** at the request level is the initial query, producing the candidate pool and first score.
- **rescore** declares the rescoring pass.
- **window_size** caps how many documents are considered for rescoring per shard.
- **rescore_query** is the second query, here favoring phrase proximity.
- **query_weight** scales the initial score's influence.
- **rescore_query_weight** scales the rescore query's score influence.

In this example, the rescore query carries greater weight, so phrase-matching documents can rise higher. The numbers are illustrative only; tune them via real relevance evaluation.

### Why Use Two Stages?

The first query can be optimized for broad candidate recall. The rescore query can be heavier and execute only on a small group, improving precision without paying the high cost across all matching documents.

For example, a `match` query across multiple keywords captures enough relevant products. `match_phrase` in the rescore stage favors products whose names contain the exact or near-exact phrase.

## 7. window_size and Rescore Scope

**window_size** specifies how many top documents per shard enter the rescore pass. Larger values rescore more candidates, increasing processing cost.

Example:

~~~json
{
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      }
    }
  }
}
~~~

If each shard has many matching documents, Elasticsearch only rescores candidates within the configured window. A document initially ranked outside the window cannot be promoted to the top by rescore because the second query never runs on it.

Practical guidelines:

- Set `window_size` large enough to cover candidates likely to need reordering.
- A large window raises the cost of the second query.
- An overly small window can miss relevant documents that ranked low initially.
- Rescore applies per shard, so total rescored candidates across the cluster can exceed `window_size`.
- When paginating, keep `window_size` consistent across requests in the same search flow.
- When using `from`/`size`, `window_size` must be large enough to cover the result slice the application expects to be rescored; hits beyond the window will not have been recomputed.

For instance, if page one has `size` 20 while `window_size` is only 10, part of the returned hits may lie outside the rescore window. Choose `window_size` to fit `from + size` and the candidate pool you wish to rerank.

Do not set `window_size` equal to the total document count in the index. Rescore is designed to refine the top group, not re-run a second query over the entire dataset.

## 8. Combining Scores in Query Rescorer

The query rescorer combines the initial query score with the rescore query score. Two weights are commonly used:

- **query_weight**: weight for the initial score.
- **rescore_query_weight**: weight for the rescore query score.

With the default **total** score mode, the general calculation is:

\[
\text{final score} =
(\text{query score} \times \text{query weight}) +
(\text{rescore score} \times \text{rescore query weight})
\]

Example:

~~~json
{
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 3.0,
      "score_mode": "total"
    }
  }
}
~~~

Here, the `match_phrase` score carries more weight than the initial query score. Documents matching the phrase stand a better chance of ranking higher.

Elasticsearch supports score combination modes such as:

| score_mode | Meaning |
|---|---|
| **total** | Adds weighted scores |
| **multiply** | Multiplies weighted scores |
| **avg** | Averages weighted scores |
| **max** | Picks the larger score |
| **min** | Picks the smaller score |

Check the documentation for your exact Elasticsearch version because supported rescorer types and options can vary. Do not pick `score_mode` by name alone; verify its impact on a real dataset.

If the rescore query does not match a document, score combination still depends on `score_mode` and query behavior. Use `explain` or `profile` when you need to understand why a document landed at a specific rank.

## 9. When Should You Use rescore?

Rescore fits when the initial query already retrieves a solid candidate set, yet the top ordering needs refinement using a costlier search criterion.

Typical scenarios:

- Phrase search: prefer documents where words appear close together in order.
- Product search: prefer product names matching an exact phrase over descriptions containing scattered words.
- Document search: run a broad query to gather candidates, then a phrase or specialized query to rank top hits.
- Multi-field search: initial query searches title and description; rescore boosts phrase matches in title.
- Relevance tuning: refine top results without paying for an expensive query across the whole dataset.

Example where the initial query searches both `name` and `description`:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wireless mechanical keyboard",
      "fields": [
        "name^3",
        "description"
      ],
      "type": "best_fields"
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless mechanical keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 2.5
    }
  }
}
~~~

The initial query finds terms across multiple fields, while rescore favors product names containing the phrase in proximity. This creates a two-tier relevance pipeline.

## 10. When Should You Not Use rescore?

Rescore is not suited to every query.

Avoid using it when:

- The query is purely a filter on `status`, `category`, or `range`.
- There is no second query likely to improve relevance.
- The candidate set is small and the initial query is already sufficient.
- You want to change which documents are allowed to appear; modify the initial query instead.
- You want to score every matching document; consider `function_score` or appropriate query design.
- You want to sort by business fields like price, time, or quantity; use `sort`.
- You want to drop hits below a score cutoff; use `min_score` if scores are meaningful.
- You want the second query to run on all results; rescore is bounded by `window_size`.

Rescore also does not replace proper analyzer, mapping, or initial query design. If the first query misses a document entirely, rescore cannot bring it into results because it never became a candidate.

## 11. Distinguishing min_score, rescore, function_score, and sort

These features all affect search results, yet address different requirements.

| Feature | Role | Scope of Impact |
|---|---|---|
| **min_score** | Drops hits scoring below a cutoff | Filters hits by score |
| **rescore** | Recomputes scores and reorders top candidates | Top `window_size` documents per shard |
| **function_score** | Combines query score with business scoring functions | Document set matching the query |
| **sort** | Orders by score or data fields | Order of returned hits |
| **bool.filter** | Filters by data conditions | Eligible document set; no score from filter clauses |

### min_score and rescore

`min_score` asks: "Is the document's score high enough to keep?"

`rescore` asks: "Among the top candidates, which documents should rank higher after evaluating additional criteria?"

Both can be used in a single search request, provided you evaluate the cutoff against the final score and your cluster version's behavior. Never assume `rescore` will always rescue a document dropped by `min_score` regardless of evaluation order.

### Rescore and function_score

**function_score** alters scoring across all documents matching the query, such as boosting by popularity, freshness, or numeric values. It fits when business scores should influence results broadly.

**rescore** refines only the top candidate group with a second query. It fits when an expensive criterion only needs to run on top results.

For example, `function_score` can boost popular products via a `popularity` field; `rescore` can boost exact phrase matches on product names. Both techniques can be combined if justified, with each tier serving a distinct goal.

### Rescore and sort

Rescore alters scores. If a request specifies a field sort such as `price` or `createdAt`, the final order is determined by that sort field; changing the score may not change the order. Rescore is usually most helpful when results are ordered by relevance score.

If you want lowest-priced products first, sort by `price`. If you want more relevant documents first, use a scoring query and optionally add `rescore`. Do not use `rescore` to replace an explicit sort rule.

## 12. Combining rescore with filter

Rescore should only refine documents that already passed the initial query. Business constraints belong in the query/filter before rescoring.

Example searching only ACTIVE products in the accessories category with matching names:

~~~http
POST /products/_search
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
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": {
            "query": "wireless keyboard",
            "slop": 1
          }
        }
      },
      "query_weight": 1.0,
      "rescore_query_weight": 2.0
    }
  }
}
~~~

Filters eliminate ineligible products right in the initial query. Rescore evaluates only results meeting business criteria and refines the top ordering.

This design is far cleaner than trying to use `min_score` to drop non-ACTIVE products or using a rescore query to replace a category condition.

## 13. Using min_score in Spring Data Elasticsearch

Spring Data Elasticsearch offers the **Query** abstraction to hold search settings. Depending on version, query objects may provide a **minScore** property. Example with `CriteriaQuery`:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = Criteria.where("name")
        .matches("wireless keyboard");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setMinScore(1.5f);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

This example demonstrates setting a score cutoff on the Query abstraction. Check the **setMinScore** signature or corresponding builder in your project's Spring Data Elasticsearch version; some versions provide alternative APIs or set the option on `NativeQuery` builders.

With `NativeQuery` in Spring Data Elasticsearch 5.x, you can build queries using the Elasticsearch Java API Client and attach supported search options:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("wireless keyboard")))
        .withMinScore(1.5f)
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Builder names and the numeric type of **withMinScore** depend on version. Use the dependency managed by Spring Boot and verify the available API in your project before applying.

If the Query abstraction lacks a required option, you can invoke the Elasticsearch Java API Client directly for full control over `SearchRequest`.

## 14. Using rescore via the Elasticsearch Java API Client

Rescore is a search-request-level option. When the Spring Data abstraction in your version lacks a convenient way to configure rescore, use **ElasticsearchClient** from the Elasticsearch Java API Client to build a `SearchRequest`.

The example below shows an initial query, rescore query, and `min_score` threshold in one request:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .query(q -> q.match(m -> m
                .field("name")
                .query("wireless mechanical keyboard")))
        .minScore(1.5)
        .rescore(r -> r
                .windowSize(100)
                .query(rq -> rq
                        .rescoreQuery(q -> q.matchPhrase(mp -> mp
                                .field("name")
                                .query("wireless mechanical keyboard")))
                        .queryWeight(1.0)
                        .rescoreQueryWeight(2.0)
                )
        )
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

In this example:

- **query(...)** defines the initial query.
- **minScore(1.5)** sets the request's score cutoff.
- **rescore(...)** declares the rescoring pass.
- **windowSize(100)** caps rescored candidates per shard.
- **rescoreQuery(...)** uses `match_phrase` to prioritize phrase matches.
- **queryWeight(...)** and **rescoreQueryWeight(...)** tune the balance between both scores.
- **search(request, Product.class)** executes the request and maps `_source` to `Product`.

Use an Elasticsearch Java API Client compatible with your cluster and Spring Boot version. Generated builders, data types, and overloads can change across client versions. If the code does not compile, check the actual dependency API instead of mixing legacy `RestHighLevelClient` snippets with the new Java API Client.

In Spring Boot applications, the client is normally configured as a bean. Never create a new client per request. Inject the configured bean into a service or dedicated search component.

## 15. Inspecting Scores and Rescore While Debugging

When result ordering does not match expectations, inspect both the initial query and the rescore query.

Useful tools:

### Inspecting Hit Scores

The search response includes **_score** for each hit. Compare scores among top documents to see why ranks differ.

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

### Using explain

The **_explain** API explains why a document matched a query and how its score was computed:

~~~http
GET /products/_explain/p-1001
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Explain helps understand the initial query. When investigating `rescore`, compare behavior before and after adding rescore, and inspect the actual request and hit scores.

### Using profile

You can enable **profile: true** to view detailed execution breakdowns:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "rescore": {
    "window_size": 100,
    "query": {
      "rescore_query": {
        "match_phrase": {
          "name": "wireless keyboard"
        }
      }
    }
  }
}
~~~

Profile adds overhead and creates large responses. Enable it only when investigating performance, not by default on every production request.

### Evaluating min_score Thresholds with Real Data

To pick a threshold, prepare a representative query set with labeled relevant results. Test multiple `min_score` values and record:

- Remaining hit count.
- Precision and recall.
- Rate of queries returning zero results.
- Relevant documents that got dropped.
- Score stability across query groups.
- Impact when changing analyzers, mappings, or query boosts.

A threshold suited to product names may fail for long descriptions or multi-word queries. If you serve multiple query classes, consider per-class scoring policies instead of a single global cutoff.

## 16. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `min_score` drops all results | Threshold too high or query produces low scores | Check actual scores, lower threshold, and evaluate recall |
| `min_score` has no expected effect | Query sits mainly in filter context or produces no meaningful score | Use a scoring query or filter by data conditions |
| Scores shift across queries | Scores depend on query, analyzer, corpus, and similarity | Avoid a global cutoff without evaluation |
| Rescore does not change order | Rescore query fails to differentiate candidates or weight is too low | Check rescore query, scores, and weights |
| Desired document is not promoted | Document lies outside `window_size` | Increase window reasonably or improve the initial query |
| Rescore increases latency | Window too large or second query is expensive | Shrink window and simplify the rescore query |
| Pagination order is unstable | `window_size` changes across requests or sort is unstable | Keep `window_size` consistent and use an appropriate tie-breaker sort |
| Rescore does not affect ordering | Request sorts by a field like `price` | Sort by score when relevance is the goal |
| Initial query misses the document | Rescore runs only on initial candidates | Improve the initial query and mappings |
| Java API fails to compile | Builder signatures differ across client versions | Check dependency and API signatures for your exact version |

## 17. Workflow for Choosing min_score and rescore

When designing search ranking, follow this sequence:

1. **Define business conditions.** Use `term`, `range`, and `bool.filter` to exclude ineligible data.
2. **Build a scoring query.** Use `match`, `multi_match`, or a query suited to the language and mapping.
3. **Evaluate initial results.** Inspect top hits and scores before adding cutoffs or rescore.
4. **Consider min_score.** Use only if a relevance cutoff is sufficiently stable and verified.
5. **Consider rescore.** Use when a second query can improve the ordering of top candidates.
6. **Choose window_size.** Wide enough to cover hits needing reranking, yet not overly large.
7. **Tune weights.** Test `query_weight` and `rescore_query_weight` on labeled relevance data.
8. **Check pagination and sorting.** Ensure windows and result ordering stay consistent.
9. **Measure performance.** Use profile, slow logs, and application metrics.
10. **Monitor after release.** Track zero-result rates, latency, and user feedback.

`min_score` and `rescore` solve two different problems. **min_score** keeps hits meeting a score threshold; **rescore** refines the ranking of a candidate pool using a second query. Data conditions still belong in queries/filters, and ordering by business attributes belongs in `sort`. Only apply score cutoffs and rescoring once you understand how scores are generated, what the window covers, and how result quality holds up on real queries.
