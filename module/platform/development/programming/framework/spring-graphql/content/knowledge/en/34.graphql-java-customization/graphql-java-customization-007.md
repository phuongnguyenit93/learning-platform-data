# DataFetcherExceptionHandler

In GraphQL Java, `DataFetcherExceptionHandler` is the SPI responsible for handling exceptions thrown during `DataFetcher` execution. The handler receives details about the exception, the field being resolved, and the field's position in the operation; it then returns a `DataFetcherExceptionHandlerResult` containing one or more `GraphQLError`s. The GraphQL engine uses those errors to build the `ExecutionResult` and enforce the schema's null propagation rules.

In Spring for GraphQL, `DataFetcherExceptionHandler` is a GraphQL Java-level extension point. Spring applications should generally use `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` to map exceptions via built-in mechanisms. Only replace `DataFetcherExceptionHandler` directly when lower-level customization is required and you understand how that configuration interacts with Spring's exception resolver chain.

## 1. Where Does DataFetcherExceptionHandler Fit in Execution?

When GraphQL executes a field, it invokes the corresponding `DataFetcher`. The DataFetcher can return a value directly, return a `CompletionStage`, or throw an exception. For asynchronous results, the `CompletionStage` may also complete exceptionally.

GraphQL Java forwards exceptions thrown during fetching to `DataFetcherExceptionHandler`. The handler converts the exception into a `GraphQLError`. The GraphQL engine attaches the error to the response and applies schema nullability to determine which field or parent becomes null.

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[Resolve field]
    B --> C[Invoke DataFetcher]
    C --> D{Fetch succeeded?}
    D -->|Yes| E[Field value]
    D -->|No| F[Exception]
    F --> G[DataFetcherExceptionHandler]
    G --> H[DataFetcherExceptionHandlerResult]
    H --> I[GraphQLError in ExecutionResult]
    E --> J[GraphQL response]
    I --> J
    J --> K[Null propagation per schema]
~~~

The handler does not replace the DataFetcher and does not synthesize business values for the failed field. It only describes the error to include in the GraphQL result. If you want to return a fallback value, the resolver or service must actively return the appropriate value; if you want to return both data and errors simultaneously, consider `DataFetcherResult`.

## 2. GraphQL Java API

`DataFetcherExceptionHandler` has one primary method:

~~~java
CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
    DataFetcherExceptionHandlerParameters handlerParameters);
~~~

Key types:

| Type | Role |
| --- | --- |
| `DataFetcherExceptionHandler` | Contract for handling DataFetcher exceptions |
| `DataFetcherExceptionHandlerParameters` | Context of the exception and the field being fetched |
| `DataFetcherExceptionHandlerResult` | Result returned by the handler to the GraphQL engine |
| `GraphQLError` | Error added to the GraphQL response |
| `DataFetchingEnvironment` | Field execution context, arguments, source object, and context |
| `ResultPath` | Field path in the response, including list indices and aliases if present |
| `SourceLocation` | Field location in the GraphQL document |

The handler returns a `CompletableFuture` because GraphQL Java supports asynchronous execution. For simple mappings, use `CompletableFuture.completedFuture(...)`. Do not perform blocking I/O inside the handler and do not call `join`/`get` on another future if doing so could block the GraphQL processing thread.

## 3. What Does DataFetcherExceptionHandlerParameters Provide?

Parameters provide the information needed to construct an accurate error:

- `getException()`: the original exception passed by GraphQL Java to the handler.
- `getDataFetchingEnvironment()`: the field environment, including source object, arguments, `GraphQLContext`, and field definition.
- `getPath()`: the response path of the failing field.
- `getSourceLocation()`: the field's location in the document.

For example, a path might look like:

~~~text
books[2].author.name
~~~

If the client uses an alias:

~~~graphql
query {
    featured: bookById(id: "book-01") {
        author {
            name
        }
    }
}
~~~

the response path uses the response key `featured`, not necessarily the field name `bookById`. Preserve the path supplied by GraphQL instead of assembling strings manually from Java method names.

## 4. Writing a Custom DataFetcherExceptionHandler

Minimal handler example:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherExceptionHandler;
import graphql.execution.DataFetcherExceptionHandlerParameters;
import graphql.execution.DataFetcherExceptionHandlerResult;
import org.springframework.stereotype.Component;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;
import java.util.concurrent.CompletableFuture;

