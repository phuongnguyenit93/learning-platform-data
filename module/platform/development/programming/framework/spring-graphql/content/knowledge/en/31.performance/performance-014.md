# Measuring per-field latency in Spring for GraphQL

A GraphQL request can resolve many fields, call multiple services, and query multiple data sources. When a response is slow, looking only at total request duration does not reveal which field is consuming most of the time. Spring for GraphQL integrates Micrometer Observation to measure the execution duration of each non-trivial DataFetcher using the `graphql.datafetcher` observation.

This observation provides timers and trace spans tied to the field being resolved. With default tags such as `graphql.field.name`, `graphql.outcome`, and `graphql.error.type`, you can aggregate which fields are frequently slow or failing. In traces, `graphql.field.path` pinpoints the field's position within the object graph of a specific request.

## 1. Why measure per-field latency?

Suppose a client sends a query:

```graphql
query BookDetails($id: ID!) {
    bookById(id: $id) {
        id
        title
        author {
            id
            name
            profile {
                biography
            }
        }
        reviews {
            rating
            comment
        }
    }
}
```

This request may invoke multiple DataFetchers:

- `bookById` loads book details.
- `author` loads the book's author.
- `profile` loads the author's profile.
- `reviews` loads the list of reviews.

If the total request takes 900 ms, it is unclear which part is slow. Perhaps `bookById` took 30 ms, `author` took 40 ms, `profile` took 760 ms, and `reviews` took 70 ms. Measuring latency per field lets you pinpoint the exact resolver to investigate.

Common questions include:

- Which fields have high p95/p99 latency?
- Which fields frequently return errors?
- Is a field slow on all requests or only on a specific branch of the object graph?
- Does the latency sit inside the resolver, batch loader, database, or remote service?
- After optimizing a resolver, how do field and request latencies change?

## 2. Distinguishing request latency from field latency

Spring for GraphQL provides two observations with distinct roles:

| Observation | Scope | Purpose |
|---|---|---|
| `graphql.request` | Entire GraphQL execution request | Measures overall request processing time and outcome. |
| `graphql.datafetcher` | A single non-trivial DataFetcher operation | Measures the resolution time of an individual field. |

One request can produce a single `graphql.request` observation and many `graphql.datafetcher` observations.

```text
HTTP server request
       |
       v
  graphql.request
       |
       +---- graphql.datafetcher: bookById
       |
       +---- graphql.datafetcher: author
       |
       +---- graphql.datafetcher: profile
       |
       +---- graphql.datafetcher: reviews
       |
       v
  GraphQL response
```

Do not sum the durations of all fields to estimate request latency. GraphQL can execute independent fields concurrently, so their intervals overlap. Request latency reflects total execution duration, while field latency reflects individual fetch operations.

The request observation also does not necessarily cover full client-to-client network time. Transports such as HTTP may have their own observations. When investigating end-to-end latency, examine transport spans, GraphQL request spans, and downstream spans together.

## 3. When is `graphql.datafetcher` created?

Spring for GraphQL creates DataFetcher observations for fetching operations considered non-trivial. Examples:

- Methods using `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` calling services/repositories.
- Directly registered DataFetchers performing data loading work.
- Data fetching operations with custom logic worth measuring.

Simple property fetching from a Java object, such as GraphQL Java reading `book.title` directly via `PropertyDataFetcher`, is treated as trivial and does not generate a separate `graphql.datafetcher` observation.

This avoids emitting excessive observations for fields that merely read in-memory properties. If a field calls a database or remote service, map it with a DataFetcher/annotated controller so that work becomes observable.

## 4. Default metadata of DataFetcher observations

Spring for GraphQL uses `DefaultDataFetcherObservationConvention`, backed by `DataFetcherObservationContext`.

Default keys:

