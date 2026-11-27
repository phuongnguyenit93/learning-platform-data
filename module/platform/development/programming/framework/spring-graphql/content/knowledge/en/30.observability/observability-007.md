# graphql.field.path

## Objectives

After this lesson, you will be able to:

- Explain the meaning of the `graphql.field.path` key in Spring for GraphQL.
- Distinguish `graphql.field.path` from `graphql.field.name`.
- Understand the role of the `graphql.datafetcher` observation in Micrometer.
- Read field paths in distributed traces to pinpoint slow or failing resolvers.
- Understand why field path is classified as a high-cardinality key.
- Distinguish metadata used for metrics from metadata used for tracing.
- Enable GraphQL observability using Spring Boot Actuator and Micrometer.
- Recognize the limits of DataFetcher observations and how to combine them with request/DataLoader observations.
- Design safe logging, tracing, and dashboards while avoiding cardinality explosion.

## 1. What Is graphql.field.path?

A GraphQL operation can request many nested fields. When GraphQL Java executes the operation, each field is resolved at a specific position in the response tree.

Example:

~~~graphql
query BookDetails($id: ID!) {
  bookById(id: $id) {
    id
    title
    author {
      name
      organization {
        name
      }
    }
  }
}
~~~

One request can execute DataFetchers for fields such as:

- `Query.bookById`
- `Book.author`
- `Author.organization`

Spring for GraphQL integrates Micrometer Observation to measure the duration of DataFetchers that perform real work. This observation is named `graphql.datafetcher` and carries metadata describing the field being resolved.

The `graphql.field.path` key indicates the path to the field in the execution tree, for example:

~~~text
/bookById
/bookById/author
/bookById/author/organization
~~~

With this path, when viewing the trace of a GraphQL request, you can pinpoint which resolver on which branch is taking a long time or throwing errors.

`graphql.field.path` is observability metadata. It is not a field in the GraphQL schema, not an argument sent by the client, and not a value returned in the GraphQL response.

## 2. Distinguishing graphql.field.name and graphql.field.path

Spring for GraphQL records both the field name and the field path in DataFetcher observations. These two keys answer different questions.

| Key | Meaning | Example |
|---|---|---|
| `graphql.field.name` | Name of the schema field being fetched | `author` |
| `graphql.field.path` | Position of the field in the response tree | `/bookById/author` |

Suppose a query fetches multiple sets of books:

~~~graphql
query {
  featuredBooks {
    author {
      name
    }
  }
  recentBooks {
    author {
      name
    }
  }
}
~~~

The `author` field appears in two different branches:

~~~text
/featuredBooks/0/author
/recentBooks/0/author
~~~

Both observations may share:

~~~text
graphql.field.name = author
~~~

Yet their field paths differ, helping distinguish which data branch is being resolved.

This is especially useful when the same resolver is reused in multiple places in the schema. Looking only at the field name is not enough to tell which root query or object branch invoked it.

## 3. Which Observation Contains graphql.field.path?

Spring for GraphQL provides three main observations at the GraphQL server layer:

| Observation name | Measures | Some default metadata |
|---|---|---|
| `graphql.request` | Entire GraphQL request | operation type, outcome, operation name, execution ID |
| `graphql.datafetcher` | A non-trivial DataFetcher execution | field name, field path, outcome, error type |
| `graphql.dataloader` | A DataLoader or `@BatchMapping` call | loader name, loader size, outcome, error type |

`graphql.field.path` belongs to the `graphql.datafetcher` observation.

One request can produce one `graphql.request` observation and multiple `graphql.datafetcher` observations. For instance, a Query loading a Book, then its Author and Organization, will have corresponding child spans/observations if those DataFetchers are considered non-trivial.

Conceptual diagram:

~~~mermaid
flowchart TD
    A[graphql.request] --> B[graphql.datafetcher: bookById]
    B --> C[graphql.datafetcher: author]
    C --> D[graphql.datafetcher: organization]
    C --> E[graphql.dataloader: authorLoader]
~~~

