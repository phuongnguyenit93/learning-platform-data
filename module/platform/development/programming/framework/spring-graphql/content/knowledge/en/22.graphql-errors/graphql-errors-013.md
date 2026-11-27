# Hiding stack traces from clients

## Objectives

After this lesson, you will be able to:

- Explain why stack traces and internal exception details should not appear in GraphQL responses.
- Distinguish client-facing GraphQL errors from exceptions and stack traces used for server operations.
- Understand the `message`, `locations`, `path`, and `extensions` components of a GraphQL error.
- Standardize business errors into safe messages and stable error codes.
- Handle exceptions using `@GraphQlExceptionHandler` and `@ControllerAdvice`.
- Recognize the role of `DataFetcherExceptionResolver` in handling errors from DataFetchers.
- Log stack traces on the server alongside request IDs and field paths to assist investigation.
- Avoid exposing SQL, table names, file paths, hostnames, tokens, and personal data.
- Understand partial data and null propagation when a field encounters an error.
- Test with `GraphQlTester` to verify responses do not contain internal information.

## 1. Why must stack traces be hidden from clients?

When a resolver throws an exception, the stack trace can contain package names, class names, method names, libraries, system structure, and error locations. With exceptions from databases or HTTP clients, the details can also contain SQL, table names, hostnames, internal paths, or input data.

If raw stack traces or exception messages are placed into GraphQL responses, clients receive information unnecessary for consuming the API yet useful to someone probing the system's architecture.

Example of information that should not be sent externally:

~~~text
org.springframework.dao.DataAccessResourceFailureException:
JDBC exception executing SQL [select * from internal_book ...]

    at com.example.catalog.BookRepository.findById(BookRepository.java:87)
    at com.example.catalog.BookService.findBook(BookService.java:42)
    at com.example.catalog.BookController.book(BookController.java:31)
    ...
Caused by: org.postgresql.util.PSQLException:
Connection to db-internal.prod.local refused
~~~

Clients only need to know that the operation did not complete and can use an error code to decide the next step. Stack traces belong in server-side logs with proper access controls.

The design principle is to separate two outputs:

- **Client response:** short, stable message without internal details.
- **Server diagnostics:** exception, stack trace, field path, request ID, and technical details needed for investigation.

Do not solve this by discarding all error information. Keep sufficient diagnostic data on the server while limiting what is returned to the client.

## 2. What components does a GraphQL error have?

A GraphQL response can contain `data` and `errors`. An error typically has the following components:

| Component | Meaning | Points to note |
| --- | --- | --- |
| `message` | Error description for the caller | Must be controlled; do not reuse raw internal exception messages |
| `locations` | Position in the GraphQL document related to the error | Usually provided by the GraphQL runtime |
| `path` | Path to the failing field in the response | Helpful with aliases or nested fields |
| `extensions` | Extended metadata provided by the runtime or application | Include only permitted error codes and metadata |

Example of a safe response:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "An error occurred while processing the request.",
            "locations": [
                {
                    "line": 2,
                    "column": 5
                }
            ],
            "path": [
                "book"
            ],
            "extensions": {
                "classification": "INTERNAL_ERROR",
                "code": "INTERNAL_ERROR"
            }
        }
    ]
}
~~~

This response tells the client that the `book` field did not complete and provides a stable error code. It does not reveal Java exception names, stack traces, SQL statements, or database addresses.

The exact structure of `extensions` depends on the error classification and application configuration. Standardize public error codes and keep them stable so clients can handle them.

GraphQL errors do not define a standard field named `stackTrace`. Stack traces usually leak when an application appends them to `message`, adds them to `extensions`, or uses a custom serializer/debug handler that injects internal exceptions into the response. Therefore, review both error builders and any custom response-formatting classes.

## 3. Distinguishing exceptions, GraphQL errors, and HTTP errors

These three concepts are not synonymous:

- **Java exception:** an object thrown when processing encounters an error.
- **GraphQL error:** an error represented in a GraphQL response, typically tied to a field or operation.
- **HTTP error:** a transport-layer status, such as when a request cannot be processed due to protocol or infrastructure failures.

An exception from a resolver can be mapped into a GraphQL error in the response. In that case, the HTTP request can still receive a normal GraphQL response even when the response contains `errors`.

For example, `Query.book` queries the database and the service throws `BookNotFoundException`. The application can map this exception to a GraphQL error with code `BOOK_NOT_FOUND`. The client receives an error conforming to the GraphQL contract instead of a Java stack trace.

