# Measuring Application-Side Time and Elasticsearch Time Separately

When an API using Spring Data Elasticsearch is slow, measuring only from when the controller receives a request to when it returns a response is not enough to identify the cause. That duration can include business processing, waiting on threads or a connection pool, request serialization, network transfer, Elasticsearch processing, receiving the response, deserialization, and mapping results into entities.

To diagnose accurately, you need to separate at least two perspectives:

- **Application elapsed time:** the time observed by the application around an Elasticsearch call. It includes client overhead and waiting time from the caller's perspective.
- **Elasticsearch-reported time (server execution time):** the duration returned by Elasticsearch in the response, such as the `took` field of the Search API or `SearchHits.getExecutionDuration()` in Spring Data Elasticsearch versions that support it.

These two numbers measure different intervals. You should not subtract Elasticsearch time from application time and conclude that the remainder is exact network latency. The difference can also include waiting for a connection, serialization, response mapping, callbacks, scheduling, and other overhead.

## 1. Why measure both sides?

Suppose a search endpoint takes 420 ms according to application logs. The search response from Elasticsearch reports took = 95 ms.

This indicates Elasticsearch reported a search processing duration of 95 ms, while the application took 420 ms in total for the measured interval. The remainder could come from:

- The application processing and preparing criteria.
- Waiting to acquire a connection from the HTTP connection pool.
- Serializing the query into an HTTP request.
- Transmitting the request to an Elasticsearch node.
- Waiting through proxies, load balancers, or internal networking.
- Deserializing the response and mapping hits to entities.
- Converting SearchHits into DTOs.
- Post-search processing before returning the HTTP response.

This is an illustrative example, not an exact breakdown. If you only look at application latency, you may mistakenly think the Elasticsearch query is slow. If you only look at `took`, you may miss that the application is waiting on connections or spending too long processing responses.

## 2. Defining measurement boundaries

Before adding timers, clearly define start and end points.

A synchronous flow can be illustrated as:

~~~text
HTTP request enters controller
          |
          v
  Validate / business logic
          |
          v
     Build Search Query
          |
          v
  Call Spring Data / Client
          |
          +------------------------------+
          |                              |
          v                              v
  Client serialize                 Elasticsearch
  / connection / network          processes request
          |                              |
          |                         Server took
          |                              |
          +---------------+--------------+
                          |
                          v
                 Receive response
                          |
                          v
              Deserialize / map entity
                          |
                          v
                Map DTO / response
                          |
                          v
                  HTTP response out
~~~

Multiple intervals can be measured:

| Timer | Start | End | Purpose |
|---|---|---|---|
| HTTP request | Request enters application | Response is sent | API caller perspective |
| Search service | Service starts processing | Service returns result | Business and search cost inside service |
| Elasticsearch call | Right before client call | Call completes | Time the application waits on the Elasticsearch operation |
| Elasticsearch took | Per server measurement boundary | Server response reports | Time reported by Elasticsearch |
| Mapping/DTO | Start converting results | Complete DTO ready | Cost of processing results in the application |

Do not group timers with different boundaries under the same metric name. Metric names and tags should clearly state which part is being measured.

## 3. Measuring elapsed time in Java with System.nanoTime

For synchronous code blocks, use System.nanoTime() to measure duration. It is a monotonic clock suitable for elapsed intervals; do not use System.currentTimeMillis() to benchmark elapsed time because the wall clock can be adjusted.

Example:

~~~java
long started = System.nanoTime();

try {
    SearchHits<Product> hits =
            operations.search(query, Product.class);

    long elapsedNanos = System.nanoTime() - started;
    Duration applicationDuration =
            Duration.ofNanos(elapsedNanos);

    log.info(
            "Elasticsearch call completed in {} ms",
            applicationDuration.toMillis()
    );

    return hits;
} catch (RuntimeException exception) {
    long elapsedNanos = System.nanoTime() - started;
    log.warn(
            "Elasticsearch call failed after {} ms",
            Duration.ofNanos(elapsedNanos).toMillis()
    );
    throw exception;
}
~~~