This diagram only illustrates observation relationships. The actual number of observations depends on registered DataFetchers, whether DataLoader is used, and instrumentation configuration.

## 4. Why Is Field Path a High-Cardinality Key?

A low-cardinality key typically has only a small, finite, stable set of values. For example:

- Operation type: `query`, `mutation`, `subscription`.
- Outcome: `SUCCESS`, `ERROR`.
- Field name: `bookById`, `author`, `organization`.

In contrast, field paths can vary with the query structure:

~~~text
/bookById/author
/featuredBooks/0/author
/featuredBooks/1/author
/recentBooks/0/author
/search/results/12/book/author
~~~

When queries use aliases, multiple branches, or lists with many elements, the number of paths can grow rapidly. That is why Spring for GraphQL classifies `graphql.field.path` as a high-cardinality key.

Micrometer divides metadata into:

- Low-cardinality keys: suitable for metric tags because the value set is bounded.
- High-cardinality keys: better suited for traces or logs because the number of values can be very large.

This is why understanding `graphql.field.path` clearly is essential both when analyzing traces and when designing metric dashboards.

## 5. Do Not Put graphql.field.path into Metric Tags

Metric backends like Prometheus create a time series per combination of metric name and tags. If every distinct path produced a separate metric tag, the number of time series could grow sharply.

For example, do not create metrics like this:

~~~text
graphql.datafetcher.duration{
  graphql.field.path="/books/0/author"
}
graphql.datafetcher.duration{
  graphql.field.path="/books/1/author"
}
graphql.datafetcher.duration{
  graphql.field.path="/books/2/author"
}
~~~

If a query returns thousands of items, the metric can spawn huge numbers of series solely due to differing list indices.

Micrometer Observation only uses low-cardinality key values as meter tags. High-cardinality key values like `graphql.field.path` are excluded from default metrics; they can be retained in tracing output or logging systems that handle high-cardinality metadata.

Use keys with bounded value sets for dashboard metrics:

- `graphql.field.name`
- `graphql.outcome`
- `graphql.error.type`
- `graphql.operation.type`

Use `graphql.field.path` when you need to drill down into a specific trace to locate the exact resolver branch.

## 6. Configuring Observability in Spring Boot

Spring GraphQL uses Micrometer Observation to create request and DataFetcher observations. Observations are only published when the application has an `ObservationRegistry` and GraphQL instrumentation configured.

With Spring Boot, the common approach is adding Actuator:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-actuator")
~~~

If you want to export metrics to Prometheus, add the corresponding registry:

~~~groovy
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

Spring Boot provides `ObservationRegistry` and auto-configuration for GraphQL observations when the required conditions are met. Spring Boot 3.x includes `GraphQlObservationAutoConfiguration` starting from 3.0; Spring Boot 4 continues to provide the corresponding auto-configuration in the GraphQL module.

For a standardly configured Spring Boot application, check Actuator and the observation registry before registering instrumentation manually. Do not create a second `GraphQlObservationInstrumentation` if auto-configuration already creates one.

Example configuration exposing diagnostic endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

The `/actuator/metrics` endpoint is useful for checking whether metrics have been created. The Prometheus endpoint is only available if the Prometheus registry is added and the endpoint is exposed.

### Manually Configuring GraphQlSource

If the application does not use Spring Boot's GraphQL auto-configuration and builds `GraphQlSource` manually, add `GraphQlObservationInstrumentation` to the builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResources)
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)))
        .build();
~~~

`schemaResources` and `observationRegistry` are dependencies already prepared in your application configuration. If the GraphQL runtime already has other instrumentations, include them in the same list instead of overwriting existing ones.

With Spring Boot starters, you do not need the manual builder snippet above in typical cases. Boot can automatically detect `Instrumentation` beans and add them to the `GraphQlSource` builder; GraphQL observation auto-configuration creates the instrumentation when an `ObservationRegistry` is present.

The default constructor uses Spring GraphQL's conventions, including `DefaultDataFetcherObservationConvention`, where `graphql.field.path` is created as a high-cardinality key.

