# graphql.loader.name

When a GraphQL query returns multiple objects with relationships, each object may need to load additional related data. If each field resolver calls a repository or service individually, the application easily runs into N+1 queries. Spring for GraphQL supports `DataLoader` and `@BatchMapping` to group data fetches into batches.

Starting in Spring for GraphQL 1.4.0, instrumentation creates an additional DataLoader observation named `graphql.dataloader`. This observation carries the `graphql.loader.name` key to identify the DataLoader that performed the batch. It is a low-cardinality key, suitable for grouping metrics and traces by loader.

This lesson explains the meaning of `graphql.loader.name`, how Spring names DataLoaders, how to assign stable names using `BatchLoaderRegistry`, how to read outcomes and batch sizes, and how to use that metadata to locate bottlenecks in batch loading flows.

## 1. Why Do We Need to Identify Each DataLoader?

Suppose a library API returns a list of books along with each book's author:

```graphql
type Query {
  books: [Book!]!
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

If the `Book.author` field resolver queries the database for each book, a query fetching 100 books can generate:

- One query to load the list of books.
- 100 separate queries to load authors.

This is the N+1 problem. DataLoader defers `load(key)` calls, groups keys within the same GraphQL execution, and invokes the batch loader once for the group. In the example above, instead of 100 author queries, the application can load authors with a single query using a `WHERE id IN (...)` condition.

In a large API, there can be many different DataLoaders:

- `authorById` loads authors by ID.
- `reviewsByBookId` loads reviews by book.
- `permissionsByUserId` loads permissions by user.
- `inventoryBySku` loads inventory by SKU.

When a GraphQL request is slow, knowing only the total request duration is not enough to identify which batch loader is slow or failing frequently. `graphql.loader.name` separates observations per loader for more accurate investigation.

## 2. Distinguishing Observation Name and the graphql.loader.name Key

These two values serve different roles:

| Value | Meaning |
| --- | --- |
| `graphql.dataloader` | Name of the DataLoader observation |
| `graphql.loader.name` | Key identifying the name of the DataLoader being observed |

Do not confuse `graphql.loader.name` with:

- GraphQL operation names such as `BookDetails`.
- GraphQL field names such as `author` or `reviews`.
- The overall request observation name `graphql.request`.
- The DataFetcher observation name `graphql.datafetcher`.

For example, a trace might contain:

```text
graphql.request
  graphql.datafetcher
  graphql.dataloader [graphql.loader.name=authorById]
  graphql.dataloader [graphql.loader.name=reviewsByBookId]
```

One request can produce multiple DataLoader observations. Each observation represents one batch loading operation tracked by instrumentation; the `graphql.loader.name` key tells you which loader executed that operation.

## 3. Default Metadata of the DataLoader Observation

Spring for GraphQL uses `DefaultDataLoaderObservationConvention` with `DataLoaderObservationContext` to produce metadata for `graphql.dataloader`.

Default keys:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.loader.name` | Low | Name of the DataLoader used |
| `graphql.outcome` | Low | Operation outcome: `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Class name of the DataLoader error, if any |
| `graphql.loader.size` | High | Size of the list of elements loaded |

### Low-Cardinality Key

`graphql.loader.name` is a required low-cardinality key. It should have a finite, stable, and predictable set of values, for example:

```text
authorById
reviewsByBookId
inventoryBySku
permissionsByUserId
```

Micrometer uses low-cardinality values for metric tags and can also include them in trace metadata. Thus, loader names can be used to group invocation counts, processing times, and error counts per batch loader.

### High-Cardinality Key

`graphql.loader.size` is a high-cardinality key. It describes the number of elements loaded in the batch. This value is useful when inspecting individual traces to see how many items a batch processed.

Do not treat `graphql.loader.size` as a metric tag equivalent to `graphql.loader.name`. High-cardinality values should not be used as meter tags in the usual way because each distinct value can create another time series. If you need batch size distributions in metrics, design a dedicated histogram or meter with clear cardinality bounds.

## 4. How Are DataLoader Names Generated?

Spring for GraphQL manages batch loaders via `BatchLoaderRegistry`. When registering by type pair:

```java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            // Return Mono<Map<Long, Author>>.
        });
