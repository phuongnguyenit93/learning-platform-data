# Filter Aggregation and Conditional Set Statistics

Aggregations in Elasticsearch summarize search data into meaningful numbers and groups: counting products by category, calculating revenue of paid orders, finding the average price of in-stock items, or comparing document groups across multiple conditions. When you only want statistics over a subset of documents satisfying a specific condition, the filter aggregation is an essential tool.

A filter aggregation creates a single bucket containing documents that match a query/filter declared inside the aggregation. Sub-aggregations placed under that bucket compute statistics solely over the filtered document set. When you need to divide data into multiple parallel conditional groups, use a filters aggregation.

Distinguish three filtering levels:

- Search-level query restricts the input document set for the entire result and standard aggregations.
- Filter aggregation restricts a single aggregation branch.
- Filters aggregation creates multiple buckets, each with its own condition for comparing groups.

Understanding each filter's scope prevents miscounting, especially in search APIs that return both a result list and facet filters.

## 1. Which document set does an aggregation operate on?

Elasticsearch executes the query first, then runs aggregations on the set of documents matching the query. Example:

~~~json
{
  "query": {
    "term": {
      "status": "PAID"
    }
  },
  "aggs": {
    "revenue": {
      "sum": {
        "field": "totalAmount"
      }
    }
  }
}
~~~

The `revenue` aggregation sums `totalAmount` only for documents whose status is PAID. If the top-level query has no condition, standard aggregations examine all documents in the searched index.

Diagram:

~~~text
Index / alias
     |
     v
Top-level query
     |
     v
Document set matching query
     |
     +----> Returned hits
     |
     +----> Aggregations
                |
                +----> Bucket
                |        |
                |        +----> Sub-aggregations
                |
                +----> Metrics
~~~

This matters because a query-level filter impacts both hits and downstream aggregations. If you want hits to display broader documents while computing one statistic over a subset, use a filter aggregation on that statistical branch.

## 2. What is a filter aggregation?

A filter aggregation is a single-bucket aggregation. It takes a query as its condition, creates a bucket containing documents matching that condition, and allows placing sub-aggregations inside.

Example: returning a list of products matching the current query while computing the average price of in-stock products:

~~~json
{
  "size": 20,
  "query": {
    "match": {
      "name": "laptop"
    }
  },
  "aggs": {
    "available_products": {
      "filter": {
        "term": {
          "available": true
        }
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        },
        "total_stock": {
          "sum": {
            "field": "stock"
          }
        }
      }
    }
  }
}
~~~

The hits results still include all products matching the keyword `laptop`, regardless of `available` status. The `available_products` bucket contains only products with `available=true`. The two metrics `average_price` and `total_stock` compute exclusively on that bucket.

A filter aggregation typically returns:

- doc_count: the number of documents in the bucket.
- Results of sub-aggregations, such as avg, sum, min, max, terms, or date_histogram.

Filter aggregation fits when you need a single subset for one statistical branch.

## 3. How do filter aggregation and top-level query differ?

Both approaches restrict documents, but their scopes of impact differ.

| Criterion | Top-level query | Filter aggregation |
|---|---|---|
| Scope | Hits and standard aggregations | Only that aggregation bucket and its sub-aggregations |
| Purpose | Restrict the primary result set | Compute statistics on a subset |
| Can have multiple independent conditions | Yes, via bool query | Can create multiple filter aggregation branches |
| Use when | All statistics need the same base condition | One statistic needs its own condition |

For example, if all results and statistics only concern paid orders, placing `status=PAID` in the top-level query is usually simpler and more efficient than wrapping every aggregation in a filter.

If an API must return hits for all orders matching a keyword while also providing a separate metric for paid orders only, a filter aggregation is more appropriate.

### 3.1. Example with both total statistics and paid statistics

~~~json
{
  "query": {
    "match": {
      "customerName": "Nguyen"
    }
  },
  "aggs": {
    "all_matching_orders": {
      "stats": {
        "field": "totalAmount"
      }
    },
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "paid_amount": {
          "sum": {
            "field": "totalAmount"
          }
        }
      }
    }
  }
}
~~~

`all_matching_orders` computes statistics across all orders matching the customer name. `paid_orders` examines only orders with status PAID. Both branches share the document set produced by the top-level query.

### 3.2. Filter aggregation does not filter hits

