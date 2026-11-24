# Verification Boundaries of RestClient, RestTemplate, or WebClient

**Context:** Spring Framework Testing → HTTP client testing.

A Spring application often calls external HTTP services to fetch data, send commands, or coordinate with other systems. These calls create a boundary between the application and the remote system. Testing that boundary requires verifying that the application constructs the right request, interprets the response properly, and handles error scenarios according to the agreed contract.

Spring has three commonly used HTTP clients:

- **RestTemplate:** A synchronous, template-style HTTP API widely used in existing Spring applications.
- **RestClient:** A fluent, synchronous HTTP API introduced in Spring Framework 6.1.
- **WebClient:** A reactive HTTP API supporting non-blocking I/O and data streaming.

All three can make HTTP calls, but their execution models, configuration, and testing tools differ. A good test must clearly identify the boundary to protect: whether the application's adapter creates the right HTTP request and handles the response properly; there is no need to re-test the entire third-party system that the application calls.

## 1. Where Does the HTTP Client Boundary Lie?

Suppose a sales application calls a Catalog service to check inventory. The controller receives a request from the user, the service orchestrates the business logic, and an adapter uses an HTTP client to call Catalog.

~~~text
HTTP request from user
        |
        v
OrderController
        |
        v
OrderService
        |
        v
CatalogGateway (application adapter)
        |
        v
RestClient / RestTemplate / WebClient
        |
        v
HTTP transport
        |
        v
External Catalog service
~~~

The verification boundary of an HTTP client lies at the call from the adapter to the HTTP transport. The test must confirm that the adapter translates the business request into a valid HTTP request and translates the HTTP response into a result or error understood by the application.

For example, when OrderService requests inventory information for a SKU, CatalogGateway needs to:

1. Call the right host and path.
2. Use the right HTTP method.
3. Encode path variables and query parameters correctly.
4. Send required headers such as Accept, Content-Type, Authorization, or correlation id.
5. Serialize the request body in the right format.
6. Read the response into the right DTO type.
7. Handle 4xx, 5xx statuses, empty bodies, or invalid responses.
8. Apply timeouts, retries, or cancellation according to the application's policy.

An adapter test does not need to verify Catalog's internal inventory algorithm. That is the Catalog system's responsibility. The application's test only needs to verify how the application interacts with the HTTP contract published by Catalog.

## 2. Distinguishing HTTP Client Testing from HTTP Server Testing

Both sides use HTTP, but they verify different responsibilities.

| Test type | Component under test | Key question |
|---|---|---|
| Controller test | Application endpoint receiving requests | Does the application respond properly when called by a client? |
| HTTP client adapter test | RestClient, RestTemplate, or WebClient used by the application | Does the application send the right request and handle the response from the remote service properly? |
| Application integration test | Multiple application components working together | Are configuration, dependency injection, and business flows wired properly? |
| End-to-end test with real service | Network integration with a real or sandbox environment | Can the systems actually interoperate in the deployment environment? |

**MockMvc** and **WebTestClient** are commonly used to test server-side endpoints. They send requests to the Spring application under test. They do not automatically test outbound HTTP calls made by controllers or services.

For example, if OrderController calls CatalogGateway, a MockMvc test can mock CatalogGateway to focus on the controller's response. A separate CatalogGateway test uses a mock HTTP server to inspect the actual request produced by RestClient or WebClient.

The two tests have different boundaries and complement each other.

## 3. Choosing Tools by HTTP Client Type

The testing tool should match the transport and abstraction used by the application.

| HTTP client | Execution style | Common tool for simulating the remote service |
|---|---|---|
| RestTemplate | Synchronous, blocking | MockRestServiceServer |
| RestClient | Synchronous, blocking | MockRestServiceServer |
| WebClient | Reactive, non-blocking | MockWebServer or WireMock |
| WebClient with very narrow logic | Reactive | Controlled stub ExchangeFunction |

**MockRestServiceServer** belongs to Spring Test and can bind to RestTemplate or RestClient.Builder to verify requests and provide mock responses. It is not a real network mock server; it intercepts requests at Spring's request factory layer.

**MockWebServer** and **WireMock** open a local HTTP server on loopback, letting the client send requests over real HTTP. They suit WebClient because they can verify that requests pass through the WebClient connector, HTTP codecs, and transport.

