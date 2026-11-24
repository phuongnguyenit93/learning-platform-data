# Synchronous HTTP Testing with an Assertion-Oriented API

`RestTestClient` is an HTTP client for testing server applications in Spring Framework. It uses `RestClient` to build and send requests, while providing an assertion API for responses. Writing tests closely resembles calling a real REST API: build a request, call `exchange()`, and then verify status, headers, and body using built-in expectations.

A key advantage of `RestTestClient` is its synchronous API. Tests do not need to work with `Mono`, `Flux`, or reactive operators to read responses. The client can connect to a running server for end-to-end testing, or bind to Spring MVC through MockMvc to test controllers without opening an HTTP port.

`RestTestClient` was introduced in Spring Framework 7.0. If a project uses Spring Framework 6.x or Spring Boot 3.x, this API is not available yet; in that case, continue using `MockMvc`, `WebTestClient`, or `RestClient` depending on the application type and testing goal. With Spring Boot 4.x based on Spring Framework 7.x, you can use `RestTestClient` from the Spring testing dependency.

## 1. Request and Assertion Flow

The API has two clear halves. Before `exchange()`, request creation is similar to `RestClient`. After `exchange()`, `RestTestClient` returns a response specification to verify the result.

```text
RestTestClient
    |
    v
HTTP method + URI + headers + body
    |
    v
exchange()
    |
    v
ResponseSpec
    |
    +--> expectStatus()
    +--> expectHeader()
    +--> expectBody()
    +--> expectAll()
    |
    v
Test pass / assertion failure
```

A typical test:

```java
client.get()
        .uri("/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody(Person.class)
        .consumeWith(result ->
                assertThat(result.getResponseBody())
                        .isEqualTo(new Person(1L, "Jane")));
```

Expectations make the test's intent easy to read: the endpoint must return `200`, the response must be JSON, and the body must represent the expected person. If an expectation fails, the test reports an error at the corresponding assertion step.

## 2. Creating RestTestClient and Choosing the Test Scope

Before creating the client, choose where requests will be sent. `RestTestClient` offers multiple binding options to fit the test scope.

| Binding mode | Where requests are handled | When to use |
|---|---|---|
| `bindToController(...)` | The provided controller, via mock request/response | Testing one or a few specific controllers |
| `bindToApplicationContext(context)` | Spring MVC infrastructure and configuration loaded in `WebApplicationContext` | Testing controllers together with advice, converters, interceptors, filters, and MVC configuration |
| `bindToRouterFunction(router)` | The provided functional endpoint `RouterFunction` | Testing routes and handlers in Spring MVC's functional style |
| `bindToServer()` | Running HTTP server | End-to-end testing over real HTTP |

### Binding Directly to a Controller

This is the shortest approach when a test only needs a single controller and the components that controller uses. No real server needs to be started:

```java
import org.springframework.test.web.servlet.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

The controller can be an instance created directly in the test. If the controller needs dependencies, pass test dependencies through the constructor, or bind to the application context when you want Spring to manage bean creation and wiring.

### Binding to an Application Context

When you need to verify full MVC configuration, bind to `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonControllerTests {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

`WebConfig` is the application's Spring MVC configuration or a test configuration. This approach brings components registered in the context into the mock request/response processing pipeline, such as controllers, `@ControllerAdvice`, message converters, and interceptors.

### Binding to a Functional Router

For Spring MVC functional endpoints, you can bind directly to a `RouterFunction`:

```java
RestTestClient client = RestTestClient
        .bindToRouterFunction(personRoutes)
        .build();
```

This tests the router's request predicates and handlers using mock requests/responses. If you need application-context-level MVC configuration, use `bindToApplicationContext(...)` for broader testing.

### Binding to a Running Server

When you need to verify the entire real HTTP path, create a client connecting to the server:

```java
RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

In tests that start a server themselves, the base URL is usually taken from a random port assigned by the test framework. In that case, the test passes through the actual HTTP client and server connector. It can catch issues with ports, HTTP transport, TLS, or server configuration that mock setups do not cover.

## 3. Complete Example with bindToController

Suppose an API returns a person's information:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record Person(long id, String name) {
}

@RestController
class PersonController {

    @GetMapping("/persons/{id}")
    Person findById(@PathVariable long id) {
        return new Person(id, "Jane");
    }
}
```

Test using JUnit Jupiter and `RestTestClient`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.assertj.core.api.Assertions.assertThat;

class PersonControllerTests {

    private RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToController(new PersonController())
                .build();
    }

    @Test
    void returnsPersonAsJson() {
        client.get()
                .uri("/persons/{id}", 1)
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody(Person.class)
                .consumeWith(result ->
                        assertThat(result.getResponseBody())
                                .isEqualTo(new Person(1L, "Jane")));
    }
}
```

`bindToController(...)` creates a mock MVC setup for the provided controller. The test calls the endpoint using a URI template, requests JSON, and decodes the response body into `Person`. `consumeWith(...)` allows using AssertJ or custom assertions when built-in expectations are not expressive enough for what needs to be checked.

In this example the controller has no dependencies. If the controller needs a service, you can create a fake or mock service and pass it into the controller's constructor. If you want to test real dependency injection and bean configuration, use `bindToApplicationContext(...)`.

## 4. Building Requests with the Synchronous API

`RestTestClient`'s request-building methods are similar to `RestClient`. You can specify the HTTP method, URI, query parameters, headers, content type, and body.

```java
record CreatePersonRequest(String name) {
}

