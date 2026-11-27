# graphql.outcome in Spring for GraphQL

`graphql.outcome` is a low-cardinality key of Micrometer Observation that indicates the result of GraphQL processing. Spring for GraphQL records this key across three scopes: the entire GraphQL request, each non-trivial data fetcher, and each executed DataLoader batch. As a result, dashboards can distinguish successful requests, requests with GraphQL errors, and internal errors, while also observing which field or batch loader fails frequently.

The key point to remember is that `graphql.outcome` describes the result at the GraphQL layer. It is not synonymous with HTTP status. An HTTP response can return `200 OK` while the GraphQL response still contains `errors`, causing the request observation to carry an outcome of `REQUEST_ERROR` or `INTERNAL_ERROR`.

## 1. Observations and graphql.outcome

Spring for GraphQL integrates Micrometer Observation to record metrics and traces. An Observation can produce a timer metric, a trace span, or both, depending on the `ObservationRegistry` configuration and registered handlers.

`graphql.outcome` is contributed by Spring for GraphQL's default observation conventions. Because this key has a finite set of values, it can be used as a metric tag to group requests by outcome.

Main observations:

| Observation name | Scope | When recorded |
| --- | --- | --- |
| `graphql.request` | Entire GraphQL execution request | Every processed GraphQL request |
| `graphql.datafetcher` | A data fetcher | Non-trivial data fetching operations |
| `graphql.dataloader` | A DataLoader batch invocation | `@BatchMapping` and manually registered DataLoaders |

One request can create multiple `graphql.datafetcher` and `graphql.dataloader` observations. Therefore, when analyzing errors, look at both the request outcome and the field/batch outcomes.

## 2. Three Values of graphql.outcome at the Request Level

For the `graphql.request` observation, Spring for GraphQL uses three values:

| Value | When assigned |
| --- | --- |
| `SUCCESS` | A valid GraphQL response is created and contains no errors |
| `REQUEST_ERROR` | The request cannot be parsed, or the response has errors with none belonging to `ErrorType.INTERNAL_ERROR` |
| `INTERNAL_ERROR` | A valid GraphQL response cannot be created, or the response contains at least one error belonging to `ErrorType.INTERNAL_ERROR` |

The classification rules can be visualized as follows:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B{Valid GraphQL response?}
    B -->|No| C[INTERNAL_ERROR]
    B -->|Yes| D{Response has errors?}
    D -->|No| E[SUCCESS]
    D -->|Yes| F{Any error type INTERNAL_ERROR?}
    F -->|Yes| C
    F -->|No| G[REQUEST_ERROR]
~~~

`REQUEST_ERROR` is not limited to syntax or validation errors before resolvers run. An execution can return partial data and errors; if none of the errors are `INTERNAL_ERROR`, the outcome for the whole request is still `REQUEST_ERROR`.

Conversely, having at least one `INTERNAL_ERROR` classifies the request outcome as `INTERNAL_ERROR`, even if other fields returned data successfully.

## 3. Outcome Classification Examples

Suppose a schema has a query to fetch a book and its author:

~~~graphql
type Query {
    book(id: ID!): Book
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
~~~

Possible scenarios:

| Scenario | GraphQL response | `graphql.outcome` |
| --- | --- | --- |
| Valid query, all fields resolve successfully | Has `data`, no `errors` | `SUCCESS` |
| Malformed document syntax | No execution data, response has parse error | `REQUEST_ERROR` |
| Input fails GraphQL validation | Request rejected before resolvers run | `REQUEST_ERROR` |
| Resolver returns a business error classified as `NOT_FOUND` | May have partial data and error | `REQUEST_ERROR` |
| Resolver returns an error classified as `FORBIDDEN` or `BAD_REQUEST` | May have partial data and error | `REQUEST_ERROR` |
| Resolver throws an error mapped to `INTERNAL_ERROR` | Response contains internal error | `INTERNAL_ERROR` |
| Cannot create a valid GraphQL response | No valid GraphQL response | `INTERNAL_ERROR` |

Example where the author resolver fails while the book field succeeds:

~~~json
{
    "data": {
        "book": {
            "id": "book-1",
            "title": "Spring GraphQL",
            "author": null
        }
    },
    "errors": [
        {
            "message": "Author is not available",
            "path": ["book", "author"],
            "extensions": {
                "classification": "NOT_FOUND"
            }
        }
    ]
}
~~~

If the error is mapped to `ErrorType.NOT_FOUND`, the request observation carries `REQUEST_ERROR`. If the error is mapped to `ErrorType.INTERNAL_ERROR`, the request observation carries `INTERNAL_ERROR`. Check the actual classification produced by your exception resolver rather than inferring the outcome solely from the message text.

Example exception handler classifying business errors:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class BookGraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book was not found")
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleUnexpected(
            IllegalStateException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("An unexpected error occurred")
                .build();
    }
}
~~~