A fake ExchangeFunction can be used to test a slice of WebClient logic such as filters or request construction. However, this bypasses the actual HTTP connector, so it does not prove that network client configuration or socket transmission works properly.

Do not use MockRestServiceServer to test WebClient. The two tools operate at different client layers.

## 4. Designing Adapters for Clear Test Boundaries

Business logic should not manually build URLs, set headers, and parse responses everywhere. A centralized adapter defines the HTTP contract in one place.

Example:

~~~java
record ProductAvailability(String sku, boolean available) {}

interface CatalogGateway {
    ProductAvailability findAvailability(String sku);
}
~~~

OrderService only depends on the business interface:

~~~java
class OrderService {

    private final CatalogGateway catalogGateway;

    OrderService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    void placeOrder(String sku) {
        ProductAvailability availability =
                catalogGateway.findAvailability(sku);

        if (!availability.available()) {
            throw new OutOfStockException(sku);
        }

        // Continue processing the order.
    }
}
~~~

The HTTP adapter is responsible for calling the service:

~~~java
class HttpCatalogGateway implements CatalogGateway {

    private final RestClient restClient;

    HttpCatalogGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public ProductAvailability findAvailability(String sku) {
        return restClient.get()
                .uri("/products/{sku}/availability", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ProductAvailability.class);
    }
}
~~~

This design creates two easily testable boundaries:

- OrderService unit tests mock CatalogGateway to verify business decisions.
- HTTP adapter tests use a mock server to verify real communication at the HTTP client layer.

If a service builds URLs, serializes JSON, and handles status codes across many places, tests will struggle to pinpoint which component is responsible for the HTTP contract.

## 5. Testing RestClient with MockRestServiceServer

### 5.1. How Does RestClient Work?

RestClient is a synchronous HTTP client with a fluent API. Requests are constructed through steps such as:

- get(), post(), put(), delete(), or method(...).
- uri(...) to specify the address.
- header(...), contentType(...), and accept(...).
- body(...) to send data.
- retrieve() to handle the response by reading the body or mapping errors.
- body(...), toEntity(...), or corresponding operations to obtain the result.

RestClient was introduced in Spring Framework 6.1. It uses Spring's request factory and message converter infrastructure, and supports configuring a base URL, interceptors, default headers, and status handlers.

### 5.2. Binding a Mock Server to RestClient.Builder

Example configuration:

~~~java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://catalog.example.test");

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();

CatalogGateway gateway = new HttpCatalogGateway(restClient);
~~~

MockRestServiceServer is bound to the builder before creating the RestClient. Requests sent by the client are routed to the mock server to match expectations and return configured responses.

In a Spring configuration, you can obtain the builder from a managed bean and bind the mock server to that builder in the test. Ensure that the RestClient instance used by the adapter is the exact instance built from the bound builder.

### 5.3. Verifying a GET Request

Suppose the adapter calls:

~~~java
ProductAvailability result =
        gateway.findAvailability("SKU-42");
~~~

Test:

~~~java
@Test
void sendsExpectedGetRequestAndReadsJsonResponse() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/SKU-42/availability"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    ProductAvailability result =
            gateway.findAvailability("SKU-42");

    assertThat(result)
            .isEqualTo(new ProductAvailability("SKU-42", true));

    mockServer.verify();
}
~~~

The test verifies both sides of the contract:

- The request is sent to the expected URL, uses GET, and declares Accept JSON.
- The JSON response is read into ProductAvailability with the expected data.

If the adapter unintentionally changes the path, method, or header, the expectation fails. If the response is not deserialized properly, the assertion on the DTO fails.

### 5.4. Verifying Path Variables and Query Parameters

Suppose an API looks up a product by code and status:

~~~java
restClient.get()
        .uri(builder -> builder
                .path("/products/{sku}")
                .queryParam("includeInactive", false)
                .build(sku))
        .retrieve()
        .body(ProductAvailability.class);
~~~

The test can verify the final URI:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/products/SKU-42"
                        + "?includeInactive=false"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-42","available":true}
                """,
                MediaType.APPLICATION_JSON));
~~~

For data containing spaces, slashes, or Unicode characters, verify that URI encoding matches the contract. Using URI templates and builders instead of manual string concatenation helps prevent encoding bugs and path/query injection.

### 5.5. Checking a POST Request Body

Example of an adapter sending a reservation creation command:

~~~java
record ReservationRequest(String sku, int quantity) {}
record ReservationResponse(String reservationId) {}
~~~

Adapter:

~~~java
ReservationResponse reserve(String sku, int quantity) {
    return restClient.post()
            .uri("/reservations")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .body(new ReservationRequest(sku, quantity))
            .retrieve()
            .body(ReservationResponse.class);
}
~~~

Test:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "SKU-42",
                  "quantity": 2
                }
                """))
        .andRespond(withSuccess("""
                {
                  "reservationId": "RSV-100"
                }
                """, MediaType.APPLICATION_JSON));

