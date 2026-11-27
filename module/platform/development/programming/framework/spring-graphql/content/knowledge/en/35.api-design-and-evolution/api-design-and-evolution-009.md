# Error Contracts

A GraphQL API needs a stable error convention so clients know when a request could not execute, when only a single field failed, and when a business operation was rejected. In Spring for GraphQL, errors can arise at multiple stages: parsing and validation, argument binding, `DataFetcher` execution, service methods, or Subscription publishers. Each error category flows through a different handling mechanism.

An error contract is the part of the public contract describing error shapes, error codes, meanings, retryability, and what data may accompany partial responses. This contract enables clients to handle failures consistently and lets the server change internal implementations without breaking consuming applications.

## Objectives

After this lesson, you can:

- Distinguish request errors, execution errors, and transport-layer errors.
- Interpret `message`, `locations`, `path`, and `extensions` in a GraphQL response.
- Understand partial data and null propagation driven by SDL nullability.
- Design stable `extensions.code` values for an API.
- Distinguish technical errors from predictable business errors.
- Choose between top-level GraphQL errors and errors-as-data in the schema.
- Map exceptions using `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler`.
- Handle binding/validation errors, authentication errors, and authorization errors.
- Understand the boundaries of `DataFetcherExceptionResolver` with respect to request errors and Subscription publisher errors.
- Standardize messages, logging, correlation IDs, and sensitive data handling.
- Test error contracts with `GraphQlTester`.
- Evolve error codes without breaking existing clients.

## 1. What is an error contract?

GraphQL responses do not contain only successful data. A single response can contain partial data alongside a list of errors. Clients therefore need clear answers to:

- Was the request executed at all?
- Which field produced the error?
- Was that field replaced with null, or did null propagate up to a parent?
- What category of error occurred?
- Can the client retry, or must it modify its input?
- Is any data in the response still usable?

A simple successful response:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-100",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

A response containing an execution error:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-100",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Book title is temporarily unavailable",
      "path": ["bookById", "title"],
      "extensions": {
        "code": "BOOK_TITLE_UNAVAILABLE"
      }
    }
  ]
}
~~~

The client can still use the Book's ID even though `title` failed. This is a key difference between GraphQL and APIs that return a single status/error body for the entire request.

Error contracts should be designed deliberately rather than letting every resolver craft its own ad-hoc messages and extensions.

## 2. GraphQL response shape

A GraphQL response has three standardized top-level entries:

| Entry | Role |
|---|---|
| `data` | Result of operation execution |
| `errors` | List of errors raised during the request |
| `extensions` | Extended metadata provided by the implementation |

Successful responses typically have `data` and no `errors`. Under the current GraphQL Specification, a request error result has `errors` without `data`. When an error occurs during field execution, the response has both `data` and `errors`; the failing position is replaced with null while other fields can continue.

Compatibility note: Spring for GraphQL documentation currently notes that request-level parse/validation errors may return `data: null` alongside top-level errors. When working with a specific Spring for GraphQL/GraphQL Java version, verify the transport's actual response and document that behavior in your application contract. The core distinction remains that the error occurred before execution and has no field path, rather than relying solely on whether the `data` key is present.

Example request error:

~~~json
{
  "errors": [
    {
      "message": "Cannot query field 'titel' on type 'Book'.",
      "locations": [
        {
          "line": 3,
          "column": 5
        }
      ]
    }
  ]
}
~~~

There is no `data` because the operation was never executed.

Example execution error:

