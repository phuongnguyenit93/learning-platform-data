# Asserting Data with GraphQlTester in Spring for GraphQL

`GraphQlTester` provides a fluent API to send a GraphQL operation, select fields in the response, and verify the received data. Instead of comparing the entire JSON response as a string, tests can navigate directly to the target path and assert scalars, objects, lists, null values, or GraphQL errors.

`GraphQlTester` uses a unified workflow across multiple transports. The same assertion style works over HTTP, WebSocket, RSocket, or directly against the in-server GraphQL service. This lesson focuses on asserting returned **data**: whether the data has the right values, right structure, right counts, and right behavior when a field has no data or encounters an error.

## 1. Adding Testing Dependencies

Add the `spring-graphql-test` module in test scope:

~~~groovy
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

When using Spring Boot dependency management, let Boot manage versions compatible with Spring GraphQL. If you are not using Boot's BOM, declare a `spring-graphql-test` version matching your application's `spring-graphql` version.

Some JSON assertions require the JSONassert library on the test classpath. Add this dependency only when using `matchesJson(...)` or the required JSON assertions:

~~~groovy
dependencies {
    testImplementation("org.skyscreamer:jsonassert")
}
~~~

## 2. GraphQlTester Provides a Unified Workflow

A GraphQL test typically follows four steps:

1. Create a tester matching where you want to test.
2. Build a request using `document(...)` or `documentName(...)`.
3. Execute with `execute()`.
4. Select a response path and assert using `entity(...)`, `entityList(...)`, `matchesJson(...)`, or `valueIsNull()`.

~~~mermaid
flowchart TD
    A[GraphQlTester] --> B[document or documentName]
    B --> C[Set variables and headers]
    C --> D[execute]
    D --> E[Inspect errors if expected]
    E --> F[Select path relative to data]
    F --> G[Assert scalar, object, list or JSON]
~~~

Simplest example:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, GraphQL!");
~~~

`path("greeting")` is a path relative to the `data` section of the GraphQL response. You do not need to write `data.greeting`.

## 3. Choosing the Right GraphQlTester Type

`GraphQlTester` is the common contract. Builders differ in the transport or server layer that the test passes through:

| Tester | Testing Scope | When to Use |
| --- | --- | --- |
| `HttpGraphQlTester` | Sends requests over HTTP using `WebTestClient` | Testing GraphQL endpoints and HTTP transport |
| `WebSocketGraphQlTester` | Sends requests over a WebSocket connection | Testing WebSocket and subscriptions |
| `RSocketGraphQlTester` | Sends requests over an RSocket session | Testing RSocket transport and routing |
| `ExecutionGraphQlServiceTester` | Calls `ExecutionGraphQlService` directly | Testing server execution without transport |
| `WebGraphQlTester` | Goes through `WebGraphQlHandler` and interceptor chain | Testing `WebGraphQlInterceptor` with GraphQL execution |

If the goal is solely to assert data returned by resolvers, you can use a server-side tester for fast execution. If you need to verify HTTP headers, status codes, WebSocket, or RSocket routing, use the tester matching that transport.

## 4. Using the Tester in @GraphQlTest

Spring Boot provides `@GraphQlTest` to create a test slice for GraphQL controllers and related components. Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    price: Float!
}
~~~

Controller:

~~~java
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
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookData() {
        given(bookService.findById("book-1"))
                .willReturn(new Book("book-1", "Spring GraphQL", 39.5));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                        price
                    }
                }
                """)
                .variable("id", "book-1")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }
}
~~~

`@GraphQlTest` loads the GraphQL test slice and allows injecting `GraphQlTester`. `@MockitoBean` replaces the service with a mock so the test focuses on argument binding, resolver invocation, and response building. For older Spring Boot versions without `@MockitoBean`, use the mock bean mechanism supported by that Boot version, such as `@MockBean`.

## 5. Asserting Scalars with entity

After selecting a path, use `entity(Class)` to decode the value into a Java type and assert:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, GraphQL!");
~~~

Common scalar types:

~~~java
response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-1");

response.path("book.price")
        .entity(Double.class)
        .isEqualTo(39.5);

response.path("book.available")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

Choose Java types compatible with the scalar and the application's mapping. For example, GraphQL `Float` is typically converted to `Double` in JSON mapping; do not assume every number is an `Integer`.

## 6. Asserting Objects with entity

When the response path is an object, you can decode it into a record or DTO:

~~~java
public record BookView(String id, String title, Double price) {}
~~~

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                id
                title
                price
            }
        }
        """)
        .execute()
        .path("book")
        .entity(BookView.class)
        .satisfies(book -> {
            org.assertj.core.api.Assertions.assertThat(book.id())
                    .isEqualTo("book-1");
            org.assertj.core.api.Assertions.assertThat(book.title())
                    .isEqualTo("Spring GraphQL");
            org.assertj.core.api.Assertions.assertThat(book.price())
                    .isEqualTo(39.5);
        });
