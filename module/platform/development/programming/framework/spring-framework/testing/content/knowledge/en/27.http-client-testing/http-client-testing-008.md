# MockMvcClientHttpRequestFactory for In-Process Client-to-MVC Flows

## 1. The Problem of Testing an HTTP Client Calling Spring MVC

An application may contain client code using `RestClient` or `RestTemplate` to send HTTP requests to a Spring MVC endpoint. When testing that client code, we often want to verify both sides: the client produces the right method, URI, headers, and body; the controller receives the request, processes it, and returns a response matching the contract.

If using a real server, the test must start the application and send requests over HTTP. If using only a mock HTTP server, the test can check how the client sends requests, but responses are usually declared by the test itself and do not run through the real controller.

`MockMvcClientHttpRequestFactory` offers an option in between these two approaches. It is a `ClientHttpRequestFactory` that uses `MockMvc` to execute requests in the same process. `RestClient` or `RestTemplate` still creates requests via the standard HTTP client API; requests are handed to the MockMvc infrastructure, flow through Spring MVC, and receive responses from the controller.

As a result, tests can run real client code and real controllers in the same JVM without opening ports or starting a Servlet container.

`MockMvcClientHttpRequestFactory` belongs to the `spring-test` artifact, in the `org.springframework.test.web.client` package. With Gradle, the dependency is typically declared in the test scope:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
}
```

If using `RestClient`, the project needs Spring Framework 6.1 or later because `RestClient` was introduced in that version. Keep `spring-test`, `spring-web`, and `spring-webmvc` on the same version line to avoid API conflicts. With Spring Boot, `spring-boot-starter-test` usually already provides `spring-test`; the MVC application also needs the corresponding web dependency.

## 2. How Requests Are Routed Through MockMvc

`RestClient` does not inherently know how to invoke a controller. It sends requests through a `ClientHttpRequestFactory`. The factory decides how requests are created and executed. When the factory is `MockMvcClientHttpRequestFactory`, requests are converted into mock Servlet requests for `MockMvc` to dispatch through Spring MVC.

The processing flow can be visualized as follows:

```text
Test
 |
 | invokes application client method
 v
RestClient / RestTemplate
 |
 | creates ClientHttpRequest
 v
MockMvcClientHttpRequestFactory
 |
 | forwards request into MockMvc
 v
DispatcherServlet and Spring MVC
 |
 | HandlerMapping -> Controller -> MessageConverter
 | ExceptionResolver / ControllerAdvice on errors
 v
MockHttpServletResponse
 |
 | converts status, headers, and body back to ClientHttpResponse
 v
RestClient / RestTemplate reads response
 |
 v
Test asserts client result
```

The factory acts as a bridge between the synchronous client API and the MockMvc environment. Client code still uses URIs, HTTP methods, headers, and bodies just as when calling a regular HTTP address. On the server side, Spring MVC processes requests through `DispatcherServlet`, mappings, controllers, argument resolvers, message converters, and exception resolvers configured in MockMvc.

This is in-process execution. The host and port in the URI help the client build the request address, but there is no TCP connection to that host. MockMvc receives the request directly inside the JVM.

## 3. Creating MockMvc and Attaching It to RestClient

The simplest example uses `MockMvcBuilders.standaloneSetup(...)` to create an MVC environment for one controller:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new ProductController())
        .build();

RestClient restClient = RestClient.builder()
        .baseUrl("http://localhost")
        .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
        .build();
```

There are two key points in this setup:

- `MockMvcBuilders.standaloneSetup(...)` creates MockMvc with the specified controller and basic MVC infrastructure. This suits small tests focused on a specific controller.
- `requestFactory(...)` replaces `RestClient`'s default factory with a factory connected to MockMvc. From here on, client requests are processed in-process.

`baseUrl("http://localhost")` serves as the base address for `RestClient` to resolve relative URIs. With this factory, `localhost` does not need a listening server. You can use a consistent fake host in tests; what matters are the path, query, and request parts the controller needs to receive.

If the controller depends on services, repositories, or other Spring beans, you can instantiate the controller with mock dependencies in the test, or use a `MockMvc` built from `WebApplicationContext` to use the application's configuration.

## 4. Complete Example: RestClient Calling a Controller in the Same JVM

Suppose an application has an endpoint returning product information:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

record Product(long id, String name) {
}

@RestController
class ProductController {

    @GetMapping("/api/products/{id}")
    Product findById(@PathVariable long id) {
        return new Product(id, "Mechanical Keyboard");
    }
}
```

The client code is the component the test wants to verify. It uses `RestClient` to call the endpoint and convert the JSON response into `Product`:

```java
import org.springframework.web.client.RestClient;

class ProductApiClient {

    private final RestClient restClient;

    ProductApiClient(RestClient restClient) {
        this.restClient = restClient;
    }

