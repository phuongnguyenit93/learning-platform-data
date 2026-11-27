# Using Filters for Conditions That Do Not Need Scoring

When searching in Elasticsearch, not every condition needs to influence result relevance. A product query might need to match text entered by the user while also restricting results to active products, a specific brand, a price range, and in-stock availability.

In that example, the product name is a full-text search condition: documents matching better should receive a higher relevance score. Conditions such as status, brand, price range, and stock usually exist only to include or exclude documents. They do not need to contribute to the relevance score.

Elasticsearch distinguishes two execution contexts:

- **Query context:** determines whether a document matches and computes `_score` to represent how well it matches.
- **Filter context:** only determines whether a document satisfies the condition; no relevance score is computed for that condition.

Placing non-scoring conditions inside `bool.filter` expresses the intent clearly, avoids unnecessary scoring calculations, and gives Elasticsearch opportunities to apply filter optimizations. In Spring Data Elasticsearch, this type of query can be built using `NativeQuery` and the Elasticsearch Query DSL.

## 1. Query context and filter context

An Elasticsearch query often needs to answer two different questions:

1. Does the document satisfy the conditions?
2. Among documents that satisfy the conditions, which ones match the search input better?

Query context handles both questions. Filter context answers only the first question.

### 1.1. Query context

In query context, Elasticsearch evaluates how well a document matches the query and computes `_score`.

Example:

~~~json
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

`match` analyzes the search string using the field's analyzer and finds matching documents. Documents that match better can receive a higher `_score` and rank higher under default relevance sorting.

Query context fits full-text search, matching user-entered text, queries where relative relevance between documents is meaningful, and clauses that should contribute to `_score`.

### 1.2. Filter context

In filter context, Elasticsearch only checks whether a condition is true or false. The condition does not contribute to the relevance score.

Example:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 200
            }
          }
        }
      ]
    }
  }
}
~~~

The query only retrieves products with status `ACTIVE` and price between 50 and 200. Neither condition needs relevance scoring.

Filter context typically fits status, type, category, or brand ID; price, date, or quantity ranges; access control and tenant ID; boolean flags; field existence checks; and geo distance or bounding box when only restricting an area.

### 1.3. Comparison

| Criterion | Query context | Filter context |
| --- | --- | --- |
| Match/non-match decision | Yes | Yes |
| Computes relevance score | Yes | No |
| Affects _score | Yes | No |
| Used for relevance ranking | Yes | No |
| Suitable for exact/range conditions | Possible | Usually preferred |
| Eligible for query cache | Depends on query type and conditions | Yes, subject to Elasticsearch cache policies |

Filter context does not mean a separate index structure or a separate mapping type. It is the execution context in which a query runs.

## 2. Placing conditions in bool.filter

A `bool` query combines multiple conditions. Main clauses:

| Clause | Meaning | Context |
| --- | --- | --- |
| `must` | Document must match the clause | Query context |
| `should` | Clause should match to boost score or satisfy threshold | Query context |
| `filter` | Document must satisfy the condition | Filter context |
| `must_not` | Document must not satisfy the condition | Filter context |

Example finding keyboards matching a name, belonging to a specific brand, in stock, and not discontinued:

~~~json
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
        {
          "term": {
            "brandId": "BRAND-10"
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
              "gte": 50,
              "lte": 250
            }
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "status": "DISCONTINUED"
          }
        }
      ]
    }
  }
}
~~~

In this query, `must` uses `match` to search names and compute relevance scores; `filter` excludes products with the wrong brand, out of stock, or outside the price range; `must_not` excludes discontinued products. Only queries in query context contribute to ranking scores.

### 2.1. Filters combine with AND

All clauses inside `bool.filter` must be satisfied. You can think of them as an AND expression:

~~~text
brandId = BRAND-10
       AND available = true
       AND price >= 50
       AND price <= 250
~~~

If a document fails any required filter, it is excluded from results.

### 2.2. must_not is negation in filter context

`must_not` excludes documents matching the enclosed query. This clause does not compute relevance scores.

~~~json
{
  "bool": {
    "must_not": [
      {
        "terms": {
          "status": ["DELETED", "BLOCKED"]
        }
      }
    ]
  }
}
~~~

