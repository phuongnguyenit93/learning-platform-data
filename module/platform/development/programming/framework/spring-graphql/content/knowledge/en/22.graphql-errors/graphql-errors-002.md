# errors in GraphQL responses

A GraphQL response can contain both data and errors in the same result. Therefore, clients should not assume that having errors means all data failed, or that having `data` means the operation encountered no errors. GraphQL distinguishes errors that occur before operation execution from errors that arise during field resolution; these two categories have different response structures and handling strategies.

In Spring for GraphQL, errors from resolvers can be mapped to `GraphQLError` using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. The GraphQL engine is responsible for placing errors into the response, along with location and path information when available. Good error design helps clients know which field failed, what data is still usable, and how to display or handle the situation without exposing internal server details.

After this lesson, you will be able to:

- Read the `data` and `errors` structure of a GraphQL response.
- Distinguish request errors from execution errors.
- Understand `message`, `locations`, `path`, and `extensions`.
- Explain partial data and null propagation rules.
- Map exceptions in Spring for GraphQL to GraphQL errors.
- Distinguish GraphQL errors from business errors represented in the payload.
- Design stable error codes without exposing sensitive information.
- Test error responses using `GraphQlTester`.

## 1. GraphQL response structure

A simple successful response might look like this:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice"
    }
  }
}
```

If there are no errors, the response typically contains only `data`; there is no need to return an empty `errors` array.

When errors occur, the response can contain `data` and `errors` at the same time:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "Spring GraphQL in Practice",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "locations": [
        { "line": 7, "column": 7 }
      ],
      "path": ["book", "author"],
      "extensions": {
        "code": "UPSTREAM_UNAVAILABLE"
      }
    }
  ]
}
```

In this example, `book.id` and `book.title` still have data. Only the `author` field failed and became null because this field is declared nullable. The client can continue displaying book information while informing the user that author data is temporarily unavailable.

A response can contain multiple errors if multiple independent fields encounter issues. Each element in `errors` describes a separate error; clients should inspect each error rather than only checking whether `errors` exists.

## 2. Request errors and execution errors

GraphQL distinguishes two stages where errors occur.

A **request error** occurs before operation execution. For example:

- The GraphQL document has invalid syntax and cannot be parsed.
- The query requests a non-existent field or passes an argument of the wrong type.
- The operation is invalid against the schema.
- A required variable is missing or cannot be coerced to the declared type.
- The document contains multiple operations, but the request does not specify which operation to run.

When a request error occurs, GraphQL does not execute resolvers. The response contains `errors` and has no `data` entry:

```json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'. Did you mean 'title'?",
      "locations": [
        { "line": 4, "column": 7 }
      ]
    }
  ]
}
```

An **execution error** occurs after the operation has passed validation checks and GraphQL begins resolving fields. For example, a resolver cannot find a resource, an external service times out, or the user lacks permission to read a field. In that case, the response has a `data` entry; the failing field is handled according to nullability, and the error is added to `errors`.

| Error type | Timing | Did the resolver run? | Typical response |
| --- | --- | --- | --- |
| Parse error | Parsing document | No | `errors`, no `data` |
| Validation error | Validating document against schema | No | `errors`, no `data` |
| Variable coercion error | Preparing variables | No | `errors`, no `data` |
| Execution error | Resolving a field | May have partially run | `data` together with `errors` |

This distinction is useful when diagnosing issues: request errors usually require fixing the query, schema, or variables; execution errors usually require checking data, permissions, resolvers, or downstream systems.

## 3. Components of a GraphQL error

An element in `errors` can contain the following fields:

| Field | Meaning |
| --- | --- |
| `message` | Brief description of the error |
| `locations` | Positions in the GraphQL document related to the error, consisting of line and column |
| `path` | Path to the response field where the error occurred |
| `extensions` | Metadata provided by the implementation or application |

Not every error has all fields. For example, a parse error may have `locations` but no `path` because no field has been executed yet. An error created outside the GraphQL layer may also lack document locations.

### `message`

