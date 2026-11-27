# Error classification in GraphQL and Spring for GraphQL

GraphQL has several kinds of errors that occur at different stages of an operation. A request may have invalid syntax and never execute; a field resolver may throw an exception while other fields still return data; or a mutation may succeed at the GraphQL level yet fail a business rule, such as an email already being in use.

Error classification helps the server choose the right response and helps clients know what to do next. In Spring for GraphQL, distinguish between request errors, execution errors, and business errors; then use GraphQL error classification, exception resolvers, or typed payloads to represent each case.

## 1. Three common error groups

From an API design perspective, scenarios can be divided into three groups:

| Group | Timing | Does the resolver run? | Common representation |
|---|---|---|---|
| Request error | Parsing, validation, operation selection, or variable coercion fails | No | Top-level `errors`; request is not executed. |
| Execution error | Field resolver or value completion encounters an error | May have partially run | `data` with `errors`; failing field typically becomes `null`, partial data possible. |
| Business error | Business rule rejects a GraphQL-valid action | Yes | Payload inside `data`, such as `userErrors` or a dedicated result type. |

This is a useful classification when designing an API. The GraphQL specification defines request errors and execution errors; business errors are an application convention, often represented in the schema so clients can handle them as business outcomes.

For example:

- `query { unknownField }`: request error because the field does not exist in the schema.
- Resolver calls database and connection fails: execution error.
- `createUser` receives properly typed data but the email is already registered: business error can be returned in the payload.

## 2. Request errors: errors before execution

Request errors occur before GraphQL starts executing fields. Common cases:

**Syntax/parse error:** the document is not valid GraphQL syntax, such as a missing brace or quote.

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    # missing closing brace
```

**Validation error:** the document parses, but is invalid against the schema, such as querying a non-existent field or selecting subfields on a scalar.

```graphql
query {
    bookById(id: "book-01") {
        unknownProperty
    }
}
```

**Variable coercion error:** a variable does not match the declared type, a Non-null variable is missing, or a value cannot be coerced to the GraphQL type.

```graphql
query FindBook($id: ID!) {
    bookById(id: $id) {
        id
    }
}
```

If the client does not supply `$id`, the request fails the coercion step because the variable is declared Non-null.

**Operation selection error:** the document contains multiple operations, but the client does not specify which operation name to run, or the specified name does not exist.

For these errors, GraphQL does not invoke `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping`. Following the request-error response format, the response contains an `errors` list and no `data` entry because execution never started. The client must fix the document, variables, or operation name. Because resolvers have not run, `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler` are not the place to handle these parse/validation errors.

## 3. Execution errors: errors during execution

Execution errors occur after GraphQL accepts the document and begins resolving fields. Possible causes include:

- A data fetcher or controller throws an exception.
- A database, HTTP service, or dependent system encounters a failure.
- A custom scalar cannot serialize the returned value.
- A resolver returns `null` for a field declared Non-null.
- A returned value does not match the GraphQL type during value completion.
- A child field raises an error while other fields resolve successfully.

Example query:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            name
        }
    }
}
```

Suppose `Book.id` and `Book.title` resolve successfully, but the `Book.author` resolver throws an exception. If `author` is nullable, the response may contain:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "GraphQL Basics",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["bookById", "author"]
    }
  ]
}
```

The client still receives data for the fields that succeeded. Therefore, do not treat the presence of `errors` as meaning the entire operation has no data.

## 4. Reading GraphQL error structure

An element in the `errors` list can have the following properties:

| Property | Meaning |
|---|---|
| `message` | Description of the error for the client or developer to understand the situation. |
| `locations` | Position in the GraphQL document, consisting of line and column, if determinable. |
| `path` | Path to the field in the response that caused the execution error. |
| `extensions` | Additional metadata such as error code, error category, or tracing information. |

Example response:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        { "line": 2, "column": 5 }
      ],
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
```

`locations` points to the position in the document sent by the client, not line numbers in an SDL file or Java source file. `path` uses response keys; if the query sets an alias, `path` contains that alias. For lists, `path` also includes element indices.

Example query with aliases and a list:

```graphql
query {
    featured: books {
        title
        author {
            name
        }
    }
}
```

