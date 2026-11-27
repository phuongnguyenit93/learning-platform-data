# Distinguishing `filter` and `post_filter` When Building Faceted Statistics

On a product search page, users often browse results while selecting filters such as category, brand, color, or price range. Alongside the product list, the UI also displays counts per value as facets—for example, "Accessories (120)", "Office (85)", or "Acme (70)".

Elasticsearch has two filtering locations that are easily confused:

- `bool.filter` sits inside the `query` section: it restricts the document set used for both search results and aggregations.
- `post_filter` sits at the top level of the search request: it filters the hit list after aggregations have already been computed, so it does not alter bucket counts.

Choosing the right placement determines whether facet counts reflect the user's active selections or still display alternative options. This is the foundation of faceted search and disjunctive faceting.

## 1. Three Filter Concepts to Distinguish

In Elasticsearch, the word "filter" can refer to three distinct mechanisms:

| Mechanism | Position in Request | Effect on Hits | Effect on Aggregations |
| --- | --- | --- | --- |
| `bool.filter` | Inside `query.bool` | Yes | Yes; aggregations only receive documents that matched the query. |
| `post_filter` | At the same level as `query` and `aggs` | Yes | No; aggregations are computed before `post_filter` filters hits. |
| `filter` aggregation | Inside `aggs.<name>.filter` | Does not directly filter hits | Yes; scopes documents for that aggregation and its sub-aggregations. |

All three mechanisms can appear in the same request, serving different purposes.

### 1.1. `bool.filter`

`bool.filter` is a Query DSL clause. Elasticsearch checks whether a document meets the condition without computing a relevance score from that clause. Because the condition is part of the main query, it restricts the input document set for both hits and aggregations.

Conditions well-suited to `bool.filter` include:

- Tenant or data scope the user is authorized to access.
- Mandatory status, such as active products only.
- Category or document type when statistics should also be scoped to that condition.
- Price ranges, date ranges, or geo conditions that should not contribute to the score.

### 1.2. `post_filter`

`post_filter` is a separate top-level section of a search request, outside the `query` object. It only filters returned hits after Elasticsearch has computed aggregations over the documents matching the main query.

This is useful when the UI wants to:

- Show only products matching the facets the user selected.
- Keep displaying counts for other facet choices so the user can switch or broaden selections.
- Compute statistics on the baseline set before applying current facet selections.

`post_filter` also computes no relevance score. However, its key distinction from `bool.filter` is its scope of impact on aggregations.

### 1.3. `filter` Aggregation

A `filter` aggregation defines a separate document scope for a single aggregation. Sub-aggregations inside it run only over documents matching that aggregation's filter condition.

For example, you can build a `categories` aggregation counting only Acme products, while a `brands` aggregation counts over a different scope. This mechanism is essential for disjunctive facet counts—where each facet ignores its own selection while still respecting all other facets.

## 2. `bool.filter` Affects Both Hits and Statistics

Suppose the `products` index has these fields:

| Field | Mapping | Meaning |
| --- | --- | --- |
| `name` | `text` | Product name for full-text search. |
| `tenantId` | `keyword` | Tenant scope. |
| `active` | `boolean` | Whether the product is active. |
| `category` | `keyword` | Product category. |
| `brand` | `keyword` | Brand. |
| `color` | `keyword` | Color. |
| `price` | `long` | Product price. |

Request searching for products whose name relates to `wireless`, belonging to `tenant-42`, active, and priced between 100 and 500:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    },
    "brands": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

In this request, aggregations only count documents satisfying:

1. Product name matches query `wireless`.
2. Belongs to `tenant-42`.
3. Active.
4. Price within 100–500.

When the user has not yet chosen a category or brand, this is usually the desired behavior. All statistics reflect the same baseline result set.

However, if you add `category = ACCESSORIES` into `bool.filter`, the `categories` aggregation also sees only `ACCESSORIES` products. Other category buckets disappear or lose meaningful counts for users wanting to switch categories.

