# Binding the Mock Server to the Exact Client or Builder Used by the Application

When a service calls another system over HTTP, tests need to verify the request the client actually sends and how the application handles the returned response. Spring Test provides `MockRestServiceServer` for `RestTemplate` and `RestClient`; for `WebClient`, you can use a locally running mock HTTP server such as OkHttp `MockWebServer` or WireMock.

The decisive point is that the mock server must be bound to the exact client or builder used by the component. If the test creates a separate client to bind the mock server while the service uses a different client, the service's requests will not pass through that mock. The test may fail because it sees no requests, or it may accidentally call a real endpoint.

## 1. Identifying Which Client the Component Uses

Spring offers multiple HTTP clients with different request-sending mechanisms:

| HTTP client | Request-sending mechanism | Suitable testing tool |
|---|---|---|
| `RestTemplate` | Synchronous `ClientHttpRequestFactory` | `MockRestServiceServer` bound directly to the `RestTemplate` instance |
| `RestClient` | Synchronous fluent API, backed by a request factory | `MockRestServiceServer` bound to `RestClient.Builder` before building the client |
| `WebClient` | Reactive `ClientHttpConnector` | Local mock HTTP server such as `MockWebServer` or WireMock |

`MockRestServiceServer` replaces the request-sending layer of `RestTemplate` or `RestClient` to record requests and return mock responses in the same process. It does not open an HTTP port. `MockWebServer` and WireMock start a local HTTP server on an assigned port, so the client sends requests through the real HTTP stack.

This is **outbound HTTP client** testing: our application is the side sending requests to another service. For testing **inbound HTTP endpoints** where the application receives requests, use `MockMvc` for Spring MVC or `WebTestClient` for WebFlux. These two goals sit on opposite sides of the connection.

## 2. Binding MockRestServiceServer to RestTemplate

For `RestTemplate`, create or obtain the exact instance used by the component and bind the mock server to that instance. For example:

```java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

RestTemplate restTemplate = new RestTemplate();
MockRestServiceServer server = MockRestServiceServer
    .bindTo(restTemplate)
    .build();
```

Once bound, requests sent through this `restTemplate` are controlled by the mock server. The test declares expected requests and mock responses:

```java
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

server.expect(requestTo("https://inventory.example/api/items/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """
        {"id":"42","name":"Book"}
        """,
        MediaType.APPLICATION_JSON
    ));
```

Example component using this exact `RestTemplate`:

```java
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

record Item(String id, String name) {
}

class RestTemplateCatalogClient {

    private final RestTemplate restTemplate;

    RestTemplateCatalogClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    Item findById(String id) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Client", "catalog");

        ResponseEntity<Item> response = restTemplate.exchange(
            "https://inventory.example/api/items/{id}",
            HttpMethod.GET,
            new HttpEntity<>(headers),
            Item.class,
            id
        );
        return response.getBody();
    }
}
```

After invoking the component that uses `restTemplate`, assert the business result and verify all expectations were met:

```java
import static org.assertj.core.api.Assertions.assertThat;

RestTemplateCatalogClient catalogClient =
    new RestTemplateCatalogClient(restTemplate);
Item item = catalogClient.findById("42");

assertThat(item.id()).isEqualTo("42");
assertThat(item.name()).isEqualTo("Book");
server.verify();
```

`expect(...)` describes the request the test expects to receive, `andExpect(...)` checks the request's method, URL, headers, or body, and `andRespond(...)` supplies the mock response. `verify()` confirms that the expected requests were actually sent.

In Spring Test, `MockRestServiceServer.createServer(restTemplate)` is also a way to create a server bound to an existing `RestTemplate`. Whether using `bindTo(...).build()` or `createServer(...)`, what matters is binding to the instance that the component actually uses.

## 3. Binding MockRestServiceServer to RestClient.Builder

`RestClient` was introduced in Spring Framework 6.1. Unlike `RestTemplate`, the API is typically built from `RestClient.Builder`. To mock `RestClient` requests, bind `MockRestServiceServer` to the builder before calling `build()`:

```java
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
    .bindTo(builder)
    .build();

RestClient restClient = builder.build();
```

This order matters: the mock server configures the request factory on the builder, and then `RestClient` is created from that configured builder. If you create `RestClient` from a different builder, requests from that client will not be recorded by this mock server.

Example of a component using `RestClient`:

```java
import org.springframework.web.client.RestClient;

class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder) {
        this.restClient = builder
            .baseUrl("https://inventory.example")
            .build();
    }

    Item findById(String id) {
        return restClient.get()
            .uri("/api/items/{id}", id)
            .header("X-Client", "catalog")
            .retrieve()
            .body(Item.class);
    }
}
```

The test creates the client from the builder bound to the mock server, passes that client into the component, and declares expectations:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

RestClient.Builder builder = RestClient.builder()
    .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
    .bindTo(builder)
    .build();

CatalogClient catalogClient = new CatalogClient(builder);

server.expect(requestTo("https://inventory.example/api/items/42"))
    .andExpect(method(HttpMethod.GET))
    .andExpect(header("X-Client", "catalog"))
    .andRespond(withSuccess(
        """{"id":"42","name":"Book"}""",
        MediaType.APPLICATION_JSON
    ));