Conversely, parse or validation errors in the GraphQL document can occur before any DataFetcher is invoked. `DataFetcherExceptionResolver` is not the place to handle all HTTP errors or all parse/validation errors. Choose the right handling layer for each error type.

## 4. Do not return exception messages directly

A dangerous practice often starts with using `ex.getMessage()` to build responses:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    try {
        return bookService.findById(id);
    }
    catch (Exception ex) {
        throw new RuntimeException(ex.getMessage(), ex);
    }
}
~~~

Exception messages can originate from:

- JDBC drivers or ORMs.
- HTTP clients and downstream services.
- Filesystems or file-handling libraries.
- Developer-created exceptions that concatenate input data.
- Messages containing IDs, emails, or personal data.

Do not put `ex.getMessage()`, `ex.toString()`, or `ex.getStackTrace()` into a GraphQL error's `message` or `extensions`.

Instead, map known exceptions to public messages:

| Internal exception | Client message |
| --- | --- |
| `BookNotFoundException` | The requested book was not found. |
| `AccessDeniedException` | You do not have permission to perform this action. |
| `DuplicateBookException` | The book already exists. |
| `DataAccessException` | Unable to complete the operation right now. |
| Unexpected exception | An error occurred while processing the request. |

Public messages should be concise and contain no details about how the system stores or retrieves data.

## 5. Handling errors with @GraphQlExceptionHandler

Spring for GraphQL supports `@GraphQlExceptionHandler` to map exceptions thrown during resolution into GraphQL errors.

Handlers can be placed inside the controller handling the relevant fields or inside `@ControllerAdvice` to apply across multiple controllers. For API-wide error policies, global advice keeps error responses consistent.

For example:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
class GraphQlExceptionAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlExceptionAdvice.class);

    @GraphQlExceptionHandler
    public GraphQLError handle(
            Exception exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("The requested book was not found.")
                    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        Object requestId =
                environment.getGraphQlContext().get("requestId");

        log.error(
                "Unhandled GraphQL exception requestId={} path={}",
                requestId,
                environment.getExecutionStepInfo().getPath(),
                exception
        );

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("An error occurred while processing the request.")
                .extensions(Map.of("code", "INTERNAL_ERROR"))
                .build();
    }
}
~~~

In this example:

- `@ControllerAdvice` registers a shared exception handler for GraphQL controllers.
- `@GraphQlExceptionHandler` marks the exception-handling method.
- `DataFetchingEnvironment` provides information about the currently resolving field and the GraphQL context.
- `GraphqlErrorBuilder` builds a GraphQL error bound to the execution environment.
- `ErrorType.NOT_FOUND` and `ErrorType.INTERNAL_ERROR` classify errors.
- `extensions.code` provides a stable error code for clients.
- The full exception is passed to the server-side logger, not placed into the response.

The example uses one consolidated handler to illustrate classification. In a larger application, you can separate handlers for specific exceptions and keep a fallback handler for unexpected exceptions. Ensure specific exceptions are mapped before falling into the generic branch.

## 6. Separating business errors and system errors

Not every exception needs the same message.

Known business errors can be safely interpreted:

~~~java
if (exception instanceof BookNotFoundException) {
    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("The requested book was not found.")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
}
~~~

Unexpected system errors should use a generic message:

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.INTERNAL_ERROR)
        .message("An error occurred while processing the request.")
        .extensions(Map.of("code", "INTERNAL_ERROR"))
        .build();
~~~

Do not return the same `INTERNAL_ERROR` code for every business scenario. Clients need to distinguish actionable cases, such as:

- `BOOK_NOT_FOUND`
- `BOOK_ALREADY_EXISTS`
- `ACCESS_DENIED`
- `VALIDATION_FAILED`
- `INTERNAL_ERROR`

Do not put Java exception class names into public error codes. Error codes are part of the API contract; codes can remain unchanged even when refactoring packages or changing backend implementations.

## 7. Role of DataFetcherExceptionResolver

`DataFetcherExceptionResolver` is a GraphQL execution-layer mechanism for handling exceptions thrown from DataFetchers and converting them into a list of GraphQL errors.

In Spring for GraphQL, you can implement a custom resolver or use the adapter to map exceptions. This mechanism fits when centralized error handling at the execution layer is preferred over placing exception handler logic in annotated controllers.

Example resolver skeleton:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
class SafeDataFetcherExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("The requested book was not found.")
                    .build();
        }

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("An error occurred while processing the request.")
                .build();
    }
}
~~~

