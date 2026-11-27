# Date Histogram, Histogram, and Range Aggregations

Elasticsearch aggregations can group documents into buckets for data analysis. Three commonly used bucket aggregation types are:

- **date_histogram**: partitions data by time intervals such as hour, day, week, or month.
- **histogram**: partitions numeric values into equal-width intervals, such as every 100,000 VND or every 5 units.
- **range**: groups data into application-defined intervals, such as under 100,000, from 100,000 to under 500,000, and 500,000 and above.

These aggregations do not return one document per bucket. They return statistics for each group, such as document count, total revenue, average price, or sub-aggregations.

In Spring Data Elasticsearch, you can send bucket aggregations using NativeQuery and the Elasticsearch Java API Client, then read results from the SearchHits aggregation container or corresponding aggregate API. This lesson explains how to choose a bucket type, boundary rules, intervals, timezones, empty buckets, nested aggregations, and how to apply them to reports.

## 1. What is a bucket aggregation?

A bucket aggregation divides a document set into groups based on a field value or rule. Each document can belong to one or more buckets depending on the aggregation type.

Example `orders` index:

~~~json
{
  "orderId": "O-1001",
  "createdAt": "2026-11-13T08:30:00Z",
  "totalInCents": 259900,
  "status": "PAID"
}
~~~

A report might need:

- Number of orders per month.
- Daily revenue.
- Number of products by price range.
- Average order value in each group.
- Number of PAID and CANCELLED orders in each time interval.

Aggregations let Elasticsearch perform grouping on the cluster side instead of loading all documents into Java and grouping them in application memory.

Processing flow:

~~~text
Search request
    |
    v
Query selects the document set to analyze
    |
    v
Bucket aggregation
    |
    +--> Bucket 1
    |      +--> doc_count
    |      +--> metric sub-aggregations
    |
    +--> Bucket 2
    |      +--> doc_count
    |      +--> metric sub-aggregations
    |
    +--> Bucket N
           +--> doc_count
           +--> metric sub-aggregations
    |
    v
Aggregation response
    |
    v
DTO / report / chart
~~~

The query and aggregation have distinct responsibilities:

- The query restricts which documents participate in the analysis.
- The bucket aggregation partitions the selected documents into groups.
- Metric aggregations compute numbers within each group.

For example, filter orders with status = PAID first, then date_histogram groups paid orders by month, and sum calculates monthly revenue.

## 2. Preparing data and mapping

Suppose the Order entity is:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Long)
    private Long totalInCents;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters and setters
}
~~~

Corresponding Elasticsearch mapping:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "totalInCents": {
        "type": "long"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Some principles:

- Fields used for date_histogram must have a `date` mapping or a date type supported by Elasticsearch.
- Fields used for histogram must be aggregatable numeric types, such as integer, long, float, or double.
- Fields used for range aggregation must have a data type compatible with the declared intervals.
- Fields requiring aggregation must have doc values; this is enabled by default for most keyword, numeric, and date fields.
- Standard text fields are unsuitable for numeric histograms or ranges. For text requiring exact-value grouping, use a keyword multi-field.

Inspect the actual mapping:

~~~http
GET /orders/_mapping?pretty
~~~

Java annotations only describe mapping metadata when the index is created via the corresponding configuration. If the index already exists with an old mapping, changing annotations does not automatically update the mapping. Check the live index and perform migration/reindexing if needed.

## 3. Date histogram: grouping documents by time

date_histogram divides date values into buckets by interval. For example:

- Hourly.
- Daily.
- Weekly.
- Monthly.
- Quarterly.
- Yearly.

Example counting orders per day:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day"
      }
    }
  }
}
~~~

Abbreviated response:

~~~json
{
  "aggregations": {
    "orders_per_day": {
      "buckets": [
        {
          "key_as_string": "2026-11-11T00:00:00.000Z",
          "key": 1794355200000,
          "doc_count": 12
        },
        {
          "key_as_string": "2026-11-12T00:00:00.000Z",
          "key": 1794441600000,
          "doc_count": 18
        },
        {
          "key_as_string": "2026-11-13T00:00:00.000Z",
          "key": 1794528000000,
          "doc_count": 9
        }
      ]
    }
  }
}
~~~