```

The default DataLoader name is based on the class name of the target value type, which in this example is `Author`. This allows `@SchemaMapping` to accept a `DataLoader<Long, Author>` parameter by generic type without manually specifying a name in the common case.

You can specify an explicit name via `RegistrationSpec.withName(String)` or start registration with `BatchLoaderRegistry.forName(String)`. When naming manually, the name must match how the DataLoader is looked up and injected into resolvers.

### Registering by Explicit Name

Example using the name `authorById`:

```java
@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.<Long, Author>forName("authorById")
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds)
                                .collectMap(Author::id));
    }
}
```

The resolver uses the same name as the parameter name:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorById) {

        return authorById.load(book.authorId());
    }
}
```

`forName("authorById")` registers the loader under a specific name. Spring for GraphQL uses that name to look up the corresponding loader in the request-scoped `DataLoaderRegistry`. With name-based injection, the `DataLoader` parameter name in the handler must match the registered name; ensure the compiler preserves parameter names or configure parameter names appropriately.

### Registering by Type Pair and Renaming

If you want to register by key/value types while still controlling the name:

```java
registry.forTypePair(Long.class, Author.class)
        .withName("authorById")
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id));
```

Custom names keep metadata cleaner than fully qualified class names like `com.example.library.Author`. When packages change or classes are refactored, a stable logical name prevents dashboards and metric queries from breaking unexpectedly.

## 5. @BatchMapping Also Creates DataLoader Observations

For simple cases, `@BatchMapping` is a more concise way than manually registering a loader and writing a resolver that calls `DataLoader.load`:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        return authorService.findByBooks(books)
                .collectMap(AuthorEntry::book, AuthorEntry::author);
    }
}
```

Spring for GraphQL registers the batch loading function and corresponding DataFetcher for the `Book.author` field. Instrumentation tracks both `@BatchMapping` calls and manually registered DataLoaders, so both can produce `graphql.dataloader` observations.

`@BatchMapping` can auto-generate a loader name from type and mapping info. If you want explicit control over the DataLoader name for easier observability, consider registering via `BatchLoaderRegistry`. Either way, check the actual `graphql.loader.name` value in traces or meters after running a sample request.

## 6. Enabling DataLoader Observations

DataLoader observations are provided by `GraphQlObservationInstrumentation`. Observations are only emitted when the application has an `ObservationRegistry` and the instrumentation is attached to the GraphQL runtime.

### Spring Boot

With the Spring Boot starter, ensure Micrometer Observation infrastructure is configured and `ObservationRegistry` is present in the application context. Boot integrates instrumentation into the GraphQL source via the auto-configuration for your Boot version. If your application has custom `GraphQlSource` configuration, verify that instrumentation is not bypassed when building the source manually.

### Standalone GraphQlSource

For applications building `GraphQlSource` manually, you can add the instrumentation:

```java
import java.util.List;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureRuntimeWiring(runtimeWiringConfigurer)
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)))
        .build();
```

This example uses the single-argument constructor to apply default observation conventions. If configuring instrumentation manually, verify that the application is not simultaneously adding an equivalent instrumentation elsewhere, which would cause duplicate observations.

### Supported Versions

`DataLoaderObservationContext` and `DataLoaderObservationConvention` were introduced in Spring for GraphQL 1.4.0. In earlier versions, `graphql.dataloader` and `graphql.loader.name` are not available by default. Check the actual version before creating dashboards or alerts based on this key.

## 7. Reading Metrics by graphql.loader.name

Because `graphql.loader.name` is a low-cardinality key, Micrometer can use it as a tag to group timers/counters for DataLoader observations. Meter names and tag normalization depend on the registry/exporter, so check the actual output from Prometheus, OTLP, or your monitoring backend.

A conceptual metric series looks like:

```text
graphql.dataloader
  graphql.loader.name = authorById
  graphql.outcome = SUCCESS
