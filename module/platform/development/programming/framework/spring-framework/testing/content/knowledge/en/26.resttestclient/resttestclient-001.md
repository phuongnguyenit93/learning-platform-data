# RestTestClient from Spring Framework 7 and Its Relationship with RestClient

## 1. What Problem Does RestTestClient Solve?

Spring Framework 7.0 adds `RestTestClient`, an HTTP client for testing server applications. This API uses `RestClient` underneath to send requests, while providing matchers to assert response status, headers, and body.

Notably, `RestTestClient` can run in two ways:

- Send HTTP requests to a running server for end-to-end testing.
- Use the `MockMvc` infrastructure to test Spring MVC without starting a real server.

As a result, developers familiar with how `RestClient` builds requests can use nearly the same syntax to test endpoints. The main difference comes after the `exchange()` call: `RestTestClient` switches to a test assertion chain.

`RestTestClient` belongs to Spring Test and is available starting in Spring Framework 7.0. It is not present in Spring Framework 6.x, even if the project already uses `RestClient` from Spring Framework 6.1. Therefore, verify the project's Spring Framework version before using it.

## 2. Relationship Between RestClient and RestTestClient

`RestClient` is a synchronous HTTP client used in application code to call another REST API. It provides a fluent API to configure requests, send requests, and read responses. `RestTestClient` also executes requests synchronously, but its goal is to test a server application and verify responses with assertions.

Spring describes the two APIs as sharing the same request preparation up to the `exchange()` call. After that point, response handling differs:

| Aspect | `RestClient` | `RestTestClient` |
|---|---|---|
| Purpose | Call HTTP APIs from application code | Send HTTP requests to test a server and assert responses |
| Foundation | Spring's synchronous HTTP client | Uses `RestClient` to execute requests, adding a testing facade |
| Request preparation | Method, URI, headers, cookies, body, content type | Shares the same request preparation style up to `exchange()` |
| Response handling | `retrieve()`, read body or convert to `ResponseEntity`; can also use the `exchange(...)` callback | `exchange()` returns a response specification to call `expectStatus()`, `expectHeader()`, `expectBody()`, and other matchers |
| Testing infrastructure | Often combined with a mock web server or `MockRestServiceServer` when testing code that calls external APIs | Can bind to a controller, application context, router function, or running server |
| Where used | Application code and service-calling adapters | Test sources, typically with JUnit |

You can think of `RestTestClient` as a testing layer placed on top of `RestClient`'s request execution. It does not replace `RestClient` in business code and is not a reactive variant of `WebClient`.

Example of `RestClient` used in an application:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("https://inventory.example.test")
                .build();
    }

    InventoryItem findItem(long id) {
        return restClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

This is application code calling another system. Tests for `InventoryGateway` need to simulate responses from the inventory system, typically with `MockRestServiceServer`, MockWebServer, or WireMock. `RestTestClient` is primarily used in the opposite direction: sending requests to endpoints of the server application to test those endpoints' behavior.

## 3. Version and Dependencies

`RestTestClient` is provided in the `spring-test` artifact, in package:

```java
import org.springframework.test.web.servlet.client.RestTestClient;
```

With Gradle and a Spring Framework BOM or dependency management already managing versions:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
}
```

If the project uses Spring Boot, the `spring-boot-starter-test` dependency typically already brings `spring-test` onto the test classpath. However, Spring Framework 7.0 or higher must be used for `RestTestClient` to exist; simply adding `spring-test` 6.x does not make this API available.

The mock binding modes of `RestTestClient` rely on Spring MVC and MockMvc. Therefore, when using `bindToController`, `bindToApplicationContext`, or `bindToRouterFunction`, tests need the corresponding Spring MVC components on the classpath. To send requests to a running server with `bindToServer`, the client uses the synchronous HTTP client infrastructure.

## 4. Choosing the Right Binding Mode

Before creating the client, you need to determine which infrastructure the test should go through. `RestTestClient` provides the following main binding modes:

| Binding mode | When to use | Characteristics |
|---|---|---|
| `bindToController(...)` | Testing one or a few specific controllers | Uses mock request/response without needing a server; suitable when the controller has few dependencies or dependencies can be provided in the test. |
| `bindToApplicationContext(...)` | Testing Spring MVC configuration and multiple components participating in request processing | Uses `WebApplicationContext`, controllers, MVC infrastructure, and loaded configuration. |
| `bindToRouterFunction(...)` | Testing functional endpoints using Spring MVC's router function model | Uses mock request/response to invoke the route function. |
| `bindToServer()` | Testing over HTTP against a running application | Requires an accessible server; suitable for integration or end-to-end tests. |

### Binding Directly to a Controller

This is the shortest way to test a standalone controller:

```java
RestTestClient client = RestTestClient
        .bindToController(new PersonController())
        .build();
