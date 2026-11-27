# Pipeline Aggregations and Computing from Group Results

Elasticsearch aggregations typically begin by grouping documents into buckets or computing metrics over a dataset. For instance, an e-commerce system might group orders by month, sum monthly revenue, count orders, and calculate average order value. Once those group results exist, the application might also need average revenue across months, cumulative revenue, growth rate, period-over-period differences, or filtering to keep only groups above a threshold.

Pipeline aggregations address that next layer of computation. Rather than reading individual documents directly, a pipeline aggregation reads the outputs of other aggregations and computes over already-generated buckets or metrics. Thus, a pipeline aggregation can be viewed as a post-processing step on grouped results.

Elasticsearch divides pipeline aggregations into two main categories:

- **Parent pipeline aggregations:** execute inside a multi-bucket aggregation and produce a value or decision for each bucket of the parent aggregation.
- **Sibling pipeline aggregations:** sit at the same level as a multi-bucket aggregation, read the buckets of that aggregation, and produce a single aggregated result at the sibling level.

Common computations include derivative, cumulative_sum, moving function, bucket script, bucket selector, bucket sort, sum_bucket, avg_bucket, stats_bucket, and percentiles_bucket. In Spring Data Elasticsearch, you can build them using NativeQuery with Elasticsearch Java API Client builders.

## 1. Why are pipeline aggregations needed?

Suppose the `orders` index stores orders with these fields:

    {
      "orderId": "o-1001",
      "createdAt": "2026-01-15T10:00:00Z",
      "amount": 250.0,
      "status": "PAID",
      "category": "keyboard"
    }

A monthly revenue report needs:

1. Group orders by month.
2. Sum `amount` within each month.
3. Calculate cumulative revenue from the start of the year.
4. Calculate the revenue change between the current month and the previous month.
5. Calculate the average revenue across the months.

Steps 1 and 2 are standard aggregations: date_histogram and sum. Steps 3, 4, and 5 are calculations on the grouped results, so pipeline aggregations fit well.

If the application fetches all group results into Java to calculate them itself, the code may have to process many buckets, transfer more data over the network, and handle empty bucket edge cases manually. Pipeline aggregations let Elasticsearch execute these calculations directly on the search request's aggregation results.

Pipeline aggregations do not modify original documents and do not write computed results back into the index. They only add data to the search request response.

## 2. Standard aggregations vs. pipeline aggregations

Standard aggregations operate on documents selected by the query. Example:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
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

The result creates monthly buckets. Each bucket has `doc_count` and the `revenue` metric.

Pipeline aggregations can reference the `revenue` metric in those buckets:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
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
            }
          }
        },
        "average_monthly_revenue": {
          "avg_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

In this example:

- date_histogram creates monthly buckets.
- sum computes `revenue` in each bucket.
- derivative is a parent pipeline aggregation inside `sales_by_month` that computes the change relative to the previous bucket.
- avg_bucket is a sibling pipeline aggregation at the same level as `sales_by_month` that averages the `revenue` metric across monthly buckets.

Standard aggregations produce the input data. Pipeline aggregations read that data and perform additional calculations.

## 3. What is a bucket path?

A pipeline aggregation does not directly accept a document field like `amount`. Instead, it takes a path pointing to a metric or bucket property produced by another aggregation. This path is called `buckets_path`.

Common forms:

| Path form | Meaning |
|---|---|
| revenue | Child metric named `revenue` in the current bucket |
| sales_by_month>revenue | `revenue` metric inside the `sales_by_month` aggregation |
| by_category>by_month>revenue | `revenue` metric inside multi-level nested aggregations |
| sales_by_month>_count | Document count in each monthly bucket |
| sales_by_month>_key | Bucket key, when the pipeline type supports bucket keys |
| stats.avg | The `avg` property of a multi-value metric aggregation named `stats` |

The `>` symbol traverses nested aggregations/buckets. For multi-value metrics, a dot selects a specific property such as `avg`, `min`, or `max`.

Example:

    "buckets_path": "sales_by_month>revenue"

This path instructs the pipeline to read the `revenue` metric from each bucket produced by `sales_by_month`.

For `bucket_script` with multiple inputs, you can assign variable names in a map:

    "buckets_path": {
      "revenue": "revenue_sum",
      "cost": "cost_sum"
    }

The script can then use `params.revenue` and `params.cost`.

### Bucket paths must point to valid results

A pipeline aggregation requires a numeric metric or a bucket property supported by that pipeline type. You cannot use an arbitrary bucket path to read a document field that has not been computed by an aggregation.

If you need to sum `amount`, first create a `sum` aggregation on `amount`. Then the pipeline references that sum aggregation's name.

## 4. Parent and sibling pipeline aggregations

The difference between parent and sibling determines where an aggregation is declared and the shape of its result.

### Parent pipeline aggregation

A parent pipeline aggregation is declared inside a multi-bucket aggregation. It runs on each bucket of the parent aggregation.

Example:

    "sales_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        },
        "running_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }

`running_revenue` produces a value for each monthly bucket based on the revenue of that month and preceding buckets.

Common parent pipeline aggregations:

- derivative
- cumulative_sum
- moving_fn
- serial_diff
- bucket_script
- bucket_selector
- bucket_sort

A parent pipeline aggregation must be placed under an appropriate multi-bucket aggregation, such as date_histogram, histogram, terms, or composite in API-supported cases.

### Sibling pipeline aggregation

A sibling pipeline aggregation sits at the same level as the multi-bucket aggregation it reads. It aggregates across buckets to produce one metric result at the sibling level.

Example:

    "sales_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "amount"
          }
        }
      }
    },
    "average_monthly_revenue": {
      "avg_bucket": {
        "buckets_path": "sales_by_month>revenue"
      }
    }

