# graphql.operation.type

## Objectives

After this lesson, you will be able to:

- Explain what `graphql.operation.type` is in Spring for GraphQL observability.
- Distinguish operation type from operation name and field name.
- Recognize the three standard values `query`, `mutation`, and `subscription`.
- Understand the fallback value `operation` when a GraphQL document cannot be parsed.
- Read the `graphql.request` metric by operation type and outcome.
- Distinguish low-cardinality keys from high-cardinality keys.
- Configure GraphQL observations in Spring Boot and Micrometer.
- Design dashboards comparing traffic, latency, and errors by operation type.
- Customize observation conventions while keeping dimensions low-cardinality.
- Test operation types and avoid leaking data through metrics or traces.

## 1. What Is graphql.operation.type?

`graphql.operation.type` is a low-cardinality key on the GraphQL server request observation provided by Spring for GraphQL. It describes the type of operation the GraphQL engine is processing.

The standard values for this key are:

- `query`: reading data.
- `mutation`: modifying data.
- `subscription`: subscribing to receive results as an event stream.

If the request document cannot be parsed so Spring cannot determine the operation type, the fallback value is `operation`.

This is observability metadata recorded by Spring for GraphQL. It is not a field in the GraphQL schema, not an argument passed by the client, and not a resolver name.

For example, the following three requests have different root field names and are classified by operation type:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

~~~graphql
mutation RenameBook {
    renameBook(id: "book-42", title: "Spring GraphQL") {
        id
        title
    }
}
~~~

~~~graphql
subscription WatchBook {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
    }
}
~~~

Their observations carry `graphql.operation.type=query`, `graphql.operation.type=mutation`, and `graphql.operation.type=subscription`, respectively.

## 2. Distinguishing Operation Type, Operation Name, and Field Name

These three concepts serve different roles:

| Component | Example | Meaning |
| --- | --- | --- |
| Operation type | `query` | GraphQL operation type |
| Operation name | `FindBook` | Operation name chosen by the client |
| Field name | `book` | Field selected in the operation |

Example:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

In the document above:

- Type is `query`.
- Name is `FindBook`.
- Root field is `book`.

If a document contains multiple operations, the client uses `operationName` to select which operation to execute. `graphql.operation.type` reflects the type of the selected operation. A document containing a single anonymous operation is still classified by that operation's type.

The operation name is useful when inspecting traces and locating a specific operation. However, client-provided names can take a huge variety of values. Therefore, Spring for GraphQL separates them into two different observability groups:

- `graphql.operation.type` is low cardinality.
- `graphql.operation.name` is high cardinality.

Do not use operation name in place of operation type when building aggregate dashboards. A dashboard comparing Queries and Mutations should group by `graphql.operation.type`.

## 3. Three Standard Operation Types

### Query

A Query reads data and generally does not cause business side effects.

~~~graphql
query FindBooks {
    books {
        id
        title
    }
}
~~~

The observation records the operation type as `query`. You can use this dimension to monitor the traffic volume and processing duration of read operations.

### Mutation

A Mutation performs changes to state or data.

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
    }
}
~~~

The observation records the operation type as `mutation`. When Mutations see increased latency or error rates, operations teams can isolate write issues from read traffic.

### Subscription

A Subscription registers to receive new results over time.

~~~graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        status
    }
}
~~~

The observation records the operation type as `subscription`. Subscriptions are typically long-lived and use streaming-capable transports such as WebSocket or SSE. When analyzing metrics, keep in mind that the observation measures the request/operation according to the framework's lifecycle; do not assume every emitted event in the stream creates a new request observation.

## 4. The `operation` Value When a Document Cannot Be Parsed

If a GraphQL document has invalid syntax and cannot be parsed, the framework cannot determine the operation type yet. In that case, `graphql.operation.type` uses the fallback value `operation`.

Example invalid document:

~~~graphql
query FindBook {
    book(id: ) {
        id
    }
}
~~~

The value `operation` is an observation fallback label, not a fourth operation type in the GraphQL specification.

Distinguish between two situations:

- Document cannot be parsed: operation type may take the fallback value `operation`.
- Document parses but execution returns an error: operation type can still be `query`, `mutation`, or `subscription`; the error state is expressed separately via `graphql.outcome`.

This prevents dashboards from lumping syntax errors together with all execution errors.

## 5. Which Observation Contains graphql.operation.type?

