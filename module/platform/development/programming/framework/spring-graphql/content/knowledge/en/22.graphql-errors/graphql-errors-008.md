# Exceptions in DataFetcher

In GraphQL, each field is resolved by a **DataFetcher**. A DataFetcher may call a repository, service, external system, or enforce a business rule. These operations can fail: data is not found, the user lacks permission, input violates a rule, or a downstream service does not respond.

When an exception occurs inside a DataFetcher, GraphQL Java routes the error into the field execution exception handling mechanism. Spring for GraphQL adds **DataFetcherExceptionResolver** to convert exceptions into one or more structured **GraphQLError** instances suitable for the API. The goal is to return useful information to clients, preserve data from other fields when possible, and avoid exposing internal details.

## 1. Where do exceptions occur in GraphQL execution?

A GraphQL operation is parsed, validated, and then executed. During the execution stage, GraphQL Java invokes the DataFetcher corresponding to each selected field. In Spring for GraphQL, a DataFetcher can be created from annotated controllers such as **@QueryMapping**, **@MutationMapping**, **@SchemaMapping**, or registered directly.

Example resolver reading a book:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

If **bookService.findById** throws **BookNotFoundException**, the exception occurs while the DataFetcher for the **Query.bookById** field is running. GraphQL Java records the error for that field, attaches the corresponding location and path, and continues executing other fields according to GraphQL rules if possible.

Overall flow:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[Parse and validate]
    B --> C[Execute selection set]
    C --> D[Invoke DataFetcher]
    D --> E{Exception thrown?}
    E -->|No| F[Put data into response]
    E -->|Yes| G[DataFetcherExceptionHandler]
    G --> H[Spring DataFetcherExceptionResolver]
    H --> I[GraphQLError]
    I --> J[Add errors and apply null propagation]
    F --> K[GraphQL response]
    J --> K
~~~

Exceptions from a DataFetcher differ from syntax or validation errors in a GraphQL document. Parse/validation errors happen before any DataFetcher runs; therefore, **DataFetcherExceptionResolver** is not the place to handle every error that can appear in a GraphQL request.

## 2. Error types to distinguish

Not every exception should be returned to clients in the same way. Before writing resolvers, classify errors by their origin and API meaning:

| Error type | Example | Typically appropriate handling |
| --- | --- | --- |
| Resource not found | No book with the given ID | Return a business error with a stable code, or null if the contract allows and the API defines it that way |
| Unauthorized action (forbidden) | Authenticated user lacks permission to view an order | Return FORBIDDEN without exposing protected data |
| Unauthenticated | No valid principal or token | Handle at the security layer or return UNAUTHORIZED per the API contract |
| Invalid input | Value exceeds business limits | Return BAD_REQUEST or a specific validation code |
| Business conflict | Order is already confirmed and cannot be edited | Return a business error code such as ORDER_ALREADY_CONFIRMED |
| Infrastructure/downstream | Database or payment service is unavailable | Log fully on the server and return a safe generic error |
| Programming error | Unexpected null, broken invariant | Treat as an internal error; do not expose exception details to the client |

The GraphQL schema already checks data types, required arguments, enums, and scalar coercion before the DataFetcher runs. However, rules such as requiring positive quantities, verifying the account belongs to the current tenant, or validating order state transitions still need to be checked at the application/domain layer.

Do not use exceptions for every normal control-flow branch. If a nullable result is not found and that is a normal API state, the resolver can return null. If the situation carries a business error meaning that clients must distinguish, return a GraphQL error with a stable code.

## 3. GraphQL response when a DataFetcher throws an exception

GraphQL does not necessarily abort the entire operation when one field fails. An execution response can contain both **data** and **errors**:

~~~json
{
  "data": {
    "bookById": null,
    "latestBooks": [
      {
        "id": "book-01",
        "title": "Spring in Action"
      }
    ]
  },
  "errors": [
    {
      "message": "Book not found",
      "locations": [
        { "line": 2, "column": 3 }
      ],
      "path": ["bookById"]
    }
  ]
}
~~~

