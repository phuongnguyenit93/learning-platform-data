# Adding a GraphQL Error Handler

## Objectives

After this hands-on practice, you will be able to:

- Create a GraphQL error handler for exceptions thrown from resolvers.
- Use `@GraphQlExceptionHandler` in a controller or `@ControllerAdvice`.
- Choose the appropriate `ErrorType` and publish stable error codes via `extensions`.
- Preserve the field `path` and source `location` of a GraphQL error.
- Use `DataFetcherExceptionResolverAdapter` for custom `DataFetcher`s.
- Distinguish field execution errors from request-level errors and subscription errors.
- Test the error contract with `GraphQlTester`.
- Avoid leaking SQL, stack traces, tokens, or internal details in GraphQL responses.

## Problem Statement

A library API has a query to fetch a book by ID. When the book does not exist, the service throws `BookNotFoundException`. If the exception goes straight to the GraphQL engine, Spring for GraphQL falls back to its default mechanism and returns a generic internal error when no resolver handles the exception.

Clients need a stable error contract to distinguish:

- Book does not exist.
- Invalid input data.
- User is not authenticated.
- User is not authorized.
- Unexpected server error.

We will add a `@ControllerAdvice` to map domain exceptions to `GraphQLError`. Each error has a safe message, an `ErrorType`, and an `extensions.code` value so clients can handle errors without parsing message text.

## Declaring the Schema and Resolver

Create the schema in `src/main/resources/graphql/book.graphqls`:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

The `book` field is nullable so that when a book is not found, GraphQL can return `book: null` along with an error on that field. If changed to `Book!`, the error will propagate null up to the parent according to GraphQL's Non-Null rules.

Domain exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Service:

~~~java
public interface BookService {

    Book findById(String id);
}
~~~

Resolver:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

The resolver does not need to catch `BookNotFoundException` itself. The exception is routed to the error handler at the GraphQL data-fetching boundary.

## Creating a Global Error Handler with @ControllerAdvice

`@GraphQlExceptionHandler` declares a method that handles exceptions from data fetching. When placed inside a `@Controller`, the handler only applies to mapping methods in that controller. When placed inside `@ControllerAdvice`, the handler can apply across GraphQL controllers in the application.

Create a shared handler:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("The requested book was not found.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Spring for GraphQL prepares `GraphqlErrorBuilder<?>` from the `DataFetchingEnvironment` of the failing field. As a result, the error preserves the corresponding `path` and `locations`. This is the recommended approach in annotated exception handlers; creating an empty builder manually with `GraphqlErrorBuilder.newError()` can lose field location information.

The internal exception message may still contain IDs or technical details. The handler returns a safe message and a stable error code instead of passing `exception.getMessage()` directly to the client.

### Handling Multiple Exception Types

A handler can define multiple methods, each handling a group of exceptions. When the annotation does not specify `value`, Spring infers the exception type from the exception parameter in the method signature:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("The requested book was not found.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleInvalidInput(
            BindException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data.")
                .extensions(Map.of("code", "INPUT_INVALID"))
                .build();
    }
}
~~~

If you need to specify exception types explicitly, you can pass one or more classes to `@GraphQlExceptionHandler`'s `value`, e.g., `@GraphQlExceptionHandler({BookNotFoundException.class, LegacyBookException.class})`. The method signature must accept a common supertype compatible with the declared types, usually `RuntimeException` or `Throwable`.

For validation, you may need to return multiple errors for input fields. `@GraphQlExceptionHandler` supports returning `Collection<GraphQLError>` so clients receive multiple errors in the same response. Standardize the extension structure and input field names according to your API contract.

## Choosing ErrorType and Error Codes

`ErrorType` is the general classification provided by Spring for GraphQL. `extensions.code` is the stable application-defined business error code.

| ErrorType | Use When | Example extensions.code |
| --- | --- | --- |
| BAD_REQUEST | Input or business request is invalid | INPUT_INVALID |
| UNAUTHORIZED | Unauthenticated or invalid credentials | AUTHENTICATION_REQUIRED |
| FORBIDDEN | Authenticated but not permitted to perform action | ACCESS_DENIED |
| NOT_FOUND | Resource not found | BOOK_NOT_FOUND |
| INTERNAL_ERROR | Unexpected or internal error | INTERNAL_ERROR |