## 3. `post_filter` Keeps Statistics Independent of Selected Facets

Suppose the UI provides category and brand filters. The user selects:

- Category: `ACCESSORIES`.
- Brand: `ACME`.

The goal is for the hit list to show only Acme Accessories products, while category and brand counts are still calculated on the `wireless` baseline within the current tenant before applying those two facet selections.

Place global conditions in `query`, and facet selections in `post_filter`:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": { "field": "category", "size": 20 }
    },
    "brands": {
      "terms": { "field": "brand", "size": 20 }
    }
  }
}
~~~

Results operate in two scopes:

- **Hits:** only products matching `wireless`, belonging to `tenant-42`, active, in category `ACCESSORIES` and brand `ACME`.
- **Aggregations:** statistics over products matching `wireless`, belonging to `tenant-42`, and active; they are not restricted by the category and brand in `post_filter`.

This is the core difference: `post_filter` does not alter bucket counts. When the goal is to keep showing alternative facet options, this is often necessary.

## 4. Example Output and UI Usage

Suppose the baseline set after `query` has these counts:

| Category | Product Count |
| --- | ---: |
| ACCESSORIES | 120 |
| OFFICE | 85 |
| HOME | 30 |

| Brand | Product Count |
| --- | ---: |
| ACME | 70 |
| CONTOSO | 65 |
| NORTHWIND | 40 |

The user selects `ACCESSORIES` and `ACME`. With `post_filter`, hits contain only items matching both selections, while aggregations still return the baseline numbers above.

The UI can continue showing:

- ACCESSORIES (120)
- OFFICE (85)
- HOME (30)
- ACME (70)
- CONTOSO (65)
- NORTHWIND (40)

These numbers are not the counts after applying all active facets. They are the pre-`post_filter` counts. If the product needs each facet to reflect all other active facets while ignoring only itself, use disjunctive facet aggregations in the next section.

## 5. Disjunctive Faceting: Each Statistic Ignores Only Its Own Facet

In e-commerce UIs, the expected behavior is often finer-grained than having every aggregation ignore every selected facet.

Suppose the user currently has selected:

- Category = `ACCESSORIES`.
- Brand = `ACME`.
- Color = `BLACK`.

When showing category counts, we want to keep brand and color applied while ignoring the selected category. When showing brand counts, we want to keep category and color applied while ignoring brand. Likewise, color counts keep category and brand while ignoring color.

This is **disjunctive faceting**:

| Aggregation to Compute | Applied Selections | Ignored Selection |
| --- | --- | --- |
| `categories` | Brand = ACME, Color = BLACK | Category = ACCESSORIES |
| `brands` | Category = ACCESSORIES, Color = BLACK | Brand = ACME |
| `colors` | Category = ACCESSORIES, Brand = ACME | Color = BLACK |

You can implement this using one `filter` aggregation per facet. Each `filter` aggregation applies all selected facet filters except the field it is counting.

### 5.1. Query and post_filter for Hits

The main query holds the full-text search and global mandatory conditions:

~~~json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  }
}
~~~

Hits contain only documents matching all three selected facets. Aggregations are declared at the same level as `query` and `post_filter`.

### 5.2. Category Aggregation Ignoring Selected Category

The `categories` aggregation applies brand and color, omitting category:

~~~json
"aggs": {
  "categories": {
    "filter": {
      "bool": {
        "filter": [
          { "term": { "brand": "ACME" } },
          { "term": { "color": "BLACK" } }
        ]
      }
    },
    "aggs": {
      "values": {
        "terms": {
          "field": "category",
          "size": 20
        }
      }
    }
  }
}
~~~

`categories.values` shows categories containing products of brand ACME and color BLACK in the baseline set. Users can view other categories and switch choices while keeping brand and color intact.

### 5.3. Brand Aggregation Ignoring Selected Brand

