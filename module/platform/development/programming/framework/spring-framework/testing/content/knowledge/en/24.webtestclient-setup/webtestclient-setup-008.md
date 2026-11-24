# Base URL, Default Headers, and Codec Configuration

## 1. Role of WebTestClient Configuration

`WebTestClient` is Spring's HTTP testing API, offering a fluent interface similar to `WebClient`. It can send requests to a running server or route requests through the mock infrastructure of Spring MVC/WebFlux. Before calling `build()`, you can configure shared defaults for all requests:

- **Base URL**: the root address used to resolve relative URIs.
- **Default headers**: default headers such as `Accept`, client identifiers, or test-environment authentication credentials.
- **Codecs**: readers and writers for HTTP bodies, such as JSON encoders/decoders, buffer size limits, and custom codecs.

Putting repeated values into the builder makes tests shorter and more consistent. Individual tests can still override headers or send a distinct URI when special requirements arise.

## 2. Configuring the Base URL

The base URL is used when a request provides a relative URI. For example, with a base URL of `https://api.example.test`, calling `.uri("/v1/orders")` sends the request to `https://api.example.test/v1/orders`.

When testing against a running server, you can configure the address directly on the `bindToServer()` builder:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk();
```

`bindToServer()` uses real HTTP connections, so the host and port must point to a server reachable at the time the test runs. In integration tests with a random port, obtain the port assigned by Spring Boot instead of hardcoding `8080`.

When binding directly to a controller or application context, first configure the mock server side, then call `configureClient()` to obtain the client-side builder:

```java
WebTestClient client = WebTestClient.bindToController(new CatalogController())
        .configureClient()
        .baseUrl("http://localhost")
        .build();

client.get()
        .uri("/catalog")
        .exchange()
        .expectStatus().isOk();
```

In this case, requests are handled by the mock infrastructure without opening a connection to a server at `localhost`. The base URL ensures relative URIs resolve under the same rules as when using the client with a real server. If the application needs full MVC/WebFlux configuration, filters, or controller advice, bind to an application context instead of only a single controller:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .baseUrl("http://localhost")
        .build();
```

`applicationContext` in the example is a Spring application context injected or created in the test.

### Relative URIs vs. Absolute URIs

When using a base URL, distinguish between the URI forms:

```java
// Uses the base URL to build the target URI.
client.get().uri("/v1/orders");

// Uses a URI template with path variables.
client.get().uri("/v1/orders/{id}", 42);

// An absolute URI already includes its own scheme and host.
client.get().uri("https://other.example.test/status");
```

An absolute URI specifies its own destination address and therefore does not rely on the builder's base URL. Relative URIs keep tests from repeating host and port on every call.

If you have shared URI template values, the builder also supports `defaultUriVariables(...)`. Default variables are used when resolving a URI template that does not pass all corresponding variables. For paths containing a specific ID, passing variables directly to `.uri(...)` is usually easier to read.

## 3. Setting Default Headers

Headers describe metadata of requests and responses. In API tests, commonly repeated headers include:

| Header | Meaning | Usage Example |
|---|---|---|
| `Accept` | Response formats the client can accept | `application/json` |
| `Content-Type` | Format of the request body being sent | `application/json` for JSON bodies |
| `Authorization` | Authentication credentials | Bearer token or Basic authentication dedicated to tests |
| `X-Client-Name` | Custom header defined by the application | Identifying the test client or caller source |
| `X-Correlation-Id` | Request correlation ID | Tracing a request across logs and processing components |

`defaultHeader(name, values...)` declares a default value for a header. The default value is applied if a specific request does not already have a header with that name. You can call this method multiple times to declare multiple headers:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Client-Name", "catalog-test")
        .build();
```

Every request using this client includes `Accept: application/json` and `X-Client-Name: catalog-test`, unless the request explicitly specifies that header.

When you need to configure multiple headers in a single operation, use `defaultHeaders(...)` to access the default `HttpHeaders` object:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .defaultHeaders(headers -> {
            headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));
            headers.set("X-Client-Name", "catalog-test");
            headers.setBasicAuth("test-user", "test-password");
        })
        .build();
```

Credentials in the example are dummy data strictly for test environments. Never place real credentials in source code or committed configuration. If the application uses Bearer tokens, obtain tokens from a test fixture or a test-only token issuance mechanism.

### Overriding headers per request

Default headers establish shared values, while individual requests can change values for a specific call. For example, a client defaults to JSON, but a particular test wants XML:

```java
client.get()
        .uri("/catalog/export")
        .headers(headers -> headers.setAccept(
                java.util.List.of(MediaType.APPLICATION_XML)))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_XML);
```