The timer starts right before operations.search and ends when the method returns or throws an exception. This interval is the time the application observes around the Spring Data call. It can include request serialization, connection wait, network, server processing, response transfer, deserialization, and result mapping.

It does not necessarily equal the total time seen by the user across the entire endpoint. If the service also validates, builds queries, maps DTOs, or calls other services, measure those intervals separately.

### 3.1. Recording failed requests as well

In real code, ensure timers are recorded even when requests fail. You can record outcome as a tag:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);
String outcome = "success";

try {
    return operations.search(query, Product.class);
} catch (RuntimeException exception) {
    outcome = "error";
    throw exception;
} finally {
    sample.stop(Timer.builder("app.elasticsearch.call")
            .tag("operation", "search")
            .tag("outcome", outcome)
            .register(meterRegistry));
}
~~~

Timer.Sample starts using the registry's clock and stops into a Timer registered with the corresponding outcome tag. This records both successful and failed requests without calling nonexistent methods on Timer.

Do not record timers only on the success branch. Timeouts, connection failures, or rejections are also important performance data.

## 4. Measuring Elasticsearch time from the Search response

The Elasticsearch Search API returns a `took` field in the response. This is the processing time reported by the coordinating node, in milliseconds. It differs from application-measured elapsed time because it does not include all client-observed overhead, such as request/response transfer and pre/post-call processing.

With the Elasticsearch Java Client, the search response can provide took():

~~~java
SearchResponse<ProductDocument> response =
        elasticsearchClient.search(
                request -> request
                        .index("products")
                        .query(query),
                ProductDocument.class
        );

long elasticsearchTookMillis = response.took();
~~~

With Spring Data Elasticsearch, some versions provide execution duration on SearchHits<T>:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class);

Duration elasticsearchDuration =
        hits.getExecutionDuration();
~~~

getExecutionDuration() reflects the duration propagated from the search response according to the corresponding Spring Data API. Check Javadoc/dependency versions in use if this method does not exist in your project's release train. When raw Elasticsearch metadata is needed, you can use the Elasticsearch Java Client directly and read SearchResponse.took().

### 4.1. Logging both numbers side by side

Example:

~~~java
long started = System.nanoTime();

SearchHits<Product> hits =
        operations.search(query, Product.class);

Duration applicationDuration =
        Duration.ofNanos(System.nanoTime() - started);

Duration elasticsearchDuration =
        hits.getExecutionDuration();

log.info(
        "product search: app={} ms, elasticsearch={} ms, totalHits={}",
        applicationDuration.toMillis(),
        elasticsearchDuration.toMillis(),
        hits.getTotalHits()
);
~~~

This log lets you observe both perspectives within the same request. In production systems, attach a correlation/trace ID to locate the exact request and correlate it with traces, slow logs, or server metrics.

Do not log the full query if it contains sensitive data or could bloat logs. You can log the operation name, index alias, query type, page size, outcome, and trace ID.

## 5. took is not the user's total time

Search `took` is the Elasticsearch-side duration returned in the response. It tells you how long the server reported spending, but does not include every step of the request from the application's perspective.

Do not treat `took` as:

- The time from when the user clicks a button until the UI receives data.
- The time from when the controller starts until the controller finishes.
- The time spent serializing the request on the client.
- The time the application waits on the connection pool.
- The time spent receiving the entire response over the network and mapping it to objects.

`took` is also not a per-shard measurement. A search can hit multiple shards; the coordinating node merges results and returns a single duration in the response. To analyze query/fetch phases on shards, use other tools such as the Profile API or slow logs.

### 5.1. Do not subtract took from app time and call it network time

Suppose:

~~~text
Application elapsed: 420 ms
Elasticsearch took:   95 ms
Difference:          325 ms
~~~