Each bucket contains:

- key: the bucket start timestamp in epoch milliseconds.
- key_as_string: the time representation according to the chosen or default format.
- doc_count: the number of documents in the bucket.

Buckets are determined by the interval and timezone. `key` represents the start boundary of the bucket, not the timestamp of a specific document.

### 3.1. Calendar interval and fixed interval

date_histogram provides two ways to define intervals:

- **calendar_interval**: calendar-aware intervals.
- **fixed_interval**: fixed-duration intervals.

Calendar interval example:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "month"
  }
}
~~~

Fixed interval example:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "fixed_interval": "30m"
  }
}
~~~

Calendar intervals fit calendar days, weeks, months, quarters, and years. Fixed intervals fit fixed durations like 15 minutes, 30 minutes, 6 hours, or 24 hours.

You cannot mechanically replace every calendar interval with an equivalent fixed interval. Months have 28, 29, 30, or 31 days; days in DST regions can be 23 or 25 hours long. Calendar intervals preserve calendar boundaries, whereas fixed intervals preserve fixed length.

| Need | Choice |
|---|---|
| Every calendar month | calendar_interval: month |
| Every quarter | calendar_interval: quarter |
| Every calendar week | calendar_interval: week |
| Every exact 15 minutes | fixed_interval: 15m |
| Every exact 6 hours | fixed_interval: 6h |
| Every local calendar day | calendar_interval: day with time_zone |
| Exact 24-hour window | fixed_interval: 24h |

Supported interval values depend on calendar vs. fixed mode in Elasticsearch. Do not use variable calendar units like month or year in fixed_interval.

### 3.2. Commonly used calendar intervals

Example:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "week"
  }
}
~~~

Common calendar units include:

- minute
- hour
- day
- week
- month
- quarter
- year

Unit names in JSON DSL are singular such as day, month, quarter. Check your Elasticsearch version if using newer units or syntax.

### 3.3. fixed_interval

fixed_interval expresses a fixed duration:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_30_minutes": {
      "date_histogram": {
        "field": "createdAt",
        "fixed_interval": "30m"
      }
    }
  }
}
~~~

Common units:

| Symbol | Time interval |
|---|---|
| ms | Millisecond |
| s | Second |
| m | Minute |
| h | Hour |
| d | Day |

For example, 90m is a fixed 90-minute interval. 1d is a fixed 24 hours, which differs from a local calendar day in regions observing DST.

## 4. Timezone in date_histogram

Timestamps in Elasticsearch are usually stored and processed in UTC. Business reports, however, often require boundaries in local time.

For example, a sales system in Vietnam wants to group orders by local day. You can configure:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_local_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
~~~

With UTC+7, daily buckets start at local midnight. The `key` timestamp is still represented as the corresponding UTC epoch millis for that instant.

If `time_zone` is omitted, bucket boundaries default to UTC. This can cause orders near local midnight to fall into a different day than expected by business reports.

### 4.1. Timezone does not modify the original timestamp

time_zone only controls how Elasticsearch rounds and interprets bucket boundaries. It does not modify the timestamp stored in the document.

If a document is stored as 2026-11-13T08:00:00Z, it remains the same instant. When grouped using Asia/Ho_Chi_Minh, that instant corresponds to 15:00 on 2026-11-13 in Vietnam.

Do not add 7 hours to the source document and also set time_zone to Asia/Ho_Chi_Minh; doing so shifts the time twice if the original data already represented the true instant.

### 4.2. DST and calendar intervals

In timezones with daylight saving time, a calendar day can be 23 or 25 hours long. Calendar intervals follow the calendar and timezone, while fixed intervals maintain a constant duration.

If a report needs "each local day", `calendar_interval: day` with timezone is usually the right choice. If a system needs exact 24-hour windows from an epoch anchor, `fixed_interval` fits better.

## 5. Offset and format in date_histogram

offset shifts bucket boundaries relative to the default rounding anchor. For example, if you want daily buckets to start at 06:00 instead of midnight, use offset:

~~~http
POST /events/_search
{
  "size": 0,
  "aggs": {
    "business_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "offset": "+6h"
      }
    }
  }
}
~~~