~~~json
{
  "data": {
    "bookById": null,
    "featuredBooks": [
      {
        "id": "b-100",
        "title": "GraphQL in Practice"
      }
    ]
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

`featuredBooks` still has data. Clients must inspect both `data` and `errors`, rather than treating the presence of `errors` as total operation failure.

## 3. Distinguishing request errors and execution errors

These two error categories differ in timing and handling:

| Characteristic | Request error | Execution error |
|---|---|---|
| Timing | Before executing the operation | While resolving a field |
| Examples | Syntax error, unknown field, invalid variable | Missing record, database timeout |
| Are `DataFetcher`s called? | No | One or more `DataFetcher`s may have run |
| Top-level `data` | Absent per spec; some implementations return `null` | Present; may be an object, partial data, or null |
| `path` | Usually absent | Identifies the failing response position |
| Typical Spring mechanism | Transport/interceptors and GraphQL engine | `DataFetcherExceptionResolver` |

Request errors typically occur when:

- The GraphQL document has a syntax error.
- A field or argument does not exist in the schema.
- The operation cannot be identified.
- A variable cannot be coerced to the declared type.
- A validation rule rejects the document.

Execution errors can occur when:

- A resolver throws an exception.
- A service cannot find data.
- A database or downstream service fails.
- A returned value cannot complete per the output type.
- Authorization denies access to a field during resolution.

Do not expect a single resolver exception handler to catch every kind of error. `DataFetcherExceptionResolver` handles exceptions thrown by `DataFetcher`s during execution; it does not handle parse/validation errors that occur before any `DataFetcher` is called.

## 4. Meaning of fields inside errors[]

Each error typically contains the following fields:

| Field | Meaning | Should UI control logic depend on it? |
|---|---|---|
| `message` | Developer-oriented error description | Should not be used as a conditional key |
| `locations` | Position in the GraphQL document | Primarily for debugging |
| `path` | Response path where the error occurred | Can be used to pinpoint the affected field |
| `extensions` | Extended metadata | Use stable `code` for classification |

Example:

~~~json
{
  "message": "Book not found",
  "locations": [
    {
      "line": 4,
      "column": 7
    }
  ],
  "path": ["recentBooks", 2, "author"],
  "extensions": {
    "code": "AUTHOR_NOT_FOUND"
  }
}
~~~

`path` uses response names, so aliases appear in `path` instead of the underlying field name. If the client sends:

~~~graphql
query {
  primaryBook: bookById(id: "missing") {
    title
  }
}
~~~

The path for an error on the root field is:

~~~json
["primaryBook"]
~~~

For lists, `path` can contain numeric indices. Clients should therefore treat `path` as an array of strings and integers, never assuming every segment is a string.

## 5. How null propagation affects the error contract

When an execution error occurs, GraphQL treats that response position as if the field returned null. If the field is nullable, the parent can continue returning data. If the field is non-null, the error bubbles up to its parent until reaching a nullable response position or the root.

Example SDL:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  author: Author!
}

type Author {
  name: String!
}
~~~

If the resolver for `Author.name` fails:

- `name` is non-null, so it cannot hold null.
- `author` is also non-null, so null continues bubbling up to `Book`.
- `bookById` is nullable, so the `bookById` field result becomes null.
- Other sibling fields on `Query` can still return data.

Illustrative response:

~~~json
{
  "data": {
    "bookById": null,
    "health": "UP"
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["bookById", "author", "name"],
      "extensions": {
        "code": "AUTHOR_SERVICE_UNAVAILABLE"
      }
    }
  ]
}
~~~

If `bookById` were also `Book!`, null would propagate all the way to the root and `data` would become null. Thus, nullability in SDL is part of the error contract, not merely a data type description.

When designing sensitive fields or fields backed by external services, consider whether a failure on that field should wipe out the entire parent object.

## 6. Choosing top-level errors vs. errors-as-data

Not every unsuccessful outcome should be represented with exceptions.

A practical guideline:

- Use top-level `errors` for unexpected execution failures, system errors, authentication/authorization failures, and errors preventing field resolution.
- Use errors-as-data for predictable business outcomes that clients must handle as part of a workflow.

Examples:

| Scenario | Typically appropriate representation |
|---|---|
| Database timeout | Top-level GraphQL error |
| Invalid GraphQL document | Request error |
| Invalid JWT | HTTP authentication error or GraphQL error depending on the rejection layer |
| User lacks permission to read a field | Execution error |
| Book title already taken | Typed business error in mutation payload |
| Insufficient stock quantity | Typed business error in mutation payload |
| Input invalid per business rules | Typed business error or binding error depending on stage |

