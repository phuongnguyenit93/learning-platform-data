# graphql.error.type

Spring for GraphQL uses Micrometer Observation to record the duration and outcome of GraphQL requests, individual DataFetchers, and DataLoaders. One of the key attributes is `graphql.error.type`. This key helps observe what kind of error occurred during data fetching, enabling you to find failing fields and group root causes to address.

In the default `graphql.datafetcher` observation, `graphql.error.type` is a low-cardinality key whose value is the class name of the error thrown during data fetching. It also appears in the `graphql.dataloader` observation when a batch loading operation fails. This information serves metrics/tracing; it is not synonymous with the `org.springframework.graphql.execution.ErrorType` enum used to classify GraphQL errors returned to the client.

Distinguishing these two concepts is essential. For example, a resolver throws `BookNotFoundException`, and then an exception handler translates that error into `ErrorType.NOT_FOUND`. The observation may record the exception class in `graphql.error.type`, while the GraphQL response carries the `NOT_FOUND` classification. One value describes the error at the execution layer, while the other describes the error category per the API contract.

## 1. What Is `graphql.error.type`?

`graphql.error.type` is a metadata key in Micrometer observations for data fetching activity. Under the default convention, it represents the class name of the exception/error that occurred while a DataFetcher or DataLoader performed its work.

Examples of values you might encounter depending on your application's exceptions:

| Error during data fetching | Illustrative observed value |
| --- | --- |
| `BookNotFoundException` | `BookNotFoundException` |
| `AccessDeniedException` | `AccessDeniedException` |
| `DataIntegrityViolationException` | `DataIntegrityViolationException` |
| `TimeoutException` | `TimeoutException` |
| No error | Observation has a successful outcome; convention handles the error value per version |

Using the class name helps group errors by exception type. It is better than putting the entire message into a metric tag, because messages often contain IDs, usernames, query values, or data that varies per request.

This key is defined as low-cardinality. That means its values should belong to a finite and stable set so the metrics system does not create too many time series. Using meaningful exception classes in a bounded number keeps cardinality controllable.

## 2. Distinguishing Observation Error Type from GraphQL ErrorType

Spring GraphQL has two concepts with similar names that serve two different purposes:

| Concept | Where it lives | Represented value | Purpose |
| --- | --- | --- | --- |
| `graphql.error.type` | Micrometer observation `graphql.datafetcher` or `graphql.dataloader` | Class name of the data fetching error | Metrics and tracing to diagnose execution failures |
| `org.springframework.graphql.execution.ErrorType` | GraphQL `GraphQLError` | `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `INTERNAL_ERROR` | Error classification in the GraphQL response so clients understand semantics |

Spring GraphQL's `ErrorType` implements GraphQL Java's `ErrorClassification`. It allows applications to classify errors according to API semantics:

- `BAD_REQUEST`: the DataFetcher could not or would not fetch data due to an error considered to be on the client side.
- `UNAUTHORIZED`: valid authentication credentials are missing.
- `FORBIDDEN`: the caller is authenticated but not allowed to read the data.
- `NOT_FOUND`: the data was not found or the application does not want to disclose whether it exists.
- `INTERNAL_ERROR`: an unexpected error prevented the DataFetcher from fetching data.

Example of a mapped exception:

~~~java
@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

In this example:

- The underlying exception is `BookNotFoundException`.
- The classification sent in the GraphQL error is `NOT_FOUND`.
- The data fetching observation can record the exception class in `graphql.error.type`.

Do not mentally conflate the exception class with the API enum when reading dashboards. The two values answer different questions: which exception occurred in code, and which error category was communicated to the client.

## 3. Which Observations Contain This Key?

Spring for GraphQL has three main observations:

| Observation name | Scope | Relevant keys |
| --- | --- | --- |
| `graphql.request` | Entire GraphQL request | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | A non-trivial DataFetcher | `graphql.error.type`, `graphql.field.name`, `graphql.outcome` |
| `graphql.dataloader` | A DataLoader or `@BatchMapping` call | `graphql.error.type`, `graphql.loader.name`, `graphql.outcome` |

DataFetcher observations are only created for fetch operations considered non-trivial. Simply reading a property from a Java object is typically trivial and does not create a dedicated observation. Therefore, not every field in a selection set will have a `graphql.datafetcher` sample.

DataLoader observations track `@BatchMapping` invocations and manually registered DataLoaders. If a batch load fails, `graphql.error.type` helps group errors by exception class; `graphql.loader.name` identifies which loader was affected.

## 4. Default Keys of the DataFetcher Observation

The default convention generates the following low-cardinality keys:

| Key | Meaning |
| --- | --- |
| `graphql.error.type` | Class name of the data fetching error |
| `graphql.field.name` | Name of the field being fetched |
| `graphql.outcome` | `SUCCESS` or `ERROR` |

Default high-cardinality key:

| Key | Meaning |
| --- | --- |
| `graphql.field.path` | Path of the field in GraphQL execution, e.g. `/bookById` |

High-cardinality keys are well-suited for adding context to traces, but should not be used as metric labels with large value sets. Field paths can vary by query structure and aliases, so check Micrometer's export rules when using them in tracing.

For example, an error on the `Book.author` field might produce an observation with attributes similar to:

~~~text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: ERROR
graphql.error.type: AuthorServiceUnavailableException
graphql.field.path: /books/0/author
~~~

This is an illustrative example of values, not fixed output across every version or exporter. The actual field path depends on the response path, aliases, and operation structure.

## 5. Keys of the GraphQL Request Observation

`graphql.request` measures the total execution time of a GraphQL request. Default low-cardinality keys include:

| Key | Meaning |
| --- | --- |
| `graphql.operation.type` | `query`, `mutation`, `subscription`, or `operation` when document cannot be parsed |
| `graphql.outcome` | Overall outcome of the GraphQL request |

`graphql.outcome` has these primary values:

- `SUCCESS`: valid GraphQL response with no errors.
- `REQUEST_ERROR`: request could not be parsed, or response has errors with none carrying `ErrorType.INTERNAL_ERROR`.
- `INTERNAL_ERROR`: a valid GraphQL response could not be produced, or response contains at least one error carrying `ErrorType.INTERNAL_ERROR`.

This means a GraphQL response with HTTP 200 can still have `graphql.outcome=REQUEST_ERROR`. For example, a field returning `NOT_FOUND` in a response with partial data can cause the request outcome to be REQUEST_ERROR under the convention. HTTP status and GraphQL outcome measure two different layers.

The request observation also has high-cardinality keys such as execution ID and operation name. They are useful for locating a specific trace or request, but unsuitable as high-cardinality metric tags.

## 6. How Do Exceptions Enter Observations?

When a DataFetcher executes, GraphQL instrumentation wraps the fetch operation and creates an observation. If the fetch succeeds, the outcome is success. If the DataFetcher throws an exception, the observation can record the error and the exception class into `graphql.error.type`.

Then, Spring for GraphQL's exception handling mechanism decides how the GraphQL error is returned to the client. Spring registers a default DataFetcher exception handler and supports multiple `DataFetcherExceptionResolver` beans. With annotated controllers, you can use `@GraphQlExceptionHandler` inside a controller or `@ControllerAdvice`.

Overall flow:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[GraphQL request observation]
    B --> C[DataFetcher observation]
    C --> D{DataFetcher succeeded?}
    D -->|Yes| E[graphql.outcome = SUCCESS]
    D -->|No| F[Capture exception class]
    F --> G[graphql.error.type]
    F --> H[DataFetcherExceptionResolver]
    H --> I[GraphQL ErrorClassification]
    I --> J[GraphQL response errors]
    E --> K[GraphQL response]
    J --> K
    K --> L[graphql.request outcome]
~~~

`graphql.error.type` describes the exception in the fetch operation. `ErrorType` describes the GraphQL error classification after handling. When exceptions are mapped, both pieces of information are useful for correlating logs, traces, and responses.

## 7. Mapping Exceptions to GraphQL ErrorType

With annotated controllers, `@GraphQlExceptionHandler` lets you build a GraphQL error using a `GraphqlErrorBuilder` pre-configured for the current `DataFetchingEnvironment`:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument Long id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handle(
            GraphqlErrorBuilder<?> errorBuilder,
            BookNotFoundException exception) {

        return errorBuilder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

To apply handlers across multiple controllers, place the methods in a `@ControllerAdvice`. For DataFetchers not created from annotated controllers, use `DataFetcherExceptionResolver` or `DataFetcherExceptionResolverAdapter`.

Return safe and helpful messages to clients. Stack traces, SQL statements, internal hostnames, access tokens, and infrastructure details belong in controlled internal logs, not in GraphQL responses.

If an exception is not handled by any resolver, Spring GraphQL defaults to classifying it as `INTERNAL_ERROR` and returns a generic message with the execution ID. Unresolved exceptions are logged at ERROR; resolved exceptions are logged at DEBUG by default. You can use the execution ID to correlate client-side errors with server logs.

## 8. Request-Level Errors Have No DataFetcher Error Type

Not all GraphQL errors originate from DataFetchers. Some errors occur before execution:

- Malformed GraphQL document syntax.
- Non-existent field or argument in the schema.
- Variable with an incorrect type.
- Invalid operation or unable to select an operation for execution.

These are request-level errors. They have no field path and do not go through DataFetcher exception resolvers because no DataFetcher has been called yet. Therefore, do not expect a `graphql.datafetcher` observation or a corresponding `graphql.error.type` for parse/validation errors.

At the request level, inspect `graphql.outcome` and trace error events. If you need to customize request-level errors, look into `WebGraphQlInterceptor` or appropriate transport-level handling; `DataFetcherExceptionResolver` does not handle errors that occur before execution.

### Note on Subscription Publishers

A subscription DataFetcher initially returns a Publisher. If creating the Publisher succeeds but the Publisher emits an error later, that failure happens after the initial DataFetcher call. `DataFetcherExceptionResolver` does not handle errors emitted from a subscription Publisher; Spring for GraphQL provides the `SubscriptionExceptionResolver` contract to convert stream errors into GraphQL errors for the transport.

Therefore, when investigating subscriptions, distinguish errors when creating the Publisher from errors emitted while the stream is running. Do not assume all subscription errors appear under `graphql.error.type` of the initial DataFetcher observation. Inspect subscription error handling, WebSocket traces/transports, and logs with appropriate execution or connection context.

## 9. DataLoader and graphql.error.type

The `graphql.dataloader` observation tracks DataLoader calls, including `@BatchMapping` and manually registered DataLoaders. Default low-cardinality keys include:

| Key | Meaning |
| --- | --- |
| `graphql.error.type` | Class name of the error during data loading |
| `graphql.loader.name` | DataLoader name |
| `graphql.outcome` | `SUCCESS` or `ERROR` |

The default high-cardinality key is `graphql.loader.size`, indicating the number of elements loaded in the batch.

For example, if the `authorById` loader frequently fails with `AuthorRepositoryTimeoutException`, dashboards can filter by loader name and error type to identify batch loading as the source of errors. If multiple different DataFetchers depend on that loader, the failure shows up at the loader layer rather than only across scattered fields.

Do not attach individual author, book, or user IDs to metric tags. Those values can be huge in number and change constantly. Use loader name and exception class for grouping; use controlled traces/logs to inspect a specific request.

## 10. Enabling GraphQL Observations

Observations are only recorded when the application has an `ObservationRegistry` and `GraphQlObservationInstrumentation` is attached to GraphQL execution.

With Spring Boot, auto-configuration provides the instrumentation when the required conditions are met, such as GraphQL and Micrometer Observation on the classpath alongside an `ObservationRegistry`. Conditions and auto-configuration packages vary by Boot version line; inspect the actual beans if the application customizes `GraphQlSource` or does not use the Boot starter.

In configurations requiring explicit registration, the instrumentation is created with `ObservationRegistry`:

~~~java
@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    GraphQlObservationInstrumentation graphQlObservationInstrumentation(
            ObservationRegistry observationRegistry) {
        return new GraphQlObservationInstrumentation(observationRegistry);
    }
}
~~~

Do not register a duplicate instrumentation if Boot already auto-configures it. First verify the application has only one appropriate configuration source and that observations are actually emitted.

To export metrics, the application needs a suitable MeterRegistry, such as the Prometheus registry, and can expose the Actuator metrics endpoint per operational configuration. To export traces, configure Micrometer Tracing with the corresponding exporter. The Observation API is the common instrumentation layer; the metrics/tracing backend determines where data is stored and displayed.

## 11. Reading graphql.error.type in Dashboards

When investigating errors, combine at least three attributes:

1. `graphql.error.type` to see which exception class occurred.
2. `graphql.field.name` to see which field frequently encounters errors.
3. `graphql.outcome` to separate successful fetches from failed ones.

For DataLoaders, combine `graphql.loader.name` and `graphql.error.type`. For the overall request, inspect `graphql.operation.type` and `graphql.outcome`.

Examples of questions to ask when reading dashboards:

| Observation | Investigation direction |
| --- | --- |
| One error class spikes across multiple fields | Check shared dependencies or shared exception mappings |
| Only one field has outcome ERROR | Check that specific field's resolver/service |
| Multiple fields fail with the same loader name | Check the batch loader and underlying repository |
| Request outcome is REQUEST_ERROR with no INTERNAL_ERROR | Inspect business errors, validation, or authorization in GraphQL responses |
| Request outcome is INTERNAL_ERROR | Look for unhandled exceptions or internal errors making the response invalid |
| HTTP 200 but GraphQL request outcome is REQUEST_ERROR | Read GraphQL errors instead of looking only at HTTP status |

Metrics show trends and error groupings. Traces show how a specific request flowed through transport, GraphQL request, DataFetcher, DataLoader, and dependencies. Logs with execution ID/correlation ID help tie that data together.

## 12. Cardinality and Sensitive Data

`graphql.error.type` is designed as a low-cardinality key. However, an application can still cause cardinality to grow if it dynamically generates too many exception classes or uses a distinct class per data value.

Do not use the following values as metric tags:

- Exception messages containing IDs, emails, usernames, or query inputs.
- Stack traces or SQL statement strings that vary per request.
- Resource IDs, tenant IDs, or user IDs.
- GraphQL variables or entire documents.
- Raw field paths that can grow with aliases and query structures.

Keep exception classes stable and meaningful. If an application has many internal exception classes, you can normalize them into a finite set of groups in a custom convention, such as `DEPENDENCY_FAILURE`, `AUTHORIZATION_FAILURE`, or `VALIDATION_FAILURE`. Normalization must preserve sufficient diagnostic detail in logs/traces and avoid losing the ability to distinguish critical errors.

Do not expose internal exception classes or implementation details in client responses merely because they are recorded in observations. Metric tags and the public GraphQL error contract are two separate channels.

## 13. Customizing DataFetcherObservationConvention

Spring for GraphQL lets you customize key values using `DataFetcherObservationConvention`. With Spring Boot, providing the convention as a bean is a convenient way to integrate. You can extend `DefaultDataFetcherObservationConvention` and override the error type logic.

Example normalizing several exception classes into stable groups:

~~~java
@Configuration
public class GraphQlObservationConventionConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {

            @Override
            protected KeyValue errorType(DataFetcherObservationContext context) {
                Throwable error = context.getError();
                String value = classify(error);
                return KeyValue.of("graphql.error.type", value);
            }

            private String classify(Throwable error) {
                if (error == null) {
                    return "none";
                }
                if (error instanceof AccessDeniedException) {
                    return "AUTHORIZATION_FAILURE";
                }
                if (error instanceof TimeoutException) {
                    return "DEPENDENCY_TIMEOUT";
                }
                if (error instanceof BookNotFoundException) {
                    return "NOT_FOUND";
                }
                return "UNEXPECTED_FAILURE";
            }
        };
    }
}
~~~

The example above illustrates a custom policy: any exception not in the allowlist is grouped under `UNEXPECTED_FAILURE`. Verify class imports against your application's Micrometer/Spring GraphQL version. If you want to keep default class names, extend the default convention without overriding this method.

When overriding a convention, preserve the other default keys by customizing only the specific key needed. If implementing `DataFetcherObservationConvention` completely from scratch, maintain the keys required by existing dashboards and understand how changes impact metrics/traces.

## 14. Testing Error Type Observations

Do not check only the GraphQL response to conclude that `graphql.error.type` is recorded properly. Response assertions test error classification; observation tests verify emitted metadata.

A test scenario should:

1. Configure a test `ObservationRegistry`.
2. Execute a GraphQL operation whose DataFetcher throws a specific exception.
3. Verify the response contains the expected GraphQL error classification.
4. Verify the DataFetcher observation has `graphql.error.type` matching the convention.
5. Verify `graphql.field.name` and `graphql.outcome` match expectations.
6. Execute a succeeding request to ensure error state does not leak across requests.

You can use Micrometer Observation test support or an ObservationHandler that captures started/stopped contexts. When testing metrics, use a test registry such as SimpleMeterRegistry and assert timers/tags after the operation completes. The exact way to retrieve observations depends on the test support and Micrometer version in use.

Cases to include:

- Succeeding DataFetcher.
- DataFetcher throwing an exception handled by `@GraphQlExceptionHandler`.
- Unhandled exception becoming `INTERNAL_ERROR`.
- Request parse/validation failure before any DataFetcher runs.
- Failing DataLoader batch call.
- Multiple fields sharing a dependency and producing the same error class.
- Custom convention normalizing exceptions into groups.

When testing errors handled by a handler, do not assert only the HTTP status. Check the GraphQL response error, observation outcome, and tags at the appropriate layer.

## 15. Common Mistakes

| Misconception or misconfiguration | Consequence | Resolution |
| --- | --- | --- |
| Confusing `graphql.error.type` with `ErrorType.NOT_FOUND` | Misreading tag meaning | Distinguish exception class in observations from GraphQL ErrorClassification |
| Checking only HTTP status | Missing GraphQL errors in HTTP 200 responses | Inspect `graphql.outcome` and GraphQL response errors |
| Missing ObservationRegistry | No GraphQL observations recorded | Configure Micrometer Observation and verify the registry |
| Expecting every field to have a datafetcher observation | Missing counts compared to query fields | Trivial property fetchers may not be instrumented separately |
| Looking for request parse errors via graphql.error.type | Corresponding tag not found | Request errors happen before DataFetchers; check request observations |
| Putting exception messages into metric tags | Cardinality grows and data may leak | Use stable classes/groups; keep messages in controlled logs |
| Using field path as a metric label | Creates excessive time series | Keep path in high-cardinality trace context |
| Exception handler hides all internal details | Client does not see technical causes | Use execution ID to correlate responses with internal logs/traces |
| Customizing convention without keeping default keys | Existing dashboards lose tags | Extend default convention and override only necessary keys |
| Registering duplicate instrumentation | Can produce duplicate observations/metrics | Check auto-configuration and GraphQlSource customization |

## 16. Principles for Using graphql.error.type

Treat `graphql.error.type` as a technical label for errors occurring during data fetching. Use it to group exception classes in DataFetchers and DataLoaders; combine it with field name, loader name, and outcome to pinpoint where errors happen. Use request observations to inspect the overall result of a GraphQL operation, since parse/validation errors can occur before any DataFetcher is invoked.

Keep low-cardinality tags stable and never put messages, IDs, variables, or stack traces into metric labels. If exception classes are too fragmented, normalize them with a custom observation convention while preserving full details in controlled logs/traces.

When building GraphQL error responses, use GraphQL ErrorClassification or Spring GraphQL ErrorType to represent semantics for clients. When monitoring the system, use `graphql.error.type` to understand exception classes during fetching. Combining both layers lets dashboards answer both technical and business questions without blurring the API contract and telemetry.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring GraphQL ErrorType API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/execution/ErrorType.html)
- [DefaultDataFetcherObservationConvention API](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DefaultDataFetcherObservationConvention.html)
