# Tracking errors by operation

## Objectives

After this lesson, you will be able to:

- Explain why errors should be tracked per GraphQL operation instead of looking solely at HTTP status codes.
- Distinguish request errors, field execution errors, and transport errors.
- Assign stable operation names to queries, mutations, and subscriptions.
- Use Spring for GraphQL's Micrometer Observation to instrument requests and data fetchers.
- Interpret the `SUCCESS`, `REQUEST_ERROR`, and `INTERNAL_ERROR` outcomes.
- Correlate errors in traces using execution ID, operation name, and field path.
- Distinguish low-cardinality and high-cardinality keys when designing metrics.
- Extend observations using `ExecutionRequestObservationConvention`.
- Design structured logs, dashboards, and per-operation error alerts.
- Test error recording, including cases where GraphQL returns partial data.

## Why track by operation?

A GraphQL endpoint typically shares a single URL across many capabilities. For instance, `/graphql` might receive:

- Query `BookDetails` to read book details.
- Query `SearchBooks` to search.
- Mutation `CreateBook` to create a book.
- Mutation `PlaceOrder` to place an order.
- Subscription `BookEvents` to receive events.

If you only monitor HTTP requests, every operation appears under the same route. A slow book query, a failing payment mutation, and a dropped subscription get blended into a single bucket of numbers.

GraphQL can also return HTTP 200 even when the response contains `errors`. One field can fail while other fields still return data. Thus, HTTP status alone is insufficient to determine whether a GraphQL request succeeded or failed.

Tracking by operation helps answer operational questions:

- Which operation has a rising error rate?
- Are errors concentrated in queries, mutations, or subscriptions?
- Which operation has high p95/p99 latency?
- Do errors occur at a root field or a nested field?
- Are errors caused by validation, business rules, the database, or an external service?
- Which operations were impacted by a deployment change?

The goal is to link three layers of information: the overall request, the failing field resolver, and an exception or business-meaningful error code.

## Assigning stable operation names

GraphQL operations can be named:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

The operation name is the identifier declared after `query`, `mutation`, or `subscription`. This is useful metadata for distinguishing use cases sharing the same endpoint.

Use stable, meaningful names:

| Operation name | Purpose |
| --- | --- |
| `BookDetails` | Read details of a single book |
| `SearchBooks` | Search for books |
| `CreateBook` | Create a book |
| `PlaceOrder` | Create an order |
| `BookEvents` | Observe book events |

Do not construct operation names from user IDs, request IDs, timestamps, or input values. Those values change per request, making dashboards difficult to group and inflating cardinality.

If a client sends an anonymous operation, the server can still execute it, yet the observation lacks a clear business name. Establish a convention that client SDKs and frontend apps always include operation names in released requests.

When a document contains multiple operations, the client must send `operationName` so the server knows which operation to run. Operation names must also be unique within the same document.

## Distinguishing error types

GraphQL has multiple stages where errors can arise. Classifying them accurately points you to the right place to investigate.

| Error type | Timing | Example | Did data fetchers run? |
| --- | --- | --- | --- |
| Parse error | Parsing document syntax | Missing brace or invalid token | No |
| Validation error | Validating document against schema | Non-existent field or wrong argument type | No |
| Variable coercion error | Coercing variables to schema types | Sending a string for an `Int!` argument | Operation not executed |
| Execution error | During field resolution | Database timeout or missing entity | May have run one or more fields |
| Business error | Business rules from resolver/service | Out of stock or invalid order status | Usually ran the relevant field |
| Transport error | Before or outside GraphQL execution | HTTP timeout, WebSocket disconnect | Not guaranteed to have a GraphQL response |

### Request errors and execution errors

Request errors occur before GraphQL can execute a valid operation. Examples include malformed syntax, schema mismatches, or variables that fail coercion. No data fetcher needs to run to produce the response for that operation.

Execution errors occur while resolving fields. GraphQL can return both `data` and `errors`:

~~~json
{
  "data": {
    "book": {
      "id": "book-101",
      "title": "Spring for GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Unable to load author",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

This response contains partial data. The client still receives `id` and `title`, while the `author` field failed. In GraphQL, having `errors` does not mean the entire request returned no data.

### Null propagation can widen error impact

If a failing field is non-null, GraphQL propagates `null` up to the nearest nullable parent. Therefore, an error on a nested field can wipe out a larger portion of the response.

When investigating, inspect all of:

- `errors.path` to see which field originated the error.
- `data` to see what portions remain intact.
- Schema nullability to understand why `null` bubbled up to a parent.
- `extensions.code` or error type to classify the cause.

Do not merely count errors. An operation with one error on a nullable field may still be useful; a single error on a critical non-null field can break an entire data subtree.

## Micrometer Observation in Spring for GraphQL

Spring for GraphQL integrates Micrometer Observation to produce metrics and traces for GraphQL requests, non-trivial data fetchers, and DataLoaders. Observations are emitted only when the application has an `ObservationRegistry` and GraphQL observation instrumentation configured.

With Spring Boot, auto-configuration creates `GraphQlObservationInstrumentation` when an appropriate `ObservationRegistry` is present. When using the Boot starter alongside Actuator and observability infrastructure, you normally do not need to create the instrumentation manually. If building `GraphQlSource` or a `GraphQL` instance manually, register the corresponding instrumentation. [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)

Spring for GraphQL has three primary observations:

| Observation | Scope | Used to find |
| --- | --- | --- |
| `graphql.request` | Entire GraphQL request | Failing operations, slow requests, outcomes |
| `graphql.datafetcher` | A non-trivial data fetcher | Slow or failing field resolvers |
| `graphql.dataloader` | A batch loader or `@BatchMapping` | Failing batch loads, batch size, and batching efficiency |

A single request can create one `graphql.request` observation and multiple `graphql.datafetcher` observations. Data fetchers running concurrently or across nested selection sets still belong to the same request context.

### Default keys of graphql.request

Spring for GraphQL uses `DefaultExecutionRequestObservationConvention`. Default keys include:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.operation.type` | Low | `query`, `mutation`, `subscription`, or `operation` if the document cannot be parsed |
| `graphql.outcome` | Low | `SUCCESS`, `REQUEST_ERROR`, or `INTERNAL_ERROR` |
| `graphql.execution.id` | High | `ExecutionId` of the request |
| `graphql.operation.name` | High | Operation name provided by the client |

Outcome is determined from the GraphQL response:

- `SUCCESS`: response is valid and contains no errors.
- `REQUEST_ERROR`: request could not be parsed or response has errors, yet no error has `ErrorType.INTERNAL_ERROR`.
- `INTERNAL_ERROR`: could not produce a valid GraphQL response or response has at least one error with `ErrorType.INTERNAL_ERROR`.

The name `REQUEST_ERROR` can be misleading: this outcome does not cover only parse/validation errors. It can also include business errors or execution errors classified with an error type other than `INTERNAL_ERROR`.

If a response contains both `data` and `errors`, the outcome is still `REQUEST_ERROR` or `INTERNAL_ERROR` depending on the `ErrorType` of the errors. Therefore, dashboards should show outcomes alongside error details rather than interpreting `REQUEST_ERROR` as a request rejected prior to execution.

Spring for GraphQL also records GraphQL errors in the response as Observation Events. These events typically appear as span annotations in traces, containing the error type and a contextual name derived from the error message. This helps navigate from a failing operation to specific details in a trace.

### Default keys of graphql.datafetcher

The `graphql.datafetcher` observation is created only for non-trivial data fetching operations. Reading a property directly from a Java object is typically treated as trivial and does not create a separate observation.

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.field.name` | Low | Name of the field being resolved |
| `graphql.outcome` | Low | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Class name of the data fetching error |
| `graphql.field.path` | High | Field path in the response, e.g. `/book/author` |

Data fetcher observations help pinpoint the exact field experiencing errors or high processing time. For lists, the field path can contain indices; use it in traces to investigate a single execution, and do not put full paths into metric tags if paths have high cardinality.

### Default keys of graphql.dataloader

The `graphql.dataloader` observation tracks `@BatchMapping` and manually registered DataLoaders:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.loader.name` | Low | DataLoader name |
| `graphql.outcome` | Low | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Class name of the batch loading error |
| `graphql.loader.size` | High | Number of items loaded in the batch |

If `graphql.request` has high latency yet `graphql.datafetcher` does not single out one field, inspect DataLoader, database queries, and downstream clients within the same trace.

## Enabling observation in Spring Boot

With Spring Boot, add Actuator and the registry matching your metrics backend. Example using Prometheus:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Configure the metrics endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "graphql.request": true
        "graphql.datafetcher": true
~~~

Actuator provides `ObservationRegistry` and Micrometer infrastructure per your application configuration. GraphQL observation auto-configuration activates only when an `ObservationRegistry` is present and corresponding classpath conditions are met.

If using tracing, add the Micrometer Tracing bridge and exporter matching your operating environment. Metrics are suited for aggregating error rates, throughput, and latency; traces are suited for investigating a specific request.

To inspect metrics locally, you can check:

- `/actuator/metrics/graphql.request`
- `/actuator/metrics/graphql.datafetcher`
- `/actuator/metrics/graphql.dataloader`
- `/actuator/prometheus`

Endpoint and metric names may be normalized according to the registry. Inspect the registry's actual output rather than assuming every export system uses identical naming.

For non-Spring-Boot applications, construct `GraphQlObservationInstrumentation` with an `ObservationRegistry` and register it on the `GraphQL` builder. If other instrumentations are already present, combine them using `ChainedInstrumentation` or an equivalent mechanism; do not overwrite existing tracing, metrics, or instrumentation.

## Tracking errors by operation with metrics

Metrics must stay low cardinality and remain aggregatable over time. By default, `graphql.request` reports operation type and outcome. Operation name is a high-cardinality key by default, well suited for trace lookup but not meant to become a metric tag automatically.

Example fixed operations in an application:

- `BookDetails` and `SearchBooks` belong to the `catalog-read` group.
- `CreateBook` and `UpdateBook` belong to the `catalog-write` group.
- `PlaceOrder` belongs to the `order-write` group.

You can add low-cardinality keys via `ExecutionRequestObservationConvention`:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlOperationObservationConfig {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                String operationName =
                        context.getExecutionInput().getOperationName();

                String operationGroup = switch (
                        operationName == null ? "" : operationName) {
                    case "BookDetails", "SearchBooks" -> "catalog-read";
                    case "CreateBook", "UpdateBook" -> "catalog-write";
                    case "PlaceOrder" -> "order-write";
                    default -> "other";
                };

                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of(
                                "graphql.operation.group", operationGroup));
            }
        };
    }
}
~~~

Spring Boot picks up the `ExecutionRequestObservationConvention` bean and uses it to customize request observations. This example keeps all default keys and adds an operation group with a finite set of values.

Do not put raw operation names into low-cardinality keys if clients can send arbitrary names. A buggy or malicious client could generate endless distinct operation names and explode time series counts. If the application has a fixed operation allowlist, map operation names to stable groups as shown.

### Metrics to monitor

| Metric | Operational question |
| --- | --- |
| Request rate by operation group | Which operation has unusual traffic spikes or drops? |
| Error rate by operation group and outcome | Which operation group has a rising error rate? |
| p50, p95, p99 latency | Which operation is slower than baseline? |
| Data fetcher error count by field name | Which field fails most frequently? |
| DataLoader errors and batch sizes | Which batch is failing or running inefficiently? |
| Request count with errors | How many requests return partial data or GraphQL errors? |

Example PromQL assuming the registry exports the `graphql.request` timer per Prometheus conventions:

~~~promql
sum by (graphql_operation_group, graphql_outcome) (
  rate(graphql_request_seconds_count[5m])
)
~~~

Error ratio per operation group:

~~~promql
sum by (graphql_operation_group) (
  rate(graphql_request_seconds_count{
    graphql_outcome=~"REQUEST_ERROR|INTERNAL_ERROR"
  }[5m])
)
/
sum by (graphql_operation_group) (
  rate(graphql_request_seconds_count[5m])
)
~~~

Final metric and label names depend on registry naming conventions and exporter configuration. Verify actual scraped data before putting queries onto dashboards.

Do not alert solely on absolute error counts. A high-traffic operation naturally has more raw errors than a rarely called operation. Track error ratios, minimum request thresholds, and steady time windows to avoid alerting on a few isolated requests.

## Using traces to find root causes

Metrics tell you which operation is having trouble. Traces help pinpoint a specific request and where latency or errors occurred.

A GraphQL trace can typically link:

1. HTTP server span or transport observation.
2. `graphql.request` observation for the whole operation.
3. `graphql.datafetcher` observations for non-trivial resolvers.
4. `graphql.dataloader` observations for batch loading.
5. HTTP client or database spans emitted inside resolvers.

Spring for GraphQL records GraphQL errors in responses as Observation Events on the request. When opening a trace, check:

- Operation name and operation type.
- Execution ID.
- Request outcome.
- Error event type and message.
- Field path on the data fetcher span.
- Downstream spans such as SQL or HTTP clients.

Execution ID is specific to a GraphQL execution. Trace ID links multiple spans across components. The two values serve different purposes: execution ID finds the exact request in GraphQL logs; trace ID connects the entire distributed trace.

If HTTP and GraphQL traces are disconnected, check transport instrumentation and context propagation. GraphQL request observation assumes a parent observation was placed into the GraphQL context under key `micrometer.observation`; HTTP transport instrumentation is responsible for propagating trace context across network boundaries.

## Structured logging by operation

Metrics should not hold error messages or high-cardinality input data. When details are needed, write structured logs with controlled fields:

| Log field | Example | Purpose |
| --- | --- | --- |
| `operationName` | `PlaceOrder` | Identify the use case |
| `operationType` | `mutation` | Distinguish operation types |
| `executionId` | request execution ID | Look up the GraphQL request |
| `traceId` | distributed trace ID | Open cross-service traces |
| `outcome` | `REQUEST_ERROR` | Overall result |
| `errorCode` | `INVENTORY_UNAVAILABLE` | Stable error classification |
| `errorType` | `InventoryException` | Identify exception category |
| `fieldPath` | `placeOrder.items` | Identify the failing field |
| `durationMs` | `184` | Latency analysis |

Emit one summary record when an operation finishes with errors and log the exception where full context is available. For requests with multiple errors, you can log the error count and a list of standardized error codes; avoid repeating long full messages in every log record.

Do not log raw GraphQL queries, variables, access tokens, passwords, emails, addresses, or payment details in default logs. GraphQL queries can contain inline input literals and error messages can contain backend data. If payload debugging is necessary, use time-boxed sampling, restricted access, and redaction.

Prefer stable `extensions.code` values for error codes. Do not use free-form messages as grouping keys because messages can vary across languages, data, or service versions.

## Distinguishing GraphQL outcome from HTTP status

HTTP status describes transport-layer outcome. GraphQL outcome describes GraphQL request processing outcome. These two values do not replace each other.

| HTTP response | GraphQL response | Interpretation |
| --- | --- | --- |
| 200 | Full `data`, no `errors` | GraphQL succeeded |
| 200 | Partial `data` and `errors` | One or more fields failed |
| 200 | `errors` from execution | Operation may have invoked resolvers |
| 4xx | No valid GraphQL response | Transport or request handling rejected the request |
| 5xx | No valid response or server error before GraphQL returned | Investigate transport/server |

Exact status rules also depend on transport, content negotiation, and Spring for GraphQL version. Thus, dashboards should not infer GraphQL success solely from HTTP 2xx or GraphQL failure solely from HTTP 5xx.

In particular, if a client retries only on HTTP 5xx, it can miss business or dependency errors embedded in HTTP 200 GraphQL responses. Retries should depend on error codes and operation idempotency.

## Tracking subscription errors

Subscriptions have a different lifecycle from queries and mutations because a single operation can emit many events over time.

- Errors before a subscription is established can be request/validation errors.
- Errors in the publisher after the subscription starts can be converted into GraphQL subscription errors.
- WebSocket disconnect is a transport error and can happen while the stream is active.
- A single event error does not necessarily mean the entire WebSocket connection closed.

Subscription monitoring must separate operation registration, event delivery, and connection lifecycle. Record operation name, execution/trace context, count of successfully emitted events, publisher errors, and cancellations. Do not treat a long-lived WebSocket connection like a short-lived HTTP request.

For high-throughput subscriptions, do not create metric labels from event IDs, user IDs, or subscription IDs. Keep those values in controlled traces/logs; metrics should contain only operation group, outcome, and bounded error categories.

## Testing error tracking

Tests must verify both the GraphQL response and emitted telemetry.

Cases to include:

| Scenario | What to verify |
| --- | --- |
| Valid operation | `graphql.request` has outcome `SUCCESS` |
| Malformed document | `graphql.request` has outcome `REQUEST_ERROR`; no data fetcher observation |
| Field validation error | Request is rejected before resolvers run |
| Resolver throws mapped business exception | Response has a stable error code; request outcome follows `ErrorType` |
| Resolver throws internal error | Request outcome is `INTERNAL_ERROR` if mapped to `ErrorType.INTERNAL_ERROR` |
| Partial data | Response preserves successful data and includes `errors`; telemetry does not mark `SUCCESS` |
| Nested resolver fails | `graphql.datafetcher` captures field name/path and error type |
| Batch loader fails | `graphql.dataloader` records outcome `ERROR` |
| Anonymous operation | No operation name; still records operation type and execution ID |
| Subscription disconnect | Records transport failure separately from GraphQL execution outcome |

You can use `GraphQlTester` to send operations and assert response `errors`, `path`, and `extensions.code`. For observations, use Micrometer's test `ObservationRegistry` or a test handler to assert observation names and key values. Do not assert only on raw log text; verify structured keys so tests do not depend on log formatting.

Example `GraphQlTester` test verifying the error contract:

~~~java
@Test
void recordsInventoryErrorForPlaceOrder() {
    graphQlTester.document("""
            mutation PlaceOrder($input: PlaceOrderInput!) {
                placeOrder(input: $input) {
                    orderId
                }
            }
            """)
            .variable("input", Map.of(
                    "customerId", "customer-101",
                    "productId", "book-101",
                    "quantity", 2))
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getPath())
                        .contains("placeOrder");
                assertThat(errors.get(0).getExtensions())
                        .containsEntry("code", "INVENTORY_UNAVAILABLE");
            });
}
~~~

This test assumes a fixture causes the inventory service to return an error and the exception resolver maps it to error code `INVENTORY_UNAVAILABLE`. This response test alone does not prove metrics were emitted; write separate tests for `ObservationConvention` or `ObservationRegistry`.

## Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Dashboard shows only one `/graphql` route | Using only HTTP request metrics | Add `graphql.request` and operation metadata |
| HTTP 200 requests show as successes on dashboard | Relying solely on HTTP status | Track `graphql.outcome` and response errors |
| No datafetcher observations on validation errors | Resolvers never ran | Use `graphql.request` observation to track request errors |
| Nested properties missing from traces | Property fetchers are treated as trivial | Focus on non-trivial resolvers and service spans |
| Operation names explode time series | Putting arbitrary names into low-cardinality tags | Use operation groups with finite values |
| Cannot find root cause from metrics | Metrics only show outcomes and latency | Open traces by execution ID/trace ID |
| Errors misclassified as client errors | Business errors and validation errors share `ErrorType` | Standardize `ErrorType` and `extensions.code` by error group |
| Logs contain too much sensitive data | Logging raw queries, variables, or exception messages | Redact and log only necessary metadata |
| Alerts fire from a few isolated requests | Using absolute error counts | Use error ratios, minimum traffic floors, and time windows |
| Subscription errors treated as HTTP request errors | Not separating transport from event stream | Monitor publisher, operation, and connection lifecycle |
| Instrumentation emits no observations | Missing `ObservationRegistry` or GraphQL instrumentation | Check Boot auto-configuration or manual registration |

## End-to-end practice

Set up error tracking for the library API:

1. Assign stable operation names for `BookDetails`, `SearchBooks`, `CreateBook`, and `PlaceOrder`.
2. Add Spring Boot Actuator and a Micrometer registry.
3. Verify `graphql.request`, `graphql.datafetcher`, and `graphql.dataloader` appear.
4. Send a valid query and check outcome `SUCCESS`.
5. Send a malformed document and verify `REQUEST_ERROR` with no resolver observation.
6. Make `BookDetails` return partial data with an error on `author`; inspect response `data`/`errors` and request outcome.
7. Make `PlaceOrder` fail due to inventory; inspect error code and field path.
8. Verify internal errors map to `ErrorType.INTERNAL_ERROR`.
9. Add `ExecutionRequestObservationConvention` to attach a low-cardinality operation group.
10. Export metrics and build a dashboard by operation group, outcome, and latency.
11. Open a trace of a failing request to inspect error events and datafetcher spans.
12. Produce structured logs with operation name, execution ID, trace ID, error code, and field path.
13. Test a subscription encountering a publisher error and a WebSocket disconnect; confirm the two failure modes are distinguished.
14. Configure alerts on error ratio and p95 latency with a minimum traffic threshold.

After completing this, explain why HTTP 200 does not imply a GraphQL operation succeeded, why operation name is a high-cardinality key by default, and how to go from metrics to traces to find the failing field.

## Summary

Tracking errors by operation starts with stable operation names. Spring for GraphQL provides `graphql.request` for the full request, `graphql.datafetcher` for non-trivial resolvers, and `graphql.dataloader` for batch loading. `graphql.outcome` has three values—`SUCCESS`, `REQUEST_ERROR`, and `INTERNAL_ERROR`—and `REQUEST_ERROR` can include partial-data responses with errors. Operation name and execution ID are high-cardinality keys suited for traces and should not automatically become metric tags. Use `ExecutionRequestObservationConvention` to map operations into finite groups, metrics to spot trends, traces to locate failing fields and downstream spans, and structured logs to capture error codes and correlation IDs. Always distinguish GraphQL outcomes from HTTP statuses and protect sensitive data in logs and traces.

## References

- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [ExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationConvention.html)
- [DefaultExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [Spring Boot – Metrics and Observability](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