Item item = catalogClient.findById("42");

assertThat(item.name()).isEqualTo("Book");
server.verify();
```

Here the component receives the exact `RestClient` built from the bound builder. This is the link that must be preserved in tests and in how the application organizes factories.

## 4. Using the Spring Boot Test Slice for REST Clients

In Spring Boot, `@RestClientTest` can create a test slice for components calling REST services. This annotation limits the application context to REST-client-related components and configures testing infrastructure; supported Boot versions provide a `MockRestServiceServer` for tests to declare expectations.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
class CatalogClientTests {

    @Autowired
    private CatalogClient catalogClient;

    @Autowired
    private MockRestServiceServer server;

    @Test
    void readsItemFromInventoryService() {
        server.expect(requestTo("https://inventory.example/api/items/42"))
            .andRespond(withSuccess(
                """{"id":"42","name":"Book"}""",
                org.springframework.http.MediaType.APPLICATION_JSON
            ));

        Item item = catalogClient.findById("42");

        assertThat(item.name()).isEqualTo("Book");
        server.verify();
    }
}
```

`@RestClientTest` is useful when a component receives `RestTemplateBuilder` or `RestClient.Builder` from Spring Boot configuration. Let the component use the Spring-managed builder so the test slice can bind the mock server into that exact infrastructure. If the component creates `new RestTemplate()` or `RestClient.builder()` internally, the builder configured by the test slice may not be the builder the component uses; in that case, refactor to inject the factory/builder or create the mock server manually with the exact instance.

Auto-configuration support for `RestClient` depends on the Spring Boot version. On older versions, check the documentation for the version in use; you may need to create `RestClient.Builder`, bind the mock server, and pass the client into the component as in the example above.

## 5. Why Does WebClient Need Its Own Mock HTTP Server?

`WebClient` uses a reactive `ClientHttpConnector` to send requests. `MockRestServiceServer` is designed to bind to the request factory of `RestTemplate` and `RestClient.Builder`; it is not an adapter that replaces `WebClient`'s connector.

With `WebClient`, the practical approach is to start a local HTTP server on a random port, point the client's base URL to that server, enqueue mock responses, and inspect the requests the server received. OkHttp's `MockWebServer` is a common choice.

Add the test dependency, picking a version compatible with the OkHttp version used by the project:

```groovy
dependencies {
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
```

Example of testing a `WebClient`:

```java
import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveCatalogClientTests {

    @Test
    void sendsRequestToInventoryAndReadsResponse() throws IOException, InterruptedException {
        MockWebServer server = new MockWebServer();
        server.start();

        try {
            server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""{"id":"42","name":"Book"}"""));

            WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

            ReactiveCatalogClient catalogClient =
                new ReactiveCatalogClient(webClient);

            StepVerifier.create(catalogClient.findById("42"))
                .assertNext(item -> {
                    assertThat(item.id()).isEqualTo("42");
                    assertThat(item.name()).isEqualTo("Book");
                })
                .verifyComplete();

            RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/api/items/42");
        }
        finally {
            server.shutdown();
        }
    }
}
```

In the example, `ReactiveCatalogClient` is the application component using `WebClient`; the test builds a `WebClient` with the mock server's base URL and passes that exact instance into the component. After the publisher completes, the test reads `RecordedRequest` to verify the method and path the server actually received.

Example component:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class ReactiveCatalogClient {

    private final WebClient webClient;

    ReactiveCatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<Item> findById(String id) {
        return webClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(Item.class);
    }
}
```

`MockWebServer` receives requests over real HTTP on the loopback interface, so it verifies the URL, method, headers, and body sent. Still, the test runs against a local server in the test process without depending on external services.

## 6. Checking Request Body, Headers, and Error Responses

The mock server should verify the client's HTTP contract, not just return a fixed response. With `MockRestServiceServer`, you can add matchers for headers, body, query parameters, and method:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;

server.expect(requestTo("https://payments.example/charges"))
    .andExpect(method(HttpMethod.POST))
    .andExpect(header("Authorization", "Bearer test-token"))
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(content().json("""{"orderId":"ORD-42","amount":250000}"""))
    .andRespond(withSuccess("""{"chargeId":"CH-1"}""", MediaType.APPLICATION_JSON));
```

Corresponding static matchers live in `MockRestRequestMatchers`, while response creators live in `MockRestResponseCreators`. Tests can simulate successful responses, HTTP errors, or empty responses to verify how the component handles them.

With `MockWebServer`, use `RecordedRequest` to inspect the received data:

```java
RecordedRequest request = server.takeRequest(1, TimeUnit.SECONDS);
assertThat(request).isNotNull();
assertThat(request.getHeader("Authorization")).isEqualTo("Bearer test-token");
assertThat(request.getBody().readUtf8())
    .contains("\"orderId\":\"ORD-42\"");
```

To test errors, enqueue a response with status 503 or 404 and assert the exception or error result returned by the client. With `RestClient`, `retrieve()` typically throws `RestClientResponseException` for error statuses unless a custom status handler is configured. With `WebClient`, `retrieve()` typically emits `WebClientResponseException` in the reactive publisher; use `StepVerifier` to assert the error type or status.

