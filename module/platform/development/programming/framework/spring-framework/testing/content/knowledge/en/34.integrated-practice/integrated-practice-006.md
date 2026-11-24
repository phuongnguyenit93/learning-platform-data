# Verifying External Service Clients with Controlled Responses

**Context:** Spring Framework Testing → Integrated Practice.

A Spring application often calls an external HTTP service to fetch data or perform a business operation. When testing this integration, we need control over the response returned by the external service so we can verify that the application sends the right request, decodes the response properly, and handles errors according to the contract.

Tests should not depend on the Internet, live data, or the state of an external service provider. A mock HTTP server or Spring's HTTP testing utilities can return predefined responses: success, not found, server error, empty body, or malformed responses.

This practice builds a flow from a business service to an HTTP client:

~~~text
OrderService
    |
    v
CatalogGateway
    |
    v
RestClient
    |
    v
MockRestServiceServer
    |
    +--> 200 JSON response
    +--> 404 response
    +--> 503 response
    +--> empty body response
~~~

Tests will verify both the outgoing request and how the application uses the received response. The real Catalog service does not need to be running during testing.

## 1. Testing Goals and Boundaries

Suppose a sales application needs to check inventory before creating an order. The application calls the Catalog API:

- GET /v1/items/{sku} to retrieve product details.
- POST /v1/reservations to reserve product quantity.
- Catalog returns JSON on success.
- Catalog returns 404 if the SKU does not exist.
- Catalog may return 5xx when the service encounters an outage.

The tests must prove:

1. The client calls the right host, path, and HTTP method.
2. The request includes appropriate Accept and Content-Type headers.
3. The request body is serialized properly when performing a POST operation.
4. The JSON response is deserialized into the right DTO.
5. The application distinguishes a non-existent product from a service error.
6. The business service only creates a reservation when the product is in stock.
7. A scenario does not send unexpected extra requests.
8. Tests produce repeatable results without needing external services.

This boundary is the outbound HTTP client adapter. It does not replace controller tests or tests of Catalog's internal logic. Tests for OrderService can mock the CatalogGateway interface; tests for HttpCatalogGateway need to inspect the actual HTTP requests produced by RestClient.

## 2. Choosing a Tool for Controlled Responses

Spring offers several ways to control HTTP client responses. Pick the tool matching the layer you want to verify.

| Tool | Suitable Client | How It Works | What It Verifies |
|---|---|---|---|
| MockRestServiceServer | RestClient, RestTemplate | Replaces the request factory with Spring's mock mechanism | URI, method, headers, body, status, and response conversion |
| MockWebServer | RestClient, RestTemplate, WebClient | Starts a local HTTP server; client sends requests over a socket | HTTP requests over local connector/transport and responses |
| WireMock | Various HTTP clients | Runs a mock HTTP server with mappings and request journal | HTTP contracts, scenarios, delays, and diverse response shapes |
| Mockito mock gateway | Business service | Replaces the adapter interface with a mock object | Business logic when receiving results/errors from the gateway |
| Fake ExchangeFunction | WebClient | Returns ClientResponse directly inside the pipeline | WebClient filter/adapter logic at the ExchangeFunction layer |

In this lesson, the primary examples use **RestClient** and **MockRestServiceServer** because this testing approach is directly supported by Spring. MockRestServiceServer does not open a network port; it inspects requests at Spring's request factory layer. As a result, it is well suited for verifying the HTTP contract and message conversion.

When you need to verify connectors, sockets, TLS, or timeouts at the HTTP transport layer, use MockWebServer or WireMock. Later sections show how to adapt the same scenario to those tools.

## 3. Preparing Dependencies

The examples below assume the application uses Spring Framework 6.1 or later for RestClient. Spring Boot projects can rely on Boot's dependency management to align versions.

With Gradle, relevant dependencies might include:

~~~groovy
dependencies {
    implementation("org.springframework:spring-web")
    implementation("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
~~~

In a Spring Boot application, the corresponding starters may already provide Spring Web, Jackson, JUnit, and AssertJ. Ensure `spring-test` is on the test classpath; Spring Boot typically brings it in via `spring-boot-starter-test`.

If using RestTemplate instead of RestClient, MockRestServiceServer is also in `spring-test`. If using WebClient, you need `spring-webflux` and typically `reactor-test` alongside MockWebServer or WireMock for HTTP over sockets.

## 4. Designing Data Types and the Gateway Interface

Start with DTOs representing responses and requests.

~~~java
public record CatalogItem(
        String sku,
        String name,
        boolean available
) {}

public record ReservationRequest(
        String sku,
        int quantity
) {}

public record Reservation(
        String reservationId,
        String sku,
        int quantity
) {}

public record OrderDecision(
        String sku,
        int quantity,
        String status,
        String reservationId
) {}
~~~

Define the interface used by the business service:

~~~java
public interface CatalogGateway {

    CatalogItem findBySku(String sku);

    Reservation reserve(String sku, int quantity);
}
~~~

The business service depends only on CatalogGateway. It does not need to know whether the application uses RestClient, RestTemplate, or WebClient.

~~~java
public class OrderService {

    private final CatalogGateway catalogGateway;

    public OrderService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    public OrderDecision placeOrder(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero");
        }

        CatalogItem item = catalogGateway.findBySku(sku);

        if (!item.available()) {
            return new OrderDecision(
                    sku, quantity, "REJECTED_OUT_OF_STOCK", null);
        }

        Reservation reservation =
                catalogGateway.reserve(sku, quantity);

        return new OrderDecision(
                sku,
                quantity,
                "CONFIRMED",
                reservation.reservationId()
        );
    }
}
~~~

This flow makes two key decisions:

- If Catalog reports the product is out of stock, OrderService returns a rejected result and does not call POST reservation.
- If the product is in stock, OrderService sends a reservation request and returns a confirmed result once Catalog creates the reservation.

Business exceptions are defined to decouple external service errors from Spring's HTTP error representations:

~~~java
public class CatalogItemNotFoundException extends RuntimeException {

    public CatalogItemNotFoundException(String sku) {
        super("Catalog item not found: " + sku);
    }
}

public class CatalogUnavailableException extends RuntimeException {

    public CatalogUnavailableException(String message) {
        super(message);
    }
}

public class CatalogProtocolException extends RuntimeException {

    public CatalogProtocolException(String message) {
        super(message);
    }
}
~~~

In a real application, exceptions can carry status, error codes, or correlation information. Avoid putting tokens, credentials, or response bodies containing sensitive data into exception messages.

## 5. Implementing the HTTP Adapter with RestClient

RestClient is the fluent synchronous HTTP API introduced in Spring Framework 6.1. The adapter is responsible for building requests, handling status codes, and reading response bodies.

~~~java
public class HttpCatalogGateway implements CatalogGateway {

    private final RestClient restClient;

    public HttpCatalogGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public CatalogItem findBySku(String sku) {
        CatalogItem item = restClient.get()
                .uri("/v1/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        status -> status.value() == 404,
                        (request, response) -> {
                            throw new CatalogItemNotFoundException(sku);
                        }
                )
                .onStatus(
                        HttpStatusCode::is5xxServerError,
                        (request, response) -> {
                            throw new CatalogUnavailableException(
                                    "Catalog returned HTTP "
                                            + response.getStatusCode().value()
                            );
                        }
                )
                .body(CatalogItem.class);

        if (item == null) {
            throw new CatalogProtocolException(
                    "Catalog returned an empty item response");
        }

        return item;
    }

    @Override
    public Reservation reserve(String sku, int quantity) {
        Reservation reservation = restClient.post()
                .uri("/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(new ReservationRequest(sku, quantity))
                .retrieve()
                .onStatus(
                        HttpStatusCode::is5xxServerError,
                        (request, response) -> {
                            throw new CatalogUnavailableException(
                                    "Catalog returned HTTP "
                                            + response.getStatusCode().value()
                            );
                        }
                )
                .body(Reservation.class);

        if (reservation == null) {
            throw new CatalogProtocolException(
                    "Catalog returned an empty reservation response");
        }

        return reservation;
    }
}
~~~

Several points to note:

- URIs use templates and path variables to avoid manual string concatenation.
- GET sends Accept JSON to declare the desired response media type.
- POST specifies Content-Type JSON and passes a DTO as the request body.
- 404 is mapped to CatalogItemNotFoundException.
- 5xx is mapped to CatalogUnavailableException.
- An empty body on a successful response is treated as a protocol error in this example.

Other 4xx statuses are not mapped specifically here and thus follow RestClient's default error handling. In a real application, define explicit contracts for 400, 401, 403, 409, 422, and 429 if the service needs to distinguish those cases.

## 6. Creating a RestClient Bound to MockRestServiceServer

The key step is binding MockRestServiceServer to the exact RestClient.Builder before building the client.

~~~java
private static final String CATALOG_BASE_URL =
        "https://catalog.example.test";

RestClient.Builder builder = RestClient.builder()
        .baseUrl(CATALOG_BASE_URL);

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(builder).build();

RestClient restClient = builder.build();

CatalogGateway gateway = new HttpCatalogGateway(restClient);
~~~

The mock server replaces the request factory inside the builder so requests from RestClient are matched against expectations registered by the test. Responses configured by the test are returned to the client like HTTP responses.

If the adapter is built from a different RestClient that did not use the bound builder, the mock server will not observe those requests. In Spring context tests, ensure the RestClient bean is built from the builder attached to the mock server.

Each test should have its own mock server or its own fixture. Do not share a single server with mutable expectations across concurrently running tests unless an isolation mechanism is in place.

## 7. Writing an Integration Test for the Successful Order Flow

### 7.1. Setting Up the Fixture for Each Test

~~~java
class OrderServiceHttpIntegrationTest {

    private MockRestServiceServer mockServer;
    private CatalogGateway catalogGateway;
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.example.test");

        mockServer = MockRestServiceServer.bindTo(builder).build();

        RestClient restClient = builder.build();

        catalogGateway = new HttpCatalogGateway(restClient);
        orderService = new OrderService(catalogGateway);
    }
}
~~~

The mock server and RestClient are recreated in each test. As a result, expectations from one scenario cannot leak into another.

### 7.2. Defining GET and POST Responses

The success scenario requires two responses:

1. GET item returns an available product.
2. POST reservation returns a reservation ID.

~~~java
@Test
void confirmsOrderWhenCatalogItemIsAvailable() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(
                    HttpHeaders.ACCEPT,
                    MediaType.APPLICATION_JSON_VALUE))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": true
                    }
                    """, MediaType.APPLICATION_JSON));

    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/reservations"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(content().json("""
                    {
                      "sku": "SKU-42",
                      "quantity": 2
                    }
                    """))
            .andRespond(withStatus(HttpStatus.CREATED)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "reservationId": "RSV-100",
                              "sku": "SKU-42",
                              "quantity": 2
                            }
                            """));

    OrderDecision decision = orderService.placeOrder("SKU-42", 2);

    assertThat(decision.status()).isEqualTo("CONFIRMED");
    assertThat(decision.sku()).isEqualTo("SKU-42");
    assertThat(decision.quantity()).isEqualTo(2);
    assertThat(decision.reservationId()).isEqualTo("RSV-100");

    mockServer.verify();
}
~~~

