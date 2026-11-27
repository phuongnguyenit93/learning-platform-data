# graphql.request observation

Spring for GraphQL integrates Micrometer Observation to record the processing duration and status of GraphQL requests. Observations can be converted into metrics, traces, or both depending on the application configuration. The request-level observation name is `graphql.request`.

Request-level observations help answer important operational questions: how long a GraphQL query/mutation/subscription takes, what proportion of requests succeed or fail, which operations are frequently slow, and which requests require deeper tracing. They also establish a parent context for more granular observations on data fetchers and DataLoaders.

This article focuses on the `graphql.request` observation, default metadata, how to enable and inspect metrics/traces, customizing conventions, and principles for avoiding high cardinality or leaking sensitive data. Within the Spring for GraphQL module, this mechanism adds a runtime perspective alongside schemas, resolvers, DataLoaders, errors, and transports.

## 1. What Is an Observation?

Micrometer Observation is an abstraction for recording an activity in an application. An observation has a context holding information about that activity and key-value pairs describing it. Handlers registered in `ObservationRegistry` can turn observations into timer/counter metrics or spans in a distributed trace.

Main components:

| Component | Role |
| --- | --- |
| `Observation` | Represents a measured operation |
| `ObservationRegistry` | Registry that receives and coordinates observations |
| `Observation.Context` | Holds information about the operation while it is being recorded |
| `ObservationConvention` | Determines the observation name and metadata |
| `KeyValues` | Set of key-value pairs attached to the observation |
| `ObservationHandler` | Converts the observation into metrics, traces, or other processing |

Spring for GraphQL provides instrumentation to create observations directly during GraphQL Java request execution. Applications do not need to manually wrap every resolver in a timer just to know which requests are slow.

## 2. Where graphql.request Sits in the Request Lifecycle

A GraphQL request typically passes through a transport such as HTTP, WebSocket, or RSocket, then reaches the GraphQL execution service and GraphQL Java. The `graphql.request` observation wraps the execution of the GraphQL operation at the GraphQL layer.

~~~mermaid
flowchart TD
    A[Client] --> B[Transport: HTTP / WebSocket / RSocket]
    B --> C[Transport observation]
    C --> D[GraphQL handler]
    D --> E[graphql.request observation]
    E --> F[Parse and validate document]
    F --> G[Execute operation]
    G --> H[DataFetcher / resolver]
    H --> I[Service / repository]
    I --> J[GraphQL response]
    J --> K[Metrics and traces]
~~~

Transport observations and GraphQL observations measure different layers:

- Transport observation measures the HTTP exchange or corresponding connection at the protocol layer.
- `graphql.request` measures GraphQL document processing and operation execution.
- `graphql.datafetcher` measures certain non-trivial data-fetching operations.
- `graphql.dataloader` measures supported batch loader invocations.

Therefore, an HTTP request can have both an `http.server.requests` observation and a `graphql.request` observation. These are not duplicate records; they help distinguish time spent in transport from time spent in GraphQL execution.

## 3. Enabling Observations in Spring Boot

Spring for GraphQL only emits observations when the application has a configured `ObservationRegistry`. With Spring Boot, the common approach is to use Actuator alongside the GraphQL starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot auto-configures `ObservationRegistry` and GraphQL observation instrumentation when the required conditions are met. In Spring Boot 3.x, the auto-configuration lives in Actuator; in Spring Boot 4.x, auto-configuration packages were reorganized. A typical Boot application does not need to manually create an extra `GraphQlObservationInstrumentation` just to enable observations.

If not using Spring Boot, you need to provide an `ObservationRegistry` and register `GraphQlObservationInstrumentation` with the GraphQL runtime/`GraphQlSource`. The exact integration API depends on how the application constructs `GraphQlSource`.

Simply adding Actuator does not mean all metrics are exported to Prometheus or all traces are sent to a tracing backend. You also need the corresponding registry/exporter and endpoint or exporter configuration.

## 4. Default graphql.request Observation

Spring for GraphQL creates an observation named `graphql.request` for GraphQL server requests across supported transports, in both servlet and reactive applications.

The default instrumentation uses `DefaultExecutionRequestObservationConvention` and `ExecutionRequestObservationContext`. The convention produces the following key-values:

| Cardinality | Key | Meaning |
| --- | --- | --- |
| Low | `graphql.operation.type` | Operation type: `query`, `mutation`, `subscription`, or `operation` if unparseable |
| Low | `graphql.outcome` | Processing outcome of the GraphQL request |
| High | `graphql.execution.id` | ID of the GraphQL execution |
| High | `graphql.operation.name` | Operation name provided by the client |