| Key | Cardinality | Meaning |
|---|---|---|
| `graphql.field.name` | Low | Name of the field being resolved. |
| `graphql.outcome` | Low | Outcome `SUCCESS` or `ERROR`. |
| `graphql.error.type` | Low | Class name of the data fetching error if present. |
| `graphql.field.path` | High | Field path in GraphQL execution. |

For example, an `author` field might have metadata:

```text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: SUCCESS
graphql.field.path: /bookById/author
```

`graphql.field.name` is suitable for grouping metrics by field. `graphql.field.path` can vary by branch and list index, making it high cardinality and suitable only for tracing.

## 5. Low cardinality vs high cardinality

Low-cardinality keys have a bounded set of values and can be used as metric tags. High-cardinality keys can produce huge numbers of distinct values and belong in traces.

For DataFetcher observations:

- `graphql.field.name`, `graphql.outcome`, and `graphql.error.type` are low cardinality.
- `graphql.field.path` is high cardinality.

Never add values such as user IDs, tenant IDs, emails, raw GraphQL variables, entity IDs, or query text to low-cardinality metrics. If a tag generates millions of combinations, the metrics system suffers from time-series explosion, driving up storage and query costs.

When hunting down a slow field in a specific request, use traces and field paths. When tracking p95 field latency across thousands of requests, use metrics tagged with field name and a bounded set of labels.

## 6. Configuring observability with Spring Boot

With Spring Boot, GraphQL observation instrumentation is auto-configured when the application has an `ObservationRegistry` and the required dependencies. Spring Boot registers `GraphQlObservationInstrumentation` on the GraphQL source and uses the default conventions unless custom convention beans are provided.

Illustrative Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot manages compatible versions of Spring for GraphQL and Micrometer. `micrometer-registry-prometheus` is needed only when exporting metrics to Prometheus; choose a different registry if your monitoring stack uses another system.

Checklist to verify:

1. Application has an `ObservationRegistry`.
2. GraphQL observation auto-configuration is active.
3. `GraphQlObservationInstrumentation` is present in the GraphQL source.
4. Meter registry and observation handlers are configured to export metrics.
5. Queries actually invoke non-trivial DataFetchers.

Observations are published only when an `ObservationRegistry` is configured. In Spring Boot apps with Actuator, these components are typically auto-configured.

## 7. Configuring Actuator endpoints

To inspect metrics and let Prometheus scrape them, expose the needed endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

In production, metrics endpoints must be protected by security policies and exposed only to authorized monitoring systems.

After the application serves GraphQL requests, list available meters:

```text
GET /actuator/metrics
```

Inspect the per-field timer:

```text
GET /actuator/metrics/graphql.datafetcher
```

Filter for a specific field:

```text
GET /actuator/metrics/graphql.datafetcher?tag=graphql.field.name:bookById
```

Filter for successful field executions:

```text
GET /actuator/metrics/graphql.datafetcher?tag=graphql.field.name:bookById&tag=graphql.outcome:SUCCESS
```

The meter name in Actuator is `graphql.datafetcher`. Export registries may normalize this name to match their naming conventions; for instance, Prometheus converts dots to underscores.

## 8. Reading per-field timers

The `graphql.datafetcher` observation is recorded by Micrometer as a timer when the observation finishes. A timer provides:

- `count`: how many times the field executed.
- `totalTime`: total duration across executions.
- `max`: maximum duration in the supported reporting window.
- Percentiles or histogram buckets if configured and supported by the registry.

Example metrics for a field:

| Measurement | Illustrative value | Meaning |
|---|---|---|
| Count | 12,000 | The field executed 12,000 times in the measurement window. |
| Total time | 720 seconds | Cumulative fetch duration. |
| Average | 60 ms | Mean duration per fetch. |
| p95 | 180 ms | 95% of fetches did not exceed 180 ms. |
| p99 | 420 ms | 99% of fetches did not exceed 420 ms. |

Never rely on averages alone. A handful of very slow requests can be masked by many fast requests. p95/p99 values are far more useful for assessing real user experience and setting SLOs.

## 9. Enabling percentile histograms and SLO boundaries

