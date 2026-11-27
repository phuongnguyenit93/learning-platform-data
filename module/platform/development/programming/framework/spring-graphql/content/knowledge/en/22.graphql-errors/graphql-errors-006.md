# @GraphQlExceptionHandler

In Spring for GraphQL, exceptions can arise when a resolver calls a service, queries a repository, or enforces business rules. If exceptions are allowed to propagate directly outward, clients may receive inconsistent error messages and the server risks exposing internal details. **@GraphQlExceptionHandler** provides a way to map exceptions raised during field execution into structured **GraphQLError** instances.

Handlers can be placed directly inside the controller that owns the resolver or inside an **@ControllerAdvice** to apply across multiple controllers. This allows the application to standardize error type, message, path, location, and extensions according to the GraphQL contract.

This lesson covers declaring local and global exception handlers, how Spring selects a handler, building GraphQLError with GraphqlErrorBuilder, distinguishing execution errors from parse/validation/coercion errors, protecting sensitive information, the impact of nullability, and testing with GraphQlTester.

## 1. What problem does @GraphQlExceptionHandler solve?

Suppose a resolver looks up a book:

~~~java
@QueryMapping
public Book book(@Argument("id") String id) {
    return bookService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

If the book is not found, the service throws **BookNotFoundException**. The application needs to convert that situation into a GraphQL error that the client can understand.

Each resolver should not catch exceptions and build responses on its own. That duplicates error-handling logic and easily leads to inconsistency. With **@GraphQlExceptionHandler**, the application centralizes converting exceptions into GraphQLError in one place.

For example, every BookNotFoundException can be converted into:

~~~json
{
  "message": "Book not found",
  "path": ["book"],
  "extensions": {
    "classification": "NOT_FOUND",
    "code": "BOOK_NOT_FOUND"
  }
}
~~~

Clients can read the stable error code BOOK_NOT_FOUND to display a message or handle the appropriate state.

## 2. Local exception handlers in @Controller

You can declare a **@GraphQlExceptionHandler** method directly inside an annotated controller. A local handler fits when the exception handling only makes sense for the resolvers in that controller.

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }
}
~~~

In this example:

- **@GraphQlExceptionHandler** marks the method that handles the exception.
- **BookNotFoundException** is the exception type to handle.
- **DataFetchingEnvironment** provides information about the field currently being resolved.
- **GraphqlErrorBuilder.newError(environment)** creates an error bound to the current execution environment.
- **ErrorType.NOT_FOUND** classifies the error under a public group.
- **message** is a safe message intended for the client.
- **extensions** contains a stable application-defined error code.

When bookService.findById throws BookNotFoundException, Spring finds the matching handler and forwards the returned GraphQLError to GraphQL execution.

### When to use a local handler?

A local handler is useful when:

- The exception only occurs in one group of resolvers.
- The same exception class is represented differently depending on the controller context.
- The controller needs to add field-specific information to the error.
- You want to keep it close to the resolver so readers clearly see the relationship between the use case and the error.

If multiple controllers need the same handling rules, consider a global handler.

## 3. Global exception handlers with @ControllerAdvice

**@ControllerAdvice** lets you place **@GraphQlExceptionHandler** methods in a component shared across multiple annotated controllers.

For example:

