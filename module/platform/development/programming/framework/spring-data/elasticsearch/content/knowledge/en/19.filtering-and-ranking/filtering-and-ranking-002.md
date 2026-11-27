# Query Context vs. Filter Context in Practice

When searching with Elasticsearch, a condition can be used either to **rank how well a document matches** or solely to **determine whether a document is allowed to appear in the results**. These two modes of evaluation are called query context and filter context.

- **Query context** answers the question: how well does this document match the search content? Elasticsearch calculates `_score` to represent relevance and typically uses the score to rank results.
- **Filter context** answers the question: does this document satisfy the condition? The result is purely true or false; the condition does not contribute to `_score`.

In a Spring Data Elasticsearch application, placing conditions appropriately into `must`, `should`, `filter`, or `must_not` produces sensible result ordering, eliminates unnecessary scoring work, and makes the business intent of the query clear.

Consider a product search page:

- The user enters `mechanical keyboard`: the name/description content needs to be scored so more relevant products appear first.
- The user selects category `KEYBOARD`, status `ACTIVE`, price from 1,000,000 to 5,000,000: these are yes/no filter conditions.
- The user excludes discontinued products: an exclusion condition does not need to increase or decrease the relevance score.

A combined query typically looks like this:

```json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "mechanical keyboard" } }
      ],
      "filter": [
        { "term": { "category": "KEYBOARD" } },
        { "term": { "status": "ACTIVE" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ],
      "must_not": [
        { "term": { "discontinued": true } }
      ]
    }
  }
}
```

In this example, `match` runs in query context to compute relevance; the `filter` and `must_not` conditions only narrow down the result set.

## 1. What Is Query Context?

A query clause runs in query context when Elasticsearch needs to evaluate how well a document matches the query. Besides determining whether the document matches, Elasticsearch computes a relevance score in the `_score` field.

Query context is usually appropriate for requirements such as:

- Searching text by meaning or user-entered keywords.
- Ranking documents by relevance.
- Combining multiple content signals so more suitable documents appear first.
- Approximate, fuzzy, or phrase matching when the user does not know the exact stored format.

Example `match` query:

```json
GET /articles/_search
{
  "query": {
    "match": {
      "body": "distributed search engine"
    }
  }
}
```

Elasticsearch analyzes the query text using the field's analyzer, finds documents with matching tokens, and computes `_score`. Documents matching more terms or showing stronger relevance signals can receive a higher score, depending on the similarity algorithm and query structure.

Query context is not exclusively for `match`. Other queries like `term`, `range`, or `exists` can also be placed in query context. The difference lies in the **execution context**, not solely in the type of query clause.

## 2. What Is Filter Context?

A query clause runs in filter context when the goal is purely a true/false check. Elasticsearch does not calculate a relevance score for that clause and can leverage appropriate caching mechanisms.

Filter context is usually suitable for conditions with fixed, exact semantics:

- Status must be `ACTIVE`.
- Tenant must be `tenant-42`.
- Price falls within a defined range.
- Creation date falls within a time window.
- Field must exist.
- IP address must belong to a subnet.
- Document must not be marked deleted or discontinued.

Example:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ACTIVE" } },
        { "term": { "category": "KEYBOARD" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ]
    }
  }
}
```

Documents satisfying all three conditions are retained. None of the conditions are used for relevance ranking; if there is no other scoring part and no field sort, the result order carries no relevance meaning.

## 3. Distinguishing Through `bool` Query Clauses

The `bool` query is the common way to combine query context and filter context.

| Clause | Context | Meaning |
|---|---|---|
| `must` | Query context | Condition must match; the clause's score can contribute to the total score. |
| `should` | Query context | Condition should match; can boost the score and sometimes becomes mandatory depending on `minimum_should_match`. |
| `filter` | Filter context | Condition must match, but does not contribute to the score. |
| `must_not` | Filter context | Excludes documents matching the condition; does not contribute to the score. |

Example:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "gaming keyboard" } }
      ],
      "should": [
        { "term": { "brand": "ACME" } },
        { "term": { "featured": true } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "must_not": [
        { "term": { "deleted": true } }
      ],
      "minimum_should_match": 0
    }
  }
}
```

Here:

- Products must match the content `gaming keyboard`.
- Products must be active.
- Deleted products are excluded.
- Brand `ACME` or featured products can receive a score boost if they match `should`.

With `minimum_should_match: 0`, `should` acts purely as a boosting signal; a document does not have to match any of the `should` clauses as long as it satisfies `must` and `filter`.

### Default Rules for `minimum_should_match`

If a `bool` query has only `should` and no `must` or `filter`, at least one `should` must match by default. If `must` or `filter` is already present, `should` is optional by default and can serve purely to increase the score.

If business logic requires at least one of several optional conditions to hold, declare `minimum_should_match` explicitly:

```json
{
  "bool": {
    "must": [
      { "match": { "name": "keyboard" } }
    ],
    "should": [
      { "term": { "brand": "ACME" } },
      { "term": { "featured": true } }
    ],
    "minimum_should_match": 1
  }
}
```

In that case, the document must match the content `keyboard` and also match at least one of the two `should` conditions.

## 4. Choosing the Right Context in Real Business Cases

An easy rule of thumb:

- If a condition determines whether a document is **allowed to appear**, usually place it in `filter` or `must_not`.
- If a condition indicates the document is **more relevant** to the search intent and should affect ordering, place it in `must` or `should`.

Example of a course search page:

| Condition | Suggested Context | Reason |
|---|---|---|
| Name/description contains user-entered text | `must` with `match` | Needs relevance scoring based on content. |
| Course belongs to the Java category | `filter` with `term` | Category is a mandatory condition; no scoring needed. |
| Only retrieve published courses | `filter` with `term` | Status is a business constraint. |
| Tuition within user-selected range | `filter` with `range` | Only needs a range check. |
| Recommended course | `should` | Can increase priority without excluding other courses. |
| Exclude removed courses | `must_not` | Excludes from the result set. |

Do not put all conditions into `must` simply because they are all required. `must` can compute scores for each clause even when the application has no need to rank by those conditions. Conversely, do not put primary search content into `filter` if relevance scoring is required.

## 5. Query Context Does Not Mean Full-Text; Filter Context Does Not Mean Exact Query

This is a common misconception. `match` is often used in query context because it serves full-text search, yet `match` can still be placed inside `filter`. When placed there, it only checks whether the document matches and contributes no score.

Similarly, `term` is typically used for exact matching, but it can be placed in `must` or `should` to contribute to the score when run in query context.

Example of `term` in query context:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "term": { "brand": "ACME" } }
      ]
    }
  }
}
```

Example of the same condition in filter context:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "brand": "ACME" } }
      ]
    }
  }
}
```

Both queries check whether `brand` equals `ACME`, but the first query computes a score while the second query computes no score from the brand condition.

## 6. Why Put Filtering Conditions in Filter Context?

### Avoid Scoring Conditions That Need No Ranking

If `status = ACTIVE` is purely a mandatory condition, scoring it adds no business value. Putting it in `filter` clearly expresses that this condition only narrows the document set.

### Potential Query Cache Benefits

Elasticsearch has a node query cache for certain queries executed in filter context. The cache stores matching results per segment so they can be reused in eligible subsequent queries. However, not every filter is cached; caching depends on query type, usage frequency, segment size, and Elasticsearch heuristics.

Therefore, do not design queries assuming every `filter` is guaranteed to be cached. Filter context remains beneficial because it skips scoring; caching is simply an additional optimization when conditions and workloads qualify.

### Works Well with Repetitive Data

Conditions such as tenant, status, product type, or date ranges appear across many requests. They fit filter context well because they have clear boolean semantics and can be reused during execution.

### No Need to Manually Order Filters by Selectivity

You do not need to manually order `filter` clauses by which condition eliminates the most documents. Elasticsearch optimizes query execution; the order in JSON is not a guarantee that the first clause always runs first. Organize filters for clarity and maintainability.

## 7. Query Context and `_score`

In query context, `_score` represents how well a document matches the query. Elasticsearch typically uses BM25 for default full-text similarity, though the exact score depends on analyzers, term statistics, field length, similarity settings, and query structure.

Example:

```json
GET /articles/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "title": "spring elasticsearch" } },
        { "match": { "body": "distributed search" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
```