`average_monthly_revenue` is a result metric at the root aggregation level. It does not create additional monthly buckets.

Common sibling pipeline aggregations:

- min_bucket
- max_bucket
- sum_bucket
- avg_bucket
- stats_bucket
- extended_stats_bucket
- percentiles_bucket

A helpful rule of thumb:

- Parent: computes per bucket of the parent aggregation.
- Sibling: reads a set of buckets and produces a combined summary at the same level.

## 5. sum_bucket, avg_bucket, min_bucket, and max_bucket

These are the basic sibling pipeline aggregations. They compute a single metric across the same metric in multiple buckets.

Example computing average and total monthly revenue:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "total_revenue_across_months": {
          "sum_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "average_monthly_revenue": {
          "avg_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "lowest_monthly_revenue": {
          "min_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        },
        "highest_monthly_revenue": {
          "max_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

These pipelines return a single metric value. They do not generate a new bucket list.

### When to use each

- sum_bucket: total revenue across months or total quantity across groups.
- avg_bucket: average of a metric across groups.
- min_bucket: find the lowest metric value across groups.
- max_bucket: find the highest metric value across groups.

Note that `avg_bucket` averages across buckets, not automatically across individual documents. If different months have different order counts, the average monthly revenue and the average order amount are two distinct quantities.

## 6. stats_bucket and extended_stats_bucket

`stats_bucket` computes basic statistics over a metric across multiple buckets:

- count
- min
- max
- avg
- sum

Example:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "monthly_revenue_stats": {
          "stats_bucket": {
            "buckets_path": "sales_by_month>revenue"
          }
        }
      }
    }

`extended_stats_bucket` adds extended statistics such as variance and standard deviation:

    "monthly_revenue_extended_stats": {
      "extended_stats_bucket": {
        "buckets_path": "sales_by_month>revenue"
      }
    }

These metrics are helpful for executive summaries, such as highest, lowest, average monthly revenue, and dispersion across months.

Do not confuse `stats_bucket` with the standard `stats` aggregation:

- `stats` computes statistics over document field values in a dataset.
- `stats_bucket` computes statistics over the metric values already calculated for each bucket.

## 7. percentiles_bucket

`percentiles_bucket` calculates percentiles over metric values across buckets. For example, finding the monthly revenue threshold below which 90% of months fall:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            }
          }
        },
        "monthly_revenue_percentiles": {
          "percentiles_bucket": {
            "buckets_path": "sales_by_month>revenue",
            "percents": [
              50,
              90,
              99
            ]
          }
        }
      }
    }

The 50th percentile corresponds to the approximate median of the bucket metric distribution; the 90th and 99th percentiles indicate higher thresholds.

This is the percentile over monthly revenues, not the percentile over individual order amounts. To get percentiles of order amounts, use the standard `percentiles` aggregation on the `amount` field.

## 8. derivative: computing change between buckets

`derivative` computes the discrete derivative of a metric along the ordered buckets. In monthly reports, it is commonly used to see whether revenue increased or decreased compared to the previous month.