The first handler creates a GraphQL error in the `NOT_FOUND` business category, so the request outcome is `REQUEST_ERROR`. The second handler creates an `INTERNAL_ERROR`, making the request outcome `INTERNAL_ERROR`. In production applications, classify exceptions intentionally and do not return raw exception messages verbatim if they could reveal internal details.

## 4. Distinguishing Request Outcome from Data Fetcher Outcome

The `graphql.datafetcher` observation measures an individual field resolution operation. At this scope, `graphql.outcome` has only two values:

| Value | Meaning |
| --- | --- |
| `SUCCESS` | The data fetcher completed without throwing an error |
| `ERROR` | The data fetcher threw an error |

For example, a request has three field resolvers:

- `Query.book` succeeds.
- `Book.author` fails.
- `Book.reviews` succeeds.

The request may have one `graphql.request` observation with `REQUEST_ERROR`, while the data fetcher observations have outcomes `SUCCESS`, `ERROR`, and `SUCCESS`, respectively.

Do not use a single field's outcome to deduce the entire request's outcome. The request outcome is derived from the overall GraphQL result and error classification.

## 5. Distinguishing DataLoader Outcome

The `graphql.dataloader` observation tracks each batch loader execution. The `graphql.outcome` key has two values:

- `SUCCESS`: the batch loader completed successfully.
- `ERROR`: the batch loader encountered an error.

This helps identify a failing batch loader even when some fields in the GraphQL response still resolve successfully.

Examples:

| Request | DataFetcher | DataLoader | Meaning |
| --- | --- | --- | --- |
| `SUCCESS` | `SUCCESS` | `SUCCESS` | Request, field, and batch all succeeded |
| `REQUEST_ERROR` | `ERROR` | `ERROR` | A batch failed and produced a non-internal GraphQL error |
| `INTERNAL_ERROR` | `ERROR` | `ERROR` | A batch failed and the error was classified as internal |
| `REQUEST_ERROR` | `ERROR` | None | Error occurred in a data fetcher not using DataLoader |

Not every field has a DataLoader observation. This observation is only created for `@BatchMapping` or registered and instrumented DataLoaders.

## 6. Low Cardinality and High Cardinality

Micrometer divides keys into two groups:

| Key type | Included in | Examples |
| --- | --- | --- |
| Low cardinality | Metrics and traces | `graphql.outcome`, `graphql.operation.type`, `graphql.field.name` |
| High cardinality | Traces, not used as metric tags | `graphql.execution.id`, `graphql.operation.name`, `graphql.field.path` |

Low-cardinality keys have a finite or bounded set of values. This keeps the number of time series in the metrics system from growing uncontrollably.

High-cardinality keys can take a very large number of distinct values. Examples include client-supplied operation names, execution IDs, or field paths containing list indices. They are useful when investigating a specific trace, but unsuitable as metric tags.

Do not convert `graphql.operation.name`, user IDs, request IDs, or field paths into low-cardinality tags just to make dashboard queries easier. Doing so can generate thousands or millions of time series.

## 7. Default Keys of graphql.request

The `graphql.request` observation uses `DefaultExecutionRequestObservationConvention`.

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.operation.type` | Low | `query`, `mutation`, `subscription`, or `operation` when document cannot be parsed |
| `graphql.outcome` | Low | Request outcome: `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High | GraphQL execution ID |
| `graphql.operation.name` | High | Operation name sent by the client |

