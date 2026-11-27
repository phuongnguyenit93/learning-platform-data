# Writing GraphQlTester Tests for Queries

`GraphQlTester` is the testing API for Spring for GraphQL. It lets you send a GraphQL document, pass variables, execute through the GraphQL engine, and assert responses by path. When testing Queries, we verify that the schema recognizes the right fields and arguments, resolvers are invoked, data is converted properly, and errors are returned according to the GraphQL contract.

This hands-on practice uses a book catalog API with three read operations: fetching the list, finding by ID, and searching by keyword. We will write tests at the GraphQL layer using `@GraphQlTest`, mock the service with Mockito, and then test the HTTP endpoint using `HttpGraphQlTester`.

## 1. Objectives and Testing Scope

After this lesson, you will be able to configure `@GraphQlTest`, send queries with `GraphQlTester`, pass variables, and assert data, nullability, errors, and service invocations.

Tests verify the schema, request, mapping, service calls, response, and errors. When mocking the service, tests focus on the GraphQL flow and resolvers.

## 2. Preparing Dependencies and Schema

With Maven, the required dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Boot dependency management manages versions for these dependencies. `spring-graphql-test` provides `GraphQlTester` and GraphQL testing utilities.

Place the schema at `src/main/resources/graphql/schema.graphqls`:

~~~graphql
type Query {
    books: [Book!]!
    bookById(id: ID!): Book
    searchBooks(keyword: String!): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: String!
    publishedYear: Int!
    price: Float!
}
~~~

Two nullability rules directly affect assertions:

- `bookById` returns a nullable `Book` when the book ID is not found.
- `searchBooks` returns `[Book!]!`, meaning both the list and each element are non-null. When there are no matches, the resolver returns an empty list.

## 3. Preparing the Resolver

Use a Java record to represent data:

~~~java
package com.example.bookcatalog.book;

public record Book(
        String id,
        String title,
        String author,
        int publishedYear,
        double price
) {
}
~~~

Service contract:

~~~java
package com.example.bookcatalog.book;

import java.util.List;
import java.util.Optional;

public interface BookService {
    List<Book> findAll();
    Optional<Book> findById(String id);
    List<Book> searchByKeyword(String keyword);
}
~~~

Resolver:

~~~java
package com.example.bookcatalog.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping(name = "searchBooks")
    public List<Book> search(@Argument("keyword") String keyword) {
        return bookService.searchByKeyword(keyword);
    }
}
~~~

Spring uses the method name as the GraphQL field name if `@QueryMapping` does not specify `name`. For `searchBooks`, the `name` attribute maps the SDL field name to the Java method `search`.

In the test slice, `BookService` is replaced by a mock. We explicitly stub returned data and verify that the resolver passes the right arguments to the service.

## 4. How to Use GraphQlTester

A basic GraphQL test consists of these steps:

1. `document(...)` creates the GraphQL operation.
2. `variable(...)` passes values for variables.
3. `execute()` executes the document.
4. `errors()` checks errors in the response.
5. `path(...)` selects the field to inspect.
6. `entity(...)` or `entityList(...)` converts data into Java types.

Example:

~~~java
graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .execute()
        .errors()
        .verify()
        .path("books[0].id")
        .entity(String.class)
        .isEqualTo("B-101");
~~~

`errors().verify()` confirms the response has no GraphQL errors. `path("books[0].id")` selects the `id` of the first element. `entity(String.class)` converts the value to `String` for assertion.

Paths in `path` are evaluated starting from the `data` section of the response, without needing a `data.` prefix. For a response with `data.books[0].id`, the path to use is `books[0].id`.

`GraphQlTester` commonly uses `path(...)` to select fields, `entity(...)` to read an object or scalar value, `entityList(...)` to read a list, `valueIsNull()` to assert null, and `errors()` to inspect errors.

For queries that select only a few attributes, assert each path individually instead of mapping a partial response into a record with many attributes.

## 5. Writing Tests with @GraphQlTest

`@GraphQlTest` creates a test slice for Spring for GraphQL. Spring configures the schema, GraphQL infrastructure, and the specified controller. Controller dependencies can be replaced with mocks.