~~~java
@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book not found")
                .extensions(Map.of("code", "BOOK_NOT_FOUND"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You do not have permission to perform this action")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

Spring detects **@ControllerAdvice** as a shared handler component for annotated controllers. When a matching exception is thrown during field resolution, the framework can locate the corresponding global handler.

### Choosing the scope of application

If the application has multiple GraphQL controllers or business modules, you can narrow the scope of @ControllerAdvice using Spring's controller selection attributes, such as package or controller type. This avoids applying an error rule to controllers outside the intended scope.

Global handlers are suitable for errors with shared semantics:

- Resource does not exist.
- User lacks sufficient permissions.
- Invalid input data at the business layer.
- Standardized domain errors.

Do not lump every exception into a single global handler and return exception.getMessage() verbatim to the client.

## 4. Local handlers vs. global handlers

The two declaration styles have different scopes:

| Criterion | Inside @Controller | Inside @ControllerAdvice |
|---|---|---|
| Scope | The controller containing the handler | Controllers within the advice's scope |
| Use when | Rules specific to one controller | Shared rules |
| Code organization | Close to resolvers | Centralized in advice layer |
| Customization per use case | Convenient | Can use exception type or metadata |
| Reusability | Lower | Higher |

When both a local handler and a global handler exist, the local handler takes precedence for its owning controller; the global handler handles shared cases. If more granular rules are needed, design clear exception types and appropriate advice scopes rather than relying on arbitrary ordering.

## 5. How does Spring select an exception handler?

A handler method must declare the exception type it handles through its exception parameter. Spring searches for a handler capable of accepting the thrown exception based on exception type and handler scope.

For example:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleBookNotFound(
        BookNotFoundException exception,
        DataFetchingEnvironment environment) {
    // ...
}
~~~

The method above explicitly declares BookNotFoundException. A handler can accept a supertype like RuntimeException or Exception, but an overly broad handler can easily obscure the meaning of specific errors.

Prefer:

- Specific domain exceptions for expected business scenarios.
- Appropriate security exceptions for authorization.
- Separate handlers for errors requiring different codes and messages.
- A final fallback handler for unexpected errors, with a generic message and internal logging.

Do not create multiple handlers with ambiguous signatures that can all match the same exception without understanding the framework's precedence rules. When an exception hierarchy exists, use specific types and organize handlers predictably.

## 6. Building GraphQLError with GraphqlErrorBuilder

**GraphQLError** is GraphQL's error structure. A GraphQL response can contain both data and errors simultaneously.

An error typically has the following components:

| Component | Meaning |
|---|---|
| message | Error message |
| locations | Field position in the GraphQL document if available |
| path | Path to the failing field in the response |
| extensions | Additional metadata such as error code or classification |

Spring for GraphQL uses GraphQL Java, so errors can be constructed with **GraphqlErrorBuilder**.

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.NOT_FOUND)
        .message("Book not found")
        .extensions(Map.of(
                "code", "BOOK_NOT_FOUND",
                "resource", "Book"))
        .build();
~~~

newError(environment) attaches location and path information matching the field currently being resolved. This is important when the same resolver is called multiple times in a list or nested field.

### Error type

Spring for GraphQL provides common error categories via **org.springframework.graphql.execution.ErrorType**, for example:

| ErrorType | Common meaning |
|---|---|
| BAD_REQUEST | Invalid request or input data |
| UNAUTHORIZED | Unauthenticated or missing valid credentials |
| FORBIDDEN | Authenticated but not permitted to perform the action |
| NOT_FOUND | Resource not found |
| INTERNAL_ERROR | Unexpected system error |

Error type is the classification of the GraphQL error. It does not automatically dictate the HTTP status code of the entire response. GraphQL over HTTP has its own transport rules; an operation can return HTTP 200 while having errors in the body.

## 7. Using extensions for a stable error contract

Do not force clients to parse the message to determine the error type. Messages may change by language or phrasing.

Provide a stable error code in extensions:

~~~java
return GraphqlErrorBuilder.newError(environment)
        .errorType(ErrorType.BAD_REQUEST)
        .message("Book title must not be blank")
        .extensions(Map.of(
                "code", "BOOK_TITLE_REQUIRED",
                "field", "title"))
        .build();
~~~

Response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Book title must not be blank",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "BOOK_TITLE_REQUIRED",
        "field": "title"
      }
    }
  ]
}
~~~

Keys in extensions are a contract designed by the application. Standardize key names, data types, and error codes across controllers so clients can handle them consistently.

You can use an internal enum for error codes to avoid typos:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    BOOK_TITLE_REQUIRED,
    FORBIDDEN,
    INTERNAL_ERROR
}
~~~

When emitting a GraphQL response, convert the enum into a stable string. Do not use Java exception class names as public error codes, because internal code refactoring could break the API.

## 8. Error path and location

A GraphQL error can specify:

- **path**: the field position in response data.
- **locations**: the field position in the GraphQL document.

Example client query:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

If resolving author for the second item fails, path might look like:

~~~json
{
  "path": ["books", 1, "author"]
}
~~~

Path helps the client identify the exact failing field, even when the resolver is invoked for multiple objects in a list.

When building an error with GraphqlErrorBuilder.newError(environment), the builder can obtain path and source location from DataFetchingEnvironment. This is convenient when the exception arises within a specific field.

For errors occurring before DataFetchers run, such as document parsing or schema validation, path may not exist because no specific field execution has started.

## 9. Distinguishing execution exceptions from parse, validation, and coercion errors

**@GraphQlExceptionHandler** primarily handles exceptions thrown while a DataFetcher/resolver is executing. Not every GraphQL error passes through an annotated exception handler.

| Error group | Example | Does it pass through @GraphQlExceptionHandler? |
|---|---|---|
| Resolver/service exception | BookNotFoundException from service | Yes, if the exception is thrown during field execution |
| Domain error from repository/service | State does not allow update | Possibly, if the exception escapes the resolver |
| Syntax error | Missing bracket in document | No, occurs while parsing document |
| Schema validation error | Field does not exist on type | No, occurs before resolver |
| Variable coercion error | Passing String to Int! variable | No, usually rejected before field execution |
| Transport error | Malformed or unreadable HTTP body | Does not necessarily go through GraphQL exception handler |