`headers(...)` lets you modify the `HttpHeaders` of the current request. Use `set(...)` when you want to replace an existing header value; use `add(...)` when you intend to append another value. This matters for headers that can hold multiple values, such as `Accept`.

Avoid mechanically setting `Content-Type: application/json` as a default for every request. `Content-Type` describes the body being sent; GET requests without a body generally do not need this header. Set the content type on requests that actually carry a body:

```java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("book-42", 2))
        .exchange()
        .expectStatus().isCreated();
```

Conversely, `Accept` describes the desired response format and is often a good fit for a test client's default configuration.

## 4. Configuring Default Codecs

Codecs are responsible for converting between HTTP bodies and Java data types. When sending a request, an encoder writes an object into bytes or content according to the media type. When reading a response, a decoder parses the body into the object requested by the test.

`WebTestClient.Builder.codecs(...)` allows customizing the client's `CodecConfigurer`. A common configuration is increasing the buffer limit for tests that need to read large JSON responses:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(4 * 1024 * 1024))
        .build();
```

The value `4 * 1024 * 1024` equals 4 MiB. Some codecs need to buffer data in memory before decoding or returning a result. If a body exceeds the limit, the operation can fail with `DataBufferLimitException`. Raising the limit is only appropriate when the test genuinely needs to handle large payloads and the environment has sufficient memory.

This limit does not automatically allow the server to accept larger requests. It configures the codec on the `WebTestClient` side. If the application enforces its own limits at the server, gateway, or storage layer, those limits still apply independently.

### Using a custom ObjectMapper for JSON

When the application has custom JSON rules—such as Java time handling, naming strategies, or custom modules—the test client can use the same Jackson configuration to serialize requests and deserialize responses:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> {
            configurer.defaultCodecs().jackson2JsonEncoder(
                    new Jackson2JsonEncoder(objectMapper));
            configurer.defaultCodecs().jackson2JsonDecoder(
                    new Jackson2JsonDecoder(objectMapper));
            configurer.defaultCodecs().maxInMemorySize(4 * 1024 * 1024);
        })
        .build();
```

In a Spring Boot application, consider using the `ObjectMapper` already configured in the application context so tests reflect the application's exact JSON configuration. The example above creates an independent mapper to illustrate the API; an actual mapper may need the same modules and features as the server.

Encoders and decoders handle opposite directions:

- `Jackson2JsonEncoder` converts Java objects into JSON when sending requests or writing bodies.
- `Jackson2JsonDecoder` reads JSON and creates Java objects when receiving responses.

If you replace only the encoder without replacing the decoder, requests and responses may use two different JSON configurations. When testing an API contract, clearly determine which direction needs configuration and keep both directions synchronized when appropriate.

## 5. Registering Custom Codecs

When a body uses a custom format or a data type not supported by default codecs, you can register additional encoders/decoders via `customCodecs()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .codecs(configurer -> {
            configurer.customCodecs().register(new MeasurementEncoder());
            configurer.customCodecs().register(new MeasurementDecoder());
        })
        .build();
```

`MeasurementEncoder` and `MeasurementDecoder` are application-defined classes that implement Spring's encoder/decoder contracts and advertise the media types they support. The example shows where registration happens; it does not assume a specific built-in Spring codec.

Custom codecs must declare the right Java types, media types, and buffer reading/writing behavior. You also need to manage `DataBuffer` allocation and release carefully, especially when working with streaming bodies. Registering a codec on the client does not make the server understand that format automatically; both the server and the test client must have compatible configurations.

## 6. When to Use ExchangeStrategies?

`ExchangeStrategies` encapsulates the set of readers/writers (codecs) and data-exchange strategies used by WebClient/WebTestClient. You can build a dedicated strategy and attach it to the builder:

```java
import org.springframework.web.reactive.function.client.ExchangeStrategies;

ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(4 * 1024 * 1024))
        .build();

WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .exchangeStrategies(strategies)
        .build();
```

Choose `codecs(...)` when you only need to adjust a few codecs on top of the builder's default configuration. Choose `exchangeStrategies(...)` when you want to reuse a separately created and managed strategy set, or need holistic control over the codec set.

Both approaches configure codecs for the client. Avoid building a strategy while simultaneously reconfiguring codecs in multiple places without knowing which strategy takes precedence; that pattern makes tests hard to understand and maintain.

## 7. Combining Configuration in a WebTestClient