The two low-cardinality keys are important default metadata for metrics analysis. The two high-cardinality keys provide detail for tracing individual executions.

Example document with an operation name:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

The observation records the operation type as `query` and the operation name as `FindBook`. If the client sends a document without an operation name, the high-cardinality operation name can take a default value according to the convention.

## 5. Meaning of graphql.outcome

`graphql.outcome` describes the outcome at the GraphQL execution level, which is not synonymous with the HTTP status code.

| Value | When it occurs |
| --- | --- |
| `SUCCESS` | A valid GraphQL response is produced with no GraphQL errors |
| `REQUEST_ERROR` | The request cannot be parsed or the response has an error not of type `INTERNAL_ERROR` |
| `INTERNAL_ERROR` | A valid GraphQL response cannot be produced or the response contains at least one `INTERNAL_ERROR` error |

For example, a valid query where a field returns a business error may receive HTTP 200 under GraphQL over HTTP, while the `graphql.request` observation has outcome `REQUEST_ERROR`. This ensures metrics reflect errors at the GraphQL layer even when the HTTP transport completes normally.

You should not infer that `SUCCESS` means every business rule was satisfied in the way the product desired. It means GraphQL execution returned a valid response and there were no errors in the response.

## 6. How GraphQL Errors Are Recorded in Traces

Spring for GraphQL also adds GraphQL errors from the response as Observation Events. These events are typically translated into span events or annotations depending on the tracing bridge/exporter.

An event can carry:

- A name based on the GraphQL error type, such as `InvalidSyntax`.
- A contextual name containing the GraphQL error message.

This information lets you open a trace and see the specific errors that occurred during an operation. However, error messages sometimes contain input data, account identifiers, resource names, or sensitive business information. Do not include secrets or personal data in error messages; sanitize errors before sending them to clients and the trace backend.

## 7. Distinguishing graphql.request, graphql.datafetcher, and graphql.dataloader

`graphql.request` shows how long the entire operation took and how it ended. When you need to pinpoint a specific slow resolver or batch loader, two more granular observations are helpful.

| Observation | What does it measure? | When is it created? |
| --- | --- | --- |
| `graphql.request` | GraphQL operation at the request level | Every GraphQL request handled by instrumentation |
| `graphql.datafetcher` | A data-fetching operation | For non-trivial data fetchers; simple property reads from Java objects are usually not measured |
| `graphql.dataloader` | A batch loader invocation | For supported `@BatchMapping` and manually registered DataLoaders |

Default keys:

**`graphql.datafetcher`**

- Low-cardinality: `graphql.error.type`, `graphql.field.name`, `graphql.outcome`.
- High-cardinality: `graphql.field.path`.

**`graphql.dataloader`**

- Low-cardinality: `graphql.error.type`, `graphql.loader.name`, `graphql.outcome`.
- High-cardinality: `graphql.loader.size`.

These observations are created by GraphQL observation instrumentation. DataLoader observability depends on the version of Spring for GraphQL in use; check the API documentation of the corresponding branch when working with older versions.

For example, if `graphql.request` is slow, `graphql.datafetcher` might reveal that the `author` field accounts for most of the duration. If that field invokes a batch loader, `graphql.dataloader` can help inspect the loader name, batch size, and errors.

## 8. Low Cardinality and High Cardinality

Cardinality is the number of distinct values a key can take.

- **Low cardinality** has a small, finite number of values, making it suitable for metric tags.
- **High cardinality** can have a very large number of distinct values, making it better suited for traces than metrics.

Micrometer only includes low-cardinality key-values in metrics; high-cardinality key-values are reserved for traces. This is an important boundary to avoid creating hundreds of thousands of time series.

Examples:

| Data | Recommended classification | Reason |
| --- | --- | --- |
| Operation type: query/mutation/subscription | Low | Small, fixed set of values |
| Outcome: SUCCESS/REQUEST_ERROR/INTERNAL_ERROR | Low | Finite set of states |
| Client-supplied operation name | High | Clients can send unlimited names |
| Execution ID | High | Every request has its own ID |
| Field path | High | Can vary with query structure |
| Raw GraphQL document | Should not be added to metrics | Diverse content, easily contains sensitive data |
| Variable values, user ID, email | Should not be used as metric tags | High cardinality and risk of data exposure |

Do not put operation name, user ID, tenant ID, GraphQL variables, or raw documents into a low-cardinality convention just to filter dashboards by those fields. If tracing genuinely requires them, consider placing controlled metadata in traces under a clear data policy.

## 9. Viewing Metrics via Actuator