Operation name is set by the client and can vary per query. If you need to group metrics by operation kind, use `graphql.operation.type` instead of `graphql.operation.name`.

## 8. Default Keys of graphql.datafetcher

The `graphql.datafetcher` observation is only created for non-trivial data fetching operations. Directly reading a property on a Java object is usually considered trivial and does not create a dedicated observation.

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.field.name` | Low | Name of the field being resolved |
| `graphql.outcome` | Low | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Class name of the data fetching error, if any |
| `graphql.field.path` | High | Path to the field in the response, e.g. `/bookById` |

`graphql.field.name` is useful for aggregating which fields are frequently slow or failing. `graphql.field.path` is more useful when inspecting the trace of a specific request.

## 9. Default Keys of graphql.dataloader

The `graphql.dataloader` observation tracks DataLoader invocations:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.loader.name` | Low | DataLoader name |
| `graphql.outcome` | Low | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Class name of the batch error, if any |
| `graphql.loader.size` | High | Number of elements loaded in the batch |

`graphql.loader.name` helps compare different loaders. `graphql.loader.size` helps investigate oversized or unusually small batches in traces.

## 10. Enabling GraphQL Observations with Spring Boot Actuator

With Spring Boot 3.x, GraphQL observation auto-configuration is provided via Actuator. When `ObservationRegistry` is present, Boot registers `GraphQlObservationInstrumentation` and attaches it to `GraphQlSource`.

Add dependencies:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

To export metrics to Prometheus, add the corresponding registry:

~~~groovy
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

Configuration to expose the required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Actuator and the registry help create, store, or export metrics. To obtain traces, the application also needs a corresponding Micrometer Tracing bridge/exporter. Simply adding Actuator does not automatically send traces to Zipkin, Tempo, or another tracing backend.

If not using Spring Boot, you can register `GraphQlObservationInstrumentation` manually with `ObservationRegistry`:

~~~java
import java.util.List;

import graphql.execution.instrumentation.Instrumentation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.core.io.ClassPathResource;

GraphQlSource.SchemaResourceBuilder builder = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"));

Instrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);

GraphQlSource graphQlSource = builder
        .instrumentation(List.of(instrumentation))
        .build();
~~~

In a Boot application that already has GraphQL observation auto-configuration, do not register an identical instrumentation manually without intent. Avoid creating duplicate observations for the same execution.

## 11. Viewing graphql.outcome via the Actuator Metrics Endpoint

After sending several GraphQL requests, you can inspect timer metrics via the endpoint:

~~~http
GET /actuator/metrics/graphql.request
~~~

Filter by outcome:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.outcome:SUCCESS
GET /actuator/metrics/graphql.request?tag=graphql.outcome:REQUEST_ERROR
GET /actuator/metrics/graphql.request?tag=graphql.outcome:INTERNAL_ERROR
~~~

Similarly, inspect fields and DataLoaders:

~~~http
GET /actuator/metrics/graphql.datafetcher
GET /actuator/metrics/graphql.dataloader
~~~

Actuator returns timer details such as count, total time, and available statistics. Metric names and tag formats upon export may be transformed according to the registry's naming conventions. When using Prometheus, timer metrics are typically represented as count/sum/bucket series with normalized names.

Do not expose Actuator endpoints publicly without access controls. In production, restrict endpoints using Spring Security, network policies, or an appropriate management port configuration.

## 12. Reading Outcome Metrics to Find Errors

A basic dashboard can track request counts by outcome:

| Metric to monitor | Question to answer |
| --- | --- |
| `graphql.request` by `graphql.outcome` | How are the rates of success, request error, and internal error changing? |
| `graphql.request` by `graphql.operation.type` | Is the problem affecting queries, mutations, or subscriptions? |
| `graphql.datafetcher` by `graphql.field.name` and outcome | Which field frequently produces errors or high processing time? |
| `graphql.dataloader` by `graphql.loader.name` and outcome | Which batch loader is failing? |
| `graphql.dataloader` duration and loader size in traces | Do large batches increase latency? |

Typical scenarios:

