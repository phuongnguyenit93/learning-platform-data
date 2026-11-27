# Building Reactive Search Pipelines and Load Limit Testing

A reactive search pipeline with Spring Data Elasticsearch must get three things right simultaneously: building semantically accurate queries, keeping the entire execution path non-blocking, and bounding the amount of work the application sends to Elasticsearch. Merely changing return types from List to Flux while still using a blocking client, calling block(), or allowing unbounded concurrency will still stall under load.

A complete hands-on implementation spans receiving search criteria in the API, validating inputs, building queries, invoking ReactiveElasticsearchOperations, mapping SearchHit objects to DTOs, streaming results to clients, and measuring behavior under load with representative data and workloads.

Target flow:

~~~text
HTTP request
    |
    v
WebFlux controller
    |
    v
Validate search criteria
    |
    v
Reactive search service
    |
    +-- build bounded query
    |
    +-- apply timeout / concurrency policy
    |
    v
ReactiveElasticsearchOperations
    |
    v
Reactive Elasticsearch client
    |
    v
Elasticsearch cluster
    |
    v
Flux<SearchHit<Product>>
    |
    v
DTO mapping and streaming response
~~~

## 1. Scope and Goals of the Exercise

We will build a keyword-based product search endpoint that returns only active products, optionally filters by brand, sorts deterministically, and streams results reactively.

Afterward, we will test:

- Latency under low, normal, and high load.
- Achieved throughput compared to the generated request arrival rate.
- Error rates, timeouts, and dropped iterations when virtual users are exhausted.
- Behavior under high request concurrency.
- Backpressure and concurrency limits.
- Resource utilization in both the application and Elasticsearch.
- Stability of latency over sustained duration.

The examples use Spring Boot WebFlux, Spring Data Elasticsearch reactive APIs, Project Reactor, and k6. Exact method and builder signatures can vary across release trains; use compatible dependency versions managed by Spring Boot/Spring Data.

## 2. How Does Reactive Search Differ from Blocking Search?

In the blocking model:

~~~java
List<Product> products = productRepository.findByNameContaining(keyword);
~~~

The calling thread blocks until I/O finishes. Under high concurrency, many threads stay parked waiting for Elasticsearch responses.

In the reactive model:

~~~java
Flux<Product> products = reactiveProductRepository.findByNameContaining(keyword);
~~~

The method returns a Publisher describing the work. I/O executes asynchronously when the pipeline is subscribed to. Threads are not held idle simply waiting for network responses.

This uses threads much more efficiently for I/O-bound workloads, though it does not give Elasticsearch infinite capacity. The cluster still has finite CPUs, shards, search threads, memory, file descriptors, and network bandwidth.

### 2.1. Reactive Does Not Automatically Mean Faster in Every Case

Reactive pipelines reduce thread-per-request overhead and help manage data streams. They do not make Query DSL cheaper, reduce shard counts, allow Elasticsearch to execute more queries, improve mappings/analyzers, or turn a heavy query into a light one.

If a query takes 2 seconds inside Elasticsearch, the reactive pipeline still waits 2 seconds for that result. The benefit is that application threads can handle other work while waiting.

### 2.2. Do Not Mix Blocking and Reactive Arbitrarily

The following destroy reactive benefits when run on an event-loop thread:

- Calling synchronous RestHighLevelClient.
- Using blocking RestTemplate or JDBC directly.
- Calling Mono.block() or Flux.blockFirst().
- Reading files or network sockets with blocking APIs.
- Waiting unboundedly on Future.get().

If calling a blocking API is unavoidable, isolate it on boundedElastic or a bounded executor while measuring and capping concurrency. Better yet, use reactive/non-blocking APIs end-to-end.

## 3. Configuring Reactive Elasticsearch

Spring Data Elasticsearch provides ReactiveElasticsearchConfiguration to set up reactive clients and operations.

Basic configuration example:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(5))
            .build();
    }
}
~~~

This is an illustrative configuration. TLS, authentication, path prefixes, and transport settings must match your environment. Spring Data Elasticsearch 6.x uses the Elasticsearch 9 client generation and Rest5Client by default; earlier versions use different client stacks. Never copy client configurations across major versions without checking the migration guide.

### 3.1. Distinguishing Imperative and Reactive Beans

| Component | Reactive type |
| --- | --- |
| Client | ReactiveElasticsearchClient |
| Operations | ReactiveElasticsearchOperations |
| Repository | ReactiveElasticsearchRepository |
| Auditing provider | ReactiveAuditorAware |
| Callbacks | ReactiveBeforeConvertCallback and related reactive callbacks |

Never inject imperative ElasticsearchOperations into a reactive service and invoke it on an event-loop thread. If an application uses both stacks, qualify bean names explicitly.

### 3.2. Timeouts Across Layers

Distinguish clearly:

- Connect timeout: time allowed to establish a connection.
- Socket/response timeout: time waiting for transport responses.
- Elasticsearch search timeout: server-side execution limit via the Search API.
- Application deadline: maximum time the business API permits.
- Client timeout: time the caller waits for the HTTP response.

