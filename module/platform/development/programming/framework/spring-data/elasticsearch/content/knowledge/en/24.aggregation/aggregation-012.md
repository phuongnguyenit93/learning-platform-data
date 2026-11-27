# Bucket Size, shard_size, Bucket Count, and Resource Cost

Aggregations allow Elasticsearch to group documents and compute statistics such as product counts by category, brand, status, or time range. For fields with many distinct values, a terms aggregation can create a large number of buckets. When data is distributed across multiple shards, Elasticsearch must also collect candidate buckets from each shard and merge them on the coordinating node.

Four concepts to distinguish when designing aggregations:

- **size:** the maximum number of buckets a bucket aggregation such as terms returns in the final result.
- **shard_size:** the number of candidate buckets each shard sends to the coordinating node in a terms aggregation.
- **bucket count:** the total number of buckets created across a request's aggregation tree, including nested buckets.
- **resource cost:** CPU, heap, temporary memory, data transferred between shards and coordinating node, plus response size.

Choosing a size that is too small can omit buckets users need to see. Setting size or shard_size too high can make requests resource-heavy. Good design balances displayed metrics, accuracy, and cost.

## 1. What is a bucket aggregation?

A bucket aggregation divides documents into groups according to a criterion. Each bucket holds documents satisfying that group's condition and can contain sub-aggregations for deeper statistics.

For example, grouping products by category:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  }
}
~~~

If the index has categories ACCESSORIES, OFFICE, HOME, Elasticsearch creates buckets for the selected values. Each bucket typically contains:

- key: the representative value for the bucket.
- doc_count: the number of documents in the bucket.
- Child aggregations if declared.

Illustrative response:

~~~json
{
  "aggregations": {
    "categories": {
      "buckets": [
        { "key": "ACCESSORIES", "doc_count": 120 },
        { "key": "OFFICE", "doc_count": 85 },
        { "key": "HOME", "doc_count": 30 }
      ]
    }
  }
}
~~~

In this example, `terms.size` of 10 asks for at most 10 category buckets in the aggregation result. It does not limit the search request's hits. The top-level `size` property on the search request controls hit count; `terms.size` controls bucket count.

You can set top-level `size` to 0 when you only need aggregations and not a document list.

## 2. size: final number of buckets returned

In a terms aggregation, `size` is the maximum number of buckets the coordinating node returns after merging results across shards.

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 5
      }
    }
  }
}
~~~

The request above fetches at most five brands. By default, a terms aggregation typically returns 10 buckets when `size` is omitted.

### 2.1. size is not the total number of distinct values

Suppose the `brand` field has 2,000 distinct values, yet the request sets `size` to 10. The result contains at most the top 10 buckets according to the default sort criteria. Remaining brands are not returned as buckets in that response.

This does not mean the index only has 10 brands. It simply means the aggregation asked for the top 10.

Helpful fields in the response:

- buckets: the list of buckets actually returned.
- sum_other_doc_count: total document count belonging to buckets omitted from the result list.
- doc_count_error_upper_bound: upper bound on `doc_count` error when Elasticsearch can compute it under the active ordering mode.

`sum_other_doc_count` is not guaranteed to be the exact number of unique documents outside the returned buckets. With multi-valued fields, one document can contribute to multiple buckets, so the summed count can exceed the number of excluded documents.

### 2.2. Choosing size based on the UI

| Need | Initial approach |
| --- | --- |
| Small facets, fixed list of statuses | Set size large enough to hold expected values. |
| Top brands or categories | Choose the top N displayed by the UI, such as 10 or 20. |
| Dashboard with multiple groups | Fetch only buckets actually used in charts. |
| Need to traverse every distinct value | Use composite aggregation instead of setting a massive size. |

There is no universal size fitting every index. Base it on cardinality, shard count, aggregation depth, and UI requirements.

## 3. shard_size: candidate buckets from each shard

In a distributed index, each shard sees only a portion of the data. To produce a top terms aggregation, each shard selects local candidate buckets and sends them to the coordinating node. The coordinating node merges candidates and builds the final bucket list.

`shard_size` controls how many candidate buckets each shard returns in a terms aggregation. This value is usually larger than `size` to reduce the risk of missing a term that has a high global count across the index even if it does not rank at the top of any single shard.

Example:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 10,
        "shard_size": 50
      }
    }
  }
}
~~~

In this example:

- Each shard sends up to 50 candidate buckets.
- The coordinating node merges candidates.
- The final result returns at most 10 buckets.

`shard_size` is not the final bucket count in the response. It governs the volume of intermediate data collected from each shard.

### 3.1. Why is shard_size larger than size?

Suppose there are three shards. A brand has this document distribution:

| Brand | Shard 1 | Shard 2 | Shard 3 | Total |
| --- | ---: | ---: | ---: | ---: |
| ACME | 40 | 0 | 0 | 40 |
| CONTOSO | 0 | 35 | 0 | 35 |
| NORTHWIND | 0 | 0 | 30 | 30 |
| GLOBEX | 15 | 15 | 15 | 45 |

If each shard sends only one candidate bucket, Shard 1 sends ACME, Shard 2 sends CONTOSO, and Shard 3 sends NORTHWIND. The GLOBEX bucket has count 15 on every shard yet ranks first on none, so it can be omitted from candidates. The coordinating node cannot sum counts it never received.

When `shard_size` increases, more local buckets are returned. GLOBEX gets a chance to be sent from all three shards and merged to count 45, thereby ranking first globally.

This example shows that a large `size` alone does not solve distributed inaccuracies. `shard_size` directly affects the completeness of candidates from each shard.

### 3.2. Default value of shard_size

For terms aggregations, Elasticsearch typically computes a default `shard_size` larger than `size`; the standard default formula is:

~~~text
shard_size = size * 1.5 + 10
~~~

This is the default for terms aggregations per current Elasticsearch documentation, not a rule for every bucket aggregation type. Check the documentation for your exact running version if you depend on defaults.

You can set `shard_size` explicitly when tuning accuracy or cost. Avoid multiplying it many times over by default without measuring impact.

## 4. Trade-off between size and shard_size

The two parameters control different stages of execution:

| Parameter | Scope | Increasing the value will | Primary cost |
| --- | --- | --- | --- |
| size | Final result at coordinating node | Return more buckets. | Larger response, more buckets and sub-aggregations retained. |
| shard_size | Candidate bucket set per shard | Send more candidates to merge. | More intermediate data, network traffic, and coordinator memory. |

Increasing `size` shows users more buckets, yet also increases the final bucket count and sub-aggregations computed for them.

Increasing `shard_size` primarily improves candidate completeness and count/top-term accuracy in certain ordering modes. It does not make the final response contain more buckets if `size` stays fixed.

Example:

~~~json
{
  "aggs": {
    "top_categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "shard_size": 100
      }
    }
  }
}
~~~

The final output still returns at most 20 categories, even though each shard can send up to 100 candidates.

## 5. doc_count error in distributed aggregations

Across multiple shards, the coordinating node does not necessarily receive every term from every shard. A term omitted from candidates on one shard can make the final `doc_count` lower than the true total.

Terms aggregations can return additional error metadata:

~~~json
{
  "aggregations": {
    "top_brands": {
      "doc_count_error_upper_bound": 12,
      "sum_other_doc_count": 430,
      "buckets": [
        {
          "key": "GLOBEX",
          "doc_count": 120,
          "doc_count_error_upper_bound": 3
        },
        {
          "key": "ACME",
          "doc_count": 98,
          "doc_count_error_upper_bound": 0
        }
      ]
    }
  }
}
~~~

`doc_count_error_upper_bound` is the upper bound on how much count could be missing, when Elasticsearch can compute that bound for the selected ordering. A value of 0 means no omitted error according to the reported bound. A value of -1 means Elasticsearch cannot determine an error bound for that sort order.

You can request per-bucket error via `show_term_doc_count_error` when supported by the ordering:

~~~json
{
  "aggs": {
    "top_brands": {
      "terms": {
        "field": "brand",
        "size": 10,
        "show_term_doc_count_error": true
      }
    }
  }
}
~~~

Do not interpret `doc_count_error_upper_bound` as a percentage or the exact number of missing documents. It is an upper bound reported by the aggregation algorithm under its current conditions.

### 5.1. Ordering affects accuracy

The default ordering for terms aggregation is descending document count. With this ordering, Elasticsearch can compute useful error bounds and raising `shard_size` can improve accuracy.

Other ordering modes have limitations:

- Sorting by `_key` can guarantee exact counts for returned buckets in supported cases.
- Sorting by `_count` ascending can be inaccurate across multiple shards. If you need rare terms, consider the `rare_terms` aggregation.
- Sorting by a sub-aggregation metric can make top buckets hard to guarantee globally. Elasticsearch guarantees accuracy only for special cases, such as ordering by certain min/max metrics.