`message` is a string describing the error for humans or tools to read. Write short, stable messages and avoid exposing SQL, internal table names, stack traces, secrets, tokens, or other users' information.

### `locations`

`locations` is an array of positions in the GraphQL document, each with 1-based `line` and `column`. When a client uses multi-line queries or fragments, locations help pinpoint the relevant field or syntax segment.

### `path`

`path` indicates the path to the field in the response. Elements can be field names or list item indices. `path` uses the response key; if a field is aliased, path uses that alias.

For example:

```graphql
query {
    library: books {
        title
        writer: author {
            name
        }
    }
}
```

If `author` of the second item fails, the path might be:

```json
["library", 1, "writer"]
```

Clients can use path to highlight the exact failing element without guessing from the message.

### `extensions`

`extensions` is where the application can include metadata such as an error code, correlation ID, or publicly permitted classification info:

```json
{
  "message": "Book not found",
  "path": ["book"],
  "extensions": {
    "code": "BOOK_NOT_FOUND"
  }
}
```

`extensions` is not a fixed schema defined by GraphQL. Design a documented custom structure, use stable error codes, and include only metadata needed by the client. Do not put tokens, full principals, SQL queries, stack traces, or internal exception details here.

## 4. `data: null` vs. no `data`

The following two responses represent two different situations.

Request error, not yet executed:

```json
{
  "errors": [
    { "message": "Invalid query document" }
  ]
}
```

Execution error propagated to the root:

```json
{
  "data": null,
  "errors": [
    {
      "message": "Required field could not be resolved",
      "path": ["book", "author", "name"]
    }
  ]
}
```

In the first response, `data` does not appear because the operation was never executed. In the second response, `data` appears with a null value because the operation ran, but an error in a non-null field propagated all the way to the root. Clients should not collapse these two states into the same outcome.

## 5. Partial data: part of the data remains valid

GraphQL can return data for fields that succeeded even if another field failed. This is very useful for queries fetching multiple independent data regions:

```graphql
query Dashboard {
    profile {
        displayName
    }
    recommendations {
        id
        title
    }
    notifications {
        id
        message
    }
}
```

If the recommendations service fails while profile and notifications succeed, the response might look like this:

This example assumes the `recommendations` field is declared nullable in the schema, so the error can be represented by a null value at that field.

```json
{
  "data": {
    "profile": {
      "displayName": "An"
    },
    "recommendations": null,
    "notifications": [
      { "id": "n-1", "message": "Welcome back" }
    ]
  },
  "errors": [
    {
      "message": "Recommendations are temporarily unavailable",
      "path": ["recommendations"],
      "extensions": {
        "code": "RECOMMENDATIONS_UNAVAILABLE"
      }
    }
  ]
}
```

Clients should inspect both `data` and `errors`. If a client simply checks `errors.length > 0` and discards all `data`, the application loses fields that can still be displayed. Conversely, if it only reads `data` and ignores `errors`, the client might silently treat a null field caused by an error as normal empty data.

## 6. Null propagation and non-null fields

Nullability in SDL determines how an error in a field propagates up the response.

Suppose:

```graphql
type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

`Book.author` is nullable. If the `author` resolver fails, GraphQL can set `author` to null and preserve the other fields of book:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": "GraphQL Essentials",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author lookup failed",
      "path": ["book", "author"]
    }
  ]
}
```

If the schema changes to `author: Author!`, the field is not allowed to be null. When the resolver fails, GraphQL bubbles null up to the parent `Book`. If `Query.book` is also declared `Book!`, null continues propagating to the root and `data` can become null.

General rules:

1. Nullable field encounters an execution error: the field value becomes null; sibling fields can still retain their data.
2. Non-null field encounters an error or returns null: the error propagates up to the parent.
3. If the parent is nullable, propagation stops at that parent and the parent becomes null.
4. If the entire chain of parents is non-null, the error can propagate to the root, making `data` null.

`path` still points to the original field where the error occurred, even if the resulting null appears at an ancestor. Therefore, clients can use path to pinpoint the cause rather than just looking at where null appears in data.

