# GraphQL metrics and alerting

GraphQL aggregates many fields behind a single endpoint. A single HTTP request might run a simple query, a multi-step mutation, or a deeply nested query invoking many DataFetchers and DataLoaders. Therefore, tracking only total HTTP request counts and overall response times is not enough to know which resolver is slowing GraphQL down, where errors originate, or whether DataLoader is actually eliminating N+1 queries.

Spring for GraphQL integrates Micrometer Observation to time and trace GraphQL requests, non-trivial DataFetchers, and DataLoaders. Spring Boot Actuator exposes these meters to monitoring systems such as Prometheus, Datadog, or OTLP. From those signals, operations teams can build dashboards, define SLIs/SLOs, and create alerts when users are genuinely impacted.

This lesson walks from Spring for GraphQL's default observations to Actuator configuration, histograms, and PromQL, then covers sustained alerts, dashboards, runbooks, cardinality control, and monitoring verification.

## 1. Why does GraphQL need dedicated metrics?

Suppose a client sends the query:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
    }
    reviews {
      rating
      reviewer {
        name
      }
    }
  }
}
~~~

This single HTTP request can trigger:

1. A root DataFetcher loading `Book`.
2. An `Author` resolver loading the author.
3. A `Reviews` resolver loading the list of reviews.
4. A `Reviewer` resolver loading the reviewer for each review.
5. A DataLoader batching the `Reviewer` loads together.

If you only measure HTTP latency, you know the request took 900 ms, but not whether 850 ms was spent in the database, a remote service, the `Reviews` resolver, or repeated `Reviewer` fetches.

Metric layers to observe:

| Layer | Question to answer | Signal |
| --- | --- | --- |
| Transport | Are HTTP/WebSocket connections failing or congested? | HTTP server metrics, connection metrics |
| GraphQL request | Which operations are slow, and what is the error rate? | **graphql.request** |
| DataFetcher | Which resolvers are frequently slow or failing? | **graphql.datafetcher** |
| DataLoader | Which batch loaders are slow or failing? | **graphql.dataloader** |
| Infrastructure | Are JVM, database pools, or executors exhausting resources? | JVM, datasource, pool, and executor metrics |

Metrics show trends and blast radius. Traces and logs help pinpoint a specific request. All three telemetry signals need to be linked together.

## 2. Metrics, traces, and logs are different

| Telemetry type | Used for | Example |
| --- | --- | --- |
| Metrics | Aggregated trends, alerting, and SLOs | p95 latency, error ratio, request rate |
| Traces | Following a single request across components | GraphQL request → DataFetcher → HTTP client → database |
| Logs | Recording details of an event or error | Exception, operation name, execution ID, error path |

Do not put entire GraphQL documents and variables into metrics. Query text may contain sensitive data, and each document or query variant can create a separate series if placed into a label.

A typical investigation flow:

1. An alert signals that p95 GraphQL latency breached the SLO.
2. The dashboard shows **graphql.request** rising while transport latency does not rise proportionally.
3. Drill down by **graphql.field.name** to find that the `Reviews` resolver is slow.
4. Open the corresponding trace via execution ID or trace ID.
5. Inspect logs to find the database or remote service error.

## 3. Three default observations in Spring for GraphQL

Spring for GraphQL integrates Micrometer Observation. When an **ObservationRegistry** is configured and **GraphQlObservationInstrumentation** is registered, the instrumentation creates three primary observations:

| Observation name | Scope | When created |
| --- | --- | --- |
| **graphql.request** | Entire GraphQL request execution | Queries, mutations, and subscriptions on supported transports |
| **graphql.datafetcher** | One DataFetcher invocation | Non-trivial DataFetchers; simple property fetchers on Java objects are excluded |
| **graphql.dataloader** | One DataLoader call | **@BatchMapping** and manually registered DataLoaders |

Observations can produce both Timer metrics and trace spans depending on configured handlers. Observations are only published when the application has an `ObservationRegistry` and corresponding handlers.

### 3.1. graphql.request

**graphql.request** measures operation execution time and adds default KeyValues:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| **graphql.operation.type** | Low | `query`, `mutation`, `subscription`, or `operation` if the document cannot be parsed |
| **graphql.outcome** | Low | Outcome of GraphQL request processing |
| **graphql.execution.id** | High | Execution ID of the request |
| **graphql.operation.name** | High | Operation name sent by the client |

