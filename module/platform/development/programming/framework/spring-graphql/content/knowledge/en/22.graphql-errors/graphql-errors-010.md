# Error extensions

## Objectives

After this lesson, you will be able to:

- Explain the role of the extensions field in a GraphQL error.
- Design stable error codes so clients handle errors by rules rather than comparing messages.
- Put safe metadata such as error codes, field validation details, and request IDs into error extensions.
- Create extensions using GraphqlErrorBuilder in Spring for GraphQL.
- Standardize extensions when mapping exceptions with DataFetcherExceptionResolver.
- Distinguish error extensions from response extensions, path, locations, and HTTP status.
- Test error extensions using GraphQlTester.

## What are error extensions?

A GraphQL response can contain a list of errors. Each error has standard fields such as message, locations, and path when applicable. In addition, GraphQL allows the server to provide an extensions object to attach application-specific metadata.

For example:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND",
        "requestId": "req-8f31"
      }
    }
  ]
}
~~~

In this example:

- message briefly describes the error.
- path indicates which response field encountered the error.
- extensions.code is a machine-readable code for the client to identify the error type.
- extensions.requestId helps users or clients correlate the error with server logs if this ID is designed to be public.

extensions is not a field in the GraphQL schema and clients do not query it via selection sets. It is metadata sent alongside an error in the response. Its internal structure is defined by the application, so the server and clients must agree on the contract.

Not every response has error extensions. If the operation succeeds, the errors list may be absent. If a nullable field returns null under normal semantics and there is no execution error, there is no need to create an error just to attach metadata.

## Why are error codes needed?

Do not let clients classify errors by comparing message content. Messages can change when wording is edited, translated into another language, or expanded with guidance.

For example, the following messages could all represent the same situation:

- "Book not found"
- "The book does not exist or was deleted"
- "We could not find this book"

Clients need a stable code:

~~~json
{
  "message": "Book not found",
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
~~~

When the message changes, clients can still handle BOOK_NOT_FOUND. An error code is part of the API contract; renaming or removing a code can break older clients.

A good error code should:

- Have a clear and unique meaning within the API scope.
- Not depend on Java exception class names or package structure.
- Be used consistently across all resolvers sharing the same error type.
- Not contain user IDs, tokens, or dynamic data.
- Be documented so clients know what action to take.

Examples of error codes:

| Code | Meaning | Action client can take |
| --- | --- | --- |
| BOOK_NOT_FOUND | Book not found | Display not-found state |
| BOOK_UPDATE_FORBIDDEN | User is not allowed to update the book | Display permission message |
| VALIDATION_FAILED | Invalid input data | Display errors on the form |
| DUPLICATE_BOOK_ISBN | ISBN is already in use | Ask user to check the ISBN |
| RATE_LIMITED | Request limit exceeded | Consider retrying according to policy |
| INTERNAL_FAILURE | Unexpected internal error | Display generic message and provide request ID if available |

Do not create overly generic codes like ERROR for every situation. Also do not create overly granular codes for every wording variation. Choose a classification level that helps clients decide on an action.

## Designing the extensions structure

A common structure is placing the error code in code, then adding useful metadata:

~~~json
{
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "price",
      "code": "MUST_BE_POSITIVE"
    },
    {
      "field": "name",
      "code": "MUST_NOT_BE_BLANK"
    }
  ],
  "requestId": "req-8f31"
}
~~~

Not every error needs every property. Send only information meaningful for that error type:

| Property | Purpose | Note |
| --- | --- | --- |
| code | Stable error code | Should be present for application errors clients must handle |
| fieldErrors | List of errors per input field | Return only field names and safe validation codes |
| requestId | Link response to logs | Expose only non-sensitive lookup IDs |
| retryable | Hint whether the error can be retried | Must reflect actual semantics, not inferred for all server errors |
| retryAfterSeconds | Suggested wait interval before retrying | Use only when the server has a concrete policy |

Do not turn extensions into a copy of the exception or the entire request context. The more metadata you include, the harder the contract is to maintain and the greater the risk of leaking information.

### Do not confuse error extensions with response extensions

GraphQL also allows metadata at the response level, outside the errors list:

~~~json
{
  "data": {
    "books": []
  },
  "extensions": {
    "cost": 4,
    "requestId": "req-8f31"
  }
}
~~~

These are response-level extensions, typically used for metadata applying to the whole operation such as query cost or request ID. By contrast, errors[i].extensions belongs to one specific error.

These two locations have different scopes:

- Response extensions: shared metadata for the execution.
- Error extensions: metadata describing a specific error.

Do not put a field's error code into response extensions if the operation can have multiple different errors. Place the code on each error so clients can match the right code to the right path.

## Creating error extensions with GraphqlErrorBuilder

