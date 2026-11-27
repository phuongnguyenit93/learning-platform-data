# Measuring Performance on Production-Like Data and Queries

Measuring Elasticsearch performance on a few hundred sample documents often yields results drastically different from a real system. As data scales up, value distributions shift, shards experience uneven load, caches behave differently, aggregations build far more buckets, and queries contend for resources with writes. A query running fast on a laptop or tiny test environment does not prove the system will hold up under hundreds of users, millions of documents, and continuous updates.

To evaluate accurately, build a benchmark close to the production workload: data with realistic scale and distributions, matching mappings, realistic read/write ratios, representative queries, realistic concurrency, and comparable infrastructure. Measure both Elasticsearch and the Spring Data application to tell whether latency sits in the query, network, serialization, entity mapping, or downstream processing.

A useful benchmark must answer concrete questions:

- How many requests or documents per second can the system sustain?
- What are p50, p95, and p99 latencies at projected load?
- As concurrency rises, how far does throughput scale before saturating?
- Which queries drive high tail latency or heavy CPU/memory usage?
- How do error rates, timeouts, 429s, and queue backlogs behave?
- Do searches remain responsive while bulk indexing runs concurrently?
- Are results reproducible after changing mappings, shards, queries, or code?

## 1. Why is production-like data necessary?

A small index often fits entirely inside the filesystem cache, has few segments, few shards, and few distinct values. Those conditions make queries appear substantially faster than in production.

For example, a terms aggregation on `category` might produce only 8 buckets in a sample dataset. In production, that field might contain hundreds of thousands of distinct values. Similarly, a tenant filter might match 5 documents in tests yet millions in the largest tenant.

Common discrepancies that skew benchmarks:

- **Document count:** small sets miss search, segment, and merge costs at scale.
- **Data distribution:** uniform values in tests vs. heavy skew in production.
- **Cardinality:** fields with few values in tests vs. many unique values in reality.
- **Document size:** sample payloads smaller than real data or missing nested arrays.
- **Fresh/stale data churn:** production experiences frequent updates, deletes, and expirations.
- **Shard distribution:** specific tenants or routing keys create hotspots.
- **Query mix:** tests run a single match query while production mixes filters, sorts, aggregations, nested queries, and pagination.
- **Concurrency:** a single sequential request hides CPU, disk, thread pool, and connection pool contention.
- **Caches:** repeating a single query measures cache hits only.
- **Refreshes and merges:** continuously written data behaves differently from static indexes.

A good benchmark does not necessarily need an exact copy of production data. What matters is preserving characteristics that drive processing cost: distribution, cardinality, sizes, skew, churn rate, and query shapes.

## 2. Defining targets and SLOs before measuring

Before generating data or writing scripts, define what counts as passing. Without targets, benchmarks produce numbers without informing decisions.

Example goals for a search API:

| Metric | Illustrative target |
|---|---:|
| Throughput | 300 requests/second |
| Search latency p50 | Under 80 ms |
| Search latency p95 | Under 250 ms |
| Search latency p99 | Under 600 ms |
| Error rate | Under 0.1% |
| Indexing lag | Under 5 seconds |
| 429/rejected execution | Not continuously rising at target load |

These are examples only. Actual SLOs must reflect product requirements, deployment region, network, response sizes, and infrastructure budget.

Separate targets by workload type:

- Interactive search needs low latency.
- Aggregation dashboards may tolerate higher latency.
- Bulk imports prioritize throughput and completion time.
- Event-driven updates bound indexing lag.
- Large exports prioritize steady throughput and backpressure.

Do not collapse all requests into one average latency number. Averages mask slow query groups and unacceptable tail latency.

## 3. Creating a representative dataset

Benchmark datasets should reflect real structure and distributions. Use anonymized production data, synthetic data, or a combination of both.

Example product document:

    {
      "productId": "p-100001",
      "tenantId": "tenant-42",
      "name": "Mechanical Keyboard K8",
      "description": "Wireless mechanical keyboard",
      "category": "keyboard",
      "brand": "Keychron",
      "price": 120.0,
      "stock": 42,
      "status": "ACTIVE",
      "createdAt": "2026-10-20T10:00:00Z",
      "updatedAt": "2026-11-10T08:30:00Z",
      "tags": ["wireless", "mechanical"],
      "offers": [
        {
          "sellerId": "seller-10",
          "price": 120.0,
          "available": true
        }
      ]
    }

Datasets should not include only flat simple fields. If production uses nested objects, arrays, text analyzers, date ranges, geo fields, or dynamic attributes, include those structures in the benchmark.

### Document count

Pick a scale large enough to reveal operational behavior:

- Current projected document count.
- Projected document count in 6 or 12 months.
- Rapid-growth scenario.
- Index store size after ingestion and merges.

You can benchmark across multiple scales, e.g., 1 million, 10 million, and 50 million documents, if infrastructure permits. The goal is understanding growth curves, not measuring a single point.

### Document size

Measure average and percentile sizes of real documents. Do not give every document the exact same size.

A realistic dataset might include:

- Small documents with only a few fields.
- Medium documents with descriptions and metadata.
- Large documents containing arrays or nested objects.
- A small percentage of unusually large yet valid documents.

Source size affects network transfer, storage, mapping heap, and serialization time.

## 4. Data distribution matters more than uniform randomness

Uniformly random data usually yields overly optimistic benchmarks. Production typically exhibits skew:

- A few categories hold most products.
- Some tenants hold far more data than others.
- A handful of keywords are searched heavily.
- Many documents share identical statuses.
- Rare values appear in certain filters.
- Timestamps cluster in the most recent days.

Example tenant distribution:

| Tenant group | Share of tenants | Share of documents |
|---|---:|---:|
| Small | 80% | 20% |
| Medium | 15% | 30% |
| Large | 4% | 25% |
| Very large | 1% | 25% |

