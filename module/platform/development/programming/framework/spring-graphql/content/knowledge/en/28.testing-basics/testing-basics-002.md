# HttpGraphQlTester in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain the role of `HttpGraphQlTester` in testing Spring for GraphQL.
- Distinguish between testing GraphQL execution and testing over HTTP transport.
- Configure `HttpGraphQlTester` from `WebTestClient`.
- Write integration tests that send GraphQL documents and variables over HTTP.
- Verify returned data using `path`, `entity`, and `entityList`.
- Verify GraphQL errors, error paths, and error codes.
- Send authentication headers and verify authorization over HTTP.
- Distinguish GraphQL response assertions from HTTP status/header assertions.
- Test validation, input binding, and error cases.
- Understand the limitations of `HttpGraphQlTester` with Subscriptions and WebSockets.

## 1. What Is HttpGraphQlTester Used For?

`HttpGraphQlTester` is Spring for GraphQL's GraphQL client testing tool for HTTP transport. It sends GraphQL operations over HTTP to the application's endpoint, then provides an API to inspect `data` and `errors` in the GraphQL response.

This tool is suitable when you need to verify the full path from an HTTP request to the resolver:

- Is the HTTP endpoint configured correctly?
- Is the GraphQL document parsed and validated?
- Are variables bound to arguments and input DTOs?
- Does the resolver return the expected data?
- Do security filters authenticate and enforce permissions?
- Are exceptions converted into GraphQL errors according to the contract?

For example, instead of calling the `BookController.book(...)` method directly, a test sends the operation `query { book(id: ...) { ... } }` to `/graphql`. The request goes through the web server, GraphQL HTTP handler, interceptors, execution engine, and resolvers just like a real client.

`HttpGraphQlTester` lets you write assertions at the GraphQL response level, avoiding manual JSON response parsing in every test.

## 2. Distinguishing Types of GraphQlTester

Spring for GraphQL provides multiple testing approaches depending on the boundary you need to verify:

| Tester | Testing Boundary | When to Use |
| --- | --- | --- |
| `ExecutionGraphQlServiceTester` | GraphQL execution service | Testing execution and resolvers without HTTP transport |
| `HttpGraphQlTester` | HTTP GraphQL endpoint | Testing request/response over HTTP, headers, and web security |
| `WebSocketGraphQlTester` | WebSocket GraphQL transport | Testing subscriptions and response streams over WebSocket |
| `RSocketGraphQlTester` | RSocket transport | Testing applications using RSocket |

If the goal is to verify `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` in the execution layer, a tester at the execution boundary may be sufficient.

If you need to verify URLs, HTTP headers, filter chains, CORS integration, or requests actually hitting the endpoint, use `HttpGraphQlTester`.

Do not use `HttpGraphQlTester` to conclude that Subscriptions work over WebSocket. HTTP request/response and WebSocket subscriptions are two different transports.

## 3. Preparing Testing Dependencies

In a Maven project, you need the Spring GraphQL testing dependency:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If the project uses Spring Boot dependency management, the version of `spring-graphql-test` should be managed in sync with the Spring GraphQL version provided by Boot. Do not manually pick a version different from the runtime dependency.

Common companion test dependencies:

- `spring-boot-starter-test` for JUnit Jupiter, AssertJ, and Spring Test.
- `spring-test` providing `WebTestClient`.
- `spring-graphql-test` providing `HttpGraphQlTester` and the GraphQL tester APIs.

Check test scope so testing support dependencies are not packaged into the runtime artifact if the application does not need them at runtime.

## 4. Creating HttpGraphQlTester from WebTestClient

`HttpGraphQlTester` takes a `WebTestClient` configured to access the GraphQL endpoint.

Example connecting to a running server:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

In the default Spring Boot configuration, the GraphQL HTTP endpoint is typically `/graphql`. `HttpGraphQlTester` uses the tester's default GraphQL endpoint; if the application changes the path, configure the tester's URL to match the actual path according to the API of your Spring GraphQL version.

`WebTestClient.bindToServer()` connects to a server over HTTP. Therefore, the server must be started before the test sends requests.

For integration tests, a random server port is usually used to avoid port conflicts between test runs.

## 5. Creating the Tester in a Spring Boot Integration Test

You can use `@SpringBootTest` with a random port, then create `WebTestClient` and `HttpGraphQlTester` in the test fixture.

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpGraphQlTests {

    @LocalServerPort
    int port;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient webTestClient = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();

        graphQlTester = HttpGraphQlTester.create(webTestClient);
    }
}
~~~

