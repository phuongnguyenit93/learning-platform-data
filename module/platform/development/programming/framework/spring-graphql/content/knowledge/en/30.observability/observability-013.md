# High-Cardinality Keys in Spring GraphQL

A high-cardinality key is metadata whose set of distinct values is very large or cannot be bounded in advance—such as execution IDs, client-supplied operation names, field paths with aliases/indices, and batch sizes. In observability, these values are very helpful when investigating a specific request, yet unsuitable as metric tags because each new tag combination can spawn another time series.

Spring for GraphQL uses Micrometer Observation to record requests, data fetching, and DataLoaders. Default conventions classify metadata into **low cardinality** and **high cardinality**. Low-cardinality values can be used as metric dimensions; high-cardinality values are retained for traces/spans to locate the exact request or field under investigation.

## What Is Cardinality?

The cardinality of a key is the number of distinct values that key can take. For example:

| Key | Possible values | Common classification |
| --- | --- | --- |
| `graphql.operation.type` | `query`, `mutation`, `subscription` | Low cardinality |
| `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` | Low cardinality |
| `graphql.field.name` | Set of fields declared in the schema | Low cardinality |
| `graphql.loader.name` | Set of DataLoaders registered in the application | Low cardinality |
| `graphql.execution.id` | Unique ID per request execution | High cardinality |
| `graphql.operation.name` | Client-chosen operation name, which can vary widely | High cardinality |
| `graphql.field.path` | Field path, potentially containing aliases and list indices | High cardinality |
| `graphql.loader.size` | Number of keys in a batch, varying per request | High cardinality |

The key name is usually fixed; what drives cardinality are the distinct values. For example, `graphql.execution.id` is a single key, yet almost every request has a unique value.

## Why Is High Cardinality Dangerous for Metrics?

Metrics systems store time series keyed by metric name and tag set. If you add `userId`, `requestId`, or full field paths into tags, every new value can create a new time series. With many requests and tag combinations, the number of series grows rapidly, driving up RAM, CPU, storage capacity, and query costs.

Consider a metric with dimensions `field`, `tenant`, `requestId`, and `outcome`. `field` and `outcome` normally have small value sets, whereas `tenant` may have thousands of values and `requestId` changes on nearly every request. Combining these dimensions multiplies the number of time series rather than adding them.

Therefore, separate the purposes of the two telemetry types:

- **Metrics:** aggregate request counts, error rates, mean/p95 latencies, which fields are frequently slow, and which loaders frequently fail.
- **Traces:** which operation a specific request ran, which field path was slow, which execution ID it had, and how many keys the batch contained.

Do not put high-cardinality values into metric tags merely for convenient dashboard filtering. When you need to trace a specific case, use trace ID or execution ID to locate the corresponding trace.

## Low and High Cardinality in Micrometer Observation

An `Observation` can hold two groups of `KeyValues`: low cardinality and high cardinality. The convention decides which metadata belongs to which group.

| Group | Metrics | Traces |
| --- | --- | --- |
| Low cardinality | Used as metric dimensions/tags. | Can be kept on spans to filter and group traces. |
| High cardinality | Not added to default metric tags. | Kept as span attributes for detailed investigation. |

This classification is an important instrumentation contract. When writing a custom convention, never put user IDs, request IDs, raw arguments, or unbounded values into `getLowCardinalityKeyValues(...)`. Use `getHighCardinalityKeyValues(...)` if the data is genuinely needed in traces and contains no sensitive information.

## Default High-Cardinality Keys in Spring for GraphQL

`GraphQlObservationInstrumentation` creates three main observation types in modern versions of Spring for GraphQL:

| Observation | Purpose | Default high-cardinality keys |
| --- | --- | --- |
| `graphql.request` | Measure entire GraphQL request execution. | `graphql.execution.id`, `graphql.operation.name` |
| `graphql.datafetcher` | Measure non-trivial data fetching operations. | `graphql.field.path` |
| `graphql.dataloader` | Measure batch loader calls. | `graphql.loader.size` |

Accompanying low-cardinality keys allow aggregating metrics:

| Observation | Default low-cardinality keys |
| --- | --- |
| `graphql.request` | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | `graphql.error.type`, `graphql.field.name`, `graphql.outcome` |
| `graphql.dataloader` | `graphql.error.type`, `graphql.loader.name`, `graphql.outcome` |

Request `graphql.outcome` takes `SUCCESS`, `REQUEST_ERROR`, and `INTERNAL_ERROR`. DataFetcher and DataLoader use `SUCCESS` or `ERROR`. `graphql.operation.type` is `query`, `mutation`, `subscription`, or `operation` if the document cannot be parsed.

`graphql.datafetcher` is recorded only for non-trivial fetch operations. Reading a simple property on a Java object usually does not create a dedicated observation. `graphql.dataloader` tracks `@BatchMapping` methods and manually registered DataLoaders. Dedicated DataLoader observations were added in Spring for GraphQL 1.4; on older versions, the observation set and how batches are distinguished may differ.