A small factory can centralize shared base URL, headers, and codecs for a group of tests:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class ApiTestClientFactory {

    static WebTestClient create(String baseUrl) {
        return WebTestClient.bindToServer()
                .baseUrl(baseUrl)
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader("X-Client-Name", "integration-test")
                .codecs(configurer -> configurer.defaultCodecs()
                        .maxInMemorySize(4 * 1024 * 1024))
                .build();
    }
}
```

Tests can pass the server address matching the active runtime environment:

```java
WebTestClient client = ApiTestClientFactory.create("http://localhost:8080");

client.get()
        .uri("/api/products/{id}", 42)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
```

The factory should contain only genuinely shared configuration. Headers carrying test-specific data, short-lived tokens, or special media types should be set on individual requests so each test clearly expresses its input conditions.

## 8. Integrating with the Spring Boot Test Context

When testing a Spring Boot application with a real server on a random port, you can let Spring Boot provide `WebTestClient`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductApiIntegrationTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void readsProductAsJson() {
        webTestClient.get()
                .uri("/api/products/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
    }
}
```

In this mode, `WebTestClient` is configured to send requests to the application running on a random port. If a group of tests needs custom default headers or codecs, you can build a client with the appropriate builder and the running server's address, or organize a shared test factory. Avoid overriding the base URL with a fixed value that discards the random port assigned by Spring Boot.

If you only need to test controllers without starting a server, you can use `@WebFluxTest` or bind to a controller/application context. The binding mode determines which infrastructure is brought into the test; client settings such as base URL, headers, and codecs form a separate client-side configuration layer.

## 9. Common Confusions

| Symptom | Cause | Resolution |
|---|---|---|
| Request calls wrong host or port | Base URL is unconfigured, or test hardcodes a port while the server runs on a random port. | Use a base URL containing the actual runtime address; with Spring Boot random port, let test configuration manage the port or inject the assigned port. |
| Path has a duplicated prefix | Test appends a prefix already included in the base URL to the URI again. | Define clearly whether the base URL holds only the host or also a path prefix; pass only the remaining path in `.uri(...)`. |
| Default header does not appear | The request already specifies a header with the same name, so the default is not applied. | Check request-level headers; use `headers(...)` to explicitly set desired values. |
| Server returns `406 Not Acceptable` | `Accept` requests a media type the endpoint cannot produce. | Check default `Accept`, `produces`, and the server's message converters. |
| Server returns `415 Unsupported Media Type` | The request `Content-Type` is unsupported by the endpoint or the body is sent in the wrong format. | Set the appropriate content type on requests with a body and check codec encoders. |
| Reading large responses throws `DataBufferLimitException` | Codec needs to buffer a body exceeding the configured limit. | Consider raising `maxInMemorySize` reasonably or streaming data instead of buffering the entire body. |
| JSON deserialization differs from the application | Test client and server use different Jackson configurations. | Use an `ObjectMapper` or codec configuration compatible with the application. |
| Custom codec is not used | Codec is not registered properly or media type/Java type mismatches. | Check that the decoder/encoder supports the request/response types and media types. |
| Mock test mistakenly calls external server | Confusing `bindToController`/`bindToApplicationContext` with `bindToServer`. | Pick the binding mode matching your goal: mock infrastructure or real HTTP server. |

## 10. Principles for Organizing Configuration

- Use the base URL to centralize host and port; keep each request's URI relative whenever possible.
- Set default headers only when genuinely shared. Per-user headers, tokens, correlation IDs, or special media types should be configured per request if they vary across tests.
- Distinguish `Accept` (desired response format) from `Content-Type` (request body format).
- Use `codecs(...)` for routine codec adjustments such as buffer size or Jackson mapper; use `exchangeStrategies(...)` when packaging and reusing a complete codec strategy.
- Keep buffer limits finite and matched to expected payloads. Increasing the limit does not replace request/response size controls at other layers.
- Ensure client codecs match the media types and formats the server actually provides.
- Extract shared configuration into a factory or test configuration when shared across multiple tests; avoid building abstractions for a single simple test.
- Choose mock bindings for framework-level MVC/WebFlux testing and server binding for HTTP testing over a network; the base URL must correspond to the chosen binding mode.

## 11. Conclusion

`baseUrl(...)` resolves relative URIs and eliminates repeating host/port in every request. `defaultHeader(...)` and `defaultHeaders(...)` set default metadata while allowing individual requests to override values as needed. `codecs(...)` customizes encoders/decoders and buffer limits; `exchangeStrategies(...)` allows supplying a complete codec strategy set. When combining these three configuration groups, keep clear boundaries between client configuration, per-request configuration, and server configuration so tests accurately reflect the application's HTTP contract.
