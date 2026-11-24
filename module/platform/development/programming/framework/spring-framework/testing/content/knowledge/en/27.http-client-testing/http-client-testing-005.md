# Creating Success, Error, and Invalid Data Responses

When testing an HTTP client, checking only a `200 OK` response is not enough. A client must properly handle many outcomes from an external service: valid data, `4xx` business errors, `5xx` server errors, malformed response structures, data violating business rules, and cases where no response arrives due to connection failures.

These tests should drive responses from a mock HTTP server. The test sends requests through the application's real HTTP client, and the mock server returns a predefined status, headers, and body. That approach verifies URL, method, headers, serialization, deserialization, and error-handling policy in a single flow.

Spring provides `MockRestServiceServer` for `RestTemplate` and `RestClient`. For `WebClient`, you can use MockWebServer or WireMock to create a local HTTP server. Alternatively, you can mock `ExchangeFunction` directly, though that tests at a lower level and does not fully verify how the client produces HTTP requests over transport.

## 1. Categorizing Responses to Test

Suppose an application has an HTTP client to read inventory information from an Inventory service. A request can receive the following categories of outcomes:

| Scenario | Response or situation | What the client should do |
|---|---|---|
| Success | `200 OK` with valid JSON | Deserialize into the right DTO and return data to caller. |
| Created | `201 Created` with `Location` and body | Read newly created data and preserve needed metadata. |
| No content | `204 No Content` | Handle empty body according to the contract. |
| Invalid request | `400 Bad Request` with validation error | Convert to an input error or meaningful domain error. |
| Not found | `404 Not Found` | Convert to a not-found error or absent result per design. |
| Unauthorized / Forbidden | `401` or `403` | Report authentication/authorization failure, not treat as success. |
| Service failure | `500`, `502`, `503`, `504` | Raise upstream error and apply retry/fallback if policy permits. |
| Malformed JSON | `200 OK` but unparseable body | Report decode error, do not fabricate a dummy DTO or defaults. |
| Valid JSON but invalid business data | `200 OK` but missing required fields or out-of-range values | Reject invalid data before using it in business logic. |
| Transport error | DNS, connection refused, reset, or timeout | Handle connection errors separately from HTTP statuses. |

Each response should target a specific goal. For instance, `404` is not equivalent to `500`; malformed JSON inside a `200` response also differs from a `400` response reporting that the client's request was invalid.

## 2. Creating Mock Responses with MockRestServiceServer

`MockRestServiceServer` is a Spring Test tool for testing code using `RestTemplate` or `RestClient`. It attaches to the client's request factory, lets you declare request expectations, and returns mock responses without opening real HTTP ports.

Example DTO and inventory-reading client:

```java
public record InventoryItem(long id, String sku, int availableQuantity) {
}
```

With Spring Framework 6.1 and later, `MockRestServiceServer` can bind to `RestClient.Builder`:

```java
import org.springframework.web.client.RestClient;

class InventoryClient {

    private final RestClient restClient;

    InventoryClient(RestClient restClient) {
        this.restClient = restClient;
    }

    InventoryItem findById(long id) {
        return restClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryItem.class);
    }
}
```

Create the builder first, bind the mock server to the builder, and only then build the client:

```java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://inventory.example.test");

MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
RestClient restClient = builder.build();

InventoryClient inventoryClient = new InventoryClient(restClient);
```

Binding to the builder ensures `RestClient` requests pass through the request factory controlled by `MockRestServiceServer`. If you build the client first and later create a mock server from a different builder, the client will not automatically use that mock configuration.

## 3. Success Responses