## 7. Default Metadata of the DataFetcher Observation

The `graphql.datafetcher` observation uses `DataFetcherObservationContext` and `DefaultDataFetcherObservationConvention`.

Default low-cardinality keys:

| Key | Description | Example |
|---|---|---|
| `graphql.error.type` | Class name of the error when the DataFetcher fails | `AccessDeniedException` |
| `graphql.field.name` | Name of the field being fetched | `author` |
| `graphql.outcome` | Fetch outcome | `SUCCESS`, `ERROR` |

Default high-cardinality key:

| Key | Description | Example |
|---|---|---|
| `graphql.field.path` | Path to the field being fetched | `/bookById/author` |

These keys let you observe a DataFetcher across three dimensions:

1. Which field is being resolved.
2. Where the field is located in the GraphQL response tree.
3. Whether the fetch succeeded or failed, and what type of error occurred.

Not every field selected by the client creates a dedicated observation. Spring GraphQL only creates DataFetcher observations for fetch operations considered non-trivial. Reading a property directly from a Java object using the default property fetcher is a trivial operation and normally does not create a dedicated observation.

Therefore, do not expect a `graphql.datafetcher` span for every scalar field like `Book.id` or `Book.title` if they are simply read from existing properties.

## 8. Using Field Path to Find Slow Resolvers

Suppose a query returns a list of books and author information:

~~~graphql
query {
  books(first: 20) {
    id
    title
    author {
      name
      organization {
        name
      }
    }
  }
}
~~~

A trace might show:

~~~text
graphql.request                 850 ms
  graphql.datafetcher           120 ms  /books
  graphql.datafetcher           640 ms  /books/0/author
  graphql.datafetcher            12 ms  /books/0/author/organization
  graphql.datafetcher           610 ms  /books/1/author
  graphql.datafetcher            10 ms  /books/1/author/organization
~~~

These numbers are illustrative. When analyzing a real trace:

1. Open a `graphql.request` observation or span with unusually high total duration.
2. Inspect the `graphql.datafetcher` observations inside the request.
3. Sort by duration to find fetchers consuming the most time.
4. Read `graphql.field.name` to identify the field type.
5. Read `graphql.field.path` to pinpoint the specific branch.
6. Check the error type if the outcome is `ERROR`.
7. Open downstream spans or correlated logs to find slow database queries, HTTP calls, or business logic.

If both `/books/0/author` and `/books/1/author` are slow, the resolver may be querying the database individually for each Book. This is a sign to check for N+1 and consider DataLoader or `@BatchMapping`.

If only one specific path is slow, inspect the data or service called from that branch. Do not conclude the root cause from field path alone; the path only reveals where execution happened, while child spans and logs provide evidence of timing and dependencies.

## 9. Distinguishing Field Path from Execution Path in GraphQL Java

GraphQL Java also exposes the execution path to a DataFetcher through `DataFetchingEnvironment`.

Example:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(
        Book book,
        DataFetchingEnvironment environment) {

    String executionPath =
            environment.getExecutionStepInfo()
                    .getPath()
                    .toString();

    log.debug("Resolving author at path={}", executionPath);

    return authorService.findByBookId(book.id());
}
~~~

Execution path can be used for logging inside a resolver when local debugging is needed. However, you do not need to manually create an observation just to store the path if GraphQL observation instrumentation is already enabled.

Distinguish the two uses:

- `environment.getExecutionStepInfo().getPath()`: GraphQL Java API allowing a resolver to read the current field's position at execution time.
- `graphql.field.path`: key placed by Spring GraphQL into the Micrometer DataFetcher observation for viewing in traces.

Both describe the field's position, but they live at different layers: one is an execution API, and the other is observability metadata.

Avoid logging the full path in every resolver if the system already collects full traces. Repetitive logging can generate high log volume and increase storage costs.

## 10. Combining graphql.field.path with the Request Observation

A GraphQL request can invoke many DataFetchers. Observing individual fields alone is sometimes not enough to understand the overall experience.