Timeouts must align across layers. If the client times out after 2 seconds while Elasticsearch keeps running a 10-second query, cluster resources continue burning long after the caller gave up.

## 4. Mapping and Document for Search

Example entity:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // Constructors, getters and setters
}
~~~

The products-read alias can point to one physical index or multiple indices with compatible mappings. For load testing, use a dedicated test index or alias pointing to prepared test data in a test cluster.

### 4.1. Mappings Must Match Queries

- name and description are text for full-text search.
- brandId and status are keyword for exact matching and filtering.
- price is numeric for ranges and sorting.
- updatedAt is date for chronological sorting.
- id needs stable semantics if used as a sort tie-breaker.

Never use term queries to search for words inside an analyzed text field. Use match/multi_match for full-text and keyword fields for exact matches.

### 4.2. Analyzers and Test Data

Load tests need production-like data: realistic distributions of name/description length, brand/category counts, ACTIVE/INACTIVE ratios, shard and replica counts, term distributions, and hit/no-hit query ratios.

An overly tiny dataset may fit entirely in caches and hide real system cost. A huge dataset with unrealistic term distributions can also skew workload results.

## 5. Designing a Bounded Search API

APIs must never let clients pick arbitrary page sizes or send open-ended wildcards and index patterns.

Example request:

~~~http
GET /api/products/search?q=wireless%20keyboard&brandId=BRAND-10&page=0&size=20
~~~

Conventions:

- q is required and length-bounded.
- page is 0-indexed and non-negative.
- size defaults to 20 and caps at 50.
- Sort options are server-controlled or allowlisted.
- Tenant/security filters come from authenticated context.
- Never accept raw Elasticsearch Query DSL from public APIs.

### 5.1. Validate Before Calling Elasticsearch

~~~java
private static final int MAX_SIZE = 50;
private static final int MAX_OFFSET = 10_000;

private void validate(String keyword, int page, int size) {
    if (keyword == null || keyword.isBlank()) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Search keyword is required"
        );
    }

    if (keyword.length() > 120) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Search keyword is too long"
        );
    }

    if (page < 0 || size < 1 || size > MAX_SIZE) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Invalid page or size"
        );
    }

    long offset = (long) page * size;
    if (offset + size > MAX_OFFSET) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "Deep pagination is not supported by this endpoint"
        );
    }
}
~~~

Capping offset here fits shallow pagination. For deep traversal, build a cursor-based endpoint with search_after and PIT instead of raising max_result_window.

### 5.2. Never Trust Client Sort Fields

~~~java
Sort resolveSort(String requestedSort) {
    return switch (requestedSort) {
        case "price-asc" ->
            Sort.by(Sort.Direction.ASC, "price");
        case "price-desc" ->
            Sort.by(Sort.Direction.DESC, "price");
        case "newest" ->
            Sort.by(Sort.Direction.DESC, "updatedAt");
        default ->
            Sort.by(Sort.Direction.DESC, "updatedAt");
    };
}
~~~

Never pass raw client strings directly into field names in queries. Permit only mapped, business-approved fields.

## 6. Building Reactive Queries with NativeQuery

NativeQuery builds Elasticsearch Query DSL using the Elasticsearch Java API Client model.

Example searching name/description, filtering by status and brand, and sorting by update time:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

private Query buildQuery(
        String keyword,
        String brandId,
        int page,
        int size) {

    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> {
            b.must(m -> m.multiMatch(mm -> mm
                .query(keyword)
                .fields("name^3", "description")
            ));

            b.filter(f -> f.term(t -> t
                .field("status")
                .value("ACTIVE")
            ));

            if (brandId != null && !brandId.isBlank()) {
                b.filter(f -> f.term(t -> t
                    .field("brandId")
                    .value(brandId)
                ));
            }

            return b;
        }))
        .withPageable(PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("id")
            )
        ))
        .build();
}
~~~

This follows the Elasticsearch Java API Client builder style; exact bool builder signatures and query overloads can differ across versions. Verify compilation against your dependencies. Query semantics to preserve:

- multi_match in query context to compute relevance.
- status and brand in filter context as pure include/exclude predicates.
- sort with a tie-breaker for deterministic ordering.
- page size bounded before building the query.

### 6.1. Why Separate Filters from must?

status=ACTIVE and brandId are exact conditions that should not alter relevance scores. Placing them in bool.filter expresses proper semantics and avoids unnecessary scoring work.

### 6.2. When Keyword Is Absent

If the product supports browsing/filtering without a keyword, use a dedicated query branch containing only bool.filter or match_all with filters. Never send empty strings into match/multi_match.

### 6.3. Queries Must Be Bounded

A search endpoint should bound page size, offset or cursor lifetime, maximum allowed filters, terms list lengths, keyword lengths, wildcard/regex usage, query timeouts, and response sizes.