ReservationResponse response = gateway.reserve("SKU-42", 2);

assertThat(response.reservationId()).isEqualTo("RSV-100");
mockServer.verify();
~~~

Verify the body fields that are meaningful to the contract. Avoid comparing JSON as a verbatim string if property order or whitespace is not an API requirement.

### 5.6. Checking Error Statuses and Exception Mapping

By default, RestClient with retrieve converts 4xx/5xx responses into an appropriate exception, typically subclasses of RestClientResponseException. The adapter can propagate that exception or map it to an application domain exception.

Example using onStatus:

~~~java
ProductAvailability findAvailability(String sku) {
    return restClient.get()
            .uri("/products/{sku}/availability", sku)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    (request, response) -> {
                        if (response.getStatusCode()
                                .equals(HttpStatus.NOT_FOUND)) {
                            throw new ProductNotFoundException(sku);
                        }
                    })
            .body(ProductAvailability.class);
}
~~~

Test for the not-found scenario:

~~~java
@Test
void mapsCatalogNotFoundToDomainException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/MISSING/availability"))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {"code":"PRODUCT_NOT_FOUND"}
                            """));

    assertThatThrownBy(() ->
            gateway.findAvailability("MISSING"))
            .isInstanceOf(ProductNotFoundException.class);

    mockServer.verify();
}
~~~

The test needs to confirm that the application throws the error type expected by the upstream service. It is not always necessary to assert every Spring exception detail if those details are not part of the internal contract.

## 6. Testing RestTemplate with MockRestServiceServer

### 6.1. RestTemplate and Responsibilities to Verify

RestTemplate is a synchronous, template-style API widely used in Spring applications before RestClient was introduced. It may still be used in existing systems.

Common methods:

- getForObject(...) and getForEntity(...).
- postForObject(...) and postForEntity(...).
- exchange(...) when control over method, headers, and response type is needed.
- execute(...) for callback scenarios or custom body handling.

The points to verify are the same as RestClient: URI, method, headers, body serialization, response decoding, and error handling.

### 6.2. Binding MockRestServiceServer

~~~java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

Example adapter:

~~~java
class LegacyCatalogGateway {

    private final RestTemplate restTemplate;
    private final String baseUrl;

    LegacyCatalogGateway(RestTemplate restTemplate, String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl;
    }

    ProductAvailability findAvailability(String sku) {
        return restTemplate.getForObject(
                baseUrl + "/products/{sku}/availability",
                ProductAvailability.class,
                sku
        );
    }
}
~~~

Test:

~~~java
@Test
void restTemplateReadsCatalogAvailability() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/products/SKU-42/availability"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    ProductAvailability result =
            gateway.findAvailability("SKU-42");

    assertThat(result.available()).isTrue();
    mockServer.verify();
}
~~~

For new code, URIs should be built with UriBuilder or centralized base URL configuration rather than string concatenation. The concatenation example above is abbreviated for readability; avoid slash bugs, query encoding issues, and differing host configurations across environments.

### 6.3. Checking Headers and Body with exchange

When you need to verify multiple request attributes, use HttpEntity:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
headers.setBearerAuth("test-token");

HttpEntity<ReservationRequest> request =
        new HttpEntity<>(
                new ReservationRequest("SKU-42", 2),
                headers
        );

ResponseEntity<ReservationResponse> response =
        restTemplate.exchange(
                baseUrl + "/reservations",
                HttpMethod.POST,
                request,
                ReservationResponse.class
        );
~~~

The mock server can verify the Authorization, Content-Type, and Accept headers along with the JSON body. In tests, use a fake token. Never put real tokens in source code or logs.

### 6.4. Checking Error Handlers

RestTemplate uses ResponseErrorHandler by default to handle error statuses. You can rely on the default handler and assert the exception, or provide a custom handler if the application maps errors according to its own contract.

Example with default behavior:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/products/MISSING"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() ->
        restTemplate.getForObject(
                "https://catalog.example.test/products/MISSING",
                ProductAvailability.class))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

mockServer.verify();
~~~

If the adapter has a custom ResponseErrorHandler, the test must verify that the status and error body are translated into the proper business error. It should also verify that the response error body is read and closed according to the client's mechanism; do not let a custom handler swallow errors or discard diagnostic information.

## 7. Testing WebClient with MockWebServer

### 7.1. Why Does WebClient Need a Different Tool?

WebClient uses a reactive API and a ClientHttpConnector to perform HTTP calls. In many applications, the connector is Reactor Netty; another connector may also be used.

MockRestServiceServer does not bind to WebClient. To verify requests made through WebClient, you can run a local mock HTTP server such as OkHttp's **MockWebServer** or **WireMock**.

MockWebServer opens a local HTTP port, receives real requests from WebClient, and lets the test enqueue mock responses. It supports verifying the method, path, headers, and body sent over the transport.

### 7.2. Test Dependencies

Gradle example when the project already manages versions via a BOM:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("com.squareup.okhttp3:mockwebserver")
}
~~~

WebClient belongs to spring-webflux; MockWebServer is a standalone library; StepVerifier belongs to reactor-test. The MockWebServer version should be managed consistently with the OkHttp version used by the project, if any.

If using WireMock instead of MockWebServer, choose the one mock server that fits your needs. You do not need to pull both libraries into the same test suite.

### 7.3. Initializing MockWebServer

JUnit 5 example:

~~~java
class WebClientCatalogGatewayTest {

    private MockWebServer mockServer;
    private WebClient webClient;
    private WebClientCatalogGateway gateway;

    @BeforeEach
    void setUp() throws IOException {
        mockServer = new MockWebServer();
        mockServer.start();

        webClient = WebClient.builder()
                .baseUrl(mockServer.url("/").toString())
                .build();

        gateway = new WebClientCatalogGateway(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        mockServer.shutdown();
    }
}
~~~

The server is created per test and shut down after the test completes. Do not use a fixed host or port because CI may run multiple tests concurrently.

### 7.4. Verifying a GET Request and Response DTO

Adapter:

~~~java
class WebClientCatalogGateway {

    private final WebClient webClient;

    WebClientCatalogGateway(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<ProductAvailability> findAvailability(String sku) {
        return webClient.get()
                .uri("/products/{sku}/availability", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(ProductAvailability.class);
    }
}
~~~

Test:

~~~java
@Test
void sendsGetRequestAndDecodesResponse() throws Exception {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {
                      "sku": "SKU-42",
                      "available": true
                    }
                    """));

    StepVerifier.create(gateway.findAvailability("SKU-42"))
            .assertNext(result -> {
                assertThat(result.sku()).isEqualTo("SKU-42");
                assertThat(result.available()).isTrue();
            })
            .verifyComplete();

    RecordedRequest request =
            mockServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request).isNotNull();
    assertThat(request.getMethod()).isEqualTo("GET");
    assertThat(request.getPath())
            .isEqualTo("/products/SKU-42/availability");
    assertThat(request.getHeader(HttpHeaders.ACCEPT))
            .isEqualTo(MediaType.APPLICATION_JSON_VALUE);
}
~~~