- `REQUEST_ERROR` rises while `INTERNAL_ERROR` stays flat: check clients sending malformed queries, validation issues, invalid inputs, or intentional business errors.
- `INTERNAL_ERROR` rises: check unhandled exceptions, database failures, downstream services, or resolver errors classified as internal.
- `graphql.datafetcher` shows `ERROR` on a specific field: check traces and `graphql.error.type` to locate the responsible resolver/service.
- `graphql.dataloader` shows `ERROR`: check the batch service, key-set queries, timeouts, and mapping errors.
- Request duration increases while outcome remains `SUCCESS`: likely a performance issue rather than a failure. Inspect data fetcher and dependency spans.

Do not treat the `REQUEST_ERROR` rate as equivalent to the HTTP 4xx rate. GraphQL request errors can be returned over HTTP 200 depending on the transport and server handling.

## 13. Customizing Observation Conventions While Preserving Outcome Semantics

Spring for GraphQL allows adding metadata via custom observation conventions. With Spring Boot, a convention can be registered as a bean. Extend the default convention and keep default keys, especially `graphql.outcome`:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.stereotype.Component;

@Component
public class ApplicationGraphQlObservationConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context
    ) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("graphql.application", "catalog"));
    }
}
~~~

The `graphql.application` key in the example has a small set of fixed values, making it suitable as a low-cardinality key. The default convention remains responsible for producing `graphql.outcome` and `graphql.operation.type`.

If you want to customize data fetcher or DataLoader observations, you can provide a `DataFetcherObservationConvention` or `DataLoaderObservationConvention` respectively. With Spring GraphQL 1.4+, the full constructor of `GraphQlObservationInstrumentation` supports all three conventions: request, data fetcher, and DataLoader. Spring Boot can automatically detect convention beans to configure the instrumentation.

Do not record user IDs, emails, tokens, raw queries, request IDs, or tenant IDs with unbounded value sets in low-cardinality keys. If you genuinely need detailed metadata for investigation, consider high-cardinality trace attributes after evaluating privacy and retention policies.

## 14. Error Events in Traces

In addition to the `graphql.outcome` key, Spring for GraphQL records GraphQL errors as Observation events on the request. These events have names based on the error type; the contextual name may contain the full error message.

This is helpful when opening a trace to see why a request resulted in `REQUEST_ERROR` or `INTERNAL_ERROR`. However, error messages can contain input data, personal information, or infrastructure details if the application passes exception messages through directly.

Sanitize error messages before placing them into GraphQL responses and traces. Do not put access tokens, passwords, SQL, connection strings, or personal data into messages or extensions.

## 15. Distinguishing graphql.outcome from HTTP Outcome

An HTTP request and a GraphQL execution are two distinct observation layers:

| Layer | Observation | Example outcome/status |
| --- | --- | --- |
| HTTP server | `http.server.requests` | HTTP 200, 400, 500 |
| GraphQL request | `graphql.request` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| GraphQL field | `graphql.datafetcher` | `SUCCESS`, `ERROR` |
| GraphQL batch | `graphql.dataloader` | `SUCCESS`, `ERROR` |

For example, the server returns HTTP 200 with a body containing partial `data` and `errors`. In that case, the HTTP observation may record status 200, while the GraphQL request observation records `REQUEST_ERROR` or `INTERNAL_ERROR` according to the error classification.

If you look only at HTTP status, dashboards may miss business errors and field-level failures. If you look only at `graphql.outcome`, you will not see requests that failed at the network/transport layer before GraphQL execution began. Place both observation types side by side during investigations.

## 16. Testing Outcomes in Your Application

You can verify observations at two layers:

1. **Integration test:** send GraphQL operations via `GraphQlTester` or an HTTP tester, then assert the response and recorded metrics.
2. **Observation convention test:** construct an appropriate `ExecutionRequestObservationContext` and verify the keys produced by the convention.

With Spring Boot, an integration test can use `@SpringBootTest`, `@AutoConfigureObservability`, or a test registry configuration appropriate for your Boot version. After executing a request, retrieve the timer from `MeterRegistry` and verify the `graphql.outcome` tag.

