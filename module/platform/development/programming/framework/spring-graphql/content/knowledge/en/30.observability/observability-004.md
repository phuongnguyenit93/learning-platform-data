# Observing GraphQL DataLoader in Spring for GraphQL

DataLoader helps group multiple related data fetches into batches to mitigate the N+1 problem. However, merely knowing that a query returned the right data is not enough to evaluate whether batching is effective. You need to know which batch loader was called, how long it took, how many elements it returned, and whether any errors occurred.

Spring for GraphQL integrates Micrometer Observation to record DataLoader activity using an observation named `graphql.dataloader`. This observation covers `@BatchMapping` methods and manually registered `DataLoader` instances. It adds a dedicated perspective on batch loading alongside observations for the overall GraphQL request and non-trivial DataFetchers.

## 1. Why Do We Need to Observe DataLoader?

Suppose a query loads 40 orders and also selects customer details for each order:

```graphql
query Orders {
    orders {
        id
        customer {
            id
            name
        }
    }
}
```

If each `Order.customer` field queries the repository individually, the server may execute one query to load the list of orders plus 40 queries to load customers. This is the N+1 problem.

With `@BatchMapping` or `DataLoader`, customer IDs are grouped and loaded in batches. When properly observed, a trace shows a single batch operation processing multiple keys instead of dozens of separate data-fetching operations.

Observability helps answer these questions:

- Which loader is used in a GraphQL request?
- How long does each batch load take?
- Did the batch loader succeed or fail?
- How many elements were returned in a batch load?
- Is a request performing many small batches or one large batch?
- Does the latency come from the GraphQL resolver, the batch loader, or the underlying database?

## 2. Micrometer Observation in Spring for GraphQL

Micrometer Observation is an abstraction for recording an activity in an application. `ObservationHandler` implementations can convert observations into metrics, traces, or both.

Spring for GraphQL has three main server-side observations:

| Observation | Scope | Used to observe |
|---|---|---|
| `graphql.request` | Entire GraphQL request | Request duration, operation type, and outcome. |
| `graphql.datafetcher` | Non-trivial DataFetcher | Field resolution time and resolver errors. |
| `graphql.dataloader` | Batch loading activity | Execution time of `@BatchMapping` or manual DataLoader calls. |

A single request can create one `graphql.request` observation and multiple child observations for DataFetcher or DataLoader operations. This makes it possible to drill down from a slow request to a specific operation.

Since Spring for GraphQL 1.4.0, DataLoader has its own dedicated observation. Prior to that, distinguishing regular DataFetcher work from a batch loading invocation was less clear in traces. If you need `graphql.dataloader`, verify the version of Spring for GraphQL managed by Spring Boot; versions older than 1.4.0 do not include this observation.

## 3. What Does the `graphql.dataloader` Observation Record?

Spring for GraphQL uses `GraphQlObservationInstrumentation` to create observations. For DataLoaders, the default convention is `DefaultDataLoaderObservationConvention`, based on `DataLoaderObservationContext`.

The `graphql.dataloader` observation is created when data loading occurs for:

- Controller methods using `@BatchMapping`.
- Manually registered DataLoaders, typically via `BatchLoaderRegistry`.

Each observation describes one batch loader execution. It is not an observation for every individual `DataLoader.load(key)` call on each field.

Default keys:

| Key | Cardinality | Meaning |
|---|---|---|
| `graphql.loader.name` | Low | Name of the DataLoader being used. |
| `graphql.outcome` | Low | Operation outcome: `SUCCESS` or `ERROR`. |
| `graphql.error.type` | Low | Class name of the data fetching error, if any. |
| `graphql.loader.size` | High | Number of elements in the result list returned by the DataLoader. |

`graphql.loader.size` is the number of resolved/returned elements; it should not be assumed to equal the number of `load()` calls, cache misses, or database rows read. If a batch loader omits keys that have no matching result, the number of returned elements may be smaller than the number of input keys.

## 4. Low Cardinality and High Cardinality

Micrometer divides observation key-values into two groups:

- Low cardinality: bounded number of values that can be used as metric tags.
- High cardinality: number of values can grow very large; should only be included in traces.

For `graphql.dataloader`:

- `graphql.loader.name`, `graphql.outcome`, and `graphql.error.type` are low cardinality.
- `graphql.loader.size` is high cardinality.

Therefore, you can filter metrics by loader name and outcome, while batch size can be inspected in traces. Do not expect `graphql.loader.size` to appear as a tag on default meter metrics.

Do not put values such as raw entity IDs, user IDs, tenant IDs, key lists, GraphQL variables, or query text into low-cardinality metrics. Such values can create thousands or millions of time series, increasing memory and storage costs for the metrics system; they may also contain sensitive data.