If the business relies on exact ranking by a child metric, verify Elasticsearch's ordering limits rather than assuming raising `shard_size` always solves it.

## 6. min_doc_count and shard_min_doc_count

In addition to `size` and `shard_size`, terms aggregation has two document-count thresholds for filtering buckets:

- min_doc_count: minimum documents a bucket must have after merging results across all shards.
- shard_min_doc_count: local count threshold for shards to filter buckets before sending candidates to the coordinating node.

Example fetching only brands with at least 20 documents globally:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 50,
        "min_doc_count": 20
      }
    }
  }
}
~~~

`min_doc_count` is helpful when the UI does not need tiny buckets. However, a bucket excluded from results does not mean documents were deleted; they are simply omitted from the aggregation output.

### 6.1. Risk when shard_min_doc_count is too high

Suppose a term has 30 documents total spread across 10 shards, with 3 documents per shard. If `shard_min_doc_count` is set to 5, every shard drops that term before sending candidates to the coordinator. Even though the global total is 30, the bucket disappears from the result.

Therefore, `shard_min_doc_count` should be set much lower than the global threshold when data is distributed. Unless there is a clear reason, keeping the default is usually safer. Do not use the local threshold as a substitute for `min_doc_count`.

## 7. Bucket count and the max_buckets limit

An aggregation request can generate a nested bucket tree. For example:

- Terms over 20 categories.
- Each category has 30 brands.
- Each brand has 10 inventory statuses.

Bucket counts can grow by the product across levels. In the example above, maximum child buckets can reach thousands, before even counting parent buckets and other aggregation branches.

Elasticsearch enforces `search.max_buckets` to prevent one request from creating too many buckets. The default in modern versions is 65,536 buckets per response; check your cluster configuration and version documentation.

Nested aggregation example:

~~~json
{
  "size": 0,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 100
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 100
          },
          "aggs": {
            "availability": {
              "terms": {
                "field": "availability",
                "size": 10
              }
            }
          }
        }
      }
    }
  }
}
~~~

If each category has 100 brands and each brand has 10 availability buckets, the bucket tree grows rapidly. The `max_buckets` limit applies to total buckets in the result, not just outermost buckets.

When exceeded, Elasticsearch may throw `too_many_buckets_exception`. Do not fix this immediately by raising `max_buckets`. First review how many buckets are actually needed, the size at each level, and whether requests can be paginated or split.

### 7.1. Estimating bucket count

For nested structures with fixed sizes, you can estimate worst-case bucket count by multiplying buckets across levels:

~~~text
outer buckets = 100
middle buckets per outer = 100
inner buckets per middle = 10

approximate bucket count
  = 100 + (100 * 100) + (100 * 100 * 10)
  = 110,100
~~~

This is a simple worst-case estimate. Actual counts may be lower if fewer values exist or `min_doc_count` drops buckets, yet designs should never depend on data remaining sparse by chance.

## 8. Bucket explosion and resource cost

Bucket explosion occurs when a request generates too many buckets or too many sub-aggregations across buckets. It can drive up:

- **Heap and temporary memory:** Elasticsearch must track buckets, counts, metrics, and collector structures.
- **CPU:** each document must be evaluated and placed into matching aggregations.
- **Network traffic:** shards send candidate buckets and aggregation payloads to the coordinating node.
- **Garbage collection:** large numbers of transient objects increase allocation and GC pressure.
- **Response size:** many buckets and metrics inflate returned JSON.
- **Latency:** deep aggregation trees and high cardinality lengthen execution time.

Common causes:

- Setting `terms.size` too large.
- Nesting multiple terms aggregations.
- Using high-cardinality fields like user ID, session ID, or email.
- Attaching expensive sub-aggregations to every bucket.
- Returning too many `top_hits` inside each bucket.
- Running many similar dashboard queries concurrently.
- Aggregating on `text` fields with fielddata causing heap pressure.

## 9. Field cardinality and choosing aggregation types

Cardinality is the number of distinct values in a field. It dictates the potential scale of a terms aggregation.