Do not use top-level exceptions for routine business errors. When clients need to render per-field validation messages or let users correct a form, a typed payload is usually clearer.

Conversely, do not turn a database outage or programming bug into `userErrors`. Clients might mistake it for a normal, recoverable business outcome.

## 7. Designing errors-as-data for Mutations

Suppose creating a `Book` can fail because the ISBN already exists or the title is invalid. The schema can declare:

~~~graphql
enum CreateBookErrorCode {
  ISBN_ALREADY_EXISTS
  TITLE_REQUIRED
  INVALID_PUBLICATION_YEAR
}

type UserError {
  code: CreateBookErrorCode!
  message: String!
  field: [String!]
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

The resolver returns the business outcome:

~~~java
@MutationMapping
public CreateBookPayload createBook(
        @Argument CreateBookInput input) {

    if (bookService.isbnExists(input.isbn())) {
        return new CreateBookPayload(
                null,
                List.of(new UserError(
                        CreateBookErrorCode.ISBN_ALREADY_EXISTS,
                        "ISBN is already registered",
                        List.of("isbn"))));
    }

    Book book = bookService.create(input);

    return new CreateBookPayload(book, List.of());
}
~~~

Clients can query the payload:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
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
~~~

When the ISBN already exists, the operation still executes successfully per the GraphQL protocol. The client receives a payload with `book: null` and one entry in `userErrors`.

Enum codes are part of the schema contract. To add a new business error, add an enum value and update clients accordingly. Avoid changing the meaning of an existing code or deleting a value while clients still use it.

## 8. Organizing stable error codes

Do not let clients depend on Java exception classes or free-form messages.

Example taxonomy:

| Code | Meaning | Client handling |
|---|---|---|
| `BOOK_NOT_FOUND` | Book not found | Display empty/not-found state |
| `INVALID_INPUT` | Invalid input | Allow correcting data |
| `ISBN_ALREADY_EXISTS` | ISBN already in use | Report error on the ISBN field |
| `UNAUTHENTICATED` | Not authenticated | Prompt to log in |
| `FORBIDDEN` | Not authorized | Show access denied |
| `RATE_LIMITED` | Request limit exceeded | Wait before retrying |
| `DEPENDENCY_UNAVAILABLE` | Dependent service unavailable | May retry if operation is safe |
| `INTERNAL_ERROR` | Unexpected error | Show generic message and record support ID |

A good error code should:

- Have a stable, readable name.
- Have a single unambiguous meaning.
- Contain no user IDs, record IDs, or dynamic data.
- Not depend on Java class names.
- Not change across display languages.
- Be documented with expected client handling.

Additional metadata can live in `extensions`:

~~~json
{
  "code": "DEPENDENCY_UNAVAILABLE",
  "retryable": true,
  "correlationId": "req-7f21"
}
~~~

Only include `retryable` when the server can make a trustworthy determination. Not every timeout can be retried safely, especially for Mutations that may have committed even though the response was lost.

## 9. Distinguishing ErrorType from extensions.code

Spring for GraphQL provides `ErrorType` for coarse-grained error classification:

- `BAD_REQUEST`
- `UNAUTHORIZED`
- `FORBIDDEN`
- `NOT_FOUND`
- `INTERNAL_ERROR`

`ErrorType` is a framework-level classification. `extensions.code` is the detailed code belonging to your application's public API contract.

When building a `GraphQLError`, set `errorType(ErrorType.NOT_FOUND)` to attach Spring's classification. If you want to expose the classification as a separate extension, add it explicitly to `extensions`; always keep `extensions.code` as the stable application code for clients.

Clients can branch on specific codes for business handling, while classifications help group errors broadly. Never force clients to parse `message` to distinguish not-found from forbidden.

`ErrorType` does not determine the HTTP status code on its own. It classifies GraphQL errors at the execution layer. HTTP status also depends on whether the error occurred in transport or execution, the media type, and the GraphQL-over-HTTP behavior supported by the server. Do not mechanically map `NOT_FOUND` to HTTP 404 for every GraphQL field error, because a single response can contain multiple fields and partial data.

You do not need a separate code for every internal exception class. Multiple exceptions can map to the same public error code when their contract and client handling are identical.

## 10. Mapping exceptions with DataFetcherExceptionResolver

Spring for GraphQL registers a `DataFetcherExceptionHandler` with GraphQL Java and provides the `DataFetcherExceptionResolver` contract for applications to handle exceptions from `DataFetcher`s.

Spring Boot auto-detects resolver beans and invokes them in registration order. A resolver can return one or more `GraphQLError`s. If a resolver does not handle an exception, it returns an unresolved result so the next resolver gets a chance.

Example:

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
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        if (exception instanceof DependencyUnavailableException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.INTERNAL_ERROR)
                    .message("A required service is temporarily unavailable")
                    .extensions(Map.of(
                            "code", "DEPENDENCY_UNAVAILABLE"))
                    .build();
        }

        return null;
    }
}
~~~

