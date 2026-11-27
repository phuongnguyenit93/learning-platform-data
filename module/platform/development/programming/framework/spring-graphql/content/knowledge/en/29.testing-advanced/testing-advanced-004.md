# WebTestClient with GraphQL

The GraphQL endpoint in Spring for GraphQL is typically exposed over HTTP at `/graphql`. When testing this endpoint, you need to verify both the GraphQL payload and the surrounding HTTP behavior: method, URL, request headers, content type, status code, response headers, and JSON body.

WebTestClient is the HTTP client provided by Spring for testing web endpoints. It can send requests to a WebFlux application in a mock environment, run over MockMvc for a Spring MVC application, or call a live running server. With GraphQL, you can use WebTestClient directly to test the HTTP transport or combine it with HttpGraphQlTester for GraphQL-specific assertions.

## Why test at the HTTP layer?

Testing resolvers directly verifies GraphQL logic, but it does not prove that the HTTP endpoint is configured properly. A request can succeed in ExecutionGraphQlServiceTester and still fail over HTTP due to a wrong path, content type, security filter, CORS, or JSON codec.

WebTestClient helps verify the following:

- The GraphQL endpoint accepts the expected HTTP method and URL.
- The request body containing `query`, `operationName`, `variables`, and `extensions` is bound properly.
- `Content-Type` and `Accept` are handled properly.
- HTTP status codes accurately reflect transport or protocol errors.
- The GraphQL response has properly structured `data` and `errors`.
- Security, CORS, cookies, and custom response headers work through the web stack.
- The application handles requests in both mock web environments and a live server.

## WebTestClient and HttpGraphQlTester

HttpGraphQlTester uses WebTestClient under the hood. The two tools serve complementary perspectives:

| Tool | Best suited for testing |
| --- | --- |
| WebTestClient | HTTP method, path, headers, status, content type, JSON body, and web stack behavior |
| HttpGraphQlTester | GraphQL document, variables, `operationName`, data paths, GraphQL errors, and typed entities |
| ExecutionGraphQlServiceTester | Direct GraphQL execution without passing through HTTP transport |
| WebGraphQlTester | `WebGraphQlHandler` and the `WebGraphQlInterceptor` chain with mock requests |

If a test must verify that the HTTP endpoint actually accepts `POST /graphql` and returns the right headers/status, use WebTestClient. If the goal is to assert fields, nested data, or GraphQL errors, HttpGraphQlTester makes tests shorter and easier to read.

Both approaches can be used in the same test suite. There is no need to rewrite every GraphQL assertion with JSONPath when HttpGraphQlTester already serves that purpose.

## Testing dependencies

To use GraphQlTester and HttpGraphQlTester, add the Spring for GraphQL test module:

~~~kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

WebTestClient is part of the Spring WebFlux/Spring Test ecosystem. If the application already has WebFlux on the classpath, the required types are usually already available. For Spring MVC applications, you can use MockMvcWebTestClient to run WebTestClient over MockMvc. For tests hitting a live server, you need an appropriate HTTP connector and a running server.

In Spring Boot, test dependencies may be supplied via starters or test modules depending on the Boot version and web stack. Use Spring Boot dependency management to align versions; do not manually pin a `spring-graphql-test` version that differs from your `spring-graphql` version.

## What is the structure of a GraphQL HTTP request?

Under Spring for GraphQL's default HTTP transport, the endpoint accepts `POST` with `Content-Type` `application/json`. The body is a JSON object that can contain:

| Property | Meaning |
| --- | --- |
| query | GraphQL document |
| operationName | Name of the operation to execute when the document contains multiple operations |
| variables | Map of input variables for the operation |
| extensions | Extended metadata, such as persisted queries if supported by the application |

Example request:

~~~json
{
  "operationName": "BookById",
  "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-42"
  }
}
~~~

In the following examples, assume the application has this GraphQL schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

## Sending a GraphQL POST with WebTestClient

Test the HTTP endpoint directly by building a JSON payload and sending a POST:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GraphQlHttpEndpointTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void shouldReturnBookForValidQuery() {
        Map<String, Object> request = Map.of(
                "operationName", "BookById",
                "query", """
                        query BookById($id: ID!) {
                            book(id: $id) {
                                id
                                title
                            }
                        }
                        """,
                "variables", Map.of("id", "book-42"));

        webTestClient.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                    .jsonPath("$.data.book.id").isEqualTo("book-42")
                    .jsonPath("$.data.book.title").isEqualTo("Spring GraphQL");
    }
}
~~~

Key points:

1. `post()` selects HTTP POST.
2. `uri("/graphql")` targets the GraphQL endpoint; if the application changes `spring.graphql.path`, the test must use that configured path.
3. `contentType(APPLICATION_JSON)` specifies the request body media type.
4. `accept(APPLICATION_JSON)` selects the legacy-compatible response format.
5. `bodyValue(request)` sends the map serialized as JSON.
6. `exchange()` executes the request; the `expect...` assertions verify the response.

JSONPath inside `expectBody()` targets the entire HTTP response body, so it must start with `$.data` or `$.errors`. This differs from `GraphQlTester.path()`, where paths are already relative to the `data` section by default.

## Configuring WebTestClient for each environment

WebTestClient can bind to different server targets. Choose the setup that matches your test goal.

### WebFlux with a mock ApplicationContext

For Spring WebFlux applications, you can bind the client directly to the `ApplicationContext` without opening a port:

~~~java
WebTestClient webTestClient =
        WebTestClient.bindToApplicationContext(context)
                .configureClient()
                .build();
~~~

Then send requests to `/graphql` as in the previous example. This routes through WebFlux's web infrastructure in the test environment, which is ideal for testing routes and filters without starting a live server.

With Spring Boot, `@SpringBootTest` combined with `@AutoConfigureWebTestClient` can supply a pre-configured `WebTestClient` for the mock web environment. `@WebFluxTest` also auto-configures `WebTestClient`, but that slice only loads a subset of beans; you must import the required GraphQL configuration or components if you want to test the GraphQL endpoint.

The `AutoConfigureWebTestClient` import differs across Spring Boot versions:

- Spring Boot 4: `org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient`.
- Spring Boot 3: `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`.

In Spring Boot 3, the auto-configured `WebTestClient` is primarily intended for WebFlux applications. For Spring MVC applications, use `MockMvcWebTestClient` or `WebTestClient.bindToServer()` when hitting a live server.

### Spring MVC with MockMvcWebTestClient

Spring MVC runs on the Servlet stack. To keep the `WebTestClient` testing API while running on top of MockMvc, use `MockMvcWebTestClient`:

~~~java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient webTestClient =
        MockMvcWebTestClient.bindToApplicationContext(context)
                .configureClient()
                .build();
~~~

The client still sends `POST` requests to `/graphql` and supports WebTestClient assertions. This tests MVC handlers, filters, and interceptors without opening a TCP port.

### Calling a live running server

When you need to test the embedded server, HTTP connector, port mapping, or behavior unavailable in a mock environment, bind the client to the server:

~~~java
WebTestClient webTestClient =
        WebTestClient.bindToServer()
                .baseUrl("http://localhost:8080")
                .build();
~~~

Requests still use `uri("/graphql")`. In test suites, prefer a random port to avoid conflicts with applications running on the machine:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GraphQlLiveHttpTests {

    @Autowired
    private WebTestClient webTestClient;

    // Test methods use webTestClient.post().uri("/graphql") ...
}
~~~

With a live server, tests exercise the network stack and embedded server. In return, tests run slower and require managing test data, ports, timeouts, and application state.

## Checking HTTP status and GraphQL errors

One of the most common points of confusion when testing GraphQL is that HTTP status does not directly represent whether a resolver succeeded or failed.

Spring for GraphQL handles execution in two stages:

1. Errors at the HTTP or request transport layer—such as an unavailable server, missing credentials, invalid JSON, or unsupported content type—can produce HTTP 4xx/5xx.
2. Once a GraphQL request is accepted and executed, resolver errors are placed into the `errors` array of the GraphQL response. The HTTP status typically remains 200 OK.

Example when a resolver raises a business error:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["book"]
    }
  ]
}
~~~

Tests must verify both status and body:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query",
                "{ book(id: \"missing\") { id title } }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.book").isEqualTo(null)
        .jsonPath("$.errors[0].message")
            .isEqualTo("Book not found")
        .jsonPath("$.errors[0].path[0]").isEqualTo("book");
~~~

Do not write `expectStatus().isOk()` alone and conclude the test passed. A GraphQL response can return HTTP 200 while containing errors in `errors`.

## Content negotiation and GraphQL response media types

Spring for GraphQL supports two common `Accept` media types:

| Accept | Behavior |
| --- | --- |
| application/json | Legacy compatibility mode; GraphQL parse or validation errors may still be returned with HTTP 200 |
| application/graphql-response+json | Follows GraphQL over HTTP; parse or validation errors can use HTTP 4xx |