Do not use `NOT_FOUND` for every exception just to avoid returning HTTP 500. Classification should reflect the cause so clients can handle it properly.

`ErrorType` has a finite set of values, suitable for high-level categorization. `extensions.code` should have a dedicated, stable, documented list of codes. Do not use `message` as an error code because messages can change across languages or wording revisions.

`ErrorType` is a GraphQL error classification, not a directive to automatically set HTTP status codes per error. The transport still applies its own status rules; clients should read the GraphQL response and `extensions.code` rather than inferring from HTTP status.

Example response a client can process:

~~~json
{
  "errors": [
    {
      "message": "The requested book was not found.",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ],
  "data": {
    "book": null
  }
}
~~~

The `classification` field in JSON is how GraphQL Java/Spring represents `ErrorType`; exact response fields also depend on the error serializer and version. Clients should rely on the application-managed `extensions.code`.

## Local Handler Inside a Controller

If an exception only applies to a single controller, you can place the handler directly in that controller:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found.")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Choose scope based on responsibility:

- Handler in controller: errors specific to that controller.
- `@ControllerAdvice`: errors shared across multiple controllers.
- `DataFetcherExceptionResolver`: errors from `DataFetcher`s not implemented with annotated controllers.

Do not declare the same exception in multiple handlers with overlapping scopes without a clear reason. Duplicate handlers make it harder to determine where errors are mapped.

## Handling Exceptions from Custom DataFetchers

`@GraphQlExceptionHandler` is applied automatically to controller method invocations. If the application registers a `graphql.schema.DataFetcher` directly via `RuntimeWiringConfigurer`, exceptions from that data fetcher do not pass through controller exception handlers.

Spring for GraphQL provides `DataFetcherExceptionResolver`. You can extend `DataFetcherExceptionResolverAdapter` to map exceptions synchronously:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import java.util.Map;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class CatalogDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof CatalogUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("The catalog service is currently unavailable.")
                    .extensions(Map.of("code", "CATALOG_UNAVAILABLE"))
                    .build();
        }

        // Return null so the next resolver has a chance to handle it.
        return null;
    }
}
~~~

The Spring Boot GraphQL starter automatically detects `DataFetcherExceptionResolver` beans and registers them with the GraphQL engine. Multiple resolvers can be declared; they are called in order until one handles the exception.

`DataFetcherExceptionResolverAdapter` provides `resolveToSingleError` and `resolveToMultipleErrors`. Returning `null` from these methods means the exception was not handled by the current resolver; Spring can pass it to the next resolver. If no resolver handles it, the default handler returns an `INTERNAL_ERROR` with a generic message and execution ID to avoid leaking implementation details.

In this example, `CatalogUnavailableException` is an exception from a custom data fetcher calling a catalog service. For standard controller methods, prefer `@GraphQlExceptionHandler` because the code is concise and ties directly into the controller programming model.

## Errors Not Handled by Data-Fetcher Error Handlers