Example parse error:

~~~graphql
query {
  book(id: "book-01"
}
~~~

The GraphQL parser cannot build a valid operation, so the book controller is never called.

Example validation error:

~~~graphql
query {
  book(id: "book-01") {
    unknownField
  }
}
~~~

If unknownField does not exist in the schema, GraphQL validation rejects the operation before the resolver executes.

Therefore, do not rely on @GraphQlExceptionHandler to customize all syntax or schema validation errors. Those belong to the GraphQL parse/validation stage and require corresponding handling at the execution/transport layer.

## 10. Distinguishing GraphQL errors from payload userErrors

A mutation can choose to return business errors in its payload:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

The two representations serve different purposes:

| Payload userErrors | GraphQL top-level errors |
|---|---|
| Expected business errors that the client can handle as a result | Errors during GraphQL execution or operation processing |
| Located inside data.createBook.userErrors | Located in the response's errors array |
| Resolver still returns a normal payload | Field may receive null and the error is recorded |
| Suited for mutation validation/domain outcomes | Suited for exceptions not represented as business results |

For example, a book title already in use can be a userError if the mutation contract is designed that way. A database connection failure or unexpected bug should go through GraphQL error handling and not be turned into a fake userError.

@GraphQlExceptionHandler converts exceptions into top-level GraphQLError instances. It does not automatically create or populate a userErrors field in the payload. If the API wants validation errors in the payload, the service/controller must explicitly return the payload according to the contract.

## 11. Protecting sensitive information when mapping exceptions

Do not return the raw exception message to the client:

~~~java
@GraphQlExceptionHandler
public GraphQLError handle(Exception exception,
                           DataFetchingEnvironment environment) {
    return GraphqlErrorBuilder.newError(environment)
            .message(exception.getMessage())
            .build();
}
~~~

The snippet above can expose:

- SQL or table/column names.
- Internal file paths and directory structures.
- Hostnames, service addresses, or infrastructure details.
- Tokens, credentials, or user data.
- Stack traces and implementation details.

Return a safe public message while logging the detailed exception on the server:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleUnexpected(
        RuntimeException exception,
        DataFetchingEnvironment environment) {

    log.error("Unexpected GraphQL resolver error", exception);

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.INTERNAL_ERROR)
            .message("An error occurred while processing the request")
            .extensions(Map.of("code", "INTERNAL_ERROR"))
            .build();
}
~~~

In production, avoid logging credentials or full sensitive inputs. Include a correlation ID/trace ID to link logs without putting stack traces in the response.

## 12. Do not catch all exceptions as the same error type

A handler for Exception or Throwable can act as a safety net for unexpected errors, but it should not replace specific domain handlers.

For example:

- BookNotFoundException → NOT_FOUND.
- AccessDeniedException → FORBIDDEN.
- Recognized business validation error → BAD_REQUEST.
- Unexpected error → INTERNAL_ERROR.

If everything returns BAD_REQUEST, clients will misinterpret system failures as input mistakes. If everything returns INTERNAL_ERROR, clients cannot distinguish a missing resource from an infrastructure outage.

Map errors according to their semantics, not merely by package name or exception class.

### Do not hide the original cause

When catching an exception to wrap it into a domain exception, preserve the cause for logging and investigation:

~~~java
throw new BookPersistenceException(
        "Unable to save book",
        originalException);
~~~

The public handler returns only a safe message and code. The full cause remains in server logs.

## 13. Null propagation when a field resolver throws an exception

A GraphQL response depends on schema nullability. If a field resolver throws an exception and it is converted into a GraphQLError, the failing field is treated as unresolvable.

Schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: Author!
}
~~~

If Book.author is non-null yet the author resolver raises an error, GraphQL cannot place null in that field while upholding the contract. Null can propagate up to the Book object, and continue bubbling through non-null parent fields.

If author is nullable:

~~~graphql
type Book {
  id: ID!
  author: Author
}
~~~

GraphQL can preserve Book and only set author to null while adding the error to the response.

Example response with partial data:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author not found",
      "path": ["book", "author"],
      "extensions": {
        "code": "AUTHOR_NOT_FOUND"
      }
    }
  ]
}
~~~

When designing the schema, choose nullability based on failure likelihood and domain semantics. Exception handlers cannot disable GraphQL's non-null propagation rules.

## 14. Handling security errors

Certain security-related exceptions can occur when a resolver calls a service or hits method security.

For example:

~~~java
@GraphQlExceptionHandler
public GraphQLError handleAccessDenied(
        AccessDeniedException exception,
        DataFetchingEnvironment environment) {

    return GraphqlErrorBuilder.newError(environment)
            .errorType(ErrorType.FORBIDDEN)
            .message("You do not have permission to perform this action")
            .extensions(Map.of("code", "FORBIDDEN"))
            .build();
}
~~~

Not every unauthenticated request goes through this handler. Security filters may reject requests before GraphQL execution starts; field authorization may also be handled in other layers.

Distinguish between:

- **UNAUTHORIZED**: authentication is required or credentials are invalid.
- **FORBIDDEN**: the principal is authenticated but lacks permission.

Messages should not disclose whether a resource exists if that leaks data. For some use cases, returning the same message for both not found and forbidden is an intentional security decision.

## 15. Testing @GraphQlExceptionHandler with GraphQlTester

GraphQlTester can verify the GraphQL response when a resolver throws an exception and a handler converts it into a GraphQLError.

For example:

~~~java
@SpringBootTest
class BookExceptionHandlerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnNotFoundGraphQlError() {
        graphQlTester.document("""
                query {
                    book(id: "missing-book") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .expect()
            .message("Book not found")
            .verify();
    }
}
~~~

You should also test:

1. Specific domain exceptions are mapped to the right error type.
2. Local handlers apply to their corresponding controller.
3. Global handlers handle exceptions across multiple controllers.
4. Error path points to the currently executing field.
5. Error location is preserved when DataFetchingEnvironment is provided.
6. Extensions contain a stable error code.
7. AccessDeniedException returns an error consistent with policy.
8. Unexpected exceptions return a generic message without exposing stack traces.
9. Partial data and null propagation match the schema.
10. Parse/validation errors are not confused with resolver exceptions.

If you need to verify path and extensions, you can inspect the errors list in the response:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing-book") {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error -> {
        assertThat(error.getPath()).containsExactly("book");
        assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND");
    });
});
~~~

Specific testing API method names may vary across Spring for GraphQL versions; use the GraphQlTester API from your application's dependency version. What matters is verifying message, path, extensions, and data.

## 16. Common pitfalls when using @GraphQlExceptionHandler

| Symptom | Possible cause | Solution |
|---|---|---|
| Handler is not called | Exception occurred before resolver or outside handler scope | Identify the stage where the error occurred |
| Local handler does not handle other controllers | Handler only lives in the current controller | Use @ControllerAdvice if shared scope is needed |
| Error path is missing | Creating GraphQLError without execution environment | Use GraphqlErrorBuilder.newError(environment) |
| Client receives internal message | Returning exception.getMessage() directly | Use public messages and log details on the server |
| All errors become INTERNAL_ERROR | Handler is overly broad | Create mappings for specific domain exceptions |
| Validation syntax errors bypass handler | Parse/validation runs before DataFetcher | Use error handling at the appropriate layer |
| More data disappears than expected | Non-null field triggers null propagation | Review nullability and semantics |
| Client depends on message text | No stable error code | Put codes in extensions |
| HTTP status differs from ErrorType | Confusing GraphQL error classification with HTTP status | Handle transport status per GraphQL over HTTP rules |
| Security error leaks resource existence | Messages distinguish too specifically | Standardize messages according to the threat model |

## 17. Workflow for implementing @GraphQlExceptionHandler

When mapping exceptions to GraphQL errors:

1. Determine whether the exception arises in the resolver, service, or before GraphQL execution.
2. Create specific exception types for the domain errors to be handled.
3. Choose a local handler in @Controller or a shared handler in @ControllerAdvice.
4. Declare the exception type the method handles.
5. Accept DataFetchingEnvironment if path and location are needed.
6. Use GraphqlErrorBuilder to construct GraphQLError.
7. Choose an ErrorType matching the error semantics.
8. Set a safe public message and a stable code in extensions.
9. Log the original exception on the server with an appropriate correlation ID.
10. Verify nullability and partial data after a field throws an error.
11. Write GraphQlTester tests for local/global handlers, path, extensions, and security.
12. Separately test parse, validation, and variable coercion errors because they do not pass through resolver exception handlers.

@GraphQlExceptionHandler helps Spring for GraphQL convert exceptions during field resolution into structured GraphQLError responses. Local handlers fit controller-specific rules; @ControllerAdvice fits shared rules. When building errors, preserve path/location, classify errors by semantics, provide stable codes in extensions, and protect internal details. Also remember that this annotation handles exceptions at the field execution stage; parse, validation, and coercion errors belong to earlier stages. Testing both error responses and partial data keeps the error contract clear and consistent.