This test exercises OrderService, CatalogGateway, and RestClient. It verifies:

- GET is sent to the right URI and method.
- The Accept header is JSON.
- The JSON response is decoded into CatalogItem.
- POST is sent to the right endpoint.
- The request body contains the right SKU and quantity.
- The 201 response is decoded into Reservation.
- OrderService returns CONFIRMED with the corresponding reservation id.

The JSON matcher compares JSON structure, so it does not depend on property ordering or whitespace in the body.

### 7.3. Why Call verify() at the End of the Test?

MockRestServiceServer.verify() verifies that all registered expectations were satisfied. If the service fails to send the expected POST, the POST expectation remains unfulfilled and verify fails.

If the client sends an unexpected request, the mock server also reports an unmatched request. This catches cases where the service accidentally calls an endpoint an extra time.

Do not merely assert on the returned object and skip verify. A test might receive the expected result from stubbed code or an alternate path while the actual HTTP request has changed.

## 8. Controlling Responses for Each Scenario

An advantage of a mock HTTP server is that the test dictates the exact response the client receives. Each scenario can be written as a separate test to pinpoint the behavior being protected.

### 8.1. Product Out of Stock: HTTP 200

Not every business scenario is an HTTP error. Catalog can return HTTP 200 with available=false.

~~~java
@Test
void rejectsOrderWithoutCreatingReservationWhenItemIsUnavailable() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": false
                    }
                    """, MediaType.APPLICATION_JSON));

    OrderDecision decision = orderService.placeOrder("SKU-42", 2);

    assertThat(decision.status())
            .isEqualTo("REJECTED_OUT_OF_STOCK");
    assertThat(decision.reservationId()).isNull();

    mockServer.verify();
}
~~~

There is only one GET expectation. If OrderService mistakenly calls POST reservation, the request has no matching expectation and the test fails. This is how you verify a business branch does not trigger a side effect.

### 8.2. Non-Existent SKU: HTTP 404

~~~java
@Test
void mapsCatalogNotFoundToDomainException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/MISSING"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "code": "ITEM_NOT_FOUND",
                              "message": "Unknown SKU"
                            }
                            """));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("MISSING"))
            .isInstanceOf(CatalogItemNotFoundException.class)
            .hasMessageContaining("MISSING");

    mockServer.verify();
}
~~~

