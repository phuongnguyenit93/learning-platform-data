# GraphQLError

## Objectives

After this lesson, you will be able to:

- Explain the role of GraphQLError in a GraphQL response.
- Read the message, locations, path, and extensions components.
- Create structured errors using GraphqlErrorBuilder.
- Classify errors using Spring for GraphQL's ErrorType.
- Map business exceptions to GraphQL errors using DataFetcherExceptionResolver.
- Distinguish between request errors, execution errors, and responses with partial data.
- Test GraphQL errors using GraphQlTester.

## What is GraphQLError?

GraphQLError is GraphQL Java's abstraction for representing an error during the processing of a GraphQL operation. A GraphQL response can contain data in data, errors in errors, or both.

For example, a query requesting a non-existent book:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

If the server chooses to report an error when the book is not found, the response might be:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        {
          "line": 2,
          "column": 3
        }
      ],
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

A GraphQL error is structured data in the response. Clients can use message to display appropriate information, path to identify the failing field, and extensions to handle errors by a stable error code.

Not every case without data requires a GraphQLError. If a field is nullable and the resolver intentionally returns null because the resource does not exist according to the API's semantics, the response can simply contain data with a null field and no errors. Clearly distinguish normal business outcomes from execution errors.

## Components of a GraphQL error

A GraphQLError can provide the following information:

| Component | Meaning | What clients typically use it for |
| --- | --- | --- |
| message | Brief description of the problem | Displaying or logging the error |
| locations | Position in the GraphQL document related to the error | Highlighting the operation or assisting with debugging |
| path | Path to the field in the response where the error occurred | Identifying the affected field/branch |
| extensions | Additional metadata following application conventions | Reading error codes, categories, or machine-readable information |
| ErrorClassification | Error classification according to GraphQL Java or Spring | Distinguishing error groups and handling them consistently |

Not every error has all components. For example, syntax or validation errors may have locations without a path because resolvers have not been executed yet. Errors occurring inside a resolver usually have a path pointing to the field that raised the error.

### message

message is the error description. It should be concise, clear, and appropriate for the response recipient. For example:

- "Book not found"
- "You do not have permission to perform this action"
- "Invalid input data"

Do not include internal exception contents, SQL statements, table names, internal service addresses, stack traces, or authentication information in message. Message is part of the response sent to the client.

### locations

locations is the line and column position in the GraphQL document. This position helps clients or developer tools identify the field/argument related to the error.

For example:

~~~graphql
query {
  bookById(id: "missing-book") {
    id
    title
  }
}
~~~

If an error occurs while resolving bookById, location usually points to the field in the operation. It is not the line number in the Java file containing the resolver.

### path

path is the path to the location in the response. Elements of path can be field names or list item indices.

For example, if a client uses an alias:

~~~graphql
query {
  featured: books {
    title
    author {
      name
    }
  }
}
~~~

If an error occurs at author's name in the second element, path might be:

~~~json
["featured", 1, "author", "name"]
~~~

Path uses the alias featured because that is the field name in the response. When handling errors on the client, do not assume path always matches the original field name in the schema.

### extensions

extensions is an extensible metadata area. This is an appropriate place to provide stable error codes:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "category": "NOT_FOUND"
}
~~~

Clients should rely on a code like BOOK_NOT_FOUND rather than comparing localized message text. Messages may be edited or translated; error codes should remain stable according to the API contract.

Only include permitted metadata in extensions. Do not put principals, tokens, personal data, database information, or internal details here.

## Creating GraphQLError with GraphqlErrorBuilder

GraphQL Java provides GraphqlErrorBuilder to create a GraphQLError. In Spring for GraphQL, this builder is commonly used when mapping exceptions or when a resolver needs to construct a structured error.

Example of a simple resolver throwing a business exception:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

In a real application, keep the controller focused on coordination and map exceptions in a shared resolver. GraphqlErrorBuilder.newError(environment) is useful because the builder can obtain field execution information such as locations and path from DataFetchingEnvironment.

When you need to create an error directly from a resolver, you can build a GraphQLError:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

GraphQLError error = GraphqlErrorBuilder.newError(environment)
        .message("Book not found")
        .errorType(ErrorType.NOT_FOUND)
        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
        .build();
~~~

GraphqlErrorBuilder.newError(environment) attaches the path and locations of the currently executing field. If creating an error not tied to a specific field, you can use the builder without DataFetchingEnvironment; in that case, path or locations may be absent.