Spring Boot lets you configure timer distributions by meter name. For example, enabling histograms for `graphql.datafetcher` and setting SLO boundaries:

```properties
management.metrics.distribution.percentiles-histogram.graphql.datafetcher=true
management.metrics.distribution.slo.graphql.datafetcher=50ms,100ms,250ms
```

Histograms let monitoring systems aggregate percentiles accurately across multiple instances. SLO boundaries add buckets at specific latency thresholds your application cares about.

If you configure only `percentiles`, Micrometer computes percentiles locally per meter ID inside each process; those percentiles cannot be accurately aggregated across instances. With Prometheus, prefer percentile histograms so you can compute `histogram_quantile` over aggregated buckets.

Histograms increase time-series count. Enable them only on meters needing distribution analysis and keep tag cardinality low.

## 10. Querying percentiles with Prometheus

With Prometheus timers and percentile histograms enabled, compute p95 by field name:

```promql
histogram_quantile(
  0.95,
  sum by (le, graphql_field_name) (
    rate(graphql_datafetcher_seconds_bucket[5m])
  )
)
```

Prometheus naming conventions typically convert `graphql.datafetcher` to `graphql_datafetcher` and `graphql.field.name` to `graphql_field_name`. Exact names depend on your registry/exporter and naming convention settings.

Compute average latency per field:

```promql
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_sum[5m])
)
/
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_count[5m])
)
```

When deploying, verify actual series names in Prometheus before adding queries to dashboards. If histograms are not enabled, `_bucket` series will not be exported.

## 11. Using traces to find slow fields in a request

Metrics reveal overall trends. Traces help investigate a specific request.

A trace might have this structure:

```text
HTTP server request
  |
  +-- graphql.request
        |
        +-- graphql.datafetcher: bookById
        |
        +-- graphql.datafetcher: author
        |
        +-- graphql.datafetcher: profile
        |      |
        |      +-- database query
        |
        +-- graphql.datafetcher: reviews
```

In the trace, inspect:

- Field name to identify the resolver.
- Field path to identify the branch of the object graph.
- Span duration to see how long the field took.
- Error events/exceptions to see where a resolver failed.
- Child database or HTTP client spans to pinpoint slow dependencies.

To correlate GraphQL traces with HTTP requests, ensure proper transport instrumentation and context propagation are configured. Spring Framework provides HTTP observation instrumentation; tracing exporters such as OTLP forward spans to your observability backend.

## 12. Example schema and controller with measurable fields

SDL:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Illustrative models:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Controller:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

In this example, `bookById` and `author` are DataFetchers with custom logic, so they are measured by `graphql.datafetcher`. If `Book.author` were simply a Java property read directly without `@SchemaMapping`, the default property fetcher would not create a separate observation.

When metrics show `author` has high p95 latency, traces can reveal whether the time went into `authorService.findById` or a child database/HTTP span. If queries select many books, also check whether this field is invoked repeatedly per parent and should be migrated to `@BatchMapping` or DataLoader.

## 13. Customizing `DataFetcherObservationConvention`

The default convention uses field name, outcome, and error type as low-cardinality metadata; field path is high-cardinality metadata.

If you need to group fields by domain, supply a `DataFetcherObservationConvention` bean. For example, adding a `graphql.field.group` label with a fixed set of values:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    DataFetcherObservationContext context) {

                String fieldName = context.getEnvironment()
                    .getFieldDefinition()
                    .getName();

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.field.group", fieldGroup(fieldName)));
            }
        };
    }

    private String fieldGroup(String fieldName) {
        return switch (fieldName) {
            case "bookById", "books" -> "catalog";
            case "author", "profile" -> "identity";
            case "reviews" -> "feedback";
            default -> "other";
        };
    }
}
```

Spring Boot automatically detects convention beans and passes them into `GraphQlObservationInstrumentation`. Extending `DefaultDataFetcherObservationConvention` preserves all default keys and merely adds a new tag.

The values `catalog`, `identity`, `feedback`, and `other` form a finite set, making them safe for low cardinality. Placing raw field paths or IDs into this tag would cause time series to grow rapidly.

## 14. When to distinguish identical field names across types?

`graphql.field.name` contains only the field name. A schema may have multiple types declaring `id`, `name`, `status`, or `createdAt`. Grouping metrics solely by field name merges fields with the same name together.

If you need to tell them apart, add a parent type or field group tag using a custom convention. Example:

```java
import graphql.schema.GraphQLNamedType;
import graphql.schema.GraphQLType;

