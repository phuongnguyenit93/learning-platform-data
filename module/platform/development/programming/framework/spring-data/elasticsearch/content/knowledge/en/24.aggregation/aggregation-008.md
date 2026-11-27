# Cardinality, Percentiles, and Accuracy Limits

Elasticsearch provides several aggregations to summarize data without loading every document into the application. Among them, `cardinality` estimates the number of unique values, while `percentiles` and `percentile_ranks` describe the distribution of numeric data.

These aggregations are valuable for dashboards, behavioral analytics, and performance monitoring. For instance, a system may need to estimate daily unique users, calculate P50/P95/P99 of response times, or determine which percentile a given value falls into within a dataset.

A crucial point to understand is that these results are typically approximate. Elasticsearch uses bounded-memory algorithms and settings to process distributed data across multiple shards. Increasing accuracy usually increases memory usage or computation time. Therefore, choose settings based on business requirements rather than assuming a percentile or distinct count is strictly exact.

## 1. Overview of Cardinality and Percentiles

### 1.1. Cardinality is the number of distinct values

Cardinality answers how many different values exist in a field.

Example event data:

| eventId | userId | eventType |
|---|---|---|
| E01 | U100 | view |
| E02 | U101 | click |
| E03 | U100 | purchase |
| E04 | U102 | view |
| E05 | U101 | view |

There are 5 documents, yet only 3 unique `userId` values: U100, U101, and U102.

A regular aggregation can count documents. A cardinality aggregation counts unique values of a field, making it suited for questions such as:

- How many unique users visited the website?
- How many distinct IP addresses appeared?
- How many different products were viewed?
- How many unique sessions or devices occurred?
- How many distinct order IDs exist within a time range?

Cardinality aggregation is typically an estimate based on HyperLogLog++, not an exact count of every unique value.

### 1.2. Percentiles describe position in a distribution

A percentile indicates where a value sits within a sorted distribution.

For example, if the P95 response time is 850 ms, it can be roughly interpreted that 95% of observations have a response time at or below 850 ms, and roughly 5% sit above that level.

Common percentiles:

| Percentile | Common meaning |
|---|---|
| P50 | Median, the middle value of the distribution |
| P75 | Threshold at or below which about 75% of observations lie |
| P90 | 90th percentile mark |
| P95 | 95th percentile mark, commonly used to monitor tail latency |
| P99 | 99th percentile mark, focusing on the tail |
| P99.9 | Very deep tail, sensitive to outliers and sample size |

Percentiles are more informative than averages in many latency problems because an average can hide a cluster of very slow requests.

### 1.3. Percentiles and percentile ranks work in opposite directions

- `percentiles` takes percentage thresholds and returns the corresponding values in the distribution.
- `percentile_ranks` takes specific values and returns the estimated percentage position of each value in the distribution.

For example:

- The 95th percentile returns the response time at the P95 mark.
- The percentile rank of 500 ms returns the percentage of observations at or below roughly 500 ms.

Do not confuse these two calculations when naming fields on a dashboard.

## 2. Cardinality aggregation

### 2.1. Basic Query DSL

Example counting unique `userId` values:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_users": {
      "cardinality": {
        "field": "userId"
      }
    }
  }
}
~~~

`size: 0` indicates that document hits do not need to be returned. The response focuses on aggregations.

Conceptual result shape:

~~~json
{
  "aggregations": {
    "unique_users": {
      "value": 3
    }
  }
}
~~~

The value `3` in a tiny dataset is an illustrative result. On large datasets, cardinality is typically an estimate and can deviate from the exact distinct count.

### 2.2. Fields must be suitable for distinct counting

Cardinality operates on indexed field values. Commonly used fields include:

- `keyword`: user IDs, session IDs, product codes.
- Numeric: numeric codes or numeric values needing distinct counts.
- `ip`: IP addresses.
- Other field types supporting doc values per mapping.

For text fields, check the mapping carefully. A `text` field is analyzed into tokens and usually lacks doc values by default. Counting cardinality on a text field is rarely the intended behavior. If you need a distinct count of full strings, use a keyword subfield.