If the author of the second item fails, the path might look like `["featured", 1, "author"]`. Clients can use `path` to pinpoint which exact part of the response failed.

Request errors usually do not have `path`, because no field has executed yet. `locations` may still be present if the parser or validator can locate the error position in the document.

## 5. `data` and `errors`: partial data and null propagation

A GraphQL response follows an important rule: an error on one field does not necessarily discard all `data`. When a field resolver fails, that field usually receives `null` and the error is added to the `errors` list.

However, nullability in SDL determines how far the error propagates.

```graphql
type Book {
    id: ID!
    author: Author
}
```

If `author` fails, `author` becomes `null`, while `Book` can still be returned.

If the schema changes to:

```graphql
type Book {
    id: ID!
    author: Author!
}
```

then `author` is not allowed to be `null`. An error on this field propagates up to its parent `Book`; if the parent field `bookById` is nullable, the entire `bookById` becomes `null`. If subsequent parents are also Non-null, the error keeps bubbling up to the nearest nullable boundary. If every parent along the path to the root is Non-null, `data` can become `null`.

When designing the schema, decide clearly which fields genuinely always have data. Do not use `!` merely to express wishful thinking; Non-null is a commitment that resolvers must uphold in every valid scenario.

## 6. Error classification in Spring for GraphQL

Spring for GraphQL provides `ErrorType`, an enum implementing `ErrorClassification`, to classify common errors when the server constructs a `GraphQLError`:

| `ErrorType` | Common meaning |
|---|---|
| `BAD_REQUEST` | Request or input data was rejected at the application processing layer. |
| `UNAUTHORIZED` | Request is unauthenticated or credentials are invalid. |
| `FORBIDDEN` | User is authenticated but lacks permission to perform the action. |
| `NOT_FOUND` | Requested resource does not exist. |
| `INTERNAL_ERROR` | Internal error not belonging to a more specific group. |

These values help standardize error categories created by the application. They do not replace application-specific business error codes, nor are they the only classification list used by GraphQL Java for parse/validation. Pre-execution errors can carry GraphQL Java's own classifications; Spring's `ErrorType` is typically used when the application explicitly constructs a `GraphQLError`, such as inside an exception resolver. Several distinct errors may share `BAD_REQUEST`, yet clients still need to distinguish `DUPLICATE_EMAIL`, `INVALID_STATE`, or `INVALID_COUPON`.

You can create a GraphQL error with `GraphqlErrorBuilder`:

```java
GraphQLError error = GraphqlErrorBuilder.newError(environment)
    .errorType(ErrorType.NOT_FOUND)
    .message("Book not found")
    .extensions(Map.of("code", "BOOK_NOT_FOUND"))
    .build();
```

In this example, `ErrorType.NOT_FOUND` classifies the error at a general level; `extensions.code` is a stable application-defined code. Clients should rely on documented codes for handling rather than parsing `message` content.

## 7. Mapping exceptions to GraphQL errors

For exceptions thrown by resolvers, Spring for GraphQL provides two common approaches:

- `@GraphQlExceptionHandler` inside a controller or `@ControllerAdvice`.
- `DataFetcherExceptionResolver` or the convenience class `DataFetcherExceptionResolverAdapter` for centralized handling.

Example business exception:

```java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(String id) {
        super("Book not found: " + id);
    }
}
```

Centralized handler:

```java
@ControllerAdvice
class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

`DataFetchingEnvironment` lets the error builder attach information related to execution position and response path. This approach fits exceptions thrown by data fetchers.

Do not use an exception handler to turn every error into the same `INTERNAL_ERROR` code. Distinguish predictable errors from unexpected ones; expose only safe information to clients while logging stack traces and system details on the server.

## 8. Request errors and execution errors need handling at different layers

Not every GraphQL error passes through an exception resolver:

| Stage | Example | Appropriate handling mechanism |
|---|---|---|
| Parse | Document has syntax error | GraphQL parser; client fixes document. |
| Validation | Non-existent field, invalid selection set | GraphQL validator; client fixes query against schema. |
| Variable coercion | Missing Non-null variable or wrong type | GraphQL input coercion; client fixes variables. |
| Data fetching | Resolver throws exception | `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`. |
| Value completion | Scalar serialization error, Non-null receives `null` | GraphQL execution; check return types and nullability. |
| Business validation | Duplicate email, disallowed state | Payload with `userErrors` or business result type. |

Request errors occur before any data fetcher is invoked. Thus, if a client sends a field not in the schema, there is no `@QueryMapping` to catch that error. Likewise, if variables cannot be coerced, the mutation resolver never runs.

When you need to observe request errors at the transport level, you can use `WebGraphQlInterceptor` to inspect errors in the response after GraphQL processes the request. This is an observation point for the response, not a replacement for the parser or validator.

## 9. Business errors: domain errors inside `data`

A business error is an expected business outcome, not necessarily a GraphQL execution failure. For example, creating an account with an email that already exists: the document and variables are valid, the server executes the mutation properly, yet business rules reject the operation.

You can define a payload:

```graphql
input RegisterUserInput {
    email: String!
    name: String!
}