The most basic scenario is the server returning `200 OK`, `Content-Type: application/json`, and JSON structured to match the DTO.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class InventoryClientTest {

    @Test
    void mapsSuccessfulJsonResponseToInventoryItem() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://inventory.example.test");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        InventoryClient client = new InventoryClient(builder.build());

        server.expect(requestTo("https://inventory.example.test/inventory/42"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("""
                        {
                          "id": 42,
                          "sku": "BOOK-42",
                          "availableQuantity": 12
                        }
                        """, MediaType.APPLICATION_JSON));

        InventoryItem item = client.findById(42);

        assertThat(item.id()).isEqualTo(42);
        assertThat(item.sku()).isEqualTo("BOOK-42");
        assertThat(item.availableQuantity()).isEqualTo(12);
        server.verify();
    }
}
```

The test verifies several things at once:

- The client calls the right URL and uses the right HTTP method.
- The `200` response is read as JSON.
- JSON fields map onto the right DTO properties.
- `server.verify()` confirms all request expectations were executed.

Do not merely assert that `item` is not `null`. Field-by-field assertions catch wrong property names, wrong data types, or incorrect mapping.

### Checking Request and Response Headers

If the client needs to send an API version or authorization header, you can add matchers:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header("Accept", MediaType.APPLICATION_JSON_VALUE))
        .andExpect(header("X-Client-Name", "order-service"))
        .andRespond(withSuccess("""
                {"id":42,"sku":"BOOK-42","availableQuantity":12}
                """, MediaType.APPLICATION_JSON));
```

If you need to check response headers such as `ETag` or `Location`, `MockRestServiceServer` provides response creators or builders that allow adding headers. What matters is checking the metadata the client actually uses, not just the body.

## 4. HTTP Error Responses

By default, `RestClient.retrieve()` converts `4xx` and `5xx` responses into exceptions under `RestClientResponseException`, unless code configures `onStatus(...)` to handle them specially. `RestTemplate` also has a default `ResponseErrorHandler` to convert error statuses into exceptions.

### Testing 404 Not Found

Example where the server returns `404` with a JSON body describing the error:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

import org.springframework.http.HttpStatus;

server.expect(requestTo("https://inventory.example.test/inventory/999"))
        .andRespond(withStatus(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"code":"ITEM_NOT_FOUND","message":"Item 999 does not exist"}
                        """));

assertThatThrownBy(() -> client.findById(999))
        .isInstanceOf(HttpClientErrorException.NotFound.class);

server.verify();
```

In a real test, `client` must be built from the builder bound to `server` as in the previous section. The exception assertion confirms the client does not treat an error response as a successful DTO.

If the application's convention is to convert `404` into `Optional.empty()` or `ItemNotFoundException`, test that convention instead of always expecting the default exception. For example, a client might declare:

```java
InventoryItem findById(long id) {
    return restClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    (request, response) -> {
                        throw new ItemNotFoundException(id);
                    })
            .body(InventoryItem.class);
}
```

Then the test should verify `ItemNotFoundException`, and may also inspect the id and cause details if the exception retains the response body.

### Testing 400 and Validation Errors

A `400 Bad Request` response typically indicates invalid request data. If the external API returns a stable error code, the client can convert that code into a domain error:

```json
{
  "code": "INVALID_QUANTITY",
  "message": "quantity must be greater than zero",
  "field": "quantity"
}
```

Tests must verify the status and how the client interprets the error body. If the client keeps `RestClientResponseException` as-is, you can check the status and response body in the exception. If the client converts it into a custom exception, check the extracted error code and field.

Do not assume every `400` carries valid JSON. A service may return an empty body, HTML from a gateway, or a different error schema. The client needs a clear policy when the error body cannot be parsed; tests should cover that case if the system might encounter it.

### Testing 5xx Errors

The server may return `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable`, or `504 Gateway Timeout`. You can construct these statuses with `withStatus(...)`:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"code":"INVENTORY_UNAVAILABLE"}
                        """));

assertThatThrownBy(() -> client.findById(42))
        .isInstanceOf(HttpServerErrorException.ServiceUnavailable.class);