Once a request is successfully validated, errors occurring during resolver execution are still returned in `errors` with HTTP status 200.

Example testing a GraphQL document error in legacy compatibility mode:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query", "{ fieldDoesNotExist }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.errors").isArray();
~~~

Example testing the same error when the client selects the GraphQL response media type:

~~~java
MediaType graphQlResponseJson =
        MediaType.parseMediaType("application/graphql-response+json");

webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(graphQlResponseJson)
        .bodyValue(Map.of(
                "query", "{ fieldDoesNotExist }"))
        .exchange()
        .expectStatus().is4xxClientError()
        .expectBody()
        .jsonPath("$.errors").isArray();
~~~

The two tests above differ only in the `Accept` header. When testing your API, verify which media type real clients use so you do not assert the wrong status. If the application supports both media types, test both.

## Testing HTTP request errors

Beyond GraphQL errors, verify that the endpoint responds properly to malformed HTTP requests:

~~~java
import java.nio.charset.StandardCharsets;

@Test
void shouldRejectInvalidJson() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{ invalid json".getBytes(StandardCharsets.UTF_8))
            .exchange()
            .expectStatus().is4xxClientError();
}
~~~

~~~java
@Test
void shouldRejectUnsupportedContentType() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("query { book { id } }")
            .exchange()
            .expectStatus().is4xxClientError();
}
~~~

The GraphQL HTTP endpoint accepts `POST` by default. `GET` is not enabled by default in Spring for GraphQL; if the application enables `GET`, both the handler and route predicate must allow that method. `GET` is intended only for Queries since it is an HTTP safe method; Mutations must use `POST`.

## Using HttpGraphQlTester on top of WebTestClient

When you want GraphQL-aware assertions instead of writing raw JSONPath, create an `HttpGraphQlTester` from `WebTestClient`:

~~~java
import org.springframework.graphql.test.tester.HttpGraphQlTester;

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.create(webTestClient);
~~~

Then test queries with GraphQL documents and variables:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "book-42")
        .execute()
        .path("book.id")
            .entity(String.class).isEqualTo("book-42")
        .path("book.title")
            .entity(String.class).isEqualTo("Spring GraphQL");
~~~

`HttpGraphQlTester` executes requests through the same `WebTestClient` while understanding GraphQL response structure. `path()` is relative to the `data` section by default, so there is no need to write `data.book.title`.

For mutations or requests where a test does not need to inspect specific fields, you can use `executeAndVerify()` to verify the response contains no GraphQL errors:

~~~java
graphQlTester.document("""
        mutation DeleteBook($id: ID!) {
            deleteBook(id: $id)
        }
        """)
        .variable("id", "book-42")
        .executeAndVerify();
~~~

If the mutation returns data, use `execute()` and assert fields just like a query.

## Checking GraphQL errors with HttpGraphQlTester

`GraphQlTester` provides an API to verify that errors occur, filter known errors, or inspect the entire error list:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", "missing")
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Book not found"))
        .verify();
~~~

If you want to verify multiple errors:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