```

Grouping metrics by loader lets you answer:

- Which loader is invoked most frequently?
- Which loader has high average or percentile processing times?
- Which loader has a high `ERROR` rate?
- After a deployment, which loader's batch duration increased noticeably?
- Which loaders does a query typically invoke?

Do not look only at invocation counts. A loader might be called infrequently while each batch loads massive amounts of data or waits a long time on a downstream system. Combine duration, outcome, and traces to understand the root cause.

### Example Data Interpretation

Suppose a dashboard shows:

| Loader | Observations | Errors | p95 duration |
| --- | ---: | ---: | ---: |
| `authorById` | 2.400 | 3 | 18 ms |
| `reviewsByBookId` | 800 | 72 | 240 ms |
| `inventoryBySku` | 1.100 | 2 | 35 ms |

`reviewsByBookId` has significantly higher errors and p95 latency. This is a signal to open corresponding traces and inspect batch sizes, database queries, cache hit rates, and dependencies behind that loader.

These numbers only illustrate how to read a dashboard. They are not defaults or benchmarks for Spring GraphQL.

## 8. Using graphql.loader.size in Traces

`graphql.loader.size` is a high-cardinality key describing the number of elements loaded in a batch. It helps distinguish scenarios:

- Small batch but slow: possible slow backend, exhausted connection pool, or poor query plan.
- Large batch and slow: possible large payload, overly broad query, or unsuitable batch limit.
- Batch size of 0: no matching data found for the requested keys, depending on the batch loader type and returned results.
- Batch size fluctuates widely across requests: unstable client query shapes or page sizes.

With `DataLoaderObservationContext`, instrumentation can access the running DataLoader, requested keys, batch environment, and result list. The default convention uses that information to build metadata.

Do not turn `graphql.loader.size` into a label/tag on all metric time series. If you want to track batch size distributions, create a separate histogram with bounded buckets, such as `1–10`, `11–50`, `51–100`, and `100+`. This lets you monitor batch sizes without spawning a new time series for every distinct integer.

## 9. Understanding Outcome and Error Type

DataLoader observations include two additional low-cardinality keys:

| Key | Value |
| --- | --- |
| `graphql.outcome` | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Class name of the error when batch loading fails |

Example:

```text
graphql.dataloader
  graphql.loader.name = authorById
  graphql.outcome = ERROR
  graphql.error.type = DataAccessResourceFailureException
```

When a batch loader fails, check:

1. Which loader threw the error via `graphql.loader.name`.
2. Which error category it belongs to via `graphql.error.type`.
3. Which trace and parent GraphQL request the error occurred in.
4. Whether the batch size was unusual.
5. Which dependency sits behind the batch loader.

`graphql.error.type` is the class name, not the exception message. Do not replace it with an exception message containing SQL, IDs, tenants, or dynamic input data in metric tags.

## 10. Loader Names and Cardinality

DataLoader names often become tag values in metrics. Therefore, names must be stable over time and bounded in count.

### Recommended

```text
authorById
reviewsByBookId
inventoryBySku
permissionsByUserId
```

### Not Recommended

```text
authorById-user-839102
reviews-book-2026-11-20T10:15:00Z
inventory-tenant-<tenant-id>
loader-<random-uuid>
```

Do not include the following values in loader names:

- User ID, tenant ID, or account ID.
- Request ID, trace ID, or random UUIDs.
- Book ID, SKU, or the list of keys in a batch.
- Timestamps, query strings, or GraphQL variables.
- Table/database names concatenated from untrusted input.

Dynamic values cause cardinality to grow rapidly. Every new value can create a new time series, consuming memory and processing resources in Prometheus or your metrics backend. When you need to trace a specific request, use trace IDs and high-cardinality trace attributes according to your system's security policy; do not embed them into `graphql.loader.name`.

### Naming by Business Purpose

A name like `authorById` expresses the data-loading purpose. A name like `com.example.persistence.AuthorEntity` reflects implementation and can change during refactoring. Prefer short, stable logical names that clearly distinguish different batch loaders.

If two loaders have different behavior or dependencies, do not share the same name just because they return the same Java type. Use distinct names so dashboards can separate their latency and error rates.

## 11. Customizing DataLoaderObservationConvention

If the default naming convention does not fit, Spring for GraphQL lets you customize metadata using `DataLoaderObservationConvention`. The default implementation is `DefaultDataLoaderObservationConvention`.

With Spring Boot, the preferred integration method is providing a custom convention as a bean for GraphQL observation instrumentation to pick up. In standalone setups, pass the convention into `GraphQlObservationInstrumentation`.

Starting in Spring for GraphQL 1.4.0, the full instrumentation constructor accepts four arguments (registry plus three conventions):

```java
new GraphQlObservationInstrumentation(
        observationRegistry,
        requestObservationConvention,
        dataFetcherObservationConvention,
        dataLoaderObservationConvention);
