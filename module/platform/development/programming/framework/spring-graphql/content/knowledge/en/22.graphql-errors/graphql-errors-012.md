# Partial data and errors in Spring for GraphQL

A GraphQL operation can return data for fields that resolved successfully while also returning errors for fields that failed. This is a key characteristic of GraphQL: an error during the execution of one field does not necessarily break the entire query. A response can contain both `data` and `errors`; clients need to inspect both to know which parts of the data are usable and which parts are incomplete.

In Spring for GraphQL, exceptions raised from annotated controllers or data fetchers are routed into GraphQL's error handling mechanism. The application can convert exceptions into GraphQL errors using `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`, or explicitly return `DataFetcherResult` when supplying data alongside errors. The final outcome also depends on nullability in the SDL and GraphQL's null propagation rules.

## 1. Why does GraphQL have partial data?

Suppose a library schema has a query that fetches a book along with its author and reviews:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    comment: String!
}
~~~

The client sends:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            comment
        }
    }
}
~~~

Suppose the `book` resolver returns the book and the `reviews` resolver loads the reviews, but the author service fails. Because `Book.author` is nullable, GraphQL can return `author: null` and keep the other fields:

~~~json
{
    "data": {
        "book": {
            "id": "book-1",
            "title": "Spring for GraphQL",
            "author": null,
            "reviews": [
                {
                    "id": "review-1",
                    "comment": "Clear examples"
                }
            ]
        }
    },
    "errors": [
        {
            "message": "Author service is unavailable",
            "locations": [
                { "line": 6, "column": 9 }
            ],
            "path": ["book", "author"]
        }
    ]
}
~~~

The response still has `data` because part of the query executed successfully. `errors` describes the field that could not be resolved. The client can display the title and reviews while indicating that the author section could not be loaded.

## 2. Distinguishing request errors and execution errors

GraphQL errors are typically divided into two groups based on when they occur:

| Error type | Timing | Are resolvers executed? | Response data |
| --- | --- | --- | --- |
| Request error | Parsing document, validating schema, or coercing variables | No | No `data` key |
| Execution error | While a field resolver or value serialization executes | Yes, at least part of the operation | May have partial `data` or `data: null` due to null propagation |

Example request error: the client queries a non-existent field or passes the wrong argument type. GraphQL rejects the operation before running any resolver, so no field data is produced.

Example execution error: the query is valid, the `book` resolver returns data, but the `author` resolver throws an exception. GraphQL records the error in `errors` and processes `data` according to schema nullability.

This explains why `errors` does not mean the entire operation failed. Clients must inspect both `data` and `errors`, rather than relying only on HTTP status or treating every response containing `errors` as having no data.

## 3. GraphQL error structure

An error in a GraphQL response can have the following components:

| Component | Meaning |
| --- | --- |
| `message` | Brief error description for the client |
| `locations` | Line/column position in the GraphQL document related to the error, if determinable |
| `path` | Path to the failing field or list item in the response |
| `extensions` | Additional metadata defined by the implementation or application |

Example error for a child field:

~~~json
{
    "message": "Author is not available",
    "locations": [{ "line": 6, "column": 9 }],
    "path": ["book", "author"],
    "extensions": {
        "code": "AUTHOR_UNAVAILABLE"
    }
}
~~~

`path` uses response key names, so if the client aliases a field, path typically contains that alias. For fields inside a list, path also includes the element index, such as `["books", 2, "author"]`. This helps clients identify the exact missing piece of data.

`extensions` does not have a fixed set of business keys across all applications. Choose a consistent structure, such as `code`, `correlationId`, or `retryable`, and avoid putting stack traces, SQL statements, table names, or internal information into the response.

## 4. Nullability determines how partial data propagates

GraphQL uses `null` to represent a field with no result. When a field fails during execution, GraphQL treats that field's result as `null` and then applies the schema's Non-Null rules.

For a nullable field, an error only turns that field into `null`; sibling fields can still be resolved. For a field with `!`, `null` is invalid, so the error bubbles up to the nearest parent that can accept `null`. This process continues until a nullable field is reached or it hits the root, at which point `data` can become `null`.

