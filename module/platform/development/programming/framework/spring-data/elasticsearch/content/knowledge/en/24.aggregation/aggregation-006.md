# Nested Aggregations and Combining Metrics with Buckets

Elasticsearch Aggregations summarize data directly on the cluster: grouping documents by category, status, or time interval; then calculating sums, averages, min/max, counts, or statistical indicators for each group. When an aggregation contains child aggregations, the result can represent multiple levels of analysis in a single search request.

The two fundamental categories are **bucket aggregations** and **metric aggregations**:

- Bucket aggregations divide documents into groups (buckets) based on a criterion, such as `terms`, `range`, `date_histogram`, `filters`, or `nested`.
- Metric aggregations compute one or more values over the documents within a bucket, such as `sum`, `avg`, `min`, `max`, `stats`, `cardinality`, or `value_count`.

Combining them allows answering questions such as:

- How many products are in each category and what is their average price?
- What is the monthly revenue per sales channel?
- Within each category, what is the average review rating?
- How many products does each brand have in each status?
- What is the average monthly revenue across months?

In Spring Data Elasticsearch, you can construct aggregations using the Elasticsearch Java API Client DSL, attach them to `NativeQuery`, execute via `ElasticsearchOperations`, and read results from `SearchHits.getAggregations()`.

## 1. Two meanings of "nested" to distinguish

In Elasticsearch, the phrase nested aggregation can refer to two different mechanisms:

1. **Sub-aggregations:** placing a bucket or metric aggregation inside another bucket aggregation for multi-level analysis. For example: grouping by category, within each category grouping by brand, and then computing average price.
2. **Nested aggregation:** switching the calculation scope from parent documents to nested documents inside a field mapped as `nested`. For example: moving from products to product reviews to calculate average rating.

Both mechanisms can be used simultaneously. A category bucket can contain a nested aggregation to analyze reviews of products within each category.

```text
Search request
    |
    v
Bucket: group by category
    |
    +-- Metric: average product price
    |
    +-- Bucket: group by brand
    |       |
    |       +-- Metric: product count / max price
    |
    +-- Nested: enter reviews
            |
            +-- Metric: average review rating
            |
            +-- Bucket: group by reviewer
```

## 2. What is a bucket aggregation?

A bucket aggregation partitions documents into groups based on a condition. Each bucket has `doc_count`, which is the number of documents falling into that bucket within the aggregation scope.

Common bucket aggregations:

| Aggregation | How groups are formed | Example |
|---|---|---|
| `terms` | By each distinct field value. | Group products by `category`. |
| `range` | By numeric or date intervals. | Group orders by amount brackets. |
| `date_histogram` | By regular time intervals. | Daily/monthly revenue. |
| `filters` | By application-defined query filters. | Group orders by business statuses. |
| `filter` | A single bucket containing documents matching a condition. | Aggregate only `PAID` orders. |
| `nested` | Enter nested documents at a given path. | Aggregate reviews inside a product. |
| `reverse_nested` | Return from nested documents to parent document. | Count/compute metrics on products with matching reviews. |
| `composite` | Create buckets from multiple sources with bucket pagination. | Export statistics for all category/brand pairs. |

### 2.1. `terms` aggregation

`terms` creates one bucket per distinct field value:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 10
      }
    }
  }
}
```

The result has one bucket per returned category, along with `key` and `doc_count`. `size: 10` in `terms` is the maximum number of buckets returned, not the number of documents in each bucket.

Fields used for `terms` are typically `keyword`, numeric, or other aggregatable types. Do not use a plain `text` field to group by the entire string; use a `keyword` subfield or a field with appropriate doc values.

### 2.2. `range` aggregation

`range` creates buckets by intervals:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_price_range": {
      "range": {
        "field": "price",
        "ranges": [
          { "to": 1000000 },
          { "from": 1000000, "to": 5000000 },
          { "from": 5000000 }
        ]
      }
    }
  }
}
```

Intervals follow `[from, to)` semantics: `from` is inclusive, `to` is exclusive. Therefore, a product priced at exactly 1,000,000 belongs to the second bucket in this example.

### 2.3. `date_histogram` aggregation