The test verifies that HTTP 404 is mapped by the adapter into a business exception. The service above does not need to depend on RestClientResponseException or HTTP client implementation details.

### 8.3. Catalog Server Error: HTTP 503

~~~java
@Test
void mapsCatalogServerFailureToUnavailableException() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                            {
                              "code": "TEMPORARILY_UNAVAILABLE"
                            }
                            """));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(CatalogUnavailableException.class)
            .hasMessageContaining("503");

    mockServer.verify();
}
~~~

HTTP 503 typically indicates the service is temporarily unable to handle the request. The adapter maps it to CatalogUnavailableException so the business layer can apply a retry policy, fallback, or report an error to the caller.

Do not automatically retry every POST. If an operation has side effects such as creating a reservation, retrying requires an idempotency key or a contract guaranteeing no duplicate reservations are created.

### 8.4. HTTP 200 (Success) with an Empty Body

In this example, the adapter requires the CatalogItem body to be present. We can test a 204 response:

~~~java
@Test
void rejectsEmptySuccessfulResponse() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andRespond(withStatus(HttpStatus.NO_CONTENT));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(CatalogProtocolException.class);

    mockServer.verify();
}
~~~

An empty response can be valid for some endpoints, such as DELETE returning 204. However, a GET endpoint requiring a CatalogItem cannot fulfill its contract without a body. Tests should reflect the endpoint's actual contract rather than assuming every 204 is an error.

### 8.5. Response Containing Invalid JSON

If the server returns a malformed body or lacks required data types, the message converter may throw an exception during deserialization.

~~~java
@Test
void failsWhenCatalogReturnsMalformedJson() {
    mockServer.expect(requestTo(
                    "https://catalog.example.test/v1/items/SKU-42"))
            .andRespond(withSuccess(
                    "{ this-is-not-valid-json",
                    MediaType.APPLICATION_JSON));

    assertThatThrownBy(() ->
            catalogGateway.findBySku("SKU-42"))
            .isInstanceOf(RestClientException.class);

    mockServer.verify();
}
~~~

The exact exception type may depend on the message converter and Spring/Jackson version. If the adapter needs to normalize decoding errors into CatalogProtocolException, catch and map the appropriate error in the adapter and test against that contract. Do not assert that all deserialization errors yield the exact same exception class across all configurations.

## 9. Verifying POST Request Body and Headers in Detail

When a client sends a state-changing command, the request body is a critical part of the contract.

Example reservation request:

~~~java
new ReservationRequest("SKU-42", 2)
~~~

MockRestServiceServer can verify:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "SKU-42",
                  "quantity": 2
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "reservationId": "RSV-100",
                          "sku": "SKU-42",
                          "quantity": 2
                        }
                        """));
~~~

If the API requires an idempotency key, correlation id, or authorization header, add the corresponding expectations:

~~~java
.andExpect(header("Idempotency-Key", "order-test-100"))
.andExpect(header("X-Correlation-Id", "trace-test-100"))
~~~