Key points to remember:

- Use `GraphqlErrorBuilder.newError(environment)` so the error attaches to the current `DataFetchingEnvironment`.
- `ErrorType` classifies the error broadly.
- `extensions.code` gives clients a stable code.
- Return null when the resolver does not handle the exception so the next resolver runs.
- Never leak internal exception messages into public responses.

When multiple resolvers exist, order them so specific resolvers handle exceptions before generic catch-all resolvers.

## 11. Using @GraphQlExceptionHandler in annotated controllers

When resolvers are declared with `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping`, exceptions can be handled with `@GraphQlExceptionHandler`.

A handler placed inside a controller applies only to that controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of(
                        "code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

To share handlers across multiple controllers, place them in a `@ControllerAdvice`:

~~~java
@ControllerAdvice
public class GlobalGraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .errorType(ErrorType.NOT_FOUND)
                .message("Requested resource was not found")
                .extensions(Map.of(
                        "code", "RESOURCE_NOT_FOUND"))
                .build();
    }
}
~~~

Inject `GraphqlErrorBuilder` rather than creating a builder without an environment. The builder supplied by Spring is already bound to the current `DataFetchingEnvironment`, preserving field location and path details.

Do not declare multiple handlers capable of matching the same exception without clear precedence rules. Review controller-local and global advice scopes to avoid inconsistent mappings.

## 12. Binding and validation errors

Inputs can be rejected at two distinct points:

**GraphQL request validation/coercion**

If a client passes the wrong variable type, omits a non-null argument, or queries a field absent from the schema, GraphQL rejects the request before any `DataFetcher` runs. This is a request error.

**Spring argument binding/Bean Validation**

Once GraphQL accepts the operation and Spring binds inputs into Java objects, validation can occur when the `DataFetcher` is invoked. For example, using `@Valid` on an argument:

~~~java
@MutationMapping
public Book createBook(
        @Argument @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String isbn,
        @Min(1450) Integer publicationYear) {
}
~~~

You can handle `BindException` with `@GraphQlExceptionHandler`:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBinding(
        BindException exception,
        GraphqlErrorBuilder<?> errorBuilder) {

    return errorBuilder
            .errorType(ErrorType.BAD_REQUEST)
            .message("Input validation failed")
            .extensions(Map.of(
                    "code", "INVALID_INPUT"))
            .build();
}
~~~

Do not echo raw rejected values or full input objects in the message. They may contain emails, tokens, personal data, or sensitive fields. When clients need per-field errors, errors-as-data with field paths is generally a better fit.

## 13. Request-level errors bypass DataFetcherExceptionResolver

Parse, validation, and variable coercion errors arise before any `DataFetcher` executes. Consequently, `DataFetcherExceptionResolver` cannot handle these errors.