## 7. Controlling Call Counts and Request Ordering

A component may call a service once, call again on retry, or send multiple requests in one operation. `MockRestServiceServer` lets you declare expected counts using `ExpectedCount`:

```java
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;

server.expect(ExpectedCount.once(), requestTo("https://inventory.example/api/items/42"))
    .andRespond(withSuccess("""{"id":"42"}""", MediaType.APPLICATION_JSON));
```

Common options include `once()`, `never()`, `times(n)`, `min(n)`, and `max(n)`. Use expected counts to catch over-calling, missing calls, or retries violating policy.

By default, `MockRestServiceServer` expectations are verified in declaration order. If requests are independent and order is not part of the contract under test, the builder can be configured with `ignoreExpectOrder(true)`. Only disable order checking when the application truly does not depend on call order.

`MockWebServer` serves queued responses in the order requests arrive. When verifying multiple requests, read each `RecordedRequest` in order or use `takeRequest(timeout, unit)` to avoid waiting indefinitely. For retries, enqueue error/success responses according to the scenario and verify the total number of requests received.

## 8. Mock Server Lifecycle in Tests

The mock server must be set up before the component sends requests and verified after the operation finishes:

```text
Create client / builder
        |
        v
Bind mock server to the right client or builder
        |
        v
Create component using that client
        |
        v
Declare request expectations or enqueue responses
        |
        v
Invoke business method
        |
        v
Assert business result and sent requests
        |
        v
verify() / read RecordedRequest
        |
        v
Shut down local mock server if needed
```

With `MockRestServiceServer`, call `verify()` after the component has executed requests. If reusing the server across multiple tests, reset expectations using the test setup mechanism so each test has an independent scenario. Avoid sharing a mutable instance across tests running in parallel.

With `MockWebServer`, always stop the server in `finally` or a lifecycle callback such as `@AfterEach`. Do not leave the server holding ports and threads after the test finishes. Use the random port assigned by `server.start()`, rather than hard-coding a port prone to CI collisions.

## 9. Choosing the Right Tool and Scope

| Goal | Tool |
|---|---|
| Verify `RestTemplate` sends the right request | `MockRestServiceServer` bound to the right `RestTemplate` |
| Verify `RestClient` sends the right request | `MockRestServiceServer` bound to `RestClient.Builder` before `build()` |
| Verify `WebClient` sends real HTTP requests | `MockWebServer` or WireMock with base URL pointing to local server |
| Test Spring MVC controller receiving requests | `MockMvc` |
| Test WebFlux controller receiving requests | `WebTestClient` |
| Test full integration through a running application server | HTTP client calling a real server in an integration test |

Do not use `MockMvc` or `WebTestClient.bindToController(...)` to assert that a component called an external service properly. Those tools test the server side receiving requests. Conversely, `MockRestServiceServer` and `MockWebServer` test the client side of the application issuing outbound requests.

## 10. Common Mistakes When Binding a Mock Server

| Symptom | Cause to check |
|---|---|
| `MockRestServiceServer.verify()` reports missing requests | Component was not called, URI/method mismatched, or component uses a different client instance than the bound one |
| Test still calls the real endpoint | Mock server was bound to a different `RestTemplate`/builder; check where the client is created and injected |
| `RestClient` bypasses the mock server | Client was built before binding or created from a different builder |
| `MockRestServiceServer` does not support `WebClient` | `WebClient` uses `ClientHttpConnector`; use a mock HTTP server such as `MockWebServer` or WireMock |
| `WebClient` cannot reach mock server | Base URL does not point to `server.url(...)`, server not started, or already shut down before the request |
| Request matcher fails | Check full URL, query string, method, headers, and actual body |
| Retry test sends a different number of requests than expected | Verify retry policy, backoff, and error responses queued in the mock server |
| Test hangs reading request from MockWebServer | No request was sent or waiting indefinitely; use `takeRequest(timeout, unit)` and check the call flow |

When debugging, start from the component making outbound calls: identify which field or constructor receives the HTTP client, which builder created the client, and trace that exact instance to where the mock server is bound. Only then inspect expectations, responses, and business results.

## 11. Outbound HTTP Test Setup Workflow

1. Identify whether the component uses `RestTemplate`, `RestClient`, or `WebClient`.
2. For `RestTemplate`, bind `MockRestServiceServer` to the exact instance; for `RestClient`, bind to the builder before building the client.
3. For `WebClient`, start a local mock HTTP server and create the client with the server's base URL.
4. Pass the configured client into the component under test.
5. Declare expected requests or enqueue mock responses before invoking the component.
6. Call the business method, check the returned result, and verify method, URL, headers, body, and call count.
7. Verify the mock server and release resources in the test lifecycle.

A reliable outbound HTTP test must prove that the component used the exact client bound to the mock server, sent the right request, and handled the response as expected. By choosing the tool matching the client type and keeping the same instance or builder between the test and the component, the test will not leak real outbound requests or accidentally verify the wrong client.