`DataFetcherExceptionResolverAdapter` offers a straightforward implementation when one exception maps to one GraphQL error. For more complex needs, you can implement `DataFetcherExceptionResolver` directly.

Choose one mechanism suited to your application structure. `@GraphQlExceptionHandler` is convenient near controllers or in `@ControllerAdvice`; `DataFetcherExceptionResolver` fits centralized exception handling at the execution layer. Avoid registering multiple handlers for the same exception without clear precedence rules.

## 8. Errors that do not pass through DataFetcherExceptionResolver

`DataFetcherExceptionResolver` handles exceptions thrown during DataFetcher execution. It does not replace all GraphQL and HTTP error-handling mechanisms.

For example:

| Stage | Example error | Appropriate handling layer |
| --- | --- | --- |
| HTTP transport | Unreadable request body, dropped connection | Web server and transport layer |
| GraphQL parse | Query document has syntax error | GraphQL parser/execution |
| GraphQL validation | Non-existent field or schema-invalid argument | GraphQL validation |
| DataFetcher execution | Resolver or service throws an exception | `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` |
| Bean validation | Input violates constraint | Appropriate validation and exception mapping |
| Downstream infrastructure | Database or HTTP service fails inside resolver | Resolver exception handling with logging/monitoring |

Do not try to use a resolver to handle errors that occur before a DataFetcher is invoked. Understand which stage an error belongs to in order to configure the right layer.

Even though parse/validation errors do not pass through exception resolvers, still inspect their responses to ensure no custom error handler appends stack traces or sensitive information to `message`/`extensions`.

## 9. Log stack traces on the server, never send them to clients

Hiding stack traces from responses does not mean removing stack traces from monitoring systems. When unexpected exceptions occur, the server must log enough information to investigate.

For example:

~~~java
Object requestId =
        environment.getGraphQlContext().get("requestId");

log.error(
        "Unhandled GraphQL exception requestId={} path={}",
        requestId,
        environment.getExecutionStepInfo().getPath(),
        exception
);
~~~

The final `exception` argument lets SLF4J log the stack trace on the server. In the response, return only a generic message and an error code.

Consider logging:

- Request ID or correlation ID.
- GraphQL field path.
- Operation name if present and normalized.
- Exception type.
- Stack trace for system errors requiring investigation.
- Timestamp and service instance per system logging standards.

Do not log full variables or tokens alongside stack traces. Exception messages sometimes contain inputs or SQL, so logs must be protected, role-restricted, and redacted when necessary.

## 10. Using request IDs to link logs and responses

A request identifier helps locate the corresponding log entry when a client submits an error report.

The request ID can be placed into `GraphQLContext` in an interceptor or where execution input is created. The exception handler reads the same key when logging.

Example retrieving request ID:

~~~java
Object requestId =
        environment.getGraphQlContext().get("requestId");
~~~

Clients can receive a stable error code such as `INTERNAL_ERROR`. If the API needs users to send a reference ID to support, you can provide a separately generated and controlled `correlationId` in `extensions`.

Do not put stack traces into `extensions` merely to aid debugging. `extensions` is still part of the response sent to clients. A reference ID is sufficient for internal systems to look up logs.

## 11. Do not swallow exceptions by returning null

A misleading approach is catching every exception and returning `null`:

~~~java
@QueryMapping
public Book book(@Argument("id") UUID id) {
    try {
        return bookService.findById(id);
    }
    catch (Exception exception) {
        return null;
    }
}
~~~

This prevents clients from distinguishing between:

- The book does not exist.
- The user lacks permission to view it.
- The database is down.
- A downstream service timed out.
- There is a programming bug in the resolver.

If the field is nullable, GraphQL may return `null` with no error, leading the client to mistake it for a valid result.

Throw an appropriate business exception or let exceptions flow through centralized error handling. Return `null` only when null is a valid outcome according to the schema and business rules.

## 12. Partial data and null propagation

GraphQL can return data for successful fields alongside errors for failing fields.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Query {
    book(id: ID!): Book
}
~~~

If `internalNotes` fails while `book` and `title` remain valid, the response can contain `book` with `internalNotes: null` alongside an error whose path points to that field.

If the failing field is declared non-null, GraphQL applies null propagation up to the nearest nullable parent. Thus, hiding stack traces does not alter nullability semantics.

Do not turn every field nullable just to prevent errors from bubbling up to parents. Design the schema according to data semantics and map errors according to the contract.

## 13. Data that must never be included in GraphQL errors