The two `match` clauses in `must` contribute to the total score. The `status` filter only keeps published articles; it does not raise an article's score.

In a `bool` query, scores of scoring clauses are combined according to the query's rules. Do not assume the total score is a simple addition in all structures, because nested queries, boosts, `dis_max`, function scores, or script scores can alter how it is calculated.

### Inspecting Score with `explain`

When you want to know why a document received a particular score, you can use the Explain API:

```json
GET /articles/_explain/article-100
{
  "query": {
    "bool": {
      "must": [
        { "match": { "title": "spring elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
```

The response explains whether the document matched the query and which components contributed to the score. Explain is useful for diagnosing a single document; do not call it for every document in production traffic because responses can be large and resource-intensive.

## 8. Using `constant_score` When You Only Need a Fixed Score for a Match

`constant_score` executes a query inside filter context and assigns a fixed score to every matching document. It is useful when you need to include a boolean condition in a scoring query without having the score depend on how well that condition matched.

Example:

```json
GET /products/_search
{
  "query": {
    "constant_score": {
      "filter": {
        "term": {
          "featured": true
        }
      },
      "boost": 2.0
    }
  }
}
```

Every document with `featured = true` receives a fixed score according to the configured boost. This differs from placing `term` directly in `must`, where the term query's score is computed by the scoring model.

In a complex query, `constant_score` can provide a fixed score signal for a group of documents, though you should consider how it combines with other scoring clauses to avoid unintentionally skewing result ordering.

## 9. Combining Relevance with Filters in a Product Query

Suppose an e-commerce page has these parameters:

- `q`: search keywords.
- `category`: user-selected category.
- `minPrice`, `maxPrice`: price range.
- `brand`: optional brand.
- `featured`: boost featured products.
- `status`: only return active products.

The Query DSL can be structured as follows:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "mechanical keyboard",
            "fields": ["name^3", "description"]
          }
        }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } },
        { "term": { "category": "KEYBOARD" } },
        {
          "range": {
            "price": {
              "gte": 1000000,
              "lte": 5000000
            }
          }
        }
      ],
      "should": [
        { "term": { "brand": { "value": "ACME", "boost": 1.5 } } },
        { "term": { "featured": { "value": true, "boost": 2.0 } } }
      ],
      "minimum_should_match": 0,
      "must_not": [
        { "term": { "discontinued": true } }
      ]
    }
  }
}
```

Here:

- `name^3` gives greater weight to name matches than description matches.
- Category, status, and price range are filters.
- Brand ACME and featured products are optional boosting signals.
- Discontinued products are excluded.
- `minimum_should_match: 0` allows products that do not match the `should` signals to still appear if they satisfy the primary query and filters.

If the user selects a brand and asks to see only that brand, move brand from `should` to `filter`. Clause placement must reflect the meaning of the UI filter.

## 10. Example in Spring Data Elasticsearch with `NativeQuery`

In modern Spring Data Elasticsearch, `NativeQuery` uses the Elasticsearch Java API Client's Query DSL. You can build a `bool` query and place each condition in the right context.

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(String text, String category) {
        Query esQuery = Query.of(q -> q
                .bool(b -> b
                        .must(m -> m
                                .match(mm -> mm
                                        .field("name")
                                        .query(text)
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("category")
                                        .value(FieldValue.of(category))
                                )
                        )
                        .filter(f -> f
                                .term(t -> t
                                        .field("status")
                                        .value(FieldValue.of("ACTIVE"))
                                )
                        )
                        .mustNot(mn -> mn
                                .term(t -> t
                                        .field("discontinued")
                                        .value(FieldValue.of(true))
                                )
                        )
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(esQuery)
                .build();

        return operations.search(query, ProductDocument.class);
    }
}
```

This snippet clearly shows:

- `must(match(...))` uses query context to score relevance by product name.
- `filter(term(...))` restricts category and status without scoring.
- `mustNot(term(...))` excludes discontinued products in filter context.

In the example, the field names passed to the Java API Client are the actual Elasticsearch field names. If an entity has `@Field(name = "product_name")` for property `name`, a raw Java API Client query must use `product_name`; Spring Data's mapping does not automatically rename fields inside manually constructed Query DSL.

### Using `CriteriaQuery` for Simple Filter Conditions