client.post()
        .uri("/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Request-Source", "integration-test")
        .body(new CreatePersonRequest("Ada"))
        .exchange()
        .expectStatus().isCreated();
```

Commonly used elements:

| Element | Role |
|---|---|
| `get()`, `post()`, `put()`, `patch()`, `delete()` | Select the HTTP method |
| `uri(...)` | Set the path, URI template, or URI builder |
| `accept(...)` | Declare the media type the client wants to receive |
| `contentType(...)` | Declare the media type of the request body |
| `header(...)`, `headers(...)` | Add headers to the request |
| `body(object)` | Send an object for a message converter to serialize |
| `exchange()` | Execute the request and transition to response assertions |

`Content-Type` and `Accept` have different meanings. `Content-Type` states the format of the body being sent; `Accept` states the format the client wants in the response. JSON tests usually set both when sending JSON and expecting JSON back.

For query parameters or path variables, use a URI template or builder instead of manual string concatenation:

```java
client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/persons")
                .queryParam("name", "Ada Lovelace")
                .queryParam("active", true)
                .build())
        .exchange()
        .expectStatus().isOk();
```

The URI builder is responsible for encoding required characters. This ensures tests properly send values containing spaces, Unicode, or special characters.

## 5. Assertions for Status and Headers

After `exchange()`, you can check the status using built-in matchers:

```java
client.get()
        .uri("/persons/999")
        .exchange()
        .expectStatus().isNotFound();
```

Common assertions include `isOk()`, `isCreated()`, `isAccepted()`, `isNoContent()`, `isBadRequest()`, `isUnauthorized()`, `isForbidden()`, `isNotFound()`, and `is5xxServerError()`. For specific status codes, you can use matchers accepting a status code or the API's corresponding predicates.

Headers can also be checked directly:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().exists("ETag")
        .expectHeader().valueEquals("X-Api-Version", "v1");
```

If you only need to check for a compatible media type, use `contentTypeCompatibleWith(...)`. This is useful when the response includes parameters such as `charset` while still being the same media type.

You can group multiple expectations with `expectAll(...)`:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectAll(
                spec -> spec.expectStatus().isOk(),
                spec -> spec.expectHeader()
                        .contentType(MediaType.APPLICATION_JSON),
                spec -> spec.expectHeader().exists("ETag"));
```

Expectations inside `expectAll(...)` are evaluated like soft assertions, so the test can report multiple failures in a single run instead of stopping at the first assertion.

## 6. Assertions for the Response Body

`RestTestClient` provides several ways to read the body depending on the response type.

### Decoding into an Object

When the response represents an object:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .consumeWith(result -> {
            Person person = result.getResponseBody();
            assertThat(person).isNotNull();
            assertThat(person.name()).isEqualTo("Jane");
        });
```

`expectBody(Person.class)` uses a message converter to decode the response body. You can then assert on the object using AssertJ or custom logic.

### Checking JSON with JSONPath

If you only need to inspect a few fields, there is no need to deserialize the entire object:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(1)
        .jsonPath("$.name").isEqualTo("Jane");