If you need to normalize request errors, use a `WebGraphQlInterceptor` to inspect the GraphQL execution response and adjust the error result at the transport layer.

Do not alter standard details like `locations` or `message` so heavily that query debugging becomes impossible. Usually you only need to add useful metadata or apply redaction policies in production.

A request-level error has no field path because no response position was executed. Clients should display an operation-level error and use `locations` to assist developers when needed.

## 14. Authentication and authorization errors

Authentication and authorization can reject requests at two layers:

**HTTP security filter**

If a JWT is missing or invalid, Spring Security can reject the request before the GraphQL engine receives the operation. Clients receive HTTP 401 or 403 depending on security configuration and transport.

**Field/service authorization**

If a request passes HTTP authentication but a `DataFetcher` calls a service method that throws `AccessDeniedException`, this is an execution error. GraphQL can return partial data alongside an error on the denied field.

Example:

~~~java
@Service
public class InventoryService {

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory findForProduct(String productId) {
        return repository.findByProductId(productId)
                .orElseThrow(InventoryNotFoundException::new);
    }
}
~~~

An exception resolver can map it:

~~~java
if (exception instanceof AccessDeniedException) {
    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("Access denied")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
}
~~~

Do not treat HTTP 200 as proof that every field succeeded. A GraphQL execution can return a successful transport-level HTTP response while still containing errors in the body. Clients must inspect status, content type, and the GraphQL response body.

## 15. Errors from Subscription publishers

Subscriptions have a different lifecycle from Queries and Mutations. A Subscription `DataFetcher` typically only creates the initial publisher. Afterward, the transport subscribes to that publisher, which may emit an error signal later on.

`DataFetcherExceptionResolver` does not handle error signals emitted after the `DataFetcher` has already returned its publisher. Spring for GraphQL provides `SubscriptionExceptionResolver` to map publisher errors into GraphQL errors sent over the transport.

Contract considerations:

- Errors while constructing the publisher can go through `DataFetcher` exception handling.
- Errors emitted while the publisher is streaming events require `SubscriptionExceptionResolver`.
- Clients must handle stream-termination or error messages per the transport protocol.
- Never forward raw exception messages from event sources straight to clients.

Over WebSocket, subscription errors may be sent as a terminal error message per the active protocol. Over SSE, check how the transport represents events and errors. Do not assume all transports share the same frame format.

## 16. Transport-layer errors

Some failures never produce a GraphQL response:

- DNS lookup or TLS handshake failure.
- Connection closed before the server sends a response.
- Client timeout waiting for a response.
- HTTP proxy or gateway rejecting the request.
- Request body too large or unsupported media type.

In these cases, the client receives no `data`, `errors`, or `extensions`. These are transport/network failures, not a GraphQL `extensions.code` returned by a resolver. Clients must distinguish HTTP/WebSocket client exceptions from decoded GraphQL errors in responses.

Do not blindly auto-retry every transport failure on Mutations. A connection may drop after the server committed the change but before the client received the response. Use an idempotency key or command ID when clients must be able to resend operations safely.

## 17. Error contracts for system and internal errors

Never allow library exception classes or raw messages to appear directly in the API contract.

Example of what NOT to return:

~~~json
{
  "errors": [
    {
      "message": "org.postgresql.util.PSQLException: Connection refused at 10.0.2.15:5432"
    }
  ]
}
~~~

Such details can leak:

- Database technology.
- Internal hostnames and ports.
- Package structure.
- Table names or SQL queries.
- User data.
- Stack traces or infrastructure details.

Return a generic public message instead:

~~~json
{
  "errors": [
    {
      "message": "The service could not complete the request",
      "extensions": {
        "code": "INTERNAL_ERROR",
        "correlationId": "req-7f21"
      }
    }
  ]
}
~~~

Exception details are written to server logs alongside a correlation/execution ID so operations teams can investigate. Never use correlation IDs as a substitute for authorization or to let clients read logs.

## 18. Correlation IDs and logging