@Component
public class SafeDataFetcherExceptionHandler
        implements DataFetcherExceptionHandler {

    @Override
    public CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
            DataFetcherExceptionHandlerParameters parameters) {

        GraphQLError error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Unable to complete this field")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();

        DataFetcherExceptionHandlerResult result =
            DataFetcherExceptionHandlerResult.newResult()
                .error(error)
                .build();

        return CompletableFuture.completedFuture(result);
    }
}
~~~

`GraphqlErrorBuilder.newError(DataFetchingEnvironment)` attaches the field context to the error, including `path` and `sourceLocation` from the environment. `ErrorType.INTERNAL_ERROR` here is Spring for GraphQL's classification. If using GraphQL Java without Spring, select an `ErrorClassification` matching your API.

The handler above returns a safe message and a stable error code. It deliberately avoids exposing `exception.getMessage()` in the response because the message could contain SQL, hostnames, internal IDs, or sensitive data.

GraphQL Java provides `SimpleDataFetcherExceptionHandler` as its default handler. The default handler creates an `ExceptionWhileDataFetching` error and preserves path/source location metadata for the execution result. When replacing it with a custom handler, the application assumes responsibility for classification, message, extensions, and logging; inspect the actual response produced by your GraphQL Java version to avoid inadvertently exposing exception details.

## 5. Mapping Exceptions by Type

In practice, not every exception should return the same message or classification. You can branch by exception type:

~~~java
@Override
public CompletableFuture<DataFetcherExceptionHandlerResult> handleException(
        DataFetcherExceptionHandlerParameters parameters) {

    Throwable exception = parameters.getException();
    GraphQLError error;

    if (exception instanceof BookNotFoundException) {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
    else if (exception instanceof AccessDeniedException) {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.FORBIDDEN)
            .message("You are not allowed to access this resource")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
    }
    else {
        error = GraphqlErrorBuilder
            .newError(parameters.getDataFetchingEnvironment())
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("Unable to complete this field")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
    }

    return CompletableFuture.completedFuture(
        DataFetcherExceptionHandlerResult.newResult()
            .error(error)
            .build());
}
~~~

Example classification mapping:

| Exception | GraphQL Classification | Public Code |
| --- | --- | --- |
| `BookNotFoundException` | `NOT_FOUND` | `BOOK_NOT_FOUND` |
| `AccessDeniedException` | `FORBIDDEN` | `FORBIDDEN` |
| Validation/domain input exception | `BAD_REQUEST` if fitting the contract | `INVALID_INPUT` |
| Unrecoverable dependency timeout | `INTERNAL_ERROR` or dependency-specific code | `DEPENDENCY_UNAVAILABLE` |
| Unexpected exception | `INTERNAL_ERROR` | `INTERNAL_ERROR` |

Do not map every exception to `BAD_REQUEST`. An unavailable database or a bug in a resolver is not a client error. Classification should accurately reflect API semantics.

## 6. Preserving Path and Source Location

The error `path` helps clients locate which field failed in a nested response. The source location helps developer tools point to the exact position in the document.

Build errors from `DataFetchingEnvironment`:

~~~java
GraphQLError error = GraphqlErrorBuilder
    .newError(parameters.getDataFetchingEnvironment())
    .message("Author information is temporarily unavailable")
    .errorType(ErrorType.INTERNAL_ERROR)
    .extensions(Map.of("code", "AUTHOR_UNAVAILABLE"))
    .build();
~~~

Avoid constructing errors with only a message when the environment is available, as you can lose essential path/location data. With aliases and list indices, the path supplied by GraphQL Java is the authoritative source.

Path is not authorization metadata. Never rely on the path to decide which data a user is allowed to read; authorization must rely on the principal and business policies.

## 7. Handling Exception Wrappers

Asynchronous DataFetchers can complete exceptionally with exceptions wrapped inside `CompletionException` or `ExecutionException`. When classifying the underlying exception, you can unwrap common wrappers:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

private Throwable unwrap(Throwable error) {
    Throwable current = error;

    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }

    return current;
}
~~~

Then classify:

~~~java
Throwable exception = unwrap(parameters.getException());
~~~