The test verifies both the request on the HTTP transport and the response decoded into a DTO by WebClient. StepVerifier subscribes to the Mono and verifies that it emits a single element and completes.

### 7.5. Verifying a POST Request Body

~~~java
@Test
void sendsReservationAsJson() throws Exception {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(201)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {"reservationId":"RSV-100"}
                    """));

    StepVerifier.create(gateway.reserve("SKU-42", 2))
            .assertNext(response ->
                    assertThat(response.reservationId())
                            .isEqualTo("RSV-100"))
            .verifyComplete();

    RecordedRequest request =
            mockServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request.getMethod()).isEqualTo("POST");
    assertThat(request.getPath()).isEqualTo("/reservations");
    assertThat(request.getHeader(HttpHeaders.CONTENT_TYPE))
            .contains(MediaType.APPLICATION_JSON_VALUE);
    String body = request.getBody().readUtf8();
    assertThat(body).contains("\"sku\":\"SKU-42\"");
    assertThat(body).contains("\"quantity\":2");
}
~~~

You can also parse the body as JSON to verify structure and values without depending on property order. What matters is checking the request actually sent by WebClient, not just inspecting the input object before serialization.

### 7.6. Checking HTTP Errors

WebClient retrieve converts 4xx/5xx statuses into WebClientResponseException by default. You can map them using onStatus:

~~~java
Mono<ProductAvailability> findAvailability(String sku) {
    return webClient.get()
            .uri("/products/{sku}/availability", sku)
            .retrieve()
            .onStatus(HttpStatusCode::is4xxClientError,
                    response -> response.bodyToMono(String.class)
                            .defaultIfEmpty("")
                            .map(body ->
                                    new ProductNotFoundException(sku)))
            .bodyToMono(ProductAvailability.class);
}
~~~

Test:

~~~java
@Test
void mapsNotFoundResponseToDomainException() {
    mockServer.enqueue(new MockResponse()
            .setResponseCode(404)
            .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {"code":"PRODUCT_NOT_FOUND"}
                    """));

    StepVerifier.create(gateway.findAvailability("MISSING"))
            .expectError(ProductNotFoundException.class)
            .verify(Duration.ofSeconds(3));
}
~~~