`graphql.operation.type` is useful for separating query, mutation, and subscription load. Operation name and execution ID can take many distinct values, so they belong in traces/logs and should not become metric labels.

Default values of `graphql.outcome`:

| Value | Meaning in Spring for GraphQL |
| --- | --- |
| `SUCCESS` | GraphQL response is valid and has no errors |
| `REQUEST_ERROR` | Request failed to parse or response has errors, provided none is of type `INTERNAL_ERROR` |
| `INTERNAL_ERROR` | Could not produce a valid GraphQL response or response has at least one error of type `INTERNAL_ERROR` |

**Note:** `REQUEST_ERROR` is an observation convention outcome name, not an HTTP status classification. A response with partial data and a nested field error can also carry this outcome. Therefore, do not mechanically treat `graphql.outcome != SUCCESS` as a server availability error ratio.

### 3.2. graphql.datafetcher

**graphql.datafetcher** measures non-trivial DataFetchers. Simple property fetchers reading fields off Java objects typically do not create observations.

Default KeyValues:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| **graphql.error.type** | Low | Class name of the error when the DataFetcher fails |
| **graphql.field.name** | Low | Name of the field being resolved |
| **graphql.outcome** | Low | `SUCCESS` or `ERROR` |
| **graphql.field.path** | High | Field path in the response, e.g. `/bookById/author` |

`graphql.field.name` helps locate slow resolvers by field. `graphql.field.path` can vary across data branches or aliases, so it is kept in high-cardinality metadata for traces.

Not every field in a query produces a `graphql.datafetcher` observation. When a property is read directly from a source object, there is no custom DataFetcher to time.

### 3.3. graphql.dataloader

**graphql.dataloader** observes `@BatchMapping` calls and manually registered DataLoaders.

Default KeyValues:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| **graphql.error.type** | Low | Class name of the error |
| **graphql.loader.name** | Low | DataLoader name |
| **graphql.outcome** | Low | `SUCCESS` or `ERROR` |
| **graphql.loader.size** | High | Number of items loaded in the batch |

`graphql.loader.name` is helpful for comparing batch loaders. `graphql.loader.size` can vary per request, so it is placed in high-cardinality metadata and should not be used as a default metric label.

If you need a batch size histogram to alert on batches that are too small or too large, create a dedicated metric with a bounded loader name and record the size via `DistributionSummary`. Do not convert the default high-cardinality key directly into a Timer tag.

Example dedicated batch size metric:

~~~java
DistributionSummary batchSize = DistributionSummary.builder("graphql.dataloader.batch.size")
        .description("Number of keys loaded by a DataLoader batch")
        .tag("loader", "bookAuthors")
        .register(meterRegistry);

batchSize.record(bookIds.size());
~~~

Use only `loader` tags from a finite, server-controlled list. If loader names are generated dynamically per tenant or request, normalize them into a fixed set of categories.

## 4. Enabling GraphQL Observation in Spring Boot

For Spring Boot applications, common dependencies are:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Spring Boot auto-configures `ObservationRegistry` when observability infrastructure is present. Spring Boot 3.x and 4.x include auto-configuration for GraphQL observation when `ObservationRegistry` and Spring GraphQL are on the classpath. Check your Boot version and avoid manually registering a duplicate instrumentation if auto-configuration already creates the bean.

For non-Boot Spring Framework applications or custom GraphQL setups, ensure `GraphQlObservationInstrumentation` is attached to the GraphQL source. APIs and registration mechanisms may vary across Spring for GraphQL versions; consult the Javadoc of the exact dependency in use.

### Verifying that observation is working

After starting the application:

1. Send a successful GraphQL query.
2. Send a query with a validation error or DataFetcher error.
3. Send a query with a nested field resolved via `@SchemaMapping`.
4. Send a query using `@BatchMapping` or a DataLoader.
5. Check `/actuator/metrics` to confirm `graphql.request`, `graphql.datafetcher`, and `graphql.dataloader` meters exist.

If you see `graphql.request` but not `graphql.datafetcher`, check the instrumentation and confirm the query actually invokes a non-trivial DataFetcher. If `graphql.dataloader` is missing, confirm the query triggered the batch loader.