You cannot conclude that the network took 325 ms. The difference can include:

- Waiting for the connection pool or client threads.
- Serialization/deserialization.
- Network and proxies.
- Mapping responses into SearchHit/entities.
- Callbacks or logic inside the timer boundary.
- Waiting periods not measured against the same boundary as server `took`.

To measure network or connection acquisition specifically, you need tracing/instrumentation in client transport and network infrastructure. The difference is only a signal that overhead exists outside server duration.

## 6. Not every API provides took

Search responses usually include `took`. Some batch APIs like Bulk or Update By Query also return their own duration in the response. However, not every single-document write response provides an equivalent server-side duration field.

| API | Timing information available | Notes |
|---|---|---|
| Search | took | Server-reported duration for search |
| Bulk | took, and possibly ingest_took | Bulk request duration; ingest duration relates only to ingest pipelines |
| Update By Query | took | Potentially long-running task supporting task tracking |
| Reindex | took | Long-running task; track task and progress |
| Single document index | No general took field in standard index responses | Measure app elapsed and use tracing/metrics to analyze server side |
| Get by ID | Standard response has no took equivalent to Search | Measure app elapsed and tracing |

Do not fabricate an `elasticsearch.took` metric by reusing app time for responses that do not provide server duration. Name metrics accurately after their data source, e.g., `app.elasticsearch.call`.

## 7. Measuring with Micrometer

Micrometer Timer is well suited for recording durations and analyzing latency distributions. With Spring Boot, the registry can export metrics to Prometheus, OTLP, or any configured backend.

Example of a service timing search calls:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class ProductSearchService {

    private final ElasticsearchOperations operations;
    private final MeterRegistry meterRegistry;

    public ProductSearchService(
            ElasticsearchOperations operations,
            MeterRegistry meterRegistry
    ) {
        this.operations = operations;
        this.meterRegistry = meterRegistry;
    }

    public SearchHits<Product> search(Query query) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            return operations.search(query, Product.class);
        } catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(Timer.builder("app.elasticsearch.call")
                    .description("Elapsed time around a Spring Data Elasticsearch call")
                    .tag("operation", "search")
                    .tag("index", "products")
                    .tag("outcome", outcome)
                    .register(meterRegistry));
        }
    }
}
~~~

The timer above measures the application-observed time around the operations.search call. It does not automatically measure `took` separately; if server duration is needed, record the value from SearchHits.getExecutionDuration() or the raw response separately.

### 7.1. Recording server duration as a separate metric

After receiving SearchHits, you can record the server-reported duration:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

Timer.builder("elasticsearch.search.server_duration")
        .tag("index", "products")
        .register(meterRegistry)
        .record(hits.getExecutionDuration());
~~~

This is an illustrative metric for Spring Data versions that support getExecutionDuration(). If that method is absent, read `took` from the Elasticsearch Java Client or appropriate response metadata. Do not substitute application-side elapsed time.

### 7.2. Tags should have low cardinality

Commonly useful tags:

- operation: search, get, bulk, update.
- index: stable alias/index name.
- outcome: success, error, timeout.
- query_type: controlled query category such as full_text, filtered, aggregation.

Avoid high-cardinality tags:

- Document ID.
- User ID.
- Search keywords.
- Full Query DSL.
- URLs with dynamic IDs.
- Trace ID or request ID.

These values can create millions of time series and overload the metrics system. Trace IDs belong in tracing/logging, not metric tags.

## 8. Measuring reactive operations properly

With Reactive Spring Data Elasticsearch, methods can return Mono or Flux. Calling the method only creates a publisher; the actual request may not execute until the publisher is subscribed to.

Therefore, the following code can measure inaccurately:

~~~java
long started = System.nanoTime();
Mono<SearchPage<Product>> result =
        reactiveOperations.searchForPage(query, Product.class);