Not all GraphQL errors go through `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.

| Error Type | Why It Bypasses Data-Fetcher Handlers | Where It Is Handled |
| --- | --- | --- |
| Parse error | Document cannot be parsed; no fields are executed | GraphQL engine returns a request error |
| Validation error | Document does not conform to schema; data fetchers are not invoked | GraphQL engine returns a request error; `WebGraphQlInterceptor` can transform the response |
| Variable coercion error | Variables cannot be coerced to schema types before execution | GraphQL engine returns a request error |
| Exception in resolver | Occurs while a data fetcher is executing | `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` |
| Exception from Subscription Publisher after resolver returns | Publisher emits an error only after the data fetcher has created the publisher | `SubscriptionExceptionResolver` |
| WebSocket disconnect or HTTP timeout | Transport error; there may be no GraphQL response | Transport/client/server handling |

`DataFetcherExceptionResolver` only handles errors raised when a data fetcher is called. For example, a query with invalid syntax or a non-existent field is rejected before execution and therefore cannot be handled by this resolver.

For request-level errors that need transformation, you can use `WebGraphQlInterceptor` to inspect `ExecutionResult` after `ExecutionGraphQlService` processes it. Do not use an interceptor to replace error mapping for business exceptions from resolvers.

For subscriptions, `DataFetcherExceptionResolver` only sees errors thrown while the data fetcher creates the publisher. If the publisher emits an error signal later, `SubscriptionExceptionResolver` is required to convert the error into GraphQL errors sent over WebSocket or the corresponding transport.

## GraphQL Error Responses and Partial Data

When a field resolver throws an exception, GraphQL can return partial data alongside `errors`:

~~~graphql
query {
  book(id: "missing") {
    id
    title
  }
}
~~~

With a nullable `book: Book` in the schema, the response can be:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "The requested book was not found.",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

If a query has multiple root fields and only one fails, the remaining fields can still return data. Clients must inspect both `data` and `errors`; they must not discard all data simply because `errors` is present.

`path` uses the field's response key, so an alias appears in `path` instead of the schema field name. `locations` points to the field's position in the GraphQL document. Using the injected `GraphqlErrorBuilder<?>` allows the handler to preserve this metadata.

Nullability determines the scope of null propagation:

- Nullable field fails: that field can become `null`, while sibling fields can still retain data.
- Non-null field fails: null propagates up to the nearest nullable parent.
- If root `data` has no nullable parent left to stop propagation, `data` itself can become `null`.

Schema nullability and error contracts must be consistent. Do not mark every field as non-null if clients need to continue displaying the parts of the data that succeeded.

## Testing the Error Handler with GraphQlTester

Add the test dependency if the project does not already have it:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
~~~

With Spring Boot 4, `@GraphQlTest` auto-configures the GraphQL infrastructure and `GraphQlTester` without starting an HTTP server. Controller advice can be explicitly imported in the test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
@Import(GlobalGraphQlExceptionHandler.class)
class BookErrorHandlerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void mapsBookNotFoundToGraphQlError() {
        given(bookService.findById("missing"))
                .willThrow(new BookNotFoundException("missing"));

        graphQlTester.document("""
                query BookDetails {
                    book(id: "missing") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> {
                    assertThat(errors).hasSize(1);
                    assertThat(errors.get(0).getMessage())
                            .isEqualTo("The requested book was not found.");
                    assertThat(errors.get(0).getPath())
                            .containsExactly("book");
                    assertThat(errors.get(0).getExtensions())
                            .containsEntry("code", "BOOK_NOT_FOUND");
                });
    }
}
~~~

The test verifies three parts of the error contract:

1. The returned message matches the defined safe text.
2. The path points to the `book` field.
3. The extension code is `BOOK_NOT_FOUND`, independent of the message.

`@GraphQlTest` loads only a slice of the application context. Services/repositories must be mocked or imported separately. In Spring Boot 3.x, the package for `@GraphQlTest` is `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest`; starting in Spring Boot 4, it moved to `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest`.

If the test requires HTTP filters, the security chain, or transport behavior, use `@SpringBootTest` with `HttpGraphQlTester` instead of a slice test.

### Recommended Test Cases

| Case | What to Verify |
| --- | --- |
| BookNotFoundException | `NOT_FOUND` and `BOOK_NOT_FOUND` |
| BindException or input error | `BAD_REQUEST` and `INPUT_INVALID` |
| AccessDeniedException | `FORBIDDEN` and `ACCESS_DENIED` |
| AuthenticationException | `UNAUTHORIZED` and `AUTHENTICATION_REQUIRED` |
| Unmapped exception | `INTERNAL_ERROR` and generic message |
| Nested resolver failure | Path includes full parent/field segments |
| Aliased field | Path uses the alias in the response |
| Nullable field failure | Partial data is preserved |
| Non-null field failure | Null propagation matches the schema |
| Custom DataFetcher exception | Handled by `DataFetcherExceptionResolver` |
| Request validation error | Does not invoke data-fetcher resolver |

## Security Guidelines When Returning Errors

A GraphQL error is part of the public API response. Never return raw exception messages or stack traces to clients in production.

Do not include the following in `message` or `extensions`:

- SQL statements, table names, and database details.
- File paths, hostnames, internal URLs, or implementation class names.
- Stack traces, tokens, passwords, session IDs, or secrets.
- Personal information of other users.
- Sensitive input values that the client does not need to know.

Use short, user-presentable messages; stable `extensions.code` values for client logic; and an `executionId` or trace ID in internal logs for investigation. Spring for GraphQL's default handler also uses a generic message for unhandled exceptions and logs them with an execution ID.

Do not map every exception to `BAD_REQUEST`. If the database or a downstream service fails, classifying it as an input error misleads clients and can hide operational incidents.

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@GraphQlExceptionHandler` is not called | Exception comes from a custom `DataFetcher` that is not a controller method | Use `DataFetcherExceptionResolver` |
| Handler runs in only one controller | Handler was placed inside a `@Controller` | Move to `@ControllerAdvice` if it should apply globally |
| Response lacks `path` or `locations` | Created `GraphQLError` with a builder not bound to `DataFetchingEnvironment` | Inject `GraphqlErrorBuilder<?>` or use `newError(environment)` |
| Client must parse message to identify error | No stable `extensions.code` is provided | Define error codes and an error contract |
| Database error leaks raw exception message | Handler passes `exception.getMessage()` | Use a safe message and keep details in logs |
| Request with invalid field misses handler | Validation fails before data fetchers run | Let the GraphQL engine return request errors or use `WebGraphQlInterceptor` when needed |
| Subscription publisher errors are not mapped | `DataFetcherExceptionResolver` only handles errors when creating the `Publisher` | Register a `SubscriptionExceptionResolver` |
| Sibling data disappears after a field error | Non-null field propagates null up to parent | Review nullability against the contract |
| Multiple resolvers handle the same exception | Overlapping resolver chain or handler scopes | Clarify responsibilities and resolver ordering |
| Test fails even when testing expected errors | `GraphQlTester` treats errors as assertion failures by default on verify | Use `errors().expect(...)` or `errors().satisfy(...)` to assert errors |