This groups by operational days starting at 06:00. Understand how offset interacts with rounding rules and timezone; verify timestamps near boundaries with test data.

format lets you customize key_as_string formatting:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "month",
    "format": "yyyy-MM"
  }
}
~~~

The numeric key remains the epoch timestamp; format only changes the string representation. Applications should use `key` for exact time processing and `key_as_string` for display labels where appropriate.

## 6. Empty buckets: min_doc_count and extended_bounds

By default, date_histogram usually returns only buckets containing documents. A daily report might need to show days with no orders as `doc_count = 0`.

Use min_doc_count: 0 together with extended_bounds:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "min_doc_count": 0,
        "extended_bounds": {
          "min": "2026-11-01",
          "max": "2026-11-07"
        }
      }
    }
  }
}
~~~

Meaning:

- min_doc_count: 0 allows empty buckets to be returned.
- extended_bounds expands the bucket range to the min/max bounds even when no documents exist there.
- Buckets within the range can appear with doc_count equal to 0.

extended_bounds does not filter documents. If you need to analyze only documents within a date range, add a range query in the `query` section.

Combined example:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-11-01T00:00:00+07:00",
        "lt": "2026-11-08T00:00:00+07:00"
      }
    }
  },
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "min_doc_count": 0,
        "extended_bounds": {
          "min": "2026-11-01",
          "max": "2026-11-07"
        }
      }
    }
  }
}
~~~

The range query selects documents belonging to the reporting window. extended_bounds ensures empty day buckets are generated within the desired range.

### 6.1. extended_bounds and hard_bounds

These two options serve different purposes:

| Option | Meaning |
|---|---|
| extended_bounds | Expands the bucket range so empty buckets can be generated up to the specified bounds |
| hard_bounds | Restricts generated buckets, preventing buckets outside the specified min/max |

extended_bounds is not a data filter and does not guarantee preventing out-of-range buckets produced by actual documents. If you need to cap the bucket range, use `hard_bounds` appropriately; if you need to filter documents, use a range query.

Example:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "day",
    "min_doc_count": 0,
    "extended_bounds": {
      "min": "2026-11-01",
      "max": "2026-11-30"
    },
    "hard_bounds": {
      "min": "2026-11-01",
      "max": "2026-11-30"
    }
  }
}
~~~

Be careful with wide time ranges and min_doc_count = 0. Requesting per-minute buckets across multiple years can generate a massive number of buckets.

## 7. Histogram: partitioning numeric fields into equal intervals

The histogram aggregation divides numeric values into equal-sized buckets. For example, grouping orders by total amount in buckets of 100,000 units:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_by_amount": {
      "histogram": {
        "field": "totalInCents",
        "interval": 10000000
      }
    }
  }
}
~~~

In the example, totalInCents is stored in cents. An interval of 10,000,000 cents equals 100,000 currency units assuming 100 cents = 1 currency unit.

Histogram automatically computes uniform buckets based on the interval. Each bucket has `key` as the bucket boundary and `doc_count` as the number of documents in that interval.

### 7.1. How buckets are determined

Conceptually, histogram uses interval and offset to determine bucket keys. For value x, interval i, and offset o, the bucket key is determined by rounding down on the shifted interval grid:

\[
key = \left\lfloor \frac{x-o}{i} \right\rfloor i + o
\]

Example with interval = 100 and offset = 0:

| Value | Bucket key |
|---:|---:|
| 12 | 0 |
| 99 | 0 |
| 100 | 100 |
| 175 | 100 |
| 250 | 200 |

Buckets are half-open intervals in the standard sense: [0,100), [100,200), [200,300), ... A value right on a boundary belongs to the bucket starting at that boundary.

### 7.2. Offset for histogram

offset shifts numeric buckets:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "histogram": {
        "field": "priceInCents",
        "interval": 100000,
        "offset": 50000
      }
    }
  }
}
~~~

With interval 100,000 and offset 50,000, buckets start at 50,000, 150,000, 250,000, ... according to histogram rounding rules.

Offset is useful when business boundaries do not align with multiples of 0 for the interval. Verify negative values and boundary values if the dataset can contain them.

### 7.3. min_doc_count and empty buckets for histogram