This distribution creates a few tenants holding disproportionately large datasets. Benchmarking with equal-sized tenants hides hotspot and tail-latency risks for large tenants.

Generate data following histograms or distributions extracted from anonymized production metrics. When real distributions are unavailable, model skew from domain knowledge and document assumptions.

## 5. Field cardinality

Cardinality is the number of distinct values in a field. It impacts terms aggregations, memory, doc values, sorting, and compression.

Examples:

| Field | Typical cardinality |
|---|---|
| status | Very low |
| category | Low to medium |
| brand | Medium |
| tenantId | Potentially high |
| productId | Near document count |
| email | Very high |
| exact timestamp | Potentially very high |

Benchmarking an aggregation by `tenantId` with only 10 tenants does not reflect costs with 100,000 tenants.

Generate production-like cardinality for every field used in:

- Terms aggregations.
- Cardinality aggregations.
- Sorting.
- Terms queries.
- Composite aggregations.
- Grouping or dashboards.

In particular, aggregations on high-cardinality fields can build large bucket counts and consume heap. Measure response size, bucket count, and latency together.

## 6. Time distribution and fresh data

For systems storing events, orders, or history, timestamp distributions affect range queries and index lifecycles.

A production-like benchmark should model:

- Documents concentrated in recent hours or days.
- Large volumes of historical data.
- Seasonal or hourly activity spikes for certain tenants.
- Late-arriving events.
- Updates to older documents.
- Deletes or retention cleanups.

If every document has the same timestamp, weekly/monthly range queries will not mirror reality. If timestamps are spread uniformly, benchmarks can miss hotspots on recent time ranges.

For date histograms, include both dense intervals and sparse or empty intervals. This exercises empty buckets, extended bounds, and pipeline aggregations.

## 7. Keeping mappings identical to production

Benchmarking with simple dynamic mappings and later switching to production mappings with analyzers, nested fields, doc values, and normalizers makes comparisons invalid.

Mappings must preserve:

- Exact field types.
- Text analyzers and `keyword` subfields.
- Normalizers.
- `nested`/`object` distinctions.
- `index` and `doc_values` settings.
- Dynamic templates.
- Custom similarities if used.
- Runtime fields if used by the workload.
- Source settings and stored fields.

Example:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword"
              }
            }
          },
          "category": {
            "type": "keyword"
          },
          "tenantId": {
            "type": "keyword"
          },
          "price": {
            "type": "scaled_float",
            "scaling_factor": 100
          },
          "createdAt": {
            "type": "date"
          },
          "offers": {
            "type": "nested",
            "properties": {
              "sellerId": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "available": {
                "type": "boolean"
              }
            }
          }
        }
      }
    }

This mapping is an example. Benchmarks must use real mappings or explicitly documented variants. Do not change field types between two runs and attribute the difference to a query change.

## 8. Making datasets reproducible

Datasets should be generated with a fixed seed or loaded from a versioned snapshot. If every run generates different data, benchmark results can fluctuate simply because data distribution changed.

Record:

- Generator random seed.
- Generator version.
- Document count.
- Tenant/category/status distributions.
- Source sizes.
- Mapping and settings.
- Elasticsearch version.
- Spring Data Elasticsearch and Java API Client versions.
- Snapshot creation date.

If data originates from production, anonymize it and strip personal information or secrets before moving it to benchmark environments.

Never leave real sensitive IDs or payloads in benchmark scripts, logs, or reports.

### Verifying the dataset before benchmarking

Before starting measurements, confirm:

- Document count matches expectations.
- Unique tenant/category/brand counts are realistic.
- Field distributions align with the model.
- Document sizes show expected variety.
- Mappings match.
- No bulk errors were silently ignored.
- Indexes are refreshed when scenarios require search visibility.

Use count queries, cardinality aggregations, and sample statistics to verify. Never start benchmarking without knowing whether the dataset ingested cleanly.

## 9. Reproducing the query workload

Workloads should reflect realistic query proportions instead of running one query. A search application might have:

| Request type | Example share |
|---|---:|
| Match/full-text search | 35% |
| Filter by tenant/status/category | 25% |
| Sort and pagination | 15% |
| Aggregation dashboard | 10% |
| Nested query | 5% |
| Get by ID | 5% |
| Bulk/index/update | 5% |

These percentages are illustrative. Use anonymized access logs, APM, or API metrics to establish your actual query mix.

A production-like workload should include:

- Frequent queries.
- Rare but expensive queries.
- Zero-result queries.
- Queries matching vast hit sets.
- Queries on small and large tenants.
- Highly selective and poorly selective filters.
- Low- and high-cardinality aggregations.
- First-page and deep pagination.
- Reads while writes are active.

Do not benchmark only average queries. Rare queries consuming heavy CPU or causing tail latency can be the primary reason SLOs fail.

## 10. Using production-like query parameters

A single query template can run fast with one parameter value and slow with another. For example, filtering `status=ACTIVE` might match 90% of documents, whereas `status=ARCHIVED` matches 1%.

Build a representative parameter set:

- Popular values.
- Rare values.
- Largest tenant.
- Small tenants.
- Short time windows.
- Long time windows.
- Short and long keywords.
- Common and rare keywords.
- Cases yielding zero results.

Repeating the exact same keyword thousands of times biases benchmarks toward cache hits. If production queries vary broadly, benchmark parameters must share comparable diversity.

## 11. Example query mix

### Full-text search

    GET products/_search
    {
      "query": {
        "match": {
          "name": "mechanical keyboard"
        }
      },
      "size": 20
    }

### Tenant and status filter

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-42"
              }
            },
            {
              "term": {
                "status": "ACTIVE"
              }
            },
            {
              "range": {
                "price": {
                  "gte": 50,
                  "lte": 300
                }
              }
            }
          ]
        }
      },
      "sort": [
        {
          "createdAt": {
            "order": "desc"
          }
        }
      ],
      "size": 20
    }

### Aggregation by category

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category",
            "size": 100
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