Documents with status `DELETED` or `BLOCKED` are excluded. There is no need to put negation conditions inside `must` or use `match` just to generate unnecessary scores.

### 2.3. should is not a filter by default

`should` is commonly used to boost relevance scores when a document matches an additional condition. It belongs to query context.

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "keyboard"
        }
      }
    ],
    "should": [
      {
        "term": {
          "featured": true
        }
      }
    ],
    "filter": [
      {
        "term": {
          "available": true
        }
      }
    ]
  }
}
~~~

Featured products can receive a score boost, while still having to satisfy the `available` filter.

If a `bool` query has `must` or `filter`, `minimum_should_match` defaults to 0. In that case, `should` only affects score and does not require documents to match `should`. If a `bool` query has only `should` without `must`/`filter`, at least one `should` clause must match by default.

If business logic requires at least one `should` clause to match, declare `minimum_should_match` explicitly instead of relying on defaults.

## 3. Combining full-text search with filters

This is a common pattern in Spring Data Elasticsearch applications:

- User enters keywords.
- Application searches by content.
- User selects filters in the UI.
- Filters only narrow down the result set.

Example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "wireless keyboard",
            "fields": ["name^3", "description", "brandName"]
          }
        }
      ],
      "filter": [
        {
          "term": {
            "categoryId": "KEYBOARDS"
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
              "gte": 30,
              "lte": 180
            }
          }
        }
      ]
    }
  }
}
~~~

`multi_match` searches across multiple fields and affects relevance scores. The `category`, `available`, and `price` filters only narrow the document set.

If the user leaves keywords blank while selecting filters, you can build a `bool` query containing only `filter`. You do not need to add `match_all` into `must` just to make the query run; however, combining `match_all` with `filter` is also valid if the application prefers a fixed query structure.

### 3.1. Filters do not alter relevance scores

Suppose two products both match the search name, while one has the matching brand ID and the other does not:

- The product failing the brand filter is excluded.
- The remaining products are ranked based on query context.
- The filter adds no extra score to the product with the matching brand ID.

This is a key distinction between mandatory constraints and ranking signals.

### 3.2. When should a condition be in must?

Ask whether the condition needs to alter ranking order.

| Condition | Usually appropriate placement | Reason |
| --- | --- | --- |
| Product name contains user's search terms | `must` / `should` | Needs relevance |
| Brand ID must equal a value | `filter` | Only true/false needed |
| Status must be ACTIVE | `filter` | No score needed |
| Price falls within range | `filter` | Numeric constraint |
| Document also matches synonyms to improve fit | `should` | Can boost score |
| Forbidden document types | `must_not` | Exclude from result set |
| User must belong to current tenant | `filter` | Mandatory constraint |

A `term` condition can still be placed inside `must`, but if it does not need scoring, placing it in `filter` expresses intent more accurately.

## 4. Common queries used in filter context

Many Query DSL queries can be executed in filter context. They do not require a separate query type solely because they sit inside `filter`.

### 4.1. term

Used to match an exact value:

~~~json
{
  "term": {
    "status": "ACTIVE"
  }
}
~~~

Suitable for `keyword`, `boolean`, numeric, `date`, and fields with exact-match semantics.

Do not use `term` directly on an analyzed `text` field if you expect full-text matching. For `text`, normally use `match` in query context. If exact matching is needed, create a `keyword` subfield or map the field as `keyword`.

### 4.2. terms

Used when a field can match one of several values:

~~~json
{
  "terms": {
    "categoryId": ["KEYBOARDS", "MICE", "MONITORS"]
  }
}
~~~

`terms` is typically placed in `filter` when the IDs represent filter selections.

### 4.3. range

Used to bound values:

~~~json
{
  "range": {
    "price": {
      "gte": 50,
      "lt": 200
    }
  }
}
~~~

Common operators: `gt` greater than, `gte` greater than or equal to, `lt` less than, and `lte` less than or equal to.

Range also works well for `date`:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "2026-01-01T00:00:00Z",
      "lt": "2027-01-01T00:00:00Z"
    }
  }
}
~~~

### 4.4. exists

Used to check whether a field has an indexed value:

~~~json
{
  "exists": {
    "field": "publishedAt"
  }
}
~~~