~~~

`isEqualTo(expected)` is suitable when comparing the whole object and the class implements `equals` as expected. `satisfies(...)` is suitable when asserting several properties without constructing a full expected object.

`entity(...)` returns an entity assertion object; call `get()` if you need the decoded value for further use in the test. Avoid extracting the value too early if you can assert directly in the fluent chain.

## 7. Asserting Lists with entityList

For scalar lists, choose a JSONPath with the `[*]` wildcard and use `entityList`:

~~~java
graphQlTester.document("""
        {
            books {
                title
            }
        }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .containsExactly("Spring GraphQL", "GraphQL in Action");
~~~

`EntityList` supports common assertions:

~~~java
response.path("books[*].title")
        .entityList(String.class)
        .hasSize(2)
        .contains("Spring GraphQL");

response.path("books[*].title")
        .entityList(String.class)
        .doesNotContain("Unknown Book");
~~~

Useful methods:

| Method | Meaning |
| --- | --- |
| `hasSize(n)` | List has exactly `n` elements |
| `hasSizeGreaterThan(n)` | Element count is greater than `n` |
| `hasSizeLessThan(n)` | Element count is less than `n` |
| `contains(...)` | Contains expected values, regardless of order |
| `containsExactly(...)` | Has the exact values in the exact order |
| `doesNotContain(...)` | Does not contain the specified values |
| `singleElement()` | Asserts the list has exactly one element and continues asserting that element |

For lists of objects, decode each element into a DTO:

~~~java
graphQlTester.document("{ books { id title price } }")
        .execute()
        .path("books")
        .entityList(BookView.class)
        .hasSize(2)
        .satisfies(books -> {
            org.assertj.core.api.Assertions.assertThat(books)
                    .extracting(BookView::title)
                    .containsExactly("Spring GraphQL", "GraphQL in Action");
        });
~~~

## 8. Asserting Nested Paths

`GraphQlTester` JSONPath starts from the `data` section by default. You can select nested paths:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                title
                author {
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

If you need to check multiple paths under the same object, use the callback overload:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                title
                author { name }
            }
        }
        """)
        .execute()
        .path("book", book -> {
            book.path("title")
                    .entity(String.class)
                    .isEqualTo("Spring GraphQL");
            book.path("author.name")
                    .entity(String.class)
                    .isEqualTo("Ada Lovelace");
        });
~~~

The callback gives assertions a shared base path, avoiding long repeated prefixes and keeping test structure close to response structure.

## 9. Asserting the Full JSON of an Object

When you want to verify multiple fields together, use `matchesJson(...)`:

~~~java
graphQlTester.document("""
        {
            book(id: "book-1") {
                id
                title
                price
            }
        }
        """)
        .execute()
        .path("book")
        .matchesJson("""
                {
                    "id": "book-1",
                    "title": "Spring GraphQL",
                    "price": 39.5
                }
                """);
~~~

`matchesJson` compares JSON according to JSONassert rules. It is helpful when checking an entire object structure without creating an expected DTO. The JSONassert library must be on the classpath.

`matchesJsonStrictly(...)` is the strict variant of JSON comparison. Use it when tests need stricter checks on structure/array ordering; verify the semantics of your JSONassert version. If you only care about a few fields, `path(...).entity(...)` usually makes tests less brittle when the schema gains new fields.

## 10. Asserting Null Values and Nonexistent Paths

GraphQL distinguishes between a field with a null value and a field omitted from the response. `GraphQlTester` provides separate assertions:

~~~java
graphQlTester.document("{ book(id: \"missing\") { id title } }")
        .execute()
        .path("book")
        .valueIsNull();
~~~

`valueIsNull()` verifies that the path has a null value. `pathDoesNotExist()` verifies that the path is absent:

~~~java
response.path("book.internalNotes")
        .pathDoesNotExist();