### Nested query

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "filter": [
                {
                  "term": {
                    "offers.available": true
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }

The query mix must preserve both structure and relative frequency. A heavy query making up only 1% of traffic can still dominate CPU if it creates huge buckets or scans vast document sets.

## 12. Simulating writes alongside searches

Production rarely runs searches on a static index alone. It receives new documents, status updates, and deletions while serving queries.

Benchmarks should cover these scenarios:

- Search-only to measure read limits.
- Index-only to measure ingest throughput.
- Concurrent search and indexing.
- Updates/deletes concurrent with searches.
- Large bulk imports while interactive APIs run.
- Normal refresh interval and delayed refresh scenarios.

Concurrent writes trigger new segments, merges, indexing pressure, and disk contention. Search-only latency numbers miss these effects.

If production runs nightly bulk imports and daytime search traffic, benchmark both phases individually as well as overlapping scenarios during incidents or backfills.

## 13. Load models: closed-loop vs. open-loop

Two common load generation models behave differently:

- **Closed-loop:** each virtual user sends the next request only after the previous one completes. When the server slows down, the request send rate automatically drops.
- **Open-loop:** requests arrive at a scheduled rate independent of response times. When the server slows down, queues and latencies build up.

Closed-loop generators are easy to configure yet can mask overload because clients throttle themselves when the server stalls. Open-loop fits verifying whether a system handles a target arrival rate, though generators need queue limits to avoid exceeding their own capacity.

Pick the model matching actual client behavior. If production traffic arrives at a steady rate, test open-loop. If a fixed worker pool waits on each call before issuing the next, closed-loop may fit better.

## 14. Test types to execute

A benchmark plan should not consist of a single 5-minute run. Split into distinct test types:

| Test type | Objective |
|---|---|
| Baseline | Measure the system at low load for a reference point |
| Load test | Measure at projected load for a sustained window |
| Stress test | Push load past target to find the saturation point |
| Spike test | Inject sudden bursts to evaluate burst absorption |
| Soak test | Run long enough to expose memory leaks, merge backlogs, and degradation |
| Recovery test | Observe recovery after overload or node restarts |
| Mixed workload | Measure concurrent reads/writes/aggregations |
| Scale test | Compare performance when changing nodes, shards, or resources |

Document the objective, warm-up time, measurement window, concurrency, arrival rate, and stop criteria for each test.

## 15. Warm-up and cold-cache testing

Initial runs can be slower due to:

- Cold JVM startup or unoptimized JIT compilation.
- Cold filesystem page cache.
- Empty query cache or request cache.
- Connection pools opening fresh connections.
- Elasticsearch opening segments or loading mappings.

Measuring only the first run underestimates steady-state performance. Measuring only after running the same query thousands of times overestimates performance for diverse queries.

Separate:

- Cold-start measurements.
- Warm-up phase.
- Steady-state measurements.
- Cache-hit workloads.
- Cache-miss or diverse-query workloads.

Label every result with its cache state. Never compare a cold-cache run to a warm-cache run and claim code changes sped things up.

## 16. How do caches affect benchmark results?

Elasticsearch and the OS contain multiple caching layers:

- Filesystem page cache.
- Node query cache.
- Shard request cache.
- Application or reverse-proxy caches if present.
- Connection pool and DNS/TLS session reuse.

Not every query gets cached. Cache behavior depends on query types, segments, requests, and index settings.

Repeating the exact same aggregation on a static index lets the shard request cache accelerate subsequent runs. Varying queries or actively updating indexes yield lower hit ratios.

To measure realistic workloads:

- Use a parameter distribution matching production.
- Record cache hit/miss metrics where available.
- Avoid arbitrarily purging caches between every request.
- Run both warm and cold scenarios.
- Keep index state comparable across runs.

Do not disable all caches just to produce a number. Measure cache behavior under the workload users actually generate.

## 17. Refreshes and merges during benchmarks

A static index after refreshes and merges behave differently from an actively ingested index.

Refreshes make new documents searchable. Newly created segments start smaller and merge later. Merges consume CPU and I/O, affecting search and indexing latency.

Therefore, benchmark:

- Search on a steady static index.
- Search while indexing continuously.
- Search during bulk imports.
- Search while merge backlogs grow.
- Alternative refresh policies if used by the application.

Indexing everything, refreshing, force merging, and only then running searches may not represent continuously written production indexes.

Force merging can fit read-mostly indexes, but should not precede every benchmark if production does not run it. It changes segment layouts and cache behavior.

## 18. Measuring latency properly

Measure latency across multiple layers:

- Client sends request until response arrives.
- Spring service processes request.
- Elasticsearch client performs network call.
- Elasticsearch server executes query.
- Mapping source to entities.
- Mapping entities to DTOs.
- HTTP response serialization.

A timer around `operations.search` often captures more than server query execution because it can span network and conversion depending on the API. `took` in Elasticsearch responses excludes much of the end-to-end user experience.

Collect at least:

- p50: median latency.
- p90 or p95: slower request bands.
- p99: tail latency.
- Maximum: helpful for diagnostics, though sensitive to outliers.
- Error rate and timeout rate.

Never report averages alone. A system averaging 50 ms with a 5-second p99 still gives a poor experience to affected users.

## 19. Throughput and latency must be viewed together

Throughput is completed operations per unit of time. Adding workers raises throughput initially, until saturation sets in:

- CPU hits limits.
- Disk queues grow.
- Thread pool queues fill.
- GC pauses lengthen.
- Requests are rejected or time out.
- p95/p99 climbs rapidly.

Example:

| Concurrency | Throughput | p95 latency | Error rate |
|---:|---:|---:|---:|
| 10 | 120 req/s | 90 ms | 0% |
| 25 | 260 req/s | 140 ms | 0% |
| 50 | 340 req/s | 280 ms | 0.02% |
| 100 | 355 req/s | 900 ms | 1.2% |
| 150 | 350 req/s | 1.8 s | 4.5% |

This example shows throughput barely climbing past concurrency 50 while latency and errors surge. Adding more concurrency does not make the system faster.

The objective is not maximum throughput at all costs. Find the operating point that satisfies SLOs with enough headroom for bursts and variance.

## 20. Measuring p95 and p99 accurately

Percentiles require sufficient sample counts over a meaningful window. A run of a few dozen requests cannot yield trustworthy p99 numbers.

Practices:

- Collect enough requests in each scenario.
- Split percentiles by query type.
- Do not lump lightweight and heavyweight queries into a single histogram if mix varies.
- Record the measurement window.
- Use proper histograms (e.g., HdrHistogram) to merge results across multiple instances.
- Never average percentiles calculated independently on different machines.

When running multiple load generators, aggregate percentiles from raw samples or mergeable histograms. Do not compute the arithmetic mean of per-machine p99s.

## 21. Measuring errors and timeouts

Low latency means nothing if requests are dropped or timing out. Track:

- HTTP 4xx/5xx.
- Item errors inside Elasticsearch Bulk responses.
- 429s and rejected executions.
- Connection timeouts.
- Socket timeouts.
- Circuit breaker trips.
- Retry counts.
- Cancellations.
- Dropped iterations in the load generator.

Load testing tools can fall behind target rates if the generator runs out of CPU or connections. If the generator saturates, measured throughput no longer reflects Elasticsearch capacity.

Monitor CPU, memory, and network on both the load generator and the cluster.

## 22. Measuring Elasticsearch resources

Cluster metrics to track:

| Group | Example metrics | What to check |
|---|---|---|
| CPU | Node CPU, process CPU | Are queries, merges, or indexing saturating CPU? |
| Heap | Heap used, old generation | Memory pressure and GC |
| GC | Pause time, collection count | Is tail latency impacted? |
| Disk | Read/write throughput, latency, queues | Is storage the bottleneck? |
| Network | Bytes, packets, retransmissions | Is data transfer or networking congested? |
| Thread pools | Active, queued, rejected | Are requests waiting or getting rejected? |
| Indexing pressure | Coordinating/primary/replica bytes | Is ingest outpacing capacity? |
| Segments | Segment count, memory | Segment fragmentation and merges |
| Merges | Merge time, throttling | Are merges competing for resources? |
| Shards | Shard size, distribution | Oversized shards or skewed load? |

Exact metric names and endpoints depend on Elasticsearch version. Use Stack Monitoring, node stats, index stats, cat APIs, or your deployed metrics stack.

## 23. Measuring resources in the Spring application

Benchmarks measuring only Elasticsearch miss application-tier costs:

- Query builders.
- JSON serialization.
- HTTP connection pools.
- TLS handshakes if connections are not reused.
- Mapping source to entities.
- Mapping entities to DTOs.
- Validation and business logic.
- Response JSON serialization.
- Thread scheduling or reactive operator overhead.

Use Micrometer or APM to track:

- Search requests per endpoint.
- Duration of `operations.search`.
- Bulk request durations.
- Error counts by type.
- Active/pending connection pool counts.
- JVM heap, allocation, and GC.
- CPU and thread utilization.
- Time spent in DTO mapping and serialization if needed.

Never place high-cardinality raw search text, emails, tenant IDs, or document IDs into metric tags. Use low-cardinality tags such as operation, query family, index alias, and status class.

## 24. Instrumentation around ElasticsearchOperations

Measure service-level timing using Micrometer:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;
        private final MeterRegistry registry;

        public ProductSearchService(
                ElasticsearchOperations operations,
                MeterRegistry registry) {
            this.operations = operations;
            this.registry = registry;
        }

        public SearchHits<Product> search(Query query) {
            return Timer.builder("product.search.duration")
                .tag("operation", "search")
                .register(registry)
                .record(() ->
                    operations.search(query, Product.class)
                );
        }
    }

This measures synchronous duration around `operations.search`. The timer reflects total service-call time, not solely server-side query processing.

For reactive APIs, never time `Mono` construction because publishers are lazy. Use `Timer.Sample` or operator instrumentation spanning subscription through completion/error:

    Mono<SearchHits<Product>> result =
        reactiveOperations.search(query, Product.class)
            .name("product.search")
            .metrics();

Exact metric naming, registry integration, and Reactor instrumentation depend on dependencies. If using Micrometer Observation or tracing, prefer the unified mechanism configured across the application.

Never call `block()` just to wrap with `Timer.record` in reactive flows.

## 25. Measuring server-side and application-side time separately

A request might report:

    Application latency: 180 ms
    Elasticsearch took: 45 ms

The gap can come from networking, queues, connection acquisition, source transfer, entity mapping, or service logic. You cannot conclude from those two numbers alone that the difference is purely serialization.

Measure separately:

- Connection wait time.
- Request send/receive time.
- Elasticsearch `took`.
- Entity mapping.
- Business processing.
- Response serialization.

Without fine-grained timers, add timing at key boundaries and use tracing to identify which spans dominate duration.

Do not optimize Query DSL if most latency comes from application mapping or network. Conversely, if Elasticsearch `took` is high, focus on queries, mappings, shards, and cluster resources.

## 26. Query profiling

The Elasticsearch Profile API exposes detailed execution breakdowns for queries and aggregations:

    GET products/_search
    {
      "profile": true,
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "tenantId": "tenant-42"
              }
            },
            {
              "range": {
                "price": {
                  "gte": 50,
                  "lte": 300
                }
              }
            }
          ]
        }
      }
    }

