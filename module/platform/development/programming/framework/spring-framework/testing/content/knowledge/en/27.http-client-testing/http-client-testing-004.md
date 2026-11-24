# Setting Expectations for Outbound URI, Method, Headers, and Body

When a service makes HTTP calls to another system, tests need to verify the request that the application actually sends. With Spring Framework, `MockRestServiceServer` lets you inspect requests from `RestClient` and `RestTemplate` without calling an external server. Tests can set expectations on the URI, HTTP method, query parameters, headers, and body, then provide mock responses to check how the application processes the result.

The key point is testing at the HTTP client boundary. We want to know that the client sends the right address, the right method, the right data, and handles responses according to the contract. There is no need to spin up a real server for every unit test of the HTTP integration layer.

## 1. Testing Flow for an HTTP Client

Suppose an application has an `InventoryClient` calling an inventory service:

~~~text
Service in the application
        |
        v
InventoryClient
        |
        |  RestClient / RestTemplate
        v
MockRestServiceServer
        |
        +--> verify URI
        +--> verify HTTP method
        +--> verify headers
        +--> verify request body
        |
        +--> return mock response
        |
        v
InventoryClient handles response
~~~

The test declares expected requests before invoking the code under test. When the client sends a request, the mock server compares the actual request against the registered matchers. If the request does not match, the test fails with an error describing which expectation was not satisfied.

For Spring `RestClient` and `RestTemplate`, the standard tool is `MockRestServiceServer` in the Spring Test module. This mechanism replaces the request factory so requests are handled inside the test process; it does not open sockets to real hosts.

## 2. Creating RestClient and Binding MockRestServiceServer

Spring Framework 6.1 and later support binding `MockRestServiceServer` directly to `RestClient.Builder`. Bind before building `RestClient` so the builder uses the request factory managed by the mock server.

Example client class:

~~~java
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public InventoryItem findBySku(String sku) {
        return restClient.get()
                .uri("/api/items/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(InventoryItem.class);
    }
}
~~~

Test:

~~~java
class InventoryClientTest {

    private MockRestServiceServer server;
    private InventoryClient inventoryClient;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.example");