Example:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "monthly_change": {
              "derivative": {
                "buckets_path": "revenue"
              }
            }
          }
        }
      }
    }

If monthly revenues are:

| Month | Revenue | Derivative |
|---|---:|---:|
| Month 1 | 100 | null |
| Month 2 | 130 | 30 |
| Month 3 | 120 | -10 |
| Month 4 | 160 | 40 |

The first month's derivative has no value because there is no preceding bucket to compare against. Positive values indicate metric growth; negative values indicate decline.

### Derivative is not percentage growth

Derivative in the example is the absolute difference between two buckets:

    current - previous

If you need percentage change:

    (current - previous) / previous * 100

you can use `bucket_script` combining the current metric and derivative, or use `bucket_script` referencing the appropriate metrics. Handle the case where `previous` is 0 to avoid division by zero.

## 9. cumulative_sum: running totals

`cumulative_sum` computes the running total of a metric across ordered buckets:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "order": {
              "_key": "asc"
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
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

Example:

| Month | Revenue | Running revenue |
|---|---:|---:|
| Month 1 | 100 | 100 |
| Month 2 | 130 | 230 |
| Month 3 | 120 | 350 |
| Month 4 | 160 | 510 |

Common uses of `cumulative_sum`:

- Year-to-date cumulative revenue.
- Cumulative order counts.
- Cumulative page views.
- Cumulative event counts over time.

Bucket order is critical. For `date_histogram`, explicitly specify ascending `_key` order when you need running totals chronologically from oldest to newest.

## 10. moving_fn: computing over a sliding window

`moving_fn` evaluates a function over a sliding window of neighboring buckets. Example: computing a 3-month trailing average revenue to smooth fluctuations:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "moving_average_3_months": {
              "moving_fn": {
                "buckets_path": "revenue",
                "window": 3,
                "script": "MovingFunctions.unweightedAvg(values)"
              }
            }
          }
        }
      }
    }

`window` is the number of buckets in the window, not the number of days. For a monthly `date_histogram`, window 3 usually corresponds to three monthly buckets. For a daily histogram, window 7 corresponds to seven daily buckets.

`MovingFunctions` provides supported Painless helpers such as `unweightedAvg`, `max`, `min`, `sum`, and several other calculations. You can write a custom script when a tailored formula is required, though prefer built-in functions when they meet your goal.

### moving_fn vs. moving_avg

Older Elasticsearch versions had a `moving_avg` pipeline aggregation. That API has been replaced by `moving_fn` in newer versions. For current projects, prefer `moving_fn` and check cluster version if maintaining legacy systems.

### Windows and empty buckets

`moving_fn` depends on bucket count and how missing-data buckets are handled. If a month has no orders, `date_histogram` may omit that month's bucket by default. When you need a continuous time series, consider `min_doc_count: 0` and `extended_bounds`, then choose an appropriate `gap_policy`.

## 11. serial_diff: difference from an earlier bucket

`serial_diff` computes the difference between the current value and the value a specified `lag` number of buckets earlier.

Example comparing this month's revenue with the same month 12 months ago:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "year_over_year_difference": {
              "serial_diff": {
                "buckets_path": "revenue",
                "lag": 12
              }
            }
          }
        }
      }
    }

A `lag` of 12 means comparing against the bucket 12 positions earlier in the bucket sequence. When each bucket is one month, this yields the year-over-year difference against 12 months prior.

`serial_diff` returns the absolute difference, not a percentage. To calculate a percentage, combine with `bucket_script` and handle a zero denominator.

## 12. bucket_script: evaluating formulas per bucket

`bucket_script` is a parent pipeline aggregation that computes a new metric from multiple metrics inside the same bucket. It runs a script using variables declared in `buckets_path`.

Example computing monthly profit:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "shipping_cost": {
              "sum": {
                "field": "shippingCost"
              }
            },
            "profit_after_shipping": {
              "bucket_script": {
                "buckets_path": {
                  "revenue": "revenue",
                  "shipping": "shipping_cost"
                },
                "script": "params.revenue - params.shipping"
              }
            }
          }
        }
      }
    }

Inside each monthly bucket:

- `revenue` references the summed `amount` metric.
- `shipping` references the summed `shippingCost` metric.
- The script computes `revenue` minus `shipping`.
- The result `profit_after_shipping` is returned as a metric on the bucket.

You can use `bucket_script` to compute:

- Conversion rate from order count and visit count.
- Average order value from total revenue and order count.
- Profit margin.
- Percentage change from the previous period when corresponding metrics exist.

### Division and handling zero values

Example calculating average order value:

    "average_order_value": {
      "bucket_script": {
        "buckets_path": {
          "revenue": "revenue",
          "orders": "_count"
        },
        "script": "params.orders == 0 ? 0 : params.revenue / params.orders"
      }
    }

In some scenarios, using a `value_count` metric on `orderId` is clearer if one document does not correspond one-to-one with one order. `_count` is the number of documents in the bucket, not the business order count if an order spans multiple documents.

The script must return a valid number. Define behavior when the denominator is 0, a metric is missing, or a bucket has no data.

## 13. bucket_selector: filtering buckets by computed results

`bucket_selector` is a parent pipeline aggregation that uses a boolean script to keep or drop each bucket. Example keeping only months with at least 100,000 in revenue:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "qualified_months": {
              "bucket_selector": {
                "buckets_path": {
                  "monthlyRevenue": "revenue"
                },
                "script": "params.monthlyRevenue >= 100000"
              }
            }
          }
        }
      }
    }

Bucket selector does not filter documents before the aggregation runs. It executes after buckets and metrics have already been computed, then strips non-matching buckets from the response.

This has performance implications: `bucket_selector` trims the response down to desired buckets, but it does not stop Elasticsearch from computing aggregations for the discarded buckets. If a condition can be expressed as a document-level query/filter, filtering before aggregation is usually more efficient.

### Distinguishing bucket_selector from query filters

- Query filters exclude documents before aggregations compute.
- `bucket_selector` excludes buckets after bucket metrics have been computed.

For example, keeping only PAID orders is a document condition, so place `status` in a bool filter. Showing only months whose revenue exceeds 100,000 is a bucket-metric condition, so use `bucket_selector`.

## 14. bucket_sort: sorting and limiting buckets

`bucket_sort` is a parent pipeline aggregation that sorts, skips, or truncates buckets produced by the parent aggregation.

Example retrieving the 5 categories with highest total revenue:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_category": {
          "terms": {
            "field": "category",
            "size": 100
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "top_categories": {
              "bucket_sort": {
                "sort": [
                  {
                    "revenue": {
                      "order": "desc"
                    }
                  }
                ],
                "size": 5
              }
            }
          }
        }
      }
    }

`bucket_sort` sorts buckets by the `revenue` metric and retains the top 5 buckets.

### Important limitation of bucket_sort

`bucket_sort` only operates on buckets already created by the parent aggregation. In the example, `terms.size` is 100, so `bucket_sort` can sort at most the 100 categories returned by the terms aggregation.

If terms only produces 10 buckets, `bucket_sort` with `size: 50` cannot magically discover 40 more categories. To get an accurate top 5 across all categories, ensure the parent aggregation collected sufficient candidates within terms' semantics and limits. For paginated traversal across all buckets, consider a composite aggregation instead of using `bucket_sort` as an unbounded pagination mechanism.

`bucket_sort` accepts `from` and `size` to slice the sorted bucket list. This paginates over the already-generated buckets and is not equivalent to `search_after` on documents.

## 15. Gap policy and buckets with no data

Time-series pipeline aggregations can encounter buckets missing metrics. For instance, February had no orders, so `date_histogram` might omit that month's bucket by default, or the bucket exists with no metric value.

Pipeline aggregations support `gap_policy` to decide how gaps are handled. Two common choices:

- skip: skips buckets missing values during the calculation.
- insert_zeros: treats missing values as 0.

Example:

    "monthly_change": {
      "derivative": {
        "buckets_path": "revenue",
        "gap_policy": "insert_zeros"
      }
    }

If February has no revenue data, `insert_zeros` treats that month's metric as 0 when computing the derivative. With `skip`, buckets missing the metric are skipped according to pipeline semantics.

Do not pick `insert_zeros` merely to make charts look continuous. Clarify whether an empty bucket means zero revenue occurred or data was never collected. Those two situations differ in business meaning.

## 16. Generating continuous time buckets

