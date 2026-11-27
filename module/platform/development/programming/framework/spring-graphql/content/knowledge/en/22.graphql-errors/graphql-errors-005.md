# GraphQlExceptionHandler

In Spring for GraphQL, **@GraphQlExceptionHandler** lets you convert exceptions thrown during GraphQL field execution into a structured GraphQL error with a client-appropriate message. This annotation enables controllers to handle business errors such as missing resources, invalid data, or insufficient permissions without manually building JSON responses.

Exception handlers can be declared directly inside a controller or centralized in `@ControllerAdvice`. This lesson covers how to register handlers, choose error types, preserve field paths and locations, return partial data, distinguish execution errors from request errors, combine with `DataFetcherExceptionResolver`, and test using `GraphQlTester`.

## 1. Why is GraphQlExceptionHandler needed?

Suppose the schema has a Query to look up a book:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

The service might throw an exception when the book is not found:

~~~java
public Book findById(String id) {
    return bookRepository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

If the resolver does not handle the exception, the GraphQL engine still needs to build a response conforming to the GraphQL response format. The client needs a meaningful error, such as the code `BOOK_NOT_FOUND`, rather than internal details like SQL statements, stack traces, or Java class names.

Spring for GraphQL provides `@GraphQlExceptionHandler` to map exceptions to `GraphQLError`:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
    }
}
~~~

When `findById` throws `BookNotFoundException`, Spring finds the matching handler and uses the `GraphQLError` returned by the handler to record the error in the GraphQL response.

`@GraphQlExceptionHandler` handles exceptions during field execution. It does not replace operation syntax checking or schema validation before resolvers run.

## 2. How do GraphQL errors differ from HTTP errors?

GraphQL typically returns operation results in the response body. A single response can contain both `data` and `errors`.

For example, when the `book` field is nullable and the resource is not found:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"],
            "extensions": {
                "classification": "NOT_FOUND",
                "code": "BOOK_NOT_FOUND"
            }
        }
    ]
}
~~~

Key points to understand:

- `data` describes the results of the fields that executed.
- `errors` describes errors raised during operation processing.
- `path` indicates the location of the failing field in the response.
- `locations` can indicate the field position in the GraphQL document.
- `extensions` contains additional metadata such as error codes or classification.

A GraphQL execution error does not necessarily cause the entire HTTP request to fail. Over HTTP transport, the server usually still returns a protocol-compliant GraphQL response, while the HTTP status depends on the error type and transport configuration.

Do not treat every GraphQL error as an HTTP 500. Business errors such as missing resources or insufficient permissions can be represented in `errors` while the response remains a valid GraphQL response.

## 3. Handlers in controllers and @ControllerAdvice

There are two common places to declare `@GraphQlExceptionHandler`.

### Local handler in a controller

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

Placing the handler inside a controller fits when the error only has meaning for that controller's resolvers or when error interpretation depends on a specific domain.

### Shared handler with @ControllerAdvice

When multiple controllers need the same handling rules, you can place the handler in `@ControllerAdvice`:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;

@ControllerAdvice
public class GraphQlGlobalExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

`@ControllerAdvice` helps group common rules such as validation errors, access denied, or business errors shared across multiple resolvers.

| Location | Appropriate scope |
| --- | --- |
| `@Controller` | Errors specific to a single controller or a closely related group of resolvers. |
| `@ControllerAdvice` | Errors shared across multiple annotated controllers. |

If both local handlers and shared advice exist, design their scopes clearly. Local handlers suit errors understood only by that controller; advice handles common errors not handled at the controller level.

## 4. How is an exception handler selected?

A handler must declare the exception type it handles via the method's exception parameter.

For example:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {
    // ...
}
~~~

Spring looks up a handler matching the exception thrown while invoking the data fetcher. Use specific business exceptions to avoid an overly broad handler accidentally catching unrelated errors.

For example, do not use a single handler for all `RuntimeException` instances and return `NOT_FOUND`. Missing book errors, validation errors, access permission errors, and database errors should be classified differently.

Exceptions can be organized by domain:

~~~java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}

public class InvalidBookInputException extends RuntimeException {
    public InvalidBookInputException(String message) {
        super(message);
    }
}
~~~

The handler uses the exception type to determine the public error code. You do not have to send `exception.getMessage()` verbatim to the client, because internal messages may contain IDs, queries, or details that should not be exposed.

## 5. Creating GraphQLError with ErrorType

Spring for GraphQL provides `ErrorType` to classify common errors.

Commonly used values:

| ErrorType | Meaning |
| --- | --- |
| `BAD_REQUEST` | Input or request is invalid in the execution context. |
| `UNAUTHORIZED` | Unauthenticated or lacking appropriate credentials. |
| `FORBIDDEN` | Authenticated but not permitted to perform the action. |
| `NOT_FOUND` | Required resource not found. |
| `INTERNAL_ERROR` | Internal error whose details should not be exposed to the client. |

These are the standard classifications commonly used in Spring for GraphQL. For more specific cases such as version conflicts, temporarily unavailable dependencies, or timeouts, use `extensions.code` to publish a stable business code; choose `ErrorType` based on the general group that matches the API policy.

Example of handling invalid input:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleInvalidInput(
        InvalidBookInputException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Invalid book data")
            .errorType(ErrorType.BAD_REQUEST)
            .extensions(Map.of("code", "INVALID_BOOK_INPUT"))
            .build();
}
~~~

`ErrorType` provides consistent classification for errors. Clients can rely on stable codes in `extensions` to display messages or decide the next action.

Do not use `INTERNAL_ERROR` for all business errors. Proper classification makes error monitoring and client-side handling much easier.

## 6. Adding error codes via extensions

`GraphQLError` has an `extensions` field to carry additional metadata. This is the right place for stable error codes that clients can handle programmatically.

For example:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBookConflict(
        BookConflictException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("The book was updated by another operation")
            .errorType(ErrorType.BAD_REQUEST)
            .extensions(Map.of(
                    "code", "BOOK_VERSION_CONFLICT",
                    "retryable", true
            ))
            .build();
}
~~~

The response may contain:

~~~json
{
    "errors": [
        {
            "message": "The book was updated by another operation",
            "path": ["updateBook"],
            "extensions": {
                "classification": "BAD_REQUEST",
                "code": "BOOK_VERSION_CONFLICT",
                "retryable": true
            }
        }
    ]
}
~~~

Extension conventions should be stable and documented. Do not put arbitrary values like stack traces, SQL, connection strings, tokens, or credentials into extensions.

Use constants or enums for error codes on the server to avoid typos and help clients handle them consistently.

## 7. Preserving path and location with DataFetchingEnvironment

When creating a `GraphQLError`, you can pass `DataFetchingEnvironment` to `GraphqlErrorBuilder.newError(environment)`:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("Book not found")
            .errorType(ErrorType.NOT_FOUND)
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
}
~~~

A builder created from the environment has information about the currently executing field, including the appropriate path and source location. This is especially useful when the same exception type can occur across multiple fields or inside a nested selection set.

Example query:

~~~graphql
query {
    books {
        id
        publisher {
            name
        }
    }
}
~~~

If an error occurs in `publisher.name` of the second item, the path might describe a location like:

~~~json
{
    "path": ["books", 1, "publisher", "name"]
}
~~~

Clients can use path to determine which field could not complete. If you manually create an error with `GraphqlErrorBuilder.newError()` without an environment, path/location might not be attached as desired. When handling errors from a specific DataFetcher, prefer the builder that takes the environment.

## 8. Partial data and null propagation

GraphQL can return successful data for some fields alongside errors on other fields.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
    serviceStatus: String!
}
~~~

Client query:

~~~graphql
query {
    book(id: "missing") {
        id
        title
    }
    serviceStatus
}
~~~

If `book` is nullable, an error at this field can produce the response:

~~~json
{
    "data": {
        "book": null,
        "serviceStatus": "UP"
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"]
        }
    ]
}
~~~

The `serviceStatus` field can still return a result.

If the schema declares `book: Book!`, the resolver cannot complete the field with null. GraphQL applies the non-null propagation rule: null bubbles up to the nearest nullable parent. If that parent is also non-null, propagation continues upward. If the error reaches the root `data`, the entire `data` may become null.

Therefore, nullability in SDL is part of the error contract. Choose nullable/non-null based on whether the client can still use the remaining data, rather than merely wishing responses always had data.

## 9. Distinguishing execution errors and request errors

`@GraphQlExceptionHandler` focuses on exceptions raised during data fetcher execution. Some errors occur before any resolver is called.

| Error type | Timing | Example | Does a resolver handler handle it? |
| --- | --- | --- | --- |
| Parse error | Reading GraphQL document | Missing bracket, invalid syntax | No |
| Validation error | Checking document against schema | Querying a non-existent field | No |
| Input coercion error | Normalizing variables/arguments | Missing non-null input field, invalid enum | No |
| Execution error | Running resolver/data fetcher | Service throws `BookNotFoundException` | Yes |
| Binding/validation during resolver invocation | Passing arguments into method or validating data | DTO fails binding or validation throws exception | Depends on where it occurs and configured handling |

Example parse error:

~~~graphql
query {
    book(id: "1" {
        id
    }
}
~~~

GraphQL cannot parse the document, so no `book` resolver is ever invoked. A controller handler cannot fix operation syntax.

Example validation error: the schema has no `unknownBooks` field, yet the client queries it. This is a pre-execution document validation error.

If a client sends a missing `ID!` or an invalid enum, GraphQL can reject the request during the input coercion stage. This is also not a business exception inside a resolver.

Choose the appropriate mechanism for each stage: clients fix operations/inputs, the server fixes schemas or configuration, and `@GraphQlExceptionHandler` handles exceptions during field execution.

## 10. Distinguishing @GraphQlExceptionHandler from @ExceptionHandler

Spring MVC has `@ExceptionHandler` for handling exceptions in HTTP controller request flows. Spring for GraphQL has `@GraphQlExceptionHandler` for exceptions during GraphQL data fetcher execution.

| Annotation | Scope |
| --- | --- |
| `@ExceptionHandler` | Handles exceptions in Spring MVC/WebFlux HTTP controller mechanisms. |
| `@GraphQlExceptionHandler` | Converts exceptions from GraphQL data fetchers into GraphQL errors. |

GraphQL controllers do not typically build HTTP responses directly like REST controllers. A GraphQL operation can have multiple fields and partial data, so an exception handler must produce `GraphQLError` following GraphQL response semantics.

Do not use `@ExceptionHandler` in place of `@GraphQlExceptionHandler` when the goal is to handle exceptions thrown by GraphQL resolvers.

## 11. When is DataFetcherExceptionResolver needed?

`@GraphQlExceptionHandler` is convenient for annotated controllers. When you need centralized exception handling at the GraphQL execution layer or want to integrate general resolver logic, you can implement `DataFetcherExceptionResolver`.

Example adapter:

~~~java
@Component
public class BookDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

The resolver returns a `GraphQLError` when it recognizes the exception. Returning `null` means this resolver does not handle the exception, giving subsequent resolvers a chance to handle it.

Choose one primary strategy for each error group:

- Use `@GraphQlExceptionHandler` when handling exceptions tied to annotated controllers.
- Use `DataFetcherExceptionResolver` when you need centralized rules at the execution layer, including non-annotated data fetchers.
- Avoid implementing the same mapping in multiple places without clear precedence rules.

Do not write a custom resolver just to change a simple message if the annotation already meets your needs.

## 12. Security error handling and avoiding internal leaks

Exceptions can contain sensitive information:

- SQL statements or table names.
- Internal file paths.
- Hostnames, ports, or connection strings.
- Tokens, credentials, or personal data.
- Stack traces and configuration details.
- Internal IDs that the client is not allowed to know.

Do not return `exception.getMessage()` directly for every exception. Instead, use safe messages and public error codes:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleUnexpectedError(
        RuntimeException exception,
        DataFetchingEnvironment environment) {

    log.error(
            "Unexpected GraphQL error at {}",
            environment.getExecutionStepInfo().getPath(),
            exception
    );

    return GraphqlErrorBuilder.newError(environment)
            .message("An error occurred while processing the request")
            .errorType(ErrorType.INTERNAL_ERROR)
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
}
~~~

This example illustrates the principle of hiding internal details. In real systems, carefully consider handler ordering and scope so that a broad handler for `RuntimeException` does not shadow specifically classified business exceptions.

For access permission errors, do not disclose whether a resource exists if security policy requires hiding its existence. Use the same message or error code where required by the application's threat model.

## 13. Combining Spring Security with GraphQlExceptionHandler

A resolver may call a service and receive `AccessDeniedException` if the user lacks permission.

For example:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .message("You do not have permission to perform this action")
            .errorType(ErrorType.FORBIDDEN)
            .extensions(Map.of("code", "ACCESS_DENIED"))
            .build();
}
~~~

However, not all authentication or authorization failures occur inside resolvers. Some requests may be rejected by Spring Security filters before the GraphQL engine receives the operation. `@GraphQlExceptionHandler` does not replace authentication/authorization configuration at the transport layer.

Distinguish between:

- Authentication: identifying who the user is.
- Authorization: determining whether the user is allowed to perform an action.
- GraphQL error mapping: representing exceptions raised during execution as errors under the GraphQL contract.

Do not use exception handlers as a substitute for permission checks in services or method security.

## 14. Testing GraphQlExceptionHandler with GraphQlTester

Test handlers through actual GraphQL operations rather than just calling handler methods directly.

Example controller with resolver:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

A global exception handler returns `NOT_FOUND` when the service throws `BookNotFoundException`.

Test:

~~~java
@Test
void mapsBookNotFoundToGraphQlError() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
        .execute();

    response.errors().satisfy(errors ->
            assertThat(errors).anySatisfy(error -> {
                assertThat(error.getMessage())
                        .isEqualTo("Book not found");
                assertThat(error.getPath())
                        .containsExactly("book");
                assertThat(error.getExtensions())
                        .containsEntry("code", "BOOK_NOT_FOUND");
            }));

    response.path("book").valueIsNull();
}
~~~

This example assumes the `book` field is nullable in the SDL. If the field is non-null, verify null propagation at parent/root levels according to the actual schema.

Cases to test:

- Business exceptions map to the right `ErrorType`.
- `extensions.code` has a stable code.
- Path points to the exact failing field.
- Partial data for other fields is preserved.
- Non-null propagation follows the SDL.
- Local handlers handle only errors belonging to that controller.
- Handlers in `@ControllerAdvice` apply across multiple controllers.
- Unrecognized exceptions fall through to the next resolver or fallback mechanism.
- Responses do not contain stack traces, SQL, or sensitive rejected values.
- Parse/validation/coercion errors are not confused with execution exceptions.

When testing shared handlers, test at least one resolver per controller or a representative operation to confirm the advice is detected in the application context.

## 15. Common pitfalls

| Symptom | Common cause | Solution |
| --- | --- | --- |
| Handler is not called | Method is not in a Spring-detected controller/advice or exception did not happen during execution. | Check component scan, annotations, and error stage. |
| Handler does not match exception | Exception parameter is incompatible with the actual exception. | Use specific exception types and check cause. |
| Client receives generic errors | No matching handler or fallback resolver handled it. | Register handlers for business exceptions that need classification. |
| Path is missing or wrong | Creating GraphQLError without using the execution environment. | Use `GraphqlErrorBuilder.newError(environment)`. |
| Loss of partial data | Misunderstanding that a field error breaks the entire operation or parent field is non-null. | Check nullability and null propagation. |
| All errors become NOT_FOUND | Handler catches too broad an exception type. | Separate exceptions by domain and ErrorType. |
| Stack trace or SQL leaked | Returning raw exception message to client. | Use safe messages and log details on the server. |
| `@ExceptionHandler` does not handle resolver errors | Using HTTP controller annotation instead of GraphQL handler. | Use `@GraphQlExceptionHandler` or DataFetcherExceptionResolver. |
| Handler does not catch parse errors | Parse/validation runs before data fetchers. | Fix request/schema or handle at the appropriate request/transport layer. |
| Permission error gets wrong classification | Mixing authentication, authorization, and business exceptions. | Distinguish UNAUTHORIZED, FORBIDDEN, and business errors. |

## 16. Exception handling design workflow

When adding error handling to a GraphQL API, follow this sequence:

1. Determine whether the exception occurs at the request stage or execution stage.
2. Create specific business exceptions for situations meaningful to clients.
3. Choose a local handler or `@ControllerAdvice` according to scope of reuse.
4. Select the appropriate `ErrorType`.
5. Define stable error codes in `extensions`.
6. Use `DataFetchingEnvironment` when path/location needs to be preserved.
7. Design safe messages that do not expose internal information.
8. Check field nullability and the impact of null propagation.
9. Use `DataFetcherExceptionResolver` if centralized execution-layer handling is needed.
10. Test errors, path, extensions, and partial data with `GraphQlTester`.
11. Separately test parse, validation, and input coercion errors.
12. Monitor server logs/metrics using an appropriate correlation ID.

## 17. Key takeaways

- `@GraphQlExceptionHandler` converts exceptions raised during GraphQL data fetcher execution into `GraphQLError`.
- Handlers can live in `@Controller` or `@ControllerAdvice`.
- Use specific business exceptions to avoid misclassifying errors.
- `ErrorType` provides classification; `extensions` can carry stable error codes for clients.
- Use `GraphqlErrorBuilder.newError(environment)` to retain field path and location.
- GraphQL can return partial `data` alongside `errors`; nullability dictates how nulls propagate.
- Parse, validation, and input coercion errors happen before resolvers run and are therefore not handled as execution exceptions.
- `@GraphQlExceptionHandler` differs from Spring MVC's `@ExceptionHandler`.
- `DataFetcherExceptionResolver` fits when centralized error handling at the GraphQL execution layer is needed.
- Never return stack traces, SQL, tokens, or internal information in messages/extensions.
- Use `GraphQlTester` to verify `ErrorType`, path, extensions, and partial data.

`@GraphQlExceptionHandler` helps standardize business errors in Spring for GraphQL in accordance with GraphQL response semantics. When exceptions are clearly classified, field paths are preserved, nullability is respected, and internal details are protected, clients can handle errors consistently while still using the valid portions of an operation's data.