        server = MockRestServiceServer.bindTo(builder).build();
        inventoryClient = new InventoryClient(builder.build());
    }

    @Test
    void sendsGetRequestForSku() {
        server.expect(requestTo(
                        "https://inventory.example/api/items/COFFEE-01"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andRespond(withSuccess("""
                        {
                          "sku": "COFFEE-01",
                          "available": 12
                        }
                        """, MediaType.APPLICATION_JSON));

        InventoryItem item = inventoryClient.findBySku("COFFEE-01");

        assertThat(item.sku()).isEqualTo("COFFEE-01");
        assertThat(item.available()).isEqualTo(12);
        server.verify();
    }
}
~~~

In this test:

- `baseUrl` defines the root host the client uses.
- `bindTo(builder)` attaches the mock server to the builder.
- `expect(requestTo(...))` checks the full URI.
- `andExpect(method(...))` checks the method.
- `andExpect(header(...))` checks headers.
- `andRespond(withSuccess(...))` provides the mock response.
- `verify()` confirms that expectations were satisfied.

By default, each expectation requires the matching request to occur once. If the code sends no request, calls the wrong endpoint, or sends an extra undeclared request, the test detects the discrepancy.

## 3. Verifying URI and Query Parameters

The URI is a core part of the integration contract. A request may have the right method and body yet still hit the wrong host, path, or query parameters.

### 3.1. Verifying the Full URI

The `requestTo(...)` matcher checks the request URI:

~~~java
server.expect(requestTo(
                "https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Use the full URI when host, base path, or path is a critical part of client configuration. This catches base URL concatenation bugs, missing prefixes, or calls to the wrong endpoint.

### 3.2. Verifying Query Parameters

Example client searching for products by keyword and pagination:

~~~java
public List<CatalogItem> search(String keyword, int page, int size) {
    return restClient.get()
            .uri(uriBuilder -> uriBuilder
                    .path("/api/catalog")
                    .queryParam("q", keyword)
                    .queryParam("page", page)
                    .queryParam("size", size)
                    .build())
            .retrieve()
            .body(new ParameterizedTypeReference<>() {});
}
~~~

Setting expectations:

~~~java
server.expect(requestTo(
                "https://catalog.example/api/catalog?q=green+tea&page=0&size=20"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
~~~

You can use the `queryParam(...)` matcher to check individual parameters without assembling the whole URI:

~~~java
server.expect(requestTo(
                "https://catalog.example/api/catalog?q=green+tea&page=0&size=20"))
        .andExpect(queryParam("q", "green tea"))
        .andExpect(queryParam("page", "0"))
        .andExpect(queryParam("size", "20"))
        .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));
~~~

When using query parameter matchers, the test clearly states which parameters belong to the contract. If query parameter order does not matter, per-key matchers are often easier to read and less coupled to how the URI builder orders parameters.

### 3.3. Special Characters and Encoding

Do not concatenate query strings manually with `+` if values can contain spaces, plus signs, ampersands, or Unicode characters. Use `UriBuilder` so Spring encodes values properly for the URI context.

For example, the keyword `tea & coffee` must be encoded so `&` is not interpreted as a separator between two query parameters. Tests should check both the decoded value with `queryParam(...)` and the final URI when exact encoding needs verification.

Path variables must also be encoded appropriately. Identifier data containing `/`, `?`, or `#` should not be inserted directly into the path in a way that alters URL structure. Define which characters the identifier contract allows and test how the client builds the URI.

## 4. Verifying the HTTP Method

The `method(...)` matcher verifies that the client uses the right HTTP method:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.PUT))
        .andRespond(withSuccess());
~~~

Common method mistakes:

- Using `GET` instead of `POST` when creating a resource.
- Using `PUT` when the contract requires `PATCH` for partial updates.
- Sending `DELETE` to the wrong path.
- Sending a body with a method or endpoint that does not support that body.

Do not verify only the URI while ignoring the method. The same URI can have completely different behavior depending on the method.

Example update test:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.PATCH))
        .andRespond(withSuccess());
~~~

If the API requires `PUT` instead of `PATCH`, the expectation fails when the client sends the wrong method.

## 5. Verifying Headers

Headers carry metadata and request control information. Common headers to verify:

- `Accept`: the response format expected by the client.
- `Content-Type`: the format of the body sent by the client.
- `Authorization`: authentication credentials.
- `If-Match` or `If-None-Match`: update or caching preconditions.
- `Idempotency-Key`: key preventing duplicate processing per the API contract.
- `X-Correlation-ID` or `traceparent`: request correlation ID across systems.

Example:

~~~java
server.expect(requestTo("https://payment.example/api/charges"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header(
                HttpHeaders.CONTENT_TYPE,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header(
                HttpHeaders.AUTHORIZATION,
                "Bearer test-access-token"))
        .andExpect(header("Idempotency-Key", "charge-001"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

For multi-valued headers, check values using the appropriate header matchers. For optional headers, `headerDoesNotExist(...)` helps confirm that the client does not send unnecessary information.

Do not put real tokens in test fixtures or logs. Use fake test-only tokens and simply verify that the header is formatted correctly. If you need to verify that a token comes from configuration, inject a controllable test value.

## 6. Verifying the Request Body

When a client sends JSON, verify both the body and `Content-Type`. Example:

~~~java
public void createItem(CreateItemRequest request) {
    restClient.post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .retrieve()
            .toBodilessEntity();
}
~~~

Test:

~~~java
server.expect(requestTo("https://inventory.example/api/items"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "sku": "COFFEE-01",
                  "quantity": 12
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED));
~~~

The `content().json(...)` matcher compares the body as JSON rather than comparing a whitespace-formatted byte string. This keeps the test focused on JSON content. If whitespace or property ordering genuinely matters for a special protocol, use a string or byte matcher instead.

For text bodies:

~~~java
server.expect(requestTo("https://legacy.example/api/commands"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().string("REFRESH CACHE"))
        .andRespond(withSuccess());
~~~

For URL-encoded form bodies, check the content type and form payload against the contract:

~~~java
server.expect(requestTo("https://auth.example/token"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_FORM_URLENCODED))
        .andExpect(content().string(
                containsString("grant_type=client_credentials")))
        .andRespond(withSuccess(
                "{\"access_token\":\"test-token\"}",
                MediaType.APPLICATION_JSON));
~~~

Do not assert the body with a rigid long string if field order or whitespace is not part of the contract. Conversely, do not use matchers so loose that the test misses omitted critical fields.

## 7. Combining Multiple Expectations for One Request

A single expectation can combine URI, method, query, headers, and body:

~~~java
server.expect(requestTo("https://payment.example/api/charges?region=apac"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(queryParam("region", "apac"))
        .andExpect(header(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {
                  "orderId": "ORDER-1001",
                  "amount": 250000,
                  "currency": "VND"
                }
                """))
        .andRespond(withStatus(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "chargeId": "CHARGE-9001",
                          "status": "ACCEPTED"
                        }
                        """));
~~~

This test verifies that the request has the right structure and provides a representative response for client code to process. After invoking the client, assert the returned result or corresponding side effect, then call `server.verify()`.

Avoid packing too many unrelated expectations into a single test. Each test should focus on one client behavior, such as creating a charge, retrying on transient errors, or handling an invalid response.

## 8. Expectations for Ordering and Call Counts

By default, `MockRestServiceServer` expects requests to occur in declaration order. When a client calls multiple endpoints in a meaningful sequence, default ordering catches out-of-order calls.

Example:

~~~java
server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess("{\"available\":12}",
                MediaType.APPLICATION_JSON));

server.expect(requestTo("https://inventory.example/api/reservations"))
        .andExpect(method(HttpMethod.POST))
        .andRespond(withSuccess());
~~~

If request order does not matter, you can configure the expectation manager to ignore ordering via the `ignoreExpectOrder(true)` option on the mock server builder. Use this only when requests are genuinely independent; if ordering is part of the business flow, keep the default check.

To check invocation counts, use `ExpectedCount`:

~~~java
server.expect(once(), requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));
~~~

Count types such as `once()`, `twice()`, `times(n)`, or `manyTimes()` specify how many times a request is allowed to occur. This is useful when testing retries, caching, or ensuring a request is not sent repeatedly by mistake.

For example, if a client must retry up to three times, declare the exact expected count matching the retry policy and responses for each attempt. Do not use `manyTimes()` if the test needs to catch excessive retries.

## 9. Providing Mock Responses and Checking Client Handling

`andRespond(...)` defines the response returned by the mock server. Some commonly used response creators:

~~~java
withSuccess("{\"status\":\"OK\"}", MediaType.APPLICATION_JSON);
withStatus(HttpStatus.NOT_FOUND);
withStatus(HttpStatus.SERVICE_UNAVAILABLE);
withServerError();
withNoContent();
~~~

Mock responses let you verify how the client handles both success and failure without depending on external services.

Example with a 404 response:

~~~java
server.expect(requestTo("https://inventory.example/api/items/MISSING"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withStatus(HttpStatus.NOT_FOUND));

assertThatThrownBy(() -> inventoryClient.findBySku("MISSING"))
        .isInstanceOf(RestClientResponseException.class);

server.verify();
~~~

If the client layer translates HTTP exceptions into its own domain exceptions, assert that domain exception. Tests should reflect the behavior seen by callers of `InventoryClient`, while expectations confirm that the request was sent properly.

## 10. Verifying Requests When the Client Is Managed by Spring

In an application, `RestClient` may be created from a configuration bean:

~~~java
@Configuration
class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example")
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

When testing a Spring-managed client, ensure the mock server is bound to the exact builder before `RestClient` is created. You can configure tests with their own builder and instantiate the client in the test fixture, or use an appropriate test context setup to supply the bound builder.

Do not create a builder bound to the mock server and then inject a `RestClient` built from another builder. Otherwise outbound requests from the real client bypass the mock server and the test may attempt to hit the real network.

With `RestTemplate`, the mechanism is similar:

~~~java
RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server =
        MockRestServiceServer.createServer(restTemplate);

server.expect(requestTo("https://inventory.example/api/items/COFFEE-01"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                "{\"sku\":\"COFFEE-01\"}",
                MediaType.APPLICATION_JSON));
~~~

`MockRestServiceServer.createServer(restTemplate)` replaces `RestTemplate`'s request factory so requests are handled inside the test. For `RestClient`, use builder binding as shown in the earlier examples.

## 11. Distinguishing RestClient/RestTemplate from WebClient

`MockRestServiceServer` is meant for synchronous clients based on `RestClient` and `RestTemplate`. `WebClient` is a reactive HTTP client with its own connector mechanism. When testing outbound requests sent by `WebClient`, a mock HTTP server such as MockWebServer or WireMock is typically used to inspect requests over the HTTP protocol.

| HTTP client | Typical request-testing tool |
|---|---|
| `RestClient` | `MockRestServiceServer.bindTo(RestClient.Builder)` |
| `RestTemplate` | `MockRestServiceServer.createServer(RestTemplate)` |
| `WebClient` | MockWebServer, WireMock, or HTTP-compatible test server |

Do not try to bind `MockRestServiceServer` to `WebClient`. Choosing the tool matching the client type keeps tests flowing through the right request abstraction and avoids incompatible configuration.

## 12. Checking Headers, Body, and URI Meaningfully

A few principles keep expectations both strict and maintainable:

- Check full host/path when routing to the right system is an important requirement.
- Check query parameters per key when query ordering has no meaning.
- Check the method for every request that has side effects or distinct semantics.
- Check `Content-Type` when sending a body and `Accept` when the client expects a specific representation.
- Check authentication or idempotency headers when they are part of the contract.
- Check important JSON fields without necessarily pinning every unrelated field.
- Check call counts when retry, caching, or duplicate prevention is required.
- Assert the response returned by the client layer rather than stopping once the request matches.

Overly strict matchers can break tests on changes that do not affect the contract, such as JSON property ordering. Overly loose matchers can miss real bugs, such as a missing `Authorization` header or sending the wrong amount. Choose the verification level according to the risk of each component.

## 13. Common Mistakes

| Symptom | Common cause | Solution |
|---|---|---|
| Test tries to call a real host | Client was not created from the builder/RestTemplate bound to the mock server | Bind the right builder before building the client |
| No requests are recorded | Code uses a different client instance than the one configured in the test | Check dependency injection and builder ownership |
| URI expectation does not match | Base URL, path, encoding, or query parameter differs from expected | Check full URI and use URI builder |
| Request has right path but test still fails | Method or header mismatch | Add dedicated matchers for method/header |
| JSON body differing only in whitespace fails test | String comparison instead of JSON structure comparison | Use `content().json(...)` if whitespace is not part of the contract |
| `verify()` reports unsatisfied expectations | Code never called client or logic branch did not execute | Verify the test triggered the right behavior |
| Request sent unexpectedly multiple times | Retries or duplicate call logic | Use `ExpectedCount` to lock down call count |
| Expectation order mismatch | Requests sent in a different order | Keep ordering if meaningful; if independent, configure ignore order |
| Using MockRestServiceServer for WebClient | Wrong HTTP client category | Use MockWebServer or WireMock |

## 14. Workflow for Writing an HTTP Client Test

When testing a client calling an external service, follow this sequence:

1. Create a `RestClient.Builder` or `RestTemplate` within the test scope.
2. Bind `MockRestServiceServer` to that builder/client before the code under test uses it.
3. Set expectations on URI, method, query parameters, headers, and body.
4. Declare a mock response with appropriate status, headers, and body.
5. Call the public method of the client class or integration service.
6. Assert the returned data or exception observed by callers.
7. Call `server.verify()` to confirm all expected requests occurred.

Tests should invoke the public method of the client class rather than manually constructing requests in the test identical to the implementation. If a test builds its own request, it only proves the matcher works, not that the application sends the right request.

`MockRestServiceServer` verifies the request contract at the `RestClient` or `RestTemplate` layer: URI, method, headers, and body. Combining meaningful expectations with mock responses and result assertions allows tests to catch endpoint configuration, serialization, authentication, and response-handling bugs without depending on external systems.