`date_histogram` groups documents by day, week, month, or time interval:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
```

`calendar_interval` fits calendar intervals (day/month/year); `fixed_interval` fits fixed durations like 15 minutes or 1 hour. When reporting by business day, specify the timezone explicitly to prevent shifted buckets when data is stored in UTC.

## 3. What is a metric aggregation?

A metric aggregation computes values over documents in the current scope. Metrics can return a single value (single-value) or multiple values (multi-value).

| Metric | Result | Example |
|---|---|---|
| `sum` | Sum of values | Total revenue. |
| `avg` | Average | Average product price. |
| `min` / `max` | Minimum/maximum | Lowest/highest price. |
| `value_count` | Count of values counted | Number of present field values. |
| `cardinality` | Approximate count of distinct values | Number of unique customers. |
| `stats` | `count`, `min`, `max`, `avg`, `sum` | Price statistics. |
| `extended_stats` | Extended stats including standard deviation and related values | Price distribution analysis. |
| `percentiles` | Percentiles | P50, P90, P95 of processing time. |
| `weighted_avg` | Weighted average | Average price weighted by quantity sold. |

Metric aggregations do not create new buckets. They return calculated results within the document scope determined by the query or parent bucket.

Example `avg` across all products:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
```

If a field is missing or lacks a numeric value, that document does not contribute a value to the `avg` metric. Therefore, `avg` does not necessarily equal `sum / bucket doc_count` when some documents are missing the `price` field.

### 3.1. `value_count` does not always equal `doc_count`

`doc_count` counts documents in the bucket. `value_count` counts field values evaluated. For a single-valued field present on every document, the two numbers can match. For missing or multi-valued fields, they can differ.

For example, a document with three tags contributes three values to `value_count(tags)` but only one to the bucket's `doc_count`.

### 3.2. `cardinality` is an approximation

`cardinality` uses the HyperLogLog++ algorithm to estimate the number of distinct values. It is useful on large datasets when you need a distinct count at lower cost than building all buckets, though you should not assume the result is always strictly exact.

If the business requires an exact distinct count, choose a suitable solution and evaluate cost, such as a composite aggregation to paginate distinct values or processing in a dedicated store.

## 4. Combining metrics inside buckets

This is the most common aggregation pattern: buckets partition data into groups, and child metrics compute statistics within each group.