GraphQL Java provides GraphqlErrorBuilder to build GraphQLError instances. You can use extensions(Map<String, Object>) to attach metadata:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Book not found")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "requestId", requestId))
        .build();
~~~

newError(environment) enables the builder to attach field execution information such as path and locations when available. errorType provides a general classification; extensions.code is a detailed code defined by the application's API.

Do not assume that GraphQL Java's default classification names or structure will always remain identical across versions. If clients need a stable property, explicitly publish it in your application extensions, such as code.

### Centralizing error codes as constants

Avoid typing arbitrary error code strings across multiple resolvers. You can use an enum:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    BOOK_UPDATE_FORBIDDEN,
    VALIDATION_FAILED,
    DUPLICATE_BOOK_ISBN,
    INTERNAL_FAILURE
}
~~~

A small helper keeps error creation consistent:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

public final class ApiGraphQlErrors {

    private ApiGraphQlErrors() {
    }

    public static GraphQLError notFound(
            DataFetchingEnvironment environment,
            ApiErrorCode code,
            String message,
            String requestId) {

        return GraphqlErrorBuilder.newError(environment)
                .message(message)
                .errorType(ErrorType.NOT_FOUND)
                .extensions(Map.of(
                        "code", code.name(),
                        "requestId", requestId))
                .build();
    }
}
~~~

Helpers should contain only genuinely reusable common rules. Do not build a complex error framework if the application only has a few simple error types.

## Standardizing extensions with DataFetcherExceptionResolver

In Spring for GraphQL, DataFetcherExceptionResolver converts exceptions from resolvers or services into GraphQLError instances. This is the right place to ensure all business exceptions share the same extensions structure.

Example exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Resolver:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class ApiExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        if (exception instanceof DuplicateBookIsbnException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("ISBN is already in use")
                    .errorType(ErrorType.BAD_REQUEST)
                    .extensions(Map.of(
                            "code", "DUPLICATE_BOOK_ISBN"))
                    .build();
        }

        return null;
    }
}
~~~

This resolver converts known exceptions into public error codes. Other exceptions are left for subsequent resolvers or the default mechanism to handle. When expanding the list of errors, ensure each exception type maps according to a clear rule.

Do not pass exception.getMessage() directly into the response if the message may contain internal data. Public messages should be controlled; full technical details are logged on the server.

### Adding a request ID to extensions

If the application already stores a request/correlation ID in GraphQLContext, the exception resolver can read the ID from DataFetchingEnvironment and attach it to the error:

~~~java
String requestId =
        environment.getGraphQlContext().get("correlationId");

return GraphqlErrorBuilder.newError(environment)
        .message("Book not found")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "requestId", requestId))
        .build();
~~~

In a real implementation, handle the case where request ID may be absent before calling Map.of, because Map.of does not allow null keys or values. You can build the map conditionally or use a null-safe helper.

Request ID should only be a safe lookup identifier. Do not put access tokens, session IDs, cookies, or full headers into extensions.

## Error extensions for validation

A validation error may need to indicate multiple invalid input fields. Instead of forcing clients to parse messages, the server can return a general code together with a list of field errors:

~~~json
{
  "message": "Invalid input data",
  "extensions": {
    "code": "VALIDATION_FAILED",
    "fieldErrors": [
      {
        "field": "name",
        "code": "MUST_NOT_BE_BLANK"
      },
      {
        "field": "price",
        "code": "MUST_BE_POSITIVE"
      }
    ]
  }
}
~~~

Clients can map field error codes to localized UI messages. The server remains responsible for validation; this metadata merely describes the validation outcome.

Example helper creating a validation error:

~~~java
Map<String, Object> extensions = Map.of(
        "code", "VALIDATION_FAILED",
        "fieldErrors", List.of(
                Map.of(
                        "field", "name",
                        "code", "MUST_NOT_BE_BLANK"),
                Map.of(
                        "field", "price",
                        "code", "MUST_BE_POSITIVE")));

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Invalid input data")
        .errorType(ErrorType.BAD_REQUEST)
        .extensions(extensions)
        .build();
~~~

This is an application-defined structure, not a mandatory GraphQL validation format. Keep property names and field error codes stable, and avoid sending rejected values if those values may contain personal data or secrets.

## Distinguishing error code, ErrorType, and HTTP status

These three concepts serve different layers:

| Component | Scope | Example |
| --- | --- | --- |
| extensions.code | Stable business code defined by the API | BOOK_NOT_FOUND |
| ErrorType | General error classification from Spring for GraphQL | NOT_FOUND, BAD_REQUEST |
| HTTP status | Status of the HTTP response/transport | 200, 4xx, 5xx depending on how the server handles the request |

GraphQL execution errors can appear alongside partial data. Therefore, you cannot assume every GraphQL error must return HTTP 4xx or 5xx. HTTP status depends on the error stage, transport, and server configuration. An error code in extensions does not automatically change the HTTP status either.