Do not use real tokens in test fixtures. If you need to verify Authorization, use fake credentials and only verify that the header matches the expected format or test value.

Do not verify every header automatically generated by the HTTP stack such as Connection, User-Agent, or Content-Length unless they are part of the adapter's contract. Those headers can vary by request factory, JDK, or connector.

## 10. Distinguishing HTTP Errors from Connection Errors

MockRestServiceServer controls responses at the request factory layer. It is well suited for simulating statuses and bodies, but it does not fully simulate a network timeout or a failed TLS handshake.

Two error categories must be distinguished:

| Error Category | Examples | Appropriate Testing Method |
|---|---|---|
| HTTP response error | 404, 429, 500, 503 | MockRestServiceServer or mock HTTP server |
| Transport error | Connection refused, socket disconnect, DNS failure, timeout, TLS handshake failure | MockWebServer/WireMock with socket policies or appropriate transport environment tests |

If the application has timeout or retry policies, write dedicated transport tests. Do not use an HTTP 503 response to conclude that the client handles connection timeouts properly; those are two different situations.

With RestClient/RestTemplate, MockWebServer can open a local port, allowing the client to perform HTTP over a real connector. You can then configure response delays or drop connections. Choose an explicit request factory if you need to test a specific transport behavior.

## 11. When You Need to Test HTTP Transport with MockWebServer

### 11.1. Starting a Local Server

MockWebServer is part of the OkHttp library. It runs an HTTP server on loopback with a dynamic port.

~~~java
class CatalogTransportTest {

    private MockWebServer mockWebServer;
    private RestClient restClient;

    @BeforeEach
    void setUp() throws IOException {
        mockWebServer = new MockWebServer();
        mockWebServer.start();

        restClient = RestClient.builder()
                .baseUrl(mockWebServer.url("/").toString())
                .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        mockWebServer.shutdown();
    }
}
~~~

The test enqueues responses:

~~~java
@Test
void sendsRequestThroughLocalHttpServer() throws Exception {
    mockWebServer.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE)
            .setBody("""
                    {
                      "sku": "SKU-42",
                      "name": "Mechanical Keyboard",
                      "available": true
                    }
                    """));

    CatalogItem item = restClient.get()
            .uri("/v1/items/{sku}", "SKU-42")
            .retrieve()
            .body(CatalogItem.class);

    assertThat(item.available()).isTrue();

    RecordedRequest request =
            mockWebServer.takeRequest(1, TimeUnit.SECONDS);

    assertThat(request).isNotNull();
    assertThat(request.getMethod()).isEqualTo("GET");
    assertThat(request.getPath()).isEqualTo("/v1/items/SKU-42");
}
~~~

MockWebServer receives requests over local HTTP. Tests can inspect RecordedRequest, response delays, socket policies, and transport details that MockRestServiceServer does not simulate.

### 11.2. Testing Delays and Timeouts

You can enqueue a delayed response:

~~~java
mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBodyDelay(2, TimeUnit.SECONDS)
        .setBody("""
                {"sku":"SKU-42","name":"Keyboard","available":true}
                """));
~~~

Then configure the HTTP client timeout shorter than the delay and verify that the adapter handles the timeout error according to the contract.

How timeouts are configured depends on the request factory/connector used by RestClient. Therefore, tests must initialize the client with the exact factory deployed in production or one with matching behavior. Do not merely change an arbitrary timeout in a test and infer that production configuration is correct.

### 11.3. Testing Disconnects

MockWebServer provides socket policies to simulate connection scenarios, such as closing the socket before the response completes. Use them when you need to verify how the adapter or retry policy handles transport failures.

Specific socket policies and exception behaviors depend on the MockWebServer/HTTP client version. Assert on the application's stable contract, such as CatalogUnavailableException or a defined retry count, rather than tying tests to JDK exception messages.

## 12. Adapting the Same Scenario to RestTemplate

RestTemplate can also be tested with MockRestServiceServer. The main difference is how the client API is called.

Setup:

~~~java
RestTemplate restTemplate = new RestTemplate();

MockRestServiceServer mockServer =
        MockRestServiceServer.bindTo(restTemplate).build();
~~~

Adapter:

~~~java
CatalogItem item = restTemplate.getForObject(
        "https://catalog.example.test/v1/items/{sku}",
        CatalogItem.class,
        sku
);
~~~

Expectation:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("""
                {
                  "sku": "SKU-42",
                  "name": "Mechanical Keyboard",
                  "available": true
                }
                """, MediaType.APPLICATION_JSON));

CatalogItem item = gateway.findBySku("SKU-42");

assertThat(item.available()).isTrue();
mockServer.verify();
~~~

MockRestServiceServer verifies requests and responses at Spring's request factory layer. There is no need to mock CatalogGateway in the adapter test because the goal is to test that RestTemplate itself is configured and used properly.

## 13. Adapting the Same Scenario to WebClient

WebClient is a reactive client. Requests usually execute only when the Mono or Flux is subscribed to. To test HTTP over a connector, use MockWebServer or WireMock.

Adapter example:

~~~java
public Mono<CatalogItem> findBySku(String sku) {
    return webClient.get()
            .uri("/v1/items/{sku}", sku)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new CatalogItemNotFoundException(sku))
            )
            .onStatus(
                    HttpStatusCode::is5xxServerError,
                    response -> Mono.error(
                            new CatalogUnavailableException(
                                    "Catalog server failure"))
            )
            .bodyToMono(CatalogItem.class);
}
~~~

Test using an enqueued response:

~~~java
mockWebServer.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader(
                "Content-Type",
                MediaType.APPLICATION_JSON_VALUE)
        .setBody("""
                {
                  "sku": "SKU-42",
                  "name": "Mechanical Keyboard",
                  "available": true
                }
                """));

StepVerifier.create(webClientCatalogGateway.findBySku("SKU-42"))
        .assertNext(item -> {
            assertThat(item.sku()).isEqualTo("SKU-42");
            assertThat(item.available()).isTrue();
        })
        .verifyComplete();
~~~

Do not just call findBySku and end the test. If the publisher has not been subscribed to, the request may never be sent. StepVerifier performs the subscription and verifies signals.

For long-lived streams, verify a few necessary events and then cancel the subscription deliberately. For finite Mono or Flux, verify completion or error as required by the contract.

## 14. When to Use Mockito Instead of a Mock HTTP Server?

The two test styles answer two different questions.

### 14.1. Service Unit Test with a Mock Gateway

~~~java
@Test
void rejectsOrderWhenCatalogSaysUnavailable() {
    CatalogGateway gateway = mock(CatalogGateway.class);

    given(gateway.findBySku("SKU-42"))
            .willReturn(new CatalogItem(
                    "SKU-42", "Mechanical Keyboard", false));

    OrderService service = new OrderService(gateway);

    OrderDecision decision = service.placeOrder("SKU-42", 2);

    assertThat(decision.status())
            .isEqualTo("REJECTED_OUT_OF_STOCK");

    then(gateway).should().findBySku("SKU-42");
    then(gateway).shouldHaveNoMoreInteractions();
}
~~~

This test focuses on OrderService logic. It does not verify URLs, HTTP methods, headers, JSON serialization, or response conversion.

### 14.2. Adapter Test with MockRestServiceServer