```

The older three-argument constructor was deprecated in 1.4.0 in favor of the constructor that includes `DataLoaderObservationConvention`. When configuring instrumentation manually, use the newer API so you can customize DataLoader metadata as well.

`DataLoaderObservationContext` exposes information to the convention:

| Method | Information |
| --- | --- |
| `getDataLoader()` | The DataLoader executing the operation |
| `getKeys()` | List of requested keys |
| `getResult()` | List of resolved values, or an empty list if none |
| `getEnvironment()` | BatchLoaderEnvironment passed to the batch function |

A convention can use this information to normalize loader names or add metadata. However, keeping `graphql.loader.name` stable and low-cardinality is the top requirement if you intend to use this key for metrics.

Do not replace `graphql.loader.name` with a request ID or dynamic name. If you need request-specific information for traces, use high-cardinality metadata and sanitize sensitive data.

## 12. From DataLoader Observations to Diagnosing N+1

DataLoader observations make batch loading visible separately from ordinary field fetches. Starting in Spring for GraphQL 1.4, DataFetcher operations that merely delegate to a DataLoader no longer produce the same `graphql.datafetcher` observation as before; instead, the batch load is represented by `graphql.dataloader`. This reduces repetitive per-child-field spans and makes traces reflect batch operations more accurately.

When investigating N+1 or performance issues, you can follow this workflow:

1. Find `graphql.request` executions with high duration.
2. Open the trace and list child `graphql.dataloader` observations.
3. Group them by `graphql.loader.name` to see which loaders ran.
4. Compare duration, `graphql.outcome`, and `graphql.error.type`.
5. Read `graphql.loader.size` to see how many items each batch processed.
6. Open the corresponding batch loader code and inspect SQL queries, remote calls, caches, connection pools, and batch limits.

Example:

```text
graphql.request  920 ms
  graphql.dataloader [loader=authorById, size=40]       28 ms
  graphql.dataloader [loader=reviewsByBookId, size=40]  710 ms
  graphql.dataloader [loader=inventoryBySku, size=40]    45 ms