If the application uses a Micrometer registry and exposes the Actuator metrics endpoint, you can query meters by observation name:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Example query:

~~~http
GET /actuator/metrics/graphql.request
~~~

The metrics endpoint can return aggregated numbers such as count, total time, and statistics supported by the registry. You can filter by low-cardinality tags, such as operation type:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query
~~~

Metric paths and formats depend on the registry and Actuator configuration. With Prometheus, expose the `/actuator/prometheus` endpoint so Prometheus can scrape it. Metric names are converted according to backend conventions, so the name displayed in Prometheus may differ from the original `graphql.request` observation name.

Secure Actuator endpoints with Spring Security or restrict network access. Do not expose metrics and trace metadata to the public internet without an appropriate access policy.

## 10. Tracing and Linking with Transport Observations

Metrics show trends and rates across many requests. Traces allow you to follow a specific request through the components of the system.

A GraphQL trace can have a general structure like:

~~~text
HTTP server request
└── graphql.request
    ├── graphql.datafetcher: book
    │   └── database/client observation
    ├── graphql.datafetcher: author
    │   └── graphql.dataloader: authorLoader
    └── graphql response
~~~

This is an illustrative relationship; actual child spans depend on the instrumentations present in the application and how context is propagated.

`graphql.request` assumes the parent observation is placed in the GraphQL context under the standard key `micrometer.observation`. Trace propagation across network boundaries is handled by the transport's instrumentation. For HTTP, Spring Framework has its own instrumentation to receive and propagate trace context.

Therefore, when you see disconnected traces, inspect HTTP server/client instrumentation, ObservationRegistry, and context propagation. Enabling GraphQL instrumentation alone does not automatically guarantee that the trace ID is propagated across every service.

## 11. Customizing the Convention for graphql.request

In Spring Boot, the recommended approach is to provide a bean of type `ExecutionRequestObservationConvention`. You can extend `DefaultExecutionRequestObservationConvention` to preserve default metadata while adding a low-cardinality key with a small value set.

Example adding a fixed API version:

~~~java
package com.example.graphql.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention graphQlRequestConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.api.version", "v1"));
            }
        };
    }
}
~~~

Spring Boot auto-configuration will use this convention bean for request observations. Default keys such as operation type and outcome are preserved because the code calls `super.getLowCardinalityKeyValues(context)`.

Only add keys with finite values controlled by the application. If you want to categorize by a request attribute, normalize the input value into a small enum set before adding it to low-cardinality metadata.

## 12. When Is Custom Instrumentation Needed?

In a typical Spring Boot application, a custom convention bean suffices for most needs. Do not manually create a second `GraphQlObservationInstrumentation` if Boot already auto-configures instrumentation.

Custom instrumentation is only appropriate when you need to deeply alter how GraphQL Java emits observations or when the application builds its GraphQL runtime manually without auto-configuration. In that case, make sure only one corresponding instrumentation exists and the registry is properly configured.

The constructors of `GraphQlObservationInstrumentation` have evolved over time to support conventions for requests, data fetchers, and DataLoaders. Some older constructors are deprecated in newer branches. Use the API matching the version of Spring for GraphQL managed by your Spring Boot BOM rather than copying configuration from articles targeting older versions.

## 13. Separating GraphQL Errors from HTTP Errors

A GraphQL response can return HTTP 200 yet contain `errors`. Conversely, errors occurring before GraphQL execution—such as authentication rejected in an HTTP security filter—may not create a `graphql.request` observation because the request never entered the GraphQL runtime.

| Situation | Observation to inspect |
| --- | --- |
| Valid GraphQL request, no errors | `graphql.request` outcome SUCCESS |
| Query parse/validation error | `graphql.request` outcome REQUEST_ERROR if GraphQL instrumentation handles the request |
| Resolver returns a business GraphQL error | `graphql.request` outcome REQUEST_ERROR and possibly a data fetcher error |
| Internal GraphQL execution error | `graphql.request` outcome INTERNAL_ERROR |
| HTTP authentication rejected before GraphQL | HTTP server/security observation and security logs |
| HTTP connection timeout or network error | HTTP transport/client observation |

When investigating an incident, do not look only at the HTTP status. Cross-reference the GraphQL outcome with the transport outcome to know whether the failure happened before or during operation execution.

## 14. Protecting Data and Limiting Observability Costs

GraphQL documents and variables can contain user data, search filters, or business information. Do not log full documents, variables, or tokens into default metrics or traces.

Principles to apply:

- Use controlled operation names if you want to rely on them for tracing; by default, operation name is high-cardinality.
- Do not add raw queries or variable values to metric tags.
- Do not put emails, access tokens, session IDs, or personal data into low-cardinality keys.
- Keep GraphQL error messages free of secrets because errors can become span events.
- Consider trace sampling based on traffic volume and criticality.
- Restrict access permissions to metrics, traces, and Actuator endpoints.
- Do not arbitrarily rename observations if dashboards/alerts depend on current names.

Detailed instrumentation can generate many spans if an operation has many field resolvers. Enable enough to diagnose issues while monitoring CPU, memory, storage, and ingestion costs of the observability system.

## 15. Testing GraphQL Observations

You should test both conditions: the GraphQL operation actually runs and the observation is recorded in the registry. You can use `SimpleMeterRegistry` in the test context to verify timers, or `TestObservationRegistry` to inspect observation lifecycle and key-values.

Conceptual test example using a meter registry:

~~~java
@Test
void recordsGraphQlRequestObservation() {
    // Arrange: GraphQL test application with ObservationRegistry
    // and SimpleMeterRegistry wired to observation handlers.

    graphQlTester.document("""
            query FindBook {
                book(id: "book-42") {
                    id
                }
            }
            """)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

    Timer timer = meterRegistry.find("graphql.request")
        .tag("graphql.operation.type", "query")
        .tag("graphql.outcome", "SUCCESS")
        .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

This snippet assumes the test application has configured ObservationRegistry, a meter handler, and a GraphQL test client. Meter and tag names should be verified against the actual registry/version. With Prometheus, metric names may be converted according to naming conventions.

Cases to test:

1. A successful query creates a request observation with operation type query and outcome SUCCESS.
2. Mutations and subscriptions have their corresponding operation types.
3. GraphQL errors set the outcome to REQUEST_ERROR or INTERNAL_ERROR based on error type.
4. Unparseable request documents are classified properly.
5. Custom conventions preserve default keys and add the expected keys.
6. No user IDs or raw variables appear in metric tags.
7. HTTP and GraphQL observations have linked trace context when supported by the transport.

## 16. Common Implementation Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `graphql.request` meter not found | Missing ObservationRegistry or instrumentation not configured | Check Actuator, GraphQL auto-configuration, and registry |
| HTTP metrics exist but no GraphQL metrics | Only transport instrumentation is present | Check GraphQL observation auto-configuration |
| Metrics exist but no traces | Missing tracing bridge/exporter or sampling dropped the trace | Check Micrometer Tracing and exporter |
| Request returns HTTP 200 but GraphQL outcome is REQUEST_ERROR | GraphQL response contains errors | Check the GraphQL error list and resolvers |
| Metrics time series count grows rapidly | Putting operation name, ID, or field path into low-cardinality tags | Move unbounded metadata to high-cardinality or remove it |
| Trace splits into multiple traces | Transport context propagation is not working | Check HTTP instrumentation and the `micrometer.observation` key |
| DataFetcher observation does not appear for every field | Simple property fetchers are not considered non-trivial | Expected behavior; observe resolvers that perform real execution work |
| Custom convention is not used | Bean has wrong interface or custom instrumentation replaced auto-config | Check bean type and auto-configuration conditions |
| Trace contains sensitive data | GraphQL error messages or custom key-values contain private info | Sanitize errors and remove sensitive data |

## 17. Implementation Checklist

- Does the application have a configured `ObservationRegistry`?
- Does Spring Boot auto-configure GraphQL observation instrumentation?
- Does the `graphql.request` observation appear when sending a query?
- Are `graphql.operation.type` and `graphql.outcome` recorded correctly?
- Is high-cardinality metadata kept out of metrics?
- Are `graphql.datafetcher` and `graphql.dataloader` enabled if deep analysis is needed?
- Are HTTP transport and GraphQL observations linked in traces?
- Do custom conventions keep default keys and only add keys with finite cardinality?
- Are GraphQL error messages free of tokens or sensitive data?
- Are metrics/traces exported with appropriate sampling?
- Are Actuator endpoints protected?
- Are there tests verifying observations and outcomes for both successful and error requests?

The `graphql.request` observation provides visibility at the GraphQL operation level: processing duration, operation type, outcome, and execution identifier. Combining it with `graphql.datafetcher`, `graphql.dataloader`, and transport observations helps trace the root cause of slowdowns or failures from the protocol layer down to resolvers and batch loading. In Spring Boot, leverage auto-configuration and customize via convention beans; keep low-cardinality key-values small, avoid putting sensitive data into traces/metrics, and write tests to ensure observations accurately reflect API behavior.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — DefaultExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
