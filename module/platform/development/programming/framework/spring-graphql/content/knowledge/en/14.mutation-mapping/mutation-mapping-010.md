# Mutation Error Responses in Spring for GraphQL

When a mutation cannot complete, GraphQL can return an error at the execution level or return a business outcome describing the error directly inside `data`. These two approaches serve different scenarios. Execution errors fit exceptions, system failures, or invalid requests; strongly typed business outcomes fit cases users can correct and resubmit, such as duplicate values or inputs failing business rules.

With Spring for GraphQL, mutation resolvers are typically written with `@MutationMapping`. Exceptions from resolvers can be mapped to `GraphQLError` using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. If you want clients to handle business errors as part of a normal result, design a payload in SDL and return it from the resolver.

## 1. How Does GraphQL Represent Errors?

A GraphQL response can contain `data`, `errors`, or both. `errors` is a list of errors raised while processing the operation. Each error may include:

- `message`: error description intended for the client.
- `locations`: locations in the GraphQL document where the error was detected, if applicable.
- `path`: path to the field in the response that caused the execution error.
- `extensions`: additional metadata provided by the server, such as a stable error code.

For example, a client invokes a mutation, but a related resource is not found:

```graphql
mutation {
    publishBook(id: "missing-book") {
        id
        title
    }
}
```

If the resolver throws an exception and an exception handler maps it to a GraphQL error, the response may look like:

```json
{
  "data": {
    "publishBook": null
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["publishBook"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

This is an illustrative structure. Actual `locations`, `path`, and `extensions` contents depend on where the error occurred and how the server constructs the `GraphQLError`.

An execution error does not necessarily wipe out all of `data`. GraphQL can return partially resolved data while setting the failing field to `null`. If that field is Non-null, `null` propagates up to the nearest nullable parent field according to null propagation rules.

## 2. Distinguishing Request Errors, Execution Errors, and Business Errors

Not all errors should be handled the same way:

| Error type | When does it occur? | Did the mutation resolver run? | Typical response approach |
|---|---|---|---|
| Request error | Invalid document syntax, unknown field, wrong argument type, or variable coercion failure | No | GraphQL returns `errors`; the request is not executed. |
| Execution error | Resolver or child field throws an exception, or fails to produce a valid value | Possibly | GraphQL returns `errors`, `path`, and remaining valid `data`. |
| Expected business error | Input fails business rules, such as duplicate ISBN or disallowed state | Yes | Usually returns a payload with `userErrors` or a specific result type in `data`. |

For instance, if SDL declares `createBook(input: CreateBookInput!): Book!` and the client omits `input`, GraphQL rejects the request before calling the `@MutationMapping` method. That is a request error. If the resolver runs and the service hits a database connection failure, that is an execution error. If the ISBN is already taken and the user can supply a different ISBN, that is a business error suited for a payload.

Proper classification helps clients know when to fix the GraphQL document, when to show a system error, and when to simply prompt the user to adjust their input.

## 3. Mutations and Execution Errors from Exceptions

Consider the schema:

```graphql
type Mutation {
    deleteBook(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Resolver:

```java
@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    Book deleteBook(@Argument("id") String id) {
        return bookService.deleteById(id);
    }
}
```

If `deleteById` throws `BookNotFoundException`, Spring for GraphQL must translate that exception into a GraphQL error with appropriate details. Avoid letting default messages or internal exceptions accidentally expose implementation details to clients.

In this example, `deleteBook` is nullable (`Book`), so when the resolver fails, the response can preserve `data.deleteBook: null` alongside `errors`. If changed to `Book!`, an error propagates `null` up to the nearest nullable parent; for a root mutation field, that can make the entire `data` field `null`. If book-not-found is a normal state clients should handle, consider a nullable payload or typed result instead of promising an object always exists.

## 4. Mapping Exceptions with `@GraphQlExceptionHandler`

Spring for GraphQL supports `@GraphQlExceptionHandler` to handle exceptions from GraphQL controllers. Handlers can live in `@ControllerAdvice` for shared handling across controllers, or inside a single controller if scoped only to that controller.

Exception definition example:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Handler converting the exception into a `GraphQLError`:

```java
@ControllerAdvice
class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    GraphQLError handleBookNotFound(
            BookNotFoundException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` attaches execution metadata such as source location and field path to the error. `ErrorType.NOT_FOUND` classifies the error under Spring for GraphQL's categories; `extensions.code` provides a stable code clients can inspect without parsing messages.

Related imports:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.Map;
```

Do not return `ex.getMessage()` directly in every case. Exception messages may contain internal IDs, queries, or system details. Return a safe, client-meaningful message; technical details can be logged server-side with an appropriate correlation ID.

## 5. Centralized Exception Handling with `DataFetcherExceptionResolver`

When you want application-level exception handling or deeper customization, register a `DataFetcherExceptionResolver`. `DataFetcherExceptionResolverAdapter` offers a convenient way to map a single exception to a single `GraphQLError`.

```java
@Component
class BookDataFetcherExceptionResolver extends DataFetcherExceptionResolverAdapter {

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
```

If this resolver does not handle the exception, return `null` so subsequent resolvers can handle it. Multiple resolvers can be ordered by priority.

Choose one clear home for each category of exception. `@GraphQlExceptionHandler` is convenient for controller advice and annotation-based handling; `DataFetcherExceptionResolver` fits centralized handling at the GraphQL layer. Avoid defining multiple handlers that catch the same exception but return inconsistent codes and messages.

## 6. Returning Business Errors in Mutation Payloads

Not every unsuccessful outcome is an execution error. For example, a user submits an ISBN that already exists. The server still processes the request properly, runs business checks successfully, and concludes the record cannot be created. This is an expected business outcome and does not necessarily require top-level `errors`.

A common pattern is returning a payload that always includes a `userErrors` list:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

`userErrors` is always a list, even when the mutation succeeds (returning an empty list). `field` indicates the input path related to the error, such as `['input', 'isbn']`. `book` can be `null` when no record was created.

Java records for the payload:

```java
public record UserError(
    String code,
    String message,
    List<String> field
) {}

public record CreateBookPayload(
    Book book,
    List<UserError> userErrors
) {}
```

The resolver can return the business error as a normal outcome:

```java
@MutationMapping
CreateBookPayload createBook(@Argument("input") CreateBookInput input) {
    if (bookService.isIsbnTaken(input.isbn())) {
        UserError error = new UserError(
            "DUPLICATE_ISBN",
            "ISBN is already in use",
            List.of("input", "isbn")
        );
        return new CreateBookPayload(null, List.of(error));
    }

    Book created = bookService.create(input);
    return new CreateBookPayload(created, List.of());
}
```

In this example, a duplicate ISBN is an expected outcome, so the resolver returns a payload instead of throwing an exception. The client can read `userErrors`, display the message next to the input field, and let the user correct the data.

Successful mutation:

```graphql
mutation {
    createBook(input: {
        title: "GraphQL in Practice"
        isbn: "978-0000000001"
    }) {
        book {
            id
            title
        }
        userErrors {
            code
            message
            field
        }
    }
}
```

When a business error occurs, the response still follows a normal `data` structure:

```json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "code": "DUPLICATE_ISBN",
          "message": "ISBN is already in use",
          "field": ["input", "isbn"]
        }
      ]
    }
  }
}
```

This is not a top-level GraphQL execution error. The client does not need to inspect `errors` to determine which field the user must fix.

## 7. Using Unions to Represent Mutation Outcomes

If each outcome type carries substantially different data, you can use a union instead of a single payload with many nullable fields:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookResult!
}

union CreateBookResult = CreateBookSuccess | CreateBookValidationFailure

type CreateBookSuccess {
    book: Book!
}

type CreateBookValidationFailure {
    errors: [UserError!]!
}
```