A syntactically valid query can still be far too expensive.

## 7. Reactive Search Service

The service returns Flux<SearchHit<ProductDocument>> or Flux<DTO> for further composition.

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    ProductSearchService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    Flux<ProductSearchItem> search(
            String keyword,
            String brandId,
            int page,
            int size) {

        validate(keyword, page, size);
        Query query = buildQuery(keyword, brandId, page, size);

        return operations.search(query, ProductDocument.class)
            .map(this::toSearchItem);
    }

    private ProductSearchItem toSearchItem(
            SearchHit<ProductDocument> hit) {
        ProductDocument product = hit.getContent();
        return new ProductSearchItem(
            product.getId(),
            product.getName(),
            product.getBrandId(),
            product.getPrice(),
            hit.getScore()
        );
    }
}
~~~

SearchHit preserves metadata such as score and sort values alongside content. If only entities are needed, you can use overloads returning Flux<T>, but keep SearchHit whenever score or sort metadata is required.

### 7.1. Response DTO

~~~java
public record ProductSearchItem(
    String id,
    String name,
    String brandId,
    Double price,
    Float score
) {}
~~~

Do not return the raw entity directly if it contains internal fields, unnecessary attributes, or sensitive data. DTOs constrain payload size and reduce serialization cost.

### 7.2. Never Collect Unbounded Results

Avoid collectList on queries that might return hundreds of thousands of documents. collectList buffers every element in memory until the stream completes.

If the endpoint returns a single tightly bounded page (e.g., max size 50), collectList may be acceptable. For large exports, process in batches/streams with checkpoints and bounded concurrency.

## 8. WebFlux Controller and Streaming Responses