Like date_histogram, histogram can omit empty buckets by default. You can request empty buckets:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "histogram": {
        "field": "priceInCents",
        "interval": 100000,
        "min_doc_count": 0,
        "extended_bounds": {
          "min": 0,
          "max": 500000
        }
      }
    }
  }
}
~~~

extended_bounds creates buckets within the desired range, while min_doc_count = 0 allows buckets with no documents to appear with doc_count = 0.

If you want no buckets outside the specified range, consider hard_bounds. If you need to select only documents whose price falls in the range, add a separate range query.

### 7.4. Histogram and missing values

Documents lacking the numeric field are normally excluded from buckets. If business rules treat missing prices as a default value, you can use missing:

~~~json
{
  "histogram": {
    "field": "priceInCents",
    "interval": 100000,
    "missing": 0
  }
}
~~~

Documents without priceInCents are then treated as having value 0 for this aggregation. This only applies inside the aggregation and does not write 0 into the document.

Use `missing` only if the substitute value makes business sense. A missing price and a price of 0 may mean two different things; merging them could distort reports.

## 8. Range aggregation: application-defined value ranges

histogram creates equal-width buckets by interval. Range aggregation allows defining unequal intervals, such as:

- Price under 100,000.
- Price from 100,000 to under 500,000.
- Price from 500,000 to under 2,000,000.
- Price 2,000,000 and above.

REST DSL:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "priceInCents",
        "ranges": [
          { "to": 10000000 },
          { "from": 10000000, "to": 50000000 },
          { "from": 50000000, "to": 200000000 },
          { "from": 200000000 }
        ]
      }
    }
  }
}
~~~

Each range can specify from, to, or both:

| Range | Meaning |
|---|---|
| Only `to` | No lower bound, strictly less than `to` |
| `from` and `to` | From `from` up to (but excluding) `to` |
| Only `from` | From `from` and above |

In standard range aggregations, `from` is inclusive and `to` is exclusive. Therefore, adjacent intervals like [0,100), [100,500) do not overlap at boundary 100.

### 8.1. Setting keys for each range

You can assign custom keys:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "priceInCents",
        "keyed": true,
        "ranges": [
          {
            "key": "budget",
            "to": 10000000
          },
          {
            "key": "standard",
            "from": 10000000,
            "to": 50000000
          },
          {
            "key": "premium",
            "from": 50000000
          }
        ]
      }
    }
  }
}
~~~

keyed: true causes response buckets to be returned as an object keyed by name instead of a list. This is convenient when mapping buckets by business name, though you must check the corresponding response type in the Java client.

If no key is set, Elasticsearch typically generates a key from the range bounds. Setting explicit keys makes responses easier to read and more stable for consuming applications.

### 8.2. Ranges can overlap

Unlike histogram, range aggregations allow overlapping intervals:

~~~json
{
  "range": {
    "field": "priceInCents",
    "ranges": [
      { "key": "under_500k", "to": 50000000 },
      { "key": "under_1m", "to": 100000000 },
      { "key": "premium", "from": 50000000 }
    ]
  }
}
~~~

A document priced at 300,000 currency units can belong to both under_500k and under_1m. A document priced at 700,000 can belong to under_1m and premium.

This is useful for overlapping analytical cohorts, though the sum of bucket doc_counts can exceed the total number of unique documents. If you want non-overlapping partitions, design adjacent and explicit from/to bounds.

## 9. Date range aggregation: grouping by business time periods

Date range aggregation works like range but for date fields. It is useful when intervals are uneven or follow business periods, such as:

- Before the current month.
- During the current month.
- During the current quarter.
- After a campaign launch date.

Example:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "order_periods": {
      "date_range": {
        "field": "createdAt",
        "time_zone": "Asia/Ho_Chi_Minh",
        "format": "yyyy-MM-dd",
        "ranges": [
          {
            "key": "before_november",
            "to": "2026-11-01"
          },
          {
            "key": "november",
            "from": "2026-11-01",
            "to": "2026-12-01"
          },
          {
            "key": "december_onward",
            "from": "2026-12-01"
          }
        ]
      }
    }
  }
}
~~~

Date range fits cases where boundaries are dictated by business logic. If you need continuous daily or monthly buckets, date_histogram is usually cleaner.