Profile output helps identify expensive query components. However, profiling adds overhead and alters timing relative to normal requests.

Use the Profile API to diagnose specific queries, not as a production latency benchmark. After optimizing, re-benchmark with normal unprofiled requests.

## 27. Explain and slow logs

Explain shows why a document matched and how its score was computed. It helps with relevance debugging, not throughput benchmarking.

Slow logs record queries or indexing operations exceeding configured duration thresholds. They catch slow requests under real load.

Practical usage:

1. Set reasonable slow-log thresholds per index and workload.
2. Collect logs over a window of realistic load.
3. Group entries by query shape or endpoint.
4. Inspect Query DSL and shard behavior.
5. Use the Profile API for deep dives on selected queries.
6. Lower verbosity or tighten thresholds when unneeded to avoid log overhead.

Slow logs do not replace latency histograms. They capture only requests crossing configured thresholds.

## 28. Checking shard distribution

An index with too many small shards or a few oversized shards adds overhead and imbalance.

Benchmarks should record:

- Primary and replica shard counts.
- Size of each shard.
- Document count per shard.
- Routing key and tenant distribution.
- Shards queried per request.
- Active shard relocations/recoveries during measurement.

If every query touches all shards, coordinating node and network costs climb. If custom routing packs a huge tenant onto one shard, that shard can become a hotspot.