`CriteriaQuery` works well when most of the query consists of dynamic filter conditions and does not require complex scoring control. Example:

```java
Criteria criteria = new Criteria("status").is("ACTIVE")
        .and("category").is(category)
        .and("price").between(minPrice, maxPrice);

CriteriaQuery query = new CriteriaQuery(criteria);
SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

When you need to combine relevance scoring, `should`, boosts, or advanced Query DSL, `NativeQuery` lets you express the `bool` query and desired context directly. With the Criteria API, inspect the Query DSL generated by your Spring Data version if distinguishing scoring vs. filtering is an important requirement.

## 11. Using Filters for Tenant, Access Control, and Status

Conditions such as tenant, status, or data scope are typically filters because they determine which documents are eligible to appear in the results. Example:

```json
GET /orders/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "description": "late delivery" } }
      ],
      "filter": [
        { "term": { "tenant_id": "tenant-42" } },
        { "term": { "status": "OPEN" } }
      ]
    }
  }
}
```

Filtering by tenant restricts the results of an application query. However, placing tenant in a filter does not replace Elasticsearch security. If multiple tenants or users with different permissions access the cluster directly, configure security roles, document-level security if supported by your environment, or ensure every query passes through a controlled service.

Do not let clients supply an arbitrary tenant ID to query. Tenant identity should be obtained from the authentication context and added in the service/repository layer to prevent users from modifying request parameters to read another tenant's data.

## 12. Filter Context and Caching

Elasticsearch has a node query cache that often serves results of certain queries running in filter context. The cache operates per segment and is managed by Elasticsearch; it is not a full HTTP response cache.

A few notes:

- Not every filter is cached.
- Queries used frequently and matching caching heuristics have a higher chance of being cached.
- Small segments or infrequently repeated queries may not see caching benefits.
- The cache is managed automatically; do not assume every filter condition stays cached indefinitely.
- `must_not` also runs in filter context and can participate in appropriate optimizations.

Therefore, put conditions into `filter` primarily to express the right semantics and avoid unnecessary scoring. If performance is the goal, measure actual workloads and observe cache statistics rather than relying on an assumption that filters are always faster by a fixed percentage.

## 13. Field Sorting vs. Relevance Scoring

If a query has scoring clauses, Elasticsearch normally sorts by `_score` descending by default. However, when business logic requires sorting by price, creation date, or name, you can specify sort fields.

Example:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "keyboard" } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "sort": [
    { "price": "asc" },
    { "_score": "desc" }
  ]
}
```

Here, lower price comes first; when prices are equal, higher score comes first. If you sort solely by a field and do not need scores, consider disabling score computation/tracking via the appropriate API. If you need to combine score and field sorting, define the priority order of each sort key clearly.

Sorting on `keyword`, numeric, or date fields is more suitable than sorting directly on `text`. If a name needs both full-text search and sorting, use a `keyword` multi-field or a separate sort field.

## 14. When to Use `function_score` or Boosts?

Query context lets you rank by text relevance. When business logic needs additional signals such as popularity, product quality, or recency, you can combine scoring using boosts, `function_score`, or specialized queries.