@Override
public KeyValues getLowCardinalityKeyValues(DataFetcherObservationContext context) {
    GraphQLType type = context.getEnvironment().getParentType();
    String parentType = (type instanceof GraphQLNamedType namedType)
        ? namedType.getName() : "unknown";

    return super.getLowCardinalityKeyValues(context)
        .and(KeyValue.of("graphql.parent.type", parentType));
}
```

This extends the convention bean from the previous section. `DataFetcherObservationContext.getEnvironment()` provides the `DataFetchingEnvironment` to inspect the field definition, parent type, and execution metadata.

Parent types are bounded by the schema and therefore have finite cardinality. Even so, keep your schema controlled and never emit dynamically generated type names from user data as metric tags.

When you need exact details for a single invocation, `graphql.field.path` in traces already provides granular context without bloating metrics.

## 15. Distinguishing field latency from DataLoader latency

When fields use `@BatchMapping` or manually registered DataLoaders, inspect both observation layers:

| Observation | What does it measure? | When used |
|---|---|---|
| `graphql.datafetcher` | Non-trivial DataFetchers | Resolvers such as query roots or field mappings. |
| `graphql.dataloader` | Batch loader executions | `@BatchMapping` and manual DataLoaders. |

A field resolved via a batch loader can have its own `graphql.dataloader` observation. Do not add durations from both observations as two independent workloads if they overlap the same resolution flow.

When field latency is high, determine whether the resolver calls the backend once per parent. If N+1 occurs, switching to batch loading can reduce round trips. Afterward, compare field timing, DataLoader timing, and database metrics together.

## 16. Analyzing errors per field

DataFetcher observations include `graphql.outcome` with values `SUCCESS` or `ERROR`. On failure, `graphql.error.type` reports the class name of the data fetching error.

Example:

```text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: ERROR
graphql.error.type: AuthorServiceException
```

Metrics show which fields fail most often, while traces/logs reveal the specific request and root cause. Aggregate by error type rather than adding free-form exception messages into metric tags.

Even when exceptions are mapped to GraphQL errors via `DataFetcherExceptionResolver`, verify how the application handles and classifies errors during execution. Never expose sensitive details or stack traces in GraphQL responses just for observability convenience.

## 17. Testing field observations with `MeterRegistry`

You can write an integration test executing a GraphQL query and verifying that the field's timer was recorded. Example with Spring Boot:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlFieldObservationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsLatencyForBookById() {
        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");

        Timer timer = meterRegistry.find("graphql.datafetcher")
            .tag("graphql.field.name", "bookById")
            .tag("graphql.outcome", "SUCCESS")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isPositive();
    }
}
```

This example assumes the application has a schema, a resolver returning `book-1`, Actuator/Micrometer observation configured, and `@AutoConfigureHttpGraphQlTester` matching your Spring Boot version. Import `MeterRegistry`, `Timer`, and the corresponding assertion library in the test.

The imports above target Spring Boot 3.x. In Spring Boot 4.x, the test auto-configuration package moved to `org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester`.

Do not assert exact duration numbers because timings vary by test machine and system load. Assert that the timer exists, its count incremented, and its tags match. If tests share a registry across runs, reset or isolate contexts to prevent stale data from producing false passes.

## 18. Workflow for investigating slow fields

When dashboards show p95 latency climbing for field `profile`, investigate in this order:

1. Filter `graphql.datafetcher` by `graphql.field.name=profile` and `graphql.outcome=SUCCESS` to inspect successful execution latencies.
2. Check `graphql.outcome=ERROR` and `graphql.error.type` to see whether errors increased at the same time.
3. Open traces of slow requests to inspect `graphql.field.path` and child spans.
4. Inspect database or HTTP client spans to pinpoint slow dependencies.
5. If the field sits inside a large list, check fetch counts and possible N+1 behavior.
6. Consider batch loading, pagination, projections, or appropriate caching.
7. Deploy the change and compare p50/p95/p99 before and after.

Example diagnostic table:

| Symptom | Where to investigate |
|---|---|
| Field p95 rises and database span also rises | Query plan, indexes, locks, connection pool. |
| Field p95 rises while database span is normal | Mapping, service logic, remote calls, or CPU. |
| Field count scales with parent object count | Check for N+1 and `@BatchMapping`. |
| Field errors increase | Exception resolvers, dependency failures, timeouts. |
| Request is slow while all fields are fast | Parsing/validation, transport, serialization, or scheduling. |

## 19. Notes on subscriptions and repeatedly resolved fields

A Subscription is a long-lived event stream. DataFetcher observations measure individual fetching operations wrapped by GraphQL instrumentation; they do not automatically measure wait intervals between events, emission rates, or client delivery latency.

To observe subscriptions thoroughly, combine:

- `graphql.request` for execution/operation tracking as supported by the transport.
- DataFetcher observations for field fetching operations.
- `graphql.dataloader` if the subscription uses batch loading.
- Transport metrics and custom metrics for event counts, inter-event gaps, active streams, and cancellations.

A single field can be resolved multiple times within one request, such as inside a list of parent objects. Metrics keyed by field name aggregate across invocations; trace paths distinguish exact locations in the object graph.

## 20. Common pitfalls

**Looking only at `graphql.request` to find slow fields.** The request timer only gives total duration; you need `graphql.datafetcher` to analyze individual resolvers.

**Assuming every field generates a DataFetcher observation.** Simple property fetchers on Java objects are trivial and are not measured individually.

**Using `graphql.field.path` as a metric tag.** This is a high-cardinality key meant for traces. Use `graphql.field.name` or bounded field groups for metrics.

**Summing all field durations to derive request duration.** Fields can run concurrently and their durations overlap.

**Confusing DataFetcher latency with SQL latency.** Field observations cover work inside the DataFetcher; use database instrumentation to isolate query and connection times.

**Missing `ObservationRegistry` configuration.** Without an active registry/instrumentation, no `graphql.datafetcher` observations are emitted.

**Overriding default tags when customizing conventions.** When extending the default convention, call `super.getLowCardinalityKeyValues(context)` and append tags.

**Enabling histograms on every meter.** Histograms create extra time series. Enable them only for meters needing percentiles or SLOs.

**Putting user IDs, tenant IDs, or query text in metric tags.** Cardinality and data leakage risks spike. Use only labels with finite value sets.

## Conclusion

Measuring per-field latency in Spring for GraphQL relies on the Micrometer observation `graphql.datafetcher`, created for non-trivial DataFetchers. Default tags `graphql.field.name`, `graphql.outcome`, and `graphql.error.type` fit metrics, while `graphql.field.path` is high cardinality and suited for tracing. Spring Boot auto-configures `GraphQlObservationInstrumentation` when an `ObservationRegistry` is present; Actuator exposes endpoints to inspect timers, and Micrometer supports percentile histograms and SLOs. When investigating slow fields, combine request timers, field timers, trace spans, DataLoader observations, and database metrics to isolate the exact layer causing latency.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL API — `GraphQlObservationInstrumentation`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL API — `DataFetcherObservationContext`](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DataFetcherObservationContext.html)
- [Spring for GraphQL API — `DataFetcherObservationConvention`](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DataFetcherObservationConvention.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot 3.5 — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