With WebClient, error assertions must subscribe to the publisher. If you only create the Mono without subscribing or verifying, the HTTP request may never execute and the test checks nothing.

### 7.7. Verifying Requests Were Sent and Not Duplicated

MockWebServer retains received requests as RecordedRequest objects. You can use it to verify retries or invocation counts:

~~~java
RecordedRequest first = mockServer.takeRequest();
RecordedRequest second = mockServer.takeRequest();

assertThat(first.getPath()).isEqualTo("/products/SKU-42");
assertThat(second.getPath()).isEqualTo("/products/SKU-42");
~~~

Only expect multiple requests when the application has a retry policy or makes multiple calls by design. Otherwise, an unexpected request may signal duplicate subscriptions, unintended retries, or code sending the request twice.

## 8. When Should You Use a Fake ExchangeFunction?

WebClient can accept a custom **ExchangeFunction**:

~~~java
ExchangeFunction exchangeFunction = request ->
        Mono.just(ClientResponse.create(HttpStatus.OK)
                .header(
                        HttpHeaders.CONTENT_TYPE,
                        MediaType.APPLICATION_JSON_VALUE)
                .body("""
                        {
                          "sku": "SKU-42",
                          "available": true
                        }
                        """)
                .build());

WebClient webClient = WebClient.builder()
        .exchangeFunction(exchangeFunction)
        .build();
~~~

This creates responses directly in the test without opening an HTTP port. It is useful when testing very narrow logic, for example:

- Filters that add authentication headers.
- Logic that selects a URI based on input.
- An adapter mapping a response into a domain object.
- Handling of a specific status at the ExchangeFunction layer.

However, a fake ExchangeFunction bypasses the real connector. The test does not verify DNS, sockets, TLS, connection pooling, network timeouts, or how the connector transmits the body. Depending on how ClientResponse is constructed, it also does not fully represent the behavior of an HTTP server and wire codecs.

If the goal is to verify WebClient's HTTP contract, prefer MockWebServer or WireMock. Use a fake ExchangeFunction for unit tests focused on filter or adapter logic when the transport part is already verified in another test.

## 9. Identifying Conditions to Check at the Boundary

Not every endpoint needs every attribute checked. Choose conditions that matter to the service contract.

### 9.1. URI and HTTP Method

Check:

- Do the scheme and host match the environment configuration?
- Is the base URL concatenated with the path incorrectly or missing a slash?
- Is the HTTP method correct?
- Are path variables encoded properly?
- Do query parameters have the right names, values, and encoding?
- Could the request be sent to the wrong endpoint?

For a base URL that varies by environment, tests can use a fake host while still verifying the path and query. Do not hard-code production hosts in tests.

### 9.2. Request Headers

Commonly important headers:

- Accept and Content-Type.
- Authorization.
- X-Request-Id or trace/correlation id.
- API version header.
- Locale or tenant id.
- Idempotency-Key for retryable operations.

Only assert headers that belong to the contract. Avoid locking down auto-generated transport headers such as User-Agent or Connection if the application does not commit to them.

### 9.3. Request Body

Check:

- Required fields and data types.
- JSON property names.
- Nulls, omitted fields, and default values.
- Dates, times, timezones, and number formats.
- Generic collections or nested objects.
- Whether sensitive content could be sent unintentionally.