## Understanding Each High-Cardinality Key

### `graphql.execution.id`

Execution ID identifies a single GraphQL execution. It is helpful when a request has multiple concurrent field fetches and you need to group spans belonging to the same run.

For example, a book search request can generate a unique execution ID and then create spans for the root query, data fetchers, and batch loaders. When investigating that request, the execution ID helps find the exact trace in your tracing backend.

Do not use execution ID as a metric tag. Each new request typically produces a new ID, causing time series counts to grow with request count.

### `graphql.operation.name`

Operation name is the name placed by the client in the document:

```graphql
query BookCatalogPage {
  books(first: 50) {
    id
    title
    author {
      name
    }
  }
}
```

The name `BookCatalogPage` helps operators recognize the operation in a trace. However, GraphQL clients can send many different operation names, even dynamically generated ones. Thus, Spring for GraphQL treats operation name as high cardinality.

Metrics should group by `graphql.operation.type` to track proportions of queries, mutations, and subscriptions. Traces can retain `graphql.operation.name` to identify specific documents. Even if an application only accepts a fixed list of operations, keep the default classification to avoid changing the metrics contract when new clients deploy.

### `graphql.field.path`

Field name only identifies the field's name, whereas field path indicates the field's position in the response tree. In a query with lists and aliases, the path can differ across branches or elements:

```graphql
query AuthorDashboard {
  featured: books(first: 20) {
    id
    writer: author {
      name
    }
  }
}
```

`graphql.field.name` can show the field being fetched is `author`; `graphql.field.path` pinpoints that it sits under the aliases `featured` and `writer`, or belongs to a specific list element. This detail is especially valuable when a resolver is slow only on one query branch.

Field paths can contain aliases, list indices, or path segments dependent on response structure. Therefore, use paths in traces for diagnosis; use `graphql.field.name` to aggregate metrics.

### `graphql.loader.size`

Loader size is the number of elements grouped into a single batch invocation. In a trace, this value helps verify whether the batch actually grouped multiple keys or only received one key at a time.

For instance, a query fetches 50 books and each book needs author details. One batch can receive multiple author IDs instead of querying the repository 50 times. `graphql.loader.size` reveals the actual key count of that batch.

This numeric value can vary with page size, duplicate relationships, `maxBatchSize`, and dispatch waves. Do not add every specific size as a metric tag. If you need to analyze batch size distributions over time, record a separate `DistributionSummary` with a fixed loader tag, as shown later.

## Observing a GraphQL Trace

Suppose a client calls the `BookCatalogPage` operation to fetch 50 books and their authors. A trace might exhibit a structure similar to:

```text
HTTP POST /graphql
└── graphql.request
    ├── graphql.operation.type = query
    ├── graphql.operation.name = BookCatalogPage
    ├── graphql.execution.id = <unique execution id>
    ├── graphql.datafetcher
    │   ├── graphql.field.name = books
    │   └── graphql.field.path = /books
    └── graphql.dataloader
        ├── graphql.loader.name = authors
        └── graphql.loader.size = 37
```

This diagram is illustrative. A single request can produce multiple DataFetcher spans and multiple batch spans due to multiple fields, branches, or batch size limits. Do not assume a GraphQL request always performs only one batch.

In the trace backend, you can filter by operation name to find a group of requests, open an execution ID to inspect a single run, and then examine field paths or loader sizes on individual spans. This bridges aggregate signals in metrics to root causes in a concrete request.

## Sending High-Cardinality Data to Traces

In Spring Boot, the Spring GraphQL starter and observability auto-configuration configure `GraphQlObservationInstrumentation` when an `ObservationRegistry` is available. For applications not using Spring Boot, register this instrumentation when building `GraphQlSource`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

@Configuration(proxyBeanMethods = false)
public class GraphQlObservabilityConfiguration {

    @Bean
    GraphQlSource graphQlSource(
            ObservationRegistry observationRegistry,
            AnnotatedControllerConfigurer controllerConfigurer) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
                .configureRuntimeWiring(controllerConfigurer)
                .configureGraphQl(builder -> builder.instrumentation(
                        new GraphQlObservationInstrumentation(observationRegistry)))
                .build();
    }
}
```

This is a minimal configuration for applications managing `GraphQlSource` directly. In a real application, include the remaining `RuntimeWiringConfigurer` beans, exception resolvers, and schema configuration. `ObservationRegistry` must also be wired to appropriate meter/tracing handlers so data is exported to backends. If Spring Boot already configures instrumentation, do not register a duplicate copy.

Observations can generate metrics and/or traces depending on `ObservationRegistry` and configured handlers. Having an `ObservationRegistry` enables recording observations; to view distributed spans, the application also needs a Micrometer Tracing bridge and exporter matching your tracing system. Enabling only a metrics registry does not automatically create a trace backend.

## Adding High-Cardinality Metadata via Conventions

When you need to attach dynamic details to traces, extend an observation convention and place the data in the high-cardinality group. The following example adds the field alias to DataFetcher spans:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlObservationConventionConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {
            @Override
            public KeyValues getHighCardinalityKeyValues(
                    DataFetcherObservationContext context) {
                KeyValues values = super.getHighCardinalityKeyValues(context);
                String alias = context.getEnvironment().getField().getAlias();
                return (alias != null)
                        ? values.and(KeyValue.of("graphql.field.alias", alias))
                        : values;
            }
        };
    }
}
```

