# @GraphQlTest

In Spring Boot, `@GraphQlTest` is the test slice for the GraphQL layer of an application. This annotation creates a Spring test context with the required GraphQL infrastructure, loads the schema and selected GraphQL controllers, and auto-configures a `GraphQlTester` to send documents and assert responses.

The goal of `@GraphQlTest` is to verify how a GraphQL operation is handled at the controller layer and GraphQL runtime: whether fields are mapped properly, arguments are bound accurately, responses match the expected structure, and errors are translated into GraphQL errors according to contract. Services and repositories are typically replaced with mocks so tests stay focused on the GraphQL boundary.

`@GraphQlTest` does not start an HTTP server and does not test HTTP transport. When you need to verify endpoints, security filters, headers, status codes, or real connections, use an integration test with `@SpringBootTest` and the appropriate tester.

## 1. What is a test slice?

A typical test using `@SpringBootTest` can load nearly the entire application context: controllers, services, repositories, database configuration, security, transport, and many other beans. This is useful for integration tests, but it makes controller tests slower and dependent on many components.

A test slice loads only the subset of the application relevant to the testing goal. `@GraphQlTest` focuses on the GraphQL infrastructure and the components involved in executing GraphQL requests.

~~~mermaid
flowchart TD
    A[Test class with @GraphQlTest] --> B[Spring test context]
    B --> C[GraphQL auto-configuration]
    B --> D[GraphQL schema and runtime wiring]
    B --> E[Selected GraphQL controllers]
    B --> F[GraphQlTester]
    E --> G[Mock service / imported test bean]
    F --> H[GraphQL document]
    H --> I[GraphQL execution]
    I --> J[Response: data and errors]
~~~

This approach lets you verify the contract between the GraphQL schema and controllers without starting a server or connecting to a real database.

## 2. Required dependencies

Spring GraphQL provides a test module containing `GraphQlTester`. With Spring Boot 3.x, you can add the following dependency to Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Or Gradle:

~~~gradle
dependencies {
    // Spring Boot 3.x
    testImplementation("org.springframework.graphql:spring-graphql-test")

    // Spring Boot 4.x: use the Boot test starter instead
    // testImplementation("org.springframework.boot:spring-boot-starter-graphql-test")
}
~~~

If using `HttpGraphQlTester` with `WebTestClient` in HTTP tests, the WebFlux test client is required on the test classpath if the application does not already include the corresponding dependency.

Spring Boot 4 splits test support into technology-specific modules. You can use the `spring-boot-starter-graphql-test` starter in test scope; this starter brings Spring's GraphQL test support onto the classpath. When using Spring Boot's dependency management, you do not need to specify versions for managed dependencies manually.

The annotation package name also changes between major versions:

| Version | `@GraphQlTest` Import |
| --- | --- |
| Spring Boot 3.x | `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest` |
| Spring Boot 4.x | `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest` |

Check your project's Spring Boot version before copying the import. `GraphQlTester` remains in the `org.springframework.graphql.test.tester` package.

## 3. What does @GraphQlTest auto-configure?

`@GraphQlTest` auto-configures the Spring GraphQL infrastructure and tester needed for tests. Beans included in the context typically consist of:

- `@Controller` and the specified GraphQL controllers.
- `@ControllerAdvice` for controller exception handling.
- `RuntimeWiringConfigurer` for registering runtime wiring.
- Relevant converters and JSON components.
- `DataFetcherExceptionResolver`.
- `Instrumentation`.
- `GraphQlSourceBuilderCustomizer`.
- GraphQL schema/runtime and `GraphQlTester`.

The exact list depends on the Spring Boot version. Regular beans such as `@Service`, `@Repository`, and `@Component` are not automatically scanned in this test slice. This is why a controller that depends on a service is usually paired with `@MockitoBean` or an imported test configuration.

`@GraphQlTest` also does not create an HTTP server. GraphQL requests are sent directly into the GraphQL execution infrastructure inside the test context.

## 4. Specifying controllers to test

You should explicitly specify controllers in the annotation so the context loads only the required GraphQL components:

~~~java
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;

@GraphQlTest(BookController.class)
class BookControllerTests {
    // tests
}
~~~

For Spring Boot 4, update the import to the new package:

~~~java
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
~~~

If you omit the controller list, the test slice may load all discovered GraphQL controllers into the context. This is convenient when testing multiple collaborating resolvers, but it can enlarge the test context and pull in unrelated dependencies.

You can specify multiple controllers:

~~~java
@GraphQlTest({
    BookController.class,
    AuthorController.class
})
class BookAndAuthorGraphQlTests {
}
~~~

Select controllers around a cohesive group of behaviors. If a test only targets book queries, there is no need to load controllers for accounts or payments.