Do not choose shard count from total storage alone. Measure shard sizes, ingest throughput, query fan-out, and cluster scalability.

## 29. Checking thread pools and queues

When Elasticsearch receives requests faster than it processes them, queues grow. Once queues fill, requests are rejected.

Monitor:

- Active threads.
- Queue depth.
- Rejected count.
- Queue wait time.
- Concurrent running requests.

Thread pool names and stats endpoints vary by version. Do not automatically raise queue sizes upon seeing rejections. Huge queues often turn fast failures into long latencies and higher memory consumption.

Find the underlying bottleneck first: CPU, disk, network, shard imbalance, bulk size, or heavy queries. Backpressure and concurrency tuning are usually more effective than enlarging queues.

## 30. Benchmarking bulk indexing

To measure ingestion, hold constant:

- Batch size by document count and bytes.
- Worker count/concurrency.
- Refresh policy.
- Replica count and index settings.
- Mapping and ingest pipelines.
- Source payload sizes.
- Routing distribution.
- Shard count.

A run summary should record:

    Documents attempted: 5,000,000
    Documents indexed:   4,998,700
    Item failures:       1,300
    Duration:            900 seconds
    Throughput:          calculated from successful items
    p95 bulk latency:    measured per request

Compute throughput from successfully indexed items, not attempted items. Track item failures, retries, and DLQs separately.

Do not use `IMMEDIATE` refresh after each batch unless production does the same. For large imports, measure realistic policies like `NONE` followed by a final refresh.

## 31. Bulk batch size and concurrency

Too-small batches incur heavy request overhead. Too-large batches can:

- Raise memory on the application and coordinating node.
- Increase per-request latency.
- Make retries costly.
- Trigger indexing pressure.
- Exceed HTTP request limits.

Too-low concurrency underutilizes resources; too-high concurrency causes queues, rejections, and tail latency.

Benchmark matrix:

| Batch size | Worker count | Goal |
|---:|---:|---|
| 250 docs | 1 | Small baseline |
| 500 docs | 2 | Test increased parallelism |
| 1,000 docs | 4 | Test throughput |
| 2,000 docs | 4 | Test larger payload impact |
| 1,000 docs | 8 | Test higher concurrency |

This is an illustrative matrix. Vary one parameter at a time to isolate causality; then rerun the combined workload to validate.

Monitor bytes/request, latency, 429s, heap, disk, and merges. Never pick the largest batch solely because it yielded high throughput in a brief run.

## 32. Benchmarking pagination

First-page pagination and deep pagination differ in cost. `from/size` grows more expensive as offset climbs because Elasticsearch must collect and discard earlier hits.

Benchmark across depths:

- First page.
- Page 5 or 10.
- Deep offset near real limits.
- PIT + `search_after`.
- Results sorted by `keyword`/`date` fields.
- Results with stable tie-breakers.

If production uses `search_after`, benchmark with the exact sort and cursor. If production uses `from/size`, do not substitute `search_after` in the benchmark and claim the current system meets SLOs.

Measure both per-page latency and full-export completion time. For cursor pagination, measure PIT open/close overhead and long-lived context retention.

## 33. Benchmarking aggregations

Aggregation cost depends on document count, cardinality, bucket count, and nesting depth.

Measure:

- Terms aggregations on low-cardinality fields.
- Terms aggregations on high-cardinality fields.
- Composite aggregations across multiple pages.
- Nested aggregations.
- Pipeline aggregations.
- Aggregations paired with query filters.
- Aggregations over wide time windows.

Track:

- Query latency.
- Bucket counts.
- Response size.
- Heap pressure.
- Circuit breaker events.
- Shards involved.

Do not benchmark only a 5-bucket aggregation. If real dashboards group by tenant or product ID, simulate real cardinality.

## 34. Benchmarking searches with nested and parent-child

If the data model uses `nested` or parent-child, benchmarks must mirror production child-count distributions per parent.

For `nested`:

- Measure average and p95 nested objects per document.
- Include a realistic share of documents with many nested objects.
- Benchmark `nested` queries, `nested` aggregations, `inner_hits`, and nested sorts.
- Measure parent-document update cost.

For parent-child:

- Measure average and p99 children per parent.
- Simulate realistic routing.
- Benchmark `has_child` and `has_parent`.
- Check for shard hotspots.
- Measure child index/update costs.

Do not compare `nested` and parent-child on different datasets. Keep business logic, query semantics, and document counts equivalent for meaningful comparisons.

## 35. Load generation tools

Commonly used tools:

| Tool | Best suited for |
|---|---|
| Elasticsearch Rally | Reproducible Elasticsearch benchmarks, tracks, and workloads |
| k6 | HTTP API load testing and arrival-rate models |
| Gatling | Scripted HTTP load testing with virtual users |
| JMeter | HTTP/API scenarios and load integration testing |
| Locust | Python-scripted load generation and custom user behavior |
| Internal tools | Custom workloads, event streams, or batch jobs |