Clients use inline fragments to handle each branch:

```graphql
mutation {
    createBook(input: {
        title: "GraphQL in Practice"
        isbn: "978-0000000001"
    }) {
        __typename
        ... on CreateBookSuccess {
            book {
                id
                title
            }
        }
        ... on CreateBookValidationFailure {
            errors {
                code
                message
                field
            }
        }
    }
}
```

Unions make outcome states explicit via concrete types. In return, the server must configure type resolution for the returned Java objects, and clients must handle branches using `__typename` and inline fragments. For simple mutations, payloads with `userErrors` are usually easier to implement; unions shine when success and failure outcomes have markedly different shapes.

## 8. Distinguishing GraphQL Validation Errors from Business Validation

GraphQL validates input types and structure before calling resolvers. For example:

```graphql
input CreateBookInput {
    title: String!
    isbn: String!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

The following cases are request errors:

- Omitting the required `input` argument.
- Missing Non-null fields `title` or `isbn`.
- Passing a value that cannot coerce to the declared GraphQL type.
- Sending a field that does not exist on the input object.

In these cases, GraphQL rejects the request before invoking the resolver. Do not attempt to convert GraphQL schema-type errors into `userErrors` inside the payload, because the mutation method never gets a chance to run.

By contrast, rules such as unique titles, publication dates within allowed ranges, or capping how many books a user may create are business validations. They can be represented in the payload so clients can correct and resubmit.

You can use Bean Validation on Java inputs if Spring Validation is configured. When validation throws an exception, decide clearly whether it represents an input error returned as a GraphQL error or a business error placed in a payload. Keep one consistent policy across mutations so clients do not have to handle the same rule in multiple response formats.

## 9. Transactions and Consistency When Mutations Fail

Mutation root fields execute serially in the order they appear in the operation. However, that does not automatically create a database transaction spanning the entire mutation operation.

If a mutation modifies multiple records atomically, place the transaction boundary in the service:

```java
@Service
class OrderService {