In the test:

- `RANDOM_PORT` starts the application on an available port chosen by the test environment.
- `@LocalServerPort` provides the actual port.
- `WebTestClient.bindToServer()` connects to the running server.
- `HttpGraphQlTester.create(...)` creates a GraphQL tester using HTTP.

This approach tests the application's real HTTP transport. On the other hand, the test starts more components and is usually slower than tests that only verify GraphQL execution.

## 6. Sending GraphQL Documents and Variables

`HttpGraphQlTester`'s API uses the same fluent request style as other GraphQL testers.

Example Query test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.test.tester.GraphQlTester;

@Test
void shouldReturnBook() {
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
            .isEqualTo("Spring for GraphQL");
}
~~~

`document(...)` holds the GraphQL operation. `variable(...)` assigns a value to a variable declared in the document. `execute()` sends the operation over HTTP and returns a response object for assertions.

Use variables instead of concatenating data into the query string. This keeps the document stable and readable, and helps tests cover multiple input sets.

If a document contains multiple operations, select the appropriate operation using the request builder API of the version in use. In most tests, each document should contain a single clearly named operation so results are easy to understand.

## 7. Verifying Objects and Scalars with path

After execution, `GraphQlTester.Response` lets you access fields in `data` using `path(...)`.

Example:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                published
            }
        }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

response.path("book.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");

response.path("book.published")
        .entity(Boolean.class)
        .isEqualTo(true);
~~~

The paths in this example are evaluated from the GraphQL `data` content, without needing a `data.` prefix.

`entity(Class<T>)` converts the value at the path to the expected Java type. Using explicit types helps tests detect mismatches between the schema, serialization, and DTOs.

For nullable fields, write assertions for both non-null values and `null` according to the contract. Do not assume every field returning `null` is an error; it may be a valid schema outcome.

## 8. Verifying Lists and Nested Objects

You can use `entityList(...)` to verify lists:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .execute();

response.path("books[*].id")
        .entityList(String.class)
        .contains("book-42", "book-99");
~~~

The `[*]` notation selects the corresponding field across elements of the list.

For nested objects, you can navigate deeper along the path:

~~~java
response.path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

If list ordering is not part of the API contract, avoid index-based assertions. Check the set of IDs or meaningful attributes instead so tests do not depend on unguaranteed ordering.

If a list is paginated, verify separately:

- Items on the page.
- Cursors or page information.
- Total record count if provided by the API.
- Behavior when the page size exceeds limits.

## 9. Verifying GraphQL Errors

A GraphQL response can contain `data`, `errors`, or both. Therefore, tests must explicitly assert whether an operation is expected to succeed or fail.

For a successful operation, you can use:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
            }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

`verify()` ensures the response has no GraphQL errors. If any errors are present, the assertion fails and indicates that the response contained errors.

For cases expecting errors, verify the error contract:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "missing-book") {
                id
                title
            }
        }
        """)
        .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).hasSize(1);
    assertThat(errors.get(0).getMessage())
            .isEqualTo("The requested book was not found.");
    assertThat(errors.get(0).getExtensions())
            .containsEntry("code", "BOOK_NOT_FOUND");
});
~~~

Do not just check that there is an error. Verify standardized messages, error codes, and paths when they are part of the API contract.

Do not compare the entire error object if parts such as `locations` or internal runtime details may vary across GraphQL versions. Assert only properties meaningful to the client.

## 10. Verifying Partial Data and Error Paths

A nested field may fail while other fields still return data.

Example:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
~~~

If `internalNotes` fails while its parent field remains valid, the response may contain `book.id` and `book.title` alongside the error path `["book", "internalNotes"]`.

Tests can verify both the successful data and the error:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                id
                title
                internalNotes
            }
        }
        """)
        .execute();

response.path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
            assertThat(error.getPath())
                    .contains("book", "internalNotes")
    );
});
~~~

Testing this way verifies GraphQL partial responses, nullability, and error mapping at the same time.

If the schema declares a field as non-null, GraphQL can propagate `null` up to the nearest nullable parent. Tests should accurately reflect SDL null propagation rather than assuming a failing field only affects itself.

## 11. Testing Mutations and Input Binding

`HttpGraphQlTester` is also well suited for testing Mutations over HTTP.

Example:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
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
        .execute();

response.path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
~~~