| Field type | Example | Typical cardinality | Approach |
| --- | --- | --- | --- |
| Status | ACTIVE, DRAFT, ARCHIVED | Low | Small terms aggregation or filters aggregation. |
| Category | ACCESSORIES, OFFICE, HOME | Low to medium | Terms aggregation with appropriate size. |
| Brand | Brand names | Medium | Top-N terms aggregation; composite if scanning all. |
| User ID | User identifiers | High | Avoid returning all buckets in one request; consider composite or cardinality metric. |
| Session ID | Session identifiers | Very high | Usually unsuitable for full bucketing in dashboards. |

You do not always need a terms aggregation returning every value. Choose the API by goal:

- terms: retrieve top N popular values.
- filters: group by a known set of conditions.
- composite: iterate buckets page by page when many or all value combinations are needed.
- cardinality: estimate distinct value count without creating one bucket per value.
- rare_terms: find rare terms instead of sorting terms ascending by count.

### 9.1. Filters aggregation for fixed groups

If the UI only needs known groups such as order statuses, a filters aggregation is often clearer than terms:

~~~json
{
  "aggs": {
    "order_status": {
      "filters": {
        "filters": {
          "active": { "term": { "status": "ACTIVE" } },
          "pending": { "term": { "status": "PENDING" } },
          "archived": { "term": { "status": "ARCHIVED" } }
        }
      }
    }
  }
}
~~~

This creates the exact declared buckets without discovering every distinct value in the field. It fits enums or fixed business categories.

## 10. Composite aggregation for traversing many buckets

Terms aggregation is built primarily to fetch top buckets. When you need to scan all distinct values or combinations of multiple fields, raising `terms.size` to a massive value is not the right solution.

Composite aggregation supports bucket pagination via `after_key`.

Example grouping by category and brand:

~~~json
{
  "size": 0,
  "aggs": {
    "catalog": {
      "composite": {
        "size": 100,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "brand": {
              "terms": {
                "field": "brand"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

The response returns the current page's buckets and optionally `after_key`. Pass `after` in the next request to retrieve the following page of buckets:

~~~json
{
  "size": 0,
  "aggs": {
    "catalog": {
      "composite": {
        "size": 100,
        "after": {
          "category": "ACCESSORIES",
          "brand": "ACME"
        },
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category"
              }
            }
          },
          {
            "brand": {
              "terms": {
                "field": "brand"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

In the application, use the exact `after_key` returned by Elasticsearch as the cursor for the next request; do not infer a cursor from the last bucket when the response provides `after_key`.

Composite aggregation paginates buckets and keeps response sizes bounded. It does not make scanning entire cardinalities free: each page still consumes resources and requires multiple requests. If data mutates during traversal and a consistent view is needed, consider Point in Time (PIT) if your version and API support combining it appropriately.

## 11. Pipeline aggregations do not replace bucket limits

Pipeline aggregations like `bucket_sort` or `bucket_selector` operate on buckets already produced by the parent aggregation.

Example:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 100
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "revenue"
          }
        },
        "top_revenue": {
          "bucket_sort": {
            "sort": [
              { "revenue": { "order": "desc" } }
            ],
            "size": 10
          }
        }
      }
    }
  }
}
~~~

`bucket_sort` can sort and truncate buckets already created by the parent aggregation. It does not stop the parent terms aggregation from collecting initial candidate buckets. Thus, setting `bucket_sort.size` to 10 does not reduce the parent terms aggregation's collection cost to 10 buckets.

Similarly, `bucket_selector` removes buckets after associated metrics have already been computed. It is useful for post-processing logic, not as a substitute for `terms.size`, `shard_size`, or composite pagination.

## 12. How do sub-aggregations increase cost?

Each bucket can hold child metric or bucket aggregations. As parent bucket counts grow, sub-aggregations are evaluated for each corresponding bucket.

Example:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "brands": {
          "terms": {
            "field": "brand",
            "size": 10
          }
        }
      }
    }
  }
}
~~~

With 20 categories and up to 10 brands per category, the aggregation can return up to 200 brand buckets plus category buckets, along with the average price metric. Raising `size` at both levels grows the bucket tree multiplicatively through nesting.

When designing:

- Add only sub-aggregations that the UI actually renders.
- Keep sizes small at deeper levels.
- Avoid nesting terms on high-cardinality fields.
- Split dashboards into independent requests if a single request builds too large a tree and does not need a shared snapshot.
- Consider composite aggregation when scanning bucket combinations.

## 13. collect_mode: depth_first and breadth_first

Terms aggregations support two modes for collecting sub-aggregations:

- depth_first: collects sub-aggregations as documents are collected into parent buckets.
- breadth_first: defers sub-aggregation collection until top parent buckets have been selected.

Example:

~~~json
{
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20,
        "collect_mode": "breadth_first"
      },
      "aggs": {
        "brands": {
          "terms": {
            "field": "brand",
            "size": 10
          }
        }
      }
    }
  }
}
~~~

`breadth_first` can help when parent terms have high cardinality and sub-aggregations are expensive, because it defers sub-aggregation work for parent buckets that do not survive into the top selection. However, it may need to buffer document state for replay on selected buckets, so it does not always use less memory.

The default is typically `depth_first`. Only change `collect_mode` after benchmarking on representative data and understanding the trade-off between sub-aggregation cost and deferral/replay memory.

## 14. execution_hint and global ordinals

Terms aggregations on `keyword` fields normally rely on global ordinals to group terms efficiently. Global ordinals map segment-level terms to shard-wide ordinals.

In some cases you can use `execution_hint` to request another execution strategy, such as `map`:

~~~json
{
  "aggs": {
    "brands": {
      "terms": {
        "field": "brand",
        "size": 20,
        "execution_hint": "map"
      }
    }
  }
}
~~~

`map` can fit selective queries over small document sets, though it is rarely the right default for aggregations over large sets. Global ordinals carry build/update overhead, especially after refresh; eager global ordinals is a mapping option that shifts part of that cost to refresh time rather than the first query.

Do not set `execution_hint` based on guesswork. Profile and benchmark against your actual cardinality, refresh cadence, query selectivity, and shard count. Hint values and behavior can vary across Elasticsearch versions and field types.

## 15. Spring Data Elasticsearch: configuring size and shard_size

In Spring Data Elasticsearch using the Elasticsearch Java API Client, `NativeQuery` carries the aggregation builder. Example:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation brandsAggregation = Aggregation.of(a -> a
        .terms(t -> t
                .field("brand")
                .size(20)
                .shardSize(60)));

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withAggregation("top_brands", brandsAggregation)
        .build();
~~~

In this example:

- `size(20)` requests up to 20 final buckets.
- `shardSize(60)` requests each shard to send up to 60 candidate buckets.
- `top_brands` is the key of the aggregation in the response.

If hits are not needed, you can set page size to 0 using your Spring Data version's API, or use an appropriate query builder to fetch aggregations only. Check the generated request because how hit windows and aggregations are configured depends on the API version.

### 15.1. Setting min_doc_count and show_term_doc_count_error

You can add other options on the terms builder:

~~~java
Aggregation brandsAggregation = Aggregation.of(a -> a
        .terms(t -> t
                .field("brand")
                .size(20)
                .shardSize(60)
                .minDocCount(5)
                .showTermDocCountError(true)));
~~~

Builder methods are generated from the Elasticsearch Java API Client. Method names and parameter types must match the client version managed by Spring Data Elasticsearch in your project.

### 15.2. Reading aggregation results

`ElasticsearchOperations.search(...)` returns `SearchHits<T>`, where aggregation metadata is exposed via Spring Data's aggregation container. How each bucket is extracted depends on the Spring Data Elasticsearch and Elasticsearch Java API Client versions.

When reading the response, distinguish:

- Bucket key.
- doc_count.
- doc_count_error_upper_bound.
- sum_other_doc_count.
- Metrics or sub-aggregations inside each bucket.

Do not substitute the search request's hit count for a bucket's `doc_count`. Hits and aggregations can use different scopes or counting rules.

## 16. Dashboard aggregation design example

Suppose a dashboard needs the top 10 categories and the average price for each category. You can use:

~~~json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "active": true } }
      ]
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 10,
        "shard_size": 30,
        "show_term_doc_count_error": true
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

This design:

- Restricts data by tenant and status before aggregation.
- Returns at most 10 categories.
- Collects up to 30 candidates per shard to reduce the risk of missing top buckets.
- Computes average price over documents inside each category bucket.
- Returns error metadata so the application can assess count accuracy.

If category has low, fixed cardinality, you can raise `size` enough to cover all categories. If category has high cardinality, return only top N or use composite to paginate.

## 17. How to diagnose resource-intensive aggregations

When an aggregation is slow or fails, inspect in order:

1. **Shard count:** how many shards does the request hit? Are any shards oversized or imbalanced?
2. **Cardinality:** how many distinct values does the terms field have?
3. **size and shard_size:** is it requesting too many buckets or too many candidates per shard?
4. **Aggregation tree:** are there multiple levels of terms and sub-aggregations?
5. **Expensive metrics:** are there `top_hits`, scripted metrics, pipelines, or nested aggregations?
6. **Field mapping:** does the field have doc values? Is fielddata enabled on text?
7. **Concurrency:** are many dashboards or users running large aggregations simultaneously?
8. **Bucket limit:** is it hitting `search.max_buckets`?
9. **Response size:** does the client actually need every returned bucket and metric?
10. **Profile:** does query profiling or benchmarking reveal which aggregation stage consumes the time?

The Elasticsearch Profile API helps break down execution time across query/aggregation stages, though it adds overhead. Enable it only during investigation or test requests, never permanently across all production traffic.

Observe cluster metrics such as heap pressure, search thread pool, request circuit breaker, GC, and search latency. If requests are rejected by circuit breakers, raising memory limits should not be the first step; reduce buckets, `shard_size`, sub-aggregations, or concurrency first.

## 18. Common limits and anti-patterns

| Anti-pattern | Consequence | Resolution |
| --- | --- | --- |
| Setting a huge terms size to fetch all values | Huge bucket count, large response, may exceed max_buckets. | Use composite aggregation to paginate. |
| Raising shard_size very high without measuring | Increases intermediate data, network, and coordinator memory. | Increase only when improving top terms/count accuracy. |
| Nesting multiple terms aggregations with large sizes | Bucket count grows as the product across levels. | Reduce sizes at deeper levels, drop unnecessary sub-aggregations. |
| Aggregating by user/session ID for dashboards | High cardinality and huge bucket counts. | Use cardinality metric, composite pagination, or pre-aggregated models. |
| Using ascending count terms to find rare terms | Results can be inaccurate across multiple shards. | Use rare_terms aggregation. |
| Assuming bucket_sort lowers parent aggregation cost | Parent buckets are still collected before the pipeline runs. | Lower size on parent aggregation or use proper pagination. |
| Enabling fielddata on text for terms aggregation | Can spike heap usage severely. | Add a keyword subfield and aggregate on that field. |
| Raising search.max_buckets to silence errors | Allows requests to consume excessive memory. | Optimize the aggregation tree and paginate first. |
| Setting a high shard_min_doc_count | Terms with sufficient global count can be dropped on individual shards. | Keep threshold low or default unless clearly justified. |
| Running many heavy aggregation requests concurrently | Contention on CPU, heap, and request circuit breakers. | Bound concurrency, cache results appropriately, isolate dashboard workloads. |

## 19. Workflow for choosing size and shard_size

When constructing a terms aggregation, follow this sequence:

1. Determine whether the UI needs top N or full bucket traversal.
2. Check field cardinality and verify the mapping supports aggregations via doc values.
3. Choose `size` matching the number of buckets actually displayed.
4. Start with default `shard_size`; increase only when accuracy or ranking requires it.
5. Check `doc_count_error_upper_bound` and `sum_other_doc_count` when counts matter.
6. Use `min_doc_count` to prune tiny buckets when appropriate; avoid high `shard_min_doc_count`.
7. Estimate total buckets when sub-aggregations exist and check against `search.max_buckets`.
8. Use `filters` for fixed groups, `composite` for scanning many buckets, `cardinality` for distinct estimates, and `rare_terms` for rare terms.
9. Apply `collect_mode` or `execution_hint` only after profiling.
10. Test at shard counts, cardinalities, and concurrency levels close to production.

## 20. References

- [Elasticsearch — Terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-terms-aggregation.html)
- [Elasticsearch — Composite aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-composite-aggregation.html)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket.html)
- [Elasticsearch — Search settings: max buckets](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-settings.html)
- [Elasticsearch — Cardinality aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics-cardinality-aggregation.html)
- [Elasticsearch — Rare terms aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-rare-terms-aggregation.html)
- [Spring Data Elasticsearch — NativeQuery and aggregations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

`size` limits the final number of buckets returned; `shard_size` limits the number of candidate buckets each shard sends to the coordinator. Increasing each parameter affects completeness, accuracy, and resource usage differently. For high-cardinality fields or when scanning all buckets, use composite pagination instead of setting a massive `size`. Always factor in nested buckets, sub-aggregations, and concurrency when estimating cost.