    Product findById(long id) {
        return restClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
```

The test wires the client to the controller via MockMvc:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

class ProductApiClientTests {

    @Test
    void readsProductThroughMvcInTheSameProcess() {
        MockMvc mockMvc = MockMvcBuilders
                .standaloneSetup(new ProductController())
                .build();

        RestClient restClient = RestClient.builder()
                .baseUrl("http://localhost")
                .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
                .build();

        ProductApiClient client = new ProductApiClient(restClient);

        Product product = client.findById(42);

        assertThat(product).isEqualTo(new Product(42, "Mechanical Keyboard"));
    }
}
```

The test executes a full application-level chain:

1. Calls `ProductApiClient.findById(42)` just like business code.
2. `RestClient` builds a GET request to `/api/products/42`.
3. The factory forwards the request to MockMvc.
4. Spring MVC invokes `ProductController.findById(...)` and writes the object to JSON via message converters.
5. The factory returns the response to `RestClient`, and `RestClient` deserializes the JSON into `Product`.
6. The test asserts the received object.

The example uses a record to keep code concise. Jackson must be on the test runtime classpath to serialize and deserialize JSON. If the application uses custom message converters or custom Jackson configuration, build MockMvc from the application context so the test uses that exact configuration.

## 5. Using WebApplicationContext for Full MVC Configuration

`standaloneSetup(...)` fits when testing a controller in isolation. In real applications, controllers typically run alongside interceptors, controller advice, validators, converters, and other MVC configurations. When you need to test the client with the full loaded MVC configuration, build MockMvc from `WebApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.client.RestClient;

@SpringJUnitConfig(WebConfig.class)
@WebAppConfiguration
class ProductApiClientContextTests {

    @Autowired
    private WebApplicationContext context;

    private ProductApiClient client;

    @BeforeEach
    void setUp() {
        MockMvc mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .build();

        RestClient restClient = RestClient.builder()
                .baseUrl("http://localhost")
                .requestFactory(new MockMvcClientHttpRequestFactory(mockMvc))
                .build();

        client = new ProductApiClient(restClient);
    }

    @Test
    void usesMvcConfigurationFromTheApplicationContext() {
        Product product = client.findById(42);

        assertThat(product).isEqualTo(new Product(42, "Mechanical Keyboard"));
    }
}
```

`WebConfig` represents the application's Spring MVC configuration and must register the controller and required beans. `webAppContextSetup(context)` builds MockMvc backed by the `WebApplicationContext`, so requests pass through the loaded MVC configuration rather than relying only on standalone setup defaults.

If the application has Servlet filters that need to participate in the test, ensure those filters are registered in the MockMvc setup as appropriate, such as via `addFilters(...)` when building MockMvc. Do not assume every real Servlet container configuration automatically appears in MockMvc.

## 6. Checking Method, Headers, and Request Body

Because the client still builds requests through `ClientHttpRequestFactory`, tests can verify the HTTP behaviors executed by client code. For instance, a client sending a JSON POST with headers:

```java
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

record CreateProductRequest(String name) {
}

class ProductApiClient {

    private final RestClient restClient;

    ProductApiClient(RestClient restClient) {
        this.restClient = restClient;
    }

    Product create(String name) {
        return restClient.post()
                .uri("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Client-Name", "catalog-client")
                .body(new CreateProductRequest(name))
                .retrieve()
                .body(Product.class);
    }
}
```

Extend `ProductController` from the example above with a method accepting the body and header like a normal MVC endpoint. Corresponding imports are declared at the top of the controller file:

```java
// Add this method to ProductController.
@PostMapping("/api/products")
ResponseEntity<Product> create(
        @RequestBody CreateProductRequest request,
        @RequestHeader("X-Client-Name") String clientName) {

    Product created = new Product(100, request.name() + " / " + clientName);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
```

In the test, create MockMvc and `RestClient` as in the earlier example, then call `client.create("Desk Lamp")` and assert that the returned product has the expected contents. If the request lacks `Content-Type`, sends malformed JSON, or omits a required header, Spring MVC can return the corresponding error; that error also flows back to `RestClient` as an HTTP response.

This example simultaneously tests how the client encodes the body/headers and how MVC receives them. When you only want to verify the outbound request without running a real controller, a mock HTTP server is more appropriate.

## 7. Using with RestTemplate

`MockMvcClientHttpRequestFactory` implements `ClientHttpRequestFactory`, so it can also be used with `RestTemplate`:

```java
import org.springframework.test.web.client.MockMvcClientHttpRequestFactory;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestTemplate;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new ProductController())
        .build();

RestTemplate restTemplate = new RestTemplate(
        new MockMvcClientHttpRequestFactory(mockMvc));

Product product = restTemplate.getForObject(
        "http://localhost/api/products/{id}", Product.class, 42);
```

This is helpful when a project still has client code using `RestTemplate`. Existing clients can be tested via MockMvc without rewriting business code just to switch to `RestClient`.

With `RestClient`, the factory is set on the builder via `requestFactory(...)`. With `RestTemplate`, the factory is passed to the constructor or configured on the instance. Both use the same bridge mechanism to MockMvc.

## 8. Comparison with MockRestServiceServer and Real Servers

These tools solve different problems:

| Option | What gets executed? | Appropriate when |
|---|---|---|
| `MockMvcClientHttpRequestFactory` | Application's real client sends requests to real Spring MVC inside MockMvc | You want to test the client-to-controller flow and check interaction between both sides in the same process. |
| `MockRestServiceServer` | Real client sends requests; mock server returns responses declared via expectations | You want to verify URL, method, headers, body, and how the client handles responses from a dependent service. |
| MockWebServer or WireMock | Real client communicates with a fake HTTP server over the network | You want to test HTTP transport and simulate an external service over sockets. |
| Embedded server or running environment | Client sends requests over HTTP to the real application | You want to test the Servlet container, network ports, and runtime configuration too. |

Example of the differences:

- With `MockRestServiceServer`, a test declares: when the client calls GET `/products/42`, return fixed JSON. No controller runs.
- With `MockMvcClientHttpRequestFactory`, GET `/products/42` is dispatched to the real mapping and controller inside MockMvc. The response depends on running MVC logic.
- With an embedded server, requests travel over sockets to the application listening on a port, which can catch container- or network-related issues that MockMvc does not simulate.

If the goal is testing an adapter calling an external service, `MockRestServiceServer` or a mock HTTP server is usually the right choice. If the goal is testing an in-app HTTP client calling an internal Spring MVC endpoint, `MockMvcClientHttpRequestFactory` connects both sides without standing up network infrastructure.

## 9. Scope and Limitations of In-Process Testing

This factory tests behavior at the boundary between `ClientHttpRequestFactory` and Spring MVC. It can verify request construction, MVC request handling, and client response reading. However, the test does not go through a real HTTP server or Servlet container.

Consequently, this test does not verify:

- Real port binding, DNS, or TCP connections.
- TLS handshakes, certificates, proxies, socket timeouts, and HTTP client connection pool settings in a network environment.
- How a real Servlet container handles connectors, thread pools, request limits, multipart handling, or deployment-specific behaviors.
- Streaming behavior or wire-level data transmission as when a client talks to a real server.

MockMvc still runs the configured Spring MVC infrastructure, yet it does not replace integration tests against a real server. Use this factory for fast tests focused on client-to-MVC flows; supplement with real-server tests when the contract must verify transport or container behavior.

`MockMvcClientHttpRequestFactory` targets Spring MVC on the Servlet stack. It is not a factory for dispatching to WebFlux handlers. If the application uses WebFlux, `WebTestClient` provides binding and testing suited to the reactive web stack.

## 10. Common Mistakes

| Symptom | Common cause | Solution |
|---|---|---|
| `MockMvcClientHttpRequestFactory` not found | Missing `spring-test` or Spring version lacks this class. | Add `spring-test` to the test classpath and align versions with Spring Framework in use. |
| Requests still go out to the network | `RestClient` was not configured with the MockMvc factory or client code creates another client. | Pass `MockMvcClientHttpRequestFactory` into `requestFactory(...)` of the builder used by the client. |
| Receiving `404 Not Found` | URI path does not match mapping or controller was not registered in MockMvc. | Check base URL, path, HTTP method, and controllers passed to setup. |
| Receiving `415 Unsupported Media Type` | Client sends a body with a Content-Type unsupported by the endpoint. | Set the right content type and check MockMvc's message converters. |
| Receiving `406 Not Acceptable` | Accept header is incompatible with response types MVC can produce. | Check Accept, `produces`, and registered converters. |
| JSON is not converted | Jackson or needed converter is missing from test classpath/MVC config. | Add the right dependency and use `webAppContextSetup` when application converter configuration is needed. |
| Filters or controller advice do not run | MockMvc was built with standalone setup or components were not registered. | Build MockMvc from `WebApplicationContext` and register filters/configuration under test. |
| Test passes but real deployment fails to connect | Test runs in-process only and creates no sockets or container. | Add tests with an embedded server or a real integration environment. |

## 11. Workflow to Apply

When using `MockMvcClientHttpRequestFactory`, you can follow this sequence:

1. Identify whether client code uses `RestClient` or `RestTemplate` and keep that client code's API intact.
2. Create `MockMvc` via `standaloneSetup(...)` for a simple controller or `webAppContextSetup(...)` for full MVC configuration.
3. Create `MockMvcClientHttpRequestFactory` from the built `MockMvc`.
4. Attach the factory to `RestClient.Builder.requestFactory(...)` or `RestTemplate`'s constructor.
5. Supply a base URL so the client resolves complete URIs; the host does not need a listening server.
6. Invoke client methods as in application code and assert results, exceptions, or required side effects.
7. Use a mock HTTP server for external services and an embedded server when real transport/container behavior must be tested.

## 12. Conclusion

`MockMvcClientHttpRequestFactory` connects a `ClientHttpRequestFactory`-based HTTP client to `MockMvc`. This lets `RestClient` or `RestTemplate` send requests using their normal API while dispatching those requests to Spring MVC in the same process. This approach fits testing collaboration between client code and controllers without opening ports or running a Servlet container. When networking, TLS, or container behavior must be verified, an integration test against a real server is still required.