~~~json
"brands": {
  "filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  },
  "aggs": {
    "values": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

### 5.4. Color Aggregation Ignoring Selected Color

~~~json
"colors": {
  "filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } }
      ]
    }
  },
  "aggs": {
    "values": {
      "terms": {
        "field": "color",
        "size": 20
      }
    }
  }
}
~~~

All three aggregations can be placed inside the same `aggs` object of a single request. Each aggregation has its own filter so counts reflect that facet's exact scope.

## 6. Distinguishing Filter Aggregation and post_filter

`post_filter` and `filter` aggregations are often used together, yet they do not replace each other:

- `post_filter` decides which documents appear in `hits`.
- `filter` aggregation decides which documents are counted in a specific statistics branch.

For example, a request might have `post_filter` for category `ACCESSORIES`, alongside a `brands` aggregation filtered by category `ACCESSORIES` and color `BLACK`. `post_filter` does not affect aggregations; the filter inside `brands` determines which documents are counted for that branch.

You can use `filter` aggregations even without `post_filter`, such as on a dashboard needing multiple statistical breakdowns across different filter conditions in a single request.

## 7. When Is `global` Aggregation Needed?

A `global` aggregation creates an aggregation scope that ignores the top-level query. It can be useful when you need statistics over the entire index, independent of full-text queries or query filters.

Example:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category"
          }
        }
      }
    }
  }
}
~~~

The `all_products` aggregation ignores the `match` query and aggregates across all documents in the index. That also means it bypasses query filters such as tenant, access control, status, or data scope.

**Never place security conditions solely in `query` and then use a `global` aggregation without re-applying those conditions inside the aggregation.** If an aggregation returns buckets or counts belonging to another tenant, information can leak even when hits are properly scoped.

For example, when using `global` aggregation in a multi-tenant environment, put the tenant scope inside a `filter` aggregation nested under `global`:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } }
      ]
    }
  },
  "aggs": {
    "all_products_for_tenant": {
      "global": {},
      "aggs": {
        "tenant_scope": {
          "filter": {
            "term": { "tenantId": "tenant-42" }
          },
          "aggs": {
            "categories": {
              "terms": { "field": "category" }
            }
          }
        }
      }
    }
  }
}
~~~

Here, the tenant filter is repeated inside the global scope to ensure statistics remain tenant-isolated. Apply the same precaution to every mandatory authorization constraint.

## 8. Using `NativeQuery` in Spring Data Elasticsearch

`NativeQuery` supports Elasticsearch Java API Client builders, including queries, aggregations, and filters. In modern Spring Data Elasticsearch APIs, `NativeQueryBuilder.withFilter(...)` sets the search-request-level filter corresponding to `post_filter`, whereas `withQuery(...)` sets the main query. Check the API of the Spring Data Elasticsearch version used in your project.

The example below keeps tenant and status in `query`, while putting user-selected category and brand in `post_filter`. Category and brand aggregations are computed on the baseline set before `post_filter`:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("wireless")))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value(FieldValue.of("tenant-42"))))
                .filter(f -> f.term(t -> t
                        .field("active")
                        .value(FieldValue.of(true))))))
        .withFilter(f -> f.bool(b -> b
                .filter(x -> x.term(t -> t
                        .field("category")
                        .value(FieldValue.of("ACCESSORIES"))))
                .filter(x -> x.term(t -> t
                        .field("brand")
                        .value(FieldValue.of("ACME"))))))
        .withAggregation("categories", Aggregation.of(a -> a
                .terms(t -> t.field("category").size(20))))
        .withAggregation("brands", Aggregation.of(a -> a
                .terms(t -> t.field("brand").size(20))))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

In this snippet:

- `withQuery(...)` builds the main query; tenant and active sit in `bool.filter`, so they restrict both hits and aggregations.
- `withFilter(...)` places user-selected facets into the top-level post-filter, so they restrict hits only.
- `withAggregation(...)` declares category and brand statistics.
- `operations.search(...)` executes the request and returns `SearchHits` along with aggregation metadata.