Spring for GraphQL integrates Micrometer Observation to record GraphQL server activity.

The observation for a GraphQL server request is named:

`graphql.request`

This observation is created for both imperative and reactive applications across transports supported by Spring for GraphQL. By default, `GraphQlObservationInstrumentation` uses `DefaultExecutionRequestObservationConvention` to collect metadata.

Default low-cardinality keys for a server request include:

| Key | Role | Example |
| --- | --- | --- |
| `graphql.operation.type` | Operation type | `query`, `mutation`, `subscription`, `operation` |
| `graphql.outcome` | Request outcome | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |

A request observation also includes high-cardinality keys:

| Key | Meaning |
| --- | --- |
| `graphql.execution.id` | Execution ID of the GraphQL request |
| `graphql.operation.name` | Operation name sent by the client |

Thus, `graphql.operation.type` is a dimension of the `graphql.request` observation, not the name of a separate meter.

## 6. Reading graphql.outcome Alongside Operation Type

Knowing only the operation type is not enough to evaluate API health. Analyze it alongside `graphql.outcome`.

By default, Spring for GraphQL classifies outcomes as follows:

| Outcome | Meaning |
| --- | --- |
| `SUCCESS` | A valid GraphQL response is produced and contains no errors |
| `REQUEST_ERROR` | The request could not be parsed or the response contains errors not categorized as `INTERNAL_ERROR` |
| `INTERNAL_ERROR` | A valid GraphQL response could not be produced or the response contains at least one `INTERNAL_ERROR` error |

Examples of how to read them:

- `query + SUCCESS`: a read operation completed with no GraphQL errors.
- `mutation + REQUEST_ERROR`: a Mutation encountered a request error or a GraphQL error not classified as internal.
- `subscription + INTERNAL_ERROR`: subscription processing encountered an internal error according to the instrumentation's classification rules.

`REQUEST_ERROR` is not synonymous with HTTP status 400 in every case. A GraphQL response can contain `errors` while the transport still returns a valid HTTP response. Treat GraphQL outcome and HTTP transport observation as two complementary viewpoints.

## 7. Low Cardinality and High Cardinality

Cardinality is the number of distinct values a dimension can take.

**Low cardinality** has a small, bounded set of values. `graphql.operation.type` is low cardinality because it only has a finite set of values.

**High cardinality** has a value set that can grow very large. Execution ID and operation name are examples in the GraphQL request observation.

In Micrometer Observation:

- Low-cardinality key values are used as metric tags.
- High-cardinality key values are excluded from meters; they are intended for tracing or logging backends capable of handling large value sets.

This distinction matters because metrics are typically stored as time series and each tag combination creates a new time series. Rapidly growing combinations increase memory usage, storage costs, and query overhead on the monitoring backend.

For example, with three operation types and three outcomes, the base combinations across these two dimensions remain small. If you add `userId` with millions of values, the number of time series can explode.

Do not convert high-cardinality values into metric tags merely for dashboard filtering convenience.

## 8. Enabling GraphQL Observations in Spring Boot

Spring for GraphQL only publishes observations when the application has a configured `ObservationRegistry`.

In a Spring Boot application, GraphQL observation auto-configuration registers `GraphQlObservationInstrumentation` when an `ObservationRegistry` is present. Spring Boot also allows providing custom conventions as beans.

A common setup for exporting metrics is adding Actuator and a corresponding registry, such as Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Configuration to expose the required endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Exposing endpoints must align with the environment's security policy. Do not expose metrics endpoints to arbitrary Internet clients without proper access controls.

If the application does not use Spring Boot, configure an `ObservationRegistry` and add `GraphQlObservationInstrumentation` to the application's GraphQL instrumentation. The default constructor accepts the registry and uses default conventions:

~~~java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);
~~~

The snippet above creates the instrumentation. The application must pass that instance to the GraphQL runtime when configuring `GraphQlSource`/GraphQL Java.

## 9. Viewing Metrics by Operation Type

Once instrumentation is active and a meter registry is connected, you can query the `graphql.request` meter.

The Actuator metrics endpoint allows filtering by tags. Example querying Query requests:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query
~~~

Filter for successful Queries:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query&tag=graphql.outcome:SUCCESS
~~~

Filter for Mutations with request errors:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:mutation&tag=graphql.outcome:REQUEST_ERROR
~~~

Meter names and tag representations upon export may be transformed according to the registry/backend. Use the Actuator metrics endpoint or the actual scrape endpoint to verify the names and tags your system exports.