By default, `date_histogram` only creates buckets that contain matching documents. If you need to display months with zero orders, use `min_doc_count: 0` and `extended_bounds`:

    GET orders/_search
    {
      "size": 0,
      "query": {
        "range": {
          "createdAt": {
            "gte": "2026-01-01T00:00:00Z",
            "lt": "2027-01-01T00:00:00Z"
          }
        }
      },
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month",
            "min_doc_count": 0,
            "extended_bounds": {
              "min": "2026-01-01T00:00:00Z",
              "max": "2026-12-01T00:00:00Z"
            }
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "amount"
              }
            },
            "running_revenue": {
              "cumulative_sum": {
                "buckets_path": "revenue",
                "gap_policy": "insert_zeros"
              }
            }
          }
        }
      }
    }

`min_doc_count: 0` requests empty buckets within the applicable range; `extended_bounds` defines the display time boundaries. The range query narrows input documents. When using timezones or calendar intervals, choose boundary anchors in the business timezone.

If no bucket exists for a time slot, a pipeline cannot fabricate that bucket itself. Configure the histogram to generate the desired bucket sequence first.

## 17. Pipeline aggregations on nested buckets

Aggregations can nest multiple levels, such as grouping by category and then by month:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category"
          },
          "aggs": {
            "sales_by_month": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month"
              },
              "aggs": {
                "revenue": {
                  "sum": {
                    "field": "amount"
                  }
                },
                "running_revenue": {
                  "cumulative_sum": {
                    "buckets_path": "revenue"
                  }
                }
              }
            },
            "average_monthly_revenue": {
              "avg_bucket": {
                "buckets_path": "sales_by_month>revenue"
              }
            }
          }
        }
      }
    }

Here:

- `by_category` creates buckets per category.
- `sales_by_month` creates monthly buckets inside each category.
- `running_revenue` computes a running total separately within each category.
- `average_monthly_revenue` computes average monthly revenue within the current category's scope.

When writing bucket paths, identify which level the pipeline sits at and which child aggregation holds the target metric. Paths are relative to where the pipeline is declared; for instance, `revenue` inside `sales_by_month` is referenced as `sales_by_month>revenue` when the pipeline sits at the parent level of `sales_by_month`.

## 18. Calculating conversion rate from bucket metrics

A marketing report might group by campaign and count both visits and orders. Then `bucket_script` calculates conversion rate:

    GET campaign_events/_search
    {
      "size": 0,
      "aggs": {
        "by_campaign": {
          "terms": {
            "field": "campaign"
          },
          "aggs": {
            "visits": {
              "filter": {
                "term": {
                  "eventType": "visit"
                }
              }
            },
            "orders": {
              "filter": {
                "term": {
                  "eventType": "order"
                }
              }
            },
            "conversion_rate": {
              "bucket_script": {
                "buckets_path": {
                  "visits": "visits>_count",
                  "orders": "orders>_count"
                },
                "script": "params.visits == 0 ? 0 : params.orders / params.visits * 100"
              }
            }
          }
        }
      }
    }

Here, `visits` and `orders` are filter aggregations, each producing a single bucket with a `doc_count`. The pipeline script reads `_count` from both buckets and calculates the percentage.

Ensure event data has matching semantics. If one person can generate multiple visit or order events, event-based conversion rate differs from unique-user conversion rate. If unique users are required, design corresponding cardinality metrics or pre-aggregated data.

## 19. Calculating percentage growth via bucket_script

To calculate month-over-month percentage growth, you can combine `derivative` with `bucket_script`. One approach uses `derivative` as the numerator and subtracts `derivative` from current revenue to derive the previous bucket's value:

    GET orders/_search
    {
      "size": 0,
      "aggs": {
        "sales_by_month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
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
            "growth_percent": {
              "bucket_script": {
                "buckets_path": {
                  "current": "revenue",
                  "change": "revenue_change"
                },
                "script": "params.current - params.change == 0 ? 0 : params.change / (params.current - params.change) * 100"
              }
            }
          }
        }
      }
    }

Because `derivative = current - previous`, the expression `current - change` recovers `previous`. The script handles a zero denominator by returning 0 in this example. Depending on business rules, you may prefer returning null/no value or flagging it separately rather than treating growth as 0 when the prior month had no revenue.

For reports requiring simpler formulas, use an appropriate pipeline to fetch prior-period metrics or perform the final calculation in application code after receiving buckets. Verify whether chaining pipeline aggregations is supported in your version and avoid circular dependencies between pipelines.

## 20. Execution order and dependencies between aggregations

Pipeline aggregations execute after the standard aggregations they depend on. Therefore:

- Input metrics must be declared at the right position in the aggregation tree.
- Parent pipelines must sit inside a suitable multi-bucket aggregation.
- Sibling pipelines must reference a multi-bucket aggregation at the same level.
- Pipelines cannot read a document field directly as a metric without an aggregation generating that value first.
- Do not create circular dependencies among pipelines.

Example structure:

    sales_by_month
      revenue
      revenue_change
      running_revenue
      revenue_selector

    average_monthly_revenue

`revenue_change` and `running_revenue` are parent pipelines inside `sales_by_month`. `average_monthly_revenue` is a sibling pipeline at the outer level.

If one pipeline needs the output of another pipeline, ensure the path and dependency ordering are supported by Elasticsearch. For complex logic, break calculations into clear aggregation tiers or compute the final step in the application to avoid hard-to-maintain queries.

## 21. Pipeline aggregations and performance

Pipeline aggregations do not re-scan every document like a new query. They work over already-generated aggregation results. However, that does not mean pipelines are always free.

Overall cost still depends on:

- Number of documents selected by the query.
- Number of buckets created by the parent aggregation.
- Depth and count of nested aggregations.
- Number of pipeline functions.
- Script complexity.
- Response size.

Some guidelines:

- Narrow documents with query/filter before aggregating.
- Limit bucket counts when reports do not need every group.
- Use `date_histogram` intervals matching required resolution.
- Avoid creating hundreds of thousands of buckets when only top N are needed.
- Use `bucket_selector` to trim responses when conditions depend on metrics; recognize it runs after buckets are computed.
- Keep scripts short and prefer built-in pipelines when possible.
- Do not use `bucket_sort` instead of composite aggregation for cursor-based full bucket pagination.
- Measure query duration and response size on production-like data.

### Terms and top buckets

`terms` aggregations typically return a limited number of buckets. When a pipeline computes over terms results, it sees only the buckets returned by the parent aggregation under terms' semantics and limits. Configure `size` and `shard_size` appropriately when more accurate top buckets are needed, or consider composite to traverse all groups.

## 22. Pipeline aggregations in Spring Data Elasticsearch

In modern Spring Data Elasticsearch, you can construct aggregations using the Elasticsearch Java API Client and attach them to `NativeQuery`. Example grouping monthly revenue, calculating derivative, and computing average bucket:

    Aggregation revenueByMonth = Aggregation.of(a -> a
        .dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Month)
        )
        .aggregations("revenue", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("amount"))
        ))
        .aggregations("revenue_change", Aggregation.of(pipeline -> pipeline
            .derivative(derivative -> derivative
                .bucketsPath("revenue")
            )
        ))
    );

    Aggregation averageMonthlyRevenue = Aggregation.of(a -> a
        .avgBucket(avg -> avg
            .bucketsPath("sales_by_month>revenue")
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withAggregation("sales_by_month", revenueByMonth)
        .withAggregation("average_monthly_revenue", averageMonthlyRevenue)
        .build();

    SearchHits<Order> hits =
        operations.search(query, Order.class);

In this example:

- Aggregation `revenueByMonth` holds the date histogram and sum metric.
- `revenue_change` is a parent pipeline aggregation inside the date histogram.
- `averageMonthlyRevenue` is a sibling pipeline aggregation at the query level.
- `NativeQuery` attaches both aggregations by name so bucket paths can reference them.
- `ElasticsearchOperations` executes the request.

Essential imports:

    import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
    import co.elastic.clients.elasticsearch._types.CalendarInterval;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.SearchHits;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

Enum names, builder methods, and `add` aggregation overloads depend on the Elasticsearch Java API Client version. Use the dependency version managed by Spring Boot/Spring Data and verify your project's actual API.

### Using a query for aggregations only

If the request only needs aggregation reports without returning a document list:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("2026-01-01T00:00:00Z")
                    .lt("2027-01-01T00:00:00Z")
                )
            )
        )
        .withMaxResults(0)
        .withAggregation("sales_by_month", revenueByMonth)
        .withAggregation("average_monthly_revenue", averageMonthlyRevenue)
        .build();

    SearchHits<Order> hits =
        operations.search(query, Order.class);

Setting max results to 0 retrieves only the aggregation response without loading unnecessary document hits. The API method name for configuring size can differ across versions; if `NativeQueryBuilder` lacks `withMaxResults` in your current dependency, use the corresponding option on `Query` or the client.

## 23. Reading aggregation responses in Spring Data

When calling `operations.search`, the result returns `SearchHits`. Aggregation responses live in the aggregations section of search results; they are not placed in entity content.

