# WebGraphQlTester

## Objectives

After this lesson, you will be able to:

- Explain the role of WebGraphQlTester in testing Spring for GraphQL applications.
- Distinguish WebGraphQlTester from GraphQlTester, HttpGraphQlTester, and other transport-specific testers.
- Create a WebGraphQlTester from a WebGraphQlHandler.
- Send queries and mutations using documents, variables, and operation names.
- Verify data, field paths, GraphQL errors, and partial responses.
- Test web interceptors and request context at the WebGraphQlHandler layer.
- Choose the right tester for the layer under test and design independent, maintainable tests.

## What Is WebGraphQlTester?

Spring for GraphQL provides GraphQlTester as a unified testing API for GraphQL requests and responses. WebGraphQlTester is the variant for the web layer: it sends requests through WebGraphQlHandler and receives results after the request passes through the WebGraphQlInterceptor chain and GraphQL execution.

WebGraphQlTester is useful when you want to verify how GraphQL web components work together without starting a real HTTP server. For example:

- A query is mapped properly to an annotated controller.
- Variables are bound to controller parameters.
- A WebGraphQlInterceptor adds metadata to the request context.
- An exception from a resolver becomes a GraphQL error.
- One field fails while independent fields still return partial data.

WebGraphQlTester does not send HTTP requests over a socket. Therefore, it does not test HTTP routing, servlet filter chains, HTTP status codes, TLS, proxies, or WebSocket handshakes. When you need to test those components, use an appropriate transport tester such as HttpGraphQlTester.

## Where WebGraphQlTester Fits in the Tester Hierarchy

GraphQlTester is the common contract for all tester types. Each implementation targets a different processing layer:

| Tester | Layer Tested | When to Use |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | GraphQlService and GraphQL execution | Testing resolvers, schema, and execution without the web layer |
| WebGraphQlTester | WebGraphQlHandler and WebGraphQlInterceptor | Testing the web GraphQL layer, request context, and interceptors |
| HttpGraphQlTester | HTTP GraphQL endpoint via WebTestClient | Testing HTTP requests/responses and web server integration |
| WebSocketGraphQlTester | WebSocket GraphQL transport | Testing subscriptions and connection lifecycles |
| RSocketGraphQlTester | RSocket transport | Testing requests and streaming over RSocket |

Choose a tester according to the boundary you need to verify. If a test only needs to check a service method, there is no need to create a GraphQL tester. If you need to verify controller mapping and interceptors, WebGraphQlTester fits well. If you need to verify that requests actually pass through the HTTP stack, WebGraphQlTester is not sufficient.

## Adding Testing Dependencies

With Gradle, add Spring GraphQL Test and Spring Boot Test to the test configuration:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot dependency management should manage compatible versions for Spring artifacts. Do not manually specify a Spring GraphQL version different from the one managed by the Spring Boot BOM unless you have a specific reason.

spring-graphql-test provides GraphQlTester and test implementations like WebGraphQlTester. spring-boot-starter-test provides JUnit Jupiter, AssertJ, and common Spring Boot testing utilities.

## Creating WebGraphQlTester from WebGraphQlHandler

WebGraphQlHandler is the entry point of the web GraphQL layer. It combines GraphQL execution with the configured WebGraphQlInterceptors.

In a Spring Boot integration test, you can inject the handler created by the application context:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

@SpringBootTest
class BookWebGraphQlTests {

    @Autowired
    WebGraphQlHandler handler;

    WebGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = WebGraphQlTester.builder(handler).build();
    }
}
~~~

WebGraphQlTester.builder(handler) creates a tester using the exact handler from the application context. As a result, tests run through the web GraphQL handler and the interceptor chain registered on that handler.

If the application configures a custom WebGraphQlHandler, make sure tests use that configured bean. Creating a new handler manually in a test may omit production interceptors or customizers, meaning the test no longer represents the real web layer.

You can create the tester once per test class if the handler and configuration are immutable. If different tests require different request configurations, use mutate() or create separate testers via the builder rather than mutating shared state across tests.