With Prometheus, Micrometer converts meter names and tags to fit the backend's conventions. Avoid hardcoding backend-normalized names in application code; inside the application, the original convention remains `graphql.request` and `graphql.operation.type`.

## 10. Designing Dashboards by Operation Type

`graphql.operation.type` helps separate load and service quality by operation category.

An operational dashboard might include these panels:

| Panel | Primary dimension | Purpose |
| --- | --- | --- |
| Request volume | `graphql.operation.type` | Compare Query, Mutation, and Subscription volume |
| Request latency | `graphql.operation.type` | Detect which operation type has rising processing times |
| Request errors | `graphql.operation.type`, `graphql.outcome` | Differentiate errors by operation category |
| Subscription activity | `graphql.operation.type=subscription` | Track subscription activity levels |
| Parse/validation issues | `graphql.operation.type=operation`, outcome | Identify malformed request documents |

Examples of interpreting the dashboard:

- A sudden spike in Queries may result from overly frequent client polling or a newly deployed read flow.
- Slow Mutations may point to transactions, locks, or downstream write services.
- Increased Subscriptions may drive up long-lived connections and resource consumption.
- Rising `operation` counts alongside `REQUEST_ERROR` may indicate clients sending syntactically invalid documents.

These are signals for investigation, not sole proof of root cause. Combine DataFetcher observations, DataLoader observations, HTTP server metrics, and traces to isolate bottlenecks.

## 11. Combining with DataFetcher and DataLoader Observations

A GraphQL request may invoke many DataFetchers. Spring for GraphQL creates a dedicated `graphql.datafetcher` observation for fetch operations considered non-trivial.

Some low-cardinality keys on DataFetcher observations:

- `graphql.field.name`
- `graphql.outcome`
- `graphql.error.type`

The DataLoader observation is named `graphql.dataloader`, tracking `@BatchMapping` and manually registered DataLoaders. Its low-cardinality keys include:

- `graphql.loader.name`
- `graphql.outcome`
- `graphql.error.type`

You can use these observations to drill down after a dashboard shows an issue with a particular operation type:

1. Identify the `graphql.operation.type` with high latency or error rates.
2. Open a corresponding trace to inspect field fetch operations.
3. Locate slow or failing DataFetchers.
4. Check DataLoader invocations and batch sizes if the issue involves loading relationships.
5. Cross-reference with database or downstream service spans.

Do not attach full field paths, user IDs, or input data as metric dimensions solely to correlate layers. Traces and correlation IDs are better suited for per-request investigation.

## 12. Customizing ExecutionRequestObservationConvention

In Spring Boot, you can provide an `ExecutionRequestObservationConvention` bean to add metadata to the GraphQL request observation.

Example adding a fixed `application.component` dimension while preserving default keys:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("application.component", "catalog"));
            }
        };
    }
}
~~~

The default convention still provides `graphql.operation.type` and `graphql.outcome`. The new dimension has a fixed value `catalog`, keeping cardinality low.

If you want to customize how operation types are classified, understand the impact on existing dashboards and alerts. Keep the vocabulary finite and consistent, and do not replace standard values with operation names or field names.

Do not create tags from query text, variables, user IDs, emails, tenant IDs, or arbitrary headers. If you need those values for investigation, consider putting them into traces after assessing security risks and data policies.

## 13. Testing graphql.operation.type

You should test at two layers:

- The convention returns the expected low-cardinality key.
- Metrics actually appear when GraphQL requests pass through instrumentation.

You can test the convention using `ExecutionInput` and `ExecutionRequestObservationContext`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;

import io.micrometer.common.KeyValue;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class GraphQlOperationTypeConventionTests {

    static class ExposedConvention extends DefaultExecutionRequestObservationConvention {

        KeyValue operationTypeFor(ExecutionRequestObservationContext context) {
            return operationType(context);
        }
    }

    @Test
    void shouldClassifyQueryOperation() {
        ExecutionInput input = ExecutionInput.newExecutionInput()
                .query("query FindBooks { books { id } }")
                .build();

        ExecutionRequestObservationContext context =
                new ExecutionRequestObservationContext(input);

        KeyValue operationType = new ExposedConvention().operationTypeFor(context);

        assertThat(operationType.getKey()).isEqualTo("graphql.operation.type");
        assertThat(operationType.getValue()).isEqualTo("query");
    }
}
~~~