In this example, the **bookById** field failed, yet **latestBooks** still has data. This is a partial response. Clients need to inspect both data and errors rather than relying only on HTTP status or assuming a request can only succeed completely or fail completely.

A GraphQL error typically has the following components:

- **message**: message intended for the client.
- **locations**: position of the field in the GraphQL document, if available.
- **path**: path to the field that raised the error in the response.
- **extensions**: additional metadata such as error codes, classification, or publicly shareable info.

Path uses response keys, so it can contain aliases and list indices. For example, if a client uses the alias **featured: bookById** and an error occurs in the third element of a list, the path might be **["featured", "reviews", 2, "author"]**. Based on path, the client identifies the exact affected portion of data.

## 4. GraphQL Java's default DataFetcherExceptionHandler

GraphQL Java has a **DataFetcherExceptionHandler** mechanism to catch exceptions thrown while a DataFetcher executes and convert them into execution errors. The default handler records the exception along with field location/path, then creates the corresponding GraphQLError.

When using Spring for GraphQL, the framework integrates this error-handling mechanism with a list of **DataFetcherExceptionResolver** beans. Application resolvers get a chance to recognize exceptions and produce appropriate errors. If no resolver handles the exception, Spring applies default behavior: logging the error and returning a generic message to avoid exposing internal details to clients.

This creates two distinct responsibilities:

1. GraphQL Java identifies which field owns the error and continues execution according to GraphQL semantics.
2. Spring for GraphQL lets the application interpret exceptions into GraphQLError instances conforming to the API contract.

Do not replace GraphQL Java's DataFetcherExceptionHandler just to change the message for a business exception when Spring already provides the **DataFetcherExceptionResolver** extension point. Using a resolver integrates with Spring configuration and is easier to test.

## 5. DataFetcherExceptionResolver

**DataFetcherExceptionResolver** is Spring for GraphQL's contract for handling exceptions from DataFetchers. A resolver receives the exception and **DataFetchingEnvironment**, then returns an asynchronous result containing a list of GraphQLError instances if it recognizes the error.

When not handling an exception, the resolver must signal an unresolved state so the next resolver or default handler can proceed. With the interface directly, **Mono.empty()** represents unresolved; when resolved, return a Mono containing the error list. Do not confuse an empty list of errors with the unresolved state.

Example implementing an adapter to map book-not-found errors:

~~~java
@Component
public class BookNotFoundExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
        }

        return null;
    }
}
~~~

**DataFetcherExceptionResolverAdapter** simplifies implementation when one exception only needs to produce one GraphQLError. The **resolveToSingleError** method returns a GraphQLError if handled, or null if the exception is outside this resolver's scope.

**GraphqlErrorBuilder.newError(environment)** creates an error bound to the current DataFetchingEnvironment. As a result, the GraphQL error gets location/path matching the executing field. **ErrorType.NOT_FOUND** is Spring for GraphQL's classification; the **code** extension is an application-defined stable code for clients to handle.

Register resolvers via component scanning or bean configuration. Spring for GraphQL uses detected resolvers during GraphQL runtime configuration.

## 6. Classifying errors with ErrorType and extensions

Spring for GraphQL provides common classifications via **ErrorType**, such as:

| ErrorType | Meaning |
| --- | --- |
| BAD_REQUEST | Invalid input or request at the application layer |
| UNAUTHORIZED | Request is not authenticated |
| FORBIDDEN | Caller lacks permission to perform the action |
| NOT_FOUND | Requested resource does not exist |
| INTERNAL_ERROR | Internal error whose details should not be exposed |

Classification helps clients and observability tools categorize errors. However, the API should also include a stable business error code in **extensions.code**, such as **BOOK_NOT_FOUND**, **ORDER_ALREADY_CONFIRMED**, or **INVENTORY_INSUFFICIENT**. Do not force clients to parse message strings because messages may vary by language or phrasing.