This test verifies multiple steps:

1. The document declares the input variable with the right type.
2. The tester serializes object variables to JSON.
3. GraphQL validates the input against the schema.
4. Spring binds the input to the resolver's argument/DTO.
5. The Mutation executes business logic and returns the payload.

In addition to the returned result, Mutation tests should verify required side effects through repositories or service test fixtures. Do not check only the response if business requirements demand durable persistence.

For tests that write to a database, prepare isolated data per test and clean up according to the integration test's transaction/fixture strategy. Never let tests depend on execution order.

## 12. Verifying Authentication and HTTP Headers

One advantage of `HttpGraphQlTester` is the ability to send requests over HTTP with headers just like a real client.

Example creating a `WebTestClient` with a Bearer token:

~~~java
import org.springframework.http.HttpHeaders;

WebTestClient webTestClient = WebTestClient.bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + testAccessToken
        )
        .build();

HttpGraphQlTester authenticatedTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Then use `authenticatedTester` to test operations requiring authentication.

Cases to cover include:

- Requests with a valid token are allowed to call the operation.
- Requests missing a token are rejected according to the security configuration.
- Valid tokens lacking the required authority cannot read sensitive fields.
- Users from another tenant cannot access the object.
- Error responses do not leak tokens or authentication details.

Do not use `@WithMockUser` on tests hitting a random server port and assume `Authentication` automatically propagates to the server thread. For HTTP integration tests, send credentials through the real transport mechanism or configure the corresponding test security filter chain. `@WithMockUser` is better suited for tests running within the same test application context where the security context is properly integrated.

Never hardcode real tokens in source code or logs. Use short-lived test tokens or mock authentication mechanisms that exist only in the test profile.

## 13. When to Check HTTP Status and Response Headers

`HttpGraphQlTester` focuses on the GraphQL response. When you need to verify HTTP transport details such as status codes, response headers, or content type, use `WebTestClient` directly.

Example:

~~~java
import java.util.Map;

import org.springframework.http.MediaType;

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "query { book(id: \"book-42\") { id title } }"
        ))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.data.book.id")
        .isEqualTo("book-42");
~~~

Division of responsibility:

- Use `HttpGraphQlTester` for GraphQL-semantic assertions: data paths, entities, error codes, and error paths.
- Use `WebTestClient` directly for HTTP assertions: status, headers, content type, cookies, and transport-level behavior.

Do not assume every GraphQL error must have a 4xx or 5xx HTTP status. HTTP status also depends on the GraphQL-over-HTTP media type, specification version, and transport configuration. Tests should verify the behavior the API actually commits to.

## 14. Testing CORS and Request Transport

If a frontend calls GraphQL from a different origin, CORS preflight may be part of integration requirements.

`HttpGraphQlTester` is suited for GraphQL POST requests, not for testing the entire CORS handshake on its own. You can use `WebTestClient` to send an `OPTIONS` request and inspect the CORS response headers.

Example:

~~~java
import org.springframework.http.HttpHeaders;

webTestClient.options()
        .uri("/graphql")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
        )
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type"
        )
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"
        );
~~~

Tests must match the application's CORS policy, including origin, method, and allowed headers. Do not use wildcards in assertions if the production policy requires a specific origin.

CORS only controls browser cross-origin access. It does not replace authentication or authorization; security tests still need to check requests with and without credentials.

## 15. Testing Validation and Argument Binding Errors

GraphQL parsing and validation occur before resolvers run. Tests should verify that schema-invalid operations are rejected and produce no side effects.

Example document using a nonexistent field:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                unknownField
            }
        }
        """)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
);
~~~

For a required argument, you can omit the variable:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
            }
        }
        """)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
);
~~~

For input objects, also test cases such as:

- Missing non-null fields.
- Wrong scalar types.
- Nonexistent enum values.
- Input objects containing fields not declared in the schema.
- Valid types that violate business validation rules.

Validation errors and business errors are two separate layers. Tests should verify that the resolver is not invoked when a document fails validation, and that business errors carry dedicated codes when an operation is schema-valid but violates business rules.

## 16. Reusing Testers and Configuring Headers

If multiple tests share the same base URL or authentication headers, you can create a helper to instantiate `HttpGraphQlTester`.

Example:

~~~java
HttpGraphQlTester createTester(String token) {
    WebTestClient webTestClient = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .defaultHeader(
                    HttpHeaders.AUTHORIZATION,
                    "Bearer " + token
            )
            .build();

    return HttpGraphQlTester.create(webTestClient);
}
~~~