Example: counting products by category and calculating average, minimum, and maximum price for each category:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "minimum_price": {
          "min": {
            "field": "price"
          }
        },
        "maximum_price": {
          "max": {
            "field": "price"
          }
        },
        "price_stats": {
          "stats": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

Conceptual result structure:

```json
{
  "aggregations": {
    "by_category": {
      "buckets": [
        {
          "key": "KEYBOARD",
          "doc_count": 120,
          "average_price": { "value": 2450000.0 },
          "minimum_price": { "value": 350000.0 },
          "maximum_price": { "value": 8900000.0 },
          "price_stats": {
            "count": 118,
            "min": 350000.0,
            "max": 8900000.0,
            "avg": 2450000.0,
            "sum": 289100000.0
          }
        }
      ]
    }
  }
}
```

Numbers in the response are illustrative. Notice that `doc_count` is 120 while `price_stats.count` is 118 because two documents lack a numeric `price` value.

### 4.1. Child buckets inside parent buckets

You can continue grouping by another field. For example, group products by category, then within each category group by brand and compute average price:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "by_brand": {
          "terms": {
            "field": "brand.keyword",
            "size": 10
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
  }
}
```

The result has the structure category → brand → average price. The `average_price` metric is computed separately inside each brand bucket, not across the entire category.

Bucket counts can multiply quickly when nesting multiple levels. If each category has 100 brands and there are 100 categories, one aggregation can create thousands of buckets. Set `size`, constrain cardinality, and consider `composite` if all groups must be scanned.

## 5. Combining multiple metrics in the same bucket

One bucket can contain multiple metric aggregations simultaneously. Example report by order status:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status.keyword"
      },
      "aggs": {
        "total_amount": {
          "sum": {
            "field": "amount"
          }
        },
        "average_amount": {
          "avg": {
            "field": "amount"
          }
        },
        "order_stats": {
          "stats": {
            "field": "amount"
          }
        },
        "unique_customers": {
          "cardinality": {
            "field": "customer_id"
          }
        }
      }
    }
  }
}
```

Each status has:

- Order count in `doc_count`.
- Total amount in `total_amount`.
- Average value in `average_amount`.
- Detailed statistics in `order_stats`.
- Estimated distinct customers in `unique_customers`.

This is an efficient way to build a multi-metric dashboard in a single request instead of sending a separate search for each metric. Still, multi-level or high-cardinality aggregations carry notable cost; measure real requests.

## 6. Filtering documents before bucketing and metrics

The search-level query determines the input document set for all aggregations. You can combine query context and filter context, though when a dashboard only needs statistics for documents satisfying business conditions, filters in a `bool` query are typically used.

Example aggregating only paid orders within a quarter:

```json
GET /orders/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "PAID" } },
        {
          "range": {
            "created_at": {
              "gte": "2026-07-01T00:00:00Z",
              "lt": "2026-10-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        }
      }
    }
  }
}
```

All buckets and metrics here see only `PAID` orders within the selected time window.

### 6.1. Filter aggregation inside a bucket

If you need multiple subsets inside the same group, use `filters` or `filter` aggregation inside the bucket.

For example, within each category, compute revenue separately for paid and pending orders:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword"
      },
      "aggs": {
        "by_status": {
          "filters": {
            "filters": {
              "paid": { "term": { "status": "PAID" } },
              "pending": { "term": { "status": "PENDING" } }
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        }
      }
    }
  }
}
```

The result has `paid` and `pending` buckets inside each category, each with its own `doc_count` and `revenue` metric. Unlike a filter placed in the top-level query, a filter aggregation applies only to that child aggregation branch; sibling branches of the same bucket can still see the broader document set.

## 7. Nested aggregations on `nested`-type fields

In JSON, a product can contain an array of reviews:

```json
{
  "product_id": "P-100",
  "category": "KEYBOARD",
  "price": 2500000,
  "reviews": [
    { "reviewer": "u1", "rating": 5 },
    { "reviewer": "u2", "rating": 4 }
  ]
}
```

If you need to query and aggregate elements inside an object array independently, the `reviews` field must be mapped as `nested`:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "product_id": { "type": "keyword" },
      "category": { "type": "keyword" },
      "price": { "type": "double" },
      "reviews": {
        "type": "nested",
        "properties": {
          "reviewer": { "type": "keyword" },
          "rating": { "type": "integer" },
          "created_at": { "type": "date" }
        }
      }
    }
  }
}
```

`nested` guarantees that the fields of each array element remain bound within the same nested document. With a standard `object` mapping, Elasticsearch flattens object arrays and multi-field queries can cross-match across different elements.

### 7.1. Nested aggregation

To compute the average review rating, enter the `reviews` nested path:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "review_data": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "average_rating": {
          "avg": {
            "field": "reviews.rating"
          }
        },
        "rating_distribution": {
          "terms": {
            "field": "reviews.rating"
          }
        }
      }
    }
  }
}
```

After entering `review_data`, sub-aggregations execute on nested review documents instead of product documents. Therefore:

- `average_rating` averages over reviews that have a rating.
- `rating_distribution` creates buckets by rating value.
- `review_data.doc_count` is the count of nested review documents, not products.

### 7.2. Nested aggregation inside a parent bucket

You can group products by category first, then compute review ratings within each category:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      },
      "aggs": {
        "reviews": {
          "nested": {
            "path": "reviews"
          },
          "aggs": {
            "average_rating": {
              "avg": {
                "field": "reviews.rating"
              }
            },
            "review_count": {
              "value_count": {
                "field": "reviews.rating"
              }
            }
          }
        }
      }
    }
  }
}
```

Within each category:

- The `by_category` bucket contains product documents.
- `reviews` switches scope to nested review documents belonging to products in that category.
- `average_rating` computes the average rating of reviews in the group.
- `review_count` counts present rating values.

Do not compare `by_category.doc_count` with `reviews.doc_count` as if they shared the same unit. One product can have many reviews, so the nested document count can exceed the product count.

## 8. `reverse_nested`: returning from nested documents to parent documents

After entering a nested path, child aggregations operate in the nested document context. If you need to compute metrics on the parent product, use `reverse_nested` to return to parent documents.