## 5. Enabling DataLoader Observations with Spring Boot

In Spring Boot, GraphQL observation instrumentation is auto-configured when an `ObservationRegistry` and the required conditions are present. Spring Boot 3.5 provides `GraphQlObservationAutoConfiguration` and supports a `DataLoaderObservationConvention` bean to customize DataLoader metadata.

Example dependencies with Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot manages compatible versions of Micrometer and Spring for GraphQL. The Prometheus dependency is only needed if you want to export metrics to Prometheus; it can be replaced with the registry for your monitoring system.

With Boot auto-configuration, you do not need to manually create another `GraphQlObservationInstrumentation` if Boot already creates the bean. The key requirement is that the application has an `ObservationRegistry`; Boot Actuator provides the observation infrastructure and appropriate meter registry.

## 6. Configuring Metrics Endpoints

To inspect metrics through Actuator and allow Prometheus scraping, expose the required endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

After the application serves a GraphQL request that executes a DataLoader, you can inspect the list of meters at:

```text
GET /actuator/metrics
```

Inspect the DataLoader observation:

```text
GET /actuator/metrics/graphql.dataloader
```

Filter by loader name:

```text
GET /actuator/metrics/graphql.dataloader?tag=graphql.loader.name:com.example.Author
```

The tag value for `graphql.loader.name` depends on the actual loader name. For a DataLoader registered through Spring's `BatchLoaderRegistry`, the default name is typically based on the target entity class; if the application customizes the name, use the registered name.

The `metrics` endpoint uses Micrometer meter names, such as `graphql.dataloader`. Names exported to Prometheus may be normalized according to the registry's naming conventions, such as converting dots to underscores and appending timer units.

## 7. Observing the Trace of a GraphQL Request

When Micrometer Tracing and a tracing exporter are configured, observations can generate spans in a distributed trace.

A trace can have a general structure like:

```text
HTTP server request
  |
  +-- graphql.request
        |
        +-- graphql.datafetcher (orders)
        |
        +-- graphql.dataloader (Customer loader)
        |
        +-- graphql.dataloader (Product loader)
```

In the trace:

- `graphql.request` shows the total GraphQL execution time.
- `graphql.datafetcher` shows the duration of non-trivial field resolvers.
- `graphql.dataloader` shows batch loading duration, loader name, outcome, and batch size metadata.

For HTTP, Spring Framework has its own instrumentation to create an HTTP server request observation and propagate tracing context. For other transports, ensure transport instrumentation and context propagation are properly configured.

## 8. Distinguishing DataFetcher Observations and DataLoader Observations

Not every field in GraphQL creates a `graphql.datafetcher` observation. Spring for GraphQL only creates DataFetcher observations for operations considered non-trivial; simple property reads from a Java object do not need a dedicated observation.

With `@BatchMapping` or manual DataLoaders, inspect `graphql.dataloader` to observe batch loading. In Spring for GraphQL 1.4 and later, DataLoader activity has its own observation, allowing traces to clearly show a single batch call rather than only field fetches.

Examples:

| Implementation style | Observed signal |
|---|---|
| `@SchemaMapping` querying repository per parent | Many DataFetcher operations, possibly showing an N+1 pattern. |
| `@BatchMapping` grouping multiple parents | `graphql.dataloader` observation for the batch load. |
| Manually registered DataLoader | `graphql.dataloader` observation for the registered batch loader. |
| Property fetcher reading a simple Java field | Typically no separate DataFetcher observation. |

When comparing traces before and after switching to batching, look at the number of operations and overall duration, not just a single isolated span.

## 9. Using Observations to Detect N+1

Suppose a query returns 30 books and selects the `author` for each book.

If the resolver loads the author for each book individually, a trace may show many fetches for the `author` field, each performing a data-loading operation. When switching to `@BatchMapping`, the parents are grouped together and a batch loader loads the required authors.

Investigation workflow:

1. Find `graphql.request` instances with high duration.
2. Open the trace and identify the `graphql.datafetcher` or `graphql.dataloader` spans taking the most time.
3. Check the loader name to see which field/data group is being loaded.
4. Compare the number of batch dispatches and `graphql.loader.size` in the trace.
5. Inspect the underlying database queries or service calls to verify the batch loader actually reduced round-trips.
6. Re-run the same operation with the same data to compare.

Conceptual comparison table:

| Metric | Per-parent resolver | Batch loading |
|---|---:|---:|
| Number of parent books | 30 | 30 |
| Individual author loads | Possibly 30 | Grouped by batch dispatch |
| Batch observations | No corresponding batch observation | Has `graphql.dataloader` observation |
| Database queries | May scale with parent count | Depends on batch loader implementation |