## Sending Queries and Verifying Responses

WebGraphQlTester uses the same fluent API as GraphQlTester. Start with a document, pass variables, and call execute():

~~~java
@Test
void findsBookById() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .errors()
            .verify();
}
~~~

The example above only verifies that the operation has no GraphQL errors. To verify data, keep the response and access field paths:

~~~java
@Test
void returnsBookTitle() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .path("bookById.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

path() accepts a path relative to the data section of the GraphQL response. entity(String.class) converts the value at that path to a Java type and allows asserting the result.

You can verify a complete object:

~~~java
Book book = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-101")
        .execute()
        .path("bookById")
        .entity(Book.class)
        .get();

assertThat(book.id()).isEqualTo("book-101");
assertThat(book.title()).isEqualTo("Spring for GraphQL");
~~~

When testing a collection, use entityList():

~~~java
graphQlTester.document("""
        query {
            recentBooks(first: 2) {
                id
                title
            }
        }
        """)
        .execute()
        .path("recentBooks")
        .entityList(Book.class)
        .hasSize(2);
~~~

Tests should verify values meaningful to the behavior being protected. There is no need to assert every field in a response if changes to a field do not affect the test's objective.

## Passing Variables and Selecting an Operation

You can pass variables individually:

~~~java
graphQlTester.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .variable("keyword", "Spring")
        .variable("first", 5)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

Or pass a map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 5);

graphQlTester.document(searchBooksDocument)
        .variables(variables)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

If a document contains multiple operations, specify which operation to run:

~~~java
graphQlTester.document(multiOperationDocument)
        .operationName("RecentBooks")
        .variable("first", 5)
        .execute()
        .path("recentBooks")
        .entityList(Book.class)
        .hasSize(5);
~~~

Variable names must match the document without a leading $ character. operationName() selects an operation inside the document; path() selects a field in the response. The two serve different stages.

## Testing Mutations

WebGraphQlTester can test mutations just like queries:

~~~java
@Test
void createsBook() {
    Map<String, Object> input = Map.of(
            "title", "Spring for GraphQL",
            "authorId", "author-12");

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
            .variable("input", input)
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

Mutations have side effects, so test data must be managed carefully. You can use a test database, transaction rollback where appropriate for the execution path, or dedicated fixtures per test. Never let tests depend on execution order or data created by other tests.

If the goal is to verify that a mutation calls the right service, you can mock or spy on the service. However, a test that only verifies mock invocations does not prove that the database, transactions, or GraphQL response work properly; choose the test level that matches the risk being checked.

## Verifying GraphQL Errors

GraphQlTester helps keep tests readable by requiring explicit error checks. If the response must not contain errors, call:

~~~java
response.errors().verify();
~~~

When a test is verifying an intentional error, inspect the error list and verify the message, path, or extensions:

~~~java
@Test
void reportsBookNotFound() {
    GraphQlTester.Response response = graphQlTester.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "missing-book")
            .execute();

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getMessage())
                .contains("Book not found");
        assertThat(errors.get(0).getPath())
                .containsExactly("bookById");
    });
}
~~~

The error path is the response path, which may include aliases and list indices. Therefore, if an operation uses an alias, assertions must check the path using the alias name in the response rather than the original schema field name.

If the application defines an error contract in extensions, verify the stable code rather than relying solely on the message:

~~~java
response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Avoid asserting the entire message text if messages may be localized or edited. Error codes and paths are usually a more stable contract.

## Verifying Partial Data

GraphQL execution can return partial data alongside errors. For example, the title field succeeds while internalNotes is denied:

~~~graphql
query {
  bookById(id: "book-101") {
    title
    internalNotes
  }
}
~~~

Tests can verify both the data and the error:

~~~java
@Test
void keepsPublicFieldWhenInternalFieldIsForbidden() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                bookById(id: "book-101") {
                    title
                    internalNotes
                }
            }
            """)
            .execute();

    response.path("bookById.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");

    response.errors().satisfy(errors -> {
        assertThat(errors).hasSize(1);
        assertThat(errors.get(0).getPath())
                .containsExactly("bookById", "internalNotes");
    });
}
~~~

When testing partial data, do not call errors().verify() because the test expects an error. Instead, assert both the valid data fields and the specific error path.

Nullability in SDL affects the result. If the failing field is non-null, null may propagate up to its parent or root. Tests should verify the exact nullability contract instead of assuming only the child field becomes null.

## Testing WebGraphQlInterceptor

WebGraphQlTester sends requests through WebGraphQlHandler, so it can test WebGraphQlInterceptors registered on the handler. For example, an interceptor that adds a correlation ID to GraphQLContext:

~~~java
@Component
public class CorrelationIdInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("correlationId", "test-correlation-id"))
                        .build());

        return chain.next(request);
    }
}
~~~

A resolver can read the context:

~~~java
@QueryMapping
public String currentCorrelationId(
        @ContextValue("correlationId") String correlationId) {
    return correlationId;
}
~~~

Testing through the handler:

~~~java
@Test
void interceptorAddsCorrelationId() {
    graphQlTester.document("""
            query {
                currentCorrelationId
            }
            """)
            .execute()
            .path("currentCorrelationId")
            .entity(String.class)
            .isEqualTo("test-correlation-id");
}
~~~

This example uses a fixed correlation ID so the test is repeatable. In a real application, the interceptor might extract the ID from a request header or generate a new one. If you need to verify that headers are actually passed from an HTTP request, use HttpGraphQlTester via WebTestClient; WebGraphQlTester only tests the handler layer and the request customizers it exposes.

When creating a tester from a manually built handler, ensure that handler includes the interceptor under test. Otherwise, the test may pass while the real application handler is missing the expected interceptor configuration.

## Testing Validation and Authorization

WebGraphQlTester is useful for verifying errors produced by annotated controllers and method security, provided the test supplies a security context matching the application's configuration.

For validation:

- Send invalid input.
- Verify that the mutation returns a GraphQL error matching the error contract.
- Verify that the service is not called if validation must block before the controller.

For authorization:

- Test a principal with the required authority.
- Test a principal missing the required authority being denied.
- Test a nested field being denied while public fields still return data.
- Test that a different tenant or owner cannot read the data.

WebGraphQlTester does not automatically create authentication for tests. How the security context is provided depends on how the application configures Spring Security and the web handler. If you need to verify the security filter chain, authentication from HTTP headers, or sessions/cookies, test over HTTP transport with WebTestClient and Spring Security test support.

## Customizing the Tester and Requests

GraphQlTester supports creating a new tester from an existing one via mutate(). This is helpful when you want to keep shared configuration while changing specific settings for a group of tests.

Illustrative example:

~~~java
WebGraphQlTester adminTester = graphQlTester.mutate()
        .build();
~~~

The snippet above creates a new tester from the existing configuration. Authentication does not automatically change simply by creating a new tester; the security context must be configured using the application's test mechanism.

If a test needs request-specific context or metadata, use the request configuration capabilities of the WebGraphQlTester builder provided by your Spring for GraphQL version. Avoid storing test state in a singleton interceptor or mutable field shared across multiple requests.

## Distinguishing WebGraphQlTester and HttpGraphQlTester

These two testers are often confused because both relate to the web layer:

| Criterion | WebGraphQlTester | HttpGraphQlTester |
| --- | --- | --- |
| Input | WebGraphQlHandler | WebTestClient |
| Real HTTP server | Not required | Can use a running server or mock web server |
| WebGraphQlInterceptor | Yes | Yes, via the web handler |
| HTTP routing/filters | Not tested | Can be tested |
| HTTP status and headers | Not its purpose | Can be tested via WebTestClient |
| TLS, proxy, network | Not tested | Only tested when the test setup includes them |
| Best suited for | Web GraphQL handler and interceptors | HTTP GraphQL endpoint |

If you want to test the endpoint over HTTP with Spring Boot:

~~~java
HttpGraphQlTester tester =
        HttpGraphQlTester.create(webTestClient);
~~~

WebTestClient can be configured to bind to the application context or a running server. This tests a different boundary than WebGraphQlTester and should be named clearly in the test suite.

## Test Organization Strategy

A maintainable GraphQL test suite is typically divided by boundary:

1. Unit tests: verify business services, mappers, and policies without GraphQL.
2. Execution tests: use ExecutionGraphQlServiceTester when verifying the schema and resolvers.
3. Web layer tests: use WebGraphQlTester to verify the handler, interceptors, and context propagation.
4. HTTP integration tests: use HttpGraphQlTester to verify endpoints and HTTP integration.
5. Streaming tests: use WebSocketGraphQlTester or RSocketGraphQlTester for subscriptions.

You do not need to use WebGraphQlTester for every test. Choose the lightest tester capable of proving the required behavior; add integration tests at outer boundaries where there are risks in transport, security filters, or serialization.

## Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot create WebGraphQlTester | Missing WebGraphQlHandler or spring-graphql-test | Check application context and test dependencies |
| Interceptor does not run in test | Tester uses a handler without the interceptor | Inject the production handler or register the interceptor on the test handler |
| Test does not see HTTP headers | WebGraphQlTester does not inspect real HTTP requests | Use HttpGraphQlTester and WebTestClient |
| Assertion reports remaining GraphQL errors | Test did not handle errors or response has unexpected errors | Call errors().verify() for success cases or assert specific errors |
| Cannot retrieve field path | Wrong path, alias differs from field name, or field is null due to an error | Inspect response data and error path |
| Partial data test fails | Calling errors().verify() in a test expecting an error | Assert data and errors separately |
| Security test is always anonymous | Security context not set up or testing the wrong transport layer | Use appropriate Spring Security test support |
| Mutation tests depend on execution order | Shared database state | Use isolated fixtures, cleanup, or transaction isolation |
| Handler test passes but HTTP endpoint fails | Filters, routing, or codecs were not tested | Add an HttpGraphQlTester integration test |
| Test only checks mock services | Schema, binding, or response was not verified | Add tests using WebGraphQlTester or an appropriate tester |

## Comprehensive Practice

Build a test suite for a library API:

1. Add spring-graphql-test and spring-boot-starter-test.
2. Inject WebGraphQlHandler into the test class.
3. Create WebGraphQlTester in @BeforeEach.
4. Write a BookById query, pass the id variable, and verify the title.
5. Write a CreateBook mutation with an input object and verify the response.
6. Send a nonexistent ID and verify the GraphQL error message, path, or extensions code.
7. Create a query fetching both title and internalNotes; verify partial data when internalNotes is denied.
8. Register a WebGraphQlInterceptor that adds a correlation ID and verify the resolver reads the context.
9. Write a validation test and verify the service is not called when input is invalid.
10. Add an HttpGraphQlTester test if you need to check HTTP headers, status codes, or the security filter chain.

After completing it, explain why WebGraphQlTester does not replace HttpGraphQlTester, why both data and errors must be asserted in partial responses, and when interceptors should be tested through the handler.

## Takeaways

WebGraphQlTester tests the web GraphQL layer by sending requests through WebGraphQlHandler. It is ideal for testing annotated controllers, WebGraphQlInterceptors, variables, field paths, errors, and partial data without a real HTTP server. Use document(), variable(), execute(), path(), and errors() to write clear assertions. For successful responses, verify there are no errors; for intentional errors, check paths and extensions rather than relying solely on messages. WebGraphQlTester does not test HTTP routing, filter chains, status codes, or networking; use HttpGraphQlTester with WebTestClient for those requirements. Organizing tests by boundary keeps the test suite fast, understandable, and effective at catching the right kinds of bugs.

## References

- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL – GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [Spring for GraphQL – WebGraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/WebGraphQlTester.html)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