Example: group reviews by rating, then count how many products have at least one review at each rating and compute the average price of those products:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "reviews": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "by_rating": {
          "terms": {
            "field": "reviews.rating"
          },
          "aggs": {
            "products": {
              "reverse_nested": {},
              "aggs": {
                "average_product_price": {
                  "avg": {
                    "field": "price"
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

Results:

- `reviews.doc_count` is the number of reviews.
- `by_rating.doc_count` is the number of nested reviews with that rating.
- `products.doc_count` is the number of parent products having at least one review in that rating bucket.
- `average_product_price` calculates price across the returned parent products.

A single product can have multiple reviews with the same rating, yet in `reverse_nested` it is counted only once in the corresponding parent bucket. Thus, the parent product count usually differs from the review count.

You can specify `path` for `reverse_nested` when returning to a specific nested ancestor; if omitted, the aggregation returns to the root document.

## 9. Nested queries and nested aggregations are not the same

The two APIs have similar names but perform different tasks:

- `nested` query determines which parent documents match a condition on a nested child.
- `nested` aggregation shifts aggregation scope into the corresponding nested children.

Example finding products with a review rating of 4 or higher:

```json
GET /products/_search
{
  "query": {
    "nested": {
      "path": "reviews",
      "query": {
        "range": {
          "reviews.rating": {
            "gte": 4
          }
        }
      }
    }
  },
  "aggs": {
    "matching_reviews": {
      "nested": {
        "path": "reviews"
      },
      "aggs": {
        "high_ratings": {
          "filter": {
            "range": {
              "reviews.rating": {
                "gte": 4
              }
            }
          },
          "aggs": {
            "average_rating": {
              "avg": {
                "field": "reviews.rating"
              }
            }
          }
        }
      }
    }
  }
}
```

The top-level nested query restricts which parent products are returned. However, the nested aggregation does not automatically restrict itself to only the reviews that matched the nested query; it enters all reviews belonging to those parent products. Therefore, if the metric must only include reviews rated 4 or higher, add a `filter` aggregation inside the nested aggregation as shown.

This is a common pitfall: search hits are right, yet aggregations include nested children that fail the detailed condition. Place filters at the nested level when metrics must cover only a subset of reviews.

## 10. Pipeline aggregations: computing metrics from other aggregation results

Standard metric aggregations compute on document fields. Pipeline aggregations compute based on the results of other aggregations, typically already-created buckets or metrics.

Some pipeline aggregations:

| Pipeline aggregation | Purpose |
|---|---|
| `avg_bucket` | Compute average of a metric across multiple buckets. |
| `sum_bucket` | Sum a metric across multiple buckets. |
| `min_bucket` / `max_bucket` | Find the minimum/maximum metric value across buckets. |
| `stats_bucket` | Statistics over metric values across buckets. |
| `bucket_script` | Evaluate an expression from one or more metrics in a bucket. |
| `bucket_selector` | Keep or drop buckets via a script condition. |
| `derivative` | Compute change between ordered buckets. |
| `cumulative_sum` | Compute running cumulative sum across buckets. |

Pipeline aggregations do not re-query documents. They consume results from aggregations already computed in the request.

### 10.1. `avg_bucket`: averaging a metric across buckets

Example computing the average price per category, then averaging those averages:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    },
    "average_of_category_averages": {
      "avg_bucket": {
        "buckets_path": "by_category>average_price"
      }
    }
  }
}
```

`buckets_path` uses `>` to traverse to child metric `average_price` inside bucket aggregation `by_category`.

Note: the average of category averages does not necessarily equal the average price across all products. For instance, category A has 10 products with average price 100; category B has 100 products with average price 200. The average of the two category averages is 150, while the average across all 110 products is about 190.91. Choose the metric matching the business question.

### 10.2. `bucket_script`: computing an indicator from multiple metrics

Example reporting monthly revenue and order count, then calculating average order value:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "order_count": {
          "value_count": {
            "field": "order_id"
          }
        },
        "average_order_value": {
          "bucket_script": {
            "buckets_path": {
              "total": "revenue",
              "count": "order_count"
            },
            "script": "params.count > 0 ? params.total / params.count : 0"
          }
        }
      }
    }
  }
}
```

In each monthly bucket, `bucket_script` reads two child metrics:

- `revenue` mapped to variable `params.total`.
- `order_count` mapped to variable `params.count`.

Then the script computes `total / count`. Checking `count > 0` avoids division by zero. If `order_id` can be multi-valued or missing, verify whether `value_count` truly represents order count; a single-valued always-present field or a better-suited metric may be needed.

### 10.3. `bucket_selector`: filtering buckets by metric

If you only want to keep months with revenue of 100 million or more:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "minimum_revenue": {
          "bucket_selector": {
            "buckets_path": {
              "total": "revenue"
            },
            "script": "params.total >= 100000000"
          }
        }
      }
    }
  }
}
```

`bucket_selector` drops buckets from the aggregation response after metrics have been computed. It does not reduce the number of documents processed by earlier aggregations; therefore, do not treat it as a replacement for query/filter aggregations when the goal is reducing input data.

### 10.4. `derivative` and `cumulative_sum`

With a monthly revenue series, you can compute month-over-month change:

```json
GET /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month": {
      "date_histogram": {
        "field": "created_at",
        "calendar_interval": "month",
        "min_doc_count": 0
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "revenue_change": {
          "derivative": {
            "buckets_path": "revenue"
          }
        },
        "running_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }
  }
}
```

These pipelines depend on bucket ordering. With date histogram, chronological order is determined by bucket key. The first bucket has no preceding bucket, so derivative usually has no value there. `min_doc_count: 0` can generate empty buckets within appropriate extended bounds; if you need every month without orders included, configure bounds and handle empty values per reporting goals.

## 11. Combining multiple levels: revenue by month and category

A dashboard might need revenue per category in each month. You can nest `terms` and `date_histogram`, then place `sum` metrics at the leaf level:

```json
GET /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-01-01T00:00:00Z",
        "lt": "2027-01-01T00:00:00Z"
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category.keyword",
        "size": 20
      },
      "aggs": {
        "by_month": {
          "date_histogram": {
            "field": "created_at",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "order_count": {
              "value_count": {
                "field": "order_id"
              }
            }
          }
        }
      }
    }
  }
}
```

Result structure:

```text
by_category
  KEYBOARD (bucket)
    by_month
      2026-01 (bucket)
        revenue (sum)
        order_count (value_count)
      2026-02 (bucket)
        revenue (sum)
        order_count (value_count)
  ACCESSORIES (bucket)
    by_month
      2026-01 (bucket)
        revenue (sum)
        order_count (value_count)
