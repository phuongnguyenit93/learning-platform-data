# bindToController for WebFlux Controllers

`WebTestClient` can test a WebFlux controller directly without starting a server. With `WebTestClient.bindToController(...)`, the test passes in the controller instances to test; Spring builds a mock WebFlux infrastructure so requests go through annotated controller handling, argument resolvers, and HTTP message readers/writers.

This approach is suitable when you want to verify mappings, data binding, reactive return type handling, and responses for a group of controllers with minimal configuration. The test does not need to load the entire application or open an HTTP port. Because the controller is passed directly, the test also explicitly controls the instance and the dependencies supplied to it.

## 1. How Does bindToController Work?

`WebTestClient` is an HTTP client used for testing. It can send requests to a running server or send requests into a mock server built in memory.

In a Spring Boot project, `spring-boot-starter-webflux` provides WebFlux and Reactor for the application; `spring-boot-starter-test` provides the testing libraries. `WebTestClient` is located in `spring-test`. If you verify publishers with `StepVerifier`, `reactor-test` is required on the test classpath. For JSON requests/responses, the application also needs an appropriate JSON codec, typically Jackson in Spring Boot WebFlux configurations.

With `bindToController(...)`, Spring creates a mock WebFlux environment around the provided controller. High-level processing flow:

```text
WebTestClient
    |
    | Simulated HTTP request
    v
WebFlux mock infrastructure
    |
    v
HandlerMapping / HandlerAdapter
    |
    v
WebFlux Controller
    |
    v
Mono / Flux / ResponseEntity
    |
    v
Simulated HTTP response
    |
    v
WebTestClient assertions
```

Basic steps:

1. Create the controller instance.
2. Call `WebTestClient.bindToController(controller).build()`.
3. Use the client to build a request with method, URI, headers, and body.
4. Call `exchange()` to execute the request through WebFlux.
5. Verify the status, headers, and body using the assertion APIs.

Minimal example:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .build();
```

`bindToController` accepts one or more controller instances. When you have multiple controllers, you can pass them at the same time:

```java
WebTestClient client = WebTestClient
    .bindToController(
        new GreetingController(),
        new OrderController()
    )
    .build();
```

## 2. Writing a WebFlux Controller Returning Mono

WebFlux controllers typically return reactive types such as `Mono<T>` or `Flux<T>`. The following example controller accepts a query parameter and responds with `Mono<String>`:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<String> greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return Mono.just("Hello " + name);
    }
}
```

The test uses `bindToController` to build the client and send a request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingControllerTests {

    private final WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();

    @Test
    void returnsGreeting() {
        client.get()
            .uri(uriBuilder -> uriBuilder
                .path("/greeting")
                .queryParam("name", "Mai")
                .build())
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Hello Mai");
    }
}
```

In the test:

- `client.get()` creates a GET request.
- `uri(...)` sets the path and query parameter.
- `accept(...)` declares the response media type accepted by the client.
- `exchange()` sends the request through the WebFlux mock infrastructure.
- `expectStatus()` checks the HTTP status.
- `expectHeader()` checks the response headers.
- `expectBody(String.class)` reads the body as a string for comparison.

`exchange()` is the request execution boundary. Subsequent assertions verify the response produced by controller processing.

## 3. Testing JSON Requests and Responses

For endpoints accepting JSON, the test must set `Content-Type` and provide a properly formatted body. WebFlux uses an HTTP message reader to convert JSON into a Java object, and a message writer converts the returned result into a JSON response.

Example controller:

```java
import reactor.core.publisher.Mono;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    Mono<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        return Mono.just(
            new OrderResponse("ORD-284", request.customerId())
        );
    }
}

record CreateOrderRequest(String customerId) {
}

record OrderResponse(String id, String customerId) {
}
```

Test sending JSON and verifying the response with JSONPath:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrderControllerTests {

    private final WebTestClient client = WebTestClient
        .bindToController(new OrderController())
        .build();

    @Test
    void createsOrderFromJson() {
        client.post()
            .uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("C-208"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("ORD-284")
            .jsonPath("$.customerId").isEqualTo("C-208");
    }
}
```

`bodyValue(...)` sends an object for the message writer to encode according to `Content-Type`; `expectBody()` allows inspecting the JSON response with JSONPath. This ensures the test goes through the same message codecs that the application uses to read requests and write responses.

## 4. Testing Multiple Elements from Flux

Controllers can return `Flux<T>` when the response contains a stream of multiple elements. For finite responses, `expectBodyList(...)` can collect the body into a list for assertion:

```java
import reactor.core.publisher.Flux;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/products")
    Flux<String> products() {
        return Flux.just("book", "pen", "notebook");
    }
}
```

```java
client.get()
    .uri("/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(String.class)
    .contains("book", "pen", "notebook");
```

`expectBodyList` is suitable for finite responses that can be buffered in the test. For continuous streams or streaming responses, do not wait for the entire body to complete. Use `returnResult(...)` to obtain the publisher and assert elements using Reactor Test `StepVerifier`:

```java
import reactor.test.StepVerifier;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;

FluxExchangeResult<String> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("created", "updated")
    .thenCancel()
    .verify();
```

With streaming responses, you need to explicitly specify the expected number of elements or termination condition. `thenCancel()` indicates that the test actively cancels the subscription after receiving the elements to verify.

## 5. Adding ControllerAdvice to Controller Tests

`bindToController` allows registering custom `@ControllerAdvice` via `controllerAdvice(...)`. This is useful when you want to verify how a controller translates exceptions into HTTP responses without loading the entire application context.