Elasticsearch Rally is well suited for benchmarking the engine, indexes, and queries directly. k6/Gatling/JMeter fit measuring the full Spring Boot API from the client's perspective.

Never infer application end-to-end latency solely from direct Elasticsearch benchmarks. Nor should you rely solely on HTTP load tests when trying to isolate engine bottlenecks.

## 36. Elasticsearch Rally

Rally is a dedicated benchmarking tool for Elasticsearch. It supports tracks, corpora, challenges, and workloads to measure indexing and search performance.

A Rally benchmark should pin:

- Elasticsearch version.
- Track/corpus version.
- Cluster topology.
- Node hardware.
- JVM settings.
- Challenge.
- Client settings.
- Run duration.

If using a custom track, store the track definition alongside the repository or artifacts for repeatability. Never alter corpus or query mix between comparisons without recording it.

Rally measures Elasticsearch at the cluster/client benchmark layer. It does not measure Spring Data conversion or business logic.

## 37. k6 for Spring Boot APIs

A k6 script can simulate search requests:

    import http from 'k6/http';
    import { check, sleep } from 'k6';

    export const options = {
      scenarios: {
        search: {
          executor: 'constant-arrival-rate',
          rate: 100,
          timeUnit: '1s',
          duration: '5m',
          preAllocatedVUs: 50,
          maxVUs: 200
        }
      }
    };

    export default function () {
      const response = http.get(
        'http://localhost:8080/products/search?q=keyboard'
      );

      check(response, {
        'status is 200': (r) => r.status === 200
      });
    }

This example sends a single static query, so it does not yet represent a real query mix. In real benchmarks, sample parameters from a realistic distribution, preserve query family ratios, and avoid repeating a single keyword.

Constant arrival rate tests the system at a fixed request rate. Monitor dropped iterations and load generator resources to verify the generator keeps up with target load.

## 38. Benchmarking through Spring Data vs. directly against Elasticsearch

Run measurements at both layers:

### Direct Elasticsearch benchmarking

Goals:

- Measure Query DSL.
- Measure indexing.
- Measure shards and cluster behavior.
- Measure aggregations.
- Isolate server-side bottlenecks.

### Spring Boot/Spring Data benchmarking

Goals:

- Measure API latency.
- Measure conversion and mapping.
- Measure connection pools.
- Measure DTOs and serialization.
- Measure auth, validation, and business logic.
- Measure real request concurrency.

If direct Elasticsearch is fast while the API is slow, investigate the application path. If both are slow, inspect queries, cluster health, and data layout first.

## 39. Controlling the benchmark environment

For meaningful comparisons, record:

- CPU model and core counts.
- RAM and heap size.
- Disk type, IOPS, and filesystem.
- Network bandwidth and latency.
- Elasticsearch node count.
- Node roles.
- Primary/replica shard counts.
- Elasticsearch version.
- JVM version and flags.
- Spring Boot/Spring Data/client versions.
- Container CPU/memory limits.
- TLS/proxy/load balancer setup.
- Refresh interval and index settings.

Never compare results across differing hardware or settings and attribute the difference to a query change.

If benchmarking on Kubernetes, record requests/limits, node placement, storage classes, pod restarts, and CPU throttling.

## 40. Stabilizing cluster state

Before every run:

1. Verify cluster health.
2. Check shard allocation and relocations.
3. Confirm no unexpected snapshots, reindexes, or background jobs are running.
4. Verify index settings and mappings.
5. Check disk watermarks.
6. Check baseline heap and GC.
7. Confirm the dataset finished ingesting completely.
8. Record cache/refresh state.

If a node is restarting or shards are relocating, results will not represent steady state.

The cluster does not need to be completely idle if your goal is measuring production mixed workloads, yet background activity must be recorded and reproducible.

## 41. Change one variable at a time

When tuning, vary one factor per experiment:

- Query DSL.
- Mapping/analyzer.
- Number of shards.
- Replica count.
- Refresh interval.
- Bulk batch size.
- Concurrency.
- Source filtering.
- DTO conversion.
- Connection pool.

Changing mappings, queries, shards, and heap simultaneously makes it impossible to tell what caused the outcome.

Experiment loop:

    Baseline
       |
       v
    Change one factor
       |
       v
    Run same dataset/workload
       |
       v
    Compare latency/throughput/errors/resources
       |
       v
    Keep or roll back change

After finding individual improvements, rerun the mixed workload to verify they do not interact negatively when combined.

## 42. Repeat benchmarks and report variance

A single run can be skewed by background tasks, caches, GC, or network blips. Run multiple iterations under equivalent conditions.

Report:

- Number of iterations.
- Warm-up duration.
- Measurement duration.
- Median or range across runs.
- Per-run p50/p95/p99.
- Error rate.
- Cluster state.
- Dataset/version.

If results swing wildly across runs, investigate why before tuning around a single number.

Do not cherry-pick the fastest run as the headline result. Report stable statistics and variance.

## 43. Soak testing and memory pressure

A system can run smoothly for 5 minutes yet degrade after hours due to:

- Growing heap.
- Lengthening GC pauses.
- Segment merge backlogs.
- Accumulating thread pool queues.
- Connection leaks.
- Unreleased reactive subscriptions.
- Long-lived PIT/scroll contexts.
- Growing DLQ/retry backlogs.

Soak tests sustain steady load for extended durations while tracking trends. Do not check only final latency; inspect heap, disk, queues, and resource utilization over time.

If long benchmarks show rising errors, investigate memory leaks and resource lifecycles before scaling up node sizes.

## 44. Spike testing and bursts

Production sees traffic spikes from campaigns, batch jobs, event replays, or client retries. Spike tests apply sudden load surges to measure:

- Time to absorb the burst.
- Magnitude of p95/p99 spikes.
- Queue growth.
- 429s/rejections.
- Recovery time after the burst ends.
- Impact on search during bulk imports.