```

When reading results, iterate through each category bucket, then each month bucket, and extract that month's metrics. Do not read `revenue` at the category level if it was only defined at the month level.

## 12. `composite` when iterating over all buckets

`terms` aggregation returns a limited number of buckets per `size` and usually sorts by document count or key. If there are tens of thousands of category/brand combinations and all must be exported, setting `terms.size` very high is not suitable.

`composite` aggregation builds buckets from one or more sources and supports pagination with an `after` key:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "category": {
              "terms": {
                "field": "category.keyword"
              }
            }
          },
          {
            "brand": {
              "terms": {
                "field": "brand.keyword"
              }
            }
          }
        ]
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
```

The response may contain `after_key`. To fetch the next page of buckets, pass that exact value into `composite.after`:

```json
{
  "size": 0,
  "aggs": {
    "category_brand": {
      "composite": {
        "size": 500,
        "after": {
          "category": "KEYBOARD",
          "brand": "OMEGA"
        },
        "sources": [
          { "category": { "terms": { "field": "category.keyword" } } },
          { "brand": { "terms": { "field": "brand.keyword" } } }
        ]
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
```

In production code, always use the `after_key` returned by Elasticsearch; do not construct it from the last bucket because `after_key` does not always match the last bucket's key in the response. If you need consistent results across multiple composite requests while the index changes, combine an appropriate snapshot strategy such as PIT as supported by your Elasticsearch version and verify aggregation request semantics.

## 13. Building aggregations with Spring Data Elasticsearch

Modern Spring Data Elasticsearch uses the Elasticsearch Java API Client for `NativeQuery`. The aggregation type is `co.elastic.clients.elasticsearch._types.aggregations.Aggregation`.

Example creating buckets by category and an average price metric:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t
                .field("category.keyword")
                .size(20)
        )
        .aggregations("average_price", averagePrice)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withMaxResults(0)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