For example:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

`author` is nullable, so when its resolver fails, `book.author` becomes `null`; `book.id` and `book.title` are preserved.

If the schema changes to:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

The `author` resolver cannot return `null`. If it fails, null propagates up to `Book`. If the root field `Query.book` is nullable, `data.book` can become `null`, while other root fields in the same operation can still retain their data.

## 5. Null propagation with lists

A list has two independent nullability positions: the list itself and each item.

| SDL | Can list be null? | Can item be null? | If one item resolver fails |
| --- | --- | --- | --- |
| `[Review]` | Yes | Yes | That item becomes `null`, other items remain unchanged |
| `[Review!]` | Yes | No | The entire list becomes `null` |
| `[Review]!` | No | Yes | That item becomes `null`, the list remains |
| `[Review!]!` | No | No | The list becomes `null`, then null continues bubbling up to the parent |

For example, `reviews: [Review!]!` requires both the list and every item to be non-null. If one item cannot be resolved, GraphQL cannot simply set that item to null; the entire list becomes null. Because the `reviews` field is also Non-Null, null continues propagating up to the parent object.

Nullability is therefore part of API reliability design. Choose Non-Null for a field only when the application can guarantee a value always exists in all allowed cases. For relationships depending on external services or data that might be missing, nullable fields often preserve more partial data.

## 6. Resolvers can throw exceptions

An annotated controller can throw an exception when data cannot be loaded:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId())
                .orElseThrow(() -> new AuthorUnavailableException(
                        "Author service is unavailable"
                ));
    }
}
~~~

Exceptions from data fetchers are handled by GraphQL Java as execution errors. Spring for GraphQL provides exception resolver mechanisms to convert exceptions into `GraphQLError` instances with appropriate information.

Do not catch every exception and silently return `null`:

~~~java
// Do not do this: loses error information and leaves the client unaware of why the field is null.
try {
    return authorService.findById(book.authorId()).orElse(null);
}
catch (Exception ex) {
    return null;
}
~~~

If `null` is a valid business outcome, returning null is sufficient. If there is a system or business error that clients need to know about, let the exception enter error handling and preserve the appropriate path and error code.

## 7. Handling exceptions with @GraphQlExceptionHandler

`@GraphQlExceptionHandler` allows handling exceptions inside a controller or inside a `@ControllerAdvice` class. This is a convenient way to map business exceptions into GraphQL errors.

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorUnavailable(
            AuthorUnavailableException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("Author information is temporarily unavailable")
                .extensions(java.util.Map.of(
                        "code", "AUTHOR_UNAVAILABLE"
                ))
                .build();
    }
}
~~~

`GraphqlErrorBuilder.newError(environment)` creates an error bound to the field currently being resolved, enabling GraphQL to populate `locations` and `path`. Spring for GraphQL's `ErrorType` provides standardized error classification; `extensions` lets you add application-specific error codes.

Return a controlled message rather than echoing the raw exception if it contains infrastructure details. The original exception can still be logged on the server with a correlation ID.

## 8. Global error handling with DataFetcherExceptionResolver

When you want to apply shared rules across multiple controllers, you can implement `DataFetcherExceptionResolver`. Spring for GraphQL invokes the resolver when a data fetcher throws an exception.