GraphQL clients should read response contents and error extensions according to the contract. For HTTP-level errors such as unreachable server, gateway timeout, or non-GraphQL responses, clients still need to handle HTTP/network errors separately.

## Designing safe metadata

extensions is sent to clients, so treat every value inside it as public data.

Safe to include:

- Documented error codes.
- Field names and validation codes without sensitive values.
- Random request IDs or lookup IDs that grant no access rights.
- Retry hints if the server defines clear conditions and durations.

Never include:

- Stack traces or unnecessary internal class names.
- SQL, table names, connection strings, or internal service addresses.
- Access tokens, refresh tokens, cookies, or session secrets.
- Entire input objects or raw user-submitted values.
- Principals, detailed permissions, or tenant data not meant to be public.

If deep diagnostics are needed, log details on the server and link them via request ID. Do not use error extensions as a debug channel in place of controlled logging.

## Client-side handling of extensions

Clients should branch on extensions.code and always have a default branch for unknown codes:

~~~typescript
function handleGraphQLError(error: GraphQLError) {
  switch (error.extensions?.code) {
    case "BOOK_NOT_FOUND":
      showBookNotFound();
      return;
    case "BOOK_UPDATE_FORBIDDEN":
      showPermissionDenied();
      return;
    case "VALIDATION_FAILED":
      showFieldErrors(error.extensions.fieldErrors);
      return;
    default:
      showGenericError();
  }
}
~~~

If a response has multiple errors, handle each error individually and use path to link the error to its corresponding field. An operation can have multiple field errors with different codes.

Clients should not assume extensions is always present or always contains code. Syntax errors, validation errors, or errors produced by middleware may have a different structure. Always check types and values before accessing them.

## Testing error extensions with GraphQlTester

GraphQlTester lets you inspect GraphQLError entries in the response. For example:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .variable("id", "missing-book")
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    GraphQLError error = errors.get(0);
    assertThat(error.getMessage())
            .isEqualTo("Book not found");
    assertThat(error.getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

In addition to code and message, verify:

1. path points to the exact response field, even when the query uses aliases.
2. locations points to the exact position in the operation when an error occurs on a field.
3. extensions does not contain tokens, stack traces, or internal data.
4. Validation errors have properly structured fieldErrors.
5. Partial data is still present when other independent fields succeed.
6. Error codes do not change when messages are edited or localized.
7. Unrecognized exceptions fall back safely.

Have contract tests to ensure client and server agree on the same set of error codes. Renaming or removing a code should be treated as an API change that can impact clients.

## Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Client depends on message | No stable error code | Define extensions.code |
| Some errors lack extensions | Error comes from parser, validator, or other middleware | Client must support errors without custom metadata |
| Inconsistent error codes across resolvers | Each controller defines its own code strings | Centralize codes and exception mapping |
| Extensions contain sensitive data | Putting exceptions, inputs, or principals into the response | Send only public, safe metadata |
| Request ID breaks Map creation | Null value passed into Map.of | Add key only when present or use a null-safe map |
| Client does not recognize new code | Missing fallback branch | Handle unknown codes with a generic message |
| Confusing code with HTTP status | Mixing GraphQL and HTTP transport layers | Handle error extensions and HTTP/network status separately |
| Validation message is hard to parse | Returning only a free-form message | Return fieldErrors with stable field and code values |

## Comprehensive practice

Design error extensions for the library API:

1. Define the code set BOOK_NOT_FOUND, BOOK_UPDATE_FORBIDDEN, VALIDATION_FAILED, and INTERNAL_FAILURE.
2. Create an enum or constants to avoid repeating code strings.
3. Use DataFetcherExceptionResolverAdapter to map business exceptions to GraphQLError.
4. Attach appropriate ErrorType and extensions.code for each error.
5. For validation, return fieldErrors containing field names and error codes; do not send sensitive rejected values.
6. Include a safe correlation ID in extensions.requestId if available.
7. Write GraphQlTester tests checking code, message, path, and extensions structure.
8. Ensure clients have a fallback branch for errors without extensions or with unknown codes.
9. Verify responses do not contain stack traces, tokens, SQL, or internal information.

After completing, explain why error codes are part of the API contract, why ErrorType does not replace business codes, and why HTTP status needs to be handled separately.

## Key takeaways

Error extensions are application-defined metadata attached to each GraphQL error. Use a stable extensions.code for client error handling, while keeping message for human-readable information. Spring for GraphQL can create GraphQLError instances with GraphqlErrorBuilder and standardize exceptions via DataFetcherExceptionResolver. You can add validation fields or request IDs if they are safe and useful. Distinguish error extensions from response extensions, ErrorType, and HTTP status. Always inspect extensions data before sending, avoid exposing internal details, and test the error contract with GraphQlTester.
