# Role of WebTestClient and Its Relationship with WebClient

`WebTestClient` is a tool for sending requests and asserting responses in Spring testing. It allows testing endpoints in an HTTP style without necessarily opening a network port or starting a real server. Depending on how it is configured, requests can run through the in-memory WebFlux infrastructure, through a Spring MVC adapter, or against an actual running server.

`WebClient` is also a Spring HTTP client and has a similar fluent request API. However, the two classes serve different purposes: applications typically use `WebClient` to call external services; tests use `WebTestClient` to send requests to the endpoint under test and write assertions directly on the response.

## 1. What Is WebTestClient?

`WebTestClient` resides in the `org.springframework.test.web.reactive.server` package of the `spring-test` module. This API was introduced in Spring Framework 5.0 and was designed for testing WebFlux applications. Since Spring Framework 5.3, the `MockMvcWebTestClient` adapter also allows using the same testing style with Spring MVC.

WebTestClient provides three main parts:

- Request builder: chooses the HTTP method, URI, headers, cookies, query parameters, and body.
- Exchange: executes the request through the test configuration or sends it to a real server.
- Response assertions: verifies the status, headers, cookies, body, and properties of the response.

Minimal example:

```java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();

client.get()
        .uri("/greeting")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello, World");
```

The GET request is built with `.get()` and `.uri(...)`. `.exchange()` sends the request through the test server. Afterward, the test can verify the status and body using the `expect...` APIs.

## 2. What Is WebClient?

`WebClient` resides in the `org.springframework.web.reactive.function.client` package of Spring WebFlux. It is an asynchronous HTTP client that supports reactive types such as `Mono` and `Flux`. Applications use it to call other HTTP APIs, for example an order service calling a payment service.

Example of an application component using WebClient:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;

class PaymentClient {

    private final WebClient webClient;

    PaymentClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://payments.example.test")
                .build();
    }

    Mono<PaymentResponse> findPayment(String paymentId) {
        return webClient.get()
                .uri("/payments/{id}", paymentId)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
```

`retrieve()` starts processing the response along the WebClient flow; `bodyToMono(...)` converts the body into a reactive publisher. This code is logic running in the application, not an assertion of an endpoint test.

## 3. Relationship Between WebTestClient and WebClient

WebTestClient is built on top of WebClient and uses a similar request builder style. Writing requests is therefore quite familiar if you have already used WebClient: `.get()`, `.post()`, `.uri(...)`, `.header(...)`, `.cookie(...)`, `.bodyValue(...)`, and similar operations.

The differences lie in how requests are executed and how responses are handled:

| Aspect | WebClient | WebTestClient |
|---|---|---|
| Purpose | Call HTTP APIs from application code | Test HTTP endpoints |
| Request API | Fluent request builder | Similar fluent request builder |
| Execution | Sends requests over an HTTP connector to a server | Can run in memory or send to a real server |
| After sending | Reads the body into `Mono`/`Flux`, handles status and errors in application code | Uses `expectStatus()`, `expectHeader()`, `expectBody()` for assertions |
| Typical usage | Services, gateways, integration adapters | JUnit tests for WebFlux or MVC endpoints |

Example comparing response flows:

```java
// In application code: WebClient
Mono<PaymentResponse> payment = webClient.get()
        .uri("/payments/{id}", paymentId)
        .retrieve()
        .bodyToMono(PaymentResponse.class);

// In tests: WebTestClient
client.get()
        .uri("/payments/{id}", paymentId)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("PAID");
```

WebTestClient is not a subclass of WebClient and should not replace WebClient in business logic. You can think of WebTestClient as a test client that has a request API similar to WebClient while also adding assertions designed for testing.

## 4. WebTestClient Binding Modes

The key point when setting up WebTestClient is choosing the right target for requests. The factory methods determine whether the test runs against a controller, an application context, a router function, or a running server.

### 4.1. bindToController(...)

Use this when you want to test one or a few annotated controllers with minimal WebFlux configuration:

```java
WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();
```

This is a standalone test style. There is no need to start the entire application context. If the controller has dependencies, create an instance with the required dependencies and pass it in. If the test depends on controller advice, filters, codecs, or custom WebFlux configuration, you must add them through the builder configuration or use a context-based setup.

### 4.2. bindToApplicationContext(...)

When you need to use the WebFlux configuration and beans registered in the application context, bind the tester to the context:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .build();
```

Here `applicationContext` is the initialized reactive application context, typically containing WebFlux configuration and controller or handler beans. This approach is suitable when the test needs to verify the application's real web configuration, such as codecs, controller advice, filters, or components registered in the context.

### 4.3. bindToRouterFunction(...)

For WebFlux functional endpoints, you can bind directly to a `RouterFunction`:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route(
        GET("/hello"),
        request -> ServerResponse.ok().bodyValue("Hello"));

WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.get()
        .uri("/hello")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("Hello");
```

This approach is suitable for applications that use WebFlux functional routing instead of `@RestController`.

### 4.4. bindToServer()

When the server is already running and the test wants to send real HTTP requests, use `bindToServer()`:

```java
WebTestClient client = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/health")
        .exchange()
        .expectStatus().isOk();
```

This mode performs network I/O to the server. It is suitable for integration tests or tests running alongside a server started by the test framework. When using Spring Boot, you can let Boot start the server on a random port and inject a preconfigured WebTestClient:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiIntegrationTests {

    @Autowired
    private WebTestClient client;

    @Test
    void healthEndpointIsAvailable() {
        client.get()
                .uri("/api/health")
                .exchange()
                .expectStatus().isOk();
    }
}
```

In this example, requests go to a real server running on a random port. The test covers more components than binding directly to a controller, but startup cost and execution time are usually higher.

## 5. Using WebTestClient with Spring MVC

WebTestClient originally targeted WebFlux. For Spring MVC applications, you can use `MockMvcWebTestClient` to provide a similar testing API while executing through MockMvc:

```java
import org.springframework.test.web.servlet.client.MockMvcWebTestClient;

WebTestClient client = MockMvcWebTestClient
        .bindToController(new GreetingMvcController())
        .build();
```

`MockMvcWebTestClient` is an adapter in the `org.springframework.test.web.servlet.client` package. It lets you use WebTestClient's request/response assertions on top of MockMvc. This is a useful option when you want a WebTestClient-style testing API while the application uses the Spring MVC Servlet stack.

You can bind to a Spring MVC `WebApplicationContext`:

```java
WebTestClient client = MockMvcWebTestClient
        .bindToApplicationContext(webApplicationContext)
        .build();
```

Do not confuse `MockMvcWebTestClient` with `WebTestClient.bindToApplicationContext(...)`: the former uses the MockMvc adapter for Spring MVC; the latter builds a reactive WebFlux pipeline from the application context.

## 6. Writing Assertions with WebTestClient

### Asserting status and headers

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectHeader().exists("X-Request-Id");
```

You can assert specific statuses such as `isCreated()`, `isNotFound()`, `isBadRequest()`, or use `isEqualTo(...)` with the expected status.

### Asserting a JSON body

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("42")
        .jsonPath("$.status").isEqualTo("PAID");
```

### Deserializing the body into an object

```java
client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody(OrderResponse.class)
        .value(order -> {
            assertThat(order.getId()).isEqualTo("42");
            assertThat(order.getStatus()).isEqualTo("PAID");
        });
```

### Asserting an empty body

```java
client.delete()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isNoContent()
        .expectBody().isEmpty();
```

These assertions run after `.exchange()`. Do not use `retrieve()` like WebClient in the test flow, because WebTestClient needs `ResponseSpec` to call `expectStatus()`, `expectHeader()`, and `expectBody()`.

## 7. Complete WebFlux Controller Testing Example

Simple reactive controller:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<GreetingResponse> greeting(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just(new GreetingResponse("Hello, " + name));
    }
}

record GreetingResponse(String message) {}
```

Test using bindToController:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class GreetingWebFluxTests {

    private final WebTestClient client = bindToController(
            new GreetingController()).build();

    @Test
    void returnsGreetingAsJson() {
        client.get()
                .uri(uriBuilder -> uriBuilder.path("/greeting")
                        .queryParam("name", "Ada")
                        .build())
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Ada");
    }
}
```