Use representative data for realistic cases, including Unicode, special strings, and boundary values when they affect serialization.

### 9.4. Response Body

Check:

- The DTO is deserialized properly.
- Missing or null fields are handled properly.
- Unrecognized enum values.
- Generic types and collections.
- Empty responses or 204 No Content.
- Incorrect Content-Type or malformed bodies.
- Error bodies from the remote service.

Do not merely assert that the body is non-null. Check the fields that the business logic actually depends on.

### 9.5. HTTP Status and Business Errors

Clearly define how the adapter reacts to:

- 2xx: success.
- 3xx: whether redirects are followed or rejected per client policy.
- 400/401/403/404/409/422: request or business errors.
- 429: rate limiting.
- 5xx: remote service errors.
- Unexpected status codes or invalid bodies.

An adapter may map different statuses into distinct domain exceptions. Tests must ensure the business layer receives stable error types instead of depending too deeply on HTTP library-specific exceptions.

### 9.6. Timeout, Retry, and Cancellation

Timeouts and retries are part of the operational contract when they affect business outcomes.

Verify that:

- Requests do not wait indefinitely when the service does not respond.
- Retries occur only for permitted statuses or errors.
- The retry count is bounded.
- Backoff does not make tests excessively slow.
- Requests are idempotent if retried.
- When a subscriber cancels a Mono/Flux, the client stops work appropriately and releases resources.

Do not test timing with overly tight intervals that make tests flaky on CI. Use sufficiently generous timeouts and a mock server capable of controlling response delays when testing timeout behavior.

## 10. Boundaries of Test Types in an Application

HTTP client tests can be divided into layers so the same responsibility is not duplicated.

~~~text
                  Unit test
        Domain service + fake gateway
                  |
                  v
            HTTP adapter test
      MockRestServiceServer / MockWebServer
                  |
                  v
        Application integration test
    Spring context + adapter + real configuration
                  |
                  v
        External contract / smoke test
       Sandbox or real integrated service
~~~

### 10.1. Service Unit Tests

Mock interfaces such as CatalogGateway. Verify that the service calls the gateway at the right time, handles results, and throws appropriate business exceptions.

Unit tests do not need to start an HTTP server and should not check URLs, headers, or JSON serialization. Those details belong in adapter tests.

### 10.2. HTTP Adapter Tests

Use MockRestServiceServer or MockWebServer. Verify the request/response contract and how the adapter maps data.

This is usually the most important test layer for outbound clients because it catches URI, method, header, body, codec, and status-handling errors that unit tests mocking the gateway cannot see.

### 10.3. Application Integration Tests

Start a Spring context with real or production-like configuration to verify:

- The adapter is injected properly.
- The base URL is read from the right property.
- Interceptors/filters are registered.
- Timeouts and codecs are configured.
- Authentication or token providers are wired into the client.
- Services use the right adapter.

A mock HTTP server can be used as the target so there is no dependency on external services. This checks Spring configuration and the adapter together in one flow while keeping deterministic results.

### 10.4. Contract Tests and Smoke Tests with Real Services

When an OpenAPI spec, schema, or shared contract exists, you can verify that the adapter conforms to that contract. If actual connectivity needs verification, you can run a small set of smoke tests against the provider's sandbox.

Do not make the entire CI test suite depend on the Internet or an external service with mutable data. Tests against real services can fail due to network issues, quotas, maintenance, or environment data; limit their scope and keep them separate from fast, frequently run tests.

## 11. Limitations That Mock HTTP Servers Do Not Prove

A mock server creates a controllable boundary, but it does not simulate every characteristic of a network environment.

| Characteristic | MockRestServiceServer | MockWebServer/WireMock |
|---|---|---|
| URI, method, header, body | Yes | Yes |
| Response status and body | Yes | Yes |
| Spring message conversion | Can be tested via real client | Can be tested via real client |
| HTTP connector over socket | No | Yes |
| Real DNS and network routing | No | Does not represent production environment |
| TLS certificates and handshake | No | Can configure local TLS, but does not verify production PKI |
| Production proxy | No | Only if configured and set up correspondingly |
| Connection pool under real load | No | Does not fully represent production load |
| Real latency and packet loss | No | Can partially simulate delay, does not fully model real network |

For RestClient and RestTemplate, MockRestServiceServer replaces the request factory at the client layer. It is well suited for verifying the HTTP contract, but does not test real connectors or the network stack.