The adapter test creates a real RestClient and controls the HTTP response:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-42","name":"Keyboard","available":true}
                """,
                MediaType.APPLICATION_JSON));

CatalogItem item = catalogGateway.findBySku("SKU-42");

assertThat(item.available()).isTrue();
mockServer.verify();
~~~

This test protects the contract between the adapter and the Catalog service.

A good test suite can have both layers: fast service unit tests and adapter tests verifying the HTTP contract. You do not need to spin up a mock HTTP server in every business unit test.

## 15. Organizing Stable Expectations and Fixtures

### 15.1. Each Test Declares Its Own Responses

Do not use a static response queue or a shared MockRestServiceServer across independent tests. Each test needs to know which response is returned for which request.

Organization pattern:

- Create the builder and mock server in the test setup.
- Register expectations directly inside the test case.
- Invoke the service/adapter.
- Assert on business results and requests.
- Call verify to confirm expectations were consumed.
- Release resources after the test if using a real server.

### 15.2. Ordered Expectations

By default, MockRestServiceServer can verify requests in the order expectations were registered. For a flow with GET followed by POST, this order reflects the business sequence.

If request ordering is not part of the contract and a test genuinely allows multiple independent requests, you can configure unordered expectations per your Spring Test version's API. Only do so when order has no meaning; if order is part of the workflow, keep sequential expectations to catch bugs.

### 15.3. Using Meaningful Response Fixtures

JSON contents should represent the real contract:

- Required values are present.
- Data types are accurate.
- Business states are explicit.
- Error codes are stable.
- Optional fields are tested when the application relies on them.

There is no need to copy real responses with hundreds of fields if the adapter only uses a small subset. However, do not strip required fields such that the test stops verifying deserialization and mapping.

### 15.4. Avoiding Over-Specifying Non-Contractual Details

Verify meaningful methods, URIs, headers, and bodies. Avoid coupling tests to:

- JSON key ordering.
- Whitespace or newlines.
- Headers automatically generated by the HTTP stack.
- Internal exception messages from a specific library version.
- Field order in a DTO unless it is part of the contract.

Tests should fail when application behavior changes in an impactful way, not when unimportant implementation details shift.

## 16. Testing Retries and Idempotency

If the adapter has retries, controlled responses let you simulate an initial failure followed by a success.

Example response sequence:

1. First call receives HTTP 503.
2. Next call receives HTTP 200.
3. Client retries only the configured number of times.
4. Repeated requests preserve the same idempotency key if the operation has side effects.

With MockRestServiceServer, register two expectations for the same URI in sequence:

~~~java
mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

mockServer.expect(requestTo(
                "https://catalog.example.test/v1/items/SKU-42"))
        .andRespond(withSuccess("""
                {
                  "sku": "SKU-42",
                  "name": "Keyboard",
                  "available": true
                }
                """, MediaType.APPLICATION_JSON));
~~~

The test should exercise the retry policy configured in the adapter. If retries use backoff, use a controlled scheduler or test time when supported by the framework; do not add arbitrary Thread.sleep calls.

For POST requests creating reservations, retries can create duplicate reservations. Only retry when the API has an idempotency key or a mechanism ensuring repeated commands do not create a second side effect. Tests should verify that the same key is sent across retries and the request count does not exceed the limit.

## 17. Testing Timeouts and Time Limits

Timeouts can occur at multiple layers:

- Connection timeout: failing to establish a connection.
- Response/read timeout: server fails to return data in time.
- Overall request deadline: total processing time exceeds the threshold.
- Reactive timeout: publisher fails to emit a signal within the allowed time.

MockRestServiceServer does not fully simulate socket delays. Use MockWebServer/WireMock to inject response delays or close connections when you need to verify transport handling.

Tests should have a timeout for the test itself to avoid hanging builds. Example with Reactor:

~~~java
StepVerifier.create(webClientGateway.findBySku("SKU-42"))
        .expectError()
        .verify(Duration.ofSeconds(5));
~~~

StepVerifier's timeout caps how long the test waits for a signal; it does not configure a timeout on the HTTP client. The client itself still needs its own timeout configured.

If you need to assert a specific exception type, map transport errors inside the adapter and assert on the business exception. Avoid depending on an exception class that can vary by request factory or connector.

## 18. Test Case Matrix for the Catalog Adapter

A practical test suite might include:

| Scenario | Controlled Response | What to Verify |
|---|---|---|
| Product in stock | 200 + available=true | Correct DTO, service proceeds to POST reservation |
| Product out of stock | 200 + available=false | Service rejects and does not send POST |
| Non-existent SKU | 404 | Adapter throws CatalogItemNotFoundException |
| Catalog temporarily down | 503 | Adapter throws CatalogUnavailableException |
| Empty response | 204 | Adapter handles per contract, e.g., CatalogProtocolException |
| Malformed JSON | 200 + malformed JSON | Decoding fails or maps to protocol error |
| POST request | 201 + reservation JSON | Method, URI, headers, and request body are right |
| Timeout | Server delay exceeds threshold | Client times out and adapter handles properly |
| Disconnect | Socket closes before response | Transport error is mapped properly |
| Retry | 503 then 200 | Invocation count, backoff, and idempotency are right |

Not every project needs every scenario. Select the cases matching your adapter's contract and error policy.

## 19. Common Mistakes When Testing with Controlled Responses

### Test Only Mocks the Gateway Interface

When mocking CatalogGateway, service tests do not verify HTTP requests. Add adapter tests using a real RestClient/RestTemplate/WebClient and mock HTTP responses at the proper layer.

### Mock Server Receives No Requests

Check whether the client was built from the builder bound to MockRestServiceServer. If the adapter uses another RestClient, expectations will not observe those requests.

### WebClient Never Executes the Request

Mono/Flux are lazy. You must subscribe, for example with StepVerifier, before reading RecordedRequest or finishing the test.

### Request Body Mismatch

Check Content-Type, DTOs, Jackson configuration, and the JSON contract. Use a JSON matcher instead of string comparison when property order does not matter.

### verify() Reports Unmet Expectations

The service may not have reached the expected step, exited early due to an exception, or skipped calling the client. Inspect earlier assertions and expectation ordering to identify which branch did not execute.

### Unexpected Extra Requests

A request might be sent due to retries, multiple subscriptions, duplicate calls in the service, or a background callback. Use the mock server's request count/journal to identify the number of calls.

### Tests Pass While Production Timeouts Are Still Wrong

MockRestServiceServer does not simulate socket delays. Use MockWebServer/WireMock and configure the matching client to test transport timeouts.

### Tests Depend on Real Services

If tests call production or a real sandbox host, results can vary with network, data, and service state. Replace the base URL with a mock server and keep a separate smoke test group for real integration environments.

### Tests Share a Mock Server Across Multiple Tests

Expectations and response queues are stateful. Create a dedicated server per test or use explicit locking/isolation if sharing is unavoidable. Never reset queues while another test is using them.

## 20. End-to-End Practice Workflow

You can implement this practice in the following sequence:

1. Define the outbound contract: URI, method, headers, body, status, and response schema.
2. Create DTOs for requests and responses.
3. Define a gateway interface so the business service does not depend on a specific HTTP client.
4. Implement the adapter using RestClient, RestTemplate, or WebClient.
5. Choose MockRestServiceServer for RestClient/RestTemplate at Spring's request factory layer.
6. Choose MockWebServer/WireMock when you need to test connectors and HTTP transport.
7. Create an isolated mock server for the test and register controlled responses.
8. Invoke the real service/adapter in the test.
9. Assert on business outcomes, exceptions, and actual requests.
10. Call verify to catch missing or unexpected requests.
11. Add tests for HTTP errors, invalid bodies, timeouts, or retries when those are part of the contract to protect.
12. Keep smoke tests against real services in a separate group with controlled configuration and data.

## 21. Practice Principles

1. Test outbound HTTP at the adapter boundary, not just by mocking the gateway interface.
2. Use controlled responses so tests are repeatable and independent of external services.
3. Use MockRestServiceServer for RestClient and RestTemplate when testing Spring request/response handling.
4. Use MockWebServer or WireMock when requests need to traverse an HTTP connector and socket.
5. Use StepVerifier to execute and verify WebClient Mono/Flux publishers.
6. Verify URI, method, headers, request body, and response decoding.
7. Distinguish HTTP error responses from transport failures.
8. Map remote errors into stable business exceptions when the service needs a clear contract.
9. Verify that business branches do not send unexpected follow-up requests.
10. Call verify or inspect the request journal to confirm the exact call count.
11. Only retry operations with an explicit policy; use an idempotency key for repeatable side effects.
12. Never use Thread.sleep for synchronization; set finite timeouts on tests and publishers.
13. Create a dedicated mock server and fixtures per test whenever possible.
14. Never put secrets, tokens, or sensitive data into response fixtures or logs.
15. Separate stable adapter tests from smoke tests that depend on real services.

A controlled response lets a test reproduce exactly what the HTTP client receives. Combining request expectations with business assertions proves both sides of the integration: the application sends the right requests and reacts properly to results from the external service. MockRestServiceServer fits testing RestClient/RestTemplate at the Spring layer; MockWebServer or WireMock extends verification to HTTP transport; and Mockito fits service unit tests when protocol verification is unnecessary.