## 7. Exceptions in resolvers become GraphQL errors

In Spring for GraphQL, an exception raised while a DataFetcher/resolver runs can be handled by the `DataFetcherExceptionResolver` chain. This mechanism allows mapping application exceptions to one or more `GraphQLError` instances.

For annotated controllers, a common approach is using `@GraphQlExceptionHandler` in a controller or in `@ControllerAdvice` to handle exceptions with broader scope.

Example domain exception:

```java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String bookId) {
        super("Book not found: " + bookId);
    }
}
```

Service throwing an exception in domain terms:

```java
@Service
public class BookService {

    public BookView findById(String id) {
        return bookRepository.findViewById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
```

Exception handler converting the exception into an appropriate public error:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
```

In this example, the client receives a stable message and code without receiving the internal ID from the exception or query details. Spring for GraphQL combines the resolver result with execution information to place the error into the response.

`@GraphQlExceptionHandler` is suited for errors arising during GraphQL resolution. Parse, validation, or variable coercion errors occur before resolvers run and are therefore not handled as DataFetcher exceptions; the GraphQL engine creates the corresponding request errors.

## 8. Choosing DataFetcherExceptionResolver or @GraphQlExceptionHandler

These two mechanisms differ in scope and organization:

| Mechanism | When it fits |
| --- | --- |
| `@GraphQlExceptionHandler` in a controller | Errors tied to a specific controller or resolver group |
| `@GraphQlExceptionHandler` in `@ControllerAdvice` | Exception handling rules shared across multiple controllers |
| `DataFetcherExceptionResolver` | Need a centralized resolver, handling by exception type, or integrating custom error mapping logic |

`DataFetcherExceptionResolver` is Spring for GraphQL's extension point for handling exceptions from DataFetchers. The resolver receives the exception along with `DataFetchingEnvironment` and returns GraphQL error results according to the framework API. When you need a unified policy across modules or complex exception classification, this is an appropriate choice.

There is no need to implement all three mechanisms for the same exception if one simple handler satisfies the requirement. Avoid having multiple places handle the same exception in different ways, which leads to inconsistent messages, error codes, and logging.

## 9. Classifying errors and stable error codes

Clients usually need a machine-readable error code rather than parsing `message` content. You can standardize codes by category:

| Example error code | Meaning | Typical client action |
| --- | --- | --- |
| `BAD_INPUT` | Input is invalid according to application rules | Display input validation error |
| `BOOK_NOT_FOUND` | Resource does not exist or is not allowed to be shown | Display not-found state |
| `FORBIDDEN` | User is authenticated but lacks permission | Hide/disable action and show appropriate message |
| `UNAUTHENTICATED` | No valid authenticated identity | Prompt for login or refresh session |
| `UPSTREAM_UNAVAILABLE` | Dependent system is temporarily unavailable | Allow retry according to policy |
| `INTERNAL_ERROR` | Unexpected server error | Display generic message and log for support |

These names are conventions chosen by the application, not a mandatory GraphQL enum. Maintain a clear catalog of codes, descriptions, and retryability. Do not change a code just because the `message` wording is edited or translated into another language.

Spring for GraphQL provides `ErrorType` to classify common error groups such as `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, and `INTERNAL_ERROR`. You can use `errorType(...)` to attach the classification while also adding a business code in `extensions` if clients need to distinguish multiple errors within the same group.

## 10. Do not turn every error into INTERNAL_ERROR or null

Both extremes make the API hard to use:

- Returning every error as `INTERNAL_ERROR`: clients cannot distinguish a missing resource, invalid input, or missing permission.
- Catching exceptions and returning null: errors are turned into absent data, `errors` no longer reflects the cause, and clients cannot handle it properly.

Classify errors according to their semantics:

- Resource does not exist: `NOT_FOUND` or corresponding business code.
- User is logged in but lacks permission: `FORBIDDEN`.
- Unauthenticated: `UNAUTHORIZED` or request rejected by the security layer before GraphQL.
- Input violates application contract: appropriate `BAD_REQUEST`/validation error.
- Unexpected error: `INTERNAL_ERROR` with a generic public message.