A common mistake is assuming that adding a filter aggregation filters the hits list to documents matching that filter. That is incorrect. A filter aggregation only creates a bucket within the aggregations section.

If you want hits to also include only in-stock products, place `available=true` in the top-level query. If you want statistics on in-stock items while returning broader hits, keep the condition inside the filter aggregation.

## 4. Structure of filter aggregation and sub-aggregations

Basic structure:

~~~json
{
  "aggs": {
    "aggregation_name": {
      "filter": {
        "query_clause": {}
      },
      "aggs": {
        "metric_name": {
          "metric_aggregation": {
            "field": "numeric_field"
          }
        }
      }
    }
  }
}
~~~

Where:

- aggregation_name is the application-chosen name used to read the result.
- filter is the Query DSL condition applied to the bucket.
- Nested aggs are the statistics executed on the bucket.
- metric_name is the name of each child result.

Multiple levels of buckets and metrics can be nested. For example: filter paid orders, group by region, then compute total revenue per region.

~~~json
{
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "by_region": {
          "terms": {
            "field": "region.keyword"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            },
            "average_order_value": {
              "avg": {
                "field": "totalAmount"
              }
            }
          }
        }
      }
    }
  }
}
~~~

The processing order is: filter PAID orders, partition the remaining documents by region, then compute revenue and average_order_value inside each regional bucket.

## 5. Using filters aggregation for multiple condition sets

When you need to compare multiple condition groups in a single query, the filters aggregation creates multiple named buckets. Each bucket has its own filter.

Example comparing orders by status:

~~~json
{
  "aggs": {
    "orders_by_status": {
      "filters": {
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          },
          "cancelled": {
            "term": {
              "status": "CANCELLED"
            }
          }
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalAmount"
          }
        }
      }
    }
  }
}
~~~

The result has three buckets: paid, pending, and cancelled. Each bucket has its own doc_count and revenue metric.

### 5.1. Filter and filters

The two aggregation names look similar, but their semantics differ:

| Aggregation | Buckets created | When to use |
|---|---:|---|
| filter | One bucket | Statistics on a single subset |
| filters | Multiple named buckets | Comparing multiple condition sets |

A filter aggregation has one condition and one bucket. A filters aggregation has a map of conditions, each producing a separate bucket.

### 5.2. A document can belong to multiple buckets

Filters inside a filters aggregation are not mutually exclusive by default. A single document can match multiple conditions and be counted in multiple buckets.

For example:

- Bucket high_value filters totalAmount greater than 1000.
- Bucket vip_customer filters customerTier equals VIP.

A high-value order from a VIP customer will appear in both buckets. Thus, the sum of bucket doc_counts can exceed the number of input documents.

If you need mutually exclusive groups, design explicit non-overlapping conditions, such as disjoint price intervals or a single-valued status field.

### 5.3. The other bucket

Filters aggregation can configure `other_bucket` to collect documents that do not match any filter into a dedicated bucket:

~~~json
{
  "aggs": {
    "status_groups": {
      "filters": {
        "other_bucket": true,
        "other_bucket_key": "other",
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          }
        }
      }
    }
  }
}
~~~

The `other` bucket contains documents matching neither paid nor pending. If a document matches multiple named buckets, it is still counted in each matching bucket; `other` is not an exclusion bucket that turns overlapping filters into a partition.

## 6. Aggregating by multiple conditions with bool query

A filter aggregation accepts any Query DSL clause, so you can use a bool query to combine multiple conditions.

Example calculating revenue of active, in-stock products in two selected categories:

~~~json
{
  "aggs": {
    "eligible_products": {
      "filter": {
        "bool": {
          "filter": [
            {
              "term": {
                "active": true
              }
            },
            {
              "range": {
                "stock": {
                  "gt": 0
                }
              }
            },
            {
              "terms": {
                "category": ["books", "electronics"]
              }
            }
          ],
          "must_not": [
            {
              "term": {
                "visibility": "private"
              }
            }
          ]
        }
      },
      "aggs": {
        "total_value": {
          "sum": {
            "field": "inventoryValue"
          }
        },
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

Inside bool:

- filter requires active=true, stock greater than 0, and category in the list.
- must_not excludes products with visibility=private.
- Metrics run only on documents satisfying all of those conditions.

For conditions used solely for filtering, filter context is typically preferable to must because relevance scores do not need to be computed for buckets.

## 7. Metric aggregations inside filter buckets

A filter aggregation can contain various metric aggregation types.

| Metric | Meaning | Example |
|---|---|---|
| count via doc_count | Number of documents in the bucket | Number of PAID orders |
| sum | Sum of numeric values | Total revenue |
| avg | Average | Average order value |
| min | Minimum value | Lowest order amount |
| max | Maximum value | Highest order amount |
| stats | count, min, max, avg, sum | Summary statistics |
| extended_stats | Extended stats including variance and standard deviation | Price distribution analysis |
| value_count | Number of indexed values in the field | Number of values in a multi-valued field |
| cardinality | Approximate count of unique values | Number of unique customers |

Example:

~~~json
{
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "amount_stats": {
          "stats": {
            "field": "totalAmount"
          }
        },
        "unique_customers": {
          "cardinality": {
            "field": "customerId"
          }
        }
      }
    }
  }
}
~~~

Notes:

- doc_count counts documents in the bucket.
- value_count counts field values, which need not equal doc_count if the field is missing or an array.
- cardinality is typically an approximation based on HyperLogLog++; do not treat it as an exact count.
- sum and avg are only meaningful when the field has an appropriate numeric mapping.

## 8. Combining filter aggregation with terms and date_histogram

Reports often involve multiple levels: filter the dataset, group by category, then break down by time or compute metrics.

Example: paid revenue by category and by month:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-01-01",
        "lt": "2027-01-01"
      }
    }
  },
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category.keyword",
            "size": 20
          },
          "aggs": {
            "monthly_revenue": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month",
                "time_zone": "Asia/Ho_Chi_Minh"
              },
              "aggs": {
                "revenue": {
                  "sum": {
                    "field": "totalAmount"
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
~~~

The top-level query restricts to the year 2026. The filter aggregation keeps only PAID orders. Terms splits by category, date_histogram splits each category into monthly buckets, and sum computes revenue for each month.

The `time_zone` parameter determines calendar bucket boundaries in the desired timezone. If omitted, Elasticsearch typically uses UTC. For business reports by local day/month, specify the timezone explicitly and keep it consistent with timestamp storage conventions.

## 9. Filter aggregations and facets on a search page

A common use case is a product search page with category, brand, and status filters. The API needs to return:

- Hits matching a keyword.
- Product counts per category.
- Counts per brand.
- Counts per status.

There are two design approaches depending on semantics:

1. If all facets must reflect the exact same document set filtered by the main query and filters, use the top-level query for shared conditions and create terms aggregations.
2. If one facet must aggregate over a different subset, use a filter aggregation or filters aggregation on that branch.

### 9.1. Shared query filter and terms facets

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "phone"
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

Hits and both facets only consider active products matching the keyword `phone`.

### 9.2. Computing statistics ignoring a selected filter

A facet experience may want to show counts for all categories even while the user has selected one category. In that case, you must specify clearly which filters apply to hits and which filters are excluded for facets.

One option is using `post_filter` for conditions that apply only to hits after aggregations have run. Example:

~~~json
{
  "query": {
    "term": {
      "active": true
    }
  },
  "post_filter": {
    "term": {
      "category": "phones"
    }
  },
  "aggs": {
    "all_categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Here the query `active=true` applies to hits and aggregations. The `post_filter` `category=phones` filters only hits, not the `all_categories` aggregation. This mechanism differs from a filter aggregation; it is useful when facets need to show alternative choices.

If only one aggregation branch needs to bypass the category condition, you can use a global aggregation at the top level to return to all documents in the index, then place a dedicated filter inside the global bucket. Global aggregations ignore the top-level query, so you must repeat any baseline constraints that must remain enforced, such as tenant, access permissions, or valid status. Use this mechanism carefully so you do not accidentally expose statistics outside permitted scopes.

## 10. Global aggregation vs. filter aggregation

A global aggregation creates a bucket containing all documents in the index or index pattern, ignoring the top-level query. It can only be placed at the top aggregation level.

Example:

~~~json
{
  "query": {
    "term": {
      "category": "phones"
    }
  },
  "aggs": {
    "all_products": {
      "global": {},
      "aggs": {
        "active_products": {
          "filter": {
            "term": {
              "active": true
            }
          }
        }
      }
    }
  }
}
~~~

Hits remain constrained by `category=phones`. The `all_products` branch ignores that query and considers all documents in the index, after which the `active_products` filter keeps only `active=true`.

Comparison:

| Mechanism | Document scope |
|---|---|
| Top-level query | Limits hits and standard aggregations |
| filter aggregation | Filters a single aggregation branch within the post-query set |
| filters aggregation | Splits the post-query set into multiple conditional buckets |
| post_filter | Filters hits after aggregations, without affecting aggregations |
| global aggregation | Ignores top-level query, considers all documents in the index |

When using a global aggregation, pay close attention to tenant isolation and access permissions. If the top-level query contains data security constraints, the global aggregation will bypass them. Re-apply security constraints inside the global branch before computing statistics.

## 11. How field mappings affect filters and aggregations

Aggregations require appropriate mappings:

| Data type | Common mapping | Suitable aggregations/queries |
|---|---|---|
| Category, brand, status | keyword | term filter, terms aggregation |
| Name or description | text | match query; use keyword sub-field for exact grouping |
| Price, revenue, quantity | integer, long, scaled_float, double | range, sum, avg, stats |
| Date and time | date or date_nanos | range, date_histogram |
| Customer ID | keyword | terms, cardinality |
| Boolean | boolean | term filter |

Do not run terms aggregations on a text field expecting verbatim string grouping. Text fields are tokenized. Declare a keyword multi-field, for example:

~~~json
{
  "properties": {
    "category": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Then:

- Full-text search can use `category`.
- Exact filtering or bucket grouping can use `category.keyword`.

If the index already exists without the keyword sub-field, adding the mapping does not automatically populate indexed values for existing documents in all cases. Reindexing may be required to backfill the field.

## 12. Keyed vs. array responses in filters aggregation

Filters aggregations commonly use keys to name buckets. When keyed, the response returns buckets by name, such as paid, pending, cancelled. This maps easily to DTOs or statistics objects.

Abbreviated response example:

~~~json
{
  "aggregations": {
    "orders_by_status": {
      "buckets": {
        "paid": {
          "doc_count": 120,
          "revenue": {
            "value": 98000.0
          }
        },
        "pending": {
          "doc_count": 18,
          "revenue": {
            "value": 12000.0
          }
        },
        "cancelled": {
          "doc_count": 7,
          "revenue": {
            "value": 4300.0
          }
        }
      }
    }
  }
}
~~~

If the filters aggregation does not use a keyed response, buckets may be returned as an array in declaration order. Read by key or bucket order matching your configuration, rather than inferring from position if the API might change response structure.

## 13. Creating filter aggregations with Spring Data Elasticsearch

Spring Data Elasticsearch offers several ways to send aggregations:

- Using a repository method with the `@Aggregation` annotation for a fixed aggregation DSL.
- Using `ElasticsearchOperations` and `NativeQuery` when combining dynamic queries, filters, and multiple aggregations.
- Using the Elasticsearch Java Client directly when full control over DSL and aggregation responses is required.

Packages, builders, and result-reading types vary by release train. The examples below illustrate the structure with `NativeQuery` and the Elasticsearch Java Client; verify against your active dependencies.

### 13.1. Using @Aggregation for fixed queries

Example repository declaring a filters aggregation by status:

~~~java
import org.springframework.data.elasticsearch.annotations.Aggregation;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {

    @Aggregation("""
        {
          "filters": {
            "filters": {
              "paid": {
                "term": {
                  "status": "PAID"
                }
              },
              "pending": {
                "term": {
                  "status": "PENDING"
                }
              }
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            }
          }
        }
        """)
    AggregationResult summarizeOrders();
}
~~~

`AggregationResult` here is an illustrative DTO/return type for aggregation results. Repository aggregation mapping depends on the return type and Spring Data Elasticsearch version; not every nested bucket structure maps automatically to an arbitrary DTO. When you need to read metadata or complex buckets, use `ElasticsearchOperations` and the corresponding Aggregations API.

### 13.2. Using NativeQuery with Aggregation builder

With the Elasticsearch Java Client, you can construct an `Aggregation` object and attach it to `NativeQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Aggregation paidOrders = Aggregation.of(a -> a
        .filter(f -> f.term(t -> t
                .field("status")
                .value("PAID")
        ))
        .aggregations("revenue", Aggregation.of(revenue -> revenue
                .sum(s -> s.field("totalAmount"))
        ))
);

NativeQuery query = NativeQuery.builder()
        .withAggregation("paid_orders", paidOrders)
        .build();

SearchHits<Order> hits = operations.search(query, Order.class);
~~~

This snippet illustrates nesting a filter aggregation and a metric aggregation via the client builder. In a real application, you can add a top-level query with `withQuery(...)`, attach multiple aggregations via corresponding builder calls, and choose an appropriate hit size. If you only need aggregations without document hits, set the result size to 0 using the appropriate API for your version.

### 13.3. Reading aggregation results

In Spring Data Elasticsearch, `SearchHits` can hold aggregation metadata. With the Elasticsearch Java Client, aggregation responses are represented via `Aggregation` and `Aggregate` union variants. Exact retrieval depends on the Spring Data and client versions.

Conceptual result-reading flow:

~~~text
SearchHits<Order>
       |
       v
getAggregations()
       |
       v
ElasticsearchAggregations
       |
       v
aggregationsAsMap()
       |
       +----> paid_orders
                 |
                 +----> doc_count
                 |
                 +----> revenue.value
~~~

Verify that the aggregation name matches the key declared in the query. When mapping results to a DTO, map clearly:

- Bucket name.
- doc_count.
- Metric values.
- Null values or empty buckets.

Do not cast an `Aggregate` to a specific bucket type without checking the actual variant. If aggregations can vary by query, create a dedicated mapper to handle each result type and fail clearly when the structure is unexpected.

## 14. Business example: revenue report by status and region

Suppose the system needs an order report for a time range, computing revenue only for paid orders while also comparing status groups.

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-10-01T00:00:00Z",
        "lt": "2026-11-01T00:00:00Z"
      }
    }
  },
  "aggs": {
    "by_status": {
      "filters": {
        "filters": {
          "paid": {
            "term": {
              "status": "PAID"
            }
          },
          "pending": {
            "term": {
              "status": "PENDING"
            }
          },
          "cancelled": {
            "term": {
              "status": "CANCELLED"
            }
          }
        }
      },
      "aggs": {
        "amount_stats": {
          "stats": {
            "field": "totalAmount"
          }
        },
        "by_region": {
          "terms": {
            "field": "region",
            "size": 20
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalAmount"
              }
            }
          }
        }
      }
    }
  }
}
~~~

The top-level query restricts to October 2026. The filters aggregation creates buckets by status. Each bucket computes `amount_stats` and groups by region to compute `revenue`. The results can power a dashboard or operational report.

If you only need revenue for the PAID status, you can replace the filters aggregation with a single filter aggregation. Choose the simplest structure that accurately expresses the business requirement.

## 15. Performance and limits to keep in mind

Aggregations can consume more CPU, memory, and time than queries returning only hits, especially when grouping on high-cardinality fields or nesting many sub-aggregation levels.

Some guidelines:

- Use the top-level query for conditions shared across all aggregations.
- Use a filter aggregation when one branch needs a separate subset.
- Use a filters aggregation when you need multiple fixed-condition buckets.
- Choose keyword/numeric fields with proper mappings.
- Limit terms aggregation size to actual requirements.
- Avoid nesting too many high-cardinality buckets.
- Request only the metrics you need.
- Use `size: 0` when you only need aggregations and not hits.
- Monitor latency, memory, and shard failures in responses.

### 15.1. Cardinality and bucket counts

A terms aggregation can produce many buckets if a field has many distinct values. Setting a huge size is not always appropriate. If you need to iterate through all high-cardinality values, consider a composite aggregation to paginate buckets.

Cardinality aggregations typically produce approximate counts. If financial reports require exact unique counts, verify whether cardinality's error margin is acceptable or use another counting strategy.

### 15.2. Shards and doc_count

Bucket aggregations can be computed across multiple shards and merged. For terms aggregations, top buckets and `doc_count_error_upper_bound` depend on bucket distribution across shards and `shard_size`/`size` parameters. If counts must be exact within business rules, understand the limits of the aggregation used and consider composite or an appropriate data design.

A filter aggregation with a single condition does not suffer from terms' top-bucket selection issue, though it still depends on shard data, mappings, and cluster health.

### 15.3. Filter context and caching

Conditions inside a filter aggregation are evaluated in filter context. They do not calculate relevance scores. Elasticsearch may cache suitable filter results, though you should not assume every filter is always cached. Measure on realistic workloads.

## 16. Common mistakes

### 16.1. Using a filter aggregation and expecting hits to be filtered too

Filter aggregation only restricts its aggregation bucket. If hits need the same condition, put the condition in the top-level query or `post_filter` depending on desired semantics.

### 16.2. Repeating top-level conditions inside every aggregation

If every aggregation shares a condition, place it in the top-level query to reduce duplication and keep the structure clear.

### 16.3. Using filter instead of filters when comparing multiple groups

Filter creates only one bucket. If you need paid, pending, and cancelled in the same response, use a filters aggregation.

### 16.4. Assuming filters in a filters aggregation are mutually exclusive

A single document can match multiple buckets. If you need non-overlapping groups, design disjoint conditions.

### 16.5. Running terms aggregation on a text field

Text fields are tokenized. Use a keyword field or keyword multi-field to group by full values.

### 16.6. Confusing doc_count with value_count

`doc_count` counts documents in the bucket. `value_count` counts field values and can differ when fields are missing or multi-valued.

### 16.7. Using global aggregation and forgetting security conditions

Global aggregations ignore the top-level query. If the query contains tenant or authorization scope, re-apply those conditions inside the global branch.

### 16.8. Mapping aggregation responses to the wrong type

Aggregation responses can contain single-bucket, multi-bucket, and metric variants. Verify variant and key before casting or mapping to DTOs.

## 17. Testing filter aggregations

Prepare a small dataset with clear expected outcomes. Example:

| Order | Status | Region | Amount |
|---|---|---|---:|
| O1 | PAID | North | 100 |
| O2 | PAID | South | 200 |
| O3 | PENDING | North | 50 |
| O4 | CANCELLED | South | 80 |
| O5 | PAID | North | 300 |

With a filters aggregation by status, expected results:

| Bucket | doc_count | revenue |
|---|---:|---:|
| paid | 3 | 600 |
| pending | 1 | 50 |
| cancelled | 1 | 80 |

Tests should verify:

1. A filter bucket counts only documents matching its condition.
2. Sub-aggregations compute only over the parent bucket.
3. The top-level query narrows all buckets.
4. A filters aggregation returns the right buckets by key.
5. Documents matching multiple filters are counted in multiple buckets when conditions overlap.
6. `other_bucket` captures documents matching no named bucket.
7. Missing fields do not break doc_count and metric expectations.
8. Keyword/numeric/date mappings are appropriate.
9. A global aggregation actually ignores the top-level query and enforces its own security filter.
10. Aggregation results map accurately to DTOs.

In integration tests, use an Elasticsearch version compatible with your client. Mocked responses can test mappers, but they do not validate real DSL or aggregation semantics on a cluster.

## 18. Workflow for designing conditional statistics

When building reports or facets:

1. Identify the baseline document set and put shared conditions in the top-level query.
2. Determine whether each statistic needs the entire baseline set or a subset.
3. Use a filter aggregation for a single subset.
4. Use a filters aggregation for multiple condition sets to compare.
5. Place metric or bucket aggregations as sub-aggregations.
6. Check field mappings before running terms, range, date_histogram, or metrics.
7. Decide whether `post_filter` or a global aggregation is needed for facets.
8. If using global, re-apply tenant and security constraints.
9. Choose appropriate sizes and control cardinality.
10. Read the right response buckets/metrics and test with sample data.

Example choices:

| Requirement | Structure |
|---|---|
| Total revenue of PAID orders | filter aggregation + sum |
| Compare PAID/PENDING/CANCELLED | filters aggregation + metrics |
| All aggregations scoped to one tenant | top-level query |
| Hits filtered by category while facets still show all categories | post_filter or global branch with security filter |
| Monthly revenue within PAID group | filter aggregation + date_histogram + sum |

## 19. Conclusion

A filter aggregation creates a single bucket containing documents matching a condition and lets you run sub-aggregations on that subset. A filters aggregation creates multiple buckets for named conditions, making it suitable for comparing statuses, segments, or business cohorts. Buckets in `filters` can overlap if a document satisfies multiple filters.

The top-level query restricts the document set for hits and standard aggregations. A filter aggregation affects only its own statistical branch; `post_filter` filters only hits after aggregations run; global aggregation ignores the top-level query and must be used carefully with security constraints.

In Spring Data Elasticsearch, you can declare fixed aggregations using `@Aggregation` or build dynamic queries using `NativeQuery` and the Elasticsearch Java Client. Choose suitable mappings, read buckets and metrics accurately, bound cardinality, and test with datasets having clear expected results. A well-structured aggregation should reflect precisely which document set each number describes.