## Comprehensive Practice

Complete the error handling for the library API:

1. Create the schema `Query.book(id: ID!): Book`.
2. Write `BookNotFoundException` and have the service throw it when no book exists.
3. Write `BookController` with `@QueryMapping`.
4. Create `GlobalGraphQlExceptionHandler` using `@ControllerAdvice`.
5. Use `@GraphQlExceptionHandler` to map `BookNotFoundException` to `NOT_FOUND` and `BOOK_NOT_FOUND`.
6. Add a handler for `BindException` with `BAD_REQUEST` and `INPUT_INVALID`.
7. Create a `DataFetcherExceptionResolverAdapter` for a custom `DataFetcher` calling an external service.
8. Send a query with a non-existent ID and verify `errors.message`, `errors.path`, and `errors.extensions.code`.
9. Verify that nullable fields return partial data according to the schema.
10. Send a query with a non-existent field to confirm request-level validation errors bypass data-fetcher handlers.
11. Trigger an unhandled exception and confirm the default `INTERNAL_ERROR` does not leak internal details.
12. Write tests for authorization errors and verify the corresponding `UNAUTHORIZED`/`FORBIDDEN` codes.

After completing these steps, explain why `@GraphQlExceptionHandler` and `DataFetcherExceptionResolver` must be distinguished, why request validation errors bypass both mechanisms, and why clients should rely on `extensions.code`.

## Key Takeaways

Add a GraphQL error handler using `@GraphQlExceptionHandler` to map exceptions from annotated controllers into `GraphQLError`. Place it in `@Controller` when scoped locally or `@ControllerAdvice` when shared. Inject `GraphqlErrorBuilder<?>` to preserve `path` and `locations`; classify with `ErrorType` and publish stable codes in `extensions.code`. For custom `DataFetcher`s, use `DataFetcherExceptionResolverAdapter`. Request parse/validation errors occur before execution; subscription publisher errors require `SubscriptionExceptionResolver`. Test your error contract with `GraphQlTester` and always return safe messages without leaking internal details.

## References

- [Spring for GraphQL – Annotated Controllers, @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL – Request Execution, Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL – Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [DataFetcherExceptionResolverAdapter API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolverAdapter.html)