A healthy system does not have to avoid rejections entirely. What matters is controlled backpressure, retries, and recovery without cascading failures.

## 45. Separating generator load from cluster load

If the load generator maxes out CPU, it cannot issue requests at the target rate. Measured throughput becomes generator-bound.

Monitor:

- Generator CPU and memory.
- Open connection counts.
- DNS/TLS overhead.
- Network throughput.
- Request queues and dropped iterations.
- Active virtual users.

Run generators on dedicated or distributed machines so they never compete with Elasticsearch for resources. When measuring end-to-end APIs, keep network paths as close to production as possible.

## 46. Test data and privacy

Never copy production personal data into benchmark environments without controls. You can:

- Mask emails/phone numbers.
- Replace names and addresses with synthetic data.
- Preserve value distributions while replacing identifiers.
- Strip tokens, credentials, and internal notes.
- Restrict access to datasets.
- Encrypt storage and limit retention.

Benchmarks need statistical data characteristics, not real user identities.

If using anonymized production snapshots, document the source and transformation pipeline so the dataset remains reproducible.

## 47. Interpreting results and locating bottlenecks

Common diagnostic patterns:

| Symptom | Causes to check |
|---|---|
| High Elasticsearch `took`, high CPU | Complex queries, aggregations, scoring, or shard fan-out |
| Low Elasticsearch `took`, high API latency | Network, connection pool, entity mapping, DTOs, or serialization |
| Low indexing throughput, high 429s | Oversized concurrency/batches, indexing pressure, or overloaded cluster |
| High p99 with stable p50 | Heavy query subset, shard hotspot, GC, or disk latency |
| Latency grows with data scale | Cardinality, segments, shard sizing, or query selectivity |
| Search slows only during ingest | Merges, refreshes, indexing contention, and disk I/O |
| Aggregations slow for large tenants | Cardinality and skew |
| Heap climbs over time | Aggregation/bucket pressure, caches, memory leaks, or workload |
| One node runs much hotter | Shard allocation, routing skew, or node resource imbalance |

These are diagnostic leads, not automatic conclusions. Correlate with node stats, query profiles, slow logs, APM, and benchmark data.

## 48. Do not optimize around a single query

A query can run faster after a mapping change while the overall workload slows down:

- Adding fielddata or caches consumes heap.
- Adding replicas boosts search throughput yet raises write costs.
- Raising shard counts shrinks shards yet raises fan-out and overhead.
- Disabling `_source` saves storage yet breaks response/update/reindex flows.
- Adding nested fields makes queries accurate yet raises indexing cost.

Measure the entire query mix and read/write ratio. Optimize for system-wide trade-offs, not one endpoint.

## 49. Benchmarking and A/B testing mappings

When comparing a new mapping or query:

1. Create two indexes with identical data.
2. Keep shard counts, replicas, and settings identical.
3. Change only the mapping or query under test.
4. Run the same workload and random seed.
5. Measure latency, throughput, heap, disk, and index size.
6. Verify correctness of query results.
7. Run a mixed workload before deciding.

Never compare a force-merged new index against an old index under continuous ingestion. Keep segment and cache states comparable when comparing queries.

## 50. Measuring correctness alongside performance

A fast query returning wrong results is not a successful optimization.

When changing queries/mappings, verify:

- Hit counts.
- Returned document ID sets.
- Sort ordering.
- Aggregation values.
- Nested matching semantics.
- Highlights.
- Total hits relation.
- Tenant/document isolation.
- Boundary conditions on ranges and null/missing values.

Benchmarks should include correctness assertions per query family. Compare results against a trusted baseline on a fixed dataset.

Benchmarks do not replace functional tests; however, every performance change must verify semantics did not drift unexpectedly.

## 51. End-to-end benchmark workflow

A practical workflow:

1. Define SLOs and target workloads.
2. Collect query mix and data distributions from anonymized production data.
3. Generate a dataset with fixed seed/version.
4. Create indexes with production-like mappings and settings.
5. Bulk ingest and verify document counts, cardinality, and sizes.
6. Prepare refresh/cache state matching the scenario.
7. Run warm-up.
8. Run low-load baseline.
9. Run load test at target arrival rate.
10. Step up concurrency to locate saturation.
11. Run mixed read/write and bulk tests.
12. Run spike and soak tests.
13. Collect p50/p95/p99, throughput, errors, and resource metrics.
14. Use slow logs/Profile API to investigate slow queries.
15. Vary one parameter and rerun the same workload.
16. Verify correctness and repeat runs to confirm.
17. Archive report, dataset version, configs, and scripts for reproducibility.

## 52. Benchmark report template

A report should include:

    Benchmark: product-search-mixed-v3
    Date:
    Commit:
    Elasticsearch version:
    Spring Data version:
    Java version:
    Cluster nodes:
    CPU / RAM / disk:
    Primary shards / replicas:
    Dataset version:
    Document count:
    Index size:
    Query mix:
    Read/write ratio:
    Arrival rate:
    Concurrency:
    Warm-up:
    Measurement duration:
    Cache scenario:
    Refresh interval:

    Results:
      Throughput:
      p50:
      p95:
      p99:
      Error rate:
      429 count:
      Bulk item failure rate:
      Indexing lag:
      CPU:
      Heap:
      Disk I/O:
      Thread pool queue/rejections:

    Notes:
      Known deviations from production:
      Bottleneck observed:
      Follow-up experiments:

State every deviation from production explicitly. For example, a single-node test cluster, smaller dataset, or omitted write traffic. Those caveats clarify the scope of conclusions.

## 53. Common mistakes

### Benchmarking on a few hundred documents

Tiny datasets fit in caches and hide cardinality or shard-distribution effects. Use realistic scale and distributions.

### Uniformly random data

Production usually has tenant/category/keyword skew. Model skew as well as popular/rare values.

### Measuring a single query

Real workloads mix multiple query families and ratios. Use a representative query mix.