Multi-field example:

~~~json
{
  "mappings": {
    "properties": {
      "email": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

When counting unique emails, use `email.keyword` instead of `email`.

### 2.3. Cardinality inside bucket aggregations

You can compute unique users per day or per category:

~~~json
{
  "size": 0,
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day"
      },
      "aggs": {
        "unique_users": {
          "cardinality": {
            "field": "userId"
          }
        }
      }
    }
  }
}
~~~

Each daily bucket receives its own distinct user estimate. This is a common pattern in daily activity dashboards.

If there are many buckets, each bucket maintains its own cardinality state. Total memory cost can grow with bucket count and precision settings. Avoid creating hundreds of thousands of buckets with high precision thresholds per bucket without load evaluation.

### 2.4. Missing values

Documents missing the field normally do not contribute to cardinality. If you want to treat all documents missing the field as a single fallback value, use the `missing` option:

~~~json
{
  "cardinality": {
    "field": "campaignId",
    "missing": "unknown"
  }
}
~~~

In this example, documents without a `campaignId` are treated as sharing the value `unknown` for the aggregation. This alters the statistical meaning: the result includes an extra distinct group representing missing data.

Use `missing` only when business logic genuinely wants to group missing-field documents into one category. Otherwise, skipping them reflects the count of actually known values more accurately.

### 2.5. Cardinality on scripted values

You can compute cardinality from a script or runtime field when values must be normalized before counting—for example, conceptually lowercasing codes prior to distinct counting.

However, scripts incur per-document overhead and can significantly increase load. If normalized values are queried frequently, precompute and store them in a keyword field at ingest time.

When counting a composite key from multiple fields, avoid joining strings with a delimiter that might appear inside the data. Two different pairs of values can produce the same string if encoding is ambiguous. Consider a composite aggregation or a precomputed, unambiguous normalized composite key.

## 3. HyperLogLog++ and Cardinality accuracy

### 3.1. Why doesn't Elasticsearch store the entire set of values?

If an index holds hundreds of millions of user IDs, keeping the full distinct set in memory for exact counting would be prohibitively expensive. On a distributed system, each shard would also have to build and send value-set data to the coordinator.

Cardinality aggregation uses the HyperLogLog++ (HLL++) algorithm to estimate unique elements using a bounded-size data structure. Instead of storing every seen value, the algorithm uses registers and hash bits to estimate cardinality.

Benefits:

- Memory does not grow linearly with total document count.
- Results from multiple shards can be merged.
- Well suited for distinct counts over large datasets.
- Provides a tunable trade-off between memory and accuracy.

In return, the result carries statistical error and is not guaranteed to equal the exact distinct count in every situation.

### 3.2. What is precision_threshold?

`precision_threshold` adjusts the cardinality level up to which Elasticsearch targets higher accuracy. It is a target threshold for the number of unique values, not a guarantee that every count below the threshold is strictly exact.

Example:

~~~json
{
  "cardinality": {
    "field": "userId",
    "precision_threshold": 10000
  }
}
~~~

Key benchmarks in Elasticsearch:

- The default value is commonly 3,000.
- The maximum effective value is 40,000.
- Values higher than 40,000 do not improve accuracy further.
- Memory usage increases with the precision threshold.

Check the documentation for your running Elasticsearch version because implementation details and limits can change across versions.

### 3.3. Choosing a threshold based on expected cardinality

If a bucket typically contains only a few hundred unique users, setting a large threshold wastes memory. If a bucket typically has tens of thousands of values, the default threshold may yield error rates unsuitable for dashboard requirements.

Directional guide:

| Expected cardinality per bucket | Guidance |
|---|---|
| Tens to a few hundreds | Default threshold is likely sufficient |
| A few thousands | Benchmark default vs. a higher threshold |
| Tens of thousands | Consider a threshold near the required cap |
| Millions | Do not set a threshold in the millions; the algorithm remains an estimate with bounded memory |
| Exact distinct required | Use bucket enumeration or another data model |

Do not choose the threshold based solely on total document count. What matters is the estimated number of unique values inside each aggregation bucket.

