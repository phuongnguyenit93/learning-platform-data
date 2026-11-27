# Exceptions in controllers

In Spring for GraphQL, exceptions thrown while a resolver processes a field can be converted into GraphQL errors using `@GraphQlExceptionHandler`. This annotation lets you place error-handling logic directly inside a controller or centralize shared handling in a `@ControllerAdvice` class.

This organization separates business errors from GraphQL response details. Services can throw exceptions representing scenarios such as a missing book, an order state that disallows cancellation, or an account that already exists. Controller advice converts exceptions into errors with safe messages, stable error codes, and appropriate classifications for clients to handle.

## 1. How do resolver exceptions differ from GraphQL errors?

A GraphQL operation can fail at multiple stages:

1. **Parse**: the document has invalid syntax, such as a missing bracket or delimiter.
2. **Document validation**: the query uses a non-existent field, lacks a selection set, or misplaces a fragment.
3. **Input coercion**: a variable or argument has the wrong type or violates nullability.
4. **Field execution**: a resolver or service throws an exception while executing a field.

`@GraphQlExceptionHandler` primarily handles exceptions raised during data fetcher/resolver execution. Parse, document validation, and coercion errors occur before any controller method is invoked; therefore, a controller handler cannot handle them as ordinary business exceptions.

Example of a syntactically valid query where the book does not exist:

```graphql
type Query {
    book(id: ID!): Book
}
```

```java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
```

`BookNotFoundException` arises while the resolver runs. This is the right situation for an exception handler to convert it into a GraphQL error.

## 2. GraphQL response structure on error

According to the GraphQL response format, an execution result can contain `data`, `errors`, or both. Each element in `errors` can include `message`, `locations`, `path`, and `extensions`.

Example error on the `book` field:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book not found.",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

An error in one field does not necessarily fail the entire operation. Other fields can still return data if they do not depend on the failing field and nullability rules allow it. `path` indicates the location of the failing field in the response; if the query uses an alias, path uses that alias as the response key.

`extensions` is an appropriate place to supply additional metadata such as error codes or classification information needed by clients. Do not include stack traces, SQL statements, file paths, internal hostnames, or authentication details here.

## 3. Creating business exceptions

Exceptions should describe business conditions detected by the service. For example:

```java
package com.example.graphql.book;

public class BookNotFoundException extends RuntimeException {

    private final String bookId;

    public BookNotFoundException(String bookId) {
        super("Book not found: " + bookId);
        this.bookId = bookId;
    }

    public String getBookId() {
        return bookId;
    }
}
```

Service throwing an exception when data is not found:

```java
@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Book findById(String id) {
        return repository.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

The service does not need to know how the GraphQL response is structured. The exception represents a business error; the GraphQL layer decides how to expose the error in the response. That same service can be reused by a REST controller or another processing flow.

## 4. Handling exceptions directly in the controller

`@GraphQlExceptionHandler` can be placed on a method inside a `@Controller`. A local handler fits when the exception only relates to resolvers in that controller or when error presentation depends on the controller's context.

```java
package com.example.graphql.book;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import org.springframework.graphql.execution.ErrorType;

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
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found.")
            .build();
    }
}
```

The handler receives the exception to handle and `DataFetchingEnvironment` to construct an error bound to the executing field position. `GraphqlErrorBuilder.newError(environment)` preserves field location and path information. `ErrorType.NOT_FOUND` classifies the error according to Spring for GraphQL; the returned message is controlled text rather than directly reusing an internal message that might contain IDs or sensitive data.

A handler in `BookController` is scoped locally to that controller. If `AuthorController` also throws `BookNotFoundException`, this handler does not automatically act as a shared handler for the other controller.

## 5. Using @ControllerAdvice for global error handling

When multiple controllers need the same exception mapping rules, place the handler in a class annotated with `@ControllerAdvice`. This avoids repeating the same logic in every controller.

```java
package com.example.graphql.error;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Requested resource was not found.")
            .build();
    }
}
```

`@ControllerAdvice` applies handlers to annotated controllers within component scan scope. You can create multiple advices by error group or module; when scopes overlap, use intentional advice ordering and avoid declaring multiple handlers accepting the same exception ambiguously.

Local handlers in a controller fit controller-specific logic. Handlers in `@ControllerAdvice` fit shared conventions such as not found, conflict, validation, or system errors. Choose a single primary owner for each exception type to avoid unpredictable behavior.

## 6. Returning error codes via extensions

Clients often need a stable error code to decide what action to take, such as displaying a form, prompting to sign in again, or allowing the user to retry. Messages can vary by language, so do not use messages as error identifiers.

You can add an error code in `extensions`:

```java
import java.util.Map;