Helpers should centralize test configuration:

- Base URL and GraphQL path.
- Authentication headers.
- Required default headers.
- Timeouts suited to the test environment.
- Non-sensitive configuration values.

Do not share a tester holding user A's token with tests for user B. Create a dedicated tester per identity or build a fresh client per test case to avoid leaking authentication state.

When you need to adjust configuration from an existing tester, use the mutate/builder API provided by your Spring GraphQL version instead of inadvertently mutating a shared `WebTestClient`.

## 17. Limitations to Know

`HttpGraphQlTester` is very useful, but it does not replace every type of test:

- It does not test WebSocket handshakes or subscription streams.
- It does not test RSocket transport.
- It does not automatically verify database transactions if the test does not check side effects.
- It does not automatically prove authorization is correct for every field and tenant; appropriate test cases must be written.
- It does not replace unit tests for service logic.
- It does not automatically verify HTTP status/headers if the test only uses the GraphQL response API.
- It does not test performance or concurrent load with a single request assertion.

Multiple layers should be combined:

| Goal | Suitable Test Type |
| --- | --- |
| Service rules | Unit test or method-level integration test |
| Resolvers and schema mapping | GraphQL execution tester |
| HTTP endpoint, headers, security filters | `HttpGraphQlTester` and `WebTestClient` |
| Subscriptions | `WebSocketGraphQlTester` |
| Database queries and transactions | Repository/integration test |
| Performance and load | Dedicated performance/load test |

## 18. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Cannot connect to server | Server is not running or base URL is wrong | Use a random port and check lifecycle |
| Tester calls wrong endpoint | Application changed GraphQL path while tester uses default | Configure tester URL to match actual path |
| `HttpGraphQlTester` class not found | Missing `spring-graphql-test` in test scope | Add the corresponding dependency |
| Assertion cannot find field | Path does not match `data` structure | Inspect GraphQL response and path |
| Test passes despite response errors | `errors().verify()` not called or errors not asserted | Verify the error contract explicitly |
| Brittle error assertions | Comparing entire error objects or locations | Check only contract message/code/path |
| Auth test is always anonymous | Token/header not sent or `@WithMockUser` used at wrong boundary | Send credentials over HTTP or configure test security properly |
| CORS test fails | Origin/header/method does not match policy | Inspect preflight request and CORS config |
| Subscription test receives no events | Using HTTP tester for a WebSocket operation | Use a WebSocket tester |
| Test depends on stale data | Shared fixtures or database not cleaned up | Create isolated data and clean up |
| HTTP status assertion mismatch | Assuming GraphQL errors always map to a fixed status | Check transport contract of the running version |

## 19. Workflow for Building Tests with HttpGraphQlTester

When adding HTTP GraphQL integration tests, follow this sequence:

1. **Choose the right boundary.** Decide whether to test HTTP transport or only GraphQL execution.
2. **Add dependencies.** Put `spring-graphql-test` in test scope with synchronized versions.
3. **Start the test server.** Use a random port or appropriate test web environment.
4. **Create WebTestClient.** Configure the base URL and required HTTP headers.
5. **Create HttpGraphQlTester.** Use `HttpGraphQlTester.create(webTestClient)`.
6. **Send the operation.** Use `document(...)`, `variable(...)`, and `execute()`.
7. **Verify data.** Use `path(...)`, `entity(...)`, and `entityList(...)`.
8. **Verify errors.** Assert message, code, and path when part of the API contract.
9. **Verify HTTP separately.** Use `WebTestClient` directly for status, headers, CORS, and transport.
10. **Cover negative cases.** Test validation, authentication, authorization, input binding, and partial data.

## 20. Summary

`HttpGraphQlTester` is the tool for testing GraphQL over HTTP in Spring for GraphQL. It is created from `WebTestClient`, sends GraphQL documents and variables to the endpoint, and provides an API to inspect responses with `path`, `entity`, `entityList`, and `errors`.

Use `HttpGraphQlTester` when you need to verify the path from HTTP transport to GraphQL resolvers, including request binding, headers, and security filters. For HTTP status codes, response headers, or CORS preflight, use `WebTestClient` directly to test the transport layer. For Subscriptions, use a WebSocket tester. Combining test types at their proper boundaries keeps API verification clear, stable, and free from confusing GraphQL execution with HTTP transport behavior.