`exists` checks whether a value exists in the index per mapping semantics. Fields with `null` or empty arrays are usually treated as non-existent; an empty string field may still be treated as existing.

### 4.5. prefix and wildcard

When business requirements call for prefixes or patterns, these queries can still be placed in filter context:

~~~json
{
  "prefix": {
    "sku": "KB-"
  }
}
~~~

~~~json
{
  "wildcard": {
    "sku": {
      "value": "KB-10*"
    }
  }
}
~~~

Not computing a score does not mean the query is cheap. Wildcards, regexes, or patterns can still be resource-intensive depending on pattern structure and mapping. Avoid leading-wildcard patterns starting with `*` on large datasets without justification and benchmarking.

### 4.6. nested

If a field is a `nested` object, a `nested` query can also be used inside filter context:

~~~json
{
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
              "variants.price": {
                "lte": 150
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Both color and price conditions must apply to the same nested variant. Placing child fields inside a normal object array allows Elasticsearch to match values across different array elements.

### 4.7. geo_distance and geo_bounding_box

Filter context fits when distance or a geographic region is purely a bounding constraint:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

If ranking by distance is needed, sort by geo distance or use an appropriate scoring function. If you only need locations within a radius, filter context is the natural choice.

## 5. Filter context does not automatically mean cached

One common reason mentioned for using filters is leveraging the query cache. However, distinguish between two concepts:

- Filter context: the query does not compute relevance scores.
- Node query cache: a mechanism caching results of certain queries/filters per segment on each node.

Placing a query in filter context does not guarantee its results will be cached.

### 5.1. The query cache operates automatically

Elasticsearch manages the query cache using heuristics. Not every filter is cached. Caching depends on query type, usage history, segment, cost, and other internal criteria.

Key points to remember:

- The query cache is per segment.
- The cache lives at the node level, not as a single cluster-wide cache.
- Segment changes or merges can make old cache entries unusable.
- Infrequently reused queries may not be worth caching.
- Queries with unsuitable characteristics may not be cached.
- Elasticsearch decides caching and eviction according to its own policies.

Therefore, do not design performance around the assumption that every `bool.filter` is cached.

### 5.2. Stable and frequently repeated filters

A stable, frequently repeated filter, such as `status=ACTIVE` or a popular tenant/category, can be a good candidate for the query cache if it meets Elasticsearch's internal criteria.

A filter containing a continuously changing timestamp or random per-request values has little chance of cache reuse.

### 5.3. Do not manually add caches just because filters are used

Normally, there is no need to manually configure caching per filter. Instead:

1. Place non-scoring conditions in filter context.
2. Measure query latency and throughput.
3. Observe query cache hit/miss and memory via node stats.
4. Inspect query profiles if issues appear.
5. Change cache settings only when backed by measurement evidence.

There is no guarantee a filter will always outperform every query context in every scenario. The clearest benefit is avoiding unnecessary score computation and keeping query semantics accurate.

## 6. Filters and sorting

Filters do not determine result order. If a query contains only filters and no sort is specified, Elasticsearch may return results in default search engine order rather than by price or update timestamp.

Example filtering active products in a price range and sorting by ascending price:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 50,
              "lte": 200
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

In this case, results are ordered by `price`, not relevance.

### 6.1. Sorting by field and _score

If sorting solely by a field, Elasticsearch does not need `_score` to order results. If the application still needs scores in the response when sorting by a field, you can enable `track_scores` per the corresponding API.

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "available": true
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "track_scores": true
}
~~~

`track_scores` does not convert filters into query context. It requests score tracking during a field-sorted search.

### 6.2. Stable pagination

When paginating deeply or over continuously changing data, sorting needs a stable tie-breaker. For example, sort by price and then by a unique ID. For deep pagination, consider Point in Time (PIT) combined with `search_after` instead of large offsets.

## 7. How do filters affect aggregations?

Where you place a filter determines the document set used for aggregations.

### 7.1. bool.filter inside query

If the filter sits in the top-level query, both hits and aggregations operate on the filtered document set.

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    }
  }
}
~~~

The `by_brand` aggregation summarizes only `ACTIVE` products.

### 7.2. post_filter

`post_filter` is applied to search hits after aggregations have been computed. It is useful when the UI needs to filter the result list while keeping aggregations reflective of the broader result set.