Example endpoint returning NDJSON so items can stream as they arrive:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class ProductSearchController {

    private final ProductSearchService searchService;

    ProductSearchController(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    @GetMapping(
        value = "/api/products/search",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    Flux<ProductSearchItem> search(
            @RequestParam String q,
            @RequestParam(required = false) String brandId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        return searchService.search(q, brandId, page, size);
    }
}
~~~

NDJSON suits clients consuming records incrementally. If the API needs a single JSON object containing total counts, page metadata, and an item list, collect a strictly bounded page and return Mono<Response>. Never use response streaming as an excuse to drop page size limits.

### 8.1. Client Disconnects

When a client cancels its subscription, the reactive pipeline receives cancellation. Whether transport and server-side Elasticsearch execution abort immediately depends on client/server implementations and versions; never assume server-side tasks stop instantaneously.

Monitor cancelled requests and how long orphaned queries continue executing after clients disconnect. Set timeouts and concurrency caps so orphaned queries cannot burn resources indefinitely.

## 9. Bounding Concurrency at the Application Layer

A common mistake is accepting every incoming request and forwarding it straight to Elasticsearch. During traffic spikes, pending requests and connection acquisitions pile up, inflating latency and memory.

Control mechanisms:

- Rate limiting per client, tenant, or API key.
- Bulkheads limiting active search requests.
- Per-request timeouts.
- Page size and query complexity limits.
- Concurrency caps on batch jobs.
- Bounded queues when buffering is required.
- Load shedding when overloaded.

### 9.1. Bounding Concurrency in Reactor

~~~java
Flux<SearchRequest> requests = loadRequests();

return requests.flatMap(
    request -> searchService.search(request),
    16
);
~~~

The concurrency argument caps how many inner Publishers flatMap subscribes to simultaneously. 16 is only an example; measure under realistic workloads.

When input ordering must be preserved:

~~~java
return requests.concatMap(
    request -> searchService.search(request)
);
~~~

concatMap executes sequentially, lowering concurrency and preserving order at the cost of lower throughput. Pick the operator matching business semantics.

### 9.2. limitRate Is Not a System-Wide Rate Limiter

limitRate shapes upstream demand in batches via backpressure. It does not replace API gateway rate limits or application-wide bulkheads.

### 9.3. Be Careful with onBackpressureBuffer

Unbounded buffers turn transient spikes into OutOfMemoryError. When buffering is needed, configure a bounded capacity, define an overflow policy (reject, drop, or persist), monitor dropped/rejected items, and align with data semantics.

Never drop user search requests silently. During load shedding, return a retryable error such as 429 or 503 with an appropriate Retry-After header.

## 10. Timeouts, Retries, and Error Mapping

Never retry every Elasticsearch error. Retries apply only to transient failures and safe operations.

| Error | Appropriate handling |
| --- | --- |
| Timeout/network reset | Bounded retry if request deadline allows |
| HTTP 429/rejected execution | Backoff with jitter, reduce concurrency |
| HTTP 502/503/504 | Bounded retry |
| Mapping/parsing error | Do not retry as-is |
| Authentication/authorization | Do not retry; fix config/permissions |
| Query syntax error | Do not retry |
| Circuit breaker open | Fail fast or apply fallback per policy |

### 10.1. Retrying with Backoff

~~~java
return operations.search(query, ProductDocument.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .jitter(0.5)
            .filter(this::isTransientSearchFailure)
    );
~~~

This is an illustrative snippet. Verify exact exception types for your client version. Small retry counts help avoid amplifying load when Elasticsearch is already saturated.

### 10.2. Retries Can Worsen Load

When the cluster returns 429, immediate retries from all consumers drive load higher. Use exponential backoff, jitter, retry caps, and lower request rates.

Total retry time must stay within the request deadline. Once the deadline expires, return an error instead of continuing background queries.

### 10.3. Pipeline Timeouts

~~~java
return operations.search(query, ProductDocument.class)
    .timeout(Duration.ofSeconds(3));
~~~

Reactor's timeout stops subscriber waiting; whether the HTTP request and Elasticsearch search task cancel depends on transport and server support. Combine client and server timeouts and monitor post-cancellation query execution.

### 10.4. Mapping Errors to HTTP Statuses

An error handler can map:

- Invalid input: 400.
- Rate limited: 429.
- Search service overloaded/temporarily unavailable: 503.
- Deadline exceeded: 504.
- Unexpected internal failure: 500.

Never leak raw stack traces or Elasticsearch error bodies containing index names, internal queries, or infrastructure details to public callers.

## 11. Pagination and Deep Queries

For typical interactive endpoints, small page sizes and shallow offsets keep things simple.

~~~java
PageRequest.of(
    page,
    size,
    Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("id")
    )
)
~~~

The id tie-breaker keeps ordering deterministic when documents share the same updatedAt.

### 11.1. from/size Limits

Elasticsearch caps the result window by default to prevent memory-heavy deep queries. Raising index.max_result_window is not the default answer to deep pagination.

### 11.2. search_after

For scrolling across many pages:

1. Open a Point in Time if a consistent view is required.
2. Search with a sort containing a unique tie-breaker.
3. Read sort values from the last hit.
4. Send search_after for the next page.
5. Close the PIT when done.

Cursors should be server-managed or signed so clients cannot alter index, query, or sort values arbitrarily.

### 11.3. Load Testing Pagination

Never benchmark only page 0. Test page 0, the deepest allowed page, cursor/search_after, PIT lifecycle, doc-valued sort fields, and behavior while data mutates during paging.

Deep pagination exhibits a very different cost profile than page 0.

## 12. Total Hits and Response Size

Computing exact total hits can cost more than fetching one page. If the UI does not need an exact total, avoid forcing exact counts on massive datasets.

When totals are needed, decide whether exact or approximate counts suffice, narrow query scope, use the track-total-hits API/setting supported by your version, and avoid returning thousands of unnecessary aggregation buckets.

Response size affects network, serialization, and memory. Project only needed fields via DTOs and cap page size.

## 13. Preparing the Load Test Environment

Never run load tests against a production cluster unless under a separately approved test plan. Use an environment matching production sizing with representative data.

Prepare:

- Spring Boot app built with a production-like profile.
- Test Elasticsearch cluster with appropriate node, shard, and replica counts.
- Equivalent mappings and analyzers.
- Representative dataset.
- Dedicated index/alias for load testing.
- k6 or another load-testing tool.
- Dashboards/metrics for both the app and Elasticsearch.
- Resource guardrails and abort criteria.

### 13.1. Do Not Use Tiny Datasets

Tiny datasets stay warm in page cache and query cache, failing to represent production workloads.

Prepare data with realistic document counts, realistic field/term distributions, production-like match ratios, a mix of common and rare queries, and varied document sizes.

### 13.2. Warm-Up

Before measuring:

1. Start the application and Elasticsearch.
2. Wait for health checks to stabilize.
3. Send a warm-up burst of requests.
4. Allow JIT compilation, connection pools, and caches to stabilize.
5. Begin the measurement window.

Do not fold warm-up into steady-state measurements. If cold-start latency matters, measure cold-start scenarios separately.

## 14. Selecting Workloads and Load Models

| Test type | Purpose |
| --- | --- |
| Smoke | Verify script and endpoint work |
| Baseline | Measure performance under low/representative load |
| Load | Measure at expected target traffic |
| Stress | Ramp load until limits appear |
| Spike | Sudden traffic surge |
| Soak | Sustain load over time to detect leaks/drift |
| Capacity | Find maximum throughput meeting SLOs |

### 14.1. Virtual Users vs. Arrival Rate

Virtual users simulate concurrent user loops. Arrival-rate executors generate requests at a target cadence.

These two concepts are not identical:

- VUs: virtual users running iterations concurrently.
- RPS: requests initiated per second.

When response time rises, each VU completes fewer iterations per second. Thus fixed VUs do not maintain fixed RPS.

### 14.2. Use Arrival Rate When Testing Throughput

When targeting 100 requests/second, use constant-arrival-rate or ramping-arrival-rate executors. Watch dropped_iterations to see whether k6 ran short of VUs to sustain the target rate.

Never draw server capacity conclusions solely from achieved RPS if the load generator itself ran out of resources.

## 15. k6 Script for the Reactive Search Endpoint

Example script:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const searchErrors = new Rate('search_errors');
const searchLatency = new Trend('search_latency', true);

export const options = {
  scenarios: {
    product_search: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: 10, duration: '1m' },
        { target: 30, duration: '2m' },
        { target: 60, duration: '2m' },
        { target: 60, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<700'],
    search_errors: ['rate<0.01'],
    dropped_iterations: ['count==0']
  }
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  const keywords = [
    'wireless keyboard',
    'mechanical keyboard',
    'gaming mouse',
    'usb hub'
  ];

  const keyword = keywords[Math.floor(Math.random() * keywords.length)];
  const url = baseUrl + '/api/products/search?q='
    + encodeURIComponent(keyword) + '&page=0&size=20';

  const response = http.get(url, {
    headers: {
      Accept: 'application/x-ndjson'
    },
    tags: {
      endpoint: 'product-search'
    }
  });

  const ok = check(response, {
    'status is 200': (r) => r.status === 200,
    'response is not empty': (r) => r.body !== null
  });

  searchErrors.add(!ok);
  searchLatency.add(response.timings.duration);

  sleep(0.1);
}
~~~

Thresholds in this script are illustrative targets, not performance guarantees. Replace them with your real SLOs. If the endpoint returns a JSON array instead of NDJSON, adjust the Accept header accordingly.

### 15.1. Running a Smoke Test

~~~bash
k6 run --vus 1 --iterations 5 search.js
~~~

### 15.2. Running a Load Test

~~~bash
k6 run search.js
~~~

On Windows PowerShell:

~~~powershell
$env:BASE_URL = "http://localhost:8080"
k6 run .\search.js
~~~

### 15.3. Reading Results

Key metrics to inspect:

- http_req_duration: overall request duration.
- p(50), p(95), p(99): latency percentiles.
- http_req_failed: HTTP error rate.
- iterations: completed iterations.
- dropped_iterations: iterations k6 could not launch at the arrival rate.
- search_errors: custom check failure rate recorded by the script.
- search_latency: endpoint-specific latency trend.

Never inspect averages alone. p95 and p99 expose the experience of slow requests.

## 16. Designing Realistic Workloads

Search traffic normally spans a mix of query types:

| Query type | Illustrative share |
| --- | ---: |
| Popular keywords, first page | 45% |
| Rare keywords | 15% |
| With brand/category filters | 20% |
| Zero results | 5% |
| Sorted by price/date | 10% |
| Deep pages/cursor | 5% |

Base weights on real traffic or documented assumptions. Never send a single fixed keyword across all VUs, as query caches will paint an overly rosy picture.

### 16.1. Query Mix

Include multiple categories: common keywords, long keywords, low-hit keywords, low-cardinality filters, high-cardinality filters, wide and narrow ranges, and queries returning few vs. many hits.

Do not include expensive wildcards or regexes in the workload if the production API forbids them.

### 16.2. Page Size Mix

Test the page sizes allowed by the API, such as 10, 20, and 50. Never benchmark size 10 and assume size 50 has identical latency.

### 16.3. Cold vs. Warm Cache

Measure cold-start/cold-cache, warm steady-state, post-refresh/post-indexing, and continuous background updates separately. Document how cache state is prepared so runs are repeatable.

## 17. Measuring Load Limits in the Application

Monitor:

- HTTP request rate and active requests.
- p50/p95/p99 latency.
- Error rates by status and exception.
- Reactor event-loop utilization.
- Thread counts and blocked threads.
- CPU and heap usage.
- GC pauses and allocation rates.
- Connection pool active, idle, and pending acquire counts.
- Pending requests and timeouts.
- Rate-limited/rejected request counts.
- Cancellations and client disconnects.

### 17.1. Blocked Event Loops

If a callback or service calls block(), an event-loop thread stalls. Under concurrent requests, throughput drops and latency spikes.

Symptoms:

- CPU is not necessarily at 100%, yet latency climbs.
- Event-loop threads become blocked.
- BlockHound warnings if enabled in tests.
- Thread dumps reveal event-loop threads waiting on blocking I/O.

### 17.2. Connection Pools

Reactive clients still enforce connection caps and pending acquire limits. When the app issues too many concurrent requests, callers queue for connections, pending queues grow, timeouts fire before queries reach Elasticsearch, and retries swell queues even further.

Never raise connection pool limits indefinitely. Size them according to Elasticsearch capacity and file-descriptor/network limits.

## 18. Measuring Load Limits in Elasticsearch

Monitor search thread pool active/queue/rejected counts, CPU, JVM heap and GC, old-generation pressure, circuit breaker trips, per-shard search latency, query cache hit/miss rates and memory, segment counts and merge activity, disk I/O, network throughput, shard count/size, and active search tasks.

### 18.1. Search Thread Pool Queue

If queues keep growing and rejections climb, the cluster cannot keep up with incoming requests. Increasing queue size only lengthens wait times and burns memory without adding real throughput.

Examine query cost, shard fan-out, concurrency, and request rates before tuning thread pool settings.

### 18.2. Shard Fan-Out

A query hitting many shards incurs fan-out and reduce coordination overhead. Too many tiny shards raise coordination cost. Size shard counts to match data volume and workload.

### 18.3. Query Cache

Track cache metrics, but never assume every filter is cached. Evaluate cache hit ratios alongside latency, segment churn, and query mix.

### 18.4. Circuit Breakers

Elasticsearch uses circuit breakers to protect JVM memory. When requests trigger oversized aggregations or fetches, breakers reject them. Treat breaker trips as signals to bound queries/responses and tune workloads, not as an automatic reason to disable breakers.

## 19. Pinpointing Bottlenecks by Changing One Variable at a Time

When latency spikes, never change page size, shard count, pool size, and Query DSL simultaneously. Vary one factor per run:

1. Hold the dataset and query mix constant.
2. Ramp arrival rates step by step.
3. Record latency and error rates.
4. Observe both application and Elasticsearch metrics.
5. Identify where queueing, rejections, or p99 inflect sharply.
6. Change a single variable.
7. Re-run the exact same workload.

| Experiment | Change | Purpose |
| --- | --- | --- |
| A | Baseline | Measure current configuration |
| B | Reduce page size 50 to 20 | Measure fetch/serialization cost |
| C | Drop unnecessary aggregations | Measure aggregation cost |
| D | Add selective filter/query | Measure impact of fewer candidates |
| E | Cap concurrency | Observe queue/rejections and p99 |
| F | Change sort field | Inspect doc values and sort cost |

Never draw conclusions from a single run. Repeat runs in an identical environment.

## 20. Little's Law and Concurrency Limits

\[
L = \lambda W
\]

Where L is the average number of requests inside the system, lambda is average throughput (requests/second), and W is average response time (seconds).

For instance, if the system serves 100 requests/second with an average response time of 0.2 seconds:

\[
L = 100 \times 0.2 = 20
\]

On average, roughly 20 requests are concurrently active or waiting inside the system.

If latency degrades to 1 second while arrival rate stays constant:

\[
L = 100 \times 1 = 100
\]

Concurrency jumps fivefold, putting immediate pressure on connection pools, memory, and queues.

Little's Law clarifies the relationship among throughput, latency, and concurrency; it does not prescribe the maximum safe concurrency by itself. Actual limits must be measured against resources and SLOs.

### 20.1. Placing a Bulkhead

~~~text
Incoming requests
       |
       v
Rate limiter
       |
       v
Search bulkhead (max N active)
       |
       +-- capacity available -> Elasticsearch
       |
       +-- full -> 429/503
~~~

Determine N via load testing. Setting N too high risks overloading Elasticsearch; setting N too low leaves cluster capacity underutilized.

## 21. Testing Backpressure and Cancellation

Reactive Streams define downstream demand signaling from subscriber to publisher. However, an Elasticsearch search request does not necessarily fetch one document per downstream demand signal.

Distinguish Reactor pipeline backpressure, HTTP client buffering/decoding, Elasticsearch's fetch phase, hits returned per request, and WebFlux response serialization.

### 21.1. Never Assume Downstream Demand Controls Elasticsearch Shards

Backpressure regulates item emission through the pipeline, yet a query already sent to Elasticsearch has already consumed server resources. Page sizes, query timeouts, and cancellation policies remain essential.

### 21.2. Testing Client Disconnects

Write a test client that begins consuming a stream and closes the connection early. Observe whether WebFlux cancels the Publisher, whether the reactive Elasticsearch client aborts the transport request, how long the server-side search task keeps running, whether the app releases connections/permits, and whether unexpected cancellation errors appear in logs.

### 21.3. Never Buffer Large Responses in Memory

If clients need exports of millions of documents, build a checkpointed export job writing to object storage rather than streaming an unbounded Flux in a single HTTP response.

## 22. Soak Tests and Memory Leaks

Soak tests sustain steady load over an extended duration to catch creeping heap usage, leaked buffers, connection leaks, growing pending queues, uncompleted Reactor subscriptions, unclosed PITs/contexts, Elasticsearch segment/merge pressure, and worsening GC pauses.

### 22.1. Signs of Memory Leaks

- Post-GC heap baseline climbs across cycles.
- Long-lived object counts keep growing.
- Direct memory climbs.
- Pending requests or buffered items fail to return to baseline.
- Connection pool usage stays elevated after load drops.

### 22.2. Releasing Resources

Ensure PITs are closed, subscriptions complete or cancel cleanly, test containers and clients shut down properly, scheduled tasks and retry publishers do not outlive tests, and connections are reused rather than created per request.

## 23. Integration Tests with Testcontainers

Unit tests can mock ReactiveElasticsearchOperations to verify mapping and query branching. Integration tests require real Elasticsearch to verify Query DSL, mappings, analyzers, sorting, and the reactive client.

Example test:

~~~java
@Test
void shouldReturnOnlyActiveProducts() {
    ProductDocument active = product("P-1", "Wireless Keyboard", "ACTIVE");
    ProductDocument inactive = product("P-2", "Wireless Keyboard", "INACTIVE");

    StepVerifier.create(
        operations.save(active)
            .then(operations.save(inactive))
            .then(indexOperations.refresh())
            .thenMany(searchService.search("wireless keyboard", null, 0, 20))
    )
    .assertNext(result ->
        assertThat(result.id()).isEqualTo("P-1")
    )
    .verifyComplete();
}
~~~

Adapt the snippet to the return type of refresh() and index/alias creation APIs in your Spring Data version. Use isolated test indices so data from other tests never pollutes results.

### 23.1. Testing Reactive Pipelines with StepVerifier

StepVerifier asserts item counts, ordering, completion, errors, and cancellation cleanly in reactive tests.

Never call subscribe manually in a test and assert immediately; the test method can exit before the async pipeline finishes.

### 23.2. Testing Mappings and Queries

Integration tests should confirm keyword queries find expected documents, status filters exclude inactive documents, brand filters work, sorting uses tie-breakers, page sizes respect caps, empty hits return an empty stream, and invalid inputs fail before hitting Elasticsearch.

## 24. Staged Load Limit Testing

| Phase | Load | Duration | Goal |
| --- | --- | --- | --- |
| Smoke | 1 VU or a few requests | Short | Confirm script and endpoint work |
| Warm-up | Low load | 1–3 minutes | Stabilize JIT and connection pools |
| Baseline | 5–10 RPS | 3–5 minutes | Measure baseline latency |
| Load | Step up to target | 5–10 minutes | Verify SLO compliance |
| Stress | Push beyond target | Monitored | Locate saturation point |
| Soak | Steady load | 30–120 minutes | Detect leaks/accumulation |
| Recovery | Drop back to low load | 2–5 minutes | Confirm system recovers |

Loads and durations are planning examples only. Pick targets suited to your product, environment, and resource budget.

### 24.1. Stop Conditions

Define abort criteria upfront: error rates above threshold, sustained p99 breaches, dangerous Elasticsearch heap/CPU levels, steadily rising search thread pool rejections, circuit breaker trips, degraded cluster health, or the load generator failing to sustain arrival rate.

Stop tests once guardrails trip. Never push load blindly just to force a crash.

## 25. Load Test Results Report

| Metric | Result |
| --- | --- |
| Dataset size | Document count and index size |
| Cluster topology | Nodes, shards, replicas |
| Application replicas | Instance count and CPU/memory limits |
| Target arrival rate | Requested RPS |
| Achieved throughput | Actual RPS |
| p50 | Median latency |
| p95 | 95th percentile latency |
| p99 | 99th percentile latency |
| Error rate | Percentage of failed requests |
| Dropped iterations | Iterations dropped by load generator |
| App CPU/heap | Application resource usage |
| ES CPU/heap | Elasticsearch resource usage |
| Search rejections | Count of rejected requests |
| Bottleneck | Observed limiting factor |

Record exact versions of the app, Spring Data, Elasticsearch, JVM, and k6, plus shard layout, query mix, warm-up, and run duration. Without environment context, runs cannot be compared reliably.

## 26. Example Rate Limit and Bulkhead Flow

At the API gateway or service layer, limit per-client requests over a time window, total concurrent search requests per instance, per-tenant search requests, and total wait time.

~~~text
Request
  |
  v
Authenticate and resolve tenant
  |
  v
Validate query and page size
  |
  v
Rate limit by tenant/API key
  |
  v
Acquire search permit
  |
  +-- no permit --> return 429/503
  |
  v
Execute bounded reactive query
  |
  v
Release permit on complete/error/cancel
~~~

Permits must be released on every terminal signal, including errors and cancellation. If managing a manual semaphore, guard against double-releases or leaks when clients disconnect.

Resilience4j offers RateLimiter, Bulkhead, TimeLimiter, and CircuitBreaker modules. Pick modules compatible with Reactor operators in your project version; never wrap a reactive Publisher with a synchronous-only decorator when semantics conflict.

## 27. Common Pitfalls

**Simply changing List to Flux.** If a blocking client or block() remains, event loops still stall. Use reactive clients and operations end-to-end.

**Subscribing manually inside services.** Callers lose control over completion and error propagation. Return Mono/Flux to callers.

**Collecting unbounded results.** collectList on large sets spikes memory. Cap pages or stream via cursors/batches.

**Allowing arbitrary page sizes from clients.** One huge fetch can overwhelm the cluster. Cap size in the API.

**Permitting deep from/size pagination.** Costs climb with offset. Use search_after/PIT for deep traversal.

**Allowing unbounded wildcards or regexes.** Queries can scan excessive documents and shards. Validate query capabilities and restrict patterns.

**Unbounded flatMap.** Many concurrent inner Publishers flood the cluster. Cap concurrency and enforce bulkheads.

**Unbounded onBackpressureBuffer.** Queues grow until OutOfMemoryError. Use bounded buffers with explicit overflow policies.

**Retrying every exception.** Mapping errors and authorization failures never self-heal. Retry only transient failures with strict caps.

**Retrying immediately on 429.** Retry storms worsen overload. Use backoff, jitter, and reduced concurrency.

**Measuring only average latency.** Averages hide tail latency. Track p95/p99 and error rates.

**Using fixed VUs to claim RPS targets.** Slow responses shrink actual RPS. Use arrival-rate executors for throughput testing.

**Ignoring dropped_iterations.** The load generator may be starved. Monitor k6 host resources and maxVUs.

**Using tiny datasets.** Caches skew results optimistically. Use production-like data volumes and distributions.

**Skipping warm-up or mixing warm-up into measurements.** Skews comparisons. Separate phases clearly.

**Monitoring only the application.** Bottlenecks often sit in Elasticsearch search thread pools, shards, or disk. Watch both sides.

**Blindly growing the connection pool on pending acquires.** Elasticsearch may already be saturated. Measure cluster capacity before raising pool limits.

**Ignoring cancellation.** Clients leave while queries continue burning server resources. Track cancellations and server-side tasks.

**Skipping post-stress recovery checks.** Queues or backlogs may stay stuck after load subsides. Always include a recovery phase.

## 28. End-to-End Implementation Workflow

1. Create mappings and a read alias for the test dataset.
2. Configure compatible ReactiveElasticsearchClient and ReactiveElasticsearchOperations.
3. Define ProductDocument with explicit field mappings.
4. Build queries using multi_match and bool.filter.
5. Cap keywords, page, size, sort, and offset.
6. Write a service returning Flux<SearchHit> or Flux/DTOs.
7. Write a WebFlux endpoint returning NDJSON or bounded page responses.
8. Add timeouts, error mapping, and concurrency policies.
9. Write StepVerifier, unit, and integration tests.
10. Prepare representative datasets and app/Elasticsearch dashboards.
11. Run k6 smoke, baseline, load, stress, and soak tests.
12. Track p95/p99, error rates, achieved RPS, and dropped iterations.
13. Pinpoint bottlenecks from metrics, vary one parameter at a time, and re-test.
14. Document reports with exact versions and configurations for comparison.

## 29. Operational Checklist

- [ ] Client and Spring Data versions are compatible.
- [ ] Services use ReactiveElasticsearchOperations or reactive repositories.
- [ ] No block() calls or blocking I/O on event-loop threads.
- [ ] Queries use appropriate mappings and analyzers.
- [ ] Keywords and filters are validated.
- [ ] Page size and offset are bounded.
- [ ] Sorts include a stable tie-breaker.
- [ ] Responses project only required fields.
- [ ] No unbounded collection of large result sets.
- [ ] Concurrency caps and rate limits are configured.
- [ ] Timeouts and retry policies are bounded.
- [ ] Retries use backoff/jitter and target only transient errors.
- [ ] Cancellation behavior is monitored.
- [ ] Load tests run against isolated indices/datasets.
- [ ] Load generators have sufficient resources.
- [ ] Track p95/p99, error rates, and dropped iterations.
- [ ] Monitor both application and Elasticsearch metrics.
- [ ] Define stop conditions for stress tests.
- [ ] Include recovery and soak tests.
- [ ] Reports document dataset, topology, versions, and workload.

## 30. References

- [Spring Data Elasticsearch - Reactive Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): reactive operations and query execution.
- [Spring Data Elasticsearch - Reactive Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/reactive-repositories.html): reactive repository abstractions.
- [Spring Data Elasticsearch - Client Configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html): client configuration and version-specific client stacks.
- [Spring Data Elasticsearch - NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQuery.html): building queries with the Elasticsearch Java API Client.
- [Project Reactor - Reference Guide](https://projectreactor.io/docs/core/release/reference/): Publishers, backpressure, concurrency, retries, and testing.
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP request handling and streaming.
- [Elasticsearch - Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html): queries, sorting, timeouts, and search request options.
- [Elasticsearch - Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html): from/size, search_after, and Point in Time.
- [Elasticsearch - Search thread pool](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-threadpool.html): thread pools, queues, and rejected requests.
- [k6 - Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): VU-based and arrival-rate executors.
- [k6 - Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): SLO thresholds for latency and errors.
- [k6 - Built-in metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): request duration, failed requests, and dropped iterations.

Method overloads in Spring Data Elasticsearch and the Java API Client vary by version. Compile examples against your actual dependencies and check corresponding Javadocs. The goal of this exercise is to keep the reactive pipeline non-blocking, bound queries and concurrency, and use controlled load tests to find the sustainable traffic envelope meeting SLOs; reactive APIs never substitute for sound query design and Elasticsearch capacity management.