type User {
    id: ID!
    email: String!
    name: String!
}

type Mutation {
    registerUser(input: RegisterUserInput!): RegisterUserPayload!
}

type RegisterUserPayload {
    user: User
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

Java can represent the payload using records:

```java
public record UserError(String code, String message, List<String> field) {}

public record RegisterUserPayload(User user, List<UserError> userErrors) {}
```

Resolver returning the payload:

```java
@MutationMapping
RegisterUserPayload registerUser(@Argument("input") RegisterUserInput input) {
    if (userService.emailExists(input.email())) {
        return new RegisterUserPayload(
            null,
            List.of(new UserError(
                "DUPLICATE_EMAIL",
                "Email is already in use",
                List.of("input", "email")
            ))
        );
    }

    User user = userService.register(input);
    return new RegisterUserPayload(user, List.of());
}
```

When the email is duplicated, the response still contains `data.registerUser.userErrors`; top-level `errors` is unnecessary if this is an expected result under the API contract.

Clients can display the message next to the corresponding field, allowing the user to fix it and resubmit. If top-level execution errors are used for every business validation, clients will struggle to separate recoverable errors from system failures.

There is no mandatory rule that every business error must live in the payload. What matters is choosing a consistent contract: expected business states should usually have clear result types; exceptions or unexpected failures belong in top-level `errors`.

## 10. Authentication and authorization errors

Authentication and authorization errors can appear at multiple layers:

- If the Spring Security filter chain rejects the HTTP request before the GraphQL handler, clients typically receive HTTP `401` or `403` per the configured security entry point/access denied handler; a GraphQL response is not necessarily returned.
- If the request reaches GraphQL and a resolver/service denies access, the exception can be mapped to a GraphQL error with `UNAUTHORIZED` or `FORBIDDEN`.
- If the API models access control as a handleable business result, the payload may carry its own error code, but it must never expose resources the user is not authorized to know about.

Example mapping access denied:

```java
@GraphQlExceptionHandler
GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.FORBIDDEN)
        .message("You are not allowed to access this resource")
        .extensions(Map.of("code", "ACCESS_DENIED"))
        .build();
}
```

Authentication and authorization must be enforced at the proper layers. Do not rely on `extensions.code` as a substitute for verifying credentials or enforcing real access controls.

## 11. GraphQL errors are not synonymous with HTTP status

GraphQL typically uses a single endpoint for many operations. Therefore, HTTP status is not the sole way for clients to tell which fields succeeded or failed.

For example:

- A request blocked by Spring Security before GraphQL can return HTTP `401` or `403`.
- A GraphQL operation that executed while a resolver threw an exception can still return an HTTP response containing `data` and `errors`.
- Business errors in payloads can be returned in `data` without top-level `errors`.
- Pre-execution request errors have a status depending on transport, media type, and GraphQL over HTTP implementation rules; do not assume all errors share the same status.

For HTTP GraphQL, read the response body according to the GraphQL contract and inspect `data`/`errors`. For WebSocket, GraphQL operation errors are sent in protocol payloads; protocol or connection errors belong to a separate layer.

Do not use HTTP `200` to conclude every field succeeded, nor assume HTTP `4xx` always contains GraphQL `errors`. Clients need to handle both the transport layer and the GraphQL layer.

## 12. Designing stable error codes

`message` is for humans and may change or be translated. Clients should rely on stable error codes in `extensions.code` or payload `userErrors.code`.

A code set might be designed like this:

| Code | Category | Client action |
|---|---|---|
| `BOOK_NOT_FOUND` | Resource | Display not-found message or redirect. |
| `DUPLICATE_EMAIL` | Business validation | Highlight the email field and ask for another address. |
| `ACCESS_DENIED` | Authorization | Display insufficient permissions message. |
| `INVALID_STATE` | Business rule | Prompt user to perform the next valid step. |
| `INTERNAL_ERROR` | Unexpected failure | Display generic message and support reference if available. |

Document the following:

1. The error code and its meaning.
2. Whether the error appears in top-level `errors` or in the payload.
3. Whether `path`, `locations`, or field path is included.
4. Whether the client can retry or the user must correct data.
5. What information is allowed to appear in `message` and `extensions`.

Do not use messages as error codes, do not change codes arbitrarily between versions, and do not put stack traces, SQL, tokens, internal emails, or sensitive data into responses.

## 13. Testing each error category with `GraphQlTester`

`GraphQlTester` lets you verify both GraphQL data and the errors list. For execution errors, you can check the error code and field path:

```java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            bookById(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getPath())
        .containsExactly("bookById");
    assertThat(errors.get(0).getExtensions())
        .containsEntry("code", "BOOK_NOT_FOUND");
});

response.path("bookById").valueIsNull();
```

Illustrative example; `graphQlTester`, controller, exception advice, and SDL must be configured in the test context. If a field has an alias or nested path, assert the exact response path.

For request errors, send an invalid document or invalid variables and confirm the resolver is not invoked. Depending on test setup, you can inspect `errors()` without accessing field data.

For business errors, verify the payload:

```java
graphQlTester.document("""
        mutation {
            registerUser(input: {
                email: "existing@example.com"
                name: "An"
            }) {
                user { id }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("registerUser.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("DUPLICATE_EMAIL");
```

Your test matrix should cover:

- Parse error: document has syntax error.
- Validation error: non-existent field or argument.
- Variable coercion error: missing Non-null variable or wrong type.
- Execution error: resolver throws exception and is mapped accurately.
- Partial data: nullable field fails while sibling fields still return data.
- Non-null propagation: verify errors bubble up to the expected nullable boundary.
- Business error: payload contains code and field path, without top-level errors if specified by the contract.
- Security error: verify rejection at the proper layer without leaking data.

## 14. Common pitfalls in classification

**Calling every error `INTERNAL_ERROR`.** Clients cannot tell input errors, missing permissions, non-existent resources, and system failures apart. Classify by root cause.

**Using exceptions for all business validation.** Expected states that users can correct usually fit a `userErrors` payload better.

**Assuming request errors pass through resolvers.** Parsing, validation, and variable coercion happen before data fetching. Fix the document or variables on the client.

**Assuming `errors` means `data` is always null.** Execution errors can turn just one field `null`; other fields still retain data.

**Ignoring null propagation.** A Non-null field receiving `null` can turn its parent `null` and bubble to the root. Check SDL alongside response tests.

**Letting clients parse `message`.** Messages can change or be translated. Use stable error codes in `extensions` or payloads.

**Equating GraphQL errors with HTTP status.** A GraphQL response can contain partial data and errors. Handle both transport status and the GraphQL body.

**Putting internal details in error responses.** Never return stack traces, SQL, tokens, or infrastructure details to clients. Log details server-side and return safe error codes.

## Conclusion

Error classification in GraphQL begins with determining whether an error occurs before execution, during field execution, or as an expected business outcome. Request errors require the client to fix the document or variables; execution errors are represented via top-level `errors` and may accompany partial data; business errors are typically modeled with payloads carrying error codes and field paths. In Spring for GraphQL, use `ErrorType`, `@GraphQlExceptionHandler`, or `DataFetcherExceptionResolver` for resolver exceptions while keeping nullability and error contracts consistent. Test `data`, `errors`, `path`, `extensions`, and transport status so clients can handle errors accurately.

## References

- [GraphQL Specification — Response](https://spec.graphql.org/October2021/#sec-Response)
- [GraphQL Specification — Errors](https://spec.graphql.org/October2021/#sec-Errors)
- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html)
