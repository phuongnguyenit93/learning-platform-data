# Asserting Status, Headers, DTOs, and JSON

When testing a REST API, the HTTP response needs to be verified across multiple layers: the status code indicates the processing outcome, headers describe the response, and the body carries the data used by the client. A `200 OK` response can still be wrong if `Content-Type` is incorrect, an important header is missing, or the JSON cannot be converted into the DTO the client expects.

Spring Framework 7.0 introduces `RestTestClient`, an HTTP client for testing server applications. This client uses `RestClient` to execute requests and adds a fluent API to assert responses. It can be bound to a controller or `WebApplicationContext` to test Spring MVC with mock requests/responses, or connected to a running server for end-to-end testing.

`RestTestClient` supports two main assertion styles: the built-in expectation chain after `exchange()` and AssertJ integration. In this lesson, we focus on the expectation style because it clearly expresses the order of checking status, headers, and body; and then converting the response into a DTO or generic type when needed.

## 1. What Is `RestTestClient` and When to Use It?

`RestTestClient` resides in package `org.springframework.test.web.servlet.client`. It provides a way to send HTTP requests and verify responses for Spring MVC applications. The request-building API is close to `RestClient`; the difference appears after the `exchange()` call, when `RestTestClient` provides `expectStatus()`, `expectHeader()`, and `expectBody()`.

Core concepts:

| Component | Role |
| --- | --- |
| `RestTestClient` | Builds requests and provides the response assertion API. |
| `RestTestClient.bindToController(...)` | Tests selected controllers with MockMvc without needing a real server. |
| `RestTestClient.bindToApplicationContext(...)` | Loads Spring MVC configuration from `WebApplicationContext` and processes requests with MockMvc. |
| `RestTestClient.bindToRouterFunction(...)` | Tests functional endpoints declared with `RouterFunction`. |
| `RestTestClient.bindToServer()` | Connects to a running HTTP server for end-to-end testing. |
| `exchange()` | Sends the request and begins the response assertion phase. |
| `expectStatus()`, `expectHeader()`, `expectBody()` | Asserts response status, headers, and content. |

`RestTestClient` was introduced in Spring Framework 7.0. Projects need the corresponding Spring Test version aligned with the Spring Framework version in use. This is a Spring MVC Test API; if you are testing a reactive WebFlux application, look at `WebTestClient`.

Do not confuse `RestTestClient` with `RestClient`. `RestClient` is the HTTP client used inside the application to call external services. `RestTestClient` is a server testing tool: it sends requests to the application under test and verifies the responses the application returns.

## 2. Choosing How to Initialize the Client

Before writing assertions, determine what kind of server requests will be sent to. The binding mode determines the test scope and which Spring components participate.

### Binding Directly to a Controller

When you only need to test one or a few controllers, you can pass the controller instance directly:

```java
import org.springframework.test.web.servlet.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

This setup uses MockMvc's mock requests and responses and does not start an HTTP server. It is suitable for checking the mapping, binding, and responses of the selected controller. Controller dependencies and additional MVC components must be supplied via the corresponding standalone configuration.

### Binding to `WebApplicationContext`

When you want to test controllers together with loaded Spring MVC configuration, bind to `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonControllerContextTest {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

`@SpringJUnitConfig` loads the Spring configuration for the test. `bindToApplicationContext(...)` uses that web context to process requests through the mock Spring MVC infrastructure. This approach is suitable when you need to verify component scanning, controllers, converters, controller advice, interceptors, and beans configured in the context.

### Binding to `RouterFunction`

For Spring MVC functional endpoints, you can bind directly to one or more `RouterFunction`s:

```java
RestTestClient client = RestTestClient
        .bindToRouterFunction(route)
        .build();
```

This setup also uses mock requests/responses and does not require a running server. It is useful when the application declares routes in functional style instead of annotated controllers.

### Binding to a Running Server

When you need to test requests over the real HTTP stack, connect to a running server:

```java
RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

This is the choice for end-to-end testing. Requests go through a real HTTP client and server, so additional factors such as network ports, servlet container, filter chain, and server configuration can be verified. The test must start the server before making requests.

### Binding to an Existing `MockMvc`

If the project already has a `MockMvc` instance, you can pass that instance in:

```java
RestTestClient client = RestTestClient
        .bindTo(mockMvc)
        .build();
```

This is useful when `MockMvc` has already been customized with builders or custom settings. `RestTestClient` uses that MockMvc as the server handling requests.

## 3. Request Structure and Response Workflow

`RestTestClient`'s request API is similar in style to `RestClient`. You choose the HTTP method, URI, headers, content type, and body if needed; then call `exchange()` to send the request.

```text
RestTestClient
      |
      v
client.get() / post() / put() / delete()
      |
      v
uri(...), accept(...), header(...), body(...)
      |
      v
exchange()
      |
      v
ResponseSpec
      |
      +--> expectStatus()
      |
      +--> expectHeader()
      |
      +--> expectBody()
      |       |
      |       +--> JSON / JSONPath
      |       +--> DTO / generic type
      |       +--> empty body
      |
      v
End assertions or obtain ExchangeResult
```

GET request example:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectBody();
```

`accept(...)` declares the response type the client expects. `exchange()` sends the request and returns `ResponseSpec`, from which we continue inspecting the response.

## 4. Asserting HTTP Status

The status code represents the request outcome according to the HTTP contract. `RestTestClient` provides `expectStatus()` with group matchers and exact-code matchers.

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk();
```

Commonly used matchers:

| Matcher | Status |
| --- | --- |
| `isOk()` | 200 OK |
| `isCreated()` | 201 Created |
| `isAccepted()` | 202 Accepted |
| `isNoContent()` | 204 No Content |
| `isBadRequest()` | 400 Bad Request |
| `isUnauthorized()` | 401 Unauthorized |
| `isForbidden()` | 403 Forbidden |
| `isNotFound()` | 404 Not Found |
| `is3xxRedirection()` | Any status in the 3xx group |
| `is4xxClientError()` | Any status in the 4xx group |
| `is5xxServerError()` | Any status in the 5xx group |

When you need a specific status without a dedicated matcher, use `isEqualTo(...)`:

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isEqualTo(200);
```

Choose the assertion level matching the contract. If the API requires `201 Created` after creating a resource, `isCreated()` expresses that more clearly than `is2xxSuccessful()`. If you only need to confirm the response belongs to the success group, a group matcher may be enough.

### Testing HTTP Errors

Do not test only the happy path. You can verify the status for a non-existent resource:

```java
client.get()
        .uri("/api/persons/999")
        .exchange()
        .expectStatus().isNotFound();
```

After verifying the status, you can continue checking the error body if the API publishes a JSON error response:

```java
client.get()
        .uri("/api/persons/999")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(ApiError.class)
        .isEqualTo(new ApiError("PERSON_NOT_FOUND", "Person 999 was not found"));
```

## 5. Asserting Response Headers

Headers provide metadata about the response, such as `Content-Type`, `Location`, `Cache-Control`, `ETag`, or application-specific headers. Use `expectHeader()` after `exchange()` to check them.

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().exists("X-Request-Id")
        .expectHeader().valueEquals("X-API-Version", "v1");
```

Commonly used matchers:

| Matcher | Meaning |
| --- | --- |
| `contentType(MediaType)` | Compares `Content-Type` against a specific value. |
| `contentTypeCompatibleWith(MediaType)` | Checks for a compatible media type, allowing parameter differences like charset. |
| `exists(name)` | Header exists. |
| `doesNotExist(name)` | Header does not exist. |
| `valueEquals(name, values...)` | Compares header values with expected values. |
| `valueEquals(name, long)` | Compares a numeric header value. |
| `valueMatches(name, pattern)` | Matches the first header value against a regular expression. |
| `location(uri)` | Checks the `Location` header. |
| `contentLength(length)` | Checks `Content-Length`. |

### `contentType` and `contentTypeCompatibleWith`

These two matchers differ in strictness:

```java
.expectHeader().contentType(MediaType.APPLICATION_JSON)
```

checks that `Content-Type` equals the expected value. Meanwhile:

```java
.expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
```

checks for a compatible media type. For example, a response might declare `application/json;charset=UTF-8`; when you do not need to constrain parameters, the compatible matcher is usually more appropriate.

### Checking the Location Header on Resource Creation

Resource-creation APIs often return `201 Created` and a `Location` pointing to the new resource:

```java
client.post()
        .uri("/api/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreatePersonRequest("Lan"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().location("/api/persons/42");
```

The test verifies both the creation result and the URL clients can use to access that resource. If the application returns an absolute URI instead of a relative URI, the expected value needs to match the actual configuration.

## 6. Converting the Response Body into a DTO

When the JSON body represents a concrete object, use `expectBody(Class<T>)` to deserialize it into a DTO. Then you can compare the object against an expected value.

DTO:

```java
public record PersonResponse(long id, String name, String status) {
}
```

Test:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(PersonResponse.class)
        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
```

`expectBody(PersonResponse.class)` reads the body and converts it into a `PersonResponse` instance. `isEqualTo(...)` compares the converted instance with the expected object. Records work well with this style of check because records provide value-based equality. For regular classes that do not override `equals()`, you can use `value(...)` to check properties.

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(PersonResponse.class)
        .value(person -> {
            assertThat(person.id()).isEqualTo(1L);
            assertThat(person.name()).isEqualTo("Lan");
            assertThat(person.status()).isEqualTo("ACTIVE");
        });
```

`value(...)` accepts a `Consumer` to perform custom assertions on the deserialized object. You can use it when only some fields need checking or when verifying relationships between properties.

## 7. Converting the Body into a List or Generic Type

When a response is a JSON array or contains generic types, passing only a raw class can lose element type information. Use the overload accepting `ParameterizedTypeReference`.

Example response as a list of users:

```json
[
  {"id": 1, "name": "Lan", "status": "ACTIVE"},
  {"id": 2, "name": "Minh", "status": "INACTIVE"}
]
```

Test converting into `List<PersonResponse>`:

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<PersonResponse>> peopleType =
        new ParameterizedTypeReference<>() {
        };

client.get()
        .uri("/api/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(peopleType)
        .isEqualTo(List.of(
                new PersonResponse(1L, "Lan", "ACTIVE"),
                new PersonResponse(2L, "Minh", "INACTIVE")
        ));
```

`ParameterizedTypeReference<List<PersonResponse>>` preserves generic element type information. If `List.class` is used, the JSON mapper might only produce a list of maps instead of `PersonResponse`.

For nested generic responses, apply the same pattern:

```java
public record PageResponse<T>(int page, int size, List<T> content) {
}

ParameterizedTypeReference<PageResponse<PersonResponse>> pageType =
        new ParameterizedTypeReference<>() {
        };

client.get()
        .uri("/api/persons?page=0&size=2")
        .exchange()
        .expectStatus().isOk()
        .expectBody(pageType)
        .value(page -> {
            assertThat(page.page()).isZero();
            assertThat(page.size()).isEqualTo(2);
            assertThat(page.content()).hasSize(2);
            assertThat(page.content().get(0).name()).isEqualTo("Lan");
        });
```

The target type must be the full `PageResponse<PersonResponse>`, not just `PageResponse.class`. This allows the mapper to convert `content` elements into `PersonResponse`.

## 8. Checking Raw JSON with JSONAssert and JSONPath

Not every test needs to deserialize the body into a DTO. If you only want to verify the JSON structure or a few values, you can use `expectBody()` without passing a target type. This API allows inspecting raw content.

### Comparing JSON

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {
                  "id": 1,
                  "name": "Lan",
                  "status": "ACTIVE"
                }
                """);
```

The `.json(...)` matcher compares JSON content structurally rather than requiring a byte-for-byte identical response string. JSONAssert must be on the test classpath to use this JSON assertion.

### Extracting Values with JSONPath

When you only care about a few fields:

```java
client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(1)
        .jsonPath("$.name").isEqualTo("Lan")
        .jsonPath("$.status").isEqualTo("ACTIVE");
```

Common JSONPath expressions:

| JSONPath | Content |
| --- | --- |
| `$.id` | The `id` field at the root level. |
| `$.address.city` | The city inside the `address` object. |
| `$[0].name` | The name of the first element in a JSON array. |
| `$.items[1].id` | The ID of the second element in `items`. |
| `$.items[*].name` | The names of all elements in `items`. |

JSONPath suits selective assertions. Typed conversion suits cases where you want to verify that the entire body can be read as a DTO or generic type.

## 9. Using `expectAll(...)` to Group Multiple Assertions

When chaining multiple `expect...` calls sequentially, a failing assertion stops the chain before subsequent assertions run. `expectAll(...)` lets all passed expectations run and aggregates failures.

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Request-Id"),
                response -> response.expectBody(PersonResponse.class)
                        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"))
        );
```

`expectAll(...)` is similar to AssertJ's soft assertions or JUnit Jupiter's `assertAll(...)`. It is useful when you want a single test run to report multiple mismatches instead of fixing errors one by one in order of the first assertion.

## 10. Responses Without a Body

Some endpoints return `204 No Content`, or return a success status without a body. In those cases, do not attempt to deserialize into a DTO.

To assert an empty body:

```java
client.delete()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

If you do not need to check response content and only want to release the body, you can use `expectBody(Void.class)`:

```java
client.delete()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody(Void.class);
```

Consuming the body is necessary in tests that enable leak detection for pooled buffers. If the response body is neither read nor released, buffer leak detectors may report an error.

## 11. Obtaining `EntityExchangeResult` for Custom Checks

When built-in matchers are not enough, you can end the expectation chain and obtain `EntityExchangeResult<T>`:

```java
EntityExchangeResult<PersonResponse> result = client.get()
        .uri("/api/persons/1")
        .exchange()
        .expectStatus().isOk()
        .expectBody(PersonResponse.class)
        .returnResult();

PersonResponse person = result.getResponseBody();
HttpHeaders responseHeaders = result.getResponseHeaders();

assertThat(person).isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
assertThat(responseHeaders.getFirst("X-API-Version")).isEqualTo("v1");
```

`returnResult()` returns the exchange result together with the converted body. You can retrieve the DTO, response headers, and request/response details for custom assertions. For generic types, the `returnResult(ParameterizedTypeReference<T>)` overload preserves type parameter information:

```java
EntityExchangeResult<List<PersonResponse>> result = client.get()
        .uri("/api/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody(peopleType)
        .returnResult();

List<PersonResponse> people = result.getResponseBody();
assertThat(people).hasSize(2);
```

When raw content is needed, parameterless `ResponseSpec.returnResult()` returns an `ExchangeResult` with the raw body. Choose the right result type to avoid manual re-deserialization.

## 12. Sending a Request with a Body and Verifying the Response

`RestTestClient` has a request-building API similar to `RestClient`. For POST, PUT, or PATCH, you can declare the content type and body object:

```java
public record CreatePersonRequest(String name) {
}

client.post()
        .uri("/api/persons")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new CreatePersonRequest("Lan"))
        .exchange()
        .expectStatus().isCreated()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody(PersonResponse.class)
        .value(person -> {
            assertThat(person.id()).isPositive();
            assertThat(person.name()).isEqualTo("Lan");
            assertThat(person.status()).isEqualTo("ACTIVE");
        });
```

`body(...)` uses message conversion to write the object into the request body. `contentType(...)` declares the outgoing format; `accept(...)` declares the desired response format. After `exchange()`, we verify status, headers, and body just like with GET.

If you need to send a JSON string directly, you can pass the string to `body(...)` and set `contentType(MediaType.APPLICATION_JSON)`. For DTOs, passing an object usually keeps the test closer to how real clients use HTTP message conversion.

## 13. Testing Against a Running Server

Setups bound to a controller or application context use mock requests/responses. They are great for fast MVC testing, but do not verify opening a port, transmitting over sockets, or real servlet container configuration.

For end-to-end testing, you can start the application on a random port with Spring Boot:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PersonHttpIntegrationTest {

    @LocalServerPort
    int port;

    RestTestClient client;

    @BeforeEach
    void setUp() {
        client = RestTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .build();
    }

    @Test
    void shouldReturnPersonOverHttp() {
        client.get()
                .uri("/api/persons/1")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody(PersonResponse.class)
                .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"));
    }
}
```

In this setup, the server must be started by Spring Boot before requests are sent. `RestTestClient.bindToServer()` creates a real HTTP client and `.baseUrl(...)` points to the application address. The test verifies responses traveling over the HTTP transport of the running server.

## 14. Distinguishing `RestTestClient`, `MockMvc`, and `WebTestClient`

These tools can all be used to test HTTP, but they serve different application styles and setups:

| Tool | Model | When suitable |
| --- | --- | --- |
| `MockMvc` | Servlet MVC testing API with mock requests/responses. | Testing Spring MVC and needing MockMvc's matcher APIs. |
| `RestTestClient` | Client based on `RestClient` with an assertion facade; can bind to MockMvc or a real server. | Wanting a consistent HTTP client style to check status, headers, and body of a server application. |
| `WebTestClient` | Reactive test client, typically used with WebFlux; can also connect to some other server types. | Testing WebFlux or when a reactive testing API is needed. |

`RestTestClient` does not replace every capability of `MockMvc`. When bound to MockMvc, it provides an HTTP client view of the response. If you need server-side MockMvc-specific assertions such as model, handler, or request attributes, you can continue using `MockMvc` and `MvcResult` directly.

`RestTestClient` is also not a tool for mocking a target server for an application's outbound `RestClient`. When you need to test application code calling an external HTTP service, use an appropriate mock server/client tool such as `MockRestServiceServer` or an HTTP mock server.

## 15. Common Mistakes When Asserting Responses

**Using a Spring version without `RestTestClient`.**

This API was introduced in Spring Framework 7.0. If the project uses Spring Framework 6.x, the `org.springframework.test.web.servlet.client.RestTestClient` package does not exist yet. Check dependency management and use aligned Spring versions.

**Forgetting to call `exchange()`.**

The `expectStatus()`, `expectHeader()`, and `expectBody()` methods belong to the response workflow after the request is sent. You must call `exchange()` before asserting on the response.

**Checking status while ignoring important headers.**

A success status does not guarantee the right content type or location. For JSON endpoints, check `Content-Type`; for resource-creation endpoints, consider checking `Location`.

**Comparing `Content-Type` too strictly.**

Responses may include parameters such as charset. Use `contentTypeCompatibleWith(...)` when you only need to verify a compatible media type; use `contentType(...)` when the full header value is part of the contract.

**Deserializing collections with raw `List.class`.**

Raw classes lose element types. Use `ParameterizedTypeReference<List<PersonResponse>>` to convert each element into the right DTO type.

**Using `isEqualTo(...)` with DTOs lacking value-based equality.**

Two regular class instances with identical data that do not override `equals()` can still be treated as unequal. Use records, implement proper equality, or use `value(...)`/`consumeWith(...)` to check properties.

**Not consuming the body.**

If tests run with leak detection for pooled buffers, call `expectBody(...)`, `expectBody().isEmpty()`, or an appropriate body-consuming method. Do not leave the response body unconsumed.

**Confusing mock server setup with end-to-end tests.**

`bindToController(...)` and `bindToApplicationContext(...)` process requests via MockMvc and do not start a real HTTP server. Use `bindToServer()` when you need to test networking and a running server.

## 16. Workflow for Testing Status, Headers, DTOs, and JSON

A response test can be organized in the following sequence:

1. Choose the appropriate setup: controller, application context, router function, existing MockMvc, or real server.
2. Create `RestTestClient` and configure base URL or default headers if needed.
3. Build the request with the appropriate HTTP method, URI, headers, content type, and body.
4. Call `exchange()` to send the request.
5. Assert status with `expectStatus()`.
6. Assert content type, location, and business headers with `expectHeader()`.
7. Convert the body into a DTO with `expectBody(Dto.class)` or a generic type with `expectBody(ParameterizedTypeReference)`.
8. If raw JSON checks are needed, use `expectBody().json(...)` or `jsonPath(...)`.
9. Use `expectAll(...)` when you want multiple assertions to execute even if one fails.
10. Obtain `EntityExchangeResult` when custom inspection of exchange data is needed.

Combined example:

```java
client.get()
        .uri("/api/persons/1")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Request-Id"),
                response -> response.expectBody(PersonResponse.class)
                        .isEqualTo(new PersonResponse(1L, "Lan", "ACTIVE"))
        );
```

This test simultaneously verifies status, content type, a custom header, and the response DTO. When one of the conditions is incorrect, the assertion output indicates which part of the HTTP contract was violated.

## Conclusion

`RestTestClient` in Spring Framework 7.0+ provides an HTTP client API for testing server application responses. After `exchange()`, use `expectStatus()` to verify the HTTP status code, `expectHeader()` to verify metadata, and `expectBody(...)` to convert the response into a DTO or generic type. For raw JSON, `expectBody().json(...)` and `jsonPath(...)` allow checking structure and specific values.

Choose the setup matching the scope under test: bind a controller or application context to test MVC with MockMvc, or bind a server for end-to-end testing. Combining status, headers, and body verifies the HTTP contract more thoroughly than checking only whether the request succeeded.

Official documentation: [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html).