Unwrap only well-known wrappers. Do not traverse arbitrarily down every `cause`, as the deepest root cause might not represent the error meant to be exposed. Retain the original exception for logging when full stack traces are needed.

## 8. Registering a Handler at the GraphQL Java Level

GraphQL Java lets you configure the default `DataFetcherExceptionHandler` on `GraphQL.Builder`. In Spring Boot, you can use `GraphQlSourceBuilderCustomizer` to configure `GraphQL.Builder`:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlJavaConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer customExceptionHandler(
            SafeDataFetcherExceptionHandler handler) {

        return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.defaultDataFetcherExceptionHandler(handler));
    }
}
~~~

This snippet illustrates the low-level GraphQL Java extension point. Builder APIs can differ by Spring Boot, Spring for GraphQL, and GraphQL Java version; verify your actual dependency versions before applying.

When replacing the default handler, confirm the new configuration does not accidentally bypass Spring for GraphQL's exception handling chain. In a Spring application, the `DataFetcherExceptionResolver` chain integrates `@GraphQlExceptionHandler` and resolver beans. Replacing the global handler can alter or bypass that default behavior.

Do not register multiple independent handlers assuming they will run sequentially. GraphQL Java uses a single default handler per execution; if multi-step resolution is needed, use Spring's resolver chain or build an explicitly ordered chain yourself.

## 9. Spring DataFetcherExceptionResolver as the Integrated Choice

Spring for GraphQL provides `DataFetcherExceptionResolver` for reactive-friendly exception handling integrated with GraphQL execution. Spring composes resolvers into a chain. Each resolver can either handle the exception or defer to the next resolver.

Example extending `DataFetcherExceptionResolverAdapter`:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
        }

        return null;
    }
}
~~~

Returning `null` signals that this resolver did not handle the exception so the next resolver in the chain can try. This is the contract of Spring's `DataFetcherExceptionResolverAdapter`; do not apply null returns to GraphQL Java's `DataFetcherExceptionHandler`.

A resolver can return one `GraphQLError` or multiple `GraphQLError`s as needed. Only emit multiple errors when a single exception genuinely corresponds to multiple meaningful field errors; avoid duplicating one error into multiple identical messages.

## 10. @GraphQlExceptionHandler