This test runs the controller through the WebFlux test infrastructure without starting an HTTP server. It still verifies request mapping, argument binding, message conversion, and the response produced in the pipeline configured for the test.

## 8. WebTestClient Is Not a Replacement for Testing WebClient

Because the request builder APIs look alike, it is sometimes easy to assume that WebTestClient can directly test application code that uses WebClient. In practice, the two testing goals are different:

- **Testing a server endpoint:** send requests to a controller or server using WebTestClient and verify the response returned by the server.
- **Testing the application's HTTP client:** verify that a service using WebClient sends the right request to an external service, handles statuses, and deserializes responses as expected.

When testing code that uses WebClient, you typically configure the base URL to point to a mock HTTP server such as MockWebServer or WireMock, or supply a fake `ExchangeFunction` to inspect the request and return a simulated response. Example using `ExchangeFunction`:

```java
ExchangeFunction exchangeFunction = request -> {
    assertThat(request.url().getPath()).isEqualTo("/payments/p-42");
    ClientResponse response = ClientResponse.create(HttpStatus.OK)
            .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .body("{\"id\":\"p-42\",\"status\":\"PAID\"}")
            .build();
    return Mono.just(response);
};

WebClient webClient = WebClient.builder()
        .exchangeFunction(exchangeFunction)
        .build();
```

The snippet above illustrates how to isolate the application's HTTP client. Real tests can use a mock server to verify both the outgoing request and the incoming response over the HTTP protocol. Do not use `WebTestClient.bindToController(...)` as a substitute for testing a `WebClient` that calls an external system.

## 9. Choosing the Right Mode

| Goal | Initialization | Real server? |
|---|---|---|
| Test a WebFlux annotated controller | `WebTestClient.bindToController(...)` | No |
| Test WebFlux configuration in a context | `WebTestClient.bindToApplicationContext(...)` | No |
| Test a WebFlux functional route | `WebTestClient.bindToRouterFunction(...)` | No |
| Test a running server | `WebTestClient.bindToServer()` | Yes |
| Test Spring MVC with the WebTestClient API | `MockMvcWebTestClient.bindToController(...)` or `bindToApplicationContext(...)` | No, runs via MockMvc |

Choose the test mode according to the scope you need to verify. Standalone binding is fast and focused; application context binding covers Spring configuration; server binding additionally tests the HTTP connector, server, and actual deployment configuration.

## 10. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| `WebTestClient` cannot be found | Missing `spring-test` or Spring Framework version is too old | Add the appropriate test dependency and use a Spring Framework version that includes this API |
| WebFlux types cannot be resolved | Missing `spring-webflux` or required reactive dependencies | Add WebFlux dependencies compatible with Spring Framework |
| Controller has missing dependencies | Using `bindToController(...)` without creating dependencies for the controller | Pass a fully initialized controller instance or use an application context |
| Custom filters or codecs do not run | Using standalone binding without registering the required configuration | Use builder customization or bind to an application context |
| Request to server fails with connection refused | Using `bindToServer()` when the server is not running or base URL is wrong | Start the server first and configure the correct host and port |
| Using WebTestClient to test outbound WebClient | Confusing the test client with the application's HTTP client | Use a mock HTTP server or ExchangeFunction to test WebClient |
| MVC controller is not handled as expected | Using WebFlux binding for a Servlet MVC application | Use `MockMvcWebTestClient` to adapt through MockMvc |

## 11. Takeaways

`WebClient` is an HTTP client for application code; `WebTestClient` is an endpoint testing tool with a similar request API plus response assertions. WebTestClient can run against WebFlux controllers, router functions, application contexts, or a real server. For Spring MVC, use `MockMvcWebTestClient` to execute through MockMvc. When testing outbound code that uses WebClient, simulate the HTTP service that WebClient calls using a mock server or ExchangeFunction. Choosing the right client according to the direction of the request under test ensures tests accurately reflect the boundary between server endpoints and HTTP integration.