Example controller throwing an error:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/accounts/unknown")
    Mono<String> missingAccount() {
        return Mono.error(new IllegalArgumentException("Account not found"));
    }
}
```

Advice normalizing the exception into a response:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    Map<String, String> handleMissingAccount(IllegalArgumentException ex) {
        return Map.of("code", "ACCOUNT_NOT_FOUND");
    }
}
```

Pass both the controller and advice into the test configuration:

```java
WebTestClient client = WebTestClient
    .bindToController(new AccountController())
    .controllerAdvice(new ApiExceptionHandler())
    .build();

client.get()
    .uri("/accounts/unknown")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("ACCOUNT_NOT_FOUND");
```

The test verifies the final response received by the client: status 404 and the error code in JSON. Without registering the advice, the test may observe exception behavior that differs from the real application using a global exception handler.

## 6. Customizing the Client and WebFlux Mock Infrastructure

You can configure the mock server side before calling `build()`, then configure the HTTP client via `configureClient()`.

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .configureClient()
    .baseUrl("http://localhost")
    .defaultHeader("X-Test-Client", "webflux-test")
    .defaultHeader("Accept", MediaType.TEXT_PLAIN_VALUE)
    .build();
```

`configureClient()` opens the client configuration section, such as base URL, default headers, filters, and timeouts. Client-side settings do not change how the controller is instantiated.

If you need to customize the mock server infrastructure, `ControllerSpec` also allows configuring controller advice and HTTP message codecs. For example, you can register a custom codec to test how the application reads or writes a specific data format. Only add configuration when the test needs to verify that exact behavior; excessive configuration makes it harder to tell which component caused a result.

## 7. Controllers with Dependencies

`bindToController(...)` accepts controller instances. It does not perform full-application component scanning and does not automatically locate service beans as when starting an application context.

If a controller has constructor dependencies, the test must supply those dependencies when creating the instance. For example, you can use a mock of the service:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    private final CustomerService customerService;

    CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/customers/{id}")
    Mono<Customer> find(@PathVariable String id) {
        return customerService.findById(id);
    }
}
```

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

CustomerService customerService = mock(CustomerService.class);
given(customerService.findById("C-208"))
    .willReturn(Mono.just(new Customer("C-208", "Mai")));

WebTestClient client = WebTestClient
    .bindToController(new CustomerController(customerService))
    .build();
```

In this example, the test explicitly creates a service mock and passes it into the constructor. You can use Mockito or a fake implementation depending on your needs. If you want Spring to inject dependencies automatically, use an application-context-based test instead of expecting `bindToController` to scan and instantiate all beans.

## 8. How bindToController Differs from Other Binding Modes

`WebTestClient` offers several ways to create a client depending on test scope:

| Binding Mode | Input | Test Scope |
|---|---|---|
| `bindToController(...)` | One or more controller instances | Tests controllers with WebFlux mock infrastructure and minimal configuration |
| `bindToApplicationContext(...)` | Loaded WebFlux application context | Tests beans and WebFlux configuration of the application |
| `bindToRouterFunction(...)` | `RouterFunction` | Tests WebFlux functional endpoints |
| `bindToServer()` | Connection to a running server | Tests over real HTTP, including the started server |

Choose `bindToController` when the goal focuses on a controller or a group of controllers and the test can supply dependencies directly. Choose `bindToApplicationContext` when you need to verify bean configurations, filters, codecs, or WebFlux components registered in the context. Use `bindToServer` when you need to verify a real server and network communication.

## 9. Limitations and Common Pitfalls

`bindToController` keeps tests fast and isolated, but its scope has limitations:

- Does not start a real server, does not open a network port, and does not test TLS or reverse proxies.
- Does not automatically load the full application context, component scan, or deployment configuration.
- Does not automatically find and inject service beans; controller instances must have their dependencies when created.
- Only the controllers and advice passed in participate in the test configuration.
- The default WebFlux configuration of the mock setup may differ from custom codecs, filters, or customizers that the real application registers in its context.

| Symptom | Cause to Check |
|---|---|
| Controller not found | Controller was not passed to `bindToController(...)` or URI/method does not match the mapping |
| Dependency in controller is `null` | Test instantiated the controller without passing dependencies via the constructor |
| Exception returns unexpected status or body | `controllerAdvice(...)` was not registered or the exception handler does not handle that exception type |
| JSON is not read or written | Check `Content-Type`, `Accept`, codecs, and corresponding JSON dependencies |
| Test does not verify application-wide filters/configuration | Switch to binding to an application context if that configuration is part of the contract under test |
| Response stream causes test to hang | Response is a non-terminating stream; use `returnResult(...)` and `StepVerifier` with appropriate receive/cancel conditions |

## 10. Workflow for Writing Tests with bindToController

1. Choose the WebFlux controller and identify the dependencies it needs.
2. Create the controller instance along with appropriate real, fake, or mock dependencies.
3. Build `WebTestClient` with `bindToController(...)`; register `controllerAdvice(...)` if needed.
4. Send a request with the method, URI, headers, content type, and body matching the endpoint.
5. Call `exchange()` to run the request through the WebFlux mock infrastructure.
6. Verify status, headers, and body; for finite `Flux` use `expectBodyList`, for streaming use `returnResult` and `StepVerifier`.
7. If the test needs application-wide configuration or beans, expand the scope to `bindToApplicationContext(...)`.

`bindToController` fits WebFlux controller tests with a clear scope: the test explicitly provides the controller and its dependencies, while WebTestClient simulates request/response flow through the WebFlux infrastructure. Distinguishing this scope properly keeps tests fast and readable and prevents assuming that an isolated controller test verifies the configuration of the entire application.