Conceptual assertion example with a Micrometer registry:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import static org.assertj.core.api.Assertions.assertThat;

Timer successTimer = meterRegistry.find("graphql.request")
        .tag("graphql.outcome", "SUCCESS")
        .timer();

assertThat(successTimer).isNotNull();
assertThat(successTimer.count()).isGreaterThan(0);
~~~

This test assumes a valid query without errors was sent and `MeterRegistry` is wired to `ObservationRegistry`. For parallel tests or tests sharing an application context, isolate the registry or compare counts before and after the request to avoid interference from other tests.

Scenarios to cover:

| Test scenario | Expected request outcome |
| --- | --- |
| Valid query, no errors | `SUCCESS` |
| Malformed document | `REQUEST_ERROR` |
| Input validation error returned as a non-internal GraphQL error | `REQUEST_ERROR` |
| Field error with classification `NOT_FOUND` | `REQUEST_ERROR` |
| Field error with classification `INTERNAL_ERROR` | `INTERNAL_ERROR` |
| Unable to produce a valid GraphQL response | `INTERNAL_ERROR` |

For data fetchers and DataLoaders, verify their dedicated observations have outcome `ERROR` when a resolver or batch loader fails. Do not assert only the request timer, since the request-level outcome does not pinpoint which field or loader caused the failure.

## 17. Common Mistakes When Reading graphql.outcome

| Symptom | Cause | Resolution |
| --- | --- | --- |
| No `graphql.request` metric | Observation instrumentation not configured or missing `ObservationRegistry` | Check Actuator/Observation auto-configuration and GraphQL instrumentation |
| Only `http.server.requests` appears | Transport is instrumented, but GraphQL execution is not | Enable `GraphQlObservationInstrumentation` |
| Request has partial data yet outcome is `REQUEST_ERROR` | Response contains errors not classified as `INTERNAL_ERROR` | This is the default semantics; check error classification |
| HTTP 200 yet GraphQL outcome is an error | HTTP status and GraphQL outcome measure two different layers | Monitor both transport and GraphQL observations |
| Data fetcher errored yet request outcome is not `INTERNAL_ERROR` | Error was classified as `BAD_REQUEST`, `NOT_FOUND`, `FORBIDDEN`, or non-internal | Check `ErrorType` in the exception resolver |
| Metric has too many time series | Operation name, path, ID, or user data added to low-cardinality tags | Keep unbounded keys in high-cardinality trace attributes or drop them |
| No `graphql.dataloader` | Missing DataLoader instrumentation or no batch loader execution | Check GraphQlObservationInstrumentation and how DataLoaders are registered |
| Trace does not link HTTP and GraphQL | Observation context not propagated across transport | Check transport instrumentation and Micrometer context propagation |
| Error message leaks internal info in traces | Raw exception message copied into GraphQL error event | Sanitize messages and strip sensitive data |

## 18. Operational Workflow with graphql.outcome

When implementing monitoring for Spring for GraphQL:

1. Add Spring Boot Actuator and configure an appropriate Micrometer registry.
2. Ensure `ObservationRegistry` and `GraphQlObservationInstrumentation` are configured.
3. Collect `graphql.request` and group by `graphql.outcome` along with `graphql.operation.type`.
4. Monitor `graphql.datafetcher` to identify slow or failing fields.
5. Monitor `graphql.dataloader` to detect failing batches, unusual batch sizes, and N+1 issues.
6. Keep low-cardinality tags within a small, stable set of values.
7. Use high-cardinality attributes in traces when investigating a specific execution.
8. Compare GraphQL outcome with HTTP status to separate execution errors from transport errors.
9. Test `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR`, and field/batch `ERROR`.
10. Secure Actuator endpoints and strip sensitive data from error messages, tags, and traces.

`graphql.outcome` is a valuable aggregate signal for tracking GraphQL processing quality. When combined with operation type, data fetcher observations, DataLoader observations, and HTTP transport metrics, operations teams can tell at which level a request failed and start investigating from the right field or batch loader.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL 1.4 — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL 1.4 — GraphQlObservationDocumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationDocumentation.html)
- [Spring Boot 3.5 — GraphQlObservationAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