Example of an optional signal:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless mouse" } }
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } }
      ],
      "should": [
        { "term": { "featured": { "value": true, "boost": 2.0 } } }
      ]
    }
  }
}
```

Featured products receive a score boost if matched, while still having to satisfy the name query and status filter. If `featured` is a mandatory requirement, move it to `filter`; if it is only a ranking signal, keep it in `should` or use an appropriate scoring function.

Do not turn every business attribute into a boost without evaluation. Overly large boosts can push featured but irrelevant products above well-matching items. Test with a query set and expected results.

## 15. Testing Query Context and Filter Context

When building queries, test both the returned document set and the scores:

1. A document failing a filter must be excluded even if its content score is very high.
2. A document passing filters but failing the primary query must not appear if the primary query is in `must`.
3. A document matching more scoring clauses can rank higher as designed.
4. `should` has the right semantics with `minimum_should_match`.
5. `must_not` excludes the right documents.
6. Field sorting does not accidentally override relevance order if the product needs sorting by score.
7. Tenant filters pull the tenant from the security context rather than trusting arbitrary client input.

Example test dataset:

| ID | Name | Status | Category | Featured | Expected Result for query `keyboard` + ACTIVE/KEYBOARD filter |
|---|---|---|---|---:|---|
| P1 | Mechanical keyboard | ACTIVE | KEYBOARD | true | Included; may receive a score boost. |
| P2 | Keyboard cover | ACTIVE | KEYBOARD | false | Included if matching the query. |
| P3 | Mechanical keyboard | INACTIVE | KEYBOARD | true | Excluded by filter. |
| P4 | Mechanical keyboard | ACTIVE | MOUSE | true | Excluded by filter. |
| P5 | Wireless mouse | ACTIVE | MOUSE | false | Does not match primary query and fails filter. |

In integration tests, you can inspect `SearchHit.getScore()` to confirm scoring clauses behave as intended. Do not assert a fixed absolute score if analyzers, corpus, or similarity can change; usually check relative ordering and the returned result set.

## 16. Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Results are not ranked by relevance | Placed the text query inside `filter` instead of query context. | Place search content in `must` or `should` when scoring is needed. |
| Status condition unnecessarily alters score ordering | Placed a boolean condition inside `must`. | Move mandatory conditions to `filter`. |
| Documents not matching optional conditions still appear | `should` is optional because `must`/`filter` is present and `minimum_should_match` defaults to 0. | Set an appropriate `minimum_should_match` or move the condition into `filter`. |
| Filters do not improve performance as expected | Query is not cached, cache does not fit the workload, or the bottleneck lies elsewhere. | Measure the query, check cache stats, and profile if needed. |
| Using `match` for exact code/status filtering | The analyzer may split or normalize tokens. | Use `keyword` and `term` in filter context. |
| `term` query fails to find a value on a `text` field | The `text` field is analyzed, so indexed tokens differ from the input string. | Use a keyword subfield or a query compatible with the analyzer. |
| `must_not` fails to exclude documents as expected | Child condition or mapping mismatches field/value. | Check mapping, Query DSL, and `_source` data. |
| Featured products always rank first despite irrelevance | Boost is too large or `should` is poorly designed. | Adjust boosts, test relevance, and keep the primary query in `must`. |
| Tenant filter fails to protect data | Tenant ID is passed freely by client or service applies filter inconsistently. | Retrieve tenant from authentication context and configure proper security. |

## 17. Design Principles

- Put search content needing relevance into query context (`must`, `should`).
- Put mandatory yes/no conditions into filter context (`filter`, `must_not`).
- Use `term` for exact values on `keyword` fields; use `range` for range conditions.
- Do not confuse query type with context: the same clause can run in query or filter context depending on where it is placed.
- Declare `minimum_should_match` explicitly when `should` has mandatory semantics.
- Use `should` for optional ranking signals; do not use it in place of `filter` if the user selected a mandatory constraint.
- Do not assume every filter is cached; let Elasticsearch manage caching and measure real workloads.
- Do not manually order filters by selectivity.
- Use `explain` to diagnose a document's score and test relative order on a representative dataset.
- Enforce tenant/authorization conditions at the service and security layer; a filter query alone is not a security boundary.

## 18. Key Takeaways

- Query context both determines matching documents and computes `_score` to evaluate relevance.
- Filter context only checks true/false and contributes no score.
- In `bool`: `must` and `should` run in query context; `filter` and `must_not` run in filter context.
- `should` can either boost scores or become mandatory depending on `minimum_should_match` and other clauses in the `bool` query.
- `match` is not inherently always query context; clause placement determines context.
- Filter context avoids unnecessary scoring and can leverage the node query cache where appropriate; not every filter is cached.
- Use `NativeQuery` to clearly express `bool` queries in Spring Data Elasticsearch when you need control over context and scoring.
- `CriteriaQuery` fits structured filter conditions; for complex scoring needs, verify the generated Query DSL.
- Query relevance and field sorting are two distinct mechanisms; define their priority order clearly.
- Tenant or access-control filters must be enforced at the application/security layer, not relied upon solely from client-submitted queries.

Understanding query context and filter context helps you design queries that are both business-accurate and easy to control in result ordering. Use query context for signals that require scoring, filter context for conditions that restrict the document set, and test both result sets and relevance order on representative data.