Date range can use date math in expressions supported by Elasticsearch. For reproducible reports, specify explicit timestamps or pass concrete date bounds rather than relying on `now` without recording the report execution time.

### 9.1. Date range and timezone

When using date_range, specify an appropriate format and timezone. Date strings without offsets may be interpreted using the request's timezone or parser rules. Use timestamps with explicit timezones or configure `time_zone` to avoid shifted day boundaries.

For a monthly report in Vietnam, the November range can be written as:

~~~text
from = 2026-11-01T00:00:00+07:00
to   = 2026-12-01T00:00:00+07:00
~~~

The `to` bound is exclusive, so a document at exact midnight on Dec 1 belongs to December rather than November.

## 10. Comparing date_histogram, histogram, and range

| Criterion | date_histogram | histogram | range / date_range |
|---|---|---|---|
| Field | Date | Numeric | Numeric or date |
| Buckets | Calendar or fixed duration | Uniform numeric intervals | Application-defined from/to |
| Boundaries | Calendar/fixed rounding | Interval and offset | Custom bounds |
| Empty buckets | min_doc_count, extended_bounds | min_doc_count, extended_bounds | Does not auto-generate intervals outside declared list |
| Timezone | Yes | Not applicable | date_range can use time_zone |
| Overlap | Not in the usual histogram bucket sense | No | Can overlap |
| Used for | Time-based reporting | Numeric value distribution | Grouping by business thresholds |

Choose based on the question to answer:

- Daily/monthly revenue: date_histogram.
- Product price distribution in equal steps: histogram.
- Customer tiers by predefined spending brackets: range.
- Order counts during campaign phases: date_range.
- Grouping by local day: date_histogram calendar_interval day with time_zone.

## 11. Metric sub-aggregations inside buckets

Bucket aggregations are commonly combined with metric aggregations to calculate numbers for each group.

Example counting orders and summing revenue by month:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "PAID"
    }
  },
  "aggs": {
    "orders_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        },
        "average_order_value": {
          "avg": {
            "field": "totalInCents"
          }
        },
        "max_order_value": {
          "max": {
            "field": "totalInCents"
          }
        }
      }
    }
  }
}
~~~

Each bucket in the response has doc_count, revenue.value, average_order_value.value, and max_order_value.value.

Multiple bucket levels can be nested:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      },
      "aggs": {
        "by_status": {
          "terms": {
            "field": "status"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalInCents"
              }
            }
          }
        }
      }
    }
  }
}
~~~

The result has the structure month → status → revenue. This form suits multidimensional reporting.

Do not nest too many high-cardinality bucket levels without evaluating cost. Combined bucket counts can grow rapidly.

## 12. Filtering before aggregation

You can restrict the document set using a request-level query:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PAID"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2027-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "orders_per_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      }
    }
  }
}
~~~

The top-level query restricts all documents participating in aggregations. If you need multiple groups with different filter conditions in one response, use filter aggregation or filters aggregation.

Example grouping revenue by status:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        }
      }
    },
    "cancelled_orders": {
      "filter": {
        "term": {
          "status": "CANCELLED"
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        }
      }
    }
  }
}
~~~

A filter aggregation affects only its own branch and does not exclude documents from sibling aggregation branches.

## 13. Computing ratios and aggregated figures across buckets

You can use pipeline aggregations on bucket results, such as calculating ratios or changes between consecutive buckets. Common pipelines include:

- bucket_script: computes an expression from bucket metrics.
- bucket_selector: excludes buckets based on a condition.
- derivative: calculates change between buckets.
- cumulative_sum: calculates running totals.
- moving_fn: computes a sliding window with a custom function.

Example calculating cumulative monthly revenue:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "revenue_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        },
        "cumulative_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }
  }
}
~~~

Pipeline aggregations operate on other aggregation results. They do not replace the initial query filter or bucket aggregation. Some pipelines require a parent bucket aggregation and have specific rules for handling empty buckets.

## 14. Bucket limits and performance

Aggregations can generate many buckets. A query grouping by second over several years of data could theoretically produce tens of millions of intervals if empty buckets are forced.

Factors to consider:

- Number of shards and indices queried.
- Number of buckets generated.
- Depth of nested aggregations.
- Cardinality of terms fields inside each bucket.
- Number of metric sub-aggregations.
- min_doc_count = 0 and extended_bounds.
- Response size.
- Concurrency and cluster load.

Elasticsearch enforces a `search.max_buckets` limit on total buckets in a search response (commonly 65,536 by default, configurable). Exceeding the limit may cause the request to be rejected.

Ways to control this:

- Limit the time range with a range query.
- Choose an interval matching the required display granularity.
- Avoid generating empty buckets over overly wide ranges.
- Reduce aggregation nesting depth.
- Use composite aggregation when paginating through many buckets.
- Avoid nesting high-cardinality terms aggregations inside each date bucket unnecessarily.
- Return only required metrics.

### 14.1. Histogram is not a pagination mechanism for large bucket sets

If you need to iterate over all multidimensional buckets at large scale, composite aggregation is usually a better fit. Composite allows paginating buckets via after_key, though it has different semantics and configuration than histogram/range.

Do not raise `search.max_buckets` indefinitely just to make a large query run. Re-examine the report design and data range instead.

## 15. Composite aggregation and after_key

Composite aggregation constructs buckets from one or more sources (terms, histogram, date_histogram) and supports pagination. Example:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month_and_status": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "month": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month"
              }
            }
          },
          {
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

If the response includes after_key, the next request passes that value into `after`:

~~~json
{
  "composite": {
    "size": 500,
    "after": {
      "month": 1793491200000,
      "status": "PAID"
    },
    "sources": [
      {
        "month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          }
        }
      },
      {
        "status": {
          "terms": {
            "field": "status"
          }
        }
      }
    ]
  }
}
~~~

The `after` value must be taken from the previous response's `after_key`, not inferred from the last bucket. Keep the order and definitions of sources identical across pages.

Composite aggregation fits cases where you must scan all bucket combinations for large exports or batch processing. It does not replace every simple date_histogram or histogram.

## 16. NativeQuery in Spring Data Elasticsearch

Spring Data Elasticsearch 5.x uses NativeQuery to pass aggregations built with the Elasticsearch Java API Client.

Example monthly date_histogram:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation byMonth = Aggregation.of(a -> a
    .dateHistogram(h -> h
        .field("createdAt")
        .calendarInterval(CalendarInterval.Month)
        .timeZone("Asia/Ho_Chi_Minh")
    )
);

NativeQuery query = NativeQuery.builder()
    .withAggregation("orders_by_month", byMonth)
    .withMaxResults(0)
    .build();

SearchHits<Order> hits =
    operations.search(query, Order.class);
~~~

In this example:

- Aggregation is the type from the Elasticsearch Java API Client.
- dateHistogram creates monthly buckets.
- calendarInterval(CalendarInterval.Month) uses calendar months.
- timeZone sets boundaries according to Vietnam time.
- withAggregation attaches the aggregation to NativeQuery.
- withMaxResults(0) requests zero document hits when only aggregations are needed, if this overload is supported in your project version.

Enum names, builder methods, and APIs for setting max results can change across versions. Check the Javadoc of your actual Spring Data Elasticsearch and Elasticsearch Java API Client dependencies. If withMaxResults(0) is unavailable, use the corresponding size = 0 option in that version's query API.

### 16.1. Histogram with NativeQuery

The Java API Client expresses a histogram aggregation via its builder:

~~~java
Aggregation byPrice = Aggregation.of(a -> a
    .histogram(h -> h
        .field("totalInCents")
        .interval(10000000.0)
        .minDocCount(0)
    )
);
~~~

Attach the aggregation to NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("orders_by_amount", byPrice)
    .withMaxResults(0)
    .build();
~~~

The interval type is numeric. Choose units matching how the application stores values. If the field stores cents while the interval is treated as main currency units, buckets will be 100 times too wide.

### 16.2. Range aggregation with NativeQuery

The Elasticsearch Java API Client provides builders for range aggregations. The exact Java structure varies by client version and field type; consult the Javadoc of Aggregation.Builder, RangeAggregation.Builder, and the corresponding range expressions.

At the DSL level, the generated configuration takes the form:

~~~json
{
  "range": {
    "field": "totalInCents",
    "ranges": [
      { "key": "low", "to": 10000000 },
      { "key": "medium", "from": 10000000, "to": 50000000 },
      { "key": "high", "from": 50000000 }
    ]
  }
}
~~~

If the client version uses RangeExpression or a separate range union type, use the exact type suggested by your IDE. Do not mix Java API Client Range types with Spring Data Criteria Range queries.

### 16.3. Combining a query filter with aggregations

You can add a query to NativeQuery alongside aggregations:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(paidOrdersQuery)
    .withAggregation("orders_by_month", byMonth)
    .withMaxResults(0)
    .build();
~~~

Here `paidOrdersQuery` is a query from the Elasticsearch Java API Client, such as bool/filter on status and createdAt. The query restricts documents for the aggregation.

## 17. Reading aggregation results in Spring Data

`SearchHits<T>` contains search hits and the aggregation container. In Spring Data Elasticsearch 5.x, the container type is typically `ElasticsearchAggregations` when using the Elasticsearch Java API Client.

Common reading pattern:

~~~java
SearchHits<Order> hits =
    operations.search(query, Order.class);

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) hits.getAggregations();

ElasticsearchAggregation byMonth =
    aggregations.get("orders_by_month");
~~~

From the aggregation wrapper, you can obtain the specific Elasticsearch Java API Client aggregate and read the corresponding bucket list. Accessor names and aggregate union types depend on the client version.

Conceptual example for date histogram:

~~~java
// Pseudocode: the specific accessor depends on the Elasticsearch Java API Client version.
DateHistogramAggregate dateHistogram =
    byMonth.aggregation().getAggregate().dateHistogram();

for (DateHistogramBucket bucket : dateHistogram.buckets().array()) {
    long timestamp = bucket.key();
    long count = bucket.docCount();
}
~~~

If the response uses keyed buckets instead of array buckets, read the corresponding keyed variant. Do not assume every aggregation returns a bucket array.

### 17.1. Keeping the right aggregation type

The Elasticsearch Java API Client uses union types for aggregates. An aggregate can be dateHistogram, histogram, range, terms, sum, avg, or another kind. When reading results, extract the variant matching the declared aggregation.

For example:

- date_histogram → DateHistogramAggregate.
- histogram → HistogramAggregate.
- range → RangeAggregate.
- date_range → DateRangeAggregate.
- sum → SumAggregate.
- avg → AvgAggregate.

Accessing the wrong variant can return null or throw an error depending on the API. Verify the aggregation name in the response and the actual bucket type.

### 17.2. SearchHits or aggregate-only API?

If you need both document hits and aggregations, use search to receive SearchHits along with aggregation metadata.

If you only need aggregations, you can use the appropriate aggregate/query API exposed by your Spring Data version. The return signature may be `AggregationsContainer<?>` or a corresponding wrapper. Check `ElasticsearchOperations` in your actual dependency.

Do not fetch dozens of documents just to get aggregations. Set size = 0 or max results = 0 per the supported API to minimize hit payloads when reports only need buckets.

## 18. Building DTOs for reports

Do not expose internal Elasticsearch aggregation types directly from an API. Map buckets to DTOs:

~~~java
public record TimeBucket(
    long timestamp,
    String label,
    long documentCount,
    double revenue
) {
}
~~~

Mapping logic example:

~~~java
List<TimeBucket> result = buckets.stream()
    .map(bucket -> new TimeBucket(
        bucket.key(),
        formatBucketLabel(bucket.key()),
        bucket.docCount(),
        readRevenueMetric(bucket)
    ))
    .toList();
~~~

`formatBucketLabel` and `readRevenueMetric` are application functions based on the specific bucket/aggregate type. For date_histogram, `key` is usually epoch milliseconds. For numeric histogram, `key` is the bucket's numeric boundary. For range, buckets usually contain key, from, and to.

DTOs should express units clearly. If revenue is stored in cents, the response field could be `revenueInCents` or converted to display units according to the API contract. Never leave units ambiguous.

## 19. Missing values and documents without the field

Bucket aggregations normally skip documents lacking a value for the bucketing source field. For instance, a document without `createdAt` will not appear in a date_histogram.