The observation proves that the batch loader was invoked and measures that operation's duration; it does not by itself prove that only one SQL query ran. A batch method can still contain a loop querying one key at a time. Combine database metrics, query logs, or data-access layer tracing to confirm N+1 has truly been eliminated.

## 10. Both `@BatchMapping` and Manual DataLoaders Are Observed

`@BatchMapping` example:

```java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findByIds(authorIds)
            .collectMap(Author::id)
            .map(authors -> {
                Map<Book, Author> result = new LinkedHashMap<>();
                for (Book book : books) {
                    Author author = authors.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
    }
}
```

`@BatchMapping` is a concise way to declare a batch mapping; Spring for GraphQL creates the necessary DataLoader for that field. The `graphql.dataloader` observation is created for the corresponding batch operation.

For DataLoaders manually registered via `BatchLoaderRegistry`, an observation is also created when the loader is dispatched. This enables tracking the same type of signal whether the application uses annotations or the DataLoader API directly.

## 11. Understanding `graphql.loader.size`

`graphql.loader.size` is a high-cardinality key describing the number of elements in the result list returned by the DataLoader.

For example, a batch loader receives 20 author IDs but only finds 18 authors:

```text
Input keys:       20
Resolved values:  18
graphql.loader.size: 18
```

This value is useful for inspecting batch result size in traces, though it does not always equal the number of input keys. To understand it fully, you need to know:

- How many keys were placed into the batch.
- How many values the loader returned.
- How missing keys (keys without results) are handled.
- Whether the loader uses a mapped batch loader or an ordered batch loader.
- Whether a `maxBatchSize` limit splits a set of keys into multiple dispatches.

`DataLoaderObservationContext` exposes `getKeys()`, `getResult()`, `getDataLoader()`, and `getEnvironment()` so a convention can inspect further details if needed. Avoid putting raw keys or sensitive data into metrics/traces.

## 12. Observations Are Not Cache Hit/Miss Metrics

DataLoader maintains a per-request cache. If a key is requested multiple times within the same execution, DataLoader can return the cached result without invoking the batch loader again.

`graphql.dataloader` observes the batch loader execution when it runs. It is not a counter for every `load(key)` call and does not out of the box provide metrics for:

- Total `DataLoader.load()` calls.
- Cache hit count.
- Cache miss count.
- Number of deduplicated keys.
- Actual SQL query count.

Therefore, you cannot infer the exact cache hit ratio solely from the count of `graphql.dataloader` observations. If you need cache hit/miss metrics, add appropriate instrumentation at the DataLoader/cache layer or record counts using a custom metric with controlled cardinality.

## 13. Customizing Metadata with `DataLoaderObservationConvention`

Spring for GraphQL uses `DefaultDataLoaderObservationConvention` to generate default key-values. Starting in Spring for GraphQL 1.4.0, you can provide a custom `DataLoaderObservationConvention` to add or modify metadata.

In Spring Boot, declaring a convention bean is the recommended way for auto-configuration to pick up that convention. The following example adds a fixed label describing the application's loader group:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DataLoaderObservationConvention;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    DataLoaderObservationConvention dataLoaderObservationConvention() {
        return new DefaultDataLoaderObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    DataLoaderObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.loader.group", "catalog"));
            }
        };
    }
}
```

This is an example for an application with a catalog loader group. The value `catalog` is fixed, so its cardinality is low. If you need to group multiple loaders, map them to a small controlled set of groups such as `catalog`, `identity`, or `billing`.

Do not add `userId`, `tenantId`, email, raw entity IDs, or key lists to low-cardinality keys. If you want to include unbounded information in traces, consider high-cardinality keys and a data masking policy before recording.

## 14. Does Customizing the Convention Require Replacing `GraphQlObservationInstrumentation`?

When using Spring Boot, convention beans are discovered by auto-configuration. Usually there is no need to manually create `GraphQlObservationInstrumentation` just to alter DataLoader metadata.

For applications that configure `GraphQlSource` manually, you can register the instrumentation on `GraphQlSource.Builder`:

```java
GraphQlObservationInstrumentation instrumentation =
    new GraphQlObservationInstrumentation(observationRegistry);