Conceptual example:

    SearchHits<Order> searchHits =
        operations.search(query, Order.class);

    AggregationsContainer<?> aggregations =
        searchHits.getAggregations();

The concrete container type and retrieval methods depend on the Spring Data Elasticsearch and client integration versions. Some versions provide wrappers over Elasticsearch Java API Client responses; older versions use different abstractions.

When reading the response, you need to:

1. Obtain the aggregation container from `SearchHits`.
2. Look up aggregations by their declared names, such as `sales_by_month` or `average_monthly_revenue`.
3. Verify the returned aggregation type: date histogram buckets, single-value metric, or pipeline result.
4. Iterate over buckets if per-period results are needed.
5. Read pipeline metric values according to the corresponding response structure.

Do not cast every aggregation to a single concrete type without checking the variant. The Elasticsearch Java API Client uses tagged unions for aggregation/result types; access the matching variant and handle missing or unexpected types safely.

### Separating aggregations from entity mapping

The `Order` entity describes a document stored in the index. Aggregation responses are summary data computed across many documents. Do not expect Spring Data to automatically map buckets into `Order` objects or populate pipeline metrics into entity fields.

For dashboards, map aggregation responses into dedicated DTOs:

    public record MonthlyRevenue(
        String month,
        double revenue,
        Double revenueChange,
        Double runningRevenue
    ) {}

This DTO represents report data, not the underlying source document.

## 24. Pipeline aggregations with bucket_script in Java Client

Example creating a `bucket_script` to calculate profit:

    Aggregation profit = Aggregation.of(a -> a
        .bucketScript(script -> script
            .bucketsPath(Map.of(
                "revenue", "revenue",
                "cost", "cost"
            ))
            .script(Script.of(s -> s
                .inline(inline -> inline
                    .source("params.revenue - params.cost")
                )
            ))
        )
    );

Parent aggregation:

    Aggregation salesByMonth = Aggregation.of(a -> a
        .dateHistogram(h -> h
            .field("createdAt")
            .calendarInterval(CalendarInterval.Month)
        )
        .aggregations("revenue", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("amount"))
        ))
        .aggregations("cost", Aggregation.of(metric -> metric
            .sum(sum -> sum.field("cost"))
        ))
        .aggregations("profit", profit)
    );

    NativeQuery query = NativeQuery.builder()
        .withAggregation("sales_by_month", salesByMonth)
        .build();

`Script` is the Elasticsearch Java API Client script type. Specific builders can vary across versions. When a script takes dynamic inputs, pass them via `params` rather than concatenating inputs into the script source string.

## 25. Pipeline aggregations with bucket_selector and bucket_sort

You can construct `bucket_selector` to retain buckets with revenue above a threshold:

    Aggregation highRevenueOnly = Aggregation.of(a -> a
        .bucketSelector(selector -> selector
            .bucketsPath(Map.of(
                "revenue", "revenue"
            ))
            .script(Script.of(s -> s
                .inline(inline -> inline
                    .source("params.revenue >= params.minimum")
                )
            ))
        )
    );

Example `bucket_sort`:

    Aggregation topRevenueBuckets = Aggregation.of(a -> a
        .bucketSort(sort -> sort
            .sort(s -> s
                .field(f -> f
                    .field("revenue")
                    .order(SortOrder.Desc)
                )
            )
            .size(5)
        )
    );

Both snippets illustrate the Java Client structure. Exact overload names for script params, sort lists, and `JsonData` depend on the client version; inspect the generated builders of your active dependency before copying verbatim.

`bucket_selector` and `bucket_sort` must be placed under a parent multi-bucket aggregation. They act on the parent aggregation's buckets rather than filtering input documents.

## 26. When to compute in Elasticsearch vs. in Java?

Pipeline aggregations are helpful when calculations:

- Depend on already-aggregated metrics.
- Can be expressed cleanly with pipeline functions.
- Should be returned alongside the aggregation response.
- Do not require complex business logic or external state outside Elasticsearch.

Computing in Java may be better when:

- Formulas require data from multiple external sources.
- Specialized business calendars or bespoke rules apply.
- Multi-step processing is awkward to express via bucket paths.
- Aggregation outputs are small and the application already has the required figures.
- Logic must be unit-tested independently of Elasticsearch.