@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.NOT_FOUND)
        .message("Book not found.")
        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
        .build();
}
```

The response may look like:

```json
{
  "errors": [
    {
      "message": "Book not found.",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

Additional extensions may be added by the framework depending on the error type. The client contract should rely on an application-defined error code field, such as `code`, rather than depending on message text or internal implementation details.

## 7. Handling multiple exception types

An application typically has several business error groups. You can create separate handlers for each exception:

```java
import java.util.Map;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {
        return error(environment, ErrorType.NOT_FOUND,
            "Book not found.", "BOOK_NOT_FOUND");
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookConflict(
            BookConflictException exception,
            DataFetchingEnvironment environment) {
        return error(environment, ErrorType.BAD_REQUEST,
            "Unable to perform changes on this book.", "BOOK_CONFLICT");
    }

    private GraphQLError error(
            DataFetchingEnvironment environment,
            ErrorType errorType,
            String message,
            String code) {
        return GraphqlErrorBuilder.newError(environment)
            .errorType(errorType)
            .message(message)
            .extensions(Map.of("code", code))
            .build();
    }
}
```

In this example, two business exceptions are converted into two distinct error codes. The `java.util.Map` import is needed for the helper.

Do not create a blanket handler catching every `Exception` and returning `exception.getMessage()` verbatim. That easily leaks internal details and turns programming bugs into public messages. Map only expected exceptions; unrecognized errors should be logged on the server and return a safe generic message.

## 8. Classifying errors and choosing ErrorType

Spring for GraphQL provides `ErrorType` to classify common errors. Classifications can be applied to situations such as:

| Classification | Example scenario |
| --- | --- |
| `BAD_REQUEST` | Invalid input or business request |
| `UNAUTHORIZED` | Request is not authenticated |
| `FORBIDDEN` | User is authenticated but lacks permission |
| `NOT_FOUND` | Resource does not exist or is not disclosed |
| `INTERNAL_ERROR` | Unexpected system error |

Choose the classification based on the meaning of the error, not merely the Java exception name. For example, `AccessDeniedException` should be classified as forbidden; a database timeout is usually an internal error. The error code in `extensions.code` can be more specific than the general classification.

GraphQL error classification is not synonymous with the HTTP status code of the overall request. A GraphQL operation can return HTTP 200 with `errors` in the body, especially when errors occur during execution. Transport has its own rules for certain request errors; clients should inspect the GraphQL response body instead of relying solely on HTTP status.

## 9. Nullability and error propagation

When a resolver throws an exception, the corresponding field is treated as an execution error. GraphQL applies the schema's nullability rules to determine which field becomes null and how far the error propagates.

For example:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author!
}
```

If the `Book.author` resolver fails, the `author` field cannot return null because it is declared `Author!`. Null propagates up to the `Book` object; if `Query.book` is nullable, the `book` result can become null. If every parent field along the path is non-null, null can propagate all the way to `data` at the root.

Therefore, choosing nullability is part of designing error behavior. Do not mark every field non-null just to make the schema look strict. Reflect data availability and decide whether an error in a child field should discard the entire parent object.

## 10. Validation errors do not go through controller handlers

`@GraphQlExceptionHandler` does not replace GraphQL document validation. For example, if a client selects a `unknownField` that does not exist in the schema or passes a string for an `Int!` argument, the request is rejected before resolvers run.

These errors are typically produced directly in the response by the GraphQL engine. If you need to observe or normalize request errors at the transport level, consider `WebGraphQlInterceptor` to inspect `WebGraphQlResponse` after execution. Do not try to catch parse/validation errors in a controller because the controller method is never invoked.

Similarly, errors occurring in HTTP authentication filters before a request reaches the GraphQL handler belong to the Spring Security/web layer. Using the right extension point for each stage keeps error-handling code clear and ensures no errors are missed.

## 11. Handling authorization errors safely

Authentication and authorization errors require careful handling because messages can reveal the existence of a resource or user information.

Example handler for denied access:

```java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.FORBIDDEN)
        .message("You do not have permission to perform this action.")
        .extensions(Map.of("code", "ACCESS_DENIED"))
        .build();
}
```

Do not include role names, internal policies, tenant IDs, or detailed permission conditions in the message if clients do not need to know them. Mapping an exception to a GraphQL error also does not replace permission checks in resolvers/services. The server must enforce authorization before returning data or mutating state.

In some systems, `NOT_FOUND` and `FORBIDDEN` are intentionally returned identically so as not to reveal that a resource exists when the user is not allowed to view it. This is a security policy decision that must be applied consistently.

## 12. Logging exceptions without leaking data

Clients need understandable messages, while server logs need enough information for diagnosis. These two purposes should not share a single raw exception string.

A handler can log in a controlled manner before returning the error:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    private static final Logger log =
        LoggerFactory.getLogger(GraphQlExceptionAdvice.class);

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        log.info("Book lookup failed, path={}",
            environment.getExecutionStepInfo().getPath());

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found.")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

For system errors, log the exception with its stack trace on the server at an appropriate log level and attach a correlation ID/trace ID if available. Avoid logging access tokens, cookies, full GraphQL variables, or unnecessary personal data. Clients receive only safe messages and actionable error codes.

## 13. Testing exception handlers with GraphQlTester

You can use `GraphQlTester` to verify that exceptions from resolvers are converted into GraphQL errors. For example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookController.class)
class BookExceptionHandlerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsBookNotFoundToGraphQlError() {
        graphQlTester.document("""
                query {
                    book(id: "missing-book") {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
```

