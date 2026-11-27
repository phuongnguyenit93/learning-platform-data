# Sorting by _score and Conditions That Preserve Relevance Scoring

Elasticsearch not only finds documents matching criteria, but also computes a relevance score to rank results. For full-text search, this score is typically calculated with BM25 and reflects how closely a document's content matches the query.

When the Search API does not declare a sort, Elasticsearch defaults to sorting by _score descending: higher-scoring documents come first. However, adding a sort by a field such as price, createdAt, or name changes that order. If you want to keep relevance as a priority factor, you need to place _score in the sort list at the right position and structure the query so that filtering conditions do not inadvertently discard relevance scoring.

This lesson explains how to sort by _score, combine scores with business criteria, distinguish query context from filter context, use track_scores, handle stable tie-breakers, and paginate. The Java examples use NativeQuery with the Elasticsearch Java API Client; builder details should be checked against the Spring Data Elasticsearch version in your project.

## 1. What Is _score?

_score is the numerical score Elasticsearch assigns to a document matching a query. A higher score generally indicates the document is more relevant to the query within that search execution.

Example product search:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Some documents might be ranked as follows:

| Document | Name | Illustrative _score |
|---|---|---:|
| P-1001 | Wireless Mouse | 4.8 |
| P-1002 | Wireless Gaming Mouse | 4.1 |
| P-1003 | Mouse for Wireless Office Setup | 2.7 |

The numbers above are illustrative only. Actual scores depend on analyzers, term statistics, field length, query boosts, query structure, and index data.

For full-text queries, Elasticsearch typically uses BM25. Factors influencing score include:

- Which query terms appear in the document.
- Term rarity across the document collection.
- Term frequency within the field.
- Field length and length normalization.
- Which tokens the analyzer produces.
- Boosts and which query clauses participate in scoring.

Do not treat _score as a probability that a document is correct. Scores are primarily meant for ranking results within the same query.

## 2. Default Ordering When No Sort Is Declared

If the Search API specifies no sort, Elasticsearch sorts by _score descending. For example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

This is equivalent in intent to declaring:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "_score": {
        "order": "desc"
      }
    }
  ]
}
~~~

You can declare _score desc explicitly so readers see the intended order. When no explicit sort is needed, you do not need to add this configuration solely to achieve default behavior.

### 2.1. Equal Scores

Multiple documents can have the exact same _score. Without a secondary criterion, the order among tied documents should not be considered stable. Order may change after a refresh, segment merge, shard change, or another query execution.

If the application paginates or needs a repeatable stable order, add a secondary field with unique, sortable values, such as id.keyword:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "id.keyword": { "order": "asc" } }
  ]
}
~~~

Here relevance remains the first priority. id.keyword only determines the order among documents with equal scores.

Elasticsearch does not support direct sorting on the _id metadata field in the standard way across many configurations; store a copy of the ID in a keyword field with doc values if needed as a tie-breaker. Check the actual mapping of the secondary field.

## 3. Why Sorting by a Field Can Override Relevance Priority

Suppose an application wants to find products related to a keyword and prioritize lower prices. Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

Results are sorted by price ascending. The cheapest product appears first, even if that document has a lower _score.

This is not an Elasticsearch bug. The sort array defines the priority order of sort keys. When priceInCents is specified first, price is the primary ranking criterion.

If you want relevance to come first and price to only break ties among equal-score results, declare:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": { "order": "desc" } },
    { "priceInCents": { "order": "asc" } },
    { "id.keyword": { "order": "asc" } }
  ]
}
~~~

The order means:

1. _score descending.
2. If scores are equal, price ascending.
3. If both score and price are equal, ID ascending.

Do not place price before _score if the business requirement is to prioritize relevance.

## 4. Query Context and Filter Context

This is the most important point when preserving relevance scores.

Elasticsearch has two fundamental contexts:

- **Query context** evaluates how well a document matches and calculates _score.
- **Filter context** only checks whether a document satisfies a condition. Filter conditions do not contribute to _score and can be cached when appropriate.

In a bool query:

| Clause | Role | Contributes to _score? |
|---|---|---|
| must | Required condition | Yes |
| should | Optional condition or required per minimum_should_match | Yes |
| filter | Required yes/no condition | No |
| must_not | Excludes documents from results | No |