### 3.4. Memory trade-off

Raising precision threshold can reduce error in the target cardinality range, yet each aggregation allocates additional state memory. When cardinality runs inside many buckets, total memory can grow substantially.

Consider all of these together:

- Number of buckets generated.
- Number of cardinality aggregations in the request.
- Number of shards involved.
- Number of concurrent requests.
- Threshold configured for each aggregation.
- Actual data size and distribution.

A dashboard with many date histogram buckets, each carrying a high-threshold cardinality aggregation, can consume far more memory than anticipated.

### 3.5. Do not sum bucket cardinalities to infer global distinct count

Suppose:

- Day 1 has 100 unique users.
- Day 2 has 120 unique users.
- 50 users appeared on both days.

The total distinct users across both days is 170, not 220.

Per-bucket cardinality is useful for measuring daily unique users. However, summing bucket results does not produce unique users across the entire period if the same value appears in multiple buckets.

If you need overall unique users across the period, run cardinality at the overall scope or use an appropriate exact method.

### 3.6. Error is not always a fixed percentage

Cardinality error is an inherent property of the estimation algorithm. Do not interpret results as "always off by at most 1%" or manually add/subtract a fixed margin without benchmarks and documentation specific to your workload.

Test on sample data with a known exact distinct count, at scale and distribution close to production. Measure relative error:

\[
relativeError = \frac{|estimated - actual|}{actual}
\]

When `actual` is 0, handle it separately to avoid division by zero.

## 4. When is an exact distinct count needed?

### 4.1. Cardinality is not an exact count

If the business requires an exact number for reconciliation, billing, charging, or auditing, do not rely on a cardinality approximation as the final source of truth.

Cardinality fits analytics, dashboards, and metrics where small error margins are acceptable. It does not replace an exact counting pipeline when results have direct financial or compliance consequences.

### 4.2. Composite aggregation to enumerate unique keys

Composite aggregation lets you paginate through buckets across one or more source fields. If you need an exact count of distinct keys, you can scan all buckets and count the buckets received.