graphQlTester.document("""
        query {
            first: book(id: "missing-1") { id }
            second: book(id: "missing-2") { id }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors).hasSize(2));
~~~

`satisfy()` lets you use AssertJ or another assertion library to inspect the list of `ResponseError` objects. Handling errors through this API also marks them as verified, allowing the test to continue reading `data` when the response includes partial data.

Do not filter all errors with `errorFilter` just to keep tests green. Filter only expected errors and explicitly verify their content, path, or extensions.

## Testing operationName and variables

When a GraphQL document defines multiple operations, send the appropriate `operationName`:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
  }
}

query BookCount {
  bookCount
}
~~~

With `WebTestClient`, include `operationName` in the JSON request:

~~~java
Map<String, Object> request = Map.of(
        "query", document,
        "operationName", "BookCount");
~~~

With `HttpGraphQlTester`, you can combine `operationName()` with `variable()`:

~~~java
graphQlTester.document(document)
        .operationName("BookCount")
        .execute()
        .path("bookCount")
        .entity(Integer.class)
        .isEqualTo(12);
~~~

Testing variables separately verifies that the server receives the right data types, null values, and nested input objects. Avoid concatenating inputs directly into the GraphQL document when your goal is to test the variables mechanism.

## Loading GraphQL documents from files

For long queries or documents using fragments, store them in `.graphql` or `.gql` files to avoid hard-to-read Java strings. `HttpGraphQlTester` can use `documentName()` and `fragmentName()` with the default `DocumentSource` under `graphql-test/` on the classpath.

Example structure:

~~~text
src/test/resources/
  graphql-test/
    bookById.graphql
    bookFields.graphql
~~~

Contents of `bookById.graphql`:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    ...bookFields
  }
}
~~~

Contents of `bookFields.graphql`:

~~~graphql
fragment bookFields on Book {
  id
  title
}
~~~

Test:

~~~java
graphQlTester.documentName("bookById")
        .fragmentName("bookFields")
        .variable("id", "book-42")
        .execute()
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

With raw `WebTestClient`, the request body still requires the `query` field containing the complete document. When using files, the test can read the file into a `String` and place it in the payload.

## Testing headers, cookies, and authentication

WebTestClient lets you send headers just like a real client:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .bodyValue(Map.of(
                "query", "{ currentUser { id username } }"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.data.currentUser.username")
            .isEqualTo("alice");
~~~

If using Basic Authentication:

~~~java
.headers(headers -> headers.setBasicAuth("alice", "password"))
~~~

If the application uses cookie-based sessions, send cookies via `cookie()` or `cookies()` on the request. When Spring Security enables CSRF protection for `POST`, tests must send CSRF tokens using Spring Security's test support; do not disable CSRF in production just to make tests easier.

Distinguish between two types of authorization:

- HTTP security blocking a request before GraphQL, such as unauthenticated access: assert HTTP 401 or 403 depending on configuration.
- Field-level authorization inside GraphQL: the request can enter GraphQL execution and return errors in `errors` with HTTP 200.

Test both cases to confirm that security filters and resolver/service-level authorization behave properly.

## Testing custom response headers

If the application uses a `WebGraphQlInterceptor` to add a correlation ID or metadata to the HTTP response, WebTestClient can verify the header:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Request-Id")
        .expectBody()
        .jsonPath("$.data.greeting").isEqualTo("Hello");
~~~

To assert a specific value:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectHeader()
        .valueEquals("X-Request-Id", "test-request-123");
~~~

If the header is meant to be read by browser JavaScript in cross-origin requests, also verify `Access-Control-Expose-Headers` in the response.

## Testing CORS preflight

Browsers may send an `OPTIONS` preflight request before a GraphQL `POST` when cross-origin requests include headers or content types requiring preflight. You can verify the CORS response:

~~~java
import org.springframework.http.HttpHeaders;

webTestClient.options()
        .uri("/graphql")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST")
        .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,authorization")
        .exchange()
        .expectHeader()
        .valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com");
~~~

Do not hard-assume status 200 versus 204, as the result depends on CORS configuration and the web stack. What matters is that the response includes headers allowing the origin, method, and request headers according to policy.

CORS does not replace authentication or authorization. Tests should verify that unknown origins are not granted access and that credentials are not enabled alongside a wildcard origin.

## Checking GraphQL response headers and content type

Some applications return `application/graphql-response+json`. You can verify the media type:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.parseMediaType(
                "application/graphql-response+json"))
        .bodyValue(Map.of("query", "{ greeting }"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .contentTypeCompatibleWith(
                MediaType.parseMediaType(
                        "application/graphql-response+json"));
~~~

If the application only supports legacy `application/json`, use the matching `Accept` header and test according to actual configuration. Do not hard-code one response media type when the API is configured for different content negotiation.

## WebTestClient and @GraphQlTest serve different purposes

Spring Boot's `@GraphQlTest` focuses on GraphQL controllers and GraphQL infrastructure. That slice does not create HTTP transport or a server. Therefore, `@GraphQlTest` is suited for testing mappings, argument binding, and GraphQL execution with mocked collaborators, but it cannot replace HTTP endpoint tests with `WebTestClient`.

Choosing a test approach:

| Goal | Appropriate approach |
| --- | --- |
| Test resolver/controller mappings | `@GraphQlTest` or `ExecutionGraphQlServiceTester` |
| Test `WebGraphQlHandler` interceptor chain | `WebGraphQlTester` |
| Test HTTP path, method, headers, content negotiation | `WebTestClient` |
| Test GraphQL data/errors over HTTP | `HttpGraphQlTester` over `WebTestClient` |
| Test live server, connector, and port | `@SpringBootTest(RANDOM_PORT)` with `WebTestClient` |
| Test WebSocket subscriptions | `WebSocketGraphQlTester` |

A balanced test suite includes unit/slice tests for GraphQL logic alongside a targeted set of HTTP integration tests to verify the full request path.

## Timeouts and test data isolation

WebTestClient sends reactive requests, while its assertion API waits for responses within a timeout. When GraphQL resolvers call databases or external services, configure sensible timeouts so tests never hang indefinitely.

With `HttpGraphQlTester`, you can configure a response timeout:

~~~java
import java.time.Duration;

HttpGraphQlTester tester =
        HttpGraphQlTester.builder(webTestClient.mutate())
                .responseTimeout(Duration.ofSeconds(5))
                .build();
~~~

Test data should stay independent across tests:

- Seed data with explicit, reproducible IDs.
- Clean up data after tests when using a real database.
- Avoid depending on test execution order.
- With `RANDOM_PORT`, note that client and server run in separate threads/transactions; a test-side transaction rollback will not automatically roll back transactions committed on the server.
- Mock external services when the goal is to test HTTP/GraphQL mapping; use dedicated integration tests when verifying a real database or downstream service.

When running tests in parallel, avoid sharing mutable data or a single shared account across tests if doing so could introduce race conditions.

## Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| 404 when calling GraphQL | Wrong endpoint path or GraphQL endpoint not exposed | Check `spring.graphql.path` and web configuration |
| 405 when calling POST | Route or security/proxy only permits another method | Check `GraphQlHttpHandler` and route predicates |
| 415 Unsupported Media Type | `Content-Type` is not a supported JSON media type | Send `Content-Type: application/json` |
| HTTP 200 yet test should fail | GraphQL response contains `errors` | Check `$.errors` or use `HttpGraphQlTester.errors()` |
| Expected 400 but got 200 for invalid document | Client uses legacy `Accept: application/json` mode | Check `Accept` and use `application/graphql-response+json` if you want GraphQL-over-HTTP semantics |
| JSONPath cannot find data | Path omits or misstates the `data` root | WebTestClient uses `$.data...`; `GraphQlTester.path()` is relative to `data` |
| Variables are not bound | Wrong variable name, missing `variables` object, or wrong type | Compare GraphQL declarations with keys in the JSON `variables` object |
| WebTestClient cannot be injected | Missing WebFlux test support or auto-configuration setup | Check the web stack and test dependencies |
| MockMvc test does not work through WebTestClient | Used `bindToApplicationContext` for an MVC context | Use `MockMvcWebTestClient` |
| Security test gets unexpected 403 | CSRF or authentication filter blocks before GraphQL | Send credentials/CSRF token matching policy |
| CORS preflight fails | Origin, method, or request header not allowed | Check CORS configuration |
| Test passes locally but fails on real server | Differences in connector, proxy, port, or TLS | Add integration tests with `RANDOM_PORT` and matching environment settings |
| HTTP GraphQL subscription test receives no stream | Subscriptions require a streaming transport | Use `WebSocketGraphQlTester` or a configured SSE transport |

## Principles for testing GraphQL with WebTestClient

When testing a GraphQL HTTP endpoint, keep these principles in mind:

1. Send protocol-compliant requests. Use `POST`, the GraphQL path, and a JSON body with `query` and `variables` when needed.
2. Verify both HTTP and GraphQL. Check status, headers, content type, and `data`/`errors`.
3. Understand content negotiation. Legacy `application/json` and `application/graphql-response+json` have different status semantics for parse/validation errors.
4. Choose the right binding environment. WebFlux uses `bindToApplicationContext`; MVC uses `MockMvcWebTestClient`; live servers use `bindToServer` or Boot `RANDOM_PORT`.
5. Use `HttpGraphQlTester` for GraphQL assertions. `WebTestClient` remains useful when inspecting low-level HTTP transport details.
6. Test security and CORS. Verify both HTTP filters and field-level authorization errors.
7. Verify custom headers. Correlation IDs, cookies, and exposed headers should be checked on actual responses.
8. Keep test data independent. Avoid order dependencies, shared mutable state, or invalid transaction rollback assumptions.
9. Do not use `@GraphQlTest` as a substitute for transport tests. That slice does not expose an HTTP endpoint.
10. Use `WebSocketGraphQlTester` for subscriptions. Plain HTTP `WebTestClient` does not test the WebSocket lifecycle.

WebTestClient enables testing GraphQL across the exact HTTP boundary external clients use. Combined with HttpGraphQlTester, tests can verify HTTP method, path, headers, content negotiation, and status while also checking structured data, variables, and GraphQL errors. Distinguishing HTTP errors from errors inside the GraphQL response, choosing the right mock or live server setup, and verifying security and CORS help catch transport configuration bugs early that isolated resolver tests cannot see.

## References

- [Spring for GraphQL - Testing and HttpGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL - HTTP Server Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot - Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 - AutoConfigureWebTestClient package and testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework - WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