```

`bindToController(...)` creates a MockMvc environment for the provided controller. There is no TCP connection to a real server. If the controller needs services, repositories, or other beans, provide them via the constructor or use `bindToApplicationContext(...)` so Spring creates and injects dependencies.

### Binding to a WebApplicationContext

When you need to test MVC configuration, interceptors, controller advice, integrated filters, or multiple controllers, bind to a `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.servlet.client.RestTestClient;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitConfig(WebConfig.class)
class PersonContextTests {

    private RestTestClient client;

    @BeforeEach
    void setUp(WebApplicationContext context) {
        client = RestTestClient.bindToApplicationContext(context).build();
    }
}
```

`WebConfig` is the application configuration providing controllers and MVC infrastructure for the test. Spring Test loads the configuration and passes `WebApplicationContext` into the setup method. Requests are then processed through MockMvc with the loaded configuration.

### Binding to a Router Function

For functional endpoints on the Servlet stack, you can bind directly to a `RouterFunction`:

```java
import org.springframework.web.servlet.function.RouterFunction;

RouterFunction<?> routes = ...;

RestTestClient client = RestTestClient
        .bindToRouterFunction(routes)
        .build();
```

`routes` is the application's router function. This approach is useful when endpoints are declared with `RouterFunctions.route(...)` instead of `@RestController`.

### Binding to a Running Server

When you need to verify the full HTTP server, runtime configuration, filters, and network path, use `bindToServer()`:

```java
RestTestClient client = RestTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();
```

In this mode, the server must be started before the test sends requests. The base URL needs to contain the exact host and port of the running server. In tests using a random port, obtain the port assigned by the test environment instead of hardcoding `8080`.

## 5. Writing Tests with the Familiar Request API

The following example uses a simple controller returning a `Person`:

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

The test can send a request and assert the response as follows:

```java
import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.client.RestTestClient;

import static org.springframework.test.web.servlet.client.RestTestClient.bindToController;

class PersonControllerTests {

    private final RestTestClient client = bindToController(new PersonController()).build();

    @Test
    void returnsPersonAsJson() {
        client.get()
                .uri("/persons/{id}", 7)
                .accept(APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
                .expectBody(Person.class)
                .isEqualTo(new Person(7, "Jane"));
    }
}
```

The request is prepared using `get()`, `uri(...)`, and `accept(...)` in the same style as `RestClient`. After `exchange()`, the test uses `RestTestClient` assertions to verify the status, content type, and object decoded from the response body. For this JSON example, Jackson must be on the classpath for Spring MVC to convert objects to JSON.

## 6. Response Assertion Types

After `exchange()`, `RestTestClient` provides an expectation chain for tests to express the HTTP contract.

### Checking Status and Headers

```java
client.get()
        .uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON);
```

Status matchers can verify specific codes or status groups such as `is2xxSuccessful()`, `is4xxClientError()`, and `is5xxServerError()`. Header matchers can verify content type, header values, cache control, and other response attributes.

### Checking Multiple Conditions with `expectAll`

A normal matcher chain stops immediately at the first failing assertion. When you want to collect multiple failures in the same response, use `expectAll(...)`:

```java
client.get().uri("/persons/7")
        .exchange()
        .expectAll(
                response -> response.expectStatus().isOk(),
                response -> response.expectHeader()
                        .contentTypeCompatibleWith(APPLICATION_JSON),
                response -> response.expectHeader().exists("X-Correlation-Id")
        );
```

`expectAll(...)` applies all passed expectations, even if one expectation throws an error. If there are multiple failures, they are aggregated in an `AssertionError` with the detailed exceptions attached. This approach is similar to soft assertions or JUnit Jupiter's `assertAll()`.

### Reading the Body into an Object

When the response contains an object, use `expectBody(Class<T>)`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

client.get().uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody(Person.class)
        .value(person -> {
            assertEquals(7L, person.id());
            assertEquals("Jane", person.name());
        });
```

`BodySpec` supports methods such as `isEqualTo(...)`, `value(...)`, `consumeWith(...)`, and `returnResult()`. When the body is a generic type, such as `List<Person>`, use the overload accepting `ParameterizedTypeReference` to preserve generic type information during decoding.

### Checking Raw JSON and JSONPath

When you want to assert JSON directly without creating a DTO, use `expectBody()`:

```java
client.get().uri("/persons/7")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .json("""
                {"id": 7, "name": "Jane"}
                """);
```

You can check part of the body using JSONPath:

```java
client.get().uri("/persons")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].name").isEqualTo("Jane")
        .jsonPath("$[1].name").isEqualTo("Jason");
```

JSON assertions require an appropriate JSON comparison library on the test classpath, such as JSONassert or JsonUnit. When tests enable leak detection for pooled buffers, you need to consume the response body using `expectBody(...)` or an equivalent operation; only checking status and discarding the body may trigger reports of unreleased buffers.

### Responses Without a Body

If an endpoint returns `204 No Content` or a response with no content, assert an empty body:

```java
client.delete().uri("/persons/7")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

If you do not need to inspect the body but still need to consume the response, you can use `expectBody(Void.class)`.

## 7. Using AssertJ with RestTestClient

In addition to built-in matchers, Spring provides `RestTestClientResponse` for using AssertJ. You can convert a `ResponseSpec` or `ExchangeResult` to an assertion object:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.test.web.servlet.client.assertj.RestTestClientResponse;

RestTestClient.ResponseSpec spec = client.get()
        .uri("/persons/7")
        .exchange();

RestTestClientResponse response = RestTestClientResponse.from(spec);

assertThat(response).hasStatusOk();
assertThat(response).hasContentTypeCompatibleWith(APPLICATION_JSON);
```

AssertJ is suitable when tests already use that assertion style elsewhere or need to express response conditions with a unified assertion API. `RestTestClient`'s built-in matchers are usually sufficient for common HTTP conditions.

## 8. Distinguishing RestTestClient, MockMvc, and WebTestClient

All three tools can participate in web testing, but they have different APIs and scopes:

| Tool | How it interacts | Suitable when |
|---|---|---|
| `MockMvc` | API simulating Servlet requests/responses, allowing direct invocation and MVC inspection | Tests need detailed control over MVC components, request builders, session, flash attributes, or dispatch results. |
| `RestTestClient` | Synchronous HTTP API based on `RestClient`, able to use MockMvc or a real server | Tests want to write requests in `RestClient` style and inspect responses with fluent assertions. |
| `WebTestClient` | Reactive client API based on WebClient, supporting WebFlux and some MVC scenarios | Testing WebFlux, reactive endpoints, streaming, or when a reactive request/response model is needed. |

`RestTestClient` uses MockMvc for mock binding modes, so its mock scope focuses on Spring MVC on the Servlet stack. If you need to mock WebFlux handlers or test reactive streams directly, `WebTestClient` is a better fit. With a running server and real HTTP, `RestTestClient` can send requests to endpoints without needing MVC mocks.

`RestTestClient` also does not replace `MockRestServiceServer`. The two tools test opposite sides:

- `RestTestClient`: sends requests to the server application and inspects the responses the application returns.
- `MockRestServiceServer`: simulates an external server that a `RestClient` or `RestTemplate` in the application is calling.

## 9. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| `RestTestClient` class not found | The project is using Spring Framework 6.x or missing `spring-test`. | Use Spring Framework 7.0+ and add `spring-test` to the test classpath. |
| Accidentally importing `WebTestClient` | Using the reactive package `org.springframework.test.web.reactive.server` instead of `RestTestClient`. | Import `org.springframework.test.web.servlet.client.RestTestClient`. |
| `bindToController` fails to create dependent beans | The controller is instantiated directly, but services or dependencies were not provided. | Provide dependencies when instantiating the controller or bind to `WebApplicationContext`. |
| Test calls the wrong server or port | Using `bindToServer()` with an incorrect base URL, or assuming mock bindings require a running server. | Choose the right binding mode and verify the address/port when using a real server. |
| Response body cannot be decoded | Media type, message converter, or JSON library is unsuitable. | Check `Accept`, `Content-Type`, Jackson, and MVC message converters. |
| Body assertion does not run or lacks data | Test did not call `expectBody(...)` or did not consume the response body in a leak-detection environment. | Consume the body with `expectBody`, `expectBody(Void.class)`, or an equivalent API. |
| Using RestTestClient to test outbound RestClient | Confusing server testing with testing the application's HTTP client. | Use `MockRestServiceServer`, MockWebServer, or WireMock to simulate the target service. |

## 10. Selection and Usage Workflow

When starting a test with `RestTestClient`, you can proceed in order:

1. Verify the project uses Spring Framework 7.0+ and has `spring-test` on the test classpath.
2. Confirm the endpoint belongs to Spring MVC and choose controller, application context, router function, or running server as the binding target.
3. Create `RestTestClient` once in an appropriate fixture or setup, configuring base URL, default headers, and client options if needed.
4. Write requests using familiar methods such as `get()`, `post()`, `uri(...)`, `accept(...)`, `contentType(...)`, and `body(...)`.
5. After `exchange()`, verify status, headers, and body using built-in matchers or AssertJ.
6. For responses with a body, consume the body to decode and assert data; for empty responses, assert `isEmpty()` or use `Void.class`.
7. If the test makes requests to an external system, separate that problem and use an appropriate mock HTTP server to test the service-calling code.

## 11. Conclusion

`RestTestClient` from Spring Framework 7.0 is a synchronous testing client that uses `RestClient` to execute HTTP requests and adds a response assertion API. It can test Spring MVC via MockMvc without a server or send requests to a real server via `bindToServer()`. `RestClient` remains the choice for application code calling external APIs; `RestTestClient` is for testing application endpoints. Understanding this boundary lets you reuse the request style of `RestClient` while maintaining clear HTTP assertions in tests.

## References

- [Spring Framework Reference — RestTestClient](https://docs.spring.io/spring-framework/reference/testing/resttestclient.html)
- [Spring Framework Reference — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework Javadoc — package `org.springframework.test.web.servlet.client`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/client/package-summary.html)