Example query:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_users": {
      "composite": {
        "size": 1000,
        "sources": [
          {
            "user": {
              "terms": {
                "field": "userId"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

If the response contains `after_key`, send the next request with `after` set to that value until no buckets remain. Each bucket represents one unique value for the declared source.

Because this enumerates buckets, cost scales with the number of distinct values. For very high cardinality, process in batches, bound time and memory, and consider PIT or a snapshot strategy if data changes during traversal.

### 4.3. Distinct across combinations of multiple fields

For example, counting unique pairs of `userId` and `deviceId`. You can create a composite aggregation with two sources:

~~~json
{
  "size": 0,
  "aggs": {
    "unique_user_devices": {
      "composite": {
        "size": 1000,
        "sources": [
          {
            "user": {
              "terms": {
                "field": "userId"
              }
            }
          },
          {
            "device": {
              "terms": {
                "field": "deviceId"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Each bucket represents one combination of values. Iterating through all pages and counting buckets yields the number of distinct combinations within the query's scope.

If you use a script to join two fields into one string for cardinality, you need unambiguous encoding and handling for missing/null values. Composite usually expresses tuple semantics more cleanly.

### 4.4. Terms aggregation is not unconditionally exact

A terms aggregation returns top buckets according to `size` and `shard_size`. It can omit lower-frequency buckets and emits metadata like `sum_other_doc_count` or `doc_count_error_upper_bound`.

Do not set a small size and count returned buckets assuming that is the total distinct count. Even with a very large size, bucket limits and memory constraints still apply. Composite is better suited when the goal is paginated traversal of all keys.

### 4.5. Snapshots and changing data

If data changes while paginating through composite pages, buckets may reflect index states at different points in time. For reproducible reports, establish a snapshot or closed time range, and consider PIT if your API/version and aggregation type support it in your architecture.

Do not assume multiple sequential composite requests automatically form a consistent transaction or snapshot.

## 5. Percentiles aggregation

### 5.1. Basic Query DSL

Example computing response time percentiles:

~~~json
{
  "size": 0,
  "aggs": {
    "response_time_percentiles": {
      "percentiles": {
        "field": "responseTime",
        "percents": [50, 90, 95, 99]
      }
    }
  }
}
~~~

The result can look like:

~~~json
{
  "aggregations": {
    "response_time_percentiles": {
      "values": {
        "50.0": 120.5,
        "90.0": 410.0,
        "95.0": 620.0,
        "99.0": 1250.0
      }
    }
  }
}
~~~

Values are illustrative. If P99 is 1,250 ms, it indicates that the vast majority of requests are faster than that threshold while a tail of roughly 1% experiences higher latency.

### 5.2. Choosing appropriate percentiles

Not every dashboard needs every percentile. Common choices:

- P50 for the typical experience.
- P90 or P95 for slower-than-normal requests.
- P99 for tail latency.
- P99.9 when sample sizes are large enough and deep-tail visibility is required.

P99.9 on a bucket with only a few hundred observations is usually unstable and hard to interpret. Higher percentiles depend increasingly on sample size and extreme tail outliers.

### 5.3. Percentile is not average

Suppose the latency (ms) of 5 requests is:

~~~text
10, 12, 15, 20, 1000
~~~

The average is 211.4 ms, yet the median/P50 is near 15 ms. The average is skewed upward by a single very slow request. P95/P99 expose tail latency, while P50 reflects the center of the distribution.

Combine percentiles with counts and occasionally average/min/max to understand sample size and data shape.

### 5.4. Percentiles per bucket

You can calculate latency percentiles by service, endpoint, or day:

~~~json
{
  "size": 0,
  "aggs": {
    "by_service": {
      "terms": {
        "field": "service.keyword",
        "size": 20
      },
      "aggs": {
        "latency": {
          "percentiles": {
            "field": "responseTime",
            "percents": [50, 95, 99]
          }
        }
      }
    }
  }
}
~~~

Each service gets its own distribution. This helps pinpoint which services suffer from high tail latency.

A terms aggregation may not return all services if the bucket count exceeds size. If you need to list every group, consider a composite aggregation.

### 5.5. Percentile ranks

If you want to know which percentile 500 ms sits at, use `percentile_ranks`:

~~~json
{
  "size": 0,
  "aggs": {
    "latency_rank": {
      "percentile_ranks": {
        "field": "responseTime",
        "values": [100, 250, 500, 1000]
      }
    }
  }
}
~~~

The output indicates the percentage of observations at or below each threshold. For example, if the percentile rank of 500 ms is 92, roughly 92% of observations do not exceed 500 ms according to the estimate.

Use percentile ranks when the question starts with "what percentage of requests finish within 500 ms?" instead of "what is P95 in ms?".

## 6. Percentile algorithms and accuracy trade-offs

### 6.1. T-digest is the common default method

Elasticsearch uses T-digest by default for percentile aggregations. T-digest compresses a distribution into centroids, enabling approximate percentile calculation without retaining all sorted raw values.

Characteristics:

- Sketches from multiple shards can be merged.
- Uses far less memory than keeping all values.
- Suits large datasets and wide distributions.
- Can achieve good accuracy in the tails when appropriately configured.
- Results are estimates, not exact order statistics over all raw values.

### 6.2. compression controls T-digest

You can tune `compression`:

~~~json
{
  "percentiles": {
    "field": "responseTime",
    "percents": [50, 95, 99],
    "tdigest": {
      "compression": 200
    }
  }
}
~~~

Higher compression generally increases accuracy at the expense of higher memory usage and processing time. A common default is 100. Check the defaults and limits of your running Elasticsearch version.

Do not set maximum compression on every aggregation. When a query has many buckets, each bucket can hold its own T-digest state; total cost can grow substantially.

### 6.3. Compression is not an accuracy percentage

`compression: 200` does not mean 200% accurate or a 0.5% error bound. It is a parameter controlling the size/granularity of T-digest centroids, not a direct error-bound guarantee across all distributions.

Actual accuracy also depends on:

- Data distribution.
- Number of observations.
- Target percentile levels.
- Number of shards and merge behavior.
- Number of buckets and concurrent requests.
- Elasticsearch version and algorithm implementation.

Benchmark on production-like data rather than inferring error solely from the compression value.

### 6.4. T-digest and distributions with outliers

P99/P99.9 are sensitive to extreme values. T-digest is designed to allocate resolution non-uniformly across the distribution and typically allocates finer detail near the tails, yet results remain approximate.

If data shows abnormal outliers, inspect the data source, measurement units, and timeout recording. Latency values accidentally recorded in microseconds instead of milliseconds can render percentiles meaningless even though the aggregation executes properly.

## 7. HDR Histogram

### 7.1. Selecting the HDR method

Percentiles aggregations can use HDR Histogram instead of T-digest in supported Elasticsearch versions:

~~~json
{
  "percentiles": {
    "field": "responseTime",
    "percents": [50, 95, 99],
    "hdr": {
      "number_of_significant_value_digits": 3
    }
  }
}
~~~

HDR Histogram is designed to track numeric distributions with a fixed number of significant digits of precision. It fits latency or metrics with a reasonably well-defined value domain.

### 7.2. number_of_significant_value_digits

`number_of_significant_value_digits` controls how many significant digits the histogram maintains. Exact supported values and defaults depend on the Elasticsearch version; a common setting is 3 significant digits.

Increasing precision increases histogram memory. Memory usage also depends on the value range that must be represented, so huge outliers can force the structure to allocate more memory.

Do not increase significant digits if the extra precision makes no difference to business decisions.

### 7.3. How do T-digest and HDR differ?

| Criterion | T-digest | HDR Histogram |
|---|---|---|
| Representation | Centroids compressing the distribution | Histogram with precision-based buckets |
| Main parameter | compression | number_of_significant_value_digits |
| Memory | Depends on compression and bucket count | Depends on precision and value range |
| Characteristics | Flexible across wide distributions, mergeable sketches | Useful when value range and relative precision are known |
| Result | Approximate | Approximate |
| Selection | Benchmark against actual distribution | Benchmark against value range and precision needs |

Neither method is universally superior for every workload. Choose based on data, bucket count, shard count, latency, and real memory consumption.

### 7.4. Anomalous values and range

HDR must represent a numeric range. If data has huge outliers or a wildly varying range, memory footprint can differ greatly from expectations.

Clarify:

- Field unit (ms, µs, bytes, points).
- Reasonable min/max bounds.
- Whether outliers are valid data.
- Whether bad data should be clamped or rejected at the ingest pipeline.
- Required accuracy at each percentile.

Do not discard outliers merely to lighten aggregations if outliers are critical operational signals. Handle data quality at the data layer according to explicit rules.

## 8. Cardinality and percentiles in Spring Data Elasticsearch

### 8.1. Building NativeQuery with aggregations

Spring Data Elasticsearch supports aggregations via `NativeQuery` and the Elasticsearch Java API Client. Conceptual example with cardinality:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.range(r -> r
        .field("eventTime")
        .gte(JsonData.of("2026-01-01T00:00:00Z"))
    ))
    .withAggregation(
        "unique_users",
        Aggregation.of(a -> a.cardinality(c -> c
            .field("userId")
            .precisionThreshold(10000)
        ))
    )
    .build();

SearchHits<EventDocument> hits =
    operations.search(query, EventDocument.class);
~~~

Builder types and how range values are expressed can differ across Elasticsearch Java API Client versions. This snippet illustrates attaching an aggregation to a query rather than guaranteeing identical overload signatures across every version.

If you only need aggregations, you can set page size to 0 or configure the query not to return document hits, depending on your API version.

### 8.2. Adding percentile aggregations

For percentiles, builders can be constructed in a similar pattern:

~~~java
Aggregation latencyPercentiles = Aggregation.of(a -> a
    .percentiles(p -> p
        .field("responseTime")
        .percents(50.0, 95.0, 99.0)
        .tdigest(t -> t.compression(200.0))
    )
);
~~~

Exact method names/overloads depend on the Java API Client version. Some client versions express the percentile list or method configuration via different builder types. Use your IDE/API reference for your project's dependency to confirm.

Then attach the aggregation to `NativeQuery`:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("latency_percentiles", latencyPercentiles)
    .build();
~~~

### 8.3. Reading aggregations from SearchHits

`ElasticsearchOperations.search` returns `SearchHits<T>`. Aggregation metadata is held inside the response's aggregation container. Exact unwrapping depends on the Spring Data Elasticsearch version and client aggregation types.

In versions using the Elasticsearch Java API Client, you typically obtain `AggregationsContainer` from `SearchHits`, cast to the corresponding Elasticsearch implementation, and look up `Aggregate` by aggregation name. The result type is a tagged union; inspect the actual branch such as cardinality or percentiles before extracting values.

Do not cast an arbitrary aggregate to percentile/cardinality without verifying its type. A request can return multiple aggregations and nested buckets, so the mapper must know the exact declared names and structure.

### 8.4. Separating aggregation mappers from controllers

Create a mapper/service to convert aggregation results into application DTOs:

~~~java
public record UniqueUserMetric(
    long estimatedCount
) {
}

public record LatencyPercentileMetric(
    Map<Double, Double> values
) {
}
~~~

For cardinality, naming the field `estimatedCount` reminds API consumers that it is an approximation. For percentiles, preserve percentile-value pairs and explicit units.

Do not return raw client aggregation objects directly from controllers. Those structures are library-coupled and not stable API contracts.

### 8.5. Units of measurement must be explicit

If the `responseTime` field stores milliseconds, DTOs and dashboards must specify `ms`. If it stores microseconds, do not display it as milliseconds.

You can use a DTO:

~~~java
public record PercentileValue(
    double percentile,
    double value,
    String unit
) {
}
~~~

A numeric field does not carry its unit automatically. Units must be defined in the mapping, ingestion contract, or field name.

## 9. Nested aggregations and bucket counts

### 9.1. Cardinality across multiple buckets

Example cardinality by day and by event type:

~~~json
{
  "size": 0,
  "aggs": {
    "by_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day"
      },
      "aggs": {
        "by_event_type": {
          "terms": {
            "field": "eventType",
            "size": 10
          },
          "aggs": {
            "unique_users": {
              "cardinality": {
                "field": "userId",
                "precision_threshold": 3000
              }
            }
          }
        }
      }
    }
  }
}
~~~

Each child bucket maintains its own cardinality sketch. As day count, event type count, and threshold grow, aggregation memory can increase considerably.

### 9.2. Percentiles inside buckets

Percentiles per endpoint:

~~~json
{
  "size": 0,
  "aggs": {
    "by_endpoint": {
      "terms": {
        "field": "endpoint.keyword",
        "size": 50
      },
      "aggs": {
        "latency_percentiles": {
          "percentiles": {
            "field": "responseTime",
            "percents": [50, 95, 99]
          }
        }
      }
    }
  }
}
~~~

Each endpoint gets its own latency distribution. If endpoints have high cardinality, `terms.size: 50` returns only a configured subset of buckets, not every endpoint.

### 9.3. Bucket explosion

Nested aggregations multiply bucket counts across levels. For example, 365 days × 100 endpoints × 10 regions already creates huge bucket counts before even computing cardinality or percentiles inside.

You should:

- Limit terms size.
- Use filters to narrow the time range and data scope.
- Avoid unnecessary bucket nesting levels.
- Consider composite aggregations to paginate buckets.
- Measure memory/latency with realistic bucket counts.
- Monitor the cluster's `search.max_buckets` limit.

A query returning zero or few document hits can still generate vast numbers of aggregation buckets and consume significant resources.

## 10. Accuracy of percentile results

### 10.1. Percentiles are estimates

T-digest and HDR represent distributions via summary structures rather than sorting every raw value cluster-wide. Hence, percentile results can differ from exact percentiles calculated over the full raw value list.

The discrepancy depends on algorithm, settings, distribution, and how data is sharded. Do not treat a percentile output as an exact mathematical boundary when business logic makes threshold decisions right on the edge.

### 10.2. Sample size affects interpretation

If a bucket has only 10 requests, P99 carries little practical meaning: the 1% tail is smaller than a single observation. If a bucket has millions of requests, P99 is far more stable, though still an approximate aggregation output.

Dashboards should display observation counts alongside percentiles so viewers understand sample size. Very high percentiles can be hidden or flagged when sample size is too low.

### 10.3. Skewed distributions and outliers

Latency typically follows a right-skewed distribution: most requests are fast, while a few are very slow. Averages fail to capture the tail. P95/P99 are helpful, yet they remain sensitive to:

- Timeouts logged as fixed values.
- Retried requests counted multiple times.
- Inconsistent measurement units.
- Corrupted data or invalid outliers.
- Buckets with too few observations.

Before tuning compression, inspect data quality and metric instrumentation.

### 10.4. Do not sum or average bucket percentiles

Day 1's P95 plus Day 2's P95 does not produce the P95 across both days. Percentiles are not linearly additive.

Similarly, do not average each service's P95 to derive a system-wide P95. To get a global percentile, run the aggregation across the entire target dataset or use a distribution model that merges properly.

## 11. Choosing configurations by business requirements

### 11.1. Realtime dashboards

For continuously refreshing dashboards:

- Approximate cardinality is usually fine for estimating active users.
- Approximate percentiles usually fit latency monitoring.
- Keep threshold/compression moderate.
- Bound bucket counts and query duration.
- Accept a pre-evaluated error margin.

Dashboards prioritize fast responsiveness and stable trends over strictly exact numbers on every refresh.

### 11.2. Analytical reports

For periodic reports:

- You can raise precision threshold or compression if benchmarks justify it.
- Eliminate unnecessary buckets.
- Use fixed, closed time intervals.
- Record aggregation settings alongside result data.
- Compare against exact calculations on samples to measure error.

If reports must be reproducible, log the mapping version, query, aggregation configuration, and data window.

### 11.3. Reconciliation and billing

For workflows requiring exact counts:

- Do not rely on cardinality approximations for invoicing.
- Consider composite aggregations scanning all distinct keys.
- Or maintain distinct tables/stream state in an appropriate storage engine.
- Account for snapshots and late-arriving data.
- Cross-check figures using an independent reconciliation source.

When percentiles are used for SLAs or automated decisions, define acceptable tolerances and handling for values near thresholds.

## 12. Testing accuracy and performance

### 12.1. Creating datasets with known exact results

To evaluate cardinality, construct datasets with:

- Known document counts.
- Known distinct `userId` counts.
- Varying duplication ratios.
- Missing values.
- Small, medium, and high cardinalities.
- Multiple shards or indices if production is sharded.

Compute the exact distinct count externally or via bucket enumeration on the test dataset, then compare with the cardinality estimate.

### 12.2. Measuring cardinality error

A simple metric:

\[
relativeError = \frac{|estimate - exact|}{exact}
\]

Evaluate repeatedly across multiple distributions, not just a single dataset. If `exact` equals 0, compare absolute differences instead of relative error.

Experiment with different precision thresholds while recording:

- Error rate.
- Query latency.
- Heap/memory usage.
- Bucket count.
- Shard count.
- Concurrent request count.

### 12.3. Evaluating percentiles with reference calculations

On small datasets, you can fetch all numeric values, sort them, and compute percentiles using an explicit interpolation definition. Compare reference values against T-digest/HDR.

Note that libraries may use different interpolation conventions (nearest rank, linear interpolation, or other methods). Before concluding Elasticsearch is wrong, ensure both sides use the same percentile definition.

### 12.4. Benchmarking T-digest and HDR

Using the same dataset and percentile list:

1. Run T-digest at default compression.
2. Increase compression across several steps.
3. Run HDR with appropriate precision digits.
4. Compare deviations across P50/P95/P99/P99.9.
5. Record heap usage and latency.
6. Test bucket counts and shard counts close to production.
7. Pick the configuration meeting accuracy requirements at acceptable cost.

Do not benchmark solely with one standalone query on a tiny index. Real-world cost depends on bucket count, shards, and concurrency.

### 12.5. Testing with edge-case data

Include:

- Missing or null fields.
- Zero values.
- Negative values if the data domain allows them.
- Very large values.
- Data concentrated at a single value.
- Heavily skewed distributions.
- Empty buckets.
- Buckets with very few observations.
- Late-arriving documents or data mutating during reporting.

These cases uncover discrepancies caused by mapping, ingestion, and statistical interpretation.

## 13. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Cardinality is lower or higher than exact count | HLL++ is an estimation algorithm | Benchmark against exact samples and tune precision threshold |
| Raising precision threshold spikes memory | Many buckets/cardinality aggregations in one request | Reduce buckets, reduce aggregations, or lower threshold |
| Summing daily unique users gives wrong total | A single user appears across multiple days | Run cardinality over the full window or use exact distinct |
| Distinct count on text gives unexpected results | Using an analyzed text field tokenized into terms | Use a keyword subfield |
| Terms bucket count is lower than actual distinct values | Terms returns buckets capped by size/shard_size | Use composite to traverse all buckets |
| P99 fluctuates wildly | Small sample size or tail outliers | Show observation count, widen window, inspect data |
| P95 differs across reporting tools | Different percentile/interpolation definitions | Standardize reference calculation method |
| High compression slows queries | T-digest maintains finer centroid state | Lower compression or benchmark HDR |
| HDR consumes unexpected memory | Wide value range or high precision | Check units/outliers and significant digits config |
| System-wide percentile doesn't match | Averaging or summing percentiles from individual buckets | Run percentiles over the global dataset |
| Aggregation request is too heavy | Bucket explosion or too many metrics | Narrow filters, reduce buckets, monitor max_buckets |
| Spring Data fails to read aggregate | Client/version API differences or wrong type unwrapping | Check AggregationsContainer and actual Aggregate type |

## 14. Workflow for implementing aggregations in an application

A practical workflow:

1. Identify the statistical question: distinct count, percentile, or percentile rank.
2. Select a field with appropriate mapping and doc values.
3. Decide whether results can be approximate or must be exact.
4. Estimate cardinality or sample size within each bucket.
5. Choose precision threshold for cardinality.
6. Choose T-digest or HDR and configure precision for percentiles.
7. Bound bucket counts, shard scope, and time ranges.
8. Build aggregations using NativeQuery or the appropriate client API.
9. Read the aggregation container with proper type checks and map to DTOs with explicit units.
10. Benchmark error, memory, and latency on representative data.
11. Record settings alongside query/mapping versions.
12. Monitor error and resource cost as data or bucket counts grow.

## 15. Points to remember

- Cardinality counts unique values and is typically approximated via HyperLogLog++.
- `precision_threshold` tunes the accuracy-vs-memory trade-off; the common default is 3,000 and the maximum effective value is 40,000.
- The threshold is an accuracy target, not an exactness guarantee.
- Per-bucket cardinalities cannot be summed for a global distinct count if values repeat across buckets.
- Composite aggregations can paginate all distinct keys when exact counting is required, though cost scales with bucket count.
- Percentiles return values at percentage thresholds; percentile ranks return the positions of queried values.
- T-digest uses `compression` to tune granularity in exchange for memory and processing time.
- HDR uses `number_of_significant_value_digits`; footprint depends on precision and value range.
- Percentiles are approximations sensitive to sample size, outliers, units, and data distribution.
- Do not sum or average bucket percentiles to infer a global percentile.
- Spring Data Elasticsearch stores aggregations in a response container; unwrap the right aggregation type for your client version.
- Bound bucket counts and nested aggregation levels to prevent bucket explosion.
- For reconciliation or billing, use exact methods rather than unverified approximations.

Cardinality and percentiles summarize large datasets at controllable cost, provided you understand the algorithms' limits. Choosing the right fields, buckets, precision, and reference methods ensures dashboards and reports yield useful metrics without trading away excessive memory or latency.