```

The trace shows the reviews batch accounts for most of the time. Looking only at the total request makes it harder to pinpoint the dependency needing optimization right away.

DataLoader observations do not by themselves prove the application has completely eliminated N+1. A resolver might still call a repository directly, or a batch loader might dispatch many small batches due to query shape, dispatch boundaries, or max batch size. Combine traces with query logs and database call counts.

## 13. Designing Dashboards and Alerts

A dashboard keyed by `graphql.loader.name` should focus on operational questions:

| Panel | Grouped by | Purpose |
| --- | --- | --- |
| Batch duration | `graphql.loader.name` | Find loaders with high latency |
| Batch call rate | `graphql.loader.name` | Spot abnormal loader activity |
| Error rate | `graphql.loader.name`, `graphql.outcome` | Detect rising loader errors |
| Error class | `graphql.loader.name`, `graphql.error.type` | Identify downstream error categories |
| Batch size distribution | Trace or dedicated histogram | See small/large batches and size distribution |

Alerts should use thresholds tailored to each loader's baseline. A batch loader reading from cache will have different expected latency than one calling an external service. Do not apply a single duration threshold uniformly across all loaders.

Example operational rules:

- Alert when the error rate of `reviewsByBookId` rises above its baseline over a time window.
- Investigate when the p95 of `authorById` increases after a deployment.
- Monitor batch sizes when a pagination change causes items per batch to spike suddenly.
- Compare total GraphQL request duration against DataLoader observation times to uncover time spent outside batch loading.

## 14. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `graphql.dataloader` not visible | Spring GraphQL older than 1.4.0 or instrumentation inactive | Check version and `ObservationRegistry`/GraphQL instrumentation |
| `graphql.request` exists but no DataLoader observations | Request does not actually use DataLoader, or custom GraphQlSource skipped instrumentation | Check batch registration and GraphQlSource |
| `graphql.loader.name` is a long class name | Using default name derived from target type | Set a logical name via `withName` or `forName` |
| DataLoader not found by name in resolver | Registration name and DataLoader parameter name do not match | Align loader name and handler parameter name |
| Metric series count grows rapidly | Loader name contains IDs or dynamic values | Use fixed business-oriented names |
| Batch size missing from metrics | `graphql.loader.size` is a high-cardinality key | Read it in traces or build a histogram with bounded buckets |
| Trace has many field spans but lacks batch spans | Incompatible instrumentation or execution bypassed DataLoader | Check version and batch execution path |
| `graphql.outcome=ERROR` with unclear cause | Haven't checked `graphql.error.type` and trace | Open trace, inspect error type and dependencies behind the loader |
| `@BatchMapping` produces unpredictable loader name | Framework derives loader name from mapping/type | Check actual value; use BatchLoaderRegistry for explicit naming |

## 15. Principles for Using graphql.loader.name

- Understand that `graphql.dataloader` is the observation name and `graphql.loader.name` is a low-cardinality key.
- Use stable, business-meaningful, bounded loader names.
- Use `BatchLoaderRegistry.withName` or `forName` when you want explicit names.
- Keep registration names synchronized with how DataLoaders are injected into handlers.
- Use `graphql.outcome` and `graphql.error.type` to analyze successes and failures.
- Use `graphql.loader.size` in traces to understand batch size; avoid turning it into an unbounded tag.
- Remember DataLoader observations were introduced in Spring for GraphQL 1.4.0.
- Verify `GraphQlObservationInstrumentation` and `ObservationRegistry` are active at runtime.
- Cross-reference traces with SQL/query logs to confirm N+1 reduction.
- Never put IDs, tenants, users, requests, or UUIDs into loader names.
- Set alert thresholds per loader baseline instead of one-size-fits-all thresholds.
- Review dashboards when renaming DataLoaders or refactoring target types.

## 16. Hands-On Exercise

Build observability for batch loading in a library API:

1. Create a query returning a list of books with authors and reviews.
2. Register DataLoaders `authorById` and `reviewsByBookId` via `BatchLoaderRegistry`.
3. Use `withName` or `forName` to assign stable names.
4. Create `@SchemaMapping` methods using those DataLoaders.
5. Configure Micrometer Observation and GraphQL observation instrumentation.
6. Send a GraphQL request fetching multiple books.
7. Verify `graphql.dataloader` observations are recorded.
8. Inspect `graphql.loader.name` to distinguish the author and reviews loaders.
9. Simulate an error in the reviews batch loader and verify `graphql.outcome` and `graphql.error.type`.
10. Open a trace and inspect `graphql.loader.size`.
11. Temporarily rename one loader to include a request ID, observe cardinality growth in a test environment, and then revert to a fixed name.
12. Compare traces before and after migrating an N+1 resolver to batch loading.

After completing this exercise, you should be able to explain why `graphql.loader.name` is a low-cardinality key, how it relates to DataLoader registration, and how to use it to identify slow or failing batch loaders.

## 17. References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — DataLoaderObservationContext API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL — DefaultDataLoaderObservationConvention API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DefaultDataLoaderObservationConvention.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)

DataLoader observations and conventions were introduced in Spring for GraphQL 1.4.0. Check Javadocs matching your application's actual dependency version, especially when using custom instrumentation or custom observation conventions.