long elapsed = System.nanoTime() - started;
~~~

The interval above mainly measures the time to construct the publisher, not the time to execute the request.

Measure inside the publisher using `defer` and `doFinally`:

~~~java
Mono<SearchPage<Product>> measuredSearch =
        Mono.defer(() -> {
            long started = System.nanoTime();

            return reactiveOperations.searchForPage(
                            query,
                            Product.class
                    )
                    .doFinally(signalType -> {
                        long elapsed = System.nanoTime() - started;
                        applicationTimer.record(
                                elapsed,
                                TimeUnit.NANOSECONDS
                        );
                    });
        });
~~~

Mono.defer places the start point at subscription time. doFinally records the duration when the publisher completes, errors, or is cancelled. For Flux, apply the same principle, noting that the timer measures until the entire stream completes or is cancelled.

If a stream can run for a long time or the caller only reads part of it and cancels, the duration reflects how long the subscription lived, not necessarily how long the server took to process all results. Define metric semantics before using it for comparisons.

## 9. Measuring individual stages on the application side

A single timer around operations.search only tells you the total duration of the Spring Data call. If that timer is high while server `took` is low, break it down further:

1. Validate and normalize criteria.
2. Build Query/NativeQuery.
3. Wait and send request through the client.
4. Deserialize and map response.
5. Convert SearchHits into DTOs.
6. Serialize HTTP response.

Example measuring query building and the Elasticsearch call separately:

~~~java
long buildStarted = System.nanoTime();
Query query = queryBuilder.build(criteria, pageable);
Duration buildDuration =
        Duration.ofNanos(System.nanoTime() - buildStarted);

long searchStarted = System.nanoTime();
SearchHits<Product> hits =
        operations.search(query, Product.class);
Duration applicationSearchDuration =
        Duration.ofNanos(System.nanoTime() - searchStarted);

long mappingStarted = System.nanoTime();
ProductSearchResponse response = mapper.toResponse(hits);
Duration mappingDuration =
        Duration.ofNanos(System.nanoTime() - mappingStarted);
~~~

From these figures, you can determine whether query building or mapping is significant. Avoid adding too many tiny timers unless you have a specific diagnostic question; overly dense instrumentation also makes code and metrics harder to manage.

## 10. Using distributed tracing to find wait segments

Metrics show latency distributions over time, but do not always reveal where a request waited. Distributed tracing can create spans for:

- HTTP request entering the service.
- Repository/service calls.
- Elasticsearch client request.
- Other downstream services.

If client instrumentation supports it, traces can link application spans with Elasticsearch calls. With a trace ID, correlate against application logs and server logs to locate the specific request.

With Spring Boot, you can use Micrometer Observation/Tracing and a corresponding exporter. Automatic span creation for Elasticsearch depends on the Spring Boot version, Elasticsearch Java Client, and instrumentation configuration. Verify that spans are actually generated rather than assuming they are just because a tracing dependency was added.

Tracing adds a request-chain view; it does not replace server-side `took`, slow logs, or node metrics.

## 11. Elasticsearch slow logs

Slow logs record queries that exceed configured duration thresholds on each shard. They help identify whether the query phase or fetch phase is slow and preserve details for investigation.

Two categories to distinguish:

- **Query slow log:** time spent by the shard processing the query phase, finding documents, and computing scores.
- **Fetch slow log:** time spent by the shard fetching document contents and preparing results.

A request with a simple query that returns many fields or a large `_source` can spend significant time in the fetch phase. Therefore, do not look only at the query slow log.

Thresholds can be configured at the index level using index settings. Illustrative example:

~~~http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "search": {
      "slowlog": {
        "threshold": {
          "query": {
            "warn": "2s",
            "info": "1s",
            "debug": "500ms"
          },
          "fetch": {
            "warn": "1s",
            "info": "500ms",
            "debug": "250ms"
          }
        }
      }
    }
  }
}
~~~