Some aggregations let you configure `missing` to substitute a fallback value within the aggregation scope:

~~~json
{
  "histogram": {
    "field": "priceInCents",
    "interval": 100000,
    "missing": 0
  }
}
~~~

For date_histogram, you can supply a missing value in an appropriate date format if supported by the API. However, consider semantics: a missing date does not necessarily mean the epoch date or some arbitrary default date.

If you want to report the number of documents missing a date or price, use a separate filter aggregation or missing aggregation to count documents lacking the field rather than merging them into a synthetic bucket.

## 20. Common mistakes

| Symptom | Possible cause | How to check |
|---|---|---|
| date_histogram reports field is not a date | Field mapping is not date or wrong field name | Inspect mapping and check documents |
| Daily buckets are shifted by one day | Default UTC timezone or wrong query bounds | Set time_zone and use timestamps with offsets |
| Monthly report has misaligned boundaries | Using fixed interval instead of calendar interval | Use calendar_interval month |
| Empty buckets do not appear | min_doc_count is still default or extended_bounds missing | Set min_doc_count: 0 and extended_bounds |
| Out-of-range buckets still appear | extended_bounds is not a filter or hard limit | Use a range query and hard_bounds when appropriate |
| Histogram intervals have wrong units | Interval unit differs from field unit | Check whether field stores cents, VND, milliseconds, etc. |
| Boundary value falls into unexpected bucket | Misunderstanding rounding rule or offset | Check interval, offset, and boundary values |
| Range buckets overlap | Overlapping from/to declarations | Review inclusive/exclusive bounds |
| Sum of doc_count exceeds total documents | Overlapping range buckets or multi-valued fields | Inspect declared intervals |
| Cannot read aggregation in Java | Accessing wrong wrapper/variant or version mismatch | Inspect SearchHits.getAggregations and client types |
| Request exceeds search.max_buckets | Too many buckets or nested aggregations | Increase interval, narrow range, or reduce nesting |
| Aggregation returns incomplete numbers | Documents missing field or mapping lacks doc values | Check source, mapping, and missing behavior |

## 21. Report design workflow

When designing aggregations, determine step by step:

1. Is the grouping field date or numeric?
2. Do you want to group by calendar, fixed duration, or business thresholds?
3. Is a local timezone required?
4. Do empty buckets need to be displayed?
5. Which time or value range enters the analysis?
6. Should documents be filtered before aggregation?
7. Within each bucket, which metrics are needed: count, sum, avg, min, max?
8. Are nested buckets by status, category, or tenant required?
9. Will the expected bucket count exceed cluster limits?
10. Does the application need to read key, key_as_string, from/to, or metrics?
11. Are currency/time units explicitly documented in the DTO?
12. Is composite aggregation needed to paginate buckets?

A syntactically valid configuration can still produce incorrect reports if the timezone, units, or interval boundaries fail to match business rules.

## 22. Quick reference table

| Need | Aggregation |
|---|---|
| Count orders per day | date_histogram with calendar_interval day |
| Monthly revenue | date_histogram month + sum |
| Group events every 15 minutes | date_histogram with fixed_interval 15m |
| Group prices by equal steps | histogram with interval |
| Generate empty buckets | min_doc_count: 0 + extended_bounds |
| Cap generated buckets | hard_bounds |
| Group prices by custom thresholds | range |
| Group time by campaign periods | date_range |
| Group multidimensionally by month and status | Nested bucket aggregations |
| Paginate through huge bucket counts | composite aggregation + after_key |
| Filter documents before grouping | Query or filter aggregation |
| Compute revenue per bucket | sum sub-aggregation |
| Compute average value per bucket | avg sub-aggregation |

date_histogram fits calendar-based or fixed-duration time analysis; histogram divides numeric values into equal-width buckets; range/date_range use business-defined boundaries and can overlap. Choose the interval matching calendar or fixed semantics, specify timezone and offset explicitly, distinguish extended_bounds from query filters/hard_bounds, and combine metric sub-aggregations to build reports. In Spring Data Elasticsearch, use NativeQuery with Elasticsearch Java API Client aggregations, read the appropriate aggregation wrapper/variant for your version, and bound bucket counts to keep requests within cluster operating capacity.