```

If the client has retries, do not assert only the final exception. Verify the invocation count, backoff interval, or that the final request succeeded after a number of failures. When there is no retry policy, a `503` response should typically propagate as a clear error for higher layers to decide.

## 5. Success Status with Malformed JSON

An important case is when the server returns `200 OK` yet the body cannot be deserialized into the DTO. This is a response data error, not an HTTP status error.

Example of truncated JSON:

```json
{"id":42,"sku":"BOOK-42",
```

Test with `MockRestServiceServer`:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withSuccess(
                "{\"id\":42,\"sku\":\"BOOK-42\",",
                MediaType.APPLICATION_JSON));

assertThatThrownBy(() -> client.findById(42))
        .isInstanceOf(RestClientException.class);

server.verify();
```

`RestClient` uses `HttpMessageConverter` to read the body. When JSON is invalid or cannot be converted into the DTO, the client typically throws a `RestClientException` wrapping the underlying decode cause. If application code wraps the exception into a domain error, assert the exception type and cause according to the client class's contract.

Do not catch all exceptions and return an empty DTO or default values. Doing so makes corrupted data look like success and can lead to hard-to-trace business bugs.

## 6. Valid JSON That Is Business-Invalid

Not every bad payload is syntactically invalid JSON. For example, the following body parses cleanly:

```json
{
  "id": 42,
  "sku": "BOOK-42",
  "availableQuantity": -5
}
```

However, a negative available quantity may violate the service contract. Successful deserialization does not mean the data is trustworthy. The HTTP client or adapter layer should validate invariants that the application relies on.

Example of a client checking data after reading it:

```java
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    InventoryItem findById(long id) {
        InventoryItem item = restClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .body(InventoryItem.class);

        if (item == null || item.id() <= 0 || item.availableQuantity() < 0) {
            throw new InvalidInventoryResponseException(
                    "Inventory service returned invalid item data");
        }

        return item;
    }
}
```

Test producing a `200` response containing a negative value:

```java
server.expect(requestTo("https://inventory.example.test/inventory/42"))
        .andRespond(withSuccess("""
                {
                  "id": 42,
                  "sku": "BOOK-42",
                  "availableQuantity": -5
                }
                """, MediaType.APPLICATION_JSON));

assertThatThrownBy(() -> gateway.findById(42))
        .isInstanceOf(InvalidInventoryResponseException.class);
```

Invariants should be chosen from the actual contract: id must be positive, required fields must not be null, quantities must be non-negative, currency codes valid, or statuses within the allowed set. Avoid inventing business rules that do not exist in the service contract.

### Distinguishing Missing, Null, and Wrong-Type Data

The following three payloads can produce three different behaviors:

```json
{"id":42,"sku":"BOOK-42","availableQuantity":12}
```

```json
{"id":42,"sku":"BOOK-42"}
```

```json
{"id":"not-a-number","sku":"BOOK-42","availableQuantity":"many"}
```

The first payload is complete. The second payload omits a field; the result may be `null`, a default value, or an error depending on the DTO and Jackson configuration. The third payload has wrong data types and typically causes a decode error. If a required field must be present, check it after deserialization or configure mapping to detect missing fields. Do not rely on primitive defaults such as `0` to infer that the server actually sent that field.

## 7. Using MockWebServer to Test WebClient

`MockRestServiceServer` targets the synchronous `RestTemplate`/`RestClient` APIs. `WebClient` uses a reactive HTTP connector and does not use `ClientHttpRequestFactory` in the same way. A practical choice is OkHttp's MockWebServer: it opens a local server, receives real HTTP requests, and returns test-queued responses.

Add the test dependency matching the OkHttp version managed by the project:

```groovy
testImplementation 'com.squareup.okhttp3:mockwebserver'
```

Example reactive client:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveInventoryClient {

    private final WebClient webClient;

    ReactiveInventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<InventoryItem> findById(long id) {
        return webClient.get()
                .uri("/inventory/{id}", id)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
```

### Success Responses via WebClient

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.test.StepVerifier;

class ReactiveInventoryClientTest {

    @Test
    void readsSuccessfulResponseAndSendsExpectedRequest() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader("Content-Type", "application/json")
                    .setBody("""
                            {"id":42,"sku":"BOOK-42","availableQuantity":12}
                            """));
            server.start();

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .build();
            ReactiveInventoryClient client = new ReactiveInventoryClient(webClient);

            StepVerifier.create(client.findById(42))
                    .assertNext(item -> {
                        assertThat(item.id()).isEqualTo(42);
                        assertThat(item.sku()).isEqualTo("BOOK-42");
                        assertThat(item.availableQuantity()).isEqualTo(12);
                    })
                    .verifyComplete();

            RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/inventory/42");
        }
    }
}
```

MockWebServer receives requests over local HTTP, so tests can check the method, path, query, headers, and body actually sent. `StepVerifier` verifies the reactive outcome without calling `block()` in the test.

### Error Responses via WebClient

By default, `retrieve()` turns `4xx` or `5xx` responses into `WebClientResponseException`. You can verify the status and error body:

```java
server.enqueue(new MockResponse()
        .setResponseCode(404)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"code":"ITEM_NOT_FOUND"}
                """));

StepVerifier.create(client.findById(999))
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(WebClientResponseException.NotFound.class);
            WebClientResponseException responseError =
                    (WebClientResponseException) error;
            assertThat(responseError.getStatusCode().value()).isEqualTo(404);
            assertThat(responseError.getResponseBodyAsString())
                    .contains("ITEM_NOT_FOUND");
        })
        .verify(Duration.ofSeconds(2));
```

If the client uses `onStatus(...)` to map errors into custom exceptions, tests should verify that custom exception. Example:

```java
Mono<InventoryItem> findById(long id) {
    return webClient.get()
            .uri("/inventory/{id}", id)
            .retrieve()
            .onStatus(status -> status.value() == 404,
                    response -> Mono.error(new ItemNotFoundException(id)))
            .bodyToMono(InventoryItem.class);
}
```

`onStatus` takes a predicate and a function converting the response into `Mono<? extends Throwable>`. Translating errors at the adapter keeps business layers from depending on HTTP details when that matches the application's architectural boundary.

### Malformed JSON via WebClient

MockWebServer can also return `200` with invalid JSON:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"id\":42,"));

StepVerifier.create(client.findById(42))
        .expectError()
        .verify(Duration.ofSeconds(2));
```

In a concrete test, replace `expectError()` with an assertion for the decode exception type or the domain exception the application commits to raising. With WebClient, decoding failures are often `DecodingException` or an exception wrapped inside a reactive error; the exact type depends on the codec and version. If the exception type is part of the client's public contract, verify it and its cause explicitly.

## 8. Invalid Request Data and 400 Responses

HTTP clients also need to send contract-compliant data. For instance, a client builds a JSON request with `quantity` equal to `0`, and the service rejects it with `400 Bad Request`.

With `RestClient`, tests can verify the sent body and the error response:

```java
server.expect(requestTo("https://orders.example.test/orders"))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().contentType(MediaType.APPLICATION_JSON))
        .andExpect(content().json("""
                {"sku":"BOOK-42","quantity":0}
                """))
        .andRespond(withStatus(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {
                          "code":"INVALID_QUANTITY",
                          "field":"quantity"
                        }
                        """));
```

Tests should verify that the client does not silently ignore validation errors from the server. If the application validates requests before making HTTP calls, separate unit tests are needed to prove invalid requests are blocked client-side and no outbound request is sent. These two behaviors differ:

- Client sends request and server returns `400`: verifies how the client handles the error response.
- Client rejects data before sending request: verifies application-side validation and ensures zero HTTP requests.

## 9. Testing Transport Errors and Timeouts

HTTP errors are responses with a status code. Transport errors occur when no valid response is received, such as a server not listening, connection reset, DNS failure, or timeout. Do not lump these two categories into the same handling branch if the application needs different retry behavior.

With WebClient, timeouts can be tested using a mock server that delays its response:

```java
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("{\"id\":42}")
        .setBodyDelay(2, TimeUnit.SECONDS));

StepVerifier.create(client.findById(42).timeout(Duration.ofMillis(200)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
```

This is a timeout applied in the test/client Reactor pipeline. If the application configures timeouts on the HTTP connector, verify that configuration through the real client and assert the transport-generated exception. Do not just add `Mono.timeout(...)` in a test and conclude the connector timeout is configured.

For connection failures, you can shut down MockWebServer before sending the request or point the client to an unused port, though such tests can be environment-sensitive. Prefer a mock server that can actively close connections or a controlled connector test fixture. Either way, assertions must confirm the client emits a transport error and does not return a successful result.

## 10. Testing Retries and Fallbacks

If a client has a retry policy, the mock server can queue multiple responses in order. For example, returning `503` first and `200` on the next attempt:

```java
server.enqueue(new MockResponse().setResponseCode(503));
server.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("""
                {"id":42,"sku":"BOOK-42","availableQuantity":12}
                """));
```

After calling the retrying client, the test must verify both the final result and the actual request count:

```java
StepVerifier.create(client.findById(42))
        .expectNextMatches(item -> item.id() == 42)
        .verifyComplete();

assertThat(server.getRequestCount()).isEqualTo(2);
```

Only use this pattern when retrying is genuinely the client's policy. Do not automatically retry all `4xx` errors: `400`, `401`, `403`, or `404` generally will not succeed by resending the same request. For `503` or transient transport errors, retrying can make sense, provided attempt counts, backoff, and idempotency are bounded.

If the client uses a fallback, tests should verify the fallback runs only for the designated error group. For instance, `503` may return cached data, whereas `404` must preserve its not-found meaning. A catch-all fallback for every exception easily hides data bugs or programming errors.

## 11. Resetting and Verifying the Mock Server

Each test should have its own expectations and verify they were consumed. With `MockRestServiceServer`, call `verify()` after the client finishes. If reusing the same server across tests, reset expectations between tests using the appropriate API or create a fresh fixture per test.

With MockWebServer, enqueue responses before the request, then read `RecordedRequest` to inspect what arrived. Use a timeout when taking requests to avoid waiting forever. Always stop the server in `finally` or use `try-with-resources` if the library version supports `AutoCloseable`.

Do not let parallel tests share one MockWebServer if they enqueue responses and read requests from the same queue. Each test should have its own server or explicit synchronization; otherwise responses can be consumed by another test.

## 12. Common Mistakes When Crafting Mock Responses

### Returning Only a Status Without `Content-Type`

The client may select codecs based on response headers. If the test wants to verify JSON decoding, set `Content-Type: application/json`. If intentionally testing a server omitting that header, treat it as a separate scenario.

### Using a Response Body That Does Not Match the DTO

A payload may deserialize while important fields end up `null` or default values. Assert individual fields and check invariants after deserialization rather than merely asserting the object exists.

### Confusing HTTP Errors with Decode Errors

`404` is a valid HTTP response reporting that a resource does not exist. `200` with malformed JSON is a successful status whose data cannot be read. A client may need two distinct exception types and retry policies.

### Failing to Verify the Outbound Request

A test that only enqueues a response and asserts returned data can miss the client calling the wrong method or path. With `MockRestServiceServer`, declare request expectations; with MockWebServer, inspect `RecordedRequest`.

### Using Mock Objects Instead of HTTP Responses When Testing Serialization

Mock services or mock `ExchangeFunction` can be handy for small unit tests, yet they can skip request encoding, headers, and transport. If the goal is checking that the client sends and receives HTTP properly, use a mock HTTP server.

### Retries Making Tests Slow or Flaky

Retries with real delays can stretch test duration. Configure short test backoff or use a controllable scheduler if the retry logic supports it. Do not use `Thread.sleep` to wait for retries; observe request counts and outcomes using proper synchronization mechanisms.

## 13. Choosing Tools by HTTP Client

| Client in application | Tool for creating mock responses | Primary scope |
|---|---|---|
| `RestTemplate` | `MockRestServiceServer.bindTo(restTemplate)` | Request expectations and mock responses at the request factory. |
| `RestClient` (Spring Framework 6.1+) | `MockRestServiceServer.bindTo(builder)` | Testing Spring's newer synchronous API via a mock request factory. |
| `WebClient` | MockWebServer or WireMock | Local HTTP server verifying requests/responses through the connector. |
| Narrow `WebClient` unit test | Mock `ExchangeFunction` | Testing response-mapping logic without verifying HTTP transport. |

Choose tools based on the client used by the application and the behavior requiring verification. For `RestClient`/`RestTemplate`, `MockRestServiceServer` integrates directly with Spring Test. For `WebClient`, MockWebServer produces real HTTP responses over a local port and enables checking sent requests.

## 14. Checklist for Success, Error, and Invalid Data Responses

- [ ] Include success responses with status, content type, and valid JSON.
- [ ] Assert each important DTO field after deserialization.
- [ ] Test contract error statuses such as `400`, `401`, `403`, `404`, and `5xx` where needed.
- [ ] Verify the client converts error statuses into domain exceptions or results per design.
- [ ] Test `200 OK` with syntactically invalid JSON.
- [ ] Test valid JSON missing required fields or containing values violating invariants.
- [ ] Distinguish HTTP response errors, decode errors, and transport errors.
- [ ] Verify outbound request method, URI, headers, and body.
- [ ] If retries/fallbacks exist, verify invocation counts and which error groups trigger retries.
- [ ] Reset/shut down the mock server and verify expectations after each test.

Crafting mock success, error, and invalid data responses tests HTTP clients at the exact integration boundary. Verify both the outbound request and the interpreted response, distinguish error statuses from malformed payloads, and ensure the client never turns untrustworthy data into a successful outcome. When retries, fallbacks, or timeouts exist, test them as explicit policies with clear bounds and conditions.