```

Meaning:

- `averagePrice` defines an `avg` metric aggregation on the `price` field.
- `byCategory` defines a `terms` bucket on `category.keyword`.
- `.aggregations("average_price", averagePrice)` places the metric as a sub-aggregation inside each category bucket.
- `.withAggregation("by_category", byCategory)` attaches the aggregation to the search query.
- `.withMaxResults(0)` requests zero document hits if only aggregations are needed; check the corresponding builder API for your Spring Data version.

If you need both document hits and aggregations, set max results/pageable to the required hit count instead of 0.

### 13.1. Nested aggregation via Java API Client DSL

Example creating a nested aggregation to compute average rating:

```java
Aggregation averageRating = Aggregation.of(a -> a
        .avg(avg -> avg.field("reviews.rating"))
);

Aggregation nestedReviews = Aggregation.of(a -> a
        .nested(n -> n.path("reviews"))
        .aggregations("average_rating", averageRating)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("review_data", nestedReviews)
        .withMaxResults(0)
        .build();
```

If you need buckets by rating inside the nested context, you can nest `terms` inside `nestedReviews` and add child metrics or buckets similar to the Query DSL example.

### 13.2. Nesting multiple buckets and metrics

Example category → brand → average price:

```java
Aggregation averagePrice = Aggregation.of(a -> a
        .avg(avg -> avg.field("price"))
);

Aggregation byBrand = Aggregation.of(a -> a
        .terms(t -> t.field("brand.keyword").size(10))
        .aggregations("average_price", averagePrice)
);

Aggregation byCategory = Aggregation.of(a -> a
        .terms(t -> t.field("category.keyword").size(20))
        .aggregations("by_brand", byBrand)
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("by_category", byCategory)
        .withMaxResults(0)
        .build();
```

`Aggregation` objects can be built separately and nested together. This helps split large queries into named, reusable components.

## 14. Reading aggregation results from `SearchHits`

When executed via `ElasticsearchOperations.search`, the result returns `SearchHits<T>`. Aggregations reside in `getAggregations()`, not inside the entity's `getContent()`.

With the ELC client in Spring Data Elasticsearch, results are typically wrapped by `ElasticsearchAggregations` and each aggregation by `ElasticsearchAggregation`:

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsAggregate;
import co.elastic.clients.elasticsearch._types.aggregations.StringTermsBucket;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits = operations.search(query, ProductDocument.class);

ElasticsearchAggregations aggregations =
        (ElasticsearchAggregations) hits.getAggregations();

ElasticsearchAggregation categoryAggregation =
        aggregations.get("by_category");

Aggregate categoryAggregate = categoryAggregation.aggregation();
StringTermsAggregate terms = categoryAggregate.sterms();

for (StringTermsBucket bucket : terms.buckets().array()) {
    String category = bucket.key().stringValue();
    long productCount = bucket.docCount();

    Aggregate averagePriceAggregate = bucket.aggregations().get("average_price");
    double averagePrice = averagePriceAggregate.avg().value();

    System.out.printf("%s: count=%d, avgPrice=%.2f%n",
            category, productCount, averagePrice);
}
```

This snippet demonstrates accessing a String terms aggregation from the Elasticsearch Java API Client. Specific aggregate types depend on the bucket kind and client version. For `long`, `date_histogram`, `range`, `nested`, or other metrics, use the corresponding accessor on the `Aggregate` union.

If only aggregation results are needed, the query can set returned hits to 0 to avoid unnecessary document deserialization. When `size` is 0, `SearchHits` still holds aggregation metadata.

### 14.1. Reading metrics inside buckets

In the example above, each `StringTermsBucket` provides:

- `key()`: the category value.
- `docCount()`: the number of products in the category.
- `aggregations()`: a map of child aggregations by name.

To retrieve the `avg` metric, read the child aggregation named `average_price`, then call `avg().value()`. The map key must match the exact name declared in Query DSL/Java builders.

### 14.2. Reading nested aggregations

For nested aggregations, the accessor is `nested()` instead of `sterms()` at that level. Then retrieve the child aggregation map to read metrics or buckets. Conceptual example:

```java
Aggregate reviewAggregate =
        aggregations.get("review_data").aggregation();

// Retrieve the nested aggregate according to the API client version.
// Then access the child aggregation "average_rating" and read avg().value().
```

Extract aggregation parsing into a separate mapper/helper rather than placing all casting logic in controllers. Aggregation responses are dynamic structures; if a query renames a bucket or metric, the mapper must also be updated.

## 15. Handling missing values and empty buckets

Aggregations only compute over appropriately indexed values. Missing, null, or doc-value-less fields can cause metrics to skip those documents.

Options include:

- Use `missing` in metric aggregations to supply a fallback value for documents missing the field.
- Use `missing` in bucket aggregations to group documents missing the field into a dedicated bucket.
- Normalize data at index time if a field is mandatory.
- Use `min_doc_count: 0` and extended bounds on histograms when empty buckets in a defined range are needed.

Example:

```json
GET /products/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brand.keyword",
        "missing": "UNKNOWN"
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price",
            "missing": 0
          }
        }
      }
    }
  }
}
```

Here, documents without a brand are placed in the `UNKNOWN` bucket. The `average_price` metric uses 0 as a substitute for documents missing a price. Such substitution alters statistical meaning; use it only if 0 is truly a valid business value for missing cases.

## 16. Performance and limits of nested aggregations

Multi-level aggregations can produce huge bucket counts. For example, category × brand × month × status can generate tens of thousands or millions of combinations when cardinality is high.

Practical guidelines:

- Only bucket on fields actually required for the report.
- Use `keyword`, numeric, or date fields with proper doc values.
- Limit `terms.size` to what the UI genuinely needs.
- Use `composite` to paginate buckets when all combinations must be scanned.
- Put filters in the query or filter aggregations to narrow the input document set.
- Avoid nesting many high-cardinality bucket levels unnecessarily.
- Consider `cardinality` when you only need an approximate distinct count instead of a bucket per value.
- Use `size: 0` when only aggregations are needed, without hits.
- Monitor the `search.max_buckets` limit; requests can be rejected if too many buckets are created.
- Benchmark on production-like data volumes and shard counts.

Metric aggregations are generally lighter than creating a bucket per distinct value, though metrics on nested data or multi-level pipelines can still be costly. There is no blanket rule that adding a sub-aggregation is always cheap; measure specifically.

### 16.1. Terms aggregations do not guarantee all buckets are returned

`terms` typically returns top buckets ordered by descending document count and capped by `size`. When many distinct values exist, less common buckets may be omitted. Bucket distribution across shards and candidate selection can also make `doc_count` approximate in some configurations.

If you need all buckets for export or complete calculations, consider a composite aggregation. If you need an exact distinct count, do not infer it by counting the buckets returned by a capped `terms` aggregation.

### 16.2. `search.max_buckets`

Elasticsearch limits the total number of buckets created in a single response via the `search.max_buckets` setting. Multi-level nested aggregations can hit this limit. Do not simply raise the limit to fix every query; first reduce cardinality, reduce nesting levels, or paginate buckets.

## 17. Testing aggregations in Spring Data Elasticsearch

Test against a real Elasticsearch instance or Testcontainers with a compatible version, because mocks cannot verify mappings, nested semantics, bucket counts, or metric values.

A small test dataset might include:

| Product | Category | Brand | Price | Reviews |
|---|---|---|---:|---|
| P1 | KEYBOARD | ACME | 100 | 5, 4 |
| P2 | KEYBOARD | OMEGA | 200 | 3 |
| P3 | MOUSE | ACME | 50 | 5 |
| P4 | MOUSE | OMEGA | 150 | No reviews |

Checks:

1. `by_category` returns two buckets: KEYBOARD and MOUSE.
2. `doc_count` of KEYBOARD is 2 and MOUSE is 2.
3. `average_price` of KEYBOARD is 150 and MOUSE is 100.
4. Nested aggregation counts 3 reviews for KEYBOARD and 1 review for MOUSE.
5. `average_rating` of KEYBOARD is 4 and MOUSE is 5.
6. `reverse_nested` counts parent products in the rating bucket, not reviews.
7. Pipeline aggregations return values matching the defined formula.
8. Missing values are handled according to business rules.

After indexing fixtures, refresh the index before running searches. Do not rely on `Thread.sleep` to wait for data visibility.

## 18. Common mistakes

| Symptom | Possible cause | Solution |
|---|---|---|
| `terms` does not group strings properly | Using a `text` field instead of `keyword` or an exact field. | Use `.keyword` or an appropriate keyword mapping. |
| Child bucket has unexpected counts | Sub-aggregations run on the parent bucket's document set, not the whole index. | Clearly verify the scope of each bucket level. |
| Average does not equal sum divided by doc_count | Some documents are missing the metric field value. | Check the metric `count` and missing values. |
| Nested aggregation returns a higher count than parent count | `doc_count` in nested context counts nested child documents. | Use `reverse_nested` when returning to parent level. |
| Review metric includes reviews not matching the nested query | Nested query filters parents, yet nested aggregation still iterates over all children of those parents. | Add a filter aggregation inside the nested aggregation. |
| Cannot use nested aggregation | Field is mapped as `object` instead of `nested`. | Recreate index with nested mapping and reindex data. |
| `reverse_nested` returns wrong parent metric | Reading fields from the wrong document scope or path. | Verify nested/parent context and place metrics after reverse_nested. |
| Pipeline aggregation cannot find buckets_path | Wrong child metric name or nesting level in path. | Check aggregation names and use `parent>child` syntax. |
| `avg_bucket` differs from overall document average | Averaging bucket averages gives equal weight to each bucket. | Use the appropriate metric or compute a count-weighted average. |
| Rare value buckets are missing | `terms.size` limits the number of returned buckets. | Raise size reasonably or use composite. |
| Request rejected for too many buckets | Deeply nested aggregations exceed `search.max_buckets`. | Reduce cardinality, reduce depth, or paginate buckets. |
| Java code fails to extract metric | Reading the wrong Aggregate union type or wrong aggregation name. | Use the matching accessor and separate mapper logic by response structure. |

## 19. Workflow for designing aggregations

1. **Define the business question:** which fields to group by and which metrics to calculate?
2. **Determine document scope:** are metrics calculated on root documents or nested children?
3. **Check mappings:** grouping fields need keyword/numeric/date; nested paths must be declared `nested`.
4. **Determine filters:** which conditions apply to the whole query, and which apply only to a single aggregation branch?
5. **Design the bucket tree:** parent groups, child groups, and expected bucket counts.
6. **Place metrics:** sum/avg/stats/cardinality or appropriate metrics inside the right buckets.
7. **Add pipelines if needed:** cross-bucket averages, ratios, derivatives, or cumulative sums.
8. **Integrate with Spring Data:** build `Aggregation`, attach to `NativeQuery`, and execute via `ElasticsearchOperations`.
9. **Read results:** traverse the right bucket/metric types and keep document scopes clear.
10. **Measure performance:** check bucket counts, memory, latency, and cluster limits.
11. **Test edge cases:** missing values, empty nested arrays, zero-document buckets, and multi-valued fields.

## 20. Key takeaways

- Bucket aggregations partition documents into groups; metric aggregations compute values over the current document set.
- Sub-aggregations can be buckets or metrics and always execute within the parent bucket's scope.
- `terms` groups by value, `range` groups by interval, `date_histogram` groups by time.
- `sum`, `avg`, `min`, `max`, `stats`, `value_count`, and `cardinality` return different metric types.
- `doc_count` counts documents in a bucket; `value_count` counts field values.
- Nested aggregations shift into nested documents; `reverse_nested` returns to parent documents.
- Nested queries filter parent documents; nested aggregations need their own filter if they must compute only over matching child documents.
- Pipeline aggregations compute from other aggregation results; `buckets_path` must point to the exact level and name.
- `avg_bucket` averages bucket metrics and is not automatically weighted by document count.
- `terms.size` limits bucket count; use composite for pagination when all buckets must be traversed.
- Spring Data Elasticsearch can attach Java API Client `Aggregation` instances to `NativeQuery` and read results via `SearchHits.getAggregations()`.
- Choose the right mappings, document scopes, and bucket limits so aggregations return accurate results and operate reliably.

Nested aggregations enable building multi-level reports in a single search request: buckets define groups, metrics describe each group, and pipeline metrics compute over already-aggregated values. When working with nested data, carefully track whether you are at parent or nested-child level; when combining metrics with buckets, place each aggregation at the right level so the numbers make business sense.

## References

- [Elasticsearch — Aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html)
- [Elasticsearch — Bucket aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket.html)
- [Elasticsearch — Metrics aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-metrics.html)
- [Elasticsearch — Pipeline aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-pipeline.html)
- [Elasticsearch — Nested aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-nested-aggregation.html)
- [Spring Data Elasticsearch — Search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