Example of a business conflict error:

~~~java
@Component
public class OrderExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof OrderAlreadyConfirmedException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("The order can no longer be changed")
                .extensions(Map.of("code", "ORDER_ALREADY_CONFIRMED"))
                .build();
        }

        return null;
    }
}
~~~

GraphQL does not predefine every application business error code. Choose an appropriate classification and define your own extensions for cases that clients need to distinguish.

## 7. Using @GraphQlExceptionHandler

Spring for GraphQL supports **@GraphQlExceptionHandler** to handle exceptions via annotated methods. You can place handlers inside a controller to handle errors tied to that controller, or inside **@ControllerAdvice** to apply centrally across multiple controllers.

Example global handler:

~~~java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException ex,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("You are not allowed to access this resource")
            .extensions(Map.of("code", "ACCESS_DENIED"))
            .build();
    }
}
~~~

Annotated exception handlers organize logic by exception type and leverage Spring's method argument resolution. They work well when consolidating error-mapping rules into controller advice. For complex logic, returning multiple GraphQLErrors, or lower-level handling, you can implement **DataFetcherExceptionResolver** directly or extend the adapter.

There is no need to write both a @GraphQlExceptionHandler and a DataFetcherExceptionResolver for the same exception unless intentional. Avoid having two places handle the same error with two different messages or error codes. Choose one primary source for each exception group and test ordering/precedence if multiple resolvers exist.

## 8. Mapping exceptions by error group

A single resolver can handle multiple exception types, but it should not turn into a giant switch block containing the entire domain. You can split by domain group or use multiple specialized resolvers.

For example:

~~~java
@Component
public class AccessExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof AccessDeniedException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Access denied")
                .extensions(Map.of("code", "ACCESS_DENIED"))
                .build();
        }

        if (ex instanceof AuthenticationException) {
            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.UNAUTHORIZED)
                .message("Authentication is required")
                .extensions(Map.of("code", "UNAUTHENTICATED"))
                .build();
        }

        return null;
    }
}
~~~

When classifying security errors, distinguish an unauthenticated caller from an authenticated caller who lacks permission. Do not return information indicating whether a sensitive resource exists if doing so leaks data. In many systems, the same generic message is appropriate for both non-existent resources and unauthorized access.

Authentication errors occurring before GraphQL execution starts can be handled by Spring Security filters or the web security layer without passing through DataFetcherExceptionResolver. This resolver primarily handles exceptions raised while a DataFetcher executes.

## 9. Exceptions in CompletableFuture and asynchronous resolvers

A DataFetcher can return **CompletableFuture**, **CompletionStage**, **Mono**, or other asynchronous result types supported by Spring for GraphQL. If a future completes exceptionally, the error still belongs to field execution and is routed through GraphQL's exception handling mechanism.

For example:

~~~java
@QueryMapping
public CompletableFuture<Book> bookById(@Argument("id") String id) {
    return bookClient.findById(id);
}
~~~

If the HTTP call completes with an exception, the exception resolver can receive the corresponding error and construct a GraphQLError for the **bookById** field. With CompletableFuture, exceptions may be wrapped in **CompletionException**; when identifying the cause, safely inspect the cause rather than assuming the exception is always the outermost wrapper.

Do not call **join()** or **get()** in a controller just to catch exceptions synchronously. That blocks threads and defeats async benefits. Let the future complete exceptionally and handle it in DataFetcherExceptionResolver or an annotated exception handler.

For resolvers returning Mono/Flux, reactive errors also need to be translated via Spring for GraphQL's compatible mechanisms. Avoid turning errors into null or an empty list unless that is a valid business fallback.

## 10. Path, location, and aliases in GraphQLError

When using **GraphqlErrorBuilder.newError(environment)**, GraphQL Java can attach execution information to the error:

- Location indicates the line/column in the document at the field being executed.
- Path indicates the position in the response data.
- Alias is used as the response key in path.
- List index appears in path when an error occurs on a specific element.

Example query:

~~~graphql
query {
    featured: bookById(id: "missing") {
        author {
            name
        }
    }
}
~~~

If an error arises in **Book.author**, path might start with **["featured", "author"]**. Clients use path to pinpoint the failing branch even when the alias differs from the schema field name.

Do not manually build errors without the environment when the error belongs to a specific field. Using the builder with DataFetchingEnvironment preserves the right path/location. For errors not tied to a single field, such as parse/validation errors or transport-level request errors, error construction and handling locations differ.

## 11. Null propagation when a non-null field fails

The GraphQL schema defines whether a field is nullable or non-null. When a non-null field's DataFetcher throws an exception, GraphQL cannot return null at that field while maintaining its contract. Null is pushed up to the nearest nullable parent; this process is called **null propagation**.

For example:

~~~graphql
type Query {
    book: Book
}

type Book {
    id: ID!
    author: Author!
}

type Author {
    name: String!
}
~~~

If **Book.author** fails, the author value cannot be null because the schema declares Author!. Because **Query.book** is nullable, the entire book can become null. GraphQL still keeps the error path pointing to the original author field.

If **Query.book** is also Book!, then null continues propagating up to root data. Thus, an exception in a deeply nested field can nullify a large portion of the response depending on the chain of non-null wrappers.

When designing the schema, choose nullability based on data availability and field independence. Do not mark every field non-null just to make the response look cleaner. If a field depends on an unstable service, making it nullable lets other fields still return data.

## 12. Partial data and client-side handling

Clients should handle both parts of a GraphQL response simultaneously:

- **data** contains fields that resolved successfully or null due to errors/nullability.
- **errors** contains error details, path, and extensions.

For example, a screen displays book details and reviews. If the reviews service fails, the client can still show the book title and indicate that reviews are temporarily unavailable, provided the schema allows the reviews field to be nullable.

Do not treat the presence of items in errors as meaning the entire operation failed. Conversely, do not ignore errors just because partial data is present. Clients can rely on extensions.code to decide whether to show a message, prompt to log in again, or allow retrying part of the data.

The HTTP status of a GraphQL request depends on transport and request/execution handling configuration. An execution error does not necessarily correspond to an HTTP 4xx/5xx for the whole request. Therefore, error codes in GraphQL extensions provide a clearer contract for per-field error handling.

## 13. Differences between validation errors and DataFetcher exceptions

Distinguish pre-execution errors from DataFetcher exceptions:

| Stage | Example | Handled by DataFetcherExceptionResolver? |
| --- | --- | --- |
| Parse | GraphQL document has syntax error | No |
| Validation | Non-existent field, wrong argument type | No |
| Variable coercion | Variable incompatible with scalar or missing non-null variable | No |
| DataFetcher execution | Service throws BookNotFoundException | Yes |
| Async completion | CompletableFuture completes exceptionally in resolver | Yes |
| HTTP authentication/filter | Invalid token before GraphQL handler | Usually handled at the security/web layer |

Bean Validation on DTOs or inputs may run when a resolver is invoked. If a validation exception is thrown from the method or service, it can be handled as a DataFetcher exception. However, GraphQL type coercion errors that occurred earlier do not pass through the resolver.

Choose the extension point at the right layer. Use the schema to validate types and required inputs; use Bean Validation/domain services for data rules; use DataFetcherExceptionResolver for exceptions raised during field resolution.

## 14. Logging and protecting internal information

Exceptions often contain information useful to developers that is unsuitable to return verbatim to clients. For example, JDBC driver messages may include table names, SQL, or database hosts; HTTP clients may put internal URLs or tokens into exceptions; stack traces can expose classes and system structure.

Principles:

- Return short, safe, meaningful messages to clients.
- Put stable error codes in extensions.code.
- Log the original exception on the server with stack traces when investigation is needed.
- Attach a correlation ID or trace ID to logs to locate related requests.
- Do not log tokens, cookies, passwords, payment data, or full GraphQL variables if they contain sensitive data.
- Do not return ex.getMessage() for every exception by default.
- Do not swallow infrastructure exceptions and return empty data as if the request succeeded.

Spring for GraphQL's default handler hides details of unresolved errors behind a generic message. For recognized business errors, resolvers can return specific messages while still avoiding unnecessary disclosure.

## 15. Testing DataFetcherExceptionResolver with GraphQlTester

Test from the GraphQL client's perspective to confirm the resolver is invoked, the exception is mapped, and the response matches the data/errors contract.

Example querying a non-existent ID:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
                title
            }
        }
        """)
    .execute();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();

response.path("bookById").valueIsNull();
~~~

This test verifies the public error code and the nullable field's value. If the schema uses non-null fields, verify the null propagation location according to the parent structure rather than expecting only the child field to be null.

Scenarios to test:

1. Business exceptions map to the expected classification and error code.
2. Unrecognized exceptions fall through to the default handler.
3. Returned messages do not contain SQL, stack traces, internal hosts, or tokens.
4. Aliases and list indices are accurately reflected in the error path.
5. Nullable fields preserve partial data of other fields.
6. Non-null fields apply null propagation according to the schema.
7. Future/Mono completing exceptionally is handled similarly to synchronous resolvers.
8. Authentication and authorization properly distinguish UNAUTHORIZED/FORBIDDEN.
9. Pre-execution validation errors are not mistaken for DataFetcher errors.

Beyond integration tests, you can unit test resolvers by providing an exception and a suitable mock DataFetchingEnvironment. However, testing through GraphQlTester remains essential to verify actual Spring wiring and the final response.

## 16. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Client sees Internal Server Error for business errors | Resolver not registered or exception not recognized | Register DataFetcherExceptionResolver or @GraphQlExceptionHandler |
| Resolver does not handle parse/validation errors | Exception occurred before DataFetcher ran | Handle at the appropriate GraphQL request/validation layer |
| Client sees internal messages | Returning ex.getMessage() verbatim | Use safe messages and log the original exception server-side |
| Missing expected path/location | Creating GraphQLError without DataFetchingEnvironment | Use GraphqlErrorBuilder.newError(environment) |
| Parent field also becomes null | Non-null propagation per schema | Review nullability and field contract |
| One resolver catches exception but another does not run | Handling logic placed in wrong scope or exception not thrown from DataFetcher | Check lifecycle and actual exception type |
| Async exception not recognized | Cause wrapped in CompletionException | Safely unwrap cause when classifying |
| Error code changes with message | Client depends on message string | Define a stable extensions.code |
| Same error handled twice | Overlapping annotated handler and resolver scopes | Choose a single source of truth or control ordering |
| Error turned into null/empty | Fallback masks the exception | Fall back only when it is valid business behavior |

## 17. Exception handling design principles

Classify exceptions by business meaning and origin layer. Use **DataFetcherExceptionResolverAdapter** for clear, straightforward mappings; use **@GraphQlExceptionHandler** when organizing handlers by controller or ControllerAdvice; use the **DataFetcherExceptionResolver** interface when handling multiple errors or deeper custom logic.

Build GraphQLError bound to DataFetchingEnvironment to preserve path/location. Choose an appropriate ErrorType and provide stable extensions.code values for clients. Keep messages safe, log original exceptions on the server, and prevent internal errors from leaking data. Understand null propagation to pick nullability suited to how fields can fail.

In Spring for GraphQL, an exception in a DataFetcher is a per-field execution error. A good resolver does more than turn exceptions into messages; it preserves GraphQL semantics, allows partial data when appropriate, and provides an error contract that clients can handle consistently.