Never include the following information in `message` or `extensions`:

- Stack traces or lists of stack frames.
- `exception.toString()` or unsanitized exception messages.
- SQL, database queries, or internal table names.
- Database addresses, hostnames, internal IPs, and ports.
- File paths, deployment directories, or server hostnames.
- Access tokens, refresh tokens, API keys, cookies, or session IDs.
- Passwords, OTPs, payment data, and personal information.
- Request variables or entire input objects.
- Downstream system response bodies containing private data.

Send only information needed by clients, such as safe messages, error codes, and controlled correlation IDs.

## 14. Testing to verify stack traces are not leaked

Tests should verify both the error contract and the absence of internal information in responses.

Example with `GraphQlTester`:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
            }
        }
        """)
        .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("An error occurred while processing the request.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "INTERNAL_ERROR");
    assertThat(errors.get(0).getMessage())
            .doesNotContain(" at com.example.");
    assertThat(errors.get(0).getExtensions())
            .doesNotContainKey("stackTrace");
});
~~~

This test assumes the service raises an unexpected exception and the global handler maps it to a generic error.

Also add tests for business exceptions:

~~~java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("The requested book was not found.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Scenarios to test:

- Business exceptions map to public messages and error codes.
- Unexpected exceptions return a generic message.
- Responses do not contain stack traces or exception class names.
- Responses do not contain SQL, hostnames, or internal paths.
- Server logs still record exceptions and request IDs per policy.
- GraphQL error path points to the right field.
- Partial data and null propagation conform to the schema.
- Parse/validation errors are not turned by custom handlers into responses containing internal details.

Do not check only for the string `stackTrace`. Inspect `message`, `extensions`, and any custom fields the application may add to responses.

## 15. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Client sees Java class names | Returning `exception.toString()` or `getMessage()` | Map to public messages |
| Response contains stack frames | Manually appending stack traces to message/extensions | Remove diagnostic data from responses |
| Database exception leaks SQL | Returning raw exception message | Use generic messages and internal logging |
| No logs for investigation | Replacing exception with generic error and discarding original exception | Log exceptions on the server with request IDs |
| All errors become `INTERNAL_ERROR` | Not classifying business exceptions | Map specific exceptions to error codes |
| Field returns null with no error | Resolver catches exception and returns null | Use exception mapping when null is not a valid result |
| `DataFetcherExceptionResolver` does not run | Error occurred in parse/validation or transport | Handle at the appropriate layer |
| Client does not know which field failed | Error lacks proper execution environment/path | Use `GraphqlErrorBuilder.newError(environment)` |
| Error message changes with database driver | Using exception message as API contract | Use stable messages and error codes |
| Logs contain sensitive data | Logging variables or exception messages unchecked | Use allowlists, redaction, and restricted log access |

## 16. Workflow for implementing safe error handling

When designing exception handling for a GraphQL API, follow this sequence:

1. **Classify error sources.** Determine whether the error belongs to transport, parse, validation, or DataFetcher execution.
2. **Define the error contract.** Standardize `message`, `ErrorType`, and `extensions.code`.
3. **Map business errors.** Return public messages for known exceptions.
4. **Handle unexpected exceptions.** Return generic messages without appending exception messages.
5. **Record diagnostics on the server.** Log exceptions, stack traces, request IDs, and field paths per policy.
6. **Keep responses minimal.** Never put SQL, hostnames, tokens, stack traces, or variables into errors.
7. **Review nullability.** Determine partial data and null propagation from the SDL.
8. **Audit other resolvers.** Do not let resolvers catch errors and return null outside valid business semantics.
9. **Test the error contract.** Use `GraphQlTester` to verify messages, codes, paths, and absence of leaked data.
10. **Monitor production.** Use request IDs to link client reports with internal logs and traces.

## 17. Summary

Hiding stack traces from clients is a crucial requirement when building secure GraphQL APIs. Exceptions and stack traces must stay on the server for diagnostics; GraphQL responses should contain only controlled messages, stable error codes, and metadata genuinely needed by clients.

In Spring for GraphQL, you can use `@GraphQlExceptionHandler` with `@ControllerAdvice` or `DataFetcherExceptionResolver` to map DataFetcher exceptions into GraphQL errors. Separate business errors from system errors, never return `getMessage()`, `toString()`, or stack traces in `message`/`extensions`, and log diagnostics on the server with request IDs and field paths. Testing with `GraphQlTester` verifies the error contract, partial data, and null propagation while catching accidental leaks of internal information.