~~~java
package com.example.bookcatalog.book;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.graphql.test.tester.GraphQlTester;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@GraphQlTest(BookQueryController.class)
class BookQueryControllerGraphQlTest {

    @Autowired
    private GraphQlTester graphQlTester;

    @MockBean
    private BookService bookService;

    // Place test cases here.
}
~~~

`@GraphQlTest` limits the Spring context to the pieces needed for GraphQL tests. `@MockBean` registers a mock `BookService` so the controller can be instantiated. `GraphQlTester` is configured by Spring Boot and injected into the test.

With newer Spring Framework versions that support `@MockitoBean`, you can use that annotation instead of `@MockBean`.

### 5.1. Testing a List Query

~~~java
@Test
void shouldReturnBooks() {
    Book first = new Book(
            "B-101", "Spring in Action", "Craig Walls", 2022, 39.90
    );
    Book second = new Book(
            "B-102", "Effective Java", "Joshua Bloch", 2018, 45.00
    );

    given(bookService.findAll()).willReturn(List.of(first, second));

    graphQlTester.document("""
            query {
                books {
                    id
                    title
                    author
                    publishedYear
                    price
                }
            }
            """)
            .execute()
            .errors()
            .verify()
            .path("books")
            .entityList(Book.class)
            .containsExactly(first, second);

    verify(bookService).findAll();
}
~~~

The test verifies that the `books` field executes, data is mapped to a list of `Book` in order, and the resolver calls `findAll()`. We select all fields of `Book` so we can compare the record against the fixture data.

If the query only selects a subset of attributes, assert the corresponding paths instead of comparing the full `Book`.

### 5.2. Testing a Query with Variables

When arguments vary per request, use GraphQL variables rather than concatenating values into the query string.

~~~graphql
query BookDetail($id: ID!) {
    bookById(id: $id) {
        id
        title
        author
        publishedYear
        price
    }
}
~~~

~~~java
@Test
void shouldReturnBookById() {
    Book expected = new Book(
            "B-102", "Effective Java", "Joshua Bloch", 2018, 45.00
    );

    given(bookService.findById("B-102"))
            .willReturn(Optional.of(expected));

    graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                    author
                    publishedYear
                    price
                }
            }
            """)
            .variable("id", "B-102")
            .execute()
            .errors()
            .verify()
            .path("bookById")
            .entity(Book.class)
            .isEqualTo(expected);

    verify(bookService).findById("B-102");
}
~~~

`variable("id", "B-102")` supplies the value for `$id`. The GraphQL runtime validates the variable against the `ID!` declaration in the operation. The resolver receives the `id` argument via `@Argument("id")`.

This test catches mismatched variable or argument names, mis-mapped resolver fields, and return types incompatible with the schema.

### 5.3. Testing an Empty List

~~~java
@Test
void shouldReturnEmptyListWhenSearchHasNoResult() {
    given(bookService.searchByKeyword("unknown"))
            .willReturn(List.of());

    graphQlTester.document("""
            query SearchBooks($keyword: String!) {
                searchBooks(keyword: $keyword) {
                    id
                    title
                }
            }
            """)
            .variable("keyword", "unknown")
            .execute()
            .errors()
            .verify()
            .path("searchBooks")
            .entityList(Book.class)
            .hasSize(0);
}
~~~

The query still must select at least one field of `Book` because GraphQL requires a selection set for object types. For an empty list, the assertion only checks the element count, so object comparison is unnecessary.

### 5.4. Testing a Nullable Field

When a book is not found, the service returns `Optional.empty()` and the resolver converts it to `null`. Because the SDL declares `bookById` as nullable, the response is valid:

~~~java
@Test
void shouldReturnNullWhenBookDoesNotExist() {
    given(bookService.findById("UNKNOWN"))
            .willReturn(Optional.empty());

    graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "UNKNOWN")
            .execute()
            .errors()
            .verify()
            .path("bookById")
            .valueIsNull();
}
~~~

Do not use `valueIsNull()` to check a list with zero elements. An empty list and a `null` value are two distinct outcomes under the SDL contract.

### 5.5. Testing GraphQL Errors

A GraphQL response can contain both `data` and `errors`. When a resolver throws an error, the GraphQL engine can return partial data and record the corresponding error in `errors`.

~~~java
@Test
void shouldExposeGraphQlExecutionError() {
    given(bookService.findById("B-500"))
            .willThrow(new IllegalStateException("Book store unavailable"));

    var response = graphQlTester.document("""
            query BookDetail($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "B-500")
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
}
~~~