The `graphql.request` request observation provides metadata such as:

| Key | Cardinality | Meaning |
|---|---|---|
| `graphql.operation.type` | Low | `query`, `mutation`, `subscription`, or `operation` |
| `graphql.outcome` | Low | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High | Execution ID of the request |
| `graphql.operation.name` | High | Operation name provided by the client |

When inspecting traces, start from the request span, then expand DataFetcher spans to locate the problematic field path.

Example:

~~~text
graphql.request
  graphql.operation.type = query
  graphql.outcome = SUCCESS
  graphql.operation.name = BookDetails

  graphql.datafetcher
    graphql.field.name = bookById
    graphql.field.path = /bookById

  graphql.datafetcher
    graphql.field.name = author
    graphql.field.path = /bookById/author
~~~

Operation name and execution ID help locate the request. Field name and field path help locate the DataFetcher within that request.

Do not use client-sent operation names as metric labels if clients can send unbounded operation names. Under the default configuration, operation name is a high-cardinality key intended for traces.

## 11. Combining with DataLoader Observations to Find N+1

When a GraphQL query loads relational fields, DataFetcher observations show which fields are called. DataLoader observations show the batch loads.

Spring GraphQL creates the `graphql.dataloader` observation for:

- Controller methods annotated with `@BatchMapping`.
- Manually registered and invoked DataLoaders.

Some default metadata:

| Key | Cardinality | Description |
|---|---|---|
| `graphql.loader.name` | Low | DataLoader name |
| `graphql.outcome` | Low | `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Error class if the batch fails |
| `graphql.loader.size` | High | Size of the loaded element list |

When suspecting N+1:

1. Look for multiple DataFetcher observations with the same field name and different paths.
2. Check the duration of each field path.
3. Look for the corresponding `graphql.dataloader` observation.
4. Compare loader invocation counts and loader size.
5. Verify that the batch method actually consolidates multiple keys into a single query.

Example:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .map(authors -> mapAuthorsToBooks(books, authors));
    }
}
~~~

This example illustrates a batch mapping. In a real application, ensure results are mapped accurately to each source object and handle cases where no Author exists.

Field path helps locate the DataFetcher branch; DataLoader observations help verify the batching mechanism. The two observation types complement each other.

## 12. Reading Metrics and Traces in Monitoring Tools

### Metrics

Metrics are well-suited for high-level questions:

- How many GraphQL requests are processed?
- What is the average or percentile processing time?
- How is the error request rate changing?
- Which fields frequently fail?
- Is DataLoader being called?

With Micrometer, observations are turned into timers/counters according to low-cardinality key values. For example, you can inspect the metric:

~~~http
GET /actuator/metrics/graphql.datafetcher
~~~

Actual meter names and tag normalization can vary by registry. Inspect the list of meters and tags exported by the application rather than assuming every backend displays them identically.

### Distributed Traces

Traces are well-suited for detailed questions:

- Which specific request was slow?
- Which DataFetcher took most of the time?
- On which branch does the field sit?
- Which service or database did the resolver call?
- On which span did the error occur?

`graphql.field.path` is used here because tracing backends handle storing high-cardinality metadata better than metrics backends.

### Logs

Logs are well-suited for recording intentional diagnostic information:

- Execution ID or trace ID for correlation.
- Operation name if permitted.
- Field path when specific debugging is needed.
- Error type and safe handling details.

Avoid logging arguments, tokens, personal data, or full GraphQL variables without a clear business requirement and data protection policy.

## 13. Customizing Conventions When Needed

Spring GraphQL uses observation conventions to determine observation names and recorded key values. By default, `DefaultDataFetcherObservationConvention` provides `graphql.field.name`, `graphql.field.path`, `graphql.outcome`, and `graphql.error.type`.

If your application needs additional metadata, you can implement a custom `DataFetcherObservationConvention` and register it as a bean following the guide for your version of Spring GraphQL.

Examples of metadata to consider:

- Business domain group name with a finite set of values.
- DataFetcher category such as controller or repository adapter.
- Internal API version if it has a bounded set of values.

Do not turn path, entity ID, user ID, or argument values into low-cardinality tags just for easier dashboard filtering. If you need those values, keep them in high-cardinality metadata, controlled logs, or trace attributes.

When replacing the default convention, retain the necessary default keys or proactively confirm that dashboards and alerts have been updated. Changing a convention does not alter GraphQL execution; it only changes observation metadata.

## 14. Protecting Data and Avoiding Cardinality Explosion

Field path can reflect aliases or list element positions. Consequently, a client can generate many distinct paths using queries with many aliases or large lists.

Principles:

- Keep `graphql.field.path` in high-cardinality metadata.
- Do not convert field path into a metric tag.
- Do not construct dynamic metric names from paths.
- Do not add argument values or entity IDs to low-cardinality tags.
- Enforce query complexity and pagination limits to control how many fields are executed.
- Limit trace/log size and retention duration per operational policy.
- Check trace sampling so you do not store every expensive request in high-volume systems.
- Do not write sensitive data into span attributes or logs.

A high-cardinality key does not mean you can store arbitrary data without restraint. Tracing backends also have capacity limits, query costs, and retention policies.

## 15. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `graphql.datafetcher` is missing | Missing ObservationRegistry or instrumentation | Check Actuator and GraphQL observation auto-configuration |
| Only `graphql.request` appears | DataFetcher is a trivial property fetcher or fetcher is not instrumented | Verify resolvers are actually registered |
| `graphql.field.path` missing from metrics | It is a high-cardinality key, not a default metric tag | Check distributed traces |
| Metric series count rises rapidly | Path or ID was added to low-cardinality tags | Remove dynamic keys from metric tags |
| Cannot distinguish two fields with the same name | Looking only at `graphql.field.name` | Also inspect `graphql.field.path` |
| Trace lacks parent HTTP span | Transport tracing not configured or context propagation broken | Check HTTP observation and tracing setup |
| Request is slow but individual fields are fast | Cost is in parsing, validation, serialization, or transport | Inspect the request span and HTTP span |
| Many similar field paths are slow | Possible N+1 or slow shared downstream dependency | Cross-reference DataLoader observation and dependency spans |
| Error path is unclear in dashboard | Looking at aggregate metrics | Open a specific trace and inspect error events |

## 16. Implementation Checklist

Before using `graphql.field.path` for production monitoring:

- [ ] `ObservationRegistry` is present in the application.
- [ ] `GraphQlObservationInstrumentation` is registered exactly once in the GraphQL runtime.
- [ ] `graphql.request` is observable.
- [ ] `graphql.datafetcher` is observable for non-trivial resolvers.
- [ ] The difference between `graphql.field.name` and `graphql.field.path` is understood.
- [ ] Field paths are used in traces/logs in a controlled manner.
- [ ] Field paths are excluded from metric tags.
- [ ] Low-cardinality keys are used for dashboards and alerts.
- [ ] Tracing is available to drill down into specific requests.
- [ ] DataLoader observations are cross-referenced when checking for N+1.
- [ ] Sensitive data is not recorded in metadata.
- [ ] Cardinality and trace/log volume are monitored.
- [ ] Both successful and failing resolver cases are tested.

## Conclusion

`graphql.field.path` is a high-cardinality key in Spring for GraphQL's `graphql.datafetcher` observation. It indicates the position of the field being fetched in the GraphQL execution tree, helping distinguish resolutions of the same field name across different branches.

Use `graphql.field.name` and `graphql.outcome` for high-level metrics; use `graphql.field.path` in distributed traces to pinpoint slow or failing resolvers on the exact branch. Combining request observations, DataFetcher observations, and DataLoader observations enables analyzing GraphQL performance from the overall request down to individual data fetches.

Do not put field path into metric tags because the number of values can grow with aliases, query branches, and list indices. Keeping this key in controlled tracing/logs provides detailed diagnostics without causing a cardinality explosion in the metrics backend.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — Request Execution and Context](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
