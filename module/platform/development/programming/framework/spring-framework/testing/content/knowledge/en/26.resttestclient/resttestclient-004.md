# Binding to a Real Server for End-to-End Testing

## 1. Purpose of RestTestClient When Binding to a Server

A controller test can invoke handlers directly or use mock web infrastructure. That approach is useful for testing mapping, validation, serialization, and HTTP logic within Spring. However, it does not pass through an HTTP connector listening on a network port.

When you need to verify that the application works over real HTTP, you can use **RestTestClient.bindToServer()** to create a client that sends requests to a running server. The server can be an embedded server started by Spring Boot in a test, a standalone running application, or a deployed test environment.

Test flow when binding to a real server:

~~~text
JUnit test
   |
   | RestTestClient.bindToServer()
   v
HTTP client
   |
   | TCP + HTTP request
   v
Embedded servlet/reactive server
   |
   v
Filters / Security / Dispatcher / Controller
   |
   v
Service / Repository / Database
   |
   | HTTP response
   v
RestTestClient assertions
~~~

The test passes through the server's connector and HTTP stack. Therefore, it can verify multiple components working together: server startup, port, routing, filters, security, message converters, serialization, services, and persistence.

**RestTestClient** provides a fluent API to send requests and inspect responses. With server binding, requests are sent over real HTTP instead of being dispatched directly within a mock application context.

## 2. Spring Versions with RestTestClient

**RestTestClient** was introduced in Spring Framework 7.0. It belongs to a newer Spring line than projects still using Spring Framework 6.x. If a project does not have this class yet, check dependency versions before writing tests; adding an import in source code will not make the API appear if the dependency does not support it yet.

For Spring Boot projects using the Spring Framework 7.0 line, RestTestClient can be used. For applications on older versions, common options are:

- **TestRestTemplate** for Spring Boot integration tests over real HTTP, especially with Spring MVC applications.
- **WebTestClient.bindToServer()** for WebFlux endpoints or when the corresponding test client API is needed.
- **RestClient** combined with custom assertions if you want to build HTTP checks yourself.

Do not confuse **RestTestClient** with **MockRestServiceServer**. MockRestServiceServer is typically used to test a REST client created by the application by mocking the server that the client calls. In this article, RestTestClient acts as the HTTP client calling into the server of the application under test itself.

## 3. Starting a Real Server in Spring Boot

For end-to-end tests, let Spring Boot start the embedded server on a random port:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiHttpTest {
}
~~~

**RANDOM_PORT** instructs Spring Boot to start a real web server and pick an available port. This avoids depending on a fixed port and allows multiple test suites to run on the same machine with fewer conflicts.

You can obtain the assigned port using **@LocalServerPort**:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;

@LocalServerPort
private int port;
~~~

Do not use **webEnvironment = MOCK** if the goal is to test the HTTP connector. MOCK mode builds a web application context for tests without starting a server accepting TCP connections. **DEFINED_PORT** can also start a real server, but requires a preconfigured port and is prone to conflicts if another process is using that port.

### Creating RestTestClient with bindToServer()

After the server starts, create a client pointing to the server's address and port:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.RestTestClient;

RestTestClient client = RestTestClient
        .bindToServer()
        .baseUrl("http://localhost:" + port)
        .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
        )
        .build();
~~~

**bindToServer()** configures the client to use an HTTP connection to a running server. **baseUrl(...)** sets the base address; subsequent requests can use relative URIs such as **/api/orders/42**. **defaultHeader(...)** sets default headers for the client's requests.

You can set shared configuration such as base URL, default headers, converters, or timeouts before calling **build()**. Then reuse the client across multiple requests within the same test class if those settings do not change.

## 4. A Complete End-to-End Test

Suppose the application has an endpoint to read an order:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable Long id) {
        return orderService.findById(id);
    }
}
~~~

Returned DTO:

~~~java
public record OrderResponse(
        Long id,
        String orderNumber,
        String status
) {
}
~~~

The test uses a repository to create data, then sends a request over real HTTP:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.RestTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class OrderApiHttpTest {

    @LocalServerPort
    private int port;

    @Autowired
    private OrderRepository orderRepository;

    private RestTestClient client;
    private Long orderId;

    @BeforeEach
    void setUp() {
        client = RestTestClient
                .bindToServer()
                .baseUrl("http://localhost:" + port)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE
                )
                .build();

        Order saved = orderRepository.save(
                new Order("E2E-" + java.util.UUID.randomUUID(), "PAID")
        );
        orderId = saved.getId();
    }

    @AfterEach
    void cleanUp() {
        if (orderId != null) {
            orderRepository.deleteById(orderId);
        }
    }

    @Test
    void shouldReadAnOrderThroughRealHttp() {
        client.get()
                .uri("/api/orders/{id}", orderId)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                )
                .expectBody(OrderResponse.class)
                .isEqualTo(new OrderResponse(
                        orderId,
                        orderRepository.findById(orderId)
                                .orElseThrow()
                                .getOrderNumber(),
                        "PAID"
                ));
    }
}
~~~

In the example, the constructor of **Order**, the id type, and the repository are illustrative models; replace them with your application's actual entities and persistence APIs.

The important point is that the request travels through the embedded server's HTTP address and port. The test does not call **OrderController** or **OrderService** directly. Spring must receive the request, route to the controller, call the service, read data, and serialize the response before RestTestClient receives the result.

The **@AfterEach** block deletes only the record created by the test. Do not use a fixed ID shared across runs, and do not delete the entire table if other tests may be using the same database.

## 5. Checking Status, Headers, and Body

An HTTP integration test should verify all three parts of the response.

### HTTP Status

Status represents the processing outcome at the protocol level:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectStatus().isOk();
~~~

You can check specific statuses such as **isCreated()**, **isNoContent()**, **isBadRequest()**, **isUnauthorized()**, or **isNotFound()**. Choose the status according to the endpoint contract.

### Response Headers

Headers verify the metadata the client actually receives:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON);
~~~

Other headers can be checked:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectHeader()
        .exists(HttpHeaders.CACHE_CONTROL);
~~~

For endpoints that create resources, you can check **Location** if the API returns that header. For file download endpoints, verify content type and content disposition. For cached endpoints, verify cache control or ETag.

### Response Body

When you want to verify JSON as a DTO:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectBody(OrderResponse.class)
        .isEqualTo(expected);
~~~

When you want to verify the JSON structure directly:

~~~java
client.get()
        .uri("/api/orders/{id}", orderId)
        .exchange()
        .expectBody()
        .json("""
                {
                  "id": 42,
                  "orderNumber": "E2E-42",
                  "status": "PAID"
                }
                """);
~~~

Structural JSON comparison keeps tests independent of property order or whitespace. When an API contract explicitly specifies that a property is omitted, has a null value, or must have a specific JSON type, verify that exact distinction.

## 6. Testing a Create-Then-Read Resource Flow Over HTTP

An end-to-end test can verify multiple endpoints in a business flow. For example, a client creates an order and then reads back the newly created order.