You can then return the error together with data using DataFetcherResult if the use case requires it. There is no need to create GraphQLError manually for every exception; Spring provides an exception resolver mechanism to standardize errors centrally.

## Classifying errors with ErrorType

Spring for GraphQL provides ErrorType to classify common error groups. Commonly used values include:

| ErrorType | General meaning | Example |
| --- | --- | --- |
| BAD_REQUEST | Invalid request or input data | Input fails validation rules |
| UNAUTHORIZED | Unauthenticated or invalid credentials | Invalid token |
| FORBIDDEN | Authenticated but not permitted to perform the action | No permission to update the book |
| NOT_FOUND | Resource not found | No book found for the ID |
| INTERNAL_ERROR | Internal error whose details should not be exposed | Unexpected server error |

ErrorType is an ErrorClassification attached to GraphQLError. Clients can use classification or extensions code to categorize errors. Choose the type that matches the actual meaning; do not use INTERNAL_ERROR for all known business errors.

An API can use a more specific extensions.code:

| ErrorType | extensions.code |
| --- | --- |
| NOT_FOUND | BOOK_NOT_FOUND |
| BAD_REQUEST | INVALID_BOOK_TITLE |
| FORBIDDEN | BOOK_UPDATE_FORBIDDEN |
| UNAUTHORIZED | AUTHENTICATION_REQUIRED |
| INTERNAL_ERROR | INTERNAL_FAILURE |

ErrorType provides the general category, while code allows the client to handle each specific case. Do not let clients depend on Java exception class names or server log content.

## Mapping exceptions with DataFetcherExceptionResolver

In Spring for GraphQL, DataFetcherExceptionResolver is the extension point for handling exceptions raised during data fetcher execution. Instead of having each controller build its own error response, you can create a centralized resolver to convert business exceptions into GraphQLError.

Example exception:

~~~java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
~~~

Exception resolver:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class BookExceptionResolver
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

The resolver above only handles BookNotFoundException. When returning null, it indicates that this exception has not been handled by the current resolver so subsequent resolvers in the chain have a chance to handle it. If no resolver handles it, Spring for GraphQL's default mechanism handles the remaining error.

When an application has many exception types, you can split resolvers by business domain or create a consolidated resolver. Avoid having multiple resolvers handle the same exception in different ways.

### Do not expose exception messages

For example, an exception whose message contains an ID or internal information:

~~~java
throw new BookNotFoundException("book-101");
~~~

Do not return exception.getMessage() directly to the client if that message could contain information not permitted to be disclosed. The resolver above uses a controlled message and a stable extensions code.

For unexpected errors, log the exception on the server with a correlation ID and return a generic message. Do not put stack traces or configuration details into GraphQLError.

## Request errors and execution errors

GraphQL can detect errors at different stages:

| Error group | When it occurs | Does the resolver run? | Example |
| --- | --- | --- | --- |
| Syntax error | Parsing the GraphQL document | No | Missing bracket or invalid syntax |
| Validation error | Validating the operation against the schema | No | Querying a non-existent field |
| Input coercion error | Converting variables/literals to schema types | Corresponding field has not executed yet | Passing a String to an Int! argument |
| Execution error | During resolver or field execution | Yes | Service throws an exception |

Request errors usually prevent the operation from executing, so the response has no useful data from resolvers. Execution errors occur during field resolution; other independent fields can still succeed, and the response can contain partial data.

For example:

~~~json
{
  "data": {
    "bookById": null,
    "serviceStatus": "UP"
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

In this response, the bookById field encountered an error, but serviceStatus still returns a result. GraphQL does not require the entire response to fail just because one field has an error. Nullability can cause errors to propagate up to parent objects or the entire data if parent fields are non-null.

## GraphQLError and DataFetcherResult

Resolvers normally return a regular value. When you need to return data alongside one or more errors, you can use DataFetcherResult<T>:

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.execution.ErrorType;

import java.util.Map;

@QueryMapping
public DataFetcherResult<Book> bookDetails(
        @Argument("id") String id,
        DataFetchingEnvironment environment) {

    Book book = bookService.findById(id).orElse(null);
    if (book == null) {
        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(GraphqlErrorBuilder.newError(environment)
                        .message("Book not found")
                        .errorType(ErrorType.NOT_FOUND)
                        .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                        .build())
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
}
~~~

DataFetcherResult lets you attach errors, local context, or extensions along with data. It is useful when a resolver can provide valid data while also needing to report a specific issue. If data is null for a non-null field, null propagation still applies.

Do not use DataFetcherResult to hide system errors or return a false success response. Use it when the actual semantics involve returning data along with a warning/error on part of the result.

## Designing an error contract for clients

A good error contract helps clients handle errors consistently without depending on the server implementation:

~~~json
{
  "message": "You do not have permission to update this book",
  "extensions": {
    "code": "BOOK_UPDATE_FORBIDDEN",
    "category": "FORBIDDEN",
    "requestId": "req-7f31"
  }
}
~~~

Guidelines to align on:

- Error codes are stable strings that do not change with Java class names.
- Category or ErrorType reflects the general error group.
- Message does not contain internal data and can be localized.
- Request/correlation ID is only exposed if it is a safe identifier for the client to provide to support.
- Do not return sensitive data in extensions.

The client can handle errors by code:

~~~typescript
switch (error.extensions?.code) {
  case "BOOK_NOT_FOUND":
    showBookUnavailable();
    break;
  case "BOOK_UPDATE_FORBIDDEN":
    showPermissionMessage();
    break;
  default:
    showGenericError();
}
~~~

This is a client-side example. Applications should have a default branch to handle new error codes that the client does not yet recognize.

## Testing GraphQLError with GraphQlTester

GraphQlTester allows asserting errors in the response alongside data. For example:

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
    assertThat(errors.get(0).getMessage())
            .isEqualTo("Book not found");
});
~~~

For an API with an error contract, also verify:

1. extensions.code equals BOOK_NOT_FOUND.
2. Appropriate classification, for example NOT_FOUND.
3. path points to the correct response field.
4. locations points to the field position in the operation when determinable.
5. Nullable fields have a null value as expected.
6. Other independent fields still return partial data when appropriate.
7. Unexpected exceptions do not leak stack traces or internal information.

In addition to testing resolvers, test syntax, validation, and input coercion errors to confirm the client receives appropriate errors even when the resolver has not run.

## Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Client has to compare message strings to handle errors | No stable error code in extensions | Add extensions.code and document it |
| Error has no path | Error occurred before execution or builder did not receive environment | Distinguish request errors from execution errors; use builder with DataFetchingEnvironment when appropriate |
| No partial data returned | Failing field causes null to propagate through non-null fields | Check nullability and error path |
| Class names or SQL leaked in response | Returning exception message directly | Map to a safe message and log details on the server |
| Business exception becomes an internal error | No matching DataFetcherExceptionResolver | Register resolver and test mapping |
| Multiple resolvers handle the same exception | Overlapping exception resolvers | Clarify responsibilities and execution order |
| Client does not recognize category | Inconsistent error codes used | Standardize ErrorType and extensions.code |
| Using null to represent all errors | Mixing missing-data outcomes with execution errors | Return null only when semantically valid; system errors must be clearly reported |

## Comprehensive practice

Build an error contract for the library API:

1. Create BookNotFoundException for the case where a book is not found.
2. Create BookUpdateForbiddenException for the case where the user does not have permission to update.
3. Use DataFetcherExceptionResolverAdapter to map both exceptions to GraphQLError.
4. Assign appropriate ErrorType values and extensions.code as BOOK_NOT_FOUND and BOOK_UPDATE_FORBIDDEN respectively.
5. Use GraphqlErrorBuilder.newError(environment) to preserve locations and path.
6. Do not return internal exception messages to the client.
7. Write GraphQlTester tests checking message, path, classification, extensions, and partial data.
8. Trigger an unhandled exception from a resolver to test fallback error handling.

After completing, explain the difference between request errors and execution errors, why extensions.code is more stable than message, and when to return DataFetcherResult.

## Key takeaways

GraphQLError represents a structured error in a GraphQL response. Key information includes message, locations, path, extensions, and error classification. GraphqlErrorBuilder helps construct errors; use the builder with DataFetchingEnvironment to attach the path and field location when an error occurs during execution. In Spring for GraphQL, DataFetcherExceptionResolver maps exceptions to errors under a centralized contract. Request errors occur before resolvers run, while execution errors can accompany partial data and are affected by null propagation. Provide stable extensions.code values, avoid exposing internal details, and test both errors and data using GraphQlTester.