## 5. Schema and controller example

Suppose the application has the following SDL schema in its GraphQL resource directory:

The default schema is typically placed under `src/main/resources/graphql/`, such as `src/main/resources/graphql/schema.graphqls`. If the application customizes schema locations, the test context must use that same configuration.

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

The controller handling the query:

~~~java
package com.example.graphql.book;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

The returned DTO:

~~~java
package com.example.graphql.book;

public record BookView(String id, String title) {
}
~~~

The service collaborator of the controller:

~~~java
package com.example.graphql.book;

public interface BookService {
    BookView findById(String id);
}
~~~

In a slice test, the objective is to verify that the GraphQL field `book` invokes the right controller method, binds the `id` argument accurately, and transforms the returned data into a schema-compliant response.

## 6. Writing your first test with @GraphQlTest

Example testing a query with `GraphQlTester` and mocking the service using `@MockitoBean`:

~~~java
package com.example.graphql.book;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookById() {
        when(bookService.findById("book-42"))
            .thenReturn(new BookView("book-42", "Spring GraphQL"));

        GraphQlTester.Response response = graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-42")
            .execute();

        response.path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");

        response.path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");

        verify(bookService).findById("book-42");
    }
}
~~~

In this test:

1. `@GraphQlTest(BookController.class)` creates a GraphQL test context focused solely on the selected controller.
2. `@MockitoBean` replaces the `BookService` bean with a Mockito mock in the context.
3. `GraphQlTester` sends the GraphQL document like a real operation.
4. `variable("id", "book-42")` passes the variable to the document.
5. `path("book.id")` reads the corresponding field under the `data` section of the GraphQL response.
6. `verify` confirms the controller called the service with the expected ID.

This example uses `@MockitoBean` from Spring Framework 6.2+ (Spring Boot 3.4+). On older projects, you can use Spring Boot's `@MockBean`; that annotation has been superseded and deprecated in newer versions.

## 7. How does GraphQlTester work?

`GraphQlTester` provides a unified workflow for sending requests and asserting responses. Common steps look like this:

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
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Key operations:

| API | Purpose |
| --- | --- |
| `document(String)` | Provide a GraphQL document inline |
| `documentName(String)` | Load a document from test resources by name |
| `variable(name, value)` | Assign a value to a GraphQL variable |
| `operationName(String)` | Select an operation in a document containing multiple operations |
| `execute()` | Execute the query/mutation and return a response |
| `executeAndVerify()` | Execute and verify the response contains no GraphQL errors |
| `path(String)` | Select a path within the data section |
| `entity(Class)` | Convert the node to a Java entity for assertions |
| `entityList(Class)` | Convert a list of nodes to a Java list |
| `errors()` | Inspect errors in the GraphQL response |

Paths in `path` are evaluated relative to the `data` section of the response by default, so no `data.` prefix is needed. You can use JsonPath expressions such as `books[*].title` to assert across multiple elements.

## 8. Passing variables and verifying arguments

Prefer GraphQL variables when testing arguments, especially for input objects or long documents:

~~~java
@Test
void findsBookUsingVariable() {
    when(bookService.findById("book-7"))
        .thenReturn(new BookView("book-7", "GraphQL in Practice"));

    graphQlTester.document("""
            query FindBook($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", "book-7")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
}
~~~

If a variable is missing, has the wrong type, or violates nullability in the SDL, the GraphQL engine can reject the request before the resolver runs. Tests can verify coercion/validation errors without even invoking the service.

For mutation input objects, pass a matching map:

~~~java
import java.util.Map;

graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
        "title", "Spring for GraphQL",
        "isbn", "9780000000000"
    ))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Tests must mock or import the collaborators used by the controller. If a mutation causes side effects, verify that the service receives the expected command and is invoked only the intended number of times.

## 9. Testing mutations

Example controller with a mutation to create a book:

~~~java
@MutationMapping
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

A test can verify input binding and output:

~~~java
import java.util.Map;

@Test
void createsBook() {
    CreateBookInput input =
        new CreateBookInput("Spring for GraphQL", "9780000000000");

    when(bookService.create(input))
        .thenReturn(new BookView("book-99", "Spring for GraphQL"));

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
            "title", "Spring for GraphQL",
            "isbn", "9780000000000"
        ))
        .execute()
        .path("createBook.id")
        .entity(String.class)
        .isEqualTo("book-99");

    verify(bookService).create(input);
}
~~~

This example assumes `CreateBookInput` is a two-field record and the controller accepts the corresponding DTO. Mockito compares records by value; if using a mutable class without an appropriate `equals` implementation, you can use `argThat` or `ArgumentCaptor` to inspect the fields.

If a mutation returns no meaningful data and you only need to verify that the operation succeeded without errors, use `executeAndVerify()`. If you need to inspect the payload or errors, use `execute()` and assert each path.

## 10. Checking GraphQL errors

GraphQL execution can return a response containing partial `data` alongside `errors`. When you want to verify that an error is the expected outcome, use `errors().expect(...)`:

~~~java
@Test
void returnsGraphQlErrorWhenBookDoesNotExist() {
    when(bookService.findById("missing"))
        .thenThrow(new BookNotFoundException("missing"));

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
        .expect(error -> error.getMessage().contains("Book not found"))
        .verify();
}
~~~

This example assumes the test context has a `@ControllerAdvice` or `DataFetcherExceptionResolver` that maps `BookNotFoundException` to a `Book not found` message. If the application has no such handler, assert the actual error code or classification instead of assuming the raw exception message is always sent verbatim to the client.

You can check error codes in `extensions` or `path` if your application's error handler provides them. Avoid matching exclusively against full message strings if wording or locale may change; stable error codes are generally better suited for client contracts.

If a response contains an expected error while still needing assertions on partial data, filter or expect the error before reading paths:

~~~java
graphQlTester.document(query)
    .execute()
    .errors()
    .expect(error -> error.getMessage().contains("Author unavailable"))
    .verify()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

`verify()` confirms that no unhandled errors remain. If you want to inspect multiple errors with a single consumer, you can use `errors().satisfy(...)` to assert the list and mark them as handled.

## 11. Loading GraphQL documents from files

When queries are long or reused across multiple tests, place the documents in test resources instead of writing them inline.

Example directory layout:

~~~text
src
└── test
    └── resources
        └── graphql-test
            ├── findBook.graphql
            └── createBook.graphql
~~~

Contents of `findBook.graphql`:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Use `documentName` to load the file:

~~~java
graphQlTester.documentName("findBook")
    .variable("id", "book-42")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-42");
~~~

By default, `GraphQlTester` looks for documents under `graphql-test/` on the classpath with the `.graphql` or `.gql` extension. This keeps tests readable, separates query fixtures from assertions, and enables fragment reuse.

When using separate fragment files, you can add fragments via the corresponding request spec API. Make sure fragments declare the proper type condition and do not collide with other fragment names in the document.

## 12. Importing additional beans and test configuration

If a controller requires a bean that is not automatically loaded by the test slice, you can use `@Import`:

~~~java
@GraphQlTest(BookController.class)
@Import(BookTestConfiguration.class)
class BookControllerTests {
}
~~~

`BookTestConfiguration` can provide a test bean, a `RuntimeWiringConfigurer`, or additional configuration needed by the GraphQL runtime.

If you need to configure properties, use the annotation's `properties` attribute:

~~~java
@GraphQlTest(
    controllers = BookController.class,
    properties = {
        "app.graphql.feature-enabled=true"
    }
)
class BookControllerTests {
}
~~~

If the application uses `@ConfigurationProperties`, the test slice does not automatically scan every configuration bean. You can use `@EnableConfigurationProperties` for the required classes or import the corresponding configuration.

Do not import the entire application configuration just to make a mocked service appear. Doing so can turn a slice test into a large, hard-to-control context. Use `@MockitoBean` for collaborators that need replacement and `@Import` only for genuinely required GraphQL configuration.

## 13. Testing nested fields and resolver mappings

`@GraphQlTest` is well suited for testing nested field resolvers, such as querying a book along with its author:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

The controller can handle both the root query and the author field:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findByBookId(book.id());
    }
}
~~~

A test GraphQL document can select both `book` and `author` to verify that the GraphQL runtime invokes the right resolver for each field:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                author {
                    id
                    name
                }
            }
        }
        """)
    .execute()
    .path("book.author.name")
    .entity(String.class)
    .isEqualTo("Ada Lovelace");
~~~

Mock the services used by both the root query and the nested resolver. Field declarations, constructors, and dependency injection in the controller are omitted here to keep the focus on the resolvers. This test verifies GraphQL mapping across multiple fields; it does not prove database query performance or DataLoader batching in a real environment. For batching, you can verify that the batch loader is called with the expected set of keys using a mock/spy or write a dedicated test for the DataLoader.

## 14. What @GraphQlTest does not test

`@GraphQlTest` does not start an HTTP server or establish WebSocket connections. Therefore, it is not suitable for verifying:

- Whether an HTTP route such as `/graphql` is registered properly.
- HTTP status codes, request headers, or response headers.
- CORS, CSRF, servlet filters, or the WebFlux security filter chain.
- WebSocket handshakes, `connection_init`, or real transport lifecycles.
- RSocket routes, metadata, and TCP/WebSocket connections.
- Reverse proxies, TLS, or network configuration.
- Real database queries when services/repositories are mocked.
- Full integration across all production beans.

A GraphQL operation succeeding in a slice test does not prove that the HTTP endpoint is reachable by clients. It only proves that GraphQL execution within the test context behaves as configured.

## 15. When to use @SpringBootTest instead of @GraphQlTest?

Use `@SpringBootTest` when you need to test multiple layers working together or want to verify transport behavior. For HTTP integration tests, you can start the server on a random port and use `HttpGraphQlTester`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookGraphQlIntegrationTests {

    @Test
    void queriesBook(@Autowired HttpGraphQlTester graphQlTester) {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }
}
~~~

The package for `@AutoConfigureHttpGraphQlTester` also changes between Spring Boot major versions. Use the package corresponding to your project's Boot version.

For a mock web environment test, you can combine `@AutoConfigureHttpGraphQlTester` with `@SpringBootTest(webEnvironment = MOCK)` if you want to test the HTTP handler without opening a real port. With a live server, `RANDOM_PORT` tests both the server and transport over the assigned port.

Choose the scope based on your goal:

| Goal | Appropriate test approach |
| --- | --- |
| GraphQL field mapping and argument binding | `@GraphQlTest` |
| GraphQL errors and controller advice | `@GraphQlTest` |
| Input coercion, schema validation, and response shape | `@GraphQlTest` |
| Controller calls the right service | `@GraphQlTest` + `@MockitoBean` |
| HTTP route, headers, and status | `@SpringBootTest` + `HttpGraphQlTester` |
| Security filter chain and HTTP authentication | `@SpringBootTest` with security configuration |
| WebSocket subscription transport | `WebSocketGraphQlTester` with an appropriate WebSocket server/handler |
| Real database and repositories | Integration test with appropriate persistence configuration |

## 16. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Service not found when creating test context | `@Service` is not scanned in the GraphQL slice | Use `@MockitoBean` or `@Import` |
| Cannot inject `GraphQlTester` | Missing GraphQL test dependency or test auto-configuration | Add the appropriate test module and check Boot version |
| `@GraphQlTest` does not pick up controller | Controller is not specified or falls outside scan scope | Pass the class to the annotation |
| Schema cannot find field | Schema resource is not at the configured location or SDL is wrong | Check schema resources and GraphQL field definitions |
| Query errors before reaching resolver | Document validation or variable coercion failed | Check field names, arguments, scalars, and nullability |
| Mock service is never called | Wrong query field, resolver not loaded, or response failed before execution | Check schema, controller selection, and `errors()` |
| Expected HTTP test has no status code | `@GraphQlTest` does not run HTTP transport | Use `@SpringBootTest` with an HTTP tester |
| GraphQL error causes assertion failure | Test has not asserted or filtered expected errors | Use `errors().expect(...)` or `satisfy(...)` |
| Test context loads too many beans | Controllers not restricted or overly broad configuration imported | Specify controllers and mock collaborators |
| Wrong `@GraphQlTest` import | Package changed between Boot 3 and Boot 4 | Check package for your major version |
| Mutation test calls service multiple times | Operation or test setup triggers multiple executions | Verify the document and invocation count with Mockito |

## 17. Checklist for writing tests with @GraphQlTest

- Have you selected the right controllers to test?
- Is the SDL schema loaded in the test context and do fields/arguments match the controller?
- Are collaborators such as services replaced with `@MockitoBean` or appropriate imports?
- Is `GraphQlTester` injected and used to send documents?
- Does the test verify both returned data and required service invocations?
- Are variables and input objects passed with the right GraphQL types?
- Are GraphQL errors explicitly asserted rather than ignored?
- Are nested field resolvers and controller advice tested if in scope?
- Does the test avoid assuming that HTTP transport, security filters, or a real database ran?
- Do HTTP/WebSocket/RSocket requirements have dedicated integration tests?
- Do imports and test dependencies match the Spring Boot major version?

`@GraphQlTest` enables testing GraphQL controllers in a lean Spring context that includes schema/runtime and `GraphQlTester` without starting a server. Specify the controllers, mock collaborators with `@MockitoBean`, and send documents through `GraphQlTester` to verify field mapping, argument binding, responses, and errors. When you need to verify HTTP transport, security, WebSocket, or a real database, switch to integration tests with the appropriate tester and environment.

## References

- [Spring Boot — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 3 — GraphQlTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/graphql/GraphQlTest.html)
- [Spring Boot 4 — GraphQlTest API](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/graphql/test/autoconfigure/GraphQlTest.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