A good error contract gives clients enough information for support to locate the exact error in logs.

Useful metadata includes:

- HTTP request correlation ID.
- GraphQL execution ID.
- Operation name.
- Error code.
- Error path.
- Trace ID if distributed tracing is configured.

Example response:

~~~json
{
  "data": {
    "bookById": null
  },
  "errors": [
    {
      "message": "The service could not complete the request",
      "path": ["bookById"],
      "extensions": {
        "code": "DEPENDENCY_UNAVAILABLE",
        "correlationId": "req-7f21"
      }
    }
  ]
}
~~~

Never include in responses:

- Bearer tokens or cookies.
- Passwords, API keys, or secrets.
- SQL statements and connection strings.
- Full GraphQL variables.
- Unnecessary personal data.
- Unsanitized exception messages.

Spring for GraphQL logs exceptions unhandled by resolvers at `ERROR` level with an execution ID for correlation. Handled exceptions are typically logged at `DEBUG` level. Applications can layer their own logging policy, while avoiding logging the exact same error repeatedly at every layer.

## 19. Do not use message as an API code

Messages can change because:

- Wording is rewritten for clarity.
- The application adds multi-language support.
- Messages are edited to avoid leaking information.
- Libraries or frameworks are upgraded.

Therefore, clients should not do this:

~~~typescript
if (error.message === "Book not found") {
  showNotFound();
}
~~~

Use the code instead:

~~~typescript
const code = error.extensions?.code;

switch (code) {
  case "BOOK_NOT_FOUND":
    showNotFound();
    break;
  case "FORBIDDEN":
    showAccessDenied();
    break;
  case "DEPENDENCY_UNAVAILABLE":
    showTemporaryFailure();
    break;
  default:
    showGenericError();
}
~~~

Messages serve human readers and debugging. Codes serve machine logic. Keep their lifecycles independent.

## 20. Retry policy is part of the error contract

Not every error is retryable.

| Error code | Should retry? | Reason |
|---|---|---|
| `BOOK_NOT_FOUND` | No | Resource does not exist |
| `INVALID_INPUT` | No | Client must fix input |
| `FORBIDDEN` | No | Retrying does not change permissions |
| `RATE_LIMITED` | Conditionally | Wait per retry-after/backoff |
| `DEPENDENCY_UNAVAILABLE` | Conditionally | Depends on timeout and operation state |
| `INTERNAL_ERROR` | Not by default | May be a logic bug or indeterminate state |

For read Queries, retrying can be safe when errors are transient and the request has no side effects.

For Mutations, a timeout does not mean the operation failed to commit. The server may have persisted data while the response was lost over the network. If the client resends the mutation, the operation may execute twice.

To retry Mutations safely, consider:

- Idempotency keys.
- Unique business command IDs.
- Checking command status before re-executing.
- Designing idempotent mutations where appropriate.
- Bounded retries with backoff and jitter.

Only return `retryable: true` when the server can truly uphold those semantics.

## 21. Evolving the error contract

Error codes and payloads are part of the API surface. When changing them, follow compatibility rules:

- You may add new error codes.
- You may add optional extension fields if older clients ignore unknown fields.
- Do not change the meaning of existing codes.
- Do not repurpose retired codes for different errors.
- Do not remove enum values still used by clients without a migration.
- Do not change the data type of existing extension fields.
- Do not turn a nullable error position into an unexpected non-null propagation failure without assessing impact.

For example, if `BOOK_NOT_FOUND` originally meant no Book exists for an ID, do not repurpose it to mean "Book hidden by policy" if clients display a generic not-found page for all cases. Introduce a new code or preserve the committed public semantics.

When changing nullability in SDL, re-verify partial data and error paths. Changing `Book` to `Book!` can cause a field error to bubble up to the root and wipe out far more data than before.

## 22. API error catalog

For large APIs, maintain an error catalog with clear owners and handling guidance.

Example:

| Code | Classification | Source | Client behavior |
|---|---|---|---|
| `INVALID_INPUT` | BAD_REQUEST | Binding/validation | Show form error |
| `BOOK_NOT_FOUND` | NOT_FOUND | Book service | Show not-found state |
| `FORBIDDEN` | FORBIDDEN | Authorization | Hide or disable action |
| `DEPENDENCY_UNAVAILABLE` | INTERNAL_ERROR | Downstream service | Show temporary failure |
| `RATE_LIMITED` | BAD_REQUEST or custom policy | Rate limiter | Backoff |
| `INTERNAL_ERROR` | INTERNAL_ERROR | Unhandled exception | Generic notice and support ID |

The catalog should specify:

- Code and meaning.
- Whether the error occurs at the request, execution, or transport layer.
- Whether partial data is possible.
- Retry semantics.
- Whether a correlation ID is included.
- What data is allowed in messages/extensions.
- Owner responsible for changing the code.

Every team does not necessarily need an identical list of codes. However, shared codes such as `FORBIDDEN`, `UNAUTHENTICATED`, and `INTERNAL_ERROR` should maintain consistent semantics across subgraphs.

## 23. Testing error contracts with GraphQlTester

`GraphQlTester` lets you execute operations and assert on both errors and data.

Example not-found test:

~~~java
@Test
void shouldReturnStableNotFoundError() {
    graphQlTester.document("""
            query {
              bookById(id: "missing") {
                id
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).hasSize(1);
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Book not found");
                assertThat(errors.get(0).getExtensions())
                        .containsEntry("code", "BOOK_NOT_FOUND");
                assertThat(errors.get(0).getPath())
                        .containsExactly("bookById");
            });
}
~~~

Partial data test:

~~~java
@Test
void shouldKeepSiblingDataWhenOneFieldFails() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
              bookById(id: "b-100") {
                id
                title
              }
              health
            }
            """)
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getExtensions())
                .containsEntry("code", "BOOK_TITLE_UNAVAILABLE");
    });
    response.path("health").entity(String.class).isEqualTo("UP");
}
~~~

Tests should assert both error codes and data. Checking only `errors().hasSize(1)` is not enough to prove clients can consume the contract properly.

## 24. Testing request errors and execution errors separately

Request error test:

~~~java
@Test
void shouldRejectInvalidFieldBeforeExecution() {
    graphQlTester.document("""
            query {
              unknownBookField
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());
}
~~~

For request errors, no `DataFetcher` is called. You can verify no interactions with services to confirm the query was rejected before execution.

Execution error test:

~~~java
@Test
void shouldReportFieldPathForResolverFailure() {
    graphQlTester.document("""
            query {
              bookById(id: "missing") {
                title
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors.get(0).getPath())
                            .containsExactly("bookById"));
}
~~~

These two tests protect the boundary between the GraphQL engine and `DataFetcher` exception handling. If code changes cause a request error to be handled like an execution error or vice versa, clients may receive responses deviating from the published contract.

## 25. Testing null propagation

For non-null fields, tests must verify where data becomes null after error propagation.

Example SDL:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  author: Author!
}

type Author {
  name: String!
}
~~~

If `Author.name` fails, `Book` and `author` may be replaced by null depending on the non-null chain. Test:

~~~java
@Test
void shouldPropagateNonNullFailureToNullableBookField() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
              bookById(id: "b-100") {
                author {
                  name
                }
              }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors.get(0).getPath())
                    .containsExactly("bookById", "author", "name"));
    response.path("bookById").valueIsNull();
}
~~~

Whenever SDL nullability changes, re-run this test. The error path still points to where the failure originated; the final null position may sit on a parent due to propagation.

## 26. Testing that messages do not leak internal details

Simulate an exception whose message contains sensitive information:

~~~java
throw new IllegalStateException(
        "Database password=secret at db.internal:5432");
~~~

The error contract should return only a generic message and code:

~~~json
{
  "errors": [
    {
      "message": "The service could not complete the request",
      "extensions": {
        "code": "INTERNAL_ERROR"
      }
    }
  ]
}
~~~