Example finding products by name while restricting to active products in the accessories category:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
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

match is in must, so it computes relevance. active and category are in filter, so they only narrow the result set without altering relevance scores.

This structure is typically suitable for product search: full-text determines relevance, while status, tenant, category, and price range act as filter conditions.

### 4.1. Do Not Put the Entire Full-Text Query in filter If _score Is Needed

For example:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ]
    }
  }
}
~~~

Documents are still filtered by match, but the clause runs in filter context and thus does not produce standard relevance scores. If you subsequently sort by _score, results have no useful distinguishing score from this query.

If ranking by text match quality is needed, put match in must or should. Use filter for conditions meant solely to exclude non-matching documents.

### 4.2. Filter Conditions Do Not Erase Scores from must

You can combine multiple filters with a must clause:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "ergonomic wireless mouse"
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
          "range": {
            "priceInCents": {
              "gte": 100000,
              "lte": 800000
            }
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "visibility": "HIDDEN"
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

The score comes from match in must. The filter and must_not clauses narrow results without adding to or subtracting from relevance scores.

## 5. should and minimum_should_match

A should clause can both help match documents and contribute to score. However, there is an easily misunderstood default rule:

- If bool only has should and no must/filter, by default at least one should clause must match.
- If bool already has must or filter, should is usually optional by default (minimum_should_match defaults to 0).

For example, if product name is required while brand and category only boost scores:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "should": [
        {
          "term": {
            "brand": {
              "value": "Northwind",
              "boost": 3
            }
          }
        },
        {
          "term": {
            "category": {
              "value": "accessories",
              "boost": 1.5
            }
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Documents must match name and active=true. If they also match brand or category, their score increases. If they match neither should clause, documents are still returned because must is satisfied and should is optional.

### 5.1. When Is minimum_should_match Needed?

If business logic requires at least one should clause to match, declare it explicitly:

~~~json
{
  "bool": {
    "must": [
      { "match": { "name": "wireless mouse" } }
    ],
    "should": [
      { "term": { "brand": "Northwind" } },
      { "term": { "category": "accessories" } }
    ],
    "minimum_should_match": 1
  }
}
~~~

Then a document must match at least one of the two additional signals. If the goal is purely to boost scores when extra signals match without excluding documents, do not set minimum_should_match greater than 0.

Distinguish the two goals clearly:

- should for boosting: clauses may not match and the document is still kept.
- should for constraining: an appropriate minimum_should_match is needed.

## 6. Sorting by _score with Secondary Criteria

There are three common sorting patterns:

| Requirement | Sort |
|---|---|
| Relevance priority only | _score desc |
| Relevance first, price breaks ties on equal scores | _score desc, price asc |
| Price is primary priority, relevance breaks ties on equal prices | price asc, _score desc |
| Relevance first, newer date breaks ties on equal scores | _score desc, createdAt desc |
| Stable results across pages | _score desc and unique keyword tie-breaker |

Example of relevance first, then most recently updated date:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "updatedAt": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

If updatedAt precedes _score, the newest article ranks first regardless of relevance. Determine which business criterion is primary before ordering the sort clauses.

### 6.1. Tie-Breakers Must Be Stable and Unique

If the sort only contains _score, many hits may tie. If the sort contains _score and createdAt, two hits can still share the same score and timestamp.

Add a unique keyword field like id.keyword so the order is completely deterministic within the result set. This field needs doc values and a mapping that supports sorting.

Do not rely on accidental ordering among tied hits, especially when using from/size or search_after.

## 7. track_scores When Sorting by a Field

When sorting by a regular field such as price or date, Elasticsearch may skip calculating _score if it is not needed for sort ordering. If you still want to receive scores in results even when a field sort is primary, the Search API provides track_scores: true.

Example sorting by price while still tracking scores:

~~~http
POST /products/_search
{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

track_scores only requests computing and returning scores when sorting by fields. It does **not** turn _score into a sort criterion and does not change the priority order of the sort array.

If you want relevance to determine order, put _score into sort:

~~~json
{
  "sort": [
    { "_score": "desc" },
    { "priceInCents": "asc" }
  ]
}
~~~

If you only sort by price and enable track_scores, results remain ordered by price. The score is purely metadata that can be used for display or analysis.

## 8. Using NativeQuery to Declare Sort in Spring Data Elasticsearch

With Spring Data Elasticsearch 5.x and the Elasticsearch Java API Client, you can construct sort options and pass them to NativeQuery.

Example _score descending, ID ascending:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

SortOptions scoreSort = SortOptions.of(s -> s
    .score(sc -> sc.order(SortOrder.Desc))
);

SortOptions idSort = SortOptions.of(s -> s
    .field(f -> f
        .field("id.keyword")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(List.of(scoreSort, idSort))
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

This example uses the SortOptions type from the Elasticsearch Java API Client. NativeQuery builder method names may vary by minor version; check the Javadoc/IDE of your project's dependencies. If the builder accepts varargs instead of List, adjust to the overload present in your version.

You can add a second or third sort field:

~~~java
SortOptions priceSort = SortOptions.of(s -> s
    .field(f -> f
        .field("priceInCents")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withSort(List.of(scoreSort, priceSort, idSort))
    .build();
~~~

In this example _score remains the first criterion. Price only breaks ties among documents with the same score; ID ensures a final stable order.

### 8.1. Using Pageable and Sort

For query/repository paths that support Pageable, sort can be declared via Spring Data Sort:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("_score"),
        Sort.Order.asc("id.keyword")
    )
);
~~~

Then pass pageable into the corresponding query or repository method. Exact usage depends on the query and repository APIs of your Spring Data Elasticsearch version.

For heterogeneous sorts or Elasticsearch-specific options, NativeQuery with SortOptions is usually more expressive.

## 9. Field Sorting Can Make Score Stop Being the Ranking Factor

For example, wanting lower prices first, while still keeping scores for display:

~~~http
POST /products/_search
{
  "track_scores": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "priceInCents": "asc" },
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

The order is now:

1. Lower prices come first.
2. If prices are equal, higher scores come first.
3. If both price and score are equal, ID decides.

This is appropriate when price is the primary criterion. If the requirement is relevance first, swap the first two sort criteria.

Setting track_scores=true provides scores for viewing/displaying when sorting by fields. However, if _score is already a sort key, scores are computed for sorting; track_scores is not what makes _score the primary priority.

## 10. Preserving Relevance Score When Combining Multiple Fields

If a query searches across multiple fields, choose an appropriate way to combine scores before sorting.

Example bool query:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless mouse",
            "type": "best_fields",
            "fields": [
              "title^4",
              "subtitle^2",
              "description"
            ],
            "tie_breaker": 0.1
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        { "term": { "category": "accessories" } }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

multi_match best_fields combines relevance across fields. Bool filter applies business conditions without adding scores. Sort _score desc keeps the most relevant documents at the top.

If multi_match is placed inside filter, its score is not used for standard ranking. Place it in must or should if relevance is needed.

## 11. How Do Boost and function_score Affect Ordering?

Boost changes the score of a query or field. For example, title^4 prioritizes matches in title over unboosted fields. When sorting by _score desc, boosts directly affect the result order.

function_score allows modifying scores using functions such as field value factor, decay, or script. For example, combining relevance with document freshness:

~~~http
POST /articles/_search
{
  "query": {
    "function_score": {
      "query": {
        "match": {
          "content": "spring data elasticsearch"
        }
      },
      "functions": [
        {
          "gauss": {
            "publishedAt": {
              "origin": "now",
              "scale": "30d",
              "decay": 0.5
            }
          }
        }
      ],
      "boost_mode": "multiply"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Here function_score adjusts the query score based on publication recency. boost_mode determines how the query score and function score are combined.

function_score options have many parameters such as score_mode, boost_mode, max_boost, and min_score. Understand the semantics thoroughly before using them. A scoring function can significantly alter rankings; test with real queries and the Explain API.

If you sort by publishedAt before _score, results still prioritize timestamp over the adjusted score. function_score only affects ordering when score is used as a sort criterion.

## 12. Filter, constant_score, and Relevance Scoring

A constant_score query assigns a fixed score to every document matching a filter:

~~~http
POST /products/_search
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "active": true
        }
      },
      "boost": 1.2
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Every document satisfying the filter receives the same fixed score (scaled by boost). This is useful when you want a filter condition to produce a constant score, though it does not replace the relevance of a match query.

If a query consists solely of filters or constant_score clauses with identical boosts, many results will share the same score. Add a stable secondary sort if ordering among them matters.

In a combined search query, you can use must for match to preserve relevance and filter for yes/no conditions. There is no need to convert all filters into constant_score just to preserve scoring.

## 13. Paginating by _score

You can use from/size to fetch pages:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Next page:

~~~http
POST /products/_search
{
  "from": 20,
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Sorting with a unique tie-breaker makes the order among tied hits more stable. However, if the index changes between requests, new or updated documents can shift ordering and page boundaries.

Elasticsearch limits the total hits accessible with from/size; the common default for index.max_result_window is 10,000. Deep pagination forces Elasticsearch to track and process more results, so the limit should not be raised arbitrarily.

## 14. search_after and Stable Sorting

When deep traversal is needed, search_after lets you use the sort values of the last hit from the previous page as the starting point for the next page.

Example sort:

~~~http
POST /products/_search
{
  "size": 20,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Suppose the last hit on the first page has corresponding sort values:

~~~json
[3.72, "P-1020"]
~~~

The next page request uses those exact sort values:

~~~http
POST /products/_search
{
  "size": 20,
  "search_after": [3.72, "P-1020"],
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Guidelines:

- Keep query and sort identical across pages.
- Pass the exact sort values from the last hit of the previous page.
- Include a unique tie-breaker to avoid ambiguity when scores tie.
- Do not recompute sort values from _source.
- For datasets requiring a stable snapshot, use Point in Time (PIT) with search_after if supported by your version and API.

PIT preserves a consistent view of the index over the query duration. When using PIT, follow the sort requirements and PIT parameters for your Elasticsearch version; Elasticsearch may add _shard_doc as an internal tie-breaker in certain usages. Do not change the sort between requests.

### 14.1. Why Is a Tie-Breaker Important with search_after?

If sorting only by _score, multiple documents may share the same score. Page boundaries then lack deterministic positioning for stable pagination. Adding a unique field like id.keyword creates a total order over the hit set.

If using PIT, still use the returned sort values and preserve the sort order. Do not replace an ID or score value with one read from _source.

## 15. Total Hits Is Not _score

Distinguish two pieces of information:

- _score is the relevance score of an individual document.
- hits.total is the count of documents matching the query, which may be an exact total or a lower bound depending on configuration.

For example:

~~~http
POST /products/_search
{
  "track_total_hits": true,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

track_total_hits requests tracking the exact total number of hits. It does not control scores and does not replace track_scores.

Distinction:

| Option | Effect |
|---|---|
| sort: _score desc | Ranks documents by relevance score descending |
| track_scores: true | Tracks scores when sorting by another field |
| track_total_hits: true | Requests exact total hit count |
| minimum_should_match | Specifies minimum number of should clauses that must match |
| min_score | Excludes documents with scores below a threshold |

Do not confuse track_scores with track_total_hits. One relates to per-hit scores, and the other relates to the total hit count.

## 16. min_score and Keeping Documents with Sufficiently High Scores

min_score allows excluding documents whose _score is below a threshold:

~~~http
POST /products/_search
{
  "min_score": 1.5,
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

Documents must match the query and have a score of at least the threshold. This can be useful when excluding very weak matches.

However, scores depend on data and query structure. A threshold suitable for one query may not fit another. min_score may require scoring candidate documents and increase cost. Choose thresholds via evaluation data rather than picking an arbitrary number.

If you want to enforce constraints on content or status, prefer appropriate queries/filters. min_score is a score-filtering tool, not a replacement for business conditions.

## 17. Inspecting Ranking with the Explain API

When results do not appear in the expected positions, use Explain to see where scores come from:

~~~http
GET /products/_explain/P-1001
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Explain can help verify:

- Whether the document matches the query.
- How match clauses contribute to the score.
- How boosts are applied.
- Which queries contribute no score because they are in filter context.
- How function_score adjusts the score.

The Search API can enable explain=true for returned hits, but the response will be larger and more expensive. Use this only when debugging specific queries or in test environments.

The Profile API helps analyze query execution time per shard; it does not replace Explain for understanding score semantics. Both carry overhead and should not be enabled broadly in production.

## 18. Testing Sorting and Conditions That Preserve Scores

Create test data with varying relevance scores and sort attributes to verify ordering.

For example:

| ID | name | priceInCents | active |
|---|---|---:|---|
| P-1 | Wireless Mouse | 300000 | true |
| P-2 | Wireless Gaming Mouse | 250000 | true |
| P-3 | Mouse Pad | 100000 | true |
| P-4 | Wireless Mouse | 150000 | false |

Desired query:

- Match names related to wireless mouse.
- Include only active=true.
- Sort by _score descending.
- If scores tie, price ascending.
- If both score and price tie, ID ascending.

REST DSL:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" },
    { "priceInCents": "asc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Tests should verify:

1. P-4 is excluded because active=false.
2. Remaining documents are sorted by score first.
3. Price breaks ties only when scores are equal.
4. ID creates a stable order when preceding criteria are equal.
5. Changing the sort to price before _score changes results according to price-first semantics.

Do not hard-code exact BM25 score numbers unless you fully control the dataset, analyzers, and version. Instead, assert relative order or verify the sort structure and result set.

### 18.1. Testing That Filters Do Not Lose Relevance

Compare two queries:

- match in must + active in filter.
- match in filter.

The first query should produce relevance scores from match. The second query only filters documents without using match to compute relevance. Inspect _score in the response or use Explain to confirm.

## 19. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cheapest result ranks first despite low relevance | price placed before _score | Put _score first in sort if relevance is primary |
| _score is 0 or unhelpful | Full-text query is inside filter context | Move match to must/should |
| Scores are not returned when sorting by field | Elasticsearch does not track scores by default in that case | Enable track_scores if reading scores is needed |
| track_scores enabled but order still follows price | track_scores does not alter sort precedence | Add _score to sort if relevance priority is needed |
| Tied results change order | No stable tie-breaker | Add a unique keyword field at the end of sort |
| Pages contain duplicates or missing hits | Unstable sort or index changed between pages | Use unique sort, search_after, and PIT where appropriate |
| search_after returns wrong results | Sort/query changed or invalid search_after values | Use exact sort values from the last hit of the previous page |
| should is not required as expected | must/filter present so minimum_should_match defaults to 0 | Set minimum_should_match explicitly |
| Filter changes result set without changing scores | Normal semantics of filter context | Keep relevance queries in must/should |
| min_score excludes too many documents | Threshold does not match score distribution | Evaluate against real query sets |
| Scores change after mapping or data changes | BM25 depends on term statistics/analyzers | Inspect mapping, analyzers, and Explain |

## 20. Workflow for Designing Relevance-Preserving Sorts

When building a search endpoint:

1. Decide whether relevance or a business field is the primary ranking criterion.
2. Place full-text queries in must or should if _score is needed.
3. Put yes/no conditions such as tenant, active, category, and access control into filter.
4. If relevance is primary, sort by _score desc first.
5. Add secondary sort fields only to break ties among equal-scoring results.
6. Add a unique keyword tie-breaker for stable ordering.
7. If sorting by fields while still needing scores in the response, enable track_scores.
8. Distinguish track_scores from track_total_hits.
9. Use search_after and PIT for deep pagination requiring stability.
10. Use Explain and representative query sets to evaluate ranking.

## 21. Quick Reference Table

| Need | Configuration |
|---|---|
| Default relevance | Omit sort; Elasticsearch uses _score desc |
| Relevance as primary priority | sort _score desc first in the list |
| Price breaks ties on equal scores | _score desc, price asc |
| Price is primary priority, score breaks ties | price asc, _score desc |
| Filter conditions while keeping relevance | bool.must for match, bool.filter for yes/no conditions |
| Add optional boost signals | bool.should; understand minimum_should_match |
| Keep scores when sorting by field | track_scores: true |
| Track exact total hit count | track_total_hits: true |
| Exclude low-score results | min_score after evaluating threshold |
| Stable ordering | Add unique keyword tie-breaker |
| Deep pagination | search_after, consider PIT |
| Diagnose score calculation | Explain API |
| Rule-based score adjustment | boost, function_score, or script_score when needed |

Sorting by _score keeps the most relevant documents at the top of the results. To preserve relevance scoring when filtering, place full-text queries in must/should and yes/no conditions in filter. When combining price or date sorting, the order of sort keys determines which criterion is primary; track_scores only retains scores during field sorting and does not turn score into a ranking criterion. For stable pagination, add a unique tie-breaker and use search_after/PIT when appropriate.