~~~json
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "post_filter": {
    "term": {
      "brandId": "BRAND-10"
    }
  },
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    }
  }
}
~~~

In this example, the query finds all products related to keyboard; the aggregation computes brand distribution across that query's result set; `post_filter` narrows only the returned hits to brand `BRAND-10`.

If you put the brand filter into top-level `bool.filter`, the aggregation would also see only brand `BRAND-10`. Therefore, do not mechanically replace `bool.filter` with `post_filter`.

## 8. Using filters in Spring Data Elasticsearch

Spring Data Elasticsearch provides `NativeQuery` to build Elasticsearch Query DSL using the Java API Client query builders.

The example below uses:

- `must` for full-text query.
- `filter` for non-scoring conditions.
- `must_not` to exclude documents.

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("mechanical keyboard")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("brandId")
                    .value("BRAND-10")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("available")
                    .value(true)
                )
            )
            .filter(f -> f
                .range(r -> r
                    .number(n -> n
                        .field("price")
                        .gte(50.0)
                        .lte(250.0)
                    )
                )
            )
            .mustNot(mn -> mn
                .term(t -> t
                    .field("status")
                    .value("DISCONTINUED")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

Builder method names and range query overloads may differ by Elasticsearch Java API Client and Spring Data Elasticsearch version. Consult your project dependency's Javadoc if the compiler expects a different value or builder type. The DSL semantics stay the same: conditions inside `filter` execute in filter context.

### 8.1. Separating the query builder from the service

For applications with many dynamic filters, create a dedicated component for building queries rather than placing all lambdas inside the service.

Example criteria structure:

~~~java
public record ProductSearchCriteria(
    String text,
    String brandId,
    String categoryId,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    Pageable pageable
) {}
~~~

Filter construction logic should distinguish:

- Omitted field: do not apply the condition.
- Boolean `false`: still a valid filter, must not be treated as missing.
- Empty list: usually do not add a `terms` query; define clearly whether an empty list means no filter or no results.
- Value `0`: a valid value, must not be checked with `> 0` if business rules allow zero.
- Min/max range: add a range only when at least one bound is present and handle cases where min exceeds max.

When building dynamic queries, add clauses only when the corresponding criteria has a value. Never construct ranges or terms with null values, and never turn mandatory constraints into `should` clauses just to avoid query errors.

### 8.2. CriteriaQuery

Spring Data Elasticsearch also offers `CriteriaQuery` and the Criteria API to describe conditions fluently.

Criteria fits simple queries and field-oriented conditions. When you need explicit control over `bool.must`, `bool.filter`, `must_not`, `minimum_should_match`, nested scoring, or complex Query DSL, `NativeQuery` is usually more exact.

Do not assume every Criteria condition carries the exact same semantics as a specific `bool.filter` without inspecting the generated Query DSL. If performance relies on a condition running in filter context, verify the actual request via logging or integration tests.

## 9. Designing dynamic filters from search criteria

A search form often lets users pick multiple optional filters. The application should add each corresponding clause only when that filter has a value.

Example criteria:

~~~java
public record ProductSearchCriteria(
    String text,
    String brandId,
    String categoryId,
    Double minPrice,
    Double maxPrice,
    Boolean available,
    Pageable pageable
) {}
~~~

### 9.1. Filtering by a list

If the user selects multiple categories:

~~~json
{
  "terms": {
    "categoryId": ["KEYBOARDS", "MICE"]
  }
}
~~~

This acts as an OR within the same `terms` query: a document matching any selected value passes. When combined with another filter at the `bool.filter` level, the two filters are still ANDed together.

### 9.2. Multiple selections within a group and across groups

Faceted search UIs usually have these semantics:

- OR across values within the same facet, e.g., category in `KEYBOARDS` or `MICE`.
- AND across different facets, e.g., valid category AND valid brand AND `available`.

~~~json
{
  "bool": {
    "filter": [
      {
        "terms": {
          "categoryId": ["KEYBOARDS", "MICE"]
        }
      },
      {
        "terms": {
          "brandId": ["BRAND-10", "BRAND-20"]
        }
      },
      {
        "term": {
          "available": true
        }
      }
    ]
  }
}
~~~

A document must match at least one category, at least one brand, and `available=true`.

## 10. Filters for tenants and access permissions

Tenant IDs or data-partitioning conditions normally do not need scoring. You can place them in filter context:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "content": "invoice"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "tenantId": "TENANT-42"
          }
        }
      ]
    }
  }
}
~~~