Integration tests should assert that the response contains none of:

- Internal exception class names.
- Connection strings or hostnames.
- Passwords/tokens.
- SQL statements or stack traces.
- Sensitive GraphQL variable values.

At the same time, verify that server logs record the execution ID or correlation ID so operations teams can trace the root cause.

## 27. Common error contract design mistakes

| Symptom | Cause | How to improve |
|---|---|---|
| Clients parse `message` to identify errors | No stable error code | Use `extensions.code` |
| Every error returns `INTERNAL_ERROR` | Overly generic exception mapping | Separate domain and infrastructure errors |
| Business validation fails the entire response | Using exceptions for predictable business outcomes | Design errors-as-data |
| Clients ignore partial data | Only checking the `errors` array | Inspect both `data` and `errors` |
| Request errors bypass custom resolver | Errors happen before `DataFetcher`s | Use transport interceptors when genuinely needed |
| Subscription errors go unmapped | Error signal occurs after returning the `Publisher` | Use `SubscriptionExceptionResolver` |
| Messages expose SQL or tokens | Returning raw exception messages | Standardize messages and log internally |
| Retrying Mutations causes duplicate writes | Timeouts mistaken for uncommitted failures | Idempotency keys and command IDs |
| Field error wipes out whole object | Nullability too strict for independently failing fields | Re-evaluate SDL nullability |
| HTTP 200 assumed to mean complete success | Reading only HTTP status code | Inspect GraphQL `errors` in the body |
| Error codes change across releases | No error catalog | Manage codes as API contract |

## 28. Error contract design checklist

Before publishing a GraphQL API:

- [ ] Distinguish request errors, execution errors, and transport errors.
- [ ] Use `data`, `errors`, and `extensions` properly per the response format.
- [ ] Provide stable error codes for errors clients must handle.
- [ ] Do not use `message` for conditional logic.
- [ ] Distinguish predictable business errors from system failures.
- [ ] Design errors-as-data for mutation payloads where appropriate.
- [ ] Use `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` for `DataFetcher` errors.
- [ ] Have a transport-level mechanism for request-level errors if responses must be transformed.
- [ ] Use `SubscriptionExceptionResolver` for publisher errors after subscribing.
- [ ] Evaluate nullability and null propagation.
- [ ] Ensure error paths accurately reflect aliases and list indices.
- [ ] Never return raw exception messages, stack traces, or secrets.
- [ ] Include a correlation/execution ID for support troubleshooting.
- [ ] Define clear retry semantics that are safe for Mutations.
- [ ] Assign ownership to the error catalog and govern it as part of the API surface.
- [ ] Write tests for request errors, execution errors, partial data, and null propagation.
- [ ] Write tests for message sanitization and stable `extensions.code`.

## Conclusion

The error contract is part of API design. GraphQL separates pre-execution errors from errors occurring during field resolution. Per the response specification, request errors omit `data`; certain versions of Spring for GraphQL may represent them with `data: null` as noted above. Execution errors can return partial data alongside error paths. SDL nullability determines how far failures propagate in the response.

In Spring for GraphQL, use `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler` to map exceptions from `DataFetcher`s. Request-level errors must be handled at the transport layer if they need transformation; Subscription publisher errors require `SubscriptionExceptionResolver`. Use stable `extensions.code` values for clients while keeping `message` as a developer-facing description.

Predictable business errors can be modeled as typed payloads. Infrastructure failures, authorization errors, and unexpected faults should flow through top-level errors with controlled details. Combining an error catalog, retry policy, correlation IDs, and contract tests lets the API evolve without coupling clients to internal implementations.

## References

- [Spring for GraphQL — Request Execution and Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and @GraphQlExceptionHandler](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL — Response Format](https://graphql.org/learn/response/)
- [GraphQL — Error Handling](https://graphql.org/learn/error-handling/)
- [GraphQL Specification — Response](https://spec.graphql.org/September2026/#sec-Response)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