To implement disjunctive faceting, define each aggregation via `Aggregation.of(...)` with a `filter` aggregation wrapping the `terms` aggregation, just like the REST API examples above. That way, each facet ignores its own selection while applying the remaining selections.

### 8.1. Reading Aggregations from Spring Data Results

`SearchHits<T>` holds both hits and the aggregation response. Exact accessor APIs and container types depend on the Spring Data Elasticsearch version; use `SearchHits.getAggregations()` with the corresponding aggregation result types from your project's dependencies.

When parsing results, distinguish the bucket counts of `categories`, `brands`, and the `values` buckets inside a `filter` aggregation. With a `filter` aggregation, `docCount` at the filter level is the document count matching the filter; the child `terms` buckets hold the counts per facet value.

Never use total hits after `post_filter` as a substitute for aggregation counts. Those two numbers represent two different sets of documents.

## 9. Complete Example with Filter Aggregations for Multiple Facets

The following request demonstrates a baseline set, selected facets, and three independent statistics branches. The main query restricts tenant and status; `post_filter` restricts hits by category, brand, and color; each aggregation ignores the filter on the field it is counting:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "wireless" } }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "post_filter": {
    "bool": {
      "filter": [
        { "term": { "category": "ACCESSORIES" } },
        { "term": { "brand": "ACME" } },
        { "term": { "color": "BLACK" } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "brand": "ACME" } },
            { "term": { "color": "BLACK" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "category", "size": 20 }
        }
      }
    },
    "brands": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "category": "ACCESSORIES" } },
            { "term": { "color": "BLACK" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "brand", "size": 20 }
        }
      }
    },
    "colors": {
      "filter": {
        "bool": {
          "filter": [
            { "term": { "category": "ACCESSORIES" } },
            { "term": { "brand": "ACME" } }
          ]
        }
      },
      "aggs": {
        "values": {
          "terms": { "field": "color", "size": 20 }
        }
      }
    }
  }
}
~~~

This request produces three sets of statistics:

1. `categories.values`: categories in the baseline set after applying brand ACME and color BLACK.
2. `brands.values`: brands in the baseline set after applying category ACCESSORIES and color BLACK.
3. `colors.values`: colors in the baseline set after applying category ACCESSORIES and brand ACME.

Hits remain restricted by all three facet selections thanks to `post_filter`. The bucket counts allow the UI to display alternative options across the remaining facets.

## 10. Multi-Select Facets: OR or AND?

When a user selects multiple values within the same facet, define the semantics before building the query.

For example, the user selects two categories `ACCESSORIES` and `OFFICE`:

- If a product only needs to belong to either category, use a `terms` query. This is OR across values in the same field.
- If a document must satisfy both conditions, you need a different data model and query pattern suited to AND semantics; you cannot assume `terms` produces AND.

OR example:

~~~json
{
  "terms": {
    "category": ["ACCESSORIES", "OFFICE"]
  }
}
~~~

When building disjunctive facets, the filter for one facet must mirror the multi-select semantics of the other facets. If a facet uses OR across selected values, preserve that OR inside the `filter` aggregation. If business logic requires AND across values, express each condition separately and verify mappings, especially for array fields.

## 11. Mandatory Conditions Must Stay in Query

Do not push every condition into `post_filter`. Conditions that enforce data security or define the global statistical scope must reside in the main query.

Examples:

- Tenant scope.
- User or organization access rights.
- Permitted data visibility scope.
- Soft-delete flags or conditions excluding unauthorized documents.

If you only place a tenant filter in `post_filter`, hits will be scoped to the tenant, yet aggregations will still count other tenants' documents. Bucket names and counts can leak the existence or distribution of out-of-scope data.

Placing the tenant filter in `query.bool.filter` applies it to both hits and aggregations. If using a `global` aggregation, re-apply tenant/authorization filters inside the global branch because `global` bypasses the main query.

## 12. Performance and Accuracy of Statistics

Aggregations can become resource-intensive when document counts or field cardinality are high. Key considerations:

- Create only the aggregations the UI actually needs.
- Choose a reasonable `size` on `terms` aggregations to cap returned buckets.
- For high cardinality or exhaustive bucket pagination, consider `composite` aggregations with `after_key`.
- Distributed `terms` aggregations across multiple shards can have approximate counts due to candidate bucket selection; check `doc_count_error_upper_bound` and `sum_other_doc_count` when assessing accuracy.
- You can tune `shard_size` to improve `terms` aggregation accuracy, trading off memory and data transferred between shards and the coordinating node.
- Avoid deeply nested aggregations or redundant `filter` aggregations unless necessary.
- Benchmark requests on representative data; bucket counts, shard counts, and term distributions heavily influence cost.

`post_filter` does not make aggregations cheaper: aggregations still run on the baseline query set, which is usually broader than the final hit set. That is why it works for faceted search, and also why you must bound the baseline set size and aggregation count.

## 13. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Selecting a category makes all other categories disappear from statistics | Category filter was placed in `query.bool.filter`. | Move facet selections to `post_filter` or use a `filter` aggregation ignoring the current facet. |
| Hits are not restricted by selected facets | Conditions were placed only in aggregation filters. | Add facet selections to `post_filter` to filter hits. |
| All facet counts ignore every other selection | Using plain `terms` aggregations with `post_filter`. | Use a separate `filter` aggregation per facet keeping other filters and ignoring only itself. |
| Statistics include another tenant's data | Tenant was placed only in `post_filter` or omitted inside `global` aggregation. | Put tenant scope in `query` and repeat it inside `global` branches when used. |
| Aggregations do not reflect desired price range or full-text search | Global baseline conditions were mistakenly placed in `post_filter`. | Move global conditions into `query.bool.filter` or the main query. |
| Bucket counts do not equal total hits | Aggregations and hits operate on different document scopes. | Clarify `query`, `post_filter`, and each branch's `filter` aggregation. |
| Some `terms` buckets are missing or counts are slightly off | `terms` aggregation has bucket/shard candidate limits or high cardinality. | Inspect error fields, tune `size`/`shard_size`, or use `composite` aggregations. |
| `NativeQuery` filter behaves unexpectedly | Confused `withFilter` with `bool.filter` inside `query`. | Inspect the generated request; `withFilter` is `post_filter`, whereas `bool.filter` lives inside `query`. |

## 14. Workflow for Designing Faceted Filters

When building a search page with facets, follow this sequence:

1. Define the search baseline: full-text query, tenant scope, authorization, and global conditions.
2. Put global conditions into `query`, using `bool.filter` for conditions not needing relevance scores.
3. Identify user-selectable facets and each facet's multi-select semantics.
4. Put selections meant only to filter hits into top-level `post_filter`.
5. If all aggregations should count over the same baseline set, use `terms` aggregations directly.
6. If each facet must ignore its own selection while keeping other facet selections, create a separate `filter` aggregation per facet.
7. Use `global` aggregations only when truly needing to bypass the main query; re-apply tenant and authorization filters inside the `global` branch.
8. Verify hits and bucket counts on sample data spanning multiple categories/brands/colors.
9. Evaluate cardinality, bucket counts, shard count, and `terms` aggregation accuracy.
10. Inspect the emitted Query DSL to confirm placement of `query`, `post_filter`, and `aggs`.

## 15. References

- [Elasticsearch — Filter search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/filter-search-results.html)
- [Elasticsearch — Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html)
- [Elasticsearch — Filter aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-filter-aggregation.html)
- [Elasticsearch — Global aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-global-aggregation.html)
- [Spring Data Elasticsearch — NativeQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

`bool.filter` restricts the document set for both hits and aggregations. Top-level `post_filter` filters hits only after aggregations are computed. `filter` aggregations define dedicated scopes for individual statistics branches. Combining these three mechanisms properly enables faceted search with accurate counts while keeping tenant and authorization filters safely enforced on statistics.