This example assumes the test context provides a mock `BookService` or test bean throwing `BookNotFoundException` for ID `missing-book`. You can inspect `message`, `path`, and `extensions.code` further using the `ResponseError` API of your Spring GraphQL version.

Scenarios to test:

- Exceptions thrown from root query resolvers.
- Exceptions thrown from nested field resolvers.
- Local handlers and `@ControllerAdvice` handlers having the right scope.
- Unrecognized exceptions not leaking internal messages.
- Validation/coercion errors still returned by the GraphQL engine even when resolvers do not run.
- Non-null propagation matching the schema.
- Authorization errors not exposing sensitive data.

## 14. Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| `@GraphQlExceptionHandler` is not called | Exception occurred before resolver or handler is out of scope | Identify the error stage and check controller/advice beans |
| Local handler does not catch exceptions from another controller | Handler only applies within its owning controller | Use `@ControllerAdvice` for shared handling |
| Client receives internal message | Returning `exception.getMessage()` directly | Use safe messages and stable error codes |
| `data` unexpectedly becomes null | Non-null field triggers null propagation | Review nullability and field error handling |
| Client checks only HTTP status and misses errors | GraphQL execution errors can accompany HTTP 200 | Inspect `errors` in the GraphQL response as well |
| Validation error bypasses controller handler | Request rejected before resolver | Use GraphQL response/interceptor for request-level observation |
| Multiple handlers match the same exception | Advice overlap or unclear mapping | Organize handlers and advice ordering intentionally |

## 15. Exception handler design checklist

- Does the exception represent the right business error and originate from the appropriate layer?
- Is the handler placed locally or globally with the right scope?
- Is the message returned to the client safe and understandable?
- Is `extensions.code` stable for client handling?
- Does the classification accurately reflect not found, forbidden, bad request, or internal error?
- Are error paths and field locations preserved?
- Does schema nullability produce the desired null propagation?
- Are parse/validation/coercion errors distinguished from resolver errors?
- Do server logs capture enough detail without containing secrets or unnecessary data?
- Do tests verify both error responses and handler scope?

`@GraphQlExceptionHandler` helps convert exceptions raised in controller resolvers into structured GraphQL errors. Use local handlers for controller-specific rules and `@ControllerAdvice` for shared rules; keep public messages safe, provide stable error codes in `extensions`, and choose appropriate classifications. At the same time, keep in mind that parse/validation errors occur before resolvers run, follow schema null propagation rules, and understand the difference between GraphQL errors and HTTP status so clients handle errors accurately.