~~~

Do not use these two assertions interchangeably. A nullable field may appear with the value `null`, whereas a field not selected in the selection set normally does not appear in the response.

`hasValue()` checks that the path has a non-null value or a non-empty list:

~~~java
response.path("book")
        .hasValue();
~~~

## 11. Passing Variables and Using documentName

Use GraphQL variables instead of concatenating values directly into the query string:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-1")
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-1");
~~~

You can save operations in `src/test/resources/graphql-test/` with `.graphql` or `.gql` extensions and use `documentName(...)`:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

~~~java
graphQlTester.documentName("bookById")
        .variable("id", "book-1")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

With the default document source, the tester looks for files in `graphql-test/` on the classpath. Extracting queries into files improves reviewability, reuse, and GraphQL syntax highlighting in IDEs.

## 12. Asserting Mutations Without Response Data

If a mutation returns only a side result or has no data to assert, use `executeAndVerify()` to execute it and verify the response has no GraphQL errors:

~~~java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-1")
        }
        """)
        .executeAndVerify();
~~~

If the mutation returns an object or scalar, use `execute()` and assert the path just like a query:

~~~java
graphQlTester.document("""
        mutation ArchiveBook($id: ID!) {
            archiveBook(id: $id) {
                id
                archived
            }
        }
        """)
        .variable("id", "book-1")
        .execute()
        .path("archiveBook.archived")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

## 13. Asserting Errors Alongside Partial Data

GraphQL can return partial `data` and `errors` at the same time. When a test expects errors, declare or inspect them before navigating to a data path.

**Option 1: expect a specific error**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .expect(error -> error.getMessage().contains("Author service unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

`expect(...)` requires at least one error matching the predicate. If no matching error is found, the assertion fails. `verify()` checks that no unexpected errors remain, and then the test continues asserting data.

**Option 2: filter expected errors**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .filter(error -> error.getMessage().contains("Author service unavailable"))
        .verify()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

`filter(...)` allows ignoring errors matching the predicate, without requiring that error to be present. If you want to guarantee an error is present, use `expect(...)`.

**Option 3: inspect all errors with satisfy**

~~~java
graphQlTester.document("{ book(id: \"book-1\") { title author { name } } }")
        .execute()
        .errors()
        .satisfy(errors -> {
            org.assertj.core.api.Assertions.assertThat(errors)
                    .anyMatch(error -> error.getMessage()
                            .contains("Author service unavailable"));
        });
~~~

`errors().satisfy(...)` passes all errors to the callback and marks them as checked, allowing you to continue accessing data if needed.

Do not call `path(...)` before handling errors that the test expects. If the response has unchecked errors, `GraphQlTester` will fail the assertion when navigating to a data path. This behavior prevents tests from accidentally ignoring resolver errors.

## 14. Using errorFilter at the Tester Level

If many tests share a category of intentionally ignorable errors, you can register an `errorFilter` when building the tester:

~~~java
WebGraphQlTester tester = WebGraphQlTester.builder(handler)
        .errorFilter(error -> error.getMessage().contains("known warning"))
        .build();
~~~

A builder-level filter applies to every request sent through that tester. Use with care: an overly broad filter can hide real errors across many tests. For errors expected in only one scenario, declaring `.errors().expect(...)` or `.filter(...)` inline in the test makes intent clearer.

## 15. Asserting Subscriptions with StepVerifier

`executeSubscription()` returns a stream of responses per event. Use `StepVerifier` to verify values, order, and stream completion:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void receivesGreetingEvents() {
    var greetingFlux = graphQlTester.document("subscription { greetings }")
            .executeSubscription()
            .toFlux("greetings", String.class);

    StepVerifier.create(greetingFlux)
            .expectNext("Hi")
            .expectNext("Bonjour")
            .expectNext("Hola")
            .verifyComplete();
}
~~~

`toFlux(path, type)` selects a path inside the data of each subscription event and decodes it into a Java type. For streams that do not complete naturally, use `thenCancel()` or appropriate timing checks.

Subscription testing is supported via `WebSocketGraphQlTester`, or server-side testers `ExecutionGraphQlServiceTester` and `WebGraphQlTester`. Do not assume every transport tester has identical subscription capabilities.

## 16. Creating Testers by Transport

**HTTP:** `HttpGraphQlTester` uses `WebTestClient` and can run against a mock server or live server:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlTester tester = HttpGraphQlTester.create(webTestClient);
~~~

**WebSocket:**

~~~java
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

WebSocketClient webSocketClient = new ReactorNettyWebSocketClient();
WebSocketGraphQlTester tester = WebSocketGraphQlTester
        .builder("ws://localhost:8080/graphql", webSocketClient)
        .build();
~~~

**RSocket:**

~~~java
import java.net.URI;

import io.rsocket.transport.ClientTransport;
import io.rsocket.transport.netty.client.WebsocketClientTransport;
import org.springframework.graphql.test.tester.RSocketGraphQlTester;

URI uri = URI.create("wss://localhost:8080/rsocket");
ClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlTester tester = RSocketGraphQlTester.builder()
        .clientTransport(transport)
        .route("graphql")
        .build();
~~~

**Server-side execution:**

~~~java
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionGraphQlService);
~~~

**Through interceptor chain:**

~~~java
import org.springframework.graphql.test.tester.WebGraphQlTester;

WebGraphQlTester tester = WebGraphQlTester.create(webGraphQlHandler);
~~~

The examples above show how to create testers; in real applications, inject the handlers/services configured by Spring. If a tester holds a connection/session, close it after the test with `stop()` or the corresponding lifecycle hook to release resources.

## 17. Timeouts and Document Source

You can configure a response timeout so tests do not wait indefinitely if a resolver or downstream hangs:

~~~java
import java.time.Duration;

GraphQlTester tester = GraphQlTester.builder(transport)
        .responseTimeout(Duration.ofSeconds(5))
        .build();
~~~

The builder also supports `documentSource(...)` to change where GraphQL documents are loaded from. This is useful when a project stores test queries in a custom classpath folder or uses a custom resource source.

Set timeouts based on reasonable test suite execution times. Timeouts that are too short cause flaky tests on CI; timeouts that are too long delay feedback when a request genuinely hangs.

## 18. Common Errors When Asserting Data

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Path not found | Wrong path or field is not in the selection set | Check the GraphQL document and use paths relative to `data` |
| Test fails before asserting data | Response contains unhandled GraphQL errors | Use `errors().expect/filter/satisfy` before `path(...)` |
| JSONPath list returns empty | Missing wildcard or wrong field name | Use paths like `books[*].title` and inspect the actual response |
| Entity decoding fails | DTO incompatible with response or scalar mapping | Check Java types, constructors/records, and selection set |
| Object comparison always fails | DTO `equals` mismatch or expected object lacks fields | Use `satisfies(...)` to assert individual properties |
| JSON assertion does not run | Missing JSONassert on the test classpath | Add JSONassert dependency or use entity assertions |
| Test fails to verify real errors | Filter is too broad or `satisfy` assertion is too weak | Use `expect(...)` with a specific predicate and assert error count/code |
| Mutation without data causes path error | Mutation returns no field to assert | Use `executeAndVerify()` |
| Subscription test hangs | Stream never completes or lacks cancel condition | Use `thenCancel()`, `take(n)`, or a stream-completing fixture |
| Test depends on a running server | Using a live-transport tester without starting the server | Use a server-side tester or configure test server/port explicitly |

## 19. Workflow for Writing a Good Data Assertion

When writing tests for GraphQL responses:

1. Choose the tester matching the scope under test: resolvers, interceptors, or transport.
2. Write the operation with the right selection set and use variables instead of concatenating inputs.
3. Call `execute()` to obtain the response.
4. If the test expects errors, declare `expect`, `filter`, or `satisfy` before selecting a data path.
5. Use `path(...)` with JsonPath relative to `data`.
6. Use `entity(...)` for scalars/objects and `entityList(...)` for collections.
7. Use `matchesJson(...)` when comparing JSON structure; use `valueIsNull()` or `pathDoesNotExist()` with accurate semantics.
8. For mutations without data to assert, use `executeAndVerify()`.
9. For subscriptions, use `executeSubscription()` and `StepVerifier`.
10. Set a reasonable timeout and close any tester holding connections/sessions after the test.

`GraphQlTester` keeps tests focused on the data contract that a GraphQL client actually sees. When selecting exact paths, decoding into the right types, and checking errors when appropriate, tests catch regressions in resolvers, schemas, and response handling without coupling to a rigid raw JSON string.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL — GraphQlTester.Path API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html)
- [Spring Boot — GraphQL testing support](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