If a non-existent resource and an unauthorized resource must be disguised identically, the service can intentionally return the same public error to prevent resource enumeration. This is a security decision that must be applied consistently.

## 11. GraphQL errors vs. business errors in the payload

Not every unsuccessful business outcome needs to be an execution error. For example, an order creation mutation might be rejected because the cart is unpaid or a discount code is no longer valid. The API can represent this as a normal business result in the payload:

```graphql
type UserError {
    code: String!
    message: String!
    field: String
}

type CreateOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type Mutation {
    createOrder(input: CreateOrderInput!): CreateOrderPayload!
}
```

The response can succeed at the GraphQL level while the payload contains business errors:

```json
{
  "data": {
    "createOrder": {
      "order": null,
      "userErrors": [
        {
          "code": "COUPON_EXPIRED",
          "message": "The coupon has expired",
          "field": "couponCode"
        }
      ]
    }
  }
}
```

Use payload errors when the client needs to handle expected errors as part of a business workflow and wants a typed structure. Use GraphQL `errors` for field execution failures, system errors, authorization failures, or errors that prevent the operation from completing under the contract.

A validation error can be represented via payload or GraphQL error depending on the API design. What matters is choosing consistent semantics, documenting them, and not returning the same error in two arbitrary ways.

## 12. Securing messages, extensions, and logs

GraphQL errors are data sent to the client. Do not include the following information in `message` or `extensions`:

- Stack traces or unnecessary internal class names.
- SQL, table names, query statements, or database structure.
- Passwords, access tokens, refresh tokens, or credentials.
- Full principals, internal permission lists, or sensitive claims.
- Data belonging to other resources or tenant details the caller is not permitted to see.
- Third-party library exception contents if they could reveal system configuration.

Instead, send concise messages and stable codes. Server-side logs can record the original exception, stack trace, and correlation ID for investigation. Do not log tokens or sensitive data just for debugging.

If using a correlation ID, ensure the ID is generated or verified at a trusted server/gateway. You can include that ID in `extensions` so clients can attach it when reporting issues, but do not use it as proof of authentication or access rights.

## 13. Errors from Spring Security and authorization

An `AccessDeniedException` raised in a resolver/service can be mapped to a `FORBIDDEN` GraphQL error:

```java
@ControllerAdvice
public class SecurityGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(AccessDeniedException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.FORBIDDEN)
                .message("You are not allowed to access this resource")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
```

If a request is rejected in the Spring Security filter chain before reaching the GraphQL handler, the response may be an HTTP 401/403 from the transport/security layer rather than a GraphQL response with `errors`. If authorization is checked during field resolution, the error can appear in the `errors` array and follow null propagation.

Distinguishing these two stages helps clients handle errors properly: an HTTP authentication error may require signing in again; a field-level authorization error may only make part of the data inaccessible.

## 14. Errors in lists and nested fields

`path` can contain list indices to indicate the specific element that failed. For example:

```graphql
query {
    books {
        id
        author {
            name
        }
    }
}
```

If the author of the third element fails to load, the path might be:

```json
["books", 2, "author"]
```

If the list field or items are non-null, the error can propagate further according to nullability:

```graphql
type Query {
    books: [Book!]!
}
```

With `[Book!]!`, neither the list nor each item may be null. If a `Book` element becomes null due to an error in a nested non-null field, null can propagate across the item, list, and root depending on parent types. If you want other elements to be preserved when one item fails, design the nullability of the list/items and child fields appropriately.

Do not use `path` to infer an index in another list after the client has re-sorted or filtered data in the UI. Path describes the position in the specific GraphQL response of that operation.

## 15. How should clients handle responses?

Clients need to read `data` and `errors` independently:

1. If there are no `errors`, display data according to `data`.
2. If there are `errors` and `data` still contains an object, keep the valid fields and mark the failed part according to `path`.
3. If there is no `data`, handle a pre-execution request error; check the document, schema, or variables.
4. If `data` is null, the operation may have run, but a non-null error propagated to the root; display an appropriate error state.
5. Use `extensions.code` to select a machine-readable action; do not parse `message` to drive logic.
6. Retry only on retryable errors and according to policy; do not automatically retry validation, forbidden, or bad input errors.

Do not rely solely on the HTTP status code to conclude whether a GraphQL operation succeeded or failed. How transport maps errors to HTTP status depends on the error type, server, and GraphQL over HTTP integration. For a valid GraphQL response, the client needs to read the response structure and the `errors` array.

## 16. Testing errors with GraphQlTester

`GraphQlTester` lets you assert both data and errors. For example, a `book` resolver throws `BookNotFoundException` and the exception handler maps it to `BOOK_NOT_FOUND`:

```java
graphQlTester.document("""
        query {
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
        assertThat(errors.get(0).getMessage()).isEqualTo("Book not found");
    });
```

For partial data, verify that other fields still have data and the failing field has a null value:

```java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

Then verify the corresponding error via `.errors()` and the field path according to the response. Depending on the `GraphQlTester` version, you can use `errors().satisfy(...)` or the path assertion API to confirm null data.

Tests should cover:

1. Request parse/validation errors do not invoke resolvers and have no `data`.
2. Variable coercion errors are returned before execution.
3. Exceptions on nullable fields produce partial data and the correct error path.
4. Exceptions on non-null fields cause null propagation matching the schema.
5. Aliases and list indices are accurately reflected in `path`.
6. `extensions.code` is stable per error type.
7. Authorization errors do not expose sensitive information.
8. Expected errors in mutation payloads are not confused with execution errors.
9. System errors are logged on the server while client-facing messages remain safe.

## 17. Common pitfalls

- **Assuming every response with errors has no data:** execution errors can return partial data.
- **Confusing request errors with execution errors:** request errors occur before resolvers run and have no `data` entry.
- **Reading only message:** clients should use `path` and `extensions.code` for structured handling.
- **Ignoring null propagation:** non-null fields can cause null to bubble up multiple levels.
- **Returning null instead of throwing an exception:** clients receive no error information in `errors`.
- **Putting stack traces in extensions:** exposes internal structure and data.
- **Mapping all exceptions to the same code:** clients cannot distinguish business errors, permissions, and system errors.
- **Using message as an error code:** messages may change or be translated; codes must remain stable.
- **Using GraphQL errors for all business outcomes:** some expected errors fit typed payloads better.
- **Checking only HTTP status:** a GraphQL response can contain partial data and errors simultaneously.
- **Forgetting to check aliases/list indices in path:** client highlights the wrong failing element.
- **Treating HTTP security layer errors as resolver errors:** errors before GraphQL execution may not have a GraphQL response body with the same structure.

## 18. Workflow for designing and handling GraphQL errors

When implementing a field or mutation that can produce errors, follow these steps:

1. Determine whether the error occurs before execution or during field resolution.
2. Choose field nullability based on failure likelihood and how much partial data should be preserved.
3. Define meaningful business exceptions in the service/domain layer.
4. Use `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` to map exceptions.
5. Choose an appropriate `ErrorType` and a stable error code in `extensions`.
6. Write safe messages without stack traces or sensitive information.
7. Decide whether expected errors belong in GraphQL `errors` or a typed business payload.
8. Log the original exception on the server with an appropriate correlation ID.
9. Test `data`, `errors`, `locations`, `path`, `extensions`, and null propagation.
10. Guide clients on handling partial data, retries, and error codes.

GraphQL errors are part of the response contract, not merely debug messages. Request errors prevent an operation from starting; execution errors may affect only a single field while preserving partial data. By understanding `locations`, `path`, `extensions`, and null propagation, and mapping exceptions with the appropriate Spring for GraphQL mechanisms, the server can provide clear, safe, and useful errors to clients.

## References

- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring for GraphQL — DataFetcherExceptionResolver](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolver.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