Example using the adapter to map a known exception:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment
    ) {
        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.NOT_FOUND)
                    .message("Book was not found")
                    .extensions(java.util.Map.of("code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

Returning `null` from `resolveToSingleError` means this resolver does not handle that exception; Spring can forward it to another resolver. If no resolver handles it, the error goes to GraphQL Java/Spring for GraphQL's default handling mechanism.

Choose `@GraphQlExceptionHandler` when logic is tied to a controller or group of controllers. Choose `DataFetcherExceptionResolver` when you want a centralized policy independent of annotated controllers. Avoid registering multiple places handling the same exception under conflicting rules.

## 9. Proactively returning data with errors using DataFetcherResult

Not every situation requires throwing an exception. When a resolver can return data while also wanting to report an error or warning tied to the field, GraphQL Java provides `DataFetcherResult<T>`.

~~~java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;

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
    public DataFetcherResult<Book> book(
            @Argument("id") Long id,
            DataFetchingEnvironment environment
    ) {
        Book book = bookService.findById(id);

        return DataFetcherResult.<Book>newResult()
                .data(book)
                .error(GraphqlErrorBuilder.newError(environment)
                        .message("Some optional book metadata could not be loaded")
                        .extensions(java.util.Map.of("code", "METADATA_UNAVAILABLE"))
                        .build())
                .build();
    }
}
~~~

This example illustrates how to return data alongside errors from a single data fetcher. In a real application, only add an error when there is genuinely an issue the client needs to know about; if optional metadata was not requested by the client or does not affect the response, there is no need to create an error.

`DataFetcherResult` also supports local context and extensions. It is useful when returning a controlled result from a resolver. For ordinary exception failures, there is no need to manually construct `DataFetcherResult`; an exception resolver is more appropriate.

## 10. Partial data when a field inside a list fails

Suppose a query returns multiple books, each with a nullable author:

~~~graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

If the `Book.author` resolver fails for one book, the response can preserve the entire books list while that element's author field is null:

~~~json
{
    "data": {
        "books": [
            {
                "id": "book-1",
                "title": "GraphQL Basics",
                "author": { "id": "author-1", "name": "An" }
            },
            {
                "id": "book-2",
                "title": "Spring GraphQL",
                "author": null
            }
        ]
    },
    "errors": [
        {
            "message": "Author information is temporarily unavailable",
            "path": ["books", 1, "author"]
        }
    ]
}
~~~

Because `Book.author` is nullable, the error affects only the child field of the second element. If `author` were `Author!`, the error would turn the corresponding `Book` element into null; however, `books` is declared `[Book!]!`, making a null item invalid, causing the entire list to become null and continuing to bubble up to the parent.

## 11. Do not use errors to replace normal business outcomes

Not every case with no data is an error. For example:

- Not finding a book by ID can be a valid `null` result if the schema declares `Book` nullable.
- An empty list can be a valid result of a search query.
- A filter returning no matches does not necessarily need a GraphQL error.
- Insufficient access rights must be handled per authorization policy; you can return a `FORBIDDEN` error or conceal the resource's existence depending on security requirements.

Distinguish absence, validation failure, business conflict, and infrastructure failure. If every situation becomes `INTERNAL_ERROR`, clients struggle to choose appropriate behavior and telemetry struggles to categorize issues.

## 12. Designing error codes and extensions

Clients usually need stable codes rather than free-form messages to decide whether to show a retry button, prompt for login, or redirect. You can standardize extensions:

~~~json
{
    "message": "Author information is temporarily unavailable",
    "path": ["book", "author"],
    "extensions": {
        "code": "AUTHOR_UNAVAILABLE",
        "retryable": true,
        "correlationId": "req-123"
    }
}
~~~

Some rules:

1. `code` should be stable and documented.
2. `message` should be client-oriented and contain no internal details.
3. `retryable` should be `true` only if retrying makes sense and is safe.
4. `correlationId` links the response to server logs.
5. Never put tokens, cookies, stack traces, SQL, hostnames, or unnecessary personal data into `extensions`.

Do not force clients to parse `message` text to identify the error type. Messages may be localized or changed; `code` is the right machine-readable contract.

## 13. HTTP status and GraphQL errors

The GraphQL response body and HTTP status address two different layers. A valid operation can execute and return partial `data` along with `errors`; that is usually still a valid GraphQL response at the transport layer.

Do not assume every execution error must turn the HTTP status into 4xx or 5xx. With HTTP GraphQL, status also depends on the error stage, media type, transport, and server configuration. Clients should read the GraphQL response body according to the protocol rather than checking only the status code.

For example, the `author` resolver fails while `book.title` still has data: the client can continue displaying the valid data. Conversely, parse or validation errors occur before execution, so there is no field data to use.

## 14. Testing partial data and errors with GraphQlTester

`GraphQlTester` lets you verify both data and the errors list. Example query with nullable `Book.author`, where the author service throws an exception and exception advice converts it into an error with a stable code.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({BookQueryController.class, BookController.class, GraphQlExceptionAdvice.class})
class PartialDataTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void keepsBookDataWhenAuthorResolverFails() {
        given(bookService.findById(1L))
                .willReturn(new Book(1L, "Spring for GraphQL", 10L));
        given(authorService.findById(10L))
                .willThrow(new AuthorUnavailableException("downstream timeout"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    book(id: 1) {
                        id
                        title
                        author { id name }
                    }
                }
                """)
                .execute();

        response.path("book.title")
                .entity(String.class)
                .isEqualTo("Spring for GraphQL");
        response.path("book.author")
                .valueIsNull();
        response.errors().satisfy(errors -> {
            org.assertj.core.api.Assertions.assertThat(errors).hasSize(1);
            org.assertj.core.api.Assertions.assertThat(errors.get(0).getPath())
                    .containsExactly("book", "author");
        });
    }
}
~~~

This example assumes the SDL schema is loaded and the controllers/advice use the corresponding services. `Book` has constructor `(Long id, String title, Long authorId)`. Depending on Spring Boot 3.x/4.x configuration, the mock bean annotation may be `@MockitoBean` or the version's equivalent mocking mechanism.

You should also test:

1. A nullable field fails while sibling fields still have data.
2. A Non-Null field fails and null propagates up to the expected parent.
3. A list item fails across each type `[T]`, `[T!]`, `[T]!`, `[T!]!`.
4. Request validation errors do not run resolvers.
5. Error codes and extensions are stable and do not leak internal details.
6. Aliases and list indices appear accurately in `path`.
7. `DataFetcherResult` returns data alongside errors as expected.

## 15. Common pitfalls when handling partial data

| Symptom | Cause | Solution |
| --- | --- | --- |
| All `data` becomes null | Non-Null field failed and null propagated to root | Check `!` chains in SDL; use Non-Null only when a value can be guaranteed |
| Field is null with no error | Resolver intentionally returned null or exception was caught and swallowed | Distinguish valid absence from errors; never swallow exceptions unintentionally |
| `errors` present but client ignores them | Client reads only `data` or checks only HTTP status | Handle both `data` and `errors` simultaneously, using `path` to pinpoint failing fields |
| Path does not match SDL field name | Client used an alias or field is inside a list | Read the response path, including aliases and list indices |
| Error message leaks infrastructure | Returning `exception.getMessage()` directly | Use safe messages and stable error codes |
| Exception is not mapped | Exception handler/resolver did not match the type or is not registered | Check `@ControllerAdvice`, `@GraphQlExceptionHandler`, and resolver beans |
| Normal business errors reported as server errors | Using a single generic exception for all situations | Separate not-found, forbidden, validation, and infrastructure failures |
| List becomes null unexpectedly | Item type or list type is declared Non-Null | Review `[T]`, `[T!]`, `[T]!`, `[T!]!` and the data contract |

## 16. Workflow for designing partial data and errors

When designing a GraphQL API with multiple dependent fields:

1. Identify which fields can be missing or fail independently.
2. Choose nullable/Non-Null based on data guarantees, not merely client wishes.
3. Understand null propagation from fields to lists, parents, and root.
4. Use exception handlers or `DataFetcherExceptionResolver` to standardize execution errors.
5. Use `DataFetcherResult` when intentionally returning data together with errors.
6. Standardize `extensions.code` and safe messages for clients.
7. Distinguish request errors from execution errors.
8. Test partial `data`, `errors`, `path`, and null propagation with `GraphQlTester`.
9. Design clients to read both data and errors simultaneously without relying solely on HTTP status.

Partial data is an important capability of GraphQL, enabling clients to still use successful fields when one branch fails. For this behavior to be clear, the schema must use appropriate nullability, the server must attach errors to the right fields, and the client must handle both `data` and `errors`.

## References

- [GraphQL Specification — Response Format](https://spec.graphql.org/October2021/#sec-Response-Format)
- [GraphQL Specification — Handling Field Errors](https://spec.graphql.org/October2021/#sec-Handling-Field-Errors)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers-exceptions)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