For WebClient, MockWebServer sends requests through the connector and a local socket. It verifies more of the HTTP transport, yet still does not prove DNS configuration, proxies, firewalls, TLS trust stores, or the stability of the real service in the deployment environment.

If these characteristics carry high risk, a separate group of integration/smoke tests in a controlled environment is needed.

## 12. Choosing Based on Practical Needs

| Need | Choice |
|---|---|
| Existing application using RestTemplate | MockRestServiceServer |
| New application using RestClient | MockRestServiceServer bound to RestClient.Builder |
| Application using WebClient needing real HTTP verification over local socket | MockWebServer or WireMock |
| Testing only WebClient filter logic | Fake ExchangeFunction |
| Testing business logic independent of HTTP | Mock gateway interface |
| Testing wiring, properties, and interceptors in Spring context | Application integration test with mock HTTP server |
| Verifying TLS, proxies, or sandbox services | Integration/smoke test in appropriate environment |

Do not choose a tool just because one creates mock responses faster. Choose according to the layer the test needs to protect. If you need to verify WebClient codecs, URIs, headers, and connectors, a stub ExchangeFunction may be too low-level. If you only need to verify that a service calls the gateway and handles the result, spinning up MockWebServer is overkill.

## 13. Common Mistakes When Testing HTTP Clients

### Green Tests but Wrong Actual Requests

If unit tests only mock the gateway, they do not verify URLs, methods, headers, or bodies. Add adapter tests using a mock server to verify the actual request constructed.

### Mock Server Does Not Receive Requests

Check whether the adapter is using the exact client instance bound to the mock server. For RestClient, bind to the builder before building the client. For RestTemplate, bind to the exact injected instance. For WebClient, confirm the base URL points to the running MockWebServer.

### WebClient Tests Do Not Execute Requests

WebClient returns lazy Mono or Flux publishers. Requests usually execute only when the publisher is subscribed to. Use StepVerifier, bounded blocking in appropriate synchronous tests, or an explicit subscriber. Do not merely create the publisher and end the test.

### JSON Response Fails to Decode

Check Content-Type, codecs/message converters, DTO types, generic types, and ObjectMapper configuration. The mock server must return the media type expected by the client.

### Tests Use Real Data or Real Tokens

Use fake hosts, fake data, and test tokens. Do not commit secrets or log Authorization/cookie headers. Base URLs and credentials should be injected via properties or test fixtures.

### Retries Cause Unexpected Extra Requests

Check the retry policy and subscription count. Verify that every retry has a valid reason, limits the number of attempts, and applies only to safely retryable operations.

### Tests Depend on Execution Order or Fixed Ports

Create a separate mock server per test or manage its lifecycle explicitly. Use dynamic ports and shut down the server in teardown. Do not share response queues across tests running in parallel without isolation.

### Confusing HTTP Errors with Connection Errors

HTTP 404/500 are responses from the server. Connection refused, DNS failures, TLS handshake failures, and timeouts are errors before or during transmission. Tests should distinguish these groups because retry behavior and exception mapping may differ.

## 14. Practical Guidelines

1. Place the HTTP client boundary inside an adapter with clear responsibilities.
2. Use MockRestServiceServer for RestClient and RestTemplate.
3. Use MockWebServer or WireMock for WebClient when you need to test HTTP through the connector.
4. Use a fake ExchangeFunction for narrow unit tests; do not treat it as proof of network transport.
5. Verify URIs, methods, headers, and bodies against the service contract.
6. Verify response decoding, error statuses, and the domain exceptions exposed by the application.
7. With WebClient, subscribe and verify publishers using StepVerifier.
8. Test timeouts, retries, and cancellation when they are part of the behavior to protect.
9. Use a mock HTTP server to verify Spring wiring and configuration without depending on external services.
10. Separate smoke tests against real services from fast, stable, regularly run test suites.
11. Do not re-test the internal logic of the remote system in adapter tests.
12. Do not put secrets, tokens, cookies, or sensitive data into fixtures or logs.

The verification boundary of RestClient, RestTemplate, and WebClient is the contract between the application and the HTTP service it calls. MockRestServiceServer fits Spring's two synchronous clients; MockWebServer or WireMock fits WebClient when requests need to be verified over HTTP transport. Choosing the right layer lets tests prove the application's requests, responses, and error handling while keeping test results stable and independent of external service state.