You can extend similar tests for `mutation` and `subscription`. For unparseable documents, verify the fallback value `operation` according to the Spring for GraphQL version in use.

In integration tests, send each operation through the GraphQL endpoint and verify that the `graphql.request` meter has the corresponding tag. Use `SimpleMeterRegistry` or an appropriate test registry and assert that the recorded count increments after the request finishes.

When testing metrics, wait for reactive execution to finish before reading meters. Avoid sharing registries or state across parallel tests if tests can mutate the same meter.

## 14. Cardinality and Data Security

The following dimensions are generally unsuitable for metric tags:

- `userId`, `accountId`, `tenantId`.
- Email, username, or phone number.
- GraphQL query text and variables.
- Execution ID.
- Operation name if clients can generate dynamic names.
- Per-request Request ID or correlation ID.

Some of these values can be useful in traces, but still require evaluating sensitive data and retention policies. High cardinality does not mean all data is safe to record in traces.

Principles:

1. Keep `graphql.operation.type` within its standard vocabulary.
2. Use `graphql.outcome` to classify request results.
3. Keep per-request IDs in controlled traces/logs.
4. Do not construct metric tags from untrusted input.
5. Redact sensitive information before writing traces or logs.
6. Restrict access to Actuator and monitoring backends.
7. Monitor time series counts after adding custom conventions.

## 15. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `graphql.request` not found | Missing `ObservationRegistry` or instrumentation not configured | Check Boot auto-configuration and GraphQL instrumentation |
| Meter exists but lacks `graphql.operation.type` | Convention was replaced or custom convention dropped default keys | Extend the default convention and retain low-cardinality keys |
| Operation type value is `operation` | GraphQL document could not be parsed | Check document syntax and client request |
| Dashboard merges Queries and Mutations | Grouping by outcome or operation name instead of operation type | Group by `graphql.operation.type` |
| Metrics time series count grows abnormally | Custom dimension takes too many values | Remove user IDs, request IDs, and dynamic data from metric tags |
| Query errored but outcome is not INTERNAL_ERROR | Error is classified as a request/GraphQL error | Review `graphql.outcome` rules and error type |
| HTTP status is success but GraphQL has errors | GraphQL response and HTTP status are two separate layers | Check both GraphQL outcome and transport observation |
| Operation name missing from metrics | `graphql.operation.name` is a high-cardinality key | Inspect traces instead of expecting a metric tag |
| Subscription has long latency | Observation reflects request/operation lifecycle | Review transport semantics and monitor connections/events separately |
| Actuator does not expose Prometheus | Missing registry or endpoint not exposed | Check dependencies and management endpoint configuration |

## 16. Workflow for Using graphql.operation.type

When implementing observability for Spring for GraphQL, follow this sequence:

1. **Enable ObservationRegistry.** Verify GraphQL instrumentation is configured.
2. **Confirm the request meter.** Verify that `graphql.request` observations are recorded.
3. **Check operation types.** Send a Query, Mutation, and Subscription; verify their respective values.
4. **Test parse failures.** Send a syntactically invalid document and verify the fallback label `operation`.
5. **Combine with outcome.** Distinguish `SUCCESS`, `REQUEST_ERROR`, and `INTERNAL_ERROR`.
6. **Keep cardinality low.** Use only bounded-value dimensions for metrics.
7. **Build dashboards.** Compare request volume, latency, and error rate by operation type.
8. **Investigate deeply with traces.** Use operation name, execution ID, and field observations when needed.
9. **Customize carefully.** Extend conventions while retaining default keys and avoiding dynamic data.
10. **Test periodically.** Verify metric tags after upgrading Spring Boot or Spring for GraphQL.

## 17. Summary

`graphql.operation.type` is a low-cardinality key of the GraphQL server request observation in Spring for GraphQL. It classifies operations as `query`, `mutation`, `subscription`, or `operation` when the document cannot be parsed. This key lets you aggregate metrics by interaction type without creating a separate time series for each operation name.

Read `graphql.operation.type` alongside `graphql.outcome` in the `graphql.request` observation. Operation name and execution ID belong to the high-cardinality group and fit better in traces. By enabling Micrometer Observation, building dashboards by operation type, and keeping custom tags to a bounded vocabulary, you can monitor the traffic, latency, and errors of your GraphQL API without letting cardinality or data exposure risks grow out of control.

## References

- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