~~~java
@Test
void shouldCreateAndThenReadAnOrder() {
    CreateOrderRequest request = new CreateOrderRequest(
            "E2E-" + java.util.UUID.randomUUID(),
            "PENDING"
    );

    OrderResponse created = client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .body(request)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .expectBody(OrderResponse.class)
            .returnResult()
            .getResponseBody();

    assertThat(created).isNotNull();

    client.get()
            .uri("/api/orders/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(OrderResponse.class)
            .isEqualTo(created);
}
~~~

This test verifies an interaction sequence performed by a client:

1. Send a JSON request to the order creation endpoint.
2. The server binds the request body into a DTO.
3. The controller and service create the data.
4. The server returns status **201 Created**, the **Location** header, and the response DTO.
5. The client uses the id from the response to call the read endpoint.
6. The server queries the data and returns the created order.

Resources created by the test must be cleaned up after completion. You can take the id from the response and delete via the repository, or call a test-specific cleanup endpoint if the application provides that mechanism. If the test fails mid-flow, cleanup still needs to run in **finally** or **@AfterEach**.

The example above uses **body(request)** following RestTestClient's request builder API. Use your application's actual DTOs and endpoints when applying this.

## 7. Testing Validation and Error Responses Against a Real Server

An endpoint may work properly in a controller test yet still have issues when passing through filters, security, or exception handling registered in the full application context.

Example of sending invalid data:

~~~java
client.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateOrderRequest("", "UNKNOWN"))
        .exchange()
        .expectStatus().isBadRequest()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
        )
        .expectBody()
        .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");
~~~

Testing against a real server confirms that requests actually pass through:

- HTTP message converters and deserialization.
- Bean Validation if the endpoint uses validation.
- Controller advice or exception resolvers.
- Security filters and other filters.
- The error response configuration published by the application.

You can test other scenarios such as non-existent resources, requests missing authentication, insufficient role permissions, unsupported content types, or malformed JSON payloads.

An error response test should verify both status and error body. Merely checking that a request was rejected does not prove the API returns the expected error code or error schema.

## 8. Authentication, Cookies, and Headers Over Real HTTP

When you need to test the Security filter chain, requests must carry authentication details the way a real client does. Example using a bearer token:

~~~java
client.get()
        .uri("/api/profile")
        .headers(headers ->
                headers.setBearerAuth(accessToken)
        )
        .exchange()
        .expectStatus().isOk();
~~~

If tokens differ across tests, set the token on the request builder to avoid polluting default headers of a shared client. Do not store one test's token in the base client configuration where another test might accidentally reuse it.

You can test cookies or sessions by sending an appropriate **Cookie** header and asserting the **Set-Cookie** response header. When testing session mechanisms, retain the cookie returned from the previous request and send it back in the next request. If the API uses secure cookies or CSRF, simulate the exact flow a browser/client must follow.

A real HTTP client passes through the server's security filters. However, tests running on localhost do not automatically test external OAuth providers, identity proxies, or gateway configurations if those components are not in the request path.

## 9. Database and Test Data

With a real server, requests are processed on a separate server thread. A test method's transaction does not automatically wrap transactions inside HTTP requests. Therefore, placing **@Transactional** on a test does not guarantee that data created by an endpoint will roll back when the test finishes.

A clear fixture workflow typically consists of:

1. Creating dedicated test data before sending requests or via a creation endpoint.
2. Recording the id of that data.
3. Sending requests and asserting responses.
4. Deleting only the created test data during cleanup.

If tests run in parallel, use UUIDs, dedicated sequences, tenant keys, or separate databases/schemas to avoid data collisions. Do not call **deleteAll()** on a shared table in per-test cleanup.

For systems with multiple components such as a database, Redis, message broker, or object storage, cleanup must handle each resource properly. Reloading the Spring context does not automatically delete data stored outside the context.

## 10. A Real Server Does Not Mean the Entire Production Environment

**RANDOM_PORT** starts a real embedded server inside the test process. Requests pass through the HTTP connector, but typically still run on the same machine as the test.

This level can verify:

- The server starts and binds a port.
- HTTP requests reach the right application.
- Filter chain, security, routing, and controllers work.
- Message converters and serialization work.
- Services and the database integrate properly in the test environment.
- Status, headers, and response bodies received by the client.

It does not automatically verify:

- TLS termination at a load balancer or ingress.
- Whether a reverse proxy buffers or rewrites headers.
- Cluster DNS, service discovery, and network policies.
- Production secret and identity provider configurations.
- Differences between the test database and production database.
- Behavior of the entire deployment infrastructure.