### Reporting average latency only

Averages hide tail latency. Report p50/p95/p99 and error rates.

### Skipping warm-up or measuring only warm caches

Cold-start and steady-state are separate scenarios. Document cache state and warm-up clearly.

### Running search-only tests

Indexing, refreshes, and merges slow down searches. Run mixed workloads when production reads and writes concurrently.

### Using the Profile API for production latency numbers

Profiling adds overhead. Use it for diagnostics, then remeasure with normal requests.

### Failing to monitor the load generator

A saturated generator produces artificially low throughput. Monitor CPU, connections, and dropped iterations.

### Increasing concurrency indefinitely

Past saturation, latency and errors surge with no throughput gain. Find an operating point with headroom.

### Force merging before every run

Force merging alters segment state. Use it only if production follows the same workflow.

### Changing multiple variables at once

You cannot tell which change produced the effect. Change one variable at a time and verify on mixed workloads.

### Ignoring correctness

A fast query returning missing or wrong documents is a regression. Compare results against a baseline.

### Not recording configurations

Makes runs irreproducible and differences unexplainable. Save mappings, settings, versions, dataset seeds, and workload scripts.

### Using real personal data

Benchmarks do not need real identities. Mask or synthesize data and enforce access controls.

## 54. When to use JMH?

JMH fits microbenchmarking isolated Java code such as:

- DTO transformations.
- Pure serialization/deserialization.
- Collection processing.
- Query object construction.
- Standalone mapping algorithms.

JMH does not replace Elasticsearch load tests. A JMH benchmark does not simulate shards, networking, disk, refreshes, merges, or cluster concurrency.

To isolate application CPU cost from network cost, benchmark mappers/serializers with JMH, then run end-to-end load tests across the full request path.

## 55. Evaluating connection pool impact

Spring Data Elasticsearch relies on an underlying client and transport. Connection pools, keep-alive, TLS, and timeouts affect latency.

Benchmarks should check:

- Whether connections are reused or opened per request.
- Pool size and requests waiting for connections.
- Connection timeouts.
- Socket/request timeouts.
- TLS handshakes.
- Load balancers/proxies.
- Transport/client retries.

If a benchmark creates a fresh client per request, it measures client initialization and handshake costs rather than production workloads. Clients should follow application lifecycle and reuse connections cleanly.

Do not expand pool sizes without bounds. More connections can push higher concurrency into the cluster and trigger overload.

## 56. Impact of source filtering and response size

Large responses consume network, heap, and serialization time. If an endpoint only needs name, price, and category, fetching full `_source` adds unnecessary overhead.

Benchmark two scenarios:

- Full source.
- Source filtering or projections returning only needed fields.

Measure:

- Response bytes.
- Elasticsearch `took`.
- Network throughput.
- Application mapping time.
- Heap allocation.
- HTTP serialization time.

Source filtering trims payloads without securing fields. Keep queries and semantics identical when comparing performance.

## 57. Impact of _source, stored fields, and doc values

Mappings affect both performance and retrieval capabilities:

- `_source` restores document JSON at a storage/transfer cost.
- Doc values power sorting/aggregations and certain field fetches.
- Stored fields can return fields marked `store`.
- `index: false` reduces indexing work while altering query capabilities.

Do not change mappings solely to optimize one tiny benchmark. Determine which fields need querying, sorting, aggregating, fetching, and reindexing; then measure index size, ingest throughput, query latency, and response size.

## 58. Impact of replicas

Replicas increase search capacity and fault tolerance at the expense of write overhead and storage.

Benchmark:

- Single primary without replicas.
- Primary with production-like replicas.
- High search concurrency.
- Concurrent bulk indexing.
- Node failures or replica recovery when evaluating resilience.

Do not compare write throughput between two setups and simply conclude replicas make things slow. Consider search throughput, availability, and recovery alongside writes.

## 59. Benchmarking in production-like environments safely

Avoid running stress tests directly against live production without planning and safeguards. Build a staging/performance environment with:

- Production-like node and disk specs.
- Anonymized datasets.
- Equivalent mappings and settings.
- Query mixes drawn from sanitized telemetry.
- Controlled rate limits and run windows.
- Cluster monitoring dashboards.
- Immediate stop criteria if errors or resources cross thresholds.

If a controlled production test is unavoidable, cap load, schedule carefully, monitor closely, and enforce clear abort rules. Never impose surprise load on user-serving systems.

## 60. Checklist before concluding a change is faster

- Identical dataset and random seed.
- Identical mappings/settings except the variable under test.
- Comparable cluster topology and hardware.
- Identical query mix and parameter distributions.
- Warm-up and cache states clearly documented.
- Sufficiently long measurement window.
- Load generator is not saturated.
- Throughput, p50, p95, p99, and error rates compared.
- CPU, heap, GC, disk, thread pools, and merges monitored.
- Search and indexing concurrency match target workloads.
- Result correctness verified.
- Results reproduced across multiple runs.
- Deviations from production documented.

## Conclusion

Measuring performance on production-like data and queries requires reproducing both data shape and workload behavior. Datasets must reflect production scale, document sizes, cardinality, skew, time distributions, nested structures, and update rates. Query mixes must cover searches, filters, sorts, pagination, aggregations, and nested queries with both common and rare parameters. Benchmarks must also simulate concurrent reads and writes when production runs mixed workloads.

Measure throughput alongside p50/p95/p99, error rates, and cluster resources, while instrumenting Spring Data/application code to separate server time from networking, connection pools, entity mapping, and serialization. Warm-up, caches, refreshes, merges, shard distributions, and load generators all influence measurements. Use the Profile API and slow logs for investigations, then remeasure with normal requests. Change one variable at a time, repeat runs, verify correctness, and archive datasets/configs/workloads for reproducibility. A reliable benchmark identifies the operating point meeting SLOs with headroom rather than producing a high throughput figure under favorable artificial conditions.