Do not load millions of documents into Java just to compute sums or derivatives that Elasticsearch can compute directly. Conversely, do not cram massive business workflows into Painless scripts just to save a few lines of Java.

A practical boundary:

- Elasticsearch handles filtering, grouping, metrics, and direct bucket-level math.
- The application receives summary results, maps them to DTOs, and applies presentation logic or joins external data.

## 27. Common mistakes

### Using a document field directly in buckets_path

Pipeline aggregations require metrics or bucket properties produced by aggregations. Create a sum, avg, value_count, or appropriate metric first.

### Placing a parent pipeline at the wrong level

Parent pipelines must sit inside the multi-bucket aggregation they operate on. Placing one at the root level as a sibling pipeline makes the query structure invalid.

### Confusing parent and sibling pipelines

Derivative or cumulative_sum generate values per bucket and belong inside the parent aggregation. `avg_bucket` or `sum_bucket` summarize across buckets and sit at the same level as the multi-bucket aggregation they read.

### Writing an incorrect bucket path

Check aggregation names and nesting levels. Use `>` to traverse aggregations/buckets and dots to access properties of multi-value metrics when needed.

### Assuming avg_bucket averages across documents

`avg_bucket` averages metric values across buckets. If you need the average `amount` per document, use a standard `avg` aggregation directly on `amount`.

### Assuming derivative is percentage growth

Derivative is typically the absolute difference between buckets. For percentages, divide by the previous period's value and handle zero.

### Ignoring empty buckets

Time series may have missing buckets. Decide between `skip` and `insert_zeros` based on data meaning, and generate empty buckets via `min_doc_count`/`extended_bounds` if needed.

### Using bucket_selector to reduce aggregation cost

`bucket_selector` runs after buckets and metrics have already been computed. Whenever documents can be filtered beforehand via query/filter, do it there.

### Using bucket_sort to paginate all terms

`bucket_sort` only sorts buckets already produced by the parent aggregation. For large group sets requiring cursor pagination, consider composite aggregation.

### Scripts dividing by zero or reading missing fields

`bucket_script` must handle missing metrics and zero denominators. Script scores/metrics must return values compatible with the pipeline type.

### Using pipeline aggregations to update stored data

Pipeline aggregations only compute values in the response. They do not update documents or persist metrics into the index.

### Reading aggregations as entities

Aggregation responses are not entity lists. Read from the `SearchHits` aggregation container and map to report DTOs.

## 28. Workflow for designing pipeline aggregations

When building a report, follow this order:

1. Define input documents using query and filters.
2. Choose an appropriate bucket aggregation: date_histogram, histogram, terms, or composite.
3. Create required metrics in each bucket: sum, avg, min, max, value_count, or others.
4. Determine whether calculations run per bucket or across all buckets.
5. Use parent pipelines for per-bucket calculations such as derivative, cumulative_sum, moving_fn, bucket_script, or bucket_selector.
6. Use sibling pipelines for cross-bucket statistics such as avg_bucket, sum_bucket, stats_bucket, or percentiles_bucket.
7. Write accurate `buckets_path` expressions matching the aggregation tree.
8. Decide `gap_policy` and how empty buckets are generated.
9. Verify bucket order, especially for cumulative_sum, derivative, and moving_fn.
10. Bound bucket counts and evaluate script overhead.
11. Attach aggregations to `NativeQuery` when using Spring Data Elasticsearch.
12. Read aggregation responses with matching types and map to DTOs.
13. Test with empty buckets, zero metrics, missing metrics, and boundary data.

## Conclusion

Pipeline aggregations perform calculations on the outputs of other aggregations. Parent pipelines such as derivative, cumulative_sum, moving_fn, serial_diff, bucket_script, bucket_selector, and bucket_sort operate on individual buckets of a parent multi-bucket aggregation. Sibling pipelines such as sum_bucket, avg_bucket, min_bucket, max_bucket, stats_bucket, and percentiles_bucket summarize metrics across buckets at the same level.

`buckets_path` is the core link: it points to the metric or bucket property the pipeline reads. Always create input metrics first, place pipelines at the right level, handle empty buckets with `gap_policy`, and configure histograms properly. In Spring Data Elasticsearch, use `NativeQuery` with Elasticsearch Java API Client `Aggregation` builders to submit pipeline aggregations; read results from the `SearchHits` aggregation container and map them to report DTOs. Use pipeline aggregations for bucket-level calculations while keeping document filtering, external business logic, and data persistence in their appropriate application layers.