The tenant condition is a mandatory constraint and does not need to boost relevance scores.

Placing a tenant ID into a filter does not by itself create a security boundary. The application must obtain the tenant ID from an authenticated, controlled context and never trust values sent directly by the client. If a user can tamper with the tenant ID in the request, they could query another tenant's data.

Similarly, access-control filters must be derived from a trusted authorization context. Query filters are part of enforcement at the search layer, not a replacement for application authentication and authorization.

## 11. Filters and scoring: edge cases to consider

Not every category or numeric condition always belongs in `filter`. Base the choice on product semantics.

Examples:

- User selects a brand from a dropdown: `filter`.
- System wants to promote a sponsored brand: `should` or `function_score`.
- User requires price within a range: `filter`.
- System wants fit score to decay with distance from a target price: scoring function.
- User requires in-stock products: `filter`.
- System wants to prioritize products with ample stock: scoring signal if business rules allow.

### 11.1. When a condition must filter and also boost score

A condition can act as both a constraint and a scoring signal, though the two roles should be expressed clearly.

For example, retrieve only `available=true` products, then boost `featured` products:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
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
      "should": [
        {
          "term": {
            "featured": true
          }
        }
      ]
    }
  }
}
~~~

`available` is a mandatory constraint; `featured` is a boosting signal. Do not put `available` into `should` because out-of-stock items must not appear.

### 11.2. constant_score

`constant_score` runs a child query in filter context and assigns a fixed score to every matching document.

~~~json
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "status": "ACTIVE"
        }
      },
      "boost": 1.0
    }
  }
}
~~~

`constant_score` is useful when you want a set of filter-matching documents to receive the exact same score. If the application only needs filtering, `bool.filter` is usually more direct and readable.

## 12. Measuring performance

Using filters is a decision about both semantics and execution optimization. Do not infer performance purely from clause counts or the presence of filters.

### 12.1. Profiling queries

The Elasticsearch Profile API helps inspect execution time of query components. Profiling adds overhead, so enable it only during diagnostics, never permanently on all production requests.

You can use profile to pinpoint expensive clauses, compare scored queries against corresponding filter queries, spot expensive wildcard/nested/script queries, and understand per-shard execution.

### 12.2. Monitoring node stats

Query cache stats help observe cache hit counts, miss counts, memory in use, and cached/evicted entries.

Interpret these numbers in the context of workload and segment churn. A high hit ratio does not automatically prove low query latency; a low hit ratio does not mean you should force caching on every filter.

### 12.3. Benchmarking with representative data

When comparing queries, keep constant: dataset and mapping, shard/replica counts, query parameters, page size and sort, warm/cold cache state, concurrency level, and refresh/indexing activity.

Measure multiple runs and compare latency percentiles such as p50, p95, p99, along with throughput and CPU. Avoid comparing one cold-cache run against one warm-cache run and drawing conclusions.

## 13. Common mistakes

**Putting every condition into must.** Exact conditions such as status, brand ID, and price range do not need relevance scores. Move them to `filter`.

**Thinking filters remove all scoring from a query.** Filter clauses contribute no score, but query-context clauses like `must`/`should` still score documents.

**Assuming filters are always cached.** The query cache is managed by Elasticsearch heuristics; filter context does not guarantee a cache hit.

**Using term on text fields to search content.** Text fields are analyzed; use `match` for full-text or a `keyword` subfield for exact matching.

**Putting ranking signals into filter.** If an attribute should raise or lower relevance, use `should`, `function_score`, or an appropriate scoring query.

**Using should to represent mandatory conditions.** When `must` or `filter` is present, `should` is optional by default. Use `filter` for mandatory conditions or set `minimum_should_match` explicitly.

**Forgetting post_filter semantics.** `post_filter` only filters hits after aggregations; top-level queries/filters affect both hits and aggregations.

**Assuming filters automatically sort results.** Filters only restrict documents. If ordering by price, date, or score is needed, specify `sort`.

**Putting broad wildcards in filter and expecting them to always be fast.** Filters skip scoring, yet wildcards can still be resource-heavy.