The test verifies that an execution error appears in the response. The exact message and error code depend on your `DataFetcherExceptionResolver` or exception-handling mechanism. If the API guarantees an error code, assert the public code or extension rather than an internal exception message.

You can test validation errors with a query missing a required argument:

~~~java
@Test
void shouldRejectQueryWithoutRequiredArgument() {
    var response = graphQlTester.document("""
            query {
                bookById {
                    id
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
}
~~~

The query violates `id: ID!` in the schema. The resolver should not be called because GraphQL validation rejects the operation before execution.

## 6. Testing over HTTP with HttpGraphQlTester

`@GraphQlTest` is suitable for testing the schema, resolvers, and how the GraphQL engine processes queries. It does not start the full application over a real HTTP endpoint.

When you need to verify requests going through the web server and the `/graphql` endpoint, use `HttpGraphQlTester` in an integration test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookQueryHttpTest {

    @Autowired
    private HttpGraphQlTester graphQlTester;

    @Test
    void shouldQueryBookThroughHttpEndpoint() {
        graphQlTester.document("query { books { id title } }")
                .execute().errors().verify()
                .path("books[0].id").entity(String.class)
                .isEqualTo("B-101");
    }
}
~~~

`@SpringBootTest` boots the application in the test environment. `RANDOM_PORT` allocates a random HTTP port. `@AutoConfigureHttpGraphQlTester` configures the tester to send requests to the application's GraphQL endpoint.

HTTP tests use the real services and data in the application context. Load a fixture containing book `B-101` in a test profile or test database so assertions have stable data.

| Criterion | `@GraphQlTest` | `HttpGraphQlTester` |
|---|---|---|
| Goal | Schema and resolvers | Integrated HTTP flow |
| Spring context | Test slice | Full application context |
| HTTP server | No real endpoint needed | Server running on random port |
| Speed | Typically faster | Typically slower |
| Best for | Mapping, variables, responses, resolver errors | Endpoint and web configuration |

Use test slices for most resolver tests. Reserve integration tests for behaviors that need verification over HTTP.

## 7. Common Errors

| Symptom | Cause and Resolution |
|---|---|
| Cannot inject `GraphQlTester` | Check `spring-graphql-test` and test annotations. |
| Controller is not instantiated | Include the controller in `@GraphQlTest`'s scope. |
| Cannot inject service | Use `@MockBean` or `@MockitoBean`. |
| Field or variable not found | Cross-check SDL, `@QueryMapping`, `variable(...)`, and `@Argument`. |
| Path missing or error instead of null | Check selection set, path, nullability, and errors. |
| HTTP test cannot connect | Check `@SpringBootTest` and `@AutoConfigureHttpGraphQlTester`. |

Use `errors().verify()` in tests expected to succeed. For tests specifically asserting errors, use `errors().satisfy(...)` to verify errors match expected conditions.

Do not test GraphQL simply by calling controller methods directly. That bypasses schema parsing, field mapping, argument binding, and serialization. Send documents through `GraphQlTester` to properly test the API contract.

## 8. Practice Exercises

Complete the test suite for the book catalog API:

1. Verify `books` returns the expected two items in the exact order.
2. Verify `bookById` using the `id` variable, both when found and when not found.
3. Verify `searchBooks` returns an empty list when there are no matches.
4. Verify execution errors or a query missing a required argument.
5. Use Mockito `verify` and add an HTTP integration test if endpoint verification is needed.

Completion criteria: all `Query` fields have passing tests; variables are passed properly; data, `null`, empty lists, and errors are distinguished; assertions verify exact paths and nullability; services are mocked in resolver tests and the endpoint is tested over HTTP when needed.

As you expand the API, send documents the way real clients do and inspect responses the way real clients receive them. Only mock dependencies outside the test's scope. In doing so, your `GraphQlTester` suite protects the API contract whenever the schema or resolvers change.