This example is only appropriate when aliases genuinely aid trace investigation. Aliases are client-controlled data; never move them into `getLowCardinalityKeyValues(...)`. In Spring Boot, providing the convention as a bean is the recommended integration approach. If you do not need custom metadata, keeping the default convention is simpler and more stable.

Do not add raw GraphQL documents, full variables, emails, access tokens, or personal data to span attributes. High cardinality does not mean sensitive data is permitted in a tracing system. Trace backends also require appropriate access controls and retention periods.

## When You Need Batch Size Statistics in Metrics

`graphql.loader.size` is high cardinality by default and serves only traces. If dashboards need average batch size, distribution, or p95 per loader, record a dedicated `DistributionSummary` with a fixed-set `loader` tag:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuthorBatchMetrics {

    private final DistributionSummary batchSize;

    public AuthorBatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary.builder("graphql.dataloader.batch.size")
                .description("Number of keys in each author batch load")
                .baseUnit("keys")
                .tag("loader", "authors")
                .register(registry);
    }

    public void recordBatchSize(int size) {
        this.batchSize.record(size);
    }
}
```

Call `recordBatchSize(keys.size())` at the start of the batch loader method. `loader=authors` is a tag with a finite value set; the size is recorded as a sample of the DistributionSummary rather than as a tag value. With multiple loaders, use one bean or meter per registered loader, and never use request ID or user ID as a tag.

## Checking for and Finding Abnormal High Cardinality

When metrics grow faster than expected, inspect meter tags and custom conventions:

1. Identify the metric name whose time series count surged.
2. Check whether tag values are request IDs, user IDs, tenant IDs, operation names, full paths, or values from GraphQL arguments.
3. Audit custom `ObservationConvention`, `ObservationFilter`, `MeterRegistryCustomizer`, and code that manually records meters.
4. Move dynamic values to high-cardinality span attributes if genuinely needed for investigation; otherwise remove them if they hold no operational value.
5. Use finite categories or route/field templates for metric dimensions.

Micrometer provides `HighCardinalityTagsDetector` to warn when a meter name creates too many meters. `MeterFilter.maximumAllowableTags(...)` can act as a last-resort guardrail for a custom meter, though it does not replace classifying metadata properly in the convention from the start.

## Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Time series count grows continuously | Request ID, user ID, execution ID, or full path put into metric tags. | Remove the dynamic tag or move it to a high-cardinality span attribute. |
| `graphql.execution.id` missing from `/actuator/metrics` | It is a high-cardinality key, not exported as a default metric tag. | Look up the execution ID in the trace backend. |
| Cannot filter by field path in Prometheus | `graphql.field.path` is reserved for traces under the default convention. | Use `graphql.field.name` for metrics; open traces to see the full path. |
| `graphql.loader.size` missing on metrics dashboards | Loader size is high cardinality and only added to traces by default. | Use span attributes or record a DistributionSummary with a fixed loader tag. |
| Metrics exist but no traces | Micrometer Tracing bridge/exporter or tracing handler not configured. | Check tracing dependencies, exporter, and sampling. |
| Trace has no GraphQL spans | ObservationRegistry or `GraphQlObservationInstrumentation` not configured, or instrumentation overwritten/misconfigured. | Check Boot auto-configuration or manual `GraphQlSource` setup. |
| Field path missing for some fields | Simple property fetchers on Java objects are trivial and not separately observed. | Use traces of non-trivial DataFetchers or custom instrumentation if justified. |
| Aliases cause rapid growth in distinct values | Client creates dynamic aliases and aliases/paths were added to metric tags. | Keep aliases only in traces; metrics use field name. |

## Key Takeaways

High-cardinality keys hold values that can vary widely, such as execution IDs, operation names, field paths, and loader sizes. Spring for GraphQL pre-classifies these keys for use in traces, while keys with finite value sets—such as operation type, field name, loader name, and outcome—suit metrics.

Keep dynamic identifiers and full paths in traces to investigate individual requests. Use metrics to aggregate throughput, latency, and errors along stable dimensions. If you need batch size distributions, record values via a DistributionSummary rather than turning every size into a tag. When extending observation conventions, always separate low and high cardinality, and strip sensitive information from both metrics and traces.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — `GraphQlObservationInstrumentation` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Spring Boot — Metrics and Tracing](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