**Passing tenant ID directly from clients into filters.** Obtain tenant ID from an authenticated context and enforce authorization at the application layer.

**Using CriteriaQuery without checking the generated DSL.** If filter-context semantics are strictly required, verify the actual query or use `NativeQuery` to express it explicitly.

**Enabling track_scores without needing scores.** When sorting by a field, track scores only if the caller genuinely needs `_score` values.

## 14. Process for building filtered queries

When designing a search endpoint:

1. Classify each condition: does it need relevance or just true/false?
2. Place full-text searches in `must` or `should`.
3. Place exact, range, tenant, and status constraints in `filter`.
4. Place exclusion conditions in `must_not`.
5. Set `minimum_should_match` if `should` plays a mandatory role.
6. Choose matching mappings: `keyword` for exact match, numeric/date for ranges, `nested` for correlated object arrays.
7. Define sorting independently of filters.
8. Determine which document set aggregations should summarize; pick query `filter` or `post_filter` according to semantics.
9. Build the query with `NativeQuery` or the appropriate Spring Data Elasticsearch API.
10. Measure the query on representative data; optimize caching only with empirical numbers.

~~~text
Search request
     |
     v
Build bool query
     |
     +-- must: full-text relevance
     |
     +-- should: optional ranking signals
     |
     +-- filter: exact/range/tenant constraints
     |
     +-- must_not: excluded documents
     |
     v
Sort and pagination
     |
     v
Elasticsearch
     |
     v
SearchHits + aggregations
~~~

## 15. Complete example: product search

Requirements:

- Search products by keyword in name and description.
- Return only `ACTIVE` products.
- Optional filter by brand.
- Optional filter by category.
- Optional filter by price range.
- Return only in-stock products when the user enables the filter.
- Rank by relevance, with optional price sorting when selected by the user.

Illustrative Query DSL:

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
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "brandId": "BRAND-10"
          }
        },
        {
          "terms": {
            "categoryId": ["KEYBOARDS", "ACCESSORIES"]
          }
        },
        {
          "range": {
            "price": {
              "gte": 40,
              "lte": 180
            }
          }
        },
        {
          "term": {
            "available": true
          }
        }
      ],
      "must_not": [
        {
          "term": {
            "deleted": true
          }
        }
      ]
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

In production, brand, category, price, and available are added only when the corresponding criteria has a value. Status `ACTIVE` and `deleted=false` may be system-enforced conditions always applied.

### 15.1. When the user sorts by price

Change the sort:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "_score": {
        "order": "desc"
      }
    }
  ]
}
~~~

Here price is the primary sort key; `_score` breaks ties between equally priced products when allowed by the query, API, and mapping.

### 15.2. When no keyword is provided

If the user only picks brand, category, and price, you can construct a `bool` query with only `filter`:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "brandId": "BRAND-10"
          }
        },
        {
          "range": {
            "price": {
              "lte": 180
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

There is no full-text query, so there is no meaningful relevance ranking. Sorting by field satisfies the UI requirement.

## 16. References

- [Elasticsearch - Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html): difference between query context and filter context.
- [Elasticsearch - Boolean query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html): `must`, `should`, `filter`, `must_not`, and `minimum_should_match`.
- [Elasticsearch - Query cache](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-cache.html): per-segment caching and usage conditions.
- [Elasticsearch - Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html): exact matching.
- [Elasticsearch - Range query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-range-query.html): range conditions.
- [Elasticsearch - Post filter](https://www.elastic.co/guide/en/elasticsearch/reference/current/filter-search-results.html): filtering hits after aggregations.
- [Elasticsearch - Profile search requests](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-profile.html): analyzing query execution costs.
- [Spring Data Elasticsearch - Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): building queries and executing searches via `ElasticsearchOperations`.
- [Spring Data Elasticsearch - NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html): `NativeQuery` API using the Elasticsearch Java API Client.

Exact builder methods may differ depending on Spring Data Elasticsearch and Elasticsearch Java API Client versions. When implementing, verify the Javadoc for your exact dependency. The core principle is to use query context for conditions needing relevance and filter context for conditions that only determine whether a document should be retained; placing filters does not guarantee a cache hit and does not replace real performance measurement.