For annotated controllers, `@GraphQlExceptionHandler` is a concise, business-oriented way to map exceptions:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> builder) {

        return builder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
~~~

Handlers can be placed inside the controller containing the DataFetcher or inside a `@ControllerAdvice` for broader scope. Use global resolvers for shared errors; use controller-local handlers when semantics depend on a specific group of operations.

Do not declare the same exception in multiple overlapping handlers without explicit precedence rules. Test that exceptions are handled by the intended handler.

## 11. When to Use DataFetcherExceptionHandler Directly?

| Requirement | Approach to Consider |
| --- | --- |
| Mapping business exceptions in a Spring controller | `@GraphQlExceptionHandler` |
| Shared resolver across multiple controllers | `DataFetcherExceptionResolver` or `DataFetcherExceptionResolverAdapter` |
| Integrating error handling with Spring application context | Spring resolver chain |
| Customizing GraphQL Java behavior at the execution engine level | `DataFetcherExceptionHandler` |
| Using GraphQL Java standalone without Spring | `DataFetcherExceptionHandler` |
| Returning fallback data instead of only an error | Resolver/service or `DataFetcherResult` |
| Errors emitted after a subscription publisher is returned | `SubscriptionExceptionResolver` in Spring for GraphQL |

In a Spring application, prefer Spring's abstractions whenever they meet your requirements. Use the raw SPI directly only when you need precise control over GraphQL Java's handler or when the application does not use Spring GraphQL exception resolvers.

## 12. Handling Scope: Which Errors Does the Handler Receive and Not Receive?

`DataFetcherExceptionHandler` handles exceptions raised while GraphQL invokes a DataFetcher, including synchronous throws and asynchronous failures of the fetch operation.

It is not a catch-all handler for every application error:

| Error Type | Appropriate Handler |
| --- | --- |
| Exception inside a DataFetcher | `DataFetcherExceptionHandler` or Spring `DataFetcherExceptionResolver` |
| DataFetcher `CompletionStage` completes exceptionally | `DataFetcherExceptionHandler` or Spring resolver chain |
| Malformed GraphQL document syntax | GraphQL parser/request execution |
| Invalid field or argument per schema | GraphQL validation |
| Variable coercion failure | GraphQL input coercion |
| HTTP handshake, auth filter, or network failure | Web/security/transport layer |
| Exception emitted after a subscription publisher is returned | `SubscriptionExceptionResolver` |
| Exception in code before GraphQL execution starts | Application/transport layer |

For subscriptions, distinguish errors thrown when creating the `Publisher` from errors emitted later by the stream. Failures when creating the `Publisher` happen inside the initial DataFetcher. `onError` signals emitted after the `Publisher` is returned belong to the subscription lifecycle and require Spring's `SubscriptionExceptionResolver`.

## 13. GraphQL Null Propagation

The handler returns a `GraphQLError`; the GraphQL engine still enforces schema nullability. Example:

~~~graphql
type Query {
    book: Book
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
~~~

If the `author` resolver fails, the `author` field is non-null. GraphQL must propagate null up to the parent `Book`; since `book` is nullable, the response can have `book: null` along with an error path pointing to the `author` field.

If `book` were also declared non-null, null would propagate further up to root `data`. Therefore, non-null schema design must account for whether dependencies or child fields can fail.

`DataFetcherExceptionHandler` cannot override null propagation merely by returning a `GraphQLError`. If a fallback value is required, handle it inside the resolver or return a `DataFetcherResult` with data and errors per the contract.

## 14. DataFetcherResult and Partial Data

`DataFetcherExceptionHandler` fits cases where a DataFetcher throws an exception and has no valid value to return. If the application can return partial data accompanied by a warning, `DataFetcherResult` may be more appropriate:

~~~java
@QueryMapping
public DataFetcherResult<BookSummary> bookSummary(
        @Argument String id,
        DataFetchingEnvironment environment) {
    BookSummary summary = bookService.findSummary(id);

    GraphQLError warning = GraphqlErrorBuilder.newError(environment)
        .message("Some optional metadata is unavailable")
        .extensions(Map.of("code", "OPTIONAL_METADATA_UNAVAILABLE"))
        .build();

    return DataFetcherResult.<BookSummary>newResult()
        .data(summary)
        .error(warning)
        .build();
}
~~~

This example illustrates returning valid data alongside an auxiliary warning/error. Do not use `DataFetcherResult` to mask severe failures or return incomplete objects as if every field had succeeded.

## 15. Logging and Error Response Security

The handler runs at the boundary between internal exceptions and public GraphQL responses. Separate client-facing details from log-only details:

| Information | GraphQL Response | Internal Log |
| --- | --- | --- |
| Stable error code | Yes | Yes |
| Safe, clear message | Yes | Optional |
| Field path | Yes | Yes |
| Execution/correlation ID | Optional | Yes |
| Stack trace | No | Yes, when needed |
| SQL, hostname, connection string | No | Controlled and masked |
| Token, password, personal data | No | Never log raw |

Never return `exception.getMessage()` directly to clients. Messages can contain SQL queries, table names, host addresses, file paths, user IDs, or input values. Return a generic message with a stable code; log full exception details on the server under proper access control.

Avoid logging the same stack trace multiple times across resolvers, handlers, and global filters. Assign a single owner for exception logging to prevent log noise. Use the execution ID or trace ID to correlate responses with logs/traces.

## 16. Extensions and Error Codes

GraphQL errors can carry extensions so clients can classify failures:

~~~json
{
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ],
  "data": {
    "bookById": null
  }
}
~~~

This is an illustrative response; the exact `classification` field depends on `ErrorClassification` and library versions. Clients should never depend on stack traces or internal exception class names. Codes such as `BOOK_NOT_FOUND` form an application-controlled contract and should be versioned and documented.

Do not place per-request varying data into metric labels. Error codes should form a bounded set; detailed IDs and context belong in controlled logs/traces.

## 17. Testing DataFetcherExceptionHandler

Tests should verify that the handler builds the expected GraphQL error and the GraphQL engine preserves the proper path. In Spring for GraphQL, `GraphQlTester` can execute real operations:

~~~java
@Test
void mapsBookNotFoundToGraphQlError() {
    var response = graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
            .isEqualTo("Book not found");
        assertThat(errors.get(0).getPath())
            .containsExactly("bookById");
        assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
    });
}
~~~