```

`expectBody()` without a target type allows inspecting raw JSON with JSONPath or comparing JSON. For `.json(...)`, JSONassert must be on the classpath. JSONPath also requires the corresponding supporting library in test dependencies.

### Comparing the Full JSON

When the JSON structure is the contract to verify:

```java
client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 1,
                  "name": "Jane"
                }
                """);
```

JSON comparison is appropriate when fields, data types, and body structure all matter. If only one field is the target of the test, JSONPath usually makes the test less brittle to unrelated changes.

### Responses Without a Body

For `204 No Content` or endpoints that return no content:

```java
client.delete()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

If you do not need content assertions but still want to release the response body, you can use `.expectBody(Void.class)`. Consuming the response body matters when leak detection is enabled for pooled buffers; skipping body consumption can trigger detection of unreleased buffers.

## 7. Checking Bodies with Generic Types

When a response is a collection or nested generic type, `Class<T>` cannot fully express type parameters. Use `ParameterizedTypeReference`:

```java
import org.springframework.core.ParameterizedTypeReference;

List<Person> people = client.get()
        .uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(new ParameterizedTypeReference<List<Person>>() {
        })
        .returnResult()
        .getResponseBody();

assertThat(people)
        .extracting(Person::name)
        .containsExactly("Jane", "Jason");
```

`ParameterizedTypeReference` retains generic information at runtime so the message converter knows to decode JSON into `List<Person>`. Using only `List.class` may cause elements to be decoded as maps instead of `Person`.

## 8. Retrieving Response Results for Custom Assertions

When built-in assertions are not enough, you can retrieve `EntityExchangeResult`:

```java
import org.springframework.test.web.servlet.client.EntityExchangeResult;

EntityExchangeResult<Person> result = client.get()
        .uri("/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .returnResult();

Person person = result.getResponseBody();
assertThat(person).isEqualTo(new Person(1L, "Jane"));
assertThat(result.getResponseHeaders().getFirst("ETag")).isNotBlank();
```

The result contains the decoded response body, response headers, and exchange metadata. You can use it when complex assertions are needed or when passing the result to a shared helper.

## 9. Using AssertJ Integration

In addition to the expectation chain, `RestTestClient` supports AssertJ integration via `RestTestClientResponse`. This class wraps a response specification or exchange result for AssertJ-style assertions:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.test.web.servlet.client.RestTestClientResponse;

import static org.assertj.core.api.Assertions.assertThat;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/1")
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(
        MediaType.APPLICATION_JSON);
```

This approach is useful when the team is already comfortable with AssertJ or wants to build reusable assertion helpers. If you only need to check status, headers, and simple JSON fields, the built-in expectation chain is often easier to read.

You can obtain an `ExchangeResult` first and wrap it with `RestTestClientResponse.from(result)` to combine both styles. There is no need to use both approaches in a single test unless it improves assertion clarity.

## 10. Configuring a Shared Client

After choosing a binding, you can configure client-side properties such as base URL, default headers, or client filters:

```java
RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .baseUrl("/api")
        .defaultHeader("X-Client", "test-suite")
        .build();
```

Tests can then call `.uri("/persons/1")` and the default header is added to the request. Client filters can be configured to log or add metadata to test requests. These configurations belong to the client side; they do not replace filters or interceptors belonging to the server application.

Avoid putting per-test varying data into default headers of a shared client. If tests run in parallel and each test needs a different user or tenant, set the header on the corresponding request:

```java
client.get()
        .uri("/persons/1")
        .header("X-Tenant-Id", "tenant-a")
        .exchange()
        .expectStatus().isOk();
```

## 11. Choosing Between Mock Setup and a Real Server

`RestTestClient` works for both mock request/response and end-to-end HTTP. These two scopes provide different evidence.

| Characteristic | Controller/context/router binding | Server binding |
|---|---|---|
| Opens HTTP port | No | Yes, server is running |
| Speed | Usually faster | Slower due to HTTP transport and server lifecycle |
| Tests routing and MVC handlers | Yes | Yes |
| Tests server connector, TLS, port | No | Yes |
| Tests proxy/network deployment | No | Only when tests pass through that infrastructure |
| Suitable for many small API tests | Yes | Can be more resource-intensive |

A test bound to a controller can prove that the controller returns the right status and JSON. It does not prove that the real server has TLS enabled properly or that a reverse proxy forwards headers correctly. When you need to verify those factors, add tests against a real server.

If using Spring Boot tests with a random server port, you can configure `RestTestClient` from the base URL provided by the test framework. Tests must ensure the server is ready before sending requests and close resources after finishing.

## 12. Distinguishing RestTestClient, RestClient, MockMvc, and WebTestClient

These APIs have similar names but serve different purposes:

| API | Primary role | How checks are performed |
|---|---|---|
| `RestClient` | Synchronous HTTP client for applications | Call `retrieve()` or `exchange()` and handle responses in application code |
| `RestTestClient` | Synchronous HTTP test client | Send requests then use expectations/assertions to verify responses |
| `MockMvc` | API for testing Spring MVC at the mock servlet level | `perform(...)`, `andExpect(...)`, `andReturn()` |
| `WebTestClient` | Test client with fluent API supporting WebFlux and its binding modes | `exchange()` and expectations; can work with publishers/reactive streams |

`RestTestClient` is designed as the synchronous counterpart to the `WebTestClient` experience, using `RestClient` on the request-sending side. If tests focus on Spring MVC and you want the familiar request/response API of a synchronous REST client, `RestTestClient` is a good fit. If the application uses WebFlux and needs to test reactive behavior or streaming, `WebTestClient` is generally more suitable.

`MockMvc` remains useful when you need servlet-testing-specific APIs, such as checking session, flash attributes, request dispatch, or servlet details. `RestTestClient` can bind via MockMvc while offering an HTTP-client-style facade and different assertions.

## 13. Version and Dependencies

`RestTestClient` was added in Spring Framework 7.0. The API resides in package:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
```

It belongs to the `spring-test` module, which is usually already on the test classpath when using the Spring Boot test starter. With manual dependency configuration, you need to add `spring-test` in test scope along with supporting test dependencies such as JUnit Jupiter, AssertJ, JSONassert, or JSONPath if using those assertions.

Minimal Gradle example for the test classpath:

```groovy
dependencies {
    testImplementation "org.springframework:spring-test"
    testImplementation "org.junit.jupiter:junit-jupiter"
    testImplementation "org.assertj:assertj-core"
}
```

In a Spring Boot project, let Spring Boot dependency management manage the versions of Spring Framework and test dependencies rather than picking a `spring-test` version different from the rest of the framework.

If the IDE cannot find `RestTestClient`, check the Spring Framework version and test classpath before checking imports. Adding an import cannot make the API appear in Spring Framework 6.x.

## 14. Common Mistakes When Writing Tests

| Practice | Problem | Better approach |
|---|---|---|
| Using `RestTestClient` with Spring Framework 6.x | The API is only available from Framework 7.0 onward | Check the version or use the test API available in that version |
| Confusing `RestTestClient` with `RestClient` | `RestClient` does not provide a test expectation facade | Use `RestTestClient` in test sources |
| Using `bodyValue(...)` like WebClient | The `RestClient`-style request API uses `.body(object)` | Use `.body(request)` |
| Binding to a controller while expecting the entire application context to load | Controller binding only creates a mock setup for the provided controller | Bind to `WebApplicationContext` if full MVC configuration is needed |
| Checking status only | Does not verify the representation the client receives | Verify both content type and important body fields |
| Comparing full JSON when only one field is needed | Tests break easily on unrelated field changes | Use JSONPath for the target field |
| Using `List.class` for a JSON collection | Loses generic element type information | Use `ParameterizedTypeReference<List<T>>` |
| Not consuming the response body | Can trigger pooled buffer warnings when leak detection is enabled | Use `expectBody()` or `expectBody(Void.class)` |
| Using mock setup to conclude TLS/server connector works | No real HTTP server in the test | Add tests bound to a running server |

## 15. Workflow for Writing a Synchronous HTTP Test

1. Confirm the API belongs to Spring MVC and the framework version supports `RestTestClient`.
2. Choose the scope: controller, application context, functional router, or real server.
3. Create the client once for the test fixture and configure base URL/default headers if needed.
4. Build the request using HTTP method, URI, headers, content type, and body like a real client.
5. Call `exchange()` to execute the request.
6. Check status and headers with appropriate expectations.
7. Decode the body into an object, check JSONPath, compare JSON, or retrieve `EntityExchangeResult` as needed.
8. Use `expectAll(...)` when you want to report multiple expectation failures in the same test.
9. Consume the response body and close real server resources if the test manages the server itself.
10. Add end-to-end tests when you need to verify HTTP transport, TLS, or deployment infrastructure configuration.

## 16. References

- [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html): binding modes, request workflow, built-in assertions, and AssertJ integration.
- [Spring Framework Javadoc — `RestTestClient`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/client/RestTestClient.html): synchronous client API for server testing.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): introduces RestTestClient as the synchronous counterpart to WebTestClient.
- [Spring Framework Reference — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): synchronous HTTP client API that RestTestClient uses to execute requests.

`RestTestClient` enables synchronous, assertion-rich HTTP testing: requests are built with a `RestClient`-style API, and responses are verified via an expectation chain or AssertJ. Choose the right binding for the scope being tested, consume the body after exchange, and use a real server when evidence of HTTP transport or deployment infrastructure is required.