If the goal is to test those components, use **RestTestClient.bindToServer()** with the base URL of a staging or corresponding deployed environment. In that case, tests need data and access permissions prepared specifically for that environment.

Never run a test against production if the test can create, modify, or delete data. Use a test environment with appropriate data and permissions.

## 11. When to Use RestTestClient, WebTestClient, or TestRestTemplate?

| Tool | Suitable for | Testing style |
|---|---|---|
| **RestTestClient** | REST APIs via the new Spring Framework fluent test API | Mock binding or real HTTP server depending on binding mode |
| **WebTestClient** | WebFlux and reactive endpoints; can also test some MVC endpoints | Mock WebFlux/MVC or real HTTP server |
| **TestRestTemplate** | Spring Boot integration tests for REST APIs, especially MVC | HTTP to embedded server |
| **MockMvc** | Spring MVC controllers and MVC infrastructure | Mock servlet request/response without opening a real socket |

Choose the tool based on stack and goals. If you want to test a synchronous REST API over real HTTP and the project supports Spring Framework 7.0, RestTestClient is a good fit. If you need to test reactive flows, SSE, or streaming, WebTestClient usually has a more suitable API. If the project uses an older Spring Boot and Spring Framework version, TestRestTemplate is a familiar HTTP integration testing option.

## 12. Common Errors When Binding to a Server

| Symptom | Cause | Resolution |
|---|---|---|
| Connection refused | Server has not started or client uses the wrong port | Use **RANDOM_PORT** and the port injected from **@LocalServerPort** |
| Test calls the wrong endpoint | Incorrect base URL or context path | Check base URL, servlet context path, and URI |
| Client receives 404 even though controller exists | Controller is not component-scanned or test profile does not load configuration | Use application configuration appropriate for the test |
| Response differs from mock test | Filters, security, converters, or real configuration are active | Check the full application context and actual requests |
| Test passes alone but fails in full suite | Shared data or overly broad cleanup | Use unique fixture IDs and clean up by ID |
| Test depends on a fixed port | Port is occupied or tests run concurrently | Use **RANDOM_PORT** |
| Data does not roll back after test | Server requests have transactions independent of the test method | Clean up explicitly or use an isolated database |
| Authentication differs from expectations | Token, cookie, or CSRF not sent like a real client | Check request headers/cookies and security flow |
| Test hangs when calling endpoint | Server does not return a response or client timeout is too long | Configure appropriate timeouts and check async/server logs |
| Test confuses mock server with real server | Using MOCK mode or binding to application context | Use **RANDOM_PORT** and **bindToServer()** |

When an error occurs, check status, response body, headers, and server logs. An exception in a controller may be turned into a 500 response; connection refused usually happens before the request reaches the application. These two errors must be diagnosed at two different layers.

## 13. Organizing a Multi-Level Test Suite

Not every test needs to start a real server. Responsibilities can be divided as follows:

| Test level | Tools | What to verify |
|---|---|---|
| Unit test | JUnit, Mockito | Service logic, pure validation, and standalone mapping |
| Controller test | MockMvc or WebTestClient mock binding | Routing, binding, serialization, and response contract |
| HTTP integration test | RestTestClient + **RANDOM_PORT** | HTTP connector, filters, security, controllers, services, and persistence |
| Deployment smoke test | RestTestClient + environment base URL | DNS, TLS, ingress, proxy, and deployment configuration in the request path |

HTTP integration tests are typically slower than mock tests because they must start the server and dependencies. Keep their count just enough to verify critical flows; use mock-bound tests for small response cases and repetitive logic.

An end-to-end test is valuable when it proves a flow clients actually rely on: a request is sent over HTTP, the server processes it with its running configuration, data is persisted or queried, and the client receives status, headers, and body matching the contract. **RestTestClient.bindToServer()** provides the starting point for that kind of testing.