The thresholds above are only examples. Setting structure, log levels, and logger names must be verified against your Elasticsearch version. Setting thresholds too low can generate very large log volumes. Start with thresholds aligned with your SLA and adjust based on traffic and log capacity.

Slow logs are per-shard/phase measurements, not a replacement for application elapsed time or overall response `took`.

## 12. Profile API for analyzing queries

The Elasticsearch Profile API provides detailed timing information for query components on shards:

~~~http
GET /products/_search
Content-Type: application/json

{
  "profile": true,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Profiling can show how long query components and collectors took from the shard's perspective. It is useful when you need to identify which clause incurs high cost.

Do not enable the Profile API permanently for all production requests:

- Profiling adds overhead and can slow down queries.
- Output is verbose and hard to aggregate into SLA metrics.
- Profile does not measure full time from the application, network, and client mapping.
- Component timings do not necessarily sum up to `took` or application elapsed time.

Enable it only for controlled investigative requests, on appropriate data and environments.

## 13. Monitoring node, thread pool, and index statistics

If `took` rises alongside queues/rejections or high CPU, the issue may lie in cluster load rather than an individual query.

Useful data sources:

| Source | What to observe |
|---|---|
| Node stats | CPU, heap, garbage collection, thread pool, filesystem |
| Thread pool stats | Queued and rejected tasks in search/write pools |
| Index stats | Search query/fetch counts and cumulative time, indexing, refresh, merge |
| Tasks API | Long-running tasks like update-by-query, reindex, search tasks |
| Hot threads | Threads consuming CPU at the time of investigation |
| Slow logs | Slow query/fetch on shards |

Example reading the search thread pool:

~~~http
GET /_nodes/stats/thread_pool
~~~

Reading index search stats:

~~~http
GET /products/_stats/search
~~~

Reading currently running tasks:

~~~http
GET /_tasks?detailed=true&actions=*search
~~~

Cumulative statistics like query_time_in_millis should be evaluated using deltas and sampling intervals. Do not divide cumulative total time by a single request or treat it as current latency.

## 14. Designing comparable benchmarks

A measurement is only meaningful when runs share comparable conditions. When comparing two queries or two implementations, keep constant:

- Dataset and document count.
- Mapping and analyzers.
- Number of primary shards and replicas.
- Routing and number of shards actually queried.
- Refresh interval and refresh state.
- Query DSL, sort, highlight, aggregations.
- Page size and fields/source to return.
- Concurrency level and background workload.
- Cache state and warm-up.

Do not compare a query run on a newly warmed index with a query run on a freshly started index and conclude the difference comes from the DSL.

### 14.1. Warm-up and JIT

The first run may pay costs for connection initialization, class loading, JIT compilation, or cold caches. Run several warm-up iterations before sampling. State clearly whether you are measuring cold-start or steady-state because those two goals differ.

### 14.2. Measuring p50, p95, and p99

Do not report only the average. Latency distributions often have long tails:

- p50 describes the typical request.
- p95 indicates that 5% of requests are slower than this threshold.
- p99 captures tail latency for the slowest group of requests.

Also record throughput, error rate, timeouts, and concurrency level. A change that lowers the average while worsening p99 can degrade the experience for a subset of users.

### 14.3. Changing one factor at a time

If you simultaneously change page size, analyzer, shard count, and refresh interval, it is difficult to tell which change produced the outcome. Test each factor under controlled conditions, then test combinations.

Do not use the Profile API during normal latency benchmark runs because profiling adds its own overhead. Use it in a separate diagnostic run once you have identified a query to investigate.

## 15. Factors that easily skew measurements

### 15.1. Refresh policy

refresh=true can force an immediate refresh and make write requests take longer. refresh=wait_for can make the application wait for the next refresh. An application timer around writes will reflect that wait, while not all write responses provide a corresponding server `took`.

Do not compare two write runs if one uses default refresh and the other uses refresh=wait_for without accounting for that difference.

### 15.2. Connection pool

When the connection pool is exhausted or new connections must be established, the application may wait before Elasticsearch receives the request. Check connection reuse, pool limits, pending acquisitions, and connection errors.

### 15.3. Response size

Large page sizes, large `_source`, many highlight fragments, or deep inner hits can increase data transfer and mapping cost. Server `took` may not fully reflect the time the application spends deserializing and converting the response.

Test with the same response shape and result size when comparing.

### 15.4. Retries and timeouts

A single application call may include retries or timeouts at the transport/client layer. Application elapsed time can span multiple attempts. The server may only report the duration of the request that reached the node, or each individual request may have its own duration.

Record retry count and outcome. Do not collapse multiple attempts into a single assumed `took`.

### 15.5. Concurrency and background load

A query that is fast in isolation can be slow under load due to queues, CPU, heap, I/O, or contention. Benchmarks need concurrency close to the real workload while monitoring the cluster concurrently.

## 16. Interpreting results to guide investigation

| Observation | Next area to investigate |
|---|---|
| High app time, low server took | Connection pool, network, serialization, mapping, callbacks, application threads |
| Both app time and server took are high | Query, shard load, fetch, aggregations, cluster resources |
| High query slow log, low fetch | Query DSL, analyzer, scoring, filters, shard distribution |
| Low query, high fetch | `_source` size, page size, stored fields, highlighting, inner hits |
| Good p50 but bad p99 | Queues, GC, contention, hot shard, background load, retries |
| High server took with growing search queue | Search thread pool saturation or overloaded node |
| Only overall endpoint is slow, ES call is normal | Business logic, downstream services, DTO mapping, response serialization |
| High bulk app time but low bulk took | Client preparation, payload serialization, network, or response handling |

The rows in this table are diagnostic guides, not automatic conclusions. Correlate with traces, logs, metrics, and the actual workload.

## 17. Production measurement checklist

- [ ] Clearly define where the application timer starts/ends.
- [ ] Use System.nanoTime() or Micrometer Timer to measure elapsed time.
- [ ] Record success, error, timeout, and cancellation outcomes.
- [ ] Record server `took` separately when provided by the response.
- [ ] Do not infer server duration from app elapsed time.
- [ ] Do not call app time minus `took` exact network time.
- [ ] Use low-cardinality metric tags.
- [ ] Use trace IDs to correlate specific requests.
- [ ] Track p50, p95, p99, throughput, and error rate.
- [ ] Check query/fetch slow logs when server search is slow.
- [ ] Enable the Profile API only during controlled investigations.
- [ ] Monitor thread pool queues/rejections, CPU, heap, and index stats.
- [ ] Keep dataset, mapping, shards, refresh, and concurrency constant during benchmarks.
- [ ] Measure reactive publishers from subscription to terminal signal.

## 18. Conclusion

Application-side time and Elasticsearch time are two distinct measurements. Application elapsed time reflects how long the caller waits for a Spring Data/client operation to complete, including client, network, server, and mapping overhead. Search `took` or SearchHits.getExecutionDuration() reflects the duration Elasticsearch reports in the response, useful for evaluating server-side execution.

Measure application elapsed time with System.nanoTime() or Micrometer Timer, and record server duration separately when the API provides it. For write responses without an equivalent `took`, use tracing, slow logs, and node/index metrics to investigate; do not fabricate a server number by using app elapsed time.

When app time is high while server `took` is low, investigate connection pools, networking, serialization, and mapping. When both are high, examine query/fetch slow logs, the Profile API in a dedicated diagnostic run, and cluster resources. Benchmark with warm-up, concurrency, stable data, and consistent response shape; track p50/p95/p99 instead of looking only at averages. Clear measurement boundaries help pinpoint the true source of slowdowns and avoid optimizing the wrong layer.