When using Spring's `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`, this test verifies the actual Spring integration. When replacing GraphQL Java's `DataFetcherExceptionHandler` directly, test that `GraphQlSource`/`GraphQL.Builder` registers the expected handler.

## 18. Scenarios Worth Testing

| Scenario | What to Verify |
| --- | --- |
| DataFetcher succeeds | No unexpected errors |
| Synchronous exception | Handler is called and error has the right path |
| `CompletionStage` completes exceptionally | Exception wrapper is handled per policy |
| `BookNotFoundException` | Classification `NOT_FOUND` and code `BOOK_NOT_FOUND` |
| `AccessDeniedException` | No data leakage and appropriate classification |
| Unknown exception | `INTERNAL_ERROR` and safe message |
| Alias in query | Path uses the alias response key |
| Field inside a list | Path preserves the exact index |
| Non-null field fails | Null propagation obeys schema |
| Request parse/validation error | Not confused with a DataFetcher exception |
| Subscription publisher emits `onError` | Handled by `SubscriptionExceptionResolver` |
| `DataFetcherResult` with partial data | Data and errors returned together per contract |

Test both the response and side effects. For instance, when authorization fails, verify the service does not return sensitive data; when validation fails, verify mutations do not persist changes.

## 19. Common Pitfalls

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Using `DataFetcherExceptionHandler` for all HTTP errors | Misses parse errors, auth filters, or transport failures | Handle at the appropriate request/transport layer |
| Confusing GraphQL Java's handler with Spring's `DataFetcherExceptionResolver` | Misconfigured abstraction or bypassed resolver chain | Distinguish low-level SPI from Spring integration |
| Returning exception messages to clients | Leaks SQL, hostnames, or internal data | Return safe messages and error codes |
| Building `GraphQLError` without a path | Clients struggle to identify which field failed | Use `GraphqlErrorBuilder.newError(environment)` |
| Blocking threads inside `handleException` | Reduced throughput or deadlocks | Return `CompletableFuture` and avoid blocking |
| Returning `null` from `DataFetcherExceptionHandler` | Violates GraphQL Java's contract | Always return `DataFetcherExceptionHandlerResult` |
| Replacing default handler and bypassing Spring resolver chain | `@GraphQlExceptionHandler` may fail to run as expected | Prefer Spring resolvers or explicitly test the wiring |
| Mapping all errors to `BAD_REQUEST` | Hides server/dependency outages | Classify according to semantics |
| Using handler to synthesize fallback data | Mixes error mapping with business logic | Handle in resolver/service or via `DataFetcherResult` |
| Handling subscription stream errors with initial fetch handler | Misses errors emitted after the `Publisher` is returned | Use `SubscriptionExceptionResolver` |

## 20. Principles for Using DataFetcherExceptionHandler

`DataFetcherExceptionHandler` is GraphQL Java's low-level SPI that receives an exception alongside `DataFetchingEnvironment` and asynchronously returns a `DataFetcherExceptionHandlerResult`. Use `GraphqlErrorBuilder` with the environment to preserve `path` and `sourceLocation`; classify errors with an appropriate `ErrorClassification` and expose only safe messages and codes in the response.

In Spring for GraphQL, prefer `DataFetcherExceptionResolver`, `DataFetcherExceptionResolverAdapter`, or `@GraphQlExceptionHandler` for business exception handling. If configuring `DataFetcherExceptionHandler` directly, verify it does not drop the default resolver chain. Distinguish DataFetcher exceptions from parse/validation errors, transport failures, and subscription publisher errors.

Test paths, aliases, list indices, classifications, extensions, null propagation, async failures, and message security using `GraphQlTester`. The handler's sole job is turning exceptions into GraphQL errors; business fallbacks, partial data, authorization, and transactions belong in their respective layers.

## References

- [GraphQL Java — DataFetcherExceptionHandler API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandler.html)
- [GraphQL Java — DataFetcherExceptionHandlerParameters API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandlerParameters.html)
- [GraphQL Java — DataFetcherExceptionHandlerResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherExceptionHandlerResult.html)
- [Spring for GraphQL — Request Execution and Exception Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