    @Transactional
    Order createOrder(CreateOrderInput input) {
        // Validate business state.
        // Save order and order items in the same transaction.
        // Throw exception if operation must roll back.
        return saveOrderAndItems(input);
    }
}
```

When the service throws an exception, the transaction rolls back according to Spring transaction configuration; the exception is then converted to a GraphQL error or handled per application policy. If the resolver returns `userErrors` as a normal result, the transaction does not automatically roll back just because the payload contains errors. Therefore, validate business preconditions before writing data, or explicitly trigger rollback when needed.

If an operation contains multiple top-level mutation fields and a later field fails, never assume changes committed by an earlier field will roll back automatically. When multiple steps must form an atomic unit, design one composite mutation and execute all work inside a single service transaction.

## 10. Testing Mutation Error Responses

Tests should distinguish execution errors from business errors in payloads.

### Testing execution errors

Example when `BookNotFoundException` is mapped by `@GraphQlExceptionHandler`:

```java
GraphQlTester.Response response = graphQlTester.document("""
        mutation {
            deleteBook(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
        .containsEntry("code", "BOOK_NOT_FOUND");
});
response.path("deleteBook").valueIsNull();
```

This is an illustrative snippet; imports and test context setup are omitted. Assertions verify both the error code in `extensions` and the failing field's value. You can also check `path` to ensure the error is anchored to the right mutation field.

### Testing business errors in payloads

When an ISBN is duplicated, the resolver returns `CreateBookPayload` normally:

```java
graphQlTester.document("""
        mutation {
            createBook(input: {
                title: "GraphQL in Practice"
                isbn: "duplicate-isbn"
            }) {
                book { id }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("createBook.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("DUPLICATE_ISBN");
```

With business errors, the response does not need top-level `errors`; tests should verify `userErrors`, that `book` is `null`, and that the service persisted no new records.

### Recommended test matrix

| Scenario | What to verify |
|---|---|
| Input missing a Non-null field | Request rejected; resolver does not run. |
| Valid input shape violating business rules | `data` includes the payload and expected `userErrors`. |
| Object not found | Clear top-level error with code and path, or typed result if expected. |
| Database/service failure | Client receives a safe error; internal details appear only in logs. |
| User lacks sufficient permissions | No data modified and response matches authorization policy. |
| Failure mid-transaction | Changes inside the transaction roll back as expected. |

## 11. Security and Error Code Design

Clients should rely on stable error codes such as `BOOK_NOT_FOUND`, `DUPLICATE_ISBN`, or `ACCESS_DENIED` rather than comparing message strings. Messages may be translated, reworded, or redacted under security policies.

Key principles:

1. Never return stack traces, SQL, table names, connection info, or sensitive data in `message` or `extensions`.
2. Include in `extensions` only metadata the client genuinely needs to handle the error.
3. Do not reveal whether a resource exists when security policy requires concealment; for instance, return the same message for non-existent resources and resources the caller may not view.
4. Use server-side logs for detailed exception diagnostics with a correlation ID or trace ID for investigation.
5. Standardize error codes and `userErrors` structures across mutations so clients can reuse display and error-handling logic.

Do not use HTTP status codes as the sole indicator of whether a mutation succeeded or failed. GraphQL can return a protocol-valid HTTP response that still contains `errors` at execution time; payload business errors even appear inside `data` with no `errors` at all. Clients must inspect the GraphQL response body according to the API contract.

## 12. Common Pitfalls

**Throwing exceptions for every business error.** This turns user-correctable issues into execution errors. Consider payloads with `userErrors` for expected validation failures.

**Returning business errors as unstructured exception messages.** Clients are forced to parse text and break easily when wording changes. Use stable error codes and field paths.

**Forgetting null propagation.** If a mutation returns a Non-null type yet the resolver returns `null`, GraphQL raises an error and can wipe out parent data. Choose SDL types fitting all outcome states.

**Exposing raw exception messages to clients.** Exceptions can carry sensitive details. Map them to safe messages and log details on the server.

**Assuming errors in a payload automatically roll back transactions.** A payload is a normal return value from a resolver. Manage transactions and rollback conditions explicitly.

**Checking errors only via HTTP status.** Inspect `data`, `errors`, `path`, `extensions`, or `userErrors` according to the error category.

**Letting different mutations return errors in inconsistent shapes.** Standardizing codes and payloads simplifies client handling and reduces screen-specific workarounds.

## Conclusion

Mutation error responses in Spring for GraphQL require distinguishing request errors, execution errors, and expected business errors. Use `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` to convert exceptions into safe `GraphQLError` instances; use payloads with `userErrors` or result unions when clients need to handle business states as part of the response. Combining stable error codes, proper nullability, clear transactions, and `GraphQlTester` coverage yields mutations that behave consistently, clearly, and safely for clients.