graphQlSourceBuilder.instrumentation(List.of(instrumentation));
```

If creating instrumentation manually in a Boot application that already has auto-configuration, inspect the instrumentation list before adding to avoid duplicate configuration. Starting from Spring for GraphQL 1.4.0, the constructor supporting custom conventions takes all four parameters: `ObservationRegistry`, request convention, DataFetcher convention, and DataLoader convention.

## 15. Combining DataLoader Observations with Database Metrics

The `graphql.dataloader` observation measures batch loading activity at the GraphQL layer. Database metrics measure activity at the persistence layer. The two perspectives complement each other:

| Signal | Question answered |
|---|---|
| `graphql.request` | How long did the GraphQL request take? |
| `graphql.datafetcher` | Which field resolver is slow or failing? |
| `graphql.dataloader` | Which batch loader is slow, succeeding, or failing? |
| JDBC/R2DBC metrics | Are there issues with database connections or data access operations? |
| SQL/query tracing | How many SQL statements did the batch loader run and which ones are slow? |

If `graphql.dataloader` takes 300 ms while the database query takes only 10 ms, the remaining time may be spent in mapping, data processing, a remote service, or logic inside the batch method. If the batch observation is fast but the GraphQL request is slow, inspect other resolvers, serialization, network, or fields that do not use DataLoader.

Do not guess the cause from a single timer. Correlate the trace with the request, loader name, and database spans to pinpoint where time is spent.

## 16. Verifying Metrics in Tests

You can verify recorded observations using a `MeterRegistry` in integration tests. The test should execute a GraphQL query with a batched field, then read the `graphql.dataloader` timer filtered by loader name.

Conceptual example with `MeterRegistry`:

```java
Timer timer = meterRegistry.find("graphql.dataloader")
    .tag("graphql.loader.name", Author.class.getName())
    .tag("graphql.outcome", "SUCCESS")
    .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isPositive();
```

For reliable tests:

1. Use a test-dedicated registry or control the registry injected by Spring Boot.
2. Execute an operation selecting a `@BatchMapping` field.
3. Wait for GraphQL execution to complete before reading the timer.
4. Filter by loader name and outcome to avoid picking up observations from other operations.
5. Do not assert exact durations since timings depend on the test environment.

If tests share a single registry across multiple test cases, reset the registry or isolate contexts so stale counts do not cause false passes.

## 17. Frequently Asked Diagnostic Questions

**`graphql.dataloader` does not appear:** verify Spring for GraphQL is version 1.4.0 or later; check whether `ObservationRegistry` is present; check whether `GraphQlObservationInstrumentation` is configured; verify the query actually selects the batched field.

**`graphql.datafetcher` appears but `graphql.dataloader` does not:** the field may be using a regular `@SchemaMapping` instead of `@BatchMapping` or a DataLoader; or the batch loader was not registered/dispatched.

**`graphql.loader.size` does not appear in metrics:** this is a high-cardinality key, which by default is only included in traces. Inspect spans or traces instead of looking for metric tags.

**Batch observation has outcome `ERROR`:** check exceptions from the batch method, downstream databases/services, and the error type. Cross-reference with `graphql.request` to see whether the error failed the whole request or only affected the field.

**Loader name is unexpected:** check the DataLoader name in `BatchLoaderRegistry` or the name generated from `@BatchMapping`; the loader may have a customized name.

**Batch size is smaller than the number of parents:** check the number of unique keys, per-request caching, `maxBatchSize`, number of dispatches, and whether the batch loader omits missing results.

**Request is slow even though batch observation is fast:** investigate the root query, other DataFetchers, database connection pools, network, and response serialization.

## 18. Common Mistakes When Designing DataLoader Observations

**Confusing an observation with the number of `load(key)` calls.** An observation represents a batch loader execution; many keys can be processed within a single observation.

**Treating `graphql.loader.size` as a low-cardinality metric tag.** It is a high-cardinality key meant only for traces under the default convention.

**Using batch size to infer SQL query count.** A batch loader might still run multiple SQL statements or call a remote service; observe the persistence layer separately.

**Forgetting to check the Spring GraphQL version.** DataLoader observations were introduced in 1.4.0. Applications on older versions cannot expect this observation.

**Manually adding instrumentation when Boot already auto-configures it.** This can create duplicate configuration or complicate verification. Prefer convention beans when only metadata needs customization.

**Adding IDs or keys to metric tags.** Cardinality grows rapidly and risks leaking data. Use only controlled low-cardinality labels.

**Looking only at metrics without checking traces.** Metrics show aggregate trends; traces help locate the specific batch inside a slow request.

## Conclusion

Spring for GraphQL provides the `graphql.dataloader` observation to measure the activity of `@BatchMapping` and manually registered DataLoaders. By default, the observation records the loader name, outcome, error type, and result list size, with `graphql.loader.size` acting as a high-cardinality key for traces. When `ObservationRegistry` and GraphQL instrumentation are enabled, applications can use metrics to monitor batch frequency/duration/errors and use traces to locate slow loaders or detect N+1 patterns. The observation does not count individual `load` calls, cache hits/misses, or SQL queries, so combine it with database metrics, query tracing, and custom instrumentation when those measurements are needed.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL API — `DataLoaderObservationContext`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL API — `DataLoaderObservationConvention`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationConvention.html)
- [Spring Boot 3.5 — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