## 5. Exposing metrics via Actuator and Prometheus

Spring Boot provides Actuator endpoints to inspect metrics and expose Prometheus scrapes.

Example `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: catalog-graphql
~~~

The `micrometer-registry-prometheus` dependency enables Spring Boot to provide the `/actuator/prometheus` endpoint. The endpoint must be explicitly exposed; simply having the dependency does not make the endpoint public.

Prometheus scrape configuration:

~~~yaml
scrape_configs:
  - job_name: catalog-graphql
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets:
          - catalog-graphql:8080
~~~

Meter names in Actuator typically use Micrometer's dot format such as `graphql.request`. When exported to Prometheus, naming conventions convert dots to underscores and Timers are represented in seconds, for example:

| Meter name in Actuator | Prometheus series |
| --- | --- |
| `graphql.request` | `graphql_request_seconds_count`, `graphql_request_seconds_sum` |
| `graphql.datafetcher` | `graphql_datafetcher_seconds_count`, `graphql_datafetcher_seconds_sum` |
| `graphql.dataloader` | `graphql_dataloader_seconds_count`, `graphql_dataloader_seconds_sum` |

When histograms are enabled, each Timer also emits `_seconds_bucket` series.

### Securing Actuator endpoints

Do not expose all Actuator endpoints to the public Internet. Metrics endpoints can reveal meter names, tags, topology, or operational details.

Common approaches:

- Expose the Prometheus endpoint only on an internal network accessible by Prometheus.
- Use a dedicated management port or management interface.
- Enforce authentication/authorization in Spring Security or at the ingress.
- Expose only the endpoints needed.
- Never put secrets, user IDs, or query variables into tags.

The example above only illustrates which endpoints to expose; configure security suitable for your deployment environment.

## 6. Histograms and latency percentiles

A Micrometer Timer records total count and total duration. When histograms are enabled, the backend can compute percentiles over aggregated data.

With Prometheus, histograms are suitable for calculating p50, p95, or p99 via `histogram_quantile`. Client-computed percentiles cannot be accurately aggregated across multiple instances like histogram buckets can.

Example enabling histograms and SLO buckets for GraphQL requests:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        graphql.request: true
        graphql.datafetcher: true
      slo:
        graphql.request: 100ms,300ms,1s,3s
~~~

The thresholds in this example are only starting points. Choose buckets based on actual latencies and service targets. Histograms increase time series count and memory usage, so enable them only on meters that require latency distribution analysis.

### Computing p95 GraphQL request latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(graphql_request_seconds_bucket[5m])
  )
)
~~~

Breakdown by operation type:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, graphql_operation_type) (
    rate(graphql_request_seconds_bucket[5m])
  )
)
~~~

Breaking down by operation type helps compare queries, mutations, and subscriptions when transport/operation observations share semantics. For long-lived subscriptions, evaluate stream lifetime and per-event latency separately rather than mixing them directly with short requests.

### Computing request rate

~~~promql
sum by (graphql_operation_type) (
  rate(graphql_request_seconds_count[5m])
)
~~~

This represents GraphQL executions per second by operation type. It does not necessarily equal the HTTP request rate because transports may serve non-GraphQL requests, batched requests, or long-lived subscription connections.

### Computing average latency

~~~promql
sum(rate(graphql_request_seconds_sum[5m]))
/
sum(rate(graphql_request_seconds_count[5m]))
~~~

Average latency is useful for tracking overall trends, yet it can mask a subset of very slow requests. Use p95/p99 alongside it once histograms are enabled.

## 7. Cardinality: choosing the right tags

Cardinality is the number of distinct time series generated by a metric name and its label/tag combinations. Every label with many values multiplies the series count.

Example metric:

~~~text
graphql_request_seconds_count{
  application="catalog-graphql",
  graphql_operation_type="query",
  graphql_outcome="SUCCESS"
}
~~~

Bounded values like `query`, `mutation`, `subscription`, and outcome are low cardinality. Conversely, execution ID can differ on every single request.

### Default classification in Spring GraphQL

| Key | Low/High | Should it be a metric label? |
| --- | --- | --- |
| `graphql.operation.type` | Low | Yes |
| `graphql.outcome` | Low | Yes |
| `graphql.operation.name` | High | Not by default |
| `graphql.execution.id` | High | No |
| `graphql.field.name` | Low | Yes |
| `graphql.field.path` | High | No |
| `graphql.error.type` | Low per convention | Yes, if the set of class names is controlled |
| `graphql.loader.name` | Low | Yes |
| `graphql.loader.size` | High | No |

Micrometer uses only low-cardinality KeyValues as meter tags. High-cardinality KeyValues are meant for tracing and logging backends capable of storing many distinct values.

### Do not put these values into metric tags

- Execution ID, request ID, or trace ID.
- User ID, email, tenant ID, or session ID.
- GraphQL document/query text.
- Variables or input payloads.
- URLs with path parameters substituted by real values.
- Operation hashes or arbitrary client-generated operation names without a bounded allowlist.

These values can be stored in traces/logs with controlled access and retention. Metric labels require finite value sets so storage costs do not scale with user count.

### When should you add custom tags?

Appropriate tags:

- `graphql.client.type` with a bounded list such as `web`, `ios`, `android`, `service`.
- `graphql.tenant.tier` with fixed tiers such as `free`, `standard`, `enterprise`.
- `graphql.schema.version` if the number of active running versions is bounded and managed.

Inappropriate tags:

- `graphql.client.id` if there are thousands of individual clients.
- `graphql.tenant.id` if tenants are unbounded.
- `graphql.operation.name` if clients can invent arbitrary names.

If you need analysis by specific client, emit structured logs or controlled trace attributes rather than turning client ID into a metric label.

## 8. SLIs and SLOs for GraphQL

An SLI is a quantitative measure of service quality. An SLO is the target for an SLI over a time window.

A GraphQL service might choose:

| SLI | Example definition | Purpose |
| --- | --- | --- |
| Availability | Proportion of operations completing per the service's success criteria | Measure availability |
| Latency | Proportion of requests under a latency threshold | Measure speed |
| Error ratio | Proportion of operations with user-impacting errors | Measure reliability |
| Freshness | Maximum data age or sync lag | Measure data recency if required by the business |

Example initial SLOs:

- 99.9% of GraphQL requests in critical operation groups complete per success criteria over 30 days.
- 95% of critical queries complete within 500 ms.
- 99% of critical queries complete within 1.5 seconds.

These numbers are only examples. Real SLOs must be based on user experience, observed baselines, and operational capacity.

### Define GraphQL success carefully

GraphQL allows partial data alongside errors. Therefore, "HTTP 200" does not mean every field succeeded.

Conversely, not every GraphQL error is a server outage:

- A validation error caused by a client querying a non-existent field may be a client error.
- A business error such as an entity not found may be expected behavior.
- A failure on a secondary field may not impact the primary user flow.
- `INTERNAL_ERROR` is typically a server-side signal requiring investigation.

Spring for GraphQL's default `graphql.outcome` classifies responses containing errors (other than `INTERNAL_ERROR`) as `REQUEST_ERROR`. This is an observation outcome, not an HTTP client-error label. If you treat every `graphql.outcome` other than `SUCCESS` as an availability SLI failure, you may burn error budget on valid client input errors or expected business outcomes.

Define success according to business semantics. For example:

- Request parse/validation errors are tracked separately.
- Domain errors may count as expected outcomes when clearly specified by the schema contract.
- Internal server errors and infrastructure dependency failures count as bad events.
- Partial data is evaluated based on the criticality of the failed field.

If you need a dedicated SLI for this classification, create a custom low-cardinality outcome convention or business metric rather than reinterpreting the default `graphql.outcome`.

## 9. GraphQL dashboards

A good operational dashboard should quickly answer: are users affected, when did it start, what is the scope, and which component is slow or failing?

### Row 1: Request overview

| Panel | Query/metric | Question |
| --- | --- | --- |
| Request rate | `rate(graphql_request_seconds_count[5m])` | Volume of queries/mutations running |
| Error ratio | Ratio of internal errors or business bad events | Are users experiencing errors? |
| p50/p95/p99 | Histogram of `graphql.request` | How is latency changing? |
| Outcome distribution | `graphql.outcome` | Are requests succeeding, hitting request errors, or hitting internal errors? |

### Row 2: Resolvers and DataLoaders

| Panel | Metric | Question |
| --- | --- | --- |
| DataFetcher p95 | `graphql.datafetcher` histogram | Which resolvers are slow? |
| DataFetcher error rate | `graphql.datafetcher` with outcome `ERROR` | Which fields fail most often? |
| DataLoader p95 | `graphql.dataloader` histogram | Which batch loaders are slow? |
| DataLoader errors | `graphql.dataloader` with outcome `ERROR` | Which loaders are failing? |
| Batch size distribution | Custom `DistributionSummary` if needed | Are batches too small or too large? |

### Row 3: Infrastructure

Monitor alongside on the dashboard:

- JVM heap, garbage collection, and CPU.
- Active/idle/max database connections.
- HikariCP pending connection threads.
- HTTP client latency and error rates.
- Executor queues, active threads, and rejected tasks.
- Pod restarts, container CPU/memory, and readiness.

A slow GraphQL resolver may simply be a symptom of an exhausted database pool or a slow remote service. The dashboard should help connect these signals.

## 10. Alerting: notify when users are impacted

Good alerts should:

- Reflect user-facing symptoms.
- Have thresholds and sustain durations to filter out brief spikes.
- Page only when someone must take immediate action.
- Link to an accompanying dashboard and runbook.
- Have clear ownership and severity.
- Avoid creating a separate alert for every internal metric.

Prometheus supports `for` to require a condition to persist continuously before firing, and `keep_firing_for` to prevent alert flapping when a signal briefly recovers.

### 10.1. Internal error ratio alert

PromQL example:

~~~promql
(
  sum(rate(graphql_request_seconds_count{
    graphql_outcome="INTERNAL_ERROR"
  }[5m]))
  /
  sum(rate(graphql_request_seconds_count[5m]))
) > 0.01
and
sum(rate(graphql_request_seconds_count[5m])) > 0.2
~~~

This condition inspects only internal errors, requiring the ratio to exceed 1% and traffic to exceed 0.2 requests/second to avoid alerting on tiny sample sizes. Thresholds are illustrative; tune them to your SLOs and actual traffic.

### 10.2. p95 latency alert

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(graphql_request_seconds_bucket[5m])
  )
) > 1.5
~~~

This example fires when p95 exceeds 1.5 seconds. Do not page on a brief spike; add `for` in the rule to require sustained breach.

### 10.3. Rising DataFetcher error alert

~~~promql
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_count{
    graphql_outcome="ERROR"
  }[5m])
) > 0.5
~~~

This can be a ticket-level alert or dashboard warning rather than a page. A field might return expected business errors; filter or classify error types before treating this as an incident.

### 10.4. Example Prometheus alert rules

~~~yaml
groups:
  - name: graphql-service
    rules:
      - alert: GraphQLInternalErrorRatioHigh
        expr: |
          (
            sum(rate(graphql_request_seconds_count{graphql_outcome="INTERNAL_ERROR"}[5m]))
            /
            sum(rate(graphql_request_seconds_count[5m]))
          ) > 0.01
          and
          sum(rate(graphql_request_seconds_count[5m])) > 0.2
        for: 5m
        keep_firing_for: 2m
        labels:
          severity: page
          service: catalog-graphql
        annotations:
          summary: "GraphQL internal error ratio is high"
          description: "Internal GraphQL errors exceeded 1% for 5 minutes."
          runbook_url: "https://runbooks.example.com/catalog-graphql/internal-errors"

      - alert: GraphQLP95LatencyHigh
        expr: |
          histogram_quantile(
            0.95,
            sum by (le) (rate(graphql_request_seconds_bucket[5m]))
          ) > 1.5
        for: 10m
        labels:
          severity: ticket
          service: catalog-graphql
        annotations:
          summary: "GraphQL p95 latency is high"
          description: "GraphQL p95 latency has exceeded 1.5 seconds for 10 minutes."
          runbook_url: "https://runbooks.example.com/catalog-graphql/latency"
~~~

Replace domains, service labels, runbook URLs, and thresholds with your organization's real configuration. Latency rules need a traffic floor or should target operation groups with enough requests for stable percentiles.

### 10.5. Alert fatigue

Do not create paging alerts for every DataFetcher, every exception class, or every database query. One database outage can simultaneously fail dozens of resolvers; paging per field sends many notifications for a single root cause.

Page at the request-symptom or critical-dependency layer. Resolver/loader metrics aid investigation and can open tickets for sustained trends.

## 11. Error budget and burn-rate alerting

Once you have SLOs, you can alert on error budget consumption rate instead of a fixed error threshold.

For example, a 99.9% availability SLO has a 0.1% error budget over a 30-day window. Burn rate indicates how fast the budget is being consumed relative to the allowed pace:

~~~text
burn rate = observed error ratio / allowed error ratio
~~~

A burn rate of 1 means consuming the budget at exactly the pace that exhausts it at the end of the SLO window. A burn rate of 10 means consuming it 10 times faster.

A multi-window approach:

- A short window to detect severe ongoing incidents quickly.
- A longer window to confirm sustained impact and avoid paging on spikes.
- Ticket alerts when budget drains slowly yet steadily.

For example, the Google SRE Workbook provides illustrative burn-rate thresholds for pages and tickets. Do not copy these thresholds mechanically; adjust them to your service's traffic, SLOs, and on-call capacity.

## 12. Custom ObservationConvention

Spring for GraphQL allows customizing observation metadata through conventions:

- `ExecutionRequestObservationConvention`
- `DataFetcherObservationConvention`
- `DataLoaderObservationConvention`

Conventions are appropriate when you need to add a few finite low-cardinality KeyValues or normalize error types. In Spring Boot applications, registering the convention as a bean is the preferred configuration approach.

For example, you can add `graphql.client.type` with a fixed set of values:

~~~java
public class ClientTypeExecutionConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("graphql.client.type", "web"));
    }
}
~~~

The hardcoded `"web"` example merely illustrates how to extend the convention. If client type varies per request, extract it from verified metadata and restrict it to a bounded set such as `web`, `ios`, `android`, `service`.

Key imports for the example:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
~~~

In a Spring Boot application, expose this convention instance as a bean matching the API of your version so auto-configuration picks it up. Do not manually add a second `GraphQlObservationInstrumentation` if Boot already registers the default instrumentation.

Do not add operation names, execution IDs, raw queries, or tenant IDs to low-cardinality KeyValues. If you need those values for finding traces, add them to high-cardinality metadata per your version's convention API.

### Normalizing error types

By default, `graphql.error.type` uses the error's class name. If an application has many unstable or dynamically generated exception classes, you can map them into fixed buckets such as:

- `VALIDATION`
- `NOT_FOUND`
- `AUTHORIZATION`
- `DEPENDENCY`
- `INTERNAL`

Finite error buckets make dashboards and alerts easier to read. However, do not lose necessary detail in logs/traces.

## 13. Additional business metrics

Default observations do not measure everything a product cares about. You can add custom metrics for:

- Query complexity/cost after validation.
- Number of nodes or aliases in an operation.
- Resolver cache hit ratio.
- Requests rejected by query depth/complexity limits.
- Actual batch sizes if a histogram is needed.
- Dropped subscription events or queue overflows.
- Dependency retry rates.

Example measuring query cost with `DistributionSummary`:

~~~java
@Component
public class GraphQlQueryCostMetrics {

    private final DistributionSummary queryCost;

    public GraphQlQueryCostMetrics(MeterRegistry registry) {
        this.queryCost = DistributionSummary.builder("graphql.query.cost")
                .description("Estimated GraphQL query cost")
                .baseUnit("cost")
                .register(registry);
    }

    public void record(int cost) {
        queryCost.record(cost);
    }
}
~~~

Record cost after computing query cost and before execution, or within appropriate instrumentation. Do not attach raw query text as a tag. If you need to distinguish operation classes, use fixed buckets such as `simple`, `standard`, `expensive`.

Custom metrics must have clear owners, definitions, and purposes. Avoid creating a separate metric for every field or every operation name.

## 14. Traces and correlation

The `graphql.request` observation can create spans and record GraphQL errors as span events. `DataFetcher` and `DataLoader` observations can create child spans to help locate bottlenecks.

Information commonly useful in traces:

- Operation type and operation name.
- Execution ID.
- Field path.
- DataLoader name and batch size.
- Controlled error type and error message.
- Trace ID used to link with transport and downstream dependencies.

Execution ID is high-cardinality; use it to locate a specific request in traces/logs, never as a metric label.

### Exemplars

With Prometheus histograms, exemplars can link a bucket sample to a trace ID. When p95 rises, the dashboard can open a representative trace for investigation.

Micrometer and Spring Boot support exemplars when tracing context is configured appropriately. Configure both the exporter and Prometheus/OpenMetrics for your version; do not assume exemplars appear automatically simply by enabling histograms.

### Sampling

Not every request needs a detailed trace. Use appropriate sampling:

- Keep a baseline trace rate for trend analysis.
- Increase retention likelihood for traces with errors or high latency if your tracing backend supports tail sampling.
- Keep execution IDs/trace IDs in traces/logs; do not turn them into metric tags.
- Protect sensitive data in GraphQL documents, variables, and span attributes.

## 15. Testing metrics and alerts

Monitoring is also part of application quality. An empty dashboard may mean zero traffic, yet it can also mean missing instrumentation.

### Testing observations

In integration tests:

1. Create a GraphQL source with an `ObservationRegistry` and appropriate meter handler.
2. Send a successful query.
3. Send a query that triggers a DataFetcher error.
4. Send a query using `@BatchMapping`.
5. Assert that Timers and tags were recorded.

With Spring Boot, you can test the Actuator endpoint in tests or use `SimpleMeterRegistry`/test registries. Do not rely on Prometheus-normalized names when querying the Actuator metrics endpoint; the endpoint uses original Micrometer meter names.

Example integration test using `GraphQlTester` and `MeterRegistry`:

~~~java
@SpringBootTest
class GraphQlObservationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsGraphQlRequestTimer() {
        graphQlTester.document("""
                query {
                    books {
                        id
                    }
                }
                """)
                .execute();

        Timer timer = meterRegistry.find("graphql.request")
                .tag("graphql.operation.type", "query")
                .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isGreaterThan(0);
    }
}
~~~

This test assumes the schema has a `books` query and the application has GraphQL Observation enabled. If the test environment uses a different registry or custom observation handler, adjust meter lookup accordingly.

### Verifying Prometheus scraping

- `/actuator/prometheus` returns exposition format.
- The Prometheus target state is `UP`.
- `_count` and `_sum` series appear after requests run.
- `_bucket` series appear if histograms are enabled.
- Tags such as `graphql_operation_type` and `graphql_outcome` have expected values.

### Testing alert rules

Prometheus provides `promtool test rules` to test alert expressions against simulated sample series. Include tests for:

- Error rate exceeding the threshold.
- Low traffic not triggering false alerts.
- Latency returning to normal resolving the alert.
- Alerts carrying the right labels and annotations.
- Missing series or scrape failures handled per policy.

Do not check YAML syntax alone; test both PromQL logic and `for` durations.

## 16. Runbooks when GraphQL alerts fire

### When GraphQLInternalErrorRatioHigh fires

1. Open the GraphQL request dashboard and identify the affected operation type.
2. Compare HTTP 5xx, `graphql.outcome`, and DataFetcher errors.
3. Inspect traces to locate the failing field path or dependency.
4. Check database pools, remote HTTP clients, and executors.
5. Determine whether errors began after a deployment or schema change.
6. Shed load, roll back, or disable the failing dependency path if an approved mitigation exists.
7. Confirm the error ratio drops and users recover.

### When GraphQLP95LatencyHigh fires

1. Compare request p95 against DataFetcher p95.
2. Identify the slowest field/resolver from traces.
3. Verify whether DataLoader is batching properly or still causing N+1 queries.
4. Check database query plans, connection pools, and lock waits.
5. Check dependency latency and retries.
6. Compare against traffic volume, payload size, and operation mix.
7. Confirm p95 returns within SLO after remediation.

### When DataLoader errors increase

1. Identify `graphql.loader.name`.
2. Inspect `graphql.error.type` and traces of the batch loader.
3. Verify batch key mapping and result ordering.
4. Check the underlying database/service dependency.
5. Check batch sizes and queue/backpressure if custom metrics exist.
6. Verify timeout, retry, and cancellation behavior.

## 17. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Missing `graphql.request` | Missing `ObservationRegistry` or instrumentation | Check Boot auto-configuration and GraphQL source |
| Request metrics exist, yet no DataFetcher metrics | Only property fetchers used or missing instrumentation | Add non-trivial resolvers and verify instrumentation |
| Missing DataLoader metrics | Query does not trigger loader or instrumentation is disabled | Check `@BatchMapping` and DataLoader registration |
| Mistaking `REQUEST_ERROR` for HTTP 400 | Confusing observation outcome with transport status | Distinguish GraphQL outcome from HTTP status |
| Error ratio stays high | Counting all GraphQL errors as server outages | Separate client, domain, and internal errors |
| p95 does not display | Histograms not enabled or zero traffic | Configure histograms and inspect buckets |
| Metric backend has too many series | Execution ID, operation name, or tenant ID used as tags | Move high-cardinality data to traces/logs |
| Dashboard shows only overall latency | Missing DataFetcher/DataLoader observations | Enable instrumentation and add resolver/loader panels |
| Batch size cannot be queried | `graphql.loader.size` is a high-cardinality key | Create a dedicated `DistributionSummary` if a metric is needed |
| Flapping alerts | Missing `for`/`keep_firing_for` or overly sensitive threshold | Use appropriate windows and slack |
| Too many pages | Alerting per dependency/field instead of symptom | Page at the request layer; ticket at the component layer |
| Metrics endpoint publicly accessible | Actuator exposed without security | Restrict network access and permissions |
| Traces missing parent span | Transport or context propagation not configured | Check HTTP/WebFlux transport instrumentation |
| Alerts lack traces for investigation | Sampling too low or exemplars unconfigured | Adjust sampling and exemplars |

## 18. Operational principles

- Enable Micrometer Observation for GraphQL requests, DataFetchers, and DataLoaders.
- Use Actuator to inspect meters and the Prometheus endpoint for scraping.
- Monitor transport, GraphQL requests, DataFetchers, DataLoaders, and infrastructure together.
- Use histograms when percentiles must be aggregated across multiple instances.
- Choose SLIs/SLOs based on user experience and realistic error classification.
- Never treat every `REQUEST_ERROR` as a server failure.
- Use low-cardinality tags for metrics; keep execution IDs and field paths in traces/logs.
- Alert on symptoms with `for` durations, severities, and runbooks.
- Use dashboards to drill down rather than paging for every resolver.
- Test instrumentation, scrape targets, and alert rules.
- Secure Actuator endpoints and sensitive GraphQL data.
- Add custom metrics only when there is a specific operational question to answer.

## 19. Practical exercise

Set up monitoring for a library Spring for GraphQL API:

1. Add Spring Boot Actuator and the Prometheus registry.
2. Verify `ObservationRegistry` and `GraphQlObservationInstrumentation` are active.
3. Send a query with `@SchemaMapping` and a query with `@BatchMapping`.
4. Check the three meters: `graphql.request`, `graphql.datafetcher`, and `graphql.dataloader`.
5. Expose `/actuator/prometheus` on an internal network.
6. Configure Prometheus to scrape the application.
7. Enable histograms for `graphql.request` and `graphql.datafetcher`.
8. Write PromQL for request rate, p95, and internal error ratio.
9. Build a Grafana dashboard with request, error, resolver, loader, and infrastructure panels.
10. Write alert rules with `for`, severity, and runbook URL.
11. Simulate a DataFetcher exception and verify alerts/traces reflect it accurately.
12. Create a custom metric for query cost or batch size if the dashboard needs it.
13. Verify metric labels do not contain execution IDs, user IDs, or raw queries.
14. Use `promtool test rules` to validate alerts.
15. Write runbooks for the two most critical alerts.

After completing this exercise, you should be able to explain how GraphQL observations become metrics/traces, how to distinguish request outcomes from HTTP statuses, and how to design alerts that avoid noisy pages for the on-call team.

## 20. References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/observation/GraphQlObservationAutoConfiguration.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Alerting Practices](https://prometheus.io/docs/practices/alerting/)
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

Metrics show how the system is behaving broadly; traces and logs explain a specific request. When these three signals are tied to SLOs and runbooks, operations teams can detect incidents early and remediate the exact component causing impact.
